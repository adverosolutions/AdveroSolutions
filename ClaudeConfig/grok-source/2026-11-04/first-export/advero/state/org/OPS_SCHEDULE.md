# Standing ops schedule (rewritten 2026-10-27 10:30 PM CT, ops cleanup)
Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file.
Sources: Lorenzo t1331u-t1338u and t1342u (2026-10-27 evening, COO chat). Replaces the 2026-10-22 9 PM version (backup: OPS_SCHEDULE.md.bak-20261027-cleanup). All times America/Chicago. Sunday is a rest day.

## Chain of command
- Bots reach Lorenzo only through COO. No bot sends Lorenzo status notes in its own chat; a bot replies there only if he messages it first. Exception: the Reminders bot delivers his pins directly (his ask).
- Branch bots report to their manager; managers report to COO. Room posts in team chats are fine.
- Branch morning summaries (Lead Gen, Cold Email, LinkedIn, Upwork) are files only. A manager messages COO only for a blocker. COO reads the files at the roll-up.
- Rules live in ~/advero/state/org/LEAN_ORG.md; it wins over this file. This file holds timing and routing only.

## Lorenzo's day (in order; open to goal: finish early once KPIs are hit)
1. Upwork block, from about 7:30 AM. Lorenzo scrapes Vollna himself each morning and sends COO the jobs he wants demos for. Demo Builder builds only those jobs. Target 3 to 6 proposals a day, each with a demo, each boosted with 70 Connects. Lorenzo sends every proposal himself. The block ends at 3 proposals logged or when he says "Upwork done".
   - No automated Vollna scrapes, pick lists or nightly Upwork prep. Old demos, past leads and past scrapes may be deleted (t1342u). If Lorenzo later hands Vollna scraping back to the Upwork team, his manual process is the template.
2. LinkedIn: Lorenzo works connection follow-ups and approvals.
3. Communities: approval cards, one at a time.
4. Cold email monitoring and deep work (a couple of hours).
5. Calls 12 to 6 PM CT, Zoom only (Tuesday or Thursday preferred).
Cold email monitoring runs all day on its own and is not part of the focus order.

## During the Upwork block (focus rule)
Only urgent items reach Lorenzo: a hot or positive reply, a call request, a blocked channel or login, a client message. Everything else waits for the post-Upwork batch (roll-up).

## LinkedIn
- Connection requests go out automatically 10 AM to 12 PM CT, 25 a day, Mon-Sat, through linkedin_gate, with a segment mix: PPC owners, pest owners and local service owners (not all PPC). Drop to 20 a day at the first LinkedIn warning.
- Weekdays 9:55 AM to 12:00 PM the gate is reserved for the Setter's connect sends.
- Accept handling and first messages to new connections: drafted from approved copy, ask-first cards via COO, then sent.
- Cold email and LinkedIn are separate: a no on cold email doesn't stop LinkedIn outreach.

## Cold email
- Monitored nonstop: Instantly reply webhook, plus Cold Email Manager's 10-minute backup poll.
- Sends to leads only 7 AM to 7 PM CT. Overnight replies queue in state/overnight_reply_queue.jsonl and are delivered at 7 AM. Positive replies: URGENT in COO chat within 5 min; complaints to COO right away (LEAN_ORG H).

## Communities
- Community Manager's "Community pull 8, 12, 4" (Mon-Sat) wakes Community Engagement Bot. It is the only scan trigger.
- Replies and DMs check from people who already engaged, hourly 8:30 AM to 6:30 PM, silent when nothing is new.
- Drafts reach Lorenzo as one card each through COO, batched after his Upwork and LinkedIn work (COO 11 AM fallback).

## COO routines
| Routine | When (CT) | What |
|---|---|---|
| Upwork-first morning agenda | 7:30 AM daily | Opens with Upwork: "send me today's Vollna jobs for demos"; 3 to 6 proposals, 70 Connects each; everything else held |
| Community batch fallback | 11 AM | Sends held community cards if Lorenzo hasn't reached communities yet |
| Roll-up (fallback) | after the Upwork block, 12 PM at the latest | Reads branch summary files; one batch of held non-urgent items |
| Upwork KPI check | 12 PM | Proposals logged vs the 3 to 6 target |
| Hourly leak sweep | hourly 8 AM to 6 PM | Reads RevOps leak audit and Cold Email review; obeys the focus rule |
| LinkedIn and Community watchdog | 8 AM and 5 PM | Morning problems go to LinkedIn Manager or Community Manager, reaching Lorenzo only after the Upwork block |
| Evening login check | 6 PM daily | Security and login health |
| Instantly reply webhook | event | Reply intake (Cold Email Manager runs the backup poll) |
| One-offs | as set | Times-refresh check Marco (Wed 10/28 10:30 AM, follows the focus rule); Cancel Fireflies reminder (10/29) |

## Other bots' timed routines (summary; role docs are the source)
- Revenue Operations: CRM sheet live sync (every 30 min after the cleanup), Dashboard sheet refresh (hourly :05, 7 AM to 10 PM), stalled leads flag 7:45 AM weekdays, leak audit 7:50 AM weekdays, nightly close, nightly sprint row 9 PM Mon-Sat. PandaDoc watch for Leonardo (GDL), pandadoc-watch-leonardo-signed, every 30 min 8 AM to 6:30 PM Mon-Sat: taken over from COO 2026-10-27 12:45 PM CT. RevOps sends every alert and card to COO with priority and preps the post-sign links; COO sends them under Lorenzo's 10:41 AM CT pre-approval. Log: clients/gdl-herrera.md.
- Cold Email Manager: backup poll every 10 min; daily leak review 8:00 AM weekdays. Deliverability: 7:35 AM and 5 PM cards, live watch. Appointment Setter: stalled leads decision 8:15 AM weekdays, per-call reminder one-shots.
- Upwork Manager: Upwork check (hourly, proposal rooms) Mon-Sat; Adrilani follow-up cadence 9:32 AM Mon-Sat. Upwork Coordinator: daily split-test stats check about 6 PM (folded from the removed Upwork Split Test Bot, 2026-10-30).
- LinkedIn: Setter connect list 6:45 AM, auto connect send 10 to 12, accept passes; LinkedIn Manager accept watch, 6 PM leak review, Sunday counts. Sales Nav Bot: queue fill about 6 AM weekdays.
- Lead Gen: 7:10 AM count and runway file; QuickEnrich nightly Sun-Thu 11:10 PM; Maps nightly Sun-Thu 1 AM.
- Accounting: Monday 9 AM spend and Connects check; trial cancel reminders 11/19 and 12/14.

## Removed in this rewrite
Automated Vollna scrapes at 8/10/12/4 and picks after each scrape; Nightly Upwork prep (9 PM); morning sales-first agenda at 8 and 10 AM; morning roll-up at 9:15 AM; COO Instantly backup poll (moved to Cold Email Manager); times-refresh one-offs for Angela, Laura and Debby (fired 10/27).

## Interested-lead daily follow-up rule (Lorenzo, 2026-10-27 10:21 AM CT call)
- Any cold email lead who sends an interested reply gets followed up every day, starting the day after the reply, until they book a time or clearly decline.
- COO routine interested-lead-daily-follow-up runs Mon-Sat around 9:00 AM CT (Sunday is the rest day). It lists every interested lead who isn't booked and hasn't declined, and Appointment Setter preps each day's follow-up card.
- Send rules: LEAN_ORG.md E and F (approved follow-ups now send without cards, 2026-10-30).


## History
- (2026-10-22 audit) Approvals: one register, state/approvals.jsonl. Rules in org/APPROVALS.md. A yes on a call with COO counts like a yes in COO chat (Lorenzo 9:22 PM).
- (2026-10-22 audit) Overnight reply queue is now built: the backup poll writes state/overnight_reply_queue.jsonl when run outside 7 AM to 7 PM or on Sunday; bin/overnight_reply_queue.py handles classify and 7 AM delivery.
- (2026-10-22 audit) Webhook checked: reply_received hook is active (status 1) and points at the COO automation webhook. The poll now records that address correctly.
- (2026-10-22 audit) Heartbeat: bin/heartbeat.py with slots in org/routine_expected.json; COO checks hourly.
- (2026-10-22 audit) Schedule conflicts: Vollna CLOSED 2026-10-23 8:50 AM CT (Vollna Bot sweep retimed to Mon-Sat 7:50/9:50/11:50/3:50 CT, cron 50 7,9,11,15 * * 1-6; Upwork Manager scoring at 8:20/10:20/12:20/4:20). Community scans CLOSED 2026-10-23 8:05 AM CT (Engagement Bot scan retimed to Mon-Sat 7:45/11:45/3:45 CT, cron 45 7,11,15 * * 1-6, lateMinutes 0; COO ping at 8/12/4 is the only trigger for drafts to COO).

## 24/7 autonomous ops (2026-10-30 2:00 PM CT)
Rules: LEAN_ORG.md section F. Schedule changes: interested-lead daily follow-up and post-proposal runner SEND approved steps (no cards); Instantly reply webhook triggers Day 1 times email + URGENT COO chat message within 5 min; hourly leak sweep adds paused-routine check (due within 24h) and "delivered = COO chat only"; new COO evening list ~6:30 PM CT daily. Sends still only 07:00-19:00 CT.
