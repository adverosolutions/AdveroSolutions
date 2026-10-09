---
name: nurture-90-day
description: The 90-day nurture for AdveroSolutions leads who are not buying now. Covers who enters (follow-up ladder ran out, a "not now" reply, a no-show who never rebooked), who leaves (re-engaged, booked), what the record holds, how it blocks the daily follow-ups, what is sent and when (nothing yet, the content plan is waiting on Lorenzo), and the open decisions. Use for "nurture", "put them in nurture", "check back in a few months", "not now leads", "who is in nurture", "nurture touch due".
---

# 90-day nurture

A lead who is not buying now is not dropped. Nurture keeps them on a slow 90-day track so they hear from Lorenzo again later, instead of more daily follow-ups or nothing at all.

**Status (2026-09-24): enrollment and exit are built and wired, in shadow. No nurture email exists and nothing sends from nurture.** The content plan is waiting on Lorenzo.

Who does what (2026-09-25; see `grok-operator`): when nurture emails exist, the engine timer wakes Grok when a nurture touch is due, Claude Opus 5.5 decides whether it goes and returns the approved template text, and Grok sends exactly that. Until approved nurture templates exist, there is nothing to send: Grok must not write a "checking back in" email on its own, and neither may Opus invent one.

## Who enters, and why

| Reason | Set by | When |
|---|---|---|
| `no_reply_after_sequence` | the quiet-lead follow-up (`quiet-lead-followup`) | E10 went out and the lead never answered. The lead also moves to GHL Follow Up Later |
| `not_now_reply` | the quiet-lead follow-up | The lead answered a follow-up with "not now", "bad time" or "not a priority". GHL Follow Up Later, Instantly interest -1 |
| `no_show_no_rebook` | the no-show recovery (`booked-calls`) | The recovery ladder ended with no reply and no rebooking: after N7 on a first missed call (stage Follow Up Later), after N6 on a second, after N8 on a third (stage Lost) |

No other reason is accepted.

## Who leaves, and why

| Reason | When |
|---|---|
| `re_engaged` | Lorenzo's own reply to a nurtured lead is found in the thread (day 0 of a new follow-up ladder). Wired |
| `booked` | The lead books a call. Accepted, but nothing calls it yet |

Leaving sets the record to `left` with the time and reason. A lead who left and is enrolled again later starts a fresh 90 days and keeps the old history.

## What the record holds

One record per lead email (trimmed, lowercased), separate from the lead's main record:
- `status`: `active` or `left`
- `reason`: the reason that started this enrollment
- `enrolled_at`, and `ends_at` = 90 calendar days later at the same Central clock time
- `campaign_id`
- `events`: one per reason (reason, time, campaign, note)
- `touches`: empty, reserved for the nurture emails

Safe to call twice: enrolling an active lead again changes nothing (a different reason adds one event; the same reason adds nothing), so a retried job cannot pile up records or restart the 90 days.

## What nurture does to the other sequences

- On every tick, before any follow-up can send, an enrolled lead's follow-up ladder stops with reason `nurture`. It cannot be resumed while the lead is enrolled, and an out-of-office pause is not resumed either.
- If the nurture record cannot be read, the lead is held that tick, never sent to.
- Enrolling sends nothing, calls no outside system and only writes the engine's own store, so it is safe in shadow.

## What is sent, and when

Nothing yet. Known inputs for the plan:
- E10, the last follow-up, tells the lead "I'll give you some room and check back in a few months." The sequence notes say that line assumes the first nurture touch lands about 90 days out; if nurture emails sooner, E10's wording changes.
- Section 2's no-show research: the first nurture touch no sooner than 3 to 4 weeks after the hand-off, or on the date the lead named. For bookkeeping and tax firms, keep nurture out of filing-deadline weeks (March 15, April 15, September 15, October 15).
- Lorenzo's original formula (2026-09-23): "then a 90-day nurture with a new campaign."
- A "not now" with a date ("check back in January") already creates a dated GHL follow-up task (30 days when no date is given).

Questions Lorenzo has to answer before anything is written (section 1, "Waiting on Lorenzo"):
1. How often a nurtured lead hears from us in the 90 days.
2. What each touch offers.
3. What happens when the 90 days end.
4. Whether it runs in the engine or as an Instantly subsequence (Lorenzo's formula mentions "a new campaign").

Once answered, the emails get written with the same method as the E1 to E10 ladder (drafts, one pick per email, walked through with Lorenzo one at a time), then added to the emails doc for his "done". Every rule in `cold-email-replies` and `quiet-lead-followup` applies: no links, no prices or guarantee figures, no Claudeisms, same thread and inbox, 07:00 to 19:00 CT, approved text only.

## Rules that already hold for any future nurture email

- A lead whose "not now" set the opt-out marker still carries it inside nurture. The nurture sender has to decide what that means before it sends to them (open question).
- Never send to a lead who unsubscribed, was hostile, said not a fit or wrong person, or is blocklisted.
- Any reply from a nurtured lead goes through `cold-email-replies` like any other reply.

## Gaps

- No nurture emails, no nurture tick, no send path.
- Nothing calls `leave(booked)`, so a lead who books from outside the follow-up ladder stays marked active.
- Nothing ends a nurture after 90 days: `ends_at` is recorded but not acted on.
- A "not now" as the very first reply (ladder never armed) enrols the lead nowhere.
- After `leave`, a lead whose status is still Follow Up Later can be enrolled again on the next tick (guard needed before `leave` gets more callers).
- A lead enrolled between the tick's check and a send still gets that one send.
- The old contractor SOP ("If no movement after Day 14, Nurture (follow up in 30 days)") predates this build and is not the plan.

## Sources (for maintainers)

- `Agentic Worklfows/runbooks/nurture.md` (2026-09-23; its "no callers of leave yet" is superseded by the day-0 detection of 2026-09-24)
- `Agentic Worklfows/services/reply_engine/nurture.py` (REASONS, LEAVE_REASONS, NURTURE_DAYS 90) on origin/main (ba39a0c, 2026-09-24)
- `Agentic Worklfows/services/reply_engine/cadence.py` (enroll on E10 and not-now, `nurture.leave(re_engaged)` in day-0 detection), `no_show.py` `enroll_nurture`
- `Agentic Worklfows/sections/1_email_followup/README.md`, `STATUS.md` (2026-09-24), `sequence_final.md` (E10 note)
- `Agentic Worklfows/sections/2_booked_calls/STATUS.md`, `research/no_show_recovery.md`; `runbooks/show_rate_and_no_show.md`
- `Agentic Worklfows/MASTER_SOP.md` line 347 (legacy)
- Memory `grokbot-orchestrator.md` (2026-09-25)
