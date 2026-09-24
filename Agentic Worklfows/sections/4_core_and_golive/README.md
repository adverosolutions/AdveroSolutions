# Section 4: core engine, the one Google Doc, cold campaigns, go-live

## Goal
This section keeps the shared engine safe and working, turns Lorenzo's edits in the one Google Doc into code, and takes the system from shadow to live when he says so. It owns the shared code that sections 1 to 3 build on.

## Where it stands (2026-09-23)
- **Shadow by default.** `MODE=shadow` proposes, logs and notifies only. The real protection is `shared.settings.guard_write`. The `.claude/hooks/guard_live_writes.sh` hook is not installed for sessions outside the repo root, so do not rely on it. The reply engine reads replies with a GET poller (no Instantly webhooks yet). The Modal app (`services/reply_engine/modal_app.py`) has never been deployed from this build.
- **Template gate (CT3).** An engine email auto-sends only when its text is exactly a template Lorenzo approved and unchanged since then, the kill switch is off, and every send check passes. Otherwise it becomes an approval card (replies) or is held (cadence, show-rate, no-show).
  - The catalogue has 108 approvable ids.
  - The parity digest is `392b01cd05449198`, identical on Python 3.9 and 3.11. It is written down only in `runbooks/template_approvals.md` and `runbooks/reply_engine_alerts.md`.
  - The digest changes whenever sections 1 or 2 change copy. Re-run `changesets/deploy/template_parity.py` and update those two lines.
- **`config/approved_templates.json`** is still `{"version": 1, "approvals": {}}`. Nothing is approved.
- **The one Google Doc** is "Advero emails: edit here (every email, one doc)", id `1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U`, in Drive folder `1yww1rrk0blgKnD98CkIY95XPEsaDZQ9c`.
  - It holds every email: the 108 engine templates, plus the 6 live Instantly campaigns (2 steps each, body and subject), labelled by sequence. That is 379 tagged blocks, verified against Drive's own export.
  - Tooling is in `tools/template_doc/` (see its `README.txt`): `diff_doc.py` compares an export with `manifest.json`, `build.py` rebuilds the doc, and `selftest.py` passes.
  - Lorenzo's rule: when he says "done" on the doc, everything in it counts as approved (this replaces the terminal approve step). "Go live" is a separate, explicit yes. Nothing goes live, Instantly cold-email changes included, until he says "go live".
- **Live Instantly:** 6 campaigns, 2 steps each, matched the 2026-09-21 snapshot (`config/snapshots/`) on 2026-09-23 (read-only GET).
- **GitHub:** private repo `adverosolutions/AdveroSolutions`. `main` is the fresh-start snapshot `fe95263`. The old history is on the `archive/*` branches. Recorded test fixtures are now in git. There is no CI, so pushing deploys nothing.

## Next steps, in order
0. **Make the suite green in worktrees** (see Known test gaps below).
1. **Save Lorenzo's doc edits first.** Export the current doc (Drive `download_file_content`, `text/plain`) and run `python3 tools/template_doc/diff_doc.py <export.txt> --manifest tools/template_doc/manifest.json`. Anything he already changed is his approval in progress: record it in `STATUS.md` and hand each changed block to the section that owns it.
2. **Build the apply path** from the doc to the system:
   - Export the doc and diff it against the manifest.
   - For each changed block, find the file that owns it: engine templates belong to sections 1 and 2, so hand those over; the Instantly steps belong here.
   - Instantly step changes become a change-set under `changesets/`. It gets a `--dry-run` against live; the live apply comes only after "go live".
   - Recording approvals: only after Lorenzo types "done" in chat about the doc. Record exactly the doc's text, show him `git diff -- config/approved_templates.json`, and commit it quoting his words. Never on your own.
3. **Rebuild the doc** once sections 1 and 2 land their new copy. The Drive connector can't edit a doc's text in place, so this means `build.py`, then `create_file` (HTML to Google Doc), then rename the old doc "OLD, do not edit". Tell Lorenzo not to spend time in the current doc until then: the follow-up and booked-call emails in it are being rewritten.
4. **Go-live checklist** (`runbooks/GO_LIVE_CHECKLIST.md`). These are Lorenzo's own actions; walk him through them when he's ready:
   - rotate the committed credentials and create read-only keys;
   - install the guard hook (`changesets/claude_guard/`, from his own terminal);
   - A2P;
   - replace the `GOOGLE_CREDENTIALS_JSON` placeholder;
   - `NOTIFY_SHADOW_SEND` for a shadow week, and `NTFY_TOKEN` if he wants lead names in pushes;
   - GHL sandbox rehearsals, including one PUT and GET for the Upwork mirror;
   - Zoom (optional).

   The instant kill for anything deployed is `python3 -m modal app stop advero-reply-engine`.
5. **Known small items** (reviewed, none blocking):
   - fixed on 2026-09-23 by section 1 (`cadence.py`): cadence pushes on a public ntfy topic say "a lead" and carry no email or company; daily Resume reminders stop after 8 pushes or 14 days (the ladder stays stopped);
   - fixed on 2026-09-23 by section 4: the resume page's POST no longer says "not found" before checking the signed link; `GATE_RULES_VERSION` has a pin test (`services/reply_engine/tests/test_gate_rules_version.py`); the top-level `requirements.txt` now pins the engine's anthropic, httpx and pydantic, and modal 1.2.6.

## Known test gaps (fresh worktree)
A clean checkout of `main` on 2026-09-23 gave 11,635 passed and 2 failed, with 0 egress and 0 credential-file opens. Both failures depend on where the checkout sits, and both pass in the main folder:
- `changesets/tests/test_schedules.py::test_schedules_json_is_not_stale`: `changesets/schedules/build_schedules.py` writes absolute paths into the launchd plists and `crontab.txt`, so any other checkout path reads as "stale". Make the check path-independent, for example by comparing with the repo root normalised, without changing what gets installed on the laptop.
- `jobs/tests/test_list_factory_pipeline.py::test_an_apify_run_whose_shards_mostly_failed_raises`: it reads `Coding/lead-scrape-2026/niches/cleaning.json`, which the blanket `*.json` ignore keeps out of git. Either stub the niche filters in the test or commit the niche filter files (they are Apify filter settings, not lead data; check before committing).

**Do this first:** the other three sections run the suite in worktrees and should see it fully green.

## What this section owns (paths under `Agentic Worklfows/`)
- `shared/**`
- `services/reply_engine/`: `app.py`, `approval.py`, `router.py`, `poller.py`, `modal_app.py`, `models.py`, `pipeline_sync.py`, `replay.py`, `template_approvals.py`, `template_gate.py`, `README.md`, `requirements.txt`, `run_local.sh`, and the shared test helpers (`tests/conftest.py`, `tests/template_fixtures.py`)
- `jobs/approve_templates.py`, `jobs/README.md`, `jobs/tests/conftest.py`
- `changesets/**`, `config/**` (except `config/upwork_offers.md` and the `pipelines.upwork` key in `config/ids.json`, which are section 3's)
- `conftest.py`, `pytest.ini`, `tools/**`, `REVENUE_AUTOMATION_BLUEPRINT.md`, the root `CLAUDE.md`, `.gitignore`
- Every runbook not claimed by sections 1 to 3, including `GO_LIVE_CHECKLIST.md`, `DECISIONS_FOR_LORENZO.md`, `template_approvals.md`, `reply_engine_alerts.md`, `deployment.md`, `live_write_guard.md`, `read_only_keys.md`
- The one Google Doc, and the 6 live Instantly cold campaigns (copy changes only through a change-set, after "done" and "go live")
- `sections/4_core_and_golive/**`

**Parked:** built and tested, no work planned; fix here only if something breaks.
- `services/list_factory`, `services/experiments`, `services/metrics`, `services/retro`
- their jobs: `list_factory`, `campaign_verdicts`, `daily_metrics`, `deliverability_monitor`, `inbox_inventory`, `inbox_placement`, `autoresponder_canary`, `pipeline_sweep`, `positive_sweep`, `retro_packet`, `client_scorecard`
- `products/**` (fulfillment kits), and the capacity, inbox and schedule change-sets
