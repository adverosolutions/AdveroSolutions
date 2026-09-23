"""Copy-fix round Z (piece ZB): the cadence wording Lorenzo approves word for
word. One test per fix: the day-2 fallback line (item 1), day 14 (9), the
outbound free-work lines (10), the comma splices (11 and day 7), days 1 and 3
(15), the no-slot bodies (19), the fallback subject (23) and day 6's
no-invite body. Lead data is made up. No network, no live flags.
"""
import re
import types

import pytest

from services.reply_engine import cadence
from services.reply_engine import template_gate as gate
from services.reply_engine.tests.template_fixtures import template_env  # noqa: F401

TWO = ["2030-01-08T13:00:00-06:00", "2030-01-10T15:30:00-06:00"]
SLOT_DAYS = (1, 2, 3, 4, 5, 14, 30)


def _state(first="Dana", company="Brightline Test Co", niche="cleaning", offer="reactivation",
           subject="Quick question", specialty=None):
    return types.SimpleNamespace(first_name=first, company=company, niche=niche, offer=offer,
                                 campaign_key="%s_%s" % (niche, offer), campaign_id=None, phone=None,
                                 specialty=specialty, website=None, last_subject=subject, subject=None,
                                 thread_subject=None, lead_email="lead@example.invalid", ghl_contact_id=None,
                                 cadence={})


def _body(day, slots=TWO, **kw):
    invite = kw.pop("invite_created", True)
    return cadence.build_touch(_state(**kw), day, list(slots), invite_created=invite).body_text


# ---------------------------------------------------------- item 1 (d2)
@pytest.mark.parametrize("offer", ["reactivation", "outbound"])
def test_d2_fallback_line_is_one_clause_and_says_fifteen_minutes_once(offer):
    line = cadence.fallback_research_line("Brightline Test Co", offer)
    assert line.startswith("The quickest place to start is usually the ")
    assert line.count(",") == 0 and line.endswith(".")
    assert "fifteen" not in line.lower() and "Brightline" not in line
    body = _body(2, offer=offer)
    assert body.lower().count("fifteen minutes") == 1, body
    assert "The quickest place to start is usually" in body


def test_d2_fallback_line_exact_wording():
    assert cadence.fallback_research_line("X", "reactivation") == (
        "The quickest place to start is usually the accounts that already know you and went quiet.")
    assert cadence.fallback_research_line("X", "outbound") == (
        "The quickest place to start is usually the prospects who are in market right now.")


def test_d2_without_a_company_does_not_say_start_with_your_team():
    body = _body(2, first=None, company=None)
    assert "start with your team" not in body and "Hey there," in body


# ---------------------------------------------------------- item 9 (d14)
def test_d14_does_not_promise_the_slots_are_this_week():
    body = _body(14)
    assert "this week" not in body
    assert "Circling back in case the timing is better now. I have Tue 1:00pm or Thu 3:30pm CT open, or grab " \
           "a time here: " in body


# ---------------------------------------------------------- item 10 (d5 outbound)
@pytest.mark.parametrize("niche,specialty", [("cleaning", None), ("bookkeeping", None), ("recruiting", None),
                                             ("recruiting", "ICU nurse")])
def test_d5_outbound_offers_to_pull_a_list_and_never_claims_one_exists(niche, specialty):
    line = cadence.free_work_line(niche, "Brightline Test Co", specialty, offer="outbound")
    assert line.startswith("I can pull the "), line
    assert "I pulled" not in line and not re.search(r"\b15\b", line), line
    assert "near Brightline" not in line
    assert line.endswith(". Want the list?"), line
    if specialty:
        assert "ICU nurse roles" in line


# ---------------------------------------------------------- item 11 and d7 (comma splices)
@pytest.mark.parametrize("niche", ["cleaning", "bookkeeping", "recruiting", "aviation"])
@pytest.mark.parametrize("offer", ["reactivation", "outbound"])
def test_free_work_lines_have_no_comma_splice(niche, offer):
    line = cadence.free_work_line(niche, "Brightline Test Co", None, offer=offer)
    assert not re.search(r", (want|Want) ", line), line
    assert re.search(r"\. Want (to see (them|it)|the list)\?$", line), line


def test_d5_recruiting_reactivation_wording():
    line = cadence.free_work_line("recruiting", "Hire Test Co", None, offer="reactivation")
    assert line == ("I can draft the first two emails for the clients Hire Test Co made one placement for and "
                    "never heard from again. Want to see them?")


def test_d5_walkthrough_line():
    body = _body(5)
    assert "Happy to walk through it together. I have Tue 1:00pm or Thu 3:30pm CT, or grab a time here: " in body
    assert "If you want, I can walk you through it live" not in body


def test_d7_has_no_comma_splice():
    body = cadence.build_touch(_state(), 7, []).body_text
    assert "Either answer is fine. I just want to keep my notes straight." in body


# ---------------------------------------------------------- item 15 (d1, d3)
def test_d1_and_d3_do_not_say_the_times_were_lost():
    d1 = _body(1)
    d3 = _body(3)
    assert "Here are two new times in case the first ones did not suit: Tue 1:00pm or Thu 3:30pm CT." in d1
    assert "A couple more options if those did not work: Tue 1:00pm or Thu 3:30pm CT." in d3
    for body in (d1, d3):
        assert "lost" not in body and "went too" not in body and "I still have" not in body, body


def test_d6_noinvite_does_not_claim_times_opened_up():
    body = _body(6, invite_created=False)
    assert "opened up" not in body and "windows" not in body
    assert "Here are two more times on my side: Tue 1:00pm or Thu 3:30pm CT." in body


# ---------------------------------------------------------- item 19 (no free slot)
@pytest.mark.parametrize("day", SLOT_DAYS + (6,))
def test_no_slot_bodies_read_correctly_and_name_no_open_time(day):
    t = cadence.build_touch(_state(), day, [], invite_created=False)
    body = t.body_text
    assert t.slots == []
    for banned in ("afternoon", "this week", "windows", "{slots}", "two new", "two more", "A couple more",
                   "I have", "open,"):
        assert banned not in body, (day, banned, body)
    assert cadence.DEFAULT_BOOKING_URL in body
    assert body.startswith("Hey Dana,\n\n") and body.rstrip().endswith("Lorenzo")
    assert t.problems == [], (day, t.problems, body)
    # no sentence says the same thing twice (the old "open this week" doubling)
    sentences = [s.strip() for s in re.split(r"(?<=[.?])\s+", body) if s.strip()]
    assert len(sentences) == len(set(sentences)), body


def test_no_slot_body_exact_wording_d14():
    body = _body(14, slots=[])
    assert body == ("Hey Dana,\n\nCircling back in case the timing is better now. Grab any open time here: %s\n\n"
                    "Lorenzo\n" % cadence.DEFAULT_BOOKING_URL)


def test_every_slot_day_has_a_no_slot_body():
    names = set(p.stem[len("cadence_"):] for p in cadence.PROMPTS_DIR.glob("cadence_d*.md"))
    slot_templates = set(n for n in names if "{slots}" in cadence._load_template(n))
    assert slot_templates == set(cadence.NO_SLOTS_BODIES), (slot_templates, set(cadence.NO_SLOTS_BODIES))


def test_d6_one_slot_names_no_afternoon():
    body = _body(6, slots=TWO[:1])
    assert "If another time is better, say the word and I will move it." in body
    assert "afternoon" not in body


@pytest.mark.parametrize("day", SLOT_DAYS)
def test_no_slot_touch_with_no_lead_data_conforms_once_approved(template_env, day):
    """Built through the day's no_slots variant plus the missing-data
    fallbacks, a touch still passes the gate once its ids are approved."""
    t = cadence.build_touch(_state(first=None, company=None), day, [])
    main, parts = cadence.touch_template_ids(day, _state(), research_source="fallback", has_slots=False)
    template_env.approve_ids(main, *parts)
    gate.stamp(t, main, parts)
    v = gate.touch_verdict(t)
    assert v.allowed, (day, v, t.body_text)


# ---------------------------------------------------------- item 23 (subject)
def test_subject_fallback_without_a_first_name_is_your_reply():
    assert cadence.subject_for(_state(first=None, subject=None)) == "Re: your reply"
    assert cadence.subject_for(_state(first="  ", subject=None)) == "Re: your reply"
    assert cadence.subject_for(_state(first="Dana", subject=None)) == "Re: Dana, question"
    assert cadence.subject_for(_state(first=None, subject="Automatic reply: Out of office")) == "Re: your reply"
    assert cadence.subject_for(_state(first=None, subject="Re: Quick question")) == "Re: Quick question"
    t = cadence.build_touch(_state(first=None, subject=None), 1, TWO)
    assert t.subject == "Re: your reply" and "there, question" not in t.subject
