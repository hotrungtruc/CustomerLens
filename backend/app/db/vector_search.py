"""
vector_search.py — pgvector-based face embedding similarity search.

Uses the HNSW index on customer_embeddings.embedding for sub-millisecond
approximate nearest-neighbor queries.  Falls back gracefully when the
vector column has not been populated yet.
"""

import numpy as np
from db_config import DB_TYPE


def _embedding_to_pgvector_literal(embedding: np.ndarray) -> str:
    """Convert a numpy embedding to pgvector literal string format: '[0.1,0.2,...]'."""
    arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
    return "[" + ",".join(f"{float(x):.8f}" for x in arr) + "]"


from app.core.vector_cache import vector_cache_manager
from app.core.biometric_security import biometric_protector


def search_similar_faces(
    conn,
    query_embedding: np.ndarray,
    top_k: int = 5,
    threshold: float = 0.55,
):
    """Find the top_k most similar face embeddings using L1 Redis Cache and HNSW index."""
    # Apply Cancelable Biometrics Orthogonal Projection
    protected_embedding = biometric_protector.protect_embedding(query_embedding)

    # 1. Fast L1 Local Vector Cache Search (< 1ms)
    l1_hits = vector_cache_manager.search_l1_cache(protected_embedding, top_k=top_k, threshold=threshold)
    if l1_hits:
        return l1_hits

    if DB_TYPE != "postgresql":
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT customer_id, face_embedding FROM customer_embeddings WHERE face_embedding IS NOT NULL")
            rows = cursor.fetchall()
            results = []
            q_norm = protected_embedding / (np.linalg.norm(protected_embedding) or 1.0)
            for row in rows:
                cid = row["customer_id"]
                blob = row["face_embedding"]
                emb = None
                if isinstance(blob, (bytes, memoryview)):
                    try:
                        emb = np.frombuffer(blob, dtype=np.float32)
                    except Exception:
                        emb = None
                elif isinstance(blob, (list, tuple)):
                    emb = np.asarray(blob, dtype=np.float32)
                elif isinstance(blob, str) and blob.startswith("[") and blob.endswith("]"):
                    try:
                        emb = np.fromstring(blob[1:-1], dtype=np.float32, sep=",")
                    except Exception:
                        emb = None
                if emb is not None and len(emb) == 512:
                    emb = np.asarray(emb, dtype=np.float32)
                    emb_norm = emb / (np.linalg.norm(emb) or 1.0)
                    sim = float(np.dot(emb_norm, q_norm))
                    if sim >= threshold:
                        results.append((cid, sim))
            results.sort(key=lambda x: x[1], reverse=True)
            for cid, _ in results:
                vector_cache_manager.add_to_cache(cid, protected_embedding)
            return results[:top_k]
        except Exception as e:
            return []


    # Sync cache if empty or stale
    try:
        vector_cache_manager.sync_from_database(conn)
        l1_hits = vector_cache_manager.search_l1_cache(protected_embedding, top_k=top_k, threshold=threshold)
        if l1_hits:
            return l1_hits
    except Exception:
        pass

    cursor = conn.cursor()
    try:
        cursor.execute("SET LOCAL hnsw.ef_search = 200;")
    except Exception:
        pass

    vec_str = _embedding_to_pgvector_literal(protected_embedding)
    try:
        cursor.execute(
            """
            SELECT customer_id,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM customer_embeddings
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vec_str, vec_str, top_k),
        )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT customer_id,
                   1 - (embedding::halfvec(512) <=> %s::halfvec(512)) AS similarity
            FROM customer_embeddings
            WHERE embedding IS NOT NULL
            ORDER BY embedding::halfvec(512) <=> %s::halfvec(512)
            LIMIT %s
            """,
            (vec_str, vec_str, top_k),
        )

    rows = cursor.fetchall()
    results = [
        (row["customer_id"], float(row["similarity"]))
        for row in rows
        if float(row["similarity"]) >= threshold
    ]

    # Populate L1 Cache for hits
    for cid, _ in results:
        vector_cache_manager.add_to_cache(cid, protected_embedding)

    return results


def insert_embedding_with_vector(
    conn,
    customer_id: str,
    face_embedding_blob: bytes,
    embedding_np: np.ndarray,
    dim: int = 512,
    model_name: str = "edgeface_int8",
):
    """Insert a new embedding row with both BYTEA and pgvector representations."""
    protected_embedding = biometric_protector.protect_embedding(embedding_np)
    protected_blob = np.asarray(protected_embedding, dtype=np.float32).tobytes()

    if DB_TYPE == "postgresql":
        try:
            import psycopg2
            raw_blob = psycopg2.Binary(protected_blob)
        except Exception:
            raw_blob = protected_blob

        vec_str = _embedding_to_pgvector_literal(protected_embedding)
        try:
            conn.execute(
                "DELETE FROM customer_embeddings WHERE customer_id = %s;",
                (customer_id,),
            )
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

        try:
            conn.execute(
                """
                INSERT INTO customer_embeddings (
                    customer_id, face_embedding, embedding_dim, model_name,
                    created_at, updated_at, embedding
                ) VALUES (
                    %s, %s, %s, %s,
                    CURRENT_TIMESTAMP::text, CURRENT_TIMESTAMP::text, %s::vector
                )
                """,
                (
                    customer_id,
                    raw_blob,
                    dim,
                    model_name or "edgeface_int8",
                    vec_str,
                ),
            )
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            raise e
    else:
        vec_str = _embedding_to_pgvector_literal(protected_embedding)
        try:
            conn.execute(
                "DELETE FROM customer_embeddings WHERE customer_id = ?",
                (customer_id,),
            )
        except Exception:
            pass
        conn.execute(
            """
            INSERT INTO customer_embeddings (
                customer_id, face_embedding, embedding_dim, model_name,
                embedding, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (customer_id, protected_blob, dim, model_name or "edgeface_int8", vec_str),
        )
        try:
            conn.commit()
        except Exception:
            pass

    # Auto-populate into L1 Redis Vector Cache for <1ms sub-millisecond future lookups
    try:
        vector_cache_manager.add_to_cache(customer_id, protected_embedding)
    except Exception:
        pass


def fetch_all_embeddings_from_db(conn):
    """Fetch all face embeddings from the database.

    Returns four lists:
        known_embeddings, known_ids, guest_embeddings, guest_ids
    """
    cursor = conn.cursor()
    
    if DB_TYPE == "postgresql":
        # Fetch customer_id and the vector representation as text (e.g. '[0.1, 0.2, ...]')
        cursor.execute(
            """
            SELECT customer_id, embedding::text AS emb_text
            FROM customer_embeddings
            WHERE embedding IS NOT NULL
            """
        )
    else:
        cursor.execute(
            """
            SELECT customer_id, embedding AS emb_text
            FROM customer_embeddings
            WHERE embedding IS NOT NULL
            """
        )
        
    rows = cursor.fetchall()

    known_embeddings = []
    known_ids = []
    guest_embeddings = []
    guest_ids = []

    for row in rows:
        try:
            c_id = row["customer_id"]
            emb_data = row["emb_text"]
        except TypeError:
            # Fallback if row is a tuple
            c_id = row[0]
            emb_data = row[1]

        if not emb_data or not c_id:
            continue

        try:
            emb_np = None
            if isinstance(emb_data, (bytes, memoryview)):
                emb_np = np.frombuffer(emb_data, dtype=np.float32)
            elif isinstance(emb_data, (list, tuple)):
                emb_np = np.asarray(emb_data, dtype=np.float32)
            elif isinstance(emb_data, str) and emb_data.startswith("[") and emb_data.endswith("]"):
                emb_np = np.fromstring(emb_data[1:-1], dtype=np.float32, sep=",")

            if emb_np is None or len(emb_np) == 0:
                continue

            if str(c_id).startswith("GUEST_") or str(c_id).startswith("LN"):
                guest_embeddings.append(emb_np)
                guest_ids.append(c_id)
            else:
                known_embeddings.append(emb_np)
                known_ids.append(c_id)
        except Exception:
            continue

    return known_embeddings, known_ids, guest_embeddings, guest_ids
