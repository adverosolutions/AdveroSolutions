# Instantly v2 API contract (verified against developer.instantly.ai on 2026-09-21)

Authoritative for `shared/instantly.py` and every change-set. These schemas were read from the official reference pages, not guessed. Where this file and a code comment disagree, this file wins. Re-verify before any first live write.

Base: `https://api.instantly.ai/api/v2` · Auth: `Authorization: Bearer <INSTANTLY_API_KEY>`

## API-key scopes per endpoint (decision R2(a), checked 2026-09-22)

Reads send `INSTANTLY_API_KEY_READ` (falling back to `INSTANTLY_API_KEY` until it exists); only guarded live writes send `INSTANTLY_API_KEY` (`shared/keys.py`, `runbooks/read_only_keys.md`). Read or write is decided per client method, not by HTTP verb. The same table is `shared.instantly.ENDPOINTS`; keep the two in step.

Three scopes were read off the reference on 2026-09-22 and are **verified**. Every other row is **unverified**: its reference page names no scope (`GET /campaigns/analytics` among them), and some endpoints accept only `all:*` scopes. `all:read` is expected to cover every read below, which is why the runbook asks for it; that is unverified per row, so the first read with the new key is the check.

| Endpoint | Access | Scope needed |
|---|---|---|
| `GET /campaigns`, `GET /campaigns/{id}` | read | unverified |
| `GET /campaigns/analytics` | read | unverified (the page lists no scope) |
| `GET /campaigns/analytics/daily`, `GET /campaigns/analytics/steps` | read | unverified |
| `GET /accounts`, `GET /accounts/{email}` | read | unverified |
| `GET /accounts/analytics/daily` | read | unverified |
| `POST /accounts/warmup-analytics` | read | unverified |
| `POST /accounts/test/vitals` | read | unverified |
| `GET /emails` | read | **`emails:read`** (or `emails:all`, `all:read`, `all:all`) |
| `GET /emails/{id}` | read | unverified |
| `POST /leads/list` | read | **`leads:read`** |
| `GET /leads/{id}` | read | unverified |
| `GET /inbox-placement-tests` | read | unverified |
| `POST /inbox-placement-analytics/stats-by-test-id` | read | unverified |
| `GET /block-lists-entries` | read | unverified |
| `GET /audit-logs` | read | unverified |
| `GET /lead-labels` | read | unverified |
| `GET /webhooks` | read | unverified |
| `GET /subsequences` | read | unverified |
| `GET /lead-lists`, `GET /background-jobs/{id}` | read | unverified |
| `POST /emails/reply` | write | **`emails:create`** (or `emails:all`, `all:create`, `all:all`) |
| `POST /leads/update-interest-status` | write | unverified |
| `POST /leads/subsequence/move` | write | unverified |
| `POST /leads` | write | unverified |
| `PATCH /leads/{id}` | write | unverified |
| `PATCH /campaigns/{id}` | write | unverified |
| `POST /accounts/{email}/pause`, `POST /accounts/{email}/resume` | write | unverified |
| `POST /lead-labels` | write | unverified |
| `POST /webhooks` | write | unverified |
| `DELETE /webhooks/{id}` | write | unverified (the endpoint itself is unverified, see below) |
| `POST /subsequences` | write | unverified |
| `POST /block-lists-entries` | write | unverified |
| `POST /inbox-placement-tests` | write | unverified (spends credits) |
| `POST /lead-lists`, `POST /leads/move` | write | unverified |

A 403 on a read made with the read-only key raises `InstantlyScopeError` naming the scope from this table, or saying it is unverified.

## Rate limits (shared across v1 and v2, per workspace, across all keys)
100 requests/second and 6,000 requests/minute; over either returns 429. Batch about 100 calls then wait ~2 seconds. Endpoint exceptions that matter here: `GET /emails` (list email) is **20 requests per minute**. Send-a-test-email is 10/min. None of the write endpoints below declare their own limit.

## POST /emails/reply — reply to an email
```json
{"eaccount": "lorenzo@theadvero.com", "reply_to_uuid": "<email id>", "subject": "Re: ...",
 "body": {"text": "...", "html": "..."},
 "additional_recipients": ["a@b.com"], "cc_address_email_list": "", "bcc_address_email_list": "",
 "reminder_ts": "2026-09-24T15:00:00Z", "assigned_to": "<user uuid>"}
```
Required: `reply_to_uuid`, `eaccount`, `subject`, `body`. Body is a **nested object** with `text` and/or `html`; there are no flat `body_text` / `body_html` fields.

**`to` and `skip_validation`: UNRESOLVED, and the code sends both belts.** The published REST reference above does not list a `to` field; the Instantly MCP/CLI tool schema does, and documents it as "Expected recipient email - validates against the thread before sending (recommended)", with `skip_validation` to turn it off. Both were read on 2026-09-21. They may simply be a wrapper-level convenience, or the reference may be incomplete.

Because a reply delivered to the wrong person is the most expensive write in this system, `shared/instantly.py` does **both** and neither is optional:

1. it **requires** `to=<lead email>` and puts it in the body (omitting it raises `InstantlyError` before anything is guarded or sent; `skip_validation=True` is the deliberate opt-out), and
2. in live, `services/reply_engine/cadence.py` **re-reads the email by id and refuses the send** unless `from_address_email` is the lead (`thread_recipient_ok`, reason `recipient_mismatch`).

**Do not delete either one.** An earlier version of this paragraph told the next engineer to remove the `to` guard; following it would make every send raise. The open question is only whether the REST endpoint *uses* `to` or ignores it, and the reply endpoint is not documented as `additionalProperties: false`, so sending it is safe either way. Settle it with the single live-send rehearsal in `runbooks/GO_LIVE_CHECKLIST.md` Stage 4.1 (reply to a thread of Lorenzo's own, watch the response), then delete whichever half turns out to be dead. Until then keep both.

Returns 200 with the full Email object.

## POST /leads/update-interest-status
```json
{"lead_email": "sopio@example.com", "interest_value": 2, "campaign_id": "<uuid>",
 "ai_interest_value": 1, "disable_auto_interest": false, "list_id": "<uuid>"}
```
Required: `lead_email`, `interest_value`. The optional key is `campaign_id`, not `campaign`. There is no `lead_id` and no `interest_status`.

Returns **202** `{"message": "Lead interest status update background job submitted"}`, not 200. Treat 202 as success. A bad address returns 400 `{"error": "Invalid lead email"}`.

`interest_value` (also the `lt_interest_status` enum): `0` out of office, `1` interested, `2` meeting booked, `3` meeting completed, `4` won, `-1` not interested, `-2` wrong person, `-3` lost, `-4` no show. `null` resets the lead to plain "Lead". Custom lead labels use their own value in the range -30000..30000.

## POST /block-lists-entries
```json
{"bl_value": "ron.daniels@siteforce.us"}
```
`bl_value` (an email or a domain) is the only accepted property; `additionalProperties: false`, so any extra key is a 400. Note the path spelling: hyphenated, plural "lists", plural "entries".

## POST /leads/subsequence/move
```json
{"id": "<lead uuid>", "subsequence_id": "<subsequence uuid>"}
```
**One lead per call.** There is no `ids` array on this endpoint. Returns the full Lead object. `shared.instantly.move_to_subsequence(lead_id, subsequence_id)` sends exactly this; `move_leads_to_subsequence(lead_ids, ...)` loops it.

## POST /subsequences — create a subsequence
Required: `parent_campaign` (uuid), `name`, `conditions`.
```json
{"parent_campaign": "<uuid>", "name": "Interested - quiet",
 "conditions": {"crm_status": [1], "lead_activity": [], "reply_contains": ""},
 "subsequence_schedule": {"start_date": null, "end_date": null,
   "schedules": [{"name": "Business hours", "timing": {"from": "10:00", "to": "12:00"},
                  "days": {"0": false, "1": true, "2": true, "3": true, "4": true, "5": true, "6": false},
                  "timezone": "America/Chicago"}]},
 "sequences": [{"steps": [{"type": "email", "delay": 2, "delay_unit": "days",
                           "pre_delay": 1, "pre_delay_unit": "days",
                           "variants": [{"subject": "", "body": "<div>...</div>"}]}]}],
 "daily_limit_mode": "inherit"}
```
- `conditions.crm_status` takes the interest values above. `lead_activity` is an enum of exactly `2` (email opened), `4` (link clicked), `91` (campaign completed without reply).
- `timing.from`/`to` must match `^([01][0-9]|2[0-3]):([0-5][0-9])$`; `days` is keyed `"0"`–`"6"`; `timezone` is an IANA name.
- Only the **first** element of `sequences` is used. `delay` is the wait before the NEXT email. `pre_delay` is the wait before the FIRST email and works **only in subsequences** (it is ignored on campaigns), which is how a subsequence starts on day 1 rather than immediately.
- Each step needs at least one variant that is not disabled; `subject: ""` keeps the message in the same thread.
- Omitting `subsequence_schedule` inherits the parent campaign's schedule.

## POST /webhooks
```json
{"target_hook_url": "https://<app>.modal.run/webhooks/instantly", "event_type": "reply_received",
 "campaign": "<uuid or null>", "name": "Reply received", "custom_interest_value": null,
 "headers": {"X-Advero-Secret": "<secret>"}}
```
Only `target_hook_url` is required (must match `^https?://`). Custom `headers` are a flat string-to-string object sent with every delivery; the reference documents no count or size cap, so do not assume one. `event_type` enum: `all_events`, `email_sent`, `email_opened`, `email_link_clicked`, `reply_received`, `email_bounced`, `lead_unsubscribed`, `campaign_completed`, `account_error`, `lead_neutral`, `lead_interested`, `lead_not_interested`, `lead_meeting_booked`, `lead_meeting_completed`, `lead_closed`, `lead_out_of_office`, `lead_wrong_person`, `lead_no_show`, `supersearch_enrichment_completed`. Custom-label events use `event_type: null` plus `custom_interest_value`. A webhook whose deliveries keep failing is disabled by Instantly and reports `status: -1`.

## DELETE /webhooks/{id} — UNVERIFIED
Not read off the reference and never exercised against Instantly. `shared.instantly.webhooks_delete` sends it with no body and no Content-Type, and `changesets/instantly_webhooks.py --rollback` sends no DELETE at all until `DELETE_WEBHOOK_VERIFIED` is set after the live rehearsal. Until then a webhook is removed by hand in Instantly > Settings > Webhooks. Its key scope is unverified too.

## POST /accounts/{email}/pause
Path parameter only, URL-encoded. **No request body at all.** Returns the Account object; a paused account reports `status: 2`. Resume is the matching `/resume`. A separate bulk endpoint pauses up to 100 accounts and returns `paused_emails` / `failed_emails`.

## PATCH /campaigns/{id}
`minProperties: 1` (an empty body is rejected) and `additionalProperties: false`. Patchable fields relevant to us: `name`, `pl_value`, `campaign_schedule`, `sequences`, `email_gap`, `random_wait_max`, `text_only`, `first_email_text_only`, `email_list`, `daily_limit`, `stop_on_reply`, `link_tracking`, `open_tracking`, `stop_on_auto_reply`, `daily_max_leads`, `prioritize_new_leads`, `auto_variant_select`, `match_lead_esp`, `stop_for_company`, `insert_unsubscribe_header`, `allow_risky_contacts`, `disable_bounce_protect`, `cc_list`, `bcc_list`, `owned_by`, `provider_routing_rules`, `limit_emails_per_company_override`.

**`status` is read-only and cannot be patched.** Starting or pausing a campaign uses the dedicated activate and pause endpoints. In `sequences`, only the first element is used; each step needs `type` (only `email`), `delay`, and `variants` (1 to 26, each with `subject` and `body`, optional `v_disabled`).

## Campaign step delay semantics
`delay` is the wait **before the next** email, confirmed by the subsequence schema wording and consistent with the live campaigns, whose two steps both carry `delay: 3` for a day 0 / day 3 sequence. So a three-step sequence that should land on day 0, day 3 and day 7 carries `delay: 3` on step 1 and `delay: 4` on step 2. Verify on the Instantly timeline preview after the first apply.

---

# Read endpoints measured read-only on 2026-09-22

Everything below was verified against the live workspace with GET / read-shaped
POST calls only. These are the traps that cost a debugging pass each; a code
comment that disagrees with this section is wrong.

## GET /accounts/analytics/daily

Returns a **bare JSON array**, not `{items: [...]}`. Row shape:

```json
{"date": "2026-09-19", "email_account": "lorenzo@myadvero.com", "sent": 25, "bounced": 0,
 "contacted": 25, "new_leads_contacted": 25, "opened": 0, "unique_opened": 0,
 "replies": 0, "unique_replies": 0, "replies_automatic": 7, "unique_replies_automatic": 7,
 "clicks": 0, "unique_clicks": 0}
```

**`replies` and `replies_automatic` are DISJOINT counters, and `replies` is
already the human-reply count.** Do not compute real replies as
`replies - replies_automatic`. On 2026-09-19 the twelve active inboxes recorded
`replies=0` with `replies_automatic=7`, so the subtraction returns -7 and sinks
every inbox below the Section 6 1% line; over the week of Sept 14 the same
subtraction reports 2 real replies instead of 17. Use `unique_replies / sent`
for the per-lead rule, and read `replies_automatic` as the level-4
auto-responder signal it is. Pinned by
`shared/thresholds.py::REPLIES_INCLUDE_AUTOMATIC` (False) and by
`jobs/tests/test_retro.py::test_replies_automatic_is_not_a_subset_so_it_is_never_subtracted`.

It accepted **45 emails over a 28-day range in one call** (repeated `?emails=`
parameters). It 413s only with **no** emails filter at all, so the 413 is about
the unfiltered call, not the list length. `shared/analytics.py` chunks anyway:
the failure mode is a whole silent report, and a slow read beats a missing one.

## GET /campaigns/analytics

`reply_count_unique` **already excludes automatic replies.** The natural reading
of Blueprint M1 level 3 is "unique minus automatic", and that is negative on
four of six campaigns (bookkeeping_reactivation 1 and 4, bookkeeping_trigger 1
and 6). The two are disjoint buckets that sum to the replied-lead count on all
six.

With `start_date` / `end_date` it returns **LIFETIME** totals for a campaign that
was active in the range, and an empty list for one that was not. It is a
**presence filter, not a window filter**, and cannot produce a week-over-week or
day-over-day delta. Use `campaigns/analytics/daily` and
`accounts/analytics/daily` for anything windowed.

## GET /campaigns/analytics/steps

A list of `{step, variant, sent, opened, unique_opened, replies, unique_replies,
replies_automatic, unique_replies_automatic, clicks, unique_clicks}` with `step`
and `variant` as zero-based **strings**, and a leading totals row carrying
`step: null`. Five campaigns answer a real JSON null there;
recruiting_reactivation answers the literal string `"null"`, so an
`is not None` filter lets it through. `shared.instantly.campaign_step_analytics`
is the read; `services.experiments.analytics.is_totals_row` handles both shapes.

## POST /leads/list — the filter trap

**An unrecognised `filter` value is SILENTLY IGNORED and the call returns the
unfiltered list.** Measured 2026-09-21 against the live workspace:
`{"limit":100,"filter":"TOTAL_NONSENSE_XYZ"}` returned all 4,918 leads,
byte-identical to no filter at all, while `{"filter":"FILTER_VAL_BOUNCED"}`
correctly returned 20. `FILTER_VAL_LEAD_INTERESTED` (not a real value) returned
exactly what `FILTER_VAL_CONTACTED` returned.

A typo in a filter name does not raise; it changes what the call *means*.
Anything that pulls a subset by filter and then acts on it as that subset (a
bounce sweep, an unsubscribe reconciliation, a suppression build) acts on the
whole workspace instead. Validate the name against a verified allow-list first:
`services/experiments/analytics.py::LEAD_FILTERS` holds one.
`services/list_factory/suppression.py` sidesteps it by reading statuses off an
unfiltered full pull, where a wrong value can only over-suppress.

## GET /block-lists-entries

```json
{"items": [{"id": "...", "timestamp_created": "...", "organization_id": "...",
            "bl_value": "someone@example.com", "is_domain": false}],
 "next_starting_after": null}
```

`is_domain` is the flag that says whether `bl_value` is a single address or a
whole domain, and the suppression builder depends on it. Two entries live on
2026-09-22. Read via `shared.instantly.blocklist_list()` or
`iterate("block-lists-entries")`.

## POST /accounts/test/vitals

A POST that only reads, so it belongs on `shared.instantly.READ_POST_PATHS` and
gets the 429/502/503/504 retry. Answers `{status, success_list[],
failure_list[]}` grouped **BY DOMAIN**, not by account: three inboxes on one
domain produce one row carrying `domain, mx, spf, dkim, dmarc, allPass`. A
failure is therefore a DNS fault for every inbox on that domain, and pausing one
of them fixes nothing.

## Inbox placement

`GET /inbox-placement-tests` lists existing tests (**zero on this workspace**:
no placement test has ever run). `POST /inbox-placement-analytics/stats-by-test-id`
is the per-ESP inbox/spam/missing breakdown and is another read-shaped POST.
`POST /inbox-placement-tests` **creates** a test and **spends credits**, so it is
a guarded write (`shared.instantly.inbox_placement_create`) and every test this
repo produces is staged as a change-set rather than fired by the job.

No read-only endpoint was found that lists Instantly's seed addresses:
`GET /inbox-placement-tests/esp-options` and two other guesses all answered HTTP
400. Until one is found, the seeds come from starting one test by hand in the UI
and copying them.

## POST /leads — create a lead

Referenced by brief A6 and absent from the reference sections above.
**One lead per call**, so a 3,300-lead upload is 3,300 calls and has to respect
the 100 req/s and 6,000 req/min workspace budget.

```json
{"campaign": "<uuid>", "email": "owner@example.com", "first_name": "...", "last_name": "...",
 "company_name": "...", "website": "...", "personalization": "...",
 "custom_variables": {"buildingType": "...", "metro": "...", "icebreaker_style": "researched"},
 "skip_if_in_workspace": true, "verify_leads_on_import": true}
```

`shared.instantly.create_lead(...)` sends exactly this and defaults both booleans
to true: `skip_if_in_workspace` stops the list factory re-importing a lead who is
already being mailed, and `verify_leads_on_import` lets Instantly drop an address
the local verifier passed.

## GET /audit-logs

A pure read (`shared.instantly.audit_logs_list`). It is what the Friday retro's
"system changes" section wants; without it that section degrades to the git log
alone and a Claude session has to stage the entries by hand through the MCP.

## GET /lead-labels

Response shape **to be confirmed on the first live read**: the code
(`shared.instantly.lead_labels_list`, `iterate("lead-labels")` in
`changesets/instantly_phase0/apply_instantly_phase0.py`) assumes the usual
`{items: [...], next_starting_after}` page, and nothing here has checked it.

## Custom lead labels and the status ladder

`config/ids.json` records that custom lead labels carry their own interest value
in the range -30000..30000. Any code that counts positives with an unbounded
`status >= 1` ladder therefore counts **the first custom label anyone creates**
as interested, booked, held AND closed at once. Count against the known code set,
not a `>=` comparison. The blueprint plans those labels, so this is a live trap,
not a hypothetical one.

## Lead lists, leads/move and background jobs (read off developer.instantly.ai 2026-09-25)

Used by `changesets/deliverability_2026_09_25/`. Schemas read from the reference; the live responses were not yet seen when this was written.

- `POST /lead-lists` body `{name}` (required; `has_enrichment_task`, `owned_by` optional; `additionalProperties: false`). Returns the LeadList: `id`, `organization_id`, `name`, `timestamp_created`, `has_enrichment_task`, `owned_by`.
- `GET /lead-lists?search=&limit=&starting_after=` returns `{items, next_starting_after}`. `search` is a substring match; compare `name` exactly.
- `POST /leads/move`: source `campaign` or `list_id` (one is required when `ids` is given), `ids` (lead uuids; the change-set sends at most 100 per call), destination `to_campaign_id` or `to_list_id`, `copy_leads` (false = move). Returns a BackgroundJob, not the leads. A second move while one runs has been seen to answer 409 (not in the published schema): wait and retry, one job at a time. A rejected call can still have moved some leads: re-read before retrying.
- `GET /background-jobs/{id}` returns `{id, workspace_id, user_id, type ("move-leads"), entity_id, entity_type, data, progress (0-100), status, created_at, updated_at}`; `status` is one of `pending`, `in-progress`, `success`, `failed`, `draining`, `paused`, `cancelled`. `data.moved_lead_emails` is capped at 10,000.
- Lead objects carry `campaign` and `list_id` (both uuid or null): after a move to a list, `campaign` should be null and `list_id` the destination. `esp_code`: 0 in queue, 1 Google, 2 Microsoft, 3 Zoho, 8 AirMail, 9 Yahoo, 10 Yandex, 12 Web.de, 13 Libero.it, 999 other, 1000 not found. `status`: 1 active, 2 paused, 3 completed, -1 bounced, -2 unsubscribed, -3 skipped.
- `POST /leads/list` also takes `list_id`, `in_list`, `in_campaign` and `ids`. The `campaign` filter has been seen ignored, so anything selected from it is re-filtered client-side on each lead's `campaign`.
