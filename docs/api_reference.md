# Tài liệu API & WebSocket (API Reference)

Hệ thống giao tiếp thông qua hai phương thức chính: REST API (dành cho các tác vụ quản lý dữ liệu) và WebSocket (dành cho việc truyền tải luồng Video thời gian thực).

---

## 1. WebSocket Streaming (Real-time Video)

Endpoint xử lý luồng ảnh từ thiết bị đầu cuối (Camera Client) và trả về dữ liệu nhận diện.

**URL:** `ws://{host}:8000/ws/{session_id}`
- `{session_id}`: Chuỗi ngẫu nhiên (UUID hoặc Random String) đại diện cho một kết nối Client để thiết lập cơ chế Session Isolation.

**Luồng dữ liệu (Data Flow):**
1. **Client gửi (Upstream):** 
   Gửi hình ảnh trực tiếp dưới dạng **Binary Raw Bytes (ArrayBuffer)**. Thiết kế này giúp tiết kiệm băng thông mạng và tối ưu hóa thời gian giải mã so với chuỗi Base64.
2. **Server trả về (Downstream):**
   Trả về dữ liệu định dạng JSON chứa kích thước gốc của khung hình và mảng thông tin về các `customers` đang được nhận diện.
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

### 2.1. Xác thực (Authentication)

**`POST /api/login`**
Xác thực người dùng và cấp phát Token.

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

> **Yêu cầu Xác thực:** Cần đính kèm Header `Authorization: Bearer <token>`.

**`PUT /api/customer_profile`**
Tạo mới hoặc cập nhật thông tin khách hàng. Nếu truyền tham số `source_id` là mã định danh Guest (`GUEST_...`), hệ thống sẽ thực hiện quá trình Gộp (Merge/Promote) vector đặc trưng.

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
Xóa hồ sơ khách hàng. Thao tác này cũng sẽ xóa ảnh trên Supabase Storage và toàn bộ dữ liệu Vector Embedding tương ứng (Cascade Delete).

---

### 2.3. Nhật ký Ra Vào (Attendance)

**`POST /api/check_in/{customer_id}`**
Ghi nhận thủ công lượt check-in của khách hàng. Endpoint này được áp dụng cơ chế **Cooldown** (ví dụ: 30 giây) để ngăn chặn việc ghi nhận trùng lặp.

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
      "error": "Cooldown period active"
  }
  ```

---

### 2.4. Quản trị Cơ sở Dữ liệu

**`POST /api/query_db`**
Endpoint ẩn dành cho Quản trị viên (Super Admin) dùng để thực thi trực tiếp các lệnh SQL (chỉ có hiệu lực trong môi trường Development hoặc khi truyền đúng thông số bảo mật).

- **Request Body:**
  ```json
  {
      "query": "SELECT * FROM users",
      "params": []
  }
  ```

**`POST /api/promote_guest`**
Đồng bộ việc chuyển đổi `GUEST_ID` sang `CUSTOMER_ID` trong cấu trúc Vector In-memory và Database.

- **Request Body (JSON):**
  ```json
  { "guest_id": "GUEST_123", "new_id": "CUS_005" }
  ```
