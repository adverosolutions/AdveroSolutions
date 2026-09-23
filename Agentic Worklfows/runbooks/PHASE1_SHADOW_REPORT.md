# Phase 1 sales engine: what exists, what it would have done, and what it needs from you

> **Historical snapshot, not current status.** This describes the Phase 1 sales engine as it stood in
> the early morning of 2026-09-22, before Phases 2 to 4 and before the re-review. It is not kept up to
> date. For current status read `MASTER_BUILD_REPORT.md`; for the go-live order read
> `GO_LIVE_CHECKLIST.md`; for the re-review findings read `REREVIEW_2026-09-22.md`. Leads are named
> by role (Lead A, B, C), not by name.

Written 2026-09-22, revised the same day after a completeness review. The engine ran in shadow mode,
apart from the evidence runs that set the live flags inside their own process (item 5 of section 4a
below). Through Instantly and GHL, nothing was sent, booked, paused, moved or deployed to a lead,
client or third party: shadow mode intercepts every write, and the evidence runs that set live mode
used mocked Instantly and GHL transports. So no calendar event was created and no Instantly or GHL
record changed. That does not cover notifications. 9 `notify.push_email` rows were written in live
mode, and whether they emailed Lorenzo or pushed to the ntfy topic is not proven (items 2 and 3 of
"What went wrong overnight" in `MASTER_BUILD_REPORT.md`).

**Correction (2026-09-22): "no email left the building" was not true of the test suite.** Every full
`pytest` run sent one real message from Lorenzo's own Gmail to himself, subject "Pipeline sweep: 1
waiting on you", because a test that turns `NOTIFY=on` patched only the ntfy leg while the parent
`.env` supplied real SMTP credentials. That email went only to Lorenzo. Two evidence runs may also
have pushed to the ntfy topic, which cannot be confirmed (item 2 of "What went wrong overnight" in
`MASTER_BUILD_REPORT.md`). The SMTP leak is fixed and the suite
now runs with zero SMTP connections; see "What went wrong overnight" in `MASTER_BUILD_REPORT.md`.

Read this in order. Section 8 is the list of things only you could unblock at the time, and section 7
now points to the go-live checklist. **Section 9 is what was still not built**.

> **What changed in the revision.** A review pass found that two of the thirteen integration fixes had
> closed only half of their problem, and that three things would have made the 48-hour watch produce
> nothing useful even if it ran. All of them are closed; section 4a lists them with the evidence. The
> short version: the engine's own "Locked in for ..." confirmation was still armed at classification
> time and would have reached the prospect ahead of your approval tap; a veto cancelled the calendar
> event but left the whole follow-up ladder running; every Approve link would have pointed at
> `localhost` for 48 hours; four switches the runbooks tell you to flip could not be flipped in the
> deployed container; and the `Job_Log` you are told to read as the gate already held 48 `mode=live`
> rows from evidence runs.

---

## 1. What exists now

Six components, built separately, reviewed three ways each, fixed, and then joined into one system.

| Area | What it does | Source files | Lines | Tests |
|---|---|---|---|---|
| `shared/` | One library everything imports: Instantly and GHL clients, the shadow/live write guard, the state store, the job log, notifications, Claude access, the slot rules | 10 | 2,856 | 195 |
| `services/reply_engine/` | The engine itself: classify a reply, route it, draft the answer, ask you to approve, book the call, run the follow-up ladder, chase show-rate and no-shows | 16 | 12,477 | 593 |
| `jobs/` | The three scheduled ticks: cadence, appointments, and the 07:30 pipeline sweep | 4 | 1,827 | 79 |
| `changesets/` | Staged Phase 0 changes to your six live campaigns, each with a dry-run and a rollback | 7 | 2,510 | 112 |
| **Total** | | **38** | **19,670** | **1,003** |

All 1,003 tests pass (979 before the review pass, 24 added with the fixes below). Every `.py` file under
`shared/`, `services/`, `jobs/` and `changesets/` compiles clean on Python 3.9.

There are seven runbooks in `runbooks/`, one per area plus this report and the decisions list.

### The rule the whole thing is built around

Nothing writes to a live system unless two switches are both on: `MODE=live` **and**
`ALLOW_LIVE_WRITES=1`. With either one missing, every write is intercepted before the request is built,
recorded as a `would_do` line in `.tmp/shadow_log.jsonl`, and the calling code carries on as if it had
happened. Reads are always real, which is how the dry runs below can tell you true things about your
live data without touching it.

---

## 2. The replay: all 44 real replies from September, run through the engine

Command: `python3 -m services.reply_engine.replay --fixture services/reply_engine/tests/fixtures/instantly_replies_2026-09.json`

44 replies in, 44 verdicts out, zero exceptions, zero live writes.

### How it graded them

| Label | Count | What it means |
|---|---|---|
| `ooo` | 17 | Out of office. No reply drafted, no blocklist. |
| `auto_reply_unmonitored` | 7 | A robot mailbox. Recorded, nothing sent. |
| `positive_interested` | 6 | Wants to talk. Draft written, waiting on you. |
| `negative_hostile` | 3 | Angry. No reply, and the lead is blocklisted. |
| `negative_notfit` | 3 | Wrong fit. Logged to GHL, no reply. |
| `positive_question` | 3 | Asked something before committing. Draft written. |
| `unsubscribe` | 3 | Asked to be removed. Blocklisted, as your offer sheet requires. |
| `negative_notnow` | 2 | Timing. A task goes on your GHL list, no reply. |

34 of the 44 were decided by a rule, 10 by a model. The model calls were faked for this run, so it
cost nothing.

### What it would have done

| Action | Count |
|---|---|
| `instantly.update_interest_status` | 37 |
| `ghl.upsert_contact` | 20 |
| `ghl.upsert_opportunity` | 20 |
| `ghl.create_note` | 20 |
| `instantly.blocklist_create` | 6 |
| `ghl.create_appointment` | 3 |
| `ghl.create_task` | 2 |
| **Total intended writes** | **117** |

Every one of those 117 is a `would_do` line. Zero were real.

9 replies produced a draft. **Not one of them would have been sent without you tapping Approve.** That
is asserted by a test, not just by inspection: `test_no_first_reply_is_ever_sent_without_an_approval_token`.

3 calls would have been booked. All 3 appointments carry `toNotify: false`, which means GoHighLevel
would not have emailed the prospect an invite before you approved the reply. That was a real bug found
during integration; see section 4.

**What this replay does NOT cover, and why section 4a exists.** A replay classifies replies; it never
runs the ten-minute appointments tick. So every touch that the tick sends - the confirmation, the
pre-read, the reminders, the no-show ladder - is invisible to it, and the clean evidence above says
nothing about them. That is exactly where both critical defects were hiding. They were reproduced by
driving `booking.book()` and then the tick directly, and are now pinned by tests in
`services/reply_engine/tests/test_integration_fixes.py`.

1 reply was parked for you to decide: Lead B asking for 11:30, which is outside your own slot rule.

---

## 3. The three real positives, side by side with what you actually did

This is the part worth reading slowly. It is the engine's judgement against yours, on the same week.

### Lead A, bookkeeping

| | You | The engine |
|---|---|---|
| Sept 21, 09:42 CT: "What is your percentage?" | Answered with the 20-30% of first-year fees range | Graded `positive_question`, drafted an answer, offered Mon 2:30 and Tue 2:00 CT, asked you to approve |
| Sept 21, 12:37 CT: "Thursday 4pm Eastern works for me" | Booked Thu 3:00 CT, sent invite and Zoom link | Graded `positive_interested`, converted 4pm ET to 3:00 CT, booked Thu 3:00 CT, drafted the confirmation for your approval |
| Sept 21, 18:17 CT: "I am available every day 3pm-6pm Eastern" | (no action recorded) | Recognised she is **already booked**, did not create a second call, drafted "we are already set for Thu 3:00 CT" plus the reschedule link |

Same outcome as you on the booking, same time, same timezone conversion. The third message is where it
adds something: a second availability note after a booking is a trap, and it does not fall in.

### Lead B, cleaning

| | You | The engine |
|---|---|---|
| Sept 18, 10:08 CT: not interested in reactivation, but interested in chasing lost proposals | Kept the conversation going | Graded `positive_interested`, drafted a reply, offered Fri 3:00 and Mon 2:00 CT |
| Sept 18, 10:25 CT: "Monday at 2 CTS works for me" | Booked Mon 2:00 CT, sent invite | Booked Mon 2:00 CT. Same call. |
| Sept 21, 14:00 CT: "emergency, please reschedule for this Wednesday around 11:30 am" | You took 11:30 and moved the call | Parsed 11:30 correctly, then **refused to book it silently** because 11:30 breaks your own 12:00-18:00 rule. Drafted a counter-proposal for Wed 12:00 or 12:30, and put a "Book Wed 11:30 CT" button on the same card so either answer is one tap |

This is the single most important disagreement in the whole report, and it is a question for you, not a
bug. You took the morning. The engine will not take a morning without asking. Section 8, item 2.

### Lead C, facility services

| | You | The engine |
|---|---|---|
| Sept 17, 07:53 CT: "What is the upfront cost?" | Replied: "Upfront it usually lands between $750 and $3500 and the whole thing sits under the $24K guarantee", and offered Friday 3 or Monday 1 | Graded `positive_question`, drafted an answer, offered Thu 2:00 and Fri 2:30 CT, asked you to approve |

Here the engine is deliberately more cautious than you were, and you should know why. Your `$750-$3,500`
range is not in `config/offers.md`. The offer sheet says "setup + monthly retainer, $2,500-5,000/mo
(TO CONFIRM)", which is a different pricing structure, not just a different number. The copy validator
refuses to let any draft quote a figure that is not in the offer sheet, so the engine cannot repeat your
range. The staged draft for her therefore refers back to "the upfront range I sent on the 17th" and
quotes no new number.

**She has a price from you in writing that your own offer sheet does not know about.** Fixing that is
section 8, item 6.

---

## 4. What integration actually changed

The six components each worked alone. Joining them surfaced defects that no single component could see,
because each one lived in the gap between two of them. The ones worth naming:

1. **GoHighLevel would have emailed prospects an invite before you approved anything.** `booking.book()`
   runs the moment a reply is classified, not when you approve it. It created the calendar event with
   GHL's default notification setting, so the prospect got an invite for a call you had not agreed to,
   and if you vetoed, the system had to un-say it. The appointment is now created silently
   (`toNotify: false`) and the invite is released only after your approved reply actually goes out.
   Visible in the replay evidence: all 3 appointments carry `toNotify: false`.

2. **Rewording a card could confirm a call that was never created.** Editing a draft re-ran the copy
   checks and then cleared the whole problem list, including "the appointment was never created" and
   "that slot is already taken". Those now survive an edit. Only booking the call for real clears them.

3. **An out-of-office could confirm your call.** The "did they confirm?" check keyed on the classifier's
   label. Eleven of the 44 September replies are auto-responders whose first words are "Sure, thanks for
   reaching out...", which matched the confirmation pattern and disarmed the 4-hour "no C yet" safety
   net. The body is now read directly for out-of-office markers, whatever the label says.

4. **A morning could be booked directly.** The availability check and your slot rules were separate, and
   only one of them ran on the direct booking path. Both run now, with an explicit waiver for when you
   tap "Book as asked".

5. **You could not veto from email.** On an unprotected ntfy topic the push strips the Approve and Veto
   buttons, and the email it points you to carried no links either. The email now renders them.

6. **A capped read looked like a complete one.** Paged reads stopped silently at their page limit, so a
   partial lead list could be applied to GoHighLevel as if it were the whole set. A capped pull now says
   so and blocks the apply.

Four further fixes closed smaller gaps: the Lost move can now carry "No show x3" as its reason (so it
mirrors to Instantly as no-show rather than not-interested), a booking now cancels any running no-show
recovery, the show-rate ladder now receives the lead's timezone, and the booking-link sentence is no
longer copy-pasted in three places.

---

## 4a. What the review pass found, and what it cost to close

A completeness review read the whole build against the blueprint. Its verdict was "not ready for a
48-hour shadow run as it stands, but close, and the blocker is a short list rather than a rebuild."
Everything on that list is now closed. In order of how much it would have cost you:

**1. The prospect would have been told about the call before you approved it.** Integration fix #1
(above) stopped GoHighLevel mailing the invite early. It did not stop the engine's own confirmation.
`register_booking` armed the show-rate ladder at classification time, and the first touch in that
ladder is "Locked in for Wed, Sep 23 at 2:00 CT. The calendar invite is on its way with the Zoom link",
due at T+0. The appointments tick runs every ten minutes, so the prospect would have had it within ten
minutes of the reply arriving, before your approval card was tapped, and possibly after you decided to
veto. The 44-reply replay never caught it because a replay does not run the appointments tick.

The ladder is now created **held**. The hold is a marker on the appointment id, so it holds whether the
schedule was armed by the booking or later by the calendar read, and nothing is dispatched from a held
schedule. `approval.send_approved` releases it in the same breath as it releases the GHL invite, right
after your approved reply actually goes out, and re-anchors the T+0 touches to that moment (an approval
three hours later would otherwise have its confirmation dropped as "too late" and the lead would get an
invite with no confirmation). No-show detection is held too: a call you have not approved is never
chased with "Sorry we missed each other".

**2. A veto undid the calendar event and nothing else.** `cancel_booking` cancelled the GHL
appointment, moved the opportunity back, reset the Instantly interest and released the slot, but left
the show-rate ladder armed and the `appointment:<id>` / `appt:<id>` rows in the store. A call you
refused still sent the prospect a one-page pre-read fifteen minutes later, "We are on for tomorrow,
reply C to confirm" twenty-four hours before, and raised you a 4 h "has not confirmed" task. Nothing
cleaned it up: the tick only cancels schedules GoHighLevel reports as cancelled, and with no GHL token
nothing is authoritative, so the residue would never have healed itself. A veto now tears down the
schedules, the hold and every index row, and a test asserts a vetoed booking leaves zero armed touches
and no appointment row.

**3. Every Approve link would have pointed at `localhost` for 48 hours.** `BASE_URL` was in
`modal_app.SECRET_KEYS` and missing from the `modal secret create` command in the deployment runbook,
which is the thing you would actually have run. In shadow, `approval.base_url()` fell back to
`http://localhost:8000` with a warning nobody reads. The cards would have arrived on your phone, been
perfectly readable, and been dead to the touch, while the watch's "a push arrived each morning"
criterion passed. It is in step 2a now, with the two-pass deploy it requires (the URL does not exist
until the first deploy, so the secret is re-created with `--force` afterwards), the fallback logs at
ERROR in shadow as well as live, and a new exit criterion says to tap one link end to end.

**4. Four switches the runbooks tell you to flip could not be flipped.** `ZOOM_WEBHOOK_SECRET`,
`A2P_10DLC_REGISTERED`, `NTFY_TOKEN` and `CADENCE_D6_HOLD` were in no Modal secret, so connecting Zoom,
clearing A2P, putting a token on the ntfy topic and enabling the D6 hold each needed a code edit and a
redeploy. The Zoom one is the expensive one: without the secret the webhook answers 503 to every event,
no joins are recorded, and no-show detection returns "unknown" for every call, which is the exact state
connecting Zoom was supposed to fix. All six keys are in the secret now, created empty, and a test walks
the AST of every module and fails if any environment variable the code reads is in neither the secret
list nor a documented not-deployed list.

**5. The `Job_Log` you are told to read as the gate was already polluted.** It held 1,642 rows, 48 of
them `mode=live`, written by evidence scripts that set the live flags inside their own process on
2026-09-22 between 04:00 and 05:23 UTC. The Instantly and GHL transports were mocked, so those rows
reached no live API. The 9 `notify.push_email` rows (05:22:48Z to 05:23:01Z) are not covered by that:
whether they emailed Lorenzo or pushed to the ntfy topic is not proven (items 2 and 3 of "What went
wrong overnight" in `MASTER_BUILD_REPORT.md`). The rows also name real production ids and real lead
addresses and sit interleaved with the shadow ones.
The file is quarantined at `.tmp/quarantine/` with a README, the log restarts empty, and every
`--dry-run` plus the replay now redirects its logs into `.tmp/scratch/<run>/`. The session guard hook
greps command strings and cannot see a script that sets those variables internally, which is
DECISIONS C5 demonstrated rather than theorised.

**6. The "reply C" loop could not close.** The 24 h reminder goes out through GoHighLevel, so a lead
who replies "C" answers GoHighLevel, and the only confirmation reader was driven by the Instantly
poller. The 4 h "has not confirmed" task would therefore have fired on essentially every booking, which
is the opposite of the design. The tick now reads the GHL conversation for any call still waiting on a
C, using the same confirmation and out-of-office checks the Instantly path uses, before the task can be
raised. It needs the GHL token; without one it reports how many calls are waiting on a C nobody can
read, which is honest about today.

**7. Found while fixing the above, not on the review's list:** `register_booking` called
`cancel_recovery_for_rebooking` with the id of the call it had just created, which wrote
`state=done` for it, and no-show processing returns immediately on a done state. **No-show detection
has never run for a single engine-made booking** - only for widget ones. It no longer invents a state
record for a call that has nothing to cancel.

Three smaller ones closed with them: the offered-slot registry's release path was a read-then-set
against four concurrent writers and could silently drop another lead's reservation (it is atomic now);
a call that was held never moved the Instantly lead to Meeting Completed (3), so every held call that
did not immediately produce a proposal still read as booked in the numbers section 6 divides by; and
the blueprint's agent template still named the retired `claude-fable-5-1` model.

---

## 5. The dry runs

All four ran with `LLM_FAKE=1 NOTIFY=off MODE=shadow`. Reads are real; writes are intercepted.

| Run | Result | Writes |
|---|---|---|
| Replay over the 44 recorded replies | 44 verdicts, 9 drafts, 3 bookings, 117 intended writes | **0** |
| `booking.book()` then the appointments tick, before and after approval | schedule held, 0 dispatched before approval; confirmation dispatched at the approval moment; a veto leaves 0 armed touches and no appointment rows | **0** |
| `poller --dry-run` (live Instantly key, read-only) | 3 GET requests, 44 replies processed, cursor advanced in a throwaway store | **0** |
| `cadence_tick --dry-run` | 39 leads in store, 0 armed | **0** |
| `appointments_tick --dry-run` | 0 upcoming, 4 pending touches, next is a 24 h reminder at 11:30 CT | **0** |
| `pipeline_sweep --dry-run` | 1 item: Lead A awaiting reply for 7 h | **0** |
| Phase 0 change-set, all six campaigns | all six OK, 0 errors, 2 warnings | **0** |

Two of those need a word of explanation.

**The cadence found 39 leads and armed none of them.** That is correct, not broken. The follow-up ladder
only arms when you approve a reply, and in a replay nobody approves anything. It has nothing to do until
you start tapping Approve.

**The sweep and the poller both made real HTTP calls.** They were all reads: `GET /emails` and
`POST /leads/list`, which is a read despite the verb. That is how they can tell you Lead A has been
waiting 7 hours without writing anything.

**Where the evidence is written.** Every dry run and the replay now redirect their logs into
`.tmp/scratch/<run>/` rather than the shared `.tmp/job_log.csv`, so the log the 48-hour watch is read
from stays a record of the watch and nothing else. The pre-existing log, which held 48 `mode=live` rows
from earlier evidence runs, is quarantined at `.tmp/quarantine/job_log_polluted_2026-09-22.csv` with a
README explaining what is in it. `.tmp/shadow_log.jsonl` was never polluted: 1,203 rows as of the
2026-09-22 verification pass (it was 1,145 when this line was first written and grows with each
shadow-mode run), all
`mode=shadow`.

---

## 6. The Phase 0 change-set

This is the only thing that touches your six live campaigns, and it is staged, not applied.

All six dry-runs pass with zero errors and zero writes. Every campaign gets the same two settings fixes
plus new copy:

- **Sending schedule**: `07:00-19:00 America/Detroit, 6 days a week` becomes
  `07:00-19:00 America/Chicago, Mon-Fri`. Five of the six are currently sending on Detroit time, on
  Saturdays. (`recruiting_outbound` is on Chicago time but `08:00-17:00`, also 6 days.)
- **Pipeline value**: `$1,000` becomes `$6,000` for the reactivation campaigns and `$7,500` for the
  trigger and outbound ones, so the pipeline figure the sweep sorts your morning by is real.
- **Copy**: variants added to every step, and a **new step 3** added to each campaign.

Two warnings, both on `cleaning_trigger`: step 1 variant B uses `{{buildingType}}` and `{{metro}}`,
which that campaign's leads do not carry yet. Those leads need the fields before that variant can go
out.

**One thing to understand before you approve it.** Adding step 3 releases roughly 100 already-completed
leads per campaign into a step-3 send the moment the change lands, about 620 people across the six. They
would get a "Last one from me on this" after weeks of silence. The runbook offers a pause-patch-trim
path if you would rather trickle them. That is a business call, not a technical one.

Rollback: every apply writes a backup of the campaign as it was. The restore steps have changed since
this was written; use "Backups and restore" in `GO_LIVE_CHECKLIST.md` and `runbooks/phase0.md`.

---

## 7. Go-live checklist

Removed. This section used to carry its own ten-step checklist and rollback table, which competed with
`GO_LIVE_CHECKLIST.md` and had gone stale. `GO_LIVE_CHECKLIST.md` is the only go-live order and holds
the rollback steps; read `REREVIEW_2026-09-22.md` before following it.

---

## 8. Blocked on you

As it stood in the early morning of 2026-09-22. `runbooks/DECISIONS_FOR_LORENZO.md` is the current list. The short list:

| # | Thing | Why it matters |
|---|---|---|
| 1 | **GHL Private Integration token** | Not created. Without it the engine cannot read your calendar, so it will not offer or book verified times, and armed leads stall after two days. |
| 2 | **Mornings: yes or no** | Your rule says 12:00-18:00. You took Lead B's 11:30. Either it was an exception, or the rule should change. Right now the engine asks you every time. |
| 3 | **ntfy topic** | Public topic, no token. Approve and Veto buttons only exist in email until you set `NTFY_TOKEN` or rotate the topic. |
| 4 | **`REPLY_ENGINE_SECRET`** | Unset. Tokens are signed with a secret that is in the repository. |
| 5 | **Zoom** | Not connected to the Discovery Call calendar, so booking confirmations say the video link follows separately instead of carrying it. |
| 6 | **The outbound price** | You quoted Lead C $750-$3,500 upfront in writing on Sept 17. `config/offers.md` says $2,500-5,000/mo retainer and marks it TO CONFIRM. Until they agree, no draft may quote her a price. |
| 7 | **A2P 10DLC** | Not registered, so every SMS leg is off. Email-only until it is. |
| 8 | **The step-3 burst** | Approving Phase 0 releases about 620 completed leads into a step-3 send at once. Trickle or burst is your call. |
| 9 | **The live-write ticket** | A script that sets the live flags in its own process can still bypass the session guard. It already happened: 48 `mode=live` rows reached the job log that way (quarantined now). The re-review later found the hook never guarded the build session at all (SAF-1); the guard rework is re-review Slice 4. |
| 10 | **The calendar timezone** | Never read, by anyone. Every "12:00-18:00 CT" slot in this build assumes Central. Needs the token, then thirty seconds in the Availability tab. |
| 11 | **Leads A and B stay manual** | Both are Google Calendar events, not GHL bookings, so no confirmation, reminder or no-show check runs for either. Nothing to decide; just do not expect the engine to cover them. |

---

## 9. Not built yet

This is the honest list. Nothing here is broken; it is work the blueprint describes that Phase 1 does
not do, plus two things that will not behave the way the blueprint implies.

**The two calls on your calendar this week are not covered by any of this.** Lead B (Wed 11:30 CT) and
Lead A (Thu 15:00 CT) are hand-made Zoom events on your own Google Calendar, not GoHighLevel widget
bookings. The only appointment source in the engine is the GHL Discovery Call calendar, and nothing in
the repository touches the Google Calendar API. So neither call gets a confirmation, a pre-read, a 24 h
reminder, a 1 h link, a 15 m nudge or no-show detection. **They stay manual**, and that is deliberate:
the alternative is mailing a ladder of reminders to two prospects who agreed those times with you
directly, out of GHL contact records that may not exist. The tick now prints "NOT COVERED: ..." for each
of them on every run so it is never silent about it. Book the next one through the widget and the engine
owns it.

**The "reply C" loop only closes with the GHL token.** The reminder goes out through GoHighLevel and the
reply comes back to GoHighLevel, so the engine now reads the GHL conversation before raising the 4 h
task. Without a token there is nothing to read, and the task fires. The digest says how many calls are
in that state on each run. The exact shape of the GHL conversations response is also unverified (nobody
has held the token), so the reader is deliberately tolerant and fails closed: a payload it cannot parse
confirms nothing.

**D6's calendar invite does not exist as specified.** The blueprint says "a calendar invite for one of
the slots, marked free so it does not block their day". What is built is a private `HOLD:` block on your
own calendar with notifications suppressed, off by default behind `CADENCE_D6_HOLD`. The prospect
receives nothing, because a GoHighLevel appointment carries no transparency flag. The real touch needs
an ICS attachment with `TRANSP:TRANSPARENT` sent from the Instantly reply, which is a design change, not
a flag. **Out of scope for Phase 1.** Day 6 renders the no-invite wording, which is honest copy.

**"Next Tuesday" is never auto-booked.** `shared/slots.py` reads "next <weekday>" as the following week,
which is past the 5-business-day horizon, so a lead who writes "next Tuesday at 2pm works" is
counter-proposed rather than booked and waits for you to tap "Book as asked". Plain "Tuesday at 2pm"
books. Both readings are defensible; the choice is yours and it is DECISIONS F4. The cost is now pinned
by a test on each side so it cannot be changed by accident.

**A2P is not registered**, so every SMS leg in the show-rate and no-show sequences is generated and
skipped with `a2p_not_registered`. Email-only until it clears, which takes 3 to 7 business days from
the day you start it.

**Zoom is not connected to the Discovery Call calendar**, so booking confirmations say the video link
follows separately instead of carrying it, and without `ZOOM_WEBHOOK_SECRET` set there is no join
telemetry at all: no-show detection answers "unknown" for every call and raises you a manual task
instead.

**The live-write ticket (DECISIONS C5b) is not built.** A script that sets `MODE=live` inside its own
process still bypasses the session guard, which is how 48 live-mode rows reached the job log. The
quarantine and the scratch-log convention keep the record clean for this watch; the real fix has to land
across five files at once and belongs before the first live run, not in the middle of a shadow watch.
The re-review later found the hook never guarded the build session (SAF-1); its rework is re-review
Slice 4.

**Phase 0 is staged, not done.** Every hard blocker on `changesets/PHASE0_MANUAL_CHECKLIST.md` is still
open: no GHL token, no A2P, no new domains bought (how many to buy is your call; the build no longer
sizes an order), and the step-3 change-set is staged with its ~620-lead burst undecided. Two of the
four Upwork threads (an invitation and a call request) are invisible to the API and now have a
hand-step note in `changesets/drafts/` rather than a draft, because nobody can read what either client
asked for.

---

*Everything in this report is reproducible. The commands are in section 5, the evidence is in
`.tmp/`, and the tests that hold each claim in place are named where the claim is made.*
