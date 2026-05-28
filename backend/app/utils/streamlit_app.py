import time
from datetime import datetime

import cv2
import numpy as np
import streamlit as st

from app.core.insight_embedding import InsightEmbedder
from app.core.guest_tracking import GuestTrackManager
from app.db.connection import get_customer_info, get_db_connection, update_attendance
from config import ENCODE_FILE, GUEST_CACHE_FILE, GUEST_CREATION_BUFFER_SIZE, IMAGES_DIR, MIN_DETECTION_SCORE, MIN_FACE_BBOX_SIZE, SIMILARITY_THRESHOLD, TRACK_BUFFER_SIZE, TRACK_IOU_THRESHOLD

st.set_page_config(
    page_title="Face Recognition System",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_resource
def load_models():
    embedder = InsightEmbedder()
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
    return embedder, track_manager


@st.cache_resource
def get_connection():
    conn = get_db_connection()
    return conn


def load_customer_image(customer_id):
    for ext in (".png", ".jpg", ".jpeg"):
        path = IMAGES_DIR / f"{customer_id}{ext}"
        if path.exists():
            return cv2.imread(str(path))
    return None


def update_attendance_record(conn, customer_id):
    customer_info = get_customer_info(conn, customer_id)
    if not customer_info:
        return False, "Customer record not found"

    try:
        last_time = datetime.strptime(
            customer_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError):
        last_time = datetime.min

    seconds_elapsed = (datetime.now() - last_time).total_seconds()

    if seconds_elapsed > 30:
        update_attendance(
            conn,
            customer_id,
            customer_info["total_attendance"] + 1,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        return True, "Check-in successful"

    remaining = int(30 - seconds_elapsed)
    return False, f"Please wait {remaining}s"


def main():
    st.title("Smart Front-door AI")

    try:
        embedder, track_manager = load_models()
        conn = get_connection()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return

    if "cap" not in st.session_state:
        st.session_state.cap = cv2.VideoCapture(0)
        st.session_state.cap.set(3, 640)
        st.session_state.cap.set(4, 480)
        st.session_state.detected_id = None
        st.session_state.frame_count = 0

    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        st.subheader("Camera")
        camera_placeholder = st.empty()

        ret, frame = st.session_state.cap.read()

        if ret:
            frame_display = frame.copy()

            st.session_state.frame_count += 1
            if st.session_state.frame_count % 3 == 0:
                detections = embedder.detect(frame)
                face_records = []

                for bbox, landmark, score in zip(*detections):
                    x1, y1, x2, y2 = map(int, bbox)
                    quality_ok = embedder.is_quality_ok((x1, y1, x2, y2), score)

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
                st.session_state.detected_id = None
                for face in tracked_faces:
                    x1, y1, x2, y2 = face["bbox"]
                    if face["customer_id"]:
                        st.session_state.detected_id = face["customer_id"]
                        color = (0, 255, 0)
                        label = str(face["customer_id"])
                    elif face["quality_ok"]:
                        color = (255, 165, 0)
                        label = f"T{face['track_id']} buffering"
                    else:
                        color = (0, 255, 255)
                        label = f"T{face['track_id']} low quality"

                    cv2.rectangle(frame_display, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        frame_display,
                        label,
                        (x1, max(0, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        color,
                        2,
                    )

            frame_rgb = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)
            camera_placeholder.image(frame_rgb, width=640)
        else:
            st.error("Khong the truy cap camera")

    with col2:
        st.subheader("Customer profile")

        if st.session_state.detected_id:
            customer_id = st.session_state.detected_id
            customer_info = get_customer_info(conn, customer_id)

            if customer_info:
                customer_img = load_customer_image(customer_id)
                if customer_img is not None:
                    customer_img_rgb = cv2.cvtColor(customer_img, cv2.COLOR_BGR2RGB)
                    st.image(customer_img_rgb, width=300, caption=f"ID: {customer_id}")
                else:
                    st.info("No photo available")

                st.divider()

                st.markdown("### Customer details")
                st.write(f"Name: {customer_info['name']}")
                st.write(f"Customer ID: {customer_info['id']}")
                st.write(f"Customer type: {customer_info['major']}")
                st.write(f"Tier: {customer_info['year']}")
                st.write(f"First visit: {customer_info['starting_year']}")
                st.write(f"Total check-ins: {customer_info['total_attendance']}")
                st.write(f"Status: {customer_info['standing']}")
                st.write(f"Last check-in: {customer_info['last_attendance_time']}")

                st.divider()

                col_btn1, col_btn2, col_btn3 = st.columns(3)
                with col_btn2:
                    if st.button("Check in", use_container_width=True):
                        success, msg = update_attendance_record(conn, customer_id)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)
            else:
                st.warning("Customer record not found")
        else:
            st.info("Waiting for a face...")

    time.sleep(0.05)
    st.rerun()


if __name__ == "__main__":
    main()
