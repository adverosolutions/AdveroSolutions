# Runbook: inbox health and insurance promotion (M2 / brief A5)

**Health alerts only (Lorenzo, 2026-09-22).** How many sending inboxes to hold, and when to buy
more, is Lorenzo's decision, not the system's. This job reports inbox and domain health: warm-up
score, warm-up off, bounce and reply lines, missing analytics, inboxes that are not status 1
(paused, disconnected or erroring), and whether anything is sending at all. It does **not** count a
reserve, size a reserve target, forecast capacity for a go-live date, or recommend buying or
ordering inboxes or domains. `changesets/capacity/domain_order.md` stays as Lorenzo's own manual
buying doc; nothing in the job points at it.

| | |
| --- | --- |
| Job | `jobs/inbox_inventory.py` |
| Output | `config/inbox_inventory.json` (refreshed every run with `--now`) |
| Change-sets | `changesets/capacity/` (promotions and recorded snapshots) |
| Tests | `python3 -m pytest jobs/tests/test_inbox_inventory.py -q` (95) |
| Schedule | daily 07:00 CT, alongside the deliverability monitor (O1) |
| Writes to a live system | **none.** Every Instantly call is a GET or a POST-shaped read |

## Run it

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"

python3 jobs/inbox_inventory.py --dry-run          # live reads, prints, writes nothing
python3 jobs/inbox_inventory.py --now              # + refreshes config/inbox_inventory.json + ntfy digest
python3 jobs/inbox_inventory.py --dry-run --json   # the whole inventory as JSON
python3 jobs/inbox_inventory.py --dry-run --fixtures                        # offline replay
python3 jobs/inbox_inventory.py --dry-run --as-of 2026-10-11T07:00:00-05:00 # evaluate at another clock
```

`--dry-run` redirects its Job_Log and shadow log into `.tmp/scratch/inbox_inventory/` so evidence
runs never pollute the real `.tmp/job_log.csv`. `--now` writes the real row.

`--now --fixtures` is **refused** unless you also pass `--out`: replaying the recorded snapshots
into `config/inbox_inventory.json` would leave replayed data in a file that looks live.

Every run leaves exactly one Job_Log row: `inbox_inventory,<ok|attention|partial>` with the role
counts (active, warming, retired), active capacity today, the sending alerts, the actionable flag
count and how many domains carry an unhealthy inbox. A crash, at any stage, writes an `error` row
and pushes an ntfy alert; the write, the render and the digest are all inside that guard.

| Status | Means | Exit code |
| --- | --- | --- |
| `ok` | no inbox carries an actionable flag and something is sending | 0 |
| `attention` | at least one inbox carries an actionable flag, or a sending alert fired (see below) | 0 |
| `partial` | an analytics chunk, or an accounts/campaigns page, could not be read | **1** |

The ntfy push is titled `Inbox health: N inbox(es) flagged`. A sending alert leads the title
instead (`Inbox health: ALERT no_active_capacity`, plus the flag count when there is one), an
analytics outage gives `N inbox(es) with NO analytics`, and only a run with no flag and no alert
says `no alerts`. The body says plainly where health dropped, one line per domain, for example
`2 inbox(es) unhealthy on theadvero.com (reply_rate_below_1pct).`

A `partial` run **does not overwrite `config/inbox_inventory.json`** when any *active* inbox lost
its analytics window, and the ntfy push leads with the outage instead of a flag count computed
over missing data. A partial pull used to be the most dangerous kind of green run: five inboxes
under the Section 6 removal line simply disappeared from the report.

### Sending alerts

`capacity.alerts` says the sending estate itself has failed. These are health, not buying, alerts.

| Alert | Means |
| --- | --- |
| `no_inboxes` | the accounts pull came back empty: API-key scope change, workspace switch, or the estate is gone |
| `no_active_capacity` | inboxes exist but none of them is in a sending campaign |

## What the roles mean

| Role | Definition | Today |
| --- | --- | --- |
| `active` | in the `email_list` of a campaign that is **sending** (`status == 1`) | 12 |
| `warming` | not in a sending campaign, fewer than 21 days since warm-up started | 33 |
| `idle` | not in a sending campaign, warm-up finished, ready to swap in | named, not totalled |
| `retired` | Instantly `status != 1` (paused, disconnected, erroring) or `setup_pending`, whatever else is true | 0 |

`retired` wins over everything on purpose: promoting a paused or half-built account into a
campaign is how a dead inbox ends up sending.

The `idle` role is kept **per inbox** because `--promote` picks its candidate from it (the code
constant is still `ROLE_INSURANCE`). It is named but never totalled: the headline ends "the rest
idle (not in any sending campaign)", a domain row says `idle` without a number (the JSON carries
`has_idle_inboxes`), and `counts.by_role`, the push and the Job_Log leave it out, because that
total is a reserve count and the reserve is Lorenzo's call.

Membership of a **draft or paused** campaign is not capacity. It is recorded per inbox as
`inactive_campaign_ids` / `inactive_campaign_keys` and surfaced as the informational flag
`in_paused_campaign`. Staging the scale-up as a draft campaign with the new inboxes pre-assigned
is the natural thing to do; counting it as active capacity moved 575/day of imaginary sends into
the report and emptied the insurance pool at the same time.

## What it sends today

```
active capacity   = sum(daily_limit) over active inboxes      = 12 x 25 = 300/day
campaign ceiling  = sum(daily_limit) over sending campaigns   =  6 x 50 = 300/day
binding           = whichever side is lower (today: balanced)
```

`capacity` in `config/inbox_inventory.json` holds only today: `today` (active, warming and retired
inbox counts plus active capacity), `alerts`, and `campaign_limits` (the six campaigns' own
`daily_limit` fields and which side binds). There is no target date, no planned active count, no
reserve ratio and no order size. `promote_insurance` quotes the campaign total in its capacity
note so a swap is read against the real ceiling.

## Reply rate: the arithmetic that must not change

`replies_automatic` in `GET /accounts/analytics/daily` is an **independent counter, not a subset
of `replies`.** Measured on 2026-09-19 across the twelve active inboxes: `replies=0` and
`replies_automatic=7`.

Reading Blueprint M1 level 3's "exclude auto-replies" as a subtraction gives that day a reply
count of -7, drags every active inbox under the 1% line and retires the whole estate on the first
Friday audit. The real reply rate is `unique_replies / sent` as it stands. `replies_automatic` is
the auto-responder canary of level 4 and is reported separately.

Pinned by `test_replies_automatic_is_never_subtracted_from_replies` and
`test_real_snapshot_has_a_day_where_automatic_exceeds_replies`. If you change this, change both
tests and this section in the same commit.

## Flags (Section 6 thresholds)

| Flag | Rule | Action |
| --- | --- | --- |
| `account_status_error` | Instantly `status < 0` (connection error, soft bounce error, sending error), wherever the inbox sits | reconnect or fix the mailbox in Instantly |
| `retired_in_sending_campaign` | a `retired` inbox (not status 1, or `setup_pending`) still in a sending campaign's `email_list` | take it out of the campaign, or bring it back to status 1 |
| `warmup_below_98` | `stat_warmup_score < 98` | pause the inbox, promote insurance |
| `warmup_off` | warm-up disabled | turn it back on. Warm-up stays on forever, on every inbox |
| `bounce_above_2pct` | 7-day bounce > 2% | remove from the campaign |
| `reply_rate_below_1pct` | >= 100 sends in 7 days and < 1% real replies | remove from the campaign |
| `daily_limit_off_plan` | an active inbox not at the limit the **ramp plan** prescribes for it today | reconcile against the ramp plan |
| `daily_limit_zero` | a non-retired inbox explicitly set to 0/day | it is not sending; intentional or not, say which |
| `analytics_missing` | the 7-day window for this inbox could not be read this run | do not trust its rates, and it cannot be promoted |
| `warmup_score_immature` | fewer than 7 days old | **informational**: a 100 from a 2-day-old inbox means nothing |
| `in_paused_campaign` | listed in a draft or paused campaign | **informational**: not capacity, but it would be if that campaign resumed |

The exact boundaries are pinned by `test_flags_at_exactly_the_section6_thresholds`: exactly 1.00%
reply is not flagged, exactly 100 sends is the minimum that counts, exactly 2.00% bounce is not
flagged, warm-up exactly 98 is not flagged, and exactly 2.00% reply does earn 30/day.

`counts.flagged` is the **actionable** count; the two informational flags are counted separately
in `counts.flagged_informational`. The printed table, the ntfy push and the Job_Log row all read
the same field. They used to disagree: the push said "38 inbox(es) flagged" while the table under
it said 5, which reads as an estate-wide emergency when the real story is five inboxes under the
reply line.

`daily_limit_off_plan` compares against the ramp plan, not the bare constant 25. From 2026-11-01
an inbox clearing 2% real replies is *supposed* to be at 30/day; flagging that trains you to
ignore the one table that carries Section 6 alerts.

Today five of the twelve active inboxes carry `reply_rate_below_1pct` (150 sends each, 0 or 1
reply), on four domains. The push says so per domain. They are **not** auto-removed: removing an
inbox is a change-set Lorenzo approves.

## The ramp plan

Written as data in `config/inbox_inventory.json` under `ramp_plan.per_inbox`: a list of
`{from, to, open_ended, daily_limit, warmup, reason}` segments per inbox, today to the plan
horizon. The last segment carries `open_ended: true`: it is the standing limit from 2026-11-01
onward, not a one-day window.

- 25/day now, on every active inbox.
- A warming inbox sits at `daily_limit 0` for cold sending until its 21st day, then 25/day.
- 30/day from 2026-11-01, and **only** for an inbox whose 7-day real reply rate is at least 2% on
  that day. Recompute on the day; the plan in the file is built from today's data and names the
  rule, not a promise.
- `warmup: "on"` in every segment of every inbox, including retired ones. Warm-up never gets
  turned off. On today's data two inboxes (`lorenzov@proadvero.com`,
  `lorenzovillarreal@proadvero.com`) would clear the 2% bar.
- The horizon is `max(2026-11-01, today, the day that inbox starts sending)`, never a bare
  constant. A fixed end date makes every segment run backwards on any run after it
  (`{"from": "2026-12-15", "to": "2026-11-01"}`), and anything selecting the segment where
  `from <= today <= to` then finds none. Pinned by `test_ramp_segments_never_invert`.

## Promoting an insurance inbox

When the deliverability monitor (O1/A4) fails an inbox, or you spot one in the flag table:

```bash
# writes changesets/capacity/promote_<campaign>_<inbox>_<ts>.json
python3 jobs/inbox_inventory.py --promote cleaning_reactivation:lorenzo@theadvero.com

# preview only, writes nothing
python3 jobs/inbox_inventory.py --promote cleaning_reactivation:lorenzo@theadvero.com --no-changeset
```

`--promote` writes the change-set **by default**: a local JSON file is not a live write, and the
moment you run this is the moment an inbox is burning. `--no-changeset` is the preview, and
`--changeset-dir` puts it somewhere else. It does **not** refresh `config/inbox_inventory.json`
and does not fire a digest; that is what `--now` is for.

`promote_insurance()` picks the healthiest insurance inbox (warm-up score, then a **measured**
bounce rate ahead of an unmeasured one, then age), skips any candidate carrying a Section 6 flag,
skips any domain that already has 3 inboxes in that campaign, and **never puts more than 3 inboxes
from one domain in one campaign**. It takes no API client and cannot reach the network.

Three gates that fail **closed**:

- **no data is not clean.** A candidate with no warm-up score, or whose analytics window could not
  be read this run, is rejected. The old gate was "the row has no flags", and a row with no
  analytics has no flags: an inbox at 8% bounce was proposed as "the healthiest insurance inbox".
- **quarantine.** Every inbox a change-set pulls out is written to a ledger in `shared.store`
  (`capacity.quarantine`) with the flag that removed it. It stops being a promotion candidate
  until you clear it: `python3 jobs/inbox_inventory.py --clear-quarantine lorenzo@theadvero.com`.
  Without it, an inbox pulled for a 6% bounce comes back a week later with an empty window, no
  flags and the oldest age in the pool, and wins the next promotion.
- **the domain cap** is counted on the proposed list, so a domain already at 3 cannot be topped up.

### Capacity, honestly

**All twelve live inboxes are in all six campaigns.** Pulling one out of ONE campaign therefore
does not stop it sending. The record carries `remaining_campaigns` and
`failing_inbox_still_sends`, and `capacity_delta_per_day` is an **estate** number: 0/day when the
inbox still sends elsewhere, `-25/day` only when this was its last campaign, `+25/day` for the
promoted inbox because insurance sends nothing today. To take an inbox out of the estate, write
one change-set per campaign it is in.

Then review and apply:

```bash
python3 changesets/capacity/apply_promotion.py --changeset changesets/capacity/promote_....json
```

The dry-run re-reads the live campaign, re-checks every invariant, prints the `email_list` diff and
writes its copy of the live campaign JSON under `.tmp/changeset_dryruns/promotion/` as a `.dryrun.json`
(never into `changesets/backups/`, which holds only real rollback points). It refuses:

- a stale change-set (the failing inbox already gone, or the live list changed since the proposal,
  naming exactly which addresses differ);
- a proposed list that is **not** "live minus the failing inbox plus the promoted one". Nothing
  else may be PATCHed, and a hand-edited file is refused;
- any address in the proposed list that is not a live, enabled Instantly account, not only the
  promoted one (this is how a ghost address in a live `email_list` is caught and named, instead of
  being PATCHed straight back);
- a promoted inbox that is already in another **sending** campaign, or whose health figures were
  never measured. Membership of a paused or draft campaign is a printed warning, not a refusal;
- a domain over the cap, or an empty list.

Only after Lorenzo has read that diff does the apply run, with both live flags set and
`--apply --yes`. In shadow the apply exits `2` and sends nothing. **Write key first:** run `set -a; source ~/.advero/live.env; set +a` in the same terminal before the `MODE=live` command (`runbooks/read_only_keys.md` step 3).

The apply re-reads the campaign after the confirmation and refuses (exit 2, nothing sent, nothing
written) if the `email_list` moved while the prompt was open; that fresh read is the before-image,
saved as the rollback point `changesets/backups/promotion_<campaign_id>_<ts>.json`. To undo it:
**Write key first:** run `set -a; source ~/.advero/live.env; set +a` in the same terminal before the `MODE=live` command (`runbooks/read_only_keys.md` step 3).

```bash
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_promotion.py \
    --restore changesets/backups/promotion_<campaign_id>_<ts>.json --campaign <campaign_key>
```

The restore reads live first and prints the per-field diff before it asks. It refuses (exit 2) when
the `email_list` changed after the promotion (for example a later burned-inbox removal), because
putting the before-image back would undo that too; add `--override-later-changes` only after
reading the diff. The override is refused together with `--yes`, so a person always types the
confirmation, and the Job_Log row records `override_later_changes` and the drift lines. After the
confirmation the restore reads the campaign again and refuses (exit 2, nothing sent or written) if
the list moved while the prompt was open; its `.prerestore.json` is built from that second read.

### Oct 11 capacity change-set (`apply_capacity.py`)

`changesets/capacity/apply_capacity.py` adds warmed inboxes to one campaign's `email_list` and sets
its `daily_limit`. Option A and Option B are defined in `runbooks/DECISIONS_FOR_LORENZO.md` Q-L1, the
same as `changesets/capacity/domain_order.md`; which one to run is Lorenzo's choice, so the per-campaign
plan is an input file he fills in once he has chosen. `changesets/capacity/oct11_capacity.example.json` shows the shape, says
`"example": true`, and `--apply` refuses it.

**Write key first:** run `set -a; source ~/.advero/live.env; set +a` in the same terminal before the `MODE=live` command (`runbooks/read_only_keys.md` step 3).

```bash
# dry-run (default, zero writes; copy under .tmp/changeset_dryruns/capacity/)
python3 changesets/capacity/apply_capacity.py --input changesets/capacity/oct11_capacity.json
python3 changesets/capacity/apply_capacity.py --input <file> --campaign cleaning_reactivation

# apply: live flags, ONE campaign, typed confirmation
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_capacity.py \
    --input <file> --campaign cleaning_reactivation --apply

# restore: live flags, typed confirmation after the live read
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_capacity.py \
    --restore changesets/backups/capacity_<campaign_id>_<ts>.json --campaign cleaning_reactivation
#   add --override-later-changes only to also undo changes made after the apply (never with --yes)
```

It refuses any inbox it would add that is not an enabled Instantly account with warm-up running,
a warm-up score of at least `TH.WARMUP_HEALTH_MIN_PCT` and at least `TH.WARMUP_DAYS_BEFORE_PROMOTION`
(21) days of warm-up; a domain pushed past the cap; and a live read without an `email_list` list.
When nothing differs it sends and writes nothing, so a re-run never replaces the rollback point.
After the typed confirmation it reads the campaign again and refuses (exit 2) if `email_list` (as a
set) or `daily_limit` moved while the prompt was open. A PATCH that errors still leaves the
unsuffixed rollback point `capacity_<campaign_id>_<ts>.json`, because the write may land later.

**Restore exit 3.** Both restores (promotion and capacity) use
`changesets/rollback.py`, and exit 3 means the restore did not end verified. Not every exit 3 has an
`outcome`:

- **`API error: ...` (capacity) or `Instantly error: ...` (promotion):** an Instantly read failed,
  either the first live read or the re-read after the confirmation (`rollback.py:514`, `567`). Both
  happen before the `.prerestore.json` copy and before any PATCH, so **nothing was written**. The
  Job_Log row is `restore_error`, with the error and no `outcome` (`apply_capacity.py:359-362`,
  `apply_promotion.py:332-335`). Re-run the same `--restore` command.
- **`no Instantly client: ...` (capacity) or `Instantly client: ...` (promotion):** the Instantly
  client could not be built (for example no API key), so nothing was read or written, and **no
  Job_Log row is written at all** (`apply_capacity.py:324-331` and `351-353`,
  `apply_promotion.py:321-326`). Fix the key, then re-run.
- **Anything else:** the Job_Log row is `restore_failed` and its `outcome` names the case
  (`changesets/rollback.py:552-629`).

The common outcome is
`restored_unverified`: Instantly acknowledged the PATCH, but neither the response nor a re-read shows
the point's fields exactly as it has them (`email_list` for a promotion, `email_list` and
`daily_limit` for a capacity apply; `email_list` is compared as a case-insensitive set); the script prints each field that still differs, **except when that re-read failed too: then it prints no
field lines** (`rollback.py:617-624`). Either way the `.prerestore.json` copy of what it
overwrote was already written. What you do next: check the campaign's sending accounts and daily limit
in the Instantly UI (with no field lines printed, check **every** field the rollback point names, listed
on the restore's first `rollback point written ... fields [...]` line), then re-run the same `--restore` command once. `live already matches the rollback
point` (exit 0) means it is done. The same field differing again, or `CHANGED SINCE THE APPLY` on it,
means Instantly stored something other than what was sent: stop, do not add
`--override-later-changes`, do not loop the restore, and bring both runs' output and the
`.prerestore.json` path to the next session. The other exit-3 outcomes: `partial` (a field has no
before-image in the point; fix it in the UI), and `landed_after_error`, `not_restored_at_reread` or
`unknown` (the PATCH raised; the re-read says whether it landed). A restore run without the write
key also fails at the PATCH and ends as `not_restored_at_reread` (the reads work on the read-only
key; the PATCH raises `INSTANTLY_API_KEY is not set in this process`), so check that
you ran `set -a; source ~/.advero/live.env; set +a` in that terminal before re-running.

**Warm-age on the day:** the 33 new inboxes started warming at 2026-09-20T23:39Z, so at 14:00 UTC
on Oct 11 they are 20.6 days old, not 21. The script refuses them until about 18:40 CT (23:39 UTC)
on Oct 11. Plan the capacity apply for that evening, or accept that a morning run adds only the
inboxes that are already past 21 days.

## Today's state, in one paragraph

45 inboxes on 15 domains, all at warm-up 100 and warm-up on. 12 active at 300/day against a
campaign ceiling of 300/day, 33 warming, none retired. Sept 15 to 21: 1,800 sent, 1.11% bounce,
1.06% real replies, and five inboxes under the 1% reply line on four domains (theadvero.com 2,
adveromedia.com 1, myadvero.com 1, proadvero.com 1). No bounce, warm-up or disconnection alert.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `partial` Job_Log row, exit 1, `analytics_errors` non-empty | a daily-analytics chunk answered 413 twice at half size | the affected inboxes are marked `analytics_missing` and the deliverable is not overwritten. Lower `ANALYTICS_CHUNK` if it repeats. **Do not** read the flag table as complete |
| `source_errors` mentions a truncated walk | the accounts or campaigns pull stopped at `max_pages` | inboxes may be missing from the flag table. Raise `max_pages` or page the read differently; do not act on the numbers |
| `InstantlyError: no Instantly key` or `INSTANTLY_API_KEY is not set in this process` | no read key in `Agentic Worklfows/.env`, or a write run without the write key | put `INSTANTLY_API_KEY_READ` in `Agentic Worklfows/.env` for reads; for a write run, `set -a; source ~/.advero/live.env; set +a` in that terminal (the file has no `export` lines, so a plain `source` does not reach the Python process). The write key goes only in `~/.advero/live.env`, never a repo `.env` (`runbooks/read_only_keys.md`) |
| Every inbox suddenly `reply_rate_below_1pct` | someone reintroduced the `replies - replies_automatic` subtraction | see the arithmetic section above |
| An inbox shows `role: retired` unexpectedly | Instantly set `status != 1` (usually a disconnected mailbox). A negative status carries `account_status_error`, and a retired inbox still in a sending campaign carries `retired_in_sending_campaign`; both make the run `attention` | reconnect it in Instantly before anything promotes it |
| `promote_insurance` always says `removed_without_replacement` | no warm, unflagged, unquarantined inbox is outside the campaign | the removal still goes ahead on its own; the job does not advise on adding inboxes |
| A known-good inbox is refused as a candidate | it is in the quarantine ledger from an earlier removal | check it by hand, then `--clear-quarantine <email>` |
| The push or the Job_Log mentions an order, a reserve ratio or `--target` | you are on a build from before 2026-09-22 | update; the job is health alerts only now |
