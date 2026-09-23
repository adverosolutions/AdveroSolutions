"""Tests for level 4, the Saturday auto-responder canary (M1 L4 / O7).

Run: cd "Agentic Worklfows" && python3 -m pytest jobs/tests/test_deliverability_canary.py -q

The harvest fixtures are the real subjects read from the live workspace on
2026-09-22 (31 auto-responder addresses across 115 received messages), so the
pattern list is tested against the strings that actually arrive rather than
against the five the blueprint happened to name.
"""
import json
from datetime import timedelta

import pytest

from shared import job_log, thresholds as TH
from jobs import autoresponder_canary as C
from jobs.tests.test_deliverability_monitor import StubClient, account, campaign, ct

NOW = ct("2026-09-26 07:10")          # a Saturday

# Verbatim subjects from GET /emails?email_type=received on 2026-09-22.
LIVE_SUBJECTS = [
    ("cecily.welch@cecilywelchcpa.com", "Automatic reply: Cecily, question"),
    ("boris.musheyev@borismtax.com", "Auto Reply Re: Boris, question"),
    ("christy@getworkwife.com", "Out of Office Re: Christy, question"),
    ("brian@bfarrcontracting.com", "Out of office reply Re: Brian, question?"),
    ("nick.angerosa@harperlimbach.com", "Out Of Office Re: Nick, question"),
    ("eva@rbgjanitorial.com", "This email is no longer monitored Re: Eva, question"),
    ("adrian@goforward.com", "This email is no longer in use Re: Adrian, quick question"),
    ("sopiosvanishvili@taxfoaccounting.com", "Re: Sopio, question"),      # a real human reply
]


def received_rows(subjects=None, eaccount="x@a.com", ts="2026-09-20T10:00:00.000Z", i_status=0):
    return [{"from_address_email": addr, "subject": subj, "eaccount": eaccount,
             "timestamp_created": ts, "i_status": i_status}
            for addr, subj in (subjects or LIVE_SUBJECTS)]


def pool_rows(n, ts="2026-09-20T10:00:00.000Z", eaccount="x@a.com"):
    """``n`` distinct auto-responder mailboxes. The plan partitions the pool, so
    a test that wants a real round has to harvest enough mailboxes to cover the
    fleet without mailing anybody twice."""
    return received_rows([("p%02d@pool.com" % i, "Automatic reply: out") for i in range(n)],
                         eaccount=eaccount, ts=ts)


def sent_rows(pairs, ts="2026-09-25T12:00:30.000Z"):
    """GET /emails?email_type=sent rows: which inbox actually mailed which
    address, which is the denominator score_round needs."""
    return [{"eaccount": inbox, "from_address_email": inbox, "to_address_email_list": addr,
             "subject": C.CANARY_SUBJECT, "timestamp_created": ts}
            for inbox, addr in pairs]


class CanaryClient(StubClient):
    def __init__(self, blocklist=None, **kw):
        StubClient.__init__(self, **kw)
        self._blocklist = blocklist if blocklist is not None else []
        self.blocklist_error = None

    def iterate(self, path, params=None, body=None, max_pages=200):
        if path == "block-lists-entries":
            if self.blocklist_error:
                raise self.blocklist_error
            return _rows([{"bl_value": v} for v in self._blocklist])
        return StubClient.iterate(self, path, params, body, max_pages)


class _rows(list):
    truncated = False
    complete = True


def world(emails=None, received=None, blocklist=None, sent=None, lead_statuses=None):
    emails = emails or ["x@a.com", "y@a.com", "z@b.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    client = CanaryClient(blocklist=blocklist, accounts=[account(e) for e in emails],
                          campaigns=camps, emails=received or received_rows(),
                          sent_emails=sent or [], lead_statuses=lead_statuses)
    return client, emails, camps


# ---------------------------------------------------------------------- harvest

def test_every_live_autoresponder_subject_is_recognised():
    out = C.harvest_addresses(None, received=received_rows())
    found = {a["email"] for a in out["addresses"]}
    assert "cecily.welch@cecilywelchcpa.com" in found          # "Automatic reply:"
    assert "boris.musheyev@borismtax.com" in found             # "Auto Reply"
    assert "christy@getworkwife.com" in found                  # "Out of Office"
    assert "brian@bfarrcontracting.com" in found               # "Out of office reply"
    assert "nick.angerosa@harperlimbach.com" in found          # "Out Of Office" (mixed case)
    # A genuine human reply is not an auto-responder.
    assert "sopiosvanishvili@taxfoaccounting.com" not in found


def test_a_dead_mailbox_is_harvested_as_dead_and_never_planned():
    """"no longer monitored" and "no longer in use" mean the address will never
    answer again. Counting them as canary targets guarantees a false kill."""
    out = C.harvest_addresses(None, received=received_rows())
    assert set(out["dead"]) == {"eva@rbgjanitorial.com", "adrian@goforward.com"}
    assert not (set(out["dead"]) & {a["email"] for a in out["addresses"]})


def test_harvest_deduplicates_repeated_autoresponders():
    rows = received_rows([("a@x.com", "Automatic reply: one")]) * 3
    assert len(C.harvest_addresses(None, received=rows)["addresses"]) == 1


# ------------------------------------------------------------------ suppression

def test_suppress_drops_a_blocklisted_address_and_a_blocklisted_domain():
    addresses = [{"email": "a@x.com", "interest_status": 0},
                 {"email": "b@y.com", "interest_status": 0},
                 {"email": "c@z.com", "interest_status": 0}]
    out = C.suppress(addresses, ["a@x.com", "y.com"])
    assert [r["email"] for r in out["kept"]] == ["c@z.com"]
    assert {r["dropped_because"] for r in out["dropped"]} == {"blocklisted", "domain blocklisted"}


def test_suppress_drops_anyone_with_a_negative_interest_status():
    """-1 not interested, -2 wrong person, -3 lost, -4 no show. Mailing someone
    who told Lorenzo to stop is the worst thing this system could do."""
    addresses = [{"email": "ok@x.com", "interest_status": 0},
                 {"email": "no@x.com", "interest_status": -1},
                 {"email": "wrong@x.com", "interest_status": -2}]
    out = C.suppress(addresses, [])
    assert sorted(r["email"] for r in out["kept"]) == ["ok@x.com"]
    assert sorted(r["email"] for r in out["dropped"]) == ["no@x.com", "wrong@x.com"]


def test_an_address_with_no_interest_status_on_the_message_is_not_silently_kept():
    """i_status is null on the received row for 8 of the 29 addresses harvested
    live on 2026-09-22. Someone who answered "not interested" but whose later
    auto-reply carries no status must not be treated as "no negative status"."""
    addresses = [{"email": "ok@x.com", "interest_status": 0},
                 {"email": "none@x.com", "interest_status": None}]
    out = C.suppress(addresses, [])
    assert [r["email"] for r in out["kept"]] == ["ok@x.com"]
    assert out["dropped"][0]["email"] == "none@x.com"
    assert "could not be verified" in out["dropped"][0]["dropped_because"]


def test_the_lead_status_overrides_a_blank_status_on_the_harvested_message():
    addresses = [{"email": "quiet@x.com", "interest_status": None},
                 {"email": "fine@x.com", "interest_status": None}]
    out = C.suppress(addresses, [], statuses={"quiet@x.com": -1, "fine@x.com": 0}, unresolved=[])
    assert [r["email"] for r in out["kept"]] == ["fine@x.com"]
    assert "not_interested" in out["dropped"][0]["dropped_because"]


def test_an_address_the_lead_lookup_could_not_resolve_is_dropped():
    addresses = [{"email": "ghost@x.com", "interest_status": 0}]
    out = C.suppress(addresses, [], statuses={}, unresolved=["ghost@x.com"])
    assert out["kept"] == []
    assert "could not be verified" in out["dropped"][0]["dropped_because"]


def test_resolve_interest_statuses_reports_addresses_with_no_lead_row():
    client, _, _ = world(lead_statuses={"known@x.com": -1})
    out = C.resolve_interest_statuses(client, [{"email": "known@x.com"}, {"email": "ghost@x.com"}])
    assert out["statuses"] == {"known@x.com": -1}
    assert out["unresolved"] == ["ghost@x.com"]


def test_a_failed_lead_lookup_fails_closed_rather_than_open():
    class Boom(object):
        def list_leads(self, **kw):
            raise RuntimeError("HTTP 503")

    out = C.resolve_interest_statuses(Boom(), [{"email": "a@x.com"}])
    assert out["unresolved"] == ["a@x.com"] and "503" in out["error"]
    assert C.suppress([{"email": "a@x.com", "interest_status": 0}], [],
                      statuses=out["statuses"], unresolved=out["unresolved"])["kept"] == []


def test_an_unreadable_blocklist_fails_closed():
    client, _, _ = world()
    client.blocklist_error = RuntimeError("500")
    with pytest.raises(RuntimeError) as exc:
        C.load_blocklist(client)
    assert "refusing to plan a canary" in str(exc.value)


def test_the_run_plans_nothing_when_the_blocklist_cannot_be_read(tmp_path):
    client, emails, camps = world()
    client.blocklist_error = RuntimeError("500")
    report = C.run_canary(NOW, client=client, dry_run=True, changeset_dir=tmp_path, campaigns=camps,
                          log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert report["plan"]["assignments"] == []
    assert report["manual_sends"] == []
    assert any("blocklist" in n for n in report["notes"])


def test_an_unreadable_blocklist_is_a_partial_run_with_a_loud_push(tmp_path):
    """MKT-9: an unreadable blocklist used to log ``ok_unscored`` with a
    default-priority push, which reads like a quiet Saturday."""
    client, emails, camps = world()
    client.blocklist_error = RuntimeError("500")
    rows, pushes = [], []
    report = C.run_canary(NOW, client=client, dry_run=False, changeset_dir=tmp_path, campaigns=camps,
                          write=False, send_card=True,
                          log_fn=lambda job, status, details=None: rows.append((status, details)),
                          notify_fn=lambda title, body="", **k: pushes.append((title, k)))
    assert report["status"] == "ok_partial"
    assert rows[-1][0] == "ok_partial"
    assert rows[-1][1]["read_failures"]
    assert pushes and pushes[-1][1]["priority"] == "high"
    assert "PARTIAL" in pushes[-1][0]


def test_main_exits_non_zero_when_the_blocklist_cannot_be_read(monkeypatch, tmp_path):
    client, emails, camps = world()
    client.blocklist_error = RuntimeError("500")
    real = C.run_canary

    def run(now, **kw):
        return real(now, client=client, changeset_dir=tmp_path, campaigns=camps,
                    log_fn=lambda *a, **k: None, notify_fn=lambda *a, **k: None, **kw)

    monkeypatch.setattr(C, "run_canary", run)
    monkeypatch.setattr(job_log, "use_scratch_logs", lambda *a, **k: None)
    assert C.main(["--dry-run", "--as-of", NOW.isoformat(), "--json"]) == 1


# --------------------------------------------------------------------- the plan

def _inboxes(emails):
    return __import__("jobs.deliverability_monitor", fromlist=["x"]).build_inbox_index(
        [account(e) for e in emails], {"c1": campaign("c1", "cid", emails)}, NOW)


def test_build_plan_gives_every_sending_inbox_a_slice_and_rotates_by_day():
    inboxes = _inboxes(["x@a.com", "y@a.com", "z@b.com"])
    pool = [{"email": "t%d@p.com" % i} for i in range(12)]
    plan = C.build_plan(inboxes, pool, NOW, per_inbox=4)
    assert len(plan["assignments"]) == 3
    assert all(len(a["targets"]) == 4 for a in plan["assignments"])
    # Different inboxes get different slices.
    assert plan["assignments"][0]["targets"] != plan["assignments"][1]["targets"]
    tomorrow = C.build_plan(inboxes, pool, NOW + timedelta(days=1), per_inbox=4)
    assert tomorrow["assignments"][0]["targets"] != plan["assignments"][0]["targets"]


def test_build_plan_never_mails_one_address_twice_in_a_round():
    """The round is a PARTITION of the pool. Wrapping it with a modulo put 4 or
    5 near-identical notes into each of 29 real prospects' mailboxes on the same
    day, each from a different Advero domain, which is the burst-from-many-
    domains pattern level 4 exists to detect."""
    inboxes = _inboxes(["i%d@a.com" % i for i in range(12)])
    pool = [{"email": "t%02d@p.com" % i} for i in range(120)]
    plan = C.build_plan(inboxes, pool, NOW, per_inbox=10)
    everything = [t for a in plan["assignments"] for t in a["targets"]]
    assert len(set(everything)) == sum(len(a["targets"]) for a in plan["assignments"])
    assert len(everything) == 120
    assert plan["sends_per_address"] == TH.CANARY_MAX_SENDS_PER_ADDRESS == 1


def test_build_plan_refuses_when_the_pool_cannot_cover_the_fleet():
    """29 harvested mailboxes cannot give 12 inboxes 10 distinct targets each.
    The old plan wrapped; this one says the pool is too small and sends nothing."""
    inboxes = _inboxes(["i%d@a.com" % i for i in range(12)])
    pool = [{"email": "t%02d@p.com" % i} for i in range(29)]
    plan = C.build_plan(inboxes, pool, NOW, per_inbox=10)
    assert plan["assignments"] == [] and plan["refused"] is True
    assert "pool too small" in plan["note"]
    assert plan["per_inbox"] < TH.CANARY_MIN_ADDRESSES_FOR_VERDICT


def test_build_plan_clamps_rather_than_refusing_when_the_pool_still_covers_a_verdict():
    inboxes = _inboxes(["x@a.com", "y@a.com"])
    pool = [{"email": "t%d@p.com" % i} for i in range(12)]
    plan = C.build_plan(inboxes, pool, NOW, per_inbox=10)
    assert plan["per_inbox"] == 6 and plan["refused"] is False
    assert "clamped" in plan["note"]
    assert len(set(t for a in plan["assignments"] for t in a["targets"])) == 12


def test_build_plan_never_asks_for_more_addresses_than_exist():
    """One harvested address cannot produce a verdict for even one inbox, so
    nothing is planned rather than one lonely send that means nothing."""
    inboxes = _inboxes(["x@a.com"])
    plan = C.build_plan(inboxes, [{"email": "t@p.com"}], NOW, per_inbox=10)
    assert plan["assignments"] == [] and plan["refused"] is True
    assert "pool too small" in plan["note"]


def test_build_plan_with_an_empty_pool_says_so():
    plan = C.build_plan([], [], NOW)
    assert plan["assignments"] == [] and "nothing to send" in plan["note"]


def test_the_canary_email_obeys_the_prospect_copy_rules():
    blob = C.CANARY_SUBJECT + "\n" + C.CANARY_BODY
    assert "—" not in blob and "!" not in blob
    lowered = blob.lower()
    for banned in ("ai ", "automation", "automated", "test", "canary", "deliverability"):
        assert banned not in lowered, banned
    assert blob.rstrip().endswith("Lorenzo")


def test_the_send_is_a_shadow_record_and_no_reply_endpoint_is_ever_called(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    client, emails, camps = world(received=pool_rows(12))
    report = C.run_canary(NOW, client=client, dry_run=True, changeset_dir=tmp_path, campaigns=camps,
                          per_inbox=2, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert len(report["manual_sends"]) == 3
    assert all(m["status"] == C.MANUAL_SEND_STATUS for m in report["manual_sends"])
    assert all(m["sent_by_this_job"] is False for m in report["manual_sends"])
    rows = job_log.read_shadow_log(tmp_path / "shadow.jsonl")
    sends = [r for r in rows if r["action"] == C.CANARY_SEND_ACTION]
    assert len(sends) == 3
    assert "reply_to_uuid" not in sends[0]["payload"]        # never a thread reply
    assert "no v2 endpoint" in sends[0]["payload"]["_mechanism"]
    assert sends[0]["payload"]["_status"] == C.MANUAL_SEND_STATUS
    assert sends[0]["payload"]["_sent_by_this_job"] is False


def test_a_staged_canary_round_never_writes_a_live_write_intent_row(tmp_path, monkeypatch,
                                                                   live_mode):
    """GAP 7. ``guard_write`` opens a ``live_write_intent`` Job_Log row BEFORE
    the call it precedes, to be closed by a ``live_write_ok`` /
    ``live_write_failed`` from the same code path. Level 4 has no send path in
    any mode, so that row could never be closed: the audit trail Lorenzo is
    told to read as his safety gate claimed an intent to email a real
    prospect's mailbox that nothing in this process could carry out.

    MODE=live plus ALLOW_LIVE_WRITES=1 and the round is still only staged.
    """
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    client, emails, camps = world(received=pool_rows(12))
    report = C.run_canary(NOW, client=client, dry_run=False, changeset_dir=tmp_path, campaigns=camps,
                          per_inbox=2, send_card=False, notify_fn=lambda *a, **k: None)

    text = (tmp_path / "job_log.csv").read_text() if (tmp_path / "job_log.csv").exists() else ""
    assert "live_write_intent" not in text
    assert "instantly.canary_send" not in text
    # The one row the run does write says what happened: nothing was sent.
    assert '""manual_sends"": 3' in text and '""sent"": 0' in text   # csv-escaped json

    # The record still exists, in the shadow log, in live mode, saying so.
    rows = job_log.read_shadow_log(tmp_path / "shadow.jsonl")
    sends = [r for r in rows if r["action"] == C.CANARY_SEND_ACTION]
    assert len(sends) == 3
    assert all(r["payload"]["_status"] == C.MANUAL_SEND_STATUS for r in sends)
    assert all(r["payload"]["_sent_by_this_job"] is False for r in sends)
    assert len(report["manual_sends"]) == 3
    assert all(m["mode"] == "live" for m in report["manual_sends"])

    # And no code path even tried to reach a send endpoint.
    assert not hasattr(client, "posted")
    assert not [c for c in client.calls if c[0] not in ("iterate", "list_leads", "get_campaign")]


def test_the_card_never_claims_a_send_was_intended(tmp_path):
    client, emails, camps = world(received=pool_rows(12))
    report = C.run_canary(NOW, client=client, dry_run=True, changeset_dir=tmp_path, campaigns=camps,
                          per_inbox=2, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    card = report["card"]
    assert C.MANUAL_SEND_STATUS in card
    assert "no code path that can send one" in card
    assert "would_do" not in card


# -------------------------------------------------------------------- scoring

def _previous(targets, sent_at="2026-09-25T12:00:00+00:00", inbox="x@a.com"):
    return {"plan": {"round_id": "r1", "per_inbox": len(targets),
                     "assignments": [{"email": inbox, "targets": list(targets), "in_campaigns": ["c1"]}]},
            "sent_at": sent_at}


def test_a_round_that_was_never_sent_is_never_scored_as_zero():
    """The shadow run plans a round and sends nothing. If the next run scored
    that round it would see 0 auto-responses for every inbox and propose killing
    all 12 of them, which is precisely the fleet-wide outage this system exists
    to prevent."""
    prev = _previous(["a@p.com"] * 1)
    prev["sent_at"] = None
    out = C.score_round(prev, [], NOW)
    assert out["scored"] is False and out["failing"] == []
    assert "never marked sent" in out["reason"]


def test_a_round_inside_its_response_window_is_not_scored_yet():
    prev = _previous(["a@p.com"], sent_at="2026-09-26T06:00:00+00:00")
    out = C.score_round(prev, [], NOW)
    assert out["scored"] is False and "window" in out["reason"]


def test_scoring_counts_only_auto_responses_from_the_addresses_that_were_mailed():
    targets = ["t%d@p.com" % i for i in range(10)]
    prev = _previous(targets)
    rows = received_rows([(t, "Automatic reply: hi") for t in targets[:9]],
                         ts="2026-09-25T12:30:00.000Z")
    rows += received_rows([("stranger@q.com", "Automatic reply: hi")], ts="2026-09-25T12:30:00.000Z")
    rows += received_rows([(targets[9], "Re: hi")], ts="2026-09-25T12:30:00.000Z")   # human, not auto
    out = C.score_round(prev, rows, NOW)
    assert out["scored"] is True
    assert out["rows"][0]["responses"] == 9 and out["rows"][0]["response_pct"] == 90.0
    assert out["rows"][0]["verdict"] == "ok"
    assert out["failing"] == []


def test_below_sixty_percent_is_a_kill_and_between_is_a_warning():
    targets = ["t%d@p.com" % i for i in range(10)]
    prev = _previous(targets)
    kill_rows = received_rows([(t, "Automatic reply: hi") for t in targets[:5]],
                              ts="2026-09-25T12:30:00.000Z")
    out = C.score_round(prev, kill_rows, NOW)
    assert out["rows"][0]["verdict"] == "kill" and out["failing"]
    warn_rows = received_rows([(t, "Automatic reply: hi") for t in targets[:7]],
                              ts="2026-09-25T12:30:00.000Z")
    out2 = C.score_round(prev, warn_rows, NOW)
    assert out2["rows"][0]["verdict"] == "warn" and out2["failing"] == []
    assert TH.CANARY_RESPONSE_KILL_PCT == 60.0 and TH.CANARY_RESPONSE_TARGET_PCT == 80.0


def test_a_round_with_too_few_addresses_is_not_a_verdict():
    prev = _previous(["a@p.com", "b@p.com"])
    out = C.score_round(prev, [], NOW)
    assert out["rows"][0]["verdict"] == "insufficient" and out["failing"] == []


def test_a_response_outside_the_window_does_not_count():
    targets = ["t%d@p.com" % i for i in range(10)]
    prev = _previous(targets)
    late = received_rows([(t, "Automatic reply: hi") for t in targets],
                         ts="2026-09-27T12:30:00.000Z")     # after the 24h window
    out = C.score_round(prev, late, NOW)
    assert out["rows"][0]["responses"] == 0


def test_a_failing_round_becomes_a_pause_proposal_and_a_sidecar(tmp_path):
    targets = ["t%d@p.com" % i for i in range(10)]
    prev = _previous(targets)
    C.write_sidecar(tmp_path, C.SIDECAR, prev)
    rows = received_rows([(t, "Automatic reply: hi") for t in targets[:3]],
                         ts="2026-09-25T12:30:00.000Z")
    rows += pool_rows(12, ts="2026-09-20T10:00:00.000Z")
    client, emails, camps = world(received=rows,
                                  sent=sent_rows([("x@a.com", t) for t in targets]))
    report = C.run_canary(NOW, client=client, dry_run=False, changeset_dir=tmp_path, campaigns=camps,
                          per_inbox=2, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    p = [x for x in report["proposals"] if x["kind"] == "pause_inbox"]
    assert p and p[0]["target"] == "x@a.com" and p[0]["level"] == 4
    assert json.loads((tmp_path / "2026-09-26.json").read_text())["proposals"][0]["id"] \
        == "pause_inbox:x@a.com"
    # The new sidecar replaces the old one and starts unsent again.
    sidecar = json.loads((tmp_path / C.SIDECAR).read_text())
    assert sidecar["sent_at"] is None and "sent_at_note" in sidecar
    # ... and the round it rolled forward is still on disk under its own name.
    assert (tmp_path / "last_canary_r1.json").exists()


def test_a_level_4_pause_proposal_carries_the_email_list_patches_too(tmp_path):
    """Three jobs write one change-set file. A pause-only action list from the
    canary used to replace the monitor's complete one, and applying the merged
    proposal paused the inbox while leaving it in every campaign's email_list."""
    targets = ["t%d@p.com" % i for i in range(10)]
    prev = _previous(targets)
    C.write_sidecar(tmp_path, C.SIDECAR, prev)
    rows = received_rows([(t, "Automatic reply: hi") for t in targets[:3]],
                         ts="2026-09-25T12:30:00.000Z")
    client, emails, camps = world(received=rows,
                                  sent=sent_rows([("x@a.com", t) for t in targets]))
    report = C.run_canary(NOW, client=client, dry_run=True, changeset_dir=tmp_path, campaigns=camps,
                          log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    ops = [a["op"] for a in report["proposals"][0]["actions"]]
    assert "pause_account" in ops and "patch_campaign_email_list" in ops


def test_a_round_sent_through_one_campaign_is_not_scored_as_twelve_kills():
    """The old runbook said: one campaign, email_list = every inbox, lead list =
    the round's addresses. Instantly then picks which inbox mails which address,
    so every planned (inbox, address) pair misses and a perfectly healthy round
    scores 0-20% per inbox. Killing the fleet on that reading is the worst
    outcome this system can produce."""
    inboxes = ["i%d@a.com" % i for i in range(12)]
    addresses = ["t%02d@p.com" % i for i in range(29)]
    assignments = []
    for n, inbox in enumerate(inboxes):          # the committed over-subscribed plan
        assignments.append({"email": inbox, "in_campaigns": ["c1"],
                            "targets": [addresses[(n * 10 + k) % 29] for k in range(10)]})
    prev = {"plan": {"round_id": "r-live", "per_inbox": 10, "assignments": assignments},
            "sent_at": "2026-09-25T12:00:00+00:00"}
    # The healthiest possible outcome: all 29 mailboxes auto-replied, each to
    # whichever inbox Instantly happened to use.
    received = [{"from_address_email": a, "subject": "Automatic reply: out",
                 "eaccount": inboxes[i % 12], "timestamp_created": "2026-09-25T12:30:00.000Z"}
                for i, a in enumerate(addresses)]
    out = C.score_round(prev, received, NOW)
    assert out["scored"] is False
    assert out["attribution"] == "unattributable"
    assert out["failing"] == []
    assert "attribution failure" in out["reason"]


def test_scoring_uses_what_was_actually_sent_not_what_was_planned():
    """With GET /emails?email_type=sent in hand the denominator is real, so the
    same round scores per inbox on the addresses that inbox really mailed."""
    prev = _previous(["t%d@p.com" % i for i in range(10)])
    # Instantly actually gave x@a.com only five of them, and all five answered.
    really_sent = ["t%d@p.com" % i for i in range(5)]
    received = received_rows([(t, "Automatic reply: out") for t in really_sent],
                             ts="2026-09-25T12:30:00.000Z")
    out = C.score_round(prev, received, NOW,
                        sent=sent_rows([("x@a.com", t) for t in really_sent]))
    assert out["scored"] is True and out["attribution"] == "measured"
    assert out["rows"][0]["sent"] == 5 and out["rows"][0]["responses"] == 5
    assert out["rows"][0]["verdict"] == "ok" and out["failing"] == []


def test_a_round_marked_sent_with_no_sent_messages_is_unscorable():
    prev = _previous(["t%d@p.com" % i for i in range(10)])
    out = C.score_round(prev, [], NOW, sent=[])
    assert out["scored"] is False and out["attribution"] == "none"
    assert "nothing to attribute" in out["reason"]


def test_a_second_run_inside_the_response_window_does_not_discard_the_sent_round(tmp_path):
    """Runbook step 6 has Lorenzo write sent_at by hand. A scheduler retry or a
    second --now used to replace the plan and blank sent_at, so a round whose
    emails had already reached 29 prospects could never be scored and the next
    round mailed them again."""
    targets = ["t%d@p.com" % i for i in range(10)]
    prev = _previous(targets, sent_at="2026-09-26T05:00:00+00:00")   # 2 h before NOW
    C.write_sidecar(tmp_path, C.SIDECAR, prev)
    client, emails, camps = world(received=pool_rows(12))
    report = C.run_canary(NOW, client=client, dry_run=False, changeset_dir=tmp_path, campaigns=camps,
                          log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    after = json.loads((tmp_path / C.SIDECAR).read_text())
    assert after["sent_at"] == "2026-09-26T05:00:00+00:00"
    assert after["plan"]["round_id"] == "r1"
    assert after["plan"]["assignments"][0]["targets"] == targets
    assert report["pending"] is True and report["manual_sends"] == []
    assert any("response window closes" in n for n in report["notes"])


def test_a_truncated_received_walk_is_not_reported_as_a_complete_harvest():
    class Truncated(list):
        truncated = True
        complete = False

    class Client(object):
        def iterate(self, path, params=None, body=None, max_pages=200):
            return Truncated(received_rows())

    with pytest.raises(RuntimeError) as exc:
        C.harvest_addresses(Client())
    assert "partial" in str(exc.value)


def test_a_truncated_blocklist_walk_refuses_to_plan():
    class Truncated(list):
        truncated = True
        complete = False

    class Client(object):
        def iterate(self, path, params=None, body=None, max_pages=200):
            return Truncated([{"bl_value": "a@x.com"}])

    with pytest.raises(RuntimeError) as exc:
        C.load_blocklist(Client())
    assert "partial blocklist" in str(exc.value)
    assert TH.BLOCKLIST_MAX_PAGES > 10


def test_dry_run_writes_nothing(tmp_path):
    client, emails, camps = world()
    C.run_canary(NOW, client=client, dry_run=True, changeset_dir=tmp_path, campaigns=camps,
                 log_fn=lambda *a: None, notify_fn=lambda *a, **k: None)
    assert list(tmp_path.iterdir()) == []
