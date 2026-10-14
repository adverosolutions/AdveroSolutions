# Sales deck generator: implementation contract

This is the implementation brief for the first reusable version. The approved source is `/Users/lorenzovillarreal/Documents/Codex/2026-10-09/am-i-inside-of-codex-now/outputs/upwork-sales-test/` (latest V4). Preserve that folder and existing job pages. The outer palette, gradients, Inter font, opening layout, navigation, replay placement, and blue CTA are locked. Native software interiors may use their own established styles.

## File ownership

- Runtime worker: `runtime/app.js`, `runtime/shell.html`, `runtime/base.css`, `runtime/components.css`, `assets/inter-variable.woff2`, `tests/runtime.cjs`, `package.json`, `package-lock.json`.
- Platform worker: `runtime/platforms.js`, `runtime/platforms.css`, `platforms.json`, `PLATFORMS.md`.
- Build worker: `build.py`, `schema.py`, `examples/*.json`, `tests/test_build.py`, `README.md`, `CONTENT_BRIEF.md`, `REVIEW_BRIEF.md`, `BATCH_RUNBOOK.md`, `template-lock.json`, and the small superseding notice in the pipeline `UPWORK_PROCESS.md`.
- Main coordinates contract changes; workers do not silently change another worker's interface.

## Data contract (one JSON object per job)

`schemaVersion: 1`, `id` (safe slug), `title`, `systemName`, `account: {name, initials, operatorInitials}`, `personalization: {firstName, source, reviewCount}` (optional), `source: {jobUrl, facts: [string]}` (private provenance), `entities` (nested string/number data for reuse), `cover`, `scenes`, `close`.

Text may reference entity values as `{{lead.name}}`, `{{appointment.display}}`, etc. Resolve from `entities` recursively at build time; reject unresolved references. No raw HTML, CSS, JS, URLs for scripts, or arbitrary markup in the schema. Escape all rendered text. JSON embedded in HTML must safely escape script closing tags and HTML-significant characters.

`cover: {eyebrow, title, accent, caption, anchors: [string], previewSteps: [{title, detail}], footer, beat}`. Use the current approved opening caption exactly: `I've already put this workflow together for you. Let me walk you through how it works.` Personalization supports a supplied/post name or a repeated unambiguous client-contact name supported by at least two separate review entries; no ownership inference.

`close: {eyebrow, title, accent, caption, metrics: [{name, direction: 'up'|'down', aim, definition}], baselineNote, ctaTitle, ctaCopy, beat}`. Keep three directional metrics and the existing full-width blue CTA. Do not fabricate numerical improvement promises.

`scenes` is an ordered list, each `{id, kind, platform, title, caption, beat, details: [string], optional: boolean, content, statuses: [string]}`. Workflow first; record can be optional on the three-minute route. At least one result and one visible proof scene. Short routes omit optional scenes; detailed includes all. Cover and close are appended by the renderer. No auto-advance of chapters.

Supported scene kinds and content:

- `workflow` (platform `ghl`, `n8n`, `make`): `{name, nodes: [{id, type, label, detail}], edges: [{from, to, label?}], runOrder: [nodeId], context: {name, subtitle, fields: [{label,value}], states: [string]}, related: [{title,detail}]}`. Catalog type determines actual action label/icon/shape. IDs unique, edges valid, graph acyclic for this version, nodes max 12, unsupported action/platform fails validation. `runOrder` describes the one sample path; unvisited branches remain inactive. Native node IDs are *visual catalog keys*, not a claim of importable exports.
- `record` (platform `ghl`): `{name, subtitle, sourceTitle, sourceFields: [{label,value}], fields: [{label,value}], events: [{title,detail}], notice}`.
- `messages` (platform `ghl`): `{name, subtitle, fields: [{label,value}], items: [{channel: 'sms'|'email'|'internal', direction: 'incoming'|'outgoing', sender, time, subject?, body}], notice}`.
- `outcome` (platform `ghl`): `{name, subtitle, fields: [{label,value}], stages: [string], stageSequence: [integer], metrics: [{label,value,note}], note, proof?: {label,value,description,sourceNote}}`. Move/highlight the sample contact through stages on replay; counts remain explicitly illustrative.
- `workshop` (platform `ghl`): `{name, subtitle, current: {id,title,date,time}, next: {id,title,date,time}, events: [{title,detail}], followup: {subject,body}, reusable: [string], historyNote}`. Autoplay attendance + follow-up + next workshop; replay resets; keep explicit next-event empty registrations.

Shared render helpers exposed before platform script: `window.SalesUI = {esc, icon, avatar, fields}`. Runtime may instead define them in a preceding IIFE; all files must work concatenated. Platform script exposes `window.SalesPlatforms = {renderWorkflow(scene, job), applyStep(scene, stepIndex)}`. `renderWorkflow` returns native frame HTML (not outer `.demo` or controls). It uses global `PLATFORM_CATALOG` loaded from `platforms.json`; scene data is `scene.content`. `applyStep` updates only the current workflow frame; active nodes follow `runOrder` cumulative, skipped branches stay inactive. Runtime creates outer `.demo.panel`, appends replay controls, and calls platform functions. Scene rendering must not rely on global job IDs.

Use these initial visual action keys (labels/kinds/icons belong to catalog):

- ghl: `facebook_lead`, `assign_user`, `opportunity`, `sms`, `email`, `notification`, `contact_tag`, `event_date`, `wait`, `condition`.
- n8n: `webhook`, `edit_fields`, `if`, `http_request`, `slack`, `gmail`, `google_sheets`, `ai_agent`, `chat_model`.
- make: `custom_webhook`, `google_sheets_add_row`, `router`, `gmail_send_email`, `slack_create_message`, `http_request`.

First version only needs ordinary/branch graphs; if an AI agent subnode is not properly supported, mark that action unavailable and reject it explicitly rather than draw a wrong connector. All unsupported platforms are listed as reference-only with the corresponding existing example path; no GHL fallback.

## Runtime behavior

One job per standalone HTML, no hardcoded job selector. The controls retain Quick/Standard/Detailed, Talking points, Present, Previous/Next and chapter navigation. Same cover and close layout, all copy from spec. First replay state visible immediately; remainder within about five seconds; hold result. Replay and Show result operate inside the demo. Cancel timers on navigation/replay/job unload; rapid navigation cannot mutate another scene. Reduced-motion shows settled state. No scroll hijack or automatic chapter advance. Responsive desktop and 390px; large native canvases may scroll inside their own container but never the page. No external asset fetch or service writes. No old demo names in runtime files.

## Build and batch interface

Python 3.9+ stdlib CLI: `python3 build.py validate SPEC`, `python3 build.py build SPEC --out DIR`, `python3 build.py batch MANIFEST --out DIR`, `python3 build.py lock` (maintainer only). A manifest is `{jobs: [relativeSpecPath, ...]}`. CLI must work from any cwd. Build outputs `page.html`, `recording-script.txt`, `build-report.json` atomically; batch additionally produces an index with each job's status/link and batch report. Reject duplicate slugs and unsafe output paths; fail individual malformed specs without blocking unrelated jobs; overall nonzero if any failed. A build is `built_pending_review`, never automatically visually approved. Stable content/template hashes let a reviewer record the exact version checked. No auto sending, submitting or external publishing.

Use a template-lock manifest to detect drift of shared runtime, palette, font, catalog and compiler files during routine generation. Maintainer lock after accepted implementation, not from a daily content worker. Document this as an integrity check, not a security boundary. Exclude private `source` and evidence from embedded browser data and public recording notes.

Four seed specs: preserve the financial and Skool stories through data (using original V4 for content); add one invented n8n job and one invented Make job to prove distinct adapters and no stale names. Label seed job sources as test fixtures, never saved Upwork jobs. Use valid actual workflow actions and a coherent single sample path.

Build worker writes concise role briefs: Astra main coordinates; explicit `gpt-6.1-sol` worker-heavy/high with `fork_turns:none`, self-contained job brief, isolated job folder, only edits spec/content; independent Astra reviewer/xhigh checks screenshots and behavior. Queue jobs progressively, adapt active worker count to the session's exposed slot limit. A new platform is template-maintenance work, not a daily worker improvisation. Never change global model settings. The pipeline doc points at this newer default and preserves proposal/finalization process.

## Acceptance

All four fixtures compile to self-contained pages from a clean checkout; meaningful validation tests include unresolved tokens, invalid graphs/types, private-data exclusion, escaping, duplicate IDs and batch partial failure. Runtime tests cover routes, immediate/settled/replayed states, cancellation, keyboard controls and reduced motion. Browser visual QA covers desktop opening/workflow/messages/outcome/close for GHL and workflow for n8n/Make, plus 390px. Palette/font match V4. Independent reviewer approval required before accepting each worker's piece. This version creates sales demonstration HTML; real imported automations remain a separate existing process.
