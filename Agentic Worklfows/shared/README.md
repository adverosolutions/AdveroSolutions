# shared/ — the library every service and job imports

Python 3.9 compatible (no `X | Y`, no `match`). Dependencies: httpx, pydantic, pytz, python-dotenv, anthropic, gspread (sheet log only), modal (cloud only).

```python
from shared import settings, instantly, ghl, store, job_log, notify, llm, slots
from shared import analytics, thresholds, offline
from shared.settings import guard_write, is_live, IDS, OFFERS_MD, TZ
```

## The shadow contract (Lorenzo's controlled-environment rule)

| Env | Meaning |
|---|---|
| `MODE=shadow` (default) | Propose, log, notify. **No write reaches Instantly, GHL or anything else.** |
| `MODE=live` alone | Still shadow (warning logged). |
| `MODE=live` + `ALLOW_LIVE_WRITES=1` | The only combination that sends, books, pauses or moves anything. |

Every write method in `shared.instantly.Instantly` and `shared.ghl.GHL` calls `settings.guard_write(system, action, payload)` **before** building an HTTP request. In shadow it returns

```python
{"shadow": True, "system": "instantly", "action": "reply_to_email", "payload": {...}, "ts": "2026-09-22T02:22:50+00:00"}
```

and appends the same record to `.tmp/shadow_log.jsonl`. The caller receives that dict in place of the API response and performs nothing. Reads (GET, and the POST-shaped reads `leads/list`, `accounts/warmup-analytics`, `accounts/test/vitals` and `inbox-placement-analytics/stats-by-test-id`) always go to the API; they are safe against live data and are how dry-runs work.

**Every write leaves two Job_Log rows in live mode**, so a write that dies at the transport or the gateway can still be reconciled:

| Row | When |
|---|---|
| `<system>.<action>` / `live_write_intent` | written by `guard_write` **before** the HTTP call |
| `live_write_ok` \| `live_write_failed` (with the error) \| `skipped_no_token` | written after |

`settings.require_live(system, action)` raises `LiveWriteBlocked` for code paths that must never silently fall back to shadow.

**What the shadow contract covers.** Instantly writes, GHL writes, `notify()` (push + email) and the Job_Log Google-Sheet mirror. The guarded payload is the body a live run would send - never a field the request does not carry (`blocklist_create` records exactly `{"bl_value": ...}`; the `type` hint lives in the Job_Log details). The one deliberate exception is a write whose target sits in the URL rather than the body (`ghl.add_tags`, `create_note`, `update_opportunity_stage`, `update_appointment_status`, `create_task`; `instantly.update_lead` / `update_campaign`): those records add the id (`contact_id`, `opportunity_id`, `id`) beside the body, because a shadow row that does not say *which* contact it would tag is unreviewable. Anything replaying the log has to put those back in the path. The local CSV/JSONL logs and `.tmp/` files are the only writes shadow still performs.

## Modules

### settings
- `load_env()` — loads `Agentic Worklfows/.env` then `AdveroSolutions/.env` (no override). Runs at import. It never takes the gate flags (`GATE_FLAGS`: `MODE`, `ALLOW_LIVE_WRITES`) from a file: one a file sets is removed again with a WARNING naming the key (not the value), while one already in the process environment is kept, so a `.env` cannot switch the process that loads it live. The deliberate exception is `LAPTOP_LIVE_TIERS` in `.env`, the laptop scheduler's documented switch: `changesets/schedules/laptop_runner.py` reads it from the saved `.env` files and starts the scheduled laptop jobs of a named tier with `MODE=live ALLOW_LIVE_WRITES=1` (those jobs hold no Instantly or GHL write key, by design; see `runbooks/read_only_keys.md`).
- `MODE` (import-time snapshot), `get_mode()`, `is_live()`, `guard_write(system, action, payload) -> dict`, `require_live(system, action)`, `class LiveWriteBlocked(Exception)`.
- `IDS = load_ids()` from `config/ids.json`; `OFFERS_MD = load_offers()` from `config/offers.md`, plus `OFFERS_LOADED` (bool) and `require_offers()` which raises when the sheet is missing or empty. An empty offer sheet makes `draft.validate_draft` reject every draft carrying a number, so it fails at ERROR level rather than silently returning `""`.
- `TZ = pytz.timezone("America/Chicago")`, `SEND_WINDOW=(7,19)`, `SLOT_WINDOW=(12,18)`, `MIN_LEAD_HOURS=4`, `MAX_BUSINESS_DAYS=5`, `CADENCE_HOUR=10`.
- Derived ids: `GHL_LOCATION_ID`, `GHL_USER_ID`, `GHL_SALES_PIPELINE_ID`, `GHL_STAGES{key: id}`, `GHL_CALENDAR_ID`, `BOOKING_URL`, `CAMPAIGNS{key: {...}}`, `CAMPAIGN_BY_ID{id: {..., key}}`.

### instantly — `Instantly(api_key=None, transport=None, base_url=..., timeout=30.0, sleep=time.sleep)`
Auth `Authorization: Bearer <key>`; errors raise `InstantlyError`.

**Retries are for reads only.** 429/502/503/504 and `httpx.TransportError` are retried up to 3 times (`Retry-After` honoured, backoff capped at 60 s for the 20-requests/minute endpoints) on GET and on the four POST-shaped reads in `READ_POST_PATHS` (`leads/list`, `accounts/warmup-analytics`, `accounts/test/vitals`, `inbox-placement-analytics/stats-by-test-id`). Writes are never retried: a 429 can arrive after Instantly has queued the send and there is no idempotency key, so a retry is a duplicate email. A 429 on a write is logged and raised.

`iterate()` stops only when the cursor is absent (an empty page that still carries a cursor is normal when a filter excludes everything on it) and accepts a bare JSON array, which is what `GET /webhooks` and several v2 reads return.

Reads: `list_campaigns(limit=100, starting_after=None)`, `get_campaign(id)`, `list_accounts(limit=100, starting_after=None)`, `list_emails(email_type='received', campaign_id=None, limit=100, starting_after=None, eaccount=None, **extra)`, `get_email(id)`, `list_leads(filter=None, campaign=None, limit=100, starting_after=None, contacts=None, **extra)` (POST), `get_lead(id)`, `campaign_analytics(ids=None, start_date=None, end_date=None)`, `daily_campaign_analytics(campaign_id, start_date, end_date)`, `warmup_analytics(emails)` (POST), `daily_account_analytics(emails=None, start_date=None, end_date=None)` (**this workspace answers HTTP 413 without an emails filter**, short date range or not; an empty `emails` defaults to `IDS['instantly']['active_inboxes']` and raises a clear `InstantlyError` when there is nothing to default to), `campaign_step_analytics(campaign_id, start_date=None, end_date=None)`, `test_vitals(emails)` (POST-shaped read, answers **grouped by domain**), `inbox_placement_list(limit=100, starting_after=None)`, `inbox_placement_stats_by_test(test_ids)` (POST-shaped read), `blocklist_list(limit=100, starting_after=None)` (rows carry `bl_value` + `is_domain`), `audit_logs_list(start_date=None, end_date=None, limit=100)`, `lead_labels_list(limit=100)`, `webhooks_list()`, `subsequences_list(parent_campaign, limit=100)`, `iterate(path, params=None, body=None, max_pages=200)` → **`CursorWalk`** (iterates like the old generator; read `.truncated` after the loop to tell a complete pull from one capped at `max_pages`, and `.complete` for the converse).

Writes (guarded): `reply_to_email(reply_to_uuid, eaccount, subject, body_text, body_html=None, to=None, skip_validation=False)` → `POST /emails/reply`. **`to` is required**: Instantly validates it against the thread before sending, and it is the only server-side protection against a stale or crossed `reply_to_uuid` delivering a reply to the wrong lead. Omitting it raises `InstantlyError` before anything is guarded or sent; `skip_validation=True` is the explicit opt-out. `update_interest_status(lead_email, campaign_id, interest_value)` (rejects any value outside `IDS['instantly']['interest_status_codes']`, so a `4` typed for `no_show` (-4) can no longer mark a no-show as won); `update_lead(id, payload)` → PATCH; `update_campaign(id, payload)` → PATCH; `pause_account(email)` / `resume_account(email)`; `lead_labels_create(label, interest_status_label, description='', use_with_ai=True)`; `webhooks_create(payload)`; `subsequences_create(payload)`; `blocklist_create(value, type='email')` — the request body is exactly `{"bl_value": value}`; `type` is an operator note recorded in the Job_Log details, never in the payload, so the shadow log always matches the live request; `create_lead(campaign, email, ...)` → POST /leads, **one lead per call**, with `skip_if_in_workspace` and `verify_leads_on_import` defaulted true; `inbox_placement_create(payload)` → POST /inbox-placement-tests (**spends credits**); `move_to_subsequence(lead_id, subsequence_id)` (**one lead per call**, `{"id", "subsequence_id"}`) and `move_leads_to_subsequence(lead_ids, subsequence_id)` which loops it.

### ghl — `GHL(token=None, location_id=None, transport=None, base_url=..., timeout=30.0)`
Headers `Authorization: Bearer` + `Version: 2021-07-28`. Ids default from `config/ids.json`. **No token** (`GHL_PRIVATE_INTEGRATION_TOKEN` unset, which is today's state): reads log `ghl_token_missing` and return `None`; writes still call `guard_write` first, so a shadow run records the intent and returns the guard record. **In live with no token the write raises `GHLError` after a `skipped_no_token` Job_Log row** - it must never return the same `None` a read miss returns, or `booking.book()` marks the lead Meeting Booked in Instantly with no calendar event behind it. HTTP errors raise `GHLError` too.

Reads: `get_contact(id)`, `search_contacts(email, page_limit=20)`, `search_opportunities(contact_id=None, pipeline_id=None, stage_id=None, limit=20)`, `get_free_slots(calendar_id, start_date_ms, end_date_ms, timezone='America/Chicago', user_id=None)`, `get_appointment(id)`, `get_opportunity(id)`, `get_calendar_events(calendar_id, start_ms, end_ms)`, `search_conversations(contact_id)`.

Writes (guarded): `upsert_contact(email=None, first_name=None, last_name=None, company=None, phone=None, tags=None, custom_fields=None, name=None, source=None)` (a call without `name`/`source` sends exactly the old body, `"email": None` included; with `name` or `source` and `email=None` it needs a name plus a source or tags and omits `email`; a LIVE call with `email=None` and no phone raises `GHLContactNeedsIdentity` (`ghl_contact_needs_identity`) while `CONTACT_WITHOUT_EMAIL_VERIFIED` is False), `add_tags(contact_id, tags)`, `create_note(contact_id, body)`, `upsert_opportunity(contact_id, pipeline_id, stage_id, name, monetary_value=None, status='open')`, `update_opportunity_stage(opportunity_id, stage_id, status=None, lost_reason=None)` (`lostReason` rides the same PUT, so a third-no-show Lost move mirrors to Instantly as `no_show` (-4) rather than `not_interested` (-1)), `create_appointment(calendar_id, contact_id, start_iso, end_iso, title, assigned_user_id=None, appointment_status='confirmed')`, `update_appointment_status(appointment_id, status, to_notify=None)` (`to_notify=True` is how the invite is released to the prospect after Lorenzo approves; `None` keeps GHL's default and is what every cancel path wants), `send_message(contact_id, type='Email', subject=None, message=None, html=None)`, `create_task(contact_id, title, due_iso, body='')`.

### analytics — one chunked, cached reader for Instantly's analytics endpoints
`account_daily(client, emails, start, end, chunk=None, sleep=..., sleep_seconds=0.5, on_error="degrade", retry_depth=2) -> AccountDaily` (`.rows`, `.missing`, `.errors`, `.retries`, `.complete`), `campaign_totals(client, start=None, end=None)`, `campaign_daily(client, campaign_id, start, end)`, `campaign_steps(client, campaign_id, ...)`, `real_replies(row, unique=True)`, `items(payload)`, `chunked(seq, size)`, `clear_cache(client=None)`, `cache_stats()`, `ttl_seconds()`.

Four components read `GET /accounts/analytics/daily` (the 07:00 monitor, the 07:00 inventory, the 18:00 metrics, the Friday retro) and each used to carry its own chunking loop, its own degradation rule and its own answer to this workspace's 413. This module owns all three. `on_error` picks the policy: `"raise"` (the monitor: a partial fleet must never read as a clean bill of health), `"degrade"` (record the chunk's inboxes as **unread** and keep the rest) or `"halve"` (split and retry, then degrade). **Inboxes nobody could read are `missing`, never "sent nothing"** - an inbox reported as having sent nothing reads as a 0% reply rate, which is a removal proposal.

The cache is per client object, keyed on the exact arguments, TTL from `ANALYTICS_CACHE_TTL_SECONDS` (default 300 s, `0` disables). It exists so one run does not pull the same window twice; two jobs at 07:00 are two processes and share nothing, which is correct.

**`replies` and `replies_automatic` are DISJOINT counters and `replies` already excludes auto-responders.** `real_replies()` never subtracts, and no caller should: on 2026-09-19 the twelve active inboxes recorded `replies=0` with `replies_automatic=7`, so the subtraction returns -7. Full evidence in `config/instantly_api_contract.md`.

### thresholds — every Section 6 / Blueprint M1-M2 number, once
Pure data (imports only `typing`, so it can never fail to load mid-incident). `shared/thresholds.py` is the home of the warm-up line (98%), the reply line (1% at 100 sends), the bounce lines (1% green / 2% alert), the per-inbox limits (25, raised 30 at ≥2% reply) and the level schedule. `jobs/inbox_inventory.py` **binds** its own names to these rather than re-declaring them: before that, one rule lived as `2.0` (a percentage) here and `0.02` (a fraction) there. Since 2026-09-22 the inventory and the deliverability monitor are health alerts only: the M2 reserve ratio was removed from this module, and no job counts a reserve. `RESERVED_CONSTANTS` names anything declared but not yet read, with the reason; a test fails on any other public constant nothing reads.

The 18:00 KPI dashboard keeps its own `services/metrics/kpi.py::SPEC` on purpose, because it carries an alert side and a direction this module does not. The four overlapping numbers are pinned by `jobs/tests/test_metrics_kpi.py::test_thresholds_agree_with_the_shared_deliverability_constants`.

### offline — the recorded Instantly, for rehearsals and the shadow test
`OfflineInstantly.from_recorded(strict=True)`, `offline_client_factory(strict=True, **overrides)`, `UnrecordedRead`, `ShadowContractBypassed`.

It **subclasses `Instantly` and overrides `_request` only**, so every guard, retry decision, payload shape and `guard_write` call is the production path and only the bytes change. A hand-written stand-in re-implements the parts a test happens to use and quietly drops the rest, and then the thing under test is the stand-in. Two consequences: a write that reaches the transport raises `ShadowContractBypassed` (in shadow it should have stopped at `guard_write`), and an **unrecorded read raises rather than answering an empty list** - a silent empty answer turns "no fixture for the placement endpoint" into "the workspace has no placement tests", and the job then reports a clean bill of health for something it never looked at.

`shared.instantly.default_client(**kwargs)` is the one place a job builds its client, so a rehearsal replaces one name:

```python
monkeypatch.setattr(shared.instantly, "default_client", offline_client_factory(strict=False))
```

### store
`Store` (abstract: `get(key, default=None)`, `set(key, value)`, `delete(key)`, `keys(prefix='')`, `items(prefix='')`, `append(key, item)`, and the atomic primitives **`set_if_absent(key, value) -> bool`**, **`add_once(key, item) -> bool`**, **`mutate(key, fn, default=None) -> value`** (read-modify-write under one lock) and **`compare_and_set(key, expected, value) -> bool`** (pass the module sentinel `ABSENT` for "must not exist")), `JsonFileStore(path)` (atomic tmp+rename, fcntl lock), `ModalDictStore(name)` (lazy `import modal`), `get_store(force_new=False)` — `RUNTIME=modal` → Modal Dict `MODAL_DICT_NAME` (default `advero-store`), else `STORE_PATH` (default `.tmp/store.json`). The cache is keyed on `(runtime, path/name)`, so changing `STORE_PATH` after import gives you the store you asked for.

**Never write a once-only decision as `if st.get(k) is None: ... st.set(k, ...)`.** That is two operations: two Modal containers (the webhook and the poller seeing the same reply, two hourly ticks) both read `None`, both act, and the lead gets two replies. Reproduced with two forked processes: get-then-set → both claimed; `set_if_absent` → exactly one. Use

```python
if not st.set_if_absent("processed:%s" % reply_id, {"at": ts}):
    return {"skipped": "duplicate"}          # someone else already owns it
if st.add_once("offered:%s" % date, slot_iso):  # False when already offered
    ...
```

A corrupt `store.json` is never read as an empty one: `JsonFileStore` moves it aside to `store.json.corrupt-<utc>` and raises `StoreError`, because starting empty erases every cadence timer and makes the next tick re-send every touch in the window.

`JsonFileStore` holds the fcntl lock across the whole read-decide-write span; `ModalDictStore` serialises on a lock key taken with `modal.Dict.put(..., skip_if_exists=True)`, breaks a lock held for more than 60 s, and raises `StoreError` rather than racing if it cannot take one within 10 s.

### job_log
`log_run(job, status, details) -> row|None` → CSV `ts_utc,job,status,mode,details` at `.tmp/job_log.csv` (`JOB_LOG_PATH` override) plus the `Job_Log` tab when `JOB_LOG_SHEET_ID` is set (service account from `GOOGLE_CREDENTIALS_JSON` or `credentials.json`). The sheet append is a real network write, so it obeys the shadow contract too: in shadow it records a `google_sheets`/`job_log_append` intent in the shadow log instead of touching the spreadsheet. `shadow(system, action, payload) -> record|None` → `.tmp/shadow_log.jsonl` (`SHADOW_LOG_PATH` override). `read_shadow_log(path=None)`. Both create dirs, never raise. `job_log_read_path()` is what a READER resolves: `use_scratch_logs` repoints `JOB_LOG_PATH` process-wide, so a job that reads the Job_Log during its own `--dry-run` was reading the empty scratch file it had just created and reporting "no runs"; the pre-redirect path is remembered in `JOB_LOG_READ_PATH`. `use_scratch_logs(name, extra_env=None) -> Path` points **both** overrides at `.tmp/scratch/<name>/`, and `extra_env={"LIST_FACTORY_LEDGER_PATH": "cost_ledger.csv"}` redirects the caller's own evidence artifacts into the same directory rather than appending a rehearsal's imaginary spend to the real ledger: every `--dry-run` entry point and the replay call it, because the 48-hour shadow watch is gated on reading `.tmp/job_log.csv` and evidence runs used to write into it (48 `mode=live` rows from scripts that set the live flags in their own process; quarantined under `.tmp/quarantine/`). Call it from anything that produces evidence rather than operates.

### notify
`notify(title, message, priority='default', actions=None, tags=None, click=None, transport=None, email_message=None) -> dict`. `email_message` is the longer body for the EMAIL leg only: ntfy topics are world-readable, so counts belong on the push and the detail in the inbox, and without it a caller had to choose one body for both. ntfy topic from `NTFY_TOPIC`, else generated `advero-<12 hex>` persisted to `.tmp/ntfy_topic.txt` (subscribe URL included in the first message). Email via Gmail SMTP SSL 465 when `NOTIFY_EMAIL` (or `NOTIFICATION_EMAIL`) + `GMAIL_SENDER_EMAIL` + `GMAIL_APP_PASSWORD` are set. `NOTIFY=off` records to `notify.sent_in_test`. `actions` = `"view, Approve, <url>; view, Veto, <url>"` or a list of `(label, url)` / `{"label","url","action","clear"}`; `format_actions(actions)`. Never raises.

A push and an SMTP send are outbound writes, so two gates apply:

| Env | Effect |
|---|---|
| `MODE=shadow` (default) | the intent is recorded through `guard_write('notify', 'push_email', ...)` and **nothing leaves the process** |
| `NOTIFY_SHADOW_SEND=1` | deliver for real during a shadow run (only ever to Lorenzo's own topic and address) |
| `NTFY_TOKEN=<ntfy access token>` | sent as `Authorization: Bearer`; marks the topic protected |
| `NTFY_ALLOW_SENSITIVE=1` | accept the risk of a public topic without a token |

**ntfy.sh topics are world-readable and world-writable by anyone who knows the name.** Unless the topic is protected, `notify()` strips every email address and URL from the title and body (`redact()`) and drops the `Actions` and `Click` headers, because an Approve button on a public topic is a one-tap live send for a stranger; the full card goes out by email instead, and the push says "(details in the email)". **The email leg renders the action URLs as plain `Label: url` lines** (`_action_lines`), so Approve/Veto still work from email on an unprotected topic; before that fix the email carried `message` + `click` only and there was no way to act on the card at all. Subscribe-URL banners are added after redaction.

### llm
`complete(role, system, user, max_tokens=800, json_mode=False, model=None) -> str|dict`. Raises `LLMError` on `stop_reason` `refusal` **and `max_tokens`** (a truncated draft reads as finished and the cadence auto-sends it after a 30-minute veto window). `LLM_FAKE` accepts `1/true/yes/on` in any case; the first real, billed call logs a warning naming the role and model. `MODEL_POLICY = {'classify': 'claude-haiku-4-5-20251001', 'draft': 'claude-sonnet-5', 'research': 'claude-sonnet-5', 'retro': 'claude-opus-5', 'proposal': 'claude-opus-5', 'escalate': 'claude-sonnet-5'}`. Every real call also sends `thinking` from `THINKING_POLICY`, disabled for every role: without it claude-sonnet-5 thinks adaptively, spends output tokens before the text and trips the `max_tokens` guard (a 400-token Upwork draft failed that way on 2026-09-23). Re-enabling one role means setting it to `{'type': 'enabled', 'budget_tokens': N}` with N >= 1024 **and** raising `max_tokens` by at least N at every call site for that role (current caps are 120 to 2,000 tokens), or its calls are refused or cut off and callers quietly fall back; any other shape raises `LLMError` before the call bills. Newer SDKs mark `enabled` + `budget_tokens` deprecated in favour of `adaptive`, which the guard refuses on purpose, so check the accepted shape on the target model before enabling it. `LLM_FAKE=1` → registry (`register_fake(role, fn(system, user, json_mode))`, `clear_fakes()`, `fake_for(role)`), defaults: classify → `{"label": "positive_interested", "confidence": 0.95, "reason": "fake"}`, draft → short deterministic body signed "Lorenzo". Ledger `.tmp/llm_ledger.csv` (`ts,role,model,input_tokens,output_tokens,est_cost_usd,faked`; `faked=1` for an `LLM_FAKE` call, whose `est_cost_usd` is still the projection a rehearsal exists to produce, so a cost AUDIT must filter on the flag rather than sum the column). **The `faked` column was appended on 2026-09-22 and `_record` only ever wrote a header for a brand-new file**, so the ledger already on disk kept a 6-column header over 1,020 six-field rows; `csv.DictReader` then returned no `faked` key for them and `ledger_spend_usd` counted every one as billed, reporting $1.47957 that was never spent. `migrate_ledger_header(path)` fixes that in place (rewrites the header and backfills `faked=1`, since pre-flag rows were all written under `LLM_FAKE=1`) and `_record` now calls it before appending, so a narrow ledger heals itself instead of silently mis-reporting. The real `.tmp/llm_ledger.csv` was migrated on 2026-09-22: 1,026 rows, all `faked=1`, `ledger_spend_usd()` $1.47957 → $0.0 from `PRICES_USD_PER_MTOK` (update that dict when prices change). `estimate_cost(model, in, out)`. **A cumulative spend ceiling sits in front of every billed call**: `enforce_budget()` runs before anything that bills, prices the pending call at `max_tokens` so one large call cannot jump the cap, and over the cap raises `LLMBudgetExceeded` without contacting the model (one push, one `llm.budget`/`refused` Job_Log row, and one warning on the way through `warn_at_fraction`). Config: `config/llm_budget.json` (`budget_usd` default $10.00, `warn_at_fraction` 0.80; `budget_usd <= 0` is NOT unlimited and falls back to the default). The running total lives in the **store**, not the ledger CSV, so it accumulates across Modal containers instead of resetting every tick; a store outage degrades to this process plus the local ledger and says so. `LLM_FAKE` calls cost nothing, so they are neither counted nor refused. `budget_status()` reads it, `reset_spend()` zeroes it.

### slots (pure, clock injected)
`business_days_ahead(now, n)`, `candidate_slots(free_slots, now, already_offered, tz=TZ, window=(12,18), min_lead_hours=4, max_business_days=5, slot_minutes=15) -> [datetime]`, `is_offerable(dt, now, already_offered=None, ...) -> bool`, `pick_two(cands, spread=True)`, `format_slots(two, tz=TZ) -> "Tue 2:00 or Thu 3:30 CT"`, `format_slot(dt, tz)`, `parse_proposed_time(text, now, tz=TZ) -> Optional[datetime]` (CT), `parse_availability_window(text, default_tz=TZ) -> Optional[(start_hour, end_hour, tz)]`, `within_send_window(now, tz=TZ, window=(7,19))`, `is_send_time(now, tz=TZ, window=(7,19))`, helpers `strip_quoted`, `strip_phone_numbers`, `detect_tz`, `parse_iso`, `to_tz`, `ensure_aware`. Bare hours with no am/pm: 1–6 → pm, 7–11 → am. `CTS/CST/CDT/CT` → Central, `EST/EDT/ET/Eastern/Estern` → Eastern.

Rules worth knowing before you call any of it:

- **`strip_quoted` returns `""` when nothing survives above the quote.** It never falls back to the raw text: a bottom-posted reply ("> Would Tue 2:00 or Thu 3:30 CT work?" then "Neither works") would otherwise be parsed as if Lorenzo's own offered times were the lead's proposal. It understands Gmail's line-wrapped `On ... <newline addr> wrote:` attribution and Zoho's `---- On ... wrote ----`.
- **Phone numbers are blanked before time parsing** (`strip_phone_numbers`), or "contact Barbara at 1-800-311-6441" parses as "at 1" and yields 13:00. Across the 44 recorded September replies the parser now claims a time for 4 (all genuine positives) instead of 6: the out-of-office auto-responder and the hostile "do not contact us again" reply no longer produce one.
- **"next Tuesday" is the Tuesday of the following week**, whatever today is. **This costs bookings, on purpose.** Eight days out is past `MAX_BUSINESS_DAYS=5`, so `booking.evaluate_reply` answers `beyond_horizon` for "next Tuesday at 2pm" and counter-proposes instead of booking: the lead who said yes waits for Lorenzo to tap "Book as asked". Plain "Tuesday at 2pm" books. Both readings are defensible and two components disagreed (DECISIONS F4); the library keeps this one because a shared library changing meaning under its callers is worse than either answer. Pinned in `shared/tests/test_slots.py::test_next_weekday_always_means_the_following_week_and_what_that_costs` and `services/reply_engine/tests/test_cadence_booking.py::test_next_weekday_is_never_auto_booked_and_that_is_the_documented_cost`. Changing it is Lorenzo's call; change both tests and this line in the same commit.
- **`within_send_window` is the hour check only and answers `True` on a Saturday.** That is what the approval queue wants (an approved reply may go out on a weekend). Anything that auto-sends must gate on `is_send_time`, which also requires a business day (Blueprint S2 "skip weekends").
- **`parse_proposed_time` does not check the slot rules.** A lead who proposes 11:30 parses fine and breaks the no-mornings rule; run the result through `is_offerable` (or `candidate_slots`) before booking it.
- `parse_iso` normalises any fractional-second length to the 3 or 6 digits Python 3.9 accepts, and `candidate_slots` logs (never silently swallows) an `already_offered` entry it cannot read, because an unread reservation is how a slot gets offered twice.

## Files the library writes (all under `.tmp/`, override root with `ADVERO_TMP_DIR`)
`job_log.csv`, `shadow_log.jsonl`, `store.json` (+ `.lock`), `ntfy_topic.txt`, `llm_ledger.csv`. Tests point `ADVERO_TMP_DIR` at a temp dir via `conftest.py`.

## Tests
```
cd "Agentic Worklfows" && python3 -m pytest shared/tests -q
```
`conftest.py` forces `MODE=shadow`, `LLM_FAKE=1`, `NOTIFY=off`, unsets `ALLOW_LIVE_WRITES` and `GHL_PRIVATE_INTEGRATION_TOKEN`. Fixtures: `tmp_env`, `shadow_mode`, `live_mode` (live flags with **mocked** transports only). `test_notify.py` opts into `NOTIFY_SHADOW_SEND=1` so it can assert request shapes; `test_store.py` forks two processes to prove `set_if_absent` really is a claim; `test_send_paths.py` walks every `.py` file under `Agentic Worklfows/` and fails if any `reply_to_email(...)` call site omits `to=` (the library raises at send time, this fails at review time).
