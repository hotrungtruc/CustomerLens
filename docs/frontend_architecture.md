# Kiến trúc Frontend (Frontend Architecture)

Frontend của Front Door AI được xây dựng với các tiêu chí: **Hiển thị Thời gian thực (Real-time)**, **Bảo mật phân quyền (RBAC)**, và **Tối ưu hóa Trải nghiệm Người dùng (UX)** sử dụng ngôn ngữ thiết kế Glassmorphism hiện đại.

## 1. Công nghệ Sử dụng
- **Framework:** Next.js 14 (App Router)
- **Styling:** Tailwind CSS (Tích hợp Glassmorphism, CSS Transitions)
- **State Management:** React Hooks (`useState`, `useRef`, `useCallback`), `sessionStorage` (lưu trữ cache tạm thời).
- **Giao tiếp Dữ liệu:** WebSocket (Realtime Video Streaming & Data), Fetch API (REST CRUD).

---

## 2. Quản lý Kết nối Camera (Camera Stream)
**Hook `useCamera.js`**
Đây là module cốt lõi chịu trách nhiệm giao tiếp giữa Trình duyệt (Browser) và API Gateway:
- Truy xuất luồng ảnh từ thiết bị thông qua API WebRTC `navigator.mediaDevices.getUserMedia`.
- Tự động thay đổi kích thước ảnh (tối đa 640x360) và nén chất lượng (JPEG) qua đối tượng `Canvas` ẩn.
- Khởi tạo kết nối WebSocket với Server, định danh bằng `session_id`.
- Đóng gói Frame ảnh thành luồng dữ liệu thô (Binary ArrayBuffer) và gửi lên Server liên tục để tiết kiệm băng thông mạng thay vì sử dụng Base64.
- Lắng nghe phản hồi từ Server để cập nhật tọa độ Bounding Box và dữ liệu định danh khách hàng lên màn hình Camera.

---

## 3. Active Prefetching (Tải trước Dữ liệu Khách hàng)
Nhằm giảm thiểu độ trễ truy xuất dữ liệu khi quản trị viên tương tác:
- Ngay khi luồng WebSocket phát hiện một định danh khách hàng (ví dụ: `CUS_001`) xuất hiện trong khung hình.
- Hook `useProfilePrefetch` ở cấp Root sẽ lập tức kích hoạt API chạy ngầm để lấy toàn bộ lịch sử giao dịch và thông tin chi tiết của `CUS_001`.
- Dữ liệu này được lưu trữ tạm thời vào `sessionStorage`.
- Khi người quản lý click vào khuôn mặt trên màn hình, trang Chi tiết Khách hàng (`/customers/[id]`) sẽ được tải **ngay lập tức** nhờ đọc dữ liệu từ SessionStorage thay vì phải chờ phản hồi API lần nữa.

---

## 4. Role-Based Access Control (RBAC - Phân quyền)
Ứng dụng áp dụng cơ chế Bảo vệ Route (Route Protection) tại phía Client thông qua Context (`UserProvider`).

**Các Vai trò (Roles):**
1. **`guest` (Mặc định):** Chỉ có quyền xem trang Dashboard (Thống kê tổng quan), không được phép xem luồng Camera hoặc danh sách khách hàng.
2. **`moderator` (Nhân viên Lễ tân):** Được phép truy cập Dashboard và xem luồng Camera. Danh sách Camera được quyền truy cập sẽ bị giới hạn cứng dựa vào cấu hình phân quyền từ Backend.
3. **`admin` (Quản lý):** Toàn quyền hệ thống bao gồm xem, chỉnh sửa hồ sơ, tải ảnh và xóa dữ liệu khách hàng.

*(Mọi thao tác thay đổi dữ liệu từ Frontend đều phải trải qua bước xác thực JWT Token `require_admin` tại Backend).*

---

## 5. UI & UX (Thiết kế Kính Mờ - Glassmorphism)
Giao diện hệ thống được thiết kế theo hướng hiện đại, thân thiện:
- **Nền Tương tác:** Sử dụng Background Gradient kết hợp hiệu ứng làm mờ (`backdrop-blur-md`, `bg-white/10`) tạo cảm giác chiều sâu.
- **Smooth Bounding Boxes:** Các khung viền bao quanh khuôn mặt được áp dụng CSS Transition (`transition-all duration-100 ease-linear`). Kỹ thuật này giúp khung viền di chuyển mượt mà trên màn hình ngay cả khi tốc độ phản hồi từ Server bị trễ, loại bỏ hiện tượng giật lag (flickering).
- **Thiết kế Đáp ứng (Responsive):** Tuân thủ nguyên tắc Mobile-First, menu điều hướng linh hoạt (Sidebar Toggle) đảm bảo tính tiện dụng trên các thiết bị máy tính bảng của nhân viên lễ tân.
