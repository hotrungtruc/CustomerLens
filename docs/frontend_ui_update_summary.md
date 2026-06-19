# Tóm Tắt Cập Nhật Giao Diện Frontend

## Tổng quan

Tài liệu này tóm tắt các thay đổi giao diện frontend trên branch `Quang_front19/6`.
Mục tiêu chính là tối ưu giao diện để hiển thị tốt hơn trên màn hình laptop ở mức zoom trình duyệt 100%, đặc biệt là trang camera và các trang dashboard.

## Các thay đổi chính

### Thanh điều hướng bên trái

- Thay sidebar desktop rộng bằng thanh điều hướng hẹp bên trái.
- Thêm nút 3 gạch để mở menu điều hướng đầy đủ.
- Giữ nguyên phân quyền theo vai trò, tài khoản nào chỉ thấy các trang được phép truy cập.
- Giảm chiều rộng sidebar từ `220px` xuống `64px` ở các layout chính để tăng diện tích hiển thị nội dung.

### Trang Camera

- Mở rộng lưới camera lên 18 ô camera.
- Sắp xếp lưới camera desktop thành bố cục cố định `3 dòng x 6 cột`.
- Thêm một ô camera offline mới.
- Giữ toàn bộ trang trong kích thước màn hình laptop, không tạo thanh cuộn dọc bên phải.
- Chuyển mỗi ô camera thành dạng thumbnail gọn, có tên camera và trạng thái nằm nổi trên khung hình.
- Thêm chức năng phóng to từng camera.
- Chỉnh modal phóng to để nút đóng luôn nằm rõ trong phần header, không bị che bởi mép trên màn hình.
- Giảm việc khởi động lại luồng webcam không cần thiết để hạn chế lỗi trình duyệt dạng `play() request was interrupted`.

### Trang Tổng quan

- Điều chỉnh layout để vừa với viewport laptop.
- Giảm padding bên ngoài và khoảng cách bên trong.
- Giữ panel khách hàng gần đây ở bên phải.
- Đảm bảo khu vực tài khoản và nút đăng xuất ở sidebar không bị che ở màn hình laptop.

### Trang Settings

- Chuyển trang Settings sang layout cố định theo chiều cao viewport.
- Giảm padding của card và các dòng cấu hình.
- Sắp xếp 4 nhóm cấu hình thành bố cục gọn `2 x 2`.
- Tránh tình trạng phần cuối trang bị che trên laptop ở zoom 100%.

### Trang Customer

- Trang Customer được xem là ngoại lệ vì danh sách khách hàng có thể dài.
- Giữ phần tìm kiếm và bộ lọc ở phía trên.
- Thêm vùng cuộn riêng cho bảng khách hàng để danh sách dài vẫn xem được đầy đủ.
- Không ép toàn bộ danh sách phải vừa một màn hình.

## Các file frontend đã thay đổi

- `frontend/src/app/camera/page.jsx`
- `frontend/src/app/customers/[id]/page.jsx`
- `frontend/src/app/customers/page.jsx`
- `frontend/src/app/globals.css`
- `frontend/src/app/history/page.jsx`
- `frontend/src/app/layout.jsx`
- `frontend/src/app/notifications/page.jsx`
- `frontend/src/app/page.jsx`
- `frontend/src/app/reports/page.jsx`
- `frontend/src/app/settings/page.jsx`
- `frontend/src/components/CameraStream.jsx`
- `frontend/src/components/PageHeader.jsx`
- `frontend/src/components/Sidebar.jsx`
- `frontend/src/hooks/useCamera.js`

## Kiểm tra

- Đã chạy build frontend bằng lệnh `npm run build`.
- Build hoàn tất thành công.
- Các thay đổi đã được commit trên branch `Quang_front19/6`.
- Branch đã được push lên GitLab tại `origin/Quang_front19/6`.
