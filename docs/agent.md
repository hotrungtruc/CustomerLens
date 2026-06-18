# AI Agent Guidelines & Repository Context

This file serves as custom instructions for any AI assistant (like Antigravity) working on this codebase.

---

## 🤖 Identity & Guidelines

When working on this repository, you must adhere to the following rules:
1. **Always verify database compatibility:** The project supports **SQLite** and **Supabase (PostgreSQL)**. Ensure all SQL queries you generate are compatible with both or checked via `USE_SUPABASE` branching.
2. **Preserve formatting:** Keep existing comment headers and documentation intact.
3. **Check local directories:** Models are saved under `backend/models/`. If they are missing, run the utility `python -m app.utils.download_models` to download them.
4. **Git Flow Discipline:**
   * Do not make direct commits or pushes to `main`.
   * Guide the user to write their code on feature branches (`feature/your-feature`) and use GitLab Merge Requests (MRs).
   * If proposing commands, explain their purpose first.

---

## 📁 Key File Map

* [backend/config.py](file:///c:/Users/teflo/Desktop/Study/VLU\Big%20Data/face-recognition-system/backend/config.py): Main backend configuration variables (Thresholds, model selections, camera settings, processing frames config).
* [backend/db_config.py](file:///c:/Users/teflo/Desktop/Study/VLU\Big%20Data/face-recognition-system/backend/db_config.py): Determines database type switching between SQLite and Supabase PostgreSQL.
* [backend/app/api/routes.py](file:///c:/Users/teflo/Desktop/Study/VLU\Big%20Data/face-recognition-system/backend/app/api/routes.py): Core HTTP endpoints (e.g. process frame, customer information, check-in log, overview mapping).
* [backend/app/core/guest_tracking.py](file:///c:/Users/teflo/Desktop/Study/VLU\Big%20Data/face-recognition-system/backend/app/core/guest_tracking.py): The tracker class implementing the logic to track faces and assign temporary `GUEST_*` and track IDs.
* [backend/app/db/connection.py](file:///c:/Users/teflo/Desktop/Study/VLU\Big%20Data/face-recognition-system/backend/app/db/connection.py): Schema definitions, raw SQL queries for database operations.
* [frontend/src/app/page.jsx](file:///c:/Users/teflo/Desktop/Study/VLU\Big%20Data/face-recognition-system/frontend/src/app/page.jsx): Main dashboard page displaying camera feed overlay and guest overview panels.

---

## ⚠️ Known Gotchas

* **Camera Index:** In `backend/config.py`, the `CAMERA_INDEX` is set to `1` (usually built-in camera). If the feed displays as a blank screen or errors on start, toggle between `0` and `1` or use web-based frames.
* **CORS Settings:** If the frontend is hosted on another server, ensure the origin URL is added to `CORS_ORIGINS` in `config.py`.
* **FastAPI Workers:** The backend runs frame processing on a separate CPU worker thread to avoid blocking FastAPI's async main event loop.
