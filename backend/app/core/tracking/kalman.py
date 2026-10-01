"""
Kalman filter for bounding-box motion prediction.

Implements a constant-velocity model over the four bbox corners (x1, y1, x2, y2).
State vector: [x1, y1, x2, y2, vx1, vy1, vx2, vy2]^T
"""

import numpy as np


class KalmanFilterCorner:
    """Constant-velocity Kalman Filter tracking bounding-box corners."""

    def __init__(self, bbox):
        x1, y1, x2, y2 = bbox
        # State: [x1, y1, x2, y2, vx1, vy1, vx2, vy2]
        self.x = np.array([x1, y1, x2, y2, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

        # State covariance P
        self.P = np.eye(8, dtype=np.float32) * 10.0
        self.P[4:, 4:] *= 10.0

        # Transition matrix F  (constant-velocity)
        self.F = np.eye(8, dtype=np.float32)
        self.F[0, 4] = self.F[1, 5] = self.F[2, 6] = self.F[3, 7] = 1.0

        # Measurement matrix H  (observe position only)
        self.H = np.zeros((4, 8), dtype=np.float32)
        self.H[0, 0] = self.H[1, 1] = self.H[2, 2] = self.H[3, 3] = 1.0

        # Process noise Q
        self.Q = np.eye(8, dtype=np.float32) * 0.1
        self.Q[4:, 4:] *= 0.5

        # Measurement noise R
        self.R = np.eye(4, dtype=np.float32) * 1.0

    # ------------------------------------------------------------------
    def predict(self) -> np.ndarray:
        """Predict next position; returns predicted bbox (x1, y1, x2, y2)."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x[:4]

    def update(self, bbox) -> np.ndarray:
        """Correct state with a new measurement; returns updated bbox."""
        z = np.array(bbox, dtype=np.float32)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = self.P - K @ self.H @ self.P
        return self.x[:4]
