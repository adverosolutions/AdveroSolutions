# Runbook: the list factory (M5 / job O8)

## Purpose
3,300 verified, ICP-scored, personalized leads a week at no more than $0.07 per verified contact (the run's hard cap since 2026-09-25; Section 6's green line is still $0.02), running unattended on Sunday, so every campaign always has at least five days of uncontacted leads (Blueprint Section 6).

The factory **never uploads anything**. The last stage writes a CSV and records one `POST /leads` intent through `shared.settings.guard_write`. In shadow that is a line in the shadow log and no HTTP request. Turning the upload on is a separate, deliberate step that Lorenzo approves (see "Going live" below).

## Read this first: the cap is $0.07 and the projection prices worst-case thinking

**Lorenzo, 2026-09-25:** every model call now runs on Claude Opus 5.5, whose thinking cannot be turned off and bills as output. The preflight and the in-run projection price each model call with the worst case, 1,024 thinking tokens (`shared.llm.output_tokens_with_thinking`, about $0.02 a call): one per personalization line, one per ICP batch and one per possible ICP escalation (up to `--max-escalations`, default 50, which the preflight had never priced before). That alone is about $0.025 per personalization line, so the cap (`LIST_FACTORY_MAX_COST_PER_CONTACT_USD`, `shared/thresholds.py`) was raised from $0.02 to **$0.07**. Measure the real thinking spend on the first real run and lower the cap again.

`--preflight` on 2026-09-25 (cleaning, target 3,300):

| Source | Total | Per **confirmed** contact | Per deliverable (catch-alls included) | Verdict |
| --- | --- | --- | --- | --- |
| Apify `code_crafter/leads-finder` | $153.74 | **$0.06212** | $0.04659 | within the $0.07 cap |
| Google Maps | $160.53 | **$0.06486** | $0.04864 | within the $0.07 cap |

Of the Apify total, personalization is $81.44 and ICP $27.54 (text tokens plus worst-case thinking), the source $33.64. The per-niche pulls of `--all-campaigns` price at $0.06453 per confirmed contact (600 contacts per niche). Before 2026-09-25 the same Apify run priced at $55.05 and $0.02224 (Sonnet and Haiku, no thinking), over the old $0.02 cap, and every run halted before the source fetch.

**The $0.04 alert line did not move.** A run that finishes above $0.04 per confirmed contact gets verdict `alert` and status `over_cap` (non-zero exit, push) even inside the $0.07 cap; the message says so ("inside the run's own $0.0700 cap, which was set above the alert line"). A run that really spends the worst case (about $0.062) would finish that way. Real thinking at effort `low` should be well under 1,024 tokens a call, which is what the first real run measures.

**The escalation allowance is a fixed worst case**: 50 extra calls of thinking is about $1.07. A 3,300-contact run absorbs it (under 1% of the bill); a very small run does not. The recorded 58-business fixture, run with the default 50 escalations, projects about $0.16 per confirmed contact and halts, which is why the fixture tests run with `--max-escalations 0`.

The old runbook said $46.22 / $0.0140 for Apify. Three separate errors made that number: the preflight priced `fill_rate=1.0` while the run over-fetched by `1/0.36`; owner look-ups were hard-coded at $0 for Apify; and catch-all results were counted as verified contacts. Since the 2026-09-22 re-review (MKT-1) the preflight's figure is enforced as a gate in front of Apify: a run over the cap stops with `status: halted` ("before the source fetch") and spends nothing.

## The pipeline

```
source -> presuppress -> icp -> owner -> patterns -> verify -> finder
       -> suppression -> personalize -> stage
```

| Stage | What it does | Costs | Module |
| --- | --- | --- | --- |
| source | Apify `code_crafter/leads-finder` sharded by US state, Google Maps by metro, or a recorded fixture | $0.02/run start + $0.002/lead **returned** (Apify) | `sources.py` |
| presuppress | The FREE half of suppression: "this domain is already in a campaign", knowable the moment a row arrives | free | `suppression.py` |
| icp | Keyword hard-reject, keyword hard-accept, then Claude Opus 5.5 in batches with an escalation (also Opus 5.5) below 0.8 confidence | ~$0.0011/business in text tokens, plus 1,024 worst-case thinking tokens (about $0.02) per batch call of 20 and per escalation (up to 50), all priced by the preflight; **gated** | `icp.py` |
| owner | Name from the source row when it has one, otherwise `execution/discover_owner.py` | $0.005/look-up, $0 when the row carries a name | `contacts.py` |
| patterns | `first@`, `first.last@`, `flast@`, `firstlast@` only | free | `contacts.py` |
| verify | MillionVerifier, first hit wins | $0.0006/check | `contacts.py` |
| finder | Paid finder on a miss. **Stub: no LeadMagic or Prospeo account exists**, so it only prices what one would have cost | $0.0035/find if it existed | `contacts.py` |
| suppression | The address-level half. Mandatory, fail-closed. See below | free | `suppression.py` |
| personalize | One Claude Opus 5.5 line per lead, checked against the copy rules, plus the trigger variables | ~$0.0042/lead in text tokens plus 1,024 worst-case thinking tokens (about $0.02), ~$0.025/lead as priced; **gated** | `personalize.py` |
| stage | CSV + one `POST /leads` would_do record | free | `stage_out.py` |

Each stage only touches the leads that have not been through it (`RunState.pending(stage)`), which is what makes a run resumable.

**Why suppression runs twice.** The domain-level check is free and knowable from `lead['domain']` at sourcing time. Running the whole check only after verification meant paying for a Perplexity look-up and 2.6 MillionVerifier checks on companies already in a campaign: 14 of 58 rows in the recorded rehearsal. The address-level half still runs after verification, where the candidate addresses exist.

## Run it

From `Agentic Worklfows/`:

```bash
# price the run before spending anything (exits 1 when the projection is over the cap)
LLM_FAKE=1 python3 jobs/list_factory.py --preflight --niche cleaning --target 3300 --source apify

# full rehearsal on the recorded 58-business fixture. Nothing paid, nothing uploaded.
# LLM_FAKE=1 is REQUIRED: without it the ICP and personalization stages bill real
# Anthropic tokens (they are gated, so they refuse rather than bill, but the run
# then reports `blocked` and stages nothing).
LLM_FAKE=1 NOTIFY=off MODE=shadow python3 jobs/list_factory.py \
  --now --fixtures --offline --target 3300 --verify replay --fresh

# the Sunday run: every enabled campaign in config/list_factory_targets.json,
# Cleaning Reactivation first; source and verifier come from that file (apify, millionverifier).
# Needs ALLOW_PAID_CALLS=1 for Apify, Perplexity, MillionVerifier and this job's Anthropic calls.
ALLOW_PAID_CALLS=1 python3 jobs/list_factory.py --now --all-campaigns --refresh-suppression

# price the Sunday run, one block per niche pull (exits 1 when any is over the cap)
LLM_FAKE=1 python3 jobs/list_factory.py --preflight --all-campaigns

# one niche by hand: --now REQUIRES --source and --verify (no fixture or replay fallback)
ALLOW_PAID_CALLS=1 python3 jobs/list_factory.py --now --niche cleaning --source apify \
  --target 3300 --verify millionverifier --refresh-suppression

# continue a run that died or halted. The run keeps the niche, campaign split, target, source
# and verifier it was started with (read from its state file), so name none of them; a
# --campaign, --target, --niche, --source or --verify that differs is refused. This works the
# same for a niche pull of an --all-campaigns run, which is resumed on its own, WITHOUT
# --all-campaigns (that mode refuses --resume). An open run that merely died is also picked up
# by an unattended retry; a HALTED run is closed and is only continued this way.
ALLOW_PAID_CALLS=1 python3 jobs/list_factory.py --now --resume cleaning_20260922_033544_b473
# after a halt, paying for the rest is an explicit decision: raise the cap on the resume
ALLOW_PAID_CALLS=1 python3 jobs/list_factory.py --now --resume cleaning_20260922_033544_b473 \
  --max-cost-per-contact 0.025

# a dry run of the Sunday run: fixture and replay (free) unless you name paid ones yourself.
# A dry run ALWAYS starts fresh, keeps its run state and logs under .tmp/scratch/list_factory_dryrun/,
# never picks up an open run and refuses --resume. (It used to adopt an open real Apify run,
# verify its paid leads with the replay and close it as ok.)
# The only recorded fixture is 50 cleaning businesses, so every niche pull replays that file.
LLM_FAKE=1 NOTIFY=off python3 jobs/list_factory.py --dry-run --all-campaigns --offline

python3 jobs/list_factory.py --attribution   # replies per 1,000 sends by source (read-only)
python3 jobs/list_factory.py --runs          # resumable runs
python3 -m pytest jobs/tests -q              # the tests
```

Schedule: Sunday, per Blueprint Section 7 (the exact slot lives in `services/reply_engine/modal_app.py::SCHEDULES`). **The scheduled command must be `python3 -m jobs.list_factory --now --all-campaigns --refresh-suppression`.** The old `--now --niche cleaning` now refuses to start (Job_Log row `refused` and a high-priority push) because it names no source and no verifier: its old defaults were the recorded fixture and the replay verifier, so it raised `source=fixture needs --fixture <path>` every Sunday with no row and no push (MKT-3). The schedule itself is owned by the deploy slice.

### Which campaigns it feeds (owner decision R10)

`config/list_factory_targets.json` has one entry per campaign in `config/ids.json`, in run order, **Cleaning Reactivation first**. `services/list_factory/targets.py` refuses a file that leaves a campaign out, an enabled entry whose niche rubric in `config/icp/` does not name the campaign, and a disabled entry with no `disabled_reason`.

| Campaign | Fed | Weekly target | Why |
| --- | --- | --- | --- |
| cleaning_reactivation | yes, first | 300 | M4: scale first |
| cleaning_trigger | yes | 300 | M4: scale |
| bookkeeping_reactivation | yes | 300 | M4: keep |
| bookkeeping_trigger | yes | 300 | M4: keep to 1,000 |
| recruiting_reactivation | **no** | 0 | M4 retires recruiting at 1,000 sends; buying leads for it is Lorenzo's call. 464 of its 664 leads are not yet contacted |
| recruiting_outbound | **no** | 0 | same. 452 of its 648 leads are not yet contacted |

The uncontacted counts are `leads_count` minus `contacted_count` in the recorded Instantly analytics overview (`services/experiments/fixtures/campaign_overview_2026-09-22.json`). An earlier version of this table said "2,507 live recruiting leads already exist"; that was wrong. `config/icp/recruiting.json` records 2,507 live leads carrying the **filler** specialty "your clients'", which is a data-quality fact, not a count of usable stock.

**Disabling recruiting departs from owner decision R10** ("cover every cold campaign"). It rests on M4 retiring recruiting at 1,000 sends and is Lorenzo's call: flip `enabled` and set a `weekly_target` in the file to feed it.

Every run prints the disabled entries with their reasons and puts them in its Job_Log row.

**One file, one kind of run.** An entry's `source` and `verify` may be the paid ones (`apify`/`gmaps`, `millionverifier`) or the rehearsal ones (`fixture`, `replay`). A file whose entries are all rehearsal makes `--now --all-campaigns` a rehearsal: its logs go to `.tmp/scratch/`. A file that **mixes** the two (across niche pulls, or inside one, such as `apify` + `replay`) is refused under `--now`, into the real Job_Log with a push, before any pull runs: one run's logs are either real or scratch, and a mixed run would hide a paid pull's spend in scratch or put a rehearsal's made-up `create_lead_batch` record where the 48-hour shadow watch reads. The weekly target is one week of worst-case first-touch sends at today's campaign `daily_limit` (50 a day x 6 sending days); it has to be raised with the campaign limits for the Oct 11 scale-up.

**One source pull per niche, split at the staging step.** Both campaigns of a niche use identical Apify filters, and the actor returns identical rows for identical filters, so two pulls would pay twice for the same businesses and stage each company for both campaigns (a staged CSV is not in the suppression list until it is uploaded). The pull is sized for the niche's summed target; staged leads go to the campaigns in file order, each up to its target, with any surplus going to the first. A trigger campaign takes the leads whose trigger variables were filled (`advero_b_variant: yes`) first; a reactivation campaign takes the others first. Each campaign gets its own CSV, `staged_<niche>_<campaign>.csv`, and its own `POST /leads` intent.

### The four gates

| Gate | Effect |
| --- | --- |
| `MODE=shadow` (default) | the `POST /leads` intent is recorded; nothing is uploaded |
| `MODE=live` + `ALLOW_LIVE_WRITES=1` | the only combination that could upload |
| `ALLOW_PAID_CALLS=1` | the only thing that lets this job call Apify, Perplexity, MillionVerifier or its own Anthropic stages (ICP scoring, personalization). **On its own**: live mode is not required (owner decision R7) |
| `LLM_FAKE=1` | model calls answer from a deterministic offline stand-in and cost nothing |

They are independent on purpose. A run can spend real money building a list while still uploading nothing, which is exactly what the first real Sunday run should do. **So a shadow run spends money whenever `ALLOW_PAID_CALLS=1` is set**; `MODE=shadow` does not protect the budget.

**`ALLOW_PAID_CALLS=0` does not stop Anthropic spend.** It only gates this job. The reply engine, `precall_tick.py` and `retro_packet.py` bill Anthropic through `shared/llm.py`, which is gated only by `LLM_FAKE` and the $10 ceiling in `config/llm_budget.json`. To stop all model spend, set `LLM_FAKE=1` as well.

Anthropic was added to the third gate on 2026-09-22. Before that the two model stages billed real tokens whenever `LLM_FAKE` was unset, and the runbook's own "nothing paid" rehearsal command omitted it: $10.29 of a $55 run sat outside every flag this table advertised.

`--verify replay` spends nothing and draws each answer from `fixtures/mv_recorded_rates.json` (7,026 real recorded MillionVerifier checks). **Those addresses arrived already flagged `email_status: validated`, so the replay rates are an upper bound, not a prediction.** `--replay-ok-multiplier 0.5` stresses the cost model against a pessimistic assumption. Every replayed row carries `advero_verified_by: replay` in the CSV and in the `POST /leads` payload, and the cost-ledger row carries `verifier=replay, dry_run=yes`, so it can never be mistaken for a paid one.

### Re-running and resuming

- The job **looks for an unfinished run for the niche and continues it** rather than starting over. An at-least-once scheduler that fires the Sunday job twice used to pay for the whole pipeline again. `--fresh` forces a new run. Only `--now` does this: a `--dry-run` never picks up, resumes, changes or closes an existing run (its state lives in its scratch directory), and an `--all-campaigns` run refuses to pick up an open run made with a different source or verifier than the targets file names (a rehearsal left open, say).
- **A resume runs with the stored source and verifier, never others**, and whether its logs are real or scratch is decided from them before anything is written: resuming a fixture or replay rehearsal writes its Job_Log row and its `create_lead_batch` record into the scratch logs, not the ones the 48-hour shadow watch reads, even when `--verify replay` is not typed again.
- Run ids carry a random suffix, and `RunState.create` refuses to overwrite an existing `state.json`. Two invocations in the same second used to produce the same id and reset the first run's leads to `[]`.
- The ledger is written into `state.json` on every checkpoint, so a `kill -9` mid-stage still leaves the spend on disk and the resumed run inherits it. Without that the cap restarted on every resume.
- Resuming a run that already finished is safe: the staging step is skipped and the CSV is left alone. It used to be rewritten from an empty list, leaving a header-only file, while reporting `ok`.

## Suppression: the part that must never be skipped

Built read-only from the live workspace on every run (cached per day under `.tmp/list_factory/suppression/<date>.json`):

| Source | Read | What it contributes |
| --- | --- | --- |
| every lead in the workspace | `POST /leads/list`, walked to the end | the address, and the company domain |
| bounces | the same pull, `status == -1` | the address |
| unsubscribes | the same pull, `status == -2` | the address |
| blocklist | `GET /block-lists-entries` | address or domain |
| hostile replies | `GET /emails?email_type=received`, matched against `HOSTILE_MARKERS` | the sender and their domain |
| clients, our own domains, free mailbox providers | `config/icp/suppression_manual.json` | domains |

Measured 2026-09-22, after the matching fixes: **4,930 addresses and 4,268 domains, including 20 bounces and 15 hostile rows from 14 distinct senders out of 115 received emails.**

The earlier figure of 16 was wrong by one: `info@theaugustacpa.com`, subject `Automatic reply: Stefanie, question`, fired on the bare marker `do not email` because the firm's standard footer reads "please do not email documents containing sensitive information". That is an out-of-office, not an opt-out, and it suppressed the firm and its whole domain permanently in the bookkeeping niche, where the footer is industry boilerplate. Three changes fixed it:

- markers are matched **whole-phrase** (`icp.keyword_hit`), never as substrings. `marker in blob` made "was spam filtered" hit `as spam`;
- **quoted text is stripped** before matching (`> ` lines, `On ... wrote:`, the Outlook `________ From:` block), so a warm reply that quotes our own unsubscribe footer is not an opt-out;
- **auto-replies are skipped by subject** (`Automatic reply`, `Out of Office`, `Auto:`, `Undeliverable`, ...). **Do not filter on `ue_type == 2`**: every one of the 115 received rows in this workspace carries it, so that filter would suppress nobody. Pinned by `test_instantly_ue_type_cannot_be_used_to_spot_an_auto_reply`.

Every hostile hit is recorded with the marker that fired (`sources.hostile_replies.hits`) and the count is printed in every run summary, so a false positive is visible without opening the cache file. The 115 replies are recorded in `services/list_factory/fixtures/received_emails_recorded.json` so the claim is checkable offline.

**Do not replace the full workspace pull with a filtered one.** Measured 2026-09-21: `leads/list` silently ignores a `filter` value it does not recognise. A body carrying `filter: "TOTAL_NONSENSE_XYZ"` returned all 4,918 leads, identical to no filter. Statuses are read off the full pull instead, where a wrong value can only over-suppress.

**Fail-closed, three ways.**

1. If any source errors, or a cursor walk comes back truncated, the list is incomplete and the pipeline **refuses to stage** (`status: refused`).
2. `--skip-hostile-scan` now marks the list incomplete too. It used to drop a mandatory source and leave `complete=True`, and the hostile-free list was then written to the day cache and reused by later runs that never passed the flag. A list built with a skipped source is never cached. The flag is a diagnostic, not a way to run faster.
3. A list **older than 24 hours is refused like an incomplete one**. `built_utc` was stored and never read: a 16-week-old file passed the fail-closed check exactly like a fresh one. `--allow-stale-suppression` overrides it and says so loudly. `--refresh-suppression` now wins over `--suppression`; before, the saved file silently took precedence and the rebuild flag was a no-op.

The suppression list, its size and its age are printed at the top of every run summary.

**Add every client's domain to `config/icp/suppression_manual.json` the day they sign.** Nothing else knows about them: there is no GHL token, so the factory cannot see the Won stage.

## The cost cap ($0.07 per confirmed contact)

`services/list_factory/ledger.py` holds every unit price with its provenance and is the only place to change one.

The cap is checked in four places, all on **one formula** (`Ledger.projected_from`: money spent plus money still to spend, over confirmed mailboxes so far plus confirmed mailboxes still to come):

1. **before the source fetch**, on the preflight's own projection (`pipeline._gate_before_source`). Apify is about 61% of a documented run's bill, and a cap first consulted after the fetch is consulted after most of the money is gone;
2. at every stage boundary;
3. inside the owner loop and the verify loop, every `--batch-size` units;
4. never after the stage step: nothing is left to spend, so a finished run over the cap reports `over_cap`, not `halted`.

The projection prices every live lead from where it actually stands (`pipeline.project_run`): a sourced row still owes the free-suppression survival (0.76), an ICP call, `icp_pass`, a look-up when it has no name, `owner_rate`, 2.6 MillionVerifier checks and a personalization line; a lead with an owner owes the checks and the line; a verified lead owes the line. Its denominator is **confirmed** mailboxes, with the catch-all share taken out, the same as `cost_per_verified` and the preflight. The old projection divided by deliverables (catch-alls in) and ignored suppression at the source boundary, so on the documented Apify run it read $0.0161 where the preflight read $0.0222, and the run spent the whole $55.05 before halting after personalization (MKT-1). Rates are the plan's until the run has verified something, then its own observed ones.

Over the cap and the run **halts at that point, and makes no further paid call of any kind**: no source, look-up, verification or personalization money. What is already verified **and** personalized is still staged: the address-level suppression check runs (free, it reads the list the run already holds) and those leads go into a separate `staged_<niche>_<campaign>_halted.csv` beside the run state, so a later `--resume` writing the main CSV can never overwrite it. Verified leads that have no personalization line yet are **not** staged (the copy interpolates the line) and are **not** personalized either: the salvage used to write their lines after the halt, and a run the cap stopped on "$30 still to spend" then made 30 paid personalizer calls and finished at $1.00 per contact while reporting `halted`. The Job_Log row says `halted` with a `salvaged` count and an `awaiting_personalization` count, and Lorenzo gets a push. Paying for those lines is an explicit decision: `--resume <run_id>` with a raised `--max-cost-per-contact`.

**Money with no confirmed contact is over the cap.** When nothing has been confirmed and nothing is still expected but money was spent or is still to spend, the cost per confirmed contact is unbounded. The in-run check halts on it, and a run that finishes that way reports `over_cap` (non-zero exit, push). It used to pass as `ok`, because the projection had no number for it.

"Nothing still expected" is judged on a real sample, not on luck. The run's observed deliverable and confirmed rates replace the plan's only after **30 leads** have been through verification (`ledger.MIN_OBSERVED_SAMPLE_LEADS`). The first version switched after the first 20-check batch, about 7 leads, and at the plan's 0.375 confirmed per lead an all-catch-all first batch happened on about 7% of healthy pulls, halting them as "unbounded". At 30 leads a healthy list shows zero confirmed by chance with probability (1 - 0.375)^30 = 7.5e-7 at the plan rate, and 0.12% at a pessimistic 0.2 per lead.

A raised cap does not change an unbounded halt. What it means depends on what is left: if leads are still waiting for verification, `--resume <run id>` **re-tests** verification on a fresh sample (the plan's rates stand in again until 30 new leads are verified) instead of re-halting at the first boundary on the rate the first pass saved; if every lead is already verified, the list itself produced no confirmed mailbox.

A finished run over a line names the line it crossed: the run's own cap, Section 6's $0.04 alert line, or both. A run given `--max-cost-per-contact 1000` that finished at $0.05 used to be reported "over the $1000.0000 cap (verdict alert)".

A resumed run inherits the money the first pass spent, and that spend now survives an unclean exit.

### Catch-alls are not verified contacts

A catch-all domain accepts every local part at SMTP time, so for an address the factory **guessed** there is no evidence the mailbox exists. About a quarter of real checks come back this way (1,392 of 5,737 recorded plain-pattern checks; 26% in the rehearsal). They used to be counted as verified, which put roughly 980 unconfirmed guesses into the denominator of the cost KPI and of the 3,300 target.

They are now counted separately everywhere:

- `cost_per_verified` (the Blueprint KPI and the green/over_cap verdict) divides by **confirmed mailboxes only**;
- `cost_per_deliverable` is reported beside it, and the catch-all share is printed;
- the cost-ledger row has a `catch_all` column;
- `--catch-all exclude` stages confirmed mailboxes only, so Lorenzo chooses.

`verify_leads_on_import: true` does not rescue this: Instantly reports catch-all domains as `accept_all` and imports them anyway.

One row per run lands in `.tmp/list_factory/cost_ledger.csv` with per-stage counts, dollars, and the `source`, `verifier`, `dry_run` and `target` columns that tell a free rehearsal from a real paid run. **Rehearsal rows go to a scratch ledger**, not the real one, and the gate keys on the source and verifier actually in use, not on the `--fixtures` shorthand.

Verdicts: `green` at or under the lower of the run's cap and $0.04, `alert` above $0.04 (Blueprint Section 6), `over_cap` above a cap set below $0.04, `halted_over_budget`. With the $0.07 default a finished run is `green` up to $0.04 and `alert` above it.

## ICP rubrics

One file per niche in `config/icp/`. `hard_reject_keywords` beats `hard_accept_keywords` beats the model, and an `unsure` answer is a rejection.

**A hard accept only fires from the business's own words** (`company_name`, `description`, `headline`), never from `keywords`. The Apify actor echoes its own search terms into every row: "janitorial services, facilities services" appears on 27 of the 58 recorded businesses for no reason other than the query we sent. A bin-cleaning company, two window washers and an office-moving company were accepted at confidence 1.0 before the model ever saw them. Hard **reject** still reads every field, because over-rejecting on an echoed term costs a fraction of a cent and no query we send contains a reject phrase.

Keywords match on **whole phrases**, not substrings. A bare `in` test rejected "Industrial and warehouse cleaning crews" as a residential maid service.

`jobs/tests/test_list_factory_pipeline.py::test_only_real_commercial_cleaners_reach_the_csv` asserts an **allow-list over every staged name**. The old version grepped for four words and passed while "Cleanse Your Bins" and "Gillette Window And Solar Cleaning" went out as commercial cleaners. When a new business legitimately joins the fixture's output, add it to `STAGEABLE` deliberately.

## Trigger variables

`cleaning_trigger` needs `buildingType` and `metro`; `recruiting_outbound` needs `specialty`. The factory derives them from the business's own text and from `execution/us_metros.py`, and a lead it cannot fill them for is staged with `advero_b_variant: no` rather than a guess.

Two rules, both learned from real output:

- evidence is **weighted by phrase length**, so "medical office" outweighs a passing "office";
- **a tie answers `''`**, not "whichever key the JSON lists first". Nine of the eighteen tagged leads in the recorded rehearsal were decided by a tie and five landed on `medical` off a 1-1 tie, purely because `medical` is the first key in `cleaning.json`. That word goes into the email.

The recruiting rubric's trailing-space entries `"it "`, `"hr "` and `"vp "` were removed: `keyword_hit` strips the keyword, so they became the bare words it/hr/vp and matched ordinary English. "We make it simple to hire attorneys" was tagged `specialty: technology`, and `specialty` is interpolated into live `recruiting_outbound` copy.

Note that **no live campaign references `buildingType` or `metro` today**.

## Copy rules

Every personalization line is checked before it can ship: no em dashes, no exclamation marks, no mention of AI, automation or tools, no pitch, no price, no call to action, 30 to 240 characters, opens with `Hey <first name>,`.

Banned words are matched on **word boundaries**, not as substrings. `"ai "` and `" ai"` were substring tests, so "air ducts", "airport terminals", "aisles", "Dubai" and "Mumbai" all read as AI talk and the best, most checkable lines were silently swapped for the dull template. `"bot"` matched "Bottom Line Bookkeeping" and `"llm"` matched "Allman" and "Pllc": 88 of 13,988 real company names failed both the model line and the template, and the lead was dropped at the last stage after being fully paid for. Symbol rules (`$`, `/mo`) are still substring tests, because a word boundary would never fire on "$500".

There are now three lines to try, not two: the model's, the dull template, and a **nameless** variant that omits the company name for the case where the name itself trips a rule. Only after all three fail is the lead rejected, and the reject is logged with its `lead_key` and company name.

## Failure modes

| Symptom | Meaning | Do |
| --- | --- | --- |
| `status: refused` | the suppression list is incomplete, stale, or a mandatory source was skipped | re-run with `--refresh-suppression`; check the Instantly key |
| `status: blocked` | a paid call was refused (Apify, Perplexity, MillionVerifier **or Anthropic**), at any stage | intended in a rehearsal; for a real run set `ALLOW_PAID_CALLS=1` and `--resume` (held leads are picked up) |
| `status: halted` + "before the source fetch" | the preflight's projection is over the cap; nothing was spent | take one of the "Going live" decisions, or raise `--max-cost-per-contact` |
| `status: halted` | projected cost broke the cap mid-run | read the ledger row; what was verified and personalized is staged in `_halted.csv`; nothing else was paid for; the rest resumes with a raised cap |
| `status: over_cap` | the run finished, but over the cap | correct `pipeline.DEFAULT_RATES` from the ledger before the next paid run |
| `refused: --now needs --source and --verify` | a `--now` run named no source or verifier | use `--all-campaigns`, or name both |
| `status: error` with an exception name | the job itself crashed | the Job_Log row and the push carry the exception; fix and re-run |
| `status: short` | the run staged less than half its target (or nothing) | read the stage lines for where the leads were lost, then `--resume` |
| `status: error` + "failed outright" | MillionVerifier is erroring or out of credits | the leads are **held, not rejected**; fix the key or the balance and `--resume` |
| `unsure: ...` on most leads | the model stage is not answering | check `ANTHROPIC_API_KEY` and that `LLM_FAKE` is not set on a real run |
| every lead `no_domain` | the source is returning rows without websites | expected attrition on Google Maps |
| B-eligible far below half | `us_metros` does not cover the states being sourced | add cities, or shard the source onto covered metros |

**A run that produces nothing is never `ok`.** It returns a non-zero exit code and pages Lorenzo. Before, an empty source, a closed gate at verify, or twelve failed Apify shards all reported `ok`, exit 0, no notification, and the campaigns ran dry on Thursday.

**A run that cannot start is never silent either.** `main` catches every exception, an argument error and a refused start, writes a Job_Log row (`error` or `refused`) and sends a high-priority push. It used to catch only a rubric error and a suppression error, so the scheduled run's `ValueError` left nothing behind. `--all-campaigns` writes one row per niche pull plus a summary row (`ok` or `partial`) and sends one push naming every pull that did not deliver.

## Going live (not done, needs Lorenzo)

1. Run `--preflight --all-campaigns` and read the projected cost. **It currently says OVER CAP for both sources, and a `--now` run halts before the source fetch until this is decided.** Decide one of:
   - accept `cost_per_deliverable` ($0.0167 Apify) as the KPI, i.e. agree that a catch-all counts as a contact;
   - raise the cap for the first run and measure the real rates;
   - cut the source line, which is 61% of the Apify bill: `icp_pass` of 0.65 is the assumption that sizes it, and the rubric changes above should have raised it.
2. Run once with `ALLOW_PAID_CALLS=1` and **without** live writes. Real money, real list, nothing uploaded. (Live mode is not needed for the money to be spent: `ALLOW_PAID_CALLS=1` alone opens the paid gate.)
3. Read the staged CSV by hand. Twenty rows: is every one a real commercial cleaner, is every line something Lorenzo would send.
4. Correct `pipeline.DEFAULT_RATES` from the ledger's observed rates. Only rows with `dry_run=no` and a real `verifier` are evidence. `observed_name_rate` is recorded per run so the owner-cost assumption self-corrects.
5. Only then, and only with Lorenzo's sign-off, upload. `shared.instantly` has no `create_lead` yet; that method is a cross-cutting request.

## Files

- `jobs/list_factory.py` (the job), `services/list_factory/` (the pipeline), `config/icp/` (rubrics and manual suppression)
- `config/list_factory_targets.json` (which campaigns the Sunday run feeds) and `targets.py` (its loader)
- `jobs/tests/test_list_factory_*.py` (`test_list_factory_schedule.py` pins the Sunday command and the campaign coverage), fixtures in `services/list_factory/fixtures/`
- Rebuild the source fixture: `python3 services/list_factory/fixtures/build_fixture.py`
- Run state: `.tmp/list_factory/runs/<run_id>/state.json` and the staged CSV beside it
