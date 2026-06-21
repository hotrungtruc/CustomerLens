import base64
import hashlib
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import cv2
import numpy as np
from fastapi import (APIRouter, Header, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)

# Session store mapping hex tokens to user dicts
ACTIVE_SESSIONS = {}


def get_user_from_token(authorization: str | None = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    token = authorization.split(" ")[1].strip()
    if token not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return ACTIVE_SESSIONS[token]


def require_admin(authorization: str | None = None):
    user = get_user_from_token(authorization)
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403, detail="Unauthorized action: Admin role required"
        )
    return user


from app.core.guest_tracking import GuestTrackManager
from app.core.insight_embedding import InsightEmbedder, cosine_similarities
from app.db.connection import (create_or_update_customer_profile,
                               ensure_schema, get_customer_info,
                               get_db_connection, update_attendance)
from app.utils.shared_frame import SharedFrameManager
from config import (CAMERA_INDEX, CHECKIN_COOLDOWN_SECONDS,
                    CUSTOMER_PROFILE_HOLD_SECONDS, ENCODE_FILE, FRAME_HEIGHT,
                    FRAME_JPEG_QUALITY, FRAME_WIDTH, GUEST_CACHE_FILE,
                    GUEST_CREATION_BUFFER_SIZE, IMAGE_JPEG_QUALITY, IMAGES_DIR,
                    MIN_DETECTION_SCORE, MIN_FACE_BBOX_SIZE,
                    PROCESS_EVERY_N_FRAMES, SIMILARITY_THRESHOLD,
                    TRACK_BUFFER_SIZE, TRACK_IOU_THRESHOLD)

router = APIRouter()

embedder = None
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


class CameraState:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.shared_frame_mgr = SharedFrameManager(FRAME_WIDTH, FRAME_HEIGHT, 3)
        self.track_manager = GuestTrackManager(
            ENCODE_FILE,
            guest_cache_file=GUEST_CACHE_FILE,
            buffer_size=TRACK_BUFFER_SIZE,
            guest_creation_buffer_size=GUEST_CREATION_BUFFER_SIZE,
            similarity_threshold=SIMILARITY_THRESHOLD,
            iou_threshold=TRACK_IOU_THRESHOLD,
            min_bbox_size=MIN_FACE_BBOX_SIZE,
            min_detection_score=MIN_DETECTION_SCORE,
            guest_prefix=f"GUEST_{camera_id}",
        )
        self.current_customer_id = None
        self.current_customer_seen_at = None
        self.active = True
        self.ai_thread = None
        self.subscribers = set()
        self.latest_jpeg_bytes = None
        self.last_frame_time = None
        self.start_ai_loop()

    def start_ai_loop(self):
        def _ai_loop():
            last_seen_version = -1
            frame_count = 0
            while self.active:
                try:
                    if embedder is None:
                        time.sleep(0.1)
                        continue

                    frame_version = self.shared_frame_mgr.get_version()
                    if frame_version == last_seen_version:
                        time.sleep(0.05)
                        continue

                    last_seen_version = frame_version
                    frame_count += 1

                    # Apply frame sampling to skip unnecessary processing
                    if frame_count % PROCESS_EVERY_N_FRAMES != 0:
                        continue

                    frame = self.shared_frame_mgr.read_frame()
                    self._process_camera_frame(frame)
                except Exception:
                    time.sleep(0.05)

        self.ai_thread = threading.Thread(target=_ai_loop, daemon=True)
        self.ai_thread.start()

    def _process_camera_frame(self, frame):
        if embedder is None or frame is None:
            return

        detections = embedder.detect(frame)
        face_records = []
        for bbox, landmark, score in zip(*detections):
            x1, y1, x2, y2 = map(int, bbox)
            quality_ok = embedder.is_quality_ok((x1, y1, x2, y2), score)
            guest_quality_ok = embedder.is_guest_quality_ok((x1, y1, x2, y2), score, landmark)

            face_records.append(
                {
                    "bbox": (x1, y1, x2, y2),
                    "landmark": landmark,
                    "score": float(score),
                    "quality_ok": quality_ok,
                    "guest_quality_ok": guest_quality_ok,
                    "embedding": None,
                }
            )

        tracked_faces = self.track_manager.process_faces(
            face_records, frame=frame, embedder=embedder
        )
        annot_faces = []

        for face in tracked_faces:
            x1, y1, x2, y2 = face["bbox"]
            quality_ok = face["quality_ok"]
            customer_id = face["customer_id"]
            track_id = face["track_id"]

            if customer_id:
                self.current_customer_id = customer_id
                self.current_customer_seen_at = datetime.now()
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

        self.shared_frame_mgr.update_annotations(annot_faces, self.current_customer_id)


CAMERA_STATES = {}
CAMERA_STATES_LOCK = threading.Lock()


def get_camera_state(camera_id: str | None = None) -> CameraState:
    cid = (camera_id or "default").strip()
    with CAMERA_STATES_LOCK:
        if cid not in CAMERA_STATES:
            CAMERA_STATES[cid] = CameraState(cid)
        return CAMERA_STATES[cid]


def _run_cpu_bound(func, *args, **kwargs):
    if cpu_executor is None:
        return func(*args, **kwargs)

    future = cpu_executor.submit(func, *args, **kwargs)
    return future.result()


def init_models(ai_executor: ThreadPoolExecutor | None = None):
    global embedder, cpu_executor
    embedder = InsightEmbedder()
    cpu_executor = ai_executor

    # Initialize default camera state
    get_camera_state("default")


def __decode_encodings(payload):
    import pickle

    encode_list_known_with_ids = pickle.loads(payload)
    if (
        isinstance(encode_list_known_with_ids, (list, tuple))
        and len(encode_list_known_with_ids) == 2
    ):
        return encode_list_known_with_ids[0], encode_list_known_with_ids[1]
    # Fallback: return empty lists to avoid breaking callers
    return [], []


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
            ann = (
                shared_frame_mgr.get_annotations()
                if shared_frame_mgr is not None
                else {"faces": []}
            )
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
                last_display_faces.append(
                    {"bbox": (x1, y1, x2, y2), "color": color, "label": label}
                )

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


@router.post("/api/login")
async def api_login(request: Request):
    payload = await request.json()
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()

    if not username or not password:
        raise HTTPException(
            status_code=400, detail="Username and password are required"
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, password_hash, role, cameras FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        if row["password_hash"] != pwd_hash:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # Create session
        token = secrets.token_hex(16)
        cameras_list = []
        if row["cameras"]:
            cameras_list = [c.strip() for c in row["cameras"].split(",") if c.strip()]

        user_info = {
            "username": row["username"],
            "role": row["role"],
            "cameras": cameras_list,
        }
        ACTIVE_SESSIONS[token] = user_info

        return {"success": True, "token": token, "user": user_info}
    finally:
        conn.close()


@router.get("/api/customer_info")
def api_customer_info(camera_id: str | None = None):
    state = get_camera_state(camera_id)
    if not state.current_customer_id:
        return {"status": "no_detection"}

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, state.current_customer_id)

        if not customer_info:
            return {"status": "not_found"}

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
            "image": None,
        }
    finally:
        conn.close()


def _apply_profile_to_payload(payload: dict, info: dict):
    """Populate a payload dict from a customer profile dict."""
    payload.update(
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


def _invalidate_profile_cache(customer_id: str):
    """Clear cached_profile for a customer_id across all active camera states."""
    with CAMERA_STATES_LOCK:
        for cid, cam_state in CAMERA_STATES.items():
            if cam_state.track_manager:
                for tid, track in cam_state.track_manager.tracks.items():
                    if (
                        track.cached_profile
                        and track.cached_profile.get("customer_id") == customer_id
                    ):
                        track.cached_profile = None


def _build_customers_payload(faces: list, conn=None, camera_state=None) -> list:
    """Build the customers list from raw face annotations + DB lookups.

    Uses track-level caching: on the first frame where a face is recognized,
    the profile is fetched from the database and stored in TrackState.cached_profile.
    All subsequent frames for the same track reuse the cache (0 DB queries).
    """
    customers = []
    tracks = (
        camera_state.track_manager.tracks
        if camera_state and camera_state.track_manager
        else {}
    )

    for face in faces:
        customer_id = face.get("customer_id")
        track_id = face.get("track_id")

        payload = {
            "tile_id": f"tile_{track_id}",
            "track_id": track_id,
            "bbox": face.get("bbox"),
            "detected": bool(customer_id),
            "id": customer_id,
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
        }

        if customer_id:
            # 1) Check track-level cache first
            track = tracks.get(track_id)
            info = track.cached_profile if track else None

            # 2) Cache miss → query DB and store in track
            if not info:
                local_conn = conn or get_db_connection()
                try:
                    info = get_customer_info(local_conn, customer_id)
                finally:
                    if conn is None:
                        local_conn.close()
                if info and track:
                    track.cached_profile = info

            if info:
                _apply_profile_to_payload(payload, info)

        customers.append(payload)

    customers.sort(key=lambda c: c.get("track_id") or 0)
    return customers


@router.get("/api/customers_overview")
def api_customers_overview(camera_id: str | None = None):
    state = get_camera_state(camera_id)
    if state.shared_frame_mgr is None:
        return {
            "status": "no_detection",
            "customers": [],
            "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
        }

    annotations = state.shared_frame_mgr.get_annotations()
    faces = annotations.get("faces", [])
    w = state.shared_frame_mgr.width
    h = state.shared_frame_mgr.height

    if not faces:
        return {
            "status": "no_detection",
            "customers": [],
            "frame_size": {"width": w, "height": h},
        }

    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customers = _build_customers_payload(faces, conn, camera_state=state)
        status = (
            "success"
            if any(item.get("detected") for item in customers)
            else "no_detection"
        )
        return {
            "status": status,
            "customers": customers,
            "frame_size": {"width": w, "height": h},
        }
    finally:
        conn.close()


@router.put("/api/customer_profile")
async def api_customer_profile(
    request: Request, authorization: str | None = Header(None)
):
    require_admin(authorization)
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

        if source_id.startswith("GUEST_") and final_id != source_id:
            camera_id = "default"
            parts = source_id.split("_")
            if len(parts) >= 3:
                prefix = "_".join(parts[:-2])
                if prefix.startswith("GUEST_"):
                    camera_id = prefix[len("GUEST_") :]
            state = get_camera_state(camera_id)
            if state.track_manager is not None:
                state.track_manager.promote_guest(source_id, final_id)
                with CAMERA_STATES_LOCK:
                    for other_cid, other_state in CAMERA_STATES.items():
                        if other_state.track_manager:
                            other_state.track_manager.load_known_embeddings()

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
        # Invalidate track-level caches for the updated customer so future
        # frames pick up fresh data from the database.
        _invalidate_profile_cache(final_id)
        conn.close()


@router.post("/api/check_in")
def api_check_in(camera_id: str | None = None):
    state = get_camera_state(camera_id)
    if not state.current_customer_id:
        return {"success": False, "message": "No face detected"}

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, state.current_customer_id)

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
                state.current_customer_id,
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
    camera_id = payload.get("camera_id")

    if frame is None:
        return {"success": False, "message": "Invalid frame"}

    state = get_camera_state(camera_id)
    if state.shared_frame_mgr is not None:
        state.shared_frame_mgr.write_frame(frame)

    return {"success": True}


@router.post("/api/promote_guest")
async def api_promote_guest(request: Request, authorization: str | None = Header(None)):
    require_admin(authorization)
    """Promote a GUEST_* id into the known encodings.

    Expects JSON: { "guest_id": "GUEST_...", "new_id": "<customer_id>" }
    The new_id should correspond to a customer record created in the DB by the frontend.
    """
    payload = await request.json()
    guest_id = payload.get("guest_id")
    new_id = payload.get("new_id")
    if not guest_id or not new_id:
        return {"success": False, "message": "guest_id and new_id required"}

    camera_id = "default"
    if guest_id.startswith("GUEST_"):
        parts = guest_id.split("_")
        if len(parts) >= 3:
            prefix = "_".join(parts[:-2])
            if prefix.startswith("GUEST_"):
                camera_id = prefix[len("GUEST_") :]

    state = get_camera_state(camera_id)
    if not state.track_manager:
        return {
            "success": False,
            "message": f"track manager not initialized for camera {camera_id}",
        }

    ok = state.track_manager.promote_guest(guest_id, new_id)
    if ok:
        with CAMERA_STATES_LOCK:
            for other_cid, other_state in CAMERA_STATES.items():
                if other_state.track_manager:
                    other_state.track_manager.load_known_embeddings()
        return {"success": True}
    return {"success": False, "message": "guest not found"}


@router.get("/api/customers")
def api_get_all_customers(authorization: str | None = Header(None)):
    require_admin(authorization)
    conn = get_db_connection()
    ensure_schema(conn)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT customer_id as id, name, phone, note, total_visits as total_attendance, last_visit as last_attendance_time
            FROM customers
            """)
        rows = cursor.fetchall()
        customers = [dict(row) for row in rows]
        return {"status": "success", "customers": customers}
    finally:
        conn.close()


@router.get("/api/customer_profile_by_id/{customer_id}")
def api_get_customer_by_id(customer_id: str, authorization: str | None = Header(None)):
    require_admin(authorization)
    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customer_info = get_customer_info(conn, customer_id)
        if not customer_info:
            return {
                "status": "not_found",
                "message": f"Customer '{customer_id}' not found",
            }
        return {
            "status": "success",
            "customer": {
                "id": customer_info["customer_id"],
                "name": customer_info["name"],
                "phone": customer_info.get("phone"),
                "total_attendance": customer_info["total_attendance"],
                "last_attendance_time": customer_info["last_attendance_time"],
                "note": customer_info.get("note"),
            },
        }
    finally:
        conn.close()


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@router.websocket("/ws/publish/{session_id}")
async def websocket_publish(websocket: WebSocket, session_id: str):
    """Persistent bidirectional channel for the camera device (Publisher).

    Client sends:  Raw binary bytes of JPEG image
    Server sends:  { "customers": [...], "frame_size": { "width": N, "height": N } }
    Server also broadcasts the JPEG and data to all subscribers.
    """
    await websocket.accept()
    state = get_camera_state(session_id)

    try:
        while True:
            try:
                data = await websocket.receive_bytes()
            except Exception:
                break

            # Write frame into this camera's state
            if data:
                state.latest_jpeg_bytes = data
                state.last_frame_time = datetime.now()
                try:
                    img_array = np.frombuffer(data, dtype=np.uint8)
                    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if frame is not None:
                        state.shared_frame_mgr.write_frame(frame)
                except Exception:
                    pass

            # Return current annotations (AI thread updates asynchronously)
            annotations = state.shared_frame_mgr.get_annotations()
            faces = annotations.get("faces", [])
            customers = _build_customers_payload(faces, conn=None, camera_state=state)

            w = state.shared_frame_mgr.width
            h = state.shared_frame_mgr.height
            json_payload = {
                "customers": customers,
                "frame_size": {"width": w, "height": h},
            }

            # Send back to publisher
            try:
                await websocket.send_json(json_payload)
            except Exception:
                break
                
            # Broadcast to subscribers
            dead_subs = set()
            for sub in list(state.subscribers):
                try:
                    if state.latest_jpeg_bytes:
                        await sub.send_bytes(state.latest_jpeg_bytes)
                    await sub.send_json(json_payload)
                except Exception:
                    dead_subs.add(sub)
                    
            for dead in dead_subs:
                state.subscribers.discard(dead)

    except WebSocketDisconnect:
        pass


@router.websocket("/ws/subscribe/{session_id}")
async def websocket_subscribe(websocket: WebSocket, session_id: str):
    """Channel for Management devices to view the video feed."""
    await websocket.accept()
    state = get_camera_state(session_id)
    state.subscribers.add(websocket)
    try:
        # Keep connection open. The publisher loop will pump data into it.
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        state.subscribers.discard(websocket)


@router.get("/api/cameras/active")
def api_get_active_cameras():
    """Returns a list of actively publishing camera session IDs."""
    active = []
    now = datetime.now()
    with CAMERA_STATES_LOCK:
        for cid, state in CAMERA_STATES.items():
            if state.last_frame_time and (now - state.last_frame_time).total_seconds() < 5:
                active.append(cid)
    return {"status": "success", "active_cameras": active}
