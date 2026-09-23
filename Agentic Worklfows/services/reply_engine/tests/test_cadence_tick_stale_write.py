"""The hourly cadence tick writes the lead row back as a merge, never as the
whole copy it read (defect 3's last writer, and SAL-4: "a tick can erase a
reply's stop and D2 goes out anyway").

A reply pipeline and the cancel retry both write the lead row without the
tick's lock. Whichever order they land in while a tick is working, the stop
and the settled booking survive the tick's write, and no follow-up day goes
out on top of a reply.

Live mode is monkeypatched in-process only; every client is a fake and the
real Instantly/GHL clients sit on a transport that fails any request.
"""
import httpx
import pytz

from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore

from jobs import cadence_tick as cadence_job
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine import show_rate
from services.reply_engine.models import LeadState, ReplyEvent

from test_send_safety_round2 import (  # noqa: F401 - shared fakes, worlds and the env fixture
    APPT, CAMPAIGN, FRI, OTHER_TIMES, SOPIO, Failing, FakeInstantly, Recorder, _card, _go_live, _go_shadow, _world,
    ct, webhook_payload,
)
from test_send_safety_round3 import _ghl_statuses

ARMED_AT = ct(2026, 9, 21, 16, 0)
FREE = ["2026-09-24T13:00:00-05:00", "2026-09-25T14:00:00-05:00", "2026-09-28T13:00:00-05:00",
        "2026-09-29T14:00:00-05:00", "2026-09-30T13:00:00-05:00", "2026-10-01T14:00:00-05:00"]


def _nf(pings):
    return lambda *a, **k: pings.append(a[0]) or {"sent": True, "email": True}   # noqa: E731


def _sopio_ladder(store, day_done=0):
    """Sopio, armed Mon 16:00, answering her own thread. ``day_done=1`` puts
    her D2 due Wed 23rd 10:00."""
    state = cadence.arm(LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN, status="positive_question",
                                  first_name="Sopio", company="Taxfo Accounting", eaccount="lorenzov@theadvero.com",
                                  thread_id="thr-sopio", last_email_id="e-sopio", last_subject="Re: Sopio, question"),
                        ARMED_AT)
    if day_done:
        state.cadence["day"] = day_done
        state.cadence["next_send_at"] = ct(2026, 9, 23, 10, 0).isoformat()
    else:
        state.cadence["veto_notified_at"] = ct(2026, 9, 22, 9, 30).isoformat()
    store.set(state.key, cadence.state_to_dict(state))
    return state


def _real_reply(store, monkeypatch, when, email_id):
    """Sopio's question ("What is your percentage?") through the real
    pipeline (shadow, failing transports), exactly as the webhook would run
    it, stamped at ``when``. A question books nothing, so the stop it leaves
    is the plain inbound_reply stop SAL-4 is about."""
    _go_shadow(monkeypatch)
    t = httpx.MockTransport(Failing())
    deps = app_mod.configure(store=store, ghl=GHL(token=None, transport=t), instantly=Instantly(api_key="x", transport=t))
    stamp = when.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    try:
        app_mod.process_event(ReplyEvent.from_webhook(webhook_payload(SOPIO, "2026-09-21T14:42", email_id=email_id,
                                                                      timestamp=stamp)),
                              deps=deps, now=when, busy_blocks=[])
    finally:
        app_mod.configure()
        _go_live(monkeypatch)


def _assert_reply_stop_kept(raw, email_id):
    cad = raw["cadence"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    assert cad["next_send_at"] is None
    assert email_id in raw["processed_email_ids"]            # the pipeline's own fields survived too


def _later_ticks_send_nothing(store, inst, pings):
    before = len(inst.sent)
    for when in (ct(2026, 9, 23, 10, 0), ct(2026, 9, 23, 11, 0), ct(2026, 9, 24, 10, 0), ct(2026, 9, 25, 10, 0)):
        cadence_job.run(when, store, inst, None, free_slots=FREE, notify_fn=_nf(pings), log_fn=lambda *a, **k: None)
    assert len(inst.sent) == before


# ================================================ reply before the tick's send
def test_a_reply_that_lands_after_the_tick_read_the_row_withholds_d2_and_keeps_the_stop(tmp_env, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    store = JsonFileStore(tmp_env / "s1.json")
    state = _sopio_ladder(store, day_done=1)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    real_build = cadence.build_touch
    fired = {}

    def reply_mid_tick(*a, **k):
        # the tick has read the row and is building D2; Sopio's reply is
        # processed right now, before the POST
        if not fired:
            fired["x"] = True
            _real_reply(store, monkeypatch, ct(2026, 9, 23, 10, 5), "sopio-mid-tick")
            assert store.get(state.key)["cadence"]["stopped_reason"] == "inbound_reply"
        return real_build(*a, **k)

    monkeypatch.setattr(cadence, "build_touch", reply_mid_tick)
    pings = []
    summary = cadence_job.run(ct(2026, 9, 23, 10, 5), store, inst, None, free_slots=FREE, notify_fn=_nf(pings),
                              log_fn=lambda *a, **k: None)
    monkeypatch.setattr(cadence, "build_touch", real_build)
    assert fired
    r = summary["results"][0]
    assert r["action"] == "stopped" and r["reason"] == "changed_while_ticking:inbound_reply" and r["day"] == 2
    assert inst.sent == []                                   # D2 never went out
    assert store.get(cadence.touch_marker_key(state, 2)) is None
    raw = store.get(state.key)
    _assert_reply_stop_kept(raw, "sopio-mid-tick")
    assert raw["cadence"]["day"] == 1 and not raw["cadence"].get("touches")
    _later_ticks_send_nothing(store, inst, pings)


# ================================== reply after the tick's send, before its write
def test_a_reply_that_lands_between_the_send_and_the_write_is_not_erased_so_no_d2_follows(tmp_env, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    store = JsonFileStore(tmp_env / "s2.json")
    state = _sopio_ladder(store, day_done=0)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    real_send = cadence._send
    fired = {}

    def send_then_reply(*a, **k):
        out = real_send(*a, **k)
        if not fired:
            fired["x"] = True
            _real_reply(store, monkeypatch, ct(2026, 9, 22, 10, 1), "sopio-after-d1")
        return out

    monkeypatch.setattr(cadence, "_send", send_then_reply)
    pings = []
    summary = cadence_job.run(ct(2026, 9, 22, 10, 0), store, inst, None, free_slots=FREE, notify_fn=_nf(pings),
                              log_fn=lambda *a, **k: None)
    monkeypatch.setattr(cadence, "_send", real_send)
    assert fired and summary["results"][0]["action"] == "sent" and len(inst.sent) == 1
    raw = store.get(state.key)
    _assert_reply_stop_kept(raw, "sopio-after-d1")
    # ...while the tick's own record of D1 still landed
    assert raw["cadence"]["day"] == 1 and len(raw["cadence"]["touches"]) == 1
    assert len(raw["offered_slots"]) >= 2
    _later_ticks_send_nothing(store, inst, pings)            # no D2, on any later tick


# ================================================ retry between read and write
def _booked_ladder(tmp_env, monkeypatch, name):
    """Sopio's booking whose silent release cancel failed, on an armed ladder."""
    store, state = _world(tmp_env, monkeypatch, name=name)
    state.cadence = dict(cadence.arm(state, ARMED_AT).cadence)
    store.set(state.key, state.to_store())
    _go_live(monkeypatch)
    A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                ghl=Recorder(fail={"update_appointment_status"}), instantly=FakeInstantly(sender=SOPIO),
                                old_owner="card2")
    store.set(state.key, state.to_store())
    assert store.get(state.key)["cadence"]["booking"]["cancel_failed"]
    return store, state


def _assert_booking_settled(store, state):
    raw = store.get(state.key)
    booking = raw["cadence"].get("booking") or {}
    assert booking.get("appointment_id") != APPT and not booking.get("cancel_failed")
    assert raw["cadence"]["booking_cancelled"]["appointment_id"] == APPT
    assert store.get(A.CANCEL_RETRY_PREFIX + state.key) is None and not show_rate.is_held(store, APPT)
    assert not A.cancel_pending(LeadState.from_store(raw))
    return raw


def test_a_cancel_retry_that_finishes_mid_tick_is_not_undone_by_the_tick(tmp_env, monkeypatch):
    store, state = _booked_ladder(tmp_env, monkeypatch, "r1.json")
    ok_ghl = Recorder()
    inst = FakeInstantly(sender=SOPIO)
    real_tick = cadence.tick_lead
    fired = {}

    def retry_then_tick(st, now, **kw):
        # the tick has read the row (booking still cancel_failed); the */5
        # retry finishes the cancel before the tick writes back
        if not fired:
            fired["x"] = True
            A.retry_failed_cancels(store, ok_ghl, inst, ct(2026, 9, 22, 10, 0))
            assert "booking" not in store.get(state.key)["cadence"]
        return real_tick(st, now, **kw)

    monkeypatch.setattr(cadence, "tick_lead", retry_then_tick)
    summary = cadence_job.run(ct(2026, 9, 22, 10, 0), store, inst, None, free_slots=FREE, notify_fn=_nf([]),
                              log_fn=lambda *a, **k: None)
    monkeypatch.setattr(cadence, "tick_lead", real_tick)
    assert fired and summary["results"][0]["action"] == "stopped"      # the tick saw its stale booking
    assert _ghl_statuses(ok_ghl) == [((APPT, "cancelled"), {"to_notify": False})]
    _assert_booking_settled(store, state)
    # nothing re-cancels, re-holds or re-sends afterwards
    later = Recorder()
    for hour in (11, 12, 13):
        A.flush_queued(inst, store=store, now=ct(2026, 9, 22, hour, 0), ghl=later)
    assert [c for c in later.calls if c[1][:1] == (APPT,)] == [] and inst.sent == []


def test_a_retry_and_a_reply_both_landing_mid_tick_both_survive(tmp_env, monkeypatch):
    store, state = _booked_ladder(tmp_env, monkeypatch, "r2.json")
    ok_ghl = Recorder()
    inst = FakeInstantly(sender=SOPIO)
    real_tick = cadence.tick_lead
    fired = {}

    def both_then_tick(st, now, **kw):
        if not fired:
            fired["x"] = True
            A.retry_failed_cancels(store, ok_ghl, inst, ct(2026, 9, 22, 10, 0))
            _real_reply(store, monkeypatch, ct(2026, 9, 22, 10, 0), "sopio-both")
        return real_tick(st, now, **kw)

    monkeypatch.setattr(cadence, "tick_lead", both_then_tick)
    cadence_job.run(ct(2026, 9, 22, 10, 0), store, inst, None, free_slots=FREE, notify_fn=_nf([]),
                    log_fn=lambda *a, **k: None)
    monkeypatch.setattr(cadence, "tick_lead", real_tick)
    assert fired
    raw = _assert_booking_settled(store, state)
    assert raw["cadence"]["stopped_reason"] == "inbound_reply" and raw["cadence"]["needs_fresh_draft"] is True
    assert "sopio-both" in raw["processed_email_ids"]
    _later_ticks_send_nothing(store, inst, [])


# ======================================================== the merge itself
def test_merge_keeps_what_others_changed_and_lands_what_the_tick_changed():
    base = {"status": "positive", "history": [1], "offered_slots": ["a"],
            "cadence": {"armed_at": "t0", "day": 1, "next_send_at": "n2", "stopped_reason": None, "touches": [1],
                        "booking": {"appointment_id": "x", "cancel_failed": True}}}
    # the tick sent D2 and advanced
    mine = {"status": "positive", "history": [1], "offered_slots": ["a", "b"],
            "cadence": {"armed_at": "t0", "day": 2, "next_send_at": "n3", "stopped_reason": None, "touches": [1, 2],
                        "booking": {"appointment_id": "x", "cancel_failed": True}}}
    # meanwhile a reply stopped the ladder and a retry settled the booking
    current = {"status": "replied", "history": [1, 2], "offered_slots": ["a", "c"], "processed_email_ids": ["r"],
               "cadence": {"armed_at": "t0", "day": 1, "next_send_at": None, "stopped_reason": "inbound_reply",
                           "stopped_at": "s", "needs_fresh_draft": True, "touches": [1],
                           "booking_cancelled": {"appointment_id": "x"}}}
    out = A.merge_stale_write(base, mine, current)
    cad = out["cadence"]
    assert out["status"] == "replied" and out["history"] == [1, 2] and out["processed_email_ids"] == ["r"]
    assert out["offered_slots"] == ["a", "c", "b"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["next_send_at"] is None and cad["needs_fresh_draft"]
    assert "booking" not in cad and cad["booking_cancelled"] == {"appointment_id": "x"}
    assert cad["day"] == 2 and cad["touches"] == [1, 2]
    # with nobody else writing, the tick's own stop lands
    stopped = dict(mine, cadence=dict(mine["cadence"], stopped_reason="exhausted", next_send_at=None))
    assert A.merge_stale_write(base, stopped, base)["cadence"]["stopped_reason"] == "exhausted"
    # and a stop in the store beats the tick's own stop
    assert A.merge_stale_write(base, stopped, current)["cadence"]["stopped_reason"] == "inbound_reply"


def test_the_pre_send_check_reads_only_what_the_store_changed():
    state = cadence.arm(LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN), ARMED_AT)

    class Store(object):
        def __init__(self, row):
            self.row = row

        def get(self, key, default=None):
            return self.row

    same = cadence.state_to_dict(state)
    assert cadence.changed_in_store(state, Store(same)) is None
    assert cadence.changed_in_store(state, Store(None)) is None
    assert cadence.changed_in_store(state, None) is None
    stopped = dict(same, cadence=dict(same["cadence"], stopped_reason="inbound_reply"))
    assert cadence.changed_in_store(state, Store(stopped)) == "inbound_reply"
    booked = dict(same, cadence=dict(same["cadence"], booking={"slot": "x"}))
    assert cadence.changed_in_store(state, Store(booked)) == "booked"
    rearmed = dict(same, cadence=dict(same["cadence"], armed_at=ct(2026, 9, 22, 9, 0).isoformat()))
    assert cadence.changed_in_store(state, Store(rearmed)) == "rearmed"
    replied = dict(same, last_inbound_at=ct(2026, 9, 22, 9, 0).isoformat())
    assert cadence.changed_in_store(state, Store(replied)) == "inbound_reply"
