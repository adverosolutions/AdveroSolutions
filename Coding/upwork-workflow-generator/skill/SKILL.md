---
name: upwork
description: Lorenzo's complete Upwork proposal process - build the prop (n8n JSON, Make blueprint, GoHighLevel import JSON, or a native Excalidraw flowchart), private assessment, Loom beat sheet, and the locked proposal copy, one job or a batch of saved jobs. Use when he pastes a job post, says his saved jobs are ready, asks to load a build by name, or invokes /upwork.
---

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

## What we make, per job

1. **The dossier** (`dossier.md`): who the client is, their tools, every number,
   their requirements verbatim in their order, the odd ask, their likely data.
   Written first; everything else is built from it. Template:
   `jobs/_DOSSIER_TEMPLATE.md`.
2. **The prop** the Loom shows, picked by the post:
   - **n8n canvas** (default): importable JSON on the clipboard, pasted with
     Cmd+V. Carries a yellow "Built for <company>" overview sticky, a "0 -
     Config: Your Settings" node, and real params where the step is the point
     of the build (see "Where specificity lives").
   - **Make blueprint**: when the client names Make. Imported via "Import
     Blueprint". One trigger per scenario, so a build with several webhooks is
     one chain on the canvas and the proposal says "in Make it runs as N
     scenarios, one per webhook". Connections and webhooks stay unset, and
     branch conditions, AI sub-nodes and unlisted keys do not carry over (known
     limits in `jobs/_AGENT_BRIEF.md`).
     Make params use Make syntax (`{{1.field}}`, plain-text prompts), never
     n8n expressions; see "Authoring a WorkflowSpec".
   - **GoHighLevel workflow(s)**: the spec compiles to import JSON, one file per
     trigger event, loaded into empty workflows in his own sub-account with the
     "GHL Workflow Backup & Audit" Chrome extension. Prerequisites (tags, fields,
     custom values, pipeline) are created by API first. The Build-Using-AI
     prompt lane is the fallback only. Full lane: `jobs/_GHL_BUILDER_BRIEF.md`.
   - **Native Excalidraw flowchart**: audits, roadmaps, setup/infrastructure
     jobs, fine-tuning or research methods, and Zapier posts (Zapier has no
     import lane; Zapier posts keep the chart). Chart-only specs set
     `"platform": "diagram"` and use `data.transform` / `flow.branch` /
     `data.aggregate` only. Loaded with `flow`.
   Every build also gets the chart, so an n8n job can show both.
3. **Private assessment**: time, likelihood, standard pricing, ask-before-quoting.
   Never in the proposal.
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
Whenever the main session knows the client's first name (the post signature,
the Upwork client record, earlier messages), the metadata paragraph carries it
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
   full-time or human-role post (receptionist, VA) is built like any other
   and pitched as a retainer he runs. Write `jd.txt` per job, with the `client
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

Still checked by eye: sentence case, the last beat matching the proposal's
timing (call vs demo), no "placeholder" or "any CRM" wording, the GHL canvas
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
turns "Hey there" into "Hey <Name>"), recounts the preview, puts the proposal
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
the Make compiler leaves it blank and flags it unresolved. Make does not use
`condition`, `path` or `service`, draws no AI sub-nodes and no Config node, so
write full URLs and auth headers into the step. Full list in `_AGENT_BRIEF.md`
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
risk or decision. Last beat is the CTA matching the proposal's timing.

## Proposal copy (locked)

Sentence case is official (proposals have gone out in proper sentence case
since 2026-09-21). The shapes below are unchanged otherwise; two slots are now
written out: A's "[their kind of system]" and the "The video walks through"
that opens B's paragraph, which is what every sent proposal already did.

Template A, a real build exists. Fill "[their kind of system]" with 2 to 4 of
their words ("GoHighLevel follow-up systems", "n8n order sync systems"): with
"Hey there" and a one-digit "Loom" runtime the slot must be 9 to 26 characters;
in general the words after "Hey" ("there", "Mark", "Raman Family Dental team")
plus the slot must total 14 to 31, so the preview lands in 133 to 150
(verify_job counts it).

```
Hey there 👋 I build [their kind of system] like this all the time, so I went ahead and built this one custom for you, [N]-min Loom: https://www.loom.com/share/[LOOMURL]

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

I can start [START], [deliverable] delivered by [DRAFT]. Estimated timeline is [X]. [rush seed]. We just need a quick 15 minute call to [what it decides].

[same closer, Lorenzo, P.S.]
```

The four P.S. bullets (order: the one matching the job's vertical first;
roofing for trades/bids, lender for ads/ROI, consultancy for outbound/B2B,
agency for AI systems):

```
-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.
-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
-> Scaled my own AI agency to $10,000 a month on the same kind of system.
```

Test opener (A/B, logged as `TEST-built-yours-...` in proposals.csv): "Hey
there 👋 I went ahead and built your system, I finished a similar build for a
company just a week ago, [N]-min Loom: https://www.loom...". Only when he asks
for it, and only because he asserts the claim himself.

Rules:
1. Preview line 133 to 150 characters through `https://www.loom`, counted in
   code. "[N]-min Loom" for a technical client, "[N]-min video" otherwise. In
   Template A the "[their kind of system]" slot is what moves the count; size
   it with the rule above the template.
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
5. Timing line: start, demo/delivery date, estimate, rush seed when the
   timeline is more than a few days, then the 15 minute call and what it
   decides. No dollar figures unless he gives them. Ongoing roles: first piece
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

Facts he has confirmed for copy: runs AdveroSolutions, 100k+ cold emails a month
on Instantly with an agent researching each message, daily n8n/Make and Claude
Code with MCP tools on live APIs, the four case studies. His real cold-email
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
