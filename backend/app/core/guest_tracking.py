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

EMA_ALPHA = 0.8  # Exponential Moving Average factor for embeddings


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


def iou_batch(bboxes1, bboxes2):
    """
    Computes 1 - IOU between two arrays of bboxes.
    bboxes1: (N, 4)
    bboxes2: (M, 4)
    Returns: (N, M) matrix of distances (1 - IOU).
    """
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
    embedding: np.ndarray = None  # Replaced buffer with EMA single embedding
    guest_embedding: np.ndarray = None
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
        buffer_size=1,  # Redundant now, kept for signature compatibility
        guest_creation_buffer_size=1,  # Can create guest on first good frame
        similarity_threshold=0.38,
        iou_threshold=0.7,  # Distance threshold for assignment (1 - 0.3)
        min_bbox_size=100,
        min_detection_score=0.85,
        guest_prefix="GUEST",
    ):
        self.encode_file = Path(encode_file)
        self.guest_cache_file = Path(guest_cache_file) if guest_cache_file else None
        self.buffer_size = buffer_size
        self.guest_creation_buffer_size = guest_creation_buffer_size
        self.similarity_threshold = similarity_threshold
        # Distance threshold for assignment (cost is 1 - IOU). So we want cost <= (1.0 - iou_threshold)
        self.iou_cost_threshold = 1.0 - iou_threshold
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
                with open(self.guest_cache_file, "gf") as gf:
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
        with self._save_lock:
            try:
                self.encode_file.parent.mkdir(parents=True, exist_ok=True)
                payload = [self.known_embeddings, self.known_ids]
                with open(self.encode_file, "wb") as f:
                    pickle.dump(payload, f)
            except Exception:
                pass

    def promote_guest(self, guest_id: str, new_id: str) -> bool:
        with self.lock:
            try:
                if guest_id not in self.guest_ids:
                    return False
                idx = int(self.guest_ids.index(guest_id))
                emb = self.guest_embeddings.pop(idx)
                self.guest_ids.pop(idx)

                self.known_embeddings.append(emb)
                self.known_ids.append(new_id)

                self.persist_known_embeddings()
                self._persist_known_embeddings_async()
                return True
            except Exception:
                return False

    def _create_guest_id(self):
        return f"{self.guest_prefix}_{self.frame_index}_{self.next_track_id:04d}"

    def _match_tracks(self, bboxes):
        """
        ByteTrack-style matching using Kalman filter and Hungarian algorithm.
        Returns: [(track_id, bbox_idx), ...], [unmatched_bbox_idx, ...], [unmatched_track_id, ...]
        """
        track_ids = list(self.tracks.keys())
        
        # Predict all tracks
        for tid in track_ids:
            track = self.tracks[tid]
            if track.state != "Removed":
                track.mean, track.covariance = self.kalman_filter.predict(track.mean, track.covariance)
                # Update bbox based on prediction
                pred_bbox = z_to_bbox(track.mean)
                # prevent negative coordinates if heavily outside
                track.bbox = tuple(pred_bbox)

        if len(track_ids) == 0 or len(bboxes) == 0:
            return [], list(range(len(bboxes))), track_ids

        predicted_bboxes = np.array([self.tracks[tid].bbox for tid in track_ids])
        cost_matrix = iou_batch(predicted_bboxes, np.array(bboxes))

        # Hungarian assignment
        row_ind, col_ind = scipy.optimize.linear_sum_assignment(cost_matrix)

        matches = []
        unmatched_bboxes = set(range(len(bboxes)))
        unmatched_tracks = set(track_ids)

        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] > self.iou_cost_threshold:
                continue
            matches.append((track_ids[r], c))
            unmatched_bboxes.discard(c)
            unmatched_tracks.discard(track_ids[r])

        return matches, list(unmatched_bboxes), list(unmatched_tracks)

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

        bboxes = [tuple(map(int, record["bbox"])) for record in face_records]
        
        matches, unmatched_bboxes, unmatched_tracks = self._match_tracks(bboxes)

        # 1. Update matched tracks
        for track_id, bbox_idx in matches:
            track_state = self.tracks[track_id]
            bbox = bboxes[bbox_idx]
            track_state.bbox = bbox
            track_state.last_seen_frame = self.frame_index
            track_state.last_seen_at = now
            track_state.update_count += 1
            track_state.state = "Tracked"
            
            # Kalman update
            z = bbox_to_z(bbox)
            track_state.mean, track_state.covariance = self.kalman_filter.update(
                track_state.mean, track_state.covariance, z
            )

        # 2. Create new tracks for unmatched detections
        for bbox_idx in unmatched_bboxes:
            bbox = bboxes[bbox_idx]
            track_id = self.next_track_id
            self.next_track_id += 1
            z = bbox_to_z(bbox)
            mean, covariance = self.kalman_filter.initiate(z)
            self.tracks[track_id] = TrackState(
                track_id=track_id,
                bbox=bbox,
                mean=mean,
                covariance=covariance,
                last_seen_frame=self.frame_index,
                first_seen_frame=self.frame_index,
                first_seen_at=now,
                last_seen_at=now,
                update_count=1,
            )
            matches.append((track_id, bbox_idx))

        # 3. Mark unmatched tracks as Lost
        for track_id in unmatched_tracks:
            track = self.tracks[track_id]
            track.state = "Lost"

        # 4. Cleanup stale/lost tracks
        stale_cutoff = self.frame_index - 30
        self.tracks = {
            tid: trk for tid, trk in self.tracks.items()
            if trk.last_seen_frame >= stale_cutoff
        }

        # 5. Process Recognition and EMA for matched faces in this frame
        for track_id, bbox_idx in matches:
            record = face_records[bbox_idx]
            track_state = self.tracks[track_id]
            bbox = track_state.bbox

            quality_ok = bool(record.get("quality_ok", True))
            guest_quality_ok = bool(record.get("guest_quality_ok", False))
            embedding = record.get("embedding")
            existing_customer_id = track_state.resolved_customer_id

            if track_state.update_count > self.buffer_size:
                if existing_customer_id and not str(existing_customer_id).startswith("GUEST_"):
                    # Already matched to a real customer and past buffer, lock it
                    outputs.append({
                        "track_id": track_id,
                        "customer_id": existing_customer_id,
                        "bbox": bbox,
                        "embedding_ready": True,
                        "quality_ok": quality_ok,
                        "pending_guest": False,
                    })
                    continue

            # Update EMA embedding
            if quality_ok and embedding is not None:
                norm_emb = normalize_embedding(embedding)
                if track_state.embedding is None:
                    track_state.embedding = norm_emb
                else:
                    track_state.embedding = normalize_embedding(
                        EMA_ALPHA * track_state.embedding + (1 - EMA_ALPHA) * norm_emb
                    )

                if guest_quality_ok:
                    if track_state.guest_embedding is None:
                        track_state.guest_embedding = norm_emb
                    else:
                        track_state.guest_embedding = normalize_embedding(
                            EMA_ALPHA * track_state.guest_embedding + (1 - EMA_ALPHA) * norm_emb
                        )

            resolved_customer_id = existing_customer_id if existing_customer_id else None
            
            # Instant recognition: Do matching from the first valid frame!
            if track_state.embedding is not None:
                combined_embeddings = []
                combined_ids = []
                if self.known_embeddings:
                    combined_embeddings.extend(self.known_embeddings)
                    combined_ids.extend(self.known_ids)
                if self.guest_embeddings:
                    combined_embeddings.extend(self.guest_embeddings)
                    combined_ids.extend(self.guest_ids)

                if len(combined_embeddings) > 0:
                    similarities = cosine_similarities(combined_embeddings, track_state.embedding)
                    if similarities.size > 0:
                        best_index = int(np.argmax(similarities))
                        if float(similarities[best_index]) >= self.similarity_threshold:
                            if best_index < len(self.known_embeddings):
                                resolved_customer_id = self.known_ids[best_index]
                            else:
                                guest_idx = best_index - len(self.known_embeddings)
                                resolved_customer_id = self.guest_ids[guest_idx]

                # Create Guest if no match
                if resolved_customer_id is None and track_state.guest_embedding is not None:
                    known_similarity = 0.0
                    if self.known_embeddings:
                        known_scores = cosine_similarities(self.known_embeddings, track_state.embedding)
                        if known_scores.size > 0:
                            known_similarity = float(np.max(known_scores))

                    track_age_seconds = now - track_state.first_seen_at
                    if track_age_seconds < NEW_GUEST_DEBOUNCE_SECONDS:
                        resolved_customer_id = None
                    elif known_similarity >= NEW_GUEST_DEBOUNCE_SIMILARITY:
                        resolved_customer_id = None
                    else:
                        resolved_customer_id = self._register_guest(track_state.embedding, track_state)

                if resolved_customer_id is None and not str(existing_customer_id).startswith("GUEST_"):
                    resolved_customer_id = None
                else:
                    track_state.resolved_customer_id = resolved_customer_id

            outputs.append({
                "track_id": track_id,
                "customer_id": resolved_customer_id,
                "bbox": bbox,
                "embedding_ready": track_state.embedding is not None,
                "quality_ok": quality_ok,
                "pending_guest": resolved_customer_id is None and track_state.guest_embedding is None,
            })

        return outputs
