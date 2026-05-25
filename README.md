# 🎓 Hệ thống Nhận Diện Khuôn Mặt & Điểm Danh

Real-time face recognition attendance system với Flask backend, MJPEG video streaming, và SQLite database.

![Demo](assets/demo_05_21.jpg)

## ✨ Tính Năng

- 📷 **Real-time Face Detection**: Phát hiện khuôn mặt liên tục với tốc độ 30 FPS
- 🎯 **Face Recognition**: So sánh embedding với cơ sở dữ liệu đã biết
- 💾 **Attendance Tracking**: Tự động cập nhật số lần điểm danh
- 🌐 **Web Interface**: Giao diện web responsive (camera bên trái, thông tin bên phải)
- ⚡ **Smooth Video**: MJPEG streaming không giật/lag
- 🔒 **Secure**: XSS protection, error handling toàn diện
- 📱 **Mobile Friendly**: Responsive design cho mọi kích thước màn hình

## 🏗️ Kiến Trúc Hệ Thống

```
┌─────────────────────────────────────────────┐
│         Web Browser (HTML/JS)              │
│  - Camera feed display (MJPEG)             │
│  - Student info polling (500ms interval)   │
│  - Check-in button with validation         │
└────────────────┬────────────────────────────┘
                 │ HTTP (fetch API)
┌────────────────▼────────────────────────────┐
│         Flask Backend (Python)              │
│  - /video_feed: MJPEG stream               │
│  - /api/student_info: Current detected    │
│  - /api/check_in: Mark attendance         │
└────────────────┬────────────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
┌────────┐  ┌────────┐  ┌──────────┐
│ Camera │  │ Models │  │ Database │
│ (USB)  │  │(ONNX)  │  │(SQLite)  │
└────────┘  └────────┘  └──────────┘
```

## 📋 Project Structure

```
Face Recognize/
├── src/
│   └── app.py                 # Flask backend (camera, detection, API)
├── templates/
│   └── index.html             # Web frontend (UI + JavaScript)
├── models/                    # ONNX model files
│   ├── det_500m.onnx         # SCRFD detection
│   ├── w600k_mbf.onnx        # ArcFace recognition
│   ├── 1k3d68.onnx
│   ├── 2d106det.onnx
│   └── genderage.onnx
├── Images/                    # Student photos (ID.jpg/png)
├── assets/
│   └── demo_05_21.jpg        # Demo screenshot
├── insight_embedding.py       # Face detector + embedder wrapper
├── EncodeFile.p              # Pre-computed face encodings cache
├── EncodeGenerator.py        # Generate encodings from Images/
├── AddDatatoDatabase.py      # Seed database with students
├── face_attendance.db        # SQLite database
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## ⚙️ Yêu Cầu

- **Python**: 3.9+ (khuyến nghị 3.10+)
- **Webcam**: USB hoặc tích hợp
- **GPU** (tùy chọn): NVIDIA GPU + CUDA 12.x + cuDNN 9.x
- **RAM**: 4GB+ (GPU: 6GB+)

## 🚀 Cài Đặt

### 1. Clone & Setup Environment

```bash
# Tạo virtual environment
python -m venv .venv

# Kích hoạt (Windows)
.\.venv\Scripts\activate

# Hoặc kích hoạt (Linux/macOS)
source .venv/bin/activate
```

### 2. Cài Đặt Dependencies

```bash
pip install -r requirements.txt
```

**Cấu hình GPU** (tùy chọn):
```bash
# Với GPU NVIDIA
pip install onnxruntime-gpu

# Hoặc giữ CPU mode (onnxruntime đã trong requirements.txt)
```

````md
### 📥 Tải Pretrained Models

Các file ONNX models không được đưa lên repository do kích thước lớn.

Chạy lệnh sau để tự động tải toàn bộ models cần thiết:

```bash
python src\download_models.py
```

Script này sẽ tự động tải các models vào thư mục:

```text
models/
├── det_500m.onnx         # SCRFD detection
├── w600k_mbf.onnx        # ArcFace recognition
├── 1k3d68.onnx
├── 2d106det.onnx
└── genderage.onnx
```

````

### 3. Chuẩn Bị Dữ Liệu

```bash
# Seed database với dữ liệu mẫu
python src\AddDatatoDatabase.py

# Sinh encoding cho ảnh trong Images/
python src\EncodeGenerator.py
```

## 🎮 Sử Dụng

### Khởi Động Ứng Dụng

```bash
cd src
python src\app.py
```

**Output:**
```
✅ Models loaded successfully
🚀 Starting Flask app on http://0.0.0.0:5000
```

### Truy Cập Web Interface

- **Local**: http://localhost:5000
- **Network**: http://192.168.100.226:5000 (hoặc IP của máy)

### Quy Trình Điểm Danh

1. **Phát hiện khuôn mặt**: Camera phát hiện người và so sánh embedding
2. **Hiển thị thông tin**: Khi khớp (≥0.38 similarity), hiển thị ảnh + thông tin sinh viên
3. **Điểm danh**: Nhấn nút "✓ Điểm Danh"
4. **Cooldown**: 30 giây trước khi có thể điểm danh lại

## 📊 API Endpoints

### `GET /`
Trả về trang HTML chính

### `GET /video_feed`
MJPEG video stream từ camera
```
Content-Type: multipart/x-mixed-replace; boundary=frame
```

### `GET /api/student_info`
Lấy thông tin sinh viên hiện tại
```json
{
  "status": "success|no_detection|not_found|error",
  "id": "003",
  "name": "Hồ Trung Trực",
  "major": "Computer Science",
  "year": "2",
  "starting_year": "2023",
  "total_attendance": 15,
  "standing": "G",
  "last_attendance_time": "2026-05-21 21:30:42",
  "image": "base64_encoded_jpeg"
}
```

### `POST /api/check_in`
Đánh dấu điểm danh cho sinh viên hiện tại
```json
{
  "success": true|false,
  "message": "✅ Điểm danh thành công! | ⏳ Vui lòng chờ Xs"
}
```

## 🔧 Cấu Hình

### Thay Đổi Port

Trong `src/app.py`:
```python
app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
```

### Điều Chỉnh Face Detection

Trong `src/app.py`:
```python
# Xử lý mỗi frame thứ N (hiện tại = 3)
if frame_count % 3 == 0:

# Ngưỡng similarity (mặc định = 0.38)
# Thay đổi trong insight_embedding.py: SIMILARITY_THRESHOLD
```

### Cooldown Điểm Danh

Trong `src/app.py`:
```python
if seconds_elapsed > 30:  # Thay 30 thành giá trị mong muốn
```

## 📸 Chuẩn Bị Ảnh Sinh Viên

1. **Đặt ảnh vào**: `Images/` folder
2. **Tên file**: `{student_id}.jpg` hoặc `.png`
   - Ví dụ: `003.jpg`, `12345.png`
3. **Kích thước**: 300x300px trở lên, ảnh chân dung rõ ràng
4. **Định dạng**: JPG, PNG, hoặc JPEG

```bash
Images/
├── 001.jpg
├── 002.jpg
├── 003.jpg
└── ...
```

## 🐛 Troubleshooting

### Camera không hoạt động
```
❌ Cannot access camera
```
**Giải pháp**:
- Kiểm tra camera được kết nối
- Đóng các ứng dụng khác dùng camera
- Cấp quyền truy cập camera cho Python

### Model load lỗi
```
❌ Error loading models
```
**Giải pháp**:
- Kiểm tra `models/` có tất cả `.onnx` files
- Cập nhật ONNX Runtime: `pip install --upgrade onnxruntime`

### Database error
```
❌ Database connection error
```
**Giải pháp**:
- Chạy `python AddDatatoDatabase.py` để tạo database
- Xóa `face_attendance.db` cũ và chạy lại

### Video giật/lag
**Giải pháp**:
- Giảm độ phân giải camera trong app.py
- Tăng `frame_count % N` (xử lý ít frames hơn)
- Sử dụng GPU acceleration

## 📦 Dependencies

| Package | Phiên Bản | Mục Đích |
|---------|-----------|---------|
| Flask | latest | Web framework |
| opencv-python | latest | Camera & image processing |
| numpy | latest | Numerical computation |
| onnxruntime | latest | Model inference |
| sqlite3 | built-in | Database |

Chi tiết xem `requirements.txt`

## 🔐 Bảo Mật

- ✅ XSS protection: HTML sanitization trên frontend
- ✅ Error handling: Comprehensive try-catch blocks
- ✅ Resource cleanup: Camera release, DB connection close
- ✅ Input validation: Response checking, error messages

## 📝 License

Academic Project - Dùng cho mục đích học tập

## 👨‍💻 Author

Student ID: 003 (Hồ Trung Trực)
Course: HK253 - Face Recognition

2. Generate encodings:

```bash
python src\EncodeGenerator.py
```

This creates EncodeFile.p for local use.

3. Run the app:

```bash
python src\Main.py
```

4. Run the Streamlit web dashboard:

```bash
streamlit run streamlit_app.py
```

The dashboard shows images from Images/ and student info from SQLite.

## How It Works

- EncodeGenerator.py reads Images/, detects faces with SCRFD, creates 512D ArcFace embeddings, and saves EncodeFile.p.
- Main.py reads EncodeFile.p, detects faces with SCRFD, extracts InsightFace embeddings, matches by cosine similarity, loads student data from SQLite, and updates attendance (with a 30s cooldown).

## Notes

- Each image file name must match the student ID in the database.
- If you add new students or images, re-run EncodeGenerator.py.
- The app uses a 640x480 webcam feed and overlays UI from Resources/.
- The ONNX runtime uses `CUDAExecutionProvider` only when CUDA/cuDNN DLLs are available in PATH; otherwise it falls back to CPU.

## Troubleshooting

- If ONNX providers show only `CPUExecutionProvider`, install CUDA 12.x and cuDNN 9.x, then make sure their DLL folders are in PATH.
- If a student photo does not appear, confirm the file exists in Images/ and matches the student ID.
