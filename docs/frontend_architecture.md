# Kiến trúc Frontend (Frontend Architecture)

Frontend của dự án Front Door AI được xây dựng hoàn toàn dựa trên **Next.js 14** (App Router), cung cấp giao diện trực quan cho cả Khách hàng và Quản trị viên để quản lý luồng Camera, Danh sách khách hàng, và Lịch sử nhận diện.

## 1. Cấu trúc Thư mục (App Router)

Toàn bộ Source Code Frontend nằm trong `frontend/src/app`. Dưới đây là các Route chính được thiết kế dựa trên kiến trúc file-based routing của Next.js:

- **/login**: Giao diện đăng nhập cho hệ thống quản trị, lấy Token trả về từ Backend.
- **/camera**: Cung cấp giao diện kết nối Webcam (hoặc các camera ngoại vi), xử lý nén luồng hình ảnh và truyền Stream qua WebSocket. Tại đây, luồng "Observer" cũng được tích hợp để vẽ lên canvas các bounding box (Khung nhận diện).
- **/customers**: Giao diện CRM (Customer Relationship Management) quản lý thông tin các Khách hàng (Customers) và Khách vãng lai (Guests). Bao gồm tính năng Promote Guest (Chuyển khách vãng lai thành khách hàng chính thức).
- **/history**: Danh sách lịch sử điểm danh (Recognize Logs) dựa trên dữ liệu Backend trả về.
- **/reports**: Giao diện Phân tích số liệu (Analytics), báo cáo lượng Check-ins hàng ngày và thông kê các mức hạng khách (Loyalty Tiers).
- **/notifications** & **/settings**: Tùy chỉnh thông số hệ thống, độ nhạy của AI và nhận thông báo lỗi từ thiết bị.

## 2. Công nghệ Cốt lõi (Core Stack)

- **UI & Styling:** Sử dụng **Tailwind CSS** để thiết kế giao diện (Utility-first) và **Lucide React** cho hệ thống Icon đồng nhất, nhẹ, sắc nét.
- **State Management & Data Fetching:** Sử dụng hệ thống Hook của React kết hợp với WebSocket API tích hợp sẵn (Native `WebSocket`).
- **Edge AI (MediaPipe Vision) & Hybrid Tracking:** Frontend có tích hợp `@mediapipe/tasks-vision` (BlazeFace Short Range) để xử lý phân tích hình ảnh siêu nhẹ phía máy khách (Client-side Rendering). Hệ thống áp dụng **Bộ lọc 4 lớp (Strict Face Filtering)** ngay tại trình duyệt để "làm sạch" dữ liệu trước khi gửi lên Server:
  1. **Lọc theo độ tự tin (Confidence > 40%):** Loại bỏ các khuôn mặt ảo giác do AI dự đoán mò (thường là gáy, tai hoặc vật thể giống mặt). Ngưỡng 40% đã được cân chỉnh để nhận diện tốt qua màn hình/ảnh in.
  2. **Lọc theo góc nghiêng (Yaw Ratio):** Tính toán tỷ lệ khoảng cách từ đỉnh mũi tới hai mắt (giới hạn lệch 1.8 lần) để từ chối các ảnh nghiêng quá mức.
  3. **Lọc theo độ rộng (Inter-Ocular Distance):** Đo khoảng cách giữa 2 mắt (phải > 20% khung mặt) để loại bỏ góc quay ngang hoàn toàn 90 độ.
  4. **Lọc ảnh mờ (Laplacian Variance):** Đo phương sai của cường độ pixel. Các khung hình bị mờ do rung lắc hoặc thiếu sáng (Variance < 15) sẽ tự động bị loại bỏ.
  Nhờ bộ lọc Edge AI này, Backend giảm tải được một lượng lớn ảnh rác, giúp tăng tốc độ xử lý và đảm bảo chất lượng sinh ra Vector định danh. Frontend chỉ việc crop khuôn mặt ra (padding 25%) và gửi Edge Crop qua WebSocket, còn việc trích xuất Landmark độ phân giải cao sẽ giao cho SCRFD ở Backend.

## 3. Quản lý Quyền Truy cập (RBAC)

Frontend áp dụng Role-Based Access Control thông qua Wrapper Components (Layouts):
- Trạng thái phiên (Session State) được duy trì bằng `JWT` (hoặc Session Token truyền thống) ở Local Storage / Cookies.
- Nếu một User có role `moderator`, hệ thống sẽ chặn các hành động xóa thiết bị hoặc sửa đổi sâu vào cấu hình hệ thống (Settings), vốn chỉ dành cho quyền `admin`.
- Các Route được bảo vệ (Protected Routes) thông qua Next.js Middleware hoặc logic Layout cấp cao: Bất kỳ ai không có Token hợp lệ đều bị điều hướng (Redirect) thẳng về route `/login`.

## 4. Tương tác với Luồng WebSocket

### Canvas Rendering & Dynamic Cropping
Để tránh tình trạng "giật lag" (Jitter) khi luồng mạng yếu, Frontend áp dụng kỹ thuật sau:
1. **Camera Frame:** Vẽ thẳng (Draw) ảnh thu được từ thiết bị vào thẻ `<video>`.
2. **AI Results:** Dữ liệu Bounding Box từ MediaPipe được lưu dưới dạng trạng thái (state).
3. **Dynamic Canvas Cropping:** Khi đến lượt gửi ảnh, Frontend tạo một thẻ `<canvas>` tạm trong bộ nhớ (In-memory canvas), crop đúng khu vực khuôn mặt trên video, và chuyển đổi thành nhị phân. Bằng cách dùng canvas động, nhiều luồng crop có thể diễn ra song song độc lập với nhau, không bị hiện tượng Race Condition.
4. **WebSocket Binary Transport:** Mảng Byte Array được ghép thêm một header chứa `local_track_id` và kích thước bounding box để Worker phân loại.
Kết quả: Tốc độ khung hình mượt mà, Bounding Box luôn đi liền với khuôn mặt.
