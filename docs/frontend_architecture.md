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
- **Edge AI (MediaPipe Vision):** Frontend có tích hợp `@mediapipe/tasks-vision` để hỗ trợ một số logic tiện ích như vẽ Bounding Box / Landmark siêu nhẹ phía máy khách (Client-side Rendering), giảm tải quá trình Render từ ảnh nhận về thành lớp vẽ Canvas tĩnh để không làm gián đoạn UX.

## 3. Quản lý Quyền Truy cập (RBAC)

Frontend áp dụng Role-Based Access Control thông qua Wrapper Components (Layouts):
- Trạng thái phiên (Session State) được duy trì bằng `JWT` (hoặc Session Token truyền thống) ở Local Storage / Cookies.
- Nếu một User có role `moderator`, hệ thống sẽ chặn các hành động xóa thiết bị hoặc sửa đổi sâu vào cấu hình hệ thống (Settings), vốn chỉ dành cho quyền `admin`.
- Các Route được bảo vệ (Protected Routes) thông qua Next.js Middleware hoặc logic Layout cấp cao: Bất kỳ ai không có Token hợp lệ đều bị điều hướng (Redirect) thẳng về route `/login`.

## 4. Tương tác với Luồng WebSocket

### Canvas Rendering
Để tránh tình trạng "giật lag" (Jitter) khi luồng mạng yếu, Frontend áp dụng kỹ thuật sau:
1. **Camera Frame:** Vẽ thẳng (Draw) ảnh thu được từ thiết bị vào thẻ `<canvas>`.
2. **AI Results:** WebSocket Server trả về mảng Bounding Box + Metadata (Tên, ID). Lớp dữ liệu này được vẽ (Render) đè lên `<canvas>` dưới dạng lớp phủ (Overlay). 
Kết quả: Tốc độ khung hình mượt mà, Bounding Box luôn đi liền với khuôn mặt.
