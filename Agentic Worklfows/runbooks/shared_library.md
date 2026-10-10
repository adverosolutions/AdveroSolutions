# Runbook: shared library (`Agentic Worklfows/shared/`)

## Purpose
One httpx-based, dependency-injected package that every service (`services/reply_engine`) and job (`jobs/`) imports for: Instantly and GHL API access, the shadow/live write guard, state store, Job_Log + shadow log, ntfy/Gmail notifications, Claude access with a cost ledger, and the calendar-slot rules (12:00–18:00 CT, Mon–Fri, 4 h lead, 5 business days, no double offers, 07:00–19:00 send window). It exists so the controlled-environment rule is enforced in one place rather than in every script.

## How to run (shadow)
Nothing in this package runs on its own; services import it. To exercise it by hand, from `Agentic Worklfows/`:

```bash
# read-only against live Instantly (allowed in shadow):
python3 -c "from shared.instantly import Instantly; c=Instantly(); print(len(c.list_campaigns()['items']))"   # prints 6

# a shadow write: no HTTP, record lands in .tmp/shadow_log.jsonl
python3 -c "from shared.instantly import Instantly; c=Instantly(); print(c.pause_account('lorenzo@myadvero.com'))"
tail -1 .tmp/shadow_log.jsonl

# GHL without a token: reads return None, writes return the shadow record
python3 -c "from shared.ghl import GHL; g=GHL(); print(g.get_contact('x'), g.add_tags('c1',['t']))"
# (in LIVE with no token the same write raises GHLError after a skipped_no_token Job_Log row;
#  it must never return the None a read miss returns)
```

Environment (`Agentic Worklfows/.env`, then `AdveroSolutions/.env`): `INSTANTLY_API_KEY_READ` and `GHL_PRIVATE_INTEGRATION_TOKEN_READ` (read-only keys, the only Instantly/GHL keys agents see); the write-capable `INSTANTLY_API_KEY` and `GHL_PRIVATE_INTEGRATION_TOKEN` go only in `~/.advero/live.env` and the Modal secret (`runbooks/read_only_keys.md`), `NTFY_TOPIC` (optional), `NOTIFY_EMAIL`/`GMAIL_SENDER_EMAIL`/`GMAIL_APP_PASSWORD` (optional), `JOB_LOG_SHEET_ID` (optional), `ANTHROPIC_API_KEY` (only when `LLM_FAKE` is not `1`), `MODE` (default `shadow`).

## How to test
```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows" && python3 -m pytest shared/tests -q
```
219 tests (full repo suite: 2,228): guard shadow vs live; Instantly and GHL clients via `httpx.MockTransport` asserting URL, method, headers and body, and asserting that **no request is made for any write in shadow**; store atomicity (two forked processes race one `set_if_absent`; exactly one may win) and the Modal backend (stubbed); job log CSV/JSONL and never-raise behaviour; notify with `NOTIFY=off`, the shadow guard (a push and an SMTP send are writes: shadow records the intent and nothing leaves the process), public-topic redaction, ntfy header shape, generated-topic persistence, SMTP seam; LLM fake mode and ledger; 30+ slot cases including DST (Nov 1, 2026), Friday rollover, 4-hour lead, offered-slot exclusion and the five real reply phrasings with `now=2026-09-21T21:10-05:00`; plus a repo walk (`test_send_paths.py`) that fails if any `reply_to_email(...)` call site in the repo omits `to=`.

`conftest.py` forces `MODE=shadow`, `LLM_FAKE=1`, `NOTIFY=off`, unsets `ALLOW_LIVE_WRITES` and the GHL token, and redirects every file the library writes to a temp directory (`ADVERO_TMP_DIR`). The `live_mode` fixture flips the flags for unit tests only; every transport in those tests is mocked.

## How to go live (checklist)
The library itself never goes "live"; the services that import it do. Before the first service flips `MODE=live`:

1. `pytest` green on `shared/tests` and on the service's own tests.
2. 48-hour shadow period: `.tmp/shadow_log.jsonl` reviewed by Lorenzo; every `would_do` record is one he would have approved.
3. Verify the two write payload shapes that could not be confirmed read-only: `blocklist_create` (`POST /block-lists-entries {"bl_value"}`) and `move_to_subsequence` (`POST /leads/subsequence/move {"id", "subsequence_id"}`, **one lead per call**, no `ids` array; `move_leads_to_subsequence(lead_ids, ...)` loops it). Do the first live call of each by hand with one record and compare against `config/instantly_api_contract.md`.
4. `daily_account_analytics` without an `emails` filter returns HTTP 413 on this workspace ("Analytics request is too large"); always pass `emails=[...]` for a subset of inboxes or a short date range.
5. Settle the `to` field on `POST /emails/reply` in the single live-send rehearsal (`runbooks/deployment.md`): `shared/instantly.py` **requires** `to=<lead email>` and raises without it, and `config/instantly_api_contract.md` records the REST reference and the tool schema disagreeing about whether the field exists. Reply to a thread of Lorenzo's own, read the response, then delete whichever half of the double guard turns out to be dead - not before.
6. Mint the GHL Private Integration token (contacts, opportunities, calendars, calendars/events, conversations, workflows) and put it in `~/.advero/live.env` (chmod 600, never a repo `.env`) as `GHL_PRIVATE_INTEGRATION_TOKEN`; mint a second, readonly-scopes-only token into `Agentic Worklfows/.env` as `GHL_PRIVATE_INTEGRATION_TOKEN_READ` (`runbooks/read_only_keys.md`); run a read (`GHL().get_contact(<known id>)`) to confirm scopes.
7. Set `NTFY_TOPIC` (or subscribe to the generated `advero-…` topic printed in `.tmp/ntfy_topic.txt`) and confirm one test push arrives on Lorenzo's phone.
8. Set `JOB_LOG_SHEET_ID` so live writes are mirrored to the `Job_Log` tab; confirm the service account has edit access to that sheet.
9. Only then run the service with `MODE=live ALLOW_LIVE_WRITES=1` for a single lead, watch the Job_Log row and the Instantly/GHL objects, and widen from there.

## Rollback
- Unset `ALLOW_LIVE_WRITES` (or set `MODE=shadow`) and restart the process: every write immediately returns to shadow; no code change needed.
- Every live write leaves a `live_write_intent` row in `.tmp/job_log.csv` (and the sheet) **before** the HTTP call and a `live_write_ok` / `live_write_failed` / `skipped_no_token` row after it, so a write that died at the transport or the gateway - the case where Instantly may already have sent - can still be reconciled. Any Instantly reply, status change, pause or GHL upsert can be found there with its payload and reversed by hand.
- The library never deletes anything (no delete endpoints are exposed).

## Thresholds (from Blueprint Section 6 that this library encodes)
| Rule | Value | Where |
|---|---|---|
| Offered slot window | 12:00–18:00 CT, Mon–Fri | `slots.SLOT_WINDOW`, `candidate_slots` |
| Minimum lead time | 4 h | `slots.MIN_LEAD_HOURS` |
| Horizon | 5 business days | `slots.MAX_BUSINESS_DAYS` |
| Send window | 07:00–19:00 CT | `slots.within_send_window` (hour only), `settings.SEND_WINDOW` |
| Send window + weekdays | Mon–Fri 07:00–19:00 CT | `slots.is_send_time` — anything that auto-sends must use this, not the hour check |
| Cadence hour | 10:00 CT | `settings.CADENCE_HOUR` |
| Instantly rate limit | **reads only**: 429/502/503/504 and transport errors retried up to 3 times, `Retry-After` honoured, backoff capped at 60 s (GET /emails is 20/min). Writes are never retried — no idempotency key, so a retry is a duplicate email | `instantly.MAX_RETRIES`, `RETRY_STATUSES`, `READ_POST_PATHS` |
| LLM spend | ledger per call; every role on Opus 5.5 (`claude-opus-5-5`) since 2026-09-25, $4/$20 per MTok (Haiku, Sonnet and Opus 5 are no longer priced; Fable is retired: no `claude-fable-*` id appears anywhere, and a test pins the price table closed in both directions) | `llm.PRICES_USD_PER_MTOK`, `llm.MODEL_ALIASES` |
| LLM spend **ceiling** | cumulative $10.00 on billed calls, warn at 80%. Over it `complete()` raises `LLMBudgetExceeded` and calls nothing: one push, one `llm.budget`/`refused` Job_Log row. Priced at `max_tokens` before the call, so one large call cannot jump the cap. `LLM_FAKE` calls cost nothing and are never counted or refused. The total lives in the **store**, so it survives a fresh Modal container; without the store it degrades to this process plus the ledger and logs that it did. `budget_usd <= 0` is not unlimited. | `config/llm_budget.json`, `llm.enforce_budget`, `llm.budget_status()`, `llm.reset_spend()` |

## Known gaps / open items
- GHL endpoints are written from the LeadConnector v2 docs but unverified against a live token (none exists). First token-backed dry run should call every read once.
- `warmup_analytics` and `list_leads` are POST requests that only read.
- The Job_Log sheet path requires `gspread` + `google-auth` (both installed locally); it is skipped, with a warning, when `JOB_LOG_SHEET_ID` is unset.
- **The live-write guard is only the two env flags** (the PreToolUse hook was removed 2026-10-10). `settings.is_live()` is `MODE=live and ALLOW_LIVE_WRITES=1`, so a script that sets them in-process (`os.environ[...]`, a sourced profile, an entry in `.env`) runs unblocked. Closing that needs a per-run ticket minted by the approved apply flow and required by `is_live()`; it cannot land in `shared/` alone, because every live entrypoint (`services/reply_engine/modal_app.py`, `jobs/`, `changesets/*/apply_*.py`) and the root `conftest.py` `live_mode` fixture would have to mint one in the same change. Tracked as an open question for Lorenzo.
- **The ntfy topic in `.env` is unprotected and not the generated `advero-<12 hex>` form.** `notify()` therefore withholds every email address, URL and action button from the push and sends the full card by email instead (`NOTIFICATION_EMAIL` + `GMAIL_SENDER_EMAIL` + `GMAIL_APP_PASSWORD` are configured, to Lorenzo's own address). To get full cards on the phone again, set `NTFY_TOKEN` (an ntfy access token on a protected topic) or rotate `NTFY_TOPIC` and accept the risk with `NTFY_ALLOW_SENSITIVE=1`.
