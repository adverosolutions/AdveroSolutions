# Dashboard sheet refresh — CRON_TZ=America/Chicago 5 7-22 * * *, flexible ±15
Taken over from COO on 2026-10-27 with Lorenzo's approval (COO chat, 12:37 PM CT: "Yes, offload those routines and make the Reminders bot"). If ~/advero/state/KILL_SWITCH exists, stop quietly.

Refresh Lorenzo's ops dashboard cache by following ~/advero/dashboard/SHEETS_REFRESH.md exactly. Use the Google Sheets connector, read-only, to read three tabs: the Daily Log tab of the $20K sprint sheet (1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0), and the Pipeline and Goal tabs of the CRM sheet (162UL8KgMo2U--ArMl0ieBE19LqcOWjmkYdFbBbqXj9s). Save each one into ~/advero/dashboard/cache/ with ingest_sheet_dump.py. Then check that the dashboard is up: curl http://127.0.0.1:8787/ should return 200. If it doesn't, run ~/advero/dashboard/start.sh and check again.

This routine is read-only. Never write to any sheet, campaign, list or setting.

Delivery: send nothing to anyone when the refresh works. If the dashboard is still down after the restart, send COO (Grok Bot teammate, id 732ca015-c7c3-412e-92f7-f9b2de73d050) one line saying so. Never message Lorenzo directly.
