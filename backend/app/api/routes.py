import base64
from datetime import datetime

import cv2
import numpy as np
from flask import Blueprint, Response, jsonify

from app.core.insight_embedding import InsightEmbedder, cosine_similarities
from app.db.connection import ensure_schema, get_customer_info, get_db_connection, update_attendance
from config import (
    CAMERA_INDEX,
    CHECKIN_COOLDOWN_SECONDS,
    ENCODE_FILE,
    FRAME_HEIGHT,
    FRAME_JPEG_QUALITY,
    FRAME_WIDTH,
    IMAGES_DIR,
    IMAGE_JPEG_QUALITY,
    PROCESS_EVERY_N_FRAMES,
    SIMILARITY_THRESHOLD,
)

api_bp = Blueprint("api", __name__)

embedder = None
encode_list_known = None
customer_ids = None
current_customer_id = None


def init_models():
    global embedder, encode_list_known, customer_ids
    embedder = InsightEmbedder()
    with open(ENCODE_FILE, "rb") as f:
        encode_list_known_with_ids = f.read()
    encode_list_known, customer_ids = __decode_encodings(encode_list_known_with_ids)


def __decode_encodings(payload):
    import pickle

    encode_list_known_with_ids = pickle.loads(payload)
    return encode_list_known_with_ids


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
    global current_customer_id

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            frame_display = frame.copy()

            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                faces = embedder.get_faces(frame)
                if faces:
                    detected_face = False
                    for face in faces:
                        similarities = cosine_similarities(
                            encode_list_known, face["embedding"]
                        )
                        if len(similarities) > 0:
                            match_index = np.argmax(similarities)
                            if similarities[match_index] >= SIMILARITY_THRESHOLD:
                                current_customer_id = customer_ids[match_index]
                                detected_face = True

                                x1, y1, x2, y2 = face["bbox"]
                                cv2.rectangle(
                                    frame_display,
                                    (x1, y1),
                                    (x2, y2),
                                    (0, 255, 0),
                                    3,
                                )
                                cv2.putText(
                                    frame_display,
                                        str(current_customer_id),
                                    (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    1,
                                    (0, 255, 0),
                                    2,
                                )
                    if not detected_face:
                        current_customer_id = None
                else:
                    current_customer_id = None

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
