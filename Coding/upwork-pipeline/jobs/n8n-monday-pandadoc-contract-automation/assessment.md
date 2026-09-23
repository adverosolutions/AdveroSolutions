# Private assessment - n8n Automation Developer for Monday.com to PandaDoc

url: https://www.upwork.com/jobs/~022098119207372498065
Hourly $30-60, expert, part-time. Client in Nevada, Chicago timezone. New on Upwork: 1 prior contract (logo design, $45), no reviews, 0 hires, 0 invites, 18 connects to apply, avg bid 35.15.

## Time
Realistic 15 to 30 hours, 2 to 3 calendar weeks part time. Rough split: 3 to 5 hours on the Monday.com GraphQL side (webhook registration and challenge handshake, item plus column_values query, asset public_url download, column updates), 4 to 8 hours on PDF text plus the extraction schema and getting it stable across their real contract layouts, 3 to 5 hours on PandaDoc (template tokens, recipients, async draft polling, send), 4 to 8 hours on validation, retries, error path and testing against their actual documents. If the PDFs are scanned or the layouts vary a lot, the extraction half doubles.

## Likelihood
Squarely a real n8n job, not a toy. Nothing here is exotic for the stack he uses daily, and the client's stated allergy to "AI agents" is an advantage: the build is one extraction call and a lot of plumbing, which is exactly how he framed it.

What actually breaks:
- PandaDoc API access is a paid plan feature (Business or Enterprise tier on current PandaDoc pricing). Verify with the client before promising anything. If they are on a lower tier there is a cost conversation before a line of work happens.
- PandaDoc creates documents asynchronously. The doc is not sendable until it reaches document.draft, so the build must poll, and the poll needs a give-up path or it loops on a stuck document.
- Monday.com file column assets return a time-limited public_url; download has to happen inside the run, not later. Monday API rate limits (complexity budget) bite if they ever backfill in bulk.
- Scanned or image-only PDFs produce zero text. That is the failure mode most likely to embarrass a demo, hence the "Text Found in the PDF?" gate and an OCR fallback.
- Extraction accuracy on money and dates is the real risk. Validation gate before PandaDoc is non-negotiable; a wrong contract value going out for signature is worse than a stalled run.
- New client, no reviews, tiny spend history. Payment method verification and a small first milestone or a capped weekly limit is sensible. Not a reason to skip, just to scope the first block tightly.
- Unverified for Lorenzo: PandaDoc specifically, and Monday.com GraphQL at production depth. Frame honestly as REST/GraphQL work he does constantly, with the video showing the actual logic. No claim of past PandaDoc projects.

## Standard pricing
Market for this scope from a US-facing senior automation engineer: $3,500 to $7,000 fixed, or $55 to $85 per hour. The post's $30-60 band tops out around the bottom of that. Bidding inside their band is fine and deliberate, but the reference number is $45 to $60 per hour for 15 to 30 hours, roughly $1,200 to $1,800 for a tight scope and $2,500 to $4,000 if extraction across messy layouts is included.

Recurring software on their side: n8n (self hosted free, or Cloud from about $24 per month), PandaDoc on a plan with API access, an LLM API for extraction (pennies per contract at typical page counts), OCR only if scanned PDFs are in scope.

## Ask before quoting
1. Which Monday board and which column change should fire the run, and what are the exact status labels?
2. Where do the source PDFs live: a Monday file column, a Drive or Dropbox link column, or email?
3. Are the PDFs digital text or scanned images, and how consistent is the layout? Can they send three real ones?
4. Which PandaDoc template, and what are the exact token names and recipient roles it expects?
5. Is their PandaDoc plan on a tier with API access? (API is a Business/Enterprise feature, needs confirming on their account.)
6. Volume per week now, and expected in six months.
7. Does a human review the extracted fields before the document sends, or does it send automatically once validation passes?
8. Where should failures land: Slack, email, or just the Monday item status?
9. Self hosted n8n or n8n Cloud, and whose account owns the credentials?
10. Is this a one time build or ongoing maintenance and additional boards after?
