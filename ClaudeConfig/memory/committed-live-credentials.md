---
name: committed-live-credentials
description: Four live credentials in old git history (modal_reply_handler_v2.py); only on local archive/* refs since the 2026-09-23 fresh-start GitHub push - never push those refs; rotation still Lorenzo's call
metadata:
  type: project
---

Found 2026-09-22 by the Revenue Automation completeness critic and verified in this
session. `Agentic Worklfows/execution/modal_reply_handler_v2.py` (around line 249, in a
`modal.Secret.from_dict` block) hard-codes four real credentials, and the file is tracked
at HEAD and in every commit:

- `INSTANTLY_API_KEY` - **confirmed live**: it decodes to the production org id
  `92fb7f1b-1d71-45d5-bea0-178894b5b492`, the same org returned by live `list_leads` calls.
- `GITHUB_TOKEN` - a `ghp_` personal access token.
- `SLACK_WEBHOOK_URL` - a hooks.slack.com endpoint (this webhook was separately found
  unreachable during the build, so it may already be dead).
- `GOOGLE_CREDENTIALS_JSON` - a service-account block including `private_key`, the same
  account `credentials.json` uses.

**Update 2026-09-23:** the repo now has a remote, private `github.com/adverosolutions/AdveroSolutions`, which Lorenzo chose to start fresh. `main` begins at a new root commit (fe95263) that holds no credentials; reviewer-max checked every live `.env` value against it. The old 230 commits, which contain these secrets, exist only locally on `archive/main`, `archive/revenue-automation`, `archive/upwork-overhaul` and the tag `archive/pre-github-2026-09-23`. **Only push `main` or `section/*` branches rooted at fe95263 (check `git rev-list --max-parents=0 HEAD`), never `--all`, `--mirror`, `--tags` or an archive ref.** The service-account key in that history is still the live key.
CLAUDE.md says the live Modal app is `execution/modal_lead_sync.py`, so this v2 handler is
probably dead code - confirm before deleting.

**Lorenzo's decision, not an agent's:** rotate all four, then choose whether to merely
untrack the file or rewrite history. Agents must not rotate credentials, rewrite history,
or print the values. This is step 0 of `Agentic Worklfows/runbooks/GO_LIVE_CHECKLIST.md`
because the go-live path ends in a `git push` and a Modal secret, which is the moment the
exposure stops being local.

Distinct from the older Supabase credential noted in [[cleanup-2026-09-21]] (commit
f7bca3e), which is still open too. Related: [[no-live-changes-until-tested]].

**Why:** a live production key in git history is the highest-severity item in the whole
build, and it is invisible unless someone goes looking. **How to apply:** raise it before
any push, remote, or deploy is discussed; do not act on the credentials directly.
