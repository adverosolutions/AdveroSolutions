# Med Spa Cold-Email Lead Tool

Two standalone Python scripts. Runs on Windows or Mac. Standard library only,
**except** Part A's optional AI verification step, which uses the Anthropic API
(`pip install anthropic` + an `ANTHROPIC_API_KEY`). If that key/package is
missing, Part A simply skips the AI step and keeps all rows — everything else
still works with zero setup.

```
Google Maps scrape (Instant Data Scraper)
        │
        ▼   part_a.py   →  <input>_cleaned_for_hunter.csv   (domains + names)
        │
        ▼   Hunter.io bulk domain search  →  hunter_export.csv
        │
        ▼   part_b.py   →  <hunter>_instantly_ready.csv     (upload to Instantly)
```

## Part A — `python part_a.py`
Cleans a Google Maps scrape and produces a Hunter-ready list.

1. Filters: removes reviews <25 (too new/inactive), rating <4.0, and
   no/invalid website. **No upper review ceiling by default** — high-review
   independents are kept (franchises are removed by step 2, not by review count).
2. Drops national med spa chains/franchises (Ideal Image, LaserAway,
   Milan Laser, Sono Bello, European Wax, …).
3. Extracts an owner first name from the business name (else `there`).
4. Strips websites to a base domain and **de-duplicates by domain**.
5. Tags each business with a **city** from the GPS pin in its Google Maps link
   (offline — no API), and keeps the **Google Maps link** itself.
6. **AI verification** (optional): asks Claude (`claude-haiku-4-5`) to classify
   each remaining company and keeps only true LOCAL independent businesses —
   dropping chains, suppliers/dealers, and unrelated results the keyword list
   missed. One call per company, ~0.5s apart; failures keep the row. Removed
   companies are listed in the summary.

It asks for the CSV path, then an optional **fallback city** (used only for the
few rows where GPS can't be matched, e.g. a metro not in the city table).

Output columns: `domain, googleMapsUrl, firstName, companyName, city, reviewCount`

**Handles the real Instant Data Scraper export**, which uses Google's
obfuscated CSS-class headers (`qBF1Pd`, `lcr4fd href`, …). Columns are detected
by **content**, not header text, so it keeps working when Google changes those
class names. It also discards the Material-icon glyph characters the scraper
captures for "no website" rows, Google ad-redirect links, and shared-platform
domains (facebook.com, vagaro.com, booksy.com, …) that Hunter can't resolve to
an email.
The summary prints which column it chose for each field — check it.

## Part B — `python part_b.py`
Turns an email-finder export (**Anymail Finder** or Hunter) into the Instantly
upload file.

1. Keeps only valid, personal emails (drops invalid ones + role inboxes like
   info@/sales@/support@).
2. Uses the **real decision-maker first name** from the finder
   (`person_first_name`) when present; else the Part A name; else `there`.
3. De-duplicates emails.

It asks for the export path. **Anymail Finder exports are self-contained**
(they carry company/city/reviews/domain), so that's the only file needed. If
you give it a bare Hunter list with just emails, it also asks for the Part A
output and merges by domain.

Output columns (Instantly order):
`firstName, email, companyName, city, reviewCount, website, googleMapsUrl`

## AI verification setup (one-time)
1. Install the SDK: `python3 -m pip install anthropic`
2. Create a file named `.env` (in this folder or any parent) containing:
   `ANTHROPIC_API_KEY=sk-ant-...`
3. That's it — Part A picks it up automatically. To turn the step off, set
   `AI_VERIFY = False` at the top of `part_a.py`.

## Tuning knobs (top of `part_a.py`)
- `MIN_REVIEWS` / `MAX_REVIEWS` — review floor (default 25) and optional ceiling.
  `MAX_REVIEWS = None` (default) keeps all high-review independents; set it to a
  number (e.g. `1000`) only if you want to drop very large listings.
- `AI_VERIFY` / `AI_MODEL` / `AI_DELAY_SECONDS` — toggle the AI step, change the
  model, or change the delay between calls.
- `CONSERVATIVE` — name strictness. `True` (default) only personalizes when
  highly confident (possessive "Jay's", "by Steve", "Smith & Sons"); everything
  else becomes `there`. Set `False` to also use the first word
  ("Vargas Med Spa" -> Vargas) for more names but some brand/place false hits.
- `CHAINS` — national chains to exclude.
- `SERVICE_WORDS`, `BRAND_WORDS`, `PLACE_WORDS` — words that are **not** owner
  names. If you see junk first names in the output (e.g. a city or a brand
  word), add them here.
- `PLATFORM_DOMAINS` — social/SaaS hosts treated as "no usable website".
- `CITY_COORDS` / `CITY_MAX_KM` — offline city lookup for GPS-based city
  tagging. Add `"City Name": (lat, lon)` rows for any new area you scrape; a
  business is tagged with the nearest city within `CITY_MAX_KM` (default 30).

`part_b.py`: `ROLE_WORDS` — generic mailbox names to drop.

## Test fixtures
`sample_maps.csv` and `sample_hunter.csv` are tiny friendly-header examples you
can run the scripts against to see the format.
