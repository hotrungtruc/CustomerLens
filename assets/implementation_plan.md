# Kế hoạch Triển khai: Hệ thống Nhận diện Tự động Kháng Vật Cản (Kính/Khẩu trang)

Bản kế hoạch này nhằm xây dựng một hệ thống nhận diện khuôn mặt **tự động hoàn toàn 100%**, khắc phục vấn đề giảm độ chính xác khi khách hàng đeo kính hoặc thay đổi phụ kiện mà không cần nhân viên thao tác thủ công.

## 1. Mục tiêu Cốt lõi
Kết hợp **Mô hình AI kháng vật cản (Occlusion-aware)** và **Kiến trúc Tự động Học (Tracking & Auto-learning)** cùng cơ sở dữ liệu **Hồ sơ Đa Khuôn Mặt (Multi-Template Face Bank)**.

---

## 2. Phân tích & Lựa chọn Mô hình (Model Selection)

Đánh giá các mô hình trích xuất đặc trưng khuôn mặt (Face Embedding Models) dựa trên thông tin bạn cung cấp. Việc thay thế GhostFaceNet bằng một trong các mô hình này sẽ giải quyết tận gốc từ phía AI.

| Mô hình | Đặc điểm (Margin Strategy) | Đánh giá về khả năng xử lý Khách đeo Kính (Occlusion / Low-quality) | Độ ưu tiên triển khai |
| :--- | :--- | :--- | :---: |
| **AdaFace** | **Quality-Adaptive Margin**: Margin thay đổi động theo chất lượng ảnh. | **Rất Tốt**. Các khung hình có kính thường bị đánh giá là ảnh chất lượng giảm đi so với ảnh gốc (enrollment). AdaFace sẽ tự động điều chỉnh độ khắt khe, giúp nhận diện người đeo kính mượt mà hơn. Đã chứng minh hiệu năng cao trên các tập dữ liệu khó (IJB-C, TinyFace). | **1 (Khuyên dùng)** |
| **MagFace** | **Quality-Aware**: Ảnh nét sẽ bị đẩy gần tâm, ảnh mờ/đeo kính đẩy ra biên. | **Tốt**. Tránh overfit vào các mẫu nhiễu. Thích hợp cho môi trường "in the wild" (ánh sáng quán cafe, góc nghiêng, kính râm). Mang lại sự ổn định cao. | 2 |
| **ElasticFace**| **Elastic Margin**: Margin thay đổi ngẫu nhiên theo từng vòng huấn luyện. | **Khá**. Phản ánh đúng thực tế dữ liệu không đồng đều. Ổn định và mềm dẻo hơn ArcFace truyền thống nhưng việc tối ưu riêng cho kính râm/khẩu trang có thể không sắc nét bằng AdaFace. | 3 |
| **ArcFace** | **Fixed Margin**: Cố định khoảng cách phân loại. | **Trung bình/Khá**. Là baseline cực chuẩn, dễ tích hợp nhất với thư viện `insightface`. Tuy nhiên độ linh hoạt trước ảnh che khuất (kính) sẽ cứng nhắc hơn các phương pháp adaptive ở trên. | 4 (Dự phòng) |

> [!TIP]
> **Khuyến nghị Lựa chọn:** Triển khai **AdaFace** làm model Embedding chính vì tính chất "Quality-Adaptive" rất phù hợp với biến thiên sinh ra do khách đeo thêm phụ kiện kính trên mặt.

---

## 3. Kiến trúc Đề xuất: "Tự động học qua Tracking" (Auto-learning Pipeline)

Ngay cả khi dùng AdaFace, một cặp kính râm quá to vẫn có thể gây trượt (ví dụ ngưỡng 0.45, thay vì > 0.50). Để hệ thống tự động 100%, ta triển khai luồng **Face Tracking & Auto-Merge**:

1. **Giai đoạn Tracking (Theo dõi):** Camera bắt được 1 người đi từ cửa vào, liên tục gán 1 ID tạm thời duy nhất (vd: `Track_ID_A`) cho khoảng 30-50 khung hình của quá trình di chuyển này.
2. **Giai đoạn Nhận diện trong chuỗi (Sequence Matching):** 
   - Đa số khung hình bị kính che, Similarity < 0.5 $\rightarrow$ Trượt.
   - Trùng hợp có 1-2 giây khách đẩy kính/tháo kính/đổi góc sáng khiến mắt hiện rõ, Similarity vọt lên > 0.6 $\rightarrow$ Hệ thống nhận diện được `Track_ID_A` chính là anh A (`CUST_001`).
3. **Giai đoạn Auto-Merge (Học tự động):** 
   - Hệ thống tự động lấy toàn bộ các ảnh đeo kính trong `Track_ID_A` vừa nãy, trích xuất Vector và **Lưu trực tiếp vào Database** dưới dạng "Phiên bản Đeo Kính" của anh A.
   - Các lần sau khách đến quán (dù không tháo kính), AI sẽ quét qua Face Bank (chứa sẵn phiên bản đeo kính) và nhận ra ngay lập tức.

---

## 4. Các bước triển khai cụ thể (Execution Plan)

### Bước 1: Nâng cấp AI Model (Thử nghiệm AdaFace / MagFace)
- **Tác vụ:** Thay thế file/weights của mô hình hiện tại (`app/core/insight_embedding.py` và thư mục tải weights).
- **Chi tiết:** Tìm và tải pre-trained weights của **AdaFace** (hoặc model tùy chọn) có định dạng ONNX (hoặc format tương thích InsightFace). Cập nhật hàm load model để sử dụng weights mới.

### Bước 2: Cập nhật Cấu trúc Database sang Multi-Template Face Bank
- **Tác vụ:** Sửa đổi Schema DB (loại bỏ ràng buộc 1 Customer = 1 Vector).
- **Chi tiết:** Cho phép bảng `customer_embeddings` (hoặc cấu trúc RAM hiện tại) chứa Array các vectors (nhiều vector cho cùng 1 ID). Cập nhật hàm So sánh (`np.dot` trong `guest_tracking.py`) để lấy MAX similarity trong nhóm vectors của mỗi ID.

### Bước 3: Thuật toán Face Tracking (Track-let) tại Backend
- **Tác vụ:** Quản lý chuỗi khung hình của 1 khách đi qua camera.
- **Chi tiết:** Khi frame liên tục được gửi lên, backend cần nhận biết chúng thuộc cùng 1 người di chuyển (dựa trên thuật toán Tracking cơ bản hoặc toạ độ Bounding Box liên tiếp). Tính toán điểm Similarity trên toàn chuỗi thay vì 1 khung hình đơn lẻ.

### Bước 4: Viết Logic Tự động Hợp nhất (Auto-Merge Logic)
- **Tác vụ:** Code logic để khi một chuỗi frames của `Track_ID` chứa điểm "Đỉnh" (Peak Similarity > Threshold), hệ thống sẽ lưu vector của các frames có điểm thấp (đeo kính) vào DB.

---

> [!WARNING]
> ## Câu hỏi mở cần xác nhận trước khi Code (User Review Required)
> 1. **Về lựa chọn Model:** Hiện tại bộ mã của bạn đang dùng `GhostFaceNet`. Việc chuyển sang **AdaFace** (hoặc mô hình khác) sẽ yêu cầu tải file ONNX weights mới. Bạn có file ONNX của AdaFace sẵn không, hay tôi sẽ tìm script để tải từ repo nguồn mở?
> 2. **Về Tracking:** Camera (hoặc Frontend) của bạn gửi từng ảnh chụp ngắt quãng hay gửi luồng Video liên tục (nhiều FPS)? Thuật toán Auto-Merge yêu cầu có một chuỗi khung hình (Tracking) của cùng một người đi lại. Nếu frontend chỉ gửi 1 ảnh rời rạc thì không làm Auto-Merge Tracking được.
> 3. Bạn muốn bắt đầu bước nào trước? (VD: Thay model AI trước, hoặc Sửa Database làm Multi-Template trước?)
