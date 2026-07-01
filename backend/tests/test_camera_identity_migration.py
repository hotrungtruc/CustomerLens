import asyncio
import hashlib
import json
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace

from starlette.responses import Response

import app.db.connection as db
from app.api import routes


class FakeRequest:
    def __init__(self, payload=None, cookies=None):
        self._payload = payload or {}
        self.cookies = cookies or {}
        self.headers = {"user-agent": "migration-test"}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.url = SimpleNamespace(scheme="http")

    async def json(self):
        return self._payload


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.counts = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def mget(self, keys):
        return [self.values.get(key) for key in keys]

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        return True

    async def eval(self, script, numkeys, key, *args):
        if "local payload" in script:
            return self.values.pop(key, "")
        owner = args[0]
        if self.values.get(key) != owner:
            return 0
        if "EXPIRE" in script:
            return 1
        if "DEL" in script:
            del self.values[key]
            return 1
        return 0

    async def aclose(self):
        pass


class CameraIdentityMigrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.PRODUCTION_DB_PATH
        db.PRODUCTION_DB_PATH = Path(self.temp_dir.name) / "migration.db"
        conn = db.get_db_connection()
        db.ensure_schema(conn)
        conn.close()

    def tearDown(self):
        routes.ACTIVE_SESSIONS.clear()
        db.PRODUCTION_DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_identity_cookie_resolves_same_camera(self):
        first_response = Response()
        first = routes.resolve_device_identity(FakeRequest(), first_response)
        cookie = SimpleCookie()
        cookie.load(first_response.headers["set-cookie"])
        token = cookie[routes.DEVICE_COOKIE_NAME].value

        second = routes.resolve_device_identity(
            FakeRequest(cookies={routes.DEVICE_COOKIE_NAME: token}), Response()
        )

        self.assertTrue(first["is_new"])
        self.assertFalse(second["is_new"])
        self.assertEqual(first["camera_id"], second["camera_id"])

        conn = db.get_db_connection()
        row = conn.execute(
            "SELECT token_hash FROM camera_device_credentials"
        ).fetchone()
        conn.close()
        self.assertNotEqual(row["token_hash"], token)

    def test_moderator_permissions_filter_catalog(self):
        conn = db.get_db_connection()
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("moderator", "hash", "moderator"),
        )
        user_id = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("moderator",)
        ).fetchone()["id"]
        for suffix in ("a", "b"):
            db.create_camera_and_credential(
                conn,
                f"cam_{suffix}",
                f"Camera {suffix.upper()}",
                f"cred_{suffix}",
                hashlib.sha256(suffix.encode()).hexdigest(),
            )
        db.replace_user_camera_permissions(conn, user_id, ["cam_a"])
        conn.commit()

        cameras = db.list_cameras_allowed_for_user(
            conn,
            {"id": user_id, "role": "moderator", "cameras": []},
        )
        conn.close()
        self.assertEqual([camera["camera_id"] for camera in cameras], ["cam_a"])

    def test_legacy_permissions_exclude_unknown_camera_ids(self):
        conn = db.get_db_connection()
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, cameras)
            VALUES (?, ?, ?, ?)
            """,
            ("legacy", "hash", "moderator", "DSLR-002,DSLR-003"),
        )
        db.create_camera_and_credential(
            conn, "cam_current", "Current", "cred_current", "hash_current"
        )
        conn.commit()

        users = db.list_users_with_permissions(conn)
        conn.close()
        legacy = next(user for user in users if user["username"] == "legacy")
        self.assertEqual(legacy["camera_ids"], [])

    async def test_admin_can_manage_users_permissions_and_camera_names(self):
        token = "admin-test-token"
        routes.ACTIVE_SESSIONS[token] = {
            "id": 999,
            "username": "admin",
            "role": "admin",
            "cameras": [],
        }
        authorization = f"Bearer {token}"

        conn = db.get_db_connection()
        db.create_camera_and_credential(
            conn, "cam_front", "Camera mới", "cred_front", "token_hash"
        )
        conn.commit()
        conn.close()

        created = await routes.create_user(
            FakeRequest({"username": "guard", "password": "secret123"}),
            authorization,
        )
        self.assertEqual(created["user"]["role"], "moderator")

        assigned = await routes.update_camera_permissions(
            "guard",
            FakeRequest({"camera_ids": ["cam_front"]}),
            authorization,
        )
        self.assertEqual(assigned["camera_ids"], ["cam_front"])

        renamed = await routes.rename_camera(
            "cam_front",
            FakeRequest({"display_name": "CAM-001 - Cửa chính"}),
            authorization,
        )
        self.assertEqual(renamed["display_name"], "CAM-001 - Cửa chính")

        users = routes.api_users(authorization)["users"]
        guard = next(user for user in users if user["username"] == "guard")
        self.assertEqual(guard["camera_ids"], ["cam_front"])

        await routes.update_user(
            "guard", FakeRequest({"status": "disabled"}), authorization
        )
        users = routes.api_users(authorization)["users"]
        guard = next(user for user in users if user["username"] == "guard")
        self.assertEqual(guard["status"], "disabled")

        routes.delete_user("guard", authorization)
        usernames = [user["username"] for user in routes.api_users(authorization)["users"]]
        self.assertNotIn("guard", usernames)

    async def test_lease_is_owner_safe(self):
        redis = FakeRedis()
        self.assertTrue(
            await routes._acquire_camera_lease(redis, "cam_a", "conn_a")
        )
        self.assertFalse(
            await routes._acquire_camera_lease(redis, "cam_a", "conn_b")
        )
        self.assertFalse(
            await routes._renew_camera_lease(redis, "cam_a", "conn_b")
        )
        self.assertFalse(
            await routes._release_camera_lease(redis, "cam_a", "conn_b")
        )
        self.assertTrue(
            await routes._release_camera_lease(redis, "cam_a", "conn_a")
        )

    async def test_pairing_code_is_one_time_and_retires_temporary_camera(self):
        conn = db.get_db_connection()
        db.create_camera_and_credential(
            conn, "cam_target", "Target", "cred_target", "target_hash"
        )
        db.create_camera_and_credential(
            conn,
            "cam_temp",
            "Temporary",
            "cred_temp",
            hashlib.sha256(b"temp-token").hexdigest(),
        )
        conn.commit()
        conn.close()

        code = "123456"
        redis = FakeRedis()
        redis.values[routes._pairing_code_key(code)] = json.dumps({
            "camera_id": "cam_target",
            "revoke_existing": True,
        })
        original_get_redis = routes.get_redis

        async def get_fake_redis():
            return redis

        routes.get_redis = get_fake_redis
        try:
            result = await routes.claim_device_enrollment(
                FakeRequest(
                    {"code": code},
                    {routes.DEVICE_COOKIE_NAME: "temp-token"},
                ),
                Response(),
            )
            self.assertEqual(result["camera_id"], "cam_target")
            with self.assertRaises(routes.HTTPException):
                await routes.claim_device_enrollment(
                    FakeRequest({"code": code}), Response()
                )
        finally:
            routes.get_redis = original_get_redis

        conn = db.get_db_connection()
        status = conn.execute(
            "SELECT status FROM cameras WHERE camera_id = 'cam_temp'"
        ).fetchone()["status"]
        conn.close()
        self.assertEqual(status, "replaced")


if __name__ == "__main__":
    unittest.main()
