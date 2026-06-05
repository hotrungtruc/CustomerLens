import pickle
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

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

    def _match_track(self, bbox):
        now = time.monotonic()
        best_track_id = None
        best_iou = 0.0
        for track_id, track in self.tracks.items():
            iou = bbox_iou(track.bbox, bbox)
            if iou > best_iou:
                best_iou = iou
                best_track_id = track_id

        if best_track_id is not None and best_iou >= self.iou_threshold:
            return best_track_id

        track_id = self.next_track_id
        self.next_track_id += 1
        self.tracks[track_id] = TrackState(
            track_id=track_id,
            bbox=bbox,
            last_seen_frame=self.frame_index,
            first_seen_frame=self.frame_index,
            first_seen_at=now,
            last_seen_at=now,
        )
        return track_id

    def _assign_track(self, bbox):
        return self._match_track(tuple(map(int, bbox)))

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

        for record in face_records:
            now = time.monotonic()
            bbox = tuple(map(int, record["bbox"]))
            track_id = self._assign_track(bbox)
            track_state = self.tracks[track_id]
            track_state.bbox = bbox
            track_state.last_seen_frame = self.frame_index
            track_state.last_seen_at = now

            quality_ok = bool(record.get("quality_ok", True))
            guest_quality_ok = bool(record.get("guest_quality_ok", False))
            embedding = record.get("embedding")
            existing_customer_id = track_state.resolved_customer_id

            if existing_customer_id and not str(existing_customer_id).startswith("GUEST_"):
                outputs.append(
                    {
                        "track_id": track_id,
                        "customer_id": existing_customer_id,
                        "bbox": bbox,
                        "embedding_ready": False,
                        "quality_ok": quality_ok,
                    }
                )
                continue

            if quality_ok and embedding is not None:
                norm_emb = normalize_embedding(embedding)
                track_state.embeddings.append(norm_emb)
                if guest_quality_ok:
                    track_state.guest_embeddings.append(norm_emb)

            resolved_customer_id = existing_customer_id if existing_customer_id else None
            if len(track_state.embeddings) >= self.buffer_size:
                avg_embedding = normalize_embedding(np.mean(track_state.embeddings[-self.buffer_size :], axis=0))

                # Combine known + guest embeddings for matching to avoid creating duplicate guest IDs
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
                            # decide if best match is from known set or guest set
                            if best_index < len(self.known_embeddings):
                                resolved_customer_id = self.known_ids[best_index]
                            else:
                                guest_idx = best_index - len(self.known_embeddings)
                                resolved_customer_id = self.guest_ids[guest_idx]

                if resolved_customer_id is None and len(track_state.guest_embeddings) >= self.guest_creation_buffer_size:
                    known_similarity = 0.0
                    avg_guest_embedding = normalize_embedding(np.mean(track_state.guest_embeddings[-self.guest_creation_buffer_size:], axis=0))
                    
                    if self.known_embeddings:
                        known_scores = cosine_similarities(self.known_embeddings, avg_guest_embedding)
                        if known_scores.size > 0:
                            known_similarity = float(np.max(known_scores))

                    track_age_seconds = now - track_state.first_seen_at
                    if track_age_seconds < NEW_GUEST_DEBOUNCE_SECONDS:
                        resolved_customer_id = None
                    elif known_similarity >= NEW_GUEST_DEBOUNCE_SIMILARITY:
                        resolved_customer_id = None
                    else:
                        resolved_customer_id = self._register_guest(avg_guest_embedding, track_state)

                if resolved_customer_id is None and not str(existing_customer_id).startswith("GUEST_"):
                    # Keep waiting for more evidence instead of minting a guest too early.
                    resolved_customer_id = None
                elif not str(resolved_customer_id).startswith("GUEST_"):
                    track_state.resolved_customer_id = resolved_customer_id
                else:
                    track_state.resolved_customer_id = resolved_customer_id

            outputs.append(
                {
                    "track_id": track_id,
                    "customer_id": resolved_customer_id,
                    "bbox": bbox,
                    "embedding_ready": len(track_state.embeddings) >= self.buffer_size,
                    "quality_ok": quality_ok,
                    "pending_guest": resolved_customer_id is None and len(track_state.guest_embeddings) < self.guest_creation_buffer_size,
                }
            )

        # Drop stale tracks after a short gap so IDs do not accumulate forever.
        stale_cutoff = self.frame_index - 30
        self.tracks = {
            track_id: track
            for track_id, track in self.tracks.items()
            if track.last_seen_frame >= stale_cutoff
        }

        return outputs
