"""Copy-fix round Z (piece ZB), carried over to the ten-email ladder agreed on
2026-09-23: the E2 fallback line (item 1), the fallback subject (item 23), no
sentence said twice, and a touch with no first name that still passes the
gate. The old day 1/3/5/6/7/14/30 wording and the no-slot bodies are gone with
the old ladder (test_cadence_ladder_e1_e10.py pins the new text). Lead data
is made up. No network, no live flags.
"""
import re
import types

import pytest

from services.reply_engine import cadence
from services.reply_engine import template_gate as gate
from services.reply_engine.tests.template_fixtures import template_env  # noqa: F401

TWO = ["2030-01-08T13:00:00-06:00", "2030-01-10T15:30:00-06:00"]
SLOT_DAYS = (1, 3, 4, 5, 6, 7, 8, 9, 10)


def _state(first="Dana", company="Brightline Test Co", niche="cleaning", offer="reactivation",
           subject="Quick question", specialty=None):
    return types.SimpleNamespace(first_name=first, company=company, niche=niche, offer=offer,
                                 campaign_key="%s_%s" % (niche, offer), campaign_id=None, phone=None,
                                 specialty=specialty, website=None, last_subject=subject, subject=None,
                                 thread_subject=None, lead_email="lead@example.invalid", ghl_contact_id=None,
                                 cadence={})


def _body(day, slots=TWO, **kw):
    return cadence.build_touch(_state(**kw), day, list(slots)).body_text


# ---------------------------------------------------------- item 1 (E2)
@pytest.mark.parametrize("offer", ["reactivation", "outbound"])
def test_e2_fallback_line_is_one_clause_and_says_fifteen_minutes_once(offer):
    line = cadence.fallback_research_line("Brightline Test Co", offer)
    assert line.startswith("The quickest place to start is usually the ")
    assert line.count(",") == 0 and line.endswith(".")
    assert "fifteen" not in line.lower() and "Brightline" not in line
    body = _body(2, offer=offer)
    assert body.lower().count("fifteen minutes") == 1, body
    assert "The quickest place to start is usually" in body


def test_e2_fallback_line_exact_wording():
    assert cadence.fallback_research_line("X", "reactivation") == (
        "The quickest place to start is usually the accounts that already know you and went quiet.")
    assert cadence.fallback_research_line("X", "outbound") == (
        "The quickest place to start is usually the prospects who are in market right now.")


def test_e2_without_a_company_does_not_say_your_team():
    """No company on file: the {company} is left unfilled for the copy check to
    refuse (the tick holds the email before it builds it), never "your team"."""
    t = cadence.build_touch(_state(first=None, company=None), 2, list(TWO))
    assert "your team" not in t.body_text and "Hey there," in t.body_text
    assert "unfilled_placeholder" in t.problems


# ---------------------------------------------------------- no sentence said twice
@pytest.mark.parametrize("day", list(range(1, 11)))
@pytest.mark.parametrize("niche,offer", [("cleaning", "reactivation"), ("bookkeeping", "outbound"),
                                         ("recruiting", "reactivation")])
def test_no_email_says_the_same_sentence_twice(day, niche, offer):
    t = cadence.build_touch(_state(niche=niche, offer=offer), day, list(TWO))
    body = t.body_text
    assert body.startswith("Hey Dana,\n\n") and body.rstrip().endswith("Lorenzo")
    assert t.problems == [], (day, t.problems, body)
    sentences = [s.strip() for s in re.split(r"(?<=[.?])\s+", body) if s.strip()]
    assert len(sentences) == len(set(sentences)), body


@pytest.mark.parametrize("day", SLOT_DAYS)
def test_every_email_that_offers_times_says_the_earlier_ones_are_gone(day):
    """Rule 2 (sequence_final.md): an email offering new times after unbooked
    ones says the earlier ones got taken. E1 says it as "got filled", E5 as
    "the slots keep getting filled"."""
    body = _body(day)
    said = ("got filled", "got taken", "got booked", "are gone", "went too", "long gone", "keep getting filled")
    assert any(w in body for w in said), (day, body)


@pytest.mark.parametrize("day", list(range(1, 11)))
def test_a_touch_with_no_first_name_conforms_once_approved(template_env, day):
    """Built with the "there" fallback, a touch still passes the gate once its
    ids are approved (the missing_lead_data variant)."""
    state = _state(first=None)
    t = cadence.build_touch(state, day, list(TWO))
    main, parts = cadence.touch_template_ids(day, state, research_source="fallback")
    template_env.approve_ids(main, *parts)
    gate.stamp(t, main, parts)
    v = gate.touch_verdict(t)
    assert v.allowed, (day, v.reason, t.body_text)


# ---------------------------------------------------------- item 23 (subject)
def test_subject_fallback_without_a_first_name_is_your_reply():
    assert cadence.subject_for(_state(first=None, subject=None)) == "Re: your reply"
    assert cadence.subject_for(_state(first="  ", subject=None)) == "Re: your reply"
    assert cadence.subject_for(_state(first="Dana", subject=None)) == "Re: Dana, question"
    assert cadence.subject_for(_state(first=None, subject="Automatic reply: Out of office")) == "Re: your reply"
    assert cadence.subject_for(_state(first=None, subject="Re: Quick question")) == "Re: Quick question"
    t = cadence.build_touch(_state(first=None, subject=None), 1, TWO)
    assert t.subject == "Re: your reply" and "there, question" not in t.subject
