import os
import shutil

import cv2
import numpy as np
import onnxruntime as ort

# ✅ FIX: Get the project root directory (one level up from src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ✅ Use absolute paths for ONNX models
DETECTOR_PATH = os.path.join(PROJECT_ROOT, "models", "det_500m.onnx")
RECOGNIZER_PATH = os.path.join(PROJECT_ROOT, "models", "w600k_mbf.onnx")
FACE_SIZE = (112, 112)
DET_SIZE = (320, 320)
DET_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4
SIMILARITY_THRESHOLD = 0.38
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
        detector_path=DETECTOR_PATH,
        recognizer_path=RECOGNIZER_PATH,
        det_size=DET_SIZE,
    ):
        require_file(detector_path)
        require_file(recognizer_path)

        providers = get_onnx_providers()
        session_options = ort.SessionOptions()
        session_options.log_severity_level = 3
        self.det_size = det_size
        self.detector = ort.InferenceSession(
            detector_path,
            sess_options=session_options,
            providers=providers,
        )
        self.recognizer = ort.InferenceSession(
            recognizer_path,
            sess_options=session_options,
            providers=providers,
        )
        self.detector_input = self.detector.get_inputs()[0].name
        self.recognizer_input = self.recognizer.get_inputs()[0].name
        self.providers = {
            "detector": self.detector.get_providers(),
            "recognizer": self.recognizer.get_providers(),
        }

    def get_faces(self, image_bgr, scale=1.0):
        if image_bgr is None:
            return []

        boxes, landmarks, scores = self.detect(image_bgr, scale=scale)
        faces = []
        for box, landmark, score in zip(boxes, landmarks, scores):
            embedding = self.get_embedding(image_bgr, landmark)
            if embedding is None:
                continue
            left, top, right, bottom = box.astype(int)
            faces.append(
                {
                    "bbox": (left, top, right, bottom),
                    "landmark": landmark,
                    "score": float(score),
                    "embedding": embedding,
                }
            )
        return faces

    def detect(self, image_bgr, scale=1.0):
        if scale != 1.0:
            image_bgr = cv2.resize(image_bgr, (0, 0), fx=scale, fy=scale)

        original_height, original_width = image_bgr.shape[:2]
        input_image, resize_ratio = resize_with_padding(image_bgr, self.det_size)
        blob = cv2.dnn.blobFromImage(
            input_image,
            1.0 / 128.0,
            self.det_size,
            (127.5, 127.5, 127.5),
            swapRB=True,
        )
        outputs = self.detector.run(None, {self.detector_input: blob})

        scores_list = outputs[0:3]
        boxes_list = outputs[3:6]
        landmarks_list = outputs[6:9]

        all_scores = []
        all_boxes = []
        all_landmarks = []

        for stride, scores, boxes, landmarks in zip(
            SCRFD_STRIDES,
            scores_list,
            boxes_list,
            landmarks_list,
        ):
            anchor_centers = get_anchor_centers(self.det_size, stride)
            scores = scores.reshape(-1)
            keep = np.where(scores >= DET_THRESHOLD)[0]
            if len(keep) == 0:
                continue

            kept_scores = scores[keep]
            kept_boxes = distance_to_bbox(anchor_centers[keep], boxes[keep] * stride)
            kept_landmarks = distance_to_landmarks(
                anchor_centers[keep],
                landmarks[keep] * stride,
            )

            kept_boxes /= resize_ratio
            kept_landmarks /= resize_ratio

            if scale != 1.0:
                kept_boxes /= scale
                kept_landmarks /= scale
                original_height = int(original_height / scale)
                original_width = int(original_width / scale)

            kept_boxes[:, 0::2] = np.clip(kept_boxes[:, 0::2], 0, original_width - 1)
            kept_boxes[:, 1::2] = np.clip(kept_boxes[:, 1::2], 0, original_height - 1)
            kept_landmarks[:, :, 0] = np.clip(
                kept_landmarks[:, :, 0],
                0,
                original_width - 1,
            )
            kept_landmarks[:, :, 1] = np.clip(
                kept_landmarks[:, :, 1],
                0,
                original_height - 1,
            )

            all_scores.append(kept_scores)
            all_boxes.append(kept_boxes)
            all_landmarks.append(kept_landmarks)

        if not all_scores:
            return np.empty((0, 4)), np.empty((0, 5, 2)), np.empty((0,))

        scores = np.concatenate(all_scores)
        boxes = np.concatenate(all_boxes)
        landmarks = np.concatenate(all_landmarks)
        keep = nms(boxes, scores, NMS_THRESHOLD)
        return boxes[keep], landmarks[keep], scores[keep]

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
    if len(known_embeddings) == 0:
        return np.array([])
    return np.dot(np.asarray(known_embeddings, dtype=np.float32), embedding)
