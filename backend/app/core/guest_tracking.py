"""
Backward-compatible facade for the tracking layer.

New code should import directly from:
  app.core.tracking.guest_tracker    → GuestTrackManager, TrackState
  app.core.tracking.embedding_utils  → normalize_embedding, cosine_similarities, …
  app.core.tracking.kalman            → KalmanFilterCorner
  app.core.tracking.voting            → bbox_iou, vote_pgvector, vote_in_memory, …
"""

# Primary public API (used by devices.py and ai_worker.py)
from app.core.tracking.guest_tracker import GuestTrackManager, TrackState  # noqa: F401

# Math helpers (used by vector_search, ai_worker, tests)
from app.core.tracking.embedding_utils import (  # noqa: F401
    normalize_embedding,
    cosine_similarities,
    calculate_robust_mean_embedding,
    embedding_to_blob,
)

# Geometry (used by tracking internally; exported for any external callers)
from app.core.tracking.voting import bbox_iou  # noqa: F401

# Kalman filter
from app.core.tracking.kalman import KalmanFilterCorner  # noqa: F401
