# Assessment (private) - AI Engineer - AI Agent , RAG & Automation

## Time
- Discovery (what the post hires for): 6-10 hours over 1-2 weeks. Two or three calls with ops, dispatch and customer service, a process map, a ranked list of 3-5 automations with effort and payoff, a tool recommendation.
- The example build on the canvas, done for real: 25-40 hours, 2-3 calendar weeks. Most of it is the shipment system API (auth, field mapping, which endpoints exist) and loading and cleaning the SOPs, not the n8n flow.
- Realistic total if they go to implementation: 35-50 hours across 3-5 weeks, including review rounds.

## Likelihood
- Unknown and decisive: which system holds shipment status (a TMS, a WMS, a carrier portal, spreadsheets) and whether it has an API. No API means a database read, an export or a scraper, and the estimate moves a lot.
- SOP quality: RAG answers are only as good as the documents. Old, contradictory or scanned-PDF SOPs need cleanup before the agent is trustworthy.
- Language: a Polish team may ask in Polish and keep SOPs in Polish or English. Claude handles both; the embedding search should be tested with real questions in both.
- Unverified for Lorenzo: the n8n HTTP tool's placeholder handling inside a JSON body (the draft-update tool) needs a test run; the shipment endpoints on the canvas are illustrative until he sees their API docs. Say "this is the shape, the endpoints come from your system's docs".
- Single-vector-per-section ingestion is fine for a demo; a real rollout needs file sync and chunking (named on the sticky as the next add-on).

## Standard pricing
- Market for AI automation consulting plus an agent build: $60-120/hour, or $1,500-3,000 for discovery and $4,000-8,000 for a first agent in production.
- The post's $20-30/hour is well under market (bids avg $26.67). At $30/hour, 35-50 hours is $1,050-1,500.
- Recurring software: n8n cloud or self-hosted ($0-50/month), Claude API usage (likely $20-100/month at internal-team volume), OpenAI embeddings (cents), Pinecone (free tier to $50/month).

## Ask before quoting
- Which systems do you run today (TMS, WMS, ERP, email, chat tool), and do they have APIs?
- How many people are on the ops, dispatch and customer service side?
- Where do SOPs and procedures live, and in which language?
- What eats the most time today: status questions, customer updates, documents, quoting, invoicing?
- Discovery only for now, or is there a budget and timeline for the first implementation?

## Flags
- New account, no hires, no reviews, posted today: first AI hire, payment method unverified from the metadata.
- Hourly $20-30 against an expert-level ask.
- Client in Poland: timezone overlap with Texas is mornings only.
- None of these are reasons to skip.

## Pricing path (Lorenzo only, never in the proposal or chats)
- Value (assumption, the post gives no numbers): 5 ops and customer service staff each save 30 minutes a day on status and procedure questions = 2.5 hours/day x 250 working days = 625 hours/year. At an assumed $20/hour loaded cost that is about $12,500/year. One more automation from discovery (customer updates, document handling) could double it.
- Price range: 10-20% of about $12,500 = $1,250-2,500 for the first agent; discovery on top or folded in.
- Land offer (milestone 1): the discovery itself, a process map and ranked automation list with a recommended stack.
- Upsell path: build the top item (likely this ops agent), then the second process, then a monthly retainer for new tools and SOP upkeep.
- Milestones:
  1. 20% - paid once the process map, ranked automation list and tool recommendation are delivered and you've signed off.
  2. 30% - paid once the SOP knowledge base (RAG) is loaded and answering test questions with sources is delivered and you've signed off.
  3. 30% - paid once the shipment system integration (lookup, customer update drafts, ops tasks) is delivered and you've signed off.
  4. 20% - paid once the agent is live for your team with a handover session and runbook delivered and you've signed off.
