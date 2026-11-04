---
name: upwork
description: The Upwork Coordinator's job-list runbook for Lorenzo. Covers the Vollna-only source rule, the full ranked list (no cutoff, no auto-pick), the rank score and its weights, the hard exclusions, carry-forward, the one-get-per-job client enrichment flow (needs_enrichment.json, cache_client.py, --rerank-only), the schedule, the append-only picks/batch logs, Lorenzo's picks, the compare step, and the learning loop (outcomes, weight proposals). Use for "Upwork jobs", "job list", "what should I apply to", "run selection", "Vollna", "full list", "enrich", "picks log", "compare my picks", "match rate", "weights". Proposal writing is Lorenzo's and is not in this skill.
---

# Upwork job list

The bot pulls together **every** open Upwork job from Lorenzo's Vollna feeds, ranked. Lorenzo applies to 6-12 jobs a day and picks 3-5 per batch himself. The bot never narrows, filters or picks for him (Lorenzo 2026-10-21 10:52 and 10:54 CT).

**Selection only (permanent rule, 2026-10-20).** Output is a ranked list of jobs: title, link, scores, flags. No proposal text of any kind.

## Source rule (standing, Lorenzo 2026-10-21 10:46 AM CT, enrichment updated 10:57 AM CT)

- **Vollna is the primary and only source** for the job list and lead data (the 3 RSS feeds in `/workspace/vollna_rss.txt`).
- The Upwork connector is read-only and is used **only to add client details** to jobs already pulled from Vollna. Since 10:57 AM CT (option b): every NEW job gets exactly **one** read-only `find_jobs get`, cached by job_id in `runs/client_cache.json`. **Never call for a job already in the cache** (ok or error entries are both final). No retries beyond the one attempt.
- Never use the connector to search, list or discover jobs (no `find_jobs` search/list, no saved-jobs reads). No bursts: about 3 seconds between gets. Reason: Lorenzo has seen accounts banned through the Upwork MCP.
- Python scripts (`run_selection.py`, `score_vollna.py`, `cache_client.py`, `record_outcomes.py`, `propose_weights.py`, `compare_picks.py`) make **no** connector calls. Only the routine agent calls the connector, following the enrichment flow below.

## Never

- Draft proposals (no openers, proof points, P.S. lines or scoping questions), in any file or chat message.
- Apply, save, like, flag or message on Upwork. Never call an Upwork write tool.
- Narrow the list: no score cutoff, no auto-selection, no dropping a job for its category or rubric flags.
- Change rank weights outside the learning loop's approved `--apply` step, or edit the rubric in `score_vollna.py` to make lists match.
- Rewrite or delete rows in `picks_log.csv`, `lorenzo_picks.csv`, `outcomes.csv` or past batches in `batch_log.csv`.
- Change Vollna account settings or billing.

Old proposal drafts are archived at `~/advero/upwork/archive/proposal_drafts_20261020.md`. Not output, not a template.

## Hard exclusions (the only jobs left off the list)

1. **Already applied**: job id or title in the applied-history CSV (`/home/box/Downloads/proposals_2026_10_20_20_16_16.csv`). These are not logged either.
2. **Picked**: in `lorenzo_picks.csv` or marked `selected` in `outcomes.csv` (he has it; it leaves the batch view).
3. **Hired or closed**: `has_hire` or `closed` true in `runs/client_cache.json` (known only after enrichment).

Everything else stays on, ranked. Rubric exclusions (off-topic category, ads-only, W2, commission-only, SKIP list, etc.) only **flag** the job (`flag: off-topic <label>`) and cap its category sub-score at 0.15. Jobs 24h+ old age out of the list (not an exclusion; the learning loop records them as skipped).

## Rank score (0-100), weights v1

Weights live in `~/advero/upwork/weights.json` (versioned) and are read by `score_vollna.py` (`load_weights`, `rank_score`). v1 (Lorenzo 10:54 CT):

| Signal | Weight | Sub-score 0..1 |
|---|---|---|
| tools | 30 | scorer tool depth: `min(1, tool_raw / 30)` (tool weights + 4 per tool in the title) |
| category | 20 | `0.5 x lane + 0.5 x keyword fit`; lane = 1.0 core Vollna category (Sales & Marketing, Lead Gen, Digital Marketing, AI & ML, AI Apps & Integration, Scripts & Utilities, Data Mining, Marketing/PR), 0.6 adjacent (dev, data science, IT, consulting...), 0.2 other, 0.5 none; keyword fit = `min(1, kw_raw / 45)`. Rubric-flagged jobs capped at 0.15 |
| feedback | 15 | client rating: `(rating - 3) / 2`, floor 0.2. n/a = 0.5 |
| spend | 15 | `log10(spend + 1) / 5` ($100k = 1), floor 0.3 so thin clients never go to zero. n/a = 0.5 |
| age | 10 | 1.0 under 1h, linear to 0 at 24h. Recomputed every run |
| interviews | 10 | `1 - interviewing / 20` (0 = full, 20+ = 0). n/a = 0.5 |

Points = weight x sub-score. Unknown client signals get neutral half points and show as `n/a`. The old rubric total (`score_vollna.py` scoring, unchanged) is still computed and is what `picks_log.csv` records as `score`.

**What Vollna RSS actually provides** (checked 2026-10-21 on all 90 items): title (with Hourly/Fixed tag), description (with Skills and Categories text), pubDate, link, `<category>` tags. **No** client spend, rating, reviews, hires, proposals or interviewing; the scorer's 'spent' parser finds nothing. All client signals come from the enrichment cache.

## The run

```
python3 ~/advero/upwork/run_selection.py            # normal run (fetch feeds)
python3 ~/advero/upwork/run_selection.py --rerank-only   # after enrichment: no fetch, re-rank with the cache
```

Normal run: fetch the 3 feeds (GET, `--hours 24` = every item they return), dedupe, drop already-applied, score. Append every new job to `picks_log.csv` (dedupe on job_id, append-only, columns `run_time_ct, job_id, url, title, posted_time, score, reason`; flags go in reason). Update `runs/jobs_state.json` (static signals per job). Build the **carry-forward** set: all of today's (CT) jobs still open, new plus earlier, re-ranked together with fresh age points, plus yesterday's jobs with rank >= 60 that are under 24h old. Jobs logged before 10:55 AM CT Oct 21 that are no longer in the feeds are backfilled from `picks_log.csv` with an approximate category (flagged `backfilled`). Then write:

- `~/advero/upwork/runs/full_list_today.csv` and `.md`: every job, rank-ordered (rank, score, title, link, posted_time, flags/reason, age, tools, category, client fields, points per signal, rubric score, job_id). This is the batch view Lorenzo reads.
- one batch appended to `~/advero/upwork/batch_log.csv` (see Learning loop).
- `~/advero/upwork/runs/needs_enrichment.json`: open jobs not yet in the cache, newest first.
- `runs/scored_all_latest.csv` (all jobs, for compare lookups), then `record_outcomes` runs.

`--rerank-only` skips the fetch, re-ranks from `jobs_state.json` + cache, rewrites the full list and **replaces only the current (latest, same-day) batch** in `batch_log.csv`; rows of jobs that left the list since (picked, hired) keep their original row. Earlier batches are never touched. Other flags: `--no-cache` (ignore the cache), `--no-outcomes`, `--root DIR` (test copies).

Prints one `OK ...` line with feed items, unique jobs, applied dropped, kept/flagged, new to log, full-list size, drops, batch id, needs-enrichment count and outcomes. Exit 0 ok, 2 real failure (feeds missing/all empty, scorer crash, log header changed), 3 another run in progress.

## Enrichment flow (routine agent, every run)

1. Run `run_selection.py`.
2. Read `runs/needs_enrichment.json` (jobs not in `client_cache.json`, newest first).
3. For each job, **one** read-only Upwork `find_jobs get` by job id/url, about 3 seconds apart, no bursts. Never for a job already in the cache. No search/list calls.
4. Save each result right away: `python3 ~/advero/upwork/cache_client.py --from-get <saved output file>` (or `--json '{...}'` / stdin / field flags). On a failed call write `--job-id <id> --status error --error "<what>"`: the error entry is final, no retry.
5. `python3 ~/advero/upwork/run_selection.py --rerank-only`.
6. **Stop and report to Lorenzo/COO on any rate-limit, warning, or auth/login prompt.** Don't continue the queue.

`cache_client.py` maps `find_jobs get` like `runs/enrich_build_20261021.py`: feedback = `client_record.feedback_score` (only if feedback_count > 0 and score > 0; 0 = unrated = n/a), spend = `spend_total`, hire_rate = `hire_rate_percent`, total_hires = `contracts_total`, interviewing = `activityStat.jobActivity.totalInvitedToInterview`, invites = `invitesSent`, proposals = n/a (`proposals_tier_unavailable`), has_hire = `totalHired > 0`, closed = `workFlowState.status != ACTIVE`. Location: client_country = `clientCompanyPublic.country.name` (often absent), client_state, client_timezone (no city in the get). `cache_client.py --backfill-location DIR ...` refills only those 3 fields from raw get files on disk (no calls). Writes are locked and atomic. Existing entries are kept unless `--overwrite` (only on Lorenzo/COO request). The cache was seeded on 2026-10-21 from the 20 gets made at ~10:20 AM CT (`/workspace/enrich_20261021/*.txt`), so those are never re-fetched.

## Schedule

Per Lorenzo 2026-10-21 10:54 AM CT: hourly at :00 around the clock, every day (so 12:00 AM and 2:00 AM CT are included), plus :30 from 8:30 AM to 4:30 PM CT, i.e. every 30 minutes 8:00 AM-5:00 PM CT. Normal flexible timing. Runs are **not** locked to Lorenzo's Loom slots (10 AM, 12 PM, 2 PM, 4 PM CT); the list is always current and he reads it before each slot. Cron form: `CRON_TZ=America/Chicago 0 * * * *` plus `CRON_TZ=America/Chicago 30 8-16 * * *`.

Feed limit (tested 2026-10-21, full report `~/advero/upwork/vollna_pagination_test_20261021.md`): the Vollna RSS feeds have **no pagination**. `page`, `p`, `offset`, `start`, `skip`, `per_page`, `size`, `max`, `items`, `count`, `before` and `until` are ignored, and there's no next link in the XML or headers. The documented `limit` param (docs say up to 200) never returned more than 30 items on this account; it only lowers the count. Adding `frequency` (cache seconds) makes a separate, smaller cache (10–15 items). So one GET per feed per run is all there is, and the feed size limits coverage, not `--hours`:
- AI & Automation: about 1 hour of jobs per run at weekday daytime volume (30 items, 09:42–10:42 and 09:56–10:49 CT on Oct 21). At peak, hourly runs have almost no overlap, which is why 8 AM–5 PM runs every 30 minutes.
- Sales / Marketing / Leads: about 1.8 hours per run.
- Outbound & Lead Gen: about 7.5 hours per run.
Feeds are cached server-side for 10 minutes (`expireDate` in the XML), so polling faster than every 10 minutes gains nothing.
Ways to get more coverage, none set up (each needs Lorenzo): split AI & Automation into 2 narrower Vollna filters (he has 3 of 5 filters used); the Vollna API (`GET /filters/{id}/projects`, paged, up to 100 per page; needs the Agency plan or a $10/month API add-on and a token he generates); or Vollna's notification integrations, which push each job as it posts.

Report: stay quiet on a normal run. Tell Lorenzo once about a failure (exit 2), not every run, and at once about any connector rate-limit, warning or auth prompt.

## Lorenzo's picks

Lorenzo adds the jobs he picks into `lorenzo_picks.csv` (or tells an agent, who appends the row; a url is enough). Put the CT time he picked it in `run_time_ct` if known. Append only. Approvals relayed by COO can also be recorded with `record_outcomes.py --select`.

## Compare

```
python3 ~/advero/upwork/compare_picks.py [--date 2026-10-21 | --since 2026-10-21] [--top 12] [--min 0] [--out ~/advero/upwork/compare_20261021.md]
```

`picks_log.csv` now holds every job, so the bot's "picks" for comparison are its **top-ranked** jobs: each job's best rank_score in any batch that day (`batch_log.csv`; best-ever because picked jobs leave later batches), falling back to the rubric score for jobs with no batch row, then `--min`, then the top `--top` N per CT date (default 12, 0 = all). Lists shared, bot-only and Lorenzo-only (with their rank and position when they were in the list), and match rate as shared / union and shared / Lorenzo picks.

## Learning loop

Files (all in `~/advero/upwork/`):
- `batch_log.csv`: append-only, one row per job shown per batch (each run's full list). Columns: `date_ct, batch_time_ct, batch_id (bYYYYMMDD-HHMM), job_id, url, title, tools_matched, category, client_feedback, client_spend, hire_rate, job_age_hours_at_batch, interview_count, rank_score, sub_tools, sub_category, sub_feedback, sub_spend, sub_age, sub_interviews (points), rank, weights_version, outcome, outcome_time_ct`. `outcome` is written `pending` and never edited.
- `outcomes.csv`: `job_id, outcome, outcome_time_ct, source`. The **only** place outcomes are written (append-only). Effective outcome: `selected` if any selected row (a late pick beats an earlier skip), else `skipped`, else `pending`. `runs/batch_log_outcomes.csv` is a derived view (batch_log + effective outcome), rebuilt every time.
- Logging-only columns (weight 0, since 2026-10-21 11:25 CT): `client_country, country_bucket` (US / other_english = CA, UK, AU, IE, NZ / other / unknown) and `engagement_type` (build_project / ongoing_role / unclear, from `signals.py` rules on title + description + Hourly/Fixed). They are NOT in the rank score. Draft plan for weighing them (per-bucket lift, start at 0, +/-3 per cycle, max 10): `~/advero/upwork/signals_proposal_20261021.md`. Nothing changes without an approved proposal.
- `weights.json` (`version, effective_ct, weights, note`) and `weights_history.jsonl` (every version, with who approved it).

Outcomes, `python3 record_outcomes.py [--select <job_id|url> ...] [--skip <job_id|url> ...] [--time "YYYY-MM-DD HH:MM"] [--source TEXT]` (`--skip` = COO-relayed "shown but not picked"; ignored for a job already selected) (also runs at the end of every `run_selection.py`): marks **selected** from `lorenzo_picks.csv` rows and from `--select` (COO-relayed approvals); marks **skipped** for jobs shown in a batch, never picked, and no longer open (not in the latest batch, 24h+ old, or hired/closed in the cache). Idempotent: at most one selected and one skipped row per job.

Reweighting, `python3 propose_weights.py [--force]`: runs when there are **30+ selected outcomes since the current version's effective_ct**, or with `--force`. Per signal it compares the mean normalized sub-score of selected vs skipped jobs (each job's batch row nearest before the pick, or its last row; client signals marked n/a are left out), steps the weight by `clamp(20 x diff, +/-3)` points (needs 5+ jobs per group, else 0), keeps every weight in 5-40, and renormalizes to 100 without breaking the cap or bounds. It writes `weights_proposal_<YYYYMMDD>.md` (current vs proposed, evidence, sample sizes, json block) and **does not apply it**. After COO/Lorenzo approve: `python3 propose_weights.py --apply <proposal.md> --approved-by "<who, when CT>"` bumps the version, rewrites `weights.json` and logs to `weights_history.jsonl`; it refuses if weights changed since the proposal. Reweighting never touches hard exclusions and never adds a cutoff or auto-pick.

## Known gaps

- **Static applied-history.** The already-applied exclusion uses the Oct 20 proposals export in `~/Downloads`. Jobs applied to after that aren't excluded unless they are in `lorenzo_picks.csv`/`outcomes.csv`. Refreshing needs a new export from Lorenzo (not a connector pull).
- **No client signals in Vollna RSS.** Client points are neutral (n/a) until a job is enriched.
- **Backfilled jobs** (logged before the 10:55 AM CT Oct 21 change and gone from the feeds) have an approximate category sub-score (from the rubric score); they are flagged `backfilled`.
- The feed window is short: 30 items per feed, no pagination. Jobs posted during a busy hour or while runs are down can be missed.
- Lorenzo's picks may include jobs never in the 3 Vollna feeds. The compare step marks these "not seen".

## Related skills

- `upwork-followups`: proposal-room follow-ups after Lorenzo has applied (ask-first drafts, he sends).
- `claudeisms`: the voice rule for any message to Lorenzo.
- `grok-operator`: how Grok Bot delivers work to Lorenzo.

## Cross-referencing (standing rule, Lorenzo 2026-10-21)
Follow ~/advero/state/clients/README.md for every Upwork client or lead.
- BEFORE drafting a reply or follow-up, or flagging a job's client: grep ~/advero/state/clients/INDEX.csv for the client name, company, domain and email. Read the client file plus any teammate role doc it points to (~/advero/state/org/roles/).
- AFTER acting (a draft handed to Lorenzo, a stage change, a reply received, a hire or loss): append one dated line to the client file's Log, in the form `YYYY-MM-DD HH:MM CT | Upwork Coordinator | Upwork | what happened`. Create or update its INDEX.csv row under `flock ~/advero/state/clients/.lock`. Never edit other bots' lines. Never record billing details, passwords or keys.
- Job-list runs: unpicked Vollna jobs aren't clients yet, so don't create files for them. Create a client file once Lorenzo picks or applies to a job.

## Enrichment pacing (COO 2026-10-21 1:04 PM CT, after one PERMISSION error)
- At least 10s between find_jobs gets, max 15 per run, newest first. Jobs left over wait for later runs.
- One PERMISSION error is probably a private or invite-only post: cache it as an error (never retried) and continue.
- A second PERMISSION error on a different job in the same run, or any rate limit, warning or auth prompt: stop, write runs/enrichment_paused_<YYYYMMDD>.flag, go feed-only for the rest of the day, and tell COO once.
