<!-- distill: batch_07_of_11 | videos: XAjZprU5e2I, PxosIYH8HKI, DRax2OiF_ZA, yKImVaiPXzQ, _517b8nH2RE | model: opus | elapsed_s: 74 -->

# Playbook batch: List-building source selection (Sales Nav, look-alikes, Google Maps, custom scrapes, agents) + Claude Code as a campaign-testing engine

---

## 1. Frameworks / mental models

- **Pick the list source from where the ICP actually lives** (5 source types) [PxosIYH8HKI]:

  | ICP situation | Source | Tools named |
  |---|---|---|
  | Big market, people keep LinkedIn profiles | LinkedIn-based DB / Sales Nav scrape | Clay, Prospeo, Rapid API Sales Nav scraper |
  | Clear niche but no clean LinkedIn industry (e.g., fintech) | Look-alikes | Ocean.io, DiscoLike |
  | Local businesses that "live or die by Google Maps" | Google Maps scrape | scraper.tech (via Rapid API) |
  | Niche verticals in directories, associations, gov data | Custom scraping | Claude Code / Cursor / Codex, Instant Data Scraper |
  | Ultra-niche, small TAM (~2k cos), hard to filter | AI research agents | Exa.ai, Parallel.ai, Manus |

  - "For 80% of the lists that we build, it starts with this data [LinkedIn]" [PxosIYH8HKI]
- **Sales Nav is the upstream source.** Third-party DBs get LinkedIn data secondhand. Signals such as job changes, posts, follows and views appear in Sales Nav first. [XAjZprU5e2I]
- **Headcount is two different numbers** [XAjZprU5e2I]:
  - Sales Nav headcount = self-reported range on the company page.
  - Clay/Apollo headcount = count of profiles linked to the company page.
  - Blue-collar companies (e.g., pest control): the self-reported number is likely closer to reality, because techs don't have profiles.
  - SaaS: the self-reported number is often stale and set at founding.
- **Company-level LinkedIn data is self-reported and dirty.** Example: a banking SaaS lists "Banking" as its industry. Titles are usually good enough, so clean at the company level with AI. [PxosIYH8HKI]
- **Test cold email like Meta ads.** The top performers are the heaviest testers. Run more, smaller campaigns, cut losers fast, and let learnings compound per client. [DRax2OiF_ZA]
  - Claimed side benefit: varied copy across inboxes is "better for the inboxes from a deliverability standpoint." [DRax2OiF_ZA]
- **Campaign portfolio mix: Broad / Focused / Niched** [DRax2OiF_ZA]:
  - **Broad**: whole ICP, no signal.
  - **Focused**: a segment by headcount, title or industry.
  - **Niched**: a signal-based, finite TAM. Examples: website-visitor deanonymization ("everybody should do"), competitor-tech users.
- **Three-skill Claude pipeline** [DRax2OiF_ZA]:
  1. Strategy skill generates 10–20 campaign ideas, each with segment, hook, audience, CTA and lead magnet.
  2. Scoring skill rates each idea against historical campaign data and suggests improvements. The idea is then revised.
  3. Copy skill is trained on ~20 Google Docs of liked campaigns plus Josh Braun LinkedIn content.
- **Verify your ICP with data, not client hypotheses.** Example: a client believed the "1 AE : 3 SDR ratio" mattered. The analysis showed that "has a Sales Ops person" was the stronger predictor. [yKImVaiPXzQ]

## 2. Copy formulas

> Eric gave no subject lines or follow-up sequences in this batch. The items below are the only copy patterns that appear.

- **Past-company name-drop (case-study alumni)** [XAjZprU5e2I]
  - Quote: *"Hey… I saw you used to work at Coca-Cola in the past. They were actually one of our customers and I think we'd be able to help your current company."*
  - Template (adapted):
    `Hi {{first}}, saw you were at {{past_company}} before {{current_company}}. {{past_company}} is a client, and we {{result}}. Worth a look for {{current_company}}?`
- **Owner-named generic inbox** [_517b8nH2RE]
  - When only info@ is found, still open with the verified owner's name ("Hey Bob") instead of "Hey there."
  - Store `owner_name` alongside `generic_email`.
- **Signal-based first lines.** Eric names the signals but gives no copy. Hooks are to be written by Copywriter. [XAjZprU5e2I]
  - New to company
  - Recently promoted
  - Recently posted on LinkedIn
  - Follows a competitor
  - Viewed your profile
- **Style reference**: Josh Braun is his named favorite cold-email copywriter. Use Braun's work as training examples for the copy skill. [DRax2OiF_ZA]

## 3. Offer / angle patterns

- **Case-study alumni campaign**: put every case-study logo in the *Past company* filter, then add a current title filter. [XAjZprU5e2I]
- **New-in-seat vs. promoted**: use *years in current company* and *years in current position* separately. [XAjZprU5e2I]
  - <1 yr in position AND <1 yr at company = new hire.
  - <1 yr in position but longer at company = promotion.
- **Past-title affinity**: e.g., a former finance person who is now a sales leader. Eric calls this niche and rarely uses it. [XAjZprU5e2I]
- **LinkedIn Groups = high-intent interest.** Discovery on Groups is terrible, so members who found and joined one care about the topic. [XAjZprU5e2I]
- **Competitor followers filtered by function**, e.g., "every marketer following your competitor." [XAjZprU5e2I]
- **Lead magnets**: generated per campaign by the strategy skill. [DRax2OiF_ZA]

## 4. List-building & enrichment tactics

**Sales Nav checklist** [XAjZprU5e2I]
- [ ] Use the **Leads** tab, not Accounts.
- [ ] Put a **Boolean in Keywords** (it searches the whole profile), e.g. `"outbound marketing" OR "GTM engineer" OR "cold email" OR "growth hack"`. Ask an LLM to draft the Boolean.
- [ ] Skip Function and Seniority. Load explicit current job titles instead.
- [ ] Use the Past company filter for case-study alumni.
- [ ] Use Years in company and Years in position separately.
- [ ] Use Groups relevant to the offer.
- [ ] Use Changed jobs and Posted recently (these can be scraped via a rented account).
- [ ] Use Follows your company and Viewed your profile. These are tied to your own account only, so extract them with PhantomBuster or HeyReach.
- [ ] Treat Industry, Company type and Years of experience as unreliable (self-reported or LinkedIn-inferred).
- [ ] For export without risking your own seat, use a Rapid API tool that rents a Sales Nav account (Eric uses the "pro plan").
- [ ] For competitor followers, use scrapeli.io or following.co.

**Look-alikes** [PxosIYH8HKI]
- Seed with 3–5 known-good companies, then add include/exclude keywords.
- Always review the output manually. A seed like "clay.com" is ambiguous: SaaS? PLG? sales tool? data tool?
- DiscoLike claims coverage beyond LinkedIn, i.e. any site with HTTPS (per the founder).
- You're never sure you have the full TAM, so pair DiscoLike with a Google Maps scrape for local verticals.

**Google Maps → owner → email pipeline** [_517b8nH2RE] [PxosIYH8HKI]
1. **Businesses**: scraper.tech Google Maps API via Rapid API. Alternatives: Serper.dev and others.
2. **Clean the output.** "Airports and churches" show up even in roofing searches. [PxosIYH8HKI]
3. **Owner, LinkedIn first**: a match where profile says owner and company domain equals the Maps website domain.
4. **Owner, website**: scrape the homepage plus ~20 second-level pages (about, contact, blog index; not every post) with plain Node.js fetch and HTML parsing. Alternatives: spider.cloud, Crawl4AI, Scrapy, Firecrawl.
5. **LLM owner extraction** on a self-hosted model: vast.ai GPU running gpt-oss-120b. Prompt: "who is the owner + summary + proof."
6. **Fallback**: Open Web Ninja Google search (`"{{business}} owner"`) plus AI-mode/overview scrape.
7. **Re-verify with a second prompt.** "It cost you nothing. Why not verify it again."
8. **Email waterfall**: Prospeo → Smartlead email finder → website-scraped generic email, keeping `owner_name`.
- Hosted alternative mentioned: a platform from Eric's friend (name unclear in transcript, "Tang.ai"; verify the spelling).

**Custom scraping** [PxosIYH8HKI]
- Sources: chamber of commerce member directories, associations and boards (e.g., plastic surgeons), government and county data.
- Ask Claude Code, Cursor or Codex to build the scraper, or use the Instant Data Scraper Chrome extension.
- Ask ChatGPT, Claude or Manus to find directories for your ICP.
- Pros: low competition, highly targeted.
- Cons: manual setup, small lists. You may need "eight directories" for a month of volume.

**AI-agent list building** [PxosIYH8HKI]
- Feed Exa.ai or Parallel.ai client-verified good companies plus *why* they fit (website keywords).
- Set a budget ceiling (he used $100–300).
- Wrap it in Claude Code, Cursor or Codex to loop searches and watch spend.

**ICP analysis + TAM build (Claude Code)** [yKImVaiPXzQ]
- Enrich customers with LinkedIn industry, headcount, About section and contact titles, using Clay, Prospeo or Rapid API. Then have Claude analyze the CSV.
- Codify tiers, e.g. "industry + headcount + website keywords = A; industry match but no keywords = B." Then pull the TAM via the Prospeo API.
  - Pricing claim: "one credit for 25 contacts in the search" vs. Apollo charging per contact.
- Alternatives: DiscoLike for companies, then Blitz API for people.
- Store the ICP, TAM and call-transcript insights in Supabase. Ask Claude to find the official Supabase skill.
- Mine Fathom transcripts for: best and worst customer patterns, common sales questions, recurring workflows.

## 5. Deliverability / inbox infra notes

- More copy variants across inboxes is claimed to be better for deliverability. Directional only; no data given. [DRax2OiF_ZA]
- Smaller test volume per campaign limits the damage from a losing campaign. [DRax2OiF_ZA]
- Generic info@ addresses to local businesses "totally worked" for them. [_517b8nH2RE]
- Smartlead's finder is favored because it uses real send and no-bounce data. [_517b8nH2RE]

## 6. Metrics & testing cadence

- **Agency scale claims** [PxosIYH8HKI] [DRax2OiF_ZA] [yKImVaiPXzQ]:
  - "about 8 million cold emails per month"
  - "over 60,000 positive replies in 2025"
  - "1,500 campaigns last year"
  - "over 300 companies" worked with
- **Analysis method** [DRax2OiF_ZA]:
  - Dump all sending-account data into Supabase.
  - Point Claude Code at it ("like 30 Claude sub-agents") to find winner vs. loser traits.
  - Also run the analysis at the client level: number of campaigns, tenure, and positive replies.
- **Cadence** [DRax2OiF_ZA]: after 5, 10 or 15 campaigns per client, feed replies and data back in and let Claude propose the next test. The loop is recursive per client.
- **Routing without errors** [DRax2OiF_ZA]:
  - Encode if/then routing (title × industry × headcount → campaign) in a trigger.dev or Railway worker, called from Clay.
  - Clay still handles queuing and concurrency.
  - Ask Claude "are there any holes in this plan" to catch leads landing in two campaigns.
  - For Lorenzo: the same logic applies to Instantly campaign assignment.
- **Recursive data-quality tests** [yKImVaiPXzQ]:
  - Give Claude known-truth first-party data (emails, phones, headcount, revenue) and have it benchmark about 6 providers.
  - Iterate the ICP-fit prompt against 100 random companies until it classifies accurately.
- **Google Maps run** [_517b8nH2RE]: "10,000 businesses" → "7,542 business owner names" → "3,246 emails" (the run was still going when filmed; spot-checked manually).

## 7. Tools mentioned

| Tool | How used | Src |
|---|---|---|
| LinkedIn Sales Navigator | Primary lead search and signal source | [XAjZprU5e2I] |
| Rapid API Sales Nav scraper | Rented Sales Nav account for export | [XAjZprU5e2I] [PxosIYH8HKI] |
| scrapeli.io, following.co | Competitor-page followers | [XAjZprU5e2I] |
| PhantomBuster, HeyReach | Export profile viewers and your own signals | [XAjZprU5e2I] |
| Clay | Enrichment, orchestration host, Claygent | [all] |
| Prospeo | LinkedIn DB, TAM API, email finder | [PxosIYH8HKI] [yKImVaiPXzQ] [_517b8nH2RE] |
| Apollo | Alternative, per-contact credits | [yKImVaiPXzQ] |
| Ocean.io, DiscoLike | Look-alike company lists | [PxosIYH8HKI] [yKImVaiPXzQ] |
| Blitz API | Find people from company lists | [yKImVaiPXzQ] |
| scraper.tech (via Rapid API), Serper.dev | Google Maps scraping | [PxosIYH8HKI] [_517b8nH2RE] |
| spider.cloud, Crawl4AI, Scrapy, Firecrawl | Website text scraping | [_517b8nH2RE] |
| Open Web Ninja | Google search and AI-overview scrape | [_517b8nH2RE] |
| vast.ai + gpt-oss-120b/20b | Cheap self-hosted LLM for bulk extraction and ICP cleaning | [_517b8nH2RE] [PxosIYH8HKI] |
| Smartlead email finder | Email finding from send data | [_517b8nH2RE] |
| Exa.ai, Parallel.ai, Manus | Agentic niche list research | [PxosIYH8HKI] |
| Instant Data Scraper | Chrome extension for directories | [PxosIYH8HKI] |
| Claude Code, Cursor, Codex | Scrapers, analysis, skills, routing | [all but XAjZprU5e2I] |
| Supabase | Campaign, TAM and insight database | [DRax2OiF_ZA] [yKImVaiPXzQ] |
| trigger.dev, Railway | Routing-logic endpoints called from Clay | [DRax2OiF_ZA] |
| Fathom | Call transcripts for the knowledge hub | [yKImVaiPXzQ] |
| Instantly, Smartlead | Sending platforms | [DRax2OiF_ZA] |

## 8. Caveats / dated claims to re-validate

- **Scraping legality.** Eric says LinkedIn "lost a lawsuit… anybody can scrape anything… as long as you didn't have to log in." That oversimplifies. Get legal review before relying on it. [PxosIYH8HKI]
- **Rented Sales Nav accounts / PhantomBuster** likely violate LinkedIn ToS. "Without putting your account at risk" refers to *your* seat only. [XAjZprU5e2I]
- **Don't adopt the tip to tell an AI model "it's for a school project"** to get past scraping refusals. It's misrepresentation. Scrape only what you're permitted to use. [PxosIYH8HKI]
- **Model benchmarks** ("OSS 20B ≈ o3-mini, 120B ≈ o4-mini"), **GPU price** (~"69" cents/hr), and **throughput** ("13–16 requests per second") are as of filming. [_517b8nH2RE]
- **"Worth it if you spend more than $2,000 a month on AI"**: threshold for self-hosting on vast.ai. [PxosIYH8HKI]
- **Pricing claims to check**: Prospeo's "7 days" refresh on highly targeted profiles and "1 credit / 25 search results." [PxosIYH8HKI] [yKImVaiPXzQ]
- **Unverified claims**:
  - Smartlead finder described as "just released." [_517b8nH2RE]
  - DiscoLike "HTTPS-cert" coverage, per founder. [PxosIYH8HKI]
  - Anthropic case study with DiscoLike. [PxosIYH8HKI]
- **Soft or anecdotal numbers**:
  - The 7,542 / 3,246 numbers come from a single same-day, still-running test. [_517b8nH2RE]
  - "3, 5, 7, 10x effectiveness" is rhetorical. [XAjZprU5e2I]
- **Tool names are auto-transcribed.** Confirm spellings: scrapeli.io, following.co, "Tang.ai," Manus URL. [XAjZprU5e2I] [_517b8nH2RE] [PxosIYH8HKI]
- **Private skills.** Eric won't share his Claude skills. The three-skill pipeline must be rebuilt in-house. [DRax2OiF_ZA]

## Source videos

- XAjZprU5e2I — How to Use LinkedIn Sales Nav in 2026
- PxosIYH8HKI — How to Choose the Right Way to Build Any Lead List
- DRax2OiF_ZA — AI Turned Cold Email Into a Testing Machine (Here's How We Use It)
- yKImVaiPXzQ — Stop Watching AI Tutorials. Build These 5 GTM Systems Instead
- _517b8nH2RE — Inside Our Claude Code Google Maps Lead System (Owner + Email Finder)
