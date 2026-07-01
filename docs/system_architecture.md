# Kiến trúc Hệ thống (System Architecture)

Dự án Front Door AI được thiết kế với kiến trúc **Event-driven & Asynchronous**, tách biệt hoàn toàn giữa Frontend, Backend API và Luồng AI chạy ngầm. Điều này giúp hệ thống đảm bảo FPS (Frames Per Second) cao ngay cả khi máy chủ chịu tải hoặc mạng giật lag.

## 1. Cấu trúc Tổng thể (High-level Architecture)

Hệ thống bao gồm 3 tầng (tiers) chính:

1. **Client Tier (Frontend):** 
   - Xây dựng bằng **Next.js 14** (App Router).
   - Truy cập Camera thiết bị thông qua WebRTC / `getUserMedia`.
   - Nén ảnh và stream trực tiếp dữ liệu thô (Raw Binary) qua **WebSocket**.
2. **Server Tier (Backend):**
   - Xây dựng bằng **FastAPI** (Python 3.10+).
   - Tiếp nhận luồng WebSocket, cập nhật frame mới nhất vào `SharedFrameManager`.
   - **AI Thread:** Một ThreadPool ngầm độc lập chịu trách nhiệm đọc frame từ `SharedFrameManager`, xử lý phát hiện (Detection), theo dõi (Tracking) và trích xuất vector (Embedding).
3. **Data Tier (Database & Vector Store):**
   - **PostgreSQL (Supabase)** kết hợp **pgvector** cho việc tìm kiếm HNSW siêu tốc (Vector Similarity Search).
   - Cơ chế Fallback sang **SQLite** (In-memory cosine similarity) cho các môi trường Edge Computing không có Internet.

---

## 2. Luồng Dữ liệu (Data Flow) & Isolation

### 2.1. Camera identity và WebSocket

Frontend gọi `POST /api/device/identity` trước khi mở `/ws/{camera_id}`. Camera ID được lưu trong database và ổn định theo cookie HttpOnly. Backend xác thực Origin/cookie, acquire Redis lease, rồi mới `accept()` và sinh `connection_id` riêng cho handshake.

Frame metadata mang cả `camera_id` và `connection_id`. AI worker publish vào `worker_results_{connection_id}`; master chỉ nhận kết quả nếu connection còn giữ lease. Observer dùng bridge ổn định `camera_updates:{camera_id}`.

### 2.2. Queue AI và presence

Publisher đẩy JPEG binary vào queue Redis chung `camera_frames_v2`. Worker stateless detect/embed rồi trả kết quả theo Connection ID. `ConnectionState` chỉ sống trong thời gian socket; catalog camera sống trong database.

Redis key `camera:presence:{camera_id}` có TTL 15 giây, renew 5 giây và compare-and-delete khi cleanup. Vì vậy backend restart không mất catalog, còn mất mạng tự chuyển Idle sau TTL.
- Frontend có thể gửi lên 30 FPS.
- AI Thread chạy độc lập. Nếu AI đang xử lý chưa xong mà frame mới đến, frame cũ sẽ bị ghi đè (thay vì bị đưa vào hàng đợi gây độ trễ tích lũy).
- Tham số `PROCESS_EVERY_N_FRAMES` cho phép AI chỉ lấy mẫu (ví dụ 10 FPS) để tiết kiệm CPU, trong khi UI vẫn hiển thị mượt mà.

---

## 3. Sơ đồ Kiến trúc Động (Dynamic Architecture Diagram)

```mermaid
graph TD
    subgraph Client [Client / Browser]
        A[Next.js UI] -->|getUserMedia| B(Canvas Frame)
        B -->|JPEG binary + device cookie| C[Publisher WS]
    end

    subgraph Backend [FastAPI Backend]
        C -->|Frames| D[WS Route Handler]
        D -->|camera_id + connection_id| E[(Redis camera_frames_v2)]
        E -->|BRPOP| F[Stateless AI Worker]
        F -->|Detect & Track| G[GuestTrackManager]
        G -->|HNSW Query| H[(Supabase pgvector)]
        G -->|worker_results connection_id| D
        D -->|camera_updates camera_id| J[Authenticated Observer]
    end

    subgraph Cloud [Cloud Services]
        H -->|Storage| I[Supabase Storage (Images)]
    end
```

## 4. Tối ưu hóa Hiệu năng (Performance Optimizations)

- **Connection Pool:** Sử dụng `ThreadedConnectionPool` của psycopg2, tái sử dụng kết nối thay vì mở/đóng liên tục.
- **Track Lifecycle Caching:** Dữ liệu hồ sơ khách hàng chỉ được truy vấn **1 lần duy nhất** khi khuôn mặt xuất hiện. Sau đó lưu vào RAM theo `TrackState`. Các frame sau của người đó sẽ không tốn chi phí gọi Database.
- **Lazy Embedding:** Việc trích xuất vector đặc trưng 512D (nặng nhất) chỉ xảy ra ở một số frame nhất định (khi đủ điều kiện kích thước và chất lượng), và được đẩy vào một Thread phụ (`is_extracting`) để không làm nghẽn luồng Tracking chính.
