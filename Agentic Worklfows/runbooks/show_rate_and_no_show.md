# Runbook: booked-call reminders and no-show recovery (Blueprint S4, S5; section 2)

Owner: section 2 (booked calls). Status: rebuilt 2026-09-23, MODE=shadow, nothing live.
Source of truth for every word of copy: `sections/2_booked_calls/copy_signed_off.md`.

## What it is
Email only. No texts, no phone calls, no call or voicemail tasks, no pre-read, never a booking link.

| Piece | File |
| --- | --- |
| Confirmation + reminders R2/R3/R4 | `services/reply_engine/show_rate.py` |
| No-show detection + recovery N1, N3-N8 | `services/reply_engine/no_show.py` |
| In-thread transport | `services/reply_engine/thread_reply.py` |
| Scheduled job | `jobs/appointments_tick.py` |
| Zoom joins (evidence for N1 and detection) | `services/reply_engine/zoom_webhook.py` |

## Every email is a reply in the lead's thread
`thread_reply.send_lead_email` sends each email as a reply in the lead's own Instantly cold-email
thread, from the inbox that wrote to them. `to=` is always the lead, and in live the thread is re-read
so only a confirmed recipient gets the reply.
A GHL email (using the template's subject) is the fallback **only** when the lead is known and has no
thread at all. An unknown, ambiguous or mismatched lead, a broken thread or an unconfirmed recipient
holds the email. It never falls back to GHL. The reply carries "Re: <thread subject>", which the
template gate never saw: `send_lead_email` checks that exact subject against the gate's subject rules
from the same lookup it sends with, and holds (`thread_subject_refused`) on any problem.

## Reminders (show_rate.py)
| Touch | When | Skip rules |
| --- | --- | --- |
| `confirm_email` | T+0, widget bookings (an engine booking's approved reply already confirmed it) | stale booking |
| R2 `reminder_24h_email` | 24 real hours before the call | skipped `booked_late` when already past, when booked less than 6 h before R2's send time (6 h rule), or when R2 would land on a weekend or outside 07:00-19:00 CT (weekend rule) |
| R3 `reminder_morning_email` | 08:30 lead-local on the call day (CT if zone unknown) | only when R2 was skipped; `same_day` when booked on the call day; deferred to the send window, weekdays only; skipped if past or at/after R4 |
| R4 `reminder_1h_email` | 1 h before the call, everyone (confirmed or not) | `past_time` only |

Same-day booking: confirmation + R4 only. Any reply to R2/R3 counts as a yes. A reschedule makes a
new schedule and cancels the old pending touches. One email per call per run: when several are due
at once (a missed tick, a hold that kept R3 pending until R4 came due), only the latest that can
still go is sent and the earlier ones close as `superseded`.

## No-show recovery (no_show.py)
S = scheduled start. "10:00 lead" = 10:00 in the lead's zone (CT when unknown).

| Touch | When |
| --- | --- |
| N1 `ns_still_on_email` | S+3, before the flag. Only with Zoom join data (meeting started or host joined) and no lead join. Once per call, never after S+10 |
| N3 `ns_reschedule_email` | the later of the flag and S+25 min, two fresh slots |
| N4 `ns_d1_email` | next business day, 10:00 lead |
| N5 `ns_d3_value_email` | 3 business days after, 10:00 lead. Skipped (`no_niche_point`) with no niche/offer on file: never a generic line |
| N6 `ns_d7_yes_no_email` | 7 days after, next weekday, 10:00 lead |
| N7 `ns_d14_breakup_email` | 14 days after, next weekday, 10:00 lead, then nurture |
| N8 `ns_third_miss_email` | third miss only, S+25 |

Repeat rules (SOP-005 counter per contact):
- First miss: N1, N3, N4, N5, N6, N7, then `nurture.enroll(no_show_no_rebook)` and stage Follow Up Later.
- Second miss: N1, N3 `.repeat` at S+25, N6 three business days after, then nurture (+ pattern note).
- Third miss: N1, N8 at S+25, then nurture and stage Lost.

Slot emails claim two fresh times the lead was never offered, and give back the previous offer once
they reach the lead, so "those times got taken" is true. N4/N5/N6 go out only after an earlier slot
email in the same ladder reached the lead (else `no_prior_offer`).

Stops: any reply from the lead since the call's start stops the rest (`replied`). A rebooking
cancels it (`rebooked`). A late join reverses the flag (`late_show`).

One email per lead per run: the tick sends ladder emails only in its recovery sweep (never also
inside the per-call check), and the sweep stops at the first email that reaches a lead. A no-show
marked by hand the next morning gets N3 now and N4 on a later tick, never both in one minute.

## Schedules (section 4 owns the schedule file)
| Command | When |
| --- | --- |
| `python3 -m jobs.appointments_tick` | every 5 minutes (full run: reminders, detection, ladder, rebooking scan) |
| `python3 -m jobs.appointments_tick --no-show-watch` | **new, section 4 must add it:** every minute, Mon-Fri 12:00-18:59 CT. Only N1 and detection for calls that started in the last 30 min. It reads GHL only when the store knows of such a call |

Both take one lock, so they never overlap.

## Outcomes (tick digest and Job_Log)
| Outcome | Meaning | Action |
| --- | --- | --- |
| `would_do` | recorded in shadow, nothing sent | review `.tmp/shadow_log.jsonl` |
| `sent` | delivered | none |
| `deferred` | due outside the send window, stays pending | none, goes next window |
| `needs_attention` | thread lookup held it (ambiguous/foreign lead row, broken thread, recipient mismatch, no lead email) | fix the data; it stays pending |
| `maybe_sent` | the write request went out and failed or returned nothing: it may have been delivered | **check the thread or GHL conversation by hand. Never retried automatically** (a retry is a duplicate email) |

## Template approval (nothing auto-sends before this)
Every lead-facing email auto-sends only when its exact text is a template Lorenzo approved with
`jobs/approve_templates.py` and unchanged since (see `runbooks/template_approvals.md`). The new ids
need his approval before anything goes out:
- `show_rate.confirm_email.<niche>_<offer>`, `show_rate.reminder_24h_email`,
  `show_rate.reminder_morning_email`, `show_rate.reminder_1h_email`
- `no_show.ns_still_on_email`, `no_show.ns_reschedule_email`, `no_show.ns_reschedule_email.repeat`,
  `no_show.ns_d1_email`, `no_show.ns_d3_value_email.<niche>_<offer>` (cleaning, bookkeeping,
  recruiting only), `no_show.ns_d7_yes_no_email`, `no_show.ns_d14_breakup_email`,
  `no_show.ns_third_miss_email`

Unapproved or changed text is held, never sent.

## How to run (shadow)
```
cd "Agentic Worklfows"
python3 -m jobs.appointments_tick --dry-run --appointments jobs/tests/fixtures/appointments_2026-09-21.json
python3 -m jobs.appointments_tick --dry-run --no-show-watch --now 2026-09-23T13:03:00-05:00 \
  --appointments jobs/tests/fixtures/appointments_2026-09-21.json --joins joins.json
```
`--dry-run` forces MODE=shadow and NOTIFY=off, and uses `.tmp/dryrun_store.json` unless `--store` is given.

## How to test
From `Agentic Worklfows/`:
`PYTHONPATH=tools/netguard python3 -c "import netguard, pytest, sys; sys.exit(pytest.main(['-q','-p','no:cacheprovider']))"`
Key files: `test_thread_reply.py`, `test_showrate_schedule.py`, `test_no_show_ladder.py`,
`test_showrate_no_show.py`, `jobs/tests/test_appointments_tick_no_show_watch.py`.

## Go-live (Lorenzo only)
1. Approve the template ids above.
2. Zoom on the Discovery Call calendar and `ZOOM_WEBHOOK_SECRET` set (N1 and detection need join data;
   without it detection says `unknown` and nothing is flagged).
3. Section 4 adds the `--no-show-watch` schedule entry.
4. 48 h shadow review of `.tmp/shadow_log.jsonl`, then `MODE=live` + `ALLOW_LIVE_WRITES=1` on the
   tick only, after Lorenzo signs off. Never set by an agent.

## Rollback
Unset `ALLOW_LIVE_WRITES` (or set `MODE=shadow`): everything goes back to `would_do`. Stop one call's
ladder: set `state=done` in `noshow_state:<appt_id>`. Nothing here deletes data.
