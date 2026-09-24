"""CT3 piece C: the pipeline and the draft builders (shadow, zero HTTP, no LLM).

Every test runs against a tmp approvals file and a tmp parity reference
(template_fixtures.make_template_env); the real config/approved_templates.json
and config/template_catalogue_hashes.json are checked unchanged after each
test. Lead data comes from the recorded Instantly fixtures or is made up.

The verdict-level tests call app._reply_draft and app._template_verdict
directly, so they do not depend on approval.py. The process_event tests run
the whole path through CT3 piece B (create_approval(auto=...) and
approval.auto_send_approved).
"""
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytz
from fastapi.testclient import TestClient

from shared import job_log, llm, notify
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.paths import BASE_DIR
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import booking
from services.reply_engine import draft as D
from services.reply_engine import template_approvals as ta
from services.reply_engine import template_gate as gate
from services.reply_engine.classify import classify, core_text
from services.reply_engine.models import Classification, Extracted, LeadState, ReplyEvent
from services.reply_engine.tests import template_fixtures as tf

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES = json.loads((FIXTURES / "instantly_replies_2026-09.json").read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")
NOW_BUSINESS = CT.localize(datetime(2026, 9, 21, 15, 30))   # Monday 15:30 CT
REAL_APPROVALS = BASE_DIR / "config" / "approved_templates.json"
REAL_REFERENCE = BASE_DIR / "config" / "template_catalogue_hashes.json"
SOPIO = "sopiosvanishvili@taxfoaccounting.com"
ILMI = "info@shiningarmorcleaningnj.com"
# Sopio's 14:42 reply is a pricing question on the bookkeeping_reactivation campaign.
PRICING_ID = "first_reply.bookkeeping_reactivation.pricing.full"



class Failing(object):
    def __call__(self, request):
        raise AssertionError("HTTP attempted in shadow: %s %s" % (request.method, request.url))


def _bytes(p):
    return p.read_bytes() if p.exists() else None


@pytest.fixture
def env(tmp_env, monkeypatch):
    before = (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE))
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("WEBHOOK_SECRET", "hook-secret")
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    notify.reset_for_tests()
    tpl = tf.make_template_env(monkeypatch, tmp_env)
    store = JsonFileStore(tmp_env / "store.json")
    clock = {"now": NOW_BUSINESS}
    t = httpx.MockTransport(Failing())
    deps = app_mod.configure(store=store, ghl=GHL(token=None, transport=t), instantly=Instantly(api_key="x", transport=t),
                             clock=lambda: clock["now"])
    yield {"store": store, "deps": deps, "clock": clock, "tpl": tpl, "client": TestClient(app_mod.app)}
    app_mod.configure()
    gate.clear_cache()
    assert (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE)) == before, "a test wrote a real config file"


def fixture_item(email, ts_prefix=""):
    for r in REPLIES:
        if r["from_address_email"] == email and r["timestamp_created"].startswith(ts_prefix):
            return r
    raise KeyError(email)


def _event(email=SOPIO, ts_prefix="2026-09-21T14:42", **over):
    item = fixture_item(email, ts_prefix)
    payload = {
        "event_type": "reply_received", "timestamp": item["timestamp_created"], "campaign_id": item["campaign_id"],
        "campaign_name": "x", "lead_email": item["from_address_email"], "email_account": item["eaccount"],
        "firstName": item["subject"].split(":")[-1].split(",")[0].strip(), "companyName": "Taxfo Accounting",
        "reply_subject": item["subject"], "reply_text": item["text"], "email_id": item["id"], "thread_id": item["thread_id"],
    }
    payload.update(over)
    return ReplyEvent.from_webhook(payload)


def _cls(label="positive_question", confidence=0.95, method="llm", **extracted):
    return Classification(label=label, confidence=confidence, method=method, extracted=Extracted(**extracted))


def _verdict(env, ev, cls=None, now=NOW_BUSINESS, state=None):
    """The pipeline's own draft and verdict for one reply, without a card."""
    st = env["store"]
    state = state if state is not None else LeadState.from_store(st.get(ev.state_key), ev)
    cls = cls if cls is not None else classify(ev)
    info = {}
    d, requested, result = app_mod._reply_draft(ev, cls, state, env["deps"], now, st, [], core_text(ev.text), info=info)
    v = app_mod._template_verdict(d, info, cls, ev, state, requested, result)
    return d, info, v, requested


def _replies():
    return [x for x in job_log.read_shadow_log() if x["action"] == "reply_to_email"]


# ------------------------------------------------------------ builders
def test_counter_template_ids_mirror_the_counter_text():
    now = NOW_BUSINESS
    early = CT.localize(datetime(2026, 9, 23, 9, 30))
    late = CT.localize(datetime(2026, 9, 23, 19, 30))

    def m(status, proposed=None, slot=None):
        return booking.BookingMatch(slot=slot, status=status, proposed=proposed,
                                    counter_slots=[CT.localize(datetime(2026, 9, 23, 14, 0))])
    cases = (
        (m(booking.WINDOW_NO_FIT), "booking.counter.window_no_fit", "Nothing inside that window"),
        (m(booking.OUTSIDE_WINDOW, early), "booking.counter.outside_window_early", "a touch early"),
        (m(booking.OUTSIDE_WINDOW, late), "booking.counter.outside_window_late", "past my last slot"),
        (m(booking.OUTSIDE_WINDOW), "booking.counter.outside_window_late", "That time does not work on my side."),
        (m(booking.WEEKEND, early), "booking.counter.weekend", "lands on a weekend"),
        (m(booking.TOO_SOON, early), "booking.counter.too_soon", "a little tight"),
        (m(booking.BEYOND_HORIZON, early), "booking.counter.beyond_horizon", "further out than"),
        (m(booking.SLOT_TAKEN, early), "booking.counter.slot_taken", "just got taken"),
    )
    state = LeadState(lead_email="lead@example.invalid", first_name="Jordan")
    for match, tid, words in cases:
        assert booking.counter_template_id(match) == tid
        assert words in booking.counter_proposal_text(match, state)
    assert booking.counter_template_id(m(booking.NO_TIME)) is None
    assert booking.counter_template_id(m(booking.VALID_SLOT, slot=now)) is None
    assert booking.counter_template_id(None) is None
    # every id is in the catalogue
    idx = ta.catalogue_index()
    assert all(tid in idx for _, tid, _ in cases)
    assert set(booking.CONFIRMATION_IDS.values()) <= set(idx) and booking.SLOT_ALREADY_TAKEN_ID in idx


def test_confirmation_and_slot_taken_drafts_carry_their_ids():
    state = LeadState(lead_email="lead@example.invalid", first_name="Jordan", last_subject="Quick question")
    start = CT.localize(datetime(2026, 9, 23, 14, 0))
    d, _ = booking._confirmation_draft(state, start, None, "https://zoom.us/j/123", True)
    assert d.template_id == "booking.confirmation.zoom_link"
    d, _ = booking._confirmation_draft(state, start, "America/New_York", None, False)
    assert d.template_id == "booking.confirmation.no_zoom_link"
    b = booking.confirmation_bindings(state, start, "America/New_York", None)
    assert b == {"slot": "Wed 2:00pm", "first_name": "Jordan", "lead_local_time": "3:00pm ET"}
    assert "(3:00pm ET your time)" in d.body_text
    res = booking._unbookable_result(state, start, booking.SLOT_ALREADY_TAKEN, NOW_BUSINESS, free_slots=[])
    assert res.draft.template_id == "booking.slot_already_taken"
    assert booking.SLOT_ALREADY_TAKEN in res.draft.problems  # stays a card
    res = booking._unbookable_result(state, start, booking.SLOT_NOT_VERIFIED, NOW_BUSINESS, free_slots=[])
    assert res.draft.template_id is None


def test_already_booked_template_id_follows_the_booking_record():
    slot = "2026-09-24T15:00:00-05:00"
    for rec, variant in (({"awaiting_approval": True}, "awaiting_approval"),
                         ({"invite_released": False}, "invite_withheld"),
                         ({"invite_released": True}, "invite_on_calendar"),
                         ({}, "invite_on_calendar")):
        st = LeadState(lead_email="lead@example.invalid", cadence={"booking": dict(rec, slot=slot)})
        assert app_mod._already_booked_template_id(st, slot) == "booking.already_booked.%s" % variant
    st = LeadState(lead_email="lead@example.invalid", cadence={"booking": {"slot": slot}})
    assert app_mod._already_booked_template_id(st, slot, answer="Glad to hear it.") is None
    assert app_mod._already_booked_template_id(st, "not a time") is None


def test_importing_app_builds_no_catalogue():
    """Flag 4: a catalogue built while app.py is importing drops the
    already-booked ids (parity mismatch, auto-send off everywhere)."""
    code = ("import sys; sys.path.insert(0, %r)\n"
            "try:\n    import netguard  # noqa: F401 - the suite's egress guard, when on the path\n"
            "except ImportError:\n    pass\n"
            "import services.reply_engine.app\n"
            "from services.reply_engine import template_approvals as ta, template_gate as g\n"
            "assert ta._CACHE['entries'] is None and g._INDEX_CACHE['index'] is None\n"
            "print('ok')\n" % str(BASE_DIR))
    child_env = dict(os.environ)   # keeps the test-session flag and the guards' path
    child_env.update(MODE="shadow", PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    child_env.pop("ALLOW_LIVE_WRITES", None)
    out = subprocess.run([sys.executable, "-c", code], cwd=str(BASE_DIR), capture_output=True, text=True, timeout=120,
                         env=child_env)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr[-2000:]


# ------------------------------------------------------ verdict (no B)
def test_approved_first_reply_is_allowed_and_stamped(env):
    env["tpl"].approve_ids(PRICING_ID)
    d, info, v, _ = _verdict(env, _event())
    assert info["kind"] == "first_reply" and info["pre_allowed"] is True
    assert (v.allowed, v.reason, v.template_id) == (True, "ok", PRICING_ID), v.detail
    assert d.template_id == PRICING_ID and d.template_hash == gate.current_hash(PRICING_ID)
    # the bindings pin what was rendered
    b = info["bindings"]
    assert b["first_name"] == "Sopio" and b["slots"] in d.body_text and b["booking_url"] in d.body_text


def test_unapproved_first_reply_is_a_card(env):
    d, info, v, _ = _verdict(env, _event())
    assert info["pre_allowed"] is False
    assert (v.allowed, v.reason, v.template_id) == (False, "unapproved", PRICING_ID)


def test_a_changed_binding_makes_the_reply_nonconforming(env):
    """A rendered value that is not the stored lead's (a first name that
    changed between render and verdict) is refused."""
    env["tpl"].approve_ids(PRICING_ID)
    ev = _event()
    st = env["store"]
    state = LeadState.from_store(st.get(ev.state_key), ev)
    cls = classify(ev)
    info = {}
    d, requested, result = app_mod._reply_draft(ev, cls, state, env["deps"], NOW_BUSINESS, st, [], core_text(ev.text),
                                                 info=info)
    info["bindings"]["first_name"] = "Someone"
    v = app_mod._template_verdict(d, info, cls, ev, state, requested, result)
    assert (v.allowed, v.reason) == (False, "nonconforming")


def test_a_sender_name_that_differs_from_the_stored_record_is_a_card(env):
    """Flag 14: the first name is bound to the stored lead record. The event
    renders the greeting; a name that is not the record's is refused."""
    env["tpl"].approve_ids(PRICING_ID)
    ev = _event()
    state = LeadState.from_store(None, ev)
    state.first_name = "Dana"
    d, info, v, _ = _verdict(env, ev, state=state)
    assert "Hey Sopio," in d.body_text and info["bindings"]["first_name"] == "Dana"
    assert (v.allowed, v.reason) == (False, "nonconforming")


@pytest.mark.parametrize("over,reason", [
    ({"confidence": 0.5}, "classification"),
    ({"method": "fallback"}, "classification"),
])
def test_a_weak_or_fallback_classification_is_a_card(env, over, reason):
    env["tpl"].approve_ids(PRICING_ID)
    cls = _cls(question_type="pricing", **over)
    d, info, v, _ = _verdict(env, _event(), cls=cls)
    assert info["pre_allowed"] is False           # the pre-check refuses too
    assert (v.allowed, v.reason, v.template_id) == (False, reason, PRICING_ID)


def test_neutral_question_is_a_card(env):
    tid = "first_reply.bookkeeping_reactivation.other.full"
    env["tpl"].approve_ids(tid)
    d, info, v, _ = _verdict(env, _event(), cls=_cls(label="neutral_question"))
    assert d.template_id == tid
    assert (v.allowed, v.reason) == (False, "classification")


def test_an_unmapped_campaign_has_no_template_id(env):
    """Flag 1: an unmapped campaign draws the cleaning copy (draft._key's
    fallback) but never its template id, so it is a card."""
    for tid in ("first_reply.cleaning_reactivation.pricing.full", PRICING_ID):
        env["tpl"].approve_ids(tid)
    ev = _event()
    ev.campaign_key, ev.niche, ev.offer = None, None, None
    d, info, v, _ = _verdict(env, ev, cls=_cls(question_type="pricing"))
    assert D._key(ev) == "cleaning_reactivation" and D.PRICING["cleaning_reactivation"] in d.body_text
    assert d.template_id is None
    assert (v.allowed, v.reason, v.template_id) == (False, "no_template", None)


def test_a_requested_override_counter_is_a_card_that_keeps_book_as_asked(env):
    """Ilmi asked for Wed 11:30am, which only Lorenzo's own window refuses."""
    env["tpl"].approve_ids("booking.counter.outside_window_early")
    now = CT.localize(datetime(2026, 9, 21, 14, 5))
    ev = ReplyEvent.from_poller_item(fixture_item(ILMI, "2026-09-21T19:00"))
    d, info, v, requested = _verdict(env, ev, now=now)
    assert info["kind"] == "booking" and d.template_id == "booking.counter.outside_window_early"
    assert requested and requested["status"] == "outside_window"
    assert (v.allowed, v.reason) == (False, "requested_override")
    assert info["bindings"]["asked_time"] == "Wed 11:30am CT"


def test_an_approved_booking_confirmation_is_allowed_as_kind_booking(env):
    """The confirmation Sopio's Thu 4pm ET reply books: kind booking, the
    no-Zoom-link id (shadow has no Zoom link), the lead's own time bound."""
    env["tpl"].approve_ids("booking.confirmation.no_zoom_link")
    now = CT.localize(datetime(2026, 9, 21, 16, 0))
    ev = _event(SOPIO, "2026-09-21T17:37")
    d, info, v, _ = _verdict(env, ev, now=now)
    assert info["kind"] == "booking" and d.template_id == "booking.confirmation.no_zoom_link"
    assert info["bindings"]["lead_local_time"] == "4:00pm ET"
    assert (v.allowed, v.reason) == (True, "ok"), v.detail
    # a fallback classification on the same confirmation is a card
    d, info, v, _ = _verdict(env, _event(SOPIO, "2026-09-21T17:37", email_id="again-1"), now=now,
                             cls=_cls(label="positive_interested", method="fallback",
                                      proposed_time="2026-09-24T15:00:00-05:00"))
    assert v.reason in ("classification", "copy_gate") and v.allowed is False


def _booked(env, ev, slot="2026-09-24T15:00:00-05:00", **rec):
    st = env["store"]
    state = LeadState.from_store(st.get(ev.state_key), ev)
    state.cadence = {"booking": dict({"slot": slot, "appointment_id": "appt-1", "shadow": True}, **rec)}
    return state


def test_an_already_booked_reply_is_kind_booking(env):
    """Flag 2: the already-booked reply is judged as a booking email."""
    tid = "booking.already_booked.invite_on_calendar"
    env["tpl"].approve_ids(tid)
    ev = _event(reply_text="Sounds good, see you then.", email_id="booked-1")
    state = _booked(env, ev)
    cls = _cls(label="positive_interested")
    d, info, v, _ = _verdict(env, ev, cls=cls, state=state)
    assert info["kind"] == "booking" and d.template_id == tid
    assert (v.allowed, v.reason) == (True, "ok"), v.detail


def test_an_already_booked_reply_with_a_fallback_classification_is_a_card(env):
    tid = "booking.already_booked.invite_on_calendar"
    env["tpl"].approve_ids(tid)
    ev = _event(reply_text="Sounds good, see you then.", email_id="booked-2")
    state = _booked(env, ev)
    d, info, v, _ = _verdict(env, ev, cls=_cls(label="positive_interested", method="fallback"), state=state)
    assert d.template_id == tid
    assert (v.allowed, v.reason) == (False, "classification")


def test_an_already_booked_reply_with_an_answer_has_no_template_id(env):
    ev = _event(reply_text="How does the pricing work?", email_id="booked-3")
    state = _booked(env, ev)
    d, info, v, _ = _verdict(env, ev, cls=_cls(question_type="pricing"), state=state)
    assert info["kind"] == "booking" and d.template_id is None and v.reason == "no_template"


def test_gate_errors_fail_closed_to_a_card(env, monkeypatch):
    env["tpl"].approve_ids(PRICING_ID)

    def boom(*a, **k):
        raise RuntimeError("gate broke")
    monkeypatch.setattr(gate, "draft_verdict", boom)
    d, info, v, _ = _verdict(env, _event())
    assert (v.allowed, v.reason, v.template_id) == (False, "registry_error", PRICING_ID)


# ------------------------------------------------------------- polish
def _spy_llm(monkeypatch):
    calls = []

    def complete(task, system, user, **kw):
        calls.append(task)
        skel = system.split("Skeleton for this reply")[1]
        return skel.split(":", 1)[1].split("Return only the email body")[0].strip().replace(
            "Nothing up front.", "Nothing up front at all.")
    monkeypatch.setattr(llm, "is_fake", lambda: False)
    monkeypatch.setattr(llm, "complete", complete)
    return calls


def test_an_approved_template_is_never_polished(env, monkeypatch):
    env["tpl"].approve_ids(PRICING_ID)
    calls = _spy_llm(monkeypatch)
    d, info, v, _ = _verdict(env, _event(), cls=_cls(question_type="pricing"))
    assert "draft" not in calls
    assert d.model == "template" and v.allowed is True, v.detail


def test_an_unapproved_template_is_polished_and_is_a_card(env, monkeypatch):
    calls = _spy_llm(monkeypatch)
    d, info, v, _ = _verdict(env, _event(), cls=_cls(question_type="pricing"))
    assert calls.count("draft") == 1
    assert d.model != "template" and "Nothing up front at all." in d.body_text and d.template_id is None
    assert (v.allowed, v.reason) == (False, "not_template_render")


# ------------------------------------------------------------ pipeline
def test_process_event_never_auto_sends_an_approved_first_reply(env):
    """Lorenzo's rule (2026-09-23): the gate allows the approved first reply,
    but first replies are drafts he sends himself, so it is a card
    (approval.FIRST_REPLY_LOCK_REASON)."""
    env["tpl"].approve_ids(PRICING_ID)
    res = app_mod.process_event(_event(), deps=env["deps"], now=NOW_BUSINESS)
    assert res["auto_send"]["allowed"] is True and res["auto_send"]["template_id"] == PRICING_ID
    assert res["auto_send"]["status"] == "pending" and res["auto_send"]["ok"] is False, res["auto_send"]
    assert _replies() == []
    card = A.load(res["approval_token"], env["store"])
    assert card.approved_by is None and card.status == "pending"
    assert card.auto_send["reason"] == A.FIRST_REPLY_LOCK_REASON
    pushed = [n for n in notify.sent_in_test if n["title"].startswith("Reply to approve")]
    assert len(pushed) == 1 and pushed[0]["message"].startswith(
        "Not auto-sent: %s\n" % A.REASON_TEXT["first_reply_draft_only"])
    rows = [r for r in csv.reader(job_log.job_log_path().read_text().splitlines())
            if len(r) > 1 and r[1] == "reply_engine.process_event"]
    detail = json.loads(rows[-1][-1])
    assert detail["template_id"] == PRICING_ID and detail["auto"] == {"allowed": True, "reason": "ok"}


def test_process_event_unapproved_is_an_ordinary_card(env):
    res = app_mod.process_event(_event(), deps=env["deps"], now=NOW_BUSINESS)
    assert res["auto_send"] == {"allowed": False, "reason": "unapproved", "template_id": PRICING_ID, "status": None}
    assert _replies() == []
    assert A.load(res["approval_token"], env["store"]).status == "pending"
    assert [n for n in notify.sent_in_test if n["title"].startswith("Reply to approve")]


def test_process_event_kill_switch_is_a_card(env):
    env["tpl"].approve_ids(PRICING_ID)
    env["tpl"].kill_switch(True, via="env")
    res = app_mod.process_event(_event(), deps=env["deps"], now=NOW_BUSINESS)
    assert res["auto_send"]["reason"] == "kill_switch" and _replies() == []


def test_an_auto_send_that_raises_leaves_the_card_for_the_orphan_sweep(env, monkeypatch):
    env["tpl"].approve_ids(PRICING_ID)

    def boom(*a, **k):
        raise RuntimeError("send path broke")
    monkeypatch.setattr(A, "auto_send_approved", boom)
    res = app_mod.process_event(_event(), deps=env["deps"], now=NOW_BUSINESS)
    assert res["auto_send"]["status"] == "error" and _replies() == []
    assert A.load(res["approval_token"], env["store"]).status == "pending"


def test_a_reply_without_an_instantly_id_is_never_auto_sent(env):
    """Flag 6: an allowed template never bypasses a problem the pipeline
    added (here: no email id to answer in thread)."""
    env["tpl"].approve_ids(PRICING_ID)
    item = fixture_item(SOPIO, "2026-09-21T14:42")
    payload = {"event_type": "reply_received", "timestamp": item["timestamp_created"], "campaign_id": item["campaign_id"],
               "lead_email": SOPIO, "email_account": item["eaccount"], "firstName": "Sopio",
               "companyName": "Taxfo Accounting", "reply_subject": item["subject"], "reply_text": item["text"]}
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert res["auto_send"]["reason"] == "copy_gate" and _replies() == []


def test_a_first_reply_is_never_auto_sent_while_the_previous_call_is_being_cancelled(env):
    """Lorenzo's decision: with the lead's previous call still being cancelled
    in GHL (cancel_failed, retrying), an approved first reply is an ordinary
    card with reason cancel_pending, and no draft problem (still approvable)."""
    env["tpl"].approve_ids(PRICING_ID)
    ev = _event()
    state = LeadState.from_store(None, ev)
    state.cadence = {"booking": {"slot": "2026-09-24T15:00:00-05:00", "appointment_id": "appt-9",
                                 "cancel_failed": True, "shadow": True}}
    env["store"].set(ev.state_key, state.model_dump(mode="json"))
    res = app_mod.process_event(ev, deps=env["deps"], now=NOW_BUSINESS)
    assert res["auto_send"] == {"allowed": False, "reason": "cancel_pending", "template_id": PRICING_ID,
                                "status": None}
    assert _replies() == []
    card = A.load(res["approval_token"], env["store"])
    assert card.status == "pending" and card.draft.problems == []
    assert "still being cancelled in GHL" in card.draft.rationale
    pushed = [n for n in notify.sent_in_test if n["title"].startswith("Reply to approve")]
    assert len(pushed) == 1 and A.REASON_TEXT["cancel_pending"] in pushed[0]["message"]
    rows = [r for r in csv.reader(job_log.job_log_path().read_text().splitlines())
            if len(r) > 1 and r[1] == "reply_engine.process_event"]
    assert json.loads(rows[-1][-1])["auto"] == {"allowed": False, "reason": "cancel_pending"}
    # the gate alone allows this reply: the pending cancel is what holds it
    d, info, v, _ = _verdict(env, _event(email_id="again-2"), state=LeadState.from_store(state.model_dump(mode="json")))
    assert info["cancel_pending"] is True and (v.allowed, v.reason) == (True, "ok"), v.detail
    held = app_mod._not_while_cancel_pending(v)
    assert (held.allowed, held.reason, held.template_id) == (False, "cancel_pending", PRICING_ID)
