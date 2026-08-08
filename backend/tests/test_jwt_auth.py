import unittest
import time
from fastapi import HTTPException
import jwt

from app.api.routes import create_access_token, decode_access_token, get_user_from_token
from config import JWT_ALGORITHM, JWT_PUBLIC_KEY, JWT_PRIVATE_KEY
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


class TestJWTAuthentication(unittest.TestCase):

    def test_create_and_decode_token(self):
        user_data = {
            "id": 42,
            "username": "testuser",
            "role": "admin",
            "cameras": ["cam_01", "cam_02"],
        }
        token = create_access_token(user_data)
        self.assertIsInstance(token, str)

        payload = decode_access_token(token)
        self.assertEqual(payload["id"], 42)
        self.assertEqual(payload["username"], "testuser")
        self.assertEqual(payload["role"], "admin")
        self.assertEqual(payload["cameras"], ["cam_01", "cam_02"])
        self.assertIn("exp", payload)
        self.assertIn("iat", payload)

    def test_get_user_from_token_valid(self):
        user_data = {"id": 1, "username": "admin", "role": "admin", "cameras": []}
        token = create_access_token(user_data)
        auth_header = f"Bearer {token}"
        user = get_user_from_token(auth_header)
        self.assertEqual(user["username"], "admin")

    def test_get_user_from_token_invalid_format(self):
        with self.assertRaises(HTTPException) as ctx:
            get_user_from_token("InvalidHeaderString")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_get_user_from_token_tampered_token(self):
        user_data = {"id": 1, "username": "admin", "role": "admin", "cameras": []}
        token = create_access_token(user_data)
        tampered_token = token[:-5] + "XXXXX"
        auth_header = f"Bearer {tampered_token}"
        with self.assertRaises(HTTPException) as ctx:
            get_user_from_token(auth_header)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_token(self):
        now = int(time.time())
        expired_payload = {
            "sub": "1",
            "id": 1,
            "username": "expired_user",
            "role": "admin",
            "iat": now - 3600,
            "exp": now - 60,  # Expired 60 seconds ago
        }
        expired_token = jwt.encode(expired_payload, JWT_PRIVATE_KEY, algorithm=JWT_ALGORITHM)
        with self.assertRaises(HTTPException) as ctx:
            decode_access_token(expired_token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_token_signed_by_different_key(self):
        # Generate an untrusted external RSA key
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        fake_token = jwt.encode(
            {"id": 1, "username": "hacker", "role": "admin", "exp": int(time.time()) + 3600},
            other_pem,
            algorithm=JWT_ALGORITHM,
        )
        with self.assertRaises(HTTPException) as ctx:
            decode_access_token(fake_token)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
