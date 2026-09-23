"""CT3 phase 2, reviewer-max P3 / P3b: a template auto-send that ends at
send_failed is pushed to Lorenzo as a card, exactly once.

Before the fix a card whose template send failed (an Instantly error, a
recipient hold that escalated, an exception in the 07:00 flush) was never
pushed: it kept its deferred marker, nothing ever put Approve / Veto / Edit
in front of Lorenzo, and the stuck-card reminder told him to "press Retry"
or "Veto it" with no link to do either.

Now the card is pushed once with "Not auto-sent: <reason>" (REASON_TEXT) and
the buttons that take a send_failed card (Retry, Veto, Mark sent where each
is allowed; Edit, which works once Retry has put the card back to pending,
in the email leg). The public ntfy topic gets no name, address, company,
subject, body or link. A send, a queue and a recipient hold that has not
escalated push nothing. The stuck push and the recipient-hold alert carry the
links their words ask for. Plus the FYI's shadow wording.

Shadow only; fake clients; zero HTTP; no LLM. Every lead is an example.com
address.
"""
from datetime import timedelta

import pytest

from shared import notify, settings as real_settings

from services.reply_engine import approval as A
from services.reply_engine import poller as P
from services.reply_engine import template_gate as gate
from services.reply_engine.tests.test_ct3_card_autosend import (  # noqa: F401
    COMPANY, FIRST, FLUSH, LEAD, NIGHT, NOW, TID, _card, _fyi_entries, _pushes, _rows, _stored, ct, world)

BASE = "https://engine.test"


class _LiveView(object):
    """approval.py's view of shared.settings with is_live() True, so the
    recipient check runs; the real settings (guard_write, notify) stay in
    shadow, so nothing leaves the process."""

    def __getattr__(self, name):
        return getattr(real_settings, name)

    @staticmethod
    def is_live():
        return True


def _boom(*a, **k):
    raise RuntimeError("instantly 502")


def _link(kind, card):
    return "%s/%s/%s" % (BASE, kind, card.token)


def _public_text(push):
    return push["title"] + "\n" + push["message"]


def _assert_public_is_clean(push, card):
    text = _public_text(push)
    body_line = [ln for ln in card.draft.body_text.splitlines() if len(ln) > 20][0]
    for secret in (LEAD, FIRST, COMPANY, card.draft.subject, body_line, "http", "example.com", "engine.test"):
        assert secret not in text, secret


def _only_card_push():
    pushes = _pushes()
    assert len(pushes) == 1, [p["title"] for p in notify.sent_in_test]
    return pushes[0]


# ================================================= pipeline: send error (P3)
def test_a_template_send_that_fails_is_pushed_once_with_retry_veto_and_mark_sent(world, monkeypatch):
    card, v = _card(world)
    monkeypatch.setattr(world["inst"], "reply_to_email", _boom)
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["ok"] is False and out["status"] == "send_failed" and out["pushed"]
    stored = _stored(world, card)
    assert stored.status == "send_failed"
    assert "deferred" not in stored.notify_result
    assert stored.notify_result[A.DEFERRED_PUSHED_KEY]["note"] == "Not auto-sent: " + A.REASON_TEXT["send_failed"]
    push = _only_card_push()
    assert push["message"].startswith("Not auto-sent: %s\n" % A.REASON_TEXT["send_failed"])
    # the buttons (shared.notify strips them on the public topic and lists
    # them in the email leg): Retry, Veto, Mark sent; never Approve or a click
    assert push["actions"] == "view, Retry, %s; view, Veto, %s; view, Mark sent, %s" % (
        _link("retry", stored), _link("veto", stored), _link("mark-sent", stored))
    assert "/approve/" not in push["actions"] and push["click"] is None
    # the public topic: the reason and what to do, nothing about the lead
    _assert_public_is_clean(push, stored)
    assert "press Mark sent" in push["message"] and "press Retry" in push["message"]
    # the email leg: the whole card, and Edit (it works once Retry has run)
    em = push["email_message"]
    assert em.startswith("Not auto-sent: %s\n" % A.REASON_TEXT["send_failed"])
    assert LEAD in em and stored.draft.body_text in em
    assert "Edit (after Retry): %s" % _link("edit", stored) in em
    assert world["inst"].sent == [] and _fyi_entries(world) == []
    # exactly once: the same outcome again pushes nothing
    again = A._after_template_send(world["store"], stored, {"ok": False, "status": "send_failed"}, NOW)
    assert again["pushed"] is None and len(_pushes()) == 1
    # every link works: Retry takes it back to pending, then Edit takes it
    back = A.retry(stored.token, store=world["store"], now=NOW + timedelta(minutes=1))
    assert back["ok"] is True and back["token"] == stored.token
    body = stored.draft.body_text.replace("Hey %s," % FIRST, "Hi %s," % FIRST)
    assert A.edit(stored.token, body, store=world["store"], now=NOW + timedelta(minutes=2))["ok"] is True


def test_on_a_protected_topic_the_failed_card_carries_the_lead_and_the_links(world, monkeypatch):
    monkeypatch.setenv("NTFY_TOKEN", "unit-token")
    card, v = _card(world)
    monkeypatch.setattr(world["inst"], "reply_to_email", _boom)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    push = _only_card_push()
    stored = _stored(world, card)
    assert FIRST in push["title"] and COMPANY in push["title"] and "not sent" in push["title"]
    assert LEAD in push["message"] and "email_message" not in push
    assert "Edit (after Retry): %s" % _link("edit", stored) in push["message"]


def test_a_failed_push_of_a_card_mark_sent_took_meanwhile_is_not_sent(world, monkeypatch):
    """The push is taken only for a card still at send_failed as stored."""
    card, v = _card(world)
    st = world["store"]
    raw = st.get(A.APPROVAL_PREFIX + A._approval_id(card))
    st.set(A.APPROVAL_PREFIX + A._approval_id(card), dict(raw, status="sent_manually"))
    out = A._after_template_send(st, _stored(world, card), {"ok": False, "status": "send_failed"}, NOW)
    assert out["pushed"] is None and _pushes() == []
    assert st.get(A.APPROVAL_PREFIX + A._approval_id(card))["notify_result"]["deferred"]


# ======================================= pipeline: recipient mismatch (P3b)
def test_a_recipient_mismatch_is_pushed_once_with_retry_and_veto_and_no_mark_sent(world, monkeypatch):
    card, v = _card(world)
    monkeypatch.setattr(A, "settings", _LiveView())
    monkeypatch.setattr(A, "_recipient_verdict", lambda approval, recipient, instantly: False)
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["held"] is True and out["escalated"] is True and out["status"] == "send_failed"
    assert world["inst"].sent == []
    stored = _stored(world, card)
    assert "deferred" not in stored.notify_result and stored.notify_result[A.RECIPIENT_HELD_KEY]
    push = _only_card_push()
    assert push["message"].startswith("Not auto-sent: %s\n" % A.REASON_TEXT["recipient_mismatch"])
    assert push["actions"] == "view, Retry, %s; view, Veto, %s" % (_link("retry", stored), _link("veto", stored))
    assert "Mark sent is not available" in push["message"]
    _assert_public_is_clean(push, stored)
    # the urgent HELD alert says Retry or Veto, and carries both links
    alert = [n for n in notify.sent_in_test if "HELD: recipient not confirmed" in n["title"]]
    assert len(alert) == 1
    assert alert[0]["actions"] == push["actions"] and "press Retry" in alert[0]["message"]
    assert "Veto it" in alert[0]["message"] and "use Retry on the card" not in alert[0]["message"]
    # Retry takes it back to pending, its hold cleared
    assert A.retry(stored.token, store=world["store"], now=NOW + timedelta(minutes=1))["ok"] is True
    assert A.RECIPIENT_HELD_KEY not in _stored(world, card).notify_result


def test_a_recipient_hold_that_has_not_escalated_pushes_nothing(world, monkeypatch):
    """recipient_unconfirmed on the first attempt: retried on its own
    (approved_queued, RECIPIENT_RETRY_MINUTES later), not a card yet."""
    card, v = _card(world)
    monkeypatch.setattr(A, "settings", _LiveView())
    monkeypatch.setattr(A, "_recipient_verdict", lambda approval, recipient, instantly: None)
    out = A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    assert out["held"] is True and out["escalated"] is False and out["status"] == "approved_queued"
    assert out.get("pushed") is None and _pushes() == []
    assert _stored(world, card).notify_result["deferred"] and world["inst"].sent == []


def test_a_recipient_hold_pushes_only_when_it_escalates_in_the_flush(world, monkeypatch):
    """A card queued overnight: the 07:05 flush's re-read fails (attempt 1),
    and so do the retries; attempts 1 and 2 stay queued and push nothing,
    attempt 3 escalates to send_failed and pushes the card once."""
    card, v = _card(world, now=NIGHT)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NIGHT, verdict=v)
    assert _stored(world, card).status == "approved_queued"
    monkeypatch.setattr(A, "settings", _LiveView())
    monkeypatch.setattr(A, "_recipient_verdict", lambda approval, recipient, instantly: None)
    seen = []
    for minutes in (0, 11, 22):
        flushed = A.flush_queued(world["inst"], store=world["store"], now=FLUSH + timedelta(minutes=minutes))
        seen.append([(f["status"], f.get("escalated")) for f in flushed])
        if minutes < 22:
            assert _pushes() == []
    assert seen == [[("approved_queued", False)], [("approved_queued", False)], [("send_failed", True)]]
    push = _only_card_push()
    assert push["message"].startswith("Not auto-sent: %s\n" % A.REASON_TEXT["recipient_unconfirmed"])
    assert "Mark sent" not in push["actions"] and "view, Retry, " in push["actions"]
    assert world["inst"].sent == []
    # nothing more on the next flush
    A.flush_queued(world["inst"], store=world["store"], now=FLUSH + timedelta(minutes=33))
    assert len(_pushes()) == 1


# ======================================================= the 07:00 flush
def test_a_queued_template_card_whose_flush_send_fails_is_pushed_once(world, monkeypatch):
    card, v = _card(world, now=NIGHT)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NIGHT, verdict=v)
    assert _stored(world, card).status == "approved_queued" and _pushes() == []
    monkeypatch.setattr(world["inst"], "reply_to_email", _boom)
    flushed = A.flush_queued(world["inst"], store=world["store"], now=FLUSH)
    assert [f["status"] for f in flushed] == ["send_failed"] and flushed[0]["pushed"]
    push = _only_card_push()
    assert push["message"].startswith("Not auto-sent: %s\n" % A.REASON_TEXT["send_failed"])
    assert "view, Retry, " in push["actions"] and "view, Mark sent, " in push["actions"]
    # a later flush does not push it again
    A.flush_queued(world["inst"], store=world["store"], now=FLUSH + timedelta(minutes=5))
    assert len(_pushes()) == 1


@pytest.mark.parametrize("left_at", ["send_failed", "approved_queued"])
def test_an_exception_in_the_flush_pushes_the_card_only_when_it_is_left_for_lorenzo(world, monkeypatch, left_at):
    card, v = _card(world, now=NIGHT)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NIGHT, verdict=v)
    st = world["store"]
    key = A.APPROVAL_PREFIX + A._approval_id(card)

    def raising(approval, instantly, store=None, now=None, ghl=None):
        row = st.get(key)
        st.set(key, dict(row, status=left_at))
        raise RuntimeError("store hiccup")

    monkeypatch.setattr(A, "send_approved", raising)
    flushed = A.flush_queued(world["inst"], store=st, now=FLUSH)
    assert len(flushed) == 1 and flushed[0]["ok"] is False and flushed[0]["status"] == left_at
    if left_at == "send_failed":
        push = _only_card_push()
        assert push["message"].startswith("Not auto-sent: %s\n" % A.REASON_TEXT["send_raised"])
        assert "view, Retry, " in push["actions"]
    else:
        # its send may run again on the next flush: not pushed, still deferred
        assert _pushes() == [] and st.get(key)["notify_result"]["deferred"]
    assert _rows(world, "flush_send_raised")


def test_an_auto_send_that_raises_after_send_failed_pushes_the_recovery_card(world, monkeypatch):
    card, v = _card(world)
    st = world["store"]
    key = A.APPROVAL_PREFIX + A._approval_id(card)

    def raising(approval, instantly, st_, ts, ghl, actor):
        row = st.get(key)
        st.set(key, dict(row, status="send_failed"))
        raise RuntimeError("after the send")

    monkeypatch.setattr(A, "_approve_loaded", raising)
    out = A.auto_send_approved(card, world["inst"], store=st, now=NOW, verdict=v)
    assert out["ok"] is False and out["pushed"]
    push = _only_card_push()
    assert push["message"].startswith("Not auto-sent: the auto-send failed (RuntimeError).")
    assert "view, Retry, " in push["actions"]


# ================================================= no push when it went well
def test_a_send_and_a_queue_push_no_card(world):
    card, v = _card(world)
    assert A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)["status"] == "sent"
    queued, v2 = _card(world, now=NIGHT, email_id="e-2")
    out = A.auto_send_approved(queued, world["inst"], store=world["store"], now=NIGHT, verdict=v2)
    assert out["status"] == "approved_queued"
    assert _pushes() == []


# ============================================================ the stuck push
def test_the_stuck_push_carries_retry_and_veto_links_for_a_failed_send(world, monkeypatch):
    card, v = _card(world)
    monkeypatch.setattr(world["inst"], "reply_to_email", _boom)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    stored = _stored(world, card)
    later = NOW + timedelta(minutes=40)
    notify.reset_for_tests()
    assert P._push_stuck(world["store"], P.pending_approvals(world["store"], later), later) == [
        A._approval_id(card)]
    push = notify.sent_in_test[-1]
    assert "before you press Retry" in push["message"]
    assert push["actions"] == "view, Mark sent, %s" % _link("mark-sent", stored)
    # public topic: no link in the text, and it says where they are
    assert "http" not in push["message"] and "links for each card are in the email" in push["message"]
    em = push["email_message"]
    assert "  Retry: %s" % _link("retry", stored) in em and "  Veto: %s" % _link("veto", stored) in em


def test_the_stuck_push_for_a_recipient_hold_carries_the_veto_it_asks_for(world, monkeypatch):
    card, v = _card(world)
    monkeypatch.setattr(A, "settings", _LiveView())
    monkeypatch.setattr(A, "_recipient_verdict", lambda approval, recipient, instantly: False)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    monkeypatch.setattr(A, "settings", real_settings)
    stored = _stored(world, card)
    later = NOW + timedelta(minutes=40)
    notify.reset_for_tests()
    P._push_stuck(world["store"], P.pending_approvals(world["store"], later), later)
    push = notify.sent_in_test[-1]
    assert "Veto it, or check the thread in Instantly." in push["message"] and push["actions"] is None
    em = push["email_message"]
    assert "  Veto: %s" % _link("veto", stored) in em and "  Retry: %s" % _link("retry", stored) in em
    assert "/mark-sent/" not in em


def test_on_a_protected_topic_the_stuck_push_has_the_links_in_its_text(world, monkeypatch):
    card, v = _card(world)
    monkeypatch.setattr(world["inst"], "reply_to_email", _boom)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    monkeypatch.setenv("NTFY_TOKEN", "unit-token")
    stored = _stored(world, card)
    later = NOW + timedelta(minutes=40)
    notify.reset_for_tests()
    P._push_stuck(world["store"], P.pending_approvals(world["store"], later), later)
    push = notify.sent_in_test[-1]
    assert "  Retry: %s" % _link("retry", stored) in push["message"] and "email_message" not in push


def test_the_stuck_push_says_so_when_it_cannot_build_the_links(world, monkeypatch):
    card, v = _card(world)
    monkeypatch.setattr(world["inst"], "reply_to_email", _boom)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)

    def no_base(*a, **k):
        raise A.ApprovalUndeliverable("BASE_URL is unset")

    monkeypatch.setattr(A, "recovery_links", no_base)
    later = NOW + timedelta(minutes=40)
    notify.reset_for_tests()
    P._push_stuck(world["store"], P.pending_approvals(world["store"], later), later)
    push = notify.sent_in_test[-1]
    assert "This push carries no Retry or Veto link for %s" % LEAD in push["message"]


# ================================================================== the FYI
def test_the_fyi_in_shadow_says_would_have_sent_not_sent(world, monkeypatch):
    monkeypatch.setenv("NOTIFY_SHADOW_SEND", "1")
    card, v = _card(world)
    A.auto_send_approved(card, world["inst"], store=world["store"], now=NOW, verdict=v)
    calls = []

    def capture(title, message, **kw):
        calls.append(dict(kw, title=title, message=message))
        return {"sent": True}

    out = A.flush_auto_send_fyi(world["store"], now=NOW + timedelta(minutes=1), notify_fn=capture)
    assert out["sent"] is True and len(calls) == 1
    c = calls[0]
    assert c["title"] == "Auto-sent from approved templates (shadow): 1 would have sent (shadow), 0 queued, 0 held"
    assert "%s: 1 would have sent (shadow)" % TID in c["message"]
    assert " 1 sent" not in c["title"] + c["message"]
    assert "%s would have sent (shadow)" % TID in c["email_message"]


def test_the_fyi_in_live_says_sent(world, monkeypatch):
    gate.record_auto_send(world["store"], kind="first_reply", template_id=TID, approval_id="a1", status="sent",
                          now=NOW)
    monkeypatch.setattr(A, "settings", _LiveView())
    calls = []

    def capture(title, message, **kw):
        calls.append(dict(kw, title=title, message=message))
        return {"sent": True}

    A.flush_auto_send_fyi(world["store"], now=ct(2030, 1, 7, 10, 1), notify_fn=capture)
    assert calls[0]["title"] == "Auto-sent from approved templates: 1 sent, 0 queued, 0 held"
    assert "%s: 1 sent" % TID in calls[0]["message"]
