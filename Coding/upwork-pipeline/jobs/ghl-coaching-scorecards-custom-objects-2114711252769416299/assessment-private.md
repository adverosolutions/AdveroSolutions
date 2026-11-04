# Private assessment, pick 1 (4h batch 2026-10-26)

Job: https://www.upwork.com/jobs/~022114711252769416299 (id 2114711252769416299)
Client: Pursley Business Wealth (named in post), US MO. Coaching for medical/service practice owners.
Personalization: none. Post gives no person name; "Greg" appears in one freelancer review only (U-006 needs two). Recipient falls back to the business name.
Surface: GoHighLevel is the tool the post names. Supported adapter `ghl` (workflow, record, outcome). No unsupported native screen needed.

Scene map (Standard, ~2 min):
1. reminders (ghl workflow), ~40s. Purpose: the weekly reminder and missing-week follow-up. New fact: Monday link, Wednesday check, one follow-up, coach alert, thank-you branch if already submitted. Evidence: GHL vertical workflow with If/Else, run path on the "Not yet" branch.
2. scorecard-record (ghl record), ~35s. Purpose: each week kept as its own record. New fact: Week 44 creates a new Weekly Scorecards custom-object record linked to contact, practice, coach; weeks 41 to 43 listed as separate records. Evidence: record fields (all the post's metrics) and event history.
3. coach-view (ghl outcome), ~35s. Purpose: coach-facing result. New fact: 7 of 9 submitted, Dana flagged for collections 82% vs 90% target, training module added to action plan. Evidence: stages + metrics.
Cover ~10s, close ~15s.

Sample path: Dr. Dana Ellis, Ellis Family Practice, coach Priya Shah, Week 44 (Oct 26 to Nov 1), submitted Thu Oct 29 3:12 PM after the follow-up. Collections $39,500 / revenue $48,200 = 82%. Weeks 41 to 44: 91, 88, 85, 82 percent (only 91 and 82 shown).

Setup caveats (private, not in the deck):
- GHL workflow catalog has no scheduler/recurring trigger key; the deck uses the Contact Tag trigger with a weekly scorecard-due tag. In the real account the weekly re-tag would come from a recurring trigger or a small re-entry workflow; confirm on account review.
- Tag removal on submission (duplicate guard) is a second small workflow, mentioned only in the related panel.
- Custom-object record view is the legacy ghl record adapter, illustrative, not a pixel copy of GHL's custom object UI.
- No past custom-object project claimed; screening Q1/Q2 left for Lorenzo.
