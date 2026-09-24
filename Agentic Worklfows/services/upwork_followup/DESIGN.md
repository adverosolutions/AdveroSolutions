# Upwork follow-up pipeline: design (v1, 2026-09-22)

Lorenzo's ask (2026-09-22): Upwork leads flow through the same pipeline as the
cold-email leads. When a client has an open Upwork room with him and no
contract, the system drafts a 6 to 8 touch follow-up sequence, and he sends
each touch himself. A client reply gets a drafted response instead.

This file is the contract every piece builds against. Field names here are
binding; change them only by editing this file first.

**Scope update from Lorenzo (2026-09-22, later the same night). It overrides
anything below that disagrees.**
- **Scope.** Only replies to proposals Lorenzo sent, once the client opens a chat.
  A room qualifies only when it links to one of his proposals (it has a
  `proposal_id`). Invitation-only rooms and every other room are out of scope.
- **Bespoke, never automated.** Upwork stays hand-sent. Every draft goes to
  Lorenzo and nothing is ever sent for him. Drafts must read as written for that
  one client, never as a sequence template.
- **Morning drafts.** One morning batch (08:30 CT) holds a draft for every job in a
  drafting stage (see Stages) that needs one: a reply when the client wrote last,
  or the next follow-up when it is due. Every other job in a drafting stage
  appears in the same batch as one line with its next due date.
- **Stages.** Lorenzo moves jobs between pipeline stages himself, as he does for
  cold email. Jobs in a non-drafting stage get no drafts at all.
- **Calls by context.** Pushing for a call depends on the conversation. Any draft
  may propose a short Upwork call when the context supports it (the client is
  engaged, asks about scope or fit, or the thread has momentum). No touch forces
  a call on a fixed day.

## Hard boundaries

1. **The engine never writes to Upwork.** No module in `services/upwork_followup/`
   or `jobs/upwork_followup.py` may reference `send_message`, `manage_proposals`,
   `respond_to_offer`, `manage_meetings`, `submit_milestones`, `boost_profile`,
   `manage_offers` or `update_profile`. A test enforces it (the same idea as
   `jobs/tests/test_upwork_rooms.py::test_module_has_no_upwork_write_path`).
   Lorenzo copies each draft and sends it in Upwork himself.
2. **The application flow and the Demo Library loop are untouched.** Files under
   `Coding/upwork-pipeline/` (job folders, `proposals.csv`, `applications.csv`,
   templates, skills) are read, never written. `Desktop/Projects/library` is not
   read at all. `jobs/upwork_rooms.py` is imported for helpers only
   (`clean_text`, `normalize_room`, `normalize_contract`, `parse_ts`), never edited.
3. **Upwork rules.** Freelancers cannot send the first message on a proposal, so a
   thread exists only once the client has opened a room (replied, invited,
   interview). Every draft stays on-platform: no email address, phone number or
   handle, no channel aimed at Lorenzo or the client (a call, message, meeting or
   payment outside Upwork), no booking or calendar link for a call with Lorenzo,
   and no request to move off Upwork or pay outside it. A platform the job post or
   client names may appear as the project's subject ("the bot texts the lead").
   Loom links (`loom.com`) are allowed.
4. **Shadow first.** GHL writes go through `shared.ghl` (guarded by
   `guard_write`). `shared.notify` follows the existing shadow contract. LLM calls
   go through `shared.llm` roles only (`classify` = Haiku, escalate < 0.8 to
   `escalate`; `draft` = Sonnet). Tests mock every LLM call. No test or dry run
   spends tokens.
5. **Client text is untrusted data.** Room messages, job posts and client names
   pass through `upwork_rooms.clean_text` and are wrapped as quoted data in
   every prompt, never as instructions.
6. **Private material never reaches a client.** `assessment.md` (time,
   likelihood, pricing, questions) and `client.json` intel may be shown to
   Lorenzo on the card under "For you, not the client", and `assessment.md`'s
   "Ask before quoting" questions may inspire a touch's question, but no draft
   may quote pricing, likelihood or review facts from them. Their figures do not
   reach the model either: the prompt shows "(figure withheld)" in their place.
   The job post and the room messages are the client's own text and are
   shown as written, but the client stating a number never frees Lorenzo's
   price, rate or hours figure: a draft may use such a number only as a count
   with its noun ("25k emails"; see "Touch plan").
   Pricing and proof in
   a draft come only from `config/upwork_offers.md` (a separate file, so the cold-email gates that read `config/offers.md`, including the percentage gate under review, are unchanged).
7. **Committed fixtures use invented names only.** Real room data lives in
   `.tmp/` (gitignored) and never in tests, docs or the repo.

## How it runs (two halves, like `jobs/upwork_rooms.py`)

1. **Collect (Claude session with the Upwork MCP).** `python3 -m jobs.upwork_followup --print-collect`
   prints the exact read-only MCP calls. The session runs them and saves the raw
   responses as one JSON file, then runs
   `python3 -m jobs.upwork_followup --ingest <raw.json>`, which writes
   `.tmp/upwork_followup/snapshot.json`. Planned schedule: one morning run, 08:30 CT on weekdays, as
   a Claude desktop scheduled task that Lorenzo creates (persistent config is his
   action). Until then it runs by hand.
2. **Tick (plain Python, laptop).** `python3 -m jobs.upwork_followup --dry-run | --now`
   reads the snapshot and the store, advances each thread, drafts what is due,
   and emits cards. It makes no Upwork call of any kind.

Read-only MCP calls the collector makes (org_uid from `config/ids.json` `upwork.org_uid`):
- `upwork__get_messages` `list_rooms` (room_type ALL, page until `hasMore` is false, cap 10 pages)
- `upwork__get_messages` `list_messages` for each candidate room (the latest 30 messages)
- `upwork__list_freelancer_proposals` `list` for statuses Accepted, Activated and Offered (last 60 days), then `get_room` per proposal to link a proposal to its room
- `upwork__list_contracts` `search` (ACTIVE, CLOSED and PAUSED)
- `upwork__list_offers` `list_mine`

A candidate room is ONE_ON_ONE or INTERVIEW, not a support or system room, had
activity in the last 60 days, links to one of Lorenzo's proposals, and has never
had a contract (any `contractStatus`, including ENDED, means a past or current
client and is out of scope). `collect_calls.md` holds the confirmed call shapes.

## Data shapes (plain dicts, JSON-serialisable, ISO-8601 UTC timestamps)

### Snapshot (`.tmp/upwork_followup/snapshot.json`), written by `collect.py`

```
{
  "generated_at": "...", "source": "mcp", "sections": {"rooms": true, "messages": true,
     "proposals": true, "invitations": null, "contracts": true, "offers": true},   # invitations: not collected
  "truncated": false,
  "rooms": [RoomContext, ...]
}
```

`RoomContext`:
```
{
  "room_id": "room_<hex>",
  "client": "cleaned room name",
  "client_first_name": "first name if the room or job folder states it, else null",
  "room_type": "ONE_ON_ONE" | "INTERVIEW" | ...,
  "job_title": "...",
  "job_id": "~02... or null",
  "proposal_id": "... or null",
  "origin": "proposal" | "invitation" | "unknown",
  "contract": {"contract_id": "...", "status": "ACTIVE"|"CLOSED"|"PAUSED"} or null,
  "offer_state": "awaiting_your_acceptance" | "contract_started" | ... or null,
  "messages": [ {"id": "...", "side": "client"|"freelancer"|"unknown",
                 "at": "...", "text": "cleaned text, max 2000 chars"} ],   # oldest first
  "last_side": "client"|"freelancer"|"unknown",
  "last_message_at": "...",
  "job_folder": "<slug> or null",          # matched in Coding/upwork-pipeline/jobs
  "job": {                                   # null when no folder matched
     "post": "jd.txt job post, cleaned, max 6000 chars",
     "proposal": "proposal.md text with the preview line removed",
     "beats": ["Loom beat", ...],
     "ask_before_quoting": ["question", ...],   # from assessment.md, private
     "private_notes": "assessment.md Time/Likelihood/Standard pricing lines, private",
     "loom_url": "from proposals.csv or null",
     "applied_at": "from proposals.csv or null"
  }
}
```

Job-folder match order: the job id in `jd.txt`'s `url:` line equals `job_id`;
otherwise an exact case-insensitive title match; otherwise no match
(`job_folder: null`). Never guess.

### Thread (store key `upwork:<room_id>`), owned by `sequence.py`

```
{
  "room_id": "...", "client": "...", "status": ThreadStatus,
  "enrolled_at": "...", "enrolled_by": "auto" | "manual",
  "silence_started_at": "time of Lorenzo's latest message while the client has not answered",
  "touch_index": 0,                 # touches sent in the current silence (0..7)
  "cycles": 0,                      # completed silences (a client reply ends one)
  "pending": null | {"kind": "touch"|"reply", "touch": 1..7 or null, "issued_at": "...",
                     "text": "...", "card_id": "...", "resurfaced_at": null},
  "last_seen_message_id": "...",
  "history": [ {"at": "...", "event": "...", ...} ],   # capped at 50
  "stop_reason": null | "...", "follow_up_at": null | "YYYY-MM-DD",
  "ghl": {"contact_id": null, "opportunity_id": null, "stage": null}
}
```

`ThreadStatus`: `active` (a silence is running), `awaiting_lorenzo` (the client
wrote last: a reply card is out), `paused_not_now` (the client said later;
`follow_up_at` set), `won` (contract or accepted offer), `lost` (declined, hired
someone else, not interested, hostile), `closed_out` (T7 sent, no answer),
`dormant` (no client message for 60 days), `stopped` (Lorenzo stopped it),
`closed` (the room is blocked on Upwork; see the Field reference).

## Sequence rules (`sequence.py`, pure functions, no I/O except the store)

- **Enrolment.** A candidate room becomes a thread when it has a proposal,
  invitation or interview origin, no ACTIVE contract and no `contract_started`
  offer, and at least one client message. At the very first run, rooms whose
  last client message is older than 45 days are NOT auto-enrolled. They are
  listed as `revivable`, and `--enroll <room_id>` adds one.
- **Silence.** When the latest message is Lorenzo's (`last_side == freelancer`),
  a silence runs from that message. Touch N is due `GAPS[N]` days after the
  previous touch was sent (T1 counts from the start of the silence):
  `GAPS = {1: 2, 2: 2, 3: 3, 4: 4, 5: 5, 6: 7, 7: 7}`. That is days 2, 4, 7, 11,
  16, 23, 30.
- **Drafting.** At most one pending draft per thread. The tick drafts a touch
  only when it is due and nothing is pending. At most `MAX_NEW_DRAFTS_PER_RUN = 10`
  new drafts per run, oldest silence first.
- **Send detection.** On each run, a freelancer message newer than
  `pending.issued_at` counts as Lorenzo having sent the touch, even if he
  rewrote it. `touch_index` goes up by one and the silence clock is the time of
  that message. A pending draft that is not sent is resurfaced once after 3
  days. After 7 days it is dropped as `skipped`. For a touch, the next touch
  counts from the drop, and a skip does not advance `touch_index` past 7. A
  reply is drafted once more; if that one is dropped too, it waits visibly
  for Lorenzo (Field reference, "Reply expiry").
- **Client reply.** A client message newer than `last_seen_message_id` ends the
  silence (`cycles += 1`, `touch_index = 0`), withdraws any pending touch, and
  classifies the reply:
  - `positive` / `question` / `neutral` → `awaiting_lorenzo` plus a reply card;
  - `not_now` → `paused_not_now` (with `follow_up_at` from the text, else +30 days;
    one check-in draft on that date);
  - `declined` / `hired_other` / `not_interested` / `hostile` → `lost`, no more drafts;
  - `machine` (auto-reply, Upwork system text) → ignored. The rule-based
    pre-check marks `machine` only for a whole-message Upwork notice or an
    auto-reply at the start of the message. The phrase form starts (after at
    most one short greeting) with "This is an automated message / response /
    reply / notification", has no "?", no you/we/our/us words after the phrase,
    and either an absence cue (away, out of office, until, back Monday,
    vacation, will reply, unavailable, ...) or nothing else at all ("This is an
    automated notification."). The labelled form ("Auto-reply:", "Out of
    office:") needs an absence cue, no "?" and no you/we words. A client quoting the phrase goes to the
    model.

  Once Lorenzo answers, a new silence starts at touch 1. Cap: 3 cycles, then
  `closed_out` on the next silence's T7.
- **Won.** An ACTIVE contract or a `contract_started` offer on the room means `won`,
  and every pending draft is withdrawn.
- **Stops.** `--stop <room_id>` gives `stopped`. `--resume <room_id>` restores
  `active` with a fresh silence. After T7 is sent with no answer for 14 days:
  `closed_out`. No client message for 60 days: `dormant`.
- **Idempotent.** Running the tick twice on the same snapshot at the same time
  changes nothing the second time. The one exception is by design: drafts a
  run deferred (the per-run cap, or the tick's budget) may be reserved by a
  later run, including a same-time re-run. The tick's run lock prevents
  overlapping runs, so a same-time re-run is only a manual re-run after the
  first one finished. Store writes use `store.mutate` per thread key.
- **No store lock around a model call.** Every `store.mutate` callback is
  pure: no store call and no model call while a mutate is open.
  JsonFileStore's flock is not re-entrant, and `shared.llm.complete` writes
  its spend counter to the same store, so either would wait on the run's own
  lock forever. `run` therefore reads each thread without a lock, runs the
  room's step on that copy with the classifier, and then runs the same step
  inside the thread's `store.mutate` on those answers only. When the stored
  thread changed in between so that the write would read other client
  messages, it writes nothing and the room gets `room_deferred` (`reason`
  `new_messages` or `message_ids_changed`); the next run reads it again.

## Touch plan (`draft.py` + `prompts/`)

Every touch must add something new, never "just checking in":

1. **T1 (day 2), idea:** one concrete idea for their project, tied to a line in
   their post or the room, plus one easy question (it may borrow from
   `ask_before_quoting`).
2. **T2 (day 4), show:** point to the Loom or the demo already made for them
   (`loom_url`, `beats`). If there is no Loom, describe one specific piece of the
   build in two sentences.
3. **T3 (day 7), proof:** when a line in `config/upwork_offers.md` truly matches
   their vertical or problem, one short line that their project reminds Lorenzo
   of a past client with a very similar setup ("a contractor I worked with"),
   never naming the client and never repeating the line's figures or
   percentages, which the proposal already carried. A plain-words line on what
   was built for them, taken only from the proof line, is allowed. If none
   fits, a relevant insight instead.
4. **T4 (day 11), catch:** one risk or edge case in what they described that is
   easy to miss. It must be grounded in their post or messages, and must never
   invent a problem they did not state.
5. **T5 (day 16), easy reply:** a yes/no or pick-one question about scope or
   timing.
6. **T6 (day 23), next step:** a concrete low-effort next step: a 10-minute
   Upwork call with two time options (the next two weekdays at 12:00 and 15:00
   CT, written in words), or a small first milestone.
7. **T7 (day 30), close-out:** a graceful close that leaves the door open ("if
   you went another way, no worries").

**Reply drafts** (client wrote last): answer what they asked using only facts
from the room, the job post, the proposal and `config/upwork_offers.md`. Anything
unknown (price, date, scope detail) is left for Lorenzo on the card as
"Needs you: ...", never guessed.

**Figures** (every drafting prompt): money, percentages and proof come only
from `config/upwork_offers.md`, and a budget or price from any other block is
said in words. Any other number is used only exactly as the room, the job
post or the offers file gives it, never converted, rounded, combined or
re-labelled ("12 locations and about 40 techs" never becomes "12 techs"). This
rule is prompt-only: a gate check matching each number to its noun would
refuse good drafts that bring a small number of their own ("I'd test with 2
leads first"). The private figures never reach the model: `draft.py` replaces
every figure the gate's private_fact check would refuse (a money amount,
percentage, hours or review figure the private notes state, a number of 100
or more on a private pricing line, a rate whose number is on one) with
"(figure withheld)" in Lorenzo's own blocks (the proposal, the beats and the
touch history), and `ask_before_quoting` loses every money amount,
percentage, multiplier, hours figure and "k" figure ("25k emails" too). The
gate still checks the private notes.
The client's own figures are public. The title, the post and every room
message (whoever wrote it) are shown as written, and a figure they state is
matched on its value, so "approx 25k emails" also covers "25,000" and
"25000". That never frees Lorenzo's price, rate or hours figure (round 12):
a money amount, hours figure or rate from the private notes stays withheld
and refused however the client states it ("Sure, 400 a month works", "Yes,
about 6 hours"). A number on a private pricing line is freed only where the
text uses it as a count with its noun and the post or the room states it
("the 2,500 backlog", "2,500 in the backlog", "400 leads a month", "25k
emails", "a list of about 25k"). As a price it stays withheld and refused: a
money marker, a rate ("a month", "/mo", "per"), a time unit, a price word
("setup", "retainer", "fee", or a singular value noun: "a 2,500 project",
"your 2,500 figure") or no noun at all ("would be 2,500", "2,500 works",
"2,500 for the setup"). A percentage or review figure is freed when the post
or the room states it as the same kind. A figure only the private material
states stays withheld and refused.

## Copy gate (`copy_gate.py`)

A draft is refused (sent to "Needs edit" with reasons) when it breaks any rule
below.

**Characters and length**
- It contains em or en dashes, `!`, or any non-ASCII character (smart quotes are
  normalised first).
- It is longer than 900 characters (touches) or 1,500 (replies). Checks after
  the length check read only the first 4,000 characters; a longer draft is
  already too long.

**Content**
- It contains any off-platform contact: an email address, a phone number or
  handle; a URL other than `loom.com` or one already in the job post (booking,
  calendar, chat and `upwork.com` hosts are refused even from the post); a
  channel aimed at Lorenzo or the client ("I'll WhatsApp you", "my PayPal",
  "what's your email", "send me your Calendly link"); any question or request
  about the client's email, phone, number, cell or contact info, whatever the
  question word ("what number should I call", "is email ok?"), unless the
  project asks ("which email should I send the drip from"); Lorenzo sending
  through a channel or to the client's inbox or phone with no person named
  ("I'll write it up and email it tonight", "you'll have it in your inbox
  tonight", "text anytime"); an invoice, payment details or payment to Lorenzo
  outside Upwork milestones, whatever the rail; the project set up to reach the
  client for a test now ("I can have the bot text you so you can try it", "I'll
  add you to the WhatsApp test group"); leaving Upwork ("a direct chat", "skip
  the fee", "search my name", "outside of here", "elsewhere"); or a platform the
  post and client never name. A platform the post names may appear as the
  project's subject ("the bot sends the lead a text", "your Stripe webhooks").
  When the client's unanswered messages (those after Lorenzo's last message;
  the newest ten, at most 8,000 characters) ask to move contact, a call, files,
  a group or workspace, or payment off Upwork, or give a number, email address
  or handle to use, a draft of any kind is refused as `off_platform_contact`
  unless it keeps things on Upwork in so many words: Upwork, here or on here,
  this chat or this thread, an Upwork call, milestones or escrow ("here's",
  "here is", "Upwork's fees" and "off/outside/instead of Upwork" do not count).
  Words that go along with the client's own detail or ask ("that number", "I'll
  join", "I'll call you", "I'll add the group") refuse it even with a keep cue.
  The reason names only the request's category, never the client's words. A
  request Lorenzo already answered is not read, and the project's own talk (the
  bot, its users and staff, its events and schedules, an Upwork call, and a
  payment method in a payments job) is not a request.
  Payment asks include paying Lorenzo "another / some other / a different way"
  or "besides / instead of Upwork", Upwork's or the platform's cut or fees
  given as the reason (never a named third party's, such as Stripe or card
  fees), "rather not pay the fees", and the client offering or asking to send Lorenzo a transfer, wire,
  payment or check ("send you", "to your account", "can I just send a bank
  transfer?", "I'd rather send a wire", "easier if I send a wire to you
  directly"), on any schedule and for any purpose such as "to get started";
  never a plain habit with no modal and no "you" ("we send a wire every
  Friday, can the report show it?"), never when "to" names someone else ("a
  bank transfer to each supplier"), and never when Upwork, the platform or the
  project sends it ("Upwork will send you the payment"). "Through Upwork" or
  "milestones" keep payment on Upwork only when not refused, so "I'd rather
  not pay through Upwork" or "instead of milestones" does not, and refusing to
  pay through Upwork is itself a payment request. "Don't mind", "no problem" and
  "wouldn't it be" are not negations.
  Outside a payments job, a client message the narrow rules pass still counts
  as a payment request when a sentence ties a money word (pay, payment, paid,
  wire, transfer, check, cheque, cash, invoice, deposit, retainer, fee, or a
  named rail) to Lorenzo ("pay you", "your fee", "to you", "you take /
  accept", "mail / write / send you", "you ... get paid") or to Upwork
  ("through / via / on / than Upwork", Upwork's fees or cut, "Upwork takes
  20%", not "Upwork fees aside"). It does not count when the sentence keeps
  payment on Upwork, or when Upwork, the platform or the project moves the
  money ("Upwork will send the payment to you", "the bot can send you the
  invoice"). It never replaces a category the narrow rules found, and a false
  fire only makes the draft keep payment on Upwork. "Rather / prefer / easier
  / sooner ... than (go / pay) through Upwork" refuses Upwork; it is neither a
  keep nor a venue. A cheque counts like any rail: "mail / write / send you a
  check", "can I just mail a check?", "take / accept checks", "a check works /
  is fine", "by check", "who do I make the check out to?"; "check-in", "a
  check to see if" and "check your inbox" do not. On the draft side, Lorenzo
  taking a cheque, asking for one ("mail me a check", "make the check out to
  me") or giving a mailing address or wire details is refused, like "a bank
  transfer is fine". Outside a payments job, asking where or how the money
  goes also counts ("where should I send the money?", "how do you want the
  deposit?"; not "the payment data" or "the payment for the Twilio number"),
  and a draft in Lorenzo's voice that offers or accepts payment by any rail
  but Upwork is refused whether a client asked or not: bank transfer, wire,
  ACH, check or cheque, cash, Zelle, Venmo, PayPal, Wise, Cash App, crypto
  ("send a wire", "paying by check works", "cash works too", "a check is
  fine", "you can pay by Zelle", "once the wire clears I'll start"). The rail
  passes when the draft refuses it ("no wires or checks"), makes it the means
  of an Upwork payment ("fund the milestone with a bank transfer") or makes it
  the project's money ("customers who pay by check", "the bot logs each
  check", "do you take checks?", "check numbers"). Known residual: inside a
  payments job a rail can be the project's, so there a plain rail draft
  ("paying by check works") can still pass unless a client asked to move
  payment, and a where-or-how ask is not read.
  A "WhatsApp is easier" offer is a move unless the post names that platform;
  a bare "Zoom?" or "WhatsApp?" needs Upwork or a call or talk word in the
  same message. A phone number in a message that talks about a call or
  talking is a call request.
  While a client's request to move off Upwork is unanswered, every draft
  (reply, check-in or touch) is refused as off_platform_contact unless it
  keeps that request's category on Upwork in so many words, whatever it opens
  with. Payment: Upwork tied to the payment ("paying through Upwork", "Upwork
  milestones"), milestones that do not list the work's phases, escrow, "pay
  here" or "keep payment here". Call: an Upwork call, "a call here", "on here",
  "here on Upwork", or "let's do it / meet / talk on Upwork". Contact, files,
  details and group: "here" or "this chat" as where the talk or the files go
  ("keep / stay / attach / send / reply / post ... here"), Upwork messages, or
  an Upwork call. Any category: a keep of everything ("keep things here",
  "let's stay on Upwork"). A keep cue for another category does not count, and
  neither do a filler "here" ("flag here", "help here"), an extra copy ("a
  summary here too"), "here's" or "Upwork's fees". An opening yes ("Sure",
  "Works for me") only labels the reason. The refusal reason says how that
  category stays on Upwork.
  A group or channel with a stated purpose ("for updates") is Lorenzo's own
  unless the sentence names the project (its actor, a project tool or a
  per-item stream such as "each status change"), or the post or client asks
  for that group as the deliverable; either makes it the project's with or
  without a team word. The reply prompt also says to decline without
  naming the other channel or "outside Upwork" and to say what Lorenzo will do
  on Upwork.
  Also refused, with no channel word: asking where or how to reach the client
  ("where should I send the scope?", "what's the best way to reach you?")
  unless the project routes it (the project's own sender, messages, users or
  tools); "there" pointing at a channel a client message named ("just message
  me there", "see you there"); and a group Lorenzo sets up for himself and the
  client ("a shared WhatsApp group for updates"). The drip, campaign and
  sequence count as the project. The reply prompt tells the model to keep a
  client's request to move off Upwork on Upwork and offer the Upwork
  alternative: Upwork messages, an Upwork call or milestones. The check works
  clause by clause on channel plus direction; see the `copy_gate.py` docstring,
  "Off-platform concepts".
- It contains any `$` figure or percentage not in `config/upwork_offers.md`.
  A "k" figure before a count noun ("approx 25k emails", "a 25k list", "a
  list of about 25k") is a volume, like "300 leads", not money; "a 25k
  budget", "for 25k", "25k a month" and "would be 25k" are money. A bare
  number quoted as a price is refused too, private notes or not: "call it
  2,400", "Setup would be 2,500", "2,500 for the setup", "400 a month works".
- It agrees to or accepts a price the client proposed (`agrees_to_client_price`,
  round 13, probe p49), private notes or not: agreeing to a price is
  Lorenzo's call. The client states N as a price when the post, the title or
  a client message has it as money (a currency marker, "2k"), with a price
  word near it (price, budget, pay, rate, cost, quote, fixed, fee, "work
  for"), in a price position ("for 2,000") or in a question that proposes it
  ("Would 2,000 work for the whole build?", "How about 2,000?"). The draft is
  refused when it takes that value up, in any form the figure parser reads
  ("2,000", "2000", "2k", "$2,000"), in an agreeing form: "2,000 works", "2,000
  is fine / good / ok", "2,000 sounds good", "happy with 2,000", "2,000 it
  is", "can do 2,000", "2,000 for the build works", "2,000 for everything
  works", "2,000 for all of it is fine", "deal at 2,000", "Sure,
  2,000.". A count with its noun ("the 2,000 contacts") passes, and a number
  the client used only as a volume ("2,000 emails a week") is not a price, so
  "2,000 works" passes there. Asking back ("Does 2,000 work for you?") and
  arithmetic are not agreement, and only "works out to" is arithmetic ("2,000
  works out to about 100 a day" passes; "2,000 works out fine / great / well"
  and "that should work out fine" are refused). Round 14 adds "(I can)
  work with 2,000", "2,000 should / would / will cover it", "2,000 sounds
  about right", "2,000 is about right" and "2,000 is reasonable / doable /
  workable". It also refuses agreement with no figure, under the same code,
  only when all three hold: (1) the client's latest message proposes a price
  (a client price value in a question such as "would 2,000 work", "how about
  2,000", "can you do it for 2,000", "is 2,000 ok", or a statement such as
  "our budget is 2,000", "I can pay 2,000", "we can do 2,000", "2,000 is our
  max"); (2) the draft's opening sentence, after any greeting or thanks-only
  sentence, agrees without the number: "that / this / it / that budget / the
  price works", "... is fine / fair / reasonable / about right", "... should
  cover it", "sounds good", "deal", "agreed", "happy with that", "I can work
  with that", "let's do it.", a bare "yes." / "sure." / "sure thing.", or
  (round 15) a whole "Works." / "Works for me." sentence; (3) the time in that
  sentence, if any, is not what the agreement refers to, and no sentence of
  the draft defers the price ("I'll confirm the price with you on a call",
  "let me come back to you on the number"). Round 15 narrowed the time
  exemption: "Thursday works for a quick call", "Monday works for me to
  start" (the time is the subject) and "That works for Thursday at 2pm" (the
  time follows the agreeing words) pass, while "Sure, that works, talk
  Thursday." (the time sits in a separate clause) is refused. "N is our max /
  maximum / ceiling / cap", "our max is N" and "a max of N" state N as a
  client price (round 15), but a count with its noun stays a count ("our max
  is 20 domains"). Round 16: when the client's latest message proposes a
  price, ANY clause of any sentence that is not a question and has the price
  itself as its subject in an agreeing form is refused too, with no time
  exemption: "the / your / that price", "the / your / that budget", "the /
  your / that number", "the / your rate", "the / your / that fee", "the /
  your / that figure", "the amount" plus "works (for me)", "would / should
  / will work" (not "works out to", the only arithmetic form: "The budget
  works out to about 100 a day of build time." passes, while "The price works
  out fine for me." is refused), "is fine / good / ok / fair /
  reasonable / doable / workable / acceptable / about right / enough / no
  problem", "sounds good / fine / about right" or "should / would / will
  cover it" ("That works for Thursday at 2pm, and the price is fine.",
  "Thursday works for a quick call. Your budget works for me too."). A
  deferral anywhere still wins; questions ("Does that budget work for
  you?"), negations ("the price is not fine") and other predicates ("the
  price depends on the scope", "I'll send the price after the call") pass.
  A draft answering a count or scope ("Yes, I can do 20
  domains") or not responding to the price passes. The client
  text read for prices is capped at 20,000 characters (post and title first,
  then client messages newest first; `CLIENT_PRICE_CHARS`). The retry message
  says not to agree to or accept a price and to leave pricing to Lorenzo.
- It contains any pricing, likelihood or review fact from `private_notes` or
  the client intel. A private price, rate or hours figure is refused even
  when the room states the same number; a number on a private pricing line
  passes only as a count with its noun that the post or the room states, and
  a percentage or review figure only when they state it as the same kind (see
  "Touch plan", Figures).
- It has a placeholder (`[`, `{{`, `TODO`, `TBD`, `XX`) or the
  "(figure withheld)" marker.
- It is a first-name greeting when `client_first_name` is null.

**Tone and voice**
- It is not first person singular. "We" is allowed only when quoting the client.
- It contains "just checking in", "circling back", "bumping this", "touching
  base", "following up on ..." or a stock follow-up line in Lorenzo's own voice,
  unless another subject comes right before the phrase in the same clause.

The AI and automation word ban from the cold-email gate does NOT apply, because
Upwork clients post automation jobs.

## Cards (`tick.py`)

Each new draft produces one `shared.notify` card:
- **Title:** `Upwork T<N> for <client>`, `Upwork reply for <client>` or
  `Upwork check-in for <client>`. On a public ntfy topic (no `NTFY_TOKEN`, no
  `NTFY_ALLOW_SENSITIVE`) the push title and body carry nothing client-derived
  and no local path: the title is `Upwork: 1 new draft (T<N>)` (or `(reply)`,
  `(check-in)`), and the full card below, headed by the client-named title,
  goes only on the email leg (as `jobs/upwork_rooms.py` does).
- **Body:**
  - the draft text, ready to copy;
  - a line `Open room: https://www.upwork.com/ab/messages/rooms/<room_id>` (verify
    this URL shape on first live use);
  - a "For you, not the client" block with the job title, applied date, the
    thread's touch history, and the `private_notes` lines;
  - for replies, any "Needs you" items.
- **Buttons:** none. Sending is detected automatically on the next run.

Every run also writes the same drafts to
`.tmp/upwork_followup/drafts_<YYYY-MM-DD>.md`, so Lorenzo can copy from a file,
and writes one `log_run("upwork_followup", status, details)` Job_Log row with
counts: enrolled, drafted, sent_detected, replies, won, lost, skipped, errors.

The batch also has "Needs you" (every thread with `due_summary` kind
`reply_skipped`, on every run until Lorenzo acts) and, once per block,
"Blocked on Upwork (no drafts)" (every snapshot room with `blocked`, enrolled
or not). sequence.py's `needs_review` `reply_skipped` and `room_blocked` for
those rooms show there instead of under "Check these". Either section makes
the run `attention`. A public push carries only their counts; a snapshot OS
error appears there as "unreadable (OSError)", its text only in the email leg
and Job_Log.

## GHL mirror (`ghl_sync.py`, shadow via `guard_write`)

- **Contact.** One contact per thread, tagged `upwork`, name = client. Upwork
  gives no client email, so `shared/ghl.py` `upsert_contact` gains an optional
  email (the change is additive and existing callers are unchanged). Until a
  sandbox test proves GHL accepts a contact with no email or phone, the live
  path refuses and logs `ghl_contact_needs_identity`.
- **Opportunity.** An opportunity named `<client> (Upwork)` sits in the Sales
  pipeline, with stages mapped as follows:
  - a room with a client message goes to `new_reply`;
  - an offer received (`awaiting_your_acceptance`) goes to `proposal_sent`;
  - `won` goes to `won`;
  - `lost`, `closed_out` or `dormant` go to `lost`;
  - `paused_not_now` goes to `follow_up_later`.

## CLI (`jobs/upwork_followup.py`)

`--print-collect`, `--ingest <raw.json>`, `--dry-run` (the default; runs on a
copy of the store with no model call, writes only the local drafts file and
the Job_Log row), `--run` / `--now` (the real tick: drafts, store, GHL mirror,
cards; one run at a time, within the per-run spend cap), `--status`,
`--stage <room_id|fragment> <stage>`, `--stop <room_id|fragment>`,
`--resume <room_id|fragment>`, `--enroll <room_id|fragment>`, plus
`--as-of <ISO>`, `--snapshot <path>` and `--json`. A fragment matches the client
name or the job title; no match or several changes nothing. `--json` prints the
tick result as one JSON document on stdout for every outcome, a run skipped for
the lock included (the token note goes to stderr). `--as-of` never reaches the
run lease. `--status` says "blocked on Upwork since <date>" for a room the
snapshot shows blocked (a blocked room with no thread gets a row, status "not
enrolled") or, for a room not in the snapshot, a thread closed as
`room_blocked` (dated by `marks.blocked_at`); the closed line
(`tick.CLOSED_TEXT`) for a closed thread whose room is open again; and "reply
skipped on <date>; client waiting since <date>" for `due_summary` kind
`reply_skipped`.

## Module layout

```
services/upwork_followup/
  __init__.py
  DESIGN.md            (this file)
  collect.py           U1  ingest raw MCP responses + job-folder linking -> snapshot
  collect_calls.md     U1  the exact MCP calls for the session (printed by --print-collect)
  sequence.py          U2  thread state machine, due logic, send detection, stops
  classify.py          U3  client-reply classifier (shared.llm classify/escalate)
  draft.py             U3  touch and reply drafting (shared.llm draft)
  copy_gate.py         U3  the rules above
  prompts/             U3  touch_t1..t7.md, reply.md, classify.md
  tick.py              U4  orchestration, cards, drafts file, Job_Log
  ghl_sync.py          U4  GHL mirror (shadow)
  tests/               each piece adds its own test file
jobs/upwork_followup.py   U4  CLI
config/upwork_offers.md   U3  new file: proof lines from Coding/upwork-pipeline/templates/ps-case-studies.md, verbatim; no pricing until Lorenzo adds it
shared/ghl.py             U4  optional email on upsert_contact (additive)
runbooks/upwork_followup.md  U5
```

## Stages (Lorenzo controls; added 2026-09-22)

Each thread carries `"stage"` using the same stage keys as the cold-email Sales
pipeline (`config/ids.json` `pipelines.sales`):

| stage | drafts? | set by |
| --- | --- | --- |
| `new_reply` | yes | auto on enrolment (the client opened a chat on his proposal) |
| `proposal_sent` | yes | Lorenzo, or auto when an offer to him is `awaiting_your_acceptance` |
| `call_booked` | no | Lorenzo |
| `follow_up_later` | no, until `follow_up_at` arrives; then one check-in draft and the stage returns to `new_reply` | Lorenzo, or auto on a `not_now` reply |
| `won` | no | auto on an ACTIVE contract or a `contract_started` offer, or Lorenzo |
| `lost` | no | Lorenzo, or auto on declined, hired_other, not_interested, hostile, closed_out, dormant or a blocked room |

Rules:
- **Lorenzo's move wins.** A stage he sets (`stage_set_by: "lorenzo"`) is never
  changed by the engine, with one exception: `won` from a real contract.
  Automatic moves never override his.
- **Moving a stage.** Lorenzo moves a stage with
  `python3 -m jobs.upwork_followup --stage <room_id|job title fragment> <stage>`,
  or later in GHL. When the GHL mirror is live, a stage change he makes on the
  GHL opportunity is read back each run and wins, the same as a CLI move. If
  he moves a card both ways before a run, GHL's move is kept and the batch
  says so (see "A GHL move is never overwritten").
- **Leaving a drafting stage.** When a thread moves into a non-drafting stage,
  any pending draft is withdrawn.
- **Order within one run.** The engine moves stages in the same order on every
  run:
  1. won;
  2. a blocked room;
  3. client messages;
  4. close-out or dormant;
  5. the check-in return (`follow_up_later` to `new_reply`);
  6. the offer promotion (`new_reply` to `proposal_sent`).

  No later step re-opens an earlier one, so a second run at the same time
  moves nothing. A check-in that comes due while an offer awaits acceptance
  ends its run in `proposal_sent`.
- **Morning batch.** The batch groups jobs by stage and shows each job's stage
  so he can re-stage from it.

Thread fields added: `"stage"`, `"stage_set_by": "engine" | "lorenzo" | "ghl"`,
`"stage_changed_at"`.

## GHL pipeline for Upwork (revised 2026-09-22 after the U4a review)

Upwork jobs do NOT share the cold-email Sales pipeline. An Upwork contact has
no email, and `pipeline_sync.run_sync` blocks the whole nightly reverse check
while any Sales opportunity has no email (`opportunities_without_email`), which
would stop the cold-email engine from creating opportunities for new positive
leads. Sharing the pipeline would also mix Upwork into the cold-email metrics,
retro and scorecard counts.

The new setup:
- **A separate pipeline.** Upwork gets its own GHL pipeline, "Upwork", with the
  same six stage keys (`new_reply`, `proposal_sent`, `call_booked`,
  `follow_up_later`, `won`, `lost`), configured as
  `config/ids.json` → `pipelines.upwork {id, stages{key: id}}`.
- **Lorenzo creates it.** He creates the pipeline in the GHL UI (a
  change-account-settings action, so it's his), then its ids are filled in.
- **Until it's configured, the mirror is off.** The GHL mirror for Upwork is
  disabled, with no writes and no read-back. Stages live in the local store and
  move by CLI. The tick reports one `ghl_not_configured` note per run, not per
  thread.
- **The mirror only follows `thread["stage"]`.** An engine `ghl_stage` action
  that disagrees with the thread is an error entry, never a write.
  `thread["ghl"]["stage"]` means "the stage GHL is known to hold". It advances
  only on a confirmed live write, or on a shadow placeholder id.
- **A write GHL did not apply is rejected.** A stage PUT answered 2xx whose
  answer shows a different stage, status or pipeline is `ghl_write_rejected`:
  the known stage does not advance and the next run tries again.
- **A GHL move is never overwritten.** The one exception is `won` from a real
  contract. When the read-back replaces a stage Lorenzo set (`--stage` or
  `--resume`) with a GHL move, the morning batch prints a "Stage override" line
  naming his stage, GHL's stage and the room, and tells him to run `--stage`
  again if he meant it. The email summary carries the same line without the
  client name, the public ntfy only a count, Job_Log records
  `stage_overrides`, and the run status becomes `attention`.
- **A GHL status decides the stage.** A `won` or `lost` status reads back as that stage whatever the column, and `abandoned` (Lorenzo dropped the deal) reads back as `lost`, so a later push never reopens it as `open`.

## Field reference as built (2026-09-23; binding)

### Snapshot keys added by `collect.py`
- **`generated_at`**: the envelope's `collected_at` in UTC, never the ingest time. The ingest refuses a `collected_at` more than `collect.MAX_CLOCK_DRIFT` (10 minutes) after its own clock. An old one is kept as it is, so the tick's STALE warning fires on a re-ingested old file.
- **`omitted_unlinked`** (int): candidate rooms (see `contracted_rooms`) with no linked proposal.
- **`omitted_contracted`** (int): candidate rooms dropped because they have a contract id; always `len(contracted_rooms)`.
- **`contracted_rooms`** (`[{room_id, contract_id, status, proposal_id}]`): candidate rooms with any contract id (ENDED included). A candidate passed the room-type check (ONE_ON_ONE, INTERVIEW or no type stated), the support/system check and the 60-day activity check; a live thread's room skips only the age check. A contracted room that fails one of those checks (a GROUP or support room, or one quiet for 60 days that is not a live thread) is not listed. Listed rooms are left out of `rooms`. `sequence.run` marks an enrolled thread listed here as `won`: an engine move that overrides every stage and withdraws the pending draft.
- **`missing_messages`**: a sorted list of room_id strings for rooms whose messages weren't pulled (or were only partly pulled). Each such room also has `messages: null`, and sequence freezes those rooms individually. `sections.messages` is informational only.
- **`truncated_sections`**: what may be incomplete. `truncated` is true whenever it is non-empty, and the batch warns. Values: `rooms`, `proposals`, `messages`, `contracts`, `offers` (a cap was hit, or a last page said hasMore), `unrecognised_cap` (a `caps_hit` name the code does not know) and `live_threads` (an envelope entry was not as printed, so a live room may be missing).
- **`link_errors`**: diagnostics.
- **`live_threads`** (`[{room_id, proposal_id}]`): rooms the session must always read, whatever their age. Copied from `--print-collect` into the envelope, where the key is required: missing or not a list is refused. An entry that is not as printed (not an object, a room id that is not a `room_...` string, or a proposal id that is missing or not a string, integer or null) is skipped, or kept without its proposal link when only the proposal id is bad, and adds `live_threads` to `truncated_sections`.
- **Message `event: true`**: an Upwork room event, in one of two whole-line forms: the bold `**Name** ended the contract` form, or an MCP system-event line (below). It carries `side: "unknown"` and is ignored by every sequence decision. It never sets `last_side`, and the latest non-event message sets `last_message_at`. It stays in `messages` in its time order.
- **Message `event_name`** (string, present only on MCP system-event messages): the Upwork MCP writes some room events as a node sent "from" Lorenzo (`from_self: true`, `from_side: "freelancer"`), e.g. `System event: blocked. View this conversation on upwork.com for full context.` A message is one when its node is on Lorenzo's side (`collect.message_side` gives `freelancer`) and its cleaned text (wrapper stripped once, HTML entities and markdown escapes undone, newlines collapsed, the same decoding as every message), stripped, matches `^(?i:system event): ([A-Za-z0-9 _-]{1,40})\. View this conversation on upwork\.com for full context\.?$` (`collect.mcp_event_name`). Only "System event" is case-insensitive; the rest of the sentence is exact. `event_name` is the captured name, stripped, lowercased, each run of spaces as one `_` (`blocked`, `unblocked`, `contract_ended`). A bold-form event has no `event_name` key. A client-side or unknown-side copy of the line (a client typing it, or a node with no side fields) is an ordinary message: `event: false`, no `event_name`, its own side, and it sets `last_side` like any other message, so it can never block the room. The room card's `latestStory` follows the same rule: the line blanks the card's side only when the story's own side fields, or else the card's last-message side, say freelancer. Messages with the same timestamp keep the newest-first input order of `list_messages` (the one listed first is the newer).
- **Room `blocked`** (bool, on every room) and **`blocked_at`** (ISO or null): `blocked` is true when the room's newest named system event (by time) has `event_name == "blocked"` and no non-event message comes after it; `blocked_at` is that event's time (null only if its time was unreadable). A later human message from either side, or a later named event such as `unblocked` or `archived`, makes it false: the chat is evidently open again. A bold-form event neither sets nor clears it. Only the messages decide, so a room with `messages: null` is `blocked: false`. Only the name `blocked` sets the flag.
- **`blocked_rooms`**: a sorted list of the room ids in `rooms` with `blocked: true`. Blocked rooms do not appear in `list_rooms`; they are found only through `get_room`.

### Thread fields added by `sequence.py`
- **Stage:** `stage`, `stage_set_by` (`engine` | `lorenzo` | `ghl`), `stage_changed_at`.
- **Links:** `proposal_id` (and `job_id` when known), stored on enrolment so `collect.live_threads()` can re-link a live thread after its room ages out of the 60-day window.
- **`follow_up_at`:** a Central-time date.
- **`marks`** (internal): `initialized`, `last_seen_at`, `last_client_at`, `client_waiting`, `reply_target`, `reply_for`, `checkin_for`, `review_for`, `hold`, `messages_missing`, `dormant_floor`, `not_in_pull_at`, `reply_skipped` (`{message_id, count, at}`: how many reply drafts for that client message were dropped unsent, and when the last one was), `blocked_at` (the block that closed the thread), `pre_block` (`{status, stop_reason, stage, set_by}`: the thread as the block found it).
- **Status `closed`** (`stop_reason: "room_blocked"`): the room is blocked on Upwork (`room["blocked"]`, or its id in `blocked_rooms`).
  - On first sight the run keeps the thread's status, stop reason, stage and setter in `marks.pre_block`. It then withdraws the pending draft (reason `room_blocked`), sets `closed`, keeps the block time in `marks.blocked_at`, and moves the stage to `lost` (engine). A stage Lorenzo or GHL set is kept instead.
  - It adds one `needs_review` `room_blocked` with `blocked_at`, `stage`, `set_by` and `stage_kept`, once per block.
  - While the room stays blocked, nothing moves: no message is read, no ladder step runs and no draft is made.
  - A room that is not enrolled is never enrolled while blocked (`eligible` returns `blocked`), not even by `--enroll`.
  - Once the room is open again, only a real (non-machine) client message written after `blocked_at` reopens the thread, and it takes the path its `pre_block` status would have taken without the block. First the stage the block moved to `lost` comes back (engine, reason `room_unblocked`), with the stop reason. Then:
    - `stopped` stays stopped (`client_message_while_stopped`).
    - `lost` stays lost (`client_wrote_after_lost`, `client_message_while_lost`).
    - Any other status takes the normal client-message path from `closed`, so a reply label makes it `awaiting_lorenzo` with a reply draft, and `client_reply` is the silence boundary.
  - With no such message the thread stays closed until Lorenzo runs `--resume`, or `--stage` with a stage that changes the status: a drafting stage (`new_reply`, `proposal_sent`) reopens it as `--resume` does, `follow_up_later` pauses it (`paused_not_now`), and `lost` or `won` sets that status. `--stage call_booked` leaves it closed, and so does `--stage` to the stage it already has (except `--stage lost` on the `lost` the block set, below). If the room is still blocked after a `--resume` or a drafting stage, the next run closes it again and flags it again.
  - `--stop`, `--stage lost` or `--stage follow_up_later` on a closed thread sticks. If the room is still blocked, the next run closes it again with that decision as the `pre_block` status (a stop keeps the stage the first close replaced), and adds no second `room_blocked` review for the same block. `--stage lost` on the stage the block itself moved to `lost` still sets status `lost`.
- **Pending:** `kind` is `touch` | `reply` | `checkin`. A reservation is a pending whose `text` and `card_id` are null. `record_pending` fills an existing reservation only, and raises `PendingRefused` (`no_reservation` | `reservation_mismatch` | `stage_not_drafting` | `status_not_live`) otherwise. Known gap, left as is: `clear_pending(retry=False)` on a check-in is never redrafted, so the thread stays `paused_not_now` with nothing due until it goes dormant (nothing calls it that way today; tick.py releases with `retry=True`).
- **Reply expiry.** A reply draft left unsent for 7 CT days is dropped (`withdrawn`, reason `skipped`) and, the first time for that client message, drafted again in the same run (`reply_skipped`, `redraft: true`). The second expiry is not redrafted. The run adds `needs_review` `reply_skipped` once, and from then on `due_summary` returns kind `reply_skipped` with `skipped_at` (the drop) and `waiting_since` (the client's message). This lasts until Lorenzo answers in the room, runs `--resume` (asks for the reply again, `reply_resumed`), stops it or moves it, or the client writes again, or until the 60-day dormant rule ends it: with no client message for 60 CT days the thread goes `dormant`, and its stage goes to `lost` unless Lorenzo or GHL set the stage. `clear_pending(retry=False)` on a reply is an explicit skip, so no redraft. `clear_pending(retry=True)` (the draft failed or the run budget ran out) drafts it again on the next run.
- **History events.** Each is `{"at", "event", ...fields}`, capped at 50 per thread. A test fails when `sequence.py` writes an event this list does not name.
  - Sent. `at` is the time of Lorenzo's message, and `text` is his message or else the draft text, capped at 600.
    - `touch_sent {message_id, touch, text}`.
    - `reply_sent {message_id, text}`, plus `manual: true` when he answered by hand with no draft out.
    - `checkin_sent {message_id, text}`.
    - `manual_message {message_id, text}`: he wrote during a running silence with no draft out. It is not a counted touch, and the silence restarts from it.
  - Client side. `at` is the run time.
    - `client_reply {message_id, label}`: a classified client message on a live, closed-out, dormant or closed (blocked, now open again) thread.
    - `silence_ended {cycles, message_id}`: that client message ended a running silence, and `cycles` is the new count. It is written for a reply on an `active` thread, and for a message on a `stopped` or `lost` thread whose silence was still running.
    - `client_message_while_stopped {message_id, label}` / `client_message_while_lost {message_id, label}`: a client message on a stopped or lost thread. It is classified only to drop machine text; the label moves nothing. The message becomes the reply target, so `--resume` or a move back to a drafting stage answers it.
    - `machine_ignored {message_id}`: every message in the client's burst was machine text.
  - Status, stage and links.
    - `status {to, reason}`: every status change.
    - `stage {to, by, reason}`: every stage move.
    - `enrolled {by}`.
    - `room_blocked {blocked_at}`: first sight of the room blocked (see Status `closed`). `at` is the run time; `blocked_at` is the room's, or null.
    - `proposal_id_changed` / `job_id_changed {old, new}`.
  - Drafts.
    - `draft_reserved {kind, touch}`.
    - `drafted {kind, touch, card_id}`: `record_pending` filled the reservation.
    - `reservation_released {kind, touch}`: a reservation an earlier run never filled.
    - `resurfaced {kind, touch}`.
    - `withdrawn {reason, kind, touch}`.
    - `reply_skipped {message_id, count, redraft}`: see Reply expiry. `count` is how many reply drafts for that message were dropped.
    - `reply_resumed {message_id}`.
  - Reviews.
    - `needs_review {reason}` (`unknown_last_message`, `messages_missing`, `not_in_pull`).
    - `messages_back`.
  - **Silence boundaries** (draft.py `SILENCE_BOUNDARIES` and `_is_boundary`). The prompt's "touches already sent in the current silence" line counts only the `touch_sent` entries after the latest boundary. A boundary is `client_reply`, `silence_ended`, `reply_sent`, `checkin_sent`, or `status` with `to: active` and any `reason` except `touch_sent` (a resume, a re-stage, a skipped check-in, a sent reply or check-in, or Lorenzo answering by hand). A client message on a stopped or lost thread writes `silence_ended` when a silence was running, so a resume into `awaiting_lorenzo` never lists the old touches as current.
- **`ghl`:** owned by `ghl_sync.py`. `ghl.stage` is the stage GHL is known to hold. `ghl.blocked` is set after a live create returned no id.
- **Written by `tick.py`:** `draft_meta` (card id, problems, needs_you, proposes_call, `card_sent_at`), `job_title`, and `draft_claim` (`{token, kind, touch, issued_at}`: the `--run` filling that reservation; stamped in the same write that reserves it, dropped when the draft is recorded or the reservation released). The tick records a draft only into a reservation that carries its own claim, checked before `record_pending` inside the same `store.mutate`; a run that lost its lease gives back only reservations with its claim.

### Other store keys
- **`upwork_meta`** (NOT under the `upwork:` prefix): `{first_run_at, revivable: {room_id: {listed_at, last_client_at, client, job_title}}}`. A legacy `upwork:meta` is migrated.
- **`upwork_followup:tick`**: `summary_fingerprint` and `summary_at` (the last summary card), and `blocked_listed` (`{room_id: {blocked_at, listed_at}}`: blocked rooms a `--run` batch already listed; a room the pull shows open again is dropped, so a new block is listed again).
- **`upwork_followup:lock`**: the `--run` lease, on the real clock only (never `--as-of`). Held: `{owner, acquired_at, heartbeat_at, expires_at, beats, pid, as_of}`, plus `clock_suspect_at` once a blocked run saw its stamp more than `LOCK_DRIFT_MINUTES` (2) ahead of its own clock. Released: `{owner: null, released_at, released_by}`. It is live until the earliest of `expires_at`, the newest stamp + `LOCK_TTL_MINUTES` (30), and, for a stamp from the future, the checking run's clock + TTL and `clock_suspect_at` + TTL (so a skewed lease blocks one TTL at most from the first run it blocks). The holder renews it (`expires_at` = now + TTL) before every model call (each classify and escalate call as well as each draft call), every store write (each draft record included) and every card; a renewal, a store read or a classifier call made while one of the run's mutates is open raises `NestedStoreCall` instead of waiting on the store's lock. Every lease write is a compare-and-set on `owner` inside `store.mutate` (else `compare_and_set`, else a write and a re-read, see `tick._lease_write`). A renewal that finds another owner or no lease stops the run: `lock_lost` in the result, the batch and Job_Log, no model call, record or card after that point.

### Day rules
Every day-based rule counts America/Chicago calendar days from 00:00 CT, so a day-N rule is ready for the day-N 08:30 batch. This covers touch gaps, resurface, skip, close-out, dormant, revivable age, `follow_up_at` and the not-in-pull week.

### Classifier
- Only `label` drives the state machine.
- A low-confidence, stage-changing read, `machine` included, comes back as `label: neutral` plus `raw_label`, and the run adds `needs_review` `low_confidence`.
- When Lorenzo or GHL set a drafting stage, a lost or not_now label never stops drafting (`needs_review` `stage_kept`).
- It runs outside every store lock: `sequence.run` asks it in the unlocked pass, and the write replays those answers (see "No store lock around a model call"). On a `--run` each model call it makes goes through the tick's Meter: counted against the run budget and the classifier cap, and preceded by a lease renewal.
- A refusal at the shared LLM ceiling (`LLMBudgetExceeded`) gives no fallback `neutral`: the message stays unread for the next run, and the run makes no further model call. The ceiling's counter is the laptop store's `llm.spend_usd`, separate from the Modal reply engine's.

### Review reasons
`needs_review` reasons: `unknown_last_message`, `messages_missing`, `client_wrote_after_lost`, `unrecognised_label`, `low_confidence`, `stage_kept`, `not_in_pull`, `reply_skipped`, `room_blocked`. An `error` action carries `BadRecord` or `MetaUnavailable`. A `room_deferred` action (`reason`, `detail`) is not a review: the room was left for the next run. The tick counts it (`room_deferred`), adds one note without room ids to the batch and the summary, and lists the rooms in Job_Log (`deferred_rooms`).
