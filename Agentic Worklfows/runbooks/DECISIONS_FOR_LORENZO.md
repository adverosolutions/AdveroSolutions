# Decisions for Lorenzo

> Rewritten 2026-09-22 after the re-review (`REREVIEW_2026-09-22.md`). Part 1 is what still needs your call. Part 2 is what is settled, plus records.

**How to read this page.**

- `R#` ids are the re-review decisions (the table in `REREVIEW_2026-09-22.md`, plus R14 to R17 added here).
- `Q-` ids are this page's older entries. The part after `Q-` is the id the page used before, which other files
  still cite (for example "DECISIONS C5" or "DECISIONS M3"). They are **not** the blueprint's build ids
  (M#, S#, F#, O#, A#): `Q-M1` is a pricing question, not the deliverability monitor.
- Each open item gives the options, the build's recommendation ("none from the build" where it took no
  position; anything marked "Suggestion added 2026-09-22" is new in this rewrite) and what happens if you
  say nothing. Defaults are safe
  (nothing sends because you stayed quiet) except where marked **not safe** or **costs leads**.
- The earlier full wording of every entry is in git: `git show 6769f4d:"Agentic Worklfows/runbooks/DECISIONS_FOR_LORENZO.md"`.

**Words used here.** *Shadow*: the default mode; jobs log what they would do and write nothing live.
*Live*: `MODE=live` plus `ALLOW_LIVE_WRITES=1`, the only pair that writes. *Change-set*: a staged live change
with a dry-run diff and a backup. *Card*: an approval push to your phone or email. *ntfy*: the push service.
*GHL*: GoHighLevel. *Job_Log*: the run record (`.tmp/job_log.csv`, optional Google Sheet mirror).
*O8*: the Sunday list factory run.

## Time-sensitive

| Item | Why now |
|---|---|
| Q-0.1 committed credentials | **Not safe** by default. Rotate before any git remote exists. |
| Q-I2 filler specialty | "your clients'" is still going out in `recruiting_outbound`. |
| Q-D1 weekend TTL | **Costs leads**: a Friday-evening positive can expire over the weekend. |
| Q-A6 The Wednesday cleaning prospect's timezone | A staged draft line to keep or delete before the Wednesday call. |
| Q-M7 Renewal for the client who signed 2026-09-17 | Day-25 touch is due 2026-10-12. |
| Q-L1, Q-L3 Oct 11 shape and domain order | The order-by date (2026-09-19) has passed; each day moves the warm date. |
| Q-J15 Upwork | A live conversation is waiting, and one retention ask is overdue. The rooms check is turned off, so these are by hand. |

---

# Part 1: Decisions

## 1. Things only you can do

Each one unblocks something. Most are pure actions; the first row also carries a choice that is still
yours (how to clean up the git history, Q-0.1 in section 3).

| Action | Unblocks | Ref |
|---|---|---|
| Rotate the four credentials committed in `execution/modal_reply_handler_v2.py` and the Modal secret `instantly-email-responder`; stop both April apps. Timing is your call. Do not add a git remote first. Then pick how to clean up: untrack the file, or rewrite git history (Q-0.1, open). | Removes the one unsafe default | Q-0.1; GO_LIVE Stage 0.1 |
| Create read-only Instantly and GHL keys for agent use, following `runbooks/read_only_keys.md`. Only the read keys (`INSTANTLY_API_KEY_READ`, `GHL_PRIVATE_INTEGRATION_TOKEN_READ`) go in the repo `.env`. The write keys live in two places: the Modal secret and `~/.advero/live.env` on this laptop (outside the repo; `changesets/deploy/modal_secret.py` reads it first). **Check first:** GHL's docs imply that a token with only readonly scopes is allowed but never say so outright. If GHL refuses one, the fallback is one GHL token kept only in `~/.advero/live.env` and none in `.env`, so agent sessions get no GHL reads. | R2: agent sessions never hold a key that can write | R2; GO_LIVE Stage 0.3 |
| Mint the write-capable GHL Private Integration token at GO_LIVE Stage 2.1, not before. Per `runbooks/read_only_keys.md` it goes in `~/.advero/live.env`, not `.env`; only the read-only token goes in `.env`. | Real slots, bookings, three KPI rows, the retro revenue section, client suppression | Q-N1; GO_LIVE Stage 2.1 |
| Connect Zoom in GHL, then change `ghl.calendars.discovery_call.conferencing` in `config/ids.json` (the code reads that string to decide whether Zoom is connected), then redeploy, since `config/` is baked into the image | Confirmations carry the Zoom link | Part 2, Zoom; GO_LIVE Stage 2.6 |
| A2P 10DLC registration, then set `A2P_10DLC_REGISTERED=1` | Every SMS leg (today they return `skipped/a2p_not_registered`) | Q-C7; GO_LIVE Stage 0.5 |
| Replace the `GOOGLE_CREDENTIALS_JSON` placeholder in `.env` with the real service-account JSON | The Job_Log sheet mirror | Q-N2; GO_LIVE Stage 0.2 |
| Read the Discovery Call calendar's timezone in GHL (Settings > Business Profile, or the calendar's Availability tab) | Every slot assumes Central; if it is Eastern, all slot maths is an hour off | Q-A5; GO_LIVE Stage 2.2 |
| Set `REPLY_ENGINE_SECRET` before go-live | The engine refuses to run live without it | Q-C1; GO_LIVE Stage 2.4 |
| Add your current clients' domains to `config/icp/suppression_manual.json` `client_domains` (empty today) | Stops a client getting a cold pitch | Q-J14 |
| Refresh the Skool auth token (the write side answered 401) | The first real Skool post | Q-N2 |
| Upwork by hand: reply in the waiting conversation; ask the client whose Upwork contract ended 2026-09-14 for a review and testimonial (never asked; the one retention touch already overdue); confirm whether the other finished contract (last message 2026-09-17; its `config/ids.json` note says the asks were in your close-out message) was already asked, then add `"asks_done": ["review", "testimonial"]` to its entry; decide whether to ask either finished contract for a maintenance retainer (neither has been asked, and `config/offers.md` has no Upwork retainer line, so no figure can be quoted until you add one) | Retention and the one live deal | Q-J15 |

## 2. New open decisions from the re-review

### R11. Two spec conflicts (copy only)

1. **Personalization model.** `CLAUDE.md` says Sonnet for research lines, one call per lead. Brief A6 says
   "Claude Haiku batch". The code does both: Haiku in batches for the ICP score, one Sonnet call per lead for
   the personalization line (about $0.002 a lead).
2. **Step-3 P.S.** Blueprint M3.4 says step 3 uses a different proof point. Your rule is one proof point per
   email. All six staged sequences carry a P.S. in step 3.

Options: keep the code and edit brief A6, or move personalization to a Haiku batch; drop the step-3 P.S., or
keep it as the one allowed exception. **Recommendation:** none from the build; the re-review says "Your
call". *Suggestion added 2026-09-22, not from the build:* keep Sonnet per lead (it matches `CLAUDE.md`) and
drop the step-3 P.S. (it matches your rule). **If you say nothing:** Sonnet per lead, and the P.S. ships.

### R14. The list factory cannot run under its cap, counting confirmed contacts (was Q-M3)

**Decided 2026-09-25 (Lorenzo): raise the cap to $0.07 per confirmed contact** while every model call runs
on Claude Opus 5.5 and the projection prices worst-case thinking (1,024 tokens a call). Apify now prices at
$0.06212 per confirmed contact (3,300 target), Google Maps at $0.06486, both inside it. Lower the cap after
measuring the first real run. The $0.04 alert line is unchanged. The analysis below is the pre-Opus record.

At today's Apify rate the Sunday pulls price at **$0.022674 per confirmed contact**. `pipeline.preflight()`
run offline at a target of 600 per niche (two campaigns of 300) projects **600 staged / 450 confirmed for
$10.20** on Apify. The cap is $0.02. The cap is now checked before the source fetch, so every real run stops
with `status: halted` before Apify is called and spends nothing. Google Maps prices higher ($0.02499).

- **(a) Raise the cap** (`--max-cost-per-contact`) for one measured run, then set it from what that run
  actually cost. At that preflight that is about $10.20 a niche, about $20.40 a week for the two enabled
  niches (cleaning and bookkeeping).
- **(b) Change the source**, for example cut the source rows (about 62% of the Apify bill) by tightening the ICP
  pass assumption, or try Google Maps for businesses Apify does not reach.
- **(c) Leave O8 off** and stage lists by hand.
- **(d) Count catch-all addresses as contacts**, dividing the cost by deliverable contacts instead of
  confirmed ones. The same preflight is then 600 deliverable for $10.20, about **$0.0170 a contact**, under
  the $0.02 cap. It cuts against the Q-M4 recommendation to reject catch-alls, since it counts exactly the
  addresses that inflate sends and deflate reply rate.

Paid calls also need `ALLOW_PAID_CALLS=1`, and the laptop runner only sets it for a job named in
`LAPTOP_PAID_JOBS` (R7). **Recommendation:** (a) once, on Apify (its rows already carry owner names), then (b)
with a real measurement. **If you say nothing:** (c) in effect: O8 halts every Sunday, spends nothing and
stages nothing.

### R15. `--mark-invoiced`: moot

OPS-5 dropped the invoice ledger, and `--mark-invoiced` is gone from `jobs/client_scorecard.py` (the argument
is now refused, and a test pins that). Invoicing is tracked by hand. Nothing to decide.

### R16. Recruiting is left out of the list factory

`config/list_factory_targets.json` enables four campaigns (both cleaning, both bookkeeping) and disables
`recruiting_reactivation` and `recruiting_outbound`. That departs from R10 ("cover every campaign"). The reason
given: blueprint M4 runs recruiting to 1,000 sends and then retires it, and both campaigns still hold about 450
uncontacted leads each.

- **(a)** Keep recruiting off until its 1,000-send verdict.
- **(b)** Turn it on now (set `enabled` and a `weekly_target`).

**Recommendation:** none from the build; it left recruiting off because buying leads for a campaign the plan
retires at 1,000 is spend you have not approved, and it does not decide that for you. *Suggestion added
2026-09-22, not from the build:* (a). **If you say nothing:** (a).

### R17. Test fixtures that git ignores

The root `.gitignore` ignores `*.json` except under `config/`, `changesets/` and `**/tests/fixtures/`. Sixteen
recorded fixtures sit in `services/*/fixtures/` instead (metrics 6, experiments 5, list factory 3, retro 2), so
they exist only on this laptop. A clean checkout fails about 270 tests. Several of those files hold real email
addresses (one holds about 200).

- **(a)** Commit scrubbed copies (real addresses replaced) and un-ignore those folders.
- **(b)** Keep them ignored and accept that a clean checkout fails.

**Recommendation:** none from the build. *Suggestion added 2026-09-22, not from the build:* (a). A test
suite that only passes on one laptop is not a safety net. **If you say
nothing:** (b).

## 3. Older open decisions

### Credentials

**Q-0.1 How to clean up the committed credentials. Not safe by default.** The facts are in Part 2
(Credentials and safety). Rotating is the same under every option; the choice is what happens to the file
and the history. (A) rotate all four, `git rm --cached` the file and commit the deletion, then stop both
April Modal apps; the history keeps the old values, which are dead by then. (B) rotate all four, then
rewrite history (`git filter-repo` or similar); cleanest, but it changes every commit id, and is worth it
only if this repo will be pushed somewhere. (C) leave everything as it is. **Recommendation:** A, because
there is no git remote. **Default:** C in effect: the credentials stay valid, the file stays tracked and the
April app keeps holding them.

### Sales engine

**Q-0.2 Blueprint S9 (Upwork conversations use the same machine) contradicts M6, A8 and `CLAUDE.md`.**
What exists is read-only (`jobs/upwork_rooms.py`, now run by hand). (A) edit S9 to match M6: Upwork stays
read-only. (B) drafts only, you paste them; about one brief of work. (C) full S9 with on-platform sending;
needs you to read Upwork's automation rules. **Recommendation:** A. **Default:** A.

**Q-A1 Morning slots.** The rule is 12:00-18:00 CT; you took 11:30 for the Wednesday cleaning prospect.
The engine counter-proposes and adds a one-tap "Book as asked" button. (A) keep the rule and tap when you want to bend it. (B) open mornings:
change the rule, which lives in **two** places, `SLOT_WINDOW` in `shared/slots.py` (offers and booking) and in
`shared/settings.py` (no-show rebooking), so change both or merge them. (C) mornings for reschedules only
(more code). **Recommendation:** A; B if you tap the button more than about once a week. **Default:** A.

**Q-A6 The Wednesday cleaning prospect's timezone.** She wrote 11:30 with no zone; she accepted the 11:30
America/Chicago invite. The staged draft adds "If you meant 11:30 your time, say the word and I will move
it." Keep or delete the sentence. **Recommendation:** none from the build; her accepting the Central invite
is decent evidence Central is right, so delete the sentence if you would rather not reopen it.
**Default:** it stays.

**Q-D1 The 48-hour approval TTL over a weekend. Costs leads.** A card created Friday evening expires before
Monday. (A) 96-hour TTL (one constant, `TTL_HOURS` in `approval.py`). (B) pause the clock outside business
hours. **Recommendation:** A. **Default:** 48 hours.

**Q-D2 `SKIP_STALL_DAYS = 2`.** Without the GHL token, live slot touches are refused and every armed ladder
stops after two days. **Recommendation:** mint the token before live (section 1). Otherwise raise the constant.
**Default:** the constant stays at 2, so in live without the token every armed ladder stops after two skipped
days with reason `slots_unavailable` and one high-priority push. Shadow is unaffected.

**Q-E3 `auto_send_due`. Superseded by CT3 (2026-09-22).** Its premise, that first replies to positives
never auto-send, was replaced by the template rule (Part 2, "Decided on 2026-09-22"). The one auto-send path
is now `approval.auto_send_approved`, for text that is exactly an approved template; it does not use
`auto_send_due` or `AUTO_SEND_AFTER_MINUTES`. What is left of this question (keep the old timer unwired, or
delete it) is one row of the CT3 table in section 4. **Default:** it stays, unwired.

**Q-E5 Leads Instantly mis-tagged (for example, the lead who had just started with another provider and deferred to next month).** An explicit "next month" deferral sits at interest status 1 and
shows as $7,500 open pipeline. (a) triage by hand. (b) create reverse-check opportunities with no value.
(c) the reply engine stores its router label so the mirror reads it. **Recommendation:** c. **Default:** a.

**Q-F4 What "next Tuesday" means.** Today "next <weekday>" always means the following week, so said on a
Monday it lands 8 days out, past the 5-business-day horizon, and is never auto-booked. (A) "next Tuesday" on a
Monday means tomorrow. (B) keep it and allow a named "next <weekday>" past the horizon. Tests pin the current
cost on both sides. **Recommendation:** none from the build ("two ways out, both yours to choose").
*Suggestion added 2026-09-22, not from the build:* A (the common American reading). **Default:** never
auto-booked; you tap "Book as asked".

**Q-H1 Booked calls come from a hand seed.** `precall_tick` reads `config/ids.json`
`google_calendar.booked_this_week`, not Google Calendar, and warns when an entry is in the past. (A) keep the
seed and update it on every reschedule. (B) build a Google Calendar read (may need OAuth as your Gmail).
**Recommendation:** A until widget bookings are normal, then B. **Default:** A.

**Q-H2 Prospect's timezone in the brief.** **Recommendation:** add a `tz` field to the seed rows rather than
infer from state. **Default:** Central only.

### Copy and the offer sheet

`config/offers.md` is the only source the copy gate will quote from. Where it disagrees with what you sent,
the engine is quieter than you.

**Q-M1 No quotable price for any of the four things you sell.** Bid follow-up ($1,500-2,500 setup plus
$300-500/mo), cold-email setup ($750-1,500), content and lead system ($2,000, the price your 2026-09-17
client signed at), trigger retainer ($2,500-5,000/mo, TO CONFIRM). These appear only in the blueprint and
kit SOPs. Two checks read the offer sheet, and they differ:

- The renewal and quote parser (`client_scorecard.price_in_offers`) accepts only $200, $15,000, $24,000 and
  $40,000. It skips the proof-point lines and anything marked TO CONFIRM.
- The reply copy gate (`services/reply_engine/draft.validate_draft`) also passes $1,500 and $10,000, because
  those appear in the sheet's case-study proof line ("$1.5k build", "$10k/mo"). It refuses $2,500 and $5,000
  as TO CONFIRM.

**Recommendation:** add the rows; four drafts wait on it. **Default:** every renewal or quote draft naming
one of these prices is blocked.

**Q-B1 The upfront range you quoted on 2026-09-17** ($750-3,500 to build) is a different structure from the
sheet's retainer. **Suggested row:** "Upfront $750-$3,500 to build (quoted in writing 2026-09-17); monthly
retainer TO CONFIRM." **Recommendation:** add that suggested row; only you know whether the monthly
retainer is settled. **Default:** no cleaning_trigger draft can quote a price, and you answer pricing
questions by hand.

**Q-B2 The $2,500-5,000/mo retainer is TO CONFIRM.** Confirm it and the guard drops.
**Recommendation:** none from the build; only you know whether that is the retainer you will quote.
**Default:** drafts stay vague on price.

**Q-B3 Steakhouse gift card.** Live copy for `bookkeeping_trigger` and `recruiting_outbound` says "$200
gift card to your favorite steakhouse"; those two rows in the sheet say "$200 gift card" (the
`cleaning_trigger` row already says steakhouse). (A) widen the two rows. (B) keep the narrow wording.
**Recommendation:** none; this is your offer wording. B is only the safe direction the build took.
**Default:** B.

**Q-B4 Text leg in recruiting_reactivation.** The row has no text channel; live copy promised "email and
text". If SMS is part of the offer, fix the row, not the copy; either way the leg waits on A2P 10DLC.
**Recommendation:** none; only you know whether SMS is part of that offer. **Default:** email only.

**Q-B5 "Guarantee" is refused in every follow-up touch.** Confirm. This also means a research line can never
quote the $24,000/yr or $15,000 guarantee, even for the campaign that owns it. **Recommendation:** none from
the build. **Default:** guarantees stay out of follow-ups.

**Q-B6 Bare numbers as prices.** "$2,500 a month" is refused (the figure is TO CONFIRM). "2,500 a month"
without a dollar sign passes. (A) refuse any bare number over 1,000 in an unattended touch. (B) leave it.
**Recommendation:** none; the build left this open. **Default:** B; it only matters for
unattended cadence touches, since you read everything else first.

**Q-M2 Deposit.** Blueprint S7 says 50% deposit; the sheet says reactivation offers are $0 up front. The
sheet wins today: a reactivation proposal says there is no deposit and carries a check line, a trigger
proposal carries the deposit structure with no number. Edit one of the two. **Recommendation:** none on
which; only you know whether reactivation deals take a deposit. **Default:** the sheet wins.

**Q-M8 `PAYMENT_LINK_URL`.** Unset, so the "link to get started" draft is unsendable, and the verbal-commit
path cannot be finished from a deployed container. Stripe or a GHL invoice. **Recommendation:** none; which
one you bill through is your call. **Default:** unsendable.

**Q-M9 Where a proposal lands.** GHL Documents, PandaDoc or an email attachment; all are a manual paste today
(GHL has no create-document endpoint and there is no PandaDoc account). `proposal.client_body()` returns the
text that may be sent. **Recommendation:** none; your call. **Default:** you paste that text by hand
wherever you choose.

**Q-I1 Long sentences in the staged copy.** Fifteen run over 30 words, mostly the guarantee sentence.
**Recommendation:** split the guarantee sentence before Phase 0. **Default:** ships with a warning.

**Q-I2 2,507 live leads carry "your clients'" as the specialty** (measured 2026-09-21), and
`recruiting_outbound` is sending it. **Recommendation:** re-personalize the uncontacted ones; leave the rest.
**Default:** the filler keeps going out.

**Q-I3 The cleaning_trigger B variant.** The staged sequence (`changesets/instantly_phase0/sequences/
cleaning_trigger.json`) has a B variant that uses `{{metro}}` and `{{buildingType}}`. No live lead carries
either (measured 2026-09-21), so for those leads B would read "I watch  for new leases ... at ,". The list
factory fills both for new leads. (A) keep B off until the campaign's leads carry both (GO_LIVE Stage 6: the
apply refuses cleaning_trigger without `--allow-new-variables`). (B) back-fill the existing leads. (C) turn B on only in a campaign fed by the factory.
**Recommendation:** A, the build's current position (GO_LIVE Stage 6 says to wait for the list factory
to upload leads with those fields, and the apply refuses the copy until then). The build's earlier
recommendation, write the B variant with Phase 0, has been done. **Default:** A. EXP-001 is now split into EXP-001a and EXP-001b (R12), both planned.

**Q-I4 `icebreaker_style` has to be stamped on every lead, or EXP-002 stays blocked.** Instantly has no
per-lead-variable analytics, so EXP-002's three arms (compliment, researched, none) can only be told apart
if each lead carries the value as a custom variable. `config/experiments.json` shows EXP-002 as `blocked`
for exactly this reason, and nothing in `services/list_factory/` stamps it today. It is a build task, not a
judgement call: the list factory stamps it at personalization time, and the variable is registered on the
campaign. **Recommendation:** none from the build; it called this a build task, not a judgement call.
**Default:** EXP-002 reports `blocked` on every run.

**Q-I5 Canary subject.** The canary and the placement seed both use "quick question", a live subject.
**Recommendation:** change the canary subject. **Default:** identical.

**Q-I6 The Wednesday cleaning prospect's offer sentence.** She lost no accounts and wants help with
unanswered proposals; the mechanism sentence in `config/offers.md` opens with "every account that
cancelled". (A) add an offer variant for unanswered proposals. (B) handle it on the call.
**Recommendation:** B now, A if a second prospect says the same. **Default:** the proposal carries its check
line and the mismatched mechanism sentence.

**Q-I7 Security guard companies may not fit commission.** **Recommendation:** decide before the 1,000-send
test: retire on "no first-year contract value", or move that vertical to a flat fee. **Default:** the engine
reports positives and says keep running.

### Infrastructure

**Q-C2 The ntfy topic is public** (no `NTFY_TOKEN`), so cards withhold names and buttons; the full card goes by
email. (A) create an ntfy token. (B) rotate to a random topic and set `NTFY_ALLOW_SENSITIVE=1`. Set at GO_LIVE Stage 2.3.
**Recommendation:** A. **Default:** buttons by email only.

**Q-C4 `JOB_LOG_SHEET_ID`.** Unset, so no sheet mirror. In live it adds a Sheets call before every live
write. Say if you want it and the rows get batched first. **Recommendation:** none from the build; it is
about whether you want to read the log in Sheets. **Default:** no sheet; `.tmp/job_log.csv` (plus
`modal app logs`) is the record.

**Q-N3 The service account cannot create files** (zero Drive quota). (A) you create a `Clients/` folder shared
with it as Content Manager; untested, so it needs a test before it is trusted. (B) move that job to OAuth as
your Gmail. **Recommendation:** none from the build. **Default:** client folders by hand, about two minutes
per client.

### Deliverability and capacity

The inbox system is health alerts only (Part 2). These are the calls left in it.

**Q-K1 Five inboxes under the 1% line: apply or wait.** Sept 15-21, unique replies per lead (the count both
the monitor and the inventory use now):

| Inbox | Replying leads / sends | Rate |
|---|---|---|
| `lorenzo@myadvero.com` | 0 / 150 | 0.00% |
| `lorenzovillarreal@theadvero.com` | 0 / 150 | 0.00% |
| `lorenzo@proadvero.com` | 1 / 150 | 0.67% |
| `lorenzov@adveromedia.com` | 1 / 150 | 0.67% |
| `lorenzov@theadvero.com` | 1 / 150 (3 replies, one lead) | 0.67% |

Each is under the 300-send thin-evidence line, so the proposals are medium and marked thin. The 0.67% inboxes
pass with one more replying lead; the 0% ones need two. Removing all five cuts 125 of 300 sends a day with no
spare to swap in before the warming inboxes are ready on 2026-10-11. Every live inbox is in all six
campaigns, so one removal is one change-set per campaign (the monitor writes all six).
**Recommendation:** wait until after Oct 11. **Default:** nothing applied; the proposals come back on the next
level 3 run.

**Q-K2 Level 2 needs seed addresses.** No read-only endpoint lists them. Start one test in the Instantly UI,
copy the seeds, then run `python3 jobs/inbox_placement.py --now --seed ...`. A seed test spends credits.
**Recommendation:** that by-hand start is the easiest unblock; whether to spend the credits is your call.
**Default:** level 2 stays blocked ("no seeds configured"); the test create is staged and never fired.

**Q-K3 Level 5 baseline campaign.** The spec is `changesets/inbox_actions/level5_baseline_campaign.json`;
it reports "not configured" until a real `campaign_id` is pasted in. It mixes in other traffic (analytics are
per account, not per campaign), so it is capped at medium and always flagged thin. Create it (with a small
`daily_limit`), or have it propose nothing until a per-campaign source exists (a one-line change).
**Recommendation:** the build leaned to "propose nothing" as the more honest setting, but left it to you.
**Default:** no campaign exists, so level 5 reports "not configured" and proposes nothing.

**Q-J10 Canary on real prospects.** 17 of 31 harvested auto-reply addresses survive suppression.
**Recommendation:** point the canary at mailboxes you control on the warming domains instead. **Default:**
the canary plans nothing and says so.

**Q-J11 Level 4 pool size.** 12 inboxes need 60 addresses; 17 exist. (a) raise `CANARY_HARVEST_MAX_PAGES`
past 5. (b) lower `CANARY_ADDRESSES_PER_INBOX` from 10 toward 5. (c) rotate inboxes weekly.
**Recommendation:** a first (free), then decide. **Default:** level 4 stays blocked on pool size.

**Q-J12 Level 4 send mechanism.** The API contract mentions a "send a test email" endpoint at 10/min. If you
can confirm its path and payload it replaces one throwaway campaign per inbox. Nobody should guess a send
endpoint. **Recommendation:** none from the build; **only you can answer this** (from the Instantly docs or
support). **Default:** the procedure is
one throwaway Instantly campaign per inbox, run by hand.

**Q-L1 Oct 11: Option A or B** (one definition, R8, same as `changesets/capacity/domain_order.md`). Both
options **include the order**: 8 domains and 24 inboxes, about $168-240 now and $960-1,560 for year one
(Q-M6). Ordered now, the new 24 are warm about 2026-10-14. The 33 inboxes warming today are ready 2026-10-11.

| | Oct 11 | Oct 14 |
|---|---|---|
| **A** | 45 active, 1,125/day, no spare | 24 new inboxes become spares |
| **B** | 30 active, 750/day, 15 spares | 45 active, 1,125/day; the new 24 are spares |

Either way the campaigns' `daily_limit` must rise (they sum to 300 today) and the new inboxes must be added to
each `email_list` (Part 2, Q-L2). The script that does that exists: `changesets/capacity/apply_capacity.py`,
run at GO_LIVE Stage 7. What does not exist yet is its plan file, `changesets/capacity/oct11_capacity.json`,
because which inboxes go where and each campaign's `daily_limit` follow from your choice here (the shape is
`oct11_capacity.example.json`, which `--apply` refuses). **Recommendation:** B.
**Default:** nothing ordered, no plan file, nothing changes.

**Q-L3 The domain order.** **Recommendation:** none; only you know these answers: which registrar the current fifteen use; Zapmail
(about $3.00-3.50 per inbox a month) or Instantly DFY ($5), and whether either sells pre-warmed inboxes (that
would change Q-L1); whether `goadvero.com` (Vercel nameservers) is yours; whether the nine retired
`*adverosolutions.com` domains still renew; root redirect or blank for the new domains; DMARC `p=none` first or
straight to `p=reject`. **Default:** nothing is ordered until you answer.

**Q-L4 Microsoft inboxes.** `match_lead_esp` must stay false until Microsoft inboxes exist. Proposed: one
Microsoft test domain around Oct 11, `match_lead_esp` for the two cleaning campaigns around Nov 1. Approve,
or stay Gmail-only. **Recommendation:** the proposed sequencing in `changesets/capacity/domain_order.md`
(nothing now, decide the test domain around Oct 11). **Default:** Gmail-only, `match_lead_esp` stays false.

**Q-M6 Budget for the order.** Confirm the cap and the card. Nothing has been ordered.
**Recommendation:** none; only you can set the cap and pick the card. **Default:** nothing is bought.

### List factory

**Q-M4 Catch-all addresses.** Accepted and flagged today; 24% to 55% of checks land there. They inflate sends
and deflate reply rate without bouncing. **Recommendation:** reject until the reply-rate picture is stable.
**Default:** included.

**Q-M5 A paid email finder** (LeadMagic or Prospeo, about $0.0035 a find). **Recommendation:** yes, with the
first paid run. **Default:** no account, so the stage is a stub that finds nothing and only records what a
finder would have cost; a lead the four-pattern guess misses is not staged.

**Q-J13 Score the leads already uploaded.** The rubric rejected 21 of 58 rows from the same scrape that fed
the live cleaning campaigns. **Recommendation:** yes, read-only, with a pause list. **Default:** nothing
scored.

### Metrics, retro and fulfillment

**Q-O2 Reporting week.** The retro uses Monday-to-now; the client scorecard uses seven days ending yesterday.
(A) both use seven days ending yesterday. (B) both use Monday-to-now with the length printed.
**Recommendation:** A (the scorecard already does it). **Default:** they keep disagreeing, and the two
numbers can come from different code.

**Q-O6 "Proposal to close" needs dated stage changes.** Either GHL returns `lastStageChangeAt` (the collector
already reads it, so that needs no build) or the pipeline sync writes a stage-entry event. **Which?**
**Recommendation:** none from the build. **Default:** that row stays blank, even with the GHL token.

**Q-O3 Upwork daily numbers.** The Upwork columns in the daily tracker read n/a until something writes
`.tmp/upwork_daily.json`. (A) `/upwork-morning` writes it. (B) you type the four numbers.
**Recommendation:** none; it depends on how you run your mornings. **Default:** B.

**Q-M7 Renewal for the client who signed on 2026-09-17** (content and lead system). Day 0 is the signing
date, so day 25 is 2026-10-12 and day 30 is 2026-10-19. **Only you know** whether the kickoff was later; if
it was, every date moves. Their roster row has no campaign ids, so the card reads "no source". The renewal
note needs `renewal_terms`, `expansion_line` and a price in `config/offers.md` (Q-M1).
**Recommendation:** none from the build; only you know the kickoff date and the renewal terms. **Default:** the
day-21 and day-25 drafts stay blocked.

### Quick confirms

Each has a default already running. Say only if you disagree. The Recommendation column says whether the
build took a position; "none from the build" means it did not, and "the build's choice" means it picked the
default for the stated reason without recommending it over the alternative.

| Item | Default (what runs today) | Recommendation | Alternative |
|---|---|---|---|
| Q-J1 Real reply rate | Unique replies per lead (1.06% on Sept 15-21); both figures printed in the retro | Unique (from the build: the harder number, and it matches the per-lead rule) | Total replies (1.22%) |
| Q-J2 Inbox verdict floor | Retro calls an inbox dead only when the 95% Wilson interval clears the line | The 95% interval until Oct 11 (from the build); the alternative is only reasonable once there are spares | 90% interval or a four-week point estimate (faster, some false removals) |
| Q-J3 Thin-evidence line | 300 sends | None from the build (the number was its own pick) | Another number; it changes severity, not who fails |
| Q-J4 Lost and no-show deals | Still count as positives | Keep counting them (from the build) | Count only open positives |
| Q-J5 Zero positives but open opportunities | `hold`, flagged | None as such; the build's choice (a retire made off a disagreeing number judged worse than a week's delay) | `retire` |
| Q-J6 Non-recruiting campaign, 1,000 sends, zero positives | `rework_copy`, retire at 2,000 | None as such; the build's choice (the niche is not disproved, only the copy) | Retire at 1,000 |
| Q-J7 EXP-002 sample rule (EXP-002 is blocked anyway until leads carry `icebreaker_style`, Q-I4) | 500 per arm pooled across one niche's campaigns | None as such; the build's reading, which it asked you to confirm before EXP-002 unblocks | 500 per arm per campaign |
| Q-J8 Tracker cells you typed | A measured 0 never overwrites your number | Keep it (from the build) | The job wins |
| Q-J9 Skool post | Staged, never posted, even in live; " \| " separator; signed "Lorenzo" | Never post unread: keep it that way permanently (from the build). The separator follows the no-em-dash copy rule. Signature: none from the build | Drop the signature |
| Q-O4 Show-rate floor | Needs 3 decided calls in 7 days; early on the row will often read "no data" | None from the build (it asked "lower it to 2, or leave it?") | 2 |
| Q-O4 Post-contract window | 21 days | None as such; the build's choice, so both current asks stay live (two reviewers disagreed, one said 14) | 14 |
| Q-A7 Calendars | One Discovery Call calendar, neutral title | One calendar (from the build) | Two calendars |
| Q-C8 Anthropic spend outside the list factory | `ALLOW_PAID_CALLS` does not gate `shared/llm.complete()`, so `precall_tick` and the retro bill real tokens whenever `LLM_FAKE` is unset, bounded by the $10 ceiling in `config/llm_budget.json` | From the build: keep the default for the 48-hour watch, then add the second lock once live. You have not decided the second half | After the watch, once live: add a second lock (`require_paid` in `shared/llm.complete()`). Adding it before the watch would make the container refuse every model call unless `ALLOW_PAID_CALLS=1` is also in the Modal secret |
| Q-D6 Failing touch | Gives up after 12 attempts (`MAX_TOUCH_ATTEMPTS`), marked `retry_exhausted`; the tick logs `partial` and the digest carries the error | None as such; the build's choice (the common cause is a missing contact id, which leaves a task nothing to attach to) | Also notify you on exhaustion |
| Q-E1 Copy block that repeats | Stops the cadence after 3 days (`BLOCKED_COPY_STALL_DAYS`), with a push each day | None as such; the build's choice over an indefinite silent stall | Retry daily for ever with the push suppressed (`BLOCKED_COPY_STALL_DAYS = None`) |
| Q-E2 Unconfirmed send | From an earlier day: retried. Same day: held for you | None as such; the build's judgement call (a send unanswered for 24 hours is more likely lost than accepted) | Never re-send after an unconfirmed attempt; escalate the stale case too |
| Q-E6 Malformed row in `pipeline_sweep` | Logs `partial`, which holds the shadow gate | None as such; the build's choice (report, never a silent zero) | Record it as a note that does not trip the gate |
| Q-E7 Empty subsequence conditions | Unverified; at GO_LIVE Stage 6 you read the new subsequence's enrolled count and delete it at once if it is not 0 | None as such; the build's choice not to make a live write to find out | Stage a change-set that creates it against a throwaway parent campaign with zero leads first, to know in advance (a live write, so it needs your approval) |
| Q-K5 Email-list floor | `MIN_EMAIL_LIST_AFTER_APPLY = 1`, with a loud warning below 3 (`WARN_EMAIL_LIST_AFTER_APPLY`) | None as such; the build's choice | Raise the hard floor (a removal on a two-inbox campaign would then have to be done by hand in the Instantly UI, with no diff, backup or audit row) |
| Q-K5 Quarantine | Every inbox a change-set removes is quarantined, health-related or not; clear with `--clear-quarantine <email>` | None from the build | Quarantine only health-flagged removals |

## 4. CT3 template auto-send: defaults the build chose

The rule itself is decided (Part 2). These are the choices the CT3 build made inside it. Each default
already runs in the code; say only if you want the alternative. The details are in
`runbooks/template_approvals.md`.

| Item | Default (what the code does) | Alternative |
|---|---|---|
| Q-CT3-1 Day 2 research line | Fallback only (`cadence.D2_RESEARCH_MODE = "fallback"`): day 2 uses the fixed line you can approve (`cadence.d2.research_fallback.<offer>`) and never calls the model | `"llm"` for a per-lead line, which no approval covers, so every day 2 is held; or drop day 2 from the ladder |
| Q-CT3-2 Unapproved cadence day | Held (`held_template`), never a card, reported once a day. After 3 business days held for a template reason (unapproved, changed since approval, or lead data the template cannot carry; `TEMPLATE_HOLD_STALL_DAYS`) the ladder stops as `template_unapproved` with one push. The kill switch and other engine-wide holds never count and never stop a ladder. The stop carries a signed Resume link (48 h, re-sent each day while stopped and again once the held ids pass): in the push on a protected ntfy topic, in the email on a public one, and with neither the push says which setting to add. Resume re-runs every check (see `runbooks/template_approvals.md`) | A card for every held touch |
| Q-CT3-3 LLM polish on first replies | Card-only fallback: an approved template with a classification the gate accepts is built with no polish; anything else is polished as before and is always a card | Template text everywhere, never polished |
| Q-CT3-4 `neutral_question`, confidence below 0.8, the fallback classifier | Always a card, even for an approved template | Let an approved template auto-send for them too |
| Q-CT3-5 Lead asked for a time the slot rules refuse (requested override) | A card, which keeps the "Book as asked" button | Auto-send the counter-proposal |
| Q-CT3-6 `booking.slot_already_taken` | Always a card (its draft always carries the `slot_already_taken` problem) | Make it auto-sendable once approved |
| Q-CT3-7 `first_reply.*.other.full` and `first_reply.*.referral.full` | Rollout advice, not code: leave them unapproved at first (a generic answer to any question; a name the lead typed plus slots for someone you never spoke to) | Approve them with the rest |
| Q-CT3-8 First-reply delay | 0 minutes: sent on the pipeline run inside the send window (07:00-19:00 CT on a business day), otherwise queued until the window next opens | An N-minute delay before it goes (not built) |
| Q-CT3-9 Kill switch scope | Covers the ladders too: on, it holds cadence, show-rate and no-show messages (show-rate reminders included) as well as turning replies into cards | Replies only, so reminders keep going with the switch on |
| Q-CT3-10 FYI push | At most one every 30 minutes, only when something was sent, queued or held; ntfy carries counts per template id only, the email leg adds a line per card and a Veto link for a queued one | Another interval, or a push per send |
| Q-CT3-11 `auto_send_due` (was Q-E3) | Stays in the code, unwired | Delete it so nothing can re-wire it |
| Q-CT3-12 Opt-out check in show-rate and no-show | Added: a touch whose lead row carries the opt-out marker is skipped (`opt_out`), and a row that cannot be read holds it | No check (the behaviour before CT3) |
| Q-CT3-13 Deploying with unapproved ladder ids | The preflight (step 8) stops unless you type `HOLD` | Refuse outright, or only warn |
| Q-CT3-14 Booking confirmation with and without Zoom | Two ids, approved separately (`booking.confirmation.zoom_link`, `booking.confirmation.no_zoom_link`); "Zoom not connected" is a card note, not a blocker | One approval for both |
| Q-CT3-15 Reply while the lead's previous call is still being cancelled in GHL (`cancel_pending`) | Never auto-sent: a card that says so | Auto-send it anyway |
| Q-CT3-16 GHL booking links in a template | Only a calendar id listed under `ghl.calendars` in `config/ids.json` (today only `discovery_call`) or the id in the configured booking link | Any GHL booking-widget link (refused because anyone can create a GHL calendar) |

---

# Part 2: FYI

## Decided on 2026-09-22

- **Cold-email template auto-send (CT1 to CT3).** Rule (2026-09-22): an engine email (first reply,
  counter-proposal, booking confirmation, cadence touch, show-rate or no-show message) is sent automatically
  only when its text is exactly a template you approved with `jobs/approve_templates.py` and unchanged since,
  the template kill switch is off, and every send check passes (copy gate, opt-out marker, lead reply hold,
  07:00-19:00 CT send window, recipient check, slot rules); anything else goes to you as an approval card
  (replies) or is held (cadence, show-rate, no-show). It replaces "the first reply to a positive is never
  auto-sent". Nothing auto-sends until you approve templates from your own terminal
  (`runbooks/template_approvals.md`); the defaults the build chose are Part 1, section 4.
- **R1 to R10, R12 and R13 adopted** as recommended in `REREVIEW_2026-09-22.md`. **R2 is built for
  read-only keys** (`shared/keys.py`, `runbooks/read_only_keys.md`): agent sessions read with the `_READ`
  keys in the repo `.env`, and the write keys live in the Modal secret and in `~/.advero/live.env` on this
  laptop, which `load_env` never reads. Instantly issues scoped keys (`all:read`). GHL's docs imply, but do
  not state, that a readonly-only token is allowed; if it refuses one, the fallback is one GHL token kept
  only in `~/.advero/live.env` and none in `.env`, so agent sessions get no GHL reads. Creating the keys is
  in Part 1, section 1.
- **Turned off, code kept:** the A/B campaign verdicts and the Upwork rooms check. They are not
  scheduled; `config/turned_off_jobs.json` lists them with the by-hand commands
  (`python3 -m jobs.campaign_verdicts --out .tmp/verdicts.md`, `python3 -m jobs.upwork_rooms --now`).
- **Kept:** the Friday retro (Fri 16:00 CT) and the client scorecard (Fri 19:15 CT).
- **Inbox system: health alerts only.** `jobs/inbox_inventory.py` computes no reserve count, order size or
  plan option and takes no `--target` or `--planned-active`. It still shows today's campaign `daily_limit` total
  (300/day) and can stage a `--promote` change-set. Buying is your call (Q-L1, Q-L3, Q-M6).
- **OPS-5: the invoice ledger is dropped.** Invoicing is tracked by hand; `--mark-invoiced` no longer exists.
- **Zoom: through the GHL Zoom integration, keeping hold-then-confirm timing.** `booking.book()` creates the
  appointment silently when the reply is classified. When you approve and the reply goes out,
  `release_booking_invite()` confirms it with notify on, so GHL sends the invite, with the Zoom link once Zoom
  is connected. Until then confirmations say the video link follows separately.
- **Booking design from the reply-engine send-safety fixes: an explicit Keep or Release choice.** A card that holds a booking cannot go out
  until the draft restates the booked slot, or you choose Keep the call or Release the call on the Edit page.
  The choice is bound to that booking and that text. An expired card that held a call sends you a Keep or
  Release alert.

## Records and settled items

Short versions. Full earlier text: the git pointer at the top.

### Credentials and safety

- **Q-0.1 (record; the clean-up choice is still open in Part 1, section 3).** Four credentials (Instantly
  key, GitHub token, Slack webhook, Google service-account key) are hard-coded in
  `execution/modal_reply_handler_v2.py`, in three commits (`e3c4f64`, `b0eb1d1`, `14853c8`). The file is
  deleted in the working tree but still tracked; `.gitignore` lists it. Two April Modal apps were still
  deployed when checked (read-only) on 2026-09-22: `instantly-email-responder-v2` holds the four values
  baked in, with public POST and GET endpoints; `instantly-email-responder-test-mode` reads the named Modal
  secret `instantly-email-responder`, which needs rotating too. `advero-lead-sync`, the daily sync
  `CLAUDE.md` calls live, was not deployed. Option A (rotate, `git rm --cached`, stop both apps) is
  recommended over rewriting history, because there is no remote; you have not chosen yet. Rotating the
  Google key also means replacing `credentials.json`; do it in a quiet ten minutes.
- **Q-C5 (superseded by R1 and R2).** The hook greps command text and can be bypassed from inside a script.
  The fix is now R1 (user-level, fail-closed hook) and R2 (read-only keys). Record kept: on
  2026-09-22 04:00-05:23Z, evidence scripts set live mode in their own process and wrote 48 `mode=live` rows
  into `.tmp/job_log.csv`. Instantly and GHL transports were mocked. Two of those runs had notifications on and
  may have emailed or pushed to you (REREVIEW, "What went wrong" 2). The polluted file is at
  `.tmp/quarantine/job_log_polluted_2026-09-22.csv`, and dry-runs now write scratch logs.
- **Q-C1.** Without `REPLY_ENGINE_SECRET` the engine refuses to run live.
- **Q-C3.** `NOTIFY_SHADOW_SEND=1` in the shadow watch sends real pushes to your own topic and email only.
- **Q-C6.** `BASE_URL` is the modal.run URL, so it takes two deploy passes. Unset or localhost counts as
  missing, and approval links refuse to build in live. GO_LIVE Stage 3 (deployment.md step 2b).
- **Q-C7.** `ZOOM_WEBHOOK_SECRET`, `ZOOM_URL_VALIDATION`, `A2P_10DLC_REGISTERED`, `NTFY_TOKEN`,
  `NTFY_ALLOW_SENSITIVE` and `CADENCE_D6_HOLD` are in `modal_app.SECRET_KEYS`, and a test fails if any env
  read is missing from it.
- **Q-C8 (record; the second half is still open in Quick confirms).** R7 decided the list factory's rule:
  `ALLOW_PAID_CALLS` alone gates the list factory (Apify, Google Maps, MillionVerifier, Perplexity and the
  factory's model calls). It does not stop Anthropic spend elsewhere: `precall_tick` and the retro bill real
  tokens whenever `LLM_FAKE` is unset, bounded by the $10 ceiling in `config/llm_budget.json` (checked and
  reset during the watch at GO_LIVE Stage 3.1). Whether to add a second lock in `shared/llm.complete()`
  once live is not decided.

### Sales engine

- **Q-A2.** An already-booked lead who sends more times gets "we are already set" plus the reschedule link,
  never a second booking.
- **Q-A3.** Booking still happens at draft time, silently, and the show-rate ladder is created held. The slot
  is occupied until you decide. Now governed by Keep or Release (above).
- **Q-A4 (decided).** Zoom goes through the GHL integration (above). Connecting it is in Part 1, section 1.
- **Q-A5.** The calendar timezone has never been read (Part 1, section 1).
- **Q-D3.** "Locked in" confirmations wait for 07:00-19:00 CT. Email may go out on a weekend; SMS waits for a
  weekday. Sending at any hour instead is one argument in `show_rate.schedule_for`.
- **Q-D4.** On a store's first run, bookings without a readable `booked_at` get reminders only, no
  confirmation. Keeps go-live day from mailing old bookings.
- **Q-D5.** Lateness windows are my judgement (confirm 2 h, 24 h reminder 6 h, and so on); one dict per module.
- **Q-D6, Q-E1, Q-E2, Q-E6, Q-E7.** Defaults you can still overrule; they are rows in Part 1, Quick confirms.
- **Q-E4.** The auto-reply guard keys on subject markers and no-reply senders.
- **Q-F1.** The Instantly reply call raises when `to` is missing; `to` is not positional, because the live call
  sites pass four positional arguments and would bind the body to it.
- **Q-F2 (corrected).** `within_send_window()` is hour-only (07:00-19:00 CT). Everything that sends uses
  `is_send_time()`, which also requires a weekday. That includes approved replies: a reply approved Friday
  evening queues to Monday 07:00 CT. The cadence also skips weekends.
- **Q-F3.** No agent edits the live-write hook; that is now R1.
- **Q-F5.** The 145-row live Instantly fixture was not re-recorded, to keep prospect data out of the repo.
- **Q-F6.** `config/offers.md` is never edited by an agent; the copy questions are in Part 1.
- **Q-F7.** The two calls you booked by hand on Google Calendar are not in the show-rate sequence; the tick
  prints "NOT COVERED" for them. Book through the widget if you want the engine to own a call.
- **Q-F8.** The D6 prospect-facing calendar invite was not built. What exists is a private hold on your
  calendar, off by default (`CADENCE_D6_HOLD`). A real invite needs an ICS attachment.
- **Q-J15 (partly moot).** The rooms check is turned off, so its oldest-first ordering no longer matters. The
  actions are in Part 1, section 1.

### Known gaps that need live access (Q-G)

GHL `dateAdded` on calendar events; the `/opportunities/search` meta shape; empty subsequence conditions
(Q-E7); whether `to` on the Instantly reply is load-bearing (both guards stay until one live-send rehearsal);
the GHL `/conversations/search` envelope (the reader fails closed); the calendar timezone (Q-A5).

### Deliverability and capacity

- **Q-K4 Sudden-drop alert.** Per-inbox is off (R13): one inbox cannot reach enough sends. The domain check
  stays. It abstains until the 28-day window holds sends older than the last 7 days, and until a domain's recent
  week expects at least 5 replies. With 3 inboxes a domain sends up to 450 a week, so it needs a baseline of
  about 1.1%; at today's rate of about 1% it will usually abstain. The card says NOT EVALUATED rather than
  passing.
- **Q-K5 Defaults.** The two knobs (the email-list floor of 1 with a warning below 3, and quarantining
  every removed inbox) are rows in Part 1, Quick confirms, so you can still overrule them. Clearing a
  quarantine is `python3 jobs/inbox_inventory.py --clear-quarantine <email>`. Promotion change-sets without a
  `promote_health` block are refused. The inventory's per-inbox limit plan gives 30/day only at 2% or more
  unique replies over 7 days; on Sept 15-21 two inboxes are at 2.00% (`lorenzov@proadvero.com` and
  `lorenzovillarreal@proadvero.com`). Nothing applies a limit change.
- **Q-L2.** Adding inboxes alone ships no extra email: the six campaigns' `daily_limit` values sum to 300/day.
  Reaching 1,125/day needs +825/day across the six, plus the new inboxes in each `email_list`. The change-set
  script exists (`changesets/capacity/apply_capacity.py`, GO_LIVE Stage 7: dry-run by default, one campaign
  per live apply, backup first). Its plan file `changesets/capacity/oct11_capacity.json` does not exist yet;
  it is written from your Q-L1 choice.
- **Q-L5.** No lock file on the capacity job (a stale lock is its own failure). `--promote` writes the
  change-set by default; `--no-changeset` previews.
- **Q-N4.** On Oct 11, `instantly.active_inboxes` in `config/ids.json` must grow to the new active count, or
  the reports measure against the wrong plan and miss the new inboxes.

### Metrics, retro and fulfillment

- **Q-N1.** The GHL token turns on three KPI rows (positive to booked, show rate, no-show rebooked).
  Proposal to close also needs Q-O6. It also unblocks the retro revenue section, the scorecard funnel and
  client suppression. It does **not** unblock the onboarding workflow diff: `shared/ghl.py` has no
  `list_workflows()` read, so `changesets/onboarding/apply.py` notes "cannot diff workflows against live"
  and falls back to the state recorded in `config/ids.json`. Scopes: contacts, opportunities, calendars,
  calendars/events, conversations, workflows. Check pagination once there are over 100 opportunities.
- **Q-N2.** Without `NTFY_TOKEN`, cards carry counts only. A by-hand Upwork rooms run (`--now`) sends the full
  room list by email. The Google credential loaders now require `client_email` and `private_key`, so the
  placeholder no longer half-works. `RIZE_EXPORT_PATH` fills the retro's hours section;
  `FIREFLIES_API_KEY` fills objections.
- **Q-M10.** Nothing writes a first-touch date. On live data a closed deal's first touch falls back to the
  last contact date, and `jobs/client_scorecard.py` **excludes** every such row from the invoice line, with
  the reason "first touch inferred from the last contact, not recorded". So the reactivation performance
  invoice line stays empty until something writes a first-touch date. Invoicing is by hand (OPS-5).
- **Q-O1 (corrected).** Sales jobs run on Modal with `modal.Cron(timezone="America/Chicago")`, so CT times are
  literal. Marketing, ops and fulfillment jobs run on the laptop from staged launchd plists or crontab lines,
  on the Mac's local clock, which must be Central (the runner alerts if not). `schedules.json` also carries
  UTC forms for a scheduler with no timezone. They shift an hour on 2026-11-01 and 2027-03-14.
- **Q-O3.** The Upwork rooms check no longer runs on a schedule. Run by hand, it reads the last snapshot a
  session wrote and says "no fresh Upwork data, last seen X" past 12 hours.
- **Q-O5.** The Daily Log sheet has date rows to 2027-09-06. Extend it by inserting rows; rebuilding drops
  typed data.
- **Q-O4 (record) Evening restatement.** Each evening's daily-metrics run also rewrites yesterday's row with
  the finished send count (a second guarded sheet write), because the 18:00 run sees only part of its own
  day. Two reviewers disputed this and wanted it in the next morning's run instead.
- **Q-O6 (record).** Any positive-to-booked ratio read off Instantly reads zero until the pipeline mirror runs
  live: a lead with a Call Booked opportunity in GHL is still at interest status 1 in Instantly, and the
  meeting-booked filter returns zero leads workspace-wide. The verdict engine counts statuses 1 to 4 as
  positive, so its numbers are right either way.

### Choices made in the build (Q-P)

| What | Choice | Why |
|---|---|---|
| `asks_done` for the other finished Upwork contract (last message 2026-09-17) | Not added | A fact about what you sent; yours to confirm |
| Paid-call gate in `shared/llm.py` | Not added | Policy call, still open (Q-C8 in Quick confirms) |
| `appointments_tick` every 10 min | Kept | Doubling it doubles GHL reads; `precall_tick` is on 5 |
| `cadence_tick` hourly 07:00-19:00, every day | Kept | The function skips weekends itself |
| Account fixture before 2026-09-15 | Not extended | The workspace has no history before then |
| Prior week in the retro fixture | Synthetic, labelled in `_about` | Needed to test week-over-week |
| Capacity job lock file | Not added | See Q-L5 |
| `us_metros.py` (about 950 cities) | Kept | A lead outside it gets A-variant only; widen on request |

---

*Every default on this page is what the system does today, in shadow.*
