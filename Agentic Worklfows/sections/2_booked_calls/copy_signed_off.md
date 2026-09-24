# Section 2 copy, signed off by Lorenzo in chat (2026-09-23)

**Source of truth for the build.** Supersedes `reminders_final.md` and `no_show_final.md` wherever they differ. Every text here was shown to Lorenzo in full and approved. The template registry approval (`jobs/approve_templates.py`) is still his separate step after the build.

## Rules that shaped it (apply to every message)
- Email only. No texts, no phone calls, no call or voicemail tasks.
- Never a booking link. The lead picks one of the two times offered; Lorenzo sends the calendar invite.
- When an email offers new times after an earlier email offered times the lead did not book, it says those times got taken.
- Every email is a reply in the lead's cold-email thread, same inbox. The subject is used only when the lead has no thread (then it goes as a GHL email).
- No Claudeisms; normal capitalization; no em or en dashes, no exclamation marks, no emojis; signed "Lorenzo".
- `{time}` and `{when}` show the lead's local time in brackets when their zone is known and not CT: "2:00pm CT (3:00pm ET)", "Thu, Oct 1 at 2:00pm CT (3:00pm ET)".
- `{slots}` is two reserved times rendered like "Fri 12:30pm or Mon 3:00pm CT", soonest first, never offered to anyone else; refreshed if they pass before sending.

## Reminders

| Booked | Gets |
|---|---|
| At least 24 h out, and at least 6 h before R2's send time | "Locked in" confirmation (unchanged), R2 at -24 h, R4 at -1 h |
| Later than that, not same day | "Locked in", R3 at 08:30 lead local time on the call day, R4 at -1 h |
| Same day | "Locked in", R4 at -1 h |

Dropped: pre-read email (and `prompts/show_rate_preread_*.md`), confirmation SMS, 24 h SMS, 4 h unconfirmed task, 1 h SMS, 15 m SMS. The widget-booking confirmation email (`confirm_email`) stays; it has no booking link.

### R2, day-before check (-24 h). Any reply counts as a yes.
Subject: Tomorrow's call
```
Hey {first_name},

Still good for tomorrow? I have you down for {when}. A quick yes works.

Link for tomorrow: {call_link}

If the time doesn't work anymore, just reply and I'll send a couple of other times.

Lorenzo
```
No link on file: the link line reads `The link is on your calendar invite.`

### R3, morning-of check (08:30 lead local time, only when R2 was skipped; never same-day). Any reply counts as a yes.
Subject: Today's call
```
Hey {first_name},

Morning. Are we still set for {time} today? Link's here: {call_link}

If something came up, just reply and we'll find another time.

Lorenzo
```
No link on file: `Morning. Are we still set for {time} today? The link's on your calendar invite.`

### R4, one-hour heads-up (-1 h, everyone, including leads who confirmed)
Subject: See you at {time}
```
Hey {first_name},

Talk in an hour. Here's the link:
{call_link}

If {time} won't work after all, reply here and we'll move it.

Lorenzo
```
No link on file: `Talk in an hour. The call link is on the calendar invite from when we booked.`

## No-show recovery
S = scheduled start. Any reply from the lead stops the ladder. Rebooking cancels it. Day N = N business days after the missed call, 10:00 in the lead's time zone (weekends skipped). Timing and the N1, N9, second-miss and third-miss copy changed by Lorenzo on 2026-09-24.

| Case | Messages |
|---|---|
| First missed call | N1 at S+5 (not joined; needs Zoom join data), N3 at about S+25, N4 day 1, N5 day 2, N9 day 3, N6 day 5, N7 day 7, then `nurture.enroll(lead_email, "no_show_no_rebook", now)` |
| Second missed call | N1, N3 second-miss variant at about S+25, N6 on day 3, then nurture |
| Third missed call | N1, N8 at about S+25, then nurture |

Dropped: Lorenzo's call task and voicemail (N2), the day-1 SMS and its task, the "still on?" SMS.

### N1, "I'm on" (S+5, only if the lead has not joined)
Subject: I'm on
```
Hey {first_name},

I'm on the call now. Here's the link:
{call_link}

Lorenzo
```
No link on file: `I'm on the call now. The link is on your calendar invite.`

### N3, reschedule (about S+25)
Subject: New time for our call
```
Hey {first_name},

Looks like I missed you on our call today. I understand things come up, so let's get another call on the books at a time that works well for you.

Could we do {slots}? Just reply with the one that works.

Lorenzo
```

### N3, second missed call (about S+25)
Subject: Missed you again
```
Hey {first_name},

Looks like I missed you again on today's call. If this isn't a priority right now, just let me know. If you still want to talk, I can do {slots}. If you're not looking to grow {company} right now, that's fine too, just tell me.

Lorenzo
```

### N4, day 1
Subject: Two open times
```
Hey {first_name},

Those two times got taken, but I can do {slots} if you still want to find 15 minutes. Just reply with the one that works.

Lorenzo
```

### N5, day 2
Subject: One thing for {company}
```
Hey {first_name},

One thing I was going to walk you through on our call:

{niche_point}

The last two times got taken, but if that's worth 15 minutes, I've got {slots} open. Just say which one works.

Lorenzo
```
`{niche_point}` by campaign:
- Cleaning, reactivation: I'd set up emails and texts to every account that cancelled, stopped renewing or never closed, and the ones ready to talk land on your calendar.
- Bookkeeping, reactivation: I'd reach back out to your lost inquiries and former clients, timed around tax season, quarterly estimates and year-end cleanup.
- Recruiting, reactivation: I'd set up follow-up sequences to your dormant and near-miss client accounts.
- Cleaning, outbound: I'd watch for new leases, office expansions, property-manager changes and new construction, then reach out under your name and put walkthroughs on your calendar.
- Bookkeeping, outbound: I'd watch for new business formations, part-time bookkeeper job posts and second locations, then reach out to those businesses under your name.
- Recruiting, outbound: I'd watch job boards for open roles in your specialties, then reach out to the hiring managers under your agency's name.
- No campaign on file: no approved line. Hold N5 for that lead (do not invent a generic one) and go on to N9 on its day.

### N9, day 3
Subject: Still want to talk?
```
Hey {first_name},

Trying once more to get our call back on the calendar. I can do {slots}. Just reply with the one that works.

Lorenzo
```

### N6, day 5 (also day 3 after a second missed call)
Subject: Quick one
```
Hey {first_name},

Quick one on the call: still want to chat, later, or not a fit?

A one-word answer is plenty. If it's later, just tell me roughly when. If you still want to chat, the last two times got taken, but I can do {slots}.

Lorenzo
```

### N7, day 7 (no reply, no rebook). Then nurture.
Subject: Leaving the door open
```
Hey {first_name},

I'll leave this with you for now.

If the timing gets better later on, just reply here and I'll send over a couple of times.

Lorenzo
```

### N8, after a third missed call (about S+25). Then nurture.
Subject: Closing this out
```
Hey {first_name},

Missed you again today. I don't think this is worth pursuing anymore, and it doesn't make sense for either of us. Wish you the best of luck with {company}.

Lorenzo
```
