# scrape-leads

A Claude Code skill that turns natural-language queries like *"dentists in Canada"* or *"VPs of Engineering at SaaS companies in Germany"* into B2B lead lists. Powered by the Apify [`code_crafter/leads-finder`](https://apify.com/code_crafter/leads-finder) actor.

Saves results as both JSON and CSV — ready to import into your CRM, cold outreach tool, or spreadsheet.

## What you get

- **Natural-language → filters** — just ask in plain English, the skill handles the filter mapping
- **Validated emails only** — defaults to `email_status=["validated"]` so you don't burn contact slots on junk
- **Smoke-test first** — defaults to 100 leads so you can verify quality before scaling up
- **Pure stdlib** — no `pip install`, runs on any Python 3.8+
- **Local output only** — nothing is uploaded anywhere, results live in `output/` on your machine

## Requirements

1. **Claude Code** installed ([claude.com/claude-code](https://claude.com/claude-code))
2. **Python 3.8+** (ships with macOS/Linux; Windows: [python.org](https://www.python.org/downloads/))
3. **Apify account** + API token ([console.apify.com/settings/integrations](https://console.apify.com/settings/integrations)) — free tier works fine; the leads-finder actor is pay-per-event at ~$0.002 per lead returned

## Install

### Option A: Run once, then decide

1. Download/clone this folder anywhere on your machine
2. Open Claude Code in the folder: `cd scrape-leads-skill && claude`
3. Ask: *"scrape 100 dentists in Canada"*
4. Claude will ask for your Apify API token on the first run, save it to `.env`, run the scrape, then ask if you want to install this as a permanent skill (copies to `~/.claude/skills/scrape-leads/`)

### Option B: Install permanently up front

```bash
mkdir -p ~/.claude/skills
cp -r scrape-leads-skill ~/.claude/skills/scrape-leads
```

Then from any Claude Code session, just say *"scrape 250 HVAC owners in Texas"* and the skill will auto-load.

## Usage examples

```
scrape 100 dentists in Canada
find me 500 marketing directors at SaaS companies in Germany
pull 250 owners of HVAC companies in Texas with validated emails
get contacts for law firms in California, around 20-50 employees, 300 leads
```

The skill will:
1. Parse the query into Apify filter fields (job title, location, industry, size, etc.)
2. POST the filter payload to Apify
3. Save results to `output/{label}_{timestamp}.json` and `.csv`
4. Report lead count and email fill rate

## Cost

The Apify actor is pay-per-event:

| Scrape size | Approx. cost |
|------------:|-------------:|
| 100 leads   | ~$0.22 |
| 500 leads   | ~$1.02 |
| 1,000 leads | ~$2.02 |
| 5,000 leads | ~$10.02 |

Formula: `$0.02 actor start + $0.002 × leads returned` (varies slightly by Apify subscription tier).

## What's in this folder

| File | Purpose |
|------|---------|
| `SKILL.md` | The skill definition Claude reads — contains the full workflow and the filter-mapping reference |
| `scrape.py` | Stdlib Python script that POSTs filter JSON to Apify and saves the results |
| `input_schema.json` | Full Apify actor input schema (all 1857 location enums, 148 industry enums, etc.) for grep-based filter lookup |
| `.env.example` | Template for your Apify API token |
| `.env` | Your actual token (created on first run, gitignored) |
| `.gitignore` | Keeps `.env` and generated `output/` / `inputs/` out of version control |
| `inputs/` | Auto-created on first run — stores filter payloads Claude generated |
| `output/` | Auto-created on first run — stores scrape results (JSON + CSV) |

## Troubleshooting

**"APIFY_API_TOKEN not found"** — Your token isn't set. Either let Claude prompt you for it on the next run, or manually create `.env` from `.env.example`.

**"0 leads returned"** — Your filters are too narrow. Try broadening the job title or removing the industry/size filter. Claude should catch this and suggest refinements.

**"ERROR 401"** — Your Apify token is invalid or expired. Generate a new one at [console.apify.com/settings/integrations](https://console.apify.com/settings/integrations).

**"ERROR 402"** — You're out of Apify credit. Add a payment method or wait for your free tier to reset.

**Results don't match what I asked for** — The `company_keywords` field does a loose match against company descriptions, so niche verticals (like HVAC) may pull in some adjacent businesses. Tighten by using `contact_job_title` directly, or add `company_not_keywords` to exclude noise.

## License

Do whatever you want with it. No warranty. Use responsibly — always comply with CAN-SPAM, GDPR, and local outreach laws.
