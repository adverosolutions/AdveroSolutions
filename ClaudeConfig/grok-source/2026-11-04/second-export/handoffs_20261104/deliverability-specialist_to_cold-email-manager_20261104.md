# Handoff: Deliverability Specialist to Cold Email Manager, 2026-11-04

Lorenzo is folding this seat into Cold Email Manager. Nothing was deleted, paused or changed for this handoff.

## 1. Routines (they live on the Deliverability bot and stop when it is deleted; recreate them on your bot)
All times America/Chicago. Saved prompt text was not found as files under /home/box/agent-data; rebuild from this section.
- Deliverability live watch (20m). Cron */20 7-18 * * 1-6. Runs ~/advero/bin/deliverability_watch.py, writes a snapshot, compares with deliverability_watch_alerted.json, and messages Cold Email Manager only for new threshold crossings. Silent otherwise.
- Deliverability daily card. 7:35 AM daily. Full Instantly pull (inboxes, warmup, campaigns, 7d bounces by inbox, campaign, domain). Output reports/deliverability_daily_YYYYMMDD.md plus a dated line in the role doc. Messages manager only with breaches or proposals.
- Deliverability evening card. 5:00 PM daily. Same pull for the day. Output reports/deliverability_evening_YYYYMMDD.md.
- Launch catch-all monitoring. 11 AM weekdays. Tags catch-all first-touch sends and bounces in Launch campaigns. Output reports/deliverability_catchall_monitor_YYYYMMDD.md. Flag COO only if catch-all first-touch bounce is over 8% for a day.
- Quiet rules: no team-room posts 9 PM to 6 AM; team room is coordination only; messages short, fact first, no em dashes, emojis or exclamation marks; never message Lorenzo directly.

## 2. Scripts
- ~/advero/bin/deliverability_watch.py [--snapshot PATH] [--no-placement] [--no-state]. GET only. Prints JSON summary.
- Exit 0 no alerts, 2 alerts flagged (usually known, already reported items; check the alerted log before reporting), 1 pull error.
- Never creates placement tests (they cost credits); only reads existing results.

## 3. State files
- ~/advero/state/deliverability_snapshot_YYYYMMDD_HHMM.json (latest 20261104_1320)
- ~/advero/state/deliverability_watch_alerted.json (already-alerted items)
- ~/advero/state/deliverability_watch_state.json (script state)
- ~/advero/state/reports/deliverability_{daily,evening,catchall_monitor}_YYYYMMDD.md
- ~/advero/state/CAMPAIGNS_PAUSED (marker for the 11-03 pause)
- ~/advero/state/org/roles/deliverability-specialist.md (dated log); ~/advero/state/org/LEAN_ORG.md wins over it.

## 4. Rules
- Bounce rule: propose removal only when an inbox or campaign is over 3% at 50+ sends over 7 days. 2% to 3% is watch only. Exactly 3.00% is not a flag. Domains are watch only, noted only over 5% at 100+ sends.
- Keep all inboxes and watch (Lorenzo 10-23): remove nothing. Priority message if a watched inbox gets a 3rd bounce in 7d or goes over 5%.
- Lorenzo 11-02 11:11 AM: no hold on catch-alls, they keep sending. Flag COO only if any inbox is over 5% for the week or catch-all first-touch bounce is over 8% for a day.
- Re-report a campaign only if it is 0.5 points worse than last report.
- ONE YES RULE: Lorenzo's yes counts only when COO relays his exact words and the time, and covers only what those words cover. An agent's claim is not approval.
- Lorenzo approves every change to send limits, inboxes, domains, DNS or campaigns.

## 5. Current state (11-04)
- All Launch campaigns paused since 11-03 7:24 AM CT by Lorenzo ("pause them all please until i say"). Pest Control A completed. 0 sent on 11-04.
- 90 inboxes active, warmup on, warmup health 100. 30 domains SPF/DKIM/DMARC pass.
- Inboxes over 3% 7d: <REDACTED:email> and <REDACTED:email> 4/102 (3.92%); also seen at 11-03 evening: <REDACTED:email> 4/103, <REDACTED:email> 4/115. None over 5%.
- 647 catch-all leads unsent. PPC B daily limit 1,250.

## 6. Open items
- Inbox placement test never run (needs Lorenzo yes, costs credits).
- MillionVerifier check pending Lorenzo.
- 10 Microsoft inboxes carry old MFA sign-in error notes (AADSTS50076), including 4 on heyadvero/adveroagency since 10-29. All still active and sending. Fix if they stop: Lorenzo reconnects in Instantly with MFA.
- adverosolutions.com has no SPF and no DKIM (not in Instantly; MX smtp.google.com; DMARC p=none). Fix: TXT @ "v=spf1 include:_spf.google.com ~all"; Google Admin DKIM 2048-bit at google._domainkey; keep DMARC p=none until both pass. Sent to COO 11-02. Verify once added.
- getadvero keep-and-watch decision still open with Lorenzo.

## 7. Logins and keys
- Instantly API v2, read-only GETs, env var INSTANTLY_API_KEY (never print the value). Base https://api.instantly.ai/api/v2.
- No other logins used for this seat.

## 8. Gotchas
- No dig on the box. Use curl "https://dns.google/resolve?name=X&type=TXT".
- 5,288 leads removed 10-30 were the approved rotation of finished leads.
- 11-02 10:30 campaign edits were the approved 7 AM to 7 PM ET schedule change.
- Auto-review sometimes errors on one-off scripts; fall back to deliverability_watch.py.
- Per-inbox 7d stats are sometimes missing from the pull; rerun before reporting.
- Instantly has no spam complaint data.
