# Storage requirement

The user requires all Noah development files, generated artifacts, logs, and backups to remain outside iCloud Drive.

- Canonical checkout: `/Users/simseat/Codex/Noah-workspace/work/Project-Noah`.
- Workspace artifacts: `/Users/simseat/Codex/Noah-workspace/outputs` or this checkout’s `outputs/`.
- Launcher: `/Users/simseat/Codex/Noah.app`.
- Never recreate the previous checkout under `~/Documents/Codex`, nor save new project files under Desktop, Documents, or `~/Library/Mobile Documents`.
- This task’s old cwd may still be shown in app context. Always specify the canonical checkout as the working directory.

# Applying the shared learning and record practices

When planning or changing Noah's development workflow, memory, research, or retrospective features, use these projects as design references:

- `/Users/simseat/Codex/ai-education`: start from a clear purpose and observable outcome; let AI assist with organization while a person verifies facts and decides what to accept. Distinguish planned, prepared, performed, validated, and accepted work. Do not copy its course-specific materials into Noah.
- `/Users/simseat/Codex/it-work-experience`: distinguish participant reports, system evidence, hypotheses, and unknowns. Record impact, response, recovery checks, and cleanup. Do not infer a cause from timing alone or copy environment-specific settings.
- `/Users/simseat/Codex/theme-story-system`: group related records by theme, preserve source links, avoid counting summaries as separate events, and use 起承転結 only when it helps a retrospective or article. Keep claims tied to evidence and do not invent a turning point.

Apply these as development and product-design principles, not as a requirement to rewrite Noah's existing memory system. Noah's conversational memory and runtime logs are user data; keep them separate from development records, exclude them from Git, and never turn private conversation into a development example without explicit direction. Do not send private memory to external services beyond the behavior already documented and authorized for the task.

For substantive work, record the goal and checkable completion conditions, important decisions and their owners, changed artifacts, verification results and limits, user feedback, and the next step. Keep concise task records rather than full chat transcripts. Treat generated summaries as drafts until their source links and factual claims have been checked.
