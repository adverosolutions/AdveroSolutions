# Assessment (private) - Square, Zapier and Monday: Wedding Cake Consultations and Deliveries

## Time
- Call, read their current Zap and Monday boards: 1 h
- Expand the Zap (find the couple's item by email, add it if new, write deposit and final balance to it, act on invoice payments only): 2-3 h
- Consultations board: columns (couple, wedding date, venue, tasting date, design details), status, follow-up reminder automation, enquiry intake if they want a Monday form: 2-3 h
- Deliveries board: move on deposit, balance check against their due date, this week's deliveries view, status and venue photo from Monday's mobile app: 2-3 h
- End-to-end test with one small real Square invoice (refunded), fixes: 1-2 h
- Short handoff Loom and notes: 1 h

Total 9-13 hours. Calendar 1 to 2 weeks, set by how fast they share access and run one test payment.

## Likelihood
- Monday boards and automations: high. All built in their Monday UI. Automations need Monday Standard or above (Basic has none), and Standard caps automation actions a month (250 on the 2024 pricing; unverified for 2026).
- Zap expansion: medium-high. Unverified: which Square trigger their Zap uses (payment, order or invoice) and whether what it carries includes the buyer's email. Counter sales often have no customer or email attached; an invoice is sent to a customer, so it has one. If the trigger gives only a customer id, one extra lookup step gets the email. A search-then-update Zap is multi-step, and Zapier's free plan has historically allowed two-step Zaps only (unverified for 2026), so they may need a paid Zapier plan.
- Two boards vs one: with separate Consultations and Deliveries boards, the Zap must search the right board (Consultations for the deposit, Deliveries for the final balance). One board with two groups is simpler for Zapier; two boards match "additional workflow in Monday for consultations and deliveries". Settle on the call.
- For Lorenzo: Zapier and Monday are not in the list of tools he builds in daily (n8n and Make are). The logic here is simple in both; frame it as building in their accounts and make no claim of past Zapier or Monday projects.

## Standard pricing
- Market for a small Zapier plus Monday setup, US Upwork: about $700-$1,500 fixed, or 10-15 h at $60-$100/h.
- Their post: $47-$80/h, intermediate; recorded bids avg $69.54 (range $12-$150). That is at or a little under market. At $65/h, 9-13 h is $585-$845.
- Recurring software (unverified for 2026): a paid Zapier tier about $20-$30 a month if they are on the free plan; Monday Standard about $12-$14 per seat a month with a 3-seat minimum if they are on Basic. Square invoices cost nothing to send; card processing as usual.

## Ask before quoting
1. Can you screen-share your current Zap? Which Square trigger (payment, order, invoice), which Monday board, which columns?
2. Which Zapier plan and which Monday plan are you on?
3. How do couples pay: a tasting fee, a deposit and a final balance? Through Square invoices or at the counter? When is the final balance due (Your Due Date on step 7)?
4. Where do consultation requests come in today (website form, email, phone, Instagram), and who books the tasting?
5. How many weddings in a busy month? (Sets Zapier tasks and Monday automation actions.)
6. Who delivers, and will they update status and add the venue photo from Monday's mobile app?
7. One board with Consultations and Deliveries groups, or two boards?

## Flags
- US only, individuals only, UTC-05:00 preferred: Lorenzo confirms eligibility; copy asserts no location.
- 90% JSS minimum, rising talent welcome: check his status qualifies.
- No portfolio demand; no rule against contact outside Upwork.
- Part time, hourly; their history is small jobs (32 contracts, $5,034.90 spent, about $157 each). Quote in hours with a cap.
- First name unknown: greeting falls back to "Hey there".

## On the build and in a beat
- Matching by the couple's email so deposit and final balance share one item, and Square invoices carrying that email: step 2, band 1 note, beats 3 and 7.
- Their balance due date as their input: step 7, beat 6.
