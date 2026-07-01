# Quản lý moderator và phân quyền camera

Tài liệu này mô tả màn hình **Phân quyền**, API quản lý moderator và cách lưu quyền xem camera sau migration Camera ID cố định.

## 1. Luồng quản trị

1. Admin mở trang **Quản lý Camera** và đổi `display_name` để camera dễ nhận biết.
2. Admin mở trang **Phân quyền** để tạo hoặc chọn một moderator.
3. Frontend tải user thật từ `GET /api/users` và camera thật từ `GET /api/cameras`.
4. Admin chọn các camera moderator được phép xem.
5. Frontend gọi `PUT /api/users/{username}/camera_permissions`.
6. Backend lưu quyền theo `camera_id` trong `user_camera_permissions`.
7. Khi moderator tải catalog hoặc mở observer WebSocket, backend kiểm tra quyền trước khi trả dữ liệu hoặc `accept()` kết nối.

Không lưu quyền theo `connection_id`. Giá trị này chỉ đại diện cho một phiên WebSocket và thay đổi sau mỗi lần kết nối lại.

## 2. Màn hình Phân quyền

Trang `frontend/src/app/notifications/page.jsx` không còn sử dụng dữ liệu mock hoặc danh sách camera hard-code.

Các thao tác dành cho admin:

- Tạo tài khoản moderator.
- Đổi mật khẩu moderator; để trống nếu không muốn đổi.
- Khóa hoặc mở khóa tài khoản.
- Xóa moderator.
- Chọn camera được phép xem và lưu thay đổi.

Bộ đếm camera chỉ tính những Camera ID tồn tại trong catalog camera đang active. ID legacy hoặc camera đã retire không được đưa vào form, vì vậy số đã chọn không thể lớn hơn tổng camera khả dụng.

## 3. API

Tất cả endpoint dưới đây yêu cầu session admin qua `Authorization: Bearer <token>`.

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `GET` | `/api/users` | Danh sách user và `camera_ids` đã gán |
| `POST` | `/api/users` | Tạo moderator |
| `PATCH` | `/api/users/{username}` | Đổi mật khẩu hoặc trạng thái tài khoản |
| `DELETE` | `/api/users/{username}` | Xóa moderator và permission liên quan |
| `PUT` | `/api/users/{username}/camera_permissions` | Thay toàn bộ quyền xem camera |
| `PATCH` | `/api/cameras/{camera_id}` | Đổi tên hiển thị camera |

Ví dụ cập nhật quyền:

```json
{
  "camera_ids": ["cam_b1a9216ef83a406e982afead6976a875"]
}
```

Backend từ chối Camera ID không tồn tại hoặc không còn active.

## 4. Database

Quyền được lưu trong bảng chuẩn hóa:

```sql
CREATE TABLE user_camera_permissions (
    user_id INTEGER NOT NULL,
    camera_id VARCHAR(64) NOT NULL,
    permission VARCHAR(20) NOT NULL DEFAULT 'view',
    PRIMARY KEY (user_id, camera_id, permission)
);
```

Các cột `users.status`, `users.created_at` và `users.updated_at` hỗ trợ khóa tài khoản và hiển thị lịch sử cập nhật. Khi đổi mật khẩu, khóa hoặc xóa user, session tương ứng bị thu hồi.

`users.cameras` là trường legacy. Trong giai đoạn chuyển tiếp, code chỉ fallback sang trường này nếu user chưa có permission chuẩn hóa và chỉ giữ các ID còn tồn tại trong catalog active. Không thêm tính năng mới dựa trên trường legacy này.

## 5. Kiểm tra quyền runtime

- Admin nhận toàn bộ camera active từ `GET /api/cameras`.
- Moderator chỉ nhận camera có permission `view`.
- `/ws/observe/{camera_id}` xác thực session và permission trước `accept()`.
- Tài khoản `disabled` không thể đăng nhập.
- Camera đã retire hoặc ID legacy không được tính là quyền hợp lệ.

Regression tests nằm tại `backend/tests/test_camera_identity_migration.py`.
