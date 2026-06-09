# Phân tích Vấn đề Nhận diện khi Đeo/Tháo Kính

Một trong những bài toán kinh điển của các hệ thống nhận diện khuôn mặt (Face Recognition) là sự thay đổi đặc trưng khuôn mặt khi người dùng thêm/bớt phụ kiện, đặc biệt là **kính râm, kính cận dày, hoặc khẩu trang**.

Dưới đây là bản phân tích chi tiết về nguyên nhân AI nhận diện sai và phương án cải tiến triệt để cho hệ thống của bạn.

## 1. Phân tích Nguyên nhân (Tại sao AI nhận diện sai?)

Mô hình AI hiện tại của bạn (`GhostFaceNet`) chuyển đổi một khuôn mặt thành một vector đặc trưng gồm 512 chiều (512-D embedding). Thuật toán nhận diện dựa trên việc đo khoảng cách (Cosine Similarity) giữa vector của người đang đứng trước camera và các vector đã lưu trong Database.

> [!WARNING]
> **Vấn đề "Khoảng cách Vector" khi đeo kính:**
> Khi một người đeo kính (đặc biệt là kính gọng to hoặc kính râm che khuất hốc mắt):
> - Thuật toán trích xuất đặc trưng bị mất đi dữ liệu quan trọng nhất: **Khoảng cách 2 mắt, độ sâu hốc mắt, và lông mày**.
> - Kính phản chiếu ánh sáng (Glare) tạo ra các noise (nhiễu) trên ma trận ảnh.
> - Hậu quả: Vector 512-D bị dịch chuyển sai lệch một khoảng đáng kể. Điểm Similarity thay vì đạt `0.70` - `0.80` (rất chắc chắn) thì bị tụt xuống `0.40` - `0.50`.

Vì ngưỡng `SIMILARITY_THRESHOLD` của hệ thống quy định (ví dụ: `0.50`), nếu điểm tụt xuống `0.48`, AI sẽ không dám nhận diện đó là khách quen, và tự động gán họ thành một khách vãng lai mới (`GUEST_123`).

## 2. Phân tích các Giải pháp khả thi

Để giải quyết vấn đề này, chúng ta có 3 hướng tiếp cận chính:

### Phương án A: Hạ thấp ngưỡng nhận diện (Threshold)
- **Cách làm**: Thay vì yêu cầu độ giống nhau > 50%, ta hạ xuống 40%.
- **Ưu điểm**: Dễ làm, code không thay đổi nhiều. Khách đeo kính vẫn nhận ra được.
- **Nhược điểm (Rất Tệ)**: Tăng đột biến tỷ lệ **Nhận diện nhầm người (False Positive)**. Người A có thể bị nhận nhầm thành người B vì ngưỡng quá lỏng lẻo.
- **Kết luận**: Không nên dùng cách này để xử lý riêng lẻ.

### Phương án B: Cập nhật Vector Động (Dynamic Vector Updating / Exponential Moving Average)
- **Cách làm**: Mỗi lần khách đến quán (dù có kính hay không kính), nếu điểm số ở mức tạm chấp nhận (vd: 0.55), hệ thống sẽ lấy vector mới cộng dồn (blend) vào vector cũ lưu trong DB: `New_Vector = 0.9 * Old_Vector + 0.1 * Current_Vector`.
- **Ưu điểm**: Vector trong DB sẽ dần biến đổi theo độ tuổi và thói quen đeo kính của khách.
- **Nhược điểm**: Nếu blend nhầm 1 frame của người khác, profile của khách đó sẽ bị "ô nhiễm" và mất dần khả năng nhận diện chính xác.
- **Kết luận**: Khó kiểm soát, rủi ro làm hỏng dữ liệu.

### Phương án C: Hồ sơ Đa Khuôn Mặt (Multi-Template Face Bank)
> [!TIP]
> **Đây là phương pháp chuẩn công nghiệp (Industry Standard) được dùng ở Apple FaceID và các hệ thống chấm công cao cấp.**

- **Cách làm**: Phá vỡ quy tắc "1 ID - 1 Khuôn mặt". Chúng ta cho phép bảng `customer_embeddings` lưu **nhiều vector** cho cùng 1 `customer_id`. 
  - Vector 1: Mặt mộc.
  - Vector 2: Mặt đeo kính cận.
  - Vector 3: Mặt đeo khẩu trang (nếu cần).
- Khi người dùng soi mặt vào camera, AI sẽ so sánh với TOÀN BỘ các vector này. Nếu giống **BẤT KỲ** vector nào (đạt > 50%), hệ thống chốt luôn đó là người đó!
- **Ưu điểm**: Giải quyết triệt để vấn đề mà độ chính xác vẫn giữ ở mức cao nhất. Không bao giờ sợ "ô nhiễm" vector gốc.

---

## 3. Đề xuất Kiến trúc Cải tiến (Action Plan cho Phương án C)

Để áp dụng **Hồ sơ Đa Khuôn Mặt**, tôi đề xuất thực hiện 3 bước sau vào Backend hiện tại:

### Bước 1: Thay đổi Schema Database (SQLite)
Hiện tại bảng `customer_embeddings` đang set `customer_id` làm `PRIMARY KEY` (chỉ cho phép 1 dòng cho 1 khách).
- Cần thay đổi: Bỏ `PRIMARY KEY` khỏi `customer_id`. Cấu trúc mới sẽ là 1 khách hàng có thể có $N$ dòng trong bảng này.
- Khi load vào RAM, thay vì mỗi ID là một vector, hệ thống sẽ gom nhóm các vector cùng ID lại. 

### Bước 2: Cập nhật thuật toán tìm kiếm (Search Algorithm)
- Trong `app/core/guest_tracking.py`, hàm `np.dot(known_embeddings, embedding)` đang thực hiện phép nhân ma trận. Phép nhân này vốn đã **hỗ trợ cực tốt** việc 1 ID có nhiều vector.
- Nếu `known_embeddings` có chứa 3 vector của người A và 1 vector của người B. Phép `np.dot` sẽ trả về mảng 4 điểm số. Ta chỉ cần lấy ID tương ứng với điểm cao nhất. (Code hiện tại có thể chỉ cần chỉnh sửa rất nhẹ ở mảng label `guest_track_manager.known_customer_ids`).

### Bước 3: Tạo API "Gộp Hồ Sơ" (Merge Guest to Customer)
- **Vấn đề thực tế**: Khi khách quen mua cặp kính mới và bước vào quán, AI lần đầu sẽ KHÔNG nhận ra và tạo ra một ID tạm là `GUEST_005`.
- **Giải pháp**: Nhân viên/Thu ngân nhìn thấy `GUEST_005`, nhận ra đây là anh A (khách quen). Nhân viên bấm nút "Hợp nhất" trên giao diện.
- Frontend sẽ gọi API: `POST /api/merge_guest_to_customer` với body `{ "guest_id": "GUEST_005", "customer_id": "CUST_001" }`.
- Backend sẽ lấy vector của `GUEST_005` và lưu thêm vào DB dưới mã `CUST_001`. Từ ngày mai, anh A đeo kính sẽ được AI nhận diện ngay lập tức 100%.

> [!IMPORTANT]
> **Yêu cầu phản hồi từ bạn**
> Bạn có muốn tôi bắt tay vào code các bước để triển khai kiến trúc **Hồ sơ Đa Khuôn Mặt** này không? Quá trình sẽ gồm việc sửa file `connection.py` để update DB và viết thêm API `/api/merge_guest_to_customer`.
