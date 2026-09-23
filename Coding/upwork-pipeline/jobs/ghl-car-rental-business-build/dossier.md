# Dossier - GHL Build for Car Rental Business

url: https://www.upwork.com/jobs/~022102802939328978346

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown (post names none)
- Industry: "rental car business" (their words); a car rental operator with a
  fleet they track by vehicle, maintenance, accidents/claims and tickets
- Location / timezone: client in Connecticut (US), account timezone
  America/Sao_Paulo
- Website read: none named

## Client (from `client.json`)
no client intel

## Tools they named
1. "Go High Level" (their GHL CRM; they already have it: "building out my Go
   High Level crm")
2. GHL's "opportunities tab" (pipelines and stages)
Nothing else named. SMS and email go out through GHL itself (LC Phone, LC
Email or their own sending domain); no outside tool is added.

## Every number in the post
- "several tabs", then four named: "a vehicles tab, maintenance tab,
  accidents/claims tab, and tickets tab" (4 tabs)
- No other number about their business: no fleet size, no rentals per month,
  no rates, no deposit amount, no fees.
- Metadata: hourly, no rate given; part time; expert. 18 contracts, 16 jobs
  with hires, 1 active, $4.8k spent, 4.98 over 14 reviews, 391 hours. Recorded
  bids avg $23.61, range $7-$95. 14 connects. 0 invites, 0 interviewing.
- Everything else (deposit, admin fee on tickets, rates, pickup address,
  after-hours phone, fleet size) is their input: custom values
  `{{custom_values.security_deposit}}`, `{{custom_values.ticket_admin_fee}}`,
  `{{custom_values.pickup_address}}`, `{{custom_values.after_hours_phone}}`,
  `{{custom_values.rental_agreement_link}}`, `{{custom_values.payment_link}}`,
  and "[DAILY RATE]" style inputs in the snippets.

## Their requirements, verbatim, in their order
0. "I need assistance building out my Go High Level crm for a rental car
   business." (the frame, not a separate part)
1. "I need to add several tabs and fields. I will need a vehicles tab,
   maintenance tab, accidents/claims tab, and tickets tab. I will need these
   set up with the proper fields in each."
2. "I will also need some text and email automations set up for different
   actions throughout the process."
3. "I will also need some snippets made for quick message responses."
4. "I will need some headings made in the opportunities tab."
5. "I am looking for someone who has already done a build out on GHL
   specifically for a car rental business." (a hiring filter, not a build
   part; Lorenzo has NOT built GHL for a car rental business, so the answer
   is the build on screen, never a claim)

4 build parts in the post. How they land:
- Part 1 (tabs) = four GHL custom objects. The API lane cannot create custom
  objects, so they are listed below with every field for the main session to
  put on screen (Lorenzo clicks them in by hand, or shows this list).
- Part 2 (text and email automations "for different actions throughout the
  process") = the spec's 5 sections, one per action in the rental process,
  each its own GHL workflow: 1 - NEW RENTAL INQUIRY, 2 - BOOKING CONFIRMED,
  3 - CAR RETURNED, 4 - ACCIDENT REPORTED, 5 - TICKET RECEIVED.
- Part 3 (snippets) = 12 snippet texts written below (not workflows).
- Part 4 (headings in the opportunities tab) = the pipeline "Rental Car
  Process" with 8 stages, created by `ghl_prereqs` from the `stages` list on
  step 3 and moved by every workflow. Never the "Sales" pipeline.

## The odd ask only they would recognize
Their own words for GHL objects: "tabs" for custom objects (with
"accidents/claims" written as one tab) and "headings made in the
opportunities tab" for pipeline stages. On screen: the four tabs by their
names in the task steps (20, 33, 39) and as custom objects, and the 8
headings across the opportunities tab. Named in beats 2 and 3.

## What their hiring history implies
18 contracts and 391 hours for $4.8k is about $12 an hour on average: a
frequent hirer of low-cost hourly help (a VA for CallTools / Smarter Contact /
REISift, real estate cold calling and seller-lead follow-up, a text blast, a
VSL, a WordPress site). 4.98 over 14 reviews: easy to work with. They already
run SMS-heavy tools (Smarter Contact), so texting renters is familiar. They
judge on "does it look already done for a rental car business", which is why
they ask for prior car rental GHL experience. Price-sensitive (bids avg
$23.61). New industry for them relative to the history (real estate before),
so they want someone who brings the rental structure, not a blank CRM.

## Their likely data
A renter contact in their GHL, mid-rental, with the rental fields filled and
the card in their pipeline (illustrative, not a real person):

```json
{
  "first_name": "Marcus",
  "last_name": "Delgado",
  "phone": "(203) 555-0147",
  "rental_vehicle": "2022 Toyota Camry SE - Silver",
  "pickup_date": "Fri Oct 2, 10:00 AM",
  "return_date": "Mon Oct 5, 10:00 AM",
  "tags": ["rental-booked"],
  "opportunity": {"pipeline": "Rental Car Process", "stage": "Booked - Docs Needed", "name": "Marcus Delgado - Rental"}
}
```

A ticket that arrives after the rental (Tickets tab record, illustrative):

```json
{
  "ticket_name": "Parking - Oct 3 - Camry SE",
  "ticket_type": "Parking",
  "citation_number": "PK-4471093",
  "violation_date": "Oct 3, 2:14 PM",
  "fine_amount": "$40.00",
  "vehicle": "2022 Toyota Camry SE - Silver",
  "renter": "Marcus Delgado",
  "status": "Renter Notified"
}
```

## Sizing (setup job: CRM build-out)
Their only number is 4 tabs. The rest of the size comes from the design, not
from their business:
- 4 tabs (custom objects) with 13 to 21 fields each, 66 fields, plus
  associations (car to renter, record to car).
- 5 workflows, 38 action steps, 8 opportunity headings, 7 tags, 7 contact
  fields, 6 custom values, 12 snippets.
- Their fleet size is their input ("Your Number of Vehicles"): it decides
  whether the Vehicles tab is filled by CSV import (a spreadsheet of the fleet)
  or by hand.
Sharpest insight: tickets and many claims arrive after the car is back, so a
ticket is matched to the renter by car and date. Every rental has to record
which car and which dates (Rental Vehicle, Pickup Date, Return Date on the
renter), and the ticket workflow hangs off the renter, not the open rental.
Second: repeat renters are normal in rentals, so every workflow clears its own
trigger tag first, or a returning renter's second rental would fire nothing.
Third (risk): US business texting from GHL needs A2P 10DLC registration on
their number, or carriers filter the texts.

## The four tabs (GHL custom objects) and their fields
Field types are GHL custom object field types; confirm the exact type names
in their account. Each object gets a primary display field (listed first).

### Vehicles
Associations: renters (contacts), Maintenance, Accidents/Claims, Tickets.
1. Vehicle Name (primary, text): "2022 Toyota Camry SE - Silver"
2. Status (dropdown): Available, Reserved, On Rent, In Maintenance, Out of Service
3. Year (number)
4. Make (text)
5. Model (text)
6. Trim (text)
7. Color (text)
8. VIN (text)
9. License Plate (text)
10. Plate State (text)
11. Current Mileage (number)
12. Daily Rate (currency)
13. Weekly Rate (currency)
14. Registration Expiration (date)
15. Insurance Policy Number (text)
16. Insurance Expiration (date)
17. Toll Transponder Number (text)
18. Next Service Due Mileage (number)
19. Notes and Photos (long text + file upload)

### Maintenance
Associations: one Vehicle.
1. Service Record (primary, text): "Camry SE - Oil Change - Sep 18"
2. Service Type (dropdown): Oil Change, Tires, Brakes, State Inspection,
   Detailing, Repair, Other
3. Status (dropdown): Scheduled, In Shop, Completed
4. Service Date (date)
5. Mileage at Service (number)
6. Shop or Vendor (text)
7. Cost (currency)
8. Out of Service From (date)
9. Back in Service On (date)
10. Next Service Due Date (date)
11. Next Service Due Mileage (number)
12. Receipt (file upload)
13. Notes (long text)

### Accidents/Claims
Associations: one Vehicle, one renter (contact).
1. Claim Name (primary, text): "Camry SE - Oct 3 - Rear-ended"
2. Status (dropdown): Reported, Waiting on Renter Info, Filed, Adjuster
   Assigned, Repair Scheduled, Paid, Closed, Denied
3. Date of Incident (date)
4. Incident Location (text)
5. What Happened (long text)
6. Police Report Number (text)
7. Police Department (text)
8. Other Driver Name (text)
9. Other Driver Phone (phone)
10. Other Driver Insurance Company (text)
11. Other Driver Policy Number (text)
12. Renter Insurance Company (text)
13. Renter Policy Number (text)
14. Insurance Claim Number (text)
15. Adjuster Name and Phone (text)
16. Repair Estimate (currency)
17. Final Repair Cost (currency)
18. Charged to Renter (currency)
19. Amount Recovered (currency)
20. Days Out of Service (number)
21. Damage Photos and Documents (file upload)

### Tickets
Associations: one Vehicle, the renter who had it (contact).
1. Ticket Name (primary, text): "Parking - Oct 3 - Camry SE"
2. Ticket Type (dropdown): Parking, Toll Violation, Red Light Camera, Speed
   Camera, Other
3. Status (dropdown): Received, Renter Notified, Liability Transferred, Paid
   by Renter, Paid by Us - Charged to Renter, Disputed, Closed
4. Citation Number (text)
5. Issuing Agency (text)
6. Violation Date and Time (date)
7. Violation Location (text)
8. Fine Amount (currency)
9. Admin Fee Charged (currency)
10. Due Date (date)
11. Date Renter Paid (date)
12. Copy of Ticket (file upload)
13. Notes (long text)

Count: 19 + 13 + 21 + 13 = 66 fields.

## The 8 headings in the opportunities tab
Pipeline "Rental Car Process", in rental order:
1. New Inquiry (workflow 1 opens the card here)
2. Booked - Docs Needed (workflow 2)
3. Ready for Pickup (you drag it here once license, insurance and deposit check out)
4. On Rent (you drag it here at the key handoff)
5. Returned - Inspection (workflow 3)
6. Rental Completed (workflow 3, when no claim is open)
7. Accident or Claim (workflow 4)
8. Lost (you drag it here when an inquiry never books)

## Snippets (Conversations, quick message responses)
Merge fields are the build's own; anything in [BRACKETS] is their number to
fill in.
1. Rates and Availability: "Hi {{contact.first_name}}, good news, that car is
   open for your dates. It is [DAILY RATE] a day or [WEEKLY RATE] a week,
   plus a {{custom_values.security_deposit}} security deposit that comes back
   after the car is returned and inspected. Want me to book it?"
2. Not Available, Offer Another Car: "Hi {{contact.first_name}}, that car is
   booked for those dates, but I have a [OTHER VEHICLE] open at [DAILY RATE]
   a day. Want me to hold it for you?"
3. What You Need to Book: "To book you will need a photo of your driver's
   license (front and back), proof of full-coverage insurance, the
   {{custom_values.security_deposit}} deposit and your signed rental
   agreement: {{custom_values.rental_agreement_link}}"
4. Deposit Link: "Here is the link for your {{custom_values.security_deposit}}
   security deposit: {{custom_values.payment_link}}. It is released after the
   car is returned and inspected."
5. Insurance Proof Needed: "Hi {{contact.first_name}}, we still need proof of
   full-coverage insurance before pickup. A photo of your insurance card or
   declarations page is perfect, just reply here."
6. Pickup Details: "Hi {{contact.first_name}}, you are all set for pickup on
   {{contact.pickup_date}} at {{custom_values.pickup_address}}. Bring your
   driver's license. See you then!"
7. Return Reminder: "Hi {{contact.first_name}}, a reminder that the
   {{contact.rental_vehicle}} is due back {{contact.return_date}} at
   {{custom_values.pickup_address}}. Please bring it back with the same fuel
   level you picked it up with."
8. Extension Request: "Happy to extend! The car is open until [NEW RETURN
   DATE]. The extra days are [DAILY RATE] a day and I will send you a payment
   link. Want me to lock it in?"
9. Running Late on Return: "Hi {{contact.first_name}}, the
   {{contact.rental_vehicle}} was due back {{contact.return_date}}. What time
   can you have it back? Late returns are charged [LATE FEE] under your rental
   agreement."
10. Tolls and Tickets: "Tolls, parking tickets and camera tickets during your
    rental are billed to you, plus a {{custom_values.ticket_admin_fee}} admin
    fee. If you get one, tell us right away and we will help you sort it out."
11. Accident or Breakdown: "Are you safe? If anyone is hurt, call 911. Then
    take photos of both cars and the scene, get the police report number and
    the other driver's insurance, and do not admit fault. Call or text
    {{custom_values.after_hours_phone}} and we will walk you through the rest."
12. Deposit Released: "Hi {{contact.first_name}}, the inspection is done and
    your {{custom_values.security_deposit}} deposit has been released. Thanks
    for renting with {{location.name}}!"

## Three things they would recognize on screen
1. Their four tabs by name, vehicles, maintenance, accidents/claims, tickets:
   in steps 20 ("feeds your Vehicles and Maintenance tabs"), 33 ("Open the
   Accidents/Claims Record") and 39 ("Log It in the Tickets Tab"), and as the
   four custom objects if Lorenzo clicks them in.
2. "Headings in the opportunities tab": the 8 stages of "Rental Car Process",
   New Inquiry through Lost, shown in the Opportunities view after
   `ghl_prereqs`, and the cards moving in steps 3, 12, 18, 24, 29.
3. "Text and email automations for different actions throughout the
   process": five workflows named for the rental's actions (inquiry, booking,
   return, accident, ticket), with full rental texts (deposit, license and
   insurance, tolls and tickets, "are you safe"), plus the 12 snippets.

## Beat 1 draft
"This is text and email automations for your rental car business."
