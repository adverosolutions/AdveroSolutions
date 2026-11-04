# Cold Email Manager routines 8-16, verified by UpdateRoutine get at 1:50 PM CT, 2026-11-04
Read-only. Nothing was created, changed, paused or run. Every saved prompt below was checked against the get output and matches it word for word. Lead emails are redacted, and Doc and Sheet IDs are kept. Schedules are CRON_TZ=America/Chicago.

### 8. Deliverability live watch (20m)
folder deliverability-live-watch-20m | firesAt CRON_TZ=America/Chicago 9,29,49 7-18 * * 1-6 | enabled | CRON_TZ=America/Chicago */20 7-18 * * 1-6 | flexible, early 10, late 10 | first ran 1:46 PM CT 11/4
Prompt:
Deliverability seat, now part of my role (handoff doc ~/advero/state/handoffs/deliverability-specialist_to_cold-email-manager_20261104.md, rules section 4). Run ~/advero/bin/deliverability_watch.py. It only reads from Instantly and uses env INSTANTLY_API_KEY; never print the key. Exit 0 means no alerts. Exit 2 means alerts: compare them with ~/advero/state/deliverability_watch_alerted.json and treat only threshold crossings not already in that file as new. Exit 1 means the pull failed: rerun once. For a new crossing, message COO with priority true, short and fact first: any inbox over 5% for the week, a watched inbox getting its 3rd bounce in 7 days, or catch-all first-touch bounces over 8% for a day. Over 3% at 50+ sends is a removal proposal only and needs Lorenzo's yes; nothing gets removed or changed. Stay silent when nothing is new. Never change inboxes, campaigns, send limits or DNS, and never create placement tests. Never message Lorenzo.

### 9. Deliverability daily card 7:35
folder deliverability-daily-card-7-35 | firesAt CRON_TZ=America/Chicago 40 7 * * * | enabled | CRON_TZ=America/Chicago 35 7 * * * | flexible, early 15, late 15 | never run
Prompt:
Deliverability seat, now part of my role (handoff doc ~/advero/state/handoffs/deliverability-specialist_to_cold-email-manager_20261104.md, rules section 4). Do a full read-only Instantly pull with ~/advero/bin/deliverability_watch.py plus GETs as needed, using env INSTANTLY_API_KEY and never printing it. Cover inboxes, warmup, campaigns, and 7-day bounces by inbox, campaign and domain. If per-inbox stats are missing, rerun. Write ~/advero/state/reports/deliverability_daily_YYYYMMDD.md and add a dated line to ~/advero/state/org/roles/deliverability-specialist.md. Message COO only for breaches or proposals: inbox or campaign over 3% at 50+ sends in 7 days, any inbox over 5%, or a domain over 5% at 100+ sends (note only). Re-report a campaign only if it is 0.5 points worse than last time. Otherwise stay silent. Read only: change nothing, and never message Lorenzo.

### 10. Deliverability evening card 5 PM
folder deliverability-evening-card-5-pm | firesAt CRON_TZ=America/Chicago 8 17 * * * | enabled | CRON_TZ=America/Chicago 0 17 * * * | flexible, early 15, late 15 | never run
Prompt:
Deliverability seat, now part of my role (handoff doc ~/advero/state/handoffs/deliverability-specialist_to_cold-email-manager_20261104.md, rules section 4). Do the same read-only Instantly pull as the daily card, covering today, using ~/advero/bin/deliverability_watch.py and env INSTANTLY_API_KEY (never print it). Write ~/advero/state/reports/deliverability_evening_YYYYMMDD.md. Message COO only for new breaches under the bounce rules: over 3% at 50+ sends in 7 days proposes removal, over 5% for an inbox, 8% catch-all first-touch for a day. Otherwise stay silent. Change nothing, and never message Lorenzo.

### 11. Launch catch-all monitor 11 AM
folder launch-catch-all-monitor-11-am | firesAt CRON_TZ=America/Chicago 55 10 * * 1-5 | enabled | CRON_TZ=America/Chicago 0 11 * * 1-5 | flexible, early 15, late 15 | never run
Prompt:
Deliverability seat, now part of my role (handoff doc ~/advero/state/handoffs/deliverability-specialist_to_cold-email-manager_20261104.md). Read-only on Instantly, using env INSTANTLY_API_KEY and never printing it. Tag the catch-all first-touch sends and bounces in Launch campaigns for the day, and write ~/advero/state/reports/deliverability_catchall_monitor_YYYYMMDD.md. If campaigns are paused (~/advero/state/CAMPAIGNS_PAUSED) and nothing was sent, note that briefly. Flag COO with priority true only if catch-all first-touch bounces are over 8% for a day; otherwise stay silent. Catch-alls keep sending under Lorenzo's 11-02 rule. Change nothing, and never message Lorenzo.

### 12. Stalled leads decision 8:15
folder stalled-leads-decision-8-15 | firesAt CRON_TZ=America/Chicago 29 8 * * 1-5 | enabled | CRON_TZ=America/Chicago 15 8 * * 1-5 | flexible, early 15, late 15 | never run
Prompt:
Appointment Setter's seat is now part of my role. The process is in section 1, "Stalled-leads decision", of ~/advero/state/handoffs/appointment-setter_to_cold-email-manager_20261104.md, and ~/advero/state/org/LEAN_ORG.md wins over it.

Process the status=new rows in ~/advero/state/stalled/queue.csv. Close any row whose only inbound replies are auto_reply_* in handled.jsonl as closed_false_positive_autoreply. For each remaining lead, read the client file, the thread (read only) and the cases.

(A) Reactivation: append a row to the 'Reactivation' tab of the 'Advero CRM & Accountability' sheet (162UL8KgMo2U--ArMl0ieBE19LqcOWjmkYdFbBbqXj9s) with type stalled, next contact today plus 3 months, and status "reactivation queued - stalled". Never touch the Lead Pool sheet.
(B) A warm signal, a past call, Upwork, a big lead or anything unclear: send COO a one-line hold card.
A plain no, an unsubscribe or a pause is routed and logged with no card, under the ONLY YESES rule. September leads go to nurture with no card.

Then update the queue status and log the client file and INDEX under flock ~/advero/state/clients/.lock, keeping CRLF line endings. Send no emails, Upwork or LinkedIn messages. Stay silent unless a hold card is needed.

### 13. Shelley pre-call brief Wed Nov 4
folder shelley-pre-call-brief-wed-nov-4 | PAUSED (one-off finished) | CRON_TZ=America/Chicago 36 13 4 11 * | exact | ran 1:41 PM CT, skipped because Setter's brief went at 1:33
Prompt:
One-off, taken over from Appointment Setter (handoff ~/advero/state/handoffs/appointment-setter_to_cold-email-manager_20261104.md). Shelley at ASAP Pest has a call today at 2:30 PM CT. If ~/advero/state/decisions.jsonl or her client file already shows Appointment Setter sent COO a pre-call brief for her today, stop silently. Otherwise send COO one priority brief that fits on one screen: facts, warnings, likely objections and a call outline. Pull it from clients/asappestsolutions.com.md, cases/asap_shelley_*, and the queue precall file if there is one. Log it in her client file.

### 14. Marco R4 one-hour Wed Nov 4
folder marco-r4-one-hour-wed-nov-4 | enabled | CRON_TZ=America/Chicago 0 15 4 11 * | exact | never run
Prompt:
One-off, taken over from Appointment Setter (handoff ~/advero/state/handoffs/appointment-setter_to_cold-email-manager_20261104.md). Marco Cevallos at Quantum Pest has a call today at 4:00 PM CT (2:00 PM PT), event dtrmq2m8e35uervd7bfamelfog. Lorenzo approved this R4 via COO on 11/3 at 9:42 AM CT: "Yes, arm Marco's 1-hour reminder".

Check before sending. Check ~/advero/state/sent_log.jsonl for the key [lead email redacted]|show_rate.reminder_1h_email|2026-11-04, or any Marco entry today mentioning reminder_1h, R4 or one-hour. If one exists, Appointment Setter already sent it, so stop silently. Then check that KILL_SWITCH is absent, that his INDEX row and client file are in order, and that his thread has no cancel or reschedule.

If clear, send the approved R4 word for word ("See you in an hour. I'll be on a couple minutes early.", signed Lorenzo, template show_rate.reminder_1h_email.lorenzo_final_20261022). Send it in thread f1-Oc6yrbk4Z429xvE0AvqX27g from [EMAIL], with reply_to set to his newest inbound id.

Log it in sent_log with that key, plus the client file, INDEX (under flock, keeping CRLF) and decisions. If anything is unclear, send COO a priority hold card instead.

### 15. Marco pre-call brief Wed Nov 4
folder marco-pre-call-brief-wed-nov-4 | enabled | CRON_TZ=America/Chicago 2 15 4 11 * | exact | never run
Prompt:
One-off, taken over from Appointment Setter (handoff ~/advero/state/handoffs/appointment-setter_to_cold-email-manager_20261104.md). Marco Cevallos at Quantum Pest has a call today at 4:00 PM CT. If Appointment Setter already sent COO a pre-call brief for Marco today (check decisions.jsonl and clients/quantumpest.com.md), stop silently. Otherwise send COO one priority brief that fits on one screen: facts, warnings (including the 10/30 no-show), likely objections and a call outline. Pull it from his client file and cases/marco_*. Log it in his client file.

### 16. Call outcome pings Wed Nov 4
folder call-outcome-pings-wed-nov-4 | enabled | CRON_TZ=America/Chicago 30 15,17 4 11 * | exact | never run
Prompt:
One-off audit pings, taken over from Appointment Setter. The 3:30 PM CT run covers Shelley at ASAP Pest, whose call ended at 3:00. The 5:30 PM CT run covers Marco at Quantum Pest, whose call ends at 4:30. If that lead's outcome is already logged today in their client file or decisions.jsonl, stay silent. Otherwise send COO one priority line asking for the call's outcome and next step, so it can be logged within 24 hours.

