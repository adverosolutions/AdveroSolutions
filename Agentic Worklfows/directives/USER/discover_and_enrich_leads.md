# Discover & Enrich Leads (Free Email Pipeline)

**Purpose:** Replace AnyMail Finder with a self-hosted enrichment pipeline that finds owner identity + verified email at ~1/3 the cost.

**When to use:** After scraping contractor businesses (Google Maps, state registries, etc.), before kicking off a cold email campaign.

**Cost target:** ~$0.013/attempted lead, ~$0.018/successful lead at scale.

---

## Pipeline Stages (Cost-Gated)

The pipeline is ordered cheapest-to-most-expensive so we never spend money on dead-end leads.

```
[FREE GATES]
1. Source row already in completed/failed sheet?         → SKIP
2. Within-source duplicate email?                        → SKIP
3. Missing company name / city / state?                  → SKIP
4. Not electrician/plumber category?                     → SKIP
5. No website AND no domain extractable?                 → SKIP
6. Domain has no MX records?                             → SKIP (dead domain)
7. Website unreachable / 404s?                           → continue but skip scrape

[FREE — website scraping]
8. scrape_website_emails.py
   → Returns scraped emails with match-quality hints (HIGH/MEDIUM/LOW/GENERIC)

[FIRST PAID CALL — ~$0.005]
9. discover_owner.py
   → Combined owner discovery + research via Perplexity (single call)
   → If returns None (UNKNOWN owner) → SKIP, no further spend

[CHEAP — ~$0.0006-0.003 per lead]
10. generate_email_patterns.py + verify_emails_bulk.py
    → Generate top 3-5 owner-name patterns from discover_owner output
    → Bulk verify via MillionVerifier
    → Returns deliverability + catch-all flags per email

[FREE — rule-based]
11. tag_email_confidence.py
    → Picks best email + confidence tier from scraping + verification outputs
    → If confidence == REJECT, save to Failed tab and stop

[CHEAP — ~$0.0002 per lead]
12. icebreaker_generator.py (existing)
    → Uses owner research from step 9 to generate personalized icebreaker

[SAVE]
13. Write to completed sheet with confidence tag in dataProcessorSummary
```

---

## Required Tools

- `execution/discover_owner.py` — Combined owner + research via Perplexity
- `execution/scrape_website_emails.py` — Website email scraper
- `execution/generate_email_patterns.py` — Owner-pattern email generation
- `execution/verify_emails_bulk.py` — MillionVerifier API wrapper
- `execution/tag_email_confidence.py` — Confidence-tier rules
- `execution/icebreaker_generator.py` — Existing icebreaker (Claude Opus 5.5 since 2026-09-25)
- `execution/google_sheets_crm.py` — Existing sheet writes

## Required API Keys (.env)

- `PERPLEXITY_API_KEY` — already set
- `ANTHROPIC_API_KEY` — already set
- `MILLIONVERIFIER_API_KEY` — **NEW**, sign up at millionverifier.com (~$30/mo Hobby plan = 50k verifications/year)

---

## Confidence Tiers (Output)

| Tier | Source | When to send |
|------|--------|--------------|
| HIGH | Scraped match owner name OR pattern verified + non-catch-all | Always — primary outreach |
| MEDIUM | Catch-all domain OR partial name match | Send, monitor bounce rate |
| LOW | Generic mailbox (info@, contact@) | Optional secondary sequence |
| REJECT | No deliverable email | Skip, log to Failed tab |

---

## Cost Math

For a 4-email sequence × 7-day cadence at 2k sends/day:
- Steady-state: ~500 new leads/day = ~11–15k/month

**Per-lead breakdown:**
- Owner discovery + research (combined Perplexity): ~$0.005
- Email verification (~3 patterns avg): ~$0.002
- Icebreaker (Claude Opus 5.5 since 2026-09-25, was Haiku at ~$0.0002): ~$0.01, rough estimate
- **Total successful: ~$0.018/lead** (Haiku-era figure; add ~$0.01 for the Opus 5.5 icebreaker, and the same to the full-success rows below)

**Per-lead with gates:**
- ~15% killed at free gates: $0
- ~10% UNKNOWN owner: $0.005
- ~15% no verifiable email: $0.007
- ~60% full success: $0.018
- **Average: ~$0.013/attempted lead**

**Monthly at 12k attempted leads/mo:** ~$160/mo + $30/mo MillionVerifier = **~$190/mo**

vs old AnyMail+Perplexity setup at $500–600/mo → savings ~$300–400/mo.

---

## Edge Cases & Gotchas

### Catch-all domains
MillionVerifier flags domains that accept any email. Pattern-generated emails on catch-all domains return "valid" but might silently bounce. Treat as MEDIUM confidence and watch your bounce rate.

### Role-based emails
`info@`, `sales@`, `contact@` get to *someone* but not specifically the owner. The icebreaker still works (it's about the owner's story, not who's reading) but personal patterns are preferred.

### Owner name typos in source
Perplexity sometimes "corrects" company name typos to a different real company (e.g., "Scanlin Electrtc Ine" → researches "Scanlan Electric"). The hallucination guard in `icebreaker_generator.py` catches this.

### Sites that block scrapers
Some contractor sites use Cloudflare or similar bot blocking. The scraper will return empty; pipeline falls through to pattern + verify.

### Free email providers
If verification flags `is_free=True` (gmail/yahoo/etc), this is suspicious for a business owner — likely a personal email or wrong target. Tag as LOW.

---

## Self-Annealing Notes

*Add learnings here as the pipeline runs.*

- [Add notes after first 100-lead test run]
