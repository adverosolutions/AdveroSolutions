---
name: offer-intel
description: "Offer Intel (Maker School wins -> ranked offers): first live run 2026-09-23, Sheet id, fixes from that run (collect --via mcp etc., 2026-09-24), what is still open"
metadata:
  node_type: memory
  type: project
  originSessionId: 8114a7c3-f6aa-4ad1-bf59-6f8c59545372
  modified: 2026-09-24T03:55:11.847Z
---

First live run 2026-09-23: 90 days of Maker School Wins (257 posts, 223 wins, 140 winners), $2.15 of model calls. Delivered to Google Sheet "Offer Intel: Maker School Wins", id `1ZjV3CbOqoembImFLEAD8M1PgCtrT6SMDzx7av2lTeyc` (owned by Lorenzo, shared to the service account as writer; tabs Summary / Patterns / Industries / Offer types / Wins / Winners). The Sheet was written by a scratch script, not repo code.

**Fixes from that run (2026-09-24, branch `claude/maker-school-wins-tracking-153w0r`, commits 197da21..a22912e; merged to main and pushed 2026-10-09):** `collect --via mcp` (the skool-mcp client via `services/offer_intel/skool_mcp_fetch.mjs`; Playwright can't run on the Mac), tolerant JSON parse in extract.py, one-client price rules + pricing-model definitions in the prompt, closed-deal-only medians, sorted replies, First Last author names. Runbook documents the mcp path. Live smoke passed (1 page, re-save hash stable, a 17-reply thread matched).

**Still open:** comments come 25 top-level per call and the paging parameter is unknown (39 of 256 threads had more; `threads_partial` counts them). "Pay per closed call" is ambiguous between pay_per_meeting and performance in the prompt. Warm deals tagged cold_call (gate channel) was not addressed. The new prompt is untested on a paid run.

**Why:** the run facts and open items aren't in the repo.
**How to apply:** for a re-run or the weekly job, use `collect --via mcp` per `runbooks/offer_intel.md` and write to the same Sheet id. Related: [[maker-school-digest]].
