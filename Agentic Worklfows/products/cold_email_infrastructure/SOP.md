# SOP: Cold-email infrastructure setup

**Internal.** Client-facing copy is `loom_script.md`. The deliverable the client keeps is `runbook_template.md`, filled in with their own domains and dates. The setup checklist is the day-by-day table below. The blueprint's setup script (domain list, DNS records, inbox account creation through the sending platform's API) is **not built yet**, so every step here is done by hand.

## What it is

Somebody wants to send cold email at volume and their main domain is the only thing they have. Send from it and they burn the domain their invoices go out from. This build gives them separate sending domains, authenticated properly, warmed for three weeks, connected to a sending platform, with a written runbook so they are not dependent on whoever set it up.

## Proven on

The Atlantic Labs build. Blueprint section 2 records it at 199 dollars, and Blueprint M7 records it as sellable at 750 and up. The runbook from that build is the source for `runbook_template.md`.

Also proven on Advero's own account, which is the better demonstration: 4 domains and 12 inboxes live at 100 percent warm-up health, 11 more domains and 33 inboxes warming since 2026-09-20 and due live 2026-10-11. Bounce rate about 1.2 percent across the live inboxes for the week of 2026-09-15.

## Pricing

**Internal, and not yet in `config/offers.md`.** 750 to 1,500, from Blueprint F2. Domains and platform seats are the client's own cost, on the client's own card, and that is said before anything is bought, not in the invoice afterwards.

## Sizing, which is the whole quote

Three inboxes per domain, 25 sends per inbox per day. So:

| Target sends per day | Inboxes | Domains |
| --- | --- | --- |
| 300 | 12 | 4 |
| 750 | 30 | 10 |
| 1,125 | 45 | 15 |

Those are Advero's own live numbers, not a rule of thumb. 25 a day per inbox is the ceiling, not the target, and a new inbox does nothing for three weeks.

**Say the three weeks on the first call.** Every unhappy conversation about this build is a client who expected to send on day two.

## Build, day by day from the kickoff call

| Day | Step | Watch for |
| --- | --- | --- |
| 0 | Pick and buy the domains | Close to the brand, not confusing. Never the main domain, never a hyphenated near-miss of a competitor. Their card |
| 1 | DNS per domain: SPF, DKIM, DMARC, MX | DMARC starts at `p=none` with an address that someone reads. Tighten later, after real traffic |
| 1 | Create the inboxes, three personas per domain | Advero's pattern is `first@`, `firstinitial+last@`, `firstlast@`. Real names, real signatures |
| 2 | Connect to the sending platform | |
| 2 | Start warm-up, write down the go-live date | Warm-up limit 10 a day to start, daily limit 25. Put the date in the runbook where the client will see it |
| 3 | Tracking domain and unsubscribe handling | Open and link tracking stay **off**. Advero runs text only, no tracking, and the deliverability is why |
| 4 | Write their runbook | Their domains, their records, their dates. Not a generic PDF |
| 5 | Handover call, walk the runbook | |
| 21 | Go live, and check warm-up health before the first real send | Below 98 percent, wait. It is a day, not a fortnight |

## What "done" means

- Every domain passes SPF, DKIM and DMARC checks from an external tester.
- Every inbox shows warm-up health at or above 98 percent.
- The runbook is filled in, in their possession, and they have read it on the handover call.
- They know what to do when an inbox starts bouncing, and who pauses it.

## How it goes wrong

| Failure | What it looks like | Prevention |
| --- | --- | --- |
| Sending on day two | Everything lands in spam and the domains are spent | Go-live date written down on day 2 and repeated on the handover call |
| DKIM not actually published | Looks fine in the platform, fails externally | Check from outside the platform, every domain, before go-live |
| Domains bought on Advero's card | An awkward conversation and a renewal nobody owns | Their card, every time |
| Link tracking left on | Reply rate drops and nobody knows why | Off by default, and explain why on the handover |
| No unsubscribe path | One complaint becomes a blacklisting | Set it up on day 3, not after the first complaint |
| The client changes the DNS later | Silent failure weeks after handover | The runbook lists every record, so the change is findable |

## Redeploy time

Five days of work, three weeks of waiting. Quote the three weeks.
