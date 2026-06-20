# Kiến trúc Frontend (Frontend Architecture)

Frontend của Front Door AI được thiết kế với mục tiêu **Hiển thị Thời gian thực (Real-time)**, **Bảo mật (RBAC)**, và **Tối đa hóa Trải nghiệm Người dùng (UX)** bằng triết lý Glassmorphism cao cấp.

## 1. Công nghệ Sử dụng
- **Framework:** Next.js 14 (App Router)
- **Styling:** Tailwind CSS (Tích hợp Glassmorphism, CSS Transitions mượt mà)
- **State Management:** React Hooks (`useState`, `useRef`, `useCallback`), `sessionStorage` (lưu trữ token tạm).
- **Communication:** WebSocket (Realtime Video & Data), Fetch API (REST CRUD).

---

## 2. Quản lý Kết nối Camera (Camera Stream)
**Hook `useCamera.js`**
Đây là lõi giao tiếp giữa Browser và Backend:
- Đảm nhiệm lấy luồng ảnh từ thiết bị qua `navigator.mediaDevices.getUserMedia`.
- Tự động Resize ảnh (tối đa 640x360) và nén chất lượng (`0.75 JPEG`) qua thẻ `Canvas` ẩn.
- Khởi tạo kết nối WebSocket dựa trên `session_id`.
- Đóng gói Frame ảnh thành chuỗi Base64 và gửi lên Server liên tục với khoảng thời gian `CAPTURE_INTERVAL_MS = 50ms` (~20 FPS).
- Đồng thời nhận về `customers` (dữ liệu Box và Thông tin nhận diện) để Frontend vẽ đè lên Camera gốc.

---

## 3. Active Prefetching (Tải trước Dữ liệu Khách hàng)
Một kỹ thuật để giải quyết bài toán "Độ trễ khi click vào hồ sơ":
- Ngay khi luồng WebSocket thông báo có một khách hàng `CUS_001` xuất hiện trong khung hình.
- Hook `useProfilePrefetch` ở cấp Root sẽ lập tức gọi API chạy ngầm lấy toàn bộ lịch sử giao dịch, số thẻ, thông tin của `CUS_001`.
- Dữ liệu này được đẩy vào `sessionStorage`.
- Khi người quản lý (Admin/Moderator) bấm vào thẻ mặt trên màn hình, trang Chi tiết Khách hàng (`/customers/[id]`) sẽ load **Tức thì (0ms latency)** nhờ đọc từ SessionStorage thay vì chờ gọi API lại.

---

## 4. Role-Based Access Control (RBAC - Phân quyền)
Ứng dụng có cơ chế Bảo vệ Route (Route Protection) ngay tại Client thông qua Context (`UserProvider`).

**Các Vai trò (Roles):**
1. **`guest` (Mặc định):** Chỉ xem được trang Dashboard (Thống kê chung), không xem được danh sách Khách hàng chi tiết và Luồng Camera.
2. **`moderator` (Nhân viên):** Xem được Dashboard và Luồng Camera. Tuy nhiên danh sách Camera sẽ bị giới hạn cứng dựa vào cấu hình `cameras` trả về từ Backend (Ví dụ chỉ cho xem Camera Cổng số 1).
3. **`admin` (Quản lý):** Toàn quyền xem, sửa hồ sơ, thêm ảnh, xóa khách hàng.

*(Mọi thay đổi trên Frontend đều phải vượt qua chốt chặn `require_admin` ở Backend thông qua Bearer Token).*

---

## 5. UI & UX (Giao diện Kính Mờ - Glassmorphism)
Hệ thống loại bỏ hoàn toàn các khung viền cứng cáp, thay vào đó là:
- **Nền Tương tác:** Sử dụng Background Gradient và Hiệu ứng blur (`backdrop-blur-md`, `bg-white/10`).
- **Smooth Bounding Boxes:** Các viền vẽ khuôn mặt trên luồng Camera được CSS Transition làm mịn `transition-all duration-100 ease-linear` để không bị giật lag khung hình khi Server trả về tọa độ mới.
- **Responsive:** Thiết kế theo Mobile-First, Menu ẩn linh hoạt (Sidebar Toggle) cho máy tính bảng/điện thoại cầm tay của Lễ tân.
