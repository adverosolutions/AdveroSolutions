<!-- distill: batch_10_of_11 | videos: zLDu0l_AbVw, 7yWkTc8nqvY, yj-cGa7VVwE, 9HCUGBLAVeQ, kFQfMZBo6Lo | model: opus | elapsed_s: 69 -->

# Playbook batch: Cursor as the GTM build layer (Maps scrapes, Python + OpenRouter enrichment, campaign ops) + Clay operating rules

> Transcription names normalized: Smartle→Smartlead, Superbase→Supabase, serpent/server.dev→Serper.dev, Clagent→Claygent, "40 mini"→GPT-4o mini, "OSS 20 billion"→gpt-oss-20b, ICPS→Icypeas, Prospio→Prospeo, Zenro→ZenRows.

## 1. Frameworks / mental models

- **Division of labor: Cursor + Clay + sequencer** [9HCUGBLAVeQ]
  - Cursor is the front end for building, launching, list cleaning and analytics.
  - Clay stays the engine for scale. Its main advantages are queueing and rate-limit protection, cloud runs, and visual workflows.
  - Smartlead/Instantly is used only to check what Cursor built.
  - Eric's daily stack: project mgmt → Cursor → Clay → Smartlead/Instantly.
  - "Anybody that thinks that you can replace… Clay with Cursor and n8n… they're not thinking about this level of scale." [9HCUGBLAVeQ]
- **The 3 Cursor buckets** [9HCUGBLAVeQ]
  1. Launch faster
  2. Clean and enrich lists
  3. Analyze results
- **Build once, reuse forever.** The first run in Cursor may be slower than doing it manually. After that, the code is saved to GitHub and you rerun it. [9HCUGBLAVeQ][zLDu0l_AbVw]
  - While learning, run Cursor on one half of the screen and do the task manually on the other half. [zLDu0l_AbVw]
- **GTM code is "crushing beer cans" for AI coding tools.** These tools are built for enterprise software, so gluing three APIs together is trivial for them. Use this to stop being blocked by being non-technical. [yj-cGa7VVwE][zLDu0l_AbVw][9HCUGBLAVeQ]
- **10-minute manual research rule** [kFQfMZBo6Lo]
  - Ask: "What would I look for if I researched this prospect manually for 10 minutes?"
  - Automate that, working backwards.
  - Don't ask what other people use AI for.
- **One AI call = one job.** [kFQfMZBo6Lo]
  - Example: step 1 scrapes site content (Claygent). Separate downstream columns then answer: is it CPG? what products? what industry?
  - Separating is cheap on small models.
- **80/20 inversion** [kFQfMZBo6Lo]
  - "20% of building a clay table is putting the integrations in and then 80% is fiddling with that AI."
  - Budget time for edge-case prompting.
- **LinkedIn vs Google Maps sourcing** [7yWkTc8nqvY]
  - Use LinkedIn when persona accuracy matters.
  - Use Google Maps for local or low-LinkedIn industries. "99% of the time" these businesses are on Maps.
  - If a business is not on Maps, it's likely not worth emailing.

### Cursor build checklist (for team) [zLDu0l_AbVw]
- [ ] Start every build in **Plan mode**. Dump context by voice (Whisper Flow or a phone voice memo transcript).
- [ ] Paste the **exact API endpoint docs** into the plan. Otherwise, make it name the endpoint plus the doc URL it used so you can verify. (Eric saw it call a wrong Smartlead host.)
- [ ] Prompt: *"print the current status of what you're doing"* so failures don't go silent. Eric once waited 20 min on an errored run.
- [ ] *"Before you run the whole code, make a testing code"*, and test on a small batch first.
- [ ] *"Make a CSV backup as it runs so we can resume."* This came after a crash lost classification data.
- [ ] Add a global rule: read and write are allowed, **no deletes without explicit confirmation**.
- [ ] Stuck? Screenshot the error and give it to Cursor or ChatGPT.
- [ ] Prefer direct endpoints over MCPs. Eric found MCPs "think and think… and doesn't actually get anything done".
- [ ] Don't show your screen while API keys are visible. Eric uses a docs/.md walkthrough instead.

## 2. Copy formulas

*The transcripts contain very little copy. Only these items are usable:*

- **Local-business first line: reference their Google reviews.** Eric scrapes review data alongside Maps listings because "they love mentioning the business reviews." [7yWkTc8nqvY]
  - Template: `Saw {{review_snippet/theme}} in your Google reviews — {{bridge to offer}}.`
- **Website-observation line (the level of personalization Eric targets with small models):** "I saw on your website you help fitness enthusiasts breathe better." [kFQfMZBo6Lo]
  - Template: `I saw on your website you help {{audience}} {{outcome}}.`
- **Case-study hook, with a fallback.** Scrape the case studies or customers page for a proof hook. If none is found, the model outputs `purple` and that row gets a different variant. [kFQfMZBo6Lo][yj-cGa7VVwE]

## 3. Offer / angle patterns
*(No explicit offers in these videos. Section omitted.)*

## 4. List-building & enrichment tactics

**Google Maps scrape via Cursor** [7yWkTc8nqvY]
1. Get a zip code or town list. Use ChatGPT deep research or open zip datasets.
2. Choose an API:
   - RapidAPI "Google Maps Extractor". Quoted: "$100 you could get 500,000 requests"; 1 request = 1 search page.
   - Serper.dev, or Outscraper, also work.
3. Show Cursor the endpoint's **parameters and a sample response** (e.g. locate/search, query locate, business reviews). Being explicit improves results.
4. Prompt template:
   > "Build a workflow: I give you a CSV of `{{zip codes/towns}}`. Search each for `{{keyword}}` (e.g. 'restaurant in 07070'). Go **3–5 pages deep**. Return all fields and categories, plus review data. Save CSV backups."
5. For dense areas (e.g. NYC), split searches further, since one zip is overloaded.
6. Send output → Clay → Smartlead/Instantly.

**Website classification: Python + OpenRouter** [yj-cGa7VVwE][9HCUGBLAVeQ]
- Old approach: merging "is SaaS" tags from Crunchbase, Apollo, Owler and Ocean with keyword scores. This was "highly inaccurate… a waste of time."
- New approach:
  1. Python scrapes the homepage to markdown.
  2. Cursor and you co-build the prompt. Scrape 10–20 examples, give your reasoning, and let it write the prompt.
  3. Run batched through OpenRouter on **gpt-oss-20b**.
  4. Quoted result: "109,000 companies… maybe we used $20 of credits." "Unknown" results were mostly dead sites.
- Extension:
  - If qualified, fetch the sitemap. Keyword-match `pricing`, `customers`, `case study` or `product`, then scrape and summarize.
  - If there's no clear match, give the sitemap to the LLM to pick the page.
- This avoids ZenRows concurrency limits and the awkwardness of using OpenRouter inside Clay.
- Cost option: run gpt-oss-20b locally so "we're just paying for electricity." [9HCUGBLAVeQ]

**DIY email waterfall (built in Cursor)** [9HCUGBLAVeQ]
1. Check Supabase: was this email validated before?
2. MillionVerifier on the **6 most common email permutations**.
3. Provider waterfall: LeadMagic first (for speed), then Icypeas, then Prospeo.

**Clay operating rules** [kFQfMZBo6Lo]
- [ ] **Conditional formula on every paid integration**, even a trivial one like `first name not empty`.
- [ ] **Functions** (beta at the time): many tables call one shared workflow, e.g. a waterfall or CRM lookup/update/create. Change it once instead of editing 400 tables.
- [ ] **Save all paid data** to a CRM or Supabase. Clay is middleware and doesn't keep data like ZoomInfo or Apollo do. Look it up before paying again.
- [ ] **Evergreen campaigns via scheduled sources.** Load the full TAM into a cheap HubSpot account (quoted "$15 a month"), create a segment (formerly active list), and let Clay pull from it continuously. This replaced "60 of these manual tasks every day".
- [ ] **Formulas over AI** for clean, combine, if/then, scoring and abbreviations (NJ). Formulas are JavaScript; if stuck, screenshot and ask ChatGPT.

**AI prompting rules** [kFQfMZBo6Lo]
- [ ] **Sentinel output:** "if there's no case study… output `purple`". Filter on it downstream, because free-text failure messages vary and Claygent confidence is unreliable.
- [ ] **3–4 hand-written examples** in every prospect-facing prompt.
- [ ] **Meta-prompt:** have ChatGPT draft the prompt, then ask *"What questions do you have for me to improve this prompt?"* and answer them by voice. (Credited to Yash at Clay.)
- [ ] **Reasoning before answer** for hard tasks such as industry classification.
- [ ] **Review loop:** read outputs, and patch the prompt for each bad pattern you find.

## 5. Deliverability / inbox infra notes

- **Hot-swapping inboxes** [9HCUGBLAVeQ]
  - Tag inboxes as `active` or `insurance`.
  - Per customer, list the allowed domains, pull account IDs from Supabase, and have Cursor load them into Smartlead.
- **Validation loss is large.** Quoted: process "probably like… 18 million contacts to be able to send the six million emails" monthly. Plan list volume at about 3× sends. [kFQfMZBo6Lo]
- **Validated-email cache** in Supabase. Quoted: "11.4 million records" on a "$30 a month" plan. [kFQfMZBo6Lo]
- Cursor is also used for deliverability number crunching. No specifics were given. [9HCUGBLAVeQ]

## 6. Metrics & testing cadence

- **Responder vs positive-responder diff** [9HCUGBLAVeQ]
  - Pull all sent contacts, all replies and all positives via the sequencer API.
  - Compare by industry and job title.
  - This surfaced "two particular industries" driving most positives.
  - Prompt: *"We have good days and bad days with this customer. Analyze everyone emailed vs responded vs positively responded — industries and titles — show the differences. Save CSV."*
- **Scheduled analytics:** GitHub Actions cron (quoted free tier: "2,000 minutes per month" for private repos, free for public) → Supabase. This replaces Make/n8n → Sheets. [zLDu0l_AbVw][9HCUGBLAVeQ]
- **Bulk campaign ops** [9HCUGBLAVeQ][zLDu0l_AbVw]
  - Upload copy, and Cursor proposes the campaign grouping.
  - You approve, then it creates the campaigns, sets settings and subsequences, and bulk-edits past campaigns.
  - Eric: "set up 20 different Smartlead campaigns in one shot". Always test settings first.
- **Evergreen logic:** campaigns that "mathematically just work" (known sends → positives) are kept always-on via scheduled sources. [kFQfMZBo6Lo]

## 7. Tools mentioned

| Tool | How used | Src |
|---|---|---|
| Cursor | Main GTM front end: plan mode, builds scrapers, campaign setup, analytics. Includes Claude Code and Codex models | all Cursor vids |
| Whisper Flow / voice memos | Voice prompts pasted into plan mode | [zLDu0l_AbVw][9HCUGBLAVeQ] |
| ChatGPT | Screenshot debugging, meta-prompting, deep research for zip lists | [zLDu0l_AbVw][7yWkTc8nqvY][kFQfMZBo6Lo] |
| Clay | Scaled enrichment, queueing, Claygent, Functions, scheduled sources, audiences | [9HCUGBLAVeQ][kFQfMZBo6Lo] |
| Smartlead / Instantly | Sequencer. Used as a UI to check Cursor's API work | [9HCUGBLAVeQ] |
| Supabase | Data store for validated emails, inbox account IDs, analytics | [zLDu0l_AbVw][9HCUGBLAVeQ][kFQfMZBo6Lo] |
| GitHub / GitHub Actions | Code storage and cron jobs | [zLDu0l_AbVw] |
| OpenRouter + gpt-oss-20b | Cheap batch classification | [yj-cGa7VVwE][9HCUGBLAVeQ] |
| Python scraping libs | Homepage and sitemap scraping to markdown | [yj-cGa7VVwE] |
| RapidAPI Google Maps Extractor / Serper.dev / Outscraper | Maps listings and reviews | [7yWkTc8nqvY] |
| MillionVerifier, LeadMagic, Icypeas, Prospeo | Email waterfall | [9HCUGBLAVeQ] |
| HubSpot ($15/mo) | TAM holding pen (segments) for Clay scheduled sources | [kFQfMZBo6Lo] |
| GPT-4o mini | Default model for all Clay AI columns | [kFQfMZBo6Lo] |
| Gamma | Presentation decks | [7yWkTc8nqvY][9HCUGBLAVeQ] |
| Railway / Vercel | Suggested hosting. Not yet adopted | [zLDu0l_AbVw] |

## 8. Caveats / dated claims to re-validate

- **Instantly parity:** Eric's automations target the Smartlead API. Before reusing them, verify the equivalent Instantly API endpoints (campaign create, account assign, subsequences, analytics). [9HCUGBLAVeQ][zLDu0l_AbVw]
- **RapidAPI pricing** ("$100… 500,000 requests") and "worked… three times at the timing of this video". Recheck both. [7yWkTc8nqvY]
- **"$20 for 109,000 companies"** is stated loosely ("I think maybe"). [yj-cGa7VVwE]
- **Clay volume figures are inconsistent within the talk:** "37 million rows" last week vs. "27 million… this week" and "35 million". Also "6 million emails a month", "400 tables", "500,000 rows a day". These are self-reported. [kFQfMZBo6Lo][9HCUGBLAVeQ]
- **Clay Functions** was beta and enterprise-first at the time. Check availability on the Advero plan. [kFQfMZBo6Lo]
- **HubSpot** "active lists" were renamed to **segments**. [kFQfMZBo6Lo]
- **GPT-4o mini as default** is likely superseded. Re-benchmark cost and quality on current small models. [kFQfMZBo6Lo]
- **GitHub Actions free-minute quota** and Supabase $30 tier limits may have changed. [zLDu0l_AbVw][kFQfMZBo6Lo]
- **MCP skepticism** is Eric's early opinion after 2 weeks ("I could be… totally wrong"). [zLDu0l_AbVw]
- **Compliance:** scraping Google Maps and site content has ToS and legal implications that were not addressed (the compliance slide was a joke). [7yWkTc8nqvY]

## Source videos
- zLDu0l_AbVw — First 2 Weeks of Using Cursor for GTM Learnings
- 7yWkTc8nqvY — Cursor Scraping Google Maps
- yj-cGa7VVwE — Cursor to Research Companies for Outbound Campaigns
- 9HCUGBLAVeQ — Cursor GTM Use Cases
- kFQfMZBo6Lo — Lessons on Using Clay.com From Their Largest User
