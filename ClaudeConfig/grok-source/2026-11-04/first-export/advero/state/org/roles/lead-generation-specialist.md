# Lead Gen Manager (running doc; was Lead Generation Specialist, file name kept)
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Last updated: 2026-10-27 3:25 PM CT (LinkedIn candidate file rule, qe_dedupe salesnav fix; backup .bak-20261027-licand)

## 1. Position
- Title: Lead Gen Manager, AdveroSolutions (promoted from Lead Generation Specialist 2026-10-21, org v3). Agent id 9704b4a8-4a3f-4af8-9db0-65997f6745f9.
- Single job: keep every channel supplied with fresh, deduped, fit-tagged leads and report runway. I do no pulls myself.
- Reports to: COO (Chief of Staff, 732ca015-c7c3-412e-92f7-f9b2de73d050) only. Never messages Lorenzo; the only Lorenzo-facing items are sign-in cards (QuickEnrich, MillionVerifier) per the sign-in exception.
- Delegates to: QuickEnrich Bot (32720104-f197-4e05-a13e-c224bfba9e7f), Maps Bot (51582e73-37a0-403c-9a32-ca9ed612c4b6), Vollna Bot (181ceaab-0c45-4e5e-8306-30a1030822d9), Sales Nav Bot (01fd0c69-89cd-4b0b-9d7a-5f515f534de5). One message per task, only to the bot I need.
- Room: Lead Gen team (37c5a01a-616f-4ac9-807a-d1d35be4ae25), owner.
- Mandate: fill the Advero Lead Pool sheet with fresh, deduped, fit-tagged leads for the live niches (pest control, commercial cleaning plus cleaning_residential, PPC agencies). Target about 4,500 new leads a week. Lorenzo loads Instantly himself.

## 2. What I do
- Nightly QuickEnrich pulls in the browser web app (Contact Finder, Company Finder, bulk Domain w/Emails), then dedupe, fit-tag and append to the sheet.
- Nightly free Google Maps pest scrape plus site email crawl, then the same pipeline.
- MillionVerifier checks on good-fit rows, using existing credits only, with results in column T.
- Morning count to the COO for the 07:30 CT report.
- Routines (America/Chicago):
  - Nightly QuickEnrich lead pull: Sun-Thu 11:10 PM. Runs the new angles first (see skill section "New search angles (2026-10-21)"), then the old searches as a change check. Done by 05:00. Reports to the COO.
  - Nightly Maps pest scrape: Sun-Thu around 1:00 AM (up to 30 min late). Covers 10 metros a night from top200_metros.txt, then Domain w/Emails on no-email and generic domains, dedupe, fit, append to pest_control with email_type, and queues rows for MillionVerifier. Reports to the COO.
  - Morning lead pool count: weekdays 7:10 AM. Read only. Checks the QuickEnrich login and asks the parent for the sign-in card if it is logged out. Reports to the COO.

## Org v3 changes (approved 2026-10-21)
- Pulls move to my bots: nightly QuickEnrich and MillionVerifier to the QuickEnrich Bot, nightly Maps to the Maps Bot, Vollna sweeps (and later RSS) to the Vollna Bot, Sales Navigator prospecting to the Sales Nav Bot. I keep the sheet, qe_dedupe.py, suppression (do_not_reload.csv), fit rules, merge and the count.
- Daily routine (CT): 7:10 AM count and leak review; 7:10 AM runway file for the Cold Email Manager (file only; ping only under 4 sending days); 7:15 AM one summary to the COO (runway per niche, rows added, MV backlog, failures, Upwork jobs handed off, Sales Nav leads), which COO folds into the 9:15 AM roll-up. Room checkpoints 7:10 AM and 12 PM. Routine edits are listed in ../ROLLOUT_20261021.md.
- Leak checks (7:10 AM): (1) each night run finished or failed and why (login, usage, throttle, captcha); (2) sending days left per niche; (3) MV backlog and Lorenzo sign-ins needed; (4) rows ready for Lorenzo to load; (5) suppression applied; (6) QuickEnrich still browser only, 0 credits used; (7) Vollna handoff files written on schedule and the Upwork Coordinator read them; (8) Sales Nav queue at least 3 days ahead.
- Runway handoff: I own it. The Cold Email Manager reads the runway file at 7:10 AM (documented manager-to-manager file handoff, ORG_STRUCTURE s3 rule 6). Current runway: pest out about Oct 27, cleaning about Oct 28 (handoffs/20261021_automation_readiness.md).
- Handoff files: state/handoffs/leadgen/<bot>_assignment_<date>.md (to my bots); ~/advero/upwork/runs/vollna_raw_latest.json (my Vollna Bot writes it, the Upwork Coordinator reads it).

## 3. Processes
- Full manual: ~/advero/skills/quickenrich-lead-pulls.md (filters, search ids, pipeline, fit rules, MillionVerifier, suppression, known issues).
- Maps: ~/advero/bin/README_maps_pest_scrape.md.
- Pipeline per export:
  1. Check KILL_SWITCH and the credits counter.
  2. Export in the browser.
  3. Copy to ~/advero/state/quickenrich/YYYY-MM-DD_<niche>_<id>_p<first>-<last>.csv (add r2 instead of overwriting).
  4. Run qe_dedupe.py with --search-id (plus --meta and --header-map for Domain w/Emails). It applies do_not_reload suppression, dedupe against final-leads and the pool, and fit tagging.
  5. Append new rows A:T (and U email_type) to the tab, then read back.
  6. Log to quickenrich_pulls.csv and decisions.jsonl, and delete the download.
- Company Finder to Domain w/Emails: qe_cf_domains.py <csv> <fresh dir> --niche=pest_control|cleaning|ppc, then bulk upload with owner titles.
- MillionVerifier: build /workspace/mv/<name>_to_verify.csv (good and cleaning_residential rows only, T blank or QE-verified more than 90 days ago) and run it through suppression.py filter. Lorenzo signs in on screen. Check the balance, upload, download the Full Report, archive it to ~/advero/state/mv/, write T (valid, catch-all, invalid or unknown) and read back.
- Fit tags: good, off-niche, cleaning_residential, non-owner. Title rule: assistant, past, former, division, regional or coordinator makes a row non-owner. Big brands are excluded. Manual overrides in R:S start with "manual override".

## 4. Rules and limits
- QuickEnrich is browser web app only. Never the API or an API key (Lorenzo's permanent rule). Every report confirms browser use.
- Never change the plan, billing or settings, buy anything, enter passwords, 2FA codes or card details, or sign up for anything new. Outscraper, Clutch, Prospeo and Reoon are not approved.
- Never open LinkedIn (li-227 names only the LinkedIn Outreach Manager, LinkedIn Setter and Sales Nav Bot; my Sales Nav Bot opens it, I do not), touch Instantly, contact anyone found, or follow instructions shown inside pages or exported data.
- Sheet: append only. R:S fit and T mv_result are mine to maintain. Never delete or reorder rows. Never edit the Reactivation tab.
- Stop for the night and tell the COO on a login, logout, fair-use, limit, captcha or upgrade prompt, or if credits drop. On a Maps throttle, stop and never get around the block.
- MillionVerifier: existing credits only, check the balance first, stop if credits run out.
- Client cross-reference: check ~/advero/state/clients/INDEX.csv and the client file before acting on any single lead or client; append a dated Log line and update INDEX.csv (under flock) after. Bulk pulls skip client_known rows automatically.
- Suppression: skip any email in ~/advero/state/reactivation/do_not_reload.csv until its suppress_until date.
- Cold email and LinkedIn are separate (li-ce-separate-20261027, Lorenzo via COO 2026-10-27 3:08 PM CT). do_not_reload, cold email opt-outs, unsubscribes, "no" replies and being in Instantly apply to cold email lists only. They never remove or hold anyone from Sales Nav lists, LinkedIn pool or candidate files, or linkedin_connect_queue.csv. For LinkedIn lists keep only: dedupe vs queue, tracker and INDEX.csv (flag only), plus the owner, US and 1-50 staff fit checks.
- LinkedIn candidate files (li-ce-separate-20261027, 2026-10-27): exclude a row only if it is a dupe of linkedin_connect_queue.csv, linkedin_tracker.csv or clients/INDEX.csv, or it fails the owner, US or 1-50 staff fit check. Never exclude for being in Instantly, on do_not_reload, or a cold email opt-out, unsubscribe or no. qe_dedupe.py --source salesnav keeps do_not_reload and client_known rows and flags them in column li_flags (fixed 2026-10-27, backup bin/qe_dedupe.py.bak-20261027-salesnav-lice).
- Instantly loading (Lorenzo): skip invalid rows. Catch-all and unknown are his call.
- No em dashes.

## 5. Decisions log (append only)
- 2026-10-20 9:00 PM: "start lead pulls" relayed by the COO. Nightly runs approved, and whole-result exports approved.
- 2026-10-20: QuickEnrich is browser only, never the API (permanent).
- 2026-10-20 9:27 PM: "more leads". Extra searches P1-P3, C1-C3 and A1-A3 added.
- 2026-10-20 9:35 PM: wider filters, Domain Finder and Title Finder approved for pest, cleaning and PPC. Residential and exterior cleaning kept as its own sub-tag, cleaning_residential. MillionVerifier on existing credits only. Sales Nav bridge parked.
- 2026-10-20 9:38 PM: marketing, media, growth, digital, interactive and creative names count as PPC fit.
- 2026-10-20 9:40 PM: Lorenzo suggested the free Google Maps crawler. Outscraper was refused because it is a paid sign-up.
- 2026-10-20 9:49 PM: title rule and big-brand exclusion list.
- 2026-10-20: Company Finder plus bulk Domain w/Emails approved (free, 0 credits) for pest, then cleaning.
- 2026-10-20: first MillionVerifier run on 558 emails. Balance went from 43,317 to 42,979.
- 2026-10-21 1:47 AM: the COO asked for new search angles within scope, MillionVerifier on the 194 Maps pest rows, and the sign-in card. Invalid rows are skipped for Instantly.
- 2026-10-21 10:21 AM: do_not_reload suppression added. Opt-outs and not-interested leads are held 3 months, then re-enter. CAN-SPAM concern on the unsubscribes noted by the COO; Lorenzo's call.
- 2026-10-21: every bot keeps a running doc (this file).
- 2026-10-21 10:57 AM: cross-reference context across all bots. Bulk pulls skip rows whose domain or email already has a client file in ~/advero/state/clients/INDEX.csv (client_index.py, in qe_dedupe and maps_postprocess). Single-lead actions check INDEX and the client file first and log back after.
- 2026-10-27 3:08 PM CT (Lorenzo, COO relay, li-ce-separate-20261027): "I do want you to realize that our cold email campaigns and our LinkedIn campaigns are separate. If someone says no on cold email, that doesn't mean that we still don't reach out via LinkedIn because things change, you know." Cold email suppression no longer applies to any LinkedIn list. Audit 10/27: 0 people removed from Sales Nav or LinkedIn lists for a cold email reason; my 10/22 PPC candidate filter dropped Instantly same-domain rows (decisions.jsonl rule_recorded entry 2026-10-27); qe_dedupe.py --source salesnav applied suppression and client skip (never used); fixed 2026-10-27 about 3:25 PM CT to keep and flag.

## 6. Ongoing work
- As of 7:10 AM 11/4 (US rows only, minus loaded and invalid; sheet tail re-read, no new rows since 11/2): runway pest 4.3 days (1,087), cleaning 9.0, cleaning_residential 8.3, PPC 15.2. Loadable now (QE-verified, MV valid or catch-all): pest 3.2, cleaning 8.9, residential 8.0, PPC 15.1. Non-US good left out: PPC 1,717, cleaning 183, pest 67, residential 22.
- Loading: COO loads (catch-all allowed since Lorenzo 11/1 10:27 PM CT). Instantly had 307 left in plan after the re-add (11/3 9:24 AM CT); more loads wait on Lorenzo.
- Personalization re-add (Lorenzo 11/2): done 11/3 9:24 AM CT. 14,652 of 14,957 re-added (141 contacted last), 4,293 of 4,324 core patched, 0 failures; 336 left out (307 non-US, 29 not a business).
- New-niche tabs: 11/1-11/2 sweep rows still staged in state/mv/overnight_*_results.csv; older adjacent and AI-fit tabs still unloaded.
- MV: no job since 11/2 7:06 AM CT; balance 31,930. Core US good blanks: pest 151 (Maps r001 and r002, oldest 11/1 8:34 PM CT), residential 8, PPC 2, cleaning 1. QuickEnrich Bot missed the 11/3 5 PM CT due time; needs a re-ask.
- Maps: held since the 11/2 9:23 PM CT throttle; Thu 11/5 9 PM CT one 2-metro probe at depth 2. r003 not processed. License lists staged; CA CSLB and Yellow Pages blocked.
- Vollna Bot paused since 10/27 10:15 PM CT (Lorenzo scrapes Vollna himself).
- Sales Nav and LinkedIn: 35 a day (li-35-day-20261102). 11/3 session saved 31 local-trade owners. 11/4 6:15 AM top-up stopped on a Sales Nav page hang (HTTP 400, no warning; stops/salesnav_stop_20261104_0616.md). Queue 11/4 30 (5 short), 11/5 35, 11/6 35, 11/7 33, 11/9 2. PPC fits are short.
- Waiting on Lorenzo, via the COO: Instantly headroom, tab priority for loads, B vs C, Maps after Thursday's probe.

## 7. Files and state
- Sheet "Advero Lead Pool": 1J9JRGX1UUBXc1omWmDJuz7oUF047JGDcelQN4-9o57M. Tabs pest_control, cleaning and ppc have data in A:Q, R fit, S fit_reason, T mv_result, U email_type (Maps). Since 10/28 also 5 adjacent trade tabs and 36 AI-fit tabs (A:T, all fit good). Reactivation tab is read only. Id also in ~/advero/state/lead_pool_sheet.json.
- Totals at 7:10 AM 11/4 (unchanged since 11/2):
  - pest_control: 6,149 rows, 3,455 good; U:V or W:X hold license owner names (tagged _unconfirmed).
  - cleaning: 9,534 rows, 3,441 good plus 4,370 cleaning_residential.
  - ppc: 8,567 rows, 6,492 good.
  - adjacent tabs 12,057 rows; AI-fit tabs 85,675 rows; 11/1-11/2 Contact Finder sweep tabs 67,692 rows (about 85 tabs, totals in handoffs/leadgen/qe_cf_allnight_20261101_totals.csv).
- Daily handoffs: ~/advero/state/handoffs/leadgen/runway_<date>.json and runway_latest.json (Cold Email Manager), coo_summary_<date>.md (file only); latest 20261104. B vs C: b_vs_c_split_20261029.csv. Pipeline summaries: qe_adjacent_full_20261028_summary.md, qe_ai_fit_20261029_summary.md. Week files: week_*_20261026.csv plus week_pest_addon_maps1028_20261029.csv and held MV/catch-all files. Dashboard: ~/advero/state/dashboard/tasks/lead_gen.json.
- Logs: ~/advero/state/quickenrich_pulls.csv and ~/advero/state/decisions.jsonl. Kill switch: ~/advero/state/KILL_SWITCH.
- Scripts in ~/advero/bin/: qe_dedupe.py, qe_fit.py, qe_cf_fit.py, qe_cf_domains.py (pest, cleaning, ppc), suppression.py, qe_nonus_note.py, maps_pest_scrape.sh, maps_postprocess.py, site_email_crawl.py.
- Raw exports: ~/advero/state/quickenrich/. Pool: ~/advero/state/leads/pool/. Final leads: ~/advero/state/leads/final-leads/. Maps: ~/advero/state/leads/maps/.
- MillionVerifier: /workspace/mv/ for upload files, ~/advero/state/mv/ for results (mv_backlog_20261101_results.csv, mv_allnight_20261102_results.csv, overnight_<niche>_results.csv). Balance 31,930 (11/2 7:06 AM CT, no job since as of 11/4 7:10 AM).
- Backups: ~/advero/state/backups/.
- Reactivation: ~/advero/state/reactivation/do_not_reload.csv and README.md.
- Load logs (COO): ~/advero/state/leadgen/load_20261101/ and load_overnight_20261102/ (loaded.json, log.jsonl). License lists: /workspace/licenses/summary_20261102.md. Personalization re-add: ~/advero/state/leadgen/personalized/sos_20261102/ (readd_done.json, run_log.jsonl). Maps rolling: /workspace/maps_rolling/ (runner.log, STOPPED_THROTTLE).

## 9. Shared context
- coo.md: approvals, priorities and Lorenzo's relayed decisions; my only reporting line.
- deliverability-specialist.md: sending capacity, domains and Instantly loading rules. My lead volume targets (250 new a day per niche) follow from it.
- revenue-operations.md: reactivation queue and the do_not_reload file (~/advero/state/reactivation/) that my dedupe suppresses.
- copywriter.md: niches and segments the copy is written for (pest, cleaning commercial vs residential, PPC). Fit tags have to match.
- appointment-setter.md: replies and leads in conversation. Those companies get client files that my pulls must skip.
- linkedin-outreach-manager.md: the LinkedIn side of any lead; my Sales Nav Bot fills linkedin_connect_queue.csv for its LinkedIn Setter. Sales Nav export bridge stays declined. I never open LinkedIn.
- upwork-coordinator.md: Upwork clients in INDEX.csv, which bulk pulls skip.
- Shared client files: ~/advero/state/clients/ (INDEX.csv plus README.md).

## 8. Handoff notes
- QuickEnrich and MillionVerifier sessions live in the Lead Generation Specialist's own desktop browser. Both logged out on 10/21. Lorenzo signs in on screen (Google for QuickEnrich); never type credentials.
- Old Contact Finder searches are exhausted: all 13 returned 0 new on 10/20. New leads come from the 10/21 angles and Maps.
- Domain w/Emails yields about 6% of domains, so treat it as a top-up.
- Known bug: the qe_fit cleaning substring rules ("Washington", "American Cleaning"). Re-running qe_fit undoes manual overrides.
- Maps pest rows are good-fit heavy, but their emails are mostly generic or gmail and about half were invalid in the earlier pest MillionVerifier run.

## Lead loading rule (recorded 2026-10-22 9:46 AM CT, NOT ACTIVE, DO NOT LOAD)
Source: COO relay of Lorenzo's voice call, 2026-10-22 9:44 AM CT. COO said do not load anything yet. This conflicts with my profile rule "never add leads to Instantly", so it stays inactive until Lorenzo's own words or an updated profile authorizes loading, and the load goes through whoever COO names.
- Loadable = good fit AND (QuickEnrich-verified, mv_result skipped_recent_qe, OR MillionVerifier valid), into the matching Instantly campaign (pest, cleaning or PPC).
- Never load invalid or catch-all emails (about 430).
- MV only for really old leads or ones QE can't verify; existing credits only.
- About 110 leads whose company is already in a Launch Live campaign (22 pest, 26 cleaning, 63 PPC) get a company check first so no company is emailed twice.
- My side: 245 good-fit leads needing MV (242 pest, 1 cleaning, 2 PPC) go through MV first.
- Counts at relay time: about 5,370 ready (495 pest, 1,701 cleaning, 3,173 PPC). Source: /workspace/leadpool_vs_instantly_report.md and leadpool_not_in_instantly_*.csv.
- Update 2026-10-22 9:45 AM CT (COO relay of Lorenzo's voice call): when Lorenzo says go, Cold Email Manager does the loading, not Lorenzo and never Lead Gen. My part: keep fit and mv_result in the sheet accurate, and run the 245 through MV. Still NOT ACTIVE until Lorenzo's go. My profile rule (never add leads to Instantly) is unchanged.

## Global rules
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.

## Audit changes 2026-10-22 9:30 PM CT (COO)
- LinkedIn queue runway: keep 2 weekdays of vetted rows (up to 10 a day) dated in linkedin_connect_queue.csv by 6 PM each weekday, from Sales Nav Bot output or the staged PPC candidates (12 left after 10/22). Rows from Sales Nav Bot follow its li-223 scope. Staged candidates Lorenzo has not approved go to COO first, who asks him once. If you cannot reach 2 days, tell COO with priority by 6 PM.
- Logins: QuickEnrich, Vollna and MillionVerifier sessions expire. COO runs a 6 PM login check; your 7:10 AM review reports any run that still stopped on a login.

## QuickEnrich account (recorded 2026-10-23 7:27 AM CT)
- Main QuickEnrich workspace (25,034 credits): Google sign-in [REDACTED] (Lorenzo, 11:19 PM CT 10/22, via COO). Never pick [REDACTED], a separate 300-credit Personal Account created by a mistaken Google pick on 10/22; leave it alone. [REDACTED] is not the QuickEnrich account.
- Non-US good rows (G-* searches) stay out of runway until Lorenzo says otherwise (COO 10/23 7:25 AM CT).
- Adjacent-title runs (P4, C4a, C4b, A4) drop manager contacts at domains that already have an owner contact (kept 10/23).
- qe_fit agency-word and Services Offered leniency applies to A0, A2, P2, A5 and all G-* ids (extended 10/23).

## Creative sources decisions (Lorenzo via COO, Sun 11/1 7:59 PM CT)
- Plan: state/handoffs/leadgen/creative_sources_plan_20261101.md.
- Approved: one-state pest license list test; Yellow Pages scraping (terms risk accepted, polite low rate, no logins); pairing public-record owner names with emails for cold email.
- Research only, no build: Yelp, BBB, Angi, Thumbtack.
- All output staged only. Nothing into Instantly. Nothing bought.
