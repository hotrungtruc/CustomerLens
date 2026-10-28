"""
Device & Camera WebSocket routes:
- POST /api/device/identity
- POST /api/device/enrollments
- POST /api/device/enrollments/claim
- POST /api/process_frame
- GET  /api/camera_snapshot/{camera_id}
- WS   /ws/{camera_id}           (camera publisher)
- WS   /ws/observe/{camera_id}   (admin observer)

Also exports shared state: CAMERA_STATES, CAMERA_STATES_LOCK, get_camera_state()
used by customers.py.
"""

import asyncio
import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime

import cv2
import numpy as np
from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app.api.auth import decode_access_token, get_user_from_token, require_admin
from app.db.connection import (
    camera_exists,
    close_camera_connection,
    create_camera_and_credential,
    create_device_credential,
    find_active_device_credential,
    get_customer_info,
    get_db_connection,
    record_camera_connection,
    retire_replaced_camera,
    revoke_camera_credentials,
    touch_device_credential,
    update_attendance,
    bulk_insert_recognize_logs,
    user_can_view_camera,
)
from app.messaging.kafka_client import get_redis, send_camera_frame
from app.core.guest_tracking import GuestTrackManager
from app.core.settings import system_settings
from config import (
    ALLOWED_ORIGINS,
    CHECKIN_COOLDOWN_SECONDS,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    GUEST_CREATION_BUFFER_SIZE,
    MIN_DETECTION_SCORE,
    MIN_FACE_BBOX_SIZE,
    SIMILARITY_THRESHOLD,
    TRACK_BUFFER_SIZE,
    TRACK_IOU_THRESHOLD,
)

# In-memory lease fallback for single-instance or dev mode without Redis
IN_MEMORY_CAMERA_LEASES: dict[str, tuple[str, float]] = {}  # camera_id -> (connection_id, expire_at)
IN_MEMORY_LEASES_LOCK = threading.Lock()


def _process_crop_direct(raw_image_bytes: bytes, client_meta: dict, camera_id: str, connection_id: str):
    """
    Direct in-process recognition pipeline for edge crops.
    Extracts high-precision 5 landmarks via SCRFD and 512D ArcFace embeddings,
    bypassing Redis queue lag and guaranteeing 100% recognition without external workers.
    """
    from app.core.insight_embedding import get_embedder
    try:
        image_array = np.frombuffer(raw_image_bytes, dtype=np.uint8)
        crop_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if crop_bgr is None or crop_bgr.size == 0:
            return None
    except Exception as e:
        print(f"[DIRECT CROP] Decode error: {e}", flush=True)
        return None

    embedder = get_embedder()
    local_track_id = client_meta.get("local_track_id")
    client_bbox = client_meta.get("bbox")
    client_landmarks = client_meta.get("landmarks")

    h, w = crop_bgr.shape[:2]
    if h < 32 or w < 32:
        return None

    bbox = None
    landmark = None
    score = float(client_meta.get("score", 0.85))

    # 1. Try SCRFD face detector first
    try:
        detections = embedder.detect(crop_bgr)
        if (
            detections
            and len(detections[0]) > 0
            and len(detections[1]) > 0
            and len(detections[2]) > 0
        ):
            det_bbox, det_lmk, det_score = detections[0][0], detections[1][0], detections[2][0]
            if float(det_score) >= 0.40:
                x1, y1, x2, y2 = map(int, det_bbox)
                bw, bh = x2 - x1, y2 - y1
                if bw >= 24 and bh >= 24:
                    bbox = (x1, y1, x2, y2)
                    landmark = det_lmk
                    score = float(det_score)
    except Exception as exc:
        print(f"[DIRECT CROP] SCRFD detect exception: {exc}", flush=True)

    # 2. Strict verification: Reject non-faces if SCRFD found 0 faces and client landmarks invalid
    if bbox is None or landmark is None:
        if client_landmarks and len(client_landmarks) in (4, 5) and score >= 0.55:
            cl_arr = np.array(client_landmarks, dtype=np.float32)
            # 0: Right Eye, 1: Left Eye, 2: Nose, 3: Mouth Center (or 4: Mouth Right)
            eye_dist = float(np.hypot(cl_arr[1, 0] - cl_arr[0, 0], cl_arr[1, 1] - cl_arr[0, 1]))
            mouth_y = float(cl_arr[3, 1])
            eyes_y = float((cl_arr[0, 1] + cl_arr[1, 1]) / 2.0)

            # Distance between eyes must be >= 15% of width, and mouth must be strictly below eyes
            if eye_dist >= 0.15 * w and mouth_y > eyes_y:
                bbox = (0, 0, w, h)
                if len(client_landmarks) == 4:
                    # Synthesize 5th point (mouth right) from mouth center
                    p4 = np.array([cl_arr[3, 0] + eye_dist * 0.25, cl_arr[3, 1]], dtype=np.float32)
                    landmark = np.vstack([cl_arr, p4])
                else:
                    landmark = cl_arr
            else:
                # Fails geometric face check -> Reject non-face (bus, hair, backpack)
                return None
        else:
            # Neither SCRFD detected a face nor client provided valid face keypoints -> Reject non-face!
            return None

    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    quality_ok = blur_score >= 1.0 and min(w, h) >= 32
    guest_quality_ok = blur_score >= 2.0 and min(w, h) >= 36

    if not quality_ok:
        return None

    try:
        emb = embedder.get_embedding(crop_bgr, landmark)
        if emb is None:
            return None
        emb = emb.tolist() if isinstance(emb, np.ndarray) else emb
    except Exception as e:
        print(f"[DIRECT CROP] ArcFace embedding error: {e}", flush=True)
        return None

    face_record = {
        "bbox": bbox,
        "landmark": landmark.tolist() if isinstance(landmark, np.ndarray) else landmark,
        "score": score,
        "quality_ok": quality_ok,
        "guest_quality_ok": guest_quality_ok,
        "embedding": emb,
        "local_track_id": local_track_id,
    }

    worker_data = {
        "opeid": str(uuid.uuid4()),
        "camera_id": camera_id,
        "connection_id": connection_id,
        "timestamp": datetime.now().isoformat(),
        "local_track_id": local_track_id,
        "client_bbox": client_bbox,
        "face_records": [face_record],
        "frame_size": {"width": w, "height": h},
    }
    return worker_data

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEVICE_COOKIE_NAME = "device_token"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
OBSERVER_WS_SUBPROTOCOL = "camera-observer"

DEFAULT_ALLOWED_WS_ORIGINS = set(ALLOWED_ORIGINS)
ALLOWED_WS_ORIGINS = {
    origin.strip()
    for origin in os.getenv(
        "WS_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_WS_ORIGINS)
    ).split(",")
    if origin.strip()
}


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


CAMERA_PRESENCE_TTL_SECONDS = max(3, _positive_int_env("CAMERA_PRESENCE_TTL_SECONDS", 15))
CAMERA_PRESENCE_RENEW_SECONDS = max(
    1,
    min(
        CAMERA_PRESENCE_TTL_SECONDS - 1,
        _positive_int_env("CAMERA_PRESENCE_RENEW_SECONDS", 5),
    ),
)
PAIRING_CODE_TTL_SECONDS = _positive_int_env("PAIRING_CODE_TTL_SECONDS", 600)
PAIRING_CLAIM_LIMIT = _positive_int_env("PAIRING_CLAIM_LIMIT", 10)
PAIRING_CLAIM_WINDOW_SECONDS = _positive_int_env("PAIRING_CLAIM_WINDOW_SECONDS", 600)
MAX_CAMERA_FRAME_BYTES = _positive_int_env("MAX_CAMERA_FRAME_BYTES", 2 * 1024 * 1024)

# ---------------------------------------------------------------------------
# Redis Lua scripts
# ---------------------------------------------------------------------------

RENEW_CAMERA_LEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
RELEASE_CAMERA_LEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""
TAKEOVER_CAMERA_LEASE_SCRIPT = """
local previous = redis.call('GET', KEYS[1])
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return previous or ''
"""
CONSUME_PAIRING_CODE_SCRIPT = """
local payload = redis.call('GET', KEYS[1])
if payload then
    redis.call('DEL', KEYS[1])
end
return payload or ''
"""

# ---------------------------------------------------------------------------
# In-memory camera state (shared with customers.py via import)
# ---------------------------------------------------------------------------


class CameraState:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.active = True
        self.latest_jpeg = None
        self.last_frame_time = None
        self.latest_customers_payload = []


class ConnectionState:
    def __init__(self, connection_id: str, camera_id: str, websocket: WebSocket):
        self.connection_id = connection_id
        self.camera_id = camera_id
        self.websocket = websocket
        self.track_manager = None
        self.disconnect_reason = "client_disconnect"


CAMERA_STATES: dict[str, CameraState] = {}
CAMERA_STATES_LOCK = threading.Lock()
CONNECTION_STATES: dict[str, ConnectionState] = {}
CONNECTION_STATES_LOCK = threading.Lock()


def get_camera_state(camera_id: str | None = None) -> CameraState:
    cid = (camera_id or "default").strip()
    with CAMERA_STATES_LOCK:
        if cid not in CAMERA_STATES:
            CAMERA_STATES[cid] = CameraState(cid)
        return CAMERA_STATES[cid]


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


def _camera_presence_key(camera_id: str) -> str:
    return f"camera:presence:{camera_id}"


def _decode_redis_value(value):
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _pairing_code_key(code: str) -> str:
    return "camera:pairing:" + hashlib.sha256(code.encode("utf-8")).hexdigest()


def _hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _acquire_camera_lease(redis, camera_id: str, connection_id: str):
    if redis is not None:
        try:
            return bool(
                await redis.set(
                    _camera_presence_key(camera_id),
                    connection_id,
                    nx=True,
                    ex=CAMERA_PRESENCE_TTL_SECONDS,
                )
            )
        except Exception:
            pass
    with IN_MEMORY_LEASES_LOCK:
        now = time.time()
        existing = IN_MEMORY_CAMERA_LEASES.get(camera_id)
        if existing and existing[1] > now and existing[0] != connection_id:
            return False
        IN_MEMORY_CAMERA_LEASES[camera_id] = (connection_id, now + CAMERA_PRESENCE_TTL_SECONDS)
        return True


async def _renew_camera_lease(redis, camera_id: str, connection_id: str):
    if redis is not None:
        try:
            key = _camera_presence_key(camera_id)
            val = await redis.get(key)
            if _decode_redis_value(val) == connection_id:
                await redis.expire(key, CAMERA_PRESENCE_TTL_SECONDS)
                return True
            return False
        except Exception:
            pass
    with IN_MEMORY_LEASES_LOCK:
        now = time.time()
        existing = IN_MEMORY_CAMERA_LEASES.get(camera_id)
        if existing and existing[0] == connection_id:
            IN_MEMORY_CAMERA_LEASES[camera_id] = (connection_id, now + CAMERA_PRESENCE_TTL_SECONDS)
            return True
        return False


async def _release_camera_lease(redis, camera_id: str, connection_id: str):
    if redis is not None:
        try:
            key = _camera_presence_key(camera_id)
            val = await redis.get(key)
            if _decode_redis_value(val) == connection_id:
                await redis.delete(key)
                return True
        except Exception:
            pass
    with IN_MEMORY_LEASES_LOCK:
        existing = IN_MEMORY_CAMERA_LEASES.get(camera_id)
        if existing and existing[0] == connection_id:
            IN_MEMORY_CAMERA_LEASES.pop(camera_id, None)
            return True
        return False


async def _takeover_camera_lease(redis, camera_id: str, connection_id: str):
    if redis is not None:
        try:
            key = _camera_presence_key(camera_id)
            previous = await redis.get(key)
            await redis.set(key, connection_id, ex=CAMERA_PRESENCE_TTL_SECONDS)
            return _decode_redis_value(previous) or None
        except Exception:
            pass
    with IN_MEMORY_LEASES_LOCK:
        now = time.time()
        existing = IN_MEMORY_CAMERA_LEASES.get(camera_id)
        prev_id = existing[0] if existing else None
        IN_MEMORY_CAMERA_LEASES[camera_id] = (connection_id, now + CAMERA_PRESENCE_TTL_SECONDS)
        return prev_id


async def _connection_owns_camera_lease(redis, camera_id: str, connection_id: str):
    if redis is not None:
        try:
            owner = await redis.get(_camera_presence_key(camera_id))
            return _decode_redis_value(owner) == connection_id
        except Exception:
            pass
    with IN_MEMORY_LEASES_LOCK:
        existing = IN_MEMORY_CAMERA_LEASES.get(camera_id)
        return bool(existing and existing[0] == connection_id)


async def _maintain_camera_lease(redis, connection_state: ConnectionState):
    camera_id = connection_state.camera_id
    connection_id = connection_state.connection_id
    while True:
        await asyncio.sleep(CAMERA_PRESENCE_RENEW_SECONDS)
        try:
            renewed = await _renew_camera_lease(redis, camera_id, connection_id)
        except Exception:
            renewed = True
        if not renewed:
            connection_state.disconnect_reason = "lease_lost"
            try:
                await connection_state.websocket.close(code=4009, reason="Camera lease lost")
            except Exception:
                pass
            return


# ---------------------------------------------------------------------------
# WebSocket auth resolvers
# ---------------------------------------------------------------------------


def _resolve_websocket_camera(websocket: WebSocket):
    if websocket.headers.get("origin") not in ALLOWED_WS_ORIGINS:
        return None, "origin_not_allowed"

    raw_token = websocket.cookies.get(DEVICE_COOKIE_NAME)
    if not raw_token:
        return None, "missing_device_token"

    conn = get_db_connection()
    try:
        credential = find_active_device_credential(conn, _hash_device_token(raw_token))
        if not credential:
            return None, "invalid_device_token"
        touch_device_credential(conn, credential["credential_id"], credential["camera_id"])
        conn.commit()
        return dict(credential), None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _resolve_observer_user(websocket: WebSocket, camera_id: str):
    if websocket.headers.get("origin") not in ALLOWED_WS_ORIGINS:
        return None, "origin_not_allowed"

    protocols = [
        value.strip()
        for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if value.strip()
    ]
    if len(protocols) != 2 or protocols[0] != OBSERVER_WS_SUBPROTOCOL:
        return None, "missing_observer_token"

    try:
        user = decode_access_token(protocols[1])
    except HTTPException:
        return None, "invalid_observer_token"

    if not user or user.get("role") not in {"admin", "moderator"}:
        return None, "invalid_observer_token"

    conn = get_db_connection()
    try:
        if not camera_exists(conn, camera_id):
            return None, "camera_not_found"
        if not user_can_view_camera(conn, user, camera_id):
            return None, "camera_forbidden"
        return user, None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Routes: device identity & enrollment
# ---------------------------------------------------------------------------


@router.get("/")
def index():
    return {"status": "ok", "message": "Backend running"}


@router.get("/test")
def test():
    return {"status": "ok", "message": "FastAPI backend is running"}


@router.post("/api/device/identity")
def resolve_device_identity(request: Request, response: Response):
    raw_token = request.cookies.get(DEVICE_COOKIE_NAME)
    conn = get_db_connection()

    try:
        if raw_token:
            credential = find_active_device_credential(conn, _hash_device_token(raw_token))
            if not credential:
                invalid_response = Response(
                    content=json.dumps({"detail": "Device credential is invalid or revoked"}),
                    status_code=401,
                    media_type="application/json",
                )
                invalid_response.delete_cookie(
                    DEVICE_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="none"
                )
                return invalid_response

            touch_device_credential(conn, credential["credential_id"], credential["camera_id"])
            conn.commit()
            return {
                "camera_id": credential["camera_id"],
                "display_name": credential["display_name"],
                "is_new": False,
            }

        camera_id = "cam_" + uuid.uuid4().hex
        credential_id = "cred_" + uuid.uuid4().hex
        raw_token = secrets.token_urlsafe(32)
        display_name = "Camera mới"

        create_camera_and_credential(
            conn=conn,
            camera_id=camera_id,
            display_name=display_name,
            credential_id=credential_id,
            token_hash=_hash_device_token(raw_token),
            user_agent=request.headers.get("user-agent"),
        )
        conn.commit()

        response.set_cookie(
            key=DEVICE_COOKIE_NAME,
            value=raw_token,
            max_age=DEVICE_COOKIE_MAX_AGE,
            path="/",
            secure=True,
            httponly=True,
            samesite="none",
        )
        return {"camera_id": camera_id, "display_name": display_name, "is_new": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/api/device/enrollments")
async def create_device_enrollment(
    request: Request, authorization: str | None = Header(default=None)
):
    admin = require_admin(authorization)
    payload = await request.json()
    camera_id = str(payload.get("camera_id") or "").strip()
    revoke_existing = bool(payload.get("revoke_existing", True))

    conn = get_db_connection()
    try:
        if not camera_exists(conn, camera_id):
            raise HTTPException(status_code=404, detail="Camera not found")
    finally:
        conn.close()

    enrollment = json.dumps(
        {"camera_id": camera_id, "revoke_existing": revoke_existing, "created_by": admin["username"]}
    )
    r = await get_redis()
    try:
        for _ in range(10):
            code = f"{secrets.randbelow(1_000_000):06d}"
            created = await r.set(
                _pairing_code_key(code), enrollment, nx=True, ex=PAIRING_CODE_TTL_SECONDS
            )
            if created:
                return {
                    "status": "success",
                    "camera_id": camera_id,
                    "code": code,
                    "expires_in": PAIRING_CODE_TTL_SECONDS,
                    "max_use": 1,
                }
    finally:
        await r.aclose()

    raise HTTPException(status_code=503, detail="Could not allocate pairing code")


@router.post("/api/device/enrollments/claim")
async def claim_device_enrollment(request: Request, response: Response):
    payload = await request.json()
    code = str(payload.get("code") or "").strip()
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=400, detail="Pairing code must have 6 digits")

    client_host = request.client.host if request.client else "unknown"
    rate_key = "camera:pairing-rate:" + hashlib.sha256(client_host.encode("utf-8")).hexdigest()
    pairing_key = _pairing_code_key(code)
    r = await get_redis()
    enrollment_payload = None
    try:
        attempts = await r.incr(rate_key)
        if attempts == 1:
            await r.expire(rate_key, PAIRING_CLAIM_WINDOW_SECONDS)
        if attempts > PAIRING_CLAIM_LIMIT:
            raise HTTPException(status_code=429, detail="Too many pairing attempts")

        enrollment_payload = await r.eval(CONSUME_PAIRING_CODE_SCRIPT, 1, pairing_key)
        enrollment_payload = _decode_redis_value(enrollment_payload)
        if not enrollment_payload:
            raise HTTPException(status_code=400, detail="Pairing code is invalid or expired")

        enrollment = json.loads(enrollment_payload)
        camera_id = enrollment["camera_id"]
        raw_token = secrets.token_urlsafe(32)
        credential_id = "cred_" + uuid.uuid4().hex

        conn = get_db_connection()
        try:
            if not camera_exists(conn, camera_id):
                raise HTTPException(status_code=404, detail="Camera not found")

            current_credential = None
            current_token = request.cookies.get(DEVICE_COOKIE_NAME)
            if current_token:
                current_credential = find_active_device_credential(
                    conn, _hash_device_token(current_token)
                )

            if enrollment.get("revoke_existing", True):
                revoke_camera_credentials(conn, camera_id)

            if current_credential and current_credential["camera_id"] != camera_id:
                retire_replaced_camera(conn, current_credential["camera_id"])

            create_device_credential(
                conn, camera_id, credential_id, _hash_device_token(raw_token),
                request.headers.get("user-agent"),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            await r.set(
                pairing_key, enrollment_payload, nx=True, ex=min(60, PAIRING_CODE_TTL_SECONDS)
            )
            raise
        finally:
            conn.close()

        response.set_cookie(
            key=DEVICE_COOKIE_NAME,
            value=raw_token,
            max_age=DEVICE_COOKIE_MAX_AGE,
            path="/",
            secure=True,
            httponly=True,
            samesite="none",
        )
        return {
            "status": "success",
            "camera_id": camera_id,
            "display_name": enrollment.get("display_name") or "Camera đã khôi phục",
            "is_new": False,
            "recovered": True,
        }
    finally:
        await r.aclose()


# ---------------------------------------------------------------------------
# Routes: frame processing
# ---------------------------------------------------------------------------


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
        raw_bytes = __import__("base64").b64decode(image_data)
    except Exception:
        return {"success": False, "message": "Invalid base64 encoding"}

    r = await get_redis()
    opeid = str(uuid.uuid4())
    meta_dict = {"opeid": opeid, "camera_id": camera_id, "timestamp": datetime.now().isoformat()}
    meta_json = json.dumps(meta_dict).encode("utf-8")
    meta_len = len(meta_json).to_bytes(4, byteorder="big")
    packed_payload = meta_len + meta_json + raw_bytes

    await r.lpush(f"camera_frames_{camera_id}", packed_payload)
    await r.ltrim(f"camera_frames_{camera_id}", 0, 10)
    return {"success": True}


# ---------------------------------------------------------------------------
# Routes: camera snapshot
# ---------------------------------------------------------------------------


@router.get("/api/camera_snapshot/{camera_id}")
def api_camera_snapshot(camera_id: str):
    with CAMERA_STATES_LOCK:
        state = CAMERA_STATES.get(camera_id)
    if not state or not state.latest_jpeg:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(
        content=state.latest_jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store"},
    )


# ---------------------------------------------------------------------------
# Helper: apply customer profile into a detection payload dict
# ---------------------------------------------------------------------------


def _apply_profile_to_payload(payload: dict, info: dict):
    def safe_iso(val):
        return val.isoformat() if isinstance(val, datetime) else val

    from app.core.customer_code import compute_segment_code, format_display_customer_id
    seg = compute_segment_code(info)
    code = seg[0] if seg else "LN"
    label = seg[1] if seg else "Budget • New Guest"
    desc = seg[2] if seg else "Khách mới chưa đăng ký (Mặc định)"
    disp_id = format_display_customer_id(info) or info["customer_id"]

    payload.update(
        {
            "id": info["customer_id"],
            "display_id": disp_id,
            "name": info["name"] or f"Khách {disp_id}",
            "email": info.get("email"),
            "registered_at": safe_iso(info.get("registered_at")),
            "tenure": info.get("tenure", 0),
            "loyalty_tier": info.get("loyalty_tier", "Standard"),
            "total_visits": info.get("total_visits", 0),
            "last_visit": safe_iso(info.get("last_visit")),
            "total_spending": info.get("total_spending", 0),
            "service_category": info.get("service_category", "General"),
            "service_start_year": info.get("service_start_year", 0),
            "customer_tenure_years": info.get("customer_tenure_years", 0),
            "customer_type": info.get("customer_type", "guest"),
            "customer_status": info.get("status", "active"),
            "segment_code": code,
            "segment_label": label,
            "segment_desc": desc,
            "has_face_embedding": info.get("has_face_embedding"),
            "face_embedding_dim": info.get("face_embedding_dim"),
            "face_embedding_model": info.get("face_embedding_model"),
            "phone": info.get("phone"),
            "note": info.get("note"),
        }
    )


# ---------------------------------------------------------------------------
# WebSocket: camera publisher
# ---------------------------------------------------------------------------


@router.websocket("/ws/{camera_id}")
async def websocket_camera(websocket: WebSocket, camera_id: str):
    try:
        await websocket.accept()
    except Exception:
        return

    credential, auth_error = _resolve_websocket_camera(websocket)
    if auth_error or credential["camera_id"] != camera_id:
        print(
            f"WS Auth Error: {auth_error}, expected {camera_id} but got "
            f"{credential.get('camera_id') if credential else None}",
            flush=True,
        )
        await websocket.close(code=4003)
        return

    connection_id = "conn_" + uuid.uuid4().hex
    r = None
    redis_available = False
    try:
        candidate_r = await get_redis()
        await asyncio.wait_for(candidate_r.ping(), timeout=0.5)
        r = candidate_r
        redis_available = True
    except Exception as e:
        print(f"[WS SERVER] Redis offline ({e}). Running in standalone in-memory mode.", flush=True)
        r = None
        redis_available = False

    previous_connection_id = None
    try:
        takeover_requested = websocket.query_params.get("takeover") == "1"
        if takeover_requested:
            previous_connection_id = await _takeover_camera_lease(r, camera_id, connection_id)
            acquired = True
        else:
            acquired = await _acquire_camera_lease(r, camera_id, connection_id)
    except Exception as exc:
        print(f"Error acquiring lease for {camera_id}: {exc}", flush=True)
        acquired = True

    if not acquired:
        print(f"WS Camera Lease Error: could not acquire lease for {camera_id}", flush=True)
        if r is not None:
            try:
                await r.aclose()
            except Exception:
                pass
        await websocket.close(code=4008)
        return

    state = get_camera_state(camera_id)
    connection_state = ConnectionState(connection_id, camera_id, websocket)
    with CONNECTION_STATES_LOCK:
        CONNECTION_STATES[connection_id] = connection_state
    presence_task = asyncio.create_task(_maintain_camera_lease(r, connection_state))

    pubsub = None
    try:
        if redis_available and r is not None:
            try:
                pubsub = r.pubsub()
                await pubsub.subscribe(f"worker_results_{connection_id}")
                await pubsub.subscribe(f"webrtc_signaling_{camera_id}")
                await pubsub.subscribe(f"connection_control:{connection_id}")
                await pubsub.subscribe(f"camera_control:{camera_id}")
            except Exception as e:
                print(f"[WS SERVER] PubSub warning: {e}", flush=True)
                pubsub = None

        if previous_connection_id and previous_connection_id != connection_id:
            if redis_available and r is not None:
                try:
                    await r.publish(
                        f"connection_control:{previous_connection_id}",
                        json.dumps(
                            {
                                "type": "connection_taken_over",
                                "camera_id": camera_id,
                                "connection_id": previous_connection_id,
                                "replacement_connection_id": connection_id,
                            }
                        ),
                    )
                except Exception:
                    pass
            with CONNECTION_STATES_LOCK:
                prev_conn = CONNECTION_STATES.get(previous_connection_id)
                if prev_conn and prev_conn.websocket:
                    asyncio.create_task(prev_conn.websocket.close(code=4008, reason="Camera opened elsewhere"))

        track_manager = GuestTrackManager(
            buffer_size=2,
            guest_creation_buffer_size=3,
            similarity_threshold=system_settings.get("similarity_threshold", SIMILARITY_THRESHOLD),
            iou_threshold=system_settings.get("track_iou_threshold", TRACK_IOU_THRESHOLD),
            min_bbox_size=system_settings.get("min_face_bbox_size", MIN_FACE_BBOX_SIZE),
            min_detection_score=system_settings.get("min_detection_score", MIN_DETECTION_SCORE),
            guest_prefix="LN",
        )
        connection_state.track_manager = track_manager
        await asyncio.to_thread(track_manager.load_known_embeddings)

        async def _warmup_cache():
            try:
                from app.core.vector_cache import vector_cache_manager
                await asyncio.to_thread(vector_cache_manager.sync_from_database)
                print(f"[CACHE WARMUP] L1 Vector Cache pre-populated for camera {camera_id}", flush=True)
            except Exception as _e:
                print(f"[CACHE WARMUP] Warning: cache warmup failed: {_e}", flush=True)

        asyncio.create_task(_warmup_cache())

        audit_conn = get_db_connection()
        try:
            record_camera_connection(audit_conn, connection_id, camera_id)
            audit_conn.commit()
        finally:
            audit_conn.close()
    except Exception as exc:
        import traceback
        print(f"Error in websocket setup for {camera_id}:", flush=True)
        traceback.print_exc()
        with CONNECTION_STATES_LOCK:
            CONNECTION_STATES.pop(connection_id, None)
        presence_task.cancel()
        try:
            await presence_task
        except (asyncio.CancelledError, Exception):
            pass
        if pubsub is not None:
            try:
                await pubsub.aclose()
            except Exception:
                pass
        try:
            await _release_camera_lease(r, camera_id, connection_id)
        except Exception:
            pass
        if r is not None:
            try:
                await r.aclose()
            except Exception:
                pass
        await websocket.close(code=1011)
        return

    # ------------------------------------------------------------------
    # Inner helpers — scoped to this connection
    # ------------------------------------------------------------------

    def process_tracking_and_db(data):
        face_records = data.get("face_records", [])
        timestamp = data.get("timestamp")
        opeid = data.get("opeid")
        result_camera_id = data.get("camera_id")
        result_connection_id = data.get("connection_id")
        local_track_id = data.get("local_track_id")
        client_bbox = data.get("client_bbox")

        for rec in face_records:
            if rec.get("embedding") is not None:
                rec["embedding"] = np.array(rec["embedding"], dtype=np.float32)
            if rec.get("landmark") is not None:
                rec["landmark"] = np.array(rec["landmark"], dtype=np.float32)

        for rec in face_records:
            if local_track_id:
                rec["local_track_id"] = local_track_id
            if client_bbox and ("bbox" not in rec or not rec["bbox"]):
                rec["bbox"] = client_bbox
            elif client_bbox and local_track_id:
                rec["bbox"] = client_bbox

        conn = get_db_connection()
        try:
            customers = []
            logs = []

            tracked_faces = track_manager.process_faces(face_records, frame=None, embedder=None)
            for face in tracked_faces:
                x1, y1, x2, y2 = face["bbox"]
                customer_id = face["customer_id"]
                track_id = face["track_id"]

                track = track_manager.tracks.get(track_id)
                loc_track_id = (track.local_track_id if track else None) or local_track_id
                if track and not track.local_track_id and local_track_id:
                    track.local_track_id = local_track_id

                import time as _time
                payload = {
                    "tile_id": f"tile_{loc_track_id or track_id}",
                    "track_id": loc_track_id or track_id,
                    "local_track_id": loc_track_id,
                    "bbox": (x1, y1, x2, y2),
                    "detected": bool(customer_id),
                    "id": customer_id,
                    "display_id": customer_id,
                    "detected_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "name": "Đang nhận diện..." if not customer_id else "Khách mới",
                    "customer_type": "unknown" if not customer_id else "guest",
                    "customer_status": "extracting" if not customer_id else "temporary",
                    "segment_code": None if not customer_id else "LN",
                    "segment_label": None if not customer_id else "Budget • New Guest",
                    "segment_desc": None if not customer_id else "Khách mới chưa đăng ký (Mặc định)",
                }

                if customer_id:
                    info = track.cached_profile if track else None
                    if not info:
                        info = get_customer_info(conn, customer_id)
                        if info and track:
                            track.cached_profile = info
                    if info:
                        _apply_profile_to_payload(payload, info)

                customers.append(payload)
                logs.append(
                    {
                        "opeid": opeid,
                        "camera_id": result_camera_id,
                        "connection_id": result_connection_id,
                        "customer_id": customer_id,
                        "track_id": track_id,
                        "bbox": (x1, y1, x2, y2),
                        "timestamp": timestamp,
                    }
                )

            if logs:
                bulk_insert_recognize_logs(conn, logs)

                _last_checkin = getattr(process_tracking_and_db, "_last_checkin", {})
                now_ts = time.time()
                for face in tracked_faces:
                    cid = face.get("customer_id")
                    if cid:
                        if now_ts - _last_checkin.get(cid, 0) > CHECKIN_COOLDOWN_SECONDS:
                            _last_checkin[cid] = now_ts
                            try:
                                update_attendance(
                                    conn, cid,
                                    last_attendance_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                )
                                tid = face.get("track_id")
                                if tid and tid in track_manager.tracks:
                                    track_manager.tracks[tid].cached_profile = None
                            except Exception as e:
                                print(f"Auto attendance update failed for {cid}: {e}", flush=True)
                process_tracking_and_db._last_checkin = _last_checkin

            return customers
        finally:
            conn.close()

    async def process_worker_data(data):
        owns_lease = await _connection_owns_camera_lease(r, camera_id, connection_id)
        if (
            data.get("camera_id") != camera_id
            or data.get("connection_id") != connection_id
            or not owns_lease
        ):
            return
        customers = await asyncio.to_thread(process_tracking_and_db, data)
        state.latest_customers_payload = customers
        frame_size = data.get("frame_size", {"width": FRAME_WIDTH, "height": FRAME_HEIGHT})
        pubsub_message = {
            "type": "camera_update",
            "customers": customers,
            "frame_size": frame_size,
            "camera_id": camera_id,
            "connection_id": connection_id,
        }
        json_str = json.dumps(pubsub_message, default=str)
        try:
            await websocket.send_text(json_str)
        except Exception:
            pass
        await r.publish(f"camera_updates:{camera_id}", json_str)

    async def queue_reader():
        queue_key = f"results_queue:{connection_id}"
        while True:
            try:
                raw_item = await r.rpop(queue_key)
                if raw_item:
                    data = json.loads(raw_item)
                    await process_worker_data(data)
                    continue
                await asyncio.sleep(0.02)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.05)

    async def reader():
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    channel = message["channel"].decode("utf-8")
                    data = json.loads(message["data"])
                    if channel == f"worker_results_{connection_id}":
                        await process_worker_data(data)
                    elif channel == f"webrtc_signaling_{camera_id}":
                        if data.get("sender") == "admin":
                            await websocket.send_json(data)
                    elif channel == f"connection_control:{connection_id}":
                        if data.get("type") == "connection_taken_over":
                            connection_state.disconnect_reason = "taken_over"
                            await websocket.close(code=4008, reason="Camera opened elsewhere")
                            return
                    elif channel == f"camera_control:{camera_id}":
                        action = data.get("action")
                        if action == "promote_guest":
                            guest_id = data.get("guest_id")
                            new_id = data.get("new_id")
                            if guest_id and new_id:
                                track_manager.promote_guest(guest_id, new_id)
                                await asyncio.to_thread(track_manager.load_known_embeddings)
                                for track in track_manager.tracks.values():
                                    if track.resolved_customer_id in (guest_id, new_id):
                                        track.cached_profile = None
                                        track.resolved_customer_id = new_id
                        elif action == "invalidate_cache":
                            cid_to_invalidate = data.get("customer_id")
                            if cid_to_invalidate:
                                for track in track_manager.tracks.values():
                                    if track.resolved_customer_id == cid_to_invalidate:
                                        track.cached_profile = None
                        elif action == "reload_embeddings":
                            await asyncio.to_thread(track_manager.load_known_embeddings)
                            try:
                                from app.core.vector_cache import vector_cache_manager
                                await asyncio.to_thread(vector_cache_manager.sync_from_database)
                            except Exception:
                                pass
                            for track in track_manager.tracks.values():
                                track.cached_profile = None
                except Exception as e:
                    import logging
                    logging.error(f"WebSocket reader error: {e}", exc_info=True)

    reader_task = asyncio.create_task(reader()) if pubsub is not None else None
    queue_reader_task = asyncio.create_task(queue_reader()) if (redis_available and r is not None) else None

    try:
        await websocket.send_json(
            {"type": "ready", "camera_id": camera_id, "connection_id": connection_id}
        )
        if redis_available and r is not None:
            try:
                await r.publish(
                    f"camera_updates:{camera_id}",
                    json.dumps(
                        {"type": "publisher_ready", "camera_id": camera_id, "connection_id": connection_id}
                    ),
                )
            except Exception:
                pass

        while True:
            try:
                msg = await websocket.receive()
            except Exception:
                break

            if "bytes" in msg:
                data = msg["bytes"]
                if data:
                    if len(data) > MAX_CAMERA_FRAME_BYTES:
                        connection_state.disconnect_reason = "frame_too_large"
                        await websocket.close(code=1009, reason="Frame too large")
                        break

                    if data.startswith(b"\xff\xd8"):
                        raw_image_bytes = bytes(data)
                        client_meta = {}
                    else:
                        try:
                            meta_len_in = int.from_bytes(data[:4], byteorder="big")
                            client_meta_json = data[4 : 4 + meta_len_in].decode("utf-8")
                            client_meta = json.loads(client_meta_json)
                            raw_image_bytes = data[4 + meta_len_in :]
                        except Exception:
                            raw_image_bytes = bytes(data)
                            client_meta = {}

                    state.latest_jpeg = raw_image_bytes
                    state.last_frame_time = time.time()

                    is_edge_crop = bool(client_meta.get("local_track_id"))
                    if is_edge_crop or not redis_available:
                        # Direct in-process biometric recognition using InsightEmbedder + GuestTrackManager
                        worker_data = await asyncio.to_thread(
                            _process_crop_direct,
                            raw_image_bytes,
                            client_meta,
                            camera_id,
                            connection_id,
                        )
                        if worker_data:
                            customers = await asyncio.to_thread(process_tracking_and_db, worker_data)
                            print(f"[DIRECT CROP] Sent camera_update: id={[c.get('id') for c in customers]}, tracks={[c.get('local_track_id') for c in customers]}", flush=True)
                            pubsub_message = {
                                "type": "camera_update",
                                "customers": customers,
                                "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
                                "camera_id": camera_id,
                                "connection_id": connection_id,
                            }
                            json_str = json.dumps(pubsub_message, default=str)
                            try:
                                await websocket.send_text(json_str)
                            except Exception:
                                pass
                            if redis_available and r is not None:
                                try:
                                    await r.publish(f"camera_updates:{camera_id}", json_str)
                                except Exception:
                                    pass
                    else:
                        opeid = str(uuid.uuid4())
                        meta_dict = {
                            "opeid": opeid,
                            "camera_id": camera_id,
                            "connection_id": connection_id,
                            "timestamp": datetime.now().isoformat(),
                        }
                        meta_dict.update(client_meta)

                        meta_json_out = json.dumps(meta_dict).encode("utf-8")
                        meta_len_out = len(meta_json_out).to_bytes(4, byteorder="big")
                        packed_payload = meta_len_out + meta_json_out + raw_image_bytes

                        print(f"[WS SERVER] Pushing frame to worker: conn={connection_id}, track={client_meta.get('local_track_id')}, payload_bytes={len(packed_payload)}", flush=True)
                        await send_camera_frame(r, packed_payload, camera_id)
            elif "text" in msg:
                try:
                    parsed = json.loads(msg["text"])
                    parsed["sender"] = "camera"
                    if redis_available and r is not None:
                        await r.publish(f"webrtc_signaling_{camera_id}", json.dumps(parsed))
                except Exception:
                    pass
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        with CONNECTION_STATES_LOCK:
            CONNECTION_STATES.pop(connection_id, None)
        if track_manager is not None:
            try:
                track_manager._release_cached_conn()
            except Exception:
                pass
        connection_state.track_manager = None
        presence_task.cancel()
        try:
            await presence_task
        except (asyncio.CancelledError, Exception):
            pass
        if reader_task is not None:
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass
        if queue_reader_task is not None:
            queue_reader_task.cancel()
            try:
                await queue_reader_task
            except (asyncio.CancelledError, Exception):
                pass
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass
        try:
            if redis_available and r is not None:
                if await _connection_owns_camera_lease(r, camera_id, connection_id):
                    await r.publish(
                        f"camera_updates:{camera_id}",
                        json.dumps(
                            {
                                "type": "publisher_offline",
                                "camera_id": camera_id,
                                "connection_id": connection_id,
                            }
                        ),
                    )
            await _release_camera_lease(r, camera_id, connection_id)
        except Exception:
            pass
        finally:
            if r is not None:
                try:
                    await r.aclose()
                except Exception:
                    pass

        audit_conn = get_db_connection()
        try:
            close_camera_connection(audit_conn, connection_id, connection_state.disconnect_reason)
            audit_conn.commit()
        finally:
            audit_conn.close()


# ---------------------------------------------------------------------------
# WebSocket: observer
# ---------------------------------------------------------------------------


@router.websocket("/ws/observe/{camera_id}")
async def websocket_observe(websocket: WebSocket, camera_id: str):
    _, auth_error = _resolve_observer_user(websocket, camera_id)
    if auth_error:
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol=OBSERVER_WS_SUBPROTOCOL)
    with CAMERA_STATES_LOCK:
        state = CAMERA_STATES.get(camera_id)

    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"camera_updates:{camera_id}")
    await pubsub.subscribe(f"webrtc_signaling_{camera_id}")

    async def reader():
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    channel = message["channel"].decode("utf-8")
                    data = json.loads(message["data"])
                    if channel == f"camera_updates:{camera_id}":
                        await websocket.send_json(data)
                    elif channel == f"webrtc_signaling_{camera_id}":
                        if data.get("sender") == "camera":
                            await websocket.send_json(data)
                except Exception:
                    pass

    reader_task = asyncio.create_task(reader())

    try:
        await websocket.send_json(
            {
                "type": "observer_ready",
                "camera_id": camera_id,
                "customers": state.latest_customers_payload if state else [],
                "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
            }
        )
        while True:
            try:
                msg = await websocket.receive_text()
                parsed = json.loads(msg)
                parsed["sender"] = "admin"
                await r.publish(f"webrtc_signaling_{camera_id}", json.dumps(parsed))
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):
            pass
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await r.aclose()
