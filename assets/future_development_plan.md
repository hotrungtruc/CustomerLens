# Kế hoạch Mở rộng & Phát triển Dự án Face Recognition

Sau khi phân tích kiến trúc hiện tại của dự án (FastAPI + ONNX Face Recognition + Next.js), hệ thống của bạn đã có bộ khung cốt lõi rất tốt: **Nhận diện khuôn mặt -> Tạo Guest -> Check-in -> Quản lý thông tin**. 

Dưới đây là các định hướng (Phase tiếp theo) mà bạn có thể phát triển để biến hệ thống này thành một sản phẩm thương mại thực thụ (Commercial Grade) hoặc đồ án xuất sắc.

---

## 1. Nâng cấp Core AI (Trí tuệ nhân tạo)

### A. Chống giả mạo khuôn mặt (Liveness Detection / Anti-Spoofing)
- **Vấn đề:** Hiện tại nếu ai đó giơ màn hình điện thoại hoặc bức ảnh in khuôn mặt của người khác ra trước camera, hệ thống vẫn sẽ nhận diện và check-in thành công.
- **Giải pháp:** Tích hợp thêm mô hình Liveness (như *MiniFASNet* siêu nhẹ). Mô hình này sẽ kiểm tra xem khuôn mặt là 3D thực tế hay chỉ là 2D (ảnh/màn hình) trước khi cho phép check-in.
- **Độ khó:** Trung bình - Khó.

### B. Phân tích Nhân khẩu học (Age, Gender, Emotion)
- **Vấn đề:** Lễ tân cần biết thêm thông tin về khách vãng lai để tư vấn tốt hơn.
- **Giải pháp:** Cùng lúc quét khuôn mặt, chạy thêm mô hình phân loại (Classification) để dự đoán **Tuổi**, **Giới tính** và **Cảm xúc** (vui, buồn, trung tính) của khách hàng.
- **Độ khó:** Dễ (Có thể dùng thư viện InsightFace tích hợp sẵn).

---

## 2. Phát triển Tính năng Doanh nghiệp (Business Features)

### A. Hệ thống Cảnh báo VIP / Blacklist tự động
- **Vấn đề:** Nhân viên có thể không để ý màn hình liên tục.
- **Giải pháp:** Xây dựng hệ thống Webhook. Khi một khách hàng được gắn tag "VIP" hoặc "Blacklist" xuất hiện, hệ thống tự động bắn tin nhắn về nhóm **Telegram** hoặc **Zalo** của nhân viên trực (Kèm hình ảnh vừa chụp được).
- **Độ khó:** Dễ - Trung bình.

### B. Dashboard Thống kê & Báo cáo (Analytics)
- **Vấn đề:** Frontend hiện tại chỉ có màn hình trực tiếp (Live), chưa có nơi xem tổng quan dữ liệu.
- **Giải pháp:** Phát triển thêm trang `/dashboard` hiển thị biểu đồ (Dùng *Recharts* hoặc *Chart.js*):
  - Biểu đồ lưu lượng khách theo giờ/ngày.
  - Tỉ lệ khách hàng mới (Guest) vs khách hàng cũ (Returning).
  - Lịch sử check-in chi tiết (Có thể xuất Excel).
- **Độ khó:** Trung bình.

---

## 3. Tối ưu Kiến trúc & Hiệu năng (Architecture & DevOps)

### Chuyển dịch Face Detection xuống Client (WebAssembly / MediaPipe JS)
- **Vấn đề:** Việc gửi ảnh liên tục lên EC2 (3 FPS) gây tốn băng thông và tạo độ trễ.
- **Giải pháp:** (Như đã bàn ở task trước), đưa AI tìm kiếm khuôn mặt chạy thẳng trên trình duyệt. Trình duyệt tự crop đúng khuôn mặt rồi mới gửi lên Backend để tìm ID. Điều này giúp hệ thống gần như đạt **Real-time 30 FPS** mà không tốn thêm tiền server.
- **Độ khó:** Khó (Cần viết lại luồng dữ liệu).



---

