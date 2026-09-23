# Domain and inbox order for the Oct 11 ramp (M2 / A5)

Prepared 2026-09-22 from a read-only pull of the Instantly account list, the six campaign
`email_list`s and seven days of per-inbox analytics. Nothing here has been bought, no registrar
was contacted, and no API that costs money was called. The numbers below were worked out from that
pull on 2026-09-22. No job recomputes them: since 2026-09-22 `jobs/inbox_inventory.py` reports inbox
and domain health only, and it never sizes, checks or recommends a purchase.

**Nothing in this file happens until you say so.** It is a shopping list and a set of questions.

---

## 1. What you have today

| | Inboxes | Domains | Sends/day |
| --- | --- | --- | --- |
| Active (in the six campaign `email_list`s) | 12 | 4 | 300 |
| Warming (started 2026-09-20, warm 2026-10-11) | 33 | 11 | 0 |
| Insurance (warm, unassigned, ready to swap in) | **0** | 0 | **0** |
| Retired | 0 | 0 | 0 |

Warm-up health is 100 on all 45. Sept 15 to 21 across the twelve active inboxes: 1,800 sent,
20 bounced (1.11%), 19 real replies (1.06%). Five of the twelve are already under the 1% real
reply line that triggers removal in the Friday audit, and if one of them has to come out today
there is nothing to put in its place.

## 2. What the 50% insurance rule costs

The blueprint rule is: insurance capacity is at least 50% of active capacity, so any inbox can be
pulled the day it starts misbehaving without the campaign losing volume.

```
active capacity on 2026-10-11 if all 45 warm inboxes send = 45 x 25 = 1,125/day
insurance needed                                           = 1,125 x 0.5 = 562.5/day
inboxes                                                    = ceil(562.5 / 25) = 23
domains at no more than 3 inboxes each                     = ceil(23 / 3) = 8 domains (24 slots)
```

**8 domains, 24 inboxes (23 needed, one spare slot).**

Two numbers in that block are easy to mix up: **562.5/day is what the rule asks for; the 23
inboxes deliver 575/day** and the 24 slots deliver 600/day.

This number does not grow. It is sized against the **planned** 1,125/day of active capacity (45
inboxes in campaigns on the target date), and every warm inbox the plan does not activate is
credited as insurance already on hand. Buy these 24, leave them out of every campaign as section 8
says, and the arithmetic above is met.

## 3. The date problem, stated plainly

Warm-up takes about 21 days, plus a day to buy the domain, point DNS and let the mailbox come up.

| | Date |
| --- | --- |
| Order-by date to be warm on 2026-10-11 | **2026-09-19** |
| Today | 2026-09-22 |
| Earliest these can be warm if ordered today | **2026-10-14** |

The order-by date passed three days ago. Ordering tonight still leaves the new inboxes cold on
Oct 11 and warm on Oct 14. There is no version of this where 1,125/day and a 50% insurance
buffer both exist on Oct 11. Two honest ways to land it:

**Option A. Order tonight, go to 1,125/day on Oct 11, run without insurance for three days.**
Oct 11 to Oct 14 the estate is fully exposed: an inbox that fails Level 1 or Level 3 comes out and
capacity drops with it. At 300 sends per campaign per day the exposure is real but bounded.

**Option B. Order tonight, cap the Oct 11 go-live at 30 active inboxes.**
30 x 25 = 750/day, with the other 15 held as insurance (ratio exactly 50%). Lift to 1,125/day on
Oct 14 when the new 24 finish warming and become the insurance pool. You give up 375 sends/day
for three days, about 1,125 sends, and never run uninsured.

My read: Option B. The cleaning campaigns are the ones worth scaling and they are nowhere near
list-limited at 750/day; three days of extra volume on recruiting, which has zero positives in
400 contacts, is not worth running the whole estate without a spare inbox. Your call either way.

## 4. Domains to buy

Same pattern as the fifteen you already own (`{prefix}advero.com` or `advero{suffix}.com`, .com
only, never the `adverosolutions.com` brand domain and never one of the nine retired
`*adverosolutions.com` variants).

Availability column is a DNS lookup taken 2026-09-22, not a registrar check. "No NS, no SOA"
means nobody has pointed nameservers at it, which usually means it is unregistered. **Confirm at
the registrar before you count on any of these.**

| # | Domain | Availability hint (DNS, 2026-09-22) | Inboxes |
| --- | --- | --- | --- |
| 1 | useadvero.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 2 | withadvero.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 3 | adverolabs.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 4 | adveroworks.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 5 | adverodirect.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 6 | adveroreach.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 7 | hiadvero.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 8 | adverosystems.com | no NS, no SOA, likely free | lorenzo@, lorenzov@, lorenzovillarreal@ |
| spare | adverolocal.com | no NS, no SOA, likely free | hold |

Checked and **not** available, do not order:

| Domain | What is on it |
| --- | --- |
| goadvero.com | resolves, nameservers ns1/ns2.vercel-dns.com. If this is one of your own Vercel projects, say so and it can be used instead of a purchase |
| adverodigital.com | parked on Hostinger (orbit/horizon.dns-parking.com) |
| adverogroup.com | live on Cloudflare (ned/sky.ns.cloudflare.com) |

## 5. Cost

| Line | Low | High |
| --- | --- | --- |
| 8 domains at $12 to $15 per year | $96/yr | $120/yr |
| 24 Google inboxes at $3 to $5 per month | $72/mo | $120/mo |
| **Cash tonight** (domains for a year + first month of inboxes) | **$168** | **$240** |
| **Year one, all in** | **$960** | **$1,560** |

At the low end that is Zapmail (about $3.00 to $3.50 per inbox per month); at the high end it is
Instantly DFY at $5. One booked cleaning reactivation deal covers the year.

## 6. Questions only you can answer

1. **Registrar.** Where are the current fifteen registered? Put all eight on the same registrar so
   the renewals and the DNS live in one place.
2. **Inbox provider.** Zapmail (cheaper, you manage it) or Instantly DFY (more expensive, arrives
   pre-configured and pre-warmed)? DFY buys back setup time, which matters when the order is
   already three days late.
3. **Pre-warmed inboxes.** If the provider sells pre-warmed inboxes, they change the Oct 11 answer
   entirely. Worth one question to them before choosing Option A or B.
4. **Payment method and cap.** Which card, and what is the ceiling you want this to stay under?
5. **The nine retired `*adverosolutions.com` domains.** Are they still registered and still
   renewing? If they are, that is money going out for domains burnt on HVAC and roofing in
   Dec 2025 to Mar 2026, and none of them should ever send again.
6. **Root domain.** `adveromedia.com` has an A record (a redirect); `adverohq.com` has none. Do
   you want the eight new ones redirecting to adverosolutions.com, or left blank like the recent
   eleven?
7. **DMARC policy.** The live domains are at `p=reject`. Start the new ones at `p=none` for the
   first two weeks and move to `p=reject` once the reports are clean, or go straight to reject
   like the others?

## 7. DNS each new domain needs

Copied from the live records on `adveromedia.com` and `adverohq.com`, read 2026-09-22. Use the
existing domains as the reference, not this table, if anything disagrees.

| Record | Host | Value | Note |
| --- | --- | --- | --- |
| MX | `@` | `1 smtp.google.com.` | Google Workspace single-MX form, priority 1, exactly as the live domains |
| TXT (SPF) | `@` | `v=spf1 include:_spf.google.com ~all` | one SPF record per domain, never two |
| TXT (DKIM) | `google._domainkey` | 2048-bit key issued by Google per domain | generate in Workspace, then turn signing on |
| TXT (DMARC) | `_dmarc` | `v=DMARC1; p=reject; rua=mailto:lorenzo@<domain>; ruf=mailto:lorenzo@<domain>; fo=0; pct=100; rf=afrf; ri=604800; sp=reject; aspf=r; adkim=r` | this is the exact live policy; see question 7 about starting at `p=none` |
| TXT (verification) | `@` | `google-site-verification=...` | issued during Workspace domain verification |
| CNAME | `inst` | `prox.itrackly.com.` | Instantly custom tracking domain. All fifteen live domains use this target and report `CTD_ACTIVE` |
| A | `@` | only if you want the root to redirect | `adveromedia.com` has one, `adverohq.com` does not |

Open and close link tracking stay **off** in every campaign regardless; the CTD exists so Instantly
stops flagging the accounts, not so the pixel can fire.

## 8. After they are bought

1. Create the 24 mailboxes as `lorenzo@`, `lorenzov@`, `lorenzovillarreal@` on each domain, the
   same three personas as every other domain.
2. Connect them in Instantly with `daily_limit 25`, warm-up on, warm-up limit 10, sending gap 7,
   the same settings the existing 45 carry.
3. Leave them out of every campaign `email_list`. That is what makes them insurance.
4. `python3 jobs/inbox_inventory.py --now` picks them up automatically and files them as
   `warming` until day 21, then as `idle`. It reports their health. It does not count them, and it
   does not check whether this purchase was the right size.
5. They never get promoted by a script. A promotion is a change-set you read and approve
   (`runbooks/capacity.md`).
6. Do **not** pre-assign them to a draft campaign to "have them ready". A draft campaign sends
   nothing, and until 2026-09-22 the inventory counted membership of one as active capacity: the
   same report would have claimed 875/day of active capacity under a 300/day campaign ceiling and
   shown an empty insurance pool. It is fixed, but leaving them unassigned is still the honest
   state.

---

## Decision, not a build: Microsoft inboxes and ESP matching

**Recorded here for a later decision. Nothing has been built for it and nothing should be until
you say yes.**

The blueprint's M2 note is to add Microsoft-hosted inboxes (Hypertide Entra, about $25 per domain
including 25 inboxes) **once the Gmail inboxes are three weeks old**, and then turn on Instantly's
`match_lead_esp` so a lead on Outlook or Microsoft 365 is emailed from a Microsoft inbox and a
lead on Google from a Gmail inbox. Same-ESP delivery is the single largest lever on inbox
placement that does not involve changing the copy.

Where it stands:

- `match_lead_esp` is **false** on all six live campaigns (verified 2026-09-22). It is a campaign
  field, so turning it on is a `PATCH /campaigns/{id}`, which means a change-set and your
  approval, not a switch a job flips.
- Turning it on with a Gmail-only estate makes things **worse**, not better: every Microsoft lead
  either waits for a matching inbox that does not exist or falls back, and throughput per inbox
  gets lumpy. It only pays once Microsoft inboxes exist.
- The earliest the current 33 are three weeks old is 2026-10-11, and the eight new domains would
  be three weeks old around 2026-11-04.

Proposed sequencing, for you to accept or reject later:

| When | What |
| --- | --- |
| Now | Nothing. Buy Google inboxes only, per section 4 |
| ~2026-10-11 | Decide whether to add one Microsoft domain (about $25 for 25 inboxes) as a test, warmed separately |
| ~2026-11-01 | If the Microsoft inboxes are healthy, stage a change-set turning `match_lead_esp` on for the two cleaning campaigns only, and read the placement difference before touching the other four |

The cost case is strong (about $25 per domain including 25 inboxes against $72 to $120 a month for
24 Google inboxes), but a second provider is a second warm-up estate, a second DNS pattern and a
second failure mode. That is the trade, and it is yours to make.
