import argparse
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime

import cv2
import numpy as np
import redis

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.guest_tracking import GuestTrackManager
from app.core.insight_embedding import InsightEmbedder
from app.db.connection import (bulk_insert_recognize_logs, get_customer_info,
                               get_db_connection)
from config import (FRAME_HEIGHT, FRAME_WIDTH, GUEST_CREATION_BUFFER_SIZE,
                    MIN_DETECTION_SCORE, MIN_FACE_BBOX_SIZE,
                    PROCESS_EVERY_N_FRAMES, SIMILARITY_THRESHOLD,
                    TRACK_BUFFER_SIZE, TRACK_IOU_THRESHOLD)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AIWorker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

def _apply_profile_to_payload(payload: dict, info: dict):
    payload.update({
        "id": info["customer_id"],
        "name": info["name"] or "Khach moi",
        "email": info.get("email"),
        "occupation": info.get("occupation", "General"),
        "registered_at": info.get("registered_at"),
        "tenure": info.get("tenure", 0),
        "loyalty_tier": info.get("loyalty_tier", "Standard"),
        "total_visits": info.get("total_visits", 0),
        "last_visit": info.get("last_visit"),
        "total_spending": info.get("total_spending", 0),
        "service_category": info.get("service_category", "General"),
        "service_start_year": info.get("service_start_year", 0),
        "customer_tenure_years": info.get("customer_tenure_years", 0),
        "customer_type": info.get("customer_type", "guest"),
        "customer_status": info.get("status", "active"),
        "has_face_embedding": info.get("has_face_embedding"),
        "face_embedding_dim": info.get("face_embedding_dim"),
        "face_embedding_model": info.get("face_embedding_model"),
        "phone": info.get("phone"),
        "note": info.get("note"),
    })

def main():
    parser = argparse.ArgumentParser(description="AI Worker for Face Recognition")
    parser.add_argument("--camera", type=str, default="default", help="Camera ID to process")
    args = parser.parse_args()
    
    camera_id = args.camera
    logger.info(f"Starting AI Worker for camera: {camera_id}")
    
    # Initialize Models
    embedder = InsightEmbedder()
    track_manager = GuestTrackManager(
        buffer_size=TRACK_BUFFER_SIZE,
        guest_creation_buffer_size=GUEST_CREATION_BUFFER_SIZE,
        similarity_threshold=SIMILARITY_THRESHOLD,
        iou_threshold=TRACK_IOU_THRESHOLD,
        min_bbox_size=MIN_FACE_BBOX_SIZE,
        min_detection_score=MIN_DETECTION_SCORE,
        guest_prefix=f"GUEST_{camera_id}",
    )
    
    conn = get_db_connection()
    frame_queue = f"camera_frames_{camera_id}"
    control_queue = f"camera_control_{camera_id}"
    pubsub_channel = f"camera_results_{camera_id}"
    
    frame_count = 0
    
    logger.info("Worker is ready and waiting for frames...")
    
    while True:
        try:
            # BRPOP blocks until an item is available. Priority: control_queue > frame_queue
            result = redis_client.brpop([control_queue, frame_queue], timeout=1)
            
            if not result:
                continue
                
            queue_name, item = result
            queue_name = queue_name.decode("utf-8")
            
            if queue_name == control_queue:
                data = json.loads(item.decode("utf-8"))
                action = data.get("action")
                if action == "promote_guest":
                    logger.info(f"Promoting guest {data['guest_id']} to {data['new_id']}")
                    track_manager.promote_guest(data["guest_id"], data["new_id"])
                    track_manager.load_known_embeddings()
                elif action == "reload_embeddings":
                    logger.info("Reloading embeddings from database...")
                    track_manager.load_known_embeddings()
                elif action == "invalidate_cache":
                    cid = data.get("customer_id")
                    for tid, track in track_manager.tracks.items():
                        if track.cached_profile and track.cached_profile.get("customer_id") == cid:
                            track.cached_profile = None
                continue
                
            # It's a frame (Binary Packed)
            frame_count += 1
            if frame_count % PROCESS_EVERY_N_FRAMES != 0:
                continue
                
            # Unpack 4-byte length
            meta_len = int.from_bytes(item[:4], byteorder="big")
            meta_json = item[4:4+meta_len].decode("utf-8")
            data = json.loads(meta_json)
            raw_image_bytes = item[4+meta_len:]
                
            opeid = data.get("opeid")
            
            try:
                image_array = np.frombuffer(raw_image_bytes, dtype=np.uint8)
                frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            except Exception as e:
                logger.error(f"Frame decode error: {e}")
                frame = None
            
            if frame is None:
                continue
                
            # Detect
            detections = embedder.detect(frame)
            face_records = []
            for bbox, landmark, score in zip(*detections):
                x1, y1, x2, y2 = map(int, bbox)
                quality_ok = embedder.is_quality_ok((x1, y1, x2, y2), score)
                guest_quality_ok = embedder.is_guest_quality_ok((x1, y1, x2, y2), score, landmark)
                
                face_records.append({
                    "bbox": (x1, y1, x2, y2),
                    "landmark": landmark,
                    "score": float(score),
                    "quality_ok": quality_ok,
                    "guest_quality_ok": guest_quality_ok,
                    "embedding": None,
                })
                
            tracked_faces = track_manager.process_faces(face_records, frame=frame, embedder=embedder)
            
            customers = []
            logs = []
            
            for face in tracked_faces:
                x1, y1, x2, y2 = face["bbox"]
                customer_id = face["customer_id"]
                track_id = face["track_id"]
                
                payload = {
                    "tile_id": f"tile_{track_id}",
                    "track_id": track_id,
                    "bbox": (x1, y1, x2, y2),
                    "detected": bool(customer_id),
                    "id": customer_id,
                    "name": "Khach moi",
                    "customer_type": "guest",
                    "customer_status": "temporary"
                }
                
                if customer_id:
                    track = track_manager.tracks.get(track_id)
                    info = track.cached_profile if track else None
                    
                    if not info:
                        info = get_customer_info(conn, customer_id)
                        if info and track:
                            track.cached_profile = info
                            
                    if info:
                        _apply_profile_to_payload(payload, info)
                        
                customers.append(payload)
                
                # Prepare log entry for Bulk Insert
                logs.append({
                    "opeid": opeid,
                    "camera_id": camera_id,
                    "customer_id": customer_id,
                    "track_id": track_id,
                    "bbox": (x1, y1, x2, y2),
                    "timestamp": data.get("timestamp")
                })
                
            # Bulk Insert logs
            if logs:
                bulk_insert_recognize_logs(conn, logs)
                
            # Publish to Pub/Sub
            pubsub_message = {
                "customers": customers,
                "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT}
            }
            redis_client.publish(pubsub_channel, json.dumps(pubsub_message))
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}", exc_info=True)
            time.sleep(1)

if __name__ == "__main__":
    main()
