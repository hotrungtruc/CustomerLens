import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import threading
import time
from fastapi import APIRouter, Request

from app.utils.shared_frame import SharedFrameManager

from app.core.insight_embedding import InsightEmbedder, cosine_similarities
from app.core.guest_tracking import GuestTrackManager
from app.db.connection import ensure_schema, get_customer_info, get_db_connection, update_attendance
from config import (
    CAMERA_INDEX,
    CHECKIN_COOLDOWN_SECONDS,
    CUSTOMER_PROFILE_HOLD_SECONDS,
    ENCODE_FILE,
    GUEST_CREATION_BUFFER_SIZE,
    GUEST_CACHE_FILE,
    FRAME_HEIGHT,
    FRAME_JPEG_QUALITY,
    FRAME_WIDTH,
    IMAGES_DIR,
    IMAGE_JPEG_QUALITY,
    MIN_DETECTION_SCORE,
    MIN_FACE_BBOX_SIZE,
    PROCESS_EVERY_N_FRAMES,
    TRACK_BUFFER_SIZE,
    TRACK_IOU_THRESHOLD,
    SIMILARITY_THRESHOLD,
)

router = APIRouter()

embedder = None
encode_list_known = None
customer_ids = None
current_customer_id = None
current_customer_seen_at = None
track_manager = None
shared_frame_mgr = None
cpu_executor: ThreadPoolExecutor | None = None



def _run_cpu_bound(func, *args, **kwargs):
    if cpu_executor is None:
        return func(*args, **kwargs)

    future = cpu_executor.submit(func, *args, **kwargs)
    return future.result()


def init_models(ai_executor: ThreadPoolExecutor | None = None):
    global embedder, encode_list_known, customer_ids, track_manager, cpu_executor
    embedder = InsightEmbedder()
    cpu_executor = ai_executor
    track_manager = GuestTrackManager(
        ENCODE_FILE,
        guest_cache_file=GUEST_CACHE_FILE,
        buffer_size=TRACK_BUFFER_SIZE,
        guest_creation_buffer_size=GUEST_CREATION_BUFFER_SIZE,
        similarity_threshold=SIMILARITY_THRESHOLD,
        iou_threshold=TRACK_IOU_THRESHOLD,
        min_bbox_size=MIN_FACE_BBOX_SIZE,
        min_detection_score=MIN_DETECTION_SCORE,
    )
    encode_list_known = track_manager.known_embeddings
    customer_ids = track_manager.known_ids
    # create shared frame buffer and start AI worker thread
    global shared_frame_mgr
    if shared_frame_mgr is None:
        shared_frame_mgr = SharedFrameManager(FRAME_WIDTH, FRAME_HEIGHT, 3)

    def _ai_loop():
        global current_customer_id, current_customer_seen_at
        while True:
            try:
                if embedder is None or track_manager is None:
                    time.sleep(0.1)
                    continue

                frame = shared_frame_mgr.read_frame()
                # run detection + tracking on the shared frame
                detections = _run_cpu_bound(embedder.detect, frame)
                face_records = []
                for bbox, landmark, score in zip(*detections):
                    x1, y1, x2, y2 = map(int, bbox)
                    quality_ok = embedder.is_quality_ok((x1, y1, x2, y2), score)
                    embedding = None
                    if quality_ok:
                        embedding = _run_cpu_bound(embedder.get_embedding, frame, landmark)

                    face_records.append(
                        {
                            "bbox": (x1, y1, x2, y2),
                            "score": float(score),
                            "quality_ok": quality_ok,
                            "embedding": embedding,
                        }
                    )

                tracked_faces = track_manager.process_faces(face_records)

                annot_faces = []
                for face in tracked_faces:
                    x1, y1, x2, y2 = face["bbox"]
                    quality_ok = face["quality_ok"]
                    customer_id = face["customer_id"]
                    track_id = face["track_id"]

                    if customer_id:
                        current_customer_id = customer_id
                        current_customer_seen_at = datetime.now()
                        color = (0, 255, 0)
                        label = str(customer_id)
                    elif quality_ok:
                        color = (255, 165, 0)
                        label = f"T{track_id} buffering"
                    else:
                        color = (0, 255, 255)
                        label = f"T{track_id} low quality"

                    annot_faces.append({"bbox": (x1, y1, x2, y2), "color": color, "label": label, "customer_id": customer_id, "track_id": track_id, "quality_ok": quality_ok})

                shared_frame_mgr.update_annotations(annot_faces, current_customer_id)
            except Exception:
                # swallow errors in worker to keep thread alive
                time.sleep(0.05)

    t = threading.Thread(target=_ai_loop, daemon=True)
    t.start()


def __decode_encodings(payload):
    import pickle

    encode_list_known_with_ids = pickle.loads(payload)
    if isinstance(encode_list_known_with_ids, (list, tuple)) and len(
        encode_list_known_with_ids
    ) == 2:
        return encode_list_known_with_ids[0], encode_list_known_with_ids[1]
    # Fallback: return empty lists to avoid breaking callers
    return [], []


def load_customer_image_base64(customer_id):
    for ext in (".png", ".jpg", ".jpeg"):
        path = IMAGES_DIR / f"{customer_id}{ext}"
        if path.exists():
            img = cv2.imread(str(path))
            if img is None:
                continue
            _, buffer = cv2.imencode(
                ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, IMAGE_JPEG_QUALITY]
            )
            return base64.b64encode(buffer).decode()
    return None


def camera_feed():
    global current_customer_id, current_customer_seen_at, track_manager

    # If models/encodings are not initialized, yield a blank frame repeatedly
    if embedder is None:
        blank = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        _, buffer = cv2.imencode(
            ".jpg", blank, [cv2.IMWRITE_JPEG_QUALITY, FRAME_JPEG_QUALITY]
        )
        frame_bytes = buffer.tobytes()

        while True:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: "
                + str(len(frame_bytes)).encode()
                + b"\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    frame_count = 0
    last_display_faces = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            # write current frame to shared buffer for AI thread
            if shared_frame_mgr is not None:
                try:
                    shared_frame_mgr.write_frame(frame)
                except Exception:
                    pass

            # draw annotations provided by AI thread (no heavy copies)
            frame_display = frame
            ann = shared_frame_mgr.get_annotations() if shared_frame_mgr is not None else {"faces": []}
            last_display_faces = []
            for face in ann.get("faces", []):
                x1, y1, x2, y2 = face["bbox"]
                color = face.get("color", (255, 0, 0))
                label = face.get("label", "")
                cv2.rectangle(frame_display, (x1, y1), (x2, y2), color, 3)
                cv2.putText(
                    frame_display,
                    label,
                    (x1, max(0, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    color,
                    2,
                )
                last_display_faces.append({"bbox": (x1, y1, x2, y2), "color": color, "label": label})

            ret, buffer = cv2.imencode(
                ".jpg", frame_display, [cv2.IMWRITE_JPEG_QUALITY, FRAME_JPEG_QUALITY]
            )
            if not ret:
                continue

            frame_bytes = buffer.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: "
                + str(len(frame_bytes)).encode()
                + b"\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )
    finally:
        cap.release()


@router.get("/")
def index():
    return {"status": "ok", "message": "Backend running"}


@router.get("/test")
def test():
    return {"status": "ok", "message": "FastAPI backend is running"}


@router.get("/api/customer_info")
def api_customer_info():
    if not current_customer_id:
        return {"status": "no_detection"}

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, current_customer_id)

        if not customer_info:
            return {"status": "not_found"}

        img_base64 = load_customer_image_base64(current_customer_id)

        return {
            "status": "success",
            "id": customer_info["id"],
            "name": customer_info["name"],
            "major": customer_info["major"],
            "year": customer_info["year"],
            "starting_year": customer_info["starting_year"],
            "total_attendance": customer_info["total_attendance"],
            "standing": customer_info["standing"],
            "last_attendance_time": customer_info["last_attendance_time"],
            "image": img_base64,
        }
    finally:
        conn.close()


@router.post("/api/check_in")
def api_check_in():
    if not current_customer_id:
        return {"success": False, "message": "No face detected"}

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, current_customer_id)

        if not customer_info:
            return {"success": False, "message": "Customer not found"}

        try:
            last_time = datetime.strptime(
                customer_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            last_time = datetime.min

        seconds_elapsed = (datetime.now() - last_time).total_seconds()

        if seconds_elapsed > CHECKIN_COOLDOWN_SECONDS:
            update_attendance(
                conn,
                current_customer_id,
                customer_info["total_attendance"] + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return {"success": True, "message": "Check-in successful"}

        remaining = int(CHECKIN_COOLDOWN_SECONDS - seconds_elapsed)
        return {"success": False, "message": f"Please wait {remaining}s"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}
    finally:
        conn.close()


@router.post("/api/promote_guest")
async def api_promote_guest(request: Request):
    """Promote a GUEST_* id into the known encodings.

    Expects JSON: { "guest_id": "GUEST_...", "new_id": "<customer_id>" }
    The new_id should correspond to a customer record created in the DB by the frontend.
    """
    payload = await request.json()
    guest_id = payload.get("guest_id")
    new_id = payload.get("new_id")
    if not guest_id or not new_id:
        return {"success": False, "message": "guest_id and new_id required"}

    if not track_manager:
        return {"success": False, "message": "track manager not initialized"}

    ok = track_manager.promote_guest(guest_id, new_id)
    if ok:
        return {"success": True}
    return {"success": False, "message": "guest not found"}
