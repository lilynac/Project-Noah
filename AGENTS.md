# Storage requirement

The user requires all Noah development files, generated artifacts, logs, and backups to remain outside iCloud Drive.

- Canonical checkout: `/Users/simseat/Codex/Noah-workspace/work/Project-Noah`.
- Workspace artifacts: `/Users/simseat/Codex/Noah-workspace/outputs` or this checkout’s `outputs/`.
- Launcher: `/Users/simseat/Codex/Noah.app`.
- Never recreate the previous checkout under `~/Documents/Codex`, nor save new project files under Desktop, Documents, or `~/Library/Mobile Documents`.
- This task’s old cwd may still be shown in app context. Always specify the canonical checkout as the working directory.
