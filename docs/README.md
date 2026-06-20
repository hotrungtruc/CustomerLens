# Face Recognition System - Technical Documentation

Chào mừng bạn đến với tài liệu kỹ thuật của dự án **Front Door AI - Hệ thống Nhận diện Khuôn mặt Thời gian thực**. Tài liệu này được biên soạn dành cho các Software Engineers, AI Engineers và DevOps nhằm cung cấp cái nhìn sâu sắc, toàn diện về kiến trúc, luồng dữ liệu và các quyết định thiết kế (Design Decisions) của hệ thống.

## Mục lục Tài liệu (Table of Contents)

1. [Kiến trúc Hệ thống (System Architecture)](system_architecture.md)
   - Kiến trúc High-level, Luồng dữ liệu qua WebSocket.
2. [Luồng Xử lý AI & Tracking (AI Pipeline)](ai_pipeline.md)
   - Chi tiết về MediaPipe, Kalman Filter, Lazy Embedding, Multi-frame Voting và Vector Search.
3. [Cấu trúc Cơ sở Dữ liệu (Database Schema)](database_schema.md)
   - PostgreSQL, pgvector HNSW Index và SQLite fallback.
4. [Kiến trúc Frontend (Frontend Architecture)](frontend_architecture.md)
   - Next.js App Router, Active Prefetching, RBAC (Role-Based Access Control).
5. [Tài liệu API & WebSocket (API Reference)](api_reference.md)
   - RESTful APIs và Giao thức truyền phát WebSocket.
6. [Hướng dẫn Vận hành & Bảo trì (Maintenance Guide)](maintenance_guide.md)
   - Xử lý sự cố, CI/CD, Docker deployment.

---
> **Lưu ý:** Hệ thống đang áp dụng những kỹ thuật tối ưu hóa hiện đại nhất như **Track Lifecycle Caching**, **pgvector HNSW**, và **Session Isolation** để đạt độ trễ cực thấp (Sub-millisecond) ở quy mô hàng ngàn khách hàng.
