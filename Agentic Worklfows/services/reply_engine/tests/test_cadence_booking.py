"""Booking tests (Blueprint S3) on the real September replies. now = 2026-09-21T21:10-05:00."""
import json
from pathlib import Path

import httpx
import pytest

from shared import slots as slot_rules
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.job_log import read_shadow_log

from services.reply_engine import booking, cadence
from services.reply_engine.cadence import LeadState

NOW = slot_rules.parse_iso("2026-09-21T21:10:00-05:00")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPLIES = json.loads((FIXTURES / "instantly_replies_2026-09.json").read_text(encoding="utf-8"))


def reply_text(needle: str) -> str:
    """The recorded reply whose own words (not the quoted history) contain ``needle``."""
    for r in REPLIES:
        if needle in slot_rules.strip_quoted(r.get("text") or ""):
            return r["text"]
    raise AssertionError("fixture reply not found: %s" % needle)


def raising_transport():
    def handler(request):
        raise AssertionError("HTTP request attempted in shadow: %s %s" % (request.method, request.url))

    return httpx.MockTransport(handler)


def sopio():
    return LeadState(lead_email="sopiosvanishvili@taxfoaccounting.com", campaign_id="f00c5e28-fdc4-4d84-a7e6-dfba9695f35d",
                     status="positive_question", first_name="Sopio", company="Taxfo Accounting", eaccount="lorenzov@theadvero.com",
                     last_email_id="01a0c50b-6021-793c-a3b9-81506c6a291b", last_subject="Re: Sopio, question",
                     ghl_contact_id="iDhesF6A9rhdDajGZuYw", ghl_opportunity_id="hStqQMLQ5eSRVnqxnSMq")


# --------------------------------------------------------------- matching
FREE_THU_3 = ["2026-09-24T15:00:00-05:00", "2026-09-25T13:00:00-05:00"]


def test_thursday_4pm_eastern_books_thu_3pm_ct():
    """The tz maths: 4pm ET on Thursday is 15:00 CT. It only books when the
    calendar says that time is free."""
    text = reply_text("Thursday 4pm Eastern time")
    m = booking.evaluate_reply(text, [], NOW, free_slots=FREE_THU_3)
    assert m.slot.isoformat() == "2026-09-24T15:00:00-05:00"
    assert m.status == booking.VALID_SLOT and m.bookable and m.lead_tz == "America/New_York"
    assert m.verified is True and m.slots_source == "provided"
    assert booking.match_reply_to_slot(text, [], NOW, free_slots=FREE_THU_3).isoformat() == "2026-09-24T15:00:00-05:00"


def test_proposed_time_that_collides_with_a_known_booking_is_not_valid():
    """config/ids.json records Sopio's Discovery Call at 2026-09-24T15:00 CT.
    With no calendar to check against, a second prospect asking for "Thursday
    4pm Eastern" must be countered, not booked on top of her."""
    text = reply_text("Thursday 4pm Eastern time")
    m = booking.evaluate_reply(text, [], NOW)
    assert m.status == booking.SLOT_TAKEN and not m.bookable
    assert m.proposed.isoformat() == "2026-09-24T15:00:00-05:00"
    assert m.verified is False and m.slots_source == "default_grid"
    assert m.counter_slots and all(not booking.collides_with_known_booking(c) for c in m.counter_slots)
    body = booking.counter_proposal_text(m, sopio())
    assert "just got taken" in body and cadence.copy_problems(body) == []


def test_counter_slots_come_from_the_calendar_not_the_default_grid():
    free = ["2026-09-23T16:30:00-05:00", "2026-09-24T12:30:00-05:00"]
    m = booking.evaluate_reply("Can we do Thursday at 3pm?", [], NOW, free_slots=free)
    assert m.status == booking.SLOT_TAKEN
    assert m.counter_slots and all(c.isoformat() in free for c in m.counter_slots)
    assert m.counter_slots[0].isoformat() == "2026-09-24T12:30:00-05:00"  # the day they asked for


def test_counter_slots_are_chronological():
    late = booking.evaluate_reply("How about Thursday at 7pm?", [], NOW,
                                  free_slots=["2026-09-24T17:00:00-05:00", "2026-09-24T17:30:00-05:00"])
    assert late.status == booking.OUTSIDE_WINDOW
    assert [c.isoformat() for c in late.counter_slots] == ["2026-09-24T17:00:00-05:00", "2026-09-24T17:30:00-05:00"]


def test_offered_slot_that_is_no_longer_free_is_not_honoured():
    offered = ["2026-09-24T15:00:00-05:00"]
    m = booking.evaluate_reply("Thursday at 3pm works", offered, NOW,
                               free_slots=["2026-09-24T15:30:00-05:00", "2026-09-25T13:00:00-05:00"])
    assert m.status == booking.SLOT_TAKEN and not m.bookable
    assert m.counter_slots[0].isoformat() == "2026-09-24T15:30:00-05:00"


def _auto_reply_indices():
    """Every recorded reply whose subject classify calls an auto-responder.

    The hand-written index list this replaces omitted exactly the eight fixtures
    OOO_STRONG_RE does not catch (11, 23, 26, 29, 31, 37, 41, 44), so the one
    that leaked was the one not tested."""
    from services.reply_engine import classify as classify_mod

    return [i for i, item in enumerate(REPLIES, 1)
            if classify_mod.AUTO_SUBJECT_RE.match(item.get("subject") or "")]


AUTO_REPLY_INDICES = _auto_reply_indices()
# The recorded auto-responders classify's subject rule does not label, but whose
# bodies booking must still refuse on their own.
EXTRA_AUTO_BODY_INDICES = [4, 16, 25, 28, 30, 33, 40, 42, 43]


@pytest.mark.parametrize("idx", AUTO_REPLY_INDICES + EXTRA_AUTO_BODY_INDICES)
def test_auto_responders_never_produce_a_bookable_slot(idx):
    """Out-of-office bodies name dates ("I will return Monday, 9/21") and office
    hours ("open 8am-4pm MST") that parse as meeting times. classify keeps them
    out of book() today; booking refuses them itself as the second layer.

    The subject is the strongest signal, but app.py:416 calls evaluate_reply
    with no subject= at all, so both calls have to refuse: fixture #23 (Sienna
    Consulting) yielded a bookable Tue 12:00 from the "OFFICE HOURS: Mon - Thurs
    10am to 2pm" block in its own signature."""
    item = REPLIES[idx - 1]
    text = item.get("text") or ""
    subject = item.get("subject") or ""
    with_subject = booking.evaluate_reply(text, [], NOW, subject=subject)
    assert with_subject.status == booking.NO_TIME, (idx, subject, with_subject.status, with_subject.slot)
    # the way app.py actually calls it
    without = booking.evaluate_reply(text, [], NOW)
    assert without.status == booking.NO_TIME, (idx, subject, without.status, without.slot)
    assert not without.bookable
    assert booking.match_reply_to_slot(text, [], NOW) is None


def test_every_subject_flagged_auto_reply_is_covered():
    """Guards the list itself: a new fixture must not silently drop out."""
    assert len(AUTO_REPLY_INDICES) >= 23
    for leaky in (11, 23, 26, 29, 31, 37, 41, 44):
        assert leaky in AUTO_REPLY_INDICES


def test_office_hours_in_a_signature_are_not_an_availability_window():
    body = ("Thanks, I will take a look.\n\n-- \nAmanda C. Walker, CPA\n\nOFFICE HOURS:\n\nMon - Thurs 10am to 2pm\n")
    assert "OFFICE HOURS" not in booking.proposal_region(body)
    # a window the writer states themselves still counts
    stated = "I am around Tuesday between 1pm and 4pm if that helps."
    assert "1pm and 4pm" in booking.proposal_region(stated)


def test_monday_at_2_cts_is_next_monday_2pm_ct():
    text = reply_text("Monday  at 2 CTS")
    out = booking.match_reply_to_slot(text, [], NOW)
    assert out.isoformat() == "2026-09-28T14:00:00-05:00"
    assert booking.evaluate_reply(text, [], NOW).status == booking.VALID_SLOT


def test_this_wednesday_1130_is_outside_window_with_counter_proposal():
    text = reply_text("this Wednesday around 11:30 am")
    assert booking.match_reply_to_slot(text, [], NOW) is None
    m = booking.evaluate_reply(text, [], NOW)
    assert m.status == booking.OUTSIDE_WINDOW
    assert m.proposed.isoformat() == "2026-09-23T11:30:00-05:00"
    # Wed 12:00pm is inside the buffer around the 11:30 call config/ids.json records,
    # so the counter starts at 12:30
    assert m.counter_slots and m.counter_slots[0].isoformat() == "2026-09-23T12:30:00-05:00"
    assert all(c.date() == m.proposed.date() for c in m.counter_slots)
    state = LeadState(lead_email="ilmi@shiningarmorcleaningnj.com", first_name="Ilmi")
    body = booking.counter_proposal_text(m, state)
    assert body.startswith("Hey Ilmi,") and "Wed 11:30am CT is a touch early" in body and "Wed 12:30pm" in body
    assert cadence.copy_problems(body) == []


def test_friday_afternoon_2pm_est_is_friday_1pm_ct():
    text = reply_text("How’s 2pm EST?")
    out = booking.match_reply_to_slot(text, [], NOW, free_slots=["2026-09-25T13:00:00-05:00"])
    assert out.isoformat() == "2026-09-25T13:00:00-05:00"


def test_any_day_3_to_6pm_et_proposes_earliest_compliant_slot():
    text = reply_text("every day 3pm-6pm Estern time")
    m = booking.evaluate_reply(text, [], NOW)
    assert m.status == booking.WINDOW_EARLIEST and m.window == (15, 18, "America/New_York")
    # 3-6pm ET = 2-5pm CT; earliest business day after Monday night is Tuesday 14:00 CT
    assert m.slot.isoformat() == "2026-09-22T14:00:00-05:00"
    assert booking.match_reply_to_slot(text, [], NOW).isoformat() == "2026-09-22T14:00:00-05:00"
    m2 = booking.evaluate_reply(text, [], NOW, free_slots=["2026-09-23T16:30:00-05:00", "2026-09-24T12:00:00-05:00"])
    assert m2.slot.isoformat() == "2026-09-23T16:30:00-05:00"


def test_offered_slot_match_accepted_even_when_now_inside_lead_time():
    offered = ["2026-09-22T12:00:00-05:00"]
    now = slot_rules.parse_iso("2026-09-22T09:30:00-05:00")  # < 4 h out, but it was our own offer
    m = booking.evaluate_reply("Tuesday at noon works", offered, now)
    assert m.status == booking.OFFERED_SLOT_MATCH and m.slot.isoformat() == "2026-09-22T12:00:00-05:00"


def test_weekend_and_too_soon_and_horizon():
    assert booking.evaluate_reply("Saturday at 2pm", [], NOW).status == booking.WEEKEND
    soon = booking.evaluate_reply("today at 12:30", [], slot_rules.parse_iso("2026-09-22T09:00:00-05:00"))
    assert soon.status == booking.TOO_SOON and soon.counter_slots
    # any weekday word lands inside 5 business days (7 calendar days); the horizon rule is checked directly
    assert booking.compliance(slot_rules.parse_iso("2026-10-05T14:00:00-05:00"), NOW) == booking.BEYOND_HORIZON
    assert booking.compliance(slot_rules.parse_iso("2026-09-28T14:00:00-05:00"), NOW) is None
    # "next Tuesday" is next week's Tuesday (shared.slots), which is past the
    # 5-business-day horizon from a Monday night: counter, never book.
    nxt = booking.evaluate_reply("next Tuesday at 2pm", [], NOW)
    assert nxt.status == booking.BEYOND_HORIZON and not nxt.bookable and nxt.counter_slots
    assert booking.evaluate_reply("Tuesday at 2pm", [], NOW).status == booking.VALID_SLOT
    assert booking.evaluate_reply("Sounds good, talk soon.", [], NOW).status == booking.NO_TIME
    assert booking.counter_proposal_text(booking.evaluate_reply("Sounds good", [], NOW), sopio()) is None


def test_slot_taken_when_calendar_not_free():
    m = booking.evaluate_reply("Thursday 4pm Eastern time", [], NOW, free_slots=["2026-09-24T15:30:00-05:00"])
    assert m.status == booking.SLOT_TAKEN and m.counter_slots[0].isoformat() == "2026-09-24T15:30:00-05:00"


# ----------------------------------------------------------------- booking
def test_book_in_shadow_makes_zero_http_and_returns_confirmation_draft(tmp_env):
    inst = Instantly(api_key="x", transport=raising_transport())
    ghl = GHL(token="fake-token", transport=raising_transport())
    state = cadence.arm(sopio(), NOW)
    slot = booking.match_reply_to_slot(reply_text("Thursday 4pm Eastern time"), [], NOW, free_slots=FREE_THU_3)
    # the caller passes the free slots it resolved; book() will not write a time
    # it cannot see on the calendar
    res = booking.book(state, slot, ghl, inst, now=NOW, lead_tz="America/New_York", free_slots=FREE_THU_3)
    assert res.shadow is True
    assert res.zoom_not_connected is True and res.zoom_link is None
    assert "zoom_not_connected" in res.problems
    assert res.draft.subject == "Re: Sopio, question"
    assert res.draft.body_text.startswith("Hey Sopio,\n\nLocked in Thu 3:00pm CT (4:00pm ET your time). The calendar "
                                          "invite with the video link follows in a separate email.")
    assert res.draft.body_text.rstrip().endswith("Lorenzo")
    assert "—" not in res.draft.body_text and "!" not in res.draft.body_text
    assert state.cadence["stopped_reason"] == "booked" and state.cadence["booking"]["slot"] == "2026-09-24T15:00:00-05:00"
    assert state.status == "call_booked"
    log = read_shadow_log()
    actions = [(r["system"], r["action"]) for r in log]
    assert ("ghl", "create_appointment") in actions
    assert ("ghl", "update_opportunity_stage") in actions
    assert ("instantly", "update_interest_status") in actions
    appt = [r for r in log if r["action"] == "create_appointment"][-1]["payload"]
    assert appt["calendarId"] == "GDugwLmZNdsD13RBDnRu" and appt["startTime"] == "2026-09-24T15:00:00-05:00"
    assert appt["endTime"] == "2026-09-24T15:15:00-05:00" and appt["title"] == "Lorenzo <> Taxfo Accounting: 15-min reactivation plan"
    stage = [r for r in log if r["action"] == "update_opportunity_stage"][-1]["payload"]
    assert stage["pipelineStageId"] == "f12615dc-66e1-412d-902b-4d1adab812c9" and stage["opportunity_id"] == "hStqQMLQ5eSRVnqxnSMq"
    interest = [r for r in log if r["action"] == "update_interest_status"][-1]["payload"]
    assert interest == {"lead_email": "sopiosvanishvili@taxfoaccounting.com", "campaign_id": "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d", "interest_value": 2}


def test_book_without_clients_or_ghl_token_still_records_intent(tmp_env):
    state = sopio()
    state.ghl_contact_id = None
    state.ghl_opportunity_id = None
    ghl = GHL(token=None, transport=raising_transport())
    res = booking.book(state, "2026-09-25T13:00:00-05:00", ghl, None, now=NOW,
                       free_slots=["2026-09-25T13:00:00-05:00"])
    assert res.shadow is True and res.contact_id is None
    assert "Locked in Fri 1:00pm CT. The calendar invite with the video link follows" in res.draft.body_text
    actions = [r["action"] for r in read_shadow_log()]
    assert "upsert_contact" in actions and "upsert_opportunity" in actions and "update_interest_status" in actions


def test_book_live_with_zoom_uses_the_link(live_mode, tmp_env):
    seen = []

    def ghl_handler(request):
        seen.append((request.method, request.url.path))
        if "free-slots" in request.url.path:
            return httpx.Response(200, json={"2026-09-24": {"slots": ["2026-09-24T15:00:00-05:00"]}})
        if request.url.path.endswith("/appointments"):
            return httpx.Response(200, json={"id": "appt-1", "address": "https://us02web.zoom.us/j/123"})
        return httpx.Response(200, json={"id": "ok"})

    def inst_handler(request):
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "ok"})

    ghl = GHL(token="fake-token", transport=httpx.MockTransport(ghl_handler))
    inst = Instantly(api_key="x", transport=httpx.MockTransport(inst_handler))
    res = booking.book(sopio(), "2026-09-24T15:00:00-05:00", ghl, inst, now=NOW, zoom_connected=True)
    assert res.shadow is False and res.zoom_link == "https://us02web.zoom.us/j/123"
    assert "Here is the Zoom link:\nhttps://us02web.zoom.us/j/123\n\nI will keep it to 15 minutes." in res.draft.body_text
    assert "zoom_not_connected" not in res.problems
    assert ("POST", "/calendars/events/appointments") in seen
    assert ("PUT", "/opportunities/hStqQMLQ5eSRVnqxnSMq") in seen
    assert ("POST", "/api/v2/leads/update-interest-status") in seen


def test_zoom_default_reads_ids_json():
    assert booking.zoom_connected_default() is False  # isZoomAdded=false as of 2026-09-21


# ------------------------------------------------- booking refuses to lie
def test_book_live_without_ghl_token_refuses_to_confirm(live_mode, tmp_env):
    """config/ids.json: there is no Private Integration token, so every GHL write
    returns None. Telling the prospect "Locked in" and stopping the cadence on a
    call that does not exist is how a positive reply is lost."""
    state = cadence.arm(sopio(), NOW)
    ghl = GHL(token=None, transport=raising_transport())
    res = booking.book(state, "2026-09-25T13:00:00-05:00", ghl, None, now=NOW,
                       free_slots=["2026-09-25T13:00:00-05:00"])
    assert booking.APPOINTMENT_NOT_CREATED in res.problems
    assert res.appointment is None
    assert "Locked in" not in res.draft.body_text
    assert state.cadence.get("stopped_reason") != "booked"
    assert state.cadence.get("booking") is None
    assert res.draft.problems, "approval.send_approved must refuse this draft"


def test_book_refuses_a_slot_it_cannot_verify_in_live(live_mode, tmp_env):
    state = cadence.arm(sopio(), NOW)
    ghl = GHL(token=None, transport=raising_transport())
    res = booking.book(state, "2026-09-25T13:00:00-05:00", ghl, None, now=NOW)
    assert booking.SLOT_NOT_VERIFIED in res.problems
    assert res.records == [] and state.cadence.get("booking") is None
    assert read_shadow_log() == []


def test_book_refuses_to_write_over_a_known_booking(tmp_env):
    """Sopio's Discovery Call is at 2026-09-24T15:00 (config/ids.json)."""
    state = cadence.arm(LeadState(lead_email="new@example.com", campaign_id="8086b41e-b546-4b36-9fa0-2d01f5cc119a",
                                  first_name="Dana", company="Acme Cleaning"), NOW)
    res = booking.book(state, "2026-09-24T15:00:00-05:00", None, None, now=NOW)
    assert booking.SLOT_ALREADY_TAKEN in res.problems
    assert "just got taken" in res.draft.body_text
    assert res.records == [] and state.cadence.get("booking") is None
    assert [r for r in read_shadow_log() if r["action"] == "create_appointment"] == []


def test_rebooking_an_already_booked_lead_cancels_the_original(live_mode, tmp_env):
    """Ilmi asks to move her call: exactly one appointment may survive."""
    calls = []

    def ghl_handler(request):
        calls.append((request.method, request.url.path))
        if "free-slots" in request.url.path:
            return httpx.Response(200, json={"2026-09-23": {"slots": ["2026-09-23T12:30:00-05:00"]}})
        return httpx.Response(200, json={"id": "appt-NEW"})

    def inst_handler(request):
        return httpx.Response(200, json={"status": "ok"})

    state = cadence.arm(LeadState(lead_email="ilmi@shiningarmorcleaningnj.com",
                                  campaign_id="8086b41e-b546-4b36-9fa0-2d01f5cc119a", first_name="Ilmi",
                                  company="Shining Armor Cleaning NJ", eaccount="lorenzo@adveromedia.com",
                                  ghl_contact_id="cnfZoGRCRi3JMqZfo0XD", ghl_opportunity_id="HOPG1Hl4vj6REtzjXH8r"), NOW)
    state.cadence["booking"] = {"slot": "2026-09-23T11:30:00-05:00", "appointment_id": "appt-ORIGINAL"}
    ghl = GHL(token="fake-token", transport=httpx.MockTransport(ghl_handler))
    inst = Instantly(api_key="x", transport=httpx.MockTransport(inst_handler))
    res = booking.book(state, "2026-09-23T12:30:00-05:00", ghl, inst, now=NOW)
    assert res.problems == ["zoom_not_connected"]
    assert state.cadence["booking"]["appointment_id"] == "appt-NEW"
    assert state.cadence["booking"]["rescheduled_from"] == "appt-ORIGINAL"
    assert ("PUT", "/calendars/events/appointments/appt-ORIGINAL") in calls
    assert len([c for c in calls if c == ("POST", "/calendars/events/appointments")]) == 1


def test_a_lead_s_own_call_is_not_a_collision_for_that_lead():
    """config/ids.json records Sopio's Discovery Call at 2026-09-24T15:00 CT and
    now carries her email on the block. A DIFFERENT prospect asking for that
    time is still countered; Sopio herself is not protected from her own call."""
    slot = slot_rules.parse_iso("2026-09-24T15:00:00-05:00")
    assert booking.collides_with_known_booking(slot) is True
    assert booking.collides_with_known_booking(slot, exclude_email="sopiosvanishvili@taxfoaccounting.com") is False
    assert booking.collides_with_known_booking(slot, exclude_email="someone@else.com") is True
    # verify_slot follows the same rule, so book() does not refuse her own time
    assert booking.verify_slot(slot, None, NOW)[1] == booking.SLOT_ALREADY_TAKEN
    assert booking.verify_slot(slot, None, NOW, lead_email="sopiosvanishvili@taxfoaccounting.com")[1] == booking.SLOT_NOT_VERIFIED


# ----------------------------------------- regressions found by the A2 review
def test_a_counter_that_crosses_a_week_names_the_date():
    """format_slot has no date, so "Tue 2:00pm is further out than I can lock
    in right now. Could you do Tue 12:00pm instead?" reads as two times on the same
    day, two hours apart. _counter() deliberately prefers a different day, so
    this is the normal shape of a beyond_horizon counter."""
    m = booking.evaluate_reply("next Tuesday at 2pm", [], NOW)
    assert m.status == booking.BEYOND_HORIZON
    body = booking.counter_proposal_text(m, sopio())
    assert m.proposed.isoformat().startswith("2026-09-29")
    # the refused time carries its date, and so do the alternatives
    assert "Sep 29" in body, body
    assert "Sep 22" in body or "Sep 23" in body, body
    assert body.count("Tue ") <= 1 or "Sep" in body
    assert "—" not in body and "!" not in body and body.rstrip().endswith("Lorenzo")
    # a counter inside the same week stays on the short weekday form
    same_week = booking.evaluate_reply("this Wednesday around 11:30 am", [], NOW)
    inside = booking.counter_proposal_text(same_week, sopio())
    assert "Sep" not in inside, inside


def test_booking_the_same_slot_twice_is_a_no_op(live_mode, tmp_env):
    """rescheduled_from is only computed when the slot CHANGED, so an identical
    slot fell through to a second create_appointment: two calls on the calendar,
    nothing cancelled, the first appointment id and its show-rate schedule
    orphaned, and two "Locked in" cards for the prospect."""
    calls = []

    def ghl_handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/calendars/events/appointments":
            return httpx.Response(200, json={"id": "appt-%d" % len([c for c in calls if c[0] == "POST"])})
        return httpx.Response(200, json={"ok": True})

    ghl = GHL(token="fake-token", transport=httpx.MockTransport(ghl_handler))
    inst = Instantly(api_key="x", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok"})))
    state = cadence.arm(sopio(), NOW)
    first = booking.book(state, "2026-09-24T15:00:00-05:00", ghl, inst, now=NOW, free_slots=FREE_THU_3)
    second = booking.book(state, "2026-09-24T15:00:00-05:00", ghl, inst, now=NOW, free_slots=FREE_THU_3)
    posts = [c for c in calls if c == ("POST", "/calendars/events/appointments")]
    assert len(posts) == 1, calls
    assert not [c for c in calls if c[0] == "PUT" and "appointments" in c[1]], calls
    assert state.cadence["booking"]["appointment_id"] == first.appointment.get("id")
    assert second.slot == first.slot
    assert second.draft.body_text == first.draft.body_text
    # a DIFFERENT time is still a reschedule, not a no-op
    third = booking.book(state, "2026-09-25T13:00:00-05:00", ghl, inst, now=NOW, free_slots=FREE_THU_3)
    assert len([c for c in calls if c == ("POST", "/calendars/events/appointments")]) == 2
    assert state.cadence["booking"]["rescheduled_from"] == first.appointment.get("id")
    assert third.slot.isoformat() == "2026-09-25T13:00:00-05:00"


def test_an_unbookable_slot_is_a_card_for_lorenzo_not_a_confirmation(live_mode, tmp_env):
    """With no GHL Private Integration token nothing is written, and the body
    used to read "Thu 3:00pm CT works on my side. I will send the invite
    shortly." - one missing booking link away from sendable, so pasting the link
    in turned a failed write into a confirmation for a call that does not exist."""
    state = cadence.arm(sopio(), NOW)
    res = booking.book(state, "2026-09-24T15:00:00-05:00", None, None, now=NOW, free_slots=None)
    assert booking.SLOT_NOT_VERIFIED in res.problems
    body = res.draft.body_text
    assert "works on my side" not in body and "invite shortly" not in body
    assert "NOT SENT" in body and "nothing was written" in body
    # it is not a reply at all, so it cannot pass the copy gate either
    assert "unsigned" in cadence.copy_problems(body)
    assert booking.NON_COPY_PROBLEMS == (booking.SLOT_NOT_VERIFIED, booking.SLOT_ALREADY_TAKEN,
                                         booking.APPOINTMENT_NOT_CREATED, "zoom_not_connected")
    # the cadence is not stopped on a booking that did not happen
    assert state.cadence.get("stopped_reason") != "booked"


def test_next_weekday_is_never_auto_booked_and_that_is_the_documented_cost():
    """The matching half of shared/tests/test_slots.py::
    test_next_weekday_always_means_the_following_week_and_what_that_costs.

    "next <weekday>" parses to the following week, which is past
    MAX_BUSINESS_DAYS=5, so the most common American phrasing for naming a time
    is answered with a counter-proposal and waits for Lorenzo's waiver button.
    Recorded here so that changing shared/slots.py breaks a test that says why
    it matters, rather than one that only says what the parser returns.
    """
    monday_morning = slot_rules.parse_iso("2026-09-21T10:00:00-05:00")
    for text in ("next Tuesday at 2pm works", "next Thursday at 1pm", "next Wednesday 3pm"):
        m = booking.evaluate_reply(text, [], monday_morning)
        assert m.status == booking.BEYOND_HORIZON, text
        assert m.slot is None and not m.bookable, text
        assert m.counter_slots, "the lead is still answered, just not booked"
    # the same sentence without "next" books
    assert booking.evaluate_reply("Tuesday at 2pm works", [], monday_morning).status == booking.VALID_SLOT
