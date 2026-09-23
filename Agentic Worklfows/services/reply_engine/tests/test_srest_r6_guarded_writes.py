"""S-rest round 6, item 1: edit, Book as asked and veto write the card only
over the status they read.

Each read the card, checked its status, and later saved the whole card (or
its status) with no guard. A send that started in between (Lorenzo's own
Approve on another device, the 07:00 flush of a queued card) was overwritten:

* edit put a card whose reply was going out, or had gone out, back to
  pending with the new text and let its old offered times go, and Approve
  then sent the lead a second reply;
* Book as asked (accept_requested) booked the call, saved the confirmation
  over the sending or sent card and sent it: a second reply;
* veto wrote vetoed over a sending card and cancelled the call the reply
  was confirming.

Now each write is a status-guarded _transition from the status the action
read. Lost, the action refuses and says what the card is now (and, for a
send that may still be running, when it can be acted on), and:

* edit drops only the times it claimed; the times the card's reply offers
  stay held, and nothing of the booking choice is written;
* Book as asked cancels the call it had just booked again, without
  notifying the lead (shadow: the would_do record), gives its time back and
  pushes one alert naming what was undone; a cancel GHL refuses stays held
  and retried, and that one alert carries the "I cancelled it" link; a call
  a newer reply's card put on the lead row meanwhile is never overwritten;
* veto cancels nothing and releases nothing.

Every lead is an example.com address; every client is an in-process fake;
live is only ever set in-process with monkeypatch.
"""
import threading
from datetime import timedelta

import pytest

from shared import notify

from services.reply_engine import approval as A
from services.reply_engine import show_rate

from test_send_safety_round2 import _go_live
from test_send_safety_srest_r3_optout import (  # noqa: F401 - the r3 world, fakes and helpers
    APPT, IN_HOURS, LEAD, FakeInstantly, Recorder, _registry_rows, ct, world,
)
from test_srest_r4_approval import AFTER_HOURS, SLOT, _booked, _plain, _rows
from test_srest_r5_mark_sent_sending import _HeldUpSend, _confirms, _sends

OFFERED = "2026-09-30T13:00:00-05:00"      # Wed Sep 30 1:00pm CT: what card c1's reply offers
NEW_BODY = "Hey Owner,\n\nHappy to explain. Does Thu 2:00pm CT work?\n\nLorenzo"
NEW_SLOT = "2026-10-01T14:00:00-05:00"     # the time the edit names
FREE_AT = "2026-09-28T10:10:00-05:00"      # the send claim taken at IN_HOURS, plus the 10-minute lease
RUNNING = ("Its send started Mon Sep 28 10:00am CT and may still be running. If the card still shows sending at "
           "Mon Sep 28 10:10am CT, 10 minutes after it started, check the Instantly thread: press Mark sent if the "
           "reply went out, or Retry if it did not")
UNDONE_TITLE = "Book as asked undone for %s" % LEAD
APPT_ASKED = "appt-asked-1"
OTHER_APPT = "appt-other-1"                # a call a newer reply's card booked in the window
OTHER_SLOT = "2026-10-02T13:00:00-05:00"   # Fri Oct 2 1:00pm CT


def _card(st, card_id="c1"):
    return st.get(A.APPROVAL_PREFIX + card_id)


def _pushes(fragment):
    return [n for n in notify.sent_in_test if fragment in n["title"]]


def _events(st, card, event):
    return [h for h in st.get(card.state_key)["history"] if h.get("event") == event]


def _send_after_the_read(monkeypatch, send):
    """The window between an action's read and its write: ``send`` runs to
    the end the moment load() hands the action its card, so the action goes
    on with what it read while the card has moved on."""
    real = A.load
    box = {}

    def spy(token, store=None):
        found = real(token, store)
        if not box:
            box["running"] = True
            box["send"] = send()
        return found

    monkeypatch.setattr(A, "load", spy)
    return box


class _Sender(object):
    """A send on its own thread, held inside the Instantly call until the
    test lets it finish: started in the action's window, still running when
    the action writes."""

    def __init__(self, world, card):
        self.world, self.card = world, card
        self.inst = _HeldUpSend()
        self.result = {}
        self.thread = threading.Thread(target=self._run)

    def _run(self):
        try:
            self.result["send"] = A.approve(self.card.token, self.inst, store=self.world["store"], now=IN_HOURS,
                                            ghl=self.world["ghl"])
        except BaseException as exc:  # noqa: BLE001 - reported by finish()
            self.result["error"] = exc

    def start(self):
        self.thread.start()
        assert self.inst.in_call.wait(10), "the send never reached Instantly"
        assert _card(self.world["store"])["status"] == "sending"

    def finish(self):
        self.inst.finish.set()
        if self.thread.ident is not None:
            self.thread.join(10)
        assert not self.thread.is_alive() and "error" not in self.result, self.result
        return self.result.get("send")


def _start_on_read(monkeypatch, sender):
    """Start ``sender`` the moment the main thread's action has read its card."""
    real = A.load
    main = threading.current_thread()
    box = {}

    def spy(token, store=None):
        found = real(token, store)
        if threading.current_thread() is main and not box:
            box["started"] = True
            sender.start()
        return found

    monkeypatch.setattr(A, "load", spy)
    return box


# ===================================================================== veto
@pytest.mark.parametrize("make", [_plain, _booked], ids=["no_call", "owns_the_call"])
def test_a_veto_that_read_the_card_before_its_send_vetoes_nothing(world, monkeypatch, make):
    st = world["store"]
    card = make(st, status="pending")
    box = _send_after_the_read(monkeypatch, lambda: dict(
        out=A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"]),
        registry=_registry_rows(st, "c1")))
    out = A.veto(card.token, store=st, now=IN_HOURS, ghl=world["ghl"], instantly=world["inst"])
    assert box["send"]["out"]["ok"] is True and box["send"]["out"]["status"] == "sent"
    assert out == {"ok": False, "status": "sent",
                   "error": "the card changed meanwhile (it is now sent); nothing was vetoed"}
    assert _card(st)["status"] == "sent" and _rows(world, "vetoed") == []
    assert _registry_rows(st, "c1") == box["send"]["registry"]          # nothing released
    assert _events(st, card, "vetoed") == [] and st.get(card.state_key)["status"] != "vetoed"
    assert len(world["inst"].sent) == 1
    if make is _booked:
        # the call the reply confirmed stands: confirmed once, never cancelled
        assert _confirms(world) == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]
        booking = st.get(card.state_key)["cadence"]["booking"]
        assert booking["confirmed_by"] == "c1" and booking["awaiting_approval"] is False


@pytest.mark.parametrize("make", [_plain, _booked], ids=["no_call", "owns_the_call"])
def test_a_veto_that_lands_while_its_send_is_running_never_cancels_the_call(world, monkeypatch, make):
    """The veto read pending; the send took the card and is inside the
    Instantly call when the veto writes. The call its reply confirms is never
    cancelled."""
    st = world["store"]
    card = make(st, status="pending")
    sender = _Sender(world, card)
    _start_on_read(monkeypatch, sender)
    try:
        out = A.veto(card.token, store=st, now=IN_HOURS, ghl=world["ghl"], instantly=world["inst"])
        assert _card(st)["status"] == "sending"
        assert [c for c in world["ghl"].calls if c[0] == "update_appointment_status"] == []
    finally:
        sent = sender.finish()
    assert out == {"ok": False, "status": "sending", "actionable_at": FREE_AT,
                   "error": "the card changed meanwhile (it is now sending); nothing was vetoed. %s" % RUNNING}
    assert sent["ok"] is True and sent["status"] == "sent" and _card(st)["status"] == "sent"
    assert _rows(world, "vetoed") == [] and _sends(st, card) == ["reply_sent"] and len(sender.inst.sent) == 1
    if make is _plain:
        assert [r["slot"] for r in _registry_rows(st, "c1")] == [OFFERED]   # the time the reply offers stays held
    else:
        assert _confirms(world) == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]
        assert not show_rate.is_held(st, APPT)                           # released by the send, not torn down


def test_a_veto_that_read_a_card_a_newer_reply_then_superseded_says_so(world, monkeypatch):
    st = world["store"]
    card = _booked(st, status="pending")

    def supersede():
        return A._transition(st, "c1", ("pending",), lambda row: dict(row, status="superseded"))

    _send_after_the_read(monkeypatch, supersede)
    out = A.veto(card.token, store=st, now=IN_HOURS, ghl=world["ghl"], instantly=world["inst"])
    assert out == {"ok": False, "status": "superseded",
                   "error": "the card changed meanwhile (it is now superseded); nothing was vetoed"}
    assert world["ghl"].calls == [] and _rows(world, "vetoed") == []
    assert st.get(card.state_key)["cadence"]["booking"]["owner"] == "c1"


def test_a_veto_that_wins_its_write_still_vetoes_and_cancels_the_call_it_owns(world):
    st = world["store"]
    card = _booked(st, status="pending")
    out = A.veto(card.token, store=st, now=IN_HOURS, ghl=world["ghl"], instantly=world["inst"])
    assert out["ok"] is True and out["status"] == "vetoed" and out["booking_cancelled"]["slot"] == SLOT
    stored = _card(st)
    assert stored["status"] == "vetoed" and stored["decided_at"] == IN_HOURS.isoformat()
    assert ("update_appointment_status", (APPT, "cancelled"), {"to_notify": False}) in world["ghl"].calls
    assert _registry_rows(st, "c1") == [] and len(_rows(world, "vetoed")) == 1


# ===================================================================== edit
def test_an_edit_that_read_the_card_before_its_send_is_not_saved_and_holds_nothing_new(world, monkeypatch):
    st = world["store"]
    card = _plain(st, status="pending")
    box = _send_after_the_read(monkeypatch, lambda: A.approve(card.token, world["inst"], store=st, now=IN_HOURS,
                                                              ghl=world["ghl"]))
    out = A.edit(card.token, NEW_BODY, store=st, now=IN_HOURS)
    assert box["send"]["ok"] is True and box["send"]["status"] == "sent"
    assert out == {"ok": False, "status": "sent", "token": card.token,
                   "error": "the card changed meanwhile (it is now sent); the edit was not saved"}
    stored = _card(st)
    assert stored["status"] == "sent" and stored["token"] == card.token
    assert stored["draft"]["body_text"] == card.draft.body_text and stored["draft"]["offered_slots"] == [OFFERED]
    # the time the sent reply offers stays held; the one the edit named was given back
    assert [r["slot"] for r in _registry_rows(st, "c1")] == [OFFERED]
    assert _rows(world, "edited") == []
    again = A.approve(card.token, world["inst"], store=st, now=IN_HOURS + timedelta(minutes=1), ghl=world["ghl"])
    assert again["ok"] is False and len(world["inst"].sent) == 1 and _sends(st, card) == ["reply_sent"]


def test_an_edit_that_lands_while_its_send_is_running_is_not_saved(world, monkeypatch):
    st = world["store"]
    card = _plain(st, status="pending")
    sender = _Sender(world, card)
    _start_on_read(monkeypatch, sender)
    try:
        out = A.edit(card.token, NEW_BODY, store=st, now=IN_HOURS)
        assert _card(st)["status"] == "sending"
        assert [r["slot"] for r in _registry_rows(st, "c1")] == [OFFERED]    # the claim on NEW_SLOT undone
    finally:
        sent = sender.finish()
    assert out == {"ok": False, "status": "sending", "token": card.token, "actionable_at": FREE_AT,
                   "error": "the card changed meanwhile (it is now sending); the edit was not saved. %s" % RUNNING}
    assert sent["ok"] is True and _card(st)["status"] == "sent"
    assert _card(st)["draft"]["body_text"] == card.draft.body_text and len(sender.inst.sent) == 1
    assert sender.inst.sent[0]["body"] == card.draft.body_text
    assert [r["slot"] for r in _registry_rows(st, "c1")] == [OFFERED] and _rows(world, "edited") == []


def test_an_edit_of_the_card_that_owns_the_call_writes_no_booking_choice_when_it_loses(world, monkeypatch):
    st = world["store"]
    card = _booked(st, status="pending")
    _send_after_the_read(monkeypatch, lambda: A.approve(card.token, world["inst"], store=st, now=IN_HOURS,
                                                        ghl=world["ghl"]))
    out = A.edit(card.token, NEW_BODY, store=st, now=IN_HOURS, booking_choice="release")
    assert out["ok"] is False and out["status"] == "sent"
    assert st.get(A.BOOKING_CHOICE_PREFIX + "c1") is None
    assert _confirms(world) == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]
    assert [c for c in world["ghl"].calls if c[1][1:] == ("cancelled",)] == []


def test_an_edit_that_wins_its_write_holds_the_new_time_and_gives_the_old_one_back(world):
    st = world["store"]
    card = _plain(st, status="pending")
    out = A.edit(card.token, NEW_BODY, store=st, now=IN_HOURS)
    assert out["ok"] is True and out["status"] == "pending" and out["offered_slots"] == [NEW_SLOT]
    assert out["token"] != card.token and A.load(out["token"], st).draft.body_text == NEW_BODY
    assert A.load(card.token, st) is None                                # the old token no longer loads
    assert [r["slot"] for r in _registry_rows(st, "c1")] == [NEW_SLOT]
    assert len(_rows(world, "edited")) == 1


@pytest.mark.parametrize("loses", [False, True], ids=["wins", "loses"])
def test_an_edit_whose_new_time_another_lead_holds_claims_nothing(world, monkeypatch, loses):
    """A claim that finds the time taken adds nothing. Won, the edit is saved
    with the problem and the card holds nothing, as before; lost, the card's
    old time stays held with the reply that offers it."""
    st = world["store"]
    card = _plain(st, status="pending")
    A.reserve_slots(st, "other@example.com", [NEW_SLOT], "other-card", IN_HOURS)
    if loses:
        _send_after_the_read(monkeypatch, lambda: A.approve(card.token, world["inst"], store=st, now=IN_HOURS,
                                                            ghl=world["ghl"]))
    out = A.edit(card.token, NEW_BODY, store=st, now=IN_HOURS)
    if loses:
        assert out["ok"] is False and out["status"] == "sent"
        assert [r["slot"] for r in _registry_rows(st, "c1")] == [OFFERED]
    else:
        assert out["ok"] is True and any("already held for another lead" in p for p in out["problems"])
        assert _registry_rows(st, "c1") == []
    assert [r["approval"] for r in st.get(A.OFFERED_KEY) if r["slot"] == NEW_SLOT] == ["other-card"]


# ========================================================= Book as asked
class _BookingGhl(Recorder):
    """Records every call; create_appointment runs ``during_booking`` first
    (the window: a send starts while the call is being written) and returns
    APPT_ASKED; a cancel raises when ``refuse_cancel``."""

    def __init__(self, during_booking=None, refuse_cancel=False, fail_create=False):
        Recorder.__init__(self)
        self.during_booking = during_booking
        self.refuse_cancel = refuse_cancel
        self.fail_create = fail_create

    def create_appointment(self, *a, **k):
        self.calls.append(("create_appointment", a, k))
        hook, self.during_booking = self.during_booking, None
        if hook is not None:
            hook()
        if self.fail_create:
            raise RuntimeError("GHL 500 on create")
        return {"id": APPT_ASKED}

    def update_appointment_status(self, appointment_id, status, **k):
        self.calls.append(("update_appointment_status", (appointment_id, status), k))
        if status == "cancelled" and self.refuse_cancel:
            raise RuntimeError("GHL 500 on cancel")
        return {"id": appointment_id, "status": status}


def _asked_card(st):
    """Card c1 (a counter-proposal offering OFFERED) for a lead who asked for
    SLOT, outside Lorenzo's hours."""
    card = _plain(st, status="pending")
    st.set(A.APPROVAL_PREFIX + "c1", dict(_card(st), requested_slot=SLOT, requested_status="outside_window"))
    return A.load(card.token, st)


def _ghl_statuses(ghl):
    return [c[1] for c in ghl.calls if c[0] == "update_appointment_status"]


def test_book_as_asked_that_lost_its_card_to_the_send_cancels_the_call_it_booked(world):
    st = world["store"]
    card = _asked_card(st)
    box = {}
    ghl = _BookingGhl()
    ghl.during_booking = lambda: box.setdefault("send", A.approve(card.token, world["inst"], store=st, now=IN_HOURS,
                                                                  ghl=ghl))
    out = A.accept_requested(card.token, ghl, world["inst"], store=st, now=IN_HOURS)
    assert box["send"]["ok"] is True and box["send"]["status"] == "sent"
    assert out["ok"] is False and out["status"] == "sent" and out["booked"] is None
    assert out["error"] == ("the card changed meanwhile (it is now sent); Book as asked was not applied. The call "
                            "booked for Thu Oct 1 3:00pm CT was cancelled again")
    assert out["undone"] == {"slot": SLOT, "appointment_id": APPT_ASKED, "cancelled": True, "error": None}
    # one reply: the counter-proposal the card held when the send took it
    assert len(world["inst"].sent) == 1 and world["inst"].sent[0]["body"] == card.draft.body_text
    stored = _card(st)
    assert stored["status"] == "sent" and stored["draft"]["body_text"] == card.draft.body_text
    assert stored["token"] == card.token
    # the call was cancelled again, silently, and nothing of it is left
    assert ("update_appointment_status", (APPT_ASKED, "cancelled"), {"to_notify": False}) in ghl.calls
    assert (APPT_ASKED, "confirmed") not in _ghl_statuses(ghl)
    row = st.get(card.state_key)
    assert "booking" not in (row.get("cadence") or {}) and row["status"] != "call_booked"
    assert _events(st, card, "booked") == []
    assert _events(st, card, "book_as_asked_undone") == [{
        "at": IN_HOURS.isoformat(), "event": "book_as_asked_undone", "approval": "c1", "slot": SLOT,
        "appointment_id": APPT_ASKED, "cancelled": True}]
    assert not show_rate.is_held(st, APPT_ASKED) and st.get("appointment:%s" % APPT_ASKED) is None
    assert SLOT not in A.offered_slots(st, IN_HOURS)                       # its time is back in the pool
    assert [r["slot"] for r in _registry_rows(st, "c1")] == [OFFERED]      # the reply's own time stays held
    assert world["inst"].interest[-1] == (LEAD, card.campaign_id, 1)
    # one push, naming what was undone
    assert [n["title"] for n in _pushes(UNDONE_TITLE)] == [UNDONE_TITLE] and _pushes("NOT cancelled") == []
    msg = _pushes(UNDONE_TITLE)[0]["message"]
    assert msg == ("Book as asked for %s was not applied: card c1 moved while the call for Thu Oct 1 3:00pm CT was "
                   "being booked (its counter-proposal is the reply that went out). The engine cancelled that call "
                   "again in GHL without notifying the lead (shadow: recorded as would_do), gave its time back to "
                   "the pool, and set the opportunity back to New Reply and Instantly interest to 1." % LEAD)
    assert u"—" not in msg
    logged = _rows(world, "book_as_asked_undone")
    assert logged == [{"lead": LEAD, "approval": "c1", "card_status": "sent", "slot": SLOT,
                       "appointment_id": APPT_ASKED, "cancelled": True, "cancel_error": None,
                       "rescheduled_from": None, "other_call": None}]
    assert _rows(world, "accepted_requested") == []


def test_book_as_asked_that_lands_while_the_send_is_running_cancels_the_call_it_booked(world):
    st = world["store"]
    card = _asked_card(st)
    ghl = _BookingGhl()
    sender = _Sender(dict(world, ghl=ghl), card)
    ghl.during_booking = sender.start
    try:
        out = A.accept_requested(card.token, ghl, sender.inst, store=st, now=IN_HOURS)
        assert _card(st)["status"] == "sending"
    finally:
        sent = sender.finish()
    assert out["ok"] is False and out["status"] == "sending" and out["actionable_at"] == FREE_AT
    assert out["error"] == ("the card changed meanwhile (it is now sending); Book as asked was not applied. %s. The "
                            "call booked for Thu Oct 1 3:00pm CT was cancelled again" % RUNNING)
    assert sent["ok"] is True and _card(st)["status"] == "sent" and len(sender.inst.sent) == 1
    assert sender.inst.sent[0]["body"] == card.draft.body_text
    assert ("update_appointment_status", (APPT_ASKED, "cancelled"), {"to_notify": False}) in ghl.calls
    assert "booking" not in (st.get(card.state_key).get("cadence") or {})
    msg = _pushes(UNDONE_TITLE)[0]["message"]
    assert "(its counter-proposal is the reply going out now)" in msg and len(_pushes(UNDONE_TITLE)) == 1


def test_book_as_asked_whose_cancel_ghl_refuses_keeps_the_call_held_and_retried_with_one_push(world, monkeypatch):
    """Live fakes: GHL refuses the cancel. The call stays held (the lead
    hears nothing), its booking goes on the row marked cancel_failed so the
    retry finds it, and the one push carries the "I cancelled it" link."""
    st = world["store"]
    card = _asked_card(st)
    _go_live(monkeypatch)
    box = {}
    ghl = _BookingGhl(refuse_cancel=True)
    ghl.during_booking = lambda: box.setdefault("send", A.approve(card.token, world["inst"], store=st, now=IN_HOURS,
                                                                  ghl=ghl))
    out = A.accept_requested(card.token, ghl, world["inst"], store=st, now=IN_HOURS)
    assert box["send"]["ok"] is True and box["send"]["status"] == "sent" and len(world["inst"].sent) == 1
    assert out["ok"] is False and out["status"] == "sent" and out["booked"] == SLOT
    assert out["error"].endswith("The call booked for Thu Oct 1 3:00pm CT could not be cancelled (GHL 500 on "
                                 "cancel); it stays held and the cancel is retried")
    booking = st.get(card.state_key)["cadence"]["booking"]
    assert booking["appointment_id"] == APPT_ASKED and booking["cancel_failed"]["error"] == "GHL 500 on cancel"
    assert show_rate.is_held(st, APPT_ASKED)
    assert st.get(A.CANCEL_RETRY_PREFIX + card.state_key)["appointment_id"] == APPT_ASKED
    assert len(_rows(world, "booking_cancel_failed")) == 1
    pushes = _pushes(UNDONE_TITLE)
    assert len(pushes) == 1 and _pushes("Call NOT cancelled") == []
    assert "That call could NOT be cancelled: GHL refused (GHL 500 on cancel)." in pushes[0]["message"]
    assert pushes[0]["actions"] and "I cancelled it" in str(pushes[0]["actions"])
    assert _rows(world, "book_as_asked_undone")[0]["cancelled"] is False

    # the retry finds it on the row and finishes the cancel
    done = A.retry_failed_cancels(st, Recorder(), world["inst"], IN_HOURS + timedelta(minutes=5))
    assert [d.get("cancelled") for d in done] == [True]
    assert "booking" not in (st.get(card.state_key).get("cadence") or {})


def _newer_reply_books_another_call(st, card):
    """The window: a newer reply supersedes card c1 and its pipeline books
    the time that reply named, on the lead row, while Book as asked is still
    writing its own call to GHL."""
    def run():
        st.set(A.APPROVAL_PREFIX + "c1", dict(_card(st), status="superseded"))
        row = st.get(card.state_key)
        other = {"slot": OTHER_SLOT, "appointment_id": OTHER_APPT, "awaiting_approval": True, "owner": "c2"}
        st.set(card.state_key, dict(row, cadence=dict(row.get("cadence") or {}, booking=other)))
    return run


@pytest.mark.parametrize("refuse", [False, True], ids=["cancelled", "ghl_refused"])
def test_book_as_asked_never_overwrites_a_call_booked_on_the_row_meanwhile(world, monkeypatch, refuse):
    """The undo cancels only the call Book as asked made; the call a newer
    reply's card booked meanwhile stays on the row, untouched, and the push
    names it. A cancel GHL refuses cannot be retried from a row that holds
    another call, so it is left to Lorenzo by hand, without the "I cancelled
    it" link (that link finishes only the row's own cancel-pending call)."""
    st = world["store"]
    card = _asked_card(st)
    if refuse:
        _go_live(monkeypatch)
    ghl = _BookingGhl(during_booking=_newer_reply_books_another_call(st, card), refuse_cancel=refuse)
    out = A.accept_requested(card.token, ghl, world["inst"], store=st, now=IN_HOURS)
    assert out["ok"] is False and out["status"] == "superseded" and len(world["inst"].sent) == 0
    assert ("update_appointment_status", (APPT_ASKED, "cancelled"), {"to_notify": False}) in ghl.calls
    assert [s for s in _ghl_statuses(ghl) if s[0] == OTHER_APPT] == []       # the other call is never touched
    assert st.get(card.state_key)["cadence"]["booking"] == {
        "slot": OTHER_SLOT, "appointment_id": OTHER_APPT, "awaiting_approval": True, "owner": "c2"}
    assert [e.get("other_call") for e in _events(st, card, "book_as_asked_undone")] == [OTHER_APPT]
    assert [r["other_call"] for r in _rows(world, "book_as_asked_undone")] == [OTHER_APPT]
    pushes = _pushes(UNDONE_TITLE)
    assert len(pushes) == 1 and _pushes("Call NOT cancelled") == []
    msg = pushes[0]["message"]
    assert "(a newer reply from the lead replaced it; answer the card for that reply instead)" in msg
    assert "lead's row now holds another call (appointment %s for Fri Oct 2 1:00pm CT)" % OTHER_APPT in msg
    assert u"—" not in msg
    if not refuse:
        assert out["booked"] is None
        assert out["error"].endswith("The call booked for Thu Oct 1 3:00pm CT was cancelled again")
        # CT3 prerequisite (flag 20): the undo no longer sets the opportunity
        # and the interest back under the other call; the push says so.
        assert msg.endswith("It left the opportunity and the Instantly interest as they are, because the lead's "
                            "row now holds another call (appointment %s for Fri Oct 2 1:00pm CT), booked while "
                            "this one was being booked." % OTHER_APPT)
        assert (LEAD, card.campaign_id, 1) not in world["inst"].interest
        assert [c for c in ghl.calls if c[0] == "update_opportunity_stage"] == []
        assert [r["reset_skipped"] for r in _rows(world, "book_as_asked_undone")] == ["other_call"]
        assert SLOT not in A.offered_slots(st, IN_HOURS)
        return
    assert out["booked"] == SLOT
    assert out["error"].endswith("The call booked for Thu Oct 1 3:00pm CT could not be cancelled (GHL 500 on "
                                 "cancel), and the lead's row now holds another call, so it is not retried: cancel "
                                 "it in GHL by hand")
    assert msg.endswith("Cancel appointment %s in GHL by hand, without notifying the lead." % APPT_ASKED)
    assert not pushes[0].get("actions")
    assert show_rate.is_held(st, APPT_ASKED)                                  # the lead hears nothing meanwhile
    assert len(_rows(world, "booking_cancel_failed")) == 1                    # which fails the deploy watch
    # the retry pass drops the retry it cannot finish and never touches the other call
    later = Recorder()
    assert A.retry_failed_cancels(st, later, world["inst"], IN_HOURS + timedelta(minutes=5)) == []
    assert later.calls == [] and st.get(A.CANCEL_RETRY_PREFIX + card.state_key) is None
    assert st.get(card.state_key)["cadence"]["booking"]["appointment_id"] == OTHER_APPT


def test_book_as_asked_that_booked_nothing_and_lost_its_card_only_refuses(world):
    """GHL refused to create the call, and the send took the card meanwhile:
    nothing to undo, no push, and the sent card is never put back to
    pending with the booking's "NOT SENT" note."""
    st = world["store"]
    card = _asked_card(st)
    box = {}
    ghl = _BookingGhl(fail_create=True)
    ghl.during_booking = lambda: box.setdefault("send", A.approve(card.token, world["inst"], store=st, now=IN_HOURS,
                                                                  ghl=ghl))
    out = A.accept_requested(card.token, ghl, world["inst"], store=st, now=IN_HOURS)
    assert out == {"ok": False, "status": "sent", "booked": None,
                   "error": "the card changed meanwhile (it is now sent); Book as asked was not applied"}
    stored = _card(st)
    assert stored["status"] == "sent" and stored["draft"]["body_text"] == card.draft.body_text
    assert _ghl_statuses(ghl) == [] and _pushes(UNDONE_TITLE) == [] and _rows(world, "book_as_asked_undone") == []
    assert len(world["inst"].sent) == 1


def test_book_as_asked_pressed_again_as_the_queue_sends_its_confirmation_leaves_the_call_alone(world, monkeypatch):
    """Book as asked at 20:00 booked the call and queued the confirmation.
    Pressed again just as the 07:00 queue sends it: book() finds the call
    already on the calendar (no second write), the card's write loses to the
    send, and the call that confirmation just confirmed is not cancelled."""
    st = world["store"]
    card = _asked_card(st)
    ghl = _BookingGhl()
    first = A.accept_requested(card.token, ghl, world["inst"], store=st, now=AFTER_HOURS)
    assert first["ok"] is True and first["status"] == "approved_queued" and first["booked"] == SLOT
    morning = ct(2026, 9, 29, 7, 5)
    box = _send_after_the_read(monkeypatch, lambda: A.flush_queued(world["inst"], store=st, now=morning, ghl=ghl))
    out = A.accept_requested(first["token"], ghl, world["inst"], store=st, now=morning)
    assert [r["status"] for r in box["send"]] == ["sent"]
    assert out == {"ok": False, "status": "sent", "booked": None,
                   "error": "the card changed meanwhile (it is now sent); Book as asked was not applied"}
    assert _ghl_statuses(ghl) == [(APPT_ASKED, "confirmed")]              # confirmed once, never cancelled
    assert len([c for c in ghl.calls if c[0] == "create_appointment"]) == 1
    booking = st.get(card.state_key)["cadence"]["booking"]
    assert booking["appointment_id"] == APPT_ASKED and booking["confirmed_by"] == "c1"
    assert _pushes(UNDONE_TITLE) == [] and _rows(world, "book_as_asked_undone") == []
    assert len(world["inst"].sent) == 1


def test_book_as_asked_that_wins_its_write_books_and_sends_as_before(world):
    st = world["store"]
    card = _asked_card(st)
    ghl = _BookingGhl()
    out = A.accept_requested(card.token, ghl, world["inst"], store=st, now=IN_HOURS)
    assert out["ok"] is True and out["status"] == "sent" and out["booked"] == SLOT
    assert len(world["inst"].sent) == 1 and world["inst"].sent[0]["body"] != card.draft.body_text
    booking = st.get(card.state_key)["cadence"]["booking"]
    assert booking["appointment_id"] == APPT_ASKED and booking["confirmed_by"] == "c1"
    assert (APPT_ASKED, "confirmed") in _ghl_statuses(ghl) and (APPT_ASKED, "cancelled") not in _ghl_statuses(ghl)
    # the counter-proposal's time went back to the pool; the card holds what its confirmation names
    assert [r["slot"] for r in _registry_rows(st, "c1")] == [SLOT]
    assert len(_rows(world, "accepted_requested")) == 1 and _pushes(UNDONE_TITLE) == []
