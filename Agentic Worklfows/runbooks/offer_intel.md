# Runbook: Offer Intel (Maker School wins -> ranked offers)

Plan and reasoning: `MAKER_SCHOOL_WINS_PLAN.md`. Code: `services/offer_intel/`, `jobs/offer_intel.py`. Tests: `jobs/tests/test_offer_intel.py` (made-up posts in `jobs/tests/fixtures/offer_intel/`).

## What it does

1. **collect** reads the Maker School Wins category from your logged-in Chrome profile (the same one `execution/skool_scraper.py` uses) and saves each post, plus the author's own replies in its comments, to `.tmp/offer_intel/raw/`. Read-only, human pace.
2. **analyze** asks Haiku "is this a business win, and which channel?" (Sonnet re-checks anything under 0.8 confidence), then asks Sonnet for the offer fields. Every field has to quote the post word for word or it is dropped. A number has to appear in its own quote.
3. **report** (free) maps industries and mechanisms to the fixed lists in `config/offer_intel/taxonomy.json`, ranks industry x mechanism patterns by **different winners in the last 90 days**, and writes:
   - `.tmp/offer_intel/out/wins.csv`, `patterns.csv`, `winners.csv`: import these into a Google Sheet called "Offer Intel"
   - `.tmp/offer_intel/out/digest_<date>.md`: top patterns, 3 to test, risers, unmatched terms
   - `.tmp/offer_intel/out/hand_check.md` (with `--review`): each post next to what the models took from it

Nothing here posts to Skool, and nothing here feeds an email, a reply-engine draft or a proof line (a test fails if a copy path imports it). Other members' numbers are research; `config/offers.md` stays the only proof.

## First real run (Lorenzo's Mac, about 15 minutes)

It has to run on the Mac: the Skool login lives in the Chrome profile there, and the cloud sessions cannot reach skool.com.

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

**2. Look (read-only).** Opens Chrome with the saved Skool profile. If the login expired, log in in that window; the script waits.
```bash
python3 jobs/offer_intel.py look
```
It prints the group's categories and any that look like Wins (`wins_labels`), and saves the payload keys (no post text) to `.tmp/offer_intel/look.json`. If it bounces you to the about page, the slug is wrong: try `--group maker-school`.

**3. Collect 40 posts (read-only, about 5 minutes).** In Chrome, open Maker School, click the Wins category, and copy the address bar. Then:
```bash
python3 jobs/offer_intel.py collect --url "<the Wins category URL>" --max-posts 40
```
Expect `"new": 40` (or fewer) and `"threads_read"` close to that. `"threads_read": 0` means the post pages did not match the expected payload; the posts are still saved, just without the author's replies. Send `.tmp/offer_intel/look.json` to a Claude session to fix it.

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

- **Backfill:** `collect --url ... --max-pages 50 --max-posts 2000`, then `analyze --preflight` (no `--sample`) for the full price, then the billed run. About $6 per 1,000 posts. The shared spend ceiling in `config/llm_budget.json` is $10 across every job, so a big backfill needs a one-time raise (your call).
- **Weekly (proposed, not installed):** Sunday 06:00 CT (`0 11 * * 0` UTC while daylight time holds), before the list factory: `collect --since <14 days ago>`, `analyze`, `report`. It re-reads comments on posts younger than 14 days because authors keep answering questions. Install only after you OK it.
- **Offer card (next build):** for a pattern you pick, a draft in the `offers.md` shape plus an ICP rubric draft and the evidence posts. Never written into `offers.md` or `config/icp/` automatically.

## Job_Log rows (job `offer_intel`)

| status | meaning |
|---|---|
| `look_ok` | categories listed; details carry `wins_labels` and payload keys |
| `collect_ok` / `collect_logged_out` | counts of pages, new, updated, threads read |
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
| `collect` saves 0 posts | the feed payload shape changed | send `.tmp/offer_intel/look.json` (keys only) to a Claude session |
| `STOPPED: ALLOW_PAID_CALLS is not set` | by design | run `--preflight`, then prefix `ALLOW_PAID_CALLS=1` |
| `analyze_budget_stop` | the $10 shared ceiling is spent | raise it or reset per `config/llm_budget.json` (your call) |
| Wrong industry or mechanism in `patterns.csv` | missing keyword | add it to `config/offer_intel/taxonomy.json`; the digest's Unmatched section lists candidates |

## Evidence (2026-09-24, cloud session)

- `python3 jobs/offer_intel.py rehearse`: 12 made-up posts, 11 wins, 1 not a win, 1 escalation, 2 invented fields dropped by the quote check (a wrong monthly price and a guarantee the post never states), 9 patterns, first pick "Dental x Lead / database reactivation" (2 different winners).
- `jobs/tests/test_offer_intel.py`: 53 passed, 0 egress, including the collector driven through a fake browser (paging, empty pages, `--since`, logged out, a timed-out page).
- The repo-wide suite was not run to the end: Lorenzo's call (2026-09-24), since this adds only new files, is internal, and gets tested live. Run it before this merges into `main`.
- Not run: anything against Skool (skool.com is blocked from the cloud container and the login lives on the Mac) and any billed model call.
