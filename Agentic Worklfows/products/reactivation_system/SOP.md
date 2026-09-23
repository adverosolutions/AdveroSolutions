# SOP: Reactivation system

**Internal.** Client-facing copy is `loom_script.md` and the sequences in `campaign_templates.md`.

## What it is

Every business with more than two years of history has a list of people who already bought, already trusted them, and then went quiet. Cancelled accounts. Proposals that never came back. Enquiries that went cold in week two. The reactivation system writes to all of them in the client's name and puts the ready ones on the client's calendar.

It is the easiest thing to sell because the client already paid to acquire every name on the list.

## Who it is for

Any business that can produce 60 or more lost or dormant accounts with an email address. The three live verticals are commercial cleaning, bookkeeping and tax, and recruiting. Cleaning is the one that works: four of the six positive replies and two of the three booked calls across all six campaigns as of 2026-09-21.

Below 60 usable rows, say no. The maths does not work and the client remembers a build that produced nothing.

## Pricing

From `config/offers.md`, which is the only source:

- Nothing up front.
- 20 to 30 percent of first-year contract value or fees from accounts brought back. A smaller cut on a bigger list.
- Zero if nothing closes.
- Recruiting is quoted as a percentage of the first placement fee, in the same 20 to 30 band.
- Attribution window: a reactivated contact that signs within **six months** of its first sequence touch counts. Confirmed in `config/offers.md`.

Monthly invoicing runs against the F3 client scorecard, which is why the scorecard has to name the contacts that closed and show the window. No scorecard, no invoice. The scorecard itself is weekly (the seven days ending yesterday), so a month's invoice is the invoice lines of that month's weekly cards, checked by hand against Lorenzo's own records: the job keeps no billing ledger.

## What the client provides

From the kickoff form: the export of past and lost customers, the lost proposals, the off-limits list, calendar access, the voice file, the do-not-say list.

## Build, day by day from the kickoff call

| Day | Step | Tool | Watch for |
| --- | --- | --- | --- |
| 0 | Import and clean the list | By hand. The blueprint's lead import script is **not built yet** | Dedupe, drop anyone currently a customer, drop the off-limits names. Under 60 usable rows, stop and tell the client before spending a cent |
| 1 | Verify the emails | `execution/verify_emails_bulk.py` (MillionVerifier) | Their cost and quoted first. A dormant list is old, so expect a worse pass rate than a scraped one |
| 2 | Write three emails in their voice | `campaign_templates.md`, the voice file. `execution/unified_personalization_engine.py` writes per-contact personalization lines only, not the emails | Their signature, their trade words, nothing from the do-not-say list |
| 3 | Client approves the copy | | Nothing sends before this. Ever |
| 4 | Build the campaign, set the schedule | The sending platform's own UI. `shared.instantly` has no create-campaign call; it can add leads (`create_lead`), and only through `shared.settings.guard_write` | Their sending domain if they have one, ours if they do not. 07:00 to 19:00 in their timezone |
| 4 | Test send to the client and to Lorenzo | | Read it on a phone before anyone else does |
| 5 | Go live with the first 50 | | Fifty, not the whole list. The first day is a test of the list, not the copy |
| 5 | Seed the attribution tracker | `attribution_tracker.md` | First-touch date for every contact. Without it there is no invoice in month two |

## The sequences

Three emails, 7 to 10 days apart, in `campaign_templates.md`. Timed to the client's real calendar rather than a generic drip: tax season and quarterly estimates for bookkeeping, contract renewal and budget season for cleaning, hiring waves for recruiting.

The mechanism line and the proof line come from `config/offers.md` and nowhere else. One proof point per offer type, never mixed.

## The attribution tracker

Specified in `attribution_tracker.md`. It is the invoice, so it is not optional and it is not a spreadsheet someone fills in later. Per contact: first-touch date, every touch after it, reply date, booked date, closed date, contract value, and whether the close landed inside the six-month window.

## Monthly report

`jobs/client_scorecard.py` renders a weekly card: the F3 numbers, the attribution table filtered to closes inside that week and inside the window, and that week's invoice line. There is no monthly render. The monthly report is that month's weekly cards, and the invoice figure is their invoice lines added up by hand.

## How it goes wrong

| Failure | What it looks like | Prevention |
| --- | --- | --- |
| The list is current customers | A client replies "I am already working with you" | Dedupe against their active list at import, not after |
| Bounces from an old list | Bounce rate above 2 percent, the domain gets burned | Verify first, and start at 50 a day to see the bounce rate before committing the list |
| The client's own inbox is not warmed | Everything lands in spam and the client blames the copy | Either use warmed infrastructure or sell them the infrastructure build first |
| No attribution, month two | The client says "that one was already coming back" and there is no record | Seed the tracker on day 5, before the first reply arrives |
| A reply nobody answers | The one positive in the first week goes cold | The reply engine covers Lorenzo's own campaigns. For a client's campaign, the replies land in the client's inbox and someone has to own them. Decide who on the kickoff call |

## Redeploy time

One day of work spread over five, most of it waiting for the client to approve copy.
