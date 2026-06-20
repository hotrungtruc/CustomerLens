# Hướng dẫn Vận hành & Bảo trì (Maintenance Guide)

Tài liệu này cung cấp các bước cần thiết để vận hành dự án Front Door AI, từ khâu triển khai lên Server cho đến xử lý sự cố.

## 1. Triển khai Lên Server (Deployment)

Dự án sử dụng **Docker Compose** và **GitLab CI/CD** để thực thi Automation Deployment lên Máy chủ EC2 (AWS) hoặc các nhà cung cấp VPS khác.

### 1.1. Luồng CI/CD (GitLab)
Khi code được merge vào nhánh `main`:
1. **GitLab Runner** sẽ kích hoạt.
2. Thiết lập SSH bằng khóa riêng tư (`SSH_PRIVATE_KEY`) để truy cập thẳng vào Server EC2.
3. Kéo mã nguồn mới nhất (`git pull`).
4. Ghi đè tệp biến môi trường `.env` an toàn (Không commit thông tin này lên Git).
5. Chạy lệnh `docker compose up --build -d` để Rebuild container Backend mà **không gây Down-time**.

### 1.2. Môi trường Docker
File `docker-compose.yml` quy định giới hạn bộ nhớ (Resource Limits):
```yaml
mem_limit: 600m
mem_reservation: 300m
```
Điều này đảm bảo Backend (chạy Model AI nặng) không làm treo (OOM - Out Of Memory) hệ điều hành nếu chạy trên Server T3.Micro (1GB RAM).

---

## 2. Quản trị Vector & Database

### 2.1. Backfill Vector (Chuyển đổi Vector Cũ)
Nếu bạn nâng cấp hệ thống từ SQLite (sử dụng BLOB bytes) lên PostgreSQL (sử dụng `pgvector`), bạn cần chạy script sau một lần duy nhất:
```bash
# Đứng ở thư mục backend
python scripts/backfill_vectors.py
```
Script sẽ đọc tất cả các vector trong cột BYTEA và chèn lại vào cột `vector(512)` để lập chỉ mục tìm kiếm HNSW.

### 2.2. Migrate Ảnh Khách Hàng (Tùy chọn)
Nếu bạn muốn đưa ảnh local lên Supabase Storage CDN:
```bash
python scripts/migrate_images.py
```
Nó sẽ upload mọi file trong `data/images/` lên Supabase Storage bucket `customer-images`.

---

## 3. Xử lý Sự cố Thường gặp (Troubleshooting)

### 3.1. Lỗi Cạn kiệt Connection (Connection Pool Exhaustion)
- **Dấu hiệu:** Request báo `Timeout` hoặc Database Supabase báo số lượng Client connections chạm ngưỡng (VD: > 60).
- **Khắc phục:** 
  - Đảm bảo trong mã nguồn luôn sử dụng context manager `finally: conn.close()`. Backend đã dùng `ThreadedConnectionPool(min=2, max=10)`, kết nối sẽ được trả lại Pool khi `.close()` được gọi.

### 3.2. Không Nhận Diện Được Khách Cũ (Low Recall)
- **Dấu hiệu:** Một khách đã có tên nhưng hệ thống liên tục hiện hộp thoại `GUEST_...` màu cam.
- **Nguyên nhân:** Khách có thể đổi kính râm, hoặc vector mẫu trong Database chưa có góc mặt nghiêng đó.
- **Khắc phục:** Quản lý bấm vào GUEST đó trên giao diện và chọn `Promote` (Cập nhật hồ sơ) vào đúng khách cũ. Backend sẽ dùng thuật toán **Auto Merge** tự động cộng gộp (Average) vector mới vào hồ sơ để hệ thống khôn lên ở các lần sau.

### 3.3. Camera Bị Lag / Khung hình trễ (Latency)
- **Dấu hiệu:** Người đi qua cửa rồi mà 2 giây sau khung xanh mới hiện lên.
- **Nguyên nhân:** Có thể luồng AI bị kẹt (Bị blocking IO).
- **Khắc phục:** Đảm bảo `PROCESS_EVERY_N_FRAMES` (trong `backend/config.py`) được set phù hợp (VD: bằng 1 hoặc 2) và biến môi trường MKL (Intel Math Kernel Library) threads được config chuẩn ở Docker:
```env
OMP_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
MKL_NUM_THREADS=2
```
