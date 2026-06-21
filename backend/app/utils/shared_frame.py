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
        self._lock = threading.Lock()
        self._version = 0
        self._payload = None
        # annotations small structure written by AI thread and read by streamer
        self._annotations = {"faces": [], "current_customer_id": None, "ts": 0}

    def write_payload(self, payload: dict):
        """Thread-safe write for the JSON payload (cropped faces)."""
        with self._lock:
            self._payload = payload
            if payload and "frame_size" in payload:
                self.width = payload["frame_size"].get("width", self.width)
                self.height = payload["frame_size"].get("height", self.height)
            self._version += 1

    def read_payload(self):
        """Return the latest payload dict."""
        with self._lock:
            return self._payload

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
