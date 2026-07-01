# Phân tích nguyên nhân và Giải pháp khắc phục lỗi mất ID Khách Mới

Chào bạn, tôi đã điều tra cặn kẽ hệ thống theo các hình ảnh và log bạn cung cấp. Có 2 nguyên nhân cốt lõi gây ra tình trạng tạo ID khách mới liên tục và không lưu được:

## 1. Nguyên nhân hệ thống không nhận ra khách cũ (dù đã có trên Supabase)
Những khách được lưu trên Supabase (`GUEST_session-3782dmzf...`, `GUEST_session-f4k67xwg...`) đều được tạo vào ngày **28/06**. Ở thời điểm đó, hệ thống đang dùng model AI khác (ví dụ `w600k_mbf` hoặc `ghostface_int8`).
Hiện tại (ngày **30/06**), hệ thống đã chuyển sang dùng siêu model **EdgeFace** (`edgeface_s_gamma_05.onnx`). 
Do 2 model AI dùng thuật toán mã hóa khuôn mặt hoàn toàn khác nhau, nên dù là cùng 1 khuôn mặt của bạn, vector xuất ra không trùng khớp (độ tương đồng chỉ đạt tối đa `0.43`). Vì mức độ giống nhau này thấp hơn ngưỡng nhận diện (`0.50`), hệ thống xem bạn là một người hoàn toàn mới.
> [!NOTE]
> Khi thay đổi Model nhận diện, toàn bộ Vector khuôn mặt cũ sẽ bị mất tác dụng. Bạn nên xóa các khách rác cũ trong Supabase đi để dọn dẹp hệ thống.

## 2. Nguyên nhân tại sao ID khách mới tạo ra lại KHÔNG được lưu vào DB
Để tiết kiệm dung lượng lưu trữ trên Supabase, bảng `customer_embeddings` hiện tại của bạn chỉ còn giữ lại 3 cột thiết yếu: `customer_id`, `embedding`, `updated_at`. Các cột thừa như `face_embedding` (kiểu BYTEA rất nặng), `embedding_dim`, `model_name` đã bị loại bỏ.
**Tuy nhiên**, mã nguồn Backend của chúng ta (hàm `insert_embedding_with_vector`) vẫn đang cố nhồi nhét dữ liệu vào các cột bị thiếu này, dẫn đến một lỗi Crash ngầm trên Supabase. Vì Crash ngầm, quá trình lưu DB thất bại hoàn toàn. Khách mới không được lưu, nên khi bạn tải lại trang (F5), hệ thống lại tiếp tục coi bạn là khách mới tinh và tạo ID mới!

## Kế hoạch Cải tiến (Đề xuất)

Tôi sẽ sửa lại hàm lưu trữ vào Supabase để:
1. **Chỉ Insert vào đúng 3 cột đang có** (`customer_id`, `embedding`, `updated_at`), bỏ qua các cột BYTEA rườm rà. Điều này vừa giúp fix triệt để lỗi Crash, vừa giúp Supabase của bạn nhẹ gọn nhất có thể.
2. **Sử dụng cú pháp `ON CONFLICT DO UPDATE`**: Nếu trong tương lai khuôn mặt của khách có sự thay đổi (đeo kính, đổi kiểu tóc), hệ thống sẽ cập nhật lại vector mới nhất vào Supabase thay vì báo lỗi trùng lặp.

### [MODIFY] backend/app/db/vector_search.py
Cập nhật hàm `insert_embedding_with_vector`:
- Kiểm tra nếu là PostgreSQL thì chỉ chèn dữ liệu vào các cột `customer_id`, `embedding` (đã ép kiểu `halfvec`), và `updated_at`.
- Thêm logic `ON CONFLICT` để tự động ghi đè vector nếu người dùng cập nhật lại khuôn mặt.

Nếu bạn đồng ý với kế hoạch và lời giải thích trên, hãy nhấn **Proceed** để tôi tiến hành vá lỗi ngay nhé!
