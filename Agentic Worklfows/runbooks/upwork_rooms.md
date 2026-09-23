# Upwork rooms check (M6 / O2)

**What it is:** twice a day, at 09:00 and 15:00 CT, one list of Upwork rooms and
invitations waiting on Lorenzo, oldest first, plus a reminder 48 hours after any
contract ends to ask for a review, a testimonial and a maintenance retainer.

**What it is not:** it never drafts and never sends anything on Upwork. The
application flow (job selection, the Demo Library paste-and-record loop, the
Loom, the proposal, boosting) is out of scope and untouched. The job has no
Upwork write path at all, and `test_module_has_no_upwork_write_path` reads the
parse tree to keep it that way.

| | |
|---|---|
| Job | `jobs/upwork_rooms.py` |
| Tests | `jobs/tests/test_upwork_rooms.py` (81, on responses recorded from the live MCP on 2026-09-22) |
| Blueprint | M6 (Section 3), O2 (Section 6), brief A8 |
| Schedule | 09:00 and 15:00 CT |
| Reads | `.tmp/upwork_rooms.json` only. No network. |
| Writes | one Job_Log row, and on `--now` one notification to Lorenzo: a **counts-only** ntfy card plus the full digest by email. The card carries names and message text only when `NTFY_TOKEN` is set (see "What the push carries"). |
| Thresholds | Section 6: response time target under 1 h, alert over 4 h. Post-contract ask at 48 h, and it expires after 21 days. |

---

## The handoff, and why there are two halves

The Upwork MCP connector only exists inside a Claude session. A cron job cannot
reach it. So:

```
Claude session  --(read-only MCP calls)-->  .tmp/upwork_mcp_raw.json
      |
      |  python3 jobs/upwork_rooms.py --ingest .tmp/upwork_mcp_raw.json
      v
.tmp/upwork_rooms.json   <--(read)--  jobs/upwork_rooms.py   (this job, 09:00 / 15:00)
                         <--(read)--  jobs/pipeline_sweep.py (O3, 07:30)
```

`.tmp/upwork_rooms.json` is shared with the pipeline sweep, which reads the same
room keys for its Upwork section. `test_ingest_writes_a_snapshot_pipeline_sweep_can_read`
round-trips a snapshot through `pipeline_sweep.find_upwork_awaiting`, so the two
readers cannot drift apart silently.

### Refreshing the snapshot (a session, once or twice a day)

```bash
python3 jobs/upwork_rooms.py --print-collect
```

prints the exact calls. All three are read-only:

| # | Tool | Action | Params | Paging |
|---|---|---|---|---|
| 1 | `upwork__get_messages` | `list_rooms` | `{"limit": 50, "room_type": "ALL"}` | most-recently-active first, `limit` caps at 100. **Keep calling with `cursor`/`next_cursor` while `hasMore` is true.** |
| 2 | `upwork__list_contracts` | `search` | `{"contract_statuses": ["ACTIVE","CLOSED","PAUSED"], "limit": 10}` | `limit` caps at 10. **Page with `offset` (0, 10, 20, ...) until a page comes back short.** |
| 3 | `upwork__list_offers` (optional) | `list_mine` | `{"limit": 10}` | - |

`org_uid` is `config/ids.json` -> `upwork.org_uid`.

Paging is not optional once the account grows. The rooms call returns the *most
recently active* rooms first, so the ones that fall off the end of an unpaged
page are exactly the long-unanswered ones this job exists to find; and a
contract that just ended can fall off the 10-row contracts page, which silently
kills its 48-hour review ask. Today the risk is latent (3 rooms, 2 contracts,
`hasMore` false), which is why the ingest records a `truncated` flag and the
digest prints `the pull was truncated, older rooms or contracts are not listed`
rather than relying on anyone noticing.

**Never** call `upwork__send_message`, `upwork__manage_proposals`,
`upwork__respond_to_offer`, `upwork__manage_meetings`, `upwork__submit_milestones`
or `upwork__boost_profile`. `.claude/hooks/guard_live_writes.sh` blocks all of
them, and this job exists precisely so nothing is drafted or sent.

Save the raw responses verbatim. Concatenated pages are fine: pass a list of
responses per key (`"rooms_response": [page 1, page 2]`), a top-level list of
pages, or merge the pages into one `rooms` / `contracts` list. Every page is
checked for an error envelope, and `truncated` is taken from the **last** page
of each half only, so a complete paged pull (every page but the last says
`hasMore`) is not flagged. The per-key page list used to be refused with
`carries no rooms list`, and any non-final `hasMore` flagged a complete pull as
truncated (re-review OPS-7).

```json
{"collected_at": "2026-09-22T00:45:00-05:00",
 "rooms_response":     { ...response 1... },
 "contracts_response": { ...response 2... },
 "offers_response":    { ...response 3, optional... },
 "manual_checks":      [ ...optional, overrides the built-in list; [] means none left... ],
 "contract_asks":      {"44501032": {"asks_done": ["review"]}}}
```

then normalise:

```bash
python3 jobs/upwork_rooms.py --ingest .tmp/upwork_mcp_raw.json
# wrote .tmp/upwork_rooms.json: 3 rooms, 2 contracts, 2 manual checks (generated_at ...)
#   covered: rooms, contracts
```

A single raw response also works, on a file or on stdin (`--ingest -`); the
bundle keys are a convenience, not a requirement. The `covered:` line says which
halves the pull carried, and the digest says so too when one is missing, because
"no closed contracts" and "the contracts call was never made" produce the same
empty section otherwise.

**A pull that carries only one half keeps the other half from the previous
snapshot, marked as older.** A contracts-only pull used to replace a complete
snapshot and every waiting room disappeared. Now the rooms (or contracts) are
carried forward from the snapshot being replaced, with their own stamp in
`carried`, and the ingest prints `rooms carried forward from the previous
snapshot (not in this pull)`. The digest says `rooms were not in this pull, the
rooms below are from the pull of <timestamp> and may have moved on`; the title
gets `(rooms from an older pull)` (or `(rooms not checked)` when there was no
earlier snapshot, or `(truncated pull)`), the ntfy card repeats the caveat, and
the Job_Log status is `partial` instead of `ok` (re-review OPS-9).

### A pull that failed is not an empty pull

`--ingest` **refuses** and exits 2, leaving the previous snapshot in place, when
the input is not a recognisable successful response:

| Input | Result |
|---|---|
| `{"rooms_response": {"status": "error", ...}}`, or an error on any page of a page list | `refusing to write the snapshot: rooms_response page N carries an error response (...)`, exit 2 |
| `{"rooms_response": null, ...}` (or `contracts_response: null`) | `refusing to write the snapshot: rooms_response is null; the pull did not succeed`, exit 2. A key that is present and null is a call that returned nothing, not a call that was never made |
| `null`, `{}`, `[]`, a bare string, a bundle with no response in it | `refusing to write the snapshot: no rooms and no contracts response in this input; the previous snapshot is kept`, exit 2 |
| a file that is not JSON, or does not exist | `could not read ...`, exit 2 |
| `{"data": {"rooms": []}, "status": "ok"}` | accepted: a real pull with no rooms in it |

This is the one route that used to bypass the whole degradation path. A failed
MCP call wrote an empty snapshot stamped with the current time, so the 09:00 run
reported `snapshot: fresh`, `status: ok` and a digest with every real room
silently gone. The rule now is that `0 rooms returned` and `no rooms key at all`
are different answers, and only the first one is written.

If a call fails, save what it actually returned rather than an empty object. The
refusal is what makes `no fresh Upwork data, last seen ...` fire on the next run.

---

## Running the check

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"

python3 jobs/upwork_rooms.py --dry-run          # compute, print, Job_Log row to a scratch log, no push
python3 jobs/upwork_rooms.py --now              # same plus the notification to Lorenzo
python3 jobs/upwork_rooms.py --dry-run --as-of 2026-09-22T09:00:00-05:00
python3 jobs/upwork_rooms.py --dry-run --json   # machine readable
python3 -m pytest jobs/tests/test_upwork_rooms.py -q
```

`--dry-run` redirects the Job_Log to `.tmp/scratch/upwork_rooms_dryrun/`, because
the 48-hour shadow watch is gated on reading `.tmp/job_log.csv`
(`shared.job_log.use_scratch_logs`). It also **wins over `--now`**: `--dry-run
--now` prints `--dry-run given with --now: computing and printing, no push` and
sends nothing, so the word means the same thing here as everywhere else in the
build. `--as-of` fixes the clock: no function outside `main()` reads it, and a
test enforces that on the parse tree.

The digest is read-only output. There is nothing to approve and nothing to
apply; `MODE` only affects the notification, which is guarded like any other
outbound write.

### Sample output (real data, 09:00 CT on 2026-09-22)

```
Waiting on you (5, oldest first):
1. RoutVox Consulting call request, 26.4 days waiting
   Upwork Messages > Invitations tab (call request, not visible through the API)
2. Jennifer Lawson, Jennifer L, 7.8 days waiting
   last: **Jennifer Lawson** ended the contract
3. ClosePoint USA invitation (GHL expert), 6.4 days waiting
   Upwork Messages > Invitations tab (client invitation, not visible through the API)
4. Aysha Sanam, Treasure Labs LLC, 4.8 days waiting
   last: Aysha: Great thanks will do
5. Mark Firth, 7.3 h waiting, over the 4 h alert line, 2 unread
   last: Mark: approx 25k emails

Manual checks do not clear themselves. When one is answered, mark it done in config/ids.json upwork.manual_checks (see runbooks/upwork_rooms.md).

Post-contract asks (48 h after the contract ended):
1. Jennifer L (AI automation, contract 44491561), ended 2026-09-14
   note: no review/testimonial ask sent yet; 7-day support window ended Sept 21
   confirm the note, then ask for review, testimonial, maintenance retainer
2. Treasure Labs LLC (Cold Email Outreach Setup, contract 44501032), ended 2026-09-17
   note: review/testimonial already asked in Lorenzo's close-out message; warmup check-in promised around Oct 5
   confirm the note, then ask for review, testimonial, maintenance retainer
To stop an ask repeating, add asks_done for that contract (see runbooks/upwork_rooms.md).

Read only. Nothing was drafted and nothing was sent on Upwork.
```

---

## The rules it applies

**Waiting on you.** A room counts when the MCP says `awaiting_reply_from: you`.
When the MCP cannot place the last sender it omits that field; the job then falls
back to `last_message_from_self`, and if that is missing too it keeps the room
and labels it `last sender not placed, read the thread`. Over-reporting a room
Lorenzo dismisses in one glance is cheap; dropping one silently is not. Rooms are
de-duplicated by `room_id` (last wins), so a bundle that carries overlapping
pages lists each client once.

**Oldest first.** Rooms and manual invitations are merged into one list and
sorted by wait length. A room whose timestamp cannot be read sorts *last*, not
first: an unknown age is not evidence of a long wait.

**The alert phrase.** Section 6 puts the target under 1 h and the alert over 4 h.
The digest prints `over the 4 h alert line` only on **rooms** under 48 h old,
where it is news. On a six-day-old room "6.6 days waiting" already says it, and a
phrase repeated on every row is what makes a digest go unread. 48 h is
`AGE_DAYS_SWITCH_HOURS`, the same constant the h/days format switches on, so the
wording and the number cannot disagree. The full count is in the Job_Log row
(`breach`) either way.

**Post-contract asks.** A contract with status CLOSED/ENDED and an end date
produces one reminder 48 hours after it ends: review, testimonial, maintenance
retainer. An ask already made drops out of the list; a contract with all three
done produces no reminder at all. Lorenzo writes the message himself.

A reminder **expires after `POST_CONTRACT_WINDOW_DAYS` (21 days)**. Past that it
collapses into a single line, `N older contracts past the 21-day window still
have no ask on record: ...`, so a growing pile of finished clients cannot turn
the section into noise. An ask that stale is not going to be made anyway.

**Manual checks.** The ClosePoint USA invitation and the RoutVox Consulting call
request are not visible through the rooms or offers endpoints, so they are
carried as config and **always** printed, including when the snapshot is missing
entirely. Their age comes from a hand-typed date, read as **Central time** like
every other clock in the job, and they are deliberately excluded from
`counts.breach` and from the push priority: a check nobody can measure is not a
measured SLA breach, and counting it pinned every push to "high" forever.

### Retiring a manual check ("I answered the ClosePoint invitation")

Three ways, in order of preference. None of them needs a code change.

1. **`config/ids.json` -> `upwork.manual_checks`** (the durable one). Copy the
   list out of `MANUAL_CHECKS` in the job, then mark the answered entry:
   ```json
   "manual_checks": [
     {"label": "ClosePoint USA invitation (GHL expert)", "since": "2026-09-16",
      "where": "Upwork Messages > Invitations tab",
      "why": "client invitation, not visible through the API",
      "done": true},
     {"label": "RoutVox Consulting call request", "since": "2026-08-27",
      "where": "Upwork Messages > Invitations tab",
      "why": "call request, not visible through the API"}
   ]
   ```
   `"done": true` retires one; `"until": "2026-10-01"` retires it on that date;
   `"manual_checks": []` clears them all. When the key exists it wins over the
   built-in pair, and it takes effect on the next run against the snapshot
   already on disk: the ingest no longer copies the config list into the
   snapshot (that frozen copy is what made `"done": true` do nothing until the
   next pull, re-review OPS-8). A snapshot written by the old ingest still has
   the copy; it is ignored in favour of `ids.json`.
2. **In the raw bundle**, per pull: `"manual_checks": [...]`, and `[]` means
   "none left" rather than "use the built-ins". That distinction is the fix for
   the old behaviour, where an empty list silently re-injected the pair and
   `No Upwork rooms waiting on you.` was unreachable. An entry marked done in
   `ids.json` stays retired even when a bundle lists it again: the config is
   the durable switch.
3. Editing `MANUAL_CHECKS` in `jobs/upwork_rooms.py` still works, and is now the
   last resort rather than the only one.

### Already-asked is explicit, never inferred

`ids.json` records in prose that the Treasure Labs review and testimonial were
already asked in Lorenzo's close-out message. The job **prints that note above
the ask and does not suppress it**. Reading "already asked" out of free text and
getting it wrong drops the review ask and costs a Top Rated step (Lorenzo is at
$754 of the $1,000 threshold); a redundant reminder costs one glance. The row
reads `note: ...` then `confirm the note, then ask for ...`, and the section ends
with the way to retire it, so the contradiction resolves once instead of twice a
day forever.

To suppress an ask for good, say so explicitly, either in the raw bundle:

```json
"contract_asks": {"44501032": {"asks_done": ["review", "testimonial"]}}
```

or in `config/ids.json` under the **stable** key `upwork.contract_asks`:

```json
"contract_asks": {"44501032": {"asks_done": ["review", "testimonial"],
                               "note": "asked in the close-out message"}}
```

Any `upwork.rooms_awaiting_you*` key is still read for notes and `asks_done`, and
the match is on the prefix, so re-dating that key (it is named after its pull
date) no longer drops every note and un-suppresses every recorded ask.

---

## What the push carries

`--now` sends one notification through `shared.notify`: an ntfy card and, when
Gmail SMTP is configured, an email to `NOTIFICATION_EMAIL`. **The email always
carries the full digest** (`email_message`), whatever the topic: that is the one
place a scheduled run gets the room list to Lorenzo. It used to be sent without
`email_message`, so on the default public topic the email got the counts-only
card too and the list never arrived (re-review OPS-1).

ntfy topics are readable by anyone who knows the name, and
`shared.notify.redact()` only strips email addresses and URLs, which this digest
has none of. So on an unprotected topic the card is **counts only**:

```
Upwork: 5 waiting, 2 post-contract asks
5 waiting, 2 post-contract asks.
Names and messages are withheld: this ntfy topic is public. The full list went by email; run python3 jobs/upwork_rooms.py --dry-run to see it here, or set NTFY_TOKEN.
```

A partial or truncated pull adds its coverage lines to the card (they name no
client), for example `rooms were not in this pull, the rooms below are from the
pull of ... and may have moved on.`

Set `NTFY_TOKEN` (the topic is then authenticated, `notify.topic_is_protected()`
returns true) and the card carries the full digest. Until then, client names and
verbatim private Upwork messages stay off a guessable public topic.

**Priority** is `high` only when a *room* is over the 4 h alert line, or when a
post-contract ask came due in the last 24 h. Manual checks never raise it: they
can never clear themselves, so counting them made every scheduled push high
priority forever, which is how a twice-daily digest stops being read.

**The title says when the data is old**: `Upwork: 5 waiting, 2 post-contract asks
(snapshot 9 days old)`. On a lock screen the title is often all that is read.

**`notified` in the Job_Log is not a boolean.** In shadow mode `notify()` returns
normally having sent nothing, so the row records `"notified": "shadow"` (or
`"test"` under `NOTIFY=off`, `true`/`false` when a push really went out). A row
saying `true` while the phone stayed silent is worse than no row.

---

## When the data is stale or missing

The job never fails on a missing or old snapshot. It degrades:

| Snapshot | First line of the digest | Job_Log status | What is still reported |
|---|---|---|---|
| fresh (under 12 h) | the waiting list | `ok` | everything |
| stale (over 12 h) | `no fresh Upwork data, last seen 2026-09-22T00:45:00-05:00` + `rooms below are from that snapshot and may have moved on` | `stale` | the stale rooms, marked, plus manual checks and reminders |
| missing / corrupt | `no fresh Upwork data, last seen never` + how to refresh it | `no_data` | the manual checks only |
| rooms pulled, contracts not | `contracts were not in this pull, post-contract asks are not checked` (or, when an earlier snapshot had them, `the contracts below are from the pull of ...`) | `partial` | the rooms and manual checks, plus any carried contracts |
| contracts pulled, rooms not | `rooms were not in this pull, the waiting list below is invitations only` (or, when an earlier snapshot had them, `the rooms below are from the pull of ...`) | `partial` | the reminders and manual checks, plus any carried rooms. `No Upwork rooms waiting on you.` is never printed when the rooms were not read |
| truncated pull (`hasMore` on the last page) | `the pull was truncated (rooms), older rooms or contracts are not listed` | `partial` | what the pages carried |

12 hours is the threshold because the two runs are 6 h and 18 h apart: anything
older than 12 h missed at least one scheduled refresh. A snapshot with no
`generated_at` stamp falls back to the file mtime, so "last seen" is a real
timestamp rather than "never". A corrupt file is reported, not silently read as
an empty one.

Stale data is still shown on purpose. A five-day-old unanswered invitation is
actionable whether or not this morning's pull ran.

---

## Room text is untrusted

Room names and message snippets are written by clients. The MCP wraps them in
`<untrusted_participant_content>` tags. `clean_text()` strips that wrapper,
breaks any other tag-shaped run by putting a space after its `<`, removes control
characters and collapses newlines into spaces. That last part is the security
property: a client cannot write a message containing a newline plus
`6. URGENT: ...` and have it render as a row of Lorenzo's digest.
`test_client_text_cannot_forge_a_line_in_the_digest` pins it.

It does **not** delete the span between a `<` and a `>`. That rewrote ordinary
client text: `budget is < 5k and > 2k` came out as `budget is 2k`, which inverts
what the client wrote, and `<mark@firth.com>` lost the address entirely. Both
legs of the notification are plain text, so a broken tag is inert either way.

The copy rules (no em dashes, no exclamation marks) bind the job's own words.
Client text is echoed verbatim after `last:` and is exempt;
`test_client_punctuation_passes_through_untouched` documents that, and the
copy-rule test excludes those lines rather than claiming a property the code
cannot hold.

Everything that comes out of a room is data. Nothing in this job acts on it, and
nothing in this job can act on Upwork at all.

---

## Scheduling it

Turned off on 2026-09-22: Lorenzo checks the rooms by hand
(`python3 -m jobs.upwork_rooms --now`). The two laptop runs (`upwork_rooms_am`
09:00 and `upwork_rooms_pm` 15:00 CT, weekdays) are no longer scheduled
anywhere; `config/turned_off_jobs.json` lists them, and the 07:30 sweep, the
daily metrics row and the retro show them as "turned off". Nothing scheduled
shows the rooms now: the sweep on Modal cannot read `.tmp/upwork_rooms.json`.
To schedule them again, put them back in `modal_app.SCHEDULES` (runtime
laptop), delete them from `config/turned_off_jobs.json` and regenerate with
`changesets/schedules/build_schedules.py`. Three things to decide first:

1. The snapshot refresh is a Claude session, not a cron job. Either Lorenzo runs
   `--print-collect` in a session before each check, or the job runs on stale
   data and says so. The degradation path is built for the second case.
2. Set `NTFY_TOKEN` before the first `--now`, or accept counts-only cards.
3. Nothing here deploys to Modal tonight. Per the controlled-environment rule,
   registration happens after Lorenzo approves the push.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `no fresh Upwork data, last seen never` | nobody ran `--ingest` | run `--print-collect` in a session, then `--ingest` |
| `refusing to write the snapshot: ...`, exit 2 | the pull failed or is unrecognisable; the old snapshot was kept on purpose | re-run the MCP calls and save what they actually returned |
| Every room reads "0.0 h waiting" | a timestamp parsed as seconds instead of milliseconds | `parse_ts` handles the numeric-string form Upwork sends; check the raw bundle actually carries `lastActivity` or `latestStory.createdDateTime` |
| `contracts were not in this pull` | the bundle carried only the rooms response | add `contracts_response`, or accept that the asks are unchecked this run |
| `the pull was truncated` | `hasMore` was true on a page | page with `cursor`/`offset` (see the collect table) |
| An invitation Lorenzo answered keeps appearing | manual checks cannot be confirmed from the API | mark it `"done": true` in `config/ids.json -> upwork.manual_checks` |
| A room Lorenzo already answered keeps appearing | the snapshot predates his reply | refresh it, or ignore until the next `--ingest` |
| O3's Upwork section is empty but this job lists rooms | the snapshot keys drifted | `test_ingest_writes_a_snapshot_pipeline_sweep_can_read` should have caught it, run `python3 -m pytest jobs/tests -q` |
| A reminder repeats after Lorenzo sent the ask | asks are only suppressed explicitly | add `asks_done` (see above) |
| A finished client stopped being reminded about | it aged past the 21-day window | it is in the `N older contracts` line at the bottom |
| The Job_Log says `notified: shadow` and no push arrived | `MODE=shadow`, which is correct until Lorenzo approves the push | `MODE=live ALLOW_LIVE_WRITES=1`, after sign-off |

## Cost

Zero. No paid API, no model call, no third-party credit. The MCP reads are part
of Lorenzo's own Upwork connector; a refresh is three read-only calls (more when
paging, still free).
