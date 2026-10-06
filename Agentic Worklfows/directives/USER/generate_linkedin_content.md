# Generate LinkedIn Content

> **RETIRED (2026-10-06).** LinkedIn posts are written with the `linkedin-content` skill, by Opus, from real material only. Do not run `execution/linkedin_content_generator.py` or use `execution/linkedin_post_profile.json`: they allow fabricated stories and numbers. The rest of this file is kept as history.

**Purpose:** Generate 5-10 LinkedIn posts per day across 5 content pillars, output to Google Sheets content calendar
**When to use:** Weekly (or as needed) to fill the content queue
**Cost:** ~$0.02 per post on Claude Opus 5.5 at low effort (rough estimate; every model call runs on Opus 5.5 since 2026-09-25)

---

## What This Does

Generates a batch of LinkedIn posts optimized for engagement and personal branding. Posts are designed to position Lorenzo as an authority in AI-powered contractor growth. Output goes directly to a Google Sheet for easy copy-paste into LinkedIn's native scheduler.

---

## Content Pillars

| # | Pillar | Description | Example Topics |
|---|--------|-------------|----------------|
| 1 | **Contractor Growth** | Scaling, hiring, systems for home service businesses | Revenue milestones, hiring first employee, systemizing ops |
| 2 | **AI in Home Services** | How AI is transforming HVAC/plumbing/electrical/roofing | AI scheduling, automated follow-ups, predictive maintenance |
| 3 | **Lead Generation** | Cold outreach, inbound, paid ads, referrals | Email deliverability, response rates, campaign strategies |
| 4 | **Sales** | Closing, objection handling, pricing, one-call close | Handling "let me think about it", pricing confidence, follow-up |
| 5 | **Founder Journey** | Building AdveroSolutions, raw takes, lessons learned | Failures, wins, decisions, lifestyle, motivation |

---

## Post Types (Mixed Daily)

| Type | Structure | Best For |
|------|-----------|----------|
| **Hook + Story** | Attention-grabbing opener → narrative → lesson | Founder journey, case studies |
| **Hot Take** | Contrarian opinion → reasoning → reframe | AI, lead gen, sales |
| **Listicle** | "X things I learned..." or "X mistakes..." | Education, growth |
| **Data/Results** | Specific numbers → context → takeaway | Lead gen, contractor growth |
| **Question/Poll** | Provocative question → context → invite discussion | Engagement bait |
| **How-To** | Problem → step-by-step → result | Actionable education |
| **Behind-the-Scenes** | What you're building/testing right now | Founder journey, AI |

---

## Prerequisites

- `ANTHROPIC_API_KEY` in `.env`
- Google Sheets credentials configured (`credentials.json`)
- LinkedIn Content Calendar sheet created (see Output Format below)

---

## Required Tools

- `execution/linkedin_content_generator.py` - Main generation engine
- `execution/google_sheets_client.py` - Google Sheets integration

---

## Input Format

### Option 1: Generate a Week of Content
```
"Generate LinkedIn content for 7 days"
```

### Option 2: Generate Specific Count
```
"Generate 50 LinkedIn posts"
```

### Option 3: Specific Pillar Focus
```
"Generate 20 LinkedIn posts focused on AI in home services"
```

### Option 4: Test Mode
```
"Generate 3 test LinkedIn posts"
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--days` | 7 | Number of days to generate content for |
| `--posts-per-day` | 7 | Posts per day (5-10 range) |
| `--pillar` | all | Focus on specific pillar (1-5 or "all") |
| `--sheet-id` | from .env | Google Sheet ID for content calendar |
| `--model` | `claude-opus-5-5` | Model id sent to the API. Leave the default: the call sends `output_config.effort`, which Haiku rejects |
| `--dry-run` | false | Preview without writing to sheet |

---

## Output Format

### Google Sheet Structure (Tab: "LinkedIn Queue")

| Column | Content |
|--------|---------|
| Date | Post date (YYYY-MM-DD) |
| Time Slot | Suggested posting time (e.g., "7:00 AM") |
| Pillar | Content pillar (1-5) |
| Post Type | Hook+Story, Hot Take, Listicle, etc. |
| Content | Full post text (ready to copy-paste) |
| Status | Generated / Scheduled / Posted |
| Engagement | Track likes/comments after posting (manual) |

---

## Process Flow

1. Script reads existing posts from sheet (avoids duplicates/repetition)
2. Distributes posts across pillars and types for variety
3. Generates each post using Claude with LinkedIn-optimized prompts
4. Writes batch to Google Sheet
5. Reports stats (posts generated, cost, pillar distribution)

---

## LinkedIn Best Practices (Built Into Prompts)

- **Hook in first line** — Must stop the scroll
- **Short paragraphs** — 1-2 sentences max per line
- **Line breaks** — White space is your friend
- **No hashtags in body** — Add 3-5 at the very end if needed
- **Under 3,000 characters** — Sweet spot is 800-1,500
- **End with engagement driver** — Question, hot take, or CTA
- **Personal voice** — First person, conversational, direct
- **Specific > generic** — Real numbers, real names, real stories

---

## Example Usage

### Weekly Content Generation
```bash
python3 execution/linkedin_content_generator.py --days 7 --posts-per-day 7
```

### Quick Test
```bash
python3 execution/linkedin_content_generator.py --days 1 --posts-per-day 3 --dry-run
```

### Pillar-Focused Batch
```bash
python3 execution/linkedin_content_generator.py --days 3 --pillar "founder journey"
```

---

## Troubleshooting

### "Rate limit exceeded"
→ Script has built-in delays between API calls. If persistent, reduce batch size.

### "Sheet not found"
→ Ensure `LINKEDIN_SHEET_ID` is in `.env` and service account has edit access.

### "Posts feel repetitive"
→ Script reads last 50 posts from sheet to avoid repetition. If still an issue, increase diversity weight in prompts.

---

## Post-Generation Workflow

1. Run generator (fills sheet with a week of content)
2. Open Google Sheet → review posts
3. Edit any that need personal touches (add real client names, specific numbers)
4. Open LinkedIn → copy-paste → use native scheduler
5. Track engagement in the sheet after posting
