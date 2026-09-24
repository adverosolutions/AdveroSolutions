# The revenue build, split into 4 sections (2026-09-23)

Lorenzo runs each section in its own chat, all four at the same time. Every section has a folder here with a `README.md` (the handoff: goal, where it stands, next steps, what it owns) and a `STATUS.md` that the chat keeps current.

| # | Section | Chat branch | Folder |
|---|---------|-------------|--------|
| 1 | Email follow-up: the lead said interested, then went quiet (plus the 90-day nurture) | `section/1-email-followup` | `1_email_followup/` |
| 2 | Booked calls: confirmation, pre-call reminders, no-show recovery | `section/2-booked-calls` | `2_booked_calls/` |
| 3 | Upwork follow-ups | `section/3-upwork` | `3_upwork/` |
| 4 | Core engine, the one Google Doc, cold campaigns, go-live | `section/4-core-golive` | `4_core_and_golive/` |

How a lead moves between sections:

```
cold email (4) -> "interested" reply -> Lorenzo's own reply with two times (1)
   -> no answer: follow-up E1..E10 (1) -> 90-day nurture (1)
   -> "not now" reply at any point (1) -> 90-day nurture (1)
   -> books a call -> confirmation + reminders (2) -> shows up: the call
                                                 -> no-show: recovery (2) -> never rebooks: nurture (1)
Upwork proposals run on their own track (3).
```

The one hand-off in code: section 1 owns `services/reply_engine/nurture.py` and lands `enroll(lead_email, reason, now)` early. Section 2 calls it for no-shows who never rebook (reason `no_show_no_rebook`).

## Rules for every section chat

1. **Own branch, own folder.** Work in a git worktree on your section's branch, never in the main folder (four chats in one folder overwrite each other). First thing in a new chat:
   ```bash
   cd /Users/lorenzovillarreal/Desktop/AdveroSolutions
   git fetch origin
   git worktree add .worktrees/<n> -b section/<name> origin/main
   ```
   If the branch already exists (a later chat for the same section): `git worktree add .worktrees/<n> section/<name>`, or reuse the folder if it is still there. Then use absolute paths under `/Users/lorenzovillarreal/Desktop/AdveroSolutions/.worktrees/<n>/` for every read, edit and command.
2. **Edit only what your section owns** (listed in its README). If a fix truly needs a file another section owns, keep it minimal, put it in its own commit starting `shared:`, and list it in your `STATUS.md`. You may update any test that breaks because of your own change.
3. **Push every change to GitHub** (Lorenzo's rule, 2026-09-23). After each reviewed piece:
   ```bash
   git add <paths>          # by path, never -A
   git commit               # message ends with the Co-Authored-By line
   git push -u origin section/<name>
   ```
   Then bring it into main: `git fetch origin && git rebase origin/main`, run the full test suite (below), `git push origin HEAD:main`, then `git push --force-with-lease origin section/<name>`. If the push to main is rejected, fetch, rebase and test again. If a rebase conflicts in a file you do not own, stop and tell Lorenzo.
   **Before every push**, `git rev-list --max-parents=0 HEAD` must print only `fe95263e92f15c9b2f8dc20a8806c00343c1ef32` (the fresh-start root). Never push `--all`, `--mirror`, `--tags` or any `archive/*` ref: the old history on those local refs holds live credentials.
4. **New JSON files are ignored by default.** The root `.gitignore` has a blanket `*.json` rule with exceptions for `config/`, `tests/fixtures/`, `changesets/` and `tools/`. After adding a JSON file, check `git status` shows it; if not, add a narrow `!` line to `.gitignore` in a `shared:` commit.
5. **Keep `STATUS.md` current** and push it with each change: done, next, waiting on Lorenzo. If a chat runs out of usage, the next chat starts from it.
6. **Safety rules are unchanged** (root `CLAUDE.md`): shadow mode only; never set `MODE=live` or `ALLOW_LIVE_WRITES=1`; no `modal deploy`; never approve templates or write `config/approved_templates.json` (section 4 records Lorenzo's approvals only after he says "done", see its README); never print or open `.env`, `credentials.json`, `token.json`, `~/.advero/`, `~/.modal.toml`; no writes to Upwork; paid model calls only with Lorenzo's OK. Pushing code to GitHub deploys nothing (the repo has no CI).
7. **The main folder is for real runs.** `.env` and `.tmp/` exist only in `/Users/lorenzovillarreal/Desktop/AdveroSolutions`, not in worktrees. The main folder gets new code only when someone runs `git pull` there; do that just before a real (read-only) run needs it.
8. **Delegation** follows the global CLAUDE.md (scout, worker, worker-heavy, reviewer; reviewer-max for high-stakes). No workflows unless Lorenzo says "ultracode".
9. **Estimates** include review rounds. Park optional reviewer polish in `STATUS.md` instead of starting new rounds.

## Test command (from `Agentic Worklfows/` in your worktree)

```bash
PYTHONPATH=tools/netguard python3 -c "import netguard, pytest, sys; sys.exit(pytest.main(['-q','-p','no:cacheprovider']))"
```

Pass means: all tests green, `NETGUARD: 0 blocked egress attempts`, and the conftest line `credential-file opens refused: 0`. About 11,600 tests, roughly 9 minutes. Local Python is 3.9 (no `X | Y` unions, no `match`). **In a worktree, exactly 2 tests fail for path reasons** (checked on a clean checkout of `main`, 2026-09-23: 11,635 passed, 2 failed, 0 egress): `changesets/tests/test_schedules.py::test_schedules_json_is_not_stale` (the launchd files embed the main folder's path) and `jobs/tests/test_list_factory_pipeline.py::test_an_apify_run_whose_shards_mostly_failed_raises` (needs `Coding/lead-scrape-2026/niches/*.json`, which git ignores). Both pass in the main folder. Anything else failing is real. Section 4 fixes these two first.

## How email sequences get rewritten (sections 1 and 2)

This is what Lorenzo asked for on 2026-09-23 and what section 1 already did:
1. A shared writer brief (situation, Lorenzo's formula, offers, proof, voice rules). Use `1_email_followup/writer_brief.md` as the model.
2. One writer agent per email, each writing three versions.
3. One editor agent (Lorenzo asked for Fable here) ties the set together: one pick per email, openers that differ, a sequence that builds.
4. Walk Lorenzo through it **one email at a time in chat** and take his edits. Only then change code.
5. Voice rules he enforces: short, plain, casual, sounds like him texting; no em or en dashes, no exclamation marks, no emojis; never mention AI or automation; no invented facts, results or client names. Proof and prices only from `config/offers.md` and the proof list in the writer brief.

## Things no section touches

The Upwork proposal/application flow (`Coding/upwork-pipeline/`, the `/upwork` skill), the Demo Library loop (`Desktop/Projects/library`), the live campaign `email_list`, the old `execution/` scripts and the live `modal_lead_sync` webhook, credential rotation and git history (both Lorenzo's calls).

## Kickoff message for each chat

Paste one of these as the first message of a new chat:

- **Chat 1:** `You are the section 1 chat (email follow-up after an interested lead goes quiet, plus the 90-day nurture). Read "Agentic Worklfows/sections/README.md" and "Agentic Worklfows/sections/1_email_followup/README.md", set up your worktree, and pick up where STATUS.md says.`
- **Chat 2:** `You are the section 2 chat (booked calls: confirmation, pre-call reminders, no-show recovery). Read "Agentic Worklfows/sections/README.md" and "Agentic Worklfows/sections/2_booked_calls/README.md", set up your worktree, and pick up where STATUS.md says.`
- **Chat 3:** `You are the section 3 chat (Upwork follow-ups). Read "Agentic Worklfows/sections/README.md" and "Agentic Worklfows/sections/3_upwork/README.md", set up your worktree, and pick up where STATUS.md says.`
- **Chat 4:** `You are the section 4 chat (core engine, the one Google Doc, cold campaigns, go-live). Read "Agentic Worklfows/sections/README.md" and "Agentic Worklfows/sections/4_core_and_golive/README.md", set up your worktree, and pick up where STATUS.md says.`
