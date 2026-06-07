import pickle
import threading
import time
from pathlib import Path
import numpy as np

try:
    from filterpy.kalman import KalmanFilter
    from scipy.optimize import linear_sum_assignment
except ImportError:
    import sys
    print("WARNING: filterpy or scipy not installed! Please pip install filterpy scipy", file=sys.stderr)
    KalmanFilter = None
    linear_sum_assignment = None

from app.db.connection import get_db_connection, ensure_schema, insert_guest_record
from config import NEW_GUEST_DEBOUNCE_SECONDS, NEW_GUEST_DEBOUNCE_SIMILARITY


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


def bbox_ious(boxes_a, boxes_b):
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)))

    a_x1, a_y1, a_x2, a_y2 = boxes_a[:, 0:1], boxes_a[:, 1:2], boxes_a[:, 2:3], boxes_a[:, 3:4]
    b_x1, b_y1, b_x2, b_y2 = boxes_b[:, 0], boxes_b[:, 1], boxes_b[:, 2], boxes_b[:, 3]

    inter_x1 = np.maximum(a_x1, b_x1)
    inter_y1 = np.maximum(a_y1, b_y1)
    inter_x2 = np.minimum(a_x2, b_x2)
    inter_y2 = np.minimum(a_y2, b_y2)

    inter_w = np.maximum(0, inter_x2 - inter_x1)
    inter_h = np.maximum(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = (a_x2 - a_x1) * (a_y2 - a_y1)
    area_b = (b_x2 - b_x1) * (b_y2 - b_y1)

    return inter_area / (area_a + area_b - inter_area + 1e-6)


def linear_assignment(cost_matrix, thresh):
    if cost_matrix.size == 0:
        return np.empty((0, 2), dtype=int), tuple(range(cost_matrix.shape[0])), tuple(range(cost_matrix.shape[1]))
    if linear_sum_assignment is None:
        return np.empty((0, 2), dtype=int), tuple(range(cost_matrix.shape[0])), tuple(range(cost_matrix.shape[1]))
        
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    matches, unmatched_a, unmatched_b = [], [], []
    for r, c in zip(row_ind, col_ind):
        if cost_matrix[r, c] > thresh:
            unmatched_a.append(r)
            unmatched_b.append(c)
        else:
            matches.append([r, c])
    for r in range(cost_matrix.shape[0]):
        if r not in row_ind: unmatched_a.append(r)
    for c in range(cost_matrix.shape[1]):
        if c not in col_ind: unmatched_b.append(c)
    return np.array(matches, dtype=int), np.array(unmatched_a, dtype=int), np.array(unmatched_b, dtype=int)


class STrack:
    if KalmanFilter is not None:
        shared_kalman = KalmanFilter(dim_x=8, dim_z=4)
        shared_kalman.F = np.eye(8)
        for i in range(4): shared_kalman.F[i, i+4] = 1.0
        shared_kalman.H = np.zeros((4, 8))
        for i in range(4): shared_kalman.H[i, i] = 1.0
        shared_kalman.P[4:, 4:] *= 1000.
        shared_kalman.P *= 10.
        shared_kalman.R *= 10.
        shared_kalman.Q[-1, -1] *= 0.01
        shared_kalman.Q[4:, 4:] *= 0.01

    def __init__(self, bbox, track_id, score=1.0):
        self.track_id = track_id
        self.score = score
        if KalmanFilter is not None:
            self.kf = KalmanFilter(dim_x=8, dim_z=4)
            self.kf.F = self.shared_kalman.F.copy()
            self.kf.H = self.shared_kalman.H.copy()
            self.kf.P = self.shared_kalman.P.copy()
            self.kf.R = self.shared_kalman.R.copy()
            self.kf.Q = self.shared_kalman.Q.copy()
            
            x1, y1, x2, y2 = bbox
            w = x2 - x1
            h = max(y2 - y1, 1e-6)
            x = x1 + w / 2
            y = y1 + h / 2
            a = w / h
            self.kf.x[:4] = np.array([x, y, a, h]).reshape(4, 1)
            self.kf.x[4:] = 0.0
            
        self.bbox = bbox
        self.embedding = None
        self.guest_embeddings = [] # buffer for guest creation
        self.resolved_customer_id = None
        now = time.monotonic()
        self.first_seen_at = now
        self.last_seen_at = now
        self.last_seen_frame = 0
        self.is_activated = False

    def predict(self):
        if KalmanFilter is not None:
            self.kf.predict()
            self.bbox = self.get_bbox()

    def update(self, bbox, score):
        self.score = score
        if KalmanFilter is not None:
            x1, y1, x2, y2 = bbox
            w = x2 - x1
            h = max(y2 - y1, 1e-6)
            x = x1 + w / 2
            y = y1 + h / 2
            a = w / h
            z = np.array([x, y, a, h])
            self.kf.update(z)
            self.bbox = self.get_bbox()
        else:
            self.bbox = bbox
        self.last_seen_at = time.monotonic()

    def get_bbox(self):
        if KalmanFilter is None:
            return self.bbox
        x, y, a, h = self.kf.x[:4].flatten()
        w = a * h
        x1 = x - w / 2
        y1 = y - h / 2
        x2 = x + w / 2
        y2 = y + h / 2
        return (x1, y1, x2, y2)

    def update_embedding(self, new_embedding, alpha=0.9):
        norm_emb = normalize_embedding(new_embedding)
        if self.embedding is None:
            self.embedding = norm_emb
        else:
            self.embedding = normalize_embedding(alpha * self.embedding + (1 - alpha) * norm_emb)


class GuestTrackManager:
    def __init__(
        self,
        encode_file,
        guest_cache_file=None,
        guest_creation_buffer_size=8,
        similarity_threshold=0.38,
        iou_threshold=0.3,
        guest_prefix="GUEST",
    ):
        self.encode_file = Path(encode_file)
        self.guest_cache_file = Path(guest_cache_file) if guest_cache_file else None
        self.guest_creation_buffer_size = guest_creation_buffer_size
        self.similarity_threshold = similarity_threshold
        self.iou_threshold = iou_threshold
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

        det_high = []
        det_low = []
        
        for idx, record in enumerate(face_records):
            score = float(record.get("score", 0.0))
            if score >= 0.5:
                det_high.append((idx, record))
            else:
                det_low.append((idx, record))

        for track in self.tracks.values():
            track.predict()

        matched_track_ids = set()
        unmatched_dets = []

        if det_high and self.tracks:
            track_list = list(self.tracks.values())
            boxes_a = np.array([t.bbox for t in track_list])
            boxes_b = np.array([r["bbox"] for _, r in det_high])
            
            ious = bbox_ious(boxes_a, boxes_b)
            cost_matrix = 1.0 - ious
            
            matches, un_t, un_d = linear_assignment(cost_matrix, thresh=1.0 - self.iou_threshold)
            
            for t_idx, d_idx in matches:
                track = track_list[t_idx]
                record_idx, record = det_high[d_idx]
                track.update(record["bbox"], record["score"])
                track.last_seen_frame = self.frame_index
                matched_track_ids.add(track.track_id)
                record["assigned_track"] = track
                
            for d_idx in un_d:
                unmatched_dets.append(det_high[d_idx])
        else:
            unmatched_dets.extend(det_high)

        unmatched_tracks = [t for t in self.tracks.values() if t.track_id not in matched_track_ids]
        if det_low and unmatched_tracks:
            boxes_a = np.array([t.bbox for t in unmatched_tracks])
            boxes_b = np.array([r["bbox"] for _, r in det_low])
            
            ious = bbox_ious(boxes_a, boxes_b)
            cost_matrix = 1.0 - ious
            
            matches, un_t, un_d = linear_assignment(cost_matrix, thresh=0.5) 
            
            for t_idx, d_idx in matches:
                track = unmatched_tracks[t_idx]
                record_idx, record = det_low[d_idx]
                track.update(record["bbox"], record["score"])
                track.last_seen_frame = self.frame_index
                matched_track_ids.add(track.track_id)
                record["assigned_track"] = track

        for record_idx, record in unmatched_dets:
            track_id = self.next_track_id
            self.next_track_id += 1
            new_track = STrack(record["bbox"], track_id, record["score"])
            new_track.last_seen_frame = self.frame_index
            self.tracks[track_id] = new_track
            record["assigned_track"] = new_track

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
                outputs.append({
                    "track_id": track.track_id,
                    "customer_id": existing_customer_id,
                    "bbox": bbox,
                    "embedding_ready": True,
                    "quality_ok": quality_ok,
                })
                continue
                
            if quality_ok and embedding is not None:
                track.update_embedding(embedding, alpha=0.9)
                track.is_activated = True
                if guest_quality_ok:
                    track.guest_embeddings.append(normalize_embedding(embedding))
                    
            resolved_customer_id = existing_customer_id
            if track.is_activated and track.embedding is not None:
                combined_embeddings = []
                combined_ids = []
                if self.known_embeddings:
                    combined_embeddings.extend(self.known_embeddings)
                    combined_ids.extend(self.known_ids)
                if self.guest_embeddings:
                    combined_embeddings.extend(self.guest_embeddings)
                    combined_ids.extend(self.guest_ids)
                    
                if len(combined_embeddings) > 0:
                    similarities = cosine_similarities(combined_embeddings, track.embedding)
                    if similarities.size > 0:
                        best_index = int(np.argmax(similarities))
                        if float(similarities[best_index]) >= self.similarity_threshold:
                            if best_index < len(self.known_embeddings):
                                resolved_customer_id = self.known_ids[best_index]
                            else:
                                resolved_customer_id = self.guest_ids[best_index - len(self.known_embeddings)]
                                
                if resolved_customer_id is None and len(track.guest_embeddings) >= self.guest_creation_buffer_size:
                    known_similarity = 0.0
                    if self.known_embeddings:
                        known_scores = cosine_similarities(self.known_embeddings, track.embedding)
                        if known_scores.size > 0:
                            known_similarity = float(np.max(known_scores))
                            
                    track_age_seconds = now - track.first_seen_at
                    if track_age_seconds >= NEW_GUEST_DEBOUNCE_SECONDS and known_similarity < NEW_GUEST_DEBOUNCE_SIMILARITY:
                        resolved_customer_id = self._register_guest(track.embedding, track)

                if resolved_customer_id and not str(resolved_customer_id).startswith("GUEST_"):
                    track.resolved_customer_id = resolved_customer_id
                else:
                    track.resolved_customer_id = resolved_customer_id
                    
            outputs.append({
                "track_id": track.track_id,
                "customer_id": resolved_customer_id,
                "bbox": bbox,
                "embedding_ready": track.is_activated,
                "quality_ok": quality_ok,
                "pending_guest": resolved_customer_id is None and len(track.guest_embeddings) < self.guest_creation_buffer_size,
            })
            
        stale_cutoff = self.frame_index - 30
        self.tracks = {k: v for k, v in self.tracks.items() if v.last_seen_frame >= stale_cutoff}
        
        return outputs
