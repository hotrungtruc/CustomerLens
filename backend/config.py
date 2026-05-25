from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
ENCODINGS_DIR = DATA_DIR / "encodings"
ENCODE_FILE = ENCODINGS_DIR / "EncodeFile.p"
DB_PATH = DATA_DIR / "face_attendance.db"
MODELS_DIR = BASE_DIR / "models"
DETECTOR_PATH = MODELS_DIR / "det_500m.onnx"
RECOGNIZER_PATH = MODELS_DIR / "w600k_mbf.onnx"

SIMILARITY_THRESHOLD = 0.38
PROCESS_EVERY_N_FRAMES = 3
CHECKIN_COOLDOWN_SECONDS = 30

CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FRAME_JPEG_QUALITY = 80
IMAGE_JPEG_QUALITY = 85

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def ensure_data_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ENCODINGS_DIR.mkdir(parents=True, exist_ok=True)
