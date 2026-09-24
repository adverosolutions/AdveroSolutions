"""S4 show-rate sequence (section 2 rebuild, 2026-09-23): the confirmation and
the R2 / R3 / R4 reminder emails. Schedule math, the booking-time rules, DST,
re-entry, the signed-off copy, in-thread dispatch with the GHL fallback, and
zero HTTP in shadow."""
import json
import os
import re
from datetime import datetime, timedelta

import httpx
import pytest
import pytz

from shared import job_log, slots
from shared.ghl import GHL, GHLError
from shared.instantly import Instantly
from shared.paths import BASE_DIR
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
REMINDERS = ("reminder_24h_email", "reminder_morning_email", "reminder_1h_email")


def test_exact_sequence_and_order():
    touches = sr.schedule_for(ILMI, NOW)
    assert [t.template_key for t in touches] == ["confirm_email"] + list(REMINDERS)
    assert [t.channel for t in touches] == ["email"] * 4          # no SMS, no task for Lorenzo
    assert all(t.appointment_id == ILMI["id"] and t.contact_id == ILMI["contact_id"] for t in touches)
    assert len({t.key for t in touches}) == 4
    assert set(sr.MAX_LATENESS) == set(sr.SEQUENCE_KEYS)
    assert sr.MAX_LATENESS["reminder_24h_email"] == timedelta(hours=6)
    assert sr.MAX_LATENESS["reminder_morning_email"] == timedelta(hours=3)
    assert sr.MAX_LATENESS["reminder_1h_email"] == timedelta(minutes=30)


def test_offsets_relative_to_start_and_booking():
    t = by_key(sr.schedule_for(ILMI, NOW))
    start = slots.parse_iso(ILMI["start_iso"])
    assert t["confirm_email"].when() == NOW
    assert t["reminder_24h_email"].when() == start - timedelta(hours=24)
    assert t["reminder_1h_email"].when() == start - timedelta(hours=1)
    assert t["reminder_24h_email"].when_iso == "2026-09-22T11:30:00-05:00"
    assert t["reminder_1h_email"].when_iso == "2026-09-23T10:30:00-05:00"
    assert t["reminder_morning_email"].skipped and t["reminder_morning_email"].skip_reason == "not_needed"


# (now, call start, R2 skip, R3 skip, R3 time, R4 skip). The lead is in New
# York, so 08:30 on the call day is 07:30 CT.
BOOKING_CASES = {
    "booked_3_days_out": ("2026-09-21T17:10:00-05:00", "2026-09-24T14:00:00-05:00", None, "not_needed", None, None),
    "next_day_after_the_24h_mark": ("2026-09-22T15:00:00-05:00", "2026-09-23T11:30:00-05:00", "booked_late", None,
                                    "2026-09-23T07:30:00-05:00", None),
    "booked_26h_out": ("2026-09-22T09:30:00-05:00", "2026-09-23T11:30:00-05:00", "booked_late", None,
                       "2026-09-23T07:30:00-05:00", None),
    "monday_call": ("2026-09-25T10:00:00-05:00", "2026-09-28T13:00:00-05:00", "booked_late", None,
                    "2026-09-28T07:30:00-05:00", None),
    "same_day": ("2026-09-23T09:00:00-05:00", "2026-09-23T11:30:00-05:00", "booked_late", "same_day", None, None),
}


@pytest.mark.parametrize("case", sorted(BOOKING_CASES))
def test_which_reminders_a_booking_gets(case):
    """copy_signed_off.md, "Reminders": booked early enough -> R2 + R4; later
    but not the same day -> R3 + R4; same day -> R4 only."""
    now_iso, start_iso, r2, r3, r3_when, r4 = BOOKING_CASES[case]
    now = datetime.fromisoformat(now_iso)
    appt = just_booked(dict(ILMI, start_iso=start_iso), at=now)
    t = by_key(sr.schedule_for(appt, now))
    assert t["reminder_24h_email"].skip_reason == r2 and t["reminder_24h_email"].skipped == bool(r2)
    assert t["reminder_morning_email"].skip_reason == r3 and t["reminder_morning_email"].skipped == bool(r3)
    assert t["reminder_1h_email"].skip_reason == r4 and not t["reminder_1h_email"].skipped
    if r3_when:
        assert t["reminder_morning_email"].when_iso == r3_when
    assert not t["confirm_email"].skipped


def test_the_six_hour_rule_and_the_weekend_rule_say_why():
    t = by_key(sr.schedule_for(just_booked(dict(ILMI), at=datetime.fromisoformat("2026-09-22T09:30:00-05:00")),
                               datetime.fromisoformat("2026-09-22T09:30:00-05:00")))
    assert t["reminder_24h_email"].meta["why"] == "within_6h_of_booking"
    monday = dict(ILMI, start_iso="2026-09-28T13:00:00-05:00", booked_at="2026-09-25T10:00:00-05:00")
    assert by_key(sr.schedule_for(monday, datetime.fromisoformat("2026-09-25T10:00:00-05:00")))[
        "reminder_24h_email"].meta["why"] == "weekend"
    # a zone we do not know: 08:30 Central
    no_zone = {k: v for k, v in ILMI.items() if k != "lead_tz"}
    now = datetime.fromisoformat("2026-09-22T15:00:00-05:00")
    assert by_key(sr.schedule_for(just_booked(no_zone, at=now), now))["reminder_morning_email"].when_iso == \
        "2026-09-23T08:30:00-05:00"


def test_dst_fall_back_24h_is_24_real_hours():
    # DST ends 2026-11-01 02:00 CDT. A Monday 13:00 CST call: R2 is Sunday
    # 13:00 CST (24 real hours before), a weekend, so R3 goes on Monday morning.
    appt = dict(ILMI, start_iso="2026-11-02T13:00:00-06:00", end_iso="2026-11-02T13:15:00-06:00")
    now = datetime.fromisoformat("2026-10-30T10:00:00-05:00")
    t = by_key(sr.schedule_for(appt, now))
    start = slots.parse_iso(appt["start_iso"])
    assert start - t["reminder_24h_email"].when() == timedelta(hours=24)
    assert t["reminder_24h_email"].skip_reason == "booked_late"
    assert t["reminder_morning_email"].when_iso == "2026-11-02T07:30:00-06:00"   # 08:30 EST
    assert t["reminder_1h_email"].when_iso == "2026-11-02T12:00:00-06:00"


def test_booking_after_start_skips_all_reminders_but_keeps_confirmation():
    now = datetime.fromisoformat("2026-09-23T11:40:00-05:00")
    t = by_key(sr.schedule_for(ILMI, now))
    assert t["reminder_24h_email"].skip_reason == "booked_late"
    assert t["reminder_morning_email"].skip_reason == "same_day"
    assert t["reminder_1h_email"].skip_reason == "past_time"
    assert not t["confirm_email"].skipped


def test_night_time_confirmation_defers_to_07_ct():
    """CLAUDE.md: "sends only 07:00-19:00 CT". The widget takes bookings at any
    hour."""
    t = by_key(sr.schedule_for(ILMI, NIGHT))  # NIGHT is 21:10 CT
    assert t["confirm_email"].when_iso == "2026-09-22T07:00:00-05:00"
    assert t["confirm_email"].meta["deferred_from"] == "2026-09-21T21:10:00-05:00"
    day = by_key(sr.schedule_for(ILMI, NOW))
    assert day["confirm_email"].when_iso == NOW.isoformat()
    assert "deferred_from" not in day["confirm_email"].meta


# ------------------------------------------------------------ copy
SIGNED_OFF = (BASE_DIR / "sections" / "2_booked_calls" / "copy_signed_off.md").read_text(encoding="utf-8")


def signed_off(heading, first, when, time_, link):
    """The text copy_signed_off.md holds under ``heading``, filled in; with no
    link, the paragraph that carries {call_link} is its "No link on file" line."""
    part = SIGNED_OFF.split(heading, 1)[1]
    subject = re.search(r"^Subject: (.+)$", part, re.M).group(1)
    body = re.search(r"```\n(.*?)\n```", part, re.S).group(1)
    if not link:
        nolink = re.search(r"No link on file:[^`]*`([^`]+)`", part).group(1)
        body = "\n\n".join(nolink if "{call_link}" in p else p for p in body.split("\n\n"))

    def fill(text):
        return (text.replace("{first_name}", first).replace("{when}", when).replace("{time}", time_)
                .replace("{call_link}", link or ""))
    return fill(subject), fill(body)


@pytest.mark.parametrize("link", ["https://zoom.us/j/000000000001", None])
@pytest.mark.parametrize("key,heading", [("reminder_24h_email", "### R2"), ("reminder_morning_email", "### R3"),
                                         ("reminder_1h_email", "### R4")])
def test_every_reminder_is_the_signed_off_text(key, heading, link):
    appt = dict(ILMI, zoom_link=link) if link else {k: v for k, v in ILMI.items() if k != "zoom_link"}
    got = sr.render(key, appt, slots.parse_iso(ILMI["start_iso"]), NOW)
    # the lead's own clock in brackets (they are in New York)
    subject, body = signed_off(heading, "Ilmi", "Wed, Sep 23 at 11:30am CT (12:30pm ET)", "11:30am CT (12:30pm ET)",
                               link)
    assert (got["subject"], got["body"]) == (subject, body)


def test_time_is_central_only_for_a_central_or_unknown_zone():
    start = slots.parse_iso(ILMI["start_iso"])
    for zone in ("America/Chicago", None):
        appt = dict(ILMI, lead_tz=zone) if zone else {k: v for k, v in ILMI.items() if k != "lead_tz"}
        assert sr.render("reminder_1h_email", appt, start, NOW)["subject"] == "See you at 11:30am CT"
    assert sr.fmt_time_only(start) == "11:30am CT"                      # no_show's one-argument form


def test_copy_rules_no_booking_link_no_reply_c_signed_lorenzo(monkeypatch):
    monkeypatch.delenv("LOOM_URL_CLEANING", raising=False)
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        for link in ("https://zoom.us/j/000000000001", None):
            appt = dict(ILMI, niche=niche, zoom_link=link, booking_url="https://book.example.test/x",
                        reschedule_link="https://book.example.test/y")
            for t in sr.schedule_for(appt, NOW):
                text = (t.subject or "") + "\n" + t.body
                assert "—" not in text and "–" not in text and "!" not in text, (niche, t.template_key)
                low = text.lower()
                assert "automat" not in low and " ai " not in low and "a.i." not in low, (niche, t.template_key)
                assert "reply c" not in low and "book.example.test" not in low, (niche, t.template_key)
                assert "grab a" not in low and "booking" not in low, (niche, t.template_key)
                assert t.body.rstrip().endswith("Lorenzo") and t.subject, (niche, t.template_key)
    body = by_key(sr.schedule_for(ILMI, NOW))["confirm_email"].body
    assert body.count("\n- ") == 3  # three-bullet agenda
    assert "[Loom:" not in body and "walkthrough" not in body  # no URL configured: the line is dropped
    assert "Wed, Sep 23 at 11:30am CT (12:30pm ET)" in body  # lead tz shown, am/pm on both (ZC item 8)


def test_loom_url_from_env_replaces_placeholder(monkeypatch):
    monkeypatch.setenv("LOOM_URL_CLEANING", "https://www.loom.com/share/abc")
    body = by_key(sr.schedule_for(ILMI, NOW))["confirm_email"].body
    assert "https://www.loom.com/share/abc" in body and "[Loom:" not in body
    assert not sr.has_unresolved_placeholder(body)
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
    assert all(t["skipped"] and t["skip_reason"] in ("rescheduled", "not_needed") for t in old["touches"])
    pending = sr.pending_touches(store)
    assert pending and all(t["appointment_id"] == ILMI["id"] and t["meta"]["start_iso"] == "2026-09-24T14:00:00-05:00" for t in pending)


# ------------------------------------------------------------ run (shadow)
def test_run_in_shadow_sends_nothing_and_logs_would_do(tmp_env, shadow_mode):
    """No lead row with a thread: every email goes as the GHL fallback."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    out = sr.run(NOW, store, ghl, appointments=[just_booked()])
    assert out["scheduled"] == [sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")]
    assert [e["template"] for e in out["would_do"]] == ["confirm_email"]
    assert out["would_do"][0]["transport"] == "ghl_email"
    assert out["sent"] == [] and out["errors"] == []
    assert rec.requests == []  # zero HTTP in shadow
    log = job_log.read_shadow_log()
    assert log[-1]["system"] == "ghl" and log[-1]["action"] == "send_message"
    assert log[-1]["payload"]["type"] == "Email" and log[-1]["payload"]["contactId"] == ILMI["contact_id"]
    # idempotent: a second tick at the same time sends nothing new
    out2 = sr.run(NOW, store, ghl)
    assert out2["would_do"] == [] and out2["sent"] == []
    # 24 h before
    start = slots.parse_iso(ILMI["start_iso"])
    out4 = sr.run(start - timedelta(hours=23, minutes=59), store, ghl)
    assert [e["template"] for e in out4["would_do"]] == ["reminder_24h_email"]
    # 1 h before
    out5 = sr.run(start - timedelta(minutes=59), store, ghl)
    assert [e["template"] for e in out5["would_do"]] == ["reminder_1h_email"]
    assert job_log.read_shadow_log()[-1]["payload"]["subject"] == "See you at 11:30am CT (12:30pm ET)"
    # past start: nothing more
    out6 = sr.run(start + timedelta(minutes=1), store, ghl)
    assert out6["would_do"] == []
    assert rec.requests == []
    assert sr.pending_touches(store) == []


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
MONEY_RE = __import__("re").compile(r"\$[\d][\d,]*(?:\.\d+)?[A-Za-z]*")


def test_money_claims_match_the_offer_sheet():
    """Every currency figure the engine puts in writing has to appear in
    config/offers.md for that offer: it is what Lorenzo defends on the call."""
    from shared.settings import OFFERS_MD

    seen = set()
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        for offer in ("reactivation", "outbound"):
            appt = dict(ILMI, niche=niche, offer=offer)
            for t in sr.schedule_for(appt, NOW):
                for token in MONEY_RE.findall((t.subject or "") + "\n" + t.body):
                    seen.add(token)
                    assert token in OFFERS_MD, (niche, offer, t.template_key, token)
                    assert t.template_key == "confirm_email", t.template_key   # the reminders quote no money
    assert {"$24,000", "$15,000", "$40,000", "$0"} <= seen


def test_the_cleaning_guarantee_keeps_its_annualised_qualifier():
    body = by_key(sr.schedule_for(dict(ILMI, niche="cleaning", offer="outbound"), NOW))["confirm_email"].body
    assert "$24,000 a year in new cleaning contracts signed within 90 days" in body
    assert "the $24,000 in new contracts within 90 days" not in body


# ------------------------------------------------------------ send windows
def test_the_confirmation_defers_into_the_leads_local_window():
    """07:00 CT is 05:00 for a Pacific lead. The arming has to satisfy both."""
    pacific = dict(ILMI, lead_tz="America/Los_Angeles", start_iso="2026-09-23T12:00:00-05:00",
                   end_iso="2026-09-23T12:15:00-05:00")
    now = datetime.fromisoformat("2026-09-21T21:10:00-05:00")  # Monday night CT
    t = by_key(sr.schedule_for(pacific, now))
    assert t["confirm_email"].when_iso == "2026-09-22T09:00:00-05:00"  # 07:00 PDT


def test_a_weekend_booking_is_confirmed_on_monday_morning():
    """The in-thread send refuses a weekend (slots.is_send_time), so a Friday
    night booking's confirmation is armed for Monday 07:00 lead-local rather
    than held on Saturday until it expires."""
    friday_night = datetime.fromisoformat("2026-09-25T21:10:00-05:00")  # Friday 21:10 CT
    pacific = dict(ILMI, lead_tz="America/Los_Angeles", start_iso="2026-09-29T12:00:00-05:00",
                   end_iso="2026-09-29T12:15:00-05:00")
    t = by_key(sr.schedule_for(pacific, friday_night))
    assert t["confirm_email"].when_iso == "2026-09-28T09:00:00-05:00"   # Mon 07:00 PDT


def test_reminders_anchored_to_the_call_are_never_pushed_past_it():
    """A reminder is for a time the lead picked: the weekday rule must not
    move a Sunday call's 1 h SMS to the Monday after the call."""
    sunday = dict(ILMI, start_iso="2026-11-01T13:00:00-06:00", end_iso="2026-11-01T13:15:00-06:00")
    t = by_key(sr.schedule_for(sunday, datetime.fromisoformat("2026-10-30T10:00:00-05:00")))
    assert t["reminder_1h_email"].when_iso == "2026-11-01T12:00:00-06:00"
    assert not t["reminder_1h_email"].skipped


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
    out = sr.run(start - timedelta(minutes=59), store, GHL(token=None, transport=httpx.MockTransport(Recorder())))
    assert "reminder_1h_email" in [e["template"] for e in out["would_do"]]


def test_a_reschedule_clears_the_confirmation(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[ILMI])
    sr.mark_confirmed(store, ILMI["id"], NOW + timedelta(hours=1))
    assert sr.is_confirmed(store, ILMI)
    moved = dict(ILMI, start_iso="2026-09-25T14:00:00-05:00", end_iso="2026-09-25T14:15:00-05:00")
    sr.run(NOW + timedelta(hours=2), store, ghl, appointments=[moved])
    assert not sr.is_confirmed(store, moved)
    assert rec.requests == []


# ------------------------------------------------------------ live snapshot
def test_the_snapshot_follows_the_live_tags(tmp_env, shadow_mode):
    """The tags move after booking (the GHL workflow adds `call-confirmed`);
    the snapshot used to drop them."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[just_booked()])
    tagged = dict(ILMI, tags=["cold-email", "call-confirmed"])
    start = slots.parse_iso(ILMI["start_iso"])
    sr.run(start - timedelta(hours=3, minutes=59), store, ghl, appointments=[tagged])
    assert store.get(sr.schedule_key(ILMI["id"], start.isoformat()))["appointment"]["tags"] == tagged["tags"]
    assert sr.is_confirmed(store, tagged)
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
    assert out["cancelled"] == [] and out["would_do"] == []
    assert sr.pending_touches(store, ILMI["id"])


# ------------------------------------------------------------ retryable vs maybe sent
def _undispatch_confirmation(store):
    key = sr.schedule_key(ILMI["id"], "2026-09-23T11:30:00-05:00")
    rc = store.get(key)
    for t in rc["touches"]:
        t["sent"], t["result"], t["sent_at"] = False, None, None
        store.delete(sr._touch_claim_key(t["key"]))  # un-dispatch it completely
    store.set(key, rc)
    return key


def _confirm(store, key):
    return [t for t in store.get(key)["touches"] if t["template_key"] == "confirm_email"][0]


def test_a_send_refused_before_any_request_stays_pending_for_the_next_tick(tmp_env, shadow_mode):
    """thread_reply's ``retryable``: nothing left the process (here GHL has no
    write token), so the touch stays pending and the next tick tries again."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    sr.run(NOW, store, ghl, appointments=[just_booked()])
    key = _undispatch_confirmation(store)

    def no_token(*a, **k):
        raise GHLError("ghl_token_missing: no write token in this process")

    real = ghl.send_message
    ghl.send_message = no_token
    out = sr.run(NOW, store, ghl)
    assert out["sent"] == [] and out["would_do"] == [] and out["maybe_sent"] == []
    assert [e["error"] for e in out["errors"]] == ["ghl_token_missing"]
    confirm = _confirm(store, key)
    assert not confirm["sent"] and not confirm["skipped"] and confirm["attempts"] == 1  # pending, not burned
    ghl.send_message = real
    again = sr.run(NOW + timedelta(minutes=1), store, ghl)
    assert [e["template"] for e in again["would_do"]] == ["confirm_email"]


def test_a_send_that_may_have_gone_out_is_closed_and_never_retried(tmp_env, live_mode, monkeypatch):
    """thread_reply's ``maybe_sent`` (live, transports mocked): the request
    went out and came back with a null body. A retry would be a second email
    in the lead's inbox, so the touch is closed with the error and surfaced
    (errors, maybe_sent, one Job_Log row)."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token="tok")
    sr.run(NOW, store, ghl, appointments=[just_booked()])
    key = _undispatch_confirmation(store)
    calls = []

    def empty(*a, **k):
        calls.append(a)
        return None   # a 2xx whose body was null: may have been delivered

    ghl.send_message = empty
    logged = []
    monkeypatch.setattr(job_log, "log_run", lambda job, status, details=None: logged.append(status))
    out = sr.run(NOW, store, ghl)
    assert [e["template"] for e in out["maybe_sent"]] == ["confirm_email"]
    assert [e["reason"] for e in out["errors"]] == ["maybe_sent"]
    confirm = _confirm(store, key)
    assert confirm["skipped"] and confirm["skip_reason"] == "maybe_sent" and not confirm["sent"]
    assert store.get(sr._touch_claim_key(confirm["key"]))          # the claim stays: never sent twice
    later = sr.run(NOW + timedelta(minutes=10), store, ghl)
    assert later["maybe_sent"] == [] and len(calls) == 1
    assert logged.count("show_rate_maybe_sent") == 1


def test_an_email_due_outside_the_send_window_waits_without_an_attempt(tmp_env, shadow_mode):
    """A Saturday call's one-hour reminder falls on a Saturday: thread_reply
    refuses it (outside_send_window), the touch stays pending, no attempt is
    counted, and MAX_LATENESS still closes it."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    saturday = just_booked(dict(ILMI, start_iso="2026-09-26T12:00:00-05:00", end_iso="2026-09-26T12:15:00-05:00"))
    sr.run(NOW, store, ghl, appointments=[saturday])
    r4 = datetime.fromisoformat("2026-09-26T11:00:00-05:00")
    out = sr.run(r4, store, ghl)
    assert [e["template"] for e in out["deferred"]] == ["reminder_1h_email"] and out["errors"] == []
    t = [x for x in sr.pending_touches(store, ILMI["id"]) if x["template_key"] == "reminder_1h_email"][0]
    assert not t.get("attempts")
    late = sr.run(r4 + timedelta(minutes=31), store, ghl)
    assert {e["template"]: e["reason"] for e in late["skipped"]}["reminder_1h_email"] == "too_late"
    assert rec.requests == []


# ------------------------------------------------------------ stale bookings
def test_a_booking_seen_days_late_does_not_get_a_fresh_confirmation():
    """The tick now looks 30 days ahead. A booking it meets for the first time
    long after it was made must not get "Locked in ... the invite is on its way"."""
    stale = dict(ILMI, booked_at="2026-09-01T10:00:00-05:00", start_iso="2026-10-12T14:00:00-05:00",
                 end_iso="2026-10-12T14:15:00-05:00")
    t = by_key(sr.schedule_for(stale, NOW))
    assert t["confirm_email"].skipped and t["confirm_email"].skip_reason == "stale_booking"
    assert not t["reminder_1h_email"].skipped     # the reminders still run (R2 is a Sunday here)
    fresh = dict(stale, booked_at=(NOW - timedelta(minutes=3)).isoformat())
    assert not by_key(sr.schedule_for(fresh, NOW))["confirm_email"].skipped


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
    t = by_key(sr.schedule_for(outbound, NOW))
    assert "$24,000 a year in new cleaning contracts signed within 90 days" in t["confirm_email"].body
    assert "commission-only numbers" not in t["confirm_email"].body


def test_nothing_is_sent_once_the_call_has_started():
    """A touch held back past the start (a lead who booked minutes before the
    call, a paused tick) is dropped, never sent into the call."""
    booking = datetime.fromisoformat("2026-09-23T13:55:00-05:00")
    appt = just_booked(dict(ILMI, start_iso="2026-09-23T14:00:00-05:00",
                            end_iso="2026-09-23T14:15:00-05:00"), at=booking)
    t = by_key(sr.schedule_for(appt, booking))
    start = slots.parse_iso(appt["start_iso"])
    assert sr.dispatch_block_reason(t["confirm_email"], start, booking + timedelta(minutes=15)) == "appointment_started"
    assert sr.dispatch_block_reason(t["confirm_email"], start, booking) is None


def test_a_touch_that_came_due_during_an_outage_is_not_sent_with_tomorrow_copy(tmp_env, shadow_mode):
    """A retryable outcome deliberately leaves a touch pending across ticks,
    so a token rotation or a paused schedule used to deliver "still good for
    tomorrow?" on the morning of the call."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    appt = just_booked(dict(ILMI, start_iso="2026-09-23T14:00:00-05:00",
                            end_iso="2026-09-23T14:15:00-05:00"), at=NOW)
    sr.run(NOW, store, ghl, appointments=[appt])          # confirmation goes out
    # then every tick is missed until one hour before the call
    out = sr.run(datetime.fromisoformat("2026-09-23T13:00:00-05:00"), store, ghl)
    by_template = {e["template"]: e.get("reason") for e in out["skipped"]}
    assert by_template["reminder_24h_email"] == "too_late"
    assert [e["template"] for e in out["would_do"]] == ["reminder_1h_email"]   # due right now
    bodies = " ".join((r.get("payload", {}).get("message") or "") for r in job_log.read_shadow_log())
    assert "Still good for tomorrow" not in bodies


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
        assert touches["confirm_email"]["skipped"] and touches["confirm_email"]["skip_reason"] == "stale_booking", key
        assert not touches["reminder_24h_email"]["skipped"]   # the reminders still run
    # a booking that appears on a LATER tick was made between two ticks
    new = dict(ILMI, id="new-1", start_iso="2026-09-25T13:00:00-05:00", end_iso="2026-09-25T13:15:00-05:00")
    later = sr.run(NOW + timedelta(minutes=5), store, ghl, appointments=[a, b, new])
    assert [e["template"] for e in later["would_do"]] == ["confirm_email"]


def test_a_reschedule_still_gets_its_confirmation(tmp_env, shadow_mode):
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


# ------------------------------------------------------------ in-thread dispatch
CAMPAIGN = "c0ffee00-0000-7000-8000-0000000000a2"
EMAIL_ID = "01a0c5aa-0000-7000-8000-0000000000a2"
EACCOUNT = "lorenzo@adveromedia.com"


class ThreadRecorder(Recorder):
    """Answers the live recipient re-read (GET /emails/<id>) with the lead as
    the sender, and every POST with an id."""

    def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"id": EMAIL_ID, "from_address_email": ILMI["email"]})
        return httpx.Response(200, json={"id": "sent-1"})


def put_thread(store, email=None, campaign_id=CAMPAIGN, subject="Re: Ilmi, question"):
    from services.reply_engine.models import LeadState

    email = email or ILMI["email"]
    row = LeadState(lead_email=email, campaign_id=campaign_id, first_name="Ilmi", eaccount=EACCOUNT,
                    thread_id="thread-a2", last_email_id=EMAIL_ID, last_subject=subject).to_store()
    store.set("lead:%s:%s" % (campaign_id, email), row)


def threaded():
    return just_booked(dict(ILMI, campaign_id=CAMPAIGN))


def make_instantly():
    rec = ThreadRecorder()
    return Instantly(api_key="x", transport=httpx.MockTransport(rec), sleep=lambda s: None), rec


def test_shadow_dispatch_goes_in_the_leads_thread_with_zero_http(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    put_thread(store)
    ghl, grec = make_ghl(token="tok")
    inst, irec = make_instantly()
    out = sr.run(NOW, store, ghl, appointments=[threaded()], instantly=inst)
    assert [(e["template"], e["transport"]) for e in out["would_do"]] == [("confirm_email", "instantly_thread")]
    assert irec.requests == [] and grec.requests == []            # zero HTTP in shadow
    rec = job_log.read_shadow_log()[-1]
    assert (rec["system"], rec["action"]) == ("instantly", "reply_to_email")
    assert rec["payload"]["to"] == ILMI["email"] and rec["payload"]["subject"] == "Re: Ilmi, question"
    assert rec["payload"]["reply_to_uuid"] == EMAIL_ID and "Locked in for" in rec["payload"]["body"]["text"]


def test_live_dispatch_replies_in_the_thread_and_never_uses_ghl(tmp_env, live_mode):
    """Live, every transport still mocked: the recipient re-read, then the
    reply to the lead's own thread, with to= the lead."""
    store = JsonFileStore(tmp_env / "s.json")
    put_thread(store)
    ghl, grec = make_ghl(token="tok")
    inst, irec = make_instantly()
    out = sr.run(NOW, store, ghl, appointments=[threaded()], instantly=inst)
    assert [(e["template"], e["transport"]) for e in out["sent"]] == [("confirm_email", "instantly_thread")]
    assert [r.method for r in irec.requests] == ["GET", "POST"] and grec.requests == []
    body = json.loads(irec.requests[1].content.decode("utf-8"))
    assert irec.requests[1].url.path.endswith("/emails/reply")
    assert body["to"] == ILMI["email"] and body["subject"] == "Re: Ilmi, question"


def test_an_ambiguous_thread_holds_for_lorenzo_and_sends_nothing(tmp_env, shadow_mode):
    """Two campaigns' rows for the lead, each with a thread: which one is
    current cannot be told, so the email is held (needs_attention), pending,
    never sent as a GHL email instead."""
    store = JsonFileStore(tmp_env / "s.json")
    put_thread(store)
    put_thread(store, campaign_id="c0ffee00-0000-7000-8000-0000000000b2")
    ghl, grec = make_ghl(token=None)
    inst, irec = make_instantly()
    out = sr.run(NOW, store, ghl, appointments=[just_booked()], instantly=inst)   # widget booking: no campaign
    assert out["would_do"] == [] and out["errors"] == []
    assert [(e["template"], e["reason"]) for e in out["needs_attention"]] == [("confirm_email", "ambiguous_thread")]
    pending = [t for t in sr.pending_touches(store, ILMI["id"]) if t["template_key"] == "confirm_email"]
    assert pending and pending[0]["thread_hold"]["reason"] == "ambiguous_thread"
    assert not [r for r in job_log.read_shadow_log() if r.get("action") in ("send_message", "reply_to_email")]
    assert irec.requests == [] and grec.requests == []


def test_the_thread_subject_gets_the_subject_checks_too(tmp_env, shadow_mode):
    """In the thread the email carries "Re: <thread subject>", not the
    approved template's subject: a thread subject that fails the gate's
    subject rules holds the email."""
    store = JsonFileStore(tmp_env / "s.json")
    put_thread(store, subject="Re: Save $5,000 on cleaning today!")
    ghl, grec = make_ghl(token=None)
    inst, irec = make_instantly()
    out = sr.run(NOW, store, ghl, appointments=[threaded()], instantly=inst)
    assert out["would_do"] == []
    assert [(e["template"], e["reason"]) for e in out["held_template"]] == [("confirm_email", "thread_subject_refused")]
    assert not [r for r in job_log.read_shadow_log() if r.get("action") in ("send_message", "reply_to_email")]
    assert sr.thread_subject_problems("Re: Ilmi, question", ILMI) == []
