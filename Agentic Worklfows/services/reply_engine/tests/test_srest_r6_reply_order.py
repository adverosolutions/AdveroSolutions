"""S-rest round 6, item 2: approval reads the order of a lead's replies by the
router's rule.

The router processes a reply that cannot be shown to be older as the lead's
newest one: a reply is older (router.STALE_OLDER_REPLY) only when it and a
newer reply both carry the email's own time (models.entry_email_time). The
send-time check (approval.lead_replies_after, through _entry_time) read a
processing-time stand-in as a send time. So a newer reply with no email time
of its own, processed first, looked newer than the older reply the router
then processed as the newest, and the card answering that reply was held for
good: the round-4 dead card, back (the reviewer's probe B2). Now:

* a reply that is not an opt-out is newer than the card's reply by the
  email's own time when both carry one, otherwise by the order the two were
  processed in, which is the order the router took them as the newest in;
* the card's own reply counts as having no email time when its history entry
  records a processing-time stand-in;
* an opt-out keeps its received_at, a stand-in included, as the router's
  opt-out marker does: it stands unless the card's reply was provably sent
  after it;
* approval and router read entries through the same models readers.

Every lead is an example.com address, or the recorded Sopio fixture; every
client is an in-process fake. Live mode is never set.
"""
import pytest
import pytz

from shared import notify

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import models
from services.reply_engine import router
from services.reply_engine.models import ReplyEvent

from test_send_safety_round2 import SOPIO, SOPIO_KEY, _process, ct, env, webhook_payload  # noqa: F401
from test_send_safety_srest_r3_optout import (  # noqa: F401 - the r3 world, fakes and card helper
    CAMPAIGN, EACCOUNT, IN_HOURS, LEAD, POSITIVE, SUBJECT, THREAD, _direct_card, _reply, world,
)
from test_srest_r4_approval import _row

KEY = "lead:%s:%s" % (CAMPAIGN, LEAD)
QUESTION = "How much does this cost per month, roughly?"


def _utc(dt):
    return dt.astimezone(pytz.utc).isoformat()


def _id(token):
    return token.split(".", 1)[0]


def _held():
    return [n for n in notify.sent_in_test if "HELD" in n["title"]]


def _inbound(email_id, label, processed, sent=None):
    """An inbound history entry as the pipeline writes it: ``sent`` the
    email's own time, or None for a reply whose payload carried no time (its
    processing time stands in, marked "processing")."""
    entry = {"at": processed.isoformat(), "event": "inbound", "email_id": email_id, "label": label,
             "source": "webhook"}
    if sent is not None:
        entry["received_at"] = _utc(sent)
    else:
        entry["received_at"] = _utc(processed)
        entry["received_at_source"] = models.RECEIVED_AT_PROCESSING
    return entry


def _after(row, card, **kw):
    return [r["email_id"] for r in A.lead_replies_after(row, card, **kw)]


def _reply_without_time(world, email_id, text, now):
    """One webhook reply through the real pipeline whose payload carries no
    time: its history entry records the processing time as a stand-in."""
    payload = {"event_type": "reply_received", "campaign_id": CAMPAIGN, "campaign_name": "x", "lead_email": LEAD,
               "email_account": EACCOUNT, "firstName": "Owner", "companyName": "Example Services",
               "reply_subject": SUBJECT, "reply_text": text, "email_id": email_id, "thread_id": THREAD,
               "unibox_url": "https://app.instantly.ai/app/unibox"}
    return app_mod.process_event(ReplyEvent.from_webhook(payload), deps=world["deps"], now=now, busy_blocks=[])


# ======================================================== the probe, adapted
def test_the_older_reply_the_router_took_as_newest_is_sent_when_the_newer_one_has_no_email_time(env):
    """Probe B2: the lead's newer reply ("Thursday 4pm ET works") reaches the
    engine without a timestamp and is processed first; their older question
    is processed after it. The router cannot show the question is older, so
    it processes it as the newest: its card supersedes the other and takes
    the call. That card was then held for "the lead wrote again", which it
    never can stop saying. Now it is sent."""
    st = env["store"]
    no_time = webhook_payload(SOPIO, "2026-09-21T17:37")
    no_time.pop("timestamp")
    newer = _process(env, no_time, ct(2026, 9, 21, 12, 40))
    older = _process(env, webhook_payload(SOPIO, "2026-09-21T14:42"), ct(2026, 9, 21, 12, 45))
    assert newer["label"] == "positive_interested" and newer["approval_token"]
    assert older["label"] == "positive_question" and older["stale"] is None and older["approval_token"]
    assert older["superseded"] == [newer["approval_token"]]
    assert older["booking_handoff"]["action"] == "transferred"

    row = st.get(SOPIO_KEY)
    entries = {e["email_id"]: e for e in row["history"] if e.get("event") == "inbound"}
    assert entries[newer["email_id"]]["received_at_source"] == "processing"
    assert "received_at_source" not in entries[older["email_id"]]
    card = A.load(older["approval_token"], st)
    context = A.card_context(st, _id(older["approval_token"]))
    assert _after(row, card, seen_before=context["processed_before"], reply_at=context["reply_at"]) == []
    assert A.lead_reply_hold(row, card, context["processed_before"], reply_at=context["reply_at"]) is None

    out = A.approve(older["approval_token"], env["deps"].instantly, store=st, now=ct(2026, 9, 21, 13, 0),
                    ghl=env["deps"].ghl)
    assert out["ok"] is True and out["status"] == "sent" and not out.get("lead_reply")
    assert A.load(older["approval_token"], st).status == "sent"
    assert _held() == []


def test_a_reply_with_no_email_time_processed_after_the_cards_reply_still_holds_it(world):
    """The other order: the router processes the reply with no time as the
    newest, so the card answering the earlier one is held at the send."""
    st = world["store"]
    first = _reply(world, "t-1", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    second = _reply_without_time(world, "t-2", QUESTION, ct(2026, 9, 28, 9, 40))
    assert second["stale"] is None and second["superseded"] == [first["approval_token"]]
    row = st.get(KEY)
    assert [e.get("received_at_source") for e in row["history"] if e.get("event") == "inbound"] == [
        None, "processing"]
    card = A._approval_row(st, _id(first["approval_token"]))
    context = A.card_context(st, _id(first["approval_token"]))
    assert _after(row, card, seen_before=context["processed_before"], reply_at=context["reply_at"]) == ["t-2"]
    why = A.lead_reply_hold(row, card, context["processed_before"], reply_at=context["reply_at"])
    assert why["reason"] == "newer_reply" and why["email_id"] == "t-2"


# ======================================================== the card's own time
def test_a_card_whose_reply_has_no_email_time_is_held_for_a_reply_processed_after_it(world):
    """The card's own reply carries only a processing time (9:40). The
    router takes a reply processed after it as the newest, even one whose
    email time (9:35) is earlier than that stand-in. Compared with the
    stand-in, it looked older and the card went out over it."""
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=ct(2026, 9, 28, 9, 40))
    _row(st, [card.token], ["e-1", "e-2"],
         [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 40)),
          _inbound("e-2", "neutral_question", ct(2026, 9, 28, 9, 45), sent=ct(2026, 9, 28, 9, 35))])
    row = st.get(card.state_key)
    state = models.LeadState.from_store(row)
    # the router: e-2 cannot be shown to be older than e-1, so it was processed as new
    assert router.stale_reason(state, "neutral_question", ct(2026, 9, 28, 9, 35), email_id="e-2") is None
    assert _after(row, card, seen_before=[], reply_at=ct(2026, 9, 28, 9, 40).isoformat()) == ["e-2"]
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and out["lead_reply"]["email_id"] == "e-2"
    assert world["inst"].sent == []


def test_a_card_whose_reply_has_no_email_time_is_not_held_for_a_reply_processed_before_it(world):
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=ct(2026, 9, 28, 9, 40))
    _row(st, [card.token], ["e-2", "e-1"],
         [_inbound("e-2", "neutral_question", ct(2026, 9, 28, 9, 36), sent=ct(2026, 9, 28, 9, 35)),
          _inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 40))])
    row = st.get(card.state_key)
    assert _after(row, card, seen_before=["e-2"], reply_at=ct(2026, 9, 28, 9, 40).isoformat()) == []
    out = A.approve(card.token, world["inst"], store=st, now=IN_HOURS, ghl=world["ghl"])
    assert out["ok"] is True and out["status"] == "sent" and len(world["inst"].sent) == 1


# ================================================= the one rule, both sides
def test_approval_and_router_agree_on_which_replies_are_newer(world):
    """A row mixing email times, processing stand-ins, an entry from before
    received_at existed and a machine's reply. The replies approval counts as
    newer by the email's own time are exactly the ones router.newer_replies
    finds; every other one it counts was processed after the card's reply.
    p-0, processed before it, is not newer whatever its stand-in says: the
    router took the card's reply as the newest then."""
    st = world["store"]
    card = _direct_card(st, "c1", email_id="s", created=ct(2026, 9, 28, 9, 1))
    legacy = {"at": ct(2026, 9, 28, 9, 50).isoformat(), "event": "inbound", "email_id": "l-1",
              "label": "neutral_question", "source": "webhook"}
    history = [
        # processed before the card's reply, its stand-in (9:00:30) after that reply's own time (9:00)
        _inbound("p-0", "neutral_question", ct(2026, 9, 28, 9, 0, 30)),
        _inbound("s", "positive_question", ct(2026, 9, 28, 9, 1), sent=ct(2026, 9, 28, 9, 0)),
        _inbound("e-1", "neutral_question", ct(2026, 9, 28, 9, 20), sent=ct(2026, 9, 28, 8, 50)),   # older
        _inbound("e-2", "neutral_question", ct(2026, 9, 28, 9, 21), sent=ct(2026, 9, 28, 9, 10)),   # newer
        _inbound("p-1", "neutral_question", ct(2026, 9, 28, 9, 30)),                         # stand-in, after
        _inbound("m-1", "ooo", ct(2026, 9, 28, 9, 31), sent=ct(2026, 9, 28, 9, 20)),         # a machine
        legacy,                                                                              # no received_at
    ]
    _row(st, [card.token], [e["email_id"] for e in history], history)
    row = st.get(card.state_key)
    after = A.lead_replies_after(row, card, seen_before=["p-0"], reply_at=ct(2026, 9, 28, 9, 0).isoformat())
    assert sorted(r["email_id"] for r in after) == ["e-2", "l-1", "m-1", "p-1"]
    assert [r["email_id"] for r in after if r["machine"]] == ["m-1"]
    entries = {e["email_id"]: e for e in history}
    by_email_time = sorted(r["email_id"] for r in after
                           if not r["machine"] and models.entry_email_time(entries[r["email_id"]]) is not None)
    routers = router.newer_replies(row, ct(2026, 9, 28, 9, 0), email_id="s", include_opt_outs=False)
    assert by_email_time == sorted(e["email_id"] for e in routers) == ["e-2"]
    order = row["processed_email_ids"]
    for r in after:
        if models.entry_email_time(entries[r["email_id"]]) is None:
            assert order.index(r["email_id"]) > order.index("s"), r


def test_approval_and_router_read_reply_times_through_the_same_models_readers():
    assert A.entry_email_time is models.entry_email_time is router.entry_email_time
    assert A.entry_received_at is models.entry_received_at
    at = ct(2026, 9, 28, 9, 40)
    entries = [
        _inbound("a", "neutral_question", at, sent=ct(2026, 9, 28, 9, 0)),
        _inbound("b", "neutral_question", at),
        {"at": at.isoformat(), "event": "inbound", "email_id": "c", "label": "unsubscribe"},
        {"event": "inbound", "email_id": "d", "received_at": "not a time"},
        {},
    ]
    for entry in entries:
        assert A._entry_time(entry) == models.entry_email_time(entry)
        assert A._entry_time(entry, opt_out=True) == models.entry_received_at(entry)
    assert A._entry_time(entries[1]) is None and A._entry_time(entries[1], opt_out=True) == at


# ============================================ an opt-out keeps its stand-in
@pytest.mark.parametrize("processed,holds", [(ct(2026, 9, 28, 9, 31), True), (ct(2026, 9, 28, 8, 50), False)],
                         ids=["stand_in_after_the_cards_reply", "stand_in_before_it"])
def test_an_opt_out_with_only_a_processing_time_stands_unless_the_card_is_provably_later(world, processed, holds):
    """As the router's marker: an opt-out with only a processing time is
    timed by that stand-in, and a reply beats it only when its own email
    time is later. Processed before the card's reply (9:00, processed 9:40),
    at 9:31 it still holds the card; at 8:50 the card's reply is provably
    later."""
    st = world["store"]
    card = _direct_card(st, "c1", email_id="e-1", created=ct(2026, 9, 28, 9, 40))
    _row(st, [card.token], ["e-2", "e-1"],
         [_inbound("e-2", "unsubscribe", processed),
          _inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 40), sent=ct(2026, 9, 28, 9, 0))])
    row = st.get(card.state_key)
    why = A.lead_reply_hold(row, card, ["e-2"], reply_at=ct(2026, 9, 28, 9, 0).isoformat())
    if holds:
        assert why["reason"] == "opt_out" and why["category"] == "unsubscribe" and why["email_id"] == "e-2"
    else:
        assert why is None
