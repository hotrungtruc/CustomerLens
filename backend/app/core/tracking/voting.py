"""
Confidence voting logic for face recognition.

Three-tier decision strategy (fastest → slowest):
  1. EARLY-1:   1 frame  with similarity >= HIGH_CONF  → instant decision
  2. EARLY-2:   2 consecutive frames at MED_CONF matching same ID
  3. STANDARD:  majority vote ≥ 3/5 recent frames at base threshold

All functions are stateless — they operate on a TrackState's `recent_votes`
list and return the resolved customer_id (or None).
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import numpy as np

from app.core.tracking.embedding_utils import cosine_similarities

if TYPE_CHECKING:
    from app.core.tracking.guest_tracker import TrackState

from config import RECOGNITION_HIGH_CONF_THRESHOLD, RECOGNITION_MED_CONF_THRESHOLD


# ---------------------------------------------------------------------------
# IoU helper (used by the tracker's matching stage)
# ---------------------------------------------------------------------------

def bbox_iou(box_a: tuple, box_b: tuple) -> float:
    """Intersection-over-Union for two bounding boxes (x1, y1, x2, y2)."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter_w = max(0, inter_x2 - inter_x1 + 1)
    inter_h = max(0, inter_y2 - inter_y1 + 1)
    inter_area = inter_w * inter_h

    area_a = max(0, ax2 - ax1 + 1) * max(0, ay2 - ay1 + 1)
    area_b = max(0, bx2 - bx1 + 1) * max(0, by2 - by1 + 1)
    denom = area_a + area_b - inter_area
    return inter_area / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# Vote accumulation
# ---------------------------------------------------------------------------

def cast_vote(
    track: "TrackState",
    voted_id: str | None,
    voted_sim: float,
    *,
    max_votes: int = 5,
) -> str | None:
    """
    Append a (voted_id, voted_sim) pair to track.recent_votes and apply
    EARLY-1 if the similarity clears HIGH_CONF.

    Returns the resolved customer_id if EARLY-1 fires, else None.
    """
    track.recent_votes.append((voted_id, voted_sim))
    if len(track.recent_votes) > max_votes:
        track.recent_votes = track.recent_votes[-max_votes:]

    # EARLY-1: single high-confidence frame
    if voted_id is not None and voted_sim >= RECOGNITION_HIGH_CONF_THRESHOLD:
        track.resolved_customer_id = voted_id
        return voted_id
    return None


def resolve_from_votes(track: "TrackState") -> str | None:
    """
    Apply EARLY-2 and STANDARD voting to the accumulated recent_votes.
    Mutates track.resolved_customer_id on success.

    Returns the resolved customer_id or None.
    """
    # EARLY-2: 2 consecutive frames at MED_CONF agreeing on the same ID
    if len(track.recent_votes) >= 2:
        recent_2 = track.recent_votes[-2:]
        valid_med = [
            (vid, vsim)
            for vid, vsim in recent_2
            if vid is not None and vsim >= RECOGNITION_MED_CONF_THRESHOLD
        ]
        if len(valid_med) == 2 and valid_med[0][0] == valid_med[1][0]:
            track.resolved_customer_id = valid_med[0][0]
            return valid_med[0][0]

    # STANDARD: majority ≥ 3 / 5 frames at base threshold
    if len(track.recent_votes) >= 3:
        valid_ids = [vid for vid, _ in track.recent_votes if vid is not None]
        if valid_ids:
            top_id, top_count = Counter(valid_ids).most_common(1)[0]
            if top_count >= 3:
                track.resolved_customer_id = top_id
                return top_id

    return None


# ---------------------------------------------------------------------------
# pgvector path: query + vote
# ---------------------------------------------------------------------------

def vote_pgvector(
    track: "TrackState",
    current_emb: np.ndarray,
    query_fn,          # callable(emb, top_k, threshold) → [(id, sim), ...]
    similarity_threshold: float,
    guest_embeddings: list,
    guest_ids: list,
) -> str | None:
    """
    Run the pgvector HNSW query, push the result into the vote buffer, and
    apply all three decision tiers.

    ``query_fn`` is expected to be ``GuestTrackManager._query_pgvector``.
    Returns the resolved customer_id or None.
    """
    results = query_fn(current_emb, top_k=1, threshold=similarity_threshold)
    if results:
        voted_id, voted_sim = results[0]
        resolved = cast_vote(track, voted_id, voted_sim)
        if resolved:
            return resolved
    else:
        # Fall back to in-memory guest embeddings (not yet persisted)
        from app.core.biometric_security import biometric_protector
        protected_current = biometric_protector.protect_embedding(current_emb)
        voted_id, voted_sim = _best_guest_match(
            guest_embeddings, guest_ids, protected_current, similarity_threshold
        )
        resolved = cast_vote(track, voted_id, voted_sim)
        if resolved:
            return resolved

    if not track.resolved_customer_id:
        return resolve_from_votes(track)
    return None


# ---------------------------------------------------------------------------
# In-memory path: cosine search + vote
# ---------------------------------------------------------------------------

def vote_in_memory(
    track: "TrackState",
    current_emb: np.ndarray,
    known_embeddings: list,
    known_ids: list,
    guest_embeddings: list,
    guest_ids: list,
    similarity_threshold: float,
) -> str | None:
    """
    Compute cosine similarity against combined known+guest embeddings,
    push into vote buffer, and apply all three decision tiers.

    Returns the resolved customer_id or None.
    """
    combined = list(known_embeddings) + list(guest_embeddings)
    combined_ids = list(known_ids) + list(guest_ids)

    if not combined:
        return None

    sims = cosine_similarities(combined, current_emb)
    if sims.size == 0:
        return None

    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])

    voted_id = combined_ids[best_idx] if best_sim >= similarity_threshold else None
    resolved = cast_vote(track, voted_id, best_sim)
    if resolved:
        return resolved

    if not track.resolved_customer_id:
        return resolve_from_votes(track)
    return None


# ---------------------------------------------------------------------------
# Private helper
# ---------------------------------------------------------------------------

def _best_guest_match(
    guest_embeddings: list,
    guest_ids: list,
    embedding: np.ndarray,
    threshold: float,
) -> tuple[str | None, float]:
    if not guest_embeddings:
        return None, 0.0
    sims = cosine_similarities(guest_embeddings, embedding)
    if sims.size == 0:
        return None, 0.0
    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])
    if best_sim >= threshold:
        return guest_ids[best_idx], best_sim
    return None, 0.0
