import argparse
import json
import logging
import os
import sys
import time

import cv2
import numpy as np
import redis
from kafka import KafkaConsumer, KafkaProducer

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.insight_embedding import InsightEmbedder
from config import PROCESS_EVERY_N_FRAMES
from app.core.settings import system_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AIWorker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

KAFKA_BROKER_URL = os.getenv("KAFKA_BROKER_URL", "redpanda:29092")

def main():
    parser = argparse.ArgumentParser(description="Stateless AI Worker for Face Recognition")
    parser.add_argument("--camera", type=str, default="default", help="(Deprecated) Camera ID - ignored in stateless mode")
    args = parser.parse_args()
    
    logger.info("Starting Stateless AI Worker...")
    
    # Initialize Models
    embedder = InsightEmbedder()
    
    frame_queue = "camera_frames_v2"
    frame_count = 0
    
    logger.info(f"Worker connecting to Kafka at {KAFKA_BROKER_URL}...")
    
    # Initialize Kafka Consumer and Producer
    consumer = KafkaConsumer(
        frame_queue,
        bootstrap_servers=KAFKA_BROKER_URL,
        group_id="ai_workers_group",
        auto_offset_reset='latest'
    )
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER_URL,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    logger.info("Worker is ready and waiting for frames on Kafka topic 'camera_frames_v2'...")
    
    for message in consumer:
        try:
            item = message.value
            
            # Unpack 4-byte length
            meta_len = int.from_bytes(item[:4], byteorder="big")
            meta_json = item[4:4+meta_len].decode("utf-8")
            data = json.loads(meta_json)
            
            # Drop frame if delayed > 500ms (realtime constraint)
            timestamp_str = data.get("timestamp")
            if timestamp_str:
                try:
                    frame_time = datetime.fromisoformat(timestamp_str).timestamp()
                    delay = time.time() - frame_time
                    if delay > 0.5:
                        logger.warning(f"Dropping stale frame (delay: {delay:.3f}s)")
                        continue
                except Exception:
                    pass
            
            # It's a frame (Binary Packed)
            frame_count += 1
            
            # Reload settings every 60 frames to check for updates
            if frame_count % 60 == 0:
                system_settings.load_settings()
                
            current_n_frames = system_settings.get("process_every_n_frames", PROCESS_EVERY_N_FRAMES)
            raw_image_bytes = item[4+meta_len:]

            opeid = data.get("opeid")
            camera_id = data.get("camera_id")
            connection_id = data.get("connection_id")
            reply_to = data.get("reply_to")
            local_track_id = data.get("local_track_id")
            client_bbox = data.get("bbox") # Original bbox from frontend
            
            # If it's an edge crop, process it immediately (frontend already throttles)
            is_edge_crop = bool(local_track_id)
            if not is_edge_crop:
                if frame_count % current_n_frames != 0:
                    continue
            
            if not camera_id or not connection_id:
                logger.warning(
                    "Received frame without camera_id or connection_id. Skipping."
                )
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
            pubsub_channel = f"worker_results_{connection_id}"
            
            payload = {
                "opeid": opeid,
                "camera_id": camera_id,
                "connection_id": connection_id,
                "timestamp": data.get("timestamp"),
                "face_records": face_records,
                "frame_size": {"width": frame.shape[1], "height": frame.shape[0]}
            }
            if is_edge_crop:
                payload["local_track_id"] = local_track_id
                payload["client_bbox"] = client_bbox
                
            if reply_to:
                producer.send(reply_to, value=payload)
            else:
                logger.warning(f"No reply_to topic found for connection {connection_id}")
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}", exc_info=True)
            time.sleep(1)

if __name__ == "__main__":
    main()
