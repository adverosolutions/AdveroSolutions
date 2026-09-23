# Deliverable: the attribution tracker

This is the invoice. On a performance deal nothing else proves the client owes anything, so it is built on day 5, before the first reply lands, not reconstructed in month two from memory.

## Where it lives

A tab in the client's own sheet with every column below, plus the subset that `snapshot.md` lists as GHL custom fields on the contact. Two copies on purpose: the sheet is what the client reads, the CRM is what the F3 scorecard is meant to pull.

What the scorecard reads today is Advero's own GHL location (`ghl.location_id` in `config/ids.json`), not the client's snapshot sub-account. For the invoice it pages through the Won stage of Advero's Sales pipeline (`ghl.pipelines.sales` in the same file) and takes three things from each Won opportunity: `first_touch_date` off the opportunity's contact, the `monetaryValue`, and the date it moved into Won (`lastStageChangeAt`, else `lastStatusChangeAt`). Separately, the weekly-retro collection behind the A10 card walks every opportunity in that same Sales pipeline and counts Proposal and Won stage moves; none of that is the invoice. Reading the client's own GHL sub-account is **not built yet**, so the scorecard never sees a Won stage move or a deal value that exists only in the client's own GHL. Everything else in GHL is for the client and for Lorenzo, not for the invoice.

## Columns

| Column | Written when | Source | Never overwritten |
| --- | --- | --- | --- |
| `contact_id` | import | the list | yes |
| `email` | import | the list | |
| `company` | import | the list | |
| `list_source` | import | former client, lost proposal, cold enquiry | yes |
| `last_job_date` | import | their CRM | |
| `last_job_value` | import | their CRM | |
| `first_touch_date` | first send | the send, not the import | **yes, this one matters most** |
| `attribution_deadline` | first send | first_touch_date plus 180 days | yes |
| `touches` | each send | running count | |
| `last_touch_date` | each send | | |
| `replied_date` | first human reply | | yes |
| `positive_date` | marked interested | | yes |
| `booked_date` | appointment created | | yes |
| `held_date` | appointment showed | | yes |
| `closed_date` | client moves the deal to Won | | yes |
| `contract_value` | close | first-year value | |
| `in_window` | close | closed_date <= attribution_deadline | derived, never typed |
| `commission_rate` | signing | 20 to 30 percent, from the agreement | |
| `commission_due` | close | contract_value times commission_rate, only when in_window | derived |

## The rules that stop the argument

1. **First touch, not first reply.** The clock starts when the first email is sent to that contact. A contact who ignores three emails and calls the client eight weeks later still counts.
2. **Six months.** `config/offers.md` says a reactivated contact that signs within six months of the first sequence touch counts. 180 days, from `first_touch_date`.
3. **First-year value only.** A three-year contract invoices on year one.
4. **Nothing on the off-limits list ever gets a `first_touch_date`.** If it does, it was never excluded, and that is a build error, not an attribution question.
5. **`in_window` is derived.** Nobody types yes or no into it.
6. **A close with no `first_touch_date` is not ours.** It happens, the client closes someone who was never in the list, and the honest answer is zero.

## What the client sees each month

That month's weekly F3 scorecards, each with the filtered table: the contacts that closed that week, each one's first-touch date, close date, value, whether it is in the window, and the commission line. Then one number at the bottom.

`jobs/client_scorecard.py` renders exactly this for a `deal_type: performance` client and refuses to print a revenue figure it cannot trace back to a named contact. It also filters to the closes inside the reporting period: an earlier close still inside the window is listed under "Closed in an earlier period, not part of this week's figure", never added to this period's amount. The card says nothing about whether a close was billed: invoicing is tracked by hand, and every close on the invoice line, plus every earlier-period close (it may never have been on any invoice line), is checked against Lorenzo's own records before billing.

## How the scorecard reads `first_touch_date`, and what is still missing

Three sources, in order:

1. the lead record's own `first_touch_date` (Instantly does not carry one today);
2. the GHL contact custom field of the same name, read with the Won opportunity;
3. a `first_touch:<email>` record in the local store.

**Nothing writes any of them yet.** The send path that would stamp the first touch is outside brief A12, so on live data every close currently falls back to `timestamp_last_contact`, is flagged `last_contact_fallback`, and is excluded from the invoice with the reason printed. That is the safe direction (it under-reports rather than invoicing on an invented start date) but it means the performance invoice line is unreachable until one of those three is populated. Seeding it is the first job of the change-set that builds this tracker.
