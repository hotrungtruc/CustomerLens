# Báo cáo Thử nghiệm Nhận diện Khách vãng lai
Ngưỡng so khớp cấu hình hiện tại: **0.75**

| Tên Ảnh | Số khuôn mặt | Chi tiết nhận diện | Kết quả |
| --- | --- | --- | --- |
| images (1).jpg | 2 | Face 0: Tạo mới **GUEST_001**<br>Face 1: Khớp với **GUEST_001** (Độ tương đồng: 0.7505) | Tạo mới: 1<br>Trùng khớp: 1 |
| images (2).jpg | 0 | Không phát hiện khuôn mặt đạt chuẩn | Bỏ qua |
| images (3).jpg | 2 | Face 0: Tạo mới **GUEST_002**<br>Face 1: Tạo mới **GUEST_003** | Tạo mới: 2<br>Trùng khớp: 0 |
| images (4).jpg | 2 | Face 0: Tạo mới **GUEST_004**<br>Face 1: Khớp với **GUEST_004** (Độ tương đồng: 0.8318) | Tạo mới: 1<br>Trùng khớp: 1 |
| images (5).jpg | 4 | Face 0: Tạo mới **GUEST_005**<br>Face 1: Tạo mới **GUEST_006**<br>Face 2: Tạo mới **GUEST_007**<br>Face 3: Tạo mới **GUEST_008** | Tạo mới: 4<br>Trùng khớp: 0 |
| images.jpg | 2 | Face 0: Tạo mới **GUEST_009**<br>Face 1: Tạo mới **GUEST_010** | Tạo mới: 2<br>Trùng khớp: 0 |

## Bảng Tổng hợp Thống kê
| Tên Ảnh | Tổng số mặt | Số Guest Tạo mới | Số Guest Trùng khớp |
| --- | --- | --- | --- |
| images (1).jpg | 2 | 1 | 1 |
| images (2).jpg | 0 | 0 | 0 |
| images (3).jpg | 2 | 2 | 0 |
| images (4).jpg | 2 | 1 | 1 |
| images (5).jpg | 4 | 4 | 0 |
| images.jpg | 2 | 2 | 0 |

**Tổng số Guest mới được tạo ra trên toàn hệ thống:** 10