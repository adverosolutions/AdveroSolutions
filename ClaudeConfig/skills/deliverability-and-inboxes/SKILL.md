---
name: deliverability-and-inboxes
description: "Read Advero inbox health and propose deliverability actions under current keep-and-watch thresholds. Use for bounces, warmup, domains, catch-alls or sending-estate health."
---

# Deliverability and inboxes

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- Cold Email Manager inherited Deliverability Specialist’s routines on November 4. The source snapshot reports 90 inboxes and 30 domains; these are dated counts, not a live check.
- Keep and watch: remove nothing automatically. The November 2 ruling keeps catch-alls eligible; alert on an inbox above 5% weekly bounce or catch-all first-touch bounce above 8% daily. Earlier over-3%-at-50-sends rules identify watch/proposal items; exactly 3.00% is not a breach.
- Domains are watch-only above 5% at 100 or more sends. Re-report a campaign only when it worsens by 0.5 percentage points. Alert only on a meaningful new crossing; do not repeatedly report unchanged alerts.
- Live watch reads existing placement results; creating a placement test spends credits and remains unapproved. Every change to send limits, inboxes, domains, DNS or campaigns needs Lorenzo’s actual approval.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)
- [deliverability-specialist_to_cold-email-manager_20261104.md](../../grok-source/2026-11-04/first-export/advero/state/handoffs/deliverability-specialist_to_cold-email-manager_20261104.md)
- [cold-email-manager.md](../../grok-source/2026-11-04/third-export/routine_exports/cold-email-manager.md)
- [cold-email-manager_8-16.md](../../grok-source/2026-11-04/fourth-export/routines/cold-email-manager_8-16.md)


The monitor watches and proposes. It never changes anything. Every pause, removal, swap or
seed test is a written proposal that Lorenzo reads as a diff and applies himself.

## Who does what (decided 2026-09-25)

- **Grok Bot** reads the daily health card and Instantly analytics, and tells Lorenzo what
  is flagged. It never pauses an inbox, edits an `email_list`, turns warm-up off, buys
  domains or spends placement-test credits.
- **Claude Opus 5.5** reads the evidence and decides what to recommend: act now, wait for
  more sends, or ignore as noise.
- **Lorenzo** decides inbox counts and purchases, and applies every change.

## The estate (2026-09-22 baseline)

| | |
|---|---|
| Inboxes | 45 on 15 domains, at most 3 inboxes per domain in one campaign |
| Sending | 12, each in all six campaigns, 25/day each = 300/day |
| Warming | 33, warm-up started 2026-09-20T23:39Z, 21 days reached 2026-10-11 about 18:40 CT |
| Warm-up | on, score 100 on all 45; all 15 domains pass SPF, DKIM, DMARC, MX |
| Sept 15-21 | 1,800 sent, 1.11% bounce, 1.06% real replies (19 leads) |
| Schedule | Mon-Sat, no Sunday sends: 150 sends per inbox per week |

Sending domains include theadvero.com, adveromedia.com, myadvero.com and proadvero.com.

## Standing rules

- Warm-up stays on forever, on every inbox, including retired ones.
- 25/day per inbox now. A warming inbox sends 0 cold mail until day 21, then 25/day.
- From 2026-11-01: 30/day only for an inbox whose 7-day real reply rate is at least 2% that
  day. Recompute on the day.
- Never heal a domain; retire it (Eric's rule).
- 25/day is a per-inbox cap shared across campaigns, not per campaign.
- Health alerts only (Lorenzo, 2026-09-22): the system does not count a reserve, size one,
  forecast capacity or recommend buying inboxes or domains.

## Thresholds (Section 6)

| Check | Line | Proposal |
|---|---|---|
| Warm-up health | under 98% | pause the inbox |
| Warm-up health | under 90% | emergency, never send from it |
| Warm-up age | under 7 days | report only, never condemn (a 2-day score of 100 means nothing) |
| DNS | any of SPF/DKIM/DMARC/MX missing | fix DNS for the whole domain (manual) |
| Placement | under 85% inbox on Google or Microsoft seeds | pause, re-test in 48 h |
| Reply rate | 100+ sends in 7 or 14 days and under 1% real replies | remove from every campaign |
| Bounce | over 2% at 50+ sends | remove from every campaign |
| Whole domain failing | every inbox on it | retire the domain |
| Sudden drop | domain 7-day reply rate under half its 28-day average | pause the domain's inboxes |
| Canary | under 60% auto-responses (80%+ healthy, 5+ addresses) | kill the inbox |

Exact boundaries: exactly 1.00% reply, 2.00% bounce and a warm-up of 98 are not flagged.

## The five levels

| Level | When | What |
|---|---|---|
| 1 Warm-up and DNS | daily 07:00 CT | warm-up analytics plus DNS vitals (vitals answer per domain, not per inbox) |
| 2 Placement seed test | Monday 06:45 | Google and Microsoft seed placement; web.de and libero ignored |
| 3 Reply and bounce | bounce daily, reply Friday | per inbox and per domain, windows end yesterday |
| 4 Auto-responder canary | Saturday 06:45 | one note per known auto-responder address, count who answers |
| 5 Baseline campaign | daily | peer outreach that should reply 10-30%; a halved rate is a delivery fault |

Weekday map: Mon 1+2+5, Tue-Thu 1+5, Fri 1+3+5, Sat 1+4+5, Sun 1+5. Sudden drop and the
bounce half of level 3 run every day.

Current blockers: no placement test has ever run and there is no seed list (it has to come
from the Instantly UI, and a test costs credits the job never spends); the canary pool is
17 usable addresses, too few for 12 inboxes, so no round is planned; level 5's campaign is
specified but not created; sudden drop is domain-only (R13) and needs history past
2026-09-29 plus a domain baseline above about 1.1%.

## Reading the numbers without fooling yourself

- **Real replies = `unique_replies` per lead.** `replies_automatic` is a separate counter.
  Subtracting it gives negative reply counts and would retire the whole fleet on day one.
- **Thin evidence.** At 150 sends one reply moves an inbox from 0.67% to 1.33%. Under 300
  sends a failure is demoted to medium and tagged THIN EVIDENCE. At the fleet's 1.06%, a
  healthy inbox reads under 1% about half the time from noise alone.
- On 2026-09-22 five of 12 inboxes read under 1% (0.00% or 0.67% on 150 sends each). The
  recommendation on file: do not remove them on that evidence; re-run weekly until each has
  about 300 sends.
- `GET /accounts/analytics/daily` answers 413 without an emails filter; ask in chunks of 25.
  It returns a bare array.
- Instantly does not show bounce NDRs in the Unibox. "No NDRs found" is not proof of clean
  delivery.
- A paused inbox stays in `email_list`. Pausing alone silently cuts capacity.
- Membership of a draft or paused campaign is not capacity.

## Daily card (what Grok relays)

Header: date, inbox count, proposal count; then "sending 12 (300/day) paused 0, the rest
warming or idle". Proposals come critical, high, medium, low. Each names the inbox, the
numbers it failed on, the replacement or "NO replacement available", and the level. Domain
bounce tags: green under 1%, AT LINE within 0.05 of 2%, OVER. The last line says what
applying every proposal would remove from today's sending.

A day with no card is a failure, not a quiet day: every job pushes an alert when it crashes.

## Replacing a burned inbox

1. The monitor, or a flag in the health table, names the failing inbox.
2. A promotion proposal picks the healthiest idle inbox: warm-up score, then measured bounce,
   then age. It rejects any candidate with no analytics, any flag, a quarantine entry, or a
   domain already at 3 in that campaign.
3. The dry-run re-reads the live campaign and prints the `email_list` diff. It refuses if
   live changed, if anything besides "live minus failing plus promoted" would change, or if
   any address is not a live enabled account.
4. Lorenzo applies it from his own terminal (write key loaded, typed confirmation). A backup
   of the campaign is written first; restore from it if needed.
5. Because all 12 inboxes are in all six campaigns, pulling an inbox from one campaign does
   not stop it sending. Removing it from the estate is one change-set per campaign.
6. A removed inbox goes into quarantine and is not a candidate again until cleared by hand.

## List factory (weekly lead supply)

Goal: 3,300 verified, ICP-scored, personalized leads a week at no more than $0.02 per
confirmed contact, so each campaign always has five days of uncontacted leads. Pipeline:
source, free domain suppression, ICP scoring, owner name, email patterns, MillionVerifier,
address suppression, personalization line, staged CSV. It never uploads; a live upload needs
Lorenzo's sign-off.

- Feeds cleaning_reactivation (first), cleaning_trigger, bookkeeping_reactivation,
  bookkeeping_trigger at 300 a week each. Recruiting is disabled (retires at 1,000 sends
  under the verdict rules; feeding it is Lorenzo's call).
- On 2026-09-22 both sources priced over the cap (Apify $0.0222, Google Maps $0.0250 per
  confirmed contact), so a real run halts before spending anything until Lorenzo decides:
  count catch-alls as contacts, raise the cap for a first measured run, or cut source cost.
- Catch-alls are not confirmed contacts (about a quarter of checks). They are counted apart.
- Suppression is mandatory and fails closed: every workspace lead, bounces, unsubscribes,
  the blocklist, hostile replies, clients and our own domains. A list that is incomplete or
  older than 24 hours blocks staging. Add a client's domain to manual suppression the day
  they sign.
- Hostile-reply markers match whole phrases with quoted text stripped; auto-replies are
  skipped by subject. `ue_type == 2` cannot identify an auto-reply on this workspace.
- Paid calls need an explicit paid-calls flag; shadow mode does not protect the budget.

Lead sources and actors are in `lead-sourcing`. The personalization line is in
`cold-email-personalization`.

## Never

- Pause, remove, promote, retire or edit anything live without Lorenzo reading the diff.
- Turn warm-up off.
- Spend placement-test or canary credits unasked.
- Send a canary through the reply endpoint (it lands in a prospect's cold thread).
- Mail a canary address that is blocklisted, negative-status, dead, or not a lead.
- Recommend buying inboxes or domains.

## Gaps

- Seed list for placement tests; first real placement output shape unverified.
- Per-domain Friday audit CSV (brief A4) not built.
- None of these jobs are deployed on a schedule yet.
- Whether Grok reads the card from the push, the change-set file or Instantly directly is
  not yet wired.

## Sources (for maintainers)

- `Agentic Worklfows/runbooks/deliverability.md` (origin/main, 2026-09-22): levels, thresholds, baseline, traps
- `Agentic Worklfows/runbooks/capacity.md` (2026-09-22): roles, ramp plan, promotion, health-only rule
- `Agentic Worklfows/runbooks/list_factory.md` (2026-09-22): pipeline, cap, suppression, targets
- `Agentic Worklfows/runbooks/experiments.md` (2026-09-22): recruiting retirement at 1,000
- `.claude/agents/marketing.md`: Section 6 thresholds, spintax syntax, $0.02 cost rule
- `Agentic Worklfows/shared/thresholds.py`: every number with provenance
- `~/.claude/skills/grok-operator/SKILL.md` (2026-09-25): operating model
