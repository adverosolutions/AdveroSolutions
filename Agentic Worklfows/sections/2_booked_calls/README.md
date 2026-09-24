# Section 2: booked calls (confirmation, pre-call reminders, no-show recovery)

## Goal
Once a lead books, get them to show up. If they don't show, get them rebooked. If they never rebook, hand them to the 90-day nurture (section 1).

## Where it stands (2026-09-23)
- **Booking** (`services/reply_engine/booking.py`): the engine books from replies and sends the confirmation ("Locked in ..."). Lorenzo, 2026-09-23: the booking confirmations are fine, leave them.
- **Show-rate** (`show_rate.py`, driven by `jobs/appointments_tick.py`): today's `SEQUENCE` is confirmation email and SMS at booking, a pre-read email 15 minutes after booking (per offer, `prompts/show_rate_preread_*.md`), SMS and email 24 hours before, a task for Lorenzo 4 hours before if unconfirmed, SMS 1 hour before, SMS 15 minutes before. SMS waits on A2P registration (Lorenzo's item). Calls run on Google Meet today; messages say "call link", not Zoom.
- **No-show** (`no_show.py`, attendance via `zoom_webhook.py`): 10-minute grace, then "still on?" SMS and email at +5 minutes, a call task for Lorenzo at +10 minutes, reschedule email at +1 hour, other-channel SMS day 1, value email day 3, yes/no email day 7, breakup email day 14.
- **Pre-call prep for Lorenzo** (`precall.py`, `proposal.py`, `jobs/precall_tick.py`, `prompts/precall_*`, `prompts/proposal_*`): an internal brief and one-call-close prep. It never goes to the lead. Built and tested; no work planned.
- The copy passed a word-by-word check on 2026-09-22 (am/pm on times, "call link", no "send the numbers in writing"). Like every engine email, nothing sends until Lorenzo approves the templates.
- **Decision already made:** when the engine's own booking confirmation goes out, the separate show-rate confirmation email and SMS are skipped for that call; the pre-read still goes.
- **Known nits:** the 15-minute reminder says "Hopping on now" 15 minutes early; one example in the Google Doc's booking section ("beyond_horizon") contradicts itself (the template text is fine).

## Next steps, in order
1. **Research the reminder cadence** Lorenzo asked for: what cuts no-shows for a 15-minute call booked by a cold B2B lead (owners of cleaning, bookkeeping and recruiting firms). Cover timing (48h, 24h, morning of, 1h, 15m or 5m), email vs SMS, confirm-by-reply asks, and what to cut. Web research with sources, then one recommendation compared with today's `SEQUENCE`.
2. **Walk Lorenzo through the recommended cadence**, then write the messages with the sequence method (`../README.md`: a writer per message, an editor, then one message at a time with Lorenzo in chat).
3. **Then the no-show sequence**, the same way: research what gets no-shows rebooked, propose, write, walk through.
4. **Apply the changes after his sign-off:** `show_rate.py` / `no_show.py` schedules and prompts, `jobs/appointments_tick.py`, tests, runbook. No-shows who never rebook call section 1's `nurture.enroll(lead_email, "no_show_no_rebook", now)`; if it hasn't landed on main yet, code against that signature and note it in `STATUS.md`. Tell section 4 the new or changed template ids so it re-runs the parity check and rebuilds the Google Doc.

## Open questions for Lorenzo
1. Which reminder cadence (after the research)?
2. SMS: wait for A2P, or ship email-only reminders first?
3. Keep Google Meet, or connect Zoom (optional, his action in GHL)?

## What this section owns (paths under `Agentic Worklfows/`)
- `services/reply_engine/booking.py`, `show_rate.py`, `no_show.py`, `zoom_webhook.py`, `precall.py`, `proposal.py`
- `prompts/show_rate_*`, `prompts/precall_*`, `prompts/proposal_*`, and any new `prompts/no_show_*`
- `jobs/appointments_tick.py`, `jobs/precall_tick.py`
- `runbooks/show_rate_and_no_show.md`, `runbooks/precall_and_proposal.md`, `runbooks/cadence_and_booking.md` (booking parts; the cadence parts are section 1's)
- `sections/2_booked_calls/**`

Uses but does not own: `nurture.py` (section 1); the template gate, approval pages, `models.py`, `shared/`: section 4.
