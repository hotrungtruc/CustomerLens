import argparse
import json
import logging
import os
import sys
import time

import cv2
import numpy as np
import redis

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.insight_embedding import InsightEmbedder
from config import PROCESS_EVERY_N_FRAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AIWorker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

def main():
    parser = argparse.ArgumentParser(description="Stateless AI Worker for Face Recognition")
    parser.add_argument("--camera", type=str, default="default", help="(Deprecated) Camera ID - ignored in stateless mode")
    args = parser.parse_args()
    
    logger.info("Starting Stateless AI Worker...")
    
    # Initialize Models
    embedder = InsightEmbedder()
    
    frame_queue = "camera_frames"
    frame_count = 0
    
    logger.info("Worker is ready and waiting for frames on global queue 'camera_frames'...")
    
    while True:
        try:
            # BRPOP blocks until an item is available.
            result = redis_client.brpop([frame_queue], timeout=1)
            
            if not result:
                continue
                
            queue_name, item = result
            
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
            camera_id = data.get("camera_id")
            
            if not camera_id:
                logger.warning("Received frame without camera_id. Skipping.")
                continue
            
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
            
            batch_landmarks = []
            batch_records = []
            
            for bbox, landmark, score in zip(*detections):
                x1, y1, x2, y2 = map(int, bbox)
                quality_ok = embedder.is_quality_ok((x1, y1, x2, y2), score)
                guest_quality_ok = embedder.is_guest_quality_ok((x1, y1, x2, y2), score, landmark)
                
                record = {
                    "bbox": (x1, y1, x2, y2),
                    "landmark": landmark.tolist() if isinstance(landmark, np.ndarray) else landmark,
                    "score": float(score),
                    "quality_ok": quality_ok,
                    "guest_quality_ok": guest_quality_ok,
                    "embedding": None,
                }
                face_records.append(record)
                
                if quality_ok and "landmark" in record:
                    batch_landmarks.append(landmark)
                    batch_records.append(record)
                    
            # --- BATCH EMBEDDING EXTRACTION ---
            if batch_landmarks and frame is not None:
                try:
                    batch_embs = embedder.get_batch_embeddings(frame, batch_landmarks)
                    for record, emb in zip(batch_records, batch_embs):
                        if emb is not None:
                            record["embedding"] = emb.tolist() if isinstance(emb, np.ndarray) else emb
                except Exception as e:
                    logger.warning(f"Batch extraction error: {e}")
            
            # Publish back to Master
            pubsub_channel = f"worker_results_{camera_id}"
            
            payload = {
                "opeid": opeid,
                "camera_id": camera_id,
                "timestamp": data.get("timestamp"),
                "face_records": face_records,
                "frame_size": {"width": frame.shape[1], "height": frame.shape[0]}
            }
            redis_client.publish(pubsub_channel, json.dumps(payload))
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}", exc_info=True)
            time.sleep(1)

if __name__ == "__main__":
    main()
