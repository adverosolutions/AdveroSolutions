# RUNBOOK — Med Spa Cold-Email System

Operator guide. No coding needed. ~10 min start to finish per city.

The flow:  **Scrape → Part A → Hunter → Part B → Instantly**

---

## One-time setup (do this once)

1. Open **Terminal** (press `Cmd + Space`, type `Terminal`, hit Enter).
2. Confirm Python is installed — type this and press Enter:
   ```
   python3 --version
   ```
   You should see `Python 3.x.x`. If you see "command not found", install Python
   from https://python.org (the macOS installer), then reopen Terminal.
3. (Optional confidence check) Do a dry run on the sample files — see the very
   bottom of this file.

### For the AI verification step (optional but recommended)
Part A can have Claude double-check each business and drop chains, suppliers,
and unrelated results the keyword list missed. To enable it (one time):

1. Install the library — in Terminal:
   ```
   python3 -m pip install anthropic
   ```
2. Create a file named `.env` inside the tool folder with this one line
   (paste your real key after the `=`):
   ```
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

If you skip this, Part A still runs — it just prints "AI verification SKIPPED"
and keeps every row. To turn the step off on purpose, open `part_a.py` and set
`AI_VERIFY = False`.

---

## Every time you want leads

### STEP 1 — Scrape Google Maps (free scraper)
Use the scraper in the sibling `maps-scraper` folder — it pulls the real
**website** for each med spa (Instant Data Scraper can't, because Google hides
it behind the "Book online" button). One-time setup is in
`maps-scraper/README.md` (`pip install playwright` + `playwright install
chromium`).

1. In Terminal:
   ```
   cd ~/Desktop/AdveroSolutions/Coding/maps-scraper
   python3 scrape_maps.py
   ```
2. Enter a search (e.g. `med spa Dallas`) and how many listings to pull.
   Do **one city at a time**.
3. A Chrome window opens and works through the listings (solve a Google
   "are you human?" check by hand if it ever appears).
4. Output lands in **Downloads** as e.g. `med_spa_Dallas_maps.csv`.

### STEP 2 — Run Part A (clean the scrape)
1. In Terminal, go to the tool folder (copy-paste this, press Enter):
   ```
   cd ~/Desktop/AdveroSolutions/Coding/med-spa-cold-email
   ```
2. Start Part A:
   ```
   python3 part_a.py
   ```
3. It asks **"Path to the Instant Data Scraper CSV:"**
   → Open Finder, **drag the CSV from Downloads into the Terminal window**
   (this types the path for you), press Enter.
4. It asks **"Fallback city:"** → the city is now read automatically from each
   business's GPS pin, so this is just a backup for the few it can't match.
   Type your search city (e.g. `Dallas`) or press Enter to skip.
5. If AI verification is set up, it now checks each company one by one (a
   couple of minutes for a few hundred — you'll see live progress). Otherwise
   it prints "AI verification SKIPPED" and continues instantly.
6. Read the summary. **Glance at the "Detected columns" block** — business
   name / website / rating / review should each point at a column, NOT say
   "NOT FOUND". The summary also lists any companies the AI removed. Then note
   the **Output file** line.
   → It's saved next to your scrape, named `..._cleaned_for_hunter.csv`.

### STEP 3 — Find emails (Anymail Finder)
1. Open the `..._cleaned_for_hunter.csv` and feed the **`domain`** column to
   Anymail Finder (its decision-maker / domain search).
2. Export the results. Anymail's export carries your business data through and
   adds the owner's real name + verified email.

### STEP 4 — Run Part B (build the upload file)
1. Back in Terminal (same folder), start Part B:
   ```
   python3 part_b.py
   ```
2. It asks for **"Path to the email-finder export"** → drag the Anymail export
   in, Enter. (Anymail files are self-contained, so that's the only file it
   needs. A bare Hunter list would also prompt for the Part A output.)
3. Read the summary — it should say "with a real first name: <most rows>".
   Output is `..._instantly_ready.csv` (next to the export).

### STEP 5 — Upload to Instantly
1. In Instantly → your campaign → **Leads → Import → CSV**.
2. Upload `..._instantly_ready.csv`.
3. Map the columns: `firstName`, `email`, `companyName`, `city`,
   `reviewCount`, `website`, `googleMapsUrl`.
4. Launch. Done.

---

## Sanity checks (10-second habit)
- **Part A "Detected columns"** all found? If website or name says "NOT FOUND",
  Google changed the scrape format — stop and get help.
- **Rows out** is reasonable (a few hundred from ~1,000+ scraped is normal —
  most Maps listings have no website and can't be cold-emailed).
- Open the final CSV once and eyeball that emails and names look right.

## If something goes wrong
- **"NO REAL WEBSITES FOUND IN THIS SCRAPE"** (and the output is tiny) → your
  scrape captured the **"Book online"** link (Vagaro/Zenoti/etc.), not the
  **Website** link. Hunter needs a real domain. Re-scrape the Google Maps
  results so the **Website** column is captured, then run Part A again.
- `command not found: python3` → install Python (setup step 2), reopen Terminal.
- `File not found` → you dragged the wrong file, or there are stray quotes.
  Just run the command again and re-drag.
- It re-asks for the path up to 3 times, then exits — just rerun.
- Output looks empty / all "NOT FOUND" columns → the scrape format changed.

## Optional tuning (advanced)
Open `part_a.py` in a text editor. At the top you can change:
- `CONSERVATIVE = True` → set `False` for more first names (but some wrong ones).
- `MIN_REVIEWS = 25` → lower it for more volume. `MAX_REVIEWS = None` keeps all
  high-review independents; set a number (e.g. `1000`) to re-add an upper cap.
- `CHAINS`, `BRAND_WORDS`, `PLACE_WORDS`, `PLATFORM_DOMAINS` → add words to
  exclude. `ROLE_WORDS` in `part_b.py` → generic emails to drop.

---

## Dry run (practice without real data)
From the tool folder:
```
python3 part_a.py
```
- path: drag in `sample_maps.csv` (in this folder) → city: type `Dallas`
- then:
```
python3 part_b.py
```
- Hunter path: drag in `sample_hunter.csv`
- Part A path: drag in `sample_maps_cleaned_for_hunter.csv` (just created)

Look at the two output files to see exactly what each step produces.
