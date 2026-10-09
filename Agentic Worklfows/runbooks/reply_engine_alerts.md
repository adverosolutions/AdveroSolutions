# Reply engine alerts: what they mean and what to do

These are the pushes (and the matching emails) the reply engine sends when it
holds something back instead of acting. Every one of them means the lead has
heard nothing from the engine about the problem. Nothing here needs a code
change; each section ends with the one thing to do.

On a public ntfy topic (neither `NTFY_TOKEN` nor `NTFY_ALLOW_SENSITIVE=1` is
set), pushes carry no lead names: an approval card is titled by its
classification only ("Reply to approve: positive question", or "Reply to send
yourself: positive question" for a lead not answered yet), the chase leaves
out the thread's subject, and the full card with its links is in the email.
In the headings below, `{lead}` is the lead's email on a protected topic and
reads "a lead" on a public one; the cadence pushes (D1 held, D1 Veto, slots
unavailable, the D6 cards) then put the lead's email and company only in the
email copy (`cadence._lead_push`, since 2026-09-23).
Protecting the topic (set `NTFY_TOKEN`, or `NTFY_ALLOW_SENSITIVE=1` to accept
the risk; `shared.notify.topic_is_protected` reads both) brings the names back.

Related runbooks: `reply_sla_and_approvals.md` (approval cards),
`cadence_and_booking.md` (the daily follow-ups and booking),
`show_rate_and_no_show.md` (the reminder ladder).

---

## "Call NOT cancelled for {lead}"

**What you see.** A high-priority push: GHL refused to cancel appointment
{id}, with the error and the reason (vetoed, released after expiry,
superseded, passed before approval, edited to other times). It carries an **I cancelled it**
button when BASE_URL and REPLY_ENGINE_SECRET are set.

**What it means.** The engine tried to take a call off the calendar (you
vetoed its card, you released the call of an expired card, a newer reply
replaced it, or the reply you sent offered other times) and GHL said no. The call is still on the GHL
calendar. The engine has:

- kept the booking on the lead, marked as waiting on a cancel;
- kept the reminder ladder held, so the lead gets no "Confirmed" or
  "still good for tomorrow?" message;
- queued a retry, which runs every few minutes (every poller tick).

Most of the time the retry succeeds on its own and you hear nothing more.

The engine only counts a cancel as done when GHL accepts it, or when GHL
answers 404 / 410 AND a second read of the appointment also answers 404 / 410
or shows it cancelled. Any other error (422 "calendar not found", 400, 403, a
502 page, a 404 on a route) is a failed cancel and goes to the retry. When the
engine did not see the cancel itself (that second-read case, or your "I
cancelled it"), it keeps the reminders held until an hour after the call's
time, then clears them, in case the event is still live after all.

**What to do.** Nothing yet. If you would rather settle it now, cancel the
appointment in GHL (do not notify the lead), then tap **I cancelled it**.
If a second alert, "Cancel the call ... BY HAND", arrives, follow the next
section.

## "Cancel the call for {lead} BY HAND"

**What you see.** An urgent push after about six failed attempts (roughly
half an hour). It names the appointment, the number of attempts and the last
GHL error, and carries the **I cancelled it** button.

**What it means.** GHL keeps refusing the cancel. The engine still keeps the
lead silent (booking kept, reminders held) and now retries only once an hour.
If GHL answers that the appointment is already cancelled, deleted or not
found, the engine treats that as done and cleans up by itself.

**What to do.**

1. Open the appointment in GHL and cancel it. Do not notify the lead: they
   were never told about this call.
2. Tap **I cancelled it** on the push (or in the email). A page asks you to
   confirm; press the button. The engine then removes the booking and the slot
   reservation, resets the Instantly interest status, and stops retrying. It
   does not call GHL, and it leaves the opportunity stage for you to move. The
   reminders stay held (nothing is sent) until an hour after the call's time,
   then they are cleared.
3. If the push has no button, BASE_URL or REPLY_ENGINE_SECRET is missing from
   the Modal secret. Fix that; the hourly retry will clear the booking once GHL
   reports the appointment cancelled or gone.

The link is signed for this lead and this appointment only and lasts 7 days.
An unsigned, altered or expired link is refused and changes nothing; the page
behind it shows nothing about the lead unless the link is valid.

## "Cadence HELD for {lead}: recipient could not be confirmed" (Resume link)

**What you see.** An urgent push saying a follow-up (D1, D2 and so on) was
not sent. Before every follow-up the engine re-reads the lead's last email in
Instantly to check the thread really belongs to them; that re-read failed
three times in a row. It carries a **Resume** button when BASE_URL and
REPLY_ENGINE_SECRET are set.

**What it means.** Nothing was sent and the follow-up sequence for this lead
is stopped. It will not restart by itself, because no new reply is coming to
restart it: the thread read is what failed.

**What to do.**

1. Open the thread in the Instantly inbox and check the last message is from
   the lead (not a colleague, not an auto-forward).
2. If it is, tap **Resume** and confirm on the page. The held follow-up is
   due again straight away. The next tick re-reads the thread before it sends
   anything and holds again if it still cannot confirm the recipient. A held
   D1 first re-opens its 30-minute Veto window, with a fresh Veto push.
3. If the thread belongs to someone else, do not resume. Reply by hand from
   the Instantly inbox.
4. If the push says no Resume link could be signed, BASE_URL or
   REPLY_ENGINE_SECRET is missing. Fix that and re-arm the lead by hand.

The Resume link is signed for this lead and this run of the sequence and
lasts 48 hours. It only undoes this kind of stop ("recipient could not be
confirmed"); a "thread belongs to somebody else" stop cannot be resumed.

## "Booked, pipeline update failed for {lead}"

**What you see.** A high-priority push, or a bold line on the card
("BOOKED, PIPELINE UPDATE FAILED") or on the Book-as-asked result page, naming
what did not update: the GHL opportunity stage (Call Booked) and/or the
Instantly interest status (Meeting Booked).

**What it means.** The call IS booked: it is on the GHL calendar, the booking
is recorded on the lead and its reminders are held until the confirmation
reply goes out. Only the CRM bookkeeping behind it failed. This is not a
failed booking; do not book it again.

**What to do.** Approve or veto the card as usual. Then, in GHL, move the
opportunity to Call Booked, and in Instantly set the lead's interest status to
Meeting Booked, whichever the alert names.

## "Book as asked undone for {lead}"

**What you see.** A high-priority push: "Book as asked for {lead} was not
applied: card {id} moved while the call for {time} CT was being booked
({why})", then what the engine undid. The Book-as-asked page says "Not
booked" with the same reason ("Booked, not sent" when the cancel failed).

**What it means.** You tapped Book as asked, and while the engine was writing
the call to GHL the card changed. The push says how: its own reply (the
counter-proposal offering other times) is going out or went out, a newer
reply from the lead replaced the card, the lead's own words held it, or it
expired. The confirmation was not saved and nothing more was sent. So that
no call stands that the lead was never told about, the engine undid the
booking:

- the call was cancelled again in GHL without notifying the lead (in shadow,
  recorded as would_do);
- its time went back to the pool, and its held reminders and records were
  cleared;
- the GHL opportunity went back to New Reply and the Instantly interest to 1.

The card's own reply and the times it offers are untouched. The lead's
history records the undo (`book_as_asked_undone`), and so does a Job_Log row
of the same name.

If the push says "That call could NOT be cancelled: GHL refused ...", the
call is still on the calendar. Its reminders stay held so the lead hears
nothing, the engine retries the cancel every few minutes, and the push
carries the **I cancelled it** button. It stands in for "Call NOT cancelled
for {lead}"; if GHL keeps refusing, "Cancel the call for {lead} BY HAND"
follows as for any failed cancel.

If it says "Booking it had also asked GHL to cancel the lead's earlier
call", the lead already had a call and Book as asked moved it: that earlier
call was cancelled by the booking and is not restored.

If it says the lead's row now holds another call ("appointment {id} for
{time} CT"), a newer reply's card booked a call while this one was being
booked. The engine never overwrites that call's record and never touches
that call; it only cancels the call Book as asked made. When that cancel went
through, setting the opportunity and interest back may have undone what the
other call set. When GHL refused it, the engine cannot retry it (the retry
works from the lead's row, which now holds the other call), so the push asks
you to cancel that appointment by hand and has no **I cancelled it** button.

**What to do.**

- Read the thread in Instantly. Usually the lead has the counter-proposal.
  If they should still have the time they asked for, reply by hand and book
  it in GHL, or wait for their answer to the counter-proposal.
- If a newer reply replaced the card, answer the card for that reply.
- If the cancel failed: nothing yet, or cancel the appointment in GHL
  yourself (do not notify the lead) and tap **I cancelled it**.
- If an earlier call was cancelled: check it in GHL, and rebook it with the
  lead if it should stand.
- If the row holds another call and the cancel went through: check that the
  opportunity is at Call Booked and the Instantly interest at Meeting Booked.
- If the row holds another call and the cancel failed: cancel the
  appointment the push names in GHL yourself, without notifying the lead.
  Its reminders stay held until then, so the lead hears nothing; once GHL
  reports it cancelled, the appointments tick stops its reminder schedule.
  Its time stays reserved until the call's time has passed.

## "D1 follow-up to {lead} is HELD: no BASE_URL"

**What you see.** A high-priority push, once per lead, saying the D1
follow-up is held because BASE_URL is unset or points at a local-only address
(localhost, 127.0.0.1, 0.0.0.0, ::1 and similar). The push has no buttons.

**What it means.** D1 is the only follow-up that sends on its own, after a
30-minute Veto window. The Veto button needs a public BASE_URL; without one
it would point at an address your phone cannot reach, so the engine opens no
window and sends nothing. It re-checks on every tick.

**What to do.** Set BASE_URL (an https address the phone can reach, for
example the Modal web endpoint) in the Modal secret and redeploy. On the next
tick the engine opens the Veto window and pushes "D1 follow-up to {lead}
sends at {time} CT" with a working Veto button (tapping it opens a confirm
page; pressing Veto there records the veto). The send is always at least
30 minutes after that push, on the first hourly tick that may send. If that
time falls on another day (for example the fix lands after 18:00, or on a
Friday evening), no push is sent that evening: the window opens at 09:30 on
the next business day with a fresh link, and the follow-up goes at 10:00.

## Editing a card that holds a booked call (Keep or Release)

**What you see.** On the Edit page of a card that holds the lead's booked but
not yet confirmed call (the booking confirmation card, or a newer card that
took the call over), two choices under the text:

- "Keep the call: send the invite for {time} CT"
- "Release the call: cancel it silently, no invite"

**What it means.** The engine no longer guesses from your words whether your
edit confirms the call or moves away from it. Your choice decides:

- **Keep** sends your reply, then releases the GHL invite and starts the
  reminders for the booked time.
- **Release** sends your reply, then cancels the call in GHL without notifying
  the lead (with the usual retry if GHL refuses). No invite, no reminders. The
  times you wrote in the engine's wording ("Fri 1:00pm" or "Tue Sep 29
  2:00pm") are held for this lead.

Saving without a choice is refused and nothing is saved; your text stays on
the form. The choice is tied to that exact call and that exact text: if the
booking changes before the reply goes out (a newer reply, a release, a cancel,
a new time), or its time passes, the send is refused and the card asks you to
choose again. A Release whose text still says an invite is on the way is
refused too.

**What to do.** Pick the one you mean, then Save and approve. To change your
mind, edit again and pick the other.

## "Card expired with a call still booked: {lead}"

**What you see.** A high-priority push when an approval card that holds the
lead's booked but unconfirmed call reaches its 48-hour limit without being
sent. It names the appointment id and the call's time, and carries two
buttons: **Keep the call** and **Release the call**. If the call's time has
already passed, only **Release the call** is offered.

The first line says what state the card was in: never approved, approved but
held back (with the reason), or approved earlier and put back to pending. The
second says whether a reply may have left the card. It says "No reply has
been sent from this card" only when the card's send history proves it.
Otherwise it tells you to check the Instantly thread first.

If the push is not delivered (ntfy down and the email leg failing), it is
sent again 5, 15, 30, 60 and 120 minutes apart, titled "(attempt N)". From the
sixth attempt it is **urgent**, titled **UNANSWERED (attempt N)**, and repeats
every hour until one is delivered or you decide. Each undelivered attempt
writes a `push_failed` Job_Log row (`kind: expired_booking`), which fails the
deploy watch.

**What it means.** The engine changed nothing in GHL. The call is still on the
Discovery Call calendar, no invite went out for it, and its reminders stay
held. The card itself is retired: it cannot be sent as it stands, and its old
Approve link answers "already expired". Cards that hold no call simply expire
at 48 hours with no push. Pending, blocked and stale-times cards expire on the
poller tick. Cards that are sending, have failed to send, or hold a send
claim do not expire, because a send may have reached the lead: use **Retry**
on those. Cards you approved outside sending hours (queued) do not expire
either; they go out when the window opens. Until you choose, the poller lists
the card among the approvals waiting on you as "expired holding the call ...
Keep or Release not chosen". This push is its only push: "Replies with no
owner" leaves it out.

**What to do.** Tap one. Each button opens a page that asks you to confirm;
nothing happens until you press the button on that page. The page repeats
what the card's history says about what was sent.

- **Keep the call**: nothing is written to GHL. The card comes back as pending
  for another 48 hours, still holding the call, and the page links to it. It
  is chased again from the start, like a new card. Nothing is sent to the
  lead until you approve it; approving sends the confirmation and releases
  the invite, as for any booking card. If a send from the card was started
  and never cleared, the card comes back as **send failed** instead. Check the
  Instantly thread, then use the Retry link on the page; Approve works again
  after that.
- **Release the call**: the call is cancelled in GHL without notifying the
  lead. If GHL refuses, "Call NOT cancelled" follows and the usual retry runs.

If the lead writes again before you choose, the new card takes the call over
(when it restates that time) or the call is released silently, exactly as when
a newer reply replaces any card; the buttons then answer "nothing to decide".

## "Call for {lead} is too close to confirm"

**What you see.** An urgent push, and a problem on the card, saying the reply
confirming a call was approved less than 60 minutes before it.

**What it means.** Nothing was sent and no invite went out. The call is still
on the calendar with its reminders held. An email confirmation that close to
the call is not reliable, so the engine leaves it to you.

**What to do.** Message or call the lead yourself. Then veto the card to
cancel the call silently, or leave the card if you have confirmed by hand
(once the call's time passes, approving it will release the call instead of
confirming it).

## "Replies with no owner: {n}"

**What you see.** A high-priority push from the poller listing cards that are
stuck and that nothing else chases: a send that failed (`send_failed`), a send
that started and never finished (`sending`), a reply held back because its
times had passed (`stale_slots`), and a card superseded with nothing in its
place. Each line says what the status means:

- `send_failed`: the send failed or may not have gone out. Check the thread
  in Instantly before you press Retry.
- `sending`: a send started and never finished, so it may or may not have gone
  out. Check the thread in Instantly before you press Retry.
- `stale_slots`: the reply was held back, so the lead has had no answer.
  Press Retry, then Edit it to offer new times.

When the push lists a `send_failed` or `sending` card, it carries a **Mark
sent** button for it (when BASE_URL is set to an address the phone can reach,
not localhost) and says: "If the reply did go out, press Mark sent. That stops
these reminders and keeps the call." A `sending` card is listed, with its
button, once its send started at least 10 minutes ago; one with no record of
when its send started is listed without a button (see below). With several
such cards there is one button per card, named after its lead, up to three. A
card left without a button is named in a line of its own, which tells you not
to press Retry or Veto if its reply did go out. A card held because its
recipient could not be confirmed never gets the button; its line says: "No
Mark sent for {lead}: held because the recipient could not be confirmed. Veto
it, or check the thread in Instantly."

Under each card's line the email copy lists the links its line asks for:
**Retry** (for `send_failed` and `stale_slots`, and for `sending` once its
send is 10 minutes old), **Veto** (not for `sending`, which Veto refuses) and,
for `stale_slots`, **Edit (after Retry)**. The ntfy topic is public unless
`NTFY_TOKEN` is set, so the push there has no links in its text and says "The
Retry and Veto links for each card are in the email."; on a protected topic
the links are in the push itself. When the links cannot be built (BASE_URL
unset in live, or the card could not be read) the push says "This push
carries no Retry or Veto link for {lead}".

A card that expired still holding a call is not in this push. Its own "Card
expired with a call still booked" push, with the Keep and Release buttons,
chases it. The poller still lists it among the approvals waiting on you.

How often it comes:

- **Until a push about the card reaches you** (ntfy down and the email leg
  failing), it repeats 5, 15, 30, 60 and 120 minutes apart, titled
  "(attempt N)", then every hour, day or night. From the sixth attempt it is
  **urgent** and titled **UNANSWERED (attempt N)**.
- **Once one has reached you**, the card is only reminded: at most once per
  business day, at 07:00 CT on the next business day, at high priority,
  titled "Replies with no owner: {n} (reminder)". It is never urgent again
  and never comes at night or at a weekend. A push that reached you at 03:00
  counts for that day, so the next reminder is the following business day's.
  A reminder that does not get through is retried inside sending hours
  (07:00-19:00 CT, Mon-Fri), 5, 15, 30, 60 and 120 minutes apart and then
  hourly, still at high priority.

A reminder never rides in an urgent push: a tick that owes both sends two.
Every push is recorded in the store (`poller:stuck_push`), so a restart of
the poller neither repeats it early nor forgets it. A card that leaves the
list (you pressed Retry or Mark sent, vetoed it, or it was sent) stops being
pushed; if it gets stuck again later it starts from attempt 1. Each
undelivered push writes a `push_failed` Job_Log row (`kind: stuck_card`,
`reminder: true` for a missed reminder), which fails the deploy watch.

**What it means.** A card in `send_failed` or `sending` never expires, and
when it owns the lead's booked call that call stays held (on the calendar, no
invite, reminders held) until you act. This push is the only alert for it.

**What to do.** Open the card. For `send_failed` and `sending`, read the thread
in the Instantly inbox first.

- **`send_failed` or `sending`, and the thread shows your reply went out:** tap
  **Mark sent** on the push (or in the email). A page asks you to confirm;
  press the button. The card moves to `sent_manually` and these pushes stop.
  The engine records the reply as sent, without sending anything: the lead's
  history, the follow-ups (armed as after any sent reply, unless the lead has
  written again since the reply the card answers) and the `sent_manually`
  Job_Log row the metrics read. If the lead's record cannot be read or written,
  a push says so: "Mark sent for {lead}: the lead's record was NOT updated"
  (see that section below). Nothing booked is released or cancelled. If the
  card holds the lead's call and its draft confirmed that time (or you chose
  Keep on its Edit page), the call is confirmed as a send would confirm it: the
  GHL invite is released and the reminders for the booked time start. Otherwise
  (you chose Release, no choice is on record, the booking changed since the
  card was drafted, the call is under an hour away or has passed, or the lead
  has written since) the call stays exactly as it is, and a push, "Call for
  {lead} still held after Mark sent", says why and what to do with it in GHL
  (see that section below). If the card changed while you decided, the page
  says so and nothing is recorded.
- **`send_failed` or `sending`, and the thread shows no reply from you:** press
  Retry, then approve.
- **A `sending` card and Mark sent:** it is listed, with the button, once its
  send started at least 10 minutes ago. By then nothing can still be running
  that send: each send ends inside its Modal call, within four minutes. Before
  that the Mark sent page says when it becomes available, and Retry is refused
  the same way: approving the card again while its send may still be running
  would send a second reply. If the send was held up anyway and goes through
  after you pressed Mark sent, it records nothing more: the card stays
  `sent_manually` and the reply is counted once, and a push says so (see "Reply
  to {lead} went out after its card was already marked sent" below). If the
  engine has no record of when the send started (the card holds no send claim),
  Mark sent is refused. Then do not press Retry: approving the card again sends
  the reply a second time. Confirm the call in GHL by hand; the card stays on
  this list, reminded once a business day. Mark sent or Retry on a `sending`
  card writes a `send_never_finished` Job_Log row, which fails the deploy
  watch: the send never finished, and the worker that ran it wrote nothing.
- **`stale_slots`:** press Retry, then Edit it to offer new times.

Never Veto a card that owns a booked call the lead has already been told
about. Veto cancels that call in GHL without notifying the lead, so a lead
who read "you are booked for Thursday" would lose the call with no word. If
the reply went out, use Mark sent. A card held by "Reply to {lead} HELD:
recipient not confirmed" is `send_failed` too, but the engine held it before
sending, and the thread may not be the lead's. It gets no Mark sent button,
and Mark sent refuses it. Veto it, or check the thread in Instantly: once the
thread checks out, Retry it, or reply by hand.

## "Reply to {lead} went out after its card was already marked sent"

**What you see.** A high-priority push: a send of the card went through
after the card was already recorded as sent. It says "already marked sent"
when you had pressed Mark sent on it (the send was held up past its
10-minute lease, and Mark sent took the card over), and "already sent" when
another send of the same card finished first. It names the card and when
the late send started.

**What it means.** The reply is recorded once. The card stays `sent_manually`
(or `sent`), and the late send wrote no history, armed no follow-ups, set no
interest status and wrote no second sent row. It wrote a
`sent_after_card_sent` Job_Log row, which fails the deploy watch. The lead
may have two replies: the one already recorded (yours, if you replied by
hand, or the other send) and this one.

**What to do.** Read the Instantly thread. If the lead has two replies, send
nothing more; if the second one needs a word of explanation, write it by
hand. Retry and Mark sent are refused on a sent card, and nothing in the
lead's record needs repairing.

## "Call for {lead} still held after Mark sent"

**What you see.** A high-priority push right after you pressed Mark sent. It
names the card, the call's time and appointment id, why the call was not
confirmed, and what to do in GHL.

**What it means.** Your reply is recorded as sent, but the lead's call was
left exactly as it was: on the GHL calendar, the invite withheld and the
reminders held. Mark sent confirms a call only when sending that card would
have confirmed it. The push says what stopped it, and what to do:

| The push says | What to do |
|---|---|
| the lead opted out or gave a final no (asked to be removed, a hostile reply, the wrong person, not a fit, not now) | Cancel it in GHL without notifying the lead; the push also says what not to do (for most: do not reply to them) |
| the lead wrote again after the card was drafted, or after the reply this card answers (their newer reply was sent before the card was drafted) | Read the thread, then confirm it or cancel it without notifying the lead |
| your recorded choice for it is Release the call | Cancel it without notifying the lead, as you chose |
| no Keep choice for it is on record, or the booking changed since the card was drafted | Read the reply that went out, then confirm it or cancel it without notifying the lead |
| its time has passed | Settle it: a no-show, or cancel it without notifying the lead |
| it starts in less than 60 minutes | Confirm it with the lead by hand, or cancel it without notifying the lead |
| its Keep or Release choice could not be read | Confirm it, or cancel it without notifying the lead |

The push is not repeated. The card is done (`sent_manually`), so Veto and
Retry are refused on it. Nothing in the engine settles the call on its own:
until you act, it stays on the calendar with the invite withheld and the
reminders held. The `sent_manually` Job_Log row records it under
`booking_left_held`.

**What to do.** What the push says, in GHL. Do not resend the reply: it
already went out.

- **To cancel the call:** cancel the appointment in GHL without notifying the
  lead. The engine's reminders stay held, so nothing goes to the lead.
- **To confirm the call:** send the invite from GHL. The engine's reminders
  stay held for this call, so send the confirmation and the reminders by
  hand, as in "Show-rate reminders NOT started for {lead}".

## "Mark sent for {lead}: the lead's record was NOT updated"

**What you see.** A high-priority push right after you pressed Mark sent: the
card is marked sent, but the lead's row could not be read, is missing, could
not be parsed, or could not be written, with the error. It says the lead's
history, offered times and follow-up ladder were not updated. When it matters
it adds what happened to the call: "The call's calendar invite WAS released
in GHL, but the lead's booking record still shows it waiting on this card",
or, when the row was never read, that a call this card holds was not
confirmed and stays on the calendar with its invite withheld and its
reminders held.

**What it means.** The card is done: it is `sent_manually`, it has left the
stuck list, and its `sent_manually` Job_Log row was written (with
`cadence_armed: false` and the problem in `cadence_not_armed`). A second
Job_Log row, `mark_sent_record_not_updated` (the lead, the card and the
error), records the failure, and the deploy watch flags it. The lead's
record did not move. Until you have checked it, assume it is as it was
before you pressed Mark sent:

- its history has no `reply_sent_manually` entry for this card, its
  `last_outbound_at` is older, and the card's offered times are not on it;
- no follow-ups are armed, so the engine sends this lead nothing on its own;
- the call, if the card held one: when the row could not be read, is missing
  or could not be parsed, nothing was confirmed. When only the write failed,
  the engine had already done for the call what a send does, so the invite
  may have gone to the lead (the push says so when it did) and the reminders
  may have started, while the lead's record still shows the call waiting on
  this card. The `sent_manually` row's `invite` and `show_rate_released`
  fields say what happened.

**What to do.**

1. **Do not resend.** Your reply is in the thread. Do not reply again by
   hand, and do not press Retry or Mark sent: both are refused on a
   `sent_manually` card and record nothing.
2. **Read the lead's record and the card**, read-only, from the deployed
   store (use `live` instead of `shadow` after the cutover):

   ```bash
   cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
   python3 -c "import json,sys; from shared.store import open_modal_store; s=open_modal_store(sys.argv[1]); [print(k, json.dumps(s.get(k), indent=1, default=str)) for k in s.keys('lead:') if k.endswith(':' + sys.argv[2].lower())]" shadow <lead email>
   python3 -c "import json,sys; from shared.store import open_modal_store; print(json.dumps(open_modal_store(sys.argv[1]).get('approval:' + sys.argv[2]), indent=1, default=str))" shadow <card id>
   ```

   If the lead's `history` has a `reply_sent_manually` entry for this card,
   the record was written after all. If it has none, it was not: follow the
   steps below. If nothing prints for the lead, its row is missing.
3. **Check the call in GHL** when the card held one. If the invite went out,
   the lead knows about the call: keep it. If it did not, the call is still
   held: confirm it or cancel it in GHL without notifying the lead, as in
   "Call for {lead} still held after Mark sent". Until the record is
   repaired, do not Veto any later card for this lead that holds the call:
   the engine may still read the call as unconfirmed, and a Veto would cancel
   it without a word to the lead.
4. **Follow up by hand.** No follow-ups are armed. If the lead needs one, send
   it yourself from the Instantly inbox.
5. **Read the thread before you approve any later card for this lead.** It
   was drafted from the old record, so it may offer times again or miss that
   your reply went out.
6. **Leave the record as it is.** No button re-writes it, and editing the
   store by hand is not safe. Note the card id and the error from the push so
   the record can be repaired.

## "Reply to {lead} HELD: ..."

**What you see.** A high-priority push saying a reply was not sent because of
something the lead wrote. It names the kind of reply and when it came in
(never its text), lists the cards now blocked, and says their offered times
are back in the pool. It comes at one of two moments: when the lead's no
arrives (every open card of theirs is held at once), or when you approve a
card, or the queue sends it, and the lead's row shows a reply that card never
saw. The end of the title says which:

| Title ends with | The lead's reply |
|---|---|
| "the lead asked to be removed" | an unsubscribe ("(blocklisted)" when the row says so) |
| "the lead sent a hostile reply" | hostile |
| "the lead said they are the wrong person" | wrong person |
| "the lead said it is not a fit" | not a fit ("(lost)" when the row says so) |
| "the lead said not now" | not now, or follow up later |
| "the lead sent a removal-style reply the engine held for your review" | read as a removal or hostile reply, but with a buying signal and no removal request in it, so the blocklist was withheld for you |
| "the lead gave a final no" | any other final no |
| "the lead wrote again" | a newer reply of any other kind (the push says whether it has a card of its own) |

For a no, the push also says what not to do (for example "Do not reply to
them: they asked not to be emailed"). When the lead sent that no before a
newer reply of theirs that is not a no, and the engine processed the newer
reply first, the push names it: "They wrote again after it ({kind}, {time});
this answer still stands." It then asks you to read the whole thread in
Instantly before you Veto.

For "the lead wrote again", the push says "after the card was drafted" only
when their newer reply was sent after the card was drafted, and "after the
reply this card answers" otherwise. It also says where the card for that
newer reply stands: waiting on you, approved and queued, being sent, already
answered, or "Their newer reply raised no card."

When a held card owns the lead's booked call, the push adds a note. After a
no, it says: "This card holds the call booked for {time} CT (invite
withheld): Veto the card to cancel it." With several cards held, the note
names the card that holds the call. After a newer reply that is not a no, or
a no the lead sent before one, Veto is not the default, because the lead may
be keeping that call. The note then says "... and a Veto cancels that call
without telling the lead", and adds that the lead may be keeping the call
when the card answering their newer reply names the same time.

When a held card had an earlier send attempt that failed (it was stuck at
`send_failed`, or was retried after one), the push opens "Nothing more was
sent." instead of "Nothing was sent." and names the card: that attempt may
have reached the lead, so check the Instantly thread.

Every hold writes one `blocked_lead_replied` Job_Log row with the lead, the
card (`approval`, or `approvals` for the holds made when the reply arrived,
which also carry `at_arrival: true` and `earlier_send`, the held cards with
an earlier failed attempt), `reason` (`opt_out` or `newer_reply`),
`category` (the label or status behind the title), `at` (when the lead's
reply came in) and `email_id`. Like every `blocked_` status it fails the
deploy watch (`changesets/deploy/watch_report.py`).

"Reply to {lead} HELD: recipient not confirmed" is a different stop: the
thread could not be confirmed as the lead's. It carries **Retry** and **Veto**
buttons (in the email copy when the ntfy topic is public) and says to check
the thread, then press Retry (the next send checks the thread again) or Veto
it and reply by hand; Mark sent is not available for it. See "Replies with no
owner".

**What it means.** Nothing was sent, and nothing will go out from those cards
as they stand: each is `blocked`, with the reason written on the card as a
problem.

- **The lead said no** (every title but the last): the engine has already
  done what that answer needs. An unsubscribe or a hostile reply is
  blocklisted in Instantly, unless it was held for your review. A wrong
  person is marked `wrong_person`, and any contact they named is queued for
  the list factory. Not a fit is marked lost. Not now gets a GHL follow-up
  task (in 30 days, or on the date they gave) and the sequence is paused.
- **The lead wrote again:** the draft answers words the lead has moved past.
  Their newer reply is in the thread, and usually has a card of its own,
  which the push names.
- **A no with a newer reply named:** the engine processed the lead's newer
  reply first, then the no they had sent before it. A no is never set aside
  for arriving late: it took effect as any no does, and it stays in force
  until the lead writes again.
- **The booked-call note:** the invite for that call was never released, so
  the engine has not told the lead about the call. Veto cancels it in GHL
  without notifying them.

**What to do.**

- **The lead said no: Veto the card and do not reply.** Not by hand, not from
  the Instantly inbox, not from another address. For a wrong person, do not
  email anyone from that thread (offers.md rule 7); a contact they named is
  already queued for the list factory. For "held for your review", Veto the
  card and read their reply in Instantly before anything else goes to them:
  if it asks to be removed, or is hostile, blocklist the lead there by hand
  and do not reply.
- **The lead wrote again: read the thread** and the card the push names for
  their newer reply: answer them on that card. Then Veto the held card (unless
  it holds the booked call, below), or reply by hand from the Instantly inbox
  if their newer reply needs an answer and raised no card.
- **A no with a newer reply named:** read the whole thread in Instantly before
  you Veto the card or anything else goes to the lead. The advice in the push
  (for example, do not reply to a lead who asked not to be emailed) still
  applies.
- **The booked-call note, after a no:** Veto the card; the call is cancelled
  without notifying the lead. The one exception is a card the push says had
  an earlier send attempt that failed: its reply may have reached the lead.
  If the thread shows that reply, the lead was told about the call, so do not
  Veto that card. Handle the call in GHL by hand (for a no, cancel it without
  notifying the lead).
- **The booked-call note, after a newer reply** (or a no with a newer reply
  named): do not Veto by default. A Veto cancels the call without telling
  the lead, and their newer reply may keep it: the push says so when the card
  answering it names the same time. Read the thread. If the call should
  stand, leave the held card and confirm the call with the lead and in GHL by
  hand. If it should go, Veto the card.
- **The Job_Log row** needs nothing by itself. During the deploy watch,
  check each one: the lead really said that, and the card was vetoed.

## "An older reply from {lead} arrived after their opt-out; not drafted"

**What you see.** A high-priority push, one per such reply, saying when the
older reply was sent and what kind it was, and which opt-out it came before.

**What it means.** The lead opted out or gave a final no (removed, hostile,
wrong person, not a fit, not now), and afterwards the engine processed a
reply the lead had sent before that. It arrived late: its first processing
failed and was retried, or a poller run that was killed had claimed it. The
engine recorded it in the lead's history and sent nothing: no draft, no
card. The lead's status and classification stay as the opt-out set them,
nothing is stopped or armed, and the follow-ups stay stopped. Two things
still happen, as for any reply: a removal request in the older reply is
applied, and an auto-responder's hand-off to a named contact is queued for
the list factory. The opt-out stands until the lead sends a new human reply
after it; that reply is handled as usual.

**What to do.** Nothing. Do not answer the older message, by hand or
otherwise: the lead's later no is their answer. If you think the opt-out
itself was a misreading, read the whole thread in Instantly before you do
anything.

## "An older reply from {lead} arrived after their newer one; not drafted"

**What you see.** A push, one per such reply: high priority, or low for an
automatic reply (out of office, unmonitored mailbox), which needs nothing.
It says when the older reply was sent and what kind it was, which newer
reply of the lead's it came before, the call time it proposed (if any), and
where the lead's cards stand.

**What it means.** The lead sent two replies and the engine processed the
newer one first: the older one's first processing failed and was retried,
or a poller run that was killed had claimed it. The older reply is not a no
(for a no, see the next section). The engine recorded it in the lead's
history and moved nothing: it drafted no card, superseded none of the
lead's cards, and took, moved, released or booked no call. It stopped or
re-armed no follow-ups, and the lead's status and classification stay as
they were. An auto-responder's hand-off to a named contact is still queued
for the list factory.

**When the older reply proposed a call time.** The push names it ("It
proposed a call at {time} CT; nothing was booked for it."). A card of the
lead's that is still open and names other times would answer as if that
reply had never come, so it is held until you edit it:

- The card carries the problem "the lead's older reply (sent {time}, read
  only after this card was drafted) proposed a call at {time} CT, and this
  card names other times (...)". Approving it as it is is refused, and the
  page says why; its Approve link shows the problem instead of a Send button,
  day or night. A card you had already approved is not sent by the 07:00
  queue.
- Edit clears it, as it clears a copy problem. The Edit page shows the
  problem above the draft.
- No card is held when one of its times is the proposed one ("offers that
  time too"), or when a newer reply of the lead's proposed a time itself:
  that is their newer word on the time ("their cards follow that one"), and
  a card that booked it confirms that call when it goes out.

**Where the lead's cards stand.** The push says, for each:

- "Card {id}, which answers their newer reply, is still open and can be
  approved and sent as usual": only when the older reply proposed no time.
  Approve it as usual. When it holds the lead's booked call, the push adds
  "and sending it confirms the call booked for {time} CT": sending it
  releases the invite and starts the reminders, as for any booking card.
- "Card {id} ... is still approved and goes out when the sending window
  opens": nothing to do; the queue sends it at 07:00.
- "Card {id} ... names other times (...), so it is held until you Edit it":
  see above. For a card you had approved: "was approved, but ... the queue
  will not send it as it is".
- "Card {id} ... is being sent (its send started {time})": its send is under
  way. "has been stuck at sending since {time}" means its send started and
  never finished, so it may or may not have gone out: see "Replies with no
  owner".
- "The answer to their newer reply already went out (card {id})": when the
  push adds "the follow-ups it started keep running", they do. When it adds
  "naming other times", the time the older reply proposed has had no answer.
- "No card of theirs is open."

**When the lead's no is in force.** If the lead's row carries a no (for
example, they asked to be removed in a reply the engine processed late), the
push says so as the HELD push does: "the lead asked to be removed
({kind}, sent {time}), that answer still stands, and their status stays
{status}". It names the card answering their newer reply that stays
blocked, holds no card for a proposed time, and ends with the same advice
as the HELD push (for example "Do not reply to them: they asked not to be
emailed."). It never tells you to reply by hand.

**What to do.**

- **A time was proposed and a card is held:** read the older reply in the
  Instantly inbox, then Edit the card the push names: answer the time they
  proposed (and book that call in GHL by hand if it stands), or keep the
  card's times if the lead has moved on. The edit clears the hold and
  approves the card. Or reply by hand.
- **A time was proposed and no card is open** (the answer already went
  out): answer the time they proposed by hand, and book that call in GHL if
  it stands.
- **No time, or the card offers it:** read the older reply in the Instantly
  inbox. If it asks something the open card does not answer, Edit that card
  before you approve it, or reply by hand. If the answer to their newer
  reply already went out, reply by hand only if the older message still
  needs an answer.
- **The lead's no is in force:** read the whole thread in Instantly before
  anything else goes to them, and follow the advice in the push. Do not
  reply by hand.
- **An automatic reply:** nothing.

## "An older opt-out from {lead} arrived after their newer reply; applied"

**What you see.** A high-priority push naming the lead's no (removed,
hostile, wrong person, not a fit, not now) and when they sent it, the newer
reply they sent after it, what the engine applied, and that the answer to
that newer reply had already gone out (or that no card of theirs was open).

**What it means.** The engine processed the lead's newer reply first, then
the no they had sent before it, which arrived late (a retry, or a reply a
killed poller run had claimed). A no is never set aside for arriving late:
it took effect as any no does (the status, a removal's Instantly blocklist,
the follow-ups stopped), and it stays in force until the lead writes again.
No card was held, because none was open. When a card of theirs is still
open, it is held instead, the "Reply to {lead} HELD: ..." push names the
newer reply, and this push is not sent.

**What to do.** Read the whole thread in Instantly before anything else goes
to the lead: their newest words came after the no. The advice at the end of
the push still applies (for example, do not reply to a lead who asked not to
be emailed). If the no was a misreading, handle the lead by hand.

## "Show-rate reminders NOT started for {lead}"

**What you see.** A high-priority push after an approved confirmation went
out, saying the held reminder ladder for the appointment could not be
released. The reason in brackets names what failed (the hold marker could not
be read or deleted, or a schedule could not be re-armed).

**What it means.** The confirmation reply reached the lead, but the store
refused the release, so the reminders ("Locked in for ...", the 24-hour and
1-hour reminders) are still held. The engine writes one
`show_rate_release_failed` Job_Log row for the call (the deploy watch fails on
it) and retries the release at the start of every appointments tick (every ten
minutes). When a retry goes through, a second, normal-priority push says
"Show-rate reminders started for appointment {id}", and the reminders run as
usual from then.

**What to do.** Nothing if the "started" push follows within the hour. If it
does not, the store is still failing: check the appointment in GHL and send
the confirmation reminders by hand until it recovers.

## "Unheld call on the calendar for {lead}"

**What you see.** An urgent push when booking a call from a reply created the
GHL appointment but its reminder hold could not be written, or was written
but could not be checked (the store read failed twice), and GHL then refused
the silent cancel.

**What it means.** The call is on the calendar and nothing confirms its
reminders are held, so the lead could get a reminder for a call you never
approved. When the cancel works there is no push: the card says the
appointment was cancelled silently and why ("could not be held" or "its hold
was written but could not be checked").

**What to do.** Cancel the appointment in GHL without notifying the lead, then
answer the card as usual.

---

# Template auto-send (CT3)

Rule (2026-09-22): an engine email (counter-proposal, booking confirmation,
cadence touch, show-rate or no-show message) is sent automatically only when
its text is exactly a template you approved and unchanged since, the template
kill switch is off, and every send check passes (copy gate, opt-out marker,
lead reply hold, 07:00-19:00 CT send window, recipient check, slot rules);
anything else goes to you as an approval card (replies) or is held (cadence,
show-rate, no-show). These are the pushes and Job_Log rows that rule adds.
Approving, revoking and the kill switch are in `template_approvals.md`.
Nothing auto-sends until you approve its template in the emails doc and tell
Claude "done".

First replies are never auto-sent (rule of 2026-09-23). The engine drafts the
first reply (two held times, no booking link) and it always comes to you as a
card, whatever the approvals, the kill switch or the gate say; you send it
yourself from the thread. The same goes for any other reply to a lead no
reply of ours has reached yet (for example a counter-proposal or "that slot
just got taken" when their first answer names a time), with one exception: the
booking confirmation, when the time they named fits and the call is booked,
still auto-sends once its template is approved. If the lead's row cannot be
read, the lead counts as not answered yet. These cards say "Not auto-sent:
first replies are drafts you send yourself from the thread." (reason
`first_reply_draft_only` below).

## "Reply to send yourself: {name} ({label})"

**What you see.** The approval card for a lead no reply of ours has reached
yet (any reply but a booking confirmation, including a draft with no
template id; a lead row that cannot be read counts as not answered). Its
first line is "Send this yourself from the thread in Instantly, then tap Mark
sent." Its buttons are **Mark sent** and **Veto** (plus "Book {time}" when
they asked for a time outside your slot rule); there is no Approve and no
Edit, and tapping the push opens the Mark sent page. On a public ntfy topic
it is titled "Reply to send yourself: {label}" and names no one; the full
card is in the email.

**What it means.** The engine never sends a reply to a lead we have not
answered yet (except a booking confirmation): you send it yourself, and
Mark sent tells the engine you did.

Every approval card that has it (this one and the ordinary "Reply to
approve" card) shows what the lead wrote above the draft: "They wrote:",
their reply with the quoted history cut and capped at about 1,500
characters ("[cut: the rest is in the Instantly thread]"), a line of dashes,
then the draft under "Your reply, to send yourself from the thread:" (or
"Your reply (Approve sends it):" on an ordinary card). The lead's words go to
the email and to a protected topic only, never to the public topic. Cards
raised before this change have no "They wrote" part.

**What to do.** Open the thread in Instantly, send the draft (edit it there
if you want), then tap **Mark sent** and confirm. Mark sent sends nothing: it
records the card as sent by hand (`sent_manually`), adds
`reply_sent_manually` to the lead's history (so the lead counts as answered
and later replies can auto-send again), keeps the offered times held and
arms the follow-ups, as for any sent reply. It never confirms a call the
card holds: that call stays held and "Call for {lead} still held after Mark
sent" says what to do in GHL. Mark sent takes a pending card only when it is
this kind; an ordinary pending card is refused as before. Veto drops the
card if you do not want to answer. The approve link still works if you open
it yourself, but the card does not offer it.

## "Auto-sent from approved templates: {n} sent, {q} queued, {h} held"

**What you see.** A normal-priority push, at most one per 30 minutes, only
when something happened. The push lists counts per template id (for example
`booking.counter.weekend: 2 sent`) and a "Held" list with a count per
template id, then "To stop these, set the kill switch, or revoke a template
from your terminal (jobs/approve_templates.py --revoke <id>)." It has no buttons and no names, addresses,
subjects, bodies or links, because the ntfy topic is public unless `NTFY_TOKEN` is set. The email copy
adds a "Per card" list: the lead's address, the template id and the status,
and for a reply queued until 07:00 CT when it goes out and a **Veto** link.

**What it means.** "Sent" and "queued" are replies that went out (or will at
07:00) with no tap from you, through the same send path and checks as an
Approve. In shadow (MODE=shadow, where the push only reaches you with
NOTIFY_SHADOW_SEND=1) nothing reached a lead: the title reads "Auto-sent from
approved templates (shadow): {n} would have sent (shadow), {q} queued, {h}
held" and the lines say "would have sent (shadow)" instead of "sent". "Held" counts cadence, show-rate and no-show messages that did not go
out because their template is not approved or the gate refused them. If the
push fails, its lines are put back and go out with the next one.

**What to do.** Nothing, normally. To stop a queued reply, open the email copy
and use its Veto link before 07:00 CT. If a template sent something you would
not have sent, revoke it (`template_approvals.md`, "Revoking"). A held count
that keeps growing means a ladder template you have not approved yet.

## "Template parity {status}: auto-send off"

**What you see.** An urgent push, at most once a day: "Template auto-send is
OFF: every engine email becomes a card or a hold.", the parity status
(`mismatch`, `reference_missing` or `error`), how many template ids differ and
up to 20 of them. Ids only, never text.

**What it means.** The deployed app built its template catalogue and it does
not match `config/template_catalogue_hashes.json`, the reference the deploy
preflight wrote (step 7), or the reference is missing or unreadable. Until
that is fixed nothing auto-sends: replies are cards and every cadence,
show-rate and no-show message is held, reminders before booked calls included.
`/health` shows the same under `templates.parity`.

**What to do.** From your own terminal, run the deploy preflight again on the
code you are deploying (it runs `template_parity.py --write`, then `--check`),
commit the reference file with that code, and redeploy
(`runbooks/deployment.md`, check 7).

If the mismatch comes back after a fresh preflight and redeploy, the laptop
and Modal render some template differently, so redeploying again will not
help. The laptop already runs the same pydantic (2.12.5) and pytz (2023.3) as
the Modal image, which installs `services/reply_engine/requirements.txt`; the
top-level `requirements.txt` now pins the same versions for every package the
two files share (`changesets/tests/test_requirements_agree.py`). So the real difference today is Python: 3.9.6 on the laptop against
3.11 in the image. That difference has been checked: on 2026-09-23 a local
Python 3.11 rendered every approvable template of the catalogue of that time
(111) exactly as the laptop's 3.9.6 does (fastapi was stubbed out). The check
was repeated later that day on today's 108 templates, with the laptop's own
fastapi, starlette and anyio on the 3.11 path: the same 108 ids and the same
digest (392b01cd05449198). The Modal image itself was not tested; the parity
check in the preflight catches any difference.

If the differing ids are the three `booking.already_booked.*` ones, the likely
cause is that `services/reply_engine/app.py` could not be imported where the
reference or the app's own catalogue was built, for example because a
dependency such as fastapi is missing there, which leaves those three
templates with no text. Check that environment's imports first. On Modal, a
failed import makes `/health` answer `"app": "missing"` with the error in
`detail`. On the laptop, with the `python3` that wrote the reference,
`python3 jobs/approve_templates.py --show booking.already_booked.awaiting_approval`
prints "app.py could not be imported here" and the error when the import fails
there.

For any mismatch that a Python or library version difference causes (after an
upgrade on one side, for example), either run the whole preflight and the
deploy (`install_schedules.sh --preflight`, then `--deploy ...`) from one
shell whose `python3` is Python 3.11 with the image's requirements
(`services/reply_engine/requirements.txt`) plus `modal` and `pytest`, which
the preflight and the deploy also use. Step 7 rewrites the reference with
whichever `python3` runs it, so a reference written any other way is
overwritten by the next preflight. Export, review and approve the templates
from that same environment too. An approval stores each template's hash as
the approving environment renders it, and Modal compares that with its own.
An approval made under 3.9 reads as `changed_since_approval` on Modal for
every template that renders differently there, and `--approve-all-shown`
refuses a review file exported in a different environment when any template
in it renders differently between the two. Or report the differing ids from
the alert so the formatter can be fixed in code. Until the mismatch is fixed,
auto-send stays off: every reply is a card and every cadence, show-rate and
no-show message is held.

## "Cadence stopped: template {id} not auto-sendable"

**What you see.** A high-priority push: a cadence day was held for 3 business
days (the reason, and the template ids), so that lead's follow-up ladder is
stopped as `template_unapproved`, and one sentence on what to do for the
reason that stopped it. The lead and a signed Resume link, valid 48 hours, go
only where they may:

- a protected ntfy topic (NTFY_TOKEN, or NTFY_ALLOW_SENSITIVE=1): in the push
  itself, as text and as a Resume button (the email leg, when it is set too,
  gets the same text);
- a public topic with the email leg set (NOTIFY_EMAIL, GMAIL_SENDER_EMAIL,
  GMAIL_APP_PASSWORD): ids and counts only on ntfy, the lead and the link on
  the email leg only;
- a public topic and no email leg: the push says "No channel can carry the
  Resume link" and names what to set. No link went anywhere, and none is
  recorded as sent.

A `template_unapproved_stop` Job_Log row goes with it (the deploy watch fails
on it).

**What it means.** That day's email was never sent. Each day it was held it
showed in the cadence digest as `held_template` and in the FYI's held count.
The 3 days are business days on which the day was held for a reason a fix on
this lead's side can clear, whatever the reasons and in any order. A kill
switch, a parity failure or a gate that could not read its files holds every
ladder but never counts, never resets the count and never stops one (the day
goes out late once it clears); an approval hold after such a pause continues
the count it had before it. The count starts again only when the day is
sent, or the ladder is re-armed or resumed.

**What to do.** Fix the cause the push names:

- `unapproved` or `changed_since_approval`: approve the ids from your own
  terminal (`template_approvals.md`).
- `nonconforming` or `copy_gate`: approving changes nothing. The lead's
  first name, company or thread subject does not fit the template, or the
  copy check refused it. Fix the lead's record, or answer the lead by hand
  from the Instantly inbox.
- any other reason: the id cannot be auto-sent as it stands; it needs a code
  or catalogue fix.

Then open the newest Resume link (in the push on a protected topic, else in
the email) and press Resume. While the ladder stays stopped, a fresh link is
sent the same way once a day ("Cadence still stopped: template {id}", low
priority), for at most 8 reminders and at most 14 days from the stop
(`cadence.TEMPLATE_STOP_REMINDER_MAX_PUSHES` / `_MAX_DAYS`, counted in
`template_hold.link_count`). After that the reminders end but the ladder
stays stopped until someone presses Resume. For an approval stop, one more
push comes as soon as the held ids pass the gate ("Cadence ready to resume:
template {id} is approved"), cap or not. Neither comes once
the lead opted out, was blocklisted, booked, or answered hostile, lost, wrong
person or not now: a Resume would stop the ladder again at once. The page
says whether the held ids pass the gate now. Nothing is sent from it: the
next tick runs the template gate and every send check again and sends the
day only if all pass (a D1 first opens a fresh 30-minute Veto window, and its
old refusal is dropped, so the full check runs afresh); otherwise the day is
held again. If the push says no Resume link could be signed, set BASE_URL and
REPLY_ENGINE_SECRET; the link comes on the next tick. If it says no channel
can carry the link, set NTFY_TOKEN (or NTFY_ALLOW_SENSITIVE=1), or all three
of NOTIFY_EMAIL, GMAIL_SENDER_EMAIL and GMAIL_APP_PASSWORD, in `.env` and
redeploy (`runbooks/deployment.md`, step 2a); the first tick after that sends
the link.

## A card whose first line is "Not auto-sent: ..."

**What you see.** An approval card whose first line (the second, under "Send
this yourself ...", on a "Reply to send yourself" card) says why the gate did
not let it go on its own: an ordinary card ("Reply to approve: {name}
({label})", with Approve, Veto and Edit), or the send-yourself card above. The reason sentences (`approval.REASON_TEXT`):

| Reason | The line says "Not auto-sent: ..." |
|---|---|
| `kill_switch` | template auto-send is switched off (the kill switch). |
| `parity_failed` | the deployed templates do not match the approved catalogue (parity check); nothing auto-sends until the deploy is fixed. |
| `no_template` | this draft was not written from a catalogue template. |
| `not_template_render` | this draft is not the plain template text (it was polished or edited). |
| `unknown_id` | its template is not in the catalogue for this kind of email. |
| `unapproved` | its template is not approved yet; approve it in the emails doc, then tell Claude "done". |
| `changed_since_approval` | its template changed since you approved it; review it and approve it again in the emails doc, then tell Claude "done". |
| `first_reply_draft_only` | first replies are drafts you send yourself from the thread. |
| `not_approvable` | its template cannot be approved for auto-send. |
| `stale_render` | the template changed after this draft was written. |
| `classification` | the reply was not read as a clear positive with enough confidence. |
| `requested_override` | the lead asked for a time outside your slot rule; choose the counter-proposal or Book as asked. |
| `copy_gate` | the draft failed a copy check (a banned word, a figure or a link). |
| `nonconforming` | the text is not exactly the approved template with valid values filled in. |
| `registry_error` | the template check could not run, so it was treated as not approved. |
| `cancel_pending` | the lead's previous call is still being cancelled in GHL; check the calendar before sending. |
| `send_failed` | the send to Instantly failed, so the reply may or may not have gone out; check the thread in Instantly before you press anything. |
| `recipient_mismatch` | the thread's last message is from somebody other than the lead, so nothing was sent; check the thread in Instantly. |
| `recipient_unconfirmed` | the thread could not be re-read to confirm the lead wrote it, so nothing was sent; check the thread in Instantly. |
| `send_raised` | the send stopped on an error, so the reply may or may not have gone out; check the thread in Instantly before you press anything. |

`first_reply_draft_only` covers a first reply, and any reply but a booking
confirmation to a lead no reply of ours has reached yet.

The last four are a send that ended at `send_failed`: see the next section.

A first reply's card, and the card of any reply with a template id but a
booking confirmation to a lead not answered yet, says `first_reply_draft_only`
(a reply with no template id shows the gate's own reason): that check runs
before the gate, so approving the template, the kill switch and the gate's
own reason make no difference to it, and the `unapproved` advice never
appears on it. The one gate reason still shown after it is a pending GHL
cancel: "... from the thread. Also, the lead's previous call is still being
cancelled in GHL; check the calendar before sending." The Job_Log `created`
row carries `auto_reason: first_reply_draft_only`, and a first reply the
engine was about to auto-send anyway (a card raised before this rule, or one
queued overnight) is turned back into a card with a
`template_auto_send_refused` row with that reason.

A few lines come from the card path rather than the gate: "the template check
was for another draft.", "the draft has a problem to fix first (see
VALIDATION).", "the card changed after the template check.", "the auto-send
failed (<error type>).", or, when the send itself stopped, the card's
problems or "the offered times are no longer offerable". A card the gate
allowed but that the send-time re-check refused (a revoke, the kill switch or
a redeploy between queueing and 07:00) comes back as a pending card with this
line too.

**What it means.** Nothing was sent. The card is a normal card from here: the
5-minute chase and the 48-hour expiry apply.

**What to do.** Answer the card as usual. If the reason is `unapproved` or
`changed_since_approval` and you want that email to go on its own next time,
review and approve the template. For `parity_failed`, see the parity alert
above. For `cancel_pending`, check the GHL calendar first.

## "Reply to approve: {name} ({label}, not sent)"

**What you see.** A high-priority card whose first line is "Not auto-sent:
..." with one of the last four reasons above, then what to do. Its buttons
are the ones that take a failed card, never Approve: **Retry**, **Veto**, and
**Mark sent** unless the recipient check held it. The email copy has the
whole card (lead, subject, body) and an **Edit (after Retry)** link. On a
public ntfy topic the push is titled "Reply to approve: a reply was not
sent" and carries only the reason and what to do; the buttons and the card
are in the email.

**What it means.** The gate allowed the reply, and its send ended at
`send_failed`: Instantly raised, the recipient check held it and escalated
(a mismatch at once, a thread it could not re-read after 3 tries), or the
07:00 flush raised. The card is pushed once; the "Replies with no owner"
pushes keep reminding you until it moves.

**What to do.** Check the thread in Instantly. If the reply went out, press
Mark sent. If it did not, press Retry: the card goes back to pending, then
Approve it, or Edit it first. Veto drops it; reply by hand if you want to. A
card the recipient check held has no Mark sent: nothing reached Instantly,
and its next send checks the thread again.

## "Not auto-sent: the auto-send did not run (the engine stopped between the card and the send)."

**What you see.** An ordinary approval card with that first line.

**What it means.** The gate allowed the reply, so its card was stored without
a push, but the engine stopped before the send ran (a crash or a container
timeout). The poller's orphan sweep found the card at least 2 minutes later
and pushed it, once. Nothing was sent. It writes a
`template_auto_send_orphan_pushed` Job_Log row (the deploy watch fails on it).

**What to do.** Answer the card as usual. More than one in a day means the
pipeline is dying mid-reply: check the Modal logs.

## Job_Log row `template_auto_send_failed`

**What you see.** No push of its own; a Job_Log row (job
`reply_engine.approval`) with the lead, the card id and the error. The deploy
watch fails on it.

**What it means.** The auto-send of an allowed card raised. When the card was
left `pending`, `blocked`, `stale_slots` or `send_failed`, it was pushed to
you with "Not auto-sent: the auto-send failed (<error type>)." (a
`send_failed` one with Retry, Veto and Mark sent, as above). Nothing more is
pushed when it was left at `sending`: a send that started is chased by the
stuck-card pushes.

**What to do.** Answer the card if one came. Then read the error in the row
and the Modal logs; if it repeats, set the kill switch until it is fixed.

## Job_Log row `autosend_fyi_failed`

**What you see.** No push of its own; a Job_Log row (job
`reply_engine.poller`) with the error. The deploy watch fails on it.

**What it means.** Building or sending the auto-send FYI raised on a poller
tick. Nothing about any reply changed: the sends already happened or not. A
push that simply did not go out is logged differently (a `push_failed` row
with kind `auto_send_fyi`), and its lines are put back for the next push.

**What to do.** Nothing if the next FYI arrives. If the row repeats, read the
error in the Modal logs; until it is fixed you will not get the auto-send
summary, so check the Job_Log `template_auto_sent` rows instead.
