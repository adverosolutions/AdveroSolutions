---
name: upwork
description: Lorenzo's complete Upwork proposal process - build the prop (n8n JSON, Make blueprint, GoHighLevel import JSON, or a native Excalidraw flowchart), private assessment, Loom beat sheet, and the locked proposal copy, one job or a batch of saved jobs. Use when he pastes a job post, says his saved jobs are ready, asks to load a build by name, or invokes /upwork.
---

> **Superseded in part (2026-10-09):** the current end-to-end process (finished-product pages, Loom over the page, locked proposal format, finalize, screening questions) is `upwork-pipeline/UPWORK_PROCESS.md`. It wins wherever this file disagrees.

# Upwork Proposal Process (v4, quality overhaul 2026-09-22)

This is the vault. When a rule here conflicts with an older memory, this file
wins.

Tool root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator`
Pipeline root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline`

Every shell command must `cd` into the tool root first; the shell cwd resets
between calls.

## The bar

Two metrics. Quality first: a build so specific to this client that they would
pay $2,000 for it and could not mistake it for anyone else's. Speed second:
fewest minutes from saved job to submitted proposal.

Why this version exists: Mark (webinar invites to an old list) replied "that's a
generic loom". His chart matched an older client's chart on 9 of 14 steps, beat 1
never named him or his webinar, the chart never asked for his list size or
webinar date as his inputs (his post gave neither; its only number was "10-20
domains"), and the sharp sizing insight stayed in the private assessment. 28
of 31 older specs carried zero params, so even the core AI step shipped hollow.
What has won: a chart that echoed every line of the client's post including the
odd ask, and a real system shown honestly.

**Only the job post (Lorenzo, 2026-09-25).** Everything the client sees is built from the post alone. Hiring history and reviews never reach the build, beats or proposal: no company, industry, tool or first name the post does not state (the Lendersa build named the client's company from a past job title). History informs the private assessment only.

**Best version first (Lorenzo, 2026-09-28).** Before any spec, decide the highest-quality version of what the client asked for that fits this pipeline, and build that. Every pain point the post names is handled visibly and properly. Minimal means no fluff, not less quality.

**Prototype week (Lorenzo, 2026-09-28).** This week every job's prop is a clickable prototype of the client's finished system, `prototype.html` in the job folder (n8n, Make and GHL alike), written by the spec subagent under "Prototype week" in `jobs/_AGENT_BRIEF.md`. The main session opens it for Lorenzo (`open <job>/prototype.html`), publishes it as a private Artifact (one per job, icon "chart" or similar) and puts the link in the proposal. Proposal framing: "I built a working prototype of your <system in their words>", "Click through it yourself: <link>", and when the backend exists, "the workflows behind it are already built, I'd import them on day one". Never "mock" or "walkthrough". The bar: gorgeous and elegant, like a $15,000 custom build (design standard `jobs/_PROTOTYPE_DESIGN.md`; each prototype also gets a design review scoring "$15k custom build" 1-10, 8+ to pass, before it reaches Lorenzo); when the post asks for a system, the page is that finished system running live on sample data ("this is exactly what it'll look like when it's done"), every requirement its own working screen. Push the 15 minute call (reply here, I'll send three times). Finalize with `--variant prototype`.

## What we make, per job

1. **The dossier** (`dossier.md`): who the client is, their tools, every number,
   their requirements verbatim in their order, the odd ask, their likely data.
   Written first; everything else is built from it. Template:
   `jobs/_DOSSIER_TEMPLATE.md`.
2. **The prop** the Loom shows, picked by the post:
   - **n8n canvas** (default): importable JSON on the clipboard, pasted with
     Cmd+V. Carries a yellow "Built for <company>" overview sticky, a "0 -
     Config: Your Settings" node, and real params where the step is the point
     of the build (see "Where specificity lives"). Aim for 10 to 15 nodes, no
     fluff (Lorenzo, 2026-09-24): the last batch's 23-node build was too hard
     to demo. A target, not a cap: every requirement in the post gets its
     steps even past 15; only extras the post did not ask for go in the
     overview as "room to add next". Make scenarios follow the same target.
   - **Make blueprint**: when the client names Make. Imported via "Import
     Blueprint". One trigger per scenario, so a build with several webhooks is
     one chain on the canvas and the proposal says "in Make it runs as N
     scenarios, one per webhook". Connections and webhooks stay unset. Branch
     conditions carry over only when the spec sets `condition`; AI sub-nodes
     and unlisted keys do not carry over (known limits in
     `jobs/_AGENT_BRIEF.md`).
     Make params use Make syntax (`{{1.field}}`, plain-text prompts), never
     n8n expressions; see "Authoring a WorkflowSpec".
   - **GoHighLevel workflow**: only when the post is just one automation (one
     trigger and what follows it). Every other GHL post, account setups
     included, gets the chart (Lorenzo, 2026-09-24: he won't walk through a
     whole account setup, and nothing else goes into his account). The spec
     compiles to import JSON, one file per trigger event, loaded into empty workflows in his own sub-account with the
     "GHL Workflow Backup & Audit" Chrome extension. Prerequisites (tags, fields,
     custom values, pipeline) are created by API first. The Build-Using-AI
     prompt lane is the fallback only. Full lane: `jobs/_GHL_BUILDER_BRIEF.md`.
   - **Native Excalidraw flowchart**: audits, roadmaps, setup/infrastructure
     jobs, fine-tuning or research methods, and Zapier posts (Zapier has no
     import lane; Zapier posts keep the chart). Chart-only specs set
     `"platform": "diagram"` and use `data.transform` / `flow.branch` /
     `data.aggregate` only. Loaded with `flow`. Chart steps are full plain
     sentences he can read aloud (no fragments, colon lists or Title Case;
     2026-09-25), one straight line, zero or one gate (Lorenzo, 2026-09-24;
     rules in `jobs/_AGENT_BRIEF.md` step 4).
   Every build also gets the chart, so an n8n job can show both.
3. **Private assessment**: time, likelihood, standard pricing, pricing path,
   ask-before-quoting. Never in the proposal.
4. **Loom beat sheet**: 8 bullets max, 12 words each, glanced at, never read.
5. **The proposal**: written by the main session only, never by a subagent.

The Loom is always required. It is the standing differentiator. What changes per
post is what is on screen and how long it runs.

## Job folders and loading by name

Every job lives in `upwork-pipeline/jobs/<slug>/`: `jd.txt`, `dossier.md`,
`spec.json`, the compiled `.n8n.json` / `.make.json` / `.ghl.json`,
`.excalidraw`, `.mmd.md`, `assessment.md`, `beats.md`, `proposal.md`, and
`client_raw.json` / `client.json` when client intel ran.
`jd.txt` shape is fixed: `url: <upwork link>` line, title line, a metadata
paragraph (rate, client location, hiring history, bids, connects, flags), one
blank line, then the post verbatim. The blank line before the post is required.
Whenever the job post itself gives the client's first name (its signature), or
Lorenzo supplies it, the metadata paragraph carries it
on its own line, `client first name: <Name>`, before the blank line. The
dossier reads it; the greeting and beat 1 use it; without it they fall back as
usual. Client intel (batch step 2, paused) adds the same line when
freelancers' reviews name the client clearly, plus `client grade: <A|B|C|D> -
<reasons>`, and writes `client.json` beside jd.txt. It never replaces a name
line the main session wrote.

```bash
<pipeline root>/job list              # numbered, newest post first (jobs/_ORDER.txt)
<pipeline root>/job <partial>         # n8n (falls back to make) on clipboard + url + notes
<pipeline root>/job <partial> flow    # excalidraw scene
<pipeline root>/job <partial> ghl     # every .ghl.json copied to ~/Desktop/GHL-Imports/
```

`./job` warms the n8n instance (Render free tier sleeps 30 to 50 s) when it
loads. Nothing goes on the clipboard until he asks for a job by name. When he
loads a job, print the Upwork link first (he closes tabs), then what is on the
canvas, the assessment, the beats, and ask for the Loom link, runtime, start and
demo dates. After a batch he deletes the folders he did not apply to; vault
archetypes stay.

## Batch mode (his saved jobs)

1. Pull saved jobs with the Upwork connector (`list_accounts` for the org id,
   then `find_saved_jobs`). Skip anything already hired or older than the batch.
   Never skip a job Lorenzo saved for its terms (Lorenzo, 2026-09-23): a
   full-time or human-role post (receptionist, VA) is built like any other;
   a retainer is his to raise on the call, never in the proposal (rule 11). Write `jd.txt` per job, with the `client
   first name:` line when the name is known. When it creates the job folders,
   the main session also writes `jobs/_ORDER.txt`: one slug per line, newest
   post first by Upwork job id. Nothing else writes that file.
2. **PAUSED (Lorenzo, 2026-09-22): skip this step until he turns it back
   on.** No Chrome step, no grades, nothing dropped; go straight from step 1
   to step 3, and leave the grade and dropped columns out of the step 7
   table. The greeting name comes only from a `client first name:` line
   the main session writes in step 1. The rest of this step is kept for
   when it returns.
   Client intel, per job, after jd.txt and before any subagent, in Lorenzo's
   Chrome with Claude in Chrome (the built-in browser is blocked by
   Cloudflare). A Cloudflare "Just a moment..." page clears on
   its own in about 5 seconds; wait for the job page before running anything.
   An interactive challenge (a checkbox or puzzle): stop and ask Lorenzo, never
   click it.
   - Install, once per version of `client_intel/snippet.js`, on any upwork.com
     page: `python3 <pipeline root>/client_intel.py --install-js` prints two
     small scripts and the file path. Run the first with the javascript tool
     (it adds a file input labelled "advero client intel loader"), find that
     input's ref and `file_upload` the printed path into it, then run the
     second (it checks the file's sha256, stores it in the page's localStorage
     and removes the input; expect `{ok: true, v: ...}`).
   - Run, per job page once it has loaded: the one line from
     `python3 <pipeline root>/client_intel.py --loader` (the version is baked
     in; copy it, never compose it). It waits for "About the client", expands
     the review history and returns a compact object.
     `{error: "not_installed"}` or `{error: "stale_install"}`: install again,
     then rerun the loader.
   - Write the returned object to `<job>/client_raw.json` with a heredoc, then:
   ```bash
   python3 <pipeline root>/client_intel.py <job dir> <job dir>/client_raw.json
   ```
   It writes `client.json`, adds `client first name:` (only when freelancers
   name the client clearly) and `client grade:` to the metadata paragraph, and
   prints one summary line (`B  Casey  hires often (64%); ...`). Grades: A
   strong, B normal, C and D dropped (rules in the script's docstring). If
   the page fails (any other `error` object, or the script refuses), carry on
   without it. C and D jobs are dropped before any subagent is spawned; the
   batch does not wait on Lorenzo. Their grades still go to him in the step 7
   table (name, grade, reasons, dropped yes/no) so he can reinstate one by
   name. Review facts are private: never stated to the client or in the
   proposal.
3. Spawn one subagent per job with `model: "opus"`, pointed at
   `jobs/_AGENT_BRIEF.md`. Subagents write **dossier.md, spec.json,
   assessment.md, beats.md only**. No proposal, no compile, no clipboard, no git.
   They use `upwork_gen nearest` as a style reference for how deep the core
   AI step and the named tool's HTTP call go (first result on their platform;
   chart jobs skip it) and validate with
   `WorkflowSpec.load(...).validate()`; GHL jobs also run the read-only
   `compile_ghl_many` self-check in the GHL brief. Rebuilding a folder that
   already has spec.json / beats.md / assessment.md / dossier.md: the old files
   are replaced, not improved; the dossier is written from `jd.txt` first
   without opening them. The one exception is the revise round (step 6): a
   subagent whose prompt carries the reviewer's fixes opens this run's files
   and applies only those fixes.
4. The main session drafts every proposal while they run (the dossier gives the
   greeting name and the tldr's words).
5. Compile, copy and verify in one command:
   ```bash
   cd <tool root> && python3 -m upwork_gen batch <job dir> [<job dir> ...]
   ```
   It compiles each spec (with `--jd`, promoting to the vault), copies the
   outputs into the job folder, runs `verify_job`, and prints the table. It
   does not write `_ORDER.txt` (step 1 did). GHL jobs: run
   `python3 -m upwork_gen.ghl_prereqs <spec>` (dry run), then `--apply`, before
   the batch. The first `--apply` on a new account or token waits until
   Lorenzo has seen the dry-run output; after that, per-job `--apply` is
   approved (see the GHL brief).
6. Quality gate: spawn one reviewer subagent per job with
   `jobs/_REVIEWER_BRIEF.md`. It reads as the client and scores "made only for
   me" and "worth $2,000"; PASS needs 8 or more on both. It scores what the
   client sees (see "Where specificity lives"), not node internals. On REVISE, a spec
   subagent gets the fix list in its prompt, opens this run's files and applies
   only those fixes (the exception to the rebuild rule); fixes aimed at
   `proposal.md` are the main session's. A GHL revise that adds a tag, field,
   custom value or pipeline reruns ghl_prereqs (dry run, then --apply) before
   re-batching. Then the job is re-batched. A second
   REVISE goes to Lorenzo, flagged, with both reviews. A `verify_job`
   similarity WARN counts as a fail only when it matches another job's
   archetype; a match against this job's own earlier build (kept in its
   `.stale/`) is exempt, since a rebuild reuses the client's own words.
7. Post one table: name, link, client grade with reasons, dropped yes/no,
   what's on screen, reviewer scores, preview count, one-line note. Dropped C
   and D jobs get a row too, so Lorenzo can reinstate one by name. (Grade and
   dropped columns only when client intel ran; it is paused, see step 2.)

## Verification pass (every build, no exceptions)

```bash
cd <tool root> && python3 -m upwork_gen.verify_job <job dir> [<job dir> ...]
```
FAIL lines block the handover; WARN lines are the genericness lint and are
fixed or explained. It checks:
- spec validates (only "N trigger nodes side by side" or "no trigger node"
  allowed as warnings); zero dangling connections; no non-ASCII characters in
  compiled files and the chart; pinned samples on the first and last node;
  workflow name equals the spec title;
- proposal: preview 133 to 150 characters through `https://www.loom`, link
  written as `https://www.loom.com/share/[LOOMURL]` until finalize fills it,
  "the video walks through" exactly once, a P.S. with exactly four `-> ` bullets;
- beats: 8 max, 12 words max each;
- n8n and Make: aim for 10 to 15 nodes on the canvas, stickies excluded (WARN
  above: fine when every extra node carries something the post asked for);
- genericness lint: `example.com` URLs, leftover `reason_for_calling`, AI
  prompts that are just the node name, the default `{summary, score}` parser
  schema, gates comparing against their own step number, Slack with no channel,
  Sheets with no document, duplicate webhook paths, the client missing from the
  title, a "Built for" sticky and beat 1, beat 1 without the client's first
  name, and a chart whose steps match another job's archetype 50% or more (a
  match against the same job's own earlier build, in its `.stale/`, is
  exempt).

Field-level WARNs (Slack with no channel, Sheets with no document, the default
parser schema) are informational: fix them when the node is the point of the
build, otherwise leave them. They are never a reason to send a build back.

Still checked by eye: sentence case, the last beat being a direct call ask
(timing stays in the proposal), no "placeholder" or "any CRM" wording, the GHL canvas
screenshot (`ghl-canvas.png`) matching the spec with no orange dots except
client-set connections, and the reviewer's verdict.
Things this pass has caught before: error triggers importing as Calendly, Ollama
importing as OpenAI, middle dots rendering as "A with a hat", a broken link
placeholder, "the video" twice, beats promising a demo the proposal did not.

## After he records

```bash
cd <tool root> && python3 -m upwork_gen.finalize <job dir> --loom <url> --runtime <min> --start "<text>" [--draft "<text>"] [--name <First>] [--variant <label>]
```
Fills `[LOOMURL]`, `[N]`, `[START]` and `[DRAFT]` in `proposal.md` (`--name`
turns "Hey [greeting]" or "Hey there" into "Hey <Name>"; finalize refuses while
`[greeting]` is left in, so pass `--name` whenever the draft has it), recounts the preview, puts the proposal
on the clipboard, and appends the row to `proposals.csv`. Every other slot
(`[X]`, `[rush seed]`, `[their kind of system]` and the like) is the main
session's to fill when it drafts the proposal.

Outcome sync (weekly, so the market scores every change). The script cannot
call Upwork itself:
1. The main session calls the Upwork connector read-only, exactly as
   `upwork-pipeline/OUTCOMES.md` lists (`list_freelancer_proposals` per status,
   `get_room` per still-Accepted proposal and per Declined / Archived /
   Withdrawn proposal that matches a log row, `list_contracts`), and saves each result
   as JSON in the scratchpad.
2. It merges them and fills viewed / replied / interviewed / hired (it lives in
   the pipeline root, not the tool root; `--dry-run` first, then without):
   ```bash
   python3 /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/sync_outcomes.py --proposals <json> [--rooms <json>] [--contracts <json>] --dry-run
   ```
   `--report` prints the rates by platform and opener_variant.

## Authoring a WorkflowSpec

Subagent rules in full: `jobs/_AGENT_BRIEF.md`. The shape:

```json
{
  "title": "Raman Family Dental: Every Enquiry Answered in 60 Seconds",
  "platform": "n8n",
  "client":   {"name": "Priya", "company": "Raman Family Dental", "industry": "dental clinic", "location": "Oakville, Ontario"},
  "overview": {"how_it_works": ["..."], "setup": ["..."], "need_from_you": ["..."]},
  "config":   {"front_desk_channel": "PASTE-YOUR-SLACK-CHANNEL"},
  "sections": [ { "key": "intake", "label": "1 - CATCH EVERY WEBSITE ENQUIRY", "color": 0, "note": "One or two plain sentences, read aloud, in their words." } ],
  "nodes": [
    { "key": "hook", "kind": "trigger.webhook", "label": "1 - New Enquiry From Your Website Form", "section": "intake", "params": {"path": "raman-enquiries"} },
    { "key": "sort", "kind": "ai.llm", "label": "2 - Sort It: New Patient, Emergency or Billing", "section": "intake",
      "notes": "Emergencies skip the queue and reach the front desk in seconds.",
      "params": {"system_message": "You triage enquiries for Raman Family Dental ...", "prompt": "=Enquiry: {{ $json.body.message }} ..."} },
    { "key": "model", "kind": "ai.model", "app": "anthropic", "label": "Claude - Sorts the Enquiry", "parent": "sort", "port": "ai_languageModel" },
    { "key": "urgent", "kind": "flow.branch", "label": "3 - Emergency?", "section": "intake",
      "params": {"condition": {"left": "={{ $json.category }}", "op": "eq", "right": "emergency"}} }
  ],
  "edges": [ { "from": "hook", "to": "sort" }, { "from": "sort", "to": "urgent" } ],
  "input_sample":  { "a real-looking record of THEIR business": "..." },
  "output_sample": { "visible work done, on the last node": "..." }
}
```

Kinds (closed set): `trigger.webhook schedule email form chat app` /
`data.transform code merge split aggregate filter` / `flow.branch switch wait noop` /
`ai.agent llm model memory tool embed vectorstore parser` / `app.action net.http net.respond`.

n8n catalog `app:op` pairs: openai:message, googleSheets:append|read|update,
gmail:send|reply|draft, slack:post|update, airtable:create|search|update,
hubspot:create_contact|create_deal, notion:create|update, telegram:send,
whatsapp:send, discord:send, twilio:send, postgres:insert|select, stripe:get,
shopify:get, googleDrive:upload, googleDocs:create, googleCalendar:create,
wordpress:create, salesforce:create_contact, pipedrive:create_contact,
clickup:create, monday:create, outlook:send, quickbooks:create, xero:create,
supabase:insert. Error handler (n8n and Make specs only, never GoHighLevel or
chart specs): `trigger.app` app `n8n` op `error_trigger`.
Models: `anthropic`, `openai`, `ollama`. Anything else (GoHighLevel, Instantly,
Hunter, Zoho, Workiz, Quo, a client's API) is `net.http` with `params.service`
from `catalog/http_services.json` and a label naming the service.

Params shorthand (n8n; the compiler translates): `condition` {left, op, right} on
flow.branch / data.filter (op: gte gt lte lt eq neq contains exists true
false); `prompt` + `system_message` on ai.llm / ai.agent; `schema` on ai.parser;
`channel` + `text` on slack; `document` + `sheet` + `columns` on googleSheets /
airtable; `service` + `method` + `url` + `headers` + `body` on net.http; `path`
on trigger.webhook. Raw n8n parameter names pass through for everything else.

GoHighLevel gates: `params.condition` in plain English plus the tags spelled
out, `params.tag` (one tag or a list) and `params.negate: true` for "does not
have", so the compiler never reads the sentence to find tags or direction. One
gate tests one thing (see the GHL brief).

Leading `=` (n8n): the compiler adds it to `prompt`, `condition.left`, `url`,
`headers` values and slack `text` when they hold `{{ }}`, so either form works
there. Values inside a `body` object never start with `=`: the compiler wraps
the whole body as `"=" + JSON`, so an inner `=` ships literally. Raw n8n
parameters are used as written and need their own `=`. `system_message` is
plain text.

Make specs use the same keys in Make syntax: `{{1.field}}` mappings (module 1
is the trigger; paths follow `input_sample`), plain-text prompts, texts and body
values. Never an n8n expression (a leading `=`, `$json`, `$(`) in a Make spec:
the Make compiler leaves it blank and flags it unresolved. Make uses
`condition` on `flow.branch` / `flow.switch` (and on edges) in Make syntax
(`{{5.statusCode}}`). It does not use `path` or `service` and draws no AI
sub-nodes and no Config node, so write full URLs and auth headers into the step. Full list in `_AGENT_BRIEF.md`
("Make params").

Rules:
- **Built from the dossier.** Title names their company or their exact outcome
  in their words (70 chars max; it becomes the canvas name and file slug). One
  section per requirement, in their order; past 5 requirements, adjacent ones
  are grouped and the section note names the grouping; fewer than 4 sections is
  fine. Samples are a real-looking record of their business, never another
  client's. A dossier `unknown` is never copied into spec.json (omit the key).
- **Numbers rule.** A number about the client's business (list size, dates,
  volumes, counts, spend) goes on the build, in a beat, in the assessment's
  sizing or in a reviewer fix only when it is in the post or worked out from
  the post's numbers in the dossier's Sizing. Any other such number appears
  only as a labelled input the client supplies ("Your List Size"), never as a
  stated fact. The sample record is the one exception: it is illustrative.
- **Where specificity lives: in what the client sees.** Node titles, section
  labels, the overview sticky, the samples, the chart and the beats, with every
  requirement in the post visibly answered in their words and their order.
  Params are required only where the step is the point of the build: the core
  AI step's `prompt` and `system_message`, written for this client, and the
  HTTP call to a tool the client named (real endpoint, real fields). Other
  nodes may use compiler defaults. `notes` (one line) on the 3 to 5 nodes the
  Loom points at. Never "placeholder" or "any CRM swaps in"; when the post
  names no tool, pick the most likely one from the dossier and commit.
- Section labels `1 - UPPERCASE STAGE`, node labels `3 - Sentence Case Verb
  Phrase`, hyphens only (no middle dots, no em dashes, no arrows).
- AI sub-nodes use `parent` + `port` (`ai_languageModel`, `ai_memory`,
  `ai_tool`, `ai_outputParser`), no section, no edges. `ai.embed` and
  `ai.vectorstore` are sub-nodes only; use `net.http` for embed/upsert steps.
  Every sub-node label is unique and names its job ("Claude - Scores the
  Lead", "Claude - Drafts the Reply"): two sub-nodes both labelled "Claude"
  show on camera as "Claude" and "Claude 2", which reads like an old model.
- `branch` on `flow.branch` edges (`true`/`false`) and `flow.switch` edges
  (named arms). Back-edges carry `"loop": true`. A false arm shared by two gates
  goes in the last section it touches, or the layout overlaps.
- n8n and Make: 10 to 18 flow nodes; more only when the post is
  architecture-heavy. Always an error path unless the job is trivially small.
  GoHighLevel specs are exempt (no n8n error trigger; it fails the GHL
  compiler) and follow `jobs/_GHL_BUILDER_BRIEF.md`.
- **Charts**: `"platform": "diagram"`, 8 to 13 steps, bands per the section
  rule above, one or two gates, no side-path sections, no error trigger, no
  params, no `nearest`. Never adapt a prior client's chart. Setup,
  infrastructure and method jobs put the client's own numbers on the chart, and
  only those (webinar list: list size x weeks to the webinar, then domains,
  mailboxes, pre-warmed or not; a number the post does not give is a labelled
  input, as Mark's list size should have been), and the sharpest sizing
  insight from the assessment goes on the chart and into a beat.

## Compile (single job, for debugging)

`batch` is the normal path. By hand:
```bash
cd <tool root> && python3 -m upwork_gen spec <job>/spec.json --jd <job>/jd.txt --excalidraw --no-open --no-copy
```
Always `--jd` (promotes into the vault, mines keywords). `--force` when
re-running a promoted job. `--no-promote --no-log --no-commit` for renderer test
compiles. Outputs land in `out/`. Everything written is ASCII-only.

The chart renderer (`compile_excalidraw_native.py`) draws one tinted band per
stage with title and note, shapes coloured by kind, branch labels on arrows,
dashed loop-backs, scene title on top. Preview renderer changes with the
scratchpad `preview.html` over `python3 -m http.server 8765`.

## Delivery assessment (private)

- **Time**: realistic hours and calendar weeks, not the happy path.
- **Likelihood**: what breaks, weighted to the client's accounts, plan tiers,
  API access, and real data. Say plainly what is unverified for Lorenzo and how
  it will be framed honestly.
- **Standard pricing**: the defensible market range plus recurring software.
  He bids below it on purpose; he wants the reference number.
- **Pricing path** (2026-09-28): for Lorenzo only, never in the proposal or
  the chats (rule 11's billing ban stands). It holds:
  - Value: hours saved or revenue added per year, with the assumption stated
    (for example hours a week x 52 x hourly cost, or extra deals a year x
    deal value). A number the post does not give is labelled as his
    assumption.
  - Price range: 10 to 20% of that yearly value.
  - Land offer: a small first piece that ships something working, which is
    milestone 1.
  - Upsell path: what he offers once the land offer is live.
  - Milestones: 3 to 4, each with its % of the price (totalling 100%), each
    worded "paid once [deliverables] are delivered and you've signed off".
- **Ask before quoting**: the questions that move the estimate.
- Flags: US-only posts (he confirms eligibility, copy asserts no location),
  posts that demand a portfolio link he may not have, posts that forbid contact
  outside Upwork.
- Anything sharp here the client would value (sizing, a risk to their list or
  data) also goes on the build and into a beat.

## Beat sheet

8 bullets max, 12 words each, spoken language. Beat 1: "<FirstName>, this is
<their outcome> for <company or their business>" in their words, FirstName from
the dossier (the `client first name:` line in jd.txt, else the post's
signature); "this is <their outcome> for your <business type>" when the name is
unknown. At least two beats point at on-screen items only this client would
recognize (their numbers, their tool, their odd ask), under the numbers rule.
Middle beats walk the canvas by section using the real labels. One beat names a
risk or decision. One middle beat (not the first, not the last) carries the
P.S. case-study bullet that matches the job, said while the matching part of
the build is on screen, using only that bullet's fixed facts: no new numbers,
no invented detail. Last beat is a direct call ask, 12 words max ("Reply here,
I'll send three times, can jump on today or tomorrow."). Start and draft
timing stay in the proposal body, not in the beats.

## Proposal copy (locked)

**LOCKED OPENER (Lorenzo, 2026-09-29): use this for the next 100 proposals, then compare reply rates.** He dropped "just finished a similar build last week": "it just doesn't sound very true, so people don't buy it." Every proposal now opens by claiming the TYPE of build he does all the time, then hands them their finished system:

```
Hey [greeting] 👋 I do [X] builds all the time, so here's your [their system] [finished / already running], [N]-min video: https://www.loom.com/share/[LOOMURL]
```

- [X] is the build type in the post's words (GoHighLevel CRM, lead routing, AI agent, cold email, Zoho automation). Size [X] and [their system] so the preview lands in 133-150.
- A post that asks for a keyword gets it inline first ("Deluge. Hey there 👋 I do ..."), never on its own line.
- The body opens "The video walks through what your [system] will look like once it's set up and live: [input] going in and [output] coming out: ...", with inputs and outputs first (Nick Saraev). When the page shows one item from a longer list, add "I picked one item from your list to show finished, and I can build any of the others the same way."
- Preferred ending (2026-09-30, "perfect intro"): "...so here's your [system] finished and connected, [N]-min video:". The body carries "The build is done; the video is just a more visual way to show it running end to end."
- Start line: "I can start this week." Closer, sign-off and P.S. as below.
- finalize logs it as opener_variant `do-x-all-the-time` by default. Don't pass another --variant unless he asks.
- Templates A and B and the older openers below are superseded while the 100-proposal test runs.

Sentence case is official (proposals have gone out in proper sentence case
since 2026-09-21). Template A's opener changed on 2026-09-28 (below); B's
shape is unchanged. Written-out slots: A's "[2-3 tool names from the post]"
and "[their kind of system]", and the "The video walks through" that opens
B's paragraph.

Template A, a real build exists. "[greeting]" follows rule 2. The tool names
come only from the post (n8n, GoHighLevel, Claude); when the post names no
tools, the slot is their own words for the system. The fixed text is 65
characters with a one-digit "Loom" runtime, so the greeting ("there", "Mark",
"Raman Family Dental team") plus everything between "built your " and
", [N]-min" must total 68 to 85 characters (63 to 80 after "Hey there"), so
the preview lands in 133 to 150 (verify_job counts it). Tool names plus the
system usually run short of that; add one short clause the post itself
supports, as in this 141-character preview: "Hey Trey 👋 I went ahead and
built your n8n + GoHighLevel lead follow-up system, with Claude writing the
replies, 4-min Loom: https://www.loom". Logged as opener_variant
`tools-built-yours` (finalize's default since 2026-09-28).

```
Hey [greeting] 👋 I went ahead and built your [2-3 tool names from the post] [their kind of system], [N]-min Loom: https://www.loom.com/share/[LOOMURL]

tldr: [one or two short lines on what it does, no mechanics]. The video walks through how.

I can start [START], working demo by [DRAFT] (assuming we speak soon). Estimated timeline is [X] from kickoff to tested and handed off. I can always get it done faster, I just have to move a few things around in my schedule. We just need a quick 15 minute call to [what the call decides].

Looking forward to hearing from you, just shoot me a message here on Upwork and we'll book that 15 minute call to get started.

Lorenzo

P.S. A few other things I've done:

-> [four case-study bullets, vertical match first]
```

Template B, audit / method / setup, nothing importable:

```
Hey there 👋 I run this exact [setup / audit] for [their kind of business] all the time, [N]-min walkthrough of what it'd look like for you: https://www.loom.com/share/[LOOMURL]

The video walks through [one short paragraph on the stages and the evidence-driven differentiator, money framing]

I can start [START], with a first draft of [deliverable] by [DRAFT]. Estimated timeline is [X]. [rush seed]. We just need a quick 15 minute call to [what it decides].

[same closer, Lorenzo, P.S.]
```

For a Template B proposal always pass `--variant template-b-mapped-out` to
finalize, so it is not logged as `tools-built-yours`.

The four P.S. bullets (order: the one matching the job's vertical first;
roofing for trades/bids, lender for ads/ROI, consultancy for outbound/B2B,
agency for AI systems):

```
-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.
-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
-> Scaled my own AI agency to $10,000 a month on the same kind of system.
```

Previous Template A opener (default until 2026-09-28; not used unless he
asks): "Hey there 👋 I build [their kind of
system] like this all the time, so I went ahead and built this one custom for
you, [N]-min Loom: https://www.loom.com/share/[LOOMURL]". Its fixed text was
119 characters, so the words after "Hey" plus the slot totalled 14 to 31.
In proposals.csv the rows that used it carry labels such as
`template-a-all-the-time`, `template-a-wire-setups-all-the-time-propercase`,
`template-a-build-ghl-systems-all-the-time-propercase` and
`template-a-agent-workflows-propercase`. The one `standard` row (2026-09-27,
`jobs/ai-workflow-automation-small-business-uae`) used a custom opener and was
only logged under finalize's old default label. When he uses this opener, the
main session passes `--variant template-a-all-the-time` to finalize, never
`standard`, so it does not share a bucket with that custom row.

Test opener (A/B, logged as `TEST-built-yours-...` in proposals.csv): "Hey
there 👋 I went ahead and built your system, I finished a similar build for a
company just a week ago, [N]-min Loom: https://www.loom...". Only when he asks
for it, and only because he asserts the claim himself.

Rules:
1. Preview line 133 to 150 characters through `https://www.loom`, counted in
   code. "[N]-min Loom" for a technical client, "[N]-min video" otherwise. In
   Template A the tool names, the system words and any added clause together
   move the count; size them with the rule above the template.
2. Greeting: client's first name when the dossier has one (the `client first
   name:` line in jd.txt, or the post's signature) ("Hey Mark 👋"), "Hey
   [firm] team 👋" when only a business name is known, else "Hey there 👋".
   Wave emoji only.
3. Gift framing survives every rewrite. Never "nearly identical", "for other
   companies", "multiple times", "did this exact setup last week".
4. Body is a tldr, what it does not how, "the video walks through how" once
   (Template B: its paragraph opens with "The video walks through", once).
   When the build is representative rather than their exact ask, the call is
   framed as reviewing their current process and picking where to build first.
   When they say they already have a flow the post doesn't describe, the build
   is the full end-to-end version from Lorenzo's experience, and the body says
   so: we keep what they have and plug in what it's missing (2026-09-24).
5. Timing line: start, demo date or first-draft date (never "delivered by":
   it reads as finished; Lorenzo, 2026-09-24), estimate, rush seed when the
   timeline is more than a few days, then the 15 minute call and what it
   decides. Ongoing roles: first piece
   live by [date], start small.
6. Closer fixed, then "Lorenzo", then the P.S. bullets above.
7. Sentence case: capitalize the first word of each sentence, "I", names and
   proper nouns (Upwork, Instantly, Loom, Python; n8n stays lowercase as a
   brand). "[N]-min Loom" takes a capital L (every proposal since 2026-09-21
   wrote it that way); the "tldr:" label stays lowercase.
   First person singular. No em dashes, no taglines, no "it's not X, it's Y".
8. Never invent facts about the client or Lorenzo. Say only what the video
   shows. No past-project claims he has not asserted. Adjacent framing is fine
   ("the video shows the logic in n8n, production ships in Python").
9. Screening lists are never answered point by point; the P.S. carries the
   proof. Mandatory text boxes at submit time get two or three verified
   sentences pointing back to the video.
10. A post's required first word ("trailer") goes before the greeting.
11. **Never discuss billing (Lorenzo, 2026-09-24, hard stop).** No prices,
   rates, retainers, budgets, fees or payment terms anywhere in a proposal,
   even when the post asks for a rate, a fixed price or a retainer, and even
   on full-time posts. Pricing and retainers happen on the call. The
   assessment keeps the numbers privately; `verify_job` fails a proposal
   that talks billing above the P.S.
12. **Proof facts are fixed; framing and order fit the job (Lorenzo,
   2026-09-24).** The four P.S. bullets come from `templates/ps-case-studies.md`
   with every number and what it was intact. The tail that ties a bullet to
   the job adapts: "on the same kind of system" only when the build is what his
   agency runs on (outbound, lead gen and follow-up, AI agents), otherwise the
   agency bullet ends at "$10,000 a month." Never invent a link. Order per job: the bullet
   closest to what the post is about goes first (roofing routing and
   follow-up for trades, lead routing and CRM follow-up; lender for ads, ROI and
   attribution; consultancy for outbound, cold email, B2B and personalized
   messaging; agency for AI agents, AI systems and consulting), then the next
   closest. `verify_job` fails a P.S. missing a case study's number.

Facts he has confirmed for copy: runs AdveroSolutions, 100k+ cold emails a month
on Instantly with an agent researching each message, daily n8n/Make and Claude
Code with MCP tools on live APIs, the four case studies, and (2026-09-24) Claude
and Grok agents deployed in his own agency and for numerous client companies,
plus consulting for very large companies, and experience working with dental
practices (not a GHL dental build, PMS integration or offline conversions), and
flows like these set up for other bakeries, and work with outdoor living /
construction companies like the Texas GHL consult client. Also (2026-09-25) AI agents built on a
client's existing database for numerous companies; "just finished a similar build
last week" is approved for those. Also (2026-09-26) bots built in Hermes AI and Muse,
and in every major bot platform (he recommends Hermes over Muse for now). His real cold-email
infra method: mailboxes and lookalike domains provisioned through a mailbox
provider (Zapmail, about $3 to $4 per mailbox, pre-warmed when speed matters),
everything configured in Instantly, one unibox, Instantly's API wired to Claude.

## Logging

`finalize` appends one row to `upwork-pipeline/proposals.csv` for every proposal
handed over and fills applied_at, job_title, job_url, platform, build_slug,
node_count, loom_url, opener_variant, opener_visible_chars. It leaves
job_created_utc, age_hours_at_apply, connects, boosted and notes empty (notes
is filled by hand when there is something worth recording). `sync_outcomes.py`
fills viewed / replied / interviewed / hired.

## Known tool state

- n8n and Make catalogs verified. Wait nodes strip the step prefix before
  reading duration; seconds are a unit.
- If/Filter gates strip the step prefix before reading a threshold (fixed
  2026-09-22; before that every gate compiled as `field >= step number`), and an
  ai.llm or ai.agent with an ai.parser sub-node gets `hasOutputParser: true`.
- Params shorthand (`condition`, `prompt`/`system_message`, `schema`,
  `channel`/`text`, `document`/`sheet`/`columns`, `service`/`method`/`url`/
  `headers`/`body`, `path`) is translated by the compiler; raw n8n params pass
  through. Node `notes` render under the node.
- Spec fields `client`, `overview` (rendered as the yellow "Built for
  <company>" sticky) and `config` (rendered as the "0 - Config: Your Settings"
  node) are optional in the schema and expected on every n8n/Make build.
- `catalog/http_services.json` holds real endpoints, auth headers and body
  shapes for non-native services (gohighlevel, instantly, clay, hunter, apollo,
  smartlead, calendly, calcom, openphone/quo, zoho, workiz, pandadoc, monday,
  snov, firecrawl, apify); `net.http` nodes reference it with `service`.
- GoHighLevel: JSON-import lane via the Backup & Audit extension.
  `compile_ghl.py` emits one `.ghl.json` per independent trigger
  (`<slug>--<n>-<trigger>.ghl.json`); `ghl_prereqs.py` creates tags, custom
  fields, custom values and the pipeline over REST (`GHL_PIT_TOKEN` in the tool
  repo `.env`), refreshes `catalog/ghl_ids_<location>.json`, never touches the
  "Sales" pipeline. Format reference: `reference/ghl_export_sales_request_follow_up.json`.
  Some step shapes are still being confirmed (see the GHL brief).
- Zapier: no import lane; the chart is the prop.
- `pinData` survives a clipboard paste. Nodes carry no credentials, so n8n shows
  a warning triangle on each; that is normal.
- Two pre-existing test failures in the old GHL mockup renderer; that path is
  retired.
- 2026-09 patches in `params.py`, `generate.py`, `compile_make.py` and
  `catalog/n8n_nodes.json` are committed only when he asks.
