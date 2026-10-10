---
name: instantly-2026-campaigns
description: Instantly setup for the 2026 three-niche campaigns: working key lives in lead-scrape-2026/.env, SIX campaigns (one body each, leads split round-robin per niche), 25/inbox/day, ids in instantly_campaigns.json
metadata:
  type: project
---

On 2026-09-09 the Instantly key stored in `Agentic Worklfows/.env` failed auth on both
`/api/v2/accounts` (401 Invalid API key) and the legacy v1 endpoint. urllib without a
User-Agent gets a Cloudflare 1010 block first; with a browser UA the real 401 shows.

**Why:** the 2026 three-niche campaign setup (`Coding/lead-scrape-2026/instantly_push.py`,
`--check / --setup / --push / --activate`) and the 1 AM scheduled task both depend on it.

**How to apply:** ask Lorenzo for a new key (Instantly → Settings → Integrations → API
keys), put it in `lead-scrape-2026/.env` as INSTANTLY_API_KEY (that file is read first),
run `--check`, then `--setup`, `--push output/daily/day_<id>.csv`, `--activate`.
Per-inbox cap is 20/day (his requirement), campaigns share all inboxes, 8-17 Chicago Mon-Fri.

**Update 2026-09-09 (later):** Lorenzo supplied a working key (now in `lead-scrape-2026/.env`;
the one in `Agentic Worklfows/.env` is dead). He wants SIX campaigns, one email body each, TWO PER NICHE
(reactivation + outbound): the 'out of left field' email he pasted with recruiting wording
('reqs') was actually meant as CLEANING reactivation (fixed 2026-09-13: 'accounts that
cancelled or stopped renewing their contracts'). A niche's leads are split round-robin across its campaigns. Cap 25/inbox/day
(12 inboxes = 300/day, 50 per campaign), 8-17 America/Chicago Mon-Fri, text only, stop on
reply. Lessons: `POST leads/list` ignores campaign_id (group by each lead's `campaign`
field instead); moving leads needs `POST leads/move` with `ids` + source `campaign` +
`to_campaign_id` (PATCHing `campaign` silently no-ops); DELETE needs a `{}` body; a
rejected tool call can still have partly executed, so audit before re-running.

**2026-09-13:** structure corrected to 2 per niche; 378 leads at 64/64 recruiting, 60/60 cleaning,
65/65 bookkeeping. `leads/move` is an async job: a second move while one runs returns 409, so
wait and retry. Campaigns are single-step (no follow-ups) until Lorenzo writes bumps.

**2026-09-14 lessons:** (1) Lorenzo re-pasted his original emails into the Instantly editor,
which reintroduced `{{personaliztion}}` (won't fill), "outreach outreach", em dashes and the
recruiting "reqs" wording on the cleaning campaign, and added his new guarantee: "or I return
your money / give your money back and throw in a $200 gift card to your favorite steakhouse."
Always re-read live bodies from the API before touching anything; his edits are the source of
truth for copy, mine for mechanics. (2) PATCHing a campaign body as plain text left THREE of six
bodies EMPTY on the server (silently). Always send bodies as `<div>line</div><div><br /></div>`
HTML and read back to verify length > 0 and text match. (3) `campaigns/analytics` returns [] with
no sends; lead `status` 1 = not yet contacted. (4) Campaign status 2 = paused.
