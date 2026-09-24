"""Draft building and validation (offers.md rules, slots, threading)."""
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytz

from shared import llm, settings
from shared.ghl import GHL

from services.reply_engine import classify as C
from services.reply_engine import draft as D
from services.reply_engine.models import Classification, Extracted, LeadState, ReplyEvent

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES = json.loads((FIXTURES / "instantly_replies_2026-09.json").read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")
NOW = CT.localize(datetime(2026, 9, 21, 21, 10))  # Monday evening
BOOKING = settings.BOOKING_URL


def _find(email, ts_prefix):
    for r in REPLIES:
        if r["from_address_email"] == email and r["timestamp_created"].startswith(ts_prefix):
            return r
    raise KeyError(email)


def event(email, ts_prefix, **over):
    item = dict(_find(email, ts_prefix), **over)
    return ReplyEvent.from_poller_item(item)


# ------------------------------------------------------------ validation
def test_validate_rejects_banned_content():
    good = "Hey Sopio,\n\nNothing up front, $0 if nothing closes.\n\nWould Tue 2:00pm or Thu 3:30pm CT work?\n\nLorenzo"
    assert D.validate_draft(good, booking_link=BOOKING) == []
    assert "em or en dash" in D.validate_draft(good.replace(",", " —"), booking_link=BOOKING)
    assert "exclamation mark" in D.validate_draft(good.replace("Hey Sopio,", "Hey Sopio!"), booking_link=BOOKING)
    assert "mentions AI" in D.validate_draft(good.replace("Nothing", "Our AI does it. Nothing"), booking_link=BOOKING)
    assert "mentions automation" in D.validate_draft(good.replace("Nothing", "The automation runs. Nothing"), booking_link=BOOKING)
    probs = D.validate_draft(good.replace("$0", "$5,000"), booking_link=BOOKING)
    assert any("dollar figure $5000" in p for p in probs)
    assert "must end with the signature line 'Lorenzo'" in D.validate_draft(good + "\nSent from my phone", booking_link=BOOKING)
    assert D.validate_draft("") == ["empty body"]


def test_validate_flags_a_booking_link():
    """No email carries a booking link (2026-09-23): the passed link, the
    configured BOOKING_URL or the words "grab a time" are all a problem."""
    base = "Hey Sopio,\n\nWould Tue 2:00pm or Thu 3:30pm CT work?%s\n\nLorenzo"
    link = "https://cal.example/x"
    assert D.validate_draft(base % "", booking_link=link, first_reply=True) == []
    assert "contains a booking link" in D.validate_draft(base % (" " + link), booking_link=link, first_reply=True)
    assert "contains a booking link" in D.validate_draft(base % " Or grab a time here.", first_reply=True)
    if BOOKING:
        assert "contains a booking link" in D.validate_draft(base % (" " + BOOKING), first_reply=True)



INVENTED_LINKS = (
    "Or book a time here: https://calendly.com/lorenzo-advero",
    "Or use my calendar: https://api.leadconnectorhq.com/widget/booking/xyz",
    "Or pick a slot here: [booking link]",
)


@pytest.mark.parametrize("line", INVENTED_LINKS + (
    "Or here: calendly.com/lorenzo",
    "More at www.adverosolutions.com",
    "Details: [link]",
    "Book: <booking_link>",
    "Book: {booking_url}",
    "Here is my calendar link.",
))
def test_first_reply_flags_any_invented_link(line):
    """Any URL, link placeholder or booking wording is flagged in a first
    reply, not only the configured BOOKING_URL."""
    body = "Hey Sopio,\n\nWould Tue 2:00pm or Thu 3:30pm CT work?\n\n%s\n\nLorenzo" % line
    assert "contains a booking link" in D.validate_draft(body, first_reply=True)


def test_first_reply_link_check_skips_the_lead_company():
    body = "Hey Sopio,\n\nHappy to walk through it for Acme.io.\n\nWould Tue 2:00pm or Thu 3:30pm CT work?\n\nLorenzo"
    assert D.validate_draft(body, first_reply=True, allow_terms=["Acme.io"]) == []


def test_every_catalogue_first_reply_passes_the_link_check():
    """No first-reply template text (main body or any variant) trips the
    widened check, so it cannot block a legitimate first reply."""
    from services.reply_engine import template_approvals as TA

    entries = [e for e in TA.catalogue() if e["kind"] in ("first_reply", "first_reply_piece")]
    assert any(e["kind"] == "first_reply" for e in entries)
    checked = 0
    for e in entries:
        for text in [e["text"]] + [v.get("text", "") for v in e.get("variants") or []]:
            if text:
                assert not D._has_booking_link(text), (e["id"], text)
                checked += 1
    assert checked > len(entries)


def test_draft_prompt_carries_no_booking_link_instruction():
    prompt = (D.PROMPTS_DIR / "draft_system.md").read_text(encoding="utf-8")
    assert "booking link line" not in prompt
    assert "other than the booking link" not in prompt
    assert "No links of any kind" in prompt
    assert "Nobody in the office has to remember to ask." in prompt  # the no-Claudeisms rule

def test_no_slots_first_reply_asks_for_times():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    para = D.slot_paragraph([], "https://cal.example/x")
    assert para.endswith("Could you send me a couple of times that work for you next week?")
    assert "cal.example" not in para
    assert D.slot_paragraph([], None, for_person="Sam").endswith(
        "Could you send me a couple of times that work for Sam next week?")
    assert D.validate_draft(D.skeleton(ev, cls, [], "https://cal.example/x"), booking_link="https://cal.example/x",
                            first_reply=True) == []


def test_dollar_figures_from_offers_are_allowed():
    allowed = D.allowed_dollar_figures()
    for fig in ("0", "24000", "15000", "40000", "200", "2500", "5000"):
        assert fig in allowed
    body = "Hey,\n\nThe guarantee is $24,000 a year or your money back plus a $200 gift card.\n\nLorenzo"
    assert D.validate_draft(body) == []
    assert D.validate_draft(body.replace("$24,000", "$24k")) == []
    assert D.validate_draft(body.replace("$24,000", "$25,000")) != []


def test_every_template_answer_passes_validation():
    for key in D.PRICING:
        for text in (D.PRICING[key], D.MECHANISM[key], D.MINIMUM[key]):
            assert D.validate_draft("Hey,\n\n%s\n\nLorenzo" % text) == [], (key, text)


# ------------------------------------------------------------ templates
def test_pricing_question_draft_is_sendable_in_fake_mode():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert d.sendable and d.problems == []
    assert d.subject == "Re: Sopio, question"
    assert d.body_text.startswith("Hey Sopio,")
    assert "20 to 30 percent of first-year fees" in d.body_text
    assert "$0 if nothing closes" in d.body_text
    assert len(d.offered_slots) == 2
    assert BOOKING not in d.body_text and "grab a time" not in d.body_text.lower()
    assert d.body_text.split("\n\n")[-2].endswith("work for a 15-minute call?")
    assert d.body_text.rstrip().endswith("\nLorenzo")
    assert d.model == "template"
    for iso in d.offered_slots:
        dt = datetime.fromisoformat(iso)
        assert dt.weekday() < 5 and 12 <= dt.hour < 18
        assert (dt - ev.received_at).total_seconds() >= 4 * 3600


def test_outbound_pricing_uses_guarantee_from_offers():
    ev = event("tiffany@flowerhillfs.com", "2026-09-17")
    cls = C.classify(ev)
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert ev.campaign_key == "cleaning_trigger"
    assert "$24,000 a year in new cleaning contracts signed within 90 days" in d.body_text
    assert "retainer" in d.body_text
    assert d.problems == []


def test_mechanism_and_send_info_answers():
    ev = event("rob@cjsglobal.com", "2026-09-15T22:58")
    cls = C.classify(ev)
    assert cls.extracted.question_type == "mechanism"
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert "email and text sequences" in d.body_text and "60 or more" in d.body_text
    cls2 = Classification(label="positive_question", extracted=Extracted(question_type="send_info"))
    d2 = D.build_draft(ev, cls2, now=ev.received_at, busy_blocks=[])
    assert "Instead of sending a deck, I would rather walk you through it" in d2.body_text and d2.problems == []


def test_referral_draft_names_the_person():
    ev = event("rob@cjsglobal.com", "2026-09-15T22:58")
    cls = Classification(label="positive_referral", extracted=Extracted(referral_name="Dustin"))
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert "pointing me to Dustin" in d.body_text and "looping Dustin in" in d.body_text
    assert d.problems == []


def test_proposed_time_inside_rules_is_confirmed():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37")
    cls = C.classify(ev)
    assert cls.extracted.proposed_time == "2026-09-24T15:00:00-05:00"
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert d.offered_slots == ["2026-09-24T15:00:00-05:00"]
    assert "Thu 3:00pm CT works on my end" in d.body_text
    assert BOOKING not in d.body_text and d.problems == []


def test_proposed_time_before_noon_gets_two_alternatives():
    ev = event("info@shiningarmorcleaningnj.com", "2026-09-21T19:00")
    cls = C.classify(ev)
    assert cls.extracted.proposed_time == "2026-09-23T11:30:00-05:00"
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert len(d.offered_slots) == 2
    assert "Wed 11:30am CT is tough on my end." in d.body_text
    assert all(datetime.fromisoformat(s).hour >= 12 for s in d.offered_slots)


def test_proposed_time_held_by_another_lead_is_not_confirmed_but_own_offer_is():
    ev = event("info@shiningarmorcleaningnj.com", "2026-09-18T15:25")  # Monday at 2 CTS -> 2026-09-21T14:00 CT
    cls = C.classify(ev)
    taken = ["2026-09-21T14:00:00-05:00"]
    d_other = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], already_offered=taken, others_offered=taken)
    assert d_other.offered_slots != taken and len(d_other.offered_slots) == 2
    d_own = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], already_offered=taken, others_offered=[])
    assert d_own.offered_slots == taken


def test_availability_window_narrows_slots():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T23:17")  # 3-6pm Eastern daily
    cls = C.classify(ev)
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert len(d.offered_slots) == 2
    for iso in d.offered_slots:
        assert 14 <= datetime.fromisoformat(iso).hour < 17  # 3-6pm ET == 2-5pm CT


def test_already_offered_slots_are_never_reoffered_and_days_differ():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    first = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    second = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], already_offered=first.offered_slots)
    assert not set(first.offered_slots) & set(second.offered_slots)
    for d in (first, second):
        a, b = (datetime.fromisoformat(x) for x in d.offered_slots)
        assert a.date() != b.date()


def test_state_offered_slots_are_excluded():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    base = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    state = LeadState(lead_email=ev.lead_email, campaign_id=ev.campaign_id, offered_slots=list(base.offered_slots))
    again = D.build_draft(ev, cls, state=state, now=ev.received_at, busy_blocks=[])
    assert not set(base.offered_slots) & set(again.offered_slots)


# ---------------------------------------------------------------- slots
def test_fallback_slots_respect_open_hours_weekends_and_busy_blocks():
    now = CT.localize(datetime(2026, 9, 25, 9, 0))  # Friday morning
    busy = [("2026-09-28T14:00:00-05:00", "2026-09-28T14:30:00-05:00")]
    raw = D.fallback_free_slots(now, busy_blocks=busy)
    dts = [datetime.fromisoformat(x) for x in raw]
    assert dts, "no slots generated"
    assert all(d.weekday() < 5 for d in dts)
    assert all(12 <= d.hour < 18 for d in dts)
    monday = [d for d in dts if d.date().isoformat() == "2026-09-28"]
    hours = {(d.hour, d.minute) for d in monday}
    assert (14, 0) not in hours and (14, 30) not in hours and (13, 30) not in hours  # 15 min buffer each side
    assert (15, 0) in hours and (12, 0) in hours


def test_pick_two_varied_prefers_mid_afternoon_and_different_times():
    now = CT.localize(datetime(2026, 9, 21, 21, 10))
    from shared import slots as S

    cands = S.candidate_slots(D.fallback_free_slots(now, busy_blocks=[]), now)
    two = D.pick_two_varied(cands)
    assert len(two) == 2 and two[0].date() < two[1].date()
    assert two[0].hour == 14
    assert (two[0].hour, two[0].minute) != (two[1].hour, two[1].minute)


def test_ghl_free_slots_are_used_when_token_present():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET" and "/calendars/GDugwLmZNdsD13RBDnRu/free-slots" in str(request.url)
        return httpx.Response(200, json={
            "2026-09-22": {"slots": ["2026-09-22T15:00:00-05:00", "2026-09-22T16:30:00-05:00"]},
            "2026-09-24": {"slots": ["2026-09-24T13:00:00-05:00"]},
            "traceId": "x",
        })

    ghl = GHL(token="tok", transport=httpx.MockTransport(handler))
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    d = D.build_draft(ev, cls, ghl=ghl, now=ev.received_at, busy_blocks=[])
    assert len(calls) == 1
    assert d.offered_slots == ["2026-09-22T15:00:00-05:00", "2026-09-24T13:00:00-05:00"]
    assert "slots from ghl" in d.rationale


def test_ghl_without_token_falls_back_without_http():
    def handler(request):
        raise AssertionError("no HTTP allowed without a token")

    ghl = GHL(token=None, transport=httpx.MockTransport(handler))
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    d = D.build_draft(ev, C.classify(ev), ghl=ghl, now=ev.received_at, busy_blocks=[])
    assert len(d.offered_slots) == 2 and "slots from fallback" in d.rationale


def test_parse_ghl_free_slots_shapes():
    assert D.parse_ghl_free_slots({"slots": ["a", "b"]}) == ["a", "b"]
    assert D.parse_ghl_free_slots({"2026-09-22": {"slots": ["a"]}, "traceId": "t"}) == ["a"]
    assert D.parse_ghl_free_slots(["a"]) == ["a"]
    assert D.parse_ghl_free_slots(None) == []


# ------------------------------------------------------------ threading
def test_reply_subject_threads_without_double_re():
    assert D.reply_subject("Sopio, question") == "Re: Sopio, question"
    assert D.reply_subject("Re: Sopio, question") == "Re: Sopio, question"
    assert D.reply_subject("RE: Re: EXT: Chris, question") == "Re: Chris, question"
    assert D.reply_subject("") == "Re: your reply"


# -------------------------------------------------------------- LLM path
def test_llm_polish_rejected_falls_back_to_template():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    llm.register_fake("draft", lambda s, u, j: "Hey Sopio!\n\nOur AI automation handles it for $999.\n\nLorenzo")
    try:
        d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], use_llm=True)
    finally:
        llm.clear_fakes()
        C.install_offline_fakes()
    assert d.model == "template" and d.problems == []
    assert "LLM draft rejected" in d.rationale and "exclamation mark" in d.rationale



def test_llm_polish_with_an_invented_link_falls_back_to_template():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    template = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], use_llm=False)
    assert template.problems == []
    body = template.body_text.rstrip()
    assert body.endswith("\nLorenzo")
    linked = body[:-len("Lorenzo")] + "Or book a time here: https://calendly.com/x\n\nLorenzo"
    llm.register_fake("draft", lambda s, u, j: linked)
    try:
        d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], use_llm=True)
    finally:
        llm.clear_fakes()
        C.install_offline_fakes()
    assert d.model == "template" and d.problems == []
    assert d.body_text == template.body_text
    assert "calendly" not in d.body_text
    assert "LLM draft rejected" in d.rationale and "contains a booking link" in d.rationale

def test_llm_polish_accepted_when_it_keeps_slots_and_rules():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    seen = {}

    def polish(system, user, json_mode):
        seen["system"] = system
        skel = system.split("Skeleton for this reply")[1]
        return skel.split(":", 1)[1].split("Return only the email body")[0].strip().replace("Nothing up front.", "Nothing up front at all.")

    llm.register_fake("draft", polish)
    try:
        d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], use_llm=True)
    finally:
        llm.clear_fakes()
        C.install_offline_fakes()
    assert d.model == llm.model_for("draft") and d.problems == []
    assert "Nothing up front at all." in d.body_text
    assert "20–30%" in seen["system"]  # offers.md embedded at runtime
    assert "polished by" in d.rationale


# --------------------------------------------- copy rules the validator missed
def test_validate_rejects_automatically_automating_and_en_dashes():
    """_BANNED ended the automation pattern in \\b, which fails on the letter
    after 'automat(ic)', and only U+2014 counted as a dash, while
    cadence.copy_problems already rejected U+2013."""
    for body in ("We set this up so it runs automatically in the background.",
                 "I am automating the whole follow up for you.",
                 "Our machine learning model picks the times.",
                 "Booked for Tue 2:00pm – 2:15 CT."):
        problems = D.validate_draft(body + "\n\nLorenzo")
        assert problems, body
    assert "mentions automation" in D.validate_draft("It runs automatically.\n\nLorenzo")
    assert "mentions automation" in D.validate_draft("I am automating it.\n\nLorenzo")
    assert "mentions machine learning" in D.validate_draft("Our machine learning model picks the times.\n\nLorenzo")
    assert "em or en dash" in D.validate_draft("Tue 2:00pm – 2:15 CT.\n\nLorenzo")
    assert "em or en dash" in D.validate_draft("Tue 2:00pm — 2:15 CT.\n\nLorenzo")
    # the ordinary template copy is still clean
    good = "Hey Sopio,\n\nNothing up front, $0 if nothing closes.\n\nWould Tue 2:00pm or Thu 3:30pm CT work?\n\nLorenzo"
    assert D.validate_draft(good, booking_link=BOOKING) == []


REACTIVATION_PROOF = ("I built a similar system for a commercial roofer doing $150M/year. "
                      "I recovered about $6M worth of contracts within 6 months.")
OUTBOUND_PROOF = ("I recently implemented the same system for a commercial roofer doing $150M/yr "
                  "and generated about $180,000 in new contracts in 90 days.")


def test_validate_rejects_the_other_offer_types_proof_line():
    """offers.md heads the proof table 'one per offer type, never mixed', but the
    validator checked dollar figures as one flat set, so either proof line
    passed clean inside either kind of draft."""
    trigger = "Hey Tiffany,\n\n%s\n\nLorenzo" % REACTIVATION_PROOF
    problems = D.validate_draft(trigger, campaign_key="cleaning_trigger")
    assert any("never mixed" in p for p in problems), problems
    assert D.validate_draft(trigger, campaign_key="cleaning_reactivation") == []

    reactivation = "Hey Tim,\n\n%s\n\nLorenzo" % OUTBOUND_PROOF
    problems2 = D.validate_draft(reactivation, campaign_key="cleaning_reactivation")
    assert any("never mixed" in p for p in problems2), problems2
    assert D.validate_draft(reactivation, campaign_key="recruiting_outbound") == []

    # a paraphrase that only carries the other type's figure is caught too
    paraphrased = "Hey Tiffany,\n\nI recovered about $6M worth of contracts for a roofer.\n\nLorenzo"
    assert any("$6000000" in p and "Reactivation" in p for p in D.validate_draft(paraphrased, campaign_key="cleaning_trigger"))
    # with no campaign key the check is skipped, so every existing caller is unaffected
    assert D.validate_draft(paraphrased) == []


GUARANTEES = {
    "cleaning_trigger": "$24,000 a year in new cleaning contracts signed within 90 days",
    "bookkeeping_trigger": "$15,000 in new annual client fees within 90 days",
    "recruiting_outbound": "$40,000 in new placement fees within 180 days",
}


def test_validate_rejects_another_offers_guarantee_figure():
    """validate_draft cross-checked only the offers.md proof table, never the
    six-offers guarantee table. In production build_draft calls Sonnet with the
    whole of offers.md in the system prompt - all six guarantees side by side -
    so a model that swapped the number promised a commercial-cleaning prospect
    the bookkeeping guarantee in writing, and every check passed: the figure
    exists somewhere in the file, and it is not in the proof table."""
    bookkeeping_number = ("Hey Tiffany,\n\nSetup plus a monthly retainer, sized to your service area, and the "
                          "guarantee covers it: %s or your money back plus a $200 gift card.\n\nLorenzo"
                          % GUARANTEES["bookkeeping_trigger"])
    problems = D.validate_draft(bookkeeping_number, campaign_key="cleaning_trigger")
    assert problems and any("$15000" in p and "bookkeeping_trigger" in p for p in problems), problems

    # the campaign's own guarantee still validates clean
    own = ("Hey Tiffany,\n\nThe guarantee is %s or your money back plus a $200 gift card.\n\nLorenzo"
           % GUARANTEES["cleaning_trigger"])
    assert D.validate_draft(own, campaign_key="cleaning_trigger") == []

    # a reactivation lead may not be handed an outbound guarantee either
    recruiting_number = "Hey Tim,\n\nWe guarantee %s.\n\nLorenzo" % GUARANTEES["recruiting_outbound"]
    probs2 = D.validate_draft(recruiting_number, campaign_key="bookkeeping_reactivation")
    assert probs2 and any("$40000" in p for p in probs2), probs2

    # with no campaign key the check is skipped, so every existing caller is unaffected
    assert D.validate_draft(bookkeeping_number) == []


def test_every_template_pricing_answer_passes_its_own_guarantee_check():
    for key in D.PRICING:
        body = "Hey,\n\n%s\n\nLorenzo" % D.PRICING[key]
        assert D.validate_draft(body, campaign_key=key) == [], (key, D.validate_draft(body, campaign_key=key))


# ------------------------------------------------ the prospect's own name
def test_a_company_name_containing_a_banned_word_does_not_block_the_draft():
    """draft._BANNED includes automat\\w* and answer_paragraph interpolates
    event.company, so a lead at "Automated Building Services" - an ordinary
    commercial-cleaning name - produced a permanently unsendable draft. approve
    then returned {'ok': False, 'status': 'blocked'} with no 'error' key, and the
    page rendered "unknown"."""
    body = ("Hey Pat,\n\nInstead of sending a deck, I would rather walk you through it in 15 minutes and show you "
            "what it would look like for Automated Building Services.\n\nLorenzo")
    assert "mentions automation" in D.validate_draft(body)
    assert D.validate_draft(body, allow_terms=["Automated Building Services"]) == []
    # the guard itself is untouched: our own copy still cannot say it
    ours = body.replace("walk you through it", "automate it for you")
    assert "mentions automation" in D.validate_draft(ours, allow_terms=["Automated Building Services"])
    # and the draft for such a lead is sendable end to end
    ev = event("rob@cjsglobal.com", "2026-09-15T22:58", subject="Re: Pat, question")
    ev.company = "Automated Building Services"
    cls = Classification(label="positive_question", extracted=Extracted(question_type="send_info"))
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert "Automated Building Services" in d.body_text
    assert d.problems == [], d.problems


# -------------------------------------------------------- referral wording
def test_referral_draft_offers_the_slots_for_the_named_person():
    """offers.md rule 5: thank, ask for the intro, offer the same two slots FOR
    X. The draft asked the person who had just said "not me" to take the call,
    and repeated the full name twice in one sentence."""
    ev = event("rob@cjsglobal.com", "2026-09-15T22:58")
    cls = Classification(label="positive_referral", extracted=Extracted(referral_name="Dustin Landeis"))
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert "pointing me to Dustin Landeis" in d.body_text
    assert "looping Dustin in" in d.body_text            # first name on the second mention
    assert "looping Dustin Landeis in" not in d.body_text
    assert "work for a 15-minute call" not in d.body_text
    assert "work for Dustin?" in d.body_text
    assert d.problems == []
    # no name at all: "them", never a guessed pronoun
    cls2 = Classification(label="positive_referral", extracted=Extracted())
    d2 = D.build_draft(ev, cls2, now=ev.received_at, busy_blocks=[])
    assert "work for them?" in d2.body_text
    # an ordinary positive reply is unchanged
    d3 = D.build_draft(ev, C.classify(ev), now=ev.received_at, busy_blocks=[])
    assert "work for a 15-minute call" in d3.body_text


def test_referral_with_no_name_or_a_role_phrase_uses_the_no_name_wording():
    """CT3 copy bug: with no referral name the draft rendered "looping the in",
    and a role phrase ("talk to The Manager") rendered "looping The in". A
    referral name is written only when it reads as a person's name."""
    ev = event("rob@cjsglobal.com", "2026-09-15T22:58")
    for extracted in (Extracted(), Extracted(referral_name=""), Extracted(referral_name="The Manager"),
                      Extracted(referral_name="our office manager"), Extracted(referral_name="the owner")):
        cls = Classification(label="positive_referral", extracted=extracted)
        d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
        assert "Appreciate you pointing me to the right person." in d.body_text, extracted
        assert "looping them in on this thread" in d.body_text, extracted
        assert "work for them?" in d.body_text, extracted
        assert "looping the in" not in d.body_text and "looping The in" not in d.body_text
        assert "The Manager" not in d.body_text
        assert d.problems == []
    # a person's name is still written
    cls = Classification(label="positive_referral", extracted=Extracted(referral_name="  Dana   Reyes "))
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    assert "pointing me to Dana Reyes." in d.body_text and "looping Dana in" in d.body_text
    assert "work for Dana?" in d.body_text


def test_first_reply_branch_order_matches_the_answer_paragraph():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cases = (
        (Classification(label="positive_referral", extracted=Extracted(question_type="pricing")), "referral",
         "Appreciate you pointing me to"),
        (Classification(label="positive_question", extracted=Extracted(question_type="pricing")), "pricing",
         D.PRICING[D._key(ev)]),
        (Classification(label="positive_question", extracted=Extracted(question_type="send_info")), "send_info",
         "Instead of sending a deck, I would rather"),
        (Classification(label="positive_question", extracted=Extracted(question_type="mechanism")), "mechanism",
         D.MINIMUM[D._key(ev)]),
        (Classification(label="positive_question", extracted=Extracted(question_type="other")), "other",
         "Good question."),
        (Classification(label="neutral_question", extracted=Extracted()), "other", "Good question."),
        (Classification(label="positive_interested", extracted=Extracted()), "default", "Glad to hear it."),
    )
    for cls, branch, text in cases:
        assert D.first_reply_branch(cls) == branch
        assert text in D.answer_paragraph(ev, cls)
        assert D.first_reply_template_id(ev, cls) == "first_reply.%s.%s.full" % (D._key(ev), branch)


def test_first_reply_template_id_is_none_for_an_unmapped_campaign():
    """Flag 1: _key falls back to cleaning_reactivation, so an unmapped
    campaign must never pick (and auto-send) the cleaning template."""
    cls = Classification(label="positive_interested", extracted=Extracted())
    base = dict(email_id="t1", lead_email="lead@example.invalid", received_at=NOW, text="")
    unmapped = (
        ReplyEvent(**base),                                                    # nothing mapped
        ReplyEvent(campaign_key="hvac_reactivation", **base),                 # not an offers.md key
        ReplyEvent(niche="cleaning", **base),                                 # no offer
        ReplyEvent(offer="reactivation", **base),                             # no niche
        ReplyEvent(niche="plumbing", offer="reactivation", **base),           # no such offer
        ReplyEvent(niche="cleaning", offer="mystery", **base),                # unknown offer kind
        ReplyEvent(campaign_key="hvac_x", niche="cleaning", offer="reactivation", **base),
    )
    for ev in unmapped:
        assert D._key(ev) in D.PRICING  # the draft still has copy
        assert D.first_reply_template_id(ev, cls) is None, ev
        assert D.build_draft(ev, cls, now=NOW, busy_blocks=[], use_llm=False).template_id is None
    mapped = (
        (ReplyEvent(campaign_key="bookkeeping_trigger", **base), "bookkeeping_trigger"),
        (ReplyEvent(niche="cleaning", offer="reactivation", **base), "cleaning_reactivation"),
        (ReplyEvent(niche="recruiting", offer="outbound", **base), "recruiting_outbound"),
    )
    for ev, key in mapped:
        assert D.first_reply_template_id(ev, cls) == "first_reply.%s.default.full" % key
    # an explicit key must be the one the draft renders
    ev = ReplyEvent(campaign_key="bookkeeping_trigger", **base)
    assert D.first_reply_template_id(ev, cls, campaign_key="cleaning_reactivation") is None
    assert D.first_reply_template_id(ev, cls, campaign_key="bookkeeping_trigger") is not None


def test_build_draft_sets_the_template_id_only_for_the_template_render():
    ev = event("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42")
    cls = C.classify(ev)
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], use_llm=False)
    assert d.model == "template" and d.template_id == D.first_reply_template_id(ev, cls)
    assert d.template_hash is None  # stamped by the pipeline, never by the builder

    def polish(system, user, json_mode):
        skel = system.split("Skeleton for this reply")[1]
        return skel.split(":", 1)[1].split("Return only the email body")[0].strip().replace(
            "Nothing up front.", "Nothing up front at all.")
    llm.register_fake("draft", polish)
    try:
        polished = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[], use_llm=True)
    finally:
        llm.clear_fakes()
        C.install_offline_fakes()
    assert polished.model != "template" and polished.template_id is None


def test_first_reply_bindings_are_the_rendered_values():
    ev = event("rob@cjsglobal.com", "2026-09-15T22:58")
    cls = Classification(label="positive_referral", extracted=Extracted(referral_name="Dana Reyes"))
    d = D.build_draft(ev, cls, now=ev.received_at, busy_blocks=[])
    b = D.first_reply_bindings(ev, cls, d)
    assert b["referral_name"] == "Dana Reyes" and b["referral_first_name"] == "Dana"
    assert "booking_url" not in b and d.booking_link is None  # no link in any email
    assert b["slots"] in d.body_text and ("Hey %s," % b["first_name"]) in d.body_text
    assert None not in b.values()
    # no referral name written: no referral binding
    cls2 = Classification(label="positive_referral", extracted=Extracted(referral_name="The Manager"))
    b2 = D.first_reply_bindings(ev, cls2, D.build_draft(ev, cls2, now=ev.received_at, busy_blocks=[]))
    assert "referral_name" not in b2 and "referral_first_name" not in b2
