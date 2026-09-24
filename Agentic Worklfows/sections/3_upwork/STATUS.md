# Section 3 status

**2026-09-23 (split day):** Lorenzo's new voice rule (no Claudeisms, normal capitalization) is in `sections/README.md`, his global CLAUDE.md and a `claudeisms` skill.

**Earlier on 2026-09-23:** the follow-up pipeline and price guard are committed and tested. One real read-only run is done (drafts only). Not scheduled yet. The GHL Upwork pipeline doesn't exist yet (Lorenzo creates it).

## Done 2026-09-23
- **Touch walkthrough** with Lorenzo: all 9 prompts agreed (`walkthrough.md` has every decision and sample).
- **Prompts updated** (reviewed, APPROVE twice): normal capitalization; the no-Claudeisms rule; T3 hints at a similar past client (no name, no figures, a plain-words line on what was built is fine); no touch repeats a result the proposal already states (reply only when asked). All 9 agreed samples pass the copy gate.

## Next
0. **Watch trigger: reviewed and committed (2026-09-23, APPROVE on round 2).** Drafts now come when a client replies or Lorenzo moves a GHL card: `services/upwork_followup/watch.py`, `watch_task_prompt.md`, `--watch-plan` / `--ingest-light` / `--mark-full-start`, processed mark in `tick.py`, `tests/test_watch.py`. If `git log origin/main` does not show the commit "section 3: watch trigger", bring it into main (rebase, full suite, push) and delete branch `wip/section-3-watch` if it still exists. Then Lorenzo creates the Claude desktop scheduled task from the desktop app (cloud can't): prompt = `watch_task_prompt.md`, cron `*/30 8-18 * * 1-5` plus `0 19 * * 1-5`, after `git pull` in the main folder; turn off any 08:30 task.
1. Lorenzo's "say yes" items below.
2. First real run with the new prompts: main folder, after `git pull` there, with Lorenzo's OK for the model spend (read only, drafts to a file). The one quiet chat's T1 was due 09-24.

## Parked (optional, only if Lorenzo wants)
- The copy gate has no backstop for the new rules (a T3 quoting "$750M+" still passes, since the figure is in `upwork_offers.md`); they are prompt-only. Lorenzo sends every draft himself.
- Reviewer insurance notes on `touch_t3.md`: append "(what was built, never its figures)" to the "one exception" line; say "when the proof line says what was built" so the roofing example isn't reused for the lender or agency lines.
- The monthly-rate gap in `copy_gate.py` (`_RATE_AGREED_RE`).
- Watch polish (reviewer, parked): the processed mark is also written when `sequence.run` fails as a whole or drafts are held by the run budget (waits for the next trigger; the error card tells Lorenzo); `--watch-plan` help text and the runbook CLI row omit mode `run`; a hand-forced full run writes no start marker; a card with a story id but no time re-flags every run; rooms in `missing_messages` aren't retried by the watch; a revived old linked room waits until the next day.

## Waiting on Lorenzo
- **The GHL Upwork pipeline** (he is creating it): six stages in this order, New reply, Proposal sent, Call booked, Follow up later, Won, Lost (code keys `new_reply`, `proposal_sent`, `call_booked`, `follow_up_later`, `won`, `lost`). A move to New reply or Proposal sent makes the engine draft. When it exists, read its ids (read only) into `config/ids.json` `ghl.pipelines.upwork`.
- **The watch schedule** (being built): a Claude scheduled task every 30 min on weekdays; first run of the day is the full sweep. Replaces the 08:30 daily run. Created only on his yes.
- Pricing: settled 2026-09-23, never. He sets each job's price; drafts never state one (`config/upwork_offers.md`).
