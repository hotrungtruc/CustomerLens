from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
ENCODINGS_DIR = DATA_DIR / "encodings"
ENCODE_FILE = ENCODINGS_DIR / "EncodeFile.p"
GUEST_CACHE_FILE = ENCODINGS_DIR / "GuestCache.p"
DB_PATH = DATA_DIR / "face_attendance.db"
MODELS_DIR = BASE_DIR / "models"
DETECTOR_PATH = MODELS_DIR / "det_500m.onnx"
RECOGNIZER_FLOAT_PATH = MODELS_DIR / "w600k_mbf.onnx"
RECOGNIZER_PATH = MODELS_DIR / "mobilefacenet_int8.onnx"
FACE_LANDMARKER_TASK = MODELS_DIR / "face_landmarker.task"
MEDIAPIPE_FACE_MESH_MODEL_SELECTION = 0

SIMILARITY_THRESHOLD = 0.25
MIN_FACE_BBOX_SIZE = 75
MIN_DETECTION_SCORE = 0.75
TRACK_BUFFER_SIZE = 3
GUEST_CREATION_BUFFER_SIZE = 10
TRACK_IOU_THRESHOLD = 0.3
PROCESS_EVERY_N_FRAMES = 3
CHECKIN_COOLDOWN_SECONDS = 30
CUSTOMER_PROFILE_HOLD_SECONDS = 2.5
NEW_GUEST_DEBOUNCE_SECONDS = 7
NEW_GUEST_DEBOUNCE_SIMILARITY = 0.55
DEBUG_SHOW_SIMILARITY = False

CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 360
FRAME_JPEG_QUALITY = 80
IMAGE_JPEG_QUALITY = 85

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://face-recognition-system-coral.vercel.app",
    "https://face-recognition-system-f7s4lqogv-justin-ho-s-projects.vercel.app",
]


def ensure_data_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ENCODINGS_DIR.mkdir(parents=True, exist_ok=True)
