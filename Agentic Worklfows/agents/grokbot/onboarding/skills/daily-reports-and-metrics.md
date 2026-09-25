---
name: daily-reports-and-metrics
description: What Lorenzo wants reported and how. Field-by-field specs for the morning report (07:30 CT), evening report (18:30 CT), the Daily Metrics tracker row and DAILY UPDATE block, the 13-row KPI dashboard with thresholds, the Friday retro packet, campaign verdicts and experiments, and the pipeline sweep, with where every number comes from. Use for "morning report", "evening report", "daily update", "log today's metrics", "KPI", "how are the campaigns doing", "Friday retro", "verdicts", or when building anything that reports numbers.
---

# Daily reports and metrics

Grok Bot sends the reports. The numbers come from read-only pulls and from the
engine's own log. Grok does not write the analysis text of a report that goes
public (the Skool post, the retro draft); those come from the jobs or from
Opus, and Lorenzo posts them himself.

## Rules for every number

1. **Unmeasured is `n/a`, never 0.** A zero in the tracker reads as a real zero
   day and skews every average and the streak.
2. **A measured 0 never overwrites a number Lorenzo typed** (Calls Booked,
   Calls Held, Positive Replies, Proposals Sent, Closes). Keep his number and
   say so in the notes.
3. **Never backfill a missed day.** Write today's row only. A gap is a note.
4. **Say the window.** A row's window is the window its value was computed
   over. Don't put one day's positives over a week's sends.
5. **Positives are distinct leads**, not reply events.
6. **Real reply rate is `unique_replies / sent`.** Never subtract
   `unique_replies_automatic`; it is a separate bucket, not a subset.
7. **GHL dates come from `lastStageChangeAt`** (plus `lastStatusChangeAt` for
   Won and Lost). Never `updatedAt`: an edit is not a stage change.
8. **Times are CT.** Convert UTC stamps before taking the date.
9. **Public push cards carry counts and first names only.** Anything with an
   `@`, a company or a client's words goes by email, not on the public ntfy
   topic (unless the topic is protected with a token).
10. **Lower is better** for bounce rate, time to first reply, Upwork response
    time and cost per verified lead. Write thresholds with the direction
    (`<= 1.0%`, `> 2.0%`).
11. Messages to Lorenzo follow the `claudeisms` rule.

## Morning report, 07:30 CT weekdays

In this order:

| Section | Fields | Source |
|---|---|---|
| Waiting on Lorenzo | ordered list: booked calls in the next 24 h not confirmed, then positive replies with no answer from him (overdue at 24 h), then proposals untouched 7 days, then Upwork rooms awaiting him (overdue at 1 h). Inside a kind: pipeline value, then oldest wait / soonest start | the pipeline sweep (Instantly received and manual emails, positive lead filters, engine store `appointment:*`, `confirmed:*`, `proposal:*`, GHL Proposal Sent, the Upwork rooms handoff) |
| Overnight replies | each reply, its category, and what was done (sent, held, no action) | engine log / `decide` results |
| Hold cards waiting | lead, template id, why held | engine |
| Today's calls | time CT, lead first name, company, confirmed yes/no | GHL Discovery Call calendar + engine appointments |
| Touches due today | count by type (follow-up, reminder, no-show step, nurture) | engine timers |
| What is off | every KPI row in `watch` or `ALERT`, with its value and threshold | KPI dashboard |
| Failures | failed sends after retry, failed jobs, sync conflicts | Job_Log rows with status outside the healthy list |
| Health | inboxes not status 1, warm-up under 98, bounce spike | deliverability monitor (07:00) and inbox inventory (07:00) |

At 07:30 no emails have gone out yet, so "Sends/day vs plan" uses the last day
that finished and says so.

## Evening report, 18:30 CT weekdays

| Section | Fields | Source |
|---|---|---|
| Sent today | by type: cold, follow-up, booking, reminder, no-show; and cold sends vs plan | Instantly daily account analytics; engine log |
| Replies | total, then a count for each of the engine's 11 classifier labels, by label name: `positive_interested`, `positive_question`, `positive_referral`, `neutral_question`, `negative_notnow`, `negative_notfit`, `negative_hostile`, `unsubscribe`, `ooo`, `wrong_person`, `auto_reply_unmonitored` (a label with 0 shows 0) | engine classification log |
| Calls | booked, held, no-showed today | engine `appointment:*`, `noshow_state:*`; GHL |
| Upwork | messages waiting on Lorenzo, with the room and hours waiting | Upwork rooms handoff |
| Stuck | anything held, failed or not confirmed | Job_Log |
| DAILY UPDATE block | the block below, from the 18:00 metrics run | daily metrics job |

The 18:00 run is before sending stops at 19:00, so the next evening restates
yesterday's send count with the finished day (only for a row that was logged).

## The Daily Metrics tracker

Google Sheet "AdveroSolutions - Daily Metrics", id
`1GuJBW_FSZJsJZ9gmN37EmTGo65DH695BtwhFkBXWDj0`. Tabs: Daily Update, Daily
Progress, Dashboard, Daily Log.

Daily Log has 400 pre-filled date rows from 2026-08-03 in row 2. Writing a day
updates that date's row (found by reading column A unformatted); it never
appends. Write range is columns B to Y (23 metrics plus Notes). Column Z
("Logged") is a formula that drives the streak: never write it.

| Column | Kind | Where it comes from |
|---|---|---|
| Upwork Proposals, Connects Spent, Upwork View Rate, Upwork Reply Rate, Upwork Hires | flow / rate | the Upwork daily handoff (`date` required; a file for another day or with no date is ignored) |
| Cold Emails Sent | flow | Instantly `GET /accounts/analytics/daily`, summed over active inboxes |
| Email View Rate | rate | **never written**: open tracking is off on every campaign |
| Email Reply Rate | rate | `unique_replies / sent` for the day |
| DMs Sent, DM View Rate, DM Reply Rate | flow / rate | Lorenzo types them |
| Community Posts, New Communities Joined | flow | Lorenzo types them |
| Replies | flow | Instantly `unique_replies` |
| Positive Replies | flow | reply engine classification rows labelled positive, per lead, only on a day the classifier ran |
| Calls Booked, Calls Held | flow | engine `appointment:*` (`booked_at`) and `noshow_state:*`, only when the booking machinery left a trace |
| Proposals Sent, Closes | flow | GHL opportunities whose stage changed that CT day; blank until the GHL token exists |
| Cash Collected, New MRR | flow | Lorenzo types them |
| Total MRR, Active Clients | stock | Lorenzo types them; an empty cell carries the last value forward for the render only |
| Notes | text | run notes (gaps, kept values, restated days) |

Dashboard rates: Reply Rate (Replies / Cold Emails Sent), Positive Reply Rate
(Positive / Replies), Outreach to Call Booked, Show Rate (Held / Booked), Close
Rate (Closes / Held). Connects are priced at $0.15 in the Dashboard's J2 cell.

As of 2026-09-22 the last logged day was 2026-08-12 and the streak was 0.

### The DAILY UPDATE block

Rendered by code from the numbers (no model writes it). Every section prints
every day, even at zero, and unmeasured values print `n/a`:

```
📊 DAILY UPDATE  |  Tue, Sep 22, 2026  |  Day N  |  🔥 N day streak

⚡ UPWORK
   • N proposals sent  →  N total
   • N connects ($x.xx)  →  $x.xx all-time
   • View rate x%  ·  Reply rate x%

📧 EMAIL
   • N sent  →  N total
   • Open n/a  ·  Reply x%

💬 DMs / 🌐 COMMUNITY / 📞 PIPELINE / 💰 REVENUE  (same shape)

Lorenzo
```

No em dash in the header (the separator is ` | `). A block with an em dash, an
exclamation mark, or any mention of AI, automation or a model name is blocked.
It is staged as the Maker School post and never posted automatically: it is
public writing under his name, and Lorenzo posts it.

## KPI dashboard (13 rows)

| Metric | Green | Alert | Window | Source |
|---|---|---|---|---|
| Sends/day vs plan | >= 90% | < 80% | today (scaled to the elapsed send window after 25% of it) | Instantly daily analytics; plan = active inboxes x 25 |
| Warm-up health per inbox | >= 98 | < 98 | now | warm-up analytics; names every inbox under 98 |
| Bounce rate | <= 1.0% | > 2.0% | 7 days | accounts analytics; names the worst inbox |
| Real reply rate | >= 1.0% | < 1.0% | 7 days | accounts analytics |
| Positive reply rate | >= 0.7% | < 0.5% three days running | 7 days | engine classifications |
| Time to first reply | <= 5 min | > 60 min | today | engine: lead reply time to our send time, first replies only |
| Positive to booked | >= 50% | < 40% | 7 days | engine bookings / positives |
| Show rate | >= 90% | < 80% | 7 days | appointment status |
| No-show rebooked | >= 40% | < 25% | 7 days | engine no-show records |
| Proposal to close | >= 30% | < 20% | 7 days | not implemented: reads `no data` |
| Upwork reply rate | >= 15% | < 8% | 7 days | Upwork handoff |
| Upwork response time | <= 1 h | > 4 h | now | rooms handoff (degrades to `no data` if older than 6 h); names the room |
| Cost per verified lead | <= $0.02 | > $0.04 | last run | list factory ledger |

States: `green`, `watch`, `ALERT`, `no data`. A row with no source is `no data`,
never green. Trend says "better" or "worse", not up or down. Under the table,
a per-campaign breakdown of the day.

## Weekly

**Friday 16:00 CT, retro packet.** Reads Instantly, GHL, git log, the Job_Log,
staged Fireflies daily briefs and a Rize export. Sections: funnel (sent,
replies, real reply rate, positives, booked, held, closes, proposals,
revenue), per-campaign table, lifetime verdict lines, three lessons, three
bets, wins and objections from calls, hours by category, system changes, what
the machine did, and "Read this before you trust a number". One Opus call a
week. A lesson must name a metric that moved (quoting its value), a cited
cause, and one action with an owner and a number or date; generic advice is
rejected. Lorenzo edits it for ten minutes and posts the Skool draft himself.

**Friday, campaign verdicts (run by hand).** Per campaign:

| Sends | Positives | Verdict |
|---|---|---|
| < 1,000 | any | keep running |
| >= 1,000 | 0, recruiting | retire |
| 1,000-1,999 | 0, other niches | rework copy |
| >= 2,000 | 0 | retire |
| 1,000-2,999 | >= 1 | run to 3,000 |
| >= 3,000 | rate >= 0.7% | scale |
| >= 3,000 | 0.5-0.7% | hold |
| >= 3,000 | < 0.5% | rework copy |

A positive is a lead that ever reached a positive status (lost and no-show
count). Zero positives with open opportunities is a data check, never a
retirement. The job proposes; retiring a campaign is a change-set Lorenzo
approves. Experiments (`config/experiments.json`): a variant is judged only at
500 sends per arm, then a two-proportion z-test (p < 0.05). EXP-001a and
EXP-001b are planned (B arms not live); EXP-002 is blocked.

**Friday 19:15 CT, client scorecards.** One page per active client; Lorenzo
sends them by hand.

## Daily jobs behind the numbers

| Time CT | Job | Output |
|---|---|---|
| 06:00 | pipeline sync (GHL stage to Instantly interest status) | changes, conflicts |
| 07:00 | deliverability monitor, inbox inventory | health card, proposed inbox actions |
| 07:30 | pipeline sweep | the "waiting on Lorenzo" list |
| 18:00 | daily metrics | tracker row, DAILY UPDATE, KPI dashboard |
