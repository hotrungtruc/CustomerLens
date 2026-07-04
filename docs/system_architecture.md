# Kiến trúc Hệ thống (System Architecture)

Dự án Front Door AI được thiết kế với kiến trúc **Event-driven, Asynchronous & Distributed**. Sự tách biệt hoàn toàn giữa Frontend, Backend API Gateway và các AI Worker Stateless giúp hệ thống đảm bảo FPS (Frames Per Second) cao ngay cả khi lượng người dùng tăng đột biến.

## 1. Cấu trúc Tổng thể (High-level Architecture)

Hệ thống bao gồm 4 tầng (tiers) chính:

1. **Client Tier (Frontend):** 
   - Xây dựng bằng **Next.js 14** (App Router).
   - Truy cập Camera thiết bị thông qua WebRTC / `getUserMedia`.
   - Tích hợp mô hình AI nhẹ **MediaPipe** trực tiếp trên trình duyệt để thực hiện **Edge Tracking** (theo dõi khuôn mặt liên tục).
   - Tự động cắt mặt (crop) và chỉ stream phần ảnh khuôn mặt (kèm `local_track_id`) qua **WebSocket** (Subprotocol: `camera-observer`) với tần suất tối ưu (vd: 1 lần/giây).
2. **Gateway Tier (FastAPI Backend):**
   - Đóng vai trò là điểm cuối (endpoint) giao tiếp với người dùng (`routes.py`).
   - Tiếp nhận luồng WebSocket, bóc tách protocol nhị phân (chứa siêu dữ liệu Edge Crop + ảnh JPEG) và đẩy vào hàng đợi thông qua **Redis** (`camera_frames_v2`).
   - Xử lý gán nhãn thông tin hồ sơ bằng cách mapping `local_track_id` từ Worker trả về.
   - Chờ nhận kết quả từ Redis (qua cơ chế Pub/Sub) và truyền lại cho Frontend.
3. **Worker Tier (AI Processing):**
   - Là các tiến trình (containers) độc lập, hoàn toàn **Stateless** (không lưu trạng thái - `ai_worker.py`).
   - Lắng nghe hàng đợi từ Redis, kéo frame về, xử lý phát hiện (Detection), theo dõi (Tracking) và trích xuất vector (Embedding).
   - Đẩy kết quả trở lại một kênh (channel) đặc thù của `connection_id` tương ứng trên Redis (Channel name: `worker_results_{connection_id}`).
4. **Data Tier (Database & Cloud Storage):**
   - **PostgreSQL (Supabase):** Kết hợp `pgvector` cho việc tìm kiếm HNSW siêu tốc (Vector Similarity Search) áp dụng cho cả Guest và Customer. Dual-write fallback với SQLite.
   - **Supabase Storage:** Lưu trữ ảnh đại diện của khách hàng trên Cloud CDN.

---

## 2. Luồng Dữ liệu (Data Flow) & Scalability

### 2.1. Phân phối tác vụ qua Redis Pub/Sub
Hệ thống sử dụng Redis làm Message Broker trung tâm:
- API Server nhận frame từ WebSocket và đẩy vào Redis list/queue (định dạng nhị phân với 4 byte header để chỉ định metadata).
- Bất kỳ AI Worker nào đang rảnh (Idle) sẽ block (`BLPOP`) trên queue này để xử lý ngay lập tức khi có frame mới.
- Cơ chế này cho phép **Horizontal Scaling** vô hạn: API Server không bao giờ bị nghẽn CPU dù số lượng Camera tăng lên, các Worker cũng không bị gán chặt với bất kỳ Camera cụ thể nào.

### 2.2. Edge Tracking & Caching
Thay vì gửi liên tục 30 FPS lên Server gây quá tải mạng, Front Door AI sử dụng kiến trúc Edge Tracking:
- **Xử lý tại biên (Edge):** MediaPipe trên trình duyệt nhận diện và cấp phát một mã theo dõi duy nhất (`local_track_id`) cho từng người. Bounding Box trên giao diện được vẽ trực tiếp ở tần số 60 FPS mà không cần đợi Server.
- **Tối ưu băng thông:** Frontend chỉ cắt (crop) khung mặt và gửi ảnh nhỏ gọn (10-20KB) lên Server theo một tần suất cố định (ví dụ: 1 ảnh/giây). 
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
        C -->|1. Push Frame (camera_frames_v2)| D[(Redis Queue)]
        E[(Redis Pub/Sub)] -->|4. Subscribe (worker_results_...)| C
    end

    subgraph Workers [Worker Nodes / AI Cluster]
        F[AI Worker 1 (Stateless)]
        G[AI Worker 2 (Stateless)]
        
        D -->|2. Pop Frame BLPOP| F
        D -->|2. Pop Frame BLPOP| G
        
        F -->|3. Publish Result| E
        G -->|3. Publish Result| E
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
