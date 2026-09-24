"""Prospect-facing send-safety fixes (review findings GOL-1, GOL-6, SAL-1,
SAL-3, SAF-4, SAF-5).

* GOL-1 / GOL-6: one base-URL resolver (approval.base_url) for every link.
  BASE_URL first, REPLY_ENGINE_BASE_URL as the alias; unset, localhost,
  127.0.0.1, 0.0.0.0 and ::1 all count as missing. In live a missing base URL
  holds the D1 auto-send and alerts; in shadow it warns and carries on.
* SAL-1: a second reply that supersedes a booking card leaves the booking with
  an explicit owner: handed to the new card when it keeps the slot, released
  (GHL cancel with to_notify=False) when it does not.
* SAL-3: "Book as asked" passes the GHL client through, and nothing reports
  an invite as released unless the write was attempted and succeeded.
* SAF-4 (decision R6): in live a reply goes out only on a confirmed recipient
  match; a read error, a timeout or a mismatch holds, alerts, retries a bounded
  number of times and then escalates.
* SAF-5: the approval row stores only the notify fields it reads back.

Every HTTP transport here is a MockTransport or an in-process fake; live-mode
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
from services.reply_engine import cadence
from services.reply_engine import show_rate
from services.reply_engine.models import ReplyEvent

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES_PATH = FIXTURES / "instantly_replies_2026-09.json"
REPLIES = json.loads(REPLIES_PATH.read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")
NOW_BUSINESS = CT.localize(datetime(2026, 9, 21, 15, 30))   # Monday 15:30 CT
CAMPAIGN = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"           # bookkeeping_reactivation
SOPIO = "sopiosvanishvili@taxfoaccounting.com"
SOPIO_KEY = "lead:%s:%s" % (CAMPAIGN, SOPIO)
THU_3PM = "2026-09-24T15:00:00-05:00"


def ct(*args):
    return CT.localize(datetime(*args))


class Failing(object):
    def __call__(self, request):
        raise AssertionError("HTTP attempted: %s %s" % (request.method, request.url))


def _go_live(monkeypatch):
    """Live for the rest of this test only; every client in it is a fake."""
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert settings.is_live()


def _email_leg(monkeypatch):
    """A deliverable approval channel for live create_approval. NOTIFY stays
    off (conftest), so nothing is ever sent: notify() returns a test record."""
    monkeypatch.setenv("NOTIFY_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x" * 16)


@pytest.fixture
def env(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.setenv("WEBHOOK_SECRET", "hook-secret")
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "store.json")
    clock = {"now": NOW_BUSINESS}
    t = httpx.MockTransport(Failing())
    deps = app_mod.configure(store=store, ghl=GHL(token=None, transport=t),
                             instantly=Instantly(api_key="x", transport=t), clock=lambda: clock["now"])
    yield {"store": store, "deps": deps, "clock": clock, "client": TestClient(app_mod.app)}
    app_mod.configure()


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


def _process(env, payload, now, busy_blocks=None):
    env["clock"]["now"] = now
    return app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=now,
                                 busy_blocks=[] if busy_blocks is None else busy_blocks)


def _shadow(action=None):
    rows = job_log.read_shadow_log()
    return [r for r in rows if action is None or r["action"] == action]


def _alerts(fragment):
    return [n for n in notify.sent_in_test if fragment in n["title"]]


class FakeInstantly(object):
    """Records every call. get_email answers with ``sender``, or raises."""

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


class FakeGHL(object):
    """A live GHL client stand-in: records what would be written."""

    has_token = False

    def __init__(self, fail_create=False, fail_status=False):
        self.fail_create = fail_create
        self.fail_status = fail_status
        self.calls = []

    def upsert_contact(self, email, **kw):
        self.calls.append(("upsert_contact", email))
        return {"contact": {"id": "contact-1"}}

    def create_appointment(self, calendar_id, contact_id, start, end, title, **kw):
        self.calls.append(("create_appointment", start, kw))
        if self.fail_create:
            raise RuntimeError("GHL 500 on create")
        return {"id": "appt-live-9"}

    def update_opportunity_stage(self, opp_id, stage, **kw):
        self.calls.append(("update_opportunity_stage", opp_id, stage))
        return {"id": opp_id}

    def upsert_opportunity(self, contact_id, pipeline_id, stage, name, **kw):
        self.calls.append(("upsert_opportunity", contact_id, stage))
        return {"opportunity": {"id": "opp-1"}}

    def update_appointment_status(self, appointment_id, status, to_notify=None):
        self.calls.append(("update_appointment_status", appointment_id, status, to_notify))
        if self.fail_status:
            raise RuntimeError("GHL 502 on update")
        return {"id": appointment_id, "appointmentStatus": status}


# ======================================================== GOL-1 / GOL-6
@pytest.mark.parametrize("value", ["", "http://localhost:8000", "localhost:8000", "http://127.0.0.1:8000",
                                   "http://127.0.1.1", "http://0.0.0.0:8000", "http://[::1]:8000", "  "])
def test_unset_or_local_base_url_counts_as_missing(value, monkeypatch):
    monkeypatch.setenv("BASE_URL", value)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    assert A.configured_base_url() is None
    assert A.base_url() == A.DEV_BASE_URL          # shadow: warn and continue
    _go_live(monkeypatch)
    with pytest.raises(A.ApprovalUndeliverable):
        A.base_url()                               # live: fail closed


def test_base_url_prefers_BASE_URL_and_falls_back_to_the_alias(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.example.com/")
    monkeypatch.setenv("REPLY_ENGINE_BASE_URL", "https://alias.example.com")
    assert A.base_url() == "https://engine.example.com"
    monkeypatch.delenv("BASE_URL")
    assert A.base_url() == "https://alias.example.com"
    # a localhost BASE_URL does not shadow a real alias
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    assert A.base_url() == "https://alias.example.com"


def test_approval_card_links_use_the_configured_base_url(env, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://reply.advero.example")
    res = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), NOW_BUSINESS)
    token = res["approval_token"]
    card = notify.sent_in_test[-1]
    assert card["click"] == "https://reply.advero.example/mark-sent/%s" % token   # a first-contact card
    assert "https://reply.advero.example/veto/%s" % token in card["actions"]
    assert "localhost" not in json.dumps(card)


def test_cadence_decision_links_read_BASE_URL_not_only_the_alias(monkeypatch):
    """cadence._decision_url read REPLY_ENGINE_BASE_URL alone and defaulted to
    localhost, while the runbook sets BASE_URL."""
    monkeypatch.setenv("BASE_URL", "https://reply.advero.example")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    state = cadence.arm(cadence.LeadState(lead_email="tiffany@flowerhillfs.com", campaign_id="c1"),
                        ct(2026, 9, 21, 16, 0))
    for kind in ("veto", "approve", "veto-invite"):
        assert cadence._decision_url(kind, state, ct(2026, 9, 22, 9, 30)).startswith(
            "https://reply.advero.example/cadence/%s/c1/" % kind)


def test_live_create_approval_with_a_localhost_base_url_persists_nothing(env, monkeypatch):
    _email_leg(monkeypatch)
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    _go_live(monkeypatch)
    from services.reply_engine.models import Draft, LeadState

    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN)
    event = ReplyEvent.from_webhook(webhook_payload(SOPIO, "2026-09-21T14:42"))
    draft = Draft(subject="Re: x", body_text="Hey Sopio,\n\nx\n\nLorenzo", offered_slots=[THU_3PM])
    with pytest.raises(A.ApprovalUndeliverable):
        A.create_approval(state, draft, event, store=env["store"], now=NOW_BUSINESS)
    assert env["store"].keys(A.APPROVAL_PREFIX) == []
    assert not env["store"].get(A.OFFERED_KEY)


def test_health_reports_a_localhost_base_url_as_unset(env, monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:8000")
    assert env["client"].get("/health").json()["base_url_set"] is False
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    assert env["client"].get("/health").json()["base_url_set"] is True


# ---------------------------------------------------- D1 held without BASE_URL
def _d1_state():
    state = cadence.LeadState(
        lead_email="tiffany@flowerhillfs.com", campaign_id="8086b41e-b546-4b36-9fa0-2d01f5cc119a",
        status="positive_interested", first_name="Tiffany", company="Flowerhill Facility Services",
        eaccount="lorenzo@adveromedia.com", thread_id="thr-1", last_email_id="e-1",
        last_subject="Re: Tiffany, question")
    return cadence.arm(state, ct(2026, 9, 21, 16, 0))  # D1 due Tue 22nd 10:00


FREE = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]


@pytest.mark.parametrize("value", [None, "http://localhost:8000", "http://127.0.0.1:8000", "http://0.0.0.0",
                                   "http://[::1]:8000"])
def test_live_d1_never_arms_or_sends_without_a_usable_base_url(value, tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    if value is None:
        monkeypatch.delenv("BASE_URL", raising=False)
    else:
        monkeypatch.setenv("BASE_URL", value)
    _go_live(monkeypatch)
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    pings = []
    state = _d1_state()

    # 09:30: the veto window would open. It does not.
    res = cadence.tick_lead(state, ct(2026, 9, 22, 9, 30), store=store, instantly=inst, free_slots=FREE,
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "veto_undeliverable" and res["reason"] == "no_base_url" and res["quiet"] is False
    assert not state.cadence.get("veto_notified_at")
    assert len(pings) == 1 and "HELD" in pings[0][0][0] and pings[0][1]["priority"] == "high"
    assert not pings[0][1].get("actions") and not pings[0][1].get("click")   # no dead button
    # 10:00 and 11:00: due, still held, said once
    for hour in (10, 11):
        res = cadence.tick_lead(state, ct(2026, 9, 22, hour, 0), store=store, instantly=inst, free_slots=FREE,
                                notify_fn=lambda *a, **k: pings.append((a, k)))
        assert res["action"] == "veto_undeliverable" and res["quiet"] is True
    assert len(pings) == 1
    assert inst.sent == [] and inst.reads == [] and state.cadence["touches"] == [] and state.cadence["day"] == 0
    assert "held because BASE_URL" in cadence.summarize_touch(res)
    rows = job_log.job_log_path().read_text()
    assert "d1_held_no_base_url" in rows

    # BASE_URL set: the next tick opens the window with a working link, then sends
    monkeypatch.setenv("BASE_URL", "https://reply.advero.example")
    res = cadence.tick_lead(state, ct(2026, 9, 22, 12, 0), store=store, instantly=inst, free_slots=FREE,
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "veto_window_opened"
    assert pings[-1][1]["click"].startswith("https://reply.advero.example/cadence/veto/")
    assert "d1_held_no_base_url_at" not in state.cadence
    # the push names the first hourly tick at least 30 minutes out: 13:00
    assert state.cadence["next_send_at"] == ct(2026, 9, 22, 13, 0).isoformat()
    res = cadence.tick_lead(state, ct(2026, 9, 22, 13, 0), store=store, instantly=inst, free_slots=FREE,
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "sent" and len(inst.sent) == 1


def test_live_d1_whose_window_opened_is_held_if_base_url_is_gone_at_send_time(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    _go_live(monkeypatch)
    inst = FakeInstantly(sender="tiffany@flowerhillfs.com")
    state = _d1_state()
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    pings = []
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, instantly=inst, free_slots=FREE,
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "veto_undeliverable" and res["reason"] == "no_base_url"
    assert inst.sent == [] and state.cadence["day"] == 0
    assert store.get(cadence.touch_marker_key(state, 1)) is None   # the day was never claimed
    assert len(pings) == 1


def test_shadow_d1_without_a_base_url_carries_on_as_before(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    state = _d1_state()
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=FREE,
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send" and res["day"] == 1


# ================================================================ SAF-5
def test_the_approval_row_keeps_no_notify_headers_topic_or_record(env):
    def leaky_notify(title, message, **kw):
        return {"sent": True, "test": False, "shadow": False, "email": False, "topic": "advero-secret-topic",
                "errors": [], "record": {"actions": kw.get("actions")}, "guard": {"payload": {"x": 1}},
                "ntfy": {"ok": True, "status": 200, "headers": {"Authorization": "Bearer tk_live_secret",
                                                                 "Actions": "view, Approve, https://x"}}}

    from services.reply_engine.models import Draft, LeadState

    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN)
    event = ReplyEvent.from_webhook(webhook_payload(SOPIO, "2026-09-21T14:42"))
    draft = Draft(subject="Re: x", body_text="Hey Sopio,\n\nx\n\nLorenzo", offered_slots=[])
    approval = A.create_approval(state, draft, event, store=env["store"], now=NOW_BUSINESS, notify_fn=leaky_notify)
    raw = env["store"].get(A.APPROVAL_PREFIX + approval.token.split(".")[0])
    stored = raw["notify_result"]
    blob = json.dumps(stored)
    assert "tk_live_secret" not in blob and "Authorization" not in blob and "headers" not in blob
    assert "advero-secret-topic" not in blob and "record" not in stored and "guard" not in stored
    assert stored["sent"] is True and stored["ntfy"] == {"ok": True, "status": 200}
    assert "channels" in stored and "actionable" in stored


# ================================================================ SAL-1
def _sopio_booked(env):
    """Sopio's real sequence: a question, then "Thu 4pm ET" (books Thu 3pm CT)."""
    first = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), NOW_BUSINESS)
    second = _process(env, webhook_payload(SOPIO, "2026-09-21T17:37"), ct(2026, 9, 21, 16, 0))
    assert second["booking"]["slot"] == THU_3PM
    booking = env["store"].get(SOPIO_KEY)["cadence"]["booking"]
    assert booking["owner"] == second["approval_token"].split(".")[0]
    assert booking["awaiting_approval"] is True
    appt = booking["appointment_id"]
    assert show_rate.is_held(env["store"], appt)
    return first, second, appt


def _handoff(env):
    first, second, appt = _sopio_booked(env)
    third = _process(env, webhook_payload(SOPIO, "2026-09-21T23:17"), ct(2026, 9, 21, 18, 20))
    assert third["superseded"] == [second["approval_token"]]
    new_id = third["approval_token"].split(".")[0]
    assert third["booking_handoff"]["action"] == "transferred"
    booking = env["store"].get(SOPIO_KEY)["cadence"]["booking"]
    assert booking["owner"] == new_id and booking["transferred_from"] == second["approval_token"].split(".")[0]
    assert booking["slot"] == THU_3PM and show_rate.is_held(env["store"], appt)
    # the copy never claims the invite is already on her calendar: it is not
    assert third["draft"]["offered_slots"] == [THU_3PM]
    assert "invite is on your calendar" not in third["draft"]["body_text"]
    assert "locked in for Thu 3:00pm CT, invite on the way" in third["draft"]["body_text"]
    assert "takes over the call already booked" in third["draft"]["rationale"]
    new_card = A.load(third["approval_token"], env["store"])
    assert A.owns_booking(new_card, app_mod.LeadState.from_store(env["store"].get(SOPIO_KEY)))
    # vetoing the SUPERSEDED card must not touch the booking the new card owns
    assert A.veto(second["approval_token"], store=env["store"], now=ct(2026, 9, 21, 18, 25),
                  ghl=env["deps"].ghl)["booking_cancelled"] is None
    assert env["store"].get(SOPIO_KEY)["cadence"]["booking"]["slot"] == THU_3PM
    return third, appt


def test_second_reply_same_slot_hands_the_booking_to_the_new_card(env):
    _handoff(env)


def test_approving_the_card_that_took_over_the_booking_releases_the_invite_and_ladder(env):
    third, appt = _handoff(env)
    out = A.approve(third["approval_token"], env["deps"].instantly, store=env["store"],
                    now=ct(2026, 9, 21, 18, 30), ghl=env["deps"].ghl)
    assert out["ok"] is True and out["status"] == "sent"
    assert out["show_rate"] and out["show_rate"].get("released") is not False
    assert not show_rate.is_held(env["store"], appt)                   # the ladder runs now
    booking = env["store"].get(SOPIO_KEY)["cadence"]["booking"]
    assert booking["awaiting_approval"] is False and "owner" not in booking
    assert booking["confirmed_by"] == third["approval_token"].split(".")[0]
    assert "update_appointment_status" not in [r["action"] for r in _shadow()
                                                if r["payload"].get("status") == "cancelled"]


def test_vetoing_the_card_that_took_over_the_booking_tears_it_down(env):
    third, appt = _handoff(env)
    out = A.veto(third["approval_token"], store=env["store"], now=ct(2026, 9, 21, 18, 30),
                 ghl=env["deps"].ghl, instantly=env["deps"].instantly)
    assert out["ok"] is True and out["booking_cancelled"]["slot"] == THU_3PM
    state = env["store"].get(SOPIO_KEY)
    assert "booking" not in state["cadence"] and state["cadence"]["booking_cancelled"]["reason"] == "vetoed"
    assert not show_rate.is_held(env["store"], appt)
    assert env["store"].keys("showrate:%s:" % appt) == []
    assert all(r.get("approval") != "booking:%s" % appt for r in env["store"].get(A.OFFERED_KEY) or [])


def test_second_reply_with_other_times_releases_the_superseded_booking(env):
    first, second, appt = _sopio_booked(env)
    # The lead sends this AFTER the booking reply (17:37Z), so it carries a
    # time after it (18:15 CT). It used to reuse the 14:42Z fixture time,
    # which made it older than the booking reply: S-rest round 5 records such
    # a reply only (router.STALE_OLDER_REPLY), so the old data no longer
    # described a newer reply.
    third = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42", email_id="sopio-sat",
                                          reply_text="Actually, could we do Saturday at 10am instead?",
                                          timestamp="2026-09-21T23:15:00.000Z"),
                     ct(2026, 9, 21, 18, 20))
    assert third["superseded"] == [second["approval_token"]]
    assert THU_3PM not in third["draft"]["offered_slots"]          # a counter-proposal, not the booked time
    assert third["booking_handoff"]["action"] == "released"
    state = env["store"].get(SOPIO_KEY)
    assert "booking" not in state["cadence"]
    assert state["cadence"]["booking_cancelled"]["reason"] == "superseded"
    # the GHL cancel carries toNotify: False (shadow record of the would-be write)
    cancels = [r for r in _shadow("update_appointment_status") if r["payload"].get("status") == "cancelled"]
    assert cancels and cancels[-1]["payload"]["appointment_id"] == appt and cancels[-1]["payload"]["toNotify"] is False
    # the held ladder and the slot reservation went with it
    assert not show_rate.is_held(env["store"], appt) and env["store"].keys("showrate:%s:" % appt) == []
    assert all(r.get("approval") != "booking:%s" % appt for r in env["store"].get(A.OFFERED_KEY) or [])
    assert "invite" not in third["draft"]["body_text"].lower()
    # approving the new card releases no invite; vetoing it has nothing to tear down
    card = A.load(third["approval_token"], env["store"])
    assert A.owns_booking(card, app_mod.LeadState.from_store(state)) is False
    before = len(_shadow("update_appointment_status"))
    assert A.veto(third["approval_token"], store=env["store"], now=ct(2026, 9, 21, 18, 30),
                  ghl=env["deps"].ghl)["booking_cancelled"] is None
    assert len(_shadow("update_appointment_status")) == before


def test_live_same_slot_handoff_approve_releases_the_real_invite(env, monkeypatch):
    third, _shadow_appt = _handoff(env)
    # the shadow run gave the booking a synthetic id; a live booking has GHL's
    appt = "appt-live-1"
    raw = env["store"].get(SOPIO_KEY)
    raw["cadence"]["booking"]["appointment_id"] = appt
    env["store"].set(SOPIO_KEY, raw)
    # ...as the engine intent recorded at the hand-over would name it
    intent_key = A.BOOKING_INTENT_PREFIX + third["approval_token"].split(".")[0]
    env["store"].set(intent_key, dict(env["store"].get(intent_key), appointment_id=appt))
    _go_live(monkeypatch)
    ghl = FakeGHL()
    inst = FakeInstantly(sender=SOPIO)
    out = A.approve(third["approval_token"], inst, store=env["store"], now=ct(2026, 9, 21, 18, 30), ghl=ghl)
    assert out["ok"] is True and out["status"] == "sent" and len(inst.sent) == 1
    assert inst.sent[0]["to"] == SOPIO                                           # recipient belt 1
    assert inst.reads                                                            # recipient belt 2
    assert ("update_appointment_status", appt, "confirmed", True) in ghl.calls   # the invite goes now
    assert out["invite"]["released"] is True


def test_live_different_slot_release_cancels_without_notifying_the_lead(env, monkeypatch):
    first, second, _ = _sopio_booked(env)
    # A real GHL id: a synthetic shadow- id has no GHL event to cancel in live.
    appt = "appt-live-1"
    raw = env["store"].get(SOPIO_KEY)
    raw["cadence"]["booking"]["appointment_id"] = appt
    env["store"].set(SOPIO_KEY, raw)
    state = app_mod.LeadState.from_store(env["store"].get(SOPIO_KEY))
    _go_live(monkeypatch)
    ghl = FakeGHL()
    from services.reply_engine.models import Draft

    other = Draft(subject="Re: x", body_text="Hey Sopio,\n\nWould Fri 1:00pm or Fri 2:00pm CT work?\n\nLorenzo",
                  offered_slots=["2026-09-25T13:00:00-05:00", "2026-09-25T14:00:00-05:00"])
    new = A.load(first["approval_token"], env["store"])   # any card object; only its draft/id matter here
    new.draft = other
    A.supersede_pending(env["store"], state, ct(2026, 9, 21, 18, 20))
    out = A.settle_superseded_booking(env["store"], state, new, ct(2026, 9, 21, 18, 20), ghl=ghl,
                                      instantly=FakeInstantly(sender=SOPIO),
                                      superseded=[second["approval_token"]])
    assert out["action"] == "released"
    assert ("update_appointment_status", appt, "cancelled", False) in ghl.calls
    assert not any(c[0] == "update_appointment_status" and c[3] is not False for c in ghl.calls)


# ================================================================ SAL-3
def _ilmi_card(env):
    """Ilmi asked for Wed 11:30am, outside the slot rule: a card with "Book as asked"."""
    ev = ReplyEvent.from_poller_item(fixture_item("info@shiningarmorcleaningnj.com", "2026-09-21T19:00"))
    now = ct(2026, 9, 21, 14, 5)
    env["clock"]["now"] = now
    res = app_mod.process_event(ev, deps=env["deps"], now=now)
    assert res["requested_time"]["slot"] == "2026-09-23T11:30:00-05:00"
    return res["approval_token"], ev, now


def test_book_as_asked_with_a_ghl_write_failure_never_reports_success(env, monkeypatch):
    token, ev, now = _ilmi_card(env)
    _email_leg(monkeypatch)
    _go_live(monkeypatch)
    ghl = FakeGHL(fail_create=True)
    inst = FakeInstantly(sender="info@shiningarmorcleaningnj.com")
    out = A.accept_requested(token, ghl, inst, store=env["store"], now=now)
    assert out["ok"] is False and not out.get("booked") and "booking failed" in out["error"]
    assert inst.sent == []                                          # nothing reached the lead
    assert "booking" not in (env["store"].get(ev.state_key)["cadence"] or {})
    assert not any(c[0] == "update_appointment_status" for c in ghl.calls)


def test_book_as_asked_page_says_so_when_the_booking_fails(env, monkeypatch):
    token, ev, now = _ilmi_card(env)
    _email_leg(monkeypatch)
    _go_live(monkeypatch)
    env["deps"]._ghl = FakeGHL(fail_create=True)
    env["deps"]._instantly = FakeInstantly(sender="info@shiningarmorcleaningnj.com")
    r = env["client"].post("/accept/%s" % token)
    assert r.status_code == 400 and "Not booked" in r.text and "Booked as asked" not in r.text


def test_book_as_asked_passes_ghl_through_and_reports_a_failed_invite_release(env, monkeypatch):
    token, ev, now = _ilmi_card(env)
    _email_leg(monkeypatch)
    _go_live(monkeypatch)
    ghl = FakeGHL(fail_status=True)
    inst = FakeInstantly(sender="info@shiningarmorcleaningnj.com")
    notify.reset_for_tests()
    out = A.accept_requested(token, ghl, inst, store=env["store"], now=now)
    # the confirmation did go out (it cannot be unsent), so ok is True ...
    assert out["ok"] is True and out["status"] == "sent" and len(inst.sent) == 1
    # ... but the invite is NOT reported as released, and Lorenzo is told
    assert ("update_appointment_status", "appt-live-9", "confirmed", True) in ghl.calls  # ghl= was passed
    assert out["invite"]["released"] is False and "502" in out["invite"]["error"]
    assert _alerts("Calendar invite NOT sent")
    booking = env["store"].get(ev.state_key)["cadence"]["booking"]
    assert booking["invite_released"] is False


def test_book_as_asked_page_shows_the_invite_failure(env, monkeypatch):
    token, ev, now = _ilmi_card(env)
    _email_leg(monkeypatch)
    _go_live(monkeypatch)
    env["deps"]._ghl = FakeGHL(fail_status=True)
    env["deps"]._instantly = FakeInstantly(sender="info@shiningarmorcleaningnj.com")
    r = env["client"].post("/accept/%s" % token)
    assert r.status_code == 200 and "NOT released" in r.text


def test_release_invite_in_live_without_a_client_is_not_released(env, monkeypatch):
    from services.reply_engine.models import LeadState

    state = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN,
                      cadence={"booking": {"slot": THU_3PM, "appointment_id": "appt-1"}})
    shadow = A.release_booking_invite(state, None, NOW_BUSINESS)
    assert shadow == {"appointment_id": "appt-1", "released": True, "shadow": True}   # the would_do is the success
    _go_live(monkeypatch)
    notify.reset_for_tests()
    out = A.release_booking_invite(state, None, NOW_BUSINESS)
    assert out["released"] is False and out["error"] == "no_ghl_client"
    assert _alerts("Calendar invite NOT sent")

    class Nothing(object):
        def update_appointment_status(self, *a, **k):
            return None

    assert A.release_booking_invite(state, Nothing(), NOW_BUSINESS)["released"] is False
    synthetic = LeadState(lead_email=SOPIO, campaign_id=CAMPAIGN,
                          cadence={"booking": {"slot": THU_3PM, "appointment_id": "shadow-appt-1"}})
    assert A.release_booking_invite(synthetic, FakeGHL(), NOW_BUSINESS)["released"] is False


# ================================================================ SAF-4
def _live_card(env, monkeypatch):
    res = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), NOW_BUSINESS)
    _email_leg(monkeypatch)
    _go_live(monkeypatch)
    notify.reset_for_tests()
    return res["approval_token"]


@pytest.mark.parametrize("error", [RuntimeError("Instantly 503"), httpx.ReadTimeout("timed out")])
def test_approval_recipient_read_error_holds_alerts_retries_then_escalates(env, monkeypatch, error):
    token = _live_card(env, monkeypatch)
    inst = FakeInstantly(read_error=error)
    approval_id = token.split(".")[0]

    out = A.approve(token, inst, store=env["store"], now=NOW_BUSINESS)
    assert out["ok"] is False and out["held"] is True and out["attempts"] == 1
    assert out["error"] == "recipient_unconfirmed" and out["status"] == "approved_queued"
    card = A.load(token, env["store"])
    assert card.status == "approved_queued" and card.send_after == (NOW_BUSINESS + timedelta(minutes=10)).isoformat()
    assert env["store"].get(A.SEND_CLAIM_PREFIX + approval_id) is None   # a later attempt can claim again
    assert len(_alerts("held")) == 1

    # the poller's flush retries it: too early does nothing, then attempt 2 (no second alert), then 3
    assert A.flush_queued(inst, store=env["store"], now=NOW_BUSINESS + timedelta(minutes=5)) == []
    second = A.flush_queued(inst, store=env["store"], now=NOW_BUSINESS + timedelta(minutes=10))
    assert second[0]["held"] is True and second[0]["attempts"] == 2 and second[0]["escalated"] is False
    assert len(_alerts("held")) == 1
    third = A.flush_queued(inst, store=env["store"], now=NOW_BUSINESS + timedelta(minutes=20))
    assert third[0]["escalated"] is True and third[0]["attempts"] == A.RECIPIENT_HOLD_MAX_ATTEMPTS
    assert A.load(token, env["store"]).status == "send_failed"           # stays held
    urgent = _alerts("HELD")
    assert len(urgent) == 1 and urgent[0]["priority"] == "urgent"
    assert A.flush_queued(inst, store=env["store"], now=NOW_BUSINESS + timedelta(minutes=40)) == []
    assert inst.sent == [] and len(inst.reads) == 3
    assert "reply_to_email" not in [r["action"] for r in _shadow()]
    # the operator path back resets the count
    assert A.retry(token, store=env["store"], now=NOW_BUSINESS + timedelta(minutes=45))["ok"] is True
    assert env["store"].get(A.RECIPIENT_HOLD_PREFIX + approval_id) is None


def test_approval_recipient_mismatch_holds_and_alerts(env, monkeypatch):
    token = _live_card(env, monkeypatch)
    inst = FakeInstantly(sender="somebody.else@other.com")
    out = A.approve(token, inst, store=env["store"], now=NOW_BUSINESS)
    assert out["ok"] is False and out["error"] == "recipient_mismatch" and out["held"] is True
    assert A.load(token, env["store"]).status == "send_failed" and inst.sent == []
    assert _alerts("HELD")


def test_approval_recipient_match_sends(env, monkeypatch):
    token = _live_card(env, monkeypatch)
    inst = FakeInstantly(sender=SOPIO)
    out = A.approve(token, inst, store=env["store"], now=NOW_BUSINESS)
    assert out["ok"] is True and out["status"] == "sent"
    assert len(inst.sent) == 1 and inst.sent[0]["to"] == SOPIO and inst.reads


def test_approval_page_explains_a_held_reply(env, monkeypatch):
    token = _live_card(env, monkeypatch)
    env["deps"]._instantly = FakeInstantly(read_error=RuntimeError("boom"))
    r = env["client"].post("/approve/%s" % token)
    assert r.status_code == 400 and "Held, not sent" in r.text and "Nothing was sent" in r.text


def _cadence_lead():
    state = _d1_state()
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    return state


def test_cadence_recipient_read_error_holds_alerts_retries_then_escalates(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    _go_live(monkeypatch)
    inst = FakeInstantly(read_error=httpx.ConnectTimeout("timed out"))
    state = _cadence_lead()
    pings = []

    def tick(hour):
        return cadence.tick_lead(state, ct(2026, 9, 22, hour, 0), store=store, instantly=inst, free_slots=FREE,
                                 notify_fn=lambda *a, **k: pings.append((a, k)))

    first = tick(10)
    assert first["action"] == "send_failed" and first["reason"] == "recipient_unconfirmed"
    assert first["held"] is True and first["attempts"] == 1 and not first.get("needs_manual_check")
    assert store.get(cadence.touch_marker_key(state, 1)) is None   # nothing left the process: retry allowed
    assert len(pings) == 1 and pings[0][1]["priority"] == "high"
    second = tick(11)
    assert second["reason"] == "recipient_unconfirmed" and second["attempts"] == 2 and len(pings) == 1
    third = tick(12)
    assert third["escalated"] is True and third["stopped"] is True
    assert state.cadence["stopped_reason"] == "recipient_unconfirmed"
    assert len(pings) == 2 and pings[1][1]["priority"] == "urgent"
    assert tick(13)["action"] == "already_stopped"                  # stays held
    assert inst.sent == [] and state.cadence["day"] == 0 and state.cadence["touches"] == []
    assert "recipient could not be confirmed" in cadence.summarize_touch(third)


def test_cadence_recipient_with_no_readable_sender_holds(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    _go_live(monkeypatch)
    inst = FakeInstantly(sender=None)
    state = _cadence_lead()
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, instantly=inst, free_slots=FREE,
                            notify_fn=lambda *a, **k: None)
    assert res["reason"] == "recipient_unconfirmed" and inst.sent == []


def test_cadence_recipient_mismatch_holds(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    _go_live(monkeypatch)
    inst = FakeInstantly(sender="someone-else@example.com")
    state = _cadence_lead()
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, instantly=inst, free_slots=FREE,
                            notify_fn=lambda *a, **k: None)
    assert res["reason"] == "recipient_mismatch" and state.cadence["stopped_reason"] == "recipient_mismatch"
    assert inst.sent == []


def test_cadence_recipient_match_sends_and_clears_an_earlier_hold(tmp_env, monkeypatch):
    store = JsonFileStore(tmp_env / "store.json")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    _go_live(monkeypatch)
    flaky = FakeInstantly(read_error=RuntimeError("503"))
    state = _cadence_lead()
    held = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, instantly=flaky, free_slots=FREE,
                             notify_fn=lambda *a, **k: None)
    assert held["reason"] == "recipient_unconfirmed" and state.cadence["recipient_hold"]["attempts"] == 1
    good = FakeInstantly(sender="tiffany@flowerhillfs.com")
    res = cadence.tick_lead(state, ct(2026, 9, 22, 11, 0), store=store, instantly=good, free_slots=FREE,
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "sent" and len(good.sent) == 1 and good.sent[0]["to"] == "tiffany@flowerhillfs.com"
    assert "recipient_hold" not in state.cadence


# ========================================================= 44-reply replay
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
    summary = replay_mod.replay(REPLIES_PATH, tmp_path / "replay.jsonl", store,
                                ghl=GHL(token=None, transport=t), instantly=Instantly(api_key="x", transport=t))
    yield {"summary": summary, "store": store}
    app_mod.configure()


def test_replay_still_books_sopio_and_rob_and_leaves_no_orphaned_booking(replay_world):
    summary, store = replay_world["summary"], replay_world["store"]
    assert summary["replies"] == 44
    booked = {b["lead"]: b["slot"] for b in summary["booked"]}
    assert booked[SOPIO] == THU_3PM
    assert booked["rob@cjsglobal.com"] == "2026-09-18T13:00:00-05:00"

    # Sopio: her third reply's card now owns the Thu 3pm booking
    sopio = store.get(SOPIO_KEY)
    booking = sopio["cadence"]["booking"]
    lines = [ln for ln in summary["lines"] if ln["lead"] == SOPIO]
    confirm_id = lines[1]["approval_token"].split(".")[0]
    last_id = lines[2]["approval_token"].split(".")[0]
    assert booking["slot"] == THU_3PM and booking["owner"] == last_id and booking["transferred_from"] == confirm_id
    assert store.get(A.APPROVAL_PREFIX + confirm_id)["status"] == "superseded"
    assert store.get(A.APPROVAL_PREFIX + last_id)["status"] == "pending"
    assert "invite is on your calendar" not in lines[2]["draft"]["body_text"]

    # no lead anywhere is left with an unconfirmed booking whose owner is not a live card
    for key in store.keys("lead:"):
        b = (store.get(key).get("cadence") or {}).get("booking") or {}
        if b.get("awaiting_approval"):
            owner = store.get(A.APPROVAL_PREFIX + b["owner"])
            assert owner["status"] == "pending", (key, owner["status"])
