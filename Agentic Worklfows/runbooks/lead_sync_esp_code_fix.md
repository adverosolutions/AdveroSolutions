# Lead sync esp_code fix: correcting the CRM

The old daily Instantly -> CRM sync (`execution/instantly_lead_sync.py`, Modal app `advero-lead-sync`) wrote wrong Stage values into the CRM sheet. The sync code is fixed on branch `fix/lead-sync-esp-code`. This runbook covers the CRM rows it already got wrong.

Change-set: `changesets/crm_stage_correction/apply_crm_stage_correction.py`. Every command below is yours, run from `Agentic Worklfows/` in your own terminal.

## 1. What went wrong

The old sync misread three Instantly fields:

- **`esp_code`** is the lead's email provider (1 Google, 2 Microsoft, 3 Zoho, 999 Other). The sync read 3 as "bounced" and 2 as "delivered".
- **Lead `status` 3** means Completed (the sequence finished). The sync read it as "replied".
- **`lt_interest_status` 0** means Out of Office. The sync counted those auto-replies as neutral replies.

Its leads/list call also sent a `campaign_id` body key the API does not document, so each per-campaign pull most likely returned every lead in the workspace. The change-set therefore matches leads to CRM rows by email across all leads.

Affected rows, in tabs "HVAC Leads" and "Roofing Leads" only:

- Zoho-hosted leads set to "Closed - Lost". The sync never leaves "Closed - Lost", so they stayed there.
- Microsoft-hosted active leads set to "Contacted" before any email went out.
- Completed leads that never replied set to "Replied - Neutral".
- Out-of-office auto-replies counted as replies ("Replied - Neutral").
- Google- and other-hosted leads never moved to "Contacted". The change-set leaves these alone; the fixed sync moves them forward on its next run.

## 2. Background

- `advero-lead-sync` **is deployed** in Modal workspace `adverosolutions` (v1, 2026-03-04, per `modal app list` / `app history` on 2026-09-25), even though older runbooks say it is not.
- Its past run logs are only in the Modal dashboard.
- Google Sheets version history (File > Version history) shows the service account's edits, including what a row said before the sync overwrote it.
- Unknown: whether the Instantly key in the `advero-lead-sync` Modal secret still reaches the HVAC/Roofing campaigns. The current workspace has only the six 2026 campaigns. If those leads are gone from Instantly, the dry-run can only find the Zoho rows through `--mx`.

## 3. Order

**a. Confirm the old sync actually wrote rows.** Open the Modal dashboard, workspace `adverosolutions`, app `advero-lead-sync`, and look through its run logs for a `Stages updated:` line above 0. If the logs are gone, spot-check a few flagged rows in Sheets version history for edits by the service account. If the old sync never wrote a Stage, every row the dry-run flags is a false positive: apply nothing and stop here.

**b. Stop the old sync.** The deployed code runs every day at 09:00 UTC and would undo the correction (a corrected Zoho row goes back to "Closed - Lost" the next morning).
```
MODAL_PROFILE=adverosolutions python3 -m modal app stop advero-lead-sync
```

**c. Dry-run the fixed sync and the change-set** with the Instantly key the `advero-lead-sync` Modal secret holds. Open a fresh terminal and set the key there only; the Instantly client reads it from the environment, and `load_dotenv` does not override a variable that is already set. Never paste the key into a file in the repo.
```
export INSTANTLY_API_KEY=...        # the value from the advero-lead-sync secret
python3 execution/instantly_lead_sync.py --dry-run
python3 changesets/crm_stage_correction/apply_crm_stage_correction.py --dry-run
python3 changesets/crm_stage_correction/apply_crm_stage_correction.py --dry-run --mx
```
The change-set's dry-run opens the sheet with the read-only Sheets scope, prints the rows it would change and saves the plan to `.tmp/crm_stage_correction/plan_<stamp>.json`. Nothing is written. The plan records the spreadsheet id it was read from. A plan built with `--crm-snapshot` records none and can never be applied live. If a tab's header does not name "Stage", "Email" or "Last Updated", the dry-run prints a WARNING for it and apply/restore will not write that tab.

**d. Review the plan file.**
- Delete an entry to skip that row.
- `confidence: "review"` comes with a `review_reasons` list. Check each one before keeping the entry:
  - `notes`: the row has Notes.
  - `last_updated_before_legacy_sync_deploy`: Last Updated is before 2026-03-04. The old sync always wrote Last Updated with Stage, so it did not set this Stage.
  - `last_updated_before_lead_created`: Last Updated is before the Instantly lead existed, so the old sync did not set this Stage from that lead.
  - `last_updated_empty` / `last_updated_unreadable`: the dates cannot be checked.
  - `prior_stage_unknown`: Instantly has no signal for the lead, so the plan proposes "New/Uncontacted". Version history has the real earlier value if you want it instead.
- `needs_review` entries have `proposed_stage: null`. They cover the same email on two rows, a Zoho-hosted domain (by MX) with no Instantly lead, and a lead Instantly marks unsubscribed (-2) or skipped (-3, may mean blocklisted) that would otherwise go back to "New/Uncontacted". Set `proposed_stage` to include one.

**e. Apply.** Do not edit or sort the CRM tabs while this runs.
```
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/crm_stage_correction/apply_crm_stage_correction.py --apply --plan-file .tmp/crm_stage_correction/plan_<stamp>.json
```
The steps run in this order:
1. It refuses if the plan's spreadsheet id is missing or is not the sheet `GOOGLE_SHEET_ID` opens.
2. It reads each tab and skips any row whose email or Stage changed since the plan, plus every row of a tab whose header lacks Stage, Email or Last Updated.
3. It prints the rows and asks you to type the row count.
4. It reads every tab again and works the writes out again. If any row, email, Stage or column differs from what you confirmed, it writes nothing (no backup, no write) and exits 2. Re-run it to see the new list.
5. It writes the before-values from that fresh read to `changesets/backups/crm_stage_correction_before_<stamp>.json`. If that fails, nothing is written.
6. It sets Stage and Last Updated, one batch_update per tab, and stops at the first error. If a batch_update raises, the script re-reads that tab and says whether the write landed, did not land, or is unknown. The backup stays restorable either way.

Without `MODE=live ALLOW_LIVE_WRITES=1` it only prints what it would do.

**f. Check a few rows** in the sheet: a corrected Zoho row, a Microsoft row and a completed row. Compare them with the plan.

**g. Redeploy the fixed sync.** Stopping it in step b leaves the CRM unsynced until you do.
```
MODAL_PROFILE=adverosolutions python3 -m modal deploy execution/modal_lead_sync.py
```

**h. Undo, if needed.** Do not edit or sort the CRM tabs while this runs either.
```
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/crm_stage_correction/apply_crm_stage_correction.py --restore changesets/backups/crm_stage_correction_before_<stamp>.json
```
It checks the backup's spreadsheet id, reads, asks for the row count, reads again and refuses if anything moved, saves the current values as a `.prerestore.json` copy, then puts back the old Stage and Last Updated. It only touches rows that still hold the corrected stage, and it lists the rows it skipped.

Which backups can be restored:
- `crm_stage_correction_before_<stamp>.json` (no suffix): the rollback point of an apply that sent at least one write, including one that stopped on an error.
- `...before_<stamp>.preapply.json`: the run died while writing. It can be restored, but compare it with the sheet first.
- `.prerestore.json`: refused. It is the state a restore overwrote. To redo the correction, re-run the apply with the plan.
- `.not_applied.json`: refused. Nothing was sent.

If an apply stopped partway and you re-run it, the second run writes its own backup. Keep both. Undoing everything takes a `--restore` of each, newest first.

Offline check with no network: `--dry-run --crm-snapshot <file> --leads-snapshot <file>` (the test fixtures in `changesets/tests/fixtures/crm_stage_correction/` show the format).

## 4. Schedule note

`modal.Cron("0 9 * * *")` has no timezone, so it runs at 09:00 UTC (04:00 CDT). The code comment says 09:00 CT, which is wrong.
