<!-- distill: batch_08_of_11 | videos: cgTDDu915iU, oIMx7CBprh4, HiDjmYGom5g, J1Xi0T6wZAY, KKGo0_LOUx4 | model: opus | elapsed_s: 67 -->

# Playbook batch: AI lead magnets, signal-based lists, and cheap AI list scoring (2026)

## 1. Frameworks / mental models

- **Old view vs. new view on email quality** [cgTDDu915iU]
  - An email as good as one written after 10 minutes of research is now "A tier."
  - "S tier" drops most of the personalization and instead gives value before any conversation, at scale.
- **The "easy to say yes to" rule** [cgTDDu915iU]
  - Across GEX customers, the campaigns with the most positive replies all include an offer that is easy to say yes to.
- **Three buckets of AI lead magnets** [cgTDDu915iU]
  1. **Knowledge:** intel reports, competitor audits, industry news, signal lists.
  2. **Micro app / micro SaaS:** a small tool built in a weekend (e.g., in Lovable).
  3. **Agentic free trial:** part of a manual service is automated and given away free as the first touch.
- **Every business is either knowledge arbitrage or time arbitrage** [cgTDDu915iU]
  - Pick your lead magnet based on which one you sell.
- **MQL framing** [cgTDDu915iU]
  - Lead-magnet replies are hand-raisers, not booked demos.
  - Deliver about 80% of the value up front and tie the last 20% to a call.
- **Validate before you build** [cgTDDu915iU]
  - Pitch about 5 lead-magnet ideas in micro campaigns that you could fulfill manually.
  - Build only the one that wins.
- **Social proof they already recognize** [oIMx7CBprh4]
  - Target people who engage with your case-study customer's or competitor's LinkedIn content.
  - Cite that customer or competitor as proof. Never mention the engagement itself.
- **Punch up** [oIMx7CBprh4]
  - Monitor large competitors, not fellow bootstrapped founders.
- **Build the TAM backwards from the customer list** [HiDjmYGom5g, J1Xi0T6wZAY]
  - LinkedIn industry and firmographic fields are self-reported and often wrong.
  - Derive the real titles and industries from actual buyers, pull broadly, then clean with AI.
  - Goal: "80% of coverage" of TAM, with every company on the list a solid fit.

## 2. Copy formulas

**Creative ideas → report offer (knowledge lead magnet)** [cgTDDu915iU]
```
Hey {{first_name}},
{{one line about the offer / what we do}}.
If I could share {{N}} real companies that have these three signals —
{{signal_1}}, {{signal_2}}, {{signal_3}} — would you be interested in that report?
```
- Signal ideas come from a cheap AI analysis of their website.
- Only after a positive reply, generate the real report and send it as a Gamma doc. Do not ask for a call first.

**Variant: "already have it"** [cgTDDu915iU]
- "Hey, I already have this report of all these things. Do you want to see it?"
- Only use this if your prompt will reliably find matches. "Don't put yourself into a hole."

**Customer-adjacency (engagers of your case-study customer)** [oIMx7CBprh4]
```
Hey {{first_name}}, we do {{service}} for companies like {{case_study_customer}}.
Would you want to talk?
```
- ❌ Never write "I saw you liked {{company}}'s post."

**Competitor-adjacency (engagers of a competitor)** [oIMx7CBprh4]
```
{{normal message}} … Competitors like {{comp_1}}, {{comp_2}} do things {{their way}};
here's how we do things: {{differentiator}}.
```

**Agentic free-trial delivery / handoff** [cgTDDu915iU]
> "Hey, we got you a lead. This is what we said to them. This is what they said to us. I'm going to connect you guys right now. But if you want this to happen all the time, let me know and we can have a call."

- Eric says this "books meeting[s] like crazy."

**Free-trial qualification gate (GEX's free-campaign offer)** [cgTDDu915iU]
- At least 1 salesperson
- B2B
- TAM over 100,000
- LTV of $5,000

## 3. Offer / angle patterns

- **Signal intel report** [cgTDDu915iU]
  - Examples from the video:
    - Regional US banks that announced a new location in the last 30 days.
    - NJ warehouses with a new location, lease, or groundbreaking.
    - Companies that announced new developments not yet built.
    - E-commerce brands with a specific sustainability cause.
  - Use for any buyer who cares about new physical locations or expansions.
- **Knowledge lead magnet types** [cgTDDu915iU]
  - Competitor audit
  - Audit of the prospect's own company
  - Industry news digest
  - List of prospects matching a signal
- **Micro-app lead magnet** [cgTDDu915iU]
  - Example: a free email finder built from the emails you have already sent to (be truthful that it's your send database).
  - Avoid "boring" calculators. Aim for a workflow or tool the prospect would genuinely want.
- **Agentic free first campaign / trial** [cgTDDu915iU]
  - Automate part of the service (list pull, copy, inbox provisioning) and run it free.
  - Claim: this "will raise your reply rates 100%. As long as they find it valuable."
- **Two-stage cost model** [cgTDDu915iU]
  - Cheap analysis to write the email: "15 cents per analysis" or "half of half of half a penny."
  - "Spend a dollar" to build the full report only after a positive reply.
  - Automation runs about 5 minutes, then deliver.

## 4. List-building & enrichment tactics

**A. LinkedIn engagement scrape (RapidAPI + Claude Code/Cursor)** [oIMx7CBprh4]
- [ ] Subscribe to the RapidAPI LinkedIn scraper (Eric links it in the video description). Use the **batch** version for concurrent runs.
- [ ] Connect the RapidAPI MCP in Claude Code or Cursor, and work in **plan mode**.
- [ ] Input: a list of LinkedIn company URLs plus a time window.
- [ ] Pipeline:
  1. Pull the company-page posts.
  2. Pull the company's employees.
  3. Pull those employees' posts.
  4. Capture everyone who liked or commented on any of those posts.
- [ ] Dedupe engagers across posts before enrichment to save credits.
- [ ] Optional: search posts by topic instead of by company.
- [ ] Optional: add a UI hosted on Railway after the first CLI version works.
- Tip: put this video's transcript into NotebookLM to generate the build plan.
- Claims: setup took "about 10 minutes"; "sometimes we see four to five x increases on reply rates above the regular campaign."

**B. Customer-list-backwards TAM build** [HiDjmYGom5g, J1Xi0T6wZAY]
1. **Enrich the customer list** (or the do-not-contact list) at two levels:
   - Person: title, tenure, past companies, about section, headline, job description.
   - Company: description, industry, headcount, location.
   - Prospeo can do a reverse lookup from email, with a company-level fallback when the person isn't found.
2. **Have Claude (Opus) analyze the enriched list** and produce:
   - Top buyer titles, seniority, departments
   - Top industries and headcount range
3. **Pull every company** that matches those LinkedIn industries and headcounts, including stray industries.
   - Example: "event services" showed up among trucking and wholesale customers.
4. **Build an ICP scoring prompt with Claude Code or Cursor.**
   - Mix known customers into the random pull.
   - If a known customer fails the filter, the prompt must stop, ask for more inputs, and find out why. No lazy rules like "description looks like X means fit."
   - Review 10 random results manually, explaining why each is a good or bad fit.
   - Add per-industry fit rules (e.g., "if the industry is event services, these are the ones that fit").
5. **Run at scale** on GPT-5 nano with cached inputs, the batch API, and low or minimal reasoning. You wait about 24 hours for results.
6. **Find contacts** using the real extracted titles (Clay, Prospeo, or others), then launch.

**C. Prospeo V2 search features worth using** [J1Xi0T6wZAY]
- Company filters mirror LinkedIn's, with live counts per industry.
- Keyword filter with toggles for social-media (LinkedIn description) and SEO keywords.
- Buying intent (Bombora) and technologies (Wappalyzer).
- "Offers demo" and "offers free trial" flags.
- Job postings, headcount by department, and company email provider.
- Person filters: years of experience, time in role, time at company.
- **Duplicate control:** hide people on exclusion lists, on a specific customer's list, or anyone previously saved or exported. Useful for multi-client agencies.
- **"Copy API payload" button:** non-technical team members build the search visually, then push the payload to a backend workflow (trigger.dev or Railway).
- Enrich-person response also includes company data, so you don't need to enrich the company separately.
- Lookup inputs: name + company, LinkedIn URL, email, or person ID.
- Search-person returns 25,000 per search. Larger pulls (e.g., 300k) need proper pagination, possibly via a Claude skill.

## 5. Deliverability / inbox infra notes

- No direct deliverability guidance in this batch.
- GEX's agentic workflow auto-provisions inboxes as part of its free campaigns, but no details are given [cgTDDu915iU].

## 6. Metrics & testing cadence

- **Lead-magnet test** [cgTDDu915iU]: 5 ideas → micro campaigns → pick the one with the most interest → build.
- **Engagement-sourced lists vs. regular campaigns** [oIMx7CBprh4]: "sometimes 4–5x" reply rate. Worth A/B testing yourself.
- **Scoring QA** [HiDjmYGom5g]:
  - Known customers must pass the filter (recall check).
  - Spot-check 10 random scored companies before running the batch.
- **Prospeo vs. Clay database counts** [J1Xi0T6wZAY]: "always within five to 7% of each other." Contact data in Eric's tests was up to date, except for people listing two current roles and private profiles.
- **Scale reference** [cgTDDu915iU, KKGo0_LOUx4, HiDjmYGom5g]:
  - "Over 8 million" or "7 to 9 million" emails per month
  - "Over 50 customers"
  - "$15,000 to $20,000 a month on OpenAI"

## 7. Tools mentioned

| Tool | How used | Src |
|---|---|---|
| Parallel.ai / Exa / Manus | Research agents that find signal-matching companies for intel reports | [cgTDDu915iU] |
| Gamma | Format and deliver reports; internal presentations | [cgTDDu915iU, oIMx7CBprh4] |
| Clay / Clay Agent | Creative-ideas research; list building; OpenAI calls (cached inputs work inside Clay) | [cgTDDu915iU, HiDjmYGom5g, KKGo0_LOUx4] |
| Claude Code / Cursor | Build scrapers and scoring prompts; plan mode; voice-note specs | [oIMx7CBprh4, HiDjmYGom5g] |
| Claude Opus | Analyze the enriched customer list and produce a persona/ICP strategy | [HiDjmYGom5g] |
| Lovable | Weekend micro-app lead magnets | [cgTDDu915iU] |
| RapidAPI LinkedIn scraper (+MCP, batch version) | Company, employee, post, and engager scraping | [oIMx7CBprh4] |
| NotebookLM | Turn a video transcript into a build plan | [oIMx7CBprh4] |
| Railway / trigger.dev | Host workflows and UIs | [oIMx7CBprh4, J1Xi0T6wZAY] |
| Prospeo (V2 DB + API) | Search, bulk company enrich, person enrich, reverse email lookup; the "1:1 match with LinkedIn data" | [HiDjmYGom5g, J1Xi0T6wZAY] |
| Bombora / Wappalyzer | Intent and technographic filters inside Prospeo | [J1Xi0T6wZAY] |
| OpenAI GPT-5 nano + Batch API + cached inputs | Cheap mass ICP scoring | [HiDjmYGom5g, KKGo0_LOUx4] |
| Supabase | Eric's own 6–7M company database, abandoned in favor of Prospeo | [HiDjmYGom5g, J1Xi0T6wZAY] |
| Sales Nav scrapers, Sculptor | Alternatives for the LinkedIn-matched pull | [HiDjmYGom5g] |

**Cached-input prompt checklist** [KKGo0_LOUx4, HiDjmYGom5g]
- [ ] Make the prompt ≥ 1,024 tokens. Check with an OpenAI token counter.
- [ ] Keep the prefix identical across rows: instructions, rubric, examples.
- [ ] Put all variable fields (company description, industry, etc.) **at the very end**.
- [ ] Stack with the Batch API and low or minimal reasoning.
- Hits are "finicky" and not guaranteed.
- Evidence from the experiment:
  - With a prompt over 1,024 tokens, cached input spend grew alongside regular input.
  - After rerunning a prompt under 1,024 tokens, input spend jumped from "40 cents" to "82 cents."

## 8. Caveats / dated claims to re-validate

- **Pricing** [KKGo0_LOUx4, HiDjmYGom5g]:
  - "90% off" cached inputs on GPT-5; "50%" on 4o-mini.
  - Batch API "50% off input and output."
  - The 1,024-token threshold.
  - Recheck all of these against current OpenAI pricing.
- **Clay's displayed OpenAI cost estimate** was "pretty sure" wrong when cached inputs were used. Observed 2025-12-02 and reported to Clay [KKGo0_LOUx4]. Verify against the OpenAI usage dashboard, not Clay's number.
- **Parallel.ai report cost:** "15 cents" per analysis and "spend a dollar" for full reports. The balance figure he read ("$7756") is ambiguous in the transcript [cgTDDu915iU].
- **"Reply rates +100%"** from agentic free trials and **"4–5x"** from engagement lists are anecdotal agency claims. Test them in Instantly before relying on them [cgTDDu915iU, oIMx7CBprh4].
- **The specific RapidAPI endpoint** isn't named in the transcript. It's only linked in the video description. Eric also noted GEX needed to switch to the newer bulk version [oIMx7CBprh4].
- **Prospeo V2** was a new launch ("free trial this week"). Features, the 25k per-search cap, and parity with Clay (within 5–7%) may have changed. Job-posting data looked weak in his live check [J1Xi0T6wZAY].
- **Eric's note on disclosure:** there is a sponsorship/relationship with Prospeo (a long-time friend of the team, who built features to his spec) [J1Xi0T6wZAY]. Weigh the endorsement accordingly.
- **The 2026 predictions** reverse Eric's earlier "10-minute research email" advice. Treat them as a direction to test, not a proven result [cgTDDu915iU].
- **Compliance:** a micro-app email finder built from your send database raises privacy and data-use questions. Check before copying the idea [cgTDDu915iU].

## Source videos
- cgTDDu915iU — The Real Way AI Will Change Cold Email in 2026
- oIMx7CBprh4 — Beginner Claude Code Scraping Tutorial
- HiDjmYGom5g — Building Cold Outreach Lead Lists in 2026 with AI
- J1Xi0T6wZAY — Exploring Prospeo V2 Database
- KKGo0_LOUx4 — Save on OpenAI Costs with Cached Inputs
