# Section 2 status

**2026-09-23 (split day):** booking, show-rate reminders, no-show recovery and pre-call prep are built and tested in shadow; copy was fixed on 2026-09-22. Nothing is approved or live.

## Done
- Worktree `.worktrees/2`, branch `section/2-booked-calls`.
- Reminder-cadence research: `research/reminder_cadence.md` (25 sources; healthcare trials marked as extrapolation). Recommendation is in "Waiting on Lorenzo" below.
- Writer brief drafted: `writer_brief.md` (shared parts; "The sequence" is filled after Lorenzo picks the cadence).

## In progress
- No-show recovery research (`research/no_show_recovery.md`), running in parallel so step 3 does not wait on step 2.

## Findings that shape the plan
- The two times the engine offers already start with the earliest open slot (`shared/slots.pick_two`), so "offer the nearest slots first" (the research's biggest lever) is mostly in place.
- On Google Meet there is no join telemetry: `no_show.detect` returns `unknown` and Lorenzo gets a "mark it by hand" task. Any "they have not joined" touch, and the whole no-show ladder, starts only with Zoom connected or after he marks the no-show.
- The engine's "Locked in" confirmation (Lorenzo: leave it) has no agenda and no question; the pre-read at +15 min carries the agenda today.
- Show-rate emails go out through GHL as new emails, not in the cold-email thread.
- Texting consent: most phone numbers were scraped, not given by the lead (TCPA/A2P risk).

## Next
1. Walk Lorenzo through the reminder cadence; take his picks.
2. Fill "The sequence" in `writer_brief.md`, run the writer + editor agents, walk him through each message.
3. Same for the no-show sequence once its research lands.

## Waiting on Lorenzo
1. Reminder cadence (recommended version in chat, 2026-09-23).
2. SMS: email-only first, or wait for A2P?
3. Google Meet or Zoom?
4. Reminder emails: new email from GHL (today) or reply in the cold-email thread?
