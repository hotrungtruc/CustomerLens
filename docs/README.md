# CustomerLens - Technical Documentation

Chào mừng bạn đến với tài liệu kỹ thuật của dự án **CustomerLens - Hệ thống Nhận diện Khuôn mặt & Phân tích Khách hàng Thời gian thực**. Tài liệu này được biên soạn dành cho các Software Engineers, AI Engineers và DevOps nhằm cung cấp cái nhìn sâu sắc, toàn diện về kiến trúc, luồng dữ liệu và các quyết định thiết kế (Design Decisions) của hệ thống.

## Mục lục Tài liệu (Table of Contents)

1. **[Kiến trúc Hệ thống (System Architecture)](system_architecture.md)**
   - Kiến trúc High-level, Luồng dữ liệu WebSocket (Session Isolation), Dual-write Vector Database, Connection Pooling và Centralized Logging.
2. **[Luồng Xử lý AI & Tracking (AI Pipeline)](ai_pipeline.md)**
   - Chi tiết về MediaPipe, Kalman Filter, Lazy Embedding, quá trình định danh Guest qua HNSW Index và Multi-frame Voting.
3. **[Cấu trúc Cơ sở Dữ liệu (Database Schema)](database_schema.md)**
   - PostgreSQL, Supabase Storage, pgvector HNSW Index (cho cả khách hàng và Guest), cơ chế Dual-write (`vector(512)` và `BYTEA`), Bảng `users` cho phân quyền.
4. **[Kiến trúc Frontend (Frontend Architecture)](frontend_architecture.md)**
   - Next.js App Router, Cơ chế WebSocket-driven Active Prefetching, RBAC (Role-Based Access Control) bảo vệ Route cho Admin/Moderator/Guest.
5. **[Tài liệu API & WebSocket (API Reference)](api_reference.md)**
   - Giao thức truyền phát WebSocket Streaming, các RESTful APIs (bao gồm Login, check-in cooldown, và promote guest).
6. **[Hướng dẫn Vận hành & Bảo trì (Maintenance Guide)](maintenance_guide.md)**
   - Xử lý sự cố, CI/CD, Quản lý tài nguyên Docker.

---
> **Lưu ý:** Hệ thống đang áp dụng những kỹ thuật tối ưu hóa hiện đại nhất ở phiên bản **v1.4.0** như **Track Lifecycle Caching**, truy vấn **pgvector HNSW**, tái sử dụng kết nối qua **ThreadedConnectionPool**, và **Session Isolation** trên WebSocket để đạt độ trễ cực thấp (Sub-millisecond) ở quy mô hàng ngàn khách hàng, đồng thời tối ưu hóa tài nguyên phần cứng.
