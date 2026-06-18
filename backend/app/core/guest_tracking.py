import pickle
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.db.connection import get_db_connection, ensure_schema, insert_guest_record
from db_config import USE_SUPABASE
from app.utils.logger import get_logger
from config import (
    NEW_GUEST_DEBOUNCE_SECONDS,
    NEW_GUEST_DEBOUNCE_SIMILARITY,
    GUEST_MIN_FACE_BBOX_SIZE,
    GUEST_MIN_DETECTION_SCORE,
)

logger = get_logger(__name__)


def normalize_embedding(embedding):
    embedding = np.asarray(embedding, dtype=np.float32)
    if embedding.ndim == 1:
        norm = np.sqrt(np.dot(embedding, embedding))
        if norm == 0:
            return embedding
        return embedding / norm
    else:
        norm = np.linalg.norm(embedding, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        return embedding / norm


def cosine_similarities(known_embeddings, embedding):
    if known_embeddings is None:
        return np.array([])

    known = np.asarray(known_embeddings, dtype=np.float32)
    if known.size == 0:
        return np.array([])

    return np.dot(known, np.asarray(embedding, dtype=np.float32))


def bbox_iou(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1 + 1)
    inter_h = max(0, inter_y2 - inter_y1 + 1)
    inter_area = inter_w * inter_h

    area_a = max(0, ax2 - ax1 + 1) * max(0, ay2 - ay1 + 1)
    area_b = max(0, bx2 - bx1 + 1) * max(0, by2 - by1 + 1)
    denom = area_a + area_b - inter_area
    if denom <= 0:
        return 0.0
    return inter_area / denom


class KalmanFilterCorner:
    """A simple constant velocity Kalman Filter for bounding box corners (x1, y1, x2, y2)."""
    def __init__(self, bbox):
        # State vector: [x1, y1, x2, y2, vx1, vy1, vx2, vy2]^T
        x1, y1, x2, y2 = bbox
        self.x = np.array([x1, y1, x2, y2, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        
        # State covariance P
        self.P = np.eye(8, dtype=np.float32) * 10.0
        self.P[4:, 4:] *= 10.0
        
        # Transition matrix F
        self.F = np.eye(8, dtype=np.float32)
        self.F[0, 4] = 1.0
        self.F[1, 5] = 1.0
        self.F[2, 6] = 1.0
        self.F[3, 7] = 1.0
        
        # Measurement matrix H
        self.H = np.zeros((4, 8), dtype=np.float32)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0
        self.H[3, 3] = 1.0
        
        # Process noise covariance Q
        self.Q = np.eye(8, dtype=np.float32) * 0.1
        self.Q[4:, 4:] *= 0.5
        
        # Measurement noise covariance R
        self.R = np.eye(4, dtype=np.float32) * 1.0
        
    def predict(self):
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return self.x[:4]
        
    def update(self, bbox):
        z = np.array(bbox, dtype=np.float32)
        y = z - np.dot(self.H, self.x)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        self.x = self.x + np.dot(K, y)
        self.P = self.P - np.dot(np.dot(K, self.H), self.P)
        return self.x[:4]


@dataclass
class TrackState:
    track_id: int
    bbox: tuple
    embeddings: list = field(default_factory=list)
    guest_embeddings: list = field(default_factory=list)
    resolved_customer_id: str | None = None
    last_seen_frame: int = 0
    first_seen_frame: int = 0
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    recent_votes: list = field(default_factory=list)
    
    # Kalman Filter variables
    kf: KalmanFilterCorner = None
    predicted_bbox: tuple = None
    state: str = "tracked"

    # Track-level customer profile cache (populated on first DB lookup,
    # reused for every subsequent frame until the track expires).
    cached_profile: dict | None = None

    def __post_init__(self):
        self.kf = KalmanFilterCorner(self.bbox)
        self.predicted_bbox = self.bbox
        self.state = "tracked"


class GuestTrackManager:
    def __init__(
        self,
        encode_file,
        guest_cache_file=None,
        buffer_size=3,
        guest_creation_buffer_size=8,
        similarity_threshold=0.38,
        iou_threshold=0.3,
        min_bbox_size=100,
        min_detection_score=0.85,
        guest_prefix="GUEST",
    ):
        self.encode_file = Path(encode_file)
        self.guest_cache_file = Path(guest_cache_file) if guest_cache_file else None
        self.buffer_size = buffer_size
        self.guest_creation_buffer_size = guest_creation_buffer_size
        self.similarity_threshold = similarity_threshold
        self.iou_threshold = iou_threshold
        self.min_bbox_size = min_bbox_size
        self.min_detection_score = min_detection_score
        self.guest_prefix = guest_prefix

        self.known_embeddings = []
        self.known_ids = []
        self.tracks = {}
        self.next_track_id = 1
        self.frame_index = 0
        self.lock = threading.Lock()
        self._save_lock = threading.Lock()
        self.guest_embeddings = []
        self.guest_ids = []
        self.use_pgvector = USE_SUPABASE  # Use HNSW index when Supabase is available

        self.load_known_embeddings()

    def load_known_embeddings(self):
        if not self.encode_file.exists():
            self.known_embeddings = []
            self.known_ids = []
            return

        try:
            if self.encode_file.stat().st_size == 0:
                raise EOFError("empty encodings file")

            with open(self.encode_file, "rb") as file:
                payload = pickle.load(file)
        except (EOFError, pickle.UnpicklingError, OSError, ValueError):
            self.known_embeddings = []
            self.known_ids = []
            return

        if isinstance(payload, (list, tuple)) and len(payload) == 2:
            self.known_embeddings, self.known_ids = payload
        else:
            self.known_embeddings = []
            self.known_ids = []

        # Attempt to load guest cache if available
        if self.guest_cache_file and self.guest_cache_file.exists():
            try:
                if self.guest_cache_file.stat().st_size == 0:
                    raise EOFError("empty guest cache file")
                with open(self.guest_cache_file, "rb") as gf:
                    gpayload = pickle.load(gf)
                if isinstance(gpayload, (list, tuple)) and len(gpayload) == 2:
                    self.guest_embeddings, self.guest_ids = gpayload
            except (EOFError, pickle.UnpicklingError, OSError, ValueError):
                self.guest_embeddings = []
                self.guest_ids = []

    def _persist_known_embeddings_async(self):
        def worker():
            with self._save_lock:
                if self.guest_cache_file is None:
                    return

                self.guest_cache_file.parent.mkdir(parents=True, exist_ok=True)
                payload = [self.guest_embeddings, self.guest_ids]
                with open(self.guest_cache_file, "wb") as file:
                    pickle.dump(payload, file)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def persist_known_embeddings(self):
        """Synchronously persist `self.known_embeddings` + `self.known_ids` to the main encode file."""
        with self._save_lock:
            try:
                self.encode_file.parent.mkdir(parents=True, exist_ok=True)
                payload = [self.known_embeddings, self.known_ids]
                with open(self.encode_file, "wb") as f:
                    pickle.dump(payload, f)
            except Exception:
                pass

    def promote_guest(self, guest_id: str, new_id: str) -> bool:
        """Promote a guest entry (guest_id) into the known encodings with new_id.

        Returns True if promotion succeeded, False otherwise.
        """
        with self.lock:
            try:
                if guest_id not in self.guest_ids:
                    return False
                idx = int(self.guest_ids.index(guest_id))
                emb = self.guest_embeddings.pop(idx)
                self.guest_ids.pop(idx)

                # append to known embeddings/ids
                self.known_embeddings.append(emb)
                self.known_ids.append(new_id)

                # persist both: main encodings and updated guest cache
                self.persist_known_embeddings()
                # update guest cache file async
                self._persist_known_embeddings_async()

                # Also write promoted embedding to pgvector
                if self.use_pgvector:
                    try:
                        from app.db.vector_search import insert_embedding_with_vector
                        conn = get_db_connection()
                        try:
                            blob = np.asarray(emb, dtype=np.float32).tobytes()
                            insert_embedding_with_vector(
                                conn, new_id, blob, emb,
                                dim=len(emb), model_name="w600k_mbf",
                            )
                            conn.commit()
                        finally:
                            conn.close()
                    except Exception:
                        pass

                return True
            except Exception:
                return False

    def _create_guest_id(self):
        return f"{self.guest_prefix}_{self.frame_index}_{self.next_track_id:04d}"

    def _register_guest(self, embedding, track_state):
        guest_id = self._create_guest_id()
        track_state.resolved_customer_id = guest_id
        normalized = normalize_embedding(embedding)
        self.guest_embeddings.append(normalized)
        self.guest_ids.append(guest_id)
        self._insert_guest_into_main_db_async(guest_id, normalized)
        self._persist_known_embeddings_async()
        return guest_id

    def _insert_guest_into_main_db_async(self, guest_id, embedding=None):
        def worker():
            try:
                conn = get_db_connection()
                ensure_schema(conn)
                insert_guest_record(conn, guest_id)

                # Also store the embedding in customer_embeddings with pgvector
                if embedding is not None and self.use_pgvector:
                    try:
                        from app.db.vector_search import insert_embedding_with_vector
                        blob = np.asarray(embedding, dtype=np.float32).tobytes()
                        insert_embedding_with_vector(
                            conn, guest_id, blob, embedding,
                            dim=len(embedding), model_name="w600k_mbf",
                        )
                        conn.commit()
                    except Exception:
                        pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _query_pgvector(self, embedding, top_k=3):
        """Query pgvector HNSW index for the closest matches.

        Returns a list of (customer_id, similarity) tuples.
        Falls back to empty list on any error.
        """
        try:
            from app.db.vector_search import search_similar_faces
            conn = get_db_connection()
            try:
                results = search_similar_faces(
                    conn, embedding, top_k=top_k, threshold=0.45
                )
                return results
            finally:
                conn.close()
        except Exception:
            return []

    def _recognize_face(self, track_state, record, now, frame=None, embedder=None):
        quality_ok = bool(record.get("quality_ok", True))
        
        existing_customer_id = track_state.resolved_customer_id

        if existing_customer_id and not str(existing_customer_id).startswith("GUEST_"):
            return existing_customer_id

        # --- LAZY EMBEDDING EXTRACTION ---
        if record.get("embedding") is None and quality_ok and frame is not None and embedder is not None and "landmark" in record:
            try:
                # We only compute embedding if we don't know who this is yet!
                record["embedding"] = embedder.get_embedding(frame, record["landmark"])
            except Exception as e:
                logger.warning("Lazy embedding error: %s", e)
                record["embedding"] = None

        embedding = record.get("embedding")

        # Calculate guest_quality_ok if not explicitly provided
        guest_quality_ok = record.get("guest_quality_ok")
        if guest_quality_ok is None:
            bbox = record["bbox"]
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            score = record.get("score", 1.0)
            guest_quality_ok = (
                w >= GUEST_MIN_FACE_BBOX_SIZE and
                h >= GUEST_MIN_FACE_BBOX_SIZE and
                score >= GUEST_MIN_DETECTION_SCORE and
                quality_ok
            )
        else:
            guest_quality_ok = bool(guest_quality_ok)

        if quality_ok and embedding is not None:
            norm_emb = normalize_embedding(embedding)
            track_state.embeddings.append(norm_emb)
            if guest_quality_ok:
                track_state.guest_embeddings.append(norm_emb)

            # Build combined lists for matching
            combined_embeddings = []
            combined_ids = []
            if self.known_embeddings:
                combined_embeddings.extend(self.known_embeddings)
                combined_ids.extend(self.known_ids)
            if self.guest_embeddings:
                combined_embeddings.extend(self.guest_embeddings)
                combined_ids.extend(self.guest_ids)

            # --- Multi-frame Voting Logic ---
            if self.use_pgvector:
                # pgvector path: query HNSW index in Supabase for nearest match
                pgvec_results = self._query_pgvector(norm_emb, top_k=3)
                if pgvec_results:
                    voted_id = pgvec_results[0][0]  # best match customer_id
                    track_state.recent_votes.append(voted_id)
                else:
                    # Also check in-memory guest embeddings (not yet in DB)
                    if self.guest_embeddings:
                        guest_sims = cosine_similarities(self.guest_embeddings, norm_emb)
                        if guest_sims.size > 0:
                            best_g_idx = int(np.argmax(guest_sims))
                            if float(guest_sims[best_g_idx]) >= 0.45:
                                track_state.recent_votes.append(self.guest_ids[best_g_idx])
                            else:
                                track_state.recent_votes.append(None)
                        else:
                            track_state.recent_votes.append(None)
                    else:
                        track_state.recent_votes.append(None)
            elif len(combined_embeddings) > 0:
                # In-memory path (SQLite / fallback)
                similarities = cosine_similarities(combined_embeddings, norm_emb)
                if similarities.size > 0:
                    best_index = int(np.argmax(similarities))
                    best_sim = float(similarities[best_index])
                    # Lower threshold for individual frame vote
                    if best_sim >= 0.45:
                        if best_index < len(self.known_embeddings):
                            voted_id = self.known_ids[best_index]
                        else:
                            guest_idx = best_index - len(self.known_embeddings)
                            voted_id = self.guest_ids[guest_idx]
                        
                        track_state.recent_votes.append(voted_id)
                    else:
                        # Append None to represent no confident vote for this frame
                        track_state.recent_votes.append(None)
                        
            # Keep only the last 5 votes
            if len(track_state.recent_votes) > 5:
                track_state.recent_votes = track_state.recent_votes[-5:]
                
            # Tally votes: if 3 out of 5 frames match the same ID, resolve it
            if len(track_state.recent_votes) >= 3:
                from collections import Counter
                valid_votes = [v for v in track_state.recent_votes if v is not None]
                if valid_votes:
                    vote_counts = Counter(valid_votes)
                    top_id, top_count = vote_counts.most_common(1)[0]
                    if top_count >= 3:
                        existing_customer_id = top_id
                        track_state.resolved_customer_id = top_id
                        
                        # --- AUTO MERGE LOGIC ---
                        # If we have low-quality/glasses frames in the buffer and we successfully identified the person,
                        # we merge an averaged "glasses" template into the face bank to improve future recognition.
                        if len(track_state.guest_embeddings) > 0 and not str(top_id).startswith("GUEST_"):
                            avg_g_emb = normalize_embedding(np.mean(track_state.guest_embeddings, axis=0))
                            self.known_embeddings.append(avg_g_emb)
                            self.known_ids.append(top_id)
                            track_state.guest_embeddings.clear()
                            self.persist_known_embeddings()

        resolved_customer_id = existing_customer_id if existing_customer_id else None
        
        # Fallback to mean embedding for resolution or guest creation
        if resolved_customer_id is None and len(track_state.embeddings) >= self.buffer_size:
            avg_embedding = normalize_embedding(np.mean(track_state.embeddings[-self.buffer_size :], axis=0))

            # Try pgvector first for the fallback mean-embedding match
            if self.use_pgvector:
                pgvec_results = self._query_pgvector(avg_embedding, top_k=1)
                if pgvec_results and pgvec_results[0][1] >= self.similarity_threshold:
                    resolved_customer_id = pgvec_results[0][0]
                # Also check in-memory guests
                if not resolved_customer_id and self.guest_embeddings:
                    guest_sims = cosine_similarities(self.guest_embeddings, avg_embedding)
                    if guest_sims.size > 0:
                        best_g_idx = int(np.argmax(guest_sims))
                        if float(guest_sims[best_g_idx]) >= self.similarity_threshold:
                            resolved_customer_id = self.guest_ids[best_g_idx]
            elif len(combined_embeddings) > 0:
                similarities = cosine_similarities(combined_embeddings, avg_embedding)
                if similarities.size > 0:
                    best_index = int(np.argmax(similarities))
                    if float(similarities[best_index]) >= self.similarity_threshold:
                        if best_index < len(self.known_embeddings):
                            resolved_customer_id = self.known_ids[best_index]
                        else:
                            guest_idx = best_index - len(self.known_embeddings)
                            resolved_customer_id = self.guest_ids[guest_idx]

            if resolved_customer_id is None and len(track_state.guest_embeddings) >= self.guest_creation_buffer_size:
                known_similarity = 0.0
                if self.known_embeddings:
                    known_scores = cosine_similarities(self.known_embeddings, avg_embedding)
                    if known_scores.size > 0:
                        known_similarity = float(np.max(known_scores))

                track_age_seconds = now - track_state.first_seen_at
                if track_age_seconds < NEW_GUEST_DEBOUNCE_SECONDS:
                    resolved_customer_id = None
                elif known_similarity >= NEW_GUEST_DEBOUNCE_SIMILARITY:
                    resolved_customer_id = None
                else:
                    resolved_customer_id = self._register_guest(avg_embedding, track_state)

            if resolved_customer_id is None and not str(existing_customer_id).startswith("GUEST_"):
                resolved_customer_id = None
            else:
                track_state.resolved_customer_id = resolved_customer_id

        return resolved_customer_id

    def process_faces(self, face_records, frame=None, embedder=None):
        with self.lock:
            self.frame_index += 1
            now = time.monotonic()

            # 1. Predict new position of all tracks using Kalman Filter
            for track_id, track in self.tracks.items():
                if track.kf is not None:
                    pred = track.kf.predict()
                    track.predicted_bbox = tuple(map(int, pred))
                else:
                    track.predicted_bbox = track.bbox

            # 2. Divide detections into high-score and low-score
            high_score_threshold = 0.60
            high_records = []
            low_records = []

            for record in face_records:
                score = record.get("score", 1.0)
                if score < self.min_detection_score:
                    continue  # Filter out detections below absolute minimum
                if score >= high_score_threshold:
                    high_records.append(record)
                else:
                    low_records.append(record)

            # 3. Get currently active tracks pool (tracked + recently lost)
            tracks_pool = [t for t in self.tracks.values() if t.state in ("tracked", "lost")]

            matched_1 = []
            unmatched_tracks = []
            unmatched_high_dets = []

            # --- First Association: Pool Tracks vs High-Score Detections ---
            if len(tracks_pool) > 0 and len(high_records) > 0:
                cost_matrix = np.zeros((len(tracks_pool), len(high_records)), dtype=np.float32)
                for i, track in enumerate(tracks_pool):
                    for j, det in enumerate(high_records):
                        cost_matrix[i, j] = 1.0 - bbox_iou(track.predicted_bbox, det["bbox"])

                row_ind, col_ind = linear_sum_assignment(cost_matrix)

                matched_track_indices = set(row_ind)
                matched_det_indices = set(col_ind)

                for r, c in zip(row_ind, col_ind):
                    iou = 1.0 - cost_matrix[r, c]
                    if iou >= self.iou_threshold:
                        matched_1.append((tracks_pool[r], high_records[c]))
                    else:
                        unmatched_tracks.append(tracks_pool[r])
                        unmatched_high_dets.append(high_records[c])

                for i in range(len(tracks_pool)):
                    if i not in matched_track_indices:
                        unmatched_tracks.append(tracks_pool[i])
                for j in range(len(high_records)):
                    if j not in matched_det_indices:
                        unmatched_high_dets.append(high_records[j])
            else:
                unmatched_tracks = list(tracks_pool)
                unmatched_high_dets = list(high_records)

            # --- Second Association: Unmatched Tracks vs Low-Score Detections ---
            matched_2 = []
            unmatched_tracks_final = []

            if len(unmatched_tracks) > 0 and len(low_records) > 0:
                cost_matrix_2 = np.zeros((len(unmatched_tracks), len(low_records)), dtype=np.float32)
                for i, track in enumerate(unmatched_tracks):
                    for j, det in enumerate(low_records):
                        cost_matrix_2[i, j] = 1.0 - bbox_iou(track.predicted_bbox, det["bbox"])

                row_ind2, col_ind2 = linear_sum_assignment(cost_matrix_2)

                matched_track_indices2 = set(row_ind2)

                for r, c in zip(row_ind2, col_ind2):
                    iou = 1.0 - cost_matrix_2[r, c]
                    if iou >= self.iou_threshold:
                        matched_2.append((unmatched_tracks[r], low_records[c]))
                    else:
                        unmatched_tracks_final.append(unmatched_tracks[r])

                for i in range(len(unmatched_tracks)):
                    if i not in matched_track_indices2:
                        unmatched_tracks_final.append(unmatched_tracks[i])
            else:
                unmatched_tracks_final = list(unmatched_tracks)

            # 5. Process matches and update states
            all_matches = matched_1 + matched_2
            matched_detections = {}

            for track, det in all_matches:
                updated_box = track.kf.update(det["bbox"])
                track.bbox = tuple(map(int, updated_box))
                track.state = "tracked"
                track.last_seen_frame = self.frame_index
                track.last_seen_at = now

                resolved_id = self._recognize_face(track, det, now, frame, embedder)
                matched_detections[id(det)] = (track.track_id, resolved_id)

            # 6. Initialize new tracks for unmatched high-score detections
            for det in unmatched_high_dets:
                x1, y1, x2, y2 = det["bbox"]
                w, h = x2 - x1, y2 - y1
                if w < self.min_bbox_size or h < self.min_bbox_size:
                    continue  # Ignore small faces for new tracks

                track_id = self.next_track_id
                self.next_track_id += 1

                new_track = TrackState(
                    track_id=track_id,
                    bbox=det["bbox"],
                    last_seen_frame=self.frame_index,
                    first_seen_frame=self.frame_index,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                self.tracks[track_id] = new_track

                resolved_id = self._recognize_face(new_track, det, now, frame, embedder)
                matched_detections[id(det)] = (track_id, resolved_id)

            # 7. Set unmatched tracks as lost
            for track in unmatched_tracks_final:
                track.state = "lost"

            # 8. Clean up stale tracks (lost for > 30 frames)
            stale_cutoff = self.frame_index - 30
            self.tracks = {
                tid: t for tid, t in self.tracks.items()
                if t.last_seen_frame >= stale_cutoff
            }

            # 9. Build output mapped 1-to-1 to input face_records
            outputs = []
            for record in face_records:
                bbox = record["bbox"]
                quality_ok = bool(record.get("quality_ok", True))

                if id(record) in matched_detections:
                    track_id, resolved_id = matched_detections[id(record)]
                    track_state = self.tracks.get(track_id)
                    embedding_ready = len(track_state.embeddings) >= self.buffer_size if track_state else False
                    pending_guest = resolved_id is None and len(track_state.guest_embeddings) < self.guest_creation_buffer_size if track_state else False

                    outputs.append(
                        {
                            "track_id": track_id,
                            "customer_id": resolved_id,
                            "bbox": bbox,
                            "embedding_ready": embedding_ready,
                            "quality_ok": quality_ok,
                            "pending_guest": pending_guest,
                        }
                    )
                else:
                    outputs.append(
                        {
                            "track_id": None,
                            "customer_id": None,
                            "bbox": bbox,
                            "embedding_ready": False,
                            "quality_ok": False,
                            "pending_guest": False,
                        }
                    )

            return outputs
