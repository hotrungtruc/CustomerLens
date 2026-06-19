# Hướng dẫn Vận hành & Bảo trì (Maintenance Guide)

Tài liệu này hướng dẫn cách thiết lập, bảo trì, và xử lý các sự cố thường gặp của hệ thống Face Recognition.

---

## 1. Cấu hình Môi trường (.env)

Mọi cấu hình quan trọng của Backend nằm trong file `backend/.env`. Bạn cần tạo file này nếu chưa có.

```env
# Đặt thành true để dùng PostgreSQL (Supabase) + pgvector, false để dùng SQLite
USE_SUPABASE=true

# Thông tin Database (PostgreSQL)
SUPABASE_URL=postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres

```

## 2. Các Script Bảo trì (Maintenance Scripts)

Các file chạy bảo trì nằm trong thư mục `backend/scripts/` và `backend/`. Bạn có thể chạy chúng từ thư mục gốc `backend/`.

### 2.1. Khởi tạo Database
**Khi nào cần:** Khi mới setup server lần đầu, hoặc sau khi đổi từ SQLite sang Supabase.
```bash
python -m app.db.connection
```
Lệnh này sẽ tạo các bảng (tables) còn thiếu và tự động cài extension `vector` trên PostgreSQL.

### 2.2. Chuyển đổi dữ liệu cũ (Migration)
Nếu bạn có dữ liệu cũ ở bản cập nhật trước, hãy chạy các lệnh sau:


- **Tạo Vector (pgvector) từ dữ liệu kiểu cũ (BYTEA):**
  ```bash
  python scripts/backfill_vectors.py
  ```
  *(Rất quan trọng nếu hệ thống nhận diện khuôn mặt tìm kiếm bị sai lệch, lệnh này sẽ format lại các vector cho chuẩn).*

- **Dọn dẹp và đồng bộ:**
  ```bash
  python deduplicate_and_sync.py
  ```
  *(Dùng để làm sạch các khách hàng trùng lặp hoặc guest rác sinh ra trong quá trình nhận diện lỗi).*

---

## 3. Xử lý Lỗi thường gặp (Troubleshooting)

### 3.1. Lỗi `ModuleNotFoundError: No module named 'psycopg2'`
- **Nguyên nhân:** Chưa cài đặt thư viện kết nối PostgreSQL cho Python sau khi pull code mới (có tính năng Supabase).
- **Cách sửa:** Chạy lệnh `pip install -r requirements.txt` trong thư mục `backend/`.

### 3.2. Không lên hình Camera
- **Nguyên nhân:** Backend đọc sai ID camera mặc định (ví dụ laptop có 2 camera).
- **Cách sửa:** Mở `backend/config.py`, tìm dòng `CAMERA_INDEX = 1` và đổi thành `0` hoặc `2` rồi khởi động lại backend.

### 3.3. Tốc độ nhận diện bị chậm
- **Nguyên nhân:** Khung hình camera đẩy vào AI xử lý quá nhanh làm CPU bị nghẽn. Hoặc do DB chứa quá nhiều khuôn mặt chưa được index.
- **Cách sửa:** 
  1. Kiểm tra lại index HNSW trong Supabase (`docs/database_schema.md`).
  2. Tăng tham số `PROCESS_EVERY_N_FRAMES` trong `config.py` từ `3` lên `5` để giảm tải cho CPU (bỏ qua bớt khung hình).

