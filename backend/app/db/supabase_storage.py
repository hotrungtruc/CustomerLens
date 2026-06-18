"""
supabase_storage.py — Supabase Storage integration for customer images.

Provides upload, download (public URL), and delete operations for customer
profile images stored in a Supabase Storage bucket named 'customer-images'.

Requires environment variables:
    SUPABASE_PROJECT_URL  — e.g. https://qgwpntwmxpwffccptotj.supabase.co
    SUPABASE_SERVICE_ROLE_KEY — from Supabase Dashboard → Settings → API
"""

import os
import requests
from pathlib import Path

from db_config import USE_SUPABASE
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Supabase REST API credentials
SUPABASE_PROJECT_URL = os.getenv("SUPABASE_PROJECT_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

BUCKET_NAME = "customer-images"

# Check if storage is configured
STORAGE_ENABLED = bool(USE_SUPABASE and SUPABASE_PROJECT_URL and SUPABASE_SERVICE_ROLE_KEY)

if STORAGE_ENABLED:
    logger.info("Supabase Storage enabled (bucket: %s)", BUCKET_NAME)
else:
    logger.info("Supabase Storage disabled — using local filesystem for images")


def _headers():
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }


def _storage_url(path: str = "") -> str:
    return f"{SUPABASE_PROJECT_URL}/storage/v1{path}"


def ensure_bucket():
    """Create the customer-images bucket if it doesn't exist (public read)."""
    if not STORAGE_ENABLED:
        return

    # Check if bucket exists
    resp = requests.get(_storage_url("/bucket"), headers=_headers(), timeout=10)
    if resp.status_code == 200:
        buckets = resp.json()
        if any(b.get("name") == BUCKET_NAME for b in buckets):
            return  # Already exists

    # Create bucket with public access
    resp = requests.post(
        _storage_url("/bucket"),
        headers={**_headers(), "Content-Type": "application/json"},
        json={"id": BUCKET_NAME, "name": BUCKET_NAME, "public": True},
        timeout=10,
    )
    if resp.status_code in (200, 201):
        logger.info("Created Supabase Storage bucket: %s", BUCKET_NAME)
    else:
        logger.warning("Failed to create bucket %s: %s", BUCKET_NAME, resp.text)


def upload_image(customer_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str | None:
    """Upload an image to Supabase Storage.

    Returns the public URL of the uploaded image, or None on failure.
    """
    if not STORAGE_ENABLED:
        return None

    file_name = f"{customer_id}.jpg"
    resp = requests.post(
        _storage_url(f"/object/{BUCKET_NAME}/{file_name}"),
        headers={
            **_headers(),
            "Content-Type": content_type,
            "x-upsert": "true",  # overwrite if exists
        },
        data=image_bytes,
        timeout=30,
    )

    if resp.status_code in (200, 201):
        public_url = f"{SUPABASE_PROJECT_URL}/storage/v1/object/public/{BUCKET_NAME}/{file_name}"
        logger.info("Uploaded image for customer %s", customer_id)
        return public_url
    else:
        logger.warning("Failed to upload image for %s: %s", customer_id, resp.text)
        return None


def get_public_url(customer_id: str) -> str | None:
    """Return the public URL for a customer's image (does not verify existence)."""
    if not STORAGE_ENABLED:
        return None
    return f"{SUPABASE_PROJECT_URL}/storage/v1/object/public/{BUCKET_NAME}/{customer_id}.jpg"


def delete_image(customer_id: str) -> bool:
    """Delete a customer's image from Supabase Storage."""
    if not STORAGE_ENABLED:
        return False

    file_name = f"{customer_id}.jpg"
    resp = requests.delete(
        _storage_url(f"/object/{BUCKET_NAME}"),
        headers={**_headers(), "Content-Type": "application/json"},
        json={"prefixes": [file_name]},
        timeout=10,
    )
    return resp.status_code in (200, 201)


def upload_local_images(images_dir: Path):
    """Batch upload all local images from a directory to Supabase Storage.

    Meant for one-time migration.
    """
    if not STORAGE_ENABLED:
        logger.error("Cannot upload: Supabase Storage not configured")
        return

    ensure_bucket()

    uploaded = 0
    skipped = 0
    for img_path in images_dir.iterdir():
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue

        customer_id = img_path.stem
        with open(img_path, "rb") as f:
            image_bytes = f.read()

        content_type = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        result = upload_image(customer_id, image_bytes, content_type)
        if result:
            uploaded += 1
        else:
            skipped += 1

    logger.info("Image migration complete: uploaded=%d, skipped=%d", uploaded, skipped)
