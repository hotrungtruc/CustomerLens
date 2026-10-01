"""
edge_config.py — Configuration parameters for Edge Device AI Pipeline.
"""

import os
from pathlib import Path

# Paths
EDGE_ROOT = Path(__file__).resolve().parent
MODELS_DIR = EDGE_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Fallback: if models aren't in edge/models, look in backend/models
BACKEND_MODELS_DIR = EDGE_ROOT.parent / "backend" / "models"

SCRFD_MODEL_NAME = "scrfd_500m_bnkps.onnx"
EDGEFACE_MODEL_NAME = "edgeface_s_gamma_05.onnx"

def get_model_path(filename: str) -> Path:
    local_path = MODELS_DIR / filename
    if local_path.exists():
        return local_path
    backend_path = BACKEND_MODELS_DIR / filename
    if backend_path.exists():
        return backend_path
    return local_path

SCRFD_MODEL_PATH = get_model_path(SCRFD_MODEL_NAME)
EDGEFACE_MODEL_PATH = get_model_path(EDGEFACE_MODEL_NAME)

# Cloud Connection
DEFAULT_CLOUD_URL = os.getenv("CLOUD_URL", "http://localhost:8000")
DEFAULT_CAMERA_ID = os.getenv("CAMERA_ID", "CAM_EDGE_01")
DEFAULT_DEVICE_ID = os.getenv("DEVICE_ID", "edge_box_01")
DEVICE_AUTH_TOKEN = os.getenv("DEVICE_AUTH_TOKEN", "edge_secret_token")

# Quality & Detection Gates
DET_THRESHOLD = float(os.getenv("DET_THRESHOLD", "0.5"))
NMS_THRESHOLD = float(os.getenv("NMS_THRESHOLD", "0.4"))
MIN_FACE_SIZE = int(os.getenv("MIN_FACE_SIZE", "60"))        # Minimum width/height in pixels
MIN_BLUR_VAR = float(os.getenv("MIN_BLUR_VAR", "100.0"))     # Laplacian variance threshold
MIN_POSE_RATIO = float(os.getenv("MIN_POSE_RATIO", "0.26"))  # Eye distance / bbox width

# Tracking & Smart Event Dispatching
IOU_THRESHOLD = 0.35
MAX_LOST_FRAMES = 15
FIRST_SHOT_QUALITY_THRESHOLD = 0.50
BEST_SHOT_DELTA = 0.15           # Must be this much better to trigger an update
SEND_THUMBNAIL = True            # Send 112x112 JPEG thumbnail for audit log
THUMBNAIL_JPEG_QUALITY = 80

# Telemetry
HEARTBEAT_INTERVAL = 10.0        # Seconds between heartbeats
OFFLINE_QUEUE_MAX = 500          # Max events kept in memory while offline
