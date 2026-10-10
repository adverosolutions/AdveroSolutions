---
name: no-live-changes-until-tested
description: "Lorenzo's rule for the revenue automation build — never touch live Instantly/GHL/Upwork/Calendar; build and test in a controlled environment, then push to production only after sign-off"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5a6eeb0b-0a8e-4f7a-80da-80780c7ba0d5
  modified: 2026-09-22T20:00:00.000Z
---

Every automation build (reply engine, deliverability monitor, list factory, cadence jobs) must be developed and tested in a controlled environment first. No writes to live Instantly campaigns/accounts/webhooks/labels/subsequences, GHL contacts/opportunities/workflows, Upwork, Google Calendar or Gmail until the code is rigorously tested and Lorenzo has explicitly approved the production push (stated 2026-09-21).

**Why:** A bad campaign PATCH, a mis-sent reply, or a paused inbox breaks live money paths (six active campaigns, 45 inboxes, booked discovery calls). Lorenzo said this would "cause a lot of issues".

**How to apply:** Build with `MODE=shadow` as the default, read-only pulls plus recorded fixtures for tests, and stage every live change as a change-set file that a script applies only with `ALLOW_LIVE_WRITES=1` after Lorenzo reviews the dry-run diff. Use the read-only shadow poller instead of creating Instantly webhooks. Report "tested in shadow, awaiting go-live approval" rather than flipping anything live. Related: [[project_architecture]], [[instantly-2026-campaigns]].

**The PreToolUse hook is not a safety net (found 2026-09-22 re-review).** `.claude/hooks/guard_live_writes.sh` is registered only in the repo-root `.claude/settings.json`. Sessions launched from `Coding/` (where Lorenzo usually starts) load no hook, and `${CLAUDE_PROJECT_DIR}` resolves to a path where the script does not exist, which exits 127 and fails open; `.claude/settings.local.json` also pre-approves `curl:*` and `python3:*`. The overnight build ran unguarded by it. What actually held was the code-level `shared.settings.guard_write`. Also: tests and evidence scripts that set live flags with `NOTIFY=on` can send real email and ntfy pushes, because `load_env()` reads the parent `.env`. Never set live flags in a script, even with mocked transports. Fixing the hook is decision R1 in `Agentic Worklfows/runbooks/REREVIEW_2026-09-22.md`.

**Worktree sessions are guarded (seen 2026-09-24).** A session launched inside a git worktree (a full checkout such as `Coding/.claude/worktrees/*` or `.worktrees/*`) loads that checkout's repo-root `.claude/settings.json`, so the guard runs there. Its rule c blocks `git push` in any form. In such a session, commit locally and give Lorenzo the push command to run himself; don't try to route around the hook. See [[feedback-push-every-change]].
