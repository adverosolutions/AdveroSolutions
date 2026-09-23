# Runbook: pre-call brief and proposal generator (Blueprint S6, S7; brief A11)

Files: `services/reply_engine/precall.py`, `services/reply_engine/proposal.py`, `jobs/precall_tick.py`,
`services/reply_engine/prompts/precall_*.md`, `services/reply_engine/prompts/proposal_*.md`,
`changesets/ghl_workflows/proposal_follow_up.md`, tests in `services/reply_engine/tests/test_precall_*.py`.

## Purpose

Two jobs, one tick.

1. **Sixty minutes before every booked call**, Lorenzo gets a brief: company facts with their sources, the campaign and the whole reply thread, the offer for that niche with its guarantee numbers, the figures he must not say out loud, the objections this particular lead is most likely to raise, and the one-call-close skeleton. It arrives as an ntfy card, as a note on the GHL contact once a token exists, and as a file under `.tmp/precall/`.
2. **Same day as the call**, the proposal is drafted from the offer sheet plus whatever record of the call exists, with the SOP-009 verbal-commit emails under it. It is filed under `.tmp/proposals/` and announced. **Nothing is ever sent.** Lorenzo reads it, edits it, pastes the client-facing half into GHL Documents or PandaDoc, and sends it himself.

The proposal resolves its offer the same way the brief does (`precall.resolve_offer`: the booking's campaign id, then the Instantly lead record's `campaign`, then tags, then the company name), so the two documents for one call can never quote two different offers' pricing, deposit terms and proof point. When the niche still cannot be matched, the proposal carries a `BLOCKED` line saying so rather than silently shipping the `cleaning_reactivation` default.

Neither half can reach a prospect. The only outbound calls in the whole path are `ghl.create_note` and `notify`, and both go through `shared.settings.guard_write`.

## How it works

| Thing | Where the state lives | Key |
| --- | --- | --- |
| "this call has been briefed" | store | `precall:<appointment id>:<start ISO>` |
| "this call's proposal has been drafted" | store | `proposal:<appointment id>:<call date>` |
| whether the call was actually held | store, written by `no_show.process` | `noshow_state:<appointment id>` |
| the brief itself | `.tmp/precall/<start>_<company>_<id>.md` | |
| the proposal draft | `.tmp/proposals/<call date>_<company>_<id>.md` | |
| a forced re-draft (`--proposal-for`) | `.tmp/proposals/<call date>_<company>_<id>_forced.md` | |

Both claims are taken with `store.set_if_absent`. The brief key carries the start time, so a reschedule earns a fresh brief.

Three rules are worth knowing because each of them was wrong once:

1. **The proposal claim is checked by the caller, before anything is built.** `jobs/precall_tick.tick` calls `proposal.already_drafted` before `gather_inputs` and `build_proposal`, exactly as the brief pass calls `precall.already_briefed`. Taking the claim inside `deliver()` meant the 5-minute tick paid for a `claude-opus-5` proposal on every pass of the whole proposal window. Measured: a call at 11:30 leaves the window open for 146 ticks, which was 146 model calls and 292 redundant `GET /emails` for one delivered proposal.
2. **The proposal claim carries the call's own date, not the clock's.** `proposal_due` keeps the window open past midnight for an evening call, so `now.date()` gave a 22:30 call two claims, two files, two pushes and a second document dated the wrong day for the client. `proposal.call_date_for` reads `start_iso` in Central.
3. **The brief claim is released when every delivery leg fails.** `shared.notify.notify` never raises; it returns `{"sent": False, "errors": [...]}`. Keeping the claim on a failed push meant the next tick skipped the brief and Lorenzo walked into the call with nothing, with no warning, because the digest goes out over the same ntfy leg. A brief is internal, so at-least-once beats at-most-once here. Prospect-facing touches (S4, S5) still claim before they send, on purpose. The file on disk does **not** count as a delivery leg.

### Where the appointments come from

`jobs/precall_tick.load_appointments` reads two sources:

- the GHL Discovery Call calendar, through `jobs.appointments_tick.fetch_appointments` (the same read S4 and S5 use), and
- the hand-made calls on Lorenzo's own Google Calendar, from `config/ids.json` `google_calendar.booked_this_week`.

The second source is **included here and excluded from the show-rate ladder on purpose**. S4 would email a prospect who already agreed the time with Lorenzo directly; a brief is internal and nobody but Lorenzo reads it. Today both real calls on the books are of that kind, so leaving them out would mean this job covers zero live calls.

When a call appears in both sources the GHL row wins and the manual copy is dropped. De-duplication is on **`(lead email, start time to the minute)` as well as id**: the manual row's id is the Google Calendar event id and the GHL row's is GHL's own appointment id, so the two id spaces can never collide and an id-only check dropped nothing. Once the GHL token is minted, a call present in both would otherwise get two briefs, two ntfy cards, two notes on one contact and two proposal drafts. The digest reports how many manual rows were dropped this way.

`booked_this_week` also carries `response_status`. `accepted` is briefed silently; anything else (`needsAction`, which is the live Taxfo row) is briefed **with a warning at the top**; `declined` and `cancelled` are not briefed and get no proposal.

### Where the facts come from

| Fact | Source | Cost |
| --- | --- | --- |
| company name, size, website, city, industry, description, founded, title, LinkedIn | `Coding/lead-scrape-2026/output/verified/CLEAN_all.csv` (override with `LEAD_FACTS_CSV`) | free, local file |
| the opener we already sent them, reply count, first contact, last reply, which inbox owns the thread | Instantly lead record, `POST /leads/list` | free, read-only |
| the whole thread, both directions | Instantly `GET /emails?lead=<email>` | free, read-only |
| reviews, Google Maps footprint | **not pulled** | a Google Maps actor run on Apify. Not run, not budgeted, and the brief says so in writing rather than leaving a blank |

Nothing is inferred. Every fact line carries the source it came from, and a value with no source is not printed.

## How to run (shadow)

```bash
cd "Agentic Worklfows"

# what is due right now. --dry-run sets LLM_FAKE=1 itself; the prefix below is belt and braces
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 -m jobs.precall_tick --dry-run

# a specific moment: 55 minutes before the live cleaning call
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 -m jobs.precall_tick --dry-run --now 2026-09-23T10:35:00-05:00

# after that call, draft the proposal
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 -m jobs.precall_tick --dry-run --now 2026-09-23T12:00:00-05:00

# force a proposal for one call, with a transcript Lorenzo pasted into a file.
# This REPLACES the thread-based proposal the scheduled tick already drafted that
# day (the claim is overwritten and a second file is written alongside the first,
# named ..._forced.md). Before, the better transcript proposal was built and then
# silently dropped, and the digest reported it as filed.
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 -m jobs.precall_tick --dry-run \
  --proposal-for eqlug7qn67rnjdppja91ffuto0 --transcript ~/Desktop/call.txt

# briefs only, no Instantly reads at all (offline)
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 -m jobs.precall_tick --dry-run --no-read --no-proposals
```

`--dry-run` forces `MODE=shadow`, `NOTIFY=off`, **`LLM_FAKE=1`**, scratch job and shadow logs, and a **scratch store**.

- The scratch store matters: the claim keys a brief writes are writes like any other, so a dry run against the production store would silently consume the claim and the real tick would then skip that brief as already delivered.
- `LLM_FAKE=1` matters just as much. `shared.settings.load_env()` puts the real `ANTHROPIC_API_KEY` into the process at import, so a dry run that only set `MODE=shadow` reached the real-client branch of `shared.llm.complete` once per due proposal, on `claude-opus-5`, while advertising that nothing was billed. `guard_write` never sees a model call, so shadow mode does not stop it. `--llm` is the explicit opt-in if you ever want a polished dry run.
- A dry run **does** still make read-only Instantly GETs (that is how the thread gets into the brief). `--no-read` turns them off; the brief then says "thread not read on this run (offline mode)", which is deliberately different wording from a real read failure.

The brief and proposal markdown files are still written under `.tmp/` on a dry run. They are intermediate files by the CLAUDE.md convention, and reading last night's dry-run brief is the point of them.

## How to test

```bash
cd "Agentic Worklfows" && python3 -m pytest services/reply_engine/tests/test_precall_brief.py \
  services/reply_engine/tests/test_precall_proposal.py services/reply_engine/tests/test_precall_tick.py -q
```

161 tests, all offline: the LLM is faked, Instantly and GHL are stand-ins, the store is a temp file. The tick tests live under `services/reply_engine/tests/` rather than `jobs/tests/` because brief A11 owns `test_precall_*.py` there and nothing under `jobs/tests/`.

## Gates that stay closed until told otherwise

| Gate | State today | Effect |
| --- | --- | --- |
| `MODE=shadow` | default | the GHL note is a `guard_write` record; nothing reaches GHL |
| `GHL_PRIVATE_INTEGRATION_TOKEN` | not minted | no calendar read, so only the manual calls are covered, and the note is recorded rather than written |
| `PAYMENT_LINK_URL` | unset | the SOP-009 "here is the link" draft keeps a visible `{payment_link}` placeholder and is marked unsendable. It is never silently sent with a missing link |
| `FIREFLIES_API_KEY` | does not exist | the proposal degrades to Lorenzo's notes, then to the reply thread, and says which one it used on the document |
| Zoom telemetry | not connected | `held_evidence` is `unknown` on every call, so each proposal carries "No Zoom telemetry: nothing proves this call happened" at the top |
| `LLM_FAKE=1` | set by `--dry-run` itself | the Opus polish pass never runs and nothing is billed. `--llm` is the only way past it |
| `NTFY_TOKEN` / `NTFY_ALLOW_SENSITIVE` | neither is set | ntfy.sh topics are world readable to anyone who knows the name, and `notify.redact()` strips only email addresses and URLs. Until one of these is set, the pre-call card withholds the **company name** and the **verbatim quote of their last email**, and says so. Both are in the file and in the GHL note. `NOTIFY_EMAIL` is unset too, so there is no email leg to carry the withheld detail either |

## Reading a brief

The card is short enough to act on from a phone and survives `notify.redact()` on an unprotected ntfy topic. The full brief is in the note and the file. Three sections are worth trusting more than the rest:

- **Do not say** lists every figure `config/offers.md` marks TO CONFIRM (today the $2,500 to $5,000 retainer range). Those numbers appear nowhere else in the brief: `precall.quotable_text()` strips that block and the remainder is checked against the same cross-offer validators a cold reply passes, for **all six offer keys**. The three trigger rows carry the guarantee and the retainer range in one offers.md cell, so `offer_block` replaces the TO CONFIRM figures in that cell with `[figure withheld, see Do not say]` and keeps the quotable guarantee ($24,000/yr, $15,000, $40,000) intact.
- **The offer for this call** and the filled SOP-007 skeleton are safe to read out loud verbatim. `{first_name}` and `{company}` are interpolated; the discovery placeholders (`{size}`, `{value}`, `{count}`, `{math}`) stay visible because they are genuinely unknown until Lorenzo asks.
- **Likely objections** is ranked by pattern specificity first, then recency, and every ranked item quotes the sentence it came from. When two patterns match one sentence the broader one is suppressed, so the brief can never show two blocks quoting the same sentence with contradictory advice. "standard on a first call" means the thread gave no signal and these are the defaults. `price_question` exists because a plain "What is your percentage?" matched nothing: `too_expensive` needs the word "expensive" and `cant_afford` needs "afford" or "budget".

## Failure modes and what they look like

| Symptom | Cause | What the job does |
| --- | --- | --- |
| "reply thread could not be read" in the brief | Instantly 5xx or a bad key | the brief ships without the thread and says so; objections fall back to the defaults |
| "thread not read on this run (offline mode)" | `--no-read`, or the Instantly client could not be built | deliberate offline wording, not a failure. When the client failed to build, the digest also carries a WARNING naming the error |
| a brief pushed 60 minutes before a time that no longer exists | `config/ids.json` `google_calendar.booked_this_week` is a **hand-maintained snapshot**, not a calendar read. Nothing in this job reads Google Calendar | **Update that file on every reschedule.** The tick cannot fix this; it does warn when an entry in the seed is already in the past ("N entry ... is already in the past"). Reading the calendar properly is a gap, see below |
| the invite "has not been accepted (response_status=needsAction)" | the prospect never accepted the hand-made calendar invite | briefed anyway, with the warning at the top. `declined` and `cancelled` are not briefed and get no proposal |
| the brief says "NOT DELIVERED: every push and note leg failed" | ntfy unreachable and no GHL token | the claim is released and the next 5-minute tick retries. The file is still on disk |
| "proposal skipped `<id>`: already_drafted" every 5 minutes | normal steady state for the rest of the call's day | nothing is built and nothing is billed; that is the whole point of the pre-check |
| `niche could not be determined` | the booking has no campaign, no niche tag and an unrecognisable company name | the brief uses the `cleaning_reactivation` default and says so at the top. **Check it before quoting anything** |
| every brief says "GHL token: missing" | no Private Integration token | only the manual calendar calls are covered; the note intent is still recorded in the shadow log |
| `BLOCKED` on a proposal | the draft carries a figure that is not in offers.md, is marked TO CONFIRM, or belongs to another offer, **or the niche could not be matched to a campaign** | the document is still filed, with the reason at the top. Do not send it |
| the proposal recap is "(Nothing on file from the call.)" | no transcript, no notes, or **the thread was nothing but booking chatter** | write two lines by hand. The generator will not invent them, and it will not fill the section with "works for me" and a phone number |
| a "Check: the recap quotes them verbatim and the quote contains ..." note | the prospect's own sentence carries a dollar figure, an exclamation mark, an em dash or the word "automated" | **not blocking.** Their words are not our copy, so `copy_problems` blanks the quoted spans before it validates. Read the quote once and send |
| a "check" line about the deposit | the blueprint says 50 percent and offers.md says $0 up front for reactivation | see the open question below |

## Known gaps, and who owns them

1. **GHL Documents and PandaDoc are a manual paste.** There is no create-document endpoint in `shared/ghl.py` and no PandaDoc account, so `proposal.deliver` reports `{"document": {"status": "manual"}}` rather than pretending. The draft file marks the boundary: everything above `=== CLIENT-FACING PROPOSAL STARTS HERE ===` is internal and must not be pasted, and `proposal.client_body(text)` returns exactly the part that may be. A2 or A12 owns adding a documents client if Lorenzo wants it automated.
2. **Three environment keys are not registered for deployment.** `LEAD_FACTS_CSV`, `PAYMENT_LINK_URL` and `FIREFLIES_API_KEY` are read by this code but appear in neither `modal_app.SECRET_KEYS` nor `ENV_NOT_IN_SECRET`, which `shared/tests/test_settings.py::test_every_env_key_is_deployable` fails on (along with thirteen keys from other briefs). `services/reply_engine/modal_app.py` is not this brief's file; the exact patch is in the cross-cutting requests. `PAYMENT_LINK_URL` is the one that matters: unset, every "immediate" verbal-commit draft is permanently unsendable with a visible `{payment_link}`, which is the safe direction but means the SOP-009 path can never be completed from a deployed container.
2a. **Nothing reads Google Calendar.** `precall.manual_calls` reads the `booked_this_week` snapshot in `config/ids.json`. The Ilmi call in that block has already been rescheduled once. If a call moves again and only the calendar is updated, this job briefs the old time and never briefs the new one. The tick warns when a seed entry is in the past, which is the most it can do without a calendar client. A real fix is a Google Calendar read (or an `.ics` export) and belongs to whoever owns the calendar integration.
3. **The tick is not on a schedule.** `jobs/precall_tick.py` has no entry in `services/reply_engine/modal_app.py`. It needs a 5-minute schedule next to `appointments_tick`, and `precall_tick.main` / `tick` is the entry point.
4. **`held_evidence` is always `unknown`** until Zoom is connected to GHL (A3's gap, not this one). Every proposal therefore carries the "confirm the call happened" line.
5. **No reviews and no Maps footprint** in the facts block. The only source is a paid Apify run.

## Go-live checklist (do not skip a line)

1. `python3 -m pytest services/reply_engine/tests/test_precall_*.py -q` is green.
2. Run `--dry-run --now <60 min before a real call>` and read the produced file end to end. Check the offer block against `config/offers.md` by eye once.
3. Mint the GHL Private Integration token, put it in `.env`, and re-run the dry run. The digest should say `GHL token: present` and the note intent should name the right contact id.
4. Set `PAYMENT_LINK_URL` to Lorenzo's real link. Re-run and confirm the `immediate` draft is no longer blocked.
4a. **Set `NTFY_TOKEN`** (an ntfy access token on the topic). Until it is set, the pre-call card withholds the company name and the quote of their last email, because the topic is world readable and there is no email leg configured to carry the detail. Re-run the dry run and confirm the card names the company again.
5. Schedule the tick every 5 minutes (gap 3 above).
6. Only then switch `MODE=live ALLOW_LIVE_WRITES=1`, and only for the note: the proposal never sends, whatever the mode.
7. Build the GHL workflow from `changesets/ghl_workflows/proposal_follow_up.md` in the existing draft `45f6c25f-e7d0-419b-898f-a9b0e6e1fa06`, test it against Lorenzo's own contact, then publish.

## Rollback

There is nothing to roll back on the prospect side, because nothing is sent. To stop the job: remove its schedule, or run it with `--no-proposals` for briefs only. To re-brief a call whose claim was consumed by a bad run, delete the `precall:<id>:<start>` key from the store.

## Costs

| Run | Cost |
| --- | --- |
| one brief | 2 Instantly GETs and one POST-shaped read, plus one local CSV scan. $0 |
| one proposal with `LLM_FAKE=1` (every command above, and every dry run) | $0 |
| one proposal with the Opus polish on | **measured**, not estimated: 7,637 characters of system prompt (the prompt file plus the whole of `config/offers.md` plus the skeleton) and about 200 of user message, so roughly **2.0k input tokens**. A finished proposal is about 400 output tokens. At `claude-opus-5`'s $5 / $25 per Mtok that is about **$0.02**, and **$0.05** in the worst case where the model writes to the 1,600-token cap. An earlier version of this table said 9k in / 1k out and about $0.07; that was an estimate and it was wrong |
| one booked call, whole proposal window | **one** polish call, because the claim is checked before the model. It used to be one per 5-minute tick: 146 calls, about $5 of discarded spend, for one delivered proposal |
| reviews and Maps facts | not run. A Google Maps actor pull is an Apify run billed per record |

## Open questions for Lorenzo

1. **The deposit.** Blueprint S7 says every proposal carries a 50 percent deposit. `config/offers.md` says the three reactivation offers are $0 up front, commission only. The offer sheet wins today: a reactivation proposal says there is no deposit and flags the contradiction, and a trigger proposal carries the deposit structure with no number because the retainer is TO CONFIRM. Confirm which is right, and give the retainer number if the deposit is meant to be real.
2. **The retainer range.** Until `$2,500 to $5,000/mo` stops being TO CONFIRM, no proposal, brief or follow-up can put it in writing.
3. **Where the proposal should land.** GHL Documents, PandaDoc, or a plain email attachment. All three are a paste today.
