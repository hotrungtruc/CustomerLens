# Cấu trúc Cơ sở dữ liệu (Database Schema)

Hệ thống hoạt động mượt mà trên môi trường Production sử dụng **Supabase PostgreSQL**. Các bảng được thiết kế để chuẩn hóa thông tin khách hàng, nhật ký ra vào và bảo toàn các vector đặc trưng để tối ưu hóa việc định danh (Face Recognition).

Điểm nổi bật trong kiến trúc này là việc áp dụng **pgvector**, extension hỗ trợ lưu trữ vector nhúng của AI và truy vấn K-Nearest Neighbors (KNN) siêu tốc với chỉ mục HNSW.

---

## 1. Bảng `users` (Tài khoản & Phân quyền)
Lưu thông tin đăng nhập và Role-Based Access Control (RBAC).

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính (Tự tăng) |
| `username` | VARCHAR(255) | Tên đăng nhập (Unique) |
| `password_hash`| VARCHAR(255) | Mật khẩu (SHA-256 Hash) |
| `role` | VARCHAR(50) | Vai trò (`admin`, `moderator`, `guest`) |
| `cameras` | TEXT | Danh sách ID camera được phép truy cập (VD: `cam_01,cam_02`) |

---

## 2. Bảng `customers` (Hồ sơ Khách hàng)
Trung tâm lưu trữ thông tin định danh của người dùng trong hệ thống (Khách hàng chính thức, Khách vãng lai).

| Column | Type | Description |
| :--- | :--- | :--- |
| `customer_id` | VARCHAR(255) | Khóa chính (Tự tạo hoặc sinh tự động với tiền tố `CUS_` / `GUEST_`) |
| `name` | VARCHAR(255) | Tên khách hàng |
| `phone` | VARCHAR(50) | Số điện thoại liên hệ |
| `status` | VARCHAR(50) | Trạng thái (`active`, `temporary`) |
| `customer_type`| VARCHAR(50) | Phân loại (`registered` - Đã đăng ký, `guest` - Khách vãng lai) |
| `loyalty_tier` | VARCHAR(50) | Hạng thẻ (Standard, VIP, Platinum) |
| `total_attendance`| INTEGER | Tổng số lượt ghé thăm (Tự tăng khi ghi nhận Check-in) |
| `last_attendance_time`| VARCHAR | Timestamp lần cuối hệ thống nhận diện thành công |
| `note` | TEXT | Ghi chú của nhân sự |

*(Hệ thống thiết kế theo hướng mở, hỗ trợ dễ dàng thêm các trường mở rộng phục vụ cho các domain nghiệp vụ khác nhau).*

---

## 3. Bảng `customer_embeddings` (Vector Đặc Trưng Khuôn Mặt)
Bảng kết nối 1-Nhiều với bảng `customers`. Một định danh có thể có nhiều góc mặt, điều kiện ánh sáng khác nhau để cải thiện độ chính xác (Face Bank).

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính |
| `customer_id` | VARCHAR(255) | Khóa ngoại (Foreign Key) trỏ về `customers(customer_id)`. Xóa Cascade. |
| `embedding_dim`| INTEGER | Chiều của vector (Mặc định: 512) |
| `model_name` | VARCHAR(100) | Tên mô hình tạo vector (Mặc định: `edgeface_s_gamma_05`) |
| `face_embedding`| BYTEA | Bản sao nhị phân (Binary Blob) lưu giữ raw bytes. |
| **`embedding`** | **vector(512)** | Cột của `pgvector`. **Có Index HNSW**. Dùng để tính Cosine Similarity (`<=>`). |

**Tối ưu Index HNSW:**
```sql
CREATE INDEX IF NOT EXISTS customer_embeddings_hnsw_idx 
ON customer_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**Asynchronous Inserts:**
Khi phát hiện khách vãng lai mới, API Backend không bắt luồng xử lý chính phải chờ CSDL phản hồi. Việc thêm (Insert) bản ghi vào bảng `customers` và `customer_embeddings` được đẩy vào Thread phụ bất đồng bộ (`asyncio.create_task`), giúp hiệu năng của WebSocket không bị gián đoạn.

---

## 4. Bảng `attendance` (Nhật ký Ra Vào)
Ghi nhận mọi lượt check-in của hệ thống, hỗ trợ trích xuất báo cáo. Để tránh spam (nhiều bản ghi trong cùng một khoảnh khắc), hệ thống áp dụng cơ chế **Cooldown Caching** ở tầng Backend.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính |
| `customer_id` | VARCHAR(255) | Khóa ngoại trỏ đến `customers` |
| `timestamp` | VARCHAR(255) | Giờ check-in chính xác |
| `visit_date` | VARCHAR(50) | Ngày check-in (Phục vụ truy vấn thống kê Group By) |

---

## 5. Kiến trúc Storage (Supabase Storage)
Hình ảnh profile của người dùng được tải lên thông qua **Supabase Storage REST API** (hoặc client `supabase-js`).
- **Bucket:** `customer-images` (Public).
- **Quy tắc ghi:** Sử dụng `{customer_id}.jpg` để ghi đè (Upsert), tiết kiệm không gian lưu trữ và đảm bảo mỗi người dùng chỉ có 1 ảnh đại diện nhất quán.
- Ảnh Upload dạng Base64 được xử lý bởi thư viện backend và trả về CDN URL (Public URL) cho Frontend. Trong trường hợp gián đoạn kết nối Cloud, hệ thống hỗ trợ chiến lược Fallback lưu ảnh tại ổ cứng Local (`data/images`).
