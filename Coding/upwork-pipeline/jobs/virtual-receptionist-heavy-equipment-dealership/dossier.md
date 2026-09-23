# Dossier - Virtual receptionist/secretary for heavy equipment dealership

url: https://www.upwork.com/jobs/~022102791522302787270

## Who they are
- First name: unknown (no `client first name:` line in the metadata; the post
  is not signed). Beat 1 falls back to "your heavy equipment dealership".
- Company: unknown (the post names none; no domain or product name).
- Industry: heavy equipment dealership; in their words, "the machines we sell
  (Excavators, skid steers, forklifts, etc)", with a "facility" where buyers
  "come take a look/demo the machines in person".
- Location / timezone: New Jersey (US); account timezone America/Sao_Paulo.
  Preferred hire locations: United States, Colombia, Mexico, Canada,
  Venezuela, Ecuador (not required).
- Website read: none named.

## Client (from `client.json`)
no client intel

## Tools they named
None by name. The post says only "the CRM using very basic software" and
"sending invoices". Their history shows one tool: Retell ("Retell Voice Agent
Integration Investigation", fixed, April 2025, 5 stars).

Commitments (from their history and industry, stated plainly on the build as
representative because the post does not name them):
- Voice layer: Retell (their own history). It answers the phone and hands each
  request to n8n. Not live on their number; shown with sample calls.
- Workflow engine: n8n.
- CRM: HubSpot (free CRM tier fits "very basic software"). Not named in the
  post; representative.
- Invoicing: QuickBooks Online (the most common small-business invoicing tool
  in the US). Not named; representative.
- Inventory source: a Google Sheet of their stock. Not named; representative.
- Demo calendar: Google Calendar. Not named; representative.
- Texting the caller: a Twilio number. Phone system not named; calls reach
  Retell by call forwarding from their business line.

## Every number in the post
- "Usually 2-7 per day" (incoming calls).
- Metadata: "Hourly $5-$15", "FULL TIME", "entry level".
- Metadata: client record "3 contracts, 3 jobs with hires, 0 active", "$271
  spent", "5.0 over 1 review".
- Metadata: Retell job "April 2025"; website job "2021".
- Metadata: "0 invites, 0 interviewing, 0 hired"; bids "avg $11.40, range
  $5-$21.50"; "Connects to apply: 19".
Missing numbers they obviously have (asked in assessment, labelled inputs on
the build): days and hours open, demo hours at the facility, facility address,
stock count, average call length, invoices sent per month, deposit terms.

## Their requirements, verbatim, in their order
1. "take incoming calls of customers asking about the machines we sell
   (Excavators, skid steers, forklifts, etc)" / "answer all calls (Usually 2-7
   per day)"
2. "answer questions they have"
3. "shedule an appointment for them to come take a look/demo the machines in
   person at our facility"
4. "sending invoices"
5. "updated the CRM using very basic software"
Cross-cutting: "Must be proficient in English. Spanish is a bonus." Handled in
section 1 (greeting language) and in every spoken answer and text.

5 parts in your post, 5 sections on the canvas, plus an error alert section
after theirs.

## The odd ask only they would recognize
"come take a look/demo the machines in person at our facility": the whole call
exists to get a buyer onto the lot to see the machine run. Plus "Spanish is a
bonus": callers who start in Spanish get answered in Spanish, and the CRM note
is still written in English for the office.

## What their hiring history implies
Small, careful spender: $271 across 3 contracts, one 5.0 review. They already
paid for a "Retell Voice Agent Integration Investigation" (April 2025), so an
AI voice agent is not a new idea to them; they have now posted for a
full-time human at $5-$15/hr, entry level, preferring Latin American hires.
They judge on cost and on whether it simply works. The pitch has to (a) cost
less than the full-time seat, (b) cover the non-phone duties a voice agent
alone does not (invoices, CRM), and (c) be run for them, not handed over as
software to manage.

## Their likely data
One caller, one machine, one sale (illustrative):

```json
{
  "caller": "Luis Ortega",
  "company": "Ortega Site Work LLC",
  "phone": "+17325550148",
  "language": "es",
  "machine_asked_about": "mini excavator with a thumb",
  "matched_stock": {
    "stock_no": "EX-2231",
    "type": "Mini excavator",
    "year": 2019,
    "make_model": "Kubota KX040-4",
    "hours": 1860,
    "features": "hydraulic thumb, enclosed cab with heat and A/C",
    "price": 52900,
    "status": "Available"
  },
  "demo": "Thursday 2026-10-01 10:00 AM at the facility",
  "invoice": {"number": "1043", "amount": 52900, "deposit_paid": 5000}
}
```

## Sizing
Retainer sizing from their own numbers:
- Call rhythm: 2-7 calls a day across a full-time 8-hour day = one call every
  8/7 = about 1.1 hours to 8/2 = 4 hours. Full time pays for the hours in
  between.
- Their posted budget for the seat: full time = 40 h x 52 weeks / 12 = about
  173 h a month; x $5-$15 = about $870 to $2,600 a month.
- Calls a month = 2-7 x their open days a month (their input, not given).
- Voice minutes a month = calls a month x their average call length (their
  input, not given).
Sharpest insight (goes on the build and into a beat): "2-7 calls a day is one
call every 1 to 4 hours; this answers every one on the first ring, including
the ones that come in after hours."

## Three things they would recognize on screen
1. "2-7 calls a day" and "one every 1 to 4 hours": overview sticky and the
   section 1 note.
2. Excavators, skid steers, forklifts, and "take a look/demo the machines in
   person at our facility": section 3 label "3 - BOOK THE LOOK OR DEMO AT YOUR
   FACILITY", the inventory prompt, the sample (Kubota mini excavator, stock
   EX-2231).
3. English and Spanish: node "3 - Greet Them by Name in English or Spanish",
   the Spanish text confirmation in the booking step, and the English CRM note
   written from a Spanish call. Retell, from their own history, named on the
   section 1 trigger.

## Beat 1 draft
"This is your virtual receptionist for your heavy equipment dealership."
