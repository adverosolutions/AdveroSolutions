<!-- distill: batch_05_of_11 | videos: QyCqMpivjlA, 3THIdISjTkk, dj-RHJ7y4vY, BbcONjqpCkU, gzAX9hA6g48 | model: opus | elapsed_s: 55 -->

# Playbook batch: Colleague-style subject lines, signal mining on positive replies, AI research chains, and 3 north-star metrics

## 1. Frameworks / mental models

- **Write the subject line for the lock screen, not for an ad.** On a push notification the prospect sees only the subject line and the first line (preview text). Ask: "What feeling does this pair give?" [QyCqMpivjlA]
- **"Would a colleague or customer send this?"** Copy the style of subject lines the prospect already opens: messages from peers in the same industry, from customers, or from coworkers. [QyCqMpivjlA]
- **Open loop.** The subject line raises a question, the preview text deepens it, and the body delivers on it. Avoid bait-and-switch: the body must pay off the subject line. [QyCqMpivjlA]
- **Ogilvy chain.** The subject line's only job is the open. Each line's job is to get the next line read. [QyCqMpivjlA]
- **Offer first, signals second.** A better, easier-to-say-yes offer often removes the need for elaborate signals. [3THIdISjTkk]
- **Signals are unvalidated guesses.** A lift in positive replies doesn't prove the signal caused it. The prospect may have said yes anyway. [3THIdISjTkk]
- **Mine signals after the reply, not only before the send.** Enrich every positive (and negative) reply for every hypothesis, then look for patterns. Run it in real time, because agents are best at "what's true now / last 90 days." [3THIdISjTkk]
- **Structured vs. unstructured data.** Structured fields, like the "new in role" date, are the same for everyone and overused. Unstructured public research, like pricing pages, is the edge. [dj-RHJ7y4vY]
- **One AI step, one job.** Claygent does the research. A separate AI column writes the message. Don't ask one prompt to do both. [dj-RHJ7y4vY]
- **Remove rep micro-decisions.** Encode qualification and messaging rules as Clay conditional formulas so no rep hand-checks LinkedIn or websites. [gzAX9hA6g48]
- **Hormozi rule for dashboards.** "If the metric changes but your behavior doesn't, you're tracking the wrong metric." [BbcONjqpCkU]

## 2. Copy formulas

**Subject line checklist** [QyCqMpivjlA]
- [ ] 2–4 words max
- [ ] A/B test proper case vs. sentence case vs. all lowercase
- [ ] Personalization must feel natural. `{{company}}` "seems to perform really well," but normalize company names (strip Inc, LLC, and so on)
- [ ] No emojis, exclamation points, multiple question marks, ALL CAPS, or corporate tone
- [ ] Always test against the baseline subject lines `quick question` and `intro`, paired with a strong preview text ("they still continuously work")
- ❌ Anti-example: "don't hire your next engineer until you do this"

**Subject + preview pairs (quoted)**
| Pattern | Subject | Preview / first line | Source |
|---|---|---|---|
| Customer voice | `pizza orders` | "Hey {first}, I tried calling {phone}, but I figured email would be easier." The body then covers getting more pizza orders. | [QyCqMpivjlA] |
| Coworker voice | `sales reports` | (a coworker or colleague-style ask) | [QyCqMpivjlA] |
| Competitor hook | `{company} competitors` | "I have a list of people engaging with {competitor}" | [QyCqMpivjlA] |
| Baseline | `quick question` / `intro` | a strong value-bearing preview | [QyCqMpivjlA] |

**Unstructured-research first line (pricing to LTV)** [dj-RHJ7y4vY]
> "I saw on your pricing page that your {plan} is {price}. If a sizable company signed up, I could imagine you're charging anywhere from {$X} to {$Y} per month."

Template: `I saw on your {public page} that {specific fact}. {Implication for their business / LTV}.`

**Conditional second line** [gzAX9hA6g48]
- Keep one base template and swap line 2 through a Clay formula that outputs the actual sentence as a custom variable:
  - `{{line2_fundraise}}` if they raised money
  - `{{line2_international}}` if they have non-US hires
  - `{{line2_new_role}}` if the contact is new in role

**Follow-ups:** Most positive replies come from email 1 [BbcONjqpCkU]. Prioritize email 1 volume and quality over sequence length.

## 3. Offer / angle patterns

- **Competitor-engagement list.** "A list of people engaging with your competitors' content." Eric calls it a "really high-performing campaign that we run for ourselves." It won't fit every offer. [QyCqMpivjlA]
- **Anything about the prospect vs. their competitors** "consistently works." [QyCqMpivjlA]
- **Lead with a "small bite" of the offer.** Put the most compelling tangible thing in subject + preview, then explain how in the body. [QyCqMpivjlA]
- **Direct revenue outcome** for SMB or local businesses, for example "more pizza orders" for restaurants. [QyCqMpivjlA]
- **Signal-branched messaging** (fundraise / international team / new in role) on one offer, e.g. offshore sales staffing. [gzAX9hA6g48]

## 4. List-building & enrichment tactics

**3-tier campaign test structure** [3THIdISjTkk]
1. **Broad:** anyone in the TAM who fits the ICP and has a valid email. The goal is the widest variety of positive replies.
2. **Segmented:** a specific vertical, headcount band, and department or title.
3. **Signal:** high-confidence triggers such as new in role or just announced a product.

**Positive-reply signal mining workflow** [3THIdISjTkk]
1. When a reply is marked positive (and optionally negative), a webhook sends it to a Clay table.
2. Run the full "signal checklist." Make it custom to the offer. Examples: recent news (Claygent / parallel.ai), new tech installed (BuiltWith), AE count, AE:SDR ratio, whether they have a sales ops hire, LinkedIn posts in the last week.
3. Once you have 10–50+ replies, compare positive vs. negative cohorts using Sculptor (in Clay), Claude Code, or Codex.
4. Promote the winning signals to front-end targeting in the next campaign.
- Eric's example: they expected the AE:SDR ratio to matter, but "having a sales ops person" turned out to be the real predictor. [3THIdISjTkk]
- Run it in real time, not retroactively. Reconstructing why someone replied two months ago is hard. [3THIdISjTkk]

**Claygent research chain** [dj-RHJ7y4vY]
1. Claygent column: plain-language ask ("find if pricing is public on the website and summarize it"). Let Clay generate the prompt, then review it.
2. Spot-check outputs against the actual sites. Correct Claygent with where you found the info manually.
3. A separate AI column turns the research into one natural sentence. Write the context with speech-to-text, but type and refine the **examples** by hand. Examples drive quality.

**Clay qualification and routing formulas** [gzAX9hA6g48]
- Clay's 1-credit company enrichment returns LinkedIn company data plus estimated revenue, industry, sub-industry, "scale scope" (local, national, international), business type (B2B), funding amount, and headcount. Eric calls it "so slept on."
- Formulas (natural language in Clay):
  - `must have` = employee count > 30 AND business type = B2B
  - `fundraise messaging` = total funding ≠ "unknown"
  - `international messaging` = non-US employee count > 0 (from a Clay employee-location integration)
  - `golden` = all of the above are true. Route these to scarce channels: calls, and LinkedIn (quoted limit of "25 LinkedIn messages a day").

## 5. Deliverability / inbox infra notes

- **Remove open-tracking pixels.** Eric says Google shows a banner warning that hidden images "is often what spammers do" and offers to report spam. After the banner appeared, reply rates dropped. [BbcONjqpCkU]
- **Kill and rotate domains by relative reply rate:**
  - Example: customer average 2% while one domain is at 0.5%, so kill that domain
  - Example: average 0.9% while one domain is at 0%, so pull it
  - Review weekly at the domain level. [BbcONjqpCkU]
- **Don't rely on spam tests or ESP "inbox reputation" scores.** Eric says both are unreliable and that he has seen them contradict real results. Use reply-rate and contacts-per-positive trends instead. [BbcONjqpCkU]
- **Verification stack:** cached internal data, Million Verifier, Prospect.io, and the SmartLead API. Bounce rate was removed from the daily dashboard once the stack was dialed in (transcript: "they 2% all the time", which likely means under 2%). [BbcONjqpCkU]

## 6. Metrics & testing cadence

**The 3 north-star metrics** [BbcONjqpCkU]

1. **Reply rate:** tracked overall, per campaign, and per domain (weekly).
   - Target: "above a 1% reply rate"
   - "0.1%" usually means you're going to spam, so swap domains
   - "0.6% or 0.7%" suggests the list is less targeted than you think. Relevant-but-uninterested prospects still reply "not interested," while irrelevant ones ignore you.
2. **Contacts per positive reply:** used for forecasting and as an early spam and list-drift alarm.
   - Example: "1 per 300" jumping to "1 per 700" midweek means check inboxes
   - As lists widen to adjacent titles, headcounts, or industries, watch this ratio and rein the list in if it drifts past the proven baseline (e.g., "1 per 500")
3. **Net-new emails per day:** count first-touch email-1 sends, not total volume.
   - SmartLead and Instantly can drift toward sending follow-ups, so hold net-new sends steady.

**Benchmarks are relative** [BbcONjqpCkU]
- Google reputation management offer: "we get one positive response for every 70 people." If you aren't getting 1 per 200, "you got something really wrong."
- Enterprise financial software can tolerate much lower rates if LTV:CAC works.
- "10,000 companies → 120 positive responses" would be "a great campaign." [3THIdISjTkk]

**Testing cadence**
- Check the three metrics daily, and domain-level reply rate weekly. [BbcONjqpCkU]
- Mine signals continuously on each positive reply. [3THIdISjTkk]
- Always A/B subject lines against `quick question` / `intro` and against casing variants. [QyCqMpivjlA]

## 7. Tools mentioned

| Tool | How it's used | Source |
|---|---|---|
| Clay | Enrichment tables, conditional formulas, positive-reply signal table | [3THIdISjTkk][dj-RHJ7y4vY][gzAX9hA6g48] |
| Claygent | Unstructured web research, e.g. pricing pages and company news. Clay can auto-write its prompt. | [3THIdISjTkk][dj-RHJ7y4vY] |
| Clay model "Neon" / GPT-4o mini | Neon for demos; 4o mini is "our daily driver" for Clay agents | [dj-RHJ7y4vY] |
| Clay 1-credit company enrichment | Headcount, B2B type, scale scope, funding, estimated revenue | [gzAX9hA6g48] |
| Sculptor (in Clay) / Claude Code / Codex | Pull insights from the enriched reply table | [3THIdISjTkk] |
| parallel.ai Task API | Deep unstructured company research at scale, called inside Clay. Described as more detailed and slower than Claygent. | [3THIdISjTkk] |
| BuiltWith | Detects newly installed tech | [3THIdISjTkk] |
| LinkedIn scrapers / Prospector | Pull LinkedIn data to feed research | [3THIdISjTkk] |
| Wispr Flow ("Whisper Flow") | Speech-to-text for writing prompt context | [dj-RHJ7y4vY] |
| Million Verifier, Prospect.io, SmartLead API | Email verification stack | [BbcONjqpCkU] |
| SmartLead / Instantly | Sending. Watch follow-up vs. net-new drift. Eric distrusts their inbox reputation score. | [BbcONjqpCkU] |

## 8. Caveats / dated claims to re-validate

- **Agency scale claims:** "8 million cold emails every month" and "over 62,000 positive responses in 2025." These are self-reported. [QyCqMpivjlA][BbcONjqpCkU]
- **Gmail open-pixel spam banner:** confirm current Gmail behavior, and whether it applies to Instantly's tracking setup, before disabling tracking on AdveroSolutions campaigns. [BbcONjqpCkU]
- **Clay features:** the 1-credit enrichment fields (it wasn't formally announced), the Neon model, and Sculptor may change in credit cost or availability. [gzAX9hA6g48][dj-RHJ7y4vY][3THIdISjTkk]
- **"GPT-4o mini as daily driver":** may be superseded by newer models in Clay. [dj-RHJ7y4vY]
- **parallel.ai cost:** "50 cents" was a hypothetical, not a quoted price. [3THIdISjTkk]
- **Transcript noise:** the bounce-rate figure is garbled. The pizza example and "sales reports" are illustrative, with no stats given. [BbcONjqpCkU][QyCqMpivjlA]
- **Instantly vs. SmartLead:** Eric's shop runs SmartLead heavily. Map the equivalent Instantly features (per-domain analytics, email-1 volume caps, webhooks on positive replies) before copying the workflows. [BbcONjqpCkU][3THIdISjTkk]

## Source videos
- QyCqMpivjlA — How We Write Cold Email Subject Lines for 8M Emails/Month
- 3THIdISjTkk — How We Test Cold Email Signals with Clay
- dj-RHJ7y4vY — How to Cold Email Better Than 99% of People (Using AI)
- BbcONjqpCkU — Top 3 Metrics for Evaluating Cold Email Campaigns
- gzAX9hA6g48 — Steal This Cold Outreach Strategy, It'll Double Your Sales
