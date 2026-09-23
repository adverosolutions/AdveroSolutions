"""FastAPI endpoints + the process_event pipeline + approval flow (shadow, zero HTTP)."""
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
from services.reply_engine.models import ReplyEvent
from services.reply_engine.tests import template_fixtures

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES = json.loads((FIXTURES / "instantly_replies_2026-09.json").read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")
NOW_BUSINESS = CT.localize(datetime(2026, 9, 21, 15, 30))   # Monday 15:30 CT
NOW_NIGHT = CT.localize(datetime(2026, 9, 21, 22, 10))      # outside 07-19
CAMPAIGN = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"           # bookkeeping_reactivation


class Failing(object):
    def __call__(self, request):
        raise AssertionError("HTTP attempted in shadow: %s %s" % (request.method, request.url))


@pytest.fixture
def env(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("WEBHOOK_SECRET", "hook-secret")
    monkeypatch.delenv("DEBUG_SECRET", raising=False)
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "store.json")
    clock = {"now": NOW_BUSINESS}
    t = httpx.MockTransport(Failing())
    deps = app_mod.configure(store=store, ghl=GHL(token=None, transport=t), instantly=Instantly(api_key="x", transport=t), clock=lambda: clock["now"])
    yield {"store": store, "deps": deps, "clock": clock, "client": TestClient(app_mod.app)}
    app_mod.configure()


def fixture_item(email, ts_prefix=""):
    for r in REPLIES:
        if r["from_address_email"] == email and r["timestamp_created"].startswith(ts_prefix):
            return r
    raise KeyError(email)


def post_webhook(env, payload, secret="hook-secret", **kw):
    headers = dict(kw.pop("headers", None) or {})
    if secret is not None:
        headers.setdefault("X-Advero-Secret", secret)
    return env["client"].post("/webhooks/instantly", json=payload, headers=headers, **kw)


def webhook_payload(email, ts_prefix="", **over):
    item = fixture_item(email, ts_prefix)
    payload = {
        "event_type": "reply_received", "timestamp": item["timestamp_created"], "campaign_id": item["campaign_id"],
        "campaign_name": "x", "lead_email": item["from_address_email"], "email_account": item["eaccount"],
        "firstName": item["subject"].split(":")[-1].split(",")[0].strip(), "companyName": "Taxfo Accounting",
        "reply_subject": item["subject"], "reply_text": item["text"], "email_id": item["id"], "thread_id": item["thread_id"],
        "unibox_url": "https://app.instantly.ai/app/unibox",
    }
    payload.update(over)
    return payload


# --------------------------------------------------------------- health
def test_health(env, monkeypatch, tmp_path):
    r = env["client"].get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["mode"] == "shadow" and body["live"] is False and body["auto_send_after_minutes"] == 0
    # CT3: the templates block (parity, kill switch, counts), never any text
    tpl = template_fixtures.make_template_env(monkeypatch, tmp_path / "tpl")
    tpl.approve_ids("first_reply.bookkeeping_reactivation.pricing.full")
    t = env["client"].get("/health").json()["templates"]
    assert t["parity"] == "ok" and t["kill_switch"] is False and t["auto_send_enabled"] is True
    assert t["approved_count"] == 1 and t["approvable_count"] > 1
    assert "first_reply" not in json.dumps(t) and "Lorenzo" not in json.dumps(t)
    tpl.kill_switch(True, via="env")
    t = env["client"].get("/health").json()["templates"]
    assert t["kill_switch"] is True and t["auto_send_enabled"] is False


def test_root_and_unknown_token_pages(env):
    assert env["client"].get("/").status_code == 200
    assert env["client"].post("/approve/not.a-token").status_code == 400
    assert env["client"].get("/approve/not.a-token").status_code == 400
    assert env["client"].get("/veto/not.a-token").status_code == 400
    assert env["client"].get("/edit/not.a-token").status_code == 404


# -------------------------------------------------------------- webhook
def test_webhook_secret_is_mandatory(env, monkeypatch):
    """No secret configured used to mean 'accept everything', which let an
    unauthenticated caller drive a workspace-wide Instantly blocklist."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    assert post_webhook(env, payload, secret=None).status_code == 401
    assert post_webhook(env, payload, secret="wrong").status_code == 401
    r = post_webhook(env, payload)
    assert r.status_code == 200 and r.json()["label"] == "positive_question"
    # with WEBHOOK_SECRET unset the endpoint refuses rather than falling open
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    assert post_webhook(env, payload, secret=None).status_code == 401
    assert post_webhook(env, payload).status_code == 401


def test_webhook_without_a_campaign_id_is_refused(env):
    """The allowlist used to be skipped entirely when campaign_id was absent, so
    an unauthenticated payload naming any address reached the blocklist path."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    payload.pop("campaign_id")
    payload["lead_email"] = "realcustomer@bigprospect.com"
    payload["reply_text"] = "remove me from your list"
    r = post_webhook(env, payload)
    assert r.json()["ok"] is True and "not in ids.json" in r.json()["ignored"]
    assert [x["action"] for x in job_log.read_shadow_log()] == []
    assert env["store"].keys("lead:") == []


def test_webhook_positive_creates_state_draft_and_approval_without_http(env):
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    r = post_webhook(env, payload)
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "label": "positive_question", "status": "draft_pending_approval", "skipped": None, "approval": True}
    store = env["store"]
    state = store.get("lead:%s:sopiosvanishvili@taxfoaccounting.com" % CAMPAIGN)
    assert state["status"] == "draft_pending_approval"
    assert state["first_name"] == "Sopio" and state["company"] == "Taxfo Accounting"
    assert len(state["drafts"]) == 1 and len(state["approvals"]) == 1
    draft = state["drafts"][0]
    assert draft["subject"] == "Re: Sopio, question" and draft["problems"] == [] and len(draft["offered_slots"]) == 2
    # the push to Lorenzo carries the draft and the action URLs
    assert len(notify.sent_in_test) == 1
    rec = notify.sent_in_test[0]
    # the ntfy topic is public in tests: the title names no one, the email leg has the card
    assert rec["title"] == "Reply to approve: positive question"
    assert "Sopio" not in rec["message"] and draft["body_text"] in rec["email_message"]
    token = state["approvals"][0]
    assert "view, Approve, https://engine.test/approve/%s" % token in rec["actions"]
    assert "view, Veto, https://engine.test/veto/%s" % token in rec["actions"]
    assert "view, Edit, https://engine.test/edit/%s" % token in rec["actions"]
    # shadow log: GHL + Instantly would_do, nothing sent
    actions = [x["action"] for x in job_log.read_shadow_log()]
    assert actions == ["upsert_contact", "upsert_opportunity", "create_note", "update_interest_status"]
    assert "reply_to_email" not in actions
    # slots reserved globally
    assert [s["slot"] for s in store.get("offered_slots")] == draft["offered_slots"]


def test_webhook_duplicate_is_skipped(env):
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    post_webhook(env, payload)
    r = post_webhook(env, payload)
    assert r.json()["skipped"] == "duplicate"
    assert len(notify.sent_in_test) == 1


def test_webhook_ignores_non_reply_events_and_foreign_campaigns(env):
    r = post_webhook(env, {"event_type": "email_sent", "lead_email": "a@b.co"})
    assert r.json() == {"ok": True, "ignored": "email_sent"}
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", campaign_id="not-ours")
    r = post_webhook(env, payload)
    assert r.json()["ok"] is True and "not in ids.json" in r.json()["ignored"]
    assert env["client"].post("/webhooks/instantly", content=b"nope", headers={"Content-Type": "application/json", "X-Advero-Secret": "hook-secret"}).status_code == 400
    assert post_webhook(env, {"event_type": "reply_received"}).status_code == 422


def test_webhook_negative_has_no_draft_and_no_notification(env):
    r = post_webhook(env, webhook_payload("buck@cgavery.com"))
    assert r.json()["label"] == "unsubscribe" and r.json()["approval"] is False
    assert notify.sent_in_test == []
    assert "blocklist_create" in [x["action"] for x in job_log.read_shadow_log()]


# ------------------------------------------------------------- approval
def _positive(env, email="sopiosvanishvili@taxfoaccounting.com", ts="2026-09-21T14:42"):
    post_webhook(env, webhook_payload(email, ts))
    state = env["store"].get("lead:%s:%s" % (CAMPAIGN, email))
    return state, state["approvals"][-1]


def test_approve_sends_through_guarded_reply_endpoint_in_shadow(env):
    state, token = _positive(env)
    r = env["client"].post("/approve/%s" % token)
    assert r.status_code == 200 and "shadow mode" in r.text
    log = job_log.read_shadow_log()
    reply = [x for x in log if x["action"] == "reply_to_email"]
    assert len(reply) == 1
    p = reply[0]["payload"]
    item = fixture_item("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    assert p["reply_to_uuid"] == item["id"] and p["eaccount"] == item["eaccount"] and p["subject"] == "Re: Sopio, question"
    assert p["body"]["text"].rstrip().endswith("Lorenzo")
    assert [x["action"] for x in log].count("update_interest_status") == 2  # route + approve
    new_state = env["store"].get(state_key(state))
    assert new_state["status"] == "replied_awaiting_booking"
    assert new_state["last_outbound_at"] == NOW_BUSINESS.isoformat()
    assert new_state["offered_slots"] == state["drafts"][0]["offered_slots"]
    cad = new_state["cadence"]  # cadence.arm(): day 0 done, next touch the next business day at 10:00 CT
    assert cad["armed_at"] == NOW_BUSINESS.isoformat() and cad["day"] == 0
    assert cad["next_send_at"] == "2026-09-22T10:00:00-05:00"
    assert cad["stopped_reason"] is None and cad["needs_fresh_draft"] is False
    approval = A.load(token, env["store"])
    assert approval.status == "sent"
    # a second approve is refused
    assert env["client"].post("/approve/%s" % token).status_code == 400
    rows = [ln for ln in job_log.job_log_path().read_text().splitlines() if "reply_engine.approval" in ln]
    assert any(",would_send," in ln for ln in rows)


def state_key(state):
    return "lead:%s:%s" % (state["campaign_id"], state["lead_email"])


def test_veto_marks_vetoed_releases_slots_and_blocks_send(env):
    state, token = _positive(env)
    assert env["store"].get("offered_slots")
    r = env["client"].post("/veto/%s" % token)
    assert r.status_code == 200 and "Vetoed" in r.text
    assert env["store"].get("offered_slots") == []
    assert env["store"].get(state_key(state))["status"] == "vetoed"
    assert env["client"].post("/approve/%s" % token).status_code == 400
    assert "reply_to_email" not in [x["action"] for x in job_log.read_shadow_log()]


def test_tampered_or_foreign_secret_token_is_rejected(env, monkeypatch):
    state, token = _positive(env)
    approval_id, sig = token.split(".")
    bad = "%s.%s" % (approval_id, ("0" * len(sig)))
    assert A.load(bad, env["store"]) is None
    assert env["client"].post("/approve/%s" % bad).status_code == 400
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "another-secret")
    assert A.load(token, env["store"]) is None


def test_approval_expires_after_48h(env):
    state, token = _positive(env)
    env["clock"]["now"] = CT.localize(datetime(2026, 9, 23, 16, 0))
    r = env["client"].post("/approve/%s" % token)
    assert r.status_code == 400 and "expired" in r.text
    assert A.load(token, env["store"]).status == "expired"


def test_approve_outside_send_window_queues_then_flushes(env):
    state, token = _positive(env)
    env["clock"]["now"] = NOW_NIGHT
    r = env["client"].post("/approve/%s" % token)
    assert r.status_code == 200 and "Queued" in r.text
    approval = A.load(token, env["store"])
    assert approval.status == "approved_queued" and approval.send_after == "2026-09-22T07:00:00-05:00"
    assert "reply_to_email" not in [x["action"] for x in job_log.read_shadow_log()]
    # still night: nothing flushes
    assert A.flush_queued(env["deps"].instantly, store=env["store"], now=CT.localize(datetime(2026, 9, 22, 6, 30))) == []
    sent = A.flush_queued(env["deps"].instantly, store=env["store"], now=CT.localize(datetime(2026, 9, 22, 7, 5)))
    assert len(sent) == 1 and sent[0]["shadow"] is True
    assert A.load(token, env["store"]).status == "sent"
    assert "reply_to_email" in [x["action"] for x in job_log.read_shadow_log()]


def test_edit_validates_then_approves(env):
    state, token = _positive(env)
    assert env["client"].get("/edit/%s" % token).status_code == 200
    bad = env["client"].post("/edit/%s" % token, data={"body": "Hey Sopio!\n\nAI does it.\n\nLorenzo"})
    assert bad.status_code == 400 and "exclamation mark" in bad.text
    good_body = "Hey Sopio,\n\nNothing up front, $0 if nothing closes.\n\nWould Tue 2:00pm or Wed 3:00pm CT work? Or if it's easier, grab a time here: %s\n\nLorenzo" % settings.BOOKING_URL
    ok = env["client"].post("/edit/%s" % token, data={"body": good_body})
    assert ok.status_code == 200 and "Saved and approved" in ok.text
    reply = [x for x in job_log.read_shadow_log() if x["action"] == "reply_to_email"]
    assert reply and reply[0]["payload"]["body"]["text"] == good_body
    # the old token no longer verifies (draft hash changed)
    assert A.load(token, env["store"]) is None


def test_auto_send_is_disabled_in_shadow_even_when_configured(env, monkeypatch):
    """The old timer (AUTO_SEND_AFTER_MINUTES / auto_send_due) stays unwired:
    CT3's template auto-send does not use it (see
    test_no_send_path_exists_without_a_token_or_an_approved_template)."""
    monkeypatch.setenv("AUTO_SEND_AFTER_MINUTES", "1")
    state, token = _positive(env, "sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37")  # positive_interested
    later = CT.localize(datetime(2026, 9, 21, 16, 0))
    assert A.auto_send_due(env["deps"].instantly, store=env["store"], now=later) == []
    assert A.load(token, env["store"]).status == "pending"
    assert "reply_to_email" not in [x["action"] for x in job_log.read_shadow_log()]


def test_auto_send_default_off_even_in_live(env, monkeypatch, live_mode):
    """auto_send_due is still unwired and 0 by default; CT3 sends approved
    templates through approval.auto_send_approved instead."""
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    assert A.auto_send_minutes() == 0
    assert A.auto_send_due(env["deps"].instantly, store=env["store"], now=NOW_BUSINESS) == []


# ---------------------------------------------------------------- state
def test_state_endpoint_is_secret_gated(env, monkeypatch):
    _positive(env)
    assert env["client"].get("/state/sopiosvanishvili@taxfoaccounting.com").status_code == 401
    monkeypatch.setenv("DEBUG_SECRET", "dbg")
    assert env["client"].get("/state/sopiosvanishvili@taxfoaccounting.com", headers={"X-Advero-Secret": "nope"}).status_code == 401
    r = env["client"].get("/state/sopiosvanishvili@taxfoaccounting.com", headers={"X-Advero-Secret": "dbg"})
    assert r.status_code == 200 and r.json()[0]["status"] == "draft_pending_approval"
    assert env["client"].get("/state/nobody@x.com?secret=dbg").status_code == 404


# ------------------------------------------------------------ pipeline
def test_process_event_new_inbound_stops_the_cadence_and_books_the_named_time(env):
    state, token = _positive(env)
    env["client"].post("/approve/%s" % token)  # arms cadence
    assert env["store"].get(state_key(state))["cadence"]["armed_at"] == NOW_BUSINESS.isoformat()
    second = ReplyEvent.from_webhook(webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37"))
    # busy_blocks=[]: this test is about the booking path, and config/ids.json
    # already records Sopio's own Thu 15:00pm call, which the collision guard
    # (below) would otherwise counter-propose around.
    res = app_mod.process_event(second, deps=env["deps"], now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    assert res["label"] == "positive_interested" and res["approval_token"]
    # the inbound stopped the cadence first (needs_fresh_draft), then the booking stopped it for good
    assert res["cadence_stopped"] == "inbound_reply" and res["needs_fresh_draft"] is True
    new_state = env["store"].get(state_key(state))
    cad = new_state["cadence"]
    assert cad["stopped_reason"] == "booked" and cad["next_send_at"] is None
    assert cad["armed_at"] == NOW_BUSINESS.isoformat()  # the dict is kept, not cleared
    assert cad["booking"]["slot"] == "2026-09-24T15:00:00-05:00"
    assert len(new_state["drafts"]) == 2 and len(new_state["processed_email_ids"]) == 2
    assert res["draft"]["offered_slots"] == ["2026-09-24T15:00:00-05:00"]  # confirms Thu 4pm ET
    assert "Locked in Thu 3:00pm CT (4:00pm ET your time)" in res["draft"]["body_text"]
    assert res["draft"]["problems"] == []  # zoom_not_connected is a note, never a blocker
    assert new_state["phone"] == "237-791-5700"  # cadence reads state.phone for the D6 SMS leg
    assert res["booking"]["slot"] == "2026-09-24T15:00:00-05:00"


def test_process_event_writes_job_log_row(env):
    ev = ReplyEvent.from_poller_item(fixture_item("tim.isacco@siprosearch.com"))
    res = app_mod.process_event(ev, deps=env["deps"], now=NOW_BUSINESS)
    assert res["label"] == "negative_notfit" and res["draft"] is None
    rows = job_log.job_log_path().read_text().splitlines()
    assert any("reply_engine.process_event" in ln and "negative_notfit" in ln for ln in rows)


# ------------------------------------------------- booking / cadence wiring
def _booked_state(env, appointment_id="appt-1", slot="2026-09-24T15:00:00-05:00", email="sopiosvanishvili@taxfoaccounting.com"):
    """A lead whose Discovery Call is already on the calendar."""
    _positive(env)
    key = "lead:%s:%s" % (CAMPAIGN, email)
    raw = env["store"].get(key)
    raw["cadence"] = dict(raw.get("cadence") or {}, armed_at=NOW_BUSINESS.isoformat(), day=0,
                          booking={"slot": slot, "appointment_id": appointment_id, "shadow": True})
    raw["processed_email_ids"] = []
    env["store"].set(key, raw)
    return key


def test_reply_c_marks_the_appointment_confirmed(env):
    from services.reply_engine import show_rate

    key = _booked_state(env)
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", reply_text="C", email_id="confirm-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert {"hook": "show_rate.mark_confirmed", "appointment_id": "appt-1", "at": NOW_BUSINESS.isoformat()} in res["hooks"]
    assert env["store"].get("confirmed:appt-1")["source"] == "reply_c"
    assert show_rate.is_confirmed(env["store"], {"id": "appt-1"}) is True
    assert env["store"].get(key)["cadence"]["booking"]["confirmed_at"] == NOW_BUSINESS.isoformat()


def test_reply_after_a_no_show_cancels_the_recovery_sequence(env):
    from services.reply_engine import no_show

    key = _booked_state(env, slot="2026-09-21T12:00:00-05:00")  # call already happened
    env["store"].set(no_show.state_key("appt-1"), {"state": "no_show", "at": NOW_BUSINESS.isoformat()})
    env["store"].set(no_show.recovery_key("appt-1", "2026-09-21T12:00:00-05:00"),
                     {"appointment": {"id": "appt-1"}, "touches": [{"key": "ns_still_on_sms"}, {"key": "ns_still_on_email"}]})
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", reply_text="Sorry I missed it", email_id="late-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    hook = [h for h in res["hooks"] if h["hook"] == "no_show.cancel_recovery"]
    assert hook and hook[0]["cancelled"] == 2
    rec = env["store"].get(no_show.recovery_key("appt-1", "2026-09-21T12:00:00-05:00"))
    assert rec["cancelled"] == "replied" and all(t["skipped"] for t in rec["touches"])
    assert env["store"].get(no_show.state_key("appt-1"))["state"] == "done"


def test_requested_time_outside_the_window_is_a_choice_not_a_silent_counter(env):
    """Ilmi asked for Wed 11:30am; the rule says 12:00-18:00 CT. Lorenzo decides."""
    ilmi = "info@shiningarmorcleaningnj.com"
    ev = ReplyEvent.from_poller_item(fixture_item(ilmi, "2026-09-21T19:00"))
    env["clock"]["now"] = CT.localize(datetime(2026, 9, 21, 14, 5))
    res = app_mod.process_event(ev, deps=env["deps"], now=env["clock"]["now"])
    assert res["requested_time"] == {"slot": "2026-09-23T11:30:00-05:00", "status": "outside_window", "lead_tz": None}
    assert "Wed 11:30am CT is a touch early on my side" in res["draft"]["body_text"]
    # 12:00 is offered: the only thing near it is Ilmi's OWN 11:30 call, and
    # config/ids.json now carries an email on that block, so the engine knows
    # the busy block belongs to the person asking to move it. Before the email
    # was there it counter-proposed 12:30/13:00, i.e. it protected her call
    # from her.
    assert res["draft"]["offered_slots"] == ["2026-09-23T12:00:00-05:00", "2026-09-23T12:30:00-05:00"]
    token = res["approval_token"]
    card = notify.sent_in_test[-1]
    # the card names the DATE: slots.format_slot carries none, and shared.slots
    # resolves "next Friday" said Mon-Thu to the following week, so a bare
    # "Book Fri 2:00pm CT" action and the lead's words can be seven days apart
    assert "view, Book Wed Sep 23 11:30am CT, https://engine.test/accept/%s" % token in card["actions"]
    # one tap books what they asked for and sends the confirmation instead
    r = env["client"].post("/accept/%s" % token)
    assert r.status_code == 200 and "Booked as asked" in r.text
    state = env["store"].get(ev.state_key)
    assert state["cadence"]["booking"]["slot"] == "2026-09-23T11:30:00-05:00"
    sent = [x for x in job_log.read_shadow_log() if x["action"] == "reply_to_email"][-1]
    assert "Locked in Wed 11:30am CT" in sent["payload"]["body"]["text"]
    # the reply goes to the address that actually wrote the thread, not the CRM
    # address: Instantly validates `to` against the thread before it sends
    assert ev.lead_email == "ilmi@shiningarmorcleaningnj.com"
    assert sent["payload"]["to"] == "info@shiningarmorcleaningnj.com" == ev.reply_from
    assert A.load(token, env["store"]) is None  # the counter-proposal token no longer verifies


def test_accept_requires_a_requested_time(env):
    state, token = _positive(env)
    r = env["client"].post("/accept/%s" % token)
    assert r.status_code == 400 and "no requested time" in r.text


def test_cadence_decision_endpoints(env):
    """The cadence decision URLs are broadcast on a public ntfy topic, so once
    REPLY_ENGINE_SECRET exists every card link carries a signed ``?t=`` and an
    unsigned GET is refused (cadence.verify_decision_token)."""
    from services.reply_engine import cadence

    state, token = _positive(env)
    email = "sopiosvanishvili@taxfoaccounting.com"
    obj = type("S", (), {"campaign_id": CAMPAIGN, "lead_email": email,
                         "cadence": env["store"].get(state_key(state))["cadence"]})()

    def signed(kind):
        return "/cadence/%s/%s/%s?t=%s" % (kind, CAMPAIGN, email, cadence.make_decision_token(kind, obj, NOW_BUSINESS))

    # unsigned is refused and writes nothing: a bare request must not stop a positive lead's ladder
    assert env["client"].get("/cadence/veto/%s/%s" % (CAMPAIGN, email)).status_code == 403
    assert env["client"].post("/cadence/veto/%s/%s" % (CAMPAIGN, email)).status_code == 403
    assert env["store"].get(cadence.veto_key(obj)) is None
    # a signed GET is only the confirmation page (F4); the POST records
    assert env["client"].get(signed("veto")).status_code == 200
    assert env["store"].get(cadence.veto_key(obj)) is None
    assert env["client"].post(signed("veto")).status_code == 200
    assert env["store"].get(cadence.veto_key(obj))["ts"] == NOW_BUSINESS.isoformat()
    assert env["client"].post(signed("approve")).status_code == 200
    assert env["store"].get(cadence.approval_key(obj, "d6"))["decision"] == "approve"
    assert env["client"].post(signed("veto-invite")).status_code == 200
    assert env["store"].get(cadence.approval_key(obj, "d6"))["decision"] == "veto"
    unknown = env["client"].get("/cadence/veto/%s/nobody@x.com" % CAMPAIGN)
    assert unknown.status_code == 403 and "nobody" not in unknown.text and CAMPAIGN not in unknown.text


def test_startup_shares_one_store_with_the_zoom_router(env):
    with TestClient(app_mod.app) as client:
        assert client.get("/health").status_code == 200
        assert app_mod.app.state.store is env["store"]


def test_inbound_without_a_time_stops_the_cadence_and_asks_for_a_fresh_draft(env):
    """cadence.stop('inbound_reply') sets needs_fresh_draft; the dict is kept so arm() can re-arm."""
    from services.reply_engine import cadence

    state, token = _positive(env)
    env["client"].post("/approve/%s" % token)
    key = state_key(state)
    # The lead's second reply is sent at 15:58 CT, after the approved answer
    # (15:30). The borrowed fixture's own time (Sep 15) would make it a reply
    # sent BEFORE the one already answered, and a card answering that is held
    # at send (approval.lead_replies_after compares send times, round 4).
    second = ReplyEvent.from_webhook(webhook_payload("rob@cjsglobal.com", "2026-09-15T22:58",
                                                     timestamp="2026-09-21T20:58:00.000Z"))
    second.campaign_id, second.lead_email = CAMPAIGN, "sopiosvanishvili@taxfoaccounting.com"
    second.email_id = "fresh-1"
    res = app_mod.process_event(second, deps=env["deps"], now=CT.localize(datetime(2026, 9, 21, 16, 0)))
    assert res["cadence_stopped"] == "inbound_reply" and res["needs_fresh_draft"] is True
    cad = env["store"].get(key)["cadence"]
    assert cad["stopped_reason"] == "inbound_reply" and cad["needs_fresh_draft"] is True
    assert cad["armed_at"] == NOW_BUSINESS.isoformat() and cad["next_send_at"] is None
    assert "fresh draft after the lead replied mid-cadence" in res["draft"]["rationale"]
    assert cadence.is_armed(LeadStateFrom(env["store"].get(key))) is False
    # approving the fresh draft re-arms the cadence from that day
    later = CT.localize(datetime(2026, 9, 21, 16, 5))
    out = A.approve(res["approval_token"], env["deps"].instantly, store=env["store"], now=later)
    assert out["ok"] and out["cadence"]["armed"] is True
    cad = env["store"].get(key)["cadence"]
    assert cad["armed_at"] == later.isoformat() and cad["stopped_reason"] is None
    assert cad["needs_fresh_draft"] is False and cad["next_send_at"] == "2026-09-22T10:00:00-05:00"


def LeadStateFrom(raw):
    from services.reply_engine.models import LeadState

    return LeadState.from_store(raw)


def test_no_send_path_exists_without_a_token_or_an_approved_template(env, monkeypatch, tmp_path):
    """With an empty template registry the first reply is never auto-sent:
    AUTO_SEND_AFTER_MINUTES is 0 by default, auto_send_due() is live-only, and
    every other send goes through approve(token). Once its template is
    approved (CT3), the same reply sends exactly once, approved_by "template"."""
    tpl = template_fixtures.make_template_env(monkeypatch, tmp_path / "tpl")
    monkeypatch.delenv("AUTO_SEND_AFTER_MINUTES", raising=False)
    assert A.auto_send_minutes() == 0
    state, token = _positive(env)
    # nothing sends on its own: flush, auto-send and a bad token all refuse
    assert A.flush_queued(env["deps"].instantly, store=env["store"], now=NOW_BUSINESS) == []
    assert A.auto_send_due(env["deps"].instantly, store=env["store"], now=NOW_BUSINESS) == []
    assert A.approve("%s.%s" % (token.split(".")[0], "0" * 32), env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)["ok"] is False
    assert A.accept_requested(token, env["deps"].ghl, env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)["ok"] is False
    assert "reply_to_email" not in [x["action"] for x in job_log.read_shadow_log()]
    # and the only send is the one Lorenzo's token authorises
    assert A.approve(token, env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)["ok"] is True
    assert [x["action"] for x in job_log.read_shadow_log()].count("reply_to_email") == 1
    assert A.load(token, env["store"]).approved_by == "lorenzo"

    # CT3: the same kind of reply from another lead, its template approved
    tpl.approve_ids("first_reply.bookkeeping_reactivation.pricing.full")
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", email_id="tpl-1",
                              lead_email="another.lead@example.invalid", firstName="Dana", companyName="Brightline Books")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert res["auto_send"]["allowed"] is True, res["auto_send"]
    sent = [x for x in job_log.read_shadow_log() if x["action"] == "reply_to_email"]
    assert len(sent) == 2 and sent[-1]["payload"]["to"] == "another.lead@example.invalid"
    card = A.load(res["approval_token"], env["store"])
    assert card.approved_by == "template" and card.status == "sent"


def test_accepted_booking_slot_stays_reserved_against_other_leads(env):
    ilmi = "info@shiningarmorcleaningnj.com"
    ev = ReplyEvent.from_poller_item(fixture_item(ilmi, "2026-09-21T19:00"))
    env["clock"]["now"] = CT.localize(datetime(2026, 9, 21, 14, 5))
    res = app_mod.process_event(ev, deps=env["deps"], now=env["clock"]["now"])
    env["client"].post("/accept/%s" % res["approval_token"])
    held = [s["slot"] for s in env["store"].get("offered_slots")]
    assert "2026-09-23T11:30:00-05:00" in held
    assert "2026-09-23T12:30:00-05:00" not in held  # the countered times went back in the pool


# ==========================================================================
# Regressions for the repaired A1 core
# ==========================================================================
def _shadow_actions():
    return [x["action"] for x in job_log.read_shadow_log()]


def _interest_values():
    return [x["payload"].get("interest_value") for x in job_log.read_shadow_log() if x["action"] == "update_interest_status"]


# ------------------------------------------------ booking must not double-book
def test_a_proposed_time_reserved_for_another_lead_is_countered_not_booked(env):
    """_reply_draft called evaluate_reply with free_slots=None and only this
    lead's own offers, so compliance() alone decided a time was bookable and the
    engine booked straight over a slot held for another lead's pending card."""
    env["store"].set(A.OFFERED_KEY, [{"slot": "2026-09-22T14:00:00-05:00", "lead": "alice@x.com",
                                      "at": NOW_BUSINESS.isoformat(), "approval": "a1"}])
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                              reply_text="Tuesday at 2pm works for me.", email_id="collide-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    assert res["booking"] is None
    assert "2026-09-22T14:00:00-05:00" not in res["draft"]["offered_slots"]
    assert "create_appointment" not in _shadow_actions()
    assert "just got taken on my calendar" in res["draft"]["body_text"]


def test_a_proposed_time_inside_a_known_busy_block_is_countered_not_booked(env):
    """config/ids.json records a Discovery Call at 2026-09-24T15:00 CT; the
    booking path discarded the busy blocks process_event had already computed."""
    payload = webhook_payload("tiffany@flowerhillfs.com", "", reply_text="Thursday at 3pm works for me.",
                              email_id="busy-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert res["booking"] is None
    assert "2026-09-24T15:00:00-05:00" not in (res["draft"]["offered_slots"] or [])
    assert "create_appointment" not in _shadow_actions()


def test_a_reply_that_names_a_third_party_or_defers_does_not_book(env):
    """booking.book() ran before any human saw the reply, so a third-party or
    'maybe later' mention of a time put a real event on the calendar."""
    for text, eid in (("Not me, but our office manager is free Wednesday at 2 if you want to try her.", "tp-1"),
                      ("We already have someone doing this. Maybe circle back Wednesday at 2.", "tp-2")):
        payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", reply_text=text, email_id=eid)
        res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
        assert res["booking"] is None, text
    assert "create_appointment" not in _shadow_actions()


# ------------------------------------------------------- Instantly status
def test_approving_a_booking_confirmation_leaves_instantly_at_meeting_booked(env):
    """send_approved hard-coded interest_value=1, overwriting the 2 that
    booking.book() had just written: every booked call showed up in Instantly as
    merely 'interested' and disagreed with the GHL opportunity in Call Booked."""
    state, token = _positive(env)
    second = ReplyEvent.from_webhook(webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37"))
    res = app_mod.process_event(second, deps=env["deps"], now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    assert res["booking"] and res["draft"]["label"] == "booking_confirmation"
    before = _interest_values()
    assert before[-1] == 2  # booking.book wrote meeting_booked
    r = env["client"].post("/approve/%s" % res["approval_token"])
    assert r.status_code == 200
    assert "reply_to_email" in _shadow_actions()
    assert _interest_values()[-1] == 2  # the confirmation did not drag it back to 1


def test_approving_a_neutral_question_writes_no_interest_status(env):
    """INTEREST_FOR_LABEL['neutral_question'] is None on purpose; the hard-coded
    1 in send_approved forced one anyway."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                              reply_text="Quick logistics question, is this a video call or a phone call?",
                              email_id="neutral-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert res["label"] == "neutral_question"
    before = len(_interest_values())
    env["client"].post("/approve/%s" % res["approval_token"])
    assert len(_interest_values()) == before


# ------------------------------------------------------- one send, exactly one
def test_two_concurrent_approvals_send_exactly_one_reply(env):
    """approve() was read-check-send-write with no lock, so a double tap on the
    ntfy action (or the Click header and the button both firing) sent the lead
    two identical emails on the same thread."""
    import threading

    state, token = _positive(env)
    sends = []
    real = env["deps"].instantly.reply_to_email

    def counting(*a, **kw):
        sends.append(kw.get("to") or (a[4] if len(a) > 4 else None))
        return real(*a, **kw)

    env["deps"].instantly.reply_to_email = counting
    results = []
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        results.append(A.approve(token, env["deps"].instantly, store=env["store"], now=NOW_BUSINESS))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(sends) == 1, sends
    assert sorted(bool(r.get("ok")) for r in results) == [False, True]
    assert A.load(token, env["store"]).status == "sent"


def test_a_send_that_fails_after_the_call_is_never_retried(env):
    """The status transition is written ahead of the Instantly call, so a crash
    between the send and the save cannot leave a re-sendable row for the poller
    to flush on the next tick."""
    state, token = _positive(env)
    approval = A.load(token, env["store"])
    A._save(type(approval).model_validate(dict(approval.model_dump(mode="json"), status="sending")), env["store"])
    out = A.approve(token, env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)
    assert out["ok"] is False and "already sending" in out["error"]
    assert "reply_to_email" not in _shadow_actions()
    assert A.flush_queued(env["deps"].instantly, store=env["store"], now=NOW_BUSINESS) == []


# ------------------------------------------------------------- idempotency
def test_a_reply_that_crashed_mid_pipeline_is_retried_without_booking_twice(env, monkeypatch):
    """Two failure modes, one claim.

    The claim must be strong enough that a retry cannot book the call twice, and
    weak enough that the reply is still answered. Writing processed_email_ids up
    front satisfied only the first: the retry answered 'duplicate', the poller
    counted that as a success, cleared its retry record and advanced the cursor,
    and a positive reply was retired without ever being drafted or shown."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37", email_id="crash-1")
    event = ReplyEvent.from_webhook(payload)

    def boom(*a, **kw):
        raise RuntimeError("store write failed")

    # NOTE: restore by re-patching, never monkeypatch.undo() - undo() also
    # reverts the tmp_env fixture's ADVERO_TMP_DIR/STORE_PATH, so every
    # assertion after it reads an empty shadow log and passes vacuously.
    real_create = app_mod.approval_mod.create_approval
    monkeypatch.setattr(app_mod.approval_mod, "create_approval", boom)
    with pytest.raises(RuntimeError):
        app_mod.process_event(event, deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    monkeypatch.setattr(app_mod.approval_mod, "create_approval", real_create)
    booked_once = _shadow_actions().count("create_appointment")
    assert booked_once == 1
    assert len(env["store"].get(event.state_key)["approvals"]) == 0
    assert env["store"].get(event.state_key)["processed_email_ids"] == []  # claimed, not processed

    again = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    assert again.get("skipped") is None
    assert again["label"] == "positive_interested" and again["approval_token"]
    # the booking the first pass already made is reused, never repeated
    assert _shadow_actions().count("create_appointment") == booked_once
    assert len(env["store"].get(event.state_key)["approvals"]) == 1
    assert env["store"].get(event.state_key)["processed_email_ids"] == ["crash-1"]
    # and now it really is a duplicate
    third = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    assert third["skipped"] == "duplicate"


def test_two_concurrent_workers_process_one_reply_once(env):
    """process_event's claim was a read-modify-write across two store calls, so
    two overlapping poller ticks (a */5 schedule and a tick that runs longer
    than five minutes) both passed the duplicate check and both ran the whole
    pipeline: two GHL write sets, two Instantly interest writes, two cards and
    four reserved slots for one inbound email."""
    import threading

    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", email_id="race-1")
    results = []
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        try:
            results.append(app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS,
                                                 busy_blocks=[]))
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertions below
            results.append({"error": str(exc)})

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 2 and not [r for r in results if r.get("error")], results
    done = [r for r in results if not r.get("skipped")]
    assert len(done) == 1, results
    assert len(notify.sent_in_test) == 1
    assert len(env["store"].get(A.OFFERED_KEY) or []) == 2   # one card, two slots
    assert _shadow_actions().count("upsert_contact") == 1


def test_the_same_reply_from_a_webhook_and_the_poller_is_processed_once(env):
    """A webhook payload with no id synthesised 'wh:<email>:<ts>', which never
    matched Instantly's real id when the poller re-delivered the same reply."""
    item = fixture_item("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    payload.pop("email_id")
    first = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert first.get("skipped") is None and first["email_id"].startswith("wh:")
    second = app_mod.process_event(ReplyEvent.from_poller_item(item), deps=env["deps"], now=NOW_BUSINESS)
    assert second["skipped"] == "duplicate"
    assert len(notify.sent_in_test) == 1


def test_two_id_less_webhooks_in_the_same_second_are_both_processed(env):
    """The mirror case: the synthesised id collapsed two different replies onto
    one key and silently dropped the second."""
    base = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    base.pop("email_id")
    a = dict(base, reply_text="How much does this cost?")
    b = dict(base, reply_text="Also, how does it work exactly?")
    first = app_mod.process_event(ReplyEvent.from_webhook(a), deps=env["deps"], now=NOW_BUSINESS)
    second = app_mod.process_event(ReplyEvent.from_webhook(b), deps=env["deps"], now=NOW_BUSINESS)
    assert first["email_id"] == second["email_id"]  # same synthesised id
    assert second.get("skipped") is None and second["approval_token"]


def test_a_second_reply_supersedes_the_pending_approval(env):
    """Two replies forty seconds apart raised two independent cards holding four
    different slots for one lead, and approving both sent two near-identical
    emails on the same thread."""
    a = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text="How much does this cost?", email_id="dup-a")
    b = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text="Also, how does it work exactly?", email_id="dup-b")
    first = app_mod.process_event(ReplyEvent.from_webhook(a), deps=env["deps"], now=NOW_BUSINESS)
    second = app_mod.process_event(ReplyEvent.from_webhook(b), deps=env["deps"], now=NOW_BUSINESS)
    assert second["superseded"] == [first["approval_token"]]
    assert A.load(first["approval_token"], env["store"]).status == "superseded"
    assert A.approve(first["approval_token"], env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)["ok"] is False
    assert A.approve(second["approval_token"], env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)["ok"] is True
    assert _shadow_actions().count("reply_to_email") == 1
    # the first card's slots went back in the pool
    held = {s["slot"] for s in env["store"].get(A.OFFERED_KEY)}
    assert held == set(second["draft"]["offered_slots"])


# ------------------------------------------------- a booked lead is left alone
def test_a_reply_from_a_booked_lead_never_offers_new_times(env):
    """The already-booked guard lived inside the names-a-time branch, so "C",
    "Confirmed, see you then." and any logistics question fell through to
    build_draft and were answered with two brand new call times."""
    key = _booked_state(env, slot="2026-09-22T14:00:00-05:00")
    for i, text in enumerate(("C", "Confirmed, see you then.",
                              "Quick question before we talk, do you need our client list in a spreadsheet?")):
        payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                                  reply_text=text, email_id="booked-%d" % i)
        res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
        assert res["draft"]["offered_slots"] == ["2026-09-22T14:00:00-05:00"], text
        assert "work for a 15-minute call" not in res["draft"]["body_text"], text
        assert "We are already set for Tue 2:00pm CT" in res["draft"]["body_text"], text
        assert res["draft"]["problems"] == [], (text, res["draft"]["problems"])
    # the only slot ever held for this lead is the one already on the calendar
    assert {s["slot"] for s in env["store"].get(A.OFFERED_KEY) or []} <= {"2026-09-22T14:00:00-05:00"}


def test_a_shadow_booking_still_yields_an_appointment_id_for_the_confirm_hook(env):
    """booking._extract_id returns None for every guarded write, so in shadow
    cadence.booking.appointment_id was always None and show_rate.mark_confirmed /
    no_show.cancel_recovery could never fire. Shadow is the only mode allowed
    before go-live, so both couplings would first have run in production."""
    from services.reply_engine import show_rate

    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37", email_id="book-hook-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"],
                                now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    booking = env["store"].get(res["state_key"])["cadence"]["booking"]
    assert booking["appointment_id"] and booking["appointment_id"].startswith("shadow-appt-")
    appointment_id = booking["appointment_id"]

    # The "C" answers the booking, so the lead sent it after the 17:37Z reply
    # (16:03 CT). The 14:42Z fixture time it used to carry made it OLDER than
    # the booking reply, and such a reply is now recorded only (S-rest round 5).
    confirm = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", reply_text="C", email_id="book-hook-2",
                              timestamp="2026-09-21T21:03:00.000Z")
    res2 = app_mod.process_event(ReplyEvent.from_webhook(confirm), deps=env["deps"],
                                 now=CT.localize(datetime(2026, 9, 21, 16, 5)))
    hooks = [h for h in res2["hooks"] if h["hook"] == "show_rate.mark_confirmed"]
    assert hooks and hooks[0]["appointment_id"] == appointment_id
    assert show_rate.is_confirmed(env["store"], {"id": appointment_id}) is True


def test_vetoing_a_booking_confirmation_cancels_the_appointment(env):
    """veto() released the offered slots and stopped there, so a refused draft
    left a real 15 minute call on Lorenzo's calendar for a lead who was never
    told the meeting existed."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37", email_id="veto-book-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"],
                                now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    assert res["booking"]["slot"] == "2026-09-24T15:00:00-05:00"
    assert _interest_values()[-1] == 2
    r = env["client"].post("/veto/%s" % res["approval_token"])
    assert r.status_code == 200
    cancels = [x for x in job_log.read_shadow_log() if x["action"] == "update_appointment_status"]
    assert cancels and cancels[-1]["payload"]["status"] == "cancelled"
    assert cancels[-1]["payload"]["appointment_id"].startswith("shadow-appt-")
    state = env["store"].get(res["state_key"])
    assert "booking" not in state["cadence"]
    assert state["cadence"]["booking_cancelled"]["slot"] == "2026-09-24T15:00:00-05:00"
    assert _interest_values()[-1] == 1  # back to interested, not left at meeting_booked
    assert "reply_to_email" not in _shadow_actions()


def test_vetoing_an_ordinary_answer_leaves_an_existing_call_alone(env):
    """Only the approval that booked the call may cancel it."""
    key = _booked_state(env, slot="2026-09-22T14:00:00-05:00")
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                              reply_text="Do you need our client list in a spreadsheet?", email_id="keep-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert res["draft"]["label"] != "booking_confirmation"
    assert env["client"].post("/veto/%s" % res["approval_token"]).status_code == 200
    assert "update_appointment_status" not in _shadow_actions()
    assert env["store"].get(key)["cadence"]["booking"]["slot"] == "2026-09-22T14:00:00-05:00"


# ------------------------------------------------------------ queue hygiene
def test_flush_queued_never_sends_a_queued_card_whose_times_passed(env):
    """A draft queued on a Friday evening and left across a weekend outage used
    to go out on Monday with slot times that had already passed. The card is no
    longer expired for it (re-review R1 item 2: approved_queued is Lorenzo's
    decision, so it is not in EXPIRABLE_STATUSES); send_approved's own time
    check refuses it instead, and nothing is sent."""
    state, token = _positive(env)
    env["clock"]["now"] = NOW_NIGHT
    assert env["client"].post("/approve/%s" % token).status_code == 200
    assert A.load(token, env["store"]).status == "approved_queued"
    # the card was created at NOW_BUSINESS, so its 48 h TTL lapsed on 09-23 15:30;
    # this is the next time the send window is open
    later = CT.localize(datetime(2026, 9, 24, 8, 0))
    assert later - timedelta(hours=A.TTL_HOURS) > CT.localize(datetime(2026, 9, 21, 15, 30))
    out = A.flush_queued(env["deps"].instantly, store=env["store"], now=later)
    assert out and out[0]["status"] == "stale_slots" and out[0]["ok"] is False
    assert A.load(token, env["store"]).status == "stale_slots"
    assert "reply_to_email" not in _shadow_actions()


def test_queued_send_after_survives_the_dst_change(env):
    """ts.replace(hour=7) kept the pre-transition offset, so an approval decided
    at 01:30 CDT on 2026-11-01 was recorded as 07:00-05:00, an hour before the
    window opens and a wall-clock time that does not exist locally that day."""
    from datetime import date

    assert A._localise_at(date(2026, 10, 30), 7).isoformat() == "2026-10-30T07:00:00-05:00"  # Friday, CDT
    assert A._localise_at(date(2026, 11, 2), 7).isoformat() == "2026-11-02T07:00:00-06:00"   # Monday, CST
    decided = CT.localize(datetime(2026, 11, 1, 1, 30), is_dst=True)
    nxt = A._next_window_open(decided)
    # 2026-11-01 is a Sunday: the queue opens Monday 07:00, in the new offset
    assert nxt.isoformat() == "2026-11-02T07:00:00-06:00"
    assert nxt > decided


def test_a_friday_evening_approval_is_never_queued_to_a_weekend_morning(env):
    """approve()/flush_queued gated on slots.within_send_window, which is
    hour-only and answers True on a Saturday. A reply approved on Friday night
    was queued to 07:00 Saturday and the unattended poller sent it there, with
    slots picked on Friday. slots.within_send_window's own docstring says
    anything that auto-sends must use is_send_time()."""
    friday_night = CT.localize(datetime(2026, 9, 25, 20, 0))
    saturday_night = CT.localize(datetime(2026, 10, 31, 20, 0))
    assert A._next_window_open(friday_night).isoformat() == "2026-09-28T07:00:00-05:00"    # Monday
    assert A._next_window_open(saturday_night).isoformat() == "2026-11-02T07:00:00-06:00"  # Monday
    # and the flush itself refuses to run on a weekend morning
    env["clock"]["now"] = friday_night
    state, token = _positive(env)
    assert env["client"].post("/approve/%s" % token).status_code == 200
    approval = A.load(token, env["store"])
    assert approval.status == "approved_queued" and approval.send_after == "2026-09-28T07:00:00-05:00"
    saturday_morning = CT.localize(datetime(2026, 9, 26, 7, 5))
    sunday_morning = CT.localize(datetime(2026, 9, 27, 7, 5))
    assert A.flush_queued(env["deps"].instantly, store=env["store"], now=saturday_morning) == []
    assert A.flush_queued(env["deps"].instantly, store=env["store"], now=sunday_morning) == []
    assert "reply_to_email" not in _shadow_actions()
    # By Monday the 48 h TTL has lapsed, but an approved card is not expired
    # (re-review R1 item 2): the queue sends it at the first business-day
    # window, as the queued page promised, and send_approved re-checks every
    # time it offers first (a time that is no longer offerable refuses it).
    monday_morning = CT.localize(datetime(2026, 9, 28, 7, 5))
    offered = A.load(token, env["store"]).draft.offered_slots
    assert offered and not A.stale_slots(offered, monday_morning)
    out = A.flush_queued(env["deps"].instantly, store=env["store"], now=monday_morning)
    assert len(out) == 1 and out[0]["status"] == "sent" and out[0]["shadow"] is True
    assert _shadow_actions().count("reply_to_email") == 1


# ----------------------------------------------------------------- the pages
def test_get_approve_only_renders_a_confirmation_page(env):
    """A GET that sends a customer email is a GET a link scanner, a prefetch or
    an incidental notification tap can fire."""
    state, token = _positive(env)
    page = env["client"].get("/approve/%s" % token)
    assert page.status_code == 200 and "Send this reply?" in page.text
    assert "<form method='post' action='/approve/%s'>" % token in page.text
    assert "reply_to_email" not in _shadow_actions()
    assert A.load(token, env["store"]).status == "pending"
    assert env["client"].post("/approve/%s" % token).status_code == 200
    assert "reply_to_email" in _shadow_actions()


def test_the_approval_card_body_carries_no_action_urls(env):
    """The message body is mirrored into the Gmail copy, where a safe-link
    scanner would fetch every URL in it."""
    state, token = _positive(env)
    card = notify.sent_in_test[-1]
    assert "https://engine.test/approve/" not in card["message"]
    assert "https://engine.test/veto/" not in card["message"]
    assert card["click"] == "https://engine.test/approve/%s" % token  # the confirmation page, not the send
    assert "view, Approve, https://engine.test/approve/%s" % token in card["actions"]


def test_reflected_path_segments_and_draft_text_are_escaped(env):
    state, token = _positive(env)
    r = env["client"].get("/cadence/veto/%s/%s" % (CAMPAIGN, "%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E@x.com"))
    # F4: an unknown lead gets the neutral 403, which echoes no path segment at all
    assert r.status_code == 403 and "<img src=x" not in r.text and "img" not in r.text
    approval = A.load(token, env["store"])
    approval.draft.body_text = "Hey <script>alert(1)</script>,\n\nLorenzo"
    A._refresh_token(approval)  # the draft hash is part of the token
    A._save(approval, env["store"])
    form = env["client"].get("/edit/%s" % approval.token)
    assert form.status_code == 200 and "<script>alert(1)</script>" not in form.text


# ==========================================================================
# Second repair pass
# ==========================================================================
class SlotGHL(object):
    """A GHL that HAS a token, so booking.verify_slot's calendar branch is live.

    _reply_draft always handed booking.book a synthetic Mon-Fri 12:00-18:00
    grid, and verify_slot only asks GHL when free_slots is None, so the calendar
    branch was dead code: a reply naming a time GHL knows is busy was booked
    over the existing event and the prospect was mailed a confirmation.
    """

    has_token = True
    calendar_id = "cal-1"
    user_id = "user-1"

    def __init__(self, free_iso):
        self.free = list(free_iso)
        self.calls = []

    def get_free_slots(self, calendar_id, start_ms, end_ms, timezone="America/Chicago", user_id=None):
        self.calls.append("get_free_slots")
        return {"slots": list(self.free)}

    def _rec(self, name):
        self.calls.append(name)
        return {"shadow": True}

    def search_contacts(self, email):
        return {"contacts": []}

    def upsert_contact(self, *a, **kw):
        return self._rec("upsert_contact")

    def upsert_opportunity(self, *a, **kw):
        return self._rec("upsert_opportunity")

    def update_opportunity_stage(self, *a, **kw):
        return self._rec("update_opportunity_stage")

    def create_note(self, *a, **kw):
        return self._rec("create_note")

    def create_task(self, *a, **kw):
        return self._rec("create_task")

    def create_appointment(self, *a, **kw):
        return self._rec("create_appointment")

    def update_appointment_status(self, *a, **kw):
        return self._rec("update_appointment_status")


def _grid(*iso):
    return list(iso)


def test_a_token_bearing_ghl_decides_availability_not_the_assumed_grid(env):
    thursday_3pm = "2026-09-24T15:00:00-05:00"
    ghl = SlotGHL(_grid("2026-09-24T16:00:00-05:00", "2026-09-25T14:00:00-05:00"))  # Thu 3pm is NOT free
    env["deps"]._ghl = ghl
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37", email_id="ghlfree-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"],
                                now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    assert "get_free_slots" in ghl.calls
    assert res["booking"] is None
    assert "create_appointment" not in ghl.calls
    assert thursday_3pm not in (res["draft"]["offered_slots"] or [])
    assert "just got taken on my calendar" in res["draft"]["body_text"]

    # the control: when GHL says the time IS free, the same request books it
    ghl2 = SlotGHL(_grid(thursday_3pm, "2026-09-25T14:00:00-05:00"))
    env["deps"]._ghl = ghl2
    payload2 = webhook_payload("tiffany@flowerhillfs.com", "2026-09-17T12:53",
                               reply_text="Thursday at 3pm works for me.", email_id="ghlfree-2")
    res2 = app_mod.process_event(ReplyEvent.from_webhook(payload2), deps=env["deps"],
                                 now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    assert res2["booking"] and res2["booking"]["slot"] == thursday_3pm
    assert "create_appointment" in ghl2.calls


# ------------------------------------------------- stale slots at send time
def test_an_approval_left_overnight_refuses_to_offer_a_time_that_has_passed(env):
    """approve() checked the status, the 48 h TTL and the send window; nothing
    re-checked the times. A draft written at 09:00 offering "Mon 2:00pm" and
    approved 25 h later went out byte-identical - and format_slot carries no
    date, so the lead reads it as the coming Monday and books nothing."""
    morning = CT.localize(datetime(2026, 9, 21, 9, 0))
    env["clock"]["now"] = morning
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", email_id="stale-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=morning, busy_blocks=[])
    offered = res["draft"]["offered_slots"]
    assert offered and offered[0].startswith("2026-09-21T")  # today
    token = res["approval_token"]

    next_day = CT.localize(datetime(2026, 9, 22, 10, 0))
    assert next_day - timedelta(hours=A.TTL_HOURS) < CT.localize(datetime(2026, 9, 21, 9, 0))  # still inside the TTL
    out = A.approve(token, env["deps"].instantly, store=env["store"], now=next_day)
    assert out["ok"] is False and out["status"] == "stale_slots"
    assert offered[0] in out["stale_slots"]
    assert "reply_to_email" not in _shadow_actions()
    # the card is not lost: it has an operator path back to pending
    back = A.retry(token, store=env["store"], now=next_day)
    assert back["ok"] is True and back["from_status"] == "stale_slots"
    assert A.load(back["token"], env["store"]).status == "pending"
    assert any("times in this draft have passed" in p for p in A.load(back["token"], env["store"]).draft.problems)


# -------------------------------------- one lead's failure is one lead's own
def test_an_interest_status_failure_after_the_send_does_not_lose_the_cadence(env):
    """instantly.update_interest_status sat outside any try/except, after the
    email had already gone out, and everything that matters came after it:
    last_outbound_at, status, the offered-slot record and the nine-touch S2
    ladder. The exception also escaped flush_queued, so every other queued lead
    in the same flush was never attempted."""
    env["clock"]["now"] = NOW_NIGHT
    first = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42", email_id="q-a")),
        deps=env["deps"], now=NOW_NIGHT, busy_blocks=[])
    second = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("tiffany@flowerhillfs.com", "2026-09-17T12:53", email_id="q-b")),
        deps=env["deps"], now=NOW_NIGHT, busy_blocks=[])
    for res in (first, second):
        assert A.approve(res["approval_token"], env["deps"].instantly, store=env["store"], now=NOW_NIGHT)["status"] == "approved_queued"

    def boom(*a, **kw):
        raise RuntimeError("HTTP 503")

    env["deps"].instantly.update_interest_status = boom
    morning = CT.localize(datetime(2026, 9, 22, 7, 5))
    out = A.flush_queued(env["deps"].instantly, store=env["store"], now=morning)
    assert len(out) == 2, out                      # neither lead was skipped
    assert all(r["ok"] for r in out), out
    assert all(r["interest_error"] == "HTTP 503" for r in out), out
    assert _shadow_actions().count("reply_to_email") == 2
    for res in (first, second):
        state = env["store"].get(res["state_key"])
        assert state["last_outbound_at"] == morning.isoformat()
        assert state["status"] == "replied_awaiting_booking"
        assert state["cadence"].get("armed_at"), state["cadence"]   # the S2 ladder still armed
        assert state["offered_slots"] == res["draft"]["offered_slots"]


# ------------------------------------------------------- superseding cards
def test_a_later_auto_reply_does_not_retire_the_positive_card(env):
    """supersede_pending ran before classification and unconditionally, so the
    out-of-office a shared info@ mailbox fires two minutes after a positive
    reply retired the positive card and put nothing in its place. 24 of the 44
    recorded replies come from auto-responders on shared boxes."""
    positive = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text="Yes I am interested, what is your percentage?", email_id="pos-1")),
        deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    first_token = positive["approval_token"]
    assert A.load(first_token, env["store"]).status == "pending"

    ooo = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_subject="Automatic reply: Sopio, question",
                        reply_text="I am out of the office until September 30 with limited access to email.",
                        email_id="ooo-1")),
        deps=env["deps"], now=CT.localize(datetime(2026, 9, 21, 15, 32)), busy_blocks=[])
    assert ooo["label"] in ("ooo", "auto_reply_unmonitored")
    assert ooo["draft"] is None
    assert ooo["superseded"] == []
    assert A.load(first_token, env["store"]).status == "pending"
    assert A.approve(first_token, env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)["ok"] is True


def test_a_second_answerable_reply_still_supersedes(env):
    """The other half of the same rule: two replies that each deserve an answer
    must still collapse to one card."""
    a = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text="How much does this cost?", email_id="sup-a")),
        deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    b = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text="Also, how does it work exactly?", email_id="sup-b")),
        deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    assert b["superseded"] == [a["approval_token"]]
    assert A.load(a["approval_token"], env["store"]).status == "superseded"


# -------------------------------------------------- a booked lead's question
def test_a_booked_lead_who_asked_nothing_gets_no_answer_paragraph(env):
    """_already_booked_draft tested '?' in the RAW event.text, which still
    carries Lorenzo's quoted cold email ("Does Wednesday at 2pm or Thursday at
    4pm Central work?"), so a lead who only restated her availability was sent
    the minimum-to-start pitch as a non sequitur."""
    key = _booked_state(env, slot="2026-09-24T15:00:00-05:00")
    body = ("Hello Lorenzo. I am available every day 3pm-6pm Estern time. let me know what wirks.\n\n"
            "On Sun, Sep 21, 2026 at 2:11 PM Lorenzo Villarreal <lorenzov@myadvero.com> wrote:\n"
            "> Hey Sopio, does Wednesday at 2pm or Thursday at 4pm Central work?\n")
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                              reply_text=body, email_id="booked-q-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    text = res["draft"]["body_text"]
    assert text == "Hey Sopio,\n\nWe are already set for Thu 3:00pm CT and the invite is on your calendar." \
                   " If that no longer works, grab another time here: %s\n\nLorenzo" % settings.BOOKING_URL
    assert "All I need to start" not in text
    assert res["draft"]["problems"] == []

    # a lead who really does ask still gets the answer
    ask = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                          reply_text="Before we talk, what is the percentage?", email_id="booked-q-2")
    res2 = app_mod.process_event(ReplyEvent.from_webhook(ask), deps=env["deps"], now=NOW_BUSINESS)
    assert "20 to 30 percent" in res2["draft"]["body_text"]


def test_a_question_containing_the_word_confirm_does_not_mark_the_call_confirmed(env):
    """_looks_like_confirmation searched for the bare word 'confirm' anywhere in
    the body, so a question that merely used it marked the Discovery Call
    confirmed and disabled the 4 h 'no C yet' safety net."""
    from services.reply_engine import show_rate

    _booked_state(env, appointment_id="appt-9", slot="2026-09-24T15:00:00-05:00")
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                              reply_text="Before we meet, can you confirm what the percentage would be?",
                              email_id="confirmq-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS)
    assert [h for h in res["hooks"] if h["hook"] == "show_rate.mark_confirmed"] == []
    assert show_rate.is_confirmed(env["store"], {"id": "appt-9"}) is not True
    for text in ("just confirming the address?", "can you confirm you got my list?"):
        assert app_mod._looks_like_confirmation(text) is False
    # a real confirmation still counts
    assert app_mod._looks_like_confirmation("C") is True
    assert app_mod._looks_like_confirmation("Confirmed, see you then.") is True
    assert app_mod._looks_like_confirmation("Confirming for Thursday.") is True


# ------------------------------------------------------------- GET /veto
def test_get_veto_only_renders_a_confirmation_page(env):
    """/approve and /accept were moved behind POST because a GET that has a
    customer-visible effect is a GET a link scanner, a browser prefetch or a
    forwarded card can fire. /veto was left on GET while doing more than either:
    for a booking_confirmation it cancels the GHL appointment (GHL mails the
    lead a cancellation), reverts the opportunity and rewrites the Instantly
    interest."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37", email_id="vetoget-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"],
                                now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    token = res["approval_token"]
    assert res["draft"]["label"] == "booking_confirmation"

    page = env["client"].get("/veto/%s" % token)
    assert page.status_code == 200 and "Veto this reply?" in page.text
    assert "<form method='post' action='/veto/%s'>" % token in page.text
    assert "The call this reply booked will also be cancelled." in page.text
    assert A.load(token, env["store"]).status == "pending"
    assert "update_appointment_status" not in _shadow_actions()

    assert env["client"].post("/veto/%s" % token).status_code == 200
    assert A.load(token, env["store"]).status == "vetoed"
    assert "update_appointment_status" in _shadow_actions()


# ---------------------------------------------------------------- /edit
def test_edit_rejects_the_other_offer_types_proof_line(env):
    """edit() called validate_draft with no campaign_key, and
    draft.wrong_offer_proof_problems returns [] whenever the key is falsy - so
    the one path where a human rewrites the email by hand had the cross-offer
    guard disabled, and POST /edit approves and sends immediately."""
    res = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("tiffany@flowerhillfs.com", "2026-09-17T12:53", email_id="edit-proof-1")),
        deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    token = res["approval_token"]
    assert A.load(token, env["store"]).campaign_key == "cleaning_trigger"
    reactivation_proof = ("I built a similar system for a commercial roofer doing $150M/year. "
                          "I recovered about $6M worth of contracts within 6 months.")
    body = "Hey Tiffany,\n\n%s\n\nOr if it's easier, grab a time here: %s\n\nLorenzo" % (
        reactivation_proof, settings.BOOKING_URL)
    r = env["client"].post("/edit/%s" % token, data={"body": body})
    assert r.status_code == 400 and "never mixed" in r.text
    assert "reply_to_email" not in _shadow_actions()
    assert A.load(token, env["store"]).status == "pending"


def test_edit_moves_the_slot_reservations_to_the_times_lorenzo_actually_wrote(env):
    """edit() replaced only the body: draft.offered_slots and the global
    OFFERED_KEY registry kept pointing at the times he had just replaced, so the
    next lead's card could be offered the same times he wrote here, while the
    times he deleted stayed blocked for everyone."""
    state, token = _positive(env)
    original = A.load(token, env["store"]).draft.offered_slots
    assert len(original) == 2
    assert sorted(s["slot"] for s in env["store"].get(A.OFFERED_KEY)) == sorted(original)

    body = ("Hey Sopio,\n\nNothing up front, $0 if nothing closes.\n\nWould Wed 1:00pm or Thu 4:00pm CT work? "
            "Or if it's easier, grab a time here: %s\n\nLorenzo" % settings.BOOKING_URL)
    out = A.edit(token, body, store=env["store"], now=NOW_BUSINESS)
    assert out["ok"] is True
    assert out["offered_slots"] == ["2026-09-23T13:00:00-05:00", "2026-09-24T16:00:00-05:00"]
    approval = A.load(out["token"], env["store"])
    assert approval.draft.offered_slots == out["offered_slots"]
    held = sorted(s["slot"] for s in env["store"].get(A.OFFERED_KEY))
    assert held == sorted(out["offered_slots"])
    for iso in original:
        assert iso not in held      # given back to the pool
    # and the send records the times he actually wrote
    assert A.approve(out["token"], env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)["ok"] is True
    assert env["store"].get(state_key(state))["offered_slots"] == out["offered_slots"]


# ----------------------------------------------- accept must still check free
def test_book_as_asked_still_refuses_a_time_that_is_already_taken(env):
    """accept_requested passed free_slots=[the slot being booked], which makes
    booking.verify_slot's membership test a tautology: both the GHL branch and
    the known-booking fallback were bypassed, so the override waived
    availability as well as Lorenzo's slot rule."""
    ilmi = "info@shiningarmorcleaningnj.com"
    ev = ReplyEvent.from_poller_item(fixture_item(ilmi, "2026-09-21T19:00"))
    env["clock"]["now"] = CT.localize(datetime(2026, 9, 21, 14, 5))
    res = app_mod.process_event(ev, deps=env["deps"], now=env["clock"]["now"])
    token = res["approval_token"]
    assert res["requested_time"]["slot"] == "2026-09-23T11:30:00-05:00"

    # another lead's pending card already holds that time
    env["store"].append(A.OFFERED_KEY, {"slot": "2026-09-23T11:30:00-05:00", "lead": "alice@x.com",
                                        "at": env["clock"]["now"].isoformat(), "approval": "other"})
    r = env["client"].post("/accept/%s" % token)
    assert r.status_code == 400 and "no longer free" in r.text
    assert "create_appointment" not in _shadow_actions()
    assert env["store"].get(ev.state_key)["cadence"].get("booking") is None

    # with the collision gone the override works, and it is still an override:
    # 11:30 is outside Lorenzo's own 12:00-18:00 rule
    env["store"].set(A.OFFERED_KEY, [r for r in env["store"].get(A.OFFERED_KEY) if r.get("approval") != "other"])
    ok = env["client"].post("/accept/%s" % token)
    assert ok.status_code == 200 and "Booked as asked" in ok.text
    assert env["store"].get(ev.state_key)["cadence"]["booking"]["slot"] == "2026-09-23T11:30:00-05:00"


# ------------------------------------------------- a webhook with no email id
def test_a_reply_with_no_instantly_email_id_is_never_sent_in_thread(env):
    """from_webhook synthesises 'wh:<email>:<ts>' when the payload carries no
    id, and that string went straight through to instantly.reply_to_email as
    reply_to_uuid. `to` means it cannot be mis-delivered, but a real workspace
    answers 4xx and the card ends at send_failed, which nothing watches."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    payload.pop("email_id")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    assert res["email_id"].startswith("wh:")
    assert any("without an Instantly email id" in p for p in res["draft"]["problems"])
    out = A.approve(res["approval_token"], env["deps"].instantly, store=env["store"], now=NOW_BUSINESS)
    assert out["ok"] is False and out["status"] == "blocked"
    assert "reply_to_email" not in _shadow_actions()
    page = env["client"].post("/approve/%s" % res["approval_token"])
    assert page.status_code == 400 and "reply by hand" in page.text
    assert "unknown" not in page.text


def test_a_blocked_draft_says_why_instead_of_unknown(env):
    """send_approved's blocked return carries `problems`, not `error`, and the
    page rendered result.get("error", "unknown")."""
    state, token = _positive(env)
    approval = A.load(token, env["store"])
    approval.draft.problems = ["mentions automation"]
    A._refresh_token(approval)
    A._save(approval, env["store"])
    page = env["client"].post("/approve/%s" % approval.token)
    assert page.status_code == 400
    assert "mentions automation" in page.text and "unknown" not in page.text
    assert "/edit/%s" % approval.token in page.text


# ----------------------------------------------------------- dedupe window
def test_the_same_nudge_days_later_is_answered_not_dropped(env):
    """content_fingerprint has no time component and processed_keys was kept
    forever, so a lead sending "Any update on this?" and the identical nudge
    three days later got {'skipped': 'duplicate'}: no classification, no draft,
    no card, no CRM note. The cross-source race the fingerprint exists for
    happens within minutes."""
    nudge = "Any update on this? We are still interested in hearing more."
    first = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text=nudge, email_id="nudge-1")),
        deps=env["deps"], now=NOW_BUSINESS, busy_blocks=[])
    assert first.get("skipped") is None and first["approval_token"]

    # ten minutes later, same words, a different provider id: the cross-source
    # duplicate this is for
    same_day = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text=nudge, email_id="nudge-1b")),
        deps=env["deps"], now=CT.localize(datetime(2026, 9, 21, 15, 40)), busy_blocks=[])
    assert same_day["skipped"] == "duplicate"

    later = app_mod.process_event(ReplyEvent.from_webhook(
        webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42",
                        reply_text=nudge, email_id="nudge-2")),
        deps=env["deps"], now=CT.localize(datetime(2026, 9, 24, 10, 0)), busy_blocks=[])
    assert later.get("skipped") is None, later
    assert later["approval_token"] and later["label"] == first["label"]
    assert len(notify.sent_in_test) == 2


# ------------------------------------------------------------ deploy config
def test_the_webhook_secret_falls_back_to_the_name_the_deploy_path_sets(env, monkeypatch):
    """changesets/instantly_webhooks.py mints X-Advero-Secret from
    REPLY_ENGINE_SECRET, the runbook documents it as <REPLY_ENGINE_SECRET> and
    modal_app.SECRET_KEYS ships only that name, while _secret_ok validated
    against WEBHOOK_SECRET, which no deploy path sets. Every webhook delivery
    would have been refused 401 at go-live."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    assert post_webhook(env, payload, secret="unit-secret").status_code == 200
    assert post_webhook(env, payload, secret="hook-secret").status_code == 401
    assert post_webhook(env, payload, secret=None).status_code == 401
    # WEBHOOK_SECRET still wins when a deployment does set both
    monkeypatch.setenv("WEBHOOK_SECRET", "hook-secret")
    assert app_mod.webhook_secret() == "hook-secret"
    # and with neither name set nothing is accepted
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    assert app_mod._secret_ok("anything") is False


def test_an_approval_card_lorenzo_cannot_act_on_is_refused_in_live(env, monkeypatch, live_mode):
    """base_url() silently defaulted to http://localhost:8000, so every
    Approve/Veto/Edit URL was dead on his phone; NTFY_TOPIC with no NTFY_TOKEN
    makes shared.notify strip the Actions and Click headers and append
    "(details in the email)" with no email leg configured; and notify() still
    answers sent=True, so the push_failed alarm never fires and
    poller.pending_approvals reports pushed=True."""
    assert A.base_url() == "https://engine.test"
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    with pytest.raises(A.ApprovalUndeliverable):
        A.base_url()
    monkeypatch.setenv("REPLY_ENGINE_BASE_URL", "https://engine.test")
    assert A.base_url() == "https://engine.test"

    for name in ("NOTIFY_EMAIL", "NOTIFICATION_EMAIL", "GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NTFY_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    channels = A.deliverable_channels()
    assert channels == {"ntfy_actions": False, "email": False, "any": False}
    with pytest.raises(A.ApprovalUndeliverable):
        A.require_deliverable_channel()
    # an email leg is enough on its own
    monkeypatch.setenv("NOTIFY_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x" * 16)
    assert A.deliverable_channels()["any"] is True
    assert A.require_deliverable_channel()["email"] is True


def test_shadow_never_fails_closed_on_the_card_channel(env, monkeypatch):
    """The fail-closed checks are live-only: shadow must still produce cards."""
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    for name in ("NOTIFY_EMAIL", "NOTIFICATION_EMAIL", "GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NTFY_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    assert A.base_url() == A.DEV_BASE_URL
    assert A.require_deliverable_channel()["any"] is False
    state, token = _positive(env)
    assert A.load(token, env["store"]).status == "pending"


def test_the_debug_secret_is_header_only_in_live(env, monkeypatch):
    """Both secrets were accepted as a query parameter, so they landed in proxy
    and platform access logs and in the Referer of any link the page led to -
    beside the lead's email address, which is in the path."""
    _positive(env)
    monkeypatch.setenv("DEBUG_SECRET", "dbg")
    email = "sopiosvanishvili@taxfoaccounting.com"
    assert env["client"].get("/state/%s?secret=dbg" % email).status_code == 200
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert env["client"].get("/state/%s?secret=dbg" % email).status_code == 401
    assert env["client"].get("/state/%s" % email, headers={"X-Advero-Secret": "dbg"}).status_code == 200


# ------------------------------------------- an expiring card must not leave a call
def test_an_expired_booking_confirmation_leaves_the_call_until_lorenzo_releases_it(env):
    """_reply_draft books the call at classification time, before any approval
    token exists. An expiring card used to cancel that call on its own; now
    (SAL-6) expiry writes nothing to GHL: the call and its held reminders
    stay, the card cannot be sent, and Lorenzo's Release cancels it silently."""
    payload = webhook_payload("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37", email_id="expire-book-1")
    res = app_mod.process_event(ReplyEvent.from_webhook(payload), deps=env["deps"],
                                now=CT.localize(datetime(2026, 9, 21, 16, 0)), busy_blocks=[])
    assert res["draft"]["label"] == "booking_confirmation"
    assert env["store"].get(res["state_key"])["cadence"]["booking"]["slot"] == "2026-09-24T15:00:00-05:00"
    assert _interest_values()[-1] == 2

    too_late = CT.localize(datetime(2026, 9, 24, 9, 0))   # past the 48 h TTL
    out = A.approve(res["approval_token"], env["deps"].instantly, store=env["store"], now=too_late,
                    ghl=env["deps"].ghl)
    assert out["ok"] is False and out["status"] == "expired" and out["booking_held"]
    assert not [x for x in job_log.read_shadow_log() if x["action"] == "update_appointment_status"]
    assert env["store"].get(res["state_key"])["cadence"]["booking"]["slot"] == "2026-09-24T15:00:00-05:00"
    released = A.decide_expired_booking(res["approval_token"], "release", ghl=env["deps"].ghl,
                                        instantly=env["deps"].instantly, store=env["store"], now=too_late)
    assert released["ok"] is True and released["choice"] == "release"
    cancels = [x for x in job_log.read_shadow_log() if x["action"] == "update_appointment_status"]
    assert cancels and cancels[-1]["payload"]["status"] == "cancelled" and cancels[-1]["payload"]["toNotify"] is False
    state = env["store"].get(res["state_key"])
    assert "booking" not in state["cadence"]
    assert state["cadence"]["booking_cancelled"]["slot"] == "2026-09-24T15:00:00-05:00"
    assert _interest_values()[-1] == 1
    assert env["store"].get(A.OFFERED_KEY) == []
    assert "reply_to_email" not in _shadow_actions()


def test_an_expiring_card_that_booked_nothing_touches_no_calendar(env):
    state, token = _positive(env)
    too_late = CT.localize(datetime(2026, 9, 24, 9, 0))
    out = A.approve(token, env["deps"].instantly, store=env["store"], now=too_late, ghl=env["deps"].ghl)
    assert out["ok"] is False and out["status"] == "expired"
    assert "update_appointment_status" not in _shadow_actions()


# --------------------------------------------- the second recipient belt
class ThreadReader(object):
    """An Instantly whose get_email() says who really wrote the thread."""

    def __init__(self, sender):
        self.sender = sender
        self.sent = []

    def get_email(self, email_id):
        return {"id": email_id, "from_address_email": self.sender}

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        self.sent.append({"reply_to_uuid": reply_to_uuid, "to": to})
        return {"shadow": False, "id": "sent-1"}

    def update_interest_status(self, *a, **kw):
        return {"shadow": False}


def test_the_first_reply_carries_both_recipient_belts(env, monkeypatch, live_mode):
    """config/instantly_api_contract.md and CLAUDE.md both say recipient safety
    on POST /emails/reply is enforced twice and neither half may be removed.
    grep found thread_recipient_ok at exactly two sites, both inside
    cadence._send: approval.send_approved - the first human-approved reply, the
    highest-stakes send there is - called reply_to_email directly with no
    re-read. `to` is derived from the same message, so it is self-consistent by
    construction and cannot catch a stale or crossed reply_to_uuid, which is
    exactly what the second belt exists for."""
    # This live-mode test needs a deliverable approval channel. It used to get
    # one by accident: conftest let shared.settings.load_env() leave Lorenzo's
    # real GMAIL_* credentials in the process. conftest now drops them (they
    # were also being used to send real mail), so the test supplies its own
    # dummy leg and no longer depends on what is in anyone's .env.
    monkeypatch.setenv("NOTIFY_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "lorenzo@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x" * 16)
    state, token = _positive(env)
    approval = A.load(token, env["store"])

    crossed = ThreadReader("somebody.else@other.com")
    out = A.approve(token, crossed, store=env["store"], now=NOW_BUSINESS, ghl=env["deps"].ghl)
    assert out["ok"] is False and out["error"] == "recipient_mismatch"
    assert crossed.sent == []
    assert A.load(token, env["store"]).status == "send_failed"

    # the operator path back, and then a thread that really is theirs
    assert A.retry(token, store=env["store"], now=NOW_BUSINESS)["ok"] is True
    good = ThreadReader(approval.reply_to or approval.lead_email)
    ok = A.approve(A.load(token, env["store"]).token, good, store=env["store"], now=NOW_BUSINESS,
                   ghl=env["deps"].ghl)
    assert ok["ok"] is True and ok["status"] == "sent"
    assert good.sent and good.sent[0]["to"] == (approval.reply_to or approval.lead_email)
