import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (.env file)
load_dotenv()

# Hardware & Multithreading Optimization
TOTAL_CPU_CORES = os.cpu_count() or 2
ONNX_INTRA_OP_NUM_THREADS = max(
    1,
    int(
        os.getenv("ONNX_INTRA_OP_NUM_THREADS")
        or os.getenv("OMP_NUM_THREADS")
        or TOTAL_CPU_CORES
    ),
)
ONNX_INTER_OP_NUM_THREADS = max(
    1,
    int(os.getenv("ONNX_INTER_OP_NUM_THREADS", "1")),
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
ENCODINGS_DIR = DATA_DIR / "encodings"
ENCODE_FILE = ENCODINGS_DIR / "EncodeFile.p"
GUEST_CACHE_FILE = ENCODINGS_DIR / "GuestCache.p"

# Database Configuration
# Delegated to db_config to ensure single source of truth whether running on SQLite or PostgreSQL/Supabase
from db_config import DATABASE_URL, DB_TYPE, USE_SUPABASE

DB_PATH = DATA_DIR / "face_attendance.db"  # Legacy
DATABASE_DIR = DATA_DIR / "database"
PRODUCTION_DB_PATH = DATABASE_DIR / "production.db"
BACKUP_DIR = DATABASE_DIR / "backups"

MODELS_DIR = BASE_DIR / "models"
EDGEFACE_INT8_PATH = MODELS_DIR / "edgeface_int8.onnx"
EDGEFACE_PATH = MODELS_DIR / "edgeface_s_gamma_05.onnx"
GHOSTFACE_PATH = MODELS_DIR / "ghostface_int8.onnx"
ADAFACE_PATH = MODELS_DIR / "adaface_ir18.onnx"

# Configure default face recognizer model (prioritizing EdgeFace int8)
RECOGNIZER_MODEL = os.getenv("RECOGNIZER_MODEL", "edgeface").lower()
if RECOGNIZER_MODEL == "edgeface":
    if EDGEFACE_INT8_PATH.exists():
        RECOGNIZER_PATH = EDGEFACE_INT8_PATH
        RECOGNIZER_FLOAT_PATH = EDGEFACE_PATH
    elif EDGEFACE_PATH.exists():
        RECOGNIZER_PATH = EDGEFACE_PATH
        RECOGNIZER_FLOAT_PATH = EDGEFACE_PATH
    else:
        RECOGNIZER_PATH = ADAFACE_PATH
        RECOGNIZER_FLOAT_PATH = ADAFACE_PATH
elif RECOGNIZER_MODEL == "adaface" and ADAFACE_PATH.exists():
    RECOGNIZER_PATH = ADAFACE_PATH
    RECOGNIZER_FLOAT_PATH = ADAFACE_PATH
elif RECOGNIZER_MODEL == "ghostface" and GHOSTFACE_PATH.exists():
    RECOGNIZER_PATH = GHOSTFACE_PATH
    RECOGNIZER_FLOAT_PATH = MODELS_DIR / "ghostface_fp32.onnx" if (MODELS_DIR / "ghostface_fp32.onnx").exists() else GHOSTFACE_PATH
elif EDGEFACE_INT8_PATH.exists():
    RECOGNIZER_PATH = EDGEFACE_INT8_PATH
    RECOGNIZER_FLOAT_PATH = EDGEFACE_PATH
elif EDGEFACE_PATH.exists():
    RECOGNIZER_PATH = EDGEFACE_PATH
    RECOGNIZER_FLOAT_PATH = EDGEFACE_PATH
elif GHOSTFACE_PATH.exists():
    RECOGNIZER_PATH = GHOSTFACE_PATH
    RECOGNIZER_FLOAT_PATH = MODELS_DIR / "ghostface_fp32.onnx" if (MODELS_DIR / "ghostface_fp32.onnx").exists() else GHOSTFACE_PATH
else:
    RECOGNIZER_PATH = ADAFACE_PATH
    RECOGNIZER_FLOAT_PATH = ADAFACE_PATH

FACE_LANDMARKER_TASK = MODELS_DIR / "face_landmarker.task"
MEDIAPIPE_FACE_MESH_MODEL_SELECTION = 0 # "0" for detection less than 2 meter; "1" for detection less than 5 meter

SIMILARITY_THRESHOLD = 0.322
MIN_FACE_BBOX_SIZE = 64
MIN_DETECTION_SCORE = 0.65
MIN_BLUR_SCORE = 150.0
MAX_POSE_YAW_ANGLE = 15.0
TRACK_BUFFER_SIZE = 3           # Giảm từ 5 → 3 để bắt đầu voting sớm hơn
GUEST_CREATION_BUFFER_SIZE = 6  # Giảm từ 10 → 6 để tạo guest mới nhanh hơn
TRACK_IOU_THRESHOLD = 0.3
PROCESS_EVERY_N_FRAMES = 1

# Early Decision Thresholds — Cơ chế voting nhanh, tuyệt đối không hạ threshold
# Nếu 1 frame có similarity >= HIGH_CONF: resolve ngay (không cần voting)
RECOGNITION_HIGH_CONF_THRESHOLD = 0.72
# Nếu 2/3 votes đồng thuận tại >= MED_CONF: resolve sớm
RECOGNITION_MED_CONF_THRESHOLD = 0.60
CHECKIN_COOLDOWN_SECONDS = 30
CUSTOMER_PROFILE_HOLD_SECONDS = 2.5

# GUEST CREATION STRICT MODE SETTINGS
GUEST_MIN_DETECTION_SCORE = 0.70
GUEST_MIN_FACE_BBOX_SIZE = 40
NEW_GUEST_DEBOUNCE_SECONDS = 4
NEW_GUEST_DEBOUNCE_SIMILARITY = 0.40
DEBUG_SHOW_SIMILARITY = False

# Camera Configuration
# Note: On many laptops, indices are reversed:
# 0 = Rear/external camera
# 1 = Front camera (built-in laptop camera)
# Try both if needed
CAMERA_INDEX = 1  # Front camera (Laptop built-in) 
FRAME_WIDTH = 640
FRAME_HEIGHT = 360
FRAME_JPEG_QUALITY = 80
IMAGE_JPEG_QUALITY = 85

# Messaging & Event Streaming Configuration (Kafka / Redpanda & Redis)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
KAFKA_CAMERA_FRAMES_TOPIC = os.getenv("KAFKA_CAMERA_FRAMES_TOPIC", "camera_frames")
REDIS_CAMERA_FRAMES_FALLBACK_QUEUE = os.getenv("REDIS_CAMERA_FRAMES_FALLBACK_QUEUE", "camera_frames_fallback")

# CORS & Allowed Origins Configuration
# Read from env if provided (comma-separated), otherwise use comprehensive defaults
_DEFAULT_ORIGINS = [
    "https://checkinface.me",
    "https://www.checkinface.me",
    "https://face-recognition-system-coral.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

_env_origins = os.getenv("CORS_ORIGINS") or os.getenv("ALLOWED_ORIGINS")
if _env_origins:
    CORS_ORIGINS = [origin.strip() for origin in _env_origins.split(",") if origin.strip()]
else:
    CORS_ORIGINS = _DEFAULT_ORIGINS

ALLOWED_ORIGINS = CORS_ORIGINS


def ensure_data_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ENCODINGS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


ensure_data_dirs()

# JWT Configuration (Asymmetric RS256)
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

JWT_ALGORITHM = "RS256"
JWT_EXPIRATION_MINUTES = 60 * 24  # 24 hours

KEYS_DIR = DATA_DIR / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "jwt_private_key.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "jwt_public_key.pem"


def get_jwt_keys():
    """Load or generate RSA keypair for JWT RS256 signing and verification."""
    env_private = os.getenv("JWT_PRIVATE_KEY_PEM")
    env_public = os.getenv("JWT_PUBLIC_KEY_PEM")

    if env_private and env_public:
        return env_private.encode("utf-8"), env_public.encode("utf-8")

    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        private_bytes = PRIVATE_KEY_PATH.read_bytes()
        public_bytes = PUBLIC_KEY_PATH.read_bytes()
        return private_bytes, public_bytes

    # Auto-generate RSA 2048-bit keypair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    try:
        PRIVATE_KEY_PATH.write_bytes(private_bytes)
        PUBLIC_KEY_PATH.write_bytes(public_bytes)
    except Exception:
        pass

    return private_bytes, public_bytes


JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = get_jwt_keys()

# Biometric Privacy & Security Configuration (GDPR / BIPA Compliance)
GUEST_RETENTION_DAYS = 30
BIOMETRIC_STORAGE_KEY_PATH = KEYS_DIR / "biometric_storage.key"
BIOMETRIC_PROJECTION_MATRIX_PATH = KEYS_DIR / "biometric_projection.npy"

