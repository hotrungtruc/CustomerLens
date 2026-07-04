# Kiến trúc Frontend (Frontend Architecture)

Frontend của dự án Front Door AI được xây dựng hoàn toàn dựa trên **Next.js 14** (App Router), cung cấp giao diện trực quan cho cả Khách hàng và Quản trị viên để quản lý luồng Camera, Danh sách khách hàng, và Lịch sử nhận diện.

## 1. Cấu trúc Thư mục (App Router)

Toàn bộ Source Code Frontend nằm trong `frontend/src/app`. Dưới đây là các Route chính được thiết kế dựa trên kiến trúc file-based routing của Next.js:

- **/login**: Giao diện đăng nhập cho hệ thống quản trị, lấy Token trả về từ Backend.
- **/camera**: Cung cấp giao diện kết nối Webcam (hoặc các camera ngoại vi). Tích hợp MediaPipe để phát hiện khuôn mặt ngay trên trình duyệt (Edge Detection), tự động cắt (crop) ảnh khuôn mặt, và truyền Stream qua WebSocket với dung lượng siêu nhỏ. Tại đây, luồng "Observer" cũng được tích hợp để vẽ lên canvas các bounding box (Khung nhận diện).
- **/customers**: Giao diện CRM (Customer Relationship Management) quản lý thông tin các Khách hàng (Customers) và Khách vãng lai (Guests). Bao gồm tính năng Promote Guest (Chuyển khách vãng lai thành khách hàng chính thức).
- **/history**: Danh sách lịch sử điểm danh (Recognize Logs) dựa trên dữ liệu Backend trả về.
- **/reports**: Giao diện Phân tích số liệu (Analytics), báo cáo lượng Check-ins hàng ngày và thông kê các mức hạng khách (Loyalty Tiers).
- **/notifications** & **/settings**: Tùy chỉnh thông số hệ thống, độ nhạy của AI và nhận thông báo lỗi từ thiết bị.

## 2. Công nghệ Cốt lõi (Core Stack)

- **UI & Styling:** Sử dụng **Tailwind CSS** để thiết kế giao diện (Utility-first) và **Lucide React** cho hệ thống Icon đồng nhất, nhẹ, sắc nét.
- **State Management & Data Fetching:** Sử dụng hệ thống Hook của React kết hợp với WebSocket API tích hợp sẵn (Native `WebSocket`).
- **Edge AI (MediaPipe Vision):** Frontend tích hợp thư viện `@mediapipe/tasks-vision` chạy qua WebAssembly để thực hiện **Edge Tracking**. Trình duyệt tự cấp phát `local_track_id` và cắt (crop) chính xác phần khuôn mặt ra thành một ảnh JPEG nhỏ (10-20KB). Việc chuyển dịch tính toán Face Detection xuống Edge giúp tối ưu đáng kể băng thông mạng và năng lực xử lý của máy chủ.

## 3. Quản lý Quyền Truy cập (RBAC)

Frontend áp dụng Role-Based Access Control thông qua Wrapper Components (Layouts):
- Trạng thái phiên (Session State) được duy trì bằng `JWT` (hoặc Session Token truyền thống) ở Local Storage / Cookies.
- Nếu một User có role `moderator`, hệ thống sẽ chặn các hành động xóa thiết bị hoặc sửa đổi sâu vào cấu hình hệ thống (Settings), vốn chỉ dành cho quyền `admin`.
- Các Route được bảo vệ (Protected Routes) thông qua Next.js Middleware hoặc logic Layout cấp cao: Bất kỳ ai không có Token hợp lệ đều bị điều hướng (Redirect) thẳng về route `/login`.

## 4. Tương tác với Luồng WebSocket

### Gửi Khung Hình Tối Ưu (Edge Crop)
Để tiết kiệm tối đa băng thông và giảm độ trễ, Frontend thực hiện:
1. **Local Face Detection:** Sử dụng MediaPipe dò tìm khuôn mặt liên tục ở 30-60 FPS.
2. **Crop & Compress:** Khi phát hiện khuôn mặt, thay vì gửi toàn bộ khung hình Full HD, trình duyệt dùng `<canvas>` để cắt (crop) riêng phần bounding box khuôn mặt, nén thành JPEG (khoảng 10-20KB).
3. **Transmission:** Gửi ảnh crop kèm `local_track_id` qua WebSocket lên API Gateway (FastAPI) định kỳ (ví dụ 1 lần/giây). Hệ thống Backend (AI Worker) chỉ việc trích xuất vector (Embedding) và trả về kết quả định danh cho `local_track_id` đó. Mọi thao tác vẽ UI (Bounding box) tiếp tục được thực hiện tại Frontend mà không bị lag.
