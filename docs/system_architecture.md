# Kiến trúc Hệ thống (System Architecture)

Dự án Front Door AI được thiết kế với kiến trúc **Event-driven, Asynchronous & Distributed**. Sự tách biệt hoàn toàn giữa Frontend, Backend API Gateway và các AI Worker Stateless giúp hệ thống đảm bảo FPS (Frames Per Second) cao ngay cả khi lượng người dùng tăng đột biến.

## 1. Cấu trúc Tổng thể (High-level Architecture)

Hệ thống bao gồm 4 tầng (tiers) chính:

1. **Client Tier (Frontend):** 
   - Xây dựng bằng **Next.js 14** (App Router).
   - Truy cập Camera thiết bị thông qua WebRTC / `getUserMedia`.
   - Tích hợp mô hình AI nhẹ **MediaPipe BlazeFace** trực tiếp trên trình duyệt để thực hiện **Edge Tracking** (theo dõi khuôn mặt liên tục).
   - Sử dụng thuật toán **Laplacian Variance** để đánh giá độ mờ (Blur Detection), tự động bỏ qua các ảnh bị nhòe.
   - Tự động cắt mặt (Edge Crop) với 25% padding và chỉ stream phần ảnh khuôn mặt (kèm `local_track_id`) qua **WebSocket** (Subprotocol: `camera-observer`) với tần suất tối ưu.
2. **Gateway Tier (FastAPI Backend):**
   - Đóng vai trò là điểm cuối (endpoint) giao tiếp với người dùng (`routes.py`).
   - Quản lý **Xác thực JWT RS256 Stateless**: Token được ký mã hóa bằng RSA Private Key và xác thực tức thì bằng RSA Public Key tại mọi instance Gateway.
   - Tiếp nhận luồng WebSocket, bóc tách protocol nhị phân (chứa siêu dữ liệu Edge Crop + ảnh JPEG) và đẩy vào hàng đợi thông qua **Redpanda** (Event Sourcing - topic `camera_frames`).
   - Xử lý gán nhãn thông tin hồ sơ bằng cách mapping `local_track_id` từ Worker trả về.
   - Chờ nhận kết quả từ Redis (qua cơ chế Pub/Sub) và truyền lại cho Frontend.
3. **Worker Tier (AI Processing):**
   - Là các tiến trình (containers) độc lập, hoàn toàn **Stateless** (không lưu trạng thái - `ai_worker.py`).
   - Lắng nghe sự kiện từ Redpanda, kéo các Edge Crop về. 
   - Sử dụng kiến trúc **Hybrid Detection**: Worker chạy mô hình **SCRFD 500M** (viết bằng C++ / ONNX) trên ảnh Crop để trích xuất cực kỳ chính xác 5 điểm mốc (landmarks) bất chấp góc nghiêng.
   - Dựa vào 5 điểm mốc, thuật toán Affine Transform sẽ căn chỉnh (Align) khuôn mặt trước khi đưa vào mô hình nhận diện **EdgeFace** để lấy Vector (Embedding).
   - Đẩy kết quả trở lại một kênh (channel) đặc thù của `connection_id` tương ứng trên Redis (Channel name: `worker_results_{connection_id}`).
4. **Data Tier (Database & Cloud Storage):**
   - **PostgreSQL (Supabase):** Kết hợp `pgvector` và adapter `pgvector.psycopg2` (Native Binary Parameter Binding) cho việc tìm kiếm HNSW siêu tốc (Vector Similarity Search) áp dụng cho cả Guest và Customer. Dual-write fallback với SQLite.
   - **Supabase Storage:** Lưu trữ ảnh đại diện của khách hàng trên Cloud CDN.

---

## 2. Luồng Dữ liệu (Data Flow) & Scalability

### 2.1. Phân phối tác vụ qua Redpanda & Redis
Hệ thống sử dụng **Redpanda** cho luồng dữ liệu vào (Event Sourcing) và **Redis** cho luồng kết quả ra:
- API Server nhận frame từ WebSocket và Produce vào topic `camera_frames` của Redpanda (định dạng nhị phân với 4 byte header để chỉ định metadata). Data được giữ lại (Retention 2GB) phục vụ Replay.
- Bất kỳ AI Worker nào cũng thuộc chung một Consumer Group, kéo dữ liệu theo lô lớn (Batch Polling). Việc xử lý lô lớn giúp Worker bỏ qua (drop) các frame trùng lặp cũ và luôn bắt kịp tốc độ Realtime.
- Cơ chế này cho phép **Horizontal Scaling** vô hạn: API Server không bao giờ bị nghẽn CPU dù số lượng Camera tăng lên, các Worker cũng không bị gán chặt với bất kỳ Camera cụ thể nào.

### 2.2. Edge Tracking & Caching
Thay vì gửi liên tục 30 FPS lên Server gây quá tải mạng, Front Door AI sử dụng kiến trúc Edge Tracking:
- **Xử lý tại biên (Edge):** MediaPipe trên trình duyệt nhận diện và cấp phát một mã theo dõi duy nhất (`local_track_id`) cho từng người. Bounding Box trên giao diện được vẽ trực tiếp ở tần số 60 FPS mà không cần đợi Server.
- **Tối ưu băng thông & Nhiễu:** Frontend đánh giá độ nhòe ảnh (Blur Detection), từ chối góc nghiêng xấu, sau đó cắt (crop) khuôn mặt với Padding 25% và gửi ảnh nhỏ gọn (10-20KB) lên Server theo một tần suất cố định (ví dụ: 1 ảnh/giây). Server (Worker) nhận crop, sẽ chạy tiếp mạng **SCRFD** để đảm bảo alignment hoàn hảo nhất trước khi nhúng.
- **Session Isolation:** Mỗi Tab Trình duyệt kết nối sinh ra một `connection_id` ngẫu nhiên. Khi AI Worker xử lý xong, nó publish kết quả vào kênh Redis riêng (`worker_results_{connection_id}`). API Server nhận kết quả và forward về Client, Client sẽ tự động ánh xạ thông tin cá nhân vào `local_track_id` đang hiển thị.

---

## 3. Sơ đồ Kiến trúc (Architecture Diagram)

```mermaid
graph TD
    subgraph Client [Client / Browser]
        A[Next.js UI] -->|getUserMedia| B(Canvas Frame)
        B <-->|WebSocket| C[FastAPI Gateway]
    end

    subgraph Backend [Master Node / Gateway]
        C -->|1. Produce (camera_frames)| D[(Redpanda)]
        E[(Redis Pub/Sub)] -->|4. Subscribe (worker_results_...)| C
    end

    subgraph Workers [Worker Nodes / AI Cluster]
        F[AI Worker 1 (Stateless)]
        G[AI Worker 2 (Stateless)]
        
        D -->|2. Batch Poll & Deduplicate| F
        D -->|2. Batch Poll & Deduplicate| G
        
        F -->|3. SCRFD Detect + EdgeFace Embed| E
        G -->|3. SCRFD Detect + EdgeFace Embed| E
    end

    subgraph Database [Cloud Database & Storage]
        F -->|HNSW Search / Dual-write| I[(PostgreSQL / Supabase)]
        G -->|HNSW Search / Dual-write| I
        C -->|CRUD & Permissions| I
    end
```

## 4. Tối ưu hóa Hiệu năng & Vận hành

- **Connection Pool:** Cả API Server và AI Worker đều sử dụng `ThreadedConnectionPool` của `psycopg2` để tái sử dụng kết nối Database, tránh Overhead khi khởi tạo Connection mới liên tục.
- **Track Lifecycle Caching:** Dữ liệu hồ sơ khách hàng chỉ truy vấn **1 lần duy nhất** khi khuôn mặt xuất hiện. Cache in-RAM qua `GuestTrackManager`.
- **Throttling & Lazy Execution:** Embedding chỉ được thực thi với các frame đủ điều kiện. Worker chủ động drop các frame đã "quá hạn" (`delay > 0.5s`) trên hàng đợi để đảm bảo tính Real-time.
- **Centralized Logging:** Module `logger.py` chuẩn hóa toàn bộ log trên backend, hỗ trợ tốt cho việc Debug trên Docker.

## 5. Hạ tầng Triển khai (Deployment Infrastructure)

Hệ thống hiện tại được triển khai trên nền tảng AWS EC2 với mô hình cluster Master-Worker:

- **Master Node (Gateway, API, Database, Message Broker):**
  - **Public IP:** `15.134.121.250` | **Private IP:** `172.31.9.172`
  - **SSH Key:** `MASTER.pem` (đường dẫn cục bộ: `C:\Users\hotru\Downloads\MASTER.pem`)
- **Worker Nodes (AI Processing - 2 instances):**
  - **Worker 1 IP:** `54.253.192.210` | **Private IP:** `172.31.2.93`
  - **Worker 2 IP:** `54.252.191.145` | **Private IP:** `172.31.4.195`
  - **SSH Key:** `WORKERS.pem` (đường dẫn cục bộ: `C:\Users\hotru\Downloads\WORKERS.pem`)
