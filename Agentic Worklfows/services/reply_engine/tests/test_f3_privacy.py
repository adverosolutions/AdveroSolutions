"""F3 privacy follow-ups: nothing that names a lead reaches a stranger.

1. GET /cadence/resume/<campaign>/<email> (the R6 recipient-hold and CT3
   template-hold Resume page) verifies the same signed token its POST
   verifies before it renders anything about the lead. A missing, forged,
   expired or other-lead token, and a lead with no state, get one neutral
   403 page with no address, name or company. A valid token renders the
   page as before.
2. An ordinary approval card on a public ntfy topic (no NTFY_TOKEN /
   NTFY_ALLOW_SENSITIVE) is titled by its classification only and its push
   carries no name, company, address, subject or body; the email leg keeps
   the full card. A protected topic gets today's card unchanged. The
   5-minute chase moves the thread's subject (which often carries the
   lead's first name) to the email leg on a public topic too.

Every name, company and address here is made up. Nothing leaves the
process: the notify function is a recorder and the app runs under
TestClient in shadow mode.
"""
from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytest
import pytz
from fastapi.testclient import TestClient

from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine.models import Draft, LeadState, ReplyEvent

CT = pytz.timezone("America/Chicago")
CAMPAIGN = "00000000-f3f3-4f3f-8f3f-000000000f3f"
LEAD = "marlowe.q@brightpath-test.example"
OTHER = "someone.else@brightpath-test.example"
FIRST = "Marlowe"
COMPANY = "Brightpath Test Roofing"
SUBJECT = "Re: Marlowe, question"
BODY = "Hi Marlowe,\n\nHappy to walk you through pricing on a short call.\n\nLorenzo"
PRIVATE = (LEAD, FIRST, COMPANY, "Brightpath", "marlowe")


def ct(*args):
    return CT.localize(datetime(*args))


NOW = ct(2026, 9, 22, 13, 0)


@pytest.fixture
def world(tmp_env, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret-f3")
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    store = JsonFileStore(tmp_env / "store.json")
    app_mod.configure(store=store, clock=lambda: NOW)
    try:
        yield {"store": store, "client": TestClient(app_mod.app)}
    finally:
        app_mod.configure()


# ================================================= 1. the resume GET page
def _stopped_state(store, reason="recipient_unconfirmed", email=LEAD):
    state = LeadState(lead_email=email, campaign_id=CAMPAIGN, status="positive_interested", first_name=FIRST,
                      company=COMPANY, eaccount="sender@advero-test.example", thread_id="thr-f3",
                      last_email_id="e-f3", last_subject=SUBJECT)
    state = cadence.arm(state, ct(2026, 9, 21, 16, 0))
    cadence.stop(state, reason, ct(2026, 9, 22, 12, 0))
    if reason == "template_unapproved":
        state.cadence["template_hold"] = {"day": 3, "template_id": "cadence.e3", "ids": ["cadence.e3"],
                                          "reason": "unapproved"}
    store.set(state.key, state.to_store())
    return state


def _path(email=LEAD, token=None):
    path = "/cadence/resume/%s/%s" % (CAMPAIGN, email)
    return "%s?%s" % (path, urlencode({"t": token})) if token is not None else path


def _no_lead_data(page):
    text = page.text
    assert not [p for p in PRIVATE if p in text], text
    assert "Resume" not in text and "<form" not in text


def test_resume_get_with_a_valid_token_renders_the_recipient_hold_page_as_before(world):
    state = _stopped_state(world["store"])
    token = cadence.make_decision_token("resume", state, NOW)
    page = world["client"].get(_path(token=token))
    assert page.status_code == 200
    assert "Resume the follow-ups?" in page.text and "Nothing is sent from this page." in page.text
    assert "confirmed as %s&#x27;s" % LEAD in page.text
    assert "<form method='post'" in page.text and "t=" in page.text
    # a GET changes nothing
    assert world["store"].get(state.key)["cadence"]["stopped_reason"] == "recipient_unconfirmed"


def test_resume_get_with_a_valid_token_renders_the_template_hold_page_as_before(world):
    state = _stopped_state(world["store"], reason="template_unapproved")
    token = cadence.make_decision_token("resume", state, NOW)
    page = world["client"].get(_path(token=token))
    assert page.status_code == 200 and "Resume the follow-ups?" in page.text and "cadence.e3" in page.text


@pytest.mark.parametrize("reason", ["recipient_unconfirmed", "template_unapproved"])
@pytest.mark.parametrize("case", ["missing", "empty", "forged", "expired", "other_kind", "other_lead"])
def test_resume_get_without_a_valid_token_shows_no_lead_data(world, case, reason):
    state = _stopped_state(world["store"], reason=reason)
    other = _stopped_state(world["store"], email=OTHER)
    token = {
        "missing": None,
        "empty": "",
        "forged": "2026-09-30T00:00:00-05:00.deadbeefdeadbeefdeadbeefdeadbeef",
        "expired": cadence.make_decision_token("resume", state, NOW - timedelta(days=10), ttl_hours=1),
        "other_kind": cadence.make_decision_token("veto", state, NOW),
        "other_lead": cadence.make_decision_token("resume", other, NOW),
    }[case]
    page = world["client"].get(_path(token=token))
    assert page.status_code == 403
    assert "not signed for this lead, or it has expired" in page.text
    _no_lead_data(page)
    assert world["store"].get(state.key)["cadence"]["stopped_reason"] == reason


def test_resume_get_for_a_lead_with_no_state_is_the_same_neutral_page(world):
    """No state: nothing to verify a token against, and the page must not
    say whether the lead exists (the 404 echoed the store key)."""
    _stopped_state(world["store"])
    page = world["client"].get(_path(email="nobody@brightpath-test.example", token="x.y"))
    assert page.status_code == 403 and "not signed for this lead" in page.text
    assert "nobody" not in page.text and "lead:" not in page.text


def test_resume_post_for_a_lead_with_no_state_is_the_same_neutral_403_as_a_bad_token(world):
    """The POST used to answer 404 "No state at lead:..." before checking the
    token, which said whether the lead exists and echoed the store key."""
    state = _stopped_state(world["store"])
    unknown = world["client"].post(_path(email="nobody@brightpath-test.example", token="x.y"))
    bad = world["client"].post(_path(token="x.y"))
    assert unknown.status_code == bad.status_code == 403
    assert unknown.text == bad.text
    assert "not signed for this lead, or it has expired" in unknown.text
    assert "nobody" not in unknown.text and "lead:" not in unknown.text
    assert world["store"].get(state.key)["cadence"]["stopped_reason"] == "recipient_unconfirmed"


def test_resume_post_with_a_valid_token_still_resumes(world):
    state = _stopped_state(world["store"])
    token = cadence.make_decision_token("resume", state, NOW)
    page = world["client"].post(_path(token=token))
    assert page.status_code == 200 and "Resumed" in page.text
    assert not world["store"].get(state.key)["cadence"].get("stopped_reason")


def test_resume_get_with_no_signing_secret_is_refused_like_the_post(world, monkeypatch):
    state = _stopped_state(world["store"])
    token = cadence.make_decision_token("resume", state, NOW)
    monkeypatch.delenv("REPLY_ENGINE_SECRET")
    page = world["client"].get(_path(token=token))
    assert page.status_code == 403
    _no_lead_data(page)


# ================================================== 2. the card push
def _card(store, recorder, label="positive_question", requested=None):
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name=FIRST, company=COMPANY)
    event = ReplyEvent(email_id="e-f3", thread_id="thr-f3", campaign_id=CAMPAIGN,
                       eaccount="sender@advero-test.example", lead_email=LEAD, first_name=FIRST, company=COMPANY,
                       subject=SUBJECT, text="How much is it?", received_at=ct(2026, 9, 22, 9, 55))
    draft = Draft(subject=SUBJECT, body_text=BODY, label=label)
    return A.create_approval(state, draft, event, store=store, now=ct(2026, 9, 22, 10, 0), notify_fn=recorder,
                             requested=requested)


def _recorder():
    sent = []

    def fn(title, message, **kw):
        sent.append({"title": title, "message": message, "kw": kw})
        return {"sent": True, "test": True}

    return sent, fn


def _assert_public(push):
    for text in (push["title"], push["message"]):
        assert not [p for p in PRIVATE + (SUBJECT, "pricing on a short call", "http") if p in text], text


def test_public_topic_card_names_no_one_and_the_email_leg_has_the_full_card(world):
    sent, fn = _recorder()
    card = _card(world["store"], fn)
    assert len(sent) == 1
    push = sent[0]
    assert push["title"] == "Reply to approve: positive question"
    _assert_public(push)
    assert "The card, with its links, is in the email." in push["message"]
    email = push["kw"]["email_message"]
    for detail in (FIRST, COMPANY, LEAD, "Subject: %s" % SUBJECT, BODY):
        assert detail in email
    # the buttons still reach the email leg (shared.notify lists them there)
    labels = [a[0] for a in push["kw"]["actions"]]
    assert labels == ["Approve", "Veto", "Edit"]
    assert push["kw"]["click"] == "https://engine.test/approve/%s" % card.token


def test_public_topic_card_with_a_requested_time_still_names_no_one(world):
    sent, fn = _recorder()
    _card(world["store"], fn, requested={"slot": "2026-09-24T09:00:00-05:00", "status": "outside_window"})
    push = sent[0]
    _assert_public(push)
    assert "Book as asked is on the card." in push["message"]
    assert "Book as asked: https://engine.test/accept/" in push["kw"]["email_message"]


def test_public_topic_card_through_the_real_notify_records_no_name(world):
    """NOTIFY=off records what would go out: the ntfy text names no one,
    the email body does."""
    from shared import notify

    notify.reset_for_tests()
    _card(world["store"], None)
    rec = [r for r in notify.sent_in_test if r["title"].startswith("Reply to approve")]
    assert len(rec) == 1
    _assert_public(rec[0])
    assert FIRST in rec[0]["email_message"] and COMPANY in rec[0]["email_message"]


@pytest.mark.parametrize("protect", [("NTFY_TOKEN", "unit-token-not-real"), ("NTFY_ALLOW_SENSITIVE", "1")])
def test_protected_topic_card_is_unchanged(world, monkeypatch, protect):
    monkeypatch.setenv(*protect)
    sent, fn = _recorder()
    card = _card(world["store"], fn)
    push = sent[0]
    assert push["title"] == "Reply to approve: %s %s (positive_question)" % (FIRST, COMPANY)
    assert push["message"] == "%s %s <%s>\nReply to: %s\nSubject: %s\nSlots: none\n\n%s" % (
        FIRST, COMPANY, LEAD, LEAD, SUBJECT, BODY)
    assert "email_message" not in push["kw"]
    assert push["kw"]["click"] == "https://engine.test/approve/%s" % card.token


def test_the_chase_moves_the_subject_to_the_email_leg_on_a_public_topic(world):
    _card(world["store"], _recorder()[1])
    sent, fn = _recorder()
    out = A.escalate_pending(store=world["store"], now=ct(2026, 9, 22, 10, 20), notify_fn=fn)
    assert out and len(sent) == 1
    push = sent[0]
    assert "Subject:" not in push["message"] and FIRST not in push["message"] and FIRST not in push["title"]
    assert "Subject: %s" % SUBJECT in push["kw"]["email_message"]


def test_the_chase_on_a_protected_topic_is_unchanged(world, monkeypatch):
    monkeypatch.setenv("NTFY_TOKEN", "unit-token-not-real")
    _card(world["store"], _recorder()[1])
    sent, fn = _recorder()
    A.escalate_pending(store=world["store"], now=ct(2026, 9, 22, 10, 20), notify_fn=fn)
    assert "Subject: %s" % SUBJECT in sent[0]["message"] and "email_message" not in sent[0]["kw"]
