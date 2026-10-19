# Reusable sales decks

Current visual preparation: [Native screen library](visual-reference/README.md), [interactive reference board](visual-reference/index.html), and [screen contract](visual-reference/SCREEN_CONTRACT.md). These distinguish researched references, missing captures and unimplemented native screens; they do not approve the rejected adapters.

Generate one standalone, interactive sales demonstration per job. Each page contains its font, CSS, native workflow adapters and data. It makes no service calls and creates no importable automation. The approved V4 opening, palette, font and close are shared template assets; content varies through a validated JSON spec.

Use this lane for the finished-product `page.html` prop. Keep the existing proposal and finalization process in `../../UPWORK_PROCESS.md`.

## Shared queue (daily default)

Python 3.9+ and its standard library are sufficient. Use the path-independent pipeline wrapper from any directory:

```sh
PIPELINE=/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline
"$PIPELINE/recording-queue" register "$PIPELINE/jobs/<batch-name>-queue.json"
"$PIPELINE/recording-queue" build <id>
"$PIPELINE/recording-queue" status --json
"$PIPELINE/recording-queue" start --port 8769
```

All normal Codex sessions on this Mac share `~/Desktop/AdveroSolutions/Coding/upwork-pipeline/.local/recording-queue`; no working-directory or chat-specific store. `--root` is reserved for isolated tests or deliberate portability. Registration accepts `{ "jobs": [{ "id": "unique-job-id", "title": "Job title", "spec": "relative/or/absolute/deck-spec.json", "jobUrl": "optional original URL" }] }`. Relative spec paths resolve from the manifest directory. Missing specs remain queued; same ID/same path is idempotent; conflicting IDs are refused. Main prepares this JSON from pasted or saved jobs, not Lorenzo.

`build [IDs]` builds selected jobs or all registered jobs if IDs are omitted. It reuses an exact unchanged generation only when spec/template/page/script hashes and its review receipt agree. Changed inputs reset review; unrelated failures remain visible while ready jobs advance. Main records independent review against the exact page:

```sh
"$PIPELINE/recording-queue" review <id> --verdict approve \
  --page-hash <reviewed-page-sha256> --notes '<independent Astra review evidence>'
```

Use `reject` for rejected reviews. The command checks artifact hashes and records a supplied verdict; it cannot perform or authenticate the independent visual review. Workers cannot approve their own pages. Template updates require new review; do not copy old approvals onto changed pages.

`start --port 8769` is idempotent and restarts the service after reboot; `serve --port 8769` runs in the foreground. Both expose the read-only queue at `http://127.0.0.1:8769/` without opening a browser. It refreshes every three seconds and opens a selected demo in a new tab. `status --json` supplies page/script URLs. Artifacts live under `.local/recording-queue/public/jobs/<id>/`; source specs and proposal files stay in canonical `jobs/<unique-slug>/` folders.

Only after Lorenzo's actual Loom recording, main uses `recorded <id> --loom <URL>` (URL optional); `reopen <id>` marks a job for another recording. Keep the existing proposal finalizer separately. Shared queue mutations use the CLI's OS lock. Never edit its registry/index manually or run `build.py batch --out` into the shared queue. Runtime state is durable, private and git-ignored; generator, docs, source jobs, fixtures and the version lock stay tracked. There is no cross-device cloud sync.

Read `BATCH_RUNBOOK.md` for intake, agent dispatch and capacity, diagnostics, optional pilot bootstrap and a fresh-chat kickoff prompt. Use ordinary generic/default Codex agents with task-specific briefs and explicit supported settings: Sol `medium` for coordination and content, with one focused independent Astra `high` final review. Read `OPERATING_POLICY.md` for speed and usage controls and `visual-reference/README.md` for native product-surface evidence. Use `fork_turns: none` for explicit overrides; inherited role defaults must not replace the selected effort. `examples/shared-queue.json` contains four fixture entries for reproducible bootstrap; fixtures still require independent exact-page review receipts.

## Isolated compiler utilities

`build.py` remains useful for validation and isolated pilots/tests, outside the shared store:

```sh
DECK="$PIPELINE/templates/sales-deck"
/usr/bin/python3 "$DECK/build.py" validate "$DECK/examples/financial.json"
/usr/bin/python3 "$DECK/build.py" build "$DECK/examples/financial.json" --out /private/tmp/financial-deck
/usr/bin/python3 "$DECK/build.py" batch "$DECK/examples/batch.json" --out /private/tmp/sales-deck-pilots --resume
```

Each generation writes `page.html`, `recording-script.txt` and `build-report.json`. Files are staged before atomic replacement; the report is committed last, so readers verify its page/script hashes for a consistent generation. Do not run competing compiler commands into one folder. Batch specs must be contained relative paths; duplicate slugs fail before generation. Missing/invalid jobs fail independently. `--resume` reuses only consistent unchanged inputs/artifacts/receipts. The isolated utility's `record-review` remains available for isolated test folders; use the queue's `review` command for registered jobs.

## Content and native tools

The exact schema is implemented in `schema.py`. Unknown keys, raw markup, executable URLs, missing fields, excessively long copy, unresolved or cyclic entity tokens and malformed graphs produce readable errors. `{{lead.name}}` resolves from nested `entities`; entity leaves are strings or finite numbers. Use public sample data only in entities. Put private job URLs, evidence and source facts exclusively in `source`, and personalization provenance in `personalization`. Those fields are removed before browser embedding and recording-script generation. Repeated review names need at least two separate unambiguous entries, never an inference of ownership.

Each job begins with a required workflow and contains a required outcome or workshop proof scene. Optional record scenes appear only in Detailed. The shared renderer supplies cover and close. Keep the exact approved opening caption, three directional metrics and the blue call panel. Directional aims cannot contain numerical promises; reviewers check the remaining copy for unsupported claims.

`platforms.json` is the available action catalog. A native workflow has one root trigger, 2–12 nodes, a connected acyclic graph, and a sample `runOrder` that follows edges to a terminal node. Unvisited branches stay inactive. n8n If edges require distinct `true`/`false` labels. Unavailable actions and unsupported platforms return `requires_adapter`; no GHL fallback is allowed. Node keys are visual catalog identifiers, not verified import module IDs.

The n8n and Make pilots explicitly request a GoHighLevel destination, so the native HTTP Request handoff and GHL confirmation/result scenes describe both tools. A native screen for another destination needs its own adapter. Custom project outputs can use the explicitly labelled workbench; Claude Code/Codex use task transcripts, and carousel previews can include bounded inline photographs. See `PLATFORMS.md` and `extension-contract.md` for current support.

Four seed jobs are test fixtures, never saved Upwork jobs: financial and Skool preserve the V4 stories, while n8n inbound routing and Make order handoff are invented integration briefs. They use distinct accounts, people and paths.

## Template maintenance

Routine generation verifies `template-lock.json` for compiler, schema, catalog, runtime, palette and font drift. This is an integrity check and an instruction boundary, not a security boundary. Only explicit template maintenance changes shared assets. When all candidate files have settled, the maintainer records a candidate lock so pages can be built for review:

```sh
/usr/bin/python3 "$DECK/build.py" lock
```

Any repaired shared file requires a refreshed candidate lock and new independent checks. Locking records file identity; it grants no visual approval. Final acceptance requires independent reviewer approval. Content workers never update the lock.

## Checks

```sh
/usr/bin/python3 -m pytest -q -p no:cacheprovider "$DECK/tests/test_build.py"
```

If pytest is unavailable, use `/usr/bin/python3 -m unittest discover -s "$DECK/tests" -p test_build.py`. Runtime behavior checks live in `tests/runtime.cjs`. See `CONTENT_BRIEF.md`, `REVIEW_BRIEF.md` and `BATCH_RUNBOOK.md` for the daily authoring and progressive review process. No automatic publishing, Upwork submission or message sending is part of this tool.
