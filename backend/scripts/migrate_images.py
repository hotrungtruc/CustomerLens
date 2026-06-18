"""
migrate_images.py — One-time migration to upload local customer images
to Supabase Storage.

Usage:
    cd backend
    ..\.venv\Scripts\python.exe scripts/migrate_images.py

Requires environment variables in .env:
    SUPABASE_PROJECT_URL=https://your-project.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import IMAGES_DIR
from app.db.supabase_storage import upload_local_images, STORAGE_ENABLED

def main():
    if not STORAGE_ENABLED:
        print("ERROR: Supabase Storage is not configured.")
        print("Add these to your .env file:")
        print("  SUPABASE_PROJECT_URL=https://your-project.supabase.co")
        print("  SUPABASE_SERVICE_ROLE_KEY=your-service-role-key")
        sys.exit(1)

    print(f"=== MIGRATE IMAGES TO SUPABASE STORAGE ===")
    print(f"Source: {IMAGES_DIR}")

    if not IMAGES_DIR.exists():
        print(f"ERROR: Images directory not found: {IMAGES_DIR}")
        sys.exit(1)

    images = list(IMAGES_DIR.glob("*.[jJ][pP][gG]")) + list(IMAGES_DIR.glob("*.[pP][nN][gG]"))
    print(f"Found {len(images)} images to upload.")

    upload_local_images(IMAGES_DIR)

    print("=== MIGRATION COMPLETE ===")


if __name__ == "__main__":
    main()
