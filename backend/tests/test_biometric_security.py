import unittest
import tempfile
from pathlib import Path
import numpy as np

from app.core.biometric_security import (
    AESGCMBiometricStorage,
    BiometricTemplateProtector,
    purge_expired_guests,
)
import app.db.connection as db


class TestBiometricSecurity(unittest.TestCase):

    def test_aes_gcm_encryption_decryption(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            key_path = Path(tmp_dir) / "test_biometric.key"
            storage = AESGCMBiometricStorage(key_path=key_path)

            original_data = b"BiometricFaceImageDataSecret12345"
            encrypted = storage.encrypt_bytes(original_data)

            self.assertNotEqual(encrypted, original_data)
            self.assertGreater(len(encrypted), len(original_data))

            decrypted = storage.decrypt_bytes(encrypted)
            self.assertEqual(decrypted, original_data)

    def test_cancelable_biometrics_orthogonal_projection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            matrix_path = Path(tmp_dir) / "test_projection.npy"
            protector = BiometricTemplateProtector(matrix_path=matrix_path, dim=512)

            # Generate two random 512D unit vectors
            v1 = np.random.randn(512).astype(np.float32)
            v1 /= np.linalg.norm(v1)
            
            v2 = np.random.randn(512).astype(np.float32)
            v2 /= np.linalg.norm(v2)

            # Calculate raw Cosine similarity
            raw_cosine = float(np.dot(v1, v2))

            # Protect embeddings
            pv1 = protector.protect_embedding(v1)
            pv2 = protector.protect_embedding(v2)

            # Verify vectors were transformed
            self.assertFalse(np.allclose(v1, pv1))
            self.assertFalse(np.allclose(v2, pv2))

            # Calculate protected Cosine similarity
            protected_cosine = float(np.dot(pv1, pv2))

            # Verify Cosine Similarity is EXACTLY preserved under Orthogonal Projection
            self.assertAlmostEqual(raw_cosine, protected_cosine, places=5)

    def test_gdpr_article_17_guest_purge(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_db = Path(tmp_dir) / "test_purge.db"
            original_db_path = db.PRODUCTION_DB_PATH
            original_db_type = db.DB_TYPE
            original_use_supabase = db.USE_SUPABASE

            db.PRODUCTION_DB_PATH = temp_db
            db.DB_TYPE = "sqlite"
            db.USE_SUPABASE = False
            import app.db.connection as db_conn
            db_conn.DB_TYPE = "sqlite"
            db_conn.USE_SUPABASE = False

            conn = db.get_db_connection()
            db.ensure_schema(conn)

            # Insert an old guest and a fresh guest
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO customers (customer_id, name, registered_at, last_visit) VALUES (?, ?, ?, ?)",
                ("GUEST_2020_0001", "Guest 2020", "2020-01-01 00:00:00", "2020-01-01 00:00:00"),
            )
            cursor.execute(
                "INSERT INTO customers (customer_id, name, registered_at, last_visit) VALUES (?, ?, ?, ?)",
                ("GUEST_FRESH_9999", "Guest Fresh", "2099-01-01 00:00:00", "2099-01-01 00:00:00"),
            )
            conn.commit()

            result = purge_expired_guests(conn, retention_days=30)
            self.assertGreaterEqual(result["purged_guests_count"], 1)

            # Verify old guest was purged while fresh guest remains
            remaining = conn.execute("SELECT customer_id FROM customers").fetchall()
            remaining_ids = [r["customer_id"] for r in remaining]
            
            self.assertNotIn("GUEST_2020_0001", remaining_ids)
            self.assertIn("GUEST_FRESH_9999", remaining_ids)

            conn.close()

            # Restore original DB settings
            db.PRODUCTION_DB_PATH = original_db_path
            db.DB_TYPE = original_db_type
            db.USE_SUPABASE = original_use_supabase
            db_conn.DB_TYPE = original_db_type
            db_conn.USE_SUPABASE = original_use_supabase


if __name__ == "__main__":
    unittest.main()
