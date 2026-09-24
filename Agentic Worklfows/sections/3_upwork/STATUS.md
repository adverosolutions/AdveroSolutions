# Section 3 status

**2026-09-24 (local chat): the watch is live in shadow.** Claude desktop scheduled task `upwork-followup-watch` (every 30 min, 08:00-18:30 CT, weekdays; prompt in `~/.claude/scheduled-tasks/upwork-followup-watch/SKILL.md`, adapted from `watch_task_prompt.md`). It runs from the **run folder** `.worktrees/run` (detached at main, with symlinks to the main folder's `.env`, `Agentic Worklfows/.env`, `Agentic Worklfows/credentials.json` and `Agentic Worklfows/.tmp`), because the main folder is checked out on another chat's branch (`claude/maker-school-wins-tracking-...`). Every `--run` sets `NOTIFY_SHADOW_SEND=1` so Lorenzo gets the draft alert. To ship new section 3 code to it: push to main, then `git -C .worktrees/run fetch -q origin && git -C .worktrees/run checkout -q --detach origin/main`. `wip/section-3-watch` was already deleted on 2026-09-23.

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
2. **First real run:** started 2026-09-24 as a "Run now" of the scheduled task (full sweep, read only, a few cents of drafting).

## Parked (optional, only if Lorenzo wants)
- The copy gate has no backstop for the new rules (a T3 quoting "$750M+" still passes, since the figure is in `upwork_offers.md`); they are prompt-only. Lorenzo sends every draft himself.
- Reviewer insurance notes on `touch_t3.md`: append "(what was built, never its figures)" to the "one exception" line; say "when the proof line says what was built" so the roofing example isn't reused for the lender or agency lines.
- The monthly-rate gap in `copy_gate.py` (`_RATE_AGREED_RE`).
- Watch polish (reviewer, parked): the processed mark is also written when `sequence.run` fails as a whole or drafts are held by the run budget (waits for the next trigger; the error card tells Lorenzo); `--watch-plan` help text and the runbook CLI row omit mode `run`; a hand-forced full run writes no start marker; a card with a story id but no time re-flags every run; rooms in `missing_messages` aren't retried by the watch; a revived old linked room waits until the next day.

## Waiting on Lorenzo
- **The GHL Upwork pipeline** (he is creating it): stages New reply, Proposal sent, Call booked, Follow up later, Won, Lost. Note: card moves only work once the GHL mirror writes live (cards are created by the engine); in shadow mode the mirror writes nothing, so the card-move trigger needs his go-live call for GHL writes.
