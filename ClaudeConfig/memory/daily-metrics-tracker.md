---
name: daily-metrics-tracker
description: "Daily outreach metrics tracker in Google Sheets — sheet id, rebuild command, and the service-account Drive quota constraint"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7fa3274e-1f8f-4f88-8888-73c7ad360755
  modified: 2026-08-03T11:49:50.335Z
---

Lorenzo logs outreach/pipeline/revenue metrics daily (Nick Sariev-style compounding view), started 2026-08-03. Mandatory daily task for him.

Spreadsheet: "AdveroSolutions - Daily Metrics", id `1GuJBW_FSZJsJZ9gmN37EmTGo65DH695BtwhFkBXWDj0`. Tabs: Dashboard / Daily Log / Weekly.

Built and rebuilt idempotently by `Agentic Worklfows/execution/build_daily_metrics_tracker.py`:

```
python3 execution/build_daily_metrics_tracker.py --id <SHEET_ID>
```

Rebuild drops and recreates the three tabs; the Daily Log's typed data is lost on rebuild, so export/re-import raw log values if rebuilding after real data exists. Adding a metric = one entry in the `METRICS` list + rerun.

**Why:** The service account `advero-crm-automation@adverosolutions.iam.gserviceaccount.com` has zero Drive storage quota, so it CANNOT create new spreadsheets (403 storageQuotaExceeded). Any new Google Sheet must be created by Lorenzo and shared to the SA as Editor first, then targeted with `--id`. This applies to every script in this repo that would create a sheet.

**How to apply:** When a task needs a new Google Sheet, don't call `client.create()` — ask Lorenzo to create + share it, then find its id with `client.list_spreadsheet_files()`. Also note gspread here is v5.12, so call `ws.update(range_name=..., values=...)` with keywords; positional order differs between v5 and v6 and silently writes to the wrong range. See [[project_architecture]].
