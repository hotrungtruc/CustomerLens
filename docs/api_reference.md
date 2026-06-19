# Tài liệu API & WebSocket (API Reference)

Backend cung cấp các REST API cho việc quản lý và một kết nối WebSocket tốc độ cao cho luồng xử lý Camera theo thời gian thực.

## 1. Xác thực (Authentication)
Một số API yêu cầu quyền Quản trị (Admin) cần truyền token vào HTTP Header.
- **Header format:** `Authorization: <token_được_cấp_khi_login>`

---

## 2. Các Endpoints REST API chính

### 2.1. Đăng nhập
**`POST /api/login`**
- **Body (JSON):** `{"username": "...", "password": "..."}`
- **Response:** `{"success": true, "token": "...", "user": {...}}`
- Dùng để xác thực nhân viên/quản trị viên.

### 2.2. Lấy dữ liệu Khách hàng đang xuất hiện
**`GET /api/customers_overview?camera_id=...`**
- **Mô tả:** Trả về danh sách TẤT CẢ các khuôn mặt đang được nhận diện trên khung hình, kèm theo bounding box và thông tin (nếu là khách hàng quen).
- **Response:** `{"status": "success", "customers": [...], "frame_size": {...}}`

**`GET /api/customer_info?camera_id=...`**
- **Mô tả:** Trả về thông tin chi tiết (kèm ảnh base64/url) của khách hàng được nhận diện chính hiện tại.

### 2.3. Check-in Điểm danh
**`POST /api/check_in`**
- Điểm danh cho khách hàng đang được nhận diện trên camera hiện tại. Có cơ chế Cooldown (chờ) giữa 2 lần check-in liên tiếp để tránh spam.
**`POST /api/check_in/{customer_id}`**
- Tương tự nhưng ép buộc check-in cho một ID cụ thể.

### 2.4. Quản lý Hồ sơ (Admin Only)
**`PUT /api/customer_profile`**
- **Header:** `Authorization: <token>`
- **Mô tả:** Cập nhật thông tin khách hàng, hoặc đăng ký mới khách hàng từ một "Khách mới" (`GUEST_...`).
- **Body (JSON):** Các trường `name`, `phone`, `note`,...

**`GET /api/customers`**
- Lấy danh sách toàn bộ khách hàng trong CSDL.

**`GET /api/customer_profile_by_id/{customer_id}`**
- Lấy hồ sơ của một khách hàng dựa trên ID.

---

## 3. WebSocket luồng Camera (Camera Stream)

Thay vì gửi ảnh liên tục qua HTTP (rất chậm), frontend mở một kết nối WebSocket để gửi nhận liên tục.

**`WS /ws/{session_id}`** (Ví dụ session_id có thể là ID của tab trình duyệt hoặc ID của camera)

- **Client gửi (Upstream):**
```json
{
  "image": "base64_encoded_jpeg_string_from_webcam"
}
```

- **Server phản hồi (Downstream):**
```json
{
  "customers": [
    {
      "track_id": 1,
      "bbox": [x1, y1, x2, y2],
      "detected": true,
      "id": "CUST_001",
      "name": "Nguyen Van A"
    }
  ],
  "frame_size": {"width": 640, "height": 360}
}
```

> [!NOTE]
> AI Thread của backend chạy độc lập với luồng WebSocket này. Khi có WebSocket đẩy frame lên, frame được lưu vào `SharedFrameManager`. Quá trình trả về tọa độ `bbox` ngay lập tức dựa trên tọa độ mới nhất mà luồng AI tính toán được, không bị giật lag khung hình.
