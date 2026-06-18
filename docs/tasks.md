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
- [ ] **Supabase Authentication Setup:** Perform OAuth integration and verify project connection.
- [ ] **Create Database Schemas:** Define the PostgreSQL tables for `customers` and `attendance` matching SQLite schema.
- [ ] **Migration Scripts:** Write migration or script to upload local test data to Supabase database.
- [ ] **Enable Supabase Mode:** Update local backend `.env` variables to set `USE_SUPABASE=true` and enter connection credentials.
- [ ] **Validate Connection:** Check startup console logs to confirm `🗄️ Using POSTGRESQL database`.

### Phase 3: Backend Verification
- [ ] Verify `api_customers_overview` correctly queries Supabase.
- [ ] Verify `api_customer_profile` updates/creates records in Supabase.
- [ ] Verify `api_check_in` logs check-in events in the Supabase database.

### Phase 4: Frontend Verification
- [ ] Verify Next.js frontend connects to backend correctly with Supabase storage.
- [ ] Perform real-time camera tracking and ensure overlays show the names saved in Supabase.
- [ ] Test the guest editing interface to verify changes are written to the cloud.

### Phase 5: Team Deployment
- [ ] Set up GitLab CI/CD pipelines (optional).
- [ ] Configure environment variables securely on deployment servers.
- [ ] Merge the feature branch into `main` after review.
