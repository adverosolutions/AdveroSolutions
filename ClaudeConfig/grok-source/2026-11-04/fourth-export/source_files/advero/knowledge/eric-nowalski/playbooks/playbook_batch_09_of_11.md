<!-- distill: batch_09_of_11 | videos: zC7yIRwkyaY, k3uGNuXtzQM, sMcolK-mvnE, cfpLJqkmB6I, -v-WBPE1gaI | model: opus | elapsed_s: 116 -->

# Playbook batch: First principles, research-driven "alpha" copy, and Cursor-automated list/infra ops

## 1. Frameworks / mental models

- **Three levers, in priority order** [k3uGNuXtzQM]
  1. Inbox infrastructure: if it lands in spam, nothing else matters.
  2. List: the right-fit people.
  3. Copy and campaign strategy: something valuable, or a problem solved.
- **Test, don't obey "best practice."** Images, video and similar tactics are tests. Judge them on net positive replies, not deliverability alone. [k3uGNuXtzQM][cfpLJqkmB6I]
- **Do the opposite of a spammer.** This covers slow ramps, aged domains, no open tracking and plain text. [k3uGNuXtzQM][cfpLJqkmB6I]
- **10-minute research rule.** Ask: "If I researched this company for 10 minutes, what would tell me it's a fit, and what would change my message?" Then automate that research. This is the source of "GTM alpha." [k3uGNuXtzQM][cfpLJqkmB6I]
- **Alpha layering.** Start with baseline blasts, then add a researched first line, then add visual proof (a screenshot). Each layer is measured. [cfpLJqkmB6I]
- **Offer sophistication check** [k3uGNuXtzQM]
  - Universal, acute problem → **"straight down the middle"** (just say what you do).
  - Crowded or overused message (e.g., "we get you leads") → you need a lead magnet or free work that outdoes competitors.
- **Buyer seniority.** CEOs reply more because they are always hunting for solutions. Mid-level roles (e.g., director of HR) avoid buying politics. Eric attributes this to his own data plus Belkins and ColdIQ, with no number given. [k3uGNuXtzQM]
- **WIIFM.** "If they reply yes, what do they get?" [cfpLJqkmB6I]
- **Only 3 ways a campaign fails** [cfpLJqkmB6I]
  1. The copy stinks.
  2. Not enough net-new Email 1s sent.
  3. Inboxes are trashed.
- **Golden ICP.** Stack ICP conditions and vary the message by how many are true. [cfpLJqkmB6I]
  - Example ladder: small-business founder → never raised → founded less than 2 years ago → first-time CEO or not.
  - 4 true = message A; 3 true = message B; … down to "valid email + a pulse."
- **Information arbitrage lead magnet.** You know something about the market that prospects want. Offer your framework on the call; no asset build needed. [cfpLJqkmB6I]
- **Cursor SOP for non-technical builders** [zC7yIRwkyaY]
  1. Dump far too much context (voice memo while walking).
  2. Run plan mode on a frontier model.
  3. Check the plan: it has all key points, explicit API endpoints with doc links, test checkpoints, and anticipated downstream issues.
  4. Ask: "What clarifying questions do you need from me to make this plan even better?"
  5. Build with a fast model for simple work; use the frontier model for novel or complex builds.
  6. **Marshmallow tower:** build small, test, then expand.
  7. Test in the terminal so you can see progress and Ctrl-C when it stalls; ask it to print logs.
  8. If it loops on errors, start a new plan mode: "why are these errors happening, fully flesh out a fix."
  9. Run locally or on GitHub Actions cron; use Railway or Trigger.dev for heavier jobs. Give the agent API or MCP access to the host so it can read errors itself.
  10. Skip front ends; trigger with webhooks.

## 2. Copy formulas

**Subject / preview text.** Think about how the push notification looks. There are two schools. [k3uGNuXtzQM]
- *Colleague/customer look:* "hey, I saw the negative Google review and I had a question about it." Eric reports "tons and tons of engagement."
- *Whole offer in the preview:* "We help companies target their entire target addressable market in less than 3 months." Eric credits Taylor for this line.
- ⚠️ Eric is retiring AI flattery openers ("Hey, I saw you help fitness enthusiasts breathe better…"). He believes they now hurt campaigns.

**First lines (researched)**
- Case study hook, as run for Clay: "Hey, I saw that great case study you had with {customer} and how you helped them {result}, and I had a question." Next line: "How are you finding more customers like those in your case studies?" Then the pitch (lookalikes) and "Would you want to chat?" [cfpLJqkmB6I]
- Found-problem hook: "Hey, I saw the negative review about the holes in your parking lot. Do you want us to take care of those?" [k3uGNuXtzQM]
- Stated-goal hook: reference their published sustainability or impact goals, optionally with a screenshot of that page. [cfpLJqkmB6I]
- Data-gap hook (sales tax): "You're collecting sales tax in {N} states; you're missing {X, Y}." If they're fully covered: "You're doing a great job, is it a lot to handle? We could take it off your plate." [cfpLJqkmB6I]

**Body**
- **Creative Ideas campaign** (his best across customers): "Here's three ideas of how I think we can help you." [k3uGNuXtzQM][cfpLJqkmB6I]
  - Define what bullets 1, 2 and 3 should each be about.
  - Feed in the company data, and add guardrails.
- **Pain / worry reframe** (Josh Braun): "How do you know that your current accountant is using every legal loophole to get you as much money back from the government as possible?" [cfpLJqkmB6I]
  - Template: *"How do you know your current {provider} is {doing the thing they fear isn't happening}?"*
- **Straight down the middle:** "Hey, we automate sales tax compliance. Do you need our help?" [k3uGNuXtzQM]
- **Outlook recipients:** send shorter emails than usual. [k3uGNuXtzQM]

**CTA**
- Explain *why* you need the time. For reputation management, "Could we chat for 15 minutes about that review and see if it was unwarranted so we could help build the case for Google on your behalf?" beat "Would it make sense to chat?" Eric quotes "Kirsten told me it was like 2.7x" and rounds it to "2.5x." [k3uGNuXtzQM]
- Tie the lead magnet *to the call*. For the chocolate company: "To show you how it works, let's hop on a call and as an example, I'll send you a free chocolate basket." This raised bookings; no number was given. [cfpLJqkmB6I]
- Attach an offer to the ask: "Would you want to book a call? We can launch a free campaign for you." Eric says this "blew out" the AI-personalization gains. [cfpLJqkmB6I]

**Follow-ups**
- Optimize Email 1, the top performer across sequences. Late steps (e.g., Email 6) draw more spam reports. [cfpLJqkmB6I]

**Positive-reply handling** [-v-WBPE1gaI]
1. Reply ASAP with two manual times plus a link: "Hey {Name}, thanks so much for the response. Are you available Tuesday at 10 or Thursday at 2? If it's easier, here's my calendar link."
2. If there's no booking, raise the stakes with a case-study match: "The reason we were so interested in meeting is because you fit {criteria}, {criteria}, and I found {X}. We did this for {similar company}; here's the process… would love to walk you through it."
3. Optionally send a lazy bump.
4. Next, do free work: a competitor audit, a site teardown, or a sample list ("I think you're targeting CEOs in Tampa, here's a list already").
5. Rotate case-study and free-work emails; always re-offer times plus the link.
6. Use **status alignment** (Oren Klaff) on the follow-up: "I lost Tuesday at 2 to another meeting and something popped up Thursday…" Then offer new times.
7. Optionally send a **calendar invite marked free** (set team boundaries first): "Instead of the back and forth, I put time on your calendar for Tue 10am. I marked it not busy so it won't block you. Accept and I'll mark it busy, or propose a new time."
8. Multi-thread through LinkedIn and phone.

**Scraped-engager lists.** Never say "I saw you liked {competitor}'s post." Send your normal best campaign. [sMcolK-mvnE]

## 3. Offer / angle patterns

- **Pay-on-result:** "We could get [the negative review] taken down and you only pay after we get it taken down." [k3uGNuXtzQM]
- **Bring-your-own-data benchmark:** "Bring three contracts you feel you're overpaying for; we'll tell you what others pay for similar contracts." This beat "want a demo of our procurement platform?" [k3uGNuXtzQM]
- **Signal-list lead magnet** (for outbound agencies): "Every person in the US, director level and above, who joined their company in the last month. Request access to the Google Sheet." Built from Clay new-hire data. [cfpLJqkmB6I]
- **Framework-on-call:** "Would you want to see our framework for consistently getting {result}?" No asset required. [cfpLJqkmB6I]
- **Free test / free campaign** as the call incentive. [cfpLJqkmB6I]
- **Found-problem angles:** negative reviews, missing states, stated goals. [k3uGNuXtzQM][cfpLJqkmB6I]
- **Case-study lookalike:** "We could help you find more customers like {case study}." [cfpLJqkmB6I]
- **Creative Ideas + trial CTA.** For Instantly this "still a year later outperformed" every signal tested, including big sales teams, founder-led sales, new VP of Sales, multiple VPs, and no DMARC. [cfpLJqkmB6I]
- ❌ Avoid "we get you leads." It is overused and attracts poor calls. [k3uGNuXtzQM][cfpLJqkmB6I]

## 4. List-building & enrichment tactics

**Three directions of list building** [k3uGNuXtzQM]

| Direction | How | Use when |
|---|---|---|
| Forward | Database filter (Apollo, Clay, LinkedIn), then clean | Easy, self-reported industries |
| Backward (Eric's preferred team default) | Take the client's customer and pipeline DNC list, enrich in Clay, have an LLM summarize common industries, description keywords, headcount and location, add onboarding-call notes, then build forward filters from that data | Most campaigns |
| Circular | Seed about 30 perfect-fit companies, write a fit prompt, call a lookalike API, fit-check with a cheap reasoning model through OpenRouter, add passes to the DB, re-seed | Hard-to-define TAM only |

- **Circular kill rule:** "if you pull 10 batches and after 10 batches less than 15% of the list is good fits… kill the workflow." Pass already-found companies as an exclude list. Eric says Exa supports large excludes, Ocean.io and DiscoLike "should," and Clay "doesn't really." [k3uGNuXtzQM]
- **Messy-industry cleaning.** Pull the broad self-reported industries (banking, financial services, lending). Run a cheap LLM (open-source "OSS 20B") on the company description: "Is this a business loan company?" Verify passes against the website. [k3uGNuXtzQM]
- **Prompt capture.** Record a Loom of yourself manually qualifying companies while talking out loud, then turn it into the AI prompt. [k3uGNuXtzQM]
- **LinkedIn engager lists** [sMcolK-mvnE]
  - Sources: your own posts (best, "shooting fish in a barrel"), competitors' posts, or viral topic posts.
  - Scrape **people's** posts, not company-page posts; company pages underperform. Map company → employees → their posts.
  - Build parameters: "fetches up to 50 posts per person, extracts up to 200 likers per post." Output a CSV, enrich in Clay, then apply the usual industry and title filters.
  - Run a cron for new posts so fresh engagers feed a workflow.
  - Company followers require a Sales Nav seat listed as working at that company, so use a vendor.
- **Local businesses** [zC7yIRwkyaY][cfpLJqkmB6I]
  1. Google Maps scrape by keyword across every US zip.
  2. Claygent finds the owner's name.
  3. Guess or verify the email.
- **Competitor footprints** [cfpLJqkmB6I]
  - BuiltWith for installed tech.
  - Clay Jobs source for keywords like "you'll manage Salesforce/QuickBooks," which catches tech not visible on the site.
- **Headcount triangulation** [cfpLJqkmB6I]
  - Compare LinkedIn associated members (accurate for SaaS) with the self-reported LinkedIn bracket (better for e-com and local) and Glassdoor's self-reported count.
  - Reconcile with Claygent.
- **Unstructured signals.** Claygent finds about/blog/case-study/sustainability pages. Zenrows handles proxied scraping of programmatic-SEO pages. Instant Data Scraper is a quick Chrome option. ChatGPT-written Python can scrape directories like Yelp. [cfpLJqkmB6I]
- **Email-finding cost control** [zC7yIRwkyaY]
  1. Cache every found email in Supabase.
  2. Re-verify anything older than 30/60/90 days.
  3. Waterfall: LeadMagic → Prospeo → MillionVerifier pattern-guessing.
  4. Log misses for a later bulk retry with other providers.
  - Eric: "we're never paying for any emails."
- **Ops automation examples** (built in Cursor) [zC7yIRwkyaY]
  - A form fill (Apollo URL or company filter plus persona) pulls the first 50 contacts for prompt-building, auto-creates the Smartlead campaign, and stages all contacts in Supabase.
  - Daily 2 a.m. campaign refill.
  - Batch API with cached inputs for cheaper ICP scoring.
  - AI categorization of master-inbox replies.
  - Replaces manual CSV-to-Clay uploads.

## 5. Deliverability / inbox infra notes

- **Insurance infrastructure.** Keep warm backup inboxes at 1:1 with active volume, or at least 0.5:1. The agency provisions for 5,000/day when a client sends 1,000/day. [k3uGNuXtzQM][cfpLJqkmB6I]
- **Don't rehab burned domains.** Kill the domain, swap in insurance inboxes, order new domains, and keep monthly spend flat. Eric says this changed from "rest it 45 days" two years ago. [k3uGNuXtzQM][cfpLJqkmB6I]
- **Burn diagnosis, in order** [cfpLJqkmB6I]
  1. **Reply rate:** no replies, no OOOs, no negatives. "If your reply rate is below 1%, you want to try to shut down the campaign."
  2. **Bounces:** read the codes. "Doesn't exist" means bad data. "Spam," "message blocked" or 550 point to burned domains. Paste the codes into an LLM.
  3. **Warm-up score** in Instantly or Smartlead: if it drops "below 100%," assume the inbox is burned.
  4. **Last resort:** turn on open tracking for 2 days. Inbox placement "should be really getting… a 60% open rate" thanks to Apple auto-opens. Cut inboxes near "10%."
- **Volume per inbox** [cfpLJqkmB6I]
  - Start at 30 per day per inbox.
  - If a campaign shows a "2% response rate," it is safe to push to 50 per day while you watch for drop-offs.
- **Rush launch.** Use a subset of new inboxes at about 5 per day, 1 per hour. Let the rest warm the full 2–3 weeks. [cfpLJqkmB6I]
- **Domain age matters more over time** [k3uGNuXtzQM][cfpLJqkmB6I]
  - In one Fortune 1000 campaign, 4-week-warmed inboxes placed badly and 6-week ones got through. Eric explicitly called this one example.
  - Keep tiered warm-up batches: 2 weeks, 4 weeks, 2 months.
  - Buy .com/.co domains during Porkbun or Dynadot sales and let them age about 3 months before adding inboxes.
- **Domain naming matters less than people think.** Generic domains, some 30 characters long, still get positive replies. [cfpLJqkmB6I]
- **Outlook and secure gateways** [k3uGNuXtzQM]
  - Default: send to all providers, including Proofpoint and Mimecast.
  - Restrict to Google-only only for new clients without momentum, or when deliverability degrades.
  - Re-enable once domains reach 4 weeks of warm-up, ideally 6.
- **Images and screenshots.** Acceptable if net positive replies rise; you can remove them later. Spam complaints are the worst outcome. [cfpLJqkmB6I]
- **Automated infra analytics.** Pull the Instantly or Smartlead API into Supabase and have Cursor recommend which domains to cancel and which insurance domains to rotate in, applied after human approval. Take intraday snapshots (12, 3, 6) rather than reviewing yesterday at the next morning's call. [zC7yIRwkyaY][k3uGNuXtzQM]

## 6. Metrics & testing cadence

- **Claimed scale:** "8 million to 11 million cold emails a month" [zC7yIRwkyaY]; "over 30 million cold emails" in 4 years; "averaged 222 positive responses every single day" over the past 90 days [cfpLJqkmB6I]; "10 million to 15 million rows a week" of CSV processed [zC7yIRwkyaY].
- **Alpha ladder** (e-com sustainability plug-in): 1 positive per 650 with no segmentation → 1 per 250 with the Claygent sustainability-goal line → 1 per 120 with a screenshot of their page. [cfpLJqkmB6I]
- **CTA "explain why you need the time":** ~2.5–2.7x vs a generic time ask. [k3uGNuXtzQM]
- **Chocolate case:** a "3% reply rate" but few meetings until the CTA was tied to the lead magnet. [cfpLJqkmB6I]
- **Testing rules** [cfpLJqkmB6I]
  - Test at least a full sentence; prefer whole-chunk changes such as pain vs benefit framing or an AI line vs none.
  - Don't A/B micro-CTAs like "worth a chat?" vs "open next week?"
- **Leading-indicator dashboard** [cfpLJqkmB6I]
  1. Positive-reply rate vs a per-client baseline, stored in Airtable; if it drops below baseline, rewrite.
  2. Net-new Email 1 volume.
  3. Inbox reputation, auto-rotated.
  4. Open-rate spot checks (being automated).
- **Reply-rate floor:** below 1% means pause and fix. [cfpLJqkmB6I]

## 7. Tools mentioned

| Tool | Use |
|---|---|
| Cursor (plan mode + agent; "Composer" for fast builds) | Builds all automations: list pulls, analytics, campaign setup, scrapers [zC7yIRwkyaY][sMcolK-mvnE] |
| Supabase | Contact/company staging, email cache, sending analytics store [zC7yIRwkyaY][k3uGNuXtzQM] |
| GitHub Actions / Railway / Trigger.dev / Vercel | Cron jobs and hosting [zC7yIRwkyaY] |
| Smartlead / Instantly (APIs) | Sequencing, warm-up scores, analytics pulls, Google-only send toggle [zC7yIRwkyaY][k3uGNuXtzQM][cfpLJqkmB6I] |
| Clay (+ Claygent, Google Maps source, Jobs source, lookalikes) | Enrichment, unstructured research, local leads, tech/job signals, golden-ICP branching [k3uGNuXtzQM][cfpLJqkmB6I][sMcolK-mvnE] |
| Apollo | Source URLs for automated campaign setup, forward lists [zC7yIRwkyaY][k3uGNuXtzQM] |
| LeadMagic → Prospeo → MillionVerifier | Email-finding waterfall [zC7yIRwkyaY] |
| OpenRouter (cheap reasoning models), "OSS 20B" | Bulk fit classification [k3uGNuXtzQM] |
| DiscoLike, Ocean.io, Exa, Clay lookalike | Lookalike expansion for circular lists [k3uGNuXtzQM] |
| RapidAPI LinkedIn endpoint (name not given) / Trigify | Post, liker and commenter scraping [sMcolK-mvnE] |
| Scrape li (per transcript) + Sales Nav | Company-page follower scraping [sMcolK-mvnE] |
| BuiltWith | Tech-install targeting [cfpLJqkmB6I] |
| Glassdoor | Headcount triangulation [cfpLJqkmB6I] |
| Zenrows, Instant Data Scraper, ChatGPT-written Python | Web scraping [cfpLJqkmB6I] |
| Porkbun, Dynadot | Discount domains to age [cfpLJqkmB6I] |
| Airtable | Baseline reply-rate tracking [cfpLJqkmB6I] |
| Loom, voice memos, ChatGPT voice | Context capture for prompts and plans [zC7yIRwkyaY][k3uGNuXtzQM] |

## 8. Caveats / dated claims to re-validate

- **Model advice is dated** (Opus 4.5, "GPT 5.1," Cursor Composer, from Thanksgiving 2025). Swap in the current frontier models. [zC7yIRwkyaY]
- **The 6-week warm-up finding comes from one Fortune 1000 campaign.** Eric: "don't… say Eric said you have to warm up 6 weeks." [cfpLJqkmB6I]
- **Outlook filtering severity** was described as current and possibly temporary. Re-check your own Instantly provider-level stats. [k3uGNuXtzQM]
- **"Warm-up score below 100% = burned"** is their internal rule, not a platform standard. [cfpLJqkmB6I]
- **The ~60% open benchmark** depends on Apple auto-opens. Only use open tracking briefly for diagnosis. [cfpLJqkmB6I]
- **"Clay Operator" browser automation** was described as upcoming. Verify it exists before planning around it. [cfpLJqkmB6I]
- **The 2.5–2.7x CTA lift** is secondhand ("Kirsten told me"), and the 222/day figure is self-reported. [k3uGNuXtzQM][cfpLJqkmB6I]
- **LinkedIn scraping carries ToS and vendor-stability risk** ("those services go in and out of business"). The RapidAPI endpoint was not named. [sMcolK-mvnE]
- **Eric's agency runs outbound for Clay and Instantly,** so treat tool enthusiasm with that in mind. [cfpLJqkmB6I]
- **Adapting to Lorenzo's stack:** where Eric uses Smartlead, the Instantly equivalents are the warm-up score, the provider-matching / Google-only send setting, and the analytics API. Verify the exact setting names in the current Instantly UI.

## Source videos
- zC7yIRwkyaY — How I Use Cursor as a Non-Technical Founder
- k3uGNuXtzQM — Cold Email First Principles Thinking
- sMcolK-mvnE — Scrape LinkedIn Post Likes Comments for Outbound Campaigns
- cfpLJqkmB6I — I sent 10,000,000 cold emails, here's what works in 2025
- -v-WBPE1gaI — How to Increase Meetings Booked Per Positive Response
