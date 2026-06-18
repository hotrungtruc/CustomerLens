"""
backfill_vectors.py — One-time migration to populate the pgvector `embedding`
column from existing BYTEA `face_embedding` blobs in customer_embeddings.

Usage:
    cd backend
    ..\.venv\Scripts\python.exe scripts/backfill_vectors.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import psycopg2
import psycopg2.extras
from db_config import DATABASE_URL, USE_SUPABASE

def main():
    if not USE_SUPABASE:
        print("ERROR: USE_SUPABASE is not enabled. This script only works with PostgreSQL/Supabase.")
        sys.exit(1)

    print("=== BACKFILL VECTORS START ===")
    print(f"Connecting to Supabase...")

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Ensure pgvector extension and column exist
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.execute(
        "ALTER TABLE customer_embeddings ADD COLUMN IF NOT EXISTS embedding vector(512)"
    )
    conn.commit()

    # Find rows that have a BYTEA blob but no vector yet
    cursor.execute(
        """
        SELECT id, customer_id, face_embedding, embedding_dim
        FROM customer_embeddings
        WHERE face_embedding IS NOT NULL AND embedding IS NULL
        """
    )
    rows = cursor.fetchall()
    print(f"Found {len(rows)} rows to backfill.")

    updated = 0
    skipped = 0

    for row in rows:
        blob = row["face_embedding"]
        dim = row["embedding_dim"] or 512

        # Convert BYTEA → numpy float32 array
        if isinstance(blob, memoryview):
            blob = bytes(blob)

        try:
            arr = np.frombuffer(blob, dtype=np.float32)
            if arr.size != dim:
                print(f"  SKIP id={row['id']} customer={row['customer_id']}: "
                      f"expected dim={dim}, got {arr.size}")
                skipped += 1
                continue

            # Normalize the embedding
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm

            # Format as pgvector literal: [0.1, 0.2, ...]
            vec_str = "[" + ",".join(f"{float(x):.8f}" for x in arr) + "]"

            cursor.execute(
                "UPDATE customer_embeddings SET embedding = %s::vector WHERE id = %s",
                (vec_str, row["id"]),
            )
            updated += 1
        except Exception as e:
            print(f"  ERROR id={row['id']}: {e}")
            skipped += 1

    conn.commit()
    print(f"\nBackfill complete:")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")

    # Create HNSW index if it doesn't exist
    print("Creating HNSW index (if not exists)...")
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_embeddings_hnsw
        ON customer_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    conn.commit()
    print("HNSW index ready.")

    # Verify
    cursor.execute(
        "SELECT COUNT(*) AS total, COUNT(embedding) AS with_vector FROM customer_embeddings"
    )
    stats = cursor.fetchone()
    print(f"\nVerification:")
    print(f"  Total rows: {stats['total']}")
    print(f"  With vector: {stats['with_vector']}")
    print(f"  Missing vector: {stats['total'] - stats['with_vector']}")

    cursor.close()
    conn.close()
    print("=== BACKFILL VECTORS END ===")


if __name__ == "__main__":
    main()
