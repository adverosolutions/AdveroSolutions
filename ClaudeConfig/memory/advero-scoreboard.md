---
name: advero-scoreboard
description: "Advero Scoreboard (built 2026-10-06): Lorenzo's daily marketing + sales dashboard and source of truth, a private claude.ai Artifact in the Spatial look reading Instantly/Upwork/GHL/Calendar live; also holds the LinkedIn tracker rows"
metadata:
  node_type: memory
  type: project
  originSessionId: 0532abdf-9182-43e2-a86e-95d7f0d4e5b6
  modified: 2026-10-07T02:11:37.429Z
---

Live at https://claude.ai/artifact/7i5vMdwy4aHPf9xrKG6nDr (private). Code in `Coding/scoreboard/` (SPEC.md is the contract), runbook `Agentic Worklfows/runbooks/scoreboard.md`, tests `node --test Coding/scoreboard/tests/*.test.js` (94 on 2026-10-07 after the reply-rate fix, commit 1f42f4b, artifact v3; the directory form fails on Node 24). Republish from that file path with `files: {"scoreboard-data.js": ...}` to keep the URL.

He asked for it because GHL "looks terrible" and he wants one marketing + sales dashboard to check daily instead of clicking around. He chose the Spatial look (light only, no dark theme).

- Reads via the Artifact `mcp` capability with his own connectors (display names Instantly, Upwork, GHL, Google Calendar); no server, no keys. Writes only to its own db: `settings/costs`, `upworkRooms/<proposalId>`, `linkedinRows/<id>` (rule: root read admin, write owner).
- Upwork "client replied" = status `Activated` ("Invitation accepted"), `Offered` or `Hired`, or a room from `get_room`, read at `data.proposalRoom.id` (NOT_FOUND means no reply). This replaces the always-blank viewed/replied columns in proposals.csv. Before 2026-10-07 it read 0%: Activated was never fetched and the room id was parsed from the wrong field. Room-cache docs now carry `v: 2`.
- Cold email rates divide by **emails sent**, never by leads contacted. This is Lorenzo's rule 6 in the daily-reports-and-metrics skill. He caught the leads-based version showing too high (1.10% vs a real 0.70%). Every rate on the page shows its basis ("replies ÷ emails sent").
- Instantly `reply_count_unique` already excludes auto-replies.
- Real sales calls are Zoom events in Google Calendar, not GHL bookings. GHL location `ebyNANPagaK7ycf1pfge`; the connector needs `locationId` on every call and rejects `location_id` in the query.
- The LinkedIn tracker lives in the dashboard because the [[linkedin-outreach-channel]] skill says "his own dashboard" holds the rows. Rows Claude writes via ArtifactData need `updatedAt` (ms).
- Merged to main and pushed 2026-10-09 ([[sync-2026-10-09]]); `Coding/scoreboard/` on main is the source now.

**Why:** a single daily view across channels, and data for choosing where to spend hours (cost per booked call per channel).
**How to apply:** change the dashboard through SPEC.md + workers + reviewer, then republish to the same URL. Parked review items are in the 2026-10-06 session; none are blocking. Related: [[daily-metrics-tracker]], [[upwork-followup-pipeline]], [[instantly-2026-campaigns]].
