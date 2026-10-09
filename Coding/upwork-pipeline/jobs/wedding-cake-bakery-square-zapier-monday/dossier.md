# Dossier - Automated Work Flow System - Small Bakery

url: https://www.upwork.com/jobs/~022103182659412281756

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown (the post names no bakery)
- Industry: "small wedding cakes bakery"
- Location / timezone: New Jersey, US; US only, UTC-05:00 preferred
- Website read: none named

## Client (from `client.json`)
no client intel

## Tools they named
1. Square
2. Zapier
3. Monday

## Every number in the post
The post itself has no numbers. From the metadata paragraph:
- Hourly $47-$80, intermediate, part time
- 90% JSS minimum, individuals only, US only
- Client record: 32 contracts, 32 jobs with hires, 2 active, $5,034.90 spent, 4.97 over 29 reviews, 55.83 hours
- Recorded bids avg $69.54, range $12-$150
- Connects to apply: 18

Missing numbers they obviously have (weddings a month, how they split deposit and final balance, their balance due date, how many people deliver) go to "Ask before quoting" and appear on the chart only as their input ("Your Due Date").

## Their requirements, verbatim, in their order
1. "continue expanding our very basic workflow system between Square, Zapier & Monday"
2. "set up additional workflow in Monday for consultations and deliveries"

2 asks in the post; the second names two workflows ("consultations and deliveries"), so 3 bands on the chart: 1 their very basic flow expanded, 2 consultations, 3 deliveries. Fewer than 4 is right here; no padding.

## The odd ask only they would recognize
They already have something running and call it their "very basic workflow system between Square, Zapier & Monday". The chart starts from it (step 1, labelled as my read of it, to confirm) instead of starting from scratch. What that Zap does today is not in the post: most likely a Square sale or payment turning into a new Monday item. That is an assumption, stated as one.

## What their hiring history implies
32 contracts for $5,034.90 (about $157 each) and 55.83 hourly hours: a small owner-run business that hires for small, well-defined jobs (bookkeeping, payroll tax filings, bank-statement data entry, a Canva brochure, photo editing, a 2020 curbside menu). 4.97 over 29 reviews: easy to work with, rewards finished work. No automation hire in the history, so the current Zap was likely set up in-house. They will judge on whether it is simple, works in their own Square and Monday, and they can run it without a freelancer. Part time, hourly: keep the scope tight and the hours visible.

## Their likely data
A couple's wedding cake order: deposit paid through Square, then the same couple as one Monday item carried from consultation to delivery. Illustrative record (names, venue, amounts made up):

```json
{
  "square": {"source": "Square invoice payment", "invoice_title": "Wedding cake deposit - Morales / Patel", "customer_name": "Jenna Morales", "customer_email": "jenna.m.weds@gmail.com", "amount": 575.00, "paid_at": "2026-10-03T14:12:00-04:00"},
  "monday_item": {"board": "Deliveries", "item": "Morales / Patel - May 22, 2027", "wedding_date": "2027-05-22", "venue": "Willow Creek Barn, Flemington NJ", "coordinator": "Dana Ruiz, 908-555-0147", "tasting_date": "2026-09-26", "design_details": "3 tiers, vanilla bean / lemon curd / chocolate ganache, pressed florals, serves 120", "delivery_and_setup_window": "1:30-2:30 PM", "deposit": "Paid 2026-10-03", "final_balance": "Paid 2027-05-01", "status": "Delivered and set up"}
}
```

## Sizing (setup job, their numbers only)
The post gives no volume, so sizing is carried as their inputs:
- Zapier tasks a month = Your wedding payments a month x 2 (find the couple's item, then update it). Adding the item for a new couple is 1 more.
- Monday automation actions a month = Your weddings a month x the reminders per couple (move to Deliveries, follow-up reminder, balance check, delivery-week list).
- The sharp point is not volume, it is matching: a basic "new Square sale, new Monday item" Zap gives a couple a fresh item for every payment, so the deposit and the final balance never meet. Expanded, the Zap finds the couple's item by email first. That only works when the payment carries an email: a Square invoice does, a counter sale often does not. This goes on the chart (step 2, band 1 note) and into a beat.

## Three things they would recognize on screen
1. "very basic workflow system" and Square, Zapier, Monday: band 1 label and step 1.
2. "consultations and deliveries": the title and the band 2 and band 3 labels.
3. Wedding cake terms: tasting date, design details, wedding date, venue, coordinator, delivery and setup window (steps 3, 4, 6, 8).

## Beat 1 draft
"This is consultations and deliveries in Monday for your wedding cakes bakery."
