"""
vector_cache.py — High-Performance L1 Local Vector Cache with Redis.

Implements an L1 in-memory / Redis vector cache layer to bypass database 
network latency (285ms -> <1ms) for frequent customer & VIP recognitions.
"""

import logging
import os
import time
import numpy as np
import redis

logger = logging.getLogger("VectorCache")

try:
    from config import REDIS_URL
except ImportError:
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

CACHE_KEY_PREFIX = "vec_cache:"
CACHE_META_KEY = "vec_cache_ids"
CACHE_TTL = 86400  # 24 hours

class VectorCacheManager:
    _instance = None
    _in_memory_cache = {}  # Fallback dictionary: customer_id -> np.ndarray (512,)
    _last_sync_time = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorCacheManager, cls).__new__(cls)
            cls._instance._init_redis()
        return cls._instance

    def _init_redis(self):
        try:
            self.redis_client = redis.from_url(REDIS_URL, socket_timeout=1.0)
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Connected to Redis Vector Cache successfully.")
        except Exception as e:
            self.redis_available = False
            logger.warning(f"Redis not available for vector cache ({e}). Using in-memory fallback.")

    def get_all_vectors(self):
        """Fetch all cached vectors as a tuple of (customer_ids, matrix_np)."""
        customer_ids = []
        vectors = []

        if self.redis_available:
            try:
                cached_ids = self.redis_client.smembers(CACHE_META_KEY)
                for cid_bytes in cached_ids:
                    cid = cid_bytes.decode('utf-8') if isinstance(cid_bytes, bytes) else str(cid_bytes)
                    vec_bytes = self.redis_client.get(f"{CACHE_KEY_PREFIX}{cid}")
                    if vec_bytes:
                        vec = np.frombuffer(vec_bytes, dtype=np.float32)
                        customer_ids.append(cid)
                        vectors.append(vec)
            except Exception as e:
                logger.error(f"Redis get_all_vectors failed: {e}")

        # Merge / fallback with in-memory cache
        for cid, vec in self._in_memory_cache.items():
            if cid not in customer_ids:
                customer_ids.append(cid)
                vectors.append(vec)

        if not customer_ids:
            return [], None

        matrix = np.vstack(vectors).astype(np.float32)
        return customer_ids, matrix

    def search_l1_cache(self, query_embedding: np.ndarray, top_k: int = 5, threshold: float = 0.55):
        """Perform fast L1 vector matrix search in NumPy (< 1ms)."""
        customer_ids, matrix = self.get_all_vectors()
        if matrix is None or len(customer_ids) == 0:
            return []

        q_vec = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        # Cosine similarity for normalized vectors is dot product
        sims = np.dot(matrix, q_vec)

        results = []
        top_indices = np.argsort(sims)[::-1][:top_k]
        for idx in top_indices:
            score = float(sims[idx])
            if score >= threshold:
                results.append((customer_ids[idx], score))

        return results

    def add_to_cache(self, customer_id: str, embedding_np: np.ndarray):
        """Add or update a customer vector in L1 Cache."""
        vec = np.asarray(embedding_np, dtype=np.float32).reshape(-1)
        self._in_memory_cache[str(customer_id)] = vec

        if self.redis_available:
            try:
                cid_str = str(customer_id)
                self.redis_client.setex(
                    f"{CACHE_KEY_PREFIX}{cid_str}",
                    CACHE_TTL,
                    vec.tobytes()
                )
                self.redis_client.sadd(CACHE_META_KEY, cid_str)
            except Exception as e:
                logger.error(f"Failed to write vector to Redis cache: {e}")

    def sync_from_database(self, conn):
        """Pre-populate / refresh L1 Vector Cache from PostgreSQL Database."""
        if time.time() - self._last_sync_time < 10:  # Rate limit sync to every 10s (giảm từ 30s)
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT customer_id, embedding::text
                FROM customer_embeddings
                WHERE embedding IS NOT NULL
                """
            )
            rows = cursor.fetchall()
            count = 0
            for row in rows:
                cid = str(row["customer_id"])
                vec_str = row["embedding"]
                if vec_str:
                    try:
                        clean_str = vec_str.strip("[]")
                        vec = np.fromstring(clean_str, sep=",", dtype=np.float32)
                        if len(vec) == 512:
                            norm = np.linalg.norm(vec)
                            if norm > 0:
                                vec = vec / norm
                            self.add_to_cache(cid, vec)
                            count += 1
                    except Exception:
                        pass

            self._last_sync_time = time.time()
            logger.info(f"L1 Vector Cache synced {count} embeddings from Database.")
        except Exception as e:
            logger.error(f"Failed to sync L1 Vector Cache from database: {e}")

# Global singleton
vector_cache_manager = VectorCacheManager()
