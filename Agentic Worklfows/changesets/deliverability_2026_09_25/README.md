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
- Manifest: `changesets/deliverability_2026_09_25/manifests/parked_leads_2026-09-25.csv` and `.json`, one row per lead. The rows record the original campaign, stage, last step, the move job, and whether the lead was verified in the list and out of the campaign. The manifest is written before the first move and updated after every batch.
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
- a campaign changed while the prompt was open;
- a campaign's before-image cannot be written to `changesets/backups/`.

The apply goes in this order: back up all campaigns, PATCH and re-read each one, quarantine the inboxes, find or create the list, write the manifest, move the leads batch by batch, then verify every manifest lead. It stops at the first campaign PATCH that fails verification. A re-run is safe: campaigns that are already applied get no PATCH, leads already moved are no longer selected, and the existing manifest rows are kept.

A 409 from `leads/move` means another move job is running. The script re-reads the batch, waits, and retries only the leads still in the campaign. Any other error stops the moves and leaves the manifest showing what moved.

## How to undo

**Campaigns (A and B).** Each apply writes a rollback point `changesets/backups/deliverability_2026_09_25_<campaign_id>_<ts>.json` holding the full campaign as it was. Restore one campaign at a time. Keys come from `config/ids.json`: `cleaning_trigger`, `cleaning_reactivation`, `bookkeeping_trigger`, `bookkeeping_reactivation`, `recruiting_outbound`, `recruiting_reactivation`.

    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/deliverability_2026_09_25/apply_deliverability.py \
        --restore changesets/backups/deliverability_2026_09_25_<campaign_id>_<ts>.json --campaign <key>

This uses `changesets/rollback.py` restore: it reads live, prints the diff, refuses if the fields changed after the apply (unless `--override-later-changes`), asks for the campaign key, and PATCHes only `email_list` and `allow_risky_contacts`. To remove the quarantine afterwards, run `python3 jobs/inbox_inventory.py --clear-quarantine <email>` for each inbox.

**Leads (C).** The following command reads the apply manifest, finds which manifest leads are still in the parked list, and moves them back to their original campaigns. It groups them by campaign and uses `{list_id, to_campaign_id}` with at most 100 ids per job. It is a dry-run unless `--apply` is given:

    python3 changesets/deliverability_2026_09_25/apply_deliverability.py --restore-leads
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/deliverability_2026_09_25/apply_deliverability.py --restore-leads --apply

Before you restore mid-sequence leads, move one back and check its step in the Instantly UI. It is not verified whether Instantly keeps a lead's progress when it moves back into a campaign. If it resets, those leads restart at step 1 and get email 1 again.

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
- The membership check assumes a parked lead shows `list_id` = the parked list and `campaign` null. The field is in the reference, but the live campaign leads read on 2026-09-25 do not carry `list_id` at all. If verification reports `verified_in_list` false for leads that plainly moved, check one lead with `GET /leads/{id}` before re-running.
