"""CT3 phase 1, review rounds 2 and 3: what may fill a placeholder, booking
classification, the confirmed-time variant, and fail-closed paths.

Each "reviewer case" test is one of the texts the phase-1 review got through
the gate; each must now be refused. The positive tests show real names,
company names and every time format the engine writes still pass. The round-3
section covers bound links, lead zones outside the main US ones, the company
and name rules, the fallback wordings and the cost of crafted time values.
Lead data is made up. No network, no live flags.
"""
import json
import re
import sys
import time
import types
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import pytest
import pytz
from pydantic import Field

from shared import notify, settings
from shared import slots as slot_rules
from shared.store import JsonFileStore

from services.reply_engine import booking, cadence, draft, models, no_show, show_rate
from services.reply_engine import template_approvals as ta
from services.reply_engine import template_gate as gate
from services.reply_engine.tests import template_fixtures as tf

FIRST = "Jordan"
COMPANY = "Brightline Test Co"
LINK = "https://example.invalid/book"
ZOOM = "https://example.invalid/zoom"
OFFER = "cleaning_reactivation"
NOW = ta._ct(2030, 1, 7, 9, 0)
START = ta._ct(2030, 1, 8, 13, 0)
TWO = [ta._ct(2030, 1, 8, 13, 0), ta._ct(2030, 1, 10, 15, 30)]
FALLBACK = models.Classification(label="neutral_question", confidence=0.0, method="fallback",
                                 reason="LLM unavailable")
SEPARATORS = ("\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}", "\x85", "\x0b", "\x0c")


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    alerts = []

    def fake_notify(title, message, priority="default", **kw):
        alerts.append((title, message))
        return {"sent": False, "test": True}
    monkeypatch.setattr(notify, "notify", fake_notify)
    monkeypatch.setattr(settings, "BOOKING_URL", LINK)
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us", "example.invalid"))
    # GHL links are pinned to our calendar ids: the made-up test calendar is
    # "ours" through a tmp ids file (the real config/ids.json is never written).
    ids = tmp_path / "ids.json"
    ids.write_text(json.dumps({"ghl": {"calendars": {"test_call": {"id": "TestCalendar01"}}}}))
    monkeypatch.setattr(gate, "CALENDAR_IDS_PATH", ids)
    gate.clear_cache()
    e = tf.make_template_env(monkeypatch, tmp_path)
    e.alerts = alerts
    yield e
    gate.clear_cache()


class GDraft(models.Draft):
    template_id: Optional[str] = None
    template_hash: Optional[str] = None
    template_parts: Dict[str, Optional[str]] = Field(default_factory=dict)


def _cls(label="positive_interested", confidence=0.95, method="llm", **extracted):
    return models.Classification(label=label, confidence=confidence, method=method,
                                 extracted=models.Extracted(**extracted))


def _state(first=FIRST, company=COMPANY, niche="cleaning", offer="reactivation"):
    return types.SimpleNamespace(first_name=first, company=company, niche=niche, offer=offer,
                                 campaign_key="%s_%s" % (niche, offer), campaign_id=None, phone=None, specialty=None,
                                 website=None, last_subject="Quick question", subject=None, thread_subject=None,
                                 lead_email="lead@example.invalid", ghl_contact_id=None, cadence={})


def _first_reply(env, first=FIRST, company=COMPANY, cls=None, branch="default"):
    cls = cls or _cls()
    ev = models.ReplyEvent(email_id="t1", lead_email="lead@example.invalid", campaign_key=OFFER, first_name=first,
                           company=company, subject="Quick question", text="", received_at=NOW)
    d = draft.build_draft(ev, cls, now=NOW, booking_link=LINK, use_llm=False, already_offered=[], busy_blocks=[])
    g = GDraft(**d.model_dump())
    tid = "first_reply.%s.%s.full" % (OFFER, branch)
    env.approve_ids(tid)
    gate.stamp(g, tid)
    return g, ev, cls


def _fr_verdict(g, ev, cls, bindings=None):
    return gate.draft_verdict(g, kind="first_reply", campaign_key=OFFER, allow_terms=draft.lead_terms(ev),
                              classification=cls, bindings=bindings)


def _cadence(env, day, company=COMPANY, first=FIRST, slots_=None):
    """Cadence email E<day>, rendered, stamped and approved with the line spliced into it."""
    state = _state(first=first, company=company)
    tid, parts = cadence.touch_template_ids(day, state)
    env.approve_ids(tid, *parts)
    t = cadence.build_touch(state, day, [s.isoformat() for s in (TWO if slots_ is None else slots_)])
    gate.stamp(t, tid, parts)
    return t


def _sr(env, key, first=FIRST, company=COMPANY, **extra):
    appt = dict({"niche": "cleaning", "offer": "reactivation", "booking_url": LINK, "id": "a1", "zoom_link": ZOOM,
                 "first_name": first, "company": company}, **extra)
    copy = show_rate.render(key, appt, START, NOW)
    t = show_rate.Touch(key="a1:x:%s" % key, appointment_id="a1", contact_id=None, when_iso=NOW.isoformat(),
                        channel="sms" if key.endswith("_sms") else "email", template_key=key, body=copy["body"],
                        subject=copy.get("subject"))
    tid = gate.resolve_combo_id("show_rate", key, "cleaning", "reactivation")
    gate.stamp(t, tid)
    env.approve_ids(tid)
    return t


def _refused(v, reason="nonconforming"):
    return (v.allowed, v.reason) == (False, reason)


# ============================================================ reviewer cases
def test_case_first_name_carrying_a_sentence(env):
    g, ev, cls = _first_reply(env, first="Jordan, our records show an unpaid invoice on your account, call 555 "
                                          "0100 today")
    v = _fr_verdict(g, ev, cls)
    assert _refused(v), (v.reason, v.detail)


def test_case_display_name_fallback_token_with_braille_blank(env):
    item = {"id": "e1", "campaign_id": None, "lead": "lead@example.invalid",
            "from_address_email": "lead@example.invalid",
            "from_address_name": "Jordan\N{BRAILLE PATTERN BLANK}your\N{BRAILLE PATTERN BLANK}account\N{BRAILLE PATTERN BLANK}is\N{BRAILLE PATTERN BLANK}locked,\N{BRAILLE PATTERN BLANK}reset\N{BRAILLE PATTERN BLANK}at\N{BRAILLE PATTERN BLANK}"
                                 "evil.example Smith",
            "subject": "Re: hello", "body": {"text": "Yes interested, what's next?"},
            "timestamp_created": NOW.isoformat()}
    ev = models.ReplyEvent.from_poller_item(item, lead={})
    assert "\N{BRAILLE PATTERN BLANK}" in ev.first_name
    g, ev2, cls = _first_reply(env, first=ev.first_name)
    assert _refused(_fr_verdict(g, ev2, cls))


def test_case_text_after_the_booking_link(env):
    # first replies carry no booking link (2026-09-23): text or a link glued
    # after the slot question is refused the same way
    g, ev, cls = _first_reply(env)
    ask = "work for a 15-minute call?"
    assert ask in g.body_text and LINK not in g.body_text
    body = g.body_text.replace(ask, ask + " or text 555 0100 and we skip the call entirely", 1)
    assert body != g.body_text
    assert _refused(_fr_verdict(g.model_copy(update={"body_text": body}), ev, cls))
    glued = g.body_text.replace(ask, ask + " " + LINK + "?ref=evil.example", 1)
    assert _refused(_fr_verdict(g.model_copy(update={"body_text": glued}), ev, cls))


def test_case_slots_placeholder_with_arbitrary_text(env):
    g, ev, cls = _first_reply(env)
    m = re.search(r"Would (.+?) work for a 15-minute call\?", g.body_text)
    assert m
    for fake in ("Saturday at midnight, or any time you like, we also do free audits",
                 "Tue 1:00pm or Thu 3:30pm ET", "Tue 25:00pm or Thu 3:30pm CT", "Tue 1:00pm or Thu 3:30pm"):
        body = g.body_text.replace(m.group(1), fake, 1)
        assert _refused(_fr_verdict(g.model_copy(update={"body_text": body}), ev, cls)), fake


def test_case_show_rate_first_name_from_the_booking_form(env):
    first = "Jordan. Your parcel is held, pay the release fee at parcel-help.example today"
    t = _sr(env, "reminder_1h_email", first=first)
    assert _refused(gate.appointment_touch_verdict(t, kind="show_rate", allow_terms=[first, COMPANY]))
    assert not gate.appointment_touch_verdict(t, kind="show_rate").allowed


def test_case_cadence_company_carrying_a_sentence(env):
    company = "Brightline. PS: reply with your card number to keep your discount"
    t = _cadence(env, 4, company=company)
    assert "card number" in t.body_text
    assert _refused(gate.touch_verdict(t))
    # E1 never renders {company}, so the same record changes nothing there
    t1 = _cadence(env, 1, company=company)
    assert "card number" not in t1.body_text + t1.subject
    assert gate.touch_verdict(t1).allowed


def test_case_referral_first_name_not_bound_to_referral_name(env):
    cls = _cls(label="positive_referral", referral_name="Dana Smith")
    g, ev, _ = _first_reply(env, cls=cls, branch="referral")
    assert _fr_verdict(g, ev, cls).allowed
    body = g.body_text.replace("looping Dana in", "looping whoever handles your bank details in").replace(
        "work for Dana?", "work for whoever handles your bank details?")
    assert body != g.body_text
    assert _refused(_fr_verdict(g.model_copy(update={"body_text": body}), ev, cls))
    other = g.body_text.replace("looping Dana in", "looping Casey in").replace("work for Dana?", "work for Casey?")
    assert other != g.body_text
    assert _refused(_fr_verdict(g.model_copy(update={"body_text": other}), ev, cls))


def test_case_referral_to_a_role_renders_an_article(env):
    # CT3 phase 2: draft.referral_person no longer takes a role phrase for a
    # name, so "looping The in" is never rendered. The draft falls back to the
    # no-name wording Lorenzo approves with the referral template ("the right
    # person" ... "looping them in"), which carries no lead-typed words.
    cls = _cls(label="positive_referral", referral_name="The Manager")
    g, ev, _ = _first_reply(env, cls=cls, branch="referral")
    assert "looping The in" not in g.body_text
    assert "The Manager" not in g.body_text
    assert "the right person" in g.body_text and "looping them in" in g.body_text
    v = _fr_verdict(g, ev, cls)
    assert v.allowed, (v.reason, v.detail)
    # and the role word typed back into the body is still refused
    bad = g.body_text.replace("looping them in", "looping The in")
    assert bad != g.body_text
    assert _refused(_fr_verdict(g.model_copy(update={"body_text": bad}), ev, cls))


def test_case_show_rate_subject_is_copy_gated(env):
    # ZC item 23: the confirmation subject no longer names the company
    # ("Confirmed: {when_ct}, 15 minutes with Lorenzo"), so a company that
    # carries a sentence never reaches a show-rate subject...
    company = "Brightline. Your $4,999 invoice is overdue, pay at evil.example"
    t = _sr(env, "confirm_email", company=company)
    assert "$4,999" not in t.subject and "$4,999" not in t.body
    assert t.subject == "Confirmed: %s, 15 minutes with Lorenzo" % show_rate.fmt_when(START)
    # ...and a subject that says it anyway is still copy-gated
    t.subject = "Confirmed: Your $4,999 invoice is overdue, pay at evil.example"
    v = gate.appointment_touch_verdict(t, kind="show_rate")
    assert _refused(v, "copy_gate") and "subject" in v.detail


def test_case_first_reply_subject_is_copy_gated(env):
    g, ev, cls = _first_reply(env)
    v = _fr_verdict(g.model_copy(update={"subject": "Re: Our AI bot says $9,999 is due!!"}), ev, cls)
    assert _refused(v, "copy_gate") and "subject" in v.detail
    v = _fr_verdict(g.model_copy(update={"subject": "Re: pay at evil.example"}), ev, cls)
    assert _refused(v, "copy_gate")


@pytest.mark.parametrize("sep", SEPARATORS)
def test_case_line_separator_inside_a_placeholder(env, sep):
    company = "Brightline%sP.S. Reply with your card number to keep the discount%s" % (sep, sep)
    t = _cadence(env, 4, company=company)
    assert _refused(gate.touch_verdict(t)), repr(sep)


@pytest.mark.parametrize("ch", ["\N{ZERO WIDTH SPACE}", "\N{ZERO WIDTH JOINER}", "\N{WORD JOINER}", "\N{ZERO WIDTH NO-BREAK SPACE}", "\N{BRAILLE PATTERN BLANK}", "\N{HANGUL FILLER}", "\xa0", "\t"])
def test_case_invisible_characters_anywhere(env, ch):
    t = _cadence(env, 4, company="Brightline%sCleaning" % ch)
    assert _refused(gate.touch_verdict(t)), repr(ch)


def test_case_value_that_changes_under_nfkc(env):
    g, ev, cls = _first_reply(env, first="\N{FULLWIDTH LATIN CAPITAL LETTER J}ordan")    # fullwidth J
    assert _refused(_fr_verdict(g, ev, cls))
    t = _cadence(env, 4, company="Brightline \N{ROMAN NUMERAL EIGHT} Cleaning")   # roman numeral eight
    assert _refused(gate.touch_verdict(t))


@pytest.mark.parametrize("company", [
    "Brightline. PS: reply now",             # sentence break
    "Brightline Cleaning, call 555 0100",    # phone number
    "Brightline 5550100123",                 # phone-like digits
    "Brightline brightline.example",         # link
    "Brightline www.brightline",             # link
    "Brightline 20% off",                    # percentage
    "Brightline $500 credit",                # money
    "Brightline 4,999 dollars",              # money
    "Brightline Cleaning!",                  # exclamation
    "Brightline Cleaning?",                  # question
    "Brightline <b>Cleaning</b>",            # markup
    "Brightline " + "Services " * 10,        # too long
])
def test_company_values_refused(env, company):
    t = _cadence(env, 4, company=company.strip())
    assert not gate.touch_verdict(t).allowed, company


# ================================================================ positives
@pytest.mark.parametrize("first", ["Mary-Jane", "O'Neil", "J. R.", "J.R.", "Jos\xe9", "Mary Ann", "D\N{RIGHT SINGLE QUOTATION MARK}Angelo",
                                   "Anne-Marie Claire"])
def test_real_first_names_pass(env, first):
    g, ev, cls = _first_reply(env, first=first)
    v = _fr_verdict(g, ev, cls)
    assert v.allowed, (first, v.reason, v.detail)
    t = _cadence(env, 4, first=first)
    assert gate.touch_verdict(t).allowed, first


@pytest.mark.parametrize("first", ["Jordan Lee Smith Jr", "Jordan3", "Jordan.", "J..", "-Jordan", "Jordan  Lee",
                                   "x" * 41])
def test_malformed_first_names_refused(env, first):
    g, ev, cls = _first_reply(env, first=first)
    assert not _fr_verdict(g, ev, cls).allowed, first


@pytest.mark.parametrize("company", ["Smith & Co. Ltd", "J. R. Cleaning", "A1 Books", "24/7 Cleaning",
                                     "O'Neil Facility Services (North)", "Brightline Commercial Cleaning Inc.",
                                     "Caf\xe9 Clean LLC", "Acme Staffing, Inc."])
def test_real_company_names_pass(env, company):
    t = _cadence(env, 4, company=company)
    v = gate.touch_verdict(t)
    assert v.allowed, (company, v.reason, v.detail)


def test_referral_names_pass(env):
    for name, first in (("Dana Smith", "Dana"), ("Mary-Jane O'Neil", "Mary-Jane"), ("J. R. Smith", "J.")):
        cls = _cls(label="positive_referral", referral_name=name)
        g, ev, _ = _first_reply(env, cls=cls, branch="referral")
        v = _fr_verdict(g, ev, cls)
        assert v.allowed, (name, v.reason, v.detail)
        assert "looping %s in" % first in g.body_text


def test_every_time_format_the_engine_writes_passes(env):
    """Values produced by the formatters themselves, across the day, both
    week forms, every lead zone the engine names."""
    import pytz
    from shared import slots as slot_rules

    times = [ta._ct(2030, 1, 7 + d, h, m) for d in range(7) for h in (0, 9, 11, 12, 13, 17, 23) for m in (0, 5, 47)]
    for dt in times:
        assert gate._time_ok("slot", slot_rules.format_slot(dt))
        # ZA item 5: the lead's proposed time comes back in their zone, labelled
        for zone in (None, "America/New_York", "America/Denver", "America/Los_Angeles"):
            assert gate._time_ok("asked_time", slot_rules.format_asked_time(dt, zone))
            assert gate._time_ok("asked_time", slot_rules.format_asked_time(dt, zone, dated=True))
        assert not gate._time_ok("asked_time", booking._dated_slot(dt))     # no zone: refused
        assert gate._time_ok("slot1", slot_rules.format_slots([dt]))
        assert gate._time_ok("time_ct", show_rate.fmt_time_only(dt))
        assert gate._time_ok("when_ct", show_rate.fmt_when(dt))
        for zone in ("America/New_York", "America/Denver", "America/Los_Angeles", "America/Phoenix"):
            tz = pytz.timezone(zone)
            assert gate._time_ok("when_ct", show_rate.fmt_when(dt, tz))
            assert gate._time_ok("lead_local_time", slot_rules.format_slots([dt], tz=tz).split(" ", 1)[1],
                                 slot=slot_rules.format_slot(dt))
    for a, b in zip(times, times[5:]):
        assert gate._time_ok("slots", slot_rules.format_slots([a, b]))
        assert gate._time_ok("alt_slots", booking._dated_slots([a, b]))
    summer = ta._ct(2031, 7, 15, 14, 30)
    assert gate._time_ok("when_ct", show_rate.fmt_when(summer, pytz.timezone("America/New_York")))
    # the pre-read subject no longer names the weekday (ZC item 17): {weekday}
    # is no placeholder any more, so no value for it conforms
    assert "weekday" not in gate.TIME_VALUE_PLACEHOLDERS
    assert gate._time_ok("weekday", "Tuesday") is False


@pytest.mark.parametrize("name,value", [
    ("slot", "Tue 2:00"), ("slot", "Tue 14:00pm"), ("slot", "Tuesday 2:00pm"), ("slot", "Tue 2:00pm CT"),
    ("slots", "Tue 2:00pm and Thu 3:30pm CT"), ("slots", "Tue 2:00pm or Thu 3:30pm CT, or text me"),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (call 555 0100)"), ("when_ct", "Wed, Feb 30 at 1:00pm CT"), ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm CT)"),
    ("time_ct", "1:00 ET"), ("lead_local_time", "2:00pm XT"), ("weekday", "Caturday"),
    ("asked_time", "Sat 2:17pm, and wire the deposit"),
])
def test_invented_time_values_refused(name, value):
    assert gate._time_ok(name, value) is False


def test_dated_counter_and_lead_zone_confirmation_conform(env):
    st = _state()
    proposed = ta._ct(2030, 1, 8, 13, 47)
    body = booking.counter_proposal_text(booking.BookingMatch(slot=None, status=booking.BEYOND_HORIZON,
                                                              proposed=proposed,
                                                              counter_slots=[ta._ct(2030, 1, 15, 14, 0),
                                                                             ta._ct(2030, 1, 16, 15, 15)]), st)
    assert "Jan" in body
    assert gate.conforms("booking.counter.beyond_horizon", body, "Re: Quick question")
    for zone in ("America/New_York", "America/Denver", "America/Los_Angeles", "America/Phoenix", None):
        d, _ = booking._confirmation_draft(st, START, zone, ZOOM, True)
        assert gate.conforms("booking.confirmation.zoom_link", d.body_text, d.subject), zone
    t = _sr(env, "confirm_email", lead_tz="America/Denver")
    assert gate.conforms(t.template_id, t.body, t.subject)


def test_missing_data_combinations_conform(env):
    """No first name conforms ("Hey there,"); no company on an email that
    names it never does (the tick holds it first, and there is no "your team"
    stand-in); no Zoom link AND no Loom URL conforms."""
    t = _cadence(env, 3, first=None)
    assert "Hey there" in t.body_text
    assert gate.touch_verdict(t).allowed
    for day in (2, 4, 5):
        held = _cadence(env, day, first=None, company=None)
        assert "your team" not in held.body_text
        assert not gate.touch_verdict(held).allowed, day
    appt_missing = {"niche": "cleaning", "offer": "reactivation", "booking_url": LINK, "id": "a1"}
    copy = show_rate.render("confirm_email", appt_missing, START, NOW)
    tid = gate.resolve_combo_id("show_rate", "confirm_email", "cleaning", "reactivation")
    assert gate.conforms(tid, copy["body"], copy["subject"])


# ================================================================ bindings
def test_bindings_pin_values(env):
    g, ev, cls = _first_reply(env)
    assert _fr_verdict(g, ev, cls, bindings={"first_name": FIRST, "booking_url": LINK}).allowed
    v = _fr_verdict(g, ev, cls, bindings={"first_name": "Casey"})
    assert _refused(v)
    slots_text = re.search(r"Would (.+?) work for a 15-minute call\?", g.body_text).group(1)
    assert _fr_verdict(g, ev, cls, bindings={"slots": slots_text}).allowed
    assert _refused(_fr_verdict(g, ev, cls, bindings={"slots": "Mon 12:00pm or Tue 12:15pm CT"}))


def test_zoom_and_loom_links(env, monkeypatch):
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us",))
    ok = _sr(env, "confirm_email", zoom_link="https://us06web.zoom.us/j/123456789?pwd=abc")
    assert gate.appointment_touch_verdict(ok, kind="show_rate").allowed
    bad = _sr(env, "confirm_email", zoom_link="https://zoom.us.evil.example/j/1")
    assert _refused(gate.appointment_touch_verdict(bad, kind="show_rate"))
    monkeypatch.setenv("LOOM_URL_CLEANING", "https://www.loom.com/share/abc")
    loom = _sr(env, "confirm_email", zoom_link="https://us06web.zoom.us/j/1")
    assert "loom.com/share/abc" in loom.body
    assert gate.appointment_touch_verdict(loom, kind="show_rate").allowed
    monkeypatch.setenv("LOOM_URL_CLEANING", "https://www.loom.com/share/other")
    assert _refused(gate.appointment_touch_verdict(loom, kind="show_rate"))


# ======================================================= booking classification
def _booking_drafts(env):
    st = _state()
    out = []
    conf, _ = booking._confirmation_draft(st, START, None, ZOOM, True)
    out.append(("booking.confirmation.zoom_link", GDraft(**conf.model_dump())))
    body = booking.counter_proposal_text(booking.BookingMatch(slot=None, status=booking.WEEKEND,
                                                              proposed=ta._ct(2030, 1, 12, 14, 0),
                                                              counter_slots=TWO), st)
    out.append(("booking.counter.weekend", GDraft(subject="Re: Quick question", body_text=body, model="template",
                                                  booking_link=LINK, problems=[])))
    from services.reply_engine import app as app_mod

    st2 = _state()
    st2.cadence = {"booking": {"invite_released": True}}
    ab = app_mod._already_booked_body(st2, START.isoformat(), LINK)
    out.append(("booking.already_booked.invite_on_calendar",
                 GDraft(subject="Re: Quick question", body_text=ab, model="template", booking_link=None, problems=[])))
    for tid, g in out:
        env.approve_ids(tid)
        gate.stamp(g, tid)
    return out


def test_booking_emails_pass_with_a_positive_classification(env):
    for tid, g in _booking_drafts(env):
        v = gate.draft_verdict(g, kind="booking", campaign_key=OFFER, allow_terms=[FIRST, COMPANY],
                               classification=_cls())
        assert v.allowed, (tid, v.reason, v.detail)


@pytest.mark.parametrize("cls", [FALLBACK, None, _cls(label="negative_notnow", confidence=0.1),
                                 _cls(confidence=0.5), _cls(label="neutral_question")])
def test_booking_emails_need_the_classification_check(env, cls):
    for tid, g in _booking_drafts(env):
        v = gate.draft_verdict(g, kind="booking", campaign_key=OFFER, allow_terms=[FIRST, COMPANY],
                               classification=cls)
        assert _refused(v, "classification"), (tid, cls)


# ============================================================ confirmed time
@pytest.mark.parametrize("label,branch,extra", [("positive_interested", "default", {}),
                                                ("positive_referral", "referral", {"referral_name": "Dana Smith"})])
def test_confirmed_time_variant_never_auto_sends(env, label, branch, extra):
    """The lead proposed a time that passes the slot rules but no booking was
    made (booking blocked): build_draft falls through to the confirmed wording
    ("I will send the invite over"). An approved first reply must not send it."""
    proposed = ta._ct(2030, 1, 8, 15, 30).isoformat()
    cls = _cls(label=label, proposed_time=proposed, **extra)
    g, ev, _ = _first_reply(env, cls=cls, branch=branch)
    assert "I will send the invite over" in g.body_text
    v = _fr_verdict(g, ev, cls)
    assert _refused(v), (v.reason, v.detail)
    assert gate.conforms(g.template_id, g.body_text, g.subject) is False


# ================================================================ fail closed
class _Exploding(object):
    template_id = "cadence.e1"

    @property
    def template_hash(self):
        raise RuntimeError("boom")


def test_attribute_errors_are_registry_error(env):
    env.approve_ids("cadence.e1")
    assert _refused(gate.touch_verdict(_Exploding()), "registry_error")
    assert _refused(gate.appointment_touch_verdict(_Exploding(), kind="show_rate"), "registry_error")
    assert _refused(gate.draft_verdict(_Exploding(), kind="first_reply", classification=_cls()), "registry_error")
    assert _refused(gate.touch_verdict(None), "registry_error")
    assert _refused(gate.draft_verdict(None, kind="first_reply"), "registry_error")


def test_catalogue_is_never_built_while_app_is_importing(env, monkeypatch):
    from services.reply_engine import app as app_mod

    ta.clear_cache()
    gate.clear_cache()
    monkeypatch.setattr(app_mod.__spec__, "_initializing", True, raising=False)
    built = []
    real = ta._build_catalogue
    monkeypatch.setattr(ta, "_build_catalogue", lambda: built.append(1) or real())
    assert ta.sources_importing() == ["services.reply_engine.app"]
    with pytest.raises(ta.CatalogueNotReady):
        ta.catalogue()
    assert gate.parity_status()["status"] == "not_ready"
    v = gate.ids_verdict("cadence.e1")
    assert _refused(v, "registry_error") and "importing" in v.detail
    assert gate.auto_send_enabled() is False
    assert gate.health_summary()["auto_send_enabled"] is False
    assert built == [] and env.alerts == []
    monkeypatch.setattr(app_mod.__spec__, "_initializing", False, raising=False)
    assert gate.parity_status()["status"] == "ok"


def test_parity_alert_claim_is_released_when_the_push_fails(env, monkeypatch, tmp_path):
    store = JsonFileStore(tmp_path / "alert_store.json")
    results = [{"sent": False, "errors": ["ntfy: down"]}, {"sent": True}]
    monkeypatch.setattr(notify, "notify", lambda *a, **k: results.pop(0))
    status = {"status": "mismatch", "ids": ["cadence.e1"]}
    now = datetime(2030, 1, 8, 15, 0, tzinfo=timezone.utc)
    assert gate.alert_parity_failure(status, store=store, now=now) is False
    assert store.get(gate.PARITY_ALERT_PREFIX + "2030-01-08") is None      # released
    assert gate.alert_parity_failure(status, store=store, now=now) is True
    assert store.get(gate.PARITY_ALERT_PREFIX + "2030-01-08") is not None
    monkeypatch.setattr(notify, "notify", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no second push")))
    assert gate.alert_parity_failure(status, store=store, now=now) is False


def test_a_failed_parity_push_backs_off_before_retrying(env, monkeypatch):
    # Every verdict under a parity failure asks for the alert. A push that does
    # not go out releases the day's claim, but the process waits
    # PARITY_ALERT_RETRY_MINUTES before trying again instead of pushing per verdict.
    calls = []

    def down(*a, **k):
        calls.append(a)
        return {"sent": False, "errors": ["ntfy: down"]}
    monkeypatch.setattr(notify, "notify", down)
    _mismatch = json.loads(env.reference_path.read_text())
    _mismatch["ids"][sorted(_mismatch["ids"])[0]] = "0" * 64
    _mismatch["digest"] = "f" * 64
    env.reference_path.write_text(json.dumps(_mismatch))
    gate.clear_cache()
    for _ in range(5):
        assert gate.auto_send_enabled() is False
        assert gate.ids_verdict("cadence.e1").reason == "parity_failed"
    assert len(calls) == 1
    assert gate._ALERT_SEEN["retry_after"] is not None and gate._ALERT_SEEN["day"] is None
    # once the backoff has passed, the next verdict tries again and a delivered
    # push memoises the day
    gate._ALERT_SEEN["retry_after"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    monkeypatch.setattr(notify, "notify", lambda *a, **k: calls.append(a) or {"sent": True})
    assert gate.auto_send_enabled() is False
    assert gate.auto_send_enabled() is False
    assert len(calls) == 2
    assert gate._ALERT_SEEN["retry_after"] is None and gate._ALERT_SEEN["day"] is not None


def test_not_ready_status_never_alerts(env, tmp_path):
    store = JsonFileStore(tmp_path / "alert_store.json")
    assert gate.alert_parity_failure({"status": "not_ready", "ids": []}, store=store) is False
    assert env.alerts == []


def test_long_hostile_bodies_fail_fast(env):
    import time

    t = cadence.build_touch(_state(company=". I have x open, or grab a time here: y. " * 400), 2,
                            [s.isoformat() for s in TWO],
                            research_line=cadence.fallback_research_line("Q", "reactivation"))
    body = t.body_text.replace("\n\nLorenzo", "\n\nLorenzo.")
    t0 = time.time()
    assert not gate.conforms("cadence.e2", body, t.subject, ["cadence.e2.research_fallback.reactivation"])
    assert time.time() - t0 < 2.0


def test_catalogue_texts_are_nfkc_stable_and_clean():
    import unicodedata

    for e in ta.catalogue():
        text = e.get("review_text") or ""
        assert unicodedata.normalize("NFKC", text) == text, e["id"]
        assert gate._clean_chars(text, allow_newline=True), e["id"]


def test_every_placeholder_in_the_catalogue_has_a_type():
    typed = set(gate.NAME_PLACEHOLDERS + gate.TEXT_PLACEHOLDERS + gate.TIME_VALUE_PLACEHOLDERS
                + gate.URL_PLACEHOLDERS + gate.PART_FILLED)
    for e in ta.catalogue():
        for v in e.get("variables") or []:
            assert v in typed, (e["id"], v)


def test_sources_importing_ignores_the_registry_itself():
    assert "services.reply_engine.template_approvals" not in ta.sources_importing()
    assert sys.modules["services.reply_engine.template_approvals"] is ta


# ================================================================== round 3
# ---- links: a binding only narrows
GHL = "https://api.leadconnectorhq.com/widget/booking/TestCalendar01"
REAL_ZOOM = "https://us06web.zoom.us/j/81234567890?pwd=AbCdEf123"
BAD_LINKS = ("http://evil.example/book", "javascript:alert(document.cookie)", "https://evil.example/reschedule",
             "data:text/html,hi")


@pytest.mark.parametrize("link", BAD_LINKS)
def test_r3_a_bad_booking_link_in_a_first_reply_is_refused_bound_or_not(env, link):
    """The first-reply copy gate refuses a body without the configured link
    first; the conformance check refuses it on its own too."""
    g, ev, cls = _first_reply(env)
    # first replies carry no booking link (2026-09-23); one added is refused
    assert LINK not in g.body_text
    assert gate.conforms(g.template_id, g.body_text, g.subject, bindings=None)
    ask = "work for a 15-minute call?"
    bad = g.body_text.replace(ask, ask + " Or grab a time here: " + link, 1)
    assert bad != g.body_text
    for bindings in (None, {"booking_url": link}):
        assert not _fr_verdict(g.model_copy(update={"body_text": bad}), ev, cls, bindings=bindings).allowed
        assert gate.conforms(g.template_id, bad, g.subject, bindings=bindings) is False, (link, bindings)


def test_r3_bound_zoom_and_loom_links_are_still_checked(env, monkeypatch):
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us",))
    off_host = "https://evil.example/j/1"
    t = _sr(env, "confirm_email", zoom_link=off_host)
    assert off_host in t.body
    for bindings in (None, {"zoom_link": off_host}):
        assert _refused(gate.appointment_touch_verdict(t, kind="show_rate", bindings=bindings)), bindings
    t = _sr(env, "confirm_email", zoom_link=REAL_ZOOM)
    assert gate.appointment_touch_verdict(t, kind="show_rate", bindings={"zoom_link": REAL_ZOOM}).allowed
    assert _refused(gate.appointment_touch_verdict(t, kind="show_rate",
                                                   bindings={"zoom_link": "https://us06web.zoom.us/j/1"}))
    loom = "https://www.loom.com/share/abc"
    monkeypatch.setenv("LOOM_URL_CLEANING", loom)
    t = _sr(env, "confirm_email", zoom_link=REAL_ZOOM)
    assert loom in t.body
    assert gate.appointment_touch_verdict(t, kind="show_rate", bindings={"loom_url": loom}).allowed
    monkeypatch.setenv("LOOM_URL_CLEANING", "https://www.loom.com/share/other")
    assert _refused(gate.appointment_touch_verdict(t, kind="show_rate", bindings={"loom_url": loom}))


@pytest.mark.parametrize("name,value", [
    ("zoom_link", "https://evil.example#@us06web.zoom.us/j/1"),          # host ends at the fragment
    ("zoom_link", "https://evil.example?@us06web.zoom.us/j/1"),          # ... or at the query
    ("zoom_link", "https://us06web.zoom.us@evil.example/j/1"),           # user info
    ("zoom_link", "https://user:pw@us06web.zoom.us/j/1"),                # user info
    ("zoom_link", "https://us06web.zoom.us:8443/j/1"),                   # port
    ("zoom_link", "https://us06web.zoom.us\\@evil.example/j/1"),         # backslash
    ("zoom_link", "https://zoom.us.evil.example/j/1"),                   # look-alike suffix
    ("zoom_link", "https://evilzoom.us/j/1"),                            # not a subdomain
    ("zoom_link", "https://us06web.zoom.us./j/1"),                       # trailing dot
    ("zoom_link", "http://us06web.zoom.us/j/1"),                         # http
    ("zoom_link", "https://us06web.zoom.us/j/1."),                       # ends the sentence
    ("zoom_link", "//us06web.zoom.us/j/1"),                              # no scheme
    ("booking_url", "https://api.leadconnectorhq.com/widget/booking/x/../../../evil"),   # traversal
    ("booking_url", "https://api.leadconnectorhq.com/widget/booking/"),                  # no calendar id
    ("booking_url", "https://api.leadconnectorhq.com/widget/booking/abc/def"),           # two segments
    ("booking_url", "https://api.leadconnectorhq.com/widget/booking/abc?next=x"),        # query
    ("booking_url", "https://api.leadconnectorhq.com/widget/booking/abc#x"),             # fragment
    ("booking_url", "https://api.leadconnectorhq.com/widget/bookings/abc"),              # other path
    ("booking_url", "https://api.leadconnectorhq.com.evil.example/widget/booking/abc"),  # other host
    ("booking_url", "https://evil.example/widget/booking/abc"),                          # other host
    ("booking_url", "https://api.leadconnectorhq.com:444/widget/booking/abc"),           # port
    ("booking_url", "http://api.leadconnectorhq.com/widget/booking/abc"),                # http
    ("booking_url", LINK + "?next=https://evil.example"),                                # not the configured link
    ("booking_url", LINK.replace("https", "http", 1)),
    ("loom_url", "https://www.loom.com/share/not-configured"),
    ("loom_url", "javascript:alert(1)"),
])
def test_r3_link_grammar_refusals(env, name, value):
    assert gate._url_ok(name, value) is False


@pytest.mark.parametrize("name,value", [
    ("zoom_link", REAL_ZOOM), ("zoom_link", "https://zoom.us/j/1"), ("zoom_link", "https://US06WEB.ZOOM.US/j/1"),
    ("booking_url", LINK), ("booking_url", GHL), ("booking_url", GHL + "/"),
])
def test_r3_link_grammar_accepts(env, name, value):
    assert gate._url_ok(name, value) is True


# ---- lead zones: whatever the engine's formatters write for the zone the render used
NAMED_ZONES = sorted(set(pytz.common_timezones) | set(n for n in pytz.all_timezones
                                                       if n.startswith(("US/", "Canada/"))))
LEAD_ZONES = sorted(set(
    ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix",
     "America/Detroit", "America/Indiana/Indianapolis", "America/Kentucky/Louisville", "America/Toronto",
     "America/Boise", "America/Anchorage", "Pacific/Honolulu", "America/Puerto_Rico", "America/Vancouver",
     "America/Edmonton", "America/Winnipeg", "America/Halifax", "America/St_Johns", "America/Regina",
     "America/Mexico_City", "Europe/London", "Asia/Kolkata"]
    + [n for n in NAMED_ZONES if n.startswith(("US/", "Canada/"))]))
# Winter: FIXED_NOW's week. Summer: the week SUMMER_WEEK_OFFSET weeks later.
SEASONS = {"winter": (NOW, START),
           "summer": (NOW + timedelta(weeks=gate.SUMMER_WEEK_OFFSET), START + timedelta(weeks=gate.SUMMER_WEEK_OFFSET))}


def _appointment(zone=None, **extra):
    appt = {"niche": "cleaning", "offer": "reactivation", "booking_url": LINK, "id": "a1", "zoom_link": ZOOM,
            "first_name": FIRST, "company": COMPANY}
    if zone:
        appt["lead_tz"] = zone
    appt.update(extra)
    return appt


def _appointment_touch(kind, key, appt, start, now):
    if kind == "show_rate":
        copy = show_rate.render(key, appt, start, now)
        channel = dict((k, c) for k, c, _ in show_rate.SEQUENCE)[key]
    else:
        slots_text = slot_rules.format_slots([start + timedelta(days=1, hours=1),
                                              start + timedelta(days=2, hours=2, minutes=30)])
        copy = no_show.render(key, appt, start, slots_text, 1)
        channel = dict((k, c) for k, c, _ in no_show.FULL_SEQUENCE)[key]
    t = show_rate.Touch(key="a1:x:%s" % key, appointment_id="a1", contact_id=None, when_iso=now.isoformat(),
                        channel=channel, template_key=key, body=copy["body"], subject=copy.get("subject"))
    gate.stamp(t, gate.resolve_combo_id(kind, key, "cleaning", "reactivation"))
    return t


def test_r3_the_zone_list_covers_every_named_zone():
    names = set(z.zone for z in gate._lead_zones())
    assert set(NAMED_ZONES) <= names
    assert len(NAMED_ZONES) > 400 and "US/Eastern" in names and "Canada/Newfoundland" in names


@pytest.mark.parametrize("season", sorted(SEASONS))
@pytest.mark.parametrize("zone", LEAD_ZONES)
def test_r3_every_kind_conforms_in_a_lead_zone(env, zone, season):
    """Show-rate and no-show touches (unbound, and bound with
    appointment_bindings) and the booking confirmation, in winter and in
    summer, for a lead in ``zone``."""
    now, start = SEASONS[season]
    env.approve_ladders()
    env.approve_ids("booking.confirmation.zoom_link")
    appt = _appointment(zone)
    bound = gate.appointment_bindings(appt, start)
    assert set(bound) == {"when_ct", "time_ct", "zoom_link"} and bound["zoom_link"] == ZOOM
    for kind, keys in (("show_rate", ta.SHOW_RATE_LEAD_FACING), ("no_show", ta.NO_SHOW_LEAD_FACING)):
        for key in keys:
            t = _appointment_touch(kind, key, appt, start, now)
            options = (None, bound)
            if kind == "show_rate":
                # Section 2: the reminders' {time} carries the lead's clock in
                # brackets, which only the engine's own binding vouches for
                # (show_rate.touch_bindings, what dispatch_touch hands the gate)
                dispatch = show_rate.touch_bindings(t, dict(appt, start_iso=start.isoformat()))
                options = (dispatch,) if "{time_ct}" in ta.catalogue_index()[t.template_id]["text"] else (
                    None, bound, dispatch)
            for bindings in options:
                v = gate.appointment_touch_verdict(t, kind=kind, allow_terms=[FIRST, COMPANY], bindings=bindings)
                assert v.allowed, (zone, season, key, bindings is not None, v.reason, v.detail)
    d, _ = booking._confirmation_draft(_state(), start, zone, ZOOM, True)
    g = GDraft(**d.model_dump())
    gate.stamp(g, "booking.confirmation.zoom_link")
    v = gate.draft_verdict(g, kind="booking", campaign_key=OFFER, allow_terms=[FIRST, COMPANY], classification=_cls())
    assert v.allowed, (zone, season, v.reason, v.detail)


@pytest.mark.parametrize("season", sorted(SEASONS))
def test_r3_every_named_zone_the_formatters_write_passes(env, season):
    """Every pytz common zone and every US/* and Canada/* name: fmt_when with
    the zone show_rate.lead_tz_of answers for the name and with pytz's own,
    and booking's "(... your time)" beside its {slot}."""
    _, start = SEASONS[season]
    for dt in (start, start + timedelta(hours=4, minutes=47)):
        slot = slot_rules.format_slot(dt)
        for n in NAMED_ZONES:
            for tz in (pytz.timezone(n), show_rate.lead_tz_of({"lead_tz": n})):
                assert gate._time_ok("when_ct", show_rate.fmt_when(dt, tz)), (n, season, dt)
            their = booking._their_time(dt, n)
            if n == "America/Chicago":
                assert their == ""
                continue
            assert their.startswith(" (") and their.endswith(" your time)"), their
            assert gate._time_ok("lead_local_time", their[2:-len(" your time)")], slot=slot), (n, season, dt)


@pytest.mark.parametrize("name,value,slot", [
    # a real label with the wrong time
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (3:00pm ET)", None),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:30pm ET)", None),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (4:00pm EST)", None),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (1:00pm PST)", None),
    ("lead_local_time", "3:00pm ET", "Tue 1:00pm"),
    ("lead_local_time", "2:00pm PT", "Tue 1:00pm"),
    # a made-up label
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm XST)", None),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm Eastern)", None),
    ("lead_local_time", "2:00pm XT", "Tue 1:00pm"),
    ("lead_local_time", "2:00pm Eastern", "Tue 1:00pm"),
    # a label with extra words
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm ET) sharp", None),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm ET, call first)", None),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm ET) (3:00pm PT)", None),
    ("lead_local_time", "2:00pm ET sharp", "Tue 1:00pm"),
    ("lead_local_time", "2:00pm ET or later", "Tue 1:00pm"),
    # the lead's time with no slot beside it, or a slot it is not the time of
    ("lead_local_time", "2:00pm ET", None),
    ("lead_local_time", "2:00pm ET", ""),
    ("lead_local_time", "2:00pm ET", "Tue 3:00pm"),
    ("lead_local_time", "2:00pm ET", "Tue 1:00pm, or later"),
])
def test_r3_invented_lead_zone_times_refused(env, name, value, slot):
    assert gate._time_ok(name, value, slot=slot) is False


def test_r3_real_zone_labels_pass(env):
    for value in ("Tue, Jan 8 at 1:00pm CT (2:00pm ET)", "Tue, Jan 8 at 1:00pm CT (2:00pm EST)",
                  "Tue, Jan 8 at 1:00pm CT (3:00pm AST)", "Tue, Jan 8 at 1:00pm CT (3:30pm NST)",
                  "Tue, Jan 8 at 1:00pm CT (9:00am HST)", "Tue, Jan 8 at 1:00pm CT (7:00pm GMT)",
                  "Tue, Jul 9 at 1:00pm CT (2:00pm EDT)", "Tue, Jul 9 at 1:00pm CT (11:00am MST)"):
        assert gate._time_ok("when_ct", value), value
    for value, slot in (("2:00pm ET", "Tue 1:00pm"), ("2:00pm EST", "Tue 1:00pm"), ("2:00pm EDT", "Tue 1:00pm"),
                        ("11:00am MST", "Tue 1:00pm"), ("12:00pm MST", "Tue 1:00pm"), ("9:00am HST", "Tue 1:00pm")):
        assert gate._time_ok("lead_local_time", value, slot=slot), (value, slot)


def test_r3_lead_local_time_must_be_the_time_of_the_slot_beside_it(env):
    env.approve_ids("booking.confirmation.zoom_link")
    d, _ = booking._confirmation_draft(_state(), START, "America/New_York", ZOOM, True)
    assert "Tue 1:00pm CT (2:00pm ET your time)" in d.body_text
    cls = _cls()

    def verdict(body):
        g = GDraft(**d.model_dump())
        g = g.model_copy(update={"body_text": body})
        gate.stamp(g, "booking.confirmation.zoom_link")
        return gate.draft_verdict(g, kind="booking", campaign_key=OFFER, allow_terms=[FIRST, COMPANY],
                                  classification=cls)
    assert verdict(d.body_text).allowed
    assert verdict(d.body_text.replace("(2:00pm ET your", "(2:00pm EST your")).allowed
    for fake in ("(3:00pm ET your", "(2:00pm PT your", "(2:00pm XT your", "(2:00pm ET, 3:00pm PT your"):
        assert _refused(verdict(d.body_text.replace("(2:00pm ET your", fake))), fake
    # the slot moved but the lead's time did not
    assert _refused(verdict(d.body_text.replace("Tue 1:00pm CT", "Tue 3:00pm CT")))


def test_r3_an_engine_time_binding_is_its_own_check(env, monkeypatch):
    """A lead zone outside _lead_zones() (simulated by narrowing the list to
    Central): unbound, the lead's time is refused; bound with
    appointment_bindings(), exactly the engine's own value passes. A plain
    string binding only narrows, and a different engine value is refused."""
    env.approve_ladders()
    monkeypatch.setitem(gate._ZONES, "list", [pytz.timezone("America/Chicago")])
    gate._ZONE_OUTPUTS.clear()
    gate._VALUE_CACHE.clear()
    appt = _appointment("America/New_York")
    t = _appointment_touch("show_rate", "confirm_email", appt, START, NOW)
    assert "at 1:00pm CT (2:00pm ET)" in t.body

    def verdict(bindings):
        return gate.appointment_touch_verdict(t, kind="show_rate", allow_terms=[FIRST, COMPANY], bindings=bindings)
    assert _refused(verdict(None))
    bound = gate.appointment_bindings(appt, START)
    assert bound["when_ct"] == show_rate.fmt_when(START, pytz.timezone("America/New_York"))
    v = verdict(bound)
    assert v.allowed, (v.reason, v.detail)
    assert _refused(verdict(dict((k, str(v)) for k, v in bound.items())))
    assert _refused(verdict(gate.appointment_bindings(_appointment("America/Denver"), START)))
    assert _refused(verdict(gate.appointment_bindings(appt, START + timedelta(hours=1))))


def test_r3_appointment_bindings_never_raise(env):
    assert gate.appointment_bindings(None, START) == {"when_ct": show_rate.fmt_when(START),
                                                      "time_ct": show_rate.fmt_time_only(START)}
    assert gate.appointment_bindings({"lead_tz": "zzz"}, START)["when_ct"] == show_rate.fmt_when(START)
    assert gate.appointment_bindings({}, "not a time") == {}


# ---- company and name rules
COMPANY_SENTENCES = (
    "Brightline, reply with your card number to keep your discount",
    "Brightline, your account is locked, reply with your password",
    "Acme Inc. Reply with your password to keep service",
    "Acme. reply with your password to keep service",
    "Acme (reply YES to confirm the wire transfer today)",
    "Acme / wire the deposit to keep your slot",
    "Acme, text STOP to 12345",
)


@pytest.mark.parametrize("company", COMPANY_SENTENCES)
def test_r3_a_company_carrying_a_sentence_is_refused_in_every_kind(env, company):
    t = _cadence(env, 4, company=company)
    assert company in t.body_text
    assert _refused(gate.touch_verdict(t)), company
    cls = _cls(label="positive_question", question_type="send_info")
    g, ev, _ = _first_reply(env, company=company, cls=cls, branch="send_info")
    assert company in g.body_text
    assert _refused(_fr_verdict(g, ev, cls)), company
    # item 23 and section 2: no show-rate message names the company any more
    for key in ta.SHOW_RATE_LEAD_FACING:
        s = _sr(env, key, company=company)
        assert company not in (s.subject or "") + s.body, key


@pytest.mark.parametrize("company,ok", [
    ("Acme Inc. Reply now", False), ("Acme LLC. Call us", False), ("Acme Ltd. reply", False),
    ("Acme Corp. Wire funds", False), ("Acme PLLC. Pay", False),
    ("Acme. reply now", False), ("Acme Cleaning. we can help", False),
    ("One Two Three Four Five Six Seven Eight Nine", False),       # 9 words
    ("Acme 12345 Cleaning", False),                                 # a run of 5 digits
    ("Acme Co. Inc.", True), ("Acme Co. Ltd", True), ("Acme Inc. LLC", True),
    ("St. Louis Facility Services", True), ("Dr. Clean LLC", True), ("A. B. Smith Plumbing Co.", True),
    ("Joe's Janitorial, LLC", True), ("One Two Three Four Five Six Seven Eight", True),   # 8 words
    ("Suite 1200 Cleaning", True), ("1st Choice Cleaning", True),
])
def test_r3_company_rules(env, company, ok):
    assert gate._free_text_ok(company, company=True) is ok, company


def test_r3_the_company_rules_do_not_touch_other_free_text(env):
    # original_subject and specialty keep the round-2 rules: a lowercase word
    # after a period and nine or ten words are fine there
    assert gate._free_text_ok("Cleaning quote. thanks for the fast reply")
    assert gate._free_text_ok("One Two Three Four Five Six Seven Eight Nine Ten")
    assert gate._free_text_ok("Acme 12345 Cleaning")


@pytest.mark.parametrize("first", ["Jоrdan", "Аlex", "Jordαn", "Mary Мae"])
def test_r3_names_mixing_scripts_are_refused(env, first):
    assert gate._name_ok(first) is False
    g, ev, cls = _first_reply(env, first=first)
    assert _refused(_fr_verdict(g, ev, cls)), first


@pytest.mark.parametrize("first", ["Дмитрий", "Νίκος",
                                   "José", "Zoë", "Björn", "Élodie"])
def test_r3_names_in_one_script_pass(env, first):
    assert gate._name_ok(first) is True


# ---- fallback wordings: the fixed words a variant puts in a placeholder's place
EXPECTED_FALLBACKS = {
    # ZA item 20: a counter with no free alternative asks the lead to pick on
    # the booking link, so only the dated example remains here.
    "alt_slots": ["Tue Jan 15 2:43pm or Wed Jan 16 3:17pm CT"],
    "preview": ["The first two messages I'd send accounts that cancelled or never signed: \"Quick question, who's "
                "handling your cleaning these days?\" and \"Happy to take another look at the space and send a fresh "
                "quote. Want me to set that up?\""],
    # ZA item 5: the lead's time in their own zone, with its label (CT for
    # Central or no zone); "that time" is gone (item 18).
    "asked_time": ["Fri Jan 11 1:47pm CT", "Sat Jan 12 1:47pm CT", "Tue Jan 8 1:47pm CT", "Tue Jan 8 7:47pm CT",
                   "Tue Jan 8 9:47am CT"],
    # 2026-09-23: no "your team" any more. A cadence email that names the
    # company is held without one (cadence.missing_lead_data).
    "company": ["your business"],
    "first_name": ["there"],
    # The cadence lines the missing_lead_data variants show in place (cleaning
    # reactivation). A touch always fills these from its part, so an unbound
    # one never auto-sends (template_gate._conforms skips it).
    "observation": ["An account that cancelled or never signed already knows your name, so it's usually an easier "
                    "conversation than a brand-new lead."],
    "offer_proof": ["a win-back system for a commercial roofer doing $150M a year that recovered about $6M worth of "
                    "contracts within 6 months"],
    # ZB: no first name gives "Re: your reply" (never "Re: there, question")
    "original_subject": ["your reply"],
    # CT3 phase 2: the referral template's no-name variant ("the right
    # person" ... "looping them in", draft.referral_person).
    "referral_first_name": ["them"],
    "referral_name": ["the right person"],
    # ZB: no "slots" entry. There is no no-slot cadence body any more (2026-09-23).
    # ZC item 8: am/pm (the lead_in_other_timezone variants keep their example times)
    # Section 2: the reminders' {time} carries the lead's clock too
    "time_ct": ["1:47pm CT (2:47pm ET)"],
    "when_ct": ["Tue, Jan 8 at 1:47pm CT (2:47pm ET)"],
    # ZC: no zoom_link entry any more. With no call link on file the
    # show-rate and no-show messages use their own no_call_link wording, so
    # no fixed phrase is accepted in the link's place.
}


def test_r3_the_accepted_fallback_wordings_are_pinned(env):
    """Every fixed wording an unbound placeholder may take without its type
    check. A change here widens (or narrows) what auto-sends: review it."""
    got = gate.fallback_wordings()
    assert got == EXPECTED_FALLBACKS
    assert sum(len(v) for v in got.values()) == 16


# ---- cost: a crafted time value stays cheap
CRAFTED_TIMES = (
    ("when_ct", "Mon Tue Wed Thu Fri Sat Sun Jan Feb Mar 1 2 3 4 5 6 7 8 9 10 1:00", None),
    ("when_ct", "Jan Feb Mar Apr May Jun Tue 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15", None),
    ("alt_slots", "Tue Jan 1 2 3 4 5 6 7 1:00 2:00 3:00 4:00 5:00 6:00 7:00 8:00 9:", None),
    ("alt_slots", "Mon Tue Wed Thu Fri Sat Sun Jan 1:00 2:00 3:00 4:00 5:00 6:00 7:0", None),
    ("slots", "Mon 1:00 2:00 3:00 4:00 5:00 6:00 7:00 8:00 9:00 10:00 11:00 12:00", None),
    ("asked_time", "Mon Tue Wed Thu Fri Sat Sun Jan Feb Mar Apr May 1 2 3 4 5 6 7 1:00", None),
    ("lead_local_time", "1:00 2:00 3:00 4:00 5:00 6:00 7:00 8:00 9:00 10:00 11:00 12:", None),
    # a real Central rendering first, so the zone tables are built
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm EST) Jan Feb Mar Tue 1 2 3 4 5 6 7", None),
    ("when_ct", "Tue, Jan 8 at 1:00pm CT (9:59am XST)", None),
    ("lead_local_time", "2:00pm EST", "Mon Tue Wed Thu Fri 1:00 2:00 3:00 4:00 5:00 6:00 7:00 8:00"),
    ("lead_local_time", "3:00pm EST", "Tue 1:00pm"),
)
CRAFTED_TIME_LIMIT = 0.058


def test_r3_crafted_time_values_stay_cheap(env):
    """Each value with every value and zone-table cache cleared, best of
    three (a scheduler hiccup is not the gate's cost). The zone list itself
    is built with the catalogue, before any value check."""
    gate._index()
    assert gate._ZONES["list"]
    for name, value, slot in CRAFTED_TIMES:
        best = None
        for _ in range(3):
            gate._VALUE_CACHE.clear()
            gate._ZONE_OUTPUTS.clear()
            t0 = time.perf_counter()
            assert gate._time_ok(name, value[:gate.TIME_MAX_CHARS], slot=slot) is False
            took = time.perf_counter() - t0
            best = took if best is None else min(best, took)
        assert best < CRAFTED_TIME_LIMIT, (name, value, best)


def test_r3_the_catalogue_build_warms_the_zone_list(env, monkeypatch):
    monkeypatch.setitem(gate._ZONES, "list", None)
    gate.clear_cache()
    gate._index()
    assert gate._ZONES["list"] and len(gate._ZONES["list"]) > 400


def test_r3_a_failed_zone_warm_up_leaves_the_value_check_to_fail_closed(env, monkeypatch):
    monkeypatch.setitem(gate._ZONES, "list", None)
    gate.clear_cache()

    def boom():
        raise RuntimeError("no zones")
    monkeypatch.setattr(gate, "_lead_zones", boom)
    gate._index()                                   # the catalogue still builds
    assert gate._ZONES["list"] is None
    with pytest.raises(RuntimeError):
        gate._time_ok("when_ct", "Tue, Jan 8 at 1:00pm CT (2:00pm ET)")
    env.approve_ladders()
    t = _appointment_touch("show_rate", "confirm_email", _appointment("America/New_York"), START, NOW)
    assert _refused(gate.appointment_touch_verdict(t, kind="show_rate", allow_terms=[FIRST, COMPANY]),
                    "registry_error")


# ================================================================== CT3 phase-1 polish
# ---- trade-name abbreviations are not the end of a sentence
@pytest.mark.parametrize("company", ["Mr. Rooter Plumbing", "Mr. Electric of Dallas", "Mr. Sparky Electric",
                                     "Ms. Molly Maid", "Ft. Worth Roofing", "Smith & Assoc. Inc", "Acme Svcs. LLC",
                                     "Acme Mfg. Co.", "Mrs. Clean Janitorial", "Pt. Loma Plumbing",
                                     "Acme Service Ctr. LLC"])
def test_polish_trade_name_abbreviations_pass(env, company):
    assert gate._free_text_ok(company, company=True) is True, company
    t = _cadence(env, 4, company=company)
    assert company in t.body_text
    v = gate.touch_verdict(t)
    assert v.allowed, (company, v.reason, v.detail)


@pytest.mark.parametrize("company", COMPANY_SENTENCES + (
    "Mr. Rooter. Reply now", "Acme Svcs. LLC. Reply now", "Ms. Molly Maid Inc. Pay now"))
def test_polish_attack_companies_stay_refused(env, company):
    assert gate._free_text_ok(company, company=True) is False, company


# ---- mixed scripts: Latin letters with letters from any other script
ARMENIAN_JORDAN = "Jօrdan"     # Armenian small oh
CHEROKEE_JOHN = "Joᏼn"         # Cherokee small letter


@pytest.mark.parametrize("first", [ARMENIAN_JORDAN, CHEROKEE_JOHN])
def test_polish_names_mixing_latin_with_any_script_are_refused(env, first):
    assert unicodedata.normalize("NFKC", first) == first      # refused for the script, not by NFKC
    assert gate._mixed_script(first) is True
    assert gate._name_ok(first) is False
    g, ev, cls = _first_reply(env, first=first)
    assert _refused(_fr_verdict(g, ev, cls)), first
    t = _cadence(env, 4, first=first)
    assert _refused(gate.touch_verdict(t)), first


@pytest.mark.parametrize("company", [ARMENIAN_JORDAN + " Roofing", CHEROKEE_JOHN + " Plumbing LLC",
                                     "Brightline Clеaning"])   # Cyrillic e
def test_polish_companies_mixing_latin_with_any_script_are_refused(env, company):
    assert gate._free_text_ok(company, company=True) is False
    t = _cadence(env, 4, company=company)
    assert company in t.body_text
    assert _refused(gate.touch_verdict(t)), company


@pytest.mark.parametrize("value", ["José", "Müller", "Zoë", "Nuñez"])
def test_polish_latin_with_diacritics_passes(env, value):
    assert gate._mixed_script(value) is False
    assert gate._name_ok(value) is True
    g, ev, cls = _first_reply(env, first=value)
    v = _fr_verdict(g, ev, cls)
    assert v.allowed, (value, v.reason, v.detail)
    company = value + " Roofing LLC"
    assert gate._free_text_ok(company, company=True) is True
    t = _cadence(env, 4, company=company)
    v = gate.touch_verdict(t)
    assert v.allowed, (company, v.reason, v.detail)


def test_polish_one_non_latin_script_still_passes(env):
    for value in ("Дмитрий", "Νίκος"):
        assert gate._name_ok(value) is True
        assert gate._free_text_ok(value, company=True) is True
    # specialty and original_subject keep the old rule: look-alikes are not refused there
    assert gate._free_text_ok("Brightline Clеaning") is True


# ---- GHL booking links: our calendar ids only
REAL_IDS = Path(__file__).resolve().parents[3] / "config" / "ids.json"


def _real_calendar_ids():
    data = json.loads(REAL_IDS.read_text(encoding="utf-8"))
    return sorted(c["id"] for c in data["ghl"]["calendars"].values() if c.get("id"))


def test_polish_a_ghl_link_to_our_calendar_passes_and_a_strangers_is_refused(env, monkeypatch):
    before = REAL_IDS.read_bytes()
    monkeypatch.setattr(gate, "CALENDAR_IDS_PATH", REAL_IDS)       # the real file, read only
    gate.clear_cache()
    ours = _real_calendar_ids()
    assert ours
    for cal in ours:
        link = "https://api.leadconnectorhq.com/widget/booking/%s" % cal
        assert gate._url_ok("booking_url", link), cal
    # (section 2: no show-rate message carries a booking link any more, so
    # the link is judged on its own here)
    stranger = "https://api.leadconnectorhq.com/widget/booking/StrangerCalendar99"
    assert gate._url_ok("booking_url", stranger) is False
    # the test calendar of the fixture is not ours in the real file
    assert gate._url_ok("booking_url", GHL) is False
    assert REAL_IDS.read_bytes() == before


def test_polish_the_configured_booking_links_calendar_passes(env, monkeypatch, tmp_path):
    empty = tmp_path / "no_calendars.json"
    empty.write_text(json.dumps({"ghl": {}}))
    monkeypatch.setattr(gate, "CALENDAR_IDS_PATH", empty)
    gate.clear_cache()
    configured = "https://api.leadconnectorhq.com/widget/booking/ConfiguredCal7"
    monkeypatch.setattr(settings, "BOOKING_URL", configured)
    assert gate._url_ok("booking_url", configured)
    assert gate._url_ok("booking_url", configured + "/")                # same calendar id
    assert gate._url_ok("booking_url", GHL) is False                    # not in the (empty) ids file


@pytest.mark.parametrize("content", [None, "{not json", "[]", '{"ghl": {"calendars": {"x": {"id": 7}}}}'])
def test_polish_an_unreadable_ids_file_pins_nothing_extra(env, monkeypatch, tmp_path, content):
    path = tmp_path / "broken_ids.json"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(gate, "CALENDAR_IDS_PATH", path)
    gate.clear_cache()
    assert gate._url_ok("booking_url", GHL) is False
    assert gate._url_ok("booking_url", LINK) is True                    # the configured link still passes


def test_polish_an_edited_ids_file_is_read_again(env, monkeypatch, tmp_path):
    path = tmp_path / "ids_edit.json"
    path.write_text(json.dumps({"ghl": {"calendars": {"a": {"id": "OtherCal"}}}}))
    monkeypatch.setattr(gate, "CALENDAR_IDS_PATH", path)
    gate.clear_cache()
    assert gate._url_ok("booking_url", GHL) is False
    path.write_text(json.dumps({"ghl": {"calendars": {"a": {"id": "OtherCal"}, "b": {"id": "TestCalendar01"}}}}))
    assert gate._url_ok("booking_url", GHL) is True


# ---- a zone name that fails to load is skipped, not fatal
def test_polish_a_zone_that_fails_to_load_is_skipped_and_logged_once(env, monkeypatch, caplog):
    real = pytz.timezone
    bad = "Europe/Lisbon"

    def flaky(name):
        if name == bad:
            raise pytz.UnknownTimeZoneError(name)
        return real(name)
    monkeypatch.setattr(pytz, "timezone", flaky)
    monkeypatch.setitem(gate._ZONES, "list", None)
    gate.clear_cache()
    with caplog.at_level("WARNING", logger="reply_engine.template_gate"):
        zones = gate._lead_zones()
        gate._lead_zones()                                  # built once: no second warning
    names = set(z.zone for z in zones)
    assert bad not in names and "America/New_York" in names and len(names) > 400
    skipped = [r for r in caplog.records if "skipped" in r.getMessage()]
    assert len(skipped) == 1 and bad in skipped[0].getMessage()
    # a timed verdict in another zone is still judged, not registry_error
    env.approve_ladders()
    t = _appointment_touch("show_rate", "confirm_email", _appointment("America/New_York"), START, NOW)
    v = gate.appointment_touch_verdict(t, kind="show_rate", allow_terms=[FIRST, COMPANY])
    assert v.allowed, (v.reason, v.detail)
    monkeypatch.setitem(gate._ZONES, "list", None)          # the next test builds the real list


# ---- the year window always holds FIXED_NOW's year
class _FutureClock(datetime):
    YEAR = 2033

    @classmethod
    def now(cls, tz=None):
        return datetime(cls.YEAR, 3, 1, 12, 0, tzinfo=tz or timezone.utc)


@pytest.mark.parametrize("year", [2032, 2033, 2040])
def test_polish_fixed_now_dates_pass_whatever_the_real_year(env, monkeypatch, year):
    """Tue Jul 9 is a Tuesday in 2030 (the summer reference week) and in no
    year of 2032-2038, so with the clock in 2033 only FIXED_NOW's year can
    make the dated summer values match."""
    monkeypatch.setattr(_FutureClock, "YEAR", year)
    monkeypatch.setattr(gate, "datetime", _FutureClock)
    summer = START + timedelta(weeks=gate.SUMMER_WEEK_OFFSET)
    assert summer.year == ta.FIXED_NOW[0]
    assert ta.FIXED_NOW[0] in set(d.year for d in gate._dates(show_rate.fmt_when(summer, None), True))
    for dt in (START, summer):
        assert gate._time_ok("when_ct", show_rate.fmt_when(dt, None)), (year, dt)
        assert gate._time_ok("when_ct", show_rate.fmt_when(dt, pytz.timezone("America/New_York"))), (year, dt)
        assert gate._time_ok("asked_time", slot_rules.format_asked_time(dt, dated=True)), (year, dt)


# ================================================================== ZC copy round
# ---- the call link: Zoom or Google Meet, exact host, nothing else
MEET = "https://meet.google.com/abc-defg-hij"


@pytest.mark.parametrize("value", [MEET, "https://MEET.GOOGLE.COM/abc-defg-hij", MEET + "?authuser=0"])
def test_zc_a_meet_link_passes_only_as_the_appointments_own_link(env, monkeypatch, value):
    """Reviewer-max: meet.google.com only when it is the appointment's own
    call link, bound by appointment_bindings(). On its own it is refused."""
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us",))
    assert gate._url_ok("zoom_link", value) is False
    assert gate._url_ok("zoom_link", value, engine_link=True) is True


@pytest.mark.parametrize("value", [REAL_ZOOM, "https://zoom.us/j/1"])
def test_zc_zoom_links_keep_the_host_rule(env, monkeypatch, value):
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us",))
    assert gate._url_ok("zoom_link", value) is True
    assert gate._url_ok("zoom_link", value, engine_link=True) is True


@pytest.mark.parametrize("value", [
    "http://meet.google.com/abc-defg-hij",                    # http
    "javascript:alert(document.cookie)",                      # not a link
    "data:text/html,hi",                                      # not a link
    "https://meet.google.com.evil.example/abc-defg-hij",      # look-alike suffix
    "https://evil.meet.google.com/abc-defg-hij",              # a subdomain: Meet is its exact host only
    "https://meetgoogle.com/abc-defg-hij",                    # another host
    "https://google.com/abc-defg-hij",                        # the parent domain
    "https://user@meet.google.com/abc-defg-hij",              # user info
    "https://meet.google.com@evil.example/abc",               # user info
    "https://meet.google.com:8443/abc-defg-hij",              # port
    "https://meet.google.com./abc-defg-hij",                  # trailing dot
    "https://evil.example/meet.google.com/abc-defg-hij",      # off-host, Meet in the path
    "https://evil.example#@meet.google.com/abc",              # host ends at the fragment
    "https://meet.google.com/abc-defg-hij.",                  # ends the sentence
    "//meet.google.com/abc-defg-hij",                         # no scheme
])
def test_zc_bad_call_links_are_refused_even_as_the_appointments_own(env, monkeypatch, value):
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us",))
    assert gate._url_ok("zoom_link", value) is False
    assert gate._url_ok("zoom_link", value, engine_link=True) is False


@pytest.mark.parametrize("kind,key", [("show_rate", "confirm_email"), ("show_rate", "reminder_24h_email"),
                                      ("show_rate", "reminder_morning_email"), ("show_rate", "reminder_1h_email"),
                                      ("no_show", "ns_still_on_email")])
def test_zc_a_meet_link_passes_only_bound_to_its_appointment(env, monkeypatch, kind, key):
    """jobs/appointments_tick hands a widget booking's Meet link over as the
    call link. It used to be held (zoom.us only) until the touch expired. Now
    it passes when bound to the appointment it came from, and only then."""
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us",))
    env.approve_ladders()
    appt = _appointment(zoom_link=MEET)
    t = _appointment_touch(kind, key, appt, START, NOW)
    assert MEET in t.body, (key, t.body)

    def verdict(bindings):
        return gate.appointment_touch_verdict(t, kind=kind, allow_terms=[FIRST, COMPANY], bindings=bindings)
    own = gate.appointment_bindings(appt, START)
    assert own["zoom_link"] == MEET
    v = verdict(own)
    assert v.allowed, (key, v.reason, v.detail)
    assert _refused(verdict(None)), key                                   # a Meet link on its own
    assert _refused(verdict({"zoom_link": MEET})), key                    # a plain binding only narrows
    # a different Meet link than the appointment's own is refused
    other = gate.appointment_bindings(_appointment(zoom_link="https://meet.google.com/zzz-yyyy-xxx"), START)
    assert _refused(verdict(other)), key
    swapped = _appointment_touch(kind, key, _appointment(zoom_link="https://meet.google.com/zzz-yyyy-xxx"),
                                 START, NOW)
    assert _refused(gate.appointment_touch_verdict(swapped, kind=kind, allow_terms=[FIRST, COMPANY],
                                                   bindings=own)), key
    # off-host and http links are refused however they are bound
    for link in ("https://evil.example/abc-defg-hij", "http://meet.google.com/abc-defg-hij"):
        bad_appt = _appointment(zoom_link=link)
        bad = _appointment_touch(kind, key, bad_appt, START, NOW)
        assert link in bad.body
        for bindings in (None, {"zoom_link": link}, gate.appointment_bindings(bad_appt, START)):
            assert _refused(gate.appointment_touch_verdict(bad, kind=kind, allow_terms=[FIRST, COMPANY],
                                                           bindings=bindings)), (key, link)
    # a Zoom link still passes on its host alone
    zoom_appt = _appointment(zoom_link=REAL_ZOOM)
    zt = _appointment_touch(kind, key, zoom_appt, START, NOW)
    for bindings in (None, gate.appointment_bindings(zoom_appt, START)):
        assert gate.appointment_touch_verdict(zt, kind=kind, allow_terms=[FIRST, COMPANY],
                                              bindings=bindings).allowed, key


def test_zc_the_dispatch_path_binds_the_appointments_own_link(env, monkeypatch):
    """show_rate.touch_bindings (what dispatch_touch hands the gate) keeps the
    engine-bound link: a Meet confirmation goes through gate_touch."""
    monkeypatch.setattr(gate, "ZOOM_HOST_SUFFIXES", ("zoom.us",))
    env.approve_ladders()
    appt = dict(_appointment(zoom_link=MEET), start_iso=START.isoformat())
    t = _appointment_touch("show_rate", "confirm_email", appt, START, NOW)
    b = show_rate.touch_bindings(t, appt)
    assert isinstance(b["zoom_link"], gate._EngineLink) and b["zoom_link"] == MEET
    assert show_rate.gate_touch(t, appt, kind="show_rate").allowed


# ---- no call link on file: the no_call_link variant, never a phrase in the link's place
@pytest.mark.parametrize("kind,key", [("show_rate", "confirm_email"), ("show_rate", "reminder_24h_email"),
                                      ("show_rate", "reminder_morning_email"), ("show_rate", "reminder_1h_email"),
                                      ("no_show", "ns_still_on_email")])
def test_zc_no_call_link_wording_conforms_and_claims_no_link(env, kind, key):
    env.approve_ladders()
    for first in (FIRST, None):
        appt = _appointment()
        appt.pop("zoom_link")
        if first is None:
            appt.pop("first_name")
        t = _appointment_touch(kind, key, appt, START, NOW)
        assert any(w in t.body for w in ("The link is on your calendar invite.",
                                         "invite is on its way with the call link.",
                                         "The link's on your calendar invite.",
                                         "The call link is on the calendar invite from when we booked.")), t.body
        assert "Zoom" not in t.body + (t.subject or "")
        assert "https://" not in t.body.replace(LINK, "")
        v = gate.appointment_touch_verdict(t, kind=kind, allow_terms=[FIRST, COMPANY])
        assert v.allowed, (key, first, v.reason, v.detail)
    # the old fallback phrase typed into the link's place is refused
    t = _appointment_touch(kind, key, _appointment(), START, NOW)
    bad = t.body.replace(ZOOM, "the Zoom link is on the calendar invite")
    assert bad != t.body
    t.body = bad
    assert _refused(gate.appointment_touch_verdict(t, kind=kind, allow_terms=[FIRST, COMPANY]))


def test_zc_every_show_rate_and_no_show_text_is_platform_neutral(env):
    """No lead-facing show-rate or no-show template says Zoom: widget bookings
    are on Google Meet."""
    idx = gate._index()
    ids = [i for i in idx if i.startswith(("show_rate.", "no_show.")) and idx[i].get("approvable")]
    assert len(ids) > 20
    for tid in ids:
        assert "Zoom" not in idx[tid]["review_text"], tid
        assert "zoom" not in idx[tid]["review_text"].replace("{zoom_link}", ""), tid


def test_zc_the_link_variants_are_catalogued():
    idx = gate._index()
    for tid in ("show_rate.reminder_24h_email", "show_rate.reminder_morning_email", "show_rate.reminder_1h_email",
                "no_show.ns_still_on_email"):
        names = [v["name"] for v in idx[tid]["variants"]]
        assert "no_call_link" in names, tid
    ce = idx["show_rate.confirm_email.cleaning_reactivation"]
    names = [v["name"] for v in ce["variants"]]
    assert {"no_call_link", "no_loom_url", "no_call_link_or_loom"} <= set(names)
    both = [v for v in ce["variants"] if v["name"] == "no_call_link_or_loom"][0]["text"]
    assert "{zoom_link}" not in both and "{loom_url}" not in both


# ---- am/pm: the gate accepts the new format and still refuses wrong times
def test_zc_times_carry_am_pm_and_a_wrong_half_is_refused_when_bound(env):
    assert show_rate.fmt_when(START) == "Tue, Jan 8 at 1:00pm CT"
    assert show_rate.fmt_when(START, pytz.timezone("America/Los_Angeles")) == "Tue, Jan 8 at 1:00pm CT (11:00am PT)"
    assert show_rate.fmt_time_only(ta._ct(2030, 1, 10, 16, 30)) == "4:30pm CT"
    assert show_rate.fmt_time_only(ta._ct(2030, 1, 10, 0, 5)) == "12:05am CT"
    assert show_rate.fmt_time_only(ta._ct(2030, 1, 10, 12, 0)) == "12:00pm CT"
    for value in ("Tue, Jan 8 at 1:00pm CT", "Tue, Jan 8 at 1:00pm CT (2:00pm ET)"):
        assert gate._time_ok("when_ct", value), value
    for value in ("Tue, Jan 8 at 1:00 CT", "Tue, Jan 8 at 1:00 CT (2:00 ET)", "Tue, Jan 8 at 1:00PM CT",
                  "Tue, Jan 8 at 1:00 pm CT", "Tue, Jan 8 at 13:00pm CT", "Tue, Jan 8 at 1:00pm CT (2:00am ET)"):
        assert gate._time_ok("when_ct", value) is False, value
    for value in ("1:00 CT", "1:00PM CT", "13:00 CT", "1:00pm ET"):
        assert gate._time_ok("time_ct", value) is False, value
    assert gate._time_ok("time_ct", "1:00pm CT")
    # the right clock with the wrong half is a real time, so the appointment's
    # own binding is what refuses it
    env.approve_ladders()
    appt = _appointment("America/New_York")
    t = _appointment_touch("show_rate", "reminder_24h_email", appt, START, NOW)
    assert "1:00pm CT (2:00pm ET)" in t.body and t.subject == "Tomorrow's call"
    bound = gate.appointment_bindings(appt, START)
    assert gate.appointment_touch_verdict(t, kind="show_rate", allow_terms=[FIRST, COMPANY], bindings=bound).allowed
    t.body = t.body.replace("1:00pm CT (2:00pm ET)", "1:00am CT (2:00am ET)")
    assert _refused(gate.appointment_touch_verdict(t, kind="show_rate", allow_terms=[FIRST, COMPANY],
                                                   bindings=bound))
