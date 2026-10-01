"""
Camera, credential, and user/permission repository functions.
"""

import re
from datetime import datetime

from db_config import DB_TYPE


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def find_active_device_credential(conn, token_hash):
    """Resolve a non-revoked, non-expired device token to its camera."""
    return conn.execute(
        """
        SELECT
            d.credential_id,
            d.camera_id,
            c.display_name,
            c.status
        FROM camera_device_credentials AS d
        JOIN cameras AS c ON c.camera_id = d.camera_id
        WHERE d.token_hash = ?
          AND d.revoked_at IS NULL
          AND (d.expires_at IS NULL OR d.expires_at > CURRENT_TIMESTAMP)
          AND c.status = 'active'
        """,
        (token_hash,),
    ).fetchone()


def create_camera_and_credential(conn, camera_id, display_name, credential_id, token_hash, user_agent=None):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO cameras (camera_id, display_name, status, created_at, updated_at, last_seen_at)
        VALUES (?, ?, 'active', ?, ?, ?)
        """,
        (camera_id, display_name, now, now, now),
    )
    conn.execute(
        """
        INSERT INTO camera_device_credentials (credential_id, camera_id, token_hash, created_at, last_used_at, user_agent)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (credential_id, camera_id, token_hash, now, now, user_agent),
    )


def create_device_credential(conn, camera_id, credential_id, token_hash, user_agent=None):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO camera_device_credentials (credential_id, camera_id, token_hash, created_at, last_used_at, user_agent)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (credential_id, camera_id, token_hash, now, now, user_agent),
    )
    conn.execute(
        "UPDATE cameras SET status = 'active', last_seen_at = ?, updated_at = ? WHERE camera_id = ?",
        (now, now, camera_id),
    )


def revoke_camera_credentials(conn, camera_id):
    conn.execute(
        "UPDATE camera_device_credentials SET revoked_at = ? WHERE camera_id = ? AND revoked_at IS NULL",
        (datetime.now().isoformat(timespec="seconds"), camera_id),
    )


def retire_replaced_camera(conn, camera_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE camera_device_credentials SET revoked_at = ? WHERE camera_id = ? AND revoked_at IS NULL",
        (now, camera_id),
    )
    conn.execute(
        "UPDATE cameras SET status = 'replaced', updated_at = ? WHERE camera_id = ?",
        (now, camera_id),
    )


def touch_device_credential(conn, credential_id, camera_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE camera_device_credentials SET last_used_at = ? WHERE credential_id = ?",
        (now, credential_id),
    )
    conn.execute(
        "UPDATE cameras SET last_seen_at = ?, updated_at = ? WHERE camera_id = ?",
        (now, now, camera_id),
    )


def list_active_cameras(conn):
    return conn.execute(
        """
        SELECT camera_id, display_name, status, created_at, updated_at, last_seen_at
        FROM cameras WHERE status = 'active' ORDER BY created_at ASC
        """
    ).fetchall()


def update_camera_display_name(conn, camera_id, display_name):
    cursor = conn.execute(
        "UPDATE cameras SET display_name = ?, updated_at = ? WHERE camera_id = ? AND status = 'active'",
        (display_name, datetime.now().isoformat(timespec="seconds"), camera_id),
    )
    return cursor.rowcount > 0


def delete_camera(conn, camera_id):
    now = datetime.now().isoformat(timespec="seconds")
    cursor = conn.execute(
        "UPDATE cameras SET status = 'deleted', updated_at = ? WHERE camera_id = ?",
        (now, camera_id),
    )
    conn.execute(
        "UPDATE camera_device_credentials SET revoked_at = ? WHERE camera_id = ? AND revoked_at IS NULL",
        (now, camera_id),
    )
    return cursor.rowcount > 0


def camera_exists(conn, camera_id):
    return (
        conn.execute(
            "SELECT 1 FROM cameras WHERE camera_id = ? AND status = 'active'", (camera_id,)
        ).fetchone()
        is not None
    )


def record_camera_connection(conn, connection_id, camera_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO camera_connections (connection_id, camera_id, connected_at) VALUES (?, ?, ?)",
        (connection_id, camera_id, now),
    )


def close_camera_connection(conn, connection_id, reason):
    conn.execute(
        """
        UPDATE camera_connections
        SET disconnected_at = ?, disconnect_reason = ?
        WHERE connection_id = ? AND disconnected_at IS NULL
        """,
        (datetime.now().isoformat(timespec="seconds"), reason, connection_id),
    )


# ---------------------------------------------------------------------------
# User / permission helpers
# ---------------------------------------------------------------------------

def list_users_with_permissions(conn):
    active_camera_ids = {row["camera_id"] for row in list_active_cameras(conn)}
    users = conn.execute(
        "SELECT id, username, role, cameras, status, created_at, updated_at FROM users ORDER BY username ASC"
    ).fetchall()
    result = []
    for row in users:
        user = dict(row)
        permission_rows = conn.execute(
            "SELECT camera_id FROM user_camera_permissions WHERE user_id = ? AND permission = 'view' ORDER BY camera_id ASC",
            (user["id"],),
        ).fetchall()
        normalized_ids = [
            item["camera_id"] for item in permission_rows if item["camera_id"] in active_camera_ids
        ]
        legacy_ids = [
            cid.strip()
            for cid in str(user.pop("cameras") or "").split(",")
            if cid.strip() in active_camera_ids
        ]
        user["camera_ids"] = normalized_ids if permission_rows else legacy_ids
        result.append(user)
    return result


def list_cameras_allowed_for_user(conn, user):
    cameras = [dict(row) for row in list_active_cameras(conn)]
    if user.get("role") == "admin":
        return cameras

    rows = conn.execute(
        "SELECT camera_id FROM user_camera_permissions WHERE user_id = ? AND permission = 'view'",
        (user["id"],),
    ).fetchall()
    normalized_ids = {row["camera_id"] for row in rows}
    legacy_row = conn.execute("SELECT cameras FROM users WHERE id = ?", (user["id"],)).fetchone()
    legacy_ids = (
        {cid.strip() for cid in str(legacy_row["cameras"] or "").split(",") if cid.strip()}
        if legacy_row
        else set()
    )
    allowed_ids = normalized_ids or legacy_ids
    return [camera for camera in cameras if camera["camera_id"] in allowed_ids]


def user_can_view_camera(conn, user, camera_id):
    return any(
        camera["camera_id"] == camera_id for camera in list_cameras_allowed_for_user(conn, user)
    )


def replace_user_camera_permissions(conn, user_id, camera_ids):
    conn.execute(
        "DELETE FROM user_camera_permissions WHERE user_id = ? AND permission = 'view'", (user_id,)
    )
    for camera_id in camera_ids:
        conn.execute(
            "INSERT INTO user_camera_permissions (user_id, camera_id, permission) VALUES (?, ?, 'view')",
            (user_id, camera_id),
        )
