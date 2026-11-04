# Restore notes for the 2026-11-04 source snapshot

Use PROCESS_AUTHORITY.md before interpreting any historical procedure. The four exports preserve instruction/code evidence and exact current routine prompts; they intentionally exclude secrets and live customer/transaction state. A fresh machine still needs the relevant accounts, connectors and runtime dependencies. No production script was executed in this reconciliation.

## Known code and configuration limits

- `fourth-export/source_files/advero/ask_opus.py` cannot be parsed as exported: the redactor replaced part of its environment lookup with `[SECRET]` at line 885. Preserve this original evidence. The repository's legacy onboarding helper is a separate historical implementation; do not silently substitute it or claim either is the current Grok execution path. Current model transport must be confirmed in the target environment before use.
- Other archived Python source parsed (53 files). Bash wrappers were checked with `bash -n`. Syntax checks do not validate API behavior or approve execution.
- Imported modules include requests, bs4, PIL and optional video libraries such as faster_whisper. These are observed imports, not a verified install manifest. The exported dependency manifests cover the dashboard only; no Python lockfile was supplied.
- Google file IDs redacted from part 2 can be recovered only where an actual matching non-redacted first/third/fourth source provides them. Never guess a missing value. Secrets remain in the secure stores and are not reconstructed from this repo.
- The fourth export lists absent historical files and dated filename patterns separately from private-data exclusions. Deleted-bot original prompts are unavailable; current owner rebuilds are preserved with that fact.

## Repository checks

Run `/usr/bin/python3 ClaudeConfig/tools/check_inventory.py` for current skill link and source-hash checks. Run `/usr/bin/python3 -m unittest discover -s ClaudeConfig/tools/tests -q` for the config-import safety checks. The engine test command remains the netguard command in its project instructions. Keep tests offline and do not install or execute an exported production tool as part of this verification.

The recovered `ClaudeConfig/codex/setup_codex.sh` is a historical setup record, not a current restore command. Review it before any installation; it still reflects the earlier home-folder arrangement. Repo business skills are maintained under ClaudeConfig/skills and discovered with repo-relative links.
