# Fulfillment runbook (Blueprint F1 to F4, brief A12)

Onboarding, the product kits, the weekly client scorecard, and retention. Written 2026-09-22.

**State: nothing is live.** Nothing in this brief created a workflow, a folder, a form, a calendar, an invoice, a ClickUp template, a Skool post or an email. Everything is a spec, a change-set that refuses to apply, a kit, or a job that reads.

## What was built

| Thing | Where | What it does |
| --- | --- | --- |
| F1 onboarding spec | `changesets/onboarding/` | Build spec, manifest, kickoff form, ClickUp templates, and a plan-only applier |
| F2 kits | `products/` | Four assets: reactivation, bid follow-up, cold-email infrastructure, Demo Library 011 |
| F3 scorecard | `jobs/client_scorecard.py` | Weekly client card, attribution, invoice basis |
| F4 retention | `changesets/onboarding/retention/` | Four scheduled drafts, rendered by the same job |
| Roster | `changesets/onboarding/clients.seed.json` | Who is a client, when their term started, what they bought |

---

## F3: the weekly scorecard

### Run it

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"

# every active client, read-only, writes to .tmp/scorecards/, no digest
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run

# one client, with the retention drafts printed in full
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run \
  --client man-transformed --retention

# Advero's own six campaigns, to see the renderer against live data
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run --self

# offline replay on the recorded fixtures (they are ADVERO's numbers, so --self)
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run --fixtures --self \
  --as-of 2026-09-22T00:45:00-05:00

# the real run. In shadow the digest is RECORDED, not pushed: it lands in
# .tmp/shadow_log.jsonl as notify/push_email and nothing leaves the process
MODE=shadow LLM_FAKE=1 python3 jobs/client_scorecard.py --now

# ... and this is the one that actually reaches his phone, to his own topic
MODE=shadow LLM_FAKE=1 NOTIFY_SHADOW_SEND=1 python3 jobs/client_scorecard.py --now
```

Flags worth knowing: `--as-of` pins the clock, `--week-ending YYYY-MM-DD` pins the reporting week **and drops the retro renderer** (see the table at the bottom), `--lookahead N` reaches retention touches further out (default 7), `--offline` makes no network call at all, `--mark-handled SLUG:TEMPLATE_ID` retires a retention touch so it stops being listed, `--out-dir` writes somewhere other than `.tmp/scorecards/`, `--json` prints everything.

### Two documents per client, and only one of them is the client's

| File | Who reads it | What is in it |
| --- | --- | --- |
| `scorecard_<end>.md` | the client | the table, the invoice basis, next week's plan, and the caveats that change how a number reads |
| `operator_<end>.md` | Lorenzo | the retention schedule, every draft blocker, the run notes, which renderer produced the card |

Only the client body is ever listed for delivery. Before the split, a client reading their own card learned that a renewal note was scheduled for them on day 25, that their price was not in Lorenzo's offer sheet, and that their account had no campaigns wired up.

**The Sunday (A10) card carries no retention text either.** Its "Next steps" and "Open questions" used to be built from the retention drafts, so the client read "The day 25 note (due ...) is written but cannot go out yet: <blocker>". The agenda is now built from the numbers only; the schedule and every blocker stay in `operator_<end>.md` (re-review OPS-6).

**The digest push.** The digest names client companies, invoice amounts and draft blockers. On an unprotected ntfy topic (the default, `NTFY_TOKEN` unset) the card carries counts only (cards failed, cards, drafts ready, blocked, overdue) and the full digest goes by email. With `NTFY_TOKEN` set the card carries the digest too (re-review OPS-2).

**A card that fails shows on the push.** Each client's card is produced on its own, so one client's failure does not stop the others. The failure is counted on the push, in the title and in the body (`1 card failed`: a count names no client, so it is safe on a public topic), the push goes out at high priority, and the email digest names the client and the error. Some cards failing makes the run `partial`; every card failing makes it `failed` and `main` exits 1 so the scheduler sees it, and the digest ends "No card was produced this run" instead of "No active clients in the roster".

A `--fixtures` run writes `.replay.md` files instead, stamps every card and draft header, and prefixes every digest line with REPLAY. The fixtures are Advero's own recorded numbers, so they are injected for `--self` only: every other client on a replay run reads from their own sources, which for Mike means `no source`.

### When to run it

**Friday, after 19:00 CT, right after the retro packet.** Blueprint F3 says the retro packet becomes the client scorecard, so they should describe the same days.

**The word "week" now always means seven days, whenever it is run.** The card's own window is the seven days ending yesterday. The A10 retro's window is Monday 00:00 CT to now, so on any day but a Sunday it is shorter than that, and the job refuses to adopt it: it renders with the built-in renderer over its own seven days and says so in the run notes. Run live on 2026-09-22 before the fix, the card came back titled "week ending 2026-09-22" with 300 sent, against a real week of 1,800. For a performance client that document is the invoice.

The practical consequence: the A10 card is used on a Sunday run, and the built-in card everywhere else. The cross-cutting request to A10 is a window argument on `collect_week`, so the client card can adopt A10's counts over an explicit range.

### Where the numbers come from

| Column | Source |
| --- | --- |
| Sent | `GET /campaigns/analytics/daily`, per campaign, summed over the window |
| Replies from a person | `unique_replies` off the same rows, falling back to `replies`. **Nothing is subtracted**, see below |
| Out of office and other automatic answers | `unique_replies_automatic`, a parallel counter on its own line |
| Interested, booked, held, closed | `POST /leads/list` per campaign, deduplicated by email, on `lt_interest_status` **exactly 1, 2, 3 or 4**. On a Sunday the A10 card counts them itself, and it now applies the same two rules: one record per email across the client's campaigns, and only 1 to 4 climb |
| Revenue attributed | GHL opportunities in the Won stage (walked to the end of the cursor), matched by email, filtered to closes inside THIS reporting period by a real close date (below). **No GHL token exists**, so today this is always absent and the card says so |
| Term to date (day-21 and day-25 drafts only) | a second daily pull from the client's `start_date` to the end of the week |

### The eleven things it will not do

1. **It never prints an unmeasured zero.** A client with no campaign ids gets `no source` in every funnel cell, and so does a client whose every analytics pull failed. A 500, a rotated key or an exhausted rate limit used to print "Sent 0, Replies 0" as a measurement: to the client that reads as "your week produced nothing", and to Lorenzo it reads as a healthy campaign that stopped.
2. **It never invoices an estimate.** On a performance deal, a close counts only when it has a recorded first-touch date, a close date inside the window, and a contract value that a person wrote down. A `value_per_close_usd` from the roster is a planning number: it is shown, with the reason it is excluded, and it never reaches the invoice line.
3. **It bills only closes dated inside this reporting period, and it keeps no billing record.** The invoice line is what closed inside THIS reporting period. offers.md invoices performance deals monthly against this card, so an all-time total billed the same close every month. Without a ledger the job cannot promise a close is billed exactly once: the same close CAN be counted on two cards, or on none. Its date can move between weeks, earlier or later, when its source changes (for example from an Instantly status-change date to a GHL Won date once GHL is readable). Moved forward, a close counted on one card lands on the next card too. Moved back across a week boundary, a close left off card N as "dated after this week's end" shows on card N+1 as "from an earlier period" and is on no invoice line. A run off the Friday schedule covers a week that overlaps the scheduled one, and a week whose card failed or did not run had no invoice line at all. So every close on the invoice line, and every earlier-period or after-the-week close in the operator notes, is checked by hand before billing.
   - **The period is keyed on a real close date, never on the contact's last reply.** In order: the GHL Won move (`lastStageChangeAt`, else `lastStatusChangeAt`; never `updatedAt`), a `closed_at` / `close_date` on the lead record, then Instantly's `timestamp_last_interest_change` on a lead whose status is closed (4). Keyed on the last reply, a thank-you three weeks after signing moved a $10,000 close into the later period and billed it again, and a contact who signed on a call without a new email was placed in an old period. A close with none of those dates is excluded with the reason `no close date is recorded`, not placed on a guess (re-review OPS-5).
   - **Invoicing is tracked by hand.** The job keeps no record of what has been billed, and no card, client body or operator notes, says whether any close was invoiced. The operator notes of every performance card say: "Invoicing is tracked by hand and this job keeps no billing record, so the same close can be counted on two cards, or on none. Before billing, check every close on this week's invoice line against your own records. Also check every close these notes list from an earlier period or dated after this week's end: it may never have been on any invoice line. Why: a close's date can move between weeks, earlier or later, when its source changes (for example from an Instantly status-change date to a GHL Won date once GHL is readable); a run off the Friday schedule covers a week that overlaps the scheduled one; and a week whose card failed or did not run had no invoice line at all." Below it they list each counted, earlier-period and after-the-week close with its date and where the date came from (`GHL Won`, `lead close date` or `Instantly status change`). A close whose source differs from the one on an earlier card is the one to look for: it may be counted twice, or not at all.
   - An earlier close that is still countable is listed on the client card as "Closed in an earlier period, not part of this week's figure", never added to the amount. Only closes dated before the week's start go under that heading. A close dated after the week's end (a late or off-schedule run) is left off the client body and is not part of the figure; the operator notes list it as "dated after this week's end". The operator notes name all of those closes with their dates and date sources, for Lorenzo to check against his own records. (An invoice ledger and a `--mark-invoiced` command were built and then dropped on 2026-09-22: a same-week re-render could overwrite the saved basis, so the ledger could still record closes that were never billed.)
4. **It never defaults the attribution window.** A performance deal with no `attribution_window_days` prints the reason instead of a number, and a deal with no `commission_rate` says so rather than leaving the client's own contract value as the only bold figure on the page.
5. **It never judges a week it could not measure**, and it never judges a reply rate on too small a sample. Under 300 sends the plan says so instead of telling a client in week one to rewrite their sequence.
6. **It never counts one contact twice.** Leads are deduplicated by email across campaigns, and the collapse is reported. A lead on two campaigns doubled the funnel and doubled the invoice line.
7. **It never promotes a custom lead label to a signed deal.** Only interest statuses 1, 2, 3 and 4 climb the funnel. Custom labels carry their own value in -30000..30000, and a `>=` ladder read the first one as interested, booked, held AND closed.
8. **It never calls a short window a week.** See "When to run it".
9. **It never gives a client somebody else's campaigns, or somebody else's numbers.** `services/retro/scorecard.py` treats `campaign_keys=None` as every campaign, so a client with none of their own is rendered with the built-in card. A `--fixtures` replay is injected for `--self` only.
10. **It never puts a term-to-date claim in front of a week's numbers.** The day-21 and day-25 drafts are filled from a separate start-date-to-now pull and print what they were measured through. A template with `metrics_scope: term` and no term numbers is blocked, never filled from the week.
11. **It never sends.** Delivery is manual: Lorenzo reads the card and sends it himself. The run lists each client card that is ready (`deliveries`, each `sent: false`) and counts them in the Job_Log row as `deliveries_ready_for_manual_send`. It does not call `guard_write` for a send it never makes: in live mode that opened a `live_write_intent` row nothing ever closed (re-review OPS-15). Only the client document is listed, never the operator appendix.

### Two limitations to say out loud

**The built-in card places a contact in a week by its last reply.** A contact that books in a later week without sending another reply does not move between weeks. The card says this in its own footer. The Sunday (A10) card places a contact by `timestamp_last_interest_change` (falling back to the last reply, then `timestamp_updated`), and its footer now says that instead of the built-in wording, so the footer always describes the table above it. The invoice period is not affected by either: it is keyed on the close date (rule 3).

**Automatic replies are a parallel counter, not a subset, and are never subtracted.** Instantly's `replies` already excludes auto-responders. Three of the six campaigns report MORE automatic replies than replies at all ("2026 Bookkeeping - Trigger Outbound" is reply_count 1 with reply_count_automatic 6), which is impossible for a subset. Subtracting them turned the recorded week's 22 replies on 1,800 sends (1.22%, the rate measured by hand) into 6 (0.33%), printed "under the 1% line" on the client's card, and fed the same number into Section 6's inbox-removal rule. The card shows replies from a person and automatic answers on two separate rows.

**A price in client-facing copy is matched against parsed figures, not by substring.** `price_in_offers` used to ask whether `"500"` appeared anywhere in `config/offers.md`, which passed 500 (inside "$2,500"), 15, 50 and 1, and refused 750 and 1,500. It now parses the dollar figures the sheet states as prices, skipping the proof-point table (somebody else's numbers) and any clause the sheet itself marks TO CONFIRM. The rendered draft body is scanned too, because `day25_renewal.md` has no price placeholder: its money lives inside `renewal_terms`, which is operator free text. That free text is also run through the client-copy rules, so an em dash or an exclamation mark typed into the roster blocks the draft instead of shipping inside it.

---

## F4: retention

Four touches per client, counted from **day 0 = the kickoff call**.

| Day | Touch | Sendable unattended |
| --- | --- | --- |
| 7 | Check-in and the fix window | Yes, after approval. It carries no numbers |
| 21 | Results snapshot plus a case-study draft | No. Every number is term to date, from the scorecard's own pull |
| 25 | Renewal or maintenance offer | No. Numbers and a confirmed price |
| 30 | Referral ask and review request | No. It cites one result |

A draft is only `ready` when every required metric exists, when the rendered copy passes the client-copy rules, and, when money appears anywhere in it, when that figure is in `config/offers.md`. A blocked draft is still written, with the gaps listed at the top.

**A touch stops being listed** when it is marked handled (`--mark-handled man-transformed:day25_renewal`, which writes to the local store only) or when it is more than 14 days past due. Without the floor, Mike's four touches came back on every run at -26, then -68, then -250 days, and the digest went out at high priority forever. **A due date that lands on a weekend rolls to the next business day**: day 30 from 2026-09-17 is Saturday 2026-10-17, so it is drafted for Monday 2026-10-19.

### Mike at Man Transformed, due 2026-10-12

Signed 2026-09-17, 2,000 dollars, 30-day content and lead system. Generated drafts are committed under `changesets/onboarding/retention/drafts/man-transformed/`.

**His day-25 renewal cannot go out as it stands.** Three blockers, all on the file:

1. No numbers. His roster row has no campaign ids, so there is no source for sent, replies, positives, booked, held or closed. Whatever runs his content and lead capture has to be connected first.
2. `renewal_terms` and `expansion_line` are unwritten. They are two of the three offers in the note.
3. 2,000 dollars is not in `config/offers.md`, and the offer sheet is the only source for a price that goes in front of anyone. The blocker now reads `price $2,000 is not in config/offers.md`, and it is on his operator appendix, not on anything he could read.

Regenerate rather than hand-edit:

```bash
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run \
  --client man-transformed --lookahead 30 --offline --as-of 2026-09-22T00:45:00-05:00 \
  --out-dir changesets/onboarding/retention/drafts
```

`--offline` and `--as-of` are what make that run reproducible, and
`test_the_committed_man_transformed_artifacts_match_a_fresh_render` fails the
suite if the committed files drift from what the code produces.

**One retention touch is already overdue and is not in this system.** Jennifer L.'s contract ended 2026-09-14 and `config/ids.json` records that no review or testimonial ask was ever sent. That is a day-30 touch that never fired. It goes through Upwork, by hand: nothing here writes to Upwork.

---

## F1: onboarding

```bash
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 changesets/onboarding/apply.py --dry-run
```

Prints the six planned objects, what it could read from live, and the reason each one cannot be applied. `--apply` exits 2 and names the reason per target. Three are `manual_only` (GHL has no create API for workflows, forms or calendars) and three are `no_credential` (Drive, Stripe, ClickUp).

### Build order, when Lorenzo is ready

1. Read `changesets/onboarding/onboarding_spec.md` end to end.
2. Build `Client Onboarding: kickoff kit` in GHL **in Draft**. It is a second workflow on the same trigger, not an edit to the published `Deal Won -> ClickUp project + client tag`. That workflow keeps working while this one is tested.
3. Build the kickoff form from `kickoff_form.md`. **No password field, ever.** It asks for a password-manager invite instead.
4. Build the `Kickoff Call` calendar, 45 minutes, 2 a day, separate from Discovery Call. Connect Zoom first or the confirmation promises a link the booking does not create.
5. Create the ClickUp task templates from `clickup_templates.md`.
6. Test with Lorenzo's own contact record, end to end, including the two-day nudge.
7. Publish. Register the client in `clients.seed.json` (or the store) with the **kickoff call date** as `start_date`, or F4 counts from the wrong day.

### The Drive blocker

The service account has zero Drive storage quota. It cannot create a folder anywhere. Either Lorenzo creates `Clients/` and shares it with the service account as Content Manager (test this before trusting it), or the job runs under OAuth as a real user. Until then the workflow raises an internal task and the folder is made by hand, which is two minutes per client.

---

## F2: the kits

| Kit | Deliverable | Price |
| --- | --- | --- |
| `products/reactivation_system/` | Snapshot description, sequences, attribution tracker | 20 to 30 percent of first-year fees, nothing up front (`config/offers.md`) |
| `products/bid_follow_up_system/` | `bid-follow-up-system.n8n.json` (46 nodes, five lanes), `templates.csv` (**every SMS row ships `enabled` FALSE**) | 1,500 to 2,500 setup, 300 to 500 a month. **Blueprint only, not in offers.md** |
| `products/cold_email_infrastructure/` | `runbook_template.md`. The setup checklist is the day-by-day table in `SOP.md`, not a separate file; the setup script is not built yet (`products/README.md`, "Not built yet") | 750 to 1,500. **Blueprint only, not in offers.md** |
| `products/demo_library_011_reply_engine/` | Demo Library slot 011 one-pager and Loom script | Not sold separately |

Two rules that hold across all four:

**No Loom script names a price.** Two of the three prices are not in `config/offers.md`, and a number on a video is a number Lorenzo then has to honour. The prices live in the SOPs, marked internal.

**The texts ship switched off.** A2P 10DLC is not registered, and the SOP's own failure table says texting before it clears ends in carrier filtering and then a suspended number. Every SMS row in `templates.csv` is `enabled` FALSE and carries "Reply STOP to opt out"; they are flipped on the day the client's registration is confirmed, not during the initial load.

**The bid-system JSON is sanitised.** The delivered copy carried the client's business name, owner first name and team address in its Config node. The kit copy has placeholders. Check this every time a client build becomes a kit: a template that ships the last client's details is the worst thing in `products/`.

Demo Library 011 has **not** been copied into `~/Desktop/Projects/library`. That loop is on the do-not-touch list; the files are here for Lorenzo to move in his own loop.

---

## Tests

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m pytest jobs/tests/test_client_scorecard.py -q     # 126 tests
python3 -m pytest -q                                          # the whole suite
```

## When something breaks

| Symptom | Cause | Do this |
| --- | --- | --- |
| Every column says `no source` | The client has no `instantly_campaign_ids` in the roster | Add them, or accept that there is nothing to report yet |
| `ghl_token_missing` in the notes | There is no GHL Private Integration token | Expected today. Revenue attributed stays absent until there is one |
| A card reports a week that is one day long | Cannot happen any more. The card's week is always the seven days ending yesterday | Nothing. If a run note says the retro window was refused, that is the guard working |
| `--week-ending` gives different numbers from the default run | It pins the week AND drops the A10 renderer, so the counts come from this job's own sums rather than A10's | Expected. Use it to replay a specific week, not to reconcile against a retro packet |
| A retention touch is listed as overdue every week | Nobody marked it handled | `--mark-handled <slug>:<template_id>`. After 14 days past due it drops off by itself |
| A card lists a close under "Closed in an earlier period, not part of this week's figure" | It closed inside the attribution window, in an earlier week | Check it against your own invoicing records. The job does not know whether it was billed and never says |
| The push says `N card(s) failed` at high priority | One client's card raised an error; the others were still produced | The email digest names the client and the error; fix it and re-run for that client with `--client <slug>` |
| The run exits 1 with status `failed` | Every client's card failed | Same, from the email digest or the Job_Log row's notes |
| The same close is on this week's invoice line and on an earlier card | Its date source changed (the operator notes show `GHL Won` now and `Instantly status change` before), or an off-schedule run covered part of the scheduled week | Bill it once. There is no ledger, so this check is always by hand, before every invoice |
| The operator notes list a close "dated after this week's end" | The run was late or off schedule, or the close was signed after the week ended, so it falls after the card's week | Check it against your own records. A later card is not guaranteed to count it: if its date source changes and moves it back into this week, the next card lists it as "from an earlier period" and it is on no invoice line. Bill it by hand if no card counts it |
| A close from an earlier period was never on any invoice line | Its date moved back across a week boundary when the source changed, or the week it is dated in had a card that failed or did not run | Bill it by hand from your own records. The job cannot tell, so the operator notes ask for every earlier-period close to be checked |
| A close is excluded with `no close date is recorded` | Neither GHL nor the lead record dates the close | Add the Won move in GHL (or a `closed_at` on the lead); the last reply is never used |
| A draft is blocked by `copy rules:` or a dollar figure | A roster free-text field (`renewal_terms`, `headline`, ...) carries an em dash, an exclamation mark or a price that is not in the offer sheet | Fix the roster field. The blocker names the exact problem |
| `COPY RULES: this card breaks ...` in the notes | The card contains an em dash, an exclamation mark, a banned word, or no signature | Fix the source before anything is sent. The note is the gate |
| A draft says `NOT READY` | A required number is missing or a price is not in the offer sheet | The blockers are listed on the file. Nothing here can be overridden by re-running |
| `retro generator not importable` | `services/retro` is absent or broken | The built-in renderer takes over and the copy rules are not checked. Say so before sending anything |
