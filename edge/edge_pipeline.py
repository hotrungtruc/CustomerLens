"""
edge_pipeline.py — High-performance Edge AI Processing Pipeline.

Architecture:
  Camera / RTSP Ingestion
       ↓
  SCRFD-500M (Face Detection + 5 Landmarks)
       ↓
  5-point Alignment (ArcFace Similarity Transform 112x112)
       ↓
  EdgeFace γ0.5 (512-D L2-Normalized Embedding Extraction)
       ↓
  Tracker & Quality Gate (IoU Tracking + Blur/Pose assessment)
       ↓
  Smart Dispatcher (First-shot & Best-shot event publisher with offline queue)
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
    DEFAULT_CAMERA_ID,
    DEFAULT_CLOUD_URL,
    DEFAULT_DEVICE_ID,
    DET_THRESHOLD,
    EDGEFACE_MODEL_PATH,
    FIRST_SHOT_QUALITY_THRESHOLD,
    HEARTBEAT_INTERVAL,
    IOU_THRESHOLD,
    MAX_LOST_FRAMES,
    MIN_BLUR_VAR,
    MIN_FACE_SIZE,
    MIN_POSE_RATIO,
    NMS_THRESHOLD,
    OFFLINE_QUEUE_MAX,
    SCRFD_MODEL_PATH,
    SEND_THUMBNAIL,
    THUMBNAIL_JPEG_QUALITY,
)

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
    """Lightweight SCRFD-500M Face Detector running on ONNX Runtime."""

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


class EdgeFaceExtractor:
    """EdgeFace γ0.5 Embedding Extractor with 5-point Alignment."""

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
        """Forward aligned face through EdgeFace γ0.5 and L2-normalize."""
        # Blob: NCHW, normalized to [-1, 1]
        blob = cv2.dnn.blobFromImage(
            aligned_bgr,
            1.0 / 127.5,
            (112, 112),
            (127.5, 127.5, 127.5),
            swapRB=True,
        )
        emb = self.session.run([self.output_name], {self.input_name: blob})[0][0]
        # L2 normalize
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb.astype(np.float32)


def compute_face_quality(bbox: np.ndarray, det_score: float, landmarks: np.ndarray, img_bgr: np.ndarray) -> Tuple[bool, float]:
    """
    Quality gate:
    1. Size Check: width, height >= MIN_FACE_SIZE
    2. Sharpness Check: Laplacian variance on face crop
    3. Pose Gate: Eye distance to box width ratio (rejects profile/side faces)
    Returns: (is_good_quality, composite_score)
    """
    x1, y1, x2, y2 = map(int, bbox)
    w = max(0, x2 - x1)
    h = max(0, y2 - y1)

    if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE or det_score < DET_THRESHOLD:
        return False, 0.0

    # Pose Gate: Check eye distance ratio
    if landmarks is not None and len(landmarks) >= 2:
        eye_dist = np.linalg.norm(landmarks[0] - landmarks[1])
        if (eye_dist / w) < MIN_POSE_RATIO:
            return False, 0.0  # Side face / heavy yaw

    # Blur Gate: Laplacian variance
    ih, iw = img_bgr.shape[:2]
    crop = img_bgr[max(0, y1):min(ih, y2), max(0, x1):min(iw, x2)]
    if crop.size == 0:
        return False, 0.0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blur_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_var < MIN_BLUR_VAR:
        return False, 0.0  # Motion blur / unfocused

    # Composite quality score [0.0, 1.0]
    sharpness_norm = min(1.0, blur_var / 300.0)
    size_norm = min(1.0, max(w, h) / 180.0)
    score = 0.4 * float(det_score) + 0.4 * sharpness_norm + 0.2 * size_norm
    return True, score


def bbox_iou(box1: np.ndarray, box2: np.ndarray) -> float:
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    denom = area1 + area2 - inter
    return inter / denom if denom > 0 else 0.0


class EdgeTrack:
    def __init__(self, track_id: int, bbox: np.ndarray, landmarks: np.ndarray, quality: float):
        self.track_id = track_id
        self.bbox = bbox
        self.landmarks = landmarks
        self.quality = quality
        self.best_quality = quality
        self.first_shot_sent = False
        self.best_shot_sent = False
        self.lost_frames = 0
        self.identity_name = "Detecting..."
        self.identity_id = None
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
        embedding: np.ndarray,
        aligned_crop: Optional[np.ndarray] = None,
        frame_shape: Tuple[int, int] = (480, 640),
    ):
        """Put event into sending queue."""
        thumbnail_b64 = None
        if SEND_THUMBNAIL and aligned_crop is not None:
            try:
                success, buffer = cv2.imencode(".jpg", aligned_crop, [cv2.IMWRITE_JPEG_QUALITY, THUMBNAIL_JPEG_QUALITY])
                if success:
                    thumbnail_b64 = base64.b64encode(buffer).decode("ascii")
            except Exception:
                pass

        payload = {
            "camera_id": self.camera_id,
            "device_id": self.device_id,
            "track_id": track_id,
            "event_type": event_type,
            "timestamp": time.time(),
            "bbox": [float(x) for x in bbox],
            "quality_score": float(quality),
            "embedding": embedding.tolist(),
            "crop_image_base64": thumbnail_b64,
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
            "cpu_usage": 15.0,  # Telemetry placeholder
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

            # Send event to Cloud
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
                        print(f"[EdgeCloudClient] Event {event['event_type']} for Track {event['track_id']}: matched={res.get('matched')} name='{name}' (sim={sim})")
            except Exception as e:
                self.is_online = False
                print(f"[EdgeCloudClient Error] Failed to send event to {self.cloud_url}: {e}")
                time.sleep(1.0)

    def stop(self):
        self.running = False


class EdgePipeline:
    """Master Edge Pipeline coordinator."""

    def __init__(
        self,
        cloud_url: str = DEFAULT_CLOUD_URL,
        camera_id: str = DEFAULT_CAMERA_ID,
        device_id: str = DEFAULT_DEVICE_ID,
    ):
        print(f"[Edge Pipeline] Initializing SCRFD-500M from {SCRFD_MODEL_PATH}...")
        self.detector = SCRFDDetector(str(SCRFD_MODEL_PATH))
        print(f"[Edge Pipeline] Initializing EdgeFace gamma 0.5 from {EDGEFACE_MODEL_PATH}...")
        self.extractor = EdgeFaceExtractor(str(EDGEFACE_MODEL_PATH))
        self.client = EdgeCloudClient(cloud_url=cloud_url, camera_id=camera_id, device_id=device_id)

        self.tracks: Dict[int, EdgeTrack] = {}
        self.next_track_id = 1
        self.fps = 0.0
        self._frame_count = 0
        self._start_time = time.time()

    def process_frame(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, List[dict]]:
        """Processes one video frame, updates tracks, dispatches smart events."""
        t0 = time.time()
        h, w = frame_bgr.shape[:2]

        # 1. SCRFD Face Detection
        boxes, landmarks, scores = self.detector.detect(frame_bgr)

        # 2. Tracking Association (IoU matching)
        matched_tracks = set()
        det_matched = set()

        for d_idx, box in enumerate(boxes):
            best_iou = 0.0
            best_tid = None
            for tid, track in self.tracks.items():
                if tid in matched_tracks:
                    continue
                iou = bbox_iou(box, track.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            if best_iou >= IOU_THRESHOLD and best_tid is not None:
                matched_tracks.add(best_tid)
                det_matched.add(d_idx)
                track = self.tracks[best_tid]
                track.bbox = box
                track.landmarks = landmarks[d_idx] if landmarks is not None else None
                track.lost_frames = 0
            else:
                # New track
                tid = self.next_track_id
                self.next_track_id += 1
                lm = landmarks[d_idx] if landmarks is not None else None
                self.tracks[tid] = EdgeTrack(tid, box, lm, 0.0)
                matched_tracks.add(tid)
                det_matched.add(d_idx)

        # Mark lost tracks
        to_delete = []
        for tid, track in self.tracks.items():
            if tid not in matched_tracks:
                track.lost_frames += 1
                if track.lost_frames > MAX_LOST_FRAMES:
                    to_delete.append(tid)

        for tid in to_delete:
            del self.tracks[tid]

        # 3. Quality Gate, Embedding Extraction & Event Dispatching
        for tid, track in self.tracks.items():
            if track.lost_frames > 0 or track.landmarks is None:
                continue

            is_good, quality = compute_face_quality(track.bbox, 0.9, track.landmarks, frame_bgr)
            track.quality = quality

            # Update identity if returned from Cloud client
            if tid in self.client.track_identities:
                name, sim = self.client.track_identities[tid]
                track.identity_name = f"{name} ({int(sim*100)}%)"

            # First-Shot Decision: Immediately send on first clear face
            if not track.first_shot_sent and quality >= FIRST_SHOT_QUALITY_THRESHOLD:
                aligned = self.extractor.align_face(frame_bgr, track.landmarks)
                embedding = self.extractor.extract_embedding(aligned)
                self.client.dispatch_event(
                    track_id=tid,
                    event_type="first_shot",
                    bbox=track.bbox,
                    quality=quality,
                    embedding=embedding,
                    aligned_crop=aligned,
                    frame_shape=(h, w),
                )
                track.first_shot_sent = True
                track.best_quality = quality

            # Best-Shot Decision: If this frame is significantly better than before
            elif track.first_shot_sent and quality >= (track.best_quality + BEST_SHOT_DELTA):
                aligned = self.extractor.align_face(frame_bgr, track.landmarks)
                embedding = self.extractor.extract_embedding(aligned)
                self.client.dispatch_event(
                    track_id=tid,
                    event_type="best_shot",
                    bbox=track.bbox,
                    quality=quality,
                    embedding=embedding,
                    aligned_crop=aligned,
                    frame_shape=(h, w),
                )
                track.best_shot_sent = True
                track.best_quality = quality

        # FPS calculation
        self._frame_count += 1
        elapsed = time.time() - self._start_time
        if elapsed >= 1.0:
            self.fps = self._frame_count / elapsed
            self._frame_count = 0
            self._start_time = time.time()
            self.client.send_heartbeat(self.fps, len(self.tracks))

        # 4. Render Overlay Annotations
        annotated = frame_bgr.copy()
        track_summaries = []

        for tid, track in self.tracks.items():
            x1, y1, x2, y2 = map(int, track.bbox)
            color = (0, 255, 128) if track.first_shot_sent else (0, 165, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = f"ID:{tid} | {track.identity_name}"
            q_label = f"Q:{track.quality:.2f}"
            cv2.putText(annotated, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            cv2.putText(annotated, q_label, (x1, min(h - 5, y2 + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

            track_summaries.append({
                "track_id": tid,
                "bbox": [x1, y1, x2, y2],
                "quality": track.quality,
                "name": track.identity_name,
            })

        # Render Header Info
        status_text = "CLOUD ONLINE" if self.client.is_online else "CLOUD CONNECTING..."
        status_color = (0, 255, 0) if self.client.is_online else (0, 0, 255)
        cv2.putText(annotated, f"FPS: {self.fps:.1f} | {status_text} | Queue: {self.client.event_queue.qsize()}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)

        return annotated, track_summaries

    def close(self):
        self.client.stop()
