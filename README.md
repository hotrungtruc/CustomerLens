# Front Door AI — Real-time Face Recognition System

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Next.js](https://img.shields.io/badge/next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)
![OpenCV](https://img.shields.io/badge/opencv-%23white.svg?style=for-the-badge&logo=opencv&logoColor=white)

**Front Door AI** là hệ thống nhận diện khuôn mặt theo thời gian thực (Real-time Face Recognition) được thiết kế cho việc quản lý khách hàng tại cửa hàng và sự kiện. Hệ thống sử dụng kiến trúc phân tán với Frontend (Next.js) truyền tải khung hình qua **WebSocket**, Backend (FastAPI) phân phối tác vụ thông qua **Redis Pub/Sub**, Worker AI xử lý nhận diện (EdgeFace ONNX) độc lập, và lưu trữ vector đặc trưng trên **Supabase PostgreSQL (pgvector)**.

<p align="center">
  <img src="assets/06.13_demo.png" alt="Front Door AI Demo" width="900" style="border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
</p>

---

## Tính Năng & Kiến Trúc (Key Features & Architecture)

### Trí Tuệ Nhân Tạo & Thị Giác Máy Tính (AI & CV)
- **Face Detection & Recognition:** Sử dụng **MediaPipe Tasks API** để phát hiện khuôn mặt và **EdgeFace (ONNX)** để trích xuất embedding 512 chiều, đảm bảo độ chính xác cao và tối ưu trên CPU.
- **Multi-frame Voting & Lazy Embedding:** Hệ thống tự động chọn các khung hình đạt chuẩn (kích thước, độ sắc nét) để tiến hành trích xuất vector.
- **Kalman Filter Tracking:** Áp dụng thuật toán theo dõi (tracking) nhằm liên kết định danh khách hàng ổn định giữa các khung hình liên tiếp.

### Kiến Trúc Phân Tán (Distributed Architecture)
- **API Gateway (FastAPI) & WebSockets:** Nhận luồng video từ client thông qua WebSocket và gửi kết quả tracking ngược lại với độ trễ thấp.
- **Stateless AI Workers:** Các tiến trình AI chạy hoàn toàn độc lập, giao tiếp với API Server thông qua **Redis Pub/Sub**. Điều này cho phép dễ dàng mở rộng (horizontal scaling) lên nhiều Worker Nodes.
- **Asynchronous Processing:** Tách biệt luồng nhận diện AI và luồng cập nhật cơ sở dữ liệu để tối đa hóa Frame Per Second (FPS) cho client.

### Cloud & Database (Supabase)
- **pgvector & HNSW Index:** Lưu trữ và tìm kiếm độ tương đồng khuôn mặt (Cosine Similarity) bằng thuật toán Approximate Nearest Neighbor (HNSW) tích hợp sẵn trong PostgreSQL.
- **Data Caching:** Thông tin chi tiết của khách hàng được query 1 lần và cache trong bộ nhớ (Track Lifecycle Cache), giảm tải đáng kể cho database.

---

## Công Nghệ Sử Dụng (Tech Stack)

| Phân hệ | Công nghệ |
| :--- | :--- |
| **Frontend** | Next.js 14 (App Router), React, Tailwind CSS |
| **Backend API** | FastAPI, Uvicorn, Python 3.12+, WebSockets, asyncio |
| **Message Broker** | Redis (Pub/Sub) |
| **AI Workers** | ONNX Runtime (CPU), EdgeFace (`edgeface_s_gamma_05.onnx`), MediaPipe, OpenCV |
| **Database** | PostgreSQL, Supabase, pgvector |
| **Deployment**| Docker, Docker Compose, GitLab CI/CD, AWS EC2 |

---

## Hướng Dẫn Cài Đặt Dưới Local (Local Development)

Yêu cầu hệ thống: **Python 3.12+**, **Node.js 18+**, và **Docker** (để chạy Redis nội bộ).

### 1. Khởi động Redis
```bash
docker run -d --name faceai-redis -p 6379:6379 redis:alpine
```

### 2. Cấu Hình Biến Môi Trường (.env)
Tại thư mục `backend/`, tạo file `.env` (hoặc copy từ `.env_example`) và thiết lập các biến sau:
```env
USE_SUPABASE=true
SUPABASE_URL="postgresql://postgres.[YOUR_PROJECT_ID]:[YOUR_PASSWORD]@[REGION].pooler.supabase.com:6543/postgres"
REDIS_URL="redis://localhost:6379/0"
```

Tại thư mục `frontend/`, tạo file `.env.local`:
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 3. Cài Đặt & Chạy Backend
Mở 2 Terminal riêng biệt cho Backend API và AI Worker.

**Terminal 1 (Backend API):**
```bash
cd backend
python -m venv .venv
# Kích hoạt môi trường (Windows: .\.venv\Scripts\activate, Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python run.py
```

**Terminal 2 (AI Worker):**
```bash
cd backend
# Kích hoạt môi trường tương tự như trên
python app/ai_worker.py
```

### 4. Cài Đặt & Chạy Frontend
**Terminal 3:**
```bash
cd frontend
npm install
npm run dev
```
Truy cập ứng dụng tại `http://localhost:3000`.

---

## Triển Khai Máy Chủ (Production Deployment)

Hệ thống được đóng gói bằng Docker Compose, hỗ trợ phân tách Master Node (API) và Worker Nodes (AI).

### Chạy bằng Docker Compose (Single Node)
```bash
git clone <url_gitlab>
cd face-recognition-system
# Thiết lập file backend/.env chứa SUPABASE_URL và REDIS_URL=redis://redis:6379/0
sudo docker compose build backend ai_worker
sudo docker compose up -d
```

### Triển khai tự động (CI/CD)
Dự án sử dụng **GitLab CI/CD**. Quá trình triển khai lên môi trường Production (AWS EC2) được thực hiện tự động qua phương thức SSH mỗi khi mã nguồn được hợp nhất vào nhánh `main`.

---

## Tài Liệu Kỹ Thuật (Documentation)

Chi tiết kỹ thuật được ghi chép trong thư mục `docs/`:

1. **[Kiến trúc Hệ thống (System Architecture)](docs/system_architecture.md)**: Sơ đồ luồng dữ liệu, tương tác giữa API, Redis và AI Worker.
2. **[Luồng Xử lý AI & Tracking (AI Pipeline)](docs/ai_pipeline.md)**: Chi tiết giải thuật Multi-frame Voting, phân tích tiến trình trích xuất embedding.
3. **[Cấu trúc Cơ sở Dữ liệu (Database Schema)](docs/database_schema.md)**: Thiết kế PostgreSQL, chỉ mục HNSW và tích hợp Supabase.
4. **[Kiến trúc Frontend (Frontend Architecture)](docs/frontend_architecture.md)**: Cấu trúc thư mục Next.js và nguyên lý thiết kế UI/UX.
5. **[Tài liệu API & WebSocket (API Reference)](docs/api_reference.md)**: Các Endpoints hỗ trợ và giao thức truyền tải WebSocket.
6. **[Hướng dẫn Vận hành (Maintenance Guide)](docs/maintenance_guide.md)**: Troubleshooting, cách cấu hình Docker Compose và quản lý tài nguyên hệ thống.