# Kế hoạch triển khai: Kiến trúc Hybrid P2P WebRTC + CSS Smoothing

Dưới đây là thiết kế chi tiết để hiện thực hóa kiến trúc tách luồng tối ưu nhất: **P2P WebRTC cho luồng Video độ trễ 0 (trực tiếp giữa 2 trình duyệt) + WebSocket cho AI Tracking**, kết hợp với thủ thuật **CSS Transition** để đồng bộ hóa cảm giác nhìn.

## 1. Thành phần thay đổi

### [MODIFY] `backend/app/api/routes.py`
Server không gánh video, nhưng sẽ đóng vai trò làm **Signaling Server** (Trạm trung chuyển tín hiệu WebRTC) bằng Redis Pub/Sub.
- Sửa hàm `websocket_camera`: 
  - Lắng nghe cả dữ liệu `Bytes` (khung hình JPEG gửi cho AI) và `Text` (tín hiệu WebRTC SDP/ICE).
  - Nếu là Text, đẩy (Publish) vào kênh Redis `webrtc_signaling_{session_id}`.
  - Đồng thời lắng nghe kênh này để gửi tín hiệu từ Admin về lại cho Camera.
- Sửa hàm `websocket_observe`:
  - Thêm một task `receive_text` để Admin có thể gửi tín hiệu SDP/ICE lên Server.
  - Lắng nghe kênh `webrtc_signaling_{session_id}` để nhận tín hiệu kết nối từ Camera.

### [MODIFY] `frontend/src/hooks/useCamera.js`
Đây là Frontend gắn tại quầy Lễ tân (Camera). 
- Bổ sung đối tượng `peerConnections = {}` để quản lý nhiều kết nối WebRTC cùng lúc (nếu có nhiều Admin cùng xem).
- Bắt tín hiệu `webrtc_offer` từ WebSocket:
  - Khởi tạo `RTCPeerConnection`.
  - Bơm luồng Camera gốc (`streamRef.current.getTracks()`) vào kết nối.
  - Trả lời bằng `webrtc_answer`.
  - Xử lý ICE Candidates.

### [MODIFY] `frontend/src/hooks/useCameraObserver.js`
Đây là Frontend của Admin.
- Sinh ra một mã `adminId` ngẫu nhiên.
- Mở `RTCPeerConnection`, gửi `webrtc_offer` lên WebSocket để chào hàng với Camera.
- Bắt sự kiện `ontrack` để lấy luồng Video P2P gán vào một biến state `videoStream`.

### [MODIFY] `frontend/src/components/CameraViewer.jsx`
- Thay thế thẻ `<img />` (hiển thị ảnh tĩnh) bằng thẻ `<video autoPlay playsInline muted />` (hiển thị video WebRTC trực tiếp).
- Tối ưu hóa **CSS Smoothing**: Tăng cường class CSS `transition-all duration-300 ease-linear` cho các khung vuông Bounding Box. Khung vuông sẽ mượt mà lướt theo khuôn mặt trên màn hình thay vì giật cục, bù đắp hoàn hảo cho độ trễ 0.2s của luồng WebSocket so với luồng Video UDP.

## 2. Rủi ro & Lưu ý
- **STUN Server**: Trong kế hoạch này, tôi sẽ cấu hình sẵn danh sách STUN server miễn phí của Google (`stun:stun.l.google.com:19302`) để 2 trình duyệt có thể đâm xuyên tường lửa mạng LAN và tìm thấy nhau.
- **Tính bảo mật**: WebRTC yêu cầu chạy trên môi trường HTTPS hoặc Localhost. Đảm bảo trang web của Admin và Lễ tân đều đang chạy hợp lệ.

> [!IMPORTANT]
> Đây là một tính năng phức tạp đụng chạm vào cả 3 lớp: AI Backend, React Frontend (Camera) và React Frontend (Admin). Tôi sẽ cẩn thận viết lại các Hook React để tránh rò rỉ bộ nhớ (Memory Leak) khi đóng mở RTCPeerConnection. 
> 
> Nếu bạn đã sẵn sàng với kiến trúc đỉnh cao này, hãy nhấn **Proceed** để tôi tiến hành viết code!
