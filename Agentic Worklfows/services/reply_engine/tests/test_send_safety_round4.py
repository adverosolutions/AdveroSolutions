"""Send-safety round 4: the reviewer-max round-3 REJECT, as regression tests.

The reviewer's probes (scratchpad/review-s/test_r3_*.py) are copied here as
assertions:

1. Lorenzo's decision: an edit to a card that holds a booking needs an
   explicit Keep / Release choice; the words never decide (test_r3_parser,
   test_r3_edit_e2e). The choice is bound to the booking and the text; a
   stale one is refused. Unedited engine drafts go by the intent recorded
   when they took the booking.
2. "Gone" is decided on the HTTP status plus a confirming re-read, never on
   message text (test_r3_gone); an inferred or hand-reported cancel keeps the
   reminder hold until the call has passed.
3. A reply landing while a cancel retry finishes cannot bring the booking back
   (test_r3_reply_race), through the real pipeline.
4. The D1 deferral is persisted by jobs.cadence_tick (test_r3_d1_job) and the
   window opens 30 minutes before the real send (test_r3_d1_edges).
5. GET /booking/cancelled needs a valid signature (test_r3_cancel_link).
6. No confirmation less than 60 minutes before the call.

Every client is an in-process fake or a MockTransport that fails on any
request; live-mode tests set MODE=live in-process only.
"""
from datetime import timedelta
from urllib.parse import parse_qs, quote, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

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
    APPT, CAMPAIGN, D1_FREE, FRI, OTHER_TIMES, SOPIO, SOPIO_KEY, THU_3PM, Failing, FakeInstantly, Recorder,
    _alerts, _card, _d1_state, _ghl_event, _go_live, _go_shadow, _process, _prospect_facing, _save_card, _tick,
    _tick_ghl, _world, ct, env, webhook_payload,
)
from test_send_safety_round3 import _armed_touches, _ghl_statuses, _move_appointment, _sopio_confirm_card

# These tests cover the E1 Veto window, switched off on 2026-10-06 (cadence.E1_VETO).
pytestmark = pytest.mark.usefixtures("e1_veto_on")

NOW = ct(2026, 9, 21, 16, 0)
FRI_1PM = "2026-09-25T13:00:00-05:00"

# test_r3_parser.CASES: (the edited sentence, what Lorenzo means)
PARSER_CASES = [
    ("Thu 3:00pm CT just got taken on my side, sorry. Could you do Friday at 1 instead?", "release"),
    ("Thu 3:00pm CT no longer works for me. Grab any time here.", "release"),
    ("Can't do Thu 3:00pm CT after all. Would 1pm Friday work?", "release"),
    ("Instead of Thu 3:00pm, how about Fri 1pm CT?", "release"),
    ("Thu 3:00pm is out, sorry. How about Fri 13:00 CT?", "release"),
    ("Thu 3:00pm next week instead? This week is packed.", "release"),
    ("Thu 3:00pm won't work. Tomorrow at 2 works though.", "release"),
    ("Thu 3:00pm CT is gone, how about Tue Sep 29 2:00pm?", "release"),
    ("Let's move from Thu 3:00pm to Fri 1:00pm CT.", "release"),
    ("Locked in for Thursday at 3pm CT. If that ever stops working, Fri 1:00pm is open too.", "keep"),
    ("Locked in for Thursday at 3pm CT, see you then.", "keep"),
    ("Locked in Thu 3:00pm CT (4:00pm ET your time).", "keep"),
    ("Confirmed for Thu 3:00pm CT (Thu 4:00pm ET your time).", "keep"),
    ("locked in thu 3:00pm ct", "keep"),
    ("Locked in Thu 3:00 pm CT.", "keep"),
    ("Thu 3:30pm CT instead?", "release"),
    ("Sure, Thu 3:00pm ET it is.", "release"),
    ("Great, Thu 4:00pm ET works (that is 3pm my time). See you then.", "keep"),
]


def _body(env, token, sentence):
    link = A.load(token, env["store"]).draft.booking_link
    return "Hey Sopio,\n\n%s Here if needed: %s\n\nLorenzo" % (sentence, link)


def _hand_over_card(env):
    st = env["store"]
    _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), ct(2026, 9, 21, 15, 30))
    _process(env, webhook_payload(SOPIO, "2026-09-21T17:37"), ct(2026, 9, 21, 16, 0))
    # The third reply is sent after the second (16:25 CT), not at the first
    # reply's time the reused fixture carries: replies are ordered by when the
    # lead sent them (round 4), and a card answering an older reply is held.
    third = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42", email_id="sopio-fri",
                                          reply_text="Actually, could we do Friday at 1pm instead?",
                                          timestamp="2026-09-21T21:25:00.000Z"),
                     ct(2026, 9, 21, 16, 30))
    assert third["booking_handoff"]["action"] == "transferred"
    _move_appointment(st, SOPIO_KEY, "appt-live-9")
    return third


def _owner_card(env, kind):
    return _sopio_confirm_card(env) if kind == "confirmation" else _hand_over_card(env)


def _assert_kept(st, ghl, inst):
    """Keep: GHL releases the invite, the lead gets the one reply, the
    reminder ladder is armed for the booked Thursday and nothing else."""
    assert _ghl_statuses(ghl) == [(("appt-live-9", "confirmed"), {"to_notify": True})]
    assert len(inst.sent) == 1 and inst.sent[0]["to"] == SOPIO
    assert not show_rate.is_held(st, "appt-live-9")
    touches = _armed_touches(st, "appt-live-9")
    assert touches
    for key in st.keys("showrate:appt-live-9:"):
        assert (st.get(key).get("appointment") or {}).get("start_iso") == THU_3PM
    assert st.get(SOPIO_KEY)["cadence"]["booking"]["awaiting_approval"] is False


def _assert_released(st, ghl, inst):
    """Release: one silent GHL cancel, never "confirmed", the one reply, no
    ladder, and the appointments tick has nothing to say to the lead."""
    assert _ghl_statuses(ghl) == [(("appt-live-9", "cancelled"), {"to_notify": False})]
    assert len(inst.sent) == 1 and inst.sent[0]["to"] == SOPIO
    assert _armed_touches(st, "appt-live-9") == []
    assert "booking" not in st.get(SOPIO_KEY)["cadence"]
    tick_ghl = _tick_ghl()
    for when in (ct(2026, 9, 21, 16, 30), ct(2026, 9, 23, 15, 5), ct(2026, 9, 24, 11, 5)):
        _tick(st, tick_ghl, _ghl_event(appointment_id="appt-live-9", status="cancelled"), when,
              appointment_id="appt-live-9")
    assert _prospect_facing(tick_ghl) == []


# ======================================== 1. Keep / Release on the Edit page
@pytest.mark.parametrize("sentence,meaning", PARSER_CASES)
def test_every_parser_phrase_is_decided_by_the_choice_never_by_the_words(env, monkeypatch, sentence, meaning):
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    body = _body(env, r["approval_token"], sentence)
    refused = A.edit(r["approval_token"], body, store=st, now=ct(2026, 9, 21, 16, 10))
    assert refused["ok"] is False and refused["needs_booking_choice"] is True
    assert A.load(r["approval_token"], st).draft.body_text != body                   # nothing saved
    ed = A.edit(r["approval_token"], body, store=st, now=ct(2026, 9, 21, 16, 10), booking_choice=meaning)
    if not ed["ok"]:
        pytest.skip("copy rules reject this sentence: %s" % ed.get("problems"))
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(ed["token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    if out.get("status") == "stale_slots":
        # "Tue Sep 29 2:00pm" is read (dated wording) and is past the 5-business-day
        # horizon: the stale check refuses the whole send, booking untouched and held
        assert "Sep 29" in sentence and ghl.calls == [] and inst.sent == []
        assert show_rate.is_held(st, "appt-live-9")
    elif meaning == "keep":
        _assert_kept(st, ghl, inst)
    else:
        _assert_released(st, ghl, inst)


@pytest.mark.parametrize("kind", ["confirmation", "hand_over"])
@pytest.mark.parametrize("choice", ["keep", "release"])
def test_live_edit_page_end_to_end_for_both_owner_card_types_and_both_choices(env, monkeypatch, kind, choice):
    st = env["store"]
    card = _owner_card(env, kind)
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    app_mod.configure(store=st, ghl=ghl, instantly=inst, clock=lambda: ct(2026, 9, 21, 16, 45))
    client = TestClient(app_mod.app)
    form = client.get("/edit/%s" % card["approval_token"])
    assert "Keep the call: send the invite for Thu Sep 24 3:00pm CT" in form.text
    assert "Release the call: cancel it silently, no invite" in form.text
    sentence = ("Locked in for Thursday at 3pm CT, see you then." if choice == "keep"
                else "Thu 3:00pm CT just got taken on my side, sorry. Could you do Fri 1:00pm CT instead?")
    body = _body(env, card["approval_token"], sentence)
    page = client.post("/edit/%s" % card["approval_token"], data={"body": body, "booking_choice": choice})
    assert page.status_code == 200 and "Saved and approved" in page.text
    if choice == "keep":
        assert "You kept the call" in page.text
        _assert_kept(st, ghl, inst)
    else:
        assert "You released the call" in page.text
        _assert_released(st, ghl, inst)
        assert FRI_1PM in A.offered_slots(st, ct(2026, 9, 21, 16, 50))            # the new time is held


@pytest.mark.parametrize("kind", ["confirmation", "hand_over"])
def test_saving_an_owner_card_edit_without_a_choice_is_refused(env, monkeypatch, kind):
    st = env["store"]
    card = _owner_card(env, kind)
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    app_mod.configure(store=st, ghl=ghl, instantly=inst, clock=lambda: ct(2026, 9, 21, 16, 45))
    before = A.load(card["approval_token"], st).draft.body_text
    body = _body(env, card["approval_token"], "Thu 3:00pm CT just got taken, could you do Friday at 1 instead?")
    page = TestClient(app_mod.app).post("/edit/%s" % card["approval_token"], data={"body": body})
    assert page.status_code == 400 and "Choose what happens to the booked call" in page.text
    assert "Friday at 1" in page.text                                                  # his text is kept on the form
    assert A.load(card["approval_token"], st).draft.body_text == before
    assert ghl.calls == [] and inst.sent == [] and show_rate.is_held(st, "appt-live-9")


def test_a_choice_whose_booking_changed_afterwards_is_refused(env, monkeypatch):
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    ed = A.edit(r["approval_token"], _body(env, r["approval_token"], "Locked in Thu 3:00pm CT."), store=st,
                now=ct(2026, 9, 21, 16, 10), booking_choice="keep")
    # the booking moves under the card (a reschedule wrote a new appointment)
    raw = st.get(SOPIO_KEY)
    raw["cadence"]["booking"]["appointment_id"] = "appt-live-10"
    st.set(SOPIO_KEY, raw)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(ed["token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    assert out["ok"] is False and out["status"] == "blocked" and out["needs_booking_choice"]
    assert "choose again" in out["problems"][0]
    assert ghl.calls == [] and inst.sent == []
    assert st.get(A.BOOKING_CHOICE_PREFIX + r["approval_token"].split(".")[0]) is None


def test_a_choice_for_a_booking_the_card_no_longer_holds_is_refused(env, monkeypatch):
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    ed = A.edit(r["approval_token"], _body(env, r["approval_token"], "Locked in Thu 3:00pm CT."), store=st,
                now=ct(2026, 9, 21, 16, 10), booking_choice="keep")
    raw = st.get(SOPIO_KEY)
    raw["cadence"]["booking"]["owner"] = "some-newer-card"                    # superseded since
    st.set(SOPIO_KEY, raw)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(ed["token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    assert out["ok"] is False and out["status"] == "blocked" and ghl.calls == [] and inst.sent == []


def test_a_choice_whose_text_changed_is_refused(env, monkeypatch):
    st = env["store"]
    r = _sopio_confirm_card(env)
    _go_live(monkeypatch)
    ed = A.edit(r["approval_token"], _body(env, r["approval_token"], "Locked in Thu 3:00pm CT."), store=st,
                now=ct(2026, 9, 21, 16, 10), booking_choice="keep")
    card = A.load(ed["token"], st)
    stale = dict(st.get(A.BOOKING_CHOICE_PREFIX + card.token.split(".")[0]), draft_hash="another-text")
    st.set(A.BOOKING_CHOICE_PREFIX + card.token.split(".")[0], stale)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(ed["token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    assert out["status"] == "blocked" and ghl.calls == [] and inst.sent == []


@pytest.mark.parametrize("kind", ["confirmation", "hand_over"])
def test_an_unedited_owner_card_confirms_from_its_recorded_intent(env, monkeypatch, kind):
    st = env["store"]
    card = _owner_card(env, kind)
    intent = st.get(A.BOOKING_INTENT_PREFIX + card["approval_token"].split(".")[0])
    assert intent["restates"] is True and intent["appointment_id"] == "appt-live-9"
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(card["approval_token"], inst, store=st, now=ct(2026, 9, 21, 16, 45), ghl=ghl)
    assert out["ok"] and out["invite"]["released"] is True
    _assert_kept(st, ghl, inst)


def test_an_unedited_owner_card_whose_booking_changed_is_refused(env, monkeypatch):
    st = env["store"]
    r = _sopio_confirm_card(env)
    raw = st.get(SOPIO_KEY)
    raw["cadence"]["booking"]["slot"] = "2026-09-24T16:00:00-05:00"          # rescheduled after the draft
    st.set(SOPIO_KEY, raw)
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(r["approval_token"], inst, store=st, now=ct(2026, 9, 21, 16, 11), ghl=ghl)
    assert out["status"] == "blocked" and ghl.calls == [] and inst.sent == []


def test_the_text_reader_recognises_the_engines_dated_wording_and_keeps_the_stale_check(env, monkeypatch):
    st = env["store"]
    r = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), ct(2026, 9, 21, 15, 30))
    card = A.load(r["approval_token"], st)
    assert not A.card_owns_booking(card, st)
    body = _body(env, r["approval_token"], "Would Tue Sep 29 2:00pm or Wed Sep 30 1:00pm CT work for a quick call?")
    ed = A.edit(r["approval_token"], body, store=st, now=ct(2026, 9, 21, 15, 40))
    assert ed["ok"] and ed["offered_slots"] == ["2026-09-29T14:00:00-05:00", "2026-09-30T13:00:00-05:00"]
    assert "2026-09-29T14:00:00-05:00" in A.offered_slots(st, ct(2026, 9, 21, 15, 40))
    out = A.approve(ed["token"], FakeInstantly(sender=SOPIO), store=st, now=ct(2026, 9, 29, 13, 0))
    assert out["status"] in ("stale_slots", "expired")
    assert A.slots_named_in("would TUE  SEP 29\n2:00PM work", ct(2026, 9, 21, 15, 40)) == ["2026-09-29T14:00:00-05:00"]


# ========================================================== 6. 60-minute margin
def test_no_confirmation_less_than_an_hour_before_the_call(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _card(state, "card2", "Hey Sopio,\n\nYou are locked in for Thu 3:00pm CT.\n\nLorenzo", [THU_3PM],
                 created=ct(2026, 9, 24, 10, 0))
    _save_card(store, card)
    _go_live(monkeypatch)
    ghl, inst = Recorder(), FakeInstantly(sender=SOPIO)
    out = A.approve(card.token, inst, store=store, now=ct(2026, 9, 24, 14, 15), ghl=ghl)
    assert out["ok"] is False and out["status"] == "blocked"
    assert "less than 60 minutes away" in out["problems"][0] and "Handle it by hand" in out["problems"][0]
    assert ghl.calls == [] and inst.sent == []
    assert _alerts("too close to confirm") and _alerts("too close to confirm")[0]["priority"] == "urgent"
    assert show_rate.is_held(store, APPT) and store.get(state.key)["cadence"]["booking"]["appointment_id"] == APPT
    tick_ghl = _tick_ghl()
    _tick(store, tick_ghl, _ghl_event(), ct(2026, 9, 24, 14, 20))
    assert _prospect_facing(tick_ghl) == []
    # 61 minutes out is still confirmable
    store2, state2 = _world(tmp_env, monkeypatch, name="store2.json")
    card2 = _card(state2, "card2", "Hey Sopio,\n\nYou are locked in for Thu 3:00pm CT.\n\nLorenzo", [THU_3PM],
                  created=ct(2026, 9, 24, 10, 0))
    _save_card(store2, card2)
    ghl2 = Recorder()
    ok = A.approve(card2.token, FakeInstantly(sender=SOPIO), store=store2, now=ct(2026, 9, 24, 13, 59), ghl=ghl2)
    assert ok["ok"] and _ghl_statuses(ghl2) == [((APPT, "confirmed"), {"to_notify": True})]


# ======================================================= 2. "gone", decided safely
GONE_ERRORS = [
    'GHL PUT /calendars/events/appointments/appt-live-1 -> HTTP 404: {"message":"Cannot PUT /calendars/events/'
    'appointments/appt-live-1","error":"Not Found","statusCode":404}',
    'GHL PUT /calendars/events/appointments/appt-live-1 -> HTTP 422: {"message":["calendar not found"]}',
    'GHL PUT /calendars/events/appointments/appt-live-1 -> HTTP 400: {"message":"Contact does not exist"}',
    'GHL PUT /calendars/events/appointments/appt-live-1 -> HTTP 403: {"message":"The token does not have access '
    'to this location, location not found"}',
    'GHL PUT /calendars/events/appointments/appt-live-1 -> HTTP 502: <html>upstream 404 page</html>',
]


@pytest.mark.parametrize("error", GONE_ERRORS)
def test_an_error_that_merely_looks_gone_is_a_failed_cancel_and_the_lead_hears_nothing(tmp_env, monkeypatch, error):
    store, state = _world(tmp_env, monkeypatch, name="g%d.json" % GONE_ERRORS.index(error))
    _go_live(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError(error)

    # the event is still live: a re-read shows it booked
    ghl = Recorder(returns={"update_appointment_status": boom,
                            "get_appointment": {"appointment": {"id": APPT, "appointmentStatus": "confirmed"}}})
    inst = FakeInstantly(sender=SOPIO)
    out = A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                      ghl=ghl, instantly=inst, old_owner="card2")
    store.set(state.key, state.to_store())
    assert out["action"] == "release_pending" and out["cancelled"]["cancel_failed"] is True
    assert state.cadence["booking"]["cancel_failed"] and show_rate.is_held(store, APPT)
    assert store.get(A.CANCEL_RETRY_PREFIX + state.key)
    assert ghl.named("get_appointment") == ([("get_appointment", (APPT,), {})] if "HTTP 404" in error else [])
    tick_ghl = _tick_ghl()
    for when in (ct(2026, 9, 21, 16, 50), ct(2026, 9, 23, 15, 5), ct(2026, 9, 24, 11, 5)):
        _tick(store, tick_ghl, _ghl_event(), when)
    assert _prospect_facing(tick_ghl) == []
    assert inst.sent == []


def test_a_404_with_no_way_to_re_read_is_a_failed_cancel(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)

    class NoRead(object):
        def update_appointment_status(self, *a, **k):
            raise RuntimeError("GHL PUT x -> HTTP 404: not found")

    out = A.cancel_booking(state, NoRead(), None, ct(2026, 9, 21, 17, 0), store=store)
    assert out["cancelled"] is False and show_rate.is_held(store, APPT)


# ================================================= 3. reply lands mid-retry
def test_a_reply_processed_while_the_retry_finishes_never_brings_the_booking_back(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                ghl=Recorder(fail={"update_appointment_status"}), instantly=inst, old_owner="card2")
    store.set(state.key, state.to_store())
    _go_shadow(monkeypatch)
    ok_ghl = Recorder()
    real_classify = app_mod.classify
    fired = {}

    def classify_then_retry(event):
        # the */5 retry finishes the pending cancel after process_event read the row
        if not fired:
            fired["x"] = True
            _go_live(monkeypatch)
            A.retry_failed_cancels(store, ok_ghl, inst, ct(2026, 9, 21, 16, 45))
            _go_shadow(monkeypatch)
            assert "booking" not in store.get(state.key)["cadence"]
        return real_classify(event)

    monkeypatch.setattr(app_mod, "classify", classify_then_retry)
    t = httpx.MockTransport(Failing())
    deps = app_mod.configure(store=store, ghl=GHL(token=None, transport=t), instantly=Instantly(api_key="x", transport=t))
    try:
        result = app_mod.process_event(ReplyEvent.from_webhook(webhook_payload(SOPIO, "2026-09-21T17:37",
                                                                               email_id="sopio-new")),
                                       deps=deps, now=ct(2026, 9, 21, 16, 45), busy_blocks=[])
    finally:
        app_mod.configure()
    assert fired and _ghl_statuses(ok_ghl) == [((APPT, "cancelled"), {"to_notify": False})]
    raw = store.get(state.key)
    assert "sopio-new" in raw["processed_email_ids"]                               # the pipeline's own write landed
    booking = raw["cadence"].get("booking") or {}
    assert booking.get("appointment_id") != APPT and not booking.get("cancel_failed")
    assert raw["cadence"]["booking_cancelled"]["appointment_id"] == APPT
    assert store.get(A.CANCEL_RETRY_PREFIX + state.key) is None and not show_rate.is_held(store, APPT)
    assert not A.cancel_pending(LeadState.from_store(raw))
    later = Recorder()
    _go_live(monkeypatch)
    for hour in (17, 18, 19):
        A.flush_queued(inst, store=store, now=ct(2026, 9, 21, hour, 0), ghl=later)
    assert [c for c in later.calls if c[1][:1] == (APPT,)] == []
    assert result["state_key"] == state.key


def test_save_lead_state_keeps_booking_fields_another_writer_changed(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    base = store.get(state.key)
    stale = LeadState.from_store(base)
    stale.status = "draft_pending_approval"
    # meanwhile the booking was cancelled under the lock
    store.mutate(state.key, lambda raw: dict(raw, cadence={"booking_cancelled": {"slot": THU_3PM}}))
    A.save_lead_state(store, stale, base)
    raw = store.get(state.key)
    assert raw["status"] == "draft_pending_approval"
    assert "booking" not in raw["cadence"] and raw["cadence"]["booking_cancelled"] == {"slot": THU_3PM}
    # ...while a writer's own booking change still lands when nobody else touched it
    fresh = LeadState.from_store(store.get(state.key))
    base2 = store.get(state.key)
    fresh.cadence = dict(fresh.cadence, booking={"slot": FRI_1PM, "appointment_id": "appt-2"})
    A.save_lead_state(store, fresh, base2)
    assert store.get(state.key)["cadence"]["booking"]["appointment_id"] == "appt-2"


# ============================================ 5. the "I cancelled it" link
def test_the_i_cancelled_it_link_is_checked_on_get_and_post_and_bound_to_its_lead(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                ghl=Recorder(fail={"update_appointment_status"}), instantly=inst, old_owner="card2")
    store.set(state.key, state.to_store())
    url = _alerts("Call NOT cancelled")[0]["click"]
    path = url[len("https://engine.test"):]
    q = parse_qs(urlparse(path).query)
    t, a = q["t"][0], q["a"][0]
    other = LeadState(lead_email="kim@acme.com", campaign_id=CAMPAIGN, first_name="Kim",
                      cadence={"booking": {"slot": THU_3PM, "appointment_id": "appt-kim", "awaiting_approval": False}})
    store.set(other.key, other.to_store())
    ghl = Recorder()
    app_mod.configure(store=store, ghl=ghl, instantly=FakeInstantly(), clock=lambda: ct(2026, 9, 21, 17, 0))
    c = TestClient(app_mod.app)
    try:
        assert c.post("/booking/cancelled/%s/%s?a=appt-kim&t=%s" % (CAMPAIGN, quote("kim@acme.com"), t)).status_code == 403
        assert c.post("/booking/cancelled/%s/%s?a=%s&t=%s" % (CAMPAIGN, quote("kim@acme.com"), a, t)).status_code == 403
        g = c.get("/booking/cancelled/%s/%s?a=%s" % (CAMPAIGN, quote(SOPIO), a))
        assert g.status_code == 403 and "2026-09-24" not in g.text and "Sep 24" not in g.text
        g2 = c.get("/booking/cancelled/%s/%s?a=%s&t=%s" % (CAMPAIGN, quote(SOPIO), a, t[:-2] + "00"))
        assert g2.status_code == 403 and "2026-09-24" not in g2.text
        assert c.get(path).status_code == 200                                              # the signed link works
        app_mod.configure(store=store, ghl=ghl, instantly=FakeInstantly(), clock=lambda: ct(2026, 9, 29, 17, 0))
        expired = TestClient(app_mod.app)
        assert expired.get(path).status_code == 403 and expired.post(path).status_code == 403
    finally:
        app_mod.configure()
    assert store.get(other.key)["cadence"]["booking"]["appointment_id"] == "appt-kim"
    assert store.get(state.key)["cadence"]["booking"]["cancel_failed"] and ghl.calls == []


# ======================================================== 4. D1 in production
def test_the_d1_deferral_is_persisted_by_the_job_and_the_window_opens_at_0930(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "j.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    _go_live(monkeypatch)
    state = _d1_state()
    store.set(state.key, cadence.state_to_dict(state))
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    pings = []
    nf = lambda *a, **k: pings.append(a[0]) or {"sent": True, "email": True}   # noqa: E731
    free = D1_FREE + ["2026-09-24T14:00:00-05:00", "2026-09-25T13:00:00-05:00"]
    out = []
    for when in (ct(2026, 9, 22, 18, 0), ct(2026, 9, 22, 19, 0), ct(2026, 9, 23, 7, 0), ct(2026, 9, 23, 9, 30),
                 ct(2026, 9, 23, 10, 0)):
        summary = cadence_job.run(when, store, inst, None, free_slots=free, notify_fn=nf, log_fn=lambda *a, **k: None)
        r = summary["results"][0]
        out.append((r["action"], r.get("reason"), store.get(state.key)["cadence"].get("next_send_at")))
    assert out[0] == ("not_due", "veto_window_deferred", ct(2026, 9, 23, 10, 0).isoformat())
    assert [o[0] for o in out[1:]] == ["not_due", "not_due", "veto_window_opened", "sent"]
    veto_pings = [p for p in pings if p.startswith("D1 follow-up")]
    assert veto_pings == ["D1 follow-up to a lead sends at Wed 10:00am CT"]  # public topic: no lead in the title
    assert len(inst.sent) == 1


def test_a_friday_evening_resume_opens_the_window_at_monday_0930_not_0700(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "a.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    _go_live(monkeypatch)
    state = _d1_state()
    state.cadence["next_send_at"] = ct(2026, 9, 25, 10, 0).isoformat()
    state.cadence["veto_notified_at"] = ct(2026, 9, 25, 9, 30).isoformat()
    cadence.stop(state, "recipient_unconfirmed", ct(2026, 9, 25, 12, 0))
    cadence.resume_after_recipient_hold(state, ct(2026, 9, 25, 18, 45))
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    pings = []
    nf = lambda *a, **k: pings.append((a, k)) or {"sent": True, "email": True}   # noqa: E731
    free = D1_FREE + ["2026-09-30T13:00:00-05:00", "2026-10-01T14:00:00-05:00"]
    actions = []
    for when in (ct(2026, 9, 25, 19, 0), ct(2026, 9, 26, 10, 0), ct(2026, 9, 27, 12, 0), ct(2026, 9, 28, 7, 0),
                 ct(2026, 9, 28, 9, 30, 4), ct(2026, 9, 28, 10, 0, 2)):
        actions.append(cadence.tick_lead(state, when, store=store, instantly=inst, free_slots=free,
                                         notify_fn=nf)["action"])
    assert actions == ["not_due", "not_due", "not_due", "not_due", "veto_window_opened", "sent"]
    assert len(pings) == 1 and "sends at Mon 10:00am CT" in pings[0][0][0]
    token = parse_qs(urlparse(pings[0][1]["click"]).query)["t"][0]
    assert cadence.verify_decision_token("veto", state, token, ct(2026, 9, 28, 10, 0)) is True
    assert len(inst.sent) == 1 and inst.reads


def test_a_late_0931_ping_still_gives_the_full_30_minutes(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "b.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    _go_live(monkeypatch)
    state = _d1_state()
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    pings = []
    nf = lambda *a, **k: pings.append(a[0]) or {"sent": True, "email": True}   # noqa: E731
    actions = [cadence.tick_lead(state, when, store=store, instantly=inst, free_slots=D1_FREE, notify_fn=nf)["action"]
               for when in (ct(2026, 9, 22, 9, 31, 10), ct(2026, 9, 22, 10, 0, 1), ct(2026, 9, 22, 11, 0, 1))]
    assert actions == ["veto_window_opened", "not_due", "sent"]
    assert pings == ["D1 follow-up to a lead sends at Tue 11:00am CT"]  # public topic: no lead in the title
