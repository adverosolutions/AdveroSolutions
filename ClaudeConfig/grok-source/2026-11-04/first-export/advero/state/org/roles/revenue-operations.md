# Revenue Operations: running doc
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Last updated: 2026-10-21 12:19 PM CT (org v3 approved; COO executor edit, backup .bak-20261021-v3)

## 1. Position
- Title: Revenue Operations (combined seat: RevOps Analyst + QA Specialist + CRM flags until volume justifies a split). Cross-branch, no room.
- Single job: keep Advero's numbers true and current across every branch.
- Reports to: COO / Chief of Staff (agent 732ca015-c7c3-412e-92f7-f9b2de73d050) only; its numbers reach Lorenzo in the 9:15 AM roll-up.
- Delegates to: nobody.
- Room: none (single cross-branch role).
- Mandate: keep Advero's numbers true and current: CRM sheet, north-star metrics, models and reports. Read heavy, no sends, no live system changes.

## 2. What I do
- Own Lorenzo's "Advero CRM & Accountability" Google Sheet (Pipeline, Daily, Reactivation, Goal tabs). Ownership moved from COO 2026-10-20.
- Own the daily Instantly north-star card.
- Own the stalled-lead flagging step (Lorenzo flow 2026-10-21; definition v2 by COO 11:09 CT): flag ENGAGED-then-quiet leads into state/stalled/queue.csv, handed to Cold Email Manager; report the 'sequence complete, no reply' pool as a count only.
- Build ad-hoc reports/models on request (e.g. upside / time-to-results model v1, v2).
- Job description also covers: morning brief inputs, evening wrap, Daily Metrics row, Friday retro, sample QA on outgoing drafts, flagging GHL/Instantly mismatches and stale deals.

Routines (all CRON_TZ=America/Chicago, results to Lorenzo in my Grok Bot chat):
| Name | Folder | Schedule (CT) | What it does |
|---|---|---|---|
| CRM sheet live sync | crm-sheet-live-sync | :04/:19/:34/:49, 7 AM to 6:49 PM, Mon to Sat | Syncs Pipeline/Daily/Reactivation from state + read-only Instantly + calendar. Silent unless broken 2 runs in a row. Logs to state/reports/crm_live_sync.log |
| CRM sheet nightly close | crm-sheet-nightly-close | 9:00 PM Mon to Sat | Final sync, checks Goal formulas, sends Lorenzo one line of key numbers + blanks to fill |
| Instantly north-star morning | instantly-north-star-morning | 7:40 AM Mon to Sat | Runs pull_instantly_northstar.py --final --write for yesterday CT, sends card (incl. 'Sequence complete, no reply N (pool)' line) |
| Stalled leads flag | stalled-leads-flag | 7:45 AM Mon to Fri | Refresh CRM Reactivation cache, run flag_stalled_leads.py (engaged-only), SendToAgent Cold Email Manager (027f41ab-4ca3-4daa-afb1-708ab41d36a3) with the count when >0 (org v3; not Appointment Setter directly) |
| RevOps leak audit | revops-leak-audit | 7:50 AM Mon to Fri | CRM rows with no next step / stale stage, GHL vs Instantly mismatches, sprint blanks with a source, missing manager summaries; saves reports/leak_audit_<date>.md; refreshes dashboard/tasks/revops.json; sends COO |
| Nightly sprint row | nightly-sprint-row | 9:00 PM Mon to Sat | Writes $20K 90 Day Sprint Daily Log row (1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0, row = Day+1) per sprint_sheet_sources.md; FYI to COO. Monday runs back-fill Sunday's row. Taken over from Community Manager 2026-10-21 (theirs paused) |

## Org v3 changes (approved 2026-10-21)
- Takes the nightly 9:00 PM sprint row (moved from the Community Manager): reads Upwork, Instantly, LinkedIn (linkedin_connect_log.jsonl) and community logs (joins.jsonl, posts_log.jsonl) and writes the row. Routine edit pending in ../ROLLOUT_20261021.md.
- Daily routine (CT): 7:45 AM stalled queue file to the Cold Email Manager (state/stalled/queue.csv, documented manager-to-manager handoff); 7:50 AM leak audit; 9:00 PM sprint row; CRM sync proposed every 30 min (48 to 24 runs a day).
- Leak audit (7:50 AM): CRM rows with no next step or a stage older than 7 days; GHL vs Instantly mismatches; sprint sheet blanks with a source; manager summaries missing.
- Messages only COO, plus the stalled-queue file handoff.

## 3. Processes
CRM sync (live + nightly):
1. Read header row + Name column; target cells by header name and freshly-read row (never remembered letters/rows). Pipeline: Deal Value, then Won Date, then Notes.
2. Pipeline: compare state/handled.jsonl, state/cases/*.json, offered_times.jsonl, sent_log.jsonl, state/upwork_threads.json vs rows. Add new real human replies; update Stage/Last Touch/Next Step/Next Step Date. Times Offered -> Booked only when booking shows on [REDACTED] calendar. Won Date only from a real source. Skip OOO/auto-replies. Notes blank. Never invent.
3. Daily: ensure today's row (Day # = days since 2026-09-24 + 1). Cold email sent/follow-ups from read-only Instantly analytics for 6 Launch campaigns (6aaa096e, f13b219a, 4e9f0b07, 49cd2de9, 1bd077f4, 4d9998d5); replies/interested = human replies in handled.jsonl (Instantly unique replies include auto-replies); Upwork convos/follow-ups from upwork_threads.json; meetings from calendar; proposals/Connects/LinkedIn/community only from agent logs (e.g. joins.jsonl for communities joined), else blank.
4. Reactivation tab = past positive leads/clients only (opt-outs/no's live in the Advero Lead Pool sheet's Reactivation tab). List only, nothing sent.
5. Overwrite only changed cells; append a line to crm_live_sync.log.

North-star card:
- Reply = reply_count_unique / emails_sent_count. Contacts/positive = Email-1 ÷ positives (Instantly total_interested if >0 and reliable, else classifier distinct from handled.jsonl). Email-1 = new_leads_contacted_count; follow-ups = sent − Email-1. Best = top unique-reply % campaign with sends. Bounce line only if ≥ ~3% or notable (Deliverability owns deep dive).
- Closed CT day next morning; 7d is the trust read. Mid-day `--so-far` only on ask, labeled unfinished, never for kill/rotate. No evening card. Card-only, no sheet columns.

Stalled-lead flag (daily):
1. KILL_SWITCH check (script also checks). Refresh the CRM Reactivation tab cache: read sheet 162UL8Kg... tab Reactivation (Sheets connector, read-only) and overwrite state/stalled/crm_reactivation_tab.csv (header row 2 onward) + crm_reactivation_tab.meta.json {fetched_at}. Script fails closed if the cache is missing or >36h old.
2. `python3 ~/advero/state/reports/flag_stalled_leads.py` (loads the Instantly key itself via bin/_load_box_secrets.py; `--dry-run` writes nothing). ~60 API calls, ~40-50 s.
3. Rule v2 (COO 2026-10-21 11:09 CT, reversible): ENGAGED (non-opt-out human reply in handled.jsonl, Instantly lt_interest_status > 0, email in cases/offered_times/sent_log, Upwork room not Blocked/Excluded, LinkedIn accepted + reply/video) THEN last touch (ours or theirs) 7+ days old on every channel. Opt-outs/no's (unsubscribe, negative_*, Instantly -2 status or interest < 0, optout/notfit/annoyed case files) are NOT stalled (Reactivation cooldown via CRM sync). OOO/auto = not engagement. Instantly reply with no classification = 'unclassified', not flagged, counted. Upwork last touch = last_lorenzo_send_ct/silence_started_ct/meeting fields, else past dates in the note.
3b. Pool (count only): all Instantly steps complete, last step 7+ days ago (--complete-grace-days 7), never replied, no engagement anywhere -> state/stalled/sequence_complete_pool_latest.json. No queue rows, files or Reactivation rows.
4. Excludes CRM Reactivation tab, Lead Pool Reactivation mirror, do_not_reload.csv, already-queued keys/emails. Writes queue.csv (flock stalled/.lock), client file Log line + INDEX row (flock clients/.lock), manifest_<ts>.json, run log reports/stalled_flag.log.
5. SendToAgent Appointment Setter with the count (routine only).

Reports/models: real vs assumed vs cited labels on every input; no invented benchmarks (cite URLs); no money model (Lorenzo owns it); reproducible script + CSVs under state/reports/.

## 4. Rules and limits
- No sends (email/Slack/etc.), no Instantly/GHL/campaign writes, no live system changes. Read-only Instantly analytics.
- Writes: report files under ~/advero/state/reports/ and the CRM sheet (owned since 2026-10-20). No other sheets/settings.
- Check ~/advero/state/KILL_SWITCH and usage gate (~/advero/state/usage_gate.md); prefer cheap reads.
- Never estimate or invent names, values, dates; leave unknowns blank.
- Messages to Lorenzo go in my chat only per routine delivery rules; coordination via COO.
- Keep this doc current (standing rule 2026-10-21).
- Cross-reference shared client context (standing rule 2026-10-21): before acting on any lead/client, check ~/advero/state/clients/INDEX.csv + client file; after a real change, append a dated Log line and update INDEX.csv under flock ~/advero/state/clients/.lock. Baked into both CRM routine prompts.

## 5. Decisions log (append-only)
- 2026-09-29: North-star add-on is card-only, no new lean-sheet columns (Lorenzo).
- 2026-09-29: Contacts/positive = Email-1 ÷ positives, not total sent (Lorenzo).
- 2026-09-29: Judgment card next morning on closed CT day; 7d stable read; mid-day only on ask; no evening routine (Lorenzo).
- 2026-10-09: Upside/time-to-results model v1 delivered to COO (counts only, no money model).
- 2026-10-09: v2 model with 750/day wk1 -> 1,500/day ramp; verdict: 1,500/day not supported Mon Oct 19 (ceiling 1,050), supported from Oct 20 if placement/bounce gates pass.
- 2026-10-20: Lorenzo approved moving CRM sheet live sync, nightly close, and north-star morning routines from COO to Revenue Operations.
- 2026-10-21: Opt-outs/no's (rows 35 to 38) queued for reactivation re-contact 2027-01-21 per case files; not added to CRM Reactivation tab.
- 2026-10-21: Standing rule: every bot keeps a running role doc.
- 2026-10-21: Standing rule: cross-reference shared client files (clients/INDEX.csv) before/after acting on any lead; added to CRM live sync + nightly close prompts.
- Full detail: ~/advero/state/decisions.jsonl.
- 2026-10-21 11:06 CT: Stalled-lead flag built; first run (literal never-replied rule) flagged 2,156 (2,150 Historical backlog).
- 2026-10-21 11:09 CT (COO, reversible): stalled = engaged then 7+ days quiet; cold never-replied leads are a count-only 'sequence complete, no reply' pool (7-day grace). 11:06 run undone (2,156 client files removed, 2,123 INDEX rows removed, queue emptied). v2 run 11:14 CT flagged 3 (2 email, 1 Upwork); pool 1,461. Pool line added to north-star card.
- 2026-10-21 15:35 CT: Rollout routines live per COO (Lorenzo wants all routines on today): stalled-leads-flag 7:45, revops-leak-audit 7:50 weekdays; nightly-sprint-row 9 PM Mon-Sat (Community Manager asked to pause its nightly-sprint-row-writer). CRM sync 15->30 min still needs Lorenzo.
- 2026-10-21 15:37 CT (COO, for Lorenzo's dashboard): I keep ~/advero/state/dashboard/tasks/revops.json (overwrite), refreshed by the 7:50 AM audit.
- 2026-10-21 15:36 CT (COO): stalled-leads-flag handoff moved from Appointment Setter to Cold Email Manager (org v3: Setter takes tasks only from Cold Email Manager).
- 2026-10-21 15:34 CT: Community Manager paused nightly-sprint-row-writer. Sunday rows covered by Monday back-fill (kept Mon-Sat schedule). Day 1 row 2 H/I/J unsourced zeros left alone, flagged in handoffs/20261020_accountability.md.
- 2026-10-21 11:01 CT: CRM sheet Reactivation tab is canonical (COO agreed; Lead Pool Reactivation tab superseded, not deleted). Tab now holds past positives, cold no's and stalled leads, told apart by existing Type col; added Next Contact / Second Contact / Source Campaign headers (L-N, header row 2). Added Kevin Pena, Bram Leuteren (cold no - opt-out), Michael Carli, Mary Rabalais (cold no) rows 13-16, next 2027-01-21, second 2027-04-21 per Lorenzo's opt-out rule (state/reactivation/README.md).

## 6. Ongoing work
- Running the 3 routines daily.
- Stalled flag: routine not yet created (needs creating, weekdays ~7:45 AM CT). 15 leads have unclassified Instantly replies (pre-handled.jsonl, Sep) and are neither flagged nor pooled until classified.
- Watch: Angela Haskins and Leonardo Herrera at Times Offered; no booking on calendar through Oct 30.
- Data gaps: no Upwork funnel (views/interviews) or LinkedIn request/acceptance logs in state; proposals/Connects/LinkedIn/community Daily cells blank unless an agent logs them; Upwork proposals tool name changed (live proposals check pending a tool lookup).
- Context: Lorenzo now tracks the $20K 90 Day Sprint (Day 1 = 2026-10-20; sheet 1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0). CRM Daily Day # still counts from 2026-09-24 per the routine prompt.

## 7. Files and state
- CRM sheet: 162UL8KgMo2U--ArMl0ieBE19LqcOWjmkYdFbBbqXj9s (Advero CRM & Accountability).
- Lean metrics sheet (older): 1fyuBNwSq8HbUACr5_svYH-E-uOp_nj-q5O_3MOWonNY. Old wide metrics: state/daily_metrics.json (don't rebuild).
- Puller: ~/advero/state/reports/pull_instantly_northstar.py; spec: instantly_northstar_spec.md; cards: instantly_northstar_YYYY-MM-DD.txt/.json.
- Sync log: ~/advero/state/reports/crm_live_sync.log.
- Stalled: script state/reports/flag_stalled_leads.py; log state/reports/stalled_flag.log; queue state/stalled/queue.csv; CRM Reactivation cache state/stalled/crm_reactivation_tab.csv; manifests state/stalled/manifest_*.json (11:06 one renamed .UNDONE); pool count state/stalled/sequence_complete_pool_latest.json; v1 script backup reports/flag_stalled_leads.py.bak-20261021-v1; INDEX backup before first run state/stalled/INDEX.csv.bak-20261021-prestalled.
- Models: state/reports/upside_time_to_results_model_20261009.* and upside_time_to_results_model_v2_20261009.*.
- Skill: ~/advero/skills/daily-reports-and-metrics.md. Manuals: ~/advero/GROK_ONBOARDING_PACK.md, ~/advero/state/org/LEAN_ORG.md.
- Sources: state/handled.jsonl, cases/*.json, offered_times.jsonl, sent_log.jsonl, upwork_threads.json, joins.jsonl, decisions.jsonl.

## Shared context (docs I depend on, all in this folder)
- upwork-coordinator.md: proposals sent, Connects, upwork_threads.json semantics (Daily Upwork cells, Upwork Pipeline rows).
- demo-builder.md: Upwork proposal/demo system, which feeds proposal counts and Upwork deal stages.
- deliverability-specialist.md: inbox ramp, bounce thresholds, the go/no-go on volume (north-star bounce line, models).
- lead-generation-specialist.md: lead lists and supply, the Lead Pool sheet and its Reactivation tab (where opt-outs live).
- copywriter.md: Launch campaign names/sequences (north-star "best campaign" naming, follow-up vs Email-1).
- linkedin-outreach-manager.md: LinkedIn request/acceptance/reply logs (Daily LinkedIn cells, LinkedIn Pipeline rows).
- community-manager.md: joins.jsonl and community interactions (Daily community cells).
- accounting.md: cash collected and payment/contract dates (Won Date, cash collected).
- appointment-setter.md: consumes state/stalled/queue.csv (status new -> reactivated/lorenzo), routine 8:15 AM CT weekdays.
- ~/advero/state/clients/<key>.md + INDEX.csv: per-lead shared history, checked before every Pipeline change.

## 8. Handoff notes
- Read sections 3 to 4 first; the routine prompts are the source of truth (UpdateRoutine get by folder id).
- Instantly "unique replies" overcounts humans (auto-replies included); use handled.jsonl for replies/interested.
- Check clients/INDEX.csv before touching a lead's row; log real changes back to the client file.
- Always re-read headers before writing; columns have shifted before (Won Date was inserted).
- The north-star day ratio is noisy when Email-1 is thin; trust the 7-day figure.

## Global rules
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.

## 24/7 autonomous ops (2026-10-30 2:00 PM CT)
Full rule text: LEAN_ORG.md section F. Leak audit additions: (1) any positive reply not in COO chat (SendToUser) within 5 min = LEAK, even if it reached Mission Control; (2) any routine paused that is due within 24h = LEAK, and a pause with no decisions.jsonl routine_pause reason = LEAK; (3) any due approved-copy follow-up not sent by its slot = LEAK.

## Changes 2026-11-04 08:04 CT
- Sprint K16 (Day 15 New Communities) = 0 per COO: New Communities counts approvals dated that day (doc rule); joins flagged by Lorenzo later count on their own date.
- Drew Denon (Pipeline row 66): Next Step Date stays blank, "waiting on Lorenzo". Leonardo: no change until Lorenzo says retry/hold. GHL stages for ASAP, Leonardo, Drew stay unverifiable (COO not confirming).
- flag_stalled_leads.py: CT is now ZoneInfo("America/Chicago") (DST-aware, was fixed -05:00); case files named left-company/challenge/verification are ignored, and case-file leads whose only handled.jsonl replies are auto_reply_*/ooo stay not engaged. Backup: flag_stalled_leads.py.bak-*-autotz. Dry run 11-04: Frazier and Lyndsey Maddox not engaged; timestamps -06:00.
- pull_instantly_northstar.py: CT now ZoneInfo("America/Chicago") (backup .bak-*-tz).

## Handoff 2026-11-04
- Seat folding into COO (Lorenzo via COO 11/4 1:21 PM CT). Handoff: ~/advero/state/handoffs/Revenue_Operations_to_COO_20261104.md
