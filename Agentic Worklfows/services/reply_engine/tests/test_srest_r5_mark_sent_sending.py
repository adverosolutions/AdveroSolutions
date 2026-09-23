"""S-rest round 5, defect 2: nothing ended the reminders for a `sending` card
whose reply did go out.

A card stuck at sending (its worker died after taking the send claim, and
the reply may have reached the lead) could not be marked sent, Veto refuses
it, and Retry would send the reply again, so the stuck push reminded Lorenzo
every business day for good. Now (option (a)):

* approval.MARK_SENT_FROM takes sending too, once the card's send claim is
  its own attempt and SEND_CLAIM_LEASE_MINUTES old (the context sweep's
  CONTEXT_SWEEP_GRACE_MINUTES, reused). A claim inside the lease, from
  another attempt, missing or unreadable is refused and nothing is recorded;
* the transition is guarded from sending and bound to the send attempt it
  read; the claim it takes over is recorded on the card, on the lead's
  history entry and on the sent_manually row; the bookkeeping is Mark sent's;
* the send it takes over, if it was only held up, never records a second
  time: it re-reads the card before the Instantly call, and its writes (the
  send's "sent" and "send_failed", the recipient hold's) refuse a card
  already sent. Exactly one of sent / sent_manually wins;
* the poller lists a sending card once its claim is past the lease, with the
  Mark sent button (approval.mark_sent_url, given the tick's clock);
* the /mark-sent route takes it (the GET page, the POST record).

Ruling 4: when the lead's row cannot be read, the sent_manually row records
first_reply None, not True.

Every lead is an example.com address; every client is an in-process fake;
live is only ever set in-process with monkeypatch.
"""
import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from shared import notify

from services.metrics import sources
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import poller as P
from services.reply_engine import show_rate

from test_send_safety_round2 import _go_live
from test_send_safety_srest_r3_optout import (  # noqa: F401 - the r3 world, fakes and card helper
    APPT, IN_HOURS, LEAD, FakeInstantly, _alerts, _registry_rows, ct, world,
)
from test_srest_r4_approval import _FailingLeadReads, _booked, _broken_write, _plain, _rows

LEASE = timedelta(minutes=A.SEND_CLAIM_LEASE_MINUTES)
APPROVED = ct(2026, 9, 28, 9, 40)      # Lorenzo approved the card...
STARTED = ct(2026, 9, 28, 9, 50)       # ...its send took the claim, and its worker died
FREE = STARTED + LEASE                 # 10:00: nothing can still be running that send


def _sending(st, make=_plain, attempt="a1", started=STARTED, claim="own"):
    """Card c1 stuck at sending: approved at APPROVED, its send claim taken
    at ``started`` by ``attempt``. ``claim``: "own" (the card's attempt),
    "other" (another attempt's), "no_time" (a claim with no time), or None
    (no claim row)."""
    card = make(st, status="sending")
    row = st.get(A.APPROVAL_PREFIX + "c1")
    row.update(send_attempt=attempt, decided_at=APPROVED.isoformat())
    st.set(A.APPROVAL_PREFIX + "c1", row)
    if claim == "own":
        st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": attempt, "at": started.isoformat()})
    elif claim == "other":
        st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "another-attempt", "at": started.isoformat()})
    elif claim == "no_time":
        st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": attempt})
    return A.load(card.token, st)


def _sends(st, card):
    """The reply-sent events on the lead's history, in order."""
    return [h["event"] for h in st.get(card.state_key)["history"]
            if h.get("event") in A.REPLY_SENT_EVENTS + ("reply_would_send",)]


def _confirms(world):
    return [c for c in world["ghl"].calls if c[0] == "update_appointment_status"]


def _tick(store, now):
    return P._push_stuck(store, P.pending_approvals(store, now), now)


def _stuck_pushes():
    return [n for n in notify.sent_in_test if "Replies with no owner" in n["title"]]


# =========================================================== the lease
def test_the_lease_is_the_send_paths_own_figure_not_a_new_one():
    assert A.SEND_CLAIM_LEASE_MINUTES == A.CONTEXT_SWEEP_GRACE_MINUTES == 10
    assert "sending" in A.MARK_SENT_FROM and "send_failed" in A.MARK_SENT_FROM
    assert app_mod.MARK_SENT_STATUSES == A.MARK_SENT_FROM


def test_a_claim_inside_the_lease_is_refused_and_nothing_is_recorded(world):
    st = world["store"]
    card = _sending(st)
    before_card, before_row = st.get(A.APPROVAL_PREFIX + "c1"), st.get(card.state_key)
    for now in (STARTED + timedelta(minutes=1), FREE - timedelta(seconds=1)):
        out = A.mark_sent_manually("c1", now, store=st, ghl=world["ghl"])
        assert out["ok"] is False and out["status"] == "sending"
        assert out["error"].startswith("This card's send started Mon Sep 28 9:50am CT and may still be running.")
        assert "Mark sent is available from Mon Sep 28 10:00am CT, 10 minutes after it started" in out["error"]
        assert "Nothing was recorded." in out["error"] and u"—" not in out["error"]
        assert A.mark_sent_url(card, store=st, now=now) is None          # and no button yet
    assert st.get(A.APPROVAL_PREFIX + "c1") == before_card and st.get(card.state_key) == before_row
    assert _rows(world, "sent_manually") == [] and world["inst"].sent == [] and world["ghl"].calls == []


def test_a_claim_past_the_lease_is_marked_sent_with_the_claim_on_record(world):
    st = world["store"]
    card = _sending(st)
    assert A.mark_sent_url(card, store=st, now=FREE) == "https://engine.test/mark-sent/%s" % card.token
    assert A.mark_sent_url(card, now=FREE) is None                  # without the store its claim is unread
    out = A.mark_sent_manually("c1", FREE, store=st)
    assert out["ok"] is True and out["status"] == "sent_manually" and out["from_status"] == "sending"
    assert out["send_started_at"] == STARTED.isoformat() and out["send_failed_at"] is None
    assert out["first_reply"] is True and out["cadence"]["armed"] is True and out["alerts"] == []

    stored = st.get(A.APPROVAL_PREFIX + "c1")
    assert stored["status"] == "sent_manually" and stored["decided_at"] == FREE.isoformat()
    assert stored["send_attempt"] == "a1"
    assert stored["notify_result"][A.MARK_SENT_KEY] == {
        "at": FREE.isoformat(), "by": "lorenzo", "send_failed_at": None, "from": "sending",
        "send_claim": {"attempt": "a1", "at": STARTED.isoformat()}}
    # the claim it took over stays: a sent card holds its send claim
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") == {"attempt": "a1", "at": STARTED.isoformat()}
    row = st.get(card.state_key)
    entry = row["history"][-1]
    assert entry["event"] == "reply_sent_manually" and entry["from_status"] == "sending"
    assert entry["send_started_at"] == STARTED.isoformat() and entry["send_failed_at"] is None
    assert entry["first_reply"] is True and entry["sent_at"] == FREE.isoformat()
    assert row["cadence"]["armed_at"] == FREE.isoformat() and row["last_outbound_at"] == FREE.isoformat()
    logged = _rows(world, "sent_manually")
    assert len(logged) == 1 and logged[0]["from_status"] == "sending"
    assert logged[0]["send_started_at"] == STARTED.isoformat() and logged[0]["send_failed_at"] is None
    assert logged[0]["cadence_armed"] is True
    history = A.card_history(st, A.load(card.token, st))
    assert history["send_started"] is True and history["last_send_attempt_at"] == STARTED.isoformat()
    assert world["inst"].sent == [] and _registry_rows(st, "c1")       # nothing sent; its times stay held
    # done: never listed again, never marked twice
    assert P.pending_approvals(st, FREE + timedelta(hours=2)) == []
    assert A.mark_sent_manually("c1", FREE + timedelta(minutes=1), store=st)["error"] == "already sent_manually"
    assert len(_rows(world, "sent_manually")) == 1


def test_a_sending_card_that_holds_the_call_confirms_it_as_a_send_would(world):
    st = world["store"]
    _sending(st, make=_booked)
    out = A.mark_sent_manually("c1", FREE, store=st, ghl=world["ghl"])
    assert out["ok"] is True and out["booking_left_held"] is None
    assert _confirms(world) == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]
    assert not show_rate.is_held(st, APPT)


@pytest.mark.parametrize("claim,reason", [
    (None, "it holds no send claim"),
    ("other", "its send claim is from another send attempt"),
    ("no_time", "its send claim has no readable time"),
], ids=["no_claim", "another_attempt", "no_time"])
def test_a_sending_card_without_a_usable_claim_is_never_marked_sent(world, claim, reason):
    st = world["store"]
    card = _sending(st, claim=claim)
    late = FREE + timedelta(hours=3)
    out = A.mark_sent_manually("c1", late, store=st)
    assert out["ok"] is False and out["status"] == "sending"
    assert "The engine has no usable record of when this card's send started (%s)" % reason in out["error"]
    assert "Mark sent is not available for it; nothing was recorded." in out["error"]
    assert A.mark_sent_url(card, store=st, now=late) is None
    assert A.load(card.token, st).status == "sending" and _rows(world, "sent_manually") == []


def test_a_claim_that_cannot_be_read_refuses_mark_sent_and_gives_no_link(world, monkeypatch):
    st = world["store"]
    card = _sending(st)

    def unreadable(store, approval_id):
        raise IOError("store read timed out")

    monkeypatch.setattr(A, "send_claim_record", unreadable)
    out = A.mark_sent_manually("c1", FREE, store=st)
    assert out["ok"] is False and out["status"] == "sending"
    assert out["error"] == ("could not read this card's send claim (store read timed out); nothing was recorded, "
                            "try again")
    assert A.mark_sent_url(card, store=st, now=FREE) is None
    assert A.load(card.token, st).status == "sending"


def test_mark_sent_is_bound_to_the_send_attempt_it_read(world, monkeypatch):
    """Mark sent read the stale claim, then a new send of the card started
    (Retry, then approve: a new attempt, sending again) before its write.
    The write is bound to the attempt it read, so it records nothing."""
    st = world["store"]
    _sending(st)
    real = A.card_context
    box = {}

    def a_new_send_starts(store, approval_id):
        if not box:
            box["done"] = True
            row = store.get(A.APPROVAL_PREFIX + "c1")
            store.set(A.APPROVAL_PREFIX + "c1", dict(row, send_attempt="a2"))
            store.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "a2", "at": FREE.isoformat()})
        return real(store, approval_id)

    monkeypatch.setattr(A, "card_context", a_new_send_starts)
    out = A.mark_sent_manually("c1", FREE, store=st)
    assert out["ok"] is False and out["status"] == "sending"
    assert "another send of it started" in out["error"] and "nothing was recorded" in out["error"]
    stored = st.get(A.APPROVAL_PREFIX + "c1")
    assert stored["status"] == "sending" and stored["send_attempt"] == "a2"
    assert A.MARK_SENT_KEY not in (stored.get("notify_result") or {})
    assert _rows(world, "sent_manually") == []


# ============================= the send it takes over: one record, never two
@pytest.mark.parametrize("make", [_plain, _booked], ids=["no_call", "owns_the_call"])
def test_a_held_up_send_that_goes_through_after_mark_sent_records_nothing_more(world, make):
    """Mark sent takes the card over while its worker is held up inside the
    Instantly call; the call then goes through. Mark sent's record is the
    only one: one history entry, one sent_manually row, the ladder armed
    once, the call confirmed once; the worker writes no "sent" row, sets no
    interest status, and says what happened."""
    st = world["store"]
    card = make(st, status="pending")
    inst = FakeInstantly()
    marked = {}

    def mark_sent_meanwhile():
        marked["out"] = A.mark_sent_manually("c1", IN_HOURS + LEASE, store=st, ghl=world["ghl"])

    inst.hook_on, inst.hook = "send", mark_sent_meanwhile
    out = A.approve(card.token, inst, store=st, now=IN_HOURS, ghl=world["ghl"])
    assert marked["out"]["ok"] is True and marked["out"]["from_status"] == "sending"
    assert out["ok"] is True and out["status"] == "sent_manually" and out["already"] == "sent_manually"
    assert out["cadence"] is None and out["invite"] is None
    assert len(inst.sent) == 1 and inst.interest == []
    assert st.get(A.APPROVAL_PREFIX + "c1")["status"] == "sent_manually"
    assert _sends(st, card) == ["reply_sent_manually"]
    assert _rows(world, "sent") == [] and len(_rows(world, "sent_manually")) == 1
    late = _rows(world, "sent_after_card_sent")
    assert len(late) == 1 and late[0]["approval"] == "c1" and late[0]["card_status"] == "sent_manually"
    assert late[0]["marked_sent_at"] == (IN_HOURS + LEASE).isoformat()
    assert late[0]["send_started_at"] == IN_HOURS.isoformat()
    assert st.get(card.state_key)["cadence"]["armed_at"] == (IN_HOURS + LEASE).isoformat()
    push = _alerts("Reply to %s went out after its card was already marked sent" % LEAD)
    assert len(push) == 1
    msg = push[0]["message"]
    assert "Card c1 was already marked sent (Mon Sep 28 10:10am CT)" in msg
    assert "If you also replied by hand, the lead has two replies: check the Instantly thread." in msg
    assert "Nothing more was recorded: the card stays sent_manually." in msg and u"—" not in msg
    if make is _booked:
        assert _confirms(world) == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]


def test_a_send_that_fails_after_mark_sent_took_it_over_leaves_the_card_marked(world):
    st = world["store"]
    card = _plain(st, status="pending")
    inst = FakeInstantly()

    def mark_then_fail():
        A.mark_sent_manually("c1", IN_HOURS + LEASE, store=st)
        raise IOError("Instantly timed out")

    inst.hook_on, inst.hook = "send", mark_then_fail
    out = A.approve(card.token, inst, store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "sent_manually"
    assert out["error"] == ("send failed: Instantly timed out; the card was already sent_manually and was left "
                            "as it is")
    assert st.get(A.APPROVAL_PREFIX + "c1")["status"] == "sent_manually"
    failed = _rows(world, "send_failed")
    assert len(failed) == 1 and failed[0]["card_status"] == "sent_manually"
    assert len(_rows(world, "sent_manually")) == 1 and _rows(world, "sent") == []
    assert _sends(st, card) == ["reply_sent_manually"]


class _HeldUpThreadRead(FakeInstantly):
    """Live: the worker is held up in the thread re-read, and Mark sent takes
    the card over meanwhile. The read then answers, or fails."""

    def __init__(self, meanwhile, then_fail=False):
        FakeInstantly.__init__(self)
        self.meanwhile, self.then_fail, self.reads = meanwhile, then_fail, 0

    def get_email(self, email_id):
        self.reads += 1
        if self.meanwhile is not None:
            hook, self.meanwhile = self.meanwhile, None
            hook()
            if self.then_fail:
                raise IOError("thread read timed out")
        return FakeInstantly.get_email(self, email_id)


@pytest.mark.parametrize("then_fail", [False, True], ids=["read_confirms", "read_fails"])
def test_a_live_send_held_up_in_its_thread_read_sends_nothing_after_mark_sent(world, monkeypatch, then_fail):
    _go_live(monkeypatch)
    st = world["store"]
    card = _plain(st, status="pending")
    inst = _HeldUpThreadRead(lambda: A.mark_sent_manually("c1", IN_HOURS + LEASE, store=st), then_fail=then_fail)
    out = A.approve(card.token, inst, store=st, now=IN_HOURS, ghl=world["ghl"])
    assert inst.reads == 1 and inst.sent == []                       # the reply never left from here
    assert out["ok"] is False and out["status"] == "sent_manually" and "nothing was sent" in out["error"]
    stored = st.get(A.APPROVAL_PREFIX + "c1")
    assert stored["status"] == "sent_manually" and stored["send_after"] is None
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") is not None           # the claim Mark sent took over stays
    assert st.get(A.RECIPIENT_HOLD_PREFIX + "c1") is None            # no hold written over it
    assert _rows(world, "sent") == [] and len(_rows(world, "sent_manually")) == 1
    assert _rows(world, "recipient_unconfirmed") == [] and _rows(world, "recipient_held") == []
    assert _sends(st, card) == ["reply_sent_manually"]


class _HeldUpSend(FakeInstantly):
    """reply_to_email waits until the test lets it finish: a worker held up
    inside the Instantly call, on its own thread."""

    def __init__(self):
        FakeInstantly.__init__(self)
        self.in_call = threading.Event()
        self.finish = threading.Event()

    def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
        self.in_call.set()
        if not self.finish.wait(10):
            raise RuntimeError("the test never let the send finish")
        return FakeInstantly.reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=to)


@pytest.mark.parametrize("make", [_plain, _booked], ids=["no_call", "owns_the_call"])
def test_a_held_up_send_that_finishes_before_mark_sent_writes_wins_alone(world, monkeypatch, make):
    """The reverse race, on two threads: Mark sent reads the card (sending,
    its claim past the lease) and passes its checks; the worker it would
    take over finishes before Mark sent's write. The send is the only
    record; Mark sent answers "card changed" and records nothing."""
    st = world["store"]
    card = make(st, status="pending")
    inst = _HeldUpSend()
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
        assert st.get(A.APPROVAL_PREFIX + "c1")["status"] == "sending"
        real = A.card_context
        main = threading.current_thread()
        box = {}

        def the_send_finishes_first(store, approval_id):
            if threading.current_thread() is main and not box:
                box["done"] = True
                inst.finish.set()
                thread.join(10)
            return real(store, approval_id)

        monkeypatch.setattr(A, "card_context", the_send_finishes_first)
        marked = A.mark_sent_manually("c1", IN_HOURS + LEASE, store=st, ghl=world["ghl"])
    finally:
        inst.finish.set()
        thread.join(10)
    assert not thread.is_alive() and "error" not in result and box == {"done": True}
    assert result["out"]["ok"] is True and result["out"]["status"] == "sent"
    assert marked == {"ok": False, "status": "sent",
                      "error": "the card changed before it could be marked sent (it is now sent); nothing was "
                               "recorded"}
    stored = st.get(A.APPROVAL_PREFIX + "c1")
    assert stored["status"] == "sent" and A.MARK_SENT_KEY not in (stored.get("notify_result") or {})
    assert _sends(st, card) == ["reply_sent"]
    assert len(_rows(world, "sent")) == 1 and _rows(world, "sent_manually") == []
    assert _rows(world, "sent_after_card_sent") == [] and len(inst.sent) == 1
    if make is _booked:
        assert _confirms(world) == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]


# ================================================== the poller's button
def test_the_poller_lists_a_sending_card_once_its_claim_is_past_the_lease_with_the_button(world):
    st = world["store"]
    card = _sending(st)
    # decided_at + 5 minutes (the rule for the other stuck statuses) would list it at 9:45
    for now in (APPROVED + timedelta(minutes=P.STUCK_ALERT_MINUTES), STARTED + timedelta(minutes=5),
                FREE - timedelta(minutes=1)):
        assert P.pending_approvals(st, now) == [] and _tick(st, now) == []
    assert _tick(st, FREE) == ["c1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] == "view, Mark sent, https://engine.test/mark-sent/%s" % card.token
    assert "stuck at sending" in push["message"] and P.MARK_SENT_LINE in push["message"]
    assert "no Mark sent button" not in push["message"]


def test_a_queued_card_being_sent_now_is_not_reported_stuck(world):
    """Approved last night, flushed from the queue at 10:00: its decided_at
    is hours old, but its send is minutes old and may be running."""
    st = world["store"]
    _sending(st, started=IN_HOURS)
    row = st.get(A.APPROVAL_PREFIX + "c1")
    st.set(A.APPROVAL_PREFIX + "c1", dict(row, decided_at=ct(2026, 9, 27, 21, 40).isoformat()))
    assert P.pending_approvals(st, IN_HOURS + timedelta(minutes=5)) == []
    assert [w["approval"] for w in P.pending_approvals(st, IN_HOURS + LEASE)] == ["c1"]


def test_a_sending_card_with_no_claim_is_listed_as_before_without_a_button(world):
    st = world["store"]
    _sending(st, claim=None)
    assert _tick(st, APPROVED + timedelta(minutes=P.STUCK_ALERT_MINUTES)) == ["c1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] is None and P.MARK_SENT_LINE not in push["message"]
    assert "This push has no Mark sent button for %s" % LEAD in push["message"]


def test_the_poller_gives_mark_sent_url_the_ticks_clock(world, monkeypatch):
    st = world["store"]
    _sending(st)
    real = A.mark_sent_url
    seen = []

    def spy(card, store=None, now=None):
        seen.append((store, now))
        return real(card, store=store, now=now)

    monkeypatch.setattr(A, "mark_sent_url", spy)
    later = FREE + timedelta(minutes=3)
    assert _tick(st, later) == ["c1"]
    assert seen == [(st, later)]
    assert _stuck_pushes()[-1]["actions"].startswith("view, Mark sent, https://engine.test/mark-sent/")


def test_a_mark_sent_url_that_cannot_judge_the_claim_gives_a_sending_card_no_button(world, monkeypatch):
    """A builder without ``now`` (an older approval module) cannot tell a
    running send from a dead one: no button for a sending card."""
    monkeypatch.setattr(A, "mark_sent_url", lambda card, store=None: "https://engine.test/mark-sent/x")
    st = world["store"]
    _sending(st)
    assert _tick(st, FREE) == ["c1"]
    push = _stuck_pushes()[-1]
    assert push["actions"] is None and "This push has no Mark sent button for %s" % LEAD in push["message"]


# ======================================================= the route
def _clock(world, now):
    box = {"now": now}
    app_mod.configure(store=world["store"], ghl=world["ghl"], instantly=world["inst"], clock=lambda: box["now"])
    return box


def test_the_mark_sent_route_takes_a_sending_card_only_past_the_lease(world):
    st = world["store"]
    card = _sending(st)
    box = _clock(world, STARTED + timedelta(minutes=4))
    client = TestClient(app_mod.app)

    page = client.get("/mark-sent/%s" % card.token)
    assert page.status_code == 400 and "Mark sent not available" in page.text
    assert "may still be running" in page.text and "Mark sent is available from Mon Sep 28 10:00am CT" in page.text
    assert "method='post'" not in page.text
    post = client.post("/mark-sent/%s" % card.token)
    assert post.status_code == 400 and "Not recorded" in post.text and "may still be running" in post.text
    assert A.load(card.token, st).status == "sending" and _rows(world, "sent_manually") == []

    box["now"] = FREE
    page = client.get("/mark-sent/%s" % card.token)
    assert page.status_code == 200 and "Mark this reply as sent?" in page.text
    assert "action='/mark-sent/%s'" % card.token in page.text and "method='post'" in page.text
    assert "A send from this card was started" in page.text
    assert A.load(card.token, st).status == "sending"                  # a GET changes nothing
    done = client.post("/mark-sent/%s" % card.token)
    assert done.status_code == 200 and "Marked as sent" in done.text
    assert A.load(card.token, st).status == "sent_manually" and len(_rows(world, "sent_manually")) == 1
    again = client.post("/mark-sent/%s" % card.token)
    assert again.status_code == 400 and "this approval is sent_manually" in again.text
    assert len(_rows(world, "sent_manually")) == 1


def test_the_mark_sent_route_refuses_a_sending_card_with_no_claim(world):
    st = world["store"]
    card = _sending(st, claim=None)
    _clock(world, FREE + timedelta(hours=1))
    client = TestClient(app_mod.app)
    page = client.get("/mark-sent/%s" % card.token)
    assert page.status_code == 400 and "has no usable record of when this card" in page.text
    assert "method='post'" not in page.text
    post = client.post("/mark-sent/%s" % card.token)
    assert post.status_code == 400 and "has no usable record of when this card" in post.text
    assert A.load(card.token, st).status == "sending" and _rows(world, "sent_manually") == []


# ============================= ruling 4: first_reply when the row is unread
@pytest.mark.parametrize("how,first", [("unparseable", None), ("unreadable", None), ("missing", None),
                                       ("write_fails", True)])
def test_mark_sent_records_first_reply_none_when_the_lead_row_was_not_read(world, monkeypatch, how, first):
    st = world["store"]
    card = _plain(st)
    store = st
    if how == "unparseable":
        raw = st.get(card.state_key)
        raw["history"] = "not a list"
        st.set(card.state_key, raw)
    elif how == "unreadable":
        store = _FailingLeadReads(st, card.state_key, after=2)
    elif how == "missing":
        st.delete(card.state_key)
    else:
        monkeypatch.setattr(A, "save_lead_state", _broken_write)      # read fine, the write fails
    out = A.mark_sent_manually("c1", IN_HOURS, store=store)
    assert out["ok"] is True and out["first_reply"] is first
    logged = _rows(world, "sent_manually")
    assert len(logged) == 1 and logged[0]["first_reply"] is first
    assert len(_rows(world, "mark_sent_record_not_updated")) == 1


def test_the_metrics_read_a_sent_manually_row_whose_first_reply_is_none():
    """services/metrics/sources: the row counts as a draft sent, and the
    time-to-first-reply metric leaves every sent_manually row out anyway."""
    day = date(2026, 9, 28)
    rows = [{"ts_utc": "2026-09-28T15:00:00+00:00", "job": "reply_engine.approval", "status": "sent_manually",
             "details_parsed": {"lead": LEAD, "approval": "c1", "reply_at": "2026-09-28T14:00:00+00:00",
                                "sent_at": "2026-09-28T15:00:00+00:00", "first_reply": None}}]
    assert sources.engine_metrics(rows, None, day)["drafts_sent"] == 1
    assert sources.first_reply_minutes(rows, day) is None
