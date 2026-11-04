# Advero process export, part 2 (2026-11-04, built ~1:45 PM CT)

Read-only. No scripts were run, no routines, settings or bots changed, nobody messaged.

## Layout
- bin/: every source file in ~/advero/bin (incl. .bak copies; ghl, instantly, linkedin_gate wrappers), redacted. Not executed.
- manifests/: only dependency manifests found under ~/advero outside venvs: state/dashboard/live/web/package.json + package-lock.json. No requirements*.txt, pyproject, Makefile, crontab, systemd or install scripts exist (searched; .venv_video site-packages excluded).
- routine_prompts_20261104/: 8 RevOps saved prompts verbatim (pulled by RevOps with UpdateRoutine get, 11/4 1:25 PM CT), redacted.
- older_saved_prompts/: older verbatim prompt files found on box (PandaDoc watch 10/27, 10/29; Vollna sweep backup 10/22). May be stale.
- handoffs_20261104/: all 14 handoffs from today (routine names/schedules source).
- rules_source/: LEAN_ORG.md and approvals.jsonl, redacted.
- routines/coo/: placeholder for COO's prompts (COO adds them).

## Redaction
Pattern-based: sk- keys, Bearer/Authorization values, key/token/password/cookie/webhook assignments, webhook URLs, all emails, phones, long mixed-case ids (Google Sheet/Doc ids), 22-char PandaDoc doc ids. Env var NAMES kept. Google file ids were redacted too, so restore needs them re-entered. Routine folder slugs kept.

Counts per file:
- bin/yp_sheet.py: {'long_token': 1}
- routine_prompts_20261104/crm-sheet-live-sync.md: {'long_token': 1, 'email': 1}
- routine_prompts_20261104/crm-sheet-nightly-close.md: {'long_token': 1}
- routine_prompts_20261104/dashboard-sheet-refresh.md: {'long_token': 2}
- routine_prompts_20261104/nightly-sprint-row.md: {'long_token': 1, 'email': 1}
- routine_prompts_20261104/pandadoc-watch-leonardo-signed.md: {'long_token': 1, 'pandadoc_doc_id': 3, 'email': 3}
- routine_prompts_20261104/revops-leak-audit.md: {'long_token': 2}
- routine_prompts_20261104/stalled-leads-flag.md: {'long_token': 1}
- older_saved_prompts/handoffs/routines_20261029/pandadoc_watch_msc_prompt.md: {'pandadoc_doc_id': 1, 'email': 3}
- older_saved_prompts/handoffs/routines_20261027/pandadoc_watch_prompt.md: {'long_token': 1, 'pandadoc_doc_id': 3, 'email': 3}
- handoffs_20261104/Accounting_to_COO_20261104.md: {'email': 2}
- handoffs_20261104/Revenue_Operations_to_COO_20261104.md: {'long_token': 2, 'email': 2}
- handoffs_20261104/appointment-setter_to_cold-email-manager_20261104.md: {'long_token': 1, 'email': 14}
- handoffs_20261104/community-content-bot_to_community-manager_20261104.md: {'long_token': 1}
- handoffs_20261104/deliverability-specialist_to_cold-email-manager_20261104.md: {'email': 4}
- handoffs_20261104/maps-bot_to_lead-gen-manager_20261104.md: {'long_token': 3, 'email': 1}
- handoffs_20261104/quickenrich-bot_to_lead-gen-manager_20261104.md: {'long_token': 1, 'email': 5}
- handoffs_20261104/upwork-split-test-bot_to_upwork-manager_20261104.md: {'long_token': 1}
- rules_source/LEAN_ORG.md: {'long_token': 2}

## Skipped
- ~/advero/bin/__pycache__/: compiled bytecode, not source
- ~/advero/state/cases/drew_routine_prompts_20261029.md: client case file (private record)
- ~/advero/.venv_video/: third-party virtualenv, not our code
- .env/auth/session/credential files and lead/client CSV/JSON/JSONL data: excluded by scope (none were in bin)

## Routine prompts: what exists vs missing
Exact prompts included: RevOps 8 (crm-sheet-live-sync, crm-sheet-nightly-close, dashboard-sheet-refresh, instantly-north-star-morning, nightly-sprint-row, pandadoc-watch-leonardo-signed, revops-leak-audit, stalled-leads-flag). Reminders' GHL pin text is in Reminders_to_COO handoff (reminder text, not full prompt).

Limitation for all below: bot-owned routine prompts are stored server-side and can only be read by the owning bot. Not readable from this export.

| Bot | Routine | Schedule (CT) |
|---|---|---|
| COO | all 17 COO routines | COO pulled via get at ~1:40 PM; transcript not readable by this subagent, COO to add files |
| Accounting | weekly-business-spend-and-connects-check-mon-9-a | Mon ~9:00 AM flexible |
| Accounting | highlevel-trial-keep-or-cancel-reminder-nov-10 | once Nov 10 9:00 AM |
| Accounting | sales-navigator-trial-cancel-reminder-nov-19 | once Nov 19 9:00 AM |
| Accounting | zoom-scheduler-trial-cancel-reminder-dec-14 | once Dec 14 9:00 AM |
| Cold Email Mgr (inherited, Appt Setter) | stalled-leads-decision + Marco/Shelley/Wania one-offs | weekdays 8:15 AM; one-offs 11/4, 11/6 |
| Cold Email Mgr (inherited, Deliverability) | live watch, daily card, evening card, catch-all monitor | */20 7-18 Mon-Sat; 7:35; 17:00; 11:00 weekdays |
| Lead Gen Mgr (inherited) | nightly-quickenrich-pull | 10 23 * * 0-4 flexible |
| Lead Gen Mgr (inherited, Maps) | nightly pest scrape, rolling watchdog, YP window (all PAUSED); Thu 11/5 probe | ~1 AM Sun-Thu; 2h; ~2 AM; once 11/5 9:19 PM |
| Lead Gen Mgr (inherited, Sales Nav) | daily connect queue fill; 11-4 fri/thu/sat refills (PAUSED) | weekdays ~6:00 AM |
| LinkedIn Mgr (inherited, Setter) | connect list, accept/messaging pass, li-232 connect sends | ~6:30 daily; ~6:50 & 15:00 weekdays; 7:15-9:15 Mon-Sat |
| Community Mgr (inherited) | evening-community-accountability-drafts (PAUSED); community-engagement-scan-2x-daily (PAUSED) | 45 17 * * *; 2x daily |
| Upwork Mgr (inherited) | upwork-u1-opener-split-test-daily-check (PAUSED) | daily ~6 PM |
| Cold Email / Upwork / LinkedIn / Community / Lead Gen Managers' own routines, Copywriter, Demo Builder | unknown names | no handoff from these bots lists them; ask each bot to run read-only get |

## Rules
### Active (approved by Lorenzo, logged)
- Official offer menu (12:26 PM): P1 $500.00 (normally $1,497.00, first 3-5 customers), P2 $3,497.00, P3 $8,997.00. Cents always; discounts verbal only; only P1 discounted. P1 change to $500.00 at 12:50 PM is already in part 1 ZIP.
- Menu fixed regardless of calls; fit packages from call transcripts (12:27 PM).
- All earlier LEAN_ORG.md rules and security constraints (see rules_source/).

### Changes since 12:50 PM CT
- No new entries in LEAN_ORG.md or approvals.jsonl after 12:50 PM (checked ~1:45 PM).
- Lean team direction (keep 5 managers, Copywriter, Demo Builder, Accounting, RevOps, COO; cut the rest after handoffs) and RevOps folding into COO (1:21 PM, per RevOps handoff) are in handoffs/chat, not yet logged in approvals.jsonl.

### PROPOSED, NOT APPROVED
- Cut routine frequency to every 2 to 4 hours.
- Remove Mission Control or merge it into noon/evening reports.
- Weekly Friday handoff-file update by every bot.

## Files (94)
- bin/README_maps_pest_scrape.md
- bin/README_maps_pest_scrape.md.bak-20261022-reviewsasof
- bin/README_maps_rolling.md
- bin/_load_box_secrets.py
- bin/client_index.py
- bin/deliverability_watch.py
- bin/ghl
- bin/heartbeat.py
- bin/instantly
- bin/instantly_body.py
- bin/instantly_load_20261101.py
- bin/instantly_load_20261101.py.bak-20261102-1045
- bin/instantly_load_overnight_20261102.py
- bin/instantly_load_overnight_20261102.py.bak-20261102-1045
- bin/instantly_load_rotation_20261102.py
- bin/instantly_newniche_B_20261102.py
- bin/instantly_reply_poll_backup.py
- bin/instantly_reply_poll_backup.py.bak-20261020d
- bin/instantly_reply_poll_backup.py.bak-20261022-247
- bin/instantly_reply_poll_backup.py.bak-20261022-audit
- bin/instantly_reply_poll_backup.py.bak-20261102-marco
- bin/linkedin_gate
- bin/maps_pest_scrape.sh
- bin/maps_postprocess.py
- bin/maps_postprocess.py.bak-20261022-reviewsasof
- bin/maps_rolling.sh
- bin/maps_rolling.sh.bak-20261102-halfsize
- bin/maps_rolling_finalize.py
- bin/maps_rolling_finalize.py.bak-20261102-halfsize
- bin/maps_rolling_full.py
- bin/maps_rolling_post.py
- bin/maps_rolling_readback.py
- bin/overnight_reply_queue.py
- bin/overnight_reply_queue.py.bak-20261102-marco
- bin/personalize_feeder.py
- bin/personalize_feeder.py.bak-20261101-fallback
- bin/personalize_runner.py
- bin/qe_cf_domains.py
- bin/qe_cf_domains.py.bak-20261020-cleaningcf
- bin/qe_cf_domains.py.bak-20261020-cleaningcf2
- bin/qe_cf_fit.py
- bin/qe_cf_fit.py.bak-20261020-cleaningcf
- bin/qe_dedupe.py
- bin/qe_dedupe.py.bak-20261020-cleaningcf
- bin/qe_dedupe.py.bak-20261020-restitle
- bin/qe_dedupe.py.bak-20261027-salesnav-lice
- bin/qe_fit.py
- bin/qe_nonus_note.py
- bin/qe_to_sheet.md
- bin/qe_to_sheet.md.bak-20261022-reviewsasof
- bin/reply_rules.py
- bin/review_freshness.py
- bin/site_email_crawl.py
- bin/site_email_crawl.py.bak-20261026
- bin/sos_fix_runner.py
- bin/sos_merge_20261102.py
- bin/sos_personalize_runner.py
- bin/sos_readd_20261102.py
- bin/suppression.py
- bin/video_pipeline.py
- bin/yp_post.sh
- bin/yp_scrape.py
- bin/yp_sheet.py
- bin/yp_window.sh
- handoffs_20261104/Accounting_to_COO_20261104.md
- handoffs_20261104/Reminders_to_COO_20261104.md
- handoffs_20261104/Revenue_Operations_to_COO_20261104.md
- handoffs_20261104/appointment-setter_to_cold-email-manager_20261104.md
- handoffs_20261104/community-content-bot_to_community-manager_20261104.md
- handoffs_20261104/community-engagement-bot_to_community-manager_20261104.md
- handoffs_20261104/copywriter_pilot_variant_20261104.md
- handoffs_20261104/deliverability-specialist_to_cold-email-manager_20261104.md
- handoffs_20261104/linkedin-content-bot_to_linkedin-manager_20261104.md
- handoffs_20261104/linkedin-setter_to_linkedin-manager_20261104.md
- handoffs_20261104/maps-bot_to_lead-gen-manager_20261104.md
- handoffs_20261104/quickenrich-bot_to_lead-gen-manager_20261104.md
- handoffs_20261104/sales-nav-bot_to_lead-gen-manager_20261104.md
- handoffs_20261104/upwork-split-test-bot_to_upwork-manager_20261104.md
- manifests/state/dashboard/live/web/package-lock.json
- manifests/state/dashboard/live/web/package.json
- older_saved_prompts/handoffs/routines_20261027/pandadoc_watch_prompt.md
- older_saved_prompts/handoffs/routines_20261029/pandadoc_watch_msc_prompt.md
- older_saved_prompts/org/roles/backups/vollna-dashboard-sweep_routine_prompt.bak_20261022_0951.txt
- routine_prompts_20261104/crm-sheet-live-sync.md
- routine_prompts_20261104/crm-sheet-nightly-close.md
- routine_prompts_20261104/dashboard-sheet-refresh.md
- routine_prompts_20261104/instantly-north-star-morning.md
- routine_prompts_20261104/nightly-sprint-row.md
- routine_prompts_20261104/pandadoc-watch-leonardo-signed.md
- routine_prompts_20261104/revops-leak-audit.md
- routine_prompts_20261104/stalled-leads-flag.md
- routines/coo/README.md
- rules_source/LEAN_ORG.md
- rules_source/approvals.jsonl
