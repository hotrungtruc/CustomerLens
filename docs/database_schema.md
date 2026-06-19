# Cấu trúc Cơ sở dữ liệu (Database Schema)

Hệ thống Face Recognition hỗ trợ cả **PostgreSQL (Supabase)** và **SQLite** (cho local testing). Cấu trúc bảng gần như giống hệt nhau, ngoại trừ bảng `customer_embeddings` trên PostgreSQL sử dụng extension `pgvector` để tìm kiếm tốc độ cao.

---

## 1. Bảng `users` (Tài khoản Quản trị)
Dùng để đăng nhập và phân quyền trên hệ thống.

| Cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính (Tự tăng) |
| `username` | VARCHAR(255) | Tên đăng nhập (Unique) |
| `password_hash`| VARCHAR(255) | Mật khẩu đã băm bằng SHA256 |
| `role` | VARCHAR(50) | Vai trò (VD: `admin`, `staff`) |
| `cameras` | TEXT | Danh sách ID camera được phép truy cập (cách nhau dấu phẩy) |

## 2. Bảng `customers` (Khách hàng)
Lưu trữ thông tin hồ sơ và thống kê lịch sử của khách hàng.

| Cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `customer_id` | VARCHAR(255) | Khóa chính (Chuỗi ID tự sinh hoặc nhập tay) |
| `name` | VARCHAR(255) | Tên khách hàng |
| `phone` | VARCHAR(50) | Số điện thoại (Tùy chọn) |
| `email` | VARCHAR(255) | Email (Tùy chọn) |
| `occupation` | VARCHAR(255) | Nghề nghiệp / Chuyên ngành |
| `registered_at`| VARCHAR(255) | Ngày/Năm đăng ký |
| `tenure` | INTEGER | Số năm sử dụng dịch vụ |
| `loyalty_tier` | VARCHAR(50) | Hạng thành viên (VD: Standard, VIP) |
| `total_visits` | INTEGER | Tổng số lần ghé thăm (Tự động tăng) |
| `last_visit` | VARCHAR(255) | Thời gian ghé thăm gần nhất |
| `total_spending`| REAL | Tổng chi tiêu (dựa trên hóa đơn) |
| `note` | TEXT | Ghi chú thêm |
| `customer_type`| VARCHAR(50) | `registered` hoặc `guest` |
| `status` | VARCHAR(50) | `active` hoặc `temporary` |
| `created_at` | VARCHAR(255) | Thời gian tạo |
| `updated_at` | VARCHAR(255) | Thời gian cập nhật |

## 3. Bảng `customer_embeddings` (Vector Khuôn mặt)
Đây là bảng quan trọng nhất cho AI, kết nối 1-nhiều với `customers`. Một khách hàng có thể có nhiều góc khuôn mặt (embeddings).

| Cột | Kiểu dữ liệu (PG/SQLite) | Mô tả |
| :--- | :--- | :--- |
| `id` | SERIAL / INTEGER | Khóa chính |
| `customer_id` | VARCHAR(255) | Khóa ngoại trỏ đến `customers.customer_id` |
| `face_embedding`| BYTEA / BLOB | Vector khuôn mặt dạng bytes thuần tủy (dùng khi fallback / tải local cache) |
| `embedding_dim`| INTEGER | Số chiều của vector (Mặc định: 512) |
| `model_name` | VARCHAR(100) | Tên model tạo vector (Mặc định: `w600k_mbf`) |
| **`embedding`** | **vector(512)** | *(Chỉ có trên PostgreSQL)* Dữ liệu vector cho pgvector, được lập chỉ mục (index) `HNSW` để so khớp bằng `vector_cosine_ops`. |

## 4. Các bảng Hóa Đơn & Sản Phẩm (Mở rộng)
Phần này dùng để hỗ trợ mô hình kinh doanh (Nhà hàng / Dịch vụ).

### 4.1. Bảng `products`
| Cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `product_id` | VARCHAR | Khóa chính |
| `name` | VARCHAR | Tên sản phẩm |
| `price` | REAL | Giá bán |
| `category` | VARCHAR | Danh mục |

### 4.2. Bảng `orders` & `order_items`
- `orders`: Lưu header hóa đơn (`order_id`, `customer_id`, `total_amount`, `status`).
- `order_items`: Lưu chi tiết (`order_item_id`, `order_id`, `product_id`, `quantity`, `subtotal`).

### 4.3. Bảng `table_bookings`
Lưu trữ thông tin đặt bàn/chỗ ngồi của khách hàng.
- (`booking_id`, `customer_id`, `table_number`, `booking_at`, `status`).

---
> [!TIP]
> Khi bảo trì: Hệ thống AI sử dụng cả `face_embedding` (BLOB) để đồng bộ (Sync) về bộ nhớ máy local (nếu dùng SQLite) và sử dụng `embedding` (vector) cho câu lệnh truy vấn SQL siêu tốc trên Cloud.
