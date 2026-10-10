---
name: upwork-workflow-generator
description: "Upwork proposal tool at Coding/upwork-workflow-generator — generates n8n/Make workflows as visual props for a 2-3 min Loom, targeting submission within 5 minutes"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4d10cb0-4b89-4132-a193-8c07de7ccd4c
  modified: 2026-08-26T13:28:38.381Z
---

Lorenzo applies to Upwork n8n/Make.com jobs by recording a 2–3 minute Loom walking
through a workflow built for that specific posting. Target is **submitted within 5
minutes of the post going live**. The workflows are visual props — they do not
execute and carry no credentials. They must import cleanly first try, look
senior-built, and pin sample data on the first and last node.

**The reframe that drives the design:** with a 2–3 min Loom in a 5-minute budget,
generation latency is noise (6 ms vs 6 s). What actually protects the clock is
import reliability and zero-touch layout — and *take count*, which is why the
vault engine may win despite both engines being fast.

**Two engines, split tested from application #1** (decided 2026-07-31, he chose to
build both in parallel rather than sequence them):
- `vault` — 20 hand-authored archetypes, no model call, ~6 ms
- `compiler` — Claude authors a WorkflowSpec in-session, ~6 s

`runs.csv` logs both. The two columns carrying real signal are `loom_takes` (does
vault familiarity reduce re-records?) and `replied`. `gen_ms` is expected to stay
noise.

**The vault self-grows.** Every compiler run promotes its spec into
`vault/archetypes/` *and* mines keywords from the job post into
`vault/keywords.json` (classify.py merges them at import). Both halves are
mandatory — a promoted spec without keywords is unreachable, which looks like
coverage and behaves like a gap. Keyword mining strips the "to apply, please
include…" tail first, because that boilerplate matches half of Upwork.

**Confirmed on a live n8n canvas 2026-07-31:**
- `pinData` DOES survive a clipboard paste — the Cmd+V path is correct.
- Sticky colours: 3=red, 4=green, 5=blue, 6=purple, 7=grey (1, 2 unknown). Red
  is kept out of the rotation; it reads as an error state.
- n8n renders two node widths: ordinary ~100px, agent/chain nodes ~200px.

Still untested: missing-credential warning triangles at recording zoom.

**Not every job wants an n8n build — some want a plain thought-process flowchart.**
Learned 2026-08-24 on a "review our GHL automations and find gaps" post: when the ask
is an audit/consulting service (no client access yet, nothing to actually build), do
NOT compile an n8n-style workflow with `app.action`/`ai.agent` nodes pretending an
automation does the work. He does the audit himself — the diagram has to show *his*
manual thought process, not a fake AI-run audit. For that case: use only
`data.transform`/`flow.branch`/`data.aggregate` node kinds (no `app.action`, no
`ai.agent`/`ai.model`), skip the trigger node entirely (the "no trigger node" warning
is fine and expected, there's nothing to import), and when he says "make it a
straight flow" strip out branches and loop-backs too — one linear chain of steps only.
The `.mmd.md` Mermaid render is the cleanest artifact for this case since it's plain
shapes with zero platform branding; the Excalidraw scene works too as long as no
app-labeled nodes are in the spec. Frame the steps around money (revenue path, dollar
cost of each leak, ROI-ranked fixes) rather than engineer language (efficiency, step
count) — see [[upwork-proposal-copy]] rule 10.

**The Loom build is always required, whether the post asks for one or not.** Corrected
2026-08-24 after suggesting he skip it for a screening-question-gated ongoing hourly
role that never mentioned a demo in its application section. He overruled that: "the
loom is our superpower, it's always required." Don't gate the build/demo decision on
whether the post explicitly requests one — it's his standing differentiator regardless
of the application format (open proposal, screening questions, whatever). What changes
per-post is what to demo and how long the video runs, not whether one exists.

Related: [[project_architecture]], [[user_lorenzo]], [[upwork-proposal-copy]]

**Native Excalidraw renderer, 2026-09-09.** `upwork_gen/compile_excalidraw_native.py`
replaced the swiftlysingh DSL renderer: stage bands with title and note, kind-coloured
shapes, diamond gates, labelled yes/no arrows, dashed loops, AI pills, written
synchronously on every run. He called the result "so much freaking better" and now wants
it for GoHighLevel and Zapier posts too (chart is the prop there). Also that day: n8n,
Make, Mermaid and Excalidraw outputs are ASCII-only (middle dots rendered as accented
characters on paste), Make modules ship with prefilled mappers (connections, webhooks, branch
conditions and AI sub-nodes still need setting; SKILL lists the limits), catalog gained `trigger.app:n8n:error_trigger` (was importing as
a Calendly trigger) and Ollama model/embedding entries. All uncommitted in the tool repo
until he asks.
