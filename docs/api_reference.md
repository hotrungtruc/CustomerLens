# Tài liệu API & WebSocket (API Reference)

Hệ thống giao tiếp qua REST API (cho tác vụ quản lý) và WebSocket (cho luồng Video Streaming thời gian thực).

---

## 1. WebSocket Streaming (Real-time Video)

Endpoint xử lý luồng ảnh từ Camera Client và trả về dữ liệu nhận diện khuôn mặt.

**URL publisher:** `ws://{host}:8000/ws/{camera_id}`

- `{camera_id}` là danh tính ổn định do `POST /api/device/identity` trả về.
- Browser phải có cookie HttpOnly `device_token`; backend kiểm tra Origin, cookie và Camera ID trước khi `accept()`.
- Mỗi handshake sinh `connection_id` mới. Backend gửi `{ "type": "ready", "camera_id": "...", "connection_id": "..." }` trước khi nhận frame.
- Redis giữ lease `camera:presence:{camera_id}` trong 15 giây và renew mỗi 5 giây. Chỉ một publisher được giữ lease.

**Luồng dữ liệu (Data Flow):**
1. **Client gửi (Upstream):** 
   Gửi trực tiếp ảnh dưới dạng **Binary Raw Bytes (ArrayBuffer)** thay vì JSON Base64 để tiết kiệm 33% băng thông và tăng tốc decode.
2. **Server trả về (Downstream):**
   Trả về kích thước gốc của frame và mảng các `customers` (được nhận diện hoặc đang theo dõi).
   ```json
   {
       "frame_size": { "width": 640, "height": 360 },
       "customers": [
           {
               "track_id": 1,
               "bbox": [100, 50, 200, 150],
               "detected": true,
               "id": "CUS_001",
               "name": "Nguyen Van A",
               "loyalty_tier": "VIP"
           }
       ]
   }
   ```

**URL observer:** `ws://{host}:8000/ws/observe/{camera_id}`

Observer truyền hai WebSocket subprotocol: `camera-observer` và login token. Backend xác thực role/permission trước `accept()`; annotation được bridge qua `camera_updates:{camera_id}` nên publisher reconnect không đổi URL observer.

---

## 2. RESTful APIs

### 2.1. Authentication

**`POST /api/login`**
Xác thực người dùng và trả về Session Token.

- **Request Body (JSON):**
  ```json
  { "username": "admin", "password": "secret_password" }
  ```

### 2.2. Camera identity và recovery

**`POST /api/device/identity`**

Resolve-or-create camera bằng cookie HttpOnly. Không có cookie sẽ tạo camera mới; cookie hợp lệ trả lại Camera ID cũ; token revoked/invalid trả `401`.

**`GET /api/cameras`**

Yêu cầu `Authorization: Bearer <token>`. Admin thấy toàn bộ camera; moderator chỉ thấy camera có permission. Catalog lấy từ database, `active` và `connection_id` lấy từ Redis presence.

**`POST /api/device/enrollments`**

Admin tạo pairing code 6 số, dùng một lần và mặc định hết hạn sau 10 phút.

**`POST /api/device/enrollments/claim`**

Thiết bị dùng pairing code để nhận credential mới cho camera cũ. Credential chỉ được trả qua `Set-Cookie`; camera tạm tạo sau khi mất cookie được chuyển trạng thái `replaced`.

**`PUT /api/users/{username}/camera_permissions`**

Admin thay toàn bộ danh sách camera mà moderator được xem.

Xem luồng quản trị đầy đủ tại [moderator_camera_permission_management.md](moderator_camera_permission_management.md).
- **Response (200 OK):**
  ```json
  {
      "success": true,
      "token": "a1b2c3d4e5f6g7h8",
      "user": { "username": "admin", "role": "admin", "cameras": ["cam1"] }
  }
  ```

---

### 2.3. Quản lý Khách hàng (Profiles)

> **Yêu cầu Xác thực:** Thêm Header `Authorization: Bearer <token>` (Chỉ `admin` mới được cấp quyền ghi).

**`PUT /api/customer_profile`**
Tạo mới hoặc Cập nhật thông tin Khách hàng. Nếu truyền `source_id` là Guest (`GUEST_...`), hệ thống sẽ kích hoạt hàm Promote (Chuyển đổi).

- **Request Body (JSON):**
  ```json
  {
      "id": "CUS_102",
      "source_id": "GUEST_default_01_0001",
      "name": "Tran B",
      "phone": "0987654321",
      "loyalty_tier": "Standard"
  }
  ```

**`GET /api/customers`**
Lấy danh sách toàn bộ khách hàng.

**`DELETE /api/customers/{customer_id}`**
Xóa hồ sơ khách hàng, kèm theo xóa ảnh trên Supabase Storage và xóa Vector Embedding.

---

### 2.4. Chấm công / Check-in (Attendance)

**`POST /api/check_in/{customer_id}`**
Thực hiện ghi nhận lượt tới thăm (Check-in) thủ công (Manual Override) hoặc gọi qua màn hình Detail.
Có cơ chế **Cooldown** (VD: 30 giây) để tránh spam.

- **Response (200 OK):**
  ```json
  {
      "success": true,
      "message": "Check-in successful"
  }
  ```
- **Response (400/429 Cooldown):**
  ```json
  {
      "success": false,
      "message": "Please wait 25s"
  }
  ```

---

### 2.5. Promote Guest (Nâng cấp Vãng lai thành Khách hàng)
**`POST /api/promote_guest`**
Dùng nội bộ để đồng bộ việc đổi `GUEST_ID` sang `CUSTOMER_ID` trong cấu trúc Vector In-memory và Database.

- **Request Body (JSON):**
  ```json
  { "guest_id": "GUEST_123", "new_id": "CUS_005" }
  ```
