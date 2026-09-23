# Offer Sheet (canonical, as of 2026-09-21)

Source of truth for every draft the reply engine writes. Derived from the six live Instantly campaigns (`config/snapshots/instantly_campaigns_2026-09-21.json`) and Section 4/5 of `REVENUE_AUTOMATION_BLUEPRINT.md`. If a number here disagrees with a campaign, the campaign copy wins until Lorenzo updates both.

## Proof points (one per offer type, never mixed)

| Offer type | Proof line (verbatim) | Used by |
|---|---|---|
| Reactivation | "I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months." | cleaning_reactivation, bookkeeping_reactivation, recruiting_reactivation |
| Outbound / trigger | "I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days." | cleaning_trigger, bookkeeping_trigger, recruiting_outbound |

Other allowed proof (P.S. bullets only, from Lorenzo's case studies): lender $5M pipeline on a $1.5k build; consultancy +35% reply rate; agency to $10k/mo. Never invent client names or numbers.

## The six offers

| Key | Mechanism (what we build) | Guarantee / pricing answer | Minimum to start |
|---|---|---|---|
| cleaning_reactivation | Email + text sequences to every account that cancelled, stopped renewing, or never closed; ready ones land on the calendar | $0 up front. Commission on accounts brought back: **20–30% of first-year contract value**, smaller cut on bigger lists, $0 if nothing closes | List of 60+ lost/dormant accounts or lost proposals |
| bookkeeping_reactivation | Sequences to lost inquiries + former clients timed to tax season, quarterly estimates, year-end cleanup; booked onto the calendar | $0 up front. **20–30% of first-year fees** from clients brought back, $0 if nothing closes | 60+ former clients / lost inquiries |
| recruiting_reactivation | Sequences to dormant and near-miss client accounts | $0 up front. **Percentage of placement fees** from accounts brought back (quote 20–30% of the first placement fee), $0 if nothing closes | 60+ dormant client accounts |
| cleaning_trigger | Watch triggers (new leases, office expansions, PM changes, new construction); outreach under the client's name; walkthroughs on their calendar | Guarantee **$24,000/yr in new cleaning contracts signed within 90 days** or money back + $200 steakhouse gift card. Pricing: setup + monthly retainer, **$2,500–5,000/mo** (TO CONFIRM with Lorenzo before quoting in writing; until then answer "setup plus a monthly retainer, sized to your service area, and the guarantee covers it") | Service area + building types |
| bookkeeping_trigger | Watch triggers (new business formations, part-time bookkeeper/admin job posts, second locations); outreach under the client's name; discovery calls on their calendar | Guarantee **$15,000 in new annual client fees within 90 days** or money back + $200 gift card. Pricing as above (TO CONFIRM) | Target client profile |
| recruiting_outbound | Watch {{specialty}} roles open on job boards; outreach to hiring managers under the agency's name; intro calls on their calendar | Guarantee **$40,000 in new placement fees within 180 days** or money back + $200 gift card. Pricing as above (TO CONFIRM) | Specialty + geography |

## Reply rules the engine must obey

1. Answer the question first, in one or two sentences, using only the table above.
2. Then offer two specific afternoon slots (12:00–18:00 CT, Mon–Fri, ≥4 h out, within 5 business days, never a slot already offered to someone else that day), then the booking link: "or if it's easier, grab a time here".
3. "Send me info" → one-line mechanism + offer to walk through it on a 15-minute call. No attachments, no decks.
4. "Not now" → Follow Up Later with a date; never argue.
5. Referral ("talk to X") → thank, ask for the intro, offer the same two slots for X.
6. Hostile / "remove" / "stop" / "unsubscribe" → no reply; blocklist + DND same day.
7. Wrong person / no longer here → mark wrong_person; if a new contact is named, queue for the list factory, do not email them from the same thread.
8. Never mention AI, automation tools, or that a system wrote the email. Peer voice, no exclamation marks, no em dashes.
9. Sign as "Lorenzo". Same thread, same inbox the cold email came from.

## Attribution and terms (for proposals)

- Reactivation attribution window: a reactivated contact that signs within 6 months of the first sequence touch counts.
- Performance deals invoice monthly against the client scorecard (F3).
- Sales model: one-call close. No "let me send a proposal"; the agreement is signed on the call or the same day.
