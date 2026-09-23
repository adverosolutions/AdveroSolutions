"""Copy-fix round ZA (2026-09-23): first-reply and booking wording.

One test (or parametrised set) per finding in the template copy QA: pricing
lines only from config/offers.md, the send_info / other / confirmed-time
sentences, the refused time written back in the lead's own zone, the booking
confirmations, the counter-proposals' no-time and no-alternative wordings.
Lead data is made up. No network, no live flags, no LLM (use_llm=False).
"""
import re
import types
from datetime import datetime, timedelta

import pytest
import pytz

from shared import settings
from shared import slots as slot_rules

from services.reply_engine import approval, booking, cadence
from services.reply_engine import draft as D
from services.reply_engine.classify import core_text
from services.reply_engine.models import Classification, Extracted, ReplyEvent

CT = slot_rules.TZ
NOW = CT.localize(datetime(2030, 1, 7, 9, 0))  # a Monday morning, winter (standard time everywhere)
LINK = "https://example.invalid/book"
FIRST = "Jordan"
COMPANY = "Brightline Test Co"


def _event(text="", key="cleaning_reactivation", first=FIRST, company=COMPANY):
    return ReplyEvent(email_id="za1", lead_email="lead@example.invalid", campaign_key=key, first_name=first,
                      company=company, subject="Quick question", text=text, received_at=NOW)


def _cls(label="positive_interested", **extracted):
    return Classification(label=label, extracted=Extracted(**extracted))


def _state(first=FIRST):
    return types.SimpleNamespace(first_name=first, company=COMPANY, niche="cleaning", offer="reactivation",
                                 campaign_key="cleaning_reactivation", campaign_id=None, phone=None, specialty=None,
                                 website=None, last_subject="Quick question", subject=None, thread_subject=None,
                                 lead_email="lead@example.invalid", ghl_contact_id=None, cadence={})


def _build(ev, cls, busy=None):
    return D.build_draft(ev, cls, now=NOW, booking_link=LINK, use_llm=False, already_offered=[],
                         busy_blocks=busy if busy is not None else [])


# ------------------------------------------------ items 2 and 4: pricing
def test_bookkeeping_pricing_has_no_list_size_discount():
    """offers.md gives the smaller-cut-on-a-bigger-list term to cleaning only."""
    assert D.PRICING["bookkeeping_reactivation"] == (
        "Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, "
        "and $0 if nothing closes.")


def test_recruiting_pricing_states_the_fee_once():
    assert D.PRICING["recruiting_reactivation"] == (
        "Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, "
        "and $0 if nothing closes.")


def test_only_cleaning_reactivation_quotes_the_list_size_term():
    assert [k for k, v in D.PRICING.items() if "smaller cut" in v] == ["cleaning_reactivation"]
    assert "smaller cut on bigger lists" in settings.OFFERS_MD


@pytest.mark.parametrize("key", sorted(D.PRICING))
def test_every_pricing_line_passes_the_offer_checks_for_its_own_offer(key):
    body = "Hey %s,\n\n%s\n\n%s\n\nLorenzo" % (FIRST, D.PRICING[key], D.BOOKING_LINE % LINK)
    assert D.validate_draft(body, booking_link=LINK, campaign_key=key) == []
    # every figure the line quotes is in this offer's own offers.md row
    row = [r for r in D.offer_guarantee_rows() if r["key"] == key][0]
    assert set(D._norm_dollars(D.PRICING[key])) <= row["figures"] | {"0"}, key
    assert set(D._norm_percents(D.PRICING[key])) <= row["percents"], key


# ------------------------------------------------ item 3: send_info
@pytest.mark.parametrize("company,shown", [(COMPANY, COMPANY), (None, "your business")])
def test_send_info_offers_the_walkthrough_instead_of_a_deck(company, shown):
    text = D.answer_paragraph(_event(company=company), _cls("positive_question", question_type="send_info"))
    assert text.endswith("Instead of sending a deck, I would rather walk you through it in 15 minutes and show "
                         "you what it would look like for %s." % shown)
    assert "Rather than send a deck" not in text


# ------------------------------------------------ item 28: other
@pytest.mark.parametrize("key", sorted(D.PRICING))
def test_other_answer_reads_as_one_sentence_about_the_mechanism(key):
    text = D.answer_paragraph(_event(key=key), _cls("positive_question", question_type="other"))
    assert text == "Good question. The short version is that %s The rest is easier to cover on a quick call." % (
        D.MECHANISM[key])
    assert "Happy to go through the rest" not in text


def test_as_clause_lowercases_anything_but_i():
    assert D._as_clause("I build it.") == "I build it."
    assert D._as_clause("We build it.") == "we build it."


# ------------------------------------------------ items 16 and 27: slot paragraph
def test_offered_slots_ask_for_a_15_minute_call_with_the_hyphen():
    d = _build(_event(), _cls())
    assert "work for a 15-minute call?" in d.body_text
    assert "15 minute call" not in d.body_text


def test_confirmed_time_sentence_has_no_comma_splice():
    confirmed = CT.localize(datetime(2030, 1, 8, 15, 30))
    d = _build(_event(), _cls(proposed_time=confirmed.isoformat()))
    assert ("Tue 3:30pm CT works on my end. I will send the invite over, and if anything shifts, you can grab a "
            "different time here: %s" % LINK) in d.body_text
    assert d.problems == []
    assert D.slot_paragraph([], None, confirmed=confirmed) == "Tue 3:30pm CT works on my end. I will send the invite over."


def test_referral_confirmed_time_waits_for_the_named_person_before_the_invite():
    confirmed = CT.localize(datetime(2030, 1, 8, 15, 30))
    cls = _cls("positive_referral", referral_name="Sam Rivera", proposed_time=confirmed.isoformat())
    d = _build(_event(), cls)
    assert ("Tue 3:30pm CT works on my end. Once Sam is on the thread, I will send the invite over, and if "
            "anything shifts, you can grab a different time here: %s" % LINK) in d.body_text
    assert "works on my end. I will send the invite over" not in d.body_text
    assert d.problems == []
    # no usable name: the no-name wording, grammatical
    d2 = _build(_event(), _cls("positive_referral", proposed_time=confirmed.isoformat()))
    assert "Once they are on the thread, I will send the invite over" in d2.body_text
    assert "Once them" not in d2.body_text


# ------------------------------------------------ item 5: the lead's own zone
ZONES = (
    # (label in the lead's words, pytz zone the time is written in, label written back)
    ("ET", "America/New_York", "ET"),
    ("PT", "America/Los_Angeles", "PT"),
    ("MT", "America/Denver", "MT"),
    ("MST", "America/Denver", "MT"),
    ("CT", "America/Chicago", "CT"),
    ("", "America/Chicago", "CT"),
)


def _clock(dt):
    return "%d%s" % (dt.hour % 12 or 12, "am" if dt.hour < 12 else "pm") if dt.minute == 0 else \
        "%d:%02d%s" % (dt.hour % 12 or 12, dt.minute, "am" if dt.hour < 12 else "pm")


def _lead_says(target_ct, token, zone_name, day_word=None):
    """What a lead in ``zone_name`` writes to propose ``target_ct``."""
    local = target_ct.astimezone(pytz.timezone(zone_name))
    day = day_word or local.strftime("%A")
    return ("%s %s %s works for me" % (day, _clock(local), token)).replace("  ", " ")


def _expected(target_ct, zone_name, label, dated=False):
    local = target_ct.astimezone(pytz.timezone(zone_name))
    clock = "%d:%02d%s" % (local.hour % 12 or 12, local.minute, "am" if local.hour < 12 else "pm")
    if dated:
        return "%s %s %d %s %s" % (local.strftime("%a"), local.strftime("%b"), local.day, clock, label)
    return "%s %s %s" % (local.strftime("%a"), clock, label)


def test_format_asked_time_writes_the_zone_label():
    dt = CT.localize(datetime(2030, 1, 10, 10, 0))
    assert slot_rules.format_asked_time(dt, "America/New_York") == "Thu 11:00am ET"
    assert slot_rules.format_asked_time(dt, pytz.timezone("America/Los_Angeles")) == "Thu 8:00am PT"
    assert slot_rules.format_asked_time(dt, "America/Denver") == "Thu 9:00am MT"
    assert slot_rules.format_asked_time(dt, "America/Chicago") == "Thu 10:00am CT"
    assert slot_rules.format_asked_time(dt) == "Thu 10:00am CT"
    assert slot_rules.format_asked_time(dt, "Not/AZone") == "Thu 10:00am CT"
    assert slot_rules.format_asked_time(dt, "America/New_York", dated=True) == "Thu Jan 10 11:00am ET"
    # the existing formatters are unchanged for their other callers
    assert slot_rules.format_slot(dt) == "Thu 10:00am"
    assert booking._dated_slot(dt) == "Thu Jan 10 10:00am"


@pytest.mark.parametrize("token,zone_name,label", ZONES)
def test_first_reply_refused_time_is_written_in_the_lead_zone(token, zone_name, label):
    target = CT.localize(datetime(2030, 1, 10, 10, 0))  # Thu 10:00 CT: before the 12:00 window opens
    text = _lead_says(target, token, zone_name)
    pt = slot_rules.parse_proposed_time(core_text(text), NOW)
    assert pt == target, (text, pt)
    ev, cls = _event(text=text), _cls(proposed_time=pt.isoformat())
    d = _build(ev, cls)
    want = _expected(target, zone_name, label)
    assert "\n\n%s is tough on my end. Would " % want in d.body_text, d.body_text
    assert D.first_reply_bindings(ev, cls, d)["asked_time"] == want
    assert D.asked_time_text(ev, cls) == want
    assert D.validate_draft(d.body_text, booking_link=LINK, campaign_key="cleaning_reactivation",
                            allow_terms=D.lead_terms(ev)) == []


def test_a_zone_in_the_quoted_history_is_not_the_lead_zone():
    target = CT.localize(datetime(2030, 1, 10, 10, 0))
    text = ("Thursday 10am works for me\n\nOn Mon, Jan 7, 2030 at 8:00 AM Lorenzo <lorenzo@example.invalid> wrote:\n"
            "> Would Tue 9:00am PT or Wed 10:00am PT work?")
    ev = _event(text=text)
    cls = _cls(proposed_time=slot_rules.parse_proposed_time(core_text(text), NOW).isoformat())
    assert D.lead_zone_of(ev) is None
    assert D.asked_time_text(ev, cls) == _expected(target, "America/Chicago", "CT")


# the counter cases: (status, target in CT, phrase after the time, day word or None)
COUNTER_CASES = (
    (booking.OUTSIDE_WINDOW, CT.localize(datetime(2030, 1, 10, 10, 0)), "is a touch early on my side", None),
    (booking.OUTSIDE_WINDOW, CT.localize(datetime(2030, 1, 10, 18, 0)), "is past my last slot", None),
    (booking.WEEKEND, CT.localize(datetime(2030, 1, 12, 14, 0)), "lands on a weekend for me", None),
    (booking.TOO_SOON, CT.localize(datetime(2030, 1, 7, 12, 0)), "is a little tight on my end", "today"),
    (booking.BEYOND_HORIZON, CT.localize(datetime(2030, 1, 15, 14, 0)), "is further out than I can lock in right now",
     None),
    (booking.SLOT_TAKEN, CT.localize(datetime(2030, 1, 10, 13, 0)), "just got taken on my calendar", None),
)


def _free_grid():
    """Every half hour 12:00-17:30 CT, Mon Jan 7 to Fri Jan 11 2030, except Thu 13:00 (taken)."""
    out = []
    for day in range(7, 12):
        for h in range(12, 18):
            for m in (0, 30):
                dt = CT.localize(datetime(2030, 1, day, h, m))
                if dt != CT.localize(datetime(2030, 1, 10, 13, 0)):
                    out.append(dt.isoformat())
    return out


@pytest.mark.parametrize("token,zone_name,label", ZONES)
@pytest.mark.parametrize("status,target,phrase,day_word", COUNTER_CASES)
def test_counter_refused_time_is_written_in_the_lead_zone(token, zone_name, label, status, target, phrase, day_word):
    text = _lead_says(target, token, zone_name, day_word=day_word)
    if status == booking.BEYOND_HORIZON:
        text = "next " + text
    m = booking.evaluate_reply(text, [], NOW, free_slots=_free_grid())
    assert (m.status, m.proposed) == (status, target), (text, m.to_dict())
    dated = status == booking.BEYOND_HORIZON  # the alternatives are in the week before
    want = _expected(target, zone_name, label, dated=dated)
    body = booking.counter_proposal_text(m, _state())
    assert body.startswith("Hey %s,\n\n%s %s. Could you do " % (FIRST, want, phrase)), body
    assert booking.counter_bindings(m, _state())["asked_time"] == want
    assert cadence.copy_problems(body) == []


# ------------------------------------------------ items 6 and 25: confirmations
START = CT.localize(datetime(2030, 1, 8, 15, 0))


def test_no_zoom_link_confirmation_says_the_invite_once():
    d, _ = booking._confirmation_draft(_state(), START, None, None, True)
    assert d.body_text == ("Hey Jordan,\n\nLocked in Tue 3:00pm CT. The calendar invite with the video link follows "
                           "in a separate email. I will keep it to 15 minutes.\n\nLorenzo")
    assert d.body_text.count("invite") == 1
    # the approval-side invite claim still sees it
    assert approval.claims_invite(d.body_text)
    d2, _ = booking._confirmation_draft(_state(), START, "America/New_York", None, True)
    assert "Locked in Tue 3:00pm CT (4:00pm ET your time). The calendar invite" in d2.body_text


def test_zoom_link_confirmation_puts_the_link_on_its_own_line():
    link = "https://us02web.zoom.us/j/555"
    d, _ = booking._confirmation_draft(_state(), START, None, link, True)
    assert d.body_text == ("Hey Jordan,\n\nLocked in Tue 3:00pm CT, invite on the way. Here is the Zoom link:\n%s\n\n"
                           "I will keep it to 15 minutes.\n\nLorenzo" % link)
    assert "%s I will" % link not in d.body_text
    assert approval.claims_invite(d.body_text)
    assert booking.confirmation_bindings(_state(), START, None, link)["zoom_link"] == link


# ------------------------------------------------ item 18: no readable time
@pytest.mark.parametrize("status", [booking.OUTSIDE_WINDOW, booking.WEEKEND, booking.TOO_SOON,
                                    booking.BEYOND_HORIZON, booking.SLOT_TAKEN])
def test_a_counter_without_a_time_uses_the_neutral_line(status):
    alts = [CT.localize(datetime(2030, 1, 8, 14, 0)), CT.localize(datetime(2030, 1, 9, 15, 0))]
    m = booking.BookingMatch(slot=None, status=status, proposed=None, counter_slots=alts)
    body = booking.counter_proposal_text(m, _state())
    assert body.startswith("Hey Jordan,\n\nThat time does not work on my side. Could you do Tue 2:00pm or "
                           "Wed 3:00pm CT instead?\n\n"), body
    assert "past my last slot" not in body and "\nthat time" not in body
    assert "asked_time" not in booking.counter_bindings(m, _state())


# ------------------------------------------------ item 20: no alternatives
@pytest.mark.parametrize("status", [booking.OUTSIDE_WINDOW, booking.WEEKEND, booking.TOO_SOON,
                                    booking.BEYOND_HORIZON, booking.SLOT_TAKEN, booking.WINDOW_NO_FIT])
def test_a_counter_with_no_alternative_asks_for_the_booking_link(status):
    m = booking.BookingMatch(slot=None, status=status, proposed=CT.localize(datetime(2030, 1, 10, 10, 0)),
                             counter_slots=[])
    body = booking.counter_proposal_text(m, _state())
    link = cadence.DEFAULT_BOOKING_URL
    assert "Could you grab a time that suits you here instead? %s\n\nLorenzo" % link in body, body
    assert body.count(link) == 1
    assert "any afternoon" not in body and "Or if it's easier" not in body
    assert "alt_slots" not in booking.counter_bindings(m, _state())


def test_slot_already_taken_with_no_alternative_asks_for_the_booking_link():
    res = booking._unbookable_result(_state(), START, booking.SLOT_ALREADY_TAKEN, NOW, free_slots=[])
    link = cadence.DEFAULT_BOOKING_URL
    assert res.draft.body_text == ("Hey Jordan,\n\nTue 3:00pm CT just got taken on my calendar. Could you grab a "
                                   "time that suits you here instead? %s\n\nLorenzo" % link)
    assert booking.SLOT_ALREADY_TAKEN in res.problems  # still a card, never auto-sent


def test_slot_already_taken_with_alternatives_names_both_zones():
    free = [CT.localize(datetime(2030, 1, 8, 14, 0)).isoformat(), CT.localize(datetime(2030, 1, 9, 15, 0)).isoformat()]
    res = booking._unbookable_result(_state(), START, booking.SLOT_ALREADY_TAKEN, NOW, free_slots=free)
    assert res.draft.body_text.startswith("Hey Jordan,\n\nTue 3:00pm CT just got taken on my calendar. Could you do "
                                          "Tue 2:00pm or Wed 3:00pm CT instead?\n\nOr if it's easier, grab a time here: ")


# ------------------------------------------------ item 26
def test_beyond_horizon_says_lock_in_and_window_no_fit_says_the_next_week():
    alts = [CT.localize(datetime(2030, 1, 8, 14, 0)), CT.localize(datetime(2030, 1, 9, 15, 0))]
    far = booking.BookingMatch(slot=None, status=booking.BEYOND_HORIZON,
                               proposed=CT.localize(datetime(2030, 1, 10, 14, 0)), counter_slots=alts)
    assert "Thu 2:00pm CT is further out than I can lock in right now." in booking.counter_proposal_text(far, _state())
    window = booking.BookingMatch(slot=None, status=booking.WINDOW_NO_FIT, proposed=None, counter_slots=alts)
    body = booking.counter_proposal_text(window, _state())
    assert body.startswith("Hey Jordan,\n\nNothing inside that window is open on my side in the next week. Could you "
                           "do Tue 2:00pm or Wed 3:00pm CT?\n\n")
    assert "this week" not in body


# ------------------------------------------------ every rendered body stays clean
def test_no_em_or_en_dash_anywhere_in_the_new_copy():
    texts = list(D.PRICING.values()) + [
        D.answer_paragraph(_event(), _cls("positive_question", question_type=q)) for q in ("send_info", "other")]
    for t in texts:
        assert not re.search("[–—―]", t) and "!" not in t, t
