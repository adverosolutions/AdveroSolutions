# Mass Scrape Leads (Google Maps)

**Purpose:** Scrape 200K+ business leads from Google Maps across 200 US metros
**Cost:** $0 (Playwright + Google Sheets, no APIs)
**Runtime:** 24/7, runs in tmux, auto-resumes on crash
**Industries:** Pest Control, Garage Door, Landscaping, Pool Service & Repair

---

## What This Does

The Mass Lead Scraper:
1. Searches Google Maps for businesses by industry + city (100 results per search)
2. Runs 4 parallel Playwright browsers for speed (~36K leads/hour)
3. Deduplicates across all searches via SQLite
4. Batch writes to Google Sheets (one tab per industry)
5. Tracks progress in SQLite so it can resume after crashes

---

## Usage

### Test Mode (verify it works)
```bash
# Scrape 1 city, print results, no sheet write
python execution/mass_scraper.py --test

# Scrape 1 city AND write to Google Sheets
python execution/mass_scraper.py --test --save
```

### Production Run (24/7)
```bash
# Start in tmux for 24/7 operation
tmux new -s scraper

# Fresh start - all 4 industries, 200+ cities, 4 parallel browsers
python execution/mass_scraper.py

# Resume after crash/restart
python execution/mass_scraper.py --resume

# Detach from tmux: Ctrl+B then D
# Reattach later: tmux attach -t scraper
```

### Custom Runs
```bash
# Specific industries only
python execution/mass_scraper.py --industries "pest control" "landscaping"

# More parallel browsers (faster, more resource-heavy)
python execution/mass_scraper.py --parallel 6

# Skip metro subdivisions (base 200 cities only)
python execution/mass_scraper.py --no-subdivisions

# Check progress
python execution/mass_scraper.py --stats

# Start completely fresh
python execution/mass_scraper.py --reset
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--industries` | pest control, garage door repair, landscaping, pool service and repair | Industries to scrape |
| `--parallel` | 4 | Number of parallel browser instances |
| `--resume` | false | Continue from last progress |
| `--no-sheets` | false | Skip Google Sheets output |
| `--no-subdivisions` | false | Skip neighborhood-level searches |

### .env Variables
```
SCRAPER_SHEET_ID=<your_google_sheet_id>
```

---

## Output

Leads are written to the scraper Google Sheet with tabs:
- `Pest Control`
- `Garage Door`
- `Landscaping`
- `Pool Service`

### Schema
| Field | Description |
|-------|-------------|
| company_name | Business name |
| phone | Phone number |
| address | Street address |
| city | City |
| state | State |
| website | Website URL |
| industry | Search industry |
| source_query | The Google Maps search used |
| scraped_at | Timestamp |

---

## Execution Scripts

| Script | Purpose |
|--------|---------|
| `execution/mass_scraper.py` | Main orchestrator (entry point) |
| `execution/google_maps_scraper.py` | Playwright scraper engine |
| `execution/scraper_sheets.py` | Google Sheets batch writer |
| `execution/us_metros.py` | Top 200 US metro areas + subdivisions |

### Data Files
| File | Purpose |
|------|---------|
| `execution/scraper_progress.db` | SQLite progress tracker (do not delete during runs) |
| `execution/scraper.log` | Runtime log |

---

## Throughput

- 100 results per Google Maps search (Google's max)
- ~30 seconds per search with scrolling
- 4 parallel browsers = ~36,000 leads/hour
- 200 base cities + ~250 subdivision neighborhoods = ~450 locations
- 4 industries × 450 locations = 1,800 searches
- **~180,000 raw leads → ~200K after dedup within ~5 hours**

---

## Troubleshooting

### "Playwright not installed"
```bash
pip install playwright && python -m playwright install chromium
```

### "SCRAPER_SHEET_ID not set"
Create a Google Sheet, share it with `advero-crm-automation@adverosolutions.iam.gserviceaccount.com` (Editor), and add the Sheet ID to `.env`.

### "Google rate limiting / CAPTCHAs"
- Reduce `--parallel` to 2-3
- The scraper already has random delays built in
- If persistent, restart after 30 minutes

### "Scraper crashed mid-run"
Just run `python execution/mass_scraper.py --resume` - it picks up exactly where it left off.

### "Want to start over"
```bash
python execution/mass_scraper.py --reset
```
This clears the SQLite database. The Google Sheet data remains.

---

## Learned Constraints

- Google Maps returns max 100 results per search query
- Use `wait_until="domcontentloaded"` not `"networkidle"` (Maps never fully stops loading)
- Phone numbers need `'` prefix in Sheets to prevent number formatting
- Service account Drive storage can fill up - use manually created sheets shared with the service account
