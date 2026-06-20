# Cấu trúc Cơ sở dữ liệu (Database Schema)

Hệ thống hoạt động mượt mà trên môi trường Production sử dụng **Supabase PostgreSQL**. Các bảng được thiết kế để chuẩn hóa thông tin khách hàng, nhật ký ra vào và dữ liệu phân quyền.

Đặc biệt nhất là việc áp dụng **pgvector**, extension hỗ trợ lưu trữ vector nhúng của AI và truy vấn K-Nearest Neighbors siêu tốc.

---

## 1. Bảng `users` (Tài khoản & Phân quyền)
Lưu thông tin đăng nhập và Role-Based Access Control (RBAC).

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính (Tự tăng) |
| `username` | VARCHAR(255) | Tên đăng nhập (Unique) |
| `password_hash`| VARCHAR(255) | Mật khẩu (SHA-256 Hash) |
| `role` | VARCHAR(50) | Vai trò (`admin`, `moderator`, `guest`) |
| `cameras` | TEXT | Danh sách ID camera được phép (VD: `cam_01,cam_02`) |

---

## 2. Bảng `customers` (Hồ sơ Khách hàng)
Trung tâm lưu trữ thông tin của người dùng trong hệ thống (Hội viên, Khách vãng lai).

| Column | Type | Description |
| :--- | :--- | :--- |
| `customer_id` | VARCHAR(255) | Khóa chính (Tự tạo hoặc tự động sinh với tiền tố `CUS_` / `GUEST_`) |
| `name` | VARCHAR(255) | Tên khách hàng |
| `phone` | VARCHAR(50) | Số điện thoại |
| `status` | VARCHAR(50) | Trạng thái (`active`, `temporary`) |
| `customer_type`| VARCHAR(50) | Loại (`registered` - Đã đăng ký, `guest` - Vãng lai) |
| `loyalty_tier` | VARCHAR(50) | Hạng thẻ (Standard, VIP, Platinum) |
| `total_attendance`| INTEGER | Tổng số lượt ghé thăm (Tự tăng khi Check-in) |
| `last_attendance_time`| VARCHAR | Timestamp lần cuối ghé thăm |
| `note` | TEXT | Ghi chú của nhân viên |

*(Có hỗ trợ các trường mở rộng như `service_category`, `major`, `year`... phục vụ cho các domain nhà hàng / trường học khác nhau).*

---

## 3. Bảng `customer_embeddings` (Vector Khuôn Mặt - Quan trọng)
Bảng kết nối 1-Nhiều với `customers`. Một người có thể có nhiều góc mặt, điều kiện ánh sáng khác nhau (Face Bank).

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính |
| `customer_id` | VARCHAR(255) | Khóa ngoại trỏ về `customers(customer_id)` |
| `embedding_dim`| INTEGER | Chiều của vector (Mặc định: 512) |
| `model_name` | VARCHAR(100) | Tên model tạo vector (VD: `ghostface_int8`) |
| `face_embedding`| BYTEA | Bản sao nhị phân (Binary Blob) dùng để đồng bộ Offline. |
| **`embedding`** | **vector(512)** | Cột của `pgvector`. **Có Index HNSW**. Dùng để tính Cosine Similarity (`<=>`) siêu nhanh. |

**Chỉ mục (Index):**
```sql
CREATE INDEX IF NOT EXISTS customer_embeddings_hnsw_idx 
ON customer_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

## 4. Bảng `attendance` (Nhật ký Ra Vào)
Ghi nhận mọi lượt check-in của hệ thống, phục vụ trích xuất báo cáo.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính |
| `customer_id` | VARCHAR(255) | Khóa ngoại |
| `timestamp` | VARCHAR(255) | Giờ check-in chính xác |
| `visit_date` | VARCHAR(50) | Ngày check-in (Phục vụ gom nhóm Group By thống kê) |

---

## 5. Kiến trúc Storage (Supabase Storage)
Hình ảnh profile của người dùng được tải lên thông qua **Supabase Storage REST API** (hoặc `supabase-js`).
- **Bucket:** `customer-images` (Public).
- **Quy tắc ghi:** Sử dụng `customer_id.jpg` để ghi đè (Upsert), tiết kiệm dung lượng.
- Ảnh Base64 được xử lý bởi `app/db/supabase_storage.py` và trả về URL CDN (Public URL) cho Frontend. Mất kết nối Cloud sẽ Fallback về ổ cứng Local (`data/images`).
