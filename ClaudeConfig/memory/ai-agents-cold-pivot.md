---
name: ai-agents-cold-pivot
description: "2026-09-30 cold email pivot: 3 keeper campaigns stay, 3 paused ones move to an AI agents offer; working copy lives in a Claude Doc, not the edit-here Google Doc yet"
metadata:
  node_type: memory
  type: project
  originSessionId: 81de3cb2-cb8d-49e0-aaf4-a177120248ec
  modified: 2026-09-30T21:34:01.060Z
---

On 2026-09-30 Lorenzo kept three 2026 campaigns sending as written (Cleaning Client Reactivation, Cleaning Trigger Outbound, Recruiting Client Reactivation, the only three with an opportunity) and paused Bookkeeping Reactivation, Bookkeeping Trigger and Recruiting Outbound to pivot them to an AI agents offer. Two AI agents campaigns ("2026 Service - AI Agents", cleaning copy; "2026 Recruiting - AI Agents") appeared in Instantly the same day, active, no sends, time-saving offer with no proof or guarantee.

Working copy doc (Claude Doc, edited together): https://claude.ai/code/artifact/64259511-8228-48ac-bd5a-b8adc24d2dc8 . It holds the live snapshot, drafts that swap only the offer lines, a growth-vs-time-agent offer test, an "out of left field" shape test and a day 7 step 3.

**Why:** he wants to test AI agents as the offer across the non-keeper campaigns; the keepers are not to be touched.

**How to apply:** read the doc (sinceRev) before continuing; final copy still goes through the edit-here Google Doc and the change-set, live only on his "go live". Open questions in the doc: pause the AI campaigns before edits land, new campaigns vs in-place, "AI" ban in offers.md/reply engine, proadvero inboxes back in all 8 campaigns. See [[instantly-2026-campaigns]], [[deliverability-2026-09-25]], [[no-live-changes-until-tested]].

**Decisions 2026-09-30 evening (Lorenzo, answering the doc's open questions):**
- Create six new AI agents campaigns (bookkeeping & tax, insurance brokers, landscaping, marketing agencies, MSP, pest control).
  - Each has the doc's step 1 A/B variants on the same subject, plus step 2 on day 3.
  - Settings are cloned from "2026 Service - AI Agents", including the same 12 inboxes.
- Claude never turns a campaign on. Lorenzo reviews every campaign and activates by hand.
- Do not pause any additional campaign. Service and Recruiting AI Agents keep running as they are.
- The word "AI" is no longer banned in copy.
- The proadvero.com inboxes are back in on purpose.
- {{slot1}}/{{slot2}} hold real calendar slots chosen by send day:
  - Instantly has no calendar variable; Liquid `now` gives only the date and weekday.
  - `Coding/lead-scrape-2026/slots_daily.py` reads GHL free slots (the booking engine's calendar) and writes slot1/slot2/slot_date into each lead's custom variables. It is meant to run at 05:00 CT Mon-Sat.
  - The push sets initial values, so a variable is never blank.
- Change-set: `Agentic Worklfows/changesets/ai_agents_campaigns_2026_09_30/`. New ids go in `instantly_campaigns_ai_agents.json`, never in `instantly_campaigns.json`, because `--activate` turns on every id in that file.
