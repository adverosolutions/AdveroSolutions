# Automation readiness audit for Wed Oct 21 live runs
Written Tue 2026-10-20 ~8:50 PM CT by an executor for COO. Read-only audit: no files, routines, campaigns or accounts were changed. One harmless dry run of score_vollna.py was made, writing only to /tmp (deleted afterwards) to prove it still works.
Sources: GROK_ONBOARDING_PACK.md, state/org/LEAN_ORG.md, USAGE_GATE.md / state/usage_gate.md, skills/*.md, upwork/*, linkedin/*, state/communities/*, state/maker_school_audit/*, Google Doc "Maker School and Advero Operating Manual" (id 122qT6YwoK3drjZg4Z0sHrUheays-gqBKMQcO0OirD3Y, read-only), state/decisions.jsonl, state/linkedin_*.jsonl/csv, state/leads/*, /workspace/del_20261020_eve/raw (Instantly snapshot 5:02 PM CT), agent profiles in /home/box/sand-data/agents/*/profile.json.
Limitation: routine definitions (prompts, schedules) are not stored on the box (/home/box/agent-data/workflows is empty and the agent stores hold no routine records). Routine status below comes from docs and agent messages, not the routine configs themselves.

## Summary
| Area | Status | One-line |
|---|---|---|
| 1 Vollna/Upwork selection | GAPS | Rubric and scorer work end to end by hand. Nothing runs them on a schedule, and picks aren't logged in a way you can compare against later. |
| 2 LinkedIn outreach | NOT READY for agent-sent requests | Sales Nav is live with saved searches but only 17 vetted leads. The bot is still forbidden from sending requests, and there's no daily routine or request/reply log. |
| 3 Communities | GAPS | The cadence is documented. The Community Manager has no community skill, no post calendar and no post-draft routine (only the engagement digest). |
| 4 Lead supply | URGENT GAP | Pest Control and Commercial Cleaning run out of new leads around Tue Oct 27 / Wed Oct 28. QuickEnrich pulls haven't started and the skill targets the old niches. |

---

## 1. Vollna / Upwork selection

What exists:
- `~/advero/upwork/SCORING_RUBRIC_20261020.md`: Lorenzo's rubric (client signals, never reject thin clients, ignore budget, prefer his hire types). Output is selection only (job title, link, score, one-line why). Never proposal drafts.
- `~/advero/upwork/score_vollna.py`: reads the 3 Vollna RSS feeds in `/workspace/vollna_rss.txt`, excludes already-applied jobs using `/home/box/Downloads/proposals_2026_10_20_20_16_16.csv`, scores and writes `--out` (all jobs) and `--selections` (top 12, min 55). It also has a reproducible SKIP list.
- Dry run tonight at 8:47 PM CT worked: 3 feeds × 30 items, 83 unique jobs in the last 24h, 23 excluded, 12 selected.
- Only one real run is on file, at 3:23 PM CT: `selections_20261020.csv` (12 picks) and `scored_all_20261020.csv` (81 rows). `scored_all_latest.csv` (the script's default output) has never been written, so no scheduled run has ever executed it.
- The pack (file 09, sections 2/2262) and LEAN_ORG both say the Upwork Coordinator's job scoring is selection only.

Routine check: "Upwork check (15m)" (`reply-check-hourly`, Mon–Sat every 15 min 6:12 AM–10:57 PM CT) is described in USAGE_GATE as **"Upwork messages only. Quiet if nothing new. Draft for Lorenzo."** No doc or log says it runs score_vollna.py. There are no Upwork Coordinator entries in decisions.jsonl after Sep 25. **Verdict: the 15m routine is not using the scorer.**

Exact gaps:
1. No SKILL/runbook for the Upwork Coordinator to run selection end to end (feeds, command, where to save, how to report). The rubric and script exist, but no skill file tells the seat to use them. `skills/upwork-followups.md` rule 3 points to an `upwork` skill for job selection that **doesn't exist** in `~/advero/skills/`.
2. No scheduled run. Important: each Vollna RSS feed returns only the newest 30 items. Tonight the "AI & Automation Systems" feed covered only **19:09–20:42 CT (about 1.5 hours)**. A daily or occasional run misses most AI & Automation jobs, so selection needs to run at least every 30–60 min (every 15 min is ideal) during Lorenzo's hours.
3. Picks aren't comparable over time. `selections_YYYYMMDD.csv` is overwritten per run and has `posted_ct` and `url` but **no run/flagged timestamp, no job_id column and no cumulative log**. Picks are also not deduped against earlier runs, so the same job gets re-flagged every run.
4. There's no file for Lorenzo's own picks and no compare step (bot vs Lorenzo: matched, bot-only, Lorenzo-only, with scores).
5. The "already applied" exclusion uses a static Oct 20 proposals export in ~/Downloads. Proposals sent after that won't be excluded unless the history is refreshed (the Upwork MCP `list_freelancer_proposals` read could do this).
6. Client signals are always "not in feed" (Vollna RSS carries no spend/hires/reviews), so rubric item 1 never applies. Every job is scored as a thin client. Fine for now, but say so in the comparison.
7. Leftover conflict: `upwork/proposal_drafts_20261020.md` (proposal drafts) and `VOLLNA_TEMPLATE_n8n_make.md` sit next to the selection files even though the rule is "never draft proposals". They should be archived or labeled so the Coordinator doesn't treat them as output.
8. The Upwork Coordinator profile still says "shortlist jobs ... draft chat replies", with no pointer to the rubric or script.

Ready for tomorrow's comparison if: a picks log exists with run_at_ct, job_id, url, title, posted_ct, feed, score, why (append-only, deduped on job_id), and Lorenzo's picks are captured in the same shape.

## 2. LinkedIn outreach

What exists:
- `~/advero/linkedin/SIMPLE_PLAN_20261020.md`: pilot ICP is US PPC/paid media/Google Ads agency owners, 1–50 staff. Blank connection requests in small daily batches, 4 posts a week, Looms only after about 200 connections, follow-ups on days 2/4/7, and every LinkedIn write is ask-first.
- `skills/linkedin-outreach.md`: connection rules are blank, about 10 a day on weekdays to start, ramping toward 40, **never more than 50 a day**, pending under 600, withdraw after 3 weeks. It assigns sending to **Lorenzo himself** ("Vetting each lead, sending connection requests: Lorenzo, from his own browser").
- Sales Nav trial started (li-224, ends 2026-11-20 13:17 CT). Saved searches: "PPC agencies US 1-50" accounts (id 2003648028), plus 5 niche lead searches: home services 2K+, legal 2K+, dental/medical 4K+, real estate 2.5K+, local SMB 12K+.
- List "PPC pilot 2026-10": **17 vetted leads** in `state/linkedin_tracker.csv` (18 rows including 1 account). request_date, accepted and reply are all empty.
- Prospecting stopped at 2:31 PM CT after "Bummer, things aren't loading" (possible soft rate limit). Bulk save (li-226) was held by the agent because the quote predates the card, so it may not have happened.
- `state/leads/2026-10-20_salesnav_high_fit_qe_lookup.csv`: 8 pilot leads checked for emails, 5 found (Sep 15 verify dates).

Permissions as of tonight:
- li-225 (8 blank requests) was **revoked** at 3:00 PM CT: 0 of 8 sent.
- The LinkedIn Outreach Manager profile hard rules still say **"Never send connection requests, messages or InMails"**. The agent held li-225 for that reason before the revoke. `06_systems_and_access.md` line 103 also says Grok sends none.

Exact gaps:
1. No standing authorization for agent-sent daily requests. That needs either (a) Lorenzo sending them himself (as the skill says), with the bot preparing a vetted daily list, or (b) a new dated Grok update + approval record covering N blank requests a day from a named list, plus a profile hard-rule change. Neither exists.
2. No daily routine. The only LinkedIn routine is "LinkedIn count", Sundays 10:00 CT, and even that has never written `state/linkedin_counts.jsonl` (the file doesn't exist).
3. Not enough vetted leads: 17 in the pilot list. At about 10 a day that's under 2 days of supply. Prospecting resumes "at slower pace" with no target or schedule.
4. No logging for sprint sheet columns H (requests sent) and I (replies). `sprint_sheet_sources.md` marks both "NO SOURCE YET". There's no daily read of the Sent invitations count, the tracker reply column is unused, and the agent is barred from opening Messaging, so replies can't be read by the bot at all under current rules.
5. Doc drift: LEAN_ORG still describes this seat as "Phase 0 ... never writes text or contacts prospects". PLAN.md vs SIMPLE_PLAN differ on niche (old 8 service industries vs PPC pilot).
6. Cross-channel dedupe: 5 pilot leads already have emails. Nothing stops the same person getting cold email and LinkedIn at once. The decision is Lorenzo's.

## 3. Communities

Cadence outline found (this is the "document from the months he ran"): Google Doc **"Maker School and Advero Operating Manual"**, https://docs.google.com/document/d/122qT6YwoK3drjZg4Z0sHrUheays-gqBKMQcO0OirD3Y/edit (partial snapshot on box: `~/advero/state/maker_school_audit/manual_snapshot_20261020_0850.json`; lesson notes in `state/maker_school_audit/m2_notes_batch0*.md`, `m3_notes_batch0*.md`, `m2_inventory.md`, `m3_inventory.md`). Quotes:
- Month 1 calendar: "The target is 15 posts over the next 26 days: five posts in each of three communities, approximately one every five days per community. It is not fifteen posts weekly or one post across all communities every five days."
- Month 1 rotation: "For the first community post, choose one community and rotate subsequent posts through the other two. Start with a recognizable problem and show a simple solution."
- Engagement: "Community engagement is five minutes in each of three communities, approximately fifteen minutes total."
- Month 1 Day 11: "Review the first six community posts, two per community, for 30–60 minutes and select three to five changes ... Day 11 has no new-post assignment; the review is the work."
- Month 1 post 7: "This is post seven and explicitly changes the cadence to every two days ... roughly three or four posts per seven-day period." Table: "From Day 13 | Community posts every two days". The month runs to "post 10, with five more before month-end" and ends with a "Final community post" on Day 30, plus retrospectives on Days 11 and about 19.
- Month 2: "Community posts on Days 2, 4 and 6", then "Day 9 ... second community post calendar ... The month plan is 14 posts, 5 in Community A, 5 in B and 4 in C ... keep posts short, step by step, aimed at non-technical readers, with no selling." Posts on Days 11, 13, 15, 17, 19, 22, 24, 26, 29. Summary: "Community posts run about every other day."
- Month 3 steady state: "a community post about twice a week". Posts on Days 3, 8, 12, 16, 20, 24, 30. Weekly: "two community posts".
- Template: Community Post Calendar sheet https://docs.google.com/spreadsheets/d/1H4ddQjoI56cNrnRMHZm2HNZHc0ESAMZnccI8raQN97o/edit (structure: problem, step-by-step solution, no pitch).
- Current Advero plan, `~/advero/state/communities/PLAYBOOK_20261020.md` (Google Doc 1p7zJHGhKtc1QzBTiO51aWSQdIlgnmf7I4S0CimKJBgQ): "15 posts across 3 communities over ~26 days (5 each), rotate niches. Structure problem -> practical steps -> screenshot/demo -> answer questions." "Daily: 5 min engagement per community + 5 min replies/tracker; posting days +30 min creation." Friday review. Agents: "joins + engagement drafts by Community Manager; membership answers, posts, comments, DMs all ask-first via hold card."

Recommended operating cadence (merging both): engage 5 min per community daily. Posts 1–6 rotate A/B/C about daily, with a review at post 6. From post 7, one post every 2 days rotating communities (about 3–4 a week), ending around 15 posts per 26 days, with a Friday review.

Community Manager today:
- Routines: the engagement digest (first test run Oct 20, 1:50 PM CT: `state/communities/engagement_digest_20261020.md`, drafts only) and the new nightly-sprint-row-writer (about 9 PM CT). The digest itself says "Daily is probably too often for these two alone" until pending groups are approved.
- Communities: approved are The Official BookingKoala Community (FB) and Construction Contractors Hub (Skool). Pending: ZenMaid MasterMind, Commercial Cleaners Forum (JSN), Scale My Cleaning Business, Agency Service Scaling Kings, Google Ads Skool. **There's no PPC or pest control community approved yet**, though the playbook wants one per niche.

Exact gaps:
1. No community skill file (`~/advero/skills/` has none). The profile still describes only "Maker School daily accountability". There's no written procedure for engagement, post drafting, the hold card or logging.
2. No post calendar (the 15 slots, which community, which problem, due date). No calendar file exists in state/communities.
3. No post-draft routine. Nothing produces a draft on post days for Lorenzo's approval.
4. No posted log, so sprint column J (Community Posts) has no source. The tracker the playbook asks for (conversation, DM permission, stage, next action) doesn't exist.
5. No routine checks the 5 pending joins (column K accuracy).
6. Niche coverage: the playbook niches are cleaning, PPC and pest control. The approved groups cover cleaning (via BookingKoala) and contractors, not PPC or pest control.
7. USAGE_GATE rule 6 ("Maker School: draft/reshape on Lorenzo's request only. No unsolicited Skool feed scrapes or engagement picks") conflicts with a daily digest. It should be updated to match Lorenzo's request.

## 4. Lead supply

Final leads location: **not on the box.** `find / -iname '*final*lead*'` (excluding /proc) found nothing. Per Lorenzo it's in a final-leads folder on his computer, machine 43321728-d9a1-4b7f-b428-290f6c2304b6. It was **not accessed**, so the count is unknown. Pulling it in needs Lorenzo's OK (CopyToBox).

What exists:
- `skills/quickenrich-lead-pulls.md`: browser-only QuickEnrich Contact Finder pulls (never the API). Sun–Thu nights, done by 05:00 CT, 80 per niche × 8 niches = 640 a night, log `state/quickenrich_pulls.csv`, upload to Drive "QuickEnrich drops". Claude handles dedupe, verification (MillionVerifier) and adding to the lead sheet. Lorenzo adds to Instantly.
- Lead Generation Specialist (id 9704b4a8): **NOT started.** Waiting on (1) Lorenzo logged in to the QuickEnrich web plan on the box, (2) a supervised first run (bookkeeping_tax, 100 rows), (3) the exact words "start lead pulls". `quickenrich_pulls.csv` doesn't exist, so no pulls have ever happened.
- Sales Nav to QuickEnrich proof of concept: `state/leads/2026-10-20_salesnav_high_fit_qe_lookup.csv`, 5 of 8 emails found (62%).
- `state/leads/staged_leads_*_2026-10-12.csv` (900 + 1,687 rows) are for the **old** Bookkeeping/Recruiting campaigns, not the live Launch campaigns.
- No lead sheet id is recorded in any state file I found. The skill and pack refer to "the lead sheet" without an id.

Gaps:
1. The skill's niches (bookkeeping, insurance, landscaping, pest, marketing agency, MSP, cleaning, recruiting) don't match the 3 live niches (PPC agencies, pest control, commercial cleaning). The supervised first run is set for bookkeeping_tax, which isn't a live niche.
2. The nightly number (80 per niche) is sized for 8 niches. Live need is about 250 new a day per niche (see runway).
3. QuickEnrich pool sizes on Oct 8: pest control 2,029, cleaning 913 then 2,921 (Facilities + bio), marketing agency 68,370. **Pest and cleaning pools are small and would run out within weeks at 250 a day**, before the 6-month cleaning recontact rule and dedupe.
4. No dedupe master. The final leads (already in campaigns) aren't on the box, and there's no suppression/dedupe file against Instantly's 8,124 Launch leads or the old campaigns.
5. No Sales Nav to QuickEnrich lookup procedure, so the 5 saved niche searches (about 22K+ leads) have no email path. The LinkedIn agent can't export lists, and the Lead Gen Specialist is barred from opening LinkedIn.
6. Verification gap noted by the Oct 20 audit: "7,146 of 8,124 Launch leads carry no verification field."

Runway estimate (Instantly snapshot 5:02 PM CT Oct 20; 6 active Launch campaigns, each daily_limit 250 and daily_max_leads 125, so 750 new + up to 750 follow-ups = 1,500 a day; 2-step sequence with step 2 three days later; sends Mon–Sat 07:00–19:00):
| Campaign pair | Leads | Contacted Day 1 | New left | Days at 250 new/day | Runs out (sending days from Wed 10/21) |
|---|---|---|---|---|---|
| PPC Agencies A+B | 4,391 | 250 | 4,141 | 16.6 | about Sat Nov 7 (tail Mon Nov 9) |
| Pest Control A+B | 1,789 | 250 | 1,539 | 6.2 | **Tue Oct 27** (tail Wed Oct 28) |
| Commercial Cleaning A+B | 1,944 | 250 | 1,694 | 6.8 | **Wed Oct 28** |
| Total | 8,124 | 750 | 7,374 | about 9.8 at 750/day | |
- From about Wed Oct 28, new-lead volume drops from 750 a day to 250 a day (PPC only) unless pest/cleaning leads are uploaded first.
- Keeping 750 new a day needs about **4,500 new leads a week** (Mon–Sat), including about 3,000 a week for pest + cleaning, landing in campaigns by **Mon Oct 26**.
- Caveats: assumes A and B lists in each niche are separate halves (2,195 vs 2,196 suggests a split). If they share leads, runway is about half. Bounces, unsubscribes and the 6-month cleaning cooldown reduce usable leads further.

---

## Recommendations (ranked by impact)
1. **Restart lead supply now (Lead Generation Specialist; Claude/COO for dedupe; Lorenzo uploads).** Get Lorenzo's "start lead pulls". Change the supervised first run to a live niche (pest_control). Retarget the skill to the live niches with a nightly number sized to about 250 a day per niche (Lorenzo sets the number). Ask Lorenzo for a new-niche decision, because the pest and cleaning QuickEnrich pools are small. Ask permission to copy the final-leads folder to the box as the dedupe master. Deadline: leads in campaigns by Mon Oct 26.
2. **Vollna selection routine plus comparable picks log (Upwork Coordinator).** Write `skills/upwork-selection.md`, pointing to the rubric and script. Run every 15–30 min, 6 AM–11 PM CT, appending to `upwork/picks_log.csv` (run_at_ct, job_id, url, title, posted_ct, feed, score, why), deduped on job_id. Report new picks only, no drafts. Add `upwork/lorenzo_picks_YYYYMMDD.csv` and a compare step for tomorrow. Refresh the applied-proposals history daily through the Upwork MCP (read only). Archive `proposal_drafts_20261020.md`.
3. **LinkedIn daily request flow (LinkedIn Outreach Manager).** Lorenzo picks one: (a) the bot preps a vetted daily list of 10, ramping toward 40 and never over 50, and Lorenzo clicks Connect; or (b) a dated Grok update + approval record allowing N blank requests a day from "PPC pilot 2026-10", plus the profile hard-rule change. In both cases, add a morning prospecting top-up so the list stays at least 3 days ahead, and an evening read-only Sent-invitations/pending count to `state/linkedin_daily.jsonl` for column H.
4. **Sprint sheet source logs (Revenue Operations, feeding the Community Manager's nightly row-writer).** Add `linkedin_daily.jsonl` (H requests, I replies; replies need either Lorenzo's self-report or permission to read LinkedIn Messaging), `communities/posts.jsonl` (J), `bookings.jsonl` built from handled.jsonl and calendar (L), and `won_deals.jsonl` (M). This ends the blank columns.
5. **Community posting system (Community Manager).** Write `skills/communities.md`. Build the 15-slot calendar from the cadence above (daily rotation for posts 1–6, then every 2 days, Friday review). Add a routine that drafts the due post the evening before for Lorenzo's approval (ask-first hold card, his words, no pitch, no invented results). Keep the engagement digest at once a day or every other day until more groups are approved. Add a daily read-only check of pending joins. Prioritize getting one PPC and one pest control community approved. Update USAGE_GATE rule 6.
6. **Sales Nav to email bridge (Lead Generation Specialist + LinkedIn Outreach Manager, with Lorenzo's yes).** Write the procedure: from the saved niche searches, record name/company/domain in a sheet, then do QuickEnrich web lookups to find emails, dedupe against final leads and Instantly, and route to the lead sheet. This unlocks the 22K+ saved-search leads for PPC and for any new niche. Include a cross-channel rule (LinkedIn pilot leads excluded from email, or not) for Lorenzo to decide.
7. **Weekly retros automated (Revenue Operations).** Following the Maker School weekly rhythm: a Friday cold email retro (reply and positive rates per campaign and step, winner/loser call drafted for Lorenzo), an Upwork retro (applications to replies, bot picks vs applied vs replies), and a community post retro. Read-only.
8. **Doc cleanup so bots don't refuse or misfire (COO).** Fix the missing `upwork` skill reference in upwork-followups.md. Update LEAN_ORG for the LinkedIn, Upwork and Community seats. Bring the `reply-check-hourly` description into line with what it actually does. Keep `/workspace/vollna_rss.txt` (the only feed list) in `~/advero/upwork/` too, since the script default points at /workspace.

Constraints respected: draft-first and ask-first for Upwork/email/LinkedIn writes; customer-facing copy only from approved docs; no campaign, lead list, inbox or billing changes without Lorenzo's yes.
