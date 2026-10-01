"""
Authentication helpers and routes.
- JWT creation / decoding (RS256)
- /api/login
- /api/settings
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Header, HTTPException, Request

from app.db.connection import get_db_connection
from app.messaging.kafka_client import get_redis
from app.core.settings import system_settings
from config import JWT_ALGORITHM, JWT_EXPIRATION_MINUTES, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY

router = APIRouter()

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
    """Statelessly decode and verify an RS256 JWT token using public RSA key."""
    try:
        return jwt.decode(token, JWT_PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
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
