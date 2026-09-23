# Delivery assessment (private, not for the proposal)

**The post:** one line. "n8n, apify and Snov.io, openai, create marketing cold email funnel."
Fixed $50, expert level, US client, avg bid ~$47. That is the entire brief.

**Time.** 8 to 12 hours of real build across roughly 1 to 2 calendar weeks. The n8n side
is a day: Apify run + poll, Snov.io find/verify/add-prospect over HTTP, one OpenAI agent
with a website tool and a forced output shape, a switch on reply intent. The rest is
waiting on the client: API keys, an Apify actor that returns the right companies, a
Snov.io campaign that already exists to add prospects into, and one real run to prove
the personalization is not generic.

**Likelihood / what actually breaks.**
- **Apify billing is per result and per compute unit.** A 300-company daily run is a real
  monthly line item, and cancelled runs still bill. Actor choice (Google Maps place
  crawler vs a LinkedIn actor) changes both the cost and how clean the output is.
  LinkedIn actors also break more often than Maps ones.
- **Snov.io burns two separate credit pools** (email finder credits, verification credits)
  and the plan tier caps campaign count and daily send volume. If their tier is too low
  the funnel is throttled by the subscription, not by the build.
- **Deliverability is the whole game and the post does not mention it.** No sending
  domains, no mailbox count, no warmup, no SPF/DKIM/DMARC. Lorenzo runs 100k+ cold
  emails a month on Instantly, which is the adjacent tool to Snov.io, so he knows this
  first hand: a perfect funnel on cold, unwarmed domains still lands in spam. Say it on
  camera as the one judgment call, do not assume they have it handled.
- **The Snov.io reply webhook may not be available on their plan.** Fallback is polling
  the campaign for replies on a schedule, which is fine but is extra work nobody quoted.
- Everything above happens inside the client's Apify and Snov.io accounts, which is the
  part that overruns.

**Rate vs market.** $50 fixed for scrape + enrich + verify + AI personalize + campaign
load + reply routing is roughly 3 to 5 percent of market. Defensible range for this
scope is **$1,200 to $2,500 fixed**, or $75 to $125/hr. Avg bid ~$47 says the whole
applicant pool is treating it as a test task, not a build. Treat $50 the same way:
a paid trial that gets a real system in front of them, priced on purpose, with the
actual number raised once scope is on the table. Do not build the full funnel for $50
without saying out loud what the full funnel costs.

**Recurring software the client pays (name these, they are not in the post).**
Apify ~$49/mo plan plus per-result usage; Snov.io ~$39 to $99/mo depending on credits
and campaign count; OpenAI ~$20 to $60/mo at a few hundred personalized lines a day;
plus sending domains and mailboxes if they do not already have warmed ones.

**Ask before quoting.**
1. Which Apify actor, and who pays the Apify / Snov.io / OpenAI bills?
2. What Snov.io plan are they on, and does it expose reply webhooks?
3. How many sending domains and mailboxes, and are they warmed?
4. What is the ICP and the target volume per day? 100/day and 2,000/day are different builds.
5. Is $50 the whole project, or the first paid piece of something larger?
