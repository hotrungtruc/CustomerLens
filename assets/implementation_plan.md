# Kế hoạch triển khai Giải pháp 2 (Stateless Workers + Centralized Tracking)

Mục tiêu: Tách rời Tracking khỏi AI Worker. Worker chỉ nhận diện khuôn mặt và trích xuất đặc trưng (embedding), sau đó gửi về Master. Master sẽ đảm nhiệm việc Tracking (SORT) và giao tiếp với Cơ sở dữ liệu. Kiến trúc này giúp cân bằng tải hoàn hảo, mở rộng linh hoạt, và tránh tình trạng mất ID khách (GUEST_ID flickers).

## Đề nghị phản hồi (User Review Required)

> [!WARNING]  
> **Kiến trúc phân tán lớn:** Đây là một thay đổi lớn về kiến trúc (Major Architecture Shift). Việc triển khai sẽ yêu cầu:
> 1. Sửa đổi luồng dữ liệu (Data Pipeline) giữa `routes.py` và `ai_worker.py`.
> 2. Các EC2 AI Worker cũ sẽ cần được tải lại code mới.
> Vui lòng xem kỹ phần "Các thay đổi đề xuất" trước khi phê duyệt.

## Các câu hỏi mở (Open Questions)
Không có. Luồng xử lý dữ liệu và cấu trúc Payload đã được tôi kiểm tra kỹ qua mã nguồn hiện tại của hệ thống.

---

## Các thay đổi đề xuất (Proposed Changes)

### 1. `backend/app/ai_worker.py` (AI Worker)
- **Hàng đợi chung:** Đổi hàng đợi lắng nghe thành chung một List `camera_frames` (thay vì `camera_frames_default`).
- **Phi trạng thái (Stateless):** Gỡ bỏ hoàn toàn `GuestTrackManager`, `get_db_connection`, và `bulk_insert_recognize_logs`.
- **Trích xuất Đặc trưng (Embedding):** Worker sẽ nhận diện (Detect) và tự động tính Embedding (trích xuất đặc trưng vector 512 chiều) cho tất cả các khuôn mặt đạt chuẩn trong khung hình.
- **Phản hồi (Publish):** Trả kết quả (Bounding box + Landmark + Score + Embedding) về cho Master thông qua Pub/Sub channel `worker_results_{camera_id}`.

### 2. `backend/app/api/routes.py` (FastAPI Master)
- **Tạo Hàng đợi chung:** Thay vì đẩy ảnh vào `camera_frames_{session_id}`, Master sẽ đẩy mọi ảnh vào `camera_frames` chung, đính kèm `session_id` trong Metadata.
- **Quản lý Tracker (Stateful Tracking):** Master sẽ khởi tạo và lưu trữ một phiên bản `GuestTrackManager` riêng biệt cho mỗi kết nối WebSocket (mỗi `session_id` có 1 tracker riêng). 
- **Bắt kết quả & Tracking:** Master lắng nghe `worker_results_{session_id}`. Khi nhận kết quả từ các Worker, Master sẽ:
  - Chạy `tracker.process_faces(records)` (Thuật toán SORT).
  - Tra cứu DB (`get_customer_info`).
  - Ghi Log vào DB (`bulk_insert_recognize_logs`).
  - Đóng gói và gửi Payload qua WebSocket về Frontend.
- **Bất đồng bộ (Async):** Tất cả các thao tác Tracking & Database sẽ được chạy thông qua `asyncio.to_thread` để đảm bảo luồng ASGI/FastAPI không bị treo (block).

### 3. `backend/app/core/guest_tracking.py` (Tracking Engine)
- Cập nhật nhẹ `process_faces` để xử lý mảng `embedding` (đã được tính toán sẵn từ Worker gửi về) thay vì tự trích xuất qua `embedder`.

---

## Kế hoạch kiểm thử (Verification Plan)

### Kiểm thử thủ công (Manual Verification)
1. Tôi sẽ khởi động lại cả 2 máy AI Worker (Worker 1 & Worker 2).
2. Yêu cầu bạn mở trang chủ `checkinface.me` để WebRTC gửi hình ảnh lên.
3. Cùng theo dõi khung hình: Dù hệ thống có chia việc cho cả 2 máy Worker, ID khách (`GUEST_...`) sẽ luôn **đứng yên và liên tục**, không còn bị giật nháy qua lại giữa hai số ID khác nhau.
4. Đóng kết nối / Tải lại trang sẽ khởi tạo GUEST ID mới, hoạt động đúng logic hệ thống.
