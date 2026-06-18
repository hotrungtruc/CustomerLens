# Changelog

All notable changes to the **Face Recognition — Front Door AI** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.0] - 2026-06-18
### Added
* **Connection pooling** — Replaced per-query `psycopg2.connect()` with `psycopg2.pool.ThreadedConnectionPool` (min=2, max=10). Connections are returned to the pool on close instead of being destroyed.
* **Guest embeddings → pgvector** — Guest (unidentified) face embeddings are now written to `customer_embeddings` with the pgvector `vector(512)` column, unifying guest and known-customer search under the HNSW index.
* **Guest promotion → pgvector sync** — `promote_guest()` now writes the promoted embedding to pgvector so the vector database stays in sync with the in-memory face bank.
* **Supabase Storage module** (`app/db/supabase_storage.py`) — Upload, download (public URL), and delete customer photos via the Supabase Storage REST API. Falls back to local filesystem when `SUPABASE_PROJECT_URL` / `SUPABASE_SERVICE_ROLE_KEY` are not set.
* **Image migration script** (`scripts/migrate_images.py`) — One-time batch upload of local `data/images/` to a Supabase Storage bucket (`customer-images`).
* **Centralized logging** (`app/utils/logger.py`) — Structured `[HH:MM:SS] LEVEL module: message` format replacing all scattered `print()` statements.

### Changed
* `load_customer_image_base64()` now tries Supabase Storage public URL first, then falls back to local filesystem.
* `db_config.py`, `insight_embedding.py`, `guest_tracking.py` — All `print()` calls replaced with `logger.info/warning/error`.
* `useProfilePrefetch` hook now guards against non-admin users to prevent 401 spam.

## [1.3.0] - 2026-06-18
### Added
* **WebSocket real-time streaming** — Replaced HTTP polling with persistent `ws://localhost:8000/ws/{session_id}` connections for 10fps frame streaming and live annotation delivery.
* **Session isolation** — Each browser tab gets a unique `session_id` (via `sessionStorage`), so multiple users with different cameras receive only their own bounding boxes and customer data.
* **pgvector HNSW vector search** — Enabled the `pgvector` extension on Supabase with a `vector(512)` column and HNSW index (`m=16, ef_construction=64`) on `customer_embeddings` for sub-millisecond approximate nearest-neighbor face matching.
* **Dual-write embedding storage** — New face embeddings are written to both the legacy `BYTEA` column and the new `vector(512)` column for backward compatibility.
* **Backfill migration script** (`scripts/backfill_vectors.py`) — One-time script to convert existing BYTEA blobs to pgvector format; successfully migrated 9/9 rows.
* **`vector_search.py` module** — New database module with `search_similar_faces()` (HNSW query) and `insert_embedding_with_vector()` (dual-write insert).
* **Track Lifecycle Caching** — Customer profile metadata is cached per-track in `TrackState.cached_profile`, reducing DB queries from ~10/sec/face to 1 per track lifetime.
* **Cache invalidation** — `PUT /api/customer_profile` automatically clears stale cached profiles across all active camera states.
* **WebSocket-driven Active Prefetching** — New `useProfilePrefetch` React hook background-fetches customer profiles when the WebSocket detects a recognized face, enabling instant click-through to detail pages.
* **Prefetch consumption on detail page** — `customers/[id]/page.jsx` reads prefetched data from `sessionStorage` for zero-latency rendering, with background re-validation.

### Changed
* `GuestTrackManager._recognize_face()` now uses pgvector HNSW search when `USE_SUPABASE=true`; falls back to in-memory cosine similarity for SQLite.
* `_build_customers_payload()` refactored to accept `camera_state` parameter and use track-level caching.
* `ensure_schema()` now creates the pgvector extension, vector column, and HNSW index on PostgreSQL startup.
* `_migrate_embeddings()` dual-writes BYTEA + vector when target is PostgreSQL.

### Fixed
* Customer embeddings deduplication in `production.db` and Supabase.
* Concurrent multi-user bounding box isolation (each session receives only its own annotations).

## [1.2.0] - 2026-06-18
### Added
* User authentication system using SQLite (`users` table).
* Backend session management using random hex tokens and password hashing via SHA-256.
* Backend login endpoint `POST /api/login` and require_admin check guards on modification endpoints.
* Modern, premium glassmorphism user login page `/login` on the frontend.
* Role-based access control (RBAC) in Next.js frontend:
  * Guest role: restricted to homepage overview; other sidebar items locked.
  * Moderator role: access to overview and camera views; camera feed list dynamically filtered to permitted items (`DSLR-002`, `DSLR-003`).
  * Admin role: full admin access to view, edit, and navigate all subpages.
* Sidebar user context display showing active username, role, and logout action.

## [1.1.0] - 2026-06-15
### Added
* Supabase configuration endpoint supporting cloud PostgreSQL connection.
* Model Context Protocol (MCP) server settings configuration for local agent db support.
* Supabase agent skills (`supabase`, `supabase-postgres-best-practices`) for the project.
* Project documentation guidelines (`context.md`, `tasks.md`, `vibe.md`, `changelog.md`, `agent.md`).

---

## [1.0.0] - 2026-06-13
### Added
* Real-time face detection on browser cameras using MediaPipe Face Mesh.
* Face recognition models using AdaFace IR50/GhostFace ONNX model.
* Fast tracking of multiple faces with lazy face embedding computation.
* SQLite Database system for storing guest information and attendance logs.
* Next.js web application for overlays, alerts, and guest registration/editing.
* FastAPI backend integration running on port `8000`.
