# Tài liệu API & WebSocket (API Reference)

Tầng Backend của Front Door AI được xây dựng dựa trên FastAPI (`backend/app/api/routes.py`). Nó cung cấp sự kết hợp chặt chẽ giữa HTTP REST APIs phục vụ tính năng quản trị, và WebSocket phục vụ truyền phát dữ liệu Real-time.

## 1. Giao thức Truyền phát WebSocket (WebSocket Streaming)

### 1.1 Luồng Device (Camera Client)
- **Endpoint:** `WS /ws/{camera_id}`
- **Chức năng:** Sử dụng bởi thiết bị Camera (Edge Device hoặc Trình duyệt) để truyền liên tục Binary Frames về máy chủ.
- **Xác thực:** Dựa trên Cookie HTTPOnly (`device_token`) được ký phát thông qua tiến trình Enrollment. Máy chủ sẽ xác thực tính hợp lệ của Device Credential thông qua DB trước khi chấp nhận kết nối.
- **Keep-alive & Lease:** Để tránh tình trạng một luồng bị chiếm dụng sai, máy chủ quản lý "Lease" (Phiên thuê) qua Redis (`_maintain_camera_lease`). Các lệnh Redis LUA Script được sử dụng để Renew, Takeover, và Release Lease. Máy chủ sẽ ngắt các WebSocket có ping trễ hoặc hết hạn Lease (`code 4009`).
- **Data Payload:** Frames được nén dạng JPEG, gửi lên theo định dạng nhị phân với Metadata (JSON chiều dài 4 bytes header) kèm theo hình ảnh thô. Máy chủ Produce payload thẳng vào Redpanda topic `camera_frames`.

### 1.2 Luồng Observer (Dashboard Client)
- **Endpoint:** `WS /ws/observe/{camera_id}`
- **Chức năng:** Sử dụng bởi Quản trị viên trên UI (Next.js) để xem luồng Camera và Bounding Box (khuôn mặt được AI đánh dấu).
- **Xác thực:** Dựa trên Sub-protocol. Client khởi tạo với mảng `sec-websocket-protocol`: `["camera-observer", "<Authorization_Token>"]`.
- **Hoạt động:** Server đăng ký (Subscribe) vào kênh Redis `worker_results_{connection_id}` để lắng nghe kết quả trả về từ AI Worker và forward (chuyển tiếp) chúng tới UI (Client) dạng JSON.

## 2. Các RESTful APIs Chính

### 2.1 Quản trị Thiết bị (Camera Enrollment)
- **`POST /api/device/identity`**
  - **Mô tả:** Camera gửi request lên để kiểm tra trạng thái cookie `device_token`. Nếu hợp lệ, trả về Camera ID. Nếu Cookie trống, hệ thống sẽ cấp một định danh Camera ID mới hoàn toàn.
- **`POST /api/device/enrollments`** (Admin)
  - **Mô tả:** Admin kích hoạt quá trình Pairing (Kết nối lại). Trả về một mã code 6 số (Lưu tạm trên Redis TTL 600s).
- **`POST /api/device/enrollments/claim`**
  - **Mô tả:** Thiết bị (Camera) nhập mã code 6 số để nhận cấp quyền sử dụng một ID Camera có sẵn, vô hiệu hóa các thông tin đăng nhập (Credentials) trước đó.

### 2.2 Quản lý Khách Hàng
- **`GET /api/customer_info?camera_id={camera_id}`**
  - **Mô tả:** Dựa vào trạng thái bộ nhớ đệm nội bộ của AI (Camera State), API trả về thông tin chi tiết của khách hàng *lớn nhất / rõ ràng nhất* đang đứng trước khung hình hiện tại. Phục vụ việc hiển thị Dashboard Real-time.
- **`PUT /api/customer_profile`** (Admin)
  - **Mô tả:** Cập nhật thông tin Hồ sơ khách hàng. API này đồng thời xử lý kịch bản **Promote Guest**: Nếu ID được truyền lên là định dạng `GUEST_...`, hệ thống sẽ update dữ liệu định danh thành Customer chính thức, sau đó phát thông báo (Publish) tới kênh `camera_control:{camera_id}` trên Redis để báo AI Worker tải lại bộ nhớ (Reload Embeddings).

### 2.3 Quản trị Hệ thống
- **`POST /api/login`**
  - **Mô tả:** Đăng nhập. Trả về Token (Tương đương API Key). Token này được lưu giữ tại một biến Dictionary RAM trên Gateway (`ACTIVE_SESSIONS`), cho phép phân giải User cực nhanh (Bỏ qua thao tác Query DB trên mỗi luồng request).
- **`GET` & `POST /api/settings`**
  - **Mô tả:** Quản lý các biến môi trường của hệ thống (Thresholds như `MIN_DETECTION_SCORE`, IOU Config, v.v.).

## 3. Kiến trúc Bảo mật API
- Hỗ trợ Rate Limiting cho API Pairing (Chống vét cạn mã 6 số).
- Sử dụng Check Role (`require_admin`) đối với các API tác động lên dữ liệu Customers và Device. 
- Chỉ chấp nhận WebSocket từ các luồng CORS hợp lệ (`WS_ALLOWED_ORIGINS`).
