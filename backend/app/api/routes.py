import asyncio
import base64
import hashlib
import json
import os
import math
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
from aiokafka import AIOKafkaProducer

kafka_producer: AIOKafkaProducer = None
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
_reconnect_task: asyncio.Task = None

async def _kafka_reconnect_loop():
    global kafka_producer
    while True:
        await asyncio.sleep(5)
        if kafka_producer is not None:
            break
        try:
            print(f"[RETRY] Attempting to reconnect to Redpanda at {KAFKA_BOOTSTRAP_SERVERS}...", flush=True)
            producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
            await producer.start()
            kafka_producer = producer
            print(f"[SUCCESS] Reconnected to Redpanda at {KAFKA_BOOTSTRAP_SERVERS}!", flush=True)
            break
        except Exception as e:
            print(f"[RETRY FAILED] Redpanda unavailable: {e}", flush=True)

def _trigger_kafka_reconnect():
    global _reconnect_task, kafka_producer
    kafka_producer = None
    if _reconnect_task is None or _reconnect_task.done():
        try:
            loop = asyncio.get_running_loop()
            _reconnect_task = loop.create_task(_kafka_reconnect_loop())
        except RuntimeError:
            pass

async def init_kafka_producer():
    global kafka_producer
    try:
        kafka_producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        await kafka_producer.start()
        print(f"Connected to Redpanda at {KAFKA_BOOTSTRAP_SERVERS}", flush=True)
    except Exception as e:
        print(f"Failed to connect to Redpanda ({e}). Launching background auto-reconnect...", flush=True)
        _trigger_kafka_reconnect()

async def close_kafka_producer():
    global kafka_producer, _reconnect_task
    if _reconnect_task and not _reconnect_task.done():
        _reconnect_task.cancel()
    if kafka_producer:
        await kafka_producer.stop()
        kafka_producer = None

async def send_camera_frame(redis_conn, packed_payload: bytes, camera_id: str):
    """
    Publishes camera frame to Redpanda. If Redpanda is down or errors out,
    automatically falls back to Redis queue (camera_frames_fallback).
    """
    global kafka_producer
    sent_via_kafka = False
    if kafka_producer is not None:
        try:
            await kafka_producer.send_and_wait("camera_frames", packed_payload)
            sent_via_kafka = True
        except Exception as e:
            print(f"[FALLBACK WARNING] Redpanda send error ({e}). Switching to Redis queue fallback.", flush=True)
            _trigger_kafka_reconnect()

    if not sent_via_kafka:
        try:
            await redis_conn.lpush("camera_frames_fallback", packed_payload)
            await redis_conn.ltrim("camera_frames_fallback", 0, 50)
        except Exception as e:
            print(f"[ERROR] Redis fallback frame push error: {e}", flush=True)

import jwt
from datetime import datetime, timedelta, timezone
from config import JWT_ALGORITHM, JWT_EXPIRATION_MINUTES, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_pool = aioredis.ConnectionPool.from_url(REDIS_URL, max_connections=200)

async def get_redis():
    return aioredis.Redis(connection_pool=redis_pool)

def create_access_token(user_info: dict) -> str:
    """Create a signed RS256 JWT token using private RSA key."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_info.get("id")),
        "id": user_info.get("id"),
        "username": user_info.get("username"),
        "role": user_info.get("role"),
        "cameras": user_info.get("cameras", []),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRATION_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_PRIVATE_KEY, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    """Statelessly decode and verify an RS256 JWT token using public RSA key."""
    try:
        payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Session expired or invalid")

def get_user_from_token(authorization: str | None = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    token = authorization.split(" ")[1].strip()
    return decode_access_token(token)

def require_admin(authorization: str | None = None):
    user = get_user_from_token(authorization)
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403, detail="Unauthorized action: Admin role required"
        )
    return user


def revoke_user_sessions(user_id: int):
    # In stateless RS256 JWT mode, tokens naturally expire via 'exp' claim.
    pass

from app.db.connection import (create_or_update_customer_profile,
                               camera_exists, close_camera_connection,
                               create_camera_and_credential,
                               create_device_credential, ensure_schema,
                               find_active_device_credential, get_customer_info,
                               get_db_connection, list_cameras_allowed_for_user,
                               list_users_with_permissions,
                               record_camera_connection, replace_user_camera_permissions,
                               retire_replaced_camera, revoke_camera_credentials,
                               touch_device_credential, update_camera_display_name,
                               user_can_view_camera,
                               update_attendance, bulk_insert_recognize_logs,
                               get_recognize_logs, get_reports_data)
from config import (CHECKIN_COOLDOWN_SECONDS, FRAME_HEIGHT, FRAME_WIDTH,
                    GUEST_CREATION_BUFFER_SIZE, MIN_DETECTION_SCORE, MIN_FACE_BBOX_SIZE, SIMILARITY_THRESHOLD, TRACK_BUFFER_SIZE, TRACK_IOU_THRESHOLD)
from app.core.settings import system_settings
from app.core.guest_tracking import GuestTrackManager

def _apply_profile_to_payload(payload: dict, info: dict):
    from datetime import datetime
    
    def safe_iso(val):
        return val.isoformat() if isinstance(val, datetime) else val

    payload.update({
        "id": info["customer_id"],
        "name": info["name"] or "Khach moi",
        "email": info.get("email"),
        "occupation": info.get("occupation", "General"),
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
        "has_face_embedding": info.get("has_face_embedding"),
        "face_embedding_dim": info.get("face_embedding_dim"),
        "face_embedding_model": info.get("face_embedding_model"),
        "phone": info.get("phone"),
        "note": info.get("note"),
    })

router = APIRouter()


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


DEVICE_COOKIE_NAME = "device_token"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
OBSERVER_WS_SUBPROTOCOL = "camera-observer"
CAMERA_PRESENCE_TTL_SECONDS = max(
    3, _positive_int_env("CAMERA_PRESENCE_TTL_SECONDS", 15)
)
CAMERA_PRESENCE_RENEW_SECONDS = max(
    1,
    min(
        CAMERA_PRESENCE_TTL_SECONDS - 1,
        _positive_int_env("CAMERA_PRESENCE_RENEW_SECONDS", 5),
    ),
)
PAIRING_CODE_TTL_SECONDS = _positive_int_env("PAIRING_CODE_TTL_SECONDS", 600)
PAIRING_CLAIM_LIMIT = _positive_int_env("PAIRING_CLAIM_LIMIT", 10)
PAIRING_CLAIM_WINDOW_SECONDS = _positive_int_env(
    "PAIRING_CLAIM_WINDOW_SECONDS", 600
)
MAX_CAMERA_FRAME_BYTES = _positive_int_env(
    "MAX_CAMERA_FRAME_BYTES", 2 * 1024 * 1024
)
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
DEFAULT_ALLOWED_WS_ORIGINS = {
    "https://checkinface.me",
    "https://www.checkinface.me",
    "https://face-recognition-system-coral.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
ALLOWED_WS_ORIGINS = {
    origin.strip()
    for origin in os.getenv(
        "WS_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_WS_ORIGINS)
    ).split(",")
    if origin.strip()
}


def _hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _device_cookie_secure(request: Request) -> bool:
    configured = os.getenv("DEVICE_COOKIE_SECURE")
    if configured is not None:
        return configured.lower() in {"1", "true", "yes", "on"}
    return request.url.scheme == "https"


def _camera_presence_key(camera_id: str) -> str:
    return f"camera:presence:{camera_id}"


def _decode_redis_value(value):
    return value.decode("utf-8") if isinstance(value, bytes) else value


async def _acquire_camera_lease(redis, camera_id: str, connection_id: str):
    return bool(
        await redis.set(
            _camera_presence_key(camera_id),
            connection_id,
            nx=True,
            ex=CAMERA_PRESENCE_TTL_SECONDS,
        )
    )


async def _renew_camera_lease(redis, camera_id: str, connection_id: str):
    renewed = await redis.eval(
        RENEW_CAMERA_LEASE_SCRIPT,
        1,
        _camera_presence_key(camera_id),
        connection_id,
        CAMERA_PRESENCE_TTL_SECONDS,
    )
    return bool(renewed)


async def _release_camera_lease(redis, camera_id: str, connection_id: str):
    released = await redis.eval(
        RELEASE_CAMERA_LEASE_SCRIPT,
        1,
        _camera_presence_key(camera_id),
        connection_id,
    )
    return bool(released)


async def _takeover_camera_lease(redis, camera_id: str, connection_id: str):
    previous = await redis.eval(
        TAKEOVER_CAMERA_LEASE_SCRIPT,
        1,
        _camera_presence_key(camera_id),
        connection_id,
        CAMERA_PRESENCE_TTL_SECONDS,
    )
    return _decode_redis_value(previous) or None


def _pairing_code_key(code: str) -> str:
    return "camera:pairing:" + hashlib.sha256(code.encode("utf-8")).hexdigest()


async def _connection_owns_camera_lease(
    redis, camera_id: str, connection_id: str
):
    owner = await redis.get(_camera_presence_key(camera_id))
    return _decode_redis_value(owner) == connection_id


async def _maintain_camera_lease(
    redis, connection_state
):
    camera_id = connection_state.camera_id
    connection_id = connection_state.connection_id
    while True:
        await asyncio.sleep(CAMERA_PRESENCE_RENEW_SECONDS)
        try:
            renewed = await _renew_camera_lease(
                redis, camera_id, connection_id
            )
        except Exception:
            connection_state.disconnect_reason = "presence_unavailable"
            await connection_state.websocket.close(
                code=1011, reason="Presence unavailable"
            )
            return
        if not renewed:
            connection_state.disconnect_reason = "lease_lost"
            await connection_state.websocket.close(
                code=4009, reason="Camera lease lost"
            )
            return


def _resolve_websocket_camera(websocket: WebSocket):
    if websocket.headers.get("origin") not in ALLOWED_WS_ORIGINS:
        return None, "origin_not_allowed"

    raw_token = websocket.cookies.get(DEVICE_COOKIE_NAME)
    if not raw_token:
        return None, "missing_device_token"

    conn = get_db_connection()
    try:
        credential = find_active_device_credential(
            conn, _hash_device_token(raw_token)
        )
        if not credential:
            return None, "invalid_device_token"

        touch_device_credential(
            conn,
            credential["credential_id"],
            credential["camera_id"],
        )
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

class CameraState:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.active = True
        self.latest_jpeg = None          # Raw JPEG bytes of last received frame
        self.last_frame_time = None      # time.time() when last frame was received
        self.latest_customers_payload = []


class ConnectionState:
    def __init__(self, connection_id: str, camera_id: str, websocket: WebSocket):
        self.connection_id = connection_id
        self.camera_id = camera_id
        self.websocket = websocket
        self.track_manager = None
        self.disconnect_reason = "client_disconnect"

CAMERA_STATES = {}
CAMERA_STATES_LOCK = threading.Lock()
CONNECTION_STATES = {}
CONNECTION_STATES_LOCK = threading.Lock()

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


@router.post("/api/device/identity")
def resolve_device_identity(request: Request, response: Response):
    raw_token = request.cookies.get(DEVICE_COOKIE_NAME)
    conn = get_db_connection()

    try:
        if raw_token:
            credential = find_active_device_credential(
                conn, _hash_device_token(raw_token)
            )
            if not credential:
                invalid_response = Response(
                    content=json.dumps(
                        {"detail": "Device credential is invalid or revoked"}
                    ),
                    status_code=401,
                    media_type="application/json",
                )
                invalid_response.delete_cookie(
                    DEVICE_COOKIE_NAME,
                    path="/",
                    secure=True,
                    httponly=True,
                    samesite="none",
                )
                return invalid_response

            touch_device_credential(
                conn,
                credential["credential_id"],
                credential["camera_id"],
            )
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
        return {
            "camera_id": camera_id,
            "display_name": display_name,
            "is_new": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/api/device/enrollments")
async def create_device_enrollment(
    request: Request,
    authorization: str | None = Header(default=None),
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

    enrollment = json.dumps({
        "camera_id": camera_id,
        "revoke_existing": revoke_existing,
        "created_by": admin["username"],
    })
    r = await get_redis()
    try:
        for _ in range(10):
            code = f"{secrets.randbelow(1_000_000):06d}"
            created = await r.set(
                _pairing_code_key(code),
                enrollment,
                nx=True,
                ex=PAIRING_CODE_TTL_SECONDS,
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
    rate_key = "camera:pairing-rate:" + hashlib.sha256(
        client_host.encode("utf-8")
    ).hexdigest()
    pairing_key = _pairing_code_key(code)
    r = await get_redis()
    enrollment_payload = None
    try:
        attempts = await r.incr(rate_key)
        if attempts == 1:
            await r.expire(rate_key, PAIRING_CLAIM_WINDOW_SECONDS)
        if attempts > PAIRING_CLAIM_LIMIT:
            raise HTTPException(status_code=429, detail="Too many pairing attempts")

        enrollment_payload = await r.eval(
            CONSUME_PAIRING_CODE_SCRIPT, 1, pairing_key
        )
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

            if (
                current_credential
                and current_credential["camera_id"] != camera_id
            ):
                retire_replaced_camera(conn, current_credential["camera_id"])

            create_device_credential(
                conn,
                camera_id,
                credential_id,
                _hash_device_token(raw_token),
                request.headers.get("user-agent"),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            await r.set(
                pairing_key,
                enrollment_payload,
                nx=True,
                ex=min(60, PAIRING_CODE_TTL_SECONDS),
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

@router.get("/api/settings")
def get_settings():
    system_settings.load_settings()
    return system_settings.get_all()

@router.post("/api/settings")
async def update_settings(request: Request, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    data = await request.json()
    system_settings.update(data)
    return {"status": "ok", "message": "Settings updated successfully", "settings": system_settings.get_all()}

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
            "SELECT id, username, password_hash, role, cameras, status FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        if row["password_hash"] != pwd_hash:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if row["status"] != "active":
            raise HTTPException(status_code=403, detail="Account is disabled")

        cameras_list = []
        if row["cameras"]:
            cameras_list = [c.strip() for c in row["cameras"].split(",") if c.strip()]

        user_info = {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "cameras": cameras_list,
        }
        token = create_access_token(user_info)

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
    email = payload.get("email")
    note = payload.get("note")
    service_category = payload.get("service_category")
    service_start_year = payload.get("service_start_year")
    customer_tenure_years = payload.get("customer_tenure_years")
    loyalty_tier = payload.get("loyalty_tier") or payload.get("rank")

    conn = get_db_connection()

    try:
        writable_id = selected_id
        final_id = selected_id  # fallback value
        created = False
        # Treat temporary IDs as new customers requiring a generated numeric ID
        if writable_id.startswith("T") or writable_id.startswith("GUEST_") or writable_id.startswith("test_"):
            writable_id = None

        try:
            final_id, created = create_or_update_customer_profile(
                conn,
                customer_id=writable_id,
                source_id=source_id,
                name=name,
                phone=phone,
                email=email,
                note=note,
                service_category=service_category,
                service_start_year=service_start_year,
                customer_tenure_years=customer_tenure_years,
                loyalty_tier=loyalty_tier,
            )
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

        if (source_id.startswith("GUEST_") or source_id.startswith("test_")) and final_id != source_id:
            camera_id = "default"
            parts = source_id.split("_")
            if len(parts) >= 3:
                prefix = "_".join(parts[:-2])
                if prefix.startswith("GUEST_"):
                    camera_id = prefix[len("GUEST_") :]
            
            # Send control message to AI worker to promote guest
            r = await get_redis()
            await r.publish(f"camera_control:{camera_id}", json.dumps({
                "action": "promote_guest",
                "guest_id": source_id,
                "new_id": final_id
            }))
            
            # Send reload encodings command to all cameras
            with CAMERA_STATES_LOCK:
                for cid in CAMERA_STATES.keys():
                    await r.publish(f"camera_control:{cid}", json.dumps({
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
        try:
            conn.close()
        except Exception:
            pass
        # Invalidate cache command to workers
        try:
            r = await get_redis()
            with CAMERA_STATES_LOCK:
                for cid in CAMERA_STATES.keys():
                    await r.publish(f"camera_control:{cid}", json.dumps({
                        "action": "invalidate_cache",
                        "customer_id": final_id
                    }))
        except Exception:
            pass

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

@router.get("/api/logs")
def api_get_recognize_logs(
    start_date: str = None,
    end_date: str = None,
    camera_id: str = None,
    customer_type: str = None,
    search: str = None,
    page: int = 1,
    limit: int = 50,
):
    """
    Get recognition event logs with date range filtering, camera, customer_type, search and pagination.
    """
    conn = get_db_connection()
    try:
        offset = max(0, (page - 1) * limit)
        result = get_recognize_logs(
            conn,
            start_date=start_date,
            end_date=end_date,
            camera_id=camera_id,
            customer_type=customer_type,
            search=search,
            limit=limit,
            offset=offset,
        )
        return {
            "success": True,
            "logs": result["logs"],
            "total_count": result["total_count"],
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(result["total_count"] / limit) if limit > 0 else 1,
        }
    except Exception as e:
        return {"success": False, "message": f"Error fetching logs: {str(e)}", "logs": [], "total_count": 0}
    finally:
        conn.close()


@router.get("/api/logs/export")
def api_export_recognize_logs_csv(
    start_date: str = None,
    end_date: str = None,
    camera_id: str = None,
    customer_type: str = None,
    search: str = None,
):
    """
    Export filtered recognition logs as CSV file (with UTF-8 BOM for Excel compatibility).
    """
    conn = get_db_connection()
    try:
        result = get_recognize_logs(
            conn,
            start_date=start_date,
            end_date=end_date,
            camera_id=camera_id,
            customer_type=customer_type,
            search=search,
            limit=10000,
            offset=0,
        )
        logs = result["logs"]

        import csv
        import io

        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow([
            "Mã Log", "Thời Gian", "Camera ID", "Tên Camera", 
            "Mã Khách hàng", "Tên Khách hàng", "Số Điện thoại", "Loại Khách", "Hạng Thành viên", "Track ID"
        ])

        for log in logs:
            writer.writerow([
                log.get("id") or "",
                log.get("timestamp") or "",
                log.get("camera_id") or "",
                log.get("camera_name") or "",
                log.get("customer_id") or "",
                log.get("customer_name") or "",
                log.get("customer_phone") or "",
                log.get("customer_type") or "guest",
                log.get("loyalty_tier") or "Standard",
                log.get("track_id") or "",
            ])

        csv_data = output.getvalue()
        filename = f"nhat_ky_nhan_dien_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return Response(content=f"Error exporting CSV: {str(e)}", status_code=500)
    finally:
        conn.close()

@router.get("/api/reports")
def api_get_reports_data(
    start_date: str = None,
    end_date: str = None,
    camera_id: str = None,
):
    """
    Get real analytical reports data (hourly traffic flow, daily counts, loyalty distribution, top customers).
    """
    conn = get_db_connection()
    try:
        data = get_reports_data(
            conn,
            start_date=start_date,
            end_date=end_date,
            camera_id=camera_id,
        )
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "message": f"Error loading reports data: {str(e)}"}
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
    await r.publish(f"camera_control:{camera_id}", json.dumps({
        "action": "promote_guest",
        "guest_id": guest_id,
        "new_id": new_id
    }))
    
    # Send reload encodings command to all cameras
    with CAMERA_STATES_LOCK:
        for cid in CAMERA_STATES.keys():
            await r.publish(f"camera_control:{cid}", json.dumps({
                "action": "reload_embeddings"
            }))
            
    return {"success": True}

@router.get("/api/customers")
def api_get_all_customers(authorization: str | None = Header(None)):
    require_admin(authorization)
    conn = get_db_connection()
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

@router.websocket("/ws/{camera_id}")
async def websocket_camera(websocket: WebSocket, camera_id: str):
    try:
        await websocket.accept()
    except Exception:
        return

    credential, auth_error = _resolve_websocket_camera(websocket)
    if auth_error or credential["camera_id"] != camera_id:
        print(f"WS Auth Error: {auth_error}, expected {camera_id} but got {credential.get('camera_id') if credential else None}", flush=True)
        await websocket.close(code=4003)
        return

    connection_id = "conn_" + uuid.uuid4().hex
    r = await get_redis()
    previous_connection_id = None
    try:
        takeover_requested = websocket.query_params.get("takeover") == "1"
        if takeover_requested:
            previous_connection_id = await _takeover_camera_lease(
                r, camera_id, connection_id
            )
            acquired = True
        else:
            acquired = await _acquire_camera_lease(r, camera_id, connection_id)
    except Exception:
        await r.aclose()
        await websocket.close(code=1013)
        return

    if not acquired:
        print(f"WS Camera Lease Error: could not acquire lease for {camera_id}", flush=True)
        await r.aclose()
        await websocket.close(code=4008)
        return


    state = get_camera_state(camera_id)
    connection_state = ConnectionState(connection_id, camera_id, websocket)
    with CONNECTION_STATES_LOCK:
        CONNECTION_STATES[connection_id] = connection_state
    presence_task = asyncio.create_task(
        _maintain_camera_lease(r, connection_state)
    )

    pubsub = None
    try:
        pubsub = r.pubsub()
        await pubsub.subscribe(f"worker_results_{connection_id}")
        # Observer migration is a later phase, so signaling stays camera-scoped.
        await pubsub.subscribe(f"webrtc_signaling_{camera_id}")
        await pubsub.subscribe(f"connection_control:{connection_id}")
        await pubsub.subscribe(f"camera_control:{camera_id}")

        if previous_connection_id and previous_connection_id != connection_id:
            await r.publish(
                f"connection_control:{previous_connection_id}",
                json.dumps({
                    "type": "connection_taken_over",
                    "camera_id": camera_id,
                    "connection_id": previous_connection_id,
                    "replacement_connection_id": connection_id,
                }),
            )

        track_manager = GuestTrackManager(
            buffer_size=system_settings.get("track_buffer_size", TRACK_BUFFER_SIZE),
            guest_creation_buffer_size=system_settings.get("guest_creation_buffer_size", GUEST_CREATION_BUFFER_SIZE),
            similarity_threshold=system_settings.get("similarity_threshold", SIMILARITY_THRESHOLD),
            iou_threshold=system_settings.get("track_iou_threshold", TRACK_IOU_THRESHOLD),
            min_bbox_size=system_settings.get("min_face_bbox_size", MIN_FACE_BBOX_SIZE),
            min_detection_score=system_settings.get("min_detection_score", MIN_DETECTION_SCORE),
            guest_prefix=f"GUEST_{camera_id}",
        )
        connection_state.track_manager = track_manager
        await asyncio.to_thread(track_manager.load_known_embeddings)

        audit_conn = get_db_connection()
        try:
            record_camera_connection(audit_conn, connection_id, camera_id)
            audit_conn.commit()
        finally:
            audit_conn.close()
    except Exception:
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
        await r.aclose()
        await websocket.close(code=1011)
        return

    def process_tracking_and_db(data):
        face_records = data.get("face_records", [])
        timestamp = data.get("timestamp")
        opeid = data.get("opeid")
        result_camera_id = data.get("camera_id")
        result_connection_id = data.get("connection_id")
        local_track_id = data.get("local_track_id")
        client_bbox = data.get("client_bbox")

        # Convert back lists to np.arrays for embeddings and landmarks
        for rec in face_records:
            if rec.get("embedding") is not None:
                rec["embedding"] = np.array(rec["embedding"], dtype=np.float32)
            if rec.get("landmark") is not None:
                rec["landmark"] = np.array(rec["landmark"], dtype=np.float32)

        # Assign client_bbox to bbox if present, and add local_track_id
        for rec in face_records:
            if local_track_id:
                rec["local_track_id"] = local_track_id
            if client_bbox and ("bbox" not in rec or not rec["bbox"]):
                rec["bbox"] = client_bbox
            elif client_bbox and local_track_id:
                # For edge crops, overwrite bbox to track overlapping perfectly
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
                loc_track_id = track.local_track_id if track else None

                payload = {
                    "tile_id": f"tile_{loc_track_id or track_id}",
                    "track_id": loc_track_id or track_id,
                    "local_track_id": loc_track_id,
                    "bbox": (x1, y1, x2, y2),
                    "detected": bool(customer_id),
                    "id": customer_id,
                    "name": "Khách mới",
                    "customer_type": "guest",
                    "customer_status": "temporary"
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
                logs.append({
                    "opeid": opeid,
                    "camera_id": result_camera_id,
                    "connection_id": result_connection_id,
                    "customer_id": customer_id,
                    "track_id": track_id,
                    "bbox": (x1, y1, x2, y2),
                    "timestamp": timestamp
                })
            
            if logs:
                bulk_insert_recognize_logs(conn, logs)
                
                # Auto update attendance count & last visit for recognized customers
                _last_checkin = getattr(process_tracking_and_db, "_last_checkin", {})
                now_ts = time.time()
                for face in tracked_faces:
                    cid = face.get("customer_id")
                    if cid and not str(cid).startswith("GUEST_"):
                        if now_ts - _last_checkin.get(cid, 0) > CHECKIN_COOLDOWN_SECONDS:
                            _last_checkin[cid] = now_ts
                            try:
                                update_attendance(conn, cid, last_attendance_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                            except Exception as e:
                                print(f"Auto attendance update failed for {cid}: {e}", flush=True)
                process_tracking_and_db._last_checkin = _last_checkin
                
            return customers
        finally:
            conn.close()

    async def reader():
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    channel = message["channel"].decode("utf-8")
                    data = json.loads(message["data"])
                    if channel == f"worker_results_{connection_id}":
                        if (
                            data.get("camera_id") != camera_id
                            or data.get("connection_id") != connection_id
                            or not await _connection_owns_camera_lease(
                                r, camera_id, connection_id
                            )
                        ):
                            continue
                        # Process in thread to avoid blocking asyncio loop
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
                        await websocket.send_text(json_str)
                        await r.publish(f"camera_updates:{camera_id}", json_str)
                    elif channel == f"webrtc_signaling_{camera_id}":
                        if data.get("sender") == "admin":
                            await websocket.send_json(data)
                    elif channel == f"connection_control:{connection_id}":
                        if data.get("type") == "connection_taken_over":
                            connection_state.disconnect_reason = "taken_over"
                            await websocket.close(
                                code=4008, reason="Camera opened elsewhere"
                            )
                            return
                    elif channel == f"camera_control:{camera_id}":
                        action = data.get("action")
                        if action == "promote_guest":
                            guest_id = data.get("guest_id")
                            new_id = data.get("new_id")
                            if guest_id and new_id:
                                track_manager.promote_guest(guest_id, new_id)
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
                            for track in track_manager.tracks.values():
                                track.cached_profile = None
                except Exception as e:
                    import logging
                    logging.error(f"WebSocket reader error: {e}", exc_info=True)

    reader_task = asyncio.create_task(reader())

    try:
        await websocket.send_json({
            "type": "ready",
            "camera_id": camera_id,
            "connection_id": connection_id,
        })
        await r.publish(
            f"camera_updates:{camera_id}",
            json.dumps({
                "type": "publisher_ready",
                "camera_id": camera_id,
                "connection_id": connection_id,
            }),
        )

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
                        
                    # Parse Frontend Protocol
                    if data.startswith(b'\xff\xd8'):
                        # Backward compatibility: raw JPEG
                        raw_image_bytes = bytes(data)
                        client_meta = {}
                    else:
                        try:
                            meta_len = int.from_bytes(data[:4], byteorder="big")
                            client_meta_json = data[4:4+meta_len].decode("utf-8")
                            client_meta = json.loads(client_meta_json)
                            raw_image_bytes = data[4+meta_len:]
                        except Exception:
                            raw_image_bytes = bytes(data)
                            client_meta = {}

                    state.latest_jpeg = raw_image_bytes
                    state.last_frame_time = time.time()
                    
                    opeid = str(uuid.uuid4())
                    meta_dict = {
                        "opeid": opeid,
                        "camera_id": camera_id,
                        "connection_id": connection_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    meta_dict.update(client_meta)
                    
                    meta_json = json.dumps(meta_dict).encode("utf-8")
                    meta_len_out = len(meta_json).to_bytes(4, byteorder="big")
                    
                    packed_payload = meta_len_out + meta_json + raw_image_bytes
                    
                    # Push to Redpanda with automatic Redis Queue Fallback
                    await send_camera_frame(r, packed_payload, camera_id)
            elif "text" in msg:
                try:
                    text_data = msg["text"]
                    parsed = json.loads(text_data)
                    parsed["sender"] = "camera"
                    await r.publish(f"webrtc_signaling_{camera_id}", json.dumps(parsed))
                except Exception:
                    pass
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        with CONNECTION_STATES_LOCK:
            CONNECTION_STATES.pop(connection_id, None)
        # Release the cached DB connection used by pgvector queries
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
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        finally:
            try:
                if await _connection_owns_camera_lease(
                    r, camera_id, connection_id
                ):
                    await r.publish(
                        f"camera_updates:{camera_id}",
                        json.dumps({
                            "type": "publisher_offline",
                            "camera_id": camera_id,
                            "connection_id": connection_id,
                        }),
                    )
                await _release_camera_lease(r, camera_id, connection_id)
            except Exception:
                pass
            finally:
                await r.aclose()

        audit_conn = get_db_connection()
        try:
            close_camera_connection(
                audit_conn, connection_id, connection_state.disconnect_reason
            )
            audit_conn.commit()
        finally:
            audit_conn.close()

async def _list_camera_presence(user):
    conn = get_db_connection()
    try:
        cameras = list_cameras_allowed_for_user(conn, user)
    finally:
        conn.close()

    if not cameras:
        return []

    r = await get_redis()
    try:
        owners = await r.mget(
            [_camera_presence_key(camera["camera_id"]) for camera in cameras]
        )
    finally:
        await r.aclose()

    with CAMERA_STATES_LOCK:
        result = []
        for camera, raw_owner in zip(cameras, owners):
            camera_id = camera["camera_id"]
            connection_id = _decode_redis_value(raw_owner)
            state = CAMERA_STATES.get(camera_id)
            result.append({
                "camera_id": camera_id,
                "display_name": camera["display_name"],
                "status": camera["status"],
                "active": connection_id is not None,
                "connection_id": connection_id,
                "face_count": (
                    len(state.latest_customers_payload)
                    if state is not None and connection_id is not None
                    else 0
                ),
                "last_frame_time": (
                    state.last_frame_time if state is not None else None
                ),
                "last_seen_at": camera["last_seen_at"],
            })
    return result


@router.get("/api/cameras")
async def api_cameras(authorization: str | None = Header(default=None)):
    conn = get_db_connection()
    try:

        pass

    finally:
        conn.close()
    user = get_user_from_token(authorization)
    cameras = await _list_camera_presence(user)
    return {"status": "success", "cameras": cameras}


@router.patch("/api/cameras/{camera_id}")
async def rename_camera(
    camera_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    payload = await request.json()
    display_name = str(payload.get("display_name") or "").strip()
    if not display_name or len(display_name) > 100:
        raise HTTPException(
            status_code=400,
            detail="Display name must contain between 1 and 100 characters",
        )

    conn = get_db_connection()
    try:
        if not update_camera_display_name(conn, camera_id, display_name):
            raise HTTPException(status_code=404, detail="Camera not found")
        conn.commit()
        return {
            "status": "success",
            "camera_id": camera_id,
            "display_name": display_name,
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.delete("/api/cameras/{camera_id}")
async def remove_camera(
    camera_id: str,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    conn = get_db_connection()
    try:
        from app.db.connection import delete_camera
        if not delete_camera(conn, camera_id):
            raise HTTPException(status_code=404, detail="Camera not found")
        conn.commit()
        return {
            "status": "success",
            "message": "Camera deleted successfully",
        }
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/api/users")
def api_users(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    conn = get_db_connection()
    try:
        return {"status": "success", "users": list_users_with_permissions(conn)}
    finally:
        conn.close()


@router.post("/api/users")
async def create_user(
    request: Request,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    payload = await request.json()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or len(username) > 255:
        raise HTTPException(status_code=400, detail="Username is required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must have at least 6 characters")

    conn = get_db_connection()
    try:
        if conn.execute(
            "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?)", (username,)
        ).fetchone():
            raise HTTPException(status_code=409, detail="Username already exists")
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, status)
            VALUES (?, ?, 'moderator', 'active')
            """,
            (username, hashlib.sha256(password.encode("utf-8")).hexdigest()),
        )
        conn.commit()
        user = conn.execute(
            """
            SELECT id, username, role, status, created_at, updated_at
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
        result = dict(user)
        result["camera_ids"] = []
        return {"status": "success", "user": result}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.patch("/api/users/{username}")
async def update_user(
    username: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    payload = await request.json()
    password = str(payload.get("password") or "")
    status = payload.get("status")
    if password and len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must have at least 6 characters")
    if status is not None and status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="Invalid account status")

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT id, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] == "admin":
            raise HTTPException(status_code=400, detail="Admin cannot be edited here")

        if password:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (hashlib.sha256(password.encode("utf-8")).hexdigest(), user["id"]),
            )
        if status is not None:
            conn.execute(
                "UPDATE users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, user["id"]),
            )
        conn.commit()
        if password or status == "disabled":
            revoke_user_sessions(user["id"])
        return {"status": "success", "username": username}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.delete("/api/users/{username}")
def delete_user(
    username: str,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT id, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] == "admin":
            raise HTTPException(status_code=400, detail="Admin cannot be deleted")
        conn.execute(
            "DELETE FROM user_camera_permissions WHERE user_id = ?", (user["id"],)
        )
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        conn.commit()
        revoke_user_sessions(user["id"])
        return {"status": "success", "username": username}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.put("/api/users/{username}/camera_permissions")
async def update_camera_permissions(
    username: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    payload = await request.json()
    camera_ids = sorted({
        str(camera_id).strip()
        for camera_id in payload.get("camera_ids", [])
        if str(camera_id).strip()
    })

    conn = get_db_connection()
    try:
        user_row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        invalid_ids = [
            camera_id
            for camera_id in camera_ids
            if not camera_exists(conn, camera_id)
        ]
        if invalid_ids:
            raise HTTPException(
                status_code=400,
                detail={"message": "Unknown camera IDs", "camera_ids": invalid_ids},
            )

        replace_user_camera_permissions(conn, user_row["id"], camera_ids)
        conn.execute(
            "UPDATE users SET cameras = ? WHERE id = ?",
            (",".join(camera_ids) or None, user_row["id"]),
        )
        conn.commit()
        return {"status": "success", "username": username, "camera_ids": camera_ids}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()

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
        # Send initial state
        await websocket.send_json({
            "type": "observer_ready",
            "camera_id": camera_id,
            "customers": state.latest_customers_payload if state else [],
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


from app.core.biometric_security import purge_expired_guests


@router.post("/api/admin/purge_guests")
def api_purge_guests(
    retention_days: int | None = None,
    authorization: str | None = Header(None),
):
    """GDPR Article 17 (Right to be Forgotten) Purge Endpoint for Guest Records."""
    require_admin(authorization)
    conn = get_db_connection()
    try:
        days = retention_days if retention_days is not None else 30
        result = purge_expired_guests(conn, retention_days=days)
        return {"status": "success", "data": result}
    finally:
        conn.close()
