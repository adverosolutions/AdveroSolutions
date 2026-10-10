---
name: upwork-followup-pipeline
description: "Upwork follow-up drafts for proposal chats; bespoke, Lorenzo sends himself; stages he controls; separate GHL Upwork pipeline (2026-09-22)"
metadata:
  node_type: memory
  type: project
  originSessionId: 5a6eeb0b-0a8e-4f7a-80da-80780c7ba0d5
  modified: 2026-09-23T04:57:47.034Z
---

Built on 2026-09-22 in `Agentic Worklfows/services/upwork_followup/`. `DESIGN.md` there is the binding spec.

**What it covers**
- Only chats that clients open on proposals Lorenzo sent. Rooms with any contract, including ENDED ones, are excluded.
- Every draft goes to Lorenzo. He sends it himself on Upwork. The engine never writes to Upwork, and a test enforces that.
- A morning batch at 08:30 CT drafts either a reply (the client wrote last) or the next follow-up. Follow-ups fall on calendar days 2, 4, 7, 11, 16, 23 and 30 in America/Chicago time.
- Drafts must be bespoke, never template-sounding. A call is suggested only when the conversation supports it.

**Stages**
- Six stages, matching cold email.
- Lorenzo moves them with `python3 -m jobs.upwork_followup --stage ...`. His move always wins.
- Stages outside new_reply and proposal_sent get no drafts.

**GHL**
- Upwork uses its OWN "Upwork" pipeline (`ids.json` `pipelines.upwork`), which Lorenzo creates in the GHL UI.
- Contacts without an email in the Sales pipeline block `pipeline_sync`'s reverse check, which is why Upwork can't share it.

**Upwork MCP data shapes (confirmed live)**
- Participant text is wrapped in `<untrusted_participant_content>`.
- `list_messages` returns newest first and uses `from_side`.
- Offers link to a job only through `job.id`.
- `get_room` returns NOT_FOUND (`{error_code: NOT_FOUND, status: error}`) until the client messages; a found room is `data.proposalRoom`.
- Blocked rooms don't appear in `list_rooms`; their newest message is an MCP line "System event: blocked. View this conversation on upwork.com..." on Lorenzo's side. The collector flags `room.blocked` and sequence closes the thread (first real pull 2026-09-23 found 2 of 3 linked rooms blocked).

**Why:** Lorenzo wants as many Upwork contracts as possible through follow-ups, but automated-sounding messages would look low quality.

**How to apply:** never automate Upwork sends. Never touch the application flow or the Demo Library loop.

Related: [[upwork-morning-pipeline]], [[cold-email-template-autosend]].

Status 2026-09-23: committed b06daac plus price-guard commits 9d4a436, d869007, 5422402, 50c5101, dd6e5a0 (copy gate refuses agreeing to a client-proposed price, with or without the figure). Known gap: rate form "2,000 a month works out fine" (_RATE_AGREED_RE keeps the old guard).
