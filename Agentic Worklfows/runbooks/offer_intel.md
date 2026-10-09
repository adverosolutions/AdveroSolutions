# Runbook: Offer Intel (Maker School wins -> ranked offers)

Plan and reasoning: `MAKER_SCHOOL_WINS_PLAN.md`. Code: `services/offer_intel/`, `jobs/offer_intel.py`. Tests: `jobs/tests/test_offer_intel.py` and `jobs/tests/test_offer_intel_mcp.py` (made-up posts in `jobs/tests/fixtures/offer_intel/`).

## What it does

1. **collect** reads the Maker School Wins category and saves each post, plus the author's own replies in its comments, to `.tmp/offer_intel/raw/`. Read-only, human pace. On the Mac use `collect --via mcp` (next section). The default `--via playwright` path reads from a logged-in Chrome profile and does not run on the Mac today.
2. **analyze** asks Haiku "is this a business win, and which channel?" (Sonnet re-checks anything under 0.8 confidence), then asks Sonnet for the offer fields. Every field has to quote the post word for word or it is dropped. A number has to appear in its own quote.
3. **report** (free) maps industries and mechanisms to the fixed lists in `config/offer_intel/taxonomy.json`, ranks industry x mechanism patterns by **different winners in the last 90 days**, and writes:
   - `.tmp/offer_intel/out/wins.csv`, `patterns.csv`, `winners.csv`: import these into a Google Sheet called "Offer Intel"
   - `.tmp/offer_intel/out/digest_<date>.md`: top patterns, 3 to test, risers, unmatched terms
   - `.tmp/offer_intel/out/hand_check.md` (with `--review`): each post next to what the models took from it

   Price medians (setup, monthly, deal) count only `new_client` and `first_client` wins, because month totals and call quotes are not one client's price.

Nothing here posts to Skool, and nothing here feeds an email, a reply-engine draft or a proof line (a test fails if a copy path imports it). Other members' numbers are research; `config/offers.md` stays the only proof.

## Collect on the Mac: `collect --via mcp`

Playwright can't run on the Mac: there is no Chromium in `~/Library/Caches/ms-playwright`, no saved profile in `execution/.sessions/skool_profile`, and logging in needs you at the keyboard. The mcp path uses the skool-mcp client that is already logged in instead.

How it works: `services/offer_intel/skool_mcp_fetch.mjs` imports `Coding/skool-mcp/dist/client.js` and makes two GET calls, one per run of the script. `feed` reads one page of the Wins category (30 posts, newest first). `comments` reads one post's comments. Nothing else is called, and nothing is written to Skool.

Prerequisites:
- skool-mcp is built at `Coding/skool-mcp/dist` and already logged in. Its cookie config belongs to the client; Offer Intel never opens it.
- node is installed (nvm's is fine).

Overrides:
- `SKOOL_MCP_CLIENT=/path/to/client.js` when the client lives somewhere else. Without it the collector tries `<repo>/Coding/skool-mcp/dist/client.js`, then `~/Desktop/AdveroSolutions/Coding/skool-mcp/dist/client.js`.
- `NODE_BIN=/path/to/node` when node is not on PATH. Without it the collector uses `node` on PATH, then the newest `~/.nvm/versions/node/*/bin/node`.

90 days of wins (from "Agentic Worklfows/"; set `--since` to the day 90 days back):
```bash
python3 jobs/offer_intel.py collect --via mcp \
  --url "https://www.skool.com/makerschool?c=03d09fffe79e4cd4bb492e2f954cbc1d&s=newest" \
  --since 2026-06-25 --max-pages 12 --max-posts 400
```
Each Skool call waits 2.5 to 4.5 seconds after the one before, and each call starts node. 90 days of wins is roughly 270 Skool calls (the 2026-09-23 run: about 12 feed pages plus one comments call for each of about 256 posts with comments), so it takes roughly 25 to 35 minutes. `--no-threads` skips the comments calls. `--headless` does nothing here.

Statuses (the `status` field, and the Job_Log row `collect_<status>`):

| status | meaning |
|---|---|
| `ok` | the walk finished; see `counts` |
| `logged_out` | the feed came back without a logged-in user. Nothing from that page was saved. Log skool-mcp back in |
| `fetch_failed` | a feed call failed; `detail` gives the error class and message (for example the node script's last stderr line). Posts saved before it stay saved; run again later |
| `mcp_unavailable` | the client or node was not found; `detail` says which |
| `bad_url` | the URL is not a Skool group URL or has no `c=<category id>` |

`counts` holds `pages`, `seen`, `new`, `updated`, `threads_read`, `skipped_old`, `threads_partial`, and `thread_errors` when a comments call failed (that post keeps its feed copy and is retried next run).

Known limits:
- One comments call returns at most 25 top-level comments. 50 or 100 returns HTTP 400. `threads_partial` counts threads that had more, and those records carry `"thread_partial": true`. The paging parameter for the rest is not verified, so the collector does not guess one.
- Post pages carry no comments, so comments only come from the comments call.

## First real run (Lorenzo's Mac, about 15 minutes)

It has to run on the Mac: the cloud sessions cannot reach skool.com. The mcp path uses skool-mcp's own login on the Mac; Playwright's Chrome profile only matters for the Playwright path (`look` and `collect --via playwright`).

The code is on branch `claude/maker-school-wins-tracking-153w0r` until it is merged into `main`. From `/Users/lorenzovillarreal/Desktop/AdveroSolutions`:

```bash
git fetch origin
git checkout claude/maker-school-wins-tracking-153w0r    # or `git pull` on main once it is merged
cd "Agentic Worklfows"
```

**1. Rehearse (free, offline, 5 seconds).** Proves the install works before touching Skool.
```bash
python3 jobs/offer_intel.py rehearse
```
Expect `"wins": 11`, `"escalated": 1`, `"fields_dropped": 2`, and a first pick of `Dental x Lead / database reactivation`. These are made-up posts.

**2. Look (optional, Playwright path only; skip it on the Mac).** Needs Playwright's Chromium and a saved Skool profile, which the Mac does not have today. Where it runs, it opens Chrome with the saved Skool profile; if the login expired, log in in that window and the script waits.
```bash
python3 jobs/offer_intel.py look
```
It prints the group's categories and any that look like Wins (`wins_labels`), and saves the payload keys (no post text) to `.tmp/offer_intel/look.json`. If it bounces you to the about page, the slug is wrong: try `--group maker-school`.

**3. Collect 40 posts (read-only, about 3 minutes).** Uses the Wins URL below, so step 2 is not needed.
```bash
python3 jobs/offer_intel.py collect --via mcp \
  --url "https://www.skool.com/makerschool?c=03d09fffe79e4cd4bb492e2f954cbc1d&s=newest" --max-posts 40
```
Expect `"new": 40` (or fewer). `"threads_read"` counts only posts that have comments.

**4. Price it (spends nothing).**
```bash
python3 jobs/offer_intel.py analyze --sample 30 --preflight
```
Expect roughly $0.10 to $0.50 for 30 posts (`typical_usd`, `worst_usd`).

**5. Analyze 30 (billed).**
```bash
ALLOW_PAID_CALLS=1 python3 jobs/offer_intel.py analyze --sample 30
```

**6. Report and hand check (free).**
```bash
python3 jobs/offer_intel.py report --review
open .tmp/offer_intel/out/hand_check.md .tmp/offer_intel/out/digest_*.md
```
In `hand_check.md`, check each post: is the win call right, and does each value match its quote? **The bar before a full backfill: no invented facts, 90% or more of fields right.** Note anything wrong; the prompt or the quote check gets fixed before the backfill.

## After the hand check

- **Backfill:** `collect --via mcp --url ... --max-pages 50 --max-posts 2000`, then `analyze --preflight` (no `--sample`) for the full price, then the billed run. About $6 per 1,000 posts. The shared spend ceiling in `config/llm_budget.json` is $10 across every job, so a big backfill needs a one-time raise (your call).
- **Weekly (proposed, not installed):** Sunday 06:00 CT (`0 11 * * 0` UTC while daylight time holds), before the list factory: `collect --via mcp --url ... --since <14 days ago>`, `analyze`, `report`. It re-reads comments on posts younger than 14 days because authors keep answering questions. Install only after you OK it.
- **Offer card (next build):** for a pattern you pick, a draft in the `offers.md` shape plus an ICP rubric draft and the evidence posts. Never written into `offers.md` or `config/icp/` automatically.

## Job_Log rows (job `offer_intel`)

| status | meaning |
|---|---|
| `look_ok` | categories listed; details carry `wins_labels` and payload keys |
| `collect_ok` / `collect_logged_out` / `collect_fetch_failed` | counts of pages, new, updated, threads read; `"via": "mcp"` on the mcp path |
| `collect_mcp_unavailable` / `collect_bad_url` | mcp path only; `detail` says what is missing |
| `analyze_preflight` | the price, nothing billed |
| `analyze_ok` / `analyze_budget_stop` | counts, first errors; budget stop means the spend ceiling refused a call |
| `analyze_paid_calls_off` | ALLOW_PAID_CALLS was not set; nothing billed |
| `report_ok` | counts and the files written |
| `rehearse_ok` | the offline rehearsal ran |

## When something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `look` exits "can't see /makerschool" | wrong slug or not a member on that Chrome profile | `look --group maker-school`; log in with the paid account |
| `look` lists no Wins category | the category key in the payload is not the guessed one | click the category in Chrome and pass its URL to `collect`; nothing else depends on the label list |
| `collect --via mcp` saves 0 posts | see `status` and `detail` in the printed result or the `collect_*` Job_Log row | `logged_out`: skool-mcp's login expired, log it back in; `fetch_failed`: `detail` says why; `ok` with `seen: 0`: the feed payload shape changed, send the printed result (counts only) to a Claude session |
| `collect_mcp_unavailable` | skool-mcp not built, or node not found | build `Coding/skool-mcp`, or set `SKOOL_MCP_CLIENT` / `NODE_BIN` |
| `collect_logged_out` on `--via mcp` | skool-mcp's login expired | log skool-mcp back in, then rerun |
| `STOPPED: ALLOW_PAID_CALLS is not set` | by design | run `--preflight`, then prefix `ALLOW_PAID_CALLS=1` |
| `analyze_budget_stop` | the $10 shared ceiling is spent | raise it or reset per `config/llm_budget.json` (your call) |
| Wrong industry or mechanism in `patterns.csv` | missing keyword | add it to `config/offer_intel/taxonomy.json`; the digest's Unmatched section lists candidates |

## Evidence (2026-09-24, cloud session)

- `python3 jobs/offer_intel.py rehearse`: 12 made-up posts, 11 wins, 1 not a win, 1 escalation, 2 invented fields dropped by the quote check (a wrong monthly price and a guarantee the post never states), 9 patterns, first pick "Dental x Lead / database reactivation" (2 different winners).
- `jobs/tests/test_offer_intel.py`: 53 passed, 0 egress, including the collector driven through a fake browser (paging, empty pages, `--since`, logged out, a timed-out page).
- The repo-wide suite was not run to the end: Lorenzo's call (2026-09-24), since this adds only new files, is internal, and gets tested live. Run it before this merges into `main`.
- Not run: anything against Skool (skool.com is blocked from the cloud container and the login lives on the Mac) and any billed model call.
