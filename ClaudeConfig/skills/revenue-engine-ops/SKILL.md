---
name: revenue-engine-ops
description: Maintainer manual for the AdveroSolutions revenue engine ("Agentic Worklfows" repo). Layout, shadow vs live and guard_write, template approvals and the one Google Doc "done" path, change-sets with --dry-run, Modal and laptop schedules and deploy status, the four section chats with worktree and push rules, the test command, Python 3.9 limits, the old Instantly-to-CRM sync. Use before building, fixing, testing, deploying or reviewing engine code, or when asked "is it live", "what runs where", "how do I push", "how do approvals work".
---

# Revenue engine: maintainer manual

For Claude Code working in the repo. Grok Bot needs only the "Safety rules" and
"Where it runs" sections; its own manual is the `grok-operator` skill. Reply
handling, booked calls, cold campaigns, deliverability and reports have their
own skills (`cold-email-replies`, `booked-calls`, `cold-campaigns`,
`deliverability-and-inboxes`, `daily-reports-and-metrics`).

## Operating model (Lorenzo, 2026-09-25)

- Grok Bot is Lorenzo's contact point and executes: it wakes on events, asks
  Opus what to do, performs exactly that, verifies it, retries a failed send
  once with the same idempotency key, and reports.
- Claude Opus 5.5 makes every decision: classification, action, template,
  the filled text.
- Grok never writes, edits, paraphrases or chooses customer-facing text.
- Approved-template text is the only text that goes out without Lorenzo
  seeing it first.
- No polling. Everything starts from a webhook (Instantly reply, GHL
  appointment, Zoom) or an engine timer posting a due touch.

The code on `main` predates this: the engine sends its own approved templates,
the poller runs every 5 minutes, and `shared/llm.py` `MODEL_POLICY` has Haiku
classifying and Sonnet 5 drafting. Moving drafts and decisions to Opus 5.5,
building the Advero connector (`decide`, `send`, `status`, ...), the webhooks
and the timer are open builds. Do not describe them as done.

## Layout (paths under `Agentic Worklfows/`)

| Path | What |
|---|---|
| `shared/` | API clients (`instantly.py`, `ghl.py`), `settings.py` (mode, `guard_write`, ids), `store.py`, `job_log.py`, `notify.py` (ntfy + email), `llm.py` (`MODEL_POLICY`, budget), `slots.py`, `keys.py`, `thresholds.py` |
| `services/reply_engine/` | S1-S8: `poller.py`, `router.py`, `draft.py`, `approval.py` (cards), `template_gate.py`, `template_approvals.py`, `cadence.py` (E1-E10), `nurture.py`, `booking.py`, `show_rate.py`, `no_show.py`, `precall.py`, `pipeline_sync.py`, `app.py` (web routes), `modal_app.py` (every schedule) |
| `services/` others | `metrics`, `retro`, `experiments`, `list_factory`, `upwork_followup` |
| `jobs/` | scheduled and by-hand CLIs (O1-O8); each has `--dry-run`, `--now`, `--as-of` and writes one Job_Log row |
| `changesets/` | every live change as data plus an apply script; `deploy/`, `schedules/`, `instantly_copy/`, `inbox_actions/`, `capacity/` |
| `config/` | `ids.json` (live ids), `offers.md` (the only pricing and proof), `approved_templates.json`, `experiments.json`, `llm_budget.json` ($10 shared cap) |
| `tools/template_doc/` | build, diff and record tools for the one Google Doc |
| `tools/netguard/` | blocks network egress during tests |
| `runbooks/` | how to run and ship each piece |
| `sections/` | the four section handoffs and STATUS files |

## Safety rules (never break)

1. **Shadow by default.** `MODE=shadow` proposes, logs and notifies only.
   Only `MODE=live` together with `ALLOW_LIVE_WRITES=1` writes. `load_env()`
   ignores both flags in any `.env`. Never set either one, in a shell, a
   script, a test or a subprocess, even with mocked transports.
2. **Every write goes through `shared.settings.guard_write(system, action,
   payload)`.** In shadow it returns `{"shadow": True, ...}`, appends to
   `.tmp/shadow_log.jsonl`, and the caller must not write. In live it logs a
   `live_write_intent` Job_Log row first, then returns `shadow: False`. This
   is the real protection.
3. **There is no guard hook** (removed 2026-10-10, Lorenzo). Nothing checks
   commands before they run, so `guard_write` and these rules are the only
   protection.
4. **Never read or print** `.env`, `credentials.json`, `token.json`,
   `~/.advero/`, `~/.modal.toml`.
5. **Never approve templates** and never write `config/approved_templates.json`,
   except the doc path below after Lorenzo types "done".
6. **No `modal deploy`, no live apply, no live dry-run** against a live API
   without the read-only keys. Those are Lorenzo's, from his own terminal.
7. **Paid calls only with Lorenzo's OK.** `ALLOW_PAID_CALLS=1` alone opens the
   list factory's paid calls, in shadow too. Anthropic spend elsewhere is
   gated by `LLM_FAKE` and the $10 budget.
8. **Do not touch:** the Upwork application flow and Demo Library loop, live
   campaign `email_list`, the old `execution/` scripts and the live
   `modal_lead_sync` webhook, credential rotation, git history.
9. **Recipient safety on replies is enforced twice:** `shared/instantly.py`
   requires `to=<lead email>` and `cadence.thread_recipient_ok` re-reads the
   email live and refuses unless `from_address_email` is the lead. Keep both.
   `config/instantly_api_contract.md` is authoritative on request shapes.

## Engine rules the code enforces

- Send window 07:00-19:00 CT. Slots 12:00-18:00 CT Mon-Fri, at least 4 h out,
  within 5 business days, never offered twice. No booking links: the lead
  picks one of two times and Lorenzo sends the invite.
- Replies go through Instantly's reply endpoint from the original inbox and
  thread.
- Pricing and guarantee figures never appear in an email (2026-09-24); the
  call keeps them. Proof lines only from `config/offers.md`.
- Every first reply is held: a draft Lorenzo writes himself (2026-09-24).
  Other replies auto-send only after a reply of ours reached the lead, except
  the "Locked in" booking confirmation.
- The template gate sends only when: kill switch off, parity passes, text
  rendered from a template, every id approved at its current hash, text still
  current, classification confidence >= 0.8 (not the fallback), slot rules
  pass, copy gate passes, and the body is the template with only placeholders
  filled (each placeholder checked for its kind). Otherwise: a card (replies)
  or held (cadence, show-rate, no-show).
- Kill switch: `AUTO_SEND_TEMPLATES` not `1/on/true/yes`, or `"auto_send":
  false` in the registry. Neither is instant on Modal. The instant stop is
  `python3 -m modal app stop advero-reply-engine`, run by Lorenzo.

## Template approvals and the one Google Doc

- Each template is stored with a sha256 of its full text: main text, every
  variant and the time-format block. Any wording or formatter change needs
  re-approval.
- Lorenzo edits one Google Doc. When he types "done" in chat about that doc,
  everything in it counts as approved. "Go live" is a separate yes.
- Current doc: build `170b09dd897430a9`, id
  `1bK3bkYfxYkhY0vFtHhB4RG6lMkKQrHvp6Qyasp8Pbt4` (uploaded 2026-09-24; 365
  blocks; 67 to approve, 36 first replies held). Older docs are renamed "OLD,
  do not edit".
- The "done" path (section 4 chat only): read open comments and suggestions
  (stop and ask if any), export the doc as text and HTML, dry-run
  `tools/template_doc/record_doc_approvals.py`, then `--write --doc-id <id>
  --done-quote "<his exact words>" --checked-comments --html <export>`, show
  him `git diff -- config/approved_templates.json`, commit quoting his words.
  The recorder only adds approvals; it never revokes or touches the kill switch.
- Changed Instantly cold-step blocks are not approvals: they become a
  change-set under `changesets/instantly_copy/`, dry-run against live, applied
  only after "go live".
- Nothing is approved yet (`{"version": 1, "approvals": {}}`).

## Change-sets

Every live change is a file under `changesets/` plus an apply script.
`--dry-run` diffs against live (or `--from-snapshot` offline); the live apply
backs up the current object first. Claude may run only the read-only modes
(`--dry-run`, `--status`, `--plan`, `--preflight`); `--apply`, `--restore`,
`--rollback`, `--yes`, `--create` are Lorenzo's.

## Where it runs

| Where | Jobs (CT) |
|---|---|
| Modal app `advero-reply-engine` (sales tier, 9 crons + 1 web endpoint) | poller, approval_escalation, precall_tick (every 5 min), appointments_tick (10 min), no_show_watch (every minute 12-18 weekdays), cadence_tick (hourly 07-19), cadence_veto_ping (09:30 weekdays), pipeline_sync (06:00), pipeline_sweep (07:30) |
| Laptop via launchd (`changesets/schedules/laptop_runner.py`) | inbox_placement (Mon 06:45), autoresponder_canary (Sat 06:45), deliverability_monitor (07:00), inbox_inventory (07:00), list_factory (Sun 09:00), retro_packet (Fri 16:00), daily_metrics (18:00), client_scorecard (Fri 19:15) |
| Turned off, by hand | campaign_verdicts, upwork_rooms_am, upwork_rooms_pm |

`modal_app.SCHEDULES` is the one source; `build_schedules.py --check` fails on
drift. Crons read `America/Chicago`. Four Modal Dicts (engine store and
evidence, shadow and live, never shared); Modal drops a Dict entry after 7
days idle.

**Deploy status:** the Modal app has never been deployed from this build.
Everything runs in shadow. Nothing is live.

Go-live order (`runbooks/GO_LIVE_CHECKLIST.md`, `deployment.md`): Lorenzo
rotates committed credentials, fixes the `GOOGLE_CREDENTIALS_JSON`
placeholder, creates read-only keys, installs the guard, (A2P if SMS),
decides capacity and prices, mints the GHL token; then preflight (tests,
template parity check 7, unapproved-ladder check 8, stamp valid 60 min),
secret, shadow deploy, 48-hour watch (`watch_report.py` exits 0; zero
`live_write_*` rows; a push every morning; one card tapped end to end), his
written go, cutover (deploy live within 120 min), sales tier live, then
laptop tiers one at a time. Rollback: stop the app, seed the shadow cursor
from live, re-create the secret, redeploy shadow.

## The four sections (from 2026-09-23)

| # | Section | Branch |
|---|---|---|
| 1 | Email follow-up after an interested lead goes quiet (E1-E10) plus the 90-day nurture | `section/1-email-followup` |
| 2 | Booked calls: confirmation, reminders, no-show recovery | `section/2-booked-calls` |
| 3 | Upwork follow-ups | `section/3-upwork` |
| 4 | Core engine, the one Google Doc, cold campaigns, go-live; owns `shared/`, `config/`, `changesets/`, `tools/` | `section/4-core-golive` |

Each section's README says what it owns; STATUS.md is the handoff. A fix in a
file another section owns goes in its own commit starting `shared:`.

**Worktrees.** Never work in the main folder. `git worktree add .worktrees/<n>
-b section/<name> origin/main` (or reuse the branch). `.env` and `.tmp/`
exist only in the main folder.

**Push every change.** Commit by path (never `-A`), push the section branch,
then `git fetch && git rebase origin/main`, run the full suite, `git push
origin HEAD:main`, then `--force-with-lease` the section branch. Before every
push `git rev-list --max-parents=0 HEAD` must print only
`fe95263e92f15c9b2f8dc20a8806c00343c1ef32`. Never push `--all`, `--mirror`,
`--tags` or `archive/*` (old history holds live credentials). In a worktree
session the guard blocks `git push`: commit, run the root check, and give
Lorenzo the exact push command. Unreviewed WIP goes to the section branch or
`wip/section-<n>-*`, never `main`. Never `git reset --soft origin/main` to
squash. New `*.json` files are git-ignored except under `config/`,
`tests/fixtures/`, `changesets/`, `tools/`.

## Tests

From `Agentic Worklfows/`:

```
PYTHONPATH=tools/netguard python3 -c "import netguard, pytest, sys; sys.exit(pytest.main(['-q','-p','no:cacheprovider']))"
```

Pass means all green, `NETGUARD: 0 blocked egress attempts` and
`credential-file opens refused: 0`. About 12,250 tests (2026-09-24 on the
Mac). The root conftest forces shadow, faked LLM, `NOTIFY=off` and a temp
`.tmp/`. In a cloud container 75 guard tests fail for environment reasons.
Tests use recorded fixtures and `httpx.MockTransport`.

Python 3.9: no `X | Y` unions, no `match`, use `Optional[...]`. pytz is pinned
(2023.3) because template hashes depend on it.

New job: copy `jobs/pipeline_sweep.py`'s shape, read ids from
`shared.settings`, add fixtures tests, register in `modal_app.SCHEDULES`,
regenerate schedules, write a runbook, shadow 48 h.

Definition of done: pytest green, a dry-run or replay shadow log, a runbook,
Job_Log rows, evidence in the report.

## Instantly to CRM sync (legacy)

`execution/instantly_lead_sync.py` (directive
`directives/AUTOMATED/sync_instantly_leads.md`): daily 09:00 CT, pulls every
campaign's leads and maps Instantly status to the Google Sheets CRM stage
(replied/interested to Engaged, meeting_booked to Booked, meeting_completed to
Discovery Done, completed/bounced/unsubscribed/not_interested/wrong_person to
Closed Lost). Never downgrades a stage, never overwrites Closed Won or Closed
Lost, skips leads not in the CRM. It is the live `modal_lead_sync` webhook and
is off-limits to the revenue build. In the new engine GHL "Sales" is the
source of truth and `pipeline_sync` (06:00) mirrors GHL stage to Instantly
interest status; negatives are sticky.

## Sources (for maintainers)

- Repo `CLAUDE.md` (Revenue Automation Build, Working in sections; read 2026-09-25).
- On origin/main at ba39a0c (2026-09-24): `sections/README.md`; each section's STATUS.md (1: 2026-09-24; 2: 2026-09-24; 3: 2026-09-24; 4: 2026-09-23 to 09-24) and section 4 README; `runbooks/GO_LIVE_CHECKLIST.md` (rewritten 2026-09-22), `deployment.md`, `live_write_guard.md`, `template_approvals.md`, `pipeline_hygiene.md`; `jobs/README.md`; `shared/settings.py` (`guard_write`); `shared/llm.py` (`MODEL_POLICY`); commit ba39a0c message (doc build 170b09dd897430a9).
- `directives/AUTOMATED/sync_instantly_leads.md`.
- Memory: `no-live-changes-until-tested.md` (2026-09-22/24), `feedback-push-every-change.md` (2026-09-24), `sections-split-2026-09-23.md`, `cold-email-template-autosend.md` (2026-09-23), `grokbot-orchestrator.md` (2026-09-24).
- Operating model: Lorenzo in chat, 2026-09-25; `grok-operator` skill.
