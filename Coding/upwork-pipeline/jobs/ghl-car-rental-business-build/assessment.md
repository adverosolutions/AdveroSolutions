# Assessment (private) - GHL Build for Car Rental Business

## What the prop shows
- 5 GHL workflows (one per trigger tag), 38 action steps, compiled from
  spec.json: 1 New Rental Inquiry (8 steps), 2 Booking Confirmed (5),
  3 Car Returned (8), 4 Accident Reported (7), 5 Ticket Received (8).
- Pipeline "Rental Car Process" (their "headings in the opportunities tab"),
  8 stages: New Inquiry, Booked - Docs Needed, Ready for Pickup, On Rent,
  Returned - Inspection, Rental Completed, Accident or Claim, Lost.
- Created by `ghl_prereqs`: 7 tags (rental-inquiry, rental-booked,
  vehicle-returned, accident-reported, claim-open, ticket-received,
  ticket-paid), 7 contact fields (rental_vehicle, pickup_date, return_date,
  ticket_type, ticket_number, ticket_date, ticket_amount), 6 custom values
  (security_deposit, pickup_address, rental_agreement_link, payment_link,
  after_hours_phone, ticket_admin_fee), the pipeline above.
- NOT created by our lane: the four tabs (custom objects) and the 12
  snippets. Both are written out in dossier.md. Lorenzo decides whether to
  click the objects in by hand for the Loom (about 45 to 60 minutes for all
  four with fields; snippets about 15 minutes).

## The four tabs as custom objects (for the screen)
- Vehicles (19): Vehicle Name, Status (Available / Reserved / On Rent / In
  Maintenance / Out of Service), Year, Make, Model, Trim, Color, VIN, License
  Plate, Plate State, Current Mileage, Daily Rate, Weekly Rate, Registration
  Expiration, Insurance Policy Number, Insurance Expiration, Toll Transponder
  Number, Next Service Due Mileage, Notes and Photos. Linked to renters,
  Maintenance, Accidents/Claims, Tickets.
- Maintenance (13): Service Record, Service Type (Oil Change / Tires / Brakes
  / State Inspection / Detailing / Repair / Other), Status (Scheduled / In
  Shop / Completed), Service Date, Mileage at Service, Shop or Vendor, Cost,
  Out of Service From, Back in Service On, Next Service Due Date, Next Service
  Due Mileage, Receipt, Notes. Linked to one Vehicle.
- Accidents/Claims (21): Claim Name, Status (Reported / Waiting on Renter
  Info / Filed / Adjuster Assigned / Repair Scheduled / Paid / Closed /
  Denied), Date of Incident, Incident Location, What Happened, Police Report
  Number, Police Department, Other Driver Name, Other Driver Phone, Other
  Driver Insurance Company, Other Driver Policy Number, Renter Insurance
  Company, Renter Policy Number, Insurance Claim Number, Adjuster Name and
  Phone, Repair Estimate, Final Repair Cost, Charged to Renter, Amount
  Recovered, Days Out of Service, Damage Photos and Documents. Linked to one
  Vehicle and the renter.
- Tickets (13): Ticket Name, Ticket Type (Parking / Toll Violation / Red
  Light Camera / Speed Camera / Other), Status (Received / Renter Notified /
  Liability Transferred / Paid by Renter / Paid by Us - Charged to Renter /
  Disputed / Closed), Citation Number, Issuing Agency, Violation Date and
  Time, Violation Location, Fine Amount, Admin Fee Charged, Due Date, Date
  Renter Paid, Copy of Ticket, Notes. Linked to one Vehicle and the renter.

## Time
- Four custom objects, 66 fields, dropdown options, associations: 4 to 6 h
- Contact fields, custom values, tags, pipeline: 1 h
- Five workflows with message copy in their voice, test contact run-through
  of every path: 6 to 8 h
- Pickup-tomorrow and return-tomorrow reminders (date-based, see Likelihood):
  1 to 2 h
- 12 snippets: 1 h
- Connect their inquiry source (GHL form, website, Facebook) to the
  rental-inquiry tag: 1 to 2 h
- End-to-end test, handover walkthrough: 2 to 3 h
- One revision round: 2 to 4 h
Total 18 to 27 hours. 1.5 to 2 calendar weeks part time, plus however long
their A2P approval takes (days to weeks, outside our control).

## Likelihood
- High: pipeline and stages, tags, contact fields, custom values, the five
  tag-triggered workflows (the tag trigger shape is verified on a real
  export; the import lane landed 12 of 12 steps on 2026-09-22).
- Medium, account-dependent:
  - Custom objects: must be available and enabled in their sub-account;
    confirm on their plan. Associations (ticket to car to renter) and field
    types (currency, file upload, dropdown) are set by hand in Settings,
    Objects. Our API lane cannot create them.
  - Texts: US business SMS from GHL needs A2P 10DLC brand and campaign
    registration on their number. Unregistered or pending, carriers filter
    or block the texts. Ask their status first.
  - Email: deliverability depends on a dedicated sending domain in their
    GHL; unverified.
  - Date-based reminders (the day before pickup, the day before return) need
    GHL's date-based trigger or a wait until a Date field. The import lane
    does not produce either, so these are built by hand in their account and
    are not in the prop. `pickup_date` and `return_date` are created as text
    fields by `ghl_prereqs`; in their build they become Date fields.
  - Ticket workflow reads four contact fields (type, number, date, amount)
    filled on the renter. Firing it straight from a new Tickets record needs
    a custom object trigger in their workflows; that exists in GHL but is
    unverified for Lorenzo and not in our op list.
  - Deposits: "security deposit" in the copy assumes a payment link
    (`{{custom_values.payment_link}}`); card authorization holds are not a
    GHL workflow feature. Ask how they take deposits.
- Unverified for Lorenzo, say so plainly: he has never built GHL for a car
  rental business, and custom objects have not been built in his
  sub-account. The Loom shows the build for their business instead of a
  past one.
- Design decisions baked in:
  - Every workflow clears its own trigger tag first, so repeat renters
    re-fire everything on their next rental.
  - claim-open is the one tag that persists (until they remove it at
    settlement); it holds the review request.
  - The ticket-paid tag is cleared at the start of each new ticket so an old
    payment does not cancel a new reminder.
  - Waits are pacing only: 1 day (inquiry follow-up), 2 days (inspection
    before the review ask), 3 days (ticket payment reminder). All three are
    our defaults, not their numbers; adjust to their process.

## Standard pricing
- Post: hourly, no rate given. Recorded bids avg $23.61, range $7-$95.
  Their history: $4.8k over 391 hours, about $12 an hour on average. Well
  under market; expect price pressure.
- Market for an experienced GHL builder: $45 to $85 an hour, so 18 to 27 h
  is about $800 to $2,300. Fixed-price GHL CRM build-outs with custom
  objects, pipeline, 5 or more workflows and snippets commonly run $1,500 to
  $3,000.
- Recurring (theirs, already paying for GHL): their GHL plan, LC Phone SMS
  usage per segment, A2P registration fees (one-time brand and campaign
  vetting plus a monthly campaign fee), LC Email usage. No new software
  from us.

## Ask before quoting
1. "Tickets": traffic, parking and toll tickets from renters (assumed), or
   support tickets?
2. "Headings in the opportunities tab": the stages of one rental pipeline
   (assumed), or more than one pipeline?
3. Your number of vehicles, and is there a spreadsheet of the fleet (VIN,
   plate, mileage) to import into the Vehicles tab?
4. Where do inquiries come from: website form, phone, Facebook, Turo or
   another booking platform? Any rental software already holding bookings,
   agreements or payments?
5. How do you take the security deposit and charge ticket fees today?
6. Is your GHL number A2P registered? Is a sending domain set up for email?
7. Are custom objects enabled on your GHL plan?
8. Which "different actions throughout the process" do you already have in
   mind beyond inquiry, booking, return, accident and ticket?
9. Your deposit amount, admin fee, pickup address and after-hours number
   (the six custom values).

## Flags
- Screening Q1 "Have you every done a Go High Level for a car rental
  business ?": honest answer is no. Q2 "Describe your recent experience
  with similar projects": only the facts in the brief (his own n8n / Make /
  Instantly systems, the four case studies). No GHL client-project claims.
- Post filters for prior car rental GHL experience; the working build for
  their business is the counter.
- Custom objects are hand-built; the prop cannot import them.
- Five workflow files to import: the Backup & Audit extension is free for 5
  imports, then $19.99 one-time.
- Client in Connecticut, account timezone America/Sao_Paulo: confirm working
  hours overlap.
- No US-only restriction, portfolio demand or no-contact-outside-Upwork
  rule in the post.
