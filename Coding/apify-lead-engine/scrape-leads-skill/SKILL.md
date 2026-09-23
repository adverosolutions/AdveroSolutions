---
name: scrape-leads
description: Scrape B2B leads from Apify's leads-finder actor. Given a natural-language query like "dentists in Canada" or "VPs of Engineering at SaaS companies in Germany", generate filter criteria, run the scrape, and save results to local JSON + CSV. Use when the user asks to find leads, build a prospect list, or pull contacts for outreach.
allowed-tools: Read, Grep, Write, Edit, Bash
---

# Scrape Leads

Turn a natural-language query into a B2B lead list using the Apify `code_crafter/leads-finder` actor. Saves results to a local folder as JSON + CSV. No Google Sheets / LLM classification / email enrichment — just a clean, self-contained scrape.

## First-run setup (ALWAYS do this before anything else)

Before parsing any query, check for credentials:

1. Look for a `.env` file in the same directory as this `SKILL.md`.
2. If it doesn't exist, or it exists but `APIFY_API_TOKEN` is missing/empty, **stop and ask the user**:

   > "I need your Apify API token to run this scraper. You can find it at https://console.apify.com/settings/integrations (free account works — the leads-finder actor is pay-per-event, ~$0.002/lead). Paste it here and I'll save it locally."

3. Once the user provides the token, write it to `.env` in this skill's directory:
   ```
   APIFY_API_TOKEN=apify_api_xxxxxxxxxxxxxxxxxxxx
   ```
4. Confirm: "Saved. Running your scrape now…" and proceed.

Never log the token, never commit it, never echo it back.

## Pipeline

1. **Parse the query.** Extract intent across these dimensions:
   - *who* — job title, seniority, function
   - *where* — country, state, city
   - *what kind of company* — industry, keywords, company size, revenue, funding stage
   - *quality* — email validation status
   - *how many* — `fetch_count` (default 100 for a smoke test; ask before going higher)

2. **Map to schema enums.** The Apify actor is strict about allowed values. Read [input_schema.json](input_schema.json) and grep for exact enum strings before writing the filter JSON. Key rules:

   - **`contact_location`** — 1857 lowercased enum values, all **countries or administrative regions — never cities**. Countries are bare (`"canada"`, `"germany"`, `"united states"`; 203 of these). Regions are `"{region}, {country}"`: US states use the `us` suffix and there are exactly 56 (`"california, us"`, `"texas, us"`), plus provinces/oblasts (`"ontario, canada"`). A city appears here *only* when the city is itself a region — `"berlin, germany"` resolves, `"london, united kingdom"` does not. **Always grep** before guessing:
     ```bash
     grep -i "texas" input_schema.json
     ```
   - **`contact_city`** — use this for cities (`"houston"`, `"miami"`, `"chicago"`). It is **free text with no enum**, so a misspelled city fails silently and returns an empty or wrong result set rather than an error. Verify the lead count looks sane after any city-filtered run.
   - **`fetch_count`** — **always set it explicitly.** The actor's own default is `100000` (~$200). `scrape.py` refuses to run without it and caps it at 5000, but never hand-write a payload that omits it.
   - **`company_industry`** — 148 lowercased strings (`"hospital & health care"`, `"computer software"`, `"law practice"`, `"construction"`, …). Grep before guessing.
   - **`seniority_level`**: `founder`, `owner`, `c_suite`, `director`, `partner`, `vp`, `head`, `manager`, `senior`, `entry`, `trainee`
   - **`functional_level`**: `c_suite`, `finance`, `product_management`, `engineering`, `design`, `education`, `human_resources`, `information_technology`, `legal`, `marketing`, `operations`, `sales`, `support`
   - **`size`** (employee headcount bands): `1-10`, `11-20`, `21-50`, `51-100`, `101-200`, `201-500`, `501-1000`, `1001-2000`, `2001-5000`, `5001-10000`, `10001-20000`, `20001-50000`, `50000+`
   - **`email_status`**: `validated`, `not_validated`, `unknown` — default to `["validated"]` for outreach quality.
   - **`funding`**: `seed`, `angel`, `series_a` … `series_f`, `venture_round`, `debt_financing`, `convertible_note`, `private_equity_round`, `other_round`
   - **`contact_job_title`** and **`company_keywords`** are free-text arrays — use them for concepts that don't fit an enum (e.g. `"dentist"` as a job title rather than hunting for a "dentistry" industry, or `"hvac"` as a keyword since HVAC isn't in the industry list).

3. **Choose filter granularity — start narrow, not broad.**
   - `"dentists in canada"` → `contact_job_title=["dentist"]`, `contact_location=["canada"]`, `email_status=["validated"]`, `fetch_count=100`.
   - `"owners of HVAC companies in Texas"` → `seniority_level=["owner", "founder"]`, `company_keywords=["hvac"]`, `contact_location=["texas, us"]`, `email_status=["validated"]`.
   - `"VPs of Engineering at SaaS companies in Germany"` → `seniority_level=["vp"]`, `functional_level=["engineering"]`, `contact_location=["germany"]`, `company_industry=["computer software"]`, `email_status=["validated"]`.
   - Only include fields the query explicitly implies. Omit unused keys entirely — don't send `null` or empty arrays. **The one exception is `fetch_count`, which must always be present.**

4. **Write the filter JSON** to `inputs/{slug}_{timestamp}.json` inside this skill's directory. Always set a descriptive `file_name` field — it becomes both the Apify run label and the output filename.

5. **Run the scrape:**
   ```bash
   python3 scrape.py inputs/{slug}_{timestamp}.json
   ```
   Output lands in `output/{label}_{timestamp}.json` and `output/{label}_{timestamp}.csv`.

6. **Report back:** total leads returned, email fill rate, output paths. If the result count looks off (0 leads, or maxed out at the requested count implying more are available), flag it so the user can adjust.

7. **After the first successful run**, ask:

   > "Scrape complete. Would you like to install this as a permanent Claude Code skill? That moves this folder to `~/.claude/skills/scrape-leads/` so you can run it from any project just by asking me to 'scrape leads for X'."

   If yes: `mkdir -p ~/.claude/skills && cp -r "$(dirname SKILL.md)" ~/.claude/skills/scrape-leads` (use the correct absolute path to this skill's directory). Preserve the `.env` and any existing `output/` so the user keeps their results.

   If no: leave everything where it is.

   Skip this prompt on subsequent runs (you can tell it's already installed if this `SKILL.md` lives inside `~/.claude/skills/scrape-leads/`).

## Defaults & guardrails

- **Default `fetch_count=100`** for a new query. Smoke test first, scale after the user confirms.
- **Default `email_status=["validated"]`** — unverified emails waste outreach budget.
- **Cost**: $0.02 actor start + ~$0.002/lead. 100 leads ≈ $0.22, 1000 ≈ $2.02, 5000 ≈ $10.02. Mention cost before any scrape over 1000.
- **Endpoint**: `run-sync-get-dataset-items` — it blocks until the run finishes and returns items inline. No polling / run-id tracking needed.
- **Never commit `.env`** — a `.gitignore` in this folder already excludes it.

## Example filter payload

```json
{
  "file_name": "dentists_canada_smoke",
  "fetch_count": 100,
  "contact_job_title": ["dentist"],
  "contact_location": ["canada"],
  "email_status": ["validated"]
}
```

## Files in this skill

- [SKILL.md](SKILL.md) — this file
- [scrape.py](scrape.py) — stdlib-only script that POSTs the filter JSON to Apify and saves results to JSON + CSV
- [input_schema.json](input_schema.json) — full Apify input schema (all enum values). Always grep this before picking enum strings.
- [README.md](README.md) — human-readable install / quick-start guide
- [.env.example](.env.example) — template for your Apify API token
- `.env` — your actual token (created on first run, gitignored)
- `inputs/` — filter JSONs you've run (auto-created)
- `output/` — scrape results as JSON + CSV (auto-created)
