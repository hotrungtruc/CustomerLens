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
from app.db.connection import (
    create_or_update_customer_profile,
    ensure_schema,
    get_customer_info,
    get_db_connection,
    update_attendance,
)
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



def _decode_frame_payload(image_data: str | None):
    if not image_data:
        return None

    if "," in image_data:
        _, image_data = image_data.split(",", 1)

    try:
        raw_bytes = base64.b64decode(image_data)
    except Exception:
        return None

    image_array = np.frombuffer(raw_bytes, dtype=np.uint8)
    return cv2.imdecode(image_array, cv2.IMREAD_COLOR)


def _process_frame(frame):
    global current_customer_id, current_customer_seen_at, shared_frame_mgr

    if embedder is None or track_manager is None or frame is None:
        return []

    # Run detection directly (already on AI worker thread)
    detections = embedder.detect(frame)
    face_records = []
    for bbox, landmark, score in zip(*detections):
        x1, y1, x2, y2 = map(int, bbox)
        quality_ok = embedder.is_quality_ok((x1, y1, x2, y2), score)

        # Lazy embedding: we just pass the landmark to the tracker.
        # Tracker will compute embedding only if needed!
        face_records.append(
            {
                "bbox": (x1, y1, x2, y2),
                "landmark": landmark,
                "score": float(score),
                "quality_ok": quality_ok,
                "embedding": None,
            }
        )

    tracked_faces = track_manager.process_faces(face_records, frame=frame, embedder=embedder)
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

        annot_faces.append(
            {
                "bbox": (x1, y1, x2, y2),
                "color": color,
                "label": label,
                "customer_id": customer_id,
                "track_id": track_id,
                "quality_ok": quality_ok,
            }
        )

    if shared_frame_mgr is not None:
        shared_frame_mgr.update_annotations(annot_faces, current_customer_id)

    return annot_faces


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
        last_seen_version = -1
        frame_count = 0
        while True:
            try:
                if embedder is None or track_manager is None or shared_frame_mgr is None:
                    time.sleep(0.1)
                    continue

                frame_version = shared_frame_mgr.get_version()
                if frame_version == last_seen_version:
                    time.sleep(0.05)
                    continue

                last_seen_version = frame_version
                frame_count += 1
                
                # Apply frame sampling to skip unnecessary processing
                if frame_count % PROCESS_EVERY_N_FRAMES != 0:
                    continue

                frame = shared_frame_mgr.read_frame()
                _process_frame(frame)
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
            "id": customer_info["customer_id"],
            "name": customer_info["name"],
            "phone": customer_info.get("phone"),
            "email": customer_info.get("email"),
            "occupation": customer_info.get("occupation"),
            "registered_at": customer_info.get("registered_at"),
            "tenure": customer_info.get("tenure"),
            "loyalty_tier": customer_info.get("loyalty_tier"),
            "total_visits": customer_info.get("total_visits", 0),
            "last_visit": customer_info.get("last_visit"),
            "total_spending": customer_info.get("total_spending", 0),
            "service_category": customer_info["service_category"],
            "service_start_year": customer_info["service_start_year"],
            "customer_tenure_years": customer_info["customer_tenure_years"],
            "loyalty_tier": customer_info["loyalty_tier"],
            "customer_type": customer_info["customer_type"],
            "customer_status": customer_info["status"],
            "has_face_embedding": customer_info.get("has_face_embedding"),
            "face_embedding_dim": customer_info.get("face_embedding_dim"),
            "face_embedding_model": customer_info.get("face_embedding_model"),
            "major": customer_info["major"],
            "year": customer_info["year"],
            "starting_year": customer_info["starting_year"],
            "total_attendance": customer_info["total_attendance"],
            "visit_count": customer_info["total_attendance"],
            "phone": customer_info.get("phone"),
            "note": customer_info.get("note"),
            "standing": customer_info["standing"],
            "last_attendance_time": customer_info["last_attendance_time"],
            "last_visit": customer_info["last_attendance_time"],
            "image": img_base64,
        }
    finally:
        conn.close()


@router.get("/api/customers_overview")
def api_customers_overview():
    if shared_frame_mgr is None:
        return {
            "status": "no_detection",
            "customers": [],
            "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
        }

    annotations = shared_frame_mgr.get_annotations()
    faces = annotations.get("faces", [])
    if not faces:
        return {
            "status": "no_detection",
            "customers": [],
            "frame_size": {"width": shared_frame_mgr.width, "height": shared_frame_mgr.height},
        }

    conn = get_db_connection()
    ensure_schema(conn)

    customers = []
    try:
        for face in faces:
            customer_id = face.get("customer_id")
            track_id = face.get("track_id")

            base_payload = {
                "tile_id": f"tile_{track_id}",
                "track_id": track_id,
                "bbox": face.get("bbox"),
                "detected": bool(customer_id),
                "id": customer_id or f"T{track_id}",
                "name": "Khach moi",
                "email": None,
                "occupation": "General",
                "registered_at": None,
                "tenure": 0,
                "loyalty_tier": "Standard",
                "total_visits": 0,
                "last_visit": None,
                "total_spending": 0,
                "service_category": "General",
                "service_start_year": 0,
                "customer_tenure_years": 0,
                "loyalty_tier": "Standard",
                "customer_type": "guest",
                "customer_status": "temporary",
                "has_face_embedding": 0,
                "face_embedding_dim": None,
                "face_embedding_model": None,
                "major": "General",
                "year": 0,
                "starting_year": 0,
                "total_attendance": 0,
                "visit_count": 0,
                "phone": None,
                "note": None,
                "standing": "G",
                "last_attendance_time": None,
                "last_visit": None,
            }

            if customer_id:
                info = get_customer_info(conn, customer_id)
                if info:
                    base_payload.update(
                        {
                            "id": info["customer_id"],
                            "name": info["name"] or "Khach moi",
                            "email": info.get("email"),
                            "occupation": info.get("occupation", "General"),
                            "registered_at": info.get("registered_at"),
                            "tenure": info.get("tenure", 0),
                            "loyalty_tier": info.get("loyalty_tier", "Standard"),
                            "total_visits": info.get("total_visits", 0),
                            "last_visit": info.get("last_visit"),
                            "total_spending": info.get("total_spending", 0),
                            "service_category": info.get("service_category", "General"),
                            "service_start_year": info.get("service_start_year", 0),
                            "customer_tenure_years": info.get("customer_tenure_years", 0),
                            "loyalty_tier": info.get("loyalty_tier", "Standard"),
                            "customer_type": info.get("customer_type", "guest"),
                            "customer_status": info.get("status", "active"),
                            "has_face_embedding": info.get("has_face_embedding"),
                            "face_embedding_dim": info.get("face_embedding_dim"),
                            "face_embedding_model": info.get("face_embedding_model"),
                            "major": info.get("major", "General"),
                            "year": info.get("year", 0),
                            "starting_year": info.get("starting_year", 0),
                            "total_attendance": info.get("total_attendance", 0),
                            "visit_count": info.get("total_attendance", 0),
                            "phone": info.get("phone"),
                            "note": info.get("note"),
                            "standing": info.get("standing", "G"),
                            "last_attendance_time": info.get("last_attendance_time"),
                            "last_visit": info.get("last_attendance_time"),
                        }
                    )

            customers.append(base_payload)

        status = "success" if any(item.get("detected") for item in customers) else "no_detection"
        
        customers.sort(key=lambda c: c.get("track_id") or 0)
        
        return {
            "status": status,
            "customers": customers,
            "frame_size": {"width": shared_frame_mgr.width, "height": shared_frame_mgr.height},
        }
    finally:
        conn.close()


@router.put("/api/customer_profile")
async def api_customer_profile(request: Request):
    payload = await request.json()
    selected_id = (payload.get("id") or "").strip()
    source_id = (payload.get("source_id") or selected_id or "").strip()
    name = payload.get("name")
    phone = payload.get("phone")
    note = payload.get("note")
    service_category = payload.get("service_category")
    service_start_year = payload.get("service_start_year")
    customer_tenure_years = payload.get("customer_tenure_years")
    loyalty_tier = payload.get("loyalty_tier")

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        writable_id = selected_id
        if writable_id.startswith("T") or writable_id.startswith("GUEST_"):
            writable_id = None

        try:
            final_id, created = create_or_update_customer_profile(
                conn,
                customer_id=writable_id,
                source_id=source_id,
                name=name,
                phone=phone,
                note=note,
                service_category=service_category,
                service_start_year=service_start_year,
                customer_tenure_years=customer_tenure_years,
                loyalty_tier=loyalty_tier,
            )
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

        if source_id.startswith("GUEST_") and final_id != source_id and track_manager is not None:
            track_manager.promote_guest(source_id, final_id)

        customer_info = get_customer_info(conn, final_id)
        if not customer_info:
            return {"success": False, "message": "Customer not found after save"}

        return {
            "success": True,
            "created": created,
            "customer": {
                "id": customer_info["customer_id"],
                "customer_id": customer_info["customer_id"],
                "name": customer_info["name"],
                "phone": customer_info.get("phone"),
                "email": customer_info.get("email"),
                "occupation": customer_info.get("occupation"),
                "registered_at": customer_info.get("registered_at"),
                "tenure": customer_info.get("tenure"),
                "loyalty_tier": customer_info.get("loyalty_tier"),
                "total_visits": customer_info.get("total_visits", 0),
                "last_visit": customer_info.get("last_visit"),
                "total_spending": customer_info.get("total_spending", 0),
                "note": customer_info.get("note"),
                "service_category": customer_info.get("service_category"),
                "service_start_year": customer_info.get("service_start_year"),
                "customer_tenure_years": customer_info.get("customer_tenure_years"),
                "loyalty_tier": customer_info.get("loyalty_tier"),
                "customer_type": customer_info.get("customer_type"),
                "customer_status": customer_info.get("status"),
                "has_face_embedding": customer_info.get("has_face_embedding"),
                "face_embedding_dim": customer_info.get("face_embedding_dim"),
                "face_embedding_model": customer_info.get("face_embedding_model"),
                "visit_count": customer_info.get("total_attendance", 0),
                "last_visit": customer_info.get("last_attendance_time"),
                "total_attendance": customer_info.get("total_attendance", 0),
                "last_attendance_time": customer_info.get("last_attendance_time"),
            },
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


@router.post("/api/check_in/{customer_id}")
def api_check_in_by_id(customer_id: str):
    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, customer_id)

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
                customer_id,
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


@router.post("/api/process_frame")
async def api_process_frame(request: Request):
    payload = await request.json()
    frame = _decode_frame_payload(payload.get("image"))

    if frame is None:
        return {"success": False, "message": "Invalid frame"}

    if shared_frame_mgr is not None:
        shared_frame_mgr.write_frame(frame)

    return {"success": True}


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

@router.get("/api/customers")
def api_get_all_customers():
    conn = get_db_connection()
    ensure_schema(conn)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT customer_id as id, name, phone, note, total_visits as total_attendance, last_visit as last_attendance_time
            FROM customers
            """
        )
        rows = cursor.fetchall()
        customers = [dict(row) for row in rows]
        return {"status": "success", "customers": customers}
    finally:
        conn.close()

@router.get("/api/customer_profile_by_id/{customer_id}")
def api_get_customer_by_id(customer_id: str):
    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customer_info = get_customer_info(conn, customer_id)
        if not customer_info:
            return {"status": "not_found", "message": f"Customer '{customer_id}' not found"}
        return {
            "status": "success",
            "customer": {
                "id": customer_info["customer_id"],
                "name": customer_info["name"],
                "phone": customer_info.get("phone"),
                "total_attendance": customer_info["total_attendance"],
                "last_attendance_time": customer_info["last_attendance_time"],
                "note": customer_info.get("note"),
            }
        }
    finally:
        conn.close()
