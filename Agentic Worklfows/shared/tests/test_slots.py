import json
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import pytest

from shared import slots
from shared.slots import (
    TZ,
    business_days_ahead,
    candidate_slots,
    format_slot,
    format_slots,
    parse_iso,
    parse_availability_window,
    parse_proposed_time,
    pick_two,
    within_send_window,
)

EASTERN = pytz.timezone("America/New_York")

# Real replies recorded from the live workspace; the parser has to survive them
# verbatim, wrapped attributions, phone numbers and all.
FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "services" / "reply_engine" / "tests" / "fixtures" / "instantly_replies_2026-09.json"
)


def _fixture_reply(email):
    with open(FIXTURES, "r", encoding="utf-8") as fh:
        items = json.load(fh)
    for item in items:
        if (item.get("from_address_email") or item.get("lead_email")) == email:
            body = item.get("body")
            return body.get("text") if isinstance(body, dict) else item.get("text")
    raise AssertionError("no recorded reply from %s" % email)


def ct(y, m, d, hh, mm=0):
    return TZ.localize(datetime(y, m, d, hh, mm))


# "now" for every parse test: Monday 2026-09-21 21:10 CT (offset -05:00)
NOW = ct(2026, 9, 21, 21, 10)


def test_now_fixture_is_monday_with_expected_offset():
    assert NOW.weekday() == 0
    assert NOW.isoformat() == "2026-09-21T21:10:00-05:00"


# --------------------------------------------------------- business days
def test_business_days_ahead_from_monday():
    assert business_days_ahead(NOW, 5).date() == datetime(2026, 9, 28).date()
    assert business_days_ahead(NOW, 0) == NOW
    assert business_days_ahead(NOW, 1).date() == datetime(2026, 9, 22).date()


def test_business_days_ahead_skips_weekend_from_friday():
    fri = ct(2026, 9, 25, 16, 0)
    assert business_days_ahead(fri, 1).date() == datetime(2026, 9, 28).date()   # Monday
    assert business_days_ahead(fri, 5).date() == datetime(2026, 10, 2).date()   # next Friday


def test_business_days_ahead_is_dst_safe_wall_clock():
    fri = ct(2026, 10, 30, 10, 0)  # CDT
    mon = business_days_ahead(fri, 1)
    assert mon.date() == datetime(2026, 11, 2).date()
    assert (mon.hour, mon.minute) == (10, 0)
    assert mon.utcoffset() == timedelta(hours=-6)  # CST after Nov 1 change


# ------------------------------------------------------------ candidates
def test_candidate_slots_excludes_weekends_and_window():
    now = ct(2026, 9, 21, 8, 0)
    free = [
        "2026-09-22T11:45:00-05:00",  # before 12:00
        "2026-09-22T12:00:00-05:00",  # ok
        "2026-09-22T17:45:00-05:00",  # ok (ends 18:00)
        "2026-09-22T18:00:00-05:00",  # ends after 18:00
        "2026-09-26T13:00:00-05:00",  # Saturday
        "2026-09-27T13:00:00-05:00",  # Sunday
    ]
    out = candidate_slots(free, now, set())
    assert [s.isoformat() for s in out] == ["2026-09-22T12:00:00-05:00", "2026-09-22T17:45:00-05:00"]


def test_candidate_slots_four_hour_lead():
    now = ct(2026, 9, 22, 9, 0)
    free = ["2026-09-22T12:30:00-05:00", "2026-09-22T12:59:00-05:00", "2026-09-22T13:00:00-05:00", "2026-09-22T13:15:00-05:00"]
    out = candidate_slots(free, now, set())
    assert [s.strftime("%H:%M") for s in out] == ["13:00", "13:15"]


def test_candidate_slots_max_business_days():
    now = ct(2026, 9, 21, 8, 0)  # Monday -> last allowed date is Monday 9/28
    free = ["2026-09-28T14:00:00-05:00", "2026-09-29T14:00:00-05:00"]
    out = candidate_slots(free, now, set())
    assert [s.date().isoformat() for s in out] == ["2026-09-28"]


def test_candidate_slots_excludes_already_offered_by_string_or_datetime():
    now = ct(2026, 9, 21, 8, 0)
    free = ["2026-09-22T14:00:00-05:00", "2026-09-22T15:00:00-05:00", "2026-09-23T14:00:00-05:00", "2026-09-22T14:00:00-05:00"]
    offered = {"2026-09-22T19:00:00Z", ct(2026, 9, 23, 14, 0)}  # 19:00Z == 14:00 CDT
    out = candidate_slots(free, now, offered)
    assert [s.isoformat() for s in out] == ["2026-09-22T15:00:00-05:00"]  # dedupe + both exclusions


def test_candidate_slots_dst_safe_utc_inputs():
    # CDT: 18:00Z is 13:00 CT
    out = candidate_slots(["2026-10-30T18:00:00Z"], ct(2026, 10, 28, 8, 0), set())
    assert out[0].isoformat() == "2026-10-30T13:00:00-05:00"
    # CST (after Nov 1, 2026): 18:00Z is 12:00 CT and still inside the window
    out = candidate_slots(["2026-11-06T18:00:00Z", "2026-11-06T17:00:00Z"], ct(2026, 11, 2, 8, 0), set())
    assert [s.isoformat() for s in out] == ["2026-11-06T12:00:00-06:00"]


def test_candidate_slots_accepts_naive_and_epoch_ms():
    now = ct(2026, 9, 21, 8, 0)
    epoch_ms = int(ct(2026, 9, 22, 14, 0).timestamp() * 1000)
    out = candidate_slots([datetime(2026, 9, 22, 13, 0), epoch_ms, "garbage"], now, set())
    assert [s.strftime("%m-%d %H:%M") for s in out] == ["09-22 13:00", "09-22 14:00"]


def test_friday_afternoon_rolls_over_to_next_week():
    now = ct(2026, 9, 25, 16, 0)  # Friday 4pm
    free = [
        "2026-09-25T17:00:00-05:00",  # 1h lead: too soon
        "2026-09-26T13:00:00-05:00",  # Saturday
        "2026-09-28T13:00:00-05:00",  # Monday
        "2026-09-30T14:30:00-05:00",  # Wednesday
        "2026-10-05T13:00:00-05:00",  # beyond 5 business days (last allowed Fri 10/2)
    ]
    out = candidate_slots(free, now, set())
    assert [s.isoformat() for s in out] == ["2026-09-28T13:00:00-05:00", "2026-09-30T14:30:00-05:00"]
    assert format_slots(pick_two(out)) == "Mon 1:00pm or Wed 2:30pm CT"


# -------------------------------------------------------------- pick/format
def test_pick_two_prefers_different_days():
    c = [ct(2026, 9, 22, 14, 0), ct(2026, 9, 22, 15, 0), ct(2026, 9, 24, 15, 30)]
    two = pick_two(c)
    assert [s.isoformat() for s in two] == ["2026-09-22T14:00:00-05:00", "2026-09-24T15:30:00-05:00"]
    assert format_slots(two) == "Tue 2:00pm or Thu 3:30pm CT"


def test_pick_two_falls_back_to_different_hours_same_day():
    c = [ct(2026, 9, 22, 14, 0), ct(2026, 9, 22, 14, 15), ct(2026, 9, 22, 16, 0)]
    two = pick_two(c)
    assert [s.strftime("%H:%M") for s in two] == ["14:00", "16:00"]
    assert pick_two(c, spread=False)[1].strftime("%H:%M") == "16:00"


def test_pick_two_edge_cases():
    assert pick_two([]) == []
    one = [ct(2026, 9, 22, 12, 0)]
    assert pick_two(one) == one
    assert format_slots(one) == "Tue 12:00pm CT"
    assert format_slots([]) == ""


def test_format_slots_converts_from_other_tz():
    utc_slot = pytz.utc.localize(datetime(2026, 9, 22, 19, 0))
    assert format_slots([utc_slot]) == "Tue 2:00pm CT"
    assert format_slots([utc_slot], tz=EASTERN) == "Tue 3:00pm ET"


# ------------------------------------------------------------ send window
@pytest.mark.parametrize("hh,mm,expected", [(6, 59, False), (7, 0, True), (12, 0, True), (18, 59, True), (19, 0, False), (23, 30, False)])
def test_within_send_window(hh, mm, expected):
    assert within_send_window(ct(2026, 9, 22, hh, mm)) is expected


def test_within_send_window_converts_utc():
    assert within_send_window(pytz.utc.localize(datetime(2026, 9, 22, 11, 30))) is False  # 06:30 CT
    assert within_send_window(pytz.utc.localize(datetime(2026, 9, 22, 12, 0))) is True    # 07:00 CT
    assert within_send_window(datetime(2026, 9, 22, 10, 0)) is True  # naive => CT


# ---------------------------------------------------------- parse: examples
def test_parse_thursday_4pm_eastern():
    text = "Hello,\n\nThursday 4pm Eastern time. works for me 237-791-5700\n\nOn 21.09.2026 10:59, Lorenzo Villarreal wrote:\n> Hey Sopio,"
    out = parse_proposed_time(text, NOW)
    assert out.isoformat() == "2026-09-24T15:00:00-05:00"


def test_parse_monday_at_2_cts():
    text = "Sure Let’s get together on Monday  at 2 CTS that works for me .\n\nBest reagrds ;\nIlmi Curovic\n\nSent from my iPhone"
    out = parse_proposed_time(text, NOW)
    # it is Monday 21:10 already, so "Monday at 2" is next Monday
    assert out.isoformat() == "2026-09-28T14:00:00-05:00"


def test_parse_this_wednesday_around_1130am():
    text = "Hi Lorenzo,\n\nI have an one emergence please reschedule for this Wednesday around 11:30 am\n\nSent from my iPhone\n\n> On Sep 18, 2026, at 1:29 PM, Lorenzo wrote:"
    out = parse_proposed_time(text, NOW)
    assert out.isoformat() == "2026-09-23T11:30:00-05:00"


def test_parse_friday_afternoon_2pm_est():
    text = "Hi Lorenzo,\n\nI have a better idea…let’s chat Friday. Afternoon. How’s 2pm EST?\n\n[https://lh5.googleusercontent.com/x]"
    out = parse_proposed_time(text, NOW)
    assert out.isoformat() == "2026-09-25T13:00:00-05:00"


def test_parse_every_day_range_returns_none_but_window():
    text = ("Hello Lorenzo.\n\nI am available every day 3pm-6pm Estern time.\n\nlet me know what wirks.\n\n"
            "On 21.09.2026 14:30, Lorenzo Villarreal wrote:\n\n> Got a cal invite and zoom link sent over!\n"
            "> > On Monday, Sep 21, 2026 at 12:37 pm > sopio wrote:\n> > Thursday 4pm Eastern time. works for me")
    assert parse_proposed_time(text, NOW) is None
    start, end, tz = parse_availability_window(text)
    assert (start, end) == (15, 18)
    assert tz.zone == "America/New_York"


def test_parse_availability_window_variants():
    assert parse_availability_window("anytime 1-3pm central") == (13, 15, TZ)
    assert parse_availability_window("between 10am and 2pm") is None  # "and" is not a range marker we accept
    assert parse_availability_window("9am to 11am ET")[:2] == (9, 11)
    assert parse_availability_window("call me at 237-791-5700") is None
    assert parse_availability_window("Thursday 4pm Eastern time") is None


# ------------------------------------------------------------ parse: rules
def test_parse_ignores_quoted_history():
    text = "Sounds good, talk soon.\n\nOn Mon, Sep 21, 2026 Lorenzo wrote:\n> Would Thursday 4pm Eastern work?"
    assert parse_proposed_time(text, NOW) is None


def test_parse_same_weekday_later_today():
    now = ct(2026, 9, 21, 9, 0)  # Monday morning
    assert parse_proposed_time("Monday at 2 works", now).isoformat() == "2026-09-21T14:00:00-05:00"


def test_parse_tomorrow_and_today():
    assert parse_proposed_time("tomorrow at 3 is fine", NOW).isoformat() == "2026-09-22T15:00:00-05:00"
    assert parse_proposed_time("today at 10pm", NOW).isoformat() == "2026-09-21T22:00:00-05:00"


def test_parse_requires_day_and_time():
    assert parse_proposed_time("Friday afternoon works", NOW) is None
    assert parse_proposed_time("how about 3pm?", NOW) is None
    assert parse_proposed_time("call me 237-791-5700", NOW) is None
    assert parse_proposed_time("", NOW) is None


def test_parse_across_dst_change_eastern_to_central():
    now = ct(2026, 10, 30, 9, 0)  # Friday before the Nov 1 change
    out = parse_proposed_time("Monday 4pm Eastern", now)
    assert out.isoformat() == "2026-11-02T15:00:00-06:00"


def test_parse_noon_and_pacific():
    out = parse_proposed_time("Wednesday at noon Pacific", NOW)
    assert out.isoformat() == "2026-09-23T14:00:00-05:00"


# ------------------------------------------------- parse: quoted history
def test_strip_quoted_returns_empty_when_nothing_is_above_the_quote():
    """A bottom-posted reply: the whole top of the message is Lorenzo's own
    offer. Falling back to the raw text makes the engine read his times as the
    lead's proposal and book a call the lead just refused."""
    text = ("> Would Tue 2:00pm or Thu 3:30pm CT work for a 15 minute call?\n"
            "> Lorenzo\n\nNeither works, I am out all week.")
    assert slots.strip_quoted(text) == ""
    assert parse_proposed_time(text, NOW) is None
    assert parse_availability_window(text) is None


def test_strip_quoted_returns_empty_for_an_outlook_header_first_line():
    text = "From: Lorenzo Villarreal <lorenzo@theadvero.com>\nSent: Monday\nWould Thursday 4pm work?"
    assert slots.strip_quoted(text) == ""
    assert parse_proposed_time(text, NOW) is None


def test_strip_quoted_handles_gmail_wrapped_attribution():
    """Gmail wraps a long attribution over two lines, so neither line matches
    the single-line 'On ... wrote:' form and Lorenzo's own send timestamp is
    read back as the lead's proposed time. Reply #32 verbatim."""
    reply = _fixture_reply("maggie@northwestsnowremoval.com")
    assert "Please do not contact us again" in reply
    assert parse_proposed_time(reply, NOW) is None
    top = slots.strip_quoted(reply)
    assert "Please do not contact us again" in top
    assert "lorenzovillarreal@proadvero.com" not in top
    assert "commercial cleaning" not in top  # none of the quoted cold email survives


def test_strip_quoted_handles_zoho_style_dashed_attribution():
    reply = _fixture_reply("ignacio@ariacleaningservices.com")
    top = slots.strip_quoted(reply)
    assert "Let’s touch base next month" in top
    assert "outbound system" not in top  # the quoted cold email is gone


# ------------------------------------------------------- parse: phone numbers
@pytest.mark.parametrize("email", ["vania@abscomm.com", "sgrieco@sg2recruiting.com"])
def test_phone_number_after_at_is_not_a_time(email):
    """'contact Barbara at 1-800-311-6441' parsed as 'at 1' -> 13:00, so a pure
    out-of-office auto-responder produced a confident proposed time."""
    assert parse_proposed_time(_fixture_reply(email), NOW) is None


@pytest.mark.parametrize("text", [
    "Please call Barbara at 1-800-311-6441. I return Monday.",
    "Text me at 703.675.6286 on Tuesday",
    "reach us at (214) 686-7999 Thursday",
    "call me 237-791-5700",
])
def test_phone_shaped_runs_never_supply_an_hour(text):
    assert parse_proposed_time(text, NOW) is None


def test_a_real_time_still_parses_next_to_a_phone_number():
    text = "Thursday 4pm Eastern time. works for me 237-791-5700"
    assert parse_proposed_time(text, NOW).isoformat() == "2026-09-24T15:00:00-05:00"


# ------------------------------------------------------------ parse: "next"
def test_next_weekday_means_the_following_week():
    monday = ct(2026, 9, 21, 9, 0)
    assert parse_proposed_time("next Tuesday at 2pm", monday).isoformat() == "2026-09-29T14:00:00-05:00"
    assert parse_proposed_time("Tuesday at 2pm", monday).isoformat() == "2026-09-22T14:00:00-05:00"
    assert parse_proposed_time("next Friday at 3pm", monday).isoformat() == "2026-10-02T15:00:00-05:00"
    assert parse_proposed_time("this Friday at 3pm", monday).isoformat() == "2026-09-25T15:00:00-05:00"
    # "next Monday" said on a Monday is still a week out
    assert parse_proposed_time("next Monday at 2pm", monday).isoformat() == "2026-09-28T14:00:00-05:00"


# --------------------------------------------------- parse: fractional seconds
def test_parse_iso_normalises_every_fractional_second_length():
    for value, expected in (
        ("2026-09-22T15:00:00.12345-05:00", "2026-09-22T15:00:00.123450-05:00"),
        ("2026-09-22T15:00:00.1234-05:00", "2026-09-22T15:00:00.123400-05:00"),
        ("2026-09-22T15:00:00.123-05:00", "2026-09-22T15:00:00.123000-05:00"),
        ("2026-09-22T15:00:00.123456789-05:00", "2026-09-22T15:00:00.123456-05:00"),
    ):
        assert slots.parse_iso(value).isoformat() == expected


def test_candidate_slots_keeps_slots_with_odd_fractional_seconds():
    now = ct(2026, 9, 22, 8, 0)
    free = ["2026-09-22T14:00:00-05:00", "2026-09-22T15:00:00.12345-05:00",
            "2026-09-22T16:00:00.123456789-05:00", "2026-09-22 17:00:00"]
    assert [s.strftime("%H:%M") for s in candidate_slots(free, now, set())] == ["14:00", "15:00", "16:00", "17:00"]


def test_unreadable_already_offered_entries_are_logged(caplog):
    now = ct(2026, 9, 22, 8, 0)
    with caplog.at_level("WARNING"):
        out = candidate_slots(["2026-09-22T14:00:00-05:00"], now, [None, "not a date", {}])
    assert [s.strftime("%H:%M") for s in out] == ["14:00"]
    assert "unreadable" in caplog.text
    assert "double-offer protection is incomplete" in caplog.text


# ------------------------------------------------------- send time / offerable
def test_within_send_window_is_hour_only_and_is_send_time_rejects_weekends():
    """within_send_window() is the hour check the approval queue uses (an
    approved reply may still go out on a Saturday); is_send_time() is the full
    gate anything that auto-sends must use, per Blueprint S2 'skip weekends'."""
    sat, sun = ct(2026, 9, 26, 10, 0), ct(2026, 9, 27, 10, 0)
    assert within_send_window(sat) is True and within_send_window(sun) is True
    assert slots.is_send_time(sat) is False and slots.is_send_time(sun) is False
    assert slots.is_send_time(ct(2026, 9, 22, 10, 0)) is True   # Tuesday 10:00
    assert slots.is_send_time(ct(2026, 9, 22, 6, 30)) is False  # too early
    assert slots.is_send_time(ct(2026, 9, 22, 19, 0)) is False  # too late


def test_proposed_time_outside_the_slot_window_is_not_offerable():
    """Ilmi's real reply parses to 11:30, which breaks the no-mornings rule;
    the parser and SLOT_WINDOW were only connected by convention."""
    text = ("Hi Lorenzo,\n\nI have an one emergence please reschedule for this Wednesday "
            "around 11:30 am\n\nSent from my iPhone")
    now = ct(2026, 9, 21, 19, 0)
    parsed = parse_proposed_time(text, now)
    assert parsed.isoformat() == "2026-09-23T11:30:00-05:00"
    assert candidate_slots([parsed], now, set()) == []
    assert slots.is_offerable(parsed, now) is False
    # the same day at 14:00 is offerable
    assert slots.is_offerable(ct(2026, 9, 23, 14, 0), now) is True


def test_is_offerable_respects_already_offered_and_the_five_day_horizon():
    now = ct(2026, 9, 21, 8, 0)
    slot = ct(2026, 9, 22, 14, 0)
    assert slots.is_offerable(slot, now) is True
    assert slots.is_offerable(slot, now, already_offered=[slot.isoformat()]) is False
    assert slots.is_offerable(ct(2026, 9, 29, 14, 0), now) is False  # beyond 5 business days
    assert slots.is_offerable(ct(2026, 9, 26, 14, 0), now) is False  # Saturday


def test_detect_tz_aliases():
    assert slots.detect_tz("2 CTS") is TZ
    assert slots.detect_tz("4pm Estern time").zone == "America/New_York"
    assert slots.detect_tz("10 MST").zone == "America/Denver"
    assert slots.detect_tz("nothing here") is None


def test_business_days_ahead_is_dst_safe_for_a_parse_iso_value():
    """parse_iso returns a FIXED-offset tzinfo. Re-attaching it kept -05:00
    across 2026-11-01, so the end bound of the GHL free-slots query
    (services/reply_engine/draft.py) and the router's task due date were an
    hour early for the whole of November."""
    start = parse_iso("2026-10-29T14:00:00-05:00")
    out = business_days_ahead(start, 5)
    assert out.isoformat() == "2026-11-05T14:00:00-06:00"
    assert out.strftime("%H:%M") == "14:00"      # wall clock preserved


def test_a_quantity_after_a_cue_word_is_not_a_time():
    """'about 4 crews' used to parse as 16:00 and 'at 3 locations' as 15:00, so
    an auto-responder or a chatty human reply produced a concrete proposed time
    and the engine offered to book it."""
    now = TZ.localize(datetime(2026, 9, 21, 15, 30))        # Monday
    assert parse_proposed_time("We have about 4 crews right now. Thursday?", now) is None
    assert parse_proposed_time("I am at 3 locations on Thursday", now) is None
    # a real proposal still parses
    assert parse_proposed_time("Thursday at 3 works for me", now).isoformat() == "2026-09-24T15:00:00-05:00"
    assert parse_proposed_time("How about Thursday at 2?", now).isoformat() == "2026-09-24T14:00:00-05:00"
    assert parse_proposed_time("Tuesday at 2 CT", now).isoformat() == "2026-09-22T14:00:00-05:00"


def test_format_slot_always_carries_am_pm():
    """'Thu 5:00' reads as 5am to a prospect; every counter-proposal and every
    cadence touch is built from this."""
    assert format_slot(TZ.localize(datetime(2026, 9, 24, 17, 0))) == "Thu 5:00pm"
    assert format_slot(TZ.localize(datetime(2026, 9, 23, 11, 30))) == "Wed 11:30am"
    assert format_slot(TZ.localize(datetime(2026, 9, 23, 12, 0))) == "Wed 12:00pm"


# --------------------------------------------- what "next Tuesday" costs
def test_next_weekday_always_means_the_following_week_and_what_that_costs():
    """Pinned, with the price written down.

    ``next <weekday>`` adds seven days whatever the delta, so on a Monday
    "next Tuesday" is eight days out, not tomorrow. Combined with
    MAX_BUSINESS_DAYS=5 that puts the single most common American phrasing for
    proposing a time OUTSIDE the bookable horizon: the lead who said yes is
    answered with a counter-proposal instead of a booking, and has to wait for
    Lorenzo to tap "Book as asked".

    Two components disagreed about this reading (DECISIONS F4). The library's
    answer is the one pinned here; changing it is Lorenzo's call, not a
    refactor, and the matching cost is pinned in
    services/reply_engine/tests/test_cadence_booking.py.
    """
    monday = slots.to_tz(slots.parse_iso("2026-09-21T10:00:00-05:00"))
    eight_days_out = slots.parse_proposed_time("next Tuesday at 2pm", monday)
    assert eight_days_out.isoformat() == "2026-09-29T14:00:00-05:00"
    assert not slots.is_offerable(eight_days_out, monday), "beyond MAX_BUSINESS_DAYS=5"
    # the same words without "next" book normally
    tomorrow = slots.parse_proposed_time("Tuesday at 2pm", monday)
    assert tomorrow.isoformat() == "2026-09-22T14:00:00-05:00"
    assert slots.is_offerable(tomorrow, monday)
