# Kiến trúc Hệ thống (System Architecture) - Front Door AI

Dự án Front Door AI được thiết kế với kiến trúc **Event-driven, Asynchronous & Distributed** (Hướng sự kiện, Bất đồng bộ & Phân tán). Hệ thống áp dụng triết lý phân tách hoàn toàn giữa Frontend (Edge), API Gateway (Master) và AI Worker (Stateless Nodes) để đảm bảo FPS cao, khả năng mở rộng (Horizontal Scaling) mượt mà và tối ưu hóa Disk I/O trên cơ sở dữ liệu.

---

## 1. Cấu trúc Các Tầng (Multi-Tier Architecture)

Hệ thống được chia làm 4 tầng riêng biệt, hoạt động độc lập và giao tiếp thông qua mạng:

### 1.1. Client Tier (Frontend & Edge Computing)
- **Công nghệ:** Next.js 14 (App Router), Tailwind CSS, Lucide React.
- **Edge AI:** Tích hợp mô hình **MediaPipe Vision** thông qua WebAssembly. Thay vì gửi video liên tục làm nghẽn băng thông, trình duyệt sẽ chủ động nhận diện khuôn mặt (30-60 FPS), cấp phát `local_track_id`, và chỉ cắt (crop) phần khuôn mặt thành ảnh JPEG nhỏ (10-20KB).
- **Truyền dẫn:** Gửi ảnh crop lên Server qua **WebSocket** (Subprotocol: `camera-observer`) với tần suất định kỳ (VD: 1 ảnh/giây/người). Giao diện Bounding Box được vẽ trực tiếp bằng Canvas Overlay tại Edge mà không cần đợi Server trả về để tránh lag.

### 1.2. Gateway Tier (FastAPI Master Node)
- **Hạ tầng:** EC2 Master Node (IP: `15.134.121.250`).
- **Nhiệm vụ chính:**
  - Nhận luồng nhị phân (Binary Protocol) từ WebSocket.
  - Phân tích siêu dữ liệu, đính kèm thông tin định tuyến (Ví dụ: `"reply_to": "results_gateway_UUID"`).
  - Đẩy vào Message Broker để hàng đợi AI xử lý.
- **Message Brokers:**
  - **Redpanda (Kafka API):** Chịu tải luồng dữ liệu (Data Pipeline) khổng lồ cho ảnh Camera (`camera_frames_v2`) và luồng trả kết quả (`results_gateway_...`).
  - **Redis:** Quản lý WebRTC Signaling, Camera Presence/Lease Management, và các tín hiệu điều khiển (Control signals) thời gian thực có tần suất thấp.

### 1.3. Worker Tier (AI Processing Cluster)
- **Hạ tầng:** Các EC2 Worker Nodes độc lập (IP: `3.26.147.158`, `3.107.239.168`).
- **Công nghệ:** Python, InsightFace (ArcFace / RetinaFace), ONNX Runtime.
- **Stateless Consumer:** Chạy như các tiến trình độc lập, chung một Kafka Consumer Group (`ai_workers_group`). Khi hệ thống tải cao, chỉ cần bật thêm Worker, Kafka sẽ tự động Rebalance tải đều cho tất cả các node.
- **Luồng xử lý:** Kéo Frame từ Kafka -> Trích xuất Landmark / Vector (Embedding) -> So khớp Vector (HNSW) trong DB hoặc Cache -> Trả kết quả về Kafka Topic `reply_to` được chỉ định.

### 1.4. Data Tier (Database & Storage)
- **Công nghệ:** Supabase PostgreSQL & Supabase Storage (S3-compatible).
- **Vector Search:** Cài đặt extension `pgvector` tạo chỉ mục HNSW trên bảng `customer_embeddings` và `guest_embeddings` giúp tìm kiếm siêu tốc (L2 Distance hoặc Cosine Similarity).

---

## 2. Sơ đồ Kiến trúc Mạng & Xử lý (Network Diagram)

```mermaid
graph TD
    subgraph Edge [Client / Trình duyệt]
        A[Next.js Camera UI] -->|1. Edge Crop (MediaPipe)| B(Crop JPEG 20KB)
        B <-->|2. WebSocket (Binary Protocol)| C[FastAPI Gateway]
    end

    subgraph MasterNode [EC2 Master Node - 15.134.121.250]
        C -->|3. Produce Frame (camera_frames_v2)| D[(Redpanda Kafka Broker)]
        C <-->|WebRTC Signaling & Leases| R[(Redis)]
        E[(Redpanda Kafka Broker)] -->|6. Consume (results_gateway_UUID)| C
    end

    subgraph WorkerNodes [EC2 Worker Nodes - 3.x.x.x]
        F[AI Worker 1 (Consumer Group)]
        G[AI Worker 2 (Consumer Group)]
        
        D -->|4. Pull Frame| F
        D -->|4. Pull Frame| G
        
        F -->|5. Produce Reply-To| E
        G -->|5. Produce Reply-To| E
    end

    subgraph Database [Supabase Cloud]
        F -->|Vector HNSW Search| I[(PostgreSQL)]
        G -->|Vector HNSW Search| I
        C -->|CRUD & Permissions| I
    end
```

---

## 3. Các Tối ưu hóa Kiến trúc Nâng cao (Advanced Optimizations)

Hệ thống được tối ưu hóa ở mức Database và Routing để phù hợp với quy mô Enterprise:

### 3.1. Kafka Reply-To Routing (Cách 1)
- Vấn đề: Với nhiều API Server chạy song song (Master Node Load Balancing), nếu trả kết quả bừa bãi sẽ khiến các Gateway nhận nhầm kết quả của nhau.
- Giải pháp: Khi API Gateway bật lên, nó cấp phát một UUID duy nhất (VD: `GATEWAY_A`). Nó báo với Worker: *"Hãy gửi kết quả cho frame này về topic `results_gateway_GATEWAY_A`"*. Kafka đảm bảo thông tin luôn được trả về chính xác máy chủ đang mở WebSocket.

### 3.2. Database Connection Pooling (Supavisor)
- Việc AI Worker và Gateway liên tục mở connection tới Database có thể gây kiệt quệ tài nguyên (lỗi "Too many connections").
- Hệ thống sử dụng `ThreadedConnectionPool` của `psycopg2` kết nối qua **Supavisor (Transaction Mode - Cổng 6543)** của Supabase thay vì cổng mặc định 5432. Supavisor gom hàng nghìn Request ảo thành một vài Connection thực tế tới DB.

### 3.3. Tối ưu Ghi log bằng Partitioning & Bulk Insert
- Bảng `recognize_logs` sinh ra hàng chục nghìn dòng mỗi ngày. Thay vì `INSERT` từng dòng, Worker lưu trữ vào biến tạm và sử dụng **Bulk Insert** (`execute_values`) lên PostgreSQL mỗi chu kỳ.
- Bảng `recognize_logs` được cấu hình **List Partitioning theo `moderator_username`**. Dữ liệu của quán cà phê A sẽ hoàn toàn độc lập với quán B ở mức đĩa cứng (Disk), giúp các truy vấn lịch sử hoặc tính toán thống kê (Analytics) của quán nào chỉ quét đúng phân vùng của quán đó, tốc độ tăng gấp hàng chục lần.

### 3.4. Cấu trúc Soft Delete (Xóa mềm) & Autovacuum
- Khách hàng (Customers) khi bị xóa sẽ không dùng lệnh `DELETE` gây "thủng" HNSW Index dẫn tới làm chậm hệ thống. Thay vào đó, áp dụng cơ chế **Soft Delete** (cập nhật cờ `is_deleted = TRUE`).
- Để PostgreSQL không bị phình (bloat) vì thao tác UPDATE, hệ thống thiết lập **Autovacuum Tuning** cực nhạy trên bảng này (Trigger khi lượng rác đạt 5% `autovacuum_vacuum_scale_factor = 0.05`).

### 3.5. Guest Lifecycle Caching (Cache Khách vãng lai)
- Dữ liệu định danh khuôn mặt được AI Worker cache trên RAM thông qua `GuestTrackManager`. Khi một khách hàng (hoặc Guest) xuất hiện liên tục trong khung hình (có cùng `local_track_id`), Worker chỉ tìm kiếm trong Database ở **Frame đầu tiên**, các frame sau đó chỉ lấy kết quả từ bộ nhớ đệm.

---

## 4. Tổng Kết
Với kiến trúc Kafka/Redpanda Event-Driven kết hợp Edge Computing (MediaPipe) và Database Partitioning, hệ thống có khả năng đáp ứng lượng truy cập và xử lý hình ảnh liên tục cho hàng chục chi nhánh cùng lúc mà không xảy ra tình trạng "Nghẽn cổ chai" (Bottleneck) ở bất kì điểm nào. Mọi thao tác đều có thể Scale Out dễ dàng bằng cách mua thêm EC2 Server.
