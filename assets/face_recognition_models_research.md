# Báo cáo Nghiên cứu: Tối ưu AI Model cho Face Recognition (Realtime + Accuracy)

Để đạt được sự cân bằng hoàn hảo giữa **Độ chính xác (Accuracy)** và **Tốc độ thời gian thực (Real-time FPS)**, đặc biệt là khi chạy trên môi trường CPU giới hạn (như các instance EC2 `t3.micro` của bạn), việc chọn đúng kiến trúc AI Model là yếu tố sống còn.

Dưới đây là phân tích và so sánh các kiến trúc nhận diện khuôn mặt hàng đầu hiện nay dành cho Edge/CPU Deployment:

## 1. Các Ứng cử viên Hàng đầu

### A. Dòng Heavyweight (Dành cho Server có GPU)
*   **ArcFace (ResNet50 / ResNet100)**
    *   **Đặc điểm:** Đây là "tiêu chuẩn vàng" (Gold Standard) về độ chính xác. Khả năng phân biệt khuôn mặt xuất sắc nhờ các mạng CNN rất sâu.
    *   **Điểm yếu:** Cực kỳ nặng. Số lượng tham số (Parameters) và FLOPs quá lớn khiến nó **không thể chạy realtime trên CPU**. Trên `t3.micro`, bạn sẽ gặp tình trạng delay tính bằng giây cho mỗi khung hình.

### B. Dòng Lightweight (Dành cho Edge/CPU/Mobile)
*   **MobileFaceNet**
    *   **Đặc điểm:** Từng là vị vua của các model nhẹ, dựa trên kiến trúc MobileNetV2. Tốc độ cực nhanh.
    *   **Điểm yếu:** Là kiến trúc cũ, độ chính xác của nó đã bị tụt hậu khá nhiều khi đối mặt với các góc nghiêng khó, ánh sáng yếu hoặc bị che khuất so với các model đời mới.
*   **GhostFaceNet**
    *   **Đặc điểm:** Sử dụng "Ghost modules" để loại bỏ các tính toán dư thừa. Nó cung cấp sự cân bằng tuyệt vời, đạt hiệu năng State-of-the-Art (SOTA) trong số các mạng CNN nhẹ.
    *   **Điểm mạnh:** Tốc độ FPS trên CPU cực kỳ ấn tượng nhưng độ chính xác (trên các tập LFW, MegaFace) tiệm cận với các model lớn.
*   **EdgeFace (CVPR 2023 / 2024)**
    *   **Đặc điểm:** Là kiến trúc lai giữa CNN và Transformer (Hybrid). **Quán quân** của cuộc thi Efficient Face Recognition (EFaR) 2023 dành cho các thiết bị Edge.
    *   **Điểm mạnh:** Độ chính xác cực cao dù số lượng tham số rất nhỏ (~1.77 triệu). Vượt trội hoàn toàn MobileFaceNet trên các tập dữ liệu khó như IJB-B, IJB-C.

---

## 2. Bảng So sánh Trực quan

| Tiêu chí | ArcFace (ResNet50) | MobileFaceNet | GhostFaceNet | EdgeFace |
| :--- | :--- | :--- | :--- | :--- |
| **Kiến trúc** | CNN truyền thống | CNN (MobileNet) | CNN (Ghost Modules) | Hybrid (CNN + Transformer)|
| **Tốc độ (CPU)**| 🐢 Rất Chậm | ⚡ Rất Nhanh | ⚡ Nhanh | 🏎️ Khá Nhanh |
| **Độ chính xác** | ⭐⭐⭐⭐⭐ (99.8%+) | ⭐⭐⭐ (99.2%) | ⭐⭐⭐⭐ (99.6%) | ⭐⭐⭐⭐✨ (99.7%) |
| **Tài nguyên** | Rất tốn RAM & CPU | Rất ít | Ít | Rất ít |
| **Mục đích** | Bank-level Security, GPU | IoT cũ, Mobile app | Realtime Camera, CPU | Realtime Camera, CPU |

---

## 3. Khuyến nghị cho Hệ thống của Bạn

Hệ thống của bạn đang sử dụng mô hình **Phân luồng Worker trên CPU AWS EC2 (`t3.micro`)**. Dựa trên cấu hình này:

> [!IMPORTANT]
> **Kết luận:** **GhostFaceNet** và **EdgeFace** chính là 2 model hoàn hảo và tối ưu nhất cho hệ thống của bạn ở thời điểm hiện tại.
> Việc cố gắng chạy ResNet50 trên EC2 không có GPU sẽ làm sập hàng đợi (Queue) của Redis vì Worker không xử lý kịp số lượng Frame gửi đến.

**Tin vui:** Tôi nhận thấy trong file `backend/app/utils/download_models.py` của bạn, bạn đã đi cực kỳ đúng hướng khi chuẩn bị sẵn 2 model là:
*   `ghostface_fp32.onnx`
*   `edgeface_s_gamma_05.onnx` (và script tự build bản `ghostface_int8.onnx`).

### 💡 Chiến lược triển khai tối ưu (Best Practice)
1.  **Dùng `GhostFaceNet INT8` (Quantized):** Nếu bạn muốn **tốc độ tuyệt đối**, hãy sử dụng bản `ghostface_int8.onnx`. Định dạng INT8 (số nguyên 8-bit) giảm một nửa lượng RAM tiêu thụ và tăng tốc độ xử lý trên CPU lên đáng kể so với FP32 (số thực 32-bit), trong khi độ chính xác chỉ suy giảm khoảng 0.1%.
2.  **Dùng `EdgeFace`:** Nếu bạn ưu tiên **nhận diện chính xác khách VIP/khách quen**, đặc biệt là qua các camera góc chéo, hãy cấu hình Worker chạy `edgeface_s_gamma_05.onnx`. Cấu trúc Transformer của nó bắt đặc trưng khuôn mặt (embedding) tốt hơn ở các điều kiện khó.
