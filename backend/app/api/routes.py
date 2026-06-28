import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime

import numpy as np
import redis.asyncio as aioredis
from fastapi import (APIRouter, Header, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import Response

# Session store mapping hex tokens to user dicts
ACTIVE_SESSIONS = {}

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_pool = aioredis.ConnectionPool.from_url(REDIS_URL)

async def get_redis():
    return aioredis.Redis(connection_pool=redis_pool)

def get_user_from_token(authorization: str | None = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    token = authorization.split(" ")[1].strip()
    if token not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return ACTIVE_SESSIONS[token]

def require_admin(authorization: str | None = None):
    user = get_user_from_token(authorization)
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403, detail="Unauthorized action: Admin role required"
        )
    return user

from app.db.connection import (create_or_update_customer_profile,
                               ensure_schema, get_customer_info,
                               get_db_connection, update_attendance, bulk_insert_recognize_logs)
from config import (CHECKIN_COOLDOWN_SECONDS, FRAME_HEIGHT, FRAME_WIDTH,
                    GUEST_CREATION_BUFFER_SIZE, MIN_DETECTION_SCORE, MIN_FACE_BBOX_SIZE, SIMILARITY_THRESHOLD, TRACK_BUFFER_SIZE, TRACK_IOU_THRESHOLD)
from app.core.guest_tracking import GuestTrackManager

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

router = APIRouter()

class CameraState:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.active = True
        self.latest_jpeg = None          # Raw JPEG bytes of last received frame
        self.last_frame_time = None      # time.time() when last frame was received
        self.latest_customers_payload = []

CAMERA_STATES = {}
CAMERA_STATES_LOCK = threading.Lock()

def get_camera_state(camera_id: str | None = None) -> CameraState:
    cid = (camera_id or "default").strip()
    with CAMERA_STATES_LOCK:
        if cid not in CAMERA_STATES:
            CAMERA_STATES[cid] = CameraState(cid)
        return CAMERA_STATES[cid]

@router.get("/")
def index():
    return {"status": "ok", "message": "Backend running"}

@router.get("/test")
def test():
    return {"status": "ok", "message": "FastAPI backend is running"}

@router.post("/api/login")
async def api_login(request: Request):
    payload = await request.json()
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()

    if not username or not password:
        raise HTTPException(
            status_code=400, detail="Username and password are required"
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, password_hash, role, cameras FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        if row["password_hash"] != pwd_hash:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = secrets.token_hex(16)
        cameras_list = []
        if row["cameras"]:
            cameras_list = [c.strip() for c in row["cameras"].split(",") if c.strip()]

        user_info = {
            "username": row["username"],
            "role": row["role"],
            "cameras": cameras_list,
        }
        ACTIVE_SESSIONS[token] = user_info

        return {"success": True, "token": token, "user": user_info}
    finally:
        conn.close()

@router.get("/api/customer_info")
def api_customer_info(camera_id: str | None = None):
    state = get_camera_state(camera_id)
    # Finding the largest tracking box or first detected customer
    detected_customer_id = None
    for c in state.latest_customers_payload:
        if c.get("id"):
            detected_customer_id = c["id"]
            break

    if not detected_customer_id:
        return {"status": "no_detection"}

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, detected_customer_id)

        if not customer_info:
            return {"status": "not_found"}

        return {
            "status": "success",
            "id": customer_info["customer_id"],
            "name": customer_info["name"],
            "phone": customer_info.get("phone"),
            "email": customer_info.get("email"),
            "occupation": customer_info.get("occupation"),
            "registered_at": customer_info.get("registered_at"),
            "tenure": customer_info.get("tenure"),
            "loyalty_tier": customer_info.get("loyalty_tier"),
            "total_visits": customer_info.get("total_visits", 0),
            "last_visit": customer_info.get("last_visit"),
            "total_spending": customer_info.get("total_spending", 0),
            "service_category": customer_info["service_category"],
            "service_start_year": customer_info["service_start_year"],
            "customer_tenure_years": customer_info["customer_tenure_years"],
            "customer_type": customer_info["customer_type"],
            "customer_status": customer_info["status"],
            "has_face_embedding": customer_info.get("has_face_embedding"),
            "face_embedding_dim": customer_info.get("face_embedding_dim"),
            "face_embedding_model": customer_info.get("face_embedding_model"),
            "major": customer_info["major"],
            "year": customer_info["year"],
            "starting_year": customer_info["starting_year"],
            "total_attendance": customer_info["total_attendance"],
            "visit_count": customer_info["total_attendance"],
            "phone": customer_info.get("phone"),
            "note": customer_info.get("note"),
            "standing": customer_info["standing"],
            "last_attendance_time": customer_info["last_attendance_time"],
            "image": None,
        }
    finally:
        conn.close()

@router.get("/api/customers_overview")
def api_customers_overview(camera_id: str | None = None):
    state = get_camera_state(camera_id)
    customers = state.latest_customers_payload

    if not customers:
        return {
            "status": "no_detection",
            "customers": [],
            "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
        }

    status = "success" if any(item.get("detected") for item in customers) else "no_detection"
    return {
        "status": status,
        "customers": customers,
        "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
    }

@router.put("/api/customer_profile")
async def api_customer_profile(
    request: Request, authorization: str | None = Header(None)
):
    require_admin(authorization)
    payload = await request.json()
    selected_id = (payload.get("id") or "").strip()
    source_id = (payload.get("source_id") or selected_id or "").strip()
    name = payload.get("name")
    phone = payload.get("phone")
    note = payload.get("note")
    service_category = payload.get("service_category")
    service_start_year = payload.get("service_start_year")
    customer_tenure_years = payload.get("customer_tenure_years")
    loyalty_tier = payload.get("loyalty_tier")

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        writable_id = selected_id
        if writable_id.startswith("T") or writable_id.startswith("GUEST_"):
            writable_id = None

        try:
            final_id, created = create_or_update_customer_profile(
                conn,
                customer_id=writable_id,
                source_id=source_id,
                name=name,
                phone=phone,
                note=note,
                service_category=service_category,
                service_start_year=service_start_year,
                customer_tenure_years=customer_tenure_years,
                loyalty_tier=loyalty_tier,
            )
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

        if source_id.startswith("GUEST_") and final_id != source_id:
            camera_id = "default"
            parts = source_id.split("_")
            if len(parts) >= 3:
                prefix = "_".join(parts[:-2])
                if prefix.startswith("GUEST_"):
                    camera_id = prefix[len("GUEST_") :]
            
            # Send control message to AI worker to promote guest
            r = await get_redis()
            await r.lpush(f"camera_control_{camera_id}", json.dumps({
                "action": "promote_guest",
                "guest_id": source_id,
                "new_id": final_id
            }))
            
            # Send reload encodings command to all cameras
            with CAMERA_STATES_LOCK:
                for cid in CAMERA_STATES.keys():
                    await r.lpush(f"camera_control_{cid}", json.dumps({
                        "action": "reload_embeddings"
                    }))

        customer_info = get_customer_info(conn, final_id)
        if not customer_info:
            return {"success": False, "message": "Customer not found after save"}

        return {
            "success": True,
            "created": created,
            "customer": {
                "id": customer_info["customer_id"],
                "customer_id": customer_info["customer_id"],
                "name": customer_info["name"],
                "phone": customer_info.get("phone"),
                "email": customer_info.get("email"),
                "occupation": customer_info.get("occupation"),
                "registered_at": customer_info.get("registered_at"),
                "tenure": customer_info.get("tenure"),
                "loyalty_tier": customer_info.get("loyalty_tier"),
                "total_visits": customer_info.get("total_visits", 0),
                "last_visit": customer_info.get("last_visit"),
                "total_spending": customer_info.get("total_spending", 0),
                "note": customer_info.get("note"),
                "service_category": customer_info.get("service_category"),
                "service_start_year": customer_info.get("service_start_year"),
                "customer_tenure_years": customer_info.get("customer_tenure_years"),
                "customer_type": customer_info.get("customer_type"),
                "customer_status": customer_info.get("status"),
                "has_face_embedding": customer_info.get("has_face_embedding"),
                "face_embedding_dim": customer_info.get("face_embedding_dim"),
                "face_embedding_model": customer_info.get("face_embedding_model"),
                "visit_count": customer_info.get("total_attendance", 0),
                "last_attendance_time": customer_info.get("last_attendance_time"),
            },
        }
    finally:
        # Invalidate cache command to workers
        r = await get_redis()
        with CAMERA_STATES_LOCK:
            for cid in CAMERA_STATES.keys():
                await r.lpush(f"camera_control_{cid}", json.dumps({
                    "action": "invalidate_cache",
                    "customer_id": final_id
                }))
        conn.close()

@router.post("/api/check_in")
def api_check_in(camera_id: str | None = None):
    state = get_camera_state(camera_id)
    detected_customer_id = None
    for c in state.latest_customers_payload:
        if c.get("id"):
            detected_customer_id = c["id"]
            break

    if not detected_customer_id:
        return {"success": False, "message": "No face detected"}

    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customer_info = get_customer_info(conn, detected_customer_id)
        if not customer_info:
            return {"success": False, "message": "Customer not found"}

        try:
            last_time = datetime.strptime(
                customer_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            last_time = datetime.min

        seconds_elapsed = (datetime.now() - last_time).total_seconds()
        if seconds_elapsed > CHECKIN_COOLDOWN_SECONDS:
            update_attendance(
                conn,
                detected_customer_id,
                customer_info["total_attendance"] + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return {"success": True, "message": "Check-in successful"}

        remaining = int(CHECKIN_COOLDOWN_SECONDS - seconds_elapsed)
        return {"success": False, "message": f"Please wait {remaining}s"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}
    finally:
        conn.close()

@router.post("/api/check_in/{customer_id}")
def api_check_in_by_id(customer_id: str):
    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customer_info = get_customer_info(conn, customer_id)
        if not customer_info:
            return {"success": False, "message": "Customer not found"}

        try:
            last_time = datetime.strptime(
                customer_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            last_time = datetime.min

        seconds_elapsed = (datetime.now() - last_time).total_seconds()
        if seconds_elapsed > CHECKIN_COOLDOWN_SECONDS:
            update_attendance(
                conn,
                customer_id,
                customer_info["total_attendance"] + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return {"success": True, "message": "Check-in successful"}

        remaining = int(CHECKIN_COOLDOWN_SECONDS - seconds_elapsed)
        return {"success": False, "message": f"Please wait {remaining}s"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}
    finally:
        conn.close()

@router.post("/api/process_frame")
async def api_process_frame(request: Request):
    payload = await request.json()
    image_data = payload.get("image")
    camera_id = payload.get("camera_id", "default")
    
    if not image_data:
        return {"success": False, "message": "Invalid frame"}

    if "," in image_data:
        _, image_data = image_data.split(",", 1)

    try:
        raw_bytes = base64.b64decode(image_data)
    except Exception:
        return {"success": False, "message": "Invalid base64 encoding"}

    r = await get_redis()
    opeid = str(uuid.uuid4())
    meta_dict = {
        "opeid": opeid,
        "camera_id": camera_id,
        "timestamp": datetime.now().isoformat()
    }
    
    meta_json = json.dumps(meta_dict).encode("utf-8")
    meta_len = len(meta_json).to_bytes(4, byteorder="big")
    packed_payload = meta_len + meta_json + raw_bytes

    await r.lpush(f"camera_frames_{camera_id}", packed_payload)
    await r.ltrim(f"camera_frames_{camera_id}", 0, 10)
    return {"success": True}

@router.post("/api/promote_guest")
async def api_promote_guest(request: Request, authorization: str | None = Header(None)):
    require_admin(authorization)
    payload = await request.json()
    guest_id = payload.get("guest_id")
    new_id = payload.get("new_id")
    if not guest_id or not new_id:
        return {"success": False, "message": "guest_id and new_id required"}

    camera_id = "default"
    if guest_id.startswith("GUEST_"):
        parts = guest_id.split("_")
        if len(parts) >= 3:
            prefix = "_".join(parts[:-2])
            if prefix.startswith("GUEST_"):
                camera_id = prefix[len("GUEST_") :]

    r = await get_redis()
    await r.lpush(f"camera_control_{camera_id}", json.dumps({
        "action": "promote_guest",
        "guest_id": guest_id,
        "new_id": new_id
    }))
    
    # Send reload encodings command to all cameras
    with CAMERA_STATES_LOCK:
        for cid in CAMERA_STATES.keys():
            await r.lpush(f"camera_control_{cid}", json.dumps({
                "action": "reload_embeddings"
            }))
            
    return {"success": True}

@router.get("/api/customers")
def api_get_all_customers(authorization: str | None = Header(None)):
    require_admin(authorization)
    conn = get_db_connection()
    ensure_schema(conn)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT customer_id as id, name, phone, note, total_visits as total_attendance, last_visit as last_attendance_time
            FROM customers
            """)
        rows = cursor.fetchall()
        customers = [dict(row) for row in rows]
        return {"status": "success", "customers": customers}
    finally:
        conn.close()

@router.get("/api/customer_profile_by_id/{customer_id}")
def api_get_customer_by_id(customer_id: str, authorization: str | None = Header(None)):
    require_admin(authorization)
    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customer_info = get_customer_info(conn, customer_id)
        if not customer_info:
            return {
                "status": "not_found",
                "message": f"Customer '{customer_id}' not found",
            }
        return {
            "status": "success",
            "customer": {
                "id": customer_info["customer_id"],
                "name": customer_info["name"],
                "phone": customer_info.get("phone"),
                "total_attendance": customer_info["total_attendance"],
                "last_attendance_time": customer_info["last_attendance_time"],
                "note": customer_info.get("note"),
            },
        }
    finally:
        conn.close()

@router.websocket("/ws/{session_id}")
async def websocket_camera(websocket: WebSocket, session_id: str):
    await websocket.accept()
    state = get_camera_state(session_id)
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"worker_results_{session_id}")
    await pubsub.subscribe(f"webrtc_signaling_{session_id}")

    # Initialize GuestTrackManager for this session
    track_manager = GuestTrackManager(
        buffer_size=TRACK_BUFFER_SIZE,
        guest_creation_buffer_size=GUEST_CREATION_BUFFER_SIZE,
        similarity_threshold=SIMILARITY_THRESHOLD,
        iou_threshold=TRACK_IOU_THRESHOLD,
        min_bbox_size=MIN_FACE_BBOX_SIZE,
        min_detection_score=MIN_DETECTION_SCORE,
        guest_prefix=f"GUEST_{session_id}",
    )
    
    # Needs to be called once to load from DB
    await asyncio.to_thread(track_manager.load_known_embeddings)

    def process_tracking_and_db(data):
        face_records = data.get("face_records", [])
        timestamp = data.get("timestamp")
        opeid = data.get("opeid")
        camera_id = data.get("camera_id")

        # Convert back lists to np.arrays for embeddings and landmarks
        for rec in face_records:
            if rec.get("embedding") is not None:
                rec["embedding"] = np.array(rec["embedding"], dtype=np.float32)
            if rec.get("landmark") is not None:
                rec["landmark"] = np.array(rec["landmark"], dtype=np.float32)

        tracked_faces = track_manager.process_faces(face_records, frame=None, embedder=None)

        conn = get_db_connection()
        try:
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
                logs.append({
                    "opeid": opeid,
                    "camera_id": camera_id,
                    "customer_id": customer_id,
                    "track_id": track_id,
                    "bbox": (x1, y1, x2, y2),
                    "timestamp": timestamp
                })
            
            if logs:
                bulk_insert_recognize_logs(conn, logs)
                
            return customers
        finally:
            conn.close()

    async def reader():
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    channel = message["channel"].decode("utf-8")
                    data = json.loads(message["data"])
                    if channel == f"worker_results_{session_id}":
                        # Process in thread to avoid blocking asyncio loop
                        customers = await asyncio.to_thread(process_tracking_and_db, data)
                        state.latest_customers_payload = customers
                        frame_size = data.get("frame_size", {"width": FRAME_WIDTH, "height": FRAME_HEIGHT})
                        pubsub_message = {
                            "customers": customers,
                            "frame_size": frame_size
                        }
                        await websocket.send_json(pubsub_message)
                    elif channel == f"webrtc_signaling_{session_id}":
                        if data.get("sender") == "admin":
                            await websocket.send_json(data)
                except Exception as e:
                    import logging
                    logging.error(f"WebSocket reader error: {e}", exc_info=True)

    reader_task = asyncio.create_task(reader())

    try:
        while True:
            try:
                msg = await websocket.receive()
            except Exception:
                break

            if "bytes" in msg:
                data = msg["bytes"]
                if data:
                    state.latest_jpeg = bytes(data)
                    state.last_frame_time = time.time()
                    
                    opeid = str(uuid.uuid4())
                    meta_dict = {
                        "opeid": opeid,
                        "camera_id": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    meta_json = json.dumps(meta_dict).encode("utf-8")
                    meta_len = len(meta_json).to_bytes(4, byteorder="big")
                    
                    packed_payload = meta_len + meta_json + bytes(data)
                    
                    # Push to global camera_frames queue
                    await r.lpush("camera_frames_v2", packed_payload)
                    await r.ltrim("camera_frames_v2", 0, 50)
            elif "text" in msg:
                try:
                    text_data = msg["text"]
                    parsed = json.loads(text_data)
                    parsed["sender"] = "camera"
                    await r.publish(f"webrtc_signaling_{session_id}", json.dumps(parsed))
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        await pubsub.unsubscribe()

@router.get("/api/active_sessions")
def api_active_sessions():
    now = time.time()
    with CAMERA_STATES_LOCK:
        sessions = []
        for cid, state in CAMERA_STATES.items():
            face_count = len(state.latest_customers_payload)
            is_active = (
                state.last_frame_time is not None
                and (now - state.last_frame_time) < 10
            )
            sessions.append({
                "session_id": cid,
                "face_count": face_count,
                "active": bool(is_active),
                "last_frame_time": state.last_frame_time,
            })
    return {"status": "success", "sessions": sessions}

@router.get("/api/camera_snapshot/{session_id}")
def api_camera_snapshot(session_id: str):
    with CAMERA_STATES_LOCK:
        state = CAMERA_STATES.get(session_id)
    if not state or not state.latest_jpeg:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(
        content=state.latest_jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store"},
    )

@router.websocket("/ws/observe/{session_id}")
async def websocket_observe(websocket: WebSocket, session_id: str):
    await websocket.accept()
    with CAMERA_STATES_LOCK:
        if session_id not in CAMERA_STATES:
            await websocket.close(code=4004, reason="Session not found")
            return
        state = CAMERA_STATES[session_id]

    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"camera_results_{session_id}")
    await pubsub.subscribe(f"webrtc_signaling_{session_id}")

    async def reader():
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    channel = message["channel"].decode("utf-8")
                    data = json.loads(message["data"])
                    if channel == f"camera_results_{session_id}":
                        await websocket.send_json(data)
                    elif channel == f"webrtc_signaling_{session_id}":
                        if data.get("sender") == "camera":
                            await websocket.send_json(data)
                except Exception:
                    pass

    reader_task = asyncio.create_task(reader())

    try:
        # Send initial state
        await websocket.send_json({
            "customers": state.latest_customers_payload,
            "frame_size": {
                "width": FRAME_WIDTH,
                "height": FRAME_HEIGHT,
            },
        })
        while True:
            try:
                msg = await websocket.receive_text()
                parsed = json.loads(msg)
                parsed["sender"] = "admin"
                await r.publish(f"webrtc_signaling_{session_id}", json.dumps(parsed))
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        await pubsub.unsubscribe()
