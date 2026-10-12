"""
Camera management & user/permission routes:
- GET    /api/cameras
- PATCH  /api/cameras/{camera_id}
- DELETE /api/cameras/{camera_id}
- GET    /api/users
- POST   /api/users
- PATCH  /api/users/{username}
- DELETE /api/users/{username}
- PUT    /api/users/{username}/camera_permissions
"""

import hashlib

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.auth import get_user_from_token, require_admin, revoke_user_sessions
from app.api.devices import (
    CAMERA_STATES,
    CAMERA_STATES_LOCK,
    _camera_presence_key,
    _decode_redis_value,
)
from app.db.connection import (
    camera_exists,
    get_db_connection,
    list_cameras_allowed_for_user,
    list_users_with_permissions,
    replace_user_camera_permissions,
    update_camera_display_name,
)
from app.messaging.kafka_client import get_redis

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: list cameras with real-time presence info
# ---------------------------------------------------------------------------


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
            result.append(
                {
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
                    "last_frame_time": state.last_frame_time if state is not None else None,
                    "last_seen_at": camera["last_seen_at"],
                }
            )
    return result


# ---------------------------------------------------------------------------
# Camera routes
# ---------------------------------------------------------------------------


@router.get("/api/cameras")
async def api_cameras(authorization: str | None = Header(default=None)):
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
        return {"status": "success", "camera_id": camera_id, "display_name": display_name}
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
        return {"status": "success", "message": "Camera deleted successfully"}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/api/cameras/{camera_id}/disconnect")
async def disconnect_camera(
    camera_id: str,
    authorization: str | None = Header(default=None),
):
    """Admin endpoint to forcefully disconnect/revoke an active publisher session for a camera."""
    require_admin(authorization)
    r = await get_redis()
    try:
        presence_key = _camera_presence_key(camera_id)
        raw_owner = await r.get(presence_key)
        connection_id = _decode_redis_value(raw_owner)
        if connection_id:
            await r.delete(presence_key)
            await r.publish(
                f"connection_control:{connection_id}",
                '{"type": "connection_taken_over"}',
            )
            return {
                "status": "success",
                "message": f"Phiên phát của camera {camera_id} đã được thu hồi thành công.",
                "camera_id": camera_id,
            }
        return {
            "status": "success",
            "message": f"Camera {camera_id} hiện không có phiên phát nào hoạt động.",
            "camera_id": camera_id,
        }
    finally:
        await r.aclose()


# ---------------------------------------------------------------------------
# User management routes
# ---------------------------------------------------------------------------


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
        conn.execute("DELETE FROM user_camera_permissions WHERE user_id = ?", (user["id"],))
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
    camera_ids = sorted(
        {
            str(camera_id).strip()
            for camera_id in payload.get("camera_ids", [])
            if str(camera_id).strip()
        }
    )

    conn = get_db_connection()
    try:
        user_row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        invalid_ids = [cid for cid in camera_ids if not camera_exists(conn, cid)]
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
