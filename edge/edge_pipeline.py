"""
edge_pipeline.py — High-performance Edge AI Processing Pipeline.

Architecture:
  Camera / Video Ingestion
       ↓
  MediaPipe FaceLandmarker Tasks API (Default Edge Detector: face_landmarker.task)
       ↓
  OC-SORT (Observation-Centric SORT: Kalman + OOS Smoothing + VDC Direction Consistency + OCR)
       ↓
  Face Quality Gate (Size, Laplacian Sharpness, Pose Ratio)
       ↓
  Padded Face Cropping (25% margin crop sent to Cloud Backend)
       ↓
  Smart Event Dispatcher (First-shot / Best-shot to Backend for SCRFD 500M + EdgeFace int8 recognition)
"""

import base64
import json
import os
import queue
import threading
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort

from edge.edge_config import (
    BEST_SHOT_DELTA,
    CROP_PADDING_RATIO,
    DEFAULT_CAMERA_ID,
    DEFAULT_CLOUD_URL,
    DEFAULT_DETECTOR_TYPE,
    DEFAULT_DEVICE_ID,
    DET_THRESHOLD,
    EDGEFACE_MODEL_PATH,
    FACE_LANDMARKER_MODEL_PATH,
    FIRST_SHOT_QUALITY_THRESHOLD,
    HEARTBEAT_INTERVAL,
    IOU_THRESHOLD,
    MAX_LOST_FRAMES,
    MIN_BLUR_VAR,
    MIN_FACE_SIZE,
    MIN_POSE_RATIO,
    NMS_THRESHOLD,
    OC_SORT_DELTA_T,
    OC_SORT_DET_THRESH,
    OC_SORT_INERTIA,
    OC_SORT_IOU_THRESHOLD,
    OC_SORT_MAX_AGE,
    OC_SORT_MIN_HITS,
    OFFLINE_QUEUE_MAX,
    SCRFD_MODEL_PATH,
    SEND_THUMBNAIL,
    THUMBNAIL_JPEG_QUALITY,
    TRACKER_TYPE,
)
from edge.mediapipe_detector import MediaPipeLandmarkerDetector
from edge.oc_sort import OCSort

# Standard ArcFace 112x112 5-point alignment template
ARC_FACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],  # Left Eye
        [73.5318, 51.5014],  # Right Eye
        [56.0252, 71.7366],  # Nose Tip
        [41.5493, 92.3655],  # Left Mouth Corner
        [70.7299, 92.2041],  # Right Mouth Corner
    ],
    dtype=np.float32,
)


def distance2bbox(points, distance, max_shape=None):
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    if max_shape is not None:
        x1 = np.clip(x1, 0, max_shape[1])
        y1 = np.clip(y1, 0, max_shape[0])
        x2 = np.clip(x2, 0, max_shape[1])
        y2 = np.clip(y2, 0, max_shape[0])
    return np.column_stack([x1, y1, x2, y2])


def distance2kps(points, distance, max_shape=None):
    preds = []
    for i in range(0, distance.shape[1], 2):
        px = points[:, 0] + distance[:, i]
        py = points[:, 1] + distance[:, i + 1]
        if max_shape is not None:
            px = np.clip(px, 0, max_shape[1])
            py = np.clip(py, 0, max_shape[0])
        preds.append(px)
        preds.append(py)
    return np.column_stack(preds)


class SCRFDDetector:
    """Lightweight SCRFD-500M Face Detector running on ONNX Runtime (Fallback)."""

    def __init__(self, model_path: str = str(SCRFD_MODEL_PATH)):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"SCRFD model file not found at: {model_path}")

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = max(1, os.cpu_count() or 2)
        opts.inter_op_num_threads = 1

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if "CUDAExecutionProvider" in ort.get_available_providers() else ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.use_kps = len(self.output_names) == 9
        self.feat_stride_fpn = [8, 16, 32]
        self.fmc = 3
        self.num_anchors = 2
        self.center_cache = {}

    def forward(self, img_bgr: np.ndarray, threshold: float = DET_THRESHOLD):
        input_size = tuple(img_bgr.shape[0:2][::-1])
        blob = cv2.dnn.blobFromImage(
            img_bgr, 1.0 / 128, input_size, (127.5, 127.5, 127.5), swapRB=True
        )
        net_outs = self.session.run(self.output_names, {self.input_name: blob})

        def squeeze_out(arr):
            if arr.ndim == 3:
                arr = arr[0]
            if arr.ndim == 2 and arr.shape[1] == 1:
                arr = arr[:, 0]
            return arr

        net_outs = [squeeze_out(o) for o in net_outs]
        input_height = blob.shape[2]
        input_width = blob.shape[3]

        scores_list = []
        bboxes_list = []
        kpss_list = []

        for idx, stride in enumerate(self.feat_stride_fpn):
            scores = net_outs[idx]
            bbox_preds = net_outs[idx + self.fmc] * stride
            if self.use_kps:
                kps_preds = net_outs[idx + self.fmc * 2] * stride

            height = int(np.ceil(input_height / stride))
            width = int(np.ceil(input_width / stride))
            K = height * width
            key = (height, width, stride)

            if key in self.center_cache:
                anchor_centers = self.center_cache[key]
            else:
                grid_x = np.arange(width, dtype=np.float32)
                grid_y = np.arange(height, dtype=np.float32)
                xv, yv = np.meshgrid(grid_x, grid_y)
                anchor_centers = np.stack([xv, yv], axis=-1).reshape(-1, 2)
                anchor_centers = (anchor_centers * stride).astype(np.float32)
                anchor_centers = np.broadcast_to(
                    np.expand_dims(anchor_centers, axis=1), (K, self.num_anchors, 2)
                ).reshape(-1, 2)
                self.center_cache[key] = anchor_centers

            pos_inds = np.where(scores >= threshold)[0]
            bboxes = distance2bbox(anchor_centers, bbox_preds)
            scores_list.append(scores[pos_inds])
            bboxes_list.append(bboxes[pos_inds])

            if self.use_kps:
                kpss = distance2kps(anchor_centers, kps_preds).reshape((-1, 5, 2))
                kpss_list.append(kpss[pos_inds])

        return scores_list, bboxes_list, kpss_list

    def detect(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        scores_list, bboxes_list, kpss_list = self.forward(img_bgr, DET_THRESHOLD)
        if len(scores_list) == 0 or all(s.size == 0 for s in scores_list):
            return np.empty((0, 4)), np.empty((0, 5, 2)), np.empty((0,))

        scores = np.concatenate([s.reshape(-1, 1) for s in scores_list if s.size > 0], axis=0)
        scores_ravel = scores.ravel()
        order = scores_ravel.argsort()[::-1]

        bboxes = np.vstack([b for b in bboxes_list if b.size > 0])
        pre_det = np.hstack((bboxes, scores)).astype(np.float32)
        pre_det = pre_det[order, :]

        keep = self._nms(pre_det, NMS_THRESHOLD)
        det = pre_det[keep, :]

        if self.use_kps:
            kpss = np.vstack([k for k in kpss_list if k.size > 0])
            kpss = kpss[order, :, :]
            kpss = kpss[keep, :, :]
        else:
            kpss = None

        return det[:, :4], kpss, det[:, 4]

    def _nms(self, dets: np.ndarray, thresh: float) -> List[int]:
        x1 = dets[:, 0]
        y1 = dets[:, 1]
        x2 = dets[:, 2]
        y2 = dets[:, 3]
        scores = dets[:, 4]

        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            if order.size == 1:
                break
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1 + 1)
            h = np.maximum(0.0, yy2 - yy1 + 1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            inds = np.where(ovr <= thresh)[0]
            order = order[inds + 1]
        return keep

    def close(self):
        pass


class EdgeFaceExtractor:
    """Optional EdgeFace γ0.5 / int8 Extractor with 5-point Alignment."""

    def __init__(self, model_path: str = str(EDGEFACE_MODEL_PATH)):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"EdgeFace model file not found at: {model_path}")

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = max(1, os.cpu_count() or 2)
        opts.inter_op_num_threads = 1

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if "CUDAExecutionProvider" in ort.get_available_providers() else ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def align_face(self, img_bgr: np.ndarray, landmarks5: np.ndarray) -> np.ndarray:
        """Align face using similarity transform to 112x112 ArcFace standard template."""
        matrix, _ = cv2.estimateAffinePartial2D(landmarks5, ARC_FACE_TEMPLATE, method=cv2.LMEDS)
        if matrix is None:
            return cv2.resize(img_bgr, (112, 112))
        return cv2.warpAffine(img_bgr, matrix, (112, 112), borderValue=0.0)

    def extract_embedding(self, aligned_bgr: np.ndarray) -> np.ndarray:
        """Forward aligned face through EdgeFace and L2-normalize."""
        blob = cv2.dnn.blobFromImage(
            aligned_bgr,
            1.0 / 127.5,
            (112, 112),
            (127.5, 127.5, 127.5),
            swapRB=True,
        )
        emb = self.session.run([self.output_name], {self.input_name: blob})[0][0]
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb.astype(np.float32)


def crop_face_with_padding(
    frame_bgr: np.ndarray,
    bbox: np.ndarray,
    padding_ratio: float = CROP_PADDING_RATIO,
) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """
    Crops face region with padding margin (default 25%) to preserve complete facial contour.
    Returns: (padded_crop_bgr, (x1, y1, x2, y2))
    """
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = bbox[:4]
    box_w = max(1.0, x2 - x1)
    box_h = max(1.0, y2 - y1)

    pad_x = box_w * padding_ratio
    pad_y = box_h * padding_ratio

    crop_x1 = max(0, int(round(x1 - pad_x)))
    crop_y1 = max(0, int(round(y1 - pad_y)))
    crop_x2 = min(w, int(round(x2 + pad_x)))
    crop_y2 = min(h, int(round(y2 + pad_y)))

    crop = frame_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
    return crop, (crop_x1, crop_y1, crop_x2, crop_y2)


def compute_face_quality(
    bbox: np.ndarray,
    det_score: float,
    landmarks: Optional[np.ndarray],
    img_bgr: np.ndarray,
) -> Tuple[bool, float]:
    """
    Quality gate:
    1. Size Check: width, height >= MIN_FACE_SIZE
    2. Pose Gate: Eye distance to box width ratio (rejects side profiles)
    3. Sharpness Check: Laplacian variance on face crop
    Returns: (is_good_quality, composite_score)
    """
    x1, y1, x2, y2 = map(int, bbox[:4])
    w = max(0, x2 - x1)
    h = max(0, y2 - y1)

    if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE or float(det_score) < DET_THRESHOLD:
        return False, 0.0

    # Pose Gate: Check eye distance ratio
    if landmarks is not None and len(landmarks) >= 2:
        eye_dist = np.linalg.norm(landmarks[0] - landmarks[1])
        if (eye_dist / w) < MIN_POSE_RATIO:
            return False, 0.0

    # Blur Gate: Laplacian variance
    ih, iw = img_bgr.shape[:2]
    crop = img_bgr[max(0, y1):min(ih, y2), max(0, x1):min(iw, x2)]
    if crop.size == 0:
        return False, 0.0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blur_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_var < MIN_BLUR_VAR:
        return False, 0.0

    # Composite quality score [0.0, 1.0]
    sharpness_norm = min(1.0, blur_var / 300.0)
    size_norm = min(1.0, max(w, h) / 180.0)
    score = 0.4 * float(det_score) + 0.4 * sharpness_norm + 0.2 * size_norm
    return True, score


class EdgeTrackMetadata:
    """Metadata for tracked face instance."""
    def __init__(self, track_id: int, bbox: np.ndarray, landmarks: Optional[np.ndarray], quality: float):
        self.track_id = int(track_id)
        self.bbox = bbox
        self.landmarks = landmarks
        self.quality = quality
        self.best_quality = quality
        self.first_shot_sent = False
        self.best_shot_sent = False
        self.lost_frames = 0
        self.identity_name = "Detecting..."
        self.similarity = 0.0
        self.created_at = time.time()


class EdgeCloudClient:
    """Non-blocking background client for Edge to Cloud communications."""

    def __init__(
        self,
        cloud_url: str = DEFAULT_CLOUD_URL,
        camera_id: str = DEFAULT_CAMERA_ID,
        device_id: str = DEFAULT_DEVICE_ID,
    ):
        self.cloud_url = cloud_url.rstrip("/")
        self.camera_id = camera_id
        self.device_id = device_id
        self.event_queue = queue.Queue(maxsize=OFFLINE_QUEUE_MAX)
        self.running = True
        self.is_online = False
        self.last_heartbeat = 0.0
        self.track_identities: Dict[int, Tuple[str, float]] = {}  # {track_id: (name, similarity)}

        self.worker_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.worker_thread.start()

    def dispatch_event(
        self,
        track_id: int,
        event_type: str,
        bbox: np.ndarray,
        quality: float,
        crop_image: Optional[np.ndarray] = None,
        embedding: Optional[np.ndarray] = None,
        frame_shape: Tuple[int, int] = (480, 640),
    ):
        """Put event into sending queue with padded crop."""
        crop_b64 = None
        if crop_image is not None and crop_image.size > 0:
            try:
                success, buffer = cv2.imencode(".jpg", crop_image, [cv2.IMWRITE_JPEG_QUALITY, THUMBNAIL_JPEG_QUALITY])
                if success:
                    crop_b64 = base64.b64encode(buffer).decode("ascii")
            except Exception:
                pass

        payload = {
            "camera_id": self.camera_id,
            "device_id": self.device_id,
            "track_id": int(track_id),
            "event_type": event_type,
            "timestamp": time.time(),
            "bbox": [float(x) for x in bbox[:4]],
            "quality_score": float(quality),
            "embedding": embedding.tolist() if embedding is not None else None,
            "crop_image_base64": crop_b64,
            "frame_size": {"width": frame_shape[1], "height": frame_shape[0]},
        }

        try:
            self.event_queue.put_nowait(payload)
        except queue.Full:
            try:
                self.event_queue.get_nowait()  # Drop oldest
                self.event_queue.put_nowait(payload)
            except Exception:
                pass

    def send_heartbeat(self, fps: float, active_tracks: int):
        now = time.time()
        if now - self.last_heartbeat < HEARTBEAT_INTERVAL:
            return

        self.last_heartbeat = now
        payload = {
            "device_id": self.device_id,
            "camera_id": self.camera_id,
            "fps": round(fps, 1),
            "cpu_usage": 15.0,
            "mem_usage": 30.0,
            "tracks_active": active_tracks,
            "timestamp": now,
        }

        def _do_hb():
            try:
                req = urllib.request.Request(
                    f"{self.cloud_url}/api/v1/edge/heartbeat",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        self.is_online = True
            except Exception:
                self.is_online = False

        threading.Thread(target=_do_hb, daemon=True).start()

    def _sender_loop(self):
        while self.running:
            try:
                event = self.event_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                req = urllib.request.Request(
                    f"{self.cloud_url}/api/v1/edge/events",
                    data=json.dumps(event).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        self.is_online = True
                        res_data = json.loads(resp.read().decode("utf-8"))
                        res = res_data.get("result", {})
                        name = res.get("name", "Unknown")
                        sim = res.get("similarity", 0.0)
                        if res.get("matched"):
                            self.track_identities[event["track_id"]] = (name, sim)
                        print(f"[EdgeCloudClient] {event['event_type']} (Track {event['track_id']}): matched={res.get('matched')} name='{name}' (sim={sim})")
            except Exception as e:
                self.is_online = False
                print(f"[EdgeCloudClient Error] Failed to send event to {self.cloud_url}: {e}")
                time.sleep(1.0)

    def stop(self):
        self.running = False


class EdgePipeline:
    """
    Master Edge Pipeline coordinator.
    - Default Detector: MediaPipe FaceLandmarker Tasks API (face_landmarker.task)
    - Default Tracker: Observation-Centric SORT (OC-SORT)
    - Crop face with 25% padding and stream to Backend for SCRFD-500M + EdgeFace-int8 recognition
    """

    def __init__(
        self,
        cloud_url: str = DEFAULT_CLOUD_URL,
        camera_id: str = DEFAULT_CAMERA_ID,
        device_id: str = DEFAULT_DEVICE_ID,
        detector_type: str = DEFAULT_DETECTOR_TYPE,
    ):
        self.detector_type = detector_type

        # 1. Initialize Detector (Default: MediaPipe FaceLandmarker Tasks API)
        if self.detector_type == "mediapipe_landmarker" and os.path.exists(FACE_LANDMARKER_MODEL_PATH):
            print(f"[Edge Pipeline] Initializing MediaPipe FaceLandmarker Tasks API from {FACE_LANDMARKER_MODEL_PATH}...")
            self.detector = MediaPipeLandmarkerDetector(str(FACE_LANDMARKER_MODEL_PATH))
        else:
            print(f"[Edge Pipeline] Initializing SCRFD-500M detector from {SCRFD_MODEL_PATH}...")
            self.detector = SCRFDDetector(str(SCRFD_MODEL_PATH))

        # 2. Initialize OC-SORT Tracker
        print("[Edge Pipeline] Initializing Observation-Centric SORT (OC-SORT)...")
        self.tracker = OCSort(
            det_thresh=OC_SORT_DET_THRESH,
            max_age=OC_SORT_MAX_AGE,
            min_hits=OC_SORT_MIN_HITS,
            iou_threshold=OC_SORT_IOU_THRESHOLD,
            delta_t=OC_SORT_DELTA_T,
            inertia=OC_SORT_INERTIA,
        )

        # 3. Optional local EdgeFace Extractor for standalone fallback
        self.extractor = None
        if os.path.exists(EDGEFACE_MODEL_PATH):
            try:
                self.extractor = EdgeFaceExtractor(str(EDGEFACE_MODEL_PATH))
            except Exception as e:
                print(f"[Edge Pipeline] Local EdgeFace optional extractor init skipped: {e}")

        self.client = EdgeCloudClient(cloud_url=cloud_url, camera_id=camera_id, device_id=device_id)
        self.track_metadata: Dict[int, EdgeTrackMetadata] = {}

        self.fps = 0.0
        self._frame_count = 0
        self._start_time = time.time()

    def process_frame(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, List[dict]]:
        """
        Processes one video frame:
        1. MediaPipe FaceLandmarker Tasks API detection
        2. OC-SORT tracking with OOS & VDC
        3. Padded face crop generation & First-shot / Best-shot dispatch to cloud backend
        4. Visual overlay annotations
        """
        h, w = frame_bgr.shape[:2]

        # 1. Detection via MediaPipe Tasks API
        boxes, landmarks, scores = self.detector.detect(frame_bgr)

        # 2. Tracking via OC-SORT
        if len(boxes) > 0:
            dets = np.column_stack([boxes, scores])
        else:
            dets = np.empty((0, 5), dtype=np.float32)

        tracked_boxes, tracked_lms = self.tracker.update(dets, landmarks)

        active_track_ids = set()

        # 3. Process each tracked face instance
        for idx in range(len(tracked_boxes)):
            box = tracked_boxes[idx][:4]
            tid = int(tracked_boxes[idx][4])
            score = float(tracked_boxes[idx][5]) if len(tracked_boxes[idx]) > 5 else 0.95
            lm = tracked_lms[idx] if tracked_lms is not None and len(tracked_lms) > idx else None

            active_track_ids.add(tid)

            if tid not in self.track_metadata:
                self.track_metadata[tid] = EdgeTrackMetadata(tid, box, lm, 0.0)

            track_meta = self.track_metadata[tid]
            track_meta.bbox = box
            track_meta.landmarks = lm

            # Quality Assessment Gate
            is_good, quality = compute_face_quality(box, score, lm, frame_bgr)
            track_meta.quality = quality

            # Update identity label if received from Cloud
            if tid in self.client.track_identities:
                name, sim = self.client.track_identities[tid]
                track_meta.identity_name = f"{name} ({int(sim * 100)}%)"
                track_meta.similarity = sim

            # Crop Face with 25% Padding for Cloud Backend
            padded_crop, _ = crop_face_with_padding(frame_bgr, box, CROP_PADDING_RATIO)

            # First-Shot Decision: Immediately stream first good-quality face crop to Backend
            if not track_meta.first_shot_sent and quality >= FIRST_SHOT_QUALITY_THRESHOLD:
                self.client.dispatch_event(
                    track_id=tid,
                    event_type="first_shot",
                    bbox=box,
                    quality=quality,
                    crop_image=padded_crop,
                    frame_shape=(h, w),
                )
                track_meta.first_shot_sent = True
                track_meta.best_quality = quality

            # Best-Shot Decision: If a clearer, sharper angle is found
            elif track_meta.first_shot_sent and quality >= (track_meta.best_quality + BEST_SHOT_DELTA):
                self.client.dispatch_event(
                    track_id=tid,
                    event_type="best_shot",
                    bbox=box,
                    quality=quality,
                    crop_image=padded_crop,
                    frame_shape=(h, w),
                )
                track_meta.best_shot_sent = True
                track_meta.best_quality = quality

        # Clean up stale track metadata
        stale_ids = [tid for tid in self.track_metadata if tid not in active_track_ids and (time.time() - self.track_metadata[tid].created_at) > 120]
        for tid in stale_ids:
            del self.track_metadata[tid]

        # FPS calculation & Heartbeat
        self._frame_count += 1
        elapsed = time.time() - self._start_time
        if elapsed >= 1.0:
            self.fps = self._frame_count / elapsed
            self._frame_count = 0
            self._start_time = time.time()
            self.client.send_heartbeat(self.fps, len(active_track_ids))

        # 4. Render Overlay Visual Annotations
        annotated = frame_bgr.copy()
        track_summaries = []

        for idx in range(len(tracked_boxes)):
            box = tracked_boxes[idx][:4]
            tid = int(tracked_boxes[idx][4])
            track_meta = self.track_metadata.get(tid)
            if not track_meta:
                continue

            x1, y1, x2, y2 = map(int, box)
            color = (0, 255, 128) if track_meta.first_shot_sent else (0, 165, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = f"ID:{tid} | {track_meta.identity_name}"
            q_label = f"Q:{track_meta.quality:.2f}"
            cv2.putText(annotated, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            cv2.putText(annotated, q_label, (x1, min(h - 5, y2 + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

            track_summaries.append({
                "track_id": tid,
                "bbox": [x1, y1, x2, y2],
                "quality": track_meta.quality,
                "name": track_meta.identity_name,
            })

        # Header Info
        status_text = "CLOUD ONLINE" if self.client.is_online else "CLOUD CONNECTING..."
        status_color = (0, 255, 0) if self.client.is_online else (0, 0, 255)
        det_name = "MediaPipe FaceLandmarker" if self.detector_type == "mediapipe_landmarker" else "SCRFD-500M"
        cv2.putText(
            annotated,
            f"FPS: {self.fps:.1f} | Det: {det_name} | Track: OC-SORT | {status_text} | Queue: {self.client.event_queue.qsize()}",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            status_color,
            2,
        )

        return annotated, track_summaries

    def close(self):
        self.client.stop()
        if hasattr(self.detector, "close"):
            self.detector.close()
