# Dossier - Make.com Automation for Lead Follow-Up & CRM Setup

url: https://www.upwork.com/jobs/~022103211339503297421

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown
- Industry: unknown. The post says only "lead follow-up", "CRM updates" and
  "ongoing lead management", so a business that gets leads and follows them up.
  Their hiring history (website forms, a scheduling tool, SMS compliance) points
  to an appointment-style service business or an agency, but that is inference,
  not stated.
- Location / timezone: United Kingdom (Europe/London)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
1. "Make.com" (title and body: "setting up a Make.com workflow")
2. "CRM" (no product named)

Committed CRM: **GoHighLevel**. Their recent hires are a GoHighLevel A2P 10DLC /
Twilio registration and a GoHighLevel website build, so GHL is almost certainly
where their contacts live. Built as GoHighLevel API v2 calls (`net.http`,
services.leadconnectorhq.com) inside Make. The assessment asks them to confirm.
Never say "any CRM", and never tell them we read their hiring history.

Lead source: a website form posting into a Make custom webhook. Their history
also shows a Squarespace form + Acuity Scheduling job and a Wix Studio form
build, so the form tool is not certain; the canvas says "Your Website Form" and
the assessment asks which one.

Follow-up channel: text from their GoHighLevel number (they registered for SMS
sending), then their own GoHighLevel follow-up sequence.

## Every number in the post
The post body has no numbers. From the metadata paragraph:
- "Hourly $5-$40", intermediate, part time, short-term
- "52 contracts, 50 jobs with hires, 0 active"
- "$720 spent" (about $14 per contract)
- "5.0 over 51 reviews"
- "1 invite, 0 interviewing, 0 hired"
- "Recorded bids avg $44.04, range $5-$777.78 (basis unspecified)"
- "Connects to apply: 14"

No lead volume, no number of forms, no number of sources, no follow-up timing.
Lead volume and sources go under "Ask before quoting"; on the build they appear
only as settings the client fills (`PASTE-YOUR-...`), never as facts.

## Their requirements, verbatim, in their order
1. "automate lead follow-up"
2. "CRM updates"
3. "creating a reliable automation process"
4. "connecting key systems"
5. "ensuring data flows correctly between platforms"
6. "review the current setup, identify gaps"
7. "build a smooth workflow that supports ongoing lead management"

Six buildable parts plus one review ask. Part 6 is not a module: it goes in the
assessment, a section note and a beat. Parts 3, 4 and 5 are adjacent and
describe one thing (form, Make and GoHighLevel wired so nothing drops), so they
share section 3. Four sections on the canvas:
- Section 1 - LEAD FOLLOW-UP (part 1)
- Section 2 - CRM UPDATES (part 2)
- Section 3 - RELIABLE, CONNECTED, DATA FLOWING CORRECTLY (parts 3, 4 and 5;
  the note names the grouping and carries part 6's "gaps")
- Section 4 - ONGOING LEAD MANAGEMENT (part 7)

The first reply is written in section 1 and sent in section 4, after GoHighLevel
has confirmed the contact, so every reply lands in their GoHighLevel inbox.

## The odd ask only they would recognize
"You should be able to review the current setup, identify gaps": they already
have something running and want it audited before anything new is built. On
screen: section 3's note names the first gap checked (runs that fail without
anyone seeing). In a beat: "First I review your current setup and list the gaps".

## What their hiring history implies
52 contracts for $720 total, 5.0 across 51 reviews: a frequent hirer of small,
cheap, clearly scoped fixed jobs (a GHL SMS registration, a GHL website, form
integrations, a video editor). They judge work on "does it run", not on
strategy decks, and they are price-sensitive ($5-$40 an hour). A short build
they can see working, with a tight hour estimate, fits how they buy. Nothing
from this goes to the client.

## Their likely data
A website enquiry from a UK prospect: full name as typed, a UK mobile in local
format, a short message asking about a service and availability, the form name
and a London-time timestamp. Illustrative only (07700 900xxx is the Ofcom
range reserved for fiction).

```json
{
  "full_name": "hannah whitlock",
  "email": "Hannah.Whitlock@outlook.com",
  "phone": "07700 900418",
  "message": "Hi, I'd like to book an initial consultation. Are you free any evenings next week? Thanks",
  "form_name": "Website contact form",
  "submitted_at": "2026-09-24T18:42:00+01:00"
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a sizing job: the post gives no volumes. Make operations per lead come from
the build (13 modules; a new lead runs about 7-9 operations); monthly cost depends
on their lead volume, which is an ask.

## Three things they would recognize on screen
1. Their own words as the section labels, in their order: "LEAD FOLLOW-UP",
   "CRM UPDATES", "RELIABLE, CONNECTED, DATA FLOWING CORRECTLY", "ONGOING LEAD
   MANAGEMENT" (section notes on the Make canvas).
2. A UK enquiry with a local 07700 number saved to GoHighLevel as +44, British
   "enquiry" wording and a London timestamp (Sample Input, step 2's note, Final
   Output).
3. Their "review the current setup, identify gaps" ask, named in section 3's
   note as the first gap checked (failed runs nobody sees).

## Beat 1 draft
"This is lead follow-up and CRM updates in Make for your business."
