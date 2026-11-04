<!-- distill: batch_04_of_11 | videos: cfXqdbPf0So, JFlMdGEyYoM, RLHzU2_Xl5g, xc7o9iXDF7M, s_EUgLx-esY | model: opus | elapsed_s: 83 -->

# Playbook batch: Claude Code/Codex as the outbound engine (skills, sub-agent personalization, DIY scrapers, email finding, job-description signals)

## 1. Frameworks / mental models

- **The 3 things a cold email campaign needs** [JFlMdGEyYoM]
  1. Infrastructure: domains and inboxes
  2. A list: your ICP
  3. Something to say: copy and offer. Infra is "super easy." Spend your effort on #2 and #3.
- **A skill is an SOP file for the agent.** Build a process once by iterating with Claude, then save it as a skill so it runs the same way every time. You can also import other people's skills instead of learning an API's edge cases yourself. [RLHzU2_Xl5g] [JFlMdGEyYoM]
- **Get buy-in at every step, not three full drafts.** Have the AI propose one element at a time and confirm each before final copy. [JFlMdGEyYoM]
  - Direction: audience → pain → value prop → proof → angle
  - Subject + first line
  - Body / value prop
  - Final copy
- **"Bad AI personalization = bad prompt."** Don't rewrite the prompt by hand. Critique outputs conversationally (e.g., "nobody says X, make it 5th-grade reading level") and let the agent revise the prompt. **Lock the prompt only after 2 consecutive batches come back correct.** [JFlMdGEyYoM]
- **Sub-agents instead of API tokens.** Run ICP filtering, classification, and personalized lines through Claude Code **Sonnet sub-agents** on your flat-rate plan, instead of paid OpenAI/Clay AI calls. [RLHzU2_Xl5g] [JFlMdGEyYoM]
- **Signals get you written off when you name them.** "Saw you're hiring X" and "saw you raised" are table stakes. Use the *insight behind* the signal and never mention the signal itself. [s_EUgLx-esY]
- **Auto research loop** (based on Karpathy's autoresearch repo). The agent runs experiments against one metric (positive reply rate) inside a context file of guardrails. [RLHzU2_Xl5g]
  1. Pull recent campaign results.
  2. Compare vs. baseline.
  3. Re-read the context file (allowed offers, targeting, "don't give services away free").
  4. Change the list filter and/or copy.
  5. Relaunch.
  6. Log the experiment.
  7. Repeat.
- **"Marketing is just a fancy word for testing."** [RLHzU2_Xl5g]
- **Scraper scoping rule.** Before prompting, identify what's constant vs. what changes on the target page (e.g., date params in the URL), and define the exact fields you want. [cfXqdbPf0So]
- **Build local first, then deploy.** Local script and CSV, then trigger.dev (cron) plus Supabase (storage). [cfXqdbPf0So] [xc7o9iXDF7M]
- **Prompting habit:** end build prompts with "ask me 5 (or 10) clarifying questions," and use plan mode first. [xc7o9iXDF7M]

## 2. Copy formulas

**Subject lines** [JFlMdGEyYoM]
- `How {{case_study_customer}} cracked this`
- `question for {{first_name}}`

**First-line options** (the preview text) [JFlMdGEyYoM]
- **Casual question (chosen):** `{{first_name}} quick one, are you running {{channel}} for {{company}} yet or still all {{current_channels}}?`
  - Example: "…TV ads for {company} yet or still all Meta and Google?"
- **Pain insight (the AI's recommended pick):** `The thing about selling {{product_type}} is {{buyer_behavior}}. {{current_channel_A}} {{limit}}, {{current_channel_B}} {{limit}}. {{case_study_customer}} had the same problem.`
  - Example: "…customers research for weeks before they buy, Meta retargeting windows run out, Google gets expensive, Blindster had the same problem."
- **Rejected:** "giving the first 100 {{segment}} brands this week $200…" was dropped as fake exclusivity.

**Body** [JFlMdGEyYoM]
`Most {{persona}} your size are testing {{channel}} in {{year}}. Brands like {{peer_1}} and {{peer_2}} use it to {{outcome}}.`

**AI personalization line** (inserted between the body and the CTA) [JFlMdGEyYoM]
`While {{their_target_customer}} are {{everyday_situation}}, you could run an ad showing {{specific_scene_with_their_product}} {{emotional_payoff}}.`
- Example: "While Texas homeowners are sweating on the couch watching their AC bill climb, you can run an ad showing your crew rolling fresh insulation into a Dallas attic as the thermostat finally drops…"
- Watch for AI tells and ban them: "unwinding on the couch after bedtime," "design-conscious New Yorker."

**Data-driven hook** (from a scraped signal) [JFlMdGEyYoM]
"You've got {{meta_ad_count}} Meta ads live right now. That's the point where most brands start seeing CPA creep from creative fatigue. {{channel}} gives you a fresh channel and fresh inventory."

**CTA** (low friction, offer-led) [JFlMdGEyYoM]
`Want me to drop you a {{$ credit}} link to test it? No card, no call.`

**Follow-ups:** email 2/3 variants were generated but not shown in detail. [JFlMdGEyYoM]

**Copy QA checklist** [JFlMdGEyYoM]
- [ ] First line is specific
- [ ] No em dashes
- [ ] No banned phrases
- [ ] Word counts within limit
- [ ] Spam word check run
- [ ] Spintax created

**Job-signal copy** [s_EUgLx-esY]
- Do not write "I saw you're hiring {{role}}."
- Instead, write to the inferred goal, e.g., "{{upmarket push / compliance need}}."

## 3. Offer / angle patterns

- **Free trial credit as the offer** instead of a demo ask. The vibe.co example was "first $200 of advertising for free," lifted from the prospect's own Meta ads. [JFlMdGEyYoM]
- **Mine a client's own paid-ad offers** (Meta Ad Library) for cold email offers. [JFlMdGEyYoM]
- **Lookalike-of-best-customer campaign.** Name the best customer as proof ("Blindster lookalike"). [JFlMdGEyYoM]
- **"Golden ICP" campaign** as a separate strategy. [JFlMdGEyYoM]
- **Second channel, not a replacement.** "Move 10% of Meta budget to CTV, get a second attribution channel." [JFlMdGEyYoM]
- **Idea-gift personalization.** Show a concrete use case of your product *for their brand*. [JFlMdGEyYoM]
- **Strategy doc output:** 15–25 campaign ideas, each with:
  - name
  - targeting level
  - list filters
  - AI strategy
  - value prop
  - overview
  - some ideas that use no AI at all [JFlMdGEyYoM]
- **Job-description insight → angle** [s_EUgLx-esY]
  - 5 enterprise AEs → upmarket/enterprise push
  - CISO / security engineer roles plus "fortify security / compliant" language → SOC 2 / enterprise compliance need
  - Analyze a whole department's or company's jobs → infer company goals and growth direction

## 4. List-building & enrichment tactics

**ICP onboarding** (the skill asks 12 questions) [JFlMdGEyYoM]
- What they sell
- Single best customer(s)
- Titles
- Headcount (hard min/max?)
- Industries in/out
- Geos
- Triggers
- Disqualified domains (exclude direct competitors)
- Offer
- Lead magnet
- …(remaining questions not shown)

**Triggers the agent proposed for the D2C/CTV ICP** [JFlMdGEyYoM]
- Recent funding
- Recent hire
- Heavy Meta/Google ad spend
- Shopify or Klaviyo installed
- App-install campaigns / app on the App Store
- Recent product launch

**Voice-driven list pulls with the Prospeo skill** [RLHzU2_Xl5g]
- Example request: "1,000 marketing leaders, US, 10–100 employees, raised in last 180 days, verified emails required"
- The search endpoint doesn't return emails; use the **enrich endpoint**, which also returns a company description.
- Pass that description to a **Sonnet sub-agent** to classify ICP fit (e.g., "is this SaaS?") with reasoning, then filter.

**ICP prompt builder loop.** Iterate until companies are verifiably in-ICP. The agent also self-suggested dropping B2B brands from a D2C campaign. [JFlMdGEyYoM]

**List sources in the skill pack** [JFlMdGEyYoM] [RLHzU2_Xl5g]
- Prospeo
- Blitz
- DiscoLike
- Google Maps scraper
- Pre-built lists: "12 million US businesses," a SaaS company list, all US zip codes

**DIY email finder (cheapest-first waterfall)** [xc7o9iXDF7M]
1. Input: first name, last name, company domain.
2. Generate the 10 most common permutations (`first@`, `firstlast@`, `firstl@`…), most common first.
3. Validate each with MillionVerifier. **Accept `ok` only**; reject invalid, catch-all, and unknown.
4. Fall back to Prospeo (double-validated via BounceBan, so it can cover catch-alls), then Blitz API.
5. Test on 50 rows, review, then run the full 1,000.
6. Store every found email in Supabase so you never pay twice.
- **Gotcha:** the marketing domain can differ from the email domain (slack.com vs slackhq.com).

**Job data pipeline** [s_EUgLx-esY]
1. Pull open jobs and full descriptions from Clay (mostly LinkedIn-sourced), Apify (Indeed scraper), or Parallel.ai. PredictLeads is an API alternative.
2. **Build the extraction prompt.**
   - Pick 10 relevant job descriptions.
   - Record a Loom narrating what's interesting in each.
   - Use the transcript to build the prompt.
   - Validate the outputs yourself.
3. **Build the messaging prompt.**
   - Manually write 3–5 (up to 10) emails from the extracted insights.
   - Have AI build the prompt using those examples.
   - Review 10 outputs before scaling.

**Custom public-data scraper (SEC example)** [cfXqdbPf0So]
- Targets:
  - Form 144: form, filing entity/person, plus linked detail
  - Form 4: filer entity/person, stock/security type
- Date filters live in URL params, so the scraper can backfill and then run daily.
- Build spec used:
  1. Backfill into a local CSV and confirm fields.
  2. Create separate Supabase tables per form.
  3. Schedule a trigger.dev daily cron.
  4. Send a Slack notification with the count of new records.
  5. Do a test run on trigger.dev.
  6. Pipe into Clay.
- The outreach angle for SEC data is **not stated** in the video. Define it before building.
- **Fallback if the site blocks hosted scraping:** OpenClaw (has cron jobs) or Browser Use (agentic browser scraping).

## 5. Deliverability / inbox infra notes

- **Infra stack in the skill:** Dynadot (domains) + Zapmail (inboxes), auto-uploaded to SmartLead with settings configured. The skill checks that infra exists before anything else. [JFlMdGEyYoM]
- **Catch-all domains** give no SMTP handshake, so you can't trust them. Sending to them without a specialized catch-all validator raises bounce rate. Accept only `ok` status from MillionVerifier. [xc7o9iXDF7M]
- **Skills in the pack:**
  - spam word checker
  - spintax creator
  - deliverability test
  - a "which domains are landing in spam" report process [JFlMdGEyYoM] [RLHzU2_Xl5g]

## 6. Metrics & testing cadence

- **Optimize for positive reply rate**, measured against a baseline. Auto research compares each experiment to baseline daily. [RLHzU2_Xl5g]
- **Auto research at a customer:** dedicate **"10% of their overall volume"** to it. For one customer it is "starting to outperform the human-written campaigns." [RLHzU2_Xl5g]
- **Personalization prompt:** keep iterating until **2 consecutive batches** are correct, then lock it and run on the full list. [JFlMdGEyYoM]
- **Review 10 before scaling** any prospect-facing AI prompt. [s_EUgLx-esY]
- **Pilot 50 rows**, then the full list. [xc7o9iXDF7M]
- **Copy grader skill:** trained by having Claude predict campaign success from titles and copy, then check actual results, over "definitely more than a thousand" campaigns. [RLHzU2_Xl5g]
- **Positive-reply learning skill:** analyzes positive replies to inform new copy. [JFlMdGEyYoM]
- **Experiment design skill** is included in the pack. [JFlMdGEyYoM]
- **Skepticism about signal attribution:** a positive reply on a signal email may be because the prospect gets little email, or would have replied anyway. Eric promised a future video on measuring which signals truly work. [s_EUgLx-esY]

## 7. Tools mentioned

| Tool | How used | Source |
|---|---|---|
| Claude Code (CLI) / Codex app | Builds scrapers and pipelines, runs skills, sub-agent personalization and filtering | all |
| Claude Sonnet sub-agents ("Sonnet 4.6") | ICP classification and personalized lines on the flat-rate plan | [RLHzU2_Xl5g] [JFlMdGEyYoM] |
| Growth Engine X "cold outbound skills" GitHub repo | Free skill pack: kickoff, ICP, strategy, copy, infra, list building, spam check, spintax, upload, reply learning, deliverability test, experiment design, personalization sub-agent. Install by pasting the repo link into Claude Code/Codex | [JFlMdGEyYoM] [RLHzU2_Xl5g] |
| Wispr Flow ("WhisperFlow") | Voice prompting and critiquing AI outputs | multiple |
| Prospeo | Search (no emails), enrich (emails + company description), email-finder fallback | [RLHzU2_Xl5g] [xc7o9iXDF7M] [JFlMdGEyYoM] |
| Blitz API | List building, email-finder fallback | [xc7o9iXDF7M] [JFlMdGEyYoM] |
| DiscoLike | List building (lookalikes) | [JFlMdGEyYoM] |
| Google Maps scraper | Local-business lists | [JFlMdGEyYoM] [RLHzU2_Xl5g] |
| MillionVerifier | Fast, cheap validation of permutations | [xc7o9iXDF7M] [JFlMdGEyYoM] |
| mailtester.ninja | Cheap validation alternative, "pretty good" accuracy but slower | [xc7o9iXDF7M] |
| LeadMagic, Icypeas ("ICPs"), BetterContact, FullEnrich | Paid finders for harder cases and catch-alls | [xc7o9iXDF7M] |
| BounceBan | Catch-all validation (behind Prospeo) | [xc7o9iXDF7M] |
| Clay | Job data, destination table for scraped signals | [s_EUgLx-esY] [cfXqdbPf0So] |
| Apify | Indeed job scraper, Meta Ad Library scrape | [s_EUgLx-esY] [JFlMdGEyYoM] |
| Parallel.ai | Jobs data and web-agent enrichment | [s_EUgLx-esY] [xc7o9iXDF7M] |
| PredictLeads | LinkedIn jobs via API | [s_EUgLx-esY] |
| OpenRouter / DeepInfra / vast.ai | Cheaper models or self-hosted GPUs for high-volume job-description parsing | [s_EUgLx-esY] |
| trigger.dev | Hosted cron jobs for scrapers and finders | [cfXqdbPf0So] [xc7o9iXDF7M] |
| Supabase | Storage for scraped records and your own email database | [cfXqdbPf0So] [xc7o9iXDF7M] |
| Slack | Run-success notification with record count | [cfXqdbPf0So] |
| OpenClaw, Browser Use | Cron plus agentic browser scraping fallback | [cfXqdbPf0So] |
| Dynadot, Zapmail | Domains and inboxes | [JFlMdGEyYoM] [RLHzU2_Xl5g] |
| SmartLead | Eric's sequencer (skills upload campaigns there) | [JFlMdGEyYoM] [RLHzU2_Xl5g] |
| Karpathy autoresearch repo | Autonomous experiment loop | [RLHzU2_Xl5g] |
| Loom | Narrate job-description review to create a prompt-building transcript | [s_EUgLx-esY] |

## 8. Caveats / dated claims to re-validate

**Sequencer mismatch**
- The skills target **SmartLead**. For Lorenzo's Instantly setup, the upload, infra, and auto-research skills need adapting to the Instantly API. [JFlMdGEyYoM] [RLHzU2_Xl5g]

**Cost / usage claims**
- "100,000" personalized lines "in one day on a $200 a month Claude Code plan," about "$70 in AI tokens," "fit within my daily limit." Plan limits and ToS change, so re-check before relying on sub-agents for bulk generation. [JFlMdGEyYoM]

**Agency scale claims**
- "200 to 300 positive responses per day" [JFlMdGEyYoM]
- "200 positive responses per day" [xc7o9iXDF7M]
- "about 8 million cold emails per month" [s_EUgLx-esY]

**Other quoted numbers**
- "over 20 million emails" in Eric's own database [xc7o9iXDF7M]
- Codex ran the SEC build for "2 hours" unattended and produced "thousands and thousands of rows" [cfXqdbPf0So]
- Auto research on 10% of volume, "starting to outperform" in one account. Single anecdote, no numbers. [RLHzU2_Xl5g]

**Copy framing**
- "Testing CTV in 2026" is year-specific framing, and the vibe.co example is illustrative (vibe.co is not Eric's client). [JFlMdGEyYoM]

**Transcription ambiguities to verify**
- "Prospector/Perspio/Prospect.io" is most likely Prospeo.
- "Superbase" = Supabase; "Appify" = Apify.
- "Zapier" in the domain-setup skill is likely Zapmail.
- "Amplify" for Meta Ad Library scraping is likely Apify.
- "Parallel Dots AI / parallel.di" = Parallel.ai.

**Other checks**
- Repo contents: the skill count differs between videos ("four main skills" in [RLHzU2_Xl5g] vs. the full pack in [JFlMdGEyYoM]). Audit the repo before use and review any third-party skill before installing.
- SEC scraping: respect SEC fair-access rules (declared User-Agent, rate limits).

## Source videos
- cfXqdbPf0So — Automatically Scrape SEC.gov EVERY Day
- JFlMdGEyYoM — Copy These Claude Skills, They'll Blow Up Your Business
- RLHzU2_Xl5g — Claude Code Just Changed Lead Generation Forever (Tutorial + Use Cases)
- xc7o9iXDF7M — Find Anyone's Email With Claude Code
- s_EUgLx-esY — How to Use Hiring Signals for Cold Email in 2026
