import base64
from datetime import datetime

import cv2
import numpy as np
from flask import Blueprint, Response, jsonify, request

from app.core.insight_embedding import InsightEmbedder, cosine_similarities
from app.core.guest_tracking import GuestTrackManager
from app.db.connection import ensure_schema, get_customer_info, get_db_connection, update_attendance
from config import (
    CAMERA_INDEX,
    CHECKIN_COOLDOWN_SECONDS,
    CUSTOMER_PROFILE_HOLD_SECONDS,
    ENCODE_FILE,
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

api_bp = Blueprint("api", __name__)

embedder = None
encode_list_known = None
customer_ids = None
current_customer_id = None
current_customer_seen_at = None
track_manager = None


def init_models():
    global embedder, encode_list_known, customer_ids, track_manager
    embedder = InsightEmbedder()
    track_manager = GuestTrackManager(
        ENCODE_FILE,
        guest_cache_file=GUEST_CACHE_FILE,
        buffer_size=TRACK_BUFFER_SIZE,
        similarity_threshold=SIMILARITY_THRESHOLD,
        iou_threshold=TRACK_IOU_THRESHOLD,
        min_bbox_size=MIN_FACE_BBOX_SIZE,
        min_detection_score=MIN_DETECTION_SCORE,
    )
    encode_list_known = track_manager.known_embeddings
    customer_ids = track_manager.known_ids


def __decode_encodings(payload):
    import pickle

    encode_list_known_with_ids = pickle.loads(payload)
    if isinstance(encode_list_known_with_ids, (list, tuple)) and len(
        encode_list_known_with_ids
    ) == 2:
        return encode_list_known_with_ids[0], encode_list_known_with_ids[1]
    # Fallback: return empty lists to avoid breaking callers
    return [], []


def __load_customer_image_base64(customer_id):
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
            frame_display = frame.copy()
            # Do not clear immediately; use hold window to avoid flicker

            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                detections = embedder.detect(frame)
                face_records = []

                for bbox, landmark, score in zip(*detections):
                    x1, y1, x2, y2 = map(int, bbox)
                    width = max(0, x2 - x1)
                    height = max(0, y2 - y1)
                    quality_ok = width >= MIN_FACE_BBOX_SIZE and height >= MIN_FACE_BBOX_SIZE and float(score) >= MIN_DETECTION_SCORE

                    embedding = None
                    if quality_ok:
                        embedding = embedder.get_embedding(frame, landmark)

                    face_records.append(
                        {
                            "bbox": (x1, y1, x2, y2),
                            "score": float(score),
                            "quality_ok": quality_ok,
                            "embedding": embedding,
                        }
                    )

                tracked_faces = track_manager.process_faces(face_records)
                last_display_faces = []

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
                        {
                            "bbox": (x1, y1, x2, y2),
                            "color": color,
                            "label": label,
                        }
                    )

                # Release recognized ID after hold window expires
                if current_customer_id and current_customer_seen_at:
                    elapsed = (datetime.now() - current_customer_seen_at).total_seconds()
                    if elapsed > CUSTOMER_PROFILE_HOLD_SECONDS:
                        current_customer_id = None
                        current_customer_seen_at = None
            else:
                # Re-draw last known boxes on skipped frames so bbox stays visible.
                for face in last_display_faces:
                    x1, y1, x2, y2 = face["bbox"]
                    color = face["color"]
                    label = face["label"]
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


@api_bp.route("/")
def index():
    return {"status": "ok", "message": "Backend running"}


@api_bp.route("/test")
def test():
    return {"status": "ok", "message": "Flask app is running"}


@api_bp.route("/video_feed")
def video_feed():
    return Response(
        camera_feed(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@api_bp.route("/api/customer_info")
def api_customer_info():
    if not current_customer_id:
        return jsonify({"status": "no_detection"})

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, current_customer_id)

        if not customer_info:
            return jsonify({"status": "not_found"})

        img_base64 = __load_customer_image_base64(current_customer_id)

        return jsonify(
            {
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
        )
    finally:
        conn.close()


@api_bp.route("/api/check_in", methods=["POST"])
def api_check_in():
    if not current_customer_id:
        return jsonify({"success": False, "message": "No face detected"})

    conn = get_db_connection()
    ensure_schema(conn)

    try:
        customer_info = get_customer_info(conn, current_customer_id)

        if not customer_info:
            return jsonify({"success": False, "message": "Customer not found"})

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
            return jsonify({"success": True, "message": "Check-in successful"})

        remaining = int(CHECKIN_COOLDOWN_SECONDS - seconds_elapsed)
        return jsonify({"success": False, "message": f"Please wait {remaining}s"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})
    finally:
        conn.close()


@api_bp.route("/api/promote_guest", methods=["POST"])
def api_promote_guest():
    """Promote a GUEST_* id into the known encodings.

    Expects JSON: { "guest_id": "GUEST_...", "new_id": "<customer_id>" }
    The new_id should correspond to a customer record created in the DB by the frontend.
    """
    payload = request.get_json() or {}
    guest_id = payload.get("guest_id")
    new_id = payload.get("new_id")
    if not guest_id or not new_id:
        return jsonify({"success": False, "message": "guest_id and new_id required"}), 400

    if not track_manager:
        return jsonify({"success": False, "message": "track manager not initialized"}), 500

    ok = track_manager.promote_guest(guest_id, new_id)
    if ok:
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "guest not found"}), 404
