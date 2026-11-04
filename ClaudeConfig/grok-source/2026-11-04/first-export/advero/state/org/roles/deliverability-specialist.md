# Deliverability Specialist: running doc
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.

Last updated: 2026-10-23 11:00 AM CT (Lorenzo via COO: keep all inboxes and watch; no removals incl. old 12; routines updated)

## 1. Position
- Title: Deliverability Specialist, Cold Email branch, AdveroSolutions.
- Single job: keep every sending inbox and domain healthy and flag burn the same day with one clear recommended fix.
- Reports to: Cold Email Manager (027f41ab-4ca3-4daa-afb1-708ab41d36a3) only, per the profile update on 2026-10-21. I never message Lorenzo directly. Lorenzo approves every change through COO.
- Delegates to: nobody.
- Room: Cold Email team (67666b1b-7a52-4505-83fc-c44421a655c7).
- Mode: draft and report only until Lorenzo unlocks more. Source charter: ~/advero/state/org/LEAN_ORG.md (Deliverability Specialist section). Skill: skills/deliverability-and-inboxes.md inside ~/advero/GROK_ONBOARDING_PACK.md.

## 2. What I do
Responsibilities:
- Read live Instantly inbox and domain health: status, warm-up, bounce, replies, sends per inbox, campaign state.
- Check DNS auth (SPF, DKIM, DMARC, MX) on all sending domains.
- Track list quality behind bounces (MillionVerifier status, catch-all, provider mix).
- Plan and propose placement tests and blocklist checks.
- Write daily and evening health cards, flag problems the same day, and send recommended fixes to the Cold Email Manager.
- Answer COO requests (research, go/no-go, investigations), read-only.

Routines (all CRON_TZ=America/Chicago):

| Routine | Schedule (CT) | What it does |
|---|---|---|
| weekday-instantly-health-check | 7:24 AM, Mon to Fri (`24 7 * * 1-5`) | Original morning health check. Overlaps the 7:35 daily card; retirement waiting on Lorenzo via COO. |
| deliverability-live-watch-20m | Every 20 min, 7 AM to 6:40 PM, Mon to Sat (`*/20 7-18 * * 1-6`) | Runs ~/advero/bin/deliverability_watch.py, saves a snapshot, alerts only on new breaches (deduped via the alert record file). Bounce alerts only when an inbox is over 3% at 50+ sends (7-day). Cadence stays every 20 min for now; hourly is waiting on Lorenzo via COO. |
| deliverability-daily-card | 7:35 AM daily (`35 7 * * *`) | Morning card: today so far, 7-day sends, bounces, replies, inbox status, warm-up, DNS, decisions needed. |
| deliverability-evening-card | 5:00 PM daily (`0 17 * * *`) | Evening card: the day's totals, per-campaign and per-inbox bounce, open decisions. |

The last three moved from the COO to me on 2026-10-20 with Lorenzo's approval, using the COO's exact prompts. Flexible early/late windows are not supported by the routines tool, so fixed times are used.

Reporting: all 4 routines report to the Cold Email Manager (027f41ab-4ca3-4daa-afb1-708ab41d36a3), not to Lorenzo.

Client and lead rule in prompts: all 4 routine prompts now include the client and lead check-then-log rule (section 4), updated 2026-10-21 11:00 AM CT.

Bounce flag: the daily card, evening card and live watch prompts use Lorenzo's 3% rule (section 4) as of 2026-10-21 5:05 PM CT. The old 2% flag is dropped. The skill doc (skills/deliverability-and-inboxes.md) still prints 2%; Lorenzo's rule in ~/advero/state/org/deliverability_overrides.md wins over it.

## Org v3 changes (approved 2026-10-21)
- Cards go to the Cold Email Manager (it folds them into its 8:45 AM roll-up to COO), not straight to Lorenzo, once the routine edits in ../ROLLOUT_20261021.md are made.
- Routine (CT, proposed): 7:35 AM card; 5 PM card; live watch hourly instead of every 20 min (36 to 12 runs a day); retire the 7:24 check. Hourly watch and retiring 7:24 are still waiting on Lorenzo via COO; the watch stays every 20 min for now.
- Done 2026-10-21: all 4 routines report to the Cold Email Manager.
- Leak checks: bounce over 3% at 50+ sends; any inbox or domain flag waiting on Lorenzo over 2 days.

## 3. Processes
Daily and evening card:
1. Pull live Instantly data first (never assume). GET /accounts, /accounts/analytics/daily (25 emails or fewer per call), /campaigns, campaign analytics, warm-up analytics.
2. Compute today and 7-day sends, bounces and replies per inbox, per domain, per campaign, and fleet-wide.
3. Apply the thresholds in section 4. Check DNS auth for all domains.
4. Write the card to ~/advero/state/reports/deliverability_YYYY-MM-DD.md and .json, plus deliverability_daily_YYYYMMDD.* (evening: deliverability_evening_YYYYMMDD.md).
5. Message the Cold Email Manager: fact first, the decision needed, then the watch items. Short and plain. Never message Lorenzo directly.

Live watch:
1. Routine runs ~/advero/bin/deliverability_watch.py.
2. Snapshot saved to ~/advero/state/deliverability_snapshot_YYYYMMDD_HHMM.json; state in deliverability_watch_state.json.
3. Alert only on a new breach not already listed in ~/advero/state/deliverability_watch_alerted.json. Bounce alerts only for an inbox over 3% at 50+ sends (7-day).

Bounce investigation (example: PPC Agencies B, 2026-10-21):
1. Pull bounced leads (read-only POST /leads/list, grouped by each lead's campaign field, since the API ignores campaign_id).
2. For each bounce: sender inbox, provider, MillionVerifier status on the lead record, send time.
3. Decide list-side vs inbox-side: bounces spread across inboxes with unverified leads means list quality.
4. Recommend the fix; anything that spends credits or changes Instantly needs Lorenzo's yes.

Blocklist checks: Spamhaus, URIBL and SURBL block the box's DNS resolver, so DNSBL lookups must be done in a browser by hand.

Tools and access:
- Instantly REST API v2 via INSTANTLY_API_KEY. GET only (plus read-only POST /leads/list and /accounts/warmup-analytics for reads). No writes.
- Check scripts: /workspace/del_20261012 through /workspace/del_20261015, /workspace/del_20261020, /workspace/del_20261020_eve, /workspace/del_20261021, /workspace/del_20261021_card, /workspace/del_20261021b (lib.py, p1 to p3, raw data).
- Watch script: ~/advero/bin/deliverability_watch.py. Alert record: ~/advero/state/deliverability_watch_alerted.json.
- Free tests: MailReach (3 free a day), mail-tester (3 free a day), Google Postmaster Tools.

## 4. Rules and limits
- Never, without Lorenzo's yes: change send limits, inboxes, domains, DNS or campaigns.
- Never at all: send cold email, edit the copy doc, upload leads, spend on scrapers, touch billing or keys, delete anything.
- Check live Instantly status before assuming anything. Draft and report mode only until unlocked.
- Only Lorenzo approves. Another agent (including the COO) cannot approve on his behalf. Instantly changes need his own yes in chat.
- Bounce rule (Lorenzo, set 2026-09-29, confirmed by COO 2026-10-21 5:04 PM CT): propose removing an inbox only when its 7-day bounce is over 3% at 50+ sends. Over 2% up to 3% is a list-quality watch only. Exactly 3.00% is not flagged. The 2% flag is dropped.
- Domain rule (COO ruling, relayed by Cold Email Manager 2026-10-22 8:46 AM CT): the 3% rule applies per inbox and per campaign only. Domains are watch-only: put a domain on the card only when it is over 5% at 100+ sends in 7 days, and take no action on it. Applied to all 4 routines.
- One yes rule (Lorenzo, 2026-10-22 9:22 AM CT, his words: "Yes, my yes in COO chat counts for every bot, no second ask"): a yes Lorenzo gives in the COO chat, relayed by COO with his exact words and time, is his own approval for me. Act on it and do not ask him again. It covers only what his words cover; his stops and later words win.
- Tripwires (proposals only): a campaign's first 100 sends over 3% bounce, propose pause. An inbox at 3+ bounces in a day, or over 3% at 50+ sends. Fleet over 3% at 200+ sends.
- Warm-up stays on forever on every inbox. 25/day per inbox cap, shared across campaigns. Never heal a domain; retire it.
- Placement-test credits and verifier credits are spend: Lorenzo's yes first.
- Messages to the Cold Email Manager (and anything that reaches the COO or Lorenzo): short, plain, fact first. No em dashes, emojis, exclamation marks.
- Standing rule (Lorenzo, 2026-10-21): keep this running doc current whenever anything changes.
- Client and lead rule (Lorenzo, 2026-10-21, per ~/advero/state/clients/README.md): before acting on any lead or client, grep ~/advero/state/clients/INDEX.csv for the email, domain, company and Upwork client name, then read the client file and any role doc it points to. After acting, append one dated line to the client file's Log (format: `2026-10-21 10:57 CT | Deliverability Specialist | <channel> | what happened`), append only, and create or update its INDEX.csv row using `flock ~/advero/state/clients/.lock`. Read-only fleet analysis that does not act on a lead (bounce counts, inbox checks) still starts with the INDEX.csv check.
- Before changing a process that hands work to or from another bot, read that bot's role doc first.

## 5. Decisions log (append-only)
- 2026-09-22: Health alerts only; monitor proposes, Lorenzo applies every change (skill doc).
- 2026-09-29: Lorenzo's bounce rule set at over about 3% at 50+ sends per inbox; 2% to 3% is a watch.
- 2026-10-02 to 10-07: Bounce cause found to be list quality. Catch-all leads bounced 37.5% (120 leads), AOL/Yahoo 15.7%, the rest about 2%. Oct 1 was 47 of 300 (15.67%). I proposed removing the 12 old inboxes; no answer.
- 2026-10-12: My verdict, 1,500/day on 12 inboxes is NO-GO. 750/day on 30 inboxes (25/day each) is GO WITH LIMITS after list fixes. Measurement go line: at least 10 of 11 new domains and 27 of 30 inboxes pass tests.
- 2026-10-12: Old domains (adveromedia, myadvero, proadvero, theadvero) to be kept isolated and retested, not deleted.
- 2026-10-12: Cheapest paid option noted: a second verifier (NeverBounce or Bouncer, about $8 per 1,000, $8 to $25 total). Nothing bought.
- 2026-10-12: Monday launch staged read-only (900 first-3-day leads, 1,687 reserve). Never applied by me.
- 2026-10-20: Lorenzo approved moving 3 deliverability routines from the COO to me.
- 2026-10-21: Lorenzo's standing rule: every bot keeps a running doc in ~/advero/state/org/roles/.
- 2026-10-21: Lorenzo's standing rule: shared client and lead files in ~/advero/state/clients/, checked before and logged after any action on a lead or client. Added to all 4 routine prompts at 11:00 AM CT.
- 2026-10-21: Profile update: I report to the Cold Email Manager (027f41ab-4ca3-4daa-afb1-708ab41d36a3) and never message Lorenzo directly. All 4 routines now report to the Cold Email Manager.
- 2026-10-21 5:04 PM CT: Bounce rule confirmed by COO as Lorenzo's: propose removing an inbox only when its 7-day bounce is over 3% at 50+ sends; over 2% up to 3% is a list-quality watch; exactly 3.00% is not flagged. 2% flag dropped.
- 2026-10-21 5:05 PM CT: Daily card, evening card and live watch prompts switched to the 3% rule. The live watch reports bounce alerts only over 3% at 50+ sends.
- 2026-10-21 5:15 PM CT: 10-16 and 10-19 cards rebuilt from Instantly daily analytics (read-only GET): 0 sent both days. Cause: box stuck starting up those mornings; root cause not confirmable (see reports/deliverability_missing_cards_1016_1019.md).

- 2026-10-22 8:46 AM CT: COO ruling relayed by Cold Email Manager: 3% rule per inbox and per campaign only; domains watch-only, on the card only over 5% at 100+ sends in 7 days, no action. Applied to all 4 routines.
- 2026-10-22 9:08 AM CT: Lorenzo, in my chat: "Yes, run MillionVerifier on existing credits, PPC B first, and pause non-ok leads". Run log: ~/advero/state/reports/mv_verification_20261021.md.
- 2026-10-22 9:22 AM CT: Lorenzo's one yes rule (section 4).
- 2026-10-22 12:09 PM CT: MV run done by QuickEnrich Bot via Lead Gen Manager on existing credits (42,835 to 39,595). 2,702 non-ok unsent leads listed for hold (5 client matches excluded). Hold not applied. 1:35 PM CT: Lorenzo decided (via COO) to keep all 2,702 in, no hold; hold-method ask dropped.
- 2026-10-23 11:05 AM CT: First 'Launch catch-all monitoring (11 AM)' run, read-only. FYI, no clear negative trend: launch to date catch-all 6/387 (1.55%) vs valid 15/986 (1.52%), 10-23 new leads catch-all 3/279 vs valid 6/442. Sample too small to separate 1.5% from 3%. Watch Pest B catch-all 4/75. 8 inboxes at 2 bounces just over 3% at 50+ (keep-and-watch rule, no removals); the 3 keep-and-watch inboxes had no trigger. MV 10-22 ok results inferred (out/ lost). Card: ~/advero/state/reports/deliverability_catchall_monitor_20261023.md; data /workspace/catchall_monitor_20261023/.
- 2026-10-26 11:12 AM CT: Second catch-all monitoring run, read-only. FYI, no negative trend: launch to date catch-all 6/696 (0.86%) vs valid 20/1,463 (1.37%), Fisher p=0.40. Catch-all by first-touch day 1.1% (10-23) then 0/277 (10-24); 0 of 366 catch-all follow-ups bounced; 0 catch-all bounces since 10-23. Pest B catch-all 4/127 (3.15%), no new bounce. No inbox over 3% at 50+ (getadvero 3/114, proadvero 3/116). Card: ~/advero/state/reports/deliverability_catchall_monitor_20261026.md; data /workspace/catchall_monitor_20261026/.
- 2026-10-27 11:08 AM CT: Third catch-all monitoring run, read-only. FYI, no negative trend: launch to date catch-all 7/966 (0.72%) vs valid 24/1,910 (1.26%), Fisher p=0.25, catch-all 95% range 0.35% to 1.5%. Catch-all by first-touch day 1.1%, 0%, 0%, 0.4% (10-23 to 10-27); 0 of 645 catch-all follow-ups bounced. Pest B catch-all 4/179, no new bounce. MV invalid 3/39 and unknown 2/48, watch only. No inbox over 3% at 50+ (top adverostudio lorenzov and myadvero lorenzovillarreal 3/126). Card: ~/advero/state/reports/deliverability_catchall_monitor_20261027.md; data /workspace/catchall_monitor_20261027/.
- 2026-10-28 11:15 AM CT: Fourth catch-all monitoring run, read-only. FYI, no negative trend: launch to date catch-all 8/1,261 (0.63%) vs valid 31/2,340 (1.32%), Fisher p=0.06, catch-all 95% range 0.27% to 1.25%. Catch-all by first-touch day 1.1%, 0%, 0%, 0.4%, 0.3% (10-23 to 10-28). Today 750 sent, 9 bounces. Pest B catch-all 5/230 (2.17%), one new. MV invalid 5/50, unknown 2/62, watch only. No inbox over 3% at 50+ (top myadvero lorenzovillarreal 3/126). Card: ~/advero/state/reports/deliverability_catchall_monitor_20261028.md; data /workspace/catchall_monitor_20261028/.
- 2026-10-29 11:10 AM CT: Fifth catch-all monitoring run, read-only. FYI, no negative trend: launch to date catch-all 12/1,708 (0.70%) vs valid 39/2,840 (1.37%), Fisher p=0.04, catch-all 95% range 0.40% to 1.22%. Catch-all by first-touch day 1.1%, 0%, 0%, 0.4%, 0.3%, 0.9% (10-23 to 10-29); one-day uptick, still under valid 1.6%. Today 1,020 sent (PPC B 790, PPC A paused), 13 bounces on 967 first touches. Pest B catch-all 5/231, Clean A catch-all 4/237 watch. MV invalid 6/62, unknown 2/70, watch only. No inbox over 3% at 50+ (top myadvero and adveroteam lorenzovillarreal 4/138, 2.90%). Card: ~/advero/state/reports/deliverability_catchall_monitor_20261029.md; data /workspace/catchall_monitor_20261029/.
- 2026-10-30 11:15 AM CT: Sixth catch-all monitoring run, read-only. FYI, no clear negative trend: launch to date catch-all 15/1,950 (0.77%) vs valid 41/3,039 (1.35%), Fisher p=0.07, catch-all 95% range 0.47% to 1.27%. Catch-all by first-touch day 1.1%, 0%, 0%, 0.4%, 0.3%, 0.9%, 1.2% (10-23 to 10-30, last day partial); 10-30 is the first day catch-all is above valid (3/242 vs 1/199, p=0.63), watch next send day. Today 1,055 sent (PPC A paused), 4 bounces on 443 first touches, 0 on 612 follow-ups. Pest B and Clean A catch-all watches unchanged. No inbox over 3% at 50+ (top tryadvero lorenzo and adveroteam lorenzovillarreal 4/138, 2.90%). Card: ~/advero/state/reports/deliverability_catchall_monitor_20261030.md; data /workspace/catchall_monitor_20261030/.
- 2026-11-02 11:15 AM CT: Seventh catch-all monitoring run, read-only. PRIORITY to COO, copy Cold Email Manager: clear negative trend. 11-02 first touches catch-all 14/266 (5.26%) vs valid 2/228 (0.88%), Fisher p=0.009; catch-all by day 0.3%, 1.1%, 1.2%, 3.8%, 5.3% (10-28 to 11-02), above valid three send days running. Clean B catch-all 7/76, PPC B 4/69, Pest B 3/121. All 14 are newer payload-tagged catch-alls, not the 10-22 batch. [REDACTED] crossed to 5/128 (3.91%), 3 of 5 today's Clean B catch-all bounces. Cumulative catch-all 32/2,269 (1.41%) vs valid 45/3,301 (1.36%). Recommended (Lorenzo decides): hold the 868 unsent catch-all first touches (PPC B 312, Pest B 262, Clean B 238, PPC A 56), keep step-2 follow-ups (0 bounces), keep inboxes on. Found 5,288 contacted no-bounce no-reply leads gone from Instantly since 10-30 (not me); carried from the 10-30 file. Card: ~/advero/state/reports/deliverability_catchall_monitor_20261102.md; data /workspace/catchall_monitor_20261102/.
- 2026-11-03 11:10 AM CT: Eighth catch-all monitoring run, read-only. FYI (under Lorenzo's 11-02 flag lines: inbox over 5% or catch-all day over 8%). Campaigns paused 7:24 AM. Today 336 sent, 221 first touches all catch-all, 7 bounced (3.17%: Clean B 5/106, Pest B 2/115), 0 of 115 follow-ups. Catch-all by day 5.3% (11-02), 3.2% (11-03). meetadvero and proadvero lorenzovillarreal crossed to 4/115 (3.48%) on one catch-all bounce each; none over 5%. 647 unsent catch-all first touches queued. Card: ~/advero/state/reports/deliverability_catchall_monitor_20261103.md; data /workspace/catchall_monitor_20261103/.
- 2026-11-04 11:10 AM CT: Ninth catch-all monitoring run, read-only. No sends since the last run (all Launch campaigns still paused since the approved 11-03 7:24 AM pause, 0 sent 11-04). One-line FYI to COO, copy Cold Email Manager. Card: ~/advero/state/reports/deliverability_catchall_monitor_20261104.md.

## 6. Ongoing work
MV run status (2026-10-22 12:25 PM CT):
- Verification done 10-22 ~12:09 PM CT by QuickEnrich Bot via Lead Gen Manager, existing credits (42,835 to 39,595, 3,240 used for 5,546 checks). No hold: Lorenzo decided 10-22 1:35 PM CT (via COO) to keep all 2,702 in the six Launch campaigns. Read-only 'Launch catch-all monitoring (11 AM)' weekday routine tracks bounces, complaints and health by verification group, reports to COO with a copy to Cold Email Manager. Catch-alls pulled only on a clear negative trend, Lorenzo's call. Baseline: reports/deliverability_catchall_impact_20261022.md.
- 5,871 unsent exported: 3,164 valid, 2,235 catch-all, 71 unknown, 76 invalid, 325 prior catch-all (10-10). Counts recomputed and match the report; full coverage.
- Verification group lists (used for monitoring, not a hold): /workspace/mv_run_20261022/hold/ (all_nonok.csv 2,702; invalid_only.csv 76; per-campaign <slug>_nonok.csv; client_excluded.csv 9). Per campaign to hold: PPC B 906, Pest A 222, PPC A 881, Clean B 221, Clean A 243, Pest B 229.
- All 2,702 held leads unsent as of 12:13 PM CT (GET per lead). Each campaign contacts 125 new leads per send day, so re-check right before any hold.
- 9 client-matched leads excluded and logged in their client files.

Current state (2026-10-21):
- 6 "Launch 2026-10" campaigns live since 2026-10-20 (Pest Control, PPC Agencies, Commercial Cleaning, each A and B). Created 10-19 as QA HOLD drafts.
- 60 inboxes on them, including all 12 old inboxes. 90 inboxes total in the account, all active, warm-up 100. All 30 domains pass SPF, DKIM, DMARC.
- Pace: 750/day (each campaign hits its 125-lead daily max). Fleet bounce about 1% to 1.7% (Oct 20: 13 of 750, 1.73%; 7-day as of Oct 21 7:36 AM: 20 of 1,496, 1.34%).
- No verified leads left unsent in any Launch campaign: 6,247 unverified and 374 catch-all unsent.
- Watch: joinadvero (3 of 51) and proadvero (3 of 81) domains over 3%, but no inbox over 29 sends.

Findings 2026-10-21 (report: ~/advero/state/reports/deliverability_coo_ppcb_outlook_20261021.md, pulled 10:20 AM CT, read-only):
- PPC Agencies B: 6 bounces of 250 contacted (2.4%), today 3 of 125, 7-day 2.82% (6 of 213). 5 of 6 bounced leads had no MillionVerifier result, 1 was MV ok from a June check, 0 catch-all. 6 different sender inboxes, 1 bounce each, none over 27 sends in 7 days. Bounces flagged 7 to 20 seconds after send, which fits dead addresses. Verdict: list quality, not inbox-side. Watch, not a removal. None of the 6 bounced lead domains are in clients/INDEX.csv.
- Outlook: the 6 Microsoft inboxes on adverocorp.com and adverosystems.com show a stale Sep 30 to Oct 1 "Permanent OAuth failure AADSTS50076 (MFA)" note. All six are status active, warm-up 100, warm-up landing in inbox. 3 send in Pest Control A/B ([REDACTED], [REDACTED], [REDACTED]) with 0 bounces. No reconnect needed. Reported to the COO and Lorenzo.

Waiting on Lorenzo (via COO):
0. DECIDED 2026-10-23 (Lorenzo via COO, relayed by Cold Email Manager 10:59 AM CT: "Keep all inboxes and watch"). No removals, including the old 12, and no Instantly changes. Keep-and-watch: [REDACTED] (2/50), [REDACTED] (2/52), [REDACTED] (2/54). Priority message to Cold Email Manager with numbers if any gets a 3rd bounce in 7 days or goes over 5%. Keep reporting [REDACTED] and [REDACTED] once past 50 sends. All four routines (live watch, 7:24 check, daily card, evening card) updated with this.
1. CLOSED 2026-10-23 by the keep decision above: remove the 12 old inboxes. Do not re-propose.
2. DONE 10-22 (run done; no hold per Lorenzo 1:35 PM CT, all 2,702 stay in). MillionVerifier run on unsent leads (existing credits only) and the catch-all hold (proposal 2026-10-21). Start with PPC B: run its 1,862 unverified unsent rows and hold its 81 catch-all rows, then keep only ok rows. Same gap in all 6 campaigns: 6,247 unverified and 374 catch-all unsent. Spends verifier credits. The run itself sits with the Lead Generation Specialist (MillionVerifier owner, Lorenzo signs in) and loading changes are Lorenzo's in Instantly.
3. Placement test on the fresh inboxes (spends test credits).
4. Retire the 7:24 AM weekday-instantly-health-check (overlaps the 7:35 card).
5. Live watch cadence: hourly per the new profile, or keep every 20 min. Stays every 20 min for now.
6. The 13-item Monday ask-first card (2026-10-12), never answered.

Next steps:
- If yes on retiring 7:24: delete that routine (only with his yes). If yes on hourly: change the live watch schedule to hourly.
- Keep all routines running. Handle routine wakes and COO requests. Update this doc after each change.

## 7. Files and state
Reports (~/advero/state/reports/):
- Daily cards: deliverability_YYYY-MM-DD.md/.json and deliverability_daily_YYYYMMDD.md/.json, 2026-09-28 to 2026-10-21 (10-16 and 10-19 missing; rebuilt as deliverability_2026-10-16_backfill.md and deliverability_2026-10-19_backfill.md, cause in deliverability_missing_cards_1016_1019.md).
- Evening: deliverability_evening_20261020.md, deliverability_evening_20261021.md (750 sent, 0.93% bounce, 0.67% reply, no new flags); deliverability_evening_20261022.md (750 sent, 1.20% bounce, 0.67% reply, no new flags, PPC B campaign 2.13% watch). deliverability_evening_20261023.md (1,475 sent, 0.61% bounce, 0.75% reply; 7d 3,725 at 1.02%; keep-and-watch no trigger, [REDACTED] and [REDACTED] joined it; 3 more inboxes at 2 bounces just over 3% recommended keep-and-watch).
- deliverability_go_nogo_2026-10-12.md/.json, deliverability_monday_gonogo_20261009.md.
- deliverability_free_test_plan_2026-10-09.md, deliverability_free_placement_options_2026-10-09.md.
- deliverability_measurement_system_2026-10-12.md (Section 1B paid options, ask-first item 13), deliverability_scoring_sheet_template.csv.
- monday_launch_stage_2026-10-12.md.
- deliverability_coo_ppcb_outlook_20261021.md (PPC B bounces and Outlook OAuth note).
- Catch-all monitoring: deliverability_catchall_impact_20261022.md (baseline), deliverability_catchall_monitor_20261023.md (first monitor run), deliverability_catchall_monitor_20261026.md (second run), deliverability_catchall_monitor_20261027.md (third run), deliverability_catchall_monitor_20261028.md (fourth run), deliverability_catchall_monitor_20261029.md (fifth run), deliverability_catchall_monitor_20261030.md (sixth run), deliverability_catchall_monitor_20261102.md (seventh run, priority), deliverability_catchall_monitor_20261103.md (eighth run).
State and data:
- Leads: ~/advero/state/leads/staged_leads_first3days_2026-10-12.csv (900), staged_leads_reserve_pool_2026-10-12.csv (1,687).
- MillionVerifier: ~/advero/state/mv/2026-10-20_all_to_verify_mv_full.csv. 10-22 run: /workspace/mv_run_20261022/ (in/, out/, hold/), log ~/advero/state/reports/mv_verification_20261021.md.
- Backup: ~/advero/state/backups/instantly_pre_monday_20261011/.
- Watch: ~/advero/state/deliverability_snapshot_*.json, deliverability_watch_state.json, deliverability_watch_alerted.json.
- Scripts: ~/advero/bin/deliverability_watch.py; /workspace/del_2026101x and del_2026102x folders.

## 8. Handoff notes
- Read section 4 first. Nothing changes in Instantly without Lorenzo's own yes in chat.
- Bounce: use Lorenzo's rule only (over 3% at 50+ sends per inbox, 7-day; over 2% up to 3% is a watch; exactly 3.00% not flagged). The 2% in the older skill doc is dropped.
- Inboxes: 30 picked for the 750/day plan are lorenzo@ and lorenzovillarreal@ on 11 new domains, plus lorenzov@ on adverocreative, adverogrowth, adverohq, adveropartners, adverosolution, adverostudio, adveroteam and getadvero. The 12 old inboxes sit on adveromedia, myadvero, proadvero and theadvero.
- Known issues:
  - The box failed to start on 2026-10-16 and 2026-10-19, so those cards are missing (since rebuilt from Instantly analytics: 0 sent both days). If it happens, tell the Cold Email Manager so Lorenzo can use Update Bot's Computer.
  - 6 Outlook inboxes (adverocorp and adverosystems) show a Sep 30 to Oct 1 "Permanent OAuth failure AADSTS50076 (MFA)" note. It is stale: all six are active, warming at 100, and 3 send in Pest Control A/B with 0 bounces. No reconnect needed. A reconnect, if ever needed, is Lorenzo signing in via Instantly Email Accounts with Microsoft MFA.
  - DNSBL lookups are blocked from the box resolver; use a browser.
  - MillionVerifier statuses cannot be read by GET; mapping lead IDs needs a read-only POST.
- Instantly API traps: /leads/list ignores campaign_id (group by lead's campaign field); unknown filter values are silently ignored and return all leads; daily analytics takes 25 emails or fewer per call.

## 9. Shared context
Role docs I depend on (all in ~/advero/state/org/roles/, listed in INDEX.md):
- ~/advero/state/org/roles/coo.md (COO / Chief of Staff): approvals routing, hold cards, org rules, and who I report to. Listed in INDEX.md but not written yet as of 2026-10-21 11:10 AM CT. Until it exists, use ~/advero/state/org/LEAN_ORG.md.
- ~/advero/state/org/roles/lead-generation-specialist.md: where lead lists come from, MillionVerifier runs (existing credits only, Lorenzo signs in, balance last 42,979), results in Lead Pool column T, reports archived to ~/advero/state/mv/. Any verify-unsent-leads plan goes through this doc.
- ~/advero/state/org/roles/copywriter.md: copy and campaign sequences, spintax and subject rules. Copywriter reads my doc for what is live in Instantly. I never edit copy.
- ~/advero/state/org/roles/revenue-operations.md: daily metrics and bounce line (they report bounce only at about 3% or notable; I own the deep dive). Keep numbers consistent with theirs.
- ~/advero/state/org/roles/appointment-setter.md: replies to cold threads from [REDACTED], one of the 12 old inboxes I propose removing from Launch campaigns. Removing it from campaigns should not stop existing reply threads, but read that doc before any inbox change.
- ~/advero/state/org/deliverability_overrides.md: Lorenzo's bounce rule overrides, not a role doc but binding.

Shared client and lead context:
- ~/advero/state/clients/README.md and INDEX.csv. Before acting on any lead or client, check INDEX.csv and the client file. After acting, append a dated line to the client file's Log and update INDEX.csv (with flock). All 4 routine prompts include this rule as of 2026-10-21 11:00 AM CT.


## Global rules
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.

- 2026-10-30 evening: 4 more Outlook inboxes (heyadvero x2 lorenzov/lorenzovillarreal, adveroagency x2) show the AADSTS50076 MFA OAuth note since 10-29 evening; still active and sending with 0 bounces. Watch only; fix if they stop sending is Lorenzo reconnecting in Instantly with MFA.
- 2026-11-02 evening: 1,439 sent, 1.18% bounce, 0.21% reply; 7d 6,455 at 0.90%. 16 active campaigns, capacity 1,500. PPC B limit 1,250. Breaches [REDACTED] 5/128 (3.91%) and [REDACTED] 4/121, no removal proposal; keep-and-watch no trigger. Card: reports/deliverability_evening_20261102.md.
- 2026-11-03 7:45 AM CT: Daily card. All 16 Launch campaigns paused 7:24 AM CT by Lorenzo via COO (marker ~/advero/state/CAMPAIGNS_PAUSED), approved. 467 sent before pause, 11 bounced (2.36%). Inbox breaches 4/103 tryadvero lorenzo, 4/115 adverostudio, meetadvero, proadvero lorenzovillarreal; none over 5%, no COO flag. Card: ~/advero/state/reports/deliverability_daily_20261103.md.
- 2026-11-04 1:30 PM CT: Seat folding into Cold Email Manager. Handoff written: ~/advero/state/handoffs/deliverability-specialist_to_cold-email-manager_20261104.md. Nothing deleted or paused.
