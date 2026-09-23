"""S4 show-rate sequence: schedule math, DST, past-time skips, A2P gating,
re-entry, copy rules, and zero HTTP in shadow."""
import json
import os
from datetime import datetime, timedelta

import httpx
import pytest
import pytz

from shared import job_log, slots
from shared.ghl import GHL
from shared.store import JsonFileStore

from services.reply_engine import show_rate as sr

CT = pytz.timezone("America/Chicago")
# Monday 17:10 CT: inside the 07:00-19:00 send window, so a T+0 confirmation
# is armed for right now. NIGHT is the same evening after the window closes.
NOW = datetime.fromisoformat("2026-09-21T17:10:00-05:00")
NIGHT = datetime.fromisoformat("2026-09-21T21:10:00-05:00")

ILMI = {
    "id": "gcal_eqlug7qn67rnjdppja91ffuto0",
    "contact_id": "cnfZoGRCRi3JMqZfo0XD",
    "first_name": "Ilmi",
    "company": "Shining Armor Cleaning NJ",
    "email": "ilmi@shiningarmorcleaningnj.com",
    "niche": "cleaning",
    "offer": "reactivation",
    "lead_tz": "America/New_York",
    "start_iso": "2026-09-23T11:30:00-05:00",
    "end_iso": "2026-09-23T11:45:00-05:00",
    "zoom_link": "https://zoom.us/j/000000000001",
}


class Recorder(object):
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})


def make_ghl(token=None):
    rec = Recorder()
    return GHL(token=token, transport=httpx.MockTransport(rec)), rec


def by_key(touches):
    return {t.template_key: t for t in touches}


def just_booked(appointment=None, at=None):
    """A lead who booked this minute.

    A real GHL calendar event carries dateAdded, which normalise_ghl_event maps
    to booked_at. Without it the engine fails closed on a cold store (see
    test_a_cold_start_does_not_confirm_bookings_it_has_never_seen), so any test
    that means "someone just booked" has to say so.
    """
    return dict(appointment or ILMI, booked_at=(at or NOW).isoformat())


# ------------------------------------------------------------ schedule
def test_exact_sequence_and_order():
    touches = sr.schedule_for(ILMI, NOW)
    assert [t.template_key for t in touches] == [
        "confirm_email", "confirm_sms", "preread_email", "reminder_24h_sms", "reminder_24h_email",
        "unconfirmed_task", "reminder_1h_sms", "reminder_15m_sms",
    ]
    assert [t.channel for t in touches] == ["email", "sms", "email", "sms", "email", "task", "sms", "sms"]
    assert all(t.appointment_id == ILMI["id"] and t.contact_id == ILMI["contact_id"] for t in touches)
    assert len({t.key for t in touches}) == 8


def test_offsets_relative_to_start_and_booking():
    t = by_key(sr.schedule_for(ILMI, NOW))
    start = slots.parse_iso(ILMI["start_iso"])
    assert t["confirm_email"].when() == NOW
    assert t["preread_email"].when() == NOW + timedelta(minutes=15)
    assert t["reminder_24h_email"].when() == start - timedelta(hours=24)
    assert t["reminder_24h_sms"].when() == start - timedelta(hours=24)
    assert t["unconfirmed_task"].when() == start - timedelta(hours=4)
    assert t["reminder_1h_sms"].when() == start - timedelta(hours=1)
    assert t["reminder_15m_sms"].when() == start - timedelta(minutes=15)
    # when_iso is CT with offset
    assert t["reminder_24h_email"].when_iso == "2026-09-22T11:30:00-05:00"
    assert t["unconfirmed_task"].when_iso == "2026-09-23T07:30:00-05:00"


def test_dst_fall_back_24h_is_24_real_hours():
    # DST ends 2026-11-01 02:00 CDT. A 13:00 CST call the same day: "24 h before"
    # must be Sat 14:00pm CDT (24 real hours), not a naive 13:00 the day before.
    appt = dict(ILMI, start_iso="2026-11-01T13:00:00-06:00", end_iso="2026-11-01T13:15:00-06:00")
    now = datetime.fromisoformat("2026-10-30T10:00:00-05:00")
    t = by_key(sr.schedule_for(appt, now, a2p=True))
    start = slots.parse_iso(appt["start_iso"])
    r24 = t["reminder_24h_email"].when()
    assert start - r24 == timedelta(hours=24)
    assert t["reminder_24h_email"].when_iso == "2026-10-31T14:00:00-05:00"
    assert t["reminder_1h_sms"].when_iso == "2026-11-01T12:00:00-06:00"
    assert start - t["unconfirmed_task"].when() == timedelta(hours=4)


def test_dst_spring_forward_24h():
    # DST starts 2026-03-08 02:00 CST -> 03:00 CDT. Monday 12:00 CDT call.
    appt = dict(ILMI, start_iso="2026-03-09T12:00:00-05:00", end_iso="2026-03-09T12:15:00-05:00")
    now = datetime.fromisoformat("2026-03-06T10:00:00-06:00")
    t = by_key(sr.schedule_for(appt, now, a2p=True))
    start = slots.parse_iso(appt["start_iso"])
    assert start - t["reminder_24h_email"].when() == timedelta(hours=24)
    assert t["reminder_24h_email"].when_iso == "2026-03-08T12:00:00-05:00"
    assert start - t["reminder_15m_sms"].when() == timedelta(minutes=15)
    assert not t["reminder_24h_email"].skipped


def test_booking_inside_24h_skips_past_touches():
    now = datetime.fromisoformat("2026-09-23T09:00:00-05:00")  # 2.5 h before the 11:30 call
    t = by_key(sr.schedule_for(ILMI, now, a2p=True))
    assert t["reminder_24h_email"].skipped and t["reminder_24h_email"].skip_reason == "past_time"
    assert t["reminder_24h_sms"].skipped and t["reminder_24h_sms"].skip_reason == "past_time"
    assert t["unconfirmed_task"].skipped and t["unconfirmed_task"].skip_reason == "past_time"  # 07:30 already gone
    assert not t["reminder_1h_sms"].skipped
    assert not t["reminder_15m_sms"].skipped
    assert not t["confirm_email"].skipped and not t["preread_email"].skipped


def test_booking_after_start_skips_all_reminders_but_keeps_confirmation():
    now = datetime.fromisoformat("2026-09-23T11:40:00-05:00")
    t = by_key(sr.schedule_for(ILMI, now, a2p=True))
    for k in ("reminder_24h_email", "reminder_24h_sms", "unconfirmed_task", "reminder_1h_sms", "reminder_15m_sms"):
        assert t[k].skipped and t[k].skip_reason == "past_time", k
    assert not t["confirm_email"].skipped


# ------------------------------------------------------------ A2P gating
def test_sms_legs_skipped_until_a2p_registered(monkeypatch):
    monkeypatch.delenv(sr.A2P_ENV, raising=False)
    touches = sr.schedule_for(ILMI, NOW)
    sms = [t for t in touches if t.channel == "sms"]
    assert len(sms) == 4
    assert all(t.skipped and t.skip_reason == "a2p_not_registered" for t in sms)
    assert all(t.body for t in sms)  # generated, just not sent
    monkeypatch.setenv(sr.A2P_ENV, "1")
    touches = sr.schedule_for(ILMI, NOW)
    sms = [t for t in touches if t.channel == "sms"]
    assert not any(t.skipped for t in sms)
    monkeypatch.delenv(sr.A2P_ENV, raising=False)
    assert not any(t.skipped for t in sr.schedule_for(ILMI, NOW, a2p=True) if t.channel == "sms")


def test_night_time_confirmation_defers_to_07_ct_on_both_channels():
    """CLAUDE.md: "sends only 07:00-19:00 CT". The widget takes bookings at any
    hour, and only the SMS leg used to be gated, so a 02:04 booking emailed
    "Locked in ..." at 02:05."""
    t = by_key(sr.schedule_for(ILMI, NIGHT, a2p=True))  # NIGHT is 21:10 CT
    assert t["confirm_sms"].when_iso == "2026-09-22T07:00:00-05:00"
    assert t["confirm_sms"].meta["deferred_from"] == "2026-09-21T21:10:00-05:00"
    assert t["confirm_email"].when_iso == "2026-09-22T07:00:00-05:00"
    assert t["confirm_email"].meta["deferred_from"] == "2026-09-21T21:10:00-05:00"
    assert t["preread_email"].when_iso == "2026-09-22T07:00:00-05:00"
    # inside the window nothing is deferred
    day = by_key(sr.schedule_for(ILMI, NOW, a2p=True))
    assert day["confirm_email"].when_iso == NOW.isoformat()
    assert "deferred_from" not in day["confirm_email"].meta


def test_confirmed_appointment_skips_the_4h_task():
    t = by_key(sr.schedule_for(dict(ILMI, confirmed=True), NOW))
    assert t["unconfirmed_task"].skipped and t["unconfirmed_task"].skip_reason == "confirmed"


# ------------------------------------------------------------ copy
def test_copy_rules_no_em_dash_signed_lorenzo_no_automation_talk(monkeypatch):
    monkeypatch.delenv("LOOM_URL_CLEANING", raising=False)
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        appt = dict(ILMI, niche=niche)
        for t in sr.schedule_for(appt, NOW, a2p=True):
            text = (t.subject or "") + "\n" + t.body
            assert "—" not in text, (niche, t.template_key)
            low = text.lower()
            assert "automat" not in low and " ai " not in low and "a.i." not in low, (niche, t.template_key)
            if t.channel == "email":
                assert t.body.rstrip().endswith("Lorenzo"), (niche, t.template_key)
                assert t.subject
    t = by_key(sr.schedule_for(ILMI, NOW))
    body = t["confirm_email"].body
    assert body.count("\n- ") == 3  # three-bullet agenda
    assert "calendar invite" in body
    assert "[Loom:" not in body and "walkthrough" not in body  # no URL configured: the line is dropped
    assert not sr.has_unresolved_placeholder(body)
    assert "https://zoom.us/j/000000000001" in body
    assert "Wed, Sep 23 at 11:30am CT (12:30pm ET)" in body  # lead tz shown, am/pm on both (ZC item 8)
    assert "Reply C to confirm" in t["reminder_24h_email"].body
    assert "Reply C" in t["reminder_24h_sms"].body
    assert "Hopping on now" in t["reminder_15m_sms"].body
    assert "https://zoom.us/j/000000000001" in t["reminder_1h_sms"].body
    assert "Unconfirmed call" in t["unconfirmed_task"].subject
    assert all(len(x.body) <= sr.SMS_MAX_LEN for x in t.values() if x.channel == "sms")


def test_loom_url_from_env_replaces_placeholder(monkeypatch):
    monkeypatch.setenv("LOOM_URL_CLEANING", "https://www.loom.com/share/abc")
    body = by_key(sr.schedule_for(ILMI, NOW))["confirm_email"].body
    assert "https://www.loom.com/share/abc" in body and "[Loom:" not in body
    assert not sr.has_unresolved_placeholder(body)


def test_prereads_are_per_niche():
    texts = {}
    for niche in ("cleaning", "bookkeeping", "recruiting"):
        texts[niche] = by_key(sr.schedule_for(dict(ILMI, niche=niche), NOW))["preread_email"].body
    assert "janitorial" in texts["cleaning"] and "60 or more lost or dormant accounts" in texts["cleaning"]
    assert "tax season" in texts["bookkeeping"]
    assert "placement fee" in texts["recruiting"]
    for body in texts.values():
        assert "Ilmi" in body and "Shining Armor Cleaning NJ" in body and "Wed, Sep 23" in body
        assert "{" not in body and "#" not in body
        assert body.rstrip().endswith("Lorenzo")
    assert sr.niche_of({"company": "Taxfo Accounting"}) == "bookkeeping"
    assert sr.niche_of({"campaign_key": "recruiting_outbound"}) == "recruiting"
    assert sr.offer_of({"campaign_key": "cleaning_trigger"}) == "outbound"


# ------------------------------------------------------------ re-entry
def test_ensure_scheduled_is_idempotent_and_reschedule_safe(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    first = sr.ensure_scheduled(store, just_booked(), NOW)
    again = sr.ensure_scheduled(store, ILMI, NOW + timedelta(minutes=30))
    assert first["created"] is True and again["created"] is False
    assert again["key"] == first["key"] == sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")
    assert len(store.keys("showrate:")) == 1
    # Ilmi moves the call to Thursday 14:00
    moved = dict(ILMI, start_iso="2026-09-24T14:00:00-05:00", end_iso="2026-09-24T14:15:00-05:00")
    res = sr.ensure_scheduled(store, moved, NOW + timedelta(hours=1))
    assert res["created"] is True and res["cancelled"] == [first["key"]]
    old = store.get(first["key"])
    assert old["superseded_by"] == res["key"]
    assert all(t["skipped"] and t["skip_reason"] in ("rescheduled", "a2p_not_registered") for t in old["touches"])
    pending = sr.pending_touches(store)
    assert pending and all(t["appointment_id"] == ILMI["id"] and t["meta"]["start_iso"] == "2026-09-24T14:00:00-05:00" for t in pending)


# ------------------------------------------------------------ run (shadow)
def test_run_in_shadow_sends_nothing_and_logs_would_do(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    out = sr.run(NOW, store, ghl, appointments=[just_booked()])
    assert out["scheduled"] == [sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")]
    assert [e["template"] for e in out["would_do"]] == ["confirm_email"]
    assert out["sent"] == [] and out["errors"] == []
    assert rec.requests == []  # zero HTTP in shadow
    log = job_log.read_shadow_log()
    assert log[-1]["system"] == "ghl" and log[-1]["action"] == "send_message"
    assert log[-1]["payload"]["type"] == "Email" and log[-1]["payload"]["contactId"] == ILMI["contact_id"]
    # idempotent: a second tick at the same time sends nothing new
    out2 = sr.run(NOW, store, ghl)
    assert out2["would_do"] == [] and out2["sent"] == []
    # +15 min: pre-read
    out3 = sr.run(NOW + timedelta(minutes=16), store, ghl)
    assert [e["template"] for e in out3["would_do"]] == ["preread_email"]
    # 24 h before
    start = slots.parse_iso(ILMI["start_iso"])
    out4 = sr.run(start - timedelta(hours=23, minutes=59), store, ghl)
    assert [e["template"] for e in out4["would_do"]] == ["reminder_24h_email"]
    assert {e["reason"] for e in out4["skipped"]} <= {"a2p_not_registered"}
    # 4 h before, no C reply: task for Lorenzo
    out5 = sr.run(start - timedelta(hours=3, minutes=59), store, ghl)
    assert [e["template"] for e in out5["would_do"]] == ["unconfirmed_task"]
    assert job_log.read_shadow_log()[-1]["action"] == "create_task"
    # past start: nothing more, remaining reminders marked appointment_started
    out6 = sr.run(start + timedelta(minutes=1), store, ghl)
    assert out6["would_do"] == []
    assert rec.requests == []
    assert sr.pending_touches(store) == []


def test_reply_c_confirmation_cancels_the_4h_task(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[just_booked()])
    start = slots.parse_iso(ILMI["start_iso"])
    sr.mark_confirmed(store, ILMI["id"], start - timedelta(hours=20))
    out = sr.run(start - timedelta(hours=3, minutes=59), store, ghl)
    assert "unconfirmed_task" not in [e["template"] for e in out["would_do"]]
    assert {"key": ILMI["id"] + ":2026-09-23T11:30:00-05:00:unconfirmed_task", "reason": "confirmed"} in [
        {"key": e["key"], "reason": e.get("reason")} for e in out["skipped"]]
    assert not [r for r in job_log.read_shadow_log() if r["action"] == "create_task"]
    assert sr.is_confirmed(store, {"id": "x", "tags": ["call-confirmed"]})
    assert rec.requests == []


def test_live_mode_with_mock_transport_posts_to_ghl(tmp_env, live_mode, monkeypatch):
    monkeypatch.setenv("LOOM_URL_CLEANING", "https://www.loom.com/share/abc")
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token="tok")
    out = sr.run(NOW, store, ghl, appointments=[just_booked()])
    assert [e["template"] for e in out["sent"]] == ["confirm_email"]
    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert req.method == "POST" and req.url.path == "/conversations/messages"
    body = json.loads(req.content.decode("utf-8"))
    assert body["type"] == "Email" and body["contactId"] == ILMI["contact_id"] and body["subject"].startswith("Confirmed:")


def test_confirmation_still_goes_out_live_without_a_loom_url(tmp_env, live_mode, monkeypatch):
    """The Loom line is optional copy. It used to be a [Loom: ...] placeholder,
    which the live-mode guard then silently dropped: on go-live day nobody got
    the T+0 confirmation at all, and run() marked it permanently skipped."""
    monkeypatch.delenv("LOOM_URL_CLEANING", raising=False)
    monkeypatch.delenv("LOOM_URL_GENERIC", raising=False)
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token="tok")
    out = sr.run(NOW, store, ghl, appointments=[just_booked()])
    assert [e["template"] for e in out["sent"]] == ["confirm_email"]
    assert not any(e.get("reason") == "unresolved_placeholder" for e in out["skipped"])
    body = json.loads(rec.requests[0].content.decode("utf-8"))["message"]
    assert "[Loom:" not in body and "Locked in for" in body


def test_live_mode_still_refuses_an_unrendered_template_placeholder(tmp_env, live_mode):
    """The placeholder guard stays for real unrendered variables."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token="tok")
    touch = sr.schedule_for(ILMI, NOW)[0]
    touch.body = "Hey {{first_name}}, locked in."
    assert sr.has_unresolved_placeholder(touch.body)
    assert sr.dispatch_touch(touch, ghl, NOW) == {"status": "skipped", "reason": "unresolved_placeholder"}
    assert rec.requests == []


def test_touch_roundtrip():
    t = sr.schedule_for(ILMI, NOW)[0]
    assert sr.Touch.from_dict(t.to_dict()) == t


def test_sender_ghl_switch_schedules_but_never_dispatches(tmp_env, shadow_mode, monkeypatch):
    monkeypatch.setenv(sr.SENDER_ENV, "ghl")
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    out = sr.run(NOW, store, ghl, appointments=[just_booked()])
    assert out["would_do"] == [] and out["sent"] == []
    assert {e["reason"] for e in out["skipped"]} == {"sender_is_ghl"}
    assert len(store.keys("showrate:")) == 1 and rec.requests == []
    assert not [r for r in job_log.read_shadow_log() if r.get("action") == "send_message"]


# ------------------------------------------------------------ offer-aware copy
def test_preread_matches_the_offer_type():
    """An outbound/trigger booking must not get the reactivation mechanism and
    reactivation pricing fifteen minutes after a confirmation email that
    promised the guarantee."""
    outbound = dict(ILMI, niche="cleaning", offer=None, campaign_key="cleaning_trigger")
    assert sr.offer_of(outbound) == "outbound"
    t = by_key(sr.schedule_for(outbound, NOW, a2p=True))
    preread = t["preread_email"].body
    assert "$180,000 in new contracts in 90 days" in preread  # the outbound proof line
    assert "20 to 30%" not in preread and "commission" not in preread.lower()
    assert "$24,000 a year in new cleaning contracts signed within 90 days" in preread
    assert "$6M worth of contracts" not in preread  # never the reactivation proof
    # the confirmation email and the pre-read now tell the same story
    assert "$24,000 a year in new cleaning contracts signed within 90 days" in t["confirm_email"].body
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        body = by_key(sr.schedule_for(dict(ILMI, niche=niche, offer="outbound"), NOW))["preread_email"].body
        assert "$180,000" in body and "20 to 30%" not in body, niche
        assert body.rstrip().endswith("Lorenzo") and "{" not in body and "#" not in body
    # reactivation is unchanged
    react = by_key(sr.schedule_for(dict(ILMI, offer="reactivation"), NOW))["preread_email"].body
    assert "$6M worth of contracts" in react and "$180,000" not in react


MONEY_RE = __import__("re").compile(r"\$[\d][\d,]*(?:\.\d+)?[A-Za-z]*")


def test_money_claims_match_the_offer_sheet():
    """Every currency figure the engine puts in writing has to appear in
    config/offers.md for that offer: it is what Lorenzo defends on the call."""
    from shared.settings import OFFERS_MD

    seen = set()
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        for offer in ("reactivation", "outbound"):
            appt = dict(ILMI, niche=niche, offer=offer)
            for t in sr.schedule_for(appt, NOW, a2p=True):
                for token in MONEY_RE.findall((t.subject or "") + "\n" + t.body):
                    seen.add(token)
                    assert token in OFFERS_MD, (niche, offer, t.template_key, token)
    assert {"$24,000", "$15,000", "$40,000", "$180,000", "$0", "$200"} <= seen


def test_the_cleaning_guarantee_keeps_its_annualised_qualifier():
    body = by_key(sr.schedule_for(dict(ILMI, niche="cleaning", offer="outbound"), NOW))["confirm_email"].body
    assert "$24,000 a year in new cleaning contracts signed within 90 days" in body
    assert "the $24,000 in new contracts within 90 days" not in body


def test_every_sms_identifies_lorenzo():
    """Fifteen minutes before the call, from a number the prospect has not
    saved, a bare link and their own first name reads like phishing."""
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        for t in sr.schedule_for(dict(ILMI, niche=niche), NOW, a2p=True):
            if t.channel == "sms":
                assert "Lorenzo" in t.body, (niche, t.template_key)
                assert len(t.body) <= sr.SMS_MAX_LEN


# ------------------------------------------------------------ send windows
def test_sms_defers_into_the_leads_local_window():
    """07:00 CT is 05:00 for a Pacific lead. The arming has to satisfy both."""
    pacific = dict(ILMI, lead_tz="America/Los_Angeles", start_iso="2026-09-23T12:00:00-05:00",
                   end_iso="2026-09-23T12:15:00-05:00")
    now = datetime.fromisoformat("2026-09-21T21:10:00-05:00")  # Monday night CT
    t = by_key(sr.schedule_for(pacific, now, a2p=True))
    armed = slots.parse_iso(t["confirm_sms"].when_iso)
    assert armed.astimezone(pytz.timezone("America/Los_Angeles")).hour >= 7
    assert armed.astimezone(CT).hour >= 7
    assert t["confirm_sms"].when_iso == "2026-09-22T09:00:00-05:00"  # 07:00 PDT


def test_weekend_arming_defers_the_confirmation_sms_to_monday():
    friday_night = datetime.fromisoformat("2026-09-25T21:10:00-05:00")  # Friday 21:10 CT
    pacific = dict(ILMI, lead_tz="America/Los_Angeles", start_iso="2026-09-28T12:00:00-05:00",
                   end_iso="2026-09-28T12:15:00-05:00")
    t = by_key(sr.schedule_for(pacific, friday_night, a2p=True))
    armed = slots.parse_iso(t["confirm_sms"].when_iso)
    assert armed.weekday() == 0 and armed.isoformat() == "2026-09-28T09:00:00-05:00"
    # email is held for the night (07:00-19:00) but NOT for the weekend: a lead
    # who books on Friday evening gets the confirmation on Saturday morning,
    # not three days later.
    assert t["confirm_email"].when_iso == "2026-09-26T09:00:00-05:00"  # Sat 07:00 PDT
    assert slots.parse_iso(t["confirm_email"].when_iso).weekday() == 5


def test_reminders_anchored_to_the_call_are_never_pushed_past_it():
    """A reminder is for a time the lead picked: the weekday rule must not
    move a Sunday call's 1 h SMS to the Monday after the call."""
    sunday = dict(ILMI, start_iso="2026-11-01T13:00:00-06:00", end_iso="2026-11-01T13:15:00-06:00")
    t = by_key(sr.schedule_for(sunday, datetime.fromisoformat("2026-10-30T10:00:00-05:00"), a2p=True))
    assert t["reminder_1h_sms"].when_iso == "2026-11-01T12:00:00-06:00"
    assert not t["reminder_1h_sms"].skipped


# ------------------------------------------------------------ reschedules
def test_reschedule_back_to_a_previous_slot_rearms_the_sequence(tmp_env):
    store = JsonFileStore(tmp_env / "s.json")
    first = sr.ensure_scheduled(store, just_booked(), NOW, a2p=True)
    moved = dict(ILMI, start_iso="2026-09-24T14:00:00-05:00", end_iso="2026-09-24T14:15:00-05:00")
    sr.ensure_scheduled(store, moved, NOW + timedelta(minutes=5), a2p=True)
    assert all(t["skipped"] for t in store.get(first["key"])["touches"])
    # ...and back to Wednesday 11:30
    back = sr.ensure_scheduled(store, ILMI, NOW + timedelta(minutes=10), a2p=True)
    assert back["key"] == first["key"] and back["created"] is False and back["rearmed"] is True
    touches = {t["template_key"]: t for t in store.get(first["key"])["touches"]}
    assert not touches["confirm_email"]["skipped"] and not touches["reminder_24h_email"]["skipped"]
    assert not any(t.get("skip_reason") == "rescheduled" for t in touches.values())
    assert sr.pending_touches(store, ILMI["id"])
    start = slots.parse_iso(ILMI["start_iso"])
    out = sr.run(start - timedelta(hours=4), store, GHL(token=None, transport=httpx.MockTransport(Recorder())))
    assert "unconfirmed_task" in [e["template"] for e in out["would_do"]]


def test_a_reschedule_clears_the_confirmation_so_the_4h_task_fires_again(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[ILMI])
    sr.mark_confirmed(store, ILMI["id"], NOW + timedelta(hours=1))
    assert sr.is_confirmed(store, ILMI)
    moved = dict(ILMI, start_iso="2026-09-25T14:00:00-05:00", end_iso="2026-09-25T14:15:00-05:00")
    sr.run(NOW + timedelta(hours=2), store, ghl, appointments=[moved])
    assert not sr.is_confirmed(store, moved)
    out = sr.run(slots.parse_iso(moved["start_iso"]) - timedelta(hours=3, minutes=59), store, ghl)
    assert "unconfirmed_task" in [e["template"] for e in out["would_do"]]
    assert rec.requests == []


# ------------------------------------------------------------ live snapshot
def test_a_call_confirmed_tag_reaches_the_4h_check(tmp_env, shadow_mode):
    """The documented confirm path is the GHL workflow adding the contact tag
    `call-confirmed`; the snapshot used to drop tags, so it never arrived."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[just_booked()])
    tagged = dict(ILMI, tags=["cold-email", "call-confirmed"])
    start = slots.parse_iso(ILMI["start_iso"])
    out = sr.run(start - timedelta(hours=3, minutes=59), store, ghl, appointments=[tagged])
    assert "unconfirmed_task" not in [e["template"] for e in out["would_do"]]
    assert {"key": ILMI["id"] + ":2026-09-23T11:30:00-05:00:unconfirmed_task", "reason": "confirmed"} in [
        {"key": e["key"], "reason": e.get("reason")} for e in out["skipped"]]
    assert store.get(sr.schedule_key(ILMI["id"], start.isoformat()))["appointment"]["tags"] == tagged["tags"]
    assert rec.requests == []


# ------------------------------------------------------------ cancellations
def test_a_cancelled_appointment_stops_the_sequence(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[ILMI])
    start = slots.parse_iso(ILMI["start_iso"])
    window = (NOW - timedelta(days=1), NOW + timedelta(days=30))
    # GHL no longer returns the event: it was cancelled or deleted
    out = sr.run(start - timedelta(hours=23), store, ghl, active_ids=set(), window=window)
    assert out["would_do"] == [] and out["cancelled"] == [sr.schedule_key(ILMI["id"], start.isoformat())]
    assert sr.pending_touches(store, ILMI["id"]) == []
    later = sr.run(start - timedelta(hours=1), store, ghl, active_ids=set(), window=window)
    assert later["would_do"] == [] and later["sent"] == []
    assert rec.requests == []


def test_a_failed_calendar_read_is_not_read_as_cancelled(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[ILMI])
    start = slots.parse_iso(ILMI["start_iso"])
    out = sr.run(start - timedelta(hours=23, minutes=59), store, ghl, active_ids=None)
    assert "reminder_24h_email" in [e["template"] for e in out["would_do"]]
    assert out["cancelled"] == [] and sr.pending_touches(store, ILMI["id"])


def test_an_appointment_outside_the_read_window_is_left_alone(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    far = just_booked(dict(ILMI, start_iso="2026-12-01T12:00:00-06:00", end_iso="2026-12-01T12:15:00-06:00"))
    sr.run(NOW, store, ghl, appointments=[far])
    window = (NOW - timedelta(days=1), NOW + timedelta(days=30))
    out = sr.run(NOW + timedelta(minutes=20), store, ghl, active_ids=set(), window=window)
    assert out["cancelled"] == []
    assert [e["template"] for e in out["would_do"]] == ["preread_email"]


# ------------------------------------------------------------ retryable skips
def test_ghl_token_missing_leaves_the_touch_pending_for_the_next_tick(tmp_env, shadow_mode):
    """A token rotation must not silently destroy an appointment's whole
    sequence, one touch at a time, as each becomes due."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[just_booked()])
    key = sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")
    rc = store.get(key)
    for t in rc["touches"]:
        t["sent"], t["result"], t["sent_at"] = False, None, None
        store.delete(sr._touch_claim_key(t["key"]))  # un-dispatch it completely
    store.set(key, rc)

    def no_token(*a, **k):
        return None

    real = ghl.send_message
    ghl.send_message = no_token
    out = sr.run(NOW, store, ghl)
    assert out["sent"] == [] and out["would_do"] == []
    assert [e["error"] for e in out["errors"]] == ["ghl_token_missing"]
    confirm = [t for t in store.get(key)["touches"] if t["template_key"] == "confirm_email"][0]
    assert not confirm["sent"] and not confirm["skipped"]  # pending, not burned
    ghl.send_message = real
    again = sr.run(NOW + timedelta(minutes=1), store, ghl)
    assert [e["template"] for e in again["would_do"]] == ["confirm_email"]


# ------------------------------------------------------------ stale bookings
def test_a_booking_seen_days_late_does_not_get_a_fresh_confirmation():
    """The tick now looks 30 days ahead. A booking it meets for the first time
    long after it was made must not get "Locked in ... the invite is on its way"."""
    stale = dict(ILMI, booked_at="2026-09-01T10:00:00-05:00", start_iso="2026-10-12T14:00:00-05:00",
                 end_iso="2026-10-12T14:15:00-05:00")
    t = by_key(sr.schedule_for(stale, NOW, a2p=True))
    for k in ("confirm_email", "confirm_sms", "preread_email"):
        assert t[k].skipped and t[k].skip_reason == "stale_booking", k
    assert not t["reminder_24h_email"].skipped
    fresh = dict(stale, booked_at=(NOW - timedelta(minutes=3)).isoformat())
    assert not by_key(sr.schedule_for(fresh, NOW, a2p=True))["confirm_email"].skipped


# ------------------------------------- A3 review fixes (2026-09-22)
def test_offer_of_reads_the_ghl_offer_tag():
    """A GHL calendar event carries no campaign key, so the contact tags the
    published GHL workflows branch on are the only offer signal. Without them
    every real booking fell back to reactivation and an outbound/trigger
    prospect was quoted commission pricing and the reactivation proof."""
    outbound = {k: v for k, v in ILMI.items() if k not in ("offer", "niche")}
    outbound["tags"] = ["cold-email", "niche-cleaning", "offer-outbound"]
    assert sr.offer_of(outbound) == "outbound" and sr.niche_of(outbound) == "cleaning"
    reactivation = dict(outbound, tags=["niche-bookkeeping", "offer-reactivation"])
    assert sr.offer_of(reactivation) == "reactivation" and sr.niche_of(reactivation) == "bookkeeping"
    # an explicit field still wins, and an unknown tag falls through
    assert sr.offer_of(dict(outbound, offer="reactivation")) == "reactivation"
    assert sr.offer_of(dict(outbound, tags=["offer-mystery"])) == "reactivation"
    # the copy follows the tag
    t = by_key(sr.schedule_for(outbound, NOW, a2p=True))
    assert "$24,000 a year in new cleaning contracts signed within 90 days" in t["confirm_email"].body
    assert "commission-only numbers" not in t["confirm_email"].body
    assert "$6M worth of contracts" not in t["preread_email"].body
    assert "20 to 30%" not in t["preread_email"].body


def test_the_preread_is_not_sent_once_the_call_has_started():
    """preread_email is armed off the booking moment, so a lead who books
    inside 15 minutes of the call used to get "Before our call: the one-page
    version" ten minutes into the call."""
    booking = datetime.fromisoformat("2026-09-23T13:55:00-05:00")
    appt = just_booked(dict(ILMI, start_iso="2026-09-23T14:00:00-05:00",
                            end_iso="2026-09-23T14:15:00-05:00"), at=booking)
    t = by_key(sr.schedule_for(appt, booking, a2p=True))
    start = slots.parse_iso(appt["start_iso"])
    assert sr.dispatch_block_reason(t["preread_email"], start, booking + timedelta(minutes=15)) == "appointment_started"
    assert sr.dispatch_block_reason(t["confirm_email"], start, booking) is None


def test_the_preread_is_not_dispatched_after_the_call_starts(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    booking = datetime.fromisoformat("2026-09-23T13:55:00-05:00")
    appt = just_booked(dict(ILMI, start_iso="2026-09-23T14:00:00-05:00",
                            end_iso="2026-09-23T14:15:00-05:00"), at=booking)
    out = sr.run(booking, store, ghl, appointments=[appt])
    assert [e["template"] for e in out["would_do"]] == ["confirm_email"]
    later = sr.run(booking + timedelta(minutes=15), store, ghl)   # 14:10, ten minutes into the call
    assert later["would_do"] == []
    assert {e["template"]: e["reason"] for e in later["skipped"]}["preread_email"] == "appointment_started"
    assert not any("one-page version" in (r.get("payload", {}).get("subject") or "")
                   for r in job_log.read_shadow_log())


def test_a_touch_that_came_due_during_an_outage_is_not_sent_with_tomorrow_copy(tmp_env, shadow_mode):
    """RETRYABLE_SKIP_REASONS deliberately leaves a touch pending across ticks,
    so a token rotation or a paused schedule used to deliver "Tomorrow at 2:00
    CT, still good?" on the morning of the call."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    appt = just_booked(dict(ILMI, start_iso="2026-09-23T14:00:00-05:00",
                            end_iso="2026-09-23T14:15:00-05:00"), at=NOW)
    sr.run(NOW, store, ghl, appointments=[appt])          # confirmation goes out
    # then every tick is missed until one hour before the call
    out = sr.run(datetime.fromisoformat("2026-09-23T13:00:00-05:00"), store, ghl)
    by_template = {e["template"]: e.get("reason") for e in out["skipped"]}
    assert by_template["preread_email"] == "too_late"
    assert by_template["reminder_24h_email"] == "too_late"
    assert out["would_do"] == []
    bodies = " ".join((r.get("payload", {}).get("message") or "") for r in job_log.read_shadow_log())
    assert "We are on for tomorrow" not in bodies
    assert "the short version of what I will walk through" not in bodies


def test_a_contact_id_that_arrives_on_a_later_tick_revives_the_sequence(tmp_env, shadow_mode):
    """booking.register_booking passes result.contact_id, which is empty
    whenever the GHL contact upsert has not returned an id yet. The touch used
    to be burned with skip_reason no_contact_id and the lead got no
    confirmation, no pre-read, no reminder and no 4 h task."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    nameless = just_booked(dict(ILMI, contact_id=None))
    first = sr.run(NOW, store, ghl, appointments=[nameless])
    assert first["would_do"] == []
    assert [e["error"] for e in first["errors"]] == ["no_contact_id"]   # pending, not burned
    key = sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")
    confirm = [t for t in store.get(key)["touches"] if t["template_key"] == "confirm_email"][0]
    assert not confirm["sent"] and not confirm["skipped"]
    # the id arrives on the next tick
    again = sr.run(NOW + timedelta(minutes=5), store, ghl, appointments=[just_booked()])
    assert [e["template"] for e in again["would_do"]] == ["confirm_email"]
    assert job_log.read_shadow_log()[-1]["payload"]["contactId"] == ILMI["contact_id"]


def test_a_touch_that_keeps_erroring_is_eventually_given_up_on(tmp_env, shadow_mode):
    """Without a cap a permanently broken contact produced an error row on
    every 10-minute tick, forever."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[just_booked(dict(ILMI, contact_id=None))])
    key = sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")
    for i in range(1, sr.MAX_TOUCH_ATTEMPTS + 2):
        out = sr.run(NOW + timedelta(minutes=i), store, ghl)
    confirm = [t for t in store.get(key)["touches"] if t["template_key"] == "confirm_email"][0]
    assert confirm["skipped"] and confirm["skip_reason"] == "retry_exhausted"
    assert confirm["attempts"] >= sr.MAX_TOUCH_ATTEMPTS


def test_a_crash_between_the_send_and_the_store_write_does_not_re_send(tmp_env, shadow_mode):
    """dispatch_touch ran before store.set, so a container killed in between
    re-sent the same "Confirmed: ..." email on the next tick."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[just_booked()])
    key = sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")
    crashed = store.get(key)
    for t in crashed["touches"]:
        if t["template_key"] == "confirm_email":
            t["sent"], t["sent_at"], t["result"] = False, None, None
    store.set(key, crashed)
    out = sr.run(NOW + timedelta(minutes=1), store, ghl)
    assert out["would_do"] == []
    assert {e["template"]: e["reason"] for e in out["skipped"]}["confirm_email"] == "already_dispatched"
    sends = [r for r in job_log.read_shadow_log() if r.get("action") == "send_message"]
    assert len(sends) == 1


def test_a_cold_start_does_not_confirm_bookings_it_has_never_seen(tmp_env, shadow_mode):
    """First tick after deploy (or after a corrupt store was quarantined): the
    30-day window is full of calls booked days ago, and a GHL calendar event
    need not carry dateAdded at all. Fail closed."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    a = dict(ILMI, id="old-1")
    b = dict(ILMI, id="old-2", start_iso="2026-09-24T15:00:00-05:00", end_iso="2026-09-24T15:15:00-05:00")
    out = sr.run(NOW, store, ghl, appointments=[a, b])
    assert out["would_do"] == [] and out.get("cold_start") is True
    for key in store.keys("showrate:"):
        touches = {t["template_key"]: t for t in store.get(key)["touches"]}
        for k in ("confirm_email", "preread_email"):
            assert touches[k]["skipped"] and touches[k]["skip_reason"] == "stale_booking", (key, k)
        assert not touches["reminder_24h_email"]["skipped"]   # the reminders still run
    # a booking that appears on a LATER tick was made between two ticks
    new = dict(ILMI, id="new-1", start_iso="2026-09-25T13:00:00-05:00", end_iso="2026-09-25T13:15:00-05:00")
    later = sr.run(NOW + timedelta(minutes=5), store, ghl, appointments=[a, b, new])
    assert [e["template"] for e in later["would_do"]] == ["confirm_email"]


def test_a_reschedule_still_gets_its_confirmation_and_preread(tmp_env, shadow_mode):
    """GHL keeps the appointment id and dateAdded on a reschedule (only
    dateUpdated moves), so staleness measured from booked_at marked the NEW
    time stale and the lead who just moved the call heard nothing until the
    24 h reminder. ids.json records that Ilmi already rescheduled once."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    booked = dict(ILMI, booked_at="2026-09-21T10:00:00-05:00")   # Tuesday morning
    sr.run(NOW, store, ghl, appointments=[booked])               # cold start: T+0 suppressed
    moved = dict(booked, start_iso="2026-09-25T16:00:00-05:00", end_iso="2026-09-25T16:15:00-05:00")
    out = sr.run(NOW + timedelta(days=1), store, ghl, appointments=[moved])
    key = sr.schedule_key(ILMI["id"], "2026-09-25T16:00:00-05:00")
    touches = {t["template_key"]: t for t in store.get(key)["touches"]}
    assert not touches["confirm_email"]["skipped"], touches["confirm_email"]["skip_reason"]
    assert not touches["preread_email"]["skipped"]
    assert [e["template"] for e in out["would_do"]] == ["confirm_email"]
    assert "Locked in for Fri, Sep 25 at 4:00pm CT" in job_log.read_shadow_log()[-1]["payload"]["message"]


def test_mark_confirmed_without_a_start_normalises_what_it_stores(tmp_env):
    """The no-start branch stored GHL's raw string while is_confirmed()
    compares a normalised one, so a lead who replied C still got the 4 h
    "text or call them personally" task. This is the exact three-argument call
    runbooks/show_rate_and_no_show.md tells brief A1 to make."""
    store = JsonFileStore(tmp_env / "s.json")
    appt = just_booked(dict(ILMI, id="ev-z", start_iso="2026-09-24T20:00:00.000Z",
                            end_iso="2026-09-24T20:15:00.000Z"))
    sr.ensure_scheduled(store, appt, NOW)
    sr.mark_confirmed(store, "ev-z", NOW)
    stored = store.get(sr.confirmed_key("ev-z"))
    assert stored["start_iso"] == "2026-09-24T15:00:00-05:00"
    assert sr.is_confirmed(store, appt) is True


def test_appointments_tick_dry_run_actually_forces_shadow(tmp_env, monkeypatch):
    """The dry_run argument was accepted and never read, so a caller passing
    dry_run=True in a live-configured process performed the full live run."""
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    store = JsonFileStore(tmp_env / "s.json")
    res = sr.appointments_tick(now="2026-09-22T09:00:00-05:00", store=store, dry_run=True)
    assert os.environ["MODE"] == "shadow" and "ALLOW_LIVE_WRITES" not in os.environ
    assert res["status"] in ("ok", "partial")
    # and a string clock no longer raises out of the wrapper
    assert sr.appointments_tick(now="not-a-time", store=store)["status"] == "error"
