"""Send-safety round 2: the reviewer-max REJECT list, as regression tests.

1. A failed GHL cancel never tears the booking down: the booking (marked
   cancel_failed) and the show-rate hold stay, Lorenzo is alerted, the cancel
   is retried from flush_queued, and appointments_tick stays silent.
2. supersede_pending matches cards by approval id, so an edited or
   Book-as-asked card (re-signed token) is superseded; an owner stuck at
   send_failed / blocked / stale_slots is orphaned and handed on or released.
3. Veto and expiry of a never-confirmed booking cancel with to_notify=False.
4. booking.book never leaves an engine-created appointment without a booking
   record + held ladder (or a silent cancel); "booked, pipeline update
   failed" is reported as such.
5. A past booking is never handed over; it is released silently.
6. escalate_pending returns only the safe notify fields.
7. base_url() requires http(s) + host and rejects every loopback /
   unspecified / link-local / localhost form.
8. The invite-claim guard normalises whitespace and catches every "an invite
   exists or is coming" phrasing; approving every replayed card has no false
   positive.
9. A cadence R6 stopped can be resumed from a signed link in the alert.
10. A D1 veto window that opens late still lasts 30 minutes.

Most scenarios are the reviewer's probes (scratchpad/review-s). Every client
is an in-process fake or a MockTransport that fails on any request; live-mode
tests set MODE=live in-process only, to show what would be written.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytz
from fastapi.testclient import TestClient

from shared import job_log, notify, settings
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import booking as booking_mod
from services.reply_engine import cadence
from services.reply_engine import show_rate
from services.reply_engine.models import Approval, Draft, LeadState, ReplyEvent
from jobs import appointments_tick as job

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES_PATH = FIXTURES / "instantly_replies_2026-09.json"
REPLIES = json.loads(REPLIES_PATH.read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")
CAMPAIGN = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"
SOPIO = "sopiosvanishvili@taxfoaccounting.com"
SOPIO_KEY = "lead:%s:%s" % (CAMPAIGN, SOPIO)
ILMI = "info@shiningarmorcleaningnj.com"
THU_3PM = "2026-09-24T15:00:00-05:00"
APPT = "appt-live-1"


def ct(*args):
    return CT.localize(datetime(*args))


BOOKED_AT = ct(2026, 9, 21, 16, 0)


class Failing(object):
    def __call__(self, request):
        raise AssertionError("HTTP attempted: %s %s" % (request.method, request.url))


class Recorder(object):
    """Permissive fake client: records every method call as (name, args,
    kwargs); names in ``fail`` raise, ``returns`` gives fixed answers."""

    has_token = False

    def __init__(self, fail=(), returns=None):
        self.calls = []
        self.fail = set(fail)
        self.returns = returns or {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def fn(*a, **k):
            self.calls.append((name, a, k))
            if name in self.fail:
                raise RuntimeError("fake %s failure" % name)
            if name in self.returns:
                r = self.returns[name]
                return r(*a, **k) if callable(r) else r
            return {"id": "%s-%d" % (name, len(self.calls))}
        return fn

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


class FakeInstantly(object):
    def __init__(self, sender=None, read_error=None):
        self.sender = sender
        self.read_error = read_error
        self.reads = []
        self.sent = []
        self.interest = []

    def get_email(self, email_id):
        self.reads.append(email_id)
        if self.read_error is not None:
            raise self.read_error
        return {"id": email_id, "from_address_email": self.sender}

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        self.sent.append({"reply_to_uuid": reply_to_uuid, "eaccount": eaccount, "to": to, "body": body})
        return {"id": "sent-%d" % len(self.sent)}

    def update_interest_status(self, lead_email, campaign_id, value):
        self.interest.append((lead_email, campaign_id, value))
        return {"ok": True}


def _go_live(monkeypatch):
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert settings.is_live()


def _go_shadow(monkeypatch):
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    assert not settings.is_live()


def _email_leg(monkeypatch):
    monkeypatch.setenv("NOTIFY_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x" * 16)


def _alerts(fragment):
    return [n for n in notify.sent_in_test if fragment in n["title"]]


def fixture_item(email, ts_prefix=""):
    for r in REPLIES:
        if r["from_address_email"] == email and r["timestamp_created"].startswith(ts_prefix):
            return r
    raise KeyError(email)


def webhook_payload(email, ts_prefix="", **over):
    item = fixture_item(email, ts_prefix)
    payload = {
        "event_type": "reply_received", "timestamp": item["timestamp_created"], "campaign_id": item["campaign_id"],
        "campaign_name": "x", "lead_email": item["from_address_email"], "email_account": item["eaccount"],
        "firstName": item["subject"].split(":")[-1].split(",")[0].strip(), "companyName": "Taxfo Accounting",
        "reply_subject": item["subject"], "reply_text": item["text"], "email_id": item["id"],
        "thread_id": item["thread_id"], "unibox_url": "https://app.instantly.ai/app/unibox",
    }
    payload.update(over)
    return payload


@pytest.fixture
def env(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.setenv("WEBHOOK_SECRET", "hook-secret")
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "store.json")
    clock = {"now": ct(2026, 9, 21, 15, 30)}
    t = httpx.MockTransport(Failing())
    deps = app_mod.configure(store=store, ghl=GHL(token=None, transport=t),
                             instantly=Instantly(api_key="x", transport=t), clock=lambda: clock["now"])
    yield {"store": store, "deps": deps, "clock": clock, "client": TestClient(app_mod.app)}
    app_mod.configure()


def _process(env, payload, now):
    env["clock"]["now"] = now
    return app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=now, busy_blocks=[])


# ------------------------------------------------ a live, unconfirmed booking
def _world(tmp_env, monkeypatch, owner="card2", slot=THU_3PM, name="store.json"):
    """What _reply_draft + booking.register_booking leave behind for a
    booking card: the booking on the state, the hold, a held schedule."""
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / name)
    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN, first_name="Sopio", ghl_contact_id="contact-1",
                      ghl_opportunity_id="opp-1",
                      cadence={"booking": {"slot": slot, "appointment_id": APPT, "awaiting_approval": True,
                                           "owner": owner, "booked_at": BOOKED_AT.isoformat()}})
    show_rate.hold(store, APPT, reason="awaiting_approval", now=BOOKED_AT,
                   meta={"lead_email": SOPIO, "start_iso": slot})
    appt = {"id": APPT, "contact_id": "contact-1", "start_iso": slot, "email": SOPIO, "first_name": "Sopio",
            "company": "Taxfo", "booked_at": BOOKED_AT.isoformat(), "niche": "bookkeeping", "offer": "reactivation"}
    show_rate.ensure_scheduled(store, appt, BOOKED_AT)
    A.reserve_slots(store, SOPIO, [slot], "booking:%s" % APPT, BOOKED_AT)
    store.set(state.key, state.to_store())
    assert show_rate.is_held(store, APPT)
    return store, state


def _card(state, approval_id, body, offered, status="pending", created=None):
    created = created or ct(2026, 9, 21, 18, 20)
    d = Draft(subject="Re: x", body_text=body, offered_slots=offered)
    expires = (created + timedelta(hours=48)).isoformat()
    card = Approval(token="x", state_key=state.key, lead_email=SOPIO, campaign_id=CAMPAIGN, email_id="e-%s" % approval_id,
                    eaccount="lorenzo@adveromedia.com", draft=d, status=status, created_at=created.isoformat(),
                    expires_at=expires, label="booking_confirmation")
    card.token = A.make_token(approval_id, state.key, A.draft_hash(d), expires)
    return card


def _save_card(store, card):
    store.set(A.APPROVAL_PREFIX + card.token.split(".")[0], card.model_dump(mode="json"))


OTHER_TIMES = "Hey Sopio,\n\nWould Fri 1:00pm or Fri 2:00pm CT work?\n\nLorenzo"
FRI = ["2026-09-25T13:00:00-05:00", "2026-09-25T14:00:00-05:00"]
LOCKED_IN = "Hey Sopio,\n\nYou are locked in for Thu 3:00pm CT, invite on the way.\n\nLorenzo"


def _ghl_event(slot=THU_3PM, appointment_id=APPT, status="new"):
    return {"id": appointment_id, "startTime": slot, "appointmentStatus": status, "dateAdded": BOOKED_AT.isoformat(),
            "title": "Lorenzo <> Taxfo: 15-min reactivation plan",
            "contact": {"id": "contact-1", "email": SOPIO, "firstName": "Sopio", "companyName": "Taxfo",
                        "tags": ["niche-bookkeeping", "offer-reactivation"]}}


def _tick_ghl():
    return Recorder(returns={"get_conversations": {"conversations": []},
                             "search_conversations": {"conversations": []},
                             "get_messages": {"messages": []}})


def _tick(store, ghl, event, now, appointment_id=APPT):
    return job.tick(now, store, ghl, [job.normalise_ghl_event(event)], active_ids={appointment_id},
                    window=(now - timedelta(days=1), now + timedelta(days=30)), a2p=False)


def _prospect_facing(ghl):
    return [c for c in ghl.calls if c[0] in ("send_message", "create_task")]


# ===================================================== 1. failed GHL cancel
def test_live_failed_release_cancel_keeps_booking_and_hold_and_every_tick_stays_silent(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)
    ghl = Recorder(fail={"update_appointment_status"})
    inst = FakeInstantly(sender=SOPIO)
    new = _card(state, "card3", OTHER_TIMES, FRI)
    out = A.settle_superseded_booking(store, state, new, ct(2026, 9, 21, 16, 40), ghl=ghl, instantly=inst,
                                      old_owner="card2")

    # the cancel was attempted, silently, and failed: nothing else was undone
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"), {"to_notify": False})]
    assert out["action"] == "release_pending"
    assert out["cancelled"]["cancelled"] is False and out["cancelled"]["cancel_failed"] is True
    assert not ghl.named("update_opportunity_stage") and inst.interest == []
    booking = state.cadence["booking"]
    assert booking["appointment_id"] == APPT and booking["cancel_failed"]["attempts"] == 1
    assert "booking_cancelled" not in state.cadence
    assert show_rate.is_held(store, APPT)
    assert store.keys("showrate:%s:" % APPT)                       # schedule kept, held
    assert store.get(A.CANCEL_RETRY_PREFIX + state.key)["appointment_id"] == APPT
    assert _alerts("Call NOT cancelled")
    store.set(state.key, state.to_store())

    # the reviewer's ticks: 10 minutes later, the day before, the morning of, after the call
    tick_ghl = _tick_ghl()
    for when in (ct(2026, 9, 21, 16, 50), ct(2026, 9, 21, 18, 30), ct(2026, 9, 23, 15, 1),
                 ct(2026, 9, 23, 15, 5), ct(2026, 9, 24, 11, 5), ct(2026, 9, 24, 16, 30)):
        _tick(store, tick_ghl, _ghl_event(), when)
    assert _prospect_facing(tick_ghl) == []


def test_failed_cancel_is_retried_from_flush_queued_and_torn_down_once_it_succeeds(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                ghl=Recorder(fail={"update_appointment_status"}), instantly=inst, old_owner="card2")
    store.set(state.key, state.to_store())

    still_failing = Recorder(fail={"update_appointment_status"})
    assert A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 16, 45), ghl=still_failing) == []
    raw = store.get(state.key)
    assert raw["cadence"]["booking"]["cancel_failed"]["attempts"] == 2 and show_rate.is_held(store, APPT)
    assert len(_alerts("Call NOT cancelled")) == 1                 # said once

    # 20:00 is outside the send window: the silent cancel is retried anyway
    ok = Recorder()
    A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 20, 0), ghl=ok)
    assert [(c[1], c[2]) for c in ok.named("update_appointment_status")] == [((APPT, "cancelled"), {"to_notify": False})]
    raw = store.get(state.key)
    assert "booking" not in raw["cadence"] and raw["cadence"]["booking_cancelled"]["slot"] == THU_3PM
    assert "cancel_failed" not in raw["cadence"]["booking_cancelled"]
    assert not show_rate.is_held(store, APPT) and store.keys("showrate:%s:" % APPT) == []
    assert store.get(A.CANCEL_RETRY_PREFIX + state.key) is None
    assert ("update_opportunity_stage", ("opp-1", settings.GHL_STAGES.get("new_reply")), {"status": "open"}) in ok.calls
    assert THU_3PM not in A.offered_slots(store, ct(2026, 9, 21, 20, 0))
    # nothing left to retry
    again = Recorder()
    A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 20, 5), ghl=again)
    assert again.calls == []


def test_a_cancel_that_keeps_failing_escalates_once_and_keeps_the_hold(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    bad = Recorder(fail={"update_appointment_status"})
    A.settle_superseded_booking(store, state, _card(state, "card3", OTHER_TIMES, FRI), ct(2026, 9, 21, 16, 40),
                                ghl=bad, instantly=inst, old_owner="card2")
    store.set(state.key, state.to_store())
    for minute in range(5, 60, 5):
        A.flush_queued(inst, store=store, now=ct(2026, 9, 21, 16, 40) + timedelta(minutes=minute), ghl=bad)
    assert len(bad.named("update_appointment_status")) == A.CANCEL_RETRY_MAX_ATTEMPTS
    assert len(_alerts("BY HAND")) == 1 and _alerts("BY HAND")[0]["priority"] == "urgent"
    assert show_rate.is_held(store, APPT) and store.get(state.key)["cadence"]["booking"]["cancel_failed"]


def test_live_cancel_without_a_ghl_client_is_a_failure_not_a_cancel(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_live(monkeypatch)
    out = A.cancel_booking(state, None, None, ct(2026, 9, 21, 17, 0), store=store)
    assert out["cancelled"] is False and out["appointment_error"] == "no_ghl_client"
    assert show_rate.is_held(store, APPT) and state.cadence["booking"]["cancel_failed"]


def test_shadow_cancel_is_a_recorded_would_do_and_tears_down(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _go_shadow(monkeypatch)
    out = A.cancel_booking(state, None, None, ct(2026, 9, 21, 17, 0), store=store)
    assert out["cancelled"] is True and out["appointment"]["shadow"] is True
    assert out["appointment"]["payload"]["toNotify"] is False    # awaiting approval: silent
    assert not show_rate.is_held(store, APPT) and "booking" not in state.cadence


def _owner_card(store, state):
    card = _card(state, "card2", LOCKED_IN, [THU_3PM])
    _save_card(store, card)
    return card


def test_live_veto_with_a_failed_cancel_says_so_on_the_page_and_the_tick_stays_silent(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    ghl = Recorder(fail={"update_appointment_status"})
    app_mod.configure(store=store, ghl=ghl, instantly=FakeInstantly(sender=SOPIO),
                      clock=lambda: ct(2026, 9, 21, 17, 0))
    try:
        r = TestClient(app_mod.app).post("/veto/%s" % card.token)
    finally:
        app_mod.configure()
    assert r.status_code == 200
    assert "was cancelled" not in r.text and "could NOT be cancelled" in r.text
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"), {"to_notify": False})]
    raw = store.get(state.key)
    assert raw["cadence"]["booking"]["cancel_failed"] and show_rate.is_held(store, APPT)
    assert raw["history"][-1]["booking_cancelled"] is False and raw["history"][-1]["booking_cancel_failed"] is True
    tick_ghl = _tick_ghl()
    _tick(store, tick_ghl, _ghl_event(), ct(2026, 9, 21, 17, 10))
    _tick(store, tick_ghl, _ghl_event(), ct(2026, 9, 23, 15, 5))
    assert _prospect_facing(tick_ghl) == []


def test_veto_result_never_reports_a_failed_cancel_as_done(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    out = A.veto(card.token, store=store, now=ct(2026, 9, 21, 17, 0), ghl=Recorder(fail={"update_appointment_status"}),
                 instantly=FakeInstantly(sender=SOPIO))
    assert out["ok"] is True and out["booking_cancelled"] is None
    assert out["booking_cancel_failed"]["cancel_failed"] is True


# ============================================ 3. veto / expiry: to_notify=False
def test_live_veto_of_an_unconfirmed_booking_cancels_silently(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    ghl = Recorder()
    inst = FakeInstantly(sender=SOPIO)
    out = A.veto(card.token, store=store, now=ct(2026, 9, 21, 17, 0), ghl=ghl, instantly=inst)
    assert out["booking_cancelled"]["cancelled"] is True
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"), {"to_notify": False})]
    assert inst.interest == [(SOPIO, CAMPAIGN, 1)] and inst.sent == []
    assert not show_rate.is_held(store, APPT)


def test_live_veto_of_a_transferred_unconfirmed_booking_cancels_silently(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch, owner="card3")
    state.cadence["booking"].update(transferred_from="card2", transferred_at=ct(2026, 9, 21, 18, 20).isoformat())
    store.set(state.key, state.to_store())
    card = _card(state, "card3", LOCKED_IN, [THU_3PM])
    _save_card(store, card)
    _go_live(monkeypatch)
    ghl = Recorder()
    A.veto(card.token, store=store, now=ct(2026, 9, 21, 18, 30), ghl=ghl, instantly=FakeInstantly(sender=SOPIO))
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"), {"to_notify": False})]


def test_live_expiry_of_an_unconfirmed_booking_writes_nothing_to_ghl_on_approve_and_on_flush(tmp_env, monkeypatch):
    """SAL-6 (re-review): expiry no longer cancels the call on its own. The
    booking and its hold stay, the card is retired, and Lorenzo gets one
    high-priority Keep / Release push naming the appointment."""
    store, state = _world(tmp_env, monkeypatch)
    card = _owner_card(store, state)
    _go_live(monkeypatch)
    ghl = Recorder()
    inst = FakeInstantly(sender=SOPIO)
    out = A.approve(card.token, inst, store=store, now=ct(2026, 9, 24, 10, 0), ghl=ghl)
    assert out["status"] == "expired" and out["booking_held"]["appointment_id"] == APPT
    assert ghl.calls == [] and inst.sent == [] and inst.interest == []
    assert store.get(state.key)["cadence"]["booking"]["appointment_id"] == APPT and show_rate.is_held(store, APPT)
    assert len(_alerts("Card expired with a call still booked")) == 1

    # the tick's expiry path (flush_queued -> expire_overdue) does the same for
    # an open card
    store2, state2 = _world(tmp_env, monkeypatch, name="store2.json")
    open_card = _card(state2, "card2", LOCKED_IN, [THU_3PM], status="blocked")
    _save_card(store2, open_card)
    ghl2 = Recorder()
    A.flush_queued(inst, store=store2, now=ct(2026, 9, 24, 10, 0), ghl=ghl2)
    assert ghl2.calls == [] and A.load(open_card.token, store2).status == "expired"
    assert store2.get(state2.key)["cadence"]["booking"]["appointment_id"] == APPT
    # An approved_queued card is NOT expired any more (re-review R1 item 2):
    # Lorenzo approved it, so the flush sends it, and only because the call is
    # still more than an hour away does it confirm it.
    store3, state3 = _world(tmp_env, monkeypatch, name="store3.json")
    queued = _card(state3, "card2", LOCKED_IN, [THU_3PM], status="approved_queued")
    queued.send_after = ct(2026, 9, 22, 7, 0).isoformat()
    _save_card(store3, queued)
    ghl3 = Recorder()
    inst3 = FakeInstantly(sender=SOPIO)
    A.flush_queued(inst3, store=store3, now=ct(2026, 9, 24, 10, 0), ghl=ghl3)
    assert A.load(queued.token, store3).status == "sent" and len(inst3.sent) == 1
    # the confirm is the one GHL write that tells the lead: toNotify=true
    assert [(c[1], c[2]) for c in ghl3.named("update_appointment_status")] == [((APPT, "confirmed"),
                                                                                {"to_notify": True})]


def test_a_confirmed_booking_is_cancelled_without_notifying_too(tmp_env, monkeypatch):
    """SAL-9: every engine-initiated cancel passes to_notify=False; a confirmed
    booking used to keep GHL's default notification setting."""
    store, state = _world(tmp_env, monkeypatch)
    state.cadence["booking"]["awaiting_approval"] = False
    _go_live(monkeypatch)
    ghl = Recorder()
    A.cancel_booking(state, ghl, None, ct(2026, 9, 21, 17, 0), store=store)
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"), {"to_notify": False})]


# ====================================== 2. supersede by id, orphaned owners
def test_edited_card_queued_at_20_is_superseded_and_never_flushed(env):
    st = env["store"]
    first = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), ct(2026, 9, 21, 15, 30))
    tok1 = first["approval_token"]
    body = A.load(tok1, st).draft.body_text
    ed = A.edit(tok1, body.replace("Hey Sopio,", "Hi Sopio,"), store=st, now=ct(2026, 9, 21, 19, 50))
    assert ed["ok"] and ed["token"] != tok1
    q = A.approve(ed["token"], env["deps"].instantly, store=st, now=ct(2026, 9, 21, 20, 0))
    assert q["status"] == "approved_queued"

    second = _process(env, webhook_payload(SOPIO, "2026-09-21T17:37"), ct(2026, 9, 21, 20, 30))
    assert second["superseded"] == [ed["token"]]
    assert A.load(ed["token"], st).status == "superseded"
    new_id = second["approval_token"].split(".")[0]
    assert st.get(SOPIO_KEY)["cadence"]["booking"]["owner"] == new_id

    flushed = A.flush_queued(env["deps"].instantly, store=st, now=ct(2026, 9, 22, 7, 0), ghl=env["deps"].ghl)
    assert flushed == []
    assert A.load(second["approval_token"], st).status == "pending"


def test_book_as_asked_card_queued_at_20_is_superseded_and_its_booking_handed_on(env):
    st = env["store"]
    ev = ReplyEvent.from_poller_item(fixture_item(ILMI, "2026-09-21T19:00"))
    env["clock"]["now"] = ct(2026, 9, 21, 14, 5)
    res = app_mod.process_event(ev, deps=env["deps"], now=ct(2026, 9, 21, 14, 5))
    out = A.accept_requested(res["approval_token"], env["deps"].ghl, env["deps"].instantly, store=st,
                             now=ct(2026, 9, 21, 20, 0))
    assert out["status"] == "approved_queued" and out["token"] != res["approval_token"]
    booking = st.get(ev.state_key)["cadence"]["booking"]
    old_id = booking["owner"]
    assert old_id == res["approval_token"].split(".")[0]

    payload = {"event_type": "reply_received", "timestamp": "2026-09-22T01:40:00.000Z",
               "campaign_id": ev.campaign_id, "campaign_name": "x", "lead_email": ev.lead_email,
               "email_account": ev.eaccount, "firstName": "Ilmi", "companyName": "Shining Armor",
               "reply_subject": ev.subject,
               "reply_text": "Thank you Lorenzo, looking forward to it. Is there anything I should prepare?",
               "email_id": "ilmi-followup-1", "thread_id": ev.thread_id}
    r2 = _process(env, payload, ct(2026, 9, 21, 20, 40))
    assert r2["superseded"] == [out["token"]]
    assert st.get(A.APPROVAL_PREFIX + old_id)["status"] == "superseded"
    new_id = r2["approval_token"].split(".")[0]
    booking = st.get(ev.state_key)["cadence"]["booking"]
    assert r2["booking_handoff"]["action"] == "transferred"
    assert booking["owner"] == new_id and booking["transferred_from"] == old_id

    # 07:00: the superseded card does not go out; exactly one card owns the call
    assert A.flush_queued(env["deps"].instantly, store=st, now=ct(2026, 9, 22, 7, 0), ghl=env["deps"].ghl) == []
    live_owners = [k for k in st.keys(A.APPROVAL_PREFIX)
                   if st.get(k)["lead_email"] == ev.lead_email and st.get(k)["status"] in A.SENDABLE_STATUSES]
    assert live_owners == [A.APPROVAL_PREFIX + new_id]
    sent = A.approve(r2["approval_token"], env["deps"].instantly, store=st, now=ct(2026, 9, 22, 7, 5),
                     ghl=env["deps"].ghl)
    assert sent["ok"] is True and sent["status"] == "sent"


def test_r6_send_failed_booking_card_is_orphaned_and_settled_by_the_next_reply(env, monkeypatch):
    st = env["store"]
    _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), ct(2026, 9, 21, 15, 30))
    second = _process(env, webhook_payload(SOPIO, "2026-09-21T17:37"), ct(2026, 9, 21, 16, 0))
    tok2 = second["approval_token"]
    _go_live(monkeypatch)
    bad = FakeInstantly(read_error=RuntimeError("503"))
    A.approve(tok2, bad, store=st, now=ct(2026, 9, 21, 16, 5))
    A.flush_queued(bad, store=st, now=ct(2026, 9, 21, 16, 15))
    A.flush_queued(bad, store=st, now=ct(2026, 9, 21, 16, 25))
    assert A.load(tok2, st).status == "send_failed" and bad.sent == []
    _go_shadow(monkeypatch)

    # The lead sends this AFTER the booking reply (17:37Z), so it carries a
    # time after it (16:55 CT). It used to reuse the 14:42Z fixture time,
    # which made it older than the booking reply: S-rest round 5 records such
    # a reply only (router.STALE_OLDER_REPLY), so the old data no longer
    # described a newer reply.
    third = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42", email_id="sopio-sat",
                                          reply_text="Actually, could we do Friday at 1pm instead?",
                                          timestamp="2026-09-21T21:55:00.000Z"),
                     ct(2026, 9, 21, 17, 0))
    assert third["booking_handoff"] is not None
    assert third["booking_handoff"]["from"] == tok2.split(".")[0]
    # the stuck card can never be retried into sending a stale confirmation
    assert A.load(tok2, st).status == "superseded"
    assert A.retry(tok2, store=st, now=ct(2026, 9, 21, 17, 5))["ok"] is False
    # The new draft restates the booked Thu 3pm (the reschedule path is out of
    # this round's scope), so the call is handed to it: one live owner.
    booking = st.get(SOPIO_KEY)["cadence"]["booking"]
    assert third["booking_handoff"]["action"] == "transferred"
    assert booking["owner"] == third["approval_token"].split(".")[0]
    assert A.load(third["approval_token"], st).status == "pending"


@pytest.mark.parametrize("status", ["send_failed", "blocked", "stale_slots", "superseded"])
def test_an_owner_that_can_no_longer_send_is_orphaned(tmp_env, monkeypatch, status):
    store, state = _world(tmp_env, monkeypatch)
    _save_card(store, _card(state, "card2", LOCKED_IN, [THU_3PM], status=status))
    assert A.orphaned_booking_owner(store, state) == "card2"


@pytest.mark.parametrize("status", ["pending", "approved_queued", "sent"])
def test_a_live_owner_is_not_orphaned(tmp_env, monkeypatch, status):
    store, state = _world(tmp_env, monkeypatch)
    _save_card(store, _card(state, "card2", LOCKED_IN, [THU_3PM], status=status))
    assert A.orphaned_booking_owner(store, state) is None


def test_a_booking_whose_cancel_is_pending_is_not_handed_on(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    _save_card(store, _card(state, "card2", LOCKED_IN, [THU_3PM], status="superseded"))
    state.cadence["booking"]["cancel_failed"] = {"attempts": 1}
    assert A.orphaned_booking_owner(store, state) is None


# ================================================ 4. booking.book partial
def _ilmi_card_live(env, monkeypatch):
    st = env["store"]
    ev = ReplyEvent.from_poller_item(fixture_item(ILMI, "2026-09-21T19:00"))
    env["clock"]["now"] = ct(2026, 9, 21, 14, 5)
    res = app_mod.process_event(ev, deps=env["deps"], now=ct(2026, 9, 21, 14, 5))
    raw = st.get(ev.state_key)
    raw["ghl_contact_id"] = "contact-1"
    raw["ghl_opportunity_id"] = "opp-1"
    st.set(ev.state_key, raw)
    _go_live(monkeypatch)
    _email_leg(monkeypatch)
    return ev, res["approval_token"]


def _ilmi_event(start):
    return {"id": "appt-orphan-1", "startTime": start, "appointmentStatus": "new",
            "dateAdded": ct(2026, 9, 21, 20, 0).isoformat(), "title": "Lorenzo <> Shining Armor: 15-min reactivation plan",
            "contact": {"id": "contact-1", "email": ILMI, "firstName": "Ilmi",
                        "tags": ["niche-cleaning", "offer-reactivation"]}}


def test_live_book_as_asked_with_a_failed_stage_update_is_booked_held_and_reported(env, monkeypatch):
    st = env["store"]
    ev, tok = _ilmi_card_live(env, monkeypatch)
    ghl = Recorder(fail={"update_opportunity_stage"}, returns={"create_appointment": {"id": "appt-orphan-1"}})
    inst = FakeInstantly(sender=ILMI)
    now = ct(2026, 9, 21, 20, 0)     # outside the send window: the reply queues, the call stays held
    out = A.accept_requested(tok, ghl, inst, store=st, now=now)
    assert out["ok"] is True and out["status"] == "approved_queued" and out["booked"]
    assert out["pipeline_errors"] and "opportunity stage" in out["pipeline_errors"][0]
    assert _alerts("Booked, pipeline update failed")
    booking = st.get(ev.state_key)["cadence"]["booking"]
    assert booking["appointment_id"] == "appt-orphan-1" and booking["awaiting_approval"] is True
    assert booking["pipeline_errors"]
    assert show_rate.is_held(st, "appt-orphan-1")
    assert inst.interest == [(ev.lead_email, ev.campaign_id, 2)]     # the later write still ran
    assert inst.sent == []

    tick_ghl = _tick_ghl()
    later = now + timedelta(minutes=10)
    _tick(st, tick_ghl, _ilmi_event(booking["slot"]), later, appointment_id="appt-orphan-1")
    assert _prospect_facing(tick_ghl) == []


def test_book_as_asked_page_says_booked_pipeline_update_failed(env, monkeypatch):
    ev, tok = _ilmi_card_live(env, monkeypatch)
    ghl = Recorder(fail={"update_opportunity_stage"}, returns={"create_appointment": {"id": "appt-orphan-1"}})
    inst = FakeInstantly(sender=ILMI)
    app_mod.configure(store=env["store"], ghl=ghl, instantly=inst, clock=lambda: ct(2026, 9, 21, 16, 0))
    r = env["client"].post("/accept/%s" % tok)
    assert r.status_code == 200 and "Booked, pipeline update failed" in r.text


def test_live_book_with_a_failed_interest_update_still_records_and_holds(tmp_env, monkeypatch):
    store, _ = _world(tmp_env, monkeypatch)
    state = LeadState(lead_email="x@example.com", campaign_id=CAMPAIGN, first_name="X", ghl_contact_id="contact-9",
                      ghl_opportunity_id="opp-9")
    _go_live(monkeypatch)

    class BrokenInstantly(FakeInstantly):
        def update_interest_status(self, lead_email, campaign_id, value):
            raise RuntimeError("Instantly 500")

    ghl = Recorder(returns={"create_appointment": {"id": "appt-new-2"}})
    slot = "2026-09-23T14:00:00-05:00"
    res = booking_mod.book(state, slot, ghl, BrokenInstantly(), now=ct(2026, 9, 21, 16, 0), free_slots=[slot],
                           store=store)
    assert res.pipeline_errors and "Instantly interest" in res.pipeline_errors[0]
    assert state.cadence["booking"]["appointment_id"] == "appt-new-2"
    assert show_rate.is_held(store, "appt-new-2")


def test_an_appointment_that_cannot_be_held_is_cancelled_silently(tmp_env, monkeypatch):
    store, _ = _world(tmp_env, monkeypatch)
    state = LeadState(lead_email="x@example.com", campaign_id=CAMPAIGN, first_name="X", ghl_contact_id="contact-9")
    _go_live(monkeypatch)

    def broken_hold(*a, **k):
        raise RuntimeError("store down")

    monkeypatch.setattr(show_rate, "hold", broken_hold)
    ghl = Recorder(returns={"create_appointment": {"id": "appt-new-3"}})
    slot = "2026-09-23T14:00:00-05:00"
    res = booking_mod.book(state, slot, ghl, FakeInstantly(), now=ct(2026, 9, 21, 16, 0), free_slots=[slot],
                           store=store)
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [
        (("appt-new-3", "cancelled"), {"to_notify": False})]
    assert not ghl.named("update_opportunity_stage")
    assert booking_mod.APPOINTMENT_NOT_CREATED in res.problems
    assert not (state.cadence or {}).get("booking")


# ================================================= 5. no transfer of the past
def test_a_past_booking_is_released_silently_not_transferred(tmp_env, monkeypatch):
    past = "2026-09-21T13:00:00-05:00"
    store, state = _world(tmp_env, monkeypatch, slot=past)
    _go_live(monkeypatch)
    ghl = Recorder()
    new = _card(state, "card3", "Hey Sopio,\n\nYou are locked in for Mon 1:00pm CT.\n\nLorenzo", [past])
    assert A.keeps_booked_slot(new.draft, past)
    out = A.settle_superseded_booking(store, state, new, ct(2026, 9, 21, 16, 0), ghl=ghl,
                                      instantly=FakeInstantly(sender=SOPIO), old_owner="card2")
    assert out["action"] == "released"
    assert [(c[1], c[2]) for c in ghl.named("update_appointment_status")] == [((APPT, "cancelled"), {"to_notify": False})]
    assert "booking" not in state.cadence


def test_a_future_booking_kept_by_the_new_card_is_still_transferred(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    ghl = Recorder()
    out = A.settle_superseded_booking(store, state, _card(state, "card3", LOCKED_IN, [THU_3PM]),
                                      ct(2026, 9, 21, 18, 20), ghl=ghl, old_owner="card2")
    assert out["action"] == "transferred" and state.cadence["booking"]["owner"] == "card3"
    assert ghl.calls == []


# ================================================ 6. escalation Job_Log leak
def test_escalate_pending_returns_only_safe_notify_fields(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    notify.reset_for_tests()
    st = JsonFileStore(tmp_env / "store.json")
    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN)
    ev = ReplyEvent.from_webhook(webhook_payload(SOPIO, "2026-09-21T14:42"))
    ap = A.create_approval(state, Draft(subject="Re: x", body_text="Hey Sopio,\n\nx\n\nLorenzo"), ev, store=st,
                           now=ct(2026, 9, 21, 15, 0))

    def leaky(title, message, **kw):
        return {"sent": True, "topic": "advero-secret-topic",
                "record": {"actions": kw.get("actions"), "click": kw.get("click")},
                "ntfy": {"ok": True, "status": 200, "headers": {"Actions": "view, Approve, %s" % kw.get("click")}}}

    out = A.escalate_pending(store=st, now=ct(2026, 9, 21, 15, 10), notify_fn=leaky)
    assert out
    blob = json.dumps(out)
    assert ap.token not in blob and "advero-secret-topic" not in blob and "headers" not in blob
    assert out[0]["notified"] == A.stored_notify_result(leaky("t", "m"))


# ================================================== 7. base URL resolver
@pytest.mark.parametrize("value", [
    "engine.example.com",                 # scheme-less
    "reply-engine.example.modal.run",
    "//engine.example.com",
    "https://",                           # no host
    "http://[0:0:0:0:0:0:0:1]:8000",      # ::1 long form
    "http://[::1]",
    "http://localhost.:8000",             # FQDN trailing dot
    "http://LOCALHOST",
    "http://app.localhost:8000",          # *.localhost
    "http://app.localhost.",
    "http://[::]:8000",                   # IPv6 unspecified
    "http://0:8000",                      # 0 -> 0.0.0.0
    "http://0.0.0.0",
    "http://[::ffff:127.0.0.1]:8000",     # v4-mapped loopback
    "http://[::ffff:0.0.0.0]",
    "http://2130706433:8000",             # decimal 127.0.0.1
    "http://0x7f000001",                  # hex 127.0.0.1
    "http://127.1",                       # short form
    "http://017700000001",                # octal
    "http://127.0.0.1",
    "http://127.8.9.10",
    "http://169.254.169.254",             # link-local (cloud metadata)
    "http://[fe80::1]",
    "javascript:alert(1)",
    "ftp://engine.example.com",
    "file:///etc/passwd",
])
def test_resolver_rejects_every_unusable_base_url(value, monkeypatch):
    monkeypatch.setenv("BASE_URL", value)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    assert A.configured_base_url() is None
    _go_live(monkeypatch)
    with pytest.raises(A.ApprovalUndeliverable):
        A.base_url()


@pytest.mark.parametrize("value,expected", [
    ("https://engine.test", "https://engine.test"),
    ("https://engine.test/", "https://engine.test"),
    ("  https://reply.advero.example  ", "https://reply.advero.example"),
    ("http://10.0.0.5:8000", "http://10.0.0.5:8000"),
    ("https://advero--reply-engine.modal.run", "https://advero--reply-engine.modal.run"),
    ("https://localhost-proxy.example.com", "https://localhost-proxy.example.com"),
])
def test_resolver_accepts_real_hosts(value, expected, monkeypatch):
    monkeypatch.setenv("BASE_URL", value)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    assert A.configured_base_url() == expected


def test_scheme_less_base_url_holds_live_d1(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.setenv("BASE_URL", "reply-engine.example.modal.run")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    _go_live(monkeypatch)
    pings = []
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    state = _d1_state()
    r1 = cadence.tick_lead(state, ct(2026, 9, 22, 9, 30), store=store, instantly=inst, free_slots=D1_FREE,
                           notify_fn=lambda *a, **k: pings.append((a, k)) or {"sent": True, "email": True})
    r2 = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, instantly=inst, free_slots=D1_FREE,
                           notify_fn=lambda *a, **k: pings.append((a, k)) or {"sent": True, "email": True})
    assert r1["action"] == r2["action"] == "veto_undeliverable" and r1["reason"] == "no_base_url"
    assert not pings[0][1].get("click") and inst.sent == []


# ================================================== 8. invite-claim guard
CLAIMS = [
    "Thu 3:00pm CT works on my end, I will send the invite over.",
    "Locked in Thu 3:00pm CT, invite is on the way.",
    "Locked in Thu 3:00pm CT, the invite is on its way.",
    "Sent you a calendar invite for Thu 3:00pm CT.",
    "Locked in Thu 3:00pm CT, invite on the\nway.",
    "Locked in Thu 3:00pm CT, invite  on   the way.",
    "Locked in Thu 3:00pm CT, invite on the way.",
    "Locked in, the invitation is coming shortly.",
    "You should see the invite in your inbox shortly.",
    "I just sent the calendar invite.",
    "Invite to follow.",
    "The invite is on your calendar.",
    "Keep an eye out for the invite.",
    "I'll shoot you an invite.",
    "I've added you to the calendar invite.",
    "Expect an invite from me today.",
]
NOT_CLAIMS = [
    "Would Thu 3:00pm or Fri 1:00pm CT work? Grab a time here if easier.",
    "Thanks for the invitation to connect.",
    "Happy to chat whenever suits you.",
    "Here is my booking link if neither works.",
]


@pytest.mark.parametrize("sentence", CLAIMS)
def test_invite_guard_catches_every_claim_without_a_booking(sentence):
    st = LeadState(lead_email="x@y.com", campaign_id="c1")
    d = Draft(subject="Re: x", body_text="Hey X,\n\n%s\n\nLorenzo" % sentence, offered_slots=[THU_3PM])
    ap = Approval(token="a1.sig", state_key=st.key, lead_email="x@y.com", email_id="e-1", draft=d, status="pending",
                  created_at="2026-09-21T10:00:00-05:00", expires_at="2026-09-23T10:00:00-05:00")
    assert A.claims_invite(d.body_text)
    assert A._invite_claim_problem(ap, st)


@pytest.mark.parametrize("sentence", NOT_CLAIMS)
def test_invite_guard_leaves_ordinary_copy_alone(sentence):
    assert not A.claims_invite("Hey X,\n\n%s\n\nLorenzo" % sentence)


def test_invite_claim_on_a_booking_whose_cancel_failed_is_blocked(tmp_env, monkeypatch):
    store, state = _world(tmp_env, monkeypatch)
    state.cadence["booking"]["cancel_failed"] = {"attempts": 1}
    card = _card(state, "card2", LOCKED_IN, [THU_3PM])
    assert "being cancelled" in A._invite_claim_problem(card, state)


@pytest.fixture
def replay_world(tmp_path, monkeypatch):
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.setenv("LLM_FAKE", "1")
    monkeypatch.setenv("NOTIFY", "off")
    monkeypatch.delenv("GHL_PRIVATE_INTEGRATION_TOKEN", raising=False)
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow_log.jsonl"))
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "test-secret")
    from services.reply_engine.classify import install_offline_fakes
    from services.reply_engine import replay as replay_mod

    install_offline_fakes()
    store = JsonFileStore(tmp_path / "store.json")
    t = httpx.MockTransport(Failing())
    ghl = GHL(token=None, transport=t)
    inst = Instantly(api_key="x", transport=t)
    summary = replay_mod.replay(REPLIES_PATH, tmp_path / "replay.jsonl", store, ghl=ghl, instantly=inst)
    yield {"summary": summary, "store": store, "ghl": ghl, "inst": inst}
    app_mod.configure()


def test_replay_then_approving_every_pending_card_has_no_invite_false_positive(replay_world):
    s, st = replay_world["summary"], replay_world["store"]
    booked = {b["lead"]: b["slot"] for b in s["booked"]}
    assert booked[SOPIO] == THU_3PM and booked["rob@cjsglobal.com"] == "2026-09-18T13:00:00-05:00"
    now = ct(2026, 9, 22, 10, 0)
    results = []
    for key in st.keys(A.APPROVAL_PREFIX):
        raw = st.get(key)
        if raw.get("status") != "pending":
            continue
        card = Approval.model_validate(raw)
        out = A.approve(card.token, replay_world["inst"], store=st, now=now, ghl=replay_world["ghl"])
        results.append((card.lead_email, out))
    assert results
    invite_blocks = [(lead, out) for lead, out in results
                     if "invite" in " ".join(out.get("problems") or []) or "invite" in str(out.get("error") or "")]
    assert invite_blocks == []


# ===================================================== 9. R6 resume link
D1_FREE = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]


def _d1_state():
    state = cadence.LeadState(
        lead_email="tiffany@flowerhillfs.com", campaign_id="8086b41e-b546-4b36-9fa0-2d01f5cc119a",
        status="positive_interested", first_name="Tiffany", company="Flowerhill Facility Services",
        eaccount="lorenzo@adveromedia.com", thread_id="thr-1", last_email_id="e-1",
        last_subject="Re: Tiffany, question")
    return cadence.arm(state, ct(2026, 9, 21, 16, 0))   # D1 due Tue 22nd 10:00


def _r6_stopped(store, monkeypatch, pings):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    _go_live(monkeypatch)
    state = _d1_state()
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    bad = FakeInstantly(read_error=httpx.ConnectTimeout("timed out"))
    for hour in (10, 11, 12):
        res = cadence.tick_lead(state, ct(2026, 9, 22, hour, 0), store=store, instantly=bad, free_slots=D1_FREE,
                                notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["escalated"] is True and state.cadence["stopped_reason"] == "recipient_unconfirmed"
    return state


def test_r6_escalation_alert_carries_a_signed_resume_link_that_restarts_the_ladder(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    pings = []
    state = _r6_stopped(store, monkeypatch, pings)
    title, message = pings[-1][0]
    kw = pings[-1][1]
    assert kw["priority"] == "urgent" and "tap Resume" in message and "re-arm" not in message
    assert kw["actions"][0][0] == "Resume"
    url = kw["click"]
    assert url == kw["actions"][0][1] and url.startswith("https://engine.test/cadence/resume/") and "?t=" in url
    assert res_link_ok(state, url)

    store.set(state.key, state.to_store())
    app_mod.configure(store=store, ghl=Recorder(), instantly=FakeInstantly(),
                      clock=lambda: ct(2026, 9, 22, 13, 0))
    client = TestClient(app_mod.app)
    path = url[len("https://engine.test"):]
    try:
        page = client.get(path)
        assert page.status_code == 200 and "Resume" in page.text
        assert store.get(state.key)["cadence"]["stopped_reason"] == "recipient_unconfirmed"   # GET changes nothing
        unsigned = client.post(path.split("?")[0])
        assert unsigned.status_code == 403
        forged = client.post(path.split("?")[0] + "?t=2026-09-30T00:00:00-05:00.deadbeef")
        assert forged.status_code == 403
        assert store.get(state.key)["cadence"]["stopped_reason"] == "recipient_unconfirmed"
        ok = client.post(path)
        assert ok.status_code == 200 and "Resumed" in ok.text
    finally:
        app_mod.configure()
    resumed = LeadState.from_store(store.get(state.key))
    assert not resumed.cadence.get("stopped_reason") and "recipient_hold" not in resumed.cadence

    # D1 moved: it re-opens a 30-minute Veto window with a fresh link first...
    good = FakeInstantly(sender="tiffany@flowerhillfs.com")
    fresh = []
    res = cadence.tick_lead(resumed, ct(2026, 9, 22, 13, 5), store=store, instantly=good, free_slots=D1_FREE,
                            notify_fn=lambda *a, **k: fresh.append((a, k)) or {"sent": True, "email": True})
    assert res["action"] == "veto_window_opened" and good.sent == []
    assert fresh[0][1]["click"].startswith("https://engine.test/cadence/veto/")
    # ...then the next tick re-reads the thread and sends only on a confirmed recipient
    res = cadence.tick_lead(resumed, ct(2026, 9, 22, 14, 0), store=store, instantly=good, free_slots=D1_FREE,
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "sent" and good.reads and good.sent[0]["to"] == "tiffany@flowerhillfs.com"


def res_link_ok(state, url):
    token = url.split("?t=", 1)[1]
    from urllib.parse import unquote

    return cadence.verify_decision_token("resume", state, unquote(token), ct(2026, 9, 22, 12, 30)) is True


def test_resume_only_applies_to_an_unconfirmed_recipient_stop(tmp_env, monkeypatch):
    state = _d1_state()
    cadence.stop(state, "recipient_mismatch", ct(2026, 9, 22, 10, 0))
    assert cadence.resume_after_recipient_hold(state, ct(2026, 9, 22, 11, 0))["resumed"] is False
    assert state.cadence["stopped_reason"] == "recipient_mismatch"


def test_r6_escalation_without_a_signing_secret_says_there_is_no_link(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    pings = []
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    _go_live(monkeypatch)
    state = _d1_state()
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    bad = FakeInstantly(read_error=RuntimeError("503"))
    for hour in (10, 11, 12):
        cadence.tick_lead(state, ct(2026, 9, 22, hour, 0), store=store, instantly=bad, free_slots=D1_FREE,
                          notify_fn=lambda *a, **k: pings.append((a, k)))
    kw = pings[-1][1]
    assert not kw.get("actions") and not kw.get("click")
    assert "No Resume link could be signed" in pings[-1][0][1]


# ======================================= 10. late D1 window lasts 30 minutes
def test_late_d1_window_after_a_base_url_hold_pushes_the_send_30_minutes_out(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    state = _d1_state()
    pings = []
    nf = lambda *a, **k: pings.append((a, k)) or {"sent": True, "email": True}   # noqa: E731
    held = cadence.tick_lead(state, ct(2026, 9, 22, 9, 30), store=store, instantly=inst, free_slots=D1_FREE,
                             notify_fn=nf)
    assert held["reason"] == "no_base_url"
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    r = cadence.tick_lead(state, ct(2026, 9, 22, 14, 0), store=store, instantly=inst, free_slots=D1_FREE,
                          notify_fn=nf)
    assert r["action"] == "veto_window_opened"
    # at least 30 minutes out, on the first hourly tick that may send: 15:00
    assert state.cadence["next_send_at"] == ct(2026, 9, 22, 15, 0).isoformat()
    assert "3:00pm" in pings[-1][0][0]                              # the card names the real send time
    for minute in (1, 30):
        r2 = cadence.tick_lead(state, ct(2026, 9, 22, 14, minute), store=store, instantly=inst,
                               free_slots=D1_FREE, notify_fn=nf)
        assert r2["action"] == "not_due" and inst.sent == []
    r3 = cadence.tick_lead(state, ct(2026, 9, 22, 15, 0), store=store, instantly=inst, free_slots=D1_FREE,
                           notify_fn=nf)
    assert r3["action"] == "sent" and len(inst.sent) == 1


def test_an_on_time_d1_window_keeps_the_original_send_time(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    _go_live(monkeypatch)
    state = _d1_state()
    original = state.cadence["next_send_at"]
    r = cadence.tick_lead(state, ct(2026, 9, 22, 9, 30), store=store, instantly=FakeInstantly(sender="x"),
                          free_slots=D1_FREE, notify_fn=lambda *a, **k: {"sent": True, "email": True})
    assert r["action"] == "veto_window_opened" and state.cadence["next_send_at"] == original
