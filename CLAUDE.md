# Friday: rules for Claude Code
- Voice-first personal assistant. Phases and gates are in the Claude Project; we are in Phase 7 (final inspection). Fix only bugs the eval or tests show. New ideas go to the Backlog, not into v1.
- Windows 11 (Command Prompt). Venv: .venv. Run tests with `python -m pytest -q` and lint with `ruff check friday tests`. Keep both clean.
- Never open, print or edit .env, .secrets/ or any file with keys or tokens. Never commit them.
- Ask before changing more than one file or anything outside the task. Show the plan first.
- Commit only the files you changed, by name. Never `git add .`. Do not push or tag unless asked.
- Never invent measurements. Report numbers with counts.