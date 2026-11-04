<!-- distill: batch_03_of_11 | videos: m_ypRhwJakw, qw0xdTtzK1w, HBT0ogk49jo, SDTyFOI5Vdo, _HWlY5Cdel4 | model: opus | elapsed_s: 78 -->

# Playbook batch: Claude Code + Clay pipelines for TAM-first, signal-driven, self-optimizing outbound

## 1. Frameworks / mental models

- **Split the work by cost and exposure** [m_ypRhwJakw][SDTyFOI5Vdo]
  - *Claude Code:* cheap or free work that isn't prospect-facing, run across the whole TAM (headcounts, scrapes, CTA detection, pricing, tech). Store results in Supabase, or a CSV to start.
  - *Clay:* "final mile" prospect-facing work (Claygent research, AI lines, QA, routing, pushing to the sender). Clay gives observability per lead and runs "on rails".
  - Rule: never let "vibe-coded" orchestration push leads into live campaigns. Each run is "one-time setup in Claude, recurring jobs on rails" (trigger.dev + Clay).
- **Build the whole TAM up front, then run experiments** [qw0xdTtzK1w][SDTyFOI5Vdo]
  - Letting the agent make "game time decisions" (e.g., hunting for new-product launches) gave poor coverage and small samples.
  - Enrich every conceivable data point once. Refresh monthly.
  - Knowing the full TAM tells you exactly how much runway each winning campaign has.
- **"The list is the message"** [qw0xdTtzK1w]: derive campaign angles from data points that reveal pain. Combine them with overall value-prop campaigns.
- **Auto-research loop (Karpathy-inspired)** [qw0xdTtzK1w]: optimize for **positive reply rate**.
  1. Ingest past campaigns: copy, leads, companies, and positive vs negative responders.
  2. Propose the next experiments.
  3. Human approves.
  4. Launch.
  5. Review weekly.
- **Context layer first** [qw0xdTtzK1w]: without rich company context, the loop fails. Checklist:
  - [ ] Enter the website so the agent auto-learns the company and offer
  - [ ] Generate an auto onboarding draft
  - [ ] Record a voice-memo "walk and talk" dump about the dream campaigns and ICP, transcribe it, and feed it in
  - [ ] Produce files: `icp.md`, `case-studies.md`, `value-prop.md`, `problem-statement.md`
- **ICP prompt loop** [_HWlY5Cdel4]
  1. Have Claude draft an ICP-fit prompt.
  2. It shows 10 results. You correct them.
  3. Repeat until **2 consecutive runs are all correct**.
  4. Only then run it on the full list.
- **Agentic cron jobs** [HBT0ogk49jo]: scheduled jobs with an agent in the loop, so the job can diagnose and fix issues it hasn't seen before. This beats rigid if/then code.
- **Winner → autopilot refill** [SDTyFOI5Vdo]: once a campaign wins, pipe new TAM leads in daily. About **"5% of our overall volume"** goes to tests trying to beat the baseline.

## 2. Copy formulas

- **Structure** [SDTyFOI5Vdo]: about 3 lines. AI first line + AI second line + fixed CTA.
- **Bottom-of-funnel question line** (Claygent reads the site) [m_ypRhwJakw]
  - Template: `When someone wants to know {specific BOFU question about their product}, they can immediately get a walk-through instead of searching the site or talking to a rep.`
  - Example: "…how the platform handles employee performance evaluations in relation to company goals…"
- **Pain question with a niche variable** [HBT0ogk49jo]
  - Template: `Are the usual paid channels getting more expensive when you're trying to reach {buyer persona evaluating {their category}}?`
  - Example: "…buyers evaluating non-alcoholic craft beer?"
- **"Three ideas" email** [HBT0ogk49jo][SDTyFOI5Vdo]
  - Template: `I spent a little time with {Company} and had three ideas for how {our channel/offer} could fit: {idea1} / {idea2} / {idea3}`
  - Eric calls "ideas" "one of my favorite campaigns" [SDTyFOI5Vdo].
- **Persona × signal copy** [qw0xdTtzK1w]: write copy per data combination, e.g., "VP Sales + has demo button + no sales team → say X". The repo shows 3–5 sample contacts with full data so a human writes the copy.
- **CTA lock** [qw0xdTtzK1w]: fix the CTA type (meeting *or* lead magnet). AI may rephrase it but never change it. This prevents campaigns like "giving the software away for free".
- **Custom-variable prompting** [HBT0ogk49jo]: before bulk generation, hand-write **3 fully rendered example emails** with variables filled in (subject + body + lead data). The AI imitates these instead of needing a prompt per variable.
- **Follow-ups:** no specific formulas in this batch.

## 3. Offer / angle patterns

- **Signal-based relevance for high-value accounts** [_HWlY5Cdel4]: transformation programs, earnings/guidance, M&A (bolt-ons, divestitures, minority stake sales, sale rumors), personnel changes, plant closures, SEC settlements, regulatory pressure. Premise: "generic emails aren't going to land."
- **Sales-motion angles for B2B SaaS** [m_ypRhwJakw][qw0xdTtzK1w]
  - Book-demo / contact-sales CTA present?
  - Pricing floor and ceiling, enterprise tier, free trial
  - Sales and marketing leader vs IC ratios (e.g., "sales leader but no ICs")
  - Has a GTM engineer? Running Meta/Google ads? Case studies listed?
- **Hiring signal** [HBT0ogk49jo]: "company that hired their first GTM engineer" → find the VP Sales → draft an email.
- **SEC trigger leads** [HBT0ogk49jo]: Form 144 (insiders about to sell securities) and Form 4 filers, scraped daily. Useful for wealth/finance offers.
- **Large-TAM offer example** [SDTyFOI5Vdo]: a PR firm (press features in Forbes, Business Insider, etc.). A broad TAM is what enables high volume.
- **Agency acquisition offer (Eric's own)** [qw0xdTtzK1w][SDTyFOI5Vdo]: "we always launch our first campaign for somebody for free," targeting B2B companies "doing over $3 million in revenue" with a sales team short on leads. Possible model for Advero's own outbound.

## 4. List-building & enrichment tactics

**Pipeline template** [SDTyFOI5Vdo]:
1. **Source:** Prospeo + Blitz API, pulled via Claude Code (it handles pagination). Tag each lead's source.
2. **Store:** Supabase with indexed columns, a `processed` boolean, `processed_at`, raw JSON, email source, and last-validated date.
3. **Email waterfall:** a Supabase edge function runs **hourly** on new contacts. Order: internal DB ("over 20 million emails") → SmartLead Email Finder → Prospeo API → "ICPs" (unclear provider name). Then Million Verifier validates **everything**.
4. **Push:** a daily trigger.dev job sends unprocessed leads for the client to a Clay webhook **25 at a time** and flips `processed=true`.
5. **Clay:** clean domain/company, add LinkedIn description, last-mile email finding, HubSpot update, target-customer AI, first and second lines, then route by headcount × title × industry (50 campaigns in this case).
6. **Send:** push to SmartLead. For Advero, swap in Instantly [qw0xdTtzK1w, which mentions loading into both].

**Other tactics:**
- **Free website enrichment** [m_ypRhwJakw][qw0xdTtzK1w]
  - The open-source "HTML to text" library pulls homepage text. Keyword-match CTAs ("book a demo", "watch a demo", "contact us", "get a quote").
  - Find the pricing page through the sitemap and scrape it.
  - Process with a local small model ("Gemma 4, 12B") for lowest/highest USD per month, enterprise tier, and free trial.
  - This replaces ZenRows, Clay's scrape-website integration, and Claygent for these tasks.
- **Clay derived data points** [m_ypRhwJakw][qw0xdTtzK1w]: business type, growth stage, pattern tags, primary offerings, how they make money. Use them for the base company list.
- **Batch LLM processing** [qw0xdTtzK1w][HBT0ogk49jo][_HWlY5Cdel4]
  - GPT-5 Nano via the Batch API for bulk classification and custom variables.
  - Anthropic Batch API for reading earnings reports and SEC filings.
- **Sub-agents on the plan instead of paid tokens** [_HWlY5Cdel4]: prompt "using Sonnet task sub agents, go do this research" for public-web research (plant count, geographic spread, reference customers, announced personnel changes). One run used 284 parallel agents, one per company.
- **Deep web research** [_HWlY5Cdel4]: parallel.ai (like "a souped-up ClayGen") for transformation and investment signals.
- **LinkedIn freshness** [_HWlY5Cdel4]: a RapidAPI LinkedIn endpoint for job changes, tenure, past experience, and "worked in senior leadership at another TAM company."
- **Ads data** [qw0xdTtzK1w]: Apify MCP.
- **Niche databases** [HBT0ogk49jo]: have the agent find and scrape directories, Chambers of Commerce, government/SEC sites, then set up a daily cron scrape.
- **Provider discovery** [qw0xdTtzK1w][_HWlY5Cdel4]: ask Claude "what's a good data provider for X?" and check Clay's docs on what each provider does.
- **Daily "5 awesome leads" job** [HBT0ogk49jo]: signal + persona → find contacts (Prospeo/LeadMagic/etc.) → draft email. Supplies high-touch campaigns alongside automated ones.

## 5. Deliverability / inbox infra notes

- **Hard gate:** no email enters the sender unless Million Verifier approved it [qw0xdTtzK1w][SDTyFOI5Vdo].
- **Daily agentic checks** [HBT0ogk49jo]
  - [ ] Campaigns with high bounce rate → revalidate leads
  - [ ] Low "leads not started"
  - [ ] Day-over-day reply-rate drop → find likely spam-flagged keywords and vary them
  - Claimed result: "1,400 emails… four responses" → after keyword removal, "2,000 emails and getting 24 responses".
- **Scheduling:** run Supabase→Clay pushes at 2 a.m. to respect rate limits [m_ypRhwJakw].
- **Dedupe:** use the `processed` flag and track who was contacted, so no one is retargeted before the TAM is exhausted [SDTyFOI5Vdo][qw0xdTtzK1w].

## 6. Metrics & testing cadence

- **North-star metric:** positive reply rate [qw0xdTtzK1w].
- **Weekly loop** [qw0xdTtzK1w]: every Friday, an automation (Codex automation or Claude Code routine) reviews performance, proposes next tests, and presents copy for approval before pushing. Keep a human in the loop.
- **Test budget:** about 5% of volume on challengers vs the baseline [SDTyFOI5Vdo].
- **Agent self-QA** [HBT0ogk49jo]: after bulk setup, prompt "use another agent to check its own work, create tasks to fix it, then present to me".

**Claimed numbers:**

| Claim | Video |
|---|---|
| "200 to 300 positive responses every day" across customers | [m_ypRhwJakw][qw0xdTtzK1w][HBT0ogk49jo] |
| "over 50 customers" | [qw0xdTtzK1w] |
| One campaign: "12,000 contacts… 37 positive replies" | [m_ypRhwJakw] |
| Auto campaigns "20.71 replies per 1,000" vs "10.71 replies per 1,000" (Apr 6–17) | [qw0xdTtzK1w] |
| Pathos PR: "over 80 positive responses per day"; "over 11,000 leads" in "a little bit over a year"; "tens of thousands of emails every single day"; Supabase "over 5 million records" | [SDTyFOI5Vdo] |
| Automated setup of about 15 campaigns × 1,000 leads in "about 20 minutes" | [HBT0ogk49jo] |
| TAM of about 300 companies (284 ICP-fit), "close to 7,500 signals"; done in 2 days vs a quoted 3-week timeline | [_HWlY5Cdel4] |
| Pre-automation: "three full-time people" downloading Apollo CSVs into Clay | [SDTyFOI5Vdo] |
| Refill system recommended "even if you're only sending 500 to 1,000 emails a day" | [SDTyFOI5Vdo] |

## 7. Tools mentioned

| Tool | How used | Source |
|---|---|---|
| Claude Code / Codex | Build the TAM, scrapes, Supabase setup, edge functions, sub-agent research, weekly routines | all |
| Clay (Claygent, derived data points, webhooks) | Company source, final-mile AI lines, QA, routing, push to sender | [m_ypRhwJakw][SDTyFOI5Vdo][qw0xdTtzK1w] |
| Clay "Terracotta" (upcoming) | Build Clay tables/workflows from prompts | [m_ypRhwJakw] |
| Browser Use harness + Eric's open-source repo | Browser automation that builds Clay tables | [m_ypRhwJakw] |
| Supabase | TAM store, `processed` flags, hourly email waterfall | [m_ypRhwJakw][SDTyFOI5Vdo] |
| trigger.dev | Daily Supabase→Clay webhook batches | [SDTyFOI5Vdo] |
| SmartLead (API, Email Finder) | Sender; reply-rate pulls; email finding | multiple |
| Instantly | Alternate sender loaded by the repo | [qw0xdTtzK1w] |
| Prospeo | Contact lists (new filters) + email API | multiple |
| Blitz API | Bulk LinkedIn data, headcounts, leader counts ("almost all you can eat plan") | [m_ypRhwJakw][SDTyFOI5Vdo][_HWlY5Cdel4] |
| Million Verifier | Mandatory validation gate | [qw0xdTtzK1w][SDTyFOI5Vdo] |
| HTML-to-text library | Free homepage/pricing text for CTA and pricing detection | [m_ypRhwJakw][qw0xdTtzK1w] |
| Gemma 4 (12B, local) | Free local classification and extraction | [m_ypRhwJakw] |
| GPT-5 Nano Batch API | Cheap bulk AI processing and custom variables | [qw0xdTtzK1w][HBT0ogk49jo] |
| Anthropic Batch API | Reading earnings reports and SEC filings | [_HWlY5Cdel4] |
| RapidAPI (LinkedIn endpoint, earnings API) | Job changes and experience; earnings data | [qw0xdTtzK1w][_HWlY5Cdel4] |
| Apify (MCP) | Ads data, scrapes | [qw0xdTtzK1w][_HWlY5Cdel4] |
| parallel.ai | Deep web research; free tier replaces Claude web fetch | [_HWlY5Cdel4] |
| OpenClaw | Agent reachable via WhatsApp/Slack, shared team skills and memory, agentic cron jobs | [HBT0ogk49jo] |
| Obsidian | Knowledge vault fed by daily Slack and call-context syncs | [HBT0ogk49jo] |
| LeadMagic, "ICPs" | Contact finding | [HBT0ogk49jo][SDTyFOI5Vdo] |
| HubSpot | CRM update per send from Clay | [SDTyFOI5Vdo] |
| Eric's cold-outbound skills repo; auto-research repo | Pre-built agent skills; experiment loop | [HBT0ogk49jo][qw0xdTtzK1w] |

## 8. Caveats / dated claims to re-validate

- **All result numbers are self-reported by the agency, on their own customers' campaigns.** Treat them as directional, not benchmarks. [all]
- **The 20.71 vs 10.71 comparison** covers about 2 weeks and one enterprise customer; the control/segment makeup isn't described [qw0xdTtzK1w].
- **"$200/mo Claude plan ≈ $3,000–$5,000 of tokens"** is attributed to "some people are estimating". Also check whether heavy sub-agent use for bulk enrichment fits Anthropic's plan terms [_HWlY5Cdel4].
- **RapidAPI "rent fake LinkedIn profiles"** endpoint carries LinkedIn ToS, legal, and reliability risk. Review before adopting [_HWlY5Cdel4].
- **Names and details to verify:**
  - "Gemma 4 12B": confirm the model and size exist [m_ypRhwJakw]
  - "Codex 5.5" [HBT0ogk49jo]
  - Clay "Terracotta" launch status [m_ypRhwJakw]
  - parallel.ai free-tier limits ("three concurrent requests") [_HWlY5Cdel4]
  - Blitz API pricing [SDTyFOI5Vdo]
  - The "ICPs" provider (likely transcription noise) [SDTyFOI5Vdo][HBT0ogk49jo]
- **Eric's pipeline is built around SmartLead.** Map the steps to Instantly (API upload, custom variables, sender assignment) before reusing them.
- **The Clay-table-building repo** is described as "trained on all my data" and expected to be obsolete within "a month or two" [m_ypRhwJakw].
- **Fully autonomous send** exists internally but is intentionally *not* in the public repo. Keep human approval [qw0xdTtzK1w].
- **SEC Form 144/Form 4 targeting:** check compliance and suitability for finance-related outreach [HBT0ogk49jo].

## Source videos

- m_ypRhwJakw — Claude Code + Clay.com Destroys Any Marketing Team
- qw0xdTtzK1w — Claude Code + Karpathy Destroys Every Lead Gen Agency
- HBT0ogk49jo — Openclaw Just Changed Lead Generation Forever (Tutorial + Use Cases)
- SDTyFOI5Vdo — Claude Code + Clay.com = Unlimited Qualified Leads
- _HWlY5Cdel4 — Reading Investor Filings with AI for Cold Email
