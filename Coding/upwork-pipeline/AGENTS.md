# Upwork pipeline instructions

Read `UPWORK_PROCESS.md` first, then `templates/sales-deck/BATCH_RUNBOOK.md`. They define the current demo, proposal and recording process; older page-builder briefs and the shared Upwork skill are historical where they disagree.

Use the pipeline's `recording-queue` wrapper from any working directory. Normal sessions on this Mac all use its default store at `~/Desktop/AdveroSolutions/Coding/upwork-pipeline/.local/recording-queue`. Do not derive a store from the current directory, worktree or chat. `--root` is only for isolated tests or deliberate machine portability.

Lorenzo can paste a batch of jobs into chat or ask for saved jobs through the existing Upwork connector. Main extracts each original post into `jobs/<descriptive-slug>-<job-id>/jd.txt`, keeps private evidence there, and assigns one `deck-spec.json` per job. Use a stable collision-resistant suffix when a pasted post has no job ID; never invent a job URL or overwrite another job. Main writes and registers the manifest; Lorenzo does not need to write JSON.

Daily content workers own only their assigned spec and private evidence. Main uses the queue CLI for registration, builds and review receipts. Independent Astra review must identify the exact page hash before main records approval. Every changed generation needs a new review; built, rejected or adapter-blocked pages are not ready to record. Follow `templates/sales-deck/CONTENT_BRIEF.md` and `REVIEW_BRIEF.md` there.

All Codex sessions may add work through the same queue CLI, which locks shared mutations. Queue registration order controls recording; leave historical `jobs/_ORDER.txt` alone. Never edit its registry or index by hand, and never run `build.py batch --out` against the shared queue. `build.py` remains an isolated pilot/test utility. Runtime pages and state under `.local/` are private, durable and ignored by git; source jobs, compiler, docs, fixtures and the version lock are tracked.

Preserve the approved colors, Inter font, opening caption and CTA. Initially supported native adapters are GHL, n8n and Make; unsupported tools/actions require explicit adapter maintenance, never a GHL fallback. Content workers never change shared assets or the lock. Do not change global model/agent configuration. Use the capacity actually exposed: currently four total agents including main; six is a future configuration only after verification in a fresh session.

Start/restart the local queue with `./recording-queue start --port 8769`; it returns `http://127.0.0.1:8769/` without opening a browser. Start is idempotent. The read-only recording view refreshes every three seconds and opens a selected demo in a new tab. Open it for Lorenzo only when requested. Mark a job recorded only after his actual Loom recording, using `recorded ID --loom URL` when supplied. Keep the locked proposal, finalizer and manual Upwork submission rules in `UPWORK_PROCESS.md`.

This is one local queue shared across sessions on the same Mac, not cross-device cloud sync. Use the runbook for diagnostics and portability.
