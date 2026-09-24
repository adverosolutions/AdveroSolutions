# Section 2 status

**2026-09-23:** research done for both sequences; Lorenzo picked both cadences; messages are being written (writers + editor). No engine code changed yet. Nothing approved or live.

## Lorenzo's decisions (2026-09-23)
1. **Reminder cadence: the recommended one** (`research/reminder_cadence.md`, section 1):
   - "Locked in" booking confirmation unchanged.
   - R1 pre-read: +15 min after booking when the call is 0 to 2 days out; about 48 h before when 3+ days out. Adds a "best cell if either of us is running late?" ask.
   - R2 day-before check at -24 h, a plain question instead of "Reply C"; any reply counts as confirmed. R3 morning-of (08:30 lead time) instead when booked after the 24 h mark; none for same-day.
   - R5 at -4 h if no reply since booking: task for Lorenzo to call, voicemail, text by hand.
   - R4 one-hour email with the link, to everyone (email-only phase).
   - Texts (after A2P): 1 h text only to the unconfirmed, 15 m text with the link to everyone. Copy for texts comes later.
2. **SMS: email-only now.** After A2P, text only numbers the lead gave (the "best cell" answer); scraped numbers are a TCPA risk.
3. **Zoom: connect it** (Lorenzo's action in GHL). Without it, `no_show.detect` returns `unknown` on Meet and the ladder starts only when he marks the no-show by hand.
4. **Reminder and no-show emails go as replies in the cold-email thread**, same inbox; a GHL email only when the lead has no thread. (Today they go as new GHL emails.)
5. **No-show cadence: the recommended one** (`research/no_show_recovery.md`): N1 "I'm on" email at S+3; N2 Lorenzo calls at S+5 to S+8 (task at S+3); N3 reschedule at about S+25 with two times; N4 next business day; N5 day 3-4 niche point; N6 day 7 still/later/not a fit; N7 day 14 close-out, then `nurture.enroll(lead_email, "no_show_no_rebook", now)`. Second no-show: N1, N2, N3 link-only variant, N6 on day 3-4, then nurture. Third: N1 then N8 sign-off, then nurture. Any reply stops the ladder.
6. **Two times** in every reschedule email (not three).

## Done
- Worktree `.worktrees/2`, branch `section/2-booked-calls`.
- Research: `research/reminder_cadence.md`, `research/no_show_recovery.md`.
- Writer brief: `writer_brief.md` (both sequences).
- Reminder drafts R1 to R5 (`drafts/`).

## In progress
- Editor pass on R1 to R5 -> `reminders_final.md`.
- Writers N1 to N8 (`drafts/`), then an editor pass -> `no_show_final.md`.
- Scout mapping the code changes (show_rate / no_show / appointments_tick, in-thread sending, template ids).

## Findings that shape the build
- `shared/slots.pick_two` already offers the earliest open slot first.
- `app.py` (section 4) already spots confirmation replies in the Instantly thread and calls `show_rate.mark_confirmed`; the in-thread send can reuse the path the "Locked in" reply uses.
- The no-show +3 min nudge needs Zoom join events and a tick that runs near S+3 (the tick runs every 5 to 10 min today).

## Next
1. Walk Lorenzo through the reminder set one message at a time; then the no-show set.
2. After his sign-off: build (worker-heavy), review, tests, runbook; tell section 4 the new and changed template ids.

## Waiting on Lorenzo
- Connect Zoom in GHL (his action; the no-show +3/+5 steps depend on it).
- Sign-off on each message (walkthrough next).

## For section 1
- `nurture.enroll(lead_email, "no_show_no_rebook", now)` is called after N7 (day 14), after N6 on a second no-show, after N8 on a third. The research suggests the first nurture touch is no sooner than 3 to 4 weeks after the hand-off.
