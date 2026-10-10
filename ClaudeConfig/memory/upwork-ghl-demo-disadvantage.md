---
name: upwork-ghl-demo-disadvantage
description: "GoHighLevel posts: spec compiled to import JSON, loaded into an empty workflow with the 'GHL Workflow Backup & Audit' Chrome extension; prompt lane is fallback only (2026-09-22)"
metadata:
  type: project
---

**Current (2026-09-22):** GHL posts get a real workflow in his sub-account
"AdveroSolutions" (location `ebyNANPagaK7ycf1pfge`). `compile_ghl.py` turns the spec
into the extension's import JSON; `./job <name> ghl` drops it in
`~/Desktop/GHL-Imports/`; he creates an empty workflow and clicks Import in the
extension (free 5 imports, then $19.99 one-time). First real import 2026-09-22
(Cal.com job): 12/12 steps landed, but the trigger tag filter, the tag goal and the
add-task step were guessed shapes and came in half-built. Only a real export is a
trustworthy format reference (public reverse-engineered repos disagree).

**Why:** the 2026-09-16 prompt lane cost 15 min of hand-fixing on a flaky canvas;
he said "there has to be a faster way". The import lane was his breakthrough.
GHL's public API and official MCP cannot create workflows; pipelines can be
created by REST with a Private Integration token (he agreed to make one,
2026-09-22), tags/fields/custom values via the MCP or REST.

**How to apply:** prefer one short workflow per trigger event (booked, cancelled)
over one long flow with a long wait plus a goal; he found the single-flow version
hard to follow. Never touch his real "Sales" pipeline. Lane details in
`Coding/upwork-pipeline/jobs/_GHL_BUILDER_BRIEF.md`. See [[upwork-batch-mode]] and
[[upwork-quality-overhaul-2026-09]].

GHL REST API facts (2026-09-22, first live read): services.leadconnectorhq.com sits behind
Cloudflare and answers Python's default User-Agent ("Python-urllib/3.x") with HTTP 403
"Error 1010"; any named User-Agent (AdveroSolutions-ghl-prereqs/1.0) gets 200. The PIT
lives only in upwork-workflow-generator/.env (chmod 600); Lorenzo pasted one full-access
key in chat once, advised to replace it with an 8-scope key (tags, customFields,
customValues, opportunities; readonly + write each).

First live apply (2026-09-23): the 8-scope key created tags, contact fields and custom
values fine, but `POST /opportunities/pipelines` answered 401 "The token is not authorized
for this scope" (opportunities.write is not enough). Until a scope that covers pipelines is
found, pipelines are made by hand in the GHL UI, then a prereqs dry run refreshes the id map.
Same day Lorenzo said demo objects crowd his account: GHL props now go live only where the
post names a specific automation, one workflow live and the rest on the chart; vague posts
get a chart and add nothing to his account.
Tightened 2026-09-24: GHL posts default to a chart; only a post that is just one automation gets a GHL workflow, and account setups are always charts. See [[upwork-builds-minimal]].
