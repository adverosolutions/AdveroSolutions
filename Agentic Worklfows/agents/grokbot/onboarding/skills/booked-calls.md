---
name: booked-calls
description: What happens between a lead booking a 15-minute discovery call with Lorenzo and the call itself, and what happens when they miss it. Covers the "Locked in" confirmation, pre-call reminders R2/R3/R4, the no-show recovery ladder (N1, N3-N9), exact approved copy, timing, stop rules, the nurture hand-off, Zoom/GHL dependencies and current status. Use for "reminder", "confirmation", "no-show", "missed the call", "rebook", "show rate", or any booked-call event.
---

# Booked calls: confirmation, reminders, no-show recovery

Goal: once a lead books, get them to show. If they miss, get them rebooked. If they never rebook, hand them to the 90-day nurture.

## Who does what (2026-09-25)
- Claude Opus 5.5 decides every step: which touch is due, which template, the filled text, whether it may go.
- Grok Bot executes: it sends exactly the text it was given, in the lead's thread, and reports back. It never writes, edits, shortens or picks copy.
- Only approved-template text, unchanged since approval, goes out without Lorenzo seeing it. Anything else is a hold card to Lorenzo.
- Nothing polls. Each step starts from an event: the booking (GHL appointment webhook or the engine's own booking), a timer set for the exact minute a touch is due, a Zoom join/start webhook, or Lorenzo marking a no-show. Send and retry procedure: see the `grok-operator` skill.

## Hard rules (Lorenzo, 2026-09-23, "Everywhere")
- **Email only.** No texts, no phone calls, no call or voicemail tasks, no pre-read.
- **Never a booking link.** The lead picks one of two offered times; Lorenzo sends the calendar invite.
- **Earlier times are always "taken".** Any email that offers new times after an earlier email offered times the lead did not book says those times got taken.
- **Every email is a reply in the lead's cold-email thread, from the same inbox**, under "Re: <thread subject>". The template's own subject is used only when the lead has no thread at all (then it goes as a GHL email).
- A GHL email is never a fallback for a broken thread, an unknown or mismatched lead, or an unconfirmed recipient: those hold.
- The recipient is always the lead, and the thread is re-read to confirm the lead wrote it before a reply goes.
- Send window 07:00-19:00 CT. Calls sit 12:00-18:00 CT, Mon-Fri.
- No Claudeisms (see `claudeisms`), normal capitalization, no em or en dashes, no exclamation marks, no emojis, signed "Lorenzo".
- Pricing and guarantee figures never appear in any email (Lorenzo, 2026-09-24: "We never talk numbers over email.").
- Calls run on Google Meet today. The widget confirmation, R2/R3/R4 and N1-N9 say "call link", never "Zoom". The engine's "Locked in" confirmation names Zoom only in its `zoom_link` variant, which is used only when a Zoom link is on file.

## Placeholders
- `{first_name}`, `{company}`, `{call_link}` (Meet or Zoom link; each email has a no-link variant).
- `{when}` / `{time}`: CT, with the lead's local time in brackets when known and not CT: "2:00pm CT (3:00pm ET)", "Thu, Oct 1 at 2:00pm CT (3:00pm ET)".
- `{slots}`: two reserved times, soonest first, never offered to anyone else, refreshed if they pass: "Fri 12:30pm or Mon 3:00pm CT".

## Confirmation
- **Engine booking** (Opus booked from a reply): the "Locked in" reply is the confirmation. Lorenzo, 2026-09-23: fine as is, leave it. Text:
  - with a Zoom link: "Locked in {when}, invite on the way. Here is the Zoom link:\n{link}\n\nI will keep it to 15 minutes."
  - without: "Locked in {when}. The calendar invite with the video link follows in a separate email. I will keep it to 15 minutes."
  When this goes, the separate `confirm_email` is skipped for that call.
- **Widget booking** (`show_rate.confirm_email.<niche>_<offer>`, 8 variants): "Locked in for {when}. The calendar invite is on its way with the call link[, and here it is too so you do not have to dig: {link}]", then a three-line agenda (what made you write back now; a niche/offer line; "if it makes sense to work together, a concrete plan for ... If it doesn't, I'll still send you a plan I think would help where you are now."), then "If anything comes up before then, reply here and we will move it." Subject when no thread: "Confirmed: {when}, 15 minutes with Lorenzo". Skipped if the booking is more than 2 h old when first seen.

## Reminders

| Booked | Gets |
|---|---|
| 24 h+ out, and 6 h+ before R2's send time | confirmation, R2 at -24 h, R4 at -1 h |
| later than that, not same day | confirmation, R3 at 08:30 lead-local on the call day, R4 at -1 h |
| same day | confirmation, R4 at -1 h |

R2 is also skipped (R3 goes instead) when -24 h lands on a weekend or outside 07:00-19:00 CT. Any reply to R2 or R3 counts as a yes. A reschedule builds a new schedule and cancels the old pending touches. One email per call at a time: if several are due together, only the latest that can still go is sent. Max lateness: confirmation 2 h, R2 6 h, R3 3 h, R4 30 min; past that the touch is dropped, not sent.

**R2, day before** (`show_rate.reminder_24h_email`, subject "Tomorrow's call")
```
Hey {first_name},

Still good for tomorrow? I have you down for {when}. A quick yes works.

Link for tomorrow: {call_link}

If the time doesn't work anymore, just reply and I'll send a couple of other times.

Lorenzo
```
No link: "The link is on your calendar invite."

**R3, morning of** (`show_rate.reminder_morning_email`, subject "Today's call")
```
Hey {first_name},

Morning. Are we still set for {time} today? Link's here: {call_link}

If something came up, just reply and we'll find another time.

Lorenzo
```
No link: "Morning. Are we still set for {time} today? The link's on your calendar invite."

**R4, one hour before, everyone** (`show_rate.reminder_1h_email`, subject "See you at {time}")
```
Hey {first_name},

Talk in an hour. Here's the link:
{call_link}

If {time} won't work after all, reply here and we'll move it.

Lorenzo
```
No link: "Talk in an hour. The call link is on the calendar invite from when we booked."

## No-show recovery
S = scheduled start. "Day N" = N business days after the miss, 10:00 in the lead's zone (CT if unknown). Timing and copy approved 2026-09-24.

| Case | Sequence |
|---|---|
| First miss | N1 S+5, N3 ~S+25, N4 day 1, N5 day 2, N9 day 3, N6 day 5, N7 day 7, then nurture |
| Second miss | N1, N3 `.repeat` ~S+25, N6 day 3, then nurture |
| Third miss | N1, N8 ~S+25, then nurture and stage Lost |

What triggers it:
- **N1** needs Zoom join data: the meeting started or the host joined, and the lead has not. Sent once, S+5, never at or after S+10.
- **N3** goes at the later of the no-show flag and S+25. Without Zoom, detection reads "unknown" and nothing starts until Lorenzo marks the no-show by hand (today's path while calls are on Meet).
- Later emails follow the table.

What stops it: any reply from the lead after the call's start (an out-of-office counts today), a rebooking, or a late join (the flag reverses).

Spacing and slot rules:
- No two emails of a ladder reach the lead less than 8 h apart. A late email closes as superseded once the next is due within 8 h; the last email of a ladder is never closed that way, it waits 8 h after the previous one so the hand-off still runs.
- One email per lead per run.
- N4/N5/N6 ("taken" emails) go only after an earlier slot email reached the lead, and only then release the earlier times.
- N5 needs the lead's niche and offer; with none on file it is skipped, never filled with a generic line.
- If a send may have gone out but the result is unclear, check the thread before anything else. Never resend blind.

Hand-off: after N7 (first miss), N6 (second) or N8 (third), `nurture.enroll(lead_email, "no_show_no_rebook", now)`. Research suggests the first nurture touch no sooner than 3-4 weeks after. GHL after each miss: the first moves the stage to Follow Up Later. The second leaves the stage alone and adds the note "Second no-show; recovery limited to two touches per SOP-005. Watch for a pattern." The third moves the stage to Lost. Recovery never moves an opportunity already in Proposal Sent, Won or Lost.

### Approved copy (subjects only used with no thread)

**N1** `no_show.ns_still_on_email`, "I'm on"
```
Hey {first_name},

I'm on the call now. Here's the link:
{call_link}

Lorenzo
```
No link: "I'm on the call now. The link is on your calendar invite."

**N3** `no_show.ns_reschedule_email`, "New time for our call"
```
Hey {first_name},

Looks like I missed you on our call today. I understand things come up, so let's get another call on the books at a time that works well for you.

Could we do {slots}? Just reply with the one that works.

Lorenzo
```

**N3 second miss** `no_show.ns_reschedule_email.repeat`, "Missed you again"
```
Hey {first_name},

Looks like I missed you again on today's call. If this isn't a priority right now, just let me know. If you still want to talk, I can do {slots}. If you're not looking to grow {company} right now, that's fine too, just tell me.

Lorenzo
```

**N4 day 1** `no_show.ns_d1_email`, "Two open times"
```
Hey {first_name},

Those two times got taken, but I can do {slots} if you still want to find 15 minutes. Just reply with the one that works.

Lorenzo
```

**N5 day 2** `no_show.ns_d2_value_email.<niche>_<offer>`, "One thing for {company}"
```
Hey {first_name},

One thing I was going to walk you through on our call:

{niche_point}

The last two times got taken, but if that's worth 15 minutes, I've got {slots} open. Just say which one works.

Lorenzo
```
`{niche_point}` (cleaning, bookkeeping, recruiting only):
- Cleaning, reactivation: I'd set up emails and texts to every account that cancelled, stopped renewing or never closed, and the ones ready to talk land on your calendar.
- Bookkeeping, reactivation: I'd reach back out to your lost inquiries and former clients, timed around tax season, quarterly estimates and year-end cleanup.
- Recruiting, reactivation: I'd set up follow-up sequences to your dormant and near-miss client accounts.
- Cleaning, outbound: I'd watch for new leases, office expansions, property-manager changes and new construction, then reach out under your name and put walkthroughs on your calendar.
- Bookkeeping, outbound: I'd watch for new business formations, part-time bookkeeper job posts and second locations, then reach out to those businesses under your name.
- Recruiting, outbound: I'd watch job boards for open roles in your specialties, then reach out to the hiring managers under your agency's name.

**N9 day 3** `no_show.ns_d3_retry_email`, "Still want to talk?"
```
Hey {first_name},

Trying once more to get our call back on the calendar. I can do {slots}. Just reply with the one that works.

Lorenzo
```

**N6 day 5 (day 3 on a second miss)** `no_show.ns_d5_yes_no_email`, "Quick one"
```
Hey {first_name},

Quick one on the call: still want to chat, later, or not a fit?

A one-word answer is plenty. If it's later, just tell me roughly when. If you still want to chat, the last two times got taken, but I can do {slots}.

Lorenzo
```

**N7 day 7** `no_show.ns_d7_breakup_email`, "Leaving the door open"
```
Hey {first_name},

I'll leave this with you for now.

If the timing gets better later on, just reply here and I'll send over a couple of times.

Lorenzo
```

**N8 third miss** `no_show.ns_third_miss_email`, "Closing this out"
```
Hey {first_name},

Missed you again today. I don't think this is worth pursuing anymore, and it doesn't make sense for either of us. Wish you the best of luck with {company}.

Lorenzo
```

## Status (as of 2026-09-24/25)
- Built and tested in shadow; nothing live. Every email above is held until Lorenzo approves its template id (renamed ids do not carry old approvals).
- Waiting on Lorenzo: connect Zoom in GHL (N1 and automatic detection need it); approve the ids; decide N3's "today" wording when a no-show is marked on a later day.
- The trigger wiring for the Grok model (appointment and Zoom webhooks to Grok, per-touch timers) is not built yet.
- Known gaps: a later ladder email can re-offer a time an earlier one called taken (seen for London leads); an out-of-office stops the ladder; a no-show marked by hand between about 19:00 and 01:00 CT loses N3 (too late) and starts at N9; leads in UTC+7 zones get day emails about a week late.
