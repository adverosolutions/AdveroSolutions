"""S5 no-show detection, late-show, recovery timing and the SOP-005 repeat policy."""
from datetime import datetime, timedelta

import httpx
import pytest

from shared import job_log, settings, slots
from shared.ghl import GHL
from shared.store import JsonFileStore

from services.reply_engine import no_show as ns

START = datetime.fromisoformat("2026-09-24T15:00:00-05:00")
SOPIO = {
    "id": "gcal_j8n9pmfjl3cufeiu58g4kp12c8",
    "contact_id": "iDhesF6A9rhdDajGZuYw",
    "opportunity_id": "hStqQMLQ5eSRVnqxnSMq",
    "first_name": "Sopio",
    "company": "Taxfo Accounting",
    "email": "sopiosvanishvili@taxfoaccounting.com",
    "phone": "237-791-5700",
    "niche": "bookkeeping",
    "offer": "reactivation",
    "lead_tz": "America/New_York",
    "start_iso": START.isoformat(),
    "end_iso": (START + timedelta(minutes=15)).isoformat(),
    "zoom_link": "https://zoom.us/j/000000000002",
}
HOST = {"at_iso": (START - timedelta(minutes=1)).isoformat(), "name": "Lorenzo Villarreal", "email": "lorenzovillarreal@adverosolutions.com", "is_host": True}
BOT = {"at_iso": (START + timedelta(minutes=1)).isoformat(), "name": "Fred from Fireflies", "email": ""}


def lead_join(minutes):
    return {"at_iso": (START + timedelta(minutes=minutes)).isoformat(), "name": "Sopio S", "email": "sopiosvanishvili@taxfoaccounting.com"}


def host_join_for(appointment, minutes=-1):
    """Lorenzo joining this appointment's own meeting: the evidence channel
    that lets detect() conclude anything at all."""
    start = slots.parse_iso(appointment["start_iso"])
    return {"at_iso": (start + timedelta(minutes=minutes)).isoformat(), "name": "Lorenzo Villarreal",
            "email": "lorenzovillarreal@adverosolutions.com", "is_host": True}


class Recorder(object):
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})


def make_ghl(token=None):
    rec = Recorder()
    return GHL(token=token, transport=httpx.MockTransport(rec)), rec


def fixed_slots(now):
    return {"slots": ["2026-09-25T14:00:00-05:00", "2026-09-28T15:30:00-05:00"], "text": "Fri 2:00pm or Mon 3:30pm CT", "source": "ghl"}


def armed_at(store, template_key, appointment=None, start=None):
    """The time a recovery touch is actually armed for (after send-window
    deferral), read back from the stored record."""
    appointment = appointment or SOPIO
    key = ns.recovery_key(appointment["id"], (start or START).isoformat())
    for t in (store.get(key) or {}).get("touches", []):
        if t["template_key"] == template_key:
            return t["when_iso"]
    raise KeyError(template_key)


# ------------------------------------------------------------ detect
def test_detect_host_only_join_is_pending_then_no_show():
    assert ns.detect(START + timedelta(minutes=3), SOPIO, [HOST]) == "pending"
    assert ns.detect(START + timedelta(minutes=9, seconds=59), SOPIO, [HOST]) == "pending"
    assert ns.detect(START + timedelta(minutes=10), SOPIO, [HOST]) == "no_show"
    assert ns.detect(START + timedelta(minutes=30), SOPIO, [HOST]) == "no_show"


def test_detect_participant_join_at_plus_3_is_showed():
    assert ns.detect(START + timedelta(minutes=3), SOPIO, [HOST, lead_join(3)]) == "showed"
    assert ns.detect(START + timedelta(minutes=40), SOPIO, [HOST, lead_join(3)]) == "showed"
    # host recognised by email when the webhook could not flag is_host
    host_by_email = dict(HOST, is_host=False)
    assert ns.detect(START + timedelta(minutes=10), SOPIO, [host_by_email]) == "no_show"


def test_detect_notetaker_bot_does_not_count_as_a_show():
    assert ns.detect(START + timedelta(minutes=10), SOPIO, [HOST, BOT]) == "no_show"
    assert ns.is_bot({"name": "Otter.ai Notetaker"}) and not ns.is_bot({"name": "Sopio S"})


def test_detect_join_after_grace_only_is_no_show_by_the_rule():
    # a join at +12 m does not retroactively make +10 m a show; process() turns it into late_show
    assert ns.detect(START + timedelta(minutes=13), SOPIO, [HOST, lead_join(12)]) == "no_show"


def test_detect_fireflies_fallback_when_no_join_events():
    after_end = START + timedelta(minutes=20)
    assert ns.detect(after_end, SOPIO, [], fireflies_transcript_len=0) == "no_show"
    assert ns.detect(after_end, SOPIO, [], fireflies_transcript_len=1200) == "showed"
    assert ns.detect(START + timedelta(minutes=5), SOPIO, [], fireflies_transcript_len=0) == "pending"


# ------------------------------------------------------------ process / recovery
def test_no_show_flag_marks_ghl_noshow_and_schedules_full_recovery(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    res = ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    assert res["state"] == "no_show" and res["events"] == ["no_show"] and res["no_show_count"] == 1
    actions = {a["action"]: a for a in res["actions"]}
    assert actions["update_appointment_status"]["payload"] == {"status": "noshow"}
    assert actions["update_appointment_status"]["status"] == "would_do"
    assert actions["create_note"]["status"] == "would_do"
    # pipeline untouched
    assert not any(r["action"] == "update_opportunity_stage" for r in job_log.read_shadow_log())
    rec_key = ns.recovery_key(SOPIO["id"], START.isoformat())
    touches = store.get(rec_key)["touches"]
    timeline = [(t["template_key"], t["channel"], t["when_iso"], t["skipped"], t["skip_reason"]) for t in touches]
    f = flagged
    assert timeline == [
        ("ns_still_on_sms", "sms", (f + timedelta(minutes=5)).isoformat(), True, "a2p_not_registered"),
        ("ns_still_on_email", "email", (f + timedelta(minutes=5)).isoformat(), False, None),
        ("ns_call_task", "task", (f + timedelta(minutes=10)).isoformat(), False, None),
        ("ns_reschedule_email", "email", (f + timedelta(hours=1)).isoformat(), False, None),
        ("ns_d1_other_channel_task", "task", (f + timedelta(days=1)).isoformat(), False, None),
        # +3 days lands on a Sunday, so the email leg is deferred to Monday
        # 07:00 CT like every other proactive email the engine sends
        ("ns_d3_value_email", "email", "2026-09-28T07:00:00-05:00", False, None),
        ("ns_d7_yes_no_email", "email", (f + timedelta(days=7)).isoformat(), False, None),
        ("ns_d14_breakup_email", "email", (f + timedelta(days=14)).isoformat(), False, None),
    ]
    assert touches[-1]["meta"]["after"] == "stage:follow_up_later"
    # +5 m touch is due right at the flag? no: nothing due yet at flag time
    assert res["run"]["would_do"] == []
    assert rec.requests == []
    # the two offered slots are reserved so nobody else gets them, in BOTH
    # registries: the recovery-only key (bare ISO strings) and approval.py's
    # "offered_slots" (dict rows), which is the one cadence and approval read.
    assert store.get(ns.OFFERED_SLOTS_KEY) == fixed_slots(None)["slots"]
    shared_rows = store.get("offered_slots")
    assert all(isinstance(r, dict) for r in shared_rows)
    assert sorted(r["slot"] for r in shared_rows) == sorted(fixed_slots(None)["slots"])
    assert {r["source"] for r in shared_rows} == {"no_show_recovery"}


def test_recovery_timing_and_copy(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)

    assert ns.run_recovery(flagged + timedelta(minutes=4), store, ghl)["would_do"] == []
    r5 = ns.run_recovery(flagged + timedelta(minutes=5), store, ghl)
    assert [e["template"] for e in r5["would_do"]] == ["ns_still_on_email"]
    assert r5["skipped"] == []  # the SMS leg was already skipped (a2p_not_registered) when scheduled
    sms = [t for t in store.get(ns.recovery_key(SOPIO["id"], START.isoformat()))["touches"] if t["channel"] == "sms"][0]
    assert sms["skipped"] and sms["skip_reason"] == "a2p_not_registered" and not sms["sent"]
    email = job_log.read_shadow_log()[-1]["payload"]
    assert email["subject"] == "Still on?" and "10 more minutes" in email["message"] and SOPIO["zoom_link"] in email["message"]

    r10 = ns.run_recovery(flagged + timedelta(minutes=10), store, ghl)
    assert [e["template"] for e in r10["would_do"]] == ["ns_call_task"]
    task = job_log.read_shadow_log()[-1]["payload"]
    assert "237-791-5700" in task["body"] and "voicemail" in task["body"].lower() and "Lorenzo Villarreal" in task["body"]

    r60 = ns.run_recovery(flagged + timedelta(hours=1), store, ghl)
    assert [e["template"] for e in r60["would_do"]] == ["ns_reschedule_email"]
    body = job_log.read_shadow_log()[-1]["payload"]["message"]
    assert "Fri 2:00pm or Mon 3:30pm CT" in body and settings.BOOKING_URL in body and "Missed you" in job_log.read_shadow_log()[-1]["payload"]["subject"]

    r1d = ns.run_recovery(flagged + timedelta(days=1), store, ghl)
    assert [e["template"] for e in r1d["would_do"]] == ["ns_d1_other_channel_task"]  # SMS leg replaced by a task until A2P
    # the +3 day email was deferred off the Sunday; run it at the time it is armed
    d3_at = slots.parse_iso(armed_at(store, "ns_d3_value_email"))
    r3d = ns.run_recovery(d3_at, store, ghl, slots_fn=fixed_slots)
    assert [e["template"] for e in r3d["would_do"]] == ["ns_d3_value_email"]
    assert "$150M/year" in job_log.read_shadow_log()[-1]["payload"]["message"]  # offer-sheet proof line, reactivation
    r7d = ns.run_recovery(flagged + timedelta(days=7), store, ghl)
    assert [e["template"] for e in r7d["would_do"]] == ["ns_d7_yes_no_email"]
    assert job_log.read_shadow_log()[-1]["payload"]["subject"] == "Should I close your file?"
    r14 = ns.run_recovery(flagged + timedelta(days=14), store, ghl)
    assert [e["template"] for e in r14["would_do"]] == ["ns_d14_breakup_email"]
    assert r14["stage_moves"] and r14["stage_moves"][0]["payload"]["stage"] == "follow_up_later"
    move = [r for r in job_log.read_shadow_log() if r["action"] == "update_opportunity_stage"][-1]["payload"]
    assert move["pipelineStageId"] == settings.GHL_STAGES["follow_up_later"] and move["opportunity_id"] == SOPIO["opportunity_id"]
    assert store.get(ns.state_key(SOPIO["id"]))["state"] == "done"
    assert rec.requests == []

    # copy rules across the whole sequence
    for t in store.get(ns.recovery_key(SOPIO["id"], START.isoformat()))["touches"]:
        text = (t["subject"] or "") + t["body"]
        assert "—" not in text and "automat" not in text.lower()
        if t["channel"] == "email":
            assert t["body"].rstrip().endswith("Lorenzo")


def test_late_show_after_flag_cancels_recovery_and_flips_status(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    res = ns.process(START + timedelta(minutes=13), SOPIO, [HOST, lead_join(12)], store, ghl, slots_fn=fixed_slots)
    assert res["events"] == ["late_show"] and res["state"] == "late_show"
    assert res["actions"][0]["payload"] == {"status": "showed"} and res["actions"][0]["status"] == "would_do"
    touches = store.get(ns.recovery_key(SOPIO["id"], START.isoformat()))["touches"]
    assert all(t["skipped"] for t in touches)
    assert {t["skip_reason"] for t in touches} == {"late_show", "a2p_not_registered"}
    # nothing goes out afterwards
    assert ns.run_recovery(flagged + timedelta(hours=2), store, ghl)["would_do"] == []
    assert rec.requests == []


def test_showed_path_marks_showed_once(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    res = ns.process(START + timedelta(minutes=4), SOPIO, [HOST, lead_join(3)], store, ghl)
    assert res["events"] == ["showed"] and res["actions"][0]["payload"] == {"status": "showed"}
    again = ns.process(START + timedelta(minutes=20), SOPIO, [HOST, lead_join(3)], store, ghl)
    assert again["events"] == [] and again["actions"] == []
    before = ns.process(START - timedelta(minutes=5), dict(SOPIO, id="other"), [], store, ghl)
    assert before["events"] == [] and before["state"] == "pending"
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) is None
    assert rec.requests == []


def test_repeat_policy_full_then_two_then_one_then_lost(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    first = SOPIO
    second = dict(SOPIO, id="appt2", start_iso="2026-09-29T14:00:00-05:00", end_iso="2026-09-29T14:15:00-05:00")
    third = dict(SOPIO, id="appt3", start_iso="2026-10-06T14:00:00-05:00", end_iso="2026-10-06T14:15:00-05:00")

    r1 = ns.process(slots.parse_iso(first["start_iso"]) + timedelta(minutes=10), first, [host_join_for(first)], store, ghl, slots_fn=fixed_slots)
    r2 = ns.process(slots.parse_iso(second["start_iso"]) + timedelta(minutes=10), second, [host_join_for(second)], store, ghl, slots_fn=fixed_slots)
    r3 = ns.process(slots.parse_iso(third["start_iso"]) + timedelta(minutes=10), third, [host_join_for(third)], store, ghl, slots_fn=fixed_slots)
    assert (r1["no_show_count"], r2["no_show_count"], r3["no_show_count"]) == (1, 2, 3)
    assert (r1["recovery_touches"], r2["recovery_touches"], r3["recovery_touches"]) == (8, 3, 2)
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) == 3

    t2 = store.get(ns.recovery_key("appt2", "2026-09-29T14:00:00-05:00"))["touches"]
    assert [t["template_key"] for t in t2] == ["ns_still_on_sms", "ns_still_on_email", "ns_reschedule_email"]
    assert t2[-1]["meta"]["after"] == "note:second_no_show_pattern"
    assert "second time" in t2[-1]["body"]

    t3 = store.get(ns.recovery_key("appt3", "2026-10-06T14:00:00-05:00"))["touches"]
    assert [t["template_key"] for t in t3] == ["ns_still_on_sms", "ns_still_on_email"]
    assert t3[-1]["meta"]["after"] == "stage:lost"

    # third sequence: the single email goes out, then the opportunity moves to Lost
    flagged3 = slots.parse_iso(third["start_iso"]) + timedelta(minutes=10)
    out = ns.run_recovery(flagged3 + timedelta(minutes=5), store, ghl, appointment_id="appt3")
    assert [e["template"] for e in out["would_do"]] == ["ns_still_on_email"]
    assert out["stage_moves"][0]["payload"]["stage"] == "lost" and out["stage_moves"][0]["status"] == "would_do"
    lost = [r for r in job_log.read_shadow_log() if r["action"] == "update_opportunity_stage"][-1]["payload"]
    assert lost["pipelineStageId"] == settings.GHL_STAGES["lost"] and lost["status"] == "lost"
    assert rec.requests == []


def test_rebooking_cancels_pending_recovery(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    ns.process(START + timedelta(minutes=10), SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    n = ns.cancel_recovery_for_rebooking(store, SOPIO["id"])
    assert n == 7  # everything except the already-skipped SMS leg
    assert store.get(ns.state_key(SOPIO["id"]))["state"] == "done"
    assert ns.run_recovery(START + timedelta(days=3), store, ghl)["would_do"] == []


def test_fresh_two_slots_falls_back_to_synthetic_grid_without_token(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    now = datetime.fromisoformat("2026-09-24T15:10:00-05:00")  # Thursday
    info = ns.fresh_two_slots(now, ghl, store)
    assert info["source"] == "synthetic_open_hours" and len(info["slots"]) == 2 and info["text"].endswith("CT")
    for iso in info["slots"]:
        dt = slots.parse_iso(iso)
        assert dt.weekday() < 5 and 12 <= dt.hour < 18 and dt >= now + timedelta(hours=4)
    assert rec.requests == []


def test_fresh_two_slots_uses_ghl_when_token_present(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    payload = {"2026-09-25": {"slots": ["2026-09-25T13:00:00-05:00", "2026-09-25T13:30:00-05:00"]},
               "2026-09-28": {"slots": ["2026-09-28T16:00:00-05:00"]}, "traceId": "x"}
    ghl = GHL(token="tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    info = ns.fresh_two_slots(datetime.fromisoformat("2026-09-24T15:10:00-05:00"), ghl, store, already_offered=["2026-09-25T13:00:00-05:00"])
    assert info["source"] == "ghl"
    assert info["slots"] == ["2026-09-25T13:30:00-05:00", "2026-09-28T16:00:00-05:00"]
    assert info["text"] == "Fri 1:30pm or Mon 4:00pm CT"


def test_synthetic_slots_are_never_sent_live(tmp_env, live_mode):
    touches = ns.recovery_touches(SOPIO, START + timedelta(minutes=10), 1, slots_text="Fri 2:00pm or Mon 3:30pm CT", slots_source="synthetic_open_hours")
    body = [t for t in touches if t.template_key == "ns_reschedule_email"][0].body
    assert "Two times" not in body and settings.BOOKING_URL in body


def test_inbound_reply_cancels_recovery(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    ns.process(START + timedelta(minutes=10), SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    assert ns.cancel_recovery(store, SOPIO["id"], "replied") == 7
    assert store.get(ns.state_key(SOPIO["id"]))["done_reason"] == "replied"
    assert ns.run_recovery(START + timedelta(hours=2), store, ghl)["would_do"] == [] and rec.requests == []


# ------------------------------------------- detection: evidence vs silence
def test_detect_returns_unknown_when_no_zoom_telemetry_exists():
    """The Discovery Call calendar is on Google Meet and no Zoom app exists,
    so joins is always []. "Nobody joined" and "we were never told" are not
    the same thing, and only the first may flag a no-show."""
    assert ns.detect(START + timedelta(minutes=30), SOPIO, []) == "unknown"
    assert ns.detect(START + timedelta(minutes=5), SOPIO, []) == "unknown"
    meet = dict(SOPIO, zoom_link="https://meet.google.com/abc-defg-hij")
    assert ns.detect(START + timedelta(hours=2), meet, []) == "unknown"
    # any evidence channel restores the old behaviour
    assert ns.detect(START + timedelta(minutes=30), SOPIO, [HOST]) == "no_show"
    assert ns.detect(START + timedelta(minutes=30), SOPIO, [], fireflies_transcript_len=0) == "no_show"
    assert ns.detect(START + timedelta(minutes=30), SOPIO, [],
                     meeting_signals={"ended": {"at_iso": START.isoformat()}}) == "no_show"
    # and a hand-set GHL status always wins
    assert ns.detect(START + timedelta(minutes=30), dict(SOPIO, ghl_status="showed"), []) == "showed"
    assert ns.detect(START + timedelta(minutes=3), dict(SOPIO, ghl_status="noshow"), []) == "no_show"


def test_no_telemetry_raises_one_task_for_lorenzo_and_never_flags(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    res = ns.process(START + timedelta(minutes=11), SOPIO, [], store, ghl, slots_fn=fixed_slots)
    assert res["verdict"] == "unknown" and res["state"] == "pending" and res["events"] == ["no_telemetry"]
    assert [a["action"] for a in res["actions"]] == ["create_task"]
    task = job_log.read_shadow_log()[-1]["payload"]
    assert "showed or no-show by hand" in task["title"] and "recovery sequence" in task["body"]
    assert store.keys("recovery:") == [] and store.get("no_show_count:%s" % SOPIO["contact_id"]) is None
    # not repeated on every 5-minute tick
    again = ns.process(START + timedelta(minutes=25), SOPIO, [], store, ghl, slots_fn=fixed_slots)
    assert again["actions"] == [] and again["events"] == []
    assert rec.requests == []


def test_detect_ignores_a_join_from_an_earlier_meeting_on_the_same_link():
    """Personal Meeting IDs and recurring links are reused, and joins_by_appt
    accumulates across reschedules, so a join must sit in this call's window."""
    later = dict(SOPIO, id="a_later", start_iso="2026-10-01T15:00:00-05:00", end_iso="2026-10-01T15:15:00-05:00")
    stale = lead_join(3)  # a real join, but to the 2026-09-24 meeting
    assert ns.detect(START + timedelta(minutes=5), SOPIO, [HOST, stale]) == "showed"
    assert ns.detect(slots.parse_iso(later["start_iso"]) + timedelta(minutes=30), later, [stale]) == "unknown"
    assert ns.detect(slots.parse_iso(later["start_iso"]) + timedelta(minutes=30), later,
                     [stale, host_join_for(later)]) == "no_show"
    # a join 31 minutes before the call is outside the window, 29 is inside
    assert ns.joins_in_window(SOPIO, [lead_join(-31)]) == []
    assert ns.joins_in_window(SOPIO, [lead_join(-29)]) == [lead_join(-29)]


def test_a_join_delivered_late_but_timed_before_the_flag_is_still_a_late_show(tmp_env, shadow_mode):
    """Zoom retries and backlogs meeting.participant_joined.

    The guard used to require ``join_time > flagged_at``, so a join at start+2 m
    delivered one minute after the start+10 m flag was discarded and the lead
    sitting in the meeting got "Still on? I am on the Zoom now" plus the whole
    14-day ladder. Only joins OUTSIDE this appointment's window (a reused
    meeting id) may be ignored, and joins_in_window already does that.
    """
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    # a stale join from an earlier call on the same reused meeting id (outside
    # the start-30m..end+30m window) must not cancel a running recovery
    stale = dict(lead_join(-90), name="Someone Else", email="other@company.com")
    res = ns.process(flagged + timedelta(minutes=1), SOPIO, [HOST, stale], store, ghl, slots_fn=fixed_slots)
    assert res["events"] == [] and res["state"] == "no_show"
    assert store.get(ns.state_key(SOPIO["id"]))["state"] == "no_show"
    # the delayed webhook for THIS call lands: join_time start+2 m, i.e. before
    # the flag. It is still a show.
    res = ns.process(flagged + timedelta(minutes=2), SOPIO, [HOST, lead_join(2)], store, ghl, slots_fn=fixed_slots)
    assert res["events"] == ["late_show"] and res["state"] == "late_show"
    touches = store.get(ns.recovery_key(SOPIO["id"], START.isoformat()))["touches"]
    assert all(t["skipped"] for t in touches)
    assert ns.run_recovery(flagged + timedelta(hours=2), store, ghl)["would_do"] == []
    assert rec.requests == []


def test_a_join_after_the_flag_is_a_late_show(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    res = ns.process(flagged + timedelta(minutes=3), SOPIO, [HOST, lead_join(12)], store, ghl, slots_fn=fixed_slots)
    assert res["events"] == ["late_show"]
    assert rec.requests == []


def test_a_rescheduled_call_on_the_same_appointment_id_can_no_show_again(tmp_env, shadow_mode):
    """GHL keeps the appointment id and moves startTime on a reschedule, so a
    terminal state keyed on the id alone froze the lead forever."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    assert ns.cancel_recovery(store, SOPIO["id"], "replied") == 7
    assert store.get(ns.state_key(SOPIO["id"]))["state"] == "done"

    later_start = datetime.fromisoformat("2026-10-01T15:00:00-05:00")
    again = dict(SOPIO, start_iso=later_start.isoformat(), end_iso=(later_start + timedelta(minutes=15)).isoformat())
    res = ns.process(later_start + timedelta(minutes=10), again, [host_join_for(again)], store, ghl, slots_fn=fixed_slots)
    assert res["events"] == ["rebooked", "no_show"] and res["no_show_count"] == 2
    assert store.get(ns.recovery_key(SOPIO["id"], later_start.isoformat())) is not None
    assert rec.requests == []


# ------------------------------------------- rebooking cancels the sequence
def test_a_rebooking_stops_the_recovery_before_the_breakup_email(tmp_env, shadow_mode):
    """Sopio no-shows, then rebooks through the widget (same appointment id,
    new startTime). She must not receive "Should I close your file?"."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    new_start = datetime.fromisoformat("2026-10-01T12:00:00-05:00")
    rebooked = dict(SOPIO, start_iso=new_start.isoformat(), end_iso=(new_start + timedelta(minutes=15)).isoformat())
    res = ns.process(flagged + timedelta(hours=2), rebooked, [], store, ghl, slots_fn=fixed_slots)
    assert res["events"] == ["rebooked"] and res["rebooked_cancelled"] == 7
    out = ns.run_recovery(flagged + timedelta(days=14), store, ghl)
    assert out["would_do"] == [] and out["stage_moves"] == []
    assert not [r for r in job_log.read_shadow_log() if r["action"] == "update_opportunity_stage"]
    assert rec.requests == []


def test_run_recovery_skips_a_contact_with_a_call_already_on_the_books(tmp_env, shadow_mode):
    """The rebooking may be a brand new appointment id. The tick hands the
    upcoming appointments in so the old sequence stops anyway."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    later = {"id": "brand_new", "contact_id": SOPIO["contact_id"], "start_iso": "2026-10-08T12:00:00-05:00"}
    out = ns.run_recovery(flagged + timedelta(days=7), store, ghl, upcoming_appointments=[later])
    assert out["would_do"] == [] and out["cancelled"] and out["cancelled"][0]["reason"] == "rebooked"
    assert ns.run_recovery(flagged + timedelta(days=14), store, ghl)["would_do"] == []
    assert rec.requests == []


# ------------------------------------------- SOP-005 counter
def test_a_held_call_resets_the_no_show_counter(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    ns.process(START + timedelta(minutes=10), SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) == 1

    second_start = datetime.fromisoformat("2026-10-01T15:00:00-05:00")
    second = dict(SOPIO, id="appt_held", start_iso=second_start.isoformat(),
                  end_iso=(second_start + timedelta(minutes=15)).isoformat())
    join = {"at_iso": (second_start + timedelta(minutes=2)).isoformat(), "name": "Sopio S",
            "email": SOPIO["email"]}
    held = ns.process(second_start + timedelta(minutes=4), second, [host_join_for(second), join], store, ghl)
    assert held["state"] == "showed"
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) == 0

    third_start = datetime.fromisoformat("2026-10-08T15:00:00-05:00")
    third = dict(SOPIO, id="appt_missed_again", start_iso=third_start.isoformat(),
                 end_iso=(third_start + timedelta(minutes=15)).isoformat())
    res = ns.process(third_start + timedelta(minutes=10), third, [host_join_for(third)], store, ghl, slots_fn=fixed_slots)
    assert res["no_show_count"] == 1 and res["recovery_touches"] == 8  # full sequence, not the 3-touch repeat one
    assert rec.requests == []


def test_a_late_show_gives_the_counter_back(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) == 1
    ns.process(flagged + timedelta(minutes=3), SOPIO, [HOST, lead_join(12)], store, ghl, slots_fn=fixed_slots)
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) == 0
    assert rec.requests == []


# ------------------------------------------- stage moves and persistence
def test_a_skipped_final_touch_does_not_move_the_pipeline(tmp_env, shadow_mode):
    """Every touch skipped (no contact id) must not end in a Follow Up Later
    move: Lorenzo would be looking at an abandoned lead nobody ever contacted."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    faceless = dict(SOPIO, contact_id=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, faceless, [HOST], store, ghl, slots_fn=fixed_slots)
    out = ns.run_recovery(flagged + timedelta(days=14), store, ghl)
    assert out["would_do"] == []
    assert not [m for m in out["stage_moves"] if m["action"] == "update_opportunity_stage"]
    assert not [r for r in job_log.read_shadow_log() if r["action"] == "update_opportunity_stage"]
    assert rec.requests == []


def test_sender_ghl_never_moves_the_pipeline_either(tmp_env, shadow_mode, monkeypatch):
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    monkeypatch.setenv("SHOW_RATE_SENDER", "ghl")
    out = ns.run_recovery(flagged + timedelta(days=14), store, ghl)
    # one call 14 days after the flag: the early legs are dropped as too_late
    # (see MAX_LATENESS) and everything still due is skipped as sender_is_ghl
    assert {e["reason"] for e in out["skipped"]} == {"sender_is_ghl", "too_late"}
    assert [e["template"] for e in out["skipped"] if e["reason"] == "sender_is_ghl"] == ["ns_d14_breakup_email"]
    assert not [m for m in out["stage_moves"] if m["action"] == "update_opportunity_stage"]
    # instead Lorenzo gets a task to decide
    assert [m["payload"]["stage"] for m in out["stage_moves"]] == ["follow_up_later"]
    assert out["stage_moves"][0]["action"] == "create_task"


def test_a_crash_after_a_send_does_not_re_send_the_touch(tmp_env, shadow_mode):
    """The sent flag is persisted per touch, so an exception in the stage move
    (an ordinary GHL 500) cannot roll back the bookkeeping for the send."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)

    boom = {"n": 0}

    def explode(*a, **k):
        boom["n"] += 1
        raise RuntimeError("HTTP 500 from GHL")

    real_stage_move = ghl.update_opportunity_stage
    ghl.update_opportunity_stage = explode
    with pytest.raises(RuntimeError):
        ns.run_recovery(flagged + timedelta(days=14), store, ghl)
    assert boom["n"] == 1
    breakup = [t for t in store.get(ns.recovery_key(SOPIO["id"], START.isoformat()))["touches"]
               if t["template_key"] == "ns_d14_breakup_email"][0]
    assert breakup["sent"] is True  # persisted before the stage move ran
    ghl.update_opportunity_stage = real_stage_move
    out = ns.run_recovery(flagged + timedelta(days=15), store, ghl)
    assert out["would_do"] == []  # "Closing your file" is not sent twice
    sent = [r for r in job_log.read_shadow_log() if r.get("payload", {}).get("subject") == "Closing your file"]
    assert len(sent) == 1


def test_a_failed_send_leaves_the_recovery_touch_pending_for_the_next_tick(tmp_env, shadow_mode, monkeypatch):
    """A transport error or a missing token must not burn the touch: it is an
    error to retry, not a permanent skip."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)

    def boom(*a, **k):
        raise RuntimeError("ghl_token_missing")

    real_send = ghl.send_message
    ghl.send_message = boom
    out = ns.run_recovery(flagged + timedelta(minutes=5), store, ghl)
    assert out["sent"] == [] and out["would_do"] == [] and len(out["errors"]) == 1
    touch = [t for t in store.get(ns.recovery_key(SOPIO["id"], START.isoformat()))["touches"]
             if t["template_key"] == "ns_still_on_email"][0]
    assert not touch.get("sent") and not touch.get("skipped")  # still pending
    ghl.send_message = real_send
    again = ns.run_recovery(flagged + timedelta(minutes=6), store, ghl)
    assert [e["template"] for e in again["would_do"]] == ["ns_still_on_email"]
    # and the retryable-skip path is covered too
    assert "ghl_token_missing" in ns.RETRYABLE_SKIP_REASONS


# ------------------------------------------- the offered-slot registry
def test_recovery_slots_do_not_corrupt_the_approval_registry(tmp_env, shadow_mode):
    """approval.py owns "offered_slots" as a list of dicts. Writing bare ISO
    strings into it made approval.offered_slots raise on every later reply."""
    from services.reply_engine import approval as approval_mod

    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    now = START + timedelta(minutes=10)
    # another lead's time that does NOT overlap the recovery pair (an
    # overlapping one is now refused outright: see
    # test_hold_status_and_hold_checks.py, the claim_slots race tests)
    approval_mod.reserve_slots(store, "someone@else.com", ["2026-09-30T13:00:00-05:00"], "ap1", now)
    ns.process(now, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    assert all(isinstance(r, dict) for r in store.get("offered_slots"))
    # both registries now describe the same reservations: approval.offered_slots
    # (which cadence and every positive-reply draft read) sees the recovery
    # slots too, so the same 15 minutes cannot be promised to a second lead.
    assert sorted(set(approval_mod.offered_slots(store, now))) == sorted(
        set(["2026-09-30T13:00:00-05:00", "2026-09-25T14:00:00-05:00", "2026-09-28T15:30:00-05:00"]))
    assert store.get(ns.OFFERED_SLOTS_KEY) == fixed_slots(None)["slots"]


def test_recovery_never_offers_a_slot_already_promised_to_another_lead(tmp_env, shadow_mode):
    from services.reply_engine import approval as approval_mod

    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    now = datetime.fromisoformat("2026-09-24T15:10:00-05:00")
    grid = ns.fresh_two_slots(now, ghl, store)
    taken = grid["slots"][0]
    approval_mod.reserve_slots(store, "someone@else.com", [taken], "ap1", now)
    again = ns.fresh_two_slots(now, ghl, store)
    assert taken not in again["slots"]


def test_offered_slot_registry_is_pruned_of_times_already_past(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    # seeded directly: reserve_recovery_slots (no conflict check, no caller) is
    # gone, and this test is only about recovery_offered's pruning
    store.set(ns.OFFERED_SLOTS_KEY, ["2026-09-24T14:00:00-05:00", "2026-10-02T14:00:00-05:00"])
    kept = ns.recovery_offered(store, datetime.fromisoformat("2026-09-30T09:00:00-05:00"))
    assert kept == ["2026-10-02T14:00:00-05:00"]
    assert store.get(ns.OFFERED_SLOTS_KEY) == ["2026-10-02T14:00:00-05:00"]


# --------------------------------------------------- A3 review fixes (2026-09-22)
def test_a_human_named_fred_or_gongora_is_not_taken_for_a_notetaker():
    """BOT_NAME_MARKERS used to be matched as bare substrings against the name
    AND the whole email, so "Fred Wilson" was a Fireflies bot and
    manuel@gongoraservices.com was a Gong bot. A discarded lead join is how
    someone who attended ends up in the 14-day recovery ladder."""
    humans = [
        {"name": "Fred Wilson", "email": "fred.wilson@acmecleaning.com"},
        {"name": "Manuel Gongora", "email": "manuel@gongoraservices.com"},
        {"name": "Sopio Svanishvili", "email": "sopiosvanishvili@taxfoaccounting.com"},
        {"name": "Tiffany Spelman", "email": "tiffany@spelmanreads.com"},
        {"name": "Reid Fathomville", "email": "reid@fathomvilleroofing.com"},
    ]
    for j in humans:
        assert not ns.is_bot(j), j
    bots = [
        {"name": "Fred from Fireflies", "email": ""},
        {"name": "Otter.ai Notetaker", "email": ""},
        {"name": "Notetaker", "email": "notes@read.ai"},
        {"name": "Meeting Assistant", "email": ""},
        {"name": "Anything", "email": "bot@fireflies.ai"},
        {"name": "Anything", "email": "recorder@gong.io"},
    ]
    for j in bots:
        assert ns.is_bot(j), j
    # and the appointment's own contact address always wins over the heuristic
    fred = {"at_iso": (START + timedelta(minutes=1)).isoformat(), "name": "Fred",
            "email": "fred.wilson@acmecleaning.com"}
    appt = dict(SOPIO, email="fred.wilson@acmecleaning.com")
    assert ns.detect(START + timedelta(minutes=10), appt, [HOST, fred]) == "showed"


def test_a_stale_meeting_ended_signal_does_not_turn_silence_into_a_no_show():
    """With no joins at all and only a signal from an earlier call on the same
    reused link, the honest answer is 'unknown', not 'no_show'."""
    from services.reply_engine import zoom_webhook as zw

    appt = dict(SOPIO, start_iso="2026-09-24T15:00:00-05:00", end_iso="2026-09-24T15:15:00-05:00")
    stale = {"ended": {"at_iso": "2026-09-17T15:16:00-05:00"}, "started": None}
    assert ns.detect(START + timedelta(minutes=10), appt, [], meeting_signals=stale) == "no_show"
    # ...but zoom_webhook never reports a signal from another call in the first
    # place, so what detect() actually receives is "no telemetry"
    assert zw._signal_in_window(stale["ended"], zw._appointment_window(appt)) is None
    assert ns.detect(START + timedelta(minutes=10), appt, [],
                     meeting_signals={"started": None, "ended": None}) == "unknown"


def test_a_transcript_with_words_in_it_is_never_a_no_show():
    """The Fireflies branch was gated on now >= end, so a 900-character
    transcript checked at start+12 m fell through to the deadline rule and
    produced a no_show verdict."""
    assert ns.detect(START + timedelta(minutes=12), SOPIO, [], fireflies_transcript_len=900) == "showed"
    assert ns.detect(START + timedelta(minutes=20), SOPIO, [], fireflies_transcript_len=900) == "showed"
    assert ns.detect(START + timedelta(minutes=12), SOPIO, [], fireflies_transcript_len=0) == "pending"
    assert ns.detect(START + timedelta(minutes=20), SOPIO, [], fireflies_transcript_len=0) == "no_show"


def test_the_miss_is_claimed_before_any_ghl_write(tmp_env, shadow_mode):
    """A GHL 5xx between the counter bump and the state write used to leave
    no_show_count=1 with no state record, so the next tick flagged the SAME
    miss again, the counter reached 2, and the lead's first miss got the
    second-no-show copy ("I know this is the second time ...")."""
    class FlakyGHL(object):
        def __init__(self):
            self.calls = 0

        def update_appointment_status(self, *a, **k):
            self.calls += 1
            raise RuntimeError("GHL PUT ... -> HTTP 500")

        def create_note(self, *a, **k):
            return {"shadow": True}

        def create_task(self, *a, **k):
            return {"shadow": True}

        def get_free_slots(self, *a, **k):
            return None

    store = JsonFileStore(tmp_env / "s.json")
    ghl = FlakyGHL()
    flagged = START + timedelta(minutes=10)
    with pytest.raises(RuntimeError):
        ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    # the counter AND the state record are both already durable
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) == 1
    assert store.get(ns.state_key(SOPIO["id"]))["state"] == "no_show"
    # the next tick does not count the same miss twice
    good, grec = make_ghl(token=None)
    res = ns.process(flagged + timedelta(minutes=5), SOPIO, [HOST], store, good, slots_fn=fixed_slots)
    assert store.get("no_show_count:%s" % SOPIO["contact_id"]) == 1
    assert res["state"] == "no_show"
    touches = store.get(ns.recovery_key(SOPIO["id"], START.isoformat()))["touches"]
    assert len(touches) == 8  # the FULL first-no-show ladder, not the 2-touch second one
    assert not any("second time the timing did not work out" in (t["body"] or "") for t in touches)


def test_a_crash_between_the_send_and_the_store_write_does_not_re_send(tmp_env, shadow_mode):
    """The touch is claimed before it is dispatched, so a container killed
    between the send and the bookkeeping cannot send the same message twice."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    key = ns.recovery_key(SOPIO["id"], START.isoformat())
    out = ns.run_recovery(flagged + timedelta(minutes=5), store, ghl)
    assert [e["template"] for e in out["would_do"]] == ["ns_still_on_email"]
    # simulate the crash: the dispatch happened, the record write did not
    crashed = store.get(key)
    for t in crashed["touches"]:
        if t["template_key"] == "ns_still_on_email":
            t["sent"], t["sent_at"], t["result"] = False, None, None
    store.set(key, crashed)
    again = ns.run_recovery(flagged + timedelta(minutes=6), store, ghl)
    assert again["would_do"] == []
    assert [e["reason"] for e in again["skipped"]] == ["already_dispatched"]
    sends = [r for r in job_log.read_shadow_log() if r.get("action") == "send_message"]
    assert len(sends) == 1


def test_the_recovery_slot_line_is_re_rendered_at_dispatch_time(tmp_env, shadow_mode):
    """Every touch used to be rendered once, at flag time, so the +1 day and
    +3 day messages quoted two slots that had already passed, while the engine
    went on holding those slots against every other lead."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    assert store.get(ns.OFFERED_SLOTS_KEY) == fixed_slots(None)["slots"]

    later = {"slots": ["2026-09-29T13:00:00-05:00", "2026-09-30T16:00:00-05:00"],
             "text": "Tue 1:00pm or Wed 4:00pm CT", "source": "ghl"}
    d3_at = slots.parse_iso(armed_at(store, "ns_d3_value_email"))   # Monday 07:00 CT
    out = ns.run_recovery(d3_at, store, ghl, slots_fn=lambda now: later)
    assert [e["template"] for e in out["would_do"]] == ["ns_d3_value_email"]
    body = job_log.read_shadow_log()[-1]["payload"]["message"]
    assert "Tue 1:00pm or Wed 4:00pm CT" in body
    assert "Fri 2:00pm" not in body           # the dead Friday slot is gone from the copy
    # ...and released, so it is not held against every other lead any more
    assert "2026-09-25T14:00:00-05:00" not in store.get(ns.OFFERED_SLOTS_KEY)
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == sorted(later["slots"] + ["2026-09-28T15:30:00-05:00"])


def test_the_whole_backlog_does_not_fire_after_a_tick_outage(tmp_env, shadow_mode):
    """The 5-minute tick can pause. Without a max lateness the next run sends
    "Still on? I am on the Zoom now" a day after the call ended."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    out = ns.run_recovery(flagged + timedelta(days=1), store, ghl, slots_fn=fixed_slots)
    late = {e["template"] for e in out["skipped"] if e.get("reason") == "too_late"}
    assert "ns_still_on_email" in late and "ns_call_task" in late and "ns_reschedule_email" in late
    assert not any("I am on the Zoom now" in (r.get("payload", {}).get("message") or "")
                   for r in job_log.read_shadow_log())
    # the day-1 leg itself is on time and still goes out
    assert [e["template"] for e in out["would_do"]] == ["ns_d1_other_channel_task"]


def test_a_reply_during_a_tick_is_not_lost_by_the_ticks_write_back(tmp_env, shadow_mode):
    """The FastAPI reply webhook is a separate process from the tick and is not
    covered by _run_lock. run_recovery used to get-then-set the whole record,
    so a cancellation landing mid-loop was overwritten and the lead who had
    just answered kept receiving the full 14-day ladder."""
    store = JsonFileStore(tmp_env / "s.json")
    ghl, rec = make_ghl(token=None)
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    key = ns.recovery_key(SOPIO["id"], START.isoformat())

    real_get = store.get
    fired = {"done": False}

    def racing_get(k, default=None):
        value = real_get(k, default)
        if k == key and not fired["done"]:
            fired["done"] = True          # the webhook lands between read and write
            ns.cancel_recovery(store, SOPIO["id"], "replied")
        return value

    store.get = racing_get
    ns.run_recovery(flagged + timedelta(minutes=5), store, ghl)
    store.get = real_get

    rec_after = store.get(key)
    assert rec_after["cancelled"] == "replied"
    assert all(t["skipped"] or t["sent"] for t in rec_after["touches"])
    later = ns.run_recovery(flagged + timedelta(days=14), store, ghl)
    assert later["would_do"] == [] and later["stage_moves"] == []


def test_a_ladder_that_finishes_late_does_not_overwrite_a_deal_lorenzo_moved(tmp_env, shadow_mode):
    """The 14-day breakup used to write the stage with no read, so a deal moved
    to Proposal Sent or Won in the meantime was silently rewritten."""
    store = JsonFileStore(tmp_env / "s.json")

    class GHLWithOpportunity(object):
        def __init__(self, stage_id):
            self.stage_id = stage_id
            self.moves = []

        def get_opportunity(self, opp_id):
            return {"id": opp_id, "pipelineStageId": self.stage_id}

        def update_opportunity_stage(self, *a, **k):
            self.moves.append((a, k))
            return {"shadow": True}

        def send_message(self, *a, **k):
            return {"shadow": True}

        def create_task(self, *a, **k):
            return {"shadow": True}

        def create_note(self, *a, **k):
            return {"shadow": True}

        def update_appointment_status(self, *a, **k):
            return {"shadow": True}

        def get_free_slots(self, *a, **k):
            return None

    ghl = GHLWithOpportunity(settings.GHL_STAGES["proposal_sent"])
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    d14 = slots.parse_iso(armed_at(store, "ns_d14_breakup_email"))
    out = ns.run_recovery(d14, store, ghl, slots_fn=fixed_slots)
    assert ghl.moves == []
    assert out["stage_moves"][0]["status"] == "skipped:stage_already_proposal_sent"
    assert store.get(ns.state_key(SOPIO["id"]))["done_reason"] == "stage_already_proposal_sent"


def test_the_third_no_show_lost_move_carries_a_no_show_reason(tmp_env, shadow_mode):
    """pipeline_sync.desired_interest() mirrors a Lost opportunity to Instantly
    as no_show (-4) only when the lost reason says so; without one the lead is
    mislabelled not_interested (-1) and the no-show rate cannot be measured."""
    from services.reply_engine import pipeline_sync

    seen = {}

    class GHLWithLostReason(object):
        def get_opportunity(self, opp_id):
            return {"id": opp_id, "pipelineStageId": settings.GHL_STAGES["call_booked"]}

        def update_opportunity_stage(self, opp_id, stage_id, status=None, lost_reason=None):
            seen.update({"stage_id": stage_id, "status": status, "lost_reason": lost_reason})
            return {"shadow": True}

        def send_message(self, *a, **k):
            return {"shadow": True}

        def create_task(self, *a, **k):
            return {"shadow": True}

        def create_note(self, *a, **k):
            return {"shadow": True}

        def update_appointment_status(self, *a, **k):
            return {"shadow": True}

        def get_free_slots(self, *a, **k):
            return None

    store = JsonFileStore(tmp_env / "s.json")
    store.set("no_show_count:%s" % SOPIO["contact_id"], 2)   # this is the third
    ghl = GHLWithLostReason()
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, SOPIO, [HOST], store, ghl, slots_fn=fixed_slots)
    out = ns.run_recovery(flagged + timedelta(minutes=5), store, ghl, slots_fn=fixed_slots)
    assert out["stage_moves"] and seen["status"] == "lost"
    assert seen["lost_reason"] == ns.LOST_REASON_NO_SHOW
    # and that wording is what the S8 mirror looks for
    value, reason, _note = pipeline_sync.desired_interest(
        {"pipelineStageId": seen["stage_id"], "status": "lost", "lostReason": seen["lost_reason"]})
    assert value == pipeline_sync.INTEREST_NO_SHOW == -4
    assert settings.IDS["instantly"]["interest_status_codes"]["-4"] == "no_show"
    assert "no show" in reason


def test_recovery_emails_never_land_on_a_weekend():
    """cadence.py gates on ct.weekday() >= 5 and shared/slots.is_send_time
    exists precisely because within_send_window answers True on a Saturday.
    The recovery ladder used to bypass both."""
    thursday = datetime.fromisoformat("2026-09-24T15:10:00-05:00")
    friday_evening = datetime.fromisoformat("2026-09-25T18:30:00-05:00")
    for flagged, appt in ((thursday, SOPIO),
                          (friday_evening, dict(SOPIO, start_iso="2026-09-25T18:15:00-05:00",
                                                end_iso="2026-09-25T18:30:00-05:00"))):
        for t in ns.recovery_touches(appt, flagged, 1, slots_text="Tue 1:00pm or Wed 4:00pm CT", a2p=True):
            armed = slots.parse_iso(t.when_iso)
            if t.template_key == "ns_still_on_email":
                continue  # the call itself is on a weekday; this one goes out now
            if t.channel in ("email", "sms"):
                assert armed.weekday() < 5, (t.template_key, t.when_iso)
                assert 7 <= armed.hour < 19, (t.template_key, t.when_iso)


MONEY_RE = __import__("re").compile(r"\$[\d,]+(?:\.\d+)?[KMB]?|\b\d+\s*(?:to|-)\s*\d+%")


def test_recovery_copy_has_no_exclamation_mark_and_only_offer_sheet_money():
    """offers.md rule 8 forbids exclamation marks and rule 9 restricts pricing
    to the table. S4 has both guards; S5 had neither, so any future edit to
    PROOF, MECHANISM or the d3/d7/d14 bodies could slip past a green suite."""
    from shared.settings import OFFERS_MD

    seen = set()
    for niche in ("cleaning", "bookkeeping", "recruiting", "generic"):
        for offer in ("reactivation", "outbound"):
            for count in (1, 2, 3):
                appt = dict(SOPIO, niche=niche, offer=offer)
                for t in ns.recovery_touches(appt, START + timedelta(minutes=10), count,
                                             slots_text="Tue 1:00pm or Wed 4:00pm CT", a2p=True):
                    text = (t.subject or "") + "\n" + t.body
                    assert "!" not in text, (niche, offer, count, t.template_key)
                    assert "—" not in text and "automat" not in text.lower()
                    if t.channel == "sms":
                        assert "Lorenzo" in t.body and len(t.body) <= ns.SMS_MAX_LEN
                    for token in MONEY_RE.findall(text):
                        seen.add(token)
                        assert token in OFFERS_MD, (niche, offer, count, t.template_key, token)
    assert {"$150M", "$6M", "$180,000"} <= seen


# ------------------------------------------------ S3 item 4: held -> interest 3
def test_a_held_call_moves_the_lead_to_meeting_completed(tmp_env, shadow_mode):
    """Blueprint S3 item 4 says 'held -> Meeting Completed (3)', but no_show,
    show_rate and the tick never touched Instantly at all, so a call that was
    held sat at interest 2 (meeting_booked) until Lorenzo dragged the
    opportunity to Proposal Sent by hand and the nightly mirror ran. Every held
    call that did not immediately produce a proposal read as still-booked,
    which is the number the Section 6 show-rate KPI divides by."""
    store = JsonFileStore(str(tmp_env / "store.json"))
    appt = dict(SOPIO, campaign_id="f00c5e28-fdc4-4d84-a7e6-dfba9695f35d")
    joins = [host_join_for(appt), lead_join(2)]
    out = ns.process(START + timedelta(minutes=20), appt, joins, store, GHL())
    assert out["state"] == "showed"
    interest = [a for a in out["actions"] if a["action"] == "update_interest_status"]
    assert len(interest) == 1
    assert interest[0]["payload"]["interest_value"] == 3
    assert interest[0]["payload"]["lead_email"] == "sopiosvanishvili@taxfoaccounting.com"
    assert interest[0]["status"] == "would_do"   # guarded: shadow records, sends nothing
    rows = [x for x in job_log.read_shadow_log() if x["action"] == "update_interest_status"]
    assert rows and rows[-1]["payload"]["interest_value"] == 3


def test_the_campaign_id_comes_off_the_appointment_row_when_the_calendar_has_none(tmp_env, shadow_mode):
    """A GHL calendar event carries no campaign key, so the fallback is the
    appointment:<id> row booking.register_booking wrote."""
    store = JsonFileStore(str(tmp_env / "store.json"))
    store.set("appointment:%s" % SOPIO["id"], {"lead_email": "sopiosvanishvili@taxfoaccounting.com",
                                               "campaign_id": "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"})
    appt = dict(SOPIO)
    appt.pop("email", None)
    action = ns.mark_meeting_completed(store, appt, SOPIO["id"])
    assert action["payload"]["campaign_id"] == "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"
    assert action["payload"]["lead_email"] == "sopiosvanishvili@taxfoaccounting.com"


def test_a_call_with_no_instantly_lead_behind_it_is_skipped_not_failed(tmp_env, shadow_mode):
    """A hand-made or widget booking with no campaign is not an error; there is
    simply no Instantly lead to move."""
    store = JsonFileStore(str(tmp_env / "store.json"))
    appt = dict(SOPIO)
    appt.pop("email", None)
    action = ns.mark_meeting_completed(store, appt, "no-such-appt")
    assert action["status"] == "skipped:no_instantly_lead"


def test_interest_3_is_never_reported_as_written_without_a_client_in_live(tmp_env, live_mode):
    """guard_write in live returns {"shadow": False} and performs nothing, so a
    caller with no Instantly client would otherwise see "done" for a write that
    never happened."""
    store = JsonFileStore(str(tmp_env / "store.json"))
    appt = dict(SOPIO, campaign_id="f00c5e28-fdc4-4d84-a7e6-dfba9695f35d")
    action = ns.mark_meeting_completed(store, appt, SOPIO["id"], instantly=None)
    assert action["status"] == "skipped:no_instantly_client"
