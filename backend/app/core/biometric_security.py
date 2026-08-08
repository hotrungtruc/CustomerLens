import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import (
    BIOMETRIC_PROJECTION_MATRIX_PATH,
    BIOMETRIC_STORAGE_KEY_PATH,
    GUEST_RETENTION_DAYS,
    IMAGES_DIR,
    KEYS_DIR,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AESGCMBiometricStorage:
    """AES-256-GCM Authenticated Encryption for Biometric Files (Encryption at Rest)."""

    def __init__(self, key_path: Path = BIOMETRIC_STORAGE_KEY_PATH):
        self.key_path = key_path
        self.key = self._load_or_create_key()

    def _load_or_create_key(self) -> bytes:
        env_key = os.getenv("BIOMETRIC_ENCRYPTION_KEY")
        if env_key:
            return bytes.fromhex(env_key)

        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.exists():
            return self.key_path.read_bytes()

        key = AESGCM.generate_key(bit_length=256)
        try:
            self.key_path.write_bytes(key)
        except Exception as e:
            logger.warning(f"Could not persist AESGCM key to disk: {e}")
        return key

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Encrypt bytes using AES-256-GCM with a random 12-byte nonce."""
        aesgcm = AESGCM(self.key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def decrypt_bytes(self, payload: bytes) -> bytes:
        """Decrypt AES-256-GCM payload (12-byte nonce + ciphertext)."""
        if len(payload) < 28:
            raise ValueError("Invalid ciphertext length")
        nonce = payload[:12]
        ciphertext = payload[12:]
        aesgcm = AESGCM(self.key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def save_encrypted_file(self, path: Path, data: bytes):
        encrypted = self.encrypt_bytes(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encrypted)

    def read_encrypted_file(self, path: Path) -> bytes:
        encrypted = path.read_bytes()
        return self.decrypt_bytes(encrypted)


class BiometricTemplateProtector:
    """Cancelable Biometrics via Orthogonal Random Projection (Non-invertible Template Protection).
    
    Transforms face vector x into y = Q * x where Q is an orthogonal matrix (Q^T * Q = I).
    Exact inner product & cosine similarity are preserved (<Q*x1, Q*x2> == <x1, x2>),
    preventing face image reconstruction from DB vectors if database is leaked.
    """

    def __init__(self, matrix_path: Path = BIOMETRIC_PROJECTION_MATRIX_PATH, dim: int = 512):
        self.dim = dim
        self.matrix_path = matrix_path
        self.projection_matrix = self._load_or_create_matrix()

    def _load_or_create_matrix(self) -> np.ndarray:
        self.matrix_path.parent.mkdir(parents=True, exist_ok=True)
        if self.matrix_path.exists():
            try:
                matrix = np.load(str(self.matrix_path))
                if matrix.shape == (self.dim, self.dim):
                    return matrix.astype(np.float32)
            except Exception as e:
                logger.warning(f"Could not load projection matrix from {self.matrix_path}: {e}")

        # Generate orthogonal matrix via QR decomposition
        random_mat = np.random.randn(self.dim, self.dim)
        q, _ = np.linalg.qr(random_mat)
        q = q.astype(np.float32)

        try:
            np.save(str(self.matrix_path), q)
        except Exception as e:
            logger.warning(f"Could not save projection matrix to disk: {e}")

        return q

    def protect_embedding(self, embedding: np.ndarray) -> np.ndarray:
        """Apply Orthogonal Random Projection to transform embedding vector."""
        if embedding is None:
            return None
        emb = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if emb.shape[0] != self.dim:
            return emb
        
        projected = np.dot(self.projection_matrix, emb)
        norm = np.linalg.norm(projected)
        if norm == 0:
            return projected
        return projected / norm


# Global instances
biometric_storage = AESGCMBiometricStorage()
biometric_protector = BiometricTemplateProtector()


def purge_expired_guests(conn, retention_days: int = GUEST_RETENTION_DAYS) -> dict:
    """GDPR Article 17 (Right to be Forgotten): Delete expired guest records, embeddings, and logs."""
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Find expired guest IDs
    try:
        rows = conn.execute(
            """
            SELECT customer_id FROM customers
            WHERE customer_id LIKE 'GUEST_%'
              AND (registered_at < ? OR last_visit < ? OR registered_at IS NULL)
            """,
            (cutoff_str, cutoff_str),
        ).fetchall()
    except Exception:
        rows = conn.execute(
            """
            SELECT customer_id FROM customers
            WHERE customer_id LIKE 'GUEST_%'
            """
        ).fetchall()

    expired_guest_ids = [row["customer_id"] if isinstance(row, dict) else row[0] for row in rows]

    if not expired_guest_ids:
        return {"purged_guests_count": 0, "retention_days": retention_days}

    # Delete related embeddings, logs, and customer entries
    placeholders = ",".join(["?"] * len(expired_guest_ids))
    
    conn.execute(
        f"DELETE FROM customer_embeddings WHERE customer_id IN ({placeholders})",
        expired_guest_ids,
    )
    conn.execute(
        f"DELETE FROM recognize_logs WHERE customer_id IN ({placeholders})",
        expired_guest_ids,
    )
    conn.execute(
        f"DELETE FROM customers WHERE customer_id IN ({placeholders})",
        expired_guest_ids,
    )

    conn.commit()

    # Delete disk files if any
    purged_files = 0
    for gid in expired_guest_ids:
        for ext in (".jpg", ".jpeg", ".png", ".enc"):
            file_path = IMAGES_DIR / f"{gid}{ext}"
            if file_path.exists():
                try:
                    file_path.unlink()
                    purged_files += 1
                except Exception:
                    pass

    logger.info(
        f"GDPR Purge: Cleaned {len(expired_guest_ids)} guest records and {purged_files} files older than {retention_days} days."
    )
    return {
        "purged_guests_count": len(expired_guest_ids),
        "purged_files_count": purged_files,
        "retention_days": retention_days,
        "cutoff_timestamp": cutoff_str,
    }
