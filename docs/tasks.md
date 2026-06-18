# Project Tasks & Progress Tracking

## Definition of Done (DoD)
Before any task or feature is marked as complete:
- [ ] **Code Quality:** Code compiles without errors, has no debug print logs left behind, and uses the established design/architectural pattern.
- [ ] **Testing:** Manual or automated tests verify that the feature works under expected conditions.
- [ ] **Database Migration:** Database changes are scripted (schema definitions, tables, or seed files) and compatible with both SQLite and Supabase PostgreSQL.
- [ ] **Documentation:** `changelog.md` and related documents are updated.
- [ ] **Git Flow:** The branch is pushed to GitLab and a Merge Request (MR) is created for team review.

---

## Roadmap & Task Checklist

### Phase 1: Local Setup & Review
- [x] Analyze codebase structure (backend FastAPI, frontend Next.js)
- [x] Configure Supabase local development MCP config
- [x] Install Supabase agent skills for pairing assistance

### Phase 2: Database Migration to Supabase
- [x] **Supabase Authentication Setup:** Perform OAuth integration and verify project connection.
- [x] **Create Database Schemas:** Define the PostgreSQL tables for `customers` and `attendance` matching SQLite schema.
- [x] **Migration Scripts:** Write migration or script to upload local test data to Supabase database.
- [x] **Enable Supabase Mode:** Update local backend `.env` variables to set `USE_SUPABASE=true` and enter connection credentials.
- [x] **Validate Connection:** Check startup console logs to confirm `[DATABASE] Using POSTGRESQL database`.

### Phase 3: Backend Verification
- [x] Verify `api_customers_overview` correctly queries Supabase.
- [x] Verify `api_customer_profile` updates/creates records in Supabase.
- [x] Verify `api_check_in` logs check-in events in the Supabase database.

### Phase 4: Frontend Verification
- [x] Verify Next.js frontend connects to backend correctly with Supabase storage.
- [x] Perform real-time camera tracking and ensure overlays show the names saved in Supabase.
- [x] Test the guest editing interface to verify changes are written to the cloud.

### Phase 5: Performance & Scalability (v1.3.0)
- [x] **WebSocket Migration:** Replace HTTP polling with persistent WebSocket connections for real-time frame streaming.
- [x] **Session Isolation:** Ensure multi-user concurrency with unique `session_id` per browser tab.
- [x] **pgvector HNSW Vector Search:** Enable pgvector extension, add `vector(512)` column with HNSW index to `customer_embeddings`.
- [x] **Backfill Migration:** Run `scripts/backfill_vectors.py` to convert 9 BYTEA blobs → pgvector format.
- [x] **Track Lifecycle Caching:** Cache customer profiles per-track to eliminate redundant DB queries (~10/sec/face → 1/track).
- [x] **WebSocket Active Prefetching:** Background-fetch customer profiles on recognition for instant navigation.
- [x] **Dual-write Embeddings:** New embeddings written to both BYTEA and vector columns for backward compatibility.
- [x] **Cache Invalidation:** `PUT /api/customer_profile` clears stale track caches across all camera states.

### Phase 6: Production Hardening (v1.4.0)
- [x] **Guest Embeddings → pgvector:** Store guest (unidentified) face embeddings in the vector database instead of in-memory pickle files for unified matching.
- [x] **Connection Pooling:** Replace per-query `psycopg2.connect()` with `psycopg2.pool.ThreadedConnectionPool` for production-grade connection management.
- [x] **Image Storage Migration:** Move customer photos from local `data/images/` to Supabase Storage for cloud-native access. *(Module ready; requires `SUPABASE_PROJECT_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env` to activate)*
- [x] **Cleanup Debug Logs:** Remove or gate all remaining `print()` debug statements behind a logging framework (`app/utils/logger.py`).

### Phase 7: Team Deployment
- [ ] Set up GitLab CI/CD pipelines (optional).
- [ ] Configure environment variables securely on deployment servers.
- [ ] Merge the feature branch into `main` after review.
