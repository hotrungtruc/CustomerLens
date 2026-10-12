"""
oc_sort.py — Observation-Centric SORT (OC-SORT) for Edge Face Tracking.

Paper: "Observation-Centric SORT: Rethinking SORT for Robust Multi-Object Tracking" (CVPR 2023)
Features:
  1. Kalman Filter tracking in [x, y, s, r] state space.
  2. Observation-Centric Online Smoothing (OOS) to correct accumulated error when tracks re-emerge.
  3. Velocity Direction Consistency (VDC) to penalize discordant motion directions.
  4. Observation-Centric Recovery (OCR) to recover lost tracks using their last observed positions.
"""

from typing import List, Optional, Tuple
import numpy as np
from filterpy.kalman import KalmanFilter
from scipy.optimize import linear_sum_assignment


def box_iou(boxes1: np.ndarray, boxes2: np.ndarray) -> np.ndarray:
    """Computes pairwise IoU between two arrays of boxes [N, 4] and [M, 4]."""
    if len(boxes1) == 0 or len(boxes2) == 0:
        return np.empty((len(boxes1), len(boxes2)), dtype=np.float32)

    boxes1 = np.ascontiguousarray(boxes1, dtype=np.float32)
    boxes2 = np.ascontiguousarray(boxes2, dtype=np.float32)

    area1 = (boxes1[:, 2] - boxes1[:, 0]) * (boxes1[:, 3] - boxes1[:, 1])
    area2 = (boxes2[:, 2] - boxes2[:, 0]) * (boxes2[:, 3] - boxes2[:, 1])

    lt = np.maximum(boxes1[:, None, :2], boxes2[:, :2])
    rb = np.minimum(boxes1[:, None, 2:], boxes2[:, 2:])
    wh = np.clip(rb - lt, a_min=0, a_max=None)
    inter = wh[:, :, 0] * wh[:, :, 1]

    union = area1[:, None] + area2 - inter
    iou = inter / np.clip(union, a_min=1e-6, a_max=None)
    return iou


def convert_bbox_to_z(bbox: np.ndarray) -> np.ndarray:
    """Takes [x1, y1, x2, y2] and returns z = [x, y, s, r]^T."""
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = bbox[0] + w / 2.0
    y = bbox[1] + h / 2.0
    s = w * h  # scale is area
    r = w / float(h) if h > 0 else 1.0
    return np.array([x, y, s, r]).reshape((4, 1))


def convert_x_to_bbox(x: np.ndarray, score: Optional[float] = None) -> np.ndarray:
    """Takes state x = [x, y, s, r, ...] and returns [x1, y1, x2, y2]."""
    w = np.sqrt(max(1e-4, x[2] * x[3]))
    h = x[2] / max(1e-4, w)
    x1 = x[0] - w / 2.0
    y1 = x[1] - h / 2.0
    x2 = x[0] + w / 2.0
    y2 = x[1] + h / 2.0
    if score is None:
        return np.array([x1, y1, x2, y2]).reshape((1, 4))
    else:
        return np.array([x1, y1, x2, y2, score]).reshape((1, 5))


def speed_direction_batch(dets: np.ndarray, tracks: np.ndarray) -> np.ndarray:
    """
    Computes difference angle cost for Velocity Direction Consistency (VDC).
    Returns matrix of shape (num_tracks, num_dets) in range [0, 1].
    """
    if len(tracks) == 0 or len(dets) == 0:
        return np.zeros((len(tracks), len(dets)), dtype=np.float32)

    # tracks: (N, 2) velocity vectors
    # dets: (M, 2) center positions relative to tracks
    tracks_norm = np.linalg.norm(tracks, axis=1, keepdims=True)
    dets_norm = np.linalg.norm(dets, axis=1, keepdims=True)

    tracks_norm[tracks_norm == 0] = 1e-6
    dets_norm[dets_norm == 0] = 1e-6

    unit_tracks = tracks / tracks_norm
    unit_dets = dets / dets_norm

    # Dot product gives cos(theta)
    cos_theta = np.dot(unit_tracks, unit_dets.T)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)

    # Convert to cost: cos = 1 -> cost = 0, cos = -1 -> cost = 1
    direction_cost = 0.5 * (1.0 - cos_theta)
    return direction_cost


class KalmanBoxTracker:
    """Kalman Filter Tracker tracking single bounding box state with OOS."""
    count = 0

    def __init__(self, bbox: np.ndarray, delta_t: int = 3, landmarks: Optional[np.ndarray] = None):
        # Initialize 7-state Kalman Filter: [x, y, s, r, vx, vy, vs]
        self.kf = KalmanFilter(dim_x=7, dim_z=4)
        self.kf.F = np.array([
            [1, 0, 0, 0, 1, 0, 0],
            [0, 1, 0, 0, 0, 1, 0],
            [0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 1],
        ], dtype=np.float32)

        self.kf.H = np.array([
            [1, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0],
        ], dtype=np.float32)

        self.kf.R[2:, 2:] *= 10.0
        self.kf.P[4:, 4:] *= 1000.0  # High uncertainty on initial velocity
        self.kf.P *= 10.0
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01

        self.kf.x[:4] = convert_bbox_to_z(bbox)

        self.time_since_update = 0
        self.id = KalmanBoxTracker.count
        KalmanBoxTracker.count += 1
        self.history = []
        self.hits = 0
        self.hit_streak = 0
        self.age = 0

        # OC-SORT specific attributes
        self.delta_t = delta_t
        self.observations = {}  # {age: z}
        self.observations[self.age] = bbox[:4]
        self.last_observation = bbox[:4].copy()
        self.score = float(bbox[4]) if len(bbox) > 4 else 1.0
        self.velocity = np.zeros(2, dtype=np.float32)
        self.landmarks = landmarks

    def update(self, bbox: np.ndarray, landmarks: Optional[np.ndarray] = None):
        """Updates tracker state with observed bbox [x1, y1, x2, y2, (score)]."""
        self.time_since_update = 0
        self.history = []
        self.hits += 1
        self.hit_streak += 1
        self.score = float(bbox[4]) if len(bbox) > 4 else self.score
        if landmarks is not None:
            self.landmarks = landmarks

        # Observation-Centric Online Smoothing (OOS)
        # When track is re-observed after multiple missing frames:
        if self.time_since_update == 0 and len(self.observations) > 0:
            previous_ages = sorted(self.observations.keys())
            if len(previous_ages) >= 1:
                last_age = previous_ages[-1]
                dt = self.age - last_age
                if dt >= 2:
                    # Smoothing velocity over actual observation interval
                    prev_box = self.observations[last_age]
                    prev_center = np.array([(prev_box[0] + prev_box[2]) / 2.0, (prev_box[1] + prev_box[3]) / 2.0])
                    new_center = np.array([(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0])
                    smoothed_v = (new_center - prev_center) / float(dt)
                    self.kf.x[4:6] = smoothed_v.reshape((2, 1))

        # Standard Kalman update
        self.kf.update(convert_bbox_to_z(bbox))

        # Record observation
        self.observations[self.age] = bbox[:4].copy()
        self.last_observation = bbox[:4].copy()

        # Update velocity estimate for VDC
        if len(self.observations) >= 2:
            ages = sorted(self.observations.keys())
            box_new = self.observations[ages[-1]]
            box_old = self.observations[ages[-2]]
            c_new = np.array([(box_new[0] + box_new[2]) / 2.0, (box_new[1] + box_new[3]) / 2.0])
            c_old = np.array([(box_old[0] + box_old[2]) / 2.0, (box_old[1] + box_old[3]) / 2.0])
            dt = max(1, ages[-1] - ages[-2])
            self.velocity = (c_new - c_old) / float(dt)

    def predict(self) -> np.ndarray:
        """Advances state vector and returns predicted bounding box."""
        if self.kf.x[6] + self.kf.x[2] <= 0:
            self.kf.x[6] *= 0.0

        self.kf.predict()
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        self.history.append(convert_x_to_bbox(self.kf.x))
        return self.history[-1][0]

    def get_state(self) -> np.ndarray:
        """Returns current bounding box estimate [x1, y1, x2, y2]."""
        return convert_x_to_bbox(self.kf.x)[0]


class OCSort:
    """
    Observation-Centric SORT (OC-SORT) tracker.
    Provides robust tracking resistant to occlusion and non-linear face motion.
    """

    def __init__(
        self,
        det_thresh: float = 0.4,
        max_age: int = 30,
        min_hits: int = 2,
        iou_threshold: float = 0.3,
        delta_t: int = 3,
        inertia: float = 0.2,
    ):
        self.det_thresh = det_thresh
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.delta_t = delta_t
        self.inertia = inertia
        self.trackers: List[KalmanBoxTracker] = []
        self.frame_count = 0

    def update(
        self,
        dets: np.ndarray,
        landmarks: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Updates trackers with detections.
        dets: np.ndarray [N, 5] of [x1, y1, x2, y2, score]
        landmarks: Optional np.ndarray [N, 5, 2]
        Returns:
            tracked_boxes: [M, 6] of [x1, y1, x2, y2, track_id, score]
            tracked_landmarks: [M, 5, 2]
        """
        self.frame_count += 1

        if dets is None or len(dets) == 0:
            dets = np.empty((0, 5), dtype=np.float32)
        elif dets.shape[1] == 4:
            # Add dummy confidence 1.0 if not provided
            scores = np.ones((dets.shape[0], 1), dtype=np.float32)
            dets = np.hstack([dets, scores])

        # Separate detections into confident and low-confidence
        remain_inds = dets[:, 4] >= self.det_thresh
        dets_first = dets[remain_inds]
        lms_first = landmarks[remain_inds] if landmarks is not None and len(landmarks) == len(dets) else None

        # Predict positions of existing trackers
        trks = np.zeros((len(self.trackers), 5))
        to_del = []
        for t, trk in enumerate(self.trackers):
            pos = trk.predict()
            trks[t, :4] = pos
            trks[t, 4] = trk.score
            if np.any(np.isnan(pos)):
                to_del.append(t)

        for t in reversed(to_del):
            self.trackers.pop(t)
        trks = np.delete(trks, to_del, axis=0)

        # -------------------------------------------------------------
        # Association Round 1: Active Trackers vs Confident Detections (VDC)
        # -------------------------------------------------------------
        matched_a, unmatched_dets, unmatched_trks = self._associate(
            dets_first,
            trks,
            self.iou_threshold,
            velocities=[t.velocity for t in self.trackers],
            previous_obs=[t.last_observation for t in self.trackers],
        )

        # Update matched trackers
        for m in matched_a:
            det_idx = m[0]
            trk_idx = m[1]
            lm = lms_first[det_idx] if lms_first is not None else None
            self.trackers[trk_idx].update(dets_first[det_idx], landmarks=lm)

        # -------------------------------------------------------------
        # Association Round 2: OCR (Observation-Centric Recovery)
        # Recover unmatched detections with last observation of unmatched tracks
        # -------------------------------------------------------------
        if len(unmatched_dets) > 0 and len(unmatched_trks) > 0:
            leftover_dets = dets_first[unmatched_dets]
            leftover_lms = lms_first[unmatched_dets] if lms_first is not None else None

            # Use last observation instead of drifted Kalman prediction
            last_obs = np.array([self.trackers[t].last_observation for t in unmatched_trks])
            iou_matrix_ocr = box_iou(leftover_dets[:, :4], last_obs[:, :4])

            if iou_matrix_ocr.size > 0:
                row_ind, col_ind = linear_sum_assignment(-iou_matrix_ocr)
                ocr_matched_dets = []
                for r, c in zip(row_ind, col_ind):
                    if iou_matrix_ocr[r, c] >= self.iou_threshold:
                        actual_det_idx = unmatched_dets[r]
                        actual_trk_idx = unmatched_trks[c]
                        lm = leftover_lms[r] if leftover_lms is not None else None
                        self.trackers[actual_trk_idx].update(dets_first[actual_det_idx], landmarks=lm)
                        ocr_matched_dets.append(actual_det_idx)

                unmatched_dets = [d for d in unmatched_dets if d not in ocr_matched_dets]

        # -------------------------------------------------------------
        # Create new trackers for unmatched confident detections
        # -------------------------------------------------------------
        for i in unmatched_dets:
            lm = lms_first[i] if lms_first is not None else None
            trk = KalmanBoxTracker(dets_first[i], delta_t=self.delta_t, landmarks=lm)
            self.trackers.append(trk)

        # -------------------------------------------------------------
        # Build active track results
        # -------------------------------------------------------------
        results = []
        result_landmarks = []
        i = len(self.trackers)
        for trk in reversed(self.trackers):
            d = trk.get_state()
            if (trk.time_since_update < 1) and (trk.hit_streak >= self.min_hits or self.frame_count <= self.min_hits):
                results.append(np.array([d[0], d[1], d[2], d[3], trk.id, trk.score]))
                result_landmarks.append(trk.landmarks if trk.landmarks is not None else np.zeros((5, 2)))
            i -= 1
            # Remove expired tracks
            if trk.time_since_update > self.max_age:
                self.trackers.pop(i)

        if len(results) > 0:
            res_arr = np.stack(results, axis=0)
            res_lm = np.stack(result_landmarks, axis=0) if landmarks is not None else None
            return res_arr, res_lm

        return np.empty((0, 6)), (np.empty((0, 5, 2)) if landmarks is not None else None)

    def _associate(
        self,
        dets: np.ndarray,
        trks: np.ndarray,
        iou_threshold: float,
        velocities: List[np.ndarray],
        previous_obs: List[np.ndarray],
    ) -> Tuple[np.ndarray, List[int], List[int]]:
        """Pairwise association using IoU + Velocity Direction Consistency."""
        if len(trks) == 0:
            return np.empty((0, 2), dtype=int), list(range(len(dets))), []
        if len(dets) == 0:
            return np.empty((0, 2), dtype=int), [], list(range(len(trks)))

        iou_matrix = box_iou(dets[:, :4], trks[:, :4])

        # Velocity Direction Consistency (VDC)
        # Difference angle penalty: cost = (1 - IoU) + inertia * direction_cost
        cost_matrix = 1.0 - iou_matrix

        if self.inertia > 0 and len(velocities) > 0:
            # Compute center displacements
            det_centers = np.array([
                [(d[0] + d[2]) / 2.0, (d[1] + d[3]) / 2.0] for d in dets
            ])
            trk_centers = np.array([
                [(p[0] + p[2]) / 2.0, (p[1] + p[3]) / 2.0] for p in previous_obs
            ])
            # Direction vectors from trk to det: (num_trks, num_dets, 2)
            disp_vectors = det_centers[None, :, :] - trk_centers[:, None, :]  # shape (N_trk, N_det, 2)
            trk_velocities = np.array(velocities)  # shape (N_trk, 2)

            # Dot products
            norm_v = np.linalg.norm(trk_velocities, axis=1, keepdims=True)  # (N_trk, 1)
            norm_d = np.linalg.norm(disp_vectors, axis=2)  # (N_trk, N_det)
            norm_v[norm_v == 0] = 1e-6
            norm_d[norm_d == 0] = 1e-6

            dot = np.sum(trk_velocities[:, None, :] * disp_vectors, axis=2)  # (N_trk, N_det)
            cos_theta = dot / (norm_v * norm_d)
            cos_theta = np.clip(cos_theta, -1.0, 1.0)
            direction_cost = (0.5 * (1.0 - cos_theta)).T  # shape (N_det, N_trk)

            cost_matrix += self.inertia * direction_cost

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matched_indices = []
        unmatched_dets = list(range(len(dets)))
        unmatched_trks = list(range(len(trks)))

        for r, c in zip(row_ind, col_ind):
            # Only match if IoU satisfies threshold
            if iou_matrix[r, c] >= iou_threshold:
                matched_indices.append([r, c])
                if r in unmatched_dets:
                    unmatched_dets.remove(r)
                if c in unmatched_trks:
                    unmatched_trks.remove(c)

        if len(matched_indices) == 0:
            return np.empty((0, 2), dtype=int), unmatched_dets, unmatched_trks

        return np.array(matched_indices), unmatched_dets, unmatched_trks
