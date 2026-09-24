# Shared brief: booked-call reminders and no-show recovery (section 2, DRAFT 2026-09-23)

Status: shared parts drafted; "The sequence" section is filled in after Lorenzo picks the cadence (see `research/`). Model: `../1_email_followup/writer_brief.md`.

You are one of several writers. Each writer drafts ONE message of this sequence. A final editor ties them together. Write for Lorenzo Villarreal, founder of AdveroSolutions.

## The situation every message is written for
1. The lead got a cold email, replied that they are interested, and booked a 15-minute call with Lorenzo (they picked one of two times he offered, or used his booking link).
2. They already have: a short "Locked in for {when}" reply from Lorenzo in the original email thread, and a calendar invite with the Google Meet link.
3. These messages come from Lorenzo's own email address (a new email, so you write a subject) or, once texting is enabled, as a text from his business number (a number they have not saved, so every text says it is Lorenzo).
4. Reminders: goal is that they show up, on time, with the link at hand. If the time no longer works, the goal is a new time, not a silent no-show.
5. No-show recovery: they did not join. Goal is a new time on the calendar. Assume something came up; never guilt.
6. One ask per message.

## The sequence
TO FILL after Lorenzo picks the cadence.

## Placeholders you may use (and only these)
- {first_name}: their first name. If unknown the system writes "there".
- {company}: their company name (falls back to "your business").
- {when}: day, date and time, rendered like "Tue, Sep 29 at 2:00pm CT", with their local time in brackets when known, e.g. "Tue, Sep 29 at 2:00pm CT (3:00pm ET)".
- {time}: the time only, like "2:00pm CT".
- {call_link}: the Google Meet link. It can be missing; the system then uses a no-link variant, so write that too: say the link is on their calendar invite.
- {booking_url}: Lorenzo's booking page, for moving the call.
- {slots}: no-show messages only. Two open times, rendered like "Tue 12:05pm or Thu 4:30pm CT".

## The offers (the lead came from one of these six campaigns)
| Campaign | What we build | Price / guarantee answer |
|---|---|---|
| Cleaning, reactivation | Email + text sequences to every account that cancelled, stopped renewing or never closed; ready ones land on the calendar | $0 up front; 20 to 30% of first-year contract value on accounts brought back, a smaller cut on bigger lists, $0 if nothing closes |
| Bookkeeping, reactivation | Sequences to lost inquiries and former clients timed to tax season, quarterly estimates, year-end cleanup | $0 up front; 20 to 30% of first-year fees from clients brought back, $0 if nothing closes |
| Recruiting, reactivation | Sequences to dormant and near-miss client accounts | $0 up front; 20 to 30% of the first placement fee from accounts brought back, $0 if nothing closes |
| Cleaning, outbound (trigger) | Watch triggers (new leases, office expansions, property-manager changes, new construction); outreach under the client's name; walkthroughs on their calendar | Guarantee $24,000/yr in new cleaning contracts signed within 90 days or money back + $200 steakhouse gift card |
| Bookkeeping, outbound (trigger) | Watch triggers (new business formations, part-time bookkeeper job posts, second locations); outreach under the client's name | Guarantee $15,000 in new annual client fees within 90 days or money back + $200 gift card |
| Recruiting, outbound | Watch specialty roles open on job boards; outreach to hiring managers under the agency's name | Guarantee $40,000 in new placement fees within 180 days or money back + $200 gift card |

Reminders do not quote prices. Guarantees may be mentioned only as written above.

## Proof (real; use only these, exactly as stated; never invent a number or a client)
- Commercial roofer doing $150M/year: recovered about $6M worth of contracts within 6 months (reactivation system).
- Commercial roofer doing $150M/yr: about $180,000 in new contracts in 90 days (outbound system).
- $750M+ in annual bid volume runs through a routing and follow-up system he built for a commercial roofing contractor.
- $5M in loan applications in 30 days on $1,500 of ad spend for a lender.
- A software consultancy's qualified lead volume up 35% with an outbound system that personalizes each message.
- His own agency scaled to $10,000 a month on the same kind of system.

## Voice (hard rules; Lorenzo has rejected drafts for breaking these)
- The bar test: write it exactly as Lorenzo would text it. Short, plain, casual, human. Contractions are fine.
- Emails: 20 to 70 words, 2 to 4 short paragraphs, "Hey {first_name}," on its own line, "Lorenzo" on its own line at the end. Subjects: short, lower-key, no clickbait.
- Texts: one or two sentences, under 160 characters where possible (320 hard cap), start "Hey {first_name}, Lorenzo here." or similar so an unsaved number is not mistaken for spam.
- No em dashes, no en dashes, no exclamation marks, no emojis, no bullet points.
- Never mention AI, automation, reminders being scheduled, or "this is an automated message".
- Times always with am/pm and CT (the placeholders do this).
- No guessing about their business, no invented facts, no invented client names.
- No fake pressure ("last chance", countdowns). No guilt ("you missed", "I waited"). Things come up.
- Do not repeat another message's opener. Vary wording across the set.

## Output
Write your file to the path given in your task. Use this exact format:

```
# <id>: <one-line purpose>
Timing: <when it goes out>  Channel: <email | text>

## Version A
Subject: <email only>
<text exactly as sent, with placeholders>

## Version A, no call link (only if the message shows {call_link})
<text>

## Version B
...

## Version C
...

## Pick
<A, B or C> because <two short lines>.

## Notes for Lorenzo (optional, max 3 short lines)
```
Do not edit any file other than your own output file. No code changes, no git, no network. Do not read `.env` or credentials.
