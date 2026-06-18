# Changelog

All notable changes to the **Face Recognition — Front Door AI** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
