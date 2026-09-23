# Private assessment (not for the proposal)

**Time.** The first week is reading someone else's work, not writing code: 4 to 8 hours to
open every workflow, map which one owns Faire, Shopify, Unleashed and Xero, and find where
the third party put the retries and where they did not. After that it settles into a
retainer of 5 to 10 hours a week, mostly small fixes plus the occasional new automation.
The reliability layer on the canvas (dead letter, retry, run log, 7am health check) is
about 6 to 10 hours to wrap around what already exists and is the thing that turns "we
find out days later" into "Slack told us in a minute". Do not promise a rewrite; this is a
maintenance seat with a hardening project bolted on.

**Likelihood.** Good. He builds this exact monitoring pattern in n8n weekly, and the post
is not asking for four-system expertise, it is asking for someone who responds fast and
does not let things sit. The Loom lands because the prop is about their actual failure
mode, not about rebuilding their stack. Honest gap: he has not run Faire, Unleashed or
Xero specifically, so the copy leans on the reliability pattern and the API work, never on
claimed Unleashed experience. Adjacent framing only.

**Standard pricing.** The post is $20 to $40 an hour. Market for someone who owns
reliability across four connected systems is $50 to $85 an hour, and fixed hardening
projects like this go $1.5k to $4k. He can take the posted band to win a long-term seat,
but know the number: the retainer should drift up once the health check is live and the
fix list gets shorter. Client record is thin but clean, one prior contract at $1,000 fixed
with 5 stars, so they pay and they rate. No recurring software to quote, the monitoring
rides on Sheets and Slack.

**Risks that move the estimate.**
- No docs from the previous builder. Undocumented workflows are the single biggest time
  sink and the reason week one is 4 to 8 hours of reading.
- Unleashed API rate limits. Bursty order days will throw 429s; the backoff node exists
  for that reason, but throughput has to be measured before promising anything.
- Xero tokens refresh every 30 minutes. If the third party wired it badly, half the
  "random" failures are just expired tokens.
- Faire API access tier. Faire does not hand out API access freely; if they are on a
  limited tier or the integration is app-based, some of the writeback is constrained.
- Who holds the credentials. If the previous builder still owns them, the first fix is a
  handover, not a workflow.

**Ask before quoting.**
- How many workflows are there, and which of them touch money?
- n8n cloud or self hosted, and which version?
- What breaks most often, and how do you find out today?
- Who owns each API credential, you or the previous builder?
- How many hours a week do you actually expect?
- What are the on-call expectations, and what counts as urgent?

**Flags.** Client timezone Europe/London, country not shown; do not assert a location in
copy. 20 connects, 7 to 93 bids, 1 invite already out, so speed matters. Long-term hourly,
so the proposal should read like a seat being filled, not a project being sold.
