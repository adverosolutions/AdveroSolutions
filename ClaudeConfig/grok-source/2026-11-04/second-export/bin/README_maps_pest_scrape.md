# maps_pest_scrape.sh - free Google Maps pest-control lead scraper

Free and open source. No sign-ups, API keys, proxies or paid tools. It runs on the box.
It does not touch Instantly, Google Sheets or any account. The output is a CSV for Lead Generation Specialist to review and stage.

## Parts
- `~/advero/opt/google-maps-scraper`: gosom/google-maps-scraper (MIT), built from source on 2026-10-20 (repo HEAD 2026-09-24). It uses headless Chromium from Playwright, cached in ~/.cache/ms-playwright.
  - To rebuild: `git clone --depth 1 https://github.com/gosom/google-maps-scraper /tmp/gms && cd /tmp/gms && go build -o ~/advero/opt/google-maps-scraper .`
- `~/advero/bin/site_email_crawl.py`: polite website email finder. It checks robots.txt, fetches at most about 5 pages per site (home, /contact, /contact-us, /about-us, plus one linked contact or about page), sends one request at a time per site, uses a 10 s timeout and an honest User-Agent, and tries https before http. Sites that return 403 (Cloudflare) get no retries and no evasion.
- `~/advero/bin/maps_postprocess.py`: normalizes the data, keeps only emails on the site's own domain or a freemail address, classifies each email, and dedupes by domain and email against:
  - `~/advero/state/leads/final-leads/final_pest_control_all_sources_output.csv`
  - `~/advero/state/leads/pool/*pest*.csv`
  - earlier `~/advero/state/leads/maps/pest_*.csv` outputs

## Run
```
~/advero/bin/maps_pest_scrape.sh ~/advero/state/leads/maps/cities/top200_metros.txt          # next 10 undone cities
MAX_CITIES=5 ~/advero/bin/maps_pest_scrape.sh <cities.txt> 20261022                             # custom size/tag
```
- The city file has one `City, ST` per line. `cities/top200_metros.txt` holds the top 200 US MSAs (Census 2025 order, from Wikipedia), using each MSA's principal city.
- Each run takes the next MAX_CITIES cities not yet listed in `maps/state/cities_done_<listname>.txt`. Cities are marked done only after a clean run.
- Output: `~/advero/state/leads/maps/pest_<TAG>.csv`. Logs and stats are in `maps/logs/`, raw files in `maps/raw/`, and a run history in `maps/state/runs.csv`.
- A lock file prevents overlapping runs.

## Safe-pace settings (defaults)
| Setting | Default | Why |
|---|---|---|
| CONC | 1 | One browser page at a time against Google Maps |
| DEPTH | 6 | About 60 to 70 places per query (Google caps a list near 120) |
| MAX_CITIES | 10 | 30 queries, about 1,500 to 2,000 raw places, about 75 min per night |
| QUERY_TERMS | pest control, exterminator, termite control | Overlap is deduped |
| EMAIL_WORKERS | 6 | Six different websites at once, one request each |
| MAX_PLACES | 2000 | Warns if a run gets bigger than this |
| Schedule | 1 run per night, 5 nights a week, e.g. 1:00 AM CT | Don't overlap the 11:10 PM QuickEnrich pull |

Measured on 2026-10-20 (5 queries at depth 5): 271 places, Maps phase about 6 min (about 45 places/min at c=1), email crawl about 5 min. There was no throttling, no captcha and no failed Maps jobs.

## Throttling rule: stop, don't evade
The script exits with code 3 and does NOT mark cities done when the log shows google.com/sorry, "unusual traffic" or reCAPTCHA, when 3 or more queries return 0 places, or when there are fewer than 5 places from 4 or more queries.
If that happens, wait at least 24 h, then halve MAX_CITIES and DEPTH. Do not add proxies, rotate user agents or raise concurrency to get around a block.

## Output columns
business_name, category, phone, website, domain, address, city, state, rating, reviews, emails_all,
email_named (person@company), email_freemail (gmail/yahoo etc., often the owner's), email_generic (info@/office@/contact@...),
email_type (named|freemail|generic|none), dedupe_status (new|existing|batch_dup|national_chain|suppressed), fit (good|check), chain,
business_status, query, maps_link, place_id, source=google_maps_gosom, reviews_as_of

`reviews_as_of` (added 2026-10-22) is the YYYY-MM-DD date (America/Chicago) the rating and review count were pulled. It is set on every row with a rating or review count and defaults to the run date; pass `--reviews-as-of YYYY-MM-DD` to maps_postprocess.py when re-processing an older raw file. Carry `rating`, `reviews` and `reviews_as_of` into maps_email_rows.csv so qe_dedupe keeps them as extra columns in the pool file, and write `reviews_as_of` to column V of the pest_control tab. Ratings change: `~/advero/bin/review_freshness.py` flags review data older than 14 days or undated. Earlier outputs (pest_test_20261020, pest_20261021, pest_20261022) and the two Maps pool files were backfilled from runs.csv and the scrape logs on 2026-10-22.

Only `dedupe_status=new` rows are candidates. Rows with a domain but no email (about 60%) should go through the QuickEnrich Domain Finder to get owner emails. Generic-only rows belong in a separate info@ campaign. Verify any email before it gets loaded.
Note: the 5 test cities (Dallas, Houston, Phoenix, Atlanta, Tampa) aren't marked done for top200. A full run re-scrapes them with all 3 terms, and dedupe removes repeats.

## Suppression (do_not_reload, 2026-10-21)
`maps_postprocess.py` reads `~/advero/state/reactivation/do_not_reload.csv` (read only) through `suppression.py`. Any email whose suppress_until is still in the future (America/Chicago) is removed from emails_all, email_named, email_freemail and email_generic. A row left with no email that would otherwise be new gets `dedupe_status=suppressed` and is not a candidate. Stats show `suppressed` (emails), `suppressed_rows` and `suppression` (on/off). If the file is missing, the run warns loudly and continues with suppression off. The later `qe_dedupe.py` append step and the MillionVerifier queue filter (`suppression.py filter`) apply the same rule. Test override: `--suppress-file <csv>`.

## Client cross-referencing (2026-10-21)
maps_postprocess.py skips rows whose domain or email is already in ~/advero/state/clients/INDEX.csv (dedupe_status=client_known; stats client_known, client_known_hits). Logic in client_index.py (read only). Mention any hits in the COO summary.
