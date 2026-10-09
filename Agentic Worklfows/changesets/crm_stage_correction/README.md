# crm_stage_correction

Finds and corrects CRM rows ("HVAC Leads", "Roofing Leads") that the legacy Instantly sync mislabelled by misreading `esp_code`, lead status 3 and Out of Office. Full steps and order: `runbooks/lead_sync_esp_code_fix.md`. First confirm the old sync actually wrote rows, then stop `advero-lead-sync` before applying and redeploy the fixed sync afterwards.

- `--dry-run` (default): opens the sheet read-only, builds the plan and saves it to `.tmp/crm_stage_correction/plan_<stamp>.json` with the spreadsheet id it read. Nothing is written. Add `--tab <name>` (repeatable) to read other tabs, and `--mx` to flag "Closed - Lost" rows with no Instantly lead whose domain's MX is Zoho. Entries marked `confidence: "review"` list their `review_reasons`.
- `--crm-snapshot <json>` / `--leads-snapshot <json>`: offline inputs for the dry-run. With both, it uses no network. A plan from a CRM snapshot has no spreadsheet id and cannot be applied live.
- `--apply --plan-file <plan>`: live only (`MODE=live ALLOW_LIVE_WRITES=1`). In order: refuses a plan from another spreadsheet or a snapshot; reads and skips rows that changed since the plan (and every row of a tab whose header lacks Stage, Email or Last Updated); asks for the row count unless `--yes`; reads again and writes nothing if anything differs from what was confirmed; backs up from that fresh read; writes one batch_update per tab. After any batch_update is sent the backup is the unsuffixed, restorable rollback point, even if the call raised.
- `--restore <backup>`: live only. Same order (sheet id check, read, confirm, re-read, `.prerestore` copy, write). It puts back the backed-up Stage and Last Updated values on rows that still hold the corrected stage.

Do not edit or sort the CRM tabs while an apply or restore runs.

`legacy_mapping.py` holds a verbatim copy of the old mapping and names the branch that fired for each lead. Tests: `changesets/tests/test_crm_stage_correction.py`.
