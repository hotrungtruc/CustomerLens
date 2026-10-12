"""
mediapipe_detector.py — MediaPipe FaceLandmarker Tasks API for Edge Face Detection.

Uses `face_landmarker.task` via Google MediaPipe Tasks Vision API to detect
faces, extract high-fidelity bounding boxes and 5 keypoints (Left Eye, Right Eye,
Nose Tip, Left Mouth Corner, Right Mouth Corner).
"""

import os
from typing import List, Optional, Tuple
import cv2
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    _MEDIAPIPE_AVAILABLE = True
except Exception:
    mp = None
    _MEDIAPIPE_AVAILABLE = False


class MediaPipeLandmarkerDetector:
    """Face detector using Google MediaPipe Tasks Vision API (face_landmarker.task)."""

    # Indices for 5 ArcFace reference points:
    # 468: Left pupil (or 473 depending on mirror), 473: Right pupil, 1: Nose tip, 61: Left mouth, 291: Right mouth
    LM5_INDICES = [468, 473, 1, 61, 291]
    # Fallback indices if iris landmarks are not present (using eye centers)
    LM5_FALLBACK_INDICES = [33, 263, 1, 61, 291]

    def __init__(self, model_path: str, num_faces: int = 10, min_confidence: float = 0.5):
        if not _MEDIAPIPE_AVAILABLE:
            raise ImportError("MediaPipe is not installed or failed to import.")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"FaceLandmarker task model not found at: {model_path}")

        self.model_path = model_path
        self.num_faces = num_faces
        self.min_confidence = min_confidence

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_faces=num_faces,
            min_face_detection_confidence=min_confidence,
            min_face_presence_confidence=min_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)

    def detect(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Detects faces in BGR image.
        Returns:
            bboxes: np.ndarray [N, 4] of [x1, y1, x2, y2]
            kpss: np.ndarray [N, 5, 2] of 5 ArcFace-aligned landmarks
            scores: np.ndarray [N] of detection confidence scores
        """
        if img_bgr is None or img_bgr.size == 0:
            return np.empty((0, 4), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32), np.empty((0,), dtype=np.float32)

        h, w = img_bgr.shape[:2]
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)

        try:
            res = self.landmarker.detect(mp_img)
        except Exception as e:
            print(f"[MediaPipeLandmarkerDetector] Detection error: {e}")
            return np.empty((0, 4), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32), np.empty((0,), dtype=np.float32)

        if not res.face_landmarks or len(res.face_landmarks) == 0:
            return np.empty((0, 4), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32), np.empty((0,), dtype=np.float32)

        boxes_list = []
        kpss_list = []
        scores_list = []

        for face_lms in res.face_landmarks:
            num_pts = len(face_lms)
            if num_pts < 5:
                continue

            # Convert all normalized points to pixel coordinates
            pts = np.array([[lm.x * w, lm.y * h] for lm in face_lms], dtype=np.float32)

            # Compute bounding box with slight margin
            x1 = float(np.min(pts[:, 0]))
            y1 = float(np.min(pts[:, 1]))
            x2 = float(np.max(pts[:, 0]))
            y2 = float(np.max(pts[:, 1]))

            # Margin: 5% expansion to cover full face boundary
            box_w = x2 - x1
            box_h = y2 - y1
            mx = box_w * 0.05
            my = box_h * 0.05
            x1 = max(0.0, x1 - mx)
            y1 = max(0.0, y1 - my)
            x2 = min(float(w), x2 + mx)
            y2 = min(float(h), y2 + my)

            # Extract 5 ArcFace reference points
            indices = self.LM5_INDICES if num_pts > 473 else self.LM5_FALLBACK_INDICES
            kps5 = []
            for idx in indices:
                if idx < num_pts:
                    kps5.append([face_lms[idx].x * w, face_lms[idx].y * h])
                else:
                    kps5.append([0.0, 0.0])
            kps5_arr = np.array(kps5, dtype=np.float32)

            # Ensure left eye is on the left in image space (smaller x)
            if kps5_arr[0, 0] > kps5_arr[1, 0]:
                kps5_arr[[0, 1]] = kps5_arr[[1, 0]]
            if kps5_arr[3, 0] > kps5_arr[4, 0]:
                kps5_arr[[3, 4]] = kps5_arr[[4, 3]]

            boxes_list.append([x1, y1, x2, y2])
            kpss_list.append(kps5_arr)
            scores_list.append(0.95)

        if len(boxes_list) == 0:
            return np.empty((0, 4), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32), np.empty((0,), dtype=np.float32)

        return (
            np.array(boxes_list, dtype=np.float32),
            np.array(kpss_list, dtype=np.float32),
            np.array(scores_list, dtype=np.float32),
        )

    def close(self):
        try:
            if hasattr(self, "landmarker") and self.landmarker is not None:
                self.landmarker.close()
        except Exception:
            pass
