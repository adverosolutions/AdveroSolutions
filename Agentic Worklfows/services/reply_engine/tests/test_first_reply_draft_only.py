"""Lorenzo's rule (2026-09-23): first replies are never auto-sent.

The engine drafts the first reply (two held times, no booking link) and
Lorenzo sends it himself from the thread. So a first_reply.* draft is always
an approval card, whatever the approvals file, the kill switch or the template
gate say (approval.FIRST_REPLY_LOCK_REASON, checked before the gate at every
point a card can go out with no tap). A counter-proposal template still
auto-sends as before. Shadow only, zero HTTP, no LLM; the gate environment is
the tmp one test_ct3_card_autosend's world fixture builds.
"""
from datetime import timedelta

import pytest

from shared import notify, settings

from services.reply_engine import approval as A
from services.reply_engine import draft as D
from services.reply_engine import template_gate as gate
from services.reply_engine.models import LeadState
from services.reply_engine.models import Draft
from services.reply_engine.tests.test_ct3_card_autosend import (  # noqa: F401
    CAMPAIGN, COMPANY, FIRST, FLUSH, LEAD, LINK, NIGHT, NOW, OFFER, TID, _booking_reply, _card, _cls, _event,
    _fyi_entries, _pushes, _rows, _stored, booking_world, world)

LOCK_LINE = "Not auto-sent: first replies are drafts you send yourself from the thread."
# The four first replies the emails doc lists per offer, and a classification
# that draws each one.
VARIANTS = {
    "default": {},
    "pricing": {"question_type": "pricing"},
    "other": {"label": "neutral_question", "question_type": "other"},
    "referral": {"label": "positive_referral"},
}


def _classification(variant):
    kw = dict(VARIANTS[variant])
    cls = _cls(label=kw.pop("label", "positive_interested"))
    if kw.get("question_type"):
        cls.extracted.question_type = kw["question_type"]
    if variant == "referral":
        cls.extracted.referral_name = "Sam Rivera"
    return cls


def _first_card(world, variant="default", now=NOW, email_id="f-1", verdict="real", approve=True):
    """A first reply as the pipeline raises it: the template draft, stamped
    with its first_reply id, the gate's verdict and the card. ``verdict``
    "real" is the gate's own; "allowed" is an allowed verdict whatever the
    gate said (the lock must not read it); None raises the card without one."""
    tid = "first_reply.%s.%s.full" % (OFFER, variant)
    st = world["store"]
    if approve:
        world["tpl"].approve_ids(tid)
    cls = _classification(variant)
    ev = _event(email_id, now)
    state = LeadState.from_store(st.get("lead:%s:%s" % (CAMPAIGN, LEAD)), ev)
    state.classification = cls
    d = D.build_draft(ev, cls, now=now, booking_link=LINK, use_llm=False, already_offered=[], busy_blocks=[])
    gate.stamp(d, tid)
    real = gate.draft_verdict(d, kind="first_reply", campaign_key=OFFER, allow_terms=D.lead_terms(ev, state),
                              classification=cls, bindings=D.first_reply_bindings(ev, cls, d, state=state))
    v = {"real": real, "allowed": gate.Verdict(True, "ok", tid, [tid], {tid: "approved"}), None: None}[verdict]
    card = A.create_approval(state, d, ev, store=st, now=now, campaign_key=OFFER, auto=v)
    state.processed_email_ids.append(email_id)
    st.set(state.key, state.to_store())
    return card, v, real, tid


def _assert_is_an_ordinary_card(world, card, pushes_before=0):
    stored = _stored(world, card)
    assert stored.status == "pending" and stored.approved_by is None
    assert "deferred" not in (stored.notify_result or {})
    pushes = _pushes()
    assert len(pushes) == pushes_before + 1
    push = pushes[-1]
    assert push["message"].startswith(LOCK_LINE + "\n")
    # the same card an unapproved draft gets: Approve, Veto and Edit
    for action in ("Approve", "Veto", "Edit"):
        assert action in push["actions"], action
    assert world["inst"].sent == [] and _fyi_entries(world) == []
    return stored


# ================================================================ the lock
@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_an_approved_first_reply_is_never_auto_sent_and_is_a_card(world, variant):
    card, v, real, tid = _first_card(world, variant, verdict="allowed")
    assert card.draft.template_id == tid and v.allowed is True
    if variant in ("default", "pricing"):
        # a real, gate-passing first reply: approved, kill switch off
        assert (real.allowed, real.reason) == (True, "ok"), real.detail
    stored = _assert_is_an_ordinary_card(world, card)
    assert stored.auto_send["allowed"] is False and stored.auto_send["reason"] == A.FIRST_REPLY_LOCK_REASON
    assert stored.auto_send["gate_reason"] == "ok"
    assert [(r["auto"], r["auto_reason"]) for r in _rows(world, "created")] == [(False, "first_reply_draft_only")]
    # the pipeline's auto-send call refuses it too, and pushes nothing more
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is False and out["reason"] == A.REASON_TEXT["first_reply_draft_only"] and out["pushed"] is None
    assert world["inst"].sent == [] and len(_pushes()) == 1
    assert [r["reason"] for r in _rows(world, "template_auto_send_refused")] == ["first_reply_draft_only"]
    # Lorenzo's own Approve still sends it
    sent = A.approve(stored.token, world["inst"], store=world["store"], now=NOW)
    assert sent["ok"] is True and sent["status"] == "sent" and _stored(world, card).approved_by == "lorenzo"
    assert len(world["inst"].sent) == 1 and _fyi_entries(world) == []


def test_the_real_gate_verdict_on_an_approved_first_reply_is_locked_too(world):
    card, v, real, tid = _first_card(world, "default", verdict="real")
    assert (v.allowed, v.reason) == (True, "ok"), v.detail
    stored = _assert_is_an_ordinary_card(world, card)
    assert stored.auto_send["reason"] == A.FIRST_REPLY_LOCK_REASON


@pytest.mark.parametrize("verdict", ["real", None])
def test_an_unapproved_or_verdictless_first_reply_card_says_first_replies_are_drafts(world, verdict):
    card, v, real, tid = _first_card(world, "default", verdict=verdict, approve=False)
    stored = _assert_is_an_ordinary_card(world, card)
    if verdict is None:
        assert stored.auto_send is None
    else:
        assert (stored.auto_send["reason"], stored.auto_send["gate_reason"]) == ("first_reply_draft_only", "unapproved")
    # never the "approve it in the emails doc" advice, which cannot work here
    assert A.REASON_TEXT["unapproved"] not in _pushes()[0]["message"]


def test_the_kill_switch_state_does_not_matter(world):
    world["tpl"].kill_switch(False)
    card, v, real, tid = _first_card(world, "default", verdict="allowed")
    _assert_is_an_ordinary_card(world, card)


def test_a_pending_cancel_is_still_said_after_the_lock_line(world):
    card, v, real, tid = _first_card(world, "default", verdict="real")
    cancel = gate.Verdict(False, "cancel_pending", tid, [tid], {})
    assert A._auto_decision(cancel, card.draft) == (
        False, LOCK_LINE + " Also, " + A.REASON_TEXT["cancel_pending"])
    # any other refusal is replaced by the lock's line
    assert A._auto_decision(gate.Verdict(False, "kill_switch", tid, [tid], {}), card.draft) == (False, LOCK_LINE)


@pytest.mark.parametrize("tid", ["first_reply", "first_reply.x.default.full", " First_Reply.x.pricing.full"])
def test_the_lock_reads_the_template_id(tid):
    assert A.first_reply_locked(tid) is True


@pytest.mark.parametrize("tid", [None, "", TID, "booking.confirmation.zoom_link", "cadence.d3", "first_replyx"])
def test_the_lock_leaves_every_other_id(tid):
    assert A.first_reply_locked(tid) is False


# ============================================ cards raised before the lock
def _as_deferred(world, card, **fields):
    """The card as a build without the lock stored it: waiting on its
    deferred push (an auto-send the pipeline was about to run)."""
    st = world["store"]
    key = A.APPROVAL_PREFIX + A._approval_id(card)
    raw = st.get(key)
    raw["notify_result"] = {"deferred": A.DEFERRED_AUTO_SEND, "deferred_at": NOW.isoformat()}
    raw["auto_send"] = {"allowed": True, "reason": "ok", "template_id": card.draft.template_id}
    raw.update(fields)
    st.set(key, raw)
    notify.sent_in_test.clear()
    return A.load(card.token, st)


def test_a_deferred_first_reply_is_pushed_once_and_never_sent(world):
    card, v, real, tid = _first_card(world, "default", verdict="allowed")
    card = _as_deferred(world, card)
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is False and out["reason"] == A.REASON_TEXT["first_reply_draft_only"] and out["pushed"]
    assert world["inst"].sent == [] and _stored(world, card).status == "pending"
    pushes = _pushes()
    assert len(pushes) == 1 and pushes[0]["message"].startswith(LOCK_LINE + "\n")
    # a second call and the orphan sweep push nothing more
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert A.push_orphaned_deferred(world["store"], now=NOW + timedelta(minutes=30)) == []
    assert len(_pushes()) == 1 and world["inst"].sent == []


def test_a_queued_template_first_reply_is_refused_at_the_flush_before_the_gate_runs(world, monkeypatch):
    """A first reply queued overnight as approved_by "template" (before the
    lock): the 07:00 flush turns it back into a pending card and pushes it,
    without asking the gate."""
    card, v, real, tid = _first_card(world, "default", now=NIGHT, verdict="allowed")
    card = _as_deferred(world, card, status="approved_queued", approved_by="template",
                        send_after=(NIGHT + timedelta(hours=11)).isoformat(), decided_at=NIGHT.isoformat())
    asked = []
    monkeypatch.setattr(gate, "draft_verdict", lambda *a, **kw: asked.append(1) or v)
    flushed = A.flush_queued(world["inst"], store=world["store"], now=FLUSH)
    assert [(f["status"], f["reason"]) for f in flushed] == [("pending", "first_reply_draft_only")]
    assert asked == [] and world["inst"].sent == []
    stored = _stored(world, card)
    assert stored.status == "pending" and stored.approved_by is None and stored.auto_send["reason"] == "first_reply_draft_only"
    pushes = _pushes()
    assert len(pushes) == 1 and pushes[0]["message"].startswith(LOCK_LINE + "\n")
    assert [r["reason"] for r in _rows(world, "template_auto_send_refused")] == ["first_reply_draft_only"]
    # the send-time re-check says the same for any "template" card
    assert A._template_verdict(stored, world["store"].get(stored.state_key)).reason == "first_reply_draft_only"


# ================================================ the old timer (unwired)
class _LiveView(object):
    """approval.py's view of settings with is_live() True, so auto_send_due
    runs its loop. Nothing else changes: no live flag is set, and approve is
    replaced by a spy, so nothing can send."""

    def is_live(self):
        return True

    def __getattr__(self, name):
        return getattr(settings, name)


def test_the_old_timer_never_sends_a_first_reply(world, monkeypatch):
    first, _, _, _ = _first_card(world, "default", verdict=None)
    st = world["store"]
    key = A.APPROVAL_PREFIX + A._approval_id(first)
    raw = st.get(key)
    raw["notify_result"] = dict(raw.get("notify_result") or {}, sent=True, actionable=True)
    st.set(key, raw)
    monkeypatch.setenv("AUTO_SEND_AFTER_MINUTES", "1")
    monkeypatch.setattr(A, "settings", _LiveView())
    calls = []
    monkeypatch.setattr(A, "approve", lambda token, *a, **kw: calls.append(token) or {"ok": True, "status": "sent"})
    assert A.auto_send_due(world["inst"], store=st, now=NOW + timedelta(minutes=5)) == []
    assert calls == []
    assert [r["reason"] for r in _rows(world, "auto_send_refused_first_reply")] == ["first_reply_draft_only"]
    # a card whose template is not a first reply, to a lead who already got
    # one from us: the timer is not what the lock stops
    row = st.get(first.state_key)
    row["history"] = list(row.get("history") or []) + [{"event": "reply_sent", "at": NOW.isoformat()}]
    st.set(first.state_key, row)
    raw = st.get(key)
    raw["draft"] = dict(raw["draft"], template_id=TID)
    st.set(key, raw)
    out = A.auto_send_due(world["inst"], store=st, now=NOW + timedelta(minutes=5))
    assert calls == [first.token] and [o["status"] for o in out] == ["sent"]


# ============================================ other templates still auto-send
def test_a_counter_proposal_template_still_auto_sends(world):
    card, v = _card(world)
    assert (v.allowed, v.template_id) == (True, TID)
    assert _stored(world, card).notify_result["deferred"] == A.DEFERRED_AUTO_SEND
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is True and out["status"] == "sent" and _stored(world, card).approved_by == "template"
    assert len(world["inst"].sent) == 1 and _pushes() == []
    assert [e["template_id"] for e in _fyi_entries(world)] == [TID]
    assert [r["auto_reason"] for r in _rows(world, "created")] == [None]


def test_the_reason_sentences(world):
    assert A.REASON_TEXT["first_reply_draft_only"] == "first replies are drafts you send yourself from the thread."
    assert A.REASON_TEXT["unapproved"] == 'its template is not approved yet; approve it in the emails doc, then tell Claude "done".'
    assert A.REASON_TEXT["changed_since_approval"] == ('its template changed since you approved it; review it and '
                                                       'approve it again in the emails doc, then tell Claude "done".')
    for text in A.REASON_TEXT.values():
        assert "approve_templates" not in text and "—" not in text and "!" not in text


# ============================== any reply to a lead we have not answered yet
# Lorenzo, 2026-09-23: a reply to a lead nothing of ours has reached yet is a
# draft he sends himself, like a first reply; only a booking confirmation (the
# lead's own time booked the call) still auto-sends.
def test_a_first_contact_counter_proposal_is_a_card(world):
    card, v = _card(world, answered=False)
    assert (v.allowed, v.template_id) == (True, TID)
    stored = _assert_is_an_ordinary_card(world, card)
    assert (stored.auto_send["reason"], stored.auto_send["gate_reason"]) == ("first_reply_draft_only", "ok")
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is False and out["reason"] == A.REASON_TEXT["first_reply_draft_only"]
    assert world["inst"].sent == [] and len(_pushes()) == 1


def test_a_first_contact_slot_already_taken_is_a_card(world):
    tid = "booking.slot_already_taken"
    ev = _event("t-1")
    state = LeadState.from_store(None, ev)
    d = Draft(subject="Re: Quick question", body_text="Hey %s,\n\nThat time just got taken.\n\nLorenzo" % FIRST,
              model="template", label="positive_interested", template_id=tid)
    allowed = gate.Verdict(True, "ok", tid, [tid], {tid: "approved"})
    assert A._auto_decision(allowed, d, state) == (False, LOCK_LINE)
    card = A.create_approval(state, d, ev, store=world["store"], now=NOW, campaign_key=OFFER, auto=allowed)
    stored = _assert_is_an_ordinary_card(world, card)
    assert stored.auto_send["reason"] == "first_reply_draft_only"
    # once a reply of ours reached the lead, the lock no longer applies
    state.history.append({"event": "reply_sent", "at": NOW.isoformat()})
    assert A._auto_decision(allowed, d, state) == (True, None)


def test_a_first_contact_booking_confirmation_still_auto_sends(booking_world):
    w = booking_world
    for tid in ("booking.confirmation.no_zoom_link", "booking.confirmation.zoom_link"):
        w["tpl"].approve_ids(tid)
    assert w["store"].get("lead:%s:%s" % (CAMPAIGN, LEAD)) is None      # nothing of ours reached the lead
    res = _booking_reply(w)
    assert res.get("booking") and (res.get("auto_send") or {}).get("allowed") is True, res.get("auto_send")
    card = A.load(res["approval_token"], w["store"])
    assert card.draft.template_id.startswith("booking.confirmation.")
    assert card.status == "sent" and card.approved_by == "template" and len(w["inst"].sent) == 1


@pytest.mark.parametrize("tid,locked", [
    (TID, True), ("booking.slot_already_taken", True), ("booking.already_booked.invite_on_calendar", True),
    ("booking.confirmation.zoom_link", False), ("booking.confirmation.no_zoom_link", False)])
def test_an_unreadable_lead_row_locks_everything_but_a_confirmation(tid, locked):
    assert A.draft_only(tid, None) is locked
    assert A.draft_only(tid, {"not": "a lead row"}) is locked
    answered = {"lead_email": LEAD, "campaign_id": CAMPAIGN, "history": [{"event": "reply_sent"}]}
    assert A.draft_only(tid, answered) is False
    assert A.draft_only("first_reply.x.default.full", answered) is True


def test_an_unreadable_lead_row_at_send_time_locks_a_counter(world, monkeypatch):
    card, v = _card(world)                                   # answered when raised: deferred
    assert _stored(world, card).notify_result["deferred"] == A.DEFERRED_AUTO_SEND
    st = world["store"]
    real = st.get

    def broken(key, *a, **kw):
        if key == card.state_key:
            raise OSError("lead row unreadable")
        return real(key, *a, **kw)
    monkeypatch.setattr(st, "get", broken)
    out = A.auto_send_approved(card, world["inst"], store=st, now=NOW, verdict=v)
    assert out["ok"] is False and out["reason"] == A.REASON_TEXT["first_reply_draft_only"]
    assert world["inst"].sent == [] and len(_pushes()) == 1
    # the send-time re-check without a row: a counter is locked, a confirmation goes to the gate
    stored = _stored(world, card)
    assert A._template_verdict(stored, None).reason == "first_reply_draft_only"
    confirmation = stored.model_copy(deep=True)
    confirmation.draft.template_id = "booking.confirmation.no_zoom_link"
    assert A._template_verdict(confirmation, None).reason != "first_reply_draft_only"
