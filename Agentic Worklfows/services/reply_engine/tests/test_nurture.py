"""90-day nurture enrollment hook (section 1) and the cadence guard that stops
the follow-up ladder for an enrolled lead.

MODE=shadow from conftest; the one live-mode test monkeypatches it in-process
and every client sits on a transport that records instead of sending.
"""
import json
import os
from datetime import datetime

import httpx
import pytest
import pytz

from shared import settings
from shared import slots as slot_rules
from shared.instantly import Instantly
from shared.settings import TZ
from shared.store import JsonFileStore, get_store

from services.reply_engine import cadence
from services.reply_engine import nurture
from services.reply_engine.cadence import LeadState

EMAIL = "tiffany@flowerhillfs.com"
CAMPAIGN = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"


def ct(*args):
    return TZ.localize(datetime(*args))


NOW = ct(2026, 9, 23, 10, 0)  # a Wednesday, CDT (-05:00)
ARMED = ct(2026, 9, 21, 21, 10)  # Monday night: D1 due Tue 22nd 10:00


def make_state(email=EMAIL, **kw):
    base = dict(lead_email=email, campaign_id=CAMPAIGN, status="positive_interested", first_name="Tiffany",
                company="Flowerhill Facility Services", eaccount="lorenzo@adveromedia.com", thread_id="thr-1",
                last_email_id="01a0c5aa-0000-7000-8000-000000000001", last_subject="Re: Tiffany, question")
    base.update(kw)
    return LeadState(**base)


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "own_store.json")


class Recorder(object):
    """Any method call on it is recorded and answered with None."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*a, **k):
            self.calls.append((name, a, k))
            return None

        return call


# ------------------------------------------------------------ enroll
def test_positional_enroll_uses_the_default_store_and_writes_the_contract_shape():
    rec = nurture.enroll(EMAIL, "no_reply_after_sequence", NOW)
    assert rec["created"] is True
    assert rec["lead_email"] == EMAIL
    assert rec["status"] == "active"
    assert rec["reason"] == "no_reply_after_sequence"
    assert rec["enrolled_at"] == "2026-09-23T10:00:00-05:00"
    # +90 calendar days on the CT wall clock: 10:00 CST after the DST change
    assert rec["ends_at"] == "2026-12-22T10:00:00-06:00"
    assert (slot_rules.parse_iso(rec["ends_at"]).date() - NOW.date()).days == nurture.NURTURE_DAYS == 90
    assert rec["campaign_id"] is None
    assert rec["events"] == [{"reason": "no_reply_after_sequence", "at": "2026-09-23T10:00:00-05:00",
                              "campaign_id": None, "note": None}]
    assert rec["touches"] == []
    # it landed in the conftest's per-test store, at its own key, and "created" is not stored
    stored = get_store().get("nurture:" + EMAIL)
    assert stored == dict((k, v) for k, v in rec.items() if k != "created")
    assert "created" not in stored
    assert os.environ["STORE_PATH"] in str(get_store().path)
    json.dumps(stored)  # JSON-safe
    assert get_store().keys("lead:") == []  # no lead row written


def test_enroll_converts_an_aware_utc_now_to_ct_and_records_campaign_and_note(store):
    utc_now = pytz.utc.localize(datetime(2026, 9, 23, 15, 0))
    rec = nurture.enroll(EMAIL, "not_now_reply", utc_now, store=store, campaign_id=CAMPAIGN, note="said Q1")
    assert rec["enrolled_at"] == "2026-09-23T10:00:00-05:00"
    assert rec["campaign_id"] == CAMPAIGN
    assert rec["events"][0]["campaign_id"] == CAMPAIGN and rec["events"][0]["note"] == "said Q1"


def test_email_is_normalized(store):
    rec = nurture.enroll(" Bob@X.com ", "not_now_reply", NOW, store=store)
    assert rec["lead_email"] == "bob@x.com"
    assert nurture.nurture_key(" Bob@X.com ") == "nurture:bob@x.com"
    assert store.keys("nurture:") == ["nurture:bob@x.com"]
    assert nurture.is_enrolled("BOB@x.com", store) is True


@pytest.mark.parametrize("bad", ["", "   ", None, "no-at-sign"])
def test_bad_email_raises(store, bad):
    with pytest.raises(ValueError):
        nurture.enroll(bad, "not_now_reply", NOW, store=store)
    assert store.keys("") == []


def test_bad_reason_raises(store):
    with pytest.raises(ValueError):
        nurture.enroll(EMAIL, "booked", NOW, store=store)
    assert store.keys("") == []


def test_naive_now_raises(store):
    with pytest.raises(ValueError):
        nurture.enroll(EMAIL, "not_now_reply", datetime(2026, 9, 23, 10, 0), store=store)
    assert store.keys("") == []


@pytest.mark.parametrize("reason", nurture.REASONS)
def test_each_reason_is_accepted(store, reason):
    rec = nurture.enroll(EMAIL, reason, NOW, store=store)
    assert rec["created"] is True and rec["reason"] == reason
    assert set(nurture.REASONS) == {"no_reply_after_sequence", "not_now_reply", "no_show_no_rebook"}


# ------------------------------------------------------------ idempotency
def test_same_reason_twice_is_a_no_op(store):
    first = nurture.enroll(EMAIL, "no_show_no_rebook", NOW, store=store)
    again = nurture.enroll(EMAIL, "no_show_no_rebook", ct(2026, 9, 24, 11, 0), store=store)
    assert again["created"] is False
    assert again["enrolled_at"] == first["enrolled_at"] and again["ends_at"] == first["ends_at"]
    assert len(again["events"]) == 1


def test_a_new_reason_appends_one_event_and_keeps_the_original(store):
    first = nurture.enroll(EMAIL, "no_reply_after_sequence", NOW, store=store)
    later = ct(2026, 10, 1, 9, 0)
    second = nurture.enroll(EMAIL, "not_now_reply", later, store=store, campaign_id=CAMPAIGN, note="retry")
    assert second["created"] is False
    assert second["reason"] == "no_reply_after_sequence"
    assert second["enrolled_at"] == first["enrolled_at"] and second["ends_at"] == first["ends_at"]
    assert [e["reason"] for e in second["events"]] == ["no_reply_after_sequence", "not_now_reply"]
    assert second["events"][-1] == {"reason": "not_now_reply", "at": later.isoformat(), "campaign_id": CAMPAIGN,
                                    "note": "retry"}
    assert second["campaign_id"] == CAMPAIGN  # filled, it was None
    # a retrying job calling again with the same new reason does not grow the list
    third = nurture.enroll(EMAIL, "not_now_reply", ct(2026, 10, 1, 10, 0), store=store)
    assert third["created"] is False and len(third["events"]) == 2
    assert store.get(nurture.nurture_key(EMAIL)) == dict((k, v) for k, v in third.items() if k != "created")


def test_campaign_id_is_not_overwritten_once_set(store):
    nurture.enroll(EMAIL, "not_now_reply", NOW, store=store, campaign_id="first")
    rec = nurture.enroll(EMAIL, "not_now_reply", NOW, store=store, campaign_id="second")
    assert rec["campaign_id"] == "first"


def test_a_finished_enrollment_restarts_and_keeps_its_events(store):
    old_event = {"reason": "no_reply_after_sequence", "at": "2026-01-02T10:00:00-06:00", "campaign_id": None,
                 "note": None}
    store.set(nurture.nurture_key(EMAIL), {"lead_email": EMAIL, "status": "ended", "reason": "no_reply_after_sequence",
                                           "enrolled_at": "2026-01-02T10:00:00-06:00",
                                           "ends_at": "2026-04-02T10:00:00-05:00", "campaign_id": None,
                                           "events": [old_event], "touches": [{"sent": True}]})
    assert nurture.is_enrolled(EMAIL, store) is False
    rec = nurture.enroll(EMAIL, "not_now_reply", NOW, store=store)
    assert rec["created"] is True
    assert rec["status"] == "active" and rec["reason"] == "not_now_reply"
    assert rec["enrolled_at"] == NOW.isoformat() and rec["ends_at"] == "2026-12-22T10:00:00-06:00"
    assert rec["events"] == [old_event, {"reason": "not_now_reply", "at": NOW.isoformat(), "campaign_id": None,
                                         "note": None}]
    assert rec["touches"] == []
    assert nurture.is_enrolled(EMAIL, store) is True


@pytest.mark.parametrize("junk", ["active", ["active"], 7, True])
def test_a_malformed_stored_value_is_replaced(store, junk):
    store.set(nurture.nurture_key(EMAIL), junk)
    assert nurture.get(EMAIL, store) is None and nurture.is_enrolled(EMAIL, store) is False
    rec = nurture.enroll(EMAIL, "no_show_no_rebook", NOW, store=store)
    assert rec["created"] is True and len(rec["events"]) == 1
    assert store.get(nurture.nurture_key(EMAIL))["status"] == "active"


def test_get_and_is_enrolled_for_unknown_or_unusable_email(store):
    assert nurture.get("nobody@x.com", store) is None
    assert nurture.is_enrolled("nobody@x.com", store) is False
    assert nurture.get("", store) is None and nurture.is_enrolled(None, store) is False
    nurture.enroll(EMAIL, "not_now_reply", NOW, store=store)
    assert nurture.get(EMAIL, store)["status"] == "active"


# ------------------------------------------------------------ mode safety
def test_shadow_enroll_makes_no_guarded_write_and_no_request(store, monkeypatch):
    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    assert settings.get_mode() == "shadow" and not settings.is_live()

    def refuse(*a, **k):
        raise AssertionError("nurture.enroll went through guard_write: %r %r" % (a, k))

    monkeypatch.setattr(settings, "guard_write", refuse)
    monkeypatch.setattr(cadence, "guard_write", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)
    rec = nurture.enroll(EMAIL, "no_reply_after_sequence", NOW, store=store)
    assert rec["created"] is True and nurture.is_enrolled(EMAIL, store)


# ------------------------------------------------------------ cadence guard
def _spy_send(monkeypatch):
    sends = []
    real = cadence._send

    def spy(*a, **k):
        sends.append(a)
        return real(*a, **k)

    monkeypatch.setattr(cadence, "_send", spy)
    return sends


def test_an_armed_enrolled_lead_is_stopped_with_reason_nurture_and_nothing_sends(store, monkeypatch):
    state = cadence.arm(make_state(), ARMED)
    nurture.enroll(EMAIL, "not_now_reply", ct(2026, 9, 22, 8, 0), store=store)
    sends = _spy_send(monkeypatch)
    inst = Recorder()
    ghl = Recorder()
    pings = []
    now = ct(2026, 9, 22, 10, 0)  # D1 due
    res = cadence.tick_lead(state, now, store=store, instantly=inst, ghl=ghl,
                            free_slots=cadence.default_slot_grid(now), notify_fn=lambda *a, **k: pings.append(a))
    assert res["action"] == "stopped" and res["reason"] == "nurture"
    assert state.cadence["stopped_reason"] == "nurture"
    assert state.cadence["stopped_at"] == now.isoformat()
    assert state.cadence["next_send_at"] is None
    assert state.cadence["needs_fresh_draft"] is False
    assert state.cadence["touches"] == []
    assert sends == [] and inst.calls == [] and ghl.calls == [] and pings == []
    # the next tick sees an already-stopped ladder and still sends nothing
    again = cadence.tick_lead(state, ct(2026, 9, 23, 10, 0), store=store, instantly=inst, ghl=ghl,
                              free_slots=cadence.default_slot_grid(now), notify_fn=lambda *a, **k: pings.append(a))
    assert again["action"] == "already_stopped" and again["reason"] == "nurture"
    assert sends == [] and inst.calls == [] and pings == []


def test_the_guard_reads_the_shared_store_when_none_is_passed():
    state = cadence.arm(make_state(), ARMED)
    nurture.enroll(EMAIL, "no_reply_after_sequence", ct(2026, 9, 22, 8, 0))  # default store
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=None, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "stopped" and res["reason"] == "nurture"
    assert state.cadence["stopped_reason"] == "nurture"


def test_the_guard_matches_the_email_case_insensitively(store):
    state = cadence.arm(make_state(email="Tiffany@FlowerhillFS.com"), ARMED)
    nurture.enroll(EMAIL, "no_reply_after_sequence", ct(2026, 9, 22, 8, 0), store=store)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["reason"] == "nurture"


def test_dry_run_reports_the_stop_without_mutating(store):
    state = cadence.arm(make_state(), ARMED)
    nurture.enroll(EMAIL, "not_now_reply", ct(2026, 9, 22, 8, 0), store=store)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=store, dry_run=True, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "stopped" and res["reason"] == "nurture"
    assert not state.cadence.get("stopped_reason")


def test_an_unreadable_nurture_record_holds_the_lead(store, monkeypatch):
    state = cadence.arm(make_state(), ARMED)
    sends = _spy_send(monkeypatch)

    def boom(*a, **k):
        raise IOError("store down")

    monkeypatch.setattr(nurture, "is_enrolled", boom)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "error" and "nurture" in res["error"]
    assert sends == [] and state.cadence["touches"] == []


def test_the_guard_holds_in_live_mode_too(store, live_mode, tmp_env, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        return httpx.Response(200, json={"id": "x", "from_address_email": EMAIL})

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    state = cadence.arm(make_state(), ARMED)
    state.cadence["day"] = 2
    now = ct(2026, 9, 24, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    nurture.enroll(EMAIL, "no_show_no_rebook", ct(2026, 9, 24, 9, 0), store=store)
    res = cadence.tick_lead(state, now, store=store, instantly=inst, free_slots=cadence.default_slot_grid(now),
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "stopped" and res["reason"] == "nurture"
    assert calls == []


def test_an_auto_reply_pause_is_not_resumed_for_an_enrolled_lead(store):
    state = cadence.arm(make_state(), ARMED)
    state.cadence["stopped_reason"] = "inbound_reply"
    state.cadence["next_send_at"] = None
    state.history = [{"event": "inbound", "label": "ooo", "email_id": "e-ooo", "at": "2026-09-22T08:00:00-05:00"}]
    assert cadence.is_auto_reply_pause(state)
    nurture.enroll(EMAIL, "not_now_reply", ct(2026, 9, 22, 9, 0), store=store)
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[])
    assert res["action"] == "stopped" and res["reason"] == "nurture"
    assert state.cadence["stopped_reason"] == "nurture" and state.cadence["next_send_at"] is None


def test_nurture_is_not_a_resumable_stop(store):
    assert "nurture" not in cadence.RESUMABLE_STOPS
    state = cadence.arm(make_state(), ARMED)
    nurture.enroll(EMAIL, "not_now_reply", ct(2026, 9, 22, 8, 0), store=store)
    cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[])
    assert state.cadence["stopped_reason"] == "nurture"
    out = cadence.resume_after_recipient_hold(state, ct(2026, 9, 22, 11, 0))
    assert out["resumed"] is False and state.cadence["stopped_reason"] == "nurture"


def test_resume_does_not_rearm_an_enrolled_lead(store):
    state = cadence.arm(make_state(), ARMED)
    nurture.enroll(EMAIL, "not_now_reply", ct(2026, 9, 22, 8, 0), store=store)
    cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[])
    before = json.loads(json.dumps(state.cadence))
    out = cadence.resume(state, ct(2026, 9, 22, 11, 0), store=store)
    assert out is state and state.cadence == before
    assert state.cadence["stopped_reason"] == "nurture" and not cadence.is_armed(state)
    # resume with the default store refuses too
    nurture.enroll(EMAIL, "not_now_reply", ct(2026, 9, 22, 8, 0))
    cadence.resume(state, ct(2026, 9, 22, 11, 0))
    assert state.cadence == before


def test_resume_still_rearms_a_lead_that_is_not_enrolled(store):
    state = cadence.arm(make_state(), ARMED)
    cadence.stop(state, "inbound_reply", ct(2026, 9, 22, 8, 0))
    cadence.resume(state, ct(2026, 9, 22, 11, 0), store=store)
    assert cadence.is_armed(state) and state.cadence["stopped_reason"] is None


def test_a_lead_that_is_not_enrolled_is_unaffected(store):
    other = "someone@else.com"
    nurture.enroll(other, "not_now_reply", ct(2026, 9, 22, 8, 0), store=store)  # a different lead
    state = cadence.arm(make_state(), ARMED)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "would_send" and res["day"] == 1
    assert not state.cadence.get("stopped_reason")


def test_an_ended_enrollment_does_not_stop_the_ladder(store):
    store.set(nurture.nurture_key(EMAIL), {"lead_email": EMAIL, "status": "ended", "events": []})
    state = cadence.arm(make_state(), ARMED)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "would_send"
