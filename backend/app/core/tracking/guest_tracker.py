"""
Guest track state machine and the main GuestTrackManager.

Responsibilities:
  - TrackState dataclass (per-track state: bbox, embeddings, votes, Kalman filter)
  - GuestTrackManager: IoU matching, embedding accumulation, identity resolution,
    guest creation / promotion, DB async writes

Delegates to:
  - tracking.embedding_utils — normalize, cosine_similarities, robust_mean
  - tracking.kalman           — KalmanFilterCorner
  - tracking.voting           — bbox_iou, vote_pgvector, vote_in_memory,
                                 resolve_from_votes, cast_vote
"""

import threading
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.core.tracking.embedding_utils import (
    calculate_robust_mean_embedding,
    cosine_similarities,
    normalize_embedding,
)
from app.core.tracking.kalman import KalmanFilterCorner
from app.core.tracking.voting import (
    bbox_iou,
    cast_vote,
    resolve_from_votes,
    vote_in_memory,
    vote_pgvector,
    _best_guest_match,
)
from app.db.connection import get_db_connection, insert_guest_record
from app.utils.logger import get_logger
from config import (
    GUEST_MIN_DETECTION_SCORE,
    GUEST_MIN_FACE_BBOX_SIZE,
    NEW_GUEST_DEBOUNCE_SECONDS,
    NEW_GUEST_DEBOUNCE_SIMILARITY,
    RECOGNITION_HIGH_CONF_THRESHOLD,
    RECOGNITION_MED_CONF_THRESHOLD,
)
from app.core.settings import system_settings
from db_config import USE_SUPABASE

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Track state
# ---------------------------------------------------------------------------

@dataclass
class TrackState:
    track_id: int
    bbox: tuple
    embeddings: list = field(default_factory=list)
    guest_embeddings: list = field(default_factory=list)
    local_track_id: str | None = None
    resolved_customer_id: str | None = None
    last_seen_frame: int = 0
    first_seen_frame: int = 0
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    recent_votes: list = field(default_factory=list)

    # Kalman filter
    kf: KalmanFilterCorner = None
    predicted_bbox: tuple = None
    state: str = "tracked"
    is_extracting: bool = False

    # Per-track customer profile cache (avoids repeated DB lookups per frame)
    cached_profile: dict | None = None

    def __post_init__(self):
        self.kf = KalmanFilterCorner(self.bbox)
        self.predicted_bbox = self.bbox
        self.state = "tracked"


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class GuestTrackManager:
    def __init__(
        self,
        buffer_size: int = 3,
        guest_creation_buffer_size: int = 8,
        similarity_threshold: float = 0.55,
        iou_threshold: float = 0.36,
        min_bbox_size: int = 100,
        min_detection_score: float = 0.85,
        guest_prefix: str = "GUEST",
    ):
        self.buffer_size = buffer_size
        self.guest_creation_buffer_size = guest_creation_buffer_size
        self.similarity_threshold = similarity_threshold
        self.iou_threshold = iou_threshold
        self.min_bbox_size = min_bbox_size
        self.min_detection_score = min_detection_score
        self.guest_prefix = guest_prefix

        self.known_embeddings: list = []
        self.known_ids: list = []
        self.guest_embeddings: list = []
        self.guest_ids: list = []
        self.tracks: dict[int, TrackState] = {}
        self.next_track_id: int = 1
        self.frame_index: int = 0
        self.lock = threading.Lock()
        self._save_lock = threading.Lock()

        self.use_pgvector: bool = USE_SUPABASE
        self._cached_conn = None
        self._ef_search_set: bool = False

        self.load_known_embeddings()

    # ------------------------------------------------------------------
    # Embedding store
    # ------------------------------------------------------------------

    def load_known_embeddings(self):
        if self.use_pgvector:
            self.known_embeddings = []
            self.known_ids = []
            self.guest_embeddings = []
            self.guest_ids = []
            logger.info("pgvector mode: skipping bulk embedding load (HNSW index used)")
            return
        try:
            from app.db.vector_search import fetch_all_embeddings_from_db
            conn = get_db_connection()
            try:
                (
                    self.known_embeddings,
                    self.known_ids,
                    self.guest_embeddings,
                    self.guest_ids,
                ) = fetch_all_embeddings_from_db(conn)
            finally:
                conn.close()
        except Exception:
            self.known_embeddings = []
            self.known_ids = []
            self.guest_embeddings = []
            self.guest_ids = []

    # stubs kept for API compatibility
    def _persist_known_embeddings_async(self): pass
    def persist_known_embeddings(self): pass

    # ------------------------------------------------------------------
    # pgvector connection helpers
    # ------------------------------------------------------------------

    def _get_cached_conn(self):
        if self._cached_conn is None:
            self._cached_conn = get_db_connection()
            if not self._ef_search_set:
                try:
                    self._cached_conn.execute("SET hnsw.ef_search = 40")
                    self._ef_search_set = True
                except Exception:
                    pass
        return self._cached_conn

    def _release_cached_conn(self):
        if self._cached_conn is not None:
            try:
                self._cached_conn.close()
            except Exception:
                pass
            self._cached_conn = None
            self._ef_search_set = False

    def _query_pgvector(self, embedding, top_k: int = 3, threshold: float = 0.45) -> list:
        try:
            from app.db.vector_search import search_similar_faces
            return search_similar_faces(
                self._get_cached_conn(), embedding, top_k=top_k, threshold=threshold
            )
        except Exception as e:
            logger.error("pgvector query failed: %s", e, exc_info=True)
            self._cached_conn = None
            self._ef_search_set = False
            return []

    # ------------------------------------------------------------------
    # Identity search (used externally, e.g. by search_identity callers)
    # ------------------------------------------------------------------

    def search_identity(self, embedding) -> tuple[str | None, float]:
        norm_emb = normalize_embedding(embedding)
        if self.use_pgvector:
            results = self._query_pgvector(norm_emb, top_k=1, threshold=self.similarity_threshold)
            if results and results[0][1] >= self.similarity_threshold:
                return results[0]
            # Also check in-memory guests
            best_id, best_sim = _best_guest_match(
                self.guest_embeddings, self.guest_ids, norm_emb, self.similarity_threshold
            )
            return best_id, best_sim
        else:
            combined = list(self.known_embeddings) + list(self.guest_embeddings)
            combined_ids = list(self.known_ids) + list(self.guest_ids)
            if not combined:
                return None, 0.0
            sims = cosine_similarities(combined, norm_emb)
            if sims.size == 0:
                return None, 0.0
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= self.similarity_threshold:
                return combined_ids[best_idx], best_sim
            return None, 0.0

    # ------------------------------------------------------------------
    # Guest promotion
    # ------------------------------------------------------------------

    def promote_guest(self, guest_id: str, new_id: str) -> bool:
        with self.lock:
            try:
                if self.use_pgvector:
                    try:
                        conn = self._get_cached_conn()
                        conn.execute(
                            "UPDATE customer_embeddings SET customer_id = ? WHERE customer_id = ?",
                            (new_id, guest_id),
                        )
                        conn.execute(
                            "UPDATE recognize_logs SET customer_id = ? WHERE customer_id = ?",
                            (new_id, guest_id),
                        )
                        conn.execute(
                            "DELETE FROM customers WHERE customer_id = ?", (guest_id,)
                        )
                        conn.commit()
                        if guest_id in self.guest_ids:
                            idx = self.guest_ids.index(guest_id)
                            self.guest_embeddings.pop(idx)
                            self.guest_ids.pop(idx)
                        return True
                    except Exception as e:
                        logger.error("Error promoting guest in pgvector: %s", e, exc_info=True)
                        return False
                else:
                    if guest_id not in self.guest_ids:
                        return False
                    idx = self.guest_ids.index(guest_id)
                    emb = self.guest_embeddings.pop(idx)
                    self.guest_ids.pop(idx)
                    self.known_embeddings.append(emb)
                    self.known_ids.append(new_id)
                    return True
            except Exception:
                return False

    # ------------------------------------------------------------------
    # Guest creation
    # ------------------------------------------------------------------

    def _create_guest_id(self) -> str:
        return f"{self.guest_prefix}_{self.frame_index}_{self.next_track_id:04d}"

    def _register_guest(self, embedding: np.ndarray, track_state: TrackState) -> str:
        guest_id = self._create_guest_id()
        track_state.resolved_customer_id = guest_id
        normalized = normalize_embedding(embedding)
        self.guest_embeddings.append(normalized)
        self.guest_ids.append(guest_id)
        self._insert_guest_into_main_db_async(guest_id, normalized)
        return guest_id

    def _insert_guest_into_main_db_async(self, guest_id: str, embedding=None):
        def worker():
            conn = None
            try:
                logger.info("Inserting guest %s into DB", guest_id)
                conn = get_db_connection()
                insert_guest_record(conn, guest_id)
                logger.info("Guest record inserted for %s", guest_id)
                if embedding is not None:
                    try:
                        from app.db.vector_search import insert_embedding_with_vector
                        blob = np.asarray(embedding, dtype=np.float32).tobytes()
                        insert_embedding_with_vector(
                            conn, guest_id, blob, embedding,
                            dim=len(embedding), model_name="edgeface_s_gamma_05",
                        )
                        conn.commit()
                        logger.info("Embedding inserted for %s", guest_id)
                    except Exception as e:
                        logger.error("Failed to insert embedding for %s: %s", guest_id, e, exc_info=True)
            except Exception as e:
                logger.error("_insert_guest_into_main_db_async error for %s: %s", guest_id, e, exc_info=True)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Recognition (per-track, called from process_faces)
    # ------------------------------------------------------------------

    def _recognize_face(self, track_state: TrackState, record: dict, now: float, frame=None, embedder=None) -> str | None:
        quality_ok = bool(record.get("quality_ok", True))
        existing_customer_id = track_state.resolved_customer_id

        # Already resolved as a registered customer — skip
        if existing_customer_id and not str(existing_customer_id).startswith("GUEST_"):
            return existing_customer_id

        embedding = record.get("embedding")

        # Evaluate guest-quality gate
        guest_quality_ok = record.get("guest_quality_ok")
        if guest_quality_ok is None:
            bbox = record["bbox"]
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            score = record.get("score", 1.0)
            min_bbox = system_settings.get("guest_min_face_bbox_size", GUEST_MIN_FACE_BBOX_SIZE)
            min_score = system_settings.get("guest_min_detection_score", GUEST_MIN_DETECTION_SCORE)
            guest_quality_ok = w >= min_bbox and h >= min_bbox and score >= min_score and quality_ok
        else:
            guest_quality_ok = bool(guest_quality_ok)

        # Accumulate embedding
        if quality_ok and embedding is not None:
            norm_emb = normalize_embedding(embedding)
            if not track_state.embeddings or not np.array_equal(track_state.embeddings[-1], norm_emb):
                track_state.embeddings.append(norm_emb)
                if guest_quality_ok:
                    track_state.guest_embeddings.append(norm_emb)

        # Run voting (per-frame)
        if track_state.embeddings:
            current_emb = track_state.embeddings[-1]

            if self.use_pgvector:
                resolved = vote_pgvector(
                    track_state,
                    current_emb,
                    self._query_pgvector,
                    self.similarity_threshold,
                    self.guest_embeddings,
                    self.guest_ids,
                )
            else:
                resolved = vote_in_memory(
                    track_state,
                    current_emb,
                    self.known_embeddings,
                    self.known_ids,
                    self.guest_embeddings,
                    self.guest_ids,
                    self.similarity_threshold,
                )
            if resolved:
                existing_customer_id = resolved

        resolved_customer_id = existing_customer_id or None

        # Fallback: mean-embedding match after buffer fills
        if resolved_customer_id is None and len(track_state.embeddings) >= self.buffer_size:
            avg_embedding = calculate_robust_mean_embedding(
                track_state.embeddings[-self.buffer_size:]
            )
            if self.use_pgvector:
                results = self._query_pgvector(
                    avg_embedding, top_k=1, threshold=self.similarity_threshold
                )
                if results and results[0][1] >= self.similarity_threshold:
                    resolved_customer_id = results[0][0]
                if not resolved_customer_id:
                    best_id, _ = _best_guest_match(
                        self.guest_embeddings, self.guest_ids,
                        avg_embedding, self.similarity_threshold,
                    )
                    resolved_customer_id = best_id
            else:
                combined = list(self.known_embeddings) + list(self.guest_embeddings)
                combined_ids = list(self.known_ids) + list(self.guest_ids)
                if combined:
                    sims = cosine_similarities(combined, avg_embedding)
                    if sims.size > 0:
                        best_idx = int(np.argmax(sims))
                        if float(sims[best_idx]) >= self.similarity_threshold:
                            resolved_customer_id = combined_ids[best_idx]

            # Create new guest if still unresolved and enough high-quality frames
            if (
                resolved_customer_id is None
                and len(track_state.guest_embeddings) >= self.guest_creation_buffer_size
            ):
                avg_guest_emb = calculate_robust_mean_embedding(
                    track_state.guest_embeddings[-self.guest_creation_buffer_size:]
                )
                if avg_guest_emb is not None:
                    resolved_customer_id = self._register_guest(avg_guest_emb, track_state)

            if resolved_customer_id is not None:
                track_state.resolved_customer_id = resolved_customer_id

        return resolved_customer_id

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_faces(self, face_records: list, frame=None, embedder=None) -> list:
        with self.lock:
            self.frame_index += 1
            now = time.monotonic()

            # 1. Kalman predict
            for track in self.tracks.values():
                if track.kf is not None:
                    pred = track.kf.predict()
                    track.predicted_bbox = tuple(map(int, pred))
                else:
                    track.predicted_bbox = track.bbox

            # 2. Partition detections; apply local_track_id pre-association
            high_threshold = 0.60
            high_records, low_records = [], []
            matched_by_local_id = []
            tracks_pool = [t for t in self.tracks.values() if t.state in ("tracked", "lost")]
            remaining_records = []

            for record in face_records:
                tid = record.get("local_track_id")
                if tid:
                    matched_track = next((t for t in tracks_pool if t.local_track_id == tid), None)
                    if matched_track:
                        matched_by_local_id.append((matched_track, record))
                        tracks_pool.remove(matched_track)
                        continue
                remaining_records.append(record)

            for record in remaining_records:
                score = record.get("score", 1.0)
                if score < self.min_detection_score:
                    continue
                (high_records if score >= high_threshold else low_records).append(record)

            # 3. First association: pool vs high-score detections
            matched_1, unmatched_tracks, unmatched_high_dets = self._associate(
                tracks_pool, high_records
            )

            # 4. Second association: unmatched tracks vs low-score detections
            matched_2, unmatched_tracks_final, _ = self._associate(
                unmatched_tracks, low_records
            )

            # 5. Update matched tracks; queue batch embedding requests
            all_matches = matched_by_local_id + matched_1 + matched_2
            target_len = max(self.buffer_size, self.guest_creation_buffer_size)
            batch_landmarks, batch_records, batch_tracks = [], [], []

            for track, det in all_matches:
                updated_box = track.kf.update(det["bbox"])
                track.bbox = tuple(map(int, updated_box))
                track.state = "tracked"
                track.last_seen_frame = self.frame_index
                track.last_seen_at = now
                self._maybe_queue_embedding(
                    track, det, target_len,
                    batch_landmarks, batch_records, batch_tracks,
                )

            # 6. Create new tracks for unmatched high-score detections
            new_tracks_to_process = []
            for det in unmatched_high_dets:
                x1, y1, x2, y2 = det["bbox"]
                if (x2 - x1) < self.min_bbox_size or (y2 - y1) < self.min_bbox_size:
                    continue
                track_id = self.next_track_id
                self.next_track_id += 1
                new_track = TrackState(
                    track_id=track_id,
                    bbox=det["bbox"],
                    local_track_id=det.get("local_track_id"),
                    last_seen_frame=self.frame_index,
                    first_seen_frame=self.frame_index,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                self.tracks[track_id] = new_track
                new_tracks_to_process.append((new_track, det))
                self._maybe_queue_embedding(
                    new_track, det, target_len,
                    batch_landmarks, batch_records, batch_tracks,
                )

            # 7. Batch embedding extraction
            if batch_landmarks and frame is not None and embedder is not None:
                try:
                    batch_embs = embedder.get_batch_embeddings(frame, batch_landmarks)
                    for det, emb in zip(batch_records, batch_embs):
                        if emb is not None:
                            det["embedding"] = emb
                except Exception as e:
                    import logging
                    logging.warning("Batch extraction error: %s", e)

            # 8. Recognize identity for each detection
            matched_detections: dict[int, tuple[int, str | None]] = {}
            for track, det in all_matches:
                resolved = self._recognize_face(track, det, now, frame, embedder)
                matched_detections[id(det)] = (track.track_id, resolved)
            for new_track, det in new_tracks_to_process:
                resolved = self._recognize_face(new_track, det, now, frame, embedder)
                matched_detections[id(det)] = (new_track.track_id, resolved)

            # 9. Mark unmatched tracks as lost
            for track in unmatched_tracks_final:
                track.state = "lost"

            # 10. Prune stale tracks (lost > 30 frames)
            stale_cutoff = self.frame_index - 30
            self.tracks = {
                tid: t for tid, t in self.tracks.items()
                if t.last_seen_frame >= stale_cutoff
            }

            # 11. Build output list (1-to-1 with face_records)
            return self._build_output(face_records, matched_detections)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _associate(
        self, tracks_pool: list, detections: list
    ) -> tuple[list, list, list]:
        """
        Hungarian-algorithm IoU matching between tracks and detections.
        Returns (matched_pairs, unmatched_tracks, unmatched_detections).
        """
        if not tracks_pool or not detections:
            return [], list(tracks_pool), list(detections)

        cost_matrix = np.array(
            [
                [1.0 - bbox_iou(t.predicted_bbox, d["bbox"]) for d in detections]
                for t in tracks_pool
            ],
            dtype=np.float32,
        )
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        matched_rows = set(row_ind)
        matched_cols = set(col_ind)

        matched, unmatched_t, unmatched_d = [], [], []
        for r, c in zip(row_ind, col_ind):
            if 1.0 - cost_matrix[r, c] >= self.iou_threshold:
                matched.append((tracks_pool[r], detections[c]))
            else:
                unmatched_t.append(tracks_pool[r])
                unmatched_d.append(detections[c])

        unmatched_t += [tracks_pool[i] for i in range(len(tracks_pool)) if i not in matched_rows]
        unmatched_d += [detections[j] for j in range(len(detections)) if j not in matched_cols]
        return matched, unmatched_t, unmatched_d

    @staticmethod
    def _maybe_queue_embedding(track, det, target_len, batch_landmarks, batch_records, batch_tracks):
        quality_ok = bool(det.get("quality_ok", det.get("guest_quality_ok", True)))
        if (
            track.resolved_customer_id is None
            and len(track.embeddings) < target_len
            and det.get("embedding") is None
            and quality_ok
            and "landmark" in det
        ):
            batch_landmarks.append(det["landmark"])
            batch_records.append(det)
            batch_tracks.append(track)

    def _build_output(self, face_records: list, matched_detections: dict) -> list:
        outputs = []
        for record in face_records:
            bbox = record["bbox"]
            quality_ok = bool(record.get("quality_ok", True))
            if id(record) in matched_detections:
                track_id, resolved_id = matched_detections[id(record)]
                ts = self.tracks.get(track_id)
                outputs.append({
                    "track_id": track_id,
                    "customer_id": resolved_id,
                    "bbox": bbox,
                    "embedding_ready": (len(ts.embeddings) >= self.buffer_size if ts else False),
                    "quality_ok": quality_ok,
                    "pending_guest": (
                        resolved_id is None
                        and len(ts.guest_embeddings) < self.guest_creation_buffer_size
                        if ts else False
                    ),
                })
            else:
                outputs.append({
                    "track_id": None,
                    "customer_id": None,
                    "bbox": bbox,
                    "embedding_ready": False,
                    "quality_ok": False,
                    "pending_guest": False,
                })
        return outputs
