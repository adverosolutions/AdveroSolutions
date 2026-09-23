"""services/metrics/render.py: the DAILY UPDATE block and the copy rules."""
from datetime import date

import pytest

from services.metrics import render

DAY = date(2026, 9, 22)


def block(today=None, totals=None, prior=None, **kw):
    return render.render_daily_update(DAY, today or {}, totals or {}, prior or {}, **kw)


def test_header_carries_the_date_day_number_and_streak():
    text = block(day_number=5, streak=1)
    assert text.splitlines()[0] == "\U0001F4CA DAILY UPDATE  |  Tue, Sep 22, 2026  |  Day 5  |  \U0001F525 1 day streak"


def test_every_section_prints_even_at_zero():
    text = block()
    for heading in ("UPWORK", "EMAIL", "DMs", "COMMUNITY", "PIPELINE", "REVENUE"):
        assert heading in text


def test_an_unmeasured_number_is_na_never_zero():
    text = block({"Cold Emails Sent": 300})
    assert "300 sent" in text
    assert "Open n/a" in text          # open tracking is off, so there is no view rate
    assert "n/a proposals sent" in text
    assert "0 proposals sent" not in text


def test_growth_suffix_only_when_the_day_moved_the_total():
    moved = block({"Cold Emails Sent": 300}, {"Cold Emails Sent": 1800}, {"Cold Emails Sent": 1500})
    assert "(+20.0%)" in moved
    flat = block({}, {"Upwork Proposals": 20}, {"Upwork Proposals": 20})
    assert "(+0.0%)" not in flat


def test_connect_spend_uses_the_tracker_rate():
    text = block({"Connects Spent": 100}, {"Connects Spent": 1000})
    assert "100 connects ($15.00)" in text
    assert "$150.00 all-time" in text


def test_rates_render_as_percentages():
    text = block({"Email Reply Rate": 0.0106, "Upwork View Rate": 0.5})
    assert "Reply 1.1%" in text and "View rate 50.0%" in text


def test_all_time_totals_are_labelled_as_logged_days_after_a_gap():
    """The totals are summed from the rows present in the Daily Log, and the
    last logged day is 2026-08-12. "300 sent, 300 total" on a week that really
    sent 1,800 is a claim about Lorenzo's whole history, made in public under
    his name."""
    text = block({"Cold Emails Sent": 300}, {"Cold Emails Sent": 300, "Closes": 2},
                 totals_are_partial=True)
    assert "300 sent  →  300 logged to date" in text
    assert "total" not in text.split("EMAIL")[1].split("DMs")[0]
    assert "clients logged to date" in text
    honest = block({"Cold Emails Sent": 300}, {"Cold Emails Sent": 1800})
    assert "300 sent  →  1,800 total" in honest


def test_the_gap_note_rides_along_with_the_post():
    text = block({"Cold Emails Sent": 300}, {"Cold Emails Sent": 300},
                 totals_are_partial=True,
                 note="Totals below count the 5 days logged in the tracker.")
    assert "days logged in the tracker" in text
    assert render.copy_violations(text) == []


def test_the_block_is_signed_lorenzo():
    assert block().rstrip().endswith("Lorenzo")
    assert block(signature=None).rstrip().endswith("active clients")


def test_note_is_optional_and_prefixed():
    assert "\U0001F4DD hit 300 sends" in block(note="hit 300 sends")
    assert "\U0001F4DD" not in block()


def test_copy_rules_hold_for_the_rendered_block():
    text = block({"Cold Emails Sent": 300, "Calls Booked": 2}, {"Cold Emails Sent": 1800},
                 {"Cold Emails Sent": 1500}, day_number=5, streak=1, note="two calls booked")
    assert render.copy_violations(text) == []


def test_copy_violations_catches_what_the_rules_forbid():
    assert "em dash" in render.copy_violations("we shipped — finally")
    assert "exclamation mark" in render.copy_violations("we shipped!")
    assert any("automation" in v for v in render.copy_violations("built with automation"))
    assert any("ai" in v for v in render.copy_violations("an AI wrote this"))


def test_formatters_pass_none_through():
    assert render.fmt_int(None) == "n/a"
    assert render.fmt_money(None) == "n/a"
    assert render.fmt_pct(None) == "n/a"
    assert render.fmt_pct(0.0106) == "1.1%"
    assert render.fmt_money(1234.5) == "$1,234" and render.fmt_money(1.5, cents=True) == "$1.50"
