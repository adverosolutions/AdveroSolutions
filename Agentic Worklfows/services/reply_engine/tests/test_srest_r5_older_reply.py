"""S-rest round 5, defect 1: a reply the lead SENT before a newer human reply
of theirs, processed after it (a poller retry after its first attempt raised,
or a reply a killed run still held).

Round 4 processed it as a new reply that only kept the newer classification.
It superseded the newer reply's open card (pending, or approved and queued for
07:00), handed the call that card had booked to a card of its own, stopped
the follow-ups the newer answer had armed, and raised a card that the
send-time check then held ("the lead wrote again"): nothing could be sent,
and the HELD push told Lorenzo to Veto the card holding the call the lead had
just accepted. Now such a reply is stale (router.STALE_OLDER_REPLY,
"older_than_newest_reply"): it is recorded on the history and nothing else
moves. No card is superseded, no booked call is taken, moved or released, no
follow-up is stopped or re-armed, no card is drafted, and one push names the
older reply, the card that stays and that it can still be sent.

An opt-out keeps the marker rules (reviewer ruling 1): one the lead sent
before a newer reply still takes effect and holds their cards. The HELD push
now names that newer reply (Q1), and when no card was left to hold (the
answer to the newer reply had gone out) one push says what was applied (Q1b).

The HELD push for "the lead wrote again" is worded from the facts: "after the
card was drafted" only when it was, the card answering the newer reply named
(or that it raised none), and no Veto by default for a card that holds the
lead's call.

Every lead is an example.com address, or the recorded Sopio fixture; every
client is an in-process fake. Live mode is set in-process only.
"""
from datetime import timedelta

import pytest

from shared import notify

from jobs import cadence_tick as cadence_job
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import cadence
from services.reply_engine import poller as P
from services.reply_engine import router
from services.reply_engine import show_rate
from services.reply_engine.models import Approval, Draft, LeadState, ReplyEvent

from test_send_safety_round2 import SOPIO, SOPIO_KEY, THU_3PM, env, webhook_payload  # noqa: F401
from test_srest_r4_ingest_order import (  # noqa: F401 - the round-4 world, fakes and helpers
    CAMPAIGN, EACCOUNT, FREE, KEY, LEAD, POSITIVE, REMOVE, SUBJECT, FakeInstantly, _calls, _cards, _entry, _go_live,
    _item, _reply, ct, utc, world,
)

OLDER = "older_than_newest_reply"
OLDER_TITLE = "An older reply from %s arrived after their newer one; not drafted"
LATE_OPT_OUT_TITLE = "An older opt-out from %s arrived after their newer reply; applied"
QUESTION = "How much does this cost per month, roughly?"
OOO = "I am out of the office until Monday, October 5, with limited access to email."
OOO_SUBJECT = "Automatic reply: Pat, question"
THU_LABEL = "Thu Sep 24 3:00pm CT"


def _pushes(fragment=""):
    return [n for n in notify.sent_in_test if fragment in n["title"]]


def _sopio(env, ts_prefix, now):
    """One recorded Sopio reply through the real pipeline, at ``now``."""
    env["clock"]["now"] = now
    return app_mod.process_event(ReplyEvent.from_webhook(webhook_payload(SOPIO, ts_prefix)),
                                 deps=env["deps"], now=now, busy_blocks=[])


def _id(token):
    return token.split(".", 1)[0]


def _booking(st, key=SOPIO_KEY):
    return dict((st.get(key).get("cadence") or {}).get("booking") or {})


def _unmoved(row, before):
    """The row as the newer reply left it: nothing the older reply could
    have rewritten moved."""
    for field in ("status", "classification", "approvals", "last_email_id", "last_inbound_at", "cadence",
                  "opt_out", "drafts"):
        assert row.get(field) == before.get(field), field


# ============================================ Q2: the newer reply booked the call
def test_q2_an_older_question_leaves_the_newer_booking_card_sendable_and_it_confirms_the_call(env):
    st = env["store"]
    newer = _sopio(env, "2026-09-21T17:37", ct(2026, 9, 21, 12, 40))       # "Thursday 4pm ET works"
    card_b = _id(newer["approval_token"])
    assert newer["label"] == "positive_interested" and newer["booking"]["slot"] == THU_3PM
    before = st.get(SOPIO_KEY)
    booking = _booking(st)
    assert booking["owner"] == card_b and booking["awaiting_approval"] is True
    pushes = len(notify.sent_in_test)

    older = _sopio(env, "2026-09-21T14:42", ct(2026, 9, 21, 12, 45))       # "What is your percentage?"
    assert older["label"] == "positive_question" and older["stale"] == OLDER
    assert older["approval_token"] is None and older["draft"] is None and older["cards_held"] == []
    assert older["superseded"] == [] and older["booking_handoff"] is None and older["cadence_stopped"] is None
    assert [(a["action"], a["kind"]) for a in older["actions"]] == [("stale_reply", "skipped")]

    row = st.get(SOPIO_KEY)
    _unmoved(row, before)
    assert _booking(st) == booking                                        # not taken, moved or released
    assert A._approval_row(st, card_b).status == "pending"
    assert _cards(st) == [A.APPROVAL_PREFIX + card_b]                    # no card for the older reply
    entry = _entry(row, older["email_id"])
    assert entry["stale"] == OLDER and entry["label"] == "positive_question"
    assert entry["received_at"] == "2026-09-21T14:42:35+00:00"
    assert older["email_id"] in row["processed_email_ids"]

    new = notify.sent_in_test[pushes:]
    assert [n["title"] for n in new] == [OLDER_TITLE % SOPIO]            # one push, no HELD push
    msg = new[0]["message"]
    assert new[0]["priority"] == "high" and msg.startswith("Nothing was sent and no new card was drafted.")
    assert "The lead sent it Mon Sep 21 9:42am CT (positive_question)" in msg
    assert "before their newer reply (positive_interested, sent Mon Sep 21 12:37pm CT)" in msg
    assert ("Card %s, which answers their newer reply, is still open and can be approved and sent as usual, and "
            "sending it confirms the call booked for %s." % (card_b, THU_LABEL)) in msg
    assert "Edit that card before you approve it, or reply by hand" in msg
    assert "Veto" not in msg and u"\u2014" not in msg

    # the newer card goes out and confirms the call the lead accepted
    sent = A.approve(newer["approval_token"], env["deps"].instantly, store=st, now=ct(2026, 9, 21, 13, 0),
                     ghl=env["deps"].ghl)
    assert sent["ok"] is True and sent["status"] == "sent"
    booking = _booking(st)
    assert booking["awaiting_approval"] is False and booking["confirmed_by"] == card_b and "owner" not in booking
    assert not show_rate.is_held(st, booking["appointment_id"])
    assert not _pushes("HELD")


def test_q2b_nothing_is_left_that_a_veto_could_use_to_cancel_the_accepted_call(env):
    """Round 4 raised a card for the older question that took the call, was
    held, and told Lorenzo to Veto it, which cancelled the call. Now nothing
    of the older reply can be approved, vetoed or expire holding the call."""
    st = env["store"]
    newer = _sopio(env, "2026-09-21T17:37", ct(2026, 9, 21, 12, 40))
    booking = _booking(st)
    older = _sopio(env, "2026-09-21T14:42", ct(2026, 9, 21, 12, 45))
    assert older["approval_token"] is None
    # the queue flush and the expiry sweep leave the call and its card alone
    assert A.flush_queued(env["deps"].instantly, store=st, now=ct(2026, 9, 21, 13, 0), ghl=env["deps"].ghl) == []
    assert A.expire_overdue(st, now=ct(2026, 9, 21, 13, 5)) == []
    assert _booking(st) == booking and show_rate.is_held(st, booking["appointment_id"])
    assert A._approval_row(st, _id(newer["approval_token"])).status == "pending"
    assert [n["title"] for n in notify.sent_in_test] == [
        "Reply to approve: booking confirmation", OLDER_TITLE % SOPIO]


# ================================ Q5a: the booking card was approved at night
def test_q5a_an_older_reply_leaves_the_queued_booking_card_to_go_out_at_seven(env):
    st = env["store"]
    newer = _sopio(env, "2026-09-21T17:37", ct(2026, 9, 21, 12, 40))
    card_b = _id(newer["approval_token"])
    queued = A.approve(newer["approval_token"], env["deps"].instantly, store=st, now=ct(2026, 9, 21, 20, 0),
                       ghl=env["deps"].ghl)
    assert queued["status"] == "approved_queued"
    before = st.get(SOPIO_KEY)
    pushes = len(notify.sent_in_test)

    older = _sopio(env, "2026-09-21T14:42", ct(2026, 9, 21, 20, 5))
    assert older["stale"] == OLDER and older["superseded"] == [] and older["booking_handoff"] is None
    _unmoved(st.get(SOPIO_KEY), before)
    assert A._approval_row(st, card_b).status == "approved_queued"
    assert _booking(st)["owner"] == card_b
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert len(notify.sent_in_test) == pushes + 1
    assert ("Card %s, which answers their newer reply, is still approved and goes out when the sending window "
            "opens, and sending it confirms the call booked for %s." % (card_b, THU_LABEL)) in msg

    # 07:05: the queue sends it, and the call is confirmed
    A.flush_queued(env["deps"].instantly, store=st, now=ct(2026, 9, 22, 7, 5), ghl=env["deps"].ghl)
    assert A._approval_row(st, card_b).status == "sent"
    booking = _booking(st)
    assert booking["awaiting_approval"] is False and booking["confirmed_by"] == card_b
    assert not _pushes("HELD")


# ======================= Q5b: the answer to the newer reply went out and armed
def _answered(world, email_id="q5-2", received=ct(2026, 9, 28, 9, 30)):
    pos = _reply(world, email_id, POSITIVE, received, received + timedelta(minutes=1))
    sent = A.approve(pos["approval_token"], world["inst"], store=world["store"], now=ct(2026, 9, 28, 9, 35),
                     ghl=world["ghl"])
    assert sent["status"] == "sent" and sent["cadence"]["armed"] is True
    return pos


def test_q5b_an_older_question_after_the_newer_answer_went_out_leaves_the_follow_ups_running(world):
    st = world["store"]
    pos = _answered(world)
    before = st.get(KEY)
    cad = dict(before["cadence"])
    assert cad["armed_at"] and cad["next_send_at"] and not cad.get("stopped_reason")
    calls = _calls(world)
    pushes = len(notify.sent_in_test)

    old = _reply(world, "q5-1", QUESTION, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert old["stale"] == OLDER and old["approval_token"] is None and old["cadence_stopped"] is None
    row = st.get(KEY)
    _unmoved(row, before)
    assert row["cadence"] == cad                                           # not stopped, not re-armed
    assert _calls(world) == calls                                          # no interest, no CRM write, no send
    state = LeadState.from_store(row)
    assert cadence.stop_reason(state, ct(2026, 9, 29, 10, 0)) is None
    assert cadence.inbounds_since_baseline(state) == []
    assert _cards(st) == [A.APPROVAL_PREFIX + _id(pos["approval_token"])]

    new = notify.sent_in_test[pushes:]
    assert [n["title"] for n in new] == [OLDER_TITLE % LEAD]
    msg = new[0]["message"]
    assert ("The answer to their newer reply already went out (card %s); the follow-ups it started keep running."
            % _id(pos["approval_token"])) in msg
    assert "if it asks something the answer to their newer reply does not cover, reply by hand" in msg

    # the hourly tick on D1's day: the ladder is not stopped for the older reply, D1 goes out
    due = LeadState.from_store(row).cadence["next_send_at"]
    summary = cadence_job.run(A._time_of(due) + timedelta(minutes=5), st, FakeInstantly(), None, free_slots=FREE,
                              notify_fn=lambda *a, **k: None, log_fn=lambda *a, **k: None)
    mine = [r for r in summary["results"] if r.get("lead_email") == LEAD]
    assert [r["action"] for r in mine] == ["sent"], mine                  # D1 goes out (shadow)
    assert not (st.get(KEY)["cadence"] or {}).get("stopped_reason")


# ================================== Q1 / Q1b: an older opt-out keeps its rules
def test_q1_an_older_opt_out_still_holds_the_newer_card_and_the_held_push_names_the_newer_reply(world):
    st = world["store"]
    pos = _reply(world, "q1-2", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    card = _id(pos["approval_token"])
    pushes = len(notify.sent_in_test)

    unsub = _reply(world, "q1-1", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert unsub["label"] == "unsubscribe" and unsub["stale"] is None and unsub["opt_out"] == "set"
    assert unsub["cards_held"] == [card] and unsub["newer_reply"] == "q1-2"
    assert unsub["late_opt_out_alert"] is False
    row = st.get(KEY)
    assert row["opt_out"]["email_id"] == "q1-1" and row["status"] == "blocklisted"
    assert world["inst"].blocklist == [LEAD]
    assert A._approval_row(st, card).status == "blocked"

    new = notify.sent_in_test[pushes:]
    assert [n["title"] for n in new] == ["Reply to %s HELD: the lead asked to be removed" % LEAD]
    msg = new[0]["message"]
    assert "The lead asked to be removed (unsubscribe, Mon Sep 28 9:00am CT)." in msg
    assert "They wrote again after it (positive_question, Mon Sep 28 9:30am CT); this answer still stands." in msg
    assert "Read the whole thread in Instantly before you Veto it or anything else goes to them." in msg
    assert "Do not reply to them: they asked not to be emailed." in msg and "by hand" not in msg
    problem = [p for p in A._approval_row(st, card).draft.problems if "this reply must not go out" in p]
    assert len(problem) == 1 and "They wrote again after it (positive_question" in problem[0]
    assert A.approve(pos["approval_token"], world["inst"], store=st, now=ct(2026, 9, 28, 10, 0),
                     ghl=world["ghl"])["ok"] is False
    assert world["inst"].sent == []


def test_q1b_an_older_opt_out_after_the_newer_answer_went_out_is_applied_and_pushed_once(world):
    st = world["store"]
    pos = _answered(world, "q1b-2")
    pushes = len(notify.sent_in_test)

    unsub = _reply(world, "q1b-1", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert unsub["stale"] is None and unsub["cards_held"] == [] and unsub["newer_reply"] == "q1b-2"
    assert unsub["late_opt_out_alert"] is True and unsub["cadence_stopped"] == "inbound_reply"
    row = st.get(KEY)
    assert row["status"] == "blocklisted" and row["opt_out"]["email_id"] == "q1b-1"
    assert world["inst"].blocklist == [LEAD]
    assert row["cadence"]["stopped_reason"] and row["cadence"]["next_send_at"] is None     # the ladder is stopped
    assert cadence.stop_reason(LeadState.from_store(row), ct(2026, 9, 29, 10, 0)) is not None

    new = notify.sent_in_test[pushes:]
    assert [n["title"] for n in new] == [LATE_OPT_OUT_TITLE % LEAD]
    msg = new[0]["message"]
    assert ("The lead asked to be removed (unsubscribe, sent Mon Sep 28 9:00am CT) before their newer reply "
            "(positive_question, sent Mon Sep 28 9:30am CT), and the engine processed it after that reply.") in msg
    assert "It took effect: their status is now blocklisted and the follow-ups are stopped." in msg
    assert ("The answer to their newer reply had already gone out (card %s), so no card was held."
            % _id(pos["approval_token"])) in msg
    assert msg.endswith("Do not reply to them: they asked not to be emailed.") and "by hand" not in msg


def test_an_opt_out_sent_after_every_other_reply_gets_no_newer_reply_note(world):
    """The ordinary order: nothing newer, so neither the Q1 sentence nor the
    Q1b push."""
    pos = _reply(world, "n-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1))
    pushes = len(notify.sent_in_test)
    unsub = _reply(world, "n-2", REMOVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    assert unsub["newer_reply"] is None and unsub["late_opt_out_alert"] is False
    assert unsub["cards_held"] == [_id(pos["approval_token"])]
    new = notify.sent_in_test[pushes:]
    assert len(new) == 1 and "They wrote again" not in new[0]["message"] and "Veto it." in new[0]["message"]


# ======================================== other older replies, and the boundary
def test_an_older_out_of_office_after_a_newer_reply_pauses_nothing(world):
    st = world["store"]
    pos = _reply(world, "o-2", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    before = st.get(KEY)
    calls = _calls(world)
    ooo = _reply(world, "o-1", OOO, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40), subject=OOO_SUBJECT)
    assert ooo["label"] == "ooo" and ooo["stale"] == OLDER
    _unmoved(st.get(KEY), before)                                         # no "ooo" status, no pause
    assert _calls(world) == calls                                         # no Instantly interest reset to 0
    assert A._approval_row(st, _id(pos["approval_token"])).status == "pending"
    msg = _pushes(OLDER_TITLE % LEAD)[0]["message"]
    assert "(ooo)" in msg and msg.endswith("It is an automatic reply, so nothing needs doing.")


def test_a_newer_machine_reply_never_makes_the_leads_own_reply_older(world):
    """An out-of-office the lead's mailbox sent after their own reply, and
    processed first, is not a newer reply of theirs: the lead's own reply is
    processed as usual and gets its card."""
    ooo = _reply(world, "m-2", OOO, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31), subject=OOO_SUBJECT)
    assert ooo["label"] == "ooo" and ooo["stale"] is None
    pos = _reply(world, "m-1", POSITIVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert pos["label"] == "positive_question" and pos["stale"] is None and pos["approval_token"]
    assert world["store"].get(KEY)["classification"]["label"] == "positive_question"
    assert not _pushes(OLDER_TITLE % LEAD)


def test_a_reply_with_no_time_of_its_own_cannot_be_shown_older_and_is_processed_as_new(world):
    st = world["store"]
    first = _reply(world, "t-1", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    other = _reply(world, "t-2", QUESTION, None, ct(2026, 9, 28, 9, 40))
    assert other["stale"] is None and other["approval_token"]
    assert other["superseded"] == [first["approval_token"]]
    assert _entry(st.get(KEY), "t-2")["received_at_source"] == "processing"
    assert not _pushes(OLDER_TITLE % LEAD)


def test_the_poller_retry_of_an_older_reply_records_it_and_the_newer_card_stays(world, monkeypatch):
    """The real path: the older reply's first attempt raised, the newer one
    was processed on the same run, and the retry comes on the next run."""
    st = world["store"]
    world["inst"].inbox = [_item("pr-1", QUESTION, "2026-09-28T14:00:00.000Z"),
                           _item("pr-2", POSITIVE, "2026-09-28T14:30:00.000Z")]
    failed = []
    real = app_mod.classify

    def flaky(event):
        if event.email_id == "pr-1" and not failed:
            failed.append(event.email_id)
            raise RuntimeError("classifier timed out")
        return real(event)

    monkeypatch.setattr(app_mod, "classify", flaky)

    def process(event, now=None):
        return app_mod.process_event(event, deps=world["deps"], now=now, busy_blocks=[])

    first = P.run_once(world["inst"], st, now=ct(2026, 9, 28, 9, 35), campaign_filter=[CAMPAIGN], process=process)
    assert failed == ["pr-1"] and first["failed_pending"] == ["pr-1"]
    cards = _cards(st)
    assert len(cards) == 1
    newer_card = st.get(cards[0])
    before = st.get(KEY)

    second = P.run_once(world["inst"], st, now=ct(2026, 9, 28, 9, 40), campaign_filter=[CAMPAIGN], process=process)
    assert second["errors"] == 0 and second["failed_pending"] == []
    retried = [r for r in second["results"] if r.get("email_id") == "pr-1"]
    assert len(retried) == 1 and retried[0]["approval"] is False
    _unmoved(st.get(KEY), before)
    assert _cards(st) == cards and st.get(cards[0])["status"] == newer_card["status"] == "pending"
    assert _entry(st.get(KEY), "pr-1")["stale"] == OLDER
    assert len(_pushes(OLDER_TITLE % LEAD)) == 1


def test_an_older_reply_whose_record_failed_is_recorded_on_the_retry_with_one_push(world, monkeypatch):
    """A stale reply has nothing a partial save could keep: saving its copy
    would mark it processed with no push, so a failed write leaves it for
    the retry, which records it and pushes once."""
    st = world["store"]
    _reply(world, "f-2", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    real = A.save_lead_state
    fail = {"left": 1}

    def flaky(*a, **k):
        if fail["left"]:
            fail["left"] -= 1
            raise RuntimeError("store write failed")
        return real(*a, **k)

    monkeypatch.setattr(A, "save_lead_state", flaky)
    with pytest.raises(RuntimeError):
        _reply(world, "f-1", QUESTION, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert "f-1" not in st.get(KEY)["processed_email_ids"] and not _pushes(OLDER_TITLE % LEAD)
    again = _reply(world, "f-1", QUESTION, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 45))
    assert again["stale"] == OLDER and "f-1" in st.get(KEY)["processed_email_ids"]
    assert len(_pushes(OLDER_TITLE % LEAD)) == 1


def test_router_decides_older_only_by_email_times_and_never_for_an_opt_out(world):
    _reply(world, "r-2", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    state = LeadState.from_store(world["store"].get(KEY))
    at_nine = ct(2026, 9, 28, 9, 0)
    assert router.stale_reason(state, "neutral_question", at_nine, "email", email_id="r-1") == OLDER
    assert router.stale_reason(state, "ooo", at_nine, "email", email_id="r-1") == OLDER
    for label in router.OPT_OUT_LABELS:                                   # ruling 1: an opt-out takes effect
        assert router.stale_reason(state, label, at_nine, "email", email_id="r-1") is None
    assert router.stale_reason(state, "neutral_question", at_nine, "processing", email_id="r-1") is None
    assert router.stale_reason(state, "neutral_question", ct(2026, 9, 28, 9, 30), "email", email_id="r-3") is None
    assert router.stale_reason(state, "neutral_question", at_nine, "email", email_id="r-2") is None   # itself
    assert [e["email_id"] for e in router.newer_replies(world["store"].get(KEY), at_nine)] == ["r-2"]


# ============================================== the HELD push, from the facts
SLOT = "2026-10-01T15:00:00-05:00"        # Thu Oct 1 3:00pm CT
APPT = "appt-r5-held"


def _card(st, card_id, email_id, created, offered=None, status="pending", body=None, label="positive_question"):
    offered = list(offered if offered is not None else ["2026-09-30T13:00:00-05:00"])
    draft = Draft(subject=SUBJECT, body_text=body or "Hey Pat,\n\nDoes Wed 1:00pm CT work?\n\nLorenzo",
                  offered_slots=offered, label=label)
    expires = (created + timedelta(hours=48)).isoformat()
    card = Approval(token=A.make_token(card_id, KEY, A.draft_hash(draft), expires), state_key=KEY, lead_email=LEAD,
                      campaign_id=CAMPAIGN, email_id=email_id, eaccount=EACCOUNT, reply_to=LEAD, draft=draft,
                      status=status, created_at=created.isoformat(), expires_at=expires, label=label)
    st.set(A.APPROVAL_PREFIX + card_id, card.model_dump(mode="json"))
    st.set(A.APPROVAL_CONTEXT_PREFIX + card_id,
           {"email_id": email_id, "reply_at": created.isoformat(), "processed_before": [], "processed_count": 0,
            "tracks_history": True, "approved_at": None, "send_attempts": 0})
    A.reserve_slots(st, LEAD, offered, card_id, created)
    return card


def _inbound(email_id, label, sent, processed):
    return {"at": processed.isoformat(), "event": "inbound", "email_id": email_id, "label": label,
            "source": "webhook", "received_at": utc(sent)}


def _row(st, cards, history, booking=None):
    state = LeadState(lead_email=LEAD, campaign_id=CAMPAIGN, first_name="Pat", eaccount=EACCOUNT,
                      approvals=[c.token for c in cards], processed_email_ids=[e["email_id"] for e in history],
                      cadence={"booking": booking} if booking else {})
    row = dict(state.to_store(), history=list(history), status="draft_pending_approval")
    st.set(KEY, row)


def test_the_held_push_says_after_the_card_was_drafted_only_when_it_was_and_names_the_newer_card(world):
    st = world["store"]
    old = _card(st, "c1", "e-1", ct(2026, 9, 28, 9, 1))
    new = _card(st, "c2", "e-2", ct(2026, 9, 28, 9, 31), offered=["2026-09-30T14:00:00-05:00"])
    _row(st, [old, new], [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1)),
                          _inbound("e-2", "neutral_question", ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))])
    out = A.approve(old.token, world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"])
    assert out["status"] == "blocked" and out["lead_reply"] == {
        "reason": "newer_reply", "category": "neutral_question", "at": utc(ct(2026, 9, 28, 9, 30)), "email_id": "e-2"}
    msg = _pushes("HELD: the lead wrote again")[0]["message"]
    assert "The lead wrote again after the card was drafted (neutral_question, Mon Sep 28 9:30am CT)" in msg
    assert "Card c2 answers their newer reply and is waiting on you." in msg
    assert "Read the thread and any newer card for this lead, then Veto it or reply by hand." in msg
    problem = A._approval_row(st, "c1").draft.problems[-1]
    assert problem.startswith("the lead wrote again after this card was drafted (neutral_question")


def test_the_held_push_never_says_after_the_card_was_drafted_when_the_newer_reply_came_first(world):
    """The round-4 wording on the reviewer's Q2b: the card was drafted at
    12:45 for the older reply, the newer one had been sent at 12:37."""
    st = world["store"]
    card = _card(st, "c1", "e-1", ct(2026, 9, 28, 9, 45))
    _row(st, [card], [_inbound("e-2", "positive_interested", ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31)),
                      _inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 45))])
    A.approve(card.token, world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"])
    msg = _pushes("HELD: the lead wrote again")[0]["message"]
    assert "after the card was drafted" not in msg
    assert "The lead wrote again after the reply this card answers (positive_interested, Mon Sep 28 9:30am CT)" in msg
    assert "Their newer reply raised no card." in msg
    problem = A._approval_row(st, "c1").draft.problems[-1]
    assert "after this card was drafted" not in problem
    assert problem.startswith("the lead wrote again after the reply this card answers (positive_interested")
    held = A._approval_row(st, "c1")
    held.notify_result = {}                               # a card without the hold record is read from its problem
    assert A._held_for(held) == "newer_reply"


@pytest.mark.parametrize("keeps", [True, False], ids=["newer_card_names_the_call", "newer_card_other_times"])
def test_a_held_card_that_holds_the_call_is_not_told_to_veto_after_a_newer_reply(world, keeps):
    """c1 booked the call and was being sent when the lead wrote again
    (sending is not superseded), so the send-time check holds it."""
    st = world["store"]
    owner = _card(st, "c1", "e-1", ct(2026, 9, 28, 9, 1), offered=[SLOT], label="booking_confirmation",
                  body="Hey Pat,\n\nYou are locked in for Thu 3:00pm CT, invite on the way.\n\nLorenzo")
    newer = _card(st, "c2", "e-2", ct(2026, 9, 28, 9, 31), offered=[SLOT] if keeps else ["2026-10-02T13:00:00-05:00"])
    booking = {"slot": SLOT, "appointment_id": APPT, "awaiting_approval": True, "owner": "c1",
               "booked_at": ct(2026, 9, 28, 9, 1).isoformat()}
    _row(st, [owner, newer], [_inbound("e-1", "positive_interested", ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1)),
                              _inbound("e-2", "positive_question", ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))],
         booking=booking)
    out = A.approve(owner.token, world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"])
    assert out["status"] == "blocked" and out["lead_reply"]["reason"] == "newer_reply"
    msg = _pushes("HELD: the lead wrote again")[0]["message"]
    assert "Veto the card to cancel it" not in msg and "then Veto it" not in msg
    assert ("This card holds the call booked for Thu Oct 1 3:00pm CT (invite withheld), and a Veto cancels that "
            "call without telling the lead.") in msg
    assert ("Do not Veto it unless the call should go; if it should stand, confirm it with the lead and in GHL "
            "by hand.") in msg
    assert "Read the thread and any newer card for this lead before you do anything with it." in msg
    names_it = "Card c2, which answers their newer reply, names the same time, so the lead may be keeping the call."
    assert (names_it in msg) is keeps
    problem = A._approval_row(st, "c1").draft.problems[-1]
    assert "then Veto this card" not in problem
    assert ("before you Veto this card: it holds the call booked for Thu Oct 1 3:00pm CT, and a Veto cancels that "
            "call without telling the lead") in problem
    assert _booking(st, KEY)["owner"] == "c1"                              # the hold itself cancels nothing


def test_an_opt_out_hold_of_the_call_keeps_the_veto_note_unless_a_newer_reply_came_after(world):
    st = world["store"]
    owner = _card(st, "c1", "e-1", ct(2026, 9, 28, 9, 1), offered=[SLOT], label="booking_confirmation")
    booking = {"slot": SLOT, "appointment_id": APPT, "awaiting_approval": True, "owner": "c1",
               "booked_at": ct(2026, 9, 28, 9, 1).isoformat()}
    _row(st, [owner], [_inbound("e-1", "positive_interested", ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1))],
         booking=booking)
    why = {"reason": "opt_out", "category": "unsubscribe", "at": utc(ct(2026, 9, 28, 9, 30)), "email_id": "e-2"}
    assert A.hold_cards_for_lead_reply(st, [owner.token], why, now=ct(2026, 9, 28, 9, 31), lead=LEAD) == ["c1"]
    plain = _pushes("HELD: the lead asked to be removed")[-1]["message"]
    assert "This card holds the call booked for Thu Oct 1 3:00pm CT (invite withheld): Veto the card to cancel it." \
        in plain

    # the same hold for an opt-out the lead sent BEFORE their positive reply (ruling 1)
    st.set(A.APPROVAL_PREFIX + "c1", dict(st.get(A.APPROVAL_PREFIX + "c1"), status="pending", notify_result=None))
    why = dict(why, at=utc(ct(2026, 9, 28, 8, 30)), email_id="e-0",
               newer_reply={"email_id": "e-1", "label": "positive_interested", "at": utc(ct(2026, 9, 28, 9, 0))})
    assert A.hold_cards_for_lead_reply(st, [owner.token], why, now=ct(2026, 9, 28, 9, 41), lead=LEAD) == ["c1"]
    msg = _pushes("HELD: the lead asked to be removed")[-1]["message"]
    assert "Veto the card to cancel it" not in msg and "Veto it." not in msg
    assert ("This card holds the call booked for Thu Oct 1 3:00pm CT (invite withheld), and a Veto cancels that "
            "call without telling the lead: decide the call once you have read the thread.") in msg
    assert "They wrote again after it (positive_interested, Mon Sep 28 9:00am CT); this answer still stands." in msg
