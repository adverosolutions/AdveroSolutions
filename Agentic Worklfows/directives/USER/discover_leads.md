# Discover New Leads

**Purpose:** Find new HVAC and Roofing businesses and add them to the pipeline
**Cost:** $0 for discovery + ~$0.015 per email found
**Frequency:** Run daily or as needed

---

## What This Does

The Lead Discovery Pipeline:
1. Searches Yelp API for businesses in target locations (free, 5,000/day)
2. Optionally scrapes Google Maps for additional coverage (free, unlimited)
3. Deduplicates against existing CRM data
4. Finds decision maker emails via Anymail Finder
5. Saves to Discovery Staging sheet
6. Ready for enrichment pipeline

---

## Usage

### Quick Discovery (Single City)
```
"Discover HVAC leads in Houston, TX"
"Find 100 roofing businesses in Dallas"
```

### Multi-City Discovery
```
"Run discovery for HVAC in Houston, Dallas, and Austin - 100 per city"
"Discover roofing leads in all top 5 Texas cities"
```

### Full Pipeline
```
"Run full discovery for HVAC and Roofing in Texas"
```

---

## CLI Usage

```bash
# Test mode (10 leads, no emails, no save)
python execution/lead_discovery_pipeline.py --test

# Full run for specific cities
python execution/lead_discovery_pipeline.py --industries HVAC Roofing --locations "Houston, TX" "Dallas, TX" --max-per-location 100

# Without email enrichment
python execution/lead_discovery_pipeline.py --no-emails

# Check available API capacity
python execution/multi_source_discovery.py
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| Industries | HVAC, Roofing | Industries to discover |
| Locations | Top 5 TX cities | Target cities |
| Max per location | 100 | Businesses per city |
| Find emails | Yes | Run Anymail Finder enrichment |
| Save to sheets | Yes | Save to Discovery Staging |

---

## Data Sources

### Priority 1: Yelp API (Primary)
- **Limit:** 5,000 calls/day (free)
- **Data:** Name, phone, address, rating, reviews
- **Speed:** Fast (API)

### Priority 2: Google Maps Scraper (Backup)
- **Limit:** Unlimited (local)
- **Data:** Name, phone, address, rating, reviews
- **Speed:** Slower (~5 sec/business)

---

## Output

Leads are saved to the **Discovery Staging** sheet with tabs:
- `HVAC Pending`
- `Roofing Pending`
- `Discovery Log`

### Schema
| Field | Description |
|-------|-------------|
| company_name | Business name |
| address | Full address |
| city | City |
| state | State |
| phone | Phone number |
| website | Website URL |
| email | Decision maker email |
| decision_maker_name | Owner/CEO name |
| google_rating | Rating (1-5) |
| review_count | Number of reviews |
| source | yelp or google_maps |
| status | pending |

---

## Cost Breakdown

| Component | Cost |
|-----------|------|
| Discovery (Yelp/Scraper) | $0 |
| Email finding (Anymail) | ~$0.015/lead |
| **Total per lead** | ~$0.015 |

**Example:** 500 leads = ~$7.50

---

## Next Steps

After discovery:
1. Review leads in Discovery Staging sheet
2. Run `enrich_and_personalize_leads.md` for Perplexity research
3. Run `start_cold_campaign.md` to begin outreach

---

## Troubleshooting

### "Yelp API key not found"
Add `YELP_API_KEY` to your `.env` file. Get one at: https://www.yelp.com/developers/v3/manage_app

### "Anymail Finder API key not found"
Add `ANYMAIL_FINDER_API_KEY` to your `.env` file.

### "No businesses found"
- Check if the location is correct (format: "City, ST")
- Try a different search term
- Check Yelp API usage limits

### "Playwright not installed"
Run: `pip install playwright && playwright install chromium`
