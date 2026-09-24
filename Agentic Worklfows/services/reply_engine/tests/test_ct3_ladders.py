"""CT3 piece D: the template gate on the three ladders (cadence, show-rate,
no-show). An unapproved or nonconforming touch is held, never a card and
never a send; approving the template lets the same touch out.

The conftest approves every ladder id at its current hash (``approvals_file``);
each test revokes what it needs. Lead data is made up. MODE=shadow unless a
test asks for live_mode, and every client is a mock.
"""
import json
from datetime import datetime, timedelta

import httpx
import pytest

from shared import job_log, llm
from shared import slots as slot_rules
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.job_log import read_shadow_log
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import cadence, no_show as ns, show_rate as sr
from services.reply_engine import template_gate as gate
from services.reply_engine.cadence import LeadState

CLEANING_REACT = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
LEAD = "dana@examplecleaning.test"
COMPANY = "Brightside Janitorial"
FREE = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]


def ct(*args):
    return TZ.localize(datetime(*args))


def make_state(**kw):
    base = dict(lead_email=LEAD, campaign_id=CLEANING_REACT, status="positive_interested", first_name="Dana",
                company=COMPANY, eaccount="lorenzo@adveromedia.com", thread_id="thr-ct3",
                last_email_id="01a0c5aa-0000-7000-8000-00000000ct31", last_subject="Re: Dana, question")
    base.update(kw)
    return LeadState(**base)


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


@pytest.fixture(autouse=True)
def public_base_url(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)


def replies():
    return [r for r in read_shadow_log() if r["action"] == "reply_to_email"]


def at_day(done, when):
    """A lead whose ladder finished day ``done`` and is due at ``when``."""
    state = cadence.arm(make_state(), ct(2026, 9, 18, 16, 0))
    state.cadence["day"] = done
    state.cadence["next_send_at"] = when.isoformat()
    return state


# ================================================================ cadence
def test_an_approved_day_carries_its_template_id_and_goes_out(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(at_day(2, now), now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send"
    assert res["touch"]["template_id"] == "cadence.e3" and res["touch"]["template_hash"]
    assert "cadence.e3" in cadence.summarize_touch(res)
    assert len(replies()) == 1


def test_an_unapproved_day_is_held_not_sent_and_reported_once_a_day(store, tmp_env, approvals_file):
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 22, 10, 0))
    first = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=FREE,
                              notify_fn=lambda *a, **k: None)
    assert first["action"] == "held_template" and first["template_id"] == "cadence.e3"
    assert first["reason"] == "unapproved" and not first["quiet"]
    line = cadence.summarize_touch(first)
    assert "HELD" in line and "cadence.e3" in line and "got taken" not in line
    again = cadence.tick_lead(state, ct(2026, 9, 22, 11, 0), store=store, free_slots=FREE,
                              notify_fn=lambda *a, **k: None)
    assert again["action"] == "held_template" and again["quiet"]
    assert replies() == [] and state.cadence["day"] == 2 and state.cadence["touches"] == []
    assert state.cadence["template_hold"]["template_id"] == "cadence.e3"
    # counted once for the FYI, not once per tick
    assert gate.drain_fyi(store)[1] == {"cadence.e3": 1}
    # approved: the same day goes out and the hold is cleared
    approvals_file.approve_ids("cadence.e3")
    sent = cadence.tick_lead(state, ct(2026, 9, 22, 12, 0), store=store, free_slots=FREE,
                             notify_fn=lambda *a, **k: None)
    assert sent["action"] == "would_send" and "template_hold" not in state.cadence
    assert len(replies()) == 1


def test_an_unapproved_part_holds_the_day(store, tmp_env, approvals_file):
    approvals_file.revoke_ids("cadence.e4.offer_proof.reactivation")
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(at_day(3, now), now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "held_template" and "cadence.e4.offer_proof.reactivation" in res["ids"]
    assert replies() == []


def test_a_dry_run_previews_the_hold(store, tmp_env, approvals_file):
    approvals_file.revoke_ids("cadence.e3")
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(2, now)
    before = json.dumps(cadence.state_to_dict(state), sort_keys=True, default=str)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, dry_run=True)
    assert res["action"] == "held_template" and res["dry_run"]
    assert json.dumps(cadence.state_to_dict(state), sort_keys=True, default=str) == before


def test_d1_unapproved_sends_no_veto_ping_and_approval_opens_a_fresh_window(store, live_mode, tmp_env,
                                                                            approvals_file):
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"id": "e-1", "from_address_email": LEAD})
        return httpx.Response(200, json={"id": "sent-1"})

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    approvals_file.revoke_ids("cadence.e1")
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []

    def tick(h, m=0):
        return cadence.tick_lead(state, ct(2026, 9, 22, h, m), store=store, instantly=inst, free_slots=FREE,
                                 notify_fn=lambda *a, **k: pings.append((a, k)))

    assert tick(9, 30)["action"] == "held_template"
    assert tick(10)["action"] == "held_template"
    assert pings == [] and calls == [] and state.cadence.get("veto_notified_at") is None
    approvals_file.approve_ids("cadence.e1")
    opened = tick(11)
    assert opened["action"] == "veto_window_opened" and len(pings) == 1 and calls == []
    pinged = slot_rules.parse_iso(state.cadence["veto_notified_at"])
    send_at = slot_rules.parse_iso(state.cadence["next_send_at"])
    assert send_at - pinged >= timedelta(minutes=cadence.VETO_WINDOW_MINUTES)
    assert tick(11, 30)["action"] == "not_due" and calls == []
    sent = cadence.tick_lead(state, send_at, store=store, instantly=inst, free_slots=FREE,
                             notify_fn=lambda *a, **k: None)
    assert sent["action"] == "sent" and calls == ["GET", "POST"]


def test_d1_revoked_after_the_ping_drops_the_window(store, live_mode, tmp_env, approvals_file):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    res = cadence.tick_lead(state, ct(2026, 9, 22, 9, 30), store=store, free_slots=FREE,
                            notify_fn=lambda *a, **k: {"email": True})
    assert res["action"] == "veto_window_opened" and state.cadence["veto_notified_at"]
    approvals_file.revoke_ids("cadence.e1")
    held = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=FREE,
                             notify_fn=lambda *a, **k: None)
    assert held["action"] == "held_template" and state.cadence["veto_notified_at"] is None


def test_three_business_days_held_stops_the_ladder_and_resume_works(store, tmp_env, approvals_file):
    approvals_file.revoke_ids("cadence.e3")
    state = at_day(2, ct(2026, 9, 21, 10, 0))  # Monday
    pushes = []
    actions = []
    for day in (21, 22, 23, 24):  # Mon .. Thu
        now = ct(2026, 9, day, 10, 0)
        actions.append(cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                         notify_fn=lambda *a, **k: pushes.append((a, k))))
    assert [r["action"] for r in actions] == ["held_template", "held_template", "held_template", "stopped"]
    stopped = actions[-1]
    assert stopped["reason"] == "template_unapproved" and stopped["days"] == cadence.TEMPLATE_HOLD_STALL_DAYS
    assert state.cadence["stopped_reason"] == "template_unapproved"
    assert "cadence.e3" in cadence.summarize_touch(stopped)
    # one push, ids and counts only
    assert len(pushes) == 1
    title, message = pushes[0][0][:2]
    for private in (LEAD, COMPANY, "Dana", "http"):
        assert private not in title and private not in message
    assert "cadence.e3" in message
    assert cadence.tick_lead(state, ct(2026, 9, 24, 11, 0), store=store, free_slots=FREE,
                             notify_fn=lambda *a, **k: None)["action"] == "already_stopped"
    # resumable
    approvals_file.approve_ids("cadence.e3")
    resumed = cadence.resume_after_recipient_hold(state, ct(2026, 9, 24, 12, 0))
    assert resumed["resumed"] and resumed["day"] == 3 and "template_hold" not in state.cadence
    now = ct(2026, 9, 24, 13, 0)
    sent = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                             notify_fn=lambda *a, **k: None)
    assert sent["action"] == "would_send" and sent["day"] == 3


def test_e2_by_default_never_calls_the_research_model(store, tmp_env):
    calls = []
    llm.register_fake("research", lambda system, user, json_mode: calls.append(1) or "A line about them")
    try:
        touch = cadence.build_touch(make_state(), 2, FREE)
        assert touch.meta["research_source"] == "fallback"
        assert list(touch.template_parts) == ["cadence.e2.research_fallback.reactivation"]
        now = ct(2026, 9, 22, 10, 0)
        res = cadence.tick_lead(at_day(1, now), now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
        assert res["action"] == "would_send" and calls == []
    finally:
        llm.clear_fakes()


def test_e2_with_a_model_line_is_held_never_sent(store, tmp_env):
    llm.register_fake("research", lambda system, user, json_mode: "Your crews cover three towns, which is a lot")
    try:
        now = ct(2026, 9, 22, 10, 0)
        res = cadence.tick_lead(at_day(1, now), now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None,
                                research_mode="llm")
        assert res["action"] == "held_template" and "cadence.e2.research_line" in res["ids"]
        assert replies() == []
    finally:
        llm.clear_fakes()


def test_e2_carries_no_slots_even_when_some_are_passed():
    state = make_state()
    touch = cadence.build_touch(state, 2, FREE)
    assert touch.template_id == "cadence.e2" and touch.slots == []
    assert "slots" not in cadence.touch_bindings(state, touch)


def test_slots_are_bound_to_the_ones_offered(store, tmp_env):
    touch = cadence.build_touch(make_state(), 3, FREE)
    gate.stamp(touch, touch.template_id, list(touch.template_parts))
    assert gate.touch_verdict(touch, bindings=cadence.touch_bindings(make_state(), touch)).allowed
    other = slot_rules.format_slots([slot_rules.parse_iso("2026-09-25T13:00:00-05:00"),
                                     slot_rules.parse_iso("2026-09-28T14:00:00-05:00")])
    touch.body_text = touch.body_text.replace(cadence.touch_bindings(make_state(), touch)["slots"], other)
    verdict = gate.touch_verdict(touch, bindings=cadence.touch_bindings(make_state(), touch))
    assert not verdict.allowed and verdict.reason == "nonconforming"


# ============================================================== show-rate
NOW = datetime.fromisoformat("2026-09-21T17:10:00-05:00")
APPT = {
    "id": "appt-ct3-1",
    "contact_id": "contact-ct3-1",
    "first_name": "Dana",
    "company": COMPANY,
    "email": LEAD,
    "niche": "cleaning",
    "offer": "reactivation",
    "campaign_id": CLEANING_REACT,
    "lead_tz": "America/New_York",
    "start_iso": "2026-09-23T11:30:00-05:00",
    "end_iso": "2026-09-23T11:45:00-05:00",
    "zoom_link": "https://zoom.us/j/000000000301",
    "booked_at": NOW.isoformat(),
}


def make_ghl():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})
    return GHL(token=None, transport=httpx.MockTransport(handler)), requests


def confirm_touch(store):
    for key in store.keys("showrate:"):
        for t in store.get(key)["touches"]:
            if t["template_key"] == "confirm_email":
                return t
    return None


def test_a_held_show_rate_touch_stays_pending_uncounted_unclaimed_then_sends(store, tmp_env, approvals_file):
    ghl, requests = make_ghl()
    tid = sr.resolve_template_id("confirm_email", APPT)
    assert tid and tid.startswith("show_rate.confirm_email")
    approvals_file.revoke_ids(tid)
    out = sr.run(NOW, store, ghl, appointments=[APPT])
    held = [e for e in out["held_template"] if e["template"] == "confirm_email"]
    assert held and held[0]["template_id"] == tid and held[0]["reason"] == "unapproved"
    assert "confirm_email" not in [e["template"] for e in out["would_do"]]
    t = confirm_touch(store)
    assert not t["sent"] and not t["skipped"] and not t.get("attempts")
    assert t["template_hold"]["reason"] == "unapproved"
    assert store.get("touch_sent:%s" % t["key"]) is None  # the claim was released
    assert requests == []
    # a second tick: still held, counted once for the FYI
    sr.run(NOW + timedelta(minutes=5), store, ghl, appointments=[APPT])
    assert gate.drain_fyi(store)[1].get(tid) == 1
    approvals_file.approve_ids(tid)
    out = sr.run(NOW + timedelta(minutes=10), store, ghl, appointments=[APPT])
    assert "confirm_email" in [e["template"] for e in out["would_do"]]
    t = confirm_touch(store)
    assert t["sent"] and not t.get("template_hold") and t["template_id"] == tid
    assert requests == []  # shadow: a would_do record, no HTTP


def test_a_held_touch_still_expires(store, tmp_env, approvals_file):
    ghl, _ = make_ghl()
    tid = sr.resolve_template_id("confirm_email", APPT)
    approvals_file.revoke_ids(tid)
    sr.run(NOW, store, ghl, appointments=[APPT])
    later = NOW + sr.MAX_LATENESS["confirm_email"] + timedelta(minutes=5)
    out = sr.run(later, store, ghl, appointments=[APPT])
    assert {"template": "confirm_email", "reason": "too_late"}.items() <= [
        e for e in out["skipped"] if e["template"] == "confirm_email"][0].items()
    assert confirm_touch(store)["skip_reason"] == "too_late"


def test_an_opted_out_lead_gets_no_show_rate_touch(store, tmp_env):
    store.set("lead:%s:%s" % (CLEANING_REACT, LEAD),
              {"lead_email": LEAD, "campaign_id": CLEANING_REACT, "opt_out": {"reason": "unsubscribe"}})
    ghl, _ = make_ghl()
    out = sr.run(NOW, store, ghl, appointments=[APPT])
    assert out["would_do"] == []
    assert [e["reason"] for e in out["skipped"] if e["template"] == "confirm_email"] == ["opt_out"]
    assert confirm_touch(store)["skip_reason"] == "opt_out"


def test_the_opt_out_is_found_through_the_booking_row(store, tmp_env):
    appt = dict(APPT, email=None, id="appt-ct3-2")
    store.set("appointment:appt-ct3-2", {"lead_email": LEAD, "campaign_id": CLEANING_REACT})
    store.set("lead:%s:%s" % (CLEANING_REACT, LEAD), {"lead_email": LEAD, "opt_out": {"reason": "final_no"}})
    touch = sr.schedule_for(appt, NOW)[0]
    assert sr.dispatch_touch(touch, None, NOW, store=store, appointment=appt) == {"status": "skipped",
                                                                                 "reason": "opt_out"}


def test_an_unstamped_touch_is_held_at_the_choke_point(tmp_env):
    ghl, requests = make_ghl()
    touch = sr.schedule_for(APPT, NOW)[0]
    touch.template_id = touch.template_hash = None
    out = sr.dispatch_touch(touch, ghl, NOW, appointment=APPT)
    assert out["status"] == "held" and out["reason"] == "no_template" and requests == []


def test_an_injected_sentence_is_held(tmp_env):
    touch = sr.schedule_for(APPT, NOW)[0]
    touch.body = touch.body.replace("Lorenzo", "Wire the deposit today.\n\nLorenzo")
    out = sr.dispatch_touch(touch, None, NOW, appointment=APPT)
    assert out["status"] == "held" and out["reason"] == "nonconforming"


@pytest.mark.parametrize("zone", ["America/Toronto", "America/Detroit", "America/Los_Angeles"])
def test_show_rate_for_a_lead_in_another_zone_is_not_refused(store, tmp_env, zone):
    ghl, _ = make_ghl()
    appt = dict(APPT, id="appt-tz-%s" % zone.split("/")[1], lead_tz=zone)
    out = sr.run(NOW, store, ghl, appointments=[appt])
    assert out["held_template"] == []
    assert "confirm_email" in [e["template"] for e in out["would_do"]]


def test_a_company_with_a_banned_word_passes_through_allow_terms(store, tmp_env):
    ghl, _ = make_ghl()
    appt = dict(APPT, id="appt-ct3-auto", company="Automated Janitorial")
    out = sr.run(NOW, store, ghl, appointments=[appt])
    assert out["held_template"] == []
    assert "confirm_email" in [e["template"] for e in out["would_do"]]


def test_a_redeploy_that_changes_a_hash_does_not_strand_pending_touches(store, tmp_env):
    """flag 3: the copy is re-rendered and re-stamped at dispatch, so a touch
    stamped by an older build is judged on today's template."""
    ghl, _ = make_ghl()
    sr.ensure_scheduled(store, APPT, NOW)
    key = store.keys("showrate:")[0]

    def stale(rec):
        for t in rec["touches"]:
            t["template_hash"] = "0" * 64
        return rec
    store.mutate(key, stale, default={})
    out = sr.run(NOW, store, ghl, appointments=[APPT])
    assert out["held_template"] == []
    assert "confirm_email" in [e["template"] for e in out["would_do"]]


# ================================================================ no-show
START = datetime.fromisoformat("2026-09-24T15:00:00-05:00")
NS_APPT = dict(APPT, id="appt-ns-ct3", start_iso=START.isoformat(),
               end_iso=(START + timedelta(minutes=15)).isoformat(), booked_at=None)
HOST = {"at_iso": (START - timedelta(minutes=1)).isoformat(), "name": "Lorenzo Villarreal",
        "email": "lorenzovillarreal@adverosolutions.com", "is_host": True}


def fixed_slots(now):
    return {"slots": ["2026-09-25T14:00:00-05:00", "2026-09-28T15:30:00-05:00"],
            "text": "Fri 2:00pm or Mon 3:30pm CT", "source": "ghl"}


def one_slot(now):
    return {"slots": ["2026-09-25T14:00:00-05:00"], "text": "Fri 2:00pm CT", "source": "ghl"}


def recovery_touch(store, template_key):
    rec = store.get(ns.recovery_key(NS_APPT["id"], START.isoformat()))
    return [t for t in rec["touches"] if t["template_key"] == template_key][0]


def test_a_held_no_show_touch_stays_pending_then_sends_after_approval(store, tmp_env, approvals_file):
    ghl, requests = make_ghl()
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, NS_APPT, [HOST], store, ghl, slots_fn=fixed_slots)
    tid = recovery_touch(store, "ns_reschedule_email")["template_id"]
    assert tid and tid.startswith("no_show.ns_reschedule_email")
    approvals_file.revoke_ids(tid)
    due = START + timedelta(minutes=25)
    out = ns.run_recovery(due, store, ghl, slots_fn=fixed_slots)
    assert [e["template"] for e in out["held_template"]] == ["ns_reschedule_email"] and out["would_do"] == []
    t = recovery_touch(store, "ns_reschedule_email")
    assert not t["sent"] and not t["skipped"] and not t.get("attempts")
    assert store.get("touch_sent:%s" % t["key"]) is None
    approvals_file.approve_ids(tid)
    out = ns.run_recovery(due + timedelta(minutes=1), store, ghl, slots_fn=fixed_slots)
    assert [e["template"] for e in out["would_do"]] == ["ns_reschedule_email"]
    assert recovery_touch(store, "ns_reschedule_email")["sent"]


def test_the_reschedule_email_is_bound_to_its_slots(store, tmp_env):
    ghl, _ = make_ghl()
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, NS_APPT, [HOST], store, ghl, slots_fn=fixed_slots)
    out = ns.run_recovery(flagged + timedelta(hours=1), store, ghl, slots_fn=fixed_slots)
    assert "ns_reschedule_email" in [e["template"] for e in out["would_do"]]
    assert "Fri 2:00pm or Mon 3:30pm CT" in job_log.read_shadow_log()[-1]["payload"]["message"]


def test_one_free_slot_is_never_sent_and_never_replaced_by_a_link(store, tmp_env):
    ghl, _ = make_ghl()
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, NS_APPT, [HOST], store, ghl, slots_fn=one_slot)
    out = ns.run_recovery(START + timedelta(minutes=25), store, ghl, slots_fn=one_slot)
    assert out["would_do"] == [] and [e["error"] for e in out["errors"]] == ["no_slots"]
    t = recovery_touch(store, "ns_reschedule_email")
    assert not t["sent"] and not t["skipped"] and t["attempts"] == 1
    assert "Fri 2:00pm" not in t["body"] and "http" not in t["body"]


def test_fresh_two_slots_with_one_candidate_offers_none(store, tmp_env):
    info = ns.fresh_two_slots(datetime.fromisoformat("2026-09-24T15:20:00-05:00"), None, store,
                              free_slots=(["2026-09-28T13:00:00-05:00"], "ghl"))
    assert info["slots"] == [] and info["text"] == "" and info["withheld"] == "one_slot"


# ============================================================ kill switch
def test_the_kill_switch_holds_all_three_ladders(store, tmp_env, approvals_file):
    approvals_file.kill_switch(True)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(at_day(2, now), now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "held_template" and res["reason"] == "kill_switch"
    ghl, requests = make_ghl()
    out = sr.run(NOW, store, ghl, appointments=[APPT])
    assert out["would_do"] == [] and {e["reason"] for e in out["held_template"]} == {"kill_switch"}
    flagged = START + timedelta(minutes=10)
    ns.process(flagged, NS_APPT, [HOST], store, ghl, slots_fn=fixed_slots)
    rec = ns.run_recovery(START + timedelta(minutes=25), store, ghl, slots_fn=fixed_slots)
    assert rec["would_do"] == [] and {e["reason"] for e in rec["held_template"]} == {"kill_switch"}
    assert replies() == [] and requests == []


def test_the_env_kill_switch_holds_too(store, tmp_env, approvals_file):
    approvals_file.kill_switch(True, via="env")
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(at_day(2, now), now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "held_template" and res["reason"] == "kill_switch"
