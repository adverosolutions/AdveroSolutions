# Shared recording queue runbook

Current Upwork defaults: Astra at `xhigh` coordinates explicit Sol content agents at `high` and independent Astra final review at `max` or `ultra`. The coordinator may adjust these task settings as needed. Default to `max` for routine final review; the coordinator selects `max` or `ultra` per task under Lorenzo's standing preference, without another approval step. The Python tools compile specs and serialize queue changes; they do not select models, fetch jobs or review pages. All Codex sessions on this Mac use the same canonical queue. Proposal copy and Loom finalization remain in `../../UPWORK_PROCESS.md`.

## Daily commands

These commands work from any current directory. Normal sessions omit `--root`:

```sh
PIPELINE=/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline
"$PIPELINE/recording-queue" register "$PIPELINE/jobs/<batch-name>-queue.json"
"$PIPELINE/recording-queue" build <id>
"$PIPELINE/recording-queue" status --json
"$PIPELINE/recording-queue" start --port 8769
```

`build` accepts multiple IDs; omit IDs to build all registered jobs. The store is always `~/Desktop/AdveroSolutions/Coding/upwork-pipeline/.local/recording-queue`, independent of session directory or worktree. A missing spec remains queued while completed jobs advance. Invalid specs and unsupported adapters remain visible without blocking unrelated ready jobs.

`start` is idempotent and returns the URL, PID and reuse result. Restart after reboot with the same command. `serve --port 8769` runs the server in the foreground for diagnostics. Both serve the read-only view at `http://127.0.0.1:8769/`; neither opens a browser. The view refreshes every three seconds and opens a selected demo in a new tab. Queue changes happen through the CLI, not HTTP writes.

## Intake and authoring

1. Main reads `UPWORK_PROCESS.md`. Lorenzo may paste 16 jobs into chat or request saved jobs through the existing connector. Main extracts one original `jd.txt` per job, preserves metadata and questions, and writes the manifest; Lorenzo is never asked to write JSON. Use canonical `jobs/<descriptive-slug>-<job-id>/` source folders. Without an ID, use a stable collision-resistant suffix and keep the missing ID/URL uncertainty private. Reuse the same job folder rather than creating duplicates.
2. Register all entries before authoring. A manifest has this shape:
   ```json
   {"jobs":[{"id":"job-slug-123","title":"Original job title","spec":"job-slug-123/deck-spec.json","jobUrl":"https://www.upwork.com/jobs/~02123"}]}
   ```
   Here the manifest lives in `jobs/`; spec paths resolve relative to its directory, or may be absolute. `jobUrl` is optional. ID and spec identity must stay consistent; use the same ID in `deck-spec.json`. Same ID/same path is idempotent; conflicting ID/path is refused. Missing specs are valid queue entries. Never overwrite another job to resolve a collision.
3. Main uses `gpt-6-astra` at `xhigh`. Select each content agent as `gpt-6.1-sol` at `high`, using an ordinary generic/default Codex agent where supported, explicit model/effort overrides and `fork_turns: none`, with `CONTENT_BRIEF.md`, original requirements, supported adapter keys, a seed spec and its precise assigned folder. Check current tool support before dispatch and prevent inherited role defaults from replacing the selected effort; do not silently substitute settings. Workers write only their spec and private evidence. They do not register, build, approve, edit queue state or alter shared assets.
4. Use the exposed capacity, currently four total agents including main in this session. Start at most three workers; as one finishes, use that slot for review. A steady queue can run two workers and one reviewer beside main. A six-agent pool is a future configuration only after verification in a fresh session; never edit global config. Separate user-requested batch chats follow the coordination procedure below; do not create extra chats for ordinary subtasks or assume they increase account capacity.
5. As specs arrive, main runs `recording-queue build <id>` and gives the exact generated page, script, report, spec, source and original requirements to an independent generic/default Codex agent where supported, explicitly selecting `gpt-6-astra` at `max` or coordinator-selected `ultra`, with `fork_turns: none` and `REVIEW_BRIEF.md`. Current artifacts are under `.local/recording-queue/public/jobs/<id>/`; `status --json` supplies public page/script URLs. Show results progressively. A build is not ready to record until independently approved.

## Separate batch chats and the dot

Lorenzo can request separate Codex chats for a batch from an existing chat or from Arnold, his dot. The controlling chat can use the app's `create_thread` capability when available. New chats do not inherit this conversation automatically; the saved files and a precise assignment are the handoff. Reading this runbook is sufficient to recover the process, but saving it does not install knowledge into the dot's private memory.

1. Intake once: preserve the original posts, assign unique job IDs and source folders, register the full manifest, and start the canonical queue. Check existing queue entries before dispatch so an existing job is not built twice.
2. Divide the jobs into disjoint batches, normally three or four jobs per chat. For 16 jobs, four chats of four is a planning option, not a verified concurrency guarantee. Start with the capacity the app actually accepts and keep remaining batches pending. All chats share account usage limits; never promise unlimited parallelism or bypass a limit by creating chats.
3. Call `list_projects`, select the existing AdveroSolutions repository project, and create local chats only when Lorenzo has requested them. Use `gpt-6-astra` with `xhigh`, as Lorenzo requested for orchestration. Each batch coordinator uses the Sol content workers and independent Astra reviewers above, within its actual exposed capacity. Use subagents for subtasks inside each batch; do not recursively create chats. Do not create a worktree unless Lorenzo requests one.
4. Give each chat the handoff below with only its assigned IDs and absolute source paths. Save its returned thread ID, host ID and assigned IDs in a controller-owned dispatch note under `.local/recording-queue/`. A returned setup/client ID is not a ready thread ID. Keep one owner per job; the queue lock protects queue mutations, not two agents writing the same source spec.
5. Monitor with `wait_threads`, using returned cursors and up to eight targets per call. Read details only when needed. Follow-up messages require Lorenzo's authorization to message the destination chat. Child chats finish with their results; the controller reads them without requiring a message back. Report ready jobs progressively from the canonical queue. On a resumed controller, inspect recorded thread IDs and queue status before restarting or duplicating work.
6. Batch chats leave Git commits/pushes and proposal finalization to the controller. The controller saves reviewed sources by explicit paths after batches finish. Finalization updates the shared proposal log and is performed serially after Lorenzo supplies the actual Loom details. All demos still appear at `http://127.0.0.1:8769/`.

Use this starting message for each requested batch chat, filling the bracketed assignment before sending:

```text
Read /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/AGENTS.md, UPWORK_PROCESS.md and templates/sales-deck/BATCH_RUNBOOK.md. You coordinate only these assigned jobs: [exact job IDs, original-post paths and source folders]. The controller already registered them in the shared recording queue. Do not fetch another batch or create duplicate job folders. Use the canonical recording-queue wrapper without --root and operate only on your assigned IDs. Use Sol content workers and independent Astra review as specified in the runbook; preserve all locked design assets. Build and record independently approved exact-page verdicts as jobs finish. Draft proposals using UPWORK_PROCESS.md. Do not create other chats, change global configuration, commit/push, finalize proposals, send messages, submit applications or mark jobs recorded. Finish with each job's ID, queue status, demo URL, proposal path and any unresolved issue. The controller will read your result.
```

For Arnold or a fresh controlling chat, Lorenzo can use: "Read /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/templates/sales-deck/BATCH_RUNBOOK.md. Create separate Astra batch chats for these jobs, coordinate their work, and send them any follow-up instructions needed. Use our shared recording queue." The controller must have the actual job posts or an explicit saved-job request before starting builds; the runbook alone is not a request to launch jobs.

## Review and recording

Main records the reviewer's exact verdict and page SHA-256:

```sh
"$PIPELINE/recording-queue" review <id> --verdict approve \
  --page-hash <reviewed-page-sha256> --notes '<independent review evidence>'
```

Use `--verdict reject` for a failed review. The CLI verifies the artifact identities before recording the receipt. Send precise defects to a content agent with a task-specific repair brief and explicit supported model/effort settings, rebuild, and request a new independent review. Content workers never approve their own work. Unsupported native tools/actions require approved adapter maintenance; initial support is GHL, n8n and Make, never a GHL substitution for another tool.

Exact unchanged spec/template/page/script and valid review receipts allow reuse, including approved or recorded jobs. Any changed generation resets review. A template change does not automatically approve previously ready pages, even when the story is unchanged. A receipt from an older pilot may be carried only after independent approval is evidenced and the exact reviewed page hash matches the queue artifact; otherwise review again.

Lorenzo opens the queue only when he requests it. After his actual Loom recording:

```sh
"$PIPELINE/recording-queue" recorded <id> --loom <actual-Loom-share-URL>
"$PIPELINE/recording-queue" reopen <id>
```

`--loom` is optional when he confirms recording before sharing the URL. `reopen` is for a new recording. These markers do not finalize proposals or log `proposals.csv`; keep the existing finalizer, runtime, locked copy and manual Upwork submission process. At each handoff report the job link, sample path, queue status and unresolved factual questions.

## Shared state and diagnostics

All sessions may register/build/review through the wrapper. Its OS lock serializes shared mutations; only main coordinators run queue commands, while workers author isolated specs. Queue registration order is the recording order; leave historical `jobs/_ORDER.txt` alone rather than racing on a second order list. Coordinate ownership if two sessions touch the same source spec. Never hand-edit the registry, receipts or generated index. Never run `build.py batch --out` into the shared queue; that utility is only for isolated pilots/tests.

Runtime state/pages under `.local/` are durable, private and git-ignored. Keep source jobs, docs, fixtures, generator and version lock tracked. Do not delete `.local/` to fix a job or restart a server. Routine generation verifies the template lock; workers never refresh it. Explicit shared-template maintenance needs a candidate lock and new independent checks after repairs.

- If a job is absent, inspect `status --json`, confirm its manifest ID and resolved spec path, then register the manifest again.
- If a job is queued, finish its missing spec and build its ID. If it fails, use the build error to fix its spec or report the adapter requirement.
- If approval is refused, compare the reviewer's page hash to the current report; rebuild and review changed artifacts rather than bypassing the check.
- If the view is unavailable after reboot, run `start --port 8769` again. If that fails, inspect its error and run `serve --port 8769` for foreground diagnostics. Do not kill an unrelated process occupying the port.
- If the view looks stale, inspect CLI status and reload the queue; do not repair its HTML or registry manually.

`--root <absolute-directory>` is only for isolated tests or deliberate machine portability, and may appear before or after the command. A relocated installation must use one agreed absolute queue root for every session on that machine; migrate its source paths deliberately. This is local persistence, not cross-device cloud sync. Git contains the reproducible sources, not the live queue or recording receipts.

## Optional pilot bootstrap

`examples/shared-queue.json` registers four test fixtures, not saved Upwork jobs. It uses filenames relative to its own directory. For an isolated test:

```sh
"$PIPELINE/recording-queue" --root /private/tmp/upwork-queue-pilot register \
  "$PIPELINE/templates/sales-deck/examples/shared-queue.json"
"$PIPELINE/recording-queue" --root /private/tmp/upwork-queue-pilot build
"$PIPELINE/recording-queue" --root /private/tmp/upwork-queue-pilot status --json
```

To seed the canonical queue deliberately, omit `--root` from register/build. Every generated fixture still needs an independent review receipt before it is ready. Never treat fixture stories as actual saved-job intake or automatically approve them because the source pilot was approved.

## Paste-ready kickoff for a fresh chat

```text
Read /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/AGENTS.md and UPWORK_PROCESS.md, then templates/sales-deck/BATCH_RUNBOOK.md. Use the shared recording-queue wrapper with its canonical default; do not make a new per-chat store or change global configuration. Process the jobs I paste below: preserve every original post in a unique source job folder, prepare/register the manifest yourself, and use isolated Sol content workers with independent Astra review. Build and record exact-hash verdicts through the queue CLI as jobs finish. Preserve the approved template and locked proposal/finalization process. Report ready jobs progressively; do not open a browser until I ask. I do not need to prepare JSON.

[Paste the jobs here, or ask for the saved-job batch.]
```
