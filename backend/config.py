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
GHOSTFACE_PATH = MODELS_DIR / "ghostface_int8.onnx"
EDGEFACE_PATH = MODELS_DIR / "edgeface_s_gamma_05.onnx"
ADAFACE_PATH = MODELS_DIR / "adaface_ir18.onnx"
RECOGNIZER_PATH = GHOSTFACE_PATH if GHOSTFACE_PATH.exists() else (ADAFACE_PATH if ADAFACE_PATH.exists() else EDGEFACE_PATH)
RECOGNIZER_FLOAT_PATH = MODELS_DIR / "ghostface_fp32.onnx" if (MODELS_DIR / "ghostface_fp32.onnx").exists() else GHOSTFACE_PATH
FACE_LANDMARKER_TASK = MODELS_DIR / "face_landmarker.task"
MEDIAPIPE_FACE_MESH_MODEL_SELECTION = 0 # "0" for detection less than 2 meter; "1" for detection less than 5 meter

SIMILARITY_THRESHOLD = 0.322
MIN_FACE_BBOX_SIZE = 64
MIN_DETECTION_SCORE = 0.65
MIN_BLUR_SCORE = 150.0
MAX_POSE_YAW_ANGLE = 15.0
TRACK_BUFFER_SIZE = 5
GUEST_CREATION_BUFFER_SIZE = 10
TRACK_IOU_THRESHOLD = 0.3
PROCESS_EVERY_N_FRAMES = 1
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

