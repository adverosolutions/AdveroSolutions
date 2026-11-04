# maps_rolling.sh (Maps Bot, 2026-11-01)
Rolling Google Maps crawl, batches of BATCH metros (default 5, DEPTH default 3 since 11/2 half-size resume after 11/1 throttle; env BATCH=/DEPTH= override): pest top200 -> cleaning top200 (4 cleaning terms, residential HELD from MV)
-> US cities by 2024 pop (cities/us_cities_by_pop.txt, Census sub-est2024, top200 removed), alternating pest / commercial cleaning
(commercial cleaning|janitorial service). Done files: cities_done_top200_metros, cities_done_cleaning_top200_metros,
cities_done_us_cities_by_pop, cities_done_cleaning_us_cities_by_pop. A city is marked done only if all its lists came back >=90%.
- Start/resume: nohup ~/advero/bin/maps_rolling.sh >> /workspace/maps_rolling/runner.out 2>&1 &   (unfinished batch resumes first)
- Stop after current batch: touch /workspace/maps_rolling/STOP. Pause new batches: touch ~/advero/state/leads/maps/state/PAUSE_MAPS (checked every 60 s).
- KILL_SWITCH checked before each crawl and post step. Shares maps_pest_scrape.lock with the nightly script (blocking wait).
- Throttle (sorry/unusual traffic/captcha, >=3 zero lists, <5 places, exit 3): runner exits, writes STOPPED_THROTTLE to status and
  /workspace/maps_rolling/STOPPED_THROTTLE; it refuses to start while that marker exists.
- Per batch dir /workspace/maps_rolling/batches/NNN_TAG: values.json staged + READY_FOR_SHEET. Sheet write is manual (Maps Bot):
  1) get_spreadsheet grid + read col E for real last row; extend grid (appendDimension) if needed
  2) write_range A<start>:V (pest) / A:T (cleaning) with values "$file:<BD>/values.json"
  3) read_range back (write_to_file) -> python3 ~/advero/bin/maps_rolling_readback.py <file> <BD>/values.json (mismatch 0)
  4) python3 ~/advero/bin/maps_rolling_finalize.py <BD> <start>  (MV queue, held residential, quickenrich_pulls.csv, decisions.jsonl, SHEET_DONE)
- Status: /workspace/maps_rolling_status.md. No manual fit overrides in this runner. Never runs MV, QE or qe_fit.py.
