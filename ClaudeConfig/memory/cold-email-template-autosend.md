---
name: cold-email-template-autosend
description: "Cold-email replies auto-send from templates Lorenzo approved once; replaces the old \"first reply never auto-sent\" rule (2026-09-22)"
metadata:
  node_type: memory
  type: project
  originSessionId: 5a6eeb0b-0a8e-4f7a-80da-80780c7ba0d5
  modified: 2026-09-23T04:57:39.367Z
---

On 2026-09-22 Lorenzo decided that he approves cold-email TEMPLATES once, and every email of that type then sends automatically, with no per-email Approve. He explicitly approved changing the written rule "first reply to a positive is drafted for approval, never auto-sent" to "auto-sent only when it uses a template Lorenzo approved".

- **Registry (committed 8dfc53c, 2026-09-23):** `services/reply_engine/template_approvals.py`, `config/approved_templates.json` (sha256 per approved text, empty until Lorenzo approves) and `jobs/approve_templates.py`. 111 approvable ids. Each id's hash covers the main text, every fallback variant and a `value_formats` block rendered by the real time/slot formatters, so any wording or format change needs re-approval. Hashes depend on pytz (pinned 2023.3) and must match between laptop and Modal.
- **Kill switch:** `AUTO_SEND_TEMPLATES`.
- **Send-path wiring:** piece CT3, built after the S-rest reply-engine fixes commit. Until then nothing auto-sends.
- **Review format:** he reviews the templates in a Google Doc.

**Why:** he does not want to approve every individual email. The cadence and messaging are fixed by the templates he signs off on.

**How to apply:**
- Never auto-send a body whose template hash is unapproved or has changed since approval.
- Any draft with copy-gate problems still gets a card.
- LLM polish stays off for auto-sent categories.
- Upwork is the opposite: it stays bespoke and hand-sent, see [[upwork-followup-pipeline]].
- Related: [[no-live-changes-until-tested]].

Status 2026-09-23: CT3 phase 2 committed as 4232375 on branch revenue-automation (not pushed, not deployed). Catalogue is 108 templates (digest 392b01cd05449198, identical under py3.9 and 3.11). Approval docs v2 are in his Drive folder 1yww1rrk0blgKnD98CkIY95XPEsaDZQ9c (start doc 1rMUEO46TqgDLmj9eA5K0uBHdHF13KT9nYGllMgI5EU4); old v1 docs renamed "OLD, do not approve from this". No templates approved yet. Two tiny copy items parked: show_rate.reminder_15m_sms "Hopping on now" at T-15, and the beyond_horizon doc example.

UPDATE 2026-09-23 (supersedes the v2 docs above): Lorenzo found the terminal approval flow too complex. He now edits ONE Google Doc, "Advero emails: edit here (every email, one doc)", id 1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U (folder 1yww1rrk0blgKnD98CkIY95XPEsaDZQ9c). It holds all 12 Instantly cold steps + 108 engine templates (379 tagged blocks). When he says "done", everything in the doc counts as approved (his instruction; replaces jobs/approve_templates.py in his terminal); "go live" is a separate yes. Read-back tooling persisted in `Agentic Worklfows/.tmp/template_doc/` (manifest.json baseline, parse_doc.py, diff_doc.py, README.txt); Drive download_file_content with exportMimeType text/plain saves base64 JSON to a file, so no hand copying. Apply path (doc edits -> code, Instantly change-set, approvals from doc) is not built yet; build it when he says done.
