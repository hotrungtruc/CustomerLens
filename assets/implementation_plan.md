# Kế hoạch tối ưu hóa Hệ thống Nhận diện Khuôn mặt cho Nhà hàng (FaceID)

> **[TRẠNG THÁI: HOÀN TẤT]** Các hạng mục tối ưu hóa trong kế hoạch này đã được triển khai thành công vào mã nguồn.

Dưới góc nhìn chuyên gia tối ưu hóa hệ thống FaceID, tôi đã phân tích kiến trúc hiện tại và phát hiện **4 điểm nghẽn (bottlenecks) tử huyệt** khiến hệ thống không thể chạy mượt ở quy mô nhà hàng. Dưới đây là kế hoạch giải quyết triệt để:

## 1. Điểm nghẽn Truyền tải (Network & Serialization)
**Vấn đề:** Frontend hiện tại đang encode ảnh JPEG sang chuỗi `Base64`, đóng gói vào JSON rồi gửi qua WebSocket. Ở Backend lại decode JSON, giải mã Base64 thành Bytes rồi mới giải mã JPEG. Base64 làm tăng dung lượng 33% và ngốn cực nhiều CPU của cả Browser lẫn Python (vốn là ngôn ngữ chậm). Nếu truyền 20 FPS, đây là gánh nặng khổng lồ.
**Giải pháp:** 
- Đổi sang truyền **Binary WebSocket**.
- Frontend: Gọi `canvas.toBlob()` và gửi trực tiếp mảng bytes (ArrayBuffer).
- Backend: Nhận raw bytes và đưa thẳng vào `cv2.imdecode`. Bỏ qua hoàn toàn JSON và Base64.

## 2. Điểm nghẽn Cạn kiệt Kết nối Database (Connection Pool Exhaustion)
**Vấn đề:** Trong `routes.py` (hàm `websocket_camera`), một kết nối Database (Supabase) được mở ngay khi client kết nối và **bị giữ vĩnh viễn (Hold Forever)** trong vòng lặp `while True`. Nếu có 10 người mở 10 tab, pool 10 connection của Supabase sẽ cạn kiệt, hệ thống sẽ sập hoặc treo.
**Giải pháp:**
- Trả connection về pool ngay lập tức. 
- Chỉ xin cấp connection (acquire) ở đúng dòng code cần truy vấn thông tin khách hàng (khi cache chưa có), sau đó đóng/trả (release) ngay lập tức.

## 3. Điểm nghẽn UI Tracking / Vẽ Box
**Vấn đề:** Box vẽ trên Frontend có thể bị giật lag nếu AI trả về chậm hơn 20 FPS.
**Giải pháp:**
- Frontend cần làm mịn (CSS transition) cho tọa độ bounding box để nó trượt mượt mà theo khuôn mặt thay vì giật cục (đổi sang `transition: all 0.1s linear`).

---

## User Review Required

> [!WARNING]
> Đổi sang Binary WebSocket sẽ đòi hỏi phải cập nhật logic gửi/nhận ở cả `useCamera.js` (Frontend) và `routes.py` (Backend).

> [!IMPORTANT]
> Đây là một bản đại tu kiến trúc tối ưu hóa. Bạn có đồng ý với định hướng này không? Nếu đồng ý, tôi sẽ bắt đầu triển khai ngay!
