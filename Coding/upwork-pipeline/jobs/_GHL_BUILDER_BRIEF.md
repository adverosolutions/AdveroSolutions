# GoHighLevel lane (JSON import, 2026-09-22)

GHL's public API and official MCP cannot create workflows. The lane is: the spec
compiles to the JSON that the "GHL Workflow Backup & Audit" Chrome extension
imports into an empty workflow in Lorenzo's own sub-account ("AdveroSolutions",
location `ebyNANPagaK7ycf1pfge`; never a client location). First real import
2026-09-22 (Cal.com job): 12 of 12 steps landed. The Build-Using-AI prompt lane
is the fallback only (last section).

Keep his account uncluttered (Lorenzo, 2026-09-23, tightened 2026-09-24).
Everything a GHL prop needs is created in his real sub-account, so GHL posts
default to a chart (`"platform": "diagram"`, chart rules in `_AGENT_BRIEF.md`
step 4):
- Account setups, multi-location or multi-pipeline builds, snapshots, audits,
  consultations, and any post that names several workflows: chart only.
  Nothing is created in his account, and he never walks through a whole
  account setup on camera.
- Only a post that is just one automation (one trigger and what follows it)
  gets a GHL workflow spec. That one workflow goes live (`ghl_prereqs` on it,
  its import file loaded), with only the steps the automation needs.
- The narrow key cannot create pipelines (`POST /opportunities/pipelines` answers
  401 "not authorized for this scope"). Lorenzo makes the pipeline by hand, then a
  prereqs dry run refreshes the id map.

Tool root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator`

## Spec vocabulary (subagents write this)
`"platform": "gohighlevel"`. From `_AGENT_BRIEF.md` these apply: the rebuild
rule and its revise-round exception, the dossier first, the title in their
words, the numbers rule, the Sections rule (one per requirement in their order,
grouped past 5), labels, notes, tools, their data in the samples, the
assessment and the beats. These do NOT apply to GHL specs:

- **No n8n error trigger.** `trigger.app` with app `n8n` op `error_trigger`
  fails `split_ghl_spec` with "GHL specs need app ghl and an op from the closed
  list". GHL has no error workflow; leave it out.
- **No n8n "Shape" rules** (10 to 18 flow nodes, the error path) and **no n8n
  params shorthand** (`condition` left/op/right, `service`/`url`/`body`,
  `channel`/`text`, `path`, `system_message`). GHL params are the ones in the
  closed op list below.
- `client` / `overview` / `config` are optional and do not render in GHL (the
  "Built for" sticky and the Config node are n8n canvas items). A `nearest`
  result is only a reference when its platform is `gohighlevel`.

GHL-specific:

- Triggers: `trigger.app`, `app: "ghl"`, `op` from the list below.
- Actions: `app.action`, `app: "ghl"`, `op` from the list below.
- Waits: `flow.wait` with `params.amount` + `params.unit`.
- Gates: `flow.branch` with `params.condition` in plain English, e.g.
  `contact tag includes "bid-sent"` (not the n8n left/op/right shorthand).
  Every gate that tests tags also carries them explicitly:
  `params.tag` (one tag or a list) and `params.negate: true` for "does not
  have". The compiler then never has to read the sentence, so it can't flip
  or drop a tag. Example: `{"condition": "Contact does not have tag
  \"bid-sent\"", "tag": "bid-sent", "negate": true}`. One gate tests one
  thing: split "has tag X and is in stage Y" into two gates.
  A tag or reply gate may carry `params.negate: true|false`; when present it
  decides the test, so set it whenever the sentence has a second clause with
  a negative word. Other gates (stage, field, email opened) import with no
  condition and are set by hand after import.
- AI steps: `ai.llm` with `params.prompt` (compiles to `ai_step`).
- A chain end: `flow.noop` (compiles to `end`).

Closed op list (`compile_ghl_prompt.OPS`; required params first, optional in []):
- Triggers: form_submitted([form]) survey_submitted([survey])
  customer_replied([channels]) contact_created contact_tag_added(tag)
  contact_tag_removed(tag) pipeline_stage_changed(pipeline, stage)
  opportunity_created(pipeline) opportunity_status_changed(status, [pipeline])
  appointment_status(status, [calendar]) inbound_webhook missed_call
  invoice_paid order_submitted birthday task_completed
- Actions: add_tag(tag) remove_tag(tag) send_sms(message) send_email(subject,
  body, [from_name]) wait([amount, unit]) create_opportunity(pipeline, stage,
  [name, value, status]) update_opportunity(pipeline, stage, [status])
  internal_notification(type sms|email|in_app, message, [to, subject])
  if_else(condition) goal(goal_type, [tag, form, status, if_not_met end|continue])
  assign_user([user]) create_task(title, [due_in_days, assign_to])
  update_contact_field(field, value) add_to_workflow(workflow)
  remove_from_workflow(workflow) send_review_request webhook(url, [method])
  ai_step(prompt, [output_field]) call(whisper, [to, timeout_seconds])
  manual_action(type, [title, instructions]) go_to(target) end
- goal_type: tag_added tag_removed form_submitted appointment_status
  payment_received email_event trigger_link invoice_paid

add_tag and remove_tag take exactly one tag, as a plain string; to add two
tags, use two steps. Every action name param (tag, pipeline, stage, field,
output_field, workflow) is a plain string, never an object or a number. A
gate's `params.tag` is different: one tag or a list. Every GHL name the spec
creates or references (tags, fields, `{{contact.<key>}}` keys, custom values,
pipeline, stages) is plain ASCII: no accented letters ("Jose", not the
accented spelling), hyphens not en dashes. `ghl_prereqs` refuses anything
else before any call. Message bodies and labels may keep the client's accents.

Unknown ops and missing required params are compile errors, on purpose.

## Self-check (subagents, read-only)
After `WorkflowSpec.load(...).validate()`, compile the spec in memory against
the location's id map. It writes nothing (no `out/`, no vault, no clipboard):
```bash
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator && python3 -c "from upwork_gen.spec import WorkflowSpec; from upwork_gen.compile_ghl import compile_ghl_many; import json; s=WorkflowSpec.load('/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline/jobs/<slug>/spec.json'); print([ (n, sum(1 for x in w['nodes'] if x.get('nodeType') not in ('branch-yes', 'branch-no')), u) for n,w,u in compile_ghl_many(s, json.load(open('upwork_gen/catalog/ghl_ids_ebyNANPagaK7ycf1pfge.json')), 'ebyNANPagaK7ycf1pfge') ])"
```
It prints one `(workflow suffix, action count, unresolved names)` tuple per
workflow; the suffix is empty when the spec is one workflow. The count is every
action node: each If/Else counts once, its Yes and None branch nodes are left
out, and triggers are not counted. It should equal the spec's non-trigger flow
nodes in that workflow (more only when a shared tail is copied into both
branches). An exception is a spec error: fix it. Unresolved names (a tag, a
pipeline, a workflow) are expected until `ghl_prereqs` runs; check each one is
a name the spec itself creates or references on purpose. One tuple per
independent trigger is the intent: if you expected two workflows and see one,
the chains share a step.

## Design rules
- **One short workflow per trigger event.** A spec with several independent
  triggers compiles to one file per trigger. "Call booked" and "call cancelled"
  as two small workflows reads senior; one long flow with a 14-day wait and a
  goal reads confused (Lorenzo found it hard to follow on camera).
- **No long waits used as watch windows.** If something should stop the flow,
  make it its own trigger (a second workflow) or a goal, not a wait that sits
  for days hoping to be interrupted. Waits are for real pacing between messages.
- **Message bodies in full**, with merge fields: `{{contact.first_name}}`,
  `{{contact.<custom_field>}}`, `{{custom_values.<key>}}`. They are read aloud
  on camera and land verbatim in the workflow. Write them in the client's voice
  and terms, with their numbers.
- **Every tag, custom field, custom value and pipeline the spec references is
  created by `ghl_prereqs`**, so reference them by the exact name the spec uses.
  Name the demo pipeline for the client ("Mark - Webinar Registrants"); never
  use or modify his real "Sales" pipeline.
- **Stop-on-reply pattern** (reply is not a goal type): the main workflow ends
  with `goal(tag_added, <x>-replied, if_not_met end)` followed by the reply
  actions, no-response actions go before the goal, and a companion workflow
  `customer_replied -> flow.branch(condition "contact tag includes \"<x>-sent\"", tag "<x>-sent") -> add_tag(<x>-replied)`
  makes the goal fire. References: `examples/ghl_bid_follow_up.json` and
  `examples/ghl_bid_reply_catcher.json` in the tool repo.
- **No manual hand edits on camera.** If an imported step is wrong, fix the
  spec (or the compiler) and re-import into a fresh empty workflow.
- Format source of truth: `reference/ghl_export_sales_request_follow_up.json` in
  the tool repo (a real export). Shapes still being confirmed against a real
  export: trigger filters, tag goals, create_task, update_opportunity,
  manual_action, if/else condition bodies, and every trigger except the form
  trigger. Check those steps for orange dots before recording.

## Per job (main session)
1. Prerequisites, dry run then apply:
   ```bash
   cd <tool root> && python3 -m upwork_gen.ghl_prereqs <job>/spec.json
   cd <tool root> && python3 -m upwork_gen.ghl_prereqs <job>/spec.json --apply
   ```
   Controlled-environment rule: the FIRST `--apply` on a new account or a new
   `GHL_PIT_TOKEN` waits until Lorenzo has seen that dry-run output and said go.
   After that first approved apply, the per-job `--apply` is approved for this
   sub-account; each job still runs the dry run first.
   `--apply` creates only what is missing (tags, contact custom fields, custom values, the
   pipeline with its stages) through the GHL REST API with `GHL_PIT_TOKEN` from
   the tool repo `.env`, and refreshes `catalog/ghl_ids_<location>.json` so the
   compiler resolves names to ids. It never deletes or modifies anything and
   refuses a pipeline named "Sales". Exit 3 means an existing pipeline lacks a
   stage: add that stage by hand or rename the demo pipeline in the spec.
   A revise round that adds a tag, field, custom value or pipeline reruns
   `ghl_prereqs` (dry run, then `--apply`) before the job is re-batched.
2. Compile with the batch (`python3 -m upwork_gen batch <job dirs>`): writes
   `<slug>.ghl.json`, or `<slug>--<n>-<trigger>.ghl.json` per workflow when the
   spec has several independent triggers, plus the chart as usual. Next to each
   `.ghl.json` it copies that workflow's `.ghl-prompt-oneline.txt` and
   `.ghl-prereqs.txt` into the job folder (used only by the fallback lane).
3. `./job <name> ghl` copies every `.ghl.json` to `~/Desktop/GHL-Imports/` and
   opens the folder.
4. Lorenzo, per file: Automation -> Workflows -> create an empty workflow, name
   it as the file says, open the Backup & Audit extension, Import, pick the file.
   Free for 5 imports, then $19.99 one-time. Leave it in Draft; never Publish or
   Test.
5. Fit to screen, confirm step count and names match the spec, no orange dots
   except connections the client sets. Screenshot to `ghl-canvas.png` in the job
   folder for the verification pass.

## Browser facts (verified, still true)
- Extension popups and file pickers need Lorenzo's own click; the agent cannot
  drive them. The import itself is his step.
- Never type on the workflow canvas. Without a focused field, keystrokes fire
  builder shortcuts (`n` opens Notes; on 2026-09-21 a typed prompt renamed the
  workflow and created a dozen empty drafts).
- The workflow area is a cross-origin iframe: `find`, `read_page` and JS cannot
  see it. Coordinates only, and re-screenshot after any window resize.
- After a `Save action` the canvas often stops taking clicks until the URL is
  reloaded.

## Fallback: Build Using AI prompt lane
Only when the import lane is blocked (extension down, import limit, a shape that
will not import).
1. Use the per-workflow files `batch` already copied into the job folder:
   `<stem>.ghl-prompt-oneline.txt` and `<stem>.ghl-prereqs.txt`, where `<stem>`
   is `<slug>` or `<slug>--<n>-<trigger>`. One Build Using AI run per
   `.ghl-prompt-oneline.txt`, each in its own new workflow. Do not use
   `python3 -m upwork_gen ghl <spec>`: it renders one prompt for the whole spec
   and raises on a spec with several independent triggers. Run
   `ghl_prereqs --apply` first so the builder finds every tag and pipeline.
2. From the workflows LIST page: click a blank spot, `+ Create workflow` ->
   `Build Using AI` (the dropdown item; the standalone button does not respond).
   This dialog is the only safe prompt box; not the empty-canvas box, not the
   side chat.
3. Click inside the textarea, type ONE character, zoom-screenshot to confirm it
   appeared, then type the rest of the ONE-LINE prompt. A newline is Enter and
   Enter submits. Never cmd+a on that page. Click the round arrow, wait 60 s.
4. If/Else branches often come back empty: fill them with one additive prompt in
   the builder chat ("Fill in the empty branches of the If/Else named X. Do not
   delete anything. Under branch A add ..."). Delete requests trigger a
   confirmation card that dead-ends. A duplicated step can be deleted by hand
   (node menu -> Delete action).
5. Fit to screen, compare to the spec, screenshot to `ghl-canvas.png`.
