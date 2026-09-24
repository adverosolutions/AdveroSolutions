# Section 3 status

**2026-09-24 (cloud chat):** the watch trigger is on main (`9f7048b`, landed 2026-09-23 22:07 CT). In the cloud chat the live-write guard blocks `git push` (rule c), so on Lorenzo's OK (2026-09-24) the cloud chat pushes through the GitHub connector instead, one file per commit, to `main` only. `section/3-upwork` stays at `9f7048b` behind main (a fast-forward); the next chat with a working `git push` fast-forwards it.

**2026-09-23 (split day):** Lorenzo's new voice rule (no Claudeisms, normal capitalization) is in `sections/README.md`, his global CLAUDE.md and a `claudeisms` skill.

## Done 2026-09-24
- **Watch trigger on main.** The four section 3 commits sit on `78d8720`; `origin/section/3-upwork` and `origin/main` are the same commit. The cloud chat's own rebase produced the same four patches (range-diff `=`), so it pushed nothing.
- **Full suite in the cloud container on that tree:** 11,977 passed, 75 failed, 1 skipped, NETGUARD 0 blocked, credential-file opens refused 0. All 75 failures are in `changesets/tests/test_claude_guard.py` (`test_guard_case`, `test_round3_through_the_wrapper` and the apply/rollback cases). They fail the same way on `78d8720`, before any section 3 commit. Likely cause, checked for one case only: `glob .env` is `cat .en?`, which counts as a `.env` read only when a real `.env` is in the folder, and a fresh clone has none; the `git restore .` / `git clean` cases look like the same kind. Section 4 owns that test. Nothing section 3 touches failed.
- **`wip/section-3-watch` checked:** every file in its one commit (`15bafd5`) matches main, so it holds nothing unmerged. Safe to delete; the GitHub connector has no branch delete, so that one is Lorenzo's (`git push origin --delete wip/section-3-watch` from his terminal).
- Cloud setup note: `pip install -r requirements.txt` leaves out `fastapi`; also install `services/reply_engine/requirements.txt`, or 35 reply-engine test files fail to import. On the container's Debian Python, add `--ignore-installed PyJWT`.

## Done 2026-09-23
- **Touch walkthrough** with Lorenzo: all 9 prompts agreed (`walkthrough.md` has every decision and sample).
- **Prompts updated** (reviewed, APPROVE twice): normal capitalization; the no-Claudeisms rule; T3 hints at a similar past client (no name, no figures, a plain-words line on what was built is fine); no touch repeats a result the proposal already states (reply only when asked). All 9 agreed samples pass the copy gate.
- **Watch trigger** (reviewed, APPROVE on round 2): drafts come when a client replies or Lorenzo moves a GHL card. `services/upwork_followup/watch.py`, `watch_task_prompt.md`, `--watch-plan` / `--ingest-light` / `--mark-full-start`, processed mark in `tick.py`, `tests/test_watch.py`.

## Next
1. **GHL Upwork pipeline ids**, as soon as Lorenzo says the pipeline exists: read its ids (read only) into `config/ids.json` `ghl.pipelines.upwork` (only that key; the placeholder with the six stage keys is already there), one reviewer pass, push (GitHub connector from the cloud chat).
2. **The watch schedule:** Lorenzo creates the Claude desktop scheduled task from the desktop app (cloud can't): prompt = `watch_task_prompt.md`, cron `*/30 8-18 * * 1-5` plus `0 19 * * 1-5`, after `git pull` in the main folder; turn off any 08:30 task.
3. **First real run** with the new prompts: main folder, after `git pull` there, with Lorenzo's OK for the model spend (read only, drafts to a file). The one quiet chat's T1 was due 09-24.

## Parked (optional, only if Lorenzo wants)
- The copy gate has no backstop for the new rules (a T3 quoting "$750M+" still passes, since the figure is in `upwork_offers.md`); they are prompt-only. Lorenzo sends every draft himself.
- Reviewer insurance notes on `touch_t3.md`: append "(what was built, never its figures)" to the "one exception" line; say "when the proof line says what was built" so the roofing example isn't reused for the lender or agency lines.
- The monthly-rate gap in `copy_gate.py` (`_RATE_AGREED_RE`).
- Watch polish (reviewer, parked): the processed mark is also written when `sequence.run` fails as a whole or drafts are held by the run budget (waits for the next trigger; the error card tells Lorenzo); `--watch-plan` help text and the runbook CLI row omit mode `run`; a hand-forced full run writes no start marker; a card with a story id but no time re-flags every run; rooms in `missing_messages` aren't retried by the watch; a revived old linked room waits until the next day.

## Waiting on Lorenzo
- **Delete `wip/section-3-watch`** from his terminal (the connector can't).
- **The GHL Upwork pipeline** (he is creating it): six stages in this order, New reply, Proposal sent, Call booked, Follow up later, Won, Lost (code keys `new_reply`, `proposal_sent`, `call_booked`, `follow_up_later`, `won`, `lost`). A move to New reply or Proposal sent makes the engine draft.
- **The watch schedule:** his yes, then he creates the task (Next, item 2).
- Pricing: settled 2026-09-23, never. He sets each job's price; drafts never state one (`config/upwork_offers.md`).
