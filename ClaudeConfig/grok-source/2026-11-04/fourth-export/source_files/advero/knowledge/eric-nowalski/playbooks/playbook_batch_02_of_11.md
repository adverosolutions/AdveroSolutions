<!-- distill: batch_02_of_11 | videos: aq5r3_CMh-s, 4Kf3CkdvFTY, hxolLxHiydg, Ct4AUtQnIYE, SmCodMPSDlE | model: opus | elapsed_s: 91 -->

# Playbook batch: AI-orchestrated list building, signal selection, and agentic campaign ops (post-Apollo stack)

## 1. Frameworks / mental models

- **Build the company list first; contacts are the easy part.** Eric treats a strong company list as the main problem, since finding contacts is straightforward with AI. [aq5r3_CMh-s]
- **Pull broadly, then judge with AI.** LinkedIn-derived industries are self-reported, so niche ICPs get misclassified. For example, real-estate SaaS may be tagged "real estate", and "peptide manufacturing" doesn't exist as an industry. Pull every industry or keyword a known-good company appears under, then have a cheap LLM filter out the bad fits. [aq5r3_CMh-s]
- **Waterfall company sourcing by data type:** [SmCodMPSDlE]
  1. Start with high-fidelity, cheap data:
     - LinkedIn-based sources (Blitz API, Clay, Prospeo) for firmographic ICPs, e.g., "marketing agencies, 10–200 employees".
     - Google Maps-based sources for local businesses, e.g., "HVAC with 200 Google reviews".
  2. Use expensive AI-search tools (Ocean.io, DiscoLike, Parallel, Exa) only to fill gaps for companies that have a website but are missing from those sources.
- **Signal ranking criteria:** effectiveness (does the signal translate to need?), accessibility (cost and ease of getting the data), and scalability (enough volume to build pipeline). [hxolLxHiydg]
- **Two kinds of companies:** those trying to grow and those content with the status quo or dying. Outbound works best on growers, so use growth signals as silent filters. [hxolLxHiydg]
- **Signal as filter vs. signal as copy.** Many signals should only narrow the list and should never be mentioned in the email. Examples: funding, general growth, social activity, website visits. [hxolLxHiydg]
- **Dream 100 → Dream 1,000/10,000.** This is Chet Holmes' *Ultimate Sales Machine* approach: pick dream accounts and earn attention with free value and multi-threading. AI makes the free-value asset scalable. [Ct4AUtQnIYE]
- **Low-volume, high-intent lane alongside volume.** Eric's example: "reach out to 500 people per day automatically, but … five people manually that are super good fits". [SmCodMPSDlE]
- **Company brain.** Keep SOPs, skills, and every client communication in a local Obsidian vault so the agent reads it locally instead of making many tool calls to Fathom or Slack. [4Kf3CkdvFTY]
- **Write a skill when you solve something.** After figuring out a process with the agent, have it write a skill file so it's repeatable. Watch for details lost to context compaction. [4Kf3CkdvFTY]

## 2. Copy formulas

> No subject-line or follow-up formulas were given in this batch. Everything below is first-line or angle-level.

**Allowed first-line / body patterns**

- **Competitor movement:** "We have a strategy that we don't think [Competitor] is using right now." [hxolLxHiydg]
  - Eric reports getting Anthropic to reply by mentioning OpenAI. [hxolLxHiydg]
- **Job description mining** (reference the specific need, not the fact that they're hiring): [hxolLxHiydg]
  - Template: "I saw that you need an [ABM expert] in this new [enterprise SDR] role. How's the search going for that person? We have a service that does [XYZ]."
- **Hire replacement / Dream 100:** "I saw you're hiring for [role]. You might not need to hire for them because [we can do it / we have a product]. This is what the output would look like: [asset]." [Ct4AUtQnIYE]
- **Customer complaint → fix:** Frame the email around the solved complaint. Example complaint: "I tried calling [home service co.] and nobody picked up the phone." [hxolLxHiydg]
- **Lookalike case study:** "I ran outbound for [clay.com]. You are a competitor to [clay.com]. Wouldn't you want me to run the outbound? This is the result that I got." [hxolLxHiydg]
- **Competitor pricing change** (sent to the competitor's customers): "Hey, did you see that pricing change? … Wouldn't you want to work with us?" [hxolLxHiydg]
- **Audit finding** (browser-automation research): "You're not collecting sales tax properly…" [SmCodMPSDlE]
- **Lawsuit / compliance:** Let some time pass first and avoid a "you did something wrong" tone so the email doesn't feel predatory. [hxolLxHiydg]

**Banned / avoid**

- ❌ "Congrats on raising your recent round" or "I noticed you raised". Eric's agency has banned this from copy. [hxolLxHiydg]
- ❌ "I noticed you're hiring for an SDR, you could use my [thing]". This is the lazy use of job-post data. [hxolLxHiydg]
- ❌ "I saw you follow [X]" or "I saw you liked [post]". Use social activity only as a filter. [hxolLxHiydg]
- ❌ Never tell website visitors you found them from their site visit. [hxolLxHiydg]
- ❌ Product-launch "personalized first lines". They're costly to extract and usually arrive after the moment has passed. [hxolLxHiydg]
- **AI writing hygiene:** set explicit rules for no em dashes and no "it's not X, it's Y" formatting. Eric says Opus 5 was the first model to follow these rules reliably. [4Kf3CkdvFTY]

## 3. Offer / angle patterns

- **Do the job description for them.** [Ct4AUtQnIYE]
  1. Scrape companies hiring for [role].
  2. Enrich the job description.
  3. Have an agent produce a sample of that role's deliverable. Eric's example was an ABM target list with use cases, trigger signals, personas, and account briefs for "the Hog".
  4. Send it as free value.
- **Lookalike case study.** Target competitors or lookalikes of a client you already got results for. [hxolLxHiydg]
- **Competitor-audience offer.** One client offered to create a newsletter targeted at a prospect's competitor's LinkedIn followers. [hxolLxHiydg]
- **Custom-trigger offers (S-tier):** [hxolLxHiydg]
  - Reputation management → new negative Google review.
  - Parking-lot paving → satellite-image AI detecting cracked or faded lots (built by Jordan Crawford).
- **Diagnostic finding as hook.** Example: a sales-tax misconfiguration found via Browser Use. [SmCodMPSDlE]

## 4. List-building & enrichment tactics

### A. List builder + list expander skill (Eric's Apollo replacement) [aq5r3_CMh-s]

- [ ] **Intake:** ICP description, geography, headcount band, and output destination (e.g., Google Sheet).
- [ ] **Seeds:** use the client's do-not-contact list (closed won, closed lost, open opportunities, pipeline) as known-good companies.
- [ ] **Probe:** look up the seeds in Prospeo. Record their self-reported industries, Prospeo keywords, and other attributes.
- [ ] **Expand the seeds:**
  - Prospeo company lookalike
  - Exa "Find Similar"
  - Parallel Entity Search
- [ ] **Pull everything:** every company matching *any* industry or keyword that appeared even once among good fits. Restrict by headcount and geography.
- [ ] **Merge** into one database.
- [ ] **Judge** each company with GPT-5 Nano against a scorecard gate (the ICP definition).
- [ ] **Homepage audit** as final verification, then enrich the remaining gaps.
- [ ] **Optional gap-fill:** Parallel Entity Search plus Nano scoring. Eric quotes "$5 per 1,000 requests".

Claimed outputs:
- "reasonably … 85% of somebody's total addressable market"
- The peptide example yielded 70 companies vs. 32 from Prospeo alone. The run covered about 55,000 companies across 3 industries, 39 keywords, and 42 filters.
- The skill is to be posted in Eric's "cold outbound skills" GitHub repo.

### B. Contact waterfall beyond LinkedIn [SmCodMPSDlE]
- Use custom scrapers, Parallel/Exa contact search, and OpenWebNinja (Google-style owner lookup, e.g., "owner of [local business]") before falling back to generic website emails.
- QuickEnrich pulls contacts from website directories, not just LinkedIn. Eric recommends it for local-business owners. [aq5r3_CMh-s]

### C. Silent-filter first list [hxolLxHiydg]
- The first list for every new client is the normal ICP filters plus **"1% head count growth in the last 6 months"** (Prospeo).
- Eric's illustration: from a 50,000-contact TAM, start with the roughly 5,000 at growing companies.
- Other growth filters: any social follower growth, website traffic growth over 6 months, department growth.

### D. Signal tier list [hxolLxHiydg]

| Tier | Signal | Use |
|---|---|---|
| S | Custom trigger (business-specific) | Build your own proprietary signal |
| S | New in role | Run for every client |
| S | Lookalike companies | Pair with a case study |
| A | General growth (headcount, jobs, traffic, followers) | Filter only |
| A | Competitor movements (site, ads, landing pages, UGC) | First line, when relevant |
| A | Customer complaints (GMB, Trustpilot, G2), yours or competitors' | Solve the complaint in the copy |
| A | Job post data | Mine the *description* for problems and tech stack |
| A | Tech stack (BuiltWith, Wappalyzer, job posts) | Displace, integrate, or filter for sophistication (e.g., Triblio or Clearbit installed) |
| A | Website visitors | Score and filter; never mention the visit |
| A | Social activity (posts, engagement, competitor followers) | Filter only |
| B | Department growth | High access and scale, lower effectiveness |
| B | Marketing channel intelligence (ads, posting cadence; via Apify) | Growth filter |
| B | Lawsuits / compliance | Delay; non-predatory tone |
| C | Funding | Filter only; banned in copy |
| C | Search visibility gaps | S-tier only for SEO, Amazon SEO, or ChatGPT-SEO sellers |
| C | Competitor pricing change | Good one-off, not scalable (dropped from A to B to C during the video) |
| D | M&A / PE | Low access; acquirer "already figured it out", acquired company lacks authority |
| D | Layoffs / cost-cutting | "they're not buying anything" |
| D | Product launch | Timing usually missed; you'd rather reach them pre-launch |

Eric's scores:
- General growth: effectiveness "like a seven"; high accessibility and scalability.
- Competitor movements: effectiveness 7, accessibility 5, scalability 5.

### E. Website-visitor hygiene [hxolLxHiydg]
- Score every de-anonymized company and person. If you wouldn't email them in a regular campaign, drop them.
- Cautionary tale: an uncleaned RB2B list led to emailing a CEO's wife. Clay can automate this filter.

### F. "Boring" high-intent workflows [Ct4AUtQnIYE, SmCodMPSDlE]
- **Agentic daily cron:** "find 3 (or 5) new companies per day that [e.g., hired/are hiring their first GTM engineer]". Keep a memory of past suggestions to avoid repeats. Run via Parallel's task/research agent, scheduled in Claude Code, Codex, OpenClaw, or Hermes, and posted to Slack. Then find the sales, marketing, and CEO contacts with Clay or Prospeo.
- **Trade-show sponsors:** ask an agent to find upcoming niche or large events and output the sponsor (and attendee, if available) lists to a sheet. Eric's examples: Dreamforce, Unbound, SaaStr Annual. Enrich contacts in Clay.
- **Clay job-post pull:** search titles "GTM engineer" and "go-to-market engineer" with **limit per company = 1** to get a deduplicated company list. Enrich the job description in the next column.

### G. Cost-cutting via open source [SmCodMPSDlE]
- Use an open-source HTML-to-text library plus an LLM instead of paid scrape integrations (Clay scrape-website, ZenRows) for homepage text.
- DIY tech detection: fetch the site HTML and look for vendor code signatures instead of paying for BuiltWith.
- A local Gemini 4 12B (open-weights) model writes custom variables. It needed light tuning.
- Browser Use Harness handles website research and funnel tests (e.g., checking sales-tax collection at checkout).

## 5. Deliverability / inbox infra notes

- **Onboarding checklist (automated by agent):** [4Kf3CkdvFTY]
  - [ ] Create the sending-platform account (Eric uses SmartLead)
  - [ ] Buy domains
  - [ ] Set up inboxes
  - [ ] Start warmup
  - [ ] Create the signature
  - [ ] Pull the list
- **Domain monitoring loop:** [4Kf3CkdvFTY]
  - Track per-domain sends, total replies, human replies, and bounces.
  - Also run **ZapMail inbox placement tests**. ZapMail has no API for this, so Eric automates the browser.
  - Decision rule:
    - Low reply rate but good placement → give it more time.
    - Placement below threshold or landing in spam → retire the domain.
- **Bounce nuance:** separate **soft bounces** from hard "address doesn't exist" bounces, and **out-of-office** from human replies. Eric's agent found that soft bounces correlated with the reply drop. [4Kf3CkdvFTY]
- **Agentic checks:** reply-rate analysis and bounce checks run daily, hourly, or every 15 minutes via Slack-triggered agents. [SmCodMPSDlE]
- Eric's vault holds skills for inbox infrastructure, "inbox economics", deliverability, and "first principle checks". [4Kf3CkdvFTY]

## 6. Metrics & testing cadence

- **Week-over-week decline diagnosis** (when a client was good two weeks ago and worse now): [4Kf3CkdvFTY]
  - [ ] Deliverability (placement, bounce mix)
  - [ ] Different people or titles?
  - [ ] Different companies?
  - [ ] Custom variables broken or not landing?
  - [ ] Out-of-office vs. human reply mix
- **Auto-research loop, daily or weekly:** have the agent report which titles, industries, and headcounts respond, which messaging they responded to, and what they replied. Spot-check the data yourself afterwards. [SmCodMPSDlE]
- **Goal mode for list builds and campaign setup:** [SmCodMPSDlE]
  1. Plan.
  2. "Ask me 10–15 clarifying questions."
  3. Have the agent write **pass/fail completion criteria**.
  4. Review the criteria.
  5. Run until done. Example criteria: "checked all databases, CSV compiled, columns normalized"; or inboxes attached, list loaded, custom variables audited.
- **Volume claims** (see caveats):
  - "200 to 300 positive responses" [4Kf3CkdvFTY]; described as "per day" in [SmCodMPSDlE]
  - "over 8 million cold emails per month on behalf of our 50 customers" [hxolLxHiydg]

## 7. Tools mentioned

| Tool | How used | Src |
|---|---|---|
| Apollo.io | Cancelled (mostly price). Still recommended for non-technical sales teams wanting all-in-one sequencing and activity tracking | [aq5r3_CMh-s] |
| Prospeo | Best out-of-box company filters, lookalikes, headcount-growth filter. Eric gets limited free access | [aq5r3_CMh-s, hxolLxHiydg] |
| GetLead(s) | Unlimited database, "$500 a month", best email coverage, MCP for Claude Code/Codex. Paid full price | [aq5r3_CMh-s] |
| Blitz API | Unlimited contacts, companies, and now jobs; "basically an exact replica of LinkedIn". Paid full price | [aq5r3_CMh-s, SmCodMPSDlE] |
| QuickEnrich (transcribed "Quick and Rich") | Unlimited; website-directory contacts; good for local businesses. Paid full price | [aq5r3_CMh-s] |
| Parallel.ai | Entity Search lookalikes, task/research agent for daily leads, contact finding | [aq5r3_CMh-s, Ct4AUtQnIYE, SmCodMPSDlE] |
| Exa | Find Similar lookalikes, company and contact search | [aq5r3_CMh-s, SmCodMPSDlE] |
| Ocean.io, DiscoLike | AI company search to fill gaps | [SmCodMPSDlE] |
| OpenMap, D7 Lead Finder | Google Maps-based lists | [SmCodMPSDlE] |
| OpenWebNinja | Owner/contact lookup via search | [SmCodMPSDlE] |
| GPT-5 Nano | Cheap ICP-fit judging at scale | [aq5r3_CMh-s] |
| Clay | Job-post pulls, decision-maker waterfall, visitor scoring. Eric promotes free templates that give credits | [hxolLxHiydg, Ct4AUtQnIYE] |
| BuiltWith, Wappalyzer | Tech-stack signals (Eric suggests a DIY alternative) | [hxolLxHiydg, SmCodMPSDlE] |
| RB2B | Website-visitor de-anonymization | [hxolLxHiydg] |
| Apify | Marketing-channel intelligence scrapes | [hxolLxHiydg] |
| SmartLead | Sending platform and per-domain metrics | [4Kf3CkdvFTY] |
| ZapMail | Inbox placement tests via browser automation | [4Kf3CkdvFTY] |
| Claude Code (Opus 5), Codex | Skills, goal mode, scheduled tasks, orchestration | all |
| Hermes agent ("Dale"), OpenClaw | Slack-tagged agentic crons and research | [Ct4AUtQnIYE, SmCodMPSDlE] |
| Obsidian, ClickUp, WhisperFlow, Fathom, Slack | Company brain, task plans for batch agent execution, voice prompting | [4Kf3CkdvFTY] |
| Browser Use Harness | Open-source browser automation for research and audits | [SmCodMPSDlE] |
| Gemini 4 (12B, open weights) | Local custom-variable generation | [SmCodMPSDlE] |
| Typesense | Eric's internal 8.7M US-company database (clients only) | [aq5r3_CMh-s] |

## 8. Caveats / dated claims to re-validate

- **Platform mismatch:** Eric runs SmartLead + ZapMail. Map his monitoring and placement workflow to Instantly's equivalents before adopting it. Don't assume feature parity. [4Kf3CkdvFTY]
- **Unverified numbers:**
  - "85%" TAM coverage and "70 vs 32" peptide companies are self-reported from a single demo. [aq5r3_CMh-s]
  - QuickEnrich's "866,000" founder contacts comes from a vendor slide; Eric himself says "we actually need to go in here and actually validate some of this data". [aq5r3_CMh-s]
- **Pricing to re-check:** GetLead "$500 a month"; Parallel "$5 per 1,000 requests". [aq5r3_CMh-s]
- **Affiliations:** Eric gets free Prospeo credits. Clay templates are affiliate links that give credits. He says he pays full price for GetLead, Blitz, and QuickEnrich. [aq5r3_CMh-s, hxolLxHiydg, Ct4AUtQnIYE]
- **Model claims are anecdotal ("Eric vibe benchmarking"):**
  - Opus 5 used "8% … instead of 85%" of usage vs. Fable 5.
  - Opus 5 retained "like 90%" of vault knowledge.
  - [4Kf3CkdvFTY]
- **Gemini 4 12B release date:** stated as "June 3rd". Verify the license and quality before using it for custom variables. [SmCodMPSDlE]
- **Subjective tiers:** Eric changed several ranks live (pricing change A→C; search visibility B/C→C). His own advice is to "take this video with a grain of salt". [hxolLxHiydg]
- **Transcription ambiguities:**
  - "Prosper/Prospio/Prospectio/Prospector" = Prospeo
  - "Quick and Rich" = QuickEnrich
  - "Clay Code" (in [SmCodMPSDlE]) likely = Claude Code
  - "open claw" = OpenClaw
  - "Ambit" (in [Ct4AUtQnIYE]) is unclear
  - "Stream 100" = Dream 100
  - Verify tool names and URLs before purchasing.
- **Skills repo:** the "cold outbound skills" GitHub repo and the skills promised in descriptions weren't linked in the transcripts. Locate and review them before installing. [aq5r3_CMh-s, SmCodMPSDlE]

## Source videos
- aq5r3_CMh-s — I cancelled Apollo.io and built this Claude skill instead
- 4Kf3CkdvFTY — 8 Claude Opus 5 Use Cases (so your business grows without you)
- hxolLxHiydg — I Ranked the Best Buying Signal in 2026
- Ct4AUtQnIYE — 3 Boring GTM Strategies But They Generate Leads Daily
- SmCodMPSDlE — The NEW Way to Generate Leads in 2026 (With AI / Claude Code)
