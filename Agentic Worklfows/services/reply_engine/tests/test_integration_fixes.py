"""Phase 1 integration fixes: the cross-cutting defects that spanned two
components and so belonged to neither of them.

Each test here pins a behaviour that was WRONG before integration, and would
silently go back to being wrong if the fix were reverted. now = 2026-09-21T21:10-05:00.
"""
import json
from pathlib import Path

import httpx
import pytest

from shared import slots as slot_rules
from shared.ghl import GHL
from shared.instantly import Instantly

from services.reply_engine import app as app_mod
from services.reply_engine import approval as approval_mod
from services.reply_engine import booking, draft as draft_mod
from services.reply_engine.cadence import LeadState

NOW = slot_rules.parse_iso("2026-09-21T21:10:00-05:00")
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def sopio():
    return LeadState(lead_email="sopiosvanishvili@taxfoaccounting.com",
                     campaign_id="f00c5e28-fdc4-4d84-a7e6-dfba9695f35d",
                     status="positive_question", first_name="Sopio", company="Taxfo Accounting",
                     eaccount="lorenzov@theadvero.com",
                     last_email_id="01a0c50b-6021-793c-a3b9-81506c6a291b",
                     last_subject="Re: Sopio, question",
                     ghl_contact_id="iDhesF6A9rhdDajGZuYw", ghl_opportunity_id="hStqQMLQ5eSRVnqxnSMq")


def recording_ghl():
    """A GHL client with a token whose every request is captured, never sent."""
    seen = []

    def handler(request):
        seen.append({"method": request.method, "url": str(request.url),
                     "body": json.loads(request.content.decode("utf-8")) if request.content else None})
        return httpx.Response(200, json={"id": "appt-live-1", "appointment": {"id": "appt-live-1"}})

    client = GHL(token="test-token", transport=httpx.MockTransport(handler))
    return client, seen


# ------------------------------------------------- the invite is not sent early
def test_booking_never_lets_ghl_email_the_prospect_before_approval(tmp_env, live_mode):
    """booking.book() runs at CLASSIFICATION time, before Lorenzo sees the card.

    GHL emails the contact a calendar invite on create unless toNotify is false,
    so the prospect used to receive an invite for a call Lorenzo had not agreed
    to - and if he vetoed, cancel_booking had to un-say it.
    """
    client, seen = recording_ghl()
    slot = "2026-09-24T15:00:00-05:00"
    booking.book(sopio(), slot, client, None, now=NOW, free_slots=[slot])
    creates = [r for r in seen if r["method"] == "POST" and "appointments" in r["url"]]
    assert creates, "no appointment was created"
    assert creates[0]["body"]["toNotify"] is False


def test_approving_the_confirmation_releases_the_invite(tmp_env, live_mode):
    """The confirmation body says "invite on the way", so approving it has to
    make that true: the appointment is flipped with toNotify=True.

    live_mode + MockTransport: the request body is the thing under test, and in
    shadow guard_write intercepts before any request is built."""
    state = sopio()
    state.cadence = {"booking": {"appointment_id": "appt-live-1", "slot": "2026-09-24T15:00:00-05:00"}}
    client, seen = recording_ghl()
    out = approval_mod.release_booking_invite(state, client, NOW)
    assert out["released"] is True and out["appointment_id"] == "appt-live-1"
    puts = [r for r in seen if r["method"] == "PUT"]
    assert puts and puts[0]["body"]["toNotify"] is True


def test_a_shadow_booking_never_tries_to_release_an_invite(tmp_env, shadow_mode):
    """A shadow appointment id names no real GHL event, so there is nothing to
    notify anybody about."""
    state = sopio()
    state.cadence = {"booking": {"appointment_id": "shadow-appt-deadbeef"}}
    client, seen = recording_ghl()
    assert approval_mod.release_booking_invite(state, client, NOW) is None
    assert seen == []


# ------------------------------------------------------ Lorenzo's own slot rule
def test_book_refuses_a_morning_even_when_the_grid_says_it_is_free(tmp_env, shadow_mode):
    """Ilmi's real "this Wednesday around 11:30 am" parses fine and breaks the
    no-mornings rule. verify_slot only answers availability, so without the
    compliance gate a direct book() call would write 11:30 to the calendar."""
    morning = "2026-09-23T11:30:00-05:00"
    res = booking.book(sopio(), morning, None, None, now=NOW, free_slots=[morning])
    assert booking.OUTSIDE_WINDOW in res.draft.problems


def test_lorenzo_can_still_waive_his_own_rule_but_not_availability(tmp_env, shadow_mode):
    """"Book as asked" waives the 12:00-18:00 policy, never a busy calendar."""
    morning = "2026-09-23T11:30:00-05:00"
    ok = booking.book(sopio(), morning, None, None, now=NOW, free_slots=[morning],
                      allow_outside_rules=True)
    assert booking.OUTSIDE_WINDOW not in ok.draft.problems

    busy = booking.book(sopio(), morning, None, None, now=NOW, free_slots=[],
                        allow_outside_rules=True)
    assert booking.SLOT_ALREADY_TAKEN in busy.draft.problems


# ------------------------------------------------------- an edit cannot confirm
def test_editing_the_body_cannot_clear_a_booking_problem(tmp_env, shadow_mode):
    """validate_draft only checks COPY. Clearing the whole list meant rewording
    a card was enough to confirm a prospect into a call GHL never created."""
    kept = approval_mod._kept_problems(
        [booking.APPOINTMENT_NOT_CREATED, booking.SLOT_NOT_VERIFIED, "missing booking link"])
    assert booking.APPOINTMENT_NOT_CREATED in kept
    assert booking.SLOT_NOT_VERIFIED in kept
    assert "missing booking link" not in kept  # a copy problem: re-derived, not carried


def test_an_edit_does_not_resurrect_the_zoom_note(tmp_env, shadow_mode):
    """zoom_not_connected is an operational note the core strips into the
    rationale; re-adding it would turn a sendable card into a blocked one."""
    assert approval_mod._kept_problems(["zoom_not_connected"]) == []


# ------------------------------------------------- an auto-responder is not a C
def test_an_out_of_office_body_is_never_a_confirmation(tmp_env, shadow_mode):
    """Eleven of the 44 recorded September replies are auto-responders whose
    first words match _CONFIRM_RE."""
    assert app_mod._body_is_out_of_office(
        "Sure, thanks for reaching out. I am currently out of the office and will return on Tuesday.") is True
    assert app_mod._body_is_out_of_office(
        "Sure, Thursday at 3 works for me. Talk then.") is False


# ------------------------------------------------------ a capped pull says so
def _paged_instantly(pages):
    def handler(request):
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        cursor = body.get("starting_after")
        idx = 0 if cursor is None else int(cursor)
        page = pages[idx]
        return httpx.Response(200, json=page)

    return Instantly(api_key="k", transport=httpx.MockTransport(handler))


def test_a_walk_that_hits_the_page_cap_reports_truncated():
    """Silently returning a sample as if it were the whole set is how a partial
    lead list gets applied to GHL, the source of truth."""
    pages = [{"items": [{"id": "a"}], "next_starting_after": "1"},
             {"items": [{"id": "b"}], "next_starting_after": "2"},
             {"items": [{"id": "c"}], "next_starting_after": "3"}]
    walk = _paged_instantly(pages).iterate("leads/list", body={"limit": 1}, max_pages=2)
    rows = list(walk)
    assert [r["id"] for r in rows] == ["a", "b"]
    assert walk.truncated is True and walk.complete is False


def test_a_walk_that_reaches_the_end_reports_complete():
    pages = [{"items": [{"id": "a"}], "next_starting_after": "1"},
             {"items": [{"id": "b"}], "next_starting_after": None}]
    walk = _paged_instantly(pages).iterate("leads/list", body={"limit": 1}, max_pages=10)
    rows = list(walk)
    assert [r["id"] for r in rows] == ["a", "b"]
    assert walk.complete is True and walk.truncated is False


# ------------------------------------------------ the email carries the buttons
def test_the_email_leg_renders_the_action_urls():
    """On an unprotected ntfy topic the push drops the buttons, so the email is
    the only way to approve or veto. It used to carry no link at all."""
    from shared import notify as notify_mod

    lines = notify_mod._action_lines(
        "view, Approve, https://x.test/approve/t1; view, Veto, https://x.test/veto/t1")
    assert lines == ["Approve: https://x.test/approve/t1", "Veto: https://x.test/veto/t1"]
    assert notify_mod._action_lines(None) == []


# -------------------------------------------------- one reservation, not three
def test_reserving_the_same_slot_twice_does_not_grow_the_registry(tmp_env, shadow_mode):
    from shared import store as store_mod

    st = store_mod.get_store(force_new=True)
    iso = "2026-09-24T15:00:00-05:00"
    for _ in range(3):
        approval_mod.reserve_slots(st, "a@example.com", [iso], "apr-1", NOW)
    rows = st.get(approval_mod.OFFERED_KEY, []) or []
    assert len([r for r in rows if r.get("approval") == "apr-1"]) == 1

    # a DIFFERENT lead offered the same time is still a separate, visible row:
    # that is what the never-double-offered rule reads this registry for.
    approval_mod.reserve_slots(st, "b@example.com", [iso], "apr-2", NOW)
    rows = st.get(approval_mod.OFFERED_KEY, []) or []
    assert len([r for r in rows if r.get("slot") == iso]) == 2


# ------------------------------------------------------- the copy stays in step
def test_booking_copy_carries_no_booking_link_line():
    """booking.py writes no booking-link sentence anywhere: no hardcoded copy,
    no draft.BOOKING_LINE and no "grab a time" ask (Lorenzo, 2026-09-23: the
    lead picks one of the offered times and Lorenzo sends the invite)."""
    src = (Path(__file__).resolve().parents[1] / "booking.py").read_text(encoding="utf-8")
    assert "Or grab whatever works here" not in src
    assert "BOOKING_LINE" not in src
    assert "grab a time" not in src


def test_the_lost_move_can_carry_a_reason(tmp_env, live_mode):
    """Without lostReason the third-no-show Lost move mirrors to Instantly as
    not_interested (-1) instead of no_show (-4)."""
    seen = []

    def handler(request):
        seen.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"ok": True})

    client = GHL(token="t", transport=httpx.MockTransport(handler))
    client.update_opportunity_stage("opp-1", "stage-lost", status="lost",
                                    lost_reason="No show x3 (SOP-005)")
    assert seen[0]["lostReason"] == "No show x3 (SOP-005)"


# ================================================================ review gaps
# The two booking defects the completeness critic found: integration fix #1
# stopped GoHighLevel emailing the prospect an invite before approval, but the
# engine's own confirmation and the veto path were both still wrong.
from datetime import timedelta                                           # noqa: E402

from shared.store import JsonFileStore                                   # noqa: E402
from services.reply_engine import no_show as no_show_mod, show_rate      # noqa: E402

BOOK_NOW = slot_rules.parse_iso("2026-09-22T13:00:00-05:00")   # Tuesday 13:00 CT
BOOK_SLOT = "2026-09-23T14:00:00-05:00"                        # Wednesday 14:00 CT


def _booked(tmp_path, now=BOOK_NOW, slot=BOOK_SLOT):
    """A booking exactly as classification makes one: guarded, store attached."""
    store = JsonFileStore(str(tmp_path / "booking-store.json"))
    state = sopio()
    result = booking.book(state, slot, None, None, now=now, free_slots=[slot], store=store)
    appointment_id = (state.cadence or {})["booking"]["appointment_id"]
    for key in store.keys("showrate:%s:" % appointment_id):
        rec = store.get(key)
        rec["appointment"]["contact_id"] = "iDhesF6A9rhdDajGZuYw"   # shadow books create no contact
        store.set(key, rec)
    return store, state, result, appointment_id


def _armed(store, appointment_id):
    out = []
    for key in store.keys("showrate:%s:" % appointment_id):
        for t in (store.get(key) or {}).get("touches", []):
            if not t.get("sent") and not t.get("skipped"):
                out.append(t["template_key"])
    return sorted(out)


def test_the_confirmation_ladder_does_not_start_before_the_approval(tmp_env, shadow_mode):
    """register_booking armed the S4 sequence at CLASSIFICATION time, and
    SEQUENCE puts confirm_email at T+0, so the ten-minute appointments tick
    mailed the prospect "Locked in for ..." before the approval card had been
    tapped - and sometimes after Lorenzo decided to veto.

    The GHL invite was already withheld (toNotify=False); this is the engine's
    own half of the same promise.
    """
    store, state, result, appt_id = _booked(tmp_env)
    key = show_rate.schedule_key(appt_id, slot_rules.to_tz(slot_rules.parse_iso(BOOK_SLOT)).isoformat())
    assert store.get(key)["held"]["reason"] == "awaiting_approval"
    assert "confirm_email" in _armed(store, appt_id), "the ladder should exist, just frozen"

    # the tick that used to send it, ten minutes later
    summary = show_rate.run(BOOK_NOW + timedelta(minutes=10), store, GHL())
    assert summary["sent"] == [] and summary["would_do"] == []
    assert summary["held"] == [key]
    # and it is still armed, not burned: nothing was consumed by the wait
    assert "confirm_email" in _armed(store, appt_id)


def test_approving_the_reply_starts_the_ladder_at_the_approval_moment(tmp_env, shadow_mode):
    """The T+0 touches are re-anchored to the release, not left stamped with
    the classification time: MAX_LATENESS['confirm_email'] is two hours, so an
    approval any later than that would drop the confirmation as too_late and
    the lead would get an invite with no confirmation at all."""
    store, state, result, appt_id = _booked(tmp_env)
    approved_at = BOOK_NOW + timedelta(hours=3, minutes=40)
    # the engine's own unedited draft went out (send_approved passes "approved")
    released = approval_mod.release_show_rate_hold(state, store, approved_at, reason="approved")
    assert released["released"] is True and released["rearmed"] >= 1
    key = show_rate.schedule_key(appt_id, slot_rules.to_tz(slot_rules.parse_iso(BOOK_SLOT)).isoformat())
    assert "held" not in store.get(key)
    touches = dict((t["template_key"], t) for t in store.get(key)["touches"])
    # ZC item 7: the approved reply WAS the confirmation, so the ladder's own
    # "Locked in ..." is skipped; the pre-read is re-anchored to the approval
    assert touches["confirm_email"]["skipped"] is True
    assert touches["confirm_email"]["skip_reason"] == show_rate.ENGINE_CONFIRMATION_SKIP
    assert store.get(key)["engine_confirmation_sent_at"] == approved_at.isoformat()
    preread = touches["preread_email"]
    assert preread["when_iso"] == (approved_at + timedelta(minutes=15)).isoformat()
    summary = show_rate.run(approved_at, store, GHL())
    spoken = [e["template"] for e in summary["would_do"] + summary["sent"]]
    assert "confirm_email" not in spoken and "preread_email" not in spoken
    summary = show_rate.run(approved_at + timedelta(minutes=15), store, GHL())
    assert [e["template"] for e in summary["would_do"]] == ["preread_email"]


def test_a_vetoed_booking_leaves_zero_armed_touches_and_no_appointment_row(tmp_env, shadow_mode):
    """cancel_booking undid the GHL appointment, the opportunity, the Instantly
    interest and the slot reservation, but never the show-rate schedule or the
    appointment:/appt: index rows. A refused call still sent the prospect a
    pre-read, a "we are on for tomorrow, reply C" and raised a 4 h chase task,
    and jobs/appointments_tick could not clean it up: it only cancels schedules
    GHL reports as cancelled, and without a token nothing is authoritative."""
    store, state, result, appt_id = _booked(tmp_env)
    assert store.get("appointment:%s" % appt_id) and store.get("appt:%s" % appt_id)

    out = approval_mod.cancel_booking(state, None, None, BOOK_NOW, store=store)

    assert out["teardown"]["touches_cancelled"] >= 1
    assert _armed(store, appt_id) == []
    assert store.get("appointment:%s" % appt_id) is None
    assert store.get("appt:%s" % appt_id) is None
    assert store.get(show_rate.hold_key(appt_id)) is None
    # ...and no later tick can resurrect any of it
    later = show_rate.run(slot_rules.parse_iso(BOOK_SLOT) - timedelta(hours=1), store, GHL())
    assert later["sent"] == [] and later["would_do"] == []


def test_a_call_awaiting_approval_is_never_chased_for_a_no_show(tmp_env, shadow_mode):
    """The prospect has been told nothing about a held call, so "Sorry we
    missed each other" would be the first they ever hear of it."""
    store, state, result, appt_id = _booked(tmp_env)
    appointment = {"id": appt_id, "start_iso": BOOK_SLOT, "contact_id": "iDhesF6A9rhdDajGZuYw",
                   "email": "sopiosvanishvili@taxfoaccounting.com"}
    after = slot_rules.parse_iso(BOOK_SLOT) + timedelta(minutes=30)
    out = no_show_mod.process(after, appointment, [], store, GHL())
    assert out["events"] == ["awaiting_approval"]
    assert out["actions"] == []
    assert store.get(no_show_mod.state_key(appt_id)) is None


def test_a_widget_booking_is_not_held(tmp_env, shadow_mode):
    """Only a booking the engine made from a reply needs an approval. A lead
    who books themselves through the calendar link has already been told the
    time, so their ladder starts on the next tick as before."""
    store = JsonFileStore(str(tmp_env / "widget.json"))
    appt = {"id": "ghl-widget-1", "start_iso": BOOK_SLOT, "contact_id": "c-1",
            "email": "pat@flowerhillfs.com", "first_name": "Pat", "niche": "cleaning",
            "booked_at": BOOK_NOW.isoformat()}
    res = show_rate.ensure_scheduled(store, appt, BOOK_NOW)
    assert res["created"] is True and not res.get("held")
    assert "held" not in (store.get(res["key"]) or {})


def test_an_engine_booking_is_not_marked_done_before_it_happens(tmp_env, shadow_mode):
    """register_booking calls no_show.cancel_recovery_for_rebooking with the id
    of the call it has just created. That used to write state=done for it, and
    process() returns immediately on a done state, so S5 never ran for a single
    engine-made booking - only for widget ones. Found while closing the veto
    gap, not in the review list."""
    store, state, result, appt_id = _booked(tmp_env)
    assert store.get(no_show_mod.state_key(appt_id)) is None

    # and the real purpose still works: a lead who rebooks after a no-show
    store.set(no_show_mod.state_key("appt-old"), {"state": "no_show", "start_iso": BOOK_SLOT})
    no_show_mod.cancel_recovery_for_rebooking(store, "appt-old")
    assert store.get(no_show_mod.state_key("appt-old"))["done_reason"] == "rebooked"


def test_a_held_call_that_is_approved_is_then_detected_normally(tmp_env, shadow_mode):
    """The hold suppresses S5 only while the approval is outstanding."""
    store, state, result, appt_id = _booked(tmp_env)
    approval_mod.release_show_rate_hold(state, store, BOOK_NOW + timedelta(minutes=5))
    appointment = {"id": appt_id, "start_iso": BOOK_SLOT, "contact_id": "iDhesF6A9rhdDajGZuYw",
                   "email": "sopiosvanishvili@taxfoaccounting.com"}
    after = slot_rules.parse_iso(BOOK_SLOT) + timedelta(minutes=30)
    out = no_show_mod.process(after, appointment, [], store, GHL())
    assert "awaiting_approval" not in out["events"]
