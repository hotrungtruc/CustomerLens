# Kiến trúc Hệ thống (System Architecture)

Tài liệu này cung cấp cái nhìn tổng quan về kiến trúc của hệ thống nhận diện khuôn mặt, các thành phần chính và luồng xử lý dữ liệu.

## 1. Tổng quan các Thành phần (Components)

Hệ thống được chia làm hai phần chính:
- **Frontend (Giao diện người dùng):** Xây dựng bằng Next.js (React) và TailwindCSS.
- **Backend (Xử lý logic & AI):** Xây dựng bằng FastAPI (Python), sử dụng OpenCV để xử lý video và InsightFace/ONNX để nhận diện khuôn mặt.
- **Database (Lưu trữ):** Hỗ trợ môi trường Cloud (Supabase PostgreSQL + pgvector) hoặc môi trường Local (SQLite).

---

## 2. Luồng xử lý Nhận diện Khuôn mặt (Face Recognition Pipeline)

Để đảm bảo hiệu năng và không làm block (nghẽn) API server, quá trình nhận diện được chia làm các luồng bất đồng bộ:

1. **Camera Feed:** 
   - Backend kết nối tới Camera (RTSP hoặc Webcam USB) qua OpenCV (`cv2.VideoCapture`).
   - Frame hình ảnh liên tục được gửi tới Frontend qua WebSocket (`/ws/camera/{camera_id}`) dưới dạng base64 JPEG.
2. **AI Processing Thread (Luồng AI độc lập):**
   - Có một luồng độc lập (`start_ai_loop` trong `CameraState`) chạy ngầm, lấy frame mới nhất từ `SharedFrameManager`.
   - **Detection (Phát hiện khuôn mặt):** Sử dụng model nhận diện (SCRFD) để tìm bounding box (tọa độ khuôn mặt).
   - **Tracking & Embedding (Theo dõi & Trích xuất đặc trưng):** Khuôn mặt được theo dõi qua nhiều frame (tracking) bằng thuật toán IOU. Khi khuôn mặt đạt đủ chất lượng (độ phân giải, độ tin cậy), model (AdaFace/GhostFace) sẽ trích xuất vector đặc trưng (Embedding 512 chiều).
3. **Matching (So khớp):**
   - Vector đặc trưng được so sánh với CSDL.
   - Nếu dùng Supabase: Dùng `pgvector` HNSW index qua hàm `vector_cosine_ops` để tìm kiếm siêu tốc.
   - Nếu dùng Local: Tính khoảng cách Cosine Similarity trong RAM qua NumPy.
4. **Kết quả:** 
   - ID khách hàng được phát hiện sẽ được cập nhật vào `SharedFrameManager` và gửi về Frontend qua API hoặc báo động sự kiện trên màn hình.

---

## 3. Kiến trúc CSDL & Lưu trữ (Storage Architecture)

Hệ thống hỗ trợ 2 chế độ vận hành (được điều khiển bởi biến `USE_SUPABASE` trong `.env`):

### 3.1. Chế độ Cloud (Production - Khuyên dùng)
- **Database:** PostgreSQL (trên Supabase). Bảng `customer_embeddings` sử dụng extension `pgvector` để lưu trữ và tìm kiếm nearest-neighbor (KNN) với HNSW Index. (Không lưu trữ ảnh, chỉ lưu vector).

### 3.2. Chế độ Local (Development/Edge)
- **Database:** SQLite (`data/database/production.db`). So khớp vector được thực hiện trong bộ nhớ (RAM) thông qua `numpy`.

---

## 4. Bảo mật (Security & Auth)
- Hệ thống có tích hợp Role-based Access Control (RBAC). 
- Người dùng đăng nhập qua `/api/login`, nhận lại token phiên bản (Session Token) được lưu trong bộ nhớ tạm `ACTIVE_SESSIONS` (hoặc có thể mở rộng qua Redis).
- Các request nhạy cảm cần truyền token qua Header `Authorization`.

## 5. Sơ đồ Luồng dữ liệu (Data Flow Diagram)

```mermaid
graph TD
    A[Camera/Video Stream] -->|Frames| B(FastAPI: CameraState)
    B -->|WebSocket base64| C[Next.js Frontend]
    B -->|SharedFrameManager| D(AI Thread: Detection & Tracking)
    D -->|Extract Vector| E{So khớp (Matching)}
    E -->|pgvector/HNSW| F[(Supabase PostgreSQL)]
    E -->|NumPy Cosine| G[(SQLite Local)]
    C -->|REST API| J[FastAPI: Routes]
    J --> F
    J --> G
```
