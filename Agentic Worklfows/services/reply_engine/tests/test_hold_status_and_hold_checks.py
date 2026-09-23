"""Booking-hold fixes (Slice 2 S-rest, fix piece R2).

* 9: the classification-time GHL appointment is created ``new`` (never GHL's
  default ``confirmed``) and without a notification, so no status-triggered
  GHL workflow or reminder reaches the prospect before Approve, and Approve is
  a real new -> confirmed transition.
* 10: the show-rate and no-show hold checks fail CLOSED. A store error while
  reading ``showrate_hold:<appt>`` keeps ``held`` on the saved schedule, sends
  nothing that tick, and is logged once per tick.
* 7: no-show recovery claims its two times through ``approval.claim_slots``
  (all or nothing, inside ``store.mutate``): a card that claims a time across
  the free-slot read gap wins it, the recovery re-picks, and every failure
  path gives its claim back.

Every lead here is fictional. Every HTTP transport is a MockTransport; the
live-mode test sets MODE=live in-process only.
"""
import json
import logging
from datetime import datetime, timedelta

import httpx
import pytest

from shared import slots as slot_rules
from shared.ghl import GHL
from shared.job_log import read_shadow_log
from shared.store import JsonFileStore

from services.reply_engine import approval as A
from services.reply_engine import booking, cadence
from services.reply_engine import no_show as ns
from services.reply_engine import show_rate
from services.reply_engine.cadence import LeadState
from services.reply_engine.show_rate import Touch

NOW = slot_rules.parse_iso("2026-09-21T21:10:00-05:00")
FRI_1PM = "2026-09-25T13:00:00-05:00"

LEAD = "owner@brightfieldcleaning.example"
OTHER = "office@maplegrovebooks.example"
APPT = "appt-hold-1"
BOOKED_AT = datetime.fromisoformat("2026-09-21T15:30:00-05:00")
CALL = "2026-09-24T15:00:00-05:00"


def raising_transport():
    def handler(request):
        raise AssertionError("HTTP request attempted: %s %s" % (request.method, request.url))

    return httpx.MockTransport(handler)


def lead_state():
    return LeadState(lead_email=LEAD, campaign_id="f00c5e28-fdc4-4d84-a7e6-dfba9695f35d",
                     status="positive_question", first_name="Dana", company="Brightfield Cleaning",
                     eaccount="sender@adveromedia.example", last_email_id="email-1", last_subject="Re: Dana, question",
                     ghl_contact_id="contact-hold-1", ghl_opportunity_id="opp-hold-1")


# ================================================================ defect 9
def _hold_payloads():
    return [r["payload"] for r in read_shadow_log() if r["action"] == "create_appointment"]


def test_shadow_hold_without_a_client_records_status_new_and_no_notice(tmp_env, shadow_mode):
    state = cadence.arm(lead_state(), NOW)
    res = booking.book(state, FRI_1PM, None, None, now=NOW, free_slots=[FRI_1PM])
    assert res.shadow is True
    payload = _hold_payloads()[-1]
    assert payload["appointmentStatus"] == "new"
    assert payload["toNotify"] is False


def test_shadow_hold_through_the_ghl_client_records_status_new_and_no_notice(tmp_env, shadow_mode):
    state = cadence.arm(lead_state(), NOW)
    ghl = GHL(token="fake-token", transport=raising_transport())
    booking.book(state, FRI_1PM, ghl, None, now=NOW, free_slots=[FRI_1PM])
    payload = _hold_payloads()[-1]
    assert payload["appointmentStatus"] == "new" and payload["toNotify"] is False
    assert payload["appointmentStatus"] != "confirmed"


def test_live_hold_posts_status_new_and_to_notify_false(live_mode, tmp_env):
    """The body GHL actually receives. GHL's own default is "confirmed", which
    the show-rate workflow's trigger would have mailed about a minute after
    classification, before Lorenzo saw the card."""
    bodies = []

    def ghl_handler(request):
        if request.url.path.endswith("/appointments") and request.method == "POST":
            bodies.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"id": "appt-live-hold"})
        if "free-slots" in request.url.path:
            return httpx.Response(200, json={"2026-09-25": {"slots": [FRI_1PM]}})
        return httpx.Response(200, json={"id": "ok"})

    ghl = GHL(token="fake-token", transport=httpx.MockTransport(ghl_handler))
    state = cadence.arm(lead_state(), NOW)
    booking.book(state, FRI_1PM, ghl, None, now=NOW, free_slots=[FRI_1PM])
    assert len(bodies) == 1
    assert bodies[0]["appointmentStatus"] == "new"
    assert bodies[0]["toNotify"] is False


def test_book_passes_the_hold_status_to_any_ghl_client(tmp_env, shadow_mode):
    calls = []

    class FakeGHL(object):
        def create_appointment(self, calendar_id, contact_id, start, end, title, **kw):
            calls.append(kw)
            return {"id": "appt-fake-hold", "shadow": True}

        def __getattr__(self, name):
            return lambda *a, **k: {"shadow": True}

    state = cadence.arm(lead_state(), NOW)
    booking.book(state, FRI_1PM, FakeGHL(), None, now=NOW, free_slots=[FRI_1PM])
    assert calls == [{"appointment_status": "new", "to_notify": False}]
    assert booking.HOLD_APPOINTMENT_STATUS == "new"


# =============================================================== defect 10
class FlakyHoldStore(JsonFileStore):
    """A JsonFileStore whose ``showrate_hold:`` reads fail while ``failing``."""

    failing = False

    def get(self, key, default=None):
        if self.failing and str(key).startswith(show_rate.HOLD_PREFIX):
            raise OSError("store read timed out")
        return super(FlakyHoldStore, self).get(key, default)


def _appt(appt_id=APPT, email=LEAD):
    return {"id": appt_id, "contact_id": "contact-%s" % appt_id, "start_iso": CALL, "email": email,
            "first_name": "Dana", "company": "Brightfield Cleaning", "booked_at": BOOKED_AT.isoformat(),
            "niche": "cleaning", "offer": "reactivation"}


def _shadow_ghl():
    return GHL(token=None, transport=raising_transport())


def _spoken(summary):
    return list(summary.get("sent") or []) + list(summary.get("would_do") or [])


def test_read_hold_tells_no_marker_apart_from_an_unreadable_one(tmp_env):
    store = FlakyHoldStore(tmp_env / "s.json")
    assert show_rate.read_hold(store, APPT) == (None, None)
    show_rate.hold(store, APPT, reason="awaiting_approval", now=BOOKED_AT)
    rec, err = show_rate.read_hold(store, APPT)
    assert rec["reason"] == "awaiting_approval" and err is None
    store.failing = True
    rec, err = show_rate.read_hold(store, APPT)
    assert rec is None and "store read timed out" in err


def test_the_ladder_runs_when_nothing_holds_it(tmp_env, shadow_mode):
    """Baseline for the tests below: without a hold, the T+0 confirmation is
    due on this tick, so "nothing was sent" there means the hold stopped it."""
    store = FlakyHoldStore(tmp_env / "s.json")
    summary = show_rate.run(BOOKED_AT + timedelta(minutes=2), store, _shadow_ghl(), a2p=False,
                            appointments=[_appt()])
    assert _spoken(summary), summary


def test_a_hold_read_error_never_lifts_the_hold_and_sends_nothing(tmp_env, shadow_mode):
    store = FlakyHoldStore(tmp_env / "s.json")
    show_rate.hold(store, APPT, reason="awaiting_approval", now=BOOKED_AT, meta={"lead_email": LEAD})
    show_rate.ensure_scheduled(store, _appt(), BOOKED_AT)
    key = show_rate.schedule_key(APPT, CALL)
    assert store.get(key).get("held")

    store.failing = True  # one brief store error during the ten-minute tick
    tick = BOOKED_AT + timedelta(minutes=10)
    summary = show_rate.run(tick, store, _shadow_ghl(), a2p=False, appointments=[_appt()])
    assert _spoken(summary) == []
    assert summary["hold_unreadable"] == [key]
    assert store.get(key).get("held"), "the saved schedule must keep its hold on a read error"

    # the next tick reads cleanly: still held (the marker is there), still silent
    store.failing = False
    summary = show_rate.run(tick + timedelta(minutes=10), store, _shadow_ghl(), a2p=False, appointments=[_appt()])
    assert _spoken(summary) == [] and store.get(key).get("held")

    # only the approval starts the ladder
    # (the approved reply was the confirmation: ZC item 7 skips the ladder's
    # own, so the first thing the ladder says is the pre-read)
    show_rate.release_hold(store, APPT, tick + timedelta(minutes=15))
    summary = show_rate.run(tick + timedelta(minutes=30), store, _shadow_ghl(), a2p=False, appointments=[_appt()])
    assert [e["template"] for e in _spoken(summary)] == ["preread_email"]


def test_an_unheld_schedule_is_skipped_for_the_tick_when_the_hold_cannot_be_read(tmp_env, shadow_mode):
    """Unknown is not "no hold": the tick sends nothing from it, writes no hold
    it does not know about, and the next clean tick sends."""
    store = FlakyHoldStore(tmp_env / "s.json")
    show_rate.ensure_scheduled(store, _appt(), BOOKED_AT)
    key = show_rate.schedule_key(APPT, CALL)
    store.failing = True
    summary = show_rate.run(BOOKED_AT + timedelta(minutes=2), store, _shadow_ghl(), a2p=False,
                            appointments=[_appt()])
    assert _spoken(summary) == [] and key in summary["held"]
    assert not store.get(key).get("held")
    store.failing = False
    summary = show_rate.run(BOOKED_AT + timedelta(minutes=3), store, _shadow_ghl(), a2p=False,
                            appointments=[_appt()])
    assert _spoken(summary)


def test_a_schedule_born_while_the_hold_is_unreadable_is_born_held(tmp_env, shadow_mode):
    store = FlakyHoldStore(tmp_env / "s.json")
    store.failing = True
    res = show_rate.ensure_scheduled(store, _appt(), BOOKED_AT)
    assert res["created"] and res["hold_unreadable"]
    rec = store.get(res["key"])
    assert rec["held"]["reason"] == "hold_unreadable" and rec["held"]["provisional"] is True
    # a later tick that does not re-read the calendar still sends nothing from it
    store.failing = False
    summary = show_rate.run(BOOKED_AT + timedelta(minutes=2), store, _shadow_ghl(), a2p=False)
    assert _spoken(summary) == []
    # a clean read with no marker settles it: the provisional hold goes
    show_rate.ensure_scheduled(store, _appt(), BOOKED_AT + timedelta(minutes=3))
    assert not store.get(res["key"]).get("held")


def test_a_hold_read_failure_is_logged_once_per_tick(tmp_env, shadow_mode, caplog):
    store = FlakyHoldStore(tmp_env / "s.json")
    for appt_id in ("appt-a", "appt-b", "appt-c"):
        show_rate.hold(store, appt_id, reason="awaiting_approval", now=BOOKED_AT)
    appts = [_appt(i) for i in ("appt-a", "appt-b", "appt-c")]
    store.failing = True
    with caplog.at_level(logging.WARNING, logger=show_rate.logger.name):
        show_rate.run(BOOKED_AT + timedelta(minutes=10), store, _shadow_ghl(), a2p=False, appointments=appts)
    lines = [r for r in caplog.records if "show-rate hold" in r.getMessage()]
    assert len(lines) == 1, [r.getMessage() for r in lines]


def test_no_show_treats_an_unreadable_hold_as_held(tmp_env, shadow_mode, caplog):
    """The no-show chase ("Sorry we missed each other" and the recovery
    ladder) must not start on a call whose approval state is unknown."""
    store = FlakyHoldStore(tmp_env / "s.json")
    ghl_requests = []
    ghl = GHL(token=None, transport=httpx.MockTransport(lambda r: ghl_requests.append(r) or httpx.Response(200)))
    appt = dict(_appt(), end_iso="2026-09-24T15:15:00-05:00")
    host = {"at_iso": "2026-09-24T14:59:00-05:00", "name": "Host", "email": "host@adverosolutions.example",
            "is_host": True}
    after = datetime.fromisoformat("2026-09-24T15:20:00-05:00")
    store.failing = True
    with caplog.at_level(logging.WARNING):
        out = ns.process(after, appt, [host], store, ghl)
        again = ns.process(after, dict(appt, id="appt-hold-2"), [host], store, ghl)
    assert out["events"] == ["awaiting_approval"] and again["events"] == ["awaiting_approval"]
    assert out["actions"] == [] and store.keys("recovery:") == [] and store.keys("noshow_flag:") == []
    assert [r for r in read_shadow_log() if r["action"] in ("update_appointment_status", "send_message")] == []
    assert len([r for r in caplog.records if "show-rate hold" in r.getMessage()]) == 1
    assert ns._show_rate_held(store, APPT, after) is True
    store.failing = False
    assert ns._show_rate_held(store, APPT, after) is False  # no marker, read cleanly


# ================================================================ defect 7
FREE = ["2026-09-28T13:00:00-05:00", "2026-09-28T14:00:00-05:00", "2026-09-29T13:00:00-05:00",
        "2026-09-29T14:00:00-05:00", "2026-09-30T13:00:00-05:00", "2026-09-30T14:00:00-05:00"]
FLAG_AT = datetime.fromisoformat("2026-09-24T15:20:00-05:00")


class RacingStore(JsonFileStore):
    """Another lead's card claims ``racer`` times in the gap between the
    recovery's registry read and its claim: the first mutate of the shared
    registry lets the rival land first."""

    racer = None  # type: ignore

    def mutate(self, key, fn, default=None):
        if key == A.OFFERED_KEY and self.racer:
            lead, isos = self.racer
            self.racer = None
            assert A.claim_slots(self, lead, isos, FLAG_AT) == []
        return super(RacingStore, self).mutate(key, fn, default)


def _registry_owners(store):
    owners = {}
    for r in store.get(A.OFFERED_KEY, []) or []:
        owners.setdefault(r["slot"], set()).add(r["lead"])
    return owners


def _no_double_offer(store):
    owners = _registry_owners(store)
    assert all(len(leads) == 1 for leads in owners.values()), owners
    return owners


def _recovery_appt():
    return dict(_appt("appt-ns-1"), end_iso="2026-09-24T15:15:00-05:00")


def _first_pick(tmp_env, free):
    return ns.fresh_two_slots(FLAG_AT, None, JsonFileStore(tmp_env / "pick.json"), free_slots=(free, "ghl"))["slots"]


def test_recovery_claim_loses_the_race_and_repicks_from_the_same_free_list(tmp_env, shadow_mode, monkeypatch):
    reads = []
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: reads.append(1) or (list(FREE), "ghl"))
    first = _first_pick(tmp_env, FREE)
    store = RacingStore(tmp_env / "s.json")
    store.racer = (OTHER, [first[0]])
    info = ns.claim_recovery_slots(FLAG_AT, None, store, _recovery_appt())
    assert len(info["slots"]) == 2 and first[0] not in info["slots"]
    assert info["text"] and not info.get("withheld")
    assert reads == [1], "the re-pick uses the same free-slot read"
    owners = _no_double_offer(store)
    assert owners[first[0]] == {OTHER}
    assert all(owners[s] == {LEAD} for s in info["slots"])
    assert sorted(store.get(ns.OFFERED_SLOTS_KEY)) == sorted(info["slots"])


def test_process_never_emails_a_time_another_card_claimed_in_the_gap(tmp_env, shadow_mode, monkeypatch):
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(FREE), "ghl"))
    first = _first_pick(tmp_env, FREE)
    store = RacingStore(tmp_env / "s.json")
    store.racer = (OTHER, list(first))
    appt = _recovery_appt()
    host = {"at_iso": "2026-09-24T14:59:00-05:00", "name": "Host", "email": "host@adverosolutions.example",
            "is_host": True}
    out = ns.process(FLAG_AT, appt, [host], store, _shadow_ghl())
    assert out["state"] == "no_show"
    rec = store.get(ns.recovery_key(appt["id"], CALL))
    offered = rec["slots"]["slots"]
    assert len(offered) == 2 and not set(offered) & set(first)
    owners = _no_double_offer(store)
    assert all(owners[s] == {OTHER} for s in first)
    assert all(owners[s] == {LEAD} for s in offered)


def test_a_short_free_list_offers_only_what_is_left_after_the_rival(tmp_env, shadow_mode, monkeypatch):
    two = FREE[:2]
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(two), "ghl"))
    first = _first_pick(tmp_env, two)
    store = RacingStore(tmp_env / "s.json")
    store.racer = (OTHER, [first[0]])
    info = ns.claim_recovery_slots(FLAG_AT, None, store, _recovery_appt())
    assert first[0] not in info["slots"]
    owners = _no_double_offer(store)
    assert owners[first[0]] == {OTHER}
    assert all(owners[s] == {LEAD} for s in info["slots"])


def test_recovery_goes_link_only_when_every_pick_is_taken(tmp_env, shadow_mode, monkeypatch):
    """Rivals keep winning: after RECOVERY_CLAIM_ATTEMPTS picks the copy goes
    out link-only, holding nothing, instead of naming a taken time."""
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(FREE), "ghl"))
    tried = []

    def always_taken(store, lead, isos, now, fields=None):
        tried.append(list(isos))
        return [isos[0]]

    monkeypatch.setattr(A, "claim_slots", always_taken)
    store = JsonFileStore(tmp_env / "s.json")
    info = ns.claim_recovery_slots(FLAG_AT, None, store, _recovery_appt())
    assert info["slots"] == [] and info["text"] == "" and info["withheld"] == "slot_taken"
    assert len(tried) == ns.RECOVERY_CLAIM_ATTEMPTS
    assert len({t[0] for t in tried}) == len(tried), "each retry excludes the times already lost"
    assert store.get(A.OFFERED_KEY, []) in ([], None) and store.get(ns.OFFERED_SLOTS_KEY, []) in ([], None)
    copy = ns.render("ns_reschedule_email", _recovery_appt(), slot_rules.parse_iso(CALL), info["text"], 1)
    assert "Two times" not in copy["body"]


def test_an_injected_picker_that_collides_falls_back_to_link_only(tmp_env, shadow_mode):
    store = JsonFileStore(tmp_env / "s.json")
    picked = {"slots": FREE[:2], "text": "Mon 1:00pm or Mon 2:00pm CT", "source": "ghl"}
    assert A.claim_slots(store, OTHER, [FREE[1]], FLAG_AT) == []
    info = ns.claim_recovery_slots(FLAG_AT, None, store, _recovery_appt(), slots_fn=lambda now: dict(picked))
    assert info["slots"] == [] and info["text"] == "" and info["withheld"] == "slot_taken"
    assert _no_double_offer(store)[FREE[1]] == {OTHER}
    assert FREE[0] not in _registry_owners(store)  # all or nothing: the free one was not held either


def test_an_unreadable_registry_offers_no_times(tmp_env, shadow_mode, monkeypatch):
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(FREE), "ghl"))

    def boom(*a, **k):
        raise OSError("registry unavailable")

    monkeypatch.setattr(A, "claim_slots", boom)
    info = ns.claim_recovery_slots(FLAG_AT, None, JsonFileStore(tmp_env / "s.json"), _recovery_appt())
    assert info["slots"] == [] and info["text"] == "" and info["withheld"] == "registry_unavailable"


def test_a_failed_recovery_record_write_gives_the_claim_back(tmp_env, shadow_mode, monkeypatch):
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(FREE), "ghl"))

    class FailingRecordStore(JsonFileStore):
        def set(self, key, value):
            if str(key).startswith("recovery:"):
                raise OSError("disk full")
            return super(FailingRecordStore, self).set(key, value)

    store = FailingRecordStore(tmp_env / "s.json")
    host = {"at_iso": "2026-09-24T14:59:00-05:00", "name": "Host", "email": "host@adverosolutions.example",
            "is_host": True}
    with pytest.raises(OSError):
        ns.process(FLAG_AT, _recovery_appt(), [host], store, _shadow_ghl())
    assert [r for r in store.get(A.OFFERED_KEY, []) or [] if r.get("lead") == LEAD] == []
    assert store.get(ns.OFFERED_SLOTS_KEY, []) in ([], None)


def test_a_failed_re_render_gives_the_new_claim_back(tmp_env, shadow_mode, monkeypatch):
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(FREE), "ghl"))
    store = JsonFileStore(tmp_env / "s.json")
    appt = {"id": "appt-ns-2", "email": LEAD, "contact_id": "contact-ns-2"}  # no start_iso: render fails
    touch = Touch(key="appt-ns-2:x:ns1:ns_reschedule_email", appointment_id="appt-ns-2", contact_id="contact-ns-2",
                  when_iso=FLAG_AT.isoformat(), channel="email", template_key="ns_reschedule_email", body="old",
                  subject="Missed you on our call", meta={"no_show_count": 1})
    out = ns._refresh_slot_copy(touch, {"slots": {}}, appt, FLAG_AT, None, store)
    assert out is None
    assert [r for r in store.get(A.OFFERED_KEY, []) or [] if r.get("lead") == LEAD] == []


def test_live_unverified_times_are_not_held(tmp_env, live_mode, monkeypatch):
    """Live never names synthetic-grid times, so holding them would block
    them for every other lead while nobody was offered them."""
    monkeypatch.setattr(ns, "free_slot_list", lambda now, ghl: (list(FREE), "synthetic_open_hours"))
    store = JsonFileStore(tmp_env / "s.json")
    appt = _recovery_appt()
    touch = Touch(key="appt-ns-1:%s:ns1:ns_reschedule_email" % CALL, appointment_id=appt["id"],
                  contact_id=appt["contact_id"], when_iso=FLAG_AT.isoformat(), channel="email",
                  template_key="ns_reschedule_email", body="old", subject="Missed you on our call",
                  meta={"no_show_count": 1})
    out = ns._refresh_slot_copy(touch, {"slots": {}}, appt, FLAG_AT, None, store)
    assert out is not None and "Two times" not in out["body"]
    assert [r for r in store.get(A.OFFERED_KEY, []) or [] if r.get("lead") == LEAD] == []
