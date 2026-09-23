"""S-rest round 6, defect 1: an older reply that proposes a call time.

The lead's older reply ("Thursday at 3pm works for me") is processed after
their newer one (a pricing question), whose card offers two other times.
Round 5 recorded the older reply only, booked nothing, and pushed that the
newer card "can be approved and sent as usual", without the time. Now:

* the push names the proposed time in CT and says nothing was booked for it;
* the open card that names other times carries a problem saying so
  (app._mark_time_conflicts): a send refuses it with that reason, the approve
  page states it (at night too, instead of queueing it), the queue does not
  send it, and an Edit clears it like a copy problem;
* no card is marked when one of its times is the proposed one, or when a
  newer reply of the lead's proposed a time itself (their newer word on the
  time, recorded as names_time on its history entry);
* a lead whose no is in force on the row (the reviewer's three-reply
  sequence, an older opt-out processed in the middle) is told what the HELD
  push tells: that answer stands, read the whole thread, do not reply. Never
  "reply by hand", and never that the newer reply set the row.

Also here: an older automatic reply's push is low priority; a card at
sending is worded from its send claim; the retry page states retry()'s
refusal inside the lease and points at Mark sent; the settlement note on a
new card is a status-guarded write; the approve page no longer shows the
recipient-hold text for a hold on the lead's own reply.

Every lead is an example.com address; every client is an in-process fake.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from shared import notify

from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine.models import LeadState

from test_srest_r4_ingest_order import (  # noqa: F401 - the round-4 world, fakes and helpers
    KEY, LEAD, POSITIVE, REMOVE, _cards, _entry, _reply, ct, utc, world,
)
from test_srest_r5_older_reply import (
    OLDER, OLDER_TITLE, OOO, OOO_SUBJECT, QUESTION, _card, _id, _inbound, _pushes, _row, _unmoved,
)

THURSDAY = "Thursday at 3pm works for me."
THU_ISO = "2026-10-01T15:00:00-05:00"
THU = "Thu Oct 1 3:00pm CT"
# The two times the pricing answer offers on Monday Sep 28 (fallback grid).
MON_2PM, TUE_230PM = "2026-09-28T14:00:00-05:00", "2026-09-29T14:30:00-05:00"
CARD_TIMES = "Mon Sep 28 2:00pm CT, Tue Sep 29 2:30pm CT"
HELD_ADVICE = "Read the whole thread in Instantly before anything else goes to them. Do not reply to them: " \
              "they asked not to be emailed."


def _newer_question(world, email_id="t6-2", processed=ct(2026, 9, 28, 9, 31)):
    """The lead's newer reply, a pricing question, processed first: its card
    offers Monday 2:00pm and Tuesday 2:30pm."""
    newer = _reply(world, email_id, POSITIVE, ct(2026, 9, 28, 9, 30), processed)
    assert newer["label"] == "positive_question" and newer["approval_token"]
    card = A.load(newer["approval_token"], world["store"])
    assert card.draft.offered_slots == [MON_2PM, TUE_230PM] and card.draft.problems == []
    return newer


def _older_time(world, text=THURSDAY, processed=ct(2026, 9, 28, 9, 40), email_id="t6-1"):
    """The lead's older reply, sent at 09:00, processed after the newer one."""
    return _reply(world, email_id, text, ct(2026, 9, 28, 9, 0), processed)


def _time_problems(card):
    return [p for p in card.draft.problems if p.startswith(app_mod._TIME_CONFLICT_PREFIX)]


# =========================================== the reviewer's sequence (r5a A4)
def test_an_older_reply_that_proposes_a_time_names_it_and_holds_the_card_that_names_other_times(world):
    st = world["store"]
    newer = _newer_question(world)
    card_b = _id(newer["approval_token"])
    before = st.get(KEY)
    pushes = len(notify.sent_in_test)

    older = _older_time(world)
    assert older["stale"] == OLDER and older["approval_token"] is None and older["booking"] is None
    assert older["time_asked"] == {"slot": THU_ISO} and older["cards_marked"] == [card_b]
    row = st.get(KEY)
    _unmoved(row, before)                                                  # nothing booked, nothing moved
    assert not (row.get("cadence") or {}).get("booking")
    assert _entry(row, "t6-1")["names_time"] is True and "names_time" not in _entry(row, "t6-2")

    card = A._approval_row(st, card_b)
    assert card.status == "pending"
    problem = _time_problems(card)
    assert len(problem) == 1 and card.draft.problems == problem
    assert ("the lead's older reply (sent Mon Sep 28 9:00am CT, read only after this card was drafted) proposed a "
            "call at %s, and this card names other times (%s); nothing was booked for it." % (THU, CARD_TIMES)
            ) in problem[0]

    new = notify.sent_in_test[pushes:]
    assert [n["title"] for n in new] == [OLDER_TITLE % LEAD] and new[0]["priority"] == "high"
    msg = new[0]["message"]
    assert "It proposed a call at %s; nothing was booked for it." % THU in msg
    assert ("Card %s, which answers their newer reply, names other times (%s), so it is held until you Edit it: "
            "approving it as it is is refused." % (card_b, CARD_TIMES)) in msg
    assert "as usual" not in msg and "stay as the newer reply left them" not in msg
    assert ("Edit card %s: answer the time they proposed (and book that call in GHL if it stands), or keep its "
            "times. The edit clears the hold." % card_b) in msg
    assert u"—" not in msg and u"—" not in problem[0]

    # approving it as it is: refused, with the reason, and nothing goes out
    out = A.approve(newer["approval_token"], world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"])
    assert out["ok"] is False and out["status"] == "blocked" and out["problems"] == problem
    assert world["inst"].sent == [] and A._approval_row(st, card_b).status == "blocked"

    # the same reply delivered again marks nothing twice and pushes nothing more
    again = _older_time(world, processed=ct(2026, 9, 28, 9, 45))
    assert again["skipped"] == "duplicate" and A._approval_row(st, card_b).draft.problems == problem


def test_the_marked_card_is_refused_at_night_its_pages_state_why_and_an_edit_clears_it(world):
    st = world["store"]
    client = TestClient(app_mod.app)
    newer = _newer_question(world)
    token = newer["approval_token"]
    _older_time(world)
    world["clock"]["now"] = ct(2026, 9, 28, 20, 0)                        # outside the sending window

    page = client.get("/approve/%s" % token)
    assert page.status_code == 400 and "This reply cannot go out as it is:" in page.text
    assert "proposed a call at %s" % THU in page.text and "/edit/%s" % token in page.text
    assert "<form" not in page.text                                        # no Send button that can only fail
    page = client.post("/approve/%s" % token)
    assert page.status_code == 400 and "proposed a call at %s" % THU in page.text and "Queued" not in page.text
    card = A.load(token, st)
    assert card.status == "pending" and _time_problems(card)             # not queued with its problem

    form = client.get("/edit/%s" % token)
    assert form.status_code == 200 and "Why it cannot go out as it is:" in form.text
    assert "proposed a call at %s" % THU in form.text
    body = ("Hey Pat,\n\nThursday at 3:00pm CT works for us. If that changes, grab another time here: %s\n\nLorenzo"
            % card.draft.booking_link)
    saved = client.post("/edit/%s" % token, data={"body": body})
    assert saved.status_code == 200 and "Saved and approved" in saved.text and "approved_queued" in saved.text
    edited = A._approval_row(st, _id(token))
    assert edited.status == "approved_queued" and edited.draft.problems == []   # the edit cleared it

    A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 29, 7, 5), ghl=world["ghl"])
    assert A._approval_row(st, _id(token)).status == "sent"


def test_a_queued_card_that_names_other_times_is_held_and_the_queue_does_not_send_it(world):
    st = world["store"]
    newer = _newer_question(world)
    card_b = _id(newer["approval_token"])
    queued = A.approve(newer["approval_token"], world["inst"], store=st, now=ct(2026, 9, 28, 20, 0), ghl=world["ghl"])
    assert queued["status"] == "approved_queued"
    pushes = len(notify.sent_in_test)

    older = _older_time(world, processed=ct(2026, 9, 28, 20, 5))
    assert older["cards_marked"] == [card_b]
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert ("Card %s, which answers their newer reply, was approved, but it names other times (%s), so it is held "
            "until you Edit it: the queue will not send it as it is." % (card_b, CARD_TIMES)) in msg
    assert "goes out when the sending window opens" not in msg

    A.flush_queued(world["inst"], store=st, now=ct(2026, 9, 29, 7, 5), ghl=world["ghl"])
    card = A._approval_row(st, card_b)
    assert card.status == "blocked" and _time_problems(card) and world["inst"].sent == []


def test_an_older_reply_whose_record_failed_marks_the_card_once_and_pushes_once_on_the_retry(world, monkeypatch):
    """The mark is written before the row: a write that fails leaves the
    reply to its retry (nothing recorded, no push), and the retry marks
    nothing twice."""
    st = world["store"]
    newer = _newer_question(world)
    card_b = _id(newer["approval_token"])
    real = A.save_lead_state
    fail = {"left": 1}

    def flaky(*a, **k):
        if fail["left"]:
            fail["left"] -= 1
            raise RuntimeError("store write failed")
        return real(*a, **k)

    monkeypatch.setattr(A, "save_lead_state", flaky)
    with pytest.raises(RuntimeError):
        _older_time(world)
    assert "t6-1" not in st.get(KEY)["processed_email_ids"] and not _pushes(OLDER_TITLE % LEAD)
    assert len(_time_problems(A._approval_row(st, card_b))) == 1
    again = _older_time(world, processed=ct(2026, 9, 28, 9, 45))
    assert again["stale"] == OLDER and again["cards_marked"] == [card_b]
    assert len(_time_problems(A._approval_row(st, card_b))) == 1 and len(_pushes(OLDER_TITLE % LEAD)) == 1


def test_a_marked_card_that_holds_the_call_says_its_edit_page_asks_keep_or_release(world):
    """Wednesday 1pm was booked by the lead's first reply; their pricing
    question took the call over on its own card (it restates Wednesday);
    their "Thursday at 3pm would be better", sent between the two, is read
    last."""
    st = world["store"]
    first = _reply(world, "k6-0", "Wednesday at 1pm works for me.", ct(2026, 9, 28, 8, 30), ct(2026, 9, 28, 8, 31))
    assert first["booking"]["slot"] == "2026-09-30T13:00:00-05:00"
    newer = _reply(world, "k6-2", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    card_b = _id(newer["approval_token"])
    assert newer["booking_handoff"]["action"] == "transferred"
    assert A.owns_booking(A._approval_row(st, card_b), LeadState.from_store(st.get(KEY)))
    pushes = len(notify.sent_in_test)

    older = _older_time(world, text="Actually, Thursday at 3pm would be better.")
    assert older["stale"] == OLDER and older["cards_marked"] == [card_b]
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert ("Card %s, which answers their newer reply, names other times (Wed Sep 30 1:00pm CT), so it is held until "
            "you Edit it: approving it as it is is refused. It holds the call booked for Wed Sep 30 1:00pm CT: its "
            "Edit page asks whether to keep that call or release it." % card_b) in msg
    booking = dict((st.get(KEY).get("cadence") or {}).get("booking") or {})
    out = A.approve(newer["approval_token"], world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"])
    assert out["ok"] is False and out["problems"] == _time_problems(A._approval_row(st, card_b))
    assert (st.get(KEY).get("cadence") or {}).get("booking") == booking     # not confirmed, not cancelled


def test_an_older_reply_proposing_a_time_the_card_offers_marks_nothing(world):
    st = world["store"]
    newer = _newer_question(world)
    card_b = _id(newer["approval_token"])
    pushes = len(notify.sent_in_test)
    older = _older_time(world, text="Tuesday at 2:30pm works for me.")
    assert older["time_asked"] == {"slot": TUE_230PM} and older["cards_marked"] == []
    assert A._approval_row(st, card_b).draft.problems == []
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert "It proposed a call at Tue Sep 29 2:30pm CT; nothing was booked for it." in msg
    assert "Card %s, which answers their newer reply, offers that time too; it is still open." % card_b in msg
    assert "as usual" not in msg


def test_a_newer_reply_that_proposed_its_own_time_keeps_its_card_and_call(world):
    """The lead first wrote "Thursday at 3pm", then "Wednesday at 1pm works
    better", and the newer one was processed first and booked Wednesday.
    Their newer word on the time stands: nothing is marked, and the card
    confirms Wednesday when it goes out."""
    st = world["store"]
    newer = _reply(world, "t6-2", "Wednesday at 1pm works better for me.", ct(2026, 9, 28, 9, 30),
                   ct(2026, 9, 28, 9, 31))
    card_b = _id(newer["approval_token"])
    assert newer["booking"] and newer["booking"]["slot"] == "2026-09-30T13:00:00-05:00"
    assert _entry(st.get(KEY), "t6-2")["names_time"] is True
    pushes = len(notify.sent_in_test)

    older = _older_time(world)
    assert older["time_asked"] == {"slot": THU_ISO} and older["cards_marked"] == []
    assert A._approval_row(st, card_b).draft.problems == []
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert "It proposed a call at %s; nothing was booked for it." % THU in msg
    assert "A newer reply of theirs proposed a time of its own, and their cards follow that one." in msg
    assert ("Card %s, which answers their newer reply, is still open and follows the time their newer reply "
            "proposed, and sending it confirms the call booked for Wed Sep 30 1:00pm CT." % card_b) in msg
    assert "as usual" not in msg and "Edit card" not in msg

    sent = A.approve(newer["approval_token"], world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"])
    assert sent["ok"] is True and sent["status"] == "sent"
    booking = (st.get(KEY).get("cadence") or {}).get("booking") or {}
    assert booking["slot"] == "2026-09-30T13:00:00-05:00" and booking["confirmed_by"] == card_b


# ===================== the reviewer's three replies, an older no in the middle
@pytest.mark.parametrize("older_text", [
    "Also, do you work with firms outside Texas?",
    "Also, would Thursday at 3pm work instead?",
], ids=["question", "proposes_a_time"])
def test_an_older_reply_after_a_late_opt_out_is_told_as_the_held_push_tells_it(world, older_text):
    """N (9:30, a question) is processed first; O (9:00, "remove me") late,
    and applied; M (9:15) last, older than N."""
    st = world["store"]
    newest = _reply(world, "c6-n", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    card_n = _id(newest["approval_token"])
    no = _reply(world, "c6-o", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    assert no["label"] == "unsubscribe" and no["cards_held"] == [card_n]
    held = _pushes("HELD: the lead asked to be removed")[-1]["message"]
    assert held.endswith("Do not reply to them: they asked not to be emailed.")
    before = st.get(KEY)
    pushes = len(notify.sent_in_test)

    middle = _reply(world, "c6-m", older_text, ct(2026, 9, 28, 9, 15), ct(2026, 9, 28, 9, 50))
    assert middle["stale"] == OLDER and middle["cards_marked"] == []
    row = st.get(KEY)
    assert row["status"] == before["status"] == "blocklisted"
    assert row["classification"] == before["classification"] and row["approvals"] == before["approvals"]
    assert A._approval_row(st, card_n).status == "blocked"

    new = notify.sent_in_test[pushes:]
    assert [n["title"] for n in new] == [OLDER_TITLE % LEAD]
    msg = new[0]["message"]
    assert ("so nothing moved: the lead asked to be removed (unsubscribe, sent Mon Sep 28 9:00am CT), that answer "
            "still stands, and their status stays blocklisted.") in msg
    assert "Card %s, which answers their newer reply, stays blocked." % card_n in msg
    assert msg.endswith(HELD_ADVICE) and HELD_ADVICE.split(". ")[-1] in held
    assert "by hand" not in msg and "newer reply left" not in msg and "as usual" not in msg
    assert "Edit" not in msg
    if "Thursday" in older_text:
        assert middle["time_asked"] == {"slot": THU_ISO}
        assert "It proposed a call at %s; nothing was booked for it." % THU in msg


def test_no_card_is_marked_for_a_time_while_the_leads_no_is_in_force(world, monkeypatch):
    """The late no's hold did not reach the newer card (the store refused
    it), so that card is still open on a blocklisted row: the older reply's
    time marks nothing (the send holds the card anyway), and the push says
    so without any Edit or reply-by-hand advice."""
    st = world["store"]
    newest = _reply(world, "f6-n", POSITIVE, ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))
    card_n = _id(newest["approval_token"])

    def refused(*a, **k):
        raise RuntimeError("store refused the hold")

    real = A.hold_cards_for_lead_reply
    monkeypatch.setattr(A, "hold_cards_for_lead_reply", refused)
    no = _reply(world, "f6-o", REMOVE, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    monkeypatch.setattr(A, "hold_cards_for_lead_reply", real)
    assert no["cards_held"] == [] and A._approval_row(st, card_n).status == "pending"
    pushes = len(notify.sent_in_test)

    middle = _reply(world, "f6-m", THURSDAY, ct(2026, 9, 28, 9, 15), ct(2026, 9, 28, 9, 50))
    assert middle["stale"] == OLDER and middle["time_asked"] == {"slot": THU_ISO} and middle["cards_marked"] == []
    assert A._approval_row(st, card_n).draft.problems == []
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert ("the lead asked to be removed (unsubscribe, sent Mon Sep 28 9:00am CT), that answer still stands, and "
            "their status stays blocklisted.") in msg
    assert ("Card %s, which answers their newer reply, is still open, but no reply goes out to them while that answer "
            "stands: the send holds it." % card_n) in msg
    assert msg.endswith(HELD_ADVICE) and "Edit" not in msg and "by hand" not in msg
    out = A.approve(newest["approval_token"], world["inst"], store=st, now=ct(2026, 9, 28, 10, 0), ghl=world["ghl"])
    assert out["ok"] is False and out["lead_reply"]["reason"] == "opt_out" and world["inst"].sent == []


@pytest.mark.parametrize("text, window, marked", [
    ("I could do 1pm-3pm Central any day this week.", "between 1:00pm and 3:00pm CT", False),
    ("Mornings work best, 9am-11am CT.", "between 9:00am and 11:00am CT", True),
], ids=["window_holds_an_offered_time", "window_outside_the_offered_times"])
def test_an_older_reply_that_gives_a_range_of_hours(world, text, window, marked):
    st = world["store"]
    newer = _newer_question(world)
    card_b = _id(newer["approval_token"])
    pushes = len(notify.sent_in_test)
    older = _older_time(world, text=text)
    assert older["stale"] == OLDER and "window" in older["time_asked"]
    assert older["cards_marked"] == ([card_b] if marked else [])
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert "It proposed a call %s; nothing was booked for it." % window in msg
    problems = _time_problems(A._approval_row(st, card_b))
    if marked:
        assert len(problems) == 1 and "proposed a call %s, and this card names other times" % window in problems[0]
        assert "so it is held until you Edit it" in msg
    else:
        assert problems == [] and "offers that time too; it is still open." in msg


# ========================================================= the smaller items
def test_an_older_automatic_reply_is_pushed_at_low_priority(world):
    _newer_question(world)
    pushes = len(notify.sent_in_test)
    ooo = _reply(world, "o6-1", OOO, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40), subject=OOO_SUBJECT)
    assert ooo["label"] == "ooo" and ooo["stale"] == OLDER and ooo["time_asked"] is None
    new = notify.sent_in_test[pushes:]
    assert len(new) == 1 and new[0]["priority"] == "low"
    assert new[0]["message"].endswith("It is an automatic reply, so nothing needs doing.")


def _sending(st, card_id, started):
    """The stored card as its send left it: sending, with its own claim."""
    raw = st.get(A.APPROVAL_PREFIX + card_id)
    st.set(A.APPROVAL_PREFIX + card_id, dict(raw, status="sending", send_attempt="att-6"))
    st.set(A.SEND_CLAIM_PREFIX + card_id, {"attempt": "att-6", "at": started.isoformat()})


@pytest.mark.parametrize("started, words", [
    (ct(2026, 9, 28, 9, 38), "is being sent (its send started Mon Sep 28 9:38am CT)."),
    (ct(2026, 9, 28, 9, 20), "has been stuck at sending since Mon Sep 28 9:20am CT: its send started and never "
                             "finished, so it may or may not have gone out"),
], ids=["inside_the_lease", "past_the_lease"])
def test_a_card_at_sending_is_worded_from_its_send_claim(world, started, words):
    st = world["store"]
    newer = _newer_question(world)
    card_b = _id(newer["approval_token"])
    _sending(st, card_b, started)
    pushes = len(notify.sent_in_test)
    _reply(world, "s6-1", QUESTION, ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 40))
    msg = notify.sent_in_test[pushes:][0]["message"]
    assert ("Card %s, which answers their newer reply, %s" % (card_b, words)) in msg
    assert ("is being sent" in msg) is (started == ct(2026, 9, 28, 9, 38))


def test_the_retry_page_states_the_lease_refusal_and_points_at_mark_sent(world):
    st = world["store"]
    client = TestClient(app_mod.app)
    newer = _newer_question(world)
    token, card_b = newer["approval_token"], _id(newer["approval_token"])
    _sending(st, card_b, ct(2026, 9, 28, 9, 50))

    world["clock"]["now"] = ct(2026, 9, 28, 9, 55)                        # inside the 10-minute lease
    page = client.get("/retry/%s" % token)
    assert page.status_code == 400 and "Retry not available yet" in page.text
    assert "This card&#x27;s send started Mon Sep 28 9:50am CT and may still be running" in page.text
    assert "Retry is available from Mon Sep 28 10:00am CT" in page.text and "press Mark sent instead" in page.text
    assert "<form" not in page.text

    world["clock"]["now"] = ct(2026, 9, 28, 10, 5)                        # past it: the form, and Mark sent
    page = client.get("/retry/%s" % token)
    assert page.status_code == 200 and "<form method='post' action='/retry/%s'>" % token in page.text
    assert "If the reply went out, press <a href='/mark-sent/%s'>Mark sent</a> instead." % token in page.text

    st.set(A.APPROVAL_PREFIX + card_b, dict(st.get(A.APPROVAL_PREFIX + card_b), status="stale_slots"))
    page = client.get("/retry/%s" % token)
    assert page.status_code == 200 and "Mark sent" not in page.text        # its reply never went out


def test_the_settlement_note_is_never_written_over_a_card_that_moved_on(world, monkeypatch):
    """Round 5 read the card, then wrote it back whole: an approval that
    moved it to sending in between was undone (pending again)."""
    st = world["store"]
    newer = _newer_question(world)
    card_b = _id(newer["approval_token"])
    card = A.load(newer["approval_token"], st)
    handoff = {"action": "release_pending", "slot": THU_ISO}
    real = A._transition

    def approved_meanwhile(store, approval_id, allowed, fn):
        store.set(A.APPROVAL_PREFIX + approval_id, dict(store.get(A.APPROVAL_PREFIX + approval_id), status="sending"))
        return real(store, approval_id, allowed, fn)

    monkeypatch.setattr(A, "_transition", approved_meanwhile)
    rationale = card.draft.rationale
    assert app_mod._note_settlement_outcome(st, card, handoff) is False
    stored = st.get(A.APPROVAL_PREFIX + card_b)
    assert stored["status"] == "sending" and "UPDATE" not in stored["draft"]["rationale"]
    assert card.draft.rationale == rationale

    monkeypatch.setattr(A, "_transition", real)
    st.set(A.APPROVAL_PREFIX + card_b, dict(stored, status="pending"))
    assert app_mod._note_settlement_outcome(st, card, handoff) is True
    stored = st.get(A.APPROVAL_PREFIX + card_b)
    assert stored["status"] == "pending"
    assert stored["draft"]["rationale"].endswith("UPDATE: GHL refused to cancel the call for %s. It is still on the "
                                                 "calendar with its reminders held, and the cancel is being retried"
                                                 % THU_ISO)
    assert card.draft.rationale == stored["draft"]["rationale"]


def test_the_approve_page_states_a_hold_for_the_leads_reply_not_a_recipient_hold(world):
    """A hold on the lead's own reply returns held too; the page used to show
    the recipient re-read text ("retries on its own"), which is not what
    happened."""
    st = world["store"]
    client = TestClient(app_mod.app)
    old = _card(st, "h6", "e-1", ct(2026, 9, 28, 9, 1))
    _row(st, [old], [_inbound("e-1", "positive_question", ct(2026, 9, 28, 9, 0), ct(2026, 9, 28, 9, 1)),
                     _inbound("e-2", "neutral_question", ct(2026, 9, 28, 9, 30), ct(2026, 9, 28, 9, 31))])
    page = client.post("/approve/%s" % old.token)
    assert page.status_code == 400
    assert "the lead wrote again after this card was drafted (neutral_question" in page.text
    assert "retries on its own" not in page.text and "recipient" not in page.text
    assert A._approval_row(st, "h6").status == "blocked"
    again = client.get("/approve/%s" % old.token)                         # a second look states it too
    assert again.status_code == 400 and "This approval is blocked: the lead wrote again" in again.text
    tap = client.post("/approve/%s" % old.token)                          # and a second tap
    assert tap.status_code == 400 and "This approval is blocked: the lead wrote again" in tap.text
    assert "already blocked" not in tap.text and "by hand from the Instantly inbox" not in tap.text
