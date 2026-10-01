"""
Embedding math utilities.

All functions are pure (no I/O, no DB, no state) so they can be unit-tested
independently and reused by both the tracker and any vector search helpers.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_embedding(embedding) -> np.ndarray:
    """L2-normalize a 1-D or 2-D embedding array."""
    embedding = np.asarray(embedding, dtype=np.float32)
    if embedding.ndim == 1:
        norm = np.sqrt(np.dot(embedding, embedding))
        return embedding if norm == 0 else embedding / norm
    else:
        norm = np.linalg.norm(embedding, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        return embedding / norm


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def cosine_similarities(known_embeddings, embedding) -> np.ndarray:
    """
    Compute dot-product similarities between `embedding` and every row of
    `known_embeddings`.  Both inputs are assumed to be L2-normalised.

    Returns an empty array when `known_embeddings` is None or empty.
    """
    if known_embeddings is None:
        return np.array([], dtype=np.float32)
    known = np.asarray(known_embeddings, dtype=np.float32)
    if known.size == 0:
        return np.array([], dtype=np.float32)
    return np.dot(known, np.asarray(embedding, dtype=np.float32))


# ---------------------------------------------------------------------------
# Robust mean (outlier-resistant)
# ---------------------------------------------------------------------------

def calculate_robust_mean_embedding(
    embeddings, similarity_threshold: float = 0.45
) -> np.ndarray | None:
    """
    Compute a mean embedding while rejecting outliers.

    Outliers are embeddings whose *median* pairwise similarity to the others
    falls below ``similarity_threshold``.  This prevents "Frankenstein"
    embeddings when a track briefly swaps between two people.

    Returns None when the input list is empty.
    """
    if len(embeddings) == 0:
        return None
    if len(embeddings) <= 2:
        return normalize_embedding(np.mean(embeddings, axis=0))

    embs = np.array(embeddings, dtype=np.float32)
    sim_matrix = np.dot(embs, embs.T)
    median_sims = np.median(sim_matrix, axis=1)
    valid_indices = np.where(median_sims >= similarity_threshold)[0]

    if len(valid_indices) == 0:
        # Fallback: return the single embedding most similar to the rest
        return normalize_embedding(embs[int(np.argmax(median_sims))])

    return normalize_embedding(np.mean(embs[valid_indices], axis=0))


# ---------------------------------------------------------------------------
# BLOB helper (for DB storage)
# ---------------------------------------------------------------------------

def embedding_to_blob(embedding) -> tuple[bytes | None, int | None]:
    """Convert an embedding array to (bytes_blob, dim) for SQLite/PostgreSQL storage."""
    try:
        arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
        return arr.tobytes(), int(arr.size)
    except Exception:
        return None, None
