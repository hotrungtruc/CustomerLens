# 🚀 Front Door AI — Real-time Face Recognition System

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Next.js](https://img.shields.io/badge/next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)
![OpenCV](https://img.shields.io/badge/opencv-%23white.svg?style=for-the-badge&logo=opencv&logoColor=white)

**Front Door AI** là một hệ thống nhận diện khuôn mặt theo thời gian thực (Real-time Face Recognition) mạnh mẽ, được thiết kế cho các doanh nghiệp, cửa hàng, hoặc sự kiện. Hệ thống kết hợp giữa Frontend mượt mà (Next.js) truyền tải khung hình qua **WebSocket** đến Backend (FastAPI) xử lý bằng AI (GhostFaceNet) và lưu trữ vector đặc trưng trên đám mây bằng **Supabase + pgvector**.

<p align="center">
  <img src="assets/06.13_demo.png" alt="Front Door AI Demo" width="900" style="border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
</p>

---

## Tính Năng Nổi Bật (Key Features)

### Trí Tuệ Nhân Tạo & Thị Giác Máy Tính (AI & CV)
- **Multi-frame Voting & Lazy Embedding:** Tối ưu hóa việc trích xuất vector khuôn mặt. Hệ thống tự động chọn ra những khung hình có chất lượng cao nhất để đưa vào nhận diện.
- **Kalman Filter Tracking:** Theo dõi (track) khách hàng liên tục giữa các khung hình, chống nhiễu và mất dấu (flickering).

### Kiến Trúc Thời Gian Thực (Real-time Architecture)
- **WebSocket Streaming (`/ws/{session_id}`):** Loại bỏ độ trễ của HTTP Polling. Luồng video và dữ liệu bounding box được truyền tải 2 chiều liên tục với độ trễ tính bằng mili-giây.
- **Cô Lập Phiên (Session Isolation):** Hỗ trợ nhiều thiết bị/camera cùng kết nối. Mỗi thiết bị có một `session_id` riêng biệt, độc lập xử lý hình ảnh và dữ liệu.

### Cloud & Database (Supabase)
- **pgvector & HNSW Index:** Tìm kiếm độ tương đồng khuôn mặt (Cosine Similarity) với tốc độ siêu tốc (**~2ms**) ngay cả khi dữ liệu lên tới hàng chục nghìn khách hàng.
- **Connection Pooling (PgBouncer):** Xử lý hàng trăm luồng kết nối đồng thời từ AI Worker đến Database mà không gây cạn kiệt tài nguyên Server.

### Tối Ưu Hóa Trải Nghiệm (UX & Performance)
- **Track Lifecycle Cache:** Truy vấn Database **duy nhất 1 lần** khi khuôn mặt xuất hiện. Các khung hình tiếp theo sẽ sử dụng cache trên RAM, giảm 99% tải cho Database.
- **Active Prefetching:** Tự động tải trước (prefetch) thông tin hồ sơ của khách. Khi nhân viên click vào để xem, dữ liệu hiển thị tức thì (**0ms**).
- **Glassmorphism UI:** Giao diện tối (Dark Mode) hiện đại, mượt mà và cực kỳ chuyên nghiệp.

### Bảo Mật & Phân Quyền (RBAC)
- 3 cấp độ phân quyền rõ ràng: **Guest** (Khách - chỉ xem dashboard), **Moderator** (Nhân viên - được xem camera & thông tin), **Admin** (Quản lý - toàn quyền hệ thống).

---

## Công Nghệ Sử Dụng (Tech Stack)

| Phân hệ | Công nghệ |
| :--- | :--- |
| **Frontend** | Next.js 14 (App Router), React, Tailwind CSS, MediaPipe (Face Mesh Client-side) |
| **Backend** | FastAPI, Uvicorn, Python 3.10+, WebSockets, asyncio |
| **AI / ML** | ONNX Runtime (CPU), GhostFaceNet (512-D), OpenCV |
| **Database** | PostgreSQL, Supabase, pgvector |
| **Deployment**| Docker, Docker Compose, Nginx, GitLab CI/CD, AWS EC2 |

---

## Hướng Dẫn Cài Đặt Dưới Local (Local Development)

Yêu cầu hệ thống: **Python 3.10+** và **Node.js 18+**.

### 1. Cấu Hình Biến Môi Trường (.env)

Hệ thống đã chuẩn bị sẵn file mẫu. Tại thư mục `backend/`, hãy tạo file `.env` (hoặc copy từ `.env_example`) và cấu hình:

```env
# Đặt "true" để kết nối lên Supabase
USE_SUPABASE=true

# Chuỗi kết nối Database. Vui lòng lấy trong Supabase Dashboard (Port 6543)
SUPABASE_URL="postgresql://postgres.[YOUR_PROJECT_ID]:[YOUR_PASSWORD]@[REGION].pooler.supabase.com:6543/postgres?pgbouncer=true"
```

Tạo file `frontend/.env.local`:
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 2. Cài Đặt & Chạy Backend (FastAPI)

```powershell
# Di chuyển vào backend
cd backend

# Khởi tạo môi trường ảo (Virtual Environment)
python -m venv .venv
.\.venv\Scripts\activate

# Cài đặt thư viện
pip install -r requirements.txt
```

*(Chỉ chạy lần đầu tiên)*: Khởi tạo schema và tải Models
```powershell
python -m app.db.connection
python -m app.utils.download_models
```

Khởi chạy Server:
```powershell
python run.py
```
*Backend sẽ lắng nghe tại `http://localhost:8000`.*

### 3. Cài Đặt & Chạy Frontend (Next.js)

```bash
# Mở một terminal mới, di chuyển vào frontend
cd frontend

# Cài đặt thư viện
npm install

# Khởi chạy server phát triển
npm run dev
```
*Truy cập ứng dụng tại `http://localhost:3000`.*

---

## Triển Khai Lên Máy Chủ (Deployment - EC2/VPS)

Dự án đã được đóng gói tối ưu bằng Docker và cấu hình sẵn Nginx làm Reverse Proxy.

### Quản lý Biến Môi Trường (.env) Bảo Mật
Dự án cung cấp sẵn script `deploy_env.bat` (đã được cấu hình ẩn khỏi Git) để tự động hóa việc đưa file `.env` lên EC2 bằng phương thức SSH/SCP an toàn mà không làm rò rỉ mã bảo mật trên GitLab:
```bash
# Trên máy Local (Windows), click đúp vào file deploy_env.bat
# Hoặc chạy lệnh:
.\deploy_env.bat
```

### Chạy thủ công bằng Docker Compose:
```bash
git clone <url_gitlab>
cd face-recognition-system

# Chạy script deploy_env.bat từ máy Local để copy .env lên EC2 trước khi chạy lệnh bên dưới.

# Build và chạy ngầm
sudo docker compose up --build -d
```

### Triển khai tự động hóa (CI/CD):
Dự án được tích hợp luồng **GitLab CI/CD** (`.gitlab-ci.yml`). 
Mỗi khi có code mới được Push/Merge vào nhánh `main`, hệ thống CI/CD sẽ tự động:
1. Kết nối SSH vào máy chủ EC2.
2. Pull code mới nhất.
3. Cập nhật các biến bảo mật.
4. Rebuild Docker Container **không gây gián đoạn dịch vụ (Zero Downtime)**.

---

## Tài Liệu Kỹ Thuật (Documentation)

Dự án được tài liệu hóa cực kỳ chi tiết, chuẩn mực như một Production System. Mời bạn tham khảo trong thư mục `docs/`:

1. **[Kiến trúc Hệ thống (System Architecture)](docs/system_architecture.md)**: Kiến trúc High-level, luồng dữ liệu WebSocket.
2. **[Luồng Xử lý AI & Tracking (AI Pipeline)](docs/ai_pipeline.md)**: Chi tiết giải thuật Multi-frame Voting, Lazy Embedding.
3. **[Cấu trúc Cơ sở Dữ liệu (Database Schema)](docs/database_schema.md)**: Thiết kế PostgreSQL, chỉ mục HNSW.
4. **[Kiến trúc Frontend (Frontend Architecture)](docs/frontend_architecture.md)**: App Router, Prefetching, UI/UX.
5. **[Tài liệu API & WebSocket (API Reference)](docs/api_reference.md)**: Danh sách Endpoints.
6. **[Hướng dẫn Vận hành & Bảo trì (Maintenance Guide)](docs/maintenance_guide.md)**: Troubleshooting, CI/CD, Docker Resource Limits.

---

<p align="center">
  <i>Được thiết kế và phát triển với hiệu năng làm kim chỉ nam.</i>
</p>