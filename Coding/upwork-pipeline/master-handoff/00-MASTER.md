# Lorenzo’s Upwork demo and delivery master

Version: 20 October 2026. Owner: Lorenzo Villarreal, AdveroSolutions.

This is the starting point for any model taking over Lorenzo’s Upwork proposal
and Loom system. It consolidates the decisions from the original working chat.
Read this before generating a demo. The accompanying screenshots, runnable
compiler, sample specs, reviews and locked proposal source preserve the details;
do not ask Lorenzo to teach those again.

This handbook governs the Upwork sales-demo lane. “Delivery” here includes job
intake, demonstration, recording, proposal preparation, review, queue and handoff.
It does not authorize deploying a client’s production automation or sending an
application. Post-sale fulfillment has its own process; do not infer it from a demo.

## 1. Start with the right files

The working repository is:
`/Users/lorenzovillarreal/Desktop/AdveroSolutions`.

The canonical pipeline is:
`/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline`.

The maintained handbook source is `master-handoff/` inside that pipeline.
The self-contained reading/build package is `.local/upwork-master-handbook/`
inside the pipeline. Open its `START_HERE.html`. A Desktop-repository launcher
named `UPWORK_MASTER.html` points to it. Do not treat a generated export as the
source to edit: change the canonical files and rebuild the package.

In the exported package:

| File or folder | Purpose |
| --- | --- |
| `00-MASTER.md` | The consolidated decisions and nonnegotiable requirements |
| `01-OPERATIONS.md` | Intake, authoring, review, queue, Loom and proposal delivery |
| `02-UI-REFERENCE-GUIDE.md` | Per-product surface plans, saved images, sources and readiness |
| `03-TEST-THE-NEXT-MODEL.md` | A self-contained assessment and scoring rubric |
| `NEW_MODEL_PROMPT.txt` | Paste this into a new model session |
| `sources/pipeline/` | Frozen copies of the current operational documents and demo engine |
| `sources/voice/` | Lorenzo voice and no-Claudeisms guidance, read-only snapshots |
| `previews/` | The four exact reviewed illustrative pages and their scripts/reports |
| `MANIFEST.json` | File hashes, source commit, dates and explicit exclusions |
| `verify_package.py` | Offline integrity and completeness verification |

The exported source tree preserves relative paths. In this master, paths such as
`templates/sales-deck/...` are relative to the canonical pipeline or the export’s
`sources/pipeline/`. Open the saved reference board at
`sources/pipeline/templates/sales-deck/visual-reference/index.html`.

### Rule precedence

1. Lorenzo’s latest direct instructions and applicable safety rules.
2. This master’s consolidated current decisions and the current
   `UPWORK_PROCESS.md` directives; preserve its locked proposal section.
3. `SALES_ACCEPTANCE.md`, `OPERATING_POLICY.md`, current content/review briefs,
   batch runbook and the latest exact-artifact review.
4. The actual schema/compiler/runtime define executable support, not visual approval.
5. Dated reference catalogs are research evidence, not current approval receipts.
6. Old prototype-week, chart-first, Claude-role/model instructions and older
   implementation specs are historical where they conflict with the above.

A later instruction or review updates only its stated scope. Do not interpret an
older “supported” flag, passing tests or a research review as visual acceptance.
If future instructions genuinely conflict, state the specific conflict; do not
silently revive an obsolete workflow. Old Claude agent names describe roles,
not Codex model requirements. Never modify shared Claude skills to fit Codex.

## 2. What Lorenzo is selling

The artifact is a sales walkthrough for an Upwork prospect. Lorenzo records a
roughly one-, two- or three-minute Loom while stepping through it. The default
editing target is about two minutes. The prospect knows a solution exists;
they need to see that Lorenzo understands their exact request and can implement
it competently. Do not teach them why automation exists.

The goal is a reply on Upwork leading to a **15-minute call**. It is not to deliver
all the implementation files, explain every API parameter, show a generic agency
portfolio, or make the viewer read a technical manual. Specificity and visible
results establish expertise. Do not invent past experience to manufacture it.

The page must look professionally prepared for the named job. Use its actual
tools, requirements, vocabulary and important exception. Match the prospect’s
awareness: establish the problem briefly, show the mechanism, show the useful
result, then make the call ask. The sales principle discussed was Eugene
Schwartz’s awareness/sophistication framework from *Breakthrough Advertising*;
that is conceptual direction, not a supplied licensed text or a source of quotes.

### The recording story

| Stop | Approximate place in a two-minute video | What must be visible |
| --- | --- | --- |
| Personalized opening | 0–10 seconds | Their problem/outcome and a prepared-for treatment |
| Mechanism | 10–35 seconds | The exact native workflow, skill, configuration or IDE surface |
| Useful result | 35–90 seconds | The record, customer response, document or other output they asked for |
| Relevant exception | Within the result beat or about 90–105 seconds | A real missing detail, reply or validation case when relevant |
| Goal and closing | Last 10–20 seconds | Job-specific directional measures and a prominent reply-to-call CTA |

These are narration targets, not animation timers. The presenter controls progress.
Usually use two or three demonstration stops between opening and close. More is
allowed only when another original requirement needs distinct visible proof.
Do not pad a short pitch. A required output must appear on **every** recording
route. Optional detail is for extra inspection, not for hiding half the promise.

Each stop must add a new buyer-relevant fact. A canvas, that same canvas with an
inspector, and the identical inspector relabeled “execution result” are not three
sales beats. Settings/context belong on a separate stop only if they add evidence.
Technical inspection can be clickable within a useful screen.

Before authoring, write a private scene map: purpose, new fact, visible evidence,
spoken cue and time budget. Narration notes must point to actual evidence—owner,
value, row, recipient, source or missing field—not repeat a slide heading.

## 3. Presentation identity is locked

Keep the approved outer presentation: blue/light palette, atmospheric background,
Inter typography, opening composition, demo framing and the strong blue closing
CTA. Do not redesign colors or create a new visual identity during daily generation.
The authoritative implementation is in the saved runtime and font files, not an
approximation from a screenshot.

The protected outer files are:

- `templates/sales-deck/runtime/base.css`
- `templates/sales-deck/runtime/components.css`
- `templates/sales-deck/runtime/shell.html`
- `templates/sales-deck/assets/inter-variable.woff2`

The opening caption is exactly:

> I've already put this workflow together for you. Let me walk you through how it works.

Lorenzo explicitly requested that prebuilt positioning on the **front page**, neatly
placed, so he can mention it once. Do not repeat it on every workflow/result screen.
Do not reinsert the word “design” into that claim or create a recurring discussion
about its placement. It is the approved sales line; it does not make the generated
HTML a real imported workflow or turn sample messages into observed live delivery.
Keep the actual backend/import status accurately documented in private evidence.

Use a brief prepared-for/business/problem treatment when supported by the post.
An appropriate first name can be supplied by Lorenzo, stated in the post, or
supported unambiguously by at least two separate client reviews. Save provenance
privately. Repetition does not prove that the person is the business owner.
Do not invent company/industry facts from unrelated hiring history.

Intro recipient fallback is explicit: verified first name → known business name →
“Prepared for your team.” When no business is known, use “your team” as the neutral
account display name; never invent a business to satisfy a required spec field.
For the cinematic comparison, route selection and Present/Preview are on the
held intro, with two minutes selected by default. Present hides setup and stays on the intro;
Next or Right Arrow advances when the presenter is ready. Escape restores setup.
Preview launches the walkthrough with preparation controls visible. No automatic
intro advancement. This comparison remains
separate from the default production template until accepted for integration.

End with three relevant **directional** measures, their definitions and a baseline
note. They are goals, not achieved statistics. Use measures tied to the work, such
as response time, complete opportunities or incomplete dispatches—not the same
three vague metrics on every deck. No invented uplift percentages.

The CTA must stand out as a CTA, not get lost among metrics. Preserve the blue
panel and the 15-minute treatment. Ask them to reply so Lorenzo can send times.
Do not make a disconnected booking control the center of the pitch. The locked
proposal asks for three times; preserve that wording there.

## 4. Native software must look and behave like the named software

The outer deck belongs to AdveroSolutions. The interior belongs to the software
being demonstrated. Keep their boundaries clear. Native palettes/type/spacing
may differ **inside** the frame; do not turn Claude, n8n, Zapier, Make or an IDE
into the same blue GoHighLevel CRM.

Identify product + surface + edition/version + theme before selecting a renderer.
Examples: Claude Skills, Claude Projects and Claude Code are different surfaces;
Grok and Lorenzo’s Grok Bot are different; Zapier visual editor and Next Gen
Workflow Manager are different; Zoho CRM, Flow and Creator are different.
Orca means an IDE (identified in research as onorca.dev), not Orca Security.
Reconfirm ambiguous product identity if it affects the screen.

Use the saved official screenshots and actual workspace captures. Inspect the
pixels, not just the page title. The UI guide links the original image, product,
surface, source page, date/qualification and hash where recorded. Do not treat an
AI-generated screenshot as evidence. A current help page can contain an old UI.
A menu crop does not establish an entire workspace.

Compare navigation, account context, tabs, controls, node geometry, ports, labels,
iconography, density, type and output placement. Do not invent decorative native
sidebars, data cards, approval dashboards or buttons to fill space. Narration goes
outside the software frame. If a job genuinely asks for a custom app, label it as
custom; that is not permission to substitute one for a named native product.

Use real node/module/action families and semantics. A job asking for native GHL
should not get an arbitrary n8n workflow in its place. A legitimate HTTP Request
can represent an integration, but a rendered request is not an executed API test.
n8n AI subnodes need typed connections; Make routes/filters need actual semantics;
reply/booking logic needs its supported trigger/settings, not a made-up action.
Unsupported native surfaces are maintenance work, not a worker’s improvisation.

Do not provide fake JSON downloads, empty “completed workflow” links or pretend
an import/snapshot was tested. The current compiler emits sales HTML and a script;
it does **not** emit importable n8n, Make or GHL automation. Real build/import work
is a separate deliverable, using verified formats and a real artifact when asked.
Prospects do not automatically receive implementation deliverables before a call.

### Current readiness, as saved

The research library covers **29 named product plans**, not every possible Upwork
product. There are four rebuilt native desktop sales candidates:

| Product | Revised story | Remaining boundary |
| --- | --- | --- |
| GoHighLevel | Form → assign Maya → create in Contacted → SMS/email; show messages and the $8,450 opportunity | Exact current-account configuration/settings not generally verified |
| n8n | Webhook → Edit Fields → two HTTP Requests; one returned opportunity table | Literal sample bodies, not dynamic/executed API proof; mobile whole-flow entry needs work |
| Zapier | Catch Hook → Google Sheets row → Email by Zapier; show both results on every route | Current editor/test-panel native references incomplete |
| Claude app | Reusable Skill → cited visit brief and missing-address hold | Current Contents/populated chat/artifact reference coverage incomplete |

Latest whole-walkthrough review:
`templates/sales-deck/native-templates/SALES-REVIEW-2026-10-19.md`.
It accepts the repaired desktop **sales candidates** for bounded review, while
withholding blanket native production/parity approval. Lorenzo has not granted
blanket acceptance merely by asking for this handbook. Older generic interiors
remain rejected. The research catalog’s older descriptions of “no adapter” for
Zapier/Claude predate the rebuild; this table and the dated final review explain
the newer candidate implementation. All research `productionReady:false` flags
remain meaningful: a reference collection does not approve a native template.

The other products have saved surface plans and varying evidence. They do not
have accepted native renderers simply because the guide names them. A new product
or changed vendor version still requires a one-time evidence/adapter update. The
purpose of this handbook is to preserve decisions and references, not pretend
software UIs can never change.

## 5. The sample must make sense end to end

Carry the same identity, email/phone, IDs, owner, value, appointment, time and
status through the scenes. Use meaningful sample values and coherent math. Never
leave a blank CRM or confirmation page. Do not show $0.00 on the sample opportunity
when the story gives a meaningful amount. Empty other pipeline columns may have
native zero totals; that is different from a zero-value sample deal.

Every result must follow from the depicted workflow. An acknowledgement does not
confirm an appointment. A board cannot animate New enquiry → Contacted unless the
workflow actually performs that transition. If the opportunity is created directly
in Contacted, show that action explicitly and a static result. Do not invent
movement for visual excitement. A static result does not need a misleading Replay.

If the pitch promises SMS and email, show their actual sample recipient/body in
the proper conversation/test view. A toast saying “sent” is not enough. If it
promises a spreadsheet row, show the persisted row fields. A document result must
be readable; preserve its source references and flag genuinely missing inputs.

The saved examples are **invented acceptance scenarios**, not real Upwork clients.
Avery Morgan, Maya Chen and Northstar are samples. Do not copy them into a real
job by accident. A successful sample is not proof of past commercial performance.

The repaired scenarios intentionally establish these facts:

- GHL asks Avery about a visit and sends an acknowledgement; no customer reply
  is invented. Confirmation remains pending. The opportunity is created in Contacted.
- n8n returns matching sample contact/opportunity IDs, 8450 and open status.
  The HTTP bodies contain literal sample values; dynamic field mapping is unproven.
- Zapier shows saved row 42 and the customer acknowledgement on all routes.
- Claude’s source notes explicitly confirm Thursday at 2 PM and an open side gate.
  The address is absent, so the brief holds it for confirmation instead of guessing.

## 6. Interactions must support recording

The presenter must be able to speak immediately on reaching a screen. Native
chapters enter with useful, settled content. Replay deliberately shows the local
sequence, finishes in roughly five seconds and holds. Show result settles at once.
No waiting for an animation that already ended before the presenter arrived.

Replay/Show result belong next to the demo, within its footer/frame area. They
must not float as a sticky page element that sticks and jumps between sections.
Navigation is presenter-controlled: chapter buttons, Previous/Next and supported
keyboard arrows. Cancel obsolete timers on navigation and repeated Replay. No
automatic chapter changes, scroll hijacking or sticky section transitions.

Check rapid replay, back/forward navigation, route changes, Present/Escape,
Talking points, reduced motion and the relevant product controls. Reduced motion
must still show the final useful state. Product panels should not silently change
or close the wrong screen. Do not add fake nonfunctional controls as sales proof.

Desktop recording is the primary scenario. Verify representative 1440px and
1280px widths and a 390px containment check. A pannable native canvas is acceptable
inside its frame, but do not claim its entire flow is visible on mobile when only
the final node is shown. Keep text readable. A reference screenshot is not the
interactive personalized demo.

Standalone pages embed required font/assets and must make no runtime network
requests or service writes. They are local visual simulations. Do not use real
client credentials to make a demonstration appear live.

## 7. Daily generation and usage discipline

Main coordinator/content default: **GPT-6.1 Sol, Medium**. A difficult bounded
implementation repair can use Sol High. Final independent review: **one Astra High
review**, covering the whole pitch, relevant behavior and native visuals. These
later cost decisions supersede earlier Astra xhigh coordinators, Astra-everywhere
batches and Max/Ultra reviewer defaults. Lorenzo can explicitly change them.

Use Standard speed for preparation/admin. Fast is reserved for explicitly
time-sensitive production, not every step. Check actual tool controls; never
claim a speed setting was enforced if the dispatcher cannot set it. No fixed
savings or daily capacity promise: measure a small representative run first.
Model availability, pricing and limits can change; verify current product facts
when needed, rather than presenting old policy notes as current pricing.

Give workers only their assigned post, supported seed, relevant reference images,
scene map and precise output folder. Do not feed this entire conversation, all
29 image collections, or unrelated jobs to every worker. Reuse accepted template
assets. Daily content workers edit the assigned spec/private notes, not runtime,
catalog, fonts, palette, compiler or lock. New interfaces belong in maintenance.

Only delegate when Lorenzo/current rules authorize it. Use actual available
capacity; the original session exposed four total slots including main, not a
universal product maximum. Do not promise more throughput by creating more chats.
Separate chats require an explicit request and share account usage. Never modify
global agent/model configuration. Claude-era role names do not mandate models.

Run mechanical checks before the focused Astra review. Give the reviewer original
requirements, exact generated artifacts, relevant source images, known limitations
and test evidence. Repair precise defects and narrowly recheck. Do not re-review
unchanged reference libraries on every job. An author’s self-check is not an
independent approval; if no independent reviewer exists, report the limitation.

## 8. Full quality gate, not just attractive screenshots

The permanent contract is `templates/sales-deck/SALES_ACCEPTANCE.md`.
For every route, verify:

1. The original problem is recognizable and the correct tool/surface is used.
2. Each stop adds a new fact; no duplicate canvas/inspector/result padding.
3. Every promised output is visible on Quick and Standard as well as Detailed.
4. The workflow causally explains the result; statuses/messages do not leap ahead.
5. Identity, value, ownership, time, IDs and totals agree across screens.
6. The useful result is legible without hunting through an irrelevant raw payload.
7. Narration supplies concrete pointing cues instead of restating the heading.
8. Goals fit the job and the blue CTA clearly asks for a reply/15-minute call.
9. Replay, navigation, notes, Present and motion handling work without stale state.
10. Native geometry/controls match the saved current applicable reference.
11. The reviewed page/spec/template hashes identify exactly what will be recorded.
12. Any unmet native evidence requirement is reported, not converted to an approval.

Schema lint rejects exact duplicate native proof payloads even when renamed. It
cannot prove sales logic or detect every semantic duplicate. Tests passing does
not replace the whole-walkthrough review. A research review, template lock or
reviewed older generation cannot be reused as approval of changed pages.

## 9. Copy, proposal and delivery boundaries

Use Lorenzo’s direct peer voice. Sentence case. No em dashes in proposals. No
invented credentials, certifications, personal availability, years, case-study
numbers or debugging stories. Use the supplied approved facts and case-study
source. Do not answer every screening question by guessing; use the locked
proposal structure and flag facts only Lorenzo can supply.

No Claudeisms: delete a sentence or clause that merely repeats or sells the
point just made. If deleting it loses no fact, question or next step, remove it.
Avoid “No more chasing leads” and similar empty kickers. Read the voice snapshots
before writing prospect-facing copy. The specifically locked proposal lines remain
locked; this rule does not authorize rewriting that template on a whim.

The proposal is not free-form copywriting. Exact text, four P.S. bullets, ordering,
preview-length rule and approved personal facts are in the saved
`UPWORK_PROCESS.md`, sections 6–7. `01-OPERATIONS.md` explains finalization.
Do not discuss prices/retainers/billing in the proposal; approved handling is
“we can cover that on the call.” Lorenzo records the Loom and submits the
application. Do not send, submit or externally publish from this lane without
his explicit instruction.

The recording queue is shared across sessions on this Mac, newest job posts first.
It is not cloud sync. Main owns registration/builds/review receipts and finalization.
Workers do not mutate the queue. A demo being built is not ready to record until
its exact generation is independently approved for the needed scope.

## 10. Lessons that must not regress

| Previous failure | Required prevention |
| --- | --- |
| Wrong app looked like GHL | Match exact product/surface against saved images before authoring |
| Mojibake, odd characters, mixed fonts | Use UTF-8, the supplied font/assets, rendered text inspection and stale-token checks |
| Blank CRM/confirmation | Useful content visible on entry and on every route |
| $0.00 sample opportunity | Preserve the meaningful value and coherent totals |
| Implausible n8n nodes or workflow logic | Use bounded actual action types and supported semantics |
| SMS/email never appeared | Show recipient/body/result in the correct destination view |
| Animations finished before arrival | Settled native entry; deliberate local Replay |
| Scroll stick/jump and stalled transitions | No scroll hijack; inline controls; cancel old timers |
| Duplicate “result” slides | Scene map and duplicate-proof lint plus semantic review |
| Optional scene hid promised result | Check every recording route against the original promise |
| Invented pipeline movement/confirmation | Explicit matching actions or an honestly static/pending result |
| Astra checked only visuals | Require the full sales, copy, causality and interaction matrix |
| Excessive model usage | Sol Medium authoring; bounded Astra High review; relevant context only |
| Old Claude agent/model rules resurfaced | Use current operating policy, never legacy role defaults |
| Another model lacked context | Start with this package and exact supporting files, not the old chat |

## 11. Keep this durable

After an accepted update: change the canonical source, rebuild/review affected
artifacts, update exact reviews/readiness, refresh the handbook export and verify
its manifest. Keep the source in Git; export does not include credentials, real
saved-job folders, live queue state, recordings, inboxes or proposal logs.

A copy on this computer and a pushed source commit are the current backup, not
a promise of automatic cross-device replication. To give another model the
knowledge, supply `NEW_MODEL_PROMPT.txt` plus local access to this folder, or the
private ZIP for a model that accepts files. The next model still needs compatible
tools/permissions to execute commands. The handbook does not grant account access.

For a controlled capability test, use `03-TEST-THE-NEXT-MODEL.md`. Do not start
another saved-job batch as a test. Lorenzo’s five rejected unrecorded jobs remain
archived unless he explicitly requests otherwise.
