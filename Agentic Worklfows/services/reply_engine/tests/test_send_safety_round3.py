"""Send-safety round 3: the reviewer-max follow-up list, as regression tests.

1. A booking-holding card confirms the booked call (GHL invite, reminder
   ladder) only when the words it sends name exactly the booked time. Offering
   other times releases the call silently and reserves the new times; naming
   no time, or the booked time and others, blocks the send. Edit warns first.
2. An owned booking whose time has passed is never confirmed: nothing is
   sent, the card goes stale, the call is released silently, Lorenzo is told.
3. A cancel escalated to "BY HAND" clears: a signed "I cancelled it" action,
   hourly retries after the escalation, and GHL "already cancelled / not
   found" counted as done.
4. Overlapping cancel retries never resurrect a cancelled booking.
5. The card note follows the settlement rule and never states an outcome
   before it happens; a failed settlement is written back onto the card.
6. D1 timing: sub-minute jitter, the real send time in the push, and a
   window that would land on another day re-opens on that day.
7. Classification-time bookings report "booked, pipeline update failed".
8. runbooks/reply_engine_alerts.md covers the operator steps.

Scenarios come from the reviewer's probes (scratchpad/review-s/test_r2_*).
Every client is an in-process fake or a MockTransport that fails on any
request; live-mode tests set MODE=live in-process only.
"""
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from shared import notify
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine import show_rate
from services.reply_engine.models import LeadState, ReplyEvent

from test_send_safety_round2 import (  # noqa: F401 - shared fakes and worlds from round 2
    APPT, CAMPAIGN, D1_FREE, FRI, LOCKED_IN, OTHER_TIMES, REPLIES, SOPIO, SOPIO_KEY, THU_3PM, Failing,
    FakeInstantly, Recorder, _alerts, _card, _d1_state, _email_leg, _ghl_event, _go_live, _go_shadow,
    _process, _prospect_facing, _save_card, _tick, _tick_ghl, _world, ct, env, fixture_item, job,
    webhook_payload,
)

REPO = Path(__file__).resolve().parents[3]
FRI_1PM = "2026-09-25T13:00:00-05:00"


def _move_appointment(st, state_key, new_id):
    """Give a shadow booking a real GHL id, as a live booking would have."""
    raw = st.get(state_key)
    old = raw["cadence"]["booking"]["appointment_id"]
    for key in st.keys("showrate:%s:" % old):
        rec = st.get(key)
        st.delete(key)
        st.set(key.replace(old, new_id), rec)
    hold = st.get(show_rate.hold_key(old))
    st.delete(show_rate.hold_key(old))
    st.set(show_rate.hold_key(new_id), hold)
    raw["cadence"]["booking"]["appointment_id"] = new_id
    st.set(state_key, raw)
    # ...and the slot reservation booking.register_booking wrote under it
    offered = st.get(A.OFFERED_KEY) or []
    st.set(A.OFFERED_KEY, [dict(r, approval="booking:%s" % new_id) if r.get("approval") == "booking:%s" % old else r
                           for r in offered])
    # ...and the engine intent recorded when the card took the booking
    for key in st.keys(A.BOOKING_INTENT_PREFIX):
        rec = st.get(key) or {}
        if rec.get("appointment_id") == old:
            st.set(key, dict(rec, appointment_id=new_id))


def _armed_touches(st, appointment_id):
    out = []
    for key in st.keys("showrate:%s:" % appointment_id):
        rec = st.get(key) or {}
        if rec.get("held") or rec.get("cancelled"):
            continue
        out += [t for t in rec.get("touches", []) if not t.get("skipped")]
    return out


def _ghl_statuses(ghl):
    return [(c[1], c[2]) for c in ghl.named("update_appointment_status")]


# ================================== 1. edited booking-holding card, live
# Round 4 (Lorenzo's decision): an edit to a card that holds a booking must
# carry an explicit Keep / Release choice; the words never decide. The full
# choice matrix is in test_send_safety_round4.py.
def _sopio_confirm_card(env):
    r = _process(env, webhook_payload(SOPIO, "2026-09-21T17:37"), ct(2026, 9, 21, 16, 0))
    assert r["draft"]["label"] == "booking_confirmation"
    assert env["store"].get(SOPIO_KEY)["cadence"]["booking"]["owner"] == r["approval_token"].split(".")[0]
    _move_appointment(env["store"], SOPIO_KEY, "appt-live-9")
    return r


def _assert_released_not_confirmed(st, ghl, inst, appointment_id, body_fragment):
    assert _ghl_statuses(ghl) == [((appointment_id, "cancelled"), {"to_notify": False})]   # never "confirmed"
    assert len(inst.sent) == 1 and body_fragment in inst.sent[0]["body"]
    raw = st.get(SOPIO_KEY)
    assert "booking" not in raw["cadence"] and raw["cadence"]["booking_cancelled"]["reason"] == "released_on_edit"
    assert not show_rate.is_held(st, appointment_id) and _armed_touches(st, appointment_id) == []
    assert THU_3PM not in A.offered_slots(st, ct(2026, 9, 21, 16, 20))   # the call's slot is free again


def test_live_edited_booking_confirmation_released_by_choice_reserves_the_new_time(env, monkeypatch):
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    link = A.load(r["approval_token"], st).draft.booking_link
    body = ("Hey Sopio,\n\nThursday at 3 just got taken on my side, sorry. Could you do Fri 1:00pm CT instead? "
            "Or grab any time here: %s\n\nLorenzo" % link)
    ed = A.edit(r["approval_token"], body, store=st, now=ct(2026, 9, 21, 16, 10), booking_choice="release")
    assert ed["ok"] and ed["offered_slots"] == [FRI_1PM] and ed["booking_choice"] == "release"
    assert FRI_1PM in A.offered_slots(st, ct(2026, 9, 21, 16, 10))          # the time written is reserved
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(ed["token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    assert out["ok"] and out["invite"] is None and out["show_rate"] is None
    _assert_released_not_confirmed(st, ghl, inst, "appt-live-9", "Fri 1:00pm")
    tick_ghl = _tick_ghl()
    _tick(st, tick_ghl, _ghl_event(appointment_id="appt-live-9", status="cancelled"), ct(2026, 9, 23, 15, 5),
          appointment_id="appt-live-9")
    assert _prospect_facing(tick_ghl) == []


def test_live_edited_hand_over_owner_card_released_by_choice(env, monkeypatch):
    st = env["store"]
    _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), ct(2026, 9, 21, 15, 30))
    _process(env, webhook_payload(SOPIO, "2026-09-21T17:37"), ct(2026, 9, 21, 16, 0))
    # "Actually, could we do Friday" is sent at 16:25 CT, after the booking
    # reply (12:37 CT). The borrowed fixture's own time (9:42 CT) made it a
    # reply sent BEFORE that one, and round 4 holds a card answering a reply
    # the lead has since written past (approval.lead_replies_after compares
    # send times, not processing order).
    third = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42", email_id="sopio-fri",
                                          reply_text="Actually, could we do Friday at 1pm instead?",
                                          timestamp="2026-09-21T21:25:00.000Z"),
                     ct(2026, 9, 21, 16, 30))
    assert third["booking_handoff"]["action"] == "transferred"
    _move_appointment(st, SOPIO_KEY, "appt-live-7")
    _go_live(monkeypatch)
    link = A.load(third["approval_token"], st).draft.booking_link
    body = "Hey Sopio,\n\nFriday works better for me too. How about Fri 1:00pm CT? Or grab any time here: %s\n\nLorenzo" % link
    ed = A.edit(third["approval_token"], body, store=st, now=ct(2026, 9, 21, 16, 40), booking_choice="release")
    assert ed["ok"] and ed["offered_slots"] == [FRI_1PM]
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(ed["token"], inst, store=st, now=ct(2026, 9, 21, 16, 41), ghl=ghl)
    assert out["ok"] and out["invite"] is None
    _assert_released_not_confirmed(st, ghl, inst, "appt-live-7", "Fri 1:00pm")


def test_owner_card_released_by_choice_but_claiming_an_invite_is_blocked(env, monkeypatch):
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    link = A.load(r["approval_token"], st).draft.booking_link
    ed = A.edit(r["approval_token"], "Hey Sopio,\n\nCould you do Fri 1:00pm CT instead? Invite on the way. %s"
                                     "\n\nLorenzo" % link, store=st, now=ct(2026, 9, 21, 16, 10), booking_choice="release")
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(ed["token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    assert out["status"] == "blocked" and inst.sent == [] and ghl.calls == []


def test_live_unedited_owner_card_still_confirms(env, monkeypatch):
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(r["approval_token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    assert out["ok"] and out["invite"]["released"] is True
    assert _ghl_statuses(ghl) == [(("appt-live-9", "confirmed"), {"to_notify": True})]
    assert not show_rate.is_held(st, "appt-live-9")
    assert st.get(SOPIO_KEY)["cadence"]["booking"]["awaiting_approval"] is False


# ======================================= 2. a passed booking is never confirmed
def _rob_card(env):
    st = env["store"]
    rob = sorted([r for r in REPLIES if r["from_address_email"] == "rob@cjsglobal.com"],
                 key=lambda r: r["timestamp_created"])
    res = None
    for r in rob:
        now = ct(2026, 9, 17, 9, 0) if res is None else ct(2026, 9, 17, 9, 5)
        env["clock"]["now"] = now
        res = app_mod.process_event(ReplyEvent.from_poller_item(r), deps=env["deps"], now=now, busy_blocks=[])
    assert st.get(res["state_key"])["cadence"]["booking"]["slot"] == "2026-09-18T13:00:00-05:00"
    _move_appointment(st, res["state_key"], "appt-live-rob")
    return res


def test_live_rob_card_approved_after_his_call_time_sends_nothing_and_releases_silently(env, monkeypatch):
    st = env["store"]
    res = _rob_card(env)
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender="rob@cjsglobal.com")
    out = A.approve(res["approval_token"], inst, store=st, now=ct(2026, 9, 18, 15, 0), ghl=ghl)
    assert out["ok"] is False and out["status"] == "stale_slots"
    assert inst.sent == []
    assert _ghl_statuses(ghl) == [(("appt-live-rob", "cancelled"), {"to_notify": False})]
    assert _alerts("Call time passed before approval")
    raw = st.get(res["state_key"])
    assert "booking" not in raw["cadence"] and raw["cadence"]["booking_cancelled"]["reason"] == "passed_before_approval"
    assert _armed_touches(st, "appt-live-rob") == []
    # a retry puts it back in front of Lorenzo, but it still cannot be sent unedited
    assert A.retry(res["approval_token"], store=st, now=ct(2026, 9, 18, 15, 5))["ok"]
    again = A.approve(res["approval_token"], inst, store=st, now=ct(2026, 9, 18, 15, 6), ghl=ghl)
    assert again["ok"] is False and inst.sent == []


def test_live_owner_card_queued_after_hours_and_flushed_after_the_call_sends_nothing(tmp_env, monkeypatch):
    fri_1pm = "2026-09-18T13:00:00-05:00"
    store, state = _world(tmp_env, monkeypatch, slot=fri_1pm)
    card = _card(state, "card2", "Hey Sopio,\n\nYou are locked in for Fri 1:00pm CT.\n\nLorenzo", [fri_1pm],
                 created=ct(2026, 9, 18, 9, 0))
    card.expires_at = ct(2026, 9, 21, 12, 0).isoformat()      # a TTL that outlives the weekend
    card.token = A.make_token("card2", state.key, A.draft_hash(card.draft), card.expires_at)
    _save_card(store, card)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    q = A.approve(card.token, inst, store=store, now=ct(2026, 9, 18, 19, 30), ghl=Recorder())
    assert q["status"] == "approved_queued"
    ghl = Recorder()
    flushed = A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 7, 0), ghl=ghl)
    assert flushed and flushed[0]["status"] == "stale_slots"
    assert inst.sent == [] and _ghl_statuses(ghl) == [((APPT, "cancelled"), {"to_notify": False})]
    assert not show_rate.is_held(store, APPT) and _armed_touches(store, APPT) == []


# ============================================= 3. "I cancelled it" + GHL gone
def _escalated(tmp_env, monkeypatch, name="store.json"):
    store, state = _world(tmp_env, monkeypatch, name=name)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    bad = Recorder(fail={"update_appointment_status"})
    A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                ghl=bad, instantly=inst, old_owner="card2")
    store.set(state.key, state.to_store())
    for minute in range(5, 35, 5):
        A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 16, 40) + timedelta(minutes=minute), ghl=bad)
    assert len(_alerts("BY HAND")) == 1
    return store, state, inst


def test_by_hand_alert_carries_a_signed_i_cancelled_it_link_that_finishes_the_cleanup(tmp_env, monkeypatch):
    store, state, inst = _escalated(tmp_env, monkeypatch)
    alert = _alerts("BY HAND")[0]
    assert alert["priority"] == "urgent" and "I cancelled it" in alert["message"]
    assert "keeps retrying once an hour" in alert["message"]
    url = alert["click"]
    assert url.startswith("https://engine.test/booking/cancelled/")
    assert _alerts("Call NOT cancelled")[0]["click"].startswith("https://engine.test/booking/cancelled/")

    ghl, fresh_inst = Recorder(), FakeInstantly(sender=SOPIO)
    app_mod.configure(store=store, ghl=ghl, instantly=fresh_inst, clock=lambda: ct(2026, 9, 21, 17, 30))
    client = TestClient(app_mod.app)
    path = url[len("https://engine.test"):]
    bare = urlparse(path).path
    appt = parse_qs(urlparse(path).query)["a"][0]
    try:
        page = client.get(path)
        assert page.status_code == 200 and "I cancelled it" in page.text
        assert store.get(state.key)["cadence"]["booking"]["cancel_failed"]          # GET changes nothing
        assert client.post("%s?a=%s" % (bare, appt)).status_code == 403            # unsigned
        assert client.post("%s?a=%s&t=2026-09-30T00:00:00-05:00.deadbeef" % (bare, appt)).status_code == 403
        assert client.post("%s?a=other-appt&t=%s" % (bare, parse_qs(urlparse(path).query)["t"][0])).status_code == 403
        ok = client.post(path)
        assert ok.status_code == 200 and "Cleanup done" in ok.text
        assert client.post(path).status_code == 400                                 # already done
    finally:
        app_mod.configure()
    assert ghl.calls == []                                                           # GHL never called
    raw = store.get(state.key)
    assert "booking" not in raw["cadence"] and raw["cadence"]["booking_cancelled"]["reason"] == "cancelled_by_hand"
    # Lorenzo's word is not the engine seeing the cancel: the reminders stay
    # held (nothing is sent even if the event is still live) until the call has passed
    assert show_rate.is_held(store, APPT) and store.keys("showrate:%s:" % APPT)
    assert store.get(A.CANCEL_RETRY_PREFIX + state.key) is None
    # ...and the booked time stays reserved with the hold (round-4 note: it was
    # freed at once while the event might still be live)
    assert THU_3PM in A.offered_slots(store, ct(2026, 9, 21, 17, 30))
    assert not A.cancel_pending(LeadState.from_store(raw))
    assert fresh_inst.interest == [(SOPIO, CAMPAIGN, 1)]
    tick_ghl = _tick_ghl()
    for when in (ct(2026, 9, 21, 17, 40), ct(2026, 9, 23, 15, 5), ct(2026, 9, 24, 11, 5)):
        _tick(store, tick_ghl, _ghl_event(), when)                                  # the event is still live
    assert _prospect_facing(tick_ghl) == []
    # nothing left to retry; after the call the kept hold is torn down
    later = Recorder()
    A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 19, 0), ghl=later)
    assert later.calls == [] and show_rate.is_held(store, APPT)
    assert THU_3PM in A.offered_slots(store, ct(2026, 9, 21, 17, 30))
    A.flush_queued(inst, store=store, now=ct(2026, 9, 24, 16, 30), ghl=later)
    assert later.calls == [] and not show_rate.is_held(store, APPT) and store.keys("showrate:%s:" % APPT) == []
    assert THU_3PM not in A.offered_slots(store, ct(2026, 9, 21, 17, 30))      # given back with the hold


def test_an_escalated_cancel_keeps_retrying_hourly_and_clears_when_ghl_recovers(tmp_env, monkeypatch):
    store, state, inst = _escalated(tmp_env, monkeypatch)
    ghl = Recorder()
    A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 17, 30), ghl=ghl)     # < 1 h since the escalation
    assert ghl.calls == []
    A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 18, 15), ghl=ghl)
    assert _ghl_statuses(ghl) == [((APPT, "cancelled"), {"to_notify": False})]
    raw = store.get(state.key)
    assert "booking" not in raw["cadence"] and store.get(A.CANCEL_RETRY_PREFIX + state.key) is None


@pytest.mark.parametrize("reread", ["404", "410", "cancelled"])
def test_a_404_confirmed_by_a_re_read_counts_as_gone_but_keeps_the_hold_until_the_call(tmp_env, monkeypatch, reread):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)

    def cancel(*a, **k):
        raise RuntimeError("GHL PUT calendars/events/appointments/appt-live-1 -> HTTP 404: appointment not found")

    def read(*a, **k):
        if reread == "cancelled":
            return {"appointment": {"id": APPT, "appointmentStatus": "cancelled"}}
        raise RuntimeError("GHL GET calendars/events/appointments/appt-live-1 -> HTTP %s: gone" % reread)

    ghl = Recorder(returns={"update_appointment_status": cancel, "get_appointment": read})
    inst = FakeInstantly(sender=SOPIO)
    out = A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                      ghl=ghl, instantly=inst, old_owner="card2")
    assert out["action"] == "released" and out["cancelled"]["note"] == "already_gone"
    assert "booking" not in state.cadence and store.get(A.CANCEL_RETRY_PREFIX + state.key) is None
    assert show_rate.is_held(store, APPT)                             # kept: the engine did not see it cancel
    assert out["cancelled"]["teardown_deferred_until"] == ct(2026, 9, 24, 16, 0).isoformat()
    A.flush_queued(inst, store=store, now=ct(2026, 9, 24, 16, 20), ghl=Recorder())
    assert not show_rate.is_held(store, APPT) and store.keys("showrate:%s:" % APPT) == []


@pytest.mark.parametrize("error,status", [
    ("GHL PUT x -> HTTP 404: not found", 404),
    ("GHL PUT x -> HTTP 500: internal error", 500),
    ("GHL 422: appointment already cancelled", None),
    ("appointment has been deleted", None),
])
def test_only_the_http_status_is_read_never_the_message(error, status):
    assert A.http_status_of(RuntimeError(error)) == status


# ====================================================== 4. overlapping retries
def _pending_cancel(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                ghl=Recorder(fail={"update_appointment_status"}), instantly=inst, old_owner="card2")
    store.set(state.key, state.to_store())
    return store, state, inst


@pytest.mark.parametrize("worker1_error", ["GHL PUT x -> HTTP 422: appointment already cancelled",
                                           "GHL PUT x -> HTTP 500: boom"])
def test_overlapping_retries_never_resurrect_a_cancelled_booking(tmp_env, monkeypatch, worker1_error):
    store, state, inst = _pending_cancel(tmp_env, monkeypatch)
    worker2_ghl = Recorder()

    def worker1_cancel(*a, **k):
        # worker 2 runs start to finish while worker 1 waits on GHL
        A.retry_failed_cancels(store, worker2_ghl, inst, ct(2026, 9, 21, 16, 45, 1))
        assert "booking" not in store.get(state.key)["cadence"]
        raise RuntimeError(worker1_error)

    worker1_ghl = Recorder(returns={"update_appointment_status": worker1_cancel})
    A.retry_failed_cancels(store, worker1_ghl, inst, ct(2026, 9, 21, 16, 45, 0))
    raw = store.get(state.key)
    assert "booking" not in raw["cadence"] and raw["cadence"]["booking_cancelled"]["slot"] == THU_3PM
    assert not show_rate.is_held(store, APPT) and store.get(A.CANCEL_RETRY_PREFIX + state.key) is None
    assert inst.interest == [(SOPIO, CAMPAIGN, 1)]                                # undone exactly once
    for m in range(5, 65, 5):
        A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 16, 45) + timedelta(minutes=m),
                       ghl=Recorder(fail={"update_appointment_status"}))
    assert not _alerts("BY HAND") and "booking" not in store.get(state.key)["cadence"]


def test_a_retry_never_overwrites_a_lead_row_that_changed_under_it(tmp_env, monkeypatch):
    store, state, inst = _pending_cancel(tmp_env, monkeypatch)

    def slow_failure(*a, **k):
        # a new inbound reply lands while the retry waits on GHL
        store.mutate(state.key, lambda raw: dict(raw, last_email_id="new-reply-1",
                                                 history=list(raw.get("history") or []) + [{"event": "inbound"}]))
        raise RuntimeError("GHL PUT x -> HTTP 500: boom")

    A.retry_failed_cancels(store, Recorder(returns={"update_appointment_status": slow_failure}), inst,
                           ct(2026, 9, 21, 16, 45))
    raw = store.get(state.key)
    assert raw["last_email_id"] == "new-reply-1" and raw["history"][-1] == {"event": "inbound"}
    assert raw["cadence"]["booking"]["cancel_failed"]["attempts"] == 2


# =========================================================== 5. card notes
def test_a_released_past_booking_is_announced_as_being_released_and_the_restating_card_is_blocked(env):
    st = env["store"]
    for prefix, now in (("2026-09-18T15:08", ct(2026, 9, 18, 10, 10)), ("2026-09-18T15:25", ct(2026, 9, 18, 10, 27))):
        env["clock"]["now"] = now
        app_mod.process_event(ReplyEvent.from_poller_item(fixture_item("info@shiningarmorcleaningnj.com", prefix)),
                              deps=env["deps"], now=now, busy_blocks=[])
    item = dict(fixture_item("info@shiningarmorcleaningnj.com", "2026-09-21T19:00"))
    item["id"] = "ilmi-resched-1"
    item["text"] = "Hi Lorenzo,\n\nI have an emergency, please reschedule for this Wednesday at 1pm CT.\n"
    env["clock"]["now"] = ct(2026, 9, 21, 14, 2)
    r3 = app_mod.process_event(ReplyEvent.from_poller_item(item), deps=env["deps"], now=ct(2026, 9, 21, 14, 2),
                               busy_blocks=[])
    assert r3["booking_handoff"]["action"] == "released"
    rationale = r3["draft"]["rationale"]
    assert "is being released" in rationale and "takes over" not in rationale
    assert any("restates the call" in p for p in r3["draft"]["problems"])
    inst = FakeInstantly(sender="info@shiningarmorcleaningnj.com")
    out = A.approve(r3["approval_token"], inst, store=st, now=ct(2026, 9, 21, 14, 5))
    assert out["ok"] is False and inst.sent == []


def test_the_transfer_note_uses_the_same_rule_as_the_settlement(env):
    _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), ct(2026, 9, 21, 15, 30))
    _process(env, webhook_payload(SOPIO, "2026-09-21T17:37"), ct(2026, 9, 21, 16, 0))
    third = _process(env, webhook_payload(SOPIO, "2026-09-21T23:17"), ct(2026, 9, 21, 18, 20))
    assert third["booking_handoff"]["action"] == "transferred"
    assert "takes over the call" in third["draft"]["rationale"]
    assert A.will_transfer_booking(A.Draft(subject="x", body_text="x", offered_slots=[THU_3PM]), THU_3PM,
                                   ct(2026, 9, 21, 18, 20))
    assert not A.will_transfer_booking(A.Draft(subject="x", body_text="x", offered_slots=[THU_3PM]), THU_3PM,
                                       ct(2026, 9, 24, 15, 0))


def test_a_settlement_that_fails_is_written_back_onto_the_card(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _card(state, "card3", OTHER_TIMES, FRI)
    card.draft.rationale = "counter-proposal; the call is being released"
    _save_card(store, card)
    app_mod._note_settlement_outcome(store, card, {"action": "release_pending", "slot": THU_3PM})
    stored = A.load(card.token, store)                   # the token still verifies
    assert stored is not None and "UPDATE: GHL refused to cancel the call" in stored.draft.rationale
    app_mod._note_settlement_outcome(store, card, {"action": "released", "slot": THU_3PM})
    assert A.load(card.token, store).draft.rationale.count("UPDATE") == 1


# ============================================================ 6. D1 timing
def _d1_run(tmp_env, monkeypatch, times, name="d1.json"):
    store = JsonFileStore(tmp_env / name)
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    _go_live(monkeypatch)
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    state = _d1_state()
    pings = []
    nf = lambda *a, **k: pings.append((a, k)) or {"sent": True, "email": True}   # noqa: E731
    results = [cadence.tick_lead(state, when, store=store, instantly=inst, free_slots=D1_FREE, notify_fn=nf)
               for when in times]
    return state, results, pings, inst


def test_sub_minute_jitter_never_moves_the_d1_send_an_hour(tmp_env, monkeypatch):
    state, res, pings, inst = _d1_run(tmp_env, monkeypatch, [ct(2026, 9, 22, 9, 30, 5), ct(2026, 9, 22, 10, 0, 3)])
    assert res[0]["action"] == "veto_window_opened" and "sends at Tue 10:00am CT" in pings[0][0][0]
    assert res[1]["action"] == "sent" and len(inst.sent) == 1


def test_a_window_that_would_open_at_18_is_deferred_and_reopens_next_morning_with_a_fresh_link(tmp_env, monkeypatch):
    times = [ct(2026, 9, 22, 18, 0), ct(2026, 9, 22, 19, 0), ct(2026, 9, 23, 7, 0), ct(2026, 9, 23, 9, 30)]
    state, res, pings, inst = _d1_run(tmp_env, monkeypatch, times)
    assert res[0]["action"] == "not_due" and res[0]["reason"] == "veto_window_deferred"
    assert state.cadence["next_send_at"] == ct(2026, 9, 23, 10, 0).isoformat()
    assert [r["action"] for r in res[1:3]] == ["not_due", "not_due"]
    assert res[3]["action"] == "veto_window_opened" and len(pings) == 1
    title, kw = pings[0][0][0], pings[0][1]
    assert "sends at Wed 10:00am CT" in title
    token = parse_qs(urlparse(kw["click"]).query)["t"][0]
    assert cadence.verify_decision_token("veto", state, token, ct(2026, 9, 23, 10, 0)) is True
    assert inst.sent == []


def test_a_friday_evening_window_is_deferred_to_monday_so_the_link_is_live_at_the_send(tmp_env, monkeypatch):
    state = _d1_state()
    state.cadence["next_send_at"] = ct(2026, 9, 25, 10, 0).isoformat()         # Friday's D1, held all day
    times = [ct(2026, 9, 25, 18, 0), ct(2026, 9, 28, 9, 30)]
    store = JsonFileStore(tmp_env / "fri.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    _go_live(monkeypatch)
    pings = []
    res = [cadence.tick_lead(state, when, store=store, instantly=FakeInstantly(sender="x"), free_slots=D1_FREE,
                             notify_fn=lambda *a, **k: pings.append((a, k)) or {"sent": True, "email": True})
           for when in times]
    assert res[0]["reason"] == "veto_window_deferred"
    assert state.cadence["next_send_at"] == ct(2026, 9, 28, 10, 0).isoformat()
    assert res[1]["action"] == "veto_window_opened" and "sends at Mon 10:00am CT" in pings[0][0][0]
    token = parse_qs(urlparse(pings[0][1]["click"]).query)["t"][0]
    assert cadence.verify_decision_token("veto", state, token, ct(2026, 9, 28, 10, 0)) is True


def test_an_expired_veto_link_reopens_the_window_with_a_fresh_one(tmp_env, monkeypatch):
    state = _d1_state()
    state.cadence["veto_notified_at"] = ct(2026, 9, 22, 9, 30).isoformat()
    state.cadence["next_send_at"] = ct(2026, 9, 24, 10, 0).isoformat()          # the send slipped two days
    store = JsonFileStore(tmp_env / "exp.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    _go_live(monkeypatch)
    pings = []
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    r = cadence.tick_lead(state, ct(2026, 9, 24, 9, 30), store=store, instantly=inst, free_slots=D1_FREE,
                          notify_fn=lambda *a, **k: pings.append((a, k)) or {"sent": True, "email": True})
    assert r["action"] == "veto_window_opened" and inst.sent == [] and len(pings) == 1
    assert state.cadence["veto_notified_at"] == ct(2026, 9, 24, 9, 30).isoformat()


@pytest.mark.parametrize("at,expected", [
    (ct(2026, 9, 22, 10, 0), ct(2026, 9, 22, 10, 0)),
    (ct(2026, 9, 22, 14, 30), ct(2026, 9, 22, 15, 0)),
    (ct(2026, 9, 22, 18, 30), ct(2026, 9, 23, 10, 0)),
    (ct(2026, 9, 22, 8, 0), ct(2026, 9, 22, 10, 0)),
    (ct(2026, 9, 25, 19, 0), ct(2026, 9, 28, 10, 0)),
    (ct(2026, 9, 26, 12, 0), ct(2026, 9, 28, 10, 0)),
])
def test_projected_send_time_is_the_first_tick_that_may_send(at, expected):
    assert cadence.projected_send_time(at) == expected


# ================================= 7. classification-time pipeline errors
def test_a_classification_booking_whose_pipeline_update_failed_says_so_on_the_card_and_alerts(env):
    st = env["store"]
    ghl = Recorder(fail={"update_opportunity_stage", "upsert_opportunity"},
                   returns={"create_appointment": {"id": "appt-class-1"}, "upsert_contact": {"contact": {"id": "c-1"}},
                            "get_free_slots": {}, "get_calendar_events": {"events": []},
                            "list_appointments": []})
    deps = app_mod.configure(store=st, ghl=ghl, instantly=FakeInstantly(sender=SOPIO),
                             clock=lambda: ct(2026, 9, 21, 16, 0))
    r = app_mod.process_event(ReplyEvent.from_webhook(webhook_payload(SOPIO, "2026-09-21T17:37")), deps=deps,
                              now=ct(2026, 9, 21, 16, 0), busy_blocks=[])
    booking = st.get(SOPIO_KEY)["cadence"]["booking"]
    assert booking["pipeline_errors"] and booking["appointment_id"] == "appt-class-1"
    assert "BOOKED, PIPELINE UPDATE FAILED" in r["draft"]["rationale"]
    assert _alerts("Booked, pipeline update failed")
    assert show_rate.is_held(st, "appt-class-1")


# ================================================================ 8. runbook
def test_the_alert_runbook_covers_every_operator_step_without_em_dashes():
    text = (REPO / "runbooks" / "reply_engine_alerts.md").read_text(encoding="utf-8")
    for heading in ("Call NOT cancelled", "BY HAND", "I cancelled it", "Resume", "Booked, pipeline update failed",
                    "no BASE_URL"):
        assert heading in text, heading
    for section in text.split("\n## ")[1:]:
        assert "**What you see.**" in section and "**What it means.**" in section and "**What to do.**" in section
    assert "—" not in text and "–" not in text
