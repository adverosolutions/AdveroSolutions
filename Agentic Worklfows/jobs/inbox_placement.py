"""Level 2 - weekly inbox placement seed test (Blueprint M1 L2, job O5, Monday).

    cd "Agentic Worklfows"
    python3 jobs/inbox_placement.py --dry-run          # read existing tests, score them, plan the next
    python3 jobs/inbox_placement.py --now              # same + the change-set + the sidecar + the push
    python3 jobs/inbox_placement.py --dry-run --score-only

What it does
  1. GET /inbox-placement-tests                   - what tests already exist
  2. POST /inbox-placement-analytics/stats-by-test-id - inbox / spam / missing per ESP for each test
  3. Under PLACEMENT_INBOX_MIN_PCT on Google or Microsoft seeds -> propose pausing that
     inbox and re-testing in PLACEMENT_RETEST_HOURS
  4. When the newest test is older than PLACEMENT_TEST_MAX_AGE_DAYS, build the payload
     for a new one and record it as a would_do

**Creating a placement test is a live write and it costs credits.** It goes
through ``settings.guard_write``, so in MODE=shadow it is recorded in
``.tmp/shadow_log.jsonl`` and nothing is sent. There is no ``--apply`` here at
all: the create is staged into ``changesets/inbox_actions/<date>.json`` like
every other proposed action, and ``apply_inbox_actions.py`` is the only thing
that can execute it.

The workspace had **zero** placement tests on 2026-09-22, so the stats-by-test-id
response shape below has not been seen live. Every field access is defensive and
the parser reports ``unparsed`` rather than inventing a percentage: a monitor
that guesses 100% inbox placement from a shape it did not recognise is worse
than one that says it does not know.
"""
import argparse
import json
import logging
import sys
from collections import OrderedDict as OrderedDictType
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from shared import job_log  # noqa: E402
from shared import settings  # noqa: E402
from shared import thresholds as TH  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.settings import TZ  # noqa: E402

from jobs.deliverability_monitor import (  # noqa: E402
    CHANGESET_DIR,
    ROLE_INSURANCE,
    _pause_actions,
    _parse_ts,
    _read_post,
    _read_sidecar,
    build_inbox_index,
    load_accounts,
    load_campaign_email_lists,
    write_changeset,
    write_sidecar,
)

logger = logging.getLogger("jobs.inbox_placement")

JOB = "inbox_placement"
SIDECAR = "last_placement.json"

# The seed email the test is sent as. Prospect-readable copy rules apply
# (config/offers.md: no em dashes, no exclamation marks, never mention AI or
# automation, sign "Lorenzo") because a seed mailbox is a real mailbox and the
# subject line is what the spam filter scores. This is deliberately an ordinary
# short note in the same voice as the campaigns, not a test harness string:
# testing placement with copy that does not look like the real copy tests
# nothing useful.
TEST_SUBJECT = "quick question"
TEST_BODY = (
    "Hi there,\n\n"
    "I help commercial service companies get more out of the client lists they already have.\n"
    "Worth a short conversation?\n\n"
    "Lorenzo\n"
)


# =========================================================================
# Reading tests and their stats
# =========================================================================

def list_tests(client: Any, limit: int = 100) -> List[Dict[str, Any]]:
    """GET /inbox-placement-tests (read-only). Empty on this workspace today."""
    data = client._get("inbox-placement-tests", {"limit": limit})
    if isinstance(data, dict):
        return list(data.get("items") or [])
    return list(data or [])


def stats_by_test(client: Any, test_ids: Sequence[str]) -> Any:
    """POST /inbox-placement-analytics/stats-by-test-id (a POST that only reads).

    Issued through ``_read_post`` so a transient 429 or 503 is retried: the
    client's ``READ_POST_PATHS`` list does not carry this path, so without the
    explicit ``retry=True`` a read was treated as a write and never retried.
    """
    if not test_ids:
        return None
    return _read_post(client, "inbox-placement-analytics/stats-by-test-id",
                      {"test_ids": list(test_ids)})


def _esp_name(code: Any) -> str:
    for name, value in TH.PLACEMENT_ESP_CODES.items():
        if value == code or str(value) == str(code):
            return name
    return "esp_%s" % code


def _num(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_stats(payload: Any) -> List[Dict[str, Any]]:
    """Flatten the stats answer into {test_id, esp, sender_email, inbox, spam,
    other, total, inbox_pct}.

    The response shape is unverified against live data (no test has ever run in
    this workspace), so the parser accepts the plausible variants and marks
    anything it cannot read. It never fabricates a percentage.
    """
    rows = []  # type: List[Dict[str, Any]]
    if payload is None:
        return rows
    buckets = payload
    if isinstance(payload, dict):
        for key in ("items", "data", "stats", "results"):
            if isinstance(payload.get(key), list):
                buckets = payload[key]
                break
        else:
            buckets = [payload]
    if not isinstance(buckets, list):
        return rows
    for entry in buckets:
        if not isinstance(entry, dict):
            continue
        inbox = _num(entry.get("inbox", entry.get("inbox_count", entry.get("landed_inbox"))))
        spam = _num(entry.get("spam", entry.get("spam_count", entry.get("landed_spam"))))
        other = _num(entry.get("other", entry.get("categories", entry.get("unknown"))))
        total = _num(entry.get("total", entry.get("sent", entry.get("count")))) or (inbox + spam + other)
        row = {
            "test_id": entry.get("test_id") or entry.get("id"),
            "esp": _esp_name(entry.get("recipient_esp", entry.get("esp"))),
            "sender_email": (entry.get("sender_email") or entry.get("email") or "").strip().lower(),
            "inbox": inbox, "spam": spam, "other": other, "total": total,
        }
        if total:
            row["inbox_pct"] = round(TH.rate_pct(inbox, total), 2)
            row["unparsed"] = False
        else:
            row["inbox_pct"] = None
            row["unparsed"] = True
        rows.append(row)
    return rows


def _test_times(tests: Sequence[Dict[str, Any]]) -> Dict[str, datetime]:
    out = {}  # type: Dict[str, datetime]
    for t in tests or []:
        ts = _parse_ts(t.get("timestamp_created") or t.get("created_at") or t.get("date"))
        if t.get("id") and ts is not None:
            out[str(t["id"])] = ts
    return out


def _conclusive(row: Dict[str, Any]) -> bool:
    """A row that can carry a pass or fail verdict: enough seed deliveries and
    a readable inbox rate."""
    return (row.get("inbox_pct") is not None
            and (row.get("total") or 0) >= TH.PLACEMENT_MIN_SEEDS_FOR_VERDICT)


def newest_per_sender_and_esp(rows: List[Dict[str, Any]],
                              tests: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Keep only the newest CONCLUSIVE test's row for each (sender, ESP) pair.

    ``stats-by-test-id`` is asked about every test the workspace has ever run,
    and ``score`` used to judge all of them: an inbox that failed an old test
    and passed its re-test was still proposed for a high-severity pause
    (MKT-7a), which is the opposite of what the M1 L2 re-test is for.

    Only a row that carries a pass or fail verdict (at least
    ``PLACEMENT_MIN_SEEDS_FOR_VERDICT`` seed deliveries) may replace an older
    one. A newer re-test still short of that is reported as in progress
    (``in_progress``) and the older verdict stands: a re-test with two seed
    deliveries, both in the inbox, used to wipe out a 30% failure (MKT-7a
    re-review). When a pair has no conclusive row at all, its newest row is
    kept so ``score`` can call it insufficient. Rows whose test has no readable
    timestamp rank oldest; on a tie the WORSE row is kept, because guessing that
    a failure was superseded is the unsafe direction.
    """
    times = _test_times(tests or [])
    oldest = datetime.min.replace(tzinfo=timezone.utc)

    def rank(row):
        return (row["test_time"] or oldest, -(row.get("inbox_pct") or 0.0))

    by_key = {}  # type: Dict[Any, List[Dict[str, Any]]]
    for row in rows:
        if row.get("unparsed") or not row.get("sender_email"):
            continue
        row = dict(row)
        row["test_time"] = times.get(str(row.get("test_id")))
        by_key.setdefault((row["sender_email"], row["esp"]), []).append(row)

    kept = []  # type: List[Dict[str, Any]]
    superseded = []  # type: List[Dict[str, Any]]
    in_progress = []  # type: List[Dict[str, Any]]
    for key, group in by_key.items():
        conclusive = sorted([r for r in group if _conclusive(r)], key=rank)
        pending = sorted([r for r in group if not _conclusive(r)], key=rank)
        if not conclusive:
            kept.append(pending[-1])
            superseded.extend(pending[:-1])
            continue
        best = conclusive[-1]
        kept.append(best)
        superseded.extend(conclusive[:-1])
        for row in pending:
            if rank(row) > rank(best):
                row["in_progress_over"] = best.get("test_id")
                in_progress.append(row)
            else:
                superseded.append(row)
    for row in kept + superseded + in_progress:
        if row.get("test_time") is not None:
            row["test_time"] = row["test_time"].isoformat()
    return {"kept": kept, "superseded": superseded, "in_progress": in_progress}


def score(rows: List[Dict[str, Any]], inbox_index: Optional[Dict[str, Dict[str, Any]]] = None,
          tests: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Verdict per sender inbox on the gating ESPs (Google, Microsoft only),
    judged on each sender's NEWEST test per ESP only.

    A row with no ``sender_email`` is refused (``unattributed``), never scored:
    it used to become a ``pause_inbox:`` proposal with an empty target.
    """
    inbox_index = inbox_index or {}
    failing = []
    passing = []
    insufficient = []
    unparsed = [r for r in rows if r.get("unparsed")]
    unattributed = [r for r in rows if not r.get("unparsed") and not r.get("sender_email")]
    newest = newest_per_sender_and_esp(rows, tests)
    pending_by_key = {}  # type: Dict[Any, Dict[str, Any]]
    for row in newest["in_progress"]:
        pending_by_key[(row["sender_email"], row["esp"])] = row
    for row in newest["kept"]:
        if row["esp"] not in TH.PLACEMENT_ESP_GATING:
            continue
        entry = dict(row)
        meta = inbox_index.get(row["sender_email"]) or {}
        entry["in_campaigns"] = meta.get("in_campaigns") or []
        entry["email"] = row["sender_email"]
        if row["total"] < TH.PLACEMENT_MIN_SEEDS_FOR_VERDICT:
            entry["verdict"] = "insufficient"
            entry["reason"] = ("only %d seed deliveries (need %d) on %s"
                               % (row["total"], TH.PLACEMENT_MIN_SEEDS_FOR_VERDICT, row["esp"]))
            insufficient.append(entry)
        elif row["inbox_pct"] is not None and row["inbox_pct"] < TH.PLACEMENT_INBOX_MIN_PCT:
            entry["verdict"] = "fail"
            entry["reason"] = ("%.1f%% inbox on %s seeds is below %.0f%%"
                               % (row["inbox_pct"], row["esp"], TH.PLACEMENT_INBOX_MIN_PCT))
            entry["response_pct"] = row["inbox_pct"]
            retest = pending_by_key.get((row["sender_email"], row["esp"]))
            if retest is not None:
                entry["retest_in_progress"] = retest.get("test_id")
                entry["reason"] += ("; re-test %s is in progress (%d of %d seed deliveries) and does "
                                    "not replace this verdict until it can pass or fail"
                                    % (retest.get("test_id"), retest.get("total") or 0,
                                       TH.PLACEMENT_MIN_SEEDS_FOR_VERDICT))
            failing.append(entry)
        else:
            entry["verdict"] = "pass"
            passing.append(entry)
    return {"failing": failing, "passing": passing, "insufficient": insufficient,
            "unparsed": unparsed, "unattributed": unattributed,
            "superseded": newest["superseded"], "in_progress": newest["in_progress"], "rows": rows}


def newest_test_age_days(tests: List[Dict[str, Any]], now: datetime) -> Optional[float]:
    stamps = []
    for t in tests:
        ts = _parse_ts(t.get("timestamp_created") or t.get("created_at") or t.get("date"))
        if ts is not None:
            stamps.append(ts)
    if not stamps:
        return None
    return (now - max(stamps)).total_seconds() / 86400.0


def build_test_payload(emails: Sequence[str], seeds: Sequence[str], now: datetime,
                       automated: bool = False) -> Dict[str, Any]:
    """POST /inbox-placement-tests body.

    ``emails`` on this endpoint is the SEED list (where the test mail lands),
    not the sending inboxes: the sending accounts come from the workspace when
    ``sending_method`` is 0. The sending inboxes are carried in ``_meta`` so the
    change-set records which inboxes this test is meant to cover.
    """
    return {
        "name": "Weekly placement %s" % now.astimezone(TZ).date().isoformat(),
        "type": TH.PLACEMENT_TEST_TYPE_AUTOMATED if automated else TH.PLACEMENT_TEST_TYPE_ONE_TIME,
        "sending_method": TH.PLACEMENT_SENDING_METHOD_INSTANTLY,
        "email_subject": TEST_SUBJECT,
        "email_body": TEST_BODY,
        "emails": list(seeds),
        "_meta": {"sending_inboxes": list(emails), "generated_by": JOB,
                  "note": ("seed addresses must come from Instantly's own seed list "
                           "(GET /inbox-placement-tests ESP options); none are configured yet")},
    }


# =========================================================================
# The run
# =========================================================================

def run_placement(now: datetime, client: Any = None, dry_run: bool = True,
                  notify_fn: Callable = notify, log_fn: Callable = log_run,
                  changeset_dir: Path = CHANGESET_DIR, seeds: Optional[Sequence[str]] = None,
                  write: Optional[bool] = None, send_card: Optional[bool] = None,
                  score_only: bool = False,
                  campaigns: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if client is None:
        from shared.instantly import default_client
        client = default_client()
    notes = []  # type: List[str]

    accounts = load_accounts(client)
    campaign_lists = load_campaign_email_lists(client, campaigns)
    inboxes = build_inbox_index(accounts, campaign_lists, now)
    index = {i["email"]: i for i in inboxes}
    sending = [i["email"] for i in inboxes if i["role"] != ROLE_INSURANCE]

    tests = list_tests(client)
    test_ids = [t.get("id") for t in tests if t.get("id")]
    stats_raw = None
    stats_error = None
    if test_ids:
        try:
            stats_raw = stats_by_test(client, test_ids)
        except Exception as exc:  # noqa: BLE001 - an unreachable stats endpoint is a note, not a crash
            stats_error = str(exc)[:160]
            notes.append("stats-by-test-id failed (%s); no placement verdict this run" % stats_error)
    rows = parse_stats(stats_raw)
    result = score(rows, index, tests)
    if result["unparsed"]:
        notes.append("%d stats row(s) could not be parsed into inbox/total; they were NOT scored"
                     % len(result["unparsed"]))
    if result["unattributed"]:
        notes.append("%d stats row(s) carry no sender_email; they were refused rather than turned into "
                     "a pause with an empty target" % len(result["unattributed"]))
    info = []  # type: List[str]
    if result.get("in_progress"):
        info.append("%d re-test row(s) are still short of %d seed deliveries; the earlier verdict for "
                    "those inboxes stands until they finish"
                    % (len(result["in_progress"]), TH.PLACEMENT_MIN_SEEDS_FOR_VERDICT))
    if result["superseded"]:
        # Normal once a re-test has run; context, not a problem with this run.
        info.append("%d older test row(s) were superseded by a newer test of the same sender and ESP "
                    "and were not scored" % len(result["superseded"]))
    # Tests exist but not one row could be scored: the stats read failed (or
    # answered a shape nobody can read). That is NOT "every inbox passed".
    # The previous verdict is kept, and the sidecar says so, so the 07:00
    # monitor neither drops a failure from earlier that day nor counts level 2
    # as evaluated (MKT-7c).
    scored_rows = [r for r in rows if not r.get("unparsed") and r.get("sender_email")]
    stats_failed = bool(test_ids) and (stats_error is not None or not scored_rows)
    if stats_failed and stats_error is None:
        notes.append("stats-by-test-id answered but no row could be scored; treated as a failed read")

    age = newest_test_age_days(tests, now)
    due = age is None or age > TH.PLACEMENT_TEST_MAX_AGE_DAYS
    payload = None
    guard = None
    if due and not score_only:
        seed_list = list(seeds or [])
        payload = build_test_payload(sending, seed_list, now)
        if not seed_list:
            notes.append("no seed addresses configured: the create payload is staged with an empty "
                         "`emails` list and CANNOT be applied until Instantly's seed list is pulled "
                         "into the change-set (runbooks/deliverability.md, level 2)")
        # A placement test is a live write and it spends credits, and **this job
        # never makes it**: there is no POST anywhere here. The create is staged
        # into the change-set and apply_inbox_actions.py is the only thing that
        # can execute it (where it is a manual op today).
        #
        # It used to call settings.guard_write and throw the result away. In
        # MODE=live that writes a `live_write_intent` Job_Log row BEFORE the
        # call it is supposed to precede, so during an incident reconciliation
        # the log claimed a credit-spending Instantly call may have been
        # accepted upstream when nothing was ever sent. The staged payload is
        # recorded as an ordinary shadow note instead, which is what it is.
        body = dict(payload)
        body.pop("_meta", None)
        guard = job_log.shadow("instantly", "inbox_placement_create_staged", {
            "payload": body,
            "_note": ("staged only: this job never calls POST /inbox-placement-tests. Apply it "
                      "through changesets/inbox_actions/apply_inbox_actions.py."),
        })

    proposals = []
    retest_after = (now + timedelta(hours=TH.PLACEMENT_RETEST_HOURS)).astimezone(TZ).isoformat()
    by_email = OrderedDictType()
    for row in result["failing"]:
        by_email.setdefault(row["email"], []).append(row)
    for email, rows_for in by_email.items():
        meta = index.get(email) or {}
        proposals.append({
            "id": "pause_inbox:%s" % email, "kind": "pause_inbox", "target": email,
            "severity": "high", "level": 2, "reason": "; ".join(r["reason"] for r in rows_for),
            "retest_after_hours": TH.PLACEMENT_RETEST_HOURS,
            "retest_after": retest_after,
            "in_campaigns": meta.get("in_campaigns") or [],
            # The COMPLETE pause action list. A bare pause_account from this job
            # used to replace the monitor's version of the same proposal id in
            # the shared change-set file, and applying the merged row paused the
            # inbox while leaving it in every campaign's email_list.
            "actions": _pause_actions(email, meta, campaign_lists, None),
            "evidence": rows_for[0] if len(rows_for) == 1 else rows_for,
        })
    retest = None
    if by_email and not score_only:
        # M1 L2: "pause the failing inboxes; re-test after 48 h". The weekly
        # cadence alone only made a new test due after 7 days, while the
        # monitor stops re-proposing the pause after 48 h, so the failure left
        # the card with no re-test ever staged (MKT-7b). The re-test is staged
        # NOW, in the same change-set as the pause, and may not be applied
        # before retest_after.
        seed_list = list(seeds or [])
        retest_payload = build_test_payload(sending, seed_list, now)
        retest_payload["name"] = "Placement re-test %s" % now.astimezone(TZ).date().isoformat()
        retest = {
            "id": "retest_placement:%s" % now.astimezone(TZ).date().isoformat(),
            "kind": "create_placement_test", "target": retest_payload["name"],
            "severity": "medium", "level": 2,
            "reason": ("re-test %d inbox(es) that failed placement, %d h after the pause (M1 L2): %s"
                       % (len(by_email), TH.PLACEMENT_RETEST_HOURS, ", ".join(by_email))),
            "not_before": retest_after,
            "retest_for": list(by_email),
            "actions": [{"system": "instantly", "op": "create_placement_test",
                         "payload": {k: v for k, v in retest_payload.items() if k != "_meta"}}],
            "evidence": {"failing": list(by_email), "costs_credits": True},
            "blocked": not retest_payload["emails"],
        }
        proposals.append(retest)
    if payload is not None:
        proposals.append({
            "id": "create_placement_test:%s" % now.astimezone(TZ).date().isoformat(),
            "kind": "create_placement_test", "target": payload["name"],
            "severity": "low", "level": 2,
            "reason": ("no placement test in the last %d days (newest: %s); M1 L2 runs one every Monday"
                       % (TH.PLACEMENT_TEST_MAX_AGE_DAYS, "none ever" if age is None else "%.1f days ago" % age)),
            "actions": [{"system": "instantly", "op": "create_placement_test",
                         "payload": {k: v for k, v in payload.items() if k != "_meta"}}],
            "evidence": {"existing_tests": len(tests), "newest_age_days": age,
                         "sending_inboxes": sending, "costs_credits": True},
            "blocked": not payload["emails"],
        })

    summary = "%d failing, %d passing, %d insufficient, %d existing test(s)%s" % (
        len(result["failing"]), len(result["passing"]), len(result["insufficient"]), len(tests),
        "; a new test is due" if due else "")
    if stats_failed:
        summary = "stats read FAILED, no new verdict; %d existing test(s)%s" % (
            len(tests), "; a new test is due" if due else "")
    sidecar = {"job": JOB, "as_of": now.isoformat(), "summary": summary,
               "failing": result["failing"], "passing": result["passing"],
               "insufficient": result["insufficient"], "tests": len(tests),
               "newest_age_days": age, "notes": notes,
               "retest": ({"not_before": retest["not_before"], "inboxes": retest["retest_for"],
                           "proposal_id": retest["id"], "blocked": retest["blocked"]}
                          if retest else None)}
    if stats_failed:
        # Keep the previous verdict, with ITS as_of, so the monitor ages it
        # exactly as before; record this failed attempt beside it. With no
        # previous verdict the sidecar has no as_of, which the monitor already
        # treats as "not today's evidence".
        previous = _read_sidecar(changeset_dir, SIDECAR) or {}
        sidecar = dict(previous) if previous else {"job": JOB, "as_of": None, "failing": [],
                                                   "passing": [], "insufficient": [],
                                                   "summary": "no placement verdict recorded"}
        sidecar["stats_failed"] = True
        sidecar["last_attempt"] = {"as_of": now.isoformat(), "error": stats_error or "no scorable row",
                                   "kept_previous_verdict": bool(previous)}
        sidecar["notes"] = list(previous.get("notes") or []) + notes if previous else notes

    report = {"job": JOB, "as_of": now.isoformat(), "mode": settings.get_mode(), "dry_run": bool(dry_run),
              "tests": tests, "stats_rows": rows, "result": result, "due": due,
              "newest_age_days": age, "payload": payload, "guard": guard,
              "proposals": proposals, "notes": notes, "info": info, "summary": summary,
              "sending_inboxes": sending}
    report["card"] = render_card(report, now)

    if write is None:
        write = not dry_run
    report["changeset_path"] = None
    report["sidecar_path"] = None
    if write:
        if proposals:
            path = write_changeset(
                {"_about": "Level 2 placement proposals (M1 L2 / O5). Nothing applied.",
                 "generated_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
                 "generated_by": JOB, "mode": settings.get_mode(), "levels_run": [2],
                 # A failed stats read evaluated nothing: saying [2] here would
                 # let this write withdraw a level 2 pause proposed earlier today.
                 "levels_evaluated": [] if stats_failed else [2],
                 "proposals": proposals}, now, changeset_dir)
            report["changeset_path"] = str(path) if path else None
        sc = write_sidecar(changeset_dir, SIDECAR, sidecar)
        report["sidecar_path"] = str(sc) if sc else None

    status = "dry_run" if dry_run else "ok"
    if stats_failed:
        status = status + "_partial"
    elif result["failing"]:
        status = status + "_failing"
    elif notes:
        status = status + "_partial"
    report["status"] = status
    report["stats_failed"] = stats_failed
    log_fn(JOB, status, {"as_of": now.isoformat(), "tests": len(tests), "failing": len(result["failing"]),
                         "due": due, "newest_age_days": age, "notes": notes, "stats_failed": stats_failed,
                         "changeset": report["changeset_path"]})

    if send_card is None:
        send_card = not dry_run
    report["notified"] = None
    if send_card:
        report["notified"] = notify_fn(
            "Inbox placement: %s" % summary, report["card"],
            priority="high" if (result["failing"] or stats_failed) else "default", tags=["envelope"])
    return report


def render_card(report: Dict[str, Any], now: datetime) -> str:
    lines = ["Inbox placement %s" % now.astimezone(TZ).strftime("%a %Y-%m-%d %H:%M CT"),
             "=" * 40, report["summary"], ""]
    res = report["result"]
    if report.get("stats_failed"):
        lines.append("!! The stats read failed: this is NOT a clean result. The previous verdict is kept "
                     "and level 2 is not counted as evaluated today.")
    for row in res["failing"]:
        lines.append("- FAIL %s: %s" % (row["email"], row["reason"]))
    for row in res["insufficient"]:
        lines.append("- ?    %s: %s" % (row["email"], row["reason"]))
    if not res["failing"] and not res["insufficient"] and res["passing"]:
        lines.append("All %d sender/ESP pairs at or above %.0f%% inbox." % (
            len(res["passing"]), TH.PLACEMENT_INBOX_MIN_PCT))
    for p in report.get("proposals") or []:
        if p.get("id", "").startswith("retest_placement:"):
            lines.append("")
            lines.append("Re-test staged for %s, not before %s%s"
                         % (", ".join(p["retest_for"]), p["not_before"],
                            "  BLOCKED: no seeds configured" if p.get("blocked") else ""))
    if report.get("payload"):
        lines.append("")
        lines.append("A new test is due: %s" % report["payload"]["name"])
        lines.append("  %d sending inbox(es), %d seed address(es)%s" % (
            len(report["sending_inboxes"]), len(report["payload"]["emails"]),
            "  BLOCKED: no seeds configured" if not report["payload"]["emails"] else ""))
        lines.append("  This costs Instantly credits and is staged, not sent.")
    for note in report.get("notes") or []:
        lines.append("note: %s" % note)
    for note in report.get("info") or []:
        lines.append("info: %s" % note)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="inbox_placement",
                                description="Weekly inbox placement seed test (M1 L2 / O5)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="read-only: score existing tests, plan the next, print")
    g.add_argument("--now", action="store_true", help="same + change-set, sidecar and the ntfy card")
    p.add_argument("--as-of", help="ISO timestamp used as 'now'")
    p.add_argument("--score-only", action="store_true", help="never plan a new test, only score existing ones")
    p.add_argument("--seed", action="append", default=[], help="seed address for a new test (repeatable)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        from shared.job_log import use_scratch_logs

        use_scratch_logs("inbox_placement_dryrun")

    now = _parse_ts(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if now is None:
        raise SystemExit("--as-of must be an ISO timestamp")
    # A Monday cron that dies must leave a Job_Log row and a push, or a level
    # that has stopped running looks exactly like a level with nothing to say.
    try:
        report = run_placement(now, dry_run=bool(args.dry_run), seeds=args.seed,
                               score_only=args.score_only)
    except Exception as exc:  # noqa: BLE001
        logger.exception("inbox placement failed")
        log_run(JOB, "failed", {"as_of": now.isoformat(), "dry_run": bool(args.dry_run),
                                "error": str(exc)[:400]})
        notify("Inbox placement FAILED",
               "%s\n\nLevel 2 did not run, so no placement result was scored this week.\n"
               "Re-run:\n  python3 jobs/inbox_placement.py --dry-run" % str(exc)[:400],
               priority="high", tags=["rotating_light"])
        return 1
    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        print(report["card"])
    # A partial run (the stats read failed) exits non-zero, like the inventory
    # and the monitor, so a scheduler sees it as not-clean.
    return 1 if report.get("stats_failed") else 0


if __name__ == "__main__":
    sys.exit(main())
