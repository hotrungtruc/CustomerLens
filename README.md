# Face Recognition — Front Door AI (v1.4.0)

Hệ thống nhận diện khuôn mặt thời gian thực kết hợp giữa camera phía Client (Next.js) truyền tải qua WebSocket đến Backend (FastAPI) xử lý nhận diện bằng AI và lưu trữ đám mây (Supabase + pgvector).

<p align="center">
  <img src="assets/06.13_demo.png" alt="Front Door AI Demo" width="900">
</p>

---

## ⚡ Các Tính Năng Nổi Bật (v1.4.0)

- **WebSocket Streaming**: Thay thế HTTP polling bằng kết nối WebSocket thời gian thực (`/ws/{session_id}`), mang lại khung hình mượt mà **~10 FPS**.
- **Cô Lập Phiên (Session Isolation)**: Nhận dạng và hiển thị bounding box riêng biệt cho từng tab trình duyệt/camera khác nhau dựa trên `session_id`.
- **Supabase Cloud Migration**: 
  - Hỗ trợ lưu trữ thông tin khách hàng và nhật ký ra vào trên đám mây PostgreSQL.
  - Tích hợp **pgvector** và chỉ mục **HNSW** (Approximate Nearest Neighbors) cho phép so khớp vector khuôn mặt siêu tốc (**~2ms**).
- **Quản Lý Ảnh Đám Mây**: Đồng bộ ảnh chân dung khách hàng lên **Supabase Storage** qua REST API, giảm tải cho ổ đĩa máy chủ.
- **Tối Ưu Hóa Hiệu Năng (Prefetch Strategy)**:
  - **Track Lifecycle Cache**: Lưu thông tin khách hàng theo vòng đời track, chỉ truy vấn Database 1 lần duy nhất khi khuôn mặt xuất hiện.
  - **Active Prefetching**: Frontend tự động tải trước (prefetch) chi tiết hồ sơ khi phát hiện khuôn mặt để hiển thị tức thì (0ms) khi admin nhấn vào.
- **Hệ Thống Auth & Phân Quyền (RBAC)**:
  - Trang Login kính mờ (glassmorphism) bảo mật.
  - 3 vai trò: **Guest** (chỉ xem Dashboard tổng quan), **Moderator** (xem camera được phân quyền), và **Admin** (toàn quyền quản lý).
- **Production Hardening**: Tích hợp Connection Pooling (`ThreadedConnectionPool`) và Module Logging có cấu trúc để quản lý tài nguyên hiệu quả khi deploy.

---

## 🛠️ Công Nghệ Sử Dụng

- **Frontend**: Next.js 14 (App Router) + Tailwind CSS + MediaPipe Face Mesh (vẽ canvas client-side)
- **Backend**: FastAPI + Uvicorn + ONNX Runtime (CPU)
- **AI Models**: GhostFaceNet (trích xuất vector đặc trưng 512-D) + MediaPipe Face Detector
- **Database & Storage**: Supabase (PostgreSQL + pgvector) + Supabase Bucket Storage

---

## 🚀 Hướng Dẫn Chạy Dưới Local

Yêu cầu: **Python 3.10+** và **Node.js 18+**.

### 1. Cấu Hình Biến Môi Trường

Tạo file `backend/.env`:
```env
USE_SUPABASE=true
SUPABASE_URL=postgresql://postgres:PASSWORD@db.qgwpntwmxpwffccptotj.supabase.co:6543/postgres
SUPABASE_PROJECT_URL=https://qgwpntwmxpwffccptotj.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
```

Tạo file `frontend/.env.local`:
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 2. Cài Đặt & Chạy Backend

Khởi tạo môi trường ảo và cài đặt thư viện:
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Khởi chạy cơ sở dữ liệu và tải model (chỉ cần chạy lần đầu):
```powershell
# Tạo schema database
python -m app.db.connection

# Tải model AI về thư mục models/
python -m app.utils.download_models

# Đồng bộ vector cũ từ Bytea sang pgvector (nếu có)
python scripts/backfill_vectors.py

# Upload hàng loạt ảnh local lên Supabase Storage (nếu có)
python scripts/migrate_images.py
```

Khởi chạy server FastAPI:
```powershell
python run.py
```
Backend sẽ lắng nghe tại `http://localhost:8000`.

### 3. Cài Đặt & Chạy Frontend

```bash
cd frontend
npm install
npm run dev
```
Truy cập ứng dụng tại `http://localhost:3000`.

---

## 🐳 Triển Khai Trên Máy Chủ EC2 (Docker Compose)

Hệ thống đã được đóng gói sẵn để deploy lên EC2 thông qua Docker Compose và Nginx làm Reverse Proxy.

### Chạy Thủ Công Trên Server:
```bash
# Clone repo
git clone <url_gitlab>
cd face-recognition-system

# Thiết lập file .env chứa thông tin Supabase ở thư mục gốc

# Build và chạy ngầm bằng Docker Compose
sudo docker compose up --build -d
```

### Triển Khai Tự Động (CI/CD):
Dự án tích hợp sẵn `.gitlab-ci.yml`. Khi bạn merge code vào nhánh `main`, GitLab CI/CD sẽ tự động kết nối SSH vào EC2, cập nhật code mới, ghi đè biến môi trường bảo mật, và rebuild lại container Docker mà không gây downtime.

---

## 📊 Cấu Trúc Cơ Sở Dữ Liệu Supabase

- **Bảng `customers`**: Lưu thông tin cơ bản (`id`, `name`, `phone`, `note`, `visit_count`, `last_visit`).
- **Bảng `customer_embeddings`**: Lưu vector đặc trưng (`customer_id`, `embedding vector(512)`).
- **Bảng `attendance`**: Lưu nhật ký ra vào (`id`, `customer_id`, `timestamp`, `visit_date`).
- **Bảng `users`**: Quản lý tài khoản đăng nhập và phân quyền (`username`, `password_hash`, `role`).
