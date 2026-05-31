import threading
import numpy as np


class SharedFrameManager:
    """Simple in-process shared frame buffer for threads.

    This pre-allocates a single numpy array buffer and exposes
    thread-safe write/read operations so producer (camera) and
    consumer (AI) threads don't keep copying/frame-allocating.
    """

    def __init__(self, width: int, height: int, channels: int = 3):
        self.width = width
        self.height = height
        self.channels = channels
        # pre-allocated shared buffer
        self._buffer = np.zeros((height, width, channels), dtype=np.uint8)
        self._lock = threading.Lock()
        self._version = 0
        # annotations small structure written by AI thread and read by streamer
        self._annotations = {"faces": [], "current_customer_id": None, "ts": 0}

    def write_frame(self, frame: np.ndarray):
        """Copy latest frame into shared buffer (thread-safe)."""
        if frame is None:
            return
        # ensure shape matches; if not, resize into buffer
        with self._lock:
            try:
                if frame.shape != self._buffer.shape:
                    # resize source to buffer shape before copy
                    resized = cv2.resize(frame, (self.width, self.height))
                    np.copyto(self._buffer, resized)
                else:
                    np.copyto(self._buffer, frame)
                self._version += 1
            except Exception:
                # fallback: attempt best-effort copy
                self._buffer[:, :, :] = frame[: self.height, : self.width, : self.channels]
                self._version += 1

    def read_frame(self):
        """Return a view of the shared buffer (no copy)."""
        with self._lock:
            return self._buffer

    def get_version(self):
        with self._lock:
            return self._version

    def update_annotations(self, faces, current_customer_id=None):
        with self._lock:
            self._annotations["faces"] = faces
            self._annotations["current_customer_id"] = current_customer_id
            self._annotations["ts"] = time.time()

    def get_annotations(self):
        with self._lock:
            # return a shallow copy (small data)
            return dict(self._annotations)


import time
import cv2
