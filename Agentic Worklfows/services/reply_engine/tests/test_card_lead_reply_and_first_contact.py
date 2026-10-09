"""The approval card shows what the lead wrote, and a card for a lead we have
not answered yet is one Lorenzo sends himself (2026-09-23).

* The lead's reply (quoted history cut, capped) is stored on the card
  (Approval.lead_reply) and shown above the draft on the email leg and a
  protected ntfy topic, never on the public topic.
* A first-contact card (approval.first_contact: the lead is not answered
  yet, any template but booking.confirmation.*) is titled "Reply to send
  yourself", starts with SEND_YOURSELF_LINE, and carries Mark sent and Veto
  (no Approve, no Edit); a tap opens Mark sent. Mark sent takes it from
  pending, records reply_sent_manually and sends nothing.

Shadow only, zero HTTP, no LLM (test_ct3_card_autosend's world fixture).
"""
from datetime import timedelta

from services.reply_engine import approval as A
from services.reply_engine.models import Draft, LeadState, ReplyEvent
from services.reply_engine.tests.test_ct3_card_autosend import (  # noqa: F401
    CAMPAIGN, COMPANY, EACCOUNT, FIRST, LEAD, NOW, OFFER, THREAD, _rows, world)

BODY = "Hey Jordan,\n\nHappy to explain on a short call. Does Tue 1:00pm or Wed 2:00pm CT work?\n\nLorenzo"
OWN_WORDS = "Sounds good, what does it cost?"
REPLY = ("%s\n\nOn Mon, Jan 7, 2030 at 9:00 AM Lorenzo <%s> wrote:\n> Hey Jordan, quick question about your "
         "follow-ups.\n> Lorenzo" % (OWN_WORDS, EACCOUNT))
QUOTED = "quick question about your follow-ups"


def _recorder():
    sent = []

    def fn(title, message, **kw):
        sent.append({"title": title, "message": message, "kw": kw})
        return {"sent": True, "test": True}

    return sent, fn


def _raise(world, answered, tid=None, text=REPLY, requested=None, email_id="lr-1"):
    """One card as create_approval raises it (no verdict), and its pushes."""
    st = world["store"]
    ev = ReplyEvent(email_id=email_id, thread_id=THREAD, campaign_id=CAMPAIGN, campaign_key=OFFER,
                    eaccount=EACCOUNT, lead_email=LEAD, first_name=FIRST, company=COMPANY,
                    subject="Quick question", text=text, received_at=NOW)
    state = LeadState.from_store(st.get("lead:%s:%s" % (CAMPAIGN, LEAD)), ev)
    if answered:
        state.history.append({"event": "reply_sent", "at": (NOW - timedelta(days=1)).isoformat()})
    d = Draft(subject="Re: Quick question", body_text=BODY, label="positive_question", template_id=tid)
    sent, fn = _recorder()
    card = A.create_approval(state, d, ev, store=st, now=NOW, notify_fn=fn, campaign_key=OFFER, requested=requested)
    state.processed_email_ids.append(email_id)
    st.set(state.key, state.to_store())
    assert len(sent) == 1
    return card, sent[0]


def _labels(push):
    return [a[0] for a in push["kw"]["actions"]]


def _protected(monkeypatch):
    monkeypatch.setenv("NTFY_TOKEN", "unit-token-not-real")


# ======================================================== the lead's reply
def test_the_lead_reply_is_above_the_draft_on_the_email_leg_and_never_on_the_public_topic(world):
    card, push = _raise(world, answered=True)
    assert card.lead_reply == OWN_WORDS                      # quoted history cut
    # public topic: redacted exactly as before, no lead text, name or company
    assert push["title"] == "Reply to approve: positive question"
    for text in (push["title"], push["message"]):
        for private in (OWN_WORDS, FIRST, COMPANY, LEAD, "They wrote", BODY):
            assert private not in text, private
    email = push["kw"]["email_message"]
    assert "They wrote:\n%s\n\n----------\nYour reply (Approve sends it):\n%s" % (OWN_WORDS, BODY) in email
    assert QUOTED not in email


def test_the_lead_reply_is_on_a_protected_topic(world, monkeypatch):
    _protected(monkeypatch)
    card, push = _raise(world, answered=True)
    assert "email_message" not in push["kw"]
    message = push["message"]
    assert message.index("They wrote:\n" + OWN_WORDS) < message.index("Your reply (Approve sends it):") < message.index(BODY)


def test_a_long_reply_is_capped_and_the_cut_is_marked(world):
    card, push = _raise(world, answered=True, text="word " * 1000)
    assert card.lead_reply.endswith(A.LEAD_REPLY_CUT)
    assert len(card.lead_reply) <= A.LEAD_REPLY_MAX_CHARS + len(A.LEAD_REPLY_CUT)
    assert A.LEAD_REPLY_CUT.strip() in push["kw"]["email_message"]


def test_an_old_card_with_no_lead_reply_still_loads_and_pushes(world, monkeypatch):
    _protected(monkeypatch)
    card, _ = _raise(world, answered=True)
    st = world["store"]
    key = A.APPROVAL_PREFIX + A._approval_id(card)
    raw = st.get(key)
    raw.pop("lead_reply")
    st.set(key, raw)
    old = A.load(card.token, st)
    assert old is not None and old.lead_reply is None
    sent, fn = _recorder()
    A.push_card(old, st, None, notify_fn=fn)
    assert "They wrote" not in sent[0]["message"] and "Your reply" not in sent[0]["message"]
    assert sent[0]["message"].endswith("\n\n" + BODY)
    assert _labels(sent[0]) == ["Approve", "Veto", "Edit"]


# ====================================================== first-contact cards
FIRST_CONTACT_CARD = (
    "Send this yourself from the thread in Instantly, then tap Mark sent.\n"
    "Jordan Brightline Test Co <owner@example.com>\n"
    "Reply to: owner@example.com\n"
    "Subject: Re: Quick question\n"
    "Slots: none\n"
    "\n"
    "They wrote:\n"
    "Sounds good, what does it cost?\n"
    "\n"
    "----------\n"
    "Your reply, to send yourself from the thread:\n" + BODY)

ANSWERED_CARD = (
    "Jordan Brightline Test Co <owner@example.com>\n"
    "Reply to: owner@example.com\n"
    "Subject: Re: Quick question\n"
    "Slots: none\n"
    "\n"
    "They wrote:\n"
    "Sounds good, what does it cost?\n"
    "\n"
    "----------\n"
    "Your reply (Approve sends it):\n" + BODY)


def test_a_first_contact_card_is_one_lorenzo_sends_himself(world, monkeypatch):
    _protected(monkeypatch)
    card, push = _raise(world, answered=False)
    assert push["title"] == "Reply to send yourself: %s %s (positive_question)" % (FIRST, COMPANY)
    assert push["message"] == FIRST_CONTACT_CARD
    mark = "https://engine.test/mark-sent/%s" % card.token
    assert push["kw"]["actions"] == [("Mark sent", mark), ("Veto", "https://engine.test/veto/%s" % card.token)]
    assert push["kw"]["click"] == mark


def test_a_first_contact_card_on_the_public_topic_names_no_one(world):
    card, push = _raise(world, answered=False, tid="booking.counter.window_no_fit")
    assert push["title"] == "Reply to send yourself: positive question"
    assert push["message"].startswith(A.SEND_YOURSELF_LINE + "\n" + A._not_auto_sent(A.FIRST_REPLY_LOCK_REASON))
    for private in (OWN_WORDS, FIRST, COMPANY, LEAD, BODY, "http"):
        assert private not in push["title"] and private not in push["message"], private
    assert "They wrote:\n" + OWN_WORDS in push["kw"]["email_message"]
    assert _labels(push) == ["Mark sent", "Veto"]


def test_a_first_contact_card_keeps_book_as_asked(world):
    card, push = _raise(world, answered=False, requested={"slot": "2030-01-08T09:00:00-06:00",
                                                          "status": "outside_window"})
    assert _labels(push)[:2] == ["Mark sent", "Veto"] and _labels(push)[2].startswith("Book ")


def test_a_card_for_an_answered_lead_is_unchanged(world, monkeypatch):
    _protected(monkeypatch)
    card, push = _raise(world, answered=True)
    assert push["title"] == "Reply to approve: %s %s (positive_question)" % (FIRST, COMPANY)
    assert push["message"] == ANSWERED_CARD
    assert _labels(push) == ["Approve", "Veto", "Edit"]
    assert push["kw"]["click"] == "https://engine.test/approve/%s" % card.token


def test_a_first_contact_booking_confirmation_card_is_unchanged(world, monkeypatch):
    _protected(monkeypatch)
    card, push = _raise(world, answered=False, tid="booking.confirmation.zoom_link")
    assert push["title"].startswith("Reply to approve: ")
    assert not push["message"].startswith(A.SEND_YOURSELF_LINE)
    assert _labels(push) == ["Approve", "Veto", "Edit"]


# ======================================================= Mark sent from pending
def test_mark_sent_takes_a_pending_first_contact_card_and_sends_nothing(world):
    card, _ = _raise(world, answered=False)
    st = world["store"]
    assert A.mark_sent_takes(card, st) is True
    out = A.mark_sent_manually(card.token, NOW + timedelta(minutes=5), store=st)
    assert out["ok"] is True and out["status"] == "sent_manually" and out["from_status"] == "pending"
    assert out["first_reply"] is True and out["invite"] is None
    assert world["inst"].sent == []                                        # nothing sent
    stored = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    assert stored["status"] == "sent_manually" and stored["notify_result"][A.MARK_SENT_KEY]["from"] == "pending"
    row = st.get(card.state_key)
    assert row["history"][-1]["event"] == "reply_sent_manually"
    # the lock releases: the lead is answered now
    assert A.first_contact(None, row) is False
    assert A.draft_only("booking.counter.window_no_fit", row) is False
    assert [r["from_status"] for r in _rows(world, "sent_manually")] == ["pending"]


def test_mark_sent_refuses_a_pending_card_for_an_answered_lead(world):
    card, _ = _raise(world, answered=True)
    st = world["store"]
    assert A.mark_sent_takes(card, st) is False
    out = A.mark_sent_manually(card.token, NOW + timedelta(minutes=5), store=st)
    assert out["ok"] is False and out["status"] == "pending" and "send_failed" in out["error"]
    assert st.get(A.APPROVAL_PREFIX + A._approval_id(card))["status"] == "pending"
    assert _rows(world, "sent_manually") == []
