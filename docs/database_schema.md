# Cấu trúc Cơ sở Dữ liệu (Database Schema)

Hệ thống được thiết kế để hỗ trợ cả lưu trữ trên Đám mây qua PostgreSQL (Supabase) và lưu trữ nội bộ bằng SQLite nhằm mục đích dự phòng (Dual-write / Fallback). 

## 1. Cơ sở Hạ tầng DB
- **PostgreSQL / Supabase:** Là cơ sở dữ liệu mặc định. Nó được tối ưu hóa cho AI thông qua extension `pgvector` giúp hỗ trợ truy vấn vector độ chính xác siêu tốc.
- **Connection Pooling:** Ứng dụng Backend kết nối thông qua **Supavisor Transaction Pooler (Cổng 6543)** và cấu hình `ThreadedConnectionPool` của `psycopg2`. Kiến trúc này giúp quản lý lên tới hàng nghìn kết nối đồng thời từ các thiết bị camera ở quy mô hơn 100 quán mà không bị nghẽn (Scale).

---

## 2. Các Bảng Dữ liệu Cốt lõi (Core Tables)

### Bảng `users`
Lưu trữ thông tin tài khoản dùng để đăng nhập vào trang quản trị (Admin Panel / Frontend).
- `id` (SERIAL PRIMARY KEY)
- `username` (VARCHAR)
- `password_hash` (VARCHAR): Mật khẩu được mã hóa SHA-256.
- `role` (VARCHAR): Phân quyền người dùng (`admin`, `moderator`).
- `cameras` (TEXT): Danh sách ID camera người dùng có thể truy cập (nếu có).
- `status` (VARCHAR): Trạng thái tài khoản (`active` / `disabled`).

### Bảng `cameras` và Kết nối thiết bị
Để đảm bảo một thiết bị camera Edge không bị đánh cắp luồng dữ liệu, hệ thống sử dụng Device Credentials.
- **`cameras`**: Lưu ID, tên hiển thị, trạng thái và thời gian "last seen" của Camera.
- **`camera_device_credentials`**: Chứa token (đã hash) lưu trên trình duyệt của Camera. Tokens này tự động được luân chuyển (rotate) khi đăng ký mới (Enrollment) hoặc tái kích hoạt.
- **`user_camera_permissions`**: Ghi nhận quyền truy cập chi tiết (view/edit) của từng Người dùng (User) đối với từng Camera.
- **`camera_connections`**: Ghi log lịch sử mở kết nối và ngắt kết nối của các Session Camera (cùng lý do ngắt).

### Bảng `customers`
Lưu trữ thông tin chi tiết của Khách Hàng và Khách Vãng Lai (Guest).
- `customer_id` (VARCHAR PRIMARY KEY): ID khách hàng (Bắt đầu bằng `GUEST_...` đối với người lạ, hoặc chuỗi số đối với khách quen).
- `name` (VARCHAR), `phone`, `email`
- `customer_type` (VARCHAR): Định danh là `registered` hoặc `guest`.
- `loyalty_tier` (VARCHAR): Hạng khách hàng (`Standard`, `VIP`, ...).
- `total_visits`, `last_visit`, `total_spending`: Dữ liệu phân tích (Analytics) của khách.
- `is_deleted` (BOOLEAN DEFAULT FALSE): Cờ đánh dấu khách hàng đã bị xóa (Soft Delete).

### Bảng `customer_embeddings` (Bảng Vector)
Lưu trữ Vector Đặc Trưng Sinh Trắc Học của khuôn mặt.
- Bảng này sử dụng công nghệ **Dual-Write** để tương thích mọi cấu hình DB:
  1. Trường `embedding` (Kiểu `vector(512)` của `pgvector`): Hỗ trợ đánh Index theo thuật toán **HNSW** (`halfvec_cosine_ops`), tốc độ tìm kiếm dưới <5ms.
  2. Trường `face_embedding` (Kiểu `BYTEA` nhị phân): Định dạng dự phòng khi hệ thống chuyển sang dùng SQLite.
- `is_deleted` (BOOLEAN DEFAULT FALSE): Cờ xóa mềm đồng bộ với bảng `customers`.
- AI Pipeline chỉ cần 1 trong 2 trường này để có thể phân tích độ tương đồng.

### Bảng `recognize_logs`
Bảng lưu trữ lịch sử nhận diện chi tiết (tới từng frame):
- `id` (UUID PRIMARY KEY)
- `opeid` (UUID): ID hoạt động để phân nhóm log.
- `camera_id` (VARCHAR)
- `customer_id` (VARCHAR): Khách hàng được nhận diện trong log.
- `track_id` (INTEGER): Phiên track tĩnh của AI worker.
- `bbox` (JSONB): Tọa độ khuôn mặt.
- `connection_id` (VARCHAR): ID của session WebSocket.
- `moderator_username` (VARCHAR): Tài khoản quản trị chi nhánh (Moderator) sở hữu camera, dùng để làm khóa Phân vùng bảng (Partition Key).

*Lưu ý: Bảng này được áp dụng cơ chế Phân vùng List (List Partitioning) theo cột `moderator_username` để cô lập dữ liệu và tối ưu hóa truy vấn cho từng cửa hàng.*

---

## 3. Kiến trúc Supabase Vector Search
- Hệ thống tạo index HNSW trên trường `embedding` của bảng `customer_embeddings`:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_customer_embeddings_hnsw_halfvec
  ON customer_embeddings
  USING hnsw ((embedding::halfvec) halfvec_cosine_ops)
  WITH (m = 32, ef_construction = 128);
  ```
- Kỹ thuật ép kiểu `halfvec` (Float16) giúp cắt giảm 50% dung lượng bộ nhớ trên RAM của Database, qua đó duy trì hiệu năng siêu tốc ngay cả khi lượng khách hàng lên tới hàng trăm ngàn record mà không làm giảm độ chính xác của mô hình EdgeFace.

---

## 4. Các Chiến lược Tối ưu hóa Cơ sở Dữ liệu

Hệ thống được thiết kế và cập nhật các kỹ thuật tối ưu hóa nhằm đảm bảo hiệu suất ở quy mô lớn:

1. **Gộp mẻ (Batch Operations & Upsert)**:
   - Các bản ghi nhận diện (`recognize_logs`) từ AI Worker được gom thành các batch nhỏ và ghi vào DB bằng một câu lệnh `INSERT` duy nhất thông qua hàm `psycopg2.extras.execute_values`.
   - Các thao tác cập nhật khách hàng (`customers`) sử dụng cú pháp `INSERT ... ON CONFLICT DO UPDATE` (Upsert), tránh vòng lặp đọc-kiểm tra-ghi.
2. **Phân vùng bảng (Table Partitioning)**:
   - Bảng `recognize_logs` được triển khai **List Partitioning** dựa trên tài khoản của `moderator`. Việc này giúp mỗi chi nhánh (moderator) có một phân vùng vật lý riêng, tăng tốc độ truy vấn và cho phép dễ dàng xóa log cũ bằng thao tác `DROP PARTITION`.
3. **Xóa mềm (Soft Delete) & Vacuum Tuning**:
   - Sử dụng cột `is_deleted` để thay thế hoàn toàn cho lệnh `DELETE` vật lý đối với dữ liệu của khách hàng.
   - Các bảng có tần suất ghi cao (như `recognize_logs` và `customer_embeddings`) được cấu hình tùy chỉnh **Autovacuum Tuning** (giảm `autovacuum_vacuum_scale_factor` xuống 5%) để ngăn ngừa phình (bloat) dữ liệu.
