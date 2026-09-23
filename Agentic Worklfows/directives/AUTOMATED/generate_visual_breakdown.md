# Generate Visual Breakdown (AUTOMATED)

**Trigger:** Prospect replies "yes" to micro-yes question in cold email sequence
**Frequency:** Per positive reply, on demand
**System:** Automated via Modal webhook

---

## Purpose

Generate a Business Bible compliant **visual breakdown** showing the timeline from first inquiry to booked estimate/appointment. This deliverable matches the exact promise from the cold email sequence:

> "Happy to put together a visual breakdown for {{companyName}} showing what that looks like from first inquiry to [estimate/appointment] booked, without it taking up your team's time or needing to bring someone on to manage it. Takes about a minute to look at."

---

## What This Generates

A one-page HTML visual that shows:
1. **The Timeline:** Minute 0 → Within Minutes → Hour 1-2 → Hour 6-12 → Day 1-2 → Day 3+ → Appointment Booked
2. **The Gap:** Side-by-side comparison of "When It Depends on Your Team" vs "When It Runs on Its Own"
3. **Industry Statistics:** 4-6 data points showing why speed and follow-up matter (with sources)
4. **Personalization:** Company name, industry-specific scenario, service area

**Format:** Single HTML page, mobile responsive, takes ~60 seconds to review

**Output URL:** `https://view.adverosolutions.com/{slug}`

---

## Required Input

| Field | Example | Required | Source |
|-------|---------|----------|--------|
| Company name | "Apex Roofing" | Yes | CRM V2 or Instantly API |
| Owner first name | "Mike" | Yes | CRM V2 or Instantly API |
| Vertical | `hvac` or `roofing` | Yes | Campaign name detection |
| Service area | "Phoenix Metro" | Yes | CRM V2 or fallback defaults |

**Optional:**
- Primary color (defaults per industry)
- Accent color (defaults per industry)

---

## Tools

**Primary Scripts:**
- `execution/generate_free_value.py` — HTML generation (delegates to v2)
- `execution/generate_free_value_v2.py` — Business Bible compliant generator
- `execution/deploy_to_github_pages.py` — GitHub Pages deployment

**Templates:**
- `execution/templates/free_value_base_v2.html` — HTML structure
- `execution/templates/free_value_hvac_v2.json` — HVAC content and statistics
- `execution/templates/free_value_roofing_v2.json` — Roofing content and statistics

**Supporting:**
- `execution/free_value_tracker.py` — Track who received what (prevents duplicates)
- `execution/free_value_system.py` — Orchestration layer

---

## Process

### 1. Extract Lead Data
**From CRM V2 Google Sheet** (primary source):
- Sheet ID: `1zWez99wTc9yRVIgOqcTJKOwlxuBJMbG0i5YwC-6eob8`
- Tabs: "HVAC Leads", "Roofing Leads"
- Fields: company_name, first_name, service_area, vertical

**Fallback to Instantly API** if CRM lookup fails:
- Use webhook payload data
- Use campaign name for vertical detection

### 2. Generate HTML
```python
from generate_free_value import generate_html

html_content, slug, output_path = generate_html(
    company_name=company_name,
    owner_first_name=first_name,
    industry=vertical,  # 'hvac' or 'roofing'
    services=[],  # Not used in v2, kept for compatibility
    service_area=service_area
)
```

**What happens:**
- Loads industry-specific JSON (hvac_v2 or roofing_v2)
- Personalizes scenario text with company name
- Injects statistics from template
- Renders Jinja2 HTML template
- Writes to `.tmp/free_value/{slug}.html`

### 3. Deploy to GitHub Pages
```python
from deploy_to_github_pages import deploy_html_to_github_pages

public_url = deploy_html_to_github_pages(
    html_content=html_content,
    slug=slug
)
```

**What happens:**
- Writes HTML to `/free-value-pages/pages/{slug}.html`
- Git add, commit, push to GitHub
- GitHub Pages serves at `https://view.adverosolutions.com/{slug}`
- Verification: Checks URL is accessible

### 4. Track in Google Sheet
```python
from free_value_tracker import record_free_value_sent

record_free_value_sent(
    lead_email=lead_email,
    company_name=company_name,
    free_value_url=public_url,
    vertical=vertical
)
```

**What happens:**
- Records to "Free Value Tracker" tab in CRM V2
- Fields: Email, Company, URL, Vertical, Timestamp, Status
- Used for duplicate prevention and analytics

### 5. Send Reply
Reply template (per Free Value Guide Section 5):

```
Hey {{firstName}},

Here's the breakdown for {{companyName}}. It maps out the full window from first inquiry to [estimate/appointment] booked.

{{public_url}}

Takes about a minute to look at.

Let me know what stands out to you.

Lorenzo
```

---

## Business Bible Compliance

### Email Promise Match
- ✅ "Visual breakdown" = one-page HTML timeline
- ✅ "First inquiry to [estimate/appointment] booked" = timeline structure shows this
- ✅ "Takes about a minute" = simple, scannable, mobile-friendly
- ✅ "Without taking up team time" = shows automated flow in "Runs on Its Own" column
- ✅ "Without needing to hire" = gap comparison shows it doesn't require staff

### Free Value Guide Requirements (from Business Bible)

**Job 1: Show the timeline they've never mapped**
- ✅ Timeline: Minute 0 → Booked appointment
- ✅ Each step labeled with time and action
- ✅ Shows WHAT happens, not HOW

**Job 2: Show the gap**
- ✅ Side-by-side: Team-Dependent vs Automated
- ✅ Left side shows consequences (delays, lost leads, inconsistency)
- ✅ Right side shows outcomes (speed, persistence, 100% coverage)
- ✅ Gap is shown, never stated

**Job 3: Make them ask "how does this work?"**
- ✅ No technology explanations
- ✅ No AI mentions, no tool names
- ✅ No CTAs ("Book a Call", "Schedule Demo")
- ✅ Shows outcomes without revealing implementation

### Tone & Content Rules
- ✅ No tech talk, no AI buzzwords
- ✅ Operator-to-operator language
- ✅ Pattern language ("tends to," "usually") not certainty ("always")
- ✅ Shows homeowner experience
- ✅ Statistics build urgency through facts, not pressure
- ✅ Personalized with company name throughout

### Format Rules
- ✅ One page only
- ✅ No login required
- ✅ Direct URL (not behind portal or link wall)
- ✅ Mobile responsive
- ✅ Professional but not overdesigned
- ✅ Reads like operator-built, not agency-made

---

## Industry Statistics Integration

### Purpose
Statistics show prospects WHY they need this system without you having to sell them on it. Numbers create urgency through facts, not pressure.

### Statistics Placement

**1. Scenario Section (Top)**
- One high-impact stat that sets context
- HVAC: "78% of homeowners hire whoever responds first (Harvard Business Review)"
- Roofing: "After a storm, 70% of jobs go to companies that respond in the first 24 hours"

**2. Gap Comparison (Middle - Left Side)**
- Show delay consequences with data
- "After 5 minutes, conversion drops 80% (MIT study)"
- "Average HVAC company response: 42-48 hours"
- "43% of storm leads never get contacted at all"

**3. Reality Check Section (Bottom)**
- 4-6 statistics that build the case
- Mix of speed-to-lead + follow-up persistence + industry benchmarks
- Cite sources in parentheses (subtle, credible)
- No hype, just facts

### Statistics Guidelines

**DO:**
- State facts matter-of-factly
- Use pattern language ("tends to," "usually," "most")
- Frame as observations, not accusations
- Cite credible sources (MIT, Harvard, NRCA, ACCA, CallRail)
- Show consequences without fear tactics

**DON'T:**
- Use certainty claims ("always," "guaranteed")
- Create urgency through manipulation
- Accuse the business owner
- Use hype language
- Make it feel like a scare tactic

**Example Good Usage:**
- ✅ "78% of homeowners hire whoever responds first (Harvard Business Review)"
- ✅ "80% of conversions happen after 5+ follow-ups — most companies quit after 1-2"
- ✅ "Weekend storm inquiries: 8% close if they wait vs 38% for instant response"

**Example Bad Usage:**
- ❌ "You're LOSING 78% of your leads because you're TOO SLOW!"
- ❌ "Your competitors are CRUSHING you!"
- ❌ "Act NOW before you lose another $100,000!"

### Sources
See `execution/STATISTICS_SOURCES.md` for complete list of statistics and citations.

---

## Timing Budget (60s SLA)

| Step | Time |
|------|------|
| CRM V2 lookup | 2-4s |
| HTML generation (Jinja2) | <1s |
| GitHub Pages deployment | 10-15s |
| URL verification | 1-2s |
| Track in Google Sheet | 2-3s |
| Send reply (Instantly API) | 1-2s |
| **Total** | **~15-25s** |

---

## Edge Cases

### Missing Data

**No service area:**
- Use city from business address
- Fallback: "your area"

**No first name:**
- Use "there" as fallback
- Still personalize company name

**No vertical detection:**
- Check campaign name for "hvac" or "roof"
- Check CRM V2 vertical column
- Default to "hvac" if unclear

**No company name:**
- This is required - cannot generate without it
- Return error, send manual reply without free value

### Deployment Failures

**GitHub Pages deploy fails:**
- Check git authentication
- Check repo exists at `/free-value-pages`
- Check network connectivity
- Fallback: Send reply offering to create one, log error to Slack

**URL verification fails:**
- Sometimes GitHub Pages takes 30-60s to propagate
- Don't block on verification
- Send URL anyway, it will work within a minute

### Duplicate Prevention

**Lead already received free value:**
- Check `free_value_tracker.py` - `has_received_free_value(email)`
- Check thread history via Instantly API - `is_first_reply()`
- BOTH checks must pass (dual-check system)
- If duplicate detected: Skip generation, Slack notify, no auto-response

**Same company, different contact:**
- Allow generation (different person at same company)
- Slug will be unique due to email/timestamp in slug generation

---

## Error Handling

**Generation fails:**
- Log error with full traceback
- Slack alert with lead details
- Send manual reply offering to create one
- Do not send free value URL

**Deployment fails:**
- Same as above
- Attempt local file save for manual review

**Tracker update fails:**
- Log warning (not critical)
- Continue with reply
- Fix tracker manually later

**Reply send fails:**
- Log error
- Slack alert HIGH PRIORITY
- Manually send reply with free value URL

---

## Testing

### Manual Test
```bash
python execution/generate_free_value.py \
    --company "Smith Heating" \
    --owner "John" \
    --industry hvac \
    --services "AC Repair,Installation" \
    --area "Dallas Metro"
```

Check output:
1. HTML file created in `.tmp/free_value/`
2. Statistics present and formatted correctly
3. Company name appears throughout
4. Timeline shows inquiry → appointment flow
5. Gap comparison visible
6. Mobile responsive
7. Takes ~60s to review

### Integration Test
```python
# See execution/test_free_value_v2.py
from generate_free_value_v2 import generate_free_value_html_v2

lead_info = {
    "company_name": "Apex Roofing",
    "first_name": "Mike",
    "service_area": "Phoenix Metro"
}

html, slug = generate_free_value_html_v2(lead_info, "roofing")

# Verify Business Bible compliance
assert "Apex Roofing" in html
assert "artificial intelligence" not in html.lower()
assert "Book a call" not in html
assert "78%" in html or "70%" in html  # Statistics present
```

### Production Webhook Test
Use test mode in webhook handler:
```python
test_payload = {
    "data": {
        "lead": {"email": "test@example.com"},
        "reply": {"text": "Yes, send it over!"},
        "campaign": {"name": "HVAC - Test Campaign"}
    }
}
```

---

## Success Metrics

**Technical:**
- Generation time: <5s
- Deployment time: <15s
- Total response time: <60s
- URL accessibility: 100%
- Zero errors in production

**Engagement:**
- URL click rate: Track via analytics
- Reply rate: "What stands out" responses
- Quality of replies: Specific questions vs vague acknowledgments

**Conversion:**
- "How does this work?" rate
- Call booking rate
- Deal progression rate

---

## Learnings

### 2026-03-26 - Statistics Enhancement
- Added industry statistics from MIT, Harvard, NRCA, ACCA, CallRail
- Enhanced HVAC template: 6 stats with sources
- Enhanced Roofing template: 6 stats with sources
- Statistics create urgency through facts, not pressure
- Operator tone maintained: "What we're seeing," not "you must act"
- Sources cited in parentheses for credibility

### Previous Learnings
- V2 templates are Business Bible compliant (no tech talk, no CTAs)
- GitHub Pages deployment is reliable and fast
- Dual-check duplicate prevention (thread + tracker) prevents errors
- Service area defaults work fine when missing specific data
- Mobile responsive design critical (40%+ view on phones)

---

## Related Directives

- `directives/AUTOMATED/handle_reply.md` — Overall reply handling flow
- `directives/USER/generate_free_value.md` — Manual generation (deprecated, use this directive)

---

## Manual Override

If you need to manually generate and send:

1. Generate HTML:
```bash
python execution/generate_free_value.py \
    --company "Company Name" \
    --owner "FirstName" \
    --industry [hvac|roofing] \
    --services "Service1,Service2" \
    --area "Service Area"
```

2. Note the slug from output

3. Deploy (if not auto-deployed):
```bash
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/free-value-pages
git add pages/{slug}.html
git commit -m "Add free value: {slug}"
git push
```

4. URL will be: `https://view.adverosolutions.com/{slug}`

5. Send reply manually via Instantly with URL

---

**Last Updated:** 2026-03-26
**Next Review:** After 50 production uses or quarterly
