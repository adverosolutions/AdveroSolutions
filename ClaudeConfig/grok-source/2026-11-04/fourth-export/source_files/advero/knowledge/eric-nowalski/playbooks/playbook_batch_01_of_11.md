<!-- distill: batch_01_of_11 | videos: gKh33_2MXmA, -LjvwKOIH9Y, qmi5B-N3Ev8, H-dot6onaIw, 01jxZN2ZNsc | model: opus | elapsed_s: 93 -->

# Playbook batch: Agent-run cold email ops (Grok Bot + Clay CLI), cheap layered data, and 5-level deliverability

> Transcription note: product names are phonetic in the source. Likely mappings: Grockbot/Grok Bot → **Grok Bot** (Cursor/xAI), Superbase → **Supabase**, Smartle → **Smartlead**, Prospio → **Prospeo**, Zenrose → **ZenRows**, Appify → **Apify**, Claggent → **Claygent**, Wapalizer → **Wappalyzer**, Aexa → **Exa**, Hyper Tide → **Hypertide**. "Mult Sets", "Prospector", "Get Leads" and "Quick Enrich" are unclear, so verify the exact vendor before buying.

---

## 1. Frameworks / mental models

- **3-bucket diagnosis.** Every campaign problem is one of: **Infra** (how we send), **List** (who we send to) or **Offer/Copy** (what we say). Debug in that order. [H-dot6onaIw] [-LjvwKOIH9Y]
  - Deliverability and list are "hard science". Once both check out, put all your effort into the offer and its framing. [H-dot6onaIw]
- **Campaigns work quickly or they don't.** Positive replies should arrive fast. The slow part is everything after the reply: booking, no-shows, ICP fit, sales process. If the campaign fails, radically change the offer. [H-dot6onaIw]
- **5 pillars of a cold-traffic offer** (checklist): [H-dot6onaIw]
  - [ ] **Make-money** offer. If it's save-time or save-money, the claim must be about "80–90%". Nobody moves for 10%.
  - [ ] **Paired with a relevant signal.** Example: a parking-lot paver targets only lots that look bad on Google Maps, not every restaurant.
  - [ ] **Relevant case study** from a lookalike company.
  - [ ] **Easy next step** to say yes to. Example: a free dental sample.
  - [ ] **Not Google/ChatGPT-able.** Reframe commodity services, e.g. bookkeeping becomes a bookkeeping + tax "strategy review".
- **Personalization bar.** Write what you'd say after 10 minutes of manual research on the company. Never "loved your website" or "saw you've been CEO for 2 years". [H-dot6onaIw]
- **Agent onboarding in 3 steps:** [01jxZN2ZNsc]
  1. Tool access (OAuth plugins, API keys).
  2. Company context (SOPs, a skills repo in GitHub).
  3. Ability to act, plus a daily loop so it takes more work each day.
- **An autonomous account needs 4 things to stay alive:** [gKh33_2MXmA]
  1. Enough leads in the campaign.
  2. High-quality AI content (3 AI-generated points per email).
  3. Volume kept up.
  4. Deliverability kept high.
- **Always be testing.** Don't treat anyone's rules as law. [H-dot6onaIw]
  - Email 1 gets most positives "99% of the time", but one client's email 2 won even after the two were swapped.
  - Test images vs plain text by positive replies, not by "seen".
- **The offer is the multiplier.** "Cold email absolutely still works. You just need an offer that can really rip." [-LjvwKOIH9Y]

## 2. Copy formulas

**Opener / breakup: "should I ask someone else"** [gKh33_2MXmA] [qmi5B-N3Ev8]
- Template: `Hey {{first}}, let me know if I should reach out to {{peer_1}} or {{peer_2}} about this instead.`
- Use it as the first line **or** as the breakup line. Never both in the same sequence. [qmi5B-N3Ev8]
- Only 1 of 6 variants uses it in the Pathos campaign. [gKh33_2MXmA]
- QA before sending:
  - [ ] The peer is not the recipient (avoid "Hey Kareem, should I reach out to Kareem").
  - [ ] The peer still works there.
  - [ ] The peer is at a similar role and seniority. [qmi5B-N3Ev8]

**"Creative Ideas" body (called the best-performing campaign across clients)** [qmi5B-N3Ev8]
- Claimed best performer for HubSpot, Reddit, Clay, Instantly and ClickUp.
- Template: `{{opener}}. A few ways we'd help {{company}} if we were in charge:` followed by **3 bullets**. Each bullet is AI-generated from the company description and the recipient's job title.

**"AI Specificity" body** [qmi5B-N3Ev8]
- One AI sentence on exactly how you'd help this specific company.

**Case-study body** [H-dot6onaIw]
- Template: `We {{result}} for {{lookalike_company}}. Bet we could do the same for {{company}}. Want to talk?`

**Reframe commodity offers** [H-dot6onaIw]
- Example: "The IRS did a test where they sent one tax return to 20 different firms and 19 different strategies came back… we'll look and see if we can uncover more savings."

**Short format** [-LjvwKOIH9Y]
- The $50k offer's email was **3 sentences**, with **20 spintax variants of the subject line** and spintaxed unsubscribe messaging. The copy itself was not shared.

**Compliment line** [gKh33_2MXmA]
- An AI-generated compliment about the business, built from the enriched company description, used in a Clay CLI demo flow.

**Spintax rules** [H-dot6onaIw]
- Ask for "**word-level spintax**" so you get about 3 synonym options per word. A plain "spin this" request only swaps one word.
- Spin the greeting, **signature** and **unsubscribe line** too.

**Positive-reply follow-up framework (4 touches)** [-LjvwKOIH9Y]
1. **Fast reply.** Answer their question, then: `I'm available {{time_1}} or {{time_2}}, or if it's easier, grab a time here: {{cal_link}}.` Offer both because some people are offended by a bare link and others only book via a link.
2. **+1 day:** `I lost both of those times. Want to book via {{cal_link}}, or I'm free {{time_3}} / {{time_4}}?` This comes from Oren Klaff and signals scarcity instead of "just following up".
3. **Touch 3:** an AI-researched, company-specific line on why the call is worth their time, plus new times.
4. **Touch 4:** `Lost those times. Another time, or {{cal_link}}?`
5. Then hand off to a commissioned warm caller.

## 3. Offer / angle patterns

- **Signal-paired angles** (each has a data playbook in §4): [qmi5B-N3Ev8]
  - new in role
  - department hiring surge
  - tech installed
  - their case studies
  - their Facebook ads
  - keywords on their website (e.g. SOC 2)
  - job-post language (e.g. "cold calling")
  - funding
  - LinkedIn post content
  - LinkedIn engagers on competitor, partner or topic posts
  - pricing page details
- **New-in-role: new hire vs promotion.** Detect which one applies and change the message accordingly. [qmi5B-N3Ev8]
- **Order-of-magnitude CAC comparison.** Dental free-sample example: form-fill CAC of "$300" on Facebook vs "$40" via cold email. [H-dot6onaIw]
- **Affiliate / pay-per-attended-call blitz.** Used only because the offer was exceptional. Eric says "we never do performance deals". [-LjvwKOIH9Y]
- **Warm-traffic offers.** Compensate with tight signal-based lists ("signal-based warm emailing"). [-LjvwKOIH9Y] [H-dot6onaIw]

## 4. List-building & enrichment tactics

**Where do these people show up?** [H-dot6onaIw]
- SaaS, finance, professional services → LinkedIn.
- Local businesses → Google Maps.
- Weird niches (e.g. peptide manufacturers) → AI search tools: DiscoLike, Ocean.io, Apollo, Parallel, Exa.

**Vendor selection test (Sales Nav as source of truth)** [H-dot6onaIw] [-LjvwKOIH9Y]
1. Have AI build a Sales Navigator URL, e.g. "CEOs, 11–50 employees, marketing services, US".
2. Scrape it with the Harvest API on Apify, "$0.004 per lookup". [H-dot6onaIw]
3. Compare each vendor's output against it and keep whichever is closest.
- Eric's test: 10,000 Sales Nav leads, no single vendor was perfect, but layering vendors gave the best coverage. [-LjvwKOIH9Y]

**Buy each vendor for one specific job** [H-dot6onaIw] [-LjvwKOIH9Y]

| Vendor (as heard) | Claimed strength |
|---|---|
| Blitz API | Closest to LinkedIn data; job postings |
| Prospector / Prospeo | Best filters out of the box; company enrich incl. Wappalyzer tech, revenue, funding; re-enrich is free |
| Quick Enrich | Local and non-LinkedIn contacts |
| Get Leads | Bulk download, mobile numbers, MCP server |
| "Mult Sets" | Email data graded A–F (A = sent to and got open/reply; B = sent, no bounce) |
| LeadMagic | Validation + catch-all. "Tested 500 of our most recent positive replies… would have lost 80 of them" without it [-LjvwKOIH9Y] |

**Cheap email-finding waterfall** [H-dot6onaIw]
1. Generate about **6 common permutations** (first@, first.last@, flast@, …) and validate them with LeadMagic, including catch-all. Claim: "60–70%" of emails found by guessing.
2. Only the misses (unusual pattern or catch-all domain) go to paid finders: LeadMagic finder, Prospeo, ICPs.
3. Benchmark: "if you're paying anything higher than 2 cents per contact including the company, you're overpaying".

**Nearly free company data** [H-dot6onaIw]
- Google Maps scraper on RapidAPI: "$100 a month… 3 million requests".
- People Data Labs: the full LinkedIn company dataset is free via signup (claimed).
- Clean the TAM by scraping homepages with Python, then scoring with **GPT-5 Nano on the Batch API** against written ICP rules.

**Lookalike-from-DNC method** [H-dot6onaIw]
1. Take the client's do-not-contact / customer list.
2. Extract their LinkedIn industries, website keywords and description keywords.
3. Pull everything that matches from Blitz, Prospeo and Quick Enrich within the same headcount band.
4. Cut the list down with GPT-5 Nano. Alternative: Clay "Find company lookalikes" on your CRM. [qmi5B-N3Ev8]

**Hard qualification filters example** [-LjvwKOIH9Y]
- US CEOs at companies with more than 25 employees and at least 5 years in business.
- Clay "find contact at criteria" to check that **over 80% of employees are US-based**.

**Clay playbooks** (templates in Eric's "cold outbound skills" repo) [qmi5B-N3Ev8]

| Signal | How |
|---|---|
| New in role | Clay **Audiences**: "director+ in US who started <2 months ago", autosave on, pipes into an enrichment table, gets past the 50k table limit. Free list claimed at coldoutbound.com/list/newenroll |
| Hiring surge | "Find employee headcount by criteria" (job function) minus hires in the last 6 months = growth % |
| Tech installed | Prospeo company enrich (Wappalyzer) → ZenRows HTML check as fallback. BuiltWith is best but expensive |
| Case studies | Guess URLs for free (/customers, /case-studies…) → Claygent fallback (~$0.0001) → HTTP scrape → AI extract |
| Facebook ads | Google search for the FB page (or ZenRows on the site) → Apify FB Ad Library scraper → AI summary → AI fact-check |
| Website keywords | `site:domain.com "SOC 2"` via cheap SERP APIs (Open Web Ninja, DataForSEO, "sober.dev") |
| Job-post language | Blitz, LeadMagic, Prospeo and Clay native jobs; match keywords like "cold calling" |
| Funding | Prospeo → Clay enrich company → Google for the Crunchbase URL + ZenRows → optional Claygent |
| LinkedIn posts / engagement | Harvest API via Apify. Target engagers on competitor, partner and topic posts |
| Pricing page | Guess /pricing or /plans → scrape → per-seat price, free tier, enterprise tier |
| Peer names | Get Leads → Blitz → Prospeo waterfall, AI picks a similar role, confirm they still work there |
| Hygiene | Clean company names and first names on every list |

**Claygent prompt optimizer** [qmi5B-N3Ev8]
1. Use Claude or Codex subagents to build an answer key on 100 companies.
2. A Clay table iterates prompts on a cheap model (4o-mini) and optimizes for coverage, then for cost.
3. Run the winning prompt at scale.

**Always-full pipeline (Supabase + Clay CLI)** [gKh33_2MXmA]
- Supabase lead table fields: last loaded, last reply, ever in Smartlead, ever emailed, ever replied, source, send-window start/end.
- Track 30-day and 60-day contact history so nobody is hit more than once a quarter.
- Daily cron: if "not started" leads drop below **100,000**, push a batch to the Clay webhook.
  - Clay flow: normalize → email find → validate → company enrich → AI content → Smartlead.
- **12:00 check:** if under-sending, recheck the lead count and refill.

## 5. Deliverability / inbox infra

**5-level inbox health check** [H-dot6onaIw]
1. **Warm-up score.** Anything below 99–100% is suspicious; about 92% is pulled immediately. A 100% score can still mean spam.
2. **Seed test** in Instantly, Smartlead or Zapmail. Directional only, because seed inboxes never mark spam.
3. **Reply rate, Fridays.** Compare this week vs 2 weeks ago per domain and inbox.
   - [H-dot6onaIw]: ≥100 sent and <1% reply → cancel.
   - [gKh33_2MXmA]: ≥200 sent and <0.7% → cancel.
4. **Auto-responder seed list.** Save "this inbox is no longer monitored" auto-replies from past campaigns (Eric has about 10k). Send to them: expect about 80% to bounce back an auto-reply, kill anything under 60%. Runs on Saturdays.
5. **Real positive behavior.** Run a high-reply side campaign from the same inboxes (candidate sourcing, partnerships). It prolongs inbox life and gives a baseline reply rate.

**Capacity and insurance** [H-dot6onaIw] [01jxZN2ZNsc]
- Example: 3,000/day = 100 inboxes × 30/day active, plus **50% extra** (1,500/day) warming as insurance.
- Hypertide free domain warming (beta): turn on Google inboxes and they're live in "24 to 48 hours".

**Alerts** [H-dot6onaIw] [gKh33_2MXmA]
- Watch for sudden day-over-day drops, e.g. "1.5% → 0.2%" [H-dot6onaIw]. The same example transcribed as "1.5% → 2%" in [gKh33_2MXmA] is likely a transcription error.
- On a sudden drop:
  - [ ] Check yesterday's sends for **spam traps** with a premium validator, and pull affected domains.
  - [ ] Check for **content fingerprinting** and add spintax.

**Fast-start options** [-LjvwKOIH9Y]
- Keep generic inboxes always warming.
- Buy **aged domains** at coldemaildomains.com (closeout, $5 .coms). They need 3–4 days of warm-up before full send.
- Trade-off: no brand control, so use them for your own or blitz campaigns, not client brands.

**Domain hygiene** [H-dot6onaIw]
- Never send from the main domain.
- Domain forwarding: some blacklist providers are flagging forwarding domains. An optional fix is a small microsite per sending domain (ClickUp forwards with zero issues).
- Eric reports Google says it ignores third-party blacklists.

**Smartlead-specific** [gKh33_2MXmA] [01jxZN2ZNsc]
- Runs 30–50 campaigns per client so no single campaign has too many inboxes.
- A too-many-domains-over-limit issue halved Pathos's reply rate until fixed.
- For Instantly, check the equivalent per-campaign inbox limits yourself.

**Fallback** [01jxZN2ZNsc]
- If the reply rate stays bad, switch to Google-to-Google sending.

## 6. Metrics & testing cadence

**Campaign verdict rule** [H-dot6onaIw]
- 1,000 sends with 0 positives → kill.
- 1,000 sends with ≥1 positive → run to 3,000 before judging.

**Diagnosis order before touching copy** [H-dot6onaIw]
- [ ] Warm-up 100%
- [ ] Seed test 100%
- [ ] Reply rate >1%
- [ ] Auto-responder return >80%
- [ ] Baseline campaign normal
- [ ] List eyeballed

**Cadence** [H-dot6onaIw] [gKh33_2MXmA]
- Daily: spam tests and drop alerts, lead refill check.
- Midday: send-volume check.
- Fridays: reply-rate culls and domain reorders.
- Saturdays: auto-responder test.

**Weekly AI review** [H-dot6onaIw]
- Feed last week's results, sales calls and contacts to Claude or Codex and ask for new tests.

**Quoted numbers**

| Claim | Source |
|---|---|
| ~106,000 emails, 1 positive per 286 → 373 positives → ~62% booked → 231 meetings → ~$50,000 (half paid at recording) | [-LjvwKOIH9Y] |
| 80–100 positives/day for one client (Pathos) | [gKh33_2MXmA] |
| Pathos days: 0.6% → 0.7% reply with 64 positives; after inbox swap, 63 / 112 / 76 positives | [01jxZN2ZNsc] |
| 300–400 positives/day across ~50 customers; 2,000–3,000 total replies/day on the master account | [01jxZN2ZNsc] [qmi5B-N3Ev8] |
| Spintax took a campaign from 0.3% to 1.2% reply the same day | [H-dot6onaIw] |
| "Over $10 million" earned over 7 years | [H-dot6onaIw] |

## 7. Tools mentioned

**Agents and orchestration**
- **Grok Bot**: always-on cloud sandbox, secure env-var key entry, OAuth plugins, reliable crons. Used for lead refill, inbox swaps, domain reorder suggestions, reply tagging, and building Clay workflows. [gKh33_2MXmA] [01jxZN2ZNsc]
  - Named bots: Taskmaster router, deliverability, list building, ops inbox, Clay CLI expert. [01jxZN2ZNsc]
  - Weaknesses: no goal mode, interrupt aborts the run, X integration is read-only, usage burns fast. [01jxZN2ZNsc] [gKh33_2MXmA]
- **Hermes, OpenClaw**: rejected as unreliable, with broken crons. [gKh33_2MXmA] [01jxZN2ZNsc]
- **Claude Code / Codex / Cursor**: skills, automation builds, thought partner. [H-dot6onaIw]
- **Whisper Flow**: voice prompting. [gKh33_2MXmA]
- **browser-harness**: open-source library for auto-building Clay tables. [qmi5B-N3Ev8]

**Clay**
- **Clay CLI** ("the Vercel for go-to-market"): gives hosted workflows with observability and history. [gKh33_2MXmA]
- Audiences, Sculptor, Workflows, Claygent, find contact / headcount by criteria, lookalikes. [qmi5B-N3Ev8]
- Every Clay table can become a workflow, but not vice versa. [qmi5B-N3Ev8]

**Data and enrichment**
- **Supabase**: lead and inbox state tables. [gKh33_2MXmA]
- **Data vendors**: Prospeo, Blitz API, Quick Enrich, Get Leads, "Mult Sets", LeadMagic, MillionVerifier, People Data Labs, BuiltWith. [all]
- **Scrapers and search**: Apify (Harvest API, FB Ad scraper), ZenRows, RapidAPI Maps, Open Web Ninja, DataForSEO, Exa, Parallel, DiscoLike, Ocean.io, Apollo. [all]

**Sending and infra**
- **Smartlead**: sending. Instantly is also referenced. [all]
- **Hypertide** and **Zapmail**: inboxes. **Dynadot**: domain purchase via API. [01jxZN2ZNsc] [H-dot6onaIw]
- **coldemaildomains.com**: aged domains. [-LjvwKOIH9Y]

**Other**
- **Fathom**, **Stripe**: onboarded to the agent. [01jxZN2ZNsc]
- **Eric's resources**: "cold outbound skills" repo (about 30 skills plus Clay templates) and coldoutbound.com. [qmi5B-N3Ev8] [H-dot6onaIw]

## 8. Caveats / dated claims to re-validate

- **Thresholds disagree:** reply-rate cull is ≥100 sent / <1% in [H-dot6onaIw] vs ≥200 sent / <0.7% in [gKh33_2MXmA]. Pick one for our own SOP.
- **Grok Bot is new** (Eric says "about a week" old in [01jxZN2ZNsc]). Re-check reliability, pricing, the usage bug and feature gaps before adopting. Eric also promised shared bots or skills that may not exist yet. [gKh33_2MXmA]
- **Hypertide free warming** was in beta. Confirm availability and terms. [H-dot6onaIw] [-LjvwKOIH9Y]
- **Prices are claims:** Harvest "$0.004", RapidAPI "$100/3M", Claygent "~$0.0001", LeadMagic's (Eric admits "I don't know the pricing"), and PDL's free dataset.
- **Google ignoring blacklists** and **forwarding-domain blacklisting** are second-hand. Monitor rather than act by default. [H-dot6onaIw]
- **"Best campaign" claims** for Creative Ideas and the "60–70% guessable" email share are self-reported. Validate on our own data.
- **The $50k copy was not shared.** Don't reverse-engineer claims about it. [-LjvwKOIH9Y]
- **Smartlead vs Instantly:** the inbox-per-campaign and domain-limit mechanics are Smartlead-specific. Map them to Instantly before copying the "30–50 campaigns" pattern. [gKh33_2MXmA]
- **Vendor names** are transcribed phonetically (see top note).

## Source videos

- gKh33_2MXmA — How I Get 100 Positive Replies a Day Using Grokbot
- -LjvwKOIH9Y — I speedran cold email from 0 to $50k in 30 days
- qmi5B-N3Ev8 — My Favorite Cold Email Strategy for Getting Clients (with proof)
- H-dot6onaIw — Give Me 25 Minutes and I'll Give You 7 Years of Cold Email Advice
- 01jxZN2ZNsc — Grok Bot Just Changed Businesses Forever! (Tutorial)
