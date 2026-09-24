# Pre-call reminders, final set (signed off by Lorenzo, 2026-09-23)

Editor pass over `drafts/R1.md` to `drafts/R5.md`, then Lorenzo's walkthrough in chat. Nothing is approved in the template registry or live yet; the build uses this file as the source of truth for copy.

## Lorenzo's decisions in the walkthrough
- **Email only, everywhere.** No texts and no phone steps in either sequence: every lead has an email (that is what they replied to), a phone number is hit or miss. The SMS legs and call tasks come out of the schedules.
- **No pre-read email** (R1 dropped): the lead read the whole email sequence and asked for the call. The pre-read touch and `prompts/show_rate_preread_*.md` go.
- **No 4-hour personal call** (R5 dropped, email only).
- **R2 skip rule:** if the booking was made less than 6 hours before R2 would go out, skip R2 and send R3 the morning of the call instead.
- **Local time:** time-only lines show the lead's local time in brackets when it differs from CT, e.g. "2:00pm CT (3:00pm ET)", the same way `{when}` already does.
- **Capitalized subjects** (new voice rule: normal capitalization). Subjects are used only when the lead has no thread.
- **No Claudeisms** (new voice rule): R4 lost "so you don't have to dig for the invite".
- All emails go as replies in the lead's cold-email thread, from the same inbox; a GHL email only when no thread exists.

## What a lead receives

| Booked | Gets |
|---|---|
| 24 h or more before the call, and at least 6 h before R2 | "Locked in" confirmation (unchanged), R2 at 24 h, R4 at 1 h |
| Later than that, but not the same day | "Locked in", R3 at 8:30am their time on the call day, R4 at 1 h |
| Same day | "Locked in", R4 at 1 h |

Booking-link (widget) bookings get the existing show-rate confirmation email instead of "Locked in"; its text is unchanged apart from the Claudeism check in the build.

---

## R2: day-before check
Timing: 24 hours before the call (see the skip rule). Channel: email. Any reply counts as a yes.

Subject (only used when there is no thread): Tomorrow's call

```
Hey {first_name},

Still good for tomorrow? I have you down for {when}. A quick yes works.

Link for tomorrow: {call_link}

If the time doesn't work anymore, just reply with one that does, or grab a new slot here: {booking_url}

Lorenzo
```

No-link variant:

```
Hey {first_name},

Still good for tomorrow? I have you down for {when}. A quick yes works.

The link is on your calendar invite.

If the time doesn't work anymore, just reply with one that does, or grab a new slot here: {booking_url}

Lorenzo
```

---

## R3: morning-of check
Timing: 8:30am the lead's local time on the call day, only when R2 was skipped (booked after the 24-hour mark, or less than 6 hours before it), and not for same-day bookings. Channel: email. Any reply counts as a yes.

Subject (only used when there is no thread): Today's call

```
Hey {first_name},

Morning. Are we still set for {time} today? Link's here: {call_link}

If something came up, reply with a better time or grab one here: {booking_url}

Lorenzo
```

No-link variant:

```
Hey {first_name},

Morning. Are we still set for {time} today? The link's on your calendar invite.

If something came up, reply with a better time or grab one here: {booking_url}

Lorenzo
```

---

## R4: one-hour heads-up
Timing: 1 hour before the call, to everyone, including leads who already said yes. Channel: email. No question; the only ask is the out.

Subject (only used when there is no thread): See you at {time}

```
Hey {first_name},

Talk in an hour. Here's the link:
{call_link}

If {time} won't work after all, reply here and we'll move it.

Lorenzo
```

No-link variant:

```
Hey {first_name},

Talk in an hour. The call link is on the calendar invite from when we booked.

If {time} won't work after all, reply here and we'll move it.

Lorenzo
```

---

## Placeholders
`{first_name}`, `{when}` (e.g. "Thu, Oct 1 at 2:00pm CT (3:00pm ET)"), `{time}` (e.g. "2:00pm CT (3:00pm ET)"; local part only when the lead's zone is known and not CT), `{call_link}`, `{booking_url}`.

## Read as one thread (Dana, Brightline Cleaning, call Thu, Oct 1 at 2:00pm CT, booked Mon)

```
Hey Dana,

Locked in Thu, Oct 1 at 2:00pm CT. The calendar invite with the video link follows in a separate email. I will keep it to 15 minutes.

Lorenzo
```

```
Hey Dana,

Still good for tomorrow? I have you down for Thu, Oct 1 at 2:00pm CT. A quick yes works.

Link for tomorrow: https://zoom.us/j/123

If the time doesn't work anymore, just reply with one that does, or grab a new slot here: https://book.example/lorenzo

Lorenzo
```

```
Hey Dana,

Talk in an hour. Here's the link:
https://zoom.us/j/123

If 2:00pm CT won't work after all, reply here and we'll move it.

Lorenzo
```
