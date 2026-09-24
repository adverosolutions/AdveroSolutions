# Section 1: email follow-up after an interested lead goes quiet (plus the 90-day nurture)

## Goal
A lead replies "interested" to a cold email. Lorenzo answers by hand with two call times. If they go quiet, the engine follows up in the same thread until they book, say "not now", or reach the end of the sequence. Leads who don't book go into a 90-day nurture.

## Where it stands (2026-09-23)
- **The engine today** (`services/reply_engine/cadence.py`, `jobs/cadence_tick.py`): a daily ladder of touches d1 to d7, then d14 and d30 (`prompts/cadence_d*.md`, `cadence_d6_noinvite.md`, research line prompt `cadence_research.md`). Every touch passes the template gate: it auto-sends only when its text is exactly a template Lorenzo approved; otherwise it is held (see `runbooks/template_approvals.md`). Nothing is approved yet and nothing is live.
- **Lorenzo's direction (2026-09-23):** the first reply to an interested lead is his own job (he offers two times himself). Booking confirmations stay as they are (section 2). Rewrite only the no-reply follow-up sequence first.
- **His formula:** E1 "those two slots got grabbed, here are two more"; E2 a researched reason the call is valuable for them, two slots; E3 grabbed again, "I really want to get this call on the books"; E4 proof across industries (roofing, software consultancy, lending, wholesalers); E5 haven't heard back, slots keep filling, busy time of year; E6 "still a priority?" or "I put together X for you"; E7 open. About a week of daily emails, then two weeks later "been a couple of weeks", then weekly a couple more times, then a 90-day nurture with a new campaign.
- **The rewrite is drafted:** ten writer agents (one per email, three versions each, brief in `writer_brief.md`, drafts in `drafts/`) and a Fable editor produced `sequence_final.md`: one pick per email E1 to E10, an alternate for each, per-campaign lines for E4, E6 and E9, the E2 research-line rules, and the editor's notes. Checked: no em or en dashes, no "!".
- **Where the conversation stopped:** all ten emails were shown to Lorenzo in chat, with the open questions below. He had not reacted to E1 yet when the work was split into sections.

## Next steps, in order
1. **Walk Lorenzo through `sequence_final.md` one email at a time, starting with E1.** Show the email, take his edits, write them into `sequence_final.md`, commit and push after each sitting.
2. **Get his calls on the open questions** (below).
3. **Only after he signs off, change the engine** (plan the pieces, workers build, reviewer approves each):
   - Schedule: E1 to E7 on business days 1 to 7 after Lorenzo's own reply (day 0), E8 two weeks after E7, E9 and E10 a week apart, then nurture.
   - Replace `prompts/cadence_d*.md` with the new set and retire the ones no longer used (`d6_noinvite`, `d14`, `d30` as the new schedule requires). Template ids in the gate catalogue change with this; tell section 4 the new ids so it re-runs the parity check and rebuilds the Google Doc.
   - E2 research step: fill `{research_line}` per lead using the rules in `sequence_final.md` (facts only from their own site, reviews or listing, tied to the offer, no guessing, a fallback line when nothing solid turns up). Sonnet at runtime; tests mock it (no paid calls).
   - Stop logic: any reply stops the run. A "not now / bad time / not a priority" reply sends the lead to nurture (reason `not_now_reply`). Interest goes to Lorenzo.
   - Make "those slots got grabbed" true: release the previous two holds when new ones go out (slot rules live in `shared/slots.py`, section 4's file; a small `shared:` commit is fine).
   - Start trigger: day 0 is Lorenzo's own manual reply in the Instantly thread. The engine must detect it and must not send a first reply of its own.
   - Update `runbooks/cadence_and_booking.md` (cadence parts) and the tests that change.
4. **Nurture.** Land `services/reply_engine/nurture.py` with `enroll(lead_email, reason, now)` early, as a small reviewed piece pushed to main (section 2 calls it for no-shows who never rebook). Reasons: `no_reply_after_sequence`, `not_now_reply`, `no_show_no_rebook`. Shadow-safe, tested. If it needs a field on `LeadState` (`models.py`), that is an allowed `shared:` commit. The nurture content itself comes later: propose the 90-day plan to Lorenzo (how often, what each touch offers, when it ends, whether it runs in the engine or as an Instantly subsequence), then write it with the sequence method and build it.

## Open questions for Lorenzo
Answered 2026-09-23 (details in `sequence_final.md` and `STATUS.md`): 1 wholesaler line dropped; 2 E2 frame plus research rules approved once, auto-send only when the line passes every check; 3 a "not now" reply stops the run and goes to nurture; 4 E5 kept (with an offer line), "Last one from me this week" kept.
5 (answered): the engine drafts the first reply for him with two held times; he sends it himself. No free times: wait a day, alert after two misses.

## What this section owns (paths under `Agentic Worklfows/`)
- `services/reply_engine/cadence.py`, `prompts/cadence_*.md`, `jobs/cadence_tick.py`
- The first reply: `services/reply_engine/draft.py`, `classify.py`, `prompts/classify_system.md`, `prompts/draft_system.md`, `prompts/escalate_system.md`
- New: `services/reply_engine/nurture.py`, `prompts/nurture_*.md`, `jobs/nurture_tick.py`, `runbooks/nurture.md`
- `runbooks/cadence_and_booking.md` (cadence parts; the booking parts are section 2's), `runbooks/reply_sla_and_approvals.md`
- `sections/1_email_followup/**`

Uses but does not own: the template gate and approval pages (`template_gate.py`, `template_approvals.py`, `approval.py`), `shared/slots.py`, `models.py`: all section 4.

## Files in this folder
- `sequence_final.md`: the editor's final sequence (the thing to walk through).
- `writer_brief.md`: the shared brief every writer got (offers, proof, voice rules). Reuse it as the model for other sequences.
- `drafts/E1.md` to `drafts/E10.md`: each writer's three versions.
- `STATUS.md`: keep current.
