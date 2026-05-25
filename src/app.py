"""Face Recognition Attendance System - Flask Backend
Efficient video streaming with face detection and attendance tracking
"""

from flask import Flask, render_template, jsonify, request
import cv2
import numpy as np
import sqlite3
import os
import sys
import pickle
import base64
from datetime import datetime

# ✅ Add src to path so we can import local modules
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from insight_embedding import InsightEmbedder, SIMILARITY_THRESHOLD, cosine_similarities

# ✅ FIX: Get the project root directory using absolute path
# Use os.path.dirname twice to go from src/app.py -> src -> root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Double-check and resolve to absolute path to handle edge cases
PROJECT_ROOT = os.path.normpath(os.path.abspath(PROJECT_ROOT))

# ✅ Set working directory to project root to ensure all relative paths work correctly
os.chdir(PROJECT_ROOT)

# ✅ Set correct template and static folder paths using absolute paths
template_dir = os.path.join(PROJECT_ROOT, "templates")
static_dir = os.path.join(PROJECT_ROOT, "assets")
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# ✅ Add logging middleware to debug requests
@app.before_request
def log_request():
    print(f"[REQUEST] {request.method} {request.path} from {request.remote_addr}")

# Global variables for face detection
embedder = None
encodeListKnown = None
studentIds = None
current_detected_id = None


def init_models():
    """Initialize AI models for face detection"""
    global embedder, encodeListKnown, studentIds
    try:
        # ✅ Use absolute path for EncodeFile.p
        encode_file_path = os.path.join(PROJECT_ROOT, "EncodeFile.p")
        embedder = InsightEmbedder()
        with open(encode_file_path, "rb") as f:
            encodeListKnownWithIds = pickle.load(f)
        encodeListKnown, studentIds = encodeListKnownWithIds
        print("✅ Models loaded successfully")
    except Exception as e:
        print(f"❌ Error loading models: {str(e)}")
        raise


def get_db_connection():
    """Create database connection with proper configuration"""
    try:
        # ✅ Use absolute path for database
        db_path = os.path.join(PROJECT_ROOT, "face_attendance.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {str(e)}")
        return None


def get_student_info(conn, student_id):
    """Retrieve student information from database"""
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, name, major, starting_year, total_attendance, 
                      standing, year, last_attendance_time 
               FROM students WHERE id = ?""",
            (student_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"❌ Database query error: {str(e)}")
        return None


def load_student_image(student_id):
    """Load and encode student image to base64"""
    try:
        for ext in (".png", ".jpg", ".jpeg"):
            # ✅ Use absolute path for Images directory
            path = os.path.join(PROJECT_ROOT, "Images", f"{student_id}{ext}")
            if os.path.exists(path):
                img = cv2.imread(path)
                if img is not None:
                    _, buffer = cv2.imencode(
                        ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85]
                    )
                    return base64.b64encode(buffer).decode()
        return None
    except Exception as e:
        print(f"❌ Image loading error: {str(e)}")
        return None


def camera_feed():
    """Generate MJPEG video stream with face detection"""
    global current_detected_id

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot access camera")
        return

    # Set camera properties
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer for fresh frames

    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            frame_display = frame.copy()

            # Process every 3rd frame for better performance
            if frame_count % 3 == 0:
                try:
                    faces = embedder.get_faces(frame)
                    if faces:
                        detected_face = False
                        for face in faces:
                            similarities = cosine_similarities(
                                encodeListKnown, face["embedding"]
                            )
                            if len(similarities) > 0:
                                matchIndex = np.argmax(similarities)
                                if similarities[matchIndex] >= SIMILARITY_THRESHOLD:
                                    current_detected_id = studentIds[matchIndex]
                                    detected_face = True

                                    # Draw bounding box
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
                                        str(current_detected_id),
                                        (x1, y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        1,
                                        (0, 255, 0),
                                        2,
                                    )
                        if not detected_face:
                            current_detected_id = None
                    else:
                        current_detected_id = None
                except Exception as e:
                    print(f"⚠️ Face detection error: {str(e)}")

            # Encode frame to JPEG
            ret, buffer = cv2.imencode(
                ".jpg", frame_display, [cv2.IMWRITE_JPEG_QUALITY, 80]
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


@app.route("/")
def index():
    """Serve main HTML page"""
    try:
        print("[DEBUG] Rendering index.html")
        html = render_template("index.html")
        print(f"[DEBUG] Successfully rendered template ({len(html)} bytes)")
        return html
    except Exception as e:
        print(f"[ERROR] Error in index route: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500


@app.route("/test")
def test():
    """Test route"""
    return {"status": "ok", "message": "Flask app is running"}


@app.route("/video_feed")
def video_feed():
    """Stream MJPEG video"""
    return app.response_class(
        camera_feed(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/student_info")
def api_student_info():
    """API endpoint to get current detected student info"""
    if not current_detected_id:
        return jsonify({"status": "no_detection"})

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database error"})

    try:
        student_info = get_student_info(conn, current_detected_id)

        if not student_info:
            return jsonify({"status": "not_found"})

        # Load student image
        img_base64 = load_student_image(current_detected_id)

        return jsonify(
            {
                "status": "success",
                "id": student_info["id"],
                "name": student_info["name"],
                "major": student_info["major"],
                "year": student_info["year"],
                "starting_year": student_info["starting_year"],
                "total_attendance": student_info["total_attendance"],
                "standing": student_info["standing"],
                "last_attendance_time": student_info["last_attendance_time"],
                "image": img_base64,
            }
        )
    finally:
        conn.close()


@app.route("/api/check_in", methods=["POST"])
def api_check_in():
    """API endpoint to mark attendance"""
    if not current_detected_id:
        return jsonify({"success": False, "message": "Không phát hiện khuôn mặt"})

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Lỗi kết nối database"})

    try:
        student_info = get_student_info(conn, current_detected_id)

        if not student_info:
            return jsonify({"success": False, "message": "Không tìm thấy sinh viên"})

        # Check last attendance time
        try:
            last_time = datetime.strptime(
                student_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            last_time = datetime.min

        seconds_elapsed = (datetime.now() - last_time).total_seconds()

        # Only allow check-in every 30 seconds
        if seconds_elapsed > 30:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE students 
                   SET total_attendance = ?, last_attendance_time = ? 
                   WHERE id = ?""",
                (
                    student_info["total_attendance"] + 1,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    current_detected_id,
                ),
            )
            conn.commit()
            return jsonify({"success": True, "message": "✅ Điểm danh thành công!"})
        else:
            remaining = int(30 - seconds_elapsed)
            return jsonify(
                {"success": False, "message": f"⏳ Vui lòng chờ {remaining}s"}
            )
    except Exception as e:
        print(f"❌ Check-in error: {str(e)}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        # ✅ Print debug information for troubleshooting (without emojis for Windows compatibility)
        print(f"[*] Project Root: {PROJECT_ROOT}")
        print(f"[*] Template Dir: {template_dir}")
        print(f"[*] Static Dir: {static_dir}")
        print(f"[*] Working Directory: {os.getcwd()}")
        print(f"[OK] Template exists: {os.path.exists(template_dir)}")
        print(f"[OK] EncodeFile exists: {os.path.exists(os.path.join(PROJECT_ROOT, 'EncodeFile.p'))}")
        print(f"[OK] Database exists: {os.path.exists(os.path.join(PROJECT_ROOT, 'face_attendance.db'))}")
        print(f"[OK] Images dir exists: {os.path.exists(os.path.join(PROJECT_ROOT, 'Images'))}")
        print()
        
        print("[DEBUG] Registered routes:")
        for rule in app.url_map.iter_rules():
            print(f"  {rule.rule} -> {rule.endpoint}")
        print()
        
        init_models()
        
        # ✅ Host Configuration:
        # - "127.0.0.1" (DEFAULT): Only local access on http://localhost:5000
        #   Recommended for development/testing
        # - "0.0.0.0": Network access from other machines
        #   Change this if you need to access from another computer
        
        host = "127.0.0.1"  # Change to "0.0.0.0" for network access
        port = 5000
        
        print(f"[*] Starting Flask app on http://{host}:{port}")
        if host == "127.0.0.1":
            print(f"[*] Access from this computer: http://localhost:{port}")
        else:
            print(f"[*] Network access enabled on http://0.0.0.0:{port}")
            print(f"[*] Find your IP: ipconfig | findstr IPv4")
        
        app.run(host=host, port=port, debug=False, threaded=True)
    except Exception as e:
        print(f"[ERROR] Failed to start app: {str(e)}")
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()
