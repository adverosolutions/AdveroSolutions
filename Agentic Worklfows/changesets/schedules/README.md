# changesets/schedules: every schedule, as data, split between Modal and the laptop

Nothing here has been installed or deployed. `schedules.json` is the complete
list of what runs, when, in which tier, on which runtime, and whether it is
safe to leave running in shadow. It is generated from
`services/reply_engine/modal_app.py` `SCHEDULES`, the one source of truth.

## Files

| File | What it is |
| --- | --- |
| `schedules.json` | The data. Generated, not hand-written. Every entry has `tier` and `runtime`. |
| `build_schedules.py` | Generates `schedules.json` and the staged laptop files. `--check` fails if any of them is stale or the Modal-vs-laptop split is wrong; `--check-image` imports every deployed module from a copy of exactly the Modal mounts. The test suite runs both. |
| `install_schedules.sh` | `--preflight` (reads only) and `--deploy shadow\|live [--first-pass]` (asks first, deploys the Modal half, then checks `/health`). Not run. |
| `laptop_runner.py` | Runs ONE laptop schedule once, records it, alerts on failure. `--self-test` records a harmless run (the step 2c kick-start). |
| `laptop/*.plist`, `laptop/crontab.txt` | STAGED launchd agents and crontab lines for the laptop schedules, plus `com.advero.self_test.plist` (no schedule; started by hand). Not installed. |
| `laptop_store_keys.py` | Reads the laptop jobs' code and prints every store key they can write (runbooks/deployment.md step 7). |
| `../../config/turned_off_jobs.json` | Jobs Lorenzo turned off and runs by hand; `--check` refuses one that is still scheduled. |

## The split (owner decisions R3 and R4)

**Modal, sales tier only (8 schedules):** `poller`, `approval_escalation`,
`cadence_tick`, `cadence_veto_ping`, `appointments_tick`, `precall_tick`,
`pipeline_sync`, `pipeline_sweep`. `modal deploy` registers the Modal schedules
of the tiers in `DEPLOY_TIERS` (default `sales`), plus the web endpoint. Tiers
are added one redeploy at a time, and the list must keep `sales`
(`DEPLOY_TIERS=sales,marketing`), because a deploy replaces the whole app.

**Laptop (8 schedules):** every job that hands work to another job through
files. Each Modal function runs in its own throwaway container with nothing
shared on disk, so those hand-offs silently broke on Modal:

| Schedule | Tier | Why it is on the laptop |
| --- | --- | --- |
| `inbox_placement` 06:45 Mon | marketing | writes the level-2 sidecar and change-set the 07:00 monitor reads |
| `autoresponder_canary` 06:45 Sat | marketing | writes the level-4 sidecar and change-set the 07:00 monitor reads |
| `deliverability_monitor` 07:00 | marketing | reads both sidecars, writes proposals Lorenzo reviews on disk |
| `inbox_inventory` 07:00 | marketing | inbox and domain health alerts only; the scheduled `--now` writes `config/inbox_inventory.json` (kept as it was when an active inbox has no analytics), one digest and a Job_Log row; only a hand-run `--promote` writes a change-set to `changesets/capacity/` |
| `list_factory` 09:00 Sun | marketing | stages a CSV and keeps its run state, ledger and suppression files on disk |
| `retro_packet` 16:00 Fri | ops | reads the Job_Log from disk and writes `.tmp/retro/` |
| `daily_metrics` 18:00 | ops | reads the list-factory ledger and the Job_Log from disk |
| `client_scorecard` 19:15 Fri | fulfillment | needs the client roster and templates on disk |

`positive_sweep` is no longer scheduled (GOL-13): it only delegates to
`pipeline_sweep`, so both at 07:30 pushed two identical digests and read
`GET /emails` twice beside the poller. It stays available as a CLI.

## Turned off (Lorenzo, 2026-09-22)

`campaign_verdicts` (was Fri 15:00) and `upwork_rooms_am` / `upwork_rooms_pm`
(were 09:00 and 15:00 on weekdays) are no longer scheduled anywhere: not in
`modal_app.SCHEDULES`, not in `schedules.json` `schedules`, and with no plist
or crontab line. Lorenzo runs them by hand. Their code stays.
`config/turned_off_jobs.json` names them, with the by-hand command;
`schedules.json` lists them under `turned_off`, and `--check` fails if one is
scheduled again or its module is gone. The retro packet, the pipeline sweep,
the daily metrics row and the watch report show them as "turned off", never
missing or failed. If an old plist is still loaded, the runner runs nothing,
records `turned_off` and sends one normal-priority note a day with the unload
commands (runbooks/deployment.md step 2c).

## The laptop runner

The staged files call `python3 changesets/schedules/laptop_runner.py <name>`.
For each run it:

- runs the job with `MODE=shadow ALLOW_LIVE_WRITES=0` unless the job's tier is
  in `LAPTOP_LIVE_TIERS` (comma list in `.env`, empty by default). The `.env`'s
  own `MODE` is ignored for scheduled laptop jobs, so one tier goes live at a
  time. `LAPTOP_LIVE_TIERS` and `LAPTOP_PAID_JOBS` are live switches: the
  runner reads them only from the saved `.env` files, never from the shell
  (a differing shell value is ignored and noted in the run record), and does
  not pass them on to the job;
- sets `ALLOW_PAID_CALLS=0` unless the job is in `LAPTOP_PAID_JOBS`. That flag
  alone gates paid calls, in shadow as well as live (owner decision R7), and it
  does not stop Anthropic spend anywhere else;
- takes a per-job lock, and makes the 07:00 monitor and the 16:00 retro wait
  (up to 30 minutes) for a producer due today that is still running;
- runs the job ONCE and records one line in `.tmp/laptop_runs/runs.jsonl` and
  one Job_Log row `laptop.<name>` with the exit code. A non-zero exit (several
  jobs exit 1 on a partial run) is `failed` plus a high-priority push. Nothing
  retries: the plists carry no `KeepAlive`;
- records a designed outcome instead of `ok` when the job prints
  `ADVERO_OUTCOME=<outcome>` and exits 0. The only one today is
  `paid_calls_off`: the Sunday list factory with `ALLOW_PAID_CALLS=0` stages
  nothing, sends one normal-priority note and exits 0. The watch report counts
  `ok`, `paid_calls_off`, `turned_off` and `self_test_ok` as healthy.

launchd writes each agent's own log to `~/Library/Logs/advero/launchd_<name>.log`,
outside `~/Desktop`, which macOS privacy protection guards: a run refused
access to the repo still leaves its error there. Use the plists OR the crontab, never both. launchd runs a job missed while the
Mac slept once it wakes; cron skips it. Both fire on the Mac's local clock,
which must be Central Time (the runner alerts once a day if it is not).
Installing them is Lorenzo's step, in `runbooks/deployment.md`.

## Timezones, and the one trap

`cron_ct` is what is scheduled. `modal.Cron` reads it in `America/Chicago`, so
the CT times are literal and **nothing moves on 2026-11-01** when CDT ends.

`cron_utc_cdt` and `cron_utc_cst` are there only for a scheduler that cannot
take a timezone (GitHub Actions). Both are given because **one of them is wrong
for half the year**: a job pinned to a fixed UTC cron shifts by an hour on
2026-11-01 and again on 2027-03-14. The 18:00 CT daily metrics run at
`0 23 * * *` UTC becomes 17:00 CT in November and then misses the last hour of
the sending day, every day, silently.

The generator refuses to guess where a shift would change the day, and says so
in the field instead:

- `cadence_tick` (`0 7-19 * * *`) becomes a range that crosses midnight UTC and
  has to be split into two entries by hand.
- `client_scorecard` (19:15 CT Fri) and `daily_metrics` (18:00 CT, in CST) land
  on the **next** UTC day, so the day-of-week field has to move with the hour.

## Ordering that matters

Two pairs are not independent, and `modal_app.SCHEDULE_ORDERING` pins them.
All three jobs run on the laptop, on one disk, and `--check` refuses a pair split
across runtimes:

| Runs first | Must be before | Why |
| --- | --- | --- |
| `inbox_placement` 06:45 Mon | `deliverability_monitor` 07:00 | Level 2 writes its proposals into the **same dated change-set** the monitor writes, and the monitor reads its sidecar to build the card. |
| `autoresponder_canary` 06:45 Sat | `deliverability_monitor` 07:00 | Same, for level 4. |

## Mode

Every entry is `mode: shadow`. A schedule in shadow proposes, logs and
notifies Lorenzo; it writes nothing to Instantly, GHL, Sheets or anywhere else.
On Modal, `MODE=live` plus `ALLOW_LIVE_WRITES=1` in the secret (written only by
`changesets/deploy/modal_secret.py`) is the only combination that writes. On
the laptop the runner sets that pair per job, only for a tier in
`LAPTOP_LIVE_TIERS` as saved in `.env` (never the shell).

`shadow_safe` is `true` for 15 of the 16 schedules. The exception is
`list_factory`: **shadow does not cover paid calls.** Apify, Perplexity,
MillionVerifier and the factory's own model calls spend the moment
`ALLOW_PAID_CALLS=1`, live or not. The runner keeps it `0` unless
`LAPTOP_PAID_JOBS` names the job, which waits for Lorenzo to approve a figure
(about $55 a run, `DECISIONS_FOR_LORENZO.md` M3).

## Regenerating

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/schedules/build_schedules.py                 # rewrite schedules.json and laptop/
python3 changesets/schedules/build_schedules.py --check         # exit 1 if stale or the split is wrong
python3 changesets/schedules/build_schedules.py --check-image   # the image-side import check
bash changesets/schedules/install_schedules.sh --preflight
```

## Rollback

`python3 -m modal app stop advero-reply-engine` removes all 8 Modal schedules at once,
and the web endpoint with them. The Modal Dicts survive a stop. To remove one
Modal tier, redeploy with a shorter `DEPLOY_TIERS`. To stop a laptop job,
unload its plist (`launchctl bootout gui/$(id -u)/com.advero.<name>`) and then
remove it from `~/Library/LaunchAgents/` (or launchd loads it again at the next
login), or delete its crontab line.
