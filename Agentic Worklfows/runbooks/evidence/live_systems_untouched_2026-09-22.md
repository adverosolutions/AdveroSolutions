# Independent verification: nothing reached Instantly or GHL

> **Scope note added in the 2026-09-22 re-review:** this check covers Instantly and GHL only. It does not cover notifications: two evidence runs set live mode with notifications on at 00:18 and 00:22 CDT and may have emailed Lorenzo and pushed to the ntfy topic. See `../REREVIEW_2026-09-22.md`, "What went wrong that you did not know", item 2.

Run by the main session (not by a build agent) on 2026-09-22, against the live
APIs, after the Phase 1 critic flagged 48 `mode=live` rows in the Job_Log.

## Why this check exists

`.tmp/quarantine/job_log_polluted_2026-09-22.csv` contains 48 `mode=live` rows
written between 04:00:36Z and 05:23:10Z, including **8 `live_write_ok`** rows
naming real production ids. `live_write_ok` is written by the client *after* the
transport returns success, so on its face it reads like eight successful writes
to production. The quarantine README asserts the transport was mocked. That is a
build agent's claim about its own work, so it was checked against live rather
than taken at face value.

## What the rows claimed

| Claim | Object | Asserted value |
|---|---|---|
| `instantly.update_interest_status` x2 | lead `sopiosvanishvili@taxfoaccounting.com` | `interest_value: 2` (meeting booked) |
| `ghl.update_opportunity_stage` x2 | opportunity `hStqQMLQ5eSRVnqxnSMq` | stage `f12615dc...` (call_booked) |
| `ghl.create_appointment` x4 | calendar `GDugwLmZNdsD13RBDnRu` | 2026-09-24 15:00, 09-29 13:00, 09-30 14:00 CT |
| `instantly.reply_to_email` x2 | thread to `tiffany@flowerhillfs.com` | already logged `live_write_failed` |

## What live actually says

**1. Instantly lead — NOT changed.**
`list_leads contacts=[sopiosvanishvili@taxfoaccounting.com]`
- `lt_interest_status: 1` (interested), not `2`
- `timestamp_last_interest_change: 2026-09-21T19:01:33.148Z`
- `timestamp_updated: 2026-09-21T23:17:19.453Z`

Both timestamps precede the 04:00-05:23Z window, and the value is the one
Lorenzo set by hand. The claimed write did not land.

**2. GHL opportunity — NOT moved.**
`get-opportunity id=hStqQMLQ5eSRVnqxnSMq`
- `pipelineStageId: f000f05d-5732-40c1-866a-bd71cd0f95b6` = **new_reply**, not call_booked
- `lastStageChangeAt` / `updatedAt`: `2026-09-21T16:08:06.587Z`

Stage is unchanged and the object has not been written since 16:08Z on 09-21.

**3. GHL calendar — no appointments.**
`get-calendar-events calendarId=GDugwLmZNdsD13RBDnRu` over 2026-09-22 -> 2026-10-05
- `events: []`

None of the four claimed appointments exist.

**4. Instantly reply endpoint — never reached it.**
The two `instantly.reply_to_email` rows are `live_write_failed` carrying
`HTTP 500: {"error":"instantly down"}`. That payload is a test double; the string
appears nowhere in the codebase outside the log, and Instantly does not return it.

## Conclusion

Three independent live objects across two vendors show the values and
last-updated times Lorenzo left them with. The `live_write_ok` rows record a mocked
transport returning success, not a production write. **None of the claimed
Instantly or GHL writes landed.** This check does not cover notifications (see the scope note at the top).

## The real finding (unchanged)

The rows should never have been written to the shared Job_Log. `guard_live_writes.sh`
inspects the *command string*, so it cannot see a Python process that sets
`MODE=live` / `ALLOW_LIVE_WRITES=1` on itself. That is DECISIONS C5, and it is a
demonstrated hole, not a hypothetical one. It did not cause harm here only because
the transport happened to be mocked. Close it before the first live rehearsal.

## Re-run this check

    # Instantly
    list_leads contacts=["sopiosvanishvili@taxfoaccounting.com"]   # expect lt_interest_status 1
    # GHL
    get-opportunity id=hStqQMLQ5eSRVnqxnSMq                        # expect stage f000f05d...
    get-calendar-events calendarId=GDugwLmZNdsD13RBDnRu            # expect events: []
    # Local
    python3 -c "import csv,collections;print(collections.Counter(r['mode'] for r in csv.DictReader(open('.tmp/job_log.csv'))))"
