# Vibe Board: Prompts, Notes & Results

This board is a scratchpad to track prompt ideas, experiment logs, notes, and command snippets for the team.

---

## 📌 Command Reference

### Local Development Commands

* **Run Backend:**
  ```powershell
  cd backend
  .venv\Scripts\Activate.ps1
  python run.py
  ```
* **Run Frontend:**
  ```bash
  cd frontend
  npm run dev
  ```
* **Link Supabase Project:**
  ```bash
  supabase link --project-ref qgwpntwmxpwffccptotj
  ```

---

## 📝 Developer Notes

### Git & GitLab Workflows
* **Rule:** Never push directly to `main` when working in the team.
* **Standard Commands:**
  ```bash
  # Step 1: Sync main branch
  git checkout main
  git pull origin main

  # Step 2: Create feature branch
  git checkout -b feature/your-feature-name

  # Step 3: Stage and commit
  git add .
  git commit -m "Commit description"

  # Step 4: Push to GitLab
  git push origin feature/your-feature-name
  ```

---

## 🧪 Experiments & Prompt Log

| Date | Goal / Prompt | Results / Output | Notes |
| :--- | :--- | :--- | :--- |
| 2026-06-15 | "Configure MCP and Agent Skills for Supabase" | Successfully generated `mcp_config.json` and ran `npx skills add` to import Supabase context. | Installed skills are stored in `.agents/skills/` |
| | | | |
