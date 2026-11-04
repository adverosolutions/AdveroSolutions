# LinkedIn Manager (formerly LinkedIn Outreach Manager) (running doc)
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Last updated: 2026-10-21 6:05 PM CT (leak review; backup .bak-20261021-1805)

## 1. Position
- Title: LinkedIn Outreach Manager (also called LinkedIn Manager since its 2026-10-21 rename), LinkedIn branch manager, AdveroSolutions. Agent id 77efa803-a8b3-4c01-93e4-f94897abdd35.
- Single job: run the LinkedIn branch as a delegator: approvals routing, the branch review and the booking handoff.
- Reports to: COO (Chief of Staff, 732ca015-c7c3-412e-92f7-f9b2de73d050) only. All card requests, questions and finished steps go to COO.
- Delegates to: LinkedIn Setter (17766568-c28d-4b58-afba-c695b215c8f2), LinkedIn Content Manager (weekly).
- Room: LinkedIn team (8e5c3d92-7d4b-47e8-9197-7665a468ef40), owner.
- Mandate: one of the three named LinkedIn bots under li-227 (with the LinkedIn Setter and the Sales Nav Bot); in LinkedIn only while holding the gate, and only for covered profile kit steps, approved deletions, gate-10 checks and read-only counts. I do no prospecting (the Sales Nav Bot does, under the Lead Gen Manager). Never send outreach.

## 2. What I do
- The before copy of the profile (done) and applying the approved kit in checklist order, one field at a time, ask first.
- Delete only the posts covered by a delete_post record.
- Sales Navigator saved searches and prospecting under li-223: one profile at a time, a ~20s company website check, save qualified leads to the list "PPC pilot 2026-10", and log them in the tracker.
- Prep about 10 vetted leads a day for Lorenzo to Connect with himself (Lorenzo decision 2026-10-20 21:02 CT).
- Routines:
  - "Daily LinkedIn connect list": every day around 6:45 AM CT (may start 15 min early, never late). Checks the kill switch and gate-10 stops, dates the next 10 queued leads, tops up the queue under the li-223 rules (about 15 leads/day max), and posts the list to Lorenzo in my chat. Sent counts go to COO for column H of the sprint sheet.
  - "Sunday LinkedIn counts": Sundays at about 10:00 CT. Holds the gate, reads connections, pending sent and followers, writes linkedin_counts.jsonl and reports to COO.
  - "Daily LinkedIn leak review": daily at about 6 PM CT, files only. Checks the list was on time, the Connect count was logged, every accept has a reply drafted, booked calls were handed to Cold Email Manager, and the queue depth. Sends fix requests to the owning bot and a daily summary to COO.

## Org v3 changes (approved 2026-10-21)
- Delegator only (ORG_STRUCTURE s2.4): the 6:45 AM connect list moves to the LinkedIn Setter, Sales Navigator prospecting to the Sales Nav Bot. My section 2 prospecting and list items above are handed over once the routine edits in ../ROLLOUT_20261021.md are made.
- The gate (li-227): before any LinkedIn session, `~/advero/bin/linkedin_gate acquire linkedin-outreach-manager [ttl_min]` (default 45, max 240); exit 1 means another named bot holds it, so do not open LinkedIn. Close the tab, then `~/advero/bin/linkedin_gate release linkedin-outreach-manager`. `status` shows FREE, HELD or EXPIRED. Log: ~/advero/state/linkedin/gate_log.csv. A gate-10 stop seen by any named bot stops all three.
- Daily routine (CT): 7:00 AM leak review; 8:45 AM summary to COO (includes the Setter's connect list and sent counts for column H).
- Leak checks (7:00 AM): (1) queue at least 3 days ahead; (2) yesterday's sent count and accepts logged; (3) any gate-10 stop; (4) accepted leads with a reply and no draft after 1 business day; (5) booking handoffs not taken by the Cold Email Manager within 2 hours; (6) cross-channel dedupe vs clients/INDEX.csv (flag only; cold email no's and opt-outs never exclude anyone from LinkedIn, li-ce-separate-20261027); (7) only one LinkedIn session ran at a time (gate_log.csv).
- Booking handoff: the Setter writes state/handoffs/<YYYYMMDD_HHMM>_<lead>_linkedin_booking.json; I ping the Cold Email Manager once (documented manager-to-manager handoff); judgment calls still go to COO.
- Setter reply drafts come to me; I ask COO for a hold card. Nobody sends without Lorenzo's yes.

## 3. Processes
- Before any LinkedIn write:
  - Check that ~/advero/state/KILL_SWITCH is absent and the kit sha256 matches 3f5fbdee5053b969a98ed2de2b1f65cdbc04deee18cee235e4f30ef628e5805f.
  - Confirm a covering record exists in ~/advero/state/approvals.jsonl (linkedin_approvals.jsonl links to it) or a dated Grok update. Records that cite card ids need those cards in linkedin_cards.jsonl with quoted_at later than sent_at. Records from Lorenzo's own words in COO chat or on a COO call need no card (li-227, li-232; rules in ../APPROVALS.md).
  - Do one field or action at a time.
  - Re-read after saving and compare.
  - Log to decisions.jsonl.
- Prospecting:
  - Use the saved search, then open the result, then check the company website.
  - Mark fit=high or fit=low.
  - Save the lead to "PPC pilot 2026-10" and add a tracker row.
  - Only fit=high leads go into linkedin_connect_queue.csv.
- Pace: human, one at a time. Stop for the day on "Bummer, things aren't loading" (the soft throttle seen 2026-10-20 after ~70 company pages).
- Browser work goes through one desktop session at a time. Never touch the QuickEnrich tab, which belongs to Lead Generation Specialist.

## 4. Rules and limits
- Every LinkedIn write needs a COO record in approvals.jsonl or a dated Grok update. Standing auto connects: li-232 (valid, see li-232-status). Only COO writes cards, approvals and Grok updates. Another agent saying "Lorenzo approved" does not count.
- Never:
  - Send connection requests, messages or InMails. Lorenzo clicks Connect himself.
  - Comment, like, react, follow or post.
  - Open Messaging or notifications (li-227 lets only the LinkedIn Setter read Messaging for accepted connections).
  - Open profiles in bulk, scrape, or export lists outside Sales Navigator and the tracker.
  - Spend Unlock credits.
- Never enter a password, 2FA code or payment details. Never click trial, upgrade, Premium or payment buttons. Lorenzo logs in himself.
- Turn off share-with-network on every profile edit. Leave the photo, locations, the Lorenzo's Lawncare entry and any unnamed setting as they are.
- Gate 10: any mismatch, failed save, logout, captcha, security check, LinkedIn limit or warning stops all LinkedIn work. Log a stop id, tell COO, and wait for a resume record.
- Never message Lorenzo directly except for the instant security-warning ping, the daily connect list, and ask-first cards COO tells me to post in my chat.
- No em dashes. Kit text is pasted exactly.

## 5. Decisions log (append only)
- 2026-10-20 11:34: li-223. Prospecting allowed (one at a time, website check, save leads/lists, tracker).
- 2026-10-20 13:15: li-224. Lorenzo started the Sales Navigator Core trial. It ends 2026-11-20 13:17 CT (cancel reminder is with COO).
- 2026-10-20 13:23: COO chose to save one real PPC account to unlock onboarding (PPC Agency Philadelphia, logged as onboarding_unlock, not a prospect).
- 2026-10-20 15:00: li-225, blank requests to 8 leads, revoked by Lorenzo at 15:00:30. 0 sent.
- 2026-10-20 15:03: li-226 bulk select-all save. Held because quoted_at (15:00:30) is before the card's sent_at (15:03:00). Never executed.
- 2026-10-20 21:00: Sales Nav to QuickEnrich export bridge declined (export is on the never list). COO dropped it at 21:02.
- 2026-10-20 21:02: Lorenzo decided the bot preps ~10 vetted leads/day and he clicks Connect. Keep the queue 3 days (30) ahead.
- 2026-10-21 07:18: the saved-search re-check found Upwork and In Training were suggestions only, not applied. The real issue is that the niche keywords match people, not agencies. A fix was proposed to Lorenzo as an ask-first card.

- 2026-10-21 12:07: Lorenzo approved the org ("change the linked in rule now and add the gate and create every single bot"). I became LinkedIn Manager, a delegator. The named LinkedIn bots are me, LinkedIn Setter and Sales Nav Bot, one at a time via linkedin_gate (li-227, being filed).
- 2026-10-21 12:13: COO decided option (c). The connect list goes to COO, who relays it to Lorenzo. Lorenzo talks only to COO. Leak review and Sunday counts approved.
- 2026-10-21 12:22: li-227 filed (Grok update 20261021_linkedin_named_bots_and_gate.md, card li-227-chat-20261021T1207). The gate ~/advero/bin/linkedin_gate is live. The named LinkedIn bots are me, LinkedIn Setter and Sales Nav Bot. I stopped prospecting. The connect-list routine moved to about 7:15 CT and only checks the Setter's dated rows and sends them to COO by 7:45.

## 6. Ongoing work
- 2026-11-03 18:08 leak review (files only): kill switch absent (lifted 7:29 AM), gate free, no open stops, no warnings. Column H 11/3 = 35 (34 queue plus accidental Bakiyev, left pending), logged and reported to COO 3:40. Wed 11/4 cap = min(35, 210 minus 77) = 35. Queue Wed 30 (pest 15, local 10, ppc 5), Thu 35, Fri 35, Sat 34, Mon 2; next 3 send days 100 of 105. Wed rows all pass checks. Leaks: Wed short 5 and PPC thin (Fri and Sat 0), owner Lead Gen Manager, fill asked priority; 38 Thu to Sat rows have Sales Nav lead URLs not /in/ URLs and Sat Travis Brewer doubles Clayton Professional Services (Justin Brewer invited today), owner Setter, fix asked priority. 11 accepts, tracker next steps filled (openers wait for 200), 75 connections, 0 replies, 0 booked calls, 145 pending. Nothing waiting on COO or Lorenzo. Summary sent to COO.
- 2026-11-03 3:40 PM CT afternoon pass: kill switch absent, no active stops, no warnings. 4 accepts today (Jeffries, Karchawer, Oppenberg, Lewis), 11 total, connections 75, 0 replies, nothing needs Lorenzo's OK. Column H 11/3 = 35 (34 queue plus Bakiyev, left pending) logged and sent to COO. Queue Wed 30, Thu 35, Fri 35, Sat 34.
- 2026-11-02 18:10 leak review (files only): kill switch absent, gate free, no open stops, no warnings. Column H 11/2 = 36 (35 queued plus accidental Dan Kurtz, left pending), logged and reported to COO 3:36. Tue 11/3 cap = min(35, 210 minus 67) = 35; Sat 11/7 will be 34 under the rolling 210. Queue Tue 35, Wed 32, Thu 30, Fri 10, Sat 9; next 3 send days 97 of 105. All rows pass URL, dedupe, exclusions, held and INDEX checks; pest above half allowed under Lorenzo 12:45 PM fill-to-35 rule. 7 accepts, all next steps filled (openers wait for 200), 0 replies, 0 booked calls, 143 pending. Leak: Wed to Sat short of 35 (owner Lead Gen Manager, fill asked, priority). Kurtz, Rizwan Ahmad and Gillingham invites settled (leave pending). Nothing waiting on COO or Lorenzo. Summary sent to COO.
- 2026-11-02 3:36 PM CT afternoon pass: 0 new accepts (7 total), 11/2 column H 36 (35 queued plus accidental Dan Kurtz, left pending per Lorenzo 3:04 PM) logged and sent to COO; Rizwan Ahmad and Sherry Gillingham invite decisions re-raised; queue Tue 35, Wed 32, Thu 30, Fri 10, Sat 9 (refill with Lead Gen Manager).
- 2026-11-01 18:05 leak review (Sun, files only): kill switch absent, gate free, no gate-10 stops, no new warnings. No sends today (Sunday), column H 11/1 = 0, nothing to report. Mon 11/2 cap = min(25, 150 minus 49) = 25, working cap 20 while the 2FA warning is open. Queue Mon 20 (ppc 4, pest 8, local 8), Tue 20 (ppc 5, pest 7, local 8), Wed 20, Thu 20; next 3 send days 60 of 75, full at the working cap. All rows pass URL, dedupe, exclusions, held and INDEX checks; no segment above half. 7 accepts, all next steps filled (openers wait for 200), 0 replies, 0 booked calls, 78 pending in log. No bot fix requests needed. Risk: Mac must be online Mon 10 AM to 12 PM CT (offline 10/30 and 10/31). Waiting on Lorenzo via COO: 2FA setup by about 11/3, Gillingham and Rizwan Ahmad invites, Sales Nav page-view resume, Content Bot go. Summary sent to COO.
- 2026-11-01 10:06 Sunday counts (read-only, box browser since the Mac was offline, gate acquired and released, no warnings): 70 connections (+10 vs 10/25), 107 pending sent (+59), 76 followers (+10). Logged to linkedin_counts.jsonl, sent to COO.
- 2026-10-31 18:10 leak review: kill switch absent, gate free, no active connect stop. Column H 10/31 = 0 (Mac offline the whole window), logged and reported to COO 12:20. Mon 11/2 cap = min(25, 150 minus 49) = 25, working cap 20 while the 2FA warning is open. Queue Mon 20 (ppc 4, pest 8, local 8), Tue 20, Wed 20, Thu 20; next 3 send days 60 of 75, full at the working cap. All rows pass URL, dedupe, exclusions, held and INDEX checks; no segment above half. No accept pass ran today; 7 accepts, all tracker next steps filled, 0 replies, 0 booked calls, 78 pending in log. No bot fix requests needed. Leak: Mac offline two send mornings in a row (owner Lorenzo via COO). Waiting on Lorenzo via COO: 2FA setup by about 11/3, Gillingham and Rizwan Ahmad invites, Sales Nav page-view resume, Content Bot go. Summary sent to COO.
- 2026-10-30 18:08 leak review: kill switch absent, no active connect stop. Column H 10/30 = 6 (5 targeted plus accidental Sherry Gillingham), logged and reported to COO 11:56. Sat 10/31 cap = min(25, 150 minus 68) = 25, working cap 20 while the 2FA warning is open. Queue Sat 20 (pest 11, local 7, ppc 2), Mon 20 (pest 13, local 7, ppc 0), Tue 20 (ppc 7, pest 5, local 8), Wed 10; next 3 send days 60 of 75, full at the 20 working cap. All rows pass URL, dedupe, exclusions, held and INDEX checks. Leaks (owner Setter, fix asked): Mon has no PPC and pest above half, Sat pest 11 of 20, 7 accepts with blank tracker next step. 7 accepts, 70 connections, 0 replies, 0 booked calls, no openers owed (li-openers-wait-200). Waiting on Lorenzo via COO: Gillingham and Rizwan Ahmad invites (recommend leave pending), 2FA setup by about 11/3, Sales Nav page-view resume, Content Bot go. Summary sent to COO.
- 2026-10-30 15:36 approvals pass: kill switch absent, no active stop. Mac offline 10:01 to 11:49, so the 9:57 pass was skipped and 5 of 20 connects went out (column H 6 with the accidental Sherry Gillingham invite); 15 rolled to Sat. 3 PM pass: 5 new accepts (Jakober, Sharar, Slaymaker, Orten, Tompkins), 7 total, 70 connections, 0 lead replies, no drafts owed. Queue Sat 20, Mon 20, Tue 20, Wed 10. LinkedIn Split Test Bot retired by COO 10/30 (split-test stats now mine). Sent COO priority: 2FA lockout about 11/3, Sherry Gillingham and Rizwan Ahmad invite decisions, accepts FYI, offline-morning blocker.
- 2026-10-29 18:14 leak review: kill switch absent; spinner stop li-stop-salesnav-spinner-20261029 resumed by Lorenzo 5:57 PM (li-resume-20261029). Column H 10/29 = 0 (all sends held). Fri 10/30 cap = min(25, 150 minus 62) = 25, no invite-limit warning so no drop to 20. Setter re-dated Thu 21 to Fri first: Fri 25 queued (ppc 7, pest 8, local 10), all pass dedupe, exclusions and INDEX checks. Sat 36 vs cap 25, first 25 are 16 pest, 0 PPC (owner Setter, rebalance and roll 11 to Mon asked). Next 3 send days 61 of 75, Mon 11/2 short 14 and no PPC (owner Lead Gen Manager, fill asked). 2 accepts total (Jordan, Reino), no openers owed (li-openers-wait-200); accept passes skipped today, resume Fri 9:57. 0 booked calls. 77 pending. Waiting on Lorenzo via COO: Rizwan Ahmad accidental invite; 2FA re-login about 11/3. Waiting on COO: sheet H4 10/22 to 0. Content Bot parked. Summary sent to COO.
- 2026-10-28 18:14 leak review: kill switch absent, no gate-10 stops, no warnings, cap stays 25. Column H 10/28 = 25 of 25 (ppc 9, pest 7, local 9; 24 queue plus accidental Rizwan Ahmad), reported to COO 12:15; reported_counts.jsonl was missing 10/28, backfilled by me. Thu 10/29 cap = min(25, 150 minus 70) = 25. Thu queue 21 queued (pest 8, local 10, ppc 3), all pass dedupe, exclusions and INDEX checks (Matt Reynolds INDEX row is the Setter's queue row only). Leaks: Thu 4 short, Fri/Sat 0, next 3 send days 21 of 75 (owner Lead Gen Manager, fix asked); accept passes skipped all day, Mac offline (owner Setter, rerun asked). 2 accepts total (Jordan, Reino), no opener drafts owed (li-openers-wait-200). 0 booked calls. 77 pending in log. Waiting on Lorenzo via COO: Rizwan Ahmad accidental invite (leave or withdraw); COO to set sheet H4 for 10/22 to 0. Content Bot parked. 2FA lockout warning about 11/3. Summary sent to COO.
- 2026-10-28 15:40 approvals pass: kill switch absent, no active stop. Setter 9:57 AM and 3:00 PM accept passes both skipped (Mac offline), 0 accepts today (unverified), 2 total, no reply drafts. 10/28 column H 25 of 25. Sent COO priority: Rizwan Ahmad accidental invite (leave pending or withdraw) and 10/22 held rows (send or drop) still waiting on Lorenzo; Mac offline; queue Thu 21, Fri and Sat 0 vs target 30; Content Bot parked.
- 2026-10-27 18:14 leak review: list on time (Setter 06:57, my check to COO 07:22, 19 of 19 passed); column H 10/27 = 18 of 20 (Watt email required, Moran 51-200 staff), reported to COO 12:09; reported_counts.jsonl was missing 10/26 (19) and 10/27 (18), backfilled by me. 0 new accepts today (last check 12:12, 3 PM pass skipped per Lorenzo resume-tomorrow), 2 total (Jordan, Reino), no opener drafts owed (li-openers-wait-200-20261026); 0 booked calls, nothing owed to Cold Email Manager. Kill switch absent, no open gate-10 stops (load-error stop closed 12:08, spinner stop resumes 10/28 normal pace). 83 pending. Leak: queue 8 after today (all Wed 10/28), Thu/Fri 0, target 30 (owner Lead Gen Manager via Sales Nav Bot, fix asked). Waiting on Lorenzo via COO: 10/22 held rows (10, send or drop). Content Bot parked. 2FA lockout warning about 11/3. Summary sent to COO.
- 2026-10-27 15:38 approvals pass: no active stop (spinner stop resumed for 10/28, load-error stop closed); 0 accepts today, 2 total, 62 connections at 12:12; 3 PM accept pass skipped per Lorenzo resume-tomorrow; no reply drafts. Sent COO: 10/22 held rows (send or drop, column H 10 to 0), queue 8 after today (Wed only) vs target 30 with Sales Nav refill resuming 10/28, Content Bot parked.
- 2026-10-27 07:22: sent COO the Tue connect list, 19 of 19 passed, none dropped; cap 20 (36 sends prior 6 days), 1 short. Setter asked to add INDEX rows and client files for the 9 rows moved to today (Balwani through Curry), reconcile its 06:57 log (says rolled to 10/28, file says 10/27), and headcount-check Lee, Sharar, Tompkins, Slaymaker, Watt, Curry before sending. Queue for Wed/Thu/Fri is 0/0/0 vs target 30 (Lead Gen Manager), flagged to COO. Next: Setter sends 10 AM-12 PM, I confirm the count to COO for column H.
- 2026-10-26 18:10 leak review: list on time (7:22); column H 10/26 = 19 of 20 (Cody Smith skipped, former owner), reported to COO 11:53; 2 accepts total (Jordan 10/25, Reino 10/26), no opener drafts owed (openers wait for 200 connections, li-openers-wait-200-20261026); 0 booked calls; no kill switch, no gate-10 stops; 62 connections at 18:08, no new replies. Leaks: Jordan tracker accepted blank (owner Setter, fix asked); queue 15 after today, all Tue vs cap 20, Wed 0, target 30 (owner Lead Gen Manager, asked +5 Tue, 20+ Wed, new-search call since v2 nearly dry). Gate window is in OPS_SCHEDULE. Waiting on Lorenzo via COO: 10/22 held rows and column H, PPC candidates, Content Bot (parks 10/26). 2FA lockout warning about 11/3. Summary sent to COO.
- 2026-10-26 15:40 approvals pass: 1 accept today (Carmen Reino), 2 total; 3:00 PM pass 0 new, 65 pending; no drafts (no approved opener). Sent COO: opener copy for Jordan and Reino, 10/22 held rows and column H, PPC candidates, Content Bot parks today; queue 9 after today (all Tue) vs cap 20, v2 pages nearly dry; gate window still not in OPS_SCHEDULE.
- 2026-10-26 07:22: sent COO the Mon connect list, 10 of 10 passed (Mansi, Becklean, Afzal, Kimmes, OConnor, Trachtenberg, Bozett, Vaillancourt, Hanson flagged white-label, O'Sullivan), none dropped. Kill switch absent, no gate-10 stops. Setter sends ~10:15 and ~11:20 under li-232; I confirm the count to COO for column H. Queue 1 of 30 after today (Orten Tue), Tue needs 9 more.
- 2026-10-25 18:05 leak review (Sun): no list due; column H 10/25 = 0; 0 accepts, no drafts owed; 0 booked calls; no gate-10 stops, gate free. Queue 6 after today (Mon 5: Mansi, Becklean, Afzal, Kimmes, OConnor; Tue: Orten), top-up of Mon to 10 sent to Lead Gen Manager (priority). Sent tab 48 pending vs 17 logged, reconcile sent to Setter for its next weekday pass. Waiting on Lorenzo via COO: 10/22 held rows, 22 PPC candidates OK, Content Bot parks Mon 10/26. 2FA lockout warning about 11/3. Summary sent to COO.
- 2026-10-25 10:10 Sunday counts (first baseline, read-only, gate acquired and released, no warnings): 60 connections, 48 pending sent (Sent tab), 66 followers. Logged to linkedin_counts.jsonl. Sent tab shows 48 pending vs 17 tracked in leak reviews; flagged to COO for a Setter reconcile.
- 2026-10-24 18:08 leak review (Sat): no list due; column H 10/24 = 0, nothing to log; 0 accepts, 17 Pending, no drafts owed; 0 booked calls; queue 3 after today (2 ready Mon: Mansi, Becklean; Orten needs URL), refill to 10 for Mon and Orten fix sent to Lead Gen Manager; Sherman URL fixed by Setter; 10/22 rows reverted to held_lorenzo 06:54; no gate-10 stops. Waiting on Lorenzo via COO: 10/22 rows (column H, send Mon), 22 PPC candidates OK, Content Bot parks Mon 10/26. 2FA lockout warning about 11/3. Summary sent to COO.
- 2026-10-23 18:08 leak review: list not on time (7:15 paused by 2FA stop, resumed 10:56); column H 10/23 = 8 of 10 (Setter, li-232, relayed to COO 11:20); 0 accepts, 17 Pending, no drafts owed; 0 booked calls; queue 3 of 30 (2 ready Mon, Orten needs URL, Collier 404 not requeued), refill and URL fix sent to Lead Gen Manager; Setter asked to reconcile Sherman tracker URL vs connect log; no gate-10 stops; gate window now in OPS_SCHEDULE. Waiting on Lorenzo via COO: 10/22 rows (0 of 10 on Sent page, column H, send Mon), 22 PPC candidates OK, Content Bot parks Mon 10/26 if still blocked. 2FA lockout warning lands about 11/3. Summary sent to COO.
- 2026-10-23 15:35 approvals pass: 0 accepts (0 total), no drafts. Sent COO: Lorenzo calls on the 10 unsent 10/22 connects (column H 10 to 0, send Mon) and PPC candidates; queue 3 of 30 after today; gate window waiting on OPS_SCHEDULE; Content Bot blocked.
- 2026-10-23 07:18: 7:15 connect list PAUSED. The Sales Nav 2FA stop (conflict-salesnav-2fa-20261022, approvals.jsonl line 249) is still stop_active with no Lorenzo resume, so all LinkedIn bots are stopped (Setter held 6:45; 10:15 and 11:20 li-232 sends can't run). Told COO (priority) and asked for Lorenzo's resume words before 10:15. 10 rows dated 10/23 are in the queue (Lead Gen, Lorenzo 9:04 PM yes), none in tracker, INDEX or connect log; full fit check and paste-ready list go to COO on resume. Queue 0 of 30 after today. 10/22 rows still read queued until the Setter verifies them on the Sent page.
- 2026-10-22 18:06 leak review: list on time (7:15, 2 leads); column H for 10-22 unlogged, waiting on Lorenzo's count via COO for Adam Loveridge and Tim McCord; 0 accepts, 9 li-231 Pending; 0 booked calls; queue 0 of 30 (owner Sales Nav Bot via Lead Gen Manager, refill plan asked via COO); no gate-10 stops; summary sent to COO.
- 2026-10-22 15:35 approvals pass: 0 accepts (0 total), no drafts. Sent COO the blockers: Lorenzo sent count for Adam Loveridge and Tim McCord still unlogged, queue 0 of 30, Content Bot blocked.
- 2026-10-22 07:15: sent COO a 2-lead connect list (Adam Loveridge, Blue Forge Marketing; Tim McCord, Heavy Levity). Both passed checks, none dropped. Queue is 0 of 30 after today; refill is on Sales Nav Bot via Lead Gen Manager after this morning's 2FA modal stop. Waiting on Lorenzo's sent count via COO, then the Setter logs it.
- 2026-10-21 15:30 (COO, Lorenzo wants the branch to run without him checking): my routines are now Weekday LinkedIn connect list (daily-linkedin-connect-list, weekdays 7:15, to COO by 7:45), Weekday LinkedIn afternoon approvals pass (weekday-linkedin-afternoon-approvals-pass, weekdays 15:30, one message to COO or nothing), Daily LinkedIn leak review (18:00) and Sunday LinkedIn counts (Sun 10:00). Today's 9 unsent queued leads went to COO as today's connect list.
- DONE li-230 (2026-10-21 12:28-12:40): deleted stray search 2003879548. Saved the li-229 fixes as new searches: 'PPC agency owners US 1-50 (pilot) v2' 2003879556 (2K+ results) and 'PPC home services owners US 1-50 v2' 2003879564 (560 results). Originals 2003647996 and 2003701060 are intact. Sales Nav has no update-in-place. Next: Sales Nav Bot (via COO and Lead Gen Manager) and the Setter should use the v2 searches.
- DONE (superseded by li-229/li-230): saved-search filter fix. v2 searches 2003879556 and 2003879564 are live.
- DONE 2026-10-21 16:13-16:21 (li-231): the Setter sent 9 blank connect requests, all logged in linkedin/linkedin_connect_log.jsonl, queue rows marked sent, tracker request_date set, client files updated. Column H = 9 for 2026-10-21, reported to COO in the 18:00 leak review.
- 2026-10-21 18:05 leak review: queue has 0 leads after today (target 30). Owner: Sales Nav Bot via Lead Gen Manager; its fill routine first runs 2026-10-22 ~6:00 CT. No accepts yet, no booked calls, no open gate-10 stops, gate FREE, one session at a time today. Setter asked to confirm Pending on the 8 unverified requests and check accepts at its next pass.
- Held with COO: headline and About rewrite for the PPC pilot (needs a new kit). The About has pay-on-results and guarantee text that conflicts with the plan guardrails.
- WAITING on COO to file li-227 (20261021_linkedin_named_bots_and_gate.md, the approvals row, ~/advero/bin/linkedin_gate, roles/linkedin-setter.md). After that, Setter fills the queue by 6:30 CT and my 6:45 routine posts the list. Resolved 12:13 CT, option (c): my 6:45 routine sends the 10-lead list to COO by 7:45 CT, COO posts it to Lorenzo by 8, and COO passes the sent count back for me to log. I never post to Lorenzo in my chat.
- (superseded) LinkedIn Setter (reports to me, created 2026-10-21) stays off LinkedIn until COO files its Grok update, role doc and gate, and Lorenzo updates my profile. Proposed flow: Setter fills linkedin_connect_queue.csv by 6:30 CT, my routine posts at 6:45. One bot on LinkedIn at a time.

## 7. Files and state
- Manual: ~/advero/GROK_ONBOARDING_PACK.md. Job: ~/advero/03_team.md section 5.
- Plans: ~/advero/linkedin/PLAN.md and ~/advero/linkedin/SIMPLE_PLAN_20261020.md.
- Kit: ~/advero/linkedin/profile_kit.md. Banner: ~/advero/linkedin/linkedin-banner-3168x792.png.
- Skill: ~/advero/skills/linkedin-outreach.md.
- Approvals: ~/advero/state/approvals.jsonl (one register; linkedin_approvals.jsonl links to it), linkedin_cards.jsonl, grok_updates/, ../APPROVALS.md.
- Logs: ~/advero/state/decisions.jsonl.
- Tracker: ~/advero/state/linkedin_tracker.csv (17 leads, 9 fit=high, plus 1 onboarding_unlock account).
- Queue: ~/advero/state/linkedin_connect_queue.csv. Sent counts: ~/advero/state/linkedin_connect_log.jsonl. Weekly counts: ~/advero/state/linkedin_counts.jsonl.
- Before copy: ~/advero/state/linkedin_before/<date>/. Screenshots: ~/advero/state/linkedin_after/.
- Sales Nav saved lead searches (ids):
  - pilot 2003647996
  - home services 2003701060
  - legal 2003701068
  - dental/medical 2003701076
  - real estate 2003701084
  - local SMB 2003745292
- Saved account search: 2003648028.
- Sales Nav lists: "PPC pilot 2026-10" (leads) and "PPC accounts 2026-10" (accounts).
- Sprint sheet (COO owns): 1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0, column H = connection requests sent.

## 9. Shared context
- Client and lead files: before I queue, save or post any lead, I grep ~/advero/state/clients/INDEX.csv for the company, domain and LinkedIn URL and read the client file. Afterwards I append a dated Log line and update the INDEX row, using flock ~/advero/state/clients/.lock. Anyone already in talks on another channel (Upwork, email) is flagged before going on the connect list.
- coo.md (once it exists): approvals, cards, Grok updates and the sprint sheet column H.
- lead-generation-specialist.md: the same PPC agencies may already be in their QuickEnrich or Maps pools or in cold email. I avoid double-touching, and they own the QuickEnrich browser tab. Since li-ce-separate-20261027 (Lorenzo via COO, 2026-10-27 3:08 PM CT, "our cold email campaigns and our LinkedIn campaigns are separate"), a cold email no, opt-out or do_not_reload entry does not keep anyone off LinkedIn.
- linkedin-content-manager.md: profile copy, the kit and posts that prospects will see when Lorenzo connects.
- appointment-setter.md: what happens after a lead accepts or replies, and booked calls.
- copywriter.md: any future connection note or message text (none today, since requests go out blank).
- deliverability-specialist.md: whether a lead is also in a cold email sequence.

## 8. Handoff notes
- Sales Nav Core has no export or CSV. Leads live in the Sales Nav list and the tracker only.
- Saved-search suggestion chips ("+ Upwork", "+ In Training") look like filters but are not applied. Check the green x pills.
- Repeat off-target names across the niche searches (Lonnie Ayers, Marc Abrams, Tarun Singh and others): skip them.
- Skip Lee Bushby (COO instruction).
- The box browser is shared. Lead Generation Specialist owns the QuickEnrich tab.
- StopSubagent with all:true also cancels peers' turns, so use it with care.

## Current daily chain (2026-10-21)
Sales Nav Bot fills linkedin_connect_queue.csv (6:00-6:40). LinkedIn Setter dates today's 10 (6:45) and tells me. My "Daily LinkedIn connect list" routine (about 7:15) checks the rows and sends COO the list by 7:45. COO posts it to Lorenzo by 8, and the sent count comes back through COO to me, then to the Setter, who logs it. The leak review runs at 6 PM. Gate bot name for me: linkedin-outreach-manager.

## Global rules
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.

## Box migration (2026-10-30)
Lorenzo approved PLANNING a move of this work off his Mac to the box. Plan: org/BOX_MIGRATION_PLAN_20261030.md. Nothing moves until Lorenzo says go; keep running as today. Never click sidebar or recommendation areas (People you may know etc.) on any page.

- 2026-11-01 7:00 PM CT: LinkedIn work moved off Lorenzo Mac to the box browser (Lorenzo via COO 6:58 PM). Mac-offline check retired. Caps, pacing, queue and stops unchanged.

- 2026-11-01 7:03 PM CT: LinkedIn outreach PAUSED (li-pause-outreach-20261101, Lorenzo via COO). No connects, openers or messages until he resumes. Queue kept, read-only checks continue, connects routine paused.
