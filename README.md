# 🚀 CustomerLens — Real-Time Enterprise Face Recognition & Guest Intelligence System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-005571?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-14.2-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js">
  <img src="https://img.shields.io/badge/React-18.3-20232a?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React">
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase">
  <img src="https://img.shields.io/badge/pgvector-HNSW-4169e1?style=for-the-badge&logo=postgresql&logoColor=white" alt="pgvector">
  <img src="https://img.shields.io/badge/Redis-Pub%2FSub-DD0031?style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/Redpanda-Kafka-FF4500?style=for-the-badge&logo=redpanda&logoColor=white" alt="Redpanda">
  <img src="https://img.shields.io/badge/ONNX_Runtime-CPU%2FGPU-00599C?style=for-the-badge&logo=onnx&logoColor=white" alt="ONNX Runtime">
  <img src="https://img.shields.io/badge/Security-RS256_JWT_|_AES--256--GCM-red?style=for-the-badge&logo=jsonwebtokens&logoColor=white" alt="Security">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
</p>

**CustomerLens** là một hệ thống **Nhận diện Khuôn mặt Thời gian thực & Phân tích Khách hàng (Real-time Face Recognition & Guest Intelligence Platform)** chuẩn Enterprise, được thiết kế theo kiến trúc sự kiện phân tán (Distributed Event-Driven Architecture) với khả năng mở rộng ngang (Horizontal Scaling) vượt trội.

Hệ thống cho phép giám sát luồng video camera trực tiếp với độ trễ siêu thấp (Sub-100ms End-to-End Latency), nhận diện khách hàng (VIP / Khách quen / Khách vãng lai), theo dõi tọa độ di chuyển đa mục tiêu (Multi-object Kalman Tracking), đồng thời tuân thủ nghiêm ngặt các tiêu chuẩn **An ninh & Bảo mật Sinh trắc học Quốc tế (GDPR Article 9 & 17, BIPA)**.

---

<p align="center">
  <img src="assets/06.13_demo.png" alt="CustomerLens Live Monitoring Demo" width="900" style="border-radius: 10px; box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);">
</p>

---

## 🌟 Tính Năng Nổi Bật (Key Features)

### 🧠 1. Thị Giác Máy Tính & Trí Tuệ Nhân Tạo (AI & CV Pipeline)
* **High-Precision Face Detection & Alignment:** Kết hợp **MediaPipe Tasks API** ở luồng Edge và **SCRFD 500M** trên AI Worker để phát hiện và căn chỉnh 5 mốc khuôn mặt (Landmarks) với độ chính xác tuyệt đối ngay cả khi quay nghiêng.
* **Compact Feature Extraction:** Trích xuất vector đặc trưng 512 chiều bằng mô hình **EdgeFace ONNX** (`edgeface_s_gamma_05.onnx` / `adaface_ir18.onnx`), tối ưu hóa cho cả CPU và GPU Acceleration.
* **Kalman Filter & IoU Tracking:** Thuật toán lọc Kalman góc (`KalmanFilterCorner`) kết hợp thuật toán Hungarian (`scipy.optimize.linear_sum_assignment`) giúp duy trì ổn định vết di chuyển (`track_id`) giữa các khung hình liên tiếp.
* **Multi-frame Voting & Robust Centroid:** Gom nhóm vector nhiều khung hình liên tiếp, lọc nhiễu bằng ma trận Cosine chéo (`calculate_robust_mean_embedding`), loại bỏ triệt để hiện tượng nhận diện nhầm khi khuôn mặt bị che khuất hoặc nhòe chuyển động.

### ⚡ 2. Kiến Trúc Phân Tán & Chịu Tải Cao (High-Throughput Architecture)
* **Biên-Cloud Hybrid (Edge-Cloud Processing):** Trình duyệt / Edge Gateway thực hiện Blur Filtering & Edge Crop trước khi gửi qua WebSocket, giảm **>80%** dung lượng đường truyền mạng.
* **Event Sourcing với Redpanda / Kafka:** API Gateway tiếp nhận luồng khung hình nhị phân và đẩy vào Topic `camera_frames` của Redpanda.
* **Stateless Worker Nodes:** Các tiến trình AI Worker chạy hoàn toàn độc lập, kéo dữ liệu theo đợt (Batch Polling), tự động bỏ qua khung hình chậm trễ (`delay > 0.5s`), dễ dàng mở rộng thêm Pods/Containers tùy theo tải.
* **Real-time Pub/Sub Feedback:** Trả kết quả nhận diện và Bounding Box về WebSocket Client thông qua kênh Redis Pub/Sub phân lập theo `connection_id`.

### 🛡️ 3. An Ninh Sinh Trắc Học & Pháp Lý (Enterprise Biometric Security & GDPR)
* **Xác thực JWT Bất đối xứng (RS256 Stateless Auth):** Loại bỏ lưu trữ RAM nội bộ. Token đăng nhập được ký bằng RSA Private Key và xác thực ngầm định tức thì bằng RSA Public Key tại mọi node API & WebSocket Observer.
* **Cancelable Biometrics (Orthogonal Random Projection):** Áp dụng ma trận chiếu ngẫu nhiên trực giao $Q \in \mathbb{R}^{512 \times 512}$ ($Q^T Q = I$) để biến đổi vector embedding trước khi lưu DB. Bảo toàn **100% độ chính xác Cosine Similarity** ($\langle Q\vec{x}_1, Q\vec{x}_2 \rangle = \langle \vec{x}_1, \vec{x}_2 \rangle$), đồng thời ngăn chặn tuyệt đối nguy cơ đảo ngược tái tạo khuôn mặt gốc nếu CSDL bị rò rỉ.
* **Encryption at Rest (AES-256-GCM):** Mã hóa toàn bộ tập tin hình ảnh sinh trắc học trên đĩa cứng bằng thuật toán mã hóa xác thực AES-256-GCM với Nonce 12-byte ngẫu nhiên.
* **Quyền được Quên (GDPR Article 17 Purge):** Tiến trình tự động và REST API `POST /api/admin/purge_guests` giúp xoá sạch dữ liệu vết khách vãng lai (`GUEST_*`), embeddings, nhật ký và tệp đĩa quá hạn (mặc định 30 ngày).

### 🗄️ 4. Cơ Sở Dữ Liệu & Vector Search Engine
* **Native pgvector Binary Parameter Binding:** Tích hợp `pgvector.psycopg2` truyền thẳng mảng NumPy `ndarray` float32 dạng nhị phân sang PostgreSQL vector data type, loại bỏ 100% chi phí parse chuỗi SQL String trên CPU.
* **Sub-millisecond HNSW Index:** Tìm kiếm độ tương đồng vector theo chỉ mục **HNSW** (`halfvec_cosine_ops`) tích hợp sẵn trong PostgreSQL/Supabase.
* **L1 Redis Vector Cache:** Lưu bộ nhớ đệm vector nhận diện cho kết quả truy vấn dưới **<1ms**.

---

## 🛠️ Công Nghệ Sử Dụng (Tech Stack)

| Phân hệ | Công nghệ & Thư viện |
| :--- | :--- |
| **Frontend UI** | Next.js 14 (App Router), React 18, Tailwind CSS, Lucide Icons, Canvas API |
| **Backend API Gateway** | FastAPI, Uvicorn (ASGI), Python 3.12+, asyncio, WebSockets |
| **Authentication & Security** | PyJWT (RS256 RSA 2048-bit), Cryptography (AES-256-GCM) |
| **Message Broker** | Redpanda / Apache Kafka (Topic: `camera_frames`), Redis Pub/Sub |
| **AI Inference Cluster** | ONNX Runtime (CPU/CUDA), EdgeFace, MediaPipe Tasks, OpenCV, SciPy, NumPy |
| **Database & Vector Search** | PostgreSQL 16+, Supabase, pgvector (`pgvector-python` HNSW Index) |
| **DevOps & Infrastructure** | Docker, Docker Compose, GitLab CI/CD, AWS EC2, Nginx |

---

## 📐 Kiến Trúc Hệ Thống (System Architecture)

```mermaid
flowchart TD
    subgraph Client ["Client (Frontend - Next.js 14)"]
        Cam["Webcam / RTSP Camera"]
        EdgeAI["Edge MediaPipe & Blur Filter"]
        UI["Real-time Canvas & Dashboard UI"]
    end

    subgraph Gateway ["API Gateway (FastAPI)"]
        WS["WebSocket Server (/ws/stream)"]
        JWT["RS256 JWT Auth (Public Key)"]
        Routes["RESTful API Routes"]
    end

    subgraph Messaging ["Message Fabric"]
        Redpanda["Redpanda / Kafka (Topic: camera_frames)"]
        RedisPub["Redis Pub/Sub (Channel: worker_results)"]
    end

    subgraph AI_Cluster ["Stateless AI Worker Cluster"]
        Worker1["AI Worker 1 (EdgeFace + SCRFD ONNX)"]
        WorkerN["AI Worker N (Auto-scaled)"]
    end

    subgraph Storage ["Cloud Storage & Vector DB"]
        SupaDB[("Supabase PostgreSQL + pgvector (HNSW Index)")]
        L1Cache[("L1 Redis Vector & Profile Cache")]
    end

    Cam --> EdgeAI
    EdgeAI -->|1. Frame Stream via WS| WS
    WS <--> JWT
    WS -->|2. Push Binary Frame| Redpanda
    Redpanda -->|3. Batch Poll Frames| Worker1 & WorkerN
    Worker1 & WorkerN -->|4. Detect, Align & Extract 512D| Worker1 & WorkerN
    Worker1 & WorkerN -->|5. Publish Detection| RedisPub
    RedisPub -->|6. Receive Result| WS
    WS -->|7. Vector Cosine Search| L1Cache
    L1Cache -- Cache Miss --> SupaDB
    WS -->|8. Push Real-time Bounding Box & Identity| UI
```

---

## ⚡ Hướng Dẫn Cài Đặt & Khởi Chạy Nhanh

### 📋 Bước 1: Yêu cầu môi trường
* **Git**, **Python 3.12+**, **Node.js (v18+)**, **Docker Desktop**.

### 📦 Bước 2: Tải mã nguồn & Bật Redis
```bash
git clone https://github.com/hotrungtruc/CustomerLens.git
cd CustomerLens

# Chạy container Redis
docker run -d --name faceai-redis -p 6379:6379 redis:alpine
```

### ⚙️ Bước 3: Cấu hình Môi trường Backend
Vào thư mục `backend/`, tạo file `.env` (hoặc sao chép từ `.env_example`):
```env
USE_SUPABASE=true
SUPABASE_URL="postgresql://postgres:[PASSWORD]@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres"
REDIS_URL="redis://127.0.0.1:6379/0"
KAFKA_BOOTSTRAP_SERVERS="127.0.0.1:9092"
```

### 🚀 Bước 4: Khởi động AI Backend & Workers

**Terminal 1 (Khởi tạo & API Gateway):**
```bash
cd backend
python -m venv .venv

# Activate môi trường (Windows PowerShell):
.\.venv\Scripts\Activate.ps1
# Hoặc Mac/Linux: source .venv/bin/activate

# Cài đặt thư viện
pip install -r requirements.txt

# Khởi tạo DB & Tải Model AI
python -m app.db.connection
python -m app.utils.download_models
python app/db/seed_data.py

# Chạy API Server
python run.py
```

**Terminal 2 (Chạy AI Worker):**
```bash
cd backend
.\.venv\Scripts\Activate.ps1
python app/ai_worker.py
```

### 💻 Bước 5: Khởi động Frontend Dashboard

**Terminal 3 (Next.js App):**
```bash
cd frontend
npm install
npm run dev
```

Truy cập ứng dụng tại: **[http://localhost:3000](http://localhost:3000)**  
* **Tài khoản mặc định:** `admin`  
* **Mật khẩu mặc định:** `change_me_immediately`

---

## 🐳 Triển Khai Container bằng Docker Compose

Để đóng gói và khởi chạy toàn bộ cụm dịch vụ (API, Worker, Redis, Redpanda) trên một nút máy chủ duy nhất:

```bash
docker compose build
docker compose up -d
```

---

## 📊 Kết Quả Benchmark Hệ Thống (Performance Evaluation)

Đo đạc trên bộ dữ liệu chuẩn **Asian Celeb Benchmark**:

| Chỉ số / Công đoạn | Giá trị Đo đạc thực tế |
| :--- | :--- |
| **Trích xuất Đặc trưng Single Image (EdgeFace)** | Latency trung bình: **`48.16 ms`** (~**`20.76 FPS`**) |
| **SCRFD Face Detection (Khung hình 720p)** | Latency trung bình: **`30.45 ms`** (~**`32.84 FPS`**) |
| **Supabase pgvector HNSW Vector Search** | Latency trung bình: **`265.17 ms`** (P50: `263.97 ms`) |
| **Độ chính xác Định danh (Rank-1 Accuracy)** | **`98.5%`** (trên 1,000 người ngẫu nhiên) |
| **Tỉ lệ Lỗi Bằng (Equal Error Rate - EER)** | **`0.82%`** tại ngưỡng Cosine Similarity $\theta^* = 0.322$ |
| **Test Suite Tự động (Unittest)** | **`17 / 17 Tests PASS (100% OK)`** |

---

## 📚 Tài Liệu Kỹ Thuật Chi Tiết (Documentation)

Chi tiết kỹ thuật nâng cao được lưu trữ tại thư mục [docs/](docs/):

1. 📖 **[Kiến trúc Hệ thống (docs/system_architecture.md)](docs/system_architecture.md)**: Sơ đồ luồng dữ liệu, tương tác Event-Driven Redpanda & Redis.
2. 📖 **[Luồng Xử lý AI & Tracking (docs/ai_pipeline.md)](docs/ai_pipeline.md)**: Giải thuật Kalman Filter, Multi-frame Voting & Dynamic Centroid.
3. 📖 **[Cấu trúc Cơ sở Dữ liệu (docs/database_schema.md)](docs/database_schema.md)**: PostgreSQL, chỉ mục HNSW và tích hợp Supabase.
4. 📖 **[Kiến trúc Frontend (docs/frontend_architecture.md)](docs/frontend_architecture.md)**: Cấu trúc thư mục Next.js 14 và Canvas UI Rendering.
5. 📖 **[Tài liệu API & WebSocket (docs/api_reference.md)](docs/api_reference.md)**: Danh sách Endpoints RESTful và giao thức WebSocket Subprotocol.
6. 📖 **[Thành phần Cốt lõi (docs/core_components_detail.md)](docs/core_components_detail.md)**: Chi tiết RS256 JWT, Native pgvector Parameter Binding và AES-256-GCM.
7. 📖 **[Báo cáo Benchmark (backend/test_system/benchmark_report.md)](backend/test_system/benchmark_report.md)**: Báo cáo đánh giá AI học thuật chi tiết.

---

## 📄 Giấy Phép & Đóng Góp (License & Contribution)

Dự án được phát triển cho mục đích nghiên cứu học thuật và thương mại hóa. Mọi đóng góp (Pull Request) hoặc báo lỗi (Issue) đều được chào đón!

* **Tác giả:** Hồ Trung Trực
* **Email:** hotrungtruc1706@gmail.com
* **GitHub Repository:** [CustomerLens](https://github.com/hotrungtruc/CustomerLens)