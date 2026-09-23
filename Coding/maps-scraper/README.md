# Free Google Maps Scraper

Pulls business **websites** (plus name, rating, reviews, address) straight from
Google Maps — the data Instant Data Scraper can't see because it lives on each
listing's detail page, not the results list.

Completely free, runs on your Mac, no accounts / API keys / card.

## One-time setup
```
cd ~/Desktop/AdveroSolutions/Coding/maps-scraper
python3 -m pip install playwright
python3 -m playwright install chromium
```

## Run
```
python3 scrape_maps.py
```
- Enter a **search** (e.g. `med spa Dallas`) and a **max listings** count.
- A Chrome window opens so you can watch it. If Google ever shows an
  "are you human?" check, solve it by hand and it continues.
- Output saves to **Downloads** as e.g. `med_spa_Dallas_maps.csv`.

## Then feed it to the cleaner
The output drops straight into the med-spa tool — no edits needed:
```
cd ~/Desktop/AdveroSolutions/Coding/med-spa-cold-email
python3 part_a.py        # give it the _maps.csv from Downloads
```
Full flow: **scrape_maps.py → part_a.py → Hunter/Anymail → part_b.py**

## Tips & notes
- **Run one city at a time** and keep volume reasonable — it opens each listing,
  so it's slower than a list scrape, and polite pacing avoids getting blocked.
- It captures the website that exists on the listing. A business that genuinely
  has no website (booking-only) comes through with a blank website — Part A
  drops those (Hunter needs a real domain).
- `HEADLESS = True` at the top of `scrape_maps.py` hides the browser window
  (faster, but you can't solve a CAPTCHA). Leave it `False` for normal use.
- If Google changes their page and a column comes back blank for everyone,
  the CSS selectors near the top of `scrape_maps()` need a small update.
