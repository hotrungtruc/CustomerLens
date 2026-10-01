"""
enroll_customer.py — Enroll customer faces using SCRFD-500M + EdgeFace γ0.5.

Ensures 100% vector space alignment between Cloud Identity DB and Edge Devices.
Extracts 512-D L2-normalized embedding with 5-point similarity alignment and
stores into customer_embeddings (pgvector + BYTEA).
"""

import argparse
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import cv2
import numpy as np
from app.core.insight_embedding import InsightEmbedder
from app.core.vector_cache import vector_cache_manager
from app.db.connection import get_customer_info, get_db_connection, upsert_customer
from app.db.vector_search import insert_embedding_with_vector


def enroll_face(
    image_path: str,
    customer_id: str,
    name: str = None,
    service_category: str = "General",
    embedder: InsightEmbedder = None,
) -> dict:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found at {image_path}")

    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Could not read image file at {image_path}")

    if embedder is None:
        embedder = InsightEmbedder()

    # Detect faces with SCRFD-500M
    boxes, landmarks, scores = embedder.detect(img_bgr)
    if len(boxes) == 0:
        return {"success": False, "error": "No face detected in image"}

    # Take the largest face if multiple faces detected
    if len(boxes) > 1:
        areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]
        best_idx = int(np.argmax(areas))
    else:
        best_idx = 0

    best_box = boxes[best_idx]
    best_lm = landmarks[best_idx]
    det_score = float(scores[best_idx])

    # Extract aligned 512D embedding via EdgeFace γ0.5
    embedding = embedder.get_embedding(img_bgr, best_lm)
    if embedding is None:
        return {"success": False, "error": "Failed to extract embedding"}

    embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    conn = get_db_connection()
    try:
        # 1. Upsert customer profile
        existing_info = get_customer_info(conn, customer_id)
        customer_name = name or (existing_info.get("name") if existing_info else None) or f"Customer {customer_id}"
        
        upsert_customer(
            conn,
            customer_id=customer_id,
            name=customer_name,
            service_category=service_category,
        )

        # 2. Insert into customer_embeddings (pgvector + BYTEA)
        face_blob = embedding.tobytes()
        insert_embedding_with_vector(
            conn,
            customer_id=customer_id,
            face_embedding_blob=face_blob,
            embedding_np=embedding,
            model_name="edgeface_s_gamma_05",
        )
        conn.commit()

        # 3. Add to local vector cache
        vector_cache_manager.add_to_cache(customer_id, embedding)

        return {
            "success": True,
            "customer_id": customer_id,
            "name": customer_name,
            "detection_score": round(det_score, 4),
            "bbox": [int(x) for x in best_box],
            "embedding_dim": len(embedding),
            "model": "edgeface_s_gamma_05",
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Enroll customer face into Cloud Identity DB")
    parser.add_argument("--image", required=True, help="Path to face image")
    parser.add_argument("--id", required=True, help="Customer ID (e.g. 001, CUST_100)")
    parser.add_argument("--name", help="Customer Full Name")
    parser.add_argument("--category", default="VIP", help="Customer Category (VIP, Staff, etc.)")

    args = parser.parse_args()
    print(f"[Enrollment] Processing image: {args.image} for ID: {args.id}...")
    res = enroll_face(
        image_path=args.image,
        customer_id=args.id,
        name=args.name,
        service_category=args.category,
    )
    if res["success"]:
        print(f"[SUCCESS] Enrolled customer {res['name']} (ID: {res['customer_id']}) with EdgeFace γ0.5!")
        print(f"          Detection Score: {res['detection_score']}, Bbox: {res['bbox']}")
    else:
        print(f"[ERROR] Enrollment failed: {res.get('error')}")


if __name__ == "__main__":
    main()
