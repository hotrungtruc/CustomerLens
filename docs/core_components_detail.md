# Các Thành phần Cốt lõi (Core Components Detail)

Tài liệu này giải thích chi tiết mức mã nguồn (Low-level Code) cho các kỹ sư phát triển Hệ thống Nhận diện Khuôn mặt, giúp nhanh chóng nắm bắt các module phức tạp nhất trong kiến trúc Backend.

## 1. Module Tracking: `guest_tracking.py`
Nhiệm vụ của `GuestTrackManager` là ánh xạ sự tồn tại của 1 khuôn mặt qua hàng loạt khung hình (frames) liên tiếp, dù người đó đang di chuyển hay thay đổi biểu cảm.

### 1.1 `KalmanFilterCorner`
Sử dụng **Constant Velocity Kalman Filter** cho 4 điểm neo của bounding box (`x1, y1, x2, y2`). Thay vì tracking trung tâm hình chữ nhật, việc tracking 4 góc mang lại độ chính xác cao hơn khi khuôn mặt phóng to/thu nhỏ nhanh chóng do tiến lại gần camera.
- State vector: Chứa 8 giá trị bao gồm tọa độ và vận tốc của 4 góc `[x1, y1, x2, y2, vx1, vy1, vx2, vy2]`.
- Hàm `predict()` ước tính vị trí ở frame tương lai.
- Hàm `update()` điều chỉnh dự đoán thông qua thông tin phát hiện thực tế.

### 1.2. Tính toán IOU & Tránh Xung Đột
Để liên kết các Bounding Box từ frame cũ và mới, hệ thống sử dụng thuật toán tính tỉ lệ giao nhau `bbox_iou()`. Kết hợp với thư viện `scipy.optimize.linear_sum_assignment` (Thuật toán Hungarian), AI có thể xử lý việc gán nhiều mặt trong cùng khung hình một cách tối ưu, tránh tình trạng hai Tracking Box đổi ID cho nhau.

### 1.3. Tính toán `Robust Mean Embedding`
Khuôn mặt biến đổi theo góc quay, do vậy hệ thống lưu giữ lịch sử nhiều vector của cùng một Track. 
- Hàm `calculate_robust_mean_embedding(embeddings)` tính ma trận Cosine Similarity chéo giữa tất cả vector đang có. 
- Loại bỏ các vector có điểm Median Similarity thấp (<0.6). Những vector này thường là nhiễu (khi người khác đi lướt qua), đảm bảo **Trung bình đặc trưng** (Mean Embedding) cực kỳ thuần khiết trước khi mang đi tìm kiếm (HNSW).

## 2. Module Trích xuất: `insight_embedding.py`
Sử dụng lớp `InsightEmbedder` để bọc các model Deep Learning với hiệu năng tốt ưu nhất bằng ONNX.

### 2.1 MediaPipe Tasks API
Thực hiện quá trình **Face Detection** và **Landmark Extraction** (5 điểm). 
- Được cấu hình bằng `BaseOptions` để chạy mô hình `blaze_face_short_range.tflite` (Hoặc model mặc định tích hợp).
- Code có xử lý phân tích ma trận affine (`estimate_norm`) để canh chỉnh góc mặt (Alignment) thẳng trước khi cắt ảnh crop 112x112 cho mô hình nhúng.

### 2.2 ONNX Runtime & EdgeFace
- Khởi tạo session với `ExecutionMode.ORT_SEQUENTIAL` và phân mảnh luồng `intra_op_num_threads = 2` để tối ưu hóa đặc thù trên phần cứng máy chủ AWS T3 hoặc các dòng CPU có số lượng lõi hạn chế.
- Cơ chế Fallback: Cố gắng load phiên bản lượng tử hóa (`int8`), nếu phần cứng báo lỗi `NotImplemented`, code tự động catch Exception và fallback sang bản `float32`.
- Hàm `get_batch_embeddings`: Xử lý mảng ảnh (Batch Processing). Bằng cách nhóm n khuôn mặt vào chung 1 Tensor duy nhất thay vì lặp qua từng mặt, tốc độ xử lý tổng thể của Worker tăng lên theo cấp số nhân.

## 3. Quản trị Phiên WebSocket: `routes.py`
WebSocket là trạng thái kết nối 2 chiều nhưng rất dễ bị đứt gãy (Zombie connections). Backend áp dụng chặt chẽ cơ chế **Lease Management** trên Redis:

- **LUA Script (`RENEW_CAMERA_LEASE_SCRIPT` & `TAKEOVER_CAMERA_LEASE_SCRIPT`):** Đảm bảo tính nhất quán (Atomic). Khi một connection yêu cầu "Renew", Redis đảm bảo chỉ có Connection sở hữu Lease (chìa khóa) hiện tại mới được phép gia hạn thêm `CAMERA_PRESENCE_TTL_SECONDS`.
- Background task `_maintain_camera_lease`: Liên tục chạy ngầm trong suốt vòng đời WebSocket. Nếu Server sập hoặc mạng đứt, Redis sẽ tự động thu hồi Lease, giải phóng Camera ID cho một kết nối mới phục hồi (Takeover).
- **Xác thực JWT Mã hóa Bất đối xứng (RS256):** Thay thế biến lưu trữ RAM nội bộ bằng mã hóa JWT với cặp khóa RSA 2048-bit (`JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY`). Token được ký bằng khóa riêng tư tại API Gateway và được giải mã, xác thực chữ ký tức thì (Stateless) bằng khóa công khai tại mọi instance API và WebSocket Observer không qua DB hay RAM.

## 4. Module Vector DB: `vector_search.py` & `connection.py`
- **Native pgvector Parameter Binding (`pgvector.psycopg2`):** Đã nâng cấp từ chuỗi SQL string thủ công sang cơ chế đăng ký adapter `register_vector` native. Cho phép tham số NumPy `ndarray` (float32) được truyền thẳng dưới dạng Binary Protocol sang PostgreSQL `vector` data type, loại bỏ chi phí format chuỗi SQL trên CPU và đảm bảo hiệu năng tìm kiếm HNSW dưới <5ms.
