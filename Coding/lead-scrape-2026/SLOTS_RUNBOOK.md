# Slots runbook: `{{slot1}}` / `{{slot2}}` for the AI-agents campaigns

The six AI-agents campaigns (bookkeeping_ai, insurance_broker_ai, landscaping_ai, marketing_agency_ai, msp_ai, pest_control_ai) end every email with:

- step 1: "how does {{slot1}} or {{slot2}} sound?"
- step 2 (3 days later): "Would {{slot1}} or {{slot2}} work for a quick 15 minute call?"

Instantly fills both from each lead's custom variables at send time. A blank variable sends a broken sentence, so every lead must always have both set. Two things keep them set:

1. `instantly_push.py --offer ai_agents` sets `slot1`, `slot2` and `slot_date` on every lead it adds. It uses the next send day.
2. `slots_daily.py` refreshes them every morning for that day's sends.

Campaign ids are in `instantly_campaigns_ai_agents.json`. Neither script writes `instantly_campaigns.json`, because `instantly_push.py --activate` starts every id in that file. `--activate` is refused with `--offer ai_agents` and with `--dry-run`; `--setup` is refused with `--offer` and with `--dry-run`. Both refusals exit 2 before the API key is read.

The ids file must hold exactly the six keys above, six different ids, none of them an id from `instantly_campaigns.json`, and neither of the live AI-agents campaigns whose copy has no slots (`d81f1d53-…` Service - AI Agents, `59b20790-…` Recruiting - AI Agents). Anything else is refused.

## Slot rules (send day D)

- slot1 is a time on the 1st business day after D. slot2 is a time on the 2nd business day after D.
  - Mon → Tue/Wed
  - Wed → Thu/Fri
  - Thu → Fri/Mon
  - Fri → Mon/Tue
  - Sat → Mon/Tue
- Times sit on a 30-minute grid from 12:00 to 17:30 CT (start times). Each time must be free in the GHL Discovery Call calendar. `shared.slots.candidate_slots` enforces the ">= 4 h out" and "<= 5 business days" rules.
- If a day has no free time, the job rolls to the next business day, within the 5-business-day limit.
- If GHL can't be read (no `GHL_PRIVATE_INTEGRATION_TOKEN_READ`, a network error, or no answer at all), the job uses the full grid, prints a `!! GHL CALENDAR NOT READ` banner and logs `"source": "fallback"`.
- If GHL answers with an empty list of free slots, that is treated as a GHL problem too: full grid, the same banner, `"source": "fallback_empty"`. This is the choice made on 2026-09-30 because a run that writes nothing leaves yesterday's slots in place, which are stale by definition. The cost is that on a genuinely fully booked week the emails offer booked times; the banner and the log line say so.
- If GHL answers with free slots but fewer than two days have an offerable time, the job exits 1 with a slot error, prints the reason and writes nothing. Yesterday's slots stay on the leads, so treat that log line as urgent.
- Calendar conflicts are not checked on any fallback run.
- Text is in CT only: `slot1` = `Thursday at 1pm`, `slot2` = `Friday at 2:30pm CT`, `slot_date` = D (`YYYY-MM-DD`).
- Spread: each lead gets `(day1[i % n1], day2[j % n2])`, with i and j taken from a SHA-256 of `email|D`. The pick is stable within a day, changes day to day, and spreads evenly. Many leads share each time. If a lead picks a time that is already booked, the reply flow's counter-offer handles it (it offers two fresh free times).

## Daily job: `slots_daily.py`

Run it from `Coding/lead-scrape-2026/`.

| Command | What it does |
|---|---|
| `python3 slots_daily.py` | Dry-run (default). Reads GHL free slots, the six campaigns and their leads, then prints the source, both slot lists, the campaign copy check, per-campaign counts (leads / eligible / would_change / unchanged / unreadable) and 3 before/after samples. Writes nothing to Instantly. |
| `MODE=live ALLOW_LIVE_WRITES=1 python3 slots_daily.py --apply` | Backs up, then sends one PATCH per lead whose values change, with the safety checks below. Without both env vars it refuses with exit 2 before reading anything. Only Lorenzo sets those vars. |
| `--lead-id <id>` | Runs the whole flow on exactly that one lead (GET it, check it is in one of the six campaigns and can still get a step, back it up, PATCH, read back). With or without `--apply`. This is the rehearsal. |
| `--restore logs/slots_backup_<D>_<ts>.json` | Prints what it would write back (dry-run). Add `--apply` (same env gate) to PATCH each lead's custom variables back to the saved set. `--lead-id` limits it to one lead. |
| `--date YYYY-MM-DD` | Overrides D, for testing. Simulates the 05:00 CT run on that day. |
| `--ids-file f.json` | Uses another ids file. A file named `instantly_campaigns.json` is refused. |

### Safety checks on `--apply`

1. **Campaign copy check.** Before any write, it GETs each of the six campaigns. Every step-1 variant body and the step-2 body must contain both `{{slot1}}` and `{{slot2}}`. If any does not, `--apply` is refused (exit 2, status `copy_check_failed`). A dry-run prints the same problems as a warning.
2. **Backup.** Before the first PATCH it writes `logs/slots_backup_<D>_<ts>.json`: for every lead it will patch, the id, email, campaign, campaign key, full `payload`, top-level `first_name` / `company_name`, the custom variables it read, and the raw lead object.
3. **First-write check.** After the first successful PATCH it GETs that lead and aborts (exit 3, status `readback_failed`) unless:
   - `payload.personalization`, `lead_id`, `firstName` and `companyName` equal the backup;
   - `personalization` and `lead_id` are not empty, each checked only when the backup had it non-empty (a lead added by hand may have no `lead_id`);
   - `payload.campaign` and `payload.pause_until` (Instantly's own keys) equal the backup;
   - top-level `first_name`, `company_name` and `personalization` are unchanged;
   - `slot1`, `slot2` and `slot_date` hold the new values.
   The abort prints which fields failed and the `--restore` command for that run's backup. The log line holds only the lead id (`readback_lead_id`), the failed field names (`failed_fields`, `problems`) and `details_in`: no email, names or personalization. The values (before, after and the lead as read back) go into the backup file under `readback_failure`; `--restore` ignores that key.
4. **Failure brake.** 5 PATCH failures in a row stop the run (exit 3, status `failure_brake`). Fewer failures finish the run with exit 1 (`applied_with_failures`).
5. **Any other error** mid-run (a bug, a network failure while listing) is caught, logged with the number of leads already updated, and exits 3 (status `exception`).
6. **Ctrl-C, SIGTERM or SIGHUP** mid-run is caught too. The job logs status `interrupted` with the signal, the patched / failed counts so far and the backup path, prints the `--restore` command (for an interrupted `--restore`, the command to finish it) and exits 130 (Ctrl-C), 143 (SIGTERM) or 129 (SIGHUP). A SIGHUP that `nohup` set to ignored stays ignored.

### Log and exit codes

Every run appends one JSON line to `logs/slots_daily.jsonl`, including refused runs, a bad ids file, bad arguments, interrupts and crashes: ts, mode, kind (`slots` / `restore` / `usage`), send_day, source, slot options, counts, backup path, read-back result, patched / failed, and status. Statuses: `dry_run_ok`, `applied`, `applied_with_failures`, `refused`, `usage_error`, `copy_check_failed`, `slot_error`, `ids_error`, `lead_id_refused`, `no_campaign_field`, `readback_failed`, `failure_brake`, `exception`, `interrupted`, `restore_dry_run_ok`, `restored`, `restored_with_failures`, `restore_error`. A `usage_error` line carries the arguments and argparse's message.

`logs/*.jsonl` and `logs/slots_backup_*.json` are git-ignored (`Coding/lead-scrape-2026/.gitignore`); the backups hold lead emails and personalization.

- 0: ok
- 1: slot error, ids file missing or invalid, `--lead-id` refused, leads without a `campaign` field, a bad backup file, or some PATCHes failed
- 2: refused (live flags missing, or the campaign copy check failed), or a usage error (bad arguments)
- 3: aborted mid-run (read-back failed, failure brake, unexpected exception)
- 130 / 143 / 129: interrupted by Ctrl-C / SIGTERM / SIGHUP

### Which leads it updates

It reads each campaign's leads with `POST /leads/list` and `{"campaign": <id>}`. That call only reads. On 2026-09-30 the `campaign` key was verified to filter correctly; `campaign_id` is ignored. If a page ever returns another campaign's leads or leads with no `campaign` field, the job treats the filter as ignored, pages the whole workspace once and groups leads by their `campaign` field. If leads that could still get a step come back with no `campaign` field and none match the six campaigns, the job exits 1 with a `NO LEAD MATCHED A CAMPAIGN` banner (status `no_campaign_field`) instead of reporting success.

A lead is eligible when it can still get a step. That uses these Instantly v2 lead fields:

- `status` is 1 (active) or 2 (paused). It excludes 3 completed, -1 bounced, -2 unsubscribed and -3 skipped.
- `email_reply_count` is 0 and there is no `timestamp_last_reply`.

### What it writes

It sends `PATCH /leads/{id}` with `{"custom_variables": <full existing variables + slot1, slot2, slot_date>}`.

- A list or GET answer carries the custom variables inside `payload`, mixed with the standard fields and Instantly's own keys. The job takes `payload` minus the standard fields (`firstName, lastName, companyName, email, website, phone, jobTitle`) and minus Instantly's keys (`campaign`, `pause_until`, both seen in the 2026-09-21 replied-leads snapshot) as "existing". It keeps `personalization`, `lead_id`, `specialty`, `mv_result` and anything else in there.
- The existing variables count as readable only if they form a dict with a non-empty `personalization`. A null `payload`, `{}`, or a payload holding only standard keys is unreadable: the job GETs the lead and checks again. The GET answer is used only if its `id` is the listed lead's id and its `campaign` is the same campaign; anything else counts as unreadable. If it is still unreadable, it skips the lead and counts it as `unreadable`. It never sends a partial dict.
- It skips leads whose three values already match.
- It pauses 2 s every 100 calls and retries an HTTP 429 up to 3 times. The contract allows 100 req/s and 6,000 req/min.

### Rehearsal before the first full `--apply`

Whether `PATCH custom_variables` merges or replaces is **not verified**. The docs say new keys are merged; the read-back has never been checked. Before the first full run:

1. Rehearse on a lead added by the first live push (`instantly_push.py ... --offer ai_agents --limit-per-campaign 1`), not a lead added by hand: that lead has the exact variables every pushed lead will have (`personalization`, `lead_id`, `specialty`, `mv_result`, slots). Take its id from `instantly_ids` in that push's `logs/push_ai_<ts>.json` and dry-run it: `python3 slots_daily.py --lead-id <id>`. Check the before/after sample.
2. Lorenzo runs it live: `MODE=live ALLOW_LIVE_WRITES=1 python3 slots_daily.py --lead-id <id> --apply`. The job backs the lead up, PATCHes it and reads it back. Exit 0 with `read-back of the first patched lead (<id>): ok` means the merge kept everything.
3. On exit 3, run the printed `--restore <backup> --lead-id <id>` (dry-run, then `--apply`) and stop: the full run must not happen until the PATCH shape is fixed.
4. If the lead already carries today's values the job has nothing to PATCH; use `--date` with another day to force a change.
5. Only then run the full `--apply`, then schedule it.

### Restore

`python3 slots_daily.py --restore logs/slots_backup_<D>_<ts>.json` lists each lead and the variables it would write back. With `--apply` (same env gate) it PATCHes `{"custom_variables": <saved set>}` for each lead, with the same failure brake and logging. It refuses a backup whose leads are outside the six campaigns or have no usable saved variables. If Instantly merges custom variables, a restore puts every saved value back but does not delete keys the backup never had (on a lead's first run, the new slot keys stay).

## Schedule and operations

Run it at **05:00 CT, Monday to Saturday**. That is one hour before the campaigns start sending at 06:00 CT (07:00 America/Detroit).

```
# crontab (machine clock in CT); live flags are Lorenzo's to add
0 5 * * 1-6  cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026" && MODE=live ALLOW_LIVE_WRITES=1 /usr/bin/python3 slots_daily.py --apply >> logs/slots_daily.cron.log 2>&1
```

- **Do not activate the six campaigns** until the daily `--apply` has been rehearsed with `--lead-id` (above) and is scheduled.
- **Stale slots:** whenever the 05:00 CT job does not run (laptop asleep or off, cron missing, a refused or failed run), the leads keep the previous run's slots, so that day's emails offer days that may already be past or booked. Check `logs/slots_daily.jsonl` each morning for a line with today's `send_day` and status `applied`.
- **GHL token:** the job needs `GHL_PRIVATE_INTEGRATION_TOKEN_READ` (scope `calendars.readonly`) in `Agentic Worklfows/.env`. Without it every run is `fallback` and no calendar conflict is ever checked.
- Until Lorenzo approves the live run, schedule it without `--apply` (dry-run) and read `logs/slots_daily.jsonl`.
- **cron on this Mac:** cron needs Full Disk Access (System Settings > Privacy & Security > Full Disk Access, add `/usr/sbin/cron`) to read anything under `~/Desktop`; without it every run fails before writing a log line. cron also skips a run while the laptop sleeps and does not catch it up on wake. For a job the 06:00 sends depend on, an always-on runner (Modal, like the lead-sync app, or another server) is recommended over the laptop.
- **Run time:** one PATCH per lead, so a run over N leads that change takes roughly N/80 seconds at the pacing ceiling (plus the listing, about one call per 100 leads). Real round trips can be slower: time the first full run and start early enough to finish before 06:00 CT (move the 05:00 start earlier as the campaigns grow).

Sunday is skipped: Monday's 05:00 run sets Monday's values. Leads added by the push between runs already carry the next send day's values.

## Push: `instantly_push.py --offer ai_agents`

```
python3 instantly_push.py --push output/daily/day_2026093*.csv --offer ai_agents --dry-run
python3 instantly_push.py --push <files...> --offer ai_agents --limit-per-campaign 1   # first live push: one lead per campaign
python3 instantly_push.py --push <files...> --offer ai_agents                          # live add, campaigns stay inactive
```

What the push does:

- Maps the CSV `campaign` column to an AI campaign key: bookkeeping→bookkeeping_ai, insurance_broker→insurance_broker_ai, landscaping→landscaping_ai, marketing_agency→marketing_agency_ai, msp→msp_ai, pest_control→pest_control_ai. Recruiting and cleaning rows are skipped and counted.
- Drops rows with empty personalization or tier `skip`, and rows with no email in `output/FINAL/MASTER_for_sheets.csv`.
- Dedupes by lead_id and by email (case-insensitive) across all files. The first occurrence in file order wins.
- Keeps the mailbox filter as before: only `google`, `other` and `zoho` (no Microsoft, Yahoo or no-MX).
- Sets custom variables: personalization, specialty, lead_id, mv_result, slot1, slot2 and slot_date. The slots are computed once per run for the next send day. That is today if it is Mon-Sat and before 06:00 CT, otherwise the next Mon-Sat date.
- `--limit-per-campaign N` keeps the first N leads per campaign (file order) and counts the rest under skipped.
- **Status check.** Before any add (and in `--dry-run`), it GETs each of the six campaigns and prints its status (0 draft, 1 ACTIVE, 2 paused, ...). If a campaign that would receive leads is active (status 1), or its status cannot be read, a live push is refused with exit 2 and nothing written, unless `--allow-active` is passed. A dry-run prints the same warning and carries on. Campaigns that receive no leads in this push are printed but never block it.
- **Record before the first add.** A live push first lists every target campaign (`POST /leads/list`, read only) and writes `logs/push_ai_<ts>.json` with `push_started_at` (UTC) and, per campaign, the campaign id and `pre_existing` (every lead id and email already in it). It prints the record path, then adds. If that listing fails, the push stops with exit 1 before any add.
- Adds leads with `POST /leads/add`, one call per campaign per 1,000 leads, with `skip_if_in_workspace: true` and a 2 s pause between calls. It prints Instantly's returned counts: uploaded, skipped (in workspace), already in campaign, blocklist, invalid, duplicate in payload.
- The record also holds, per campaign, every email and lead_id sent (written before each call, so a crash still leaves the list) and each call's returned counts and raw response.
- After the adds it lists each campaign again and fills `instantly_ids` with the leads this push **created**: email in `sent`, id not in `pre_existing`, and, when the lead has `timestamp_created`, created at or after `push_started_at`. Sent emails whose lead was already in the campaign (for example skipped as in workspace) go under `not_created_by_this_push` with the reason, never into the rollback list. It then GETs one created lead per campaign and prints its custom variables. A `!! MISSING` line means personalization, lead_id or a slot variable did not arrive.
- `--dry-run` writes nothing (no record file either). It prints per-file rows, per-campaign counts, skip reasons, the six campaign statuses, the slot source and lists, and 2 sample request bodies. If the ids file is missing or invalid, it uses placeholder ids and skips the status GETs. A live push without a valid ids file exits.
- It never activates a campaign.

**No MODE gate on the push (decision, 2026-09-30).** The live push runs without `MODE=live` / `ALLOW_LIVE_WRITES=1`. Adding leads to campaigns that are not active sends nothing, and the old push works the same way. The gate that matters is activation, which stays a manual step of Lorenzo's. The status check above enforces the assumption: a push into an active campaign needs `--allow-active`.

### Rolling back a bad push

1. Open the push's `logs/push_ai_<ts>.json`. For each campaign, `instantly_ids` maps every lead this push created to its Instantly lead id. It never holds a lead that was in the campaign before the push (`pre_existing`), even when this push sent the same email again: those are listed under `not_created_by_this_push` and must not be deleted (an older lead may be mid-sequence).
2. **Crashed push, or `verify_error` instead of `instantly_ids`:** rebuild the list from what was saved before the first add. Page the campaign with `POST /leads/list {"campaign": <campaign_id>}` and keep only the ids that are **not** in that campaign's `pre_existing` and whose email is in its `sent` list (and, when the lead has `timestamp_created`, created at or after `push_started_at`). `instantly_push.created_by_this_push(leads, sent_emails, pre_existing_ids, push_started_at)` does exactly this. A campaign with no `sent` entries got no add.
3. Check the count: it should not exceed the sum of that campaign's `leads_uploaded` in `results` (when a batch has no result because the push crashed during it, its `sent` list is the upper bound). If it does, stop and look before deleting.
4. Delete those ids from that campaign: Instantly bulk delete with `campaign_id` and the `ids` list (the Instantly MCP `leads_bulk_delete` tool, or by hand in the campaign's lead list). This is a live write: Lorenzo approves it first.
5. Re-run the dry-run to confirm the per-campaign counts before pushing again.

The old single-file push (`--push one.csv` with no `--offer`) is unchanged. `--dry-run`, `--ids-file`, `--limit-per-campaign` and `--allow-active` are refused on it, because that path has no dry-run and would push live.
