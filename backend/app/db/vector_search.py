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


def search_similar_faces(
    conn,
    query_embedding: np.ndarray,
    top_k: int = 5,
    threshold: float = 0.50,
):
    """Find the top_k most similar face embeddings using the HNSW index.

    Uses cosine distance (<=>). pgvector's <=> returns distance in [0, 2],
    so similarity = 1 - distance.

    Returns a list of (customer_id, similarity) tuples above the threshold,
    ordered from most to least similar.
    """
    if DB_TYPE != "postgresql":
        return []

    vec_str = _embedding_to_pgvector_literal(query_embedding)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT customer_id,
               1 - (embedding::halfvec <=> %s::halfvec) AS similarity
        FROM customer_embeddings
        WHERE embedding IS NOT NULL
        ORDER BY embedding::halfvec <=> %s::halfvec
        LIMIT %s
        """,
        (vec_str, vec_str, top_k),
    )
    rows = cursor.fetchall()
    return [
        (row["customer_id"], float(row["similarity"]))
        for row in rows
        if float(row["similarity"]) >= threshold
    ]


def insert_embedding_with_vector(
    conn,
    customer_id: str,
    face_embedding_blob: bytes,
    embedding_np: np.ndarray,
    dim: int = 512,
    model_name: str = "edgeface_s_gamma_05",
):
    """Insert a new embedding row with both BYTEA and pgvector representations.

    This dual-write ensures backward compatibility with code that reads
    the BYTEA column while enabling HNSW search on the vector column.
    """
    vec_str = _embedding_to_pgvector_literal(embedding_np)
    if DB_TYPE == "postgresql":
        # Plain INSERT — customer_embeddings has no UNIQUE constraint on
        # customer_id (it uses id SERIAL PK), so ON CONFLICT would crash.
        conn.execute(
            """
            INSERT INTO customer_embeddings (
                customer_id, embedding, updated_at
            ) VALUES (%s, %s::vector, CURRENT_TIMESTAMP)
            """,
            (customer_id, vec_str),
        )
    else:
        conn.execute(
            """
            INSERT INTO customer_embeddings (
                customer_id, face_embedding, embedding_dim, model_name,
                embedding, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (customer_id, face_embedding_blob, dim, model_name, vec_str),
        )


def fetch_all_embeddings_from_db(conn):
    """Fetch all face embeddings from the database.

    Returns four lists:
        known_embeddings, known_ids, guest_embeddings, guest_ids
    """
    if DB_TYPE != "postgresql":
        return [], [], [], []

    cursor = conn.cursor()
    # Fetch customer_id and the vector representation as text (e.g. '[0.1, 0.2, ...]')
    cursor.execute(
        """
        SELECT customer_id, embedding::text AS emb_text
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
        c_id = row["customer_id"]
        emb_text = row["emb_text"]

        if not emb_text or not emb_text.startswith("[") or not emb_text.endswith("]"):
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
