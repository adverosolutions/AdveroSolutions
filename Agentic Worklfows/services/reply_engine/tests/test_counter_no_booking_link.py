"""Section 2 piece C: no counter-proposal carries a booking link, and none is
demanded of it (Lorenzo, 2026-09-23: the lead picks one of the offered times,
or sends their own, and Lorenzo sends the calendar invite).

Regression for the review of 2026-09-23: app.py built every counter draft with
booking_link=settings.BOOKING_URL and validated it against that link, so each
counter carried the problem "missing booking link", send_approved blocked it
and an approved counter template could never auto-send. These run the whole
path through app.process_event and approval.py in shadow (zero HTTP, no LLM).
"""
import types
from datetime import datetime

import pytz

from shared import settings
from services.reply_engine import app as app_mod
from services.reply_engine import approval as A
from services.reply_engine import booking
from services.reply_engine import cadence
from services.reply_engine.models import LeadState, ReplyEvent
# Fixtures and helpers only (no test_* names, so nothing is collected twice).
from services.reply_engine.tests.test_ct3_pipeline import (ILMI, SOPIO, _event, _replies, env,  # noqa: F401
                                                           fixture_item)

CT = pytz.timezone("America/Chicago")
MON_1405 = CT.localize(datetime(2026, 9, 21, 14, 5))
MON_1530 = CT.localize(datetime(2026, 9, 21, 15, 30))
MON_1600 = CT.localize(datetime(2026, 9, 21, 16, 0))
NO_ALTERNATIVES = "Could you send me a couple of times that work for you next week?"


def _links():
    return [l for l in (settings.BOOKING_URL, cadence.DEFAULT_BOOKING_URL) if l]


def _no_link(body):
    for link in _links():
        assert link not in body, body
    assert "grab a time" not in body and "Or if it's easier" not in body, body


def _ilmi(**over):
    item = dict(fixture_item(ILMI, "2026-09-21T19:00"))
    item.update(over)
    return ReplyEvent.from_poller_item(item)


def test_ilmi_counter_with_two_alternatives_has_no_problem_and_sends(env):
    """Ilmi's real "this Wednesday around 11:30 am": two alternatives, no
    link, no 'missing booking link', and Approve sends it in shadow."""
    res = app_mod.process_event(_ilmi(), deps=env["deps"], now=MON_1405)
    card = A.load(res["approval_token"], env["store"])
    assert card.draft.template_id == "booking.counter.outside_window_early"
    assert len(card.draft.offered_slots) == 2
    assert card.draft.body_text.startswith("Hey Ilmi,\n\nWed 11:30am CT is a touch early on my side. Could you do ")
    assert card.draft.body_text.endswith(" instead?\n\nLorenzo")
    _no_link(card.draft.body_text)
    assert card.draft.booking_link is None
    assert card.draft.problems == []
    assert "booking_url" not in booking.counter_bindings(
        booking.BookingMatch(slot=None, status=booking.OUTSIDE_WINDOW, proposed=CT.localize(datetime(2026, 9, 23, 11, 30)),
                             counter_slots=[CT.localize(datetime(2026, 9, 23, 13, 0))]), None)
    out = A.send_approved(card, env["deps"].instantly, store=env["store"], now=MON_1405)
    assert out["ok"] is True, out
    assert A.load(res["approval_token"], env["store"]).status == "sent"
    sent = _replies()
    assert len(sent) == 1
    _no_link(str(sent[0]["payload"]))


def test_an_edited_counter_is_not_asked_for_the_link_back(env):
    """approval.edit re-validates against the draft's stored booking link:
    with none stored, the unchanged counter body saves clean."""
    res = app_mod.process_event(_ilmi(), deps=env["deps"], now=MON_1405)
    card = A.load(res["approval_token"], env["store"])
    out = A.edit(res["approval_token"], card.draft.body_text, store=env["store"], now=MON_1405)
    assert out["ok"] is True and out["problems"] == [], out


def test_an_approved_slot_taken_counter_auto_sends_without_a_link(env):
    """A non-overridable counter (the time is held for another lead's card):
    the approved booking.counter.slot_taken template auto-sends."""
    env["tpl"].approve_ids("booking.counter.slot_taken")
    env["store"].set(A.OFFERED_KEY, [{"slot": "2026-09-22T14:00:00-05:00", "lead": "alice@x.com",
                                      "at": MON_1530.isoformat(), "approval": "a1"}])
    ev = _event(SOPIO, "2026-09-21T14:42", reply_text="Tuesday at 2pm works for me.", email_id="taken-1")
    # A reply of ours already reached this lead: only then may a counter
    # auto-send (approval.draft_only, section 4).
    lead = LeadState.from_store(env["store"].get(ev.state_key), ev)
    lead.history.append({"at": "2026-09-20T15:00:00-05:00", "event": "reply_sent", "approval": "earlier"})
    env["store"].set(ev.state_key, lead.model_dump(mode="json"))
    res = app_mod.process_event(ev, deps=env["deps"], now=MON_1530, busy_blocks=[])
    card = A.load(res["approval_token"], env["store"])
    assert card.draft.template_id == "booking.counter.slot_taken"
    assert "Tue 2:00pm CT just got taken on my calendar. Could you do " in card.draft.body_text
    _no_link(card.draft.body_text)
    assert card.draft.problems == [] and card.draft.booking_link is None
    assert res["auto_send"]["allowed"] is True, res["auto_send"]
    assert res["auto_send"]["status"] in ("sent", "ok"), res["auto_send"]
    assert len(_replies()) == 1


def test_a_counter_with_no_alternatives_asks_for_times_and_sends(env, monkeypatch):
    """Nothing free to counter with: the new ask, no link, no problem."""
    monkeypatch.setattr(app_mod, "_bookable_grid", lambda *a, **k: [])
    res = app_mod.process_event(_ilmi(), deps=env["deps"], now=MON_1405)
    card = A.load(res["approval_token"], env["store"])
    assert card.draft.body_text == ("Hey Ilmi,\n\nWed 11:30am CT is a touch early on my side. %s\n\nLorenzo"
                                    % NO_ALTERNATIVES)
    assert card.draft.offered_slots == []
    assert card.draft.booking_link is None and card.draft.problems == []
    out = A.send_approved(card, env["deps"].instantly, store=env["store"], now=MON_1405)
    assert out["ok"] is True, out
    assert len(_replies()) == 1


def test_slot_already_taken_carries_only_its_own_problem(env, monkeypatch):
    """booking.slot_already_taken (book() finds the slot gone): the draft
    stores no booking link, so its only problem is slot_already_taken (it
    stays a card by design) and an edit does not demand the link back."""
    monkeypatch.setattr(booking, "verify_slot", lambda *a, **k: (False, booking.SLOT_ALREADY_TAKEN))
    ev = _event(SOPIO, "2026-09-21T14:42", reply_text="Tuesday at 2pm works for me.", email_id="gone-1")
    res = app_mod.process_event(ev, deps=env["deps"], now=MON_1530, busy_blocks=[])
    card = A.load(res["approval_token"], env["store"])
    assert card.draft.template_id == booking.SLOT_ALREADY_TAKEN_ID
    assert card.draft.body_text.startswith("Hey Sopio,\n\nTue 2:00pm CT just got taken on my calendar. Could you do ")
    _no_link(card.draft.body_text)
    assert card.draft.booking_link is None
    assert card.draft.problems == [booking.SLOT_ALREADY_TAKEN]
    out = A.edit(res["approval_token"], card.draft.body_text, store=env["store"], now=MON_1530)
    assert out["ok"] is True and out["problems"] == [booking.SLOT_ALREADY_TAKEN], out


def test_slot_already_taken_with_no_alternatives_uses_the_new_ask():
    state = types.SimpleNamespace(first_name="Dana", company="Dana Cleaning", niche="cleaning", offer="reactivation",
                                  campaign_key="cleaning_reactivation", campaign_id=None, lead_email="dana@example.invalid",
                                  ghl_contact_id=None, last_subject="Quick question", subject=None,
                                  thread_subject=None, cadence={})
    start = CT.localize(datetime(2026, 9, 22, 13, 45))
    res = booking._unbookable_result(state, start, booking.SLOT_ALREADY_TAKEN, MON_1530, free_slots=[])
    assert res.draft.body_text == ("Hey Dana,\n\nTue 1:45pm CT just got taken on my calendar. %s\n\nLorenzo"
                                   % NO_ALTERNATIVES)
    assert res.draft.booking_link is None and res.problems == [booking.SLOT_ALREADY_TAKEN]


def test_an_edited_booking_confirmation_is_not_asked_for_a_link(env):
    """The "Locked in ..." confirmation carries no booking link, so its draft
    stores none and an edit of the card saves without 'missing booking link'."""
    res = app_mod.process_event(_event(SOPIO, "2026-09-21T17:37"), deps=env["deps"], now=MON_1600)
    card = A.load(res["approval_token"], env["store"])
    assert card.draft.label == "booking_confirmation"
    assert card.draft.body_text.startswith("Hey Sopio,\n\nLocked in ")
    _no_link(card.draft.body_text)
    assert card.draft.booking_link is None
    assert "missing booking link" not in card.draft.problems
    out = A.edit(res["approval_token"], card.draft.body_text, store=env["store"], now=MON_1600,
                 booking_choice="keep")
    assert out["ok"] is True, out
    assert "missing booking link" not in out["problems"] and out["problems"] == [], out
    assert A.load(out["token"], env["store"]).draft.booking_link is None
