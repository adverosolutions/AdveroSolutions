# Metrics tighten — Advero vs Eric (Sep 29)

## Eric’s 3 daily north-stars
1. **Reply rate** (overall + per campaign daily; per domain weekly) — target ~above 1%; ~0.1% = spam risk; ~0.6–0.7% often = list too wide.
2. **Contacts per positive reply** (e.g. 1 per 300) — early spam + list-drift alarm; rein list if it jumps (e.g. 300 → 700).
3. **Net-new Email-1s / day** — first-touch only, not total Instantly volume (follow-ups can inflate “sent”).

Weekly (separate): domain reply cull (yellow — Advero bounce rule stays ~3%, not Eric’s 2%/1% pull alone).

## What Advero already tracks
- Lean accountability sheet: cold emails sent (total), unique replies, reply rate, positives when classifier ran, calls booked/held, Upwork.
- Deliverability daily card: bounce / warmup / inbox health.
- Spec already names Email Reply Rate = unique_replies / sent; positives = distinct leads.

## Gaps (do now)
| Gap | Why it matters | Proposed fix |
|---|---|---|
| Net-new Email-1 vs total sent | Instantly can look “busy” on follow-ups while top-of-funnel stalls | Daily: Email-1 count from Instantly campaign analytics (or step-level if available); show next to total sent |
| Contacts per positive | Forecast + list/spam alarm Eric cares about | Daily: `sent / positive_replies` (CT day or rolling 7d — prefer rolling until volume is steady) |
| Campaign reply rate line | Spintax + subject A/B need a read | Per-campaign reply % on the same card (cleaning A/B first) |

Keep: bounce on deliverability card (Advero ~3% pull rule). Don’t clone Eric’s 1% domain auto-kill without Lorenzo yes.

## Owners
- **RevOps** drafts the daily 3-number card + sheet columns.
- **COO** wires routine / evening block after Lorenzo yes.
- Deliverability Specialist keeps bounce/domain health separate.

## Also in attack-order #2 (after metrics go)
- **Email-2 upgrade** (Copywriter) — yellow “cap at 2” polish, not a full rewrite tonight.
- **Booking bump** (Appointment Setter) — positive-reply → calendar loop polish under ask-first.

## Recommend
Ship a thin **Eric 3-number add-on** to the existing evening / accountability pull — don’t rebuild the whole Daily Metrics sheet.
