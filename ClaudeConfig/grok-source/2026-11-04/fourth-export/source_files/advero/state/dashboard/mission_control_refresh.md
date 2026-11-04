# Mission Control hourly refresh recipe
Page: canvas 62414b8c-c569-4384-bd19-a57e8296b7cb (read-only, no Tailscale, no webhooks, no servers).
Rules: EditCanvas only the text between /*DATA*/ and /*END*/. Never WriteCanvas. Keep field names. Never invent a number; unknown = "—" (or null for kpis). Cut bots (Copywriter, 5 Committee seats, 4 split-test bots) stay out. Times in CT.

## Header
- updated: now, "Day Mon D, h:mm AM/PM CT". sprintDay: days since Tue 10/20 + 1.
- offDay: true on Sunday, else false. money: sum of sprint log column N.

## kpis (Lorenzo's own tasks; targets from org/LORENZO_KPIS.md, set 11/1; done counts for today only)
- Upwork proposals: target 6; done = Upwork proposals submitted today (Upwork pipeline/sent log).
- Reply to interested leads and Upwork messages: target = count of new interested/client messages today; done = those answered by Lorenzo today (handled.jsonl, upwork_threads.json). null if none came in.
- Booked calls held: target = calls on today's calendar; done = held. null if none.
- Proposals out within 24h of a call: target = calls held yesterday or today needing one; done = proposals sent. null if none.
- Community comments: target 1; done = communities/posts_log.jsonl comments dated today.
- LinkedIn content post: target 1 on Mon/Wed/Fri, 0 other days; done = posts published today (content manager report).
- Clear Waiting-on-you items: target 0 left by 6 PM CT; done = items still open (COO evening list).
- Maker School accountability post: target 1; done = posts_log entries titled "Accountability Day N" today (kept from before; not in LORENZO_KPIS core 7).
- Event-driven rows (replies, calls, proposals): when nothing came in, keep target null and targetText as the rule.
- Weekly strip: calls booked target 7/week, Upwork proposals target 36/week (Mon to Sat).
- Sunday: set offDay true; the Page shows the off-day state.

## channels[].stats rows: [label, today, 7 days, sprint to date]
- Cold email: reports/sprint_row_writes.log F (sent), G (replies); handled.jsonl positive_interested by date; deliverability report for bounce % and inboxes (healthy / sending).
- Upwork: pipeline.csv proposals, replies, interviews; Connects only if confirmed spend exists, else "—" or "N planned".
- LinkedIn: requests = linkedin/reported_counts; connections/pending = linkedin_counts.jsonl latest; accepts "—" (no source). Badge "Outreach paused" while paused.
- Community: posts_log.jsonl comments/posts, joins.jsonl approved = groups.
- Sequences: copy/interested_sequence_tracker.json and copy/post_proposal_tracker.json.
- Results: sprint log M = calls booked, N = $ closed.

## Sprint to date (column 4 of every stats row) = sprint sheet ONLY
- Read sheet 1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0, tab 'Daily Log', rows Day 1 (10/20) to today. Blank cells = 0. Never use local logs for this column.
- Map: Upwork Proposals->Upwork Proposals, Upwork Replies->Upwork Replies, Cold Emails Sent->Cold email Sent, Email Replies->Cold email Replies, LinkedIn Requests Sent->LinkedIn Requests, LinkedIn Replies->LinkedIn Replies, Community Posts->Posts, New Communities->New communities, Community Engagement->Engagement, Calls Booked->Calls booked, $ Closed->$ closed.
- Sheet has no column for positives, bounce, inboxes, Connects, interviews, accepts: those stay as the log-based value or "—".
- Today/7 days: sprint_row_writes.log and the bot logs listed above.

## bots[] (state, task, since)
- working: the bot wrote a report/log or heartbeat in the last 60 minutes; task = what that file says, since = its time.
- paused: kill switch or paused routine. failed: last run errored / signed out.
- lounge: everything else; task = next scheduled job.
- status: ok / wait (needs Lorenzo) / bad (paused or failed). Also update note, last, next.

## Also refresh: emails, replies (last 7 days, Mon..Sun), proposals, sequence, waiting (from COO evening list).

## heat (activity heatmap, last 7 days x 24 hours CT)
- Run: python3 ~/advero/state/dashboard/heatmap_compute.py ; paste its first JSON line into DATA.heat (labels, grid).
- Sources: state/decisions.jsonl, sent_log.jsonl, approvals.jsonl, linkedin_approvals.jsonl, handled.jsonl, heartbeats.jsonl, linkedin/linkedin_connect_log.jsonl, linkedin/gate_log.csv, linkedin/reported_counts.jsonl, leads/maps/state/runs.csv, reports/*.log (incl. crm_live_sync, cold_email_rollup, sprint_row_writes, upwork_scrape_runs, stalled_flag), leads/maps/logs/*.log (one event per file per hour), upwork/runs/post_sweep_*.log (leak sweeps), upwork/runs/run_log.md, content/video_drop/video_log.jsonl. Backups and Upwork job-listing CSVs are excluded.

## The office
- Top section, driven by bots[].state: working = sits at its desk typing with a task bubble; lounge = wanders; paused/failed = dimmed at desk with icon. Only edit DATA.

## Today's must-dos card (keep until Lorenzo marks it done)
Keep a "Today's must-dos" card directly under the Mission Control header, above The office. Text, word for word:
- Copy and ideation: variant testing, how much to collect per deal, is a 15-min call ideal and how to stretch it, apply Cialdini's Influence.
- Ideation keywords: webinar, teaching, agents, bots, automations.
- Reminders Mon 11/2 at 8 AM, 10 AM, 12 PM, 2 PM CT.
Do not remove or reword it on any refresh. Remove only when Lorenzo says it is done.

## Cleared waiting items (Lorenzo 2026-11-01 ~10:40 PM CT: "clear the to-dos ... I already handled"). Never re-add on refresh:
- LinkedIn two-step verification (done, LEAN_ORG L15)
- Reddit signup (vault 2506970)
- QuickEnrich and MillionVerifier sign-in (vault 2506751, 1499257; bots re-sign in on their own)
- Upwork "Confirm 10/26 and 10/28 sends" (send times don't matter; parked jobs >12h always dropped)
- Instantly upload cap raise (decided 11/2: not raised; requeue finished leads, LEAN_ORG.md)
- Instantly login, Codex/Orca sign-in, pest/cleaning fallback lines, Yellow Pages and scrape/source decisions (all handled 11/1)
- (11/2 10:22 AM CT, Lorenzo t1735u) Instantly upload cap; idle/reserve inbox spreading; MFA/inbox errors; 1,500/day volume; Deliverability dashboard; 90-day re-hit reminder; Sales Nav retry; MillionVerifier login; Tailscale (cancel chosen); Namecheap Private Email (auto-renew off); LinkedIn outreach pause (resumed; only Looms paused); Upwork 0 proposals/demo picks (8-job batch building); Accounting weekly spend; copy reminder; Justin (backburner, never a to-do)
- (11/2 10:29 AM CT, Lorenzo t1741u) FYI follow-ups note; Marco Quantum Pest (times approved, sending); Community week plan 11/2-11/7 (committed); PPC fallback line (COO drafting cold-read options); 7 AM campaign move (all active campaigns now 7 AM-7 PM ET); 11 new B campaign wording (delegated to COO review); SPF/DKIM adverosolutions.com (delegated, steps in deliverability/adverosolutions_spf_dkim.md); Ignacio check-in (COO handling); Reddit sign-in (signed in, 17 subs joined); Upwork QA follow-up draft; Connects for 8-job batch (he has plenty)
- (11/2 3:04 PM CT, Lorenzo direct to COO) Accidental Dan Kurtz LinkedIn invite: left pending, not withdrawn
- Already dropped 11/2, never re-add: Julius Ayal close/reply; Overnight push note; Duplicate Leonardo Zoom event; CRM sync 15 to 30 min
Keep open unless evidence says done: HighLevel trial (cancel by 11/13), Dawnn Clisby call outcome, Mohammed Salem comment draft (while comment_drafted in conversation_tracker), GHL cancel 11/12, copy+ideation must-dos card. 'Second trust line per niche' stays only as an explanation card (Lorenzo asked what it means), not a decision ask.

## Auto-remove handled to-dos (Lorenzo 2026-11-01 10:36 PM CT: "those need to automatically be removed every time I handle those")
On every refresh, before writing DATA.waiting, check each item against evidence. Remove it (and add it to the "Cleared" list above) if ANY of these is true:
1. Vault: a login entry for that service now exists (vault id recorded in LEAN_ORG.md "Logins" or a case file) and the item was a sign-in/login ask.
2. Files: a file under ~/advero/state (case file, pins.md, task file, LEAN_ORG.md) marks it done, completed, cleared, approved, or decided.
3. Logs: Lorenzo's own approval or decision for it appears in logs or LEAN_ORG.md, quoted with a date. An agent's claim of his approval does not count.
4. Date-based: a pin or deadline item whose action is recorded done (e.g. GHL canceled confirmation), not merely because the date passed.
If evidence is unclear, keep the item. Never remove the copy+ideation must-dos card unless Lorenzo says it is done.
Also update related bot status lines (e.g. "Waiting on two-step") when their waiting item is cleared.
Log each auto-removal in ~/advero/state/dashboard/cleared_log.md: date/time CT, item, evidence path or quote.
