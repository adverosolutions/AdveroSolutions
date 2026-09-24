"""A first-contact card whose reply the thread check already found
(cadence.detect_manual_first_reply wrote ``reply_sent_manually`` with
``source: "thread"`` on the lead row) is closed, never sent again.

* approval.mark_answered_in_thread closes the pending card (sent_manually,
  marked_sent by "thread"), keeps its held times, leaves the lead row alone,
  sends and pushes nothing; a second call, or a closed card, is a no-op.
* Mark sent on such a card closes it without a second reply_sent_manually.
* approve() / send_approved() refuse it: already_answered_in_thread.
* _arm_under_lock never re-arms a ladder already running for this card's
  own inbound (armed_for_email_id), as the thread check arms it.

Shadow only, zero HTTP, no LLM (test_ct3_card_autosend's world fixture).
"""
from datetime import timedelta

from shared import notify
from services.reply_engine import approval as A
from services.reply_engine import cadence as C
from services.reply_engine.models import Draft, LeadState, ReplyEvent
from services.reply_engine.tests.test_card_lead_reply_and_first_contact import BODY, REPLY, _recorder
from services.reply_engine.tests.test_ct3_card_autosend import (  # noqa: F401
    CAMPAIGN, COMPANY, EACCOUNT, FIRST, LEAD, NOW, OFFER, THREAD, _rows, world)

SLOTS = ["2030-01-08T13:00:00-06:00", "2030-01-09T14:00:00-06:00"]
SENT_AT = NOW + timedelta(minutes=20)


def _first_contact_card(world):
    """A pending first-contact card holding two times (create_approval)."""
    st = world["store"]
    ev = ReplyEvent(email_id="lr-1", thread_id=THREAD, campaign_id=CAMPAIGN, campaign_key=OFFER,
                    eaccount=EACCOUNT, lead_email=LEAD, first_name=FIRST, company=COMPANY,
                    subject="Quick question", text=REPLY, received_at=NOW)
    state = LeadState.from_store(st.get("lead:%s:%s" % (CAMPAIGN, LEAD)), ev)
    d = Draft(subject="Re: Quick question", body_text=BODY, label="positive_question", offered_slots=list(SLOTS))
    _sent, fn = _recorder()
    card = A.create_approval(state, d, ev, store=st, now=NOW, notify_fn=fn, campaign_key=OFFER)
    state.processed_email_ids.append("lr-1")
    st.set(state.key, state.to_store())
    assert A._approval_row(st, A._approval_id(card)).status == "pending"
    assert A.first_contact(None, st.get(card.state_key)) is True
    return card


def _thread_records(world, card, arm=True):
    """What section 1's thread check writes on the lead row."""
    st = world["store"]
    row = st.get(card.state_key)
    state = LeadState.from_store(row)
    state.history.append({"at": SENT_AT.isoformat(), "event": "reply_sent_manually",
                          "approval": A._approval_id(card), "by": "lorenzo", "sent_at": SENT_AT.isoformat(),
                          "first_reply": True, "source": "thread", "email_id": "th-1"})
    if arm:
        C.arm(state, SENT_AT)
        state.cadence = dict(state.cadence, armed_for_email_id=card.email_id)
    st.set(card.state_key, state.to_store())
    return st.get(card.state_key)


def _held_times(world, card):
    rows = world["store"].get(A.OFFERED_KEY) or []
    return sorted(r["slot"] for r in rows if r.get("approval") == A._approval_id(card))


def _manual_events(row):
    return [e for e in row.get("history") or [] if e.get("event") == "reply_sent_manually"]


def test_mark_answered_in_thread_closes_the_card_and_touches_nothing_else(world):
    card = _first_contact_card(world)
    st = world["store"]
    held = _held_times(world, card)
    assert held == sorted(SLOTS)
    row = _thread_records(world, card)
    pushes = len(notify.sent_in_test)

    out = A.mark_answered_in_thread(card.token, SENT_AT, "th-1", store=st, now=NOW + timedelta(minutes=30))

    assert out == {"closed": True, "status": "sent_manually", "reason": "closed"}
    stored = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    assert stored["status"] == "sent_manually"
    assert stored["notify_result"][A.MARK_SENT_KEY]["by"] == "thread"
    assert stored["notify_result"][A.MARK_SENT_KEY]["email_id"] == "th-1"
    assert stored["notify_result"][A.MARK_SENT_KEY]["at"] == SENT_AT.isoformat()
    assert st.get(A.SEND_CLAIM_PREFIX + A._approval_id(card))       # nothing can send it now
    assert _held_times(world, card) == held                           # its times stay reserved
    assert st.get(card.state_key) == row                              # lead row untouched
    assert world["inst"].sent == [] and len(notify.sent_in_test) == pushes
    assert _rows(world, "sent_manually") == []


def test_a_second_call_is_a_no_op(world):
    card = _first_contact_card(world)
    st = world["store"]
    _thread_records(world, card)
    A.mark_answered_in_thread(card.token, SENT_AT, "th-1", store=st, now=NOW + timedelta(minutes=30))
    before = st.get(A.APPROVAL_PREFIX + A._approval_id(card))

    out = A.mark_answered_in_thread(card.token, SENT_AT, "th-1", store=st, now=NOW + timedelta(minutes=40))

    assert out == {"closed": False, "status": "sent_manually", "reason": "already_closed"}
    assert st.get(A.APPROVAL_PREFIX + A._approval_id(card)) == before


def test_a_sent_card_is_untouched(world):
    card = _first_contact_card(world)
    st = world["store"]
    _thread_records(world, card)
    key = A.APPROVAL_PREFIX + A._approval_id(card)
    st.set(key, dict(st.get(key), status="sent"))
    before = st.get(key)

    out = A.mark_answered_in_thread(A._approval_id(card), SENT_AT, "th-1", store=st, now=NOW)

    assert out["closed"] is False and out["status"] == "sent" and out["reason"] == "already_closed"
    assert st.get(key) == before


def test_mark_sent_closes_a_thread_answered_card_without_a_second_record(world):
    card = _first_contact_card(world)
    st = world["store"]
    row = _thread_records(world, card)
    assert A.mark_sent_takes(card, st) is True

    out = A.mark_sent_manually(card.token, NOW + timedelta(minutes=30), store=st)

    assert out["ok"] is True and out["status"] == "sent_manually" and out["answered_in_thread"] is True
    assert out["cadence"]["reason"] == A.ANSWERED_IN_THREAD
    assert st.get(A.APPROVAL_PREFIX + A._approval_id(card))["status"] == "sent_manually"
    after = st.get(card.state_key)
    assert len(_manual_events(after)) == 1 and after == row            # no second record, no re-arm
    assert world["inst"].sent == []


def test_approve_refuses_a_card_answered_in_the_thread(world):
    card = _first_contact_card(world)
    st = world["store"]
    _thread_records(world, card)
    before = st.get(A.APPROVAL_PREFIX + A._approval_id(card))

    out = A.approve(card.token, world["inst"], store=st, now=NOW + timedelta(minutes=30))

    assert out["ok"] is False and out["reason"] == "already_answered_in_thread"
    assert out["error"] == A.REASON_TEXT["already_answered_in_thread"]
    assert st.get(A.APPROVAL_PREFIX + A._approval_id(card)) == before
    assert world["inst"].sent == []


def test_send_approved_refuses_a_card_answered_in_the_thread(world):
    card = _first_contact_card(world)
    st = world["store"]
    _thread_records(world, card)
    before = st.get(A.APPROVAL_PREFIX + A._approval_id(card))

    out = A.send_approved(A._approval_row(st, A._approval_id(card)), world["inst"], store=st,
                          now=NOW + timedelta(minutes=30))

    assert out["ok"] is False and out["reason"] == "already_answered_in_thread" and out["status"] == "pending"
    assert st.get(A.APPROVAL_PREFIX + A._approval_id(card)) == before
    assert world["inst"].sent == []
    text = A.REASON_TEXT["already_answered_in_thread"]
    assert "!" not in text and "—" not in text and LEAD not in text and FIRST not in text


def test_arm_under_lock_does_not_rearm_a_running_ladder(world):
    card = _first_contact_card(world)
    row = _thread_records(world, card)
    assert C.is_armed(LeadState.from_store(row))
    box = {}

    merged = A._arm_under_lock(card, {}, NOW + timedelta(hours=2), box)(dict(row))

    assert box["result"]["reason"] == "already_armed" and box["result"]["armed"] is False
    assert merged == row


def test_arm_under_lock_still_arms_an_unarmed_row(world):
    card = _first_contact_card(world)
    row = _thread_records(world, card, arm=False)
    box = {}

    merged = A._arm_under_lock(card, {}, NOW + timedelta(hours=2), box)(dict(row))

    assert box["result"]["armed"] is True and merged["cadence"]["armed_at"]
