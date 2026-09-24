"""appointments_tick: fixture fallback, dry-run forcing shadow, Job_Log row,
no-show flagging via the tick, zero HTTP."""
import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from shared import job_log, notify, settings, slots
from shared.ghl import GHL
from shared.store import JsonFileStore

from jobs import appointments_tick as tick_mod

FIXTURE = str(Path(__file__).resolve().parent / "fixtures" / "appointments_2026-09-21.json")
# Monday 17:10 CT, inside the 07:00-19:00 send window.
NOW = datetime.fromisoformat("2026-09-21T17:10:00-05:00")


class Recorder(object):
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})


def test_fixture_has_the_two_real_calls():
    appts = tick_mod.load_appointments_file(FIXTURE)
    assert [a["start_iso"] for a in appts] == ["2026-09-23T11:30:00-05:00", "2026-09-24T15:00:00-05:00"]
    assert {a["contact_id"] for a in appts} == {"cnfZoGRCRi3JMqZfo0XD", "iDhesF6A9rhdDajGZuYw"}
    assert {a["niche"] for a in appts} == {"cleaning", "bookkeeping"}


def test_fetch_falls_back_to_fixture_without_ghl_token(caplog):
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    with caplog.at_level("WARNING"):
        out = tick_mod.fetch_appointments(ghl, NOW, FIXTURE)
    assert out["source"].startswith("fixture:") and len(out["appointments"]) == 2
    assert "ghl_token_missing" in caplog.text and rec.requests == []


def test_fetch_uses_ghl_events_when_token_present():
    events = {"events": [
        {"id": "ev1", "calendarId": settings.GHL_CALENDAR_ID, "contactId": "c1", "title": "Discovery Call - Jane Doe",
         "appointmentStatus": "confirmed", "startTime": "2026-09-25T14:00:00-05:00", "endTime": "2026-09-25T14:15:00-05:00",
         "address": "https://zoom.us/j/123456789", "contact": {"email": "j@x.com", "companyName": "Doe Cleaning"}},
        {"id": "ev2", "contactId": "c2", "title": "Discovery Call - Gone", "appointmentStatus": "cancelled",
         "startTime": "2026-09-25T15:00:00-05:00", "endTime": "2026-09-25T15:15:00-05:00"},
    ]}
    rec = Recorder()
    ghl = GHL(token="tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=events)))
    out = tick_mod.fetch_appointments(ghl, NOW, FIXTURE)
    assert out["source"] == "ghl" and len(out["appointments"]) == 1
    a = out["appointments"][0]
    assert a["id"] == "ev1" and a["contact_id"] == "c1" and a["zoom_link"] == "https://zoom.us/j/123456789"
    assert a["first_name"] == "Jane" and a["company"] == "Doe Cleaning" and a["email"] == "j@x.com"


def test_tick_schedules_and_sends_confirmations_in_shadow(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    # the two fixture calls were booked days ago and carry no booked_at, so the
    # T+0 legs are suppressed; give one a fresh booked_at to see a confirmation
    appts = tick_mod.load_appointments_file(FIXTURE)
    appts[0] = dict(appts[0], booked_at=(NOW - timedelta(minutes=2)).isoformat())
    appts[1] = dict(appts[1], booked_at=(NOW - timedelta(minutes=1)).isoformat())
    result = tick_mod.tick(NOW, store, ghl, appts)
    assert result["appointments"] == {"upcoming": 2, "started": 0, "cancelled": 0}
    assert result["show_rate"]["scheduled"] == 2 and result["show_rate"]["would_do"] == 2 and result["show_rate"]["sent"] == 0
    assert result["no_show"] == [] and result["recovery"]["would_do"] == 0
    assert result["pending_touches"] > 0 and result["next_touch"]["template_key"] == "reminder_24h_email"
    assert rec.requests == []
    text = tick_mod.digest_text(result)
    assert "MODE=shadow" in text and "2 upcoming" in text and "2 would_do" in text


def host_join(appt, minutes=-1):
    start = slots.parse_iso(appt["start_iso"])
    return {"at_iso": (start + timedelta(minutes=minutes)).isoformat(), "name": "Lorenzo Villarreal",
            "email": "lorenzovillarreal@adverosolutions.com", "is_host": True}


def test_tick_does_not_flag_no_show_without_zoom_telemetry(tmp_env, shadow_mode):
    """The Discovery Call calendar is still on Google Meet and no Zoom app
    exists, so every appointment has an empty join list. Treating that as
    proof of a no-show fired the full 14-day recovery at every held call."""
    store = JsonFileStore(tmp_env / "s.json")
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    appts = tick_mod.load_appointments_file(FIXTURE)
    tick_mod.tick(NOW, store, ghl, appts)
    now = datetime.fromisoformat("2026-09-23T11:40:00-05:00")  # Ilmi start + 10 m, no telemetry at all
    result = tick_mod.tick(now, store, ghl, appts, joins_override={appts[0]["id"]: []})
    assert result["appointments"] == {"upcoming": 1, "started": 1, "cancelled": 0}
    ns = result["no_show"][0]
    assert ns["verdict"] == "unknown" and ns["state"] == "pending" and ns["events"] == ["no_telemetry"]
    assert [a["action"] for a in ns["actions"]] == ["create_task"]  # Lorenzo marks it by hand
    assert store.keys("recovery:") == []
    assert store.get("no_show_count:%s" % appts[0]["contact_id"]) is None
    # and it does not nag: the task is raised once
    again = tick_mod.tick(now + timedelta(minutes=5), store, ghl, appts, joins_override={appts[0]["id"]: []})
    assert again["no_show"][0]["actions"] == [] and again["recovery"]["would_do"] == 0
    assert rec.requests == []


def test_tick_flags_no_show_at_start_plus_10_when_zoom_reported_the_meeting(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    appts = tick_mod.load_appointments_file(FIXTURE)
    tick_mod.tick(NOW, store, ghl, appts)
    now = datetime.fromisoformat("2026-09-23T11:40:00-05:00")  # Ilmi start + 10 m, only Lorenzo joined
    joins = {appts[0]["id"]: [host_join(appts[0])]}
    result = tick_mod.tick(now, store, ghl, appts, joins_override=joins)
    assert result["appointments"] == {"upcoming": 1, "started": 1, "cancelled": 0}
    ns = result["no_show"][0]
    assert ns["state"] == "no_show" and ns["events"] == ["no_show"] and ns["no_show_count"] == 1
    assert {a["action"] for a in ns["actions"]} == {"update_appointment_status", "create_note"}
    assert all(a["status"] == "would_do" for a in ns["actions"])
    # the reschedule email (N3) is due at start + 25 min
    result2 = tick_mod.tick(now + timedelta(minutes=15), store, ghl, appts, joins_override=joins)
    assert result2["recovery"]["would_do"] == 1
    assert result2["recovery_detail"]["would_do"][0]["template"] == "ns_reschedule_email"
    assert rec.requests == []


def test_tick_marks_showed_when_ghl_says_so_without_any_zoom_data(tmp_env, shadow_mode):
    """Lorenzo setting the appointment to showed by hand always wins."""
    store = JsonFileStore(tmp_env / "s.json")
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    appts = tick_mod.load_appointments_file(FIXTURE)
    held = [dict(appts[0], ghl_status="showed")]
    now = datetime.fromisoformat("2026-09-23T11:41:00-05:00")
    result = tick_mod.tick(now, store, ghl, held, joins_override={held[0]["id"]: []})
    assert result["no_show"][0]["state"] == "showed"
    assert store.keys("recovery:") == []


def test_main_dry_run_forces_shadow_writes_job_log_and_digest(tmp_env, monkeypatch, capsys):
    # even if the environment claims live, --dry-run must run in shadow
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    monkeypatch.setenv("NOTIFY", "off")
    notify.reset_for_tests()
    store_path = str(tmp_env / "store.json")
    rc = tick_mod.main(["--dry-run", "--now", NOW.isoformat(), "--appointments", FIXTURE, "--store", store_path])
    assert rc == 0
    assert os.environ["MODE"] == "shadow" and "ALLOW_LIVE_WRITES" not in os.environ
    assert not settings.is_live()
    out = capsys.readouterr().out
    assert "appointments_tick" in out and "MODE=shadow" in out and "would_do" in out
    assert "GHL token: missing" in out and "source: fixture:" in out
    rows = list(csv.DictReader(open(job_log.job_log_path(), encoding="utf-8")))
    row = [r for r in rows if r["job"] == "appointments_tick"][-1]
    assert row["status"] == "ok" and row["mode"] == "shadow"
    details = json.loads(row["details"])
    assert details["dry_run"] is True and details["live"] is False
    # the replayed fixture is two calls booked days earlier with no booked_at,
    # so nothing is confirmed: see
    # test_a_cold_start_does_not_confirm_bookings_it_has_never_seen
    assert details["show_rate"]["would_do"] == 0
    assert notify.sent_in_test and notify.sent_in_test[-1]["title"] == "Appointments tick"
    store = JsonFileStore(store_path)
    assert len(store.keys("showrate:")) == 2


def test_main_with_joins_file_marks_showed(tmp_env, monkeypatch):
    monkeypatch.setenv("NOTIFY", "off")
    appts = tick_mod.load_appointments_file(FIXTURE)
    joins_path = tmp_env / "joins.json"
    joins_path.write_text(json.dumps({appts[0]["id"]: [
        {"at_iso": "2026-09-23T11:29:00-05:00", "name": "Lorenzo Villarreal", "is_host": True},
        {"at_iso": "2026-09-23T11:32:00-05:00", "name": "Ilmi Curovic", "email": "ilmi@shiningarmorcleaningnj.com"},
    ]}), encoding="utf-8")
    store_path = str(tmp_env / "store.json")
    rc = tick_mod.main(["--dry-run", "--no-notify", "--quiet", "--now", "2026-09-23T11:41:00-05:00", "--appointments", FIXTURE,
                        "--joins", str(joins_path), "--store", store_path])
    assert rc == 0
    store = JsonFileStore(store_path)
    assert store.get("noshow_state:%s" % appts[0]["id"])["state"] == "showed"
    assert store.get("no_show_count:%s" % appts[0]["contact_id"]) is None
    assert store.keys("recovery:") == []


def test_normalise_ghl_event_handles_missing_fields():
    assert tick_mod.normalise_ghl_event({"title": "x"}) is None
    a = tick_mod.normalise_ghl_event({"id": "e", "startTime": "2026-09-25T14:00:00-05:00", "title": "Discovery Call - Ana Lima", "appointmentStatus": "confirmed"})
    assert a["first_name"] == "Ana" and a["contact_name"] == "Ana Lima" and a["zoom_link"] is None and a["cancelled"] is False


# ------------------------------------------------------------ egress
def test_dry_run_makes_no_outbound_request_at_all(tmp_env, monkeypatch, capsys):
    """--dry-run is documented as "no write can happen". It also has to mean
    no live HTTP: shared.notify posts the digest to ntfy.sh."""
    monkeypatch.setenv("NOTIFY", "on")           # the environment wants real notifications
    monkeypatch.setenv("NTFY_TOPIC", "advero-test-topic")
    notify.reset_for_tests()
    rc = tick_mod.main(["--dry-run", "--now", NOW.isoformat(), "--appointments", FIXTURE,
                        "--store", str(tmp_env / "store.json"), "--quiet"])
    assert rc == 0
    # --dry-run turns notifications off for the process, so notify never opens
    # an httpx client to ntfy.sh; the digest is recorded instead.
    assert os.environ["NOTIFY"] == "off" and notify.is_off()
    res = notify.notify("probe", "probe")
    assert res["sent"] is False and res["test"] is True  # short-circuited, no client opened
    assert [r["title"] for r in notify.sent_in_test] == ["Appointments tick", "probe"]


# ------------------------------------------------------------ failed reads
def test_a_failed_calendar_read_is_partial_and_high_priority(tmp_env, monkeypatch, capsys):
    monkeypatch.setenv("NOTIFY", "off")
    notify.reset_for_tests()

    class FailingGHL(GHL):
        def get_calendar_events(self, *a, **k):
            raise RuntimeError("HTTP 500 from GHL")

    monkeypatch.setattr("shared.ghl.GHL", FailingGHL)
    rc = tick_mod.main(["--now", NOW.isoformat(), "--store", str(tmp_env / "store.json"), "--quiet"])
    assert rc == 0
    rows = list(csv.DictReader(open(job_log.job_log_path(), encoding="utf-8")))
    row = [r for r in rows if r["job"] == "appointments_tick"][-1]
    assert row["status"] == "partial"
    assert json.loads(row["details"])["read_error"]
    assert notify.sent_in_test[-1]["priority"] == "high"


def test_a_read_failure_never_looks_like_everything_was_cancelled(tmp_env, shadow_mode):
    from services.reply_engine import show_rate as sr

    store = JsonFileStore(tmp_env / "s.json")
    ghl = GHL(token=None, transport=httpx.MockTransport(Recorder()))
    appts = tick_mod.load_appointments_file(FIXTURE)
    tick_mod.tick(NOW, store, ghl, appts)
    before = len(sr.pending_touches(store))
    # GHL failed: active_ids is None, so nothing may be treated as cancelled
    tick_mod.tick(NOW + timedelta(minutes=5), store, ghl, [], active_ids=None, window=None)
    assert len(sr.pending_touches(store)) == before


def test_fetch_reports_the_error_instead_of_an_empty_calendar():
    class Boom(GHL):
        def get_calendar_events(self, *a, **k):
            raise RuntimeError("timeout")

    ghl = Boom(token="tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    out = tick_mod.fetch_appointments(ghl, NOW, None)
    assert out["error"] and out["authoritative"] is False and out["active_ids"] is None
    rec = Recorder()
    ghl2 = GHL(token=None, transport=httpx.MockTransport(rec))
    out2 = tick_mod.fetch_appointments(ghl2, NOW, None)
    assert out2["error"] == "ghl_token_missing" and out2["active_ids"] is None and rec.requests == []


# ------------------------------------------------------------ cancellations
def test_a_cancelled_event_stops_its_show_rate_sequence():
    events = {"events": [
        {"id": "ev1", "contactId": "c1", "title": "Discovery Call - Jane Doe", "appointmentStatus": "cancelled",
         "startTime": "2026-09-25T14:00:00-05:00", "endTime": "2026-09-25T14:15:00-05:00"},
    ]}
    ghl = GHL(token="tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=events)))
    out = tick_mod.fetch_appointments(ghl, NOW, None)
    assert out["appointments"] == [] and len(out["cancelled"]) == 1
    assert out["active_ids"] == set() and out["authoritative"] is True


def test_tick_cancels_the_sequence_when_the_event_disappears(tmp_env, shadow_mode):
    from services.reply_engine import show_rate as sr

    store = JsonFileStore(tmp_env / "s.json")
    ghl = GHL(token=None, transport=httpx.MockTransport(Recorder()))
    appts = tick_mod.load_appointments_file(FIXTURE)
    window = (NOW - timedelta(days=1), NOW + timedelta(days=30))
    tick_mod.tick(NOW, store, ghl, appts, active_ids=set(a["id"] for a in appts), window=window)
    assert sr.pending_touches(store)
    # Ilmi cancels: GHL stops returning her event
    keep = [a for a in appts if a["id"] != appts[0]["id"]]
    tick_mod.tick(NOW + timedelta(minutes=5), store, ghl, keep, active_ids=set(a["id"] for a in keep), window=window)
    assert sr.pending_touches(store, appts[0]["id"]) == []
    assert sr.pending_touches(store, appts[1]["id"])


# ------------------------------------------------------------ lookahead
def test_lookahead_matches_the_calendars_booking_horizon():
    assert tick_mod.LOOKAHEAD == timedelta(days=30)
    horizon = settings.IDS["ghl"]["calendars"]["discovery_call"]["allow_booking_for_days"]
    assert tick_mod.LOOKAHEAD.days == horizon


def test_a_booking_three_weeks_out_is_scheduled_on_the_next_tick(tmp_env, shadow_mode):
    from services.reply_engine import show_rate as sr

    store = JsonFileStore(tmp_env / "s.json")
    ghl = GHL(token=None, transport=httpx.MockTransport(Recorder()))
    far = dict(tick_mod.load_appointments_file(FIXTURE)[0], id="far", start_iso="2026-10-12T14:00:00-05:00",
               end_iso="2026-10-12T14:15:00-05:00", booked_at=(NOW - timedelta(minutes=2)).isoformat())
    result = tick_mod.tick(NOW, store, ghl, [far])
    assert result["show_rate"]["scheduled"] == 1
    assert [e["template"] for e in result["show_rate_detail"]["would_do"]] == ["confirm_email"]
    assert sr.pending_touches(store, "far")


# ------------------------------------------------------------ rebooking
def test_the_tick_stops_a_recovery_when_the_lead_rebooks(tmp_env, shadow_mode):
    """booking.py (A2) is supposed to call cancel_recovery_for_rebooking and
    does not; a widget rebooking produces no inbound reply either."""
    from services.reply_engine import no_show as ns

    store = JsonFileStore(tmp_env / "s.json")
    ghl = GHL(token=None, transport=httpx.MockTransport(Recorder()))
    appts = tick_mod.load_appointments_file(FIXTURE)
    ilmi = appts[0]
    flagged = slots.parse_iso(ilmi["start_iso"]) + timedelta(minutes=10)
    tick_mod.tick(flagged, store, ghl, [ilmi], joins_override={ilmi["id"]: [host_join(ilmi)]})
    assert store.get(ns.state_key(ilmi["id"]))["state"] == "no_show"

    new_call = dict(ilmi, id="gcal_rebooked", start_iso="2026-10-01T12:00:00-05:00",
                    end_iso="2026-10-01T12:15:00-05:00")
    out = tick_mod.tick(flagged + timedelta(hours=1), store, ghl, [new_call])
    assert out["rebooked_cancelled"] and out["rebooked_cancelled"][0]["appointment_id"] == ilmi["id"]
    assert store.get(ns.state_key(ilmi["id"]))["state"] == "done"
    later = tick_mod.tick(flagged + timedelta(days=14), store, ghl, [])
    assert later["recovery"]["would_do"] == 0 and later["recovery"]["stage_moves"] == 0


# --------------------------------------------- A3 review fixes (2026-09-22)
def ghl_event(**over):
    """A realistic GHL calendar event, shaped like GET /calendars/events."""
    ev = {
        "id": "ev9", "calendarId": settings.GHL_CALENDAR_ID, "contactId": "cnt9",
        "title": "Discovery Call - Rob Marano", "appointmentStatus": "confirmed",
        "startTime": "2026-09-25T14:00:00-05:00", "endTime": "2026-09-25T14:15:00-05:00",
        "address": "https://zoom.us/j/123456789",
        "contact": {"id": "cnt9", "email": "rob@cjsglobal.com", "companyName": "CJS Global",
                    "firstName": "Rob", "timezone": "America/New_York",
                    "tags": ["cold-email", "niche-cleaning", "offer-outbound"]},
    }
    ev.update(over)
    return ev


def test_normalise_carries_the_contacts_timezone_into_lead_tz():
    """lead_tz_of() answered None for every real booking, so the lead-local SMS
    window never applied and the "(1:00 ET)" clarifier never appeared. Rob's
    recorded reply proposes "2pm EST" while Lorenzo confirms in Central."""
    from services.reply_engine import show_rate as sr

    a = tick_mod.normalise_ghl_event(ghl_event())
    assert a["lead_tz"] == "America/New_York"
    assert sr.lead_tz_of(a) is not None and sr.lead_tz_of(a).zone == "America/New_York"
    subject = sr.render("confirm_email", a, slots.parse_iso(a["start_iso"]), NOW)["subject"]
    assert "CT" in subject and "ET" in subject


def test_a_pacific_contacts_confirmation_waits_for_their_own_morning():
    from services.reply_engine import show_rate as sr

    ev = ghl_event()
    ev["contact"] = dict(ev["contact"], timezone="America/Los_Angeles")
    a = tick_mod.normalise_ghl_event(ev)
    monday_night = datetime.fromisoformat("2026-09-21T21:10:00-05:00")
    t = {x.template_key: x for x in sr.schedule_for(a, monday_night)}
    armed = slots.parse_iso(t["confirm_email"].when_iso)
    assert armed.isoformat() == "2026-09-22T09:00:00-05:00"   # 07:00 PDT, not 05:00


def test_an_outbound_booking_from_ghl_keeps_its_offer_type():
    """The GHL workflows branch on the contact tags; normalise_ghl_event used
    to drop them, so every calendar booking was treated as a reactivation deal
    and an outbound prospect was quoted commission pricing."""
    from services.reply_engine import show_rate as sr

    a = tick_mod.normalise_ghl_event(ghl_event())
    assert a["offer"] == "outbound" and a["niche"] == "cleaning"
    assert sr.offer_of(a) == "outbound" and sr.niche_of(a) == "cleaning"
    t = {x.template_key: x for x in sr.schedule_for(a, NOW)}
    confirm = t["confirm_email"].body
    assert "$24,000" in confirm
    assert "20 to 30%" not in confirm and "$6M" not in confirm


def test_a_real_booking_with_status_new_is_not_mistaken_for_a_cadence_hold():
    """The real cadence hold carries BOTH the HOLD title prefix and status
    "new" (cadence.py:1354, 1363). Dropping every "new" appointment silently
    removed a genuine booking from the show-rate sequence AND from no-show
    detection, with only an INFO log."""
    real = ghl_event(appointmentStatus="new")
    assert tick_mod.is_cadence_hold(real) is False
    a = tick_mod.normalise_ghl_event(real)
    assert a is not None and a["id"] == "ev9" and a["ghl_status"] == "new"
    hold = ghl_event(title="HOLD: cadence day 6 - Rob Marano", appointmentStatus="new")
    assert tick_mod.is_cadence_hold(hold) is True
    assert tick_mod.normalise_ghl_event(hold) is None
    # ...and a confirmed hold (title only) is still a hold
    assert tick_mod.is_cadence_hold(ghl_event(title="HOLD: x", appointmentStatus="confirmed")) is True


def test_a_ghl_event_without_dateAdded_still_suppresses_the_locked_in_confirmation(tmp_env, shadow_mode):
    """GHL's calendar-events payload need not carry dateAdded, so BOOKING_STALE_AFTER
    was inert and every booking already in the 30-day window got "Locked in for
    ... the calendar invite is on its way" on the first tick after deploy."""
    store = JsonFileStore(tmp_env / "s.json")
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    a = tick_mod.normalise_ghl_event(ghl_event())
    assert a["booked_at"] is None
    result = tick_mod.tick(NOW, store, ghl, [a])
    assert result["show_rate"]["scheduled"] == 1 and result["show_rate"]["would_do"] == 0
    bodies = " ".join((r.get("payload", {}).get("message") or "") for r in job_log.read_shadow_log())
    assert "the calendar invite is on its way" not in bodies
    # with dateAdded from this minute it is a real new booking and goes out
    fresh = tick_mod.normalise_ghl_event(ghl_event(id="ev10", dateAdded=(NOW - timedelta(minutes=1)).isoformat()))
    later = tick_mod.tick(NOW + timedelta(minutes=5), store, ghl, [a, fresh])
    assert [e["template"] for e in later["show_rate_detail"]["would_do"]] == ["confirm_email"]


def test_one_failing_appointment_does_not_abort_the_whole_tick(tmp_env, shadow_mode):
    """A single HTTP 500 on PUT /calendars/events/appointments/{id} used to
    propagate out of tick(): every other started appointment was skipped and
    the recovery sweep for every older no-show never ran. A deterministic
    failure stopped the whole S5 ladder for everyone, on every tick, for good."""
    from shared.ghl import GHLError

    store = JsonFileStore(tmp_env / "s.json")
    appts = tick_mod.load_appointments_file(FIXTURE)
    bad = dict(appts[0], id="appt-ns", start_iso="2026-09-23T11:30:00-05:00",
               end_iso="2026-09-23T11:45:00-05:00")
    good = dict(appts[1], id="appt-other", contact_id="c-other",
                start_iso="2026-09-23T11:30:00-05:00", end_iso="2026-09-23T11:45:00-05:00")
    now = datetime.fromisoformat("2026-09-23T11:41:00-05:00")

    class FlakyGHL(GHL):
        def update_appointment_status(self, appointment_id, status):
            if appointment_id == "appt-ns":
                raise GHLError("GHL PUT ... -> HTTP 500")
            return super(FlakyGHL, self).update_appointment_status(appointment_id, status)

    ghl = FlakyGHL(token=None, transport=httpx.MockTransport(Recorder()))
    joins = {"appt-ns": [host_join(bad)], "appt-other": [host_join(good)]}
    result = tick_mod.tick(now, store, ghl, [bad, good], joins_override=joins)
    states = {r["appointment_id"]: r["state"] for r in result["no_show"]}
    assert states["appt-ns"] == "error"
    assert states["appt-other"] == "no_show"                      # still processed
    assert store.get("noshow_state:appt-other")["state"] == "no_show"
    assert result["errors"] and result["errors"][0]["where"] == "no_show.process"
    assert "ERROR no_show.process on appt-ns" in tick_mod.digest_text(result)


def test_a_fixture_replay_never_cancels_the_schedules_it_cannot_see(tmp_env, shadow_mode):
    """runbooks/show_rate_and_no_show.md documents the fixture replay with no
    --store. Clearing the read error made the fixture "authoritative", so
    show_rate cancelled every other schedule in the 31-day window, and a
    cancelled record is never re-armed."""
    from services.reply_engine import show_rate as sr

    store = JsonFileStore(tmp_env / "s.json")
    rec = Recorder()
    ghl = GHL(token=None, transport=httpx.MockTransport(rec))
    real = dict(tick_mod.load_appointments_file(FIXTURE)[0], id="ev-real-999",
                start_iso="2026-09-25T13:00:00-05:00", end_iso="2026-09-25T13:15:00-05:00",
                booked_at=(NOW - timedelta(minutes=1)).isoformat())
    tick_mod.tick(NOW, store, ghl, [real])
    assert len(sr.pending_touches(store, "ev-real-999")) >= 2

    fetched = tick_mod.fetch_appointments(ghl, NOW, FIXTURE)
    assert fetched["source"].startswith("fixture:")
    assert fetched["error"] == "ghl_token_missing"     # NOT cleared by the replay
    assert fetched["authoritative"] is False and fetched["active_ids"] is None
    assert fetched["replay"] is True
    tick_mod.tick(NOW + timedelta(minutes=5), store, ghl, fetched["appointments"],
                  active_ids=fetched["active_ids"], window=fetched["window"])
    assert len(sr.pending_touches(store, "ev-real-999")) >= 2     # untouched


def test_a_dry_run_without_store_uses_a_scratch_store(tmp_env, monkeypatch, capsys):
    """--dry-run advertises "no write can happen"; it used to gate HTTP only
    and ran against the production store."""
    from shared.paths import tmp_file
    from shared.store import get_store

    monkeypatch.setenv("NOTIFY", "off")
    notify.reset_for_tests()
    production = get_store()
    production.set("showrate:keep-me:2026-09-25T13:00:00-05:00", {"touches": [], "sentinel": True})
    rc = tick_mod.main(["--dry-run", "--now", NOW.isoformat(), "--appointments", FIXTURE, "--quiet"])
    assert rc == 0
    assert production.get("showrate:keep-me:2026-09-25T13:00:00-05:00") == {"touches": [], "sentinel": True}
    assert production.keys("showrate:") == ["showrate:keep-me:2026-09-25T13:00:00-05:00"]
    scratch = JsonFileStore(tmp_file("dryrun_store.json"))
    assert len(scratch.keys("showrate:")) == 2


# ---------------------------------------------- what this job does NOT cover
def test_the_manual_google_calendar_calls_are_reported_not_scheduled():
    """The only appointment source is the GHL Discovery Call calendar, but both
    calls actually on the books this week are hand-made Zoom events on Lorenzo's
    own Google Calendar, which is how he books today. They are deliberately not
    fed into show_rate (the ladder would mail a confirmation and a "reply C" to
    a prospect who agreed the time with him directly, through a GHL contact
    that may not exist), so the tick says so on every run instead."""
    now = datetime.fromisoformat("2026-09-22T09:00:00-05:00")
    rows = tick_mod.manual_calendar_calls(now)
    assert [r["who"].split(" /")[0] for r in rows] == ["Ilmi Curovic", "Sopio Svanishvili"]
    text = tick_mod.digest_text({
        "now": now.isoformat(), "mode": "shadow", "a2p_registered": False,
        "appointments": {"upcoming": 0, "started": 0, "cancelled": 0},
        "show_rate": {}, "no_show": [], "recovery": {}, "pending_touches": 0,
        "manual_calendar_calls": rows, "confirmations": {},
    })
    assert "NOT COVERED: Ilmi Curovic" in text and "NOT COVERED: Sopio Svanishvili" in text


def test_calls_that_have_already_happened_drop_off_the_not_covered_list():
    late = datetime.fromisoformat("2026-09-25T09:00:00-05:00")
    assert tick_mod.manual_calendar_calls(late) == []


# ------------------------------------------------- the retired "reply C" scan
def test_the_retired_reply_c_scan_is_a_no_op_that_makes_no_request(tmp_path, monkeypatch):
    """Section 2 (2026-09-23): no 4 h "has not confirmed" task any more, so
    nothing waits on a C. The scan the tick still calls reads nothing."""
    from services.reply_engine import show_rate

    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    store = JsonFileStore(str(tmp_path / "store.json"))
    show_rate.ensure_scheduled(store, {"id": "appt-c-1", "start_iso": (NOW + timedelta(days=1)).isoformat(),
                                       "contact_id": "cnfZoGRCRi3JMqZfo0XD", "first_name": "Ilmi",
                                       "email": "ilmi@shiningarmorcleaningnj.com", "booked_at": NOW.isoformat()},
                               NOW)
    rec = Recorder()
    out = show_rate.scan_ghl_confirmations(NOW + timedelta(hours=2), store,
                                           GHL(token="test-token", transport=httpx.MockTransport(rec)))
    assert out == {"checked": 0, "confirmed": [], "skipped": [], "errors": []}
    assert rec.requests == []
