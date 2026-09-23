"""Tests for level 2, the weekly inbox placement seed test (M1 L2 / O5).

Run: cd "Agentic Worklfows" && python3 -m pytest jobs/tests/test_deliverability_placement.py -q

The stats-by-test-id response shape has never been seen on this workspace (zero
placement tests existed on 2026-09-22), so most of these tests are about the
parser refusing to invent a number it cannot read.
"""
import json
from datetime import datetime, timedelta

import pytest

from shared import job_log, thresholds as TH
from shared.settings import TZ
from jobs import inbox_placement as P
from jobs.tests.test_deliverability_monitor import StubClient, account, campaign, ct

NOW = ct("2026-09-22 07:05")


class PlacementClient(StubClient):
    def __init__(self, tests=None, stats=None, **kw):
        StubClient.__init__(self, **kw)
        self._tests = tests or []
        self._stats = stats
        self.posted = []

    def _get(self, path, params=None):
        self.calls.append(("get", path, params))
        if path == "inbox-placement-tests":
            return {"items": list(self._tests)}
        raise KeyError(path)

    def _post(self, path, body=None):
        self.posted.append((path, body))
        if path == "inbox-placement-analytics/stats-by-test-id":
            if isinstance(self._stats, Exception):
                raise self._stats
            return self._stats
        raise KeyError(path)


def world(tests=None, stats=None):
    emails = ["x@a.com", "y@a.com", "z@b.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    return PlacementClient(tests=tests, stats=stats,
                           accounts=[account(e) for e in emails], campaigns=camps), emails, camps


# ------------------------------------------------------------------ the parser

def test_parse_stats_reads_the_documented_shape():
    payload = {"items": [
        {"test_id": "t1", "recipient_esp": 1, "sender_email": "X@A.com", "inbox": 9, "spam": 1, "total": 10},
        {"test_id": "t1", "recipient_esp": 2, "sender_email": "x@a.com", "inbox": 5, "spam": 5, "total": 10},
    ]}
    rows = P.parse_stats(payload)
    assert [r["esp"] for r in rows] == ["google", "microsoft"]
    assert rows[0]["inbox_pct"] == 90.0 and rows[1]["inbox_pct"] == 50.0
    assert rows[0]["sender_email"] == "x@a.com"


def test_parse_stats_derives_total_when_only_the_buckets_are_present():
    rows = P.parse_stats([{"recipient_esp": 1, "email": "x@a.com", "inbox": 8, "spam": 2}])
    assert rows[0]["total"] == 10 and rows[0]["inbox_pct"] == 80.0


def test_parse_stats_marks_a_row_it_cannot_read_instead_of_calling_it_100_percent():
    """A shape with no countable field must NOT come out as 100% inbox. That is
    the failure that silently tells Lorenzo every inbox is fine."""
    rows = P.parse_stats([{"recipient_esp": 1, "sender_email": "x@a.com", "placement": "good"}])
    assert rows[0]["unparsed"] is True and rows[0]["inbox_pct"] is None
    out = P.score(rows)
    assert out["failing"] == [] and out["passing"] == [] and out["unparsed"] == rows


def test_parse_stats_tolerates_junk():
    assert P.parse_stats(None) == []
    assert P.parse_stats("nope") == []
    assert P.parse_stats([1, 2, None]) == []


# ------------------------------------------------------------------ the verdict

def test_score_fails_below_85_percent_on_google_and_microsoft_only():
    rows = P.parse_stats([
        {"recipient_esp": 1, "sender_email": "x@a.com", "inbox": 8, "spam": 2, "total": 10},   # google 80
        {"recipient_esp": 2, "sender_email": "y@a.com", "inbox": 9, "spam": 1, "total": 10},   # ms 90
        {"recipient_esp": 12, "sender_email": "z@b.com", "inbox": 1, "spam": 9, "total": 10},  # web.de ignored
    ])
    out = P.score(rows)
    assert [r["email"] for r in out["failing"]] == ["x@a.com"]
    assert [r["email"] for r in out["passing"]] == ["y@a.com"]
    assert TH.PLACEMENT_INBOX_MIN_PCT == 85.0


def test_score_abstains_on_too_few_seeds():
    rows = P.parse_stats([{"recipient_esp": 1, "sender_email": "x@a.com", "inbox": 0, "spam": 2, "total": 2}])
    out = P.score(rows)
    assert out["failing"] == []
    assert out["insufficient"][0]["verdict"] == "insufficient"
    assert "only 2 seed deliveries" in out["insufficient"][0]["reason"]


def test_newest_test_age_and_due():
    tests = [{"id": "t1", "timestamp_created": "2026-09-10T00:00:00.000Z"},
             {"id": "t2", "timestamp_created": "2026-09-20T00:00:00.000Z"}]
    age = P.newest_test_age_days(tests, NOW)
    assert 2.4 < age < 2.6   # 2026-09-20 00:00Z to 2026-09-22 07:05 CT (12:05Z)
    assert P.newest_test_age_days([], NOW) is None


# ------------------------------------------------------------------- the payload

def test_the_seed_email_obeys_the_prospect_copy_rules():
    """config/offers.md rules 8 and 9: no em dashes, no exclamation marks, no
    mention of AI or automation, signed Lorenzo. A seed mailbox is a real
    mailbox, and the subject is what the spam filter scores."""
    blob = P.TEST_SUBJECT + "\n" + P.TEST_BODY
    assert "—" not in blob and "--" not in blob
    assert "!" not in blob
    lowered = blob.lower()
    for banned in ("ai ", "automation", "automated", "bot", "test email", "placement test"):
        assert banned not in lowered, banned
    assert blob.rstrip().endswith("Lorenzo")


def test_build_test_payload_carries_the_sending_inboxes_in_meta_not_in_emails():
    payload = P.build_test_payload(["x@a.com"], ["seed@gmail.com"], NOW)
    assert payload["emails"] == ["seed@gmail.com"]
    assert payload["_meta"]["sending_inboxes"] == ["x@a.com"]
    assert payload["type"] == TH.PLACEMENT_TEST_TYPE_ONE_TIME
    assert payload["sending_method"] == TH.PLACEMENT_SENDING_METHOD_INSTANTLY


# ------------------------------------------------------------------------ runs

def test_a_due_test_is_recorded_as_a_shadow_write_and_never_posted(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    client, emails, camps = world(tests=[], stats=None)
    report = P.run_placement(NOW, client=client, dry_run=True, changeset_dir=tmp_path,
                             seeds=["seed@gmail.com"], campaigns=camps,
                             log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert report["due"] is True
    # Nothing was POSTed to the create endpoint.
    assert not [p for p in client.posted if p[0] == "inbox-placement-tests"]
    rows = job_log.read_shadow_log(tmp_path / "shadow.jsonl")
    creates = [r for r in rows if r["action"] == "inbox_placement_create_staged"]
    assert len(creates) == 1
    assert "_meta" not in creates[0]["payload"]["payload"]   # the real request body is recorded
    assert creates[0]["payload"]["payload"]["emails"] == ["seed@gmail.com"]


def test_a_staged_placement_create_never_writes_a_live_write_intent_row(tmp_path, monkeypatch,
                                                                       live_mode):
    """guard_write logs a live_write_intent row BEFORE the call it precedes, so
    that a write dying at the transport can be reconciled afterwards. This job
    makes no such call: the create is executed through the change-set. Calling
    guard_write and discarding the result told an incident reconciliation that a
    credit-spending Instantly call may have been accepted upstream when nothing
    was ever sent."""
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    client, emails, camps = world(tests=[], stats=None)
    P.run_placement(NOW, client=client, dry_run=False, changeset_dir=tmp_path,
                    seeds=["seed@gmail.com"], campaigns=camps, send_card=False,
                    log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    text = (tmp_path / "job_log.csv").read_text() if (tmp_path / "job_log.csv").exists() else ""
    assert "live_write_intent" not in text
    assert "inbox_placement_create," not in text
    assert not [p for p in client.posted if p[0] == "inbox-placement-tests"]


def test_without_seeds_the_create_proposal_is_marked_blocked(tmp_path):
    client, emails, camps = world(tests=[])
    report = P.run_placement(NOW, client=client, dry_run=True, changeset_dir=tmp_path,
                             campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    create = [p for p in report["proposals"] if p["kind"] == "create_placement_test"][0]
    assert create["blocked"] is True
    assert create["evidence"]["costs_credits"] is True
    assert any("seed addresses" in n for n in report["notes"])
    assert "BLOCKED" in report["card"]


def test_score_only_never_plans_a_test(tmp_path):
    client, emails, camps = world(tests=[])
    report = P.run_placement(NOW, client=client, dry_run=True, changeset_dir=tmp_path,
                             score_only=True, campaigns=camps,
                             log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert report["payload"] is None and report["guard"] is None
    assert not [p for p in report["proposals"] if p["kind"] == "create_placement_test"]


def test_a_failing_inbox_becomes_a_pause_proposal_with_a_retest_time(tmp_path):
    stats = {"items": [{"test_id": "t1", "recipient_esp": 1, "sender_email": "x@a.com",
                        "inbox": 5, "spam": 5, "total": 10}]}
    client, emails, camps = world(tests=[{"id": "t1", "timestamp_created": "2026-09-21T00:00:00.000Z"}],
                                  stats=stats)
    report = P.run_placement(NOW, client=client, dry_run=False, changeset_dir=tmp_path,
                             campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    p = [x for x in report["proposals"] if x["kind"] == "pause_inbox"][0]
    assert p["target"] == "x@a.com" and p["level"] == 2 and p["severity"] == "high"
    assert p["retest_after_hours"] == TH.PLACEMENT_RETEST_HOURS
    retest = datetime.fromisoformat(p["retest_after"])
    assert retest - NOW == timedelta(hours=TH.PLACEMENT_RETEST_HOURS)
    assert p["in_campaigns"] == ["c1"]
    # And the sidecar the daily monitor reads.
    sidecar = json.loads((tmp_path / P.SIDECAR).read_text())
    assert sidecar["failing"][0]["email"] == "x@a.com"


def test_an_unreachable_stats_endpoint_is_a_note_not_a_crash(tmp_path):
    client, emails, camps = world(tests=[{"id": "t1", "timestamp_created": "2026-09-21T00:00:00.000Z"}],
                                  stats=RuntimeError("500 boom"))
    report = P.run_placement(NOW, client=client, dry_run=True, changeset_dir=tmp_path,
                             campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert report["result"]["failing"] == []
    assert any("stats-by-test-id failed" in n for n in report["notes"])


def test_dry_run_writes_no_sidecar_and_no_changeset(tmp_path):
    client, emails, camps = world(tests=[])
    P.run_placement(NOW, client=client, dry_run=True, changeset_dir=tmp_path, campaigns=camps,
                    log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------- MKT-7 re-review fixes
def _stats(*rows):
    return {"items": [dict(test_id=t, recipient_esp=esp, sender_email=who, inbox=inbox,
                           spam=10 - inbox, total=10) for (t, esp, who, inbox) in rows]}


def test_only_the_newest_test_per_sender_and_esp_is_scored(tmp_path):
    """MKT-7a. x@a.com failed test t1 and passed its re-test t2. Every test ever
    run used to be scored, so the old failure still proposed a HIGH pause."""
    tests = [{"id": "t1", "timestamp_created": "2026-09-14T00:00:00.000Z"},
             {"id": "t2", "timestamp_created": "2026-09-21T00:00:00.000Z"}]
    stats = _stats(("t1", 1, "x@a.com", 5), ("t2", 1, "x@a.com", 10), ("t2", 2, "x@a.com", 9))
    client, emails, camps = world(tests=tests, stats=stats)
    report = P.run_placement(NOW, client=client, dry_run=True, changeset_dir=tmp_path,
                             campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert report["result"]["failing"] == []
    assert not [p for p in report["proposals"] if p["kind"] == "pause_inbox"]
    assert len(report["result"]["superseded"]) == 1
    assert report["result"]["superseded"][0]["test_id"] == "t1"


def test_a_failure_on_the_newest_test_still_fails():
    tests = [{"id": "t1", "timestamp_created": "2026-09-14T00:00:00.000Z"},
             {"id": "t2", "timestamp_created": "2026-09-21T00:00:00.000Z"}]
    rows = P.parse_stats(_stats(("t1", 1, "x@a.com", 10), ("t2", 1, "x@a.com", 5)))
    out = P.score(rows, tests=tests)
    assert [r["test_id"] for r in out["failing"]] == ["t2"]


def test_a_failure_stages_a_retest_48_hours_out(tmp_path):
    """MKT-7b. M1 L2 says re-test after 48 h. A new test was only due after 7
    days, and the monitor stops re-proposing the pause after 48 h, so the
    failure left the card with no re-test ever staged."""
    tests = [{"id": "t1", "timestamp_created": "2026-09-21T00:00:00.000Z"}]
    client, emails, camps = world(tests=tests, stats=_stats(("t1", 1, "x@a.com", 5)))
    report = P.run_placement(NOW, client=client, dry_run=False, changeset_dir=tmp_path,
                             campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    retest = [p for p in report["proposals"] if p["id"].startswith("retest_placement:")]
    assert len(retest) == 1
    assert retest[0]["kind"] == "create_placement_test"
    assert retest[0]["retest_for"] == ["x@a.com"]
    assert datetime.fromisoformat(retest[0]["not_before"]) - NOW == timedelta(hours=TH.PLACEMENT_RETEST_HOURS)
    sidecar = json.loads((tmp_path / P.SIDECAR).read_text())
    assert sidecar["retest"]["inboxes"] == ["x@a.com"]
    # ... and 3 days later the monitor, which drops the aged failure, says the
    # re-test is pending instead of going quiet.
    from jobs import deliverability_monitor as M

    aged = M._age_sidecar(sidecar, NOW + timedelta(days=3), TH.PLACEMENT_RETEST_HOURS / 24.0, "placement")
    assert aged["failing"] == []
    assert "re-test of x@a.com was staged" in aged["stale_note"]
    assert "UNVERIFIED" in aged["stale_note"]


def test_a_stats_failure_keeps_the_previous_verdict(tmp_path):
    """MKT-7c. A failed stats read overwrote the sidecar with failing: [],
    logged ok_partial and exited 0, and the monitor then counted level 2 as
    evaluated and dropped a failure from earlier that day."""
    tests = [{"id": "t1", "timestamp_created": "2026-09-21T00:00:00.000Z"}]
    client, emails, camps = world(tests=tests, stats=_stats(("t1", 1, "x@a.com", 5)))
    first = P.run_placement(NOW, client=client, dry_run=False, changeset_dir=tmp_path,
                            campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert first["result"]["failing"]
    later = NOW + timedelta(hours=2)
    rows = []
    client2, _e, _c = world(tests=tests, stats=RuntimeError("503 upstream"))
    second = P.run_placement(later, client=client2, dry_run=False, changeset_dir=tmp_path,
                             campaigns=camps, log_fn=lambda j, st, d: rows.append(st),
                             notify_fn=lambda *a, **k: None)
    assert second["stats_failed"] is True
    assert rows == ["ok_partial"]
    sidecar = json.loads((tmp_path / P.SIDECAR).read_text())
    assert sidecar["failing"] and sidecar["failing"][0]["email"] == "x@a.com"
    assert sidecar["as_of"] == first["as_of"], "the kept verdict keeps its own date"
    assert sidecar["stats_failed"] is True and sidecar["last_attempt"]["kept_previous_verdict"] is True

    from jobs import deliverability_monitor as M

    aged = M._age_sidecar(sidecar, later, TH.PLACEMENT_RETEST_HOURS / 24.0, "placement")
    assert aged["failing"], "the earlier failure is still today's evidence"
    assert aged.get("stats_failed") is True


def test_the_monitor_does_not_count_level_2_evaluated_after_a_failed_stats_read(tmp_path):
    from jobs import deliverability_monitor as M
    from jobs.tests.test_deliverability_monitor import build_world

    tests = [{"id": "t1", "timestamp_created": "2026-09-21T00:00:00.000Z"}]
    client2, _e, camps = world(tests=tests, stats=RuntimeError("503 upstream"))
    P.run_placement(NOW, client=client2, dry_run=False, changeset_dir=tmp_path,
                    campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    mclient, _, mcamps = build_world(reply_counts={}, days=7)
    report = M.run_monitor(NOW, client=mclient, dry_run=True, changeset_dir=tmp_path,
                           campaigns=mcamps, levels=[1, 2], log_fn=lambda *a: None,
                           notify_fn=lambda *a, **k: None)
    assert 2 not in report["levels_evaluated"]
    assert any("stats read failed" in n for n in report["notes"])


def test_a_stats_row_with_no_sender_is_refused_not_paused(tmp_path):
    """MKT-7d. It produced a `pause_inbox:` proposal with an empty target."""
    tests = [{"id": "t1", "timestamp_created": "2026-09-21T00:00:00.000Z"}]
    client, emails, camps = world(tests=tests, stats=_stats(("t1", 1, "", 2), ("t1", 1, "x@a.com", 10)))
    report = P.run_placement(NOW, client=client, dry_run=True, changeset_dir=tmp_path,
                             campaigns=camps, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert report["result"]["failing"] == []
    assert len(report["result"]["unattributed"]) == 1
    assert not [p for p in report["proposals"] if p["id"] == "pause_inbox:"]
    assert any("no sender_email" in n for n in report["notes"])


def test_main_exits_nonzero_when_the_stats_read_failed(monkeypatch):
    monkeypatch.setattr(P, "run_placement", lambda *a, **k: {"card": "x", "status": "ok_partial",
                                                             "stats_failed": True})
    assert P.main(["--now"]) == 1


def test_an_unfinished_retest_does_not_clear_a_clear_failure():
    """MKT-7a re-review (the reviewer's probe): a re-test with 2 seed deliveries,
    both in the inbox, used to replace a 30% failure and clear the pause."""
    from jobs import inbox_placement as PL

    tests = [{"id": "t_old", "timestamp_created": "2026-09-14T10:00:00Z"},
             {"id": "t_new", "timestamp_created": "2026-09-22T10:00:00Z"}]
    payload = [
        {"test_id": "t_old", "recipient_esp": 1, "sender_email": "a@x.com", "inbox": 3, "spam": 7, "total": 10},
        {"test_id": "t_new", "recipient_esp": 1, "sender_email": "a@x.com", "inbox": 2, "spam": 0, "total": 2},
    ]
    res = PL.score(PL.parse_stats(payload), {}, tests)
    assert [r["email"] for r in res["failing"]] == ["a@x.com"]
    assert res["failing"][0]["test_id"] == "t_old"
    assert res["failing"][0]["retest_in_progress"] == "t_new"
    assert "in progress" in res["failing"][0]["reason"]
    assert res["insufficient"] == []
    assert [r["test_id"] for r in res["in_progress"]] == ["t_new"]


def test_a_finished_retest_still_replaces_the_old_verdict():
    from jobs import inbox_placement as PL

    tests = [{"id": "t_old", "timestamp_created": "2026-09-14T10:00:00Z"},
             {"id": "t_new", "timestamp_created": "2026-09-22T10:00:00Z"}]
    payload = [
        {"test_id": "t_old", "recipient_esp": 1, "sender_email": "a@x.com", "inbox": 3, "spam": 7, "total": 10},
        {"test_id": "t_new", "recipient_esp": 1, "sender_email": "a@x.com", "inbox": 9, "spam": 1, "total": 10},
    ]
    res = PL.score(PL.parse_stats(payload), {}, tests)
    assert res["failing"] == []
    assert [r["test_id"] for r in res["passing"]] == ["t_new"]
    assert res["in_progress"] == []


def test_a_sender_with_only_an_unfinished_test_is_insufficient():
    from jobs import inbox_placement as PL

    tests = [{"id": "t_new", "timestamp_created": "2026-09-22T10:00:00Z"}]
    payload = [{"test_id": "t_new", "recipient_esp": 1, "sender_email": "a@x.com", "inbox": 2, "spam": 0,
                "total": 2}]
    res = PL.score(PL.parse_stats(payload), {}, tests)
    assert [r["email"] for r in res["insufficient"]] == ["a@x.com"]
    assert res["failing"] == [] and res["in_progress"] == []
