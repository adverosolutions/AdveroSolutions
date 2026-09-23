# jobs/: scheduled tasks (Blueprint Section 6, O1-O8)

Deterministic scripts that run on a schedule or by hand. Where each scheduled job runs (owner decisions R3 and R4, `runbooks/deployment.md` "What runs where"):

- **Modal, 8 schedules, the sales tier:** `poller`, `approval_escalation`, `cadence_tick`, `cadence_veto_ping`, `appointments_tick`, `precall_tick`, `pipeline_sync`, `pipeline_sweep`. The poller, the approval chase, the cadence, the appointments tick and the sync call their `services/reply_engine/` entrypoints directly; `precall_tick` and `pipeline_sweep` run the scripts in this folder.
- **Laptop, 8 schedules:** `inbox_placement`, `autoresponder_canary`, `deliverability_monitor`, `inbox_inventory`, `list_factory` (marketing), `retro_packet`, `daily_metrics` (ops), `client_scorecard` (fulfillment). They hand work to each other through files, so they run through `changesets/schedules/laptop_runner.py` from launchd (or `crontab.txt`), in shadow unless their tier is named in `LAPTOP_LIVE_TIERS` in `.env`.
- **Turned off, 3:** `campaign_verdicts`, `upwork_rooms_am`, `upwork_rooms_pm`. Lorenzo runs them by hand; their code stays. `config/turned_off_jobs.json` names them with the by-hand command, and `changesets/schedules/build_schedules.py --check` fails if one is scheduled again.

`positive_sweep.py` is not scheduled: it delegates to `pipeline_sweep`, the single 07:30 run.

Each script:

- has `--dry-run` (read, compute, print, Job_Log row, no side effects) and `--now` (same plus its output action: an ntfy digest, or guarded writes that become `would_do` records in shadow);
- takes `--as-of <ISO>` so a run can be replayed at a fixed clock; library code never calls `datetime.now()` itself, the CLI injects `now`;
- writes one row per run through `shared.job_log.log_run(job, status, details)` (`.tmp/job_log.csv`; the `Job_Log` sheet tab only when `JOB_LOG_SHEET_ID` is set and the process is live, in shadow the append is a recorded intent). On Modal those files vanish with the container, so every row and shadow record is also written to the evidence Dict that `changesets/deploy/watch_report.py` reads. The scheduler adds its own row per run: `modal.<name>` on Modal, `laptop.<name>` from the laptop runner;
- imports only `shared.*` for API access, so every write is gated by `shared.settings.guard_write` (`MODE=shadow` default; `MODE=live` + `ALLOW_LIVE_WRITES=1` is the only live combination);
- runs from `Agentic Worklfows/` as `python3 jobs/<name>.py ...` (the script adds the repo root to `sys.path`) or `python3 -m jobs.<name>`.

## Jobs

Schedules are CT-native. On Modal, `modal.Cron` reads every expression in `America/Chicago`, so
nothing drifts on 2026-11-01 when CDT ends. On the laptop, launchd fires on the Mac's local time, so
the Mac must be on Central Time. `services/reply_engine/modal_app.py::SCHEDULES` is the single
source; `changesets/schedules/schedules.json` and the staged laptop files are generated from it by
`changesets/schedules/build_schedules.py`, and `--check` fails when they drift. This table is the
human copy, and `jobs/tests/test_one_system.py::test_every_scheduled_job_is_in_the_jobs_readme`
checks that every scheduled script in this folder has a row.

| Job | ID | Runs on / schedule (CT) | Reads | Writes | Runbook |
| --- | --- | --- | --- | --- | --- |
| `cadence_tick.py` | S2 | Modal: hourly 07:00-19:00 (`cadence_tick`) and 09:30 weekdays (`cadence_veto_ping`, the D1 veto window); both call `services/reply_engine/cadence.py`, this script is the CLI | store `lead:*`, Instantly threads | Instantly replies (guarded), ntfy digest | `runbooks/cadence_and_booking.md` |
| `appointments_tick.py` | S4/S5 | Modal: every 10 min; calls `services/reply_engine/show_rate.py`, this script is the CLI | GHL calendar events, store `appointment:*`, `joins:*` | GHL appointment status, SMS/email legs (guarded) | `runbooks/show_rate_and_no_show.md` |
| `precall_tick.py` | S6/S7 | Modal: every 5 min, with `--scheduled` | GHL appointments, `config/ids.json` calendar seed, lead facts CSV | GHL notes, proposal drafts (guarded); one container at a time on Modal (`max_containers=1`); its `.tmp/precall_tick.lock` covers one disk only | `runbooks/precall_and_proposal.md` |
| `inbox_placement.py` | O5 | Laptop: Mon 06:45 | `GET /inbox-placement-tests`, `POST /inbox-placement-analytics/stats-by-test-id` | `changesets/inbox_actions/<date>.json` + `last_placement.json` sidecar; never fires the credit-spending create | `runbooks/deliverability.md` |
| `autoresponder_canary.py` | O7 | Laptop: Sat 06:45 | `GET /emails?email_type=received`, `GET /block-lists-entries`, `POST /leads/list` | same dated change-set + `last_canary.json` sidecar | `runbooks/deliverability.md` |
| `deliverability_monitor.py` | O1 | Laptop: 07:00 daily | accounts, warm-up analytics, `accounts/test/vitals`, 28 days of `accounts/analytics/daily`, both sidecars | proposals into `changesets/inbox_actions/<date>.json`, ntfy card | `runbooks/deliverability.md` |
| `inbox_inventory.py` | M2/A5 | Laptop: 07:00 daily | Instantly accounts + campaigns + `accounts/analytics/daily` | inbox and domain health alerts (ntfy), `config/inbox_inventory.json`, promotion change-sets in `changesets/capacity/`; no reserve count or buying advice; nothing live | `runbooks/capacity.md` |
| `positive_sweep.py` | O3 | not scheduled; by hand only (its `--kpi` view) | delegates to `pipeline_sweep`, optional KPI block | none; leaves TWO Job_Log rows by design (its own and the sweep's) | `runbooks/metrics.md` |
| `pipeline_sweep.py` | O3 | Modal: 07:30 daily, the single scheduled sweep | Instantly `GET /emails` (received + manual), `POST /leads/list`; GHL proposals; store `appointment:*`, `confirmed:*`, `proposal:*`, `opptouch:*`; `.tmp/upwork_rooms.json` (on Modal that file does not exist, so the scheduled sweep never shows the Upwork rooms) | none (ntfy digest + Job_Log only) | `runbooks/pipeline_hygiene.md` |
| `upwork_rooms.py` | O2 | turned off 2026-09-22, run by hand (was 09:00 and 15:00 weekdays; `config/turned_off_jobs.json`) | `.tmp/upwork_rooms.json` (written by a Claude session; the MCP only exists there), `config/ids.json` | none; ntfy card + email digest | `runbooks/upwork_rooms.md` |
| `campaign_verdicts.py` | A7 | turned off 2026-09-22, run by hand (was Fri 15:00; `config/turned_off_jobs.json`) | `GET /campaigns/analytics`, `/analytics/steps`, `/analytics/daily`, `POST /leads/list` | `config/experiments.json` | `runbooks/experiments.md` |
| `retro_packet.py` | O6 | Laptop: Fri 16:00 | Instantly analytics + leads, GHL opportunities, git log, Job_Log, staged Fireflies pull, Rize CSV | markdown in `.tmp/retro/` + a `skool` would_do | `runbooks/retro.md` |
| `client_scorecard.py` | F3/F4 | Laptop: Fri 19:15 | Instantly `campaigns/analytics/daily` + `leads/list`, GHL won opportunities, the client roster | none (guarded gmail send + Job_Log) | `runbooks/fulfillment.md` |
| `daily_metrics.py` | O4 | Laptop: 18:00 daily | Instantly analytics, GHL stages, `.tmp/upwork_daily.json`, engine log/store | Google Sheets row (guarded), Skool post (staged, never auto-posted) | `runbooks/metrics.md` |
| `list_factory.py` | O8 | Laptop: Sun 09:00, as `--now --all-campaigns --refresh-suppression` | Apify or Google Maps, MillionVerifier, Anthropic, Instantly suppression reads | staged CSV per campaign + `create_lead` would_do records. Feeds every enabled campaign in `config/list_factory_targets.json`, Cleaning Reactivation first, (R10); `--now` without a source and verifier refuses to start. The laptop runner passes `ALLOW_PAID_CALLS=0` unless `LAPTOP_PAID_JOBS` in `.env` names `list_factory`; with paid calls off the Sunday run stages nothing and is recorded as `paid_calls_off`. **The only job gated by `ALLOW_PAID_CALLS`, and that flag ALONE opens its paid calls: live mode is not required, so a shadow run with the flag set spends real money (R7).** `ALLOW_PAID_CALLS=0` does NOT stop Anthropic spend: it gates only this job's own model calls, while `precall_tick.py`, `retro_packet.py` and the reply engine bill Anthropic through `shared/llm.py`, gated only by `LLM_FAKE` plus the $10 ceiling in `config/llm_budget.json` | `runbooks/list_factory.md` |
| `services/reply_engine/pipeline_sync.py` | S8 | Modal: 06:00 daily | GHL opportunities, Instantly leads | Instantly interest status, GHL upserts and notes (guarded) | `runbooks/pipeline_hygiene.md` |

Ordering that the schedule must preserve (`modal_app.SCHEDULE_ORDERING` pins it):
`inbox_placement` and `autoresponder_canary` write into the **same** dated change-set the
07:00 monitor writes, and the monitor reads their sidecars to build its card, so both run at
06:45, all three on the laptop (one disk). The laptop runner makes the 07:00 monitor wait for a
producer still running. (`campaign_verdicts` used to run at 15:00 before the 16:00 retro; it is turned off and run
by hand now, so the retro waits for nothing.)

### A flag inconsistency worth knowing
Most jobs use `--now` as the *action* flag with `--as-of <ISO>` for the clock. `cadence_tick.py`
and `precall_tick.py` use `--now <ISO>` as the *clock*. Passing an ISO timestamp to the wrong one
is silently accepted by argparse in one direction, so check the job before scripting it. New jobs
follow the `pipeline_sweep` convention.

## Pipeline sweep in one minute
```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 jobs/pipeline_sweep.py --dry-run                      # live, read-only, prints the ordered list
python3 jobs/pipeline_sweep.py --now                          # same plus the ntfy digest
python3 jobs/pipeline_sweep.py --dry-run --fixtures --as-of 2026-09-21T21:10:00-05:00   # offline replay
python3 -m pytest jobs/tests -q
```
Output order: booked calls (unconfirmed, inside 24 h) > positive replies awaiting Lorenzo (overdue at 24 h) > proposals untouched 7 days > Upwork rooms awaiting him. Inside a kind: pipeline value desc, then oldest wait (or soonest start for booked calls).

Sources the sweep cannot reach are skipped with a note in the digest rather than an error: no GHL token (`ghl_token_missing`), no `.tmp/upwork_rooms.json` (the Upwork MCP only exists in Claude sessions; a session can write that file for the job to read).

## Adding a job
1. Copy the shape of `pipeline_sweep.py`: pure functions that take data + `now`, one `run_*(now, ...)` that accepts injected clients/data for tests, and a `main(argv)` with `--dry-run` / `--now` / `--as-of`.
2. Read ids from `shared.settings` (`IDS`, `CAMPAIGNS`, `GHL_STAGES`), never hard-code them.
3. Tests in `jobs/tests/test_<name>.py` on recorded fixtures with `httpx.MockTransport`; the root `conftest.py` already forces shadow mode, faked LLM, `NOTIFY=off` and a temp `.tmp/`.
4. Register the schedule in `services/reply_engine/modal_app.py` (`SCHEDULES`, with its tier and runtime; a Modal job also needs a function), regenerate with `python3 changesets/schedules/build_schedules.py`, and document it in a runbook under `runbooks/`. A job that hands off through files runs on the laptop.
5. Shadow for 48 hours before anything flips to live.
