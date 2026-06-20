# Tài liệu API & WebSocket (API Reference)

Hệ thống giao tiếp qua REST API (cho tác vụ quản lý) và WebSocket (cho luồng Video Streaming thời gian thực).

---

## 1. WebSocket Streaming (Real-time Video)

Endpoint xử lý luồng ảnh từ Camera Client và trả về dữ liệu nhận diện khuôn mặt.

**URL:** `ws://{host}:8000/ws/{session_id}`
- `{session_id}`: Chuỗi ngẫu nhiên (UUID hoặc Random String) đại diện cho một Tab Browser để cô lập Session (Session Isolation).

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

---

## 2. RESTful APIs

### 2.1. Authentication

**`POST /api/login`**
Xác thực người dùng và trả về Session Token.

- **Request Body (JSON):**
  ```json
  { "username": "admin", "password": "secret_password" }
  ```
- **Response (200 OK):**
  ```json
  {
      "success": true,
      "token": "a1b2c3d4e5f6g7h8",
      "user": { "username": "admin", "role": "admin", "cameras": ["cam1"] }
  }
  ```

---

### 2.2. Quản lý Khách hàng (Profiles)

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

### 2.3. Chấm công / Check-in (Attendance)

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

### 2.4. Promote Guest (Nâng cấp Vãng lai thành Khách hàng)
**`POST /api/promote_guest`**
Dùng nội bộ để đồng bộ việc đổi `GUEST_ID` sang `CUSTOMER_ID` trong cấu trúc Vector In-memory và Database.

- **Request Body (JSON):**
  ```json
  { "guest_id": "GUEST_123", "new_id": "CUS_005" }
  ```
