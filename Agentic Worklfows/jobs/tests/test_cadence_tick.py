"""jobs.cadence_tick: store sweep, dry-run purity, Job_Log row, digest, zero HTTP in shadow."""
import csv
import json
from datetime import datetime

import httpx
import pytest

from shared import notify as notify_mod
from shared import slots as slot_rules
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.job_log import job_log_path, read_shadow_log
from shared.settings import TZ
from shared.store import JsonFileStore

from jobs import cadence_tick
from services.reply_engine import cadence
from services.reply_engine.cadence import LeadState

CLEANING_REACT = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
BOOKKEEPING_REACT = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"


def ct(*args):
    return TZ.localize(datetime(*args))


def raising_transport():
    def handler(request):
        raise AssertionError("HTTP request attempted in shadow: %s %s" % (request.method, request.url))

    return httpx.MockTransport(handler)


def seed(store, armed_at):
    a = cadence.arm(LeadState(lead_email="tiffany@flowerhillfs.com", campaign_id=CLEANING_REACT, status="positive_interested",
                              first_name="Tiffany", company="Flowerhill Facility Services", eaccount="lorenzo@adveromedia.com",
                              last_email_id="e-1", last_subject="Re: Tiffany, question"), armed_at)
    b = cadence.arm(LeadState(lead_email="sopiosvanishvili@taxfoaccounting.com", campaign_id=BOOKKEEPING_REACT, status="positive_question",
                              first_name="Sopio", company="Taxfo Accounting", eaccount="lorenzov@theadvero.com",
                              last_email_id="e-2", last_subject="Re: Sopio, question"), armed_at)
    b.cadence["day"] = 2  # Sopio is on D3
    c = LeadState(lead_email="quiet@example.com", campaign_id=CLEANING_REACT, status="new")  # never armed
    d = cadence.arm(LeadState(lead_email="replied@example.com", campaign_id=CLEANING_REACT, status="positive_interested",
                              first_name="Rob", eaccount="lorenzo@myadvero.com", last_email_id="e-4"), armed_at)
    d.last_inbound_at = (armed_at.replace(hour=23)).isoformat()  # replied after arming -> stop
    for s in (a, b, c, d):
        store.set(s.key, cadence.state_to_dict(s))
    return a, b, c, d


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


def test_dry_run_plans_without_mutating_store_or_logging_shadow(store, tmp_env, capsys):
    seed(store, ct(2026, 9, 21, 16, 0))
    before = {k: store.get(k) for k in store.keys()}
    notify_mod.reset_for_tests()
    summary = cadence_tick.run(ct(2026, 9, 22, 10, 5), store, dry_run=True)
    assert summary["dry_run"] is True and summary["leads_seen"] == 4 and summary["leads_armed"] == 3
    assert summary["counts"] == {"would_send": 2, "stopped": 1}
    days = sorted((r["lead_email"], r["day"]) for r in summary["results"] if r["action"] == "would_send")
    assert days == [("sopiosvanishvili@taxfoaccounting.com", 3), ("tiffany@flowerhillfs.com", 1)]
    assert {k: store.get(k) for k in store.keys()} == before
    assert store.get("offered:2026-09-22") is None
    assert read_shadow_log() == []
    assert notify_mod.sent_in_test == []
    rows = list(csv.DictReader(open(job_log_path(), encoding="utf-8")))
    assert rows[-1]["job"] == "cadence_tick" and rows[-1]["status"] == "dry_run" and rows[-1]["mode"] == "shadow"
    details = json.loads(rows[-1]["details"])
    assert details["counts"] == {"would_send": 2, "stopped": 1} and len(details["digest"]) == 3


def test_shadow_run_records_would_do_persists_state_and_notifies_digest(store, tmp_env):
    seed(store, ct(2026, 9, 21, 16, 0))
    notify_mod.reset_for_tests()
    inst = Instantly(api_key="x", transport=raising_transport())
    ghl = GHL(token="fake-token", transport=raising_transport())
    now = ct(2026, 9, 22, 10, 5)
    summary = cadence_tick.run(now, store, instantly=inst, ghl=ghl, free_slots=cadence.default_slot_grid(now))
    assert summary["counts"] == {"would_send": 2, "stopped": 1}
    log = read_shadow_log()
    assert [r["action"] for r in log if r["system"] == "instantly"] == ["reply_to_email", "reply_to_email"]
    tiff = cadence.state_from_dict(store.get("lead:%s:tiffany@flowerhillfs.com" % CLEANING_REACT))
    assert tiff.cadence["day"] == 1 and tiff.cadence["next_send_at"] == "2026-09-23T10:00:00-05:00"
    assert len(tiff.offered_slots) == 2
    sopio = cadence.state_from_dict(store.get("lead:%s:sopiosvanishvili@taxfoaccounting.com" % BOOKKEEPING_REACT))
    assert sopio.cadence["day"] == 3
    assert not (set(tiff.offered_slots) & set(sopio.offered_slots))
    assert len(store.get("offered:2026-09-22")) == 4
    rob = cadence.state_from_dict(store.get("lead:%s:replied@example.com" % CLEANING_REACT))
    assert rob.cadence["stopped_reason"] == "inbound_reply" and rob.cadence["needs_fresh_draft"] is True
    assert len(notify_mod.sent_in_test) == 1
    digest = notify_mod.sent_in_test[0]
    # the title counts touches that went out, not digest lines: two touches were
    # sent and one lead stopped, and "stopped" is not a problem, so no "need you"
    assert digest["title"] == "[shadow] Cadence Tue 10:05 CT: 2 touches"
    assert "D1 -> tiffany@flowerhillfs.com" in digest["message"] and "replied@example.com: cadence stopped (inbound_reply)" in digest["message"]
    # second tick the same hour: nothing new, no second digest
    summary2 = cadence_tick.run(ct(2026, 9, 22, 11, 5), store, instantly=inst, ghl=ghl, free_slots=cadence.default_slot_grid(now))
    # the lead who replied is named once ("waiting on your approved answer"), then goes quiet
    assert summary2["counts"] == {"not_due": 2, "awaiting_fresh_draft": 1}
    assert len(notify_mod.sent_in_test) == 2
    # Rob's reply raised no card (the seed has none): the line says so rather
    # than claiming an answer is waiting on Lorenzo (round-6 follow-up)
    assert "raised no card" in notify_mod.sent_in_test[1]["message"]
    assert "waiting on your approved answer" not in notify_mod.sent_in_test[1]["message"]
    summary3 = cadence_tick.run(ct(2026, 9, 22, 12, 5), store, instantly=inst, ghl=ghl, free_slots=cadence.default_slot_grid(now))
    assert summary3["counts"] == {"not_due": 2, "already_stopped": 1}
    assert len(notify_mod.sent_in_test) == 2


def test_weekend_tick_is_quiet(store, tmp_env):
    """Saturday sends nothing. The old `or` arm passed trivially whenever the
    notify list was non-empty, so it asserted almost nothing; the seed does
    include one lead that legitimately stops on the first tick (it replied after
    arming), and that stop is reported once and then never again."""
    seed(store, ct(2026, 9, 25, 16, 0))
    notify_mod.reset_for_tests()
    summary = cadence_tick.run(ct(2026, 9, 26, 10, 0), store)
    assert summary["counts"]["not_due"] == 2
    assert summary["touches"] == 0 and summary["needs_you"] == 0
    assert len(notify_mod.sent_in_test) == 1
    lines = notify_mod.sent_in_test[0]["message"].splitlines()
    assert lines == ["replied@example.com: cadence stopped (inbound_reply)"]
    assert notify_mod.sent_in_test[0]["priority"] == "default"
    # the stalled lead is named once more (no card was raised for its reply,
    # and the line says so), then the rest of the weekend is completely silent
    notify_mod.reset_for_tests()
    assert cadence_tick.run(ct(2026, 9, 26, 14, 0), store)["touches"] == 0
    assert len(notify_mod.sent_in_test) == 1
    assert "raised no card" in notify_mod.sent_in_test[0]["message"]
    notify_mod.reset_for_tests()
    for when in (ct(2026, 9, 26, 16, 0), ct(2026, 9, 27, 10, 0), ct(2026, 9, 27, 17, 0)):
        out = cadence_tick.run(when, store)
        assert out["touches"] == 0 and out["needs_you"] == 0
    assert notify_mod.sent_in_test == []
    assert read_shadow_log() == []


def test_cli_dry_run_with_now_and_store(store, tmp_env, capsys):
    seed(store, ct(2026, 9, 21, 16, 0))
    rc = cadence_tick.main(["--dry-run", "--now", "2026-09-22T10:05:00-05:00", "--store", str(store.path), "--bodies"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry_run=True" in out and "would_send" in out and "The time slots I sent got filled. Here are 2 more" in out
    assert "Those last two times got taken too." in out
    rc = cadence_tick.main(["--dry-run", "--now", "2026-09-22T10:05:00-05:00", "--store", str(store.path), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["counts"]["would_send"] == 2


def test_bad_record_does_not_stop_the_sweep(store, tmp_env):
    seed(store, ct(2026, 9, 21, 16, 0))
    store.set("lead:bad", {"cadence": {"armed_at": "x"}, "lead_email": 5, "campaign_id": []})
    summary = cadence_tick.run(ct(2026, 9, 22, 10, 5), store, dry_run=True)
    assert summary["counts"].get("would_send") == 2


def test_lead_that_errors_is_reported_and_does_not_stall(store, tmp_env, monkeypatch):
    """An exception inside tick_lead used to leave day/next_send_at untouched,
    retry the same failing call every hour and never reach Lorenzo: 'error' was
    not in ACTIONABLE and the Job_Log row still said 'ok'."""
    seed(store, ct(2026, 9, 21, 16, 0))
    notify_mod.reset_for_tests()
    real_tick = cadence.tick_lead

    def boom(state, now, **kw):
        if getattr(state, "lead_email", "") == "tiffany@flowerhillfs.com":
            raise RuntimeError("GHL 422 on the D6 hold")
        return real_tick(state, now, **kw)

    monkeypatch.setattr(cadence, "tick_lead", boom)
    rows = []
    summary = cadence_tick.run(ct(2026, 9, 22, 10, 5), store, log_fn=lambda *a: rows.append(a))
    assert summary["counts"]["error"] == 1
    assert any("tiffany@flowerhillfs.com" in line and "errored" in line for line in summary["digest"])
    assert rows[-1][1] == "errors"
    assert notify_mod.sent_in_test and notify_mod.sent_in_test[-1]["priority"] == "high"


def test_a_claimed_lead_is_skipped_by_an_overlapping_tick(store, tmp_env):
    """Two overlapping runs must not both send the same touch."""
    seed(store, ct(2026, 9, 21, 16, 0))
    notify_mod.reset_for_tests()
    now = ct(2026, 9, 22, 10, 5)
    store.set(cadence_tick.lock_key("lead:%s:tiffany@flowerhillfs.com" % CLEANING_REACT),
              {"ts": now.isoformat(), "pid": 1})
    summary = cadence_tick.run(now, store, free_slots=cadence.default_slot_grid(now))
    assert summary["counts"].get("locked") == 1
    assert not any(r.get("lead_email") == "tiffany@flowerhillfs.com" and r.get("action") == "would_send"
                   for r in summary["results"])
    # the claim is released after each lead, so the next tick picks it up
    assert store.get(cadence_tick.lock_key("lead:%s:sopiosvanishvili@taxfoaccounting.com" % BOOKKEEPING_REACT)) is None


def test_an_expired_claim_does_not_block_the_next_tick(store, tmp_env):
    seed(store, ct(2026, 9, 21, 16, 0))
    now = ct(2026, 9, 22, 10, 5)
    key = "lead:%s:tiffany@flowerhillfs.com" % CLEANING_REACT
    store.set(cadence_tick.lock_key(key), {"ts": ct(2026, 9, 22, 9, 0).isoformat(), "pid": 1})
    summary = cadence_tick.run(now, store, free_slots=cadence.default_slot_grid(now))
    assert summary["counts"].get("locked") is None
    assert summary["counts"]["would_send"] == 2


# ----------------------------------------- regressions found by the A2 review
def test_an_unverifiable_slot_source_is_reported_once_and_then_escalates(store, tmp_env, live_mode):
    """config/ids.json records GHL_PRIVATE_INTEGRATION_TOKEN as "not yet
    created", so resolve_free_slots falls back to the synthetic default_grid and
    every slot-bearing touch returned skipped_unverified_slots WITHOUT recording
    a touch: the ladder never advanced, never stopped, and put a high-priority
    line in nine digests a day per lead."""
    a, b, c, d = seed(store, ct(2026, 9, 21, 16, 0))
    # both armed leads are past the D1 veto window so the slot path is reached
    for s in (a, b):
        s.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
        store.set(s.key, cadence.state_to_dict(s))
    notify_mod.reset_for_tests()
    ghl = GHL(token=None)
    titles = []
    for hour in range(10, 19):
        summary = cadence_tick.run(ct(2026, 9, 22, hour, 5), store, ghl=ghl)
        titles.append(summary["counts"])
    # reported on the first tick of the day only
    digests = [n for n in notify_mod.sent_in_test if "Cadence" in n["title"]]
    assert digests[0]["title"] == "Cadence Tue 10:05 CT: 0 touches, 2 need you"
    # the skip is named once; the later digests carry other business only
    skip_mentions = [n for n in digests if "skipped_unverified_slots" in n["message"]]
    assert len(skip_mentions) == 1, [n["title"] for n in digests]
    assert all("need you" not in n["title"] for n in digests[1:]), [n["title"] for n in digests]
    assert titles[0].get("skipped_unverified_slots") == 2
    assert all(t.get("skipped_unverified_slots") == 2 for t in titles), titles
    tiff = cadence.state_from_dict(store.get(a.key))
    assert tiff.cadence["touches"] == [] and tiff.cadence["last_skipped"]["days"] == 1
    # the next day it is still unverifiable: stop rather than look like it runs
    notify_mod.reset_for_tests()
    summary = cadence_tick.run(ct(2026, 9, 23, 10, 5), store, ghl=ghl)
    assert summary["counts"].get("stopped") == 2
    tiff = cadence.state_from_dict(store.get(a.key))
    assert tiff.cadence["stopped_reason"] == "slots_unavailable"
    assert any("no bookable times" in n["title"] for n in notify_mod.sent_in_test)


def test_digest_title_plural_and_touch_count(store, tmp_env, live_mode):
    """Both arms of the plural conditional were the empty string, so one problem
    read "1 need you"; and the count came from len(digest_lines), so a tick that
    sent nothing still read "1 touch"."""
    a, b, c, d = seed(store, ct(2026, 9, 21, 16, 0))
    store.delete(b.key)  # one armed, sendable lead left besides the stopped one
    a.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    store.set(a.key, cadence.state_to_dict(a))
    notify_mod.reset_for_tests()
    summary = cadence_tick.run(ct(2026, 9, 22, 10, 5), store, ghl=GHL(token=None))
    assert summary["touches"] == 0 and summary["needs_you"] == 1
    title = [n for n in notify_mod.sent_in_test if "Cadence" in n["title"]][0]["title"]
    assert title == "Cadence Tue 10:05 CT: 0 touches, 1 needs you", title


def test_the_claim_spans_the_persist_and_uses_an_atomic_primitive(store, tmp_env, monkeypatch):
    """_claim used the get-then-set idiom shared/store.py documents as unsafe,
    and _release ran in the `finally` BEFORE the mutated state was written back."""
    seed(store, ct(2026, 9, 21, 16, 0))
    key = "lead:%s:tiffany@flowerhillfs.com" % CLEANING_REACT
    now = ct(2026, 9, 22, 10, 5)
    # the claim is atomic: the second caller loses
    assert cadence_tick._claim(store, key, now, False) is True
    assert cadence_tick._claim(store, key, now, False) is False
    cadence_tick._release(store, key, False)
    # and it is still held while the state is being written back
    seen = {}
    real_set = store.set

    def spy(k, v):
        if k == key:
            seen["lock_held_at_persist"] = store.get(cadence_tick.lock_key(k)) is not None
        return real_set(k, v)

    # The write-back is a merge under store.mutate now (SAL-4), so spy on
    # that path as well as on a plain set.
    real_mutate = store.mutate

    def spy_mutate(k, fn, *a, **kw):
        if k == key:
            seen["lock_held_at_persist"] = store.get(cadence_tick.lock_key(k)) is not None
        return real_mutate(k, fn, *a, **kw)

    monkeypatch.setattr(store, "set", spy)
    monkeypatch.setattr(store, "mutate", spy_mutate)
    cadence_tick.run(now, store, free_slots=cadence.default_slot_grid(now))
    assert seen.get("lock_held_at_persist") is True
    assert store.get(cadence_tick.lock_key(key)) is None


def test_main_closes_the_clients_it_opened(store, tmp_env, monkeypatch):
    """`python3 -m jobs.cadence_tick` left two httpx pools to the collector."""
    closed = []

    class FakeClient(object):
        def close(self):
            closed.append(self)

    monkeypatch.setattr(cadence_tick, "_clients", lambda dry_run: (FakeClient(), FakeClient()))
    monkeypatch.setattr(cadence_tick, "run", lambda *a, **k: {"now": "x", "mode": "shadow", "live": False,
                                                              "dry_run": False, "leads_seen": 0, "leads_armed": 0,
                                                              "counts": {}, "digest": [], "results": []})
    assert cadence_tick.main(["--now", "2026-09-22T10:05:00-05:00", "--store", str(store.path)]) == 0
    assert len(closed) == 2


def test_a_template_hold_is_actionable_and_a_problem():
    """CT3: a day held because its template is not approved sent nothing, so
    it reaches the digest and the Job_Log row says 'errors'."""
    assert "held_template" in cadence_tick.ACTIONABLE
    assert "held_template" in cadence_tick.PROBLEM_ACTIONS


def test_a_held_day_shows_its_template_id_in_the_digest_never_the_body(store, tmp_env, approvals_file):
    a, b, _, _ = seed(store, ct(2026, 9, 21, 16, 0))
    approvals_file.revoke_ids("cadence.e3")  # Sopio is on D3
    pushes = []
    summary = cadence_tick.run(ct(2026, 9, 22, 10, 5), store, log_fn=lambda *x: None,
                               notify_fn=lambda *x, **k: pushes.append((x, k)))
    assert summary["counts"].get("held_template") == 1
    held = [line for line in summary["digest"] if "HELD" in line]
    assert len(held) == 1 and "cadence.e3" in held[0] and "unapproved" in held[0]
    assert "A couple more options" not in "\n".join(summary["digest"])
    assert pushes and "A couple more options" not in pushes[-1][0][1]
    assert not [r for r in read_shadow_log() if r["action"] == "reply_to_email" and "Sopio" in r["payload"]["body"]["text"]]
