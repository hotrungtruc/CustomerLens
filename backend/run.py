import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import create_app
from app.api.routes import init_models
from config import ENCODE_FILE, IMAGES_DIR, MODELS_DIR, DB_PATH, ensure_data_dirs


def main():
    ensure_data_dirs()

    app = create_app()

    print(f"[INFO] Models dir: {MODELS_DIR}")
    print(f"[INFO] Encodings file: {ENCODE_FILE}")
    print(f"[INFO] Images dir: {IMAGES_DIR}")
    print(f"[INFO] Database: {DB_PATH}")

    init_models()

    host = "127.0.0.1"
    port = 5000

    print(f"[INFO] Starting Flask app on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
