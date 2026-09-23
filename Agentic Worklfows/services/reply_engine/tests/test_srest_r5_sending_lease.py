"""S-rest round 5, open items: nothing frees a `sending` card while its send
may still be running.

Retry dropped the send claim of a `sending` card and put it back to pending
whatever the claim's age, so a Retry, then an approval, while the card's
worker was still inside the Instantly call sent the lead a second reply.
Now:

* retry() refuses a `sending` card whose own send claim is inside
  SEND_CLAIM_LEASE_MINUTES (the lease Mark sent waits for) and says when
  Retry becomes available (retry_refusal); a claim that cannot tell when the
  send started (none, another attempt's, no time) is taken as before, and one
  that cannot be read is refused;
* the move back to pending is bound to the send attempt Retry read, and only
  the Retry that wins drops the claim: a second Retry that read the old
  attempt never frees the send the first one led to;
* approve, edit, Book as asked (accept_requested) and veto refuse a `sending`
  card as they always did, and inside the lease say when it can be acted on;
  expiry, the orphan sweep and a newer reply's supersede never take one;
* Mark sent or Retry taking a card from `sending` writes a
  send_never_finished Job_Log row, a deploy-watch failure: the worker that
  ran the send wrote nothing of its own.

Every lead is an example.com address; every client is an in-process fake;
live is only ever set in-process with monkeypatch.
"""
import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from changesets.deploy import watch_report

from services.reply_engine import approval as A
from services.reply_engine import app as app_mod
from services.reply_engine import poller as P
from services.reply_engine.models import LeadState

from test_send_safety_srest_r3_optout import (  # noqa: F401 - the r3 world and fakes
    APPT, IN_HOURS, LEAD, FakeInstantly, ct, world,
)
from test_srest_r4_approval import _booked, _plain, _rows
from test_srest_r5_mark_sent_sending import (
    FREE, LEASE, STARTED, _HeldUpSend, _clock, _confirms, _sending, _sends,
)

RETRY_WAIT = ("This card's send started Mon Sep 28 9:50am CT and may still be running, so a Retry now could send "
              "the reply a second time. Retry is available from Mon Sep 28 10:00am CT, 10 minutes after it "
              "started: check the Instantly thread then, and press Mark sent instead if the reply went out. "
              "Nothing changed.")


def _lost(world):
    return _rows(world, "send_never_finished")


# ================================================= Retry waits out the lease
def test_retry_refuses_a_sending_card_whose_send_may_still_be_running(world):
    st = world["store"]
    card = _sending(st)
    before = st.get(A.APPROVAL_PREFIX + "c1")
    for now in (STARTED + timedelta(minutes=1), FREE - timedelta(seconds=1)):
        assert A.retry_refusal(card, st, now) == RETRY_WAIT
        out = A.retry(card.token, store=st, now=now)
        assert out == {"ok": False, "status": "sending", "error": RETRY_WAIT, "actionable_at": FREE.isoformat()}
    assert st.get(A.APPROVAL_PREFIX + "c1") == before
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") == {"attempt": "a1", "at": STARTED.isoformat()}
    assert not A.card_context(st, "c1").get("send_attempts")      # nothing recorded either
    assert _rows(world, "retry") == [] and _lost(world) == []


def test_retry_takes_a_sending_card_once_its_claim_is_past_the_lease(world):
    st = world["store"]
    card = _sending(st)
    assert A.retry_refusal(card, st, FREE) is None
    out = A.retry(card.token, store=st, now=FREE)
    assert out["ok"] is True and out["status"] == "pending" and out["from_status"] == "sending"
    stored = st.get(A.APPROVAL_PREFIX + "c1")
    assert stored["status"] == "pending" and stored["send_attempt"] is None
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") is None
    assert A.card_history(st, A.load(out["token"], st))["send_started"] is True   # the attempt stays on record
    assert _lost(world) == [{"lead": LEAD, "approval": "c1", "send_attempt": "a1",
                             "send_started_at": STARTED.isoformat(), "claim": "stale", "taken_by": "retry",
                             "taken_at": FREE.isoformat()}]
    assert len(_rows(world, "retry")) == 1
    sent = A.approve(out["token"], world["inst"], store=st, now=FREE + timedelta(minutes=1), ghl=world["ghl"])
    assert sent["ok"] is True and sent["status"] == "sent" and len(world["inst"].sent) == 1


@pytest.mark.parametrize("claim,state", [(None, "no_claim"), ("other", "other_attempt"), ("no_time", "no_time")],
                         ids=["no_claim", "another_attempt", "no_time"])
def test_retry_of_a_sending_card_whose_claim_cannot_tell_is_taken_as_before(world, claim, state):
    """Retry is the way out for these (Mark sent refuses them): refusing it
    too would leave the card stuck for good. The watch row says what the
    claim was."""
    st = world["store"]
    card = _sending(st, claim=claim)
    now = STARTED + timedelta(minutes=1)
    assert A.retry_refusal(card, st, now) is None
    out = A.retry(card.token, store=st, now=now)
    assert out["ok"] is True and out["status"] == "pending"
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") is None
    lost = _lost(world)
    assert len(lost) == 1 and lost[0]["claim"] == state and lost[0]["taken_by"] == "retry"
    assert lost[0]["send_started_at"] is None and lost[0]["send_attempt"] == "a1"


def test_retry_refuses_a_sending_card_whose_claim_cannot_be_read(world, monkeypatch):
    st = world["store"]
    card = _sending(st)

    def unreadable(store, approval_id):
        raise IOError("store read timed out")

    monkeypatch.setattr(A, "send_claim_record", unreadable)
    out = A.retry(card.token, store=st, now=FREE)
    assert out == {"ok": False, "status": "sending",
                   "error": "could not read this card's send claim (store read timed out); nothing changed, try again"}
    assert A.load(card.token, st).status == "sending" and _lost(world) == [] and _rows(world, "retry") == []


def test_the_retry_route_refuses_inside_the_lease_and_takes_the_card_after_it(world):
    st = world["store"]
    card = _sending(st)
    box = _clock(world, STARTED + timedelta(minutes=4))
    client = TestClient(app_mod.app)
    refused = client.post("/retry/%s" % card.token)
    assert refused.status_code == 400 and "Not retried" in refused.text
    assert "Retry is available from Mon Sep 28 10:00am CT, 10 minutes after it started" in refused.text
    assert A.load(card.token, st).status == "sending"
    box["now"] = FREE
    done = client.post("/retry/%s" % card.token)
    assert done.status_code == 200 and "Back to pending" in done.text
    assert A.load(card.token, st).status == "pending" and len(_lost(world)) == 1


# ============ a worker still inside its Instantly call: one reply, never two
@pytest.mark.parametrize("make", [_plain, _booked], ids=["no_call", "owns_the_call"])
def test_nothing_frees_a_card_whose_worker_is_still_inside_its_instantly_call(world, make):
    """The send is under way (its worker is inside the Instantly call, on its
    own thread) and every button is pressed meanwhile: Retry, Approve, Edit,
    Book as asked, Veto, Mark sent, and the poller's tick. None of them moves
    the card or starts a second send, and each says when the card can be
    acted on. The send then finishes and is the lead's only reply."""
    st = world["store"]
    card = make(st, status="pending")
    inst = _HeldUpSend()
    other = FakeInstantly()                      # any second send would land here
    result = {}

    def worker():
        try:
            result["out"] = A.approve(card.token, inst, store=st, now=IN_HOURS, ghl=world["ghl"])
        except BaseException as exc:  # noqa: BLE001 - reported below
            result["error"] = exc

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert inst.in_call.wait(10), "the send never reached Instantly"
        stored = st.get(A.APPROVAL_PREFIX + "c1")
        assert stored["status"] == "sending" and stored["send_attempt"]
        free = (IN_HOURS + LEASE).isoformat()
        for minutes in (1, 9):
            now = IN_HOURS + timedelta(minutes=minutes)
            retried = A.retry(card.token, store=st, now=now)
            assert retried["ok"] is False and retried["status"] == "sending"
            assert retried["error"].startswith("This card's send started Mon Sep 28 10:00am CT and may still be "
                                               "running, so a Retry now could send the reply a second time. Retry "
                                               "is available from Mon Sep 28 10:10am CT")
            assert retried["actionable_at"] == free
            for out in (A.approve(card.token, other, store=st, now=now, ghl=world["ghl"]),
                        A.edit(card.token, "Hi Owner, happy to walk you through pricing.", store=st, now=now),
                        A.accept_requested(card.token, world["ghl"], other, store=st, now=now),
                        A.veto(card.token, store=st, now=now, ghl=world["ghl"], instantly=other)):
                assert out["ok"] is False and out["status"] == "sending"
                assert out["error"] == ("already sending: its send started Mon Sep 28 10:00am CT and may still be "
                                        "running. If the card still shows sending at Mon Sep 28 10:10am CT, 10 "
                                        "minutes after it started, check the Instantly thread: press Mark sent if "
                                        "the reply went out, or Retry if it did not")
                assert out["actionable_at"] == free
            marked = A.mark_sent_manually("c1", now, store=st, ghl=world["ghl"])
            assert marked["ok"] is False and "Mark sent is available from Mon Sep 28 10:10am CT" in marked["error"]
            assert A.flush_queued(other, store=st, now=now, ghl=world["ghl"]) == []
            assert P.pending_approvals(st, now) == []                  # not stuck: its send may be running
            assert st.get(A.APPROVAL_PREFIX + "c1") == stored          # nothing moved it
            assert st.get(A.SEND_CLAIM_PREFIX + "c1")["attempt"] == stored["send_attempt"]
        assert inst.sent == [] and other.sent == []
    finally:
        inst.finish.set()
        thread.join(10)
    assert not thread.is_alive() and "error" not in result
    assert result["out"]["ok"] is True and result["out"]["status"] == "sent"
    assert len(inst.sent) == 1 and other.sent == [] and _sends(st, card) == ["reply_sent"]
    assert len(_rows(world, "sent")) == 1
    for status in ("retry", "vetoed", "edited", "accepted_requested", "sent_manually", "send_never_finished",
                   "sent_after_card_sent"):
        assert _rows(world, status) == [], status
    if make is _booked:
        assert _confirms(world) == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]


def test_a_retry_that_read_the_old_attempt_never_frees_the_send_the_first_one_led_to(world, monkeypatch):
    """Two Retries of a card whose worker died: the first wins, the card is
    approved again, and its new send is inside the Instantly call when the
    second Retry (which read the dead attempt) writes. That write is bound to
    the attempt it read: refused, and the new send's claim stays, so nothing
    can free the card for a third send. The lead gets one reply."""
    st = world["store"]
    card = _sending(st)                          # its worker died at 9:50
    inst = _HeldUpSend()
    other = FakeInstantly()
    real = A._note_card_history
    main = threading.current_thread()
    box = {}
    result = {}

    def approve_again(token):
        try:
            result["out"] = A.approve(token, inst, store=st, now=FREE + timedelta(minutes=1), ghl=world["ghl"])
        except BaseException as exc:  # noqa: BLE001 - reported below
            result["error"] = exc

    def the_first_retry_wins_meanwhile(store, approval_id, ts, **kw):
        if threading.current_thread() is main and not box:
            box["started"] = True
            box["first"] = A.retry(card.token, store=store, now=FREE)
            box["thread"] = threading.Thread(target=approve_again, args=(box["first"]["token"],))
            box["thread"].start()
            box["in_call"] = inst.in_call.wait(10)
        return real(store, approval_id, ts, **kw)

    monkeypatch.setattr(A, "_note_card_history", the_first_retry_wins_meanwhile)
    try:
        second = A.retry(card.token, store=st, now=FREE + timedelta(minutes=2))
        assert box["in_call"] is True and box["first"]["ok"] is True
        assert second == {"ok": False, "status": "sending",
                          "error": "the card changed meanwhile (it is now sending); open it again"}
        stored = st.get(A.APPROVAL_PREFIX + "c1")
        assert stored["status"] == "sending" and stored["send_attempt"] not in (None, "a1")
        assert st.get(A.SEND_CLAIM_PREFIX + "c1")["attempt"] == stored["send_attempt"]   # the new send's claim
        # and nothing else frees the card while that send is running
        third = A.retry(card.token, store=st, now=FREE + timedelta(minutes=3))
        assert third["ok"] is False and "may still be running" in third["error"]
        assert third["actionable_at"] == (FREE + timedelta(minutes=11)).isoformat()
        assert A.approve(card.token, other, store=st, now=FREE + timedelta(minutes=3), ghl=world["ghl"])["ok"] is False
    finally:
        inst.finish.set()
        if "thread" in box:
            box["thread"].join(10)
    assert "error" not in result and result["out"]["ok"] is True and result["out"]["status"] == "sent"
    assert len(inst.sent) == 1 and other.sent == [] and _sends(st, card) == ["reply_sent"]
    assert len(_rows(world, "retry")) == 1 and len(_rows(world, "sent")) == 1
    assert [r["taken_by"] for r in _lost(world)] == ["retry"]


# ===================================== the other buttons, past the lease
@pytest.mark.parametrize("claim,now", [("own", FREE), (None, STARTED + timedelta(minutes=1)),
                                       ("other", STARTED + timedelta(minutes=1))],
                         ids=["past_the_lease", "no_claim", "another_attempt"])
def test_outside_a_running_lease_the_other_buttons_just_say_already_sending(world, claim, now):
    st = world["store"]
    card = _sending(st, claim=claim)
    for out in (A.approve(card.token, world["inst"], store=st, now=now, ghl=world["ghl"]),
                A.edit(card.token, "Hi Owner, happy to walk you through pricing.", store=st, now=now),
                A.accept_requested(card.token, world["ghl"], world["inst"], store=st, now=now),
                A.veto(card.token, store=st, now=now, ghl=world["ghl"], instantly=world["inst"])):
        assert out == {"ok": False, "error": "already sending", "status": "sending"}
    assert A.load(card.token, st).status == "sending" and world["inst"].sent == []


def test_a_claim_that_cannot_be_read_still_refuses_the_other_buttons(world, monkeypatch):
    st = world["store"]
    card = _sending(st)

    def unreadable(store, approval_id):
        raise IOError("store read timed out")

    monkeypatch.setattr(A, "send_claim_record", unreadable)
    out = A.approve(card.token, world["inst"], store=st, now=STARTED + timedelta(minutes=1), ghl=world["ghl"])
    assert out == {"ok": False, "error": "already sending", "status": "sending"}
    assert world["inst"].sent == []


def test_expiry_the_orphan_sweep_and_a_newer_reply_never_take_a_sending_card(world):
    st = world["store"]
    card = _sending(st, make=_booked)
    later = STARTED + timedelta(days=3)                           # far past its 48 hours
    before = st.get(A.APPROVAL_PREFIX + "c1")
    assert A.expire_overdue(st, later) == []
    A._retire_orphan_owner(st, "c1", later)
    assert A.supersede_pending(st, LeadState.from_store(st.get(card.state_key)), later) == []
    assert st.get(A.APPROVAL_PREFIX + "c1") == before
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") == {"attempt": "a1", "at": STARTED.isoformat()}


# ================================================ the deploy watch's record
def test_mark_sent_of_a_sending_card_writes_the_watch_row(world):
    st = world["store"]
    _sending(st)
    assert A.mark_sent_manually("c1", FREE, store=st)["ok"] is True
    assert _lost(world) == [{"lead": LEAD, "approval": "c1", "send_attempt": "a1",
                             "send_started_at": STARTED.isoformat(), "claim": "stale", "taken_by": "mark_sent",
                             "taken_at": FREE.isoformat()}]
    assert len(_rows(world, "sent_manually")) == 1


@pytest.mark.parametrize("action", ["mark_sent", "retry"])
def test_a_send_failed_card_writes_no_watch_row_its_failure_already_has_one(world, action):
    st = world["store"]
    card = _plain(st)                                             # send_failed
    if action == "mark_sent":
        assert A.mark_sent_manually("c1", IN_HOURS, store=st)["ok"] is True
    else:
        assert A.retry(card.token, store=st, now=IN_HOURS)["ok"] is True
    assert _lost(world) == []


def test_the_watch_counts_a_send_that_never_finished_as_a_failure():
    assert "send_never_finished" in watch_report.KNOWN_FAILURES
    assert watch_report.classify("send_never_finished") == "fail"
    assert watch_report.classify("sent_manually") == "healthy"
