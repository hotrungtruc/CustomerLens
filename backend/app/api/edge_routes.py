import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.core.biometric_security import biometric_protector
from app.core.settings import system_settings
from app.db.connection import (
    bulk_insert_recognize_logs,
    get_customer_info,
    get_db_connection,
    update_attendance,
)
from app.db.vector_search import search_similar_faces
from config import FRAME_HEIGHT, FRAME_WIDTH, MODELS_DIR, SIMILARITY_THRESHOLD

router = APIRouter()

# In-memory storage for Edge device status and attendance debounce
EDGE_DEVICES: Dict[str, Dict[str, Any]] = {}
ATTENDANCE_DEBOUNCE: Dict[str, float] = {}  # {customer_id: last_checkin_timestamp}
DEBOUNCE_SECONDS = 60.0  # Cooldown between attendance increments for the same person


import base64
import cv2

class EdgeFaceEvent(BaseModel):
    camera_id: str
    device_id: str = "edge_default"
    track_id: int
    event_type: str = "first_shot"  # "first_shot", "best_shot", "heartbeat", "track_end"
    timestamp: float = Field(default_factory=time.time)
    bbox: List[float]  # [x1, y1, x2, y2]
    quality_score: float = 1.0
    embedding: Optional[List[float]] = None  # Optional 512 float values
    crop_image_base64: Optional[str] = None
    frame_size: Optional[Dict[str, int]] = None  # {"width": 640, "height": 480}


class EdgeBatchEvents(BaseModel):
    events: List[EdgeFaceEvent]


class EdgeHeartbeat(BaseModel):
    device_id: str
    camera_id: str
    fps: float = 0.0
    cpu_usage: float = 0.0
    mem_usage: float = 0.0
    tracks_active: int = 0
    timestamp: float = Field(default_factory=time.time)


ALLOWED_MODEL_FILES = {
    "scrfd_500m_bnkps.onnx": {
        "description": "SCRFD-500M Face Detector with 5 Keypoints",
        "sha256": "a3562ef62592bf387f6ef19151282ac127518e51c77696e62e0661bee95ba1ad",
        "version": "1.0.0",
    },
    "edgeface_int8.onnx": {
        "description": "EdgeFace INT8 Quantized Lightweight Feature Extractor (512-D)",
        "sha256": "dynamic_int8",
        "version": "1.0.0",
    },
    "edgeface_s_gamma_05.onnx": {
        "description": "EdgeFace S Gamma 0.5 Lightweight Feature Extractor (512-D)",
        "sha256": "b850767cf791bda585600b5c4c7d7432b2f998ccd862caae34ef1afa967d2e54",
        "version": "1.0.0",
    },
}


async def _get_redis_client():
    try:
        from app.messaging.kafka_client import get_redis
        return await get_redis()
    except Exception:
        return None


def _calculate_file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. Ingestion Endpoint: Receive Face Crop / Embedding from Edge Device
# ---------------------------------------------------------------------------
@router.post("/events")
async def receive_edge_face_event(event: EdgeFaceEvent):
    """
    Ingest a face event sent by an Edge device.
    1. If crop_image_base64 is sent without embedding, extracts 5 landmarks via SCRFD 500M
       and generates 512-D embedding via EdgeFace (int8).
    2. Runs vector search against Identity DB (pgvector / L1 cache).
    3. If recognized, updates attendance and recognize logs.
    4. Broadcasts recognition update to Dashboard observer via Redis PubSub.
    """
    from app.core.insight_embedding import get_embedder

    emb_arr = None
    if event.embedding and len(event.embedding) == 512:
        emb_arr = np.asarray(event.embedding, dtype=np.float32)
    elif event.crop_image_base64:
        try:
            crop_bytes = base64.b64decode(event.crop_image_base64)
            crop_arr = np.frombuffer(crop_bytes, dtype=np.uint8)
            crop_bgr = cv2.imdecode(crop_arr, cv2.IMREAD_COLOR)
            if crop_bgr is not None and crop_bgr.size > 0:
                embedder = get_embedder()
                # Run SCRFD 500M on the padded crop to detect facial landmarks
                detections = embedder.detect(crop_bgr)
                landmark = None
                if len(detections[0]) > 0 and len(detections[1]) > 0:
                    landmark = detections[1][0]
                else:
                    # Fallback landmark approximation based on crop geometry
                    ch, cw = crop_bgr.shape[:2]
                    landmark = np.array([
                        [cw * 0.35, ch * 0.38],
                        [cw * 0.65, ch * 0.38],
                        [cw * 0.50, ch * 0.55],
                        [cw * 0.38, ch * 0.75],
                        [cw * 0.62, ch * 0.75],
                    ], dtype=np.float32)

                emb = embedder.get_embedding(crop_bgr, landmark)
                if emb is not None:
                    emb_arr = np.asarray(emb, dtype=np.float32)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to process crop image on server: {e}",
            )

    if emb_arr is None or len(emb_arr) != 512:
        raise HTTPException(
            status_code=422,
            detail="Either valid 512D embedding or crop_image_base64 must be provided",
        )

    norm = np.linalg.norm(emb_arr)
    if norm > 0:
        emb_arr = emb_arr / norm


    threshold = float(system_settings.get("similarity_threshold", SIMILARITY_THRESHOLD))
    conn = get_db_connection()

    match_result = {
        "matched": False,
        "customer_id": None,
        "name": "Khách chưa đăng ký",
        "similarity": 0.0,
        "customer_type": "guest",
        "event_type": event.event_type,
        "track_id": event.track_id,
        "camera_id": event.camera_id,
        "greeting": None,
    }

    try:
        # Search against pgvector with cancelable biometric protection
        results = search_similar_faces(conn, emb_arr, top_k=3, threshold=threshold)
        now_ts = time.time()

        if results:
            best_id, best_sim = results[0]
            customer_info = get_customer_info(conn, best_id)
            if customer_info:
                customer_name = customer_info.get("name") or best_id
                match_result.update({
                    "matched": True,
                    "customer_id": best_id,
                    "name": customer_name,
                    "similarity": round(float(best_sim), 4),
                    "customer_type": customer_info.get("customer_type", "customer"),
                    "greeting": f"Xin chào {customer_name}!",
                })

                # Checkin attendance debounce (only increment once per cooldown)
                last_checkin = ATTENDANCE_DEBOUNCE.get(best_id, 0.0)
                if now_ts - last_checkin > DEBOUNCE_SECONDS:
                    ATTENDANCE_DEBOUNCE[best_id] = now_ts
                    try:
                        update_attendance(conn, best_id)
                    except Exception as e:
                        print(f"[Edge Ingestion] Attendance update error: {e}", flush=True)

                # Insert into recognize_logs
                try:
                    bulk_insert_recognize_logs(
                        conn,
                        [
                            {
                                "opeid": "EDGE_SYSTEM",
                                "camera_id": event.camera_id,
                                "connection_id": f"edge_{event.device_id}",
                                "customer_id": best_id,
                                "track_id": event.track_id,
                                "bbox": event.bbox,
                                "timestamp": datetime.now(timezone.utc),
                            }
                        ],
                    )
                except Exception as e:
                    print(f"[Edge Ingestion] Log insert error: {e}", flush=True)

    finally:
        conn.close()

    # Broadcast to Redis for live dashboard observer (/ws/observe/{camera_id})
    redis_client = await _get_redis_client()
    if redis_client:
        try:
            frame_size = event.frame_size or {"width": FRAME_WIDTH, "height": FRAME_HEIGHT}
            customer_payload = {
                "id": match_result["customer_id"] or f"GUEST_{event.track_id}",
                "name": match_result["name"],
                "bbox": [int(x) for x in event.bbox],
                "confidence": round(float(event.quality_score), 2),
                "distance": round(1.0 - match_result["similarity"], 4) if match_result["matched"] else 1.0,
                "similarity": match_result["similarity"],
                "match_type": "identified" if match_result["matched"] else "guest",
                "track_id": event.track_id,
                "event_type": event.event_type,
            }
            if event.crop_image_base64:
                customer_payload["thumbnail"] = f"data:image/jpeg;base64,{event.crop_image_base64}"

            pubsub_message = {
                "type": "camera_update",
                "customers": [customer_payload],
                "frame_size": frame_size,
                "camera_id": event.camera_id,
                "connection_id": f"edge_{event.device_id}",
                "timestamp": event.timestamp,
            }
            await redis_client.publish(
                f"camera_updates:{event.camera_id}",
                json.dumps(pubsub_message, default=str),
            )
        except Exception as e:
            print(f"[Edge Ingestion] Redis broadcast error: {e}", flush=True)

    return JSONResponse(content={"success": True, "result": match_result})


@router.post("/batch-events")
async def receive_edge_batch_events(batch: EdgeBatchEvents):
    """Batch ingestion for high-throughput Edge nodes."""
    results = []
    for ev in batch.events:
        res = await receive_edge_face_event(ev)
        results.append(res)
    return {"success": True, "processed": len(results)}


# ---------------------------------------------------------------------------
# 2. Heartbeat & Health Endpoint: Monitor Edge Devices
# ---------------------------------------------------------------------------
@router.post("/heartbeat")
async def edge_heartbeat(hb: EdgeHeartbeat):
    """Keepalive and telemetries from Edge devices."""
    EDGE_DEVICES[hb.device_id] = {
        "device_id": hb.device_id,
        "camera_id": hb.camera_id,
        "fps": hb.fps,
        "cpu_usage": hb.cpu_usage,
        "mem_usage": hb.mem_usage,
        "tracks_active": hb.tracks_active,
        "last_seen": time.time(),
        "status": "online",
    }
    return {
        "status": "ok",
        "server_time": time.time(),
        "acknowledged": hb.device_id,
    }


@router.get("/devices")
async def list_edge_devices():
    """List all registered Edge devices and their real-time status."""
    now = time.time()
    devices = []
    for dev_id, data in EDGE_DEVICES.items():
        is_alive = (now - data.get("last_seen", 0)) < 30.0
        item = dict(data)
        item["status"] = "online" if is_alive else "offline"
        devices.append(item)
    return {"count": len(devices), "devices": devices}


# ---------------------------------------------------------------------------
# 3. Model Management & OTA Distribution
# ---------------------------------------------------------------------------
@router.get("/models/manifest")
async def get_model_manifest():
    """
    Returns the OTA model manifest with filename, version, file size,
    and SHA-256 hash so Edge devices can detect updates and synchronize weights.
    """
    manifest = {
        "version": "1.0.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "models": {},
    }

    for filename, meta in ALLOWED_MODEL_FILES.items():
        model_path = MODELS_DIR / filename
        exists = model_path.exists()
        size = model_path.stat().st_size if exists else 0
        sha = _calculate_file_sha256(model_path) if exists else meta["sha256"]

        manifest["models"][filename] = {
            "filename": filename,
            "description": meta["description"],
            "version": meta["version"],
            "size_bytes": size,
            "sha256": sha,
            "available": exists,
            "download_url": f"/api/v1/edge/models/download/{filename}",
        }

    return manifest


@router.get("/models/download/{model_name}")
async def download_model_file(model_name: str):
    """Download ONNX model file directly from Cloud server."""
    if model_name not in ALLOWED_MODEL_FILES:
        raise HTTPException(status_code=404, detail="Requested model not found in manifest")

    model_path = MODELS_DIR / model_name
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model file {model_name} is not present on server")

    return FileResponse(
        path=str(model_path),
        filename=model_name,
        media_type="application/octet-stream",
    )
