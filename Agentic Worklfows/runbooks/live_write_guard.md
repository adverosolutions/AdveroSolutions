# Live-write guard (Claude Code hook): removed

Removed on 2026-10-10 at Lorenzo's request. Its approval pop-ups stopped agents mid-task.
The hook files (`.claude/hooks/guard_live_writes.*`, `guard_session_check.sh`), their Codex
copies, the `changesets/claude_guard/` installer and its test are gone; the old version is in
git history before that date.

Nothing checks commands before they run. The protection is in the code:
`shared.settings.guard_write` (nothing writes unless the process has `MODE=live` and
`ALLOW_LIVE_WRITES=1`), `load_env()` ignoring both flags in any `.env` file, the test netguard,
and the git-tracked template registry (`git diff -- config/approved_templates.json`).
