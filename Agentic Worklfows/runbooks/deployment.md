# Runbook: reply engine deployment (shadow first, one tier at a time)

## Purpose
Take the revenue engine from the laptop to production without touching a live system before Lorenzo has watched it propose the right actions for 48 hours. The order is fixed:

1. local checks;
2. the Modal secret and the shadow deploy of the **sales tier** (the only tier on Modal), plus the laptop runner for everything else, all in shadow;
3. the 48-hour shadow watch, read from the deployed store;
4. Lorenzo's approval;
5. the cutover and the live flip of the sales tier;
6. the Instantly webhooks (optional; the poller already reads replies);
7. the laptop tiers, one at a time.

`MODE=shadow` (the default) proposes, logs and notifies. Only `MODE=live` together with `ALLOW_LIVE_WRITES=1` lets `shared.settings.guard_write` return `shadow: False`. On the laptop, two more switches act like live flags for the scheduled jobs: `LAPTOP_LIVE_TIERS` (which tiers run live) and `LAPTOP_PAID_JOBS` (which jobs may spend). The laptop runner reads both only from the saved `.env`, never from the shell, so a prefix such as `LAPTOP_LIVE_TIERS=marketing python3 ...` changes nothing. **Lorenzo runs every command below from his own terminal.** Do not count on the Claude Code hook to stop an agent: it only matches command text and does not run from every folder. What protects the live systems is the mode in the Modal secret and the per-job mode the laptop runner sets.

**Working directory for every command in this runbook:**

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
```

Files: `services/reply_engine/modal_app.py` (app `advero-reply-engine`, the one source of truth for every schedule), `changesets/schedules/` (the schedule data, `install_schedules.sh`, the laptop runner and its staged files), `changesets/deploy/` (the secret, health, watch, cutover, budget and log tools).

## What runs where (owner decisions R3 and R4)

| Where | Tier | Schedules |
| --- | --- | --- |
| Modal | sales | `poller`, `approval_escalation`, `cadence_tick`, `cadence_veto_ping`, `appointments_tick`, `precall_tick`, `no_show_watch`, `pipeline_sync`, `pipeline_sweep` (9 crons + 1 web endpoint) |
| Laptop | marketing | `inbox_placement`, `autoresponder_canary`, `deliverability_monitor`, `inbox_inventory`, `list_factory` |
| Laptop | ops | `retro_packet`, `daily_metrics` |
| Laptop | fulfillment | `client_scorecard` |
| Turned off | (by hand) | `campaign_verdicts`, `upwork_rooms_am`, `upwork_rooms_pm` |

Laptop jobs hand work to each other through files (sidecars, change-sets, `config/*.json`, the list factory's ledger, the Job_Log), which cannot work across Modal's throwaway containers. `positive_sweep` is not scheduled: `pipeline_sweep` is the single 07:30 O3 run. `changesets/schedules/README.md` has the reasons per job.

**Turned off (Lorenzo, 2026-09-22).** `campaign_verdicts` (was Fri 15:00) and the Upwork rooms digests `upwork_rooms_am` / `upwork_rooms_pm` (were 09:00 and 15:00 on weekdays) are no longer scheduled anywhere: not on Modal, no plist, no crontab line. Lorenzo runs them by hand; their code stays. `config/turned_off_jobs.json` names them with the by-hand command, and `build_schedules.py --check` fails if one is scheduled again. The retro packet, the 07:30 sweep, the daily metrics row and the watch report show them as "turned off", never missing or failed. Nothing scheduled shows the Upwork rooms any more (the 07:30 sweep on Modal cannot read `.tmp/upwork_rooms.json`).

Four Dicts on Modal, never shared (owner decision R5, review item 8): the engine stores `advero-reply-engine-store-shadow` and `advero-reply-engine-store-live`, and the evidence stores `advero-reply-engine-obs-shadow` and `advero-reply-engine-obs-live` (every Job_Log row and shadow record a container writes). A container picks the pair for its effective mode, so the watch cannot leave used cadence days, reserved slots or a moved poller cursor behind for live, and evidence never sits in an engine store. **Modal deletes a Dict entry after 7 days with no read or write** (modal 1.2.6, `modal/dict.py`): evidence lasts 7 days, and an engine store left idle that long loses its keys, the poller cursor and `cutover:record` included. Single keys also expire while the app runs: a key nothing reads or writes for 7 days is deleted. Lead records survive (the hourly cadence reads every one); reply claims, no-show counts and other keys touched once do not.

## Step 1: local checks

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m pytest -q
python3 -c "import services.reply_engine.modal_app"          # imports offline, contacts nothing
bash changesets/schedules/install_schedules.sh --preflight
```

The preflight runs five automated checks (1 to 5), prints two it cannot do (6), then runs the two template checks (7 and 8, below). When all of them pass it writes `.tmp/deploy/preflight_ok.json`: a SHA-256 of every file the Modal image carries, with the time. The live flip in step 5 accepts that stamp for 60 minutes, on unchanged code only (`changesets/deploy/preflight_stamp.py check`). Nothing else writes a stamp: `preflight_stamp.py` has no write command, and the preflight writes it only as its last step, after checks 1 to 5, 7 and 8 passed. Check 6 is the two it cannot do, marked **NOT CHECKED**: the secret's mode (Modal shows no secret values) and the Modal plan quota. For the quota it prints what this deploy registers (9 crons and 1 web endpoint for the sales tier). Open modal.com, Settings, Plan for the `adverosolutionsbackup` workspace and confirm the plan allows that many before step 2.

**Check 7, template parity.** `changesets/deploy/template_parity.py --write` rebuilds the cold-email template catalogue on this laptop and writes the reference file `config/template_catalogue_hashes.json`: the catalogue digest, the id-to-sha256 map of every approvable template, and the python, pytz and pydantic versions it was built with (ids and hashes only, never text). `--check` then rebuilds it and compares; any difference refuses the deploy. `config/` is mounted into the Modal image, so the reference travels with the code, and the deployed app (Python 3.11) compares its own catalogue with it (`services/reply_engine/template_gate.parity_status`). A mismatch, a missing reference or an error turns template auto-send off everywhere (every reply becomes a card, every cadence, show-rate and no-show message is held) and sends one urgent push a day. `/health` reports it as `templates.parity`, and `changesets/deploy/verify_health.py` fails the deploy unless it is `ok` (it polls again while it is `not_ready`, the app still loading). The first `--write` creates the reference as a new, untracked file; after that every preflight rewrites it (at least its `generated_at` line), so commit it with the code it was built from. The script never writes `config/approved_templates.json`.

**Check 8, unapproved ladder templates.** `template_parity.py --report-unapproved` prints the cadence, show-rate and no-show ids that are not approved at their current text, the ones the catalogue could not render, and the kill switch as this laptop sees it (the Modal secret's `AUTO_SEND_TEMPLATES` is not visible from here). It warns when the kill switch is on. While either count is not 0 it asks you to type `HOLD` at the terminal (with no terminal it stops). Deployed like that, every message that uses one of those ids is held, not sent, and a show-rate or no-show message whose send time passes while held is dropped. Approve the ladder ids first (`runbooks/template_approvals.md`, "Approve the ladder templates before deploying CT3").

Offline replays, if wanted:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 jobs/pipeline_sweep.py --dry-run --fixtures --as-of 2026-09-21T21:10:00-05:00
python3 -m services.reply_engine.pipeline_sync --dry-run --fixtures
```

## Step 2: the secret and the shadow deploy

### 2a. The secret, from .env and ~/.advero/live.env

One script builds the secret, now and for every later re-create: `changesets/deploy/modal_secret.py`. It reads `Agentic Worklfows/.env`, then `AdveroSolutions/.env` (first one wins), except the two write-capable keys: those it takes from `~/.advero/live.env` first (outside the repo, chmod 600), then the shell environment, then `.env`, with a note to move a write key it still finds in `.env` (`changesets/deploy/modal_secret.py:13-21`, `overlay_write_keys`). It prints key names and value lengths only, and refuses when a required key is missing, a value looks like a placeholder, or no channel can carry an approval card's buttons. Blank optional keys are left out, never sent empty. It writes the secret only with `--create` and the word `CREATE` typed on the terminal.

Before the first run, put each key in its place as `runbooks/read_only_keys.md` step 3 describes (decision R2(a); the names are the table in `shared/keys.py`). The write-capable `INSTANTLY_API_KEY` and `GHL_PRIVATE_INTEGRATION_TOKEN` go in `~/.advero/live.env`, never in either repo `.env`, which agent sessions can read; the repo `.env` gets their read-only variants `INSTANTLY_API_KEY_READ` and `GHL_PRIVATE_INTEGRATION_TOKEN_READ` instead, which the laptop and agent sessions read with and the secret does not carry. `.env` must hold, with real values: `ANTHROPIC_API_KEY`, `NTFY_TOPIC` (the topic the phone is subscribed to), `NTFY_ALLOW_SENSITIVE` (`0` or `1`, DECISIONS C7) and `REPLY_ENGINE_SECRET`. Plus either `NTFY_TOKEN` or `NTFY_ALLOW_SENSITIVE=1`, or all three of `GMAIL_SENDER_EMAIL`, `GMAIL_APP_PASSWORD` and `NOTIFY_EMAIL`; without one of those, every Approve button is stripped from the push and nothing else carries it.

`REPLY_ENGINE_SECRET` lives in `.env` and nowhere else, and it is never regenerated once it exists: the six webhooks and every outstanding approval link carry it. If `.env` has none yet, add one once with `python3 -c "import secrets;print(secrets.token_hex(24))"`. If an old `.tmp/reply_engine_secret.txt` exists with a different value, the script refuses until one of them is gone.

`.env` also carries a placeholder `GOOGLE_CREDENTIALS_JSON` (`paste_your_json_here`). The script refuses it. Put the real service-account JSON there, or delete the line, before the first run.

Where each key comes from:

| Key | Source |
| --- | --- |
| `INSTANTLY_API_KEY` | `~/.advero/live.env`, else the shell environment, else `.env` (noted: move it); required (refuses without it). See `runbooks/read_only_keys.md` |
| `GHL_PRIVATE_INTEGRATION_TOKEN` | `~/.advero/live.env`, else the shell environment, else `.env` (noted: move it); required (refuses without it). See `runbooks/read_only_keys.md` |
| `ANTHROPIC_API_KEY` | `.env`, required (refuses without it) |
| `NTFY_TOPIC` | `.env`, required (refuses without it) |
| `REPLY_ENGINE_SECRET` | `.env`, required (refuses without it) |
| `MODE` | `--mode` |
| `ALLOW_LIVE_WRITES` | `--mode` (`1` only for live) |
| `NOTIFY_SHADOW_SEND` | always `1` (pushes to Lorenzo only) |
| `GMAIL_SENDER_EMAIL` | `.env` when set, else left out |
| `GMAIL_APP_PASSWORD` | `.env` when set, else left out |
| `NOTIFY_EMAIL` | `.env` when set, else left out |
| `JOB_LOG_SHEET_ID` | `.env` when set, else left out |
| `GOOGLE_CREDENTIALS_JSON` | `.env` when set (validated: a service account with `client_email` and `private_key`), else left out |
| `BASE_URL` | `--base-url`, else a public https `BASE_URL` in `.env`; left out on the first pass |
| `REPLY_ENGINE_BASE_URL` | = `BASE_URL` |
| `WEBHOOK_SECRET` | = `REPLY_ENGINE_SECRET` |
| `DEBUG_SECRET` | = `REPLY_ENGINE_SECRET` |
| `ZOOM_WEBHOOK_SECRET` | `.env` when set, else left out |
| `ZOOM_URL_VALIDATION` | `.env` when set, else left out |
| `A2P_10DLC_REGISTERED` | `.env`, else `0` |
| `NTFY_TOKEN` | `.env` when set, else left out |
| `NTFY_ALLOW_SENSITIVE` | `.env`, required (refuses without it) |
| `CADENCE_D6_HOLD` | `.env`, else `0` |
| `SHOW_RATE_SENDER` | `.env` when set, else left out |
| `AUTO_SEND_AFTER_MINUTES` | `.env` when set, else left out. The old timer auto-approve: nothing calls `approval.auto_send_due`, and the CT3 template auto-send does not read it |
| `LOOM_URL_GENERIC` | `.env` when set, else left out |
| `LOG_LEVEL` | `.env` when set, else left out |
| `AUTO_SEND_TEMPLATES` | `.env` when set, else left out. Any value but `1`/`on`/`true`/`yes` is the kill switch for approved-template auto-send (`runbooks/template_approvals.md`); it only ever turns sends off. Since CT3 the switch takes effect: with the switch off (this key unset or `1`, and no `"auto_send"` other than `true` in `config/approved_templates.json`), a reply, booking email or ladder message whose text is exactly an approved template goes out with no per-email Approve; with it on, every reply becomes a card and every cadence, show-rate and no-show message is held, including the reminders before a booked call. A change reaches only new containers, so re-create the secret and redeploy. An empty value (`AUTO_SEND_TEMPLATES=`) is sent as `off`, not left out: the laptop already reads empty as the kill switch, and left out, Modal would read it as not set and keep auto-send on. A bare `AUTO_SEND_TEMPLATES` with no `=` counts as not set on both sides |
| `ALLOW_PAID_CALLS` | always `0` (no Modal job spends through it) |
| `APIFY_API_TOKEN` | not sent: only the list factory uses it, and it runs on the laptop |
| `APIFY_TOKEN` | not sent: only the list factory uses it, and it runs on the laptop |
| `FIREFLIES_API_KEY` | `.env` when set, else left out |
| `PAYMENT_LINK_URL` | `.env` when set, else left out (unset, every SOP-009 draft is unsendable) |
| `DAILY_METRICS_SHEET_ID` | `.env` when set, else left out |
| `SKOOL_GROUP` | `.env` when set, else left out |
| `SKOOL_GROUP_ID` | `.env` when set, else left out |

`ALLOW_PAID_CALLS` gates Apify, Perplexity, MillionVerifier and the list factory's own model calls, alone: live mode is not required, a shadow run with it set spends (owner decision R7). It does not stop Anthropic spend anywhere else; the reply engine, `precall_tick` and `retro_packet` are capped only by `config/llm_budget.json`. No Modal schedule uses it, so the secret always carries `0`.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m modal profile activate adverosolutionsbackup
python3 changesets/deploy/modal_secret.py --mode shadow               # the plan: names and lengths, writes nothing
python3 changesets/deploy/modal_secret.py --mode shadow --create      # type CREATE; no BASE_URL yet (first pass)
```

### 2b. Deploy, then the second pass with the URL

The web URL is only known once the first deploy prints it. `install_schedules.sh --deploy` saves it from the deploy's own output to `.tmp/deploy/web_url.txt` (`modal app list` prints no URLs) and then checks `/health`.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
# first pass: expects mode shadow; BASE_URL is not in the secret yet, so that one check is skipped.
# It records the hand-off start before deploying. A NEW watch (not a retry) adds --new-watch.
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow --first-pass
# second pass: the same script re-creates the whole secret, now with the URL, then redeploy
python3 changesets/deploy/modal_secret.py --mode shadow --base-url "$(cat .tmp/deploy/web_url.txt)" --create
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow
```

The second `--deploy` must end with `All /health checks passed ... in shadow mode`. `/health` has to report `mode: shadow`, `live: false`, `base_url_set: true`, a webhook secret, the GHL token and `approval_channels.any: true`, and the BASE_URL host the last `modal_secret.py --create` wrote (recorded in `.tmp/deploy/secret_history.jsonl`) must be the host of the URL just checked: `/health` only says yes or no. To re-run only the check: `python3 changesets/deploy/verify_health.py --expect-mode shadow`.

`--base-url ""` (what `$(cat .tmp/deploy/web_url.txt)` gives when the file is missing) is refused; it never falls back to `.env` or to a first pass.

**Two clocks, never one** (`changesets/deploy/watch_clock.py`):

- the **hand-off start**, `.tmp/deploy/handoff_start.txt`. The first-pass deploy records it just before `modal deploy`, so it is at or before the first reply the shadow poller can see. It never moves: a retried first pass keeps it. Step 5 passes it to the cutover, so every reply the shadow engine saw is on the hand-off list. A new watch (weeks later, or after a rollback) starts with `--first-pass --new-watch`, which moves the old files to `.tmp/deploy/watch_archive/<time>/`; without it, a hand-off start older than 7 days is refused, not reused.
- the **report start**, `.tmp/deploy/report_start.txt`, set by hand in step 2d once the app is up and settled. The watch report reads this one. Crons due while the image builds, between the two passes, while the laptop agents go in and while the backlog drains are outside the gate.

`python3 changesets/deploy/watch_clock.py show` prints both.

**What the first shadow poll costs.** The shadow store starts with no poller cursor, so the first poll walks back up to 20 pages of 100 received emails (2,000 at most) and processes every reply in the six campaigns it finds. Every role runs on Claude Opus 5.5 ($4 in / $20 out per million tokens, thinking always on at effort `low`). Each reply is a classification (about 2,000 prompt tokens: about $0.015 with a few hundred thinking tokens, up to $0.035 if it uses the whole 1,024-token thinking headroom), about one in four is escalated (the same again), and each positive gets a draft (about $0.03, up to $0.047) and **one approval card on the phone**. **A 2,000-reply backlog costs roughly $30 or more** (2,000 classifications at about $0.015 are $30 before escalations and drafts; up to about $90 if every call used the full headroom). **That trips the $10 cap in `config/llm_budget.json` during the first poll**, after a few hundred replies. Past the cap every model call is refused, and a reply classified while the cap is hit gets the fallback label (`neutral_question`, "LLM unavailable; routed to Lorenzo for review") and a card, not a real classification. The $8 warning and the $10 stop each push once per counter period, shared by every container through the store (see step 3, "When the budget cap is hit").

So count the backlog first (the command below prints the received emails scanned) and, if it holds more than a few hundred replies, pick one of these before the first-pass deploy. Do not change the $10 cap value in the repo as part of this:

- **Raise the cap for the first poll, with Lorenzo's OK.** Price the backlog at about $0.02 per reply (more with many positives), set `budget_usd` in `config/llm_budget.json` to cover it, deploy, and once the shadow poller has its first cursor put `budget_usd` back to `10.0` and redeploy. The file is baked into the image, so both changes are redeploys (`DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow`).
- **Backfill in slices, with Lorenzo's OK for each reset.** Each poll takes new replies for 120 seconds only (see below), so the backlog drains in slices of a few dollars. Watch `python3 changesets/deploy/budget.py status --store-mode shadow`; when the $8 warning pushes, reset the counter between polls (`python3 changesets/deploy/budget.py reset --store-mode shadow`, type `RESET`) before it reaches $10, and repeat until the first cursor exists. A reset after the stop is too late for the replies already given the fallback label. Backlog cards are old replies: veto them or let them expire. They were received before the hand-off start, so they are not on the step 5 hand-off list.

**The backlog drains over several polls, not in one.** Each scheduled poll stops taking new replies after 120 seconds (`modal_app.POLLER_TIME_BUDGET_S`, half its 240-second timeout), reports the scan as truncated so the cursor stays where it was, and the next poll, 5 minutes later, carries on from there. A reply is never skipped: a poll that is killed in the middle of one leaves it claimed, the following polls pass it over as `in_flight` (not marked seen, cursor held), and it is processed once the claim is 15 minutes stale. The shadow poller has its first cursor only when a whole scan completes, that is, once the backlog is through; step 2d waits for that. (If the account holds more than 20 pages of received email, the first scan never completes; see Open. So before any first-pass deploy on a shadow store with no cursor, count the received email first, read-only:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -c "from shared.instantly import default_client; from services.reply_engine import poller; r = poller.fetch_new_replies(default_client(), None, [], {}); print('received emails scanned:', r['fetched'], 'pages:', r['pages'], 'more than 20 pages:', r['truncated'])"
```

It must print `more than 20 pages: False`. On 2026-09-22 the account held 115 received emails (`runbooks/list_factory.md`), so one or two pages. If it prints `True`, do not deploy: STOP and ask.)

Optional, to see rows land before waiting for the crons (still shadow):

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
DEPLOY_TIERS=sales python3 -m modal run services/reply_engine/modal_app.py::pipeline_sweep
python3 changesets/deploy/watch_report.py --min-hours 0 --skip-laptop
```

Logs, bounded (`modal app logs` itself streams until stopped). These are for reading by eye: a short read cannot prove something never happens in 5-minute jobs. In shadow, the proof that approval cards carry a working link is `verify_health.py` at the second pass: it passes only when `/health` reports `base_url_set: true` and the BASE_URL host the last `modal_secret.py --create` recorded is the host of the URL it just checked. The watch report cannot prove it in shadow: its `d1_held_no_base_url` and `d6_card_no_base_url` statuses are never written in shadow. Step 2d refuses to start the report clock until that second-pass check has passed.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/bounded_logs.py --seconds 360           # a little over one 5-minute cycle
```

### 2c. The laptop runner (staged; Lorenzo installs it)

The laptop schedules run through `changesets/schedules/laptop_runner.py`. For every scheduled laptop job it sets `MODE=shadow ALLOW_LIVE_WRITES=0` unless the job's tier is named in `LAPTOP_LIVE_TIERS`, and `ALLOW_PAID_CALLS=0` unless the job is named in `LAPTOP_PAID_JOBS`. Both are read only from the saved `.env` files (never the shell; a differing shell value is ignored and noted in the run record) and are empty today; the `.env`'s own `MODE` is ignored for these jobs. It runs the job once, records `.tmp/laptop_runs/runs.jsonl` and a `laptop.<name>` Job_Log row with the exit code, and pushes a high-priority alert on a non-zero exit (several jobs exit 1 on a partial run). Nothing retries. A job that exits 0 after printing `ADVERO_OUTCOME=<outcome>` is recorded with that designed outcome instead of `ok`; the only one is `paid_calls_off`, below.

**The Sunday list factory while paid calls are off** (today, until Lorenzo approves `LAPTOP_PAID_JOBS=list_factory`): the 09:00 Sunday run stages nothing, sends one normal-priority note, exits 0 and is recorded as `paid_calls_off`, which the watch accepts. With paid calls on, a blocked run still fails with a high-priority push.

The Mac's clock must be on Central Time (`date +%Z` prints `CDT` or `CST`): launchd fires on local time.

**macOS folder access.** The repo lives under `~/Desktop`, which macOS privacy protection guards. A python started by launchd (not by Terminal) may be refused access to it: the job then never starts and leaves no `runs.jsonl` row, only `Operation not permitted` in its launchd log. The plists therefore write their launchd logs to `~/Library/Logs/advero/`, outside the guarded folders, and the kick-start below proves access before the watch relies on it. It kick-starts `com.advero.self_test`, an agent with no schedule that runs no job: `laptop_runner.py --self-test` reads `schedules.json` from the repo and records one `self_test_ok` row. Its plist sets `ADVERO_STARTED_BY=launchd`, which the row records as `started_by: launchd`; a self-test typed in Terminal records `started_by: hand` and does not count for step 2d. If the kick-start leaves no new `runs.jsonl` row, open System Settings, Privacy & Security, Full Disk Access, and add the interpreter printed by `/usr/bin/python3 -c "import sys; print(sys.executable)"` (and `/usr/bin/python3` itself), then kick-start again. (Unverified on this Mac; the kick-start is the test.)

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
date +%Z                                                                  # CDT or CST
python3 changesets/schedules/build_schedules.py --check
python3 changesets/schedules/laptop_runner.py deliverability_monitor --plan   # prints the child mode; runs nothing
python3 changesets/schedules/laptop_runner.py --self-test                     # by hand: runs no job; started_by "hand", not enough for 2d
mkdir -p .tmp/laptop_runs ~/Library/Logs/advero
for f in changesets/schedules/laptop/com.advero.*.plist; do
  cp "$f" ~/Library/LaunchAgents/
  launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/"$(basename "$f")"
done
launchctl list | grep com.advero                                         # 9 agents: the 8 laptop schedules and self_test
# prove launchd itself can run the runner: kick-start the self-test agent, then read its row
wc -l < .tmp/laptop_runs/runs.jsonl
launchctl kickstart -k "gui/$(id -u)/com.advero.self_test"
sleep 30; tail -1 .tmp/laptop_runs/runs.jsonl                            # a NEW self_test row: self_test_ok, started_by launchd, clock_is_central true
cat ~/Library/Logs/advero/launchd_self_test.log                            # the same record, printed
```

**Remove the three turned-off agents** if an earlier install loaded them (commands only; Lorenzo runs them). Until they are gone, a loaded one runs nothing: the runner records `turned_off` and sends one normal-priority note a day with these commands.

```bash
for name in campaign_verdicts upwork_rooms_am upwork_rooms_pm; do
  launchctl bootout "gui/$(id -u)/com.advero.$name" 2>/dev/null || true   # unload; "not found" is fine
  rm -f ~/Library/LaunchAgents/com.advero.$name.plist                     # or launchd loads it again at the next login
done
launchctl list | grep -E 'com\.advero\.(campaign_verdicts|upwork_rooms_am|upwork_rooms_pm)'   # prints nothing
crontab -l 2>/dev/null | grep -E 'campaign_verdicts|upwork_rooms'       # crontab users: prints nothing, else crontab -e and delete those lines
```

Install the agents before step 2d: the report start waits for a laptop run recorded after the hand-off start (the kick-start above), and the watch report compares every laptop run due after the report start with the runs recorded.

Use the plists or `changesets/schedules/laptop/crontab.txt`, never both. launchd runs a job missed while the Mac slept once it wakes; cron skips it. The runner makes the 07:00 monitor wait for a producer still running (the Monday placement test, the Saturday canary) and records `ordering_not_met` when one did not run that day.

### 2d. Start the report clock

Once the second pass has passed `/health`, the laptop agents are in and kick-started, and the first-poll backlog has drained:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 jobs/inbox_inventory.py --dry-run                      # read-only; must not end partial (see Open)
python3 changesets/deploy/watch_clock.py show
python3 changesets/deploy/watch_clock.py start-report          # refuses, and says why, until all three hold
```

`partial` stays a failure in the watch. If the inbox inventory dry run ends `partial`, fix that cause before starting the report clock; if it keeps recurring, run the sales watch without the laptop half (`start-report --skip-laptop`, and the watch report with `--skip-laptop`).

`start-report` refuses unless: the newest `verify_health.py` result (each run appends one to `.tmp/deploy/health_history.jsonl`) is a passing second-pass shadow check newer than the hand-off start; a `self_test_ok` row started by launchd with `clock_is_central: true` is recorded since the hand-off start, that is, the 2c kick-start (`--skip-laptop` for a Modal-only watch); and the shadow engine store holds a complete `poller:cursor` (a completed scan: the backlog is through). It runs nothing and writes only `.tmp/deploy/report_start.txt` and a history line. The 48 hours count from the report start. It is set once; it moves only with `--restart --reason "<the cause>"`, after a failure whose cause is known (step 3), and only later, never earlier.

## Step 3: the 48-hour shadow watch

**Where the evidence is.** Each Modal function runs in its own throwaway container, so nothing on a container's disk survives. Every Job_Log row and every shadow record a container writes is also written to the evidence store (`obs:job:*`, `obs:shadow:*` in `advero-reply-engine-obs-shadow`), redacted and cut to what the report reads, and printed as a one-line `ADVERO_RECORD` (who, what, when, status; no payload) to the logs. Signed approval links never reach either: URLs on the deployment's host and the `actions` and `click` fields of a card are replaced before anything is printed or stored, and the same redaction applies to the `live_write_intent` row that reaches the Job_Log sheet in live. The Job_Log **sheet** stays empty in shadow even with `JOB_LOG_SHEET_ID` set: the sheet append is itself a guarded write. The laptop's own `.tmp/job_log.csv` and `.tmp/shadow_log.jsonl` describe only laptop runs.

Read both halves with the read-only report. It lists and reads the shadow evidence Dict, reads `.tmp/laptop_runs/runs.jsonl`, prints the full job/status table, and writes one local file, the would_do records:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/watch_report.py --since "$(cat .tmp/deploy/report_start.txt)"          # exit 0 only if every automated criterion holds
python3 changesets/deploy/watch_report.py --since "$(cat .tmp/deploy/report_start.txt)" --json   # the same, as JSON
```

Check the LLM spend in the deployed store (a laptop `llm.budget_status()` reads the laptop's store, not Modal's):

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/budget.py status                    # the shadow Dict
```

**When the budget cap is hit** (an `llm.budget refused` row, one "stop" push, or `budget.py status` at the cap): first find out why (the first-poll backlog in step 2b is the expected reason; a loop is not). Then either zero the deployed counter with `python3 changesets/deploy/budget.py reset --store-mode shadow` (type `RESET`; it opens a new counter period, which re-arms the one $8 warning and one $10 stop push), or raise `budget_usd` in `config/llm_budget.json`, which is baked into the image, so it takes a redeploy (`DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow`); `budget.py status` shows the laptop file's cap and says so. The pushes sent from Modal name this command; `llm.reset_spend()` on the laptop resets only the laptop's counter. The refused rows stay in the evidence and fail the watch, so once the cause is known and dealt with, move the report start (the hand-off start stays):

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/watch_clock.py start-report --restart --reason "budget cap: first-poll backlog"
```

Shadow exit criteria. All must hold.

Automated, read by `watch_report.py`:
- there is evidence, and it spans at least 48 hours;
- every deployed Modal schedule was due at least once, and every run due before the last timeout window left its row within its timeout. There is no slack: a daily job that misses one of its two runs fails, and a late or manual row cannot stand in for a missed run. The watch has to include a weekday, or `cadence_veto_ping` proves nothing;
- every Job_Log status is on the explicit healthy list in `watch_report.HEALTHY_STATUSES`. Anything else fails, including a status nobody has seen before: `error`, `failed` (a non-zero exit), `entrypoint_missing`, `partial`, `refused`, the poller's `errors`, `replies_stuck`, `flush_failed`, `escalation_failed`, the approval's `push_failed`, `send_failed`, recipient holds and blocks, `pipeline_sync`'s `skipped_*`, the cadence's `d1_held_no_base_url`, `llm.budget warned`, `live_write_failed` and the rest of `KNOWN_FAILURES`;
- zero `live_write_*` rows and zero records written in live mode;
- the laptop: every laptop schedule due in the window has a run starting within 15 minutes of its time, and every run is healthy with no warning: `ok`, or one of `paid_calls_off` (the Sunday list factory, step 2c), `turned_off` (a removed agent still loaded) and `self_test_ok` (`watch_report.LAPTOP_HEALTHY`). A laptop schedule never due in the window (the weekly ones) is listed as not proven. A Mac asleep at a due time fails this: keep it awake and on power for the watch. The turned-off jobs are listed under TURNED OFF, never checked and never a failure.

Manual, which the report lists and never marks done:
- every `would_do` record (in the file the report names) is an action Lorenzo would have taken himself;
- at least one push arrived on the phone each morning. A silent 48 hours is a failure, not a pass;
- at least one approval card was tapped end to end from the phone and the page it returned was read;
- no positive reply waited more than 24 hours in the 07:30 digest.

The report's laptop lines replace reading `runs.jsonl` by hand; `--skip-laptop` leaves them out and lists them as NOT CHECKED instead.

`pipeline_sync` shows `Apply blocked: ghl_unreadable` until the GHL token exists, then a clean diff. `ghl_truncated` or `instantly_unreadable` block the apply on purpose. A `conflict:` note names a lead where a stale GHL stage would have overwritten a fresher Instantly negative: settle those in GHL by hand.

## Step 4: Lorenzo approves

Lorenzo reads the report, the would_do file and the laptop runs, and says go. Record it:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -c "from shared.job_log import log_run; log_run('deployment', 'approved_by_lorenzo', {'scope': 'sales tier live', 'shadow_hours': 48})"
```

## Step 5: cutover, then the sales tier goes live

The cutover starts live on a clean store. Run it while the shadow deployment is still running.

1. It refuses unless the shadow poller ticked healthily in the last 15 minutes.
2. It takes the shadow poller's high-water mark (the newest reply it consumed) as the cutover point, so no reply falls between the watch and live.
3. It writes the **hand-off list** of every reply the watch saw, plus replies that failed in shadow, to `.tmp/cutover/handoff_<time>.md`. **Lorenzo handles each of those by hand. The live engine never sees them and nothing acts on them.**
4. It refuses unless the live engine store is empty. Evidence lives in its own Dict, so a live deploy made by mistake before the cutover (every tick refused, with a daily alert) leaves nothing in the live engine store; the cutover then only needs the shadow deployment running again.
5. With `--apply` it seeds `poller:cursor` in the live store, then writes `cutover:record`. Until that record exists, every live Modal tick refuses to run and pushes one alert a day.
6. **Deploy live within 120 minutes of the apply.** The first live tick refuses a `cutover:record` older than that (`shared.store.CUTOVER_MAX_AGE_MINUTES`) until a live tick has accepted one (`cutover:accepted`); after that the age no longer matters. A stale first cutover that no live tick accepted is redone with `--redo` (below); a stale **resume** is not: run `--resume-live` again (Rollback, "Going live again after a rollback"), because the redo would delete the live store and refuses once it shows live activity. The live poller also refuses whenever its cursor is missing or incomplete.
7. The hand-off also lists, by id, every reply the shadow poller saw but wrote no lead record for. Open each in Instantly and confirm it needs nothing.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
H="$(cat .tmp/deploy/handoff_start.txt)"; echo "hand-off start: $H"           # must print a time
R="$(cat .tmp/deploy/report_start.txt)"; echo "report start: $R"               # must print a time
python3 changesets/deploy/watch_report.py --since "$R"                          # exit 0 again, right before
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --preflight   # writes the stamp the flip needs (60 minutes)
python3 changesets/deploy/cutover.py --watch-start "$H"                         # dry-run: .tmp/cutover/handoff_<time>.dryrun.md
python3 changesets/deploy/cutover.py --watch-start "$H" --apply                 # type CUTOVER
python3 changesets/deploy/modal_secret.py --mode live --base-url "$(cat .tmp/deploy/web_url.txt)"   # the plan only; writes nothing
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy live # type DEPLOY, then CREATE; /health must say live
python3 changesets/deploy/cutover.py --status                                   # accepted_by_a_live_tick fills in after the first tick
python3 changesets/deploy/watch_report.py --store-mode live --min-hours 1 --skip-laptop --json
```

The report start (`$R`) gates the watch; the hand-off start (`$H`) bounds the hand-off list. Never swap them: the hand-off list must reach back to the first reply the shadow engine saw.

**Change no code from the preflight line to `--deploy live`.** Not a file under the image's mounted directories, not `config/`, not the requirements. The stamp holds a SHA-256 over every file the image carries, and `--deploy live` (and `modal_secret.py --mode live --create`) refuse it when that hash no longer matches the code on disk or the stamp is over 60 minutes old (`changesets/deploy/preflight_stamp.py:104-126`, `install_schedules.sh:216-218`). An edit after the cutover apply therefore means a second preflight, which runs the whole test suite (`install_schedules.sh:126`) while the 120-minute clock on `cutover:record` is running, and it would put live code the shadow watch never ran.

**The live flip starts at the secret, not at the deploy.** `modal secret create --force` replaces the secret the running shadow app reads, so any container that starts after it (the next 5-minute tick, a cold web request) runs live, with the live store, before the live deploy finishes. So `install_schedules.sh --deploy live` does both, and nothing slow sits between them: it checks the preflight stamp first (no passing preflight in the last 60 minutes on exactly this code: it stops before asking anything), asks DEPLOY, runs `modal_secret.py --mode live --create` (which checks the same stamp and asks CREATE), then runs `modal deploy` straight after, then `/health`. It runs no preflight of its own. If anything fails once the live secret may exist (the create, the deploy, the URL, `/health`), it prints the abort sequence below. Do not create the live secret by hand; `modal_secret.py --mode live --create` refuses without the stamp anyway.

**If the live deploy fails** (the deploy errors, or `/health` does not say live): abort at once. The script prints this sequence itself whenever it stops after the live secret may exist. One case prints no abort by itself first: the live deploy succeeded but its output named no web URL. The script then checks `/health` at the saved URL in `.tmp/deploy/web_url.txt` (a redeploy of the same app keeps its URL). If that passes, live is up and nothing else is printed; if it fails, the abort sequence below is the only instruction.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m modal app stop advero-reply-engine                                                                  # stops every container, shadow code with the live secret included
python3 changesets/deploy/modal_secret.py --mode shadow --base-url "$(cat .tmp/deploy/web_url.txt)" --create # type CREATE
python3 changesets/deploy/watch_report.py --store-mode live --min-hours 0 --skip-laptop                          # what ran live in between
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow                                 # shadow again
```

Then read the live report: any `instantly.*` or `ghl.*` `live_write_*` row is a real write. Fix the deploy, then see where the live store stands and follow the `next` line:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/cutover.py --status                                 # read-only
```

- "the cutover stands": no live tick accepted it and it is under 120 minutes old. Run the preflight again (the stamp lasts 60 minutes), then `install_schedules.sh --deploy live`.
- "the cutover is stale and no live tick ran": `--redo` with the shadow deployment running (below), then the step 5 block from the preflight.
- "the resume is stale and no live tick ran since it": a `--resume-live --apply` that no live deploy followed within 120 minutes. Never `--redo`: it deletes the live store, which is the record of the live period, and that record cannot be rebuilt. It then cuts over as if for the first time. Do not count on the redo refusing here. It refuses on live activity in the store and on Instantly/GHL `live_write_*` evidence rows (`cutover.py:375-402`), and both can be gone: the resume deleted `cutover:accepted`, the activity check ignores `cutover:record`, `poller:cursor` and lock keys (`cutover.py:181-205`), and the live period's other keys and its evidence rows expire after 7 idle days (the reason `.tmp/cutover/rollback_seed.json` exists). Then the redo goes ahead. Run the resume block again from the preflight (Rollback, "Going live again after a rollback").
- "a live tick ran on this cutover": the 120-minute limit no longer applies, and the live store is the record of what the live engine did. Never `--redo`. Seed the shadow cursor from live (Rollback step 2), and go live again with `--resume-live` (Rollback, "Going live again after a rollback").

**If the cutover refuses: STOP.** Read the reason; do not work around it.
- "the shadow poller last ticked ... minutes before": the shadow deployment is not running (a live deploy replaces it). Redeploy shadow (`modal_secret.py --mode shadow ... --create`, then `install_schedules.sh --deploy shadow`), wait for one poller tick, run the cutover again.
- "the live store is not clean" or "already cut over": something wrote to the live engine store. First see what, with the dry-run reset, which writes nothing and lists every key:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/cutover.py --reset                                  # dry-run: lists the live keys; writes nothing
python3 changesets/deploy/cutover.py --reset --apply                          # type RESET; deletes every live engine key
```

The reset refuses whenever the live evidence holds any `instantly.*` or `ghl.*` `live_write_*` row (a prospect-facing write happened, so the live store is the record of it), or when that evidence cannot be read. Then STOP and ask; do not delete by hand.
- "the live store shows live activity": a live tick accepted the cutover, or the live engine wrote keys of its own (lead records, cards, `poller:seen`, spend, claims). The reset and the redo refuse on the store itself, because evidence rows expire after 7 idle days and are written best-effort, so their absence proves nothing. Do not reset a store the live engine used: go live again with `--resume-live`, which keeps it (Rollback, "Going live again after a rollback"). Only when you know the activity is not real (a test, a key written by hand), add `--override-live-activity "<why>"` to `--reset` or `--redo`; the reason is written to the Job_Log and `.tmp/cutover/overrides.jsonl`. No override passes an Instantly or GHL live write in the evidence.
- A stale first cutover that no live tick accepted (the live ticks refuse `cutover_stale` and `cutover.py --status` says "the cutover is stale and no live tick ran"), or a cutover made in error before the flip: redo it in one step, with the shadow deployment running. It refuses on the same prospect-facing rows and live activity as the reset.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
H="$(cat .tmp/deploy/handoff_start.txt)"
python3 changesets/deploy/cutover.py --redo --watch-start "$H"                 # dry-run: the keys it deletes and the fresh hand-off
python3 changesets/deploy/cutover.py --redo --watch-start "$H" --apply         # type REDO
```

The last command of the live block reads the live evidence. During live, `live_write_intent` and `live_write_ok` rows are expected, so its "zero live_write_* rows" line fails by design. A `live_write_failed` row is not one of them: it is a failure (a write the engine meant to make did not happen), listed with the `error`, `failed`, `refused` and `partial` rows. Check each one by hand in Instantly or GHL. First hour live: watch one positive reply travel end to end (draft on the phone, approval, Instantly reply, GHL opportunity, a `live_write_intent` row). Widen only after that. Check spend with `python3 changesets/deploy/budget.py status --store-mode live`.

Only the sales tier runs on Modal today. If a later build moves another tier's schedule to Modal, it is added with `DEPLOY_TIERS=sales,<tier>`; the list must always keep `sales`, because a deploy replaces the whole app.

## Step 6: the Instantly webhooks (optional, after sales has run live)

The poller already reads replies every five minutes, so webhooks only make replies faster. The change-set is `changesets/instantly_webhooks.py`; it creates six webhooks (`reply_received`, `lead_interested`, `lead_not_interested`, `lead_unsubscribed`, `email_bounced`, `lead_meeting_booked`), each with `target_hook_url` set to the deployment's `/webhooks/instantly` and the `X-Advero-Secret` header from `REPLY_ENGINE_SECRET`, which it reads from `.env` like everything else. The field is `target_hook_url`, the only required property (`config/instantly_api_contract.md`). **Write key first:** run `set -a; source ~/.advero/live.env; set +a` in the same terminal before the `MODE=live` command (`runbooks/read_only_keys.md` step 3).

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/instantly_webhooks.py --dry-run --url "$(cat .tmp/deploy/web_url.txt)"
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_webhooks.py --apply --yes --url "$(cat .tmp/deploy/web_url.txt)"
```

## Step 7: the laptop tiers, one at a time

Each laptop tier goes live by adding it to `LAPTOP_LIVE_TIERS` in `.env`, then watching 24 hours before the next. The runner reads `.env` on every run, so no reinstall is needed. Order: marketing, then ops, then fulfillment.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
# in .env, one line, edited by hand:  LAPTOP_LIVE_TIERS=marketing   (later marketing,ops, then marketing,ops,fulfillment)
python3 changesets/schedules/laptop_runner.py deliverability_monitor --plan      # child_mode must now be live
```

The list factory spends only when `.env` also has `LAPTOP_PAID_JOBS=list_factory`. Even then it spends nothing today: real runs price at $0.02267 per confirmed contact against the $0.02 cap (`LIST_FACTORY_MAX_COST_PER_CONTACT_USD`, `shared/thresholds.py:357`), and the cap is checked before the source fetch, so every run stops with `status: halted` before Apify is called. Whether to raise the cap for one measured run, change the source, or leave O8 off is DECISIONS R14 (was Q-M3). Both switches are read from `.env` only; setting them in the shell does nothing.

**The laptop store.** The laptop jobs keep one `.tmp/store.json` for shadow and live, on purpose: some of its keys are written by hand and must be seen in both modes. These are every key the scheduled laptop jobs' code can read or write there, found by reading that code: `python3 changesets/schedules/laptop_store_keys.py` prints them with where each is used, and `changesets/tests/test_schedules.py` fails when this table and the code disagree. "In the code" says whether any laptop code writes the key or only reads it:

| Key | In the code | Tier / job | Who writes it | Carries into live? |
| --- | --- | --- | --- | --- |
| `appointment:<id>` | read only | ops / `daily_metrics` (engine columns) | the reply engine, which runs on Modal now and writes its own Dict | stale: old laptop data (see Open) |
| `capacity.quarantine` | written | marketing / `inbox_inventory` | `inbox_inventory` (a quarantine and its clearing) | yes: it records real change-sets |
| `client:<slug>` | read only | fulfillment / `client_scorecard` | an operator, by hand (roster overrides) | yes |
| `first_touch:<email>` | read only | fulfillment / `client_scorecard` | nothing: no code in the repo writes it. The scorecard's dates come from GHL's `first_touch_date` field, else Instantly's last-contact date | nothing to carry |
| `llm.budget_alert:<period>:<threshold>` | written | ops / `retro_packet`, marketing / `list_factory` (through `shared.llm`) | the model budget: one claim per alert per counter period | yes: re-armed by a reset |
| `llm.spend_period` | written | ops / `retro_packet`, marketing / `list_factory` (`shared.llm`) | `shared.llm`, when the counter starts or is reset | yes |
| `llm.spend_usd` | written | ops / `retro_packet`, marketing / `list_factory` (`shared.llm`) | every model call a laptop job makes (the laptop's own counter; Modal counts in its Dict) | yes: one laptop budget for both modes |
| `noshow_state:<id>` | read only | ops / `daily_metrics` (show rate) | the reply engine, on Modal now | stale: old laptop data (see Open) |
| `retention:<slug>:<template>` | written | fulfillment / `client_scorecard` | `client_scorecard --mark-handled` by hand | yes: it records what Lorenzo did |
| `retro:proposal:<week>` | written | ops / `retro_packet` | the Friday run (the paid LLM claim for that week) | yes: the proposal does not depend on the mode |
| `retro:skool:<week>` | written | ops / `retro_packet` | the Friday run (the Skool post was staged as a file for Lorenzo to post by hand) | yes: staging is a local file in both modes |

The list factory's run state is not in this file: each run keeps its own `state.json`. So nothing needs deleting before a laptop tier goes live. To see them, or to force a fresh retro proposal for one week:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/schedules/laptop_store_keys.py
python3 -c "from shared.store import get_store; s=get_store(); [print(k) for k in s.keys('') if k.startswith(('appointment:','capacity.quarantine','client:','first_touch:','llm.','noshow_state:','retention:','retro:'))]"
python3 -c "from shared.store import get_store; get_store().delete('retro:proposal:<week start date>')"   # one week's claim, by hand, only if wanted
```

## Rollback

1. **Stop everything on Modal (the fast kill switch):** `python3 -m modal app stop advero-reply-engine`. Every schedule and the web endpoint stop at once. Both Modal Dicts survive a stop.
2. **Back to shadow on Modal.** The shadow store's poller cursor is still the one from the watch, so a shadow redeploy would re-read every reply since the cutover: a model classification for each (spend) and a card on the phone for each positive. If the shadow store sat idle 7 days, its cursor has expired and the first poll walks back 20 pages instead. So seed the shadow cursor from the live one first, then re-create the secret and redeploy:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/cutover.py --seed-shadow-from-live                  # dry-run: the shadow cursor now and after
python3 changesets/deploy/cutover.py --seed-shadow-from-live --apply          # type SEED
python3 changesets/deploy/modal_secret.py --mode shadow --base-url "$(cat .tmp/deploy/web_url.txt)" --create
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow
```

   This is a secret re-create plus a redeploy, not one env change. The seed also keeps the live cursor it copied in `.tmp/cutover/rollback_seed.json`, for the resume below if the live one expires. Going live again later is `--resume-live`, never `--redo`: the redo deletes the live store and refuses once it shows live activity.
3. **A laptop tier back to shadow:** remove it from `LAPTOP_LIVE_TIERS` in `.env`. **Stop a laptop job for good:** unload it, then remove its plist, or launchd loads it again at the next login:

```bash
launchctl bootout "gui/$(id -u)/com.advero.list_factory"
rm ~/Library/LaunchAgents/com.advero.list_factory.plist
```
4. **The webhooks:** `MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_webhooks.py --rollback --yes`. **Write key first:** run `set -a; source ~/.advero/live.env; set +a` in the same terminal before the `MODE=live` command (`runbooks/read_only_keys.md` step 3). The poller keeps reading replies with GET calls.
5. Live writes leave `live_write_intent` rows (and `live_write_ok` / `live_write_failed` where a caller records the result) in the live store; `python3 changesets/deploy/watch_report.py --store-mode live --json` lists them, and counts every `live_write_failed` as a failure. Sent email, SMS and blocklist entries cannot be reversed by any of the above.

### Going live again after a rollback

The live store stays: it is the record of the live period (its lead records, cards, cadences and spend). `cutover.py --resume-live` makes it safe to deploy live on it again. Run it with the shadow deployment running and polling.

**Expect a refusal after a real live period.** Any live reply Lorenzo approved and sent (a positive or a neutral question) arms a ladder when that reply goes out, not at D1 (`approval.py` `_arm_under_lock`, then `cadence.arm`), and any drafted reply leaves a card until it is handled; a ladder can also sit paused by an out-of-office. A live period in which no reply was drafted leaves none of these; one that drafted replies may leave none either, if every card has closed (sent, vetoed, expired or otherwise closed) and every ladder has finished or been stopped other than by an auto-reply. So expect a refusal whenever someone replied during the rollback while the live store still holds an open card (pending, queued or sending), an armed ladder, a ladder paused by an auto-reply, or a lead record the engine cannot load: the resume then refuses and says "STOP and ask" (rule 4 below; `cutover.py:553-574`, `487-492`). It can go ahead only when nobody replied during the rollback, or when the live store holds no armed ladder, no auto-reply pause and no pending, queued or sending card. **There is no tool yet to stop live ladders or close live cards**: the refusal has no override, and emptying the live store by hand is not a workaround. Treat a resume after a real live period as a conversation, not a command.

1. It refuses unless the shadow poller has a complete cursor and ticked healthily in the last 15 minutes, and unless the live store was cut over before (a `cutover:record` or live activity; otherwise it is a first cutover, step 5).
2. The rollback period starts at the live store's `poller:cursor` (or, if that expired, the copy in `.tmp/cutover/rollback_seed.json`; with neither it refuses: STOP and ask). It refuses when the shadow cursor is older than that point.
3. It writes a **hand-off** of the rollback period to `.tmp/cutover/handoff_<time>.md`: every reply the shadow engine saw after the live cursor, up to the shadow high-water mark, the ones that failed in shadow, and the ids seen with no lead record. **Lorenzo handles each by hand; the live engine never sees them.** It also lists the live `poller:failed` ids it clears (older than the new cursor, the live poller could never retry them), the live cards still open (pending, queued or sending) and the live ladders that could send.
4. **The broad rule: if ANY reply arrived during the rollback, it refuses, writing nothing, while ANYTHING live could send**, whoever's it is. "Any reply" means every row of the hand-off: identified replies, replies that failed in shadow and ids seen with no lead record (for those two nobody knows whose they are, so no live lead can be ruled out). "Anything live that could send" is, for every live lead: an armed ladder (`cadence.is_armed`), a ladder paused by an auto-reply such as an out-of-office, which the next live tick restarts by itself (the engine's own `cadence.is_auto_reply_pause`), and every `pending`, `approved_queued` or `sending` card. The refusal says "STOP and ask" and lists the rollback replies (the unidentified ids included) and each ladder or card with why. If nobody replied during the rollback (the hand-off is empty), it goes ahead and the live ladders and cards carry on as they were. The rule lives in `changesets/deploy/cutover.py` (`resume_blockers`, `live_ladder_state`).
5. With `--apply` (type `RESUME`) it deletes `cutover:accepted`, sets the live `poller:cursor` to the shadow high-water mark, deletes the live `poller:failed`, and writes a fresh `cutover:record` last (with `resumed: true`). That re-arms the 120-minute limit: deploy live within 120 minutes. If you miss it, `cutover.py --status` says "the resume is stale and no live tick ran since it": run this block again from the preflight. Never `--redo`: it deletes the live store, which is the record of the live period and cannot be rebuilt, and then cuts over as if for the first time. Its refusal rests on live activity in the store and on Instantly/GHL `live_write_*` evidence rows (`cutover.py:375-402`). This apply deletes `cutover:accepted`, the activity check ignores `cutover:record` and `poller:cursor` (`cutover.py:202`), and the live period's other keys and evidence rows expire after 7 idle days, so a stale resume can leave nothing the redo refuses on.
6. **Appointment reminders are not covered by the resume rule.** `resume_blockers` looks only at lead ladders and approval cards (`cutover.py:553-574`); the show-rate touches (confirmation, pre-read, the 24 h, 1 h and 15 m reminders, `services/reply_engine/show_rate.py`, sent by `appointments_tick`) are not checked. A booked call that stands keeps its reminders and needs nothing. Before `--resume-live --apply`, make GHL match only when the call does not stand: a rollback-period reply that cancels or moves the call, or a call Lorenzo is re-arranging by hand. Cancel or reschedule that appointment in GHL. There is no way to stop only the engine's reminders for a call: the engine drops a stored reminder schedule once the appointment is no longer active in GHL (cancelled there, or missing from the calendar window it read), and only on a tick whose GHL calendar read succeeded; a failed read cancels nothing (`show_rate.py:1215-1220`, `1253-1256`, `1303-1310`; `jobs/appointments_tick.py:250` passes no active ids when the read was not authoritative). A reminder sent by a GHL workflow of its own is not the engine's; for a call you cancel or move, check it in GHL too.

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 changesets/deploy/cutover.py --status                                  # read-only: "a live tick ran on this cutover"
python3 changesets/deploy/cutover.py --resume-live                             # dry-run: .tmp/cutover/handoff_<time>.dryrun.md
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --preflight  # the stamp for the flip (60 minutes)
python3 changesets/deploy/cutover.py --resume-live --apply                     # type RESUME
DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy live
python3 changesets/deploy/watch_report.py --store-mode live --min-hours 1 --skip-laptop --json
```

**Change no code between `cutover.py --resume-live --apply` and `--deploy live`** (nor between the preflight line and the apply). The preflight stamp is a SHA-256 of every file the Modal image mounts, and `--deploy live` checks it before it asks anything: a stamp whose hash no longer matches the code on disk, or one older than 60 minutes, is refused (`changesets/deploy/preflight_stamp.py:104-126`, `install_schedules.sh:216-218`). An edit after the apply forces a second preflight, which runs the whole test suite (`install_schedules.sh:126`), while the 120-minute clock on the fresh `cutover:record` runs; miss it and the resume is stale and has to be run again. And the code that would go live is then not the code the shadow deployment ran during the rollback.

**If the resume refuses: STOP and ask.** Nothing can stop a live ladder or veto a live card while shadow is deployed, and after the resume it would be too late: an armed or auto-reply-paused ladder sends its next follow-up (D2 onward goes out without a veto ping) and a queued card sends, possibly to a lead whose new reply you are answering by hand, and for a reply with no lead record there is no telling whose it is. Do not work around the refusal; there is no override.

## Open

- **Modal Dict expiry.** Modal 1.2.6 deletes a Dict entry after 7 days with no read or write (`modal/dict.py`). Evidence records last 7 days, so run the watch report within 7 days of the window it covers. A live engine store idle for 7 days loses its keys, `cutover:record` and the poller cursor included: every live tick then refuses (`cutover_missing`, or the poller's `cursor_missing`) rather than re-reading 20 pages. If only the cursor is gone and other live keys remain, recover with `cutover.py --resume-live` against a running shadow deployment (it falls back to `.tmp/cutover/rollback_seed.json` for the lost cursor), or `--redo` if no live tick ever ran. If every live key is gone (a live store left untouched for 7 days after a rollback loses all of them together), `--resume-live` refuses: with no `cutover:record` and no live activity it reads as a first cutover (`cutover.py:441-443`). STOP and ask then; the record of the live period is gone, and a plain cutover would not know which of its replies were already handled. Keys also expire one at a time while the app runs: lead records survive because the hourly cadence reads every one, but reply claims, no-show counts and other keys touched once are gone after 7 quiet days.
- **The first shadow scan may never complete** on a large account (deferred, reviewer item A). With no cursor, a scan that reaches 20 pages (2,000 received emails) is truncated, and a truncated scan never sets the cursor, so every later poll walks the same 20 pages again (replies already seen are skipped, so nothing is processed twice, but the cursor never appears). `watch_clock.py start-report` and the cutover then refuse on the missing cursor. Measured: 115 received emails on 2026-09-22 (`runbooks/list_factory.md`), far below the limit. Until it is fixed, the received-count check in step 2b is required before any first-pass deploy on a store with no cursor. The future fix, in `poller.py` (the reply-engine owner): a capped first scan counts as complete for what it covered once every reply in it is processed or has used up its retries, and the cursor is set to its newest row.
- **The inbox inventory can end `partial`** (deferred, reviewer item B): it exits 1 on a partial read (`jobs/inbox_inventory.py`), which the laptop runner records as `failed` and the watch gate fails on. `partial` stays a failure. Before `start-report`, run `python3 jobs/inbox_inventory.py --dry-run` (step 2d). If `partial` recurs, fix its cause, or run the sales watch with `--skip-laptop`.
- The live poller refuses to run without a complete cursor (`modal_app._live_refusal`, outside `poller.py`). A matching guard inside `poller.py` itself (refuse to poll in live with an empty cursor, whoever calls it) is for the reply-engine owner.
- The laptop jobs keep one `.tmp/store.json` for shadow and live, by design (step 7 lists every key). The engine keys in that file (`appointment:*`, `noshow_state:*`) are stale once the engine runs on Modal, so `daily_metrics` (and `retro_packet`, which reads engine data from laptop files too) show old or unknown engine numbers. Not a blocker for the shadow deploy or the sales flip; it is one for putting the ops tier live (step 7) and for trusting the tracker's engine columns or the first Friday retro after live. `first_touch:*` is different: nothing writes it anywhere, and the scorecard's dates come from GHL or Instantly. If a first-touch stamp is built into the Modal engine, it should write GHL's `first_touch_date`, which the laptop scorecard already reads.
- `precall_tick` runs with `max_containers=1` on Modal (`modal_app.MODAL_MAX_CONTAINERS`), so a run that overruns 5 minutes makes the next one wait instead of overlapping; its file lock only covers one container's disk. Every Modal row carries `started_at` (`modal_app._tick`), and the watch report matches runs to their due times on that start: a run that started within 90 seconds of the previous run's end was queued behind it and is credited to the slot it waited for (`watch_report.match_runs`), so a slow run and its queued successor report nothing missing, while a run that never started is still missing.
- A scheduled `precall_tick` pushes once per call for a skipped row (a no-show), once per clock hour for the same error, and once per clock hour when its only news is a failed GHL read or a missing Instantly client; briefs and drafted proposals push every time.
- Nothing scheduled shows the Upwork rooms any more: the two digests are turned off (Lorenzo runs them by hand), and `pipeline_sweep` on Modal cannot read `.tmp/upwork_rooms.json`.

## Thresholds
| Check | Value | Source |
| --- | --- | --- |
| Shadow period before live | 48 h, automated criteria met and the manual ones signed off | `changesets/deploy/watch_report.py`, CLAUDE.md |
| Reply SLA on positives | < 5 min in business hours, alert > 60 min | Blueprint Section 6 |
| Send window | 07:00-19:00 CT | `shared.settings.SEND_WINDOW` |
| Scheduled on Modal | poller, approval_escalation, precall 5 min; appointments 10 min; cadence hourly 07-19 CT and 09:30 CT weekdays; sync 06:00 CT; sweep 07:30 CT | `modal_app.SCHEDULES`, five-field crontab strings read in `America/Chicago`, so nothing drifts when CDT ends on Nov 1, 2026 |
| Errors tolerated in shadow | 0 rows with a status outside `watch_report.HEALTHY_STATUSES`; 0 missed runs | `changesets/deploy/watch_report.py` |
| Cutover (or resume) to live flip | at most 120 minutes | `shared.store.CUTOVER_MAX_AGE_MINUTES` |
| Preflight to live flip | at most 60 minutes, same code | `changesets/deploy/preflight_stamp.MAX_AGE_MINUTES` |
| Scheduled poll, new replies taken for | 120 s of its 240 s timeout | `modal_app.POLLER_TIME_BUDGET_S` |
