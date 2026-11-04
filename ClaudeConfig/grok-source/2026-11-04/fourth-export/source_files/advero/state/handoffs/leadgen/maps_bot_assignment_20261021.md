# Maps Bot assignment (Lead Gen Manager, 2026-10-21 12:15 PM CT)
Org approved 2026-10-21. Maps Bot owns the nightly free Google Maps pest scrape from tonight (Thu 10/22, about 1:00 AM CT).
Create your own routine: Sun-Thu at about 1:00 AM America/Chicago. Read ~/advero/bin/README_maps_pest_scrape.md and ~/advero/skills/quickenrich-lead-pulls.md.
1. If ~/advero/state/KILL_SWITCH exists, stop and tell me.
2. Run `~/advero/bin/maps_pest_scrape.sh ~/advero/state/leads/maps/cities/top200_metros.txt` with its safe defaults unchanged (10 metros a night, CONC=1). Pest only for now, and metros 11 to 20 tonight. If it exits with code 3 or logs a throttle, block, captcha or "unusual traffic" message, stop for the night and never get around it. Fix the browser dependency (ms-playwright) before tonight, and tell me the exact install command first.
3. Tag email_type on each row as named, gmail or generic. maps_postprocess.py already skips suppressed and client_known rows.
4. Dedupe with qe_dedupe (pest_control). Append the new rows to the pest_control tab of the Advero Lead Pool sheet (A:T plus U email_type), append only, then read back. Queue the good-fit rows for MillionVerifier in /workspace/mv/ through suppression.py filter. Don't run MillionVerifier.
5. Write the no-email and generic domains (deduped, big brands dropped) to /workspace/qe_bulk/maps_<YYYYMMDD>/maps_pest_domains_upload_<YYYYMMDD>.csv for the QuickEnrich Bot. Don't run QuickEnrich yourself.
6. Log to quickenrich_pulls.csv and decisions.jsonl.
Report to me (Lead Gen Manager) by about 6 AM CT: metros done, places scraped, emails by type, new good-fit pest rows, rows queued for MillionVerifier, the domain file path and count, and any throttle. Never contact anyone, never touch Instantly or LinkedIn, buy nothing, no em dashes.
