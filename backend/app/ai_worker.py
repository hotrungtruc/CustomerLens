import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

import cv2
import numpy as np
import redis
from kafka import KafkaConsumer

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.insight_embedding import InsightEmbedder
from config import PROCESS_EVERY_N_FRAMES
from app.core.settings import system_settings

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
    
    frame_queue = "camera_frames_v2"
    frame_count = 0
    
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
    logger.info(f"Worker is ready and waiting for frames on Redpanda '{KAFKA_BOOTSTRAP_SERVERS}'...")
    
    try:
        consumer = KafkaConsumer(
            "camera_frames",
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id="ai_workers",
            auto_offset_reset='latest',
            enable_auto_commit=True
        )
    except Exception as e:
        logger.error(f"Failed to connect to Redpanda: {e}")
        sys.exit(1)
        
    while True:
        try:
            # Batch Polling (Max 50 records)
            records = consumer.poll(timeout_ms=1000, max_records=50)
            
            if not records:
                continue
                
            # Deduplication: keep only the latest frame per (connection_id, local_track_id)
            latest_frames = {}
            for topic_partition, messages in records.items():
                for msg in messages:
                    item = msg.value
                    meta_len = int.from_bytes(item[:4], byteorder="big")
                    try:
                        meta_json = item[4:4+meta_len].decode("utf-8")
                        data = json.loads(meta_json)
                    except Exception as e:
                        logger.error(f"Failed to parse metadata: {e}")
                        continue
                    
                    connection_id = data.get("connection_id")
                    local_track_id = data.get("local_track_id")
                    
                    if not connection_id:
                        continue
                        
                    # If it's a full frame without track id, don't deduplicate by track id
                    key = (connection_id, local_track_id) if local_track_id else (connection_id, id(msg))
                    
                    # Store the latest message for this key (messages are ordered by offset)
                    latest_frames[key] = (item, data, meta_len)

            for key, (item, data, meta_len) in latest_frames.items():
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
                
                face_records = []
                batch_landmarks = []
                batch_records = []
            
                if is_edge_crop:
                    # Run SCRFD detection on the edge crop to get high-precision landmarks
                    detections = embedder.detect(frame)
                    h, w = frame.shape[:2]
                    
                    # If SCRFD fails to detect on the crop, fallback to frontend landmarks or full crop
                    if len(detections[0]) == 0:
                        landmarks = data.get("landmarks")
                        quality_ok = True
                        guest_quality_ok = True
                        if landmarks is not None and len(landmarks) >= 2:
                            left_eye = np.array(landmarks[0])
                            right_eye = np.array(landmarks[1])
                            eye_dist = np.linalg.norm(left_eye - right_eye)
                            face_width = max(1.0, w / 2.0)
                            if eye_dist / face_width < 0.25:
                                guest_quality_ok = False
                        
                        record = {
                            "bbox": (0, 0, w, h), # Full crop
                            "landmark": landmarks,
                            "score": 1.0,
                            "quality_ok": quality_ok,
                            "guest_quality_ok": guest_quality_ok,
                            "embedding": None,
                        }
                        if landmarks is not None:
                            face_records.append(record)
                            batch_landmarks.append(landmarks)
                            batch_records.append(record)
                    else:
                        # Use the best detection from SCRFD (usually there's only one in a tight crop)
                        # We take the first one or the one with highest score
                        bbox, landmark, score = detections[0][0], detections[1][0], detections[2][0]
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
                else:
                    detections = embedder.detect(frame)
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
                
                redis_client.publish(pubsub_channel, json.dumps(payload))
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}", exc_info=True)
            time.sleep(1)

if __name__ == "__main__":
    main()
