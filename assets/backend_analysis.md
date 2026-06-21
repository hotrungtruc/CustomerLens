# Phân tích lỗi "BBox tách làm 2"

Lỗi "bbox tách làm 2" mà bạn gặp phải không phải là lỗi nhận diện sai hoặc bị lật tọa độ, mà là **lỗi độ trễ (latency)** giữa 2 hệ thống:

1. **Local FaceDetector (viền xám):** Chạy trực tiếp trên trình duyệt ở tốc độ khung hình cao (30-60 FPS), nên nó bám theo mặt bạn cực kỳ mượt mà.
2. **Backend Face Recognition (viền tím có chữ A):** Phải gửi ảnh qua mạng, xử lý AI nặng, nên nó bị trễ (lag) khoảng 0.5 - 1 giây.

**Hiện tượng xảy ra:**
Khi bạn vừa di chuyển đầu (như trong ảnh là chuyển từ giữa/phải khung hình sang mép trái), khung xám lập tức bám theo mặt bạn sang trái. Tuy nhiên, khung tím của backend vẫn đang hiển thị vị trí của bạn từ **0.5 giây trước** (ở vị trí tủ tài liệu phía bên phải). 
Do 2 khung này cách xa nhau, thuật toán của hệ thống cho rằng đây là 2 khuôn mặt khác nhau, nên nó hiển thị tách làm 2 khung. Khung tím giữ lại nhãn "A", còn khung xám hiển thị không nhãn vì chưa kịp đồng bộ với backend.

## Giải pháp:
Tôi sẽ cập nhật lại thuật toán `Hybrid Tracking` trên Frontend:
- Sử dụng **Temporal Tracking (Theo dõi theo thời gian thực):** Nếu khung xám mất kết nối với khung tím hiện tại, nó sẽ tự động "nhớ" nhãn "A" từ khung hình trước đó nhờ theo dõi độ tương đồng IoU liên tục.
- Tự động ẩn khung tím bị trễ đi để giao diện gọn gàng, và tự động gắn nhãn "A" cho khung xám đang bám sát mặt bạn.

Bạn hãy kiểm tra lại bảng phân tích này. Nếu bạn đồng ý, tôi sẽ sửa lại thuật toán trong `CameraStream.jsx` ngay bây giờ!
