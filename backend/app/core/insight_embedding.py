import os
import shutil

import cv2
import numpy as np
import onnxruntime as ort
from app.utils.logger import get_logger
from config import (FACE_LANDMARKER_TASK, GUEST_MIN_DETECTION_SCORE,
                    GUEST_MIN_FACE_BBOX_SIZE,
                    MEDIAPIPE_FACE_MESH_MODEL_SELECTION, MIN_DETECTION_SCORE,
                    MIN_FACE_BBOX_SIZE, RECOGNIZER_FLOAT_PATH, RECOGNIZER_PATH,
                    SIMILARITY_THRESHOLD)
from app.core.settings import system_settings

logger = get_logger(__name__)

try:
    import mediapipe as mp
except Exception as e:
    import sys

    logger.warning("Failed to import mediapipe: %s", e)
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

EDGE_CROP_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [56.1396, 92.2848],
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
        session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        
        # Optimize for 2 vCPUs (EC2 instances)
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session_options.intra_op_num_threads = 2
        session_options.inter_op_num_threads = 1
        self.det_size = det_size

        # Try to load the recognizer model, with fallback to float model if int8 fails
        try:
            self.recognizer = ort.InferenceSession(
                str(recognizer_path),
                sess_options=session_options,
                providers=providers,
            )
            model_used = recognizer_path.name
        except:
            import sys

            exc_info = sys.exc_info()
            error_str = str(exc_info[1])
            error_type = type(exc_info[1]).__name__
            logger.error("Exception caught: %s: %s", error_type, error_str)
            if (
                "NotImplemented" in error_str or "NOT_IMPLEMENTED" in error_str
            ) and "ConvInteger" in error_str:
                # Int8 model not supported, try float model
                logger.warning("Int8 model not supported, falling back to float model")
                if RECOGNIZER_FLOAT_PATH.exists():
                    self.recognizer = ort.InferenceSession(
                        str(RECOGNIZER_FLOAT_PATH),
                        sess_options=session_options,
                        providers=providers,
                    )
                    model_used = RECOGNIZER_FLOAT_PATH.name
                    logger.info("Successfully loaded float model: %s", model_used)
                else:
                    raise FileNotFoundError(
                        f"Int8 model failed to load and float model not found at {RECOGNIZER_FLOAT_PATH}"
                    )
            else:
                raise

        self._model_name = model_used
        self.recognizer_input = self.recognizer.get_inputs()[0].name
        logger.info("Loaded recognizer model: %s", model_used)

        # Initialize face detection - try MediaPipe tasks first, then solutions, then fallback to OpenCV
        if mp is None:
            logger.warning(
                "MediaPipe not available, will use OpenCV for face detection"
            )
            self._use_opencv = True
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            self._mediapipe_tasks = False
        elif hasattr(mp, "tasks") and FACE_LANDMARKER_TASK.exists():
            # Use the newer MediaPipe Tasks API if the .task model file is available
            BaseOptions = mp.tasks.BaseOptions
            FaceLandmarker = mp.tasks.vision.FaceLandmarker
            FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(FACE_LANDMARKER_TASK)),
                running_mode=VisionRunningMode.IMAGE,
                num_faces=5,
                min_face_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

            # Create the face landmarker for video mode
            self.face_landmarker = FaceLandmarker.create_from_options(options)
            self._mediapipe_tasks = True
            self._use_opencv = False
            logger.info("Using MediaPipe Tasks API for face detection")
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
            self._use_opencv = False
            logger.info("Using MediaPipe Solutions API for face detection")
        else:
            # Fallback to OpenCV for face detection
            logger.warning(
                "MediaPipe tasks/solutions not available, using OpenCV for face detection"
            )
            self._use_opencv = True
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            self._mediapipe_tasks = False
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

            guest_quality_ok = self.is_guest_quality_ok(box, score, landmark)

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
                    "guest_quality_ok": guest_quality_ok,
                    "embedding": embedding,
                }
            )
        return faces

    def is_quality_ok(self, bbox, score):
        left, top, right, bottom = map(int, bbox)
        width = max(0, right - left)
        height = max(0, bottom - top)
        min_size = system_settings.get("min_face_bbox_size", MIN_FACE_BBOX_SIZE)
        min_score = system_settings.get("min_detection_score", MIN_DETECTION_SCORE)
        return width >= min_size and height >= min_size and float(score) >= min_score

    def is_guest_quality_ok(self, bbox, score, landmarks):
        if not self.is_quality_ok(bbox, score):
            return False

        left, top, right, bottom = map(int, bbox)
        width = max(0, right - left)
        height = max(0, bottom - top)

        min_guest_bbox = system_settings.get("guest_min_face_bbox_size", GUEST_MIN_FACE_BBOX_SIZE)
        if width < min_guest_bbox or height < min_guest_bbox:
            return False
            
        if float(score) < system_settings.get("guest_min_detection_score", GUEST_MIN_DETECTION_SCORE):
            return False

        # Check if frontal face based on eye distance
        if landmarks is not None and len(landmarks) >= 2:
            left_eye = landmarks[0]
            right_eye = landmarks[1]
            eye_dist = np.linalg.norm(left_eye - right_eye)
            if eye_dist / width < 0.35:
                return False

        return True

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

        # We compute pupil centers by averaging eye contours for better ArcFace alignment
        # lm5 mapping: [Left Pupil, Right Pupil, Nose, Left Mouth, Right Mouth]

        # Common 5-point indices that map well onto face landmarker outputs
        lm5_idx = [33, 263, 1, 61, 291]

        if getattr(self, "_use_opencv", False):
            # Use OpenCV Haar Cascade for face detection
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=3, minSize=(50, 50)
            )

            for x, y, fw, fh in faces:
                boxes.append([x, y, x + fw, y + fh])
                # Generate simple 5-point landmarks based on face bounding box
                # These are rough estimates of key face points
                x_center = x + fw / 2
                y_center = y + fh / 2
                lm5 = np.array(
                    [
                        [x + fw * 0.25, y_center],  # left eye
                        [x + fw * 0.75, y_center],  # right eye
                        [x_center, y + fh * 0.5],  # nose
                        [x + fw * 0.2, y + fh * 0.8],  # left mouth
                        [x + fw * 0.8, y + fh * 0.8],  # right mouth
                    ],
                    dtype=np.float32,
                )
                landmarks_all.append(lm5)
                scores.append(0.8)  # Arbitrary confidence score
        elif getattr(self, "_mediapipe_tasks", False):
            # Use MediaPipe Tasks FaceLandmarker
            # Build a mediapipe Image from numpy array
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            result = self.face_landmarker.detect(mp_image)
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

        boxes_arr = np.asarray(boxes, dtype=np.float32)
        landmarks_arr = np.asarray(landmarks_all, dtype=np.float32)
        scores_arr = np.asarray(scores, dtype=np.float32)

        if len(boxes_arr) > 0:
            keep = nms(boxes_arr, scores_arr, threshold=0.4)
            boxes_arr = boxes_arr[keep]
            landmarks_arr = landmarks_arr[keep]
            scores_arr = scores_arr[keep]

        return boxes_arr, landmarks_arr, scores_arr

    def get_embedding(self, image_bgr, landmarks=None):
        if landmarks is None or len(landmarks) == 0:
            aligned = cv2.resize(image_bgr, FACE_SIZE)
        else:
            landmarks_arr = np.array(landmarks, dtype=np.float32)
            template = EDGE_CROP_TEMPLATE if len(landmarks_arr) == 4 else ARC_FACE_TEMPLATE
            matrix, _ = cv2.estimateAffinePartial2D(
                landmarks_arr,
                template,
                method=cv2.LMEDS,
            )
            if matrix is None:
                aligned = cv2.resize(image_bgr, FACE_SIZE)
            else:
                aligned = cv2.warpAffine(image_bgr, matrix, FACE_SIZE, borderValue=0.0)

        # Check input shape of the model to support NCHW vs NHWC dynamically
        input_shape = self.recognizer.get_inputs()[0].shape
        if input_shape[-1] == 3 or input_shape[-1] == "3":
            # NHWC format (e.g. GhostFaceNet)
            aligned_rgb = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB)
            aligned_norm = aligned_rgb.astype(np.float32)
            aligned_norm -= 127.5
            aligned_norm *= 0.00784313725  # Equivalent to / 127.5
            blob = np.expand_dims(aligned_norm, axis=0)
        else:
            # NCHW format (e.g. MobileFaceNet, AdaFace)
            # AdaFace models typically require BGR input, while InsightFace models require RGB
            is_adaface = "adaface" in getattr(self, "_model_name", "").lower()
            swap_rb = not is_adaface

            blob = cv2.dnn.blobFromImage(
                aligned,
                1.0 / 127.5,
                FACE_SIZE,
                (127.5, 127.5, 127.5),
                swapRB=swap_rb,
            )

        # Ensure thread safety for concurrent embedding extraction
        io_binding = self.recognizer.io_binding()
        output_name = self.recognizer.get_outputs()[0].name

        io_binding.bind_cpu_input(self.recognizer_input, blob)
        io_binding.bind_output(output_name)

        self.recognizer.run_with_iobinding(io_binding)
        embedding = io_binding.copy_outputs_to_cpu()[0][0]

        return normalize_embedding(embedding)

    def get_batch_embeddings(self, image_bgr, list_of_landmarks):
        """Batch extraction of face embeddings.
        Fallback to sequential extraction since the ONNX model may have a static batch size of 1.
        """
        if list_of_landmarks is None or len(list_of_landmarks) == 0:
            return []

        results = []
        for landmarks in list_of_landmarks:
            results.append(self.get_embedding(image_bgr, landmarks))
            
        return results



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
    embedding = np.asarray(embedding, dtype=np.float32)
    if embedding.ndim == 1:
        # Optimized for 1D using np.dot
        norm = np.sqrt(np.dot(embedding, embedding))
        if norm == 0:
            return embedding
        return embedding / norm
    else:
        # Vectorized for 2D arrays
        norm = np.linalg.norm(embedding, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
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
