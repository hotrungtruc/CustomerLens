from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
ENCODINGS_DIR = DATA_DIR / "encodings"
ENCODE_FILE = ENCODINGS_DIR / "EncodeFile.p"
GUEST_CACHE_FILE = ENCODINGS_DIR / "GuestCache.p"

# Database Configuration
DB_PATH = DATA_DIR / "face_attendance.db"  # Legacy
DATABASE_DIR = DATA_DIR / "database"
PRODUCTION_DB_PATH = DATABASE_DIR / "production.db"
BACKUP_DIR = DATABASE_DIR / "backups"
DATABASE_URL = f"sqlite:///{PRODUCTION_DB_PATH}"

MODELS_DIR = BASE_DIR / "models"
ADAFACE_PATH = MODELS_DIR / "adaface_ir50.onnx"
RECOGNIZER_PATH = ADAFACE_PATH if ADAFACE_PATH.exists() else MODELS_DIR / "ghostface_int8.onnx"
RECOGNIZER_FLOAT_PATH = ADAFACE_PATH if ADAFACE_PATH.exists() else MODELS_DIR / "ghostface_fp32.onnx"
FACE_LANDMARKER_TASK = MODELS_DIR / "face_landmarker.task"
MEDIAPIPE_FACE_MESH_MODEL_SELECTION = 0

SIMILARITY_THRESHOLD = 0.50
MIN_FACE_BBOX_SIZE = 50
MIN_DETECTION_SCORE = 0.30
TRACK_BUFFER_SIZE = 2
GUEST_CREATION_BUFFER_SIZE = 10
TRACK_IOU_THRESHOLD = 0.3
PROCESS_EVERY_N_FRAMES = 3
CHECKIN_COOLDOWN_SECONDS = 30
CUSTOMER_PROFILE_HOLD_SECONDS = 2.5

# GUEST CREATION STRICT MODE SETTINGS
GUEST_MIN_DETECTION_SCORE = 0.85
GUEST_MIN_FACE_BBOX_SIZE = 100
NEW_GUEST_DEBOUNCE_SECONDS = 4
NEW_GUEST_DEBOUNCE_SIMILARITY = 0.38
DEBUG_SHOW_SIMILARITY = False

# Camera Configuration
# Note: On many laptops, indices are reversed:
# 0 = Rear/external camera
# 1 = Front camera (built-in laptop camera)
# Try both if needed
CAMERA_INDEX = 1  # ✅ Front camera (Laptop built-in) - UPDATED
FRAME_WIDTH = 640
FRAME_HEIGHT = 360
FRAME_JPEG_QUALITY = 80
IMAGE_JPEG_QUALITY = 85

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "*",  # Allow all origins during development
]


def ensure_data_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ENCODINGS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


ensure_data_dirs()

