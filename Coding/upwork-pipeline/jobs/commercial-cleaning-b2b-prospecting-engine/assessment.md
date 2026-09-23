# Private assessment - AI Automation Developer, commercial cleaning B2B prospecting

## Time
- Phase 1 realistic: 25 to 40 hours. That is the discover, enrich, research, score, approve, push-to-HighLevel loop running daily and not lying about its numbers.
- Rough split: Outscraper pulls plus normalization 4 to 6 hours; Postgres schema, dedupe on place id and normalized phone, and the seen-before check 4 to 6; Apollo enrichment with the no-decision-maker park 4 to 6; research agent, scoring prompt and the score gate 6 to 10 including prompt iteration on real buildings; Slack approval buttons plus the decision webhook 4 to 6; HighLevel contact, tag, opportunity and the follow-up workflow trigger 4 to 6; logging, error trigger and alerting 2 to 4.
- Calendar: 2 to 3 weeks to a working daily engine, assuming their API keys land in week one. The scoring prompt needs a week of real output and human rejections before it is worth trusting.
- "Full-time" in the post is a flag. Phase 1 is a project, not 40 hours a week. Confirm what they actually want before agreeing to an hourly seat.

## Likelihood
- Good fit on substance. Every named tool is either something he builds with daily or a plain REST call. The research agent, the score gate, the human approval loop and the error path are all patterns already in his own outbound stack.
- Commercial cleaning is one of his own 2026 lead-scrape niches. He has worked this exact lead data himself, so he knows the ICP problems before they say them: buildings without a named decision maker, chain locations with a corporate facilities contact three states away, phone numbers shared across suites, and the sq ft number being wrong more often than not. That is honest and it is worth saying.
- Main build risk is Apollo hit rate on facilities and office managers for small buildings. It will not be high. The park-for-manual-enrichment branch exists because of that, and the proposal should not promise a decision maker on every record.
- Second risk: Outscraper data quality on the size filter. Square footage is rarely in the Google profile, so "over 5,000 sq ft" is inferred from category, review volume and the building record, not read off a field. Set that expectation on the call, not after the invoice.
- Third risk: HighLevel API access depends on their agency versus sub-account setup and who holds the keys. If they are on a locked agency plan under someone else, the CRM half stalls.
- Fourth risk: brand new client account, 0 contracts, 0 feedback, 0 hires. Payment method may not be verified yet. Milestones, not open-ended hourly, until the first deliverable is accepted.
- Recurring software on their card, not his: Outscraper credits per search, Apollo credits per enrichment, OpenAI per research call, HighLevel subscription, and Postgres hosting if they do not have one. Rough at a real daily volume: $150 to $500 a month. Say this early so a $10 to $20 hourly does not quietly absorb tooling.

## Standard pricing
- Market for a senior build of this scope, API integrations plus agent plus human-in-the-loop plus a real database: $40 to $85 an hour, or $3k to $6k fixed for phase 1.
- Their posted range is $10 to $20 an hour, full time, expert level. The top of their range is roughly a quarter to half of market for what they described. They wrote a senior architecture post at junior rates.
- He bids under market on purpose. The reference number is $3k to $6k for phase 1; the call decides scope and rate, and the Loom is what makes that conversation possible instead of a bidding war with 55 applicants.

## Ask before quoting
- Which metros and zip clusters first, and which building categories actually convert for them today?
- How many new prospects a day do they want in the pipe? That drives Outscraper and Apollo credit spend more than anything else.
- What does their HighLevel pipeline look like now, which stages, and who works the leads once they land?
- Where does approval happen, Slack or inside HighLevel? The post says human approval but not where.
- Postgres, or do they already have a database or warehouse they want this written to?
- Hours per week they expect, and is phase 1 a fixed scope or an ongoing hourly seat?
- Who holds the Outscraper, Apollo, OpenAI and HighLevel accounts, and does he get his own keys or a seat?

## Flags
- Brand new client account, zero history, US based, Chicago timezone. Do not assert a location for Lorenzo.
- 19 connects to apply and bids already at 5 to 55. Apply early or not at all.
- Post asks for Python and/or n8n. The Loom shows n8n because it shows the logic fastest. Frame honestly: the video shows the flow in n8n, production can ship as Python services if they prefer.
