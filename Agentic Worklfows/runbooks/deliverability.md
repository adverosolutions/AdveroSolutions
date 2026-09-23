# Deliverability runbook — the five-level monitor (Blueprint M1; jobs O1, O5, O7)

**What this protects:** the 12 sending inboxes (45 in the workspace; the other 33 are warming and
in no campaign). At 25 sends/day each that is 300/day. One domain going to spam costs three inboxes at once, and
Eric's rule is that you never heal a domain, you retire it. The monitor's job is to notice that
three days before the reply rate does.

**What it will never do:** change anything. Every level ends in a *proposal* written to
`changesets/inbox_actions/<date>.json`. Pausing an account, patching a campaign's `email_list` and
creating a seed test all happen only through `apply_inbox_actions.py --apply` with
`MODE=live ALLOW_LIVE_WRITES=1`, one proposal at a time, after you have read the diff.

---

## 1. The files

| Path | What it is |
|---|---|
| `shared/thresholds.py` | Every number, with the blueprint section and whether it is Eric's published figure or observed practice. Nothing else in the set carries a literal threshold. |
| `jobs/deliverability_monitor.py` | Levels 1, 3 and 5 plus the sudden-drop alert, and the one card that folds in 2 and 4 (O1). Level 3's bounce half runs daily; its reply half runs Friday. |
| `jobs/inbox_placement.py` | Level 2, the weekly seed test (O5, Monday) |
| `jobs/autoresponder_canary.py` | Level 4, the Saturday canary (O7) |
| `changesets/inbox_actions/<date>.json` | The day's proposals. All three jobs merge into this one file. |
| `changesets/inbox_actions/apply_inbox_actions.py` | The only thing that can execute a proposal |
| `changesets/inbox_actions/level5_baseline_campaign.json` | The level 5 spec. The monitor reads it; it never creates the campaign. |
| `changesets/inbox_actions/last_placement.json`, `last_canary.json` | How levels 2 and 4 hand their results to the daily card. Aged on read: past `PLACEMENT_RETEST_HOURS` / `CANARY_RESULT_MAX_AGE_DAYS` their failing rows are dropped and the card says stale. `last_canary_<round_id>.json` archives each sent round. |
| `jobs/tests/test_deliverability_*.py` | 153 tests, all offline |

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
python3 -m pytest jobs/tests -q -k deliverability
```

---

## 2. The daily run (O1, 07:00 CT)

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
MODE=shadow NOTIFY=off python3 jobs/deliverability_monitor.py --dry-run --full   # read-only, no file, no push
MODE=shadow            python3 jobs/deliverability_monitor.py --now              # + change-set + the ntfy card
```

`--dry-run` reads live, prints the card, writes a scratch Job_Log row and touches nothing else.
`--now` is the operating run: it writes the change-set and sends you one card.

Other flags: `--level 1 3` forces levels, `--all-levels` runs everything regardless of weekday,
`--as-of <ISO>` replays at a fixed clock, `--json` prints the whole report, `--full` adds the
per-inbox table.

By weekday (`shared.thresholds.LEVELS_BY_WEEKDAY`, derived from `LEVEL2/3/4_WEEKDAY` rather than
hand-written): Mon 1+2+5, Tue–Thu 1+5, Fri 1+3+5, Sat 1+4+5, Sun 1+5. The sudden-drop check runs
every day with level 1, and so does **the bounce half of level 3** (`BOUNCE_CHECK_EVERY_DAY`):
Section 6 gives the Monday run a bounce audit, and a domain that starts bouncing on a Saturday
should not send six more days of mail before anything notices. The reply-rate half stays on Friday.

### Reading the card

```
Deliverability Tue 2026-09-22 02:33 CT - 45 inboxes, 4 proposals
================================================================
sending 12 (300/day)  paused 0  the rest warming or idle (not in any campaign)
levels run: 1, 5
```

The card is health alerts only (Lorenzo, 2026-09-22): how many spare inboxes to hold, and when to
buy more, is his decision, so the card carries no count of spare inboxes and no ratio against a
floor. Inboxes in no campaign are named on the headline line so it adds up to the header, but they
are never totalled. Whether a removal has a replacement is said on each proposal.

Then the proposals, ordered critical → high → medium → low. Each one names the inbox, the reason
with the actual numbers, the replacement (or `NO replacement available` and what it costs), and
the level that produced it. An inbox condemned by two levels appears once, under the more complete
action, at the louder severity, with both reasons and **every safety flag either of them carried**:
a `THIN EVIDENCE` tag on the headline and the quieter level's note underneath.

The cost line is the last thing before the level summaries. It says what applying every proposal
would take out of today's sending; it is a health cost, not a reserve count or buying advice. The
"removes N of M sending inbox(es): X of Y sends/day" part counts every inbox a proposal removes,
replaced or not. Only the "leaving N%" figure counts a proposal with a replacement as no loss (its
inboxes' sends are added back), so with replacements the percentage is higher than Y minus X would
give (`jobs/deliverability_monitor.py:1505-1525`, `_capacity_cost_line`):

```
Applying all of these removes 4 of 12 sending inbox(es): 100 of 300 sends/day, leaving 67% of
today's capacity.
```

Per-proposal the wording is `removes N inbox(es), M sends/day total; they are in K campaign(s)`.
Instantly's 25/day is a **per-inbox** cap shared across campaigns, not 25 per campaign, and a
domain-scope proposal removes one inbox's worth per inbox: the old line printed the per-inbox
constant for a three-inbox domain and understated the cost by 3x.

Domain bounce rates are tagged `green` (under 1%), `AT LINE` (within 0.05 of the 2% ceiling) or
`OVER`. Three sending inboxes read exactly 2.00% on 2026-09-22 and the card used to say nothing
about it.

---

## 3. What each level actually checks

### Level 1 — warm-up health and DNS (daily 07:00)

`POST /accounts/warmup-analytics` in chunks of 100, plus `POST /accounts/test/vitals`.

- Health below **98%** proposes a pause (Eric, published).
- Below **90%** it is an emergency: never send from it.
- An inbox with fewer than **7 days** of warm-up is reported but never condemned. Instantly reports
  health 100 from the first hour, so a verdict on a two-day-old inbox would rest on nothing.
- Vitals answers **grouped by domain**, not by account. A missing SPF/DKIM/DMARC/MX record is a
  `fix_dns` proposal against the domain, listing every inbox on it, because pausing one inbox fixes
  nothing. That proposal is `manual`: it is work in the registrar.

On 2026-09-22 all 45 inboxes read 100% and all 15 domains passed all four records.

### Level 2 — inbox placement seed test (Monday, O5)

```bash
MODE=shadow NOTIFY=off python3 jobs/inbox_placement.py --dry-run
MODE=shadow            python3 jobs/inbox_placement.py --now
MODE=shadow NOTIFY=off python3 jobs/inbox_placement.py --dry-run --score-only   # never plan a new test
```

Reads `GET /inbox-placement-tests`, then `POST /inbox-placement-analytics/stats-by-test-id` for
each. Under **85% inbox on Google or Microsoft seeds** proposes a pause and a re-test in **48 h**.
Web.de and Libero.it seeds are reported and ignored. Fewer than 5 seed deliveries for an ESP is
reported as `insufficient` and proposes nothing.

**Two things block this level today.**

1. **The workspace has never run a placement test**, so the stats response shape is unverified. The
   parser handles the plausible variants and marks anything it cannot read as `unparsed` rather
   than inventing a percentage. Check the first real test's output against `--json` before you
   trust a verdict.
2. **There is no seed address list.** The create payload is staged with an empty `emails` array and
   the proposal is marked `blocked`. `GET /inbox-placement-tests/esp-options` and two other guesses
   all answered HTTP 400 on 2026-09-22; the seed list has to come out of the Instantly UI. To
   unblock: open Inbox Placement in Instantly, start a test by hand once, copy the seed addresses it
   uses, then run `python3 jobs/inbox_placement.py --now --seed a@x.com --seed b@y.com ...`.

**A seed test costs Instantly credits, and this job never spends them.** There is no
`POST /inbox-placement-tests` anywhere in it: the payload is recorded as an
`inbox_placement_create_staged` note in `.tmp/shadow_log.jsonl` and staged into the change-set, and
`apply_inbox_actions.py` is the only thing that can execute it (where it is a manual op today).
It used to call `settings.guard_write` for a call it never makes, which in `MODE=live` writes a
`live_write_intent` Job_Log row *before* the call it is supposed to precede: during an incident
reconciliation that row claimed a credit-spending Instantly call may have been accepted upstream
when nothing was ever sent.

### Level 3 — reply rate and bounce (Friday audit)

`GET /accounts/analytics/daily`, chunked at **25 emails per call**. This workspace answers **HTTP
413** without an emails filter, and a silent missing report is worse than a slow one.

- **≥100 sent and <1% real replies** → propose removal from every campaign `email_list`.
- **Bounce >2%** (at ≥50 sends) → the same.
- **Every inbox on a domain failing** → propose retiring the domain. Never heal it.
- **The two rules are judged independently, each on its own volume floor.** The reply rule needs
  `REPLY_RATE_MIN_SENT` (100) sends, the bounce rule `BOUNCE_RATE_MIN_SENT` (50). Picking one
  window for both made the bounce floor unreachable: an inbox with 80 sends and a 10% bounce rate
  was discarded entirely and printed as `sent -, bounce -`.
- **Any judgeable window that fails, fails the inbox.** M1 L3 reads "≥100 sent in 7 d or 14 d and
  <1% real replies", so either window failing is a failure. Judging only on the longest window let
  an inbox with 7 replies in the older week and none in the recent one pass at 2.00% over 14 days
  while its 7-day rate was 0.00%. The reason line names the window that produced the verdict.
- Windows end **yesterday**. At 07:00 today has almost no sends and would drag every rate to zero.

> **`replies` already excludes `replies_automatic`.** They are disjoint counters on this workspace.
> Measured 2026-09-22: `lorenzo@myadvero.com` reports `replies=0, replies_automatic=2`. Subtracting
> (which is what M1 L3 says in words) gives −2 real replies, every inbox lands negative, and the
> monitor proposes pausing the whole fleet on its first run. `shared.thresholds.REPLIES_INCLUDE_AUTOMATIC`
> is the switch, `False` is correct here, and there is a test named after the trap.

> **Replies are counted per lead (`unique_replies`), on every card.** The monitor reads them through
> `shared.analytics.real_replies`, the same definition the capacity inventory, the retro and
> DECISIONS J1 use. It used to sum total `replies`, so a lead who wrote back three times counted
> three times: `lorenzov@theadvero.com` (3 replies from 1 lead in 150 sends) passed here at 2.00%
> while the 07:00 inventory flagged it at 0.67% (MKT-4). Pinned by
> `test_the_monitor_and_the_inventory_agree_on_every_inbox`.

**Thin evidence.** At 150 sends, one extra reply moves an inbox from 0.67% to 1.33% and across the
line. Below `REPLY_RATE_THIN_EVIDENCE_SENT` (300) a failure is still proposed, but it is demoted to
`medium` and the card says which condemnations are one coin flip wide. That is mine, not Eric's.

**Domain retirement carries the same caveat, and it matters more.** At the measured fleet rate
(1.06% per lead over 150 sends per inbox) an individually healthy inbox reads under 1% about half
the time, so all three inboxes on one domain do about 15% of the time, and at least one of four
domains does on nearly half of all Fridays, from noise alone. `DOMAIN_RETIRE_REQUIRES_THICK_EVIDENCE` means a
retirement whose failing inboxes have not cleared 300 sends is still proposed but demoted to
`medium`, marked `thin_evidence`, and the reason carries the domain's total sends and replies so
the sample size is on the card. Retirement is permanent and Eric's rule is never to heal a domain;
it does not get to fire at full volume on half the evidence a single inbox needs.

**A retirement is two proposals.** `retire_domain:<domain>` holds the executable `email_list`
patches; `stop_using_domain:<domain>` is the registrar work. They used to be one proposal, and
because the apply script marks any manual op unexecutable and refuses a proposal that mixes
executable and unexecutable actions, the whole retirement could never be applied at all.

**Not built: the A4 "Friday audit CSV per domain".** Brief A4's definition of done lists a per-domain
CSV from the Friday audit. Nothing writes one. The per-domain level 3 verdicts (reply and bounce
rate, failing inboxes per domain) are on the card. Per inbox, the card's level 3 line gives a failing
count, and each failing inbox appears in the card's PROPOSALS section as a `remove_from_email_list`
proposal whose reason gives the figures it failed on; an inbox on a domain being retired is covered by
that domain's `retire_domain` proposal, which gives the domain's figures. Passing inboxes appear only
in the per-inbox table that `--full` adds under the card, and in `--json`. The Job_Log row and the day's change-set file carry only
the proposals that failing verdicts produce (id, severity and level in the Job_Log row), and no
change-set file is written on a day with no proposal, so passing inboxes and domains appear in
neither. Until the CSV is built, `python3 jobs/deliverability_monitor.py --dry-run --level 3 --json`
prints both tables, passing rows included, as JSON (`level3.per_domain` and `level3.per_inbox`).

### Level 4 — auto-responder canary (Saturday, O7)

```bash
MODE=shadow NOTIFY=off python3 jobs/autoresponder_canary.py --dry-run
MODE=shadow            python3 jobs/autoresponder_canary.py --now
MODE=shadow NOTIFY=off python3 jobs/autoresponder_canary.py --dry-run --harvest-only
```

Harvests auto-responder addresses read-only from `GET /emails?email_type=received` by subject
(`Automatic reply`, `Auto Reply`, `Out of Office`, `Out of office reply`, `no longer monitored`,
`no longer in use`). **31 found on 2026-09-22, 29 after the dead ones, 17 after suppression.**
≥80% auto-responses is healthy, <60% proposes killing the inbox, fewer than 5 addresses is not a
verdict.

**The round is a partition of the pool, never a wrap around it.** `CANARY_MAX_SENDS_PER_ADDRESS` is
1 and it is not a tuning knob. The round-robin modulo this replaces gave 12 inboxes 10 targets each
out of 29 mailboxes, so every one of those 29 real prospects received **4 or 5 near-identical notes
on the same day from 4 or 5 different Advero domains**; at the Oct 11 target of 45 sending inboxes
it would have been 18 or 19 each. That is the burst-from-many-domains pattern this entire monitor
exists to detect, aimed at the mailboxes most likely to be recycled or trapped, produced by the
level whose job is to find that damage. `build_plan` now clamps the round to
`len(pool) // len(inboxes)` and, when that drops below `CANARY_MIN_ADDRESSES_FOR_VERDICT` (5),
**plans nothing at all** and says the pool is too small. That is today's state: 17 usable addresses
cannot give 12 inboxes 5 distinct targets each, so no round is planned. Harvest more before
running one.

**Safety, because these are real prospects' mailboxes:**

- Anyone on the Instantly blocklist (address or domain) is dropped. If the blocklist cannot be read
  **or the walk is truncated**, the job **plans nothing** rather than proceeding without it.
  `BLOCKLIST_MAX_PAGES` is 50 and `CursorWalk.truncated` is checked: the old cap of 10 pages with
  no truncation check meant a blocklisted prospect past entry 1,000 was simply absent from the list
  and kept as a target.
- Anyone with a negative interest status (−1 not interested, −2 wrong person, −3 lost, −4 no show)
  is dropped, **read from the lead, not from the auto-reply row**. `i_status` on a received message
  is null for 8 of the 29 harvested addresses, and null was being read as "no negative status", so
  someone who answered "not interested" and later sent an out-of-office was a valid canary target.
  Every candidate is now resolved through `POST /leads/list` with a `contacts` filter, and anything
  that cannot be verified is dropped.
- **An address with no lead row at all is dropped.** 12 of the 29 harvested addresses are not leads
  in this workspace (verified live 2026-09-22): the auto-reply came from a shared mailbox, an
  assistant or a forwarder rather than from the address that was mailed. Sending a canary to one of
  those is cold-mailing an address that was never on a list.
- "no longer monitored" and "no longer in use" addresses are recorded as dead and never mailed:
  they will never answer, so counting them guarantees a false kill.
- The harvest walk itself refuses a truncated read. A partial harvest changes who gets mailed, for
  reasons nobody can see week to week.
- The canary copy obeys the offer-sheet rules: no em dashes, no exclamation marks, no mention of AI
  or automation, signed Lorenzo, and it says "if it is not, no need to reply".

#### The live canary send

**Instantly v2 has no endpoint that sends an arbitrary email, so this job does not send.** It
records the round as a `canary_send_staged` **shadow-log row** (status `manual_send_required`,
`_sent_by_this_job: false`), in both modes, and stops. `POST /emails/reply` is *not* a
substitute: it would put a second unwanted message into a real prospect's cold-email thread.

It is deliberately **not** a `guard_write` row any more. `guard_write` in `MODE=live` writes a
`live_write_intent` that is meant to be closed by a `live_write_ok` or `live_write_failed` from the
same code path. Level 4 has no send path in any mode, so that row could never be closed, and the
Job_Log read as an intent to email a real prospect that nothing in the process could carry out.
`jobs/inbox_placement.py` and `jobs/retro_packet.py` use the same shadow-row idiom for the same
reason. The report key is `manual_sends` (not `guards`), and the Job_Log details row carries
`manual_sends=N` with `sent=0`.

To run a round for real:

1. `python3 jobs/autoresponder_canary.py --now` and read the planned round in the card. If it says
   the pool is too small, stop: harvest more auto-responder addresses first.
2. **One campaign per inbox.** For each inbox in `plan.assignments`, create a one-off campaign named
   `Canary <date> <inbox>` whose `email_list` holds **exactly that one account**.
   `stop_on_reply: true`, `stop_on_auto_reply: false`, tracking off, text only, daily limit ≥ that
   inbox's slice.
3. Upload that inbox's own `targets` from `changesets/inbox_actions/last_canary.json` as its lead
   list. Nothing else.
4. Launch them. Watch the sends finish.
5. **Write the send timestamp into `last_canary.json` as `sent_at`** (ISO, with offset). Until you
   do, the next run reports the round as unsent and proposes nothing.
6. Next Saturday's run scores it: it reads `GET /emails?email_type=sent` inside the window to learn
   which inbox actually mailed which address, then counts the auto-responses each inbox received
   from its own addresses inside 24 hours of `sent_at`.

> **Why one campaign per inbox.** The old step 2 said one campaign whose `email_list` was every
> inbox being tested, with the round's addresses as its lead list. An Instantly campaign mails each
> lead once from an inbox **it** chooses, so 29 leads produce 29 sends and the plan's (inbox,
> address) pairing is fiction. Replaying the committed 120-pair plan with all 29 mailboxes
> auto-replying scored every one of the 12 inboxes at 0–20% and proposed killing the entire sending
> fleet: a total-collapse card on the morning after the first canary Lorenzo ever ran. The scorer
> now prefers measured attribution from `GET /emails?email_type=sent`, and when it has only the
> plan it refuses to score a round whose overall response rate is healthy while individual inboxes
> land under the kill line, reporting `attribution failure` instead of twelve pause proposals.

**A sent round is never overwritten.** If `sent_at` is set and its 24-hour window has not closed,
a second `--now` (a scheduler retry, or you re-running to look at the card) keeps the existing plan
and plans nothing. Overwriting it used to blank `sent_at` and replace the assignments, so a round
whose emails had already reached real prospects could never be scored and the next round mailed
them again. Each round is also archived to `last_canary_<round_id>.json` when it rolls forward.

*Open question for Lorenzo:* the API contract's rate-limit table mentions a "send a test email"
endpoint at 10/min. If that endpoint can send to an arbitrary address it would replace steps 2–5
entirely. Nobody has confirmed its path or payload, and this job does not guess at send endpoints.

### Level 5 — positive-behaviour baseline campaign

Cold outreach replies near 1%, which is too noisy to separate a dying inbox from a bad offer.
Partner and peer outreach should reply at 10–30%, and it is the same copy to the same audience from
every inbox, so a halved rate on one inbox is a delivery fault.

The spec is written and the campaign is **not created**:
`changesets/inbox_actions/level5_baseline_campaign.json` holds the audience, the settings, both
emails and the create checklist. The monitor reports `not configured` until you paste a real
`campaign_id` into it.

**Known limitation, read before trusting a level 5 verdict:** `GET /accounts/analytics/daily` is per
account, not per account *and* campaign. Until Instantly exposes that, level 5 scores the inbox's
whole daily traffic across the campaign window, which mixes in the revenue campaigns. Keep the
baseline campaign's `daily_limit` small and read the number as directional.

Because of that, **a level 5 proposal is capped at `medium` (`LEVEL5_MAX_SEVERITY`), always carries
`thin_evidence`, and its reason says "level 5 cannot isolate the baseline campaign yet"**. It fires
at `LEVEL5_MIN_SENT` (30) sends against level 3's 300, on a number this file itself calls
directional; before the cap it was emitted at `high` and, sharing a proposal id with level 3's
`remove_from_email_list`, promoted the same thin verdicts to high and deleted their thin-evidence
note on the way. It may never outrank a level 3 verdict on the same inbox, and there is a test
named after that.

### Sudden drop (daily, with level 1), DOMAIN-ONLY for now

**Owner decision R13 (2026-09-22): the check runs per domain only.** One inbox sends at most 150 a
week (25/day, Mon-Sat; 125 on a Mon-Fri schedule), so expecting the 5 replies the check needs before
"none arrived" means anything requires a baseline of at least 3.3% (4.0% at 125), against a fleet at
about 1%. The per-inbox check could therefore never fire, and it used to look armed. Now every inbox
row abstains with that reason (`disabled: true`), the card prints `Sudden drop (domain-only)` and a
`per-inbox: OFF` line, and an abstaining inbox scope never counts toward the check being "usable".
The switch is `shared.thresholds.SUDDEN_DROP_PER_INBOX_ENABLED` (`False`); redesigning the per-inbox
check (a longer window or a Poisson test) is a separate decision for Lorenzo. A domain of three
inboxes sends up to 450 a week (375 on Mon-Fri), so it can be judged once its own baseline is above
about 1.1% (1.33% on Mon-Fri). The domain check stays (R13), but be clear about what that buys: at
the fleet's measured 1.06% per lead, a typical domain sits just under that line and abstains, with
the reason on the card. It judges the domains running above it.

Any domain whose 7-day real reply rate falls below **half** its 28-day average proposes an
immediate pause of its inboxes, then pulls the last 24 h of bounced leads (`FILTER_VAL_BOUNCED` per campaign,
attributed to the sending inbox via `status_summary.lastStep.from`) and scans received mail for
`550` and "reported as spam".

The 28-day baseline **includes** the recent 7 days, which is what "its 4-week average" means and
which makes the test conservative: a collapse drags its own baseline down, so the drop has to be
larger before it fires. For a check whose proposed action is "pause immediately", erring toward
silence is right.

It abstains, loudly, when it cannot judge: baseline under 100 sends, baseline rate under 0.5%,
recent window under 50 sends, **the recent window expecting fewer than
`SUDDEN_DROP_MIN_EXPECTED_REPLIES` (5) replies at the baseline rate**, or — today's case — **the
baseline holds no sends outside the recent week**.

That expected-replies floor is the one that keeps this check honest. Volume is not signal: at this
workspace's reply rate (1.06% per lead), the 50-send floor expects about 0.6 replies, so zero replies
is the *modal* outcome and always reads as a 100% drop. It is also why the per-inbox scope is off. A drop computed on fewer than 300 recent sends is also demoted from
`critical` to `high` and marked thin: `critical` is the loudest thing this system says and it
drives a high-priority push. Sending began 2026-09-15, so the 28-day and 7-day windows are the same data and the ratio is
1.0 by construction. The card prints `Sudden drop: NOT EVALUATED, every domain scope abstained` rather than
"0 flagged", which would read as a passed health check. From about 2026-09-29 there is a week of
history outside the recent window, so the **domain** check can start to judge once a domain's
recent week expects 5 replies at its baseline (at 1.06% that is about 470 sends, more than the 450
three inboxes can send in a Mon-Sat week, so a domain at the fleet rate still abstains; one running
at 1.2% or better is judged). **The per-inbox check does not become useful on that date or any other
at today's volumes**: it is off (R13, above).

---

## 4. Applying a proposal

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
MODE=shadow python3 changesets/inbox_actions/apply_inbox_actions.py --dry-run
MODE=shadow python3 changesets/inbox_actions/apply_inbox_actions.py --dry-run --date 2026-09-22
```

The dry run re-reads live and prints the real diff for every action: the account's current status,
the campaign's current `email_list`, and the exact `+`/`-` lines. **That is the approval surface.**

To apply, after you have read it. **Write key first:** run `set -a; source ~/.advero/live.env; set +a` in the same terminal before the `MODE=live` command (`runbooks/read_only_keys.md` step 3).

```bash
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/inbox_actions/apply_inbox_actions.py \
    --apply --id remove_from_email_list:lorenzo@myadvero.com
```

It will ask you to type the proposal id back. What it does before writing:

- **Re-reads and recomputes.** If live `email_list` no longer matches the `expected_before` the
  proposal was built from, it **refuses**. `PATCH email_list` replaces the whole array, so sending a
  stale array silently re-adds an inbox you removed yesterday or drops one promoted this morning.
- **Backs up the whole campaign object** (not just the list) to `changesets/backups/` first, and the
  account object before a pause. **The backup is a precondition.** If it cannot be written the
  write is not sent and the action records a `REFUSED` error. It used to return `None` on a full
  disk or an unwritable directory and the PATCH went out anyway, with `record['backup']` holding
  the string `"None"` so the printed line still looked like a path.
- **Refuses to empty a campaign.** An `email_list` of zero stops a campaign with no error anywhere.
  The hard floor (`MIN_EMAIL_LIST_AFTER_APPLY`) stays at 1 so a legitimate removal on a two-inbox
  campaign is still possible through the only tool allowed to make one; below
  `WARN_EMAIL_LIST_AFTER_APPLY` (3) the diff prints a loud capacity warning instead of refusing.
- **Refuses a partial apply — but only on a real blocker.** Actions land in four buckets:
  *executable*, *blocked*, *manual* and *satisfied*.
  - **blocked** is a genuine conflict (the live `email_list` no longer matches `expected_before`,
    the account cannot be read, the patch would empty the campaign). Any blocker refuses the whole
    proposal.
  - **manual** is work outside this script. It prints as follow-up and does not stop anything.
    Bundling a manual op into a proposal used to make it permanently unapplyable: that is how
    `retire_domain`, the most consequential level 3 verdict in the system, could only ever be done
    by hand in the UI with no diff, no backup and no audit row.
  - **satisfied** is "already in the desired state". The likeliest human response to a critical card
    is to pause the inbox in the Instantly UI; that used to block the whole proposal, so the inbox
    stayed in every campaign's `email_list` and the monitor regenerated the same dead proposal every
    morning.
- **One proposal per command.** A bad threshold cannot pause the fleet in one keystroke.
- Marks the proposal `applied` (or `apply_failed`) in the change-set so a second run is a no-op.
- **`--dry-run` writes its Job_Log row to a scratch file**, like every other dry-run entry point in
  this component, and restores `JOB_LOG_PATH` afterwards. The 48-hour shadow watch reads
  `.tmp/job_log.csv` and that file was quarantined once already for exactly this pollution.

`fix_dns`, `create_placement_test`, `stop_using_domain` and `canary_send` are marked `manual`: the
script prints them as follow-up work and will not execute them.

**To undo a patch:** the backup file is the campaign object as it was. Restore `email_list` from it
with the same `--apply` path, or by hand in the UI.

---

## 5. The 2026-09-22 baseline

Recorded read-only. Use it to tell a real change from a first-run artefact.

| | |
|---|---|
| Inboxes | 45 total: 12 sending, 33 warming (started 2026-09-20, warm-up done 2026-10-11), 0 paused |
| Warm-up health | 100% on all 45 |
| Vitals | 15 domains, all four records present on every one |
| Capacity | 300 sends/day |
| Sends | 150 per sending inbox over Sept 15–21 (no Sunday sends; the campaign schedule is Mon–Sat) |
| Real reply rate | 1.06% fleet-wide per lead (19 leads replied / 1,800 sends), the Section 6 definition every card now uses; 1.22% counting every reply (22) |
| Automatic replies | 22, counted separately |
| Bounce | 1.11% fleet-wide (20 bounces), worst domain proadvero.com at 1.78% |
| Level 3 | 5 of 12 inboxes under 1% on per-lead replies: `lorenzo@myadvero.com` 0.00%, `lorenzovillarreal@theadvero.com` 0.00%, `lorenzo@proadvero.com` 0.67%, `lorenzov@adveromedia.com` 0.67%, `lorenzov@theadvero.com` 0.67% (3 replies from 1 lead; it passed at 2.00% while the monitor counted total replies, MKT-4) |
| Domains | none retiring: theadvero.com 2 of 3 failing (0.67% reply, 1.11% bounce), the other three 1 of 3 (myadvero 0.89%, adveromedia 1.11%, proadvero 1.56%) |
| Placement | no test has ever run |
| Canary | 31 auto-responder addresses harvested, 29 after the dead ones, **17 usable after suppression**; no round planned (the pool cannot cover 12 inboxes) and none ever sent |
| Level 5 | not configured |
| Sudden drop | domain-only (R13); the domain check has no week of history outside the recent window until ~2026-09-29, and after that it judges a domain only when its baseline is above about 1.1% (only proadvero.com, 1.56%, is clearly above it today; adveromedia.com at 1.11% is on the line). The per-inbox check is off at any date |

**About the canary pool.** 12 of the 29 harvested addresses are not leads in this workspace at all
(checked live: `POST /leads/list` with a `contacts` filter returns nothing for them). The auto-reply
came from a shared mailbox, an assistant or a forwarder rather than from the address that was
mailed, so canarying them would be cold-mailing addresses that were never on a list. That leaves
17, and 17 cannot give 12 inboxes 5 distinct targets each, so level 4 plans nothing until the
harvest grows. Widening `CANARY_HARVEST_MAX_PAGES` past today's 115 received messages is the cheap
first move.

**About those four inboxes.** All four are `thin_evidence`: 150 sends each, one reply either way
decides it. Removing them cuts 100 sends/day from 300, each proposal reads `NO replacement
available` today (no idle inbox has 21 days of warm-up yet), and the cleaning campaigns have not reached their 1,000-send verdict line (M4). The honest reading is that
this is the rule firing early on thin data, not four dead inboxes. **Recommendation: do not apply
these four on this evidence.** Re-run the Friday audit weekly; by the time each inbox has ~300 sends
the verdict means something.

---

## 6. Schedule (when these go on a cron)

| Day | Time CT | Command |
|---|---|---|
| Mon | 06:45 | `python3 jobs/inbox_placement.py --now` |
| Sat | 06:45 | `python3 jobs/autoresponder_canary.py --now` |
| Daily | 07:00 | `python3 jobs/deliverability_monitor.py --now` |

The level-specific jobs run **before** the monitor on their day, so their sidecars are fresh when
the card is built. (The table used to say 07:15, contradicting that sentence two lines below it,
and the ordering mattered: the later writer's pause-only action list replaced the monitor's
complete one in the shared change-set file.)

Every job writes one `Job_Log` row through `shared.job_log.log_run` and alerts through
`shared.notify` on failure — including when the run itself blows up. Each `main()` wraps its run in
`try/except` and emits `log_run(JOB, 'failed', ...)` plus a high-priority `notify`, because a
scheduled 07:00 job that has started failing is otherwise indistinguishable from a quiet morning:
Lorenzo just stops receiving cards, which is precisely the failure this monitor exists to prevent
for the inboxes.

Nothing here is deployed to Modal yet. Registering these in
`services/reply_engine/modal_app.py::SCHEDULES` is a deploy, which needs Lorenzo's sign-off.

---

## 7. Things that will bite the next person

- **`replies` vs `replies_automatic`** — see level 3. This is the one that would have broken the
  system on day one.
- **Vitals is per domain.** 45 accounts in, 15 rows out. Do not index it by email.
- **`GET /accounts/analytics/daily` 413s without an emails filter.** It also returns a bare JSON
  array, not `{items: [...]}`.
- **Instantly does not surface bounce NDRs in the Unibox.** 115 received messages on 2026-09-22 and
  zero delivery-status notifications. `scan_bounce_signatures` reporting no hits is *not* evidence
  of clean delivery, and it says so in its own output. It also reports when its walk was truncated
  (`partial`), because "no NDRs over the newest 500 messages" is a much weaker statement than "no
  NDRs" and the card now prints which one it is.
- **Three jobs write one change-set file.** Proposals carry `generated_by` and a job may only
  withdraw its own. Without that, the 07:00 monitor withdrew the placement job's proposal thirty
  seconds after it was written — caught in the first evidence run, fixed, and pinned by a test.
- **A paused inbox stays in `email_list`.** Pausing alone silently drops a campaign's capacity
  instead of moving it, which is why every pause proposal carries the `email_list` patches too.
- **The monitor imports helpers from `deliverability_monitor` into the other two jobs**
  (`build_inbox_index`, `load_accounts`, `write_changeset`, `write_sidecar`). It is the shared spine
  of the set; if it moves, all three move.
- **`accounts/test/vitals` and the placement endpoints are not on `shared.instantly.Instantly`
  yet.** The jobs call `client.test_vitals(...)` if it exists and fall back to
  `client._request("POST", ..., retry=True)` through `_read_post`. Both are POSTs that only read,
  and neither is on `shared.instantly.READ_POST_PATHS`, so without the explicit `retry=True` a
  transient 429 or 503 on vitals was treated as a write, never retried, and took the whole 07:00
  run down. Adding those two paths to `READ_POST_PATHS` would make the explicit flag redundant;
  that is a change to the shared client, not to this component.
- **Level 2 and level 4 verdicts age.** `last_placement.json` and `last_canary.json` are read with
  their `as_of` and dropped past `PLACEMENT_RETEST_HOURS` / `CANARY_RESULT_MAX_AGE_DAYS`. Without
  that, one stale failing row re-proposed a high-severity pause every single morning with no date
  anywhere for Lorenzo to notice, and the card printed a months-old summary as today's.
- **A level that could not be evaluated may not withdraw its own proposals.** Proposals carry the
  level that produced them, and `write_changeset` only withdraws a leftover whose `(generated_by,
  level)` this run actually evaluated. A 12:00 rerun that hit a 413, or a plain
  `--now --level 1` on a Friday afternoon, used to mark the morning's `retire_domain` verdict
  `withdrawn` and the apply script then skipped it.
- **Action lists are unioned across writers, not replaced.** A pause-only list from the canary or
  the placement job used to overwrite the monitor's complete one for the same proposal id. Both
  jobs now emit the full `_pause_actions` list anyway, and the merge keeps both halves.
- **One proposal per inbox, whatever condemned it.** Dedupe keys on the target (plus the family of
  action), not on `kind:target`. Level 1's `pause_inbox` and level 3's `remove_from_email_list`
  used to survive as two proposals, each claiming a different idle replacement inbox, and applying the
  first made the second stale.
- **The replacement swap respects `MAX_INBOXES_PER_DOMAIN`** (the code still calls the idle
  replacement inboxes `insurance`). A replacement that would put a fourth
  inbox from one domain into a campaign is skipped in favour of the next candidate.
