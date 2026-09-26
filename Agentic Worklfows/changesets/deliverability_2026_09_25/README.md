# Deliverability change-set, 2026-09-25

Script: `apply_deliverability.py` in this folder. Run every command from `Agentic Worklfows/`.

## What it changes and why

The inbox placement test `01a0dac3-e227-7eb6-8334-f0a75795b689` put 7 of 7 Gmail seeds from proadvero.com in spam, against 1 of 19 for the other three domains. Microsoft seeds landed in spam 9 times out of 10, and no Microsoft-hosted lead has sent a human reply since Sep 18.

All six 2026 campaigns are paused (status 2) and get the same three changes:

| | Change | How |
|---|---|---|
| A | Remove `lorenzo@`, `lorenzov@`, `lorenzovillarreal@proadvero.com` from `email_list` (12 inboxes to 9) | one `PATCH /campaigns/{id}` per campaign, together with B |
| B | `allow_risky_contacts` true to false | same PATCH |
| C | Park Microsoft-hosted leads in the lead list `Parked - Microsoft recipients 2026-09-25` | `POST /leads/move`, at most 100 ids per job, one job at a time |

A lead is parked only when all of these hold: its `campaign` is one of the six, `status` is 1 (active), `esp_code` is 2 (Microsoft), `email_reply_count` is 0 or missing, and no `lt_interest_status` is set.

After A, the three proadvero.com inboxes go into the `capacity.quarantine` ledger with reason `proadvero.com 7/7 Gmail seed spam 2026-09-25 (test 01a0dac3-e227-7eb6-8334-f0a75795b689)`. They are not paused and warm-up is not touched.

## Counts (live read-only dry-run, 2026-09-25)

| Campaign | Not started | Mid-sequence | Total |
|---|---|---|---|
| 2026 Cleaning - Trigger Outbound | 58 | 48 | 106 |
| 2026 Bookkeeping - Client Reactivation | 205 | 62 | 267 |
| 2026 Recruiting - Outbound (specialty roles) | 155 | 50 | 205 |
| 2026 Bookkeeping - Trigger Outbound | 190 | 64 | 254 |
| 2026 Cleaning - Client Reactivation | 45 | 47 | 92 |
| 2026 Recruiting - Client Reactivation | 174 | 56 | 230 |
| **Total** | **827** | **327** | **1,154** |

The earlier snapshot estimated 1,251 not started and 330 mid-sequence (1,581). The live read found 1,157 active Microsoft leads (827 never contacted, 330 mid-sequence). 3 mid-sequence leads have replied or carry an interest status and stay in their campaigns. The dry-run prints the current numbers each time it runs.

## Where the parked leads are

- Instantly lead list: `Parked - Microsoft recipients 2026-09-25`, id `<filled at apply time>` (the apply prints it and the manifest records it in `meta.list_id`).
- Manifest: `changesets/deliverability_2026_09_25/manifests/parked_leads_2026-09-25.csv` and `.json`, one row per lead. The rows record the original campaign, stage, last step, the move job, whether the lead was verified in the list and out of the campaign, and `skip_reason` for a planned lead that was not moved (for example `replied` if it replied after the dry-run). A lead the server moved without being asked gets a row with `skip_reason` `over_moved_by_server`, so a restore brings it back too. The manifest is written before the first move and updated after every batch.
- Copy of the manifest outside the repo: every write is also copied to `/Users/lorenzovillarreal/Desktop/AdveroSolutions/.tmp/deliverability_2026_09_25/` (the main checkout's `.tmp`, also when the script runs from a worktree; `.tmp` is never committed).
- The manifests hold names, emails and companies, so the whole `manifests/` folder is git-ignored (`Agentic Worklfows/.gitignore`). Check with `git check-ignore -v changesets/deliverability_2026_09_25/manifests/parked_leads_2026-09-25.json`.

## How to run

Dry-run (the default, sends no writes). It prints the email_list and allow_risky diff per campaign and the lead counts by campaign and stage, then writes the planned manifest to `manifests/parked_leads_2026-09-25.DRYRUN.csv`:

    python3 changesets/deliverability_2026_09_25/apply_deliverability.py

Apply (asks for a typed `yes` unless `--yes` is given):

    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/deliverability_2026_09_25/apply_deliverability.py --apply

Run the apply from the main checkout, not a worktree. The quarantine ledger is the local `.tmp/store.json` of whichever checkout runs the script, and the laptop's `inbox_inventory` job reads the main checkout's copy.

The script refuses and writes nothing if:
- any campaign is not paused;
- any `email_list` is neither the recorded 12 nor the target 9;
- a lead pull stops before its last page;
- an existing manifest cannot be read (it is left as it is);
- a campaign changed while the prompt was open;
- a campaign's before-image cannot be written to `changesets/backups/`.

The apply goes in this order: back up all campaigns, PATCH and re-read each one, quarantine the inboxes (an inbox already in the ledger keeps its entry), find or create the list, write the manifest, move the leads, then verify every manifest lead. It stops at the first campaign PATCH that fails verification.

How the lead moves are checked:
- The first move of the run is a 1-lead canary. The script then reads the campaign and the parked list and requires that exactly one lead left the campaign and that it is in the list. Anything else stops the run.
- Before each batch the source campaign is read again. Only leads still in it that still pass the rules are sent; the rest get a `skip_reason`.
- Each move sends at most 100 ids and `limit` = the number of ids. The script waits for the job, reads its `moved_leads` and `moved_lead_emails`, and stops if either differs from the batch.
- After each job the campaign and the list are read again before the next batch. A lead is stamped `moved_at` only when it is out of the campaign and in the list. A lead that left the campaign without being in the batch stops the run.
- A read that fails leaves the batch unstamped and stops. Polling a job stops after 3 answers of 4xx in a row, or after 20 minutes.
- A 409 from `leads/move` means another move job is running. The script re-reads the campaign, waits, and retries only the leads still in it.

A re-run is safe. What to move is decided from live state, not from the manifest: a lead still in its source campaign is sent again, a lead already in the list is not. Campaigns that are already applied get no PATCH, and existing manifest rows are kept.

## How to undo

**Campaigns (A and B).** Each apply writes a rollback point `changesets/backups/deliverability_2026_09_25_<campaign_id>_<ts>.json` holding the full campaign as it was. Restore one campaign at a time. Keys come from `config/ids.json`: `cleaning_trigger`, `cleaning_reactivation`, `bookkeeping_trigger`, `bookkeeping_reactivation`, `recruiting_outbound`, `recruiting_reactivation`.

    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/deliverability_2026_09_25/apply_deliverability.py \
        --restore changesets/backups/deliverability_2026_09_25_<campaign_id>_<ts>.json --campaign <key>

This uses `changesets/rollback.py` restore: it reads live, prints the diff, refuses if the fields changed after the apply (unless `--override-later-changes`), asks for the campaign key, and PATCHes only `email_list` and `allow_risky_contacts`. To remove the quarantine afterwards, run `python3 jobs/inbox_inventory.py --clear-quarantine <email>` for each inbox.

**Leads (C).** The following command reads the apply manifest and finds the rows not yet restored that are in the parked list (read with `leads/list {list_id}`). It moves them back to their original campaigns, grouped by campaign, with `{list_id, to_campaign_id}` and at most 100 ids per job. It is a dry-run unless `--apply` is given, and it refuses unless every target campaign is paused:

    python3 changesets/deliverability_2026_09_25/apply_deliverability.py --restore-leads
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/deliverability_2026_09_25/apply_deliverability.py --restore-leads --apply --limit 1
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/deliverability_2026_09_25/apply_deliverability.py --restore-leads --apply

After each job the campaign and the list are read again. `restored_at` is stamped only for a lead that is back in its campaign. A lead that did not come back, or a lead outside the batch that arrived, stops the run with a non-zero exit. A row recorded as parked that is neither in the list nor in its campaign is listed and also makes the exit non-zero.

Before you restore mid-sequence leads, restore one with `--limit 1` and check its step in the Instantly UI. It is not verified whether Instantly keeps a lead's progress when it moves back into a campaign. If it resets, those leads restart at step 1 and get email 1 again.

## Manual step if the quarantine is not recorded

The apply prints `QUARANTINE NOT RECORDED` when the ledger write fails. In that case, from the main checkout:

    python3 -c "from jobs.inbox_inventory import quarantine_inbox as q; [q(e, reason='proadvero.com 7/7 Gmail seed spam 2026-09-25 (test 01a0dac3-e227-7eb6-8334-f0a75795b689)', flags=['seed_test_gmail_spam']) for e in ('lorenzo@proadvero.com','lorenzov@proadvero.com','lorenzovillarreal@proadvero.com')]"

## What it does not do

- It does not change copy or sequences.
- It does not touch warm-up, pause accounts, or activate the campaigns.
- It does not handle the Zapmail captcha or any domain or DNS work.
- It does not move leads that are completed, bounced, unsubscribed, replied, or not Microsoft-hosted.

## Unverified until the first apply

- The `GET /background-jobs/{id}` response and its `status` values come from the API reference and have not been seen live.
- The `moved_leads` and `moved_lead_emails` fields of a finished move job (asked for with `data_fields`) are from the reference. If a job does not return them, the check falls back to reading the campaign and the list.
- Whether `leads/move` honours `limit` together with `ids` is unverified. If the canary is rejected over `limit`, nothing moves and the run stops.
- List membership is read with `leads/list {list_id}`, because live leads carry no `list_id` field. If that read returns leads that sit in a campaign, the filter is being ignored: the script stops and the membership has to be checked in the UI.
