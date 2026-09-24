"""S-rest round 4, the approval side (services/reply_engine/approval.py).

Defect 1 (the reviewer's P14 family). A positive reply the lead SENT before
their opt-out, but processed after it (a poller retry, a reply a killed run
still held), made the opt-out look older than the card: the card went out
and the ladder armed. Every "may this lead still be emailed" decision in
approval.py now goes through one helper, _lead_reply_verdict:

* the sticky opt-out marker (LeadState.opt_out) holds and refuses, whatever
  order the replies were processed in;
* "a newer reply than the card" compares when the lead SENT each reply (the
  history entry's received_at, falling back to its processing time ``at``)
  with the card's own reply time (the card context's reply_at), never the
  position in processed_email_ids.

Defect 3. The HELD push: an opt-out or a final no says Veto and do not reply
(never "reply by hand"; wrong person cites offers.md rule 7); only "the lead
wrote again" says reply by hand. The arrival push carries the booked-call
note, a card already held for the same reason is not held or announced
again, and an opt-out holds a send_failed card whose old claim is stale.

Mark sent (defect 2's operator action): mark_sent_manually moves a
send_failed card to sent_manually and does what a real send does after the
Instantly call, and mark_sent_url builds its link.

Every lead is an example.com address; every client is an in-process fake.
Live mode is only ever set in-process with monkeypatch.
"""
from datetime import timedelta

import pytest
import pytz

from shared import notify
from shared.store import JsonFileStore

from services.reply_engine import approval as A
from services.reply_engine import show_rate
from services.reply_engine.models import LeadState

from test_send_safety_round2 import FakeInstantly as ThreadReader, _go_live
from test_send_safety_srest_r3_optout import (  # noqa: F401 - the r3 world, fakes and card helper
    APPT, CAMPAIGN, EACCOUNT, IN_HOURS, LEAD, POSITIVE, FakeInstantly, Recorder, _alerts, _direct_card,
    _registry_rows, _reply, ct, world,
)

T_POS = ct(2026, 9, 28, 9, 0)         # the lead sends a positive reply (e-1)
T_OUT = ct(2026, 9, 28, 9, 30)        # ...and then an opt-out or a final no (e-2)
P_OUT = ct(2026, 9, 28, 9, 31)        # the opt-out is processed first
P_POS = ct(2026, 9, 28, 9, 40)        # the positive one after it (a poller retry)
AFTER_HOURS = ct(2026, 9, 28, 20, 0)
SLOT = "2026-10-01T15:00:00-05:00"    # Thu Oct 1 3:00pm CT: the booked call
POSITIVE_CLS = {"label": "positive_question", "confidence": 1.0, "method": "rules", "reason": "x"}

OPT_OUTS = [
    ("unsubscribe", "asked to be removed"),
    ("negative_hostile", "sent a hostile reply"),
    ("wrong_person", "said they are the wrong person"),
    ("negative_notfit", "said it is not a fit"),
    ("negative_notnow", "said not now"),
]


def _utc(dt):
    return dt.astimezone(pytz.utc).isoformat()


def _entry(email_id, label, received, processed=None):
    """An inbound history entry as the round-4 pipeline writes it: ``at`` is
    when it was processed, ``received_at`` when the lead sent it. received
    None writes an entry from before received_at existed (``at`` only)."""
    entry = {"at": (processed or received).isoformat(), "event": "inbound", "email_id": email_id,
             "label": label, "source": "webhook"}
    if received is not None:
        entry["received_at"] = _utc(received)
    return entry


def _marker(label="unsubscribe", email_id="e-2", received=T_OUT, set_at=P_OUT):
    return {"label": label, "email_id": email_id, "received_at": _utc(received), "set_at": set_at.isoformat()}


def _row(st, tokens, processed, history, status="draft_pending_approval", classification=None, marker=None,
         cadence=None):
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Owner", eaccount=EACCOUNT,
                      approvals=list(tokens), processed_email_ids=list(processed), cadence=cadence or {})
    row = dict(state.to_store(), history=list(history), status=status, classification=classification,
               opt_out=marker)
    last = history[-1] if history else {}
    row["last_email_id"] = last.get("email_id")
    row["last_inbound_at"] = last.get("at")
    st.set(state.key, row)
    return state.key


def _context(st, card_id, reply_at, processed_before):
    key = A.APPROVAL_CONTEXT_PREFIX + card_id
    st.set(key, dict(st.get(key) or {}, reply_at=reply_at.isoformat() if reply_at is not None else None,
                     processed_before=list(processed_before)))


def _p14_card(st, status="pending"):
    """The card for e-1, raised when e-1 was processed (after the opt-out):
    the opt-out was already on the row, so it is in processed_before."""
    card = _direct_card(st, "c1", status=status, email_id="e-1", created=P_POS)
    _context(st, "c1", T_POS, ["e-2"])
    return card


def _p14_row(st, card, label="unsubscribe", marker=True):
    """The row the P14 race leaves: the opt-out processed first, the older
    positive after it, which rewrote the status and classification (the
    round-3 bug the pipeline no longer commits; the row says it anyway)."""
    return _row(st, [card.token], ["e-2", "e-1"],
                [_entry("e-2", label, T_OUT, P_OUT), _entry("e-1", "positive_question", T_POS, P_POS)],
                classification=POSITIVE_CLS, marker=_marker(label) if marker else None)


def _pushes():
    return list(notify.sent_in_test)


def _rows(world, status):
    return [r[2] for r in world["rows"] if r[0] == "reply_engine.approval" and r[1] == status]


# ============================================================ defect 1: P14
@pytest.mark.parametrize("when", [IN_HOURS, AFTER_HOURS], ids=["send", "queue"])
@pytest.mark.parametrize("marker", [True, False], ids=["marker", "history_only"])
@pytest.mark.parametrize("label,said", OPT_OUTS, ids=[o[0] for o in OPT_OUTS])
def test_p14_a_reply_sent_before_the_opt_out_but_processed_after_it_never_goes_out(world, label, said, marker,
                                                                                  when):
    """P14 and P14d: whatever the order the replies were processed in, and
    with the status and classification rewritten by the older reply."""
    st = world["store"]
    card = _p14_card(st)
    _p14_row(st, card, label, marker)
    row = st.get(card.state_key)
    # By processing order the opt-out came first and the card saw it: the
    # round-3 rule found nothing newer, and the status says positive.
    assert row["processed_email_ids"] == ["e-2", "e-1"] and row["status"] == "draft_pending_approval"
    why = A.lead_reply_hold(row, card, ["e-2"], reply_at=T_POS.isoformat())
    assert why["reason"] == "opt_out" and why["category"] == label and why["email_id"] == "e-2"
    refusal = A.arm_refusal(row, card, {}, seen_before=["e-2"], reply_at=T_POS.isoformat())
    assert refusal == ("opt_out:%s" % label if marker else "newer_inbound:e-2")

    out = A.approve(card.token, world["inst"], store=st, now=when, ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and out["held"] is True
    assert out["lead_reply"]["category"] == label
    assert world["inst"].sent == [] and world["inst"].interest == [] and world["ghl"].calls == []
    stored = A.load(card.token, st)
    assert stored.status == "blocked" and _registry_rows(st, "c1") == []
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") is None
    assert st.get(card.state_key)["cadence"] == {}                     # the ladder was never armed
    assert len(_alerts("Reply to %s HELD: the lead %s" % (LEAD, said))) == 1
    A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 29, 7, 5), ghl=world["ghl"])
    assert world["inst"].sent == []


def test_p14c_live_fakes_a_queued_card_sends_nothing_and_arms_nothing(world, monkeypatch):
    """P14c: approved and queued before the opt-out landed, then the older
    positive reply was processed after it. Live mode (in-process only), live
    fakes: the morning flush holds the card before any Instantly or GHL call."""
    st = world["store"]
    card = _p14_card(st, status="approved_queued")
    st.set(A.APPROVAL_PREFIX + "c1", dict(st.get(A.APPROVAL_PREFIX + "c1"),
                                          send_after=ct(2026, 9, 29, 7, 0).isoformat()))
    _p14_row(st, card, "unsubscribe", marker=True)
    _go_live(monkeypatch)
    inst, ghl = FakeInstantly(), Recorder()
    out = A.flush_queued(inst, store=st, now=ct(2026, 9, 29, 7, 5), ghl=ghl)
    assert [(r["ok"], r["status"]) for r in out] == [(False, "blocked")]
    assert out[0]["lead_reply"] == {"reason": "opt_out", "category": "unsubscribe", "email_id": "e-2",
                                    "at": _utc(T_OUT)}
    assert inst.sent == [] and inst.interest == [] and ghl.calls == []
    assert st.get(card.state_key)["cadence"] == {}
    again = A.approve(card.token, inst, store=st, now=ct(2026, 9, 29, 7, 10), ghl=ghl)
    assert again["ok"] is False and inst.sent == []


def test_p14b_the_pipeline_sends_nothing_for_an_older_positive_processed_after_the_opt_out(world):
    """P14b through process_event: the opt-out is processed first, the older
    positive reply after it. Whatever the pipeline makes of the older reply,
    nothing reaches the lead and nothing is armed."""
    st = world["store"]
    out2 = _reply(world, "e-2", "Please remove me from your list", T_OUT, P_OUT)
    assert out2["label"] == "unsubscribe"
    out1 = _reply(world, "e-1", POSITIVE, T_POS, P_POS)
    token = out1.get("approval_token")
    if token:
        res = A.approve(token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
        assert res["ok"] is False
    A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 29, 7, 5), ghl=world["ghl"])
    assert world["inst"].sent == []
    assert not (st.get(out2["state_key"]).get("cadence") or {}).get("armed_at")


def test_a_reply_sent_after_the_cards_holds_it_even_when_processed_before_the_card(world):
    """Not an opt-out: the lead wrote again (sent 9:30), and that reply was
    processed before the older one this card answers (sent 9:00)."""
    st = world["store"]
    card = _p14_card(st)
    _row(st, [card.token], ["e-2", "e-1"],
         [_entry("e-2", "neutral_question", T_OUT, P_OUT), _entry("e-1", "positive_question", T_POS, P_POS)])
    row = st.get(card.state_key)
    assert [r["email_id"] for r in A.lead_replies_after(row, card, ["e-2"], reply_at=T_POS.isoformat())] == ["e-2"]
    assert A.arm_refusal(row, card, {}, seen_before=["e-2"], reply_at=T_POS.isoformat()) == "newer_inbound:e-2"
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is False and out["lead_reply"]["reason"] == "newer_reply" and world["inst"].sent == []


def test_an_older_reply_processed_after_the_card_does_not_hold_it(world):
    """The other direction: by position e-1 is "after" the card's e-2, but
    the lead sent it first. Time decides, so the card goes out and arms."""
    st = world["store"]
    card = _direct_card(st, "c2", email_id="e-2", created=P_OUT)
    _context(st, "c2", T_OUT, [])
    _row(st, [card.token], ["e-2", "e-1"],
         [_entry("e-2", "positive_question", T_OUT, P_OUT), _entry("e-1", "neutral_question", T_POS, P_POS)])
    row = st.get(card.state_key)
    assert A.lead_replies_after(row, card, [], reply_at=T_OUT.isoformat()) == []
    assert A.lead_reply_hold(row, card, [], reply_at=T_OUT.isoformat()) is None
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent" and out["cadence"]["armed"] is True
    assert len(world["inst"].sent) == 1


def test_a_machine_reply_sent_after_the_card_never_holds_it(world):
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    _row(st, [card.token], ["e-1", "e-2"],
         [_entry("e-1", "positive_question", T_POS), _entry("e-2", "ooo", T_OUT, P_OUT)])
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent" and out["cadence"]["armed"] is True


# ------------------------------------------------------------- the fallbacks
def test_an_entry_without_received_at_is_timed_by_when_it_was_processed(world):
    """A row written before received_at existed: the opt-out's entry has only
    ``at`` (9:31). Its place in processed_email_ids (before the card's own
    email) would call it older; its time says it came after the 9:00 reply
    this card answers."""
    st = world["store"]
    card = _p14_card(st)
    _row(st, [card.token], ["e-2", "e-1"],
         [_entry("e-2", "unsubscribe", None, P_OUT), _entry("e-1", "positive_question", T_POS, P_POS)],
         classification=POSITIVE_CLS)
    row = st.get(card.state_key)
    why = A.lead_reply_hold(row, card, ["e-2"], reply_at=T_POS.isoformat())
    assert why == {"reason": "opt_out", "category": "unsubscribe", "at": P_OUT.isoformat(), "email_id": "e-2"}


def test_a_card_without_reply_at_is_timed_by_its_source_entry(world):
    """A card whose context row predates reply_at: the card's time is its
    source entry's received_at (9:00), not when it was processed (9:40)."""
    st = world["store"]
    card = _p14_card(st)
    _context(st, "c1", None, ["e-2"])
    _p14_row(st, card, "negative_notfit", marker=False)
    row = st.get(card.state_key)
    assert A.card_reply_time(row, card) == T_POS
    why = A.lead_reply_hold(row, card, ["e-2"], reply_at=None)
    assert why["reason"] == "opt_out" and why["category"] == "negative_notfit"


def test_a_reply_with_no_time_at_all_falls_back_to_the_processing_order(world):
    """Only an id with no history entry (no real row has one: the pipeline
    writes the entry and the id together) is ordered by position, or, when
    the card's own email was never recorded as processed, by processed_before."""
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    after = st.get(_row(st, [card.token], ["e-1", "e-2"], []))
    assert [r["email_id"] for r in A.lead_replies_after(after, card)] == ["e-2"]
    assert A.lead_reply_hold(after, card)["category"] == "unlabelled"
    before = st.get(_row(st, [card.token], ["e-2", "e-1"], []))
    assert A.lead_replies_after(before, card) == []
    gap = st.get(_row(st, [card.token], ["e-2"], []))                   # the card's own email never recorded
    assert [r["email_id"] for r in A.lead_replies_after(gap, card, seen_before=[])] == ["e-2"]
    assert A.lead_replies_after(gap, card, seen_before=["e-2"]) == []
    assert A.lead_replies_after(gap, card, seen_before=None) == []


def test_the_opt_out_marker_holds_even_when_the_history_does_not_reach_back_to_it(world):
    """Only the marker says it (the history was trimmed, the status and
    classification were rewritten): it still holds and refuses."""
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)], classification=POSITIVE_CLS,
         marker=_marker("wrong_person"))
    row = st.get(card.state_key)
    assert A.lead_reply_hold(row, card)["category"] == "wrong_person"
    assert A.arm_refusal(row, card, {}) == "opt_out:wrong_person"
    # a marker that cannot be read is still a marker
    st.set(card.state_key, dict(row, opt_out={"malformed": "x"}))
    assert A.lead_reply_hold(st.get(card.state_key), card)["reason"] == "opt_out"


def test_book_as_asked_on_an_opted_out_lead_books_nothing(world):
    """accept_requested asks the same helper before book() touches GHL."""
    st = world["store"]
    card = _p14_card(st)
    st.set(A.APPROVAL_PREFIX + "c1", dict(st.get(A.APPROVAL_PREFIX + "c1"), requested_slot=SLOT,
                                          requested_status="outside_window"))
    _p14_row(st, card, "unsubscribe", marker=True)
    out = A.accept_requested(card.token, world["ghl"], world["inst"], store=st, now=IN_HOURS)
    assert out["ok"] is False and out["status"] == "blocked" and out["lead_reply"]["category"] == "unsubscribe"
    assert world["ghl"].calls == [] and world["inst"].sent == []


def test_vetoing_a_held_card_keeps_the_leads_opt_out_status(world):
    """The HELD push says Veto. The veto must not wipe the no off the row."""
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    _row(st, [card.token], ["e-1", "e-2"],
         [_entry("e-1", "positive_question", T_POS), _entry("e-2", "unsubscribe", T_OUT, P_OUT)],
         status="blocklisted", classification={"label": "unsubscribe", "confidence": 1.0, "method": "rules",
                                               "reason": "x"}, marker=_marker())
    assert A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])["status"] == "blocked"
    assert A.veto(card.token, store=st, now=IN_HOURS, ghl=world["ghl"], instantly=world["inst"])["ok"] is True
    row = st.get(card.state_key)
    assert row["status"] == "blocklisted" and row["history"][-1]["event"] == "vetoed"


# ======================================================= defect 3: wording
WORDING = [
    ("unsubscribe", "asked to be removed", "Do not reply to them: they asked not to be emailed."),
    ("negative_hostile", "sent a hostile reply", "Do not reply to them: they asked not to be emailed."),
    ("wrong_person", "said they are the wrong person", "Do not email from this thread"),
    ("negative_notfit", "said it is not a fit", "Do not reply to them: they said it is not a fit."),
    ("negative_notnow", "said not now", "Do not reply to them now: they said not now."),
    ("blocklisted", "asked to be removed (blocklisted)", "Do not reply to them: they asked not to be emailed."),
    ("lost", "said it is not a fit (lost)", "Do not reply to them: they said it is not a fit."),
    ("follow_up_later", "said not now", "Do not reply to them now: they said not now."),
    ("needs_review", "sent a removal-style reply the engine held for your review",
     "Read their reply before anything else goes to them"),
]


@pytest.mark.parametrize("category,said,advice", WORDING, ids=[w[0] for w in WORDING])
def test_the_held_push_for_an_opt_out_says_veto_and_never_reply_by_hand(world, category, said, advice):
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)])
    why = {"reason": "opt_out", "category": category, "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=P_OUT, lead=LEAD) == ["c1"]
    push = _alerts("Reply to %s HELD: the lead %s" % (LEAD, said))
    assert len(push) == 1
    msg = push[0]["message"]
    assert msg.startswith("Nothing was sent.") and advice in msg and "Veto it." in msg
    assert "by hand" not in msg and "raised no new card" not in msg
    problem = [p for p in A.load(card.token, st).draft.problems if "this reply must not go out" in p]
    assert len(problem) == 1 and advice in problem[0] and "Veto the card" in problem[0]
    assert "by hand" not in problem[0] and "Mon Sep 28 9:30am CT" in problem[0]
    if category == "wrong_person":
        assert "offers.md rule 7" in msg and "offers.md rule 7" in problem[0]
    assert u"\u2014" not in msg + problem[0] + push[0]["title"]
    assert A.lead_hold_record(st.get(A.APPROVAL_PREFIX + "c1")) == {
        "reason": "opt_out", "category": category, "email_id": "e-2", "at": _utc(T_OUT), "held_at": P_OUT.isoformat()}


def test_the_held_push_for_a_newer_reply_says_read_the_thread_or_reply_by_hand(world):
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    _row(st, [card.token], ["e-1", "e-2"],
         [_entry("e-1", "positive_question", T_POS), _entry("e-2", "neutral_question", T_OUT, P_OUT)])
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["status"] == "blocked" and out["lead_reply"]["reason"] == "newer_reply"
    push = _alerts("Reply to %s HELD: the lead wrote again" % LEAD)
    assert len(push) == 1
    msg = push[0]["message"]
    assert msg.startswith("Nothing was sent.") and "reply by hand" in msg
    assert "Read the thread and any newer card for this lead" in msg and "raised no new card" not in msg
    problem = A.lead_reply_problem({"reason": "newer_reply", "category": "neutral_question", "at": _utc(T_OUT)})
    assert "reply by hand" in problem and "raised no new card" not in problem and "any newer card" in problem
    assert u"\u2014" not in msg + problem


def test_the_arrival_push_carries_the_booked_call_note(world):
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", offered=[SLOT], created=T_POS)
    booking = {"slot": SLOT, "appointment_id": APPT, "awaiting_approval": True, "owner": "c1",
               "booked_at": T_POS.isoformat()}
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)], cadence={"booking": booking})
    why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=P_OUT, lead=LEAD) == ["c1"]
    msg = _alerts("HELD: the lead asked to be removed")[0]["message"]
    assert "This card holds the call booked for Thu Oct 1 3:00pm CT (invite withheld)" in msg
    assert "Veto the card to cancel it." in msg and "by hand" not in msg


def test_the_arrival_push_names_the_card_that_holds_the_call(world):
    st = world["store"]
    owner = _direct_card(st, "c1", email_id="e-1", offered=[SLOT], created=T_POS)
    other = _direct_card(st, "c2", email_id="e-3", offered=["2026-10-02T13:00:00-05:00"], created=T_POS)
    booking = {"slot": SLOT, "appointment_id": APPT, "awaiting_approval": True, "owner": "c1",
               "booked_at": T_POS.isoformat()}
    _row(st, [other.token, owner.token], ["e-3", "e-1"],
         [_entry("e-3", "positive_question", T_POS), _entry("e-1", "positive_question", T_POS)],
         cadence={"booking": booking})
    why = {"reason": "opt_out", "category": "negative_hostile", "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [other.token, owner.token], why, now=P_OUT, lead=LEAD) == ["c2", "c1"]
    msg = _alerts("HELD: the lead sent a hostile reply")[0]["message"]
    assert "Cards c2, c1 are now blocked" in msg and "Veto them." in msg
    assert "Card c1 holds the call booked for Thu Oct 1 3:00pm CT (invite withheld): Veto that card to cancel it." \
        in msg


# ------------------------------------------------- no second hold, no second push
def test_a_card_already_held_for_an_opt_out_is_not_held_or_announced_again(world):
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)])
    first = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [card.token], first, now=P_OUT, lead=LEAD) == ["c1"]
    before, stored = len(_pushes()), st.get(A.APPROVAL_PREFIX + "c1")
    second = {"reason": "opt_out", "category": "negative_hostile", "at": _utc(ct(2026, 9, 28, 11, 0)),
              "email_id": "e-3"}
    assert A.hold_cards_for_lead_reply(st, [card.token], second, now=ct(2026, 9, 28, 11, 1), lead=LEAD) == []
    assert len(_pushes()) == before and st.get(A.APPROVAL_PREFIX + "c1") == stored
    # the send path cannot re-announce it either: a blocked card is not sendable
    again = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert again["ok"] is False and "already blocked" in again["error"] and len(_pushes()) == before


def test_a_card_blocked_before_the_hold_record_existed_is_read_from_its_problem(world):
    st = world["store"]
    card = _direct_card(st, "c1", status="blocked", email_id="e-1", created=T_POS)
    why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
    raw = st.get(A.APPROVAL_PREFIX + "c1")
    raw["draft"]["problems"] = [A.lead_reply_problem(why)]
    st.set(A.APPROVAL_PREFIX + "c1", raw)
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)])
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=P_OUT, lead=LEAD) == []
    assert _pushes() == []


def test_a_card_held_because_the_lead_wrote_again_is_held_again_for_their_opt_out(world):
    """What to do changes (do not reply), so this one is re-held and pushed."""
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    _row(st, [card.token], ["e-1", "e-2"],
         [_entry("e-1", "positive_question", T_POS), _entry("e-2", "neutral_question", T_OUT, P_OUT)])
    assert A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])["status"] == "blocked"
    assert len(_alerts("HELD: the lead wrote again")) == 1
    why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(ct(2026, 9, 28, 10, 30)), "email_id": "e-3"}
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=ct(2026, 9, 28, 10, 31), lead=LEAD) == ["c1"]
    assert len(_alerts("HELD: the lead asked to be removed")) == 1
    stored = A.load(card.token, st)
    assert A.lead_hold_record(stored)["reason"] == "opt_out"
    assert any("wrote again" in p for p in stored.draft.problems)
    assert any("this reply must not go out" in p for p in stored.draft.problems)


# ------------------------------------------ send_failed: the stale send claim
def test_an_opt_out_holds_a_send_failed_card_and_drops_its_stale_claim(world):
    st = world["store"]
    card = _direct_card(st, "c1", status="send_failed", email_id="e-1", created=T_POS)
    st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)])
    why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=P_OUT, lead=LEAD) == ["c1"]
    stored = A.load(card.token, st)
    assert stored.status == "blocked" and _registry_rows(st, "c1") == []
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") is None
    assert A.card_context(st, "c1")["send_attempts"] == 1                 # the attempt is on record...
    history = A.card_history(st, stored)
    assert history["send_started"] is True and history["approved"] is True  # ...so no text says "never sent"
    problem = [p for p in stored.draft.problems if "this reply must not go out" in p][0]
    assert ("nothing more was sent (an earlier send attempt from this card failed and may have reached the lead)"
            in problem)
    msg = _alerts("HELD: the lead asked to be removed")[0]["message"]
    assert msg.startswith("Nothing more was sent.")
    assert ("Card c1 had an earlier send attempt that failed: nothing of it is still in flight, but it may have "
            "reached the lead, so check the Instantly thread." in msg)
    logged = _rows(world, "blocked_lead_replied")
    assert logged and logged[-1]["approvals"] == ["c1"] and logged[-1]["earlier_send"] == ["c1"]
    assert A.retry(card.token, store=st, now=IN_HOURS)["ok"] is False
    assert A.mark_sent_manually("c1", IN_HOURS, store=st)["ok"] is False


def test_the_stale_claim_stays_when_its_attempt_cannot_be_recorded(world, monkeypatch):
    """No record, no drop: the claim is the only proof a send started."""
    st = world["store"]
    card = _direct_card(st, "c1", status="send_failed", email_id="e-1", created=T_POS)
    st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)])

    def broken(*a, **k):
        raise IOError("store write timed out")

    monkeypatch.setattr(A, "_note_card_history", broken)
    why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=P_OUT, lead=LEAD) == ["c1"]
    assert A.load(card.token, st).status == "blocked" and st.get(A.SEND_CLAIM_PREFIX + "c1") is not None


def test_a_pending_card_mid_send_is_still_left_to_the_send(world):
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=T_POS)
    st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)])
    why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=P_OUT, lead=LEAD) == []
    assert A.load(card.token, st).status == "pending" and st.get(A.SEND_CLAIM_PREFIX + "c1") is not None


def test_a_retried_card_held_at_send_says_nothing_more_was_sent(world):
    st = world["store"]
    card = _direct_card(st, "c1", status="send_failed", email_id="e-1", created=T_POS)
    st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    _row(st, [card.token], ["e-1"], [_entry("e-1", "positive_question", T_POS)])
    retried = A.retry(card.token, store=st, now=ct(2026, 9, 28, 9, 20))
    assert retried["ok"] is True
    _row(st, [card.token], ["e-1", "e-2"],
         [_entry("e-1", "positive_question", T_POS), _entry("e-2", "unsubscribe", T_OUT, P_OUT)],
         status="blocklisted", marker=_marker())
    out = A.approve(retried["token"], world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["status"] == "blocked" and world["inst"].sent == []
    assert any("nothing more was sent" in p for p in out["problems"])
    assert _alerts("HELD: the lead asked to be removed")[0]["message"].startswith("Nothing more was sent.")


# ================================================================ Mark sent
def _booked(st, card_id="c1", status="send_failed", created=T_POS, marker=None, history=None, model=None):
    """A card that owns the lead's unconfirmed call for SLOT, the reminder
    ladder held, as booking.book() leaves it at classification time."""
    card = _direct_card(st, card_id, status=status, email_id="e-1", offered=[SLOT], created=created)
    if model:
        raw = st.get(A.APPROVAL_PREFIX + card_id)
        raw["draft"]["model"] = model
        st.set(A.APPROVAL_PREFIX + card_id, raw)
    booking = {"slot": SLOT, "appointment_id": APPT, "awaiting_approval": True, "owner": card_id,
               "booked_at": created.isoformat()}
    show_rate.hold(st, APPT, reason="awaiting_approval", now=created, meta={"lead_email": LEAD, "start_iso": SLOT})
    _row(st, [card.token], ["e-1"], history or [_entry("e-1", "positive_question", created)],
         cadence={"booking": booking}, marker=marker)
    return card


def _plain(st, card_id="c1", status="send_failed", created=T_POS, marker=None, history=None):
    card = _direct_card(st, card_id, status=status, email_id="e-1", created=created)
    _row(st, [card.token], ["e-1"], history or [_entry("e-1", "positive_question", created)], marker=marker)
    return card


def test_mark_sent_records_the_reply_as_sent_and_arms_the_ladder(world):
    st = world["store"]
    card = _plain(st)
    failed_at = ct(2026, 9, 28, 9, 5).isoformat()
    st.set(A.APPROVAL_PREFIX + "c1", dict(st.get(A.APPROVAL_PREFIX + "c1"), decided_at=failed_at))
    out = A.mark_sent_manually("c1", IN_HOURS, store=st)
    assert out["ok"] is True and out["status"] == "sent_manually" and out["first_reply"] is True
    assert out["cadence"]["armed"] is True and out["lead_reply"] is None and out["booking_left_held"] is None
    assert out["invite"] is None and out["alerts"] == [] and out["send_failed_at"] == failed_at

    stored = st.get(A.APPROVAL_PREFIX + "c1")
    assert stored["status"] == "sent_manually" and stored["decided_at"] == IN_HOURS.isoformat()
    assert stored["notify_result"][A.MARK_SENT_KEY] == {"at": IN_HOURS.isoformat(), "by": "lorenzo",
                                                        "send_failed_at": failed_at}
    row = st.get(card.state_key)
    assert row["status"] == "replied_awaiting_booking" and row["last_outbound_at"] == IN_HOURS.isoformat()
    assert row["offered_slots"] == card.draft.offered_slots
    assert row["cadence"]["armed_at"] == IN_HOURS.isoformat() and row["cadence"]["armed_for_email_id"] == "e-1"
    entry = row["history"][-1]
    assert entry["event"] == "reply_sent_manually" and entry["approval"] == "c1" and entry["by"] == "lorenzo"
    assert entry["reply_at"] == T_POS.isoformat() and entry["sent_at"] == IN_HOURS.isoformat()
    assert entry["first_reply"] is True and entry["send_failed_at"] == failed_at
    logged = _rows(world, "sent_manually")
    assert len(logged) == 1 and logged[0]["approval"] == "c1" and logged[0]["reply_at"] == T_POS.isoformat()
    assert logged[0]["sent_at"] == IN_HOURS.isoformat() and logged[0]["first_reply"] is True
    assert logged[0]["cadence_armed"] is True and _rows(world, "mark_sent_record_not_updated") == []
    # the bookkeeping of a sent card: a send claim, the offered times still
    # reserved, and the history proves the send
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") and _registry_rows(st, "c1")
    history = A.card_history(st, A.load(card.token, st))
    assert history["approved"] is True and history["send_started"] is True
    assert world["inst"].sent == [] and world["ghl"].calls == []           # nothing was sent from Mark sent


def test_mark_sent_takes_the_token_too_and_refuses_anything_but_send_failed(world):
    st = world["store"]
    # A lead a reply of ours already reached: a pending card is not a
    # first-contact card, so Mark sent still refuses it (a first-contact one
    # it takes: test_card_lead_reply_and_first_contact).
    card = _plain(st, history=[_entry("e-1", "positive_question", T_POS), {"event": "reply_sent", "at": T_POS.isoformat()}])
    other = _direct_card(st, "c2", status="pending", email_id="e-3", offered=[])
    assert A.mark_sent_manually("nope", IN_HOURS, store=st) == {"ok": False, "error": "unknown card"}
    refused = A.mark_sent_manually("c2", IN_HOURS, store=st)
    assert refused["ok"] is False and refused["status"] == "pending" and "send_failed" in refused["error"]
    assert A.load(other.token, st).status == "pending"
    assert A.mark_sent_manually(card.token, IN_HOURS, store=st)["ok"] is True
    twice = A.mark_sent_manually(card.token, IN_HOURS + timedelta(minutes=1), store=st)
    assert twice == {"ok": False, "error": "already sent_manually", "status": "sent_manually"}
    assert len(_rows(world, "sent_manually")) == 1


@pytest.mark.parametrize("booked", [True, False], ids=["owns_the_call", "no_call"])
def test_mark_sent_does_what_a_real_send_does_after_the_instantly_call(world, tmp_env, booked):
    """Twin worlds at the same instant: a send_failed card marked sent, and
    the same card pending and sent through approve(). The lead row (ladder,
    status, booking), the GHL invite call, the reminder ladder and the
    metrics row come out the same."""
    make = _booked if booked else _plain
    st_mark, st_send = world["store"], JsonFileStore(tmp_env / "twin.json")
    card = make(st_mark, status="send_failed")
    st_mark.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    make(st_send, status="pending")
    ghl_mark, ghl_send = Recorder(), Recorder()
    marked = A.mark_sent_manually("c1", IN_HOURS, store=st_mark, ghl=ghl_mark)
    sent = A.approve(card.token, FakeInstantly(), store=st_send, now=IN_HOURS, ghl=ghl_send)
    assert marked["ok"] is True and sent["ok"] is True and sent["status"] == "sent"
    assert marked["cadence"]["armed"] is True and sent["cadence"]["armed"] is True
    assert marked["invite"] == sent["invite"] and marked["first_reply"] is True

    mine, theirs = st_mark.get(card.state_key), st_send.get(card.state_key)
    for field in ("cadence", "status", "last_outbound_at", "offered_slots"):
        assert mine[field] == theirs[field], field
    ours, real = mine["history"][-1], theirs["history"][-1]
    assert (ours["event"], real["event"]) == ("reply_sent_manually", "reply_sent")
    for field in ("reply_at", "sent_at", "first_reply", "approval"):
        assert ours[field] == real[field], field
    by_status = dict((r[1], r[2]) for r in world["rows"] if r[0] == "reply_engine.approval"
                     and r[1] in ("sent_manually", "sent"))
    for field in ("reply_at", "sent_at", "first_reply", "invite", "slots", "cadence_armed", "show_rate_released"):
        assert by_status["sent_manually"][field] == by_status["sent"][field], field
    assert ghl_mark.calls == ghl_send.calls
    assert _registry_rows(st_mark, "c1") == _registry_rows(st_send, "c1")
    if booked:
        assert ghl_mark.calls == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]
        booking = mine["cadence"]["booking"]
        assert booking["confirmed_by"] == "c1" and booking["awaiting_approval"] is False
        assert "owner" not in booking and booking["invite_released"] is True
        assert not show_rate.is_held(st_mark, APPT) and not show_rate.is_held(st_send, APPT)
        assert marked["show_rate"]["released"] is True
    else:
        assert ghl_mark.calls == []


@pytest.mark.parametrize("racer", ["retry", "veto", "opt_out_hold"])
def test_mark_sent_that_loses_the_race_answers_card_changed_and_records_nothing(world, monkeypatch, racer):
    st = world["store"]
    card = _plain(st)
    st.set(A.SEND_CLAIM_PREFIX + "c1", {"attempt": "a1", "at": ct(2026, 9, 28, 9, 5).isoformat()})
    real = A.card_context
    box = {}

    def race_then_read(store, approval_id):
        if not box:
            box["started"] = True                 # once: the racer itself may read the context
            if racer == "retry":
                box["out"] = A.retry(card.token, store=store, now=IN_HOURS)
            elif racer == "veto":
                box["out"] = A.veto(card.token, store=store, now=IN_HOURS, ghl=world["ghl"],
                                    instantly=world["inst"])
            else:
                why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
                box["out"] = A.hold_cards_for_lead_reply(store, [card.token], why, now=IN_HOURS, lead=LEAD)
        return real(store, approval_id)

    monkeypatch.setattr(A, "card_context", race_then_read)
    out = A.mark_sent_manually("c1", IN_HOURS, store=st)
    expected = {"retry": "pending", "veto": "vetoed", "opt_out_hold": "blocked"}[racer]
    assert out["ok"] is False and out["status"] == expected
    assert "changed before it could be marked sent" in out["error"] and "nothing was recorded" in out["error"]
    assert st.get(A.APPROVAL_PREFIX + "c1")["status"] == expected
    assert _rows(world, "sent_manually") == []
    assert not [h for h in st.get(card.state_key)["history"] if h.get("event") == "reply_sent_manually"]
    assert not (st.get(card.state_key).get("cadence") or {}).get("armed_at")
    if racer in ("retry", "opt_out_hold"):
        assert st.get(A.SEND_CLAIM_PREFIX + "c1") is None       # the winner dropped it; Mark sent wrote none


@pytest.mark.parametrize("label,said", OPT_OUTS, ids=[o[0] for o in OPT_OUTS])
def test_mark_sent_after_an_opt_out_records_the_send_but_arms_and_confirms_nothing(world, label, said):
    st = world["store"]
    card = _booked(st, marker=_marker(label),
                   history=[_entry("e-1", "positive_question", T_POS), _entry("e-2", label, T_OUT, P_OUT)])
    out = A.mark_sent_manually("c1", IN_HOURS, store=st, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent_manually"
    assert out["cadence"] == {"armed": False, "reason": "opt_out:%s" % label}
    assert out["lead_reply"]["reason"] == "opt_out" and out["invite"] is None
    assert world["ghl"].calls == [] and show_rate.is_held(st, APPT)          # no invite, no reminders
    row = st.get(card.state_key)
    assert row["cadence"]["booking"]["owner"] == "c1" and row["cadence"]["booking"]["awaiting_approval"] is True
    assert not row["cadence"].get("armed_at") and row["history"][-1]["event"] == "reply_sent_manually"
    assert out["booking_left_held"]["appointment_id"] == APPT and said in out["booking_left_held"]["why"]
    push = _alerts("Call for %s still held after Mark sent" % LEAD)
    assert len(push) == 1
    msg = push[0]["message"]
    assert "Cancel it in GHL without notifying the lead." in msg and A.opt_out_advice(label) in msg
    assert "by hand" not in msg and u"\u2014" not in msg
    assert _rows(world, "sent_manually")[0]["cadence_armed"] is False


@pytest.mark.parametrize("drafted,after", [
    (T_POS, "after the card was drafted"),
    (P_POS, "after the reply this card answers"),
], ids=["newer_reply_after_the_card", "newer_reply_before_the_card"])
def test_mark_sent_after_a_newer_reply_arms_nothing_and_leaves_the_call(world, drafted, after):
    """The push says "after the card was drafted" only when the lead's newer
    reply was sent after it (_hold_facts, as the HELD push words it). A card
    drafted at 9:40 for their 9:00 reply, when the newer one had been sent at
    9:30, says "after the reply this card answers"."""
    st = world["store"]
    card = _booked(st, created=drafted, history=[_entry("e-1", "positive_question", T_POS),
                                                 _entry("e-2", "neutral_question", T_OUT, P_OUT)])
    ctx = st.get(A.APPROVAL_CONTEXT_PREFIX + "c1")
    st.set(A.APPROVAL_CONTEXT_PREFIX + "c1", dict(ctx, reply_at=T_POS.isoformat()))   # it answers the 9:00 reply
    out = A.mark_sent_manually("c1", IN_HOURS, store=st, ghl=world["ghl"])
    assert out["ok"] is True and out["cadence"] == {"armed": False, "reason": "newer_inbound:e-2"}
    assert world["ghl"].calls == [] and show_rate.is_held(st, APPT)
    assert st.get(card.state_key)["cadence"]["booking"]["owner"] == "c1"
    said = "the lead wrote again %s (neutral_question, Mon Sep 28 9:30am CT)" % after
    assert out["booking_left_held"]["why"] == said
    msg = _alerts("still held after Mark sent")[0]["message"]
    assert said in msg and "Read the thread" in msg
    if drafted == P_POS:
        assert "after the card was drafted" not in msg


@pytest.mark.parametrize("case,now,model,choice,reason", [
    ("release", IN_HOURS, "edited", "release", "your recorded choice for it is Release the call"),
    ("no_choice", IN_HOURS, "edited", None, "no Keep choice for it is on record"),
    ("passed", ct(2026, 10, 1, 16, 0), None, None, "its time has passed"),
    ("too_close", ct(2026, 10, 1, 14, 30), None, None, "it starts in less than 60 minutes"),
], ids=["release", "no_choice", "passed", "too_close"])
def test_mark_sent_never_releases_or_cancels_a_call_a_send_would_not_confirm(world, case, now, model, choice,
                                                                             reason):
    st = world["store"]
    card = _booked(st, model=model)
    if choice:
        draft = A.load(card.token, st).draft
        st.set(A.BOOKING_CHOICE_PREFIX + "c1", {"appointment_id": APPT, "slot": SLOT, "choice": choice,
                                                "draft_hash": A.draft_hash(draft), "approval": "c1"})
    out = A.mark_sent_manually("c1", now, store=st, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent_manually" and out["invite"] is None
    assert reason in out["booking_left_held"]["why"]
    assert world["ghl"].calls == [] and world["inst"].sent == [] and show_rate.is_held(st, APPT)
    booking = st.get(card.state_key)["cadence"]["booking"]
    assert booking["owner"] == "c1" and booking["awaiting_approval"] is True and booking["slot"] == SLOT
    msg = _alerts("Call for %s still held after Mark sent" % LEAD)[0]["message"]
    assert reason in msg and "the engine released nothing" in msg and u"\u2014" not in msg


def test_mark_sent_in_live_confirms_the_call_through_the_client_it_is_given(world, tmp_env, monkeypatch):
    _go_live(monkeypatch)
    st = world["store"]
    _booked(st)
    ghl = Recorder()
    out = A.mark_sent_manually("c1", IN_HOURS, store=st, ghl=ghl)
    assert out["invite"] == {"appointment_id": APPT, "released": True}
    assert ghl.calls == [("update_appointment_status", (APPT, "confirmed"), {"to_notify": True})]
    # without a client, live never pretends: the invite is reported unsent and Lorenzo is told
    bare = JsonFileStore(tmp_env / "bare.json")
    _booked(bare)
    out = A.mark_sent_manually("c1", IN_HOURS, store=bare)
    assert out["invite"]["released"] is False and out["invite"]["error"] == "no_ghl_client"
    assert len(_alerts("Calendar invite NOT sent to %s" % LEAD)) == 1


def test_a_card_marked_sent_is_done_everywhere(world):
    """sent_manually is in every sent-like list: never chased, expired,
    vetoed, retried, re-marked, held or sent, and its context row is swept
    like a sent card's (after the grace minutes)."""
    st = world["store"]
    card = _plain(st)
    control = _direct_card(st, "c9", email_id="e-9", offered=[], created=T_POS)   # a pending card beside it
    assert A.mark_sent_manually("c1", IN_HOURS, store=st)["ok"] is True

    chased = A.escalate_pending(st, now=ct(2026, 9, 29, 10, 0))
    assert [c["approval"] for c in chased] == ["c9"]
    assert A.sweep_card_contexts(st, IN_HOURS + timedelta(minutes=9)) == 0
    assert A.card_context(st, "c1") != {}
    expired = A.expire_overdue(st, now=T_POS + timedelta(hours=72))
    assert [e["approval"] for e in expired] == ["c9"] and A.load(control.token, st).status == "expired"
    assert A.card_context(st, "c1") == {}                                    # swept after the grace
    assert A.load(card.token, st).status == "sent_manually"
    assert A.veto(card.token, store=st, now=IN_HOURS)["error"] == "already sent_manually"
    assert "nothing to retry" in A.retry(card.token, store=st, now=IN_HOURS)["error"]
    why = {"reason": "opt_out", "category": "unsubscribe", "at": _utc(T_OUT), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [card.token], why, now=IN_HOURS, lead=LEAD) == []
    assert A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 29, 7, 5)) == []
    assert A.load(card.token, st).status == "sent_manually" and world["inst"].sent == []
    assert "sent_manually" in A.SENT_STATUSES and "sent_manually" in A.CONTEXT_DONE_STATUSES
    assert "sent_manually" not in A.EXPIRABLE_STATUSES + A.LEAD_HOLD_STATUSES + A.RETRYABLE_STATUSES


def test_a_later_send_after_mark_sent_is_not_the_first_reply(world):
    st = world["store"]
    card = _plain(st)
    assert A.mark_sent_manually("c1", IN_HOURS, store=st)["first_reply"] is True
    later = _direct_card(st, "c2", email_id="e-3", offered=["2026-10-02T13:00:00-05:00"],
                         created=ct(2026, 9, 29, 9, 0))
    row = st.get(card.state_key)
    row["approvals"] = row["approvals"] + [later.token]
    row["processed_email_ids"] = row["processed_email_ids"] + ["e-3"]
    row["history"] = row["history"] + [_entry("e-3", "positive_question", ct(2026, 9, 29, 9, 0))]
    st.set(card.state_key, row)
    out = A.approve(later.token, world["inst"], store=st, now=ct(2026, 9, 29, 10, 0), ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent"
    assert _rows(world, "sent")[-1]["first_reply"] is False
    assert st.get(card.state_key)["history"][-1]["first_reply"] is False


# ------------------------------------ Mark sent: the lead's row does not land
class _FailingLeadReads(object):
    """Wraps a store: reads of the lead row raise from the ``after``-th on."""

    def __init__(self, store, key, after):
        self._store, self._key, self.after, self.reads = store, key, after, 0

    def get(self, key, default=None):
        if key == self._key:
            self.reads += 1
            if self.reads >= self.after:
                raise IOError("store read timed out")
        return self._store.get(key, default)

    def __getattr__(self, name):
        return getattr(self._store, name)


def _broken_write(*a, **k):
    raise IOError("store write timed out")


def _not_updated(world):
    """The failure row (its own status, for the deploy watch) and the push."""
    return _rows(world, "mark_sent_record_not_updated"), _alerts("Mark sent for %s: the lead's record was NOT updated"
                                                                  % LEAD)


def test_mark_sent_whose_lead_row_write_fails_has_its_own_failure_row(world, monkeypatch):
    st = world["store"]
    card = _plain(st)
    before = st.get(card.state_key)
    monkeypatch.setattr(A, "save_lead_state", _broken_write)
    out = A.mark_sent_manually("c1", IN_HOURS, store=st)
    assert out["ok"] is True and out["status"] == "sent_manually" and A.load(card.token, st).status == "sent_manually"
    assert out["cadence"] == {"armed": False, "error": "the lead row could not be written: store write timed out"}
    failed, pushed = _not_updated(world)
    assert failed == [{"lead": LEAD, "approval": "c1",
                       "error": "the lead's row could not be written (store write timed out)"}]
    assert len(pushed) == 1 and pushed[0]["priority"] == "high"
    assert "could not be written" in pushed[0]["message"] and "Check the lead by hand." in pushed[0]["message"]
    assert "If this card holds the lead's call" not in pushed[0]["message"]
    assert u"\u2014" not in pushed[0]["message"]
    logged = _rows(world, "sent_manually")                   # the metrics row is written as always
    assert len(logged) == 1 and logged[0]["cadence_not_armed"].startswith("the lead row could not be written")
    assert st.get(card.state_key) == before


def test_a_failed_lead_row_write_after_the_invite_went_out_says_the_invite_did(world, monkeypatch):
    st = world["store"]
    _booked(st)
    monkeypatch.setattr(A, "save_lead_state", _broken_write)
    out = A.mark_sent_manually("c1", IN_HOURS, store=st, ghl=world["ghl"])
    assert out["invite"] == {"appointment_id": APPT, "released": True} and world["ghl"].calls
    failed, pushed = _not_updated(world)
    assert len(failed) == 1 and len(pushed) == 1
    assert "The call's calendar invite WAS released in GHL" in pushed[0]["message"]


def test_mark_sent_on_an_unparseable_lead_row_writes_nothing_and_says_so(world):
    """Round 4 wrote nothing and said nothing here (cadence_not_armed null)."""
    st = world["store"]
    card = _booked(st)                        # it holds a Keep call: nothing is confirmed from a row it cannot read
    raw = st.get(card.state_key)
    raw["history"] = "not a list"
    st.set(card.state_key, raw)
    out = A.mark_sent_manually("c1", IN_HOURS, store=st, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent_manually" and out["invite"] is None
    assert out["cadence"]["armed"] is False and out["cadence"]["error"].startswith("the lead's row could not be parsed")
    assert world["ghl"].calls == [] and show_rate.is_held(st, APPT) and st.get(card.state_key) == raw
    failed, pushed = _not_updated(world)
    assert len(failed) == 1 and failed[0]["approval"] == "c1" and failed[0]["lead"] == LEAD
    assert failed[0]["error"].startswith("the lead's row could not be parsed") and len(pushed) == 1
    assert "If this card holds the lead's call, it was not confirmed" in pushed[0]["message"]
    assert _rows(world, "sent_manually")[0]["cadence_not_armed"].startswith("the lead's row could not be parsed")


def test_mark_sent_whose_lead_row_cannot_be_read_again_confirms_nothing_and_says_so(world):
    """Readable before the card moved, not after: the earlier read is not
    used to confirm the call or write the row."""
    st = world["store"]
    card = _booked(st)
    flaky = _FailingLeadReads(st, card.state_key, after=2)
    out = A.mark_sent_manually("c1", IN_HOURS, store=flaky, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent_manually" and flaky.reads == 2
    assert out["invite"] is None and world["ghl"].calls == [] and show_rate.is_held(st, APPT)
    failed, pushed = _not_updated(world)
    assert [f["error"] for f in failed] == ["the lead's row could not be read (store read timed out)"]
    assert len(pushed) == 1 and "If this card holds the lead's call, it was not confirmed" in pushed[0]["message"]
    row = st.get(card.state_key)
    assert row["cadence"]["booking"]["owner"] == "c1"
    assert not [h for h in row["history"] if h.get("event") == "reply_sent_manually"]


def test_mark_sent_on_a_card_whose_lead_row_is_gone_says_so(world):
    st = world["store"]
    _direct_card(st, "c1", status="send_failed", email_id="e-1", created=T_POS)     # no lead row at all
    out = A.mark_sent_manually("c1", IN_HOURS, store=st)
    assert out["ok"] is True and out["cadence"] == {"armed": False, "error": "the lead's row is missing"}
    failed, pushed = _not_updated(world)
    assert [f["error"] for f in failed] == ["the lead's row is missing"] and len(pushed) == 1


# ============== recipient-held cards: no Mark sent (orchestrator's decision)
def _recipient_held_card(world, monkeypatch):
    """Live (in-process): the send re-reads the thread and its last inbound is
    somebody else, so the card is held at send_failed and nothing is sent."""
    st = world["store"]
    card = _plain(st, status="pending")
    _go_live(monkeypatch)
    out = A.approve(card.token, ThreadReader(sender="someone.else@example.com"), store=st, now=IN_HOURS,
                    ghl=world["ghl"])
    assert out["status"] == "send_failed" and out["escalated"] is True and out["error"] == "recipient_mismatch"
    return card


def test_a_card_held_for_its_recipient_gets_no_mark_sent_link_and_is_refused(world, monkeypatch):
    st = world["store"]
    card = _recipient_held_card(world, monkeypatch)
    stored = A.load(card.token, st)
    held = stored.notify_result[A.RECIPIENT_HELD_KEY]
    assert held["reason"] == "recipient_mismatch" and held["to"] == LEAD
    assert A.mark_sent_url(stored) is None                              # what the stuck push builds from
    assert A.mark_sent_url(st.get(A.APPROVAL_PREFIX + "c1"), store=st) is None
    before_card, before_row = st.get(A.APPROVAL_PREFIX + "c1"), st.get(card.state_key)
    out = A.mark_sent_manually("c1", IN_HOURS + timedelta(minutes=5), store=st, ghl=world["ghl"])
    assert out == {"ok": False, "status": "send_failed", "recipient_held": held, "error": A.RECIPIENT_HELD_REFUSAL}
    assert out["error"] == ("This card was held because the recipient could not be confirmed; Veto it, or check "
                            "the thread in Instantly. Mark sent is not available.")
    # nothing moved: the card, the lead row (no history, no ladder), no claim, no metrics row, no GHL call
    assert st.get(A.APPROVAL_PREFIX + "c1") == before_card and st.get(card.state_key) == before_row
    assert st.get(A.SEND_CLAIM_PREFIX + "c1") is None and _rows(world, "sent_manually") == []
    assert not (before_row.get("cadence") or {}).get("armed_at") and world["ghl"].calls == []


def test_a_card_escalated_before_the_card_side_record_is_refused_through_the_hold_row(world):
    """A card escalated before the record on the card existed has only the
    hold's own row: the store tells, and Mark sent refuses."""
    st = world["store"]
    card = _plain(st)
    st.set(A.RECIPIENT_HOLD_PREFIX + "c1", {"attempts": 3, "reason": "recipient_unconfirmed", "to": LEAD})
    assert A.mark_sent_url(card, store=st) is None
    before_card = st.get(A.APPROVAL_PREFIX + "c1")
    out = A.mark_sent_manually("c1", IN_HOURS, store=st)
    assert out["ok"] is False and out["error"] == A.RECIPIENT_HELD_REFUSAL and out["status"] == "send_failed"
    assert st.get(A.APPROVAL_PREFIX + "c1") == before_card and _rows(world, "sent_manually") == []


def test_retry_clears_the_recipient_hold_so_a_later_failed_send_can_be_marked_sent(world, monkeypatch):
    st = world["store"]
    card = _recipient_held_card(world, monkeypatch)
    retried = A.retry(card.token, store=st, now=IN_HOURS + timedelta(minutes=5))
    stored = A.load(retried["token"], st)
    assert stored.status == "pending" and A.RECIPIENT_HELD_KEY not in (stored.notify_result or {})
    assert st.get(A.RECIPIENT_HOLD_PREFIX + "c1") is None

    class AcceptedThenRaised(ThreadReader):
        def reply_to_email(self, reply_to_uuid, eaccount, subject, body, to=None):
            raise RuntimeError("Instantly answered 502 after accepting the reply")

    failed = A.approve(retried["token"], AcceptedThenRaised(sender=LEAD), store=st,
                       now=IN_HOURS + timedelta(minutes=10), ghl=world["ghl"])
    assert failed["status"] == "send_failed"
    card_now = A.load(retried["token"], st)
    assert A.mark_sent_url(card_now, store=st) == "https://engine.test/mark-sent/%s" % retried["token"]
    assert A.mark_sent_manually("c1", IN_HOURS + timedelta(minutes=15), store=st)["ok"] is True


# ============================================================= mark_sent_url
def test_mark_sent_url_with_and_without_a_usable_base_url(world, monkeypatch):
    st = world["store"]
    card = _plain(st)
    url = "https://engine.test/mark-sent/%s" % card.token
    assert A.mark_sent_url(card) == url
    assert A.mark_sent_url(st.get(A.APPROVAL_PREFIX + "c1")) == url
    assert A.mark_sent_url(card.token) == url
    monkeypatch.setenv("BASE_URL", "https://engine.test/")
    assert A.mark_sent_url(card) == url
    for dead in ("", "http://localhost:8000", "http://127.0.0.1:8000", "ftp://engine.test"):
        monkeypatch.setenv("BASE_URL", dead)
        assert A.mark_sent_url(card) is None, dead
    monkeypatch.delenv("BASE_URL")
    assert A.mark_sent_url(card) is None
    _go_live(monkeypatch)
    assert A.mark_sent_url(card) is None                    # no raise in live, unlike base_url()
    monkeypatch.setenv("REPLY_ENGINE_BASE_URL", "https://alias.test")
    assert A.mark_sent_url(card) == "https://alias.test/mark-sent/%s" % card.token
    for junk in (None, "", "no-signature", {}, {"token": None}):
        assert A.mark_sent_url(junk) is None
