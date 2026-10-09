# Brief for per-job subagents (batch mode, v4 2026-09-22)

You are preparing ONE Upwork job for Lorenzo Villarreal. Your job folder is given
in your prompt. The bar: a build so specific to this client that they would pay
$2,000 for it, and could not mistake it for anyone else's. The failure we are
fixing: Mark's cold-email chart matched an older client's chart on 9 of 14 steps,
beat 1 never named him or his webinar, the chart never asked for his list size
or webinar date as his inputs (his post gave neither; its only number was
"10-20 domains"), and the one sharp sizing insight stayed in the private
assessment. He replied "that's a generic loom". Every rule below exists to
prevent that.

Tool root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator`
Jobs root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/jobs`
The shell cwd resets between calls: `cd` into the tool root in every command.

## Read first
- `jd.txt` in your folder: `url:` line, title, a metadata paragraph (rate, client
  location, hiring history, bids, connects, and a `client first name: <Name>`
  line when the main session knows the name), a blank line, then the post
  verbatim. Client intel is paused (Lorenzo, 2026-09-22), so there is usually
  no `client.json` and no `client grade:` line; write "no client intel" in the
  dossier's Client section. When it is on, the main session runs it on the job
  page before spawning you (after writing jd.txt: `client_intel/snippet.js`, installed once in
  Lorenzo's Chrome and run on the job page with the one-line loader from
  `client_intel.py --loader`, returned an object saved as `client_raw.json`,
  then `client_intel.py` read it), so the metadata paragraph may also carry a
  `client first name:` line taken from freelancers' reviews and a
  `client grade: <A|B|C|D> - <reasons>` line (C and D jobs are dropped before
  any subagent is spawned unless Lorenzo reinstated one). An interactive challenge on the
  page stops that step for Lorenzo; a page that fails is skipped, so either
  line can be missing.
- `client.json` in your folder, when present: the client's review history,
  read for the dossier's Client section (step 1). Private: never state a
  review fact to the client, on the build or in a beat.
- `jobs/_DOSSIER_TEMPLATE.md` (you fill it in).
- `/Users/lorenzovillarreal/.claude/skills/upwork/SKILL.md`: "Authoring a
  WorkflowSpec", "Delivery assessment", "Beat sheet".
- GoHighLevel posts only: `jobs/_GHL_BUILDER_BRIEF.md`.

## Hard limits
- Write ONLY `dossier.md`, `spec.json`, `assessment.md`, `beats.md` in your
  folder. No proposal.md (the main session writes proposals).
- Do NOT compile (`upwork_gen spec`, `batch`, `ghl`, `vault`, `clip`), no
  `./job`, no `./flow`, no pbcopy, no git.
- Allowed commands: `nearest` (step 2), the validator (step 5) and, on
  GoHighLevel jobs only, the read-only GHL self-check in
  `jobs/_GHL_BUILDER_BRIEF.md`. WebFetch is allowed read-only on a website the
  client names in the post, nothing else.
- Rebuilds: if your folder already holds `spec.json`, `beats.md`,
  `assessment.md` or `dossier.md` from an older run, treat them as replaced. Do
  not open them. Write the dossier from `jd.txt` FIRST, then overwrite every
  file from scratch. Never "improve" an old spec; the old files fall short of
  these rules by definition.
- Revise round (the one exception to the rebuild rule): when your prompt
  carries the reviewer's fix list for this run, open this run's `dossier.md`,
  `spec.json`, `assessment.md` and `beats.md`, apply only those fixes, change
  nothing else, and validate again (step 5). A fix aimed at `proposal.md` is
  the main session's, not yours.

## Step 1. Dossier (before any spec)
Write `dossier.md` from `jd.txt` only (on a rebuild, without reading any old
file in the folder; in a revise round, skip to the fixes) following
`_DOSSIER_TEMPLATE.md`: first name (from the `client first name:` line in the
metadata paragraph, else as signed in the post, else unknown), company (if
shown or plainly inferable; never guess one), industry, location, the tools
they named, EVERY number in the post, their requirements
quoted verbatim in their order, the odd ask only they would recognize, what
their hiring history implies, their likely data (one real-looking record of
their business), sizing from their own numbers for setup jobs, and three "they
would recognize this" details with where each goes on screen. If the post names
a website or company site, WebFetch it for industry, services and terminology.
When `client.json` exists, fill the template's Client section from it (first
name, grade and reasons, what freelancers praise, how the client writes).

## Step 2. Retrieval (style reference only)
```bash
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator && python3 -m upwork_gen nearest /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/jobs/<slug>/jd.txt
```
`nearest` ranks by text and ignores platform: open the first result whose
`"platform"` matches your job (n8n, make or gohighlevel) and study how deep its
core AI step and its HTTP calls go (real prompts, real fields, real endpoints).
Never copy its samples, notes, titles, section labels, steps or client details.
Older specs may contain
things now banned ("any CRM swaps in", generic samples, a hollow core AI step
with no real prompt); do not
carry those over. Chart-only jobs skip this step entirely: chart steps carry no
params, and a prior chart is exactly what they must not resemble. The bar for
params depth is the inline example in step 3, not any file.

## Step 3. spec.json, built from the dossier
Pick the prop: n8n (default), `"platform": "make"` when they name Make,
`"platform": "gohighlevel"` only for a GHL post that asks for one specific
automation (see the GHL brief; every other GHL post, account setups included,
gets a chart), a chart-only spec
with `"platform": "diagram"` (step 4) for audits, setup/infrastructure, methods,
and Zapier posts.

**Title** names their company or their exact outcome in their words, 70 chars
max: "Your Webinar Invite Setup: 10-20 Warm Domains and Your Own Login" (every
fact in it is from Mark's post), "Raman Family Dental: Every Enquiry Answered in
60 Seconds" (a made-up client). Never a node list or a category. The title
becomes the canvas name and the file slug.

**Numbers rule**: a number about the client's business (list size, dates,
volumes, headcount, spend, counts) goes on the build, in a beat or in the
assessment's sizing only when it is in the post (the dossier's "Every number in
the post") or worked out from those numbers in the dossier's Sizing. Any other
such number appears only as a labelled input the client supplies ("Your List
Size", "your webinar date", a `PASTE-YOUR-...` config value), never as a stated
fact. The sample record is the one exception: it is illustrative.

**Sections** = their requirements, one section per requirement, in their order
("five parts in your post, five sections on the canvas"). Past 5 requirements,
group adjacent ones into one section and name the grouping in that section's
note ("Your parts 5 and 6: ..."). Fewer than 4 sections is fine when the post
asks for fewer things; never pad. Add an error/alert section only after theirs
(n8n and Make only). Section notes are one or two plain sentences, read aloud,
using their terms and numbers.

**Labels**: sections `1 - UPPERCASE STAGE`, nodes `3 - Sentence Case Verb
Phrase`. Hyphens only: no middle dots, no em dashes, no arrows. Branch arms
`3b - ...`. Every label reads on its own; he narrates off the canvas.

**Client fields** (optional in the schema, expected on every n8n/Make build):
```json
"client":   {"name": "Mark", "industry": "webinar host", "location": "Colombia"},
"overview": {"how_it_works": ["...", "..."], "setup": ["...", "..."], "need_from_you": ["...", "..."]},
"config":   {"list_size": "PASTE-YOUR-LIST-SIZE", "slack_channel": "PASTE-YOUR-CHANNEL"}
```
`overview` renders as the yellow "Built for <company>" sticky on the n8n canvas:
3 to 5 short lines per list, their words, their numbers. `config` renders as a
"0 - Config: Your Settings" node holding every value they must set; values use
`PASTE-YOUR-...`, never "placeholder". Omit `company` rather than guess it
(the example above has none because Mark's post names none). A dossier field
that says `unknown` is never copied into spec.json: omit that key instead.
`config` and the overview sticky render on the n8n canvas only; Make shows
neither, so a Make spec puts each value the client must set straight into the
step that uses it, as `PASTE-YOUR-...` (see "Make params" below).

**Where specificity lives: in what the client sees.** Node titles, section
labels, the overview sticky, the samples, the chart and the beats, with every
requirement in the post visibly answered in their words and their order. That
is what the quality judge scores, not node internals.

**Params are required only where the step is the point of the build**: the core
AI step's `prompt` and `system_message` (written for this client, as below) and
the HTTP call to a tool the client named (real endpoint, real fields). Other
nodes may use compiler defaults; add params there only when it is quick and
real. Field-level lint WARNs from `verify_job` (Slack with no channel, Sheets
with no document, the default parser schema) are informational and never a
reason to send a build back. When you do write params, the n8n shorthand keys
are (the compiler translates them; Make specs use "Make params" below instead):
- `flow.branch`, `data.filter`: `"condition": {"left": "={{ $json.score }}", "op": "gte", "right": 70}`;
  op is one of gte gt lte lt eq neq contains exists true false.
- `ai.llm`, `ai.agent`: `prompt` and `system_message`, real prompts written for
  this client: several sentences, their terminology, their fields, what to do
  when data is missing.
- `ai.model` app `openai`: set no `temperature` (the compiled model is
  gpt-5-mini, and GPT-5 models reject any temperature but the default with a
  400). Strictness goes in the system message.
- `ai.parser`: `schema`, an example JSON object with their fields and a
  realistic value for each.
- `app.action` slack: `channel`, `text` (with real `{{ $json.x }}` fields).
- `app.action` googleSheets / airtable: `document`, `sheet`, `columns`.
- `net.http`: `service` (a key in `upwork_gen/catalog/http_services.json`, e.g.
  gohighlevel, instantly, clay, hunter, apollo, smartlead, calendly, calcom,
  openphone/quo, zoho, workiz, pandadoc, monday, snov, firecrawl, apify),
  `method`, `url`, `headers`, `body` (values inside `body` never start with
  `=`; see "Where a leading `=` goes"). Label names the service: "Instantly:
  Add the Lead to the Webinar Campaign".
- `trigger.webhook`: `path`, unique and named for them (`webinar-signups`).
- Anything else: raw n8n parameter names pass through (data.code `jsCode`,
  data.transform `assignments`, gmail `sendTo`/`subject`/`message`, postgres
  `query`).

What params look like, for four node kinds. The AI step and the GoHighLevel
call are the required depth; the webhook path and the gate are optional. The
client is the made-up Raman Family Dental from SKILL.md; copy the depth, never
the names or the content:
```json
{"key": "hook", "kind": "trigger.webhook", "label": "1 - New Enquiry From Your Website Form",
 "params": {"path": "raman-enquiries"}},
{"key": "sort", "kind": "ai.agent", "label": "2 - Sort It: New Patient, Emergency or Billing",
 "params": {"system_message": "You triage website enquiries for Raman Family Dental, a two-dentist clinic in Oakville. Categories: new_patient, emergency (pain, swelling, broken tooth, bleeding), billing, other. Emergencies win any tie. If the message is empty or unreadable, return other and say why in reason.",
            "prompt": "=Name: {{ $json.body.name }}\nPhone: {{ $json.body.phone }}\nMessage: {{ $json.body.message }}\nReturn category, reason (one sentence) and a 2-sentence reply the front desk can send as is."}},
{"key": "urgent", "kind": "flow.branch", "label": "3 - Emergency?",
 "params": {"condition": {"left": "={{ $json.category }}", "op": "eq", "right": "emergency"}}},
{"key": "crm", "kind": "net.http", "label": "4 - GoHighLevel: Save the Patient Enquiry",
 "params": {"service": "gohighlevel", "method": "POST", "url": "https://services.leadconnectorhq.com/contacts/upsert",
            "body": {"locationId": "{{ $('0 - Config: Your Settings').item.json.ghl_location_id }}", "firstName": "{{ $json.first_name }}", "phone": "{{ $json.phone }}", "source": "Website enquiry - {{ $json.category }}"}}}
```

**Where a leading `=` goes (n8n, from `upwork_gen/params.py`).** n8n reads a
value as an expression only when the whole value starts with `=`.
- `prompt`, `condition.left`, `url`, `headers` values and slack `text`: the
  compiler adds the `=` when the value holds `{{ }}` (`prompt` always gets one),
  so `"={{ $json.x }}"` and `"{{ $json.x }}"` both work.
- `body` (an object): NO `=` on any value inside it. The compiler turns the
  whole object into one expression, `"=" + JSON`, so the inner values are
  plain `{{ ... }}`. An inner `=` stays literal and the API receives `"=<id>"`.
- `system_message`: used exactly as written. Keep it plain text.
- Raw n8n parameters (gmail `sendTo`, postgres `query`, ...): used exactly as
  written, so they need their own leading `=` when they hold `{{ }}`
  (`"sendTo": "={{ $json.email }}"`), as in n8n itself.

**Make params (`"platform": "make"`).** Mostly the same shorthand keys as n8n
(the list below), in Make's syntax. Never put an n8n expression in a Make spec: no leading `=`, no `$json`,
no `$('...')`, no `{{ $... }}`. The Make compiler leaves any such value blank and
flags it as unresolved; it never ships. Map data as `{{1.field}}`: module 1 is
always the trigger, and the path follows your `input_sample` (`{{1.name}}`,
`{{1.contact.email}}`; a Make webhook has no `body` wrapper, so the sample is
the flat payload). Prompts, texts and body values are plain text with those
mappings. Keys the Make compiler honors:
- `ai.llm`, `ai.agent`: `system_message`, `prompt` (the user message).
- slack: `channel` (emitted exactly as written), `text`.
- googleSheets append / update and airtable create / update: `document`,
  `sheet`, `columns` (a list of names, or an object of column name to value).
  airtable search: `document`, `sheet`.
- `net.http`: `url`, `method`, `headers` (an object), `body` (an object or a
  string). `service` is ignored: write the full URL and the auth header yourself
  (`"Authorization": "Bearer PASTE-YOUR-GHL-API-KEY"`).
- gmail send: `to` (a list), `subject`, `html`, `cc`, `bcc`.
- `flow.wait`: `delay` (seconds). `data.transform`: `name`, `value`.
  `data.split`: `array`.
- `flow.branch` / `flow.switch`: `condition`, as `{"left": ..., "op": ...,
  "right": ...}` or a list of those (all must hold), in Make syntax. `left` is a
  module mapping like `{{5.statusCode}}`. The number is Make's module id, not
  the step number in the label: Sample Input and every router take an id too,
  so compile once and read the `id` beside each `metadata.designer.name` in the
  job's `.make.json` before you write `left`. `op` is one of `eq`, `neq`, `gt`,
  `gte`, `lt`, `lte`, `contains`, `exists`, `not_exists`, `true`, `false`
  (`exists`, `not_exists`, `true` and `false` take no `right`), or a raw Make
  operator id such as `text:startwith`. On a two-way branch the edge labelled
  `true` or `yes` gets the condition (when one edge is labelled `false` or `no`,
  the other edge gets it), else the first edge, and the other route gets the
  opposite. For a switch with more than 2 routes, or to set each route
  yourself, put `condition` on each edge next to `branch`:
  ```json
  {"from": "gate", "to": "contact", "branch": "New Order", "condition": {"left": "{{4.data.total}}", "op": "eq", "right": 0}},
  {"from": "gate", "to": "upddeal", "branch": "Already Synced", "condition": {"left": "{{4.data.total}}", "op": "gt", "right": 0}}
  ```
Known limits (Make shows its own generic value or nothing, so do not rely on
them): `data.filter` (it carries no condition), `path` on `trigger.webhook` (webhooks stay unset), `service`,
googleSheets read, any app not listed above, and every key not listed above. AI
sub-nodes (`ai.model`, `ai.parser`, memory, tools) are not drawn in Make at all,
so `schema` goes nowhere: ask for the fields you need in the AI step's `prompt`.
The same two nodes of the dental example in Make form:
```json
{"key": "sort", "kind": "ai.agent", "label": "2 - Sort It: New Patient, Emergency or Billing",
 "params": {"system_message": "You triage website enquiries for Raman Family Dental, a two-dentist clinic in Oakville. Categories: new_patient, emergency (pain, swelling, broken tooth, bleeding), billing, other. Emergencies win any tie. If the message is empty or unreadable, return other and say why in reason.",
            "prompt": "Name: {{1.name}}\nPhone: {{1.phone}}\nMessage: {{1.message}}\nReturn category, reason (one sentence) and a 2-sentence reply the front desk can send as is."}},
{"key": "crm", "kind": "net.http", "label": "4 - GoHighLevel: Save the Patient Enquiry",
 "params": {"method": "POST", "url": "https://services.leadconnectorhq.com/contacts/upsert",
            "headers": {"Authorization": "Bearer PASTE-YOUR-GHL-API-KEY", "Version": "2021-07-28"},
            "body": {"locationId": "PASTE-YOUR-GHL-LOCATION-ID", "firstName": "{{1.name}}", "phone": "{{1.phone}}", "source": "Website enquiry"}}}
```

**Node `notes`**: one line shown under the node, on the 3 to 5 nodes the Loom
will point at. Say why it matters to them, not what the node type is.

**Tools**: use the tools they named. When the post names none, pick the most
likely one from the dossier (their history, their industry) and commit. Never
write or say "placeholder", "example CRM", "any CRM swaps in", `example.com`.

**Samples** (`input_sample` on the first node, `output_sample` on the last) are
a real-looking record of THEIR business: their industry, their numbers, their
terminology, visible work done. Never another client's names or companies.

**Shape (n8n and Make specs only; Lorenzo, 2026-09-24)**: the minimum that
really works, so he can walk through it on camera without it taking all day.
Aim for 10 to 15 nodes, counting every node on the canvas (the Config node, AI
sub-nodes and the error path included). It is a target, not a cap: go past 15
when the post's requirements need it (`verify_job` warns above 15, and the
reviewer checks each extra node is needed). Every node is one the flow needs to run:
if deleting it leaves the flow working and nothing the post asked for missing,
it goes. No logging, formatting, normalizing or double-check steps added for
polish, no node per field, no branch that repeats another. Not so bare that it
stops making sense: each requirement in the post gets its step on the canvas,
even when that takes it past 15. Only extras the post did not ask for go in the
overview's `how_it_works` or a section note as the next add-on ("room to add
WhatsApp next"). Too simple is a miss too: a requirement the post names (like
abandoned checkout in a Shopify post) never gets pushed to "next" just to stay
under 15. An error trigger (`trigger.app` app `n8n` op
`error_trigger`) plus one alert node only when they fit under the ceiling;
otherwise the overview's setup list says to point it at their error workflow.
Sections per the rule above. Kinds, catalog `app:op` pairs, AI sub-node ports and edge rules
are in SKILL.md "Authoring a WorkflowSpec". A false arm shared by two gates goes
in the last section it touches. Never a "side paths" section.

**GoHighLevel specs are exempt from Shape**: no n8n error trigger (a
`trigger.app` with app `n8n` fails the GHL compiler: every trigger and action
needs app `ghl` and an op from the closed list), no n8n params shorthand, no
node-count range. Their rules are in `jobs/_GHL_BUILDER_BRIEF.md`. **Chart-only
specs are exempt too**: they follow step 4, not Shape.

## Step 4. Charts (setup, infrastructure, audit, method, Zapier)
- `"platform": "diagram"`. No error trigger, no params, no `nearest`.
- Never adapt a prior client's chart. Build every step from THIS post's
  requirements; a lint (`verify_job`) warns when 50% or more of the steps match
  another job's archetype, and the reviewer rejects it. A match against this
  job's own earlier build (its old archetype, whose files sit in the job's
  `.stale/`) is exempt: a rebuild is expected to reuse the client's own words.
- Charts are full sentences (Lorenzo, 2026-09-25, final word): every step label is
  one complete, plain sentence a person would say out loud, in sentence case
  ("6 - When they book, they get a confirmation right away and reminders before the
  visit"). No fragments, no colon lists, no "X: Y, Z" tidbits, no Title Case.
  Section labels and notes too: notes are full sentences, never "Your parts 6 and
  7: ...". Under about 90 characters. One straight line
  from the first step to the last, zero or one gate; read in order, the steps
  explain the whole system with no narration. A "no" case can be its own step
  ("6 - No deposit yet? Monday reminds you to follow up") instead of a branch.
  When the post is vague, fill the steps with the automations Lorenzo would
  really put in for that kind of business, not guesses about their current
  setup.
- Kinds: only `data.transform`, `flow.branch`, `data.aggregate`; no trigger, no
  `ai.*`, no `app.action`. 8 to 13 steps. Bands follow the
  Sections rule in step 3: one per requirement in their order, adjacent ones
  grouped past 5, fewer than 4 when they asked for fewer.
  Params are not needed on chart steps; the labels and band notes carry the
  specificity.
- Setup jobs put the client's own numbers on the chart, and only those (the
  numbers rule in step 3). Hypothetical example, not a real client: a post that
  says "12,000 past customers, start sending in 2 weeks, everyone reached
  within 4 weeks" gives "1 - 12,000 Past Customers: Start in 2 Weeks, Done in
  4", then "2 - 600 a Day Over 20 Weekdays: 24 Mailboxes on 8 Domains", then
  "3 - 2 Weeks Is Too Short to Warm: Pre-Warmed Mailboxes". When a number is
  not in the post, the step names it as their input ("Your List Size x Weeks
  to the Webinar" on a post like Mark's, which gave only "10-20 domains") and
  the assessment asks for it.
- The sharpest sizing insight from the assessment goes ON the chart and into a
  beat (in the hypothetical above: "8 domains covers 12,000 in 4 weeks; more is
  money wasted"), not only into the private assessment.

## Step 5. Validate
```bash
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator && python3 -c "from upwork_gen.spec import WorkflowSpec; s=WorkflowSpec.load('/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/jobs/<slug>/spec.json'); print(s.validate())"
```
There is no `load_spec`. Fix every error. Acceptable warnings: "N trigger nodes
side by side", "no trigger node" (chart-only).

GoHighLevel jobs also run the read-only GHL self-check from
`jobs/_GHL_BUILDER_BRIEF.md` ("Self-check") and fix every error it raises.

## Step 6. assessment.md (private, never in the proposal)
Time (real hours and calendar weeks), Likelihood (what breaks, weighted to their
accounts, plan tiers, API access, real data; say plainly what is unverified for
Lorenzo), Standard pricing (defensible market range plus recurring software; the
post's rate vs market stated plainly), Ask before quoting (the questions that
move the estimate), Flags (US-only, portfolio demands, no contact outside
Upwork; client metrics such as reviews, spend, hourly rate and verification
are flags, never a reason to skip). Pricing path (for Lorenzo only, never in
the proposal or chats): the value per year in hours saved or revenue, with
the assumption stated (a number the post does not give is labelled as an
assumption); a price range of 10 to 20% of that value; a small land offer,
which is milestone 1; the upsell path after it; and 3 to 4 milestones, each
with its % of the price (totalling 100%) and worded "paid once
[deliverables] are delivered and you've signed off". Anything sharp here that the client would value (sizing, a risk to
their list or data) must also be on the build and in a beat.

## Step 7. beats.md
- 8 beats max, 12 words max each, spoken language, glanced at, never read.
- Beat 1: "<FirstName>, this is <their outcome> for <company or their
  business>" in their words. FirstName is the dossier's first name (from
  `client first name:` in jd.txt, else the post's signature); when it is
  unknown: "this is <their outcome> for your <business type>".
- At least two beats point at on-screen items only this client would
  recognize: their numbers, their tool, their odd ask. Beats follow the
  numbers rule in step 3.
- Middle beats walk the canvas by section using the real labels. One beat names
  a risk or decision.
- One middle beat (not the first, not the last) carries the P.S. case-study
  bullet that matches the job (`templates/ps-case-studies.md`), said while the
  matching part of the build is on screen. Only that bullet's fixed facts: no
  new numbers, no invented detail.
- Last beat is a direct call ask, 12 words max: "Reply here, I'll send three
  times, can jump on today or tomorrow." Start and draft timing stay in the
  proposal body, never in the beats.

## Facts about Lorenzo you may use (nothing else; never invent)
- Runs AdveroSolutions, an AI lead-gen agency. His own outbound runs 100k+ cold
  emails a month on Instantly, an agent researching and writing each message,
  plus a daily metrics dashboard.
- Has deployed Claude and Grok agents in his own agency and for numerous client
  companies, and has consulted for very large companies (Lorenzo, 2026-09-24).
- Has set up flows like these for other bakeries (Lorenzo, 2026-09-24).
- Has worked with outdoor living / construction companies and has expertise in
  that industry (Lorenzo, 2026-09-24).
- Has built AI agents on a client's existing database for numerous companies
  (Lorenzo, 2026-09-25).
- Has worked with dental practices (Lorenzo, 2026-09-24; no GHL-specific dental
  configuration, dental PMS integration or offline-conversion claim).
- Builds in n8n and Make daily; uses Claude Code and the Anthropic API daily,
  with MCP tools wired into live software.
- Cold-email infra method: mailboxes and lookalike domains through a mailbox
  provider (Zapmail, about $3 to $4 per mailbox a month, pre-warmed when speed
  matters), configured in Instantly, one unibox, Instantly's API wired to Claude.
- The four case-study bullets in `upwork-pipeline/templates/ps-case-studies.md`.
- No production claims for LangChain, Hermes or Ollama. No past-project claims
  ("did this exact setup last week", "for other businesses"). No location claims.

## Only the job post (Lorenzo, 2026-09-25)
Everything the client sees (title, labels, sticky, section notes, samples, beats,
proposal) is generated from the job post alone. The client's hiring history and
freelancer reviews never appear on screen: no company name, industry, tool or
first name that the post itself does not state. History may inform the private
assessment only. When the post names no tool, commit to the most common one
(HubSpot for a CRM, Postgres for a database), not the one their history shows.
Why: the Lendersa build named the client's company from a past job title; he
couldn't pronounce it and the client never mentioned it.

## An "agent" has tools (Lorenzo, 2026-09-25)
When a build calls something an AI agent, it is an `ai.agent` node with real tool
sub-nodes (search, look up, update, send) doing visible work on the canvas. A single
Claude/LLM step that only reads text and writes text is labelled as Claude doing that
step, never as an agent. Why: the PI demand-package canvas said "agent" but was two
bare Claude LLM calls; he said it "makes the agent look like it does nothing".

## Best version first (Lorenzo, 2026-09-28)
Before writing the spec, decide what the highest-quality version of this client's ask would be that we can reasonably build in this pipeline, and build that. Every pain point the post names is handled visibly and properly on the canvas or chart, even past 15 nodes. The minimal-build rule is a floor on fluff, not a cap on quality. Only-the-job-post and full-sentence rules still apply.

## Prototype week (Lorenzo, 2026-09-28; was "visual walkthrough week")
This week every job's Loom prop is a clickable prototype of the client's finished system: one self-contained `prototype.html` in the job folder that Lorenzo clicks through on camera and the client can click through themselves from a link in the proposal. It applies to n8n, Make and GHL jobs alike; the real build happens after the hire. Design standard: `jobs/_PROTOTYPE_DESIGN.md`.
- The bar (Lorenzo, 2026-09-28): gorgeous and elegant, "almost like a $15,000 custom build". Read `jobs/_PROTOTYPE_DESIGN.md` in full before designing and follow it; it overrides any style cue elsewhere in this section. When the post asks for a system, the page IS that finished system running on sample data ("this is exactly what it'll look like when it's done"), every requirement its own working screen. The first two prototypes (cold email, GHL + Pipedrive, 2026-09-28) were judged not good enough: never use them as a style reference. The GHL CRM walkthrough.html is a reference for interaction depth only, not looks.
- Positioning: it is "a working prototype of your <system in their words>", never "a mock", "a walkthrough" or "a visual". The page title and header name their outcome in their words (e.g. "Your Lead System: From Capture to Booked Call").
- Tabs follow the post's asks in the post's order, in the post's words, plus an Overview tab with the journey and a short "why it's built this way" row.
- At least one live moment: a "submit a test lead" or "run it" button that animates a sample record through the system, and a simulated outcome (reply, booking, approval). A visible "Reset" control so the client can replay it.
- Neutral branding: never an imitation of a vendor's UI (no GHL, n8n or Make logos or look-alike screens). Tool names in text are fine ("Runs on n8n").
- Samples look like their business from the post only; illustrative numbers are labelled illustrative. No real names, no client data.
- Single file, inline CSS and JS, Google Fonts only, no other external scripts. Colors as CSS variables on :root with a dark-mode override under @media (prefers-color-scheme: dark) guarded by :root:not([data-theme="light"]) and again under :root[data-theme="dark"]; body has an explicit background. Works at 1440x900 and at phone width (no horizontal scroll). No console errors.
- Where the real backend exists or is cheap to produce (GHL import files, an n8n spec), keep spec.json and compile it too, so the proposal can say "the workflows behind it are already built".
- Still write dossier.md, assessment.md and beats.md (beats follow the tabs; say "prototype" on camera, never "mock").
- Artifact page contract: no `<!DOCTYPE>`, `<html>`, `<head>` or `<body>` tags (the publisher wraps the page); put `<title>` (a 2-4 word name, e.g. "Pipedrive Lead Sync") and `<style>` at the very top. No alert/confirm/prompt, no downloads, no mailto links, no forms that submit anywhere (preventDefault). Respect prefers-reduced-motion. Design per `jobs/_PROTOTYPE_DESIGN.md`.
- The main session publishes prototype.html as a private Artifact and puts its link in the proposal ("Click through it yourself: <link>"); Lorenzo shares it when he sends the proposal. Finalize with `--variant prototype`.
