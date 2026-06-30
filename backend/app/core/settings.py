import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

from config import DATA_DIR, PROCESS_EVERY_N_FRAMES, SIMILARITY_THRESHOLD

SETTINGS_FILE = DATA_DIR / "settings.json"
_settings_lock = threading.Lock()

# Default fallback settings mapping
DEFAULT_SETTINGS = {
    "camera_resolution": "1080p",
    "process_every_n_frames": PROCESS_EVERY_N_FRAMES,
    "video_storage_days": 30,
    "motion_detection": True,
    
    "similarity_threshold": SIMILARITY_THRESHOLD,
    "detection_mode": "Nhanh",
    "auto_update_template": True,
    "unknown_face_alert": True,
    
    "vip_notification": True,
    "email_alert": False,
    "sound_alert": True,
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
