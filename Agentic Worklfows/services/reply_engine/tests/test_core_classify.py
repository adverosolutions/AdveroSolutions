"""Classification of the 44 recorded replies + quote stripping + extraction."""
import json
from datetime import datetime
from pathlib import Path

import pytest
import pytz

from shared import llm

from services.reply_engine import classify as C
from services.reply_engine.models import RULE_ONLY_LABELS, ReplyEvent

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES = json.loads((FIXTURES / "instantly_replies_2026-09.json").read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")

# (from_address_email, timestamp prefix) -> expected label(s)
EXPECTED = {
    ("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42"): "positive_question",
    ("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37"): "positive_interested",
    ("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T23:17"): "positive_interested",
    ("info@shiningarmorcleaningnj.com", "2026-09-18T15:08"): "positive_interested",
    ("info@shiningarmorcleaningnj.com", "2026-09-18T15:25"): "positive_interested",
    ("info@shiningarmorcleaningnj.com", "2026-09-21T19:00"): "positive_interested",
    ("rob@cjsglobal.com", "2026-09-15T22:58"): "positive_question",
    ("rob@cjsglobal.com", "2026-09-16T04:39"): "positive_interested",
    ("tiffany@flowerhillfs.com", "2026-09-17T12:53"): "positive_question",
    ("ignacio@ariacleaningservices.com", ""): "negative_notnow",
    ("pam@butterflystaffing.com", ""): "negative_notnow",
    ("gary.kaufman@excellisearch.com", ""): "negative_notfit",
    ("tim.isacco@siprosearch.com", ""): "negative_notfit",
    ("chris.kushmaul@millicare.com", ""): "negative_notfit",
    ("buck@cgavery.com", ""): "unsubscribe",
    ("loniskey@wowwindowcleaners.com", ""): "unsubscribe",
    ("lewis@freightappointments.com", ""): "unsubscribe",
    ("ron.daniels@siteforce.us", ""): "negative_hostile",
    ("maggie@northwestsnowremoval.com", ""): "negative_hostile",
    ("dvent@intraview.io", ""): "negative_hostile",
    ("eva@rbgjanitorial.com", ""): "auto_reply_unmonitored",
    ("adrian@goforward.com", ""): "auto_reply_unmonitored",
}
AUTO_OR_OOO = {
    "updates@transactional.getinboxzero.com", "conner@sdcleanco.com", "boris.musheyev@borismtax.com", "amanda@sienna-consulting.com",
    "info@theaugustacpa.com", "smonohan@cfscorp.net", "dayers@atwork.com", "leslie@theellemgroup.com",
}
OOO_SUBJECT_PREFIXES = ("Automatic reply", "Out of Office", "Out Of Office", "I'm currently out of the office", "Out of the office")
RETURN_DATES = {
    "jkohl@kohlbm.com": "2026-09-22",
    "ashley@amaofficesolutions.com": "2026-09-22",
    "cecily.welch@cecilywelchcpa.com": "2026-09-21",
    "vania@abscomm.com": "2026-09-21",
}


def expected_for(item):
    key = (item["from_address_email"], item["timestamp_created"][:16])
    exp = EXPECTED.get(key) or EXPECTED.get((item["from_address_email"], ""))
    if exp is not None:
        return {exp}
    if item["from_address_email"] in AUTO_OR_OOO:
        return {"auto_reply_unmonitored", "ooo"}
    if item["subject"].startswith(OOO_SUBJECT_PREFIXES):
        return {"ooo"}
    raise AssertionError("no expectation for %s" % item["from_address_email"])


@pytest.fixture
def llm_calls():
    """Count LLM calls by wrapping the offline fakes; restores them afterwards."""
    calls = []
    orig_c, orig_e = C.offline_classify, C.offline_escalate
    llm.register_fake("classify", lambda s, u, j: (calls.append(("classify", u)) or orig_c(s, u, j)))
    llm.register_fake("escalate", lambda s, u, j: (calls.append(("escalate", u)) or orig_e(s, u, j)))
    yield calls
    C.install_offline_fakes()


def event_of(item, lead=None):
    return ReplyEvent.from_poller_item(item, lead=lead)


# ------------------------------------------------------------ the 44
@pytest.mark.parametrize("item", REPLIES, ids=[r["from_address_email"] + "@" + r["timestamp_created"][:16] for r in REPLIES])
def test_each_fixture_reply_gets_expected_label(item, llm_calls):
    result = C.classify(event_of(item))
    assert result.label in expected_for(item), (item["from_address_email"], result.label, result.reason)
    if result.label in RULE_ONLY_LABELS:
        assert result.method == "rule"
        assert llm_calls == [], "LLM must not be called for %s" % result.label


def test_all_44_summary(llm_calls):
    labels = {}
    for item in REPLIES:
        res = C.classify(event_of(item))
        labels[res.label] = labels.get(res.label, 0) + 1
    assert sum(labels.values()) == 44
    assert labels["ooo"] == 17
    assert labels["auto_reply_unmonitored"] == 7
    assert labels["unsubscribe"] == 3
    assert labels["negative_hostile"] == 3
    assert labels["negative_notfit"] == 3
    assert labels["negative_notnow"] == 2
    assert labels["positive_question"] == 3
    assert labels["positive_interested"] == 6
    # rule-only labels never touched the LLM; the rest at most one classify (+ optional escalate) each
    assert all(role in ("classify", "escalate") for role, _ in llm_calls)
    assert len([1 for role, _ in llm_calls if role == "classify"]) <= 44 - 31


def test_rule_layer_never_calls_llm_for_unsub_hostile_ooo_auto(llm_calls):
    for item in REPLIES:
        res = C.classify(event_of(item))
        if res.label in RULE_ONLY_LABELS:
            assert llm_calls == []
        del llm_calls[:]


def test_llm_never_sees_quoted_cold_email(llm_calls):
    for item in REPLIES:
        C.classify(event_of(item))
    for _, user in llm_calls:
        assert "$150M" not in user and "150M" not in user, "quoted cold email leaked into the LLM prompt"
        assert "wrote:" not in user
        assert "Original Message" not in user


def test_return_dates_extracted():
    for item in REPLIES:
        email = item["from_address_email"]
        if email in RETURN_DATES:
            res = C.classify(event_of(item))
            assert res.label == "ooo"
            assert res.extracted.return_date == RETURN_DATES[email], email


# ------------------------------------------------------- quote stripping
def test_strip_quoted_markers():
    assert C.strip_quoted("Remove\n\n-----Original Message-----\nFrom: Lorenzo\nHey Buck, $150M") == "Remove"
    assert C.strip_quoted("What is the upfront cost?\n________________________________\nFrom: Lorenzo <x@y.com>\nHey") == "What is the upfront cost?"
    assert C.strip_quoted("Sure Monday at 2\n\n> On Sep 18, 2026, at 11:19 AM, Lorenzo wrote:\n> Hey Ilmi") == "Sure Monday at 2"
    assert C.strip_quoted("Hello\n\nOn 21.09.2026 07:20, Lorenzo Villarreal wrote:\n\n> Hey Sopio") == "Hello"
    assert C.strip_quoted("tell me more?\n\nRob\n\nFrom: Lorenzo Villarreal\nSent: Monday") == "tell me more?\n\nRob"
    zoho = "Thx\n\n ---- On Wed, 16 Sep 2026 04:29:47 -0700  lorenzov@adveromedia.com wrote ----\n\n Hey Ignacio"
    assert C.strip_quoted(zoho) == "Thx"
    assert C.strip_quoted("> only quoted\n> lines") == ""


def test_core_text_drops_signature():
    text = "No not really.  We only do a placement or two a month.\nThanks\nTim Isacco\n919-523-7356"
    assert C.core_text(text) == "No not really.  We only do a placement or two a month."


# ------------------------------------------------------------ extraction
def _find(email, ts_prefix):
    for r in REPLIES:
        if r["from_address_email"] == email and r["timestamp_created"].startswith(ts_prefix):
            return r
    raise KeyError(email)


def test_extracts_phone_and_proposed_time_ct():
    res = C.classify(event_of(_find("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T17:37")))
    assert res.label == "positive_interested"
    assert res.extracted.phone == "237-791-5700"
    assert res.extracted.proposed_time == "2026-09-24T15:00:00-05:00"  # Thu 4pm Eastern -> 3pm CT


def test_extracts_availability_window_eastern():
    res = C.classify(event_of(_find("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T23:17")))
    assert res.extracted.availability_window == {"start_hour": 15, "end_hour": 18, "tz": "America/New_York"}
    assert res.extracted.proposed_time is None


def test_extracts_rob_friday_2pm_est_and_ilmi_wed_1130():
    rob = C.classify(event_of(_find("rob@cjsglobal.com", "2026-09-16T04:39")))
    assert rob.extracted.proposed_time == "2026-09-18T13:00:00-05:00"
    ilmi = C.classify(event_of(_find("info@shiningarmorcleaningnj.com", "2026-09-21T19:00")))
    assert ilmi.extracted.proposed_time == "2026-09-23T11:30:00-05:00"
    ilmi2 = C.classify(event_of(_find("info@shiningarmorcleaningnj.com", "2026-09-18T15:25")))
    assert ilmi2.extracted.proposed_time == "2026-09-21T14:00:00-05:00"


def test_question_types():
    assert C.classify(event_of(_find("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42"))).extracted.question_type == "pricing"
    assert C.classify(event_of(_find("tiffany@flowerhillfs.com", "2026-09-17"))).extracted.question_type == "pricing"
    assert C.classify(event_of(_find("rob@cjsglobal.com", "2026-09-15T22:58"))).extracted.question_type == "mechanism"


def test_notnow_follow_up_dates():
    ignacio = C.classify(event_of(_find("ignacio@ariacleaningservices.com", "2026")))
    assert ignacio.extracted.follow_up_date == "2026-10-16"  # "touch base next month" -> +30 days
    received = CT.localize(datetime(2026, 9, 21, 10, 0))
    assert C.parse_follow_up_date("try me again in 2 weeks", received) == "2026-10-05"
    assert C.parse_follow_up_date("maybe next quarter", received) == "2026-12-20"
    assert C.parse_follow_up_date("not right now", received) == "2026-10-21"


def test_hostile_flags_remove_request_for_blocklist():
    ron = C.classify(event_of(_find("ron.daniels@siteforce.us", "2026")))
    assert ron.label == "negative_hostile"
    assert ron.extracted.remove_request is True


def test_referral_and_wrong_person_extraction():
    base = _find("rob@cjsglobal.com", "2026-09-15T22:58")
    ref = dict(base, text="Not me, talk to Dustin Landeis, he runs sales here.")
    res = C.classify(event_of(ref))
    assert res.label == "positive_referral"
    assert res.extracted.referral_name == "Dustin Landeis"
    wrong = dict(base, text="I no longer work here. Please contact Gary for anything sales related.")
    res2 = C.classify(event_of(wrong))
    assert res2.label == "wrong_person"
    assert res2.extracted.referral_name == "Gary"


# ------------------------------------------------------------- LLM tier
def test_low_confidence_escalates_to_sonnet_role():
    calls = []
    llm.register_fake("classify", lambda s, u, j: (calls.append("classify") or {"label": "neutral_question", "confidence": 0.4, "reason": "hmm"}))
    llm.register_fake("escalate", lambda s, u, j: (calls.append("escalate") or {"label": "positive_question", "confidence": 0.9, "reason": "pricing", "question_type": "pricing"}))
    try:
        res = C.classify(event_of(_find("tiffany@flowerhillfs.com", "2026-09-17")))
    finally:
        C.install_offline_fakes()
    assert calls == ["classify", "escalate"]
    assert res.label == "positive_question" and res.method == "escalate"
    assert "first pass: neutral_question 0.40" in res.reason


def test_confident_classify_does_not_escalate():
    calls = []
    llm.register_fake("classify", lambda s, u, j: (calls.append("classify") or {"label": "positive_question", "confidence": 0.95, "reason": "ok"}))
    llm.register_fake("escalate", lambda s, u, j: (calls.append("escalate") or {}))
    try:
        res = C.classify(event_of(_find("tiffany@flowerhillfs.com", "2026-09-17")))
    finally:
        C.install_offline_fakes()
    assert calls == ["classify"]
    assert res.method == "llm" and res.model == llm.model_for("classify")


def test_llm_failure_falls_back_to_human_review():
    def boom(s, u, j):
        raise RuntimeError("api down")

    llm.register_fake("classify", boom)
    llm.register_fake("escalate", boom)
    try:
        res = C.classify(event_of(_find("tiffany@flowerhillfs.com", "2026-09-17")))
    finally:
        C.install_offline_fakes()
    assert res.label == "neutral_question" and res.method == "fallback" and res.confidence == 0.0


def test_unknown_llm_label_is_rejected_then_escalated():
    llm.register_fake("classify", lambda s, u, j: {"label": "banana", "confidence": 0.99})
    llm.register_fake("escalate", lambda s, u, j: {"label": "negative_notfit", "confidence": 0.9, "reason": "no"})
    try:
        res = C.classify(event_of(_find("tiffany@flowerhillfs.com", "2026-09-17")))
    finally:
        C.install_offline_fakes()
    assert res.label == "negative_notfit" and res.method == "escalate"


def test_first_name_recovered_from_subject_when_lead_unknown():
    ev = event_of(_find("sopiosvanishvili@taxfoaccounting.com", "2026-09-21T14:42"))
    assert ev.first_name == "Sopio"
    assert ev.campaign_key == "bookkeeping_reactivation" and ev.niche == "bookkeeping" and ev.offer == "reactivation"


# ------------------------------------------- regressions: replies that were lost
def _plain(text, subject="Re: Pat, question"):
    return ReplyEvent(email_id="t", lead_email="pat@example.com", subject=subject, text=text,
                      received_at=CT.localize(datetime(2026, 9, 21, 15, 30)))


def test_thank_you_for_reaching_out_subject_with_a_human_body_is_not_an_auto_reply():
    """AUTO_SUBJECT_RE used to decide on the subject alone, with no body evidence:
    router.route() then filed the reply under the deliverability monitor and
    returned, so it got no GHL contact, no draft, no card and no trace."""
    res = C.classify(_plain("Yes I am interested. How much does this cost?", subject="Thank you for reaching out"))
    assert res.label == "positive_question"
    res2 = C.classify(_plain("Yes I am interested. How much does this cost?", subject="Re: Thank you for your email"))
    assert res2.label == "positive_question"


def test_auto_reply_subject_with_an_empty_body_is_still_auto_reply():
    assert C.classify(_plain("", subject="Thank you for reaching out")).label == "auto_reply_unmonitored"
    assert C.classify(_plain("Automatic reply from the office.", subject="Automatic reply: Pat, question")).label == "ooo"


@pytest.mark.parametrize("text,expected", [
    ("Yes this is interesting. Quick question first, am I talking to a bot or a real person?", "positive_interested"),
    ("Are you a bot or a real person?", "neutral_question"),
    ("Damn, that is a good pitch. Send me pricing and we can talk Thursday.", "positive_question"),
    ("Interested but I have to ask, this is not a scam is it? How much does it cost?", "positive_question"),
    ("Sure, please stop by the office Thursday at 2 and we can walk through it.", "positive_interested"),
    ("Yes lets set something up.\nPat Miller | BotCo | bot@example.com", "positive_interested"),
])
def test_a_reply_with_a_trigger_word_is_never_blocklisted(text, expected):
    """R2/R3 read the signature-bearing text and had no positive-cue guard, so a
    single keyword ('bot', 'damn', 'scam', 'please stop') destroyed a positive
    reply: blocklist + DND, no draft, no card, no notification of the decision."""
    res = C.classify(_plain(text))
    assert res.label == expected
    assert res.label not in ("negative_hostile", "unsubscribe")


def test_real_hostility_and_real_opt_outs_still_route_to_the_blocklist():
    assert C.classify(_plain("This is a scam, remove me")).label == "negative_hostile"
    assert C.classify(_plain("Remove me from your list")).label == "unsubscribe"
    assert C.classify(_plain("Stop emailing me")).label == "unsubscribe"
    assert C.classify(_plain("For the love of god leave me alone")).label == "negative_hostile"


def test_a_signoff_line_that_carries_the_answer_is_not_cut():
    """core_text cut at any line starting Thanks/Best/Regards, so a one-line
    reply that opened with 'Thanks,' was deleted before classification."""
    assert C.core_text("Hi Lorenzo,\nThanks, Tuesday at 2pm works for me.\n\nIlmi").startswith("Hi Lorenzo,\nThanks, Tuesday at 2pm")
    assert "what is the pricing?" in C.core_text("Hi Lorenzo,\nThanks, what is the pricing?")
    assert "Tell me more." in C.core_text("Hello,\nThanks! Tell me more.")
    # a genuine signature block is still removed
    assert C.core_text("No not really.  We only do a placement or two a month.\nThanks\nTim Isacco\n919-523-7356") == \
        "No not really.  We only do a placement or two a month."
    res = C.classify(_plain("Hi Lorenzo,\nThanks, Tuesday at 2pm works for me.\n\nIlmi"))
    assert res.label == "positive_interested" and res.extracted.proposed_time == "2026-09-22T14:00:00-05:00"


# ------------------------------------ polite refusals are not hostility
@pytest.mark.parametrize("text,expected", [
    # R2 ran before R4 and HOSTILE_RE still carried the bare alternatives
    # `absolutely not` and `never work with`, so an ordinary refusal was graded
    # negative_hostile 0.97 and fired the irreversible workspace-wide Instantly
    # blocklist plus GHL DND/Lost, which the lead cannot undo.
    ("Absolutely not at this time, budget is frozen until January.", "negative_notnow"),
    ("Absolutely not right now, ask me again after the holidays.", "negative_notnow"),
])
def test_a_polite_timing_refusal_is_never_blocklisted(text, expected):
    res = C.classify(_plain(text))
    assert res.label == expected, (text, res.label, res.reason)


def test_never_work_with_a_vendor_we_have_not_met_is_not_hostility():
    """An invitation to come by the office is not an insult."""
    res = C.classify(_plain("We would never work with a vendor we have not met. Come by the office sometime."))
    assert res.label not in ("negative_hostile", "unsubscribe"), (res.label, res.reason)
    assert not C.HOSTILE_RE.search("we would never work with a vendor we have not met")
    assert not C.HOSTILE_RE.search("absolutely not at this time")


def test_a_timing_objection_carrying_a_hostile_word_still_goes_to_follow_up():
    """The second belt: R2 cannot grade a "not now" hostile unless the lead also
    asked to be removed."""
    assert C._is_timing_objection("not right now, maybe next quarter") is True
    assert C._is_timing_objection("remove me, not right now or ever") is False
    assert C._is_timing_objection("this is a scam") is False


# ---------------------------------------------- the lead's own "On ... wrote"
def test_a_reply_whose_own_words_say_wrote_is_not_emptied():
    """_QUOTE_CUT_RE made the colon optional and matched under re.S, so an
    attribution could span the lead's own sentences: the body was cut to
    nothing, classify() took the empty branch (neutral_question, confidence 0.0,
    method 'fallback'), the pricing question never reached question_type_for and
    router's GHL note carried none of the lead's words."""
    body = "On your site I saw what you wrote about commercial accounts.\nWhat does this cost?\n\nThanks,\nIlmi"
    assert C.strip_quoted(body).startswith("On your site I saw what you wrote")
    assert "What does this cost?" in C.core_text(body)
    res = C.classify(_plain(body))
    assert res.method != "fallback" and res.confidence > 0.0
    assert res.extracted.question_type == "pricing"
    # a real quote header is still cut
    quoted = "Sounds good.\n\nOn Sep 18, 2026, at 7:18 AM, Lorenzo Villarreal <l@x.com> wrote:\n> Hey there"
    assert C.strip_quoted(quoted) == "Sounds good."


# ------------------------------------------------------ LLM_FAKE truthiness
def test_llm_fake_true_installs_the_offline_stand_ins(monkeypatch):
    """offline_fakes_wanted() compared LLM_FAKE to the exact string "1" while
    shared.llm.is_fake() accepts true/yes/on, so LLM_FAKE=true turned fake mode
    on but left the stand-ins uninstalled and shared.llm's generic default
    answered positive_interested 0.95 to everything - a fabricated positive that
    is indistinguishable from a real Haiku answer."""
    probe = _plain("Who is this and why are you writing to our general mailbox")
    for spelling in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("LLM_FAKE", spelling)
        llm.clear_fakes()
        assert C.offline_fakes_wanted() is True, spelling
        res = C.classify(probe)
        assert res.label == "neutral_question", (spelling, res.label)
        assert res.label != "positive_interested"
    monkeypatch.setenv("LLM_FAKE", "1")
    C.install_offline_fakes()
