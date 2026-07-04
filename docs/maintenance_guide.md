# Hướng dẫn Vận hành & Bảo trì (Maintenance Guide)

Tài liệu này cung cấp các bước cần thiết để vận hành dự án Front Door AI, từ khâu triển khai lên Server phân tán cho đến xử lý các sự cố thường gặp.

## 1. Triển khai Lên Server (Deployment)

Dự án sử dụng kiến trúc phân tán (Distributed Architecture) với **Docker Compose** và **GitLab CI/CD** để tự động hóa việc triển khai lên hệ thống cụm máy chủ (Master Node và các AI Worker Nodes).

### 1.1. Luồng CI/CD (GitLab)
Khi code được merge vào nhánh `main`:
1. **GitLab Runner** được kích hoạt.
2. Thiết lập SSH để truy cập vào cụm máy chủ (Bao gồm Master Node và các Worker Nodes).
3. Tự động kéo mã nguồn mới nhất (`git pull origin main`).
4. Rebuild các container (`backend` và `ai_worker`) mà **không gây Down-time** thông qua lệnh `docker compose build && docker compose up -d`.

### 1.2. Môi trường Docker và Resource Limits
Trong file `docker-compose.yml`, các service AI được cấu hình giới hạn tài nguyên để đảm bảo độ ổn định:
```yaml
mem_limit: 600m
mem_reservation: 300m
```
Điều này đảm bảo các tiến trình AI xử lý (vốn sử dụng CPU cường độ cao) không gây tình trạng thiếu bộ nhớ (Out Of Memory - OOM) cho hệ điều hành máy chủ.

---

## 2. Quản trị Vector & Database

### 2.1. Backfill Vector (Chuyển đổi Vector Cũ)
Nếu bạn nâng cấp hệ thống từ SQLite hoặc các phiên bản cũ lên PostgreSQL (`pgvector`), bạn cần chạy script sau một lần duy nhất:
```bash
# Đứng ở thư mục backend trên Master Node
python scripts/backfill_vectors.py
```
Script sẽ đọc tất cả các vector trong cột BYTEA cũ và chèn lại vào cột `vector(512)` để thiết lập chỉ mục tìm kiếm HNSW chính xác.

### 2.2. Migrate Ảnh Khách Hàng (Tùy chọn)
Nếu bạn muốn đồng bộ ảnh lưu nội bộ lên Supabase Storage CDN:
```bash
python scripts/migrate_images.py
```
Mọi file trong thư mục `data/images/` sẽ được upload lên Supabase Storage bucket `customer-images`.

---

## 3. Xử lý Sự cố Thường gặp (Troubleshooting)

### 3.1. Lỗi Mất Kết Nối WebSocket / Redis Disconnect
- **Dấu hiệu:** Màn hình giao diện Frontend hiện thông báo "Đang kết nối lại..." (Reconnecting) liên tục hoặc báo lỗi `RedisError`.
- **Nguyên nhân:** Cấu hình `REDIS_URL` trên Master Node hoặc Worker Node chưa chính xác, khiến các luồng Pub/Sub không thể giao tiếp.
- **Khắc phục:** 
  - Kiểm tra lại file `backend/.env` trên tất cả các node. Đảm bảo biến `REDIS_URL` phải trỏ đúng đến IP của Master Node (Ví dụ: `REDIS_URL=redis://15.134.121.250:6379/0`) thay vì `localhost`.
  - Khởi động lại các container: `sudo docker compose restart`.

### 3.2. Không Nhận Diện Được Khách Cũ (Low Recall)
- **Dấu hiệu:** Một khách đã đăng ký nhưng hệ thống liên tục hiện danh tính mới `GUEST_...` màu cam.
- **Nguyên nhân:** Khách có thể đổi góc mặt khó, đeo kính râm, hoặc vector mẫu trong CSDL ban đầu chưa có độ bao phủ đa dạng.
- **Khắc phục:** Quản lý có thể chọn GUEST đó trên giao diện và bấm `Promote` để gộp vào đúng khách cũ. Hệ thống có cơ chế **Auto Merge**, tự động lấy trung bình (Average) vector mới vào hồ sơ cũ để hệ thống "học" và nhận diện chuẩn hơn ở những lần sau.

### 3.3. Camera Bị Lag / Khung hình trễ (Latency)
- **Dấu hiệu:** Hình ảnh truyền về rất mượt, nhưng Bounding Box cập nhật rất chậm hoặc thỉnh thoảng biến mất. Số lượng người trên giao diện không cập nhật kịp thời.
- **Nguyên nhân:** Có thể số lượng AI Worker hiện tại không đủ đáp ứng số lượng người trong khung hình, dẫn đến tình trạng thắt cổ chai ở hàng đợi Redpanda (`camera_frames_v2`).
- **Cách khắc phục:**
  - Kiểm tra CPU usage của các Worker bằng lệnh `docker stats` hoặc `htop`.
  - Bật thêm các AI Worker (Thêm server Worker mới hoặc tăng số container trên các máy Worker hiện tại) để xử lý lượng tải lớn hơn. Hệ thống sẽ tự động cân bằng tải qua Kafka Consumer Group.
