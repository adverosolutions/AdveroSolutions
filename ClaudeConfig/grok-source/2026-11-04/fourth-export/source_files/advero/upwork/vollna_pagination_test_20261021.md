# Vollna RSS pagination test, Wed 2026-10-21 (10:50–10:57 AM CT)

Read-only. Used only the 3 feed URLs in `/workspace/vollna_rss.txt`, with plain curl GETs. No login, no browser, no Vollna settings touched, no Upwork MCP calls. I made 34 requests in total, spaced about 2s apart, and got no 429s or blocks. Raw responses are in `/workspace/vollna_pg/`.

## Result: there is no page 2

Each feed returns at most 30 items. Nothing I tried reached older jobs.

### Base fetch (10:50 AM CT)
| Feed | Items | Oldest → newest posted (CT) | Hours covered |
|---|---|---|---|
| AI & Automation Systems | 30 | 09:42 → 10:42 | ~1.0 h (09:56 → 10:49 on a 10:56 rebuild, ~0.9 h) |
| Outbound & Lead Gen Systems | 30 | 03:01 → 10:37 | ~7.6 h |
| Sales / Marketing / Leads | 30 | 08:53 → 10:41 | ~1.8 h |

Headers: Cloudflare only (`cache-control: max-age=0, private`, `cf-cache-status: BYPASS`). There are no rate-limit headers, no `Link`/next header, no `atom:link rel=next` and no opensearch elements. Every "next" or "page" string in the XML is inside job descriptions. The channel has `lastBuildDate` and `expireDate`, 10 minutes apart, so the feed is a cached snapshot that Vollna rebuilds every 10 minutes.

### Params tried
- On the AI feed, all 13 of these returned a byte-identical item set (same 30 ids, same lastBuildDate): `page=2, p=2, offset=30, start=30, skip=30, limit=100, count=100, per_page=100, size=100, max=100, items=100, before=<oldest epoch>, until=<oldest epoch>`.
- On Outbound and Sales, `page=2, offset=30, limit=100, before=<oldest epoch>` were also identical to the base.
- **Vollna docs** (https://www.vollna.com/docs/filters/rss) list only 2 RSS params: `limit` (default 30, min 10, max 200) and `frequency` (cache seconds, 180–3600). There's no pagination param.
- `limit` testing:
  - `limit=200` on a fresh rebuild of the AI feed's base cache (10:56 CT): **30 items** (09:56 → 10:49). Values above 30 are capped at 30 on this account, probably a plan cap.
  - `limit=10&frequency=186`: 10 items. So limit is honored downward only.
  - `limit=60/100/200` with `frequency=181/183/184`: 15 items each (10:27 → 10:49). Outbound `limit=100&frequency=185`: 15 items (08:32 → 10:46). A `frequency` value creates a separate cache that holds *fewer* items.
  - Any `limit` without a new `frequency` just gets the existing 10-minute cache. The cache key ignores `limit`.

### Answers to the requested breakdown
- Max pages reachable per feed: **1** (AI & Automation, Outbound, Sales/Marketing).
- Page 2+ age range, 63+ scores vs stale, extra unique jobs per run: **none**. No page 2+ exists, so there was nothing to score and extra pages add 0 jobs. I didn't run score_vollna.py.
- Coverage per run is unchanged: AI & Automation ~1 h, Sales/Marketing ~1.8 h, Outbound ~7.5 h (weekday daytime volume). At night, with fewer posts, the same 30 items cover more hours.

## Recommendation

1. **Don't build multi-page pulls.** They aren't possible, so pulling 2–3 pages on off-peak hourly runs doesn't apply. Keep one GET per feed per run.
2. **`--hours 2` stays.** The binding limit is 30 items per feed, not the look-back. Two hours covers the 60-minute gap with overlap, and job_id dedupe handles repeats.
3. **Recommended schedule.** Keep what Lorenzo set: :00 hourly 24/7, plus :30 from 8:30 AM to 4:30 PM CT (every 30 min, 8 AM–5 PM), ±5 min. At peak, the AI feed holds about 60 minutes of jobs, so hourly-only daytime runs would sit right at the edge, and the :30 runs are what keep 8–5 covered. Optional, Lorenzo's call: add :30 runs from 5:30 to 9:30 PM CT, because US West Coast clients keep posting into the evening. Anything faster than every 10 minutes gains nothing because of the 10-minute cache.
4. **Optional script change, not made:** log a gap warning when a feed's oldest item is newer than the previous run time. That would show whether any jobs fell between runs.

## Options to cover more than 30 items (each needs Lorenzo; nothing changed)
- **Split the AI & Automation filter** into 2 narrower Vollna filters, for example AI agents/LLM and n8n/Make/Zapier/GHL. Each gets its own 30-item feed. The account uses 3 of 5 filters. Needs: Lorenzo creates the filters in the Vollna dashboard and shares the new RSS URLs. Cost: none.
- **Vollna API** (`GET /filters/{id}/projects`, paged, up to 100 per page, 30 requests/min). Needs: the Agency plan or a $10/month API add-on on his current plan, plus an API token that Lorenzo generates. It uses 1 project credit per new job, with 10,000 credits a month. This is a billing change, so it's his decision.
- **Vollna notification integrations** (Slack, email, Telegram, webhook-style): these push every matching job as it posts, with no feed window. The account has no integrations set up today. Needs: Lorenzo enables one in the dashboard and chooses where it delivers.
- Ask Vollna support why `limit` is capped at 30 when the docs say up to 200. It may be a plan limit.

## Side effects / notes
- My `frequency` test URLs created separate short-lived caches (3 min). My `limit=200` request rebuilt the AI feed's normal cache at 10:56 CT (normal 30 items, expires 11:06 CT). This has no effect on the scheduled runs.
- I didn't edit `score_vollna.py` or `run_selection.py`, and I didn't run `run_selection.py`. Checksums:
  - At my start, `score_vollna.py` was `50a6e619…`, the same as `score_vollna.py.bak-20261021c`.
  - At 10:56:47 CT, **another agent edited `score_vollna.py`**. It's now `3b4326a7…`, and the change turns rubric exclusions into a flag instead of a drop, citing "Lorenzo 2026-10-21 10:52 CT". I left it in place.
  - `run_selection.py` is unchanged (`35f05202…`, the same as `.bak-20261021c`).

## Correction (2026-10-21 11:04 AM CT, from COO)
Only the RSS feeds are capped at 30. The Vollna web dashboard (www.vollna.com/dashboard/filter/<id>, filters 45023 / 45024 / 45365) has a "Load more" button that loads 30 jobs per click. 5 clicks reached 150 jobs, about 6h back, on AI & Automation (header showed 13,080 projects). The RSS conclusion above (no RSS pagination) still holds, but "can't see more than 30" was wrong for Vollna overall. A proposal for reading the dashboard in scheduled selection runs is pending a read-only check of whether the Upwork Coordinator desktop browser is signed in to Vollna.

## Dashboard check (2026-10-21 11:05 AM CT, read-only, Upwork Coordinator browser)
- The Upwork Coordinator box browser is already signed in to Vollna ([EMAIL]). No sign-in was needed.
- Filter 45023 (AI & Automation, primary): the header showed 13,081 projects. 30 rows were visible at first, and one "Load more" gave 60, with the oldest posted about 2h ago. The button was still there.
- Each row has an "Open on Upwork" link, a Vollna redirect `/go?...&url=https://www.upwork.com/jobs/~022...`, so the Upwork job id can be parsed from the link.
- Collapsed row columns: Job Title, Budget, Published, Client Rank (a 1-5 badge). Spend, rating, hire rate and proposals aren't shown collapsed. They may be in expanded rows, which weren't checked. Enrichment option (b) covers them anyway.

## Proposal (needs Lorenzo's approval; nothing changed)
1. Keep RSS as the fast source on every scheduled run.
2. Add a read-only dashboard sweep, done by the Upwork Coordinator browser, of filters 45023 / 45024 / 45365. Click "Load more" until the oldest visible job is older than the last sweep's newest job, capped at 8 clicks per filter. Parse the Upwork job id, title, budget, published time and client rank. Write runs/vollna_dashboard_<ts>.csv, which run_selection.py merges and dedupes by job id with the RSS items. It stays Vollna-only, and the Upwork connector is only used for the one-per-new-job enrichment.
3. Cadence: the first run of the day (about 8:00 AM CT, catching all overnight posts) plus at 12:00, 4:00 and 8:00 PM CT. These are the gaps where the RSS AI feed (about 1h deep at peak) and the Sales feed (about 1.8h deep) can overflow between runs. The :30 runs stay RSS-only because browser sweeps are slower and only one browser task runs at a time.
4. Safeguards: no clicks other than Load more and scrolling, never touch settings, filters or billing, never use the AI "Qualify" button. If the browser hits a sign-in page or a Vollna error, stop and tell COO once. The sweep would hand job ids to the existing ranking and enrichment, so nothing else changes.
