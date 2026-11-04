# Advero instructions and process record

Lorenzo designated Grok Bot as the current operational process source on 2026-11-04. Start with [PROCESS_AUTHORITY.md](PROCESS_AUTHORITY.md), then the relevant business skill and its dated source records. The repo is the maintained record; installed `~/.claude` files are imports, not the canonical copy.

- `skills/`: the 25 business skills; all have portable discovery links under `.agents/skills/`.
- `grok-source/2026-11-04/`: sanitized process exports, source manifests, routine prompts and code evidence from Grok Bot. Imported code is archival and has not been executed.
- `skill-audit/2026-11-04/`: reconciliation status, source coverage, verification and exclusions.
- `synced-skills/`: helper-skill snapshots for Claude and Codex, including supporting assets and licenses. These retain their app-specific dependencies and are not business process authority.
- `agents/`, `scheduled-tasks/`, `global-CLAUDE.md`, `memory/`: retained local instruction records. Historical scheduled-task prompts do not mean a task is currently active.

`sync_from_home.sh` is non-destructive and read-only by default. `--import-new` copies missing files only; conflicts retain the repo version. An exact `--replace <repo-relative path>` imports one intended replacement after saving a backup under `.tmp/config-import-backups/`. No deletion is performed, and credential-bearing records are excluded.

The Grok onboarding builder uses this checkout's skill sources. Rebuild from the repo with `/usr/bin/python3 "Agentic Worklfows/agents/grokbot/build_pack.py"`; parity checks do not depend on a home-folder installation. Existing Grok bots get a dated delta update rather than a fresh onboarding.

A clean clone preserves the instruction files and references. Runtime tools, connected accounts, secrets and hosted app features must still be available in the target environment. The audit lists missing exports and restore dependencies rather than claiming those are bundled.
