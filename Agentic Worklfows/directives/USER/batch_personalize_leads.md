# Batch Personalize Leads

**Purpose:** Generate personalizations for enriched leads using cost-optimized AI
**When to use:** After leads have been enriched with research data
**Cost:** ~$25 per 1,000 leads on Claude Opus 5.5 (rough estimate, not measured)

> **Model change, 2026-09-25:** every model call runs on Claude Opus 5.5 (`claude-opus-5-5`, low effort). The engine key `haiku` (`PERSONALIZATION_ENGINE=haiku`, `engine_used='haiku'`, `haiku_success`) and the file name `operational_fact_pain_generator_haiku.py` are kept so nothing breaks, but they now mean Claude Opus 5.5. The code pins the model and no longer reads `ANTHROPIC_MODEL`. Claude is now the more expensive engine: the Haiku-era cost tables and test logs further down are historical and no longer hold.

---

## What This Does

Takes enriched leads from your CRM and generates personalized email opening lines using:
1. **Primary engine:** Claude Opus 5.5, engine key `haiku` (~$0.025/lead, rough estimate)
2. **Fallback engine:** GPT-4o (~$0.002/lead)
3. **Ultimate fallback:** Template-based (free, always works)

The system intelligently routes to the most cost-effective option while maintaining quality.

---

## Prerequisites

✅ Leads must be enriched with research data (see [enrich_and_personalize_leads.md](./enrich_and_personalize_leads.md))
✅ `Data Summary` column populated with website/GBP/LinkedIn research
✅ API keys configured in `.env`:
   - `ANTHROPIC_API_KEY` (required for the Claude engine, Opus 5.5)
   - `OPENAI_API_KEY` (optional, for GPT-4o fallback)

---

## Required Tools

- `execution/unified_personalization_engine.py` - Intelligent routing between AI engines
- `execution/operational_fact_pain_generator_haiku.py` - Claude generator (Opus 5.5; file name is historical)
- `execution/operational_fact_pain_generator.py` - GPT-4o fallback
- `execution/google_sheets_client.py` - CRM operations

---

## Input Format

### Option 1: Process Specific Count
```
"Personalize 100 HVAC leads"
```

### Option 2: Process Entire Sheet
```
"Personalize all roofing leads without personalizations"
```

### Option 3: Test Mode
```
"Test personalize 10 leads"
```

---

## Cost Breakdown

### Per 1,000 Leads:

| Engine Strategy | Cost | Success Rate | Savings vs GPT-4o |
|----------------|------|--------------|-------------------|
| GPT-4o only | $2.00 | 95% | baseline |
| Haiku only | $0.20 | 95% | 90% |
| **Haiku + GPT-4o fallback** | **$0.22** | **~99%** | **89%** |

**Recommended:** Haiku + GPT-4o fallback (best quality-to-cost ratio)

### Cost Calculator:
- **100 leads:** ~$0.02
- **500 leads:** ~$0.11
- **1,000 leads:** ~$0.22
- **5,000 leads:** ~$1.10
- **10,000 leads:** ~$2.20

Compare to GPT-4o only:
- 1,000 leads: $2.00 (vs $0.22 = **$1.78 savings**)
- 10,000 leads: $20.00 (vs $2.20 = **$17.80 savings**)

---

## Configuration Options

Set in `.env`:

```bash
# Engine selection (choose one):
PERSONALIZATION_ENGINE=both      # Claude (Opus 5.5) first, GPT-4o fallback
PERSONALIZATION_ENGINE=haiku     # Claude only (key name kept; runs Opus 5.5)
PERSONALIZATION_ENGINE=gpt4o     # GPT-4o only

# Model versions:
# Claude: claude-opus-5-5, pinned in operational_fact_pain_generator_haiku.py
# (ANTHROPIC_MODEL is no longer read)
OPENAI_MODEL=gpt-4o
```

---

## Output Format

Each lead gets a personalization added to the `Personalization` column (or creates it if missing).

### Example Outputs:

**HVAC Lead (Tier 1 - Strong):**
```
Noticed {{companyName}} runs a 24/7 emergency line for AC repair across the Houston metro.
That probably means service requests are coming in around the clock, not just during business hours.
```

**Roofing Lead (Tier 2 - Medium):**
```
Noticed {{companyName}} covers most of the greater Houston area with a heavy focus on storm restoration.
I'd imagine that brings in a good amount of estimate requests, especially during peak season.
```

**Limited Data (Tier 3 - Fallback):**
```
Noticed {{companyName}} serves the greater Denver area for roofing.
I'd imagine you're getting a good amount of estimate requests, especially during peak season.
```

---

## Process Flow

```
1. Load leads from CRM (HVAC Leads or Roofing Leads sheet)
2. Filter to leads with:
   - Company Name populated
   - Data Summary populated (research data)
   - Personalization column empty or missing
3. For each lead:
   a. Extract research data from Data Summary
   b. Try Haiku personalization generation
   c. If Haiku fails → try GPT-4o
   d. If GPT-4o fails → use template fallback
   e. Write personalization to sheet
   f. Track cost and engine used
4. Report summary:
   - Total leads processed
   - Success breakdown by engine
   - Total cost
   - Cost per lead
   - Quality validation stats
```

---

## Quality Validation

Each personalization is automatically validated for:

✅ Starts with approved opener ("Noticed", "Saw that", "Looks like")
✅ Contains `{{companyName}}` variable
✅ No compliments or admiration language
✅ No bridge phrases ("figured I'd reach out")
✅ No identity labels ("family-owned", etc.)
✅ No franchise/corporate stats
✅ Connects to volume/pain naturally

Failed validations trigger re-generation or fallback.

---

## Rate Limits & Throttling

- **Haiku:** 50 requests/minute (10x faster than needed)
- **GPT-4o:** 30 requests/minute (fallback only)
- **Processing speed:** ~2 leads/second
- **100 leads:** ~1 minute
- **1,000 leads:** ~10 minutes

The system automatically throttles to stay under limits.

---

## Error Handling

### Haiku API Error
- Automatically falls back to GPT-4o
- Logs error for monitoring
- No interruption to batch

### GPT-4o API Error
- Falls back to template personalization
- Logs for manual review
- Continues processing

### Rate Limited
- Pauses for 60 seconds
- Resumes from last successful lead
- No data loss

### Invalid Research Data
- Uses template fallback
- Marks lead for manual enrichment
- Continues batch

---

## Testing Before Full Batch

Always test on 10 leads first:

```bash
# Test quality comparison
python execution/test_personalization_quality.py --count 10

# This will:
# 1. Pull 10 random leads from CRM
# 2. Generate with both Haiku and GPT-4o
# 3. Show side-by-side comparison
# 4. Display cost and latency stats
```

Review the output quality before processing thousands of leads.

---

## Example Usage

### Test 10 Leads (Quality Check)
```
User: "Test personalize 10 HVAC leads"

System:
✅ Found 10 leads with research data
✅ Testing with Haiku + GPT-4o comparison

Results:
┌─────────────────┬─────────┬────────────┬──────────────┐
│ Engine          │ Success │ Total Cost │ Avg Latency  │
├─────────────────┼─────────┼────────────┼──────────────┤
│ haiku           │ 10/10   │ $0.0020    │ 1.2s         │
│ gpt4o           │ 10/10   │ $0.0200    │ 2.8s         │
└─────────────────┴─────────┴────────────┴──────────────┘

💰 Cost Savings: 90% (haiku vs gpt4o)
   For 1,000 leads: $0.20 vs $2.00

[Shows 3 side-by-side examples]

✓ Quality verified! Ready to process full batch.
```

### Process 500 HVAC Leads
```
User: "Personalize 500 HVAC leads"

System:
✅ Found 1,247 HVAC leads with research data
✅ Processing batch of 500...

Progress:
[##########----------] 250/500 complete
- Haiku success: 238
- GPT-4o fallback: 11
- Template fallback: 1
- Total cost: $0.055

✅ Batch complete!
- Processed: 500 leads
- Success rate: 99.8%
- Total cost: $0.11
- Cost per lead: $0.00022
- Savings vs GPT-4o: $1.89 (89%)

Engine breakdown:
  Haiku: 475 (95%)
  GPT-4o: 24 (4.8%)
  Template: 1 (0.2%)

Next: Review sample outputs or process more leads.
```

---

## Post-Processing Checks

After batch completion:

1. **Spot check 10-20 personalizations** for quality
2. **Verify cost** matches estimate
3. **Check for any template fallbacks** (indicates poor research data)
4. **Validate {{companyName}} variable** is present in all outputs
5. **Ensure no compliments** slipped through validation

If quality issues detected, regenerate with `engine=gpt4o`.

---

## Learnings & Updates

### 2025-04-09: Initial System
- Haiku 3.5 matches GPT-4o quality on structured prompts
- 90% cost savings verified across 100+ test leads
- Fallback chain prevents batch failures
- Average latency: Haiku 1.2s vs GPT-4o 2.8s

---

## Troubleshooting

### "Haiku generator not available"
- Check `ANTHROPIC_API_KEY` in `.env`
- Verify `pip install anthropic` completed
- System will fall back to GPT-4o automatically

### "All engines failed"
- Check both API keys are valid
- Verify internet connectivity
- Review error logs in console
- System uses template fallback

### Personalizations look generic
- Research data may be thin
- Check `Data Summary` column has substantial content
- Consider re-enriching leads with more sources
- Template fallbacks indicate enrichment gaps

### High GPT-4o fallback rate (>10%)
- Haiku API may be experiencing issues
- Check Anthropic status page
- Temporarily switch to `PERSONALIZATION_ENGINE=gpt4o`
- Report pattern to system owner

---

## Cost Monitoring

Track actual costs vs estimates:

```bash
# Show cost comparison
python execution/unified_personalization_engine.py --cost-comparison 1000

# Shows breakdown for 1,000 leads:
# - GPT-4o only: $2.00
# - Haiku only: $0.20
# - Haiku + fallback: $0.22
```

Monitor API usage:
- **Anthropic:** https://console.anthropic.com/settings/usage
- **OpenAI:** https://platform.openai.com/usage

---

## Best Practices

1. **Always test on 10-20 leads first** before processing thousands
2. **Use `engine=both`** for best quality-to-cost ratio
3. **Monitor fallback rates** - >10% GPT-4o suggests Haiku issues
4. **Validate outputs** with spot checks after each batch
5. **Track costs** to verify savings match estimates
6. **Re-enrich leads** if seeing high template fallback rates

---

**Ready to personalize? Test 10 leads first, then scale to your full batch.**
