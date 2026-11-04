# Google Sheets recache (every 30 min, 7:00 AM to 10:00 PM CT, daily)

The box has no Google credentials; the Sheets data comes from the agent's `user-Google-sheets` connector (read-only).
A routine (COO or Revenue Operations) must run these steps each slot:

1. `read_range` with `write_to_file: true`, spreadsheetId `1FW8AmsL5CmmiUAYHt4lx3MFbjUjfiYVV_rQ4HIqRbP0`,
   ranges `[{"sheet":"Daily Log","cells":"A1:O91"}]`.
2. `read_range` with `write_to_file: true`, spreadsheetId `162UL8KgMo2U--ArMl0ieBE19LqcOWjmkYdFbBbqXj9s`,
   ranges `[{"sheet":"Pipeline","cells":"A1:AA1000"},{"sheet":"Goal","cells":"A1:J40"}]`.
3. For each result file: `python3 ~/advero/dashboard/ingest_sheet_dump.py <result file> x`
   (writes ~/advero/dashboard/cache/sheet_<id>_<tab>.json atomically, stamped fetched_at in CT).
4. Silent unless a read fails twice in a row. Never writes to any sheet.

The dashboard shows each cache's fetched_at and a red note when it is over 45 min old between 7 AM and 10 PM CT.
