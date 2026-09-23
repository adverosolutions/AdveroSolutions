# products/: the three kits and Demo Library 011 (Blueprint F2, brief A12)

A kit is what makes a build redeployable in a day instead of rebuilt from memory. Each of the three sold kits carries the same four things: the SOP, the deliverable, a three-minute Loom script, and the pricing. The fourth asset, Demo Library 011, is not sold, so it carries a README, the one-page description and a Loom script, and has no SOP and no price.

| Kit | Deliverable | Price reference | Proven on |
| --- | --- | --- | --- |
| `reactivation_system/` | GHL snapshot description plus the campaign templates and the attribution tracker | 20 to 30 percent of first-year fees, nothing up front (`config/offers.md`) | The three live reactivation campaigns |
| `bid_follow_up_system/` | `bid-follow-up-system.n8n.json` (46 nodes, five lanes) plus `templates.csv` | 1,500 to 2,500 setup, 300 to 500 a month (blueprint, **not yet in offers.md**) | Delivered to a construction client for 528.64 dollars |
| `cold_email_infrastructure/` | `runbook_template.md`. The setup checklist is the day-by-day table in `SOP.md`, not a separate file | 750 to 1,500 (blueprint, **not yet in offers.md**) | The Atlantic Labs build |
| `demo_library_011_reply_engine/` | Demo Library slot 011: the one-page description and the Loom script | Not sold on its own. It is the proof asset behind the other three | `services/reply_engine/` |

## Not built yet

The blueprint names these, and none of them exists in this repo. Nothing in `products/` should be read as if they did. The lead import script, the setup script and the bid-kit GHL snapshot come from the F2 table; the reactivation GHL snapshot comes from brief A12, which lists "snapshot/JSON" for the kits in `products/`.

| Kit | Named in the blueprint | What exists instead |
| --- | --- | --- |
| `reactivation_system/` | A lead import script | Nothing. The day-0 import and clean in `SOP.md` is done by hand |
| `cold_email_infrastructure/` | A setup script (domain list, DNS records, inbox account creation through the sending platform's API) | Nothing. Every step in `SOP.md` is done by hand, and `runbook_template.md` records the result |
| `reactivation_system/` | A GHL snapshot | `snapshot.md` describes what it must contain. The snapshot itself has not been created |
| `bid_follow_up_system/` | A GHL snapshot | Nothing. The kit ships the n8n workflow and `templates.csv` only |

## The pricing rule, because it bites

`config/offers.md` is the only source for a number that goes in front of a prospect. It carries the six cold-email offers and the reactivation commission. It does **not** carry the bid-system price or the infrastructure price, so those two numbers live in the SOPs, are marked internal, and must not be quoted in writing until Lorenzo adds them to the offer sheet. That is why none of the four Loom scripts contains a price. A Loom that names a number Lorenzo has not confirmed is a number he then has to honour.

## What every kit assumes

- The client filled in the kickoff form (`changesets/onboarding/kickoff_form.md`), so the voice file and the do-not-say list exist before a word is written.
- Day 0 is the kickoff call. Every task due-date in `changesets/onboarding/clickup_templates.md` counts from there.
- The F3 scorecard (`jobs/client_scorecard.py`) reports on the build weekly, and for the reactivation kit that scorecard is the invoice.
- Nothing in a kit sends anything by itself in this repo. Every write still goes through `shared.settings.guard_write`.

## Building a new kit

Copy the shape of `reactivation_system/`: `SOP.md` (internal, carries the pricing and the failure modes), the deliverable file or the snapshot description, `loom_script.md` (client-facing, no prices, no exclamation marks, no em dashes, signed Lorenzo). Add a row to the table above and a row to the product list in `changesets/onboarding/manifest.json`, or the onboarding workflow will not know which ClickUp template to use.
