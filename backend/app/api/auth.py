"""
Authentication helpers and routes.
- JWT creation / decoding (RS256)
- /api/login
- /api/settings
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone

import jwt
import redis
from fastapi import APIRouter, Header, HTTPException, Request

from app.db.connection import get_db_connection
from app.messaging.kafka_client import get_redis
from app.core.settings import system_settings
from config import (
    JWT_ALGORITHM,
    JWT_EXPIRATION_MINUTES,
    JWT_PRIVATE_KEY,
    JWT_PUBLIC_KEY,
    REDIS_URL,
)

logger = logging.getLogger("Auth")

router = APIRouter()

_redis_sync_client: redis.Redis | None = None


def get_sync_redis_client() -> redis.Redis:
    global _redis_sync_client
    if _redis_sync_client is None:
        _redis_sync_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_sync_client


# ---------------------------------------------------------------------------
# JWT helpers (imported by other route modules)
# ---------------------------------------------------------------------------

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
    """Statelessly decode and verify an RS256 JWT token using public RSA key,
    with fast Redis revocation check."""
    try:
        payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    user_id = payload.get("id")
    token_iat = payload.get("iat", 0)

    if user_id:
        try:
            r = get_sync_redis_client()
            revoked_at = r.get(f"user_revoked_at:{user_id}")
            if revoked_at is not None and int(token_iat) <= int(revoked_at):
                raise HTTPException(
                    status_code=401, detail="Session has been revoked. Please log in again."
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Could not verify session revocation in Redis: %s", exc)

    return payload


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
    """
    Revoke all active sessions for user_id by recording a revocation timestamp in Redis.
    Any token issued at or before this timestamp will be rejected by decode_access_token.
    TTL is set to JWT_EXPIRATION_MINUTES * 60 so keys automatically expire.
    """
    try:
        r = get_sync_redis_client()
        now_ts = int(datetime.now(timezone.utc).timestamp())
        ttl_seconds = int(JWT_EXPIRATION_MINUTES * 60)
        r.set(f"user_revoked_at:{user_id}", str(now_ts), ex=ttl_seconds)
        logger.info("Revoked all sessions for user_id=%s at timestamp %s", user_id, now_ts)
    except Exception as exc:
        logger.error("Failed to revoke sessions for user_id=%s in Redis: %s", user_id, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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


@router.get("/api/settings")
def get_settings():
    system_settings.load_settings()
    return system_settings.get_all()


@router.post("/api/settings")
async def update_settings(
    request: Request, authorization: str | None = Header(default=None)
):
    require_admin(authorization)
    data = await request.json()
    system_settings.update(data)
    return {
        "status": "ok",
        "message": "Settings updated successfully",
        "settings": system_settings.get_all(),
    }


@router.post("/api/logout")
async def api_logout(authorization: str | None = Header(default=None)):
    user = get_user_from_token(authorization)
    revoke_user_sessions(user["id"])
    return {"status": "success", "message": "Logged out successfully"}

