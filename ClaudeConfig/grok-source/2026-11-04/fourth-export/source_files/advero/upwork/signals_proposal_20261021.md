# Proposal: two LOGGED candidate signals (draft, 2026-10-21)

**Status: draft only. Nothing here is in the rank score.** Both signals are logged in `batch_log.csv` (weight 0) from 2026-10-21 11:25 CT. `weights.json` stays v1. Nothing changes until a 30-day proposal is approved by Lorenzo via COO. Hard exclusions, no cutoff and no auto-pick are not affected.

## Why
Lorenzo's first batch (relayed by COO at 11:21 CT, outcomes 11:15 CT): 9 picked, 6 shown but not picked. COO's read: 5 of 6 skips were non-US (CA x2, PL, AU, CN) and 6 of 9 picks were US. The skips were ongoing or mentorship roles and the picks were defined builds. Neither pattern is in the current weights (tools 30, category 20, feedback 15, spend 15, age 10, interviews 10).

## (a) client_country
- **Source:** `runs/client_cache.json` `client_country`, from the one `find_jobs get` per job (`clientCompanyPublic.country.name`). `cache_client.py` now maps it, plus `client_state` and `client_timezone`. There is no city field. Existing entries were backfilled from the raw get files on disk with no new calls: **78 of 90 cached jobs have a country**. The other 12 come back from Upwork with no country (timezone only). Vollna RSS has no country at all. The Vollna dashboard shows it (COO's 11:08 sweep), but that isn't a sanctioned feed.
- **Buckets:** `US` / `other_english` (Canada, United Kingdom, Australia, Ireland, New Zealand) / `other` / `unknown` (no cache entry, an error entry, or no country). 'United States Minor Outlying Islands' goes to other. Timezone is **not** used to guess the country (e.g. a US client showed America/Sao_Paulo).
- **Code:** `signals.country_bucket()`. Logged as `client_country` and `country_bucket` in `batch_log.csv`.

## (b) engagement_type
Labels: `build_project` (a defined deliverable) / `ongoing_role` (management, mentorship, staff-style, monthly retainer, ongoing, long-term, hours per week, or hourly with no defined deliverable) / `unclear`.
The classifier is `signals.engagement_type(title, description, btype)`, using only what Vollna gives (title, description, Hourly/Fixed tag). Each rule adds points to a side. A hit in the title counts double, a hit in the description counts once.

| Side | Rule (regex idea) | Points |
|---|---|---|
| ongoing | mentor / mentorship / coach / tutor(ing) | 3 |
| ongoing | monthly pay: `$X/month`, `$X per mo`, pay/salary/budget/rate ... per month, monthly retainer/fee/minimum, retainer | 3 |
| ongoing | hours per week (`10-20 hours a week`), manage/run/work on ... every week, on a weekly basis | 3 |
| ongoing | role titles: outreach/account/campaign/marketing/community/social media/project manager, delivery lead, team lead, head of | 3 |
| ongoing | staff-style: paid trial, part-time, full-time, temps partiel, join our team, in-house | 3 |
| ongoing | ongoing, long-term | 1 |
| ongoing | responsibilities, you will own/manage/run, own (technical) delivery, day-to-day | 1 |
| build | deliverable(s), milestone(s), one-time, fixed-price, proof of concept, MVP | 3 |
| build | "the system/workflow/automation/bot/agent should/must/will", set up the system, end-to-end | 3 |
| build | initial project/focus/bots/setup/build, starting with, what you will build, bots I want built | 3 |
| build | build, set up, implement, integrate, configure, migrate, fix, automate | 1 |
| budget | Fixed price: +2 build. Hourly with no strong (3-point) build rule anywhere: +2 ongoing | 2 |

Decision: build minus ongoing >= 3 gives build_project, <= -3 gives ongoing_role, otherwise unclear. On the first test I fixed three false positives ("tutorial" matching tutor, "1 SMS per month" nurture cadence, installers updating availability "every week"). These were real rule bugs, not tuning to fit the outcomes.

### Labels on today's 15 (text from the raw get files on disk)
| Outcome | Job id | Title | Fixed/Hourly | Country (cache) | Bucket | Label | Evidence (points) |
|---|---|---|---|---|---|---|---|
| PICK | ~022112932304859291673 | HubSpot Developer – Agentic AI & AI Automation | hourly | India | other | unclear | build 1 vs ongoing 3: -responsibilities(1), +build verbs(1), -hourly, no defined deliverable(2) |
| PICK | ~022112900978688649314 | Fixed-Price: Build & Verify 150 Executive Contacts + Cold Em | fixed | United States | US | build_project | build 14 vs ongoing 0: +deliverables/fixed scope(9), +build verbs(3), +fixed(2) |
| PICK | ~022112918438611511394 | GoHighLevel Expert / Marketing Automation & Business Systems | hourly | unknown | unknown | build_project | build 7 vs ongoing 1: -ongoing/long-term(1), +deliverables/fixed scope(3), +defined first build(3), +build verbs(1) |
| PICK | ~022112895866829374925 | End-to-End Recruitment & Onboarding Automation : n8n, Micros | fixed | unknown | unknown | build_project | build 12 vs ongoing 0: +defined system(9), +build verbs(1), +fixed(2) |
| PICK | ~022112748953415130313 | Grok AI Bot Specialist Needed — Build Automations & Train Me | hourly | United States | US | build_project | build 6 vs ongoing 1: -ongoing/long-term(1), +defined first build(3), +build verbs(3) |
| PICK | ~022112890219280064537 | AI Agent Developer / Voice AI, RAG, MCP & Workflow Automatio | fixed | United States | US | unclear | build 3 vs ongoing 1: -ongoing/long-term(1), +build verbs(1), +fixed(2) |
| PICK | ~022112931725830057478 | AI and Automation Specialist for CPA Firm | hourly | United States | US | unclear | build 3 vs ongoing 1: -ongoing/long-term(1), +defined first build(3) |
| PICK | ~022112836518916713990 | n8n Automation Expert for RSS Data Collection & Automated Re | fixed | United States | US | build_project | build 6 vs ongoing 1: -responsibilities(1), +defined system(3), +build verbs(1), +fixed(2) |
| PICK | ~022112919924070801433 | Voice AI Engineer: End to End implementation, telephony & CR | fixed | unknown | unknown | build_project | build 14 vs ongoing 2: -ongoing/long-term(1), -responsibilities(1), +defined system(6), +defined first build(3), +build verbs(3), +fixed(2) |
| SKIP | ~022112933077722327138 | GoHighLevel expert needed – Lead automation + self-booking f | fixed | Canada | other_english | build_project | build 9 vs ongoing 1: -ongoing/long-term(1), +deliverables/fixed scope(3), +defined system(3), +build verbs(1), +fixed(2) |
| SKIP | ~022112929621326424162 | Copywriter Campagne Marketing | hourly | United States | US | ongoing_role | build 1 vs ongoing 9: -manager/lead role(3), -staff-style(3), -responsibilities(1), +build verbs(1), -hourly, no defined deliverable(2) |
| SKIP | ~022112915526131969542 | Cold Email Outreach Manager for Two Canadian B2B Brands (Ins | hourly | Canada | other_english | ongoing_role | build 1 vs ongoing 14: -hours/week(3), -manager/lead role(6), -ongoing/long-term(3), +build verbs(1), -hourly, no defined deliverable(2) |
| SKIP | ~022112903215453246262 | AI Voice Agent Builder & Delivery Lead / $7,500/Month Minimu | fixed | Poland | other | ongoing_role | build 3 vs ongoing 16: -monthly pay(9), -manager/lead role(6), -responsibilities(1), +build verbs(1), +fixed(2) |
| SKIP | ~022112888162649235481 | Finish my half-built AI projects: Claude, Copilot, automatio | hourly | Australia | other_english | ongoing_role | build 1 vs ongoing 14: -hours/week(3), -staff-style(9), +build verbs(1), -hourly, no defined deliverable(2) |
| SKIP | ~022112925179706964964 | AI Automation Mentorship for Make/Airtable/Apify | fixed | China | other | ongoing_role | build 6 vs ongoing 16: -mentor/coach(9), -monthly pay(3), -staff-style(3), -ongoing/long-term(1), +deliverables/fixed scope(3), +build verbs(1), +fixed(2) |

Summary: **picks** are build_project 6, unclear 3, ongoing_role 0. **Skips** are ongoing_role 5, build_project 1 (the French-only Quebec GHL build), unclear 0.
Country from the cache: picks are US 5, other 1 (India), unknown 3. COO's sweep has the 3 unknowns as US, FR and IN, which fits COO's 6 of 9 US. Skips are other_english 3 (CA x2, AU), other 2 (PL, CN), US 1.
**Confound:** the non-US skips were also the ongoing roles (Canada cold-email manager, Australia paid trial, Poland delivery lead, China mentorship). With 15 jobs the two effects can't be separated. Logging both for 30 days is what separates them, using the 2x2 of bucket by label.

Also seen, not used: the get's `contractTerms.hourlyContractTerms.engagementType` (FULL_TIME / PART_TIME) appears on hourly jobs only after enrichment. It's FULL_TIME on two picks (HubSpot, Grok AI Bot), so it's a weak signal on its own. It could be logged later.

## Logging (done now, logging only)
- `batch_log.csv` header migrated at 11:25 CT (backup `batch_log.csv.bak-20261021d`). Three columns were added at the end: `client_country, country_bucket, engagement_type`. The 95 existing rows were filled from the cache and labels, and nothing else in them changed.
- `run_selection.py` labels engagement when a job is fetched (stored in `runs/jobs_state.json` as `engagement`) and writes the 3 columns on every batch. Jobs with no description on hand (54 today: older backfilled jobs and feed jobs from before this change) are `unknown` until their next fetch.
- `rank_score`, `weights.json`, `propose_weights.py` and the hard exclusions are unchanged.

## How propose_weights.py would weigh them (after about 30 days, not built yet)
Categorical signals need **per-bucket lift**, not the current linear mean difference. A mean of "US = 1, other = 0" assumes an order the buckets don't have, and unknown is not "half a US".
1. **Trigger:** at least 30 days of logged batches **and** at least 30 selected outcomes since the version (the current rule), or `--force` for a dry run. Proposal only. `--apply` still needs COO/Lorenzo approval.
2. **Per bucket b:** decided jobs n_b (selected + skipped, one row per job as now), selection rate p_b = sel_b / n_b, overall rate p. Lift_b = p_b / p. Shrink toward 1 with few jobs: lift'_b = 1 + (lift_b - 1) x n_b / (n_b + 10).
3. **Minimum sample:** 10 decided jobs and 3 selected in a bucket, or the bucket stays neutral. The signal is only eligible if at least 2 buckets pass. `unknown` always scores neutral (0.5), so missing data never penalizes a thin client.
4. **Sub-score:** sub_b = clamp(0.5 + 0.5 x (lift'_b - 1), 0, 1). The bucket-to-sub-score table is versioned in `weights.json` (`bucket_scores`) next to the weight, so batches can be re-normalized later.
5. **Weight:** new signals start at **0** (the 5-point floor doesn't apply until a signal is approved in). Each cycle moves them by at most **+/-3** points, the same cap as now, up to **X = 10** each, with country and engagement together at most 15. The step size follows the lift spread, max(lift') - min(lift'), times 10, capped at +/-3. The other weights renormalize to keep the total at 100 under their own +/-3 cap and 5-40 bounds.
6. **Evidence in the proposal:** a per-bucket table (n, selected, rate, lift, shrunk lift, proposed sub-score) and the country-by-engagement 2x2, so a country effect that's really an engagement effect (or the reverse) shows up before anything is applied.

## Not doing
No change to weights, rank score, exclusions or schedule. No connector calls were made for this (the country backfill read files already on disk). No Upwork actions.
