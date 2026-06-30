import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

from config import (DATA_DIR, PROCESS_EVERY_N_FRAMES, SIMILARITY_THRESHOLD,
                    MIN_FACE_BBOX_SIZE, MIN_DETECTION_SCORE, TRACK_BUFFER_SIZE, TRACK_IOU_THRESHOLD,
                    GUEST_CREATION_BUFFER_SIZE, GUEST_MIN_DETECTION_SCORE, GUEST_MIN_FACE_BBOX_SIZE,
                    NEW_GUEST_DEBOUNCE_SECONDS, NEW_GUEST_DEBOUNCE_SIMILARITY,
                    CHECKIN_COOLDOWN_SECONDS, CUSTOMER_PROFILE_HOLD_SECONDS)

SETTINGS_FILE = DATA_DIR / "settings.json"
_settings_lock = threading.Lock()

# Default fallback settings mapping
DEFAULT_SETTINGS = {
    "process_every_n_frames": PROCESS_EVERY_N_FRAMES,
    "similarity_threshold": SIMILARITY_THRESHOLD,
    "min_face_bbox_size": MIN_FACE_BBOX_SIZE,
    "min_detection_score": MIN_DETECTION_SCORE,
    "track_buffer_size": TRACK_BUFFER_SIZE,
    "track_iou_threshold": TRACK_IOU_THRESHOLD,
    
    "guest_creation_buffer_size": GUEST_CREATION_BUFFER_SIZE,
    "guest_min_detection_score": GUEST_MIN_DETECTION_SCORE,
    "guest_min_face_bbox_size": GUEST_MIN_FACE_BBOX_SIZE,
    "new_guest_debounce_seconds": NEW_GUEST_DEBOUNCE_SECONDS,
    "new_guest_debounce_similarity": NEW_GUEST_DEBOUNCE_SIMILARITY,
    
    "checkin_cooldown_seconds": CHECKIN_COOLDOWN_SECONDS,
    "customer_profile_hold_seconds": CUSTOMER_PROFILE_HOLD_SECONDS,
}

class SettingsManager:
    def __init__(self):
        self.settings: Dict[str, Any] = {}
        self.load_settings()

    def load_settings(self) -> None:
        with _settings_lock:
            if SETTINGS_FILE.exists():
                try:
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # Merge with defaults to ensure all keys exist
                        self.settings = {**DEFAULT_SETTINGS, **data}
                except Exception as e:
                    print(f"Error loading settings from {SETTINGS_FILE}: {e}")
                    self.settings = DEFAULT_SETTINGS.copy()
            else:
                self.settings = DEFAULT_SETTINGS.copy()
                self._save_settings_unlocked()

    def _save_settings_unlocked(self) -> None:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving settings to {SETTINGS_FILE}: {e}")

    def get_all(self) -> Dict[str, Any]:
        with _settings_lock:
            return self.settings.copy()

    def get(self, key: str, default: Any = None) -> Any:
        with _settings_lock:
            return self.settings.get(key, default)

    def update(self, updates: Dict[str, Any]) -> None:
        with _settings_lock:
            for key, value in updates.items():
                if key in DEFAULT_SETTINGS:
                    self.settings[key] = value
            self._save_settings_unlocked()

# Global instance
system_settings = SettingsManager()
