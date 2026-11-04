# Community Manager (running doc)
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Last updated: 2026-10-28 6:38 PM CT (10/28 6:15 PM review; backup .bak-20261028-review)

## 1. Position
- Title: Community Manager, Community branch manager, AdveroSolutions.
- Single job: run Lorenzo's community presence through two bots and route every post and comment to him for approval.
- Reports to: COO / Chief of Staff (732ca015-c7c3-412e-92f7-f9b2de73d050) only (Marketing head parked).
- Delegates to: Community Engagement Bot (b19d90a5-088a-4b71-8ad8-08e8d82730fa), Community Content Bot (f3b4967d-2135-410b-b3a0-6f3fbf58e8fb). Community Outreach bot planned behind a trigger.
- Room: Community team (d5214bab-7fb7-49ca-b6c6-5f9dda230744), owner.
- Mandate: joins from the vetted list, post calendar, approvals routing via COO, rule compliance, the daily review. Lorenzo approves the wording, and once he has, Community Manager posts it on his account.

## 2. What I do
- Community joins from COO's vetted list (~/advero/state/communities/vetted_20261020.csv), one at a time, staggered.
- Engagement digest: since 10/21 3:30 PM CT, Community Engagement Bot (reports to me) runs the Mon-Sat 8:30 AM / 3:30 PM read-only scans, keeps ~/advero/state/communities/conversation_tracker.csv, and sends me the top picks (max 5 per run). I relay them to Lorenzo in my chat.
- Community post calendar and next-day post drafts for Lorenzo's yes.
- Daily accountability numbers into the $20K 90 Day Sprint sheet.
- Maker School daily update support (title "Accountability Day N💸 ($20K 90 Day Sprint)").

Routines (all America/Chicago, flexible ±15 min):
| Name | Folder | Schedule | What it does | Delivers to |
|---|---|---|---|---|
| Community engagement digest (2x daily), PAUSED 10/21 12:10 CT, handed to Community Engagement Bot | community-engagement-digest-2x-daily | Mon-Sat ~8:30 AM and ~3:30 PM | Read-only scan of every joined group since the last digest; up to 5 picks per group with a draft comment; saves engagement_digest_<date>_<am/pm>.md | Lorenzo in my chat (top 5); nothing if empty |
| Evening community post draft, PAUSED 10/21 3:33 PM CT (drafts moved to Community Content Bot; joins/posts log moved to 6:15 review) | evening-community-post-draft | Daily ~6:00 PM | Read-only re-check of pending joins (updates joins.jsonl); verifies and logs Lorenzo's posts to posts_log.jsonl; drafts tomorrow's calendar post plus a 5 min/group engagement plan | Lorenzo in my chat for his yes; COO FYI only on a join status change |
| Evening community review | evening-community-review | Daily ~6:15 PM (0 early, 5 late) | Pending-join check, leak review (approved posts actually posted, flagged threads with no reply, call handoffs), QA of Content Bot drafts; writes review_<date>.md | No one (feeds 6:30 summary) |
| Daily community summary to COO | daily-community-summary-to-coo | Daily ~6:30 PM (0 early, 10 late) | One daily summary: what needs Lorenzo's approval (drafts in full), leaks, join changes; one line if nothing | COO |
| Nightly sprint row writer, PAUSED 10/21 3:31 PM CT (now Revenue Operations' nightly-sprint-row, Mon-Sat 9 PM; I keep joins.jsonl and posts_log.jsonl current for it) | nightly-sprint-row-writer | Daily ~9:00 PM | Writes today's row in the sprint sheet from real sources only; never overwrites, flags conflicts | COO (FYI); not Lorenzo |

## Org v3 changes (approved 2026-10-21)
- I manage 2 bots: the Engagement Bot (Mon to Sat 8:30 AM and 3:30 PM scans, about 6 picks a day, owns conversation_tracker.csv) and the Content Bot (daily 6:00 PM post and accountability drafts).
- Daily routine (CT): 6:15 PM review; 6:30 PM summary to COO (folded into next morning's 9:15 AM roll-up; same-evening post approvals go as one hold card via COO).
- The nightly 9 PM sprint row moves to Revenue Operations (../ROLLOUT_20261021.md). I keep writing joins.jsonl and posts_log.jsonl, which RevOps reads.
- Leak checks (6:15 PM): (1) pending joins rechecked; (2) drafts waiting on Lorenzo over 1 day; (3) Lorenzo's posts logged in posts_log.jsonl; (4) calendar slot missed; (5) tracker rows with no next action; (6) every draft checked for disclosure, no trade-business claim, no unapproved proof.
- Growth triggers: second Engagement bot when groups exceed 6 or picks exceed 15 a day for a week; Outreach bot when 5 or more DM-permission conversations in a week or the first lead asks for a call.
- Rules: no paid joins; never claim Lorenzo owns a trade business; always disclose Advero is an automation consultancy; approved proof only.

## 3. Processes
- Joins: open the group, read the rules (skip only on an explicit vendor/consultant ban or owners-only rule, but Lorenzo overrode skips on 10/20: no group gets skipped). Answer membership questions with the approved pattern: who we work with, then that we're looking for ways to help them better, tailored to the group. Never claim Lorenzo owns a trade business, no price, no pitch. Email used: [REDACTED] (Construction Contractors Hub opt-in: [REDACTED], Lorenzo's choice). Phone: none on file, so a group that requires one is blocked. Paid joins need Lorenzo's yes. Log each join to joins.jsonl and its answers to join_questions_20261020.md.
- Engagement digest: on FB, sort via ?sorting_setting=CHRONOLOGICAL and get permalinks by clicking timestamps; on Skool, ?s=newest. Lanes: lead response, missed calls, follow-up, booking/scheduling, no-shows, quote follow-up, reviews, CRM mess, tools/automation. Skip vendor pitches and anything already covered. Comments run 2-4 sentences, helpful, no pitch, no links, no price.
- Posts: follow post_calendar_month1.md (15 posts, Oct 21 to Nov 13, rotating A BookingKoala / B Construction Contractors Hub / C Agency Service Scaling Kings, never one group two days in a row). Proof only from approved_proof.md, word for word, and only with Lorenzo's okay (none is approved for communities yet). Lorenzo approves the wording, and once he has, Community Manager posts it on his account; I log every post in posts_log.jsonl after verifying it on the page.
- Sprint row: sources per column in ~/advero/state/sprint_sheet_sources.md. Upwork connector (proposals, replies), Instantly (sent, unique human replies), joins.jsonl (new communities), posts_log.jsonl (community posts), calendar/Gmail/Lorenzo's report (calls). Count by CT day. Blank when there's no source; Notes always blank.
- Browser work: one computerUse at a time on my desktop; cheap reads first (usage gate).

## 4. Rules and limits
- Posts and comments: Lorenzo approves the wording, and once he has, Community Manager posts it on his account. Nothing goes up without his approval of the wording, and I post it word for word. I still never like, react or DM. (Lorenzo 2026-11-02 12:54 PM CT: "the rule is that you're gonna post everything. I just give approval on wording and things like that, and then you post it for me.")
- posts_log.jsonl (from 2026-11-02 on): every new entry carries posted_by, either "community_manager" (posted by me on Lorenzo's account after his wording approval) or "lorenzo" (he posted it himself). Older entries have no posted_by and are left as they are.
- Never invent stats, names or proof.
- Voice for drafts: plain, sentence case, no em/en dashes, no exclamation marks, no emojis.
- Disclose Lorenzo as running Advero Solutions, an AI automation consultancy; never claim he owns a trade business.
- BookingKoala: Rule 3 bans self-promotion and competitor products; Rule 7 is for BookingKoala users only. Questions and plain tips only.
- Report to COO via SendToAgent (priority true when COO must act or is waiting; false for FYI). Lorenzo gets only real results in my chat (digests, post drafts); no pings or filler.
- Never write to retired sheets. Never overwrite a filled sheet cell without flagging it.
- Usage gate (~/advero/state/usage_gate.md): rule 6 was updated 10/20 to allow my digest and 6 PM routines.
- Keep this doc current (standing rule, Lorenzo 2026-10-21).

## 5. Decisions log (append only)
- 2026-10-23 8:05 AM CT: 8 AM pull found nothing new. All three 10/22 comments verified live (Brunson's posted text opens with 'man', flagged to COO). Julius replied to Lorenzo, follow-up drafted for review. Engagement Bot scan retimed to Mon-Sat 7:45/11:45/3:45 CT (COO approved); OPS_SCHEDULE conflict closed. COO's 8/12/4 pings and hourly replies pings come to me, and I route them to Engagement Bot.
- 2026-10-23 8:03 AM CT: Logged COO's report that Lorenzo approved (6:49-6:53 PM CT 10/22) and COO posted Brunson, Nasir (verify live) and the Julius reply; Blake, Rite Touch, Adegboyega, Melinda were denied, so they're set to not_posted. Day 3 Community Engagement = 3. New standing spec (Lorenzo 10/22 9 PM via COO, OPS_SCHEDULE.md): new-post pulls 8/12/4 Mon-Sat triggered by COO, drafts go back to COO with priority (author, exact words, link, draft); replies check hourly 8:30 AM-6:30 PM.
- 2026-10-22 6:32 PM CT (COO): Google Ads Skool added to Engagement Bot's read-only scans only (no calendar, no comments until Lorenzo says so). Day 3 New Communities = 1, passed to Revenue Operations. Федиш and Nottingham picks dropped. Engagement Bot drafting a Julius Ayal reply on clinic bookings/no-shows for Lorenzo's review, no price talk.
- 2026-10-22 9:32 AM CT (COO relaying Lorenzo, voice call 9:31 AM): stop lifted, resume all bots except the committee and go back to pre-stop work. Engagement Bot told to unpause its scans. Content Bot's Evening post draft stays paused under the 10/21 community posts hold until Lorenzo says go; COO told.
- 2026-10-21 6:38 PM CT (COO): Starting Day 3, COO owns the daily Maker School accountability post, drafted from Lorenzo's Loom. Content Bot stops drafting it, and my review no longer QAs accountability drafts. Any sprint sheet number that looks wrong gets flagged to COO.
- 2026-10-21 6:35 PM CT (COO): Lorenzo is holding off on community posts. Calendar slots 1 to 3 are parked; don't schedule, queue or call them ready until he says go. COO drafted Day 2 accountability from his Loom, and our draft is dropped. Comment drafts wait for his yes, and nothing gets posted or joined without it.
- 2026-10-21 4:15 PM CT: Revenue Operations added a "Community Engagement" column at L on the sprint Daily Log for comments Lorenzo posts. Calls Booked, $ Closed, $ Toward $20K and Notes moved to M, N, O and P. Go by header name, never by letter. The 6:15 review now logs every posted comment (type "comment", posted_at, source) in posts_log.jsonl and sets the tracker stage to posted, so the 9 PM count can include them. Drafts never count.
- 2026-10-21 4:09 PM CT: Lorenzo's rule: never use 'man' or any gendered address in drafts. Ana Rey and Julius Ayal finals (his own words) are in state/communities/drafts/comments_final_20261021.md for the 6:30 summary. Drafts only.
- 2026-10-21 4:08 PM CT: Profile updated. I report only to COO, and the org is now set by ~/advero/state/org/ORG_STRUCTURE.md (v3, approved 2026-10-21). The manual adds ~/advero/USAGE_GATE.md. Community is a core channel. All Community bots disclose Advero as an AI automation consultancy and use no price, links or pitch.
- 2026-10-21 4:05 PM CT: The Ana Rey and Julius Ayal comments were rewritten in Lorenzo's voice (v2). At Lorenzo's request, Julius was redone as v3, a clarifying-questions reply (paid ads and platform, or cold ads, or cold email; getting each clinic to 10k comes down to volume and testing). Both are in state/communities/drafts/comments_voice_v2_20261021.md and were sent to COO. They're drafts only.
- 2026-10-20 11:25 CT: I own community joins (COO), from the vetted list only.
- 2026-10-20 12:52 CT: Lorenzo said join BookingKoala (his wording), no group gets skipped, and answers following the approved pattern can be submitted without a separate yes.
- 2026-10-20 13:24 CT: Construction Contractors Hub opt-in email [REDACTED]; Home Cleaning Courses skipped (phone required, Lorenzo declined).
- 2026-10-20 15:40 CT: engagement digest moved from COO to me; runs Mon-Sat 2x daily.
- 2026-10-20 evening: 120 Day Conquest tracker retired. Now the $20K 90 Day Sprint (target corrected from $15K), Day 1 = 2026-10-20, Day 90 = 2027-01-17. Sheet columns simplified to big metrics only (no rates, no Connects).
- 2026-10-20 20:35 CT: Day 1 Calls Booked 2 (both from email replies), $ Closed 0, from Lorenzo's Day 1 video.
- 2026-10-20 20:49 CT: posting cadence starts Wed 10/21 (playbook: 15 posts in about 26 days, 3 groups); no proof unless Lorenzo okays it; posts log is posts_log.jsonl.
- 2026-10-21 08:40 CT: Agency Service Scaling Kings approved and became calendar group C.
- 2026-10-21 10:56 CT: standing rule, every bot keeps a running role doc.
- 2026-10-21 15:28 CT (Lorenzo via COO): engagement scans move to 12:00 PM and 4:00 PM CT Mon-Sat (Engagement Bot). Community Content Bot runs the 6:00 PM post and accountability drafts. I run the 6:15 PM review and the 6:30 PM summary to COO. Everything goes to COO for approval; I never message Lorenzo directly.
- 2026-10-21 12:10 CT: I handed the engagement scans to Community Engagement Bot (one owner per task, usage gate rule 2); my digest routine is paused; picks come to me, then go to Lorenzo; it doesn't write joins.jsonl.
- 2026-10-21 10:57 CT: standing rule, cross-reference shared client context (~/advero/state/clients/) across all bots; routines updated to follow it.

## 6. Ongoing work
- 10/23 6:15 review: no new Lorenzo comments or posts (Day 4 count 0). Waiting on his yes: Ahmed Mohamed comment, Julius follow-up, Maximilian Lesek reply. New: Nick Saraev 21h question on the Day 3 post (cold email positive reply rates) unanswered and not drafted; needs Lorenzo's real numbers. Kunj Patel Kings post (~4:25 PM) for the next pull.
- 10/22 6:15 review: no new Lorenzo comments or posts; 8 BK picks still at comment_drafted (4 are 2 to 3 days old); Julius Ayal reply still open; flagged Day 3 New Communities (Google Ads Skool) to COO.
- 10/21 6:15 review: first comments logged (Ana Rey BK, Julius Ayal Kings), both verified on page; Julius replied 3 times, Lorenzo's reply open. Slot 1 still not posted. engagement_time_log.csv created. Tracker stages use the README names (posted_by_lorenzo, member_replied), with posted date in next_action since the tracker has no posted_at column.
- Waiting on Lorenzo: yes or edits on the slot 1 BookingKoala post (Wed 10/21) and the 10/21 AM digest picks.
- Google Ads Skool (Skool, https://www.skool.com/google-ads-skool) approved, logged 10/22 6:20 PM CT. Not in the calendar or Engagement Bot scans yet; adding it is a COO / Lorenzo call (off-niche ads community). No pending joins left. Scale My Cleaning Business went not_pending 10/21 3:35 PM CT (likely declined, not re-requested). Rechecked nightly.
- Likely declined, not re-requested (COO/Lorenzo call): ZenMaid MasterMind, Commercial Cleaners Forum.
- Open for COO on Mon 10/26: no pest control group approved yet (playbook niche gap).
- Retired accountability sheet still needs its file rename to "(Retired)": the browser account ([REDACTED]) has no access, so it needs sharing or a manual rename.
- Day 1 sheet row: H, I, J show 0, which I didn't write; flagged to COO.

- Community Split Test Bot (daaaaa93-0e01-43a4-8cbb-3008bdd113f0) approved in my branch as a draft (role doc split-test-bots.md). Don't give it work or message it until COO relays Lorenzo's go. Adding it to the Community team room failed on 10/21 at 3:11 PM CT (channel not found, since I'm not a member); reported to COO.

- Teammate routines (10/21): Engagement Bot community-engagement-scan-2x-daily runs 0 12,16 * * 1-6 CT. Content Bot 'Evening community + accountability drafts' runs daily ~5:45 PM CT and writes drafts/post_<yyyymmdd>_slot<NN>.md and drafts/accountability_day<N>_<yyyymmdd>.md. Open: the 6 PM accountability numbers are mostly blank because the sprint row is written at 9 PM, flagged to COO. Stale Day 2 scaffold at ~/advero/state/community/drafts/ (wrong folder).

- Asked RevOps to cover Sunday sprint rows (their routine is Mon-Sat).

- Dashboard: I keep ~/advero/state/dashboard/tasks/community.json (whole branch, overwritten each time). It's refreshed by the 6:15 review and whenever a task changes state (COO/Lorenzo, 10/21 3:36 PM CT).
- Engagement time log: ~/advero/state/communities/engagement_time_log.csv, written by the 6:15 review. Minutes come only from what Lorenzo reports.

## 7. Files and state
- Sprint sheet: 1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0, tab Daily Log (gid 22421784), row = Day + 1. Columns: Date, Day, Logged, Upwork Proposals, Upwork Replies, Cold Emails Sent, Email Replies, LinkedIn Requests Sent, LinkedIn Replies, Community Posts, New Communities, Calls Booked, $ Closed, $ Toward $20K, Notes. Backup tab "Daily Log backup 2026-10-20".
- Retired, never write: 1fyuBNwSq8HbUACr5_svYH-E-uOp_nj-q5O_3MOWonNY (old Conquest sheet); 1GuJBW_FSZJsJZ9gmN37EmTGo65DH695BtwhFkBXWDj0 (old wide Daily Metrics).
- State: ~/advero/state/accountability_sheet.json, daily_metrics.json, sprint_sheet_sources.md, handoffs/<yyyymmdd>_accountability.md.
- Communities: ~/advero/state/communities/ holds vetted_20261020.csv, PLAYBOOK_20261020.md, joins.jsonl, join_questions_20261020.md, engagement_digest_*.md, post_calendar_month1.md/.csv, drafts/, posts_log.jsonl (+ posts_log_README.md), approved_proof.md.
- Maker School audit (done 10/20): ~/advero/state/maker_school_audit/final_deliverables.md; tracker sheet 1Laj4Afrmx_zQaF_bL-UeilIRxNINqQvvSoIggn1Pkm8; Operating Manual Doc 122qT6YwoK3drjZg4Z0sHrUheays-gqBKMQcO0OirD3Y.
- Manuals: ~/advero/GROK_ONBOARDING_PACK.md, ~/advero/state/org/LEAN_ORG.md, ~/advero/USAGE_GATE.md.

## 8. Handoff notes
- Joined groups: The Official BookingKoala Community (FB, https://www.facebook.com/groups/bookingkoala), Construction Contractors Hub (Skool, https://www.skool.com/construction-contractors), Agency Service Scaling Kings (Skool, https://www.skool.com/kings).
- The box browser is signed in to FB and Skool as Lorenzo, and to Google as [REDACTED] (which can't open the sprint sheets; the Sheets connector can).
- FB permalinks need a timestamp click, and its page text is noisy. Skool is clean.
- Low post volume (about 7 posts in 48h across the first two groups), so the digest is often thin.
- Everything I send Lorenzo is a draft; nothing goes out without him posting it.

## 9. Shared context
- coo.md (if present): my manager; joins vetting, usage gate, approvals routing.
- linkedin-content-manager.md: keeps my community posts and Lorenzo's LinkedIn content consistent in voice and topics.
- copywriter.md: approved proof lines and voice rules (approved_proof.md comes from cold-email copy).
- upwork-coordinator.md, deliverability-specialist.md, linkedin-outreach-manager.md, lead-generation-specialist.md: sources for sprint sheet columns D to I (Upwork, cold email, LinkedIn).
- community-engagement-bot.md (being written): owns the engagement scans and conversation_tracker.csv; reports to me.
- revenue-operations.md: QA of sprint numbers, calls booked and $ closed.
- Client/lead rule: before acting on any lead or client (e.g. a community member who becomes a lead, a post or comment that names one, calls booked), check ~/advero/state/clients/INDEX.csv and the client file; afterwards append a dated Log line ("YYYY-MM-DD HH:MM CT | community-manager | <channel> | what happened") and update INDEX.csv under flock ~/advero/state/clients/.lock.

## Global rules
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.

## Audit changes 2026-10-22 9:30 PM CT (COO)
- One batch card a day: all comment and reply drafts go to COO in the 6:30 PM summary as one card (each draft with its post, Approve/Deny/own words). Time-sensitive replies to people who already engaged may go as their own card, still through COO with priority.
- Drafts older than 48 hours without a yes are dropped and logged as expired (the post has gone stale).
- Scan times per OPS_SCHEDULE.md (Lorenzo 9 PM): 8 AM, 12 PM and 4 PM CT Mon-Sat, plus an hourly reply and DM check 8:30 AM to 6:30 PM. The routine change is with COO.

- 2026-10-24 4:38 PM CT: Second time a script expanding Brunson replies left FB reply boxes open (nothing typed or posted; verified count 23, no draft text). New EB rule: no expanding Brunson replies, check by notifications and count only; single manual clicks elsewhere; close any opened box with Escape and report.

- 2026-10-25 10:30 PM CT: COO asked for a proactive week plan (Lorenzo: "make things shake"). Plan at ~/advero/state/communities/week_plan_20261026.md, Monday drafts drafts/post_20261026_{1,2,3}.md sent to COO. Targets: 3 comments/day (max 5) as one 6:30 PM batch card, 6 original posts this week. Keep BookingKoala, Kings, Google Ads Skool (needs his go); deprioritize Contractors Hub (cut if no owner replies by 11/6). Posts hold still in force until his exact words lift it. Julius/Ahmed v2/Maximilian Day 3 closed, Carol dropped (COO 10/25).

- 2026-10-26 6:27 PM CT review: no Lorenzo comments seen (Day 7 Community Engagement 0). 7 comment/reply drafts open for tonight's batch card (Amanda Miller, Harvey v2, Akosua v2, Josh Turner, Nick Day 5+6, Aaron T, Ahmed K). Expired: Nick Day 4, Nasir thanks, Alex Vega; Maximilian Day 4 denied. Lorenzo posted his own "Outreach HELP" post in Maker School ~4:41 PM CT; not logged in posts_log.jsonl, COO asked whether it counts. Posts hold still in force.

- 2026-10-27 12:36 PM CT: Maker School is now secondary (Lorenzo 12:33 PM CT via COO: "not engaging inside of Maker School as a primary"). Primary: Kings, Google Ads Skool, BookingKoala, Contractors Hub, buyer FB groups. Maker School new-post comments only when a pull has nothing else, max 1 per pull. Leon Smith and Ivan Guzman drafts closed, Lorenzo engaged them himself.

- 2026-10-27 12:42 PM CT: Took over two routines from COO (Lorenzo yes in COO chat 12:37 PM CT: "Yes, offload those routines and make the Reminders bot"). "Community pull 8, 12, 4" (Mon to Sat 8 AM, 12 PM, 4 PM CT, folder community-pull-8-12-4) and "Community replies to people who messaged us" (hourly :30, 8:30 AM to 6:30 PM CT Mon to Sat, folder community-replies-to-people-who-messaged-us). Both route browser work to Engagement Bot one job at a time and send drafts to COO with priority.

- 2026-10-27 6:30 PM CT review: Day 8 Community Engagement 2 (Lorenzo's own comments on Leon Smith ~12:32 PM CT and Ivan Guzman ~12:39 PM CT, verified live by Engagement Bot, already in posts_log.jsonl; tracker rows set to posted). No yes or no recorded on the 10/26 batch card, so those drafts expire 10/28. Flagged to COO: sprint Day 7 Community Engagement shows 3 vs our 0. Kings post draft post_20261027_1.md waits on the posts hold.
- 2026-10-27 safety lessons (safety_incidents_20261027.md): (1) 11:46 AM CT the 11:30 replies check and the 11:45 scan drove the same browser, so with both routines now mine, a pull must queue behind a running replies check (one browser job at a time on Engagement Bot's desktop). (2) 5:47 PM CT the Skool helper skipped the about-page hop and pressed Enter without screenshotting the typed URL, and comment boxes auto-focused (nothing landed). Engagement Bot now runs short split jobs with step-by-step wording. Any auto-focused comment box gets closed with Escape or X and reported.

- 2026-10-27 10:25 PM CT: Ops cleanup (Lorenzo 10:13 PM CT via COO). Deleted paused routines community-engagement-digest-2x-daily, evening-community-post-draft, nightly-sprint-row-writer. Replies check now fully silent when nothing new; no notes to Lorenzo in my chat, everything goes via COO. Asked EB to pause its own timed scan (pull 8/12/4 is the only scan trigger) and Content Bot to delete its paused evening drafts routine. EB typed-navigation rule: Ctrl+L method (Escape + blank click on Skool, screenshot highlighted URL, type, screenshot before Enter, stop if a comment box has a cursor). Ivan Day 9 stray "h" cleared, nothing posted.

- 2026-10-28 8:22 AM CT: COMMS rule (Lorenzo 10:57 PM CT 10-27, ~/advero/state/org/COMMS_RULES.md) applied across the branch: priority=true only for member replies, drafts awaiting Lorenzo, blockers or STOPs; status and FYI go to files or priority=false; handoffs are batched. Pull routine updated: "nothing worth engaging" and late notes go to COO priority=false, and the Maker School fallback pass runs in the same job. EB timed scan community-engagement-scan-2x-daily is paused.

- 2026-10-28 6:38 PM CT review (no browser, local records only): Day 9 Community Engagement 0 seen through Engagement Bot's 3:46 PM CT check; no 4 PM pull digest or 4:30/5:30 check notes found. No yes or no recorded on the 10/27 card. Expired today under 48h: Amanda, Harvey v2, Akosua v2, Nick Day 5+6, Josh Turner, Aaron T, Ahmed K, Tre Heart (tracker rows still comment_drafted, COO to confirm close). Kyle Weese and Saad Qamar fallback drafts superseded by Tre Heart, recommend drop. Kings slot 6 draft post_20261028_1.md waits on the posts hold. Sprint Day 8 matches (2/0/0); Day 7 Community Engagement 3 vs our 0 still open for COO.

- 2026-10-29 6:05 PM CT: Free community ranking and join plan written (communities/free_community_ranking_20261029.csv, free_community_plan_20261029.md). Lorenzo approved autonomous free joins via COO (5:57 PM), vendor join for r/PestControlIndustry, and a new free Advero Reddit account on his business email (vault login "reddit.com (Advero)"). Joining only, no posts or comments without Lorenzo. Weekly re-filter drops dead communities.

- 2026-10-29 6:30 PM CT review (no browser, local records to Engagement Bot's 5:47 PM CT check): Day 10 Community Engagement 0 seen. Expired today: Arun Lvlup, Living N Luxuries, Jenya v2, Michael v2, Andrew v2, Maximilian Outreach HELP and Day 5+6, Nick Outreach HELP, Leon reply. Lorenzo's 6 PM rule (no replies inside Maker School) dropped the own-post reply drafts; recommend closing the Nick Day 3 question too. Today's Maker School fallback drafts (Grant, Petur, Nikhil) all superseded, recommend drop; COO still to confirm whether fallback comments stop too. Kings post_20261029_1.md waits on the posts hold. Sprint Day 9 matches (CE 0). 10/28 4 PM pull never reached Engagement Bot (NOT_RUN note).

- 2026-10-30 6:25 PM CT review (no browser, local records to Engagement Bot's 5:43 PM CT check): Day 11 Community Engagement 0 seen. Live drafts waiting on Lorenzo: BrightWave and Alex Jeet (BookingKoala), Nicholas Espartero (Google Ads Skool), all expire 11/1. Kyle and Saad expired today; Grant, Petur, Nikhil expire 10/31 (recommend drop). Lorenzo's own Maker School post "Is 15 min enough for $2.5K to $10K deals?" logged to posts_log.jsonl (time between 10/29 5:47 PM and 10/30 7:37 AM CT; sprint Day 10 Community Posts may need 1, COO to ask). Reddit signup and r/PestControlIndustry join had no record of running at the 10/30 8 AM pull; still outstanding. Org change (COO 2:35 PM CT, Lorenzo: "Cut the parked, committee and split-test bots"): Community Split Test Bot cut from the org chart, split-test stats fold into Community Manager; dropped from my dashboard.

- 2026-10-31 6:22 PM CT review (no browser, local records to Engagement Bot's 5:43 PM CT check): Day 12 Community Engagement 0 seen. Live drafts waiting on Lorenzo: Angel Juarez (BookingKoala, new today, expires 11/2 ~12:05 PM CT), BrightWave and Alex Jeet (BookingKoala), Nicholas Espartero (Google Ads Skool), the last three expire 11/1. Kyle, Saad, Grant, Petur, Nikhil closed per COO. Reddit signup and r/PestControlIndustry join still did not run at the 10/31 8 AM pull; likely needs Lorenzo's in-chat sign-in. Week plan 10/26 ended today (2 Lorenzo comments all week, 0 slot posts under the hold); COO to say whether a new week plan starts 11/2.
- 2026-11-01 6:29 PM CT review (Sunday, live read-only thread check): Angel Juarez BookingKoala post now unavailable, draft withdrawn; BrightWave and Nicholas Espartero drafts expired today with no yes. No live comment drafts left. 0 Lorenzo comments seen. Julius Ayal still unanswered (~9.5 days). Sprint Day 12 matches (CE 0). Week plan 11/2 to 11/7 still a draft waiting on COO and Lorenzo's answers. Posts hold still in force.
- 2026-11-02 6:20 PM CT review (live read-only browser check ~6:17 PM CT): all 5 comments posted today verified visible, 0 replies; Day 14 Community Engagement 5 matches sheet. Joins: The Modern Operator, All Contractor U, Restoration Referral System approved; 14 Skool pending; Commercial Cleaners Forum (FB) declined/lapsed. Live drafts waiting on Lorenzo: Joshua Hollandsworth, Alex Vega (CallRail line fix); Alex Jeet x2 superseded. Julius Ayal ~11 days, recommend close. COO flags: New Communities 27, Community Posts 1, Day 7, 15 min post. Posts hold still in force.

## 2026-11-02 10:29 AM CT: max joins, tracker, Saturday prune (Lorenzo, via COO)
- Week plan communities/week_plan_20261102.md is APPROVED and committed.
- Daily max joins Mon to Sat across Facebook, Skool and Reddit: free and $0 Standard tiers only, join only, no fake phone numbers, skip questions we can't answer honestly, bot email from COO for join forms. Log in joins.jsonl and activity_tracker.csv.
- I keep communities/activity_tracker.csv current (posts per day, comments, recency, score). Real reads only, blanks when unmeasured.
- Every Saturday I prune: leave the bottom performers, keep the best, report to COO.
- Morning push at 7 AM CT Mon to Sat, done before 9 AM CT: joins, engagement scrape, engage list for Lorenzo, top 3 to 5 post drafts to COO.
- Sign-in: never ask Lorenzo to sign in when a vault login exists; fill it myself. Escalate only phone 2FA or a rejected login. Passed to Engagement Bot.
- Posts and comments: Lorenzo approves the wording, and once he has, Community Manager posts it on his account (updated 2026-11-02 12:55 PM CT).
- 2026-11-03 6:30 PM CT review (local records, no browser): 0 comments posted (Day 15 CE 0). Joins approved per Skool notifications: HVAC Ads Lab, Contractor Excellence, Roofing 2.0 (slug unmatched); 8 Reddit and 3 FB joins at 7 AM push. Live drafts: Josh Turner CCH reply (priority), Brave_Lie8749, Cedar-and-Sky, Ok-Shift1044, plus Joshua Hollandsworth and Alex Vega (expire 11/4). Posts hold still in force; 9 post drafts parked.
