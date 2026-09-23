# Private assessment - n8n AI news pipeline, 6 sources, 2 styles

## Time
6 to 10 hours of real work, spread over 3 to 5 days. Roughly: 1h on the six sources
(finding real feed urls, testing which ones actually have RSS), 2 to 3h if any of the
six need HTML scraping instead of RSS, 1h on the dedupe and relevance gates, 2h on the
two style prompts and getting the voices genuinely distinct, 1h on the sheet schema and
the 20 topic articles, 1 to 2h testing across several mornings because feed problems only
show up on live runs.

## Rate vs market
The post pays $20 fixed. That is not a price, it is a door opener. At market this is a
$400 to $900 build (6 to 10 hours at $60 to $90). The client's history says the $20 is
literal, not an opening number: 293 contracts, $34k spent, that is about $115 per contract
and their graphic design work runs $0.50 per design. They are not going to be talked into
$600 on this post.

The reason to bid anyway is the relationship. 122 active contracts, 4.89 over 101 reviews,
and an already open contract titled "N8n expert - Claude automation" started 2026-08-31.
This is a client who hires constantly and keeps people around. Take the $20 as a paid
audition, deliver a build that is obviously above the price, and the play is the next ten
tasks and the standing n8n retainer, not this fee. If they come back with more scope on
the same $20, that is the moment to quote properly.

## Likelihood
Good. The post asks for exactly what Lorenzo does daily: n8n, AI nodes, Google Sheets.
0 hires and 0 invites on a fresh post, and a Loom with a working canvas beats a text bid
by a mile here. Bids are 10 to 100 but almost all of them at $20 will be one-paragraph
copy-paste. The application asks for 1 to 2 n8n workflows already built plus a time
estimate; the video covers both in one artifact.

What actually breaks after the handoff:
- Scraper rot. If any of the six sources have no RSS, they need HTML parsing, and those
  break the first time the site changes its markup. The "Feed Reachable?" gate and the
  dead source log are in the build for exactly this, so five sources keep running when
  one dies.
- LLM spend. Nobody has priced this. 6 sources x N stories x 2 styles, every day, plus
  20 original articles. At 20 stories a day that is 40 generations daily plus the topic
  batch. On GPT-4o that is real money and it is the client's key, not Lorenzo's.
- Rate limiting and Google Sheets row growth. A sheet used as the dedupe lookup gets slow
  once it is thousands of rows deep; it needs a lookup on a url column, not a full read.
- "Topic relevant" is undefined in the post. If it means a keyword list, this is a filter
  node. If it means an editorial judgement call, it is another LLM call per story and the
  cost roughly doubles.

## Standard pricing
Build: $400 to $900 one time. With HTML scraping on more than two of the six sources,
$900 to $1,400. Ongoing: $100 to $250 a month to keep scrapers alive and prompts tuned.
Client-side software: OpenAI API usage (call it $30 to $150 a month at this volume,
depending on story count and model), n8n self hosted free or n8n cloud starter, Google
Sheets free.

## Ask before quoting
1. Which six urls, and do they publish RSS or does the site need HTML scraping?
2. How many stories a day do you expect to come through, after the topic filter?
3. What does "topic relevant" mean - a keyword list you give me, or a judgement call?
4. Which model, and whose OpenAI key pays for it?
5. Is the sheet already built? What columns do the editors want to see?
6. The 20 topics - one time batch, or a recurring list that refills?
7. Do you want the two styles editable by your editors (a prompt tab in the sheet) or
   locked in the workflow?
8. Where should the failure alert land - Telegram, Slack, email?

## Flags
None blocking. Client is in Moldova, timezone Asia/Jerusalem, so the 6am schedule needs
its timezone confirmed. No location requirement in the post. The post does ask to share
1 to 2 workflows already built, which the Loom satisfies directly.
