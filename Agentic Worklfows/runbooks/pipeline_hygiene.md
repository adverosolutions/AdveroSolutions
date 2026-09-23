# Runbook: pipeline hygiene (S8): nightly sync + morning sweep

## Purpose
GHL "Sales" is the single source of truth for where a lead stands; Instantly must mirror it so cold sequences stop for booked and closed leads and the Instantly analytics stay honest. Two jobs:

- `services/reply_engine/pipeline_sync.py` (06:00 CT): GHL stage -> Instantly interest status, plus the reverse check (positive Instantly leads with no GHL opportunity) and value fixes (open opportunities with no monetary value).
- `jobs/pipeline_sweep.py` (07:30 CT): one list, ordered by money, of what is waiting on Lorenzo: booked calls inside 24 h without a confirmed flag, positive replies he has not answered, proposals untouched for 7 days, Upwork rooms awaiting him.

Both are read-only against every live system in shadow. The sync's writes go through `shared.instantly.Instantly.update_interest_status` and `shared.ghl.GHL.upsert_contact / upsert_opportunity / create_note`, each of which calls `guard_write` first; the sweep has no write path at all.

## Stage map and values
| GHL Sales stage | Instantly interest | Note |
| --- | --- | --- |
| New Reply/Lead | 1 interested | |
| Call Booked | 2 meeting booked | |
| Proposal Sent | 3 meeting completed | |
| Won | 4 closed | written with `status: won`, and with no guessed monetary value: a closed deal must carry its real contract value, not a pipeline default |
| Lost | -1 not interested | **-4 no_show** when the lost reason contains "no show", "no-show" or "ghost"; **-2 wrong person** when it names the wrong person / "no longer with" (name the GHL lost reasons that way). -4 is the code `config/ids.json` defines for no_show, so Instantly's own no-show reporting and any no-show recovery segment finally see them |
| Follow Up Later | -1 not interested | the same value `models.INTEREST_FOR_LABEL["negative_notnow"]` sets when the router classifies a "not now", plus a GHL note saying the mirror happened. The two tables must agree or the nightly sync relabels every dated not-now lead Interested |

**Negative values are sticky.** The mirror never turns a negative Instantly value back into a positive one unless GHL shows real progress (Call Booked, Proposal Sent, Won) **and GHL moved after the negative was set**, and never replaces one negative code with another unless the GHL lost reason named it (wrong person, no show). Without this, the sync undoes the router's own classification the night after it is made. See `pipeline_sync.mirror_allowed`.

The staleness half matters because nothing moves an opportunity out of Call Booked after the call (`no_show.py` says so explicitly). So a lead Lorenzo marks **No Show (-4)** or **Not Interested (-1)** tonight sits against a Call Booked stage that last moved weeks ago: the mirror used to read that old positive stage as a re-open, write 2 over the -4, and agree with itself the next night, so the negative was gone permanently with no alert. `mirror_allowed` now compares the opportunity's `lastStageChangeAt`/`updatedAt` against the lead's newest Instantly activity timestamp (`timestamp_updated`, `timestamp_last_interest_change`, `timestamp_last_reply`, `timestamp_last_contact`). When GHL is not demonstrably newer, the row is skipped and printed as a `conflict:` line for Lorenzo instead of overwritten. When either side carries no timestamp there is nothing to compare and the re-open is allowed, which is the old behaviour.

**One opportunity per contact.** When a contact has more than one Sales opportunity, the mirror uses the one furthest along (`pipeline_sync.STAGE_PROGRESS`: lost < follow up later < new reply < call booked < proposal sent < won) and logs the ones it ignored. GHL's `/opportunities/search` does not guarantee an order, so first-wins used to flip a lead with a call on the calendar to "lost" on whichever night the old opportunity came back first.

Explicit negatives in Instantly (-1 not interested, -2 wrong person, -3 lost, set by Lorenzo or the router) override the AI interest guess in the sweep. **-4 no_show does not**: it is a meeting-attendance state, not a statement of interest, so a no-show who writes back to reschedule still reaches the sweep. A lead already marked -1/-2/-3 whose new reply reads positive is surfaced too, flagged "previously marked ...": Instantly stamps the lead's current status on every email row, so the status says nothing about whether it was set before or after that reply.

Opportunity value defaults (`pipeline_sync.OPPORTUNITY_VALUE_DEFAULTS`, applied on upsert when GHL has none): reactivation offers $6,000 (20-30% of first-year fees on a 60-100 contact list, see the comment in the code), outbound/trigger offers $7,500 (two months of the $2,500-5,000/mo retainer midpoint). The offer type comes from the lead's campaign in `config/ids.json`; unknown campaign -> reactivation (the lower value).

## How to run (shadow)
From `Agentic Worklfows/`:

```bash
# sync: compute and print, apply nothing (read-only reads only)
python3 -m services.reply_engine.pipeline_sync --dry-run
# sync: apply through the guarded clients. In shadow every write is a would_do record in .tmp/shadow_log.jsonl
python3 -m services.reply_engine.pipeline_sync --now
# offline replay on the recorded September leads
python3 -m services.reply_engine.pipeline_sync --dry-run --fixtures --json

# sweep: pull (read-only), print the ordered list, Job_Log row; --now also sends the ntfy digest
python3 jobs/pipeline_sweep.py --dry-run
python3 jobs/pipeline_sweep.py --now
python3 jobs/pipeline_sweep.py --dry-run --fixtures --as-of 2026-09-21T21:10:00-05:00
```

`--fixtures` is a replay of a recorded September snapshot and can never apply: `--now --fixtures` is rejected by the parser, and `run_sync(..., replay=True)` reports `Apply blocked: fixture_replay`.

While there is no GHL token (`GHL_PRIVATE_INTEGRATION_TOKEN` unset):
- the sync seeds opportunities from the `config/ids.json` snapshot (`ghl.opportunities_observed_*`) for reporting and prints `Apply blocked: ghl_unreadable`; `--now` applies nothing, not even in shadow, because a source of truth that cannot be read must not drive writes;
- the sweep's proposal check uses only `proposal:*` store keys and notes `ghl_token_missing`;
- the sweep's booked-call check uses `appointment:*` store keys, seeded from `config/ids.json` google_calendar.booked_this_week (future entries only) while the store is empty.

Evidence from the read-only live dry-run, re-run on 2026-09-22 00:50 CT after the second round of S8 review fixes:
```
Pipeline sync DRY RUN | mode=shadow | 3 GHL opps, 4 Instantly leads
note: ghl_token_missing
Interest-status changes (1):  ilmi@shiningarmorcleaningnj.com [8086b41e] 1 -> 2 (ghl_stage:call_booked)
Missing GHL opportunities (1): ignacio@ariacleaningservices.com -> new_reply, $7500 (outbound)
Opportunities without a value (3): Sopio $6000, Ilmi $6000, Tiffany $7500
Apply blocked: ghl_unreadable (report only; mint the GHL token to let the sync act)

Pipeline sweep Tue Sep 22 12:50 AM CT: 1 item(s)
1. POSITIVE Sopio Svanishvili (Taxfo Accounting) [bookkeeping_reactivation], awaiting reply, 6 h: Hello Lorenzo. I am available every day 3pm-6pm Estern time. ...
note: booked calls include the config/ids.json calendar seed
```
Instantly's `POST /leads/list` accepted the four positive filters (`FILTER_LEAD_INTERESTED`, `_MEETING_BOOKED`, `_MEETING_COMPLETED`, `_CLOSED`), so the nightly pull is 24 small calls, not a full page-through of every campaign. The sweep's email pull took 2 `GET /emails` pages per type (4 calls) to cover the 14-day window and stopped because the cursor was exhausted, not because a row count said so: it filters rows against the cutoff and stops only when the cursor is gone or a whole page is older, instead of breaking at the first old row.

Also checked read-only on 2026-09-21 against `GET /emails?email_type=manual`: 145 rows, all 145 carrying `ue_type` (3 outbound / 2 inbound) and `from_address_email` (the outbound ones sent from the campaign inbox). `is_outbound` reads `ue_type` first, then the sender, then the recipients; the recorded fixture has neither field, so only the recipient fallback is covered offline.

## Store contracts the sweep reads (written by the booking / show-rate / proposal briefs)
| Key | Value | Used for |
| --- | --- | --- |
| `appointment:<id>` | `{"lead_email", "name", "company", "start" (ISO), "confirmed" (bool), "campaign_id", "value", "appointment_id"}` | booked calls inside 24 h that are not confirmed |
| `confirmed:<appointment_id>` | `{"at", "source", "start_iso"}`, written by `show_rate.mark_confirmed` | the lead's "C" reply. **This is where a confirmation actually lives:** `booking.appointment_payload` hard-codes `"confirmed": False` into the appointment row and never patches it, so the sweep reads this key through `show_rate.is_confirmed` (which also drops a confirmation that was for a start the lead has since rescheduled away from) |
| `proposal:<id>` | `{"lead_email", "name", "company", "sent_at" (ISO), "last_touch" (ISO), "opportunity_id", "value"}` | proposals with no touch for 7 days |
| `opptouch:<opportunity_id>` | ISO timestamp of the last touch | resets the 7-day clock for a GHL proposal. **Not `touch:`** - `cadence.py` owns that namespace (`touch:<campaign_id>:<lead_email>:<n>:<kind>`, values are dicts), so the old prefix only ever matched cadence rows and the signal was dead. Nothing writes `opptouch:` yet, so the clock currently falls through to `last_touch`/`updatedAt`/`sent_at`; the proposal brief is the writer |
| `.tmp/upwork_rooms.json` | `{"rooms": [{"room_id", "client", "awaiting": "lorenzo" or true, "last_message_at", "last"}]}` | Upwork rooms awaiting Lorenzo; written by a Claude session that has the Upwork MCP (not available inside jobs) |

## How to test
```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows" && python3 -m pytest services/reply_engine/tests/test_sync_diff.py services/reply_engine/tests/test_sync_apply.py services/reply_engine/tests/test_sync_modal_app.py jobs/tests/test_pipeline_sweep.py -q
```
111 tests.

Sync: stage map and lost-reason rules; `compute_diff` emits only changes, one row per campaign, case-insensitive; a stale positive stage does not overwrite a fresher negative and is reported as a `conflict` instead, while a GHL move made after the negative still re-opens the lead; reverse check and value fixes on the recorded leads; an opportunity with no contact email is counted and blocks the reverse check; `apply` in shadow makes zero HTTP requests and returns `would_do` records that land in the shadow log; `apply` in live mode (mocked transport) sends the exact `update-interest-status` and `opportunities/upsert` payloads; a failed GHL note does not rewrite the outcome of an interest update Instantly already accepted; GHL without token skips; row errors isolated; filtered lead pull with the 400 fallback, and a failed lead pull returns a note and blocks apply instead of reading as "no positive leads"; paging sends both halves of the cursor, refuses a page number as a cursor, settles "exactly one full page" by asking GHL, and hard-stops on a page that adds nothing; `run_sync` on fixtures, the no-token snapshot path with apply blocked, `error` status when every applied row failed, and the CLI.

Sweep: `httpx.MockTransport` serves `GET /emails` (received and manual) and `POST /leads/list` from the fixtures with the clock pinned to 2026-09-21T21:10-05:00; asserts Sopio (inbound Sept 21 23:17Z after Lorenzo's 18:30Z outbound) is flagged awaiting reply and Ilmi (19:03Z outbound after the 19:00Z inbound) is not; overdue after 24 h; booked/proposal/Upwork sources; ordering booked > positive > proposal > upwork; digest, Job_Log row, ntfy record with NOTIFY=off; dry-run does not notify; a CC'd second reply is still the lead's, not Lorenzo's; a lead marked lost who writes back is still surfaced; an out-of-order old row does not truncate the pull; the 9-page cap is reported on the fact that stopped the walk, so smaller pages still raise it and nine complete pages ending cleanly do not; a failed Instantly pull is a `partial` row with a high-priority push, never a clean zero; a call the lead confirmed with a "C" reply leaves the list, and a reschedule puts it back; a malformed `value` is a note, not the end of the run; a positive reply with no `thread_id` is still reported; an auto-responder the AI labelled interested is not a positive, and no recorded September auto-reply reaches the digest; two replies in the same second show the later one; the ids.json calendar seed merges with store appointments instead of being replaced, and the same call in both sources is listed once across time zones; booked lines read "11:30 AM CT"; the push carries no prospect address, company or wording, including when the lead record is missing or the appointment has no name.

modal_app: import smoke test, every cron string is five fields and CT-native, a TypeError inside an entrypoint is not retried, a missing entrypoint logs `entrypoint_missing`, a crashing `pipeline_sync`/`pipeline_sweep` body writes an `error` row and re-raises, and `NOTIFY_SHADOW_SEND` is in `SECRET_KEYS` and is what makes the shadow push actually leave the process.

## How to go live (checklist)
1. `pytest` green (this file's command plus `shared/tests`).
2. Mint the GHL Private Integration token (contacts, opportunities, calendars, calendars/events, conversations scopes), put it in `Agentic Worklfows/.env` and the Modal secret; rerun `pipeline_sync --dry-run` and confirm the diff matches what Lorenzo sees in GHL (the `Apply blocked` line disappears).
3. Name the GHL lost reasons so no-shows read "No show" / "Ghosted" and wrong-person losses read "Wrong person" / "No longer with": `desired_interest` keys **-4 (no show)** and **-2 (wrong person)** on that text. `INTEREST_LOST = -3` is dead in this module; the mirror writes -1, -2 and -4 only.
4. Run `pipeline_sync --now` in shadow for 3 nights; every `would_do` in `.tmp/shadow_log.jsonl` must be a change Lorenzo agrees with. Watch especially any `-> -1`, `-> -2` or `-> -4` row: those stop Instantly follow-ups and move a lead into (or out of) the no-show segment. Read the `conflict:` lines too: each one is a lead whose Instantly negative the mirror refused to overwrite with a stale GHL stage.
5. Confirm `pipeline_sweep --now` digests arrive on the phone at 07:30 CT for 3 mornings and that nothing positive sat unanswered past 24 h. The topic is `NTFY_TOPIC` in `.env`; `.tmp/ntfy_topic.txt` only exists when no env topic was ever set, so it is not where to look. On Modal the digest needs `NOTIFY_SHADOW_SEND=1` in the secret (runbooks/deployment.md step 2a), because in shadow a push is a guarded write like any other.
6. Only then: `MODE=live` + `ALLOW_LIVE_WRITES=1` (Modal secret, or the shell for a one-off) and run `pipeline_sync --now` once by hand; check the `live_write` rows in Job_Log and the Instantly lead statuses; then leave the 06:00 CT schedule on.

## Rollback
- Set `MODE=shadow` (or unset `ALLOW_LIVE_WRITES`) and redeploy: the sync goes back to `would_do` records; the sweep is unaffected (read-only).
- Every live change is a `live_write` Job_Log row with the payload (`lead_email`, `campaign_id`, `interest_value`, or the GHL upsert body); reverse by setting the previous `interest_value` with `Instantly().update_interest_status(...)` in a live shell, or by moving the opportunity back in GHL.
- Nothing here deletes anything.

## Thresholds
| Rule | Value | Where |
| --- | --- | --- |
| Positive reply unanswered | flag immediately, `overdue` at 24 h | `pipeline_sweep.REPLY_SLA_HOURS` |
| Booked call needs confirmed flag | inside 24 h of start | `pipeline_sweep.BOOKED_HORIZON_HOURS` |
| Proposal stale | 7 days without a touch | `pipeline_sweep.PROPOSAL_STALE_DAYS` |
| Upwork room overdue | 1 h | `find_upwork_awaiting` (M6 SLA) |
| Email lookback | 14 days, max 9 pages per type (18 `GET /emails` calls, inside the documented 20/min limit). Hitting the cap with the cursor still open is reported, never swallowed | `LOOKBACK_DAYS`, `MAX_EMAIL_PAGES`, `fetch_emails` |
| Digest privacy | the ntfy push carries first names and counts only; anything containing `@` becomes "a lead" | `render_digest(..., redact=True)`, `_first_name` |
| Booked call is confirmed | the row's own `confirmed`, or `show_rate.is_confirmed` reading `confirmed:<appointment_id>` for this start | `pipeline_sweep.is_confirmed` |
| Ordering | booked > positive > proposal > upwork, then value desc, then oldest wait / soonest start | `order_items` |
| Sync cadence | daily 06:00 CT; sweep 07:30 CT | `modal_app.SCHEDULES` |
| Digest priority | `high` when any booked call or overdue positive, else `default` | `run_sweep` |

## Known gaps
- GHL opportunity JSON is written from the LeadConnector docs (`opportunities`, `pipelineStageId`, `contact.email`, `monetaryValue`, `lostReason`) but unverified against a live token; the first token-backed `--dry-run` should be read line by line. In particular, an opportunity whose `contact` comes back **without an email** cannot be matched by the reverse check: `run_sync` counts those, notes `ghl_rows_without_email` and refuses to apply the reverse check at all, because the lead would otherwise get a second contact and a second opportunity in the source of truth.
- The reverse check creates opportunities in the stage implied by the Instantly value (1 new reply, 2 call booked, 3 proposal sent, 4 won); if Lorenzo prefers everything to land in New Reply, change `INTEREST_TO_STAGE`. An open question for Lorenzo sits here: Ignacio's recorded reply is a dated "not now", but Instantly's own auto-tagging left him at `lt_interest_status: 1`, so the reverse check proposes New Reply/Lead at $7,500 open pipeline. Nothing in the Instantly lead record says the router would have called it `negative_notnow`.
- **GHL paging is the real remaining defect, and it is now only half-open.** `shared.ghl.GHL.search_opportunities` does take `start_after_id` **and** `start_after` (shared/ghl.py), and `fetch_ghl_opportunities` now sends both halves of GHL's cursor, drops `nextPage` (a page number, never an id), probes with the last row's own id when the page meta carries no cursor, and hard-stops the moment a page adds no new ids instead of burning all 20 calls. What is still unverified is whether GHL's live `/opportunities/search` meta actually carries `startAfterId`/`startAfter` at all: until a token-backed run shows it, a Sales pipeline past 100 opportunities may still come back `ghl_truncated`, which blocks apply on purpose rather than letting the reverse check create duplicates.
- `config/ids.json` `google_calendar.booked_this_week` rows **do** carry `email`, so seeded appointments de-duplicate against the store on (email, start) first, with (start, person) as the fallback. Both sides normalise the start to UTC and strip the "/ company" suffix off the name before comparing, because the seed writes "Ilmi Curovic / Shining Armor Cleaning NJ" at `-05:00` while the booking engine writes "Ilmi Curovic" at `+00:00`.
- Nothing writes `proposal:*` or `opptouch:*` yet, so branch (c) of the sweep yields zero rows from the store until the proposal brief lands and the GHL token exists.
- The recorded manual-email fixture omits `from_address_email` and `ue_type` on every row, so the fixture-driven direction tests only exercise the recipient fallback. Live carries both (verified read-only 2026-09-21: 145 manual rows, 145 with a sender, ue_type 3 outbound / 2 inbound), so the branch the engine actually depends on is covered only by hand-built rows. See the cross-cutting request to re-record it.
- Cron strings in `modal_app.py` are five-field and read in `America/Chicago` (`modal_app.SCHEDULE_TZ`), so the 06:00/07:30 CT jobs no longer drift when CDT ends on Nov 1, 2026.
