# F4 retention: four scheduled drafts

Blueprint F4. Four touches per client, counted from **day 0 = the kickoff call**, not the Won date.

| Day | Template | What it is | Numbers | Can it go out unattended |
| --- | --- | --- | --- | --- |
| 7 | `day07_checkin.md` | Check-in plus the fix window | none | Yes, once approved. It carries no numbers |
| 21 | `day21_results.md` | Results snapshot, then a case-study draft for the client to approve | term to date | **No.** Every number must come from the scorecard |
| 25 | `day25_renewal.md` | Renewal or maintenance offer | term to date | **No.** Numbers and price both need confirming |
| 30 | `day30_referral_review.md` | Referral ask and a review request | none | **No.** It cites one result |

A due date that lands on a Saturday or a Sunday rolls forward to the next business day, the same way the rest of the cadence does. Mike's day 30 is 2026-10-17, a Saturday, so it is drafted for Monday 2026-10-19.

`jobs/client_scorecard.py --retention` renders the ones that are due, writes them to `.tmp/scorecards/<slug>/`, and refuses to mark any draft `ready` while a required metric is missing or a price is not in `config/offers.md`. A draft that is not `ready` is still written, with the gaps named at the top, so Lorenzo can see what to go and get.

## Template format

Front matter between two `---` lines, then the body. Keys:

| Key | Meaning |
| --- | --- |
| `id` | stable id, used as the store key so a draft is rendered once per client per term |
| `day` | day offset from the kickoff call |
| `subject` | subject line, same placeholders as the body |
| `requires` | comma-separated metric names that must be present and non-null before the draft is `ready` |
| `needs_price` | `yes` when the body quotes money, which forces the `config/offers.md` check |
| `auto_ok` | `yes` when the draft may be sent after a plain approval, with no number-checking step |
| `metrics_scope` | `term` when the copy describes the whole term ("the first 25 days"), `week` (the default) when it describes the reporting week |

**`metrics_scope` is not decoration.** A `term` template is filled from a separate start-date-to-`{metrics_through}` pull. Filling it from the reporting week rendered "What the first 25 days produced: 1800 sent" where 1,800 was a seven-day figure, and on the live path the reporting window can be a single morning. Both term templates print `{metrics_through}` and `{days_measured}`, so the client is told exactly what the numbers cover.

Placeholders are `{name}`. Anything in `requires` is available in the body under the same name. Unknown placeholders are left in the text verbatim and listed as a gap, because a rendered email containing `{revenue}` is better than one silently containing nothing.

## When a touch stops being due

`due_retention` drops a template in two cases, because an alert that is always on is an alert nobody reads:

1. **It was marked handled.** `--mark-handled <slug>:<template_id>` writes `retention:<slug>:<template_id>` to the local store and the touch never comes back. Rendering a draft does NOT mark it handled: the runbook regenerates Mike's drafts on purpose, and a render-retires rule would make the second run produce nothing.
2. **It is more than 14 days past due** (`MAX_OVERDUE_DAYS`). Before the floor existed, Mike's four touches came back on every run at -26, then -68, then -250 days, and the digest went out at high priority forever.

## Copy rules these templates obey

No em dashes, no exclamation marks, no mention of tooling, signed `Lorenzo`. Numbers only from the scorecard. Prices only from `config/offers.md`, and none of the three product prices are in it yet, which is why `day25_renewal.md` has `needs_price: yes` and cannot be marked ready.
