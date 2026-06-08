import pickle
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import scipy.optimize

from app.db.connection import get_db_connection, ensure_schema, insert_guest_record
from config import NEW_GUEST_DEBOUNCE_SECONDS, NEW_GUEST_DEBOUNCE_SIMILARITY
from app.core.kalman_filter import KalmanFilter


def normalize_embedding(embedding):
    embedding = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(embedding)
    if norm == 0:
        return embedding
    return embedding / norm


def cosine_similarities(known_embeddings, embedding):
    if known_embeddings is None:
        return np.array([])

    known = np.asarray(known_embeddings, dtype=np.float32)
    if known.size == 0:
        return np.array([])

    return np.dot(known, np.asarray(embedding, dtype=np.float32))


def iou_batch(bboxes1, bboxes2):
    """
    Computes 1 - IOU between two arrays of bboxes.
    bboxes1: (N, 4)
    bboxes2: (M, 4)
    Returns: (N, M) matrix of distances (1 - IOU).
    """
    if len(bboxes1) == 0 or len(bboxes2) == 0:
        return np.zeros((len(bboxes1), len(bboxes2)))
    
    bboxes2 = np.expand_dims(bboxes2, 0)
    bboxes1 = np.expand_dims(bboxes1, 1)
    
    xx1 = np.maximum(bboxes1[..., 0], bboxes2[..., 0])
    yy1 = np.maximum(bboxes1[..., 1], bboxes2[..., 1])
    xx2 = np.minimum(bboxes1[..., 2], bboxes2[..., 2])
    yy2 = np.minimum(bboxes1[..., 3], bboxes2[..., 3])
    w = np.maximum(0., xx2 - xx1 + 1)
    h = np.maximum(0., yy2 - yy1 + 1)
    wh = w * h
    
    area1 = (bboxes1[..., 2] - bboxes1[..., 0] + 1) * (bboxes1[..., 3] - bboxes1[..., 1] + 1)
    area2 = (bboxes2[..., 2] - bboxes2[..., 0] + 1) * (bboxes2[..., 3] - bboxes2[..., 1] + 1)
    
    iou = wh / (area1 + area2 - wh + 1e-6)
    return 1.0 - iou


def bbox_to_z(bbox):
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    cx = x1 + w / 2.
    cy = y1 + h / 2.
    a = w / h if h > 0 else 0
    return np.array([cx, cy, a, h])


def z_to_bbox(z):
    cx, cy, a, h = z
    w = a * h
    x1 = cx - w / 2.
    y1 = cy - h / 2.
    x2 = cx + w / 2.
    y2 = cy + h / 2.
    return np.array([x1, y1, x2, y2])


@dataclass
class TrackState:
    track_id: int
    bbox: tuple
    mean: np.ndarray = None
    covariance: np.ndarray = None
    embeddings: list = field(default_factory=list)
    guest_embeddings: list = field(default_factory=list)
    resolved_customer_id: str | None = None
    last_seen_frame: int = 0
    first_seen_frame: int = 0
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    state: str = "Tracked"  # "Tracked" or "Lost"


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

        self.kalman_filter = KalmanFilter()

        self.known_embeddings = []
        self.known_ids = []
        self.tracks = {}
        self.next_track_id = 1
        self.frame_index = 0
        self.lock = threading.Lock()
        self._save_lock = threading.Lock()
        self.guest_embeddings = []
        self.guest_ids = []

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
                # Fail silently; caller may log if needed
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
        self._insert_guest_into_main_db_async(guest_id)
        self._persist_known_embeddings_async()
        return guest_id

    def _insert_guest_into_main_db_async(self, guest_id):
        def worker():
            try:
                conn = get_db_connection()
                ensure_schema(conn)
                insert_guest_record(conn, guest_id)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def process_faces(self, face_records):
        self.frame_index += 1
        outputs = []
        now = time.monotonic()

        # Split detections into high-score and low-score
        det_high = []
        det_low = []
        for idx, record in enumerate(face_records):
            score = float(record.get("score", 0.0))
            if score >= 0.5:  # high-score detection threshold
                det_high.append((idx, record))
            else:
                det_low.append((idx, record))

        # Predict Kalman state for all existing tracks
        for track in self.tracks.values():
            track.mean, track.covariance = self.kalman_filter.predict(track.mean, track.covariance)
            pred_bbox = z_to_bbox(track.mean)
            # prevent negative coordinates if heavily outside
            track.bbox = tuple(map(int, pred_bbox))

        # First association: high-score detections with all tracks
        matched_track_ids = set()
        matches_step1 = []
        unmatched_high_dets = []

        track_ids = list(self.tracks.keys())
        if track_ids and det_high:
            track_list = [self.tracks[tid] for tid in track_ids]
            predicted_bboxes = np.array([t.bbox for t in track_list])
            high_bboxes = np.array([tuple(map(int, r["bbox"])) for _, r in det_high])
            
            cost_matrix = iou_batch(predicted_bboxes, high_bboxes)
            row_ind, col_ind = scipy.optimize.linear_sum_assignment(cost_matrix)
            
            for r, c in zip(row_ind, col_ind):
                # cost = 1.0 - IOU. We want IOU >= self.iou_threshold (e.g. 0.3), so cost <= 1.0 - 0.3 = 0.7
                if cost_matrix[r, c] > (1.0 - self.iou_threshold):
                    continue
                tid = track_ids[r]
                det_idx = det_high[c][0]
                matches_step1.append((tid, det_idx))
                matched_track_ids.add(tid)
                
            for c_idx in range(len(det_high)):
                is_matched = False
                for tid, det_idx in matches_step1:
                    if det_idx == det_high[c_idx][0]:
                        is_matched = True
                        break
                if not is_matched:
                    unmatched_high_dets.append(det_high[c_idx])
        else:
            unmatched_high_dets.extend(det_high)

        # Second association: low-score detections with remaining unmatched tracks
        unmatched_tracks_from_step1 = [self.tracks[tid] for tid in track_ids if tid not in matched_track_ids]
        matches_step2 = []
        
        if unmatched_tracks_from_step1 and det_low:
            predicted_bboxes = np.array([t.bbox for t in unmatched_tracks_from_step1])
            low_bboxes = np.array([tuple(map(int, r["bbox"])) for _, r in det_low])
            
            cost_matrix = iou_batch(predicted_bboxes, low_bboxes)
            row_ind, col_ind = scipy.optimize.linear_sum_assignment(cost_matrix)
            
            for r, c in zip(row_ind, col_ind):
                if cost_matrix[r, c] > (1.0 - self.iou_threshold):
                    continue
                track = unmatched_tracks_from_step1[r]
                det_idx = det_low[c][0]
                matches_step2.append((track.track_id, det_idx))
                matched_track_ids.add(track.track_id)

        # Combine matches from both steps
        all_matches = matches_step1 + matches_step2

        # 3. Update matched tracks
        for tid, det_idx in all_matches:
            track = self.tracks[tid]
            record = face_records[det_idx]
            bbox = tuple(map(int, record["bbox"]))
            
            track.bbox = bbox
            track.last_seen_frame = self.frame_index
            track.last_seen_at = now
            track.state = "Tracked"
            
            # Kalman update
            z = bbox_to_z(bbox)
            track.mean, track.covariance = self.kalman_filter.update(track.mean, track.covariance, z)
            record["assigned_track"] = track

        # 4. Create new tracks for unmatched high-score detections
        for record_idx, record in unmatched_high_dets:
            bbox = tuple(map(int, record["bbox"]))
            track_id = self.next_track_id
            self.next_track_id += 1
            
            # Kalman initiate
            z = bbox_to_z(bbox)
            mean, covariance = self.kalman_filter.initiate(z)
            
            new_track = TrackState(
                track_id=track_id,
                bbox=bbox,
                mean=mean,
                covariance=covariance,
                last_seen_frame=self.frame_index,
                first_seen_frame=self.frame_index,
                first_seen_at=now,
                last_seen_at=now,
                state="Tracked",
            )
            self.tracks[track_id] = new_track
            record["assigned_track"] = new_track

        # 5. Mark unmatched tracks as Lost
        for tid in track_ids:
            if tid not in matched_track_ids:
                self.tracks[tid].state = "Lost"

        # 6. Recognition logic and DB check for faces in this frame
        for record in face_records:
            if "assigned_track" not in record:
                continue
            
            track = record["assigned_track"]
            bbox = track.bbox
            quality_ok = bool(record.get("quality_ok", True))
            guest_quality_ok = bool(record.get("guest_quality_ok", False))
            embedding = record.get("embedding")
            existing_customer_id = track.resolved_customer_id

            if existing_customer_id and not str(existing_customer_id).startswith("GUEST_"):
                # Already matched to a registered customer (KHxxx)
                outputs.append(
                    {
                        "track_id": track.track_id,
                        "customer_id": existing_customer_id,
                        "bbox": bbox,
                        "embedding_ready": len(track.embeddings) >= self.buffer_size,
                        "quality_ok": quality_ok,
                    }
                )
                continue

            if quality_ok and embedding is not None:
                norm_emb = normalize_embedding(embedding)
                track.embeddings.append(norm_emb)
                if guest_quality_ok:
                    track.guest_embeddings.append(norm_emb)

            resolved_customer_id = existing_customer_id if existing_customer_id else None
            if len(track.embeddings) >= self.buffer_size:
                avg_embedding = normalize_embedding(np.mean(track.embeddings[-self.buffer_size :], axis=0))

                combined_embeddings = []
                combined_ids = []
                if self.known_embeddings:
                    combined_embeddings.extend(self.known_embeddings)
                    combined_ids.extend(self.known_ids)
                if self.guest_embeddings:
                    combined_embeddings.extend(self.guest_embeddings)
                    combined_ids.extend(self.guest_ids)

                if len(combined_embeddings) > 0:
                    similarities = cosine_similarities(combined_embeddings, avg_embedding)
                    if similarities.size > 0:
                        best_index = int(np.argmax(similarities))
                        if float(similarities[best_index]) >= self.similarity_threshold:
                            if best_index < len(self.known_embeddings):
                                resolved_customer_id = self.known_ids[best_index]
                            else:
                                guest_idx = best_index - len(self.known_embeddings)
                                resolved_customer_id = self.guest_ids[guest_idx]

                if resolved_customer_id is None and len(track.guest_embeddings) >= self.guest_creation_buffer_size:
                    known_similarity = 0.0
                    if self.known_embeddings:
                        known_scores = cosine_similarities(self.known_embeddings, avg_embedding)
                        if known_scores.size > 0:
                            known_similarity = float(np.max(known_scores))

                    track_age_seconds = now - track.first_seen_at
                    if track_age_seconds < NEW_GUEST_DEBOUNCE_SECONDS:
                        resolved_customer_id = None
                    elif known_similarity >= NEW_GUEST_DEBOUNCE_SIMILARITY:
                        resolved_customer_id = None
                    else:
                        resolved_customer_id = self._register_guest(avg_embedding, track)

                if resolved_customer_id is None and not str(existing_customer_id).startswith("GUEST_"):
                    resolved_customer_id = None
                elif not str(resolved_customer_id).startswith("GUEST_"):
                    track.resolved_customer_id = resolved_customer_id
                else:
                    track.resolved_customer_id = resolved_customer_id

            outputs.append(
                {
                    "track_id": track.track_id,
                    "customer_id": resolved_customer_id,
                    "bbox": bbox,
                    "embedding_ready": len(track.embeddings) >= self.buffer_size,
                    "quality_ok": quality_ok,
                    "pending_guest": resolved_customer_id is None and len(track.guest_embeddings) < self.guest_creation_buffer_size,
                }
            )

        # 7. Drop stale tracks after 30 frames
        stale_cutoff = self.frame_index - 30
        self.tracks = {
            tid: trk for tid, trk in self.tracks.items()
            if trk.last_seen_frame >= stale_cutoff
        }

        return outputs
