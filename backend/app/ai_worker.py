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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concurrent.futures import ThreadPoolExecutor

from app.core.insight_embedding import InsightEmbedder
from config import (
    PROCESS_EVERY_N_FRAMES,
    KAFKA_BOOTSTRAP_SERVERS,
    REDIS_URL,
    KAFKA_CAMERA_FRAMES_TOPIC,
    REDIS_CAMERA_FRAMES_FALLBACK_QUEUE,
)
from app.core.settings import system_settings
from app.messaging.kafka_client import init_topics

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AIWorker")

redis_client = redis.from_url(REDIS_URL)

def main():

    parser = argparse.ArgumentParser(description="Stateless AI Worker for Face Recognition")
    parser.add_argument("--camera", type=str, default="default", help="(Deprecated) Camera ID - ignored in stateless mode")
    args = parser.parse_args()
    
    logger.info("Starting Stateless AI Worker...")
    
    # Initialize Models
    embedder = InsightEmbedder()
    
    frame_count = 0
    last_settings_reload = time.time()
    executor = ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2))

    # Event-driven settings subscriber
    settings_pubsub = None
    try:
        settings_pubsub = redis_client.pubsub()
        settings_pubsub.subscribe("system_settings_updated")
        logger.info("[WORKER] Subscribed to system_settings_updated pubsub channel.")
    except Exception as e:
        logger.warning(f"[WORKER] Could not subscribe to settings updates: {e}")
    
    # Ensure Redpanda topic is initialized
    try:
        init_topics()
    except Exception as e:
        logger.warning(f"Could not auto-initialize Redpanda topics: {e}")

    from app.messaging.kafka_client import is_kafka_reachable

    def create_kafka_consumer():
        if not is_kafka_reachable(KAFKA_BOOTSTRAP_SERVERS):
            return None
        try:
            c = KafkaConsumer(
                KAFKA_CAMERA_FRAMES_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id="ai_workers",
                auto_offset_reset='latest',
                enable_auto_commit=True,
                metadata_max_age_ms=2000,
                consumer_timeout_ms=300,
                request_timeout_ms=1000,
            )
            logger.info(f"[SUCCESS] Connected to Redpanda at '{KAFKA_BOOTSTRAP_SERVERS}'")
            return c
        except Exception as e:
            logger.warning(f"[RETRY NEEDED] Redpanda unavailable ({e}). Worker starting in Redis Fallback mode.")
            return None

    consumer = create_kafka_consumer()
    if consumer is None:
        logger.info("Redpanda is offline. AI Worker is running in high-speed Redis Fallback mode.")

    last_kafka_retry = time.time()
    
    while True:
        try:
            # 1. Background retry connection to Redpanda if disconnected (check every 15s)
            if consumer is None and (time.time() - last_kafka_retry > 15):
                last_kafka_retry = time.time()
                consumer = create_kafka_consumer()

            raw_items = []

            # 2. Poll Redpanda if active
            if consumer is not None:
                try:
                    records = consumer.poll(timeout_ms=200, max_records=50)
                    if records:
                        for topic_partition, messages in records.items():
                            for msg in messages:
                                raw_items.append(msg.value)
                except Exception as e:
                    logger.warning(f"Redpanda poll error ({e}). Re-entering reconnect mode.")
                    try:
                        consumer.close()
                    except Exception:
                        pass
                    consumer = None

            # 3. Pull frames from Redis Fallback Queue
            while True:
                fallback_val = redis_client.rpop(REDIS_CAMERA_FRAMES_FALLBACK_QUEUE)
                if not fallback_val:
                    break
                raw_items.append(fallback_val)

            if not raw_items:
                time.sleep(0.01)
                continue
                
            # Deduplication: keep only the latest frame per (connection_id, local_track_id)
            latest_frames = {}
            for item in raw_items:
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
                    
                key = (connection_id, local_track_id) if local_track_id else (connection_id, data.get("opeid"))
                latest_frames[key] = (item, data, meta_len)

            for key, (item, data, meta_len) in latest_frames.items():
                # It's a frame (Binary Packed)
                frame_count += 1
                camera_id = data.get("camera_id")
                connection_id = data.get("connection_id")
                local_track_id = data.get("local_track_id")
                logger.info(f"[WORKER] Popped frame #{frame_count} for camera={camera_id}, conn={connection_id}, track={local_track_id}")
                
                # Event-driven settings reload check or throttled background refresh (30s)
                if settings_pubsub is not None:
                    try:
                        s_msg = settings_pubsub.get_message(ignore_subscribe_messages=True, timeout=0.0)
                        if s_msg:
                            system_settings.load_settings()
                            logger.info("[WORKER] System settings reloaded via event channel.")
                    except Exception:
                        pass

                now_ts = time.time()
                if now_ts - last_settings_reload > 30.0:
                    last_settings_reload = now_ts
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
                    h, w = frame.shape[:2]
                    # 1. Run backend SCRFD on the 30%-padded crop to extract high-precision 5 landmarks
                    detections = embedder.detect(frame)
                    if len(detections[0]) > 0:
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
                        # 2. Fallback if SCRFD couldn't detect in tight crop, but client provided landmarks
                        client_landmarks = data.get("landmarks")
                        if client_landmarks is not None and len(client_landmarks) in (4, 5):
                            record = {
                                "bbox": (0, 0, w, h),
                                "landmark": client_landmarks,
                                "score": 0.85,
                                "quality_ok": True,
                                "guest_quality_ok": True,
                                "embedding": None,
                            }
                            face_records.append(record)
                            batch_landmarks.append(client_landmarks)
                            batch_records.append(record)
                            
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
                        batch_embs = embedder.get_batch_embeddings(
                            frame,
                            batch_landmarks,
                            use_tta=False if (is_edge_crop or len(batch_landmarks) > 1) else None,
                        )
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
                
                logger.info(f"[WORKER] Publishing {len(face_records)} face records to {pubsub_channel} (has_emb={any(r.get('embedding') is not None for r in face_records)})")
                json_payload = json.dumps(payload)
                try:
                    redis_client.publish(pubsub_channel, json_payload)
                except Exception:
                    pass
                # Also push to list queue for 100% reliable delivery without pubsub socket issues
                list_key = f"results_queue:{connection_id}"
                redis_client.lpush(list_key, json_payload)
                redis_client.ltrim(list_key, 0, 50)
                redis_client.expire(list_key, 60)
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}", exc_info=True)
            time.sleep(1)

if __name__ == "__main__":
    main()
