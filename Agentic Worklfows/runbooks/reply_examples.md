# Reply examples and the poller start date

Lorenzo, 2026-09-25: "We only need the replies from the most recent thing, since that has been the time when my skills are the best... We don't need to do all 2,000." and "Then we'll add context every time I reply to a new one."

Two pieces:

1. The poller ignores every reply received before a start date (default 2026-09-15, the first day the six 2026 campaigns sent).
2. Some of Lorenzo's own replies are kept as examples, so a later `decide()` step can see how he answers each kind of reply. Not every reply he sends: the hourly tick keeps his **first hand-sent reply per lead**, under the conditions in "When it is captured" below, and the seed job adds whatever it finds when Lorenzo runs it. His later replies in a thread are not captured (Open).

Code: `shared/settings.py` (`poller_start_at`, `require_start_not_future`), `services/reply_engine/poller.py` (`fetch_new_replies`, `run_once`), `services/reply_engine/reply_examples.py`, `services/reply_engine/cadence.py` (`detect_manual_first_reply`, `tick`), `jobs/cadence_tick.py`, `jobs/seed_reply_examples.py`, `changesets/deploy/cutover.py` (`live_activity`). Tests: `services/reply_engine/tests/test_poller_start_date.py`, `test_reply_examples.py`, `test_reply_examples_tick.py`, `test_seed_reply_examples_pairing.py`.

## 1. The poller start date

Setting: `POLLER_START_AT`, read from the process environment.

| Value | Meaning |
| --- | --- |
| unset or empty | the default, `2026-09-15` (`settings.POLLER_START_AT_DEFAULT`) |
| `2026-09-15` | a date alone is midnight **America/Chicago** |
| `2026-09-15T08:30:00` | a datetime with no offset is read as America/Chicago |
| `2026-09-15T13:30:00Z` or `...-05:00` | taken as written (`Z` is UTC) |
| `off` (or `none`, `0`, `false`, `no`) | no start date: the poller walks back as far as its cursor and page budget reach, as it did before |
| anything else | the poll stops with a `ValueError` before it reads anything |

Where the default comes from: `runbooks/deliverability.md` ("Sending began 2026-09-15") and `runbooks/metrics.md` (a read-only `GET /accounts/analytics/daily` over 2026-09-01..14 for the twelve active inboxes returned zero rows). The earliest recorded reply (`fixtures/instantly_replies_2026-09.json`) is 2026-09-15 16:17 UTC.

On Modal the container uses the code default: `POLLER_START_AT` is listed in `modal_app.ENV_NOT_IN_SECRET`, so changing it there is a code change. On the laptop, `python3 -m services.reply_engine.poller --dry-run --start-at 2026-09-18` overrides it for one run.

What happens to a reply older than the start date:

- it is never passed to `process_event`, so it is never classified, drafted or carded, and it costs no model call;
- it is marked seen (`poller:seen`) and listed in the run's results with `skipped: before_start_date`, so no later poll takes it up;
- paging stops at it. `GET /emails?email_type=received` answers newest first (checked against the recorded September page: 44 rows in strictly descending `timestamp_created`), so every row after it is older too. The rest of that page is taken the same way (already fetched, so free) and no further page is requested;
- it is not a failure: it does not go into `poller:failed`, does not hold the cursor, and the scan counts as complete, so the cursor moves to the newest row as usual. A reply that failed on an earlier run and is older than the start date (the date was moved past it) is taken out of `poller:failed`, since it will never be retried.

The cursor rules are unchanged: a scan cut short by `--limit`, the page budget, the time budget, an in-flight claim or a reply that failed fewer than 3 times still keeps the cursor where it was. The start date only bounds how far back the rescan goes. A row with no readable timestamp is never skipped for the start date; it is processed (or fails and is retried) as before.

The run summary and its Job_Log row carry `start_at`, `before_start` (how many were skipped this run) and `reached_start`. They also carry `before_start_ids` (the skipped reply ids, newest first) and `retired_failed_ids` (the ids taken out of `poller:failed` because they are older than the start date, sorted), with the count `retired_failed`. Each id list stops at 20 (`poller.LOG_ID_CAP`); the counts are always exact.

### Rollback

Use this when a start date skipped replies that should have been processed. It is Lorenzo's step: the store on Modal is written only with his Modal token.

What the poller keeps (keys in `services/reply_engine/poller.py`):

- `poller:seen` (`SEEN_KEY`) maps each email id to its `timestamp_created`. A skipped reply is in it, so no later scan takes it up.
- `poller:cursor` (`CURSOR_KEY`) holds `last_email_id` and `last_timestamp`. The scan stops at the row with that id, or at the first row whose `timestamp_created` sorts before `last_timestamp` (a plain string compare). So removing seen entries alone does nothing: the scan stops at the cursor before it gets back to them.

Steps:

1. Pick the new start date, earlier than the replies you want back, or `off`. On Modal it is the code default `settings.POLLER_START_AT_DEFAULT` (`POLLER_START_AT` is in `modal_app.ENV_NOT_IN_SECRET`), so change it in code and deploy first. If you skip this, the next tick skips the same replies again. On the laptop pass `--start-at`.
2. Check what the rescan will pick up: `python3 -m services.reply_engine.poller --dry-run --start-at <new date>`. The dry run uses a throwaway empty store, so it lists every reply back to the new date; the ones older than the old date are the ones coming back.
3. Find the `poller:seen` entries whose timestamp is before the old start date and on or after the new one. The Job_Log rows of the skipping runs name them in `before_start_ids` (up to 20 per run; the snippet below finds all of them).
4. Remove them from `poller:seen`, and set `poller:cursor` to `{"last_email_id": "", "last_timestamp": "<the oldest removed timestamp>"}`. The empty id never matches, and a row with exactly that timestamp is not "before" it, so the scan reaches the oldest removed reply and stops right after it. Replies newer than that are still in `poller:seen` and are not processed twice. After the rescan the cursor moves back to the newest row as usual.
5. Do step 4 right after a tick finishes: a tick that is running at the same time writes its own cursor and seen list back over yours. Read both keys again afterwards to check.
6. The next tick (or a laptop run without `--dry-run`) processes them. Check its Job_Log row: `processed` should include them and `before_start` should be 0.

The rescan reads at most 20 pages of 100 on Modal (`run_once` `max_pages`), 5 on the laptop (`--pages`).

Copy-paste from `Agentic Worklfows/`. It prints what it would change and writes only with `WRITE = True`:

```python
from shared import settings
from shared.store import open_modal_store, get_store
from services.reply_engine import poller as P

OLD_START = "2026-09-18"   # the start date that skipped them
NEW_START = "2026-09-15"   # the new start date, or "off"
WRITE = False              # True only after reading the printout

store = open_modal_store("shadow")   # Modal (needs your token); get_store() is the laptop's .tmp/store.json
old = settings.parse_start_at(OLD_START)
new = settings.parse_start_at(NEW_START)
seen = store.get(P.SEEN_KEY) or {}
back = {}
for eid, stamp in seen.items():
    at = P._row_time(stamp)
    if at is not None and at < old and (new is None or at >= new):
        back[eid] = stamp
for eid, stamp in sorted(back.items(), key=lambda kv: kv[1]):
    print(stamp, eid)
cursor = {"last_email_id": "", "last_timestamp": min(back.values())} if back else None
print("%d to remove; cursor now %s; new cursor %s" % (len(back), store.get(P.CURSOR_KEY), cursor))
if WRITE and back:
    store.mutate(P.SEEN_KEY, lambda cur: {k: v for k, v in (cur or {}).items() if k not in back}, {})
    store.set(P.CURSOR_KEY, cursor)
    print("written")
```

## 2. Reply examples

### What is captured

One record per reply Lorenzo sent himself:

| Field | What it is |
| --- | --- |
| `email_id` | his email's Instantly id (the dedupe key) |
| `date` | when he sent it, CT |
| `lead_message`, `lead_message_id`, `lead_message_at` | the lead's message he answered: its text (quoted history cut, capped at 1,500 characters), id and time |
| `reply` | his reply's text (quoted history cut, capped the same way) |
| `category` | the reply category the engine classified the lead's message as (for example `positive_interested`); empty when the engine never classified it |
| `campaign_id`, `campaign_key`, `offer`, `niche` | the campaign and its offer, from `config/ids.json` |
| `thread_id`, `lead_email`, `eaccount`, `subject` | the thread, the lead and the inbox |
| `sent_by`, `source`, `recorded_at` | always `lorenzo`; `thread` (the hourly tick) or `seed` (the seed job); when it was recorded |

Only his own replies. The seed job refuses to run at all once the engine has sent live (see "How to seed"), because the engine's thread_reply, show-rate and no-show sends would read as his. The hourly tick's thread check (`cadence.detect_manual_first_reply`) runs only for a lead with no engine reply recorded, and only takes a manual row sent by hand from the inbox (`ue_type` 3). The seed job skips any row whose id is an engine touch's Instantly id, or whose time is within 10 minutes of an engine send recorded on the lead row (`reply_sent`, or a cadence touch of kind `done`). A row of ours with no lead message before it in the thread (a bump) is not an example.

### When it is captured

- **Every hourly cadence tick** (Modal `cadence_tick`), his first hand-sent reply per lead only, and only when all of these hold: the lead's newest card is `pending`, `blocked`, `stale_slots` or `expired`; no reply of ours is recorded and the ladder is unarmed; the lead has a thread id and inbox and an inbound within 14 days (the card's own reply too); the ladder is not over (booked, opted out, lost, not now...); the tick is not a dry run and still has thread reads left (10 a tick). His reply is a manual row with `ue_type` 3 in the lead's thread, sent after the reply the card answers. When the thread check finds it and records it on the lead (day 0, armed or not), it also keeps that reply as an example (`reply_examples.capture_first_reply`). The result of the check says `example: recorded`, `duplicate`, `skipped` or `failed`; the `first_reply_from_thread` Job_Log row carries the same `example`, with `example_reason` when skipped (`no_reply_text`, `read_failed`, `no_email_id`) or failed (the error). The tick's own Job_Log row counts them in `first_reply_examples` (`recorded`, `duplicate`, `skipped`, `failed`). A failure never stops the tick or the ladder: the lead's day 0 is recorded either way.
- **His text**: if the list row has no text, it reads `GET /emails/{id}` once, read-only and a single try (no retries, so a failing read never eats the tick's 240 s). That read counts toward the tick's `FIRST_REPLY_MAX_READS`, and if it fails the example is `skipped` (`read_failed`) and the rest of that tick's thread checks are deferred to the next tick, as after a failed thread read. The tick does not retry that example (the lead's reply is recorded, so later ticks no longer check the lead); a seed run can pick it up.
- **The lead's message**: from the card (`lead_reply`). An older card without one takes it from the thread rows the tick already read (no extra read): the row with the card's email id, else the lead's newest non-auto-reply row in the thread before his reply. The manual list may not hold the lead's rows; then the example has no lead message.
- **Once, by hand**: `jobs/seed_reply_examples.py` for the replies he already sent since the start date.

### Where it is stored

The engine store (`shared.store.get_store()`): the Modal Dict of the current mode on Modal (`advero-reply-engine-store-shadow` in shadow, `-live` in live), `.tmp/store.json` on the laptop. One key per example, `reply_example:<email_id>`, written with `set_if_absent`, so the tick and the seed can both see the same email and it is kept once.

How long they last: Modal deletes a Dict entry after 7 days with no read or write (`runbooks/deployment.md`, "Four Dicts"). The hourly cadence tick reads every `reply_example:*` key (`reply_examples.keep_alive`, reported as `reply_examples_read` on the tick's summary), as it reads every lead record, so the examples last as long as `cadence_tick` runs. If the tick stops for 7 days they are gone; re-seed then. The laptop's `.tmp/store.json` never expires.

At cutover (`runbooks/deployment.md` step 5) the live Dict starts empty. After `cutover.py --apply`, **Lorenzo** copies the shadow examples into it:

```
python3 jobs/seed_reply_examples.py --copy-shadow-to-live                               # dry run: the count
python3 jobs/seed_reply_examples.py --copy-shadow-to-live --write --i-am-lorenzo-live   # Lorenzo only
```

It refuses before `cutover:record` exists (the cutover needs an empty live store), never overwrites an example already in live, and the cutover does not count copied `reply_example:*` keys as live activity. A cutover `--redo` deletes them with the rest of the live store: copy again after it.

### How to seed

**Every step here is Lorenzo's to run**, the dry run included (it reads live Instantly with his key; no agent runs it). From `Agentic Worklfows/`, with the read-only Instantly key in `.env` (`INSTANTLY_API_KEY_READ`):

```
# 1. [Lorenzo only] Dry run (the default). Reads GET /emails?email_type=manual back to the start date
#    (and GET /emails/{id} for a row with no text), prints each example it would record,
#    writes nothing to the store. Its Job_Log row goes to .tmp/scratch/seed_reply_examples_dryrun/.
python3 jobs/seed_reply_examples.py

# 2. Read the list. Each example shows the date, the lead, the campaign, the category,
#    the lead's message and your reply. Skipped rows say why (engine_sent, no_lead_message,
#    no_reply_text).

# 3. [Lorenzo only] Record them in the deployed shadow store (needs your Modal token):
python3 jobs/seed_reply_examples.py --write --modal

#    or in the local store only:
python3 jobs/seed_reply_examples.py --write
```

The job refuses (exit 2, a Job_Log row `refused`, nothing read or written):

- a start date later than now;
- once the engine has sent live: the store has `cutover:record` or `cutover:accepted`, an engine `reply_sent`, or a cadence touch of kind `done` that was not a shadow record. The engine's thread_reply, show-rate and no-show sends cannot be told apart from his in the thread, so the seed is for before go-live only;
- the live Dict (`--modal` with MODE=live, or MODE=live at all) without `--i-am-lorenzo-live`.

Other flags: `--start-at` (default `POLLER_START_AT`, else 2026-09-15), `--pages` (default 10 pages of 100), `--store PATH`, `--json`, `--as-of`. Rerunning is safe: an email already kept shows as `exists` and costs no read.

Nothing is sent, tagged or moved. The job makes GET calls only (at most `--pages` list pages, plus up to two `GET /emails/{id}` per new example whose list rows carry no text: his reply and the lead's message; the client backs off on a 429 from the 20-a-minute `GET /emails` limit) and no model call. Lorenzo said he sent about 4 replies in the period, so expect a handful; the recorded September manual list (21 September) holds 8 answers of his to lead messages.

A lead message the engine never classified (it arrived before the engine was watching) is recorded with no category. It still shows in `recent()` with no category filter.

### How decide() will use them

Read API: `reply_examples.recent(category=None, n=5, store=None)` returns the `n` newest examples (by the date he sent them), newest first, only the given category when one is passed.

The plan for `decide()` (Opus 5.5, not built yet): for an incoming reply classified as `category`, put `recent(category, n=5)` (topped up from `recent(None)` when there are fewer) into the prompt as "how Lorenzo answered replies like this", each as the lead's message and his reply.

The examples are context only. They never change which text auto-sends: the only text that sends without a card is still an approved template, unchanged since approval, with the kill switch off and every send check passing (`runbooks/template_approvals.md`). Rule: examples may shape a draft; auto-send still needs an exact approved-template match. `test_reply_examples.py` pins it both ways: `template_gate`, `template_approvals`, `approval` (the send and auto-send path), `thread_reply` and `shared/instantly.py` must never mention `reply_examples` or the `reply_example:` key (deny-list), and only the allow-listed modules may import it (`cadence.py`, `jobs/seed_reply_examples.py`, `changesets/deploy/cutover.py`, with a slot reserved for `decide()`).

## Open

- **Capture every hand reply, not only the first per lead** (needs Lorenzo's OK). Today the tick keeps only his first hand-sent reply per lead; his later replies in a thread reach the store only through a seed run, and the seed is for before go-live only.
- **The seed after go-live.** It refuses once the engine has sent live, because it cannot tell the engine's thread_reply, show-rate and no-show sends from his. Recording the Instantly id of every engine send would let it run after go-live.
- **Seeded examples without a category.** A lead message the engine never classified is kept with no category; classifying it would cost model calls.
- **`decide()` is not built.** `recent()` is the read API it will use.
- Done in this change and no longer open: the skipped ids on the poller's Job_Log row and the rollback steps above (review item 5), the capture outcome on the Job_Log rows and the single-try `GET /emails/{id}` (item 9), the seed's `ue_type` handling (item 10), and the lead-message fallback from the thread rows for a card without `lead_reply` (item 11).
