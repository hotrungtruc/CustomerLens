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

    try:
        cursor.execute(
            """
            SELECT customer_id,
                   1 - (embedding::halfvec(512) <=> %s::halfvec(512)) AS similarity
            FROM customer_embeddings
            WHERE embedding IS NOT NULL
            ORDER BY embedding::halfvec(512) <=> %s::halfvec(512)
            LIMIT %s
            """,
            (protected_embedding, protected_embedding, top_k),
        )
    except Exception:
        vec_str = _embedding_to_pgvector_literal(protected_embedding)
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
        vector_cache_manager.add_to_cache(cid, query_embedding)

    return results


def insert_embedding_with_vector(
    conn,
    customer_id: str,
    face_embedding_blob: bytes,
    embedding_np: np.ndarray,
    dim: int = 512,
    model_name: str = "edgeface_s_gamma_05",
):
    """Insert a new embedding row with both BYTEA and pgvector representations."""
    protected_embedding = biometric_protector.protect_embedding(embedding_np)
    protected_blob = np.asarray(protected_embedding, dtype=np.float32).tobytes()

    if DB_TYPE == "postgresql":
        try:
            conn.execute(
                """
                INSERT INTO customer_embeddings (
                    customer_id, embedding, updated_at
                ) VALUES (%s, %s::vector, CURRENT_TIMESTAMP)
                """,
                (customer_id, protected_embedding),
            )
        except Exception:
            vec_str = _embedding_to_pgvector_literal(protected_embedding)
            conn.execute(
                """
                INSERT INTO customer_embeddings (
                    customer_id, embedding, updated_at
                ) VALUES (%s, %s::vector, CURRENT_TIMESTAMP)
                """,
                (customer_id, vec_str),
            )
    else:
        vec_str = _embedding_to_pgvector_literal(protected_embedding)
        conn.execute(
            """
            INSERT INTO customer_embeddings (
                customer_id, face_embedding, embedding_dim, model_name,
                embedding, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (customer_id, protected_blob, dim, model_name, vec_str),
        )

    # Auto-populate into L1 Redis Vector Cache for <1ms sub-millisecond future lookups
    try:
        conn.commit()
    except Exception:
        pass
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
            emb_text = row["emb_text"]
        except TypeError:
            # Fallback if row is a tuple
            c_id = row[0]
            emb_text = row[1]

        if not emb_text or not isinstance(emb_text, str) or not emb_text.startswith("[") or not emb_text.endswith("]"):
            continue

        try:
            # Parse the text string back to a list of floats
            emb_list = [float(x) for x in emb_text[1:-1].split(",")]
            emb_np = np.array(emb_list, dtype=np.float32)

            if str(c_id).startswith("GUEST_"):
                guest_embeddings.append(emb_np)
                guest_ids.append(c_id)
            else:
                known_embeddings.append(emb_np)
                known_ids.append(c_id)
        except Exception:
            continue

    return known_embeddings, known_ids, guest_embeddings, guest_ids
