# Upwork follow-up drafts (U1 to U5)

**What it does:** when a client opens a chat on one of Lorenzo's Upwork
proposals, the engine drafts his replies and his follow-ups for that chat. Every
morning (weekends included) he gets one batch of drafts, reads them, edits what he wants,
and sends each one himself in Upwork.

**What it never does:** it never writes to Upwork. No module in
`services/upwork_followup/` or `jobs/upwork_followup.py` may reference
`send_message`, `manage_proposals`, `respond_to_offer`, `manage_meetings`,
`submit_milestones`, `boost_profile`, `manage_offers` or `update_profile`, and
`services/upwork_followup/tests/test_no_upwork_write_path.py` fails the build if
one appears. The application flow (job selection, the Demo Library loop, the
Loom, the proposal) is untouched: files under `Coding/upwork-pipeline/` are read
for context and never written.

| | |
|---|---|
| Design (binding) | `services/upwork_followup/DESIGN.md` |
| Collect calls | `services/upwork_followup/collect_calls.md` (printed by `--print-collect`) |
| Ingest | `services/upwork_followup/collect.py` |
| Thread state machine | `services/upwork_followup/sequence.py` |
| Reply classifier | `services/upwork_followup/classify.py` (Claude Opus 5.5; under 0.8 confidence it asks again on the `escalate` role, also Opus 5.5) |
| Drafts | `services/upwork_followup/draft.py` and `prompts/` (Claude Opus 5.5) |
| Copy gate | `services/upwork_followup/copy_gate.py` |
| GHL mirror | `services/upwork_followup/ghl_sync.py` (shadow through `guard_write`) |
| Orchestration and cards | `services/upwork_followup/tick.py` |
| CLI | `jobs/upwork_followup.py` (laptop only, not a Modal schedule) |
| Proof source | `config/upwork_offers.md` |
| Price source | the framework reply's computed range only: $500 to $3,500 by default (DESIGN.md "Framework reply") |
| Schedule | the watch: every 30 minutes, 08:00 to 19:00 CT, every day including weekends (`watch.WATCH_DAYS`), as a Claude desktop scheduled task Lorenzo creates (prompt `services/upwork_followup/watch_task_prompt.md`); the first run of each CT day is a full run |
| Reads | `.tmp/upwork_followup/snapshot.json`, the store, the job folders under `Coding/upwork-pipeline/jobs/` |
| Writes | the store (`upwork:<room_id>` threads, `upwork_meta`, and the tick's own `upwork_followup:tick` record (summary card, blocked rooms already listed) and `upwork_followup:lock` run lease), `.tmp/upwork_followup/drafts_<date>.md`, one Job_Log row, cards on `--run` (alias `--now`), GHL would-do rows in shadow once the Upwork pipeline is configured |

---

## Scope

Only proposal rooms count. A room is in scope when the client opened a chat on
a proposal Lorenzo sent, which means the room links to one of his proposals
(it has a `proposal_id`). Everything else is left out:

- rooms where he already had a contract with that client, at any status
  (active, paused, closed or ended);
- rooms where an offer already turned into a contract;
- invitation-only rooms and every other room with no linked proposal (the
  ingest counts these as `omitted_unlinked`);
- rooms where the client has never written.

At the very first run, a room whose last client message is older than 45 days
is not enrolled automatically. It is listed once as "revivable", and
`--enroll <room_id>` brings it in. On later runs the limit is 60 days.

Upwork does not let a freelancer send the first message on a proposal, so a
thread only exists after the client opens the room. Every draft stays on
Upwork: no email address, phone number, outside chat app, outside calendar or
booking link. Loom links are fine.

## The watch (every 30 minutes, 08:00 to 19:00 CT)

Each watch run makes one read-only call (`list_rooms`, first page), saves it to
`.tmp/upwork_followup/watch_rooms.json` and asks the plan what to do:

| plan | when | what the run does |
| --- | --- | --- |
| `none` | nothing new since the last pull, or a full run must wait (see below) | stops; one summary line, no tick |
| `run` | the data is in but no `--run` finished on it (the last one was locked out, failed, lost its lease or never started) | `--run` only |
| `light` | a tracked room shows a client message or a room event the snapshot does not have yet, or (GHL mirror on) Lorenzo moved a thread's card in GHL | `list_messages` for those rooms only, `--ingest-light`, then `--run` |
| `full` | the first run of the CT day, no snapshot, an unreadable rooms file, a brand-new room, a contract on a tracked room, or more than one page of rooms moved | `--mark-full-start`, the whole collect (`scheduled_task_prompt.md`), `--ingest`, then `--run` |

A full run marks its start (`.tmp/upwork_followup/full_start.json`). Until
its `--ingest` lands, the watch does not start another: for 45 minutes it
counts as in progress, after that as failed, and it is retried 2 hours after
its start, not every 30 minutes. The `_run` reason says which, and when the
next try is. A light pull that comes back without the card's newest message
(empty, or only older messages) marks nothing as seen, so the next watch asks
again; after 3 such pulls for the same message it stops asking, and the next
full run reads the room.

A message Lorenzo sent himself is never a trigger (a room event on his side,
such as "System event: meeting_scheduled", is); the next full run (or the
next light pull of that room) picks it up. A room the day's full collect
already listed and left out (no linked proposal, too old) is not a trigger
either until the next day's full run. The exact rules are in
`services/upwork_followup/watch.py`.

**Run a watch by hand** (from the repo folder, in a Claude session with the
Upwork MCP): make the `list_rooms` call with `{"limit": 50, "room_type":
"ALL"}`, save the response to `.tmp/upwork_followup/watch_rooms.json`, then

```bash
python3 -m jobs.upwork_followup --watch-plan .tmp/upwork_followup/watch_rooms.json
```

It prints one JSON line, for example
`{"checked": 23, "mode": "light", "reasons": {"room_...": "new client activity"}, "rooms": ["room_..."]}`.
`rooms` is the list of rooms to read (only for `light`); `reasons` gives one
short reason per room, or under `"_run"` for the run as a whole (`"no new
activity"`, `"first run of the CT day (last full collect <date>)"`); `checked`
is the number of rooms on the page. The plan only reads: no store write, no
Job_Log row, no model call, and GHL is read only when the Upwork pipeline is
configured. For `light`, read each listed room's messages, save them as
`.tmp/upwork_followup/raw_light.json` (layout in `collect_calls.md`, "The
light path"), then

```bash
python3 -m jobs.upwork_followup --ingest-light .tmp/upwork_followup/raw_light.json \
    --rooms .tmp/upwork_followup/watch_rooms.json
python3 -m jobs.upwork_followup --run
```

**Force a full run:** ignore the plan and run the full collect by hand
(`--print-collect`, the calls, `--ingest`, `--run`), or run the morning
prompt (`scheduled_task_prompt.md`) once in a session. A successful full
`--ingest` resets the day: later watches compare against it. To lift a
waiting full run's 2-hour hold, delete `.tmp/upwork_followup/full_start.json`.

## The batch

Every run that reaches `--run` (the full one and each light one) writes the
batch. What arrives:

1. **A card** through `shared.notify` (push and email, the same channel as the
   other jobs), on `--run` only. One card per new draft, plus one summary card
   with the counts. The card's full title is `Upwork T<N> for <client>` for a
   follow-up, `Upwork reply for <client>` for a reply or
   `Upwork check-in for <client>` for a check-in. There are no buttons. The
   ntfy topic is public unless `NTFY_TOKEN` is set (or `NTFY_ALLOW_SENSITIVE=1`).
   On a public topic the push carries nothing from a client and no file path:
   its title is only `Upwork: 1 new draft (T<N>)` (or `(reply)`, `(check-in)`),
   and its body says the names and text are withheld. The full card, with the
   client-named title as its first line, the draft, the room link and the
   For-you notes, goes only on the email leg; when no email is set up, the push
   points him to the drafts file instead. A second run on the same snapshot
   sends no card, except the summary card when it finds a stage override (see
   Stages) or a newly blocked room. A draft recorded by a run that was killed
   before its card went out gets its card on the next run.
   In shadow (`MODE=shadow`, the default) notify records every card in the
   shadow log and delivers nothing unless he sets `NOTIFY_SHADOW_SEND=1`, the
   existing opt-in for real pushes to his own topic and inbox; the file below
   is always there.
2. **The file** `.tmp/upwork_followup/drafts_<YYYY-MM-DD>.md` (the Central
   date) with the same drafts, so he can copy from a file instead of a phone.
   It is rewritten on every run, `--dry-run` included. The top has the counts
   and the snapshot's age; a snapshot older than 20 hours gets a loud STALE
   SNAPSHOT warning (also in the Job_Log row), and the tick still runs. Next
   comes "Needs you": every client still waiting on him whose reply was
   dropped unsent with no new draft coming (it expired twice, 7 days each, or
   was cleared), as "reply skipped on <date>; client waiting since <date>".
   It is listed on every run until he answers in the room, runs `--resume`
   (a fresh reply draft on the next run), `--stop`s it or moves the stage.
   Then a "Check these" list (`needs_review` items and errors). Then, once,
   "Blocked on Upwork (no drafts)": each room the pull shows blocked by the
   client, with the date. The engine closes its thread (status `closed`,
   stage `lost` unless he set the stage) and never drafts for it; after that
   batch only `--status` shows it. On a public ntfy topic the summary push
   only counts these ("1 room blocked on Upwork (no drafts)", "Needs you: 1
   client ..."), with no names. Either section makes the run `attention`. The
   batch then groups jobs by stage (New reply, Proposal sent, Follow-up later, Call
   booked, Won, Lost) and shows each job's stage and room id. Every pending
   draft is shown in full, new or from an earlier run. Jobs in a drafting
   stage that need nothing today appear as one line each with the next due
   date; jobs in the other stages appear as one line each, so he can re-stage
   from the batch.

Each draft is laid out the same way:

- **The text to copy.** Ready to paste into the room as it stands, unless it is
  marked Needs edit.
- **Open room:** a link of the form
  `https://www.upwork.com/ab/messages/rooms/<room_id>`. Check that this link
  shape opens the right room the first time it is used live.
- **For you, not the client.** The job title, the date he applied, the touch
  history on this thread, and the private lines from the job's `assessment.md`
  (time, likelihood, standard pricing). None of this is ever in the draft text,
  and the copy gate refuses a draft that leaks it. A framework reply adds the
  line naming where its price range came from.
- **Suggests a call** when the draft proposes a short Upwork call.
- **Needs you** (replies only). Anything the reply could not answer from the
  room, the job post, the proposal or `config/upwork_offers.md`, such as a
  start date or a scope detail, plus any money figure the client mentioned
  ("Client mentioned $X; check the range"). The draft leaves a gap for these
  rather than guessing. Fill them in before sending.

**Needs edit** means the draft broke at least one copy gate rule (listed
below) even after one automatic retry. The card shows the draft anyway, with
the reasons. He fixes it by hand before sending, or ignores it. If the model
could not be reached at all (`llm_error` with no text), there is no card: the
batch lists "draft failed" under that job, and the next run drafts it again.

**Sending is detected automatically.** There are no buttons. On the next run,
any message from him in that room newer than the draft counts as the draft
being sent, even if he rewrote it completely. The touch count goes up and the
clock for the next touch starts from that message.

A draft he has not sent is shown again once after 3 days. After 7 days it is
dropped as skipped, and the next follow-up counts from the drop. At most 10 new
drafts are made per run: replies to clients who are waiting on him come first,
then the oldest silence; the rest wait for the next run.

**Guards on every `--run`.**

- **One run at a time.** A run holds a lease in the store
  (`upwork_followup:lock`, 30 minutes), always on the Mac's real clock, never
  on `--as-of`: a test run with an old or future `--as-of` cannot take the
  scheduled run's lease. The run renews it before every model call (each
  call that classifies a reply as well as each draft), every draft it saves
  and every card, so a slow run keeps it as long as it is working. A second `--run` started meanwhile prints "Another --run is still
  in progress" and does nothing. A lease with no renewal for 30 minutes (a run
  that died) is taken over, and the Job_Log row notes it. A lease stamped
  ahead of the Mac's clock (a clock that was wrong) blocks for 30 minutes at
  most. If a run finds its lease gone or taken over, it stops at once: no more
  model calls, saved drafts or cards; the drafts it had reserved but not
  written go back for the next run. Its batch and Job_Log row say LOCK LOST
  (status `lock_lost`).
- **Spend cap per run.** `UPWORK_RUN_BUDGET_USD` (default 1.50) caps the
  run's model spend, counted at each call's worst case: the prompt, the call's
  reply cap and the 1,024 thinking tokens every Claude Opus 5.5 call may add,
  the same number `shared.llm` reserves against its own ceiling (about $0.04 to
  $0.046 per draft call and up to $0.03 per classification). `UPWORK_RUN_MAX_CLASSIFY`
  (default 40) caps classifier calls. Set them in `Agentic Worklfows/.env` to
  change every run. A value set in the shell wins over `.env`, so one run can
  have a lower cap:

  ```bash
  cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
  UPWORK_RUN_BUDGET_USD=1.00 python3 -m jobs.upwork_followup --run
  ```

  A value that is not a finite number of 0 or more (a whole number for the
  classifier cap), such as `inf`, `nan`, `-1` or text, is ignored with a
  warning and the default is used. A budget above 10.00 is clamped to 10.00
  with a warning (the most one run may spend; the cumulative ceiling in
  `config/llm_budget.json` is $10.00 too). Once either cap is reached, no more calls
  are made. The drafts not yet written are released for the next run, and
  unclassified replies wait for it too. The batch shows a RUN BUDGET warning and the
  Job_Log row has `budget_hit`. The cumulative ceiling in `shared/llm.py`
  still applies on top.
- **The shared LLM spend ceiling.** `shared/llm.py` keeps one cumulative
  counter per store (`llm.spend_usd`, cap `budget_usd` in
  `config/llm_budget.json`, $10.00). This tick runs on the laptop, so its
  counter is the one in the laptop store, `.tmp/store.json`
  (`shared.store.get_store()`). Every laptop run that calls the model shares
  it: this tick, the scheduled `retro_packet` (Fri 16:00) and `list_factory`
  (Sun 09:00), and any job run by hand from the repo folder. The Modal reply
  engine keeps its own counter in its Modal Dict; resetting that one (for
  example with `changesets/deploy/budget.py reset`) does not lift this stop.
  It is separate from the per-run cap above. At the ceiling
  `shared.llm` refuses the call before anything is billed. The run then makes
  no further model call. A client reply it was classifying stays unread: it is
  never marked read as `neutral`, gets no `needs_review`, and is classified
  properly on the first run after the ceiling is lifted. A draft refused at the
  ceiling is released the same way. The batch shows an LLM SPEND CEILING
  warning (not RUN BUDGET), the summary card title says "LLM spend ceiling
  reached", and the Job_Log row has `budget_hit: ceiling`. Every run defers the
  same work until the ceiling is raised or the counter reset. Check it with:

  ```bash
  cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
  python3 -c 'from shared import llm; print(llm.budget_status())'
  ```

  Run from the repo folder on the laptop, it reads the laptop counter.
  `spent_usd`, `remaining_usd` and `over_budget` say where it stands. Raising
  `budget_usd` or resetting the laptop counter (`llm.reset_spend()`, run on
  the laptop) is Lorenzo's call; no agent does either.
- **Snapshot from the future.** A snapshot stamped more than 10 minutes after
  the run is refused as an error run with an alert, the same as a missing
  one. A missing or future snapshot alerts once per Central day.

## Stages

Every thread carries a stage, using the same stage keys as the cold-email
Sales pipeline, mirrored into a separate GHL "Upwork" pipeline (never the Sales
pipeline itself). Only `new_reply` and `proposal_sent` get drafts.

| stage | drafts? | set by |
| --- | --- | --- |
| `new_reply` | yes | auto on enrolment (the client opened a chat on his proposal) |
| `proposal_sent` | yes | Lorenzo, or auto when an offer to him is `awaiting_your_acceptance` |
| `call_booked` | no | Lorenzo |
| `follow_up_later` | no, until `follow_up_at` arrives; then one check-in draft and the stage returns to `new_reply` | Lorenzo, or auto on a `not_now` reply |
| `won` | no | auto on an ACTIVE contract or a `contract_started` offer, or Lorenzo |
| `lost` | no | Lorenzo, or auto on declined, hired_other, not_interested, hostile, closed_out or dormant |

**Moving a job.** From the terminal:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m jobs.upwork_followup --stage room_abc123 call_booked
python3 -m jobs.upwork_followup --stage "invoice sync" lost
```

The first argument is the room id or a fragment of the client name or the job
title (any case). No match, or more than one, changes nothing and lists the
candidates. Once the GHL
mirror is live, he can also drag the opportunity (named `<client> (Upwork)`)
to another stage in the separate GHL "Upwork" pipeline. Each run reads that
move back and applies it, the same as a CLI move. A room that got a real
contract is the exception: the same run marks it won and pushes `won` to GHL,
whatever stage GHL shows.

A GHL move is never overwritten; the one exception is `won` from a real
contract. That holds against his own CLI too: whenever a run reads back a GHL
card move that replaces a stage he set with `--stage` (or with a `--resume`
that moved the stage), it applies the GHL move. The batch and the summary
then say so in one line, for example "The stage you set (call_booked) for
<client> (room <id>) was overridden by the GHL card move to proposal_sent;
run --stage call_booked again if you meant it." The Job_Log row lists it
under `stage_overrides`, the run's status is `attention`, and the summary
card goes out even on a rerun of the same snapshot. The public push names no
client or room, only the count. No GHL timestamp is compared. The line comes
in two cases:

- **He ran `--stage` (or `--resume`) and also moved the card in GHL before
  the next run.** The run applies the GHL move, whichever he did last. If he
  meant the CLI stage, he runs `--stage` again: that stage is pushed to GHL
  once, on the next run.
- **He moved the card in GHL after an older `--stage` had already reached
  GHL.** For example, `--stage call_booked` days ago, mirrored since, then a
  drag to `won` in GHL: the next run shows the line once, with status
  `attention`. Nothing needs doing; the GHL move is his latest. Running
  `--stage` again here would undo his GHL move, because that stage is then
  pushed to GHL.

**His move always wins.** A stage he sets, by CLI or in GHL, is never changed by
the engine. The one exception is `won` from a real contract on the room.
Moving a job into a non-drafting stage withdraws any draft still waiting.

**What the engine moves on its own**, only where he has not set the stage:

- a new thread starts at `new_reply`;
- an offer to him that is awaiting acceptance moves it to `proposal_sent`;
- a "not now" reply moves it to `follow_up_later` with a follow-up date (the
  date the client named, or 30 days out);
- a contract or a started offer moves it to `won` (this one applies even over
  his stage);
- a decline, "hired someone else", "not interested" or a hostile reply moves
  it to `lost`;
- a thread that closed out after the last touch, or went 60 days with no client
  message, moves to `lost`.

## Follow-up spacing

A silence starts when his message is the latest in the room. The follow-ups
are due on days 2, 4, 7, 11, 16, 23 and 30 after his last message (each gap is
counted from the previous touch he actually sent):

| touch | day | what it adds |
| --- | --- | --- |
| T1 | 2 | one concrete idea for their project, tied to their post or the room, plus one easy question |
| T2 | 4 | points to the Loom or demo made for them, or describes one specific piece of the build |
| T3 | 7 | one short line that their project reminds him of a past client with a similar setup (a matching line in `config/upwork_offers.md`; no client name, no figures), or a relevant insight if none fits |
| T4 | 11 | one risk or edge case grounded in what they wrote, never an invented problem |
| T5 | 16 | a yes/no or pick-one question on scope or timing |
| T6 | 23 | a concrete low-effort next step: a short Upwork call or a small first milestone |
| T7 | 30 | a graceful close that leaves the door open |

Other timing rules:

- An unsent draft is resurfaced after 3 days and skipped after 7.
- A client reply ends the silence and resets the touch count. After he
  answers, a new silence starts again at T1.
- **Cap of 3 cycles.** After the client has broken 3 silences, the next silence
  closes out as soon as its T7 is sent. Otherwise a thread closes out 14 days
  after T7 with no answer. Closed out means `lost`.
- **Dormant after 60 days** with no client message: the thread stops and moves
  to `lost`.
- The engine only drafts. The spacing tells him when a draft appears, not when
  anything is sent.

## Calls by context

No touch forces a call on a fixed day. Every draft (replies, check-ins and
touches alike) gets three optional call times (rule of 2026-09-28): three
different business days, the first can be today when it is at least 4 hours
out, all between noon and 6pm CT Monday to Friday and no more than 5
business days out. They are written in the client's time zone with its
label, then one line for when none fit, for example:

    Wednesday at 3pm, Thursday at 4pm or Friday at 2pm ET
    If none of those work, send me a couple of times that work for you.

The zone comes from the client's location in the job folder's `jd.txt`
summary line ("Client in Virginia, US ..."): the place right after "Client
in" decides, a US state, DC or state code beats a city of the same name
("Paris, TX" is CT), a US state or city gives ET, CT, MT or PT (Arizona and
Saskatchewan say "Arizona time" and "Saskatchewan time"), another country
gives its own zone ("CEST", "Bogota time"). When the folder names no
location, or no folder matched, the times are in CT. No time lands on the
client's Saturday or Sunday, and times after 9pm client time are used only
when nothing earlier fits. To fix a wrong zone, correct the "Client in ..." sentence in that
`jd.txt`; the next pull picks it up. The model proposes a short
Upwork call only when the conversation supports it: the client is engaged, has
asked about scope, fit or timeline, or the thread has momentum. Otherwise it
leaves calls out. T6 picks between a call and a small first milestone,
whichever fits the thread.

The times are not read from a calendar. If a draft proposes a call, check the
three times against his calendar before sending. Each draft records
`proposes_call` (the model's own flag, backed up by a text check), and the
card and the batch show it as "Suggests a call".

## Copy rules the gate enforces

A draft goes to Needs edit when it breaks any of these (the code the card shows
is in brackets):

- It is empty. (`empty`)
- It has an em dash or en dash. (`em_dash`)
- It has an exclamation mark. (`exclamation`)
- It has any other non-ASCII character once smart quotes are straightened.
  (`non_ascii`)
- It is longer than 900 characters for a follow-up or check-in, or 1,500 for a
  reply. (`too_long`)
- It gives or asks for any off-Upwork contact: an email address, a phone
  number, WhatsApp, Telegram, Skype, Calendly, "text me", "email me", "call me
  at", or a request to move off Upwork or pay outside it.
  (`off_platform_contact`)
- It has a link other than a Loom link or a link already in the job post. Any
  upwork.com link is refused too. (`external_link`)
- It has a dollar figure or a percentage that is not written in
  `config/upwork_offers.md`. (`figure_not_in_offers`)
- It repeats a private fact from the assessment or client intel: a price,
  likelihood, hours estimate or review fact. (`private_fact`)
- It has a placeholder: square brackets, double curly braces, TODO, TBD, XX or
  an angle-bracket placeholder. (`placeholder`)
- It greets the client by first name when no first name is known.
  (`first_name_unknown`)
- It is not in his own first person: "we", "us" or "our" outside a quote, or
  him writing about himself in the third person. (`not_first_person`)
- It uses a filler line such as "just checking in", "circling back", "bumping
  this" or "following up on my proposal". (`filler_phrase`)
- It reads generic: a stock follow-up line such as "hope you're doing well", or
  nothing in it that is specific to this job post or the client's own messages.
  (`generic_phrasing`)

The AI and automation word ban from the cold-email gate does not apply here,
because Upwork clients post automation jobs.

Pricing (Lorenzo, 2026-10-05 and 2026-10-06): when a client who showed
interest asks questions, the reply follows his setter framework
(`prompts/reply_framework.md`) and gives one price range, never a single
number. The range defaults to $500 to $3,500: the low end near the post's
fixed budget and never below $500, the top raised only by a fixed range the
job's assessment states unambiguously. Figures in the client's messages never
move it. When the budget reaches the top there is no range and the price goes
to NEEDS_YOU. No other draft states a price, and `config/upwork_offers.md`
still holds proof lines only.

## CLI reference

All commands run from the repo folder. `TARGET` is a room id, or a fragment of
the client name or the job title (any case); no match, or more than one,
changes nothing and lists the candidates.

| command | what it does |
| --- | --- |
| `python3 -m jobs.upwork_followup --print-collect` | prints the exact read-only MCP calls and the current `org_uid` (from `collect.collect_instructions()`) |
| `python3 -m jobs.upwork_followup --ingest .tmp/upwork_followup/raw.json` | turns the raw MCP responses into `.tmp/upwork_followup/snapshot.json` and prints the room counts, the omitted counts and the sections; refuses a broken file, keeps the old snapshot and exits 1 |
| `python3 -m jobs.upwork_followup --watch-plan .tmp/upwork_followup/watch_rooms.json` | the watch plan for the saved `list_rooms` page: one JSON line with `mode` (`none`, `light`, `full`), `rooms`, `reasons`, `checked`. Read only |
| `python3 -m jobs.upwork_followup --mark-full-start` | records that a full collect starts now (`.tmp/upwork_followup/full_start.json`), so the watch does not start a second one while it runs |
| `python3 -m jobs.upwork_followup --ingest-light .tmp/upwork_followup/raw_light.json --rooms .tmp/upwork_followup/watch_rooms.json` | merges the light pull's messages into the existing snapshot, those rooms only; refuses a broken file (or one that merges no room), keeps the snapshot and exits 1 |
| `python3 -m jobs.upwork_followup --dry-run` | the default (no flag does the same); runs the tick on a throwaway copy of the store with no model call (replies classify as neutral), writes the drafts file (with "Would draft" where a draft is due) and the Job_Log row; saves nothing, calls no GHL, sends no card |
| `python3 -m jobs.upwork_followup --run` (alias `--now`) | runs the tick for real: classifies replies and writes the drafts (both Claude Opus 5.5), saves the store, mirrors GHL when configured, sends the cards; it first prints that the run spends Anthropic tokens. One run at a time (a second one prints that another run is in progress and does nothing), within the per-run spend cap |
| `python3 -m jobs.upwork_followup --status` | a table of every thread: client, job title, stage (set by), status, pending draft, next due, room id. "Next due" says "blocked on Upwork since <date>" for a blocked room (a blocked room that was never enrolled gets a row too, status "not enrolled"), "closed: the room was blocked on Upwork; --resume or --stage reopens it" once the room is open again, and "reply skipped on <date>; client waiting since <date>" for a client left waiting |
| `python3 -m jobs.upwork_followup --stage TARGET <stage>` | moves a job to a stage as his move (`set_by lorenzo`), which the engine never overrides |
| `python3 -m jobs.upwork_followup --stop TARGET` | stops a thread (`stopped`) and withdraws its pending draft |
| `python3 -m jobs.upwork_followup --resume TARGET` | restarts a stopped or closed thread with a fresh silence (or a reply draft when the client wrote last); for a client under "Needs you" it asks for a fresh reply draft on the next run |
| `python3 -m jobs.upwork_followup --enroll TARGET` | enrolls a room from the current snapshot that the age rule left out (the "revivable" list in the batch); scope, contract and client-message rules still apply |

`--as-of <ISO>` evaluates at a fixed time (the `--run` lease still uses the
real clock), `--snapshot <path>` reads another snapshot, `--json` prints the
tick result as one JSON document on stdout and nothing else there, whatever
the outcome, a run skipped for the lock included (`"status": "locked"`); the
token note and any log warnings go to stderr. The tick
exits 1 only when the snapshot is missing, unreadable or stamped in the
future; a failed draft, a GHL error, a reached budget, a run skipped for the
lock or a run that lost its lease (`lock_lost`) is in the output, the batch
and Job_Log, and the exit code stays 0.

## Going live checklist

1. **Create the scheduled task.** In the Claude desktop app, create a scheduled
   task that runs every 30 minutes, 08:00 to 19:00 CT, every day including
   weekends (cron `*/30 8-18 * * *` and `0 19 * * *`), and paste
   the prompt from `services/upwork_followup/watch_task_prompt.md` exactly (its
   first run each day is the full run). If the older 08:30 task from
   `scheduled_task_prompt.md` exists, turn it off. Persistent config is his
   action; no agent creates it.
2. **A supervised shadow week, on `--run`.** A dry run writes no draft text,
   no Needs you lines and no For-you block, so it cannot be reviewed. The
   shadow week runs the real tick (`--run`) with `MODE` left at its default,
   `shadow`. Drafts are written by the model into the batch file. Every card
   stays in the shadow log (nothing is pushed or emailed unless he sets
   `NOTIFY_SHADOW_SEND=1`), the GHL mirror stays off (no Upwork pipeline yet;
   even configured, shadow writes are would-do rows only), and nothing is ever
   written to Upwork. It costs real Anthropic tokens. Counted at worst case
   (what the per-run cap sees), a draft call is about $0.04 to $0.046 (about
   2,400 prompt tokens, the reply cap and 1,024 tokens of thinking headroom at
   $4 in / $20 out per million) and a classification up to $0.03, so a typical
   morning with 10 rooms counts about $0.40 to $0.70. The bill is lower,
   because a call rarely uses its whole cap and headroom. The worst case is the
   $1.50 per-run cap itself: it stops new drafts at about 35 draft calls, and
   40 classifications alone count about $1.20, so a morning with many replies
   can leave drafts for the next run. Watch the first run:
   check the collect used only read-only calls, the ingest wrote a snapshot,
   and the Job_Log row has sensible counts.
3. **Review the drafts.** Each morning of that week, read
   `.tmp/upwork_followup/drafts_<date>.md` against the real rooms. Check the
   tone, that nothing private leaked, that the Open room link opens the right
   room, and that Needs you items are real gaps. He sends what he likes by hand
   as usual; the next run detects it. After the week, the only change is
   turning card delivery on (`NOTIFY_SHADOW_SEND=1`, or live mode after his
   sign-off).
4. **GHL contacts without email.** Upwork gives no client email or phone. The
   live GHL path refuses such a contact and logs `ghl_contact_needs_identity`
   until `CONTACT_WITHOUT_EMAIL_VERIFIED` in `shared/ghl.py` is `True`. Flip it
   only after a sandbox test proves GHL accepts a contact with only a name and
   the `upwork` tag. Until then the mirror runs in shadow (would-do rows only)
   and stages live in the store and the CLI.

   First live rehearsal, before the mirror leaves shadow. This is Lorenzo's
   own live write, made by him after his sign-off; no agent makes it. On one
   test opportunity in the Upwork pipeline, make one PUT to
   `/opportunities/{id}` that changes the status (for example `open` to
   `lost`, with its stage id), then one GET of the same opportunity. Record
   both answers in full: the PUT answer body as well as the GET. Pass means
   the PUT answer echoes the stage id and status that were sent (the mirror
   trusts that echo: an answer showing another stage, status or pipeline is
   `ghl_write_rejected`, and one that leaves those fields out cannot be
   checked), and the GET shows the new status and the new stage. No
   timestamp check is needed, because the mirror compares no GHL times: a
   GHL move always wins. DECISIONS Q-O6 (dated stage changes from GHL) stays
   open and is not settled by this rehearsal. Until it passes, the GHL mirror
   stays in shadow.
5. **Pricing.** Only the framework reply states a price, as the computed
   range ($500 to $3,500 by default); Lorenzo checks it on the card before he
   sends. `config/upwork_offers.md` holds proof lines only.

Live GHL writes still need `MODE=live` plus `ALLOW_LIVE_WRITES=1`, set by him
after sign-off. No Upwork write exists to switch on.

## Failure modes

| symptom | cause | what to do |
| --- | --- | --- |
| No batch, or the tick reports the snapshot `missing`, `unreadable` or `unexpected shape` | the collect or the ingest did not run, or failed | open the scheduled task's run log; run `--print-collect`, the calls and `--ingest` by hand |
| The snapshot is old (its `generated_at` is from an earlier day) | the collect step failed and the ingest kept the previous snapshot on purpose | same as above. The batch, the summary card and the Job_Log row carry a STALE SNAPSHOT warning once the snapshot is older than 20 hours |
| The tick reports the snapshot is from the future | `generated_at` is more than 10 minutes after the run (a wrong clock or a hand-edited file) | nothing was drafted; re-run the collect and `--ingest`, and check the Mac's clock |
| "Another --run is still in progress" | a second `--run` started while one was drafting (it renews its lease as it works), or a run died less than 30 minutes after its last renewal. The message says when the lease is free at the latest | wait; a dead run's lease is taken over 30 minutes after its last renewal and noted in Job_Log. "Its time stamps are ahead of this machine's clock" means a clock was wrong: it clears within 30 minutes, then check the Mac's clock |
| "LOCK LOST" in the batch, Job_Log status `lock_lost` | the run's lease was taken over (another run found it stale, usually because this run hung for over 30 minutes, for example on a model call) or removed | nothing to redo: the run stopped before its next model call, saved draft or card, and gave back the drafts it had reserved but not written. The run holding the lease does the rest; if none is running, start `--run` again |
| A RUN BUDGET warning | the run reached `UPWORK_RUN_BUDGET_USD` (default $1.50) or `UPWORK_RUN_MAX_CLASSIFY` (default 40) | the rest waits for the next run on its own. If it happens every morning, raise the cap in `Agentic Worklfows/.env` (or in the scheduled task's environment, which wins) |
| An LLM SPEND CEILING warning, card title "(LLM spend ceiling reached)", Job_Log `budget_hit: ceiling` | `shared.llm` refused a call at its cumulative ceiling (`config/llm_budget.json`; the laptop counter `llm.spend_usd` in `.tmp/store.json`, shared by every laptop job that calls the model, such as `retro_packet` and `list_factory`), not this run's own cap | the replies and drafts it lists wait unread; nothing was marked `neutral`. Check the laptop counter from the repo folder with `python3 -c 'from shared import llm; print(llm.budget_status())'`. It repeats every run until Lorenzo raises `budget_usd` or resets the laptop counter; raising the per-run cap does not help, and neither does resetting the Modal reply engine's counter, which is a separate one |
| "Needs you" lists a client | the client wrote last and the reply drafted for them was never sent (it expired twice, or was cleared); no new draft comes | answer in the room, or `--resume TARGET` for a fresh reply draft on the next run, or `--stop` / `--stage` if it should not be answered |
| "Blocked on Upwork (no drafts)" | the client blocked the chat on Upwork (the pull's newest room event is "blocked") | nothing can be sent there. The thread is closed and listed once; `--status` keeps showing it. A client message after an unblock reopens it on its own, or `--resume` / `--stage` do |
| The watch says "the full run started at ... did not finish; next try after ..." | the full run failed or the session died (no snapshot from today) | open the task's run log for the full run's error. The watch retries every 2 hours; after a fix, delete `.tmp/upwork_followup/full_start.json` to retry at the next watch |
| The watch says `run` again and again | `--run` keeps being locked out or failing before its end | read the `--run` output in the task's run log (a stuck lease frees itself 30 minutes after its last heartbeat) |
| `--ingest-light` refuses the file | no snapshot yet, the light file is broken, or every listed room's `list_messages` failed | nothing is overwritten; the next watch plans the same rooms again (or `full` when there is no snapshot) |
| The ingest refuses the file | `list_rooms` or `proposals` is missing or an error, `proposal_rooms` is absent, or the file is empty or an error. Also refused: a `collected_at` more than 10 minutes in the future (the session wrote the wrong date or UTC offset); `live_threads` missing or not a list; any MCP error response in a required slot (a `status` other than ok or success, `success: false`, an `error` or `errors` field, or a top-level message with no data) | nothing is overwritten. Re-run the collect and read the error |
| The batch says "Upwork data incomplete: N room links failed; sections missing: ..." | a `get_room` call failed for N proposals (their rooms are left out of the batch), or the proposals, contracts or offers section was not collected | the run status is `attention` and the rest of the batch is fine. Re-run the collect; the line clears when the data comes back |
| A section was not collected | a `get_room`, `list_messages`, contracts or offers call failed. The snapshot marks it `false` in `sections` and lists the ids in `link_errors` or `missing_messages` | rooms without messages get a `needs_review` (`messages_missing`) instead of a draft. Re-run the collect; the flag clears when messages come back |
| The snapshot says `truncated` | a step stopped at its cap with data left (`truncated_sections` names it). `live_threads` in that list means the "Always read these rooms" list hit its cap, so some enrolled threads were not re-read | older rooms may be missing from the batch. Tell the main session if it keeps happening |
| A parameter was rejected by the MCP | the parameter names for `list_messages` and `list_offers` have not been confirmed live | the session calls `upwork__get_tool_help` for that tool (read-only), uses the documented name and says what it changed. Update `collect_calls.md` once confirmed |
| No drafts at all | every job is in a non-drafting stage (`call_booked`, `follow_up_later`, `won`, `lost`), or stopped, or nothing is due yet | run `--status`. Move a job back to `new_reply` or `proposal_sent` if it should get drafts |
| A draft stuck on Needs edit | the model kept breaking a gate rule | edit it by hand and send, or ignore it; it is skipped after 7 days. If the same code keeps coming back, tell the main session so the prompt can be fixed |
| "draft failed" under a job, status `error` | the model could not be reached (`llm_error`) | nothing to do: the reservation was cleared and the next run drafts it again |
| The batch says "GHL mirror: off (ghl_not_configured ...)" | the Upwork pipeline is not in `config/ids.json` `pipelines.upwork` yet | expected until he creates it; stages live in the store and move with `--stage` |
| A `needs_review` line with `low_confidence` | the classifier was unsure about a label that would change the stage (for example a decline). It was downgraded to `neutral` and the raw label is kept | a reply card still arrives. Read the room and move the stage yourself if the client did decline |
| A `needs_review` line with `unknown_last_message`, `client_wrote_after_lost` or `unrecognised_label` | the last message's sender was unclear, a lost client wrote again, or the classifier returned something unknown | read the room. For a lost client who wrote again, move the stage back to `new_reply` if it is worth answering |
| A thread shows `error` | a store or classifier error on that one thread; other threads still ran | re-run the tick; it is idempotent. An error named `NestedStoreCall` is a code bug (a store or model call made while a store lock was held): tell the main session |
| The batch says "N rooms changed while this run classified them, so they are left for the next run" | the run classifies new client messages before it locks the thread, then checks under the lock that the thread's read position is unchanged. A change to that position defers a room (another run or writer read those messages in between, or the thread's new messages changed). A `--stop`, `--stage` or `--resume` made between the two passes is usually applied, not deferred. The exception is a move that changes which messages the thread reads. A `--stage won` stops it reading the messages this run classified: the room is deferred with `message_ids_changed`. A move that takes a won or closed thread out of that status (a reopen or a `--stop`, for example) makes it read a message this run did not classify: the room is deferred with `new_messages` | nothing to do: those rooms' new messages were not marked read and no draft was made for them this run; the next run reads them again. The job title, the GHL read-back and the GHL mirror of the thread's current stage can still be written for that room. The room ids and reasons (`new_messages`, `message_ids_changed`) are in the Job_Log row's `deferred_rooms` |

## GHL mirror recovery

These show up only once the Upwork pipeline is configured. Each one is a line
under "GHL mirror errors" in the batch (the run's status is `attention`), and
the tick carries on.

**`ghl_blocked` (every run until he clears it).** A live create answered
without an id (reported once as `ghl_no_id_returned`). A retry could add a
second copy of the contact every morning, so nothing is created or moved in
GHL for that thread until he clears the block. The line names the room, the
reason and the stage waiting to be mirrored. There is no CLI command for it.
To clear it:

1. In GHL, find what the create left: the contact (the client's name, tag
   `upwork`) and the opportunity `<client> (Upwork)` in the Upwork pipeline.
   Note their ids and the stage the opportunity is in now.
2. From the repo folder, write them into the thread and remove the block in
   one edit (the room id is on the batch line):

   ```bash
   cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
   python3 - <<'EOF'
   from shared.store import get_store
   ROOM = "room_abc123"                  # the room id on the ghl_blocked line
   CHANGES = {"opportunity_id": "PASTE_OPPORTUNITY_ID", "stage": "new_reply"}
   def fix(t):
       if not isinstance(t, dict):
           raise SystemExit("no thread upwork:%s; nothing changed" % ROOM)
       ghl = dict(t.get("ghl") or {})
       ghl.update(CHANGES)
       ghl.pop("blocked", None)
       t["ghl"] = ghl
       return t
   print(get_store().mutate("upwork:" + ROOM, fix)["ghl"])
   EOF
   ```

   `CHANGES` names only what changes; the rest is kept. Add `contact_id` if
   the contact exists but the thread has none, and `opportunity_id` plus
   `stage` (the opportunity's current stage, as one of the six stage keys) if
   the opportunity exists. Leave out what GHL does not have: the next run
   creates it at the thread's stage (`CHANGES = {}` creates both).
3. The next `--run` resumes the thread and moves the GHL card to the thread's
   stage (the one `--status` shows). To keep GHL's stage instead, move the
   thread to it with `--stage` first. If the create blocks again, tell the
   main session instead of clearing it a second time.

**`ghl_stage_conflict`.** The mirror reads a card before moving it, and writes
only while GHL still shows the stage it last wrote. GHL showed something else,
so nothing was written. Another of the six stages means he moved the card in
GHL: nothing to do, because the next run applies his move to the thread. For a
column outside the six, or another pipeline, move the card back to one of the
six stages of the Upwork pipeline; until then the error repeats whenever there
is a stage to push. `won` from a real contract is the exception: it is written
over any stage in the Upwork pipeline, never into another pipeline. A GHL move
also wins over a stage he set with `--stage` or `--resume`: the batch says
"The stage you set (X) for ... was overridden by the GHL card move to Y; run
--stage X again if you meant it." If he meant it, `--stage` again is pushed on
the next run, since GHL now holds the stage the mirror knows. If the GHL move
is the one he wants (for example a drag made after an older `--stage` had
reached GHL), nothing needs doing (see Stages).

**A card he moved into another pipeline.** The read-back ignores a card that
sits in another pipeline (Sales, Sales Requests or any other): the thread keeps
its stage and no error shows while there is nothing to push. The next time the
engine changes that thread's stage (a client reply, a close-out, dormant), the
mirror reads the card first, finds it outside the Upwork pipeline and reports
`ghl_stage_conflict` on every run with that stage to push. It never moves a
card between pipelines, `won` from a contract included. To fix it, move the
card back into the Upwork pipeline in GHL; the next run reads its stage back.
If the card belongs where it is now, use `--stage` to give the thread the stage
it should have (`won` or `lost` stops the drafts). The conflict line then
still repeats on each run while that stage differs from the one the mirror
last wrote, because the mirror will not touch a card outside the Upwork
pipeline.

**`ghl_write_rejected`.** GHL answered a write but did not apply it: a
`{"succeded": false}` body, or a stage move answered with a stage, status or
pipeline other than the one sent. The mirror keeps the stage it last knew and
the next run tries again. If it repeats, open the card in GHL and compare its
stage and status with the thread's (`--status`); a status GHL will not take is
the usual cause (see Going live checklist, item 4).

**`ghl_read_failed`.** GHL could not be read just before a move, so nothing was
written and the next run tries again. If it keeps repeating, check that the
opportunity still exists. If it was deleted, run the snippet above with
`CHANGES = {"opportunity_id": None, "stage": None}`, and the next run creates a
new one.

## Rollback

Stop (or delete) the scheduled task in the Claude desktop app. Nothing needs
undoing on Upwork, because nothing is ever written there. The store threads and
`.tmp/upwork_followup/` files can stay; they are local and inert without the
task. In shadow the GHL mirror wrote nothing live. If it has been switched to
live, the Upwork contacts and opportunities in GHL are ordinary records he can
leave or delete by hand.

## Tests

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m pytest services/upwork_followup/tests -q
```

Tests mock every model call and use invented client names only. Real room data
lives in `.tmp/` and never in the repo.

## Where the watch runs (2026-09-24)

The scheduled task `upwork-followup-watch` runs from the run folder
`/Users/lorenzovillarreal/Desktop/AdveroSolutions/.worktrees/run/Agentic Worklfows`,
a checkout of main with symlinks to the main folder's `.env` files,
`credentials.json` and `.tmp`, so state and credentials are shared with the
main folder while its code stays on main whatever branch the main folder has
checked out. Update it after a push to main:
`git -C /Users/lorenzovillarreal/Desktop/AdveroSolutions/.worktrees/run fetch -q origin && git -C /Users/lorenzovillarreal/Desktop/AdveroSolutions/.worktrees/run checkout -q --detach origin/main`.
Every `--run` in the task sets `NOTIFY_SHADOW_SEND=1`, so draft alerts reach
Lorenzo in shadow mode.
