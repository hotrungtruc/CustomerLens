import os
import shutil

import cv2
import numpy as np
import onnxruntime as ort

from config import (
    FACE_LANDMARKER_TASK,
    MIN_DETECTION_SCORE,
    MIN_FACE_BBOX_SIZE,
    MEDIAPIPE_FACE_MESH_MODEL_SELECTION,
    RECOGNIZER_PATH,
    SIMILARITY_THRESHOLD,
)

try:
    import mediapipe as mp
except Exception as e:
    mp = None

FACE_SIZE = (112, 112)
DET_SIZE = (320, 320)
DET_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4
SCRFD_STRIDES = (8, 16, 32)

ARC_FACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


class InsightEmbedder:
    def __init__(
        self,
        recognizer_path=RECOGNIZER_PATH,
        det_size=DET_SIZE,
    ):
        require_file(recognizer_path)

        providers = get_onnx_providers()
        session_options = ort.SessionOptions()
        session_options.log_severity_level = 3
        self.det_size = det_size
        self.recognizer = ort.InferenceSession(
            str(recognizer_path),
            sess_options=session_options,
            providers=providers,
        )
        self.recognizer_input = self.recognizer.get_inputs()[0].name
        # Initialize MediaPipe FaceMesh for detection + landmarks
        if mp is None:
            raise ImportError(
                "mediapipe is required for MediaPipe-based face detection. Please install `mediapipe`."
            )

        # Prefer the newer MediaPipe Tasks API (v0.10+) if available and a model is provided.
        if hasattr(mp, "tasks"):
            # Require a .task model file for the FaceLandmarker task
            if not FACE_LANDMARKER_TASK.exists():
                raise FileNotFoundError(
                    f"MediaPipe tasks API detected but FaceLandmarker model not found: {FACE_LANDMARKER_TASK}.\n"
                    "Download a compatible FaceLandmarker .task model and place it in backend/models/.\n"
                    "See https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python for details."
                )

            BaseOptions = mp.tasks.BaseOptions
            FaceLandmarker = mp.tasks.vision.FaceLandmarker
            FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(FACE_LANDMARKER_TASK)),
                running_mode=VisionRunningMode.VIDEO,
                num_faces=5,
                min_face_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

            # Create the face landmarker for video mode
            self.face_landmarker = FaceLandmarker.create_from_options(options)
            self._mediapipe_tasks = True
        elif hasattr(mp, "solutions"):
            # Older mediapipe versions expose the 'solutions' API (mp.solutions.face_mesh).
            self.mp_face_mesh = mp.solutions.face_mesh
            # refine_landmarks=False keeps performance reasonable
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=5,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                model_selection=MEDIAPIPE_FACE_MESH_MODEL_SELECTION,
            )
            self._mediapipe_tasks = False
        else:
            raise ImportError(
                "mediapipe is required for MediaPipe-based face detection. Please install `mediapipe`."
            )
        # store recognizer provider info only
        self.providers = {"recognizer": self.recognizer.get_providers()}

    def get_faces(self, image_bgr, scale=1.0):
        if image_bgr is None:
            return []

        boxes, landmarks, scores = self.detect(image_bgr, scale=scale)
        faces = []
        for box, landmark, score in zip(boxes, landmarks, scores):
            quality_ok = self.is_quality_ok(box, score)
            if not quality_ok:
                continue

            embedding = self.get_embedding(image_bgr, landmark)
            if embedding is None:
                continue
            left, top, right, bottom = box.astype(int)
            faces.append(
                {
                    "bbox": (left, top, right, bottom),
                    "landmark": landmark,
                    "score": float(score),
                    "quality_ok": quality_ok,
                    "embedding": embedding,
                }
            )
        return faces

    def is_quality_ok(self, bbox, score):
        left, top, right, bottom = map(int, bbox)
        width = max(0, right - left)
        height = max(0, bottom - top)
        return width >= MIN_FACE_BBOX_SIZE and height >= MIN_FACE_BBOX_SIZE and float(score) >= MIN_DETECTION_SCORE

    def detect(self, image_bgr, scale=1.0):
        # Use MediaPipe FaceMesh to detect faces and extract 5-point landmarks
        if image_bgr is None:
            return np.empty((0, 4)), np.empty((0, 5, 2)), np.empty((0,))

        if scale != 1.0:
            image_bgr = cv2.resize(image_bgr, (0, 0), fx=scale, fy=scale)

        h, w = image_bgr.shape[:2]
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

        boxes = []
        landmarks_all = []
        scores = []

        # Common 5-point indices that map well onto face landmarker outputs
        lm5_idx = [33, 263, 1, 61, 291]

        if getattr(self, "_mediapipe_tasks", False):
            # Use MediaPipe Tasks FaceLandmarker
            # Build a mediapipe Image from numpy array
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            import time

            timestamp_ms = int(time.time() * 1000)
            result = self.face_landmarker.detect_for_video(mp_image, timestamp_ms)
            if not result or not getattr(result, "face_landmarks", None):
                return np.empty((0, 4)), np.empty((0, 5, 2)), np.empty((0,))

            for face_landmarks in result.face_landmarks:
                # Tasks API returns a sequence of NormalizedLandmark objects per face.
                landmarks_seq = getattr(face_landmarks, "landmark", face_landmarks)
                pts = np.array(
                    [[lm.x * w, lm.y * h] for lm in landmarks_seq],
                    dtype=np.float32,
                )
                x_min = int(np.min(pts[:, 0]))
                y_min = int(np.min(pts[:, 1]))
                x_max = int(np.max(pts[:, 0]))
                y_max = int(np.max(pts[:, 1]))

                boxes.append([x_min, y_min, x_max, y_max])

                try:
                    lm5 = pts[lm5_idx]
                except Exception:
                    indices = np.linspace(0, pts.shape[0] - 1, 5, dtype=int)
                    lm5 = pts[indices]

                landmarks_all.append(lm5)
                scores.append(1.0)

            return np.asarray(boxes, dtype=np.float32), np.asarray(landmarks_all, dtype=np.float32), np.asarray(scores, dtype=np.float32)
        else:
            # Fallback to solutions FaceMesh
            results = self.face_mesh.process(rgb)
            if not results or not results.multi_face_landmarks:
                return np.empty((0, 4)), np.empty((0, 5, 2)), np.empty((0,))

            for face_landmarks in results.multi_face_landmarks:
                landmarks_seq = getattr(face_landmarks, "landmark", face_landmarks)
                pts = np.array(
                    [[lm.x * w, lm.y * h] for lm in landmarks_seq],
                    dtype=np.float32,
                )

                x_min = int(np.min(pts[:, 0]))
                y_min = int(np.min(pts[:, 1]))
                x_max = int(np.max(pts[:, 0]))
                y_max = int(np.max(pts[:, 1]))

                boxes.append([x_min, y_min, x_max, y_max])

                try:
                    lm5 = pts[lm5_idx]
                except Exception:
                    indices = np.linspace(0, pts.shape[0] - 1, 5, dtype=int)
                    lm5 = pts[indices]

                landmarks_all.append(lm5)
                scores.append(1.0)

            return np.asarray(boxes, dtype=np.float32), np.asarray(landmarks_all, dtype=np.float32), np.asarray(scores, dtype=np.float32)

    def get_embedding(self, image_bgr, landmarks):
        matrix, _ = cv2.estimateAffinePartial2D(
            landmarks.astype(np.float32),
            ARC_FACE_TEMPLATE,
            method=cv2.LMEDS,
        )
        if matrix is None:
            return None

        aligned = cv2.warpAffine(image_bgr, matrix, FACE_SIZE, borderValue=0.0)
        blob = cv2.dnn.blobFromImage(
            aligned,
            1.0 / 127.5,
            FACE_SIZE,
            (127.5, 127.5, 127.5),
            swapRB=True,
        )
        embedding = self.recognizer.run(None, {self.recognizer_input: blob})[0][0]
        return normalize_embedding(embedding)


def require_file(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required ONNX model not found: {path}")


def get_onnx_providers():
    available = ort.get_available_providers()
    providers = []
    if "CUDAExecutionProvider" in available and has_cuda_runtime():
        providers.append("CUDAExecutionProvider")
    providers.append("CPUExecutionProvider")
    return providers


def has_cuda_runtime():
    required_dlls = ("cublasLt64_12.dll", "cudnn64_9.dll")
    return all(shutil.which(dll_name) for dll_name in required_dlls)


def resize_with_padding(image_bgr, target_size):
    target_width, target_height = target_size
    height, width = image_bgr.shape[:2]
    ratio = min(target_width / width, target_height / height)
    new_width = int(width * ratio)
    new_height = int(height * ratio)
    resized = cv2.resize(image_bgr, (new_width, new_height))
    padded = np.zeros((target_height, target_width, 3), dtype=np.uint8)
    padded[:new_height, :new_width] = resized
    return padded, ratio


def get_anchor_centers(input_size, stride):
    input_width, input_height = input_size
    feature_width = input_width // stride
    feature_height = input_height // stride
    grid_y, grid_x = np.mgrid[:feature_height, :feature_width]
    centers = np.stack((grid_x, grid_y), axis=-1).astype(np.float32)
    centers = (centers * stride).reshape(-1, 2)
    return np.repeat(centers, 2, axis=0)


def distance_to_bbox(points, distance):
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def distance_to_landmarks(points, distance):
    distance = distance.reshape(-1, 5, 2)
    landmarks = np.empty_like(distance)
    landmarks[:, :, 0] = points[:, 0:1] + distance[:, :, 0]
    landmarks[:, :, 1] = points[:, 1:2] + distance[:, :, 1]
    return landmarks


def nms(boxes, scores, threshold):
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0, x2 - x1 + 1) * np.maximum(0, y2 - y1 + 1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        index = order[0]
        keep.append(index)
        xx1 = np.maximum(x1[index], x1[order[1:]])
        yy1 = np.maximum(y1[index], y1[order[1:]])
        xx2 = np.minimum(x2[index], x2[order[1:]])
        yy2 = np.minimum(y2[index], y2[order[1:]])
        width = np.maximum(0.0, xx2 - xx1 + 1)
        height = np.maximum(0.0, yy2 - yy1 + 1)
        overlap = width * height / (areas[index] + areas[order[1:]] - width * height)
        remaining = np.where(overlap <= threshold)[0]
        order = order[remaining + 1]
    return keep


def normalize_embedding(embedding):
    embedding = embedding.astype(np.float32)
    norm = np.linalg.norm(embedding)
    if norm == 0:
        return embedding
    return embedding / norm


def cosine_similarities(known_embeddings, embedding):
    if known_embeddings is None:
        return np.array([])

    try:
        arr = np.asarray(known_embeddings, dtype=np.float32)
    except Exception:
        return np.array([])

    if arr.size == 0:
        return np.array([])

    return np.dot(arr, embedding)
