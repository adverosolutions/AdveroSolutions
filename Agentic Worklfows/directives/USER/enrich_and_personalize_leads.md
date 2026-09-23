# Enrich and Personalize Leads

**Purpose:** Research leads via Perplexity, create detailed reports, and generate personalized email icebreakers
**When to use:** After leads have been scraped and emails found via AnyMailFinder
**Frequency:** As needed for batches of unprocessed leads

---

## What This Does

1. Pulls unprocessed leads from the incomplete leads sheet
2. Researches decision maker (owner/CEO) via Perplexity
3. Researches company details via Perplexity
4. Compiles findings into structured report (`dataProcessorSummary`)
5. Generates personalized one-liner icebreaker (`emailIceBreaker`)
6. Saves completed lead to the "Ready To Outreach" sheet

---

## Required Tools

- `execution/perplexity_research.py` - Perplexity API for research
- `execution/lead_enrichment_pipeline_v2.py` - Main orchestrator (email-based dedup, failed lead tracking, phone formatting)
- `execution/icebreaker_generator.py` - Claude Haiku icebreaker generation
- `execution/google_sheets_crm.py` - Sheet operations

---

## Input Format

### Option 1: Process by State
```
"Enrich 100 leads from California"
```

### Option 2: Process Specific Count
```
"Enrich 200 leads starting with Mississippi"
```

### Option 3: Test Mode
```
"Test enrich 5 leads from Texas"
```

---

## Research Requirements

### Decision Maker Research (Priority)
Find and document:
- **Name and Title** - Full name, current role
- **Career Journey** - Previous roles, companies, progression
- **Tenure** - How long in current role/company
- **Education** - Degrees, certifications (NATE, etc.)
- **Personal Mission/Values** - Quotes, stated priorities
- **Achievements** - Revenue growth, awards, milestones
- **Community Involvement** - Charity, local orgs, church
- **Unique Path** - Career transitions, entrepreneurial story

### Company Research (Backup)
If decision maker info is limited, gather:
- **Founded** - Year established
- **Structure** - Family-owned, franchise, LLC, etc.
- **Employee Count** - Size of team
- **Locations** - Service areas, multiple branches
- **Certifications/Awards** - BBB rating, manufacturer certifications
- **Unique Attributes** - Specialties, guarantees, notable programs
- **Recent Activity** - Expansions, news, achievements

---

## Icebreaker Generation Rules

### NEVER Start With
- "Your" (e.g., "Your commitment to...")
- "I noticed that..."
- "I saw that..."
- Generic compliments

### ALWAYS Start With
- Action verbs: Running, Building, Leading, Transforming, Spending
- Time phrases: "25 years...", "Six years...", "42 years..."
- Specific achievements: "Transforming revenues by 300%..."

### Structure Formula
```
[Specific achievement/fact] + [why it resonates/stands out] + "figured I'd reach out."
```

### Resonance Phrases (rotate)
- "speaks to serious [pride/commitment/grit/dedication]"
- "really resonated with me"
- "stood out to me"
- "something I really respect"
- "I share that [philosophy/drive/value]"
- "rare to see that kind of [consistency/dedication]"
- "says a lot about [your standards/your values]"

### Ending
Always end with: "figured I'd reach out." (lowercase f, period at end)

### Hook Categories (prioritize in order)
1. **Longevity** - Years in business, years in role
2. **Career Transition** - Corporate to entrepreneur, different industry to HVAC
3. **Growth/Scale** - Revenue increases, expansion, team growth
4. **Values** - Family-owned, community focus, quality-first
5. **Certifications** - BBB A+, NATE certified, elite dealer status
6. **Hands-on Leadership** - Still doing installs, project management

---

## Example Icebreakers (Reference)

**Longevity Hook:**
```
25 years building a trusted HVAC brand in Houston with 24/7 service and a satisfaction guarantee speaks to serious pride in the craft—figured I'd reach out.
```

**Career Transition Hook:**
```
Your leap from Schlumberger engineering to HVAC entrepreneurship shows serious drive and vision—especially blending airflow science with real-world delivery. That stood out to me, so I figured I'd reach out.
```

**Growth Hook:**
```
Transforming Reliant Energy's revenues by 300% showcases impressive leadership and vision, which really resonated with me—figured I'd reach out.
```

**Values Hook:**
```
Leaving the big firms to start a family-run HVAC shop shows your commitment to quality and trust—values I really respect, so I figured I'd reach out.
```

**Certification Hook:**
```
Being BBB A+ rated just a year after launching in 2019 says a lot about your standards—especially in a competitive Houston HVAC market. Impressive growth, figured I'd reach out.
```

---

## Output Format

### dataProcessorSummary Structure
```markdown
### Decision Maker Personal Details: [Name]
- **Current Role**: [Title] at [Company] since [Year]
- **Career Journey**: [Previous roles, progression]
- **Education**: [Degrees, certifications]
- **Personal Mission/Values**: [Quotes, stated priorities]
- **Achievements**: [Notable accomplishments]
- **Community Involvement**: [Charity, local involvement]
- **Unique Path**: [What makes their story stand out]

### Company Details (Backup)
- **Founded**: [Year]
- **Structure**: [Family-owned, LLC, franchise, etc.]
- **Employee Count**: [Number]
- **Service Area**: [Geographic coverage]
- **Certifications/Awards**: [BBB, manufacturer partnerships]
- **Unique Attributes**: [Specialties, guarantees]
```

### emailIceBreaker
Single sentence, 20-40 words, following the formula above.

---

## Process Flow

```
1. Load unprocessed leads from incomplete sheet
2. For each lead:
   a. Search Perplexity: "[FirstName] [LastName] [CompanyName] [City] owner"
   b. Search Perplexity: "[CompanyName] [City] [Industry] company history"
   c. Parse results into structured report
   d. Generate icebreaker based on best available hook
   e. Save to completed sheet
   f. Log progress
3. Report summary when batch complete
```

---

## Rate Limits & Costs

- **Perplexity API**: ~$0.005 per search (2 searches per lead = $0.01/lead)
- **Batch of 100 leads**: ~$1.00
- **Batch of 200 leads**: ~$2.00
- **Recommended pace**: 1 lead every 2-3 seconds to avoid rate limits

---

## Error Handling

### No Decision Maker Info Found
- Fall back to company-focused icebreaker
- Use company founding year, BBB rating, or service area

### Rate Limited
- Pause for 60 seconds
- Resume from last successful lead
- Log which leads need retry

### Invalid/Missing Email
- Skip lead
- Log for manual review
- Don't move to completed sheet

---

## Edge Cases

### Multiple Decision Makers
- Prioritize: Owner > CEO > President > VP
- Use the one with most available information

### Very New Company (< 2 years)
- Focus on founder's background/previous experience
- Mention the entrepreneurial leap

### Franchise Location
- Research local owner if possible
- Fall back to local market positioning

### No Usable Information Found
- Mark as "NEEDS_MANUAL_REVIEW"
- Do not generate generic icebreaker
- Skip and continue to next lead

---

## Success Metrics

- **Research Success Rate**: > 85% of leads get usable info
- **Icebreaker Quality**: No generic/templated outputs
- **Processing Speed**: 100 leads in ~15-20 minutes
- **Cost per Lead**: ~$0.01

---

## Example Usage

### Process 100 California Leads
```
User: "Enrich 100 leads from California"

System:
✅ Found 1,638 unprocessed California leads
✅ Processing batch of 100...

Progress:
[##########----------] 50/100 complete
- Researched: 50
- Successful: 47
- Needs manual review: 3

✅ Batch complete!
- Added to Ready To Outreach: 47 leads
- Flagged for review: 3 leads
- Cost: ~$1.00

Next: Run again to process more, or switch to another state.
```

---

## Learnings & Updates

*This section updated as system learns from errors*

- [Add learnings here as discovered]

---

**Ready to enrich leads? Tell me which state and how many to process.**
