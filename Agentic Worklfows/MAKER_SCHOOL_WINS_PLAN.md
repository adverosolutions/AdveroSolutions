# Offer Intel: mining Maker School wins for proven offers (plan, 2026-09-24)

Status (2026-09-24): **phases 1 to 3 built; first real run done 2026-09-23** (90 days of Wins, 257 posts, $2.15 of model calls, delivered to the Google Sheet "Offer Intel: Maker School Wins"). Fixes from that run are in: `collect --via mcp` (the skool-mcp client; Playwright can't run on the Mac), tolerant JSON parsing, one-client price rules and pricing-model definitions in the extract prompt, closed-deal-only price medians, sorted author replies and First Last author names. Runbook: `runbooks/offer_intel.md`. Not built yet: the Sheet push in code (the first Sheet was written by hand), the weekly schedule, the offer card. Decisions for Lorenzo are at the bottom.

## The idea in one paragraph

Maker School members post their wins every day: "signed a $3k/mo dental client off cold email", "first client, $1,500 setup for a roofing reactivation", and so on. Each post is a data point that says *this offer, sold to this industry, through this channel, at this price, worked this month.* We collect every win post, pull the offer, industry, price, channel and cold email numbers out of each one, and roll them up. The result is a live, ranked list of offers that are closing right now, with the posts behind each one as evidence. That list feeds new campaigns: pick a pattern, write the offer, build the ICP, point the list factory at it.

## Per person or all wins? Both, but the unit is the win

**Collect every win post** (one row per win) and store the author's Skool user id on each row. The per-person view then comes for free by grouping on that id.

- **Why not per person as the main view:** you would have to know who to follow in advance, and you would miss the new member who just closed a dentist deal with an offer nobody else runs.
- **Why the person still matters:**
  1. Rank by **distinct winners**, not post count. One member posting 12 wins about the same niche should not make that niche look 12 times more validated.
  2. Repeat winners are the best source of detail. Phase 5 adds a small watchlist of the top repeat winners and pulls their full post and comment history with the scraper's existing `--member` mode.

## What already exists (reuse, don't rebuild)

| Piece | Where | What we reuse |
|---|---|---|
| Skool scraper, logged in to Maker School | `execution/skool_scraper.py` | Persistent Chrome profile (you logged in once, it survives), reading posts from the page's `__NEXT_DATA__` payload instead of the page layout, `walk_tree` for post + reply trees, human-paced page timing, feed paging |
| Model policy, cost ledger, spend ceiling | `shared/llm.py`, `config/llm_budget.json` | Roles `classify` (Haiku) and `research` (Sonnet 5), so `MODEL_POLICY` needs no change |
| Job conventions | `jobs/`, `shared/job_log.py`, `shared/notify.py` | `--dry-run`, Job_Log row per run, ntfy on failure |
| Offer sheet format | `config/offers.md` | Candidate offers get drafted in the same shape: mechanism, guarantee/pricing, minimum to start |
| ICP rubrics + list factory | `config/icp/*.json`, `config/list_factory_targets.json` | A chosen pattern becomes a new ICP rubric and list factory target (with Lorenzo's OK) |

One catch: `execution/skool_scraper.py` calls `sys.exit(1)` at import time when Playwright is missing, so importing it from a tested module would kill pytest. The new code copies its three small pure helpers (`_next_data`, `_page_props`, `walk_tree`) and imports Playwright only inside the function that opens the browser. It reuses the same Chrome profile folder (`execution/.sessions/skool_profile`), so there is no second login. The old script is not edited.

## How it works

```
Skool Wins category  ->  collect (read-only, human pace)  ->  .tmp/offer_intel/raw/<post_id>.json
   -> gate (Haiku: is this a real business win? which channel?)
   -> extract (Sonnet: structured fields, each with the sentence it came from)
   -> normalize (fixed industry + mechanism lists)
   -> roll up (patterns ranked by distinct winners, recency, deal size)
   -> Google Sheet "Offer Intel" + weekly digest to Lorenzo
```

### 1. Collect (read-only)

- Walk the **Wins category** of the Maker School feed, newest first. Skool filters the feed by category through a URL parameter; Phase 0 reads the category list and confirms the Wins category id.
- For each win post, open the post page and keep the root post **plus the author's own replies in the thread**. Wins posts get "what niche?", "what's your offer?", "how many emails?" questions in the comments, and the author's answers usually hold the details the post leaves out. Other people's comments are dropped.
- **Backfill once**, then run **weekly for new posts**. Posts younger than 14 days get their comments re-read on each run, because the author keeps answering questions for a few days.
- Same pacing as the existing scraper (2.5 to 4.5 s between pages). Stops on a login wall instead of retrying.
- Keyed by Skool post id, so re-runs never duplicate. Raw JSON lives in `.tmp/` only.

### 2. Gate (Haiku, cheap)

One call per post. It answers: is this a business win (a signed client, revenue, booked calls, a reply-rate result) or something else (a course milestone, a question, motivation)? Which channel produced it (cold email, Upwork, LinkedIn, referral, cold calling, ads, other)? Only real wins go on to extraction. Everything is kept and tagged, so the cold email view is a filter, not a data loss.

### 3. Extract (Sonnet 5)

One call per real win, JSON out. **Every field is either quoted from the post or `null`. Nothing inferred.** Each filled field carries the sentence it came from, so any row can be checked in a few seconds.

| Field | Example |
|---|---|
| `win_type` | first_client, new_client, revenue_milestone, booked_calls, reply_rate |
| `channel` | cold_email |
| `offer_one_line` | "AI receptionist that books missed calls" |
| `mechanism` | what they build or run (normalized in step 4) |
| `industry` / `niche` | the buyer's industry (normalized in step 4) |
| `buyer_role` | owner, office manager, marketing director |
| `geo` | US, UK, "Texas" |
| `pricing_model` | setup + retainer, retainer, rev share, pay per meeting, performance, one-off build |
| `setup_usd`, `monthly_usd`, `deal_usd` | numbers as stated |
| `guarantee` | as stated |
| `cold_email_stats` | sends, reply rate, positive replies, calls booked, list size, inbox count |
| `list_source` | Apollo, Google Maps, LinkedIn, job boards, Clay |
| `tools` | Instantly, Smartlead, n8n, Make, GHL |
| `copy_angle` | the hook or first line, if shared |
| `time_to_result` | "3 weeks after launch" |
| `experience` | first client, months in the program |
| `evidence_strength` | numbers stated / vague / screenshot only |
| `post_url`, `author_id`, `posted_at` | provenance |

Before the full run, extract **30 posts and check them by hand** against the source. The full run happens only when the check comes back clean (target: no invented facts, 90%+ of fields right).

Screenshots (Stripe, Instantly dashboards) are skipped in v1 and flagged `evidence_strength: screenshot_only`. Reading images is Phase 5 and costs more.

### 4. Normalize

Free text does not count well ("dentists", "dental practices" and "orthodontists" are one market). Two fixed lists in `config/offer_intel/taxonomy.json`:

- **Industries** (about 40): dental, med spa, HVAC, roofing, plumbing, law, real estate, recruiting, commercial cleaning, bookkeeping, SaaS, agencies, and so on.
- **Mechanisms** (about 15): lead reactivation, outbound appointment setting, AI voice / receptionist, speed to lead, review generation, content / ghostwriting, pay-per-lead, custom automation build, CRM setup, recruiting outreach, SEO, and so on.

Anything that does not fit goes to `other` with its free text. The weekly digest lists the new `other` values so the lists can grow.

### 5. Roll up and rank

A **pattern** is one industry x mechanism pair (for example "dental x AI receptionist"). Per pattern:

- **distinct winners** (the main rank), all time and last 90 days
- wins in the last 30 days vs the 30 before (rising or fading)
- median setup, monthly and deal size, from new_client and first_client wins only
- cold email share, and the cold email numbers people reported
- evidence strength mix
- **crowding flag:** a pattern everyone is piling into right now also means those owners' inboxes are full of the same pitch. The adjacent industries with the same mechanism are often the better test.
- **fit with us:** does it match a mechanism we already have proof for in `config/offers.md` (reactivation, trigger outbound)? Proof we can use shortens the path to a campaign.

### 6. Outputs

1. **Google Sheet "Offer Intel"**, its own spreadsheet (not the CRM). Tabs: `Wins` (one row per win), `Patterns` (the ranked list), `Winners` (per-person rollup), `Runs` (one row per run).
2. **Weekly digest** (Sunday, before the list factory runs): new wins this week, the top 10 patterns, the risers, and **3 test candidates**, each with its evidence posts. Delivered as a push plus a markdown file, and added as a section of the Friday retro packet if Lorenzo wants.
3. **Offer card** on request: for a pattern Lorenzo picks, a draft in the `offers.md` shape (mechanism, guarantee/pricing, minimum to start), the ICP rubric draft, and the evidence posts. It is a draft for Lorenzo to edit, never written into `offers.md` or `config/icp/` automatically.

## Guardrails

- **Read-only on Skool.** The job never posts, comments, reacts or messages. One run a week at human pace.
- **Their proof is not our proof.** Numbers from other members' wins are market research. They never appear in an email, a reply-engine draft or a proof line. `config/offers.md` stays the only proof source.
- **Facts only.** Every extracted field quotes its source sentence or stays empty.
- **Member data stays private.** Raw posts and names live in `.tmp/` and Lorenzo's Sheet, never in git. Test fixtures use made-up names and text.
- **Paid model calls only with Lorenzo's OK**, behind `--preflight` (prints the estimated cost and exits) and the existing spend ceiling.
- **Skool's terms.** Automated reading of a private community may go against Skool's terms of service. The existing scraper already does this at a low, human pace; this plan keeps it to one careful run a week and personal use only. Lorenzo's call whether that risk is acceptable (see decision 5).

## Cost (from `shared/llm.py` prices: Haiku $1/$5, Sonnet 5 $2/$10 per million tokens in/out)

| Step | Per post | Per 1,000 posts |
|---|---|---|
| Gate (Haiku, ~600 in / 50 out) | ~$0.001 | ~$1 |
| Extract (Sonnet, ~1,500 in / 500 out), on the ~60% that are real wins | ~$0.008 | ~$5 |
| **Total** | | **~$6 per 1,000 posts** |

The backfill size depends on how many win posts exist; Phase 0 counts them. A weekly run after that should cost well under $1. The shared ceiling in `config/llm_budget.json` is $10 total across all jobs, so the backfill needs either its own budget line or a one-time raise, with Lorenzo's OK.

## Where the code goes

All new files, so it does not collide with the four section chats:

```
Agentic Worklfows/
  services/offer_intel/
    skool_read.py      # feed + post pages, Wins category, author replies (helpers copied from execution/skool_scraper.py)
    gate.py            # Haiku: win or not, channel
    extract.py         # Sonnet: fields + source sentences, null when not stated
    taxonomy.py        # industry + mechanism normalizing
    rollup.py          # patterns, distinct winners, trends, crowding, fit
    render.py          # Sheet rows, weekly digest, offer card
    tests/             # recorded feed/post payloads with made-up members; LLM_FAKE for model calls
  jobs/offer_intel.py  # --backfill | --since DATE | --preflight | --sample 30 | --dry-run | --card "<pattern>"
  config/offer_intel/taxonomy.json
  runbooks/offer_intel.md
  directives/USER/mine_maker_school_wins.md   # only with Lorenzo's OK (directives are not created without asking)
```

Collection needs the logged-in Chrome profile, so real runs happen on Lorenzo's Mac from the main folder. Everything after collection (gate, extract, roll up) can run anywhere from the saved raw JSON.

## Phases

| Phase | What | Done when | Rough effort |
|---|---|---|---|
| 0. Look | Confirm the group slug (the scraper uses `makerschool`, `services/metrics/skool.py` says `maker-school`), find the Wins category id, count the win posts, save one feed page and one post page as sanitized fixtures | Slug, category id and post count written in the runbook | 30 min with Lorenzo at the Mac |
| 1. Collect | `skool_read.py` + `--backfill` / `--since`, author replies, 14-day comment refresh | Backfill lands in `.tmp/offer_intel/raw/`, re-run adds nothing new, pytest green on fixtures | half a day |
| 2. Gate + extract | Prompts, JSON schema, source-sentence check, `--sample 30`, `--preflight` | Lorenzo's hand check of 30 passes, then the full backfill runs within the approved budget | 1 day |
| 3. Normalize + roll up | Taxonomy, patterns, rankings, Sheet export | `Patterns` tab ranks by distinct winners and each pattern links to its posts | 1 day |
| 4. Weekly | Sunday job, digest, Job_Log row, ntfy on failure, schedule proposed in the runbook | One dry-run week and one real week produce a digest Lorenzo reads | half a day |
| 5. Later (optional) | Screenshot reading, repeat-winner watchlist, offer card into an ICP rubric + list factory target draft | Lorenzo picks a pattern and gets a campaign-ready draft | as needed |

Definition of done follows the repo's rule: pytest green, dry-run output, runbook, Job_Log rows, evidence in the report.

## Decisions for Lorenzo

1. **Scope of posts.** Wins category only (recommended to start), or also scan the general feed for wins posted in the wrong category?
2. **Channels.** Capture every channel and tag it, with cold email as the default view (recommended), or cold email wins only?
3. **Where the table lives.** A new Google Sheet "Offer Intel" (recommended), or a tab in `AdveroSolutions_CRM`?
4. **Spend.** OK to spend roughly $6 per 1,000 win posts on the backfill, and to give it its own budget line instead of using up the shared $10 ceiling?
5. **Skool terms risk.** OK with a weekly, human-paced, read-only run from your logged-in profile? The fallback is a manual weekly export: you copy new wins into a text file, and the rest of the pipeline stays the same.
6. **Directive.** OK to create `directives/USER/mine_maker_school_wins.md` so you can trigger it by name?
