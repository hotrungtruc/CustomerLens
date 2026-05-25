import streamlit as st
import cv2
import numpy as np
import sqlite3
import os
from datetime import datetime
import pickle
import time
from insight_embedding import InsightEmbedder, SIMILARITY_THRESHOLD, cosine_similarities

# Page config
st.set_page_config(
    page_title="Face Recognition System",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_resource
def load_models():
    """Load face embedder and encodings"""
    embedder = InsightEmbedder()
    with open("EncodeFile.p", "rb") as f:
        encodeListKnownWithIds = pickle.load(f)
    encodeListKnown, studentIds = encodeListKnownWithIds
    return embedder, encodeListKnown, studentIds


@st.cache_resource
def get_db_connection():
    """Connect to database"""
    conn = sqlite3.connect("face_attendance.db")
    conn.row_factory = sqlite3.Row
    return conn


def get_student_info(conn, student_id):
    """Get student information from database"""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, major, starting_year, total_attendance, standing, year, last_attendance_time
        FROM students WHERE id = ?
    """,
        (student_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def load_student_image(student_id):
    """Load student image from Images folder"""
    for ext in (".png", ".jpg", ".jpeg"):
        path = os.path.join("Images", f"{student_id}{ext}")
        if os.path.exists(path):
            return cv2.imread(path)
    return None


def update_attendance(conn, student_id):
    """Update attendance record"""
    student_info = get_student_info(conn, student_id)
    if not student_info:
        return False, "❌ Không tìm thấy thông tin sinh viên"

    try:
        last_time = datetime.strptime(
            student_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError):
        last_time = datetime.min

    seconds_elapsed = (datetime.now() - last_time).total_seconds()

    if seconds_elapsed > 30:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE students SET total_attendance = ?, last_attendance_time = ? WHERE id = ?",
            (
                student_info["total_attendance"] + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                student_id,
            ),
        )
        conn.commit()
        return True, "✅ Điểm danh thành công!"
    else:
        remaining = int(30 - seconds_elapsed)
        return False, f"⏳ Vui lòng chờ {remaining}s"


def main():
    st.title("🎓 Hệ thống Nhận Diện Khuôn Mặt")

    try:
        embedder, encodeListKnown, studentIds = load_models()
        conn = get_db_connection()
    except Exception as e:
        st.error(f"❌ Lỗi: {str(e)}")
        return

    # Initialize camera in session state
    if "cap" not in st.session_state:
        st.session_state.cap = cv2.VideoCapture(0)
        st.session_state.cap.set(3, 640)
        st.session_state.cap.set(4, 480)
        st.session_state.detected_id = None
        st.session_state.frame_count = 0

    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        st.subheader("📷 Camera")
        camera_placeholder = st.empty()

        ret, frame = st.session_state.cap.read()

        if ret:
            frame_display = frame.copy()

            # Process every 3rd frame to speed up
            st.session_state.frame_count += 1
            if st.session_state.frame_count % 3 == 0:
                faces = embedder.get_faces(frame)
                if faces:
                    for face in faces:
                        similarities = cosine_similarities(
                            encodeListKnown, face["embedding"]
                        )
                        if len(similarities) > 0:
                            matchIndex = np.argmax(similarities)
                            if similarities[matchIndex] >= SIMILARITY_THRESHOLD:
                                st.session_state.detected_id = studentIds[matchIndex]
                                x1, y1, x2, y2 = face["bbox"]
                                cv2.rectangle(
                                    frame_display, (x1, y1), (x2, y2), (0, 255, 0), 2
                                )
                                cv2.putText(
                                    frame_display,
                                    str(st.session_state.detected_id),
                                    (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.7,
                                    (0, 255, 0),
                                    2,
                                )
                else:
                    st.session_state.detected_id = None

            frame_rgb = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)
            camera_placeholder.image(frame_rgb, width=640)
        else:
            st.error("❌ Không thể truy cập camera")

    with col2:
        st.subheader("👤 Thông Tin Người Dùng")

        if st.session_state.detected_id:
            student_id = st.session_state.detected_id
            student_info = get_student_info(conn, student_id)

            if student_info:
                # Display image
                student_img = load_student_image(student_id)
                if student_img is not None:
                    student_img_rgb = cv2.cvtColor(student_img, cv2.COLOR_BGR2RGB)
                    st.image(student_img_rgb, width=300, caption=f"ID: {student_id}")
                else:
                    st.info("📸 Không có ảnh")

                st.divider()

                # Display info
                st.markdown("### Thông Tin Chi Tiết")
                st.write(f"**Họ tên:** {student_info['name']}")
                st.write(f"**Mã SV:** {student_info['id']}")
                st.write(f"**Ngành:** {student_info['major']}")
                st.write(f"**Khóa:** {student_info['year']}")
                st.write(f"**Năm bắt đầu:** {student_info['starting_year']}")
                st.write(f"**Tổng điểm danh:** {student_info['total_attendance']}")
                st.write(f"**Xếp loại:** {student_info['standing']}")
                st.write(f"**Lần cuối:** {student_info['last_attendance_time']}")

                st.divider()

                # Attendance button
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                with col_btn2:
                    if st.button("✓ Điểm Danh", use_container_width=True):
                        success, msg = update_attendance(conn, student_id)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)
            else:
                st.warning("⚠️ Không tìm thấy thông tin")
        else:
            st.info("👀 Chờ phát hiện khuôn mặt...")

    # Gentle auto-refresh
    time.sleep(0.05)
    st.rerun()


if __name__ == "__main__":
    main()
