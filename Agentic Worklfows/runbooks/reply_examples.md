# Reply examples and the poller start date

Lorenzo, 2026-09-25: "We only need the replies from the most recent thing, since that has been the time when my skills are the best... We don't need to do all 2,000." and "Then we'll add context every time I reply to a new one."

Two pieces:

1. The poller ignores every reply received before a start date (default 2026-09-15, the first day the six 2026 campaigns sent).
2. Every reply Lorenzo sends himself from an Instantly thread is kept as an example, so a later `decide()` step can see how he answers each kind of reply.

Code: `shared/settings.py` (`poller_start_at`), `services/reply_engine/poller.py` (`fetch_new_replies`, `run_once`), `services/reply_engine/reply_examples.py`, `services/reply_engine/cadence.py` (`detect_manual_first_reply`), `jobs/seed_reply_examples.py`. Tests: `services/reply_engine/tests/test_poller_start_date.py`, `services/reply_engine/tests/test_reply_examples.py`.

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

The run summary and its Job_Log row carry `start_at`, `before_start` (how many were skipped this run) and `reached_start`.

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

Only his own replies. The hourly tick's thread check (`cadence.detect_manual_first_reply`) runs only for a lead with no engine reply recorded, and only takes a manual row sent by hand from the inbox (`ue_type` 3). The seed job skips any row whose id is an engine touch's Instantly id, or whose time is within 10 minutes of an engine send recorded on the lead row (`reply_sent`, or a cadence touch of kind `done`). A row of ours with no lead message before it in the thread (a bump) is not an example.

### When it is captured

- **Every hourly cadence tick** (Modal `cadence_tick`): when the thread check finds Lorenzo's first reply to a lead and records it as day 0, it also keeps that reply as an example (`reply_examples.capture_first_reply`). The result of the check says `example: recorded`, `duplicate`, `skipped` (no text) or `failed`. A failure never stops the tick or the ladder. If the list row has no text, it reads `GET /emails/{id}` once (read-only).
- **Once, by hand**: `jobs/seed_reply_examples.py` for the replies he already sent since the start date.

### Where it is stored

The engine store (`shared.store.get_store()`): the Modal Dict of the current mode on Modal (`advero-reply-engine-store-shadow` in shadow), `.tmp/store.json` on the laptop. One key per example, `reply_example:<email_id>`, written with `set_if_absent`, so the tick and the seed can both see the same email and it is kept once.

### How to seed

From `Agentic Worklfows/`, with the read-only Instantly key in `.env` (`INSTANTLY_API_KEY_READ`):

```
# 1. Dry run (the default). Reads GET /emails?email_type=manual back to the start date
#    (and GET /emails/{id} for a row with no text), prints each example it would record,
#    writes nothing to the store. Its Job_Log row goes to .tmp/scratch/seed_reply_examples_dryrun/.
python3 jobs/seed_reply_examples.py

# 2. Read the list. Each example shows the date, the lead, the campaign, the category,
#    the lead's message and your reply. Skipped rows say why (engine_sent, no_lead_message,
#    no_reply_text).

# 3. Record them in the deployed shadow store (needs your Modal token):
python3 jobs/seed_reply_examples.py --write --modal

#    or in the local store only:
python3 jobs/seed_reply_examples.py --write
```

Other flags: `--start-at` (default `POLLER_START_AT`, else 2026-09-15), `--pages` (default 10 pages of 100), `--store PATH`, `--json`, `--as-of`. Rerunning is safe: an email already kept shows as `exists` and costs no read.

Nothing is sent, tagged or moved. The job makes GET calls only (at most `--pages` list pages, plus up to two `GET /emails/{id}` per new example whose list rows carry no text: his reply and the lead's message; the client backs off on a 429 from the 20-a-minute `GET /emails` limit) and no model call. Lorenzo said he sent about 4 replies in the period, so expect a handful; the recorded September manual list (21 September) holds 8 answers of his to lead messages.

A lead message the engine never classified (it arrived before the engine was watching) is recorded with no category. It still shows in `recent()` with no category filter.

### How decide() will use them

Read API: `reply_examples.recent(category=None, n=5, store=None)` returns the `n` newest examples (by the date he sent them), newest first, only the given category when one is passed.

The plan for `decide()` (Opus 5.5, not built yet): for an incoming reply classified as `category`, put `recent(category, n=5)` (topped up from `recent(None)` when there are fewer) into the prompt as "how Lorenzo answered replies like this", each as the lead's message and his reply.

The examples are context only. They never change which text auto-sends: the only text that sends without a card is still an approved template, unchanged since approval, with the kill switch off and every send check passing (`runbooks/template_approvals.md`). No module that drafts, gates or sends imports `reply_examples`; `test_nothing_in_the_send_path_reads_the_examples` fails if one does.
