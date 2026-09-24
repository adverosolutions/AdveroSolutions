"""Section 1, P2b: a touch that sends new times releases the lead's earlier
registry rows; no free times retries every business day (alert on the 2nd
miss, stop on the 5th); E10 and a "not now" answer enroll the lead in the
90-day nurture; nurture.leave.

Lead data is made up. MODE=shadow from conftest, every client is a mock.
"""
from datetime import datetime

import pytest

from shared.job_log import read_shadow_log
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import cadence
from services.reply_engine import nurture
from services.reply_engine.cadence import LeadState
from services.reply_engine.models import Classification, ReplyEvent
from services.reply_engine.tests import test_core_app as T
from services.reply_engine.tests.test_core_app import env  # noqa: F401 - the app fixture, reused

LEAD = "dana@examplecleaning.test"
CAMPAIGN = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"  # cleaning, reactivation
FREE = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]
EARLIER = ["2026-09-25T13:00:00-05:00", "2026-09-28T14:00:00-05:00"]
OTHER = {"slot": "2026-09-25T15:00:00-05:00", "lead": "someone@else.test", "at": "2026-09-21T10:00:00-05:00",
         "source": "cadence", "day": 3}


def ct(*args):
    return TZ.localize(datetime(*args))


def make_state(**kw):
    base = dict(lead_email=LEAD, campaign_id=CAMPAIGN, status="positive_interested", first_name="Dana",
                company="Brightside Janitorial", eaccount="lorenzo@adveromedia.com", thread_id="thr-e",
                last_email_id="01a0c5aa-0000-7000-8000-0000000000e1", last_subject="Re: Dana, question")
    base.update(kw)
    return LeadState(**base)


def at_day(done, when, **kw):
    state = cadence.arm(make_state(**kw), ct(2026, 9, 18, 16, 0))
    state.cadence["day"] = done
    state.cadence["next_send_at"] = when.isoformat()
    return state


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


@pytest.fixture(autouse=True)
def public_base_url(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)


def seed_earlier(store, state):
    """This lead's earlier offer (the first-reply card's row and a cadence row, one in another case) and
    another lead's row."""
    state.offered_slots = list(EARLIER)
    store.set(cadence.OFFERED_REGISTRY_KEY, [
        {"slot": EARLIER[0], "lead": LEAD, "at": "2026-09-18T16:00:00-05:00", "approval": "apr-1"},
        {"slot": EARLIER[1], "lead": LEAD.upper(), "at": "2026-09-21T10:00:00-05:00", "source": "cadence",
         "day": 5},
        dict(OTHER),
    ])


def quiet(*a, **k):
    return None


# ================================================================ 1. release earlier times
def test_a_touch_with_new_times_releases_only_this_leads_earlier_rows(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(6, now)
    seed_earlier(store, state)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=quiet)
    assert res["action"] == "would_send" and res["day"] == 7 and res["released_slots"] == 2
    rows = store.get(cadence.OFFERED_REGISTRY_KEY)
    mine = sorted(r["slot"] for r in rows if r["lead"].lower() == LEAD)
    assert mine == sorted(res["touch"]["slots"]) and not set(mine) & set(EARLIER)
    assert OTHER in rows  # another lead's row is untouched
    # the lead is still never re-offered the earlier times
    assert set(EARLIER) <= set(state.offered_slots) and len(state.offered_slots) == 4


def test_e2_offers_no_times_and_releases_nothing(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(1, now)
    seed_earlier(store, state)
    before = store.get(cadence.OFFERED_REGISTRY_KEY)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=quiet)
    assert res["action"] == "would_send" and res["day"] == 2 and "released_slots" not in res
    assert store.get(cadence.OFFERED_REGISTRY_KEY) == before


# ================================================================ 2. no free times
def test_no_times_alerts_once_on_the_2nd_miss_and_stops_on_the_5th(store, tmp_env):
    state = at_day(6, ct(2026, 9, 22, 10, 0))
    assert "slot_misses" not in state.cadence  # an old row without the count starts at 0
    pushes = []
    push = lambda *a, **k: pushes.append((a, k))  # noqa: E731
    seen = []
    for when in (ct(2026, 9, 22, 10, 0), ct(2026, 9, 22, 11, 0),   # Tue: miss 1 (twice the same day)
                 ct(2026, 9, 23, 10, 0), ct(2026, 9, 23, 12, 0),   # Wed: miss 2, the alert, said once
                 ct(2026, 9, 24, 10, 0), ct(2026, 9, 25, 10, 0),   # Thu, Fri: misses 3 and 4
                 ct(2026, 9, 26, 10, 0),                           # Sat: not a business day
                 ct(2026, 9, 28, 10, 0)):                          # Mon: miss 5, stopped
        res = cadence.tick_lead(state, when, store=store, free_slots=[], notify_fn=push)
        seen.append((res["action"], res.get("days"), bool(res.get("alerted"))))
    assert seen == [("skipped_no_slots", 1, False), ("skipped_no_slots", 1, False),
                    ("skipped_no_slots", 2, True), ("skipped_no_slots", 2, False),
                    ("skipped_no_slots", 3, False), ("skipped_no_slots", 4, False),
                    ("not_due", None, False), ("stopped", 5, False)]
    assert res["reason"] == "slots_unavailable" and state.cadence["stopped_reason"] == "slots_unavailable"
    assert len(pushes) == 2
    assert "no bookable times" in pushes[0][0][0] and "retries every business day" in pushes[0][0][1]
    assert "Cadence stopped" in pushes[1][0][0]
    for (title, message), kw in pushes:  # counts only on ntfy, whatever leg carries the lead
        if "email_message" in kw:
            assert LEAD not in title and LEAD not in message and "Brightside" not in message
    assert replies() == []


def test_a_send_resets_the_miss_count(store, tmp_env):
    state = at_day(6, ct(2026, 9, 22, 10, 0))
    cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[], notify_fn=quiet)
    assert state.cadence["slot_misses"] == 1
    free = ["2026-09-24T13:00:00-05:00", "2026-09-25T14:00:00-05:00"]
    res = cadence.tick_lead(state, ct(2026, 9, 23, 10, 0), store=store, free_slots=free, notify_fn=quiet)
    assert res["action"] == "would_send" and res["day"] == 7
    assert "slot_misses" not in state.cadence and "slot_miss_on" not in state.cadence


# ================================================================ 3. nurture handoffs
def test_e10_enrolls_the_lead_in_nurture_beside_the_ghl_move(store, tmp_env):
    now = ct(2026, 10, 30, 10, 0)
    state = at_day(9, now)
    free = ["2026-11-02T13:00:00-06:00", "2026-11-03T14:00:00-06:00"]
    res = cadence.tick_lead(state, now, store=store, free_slots=free, notify_fn=quiet)
    assert res["action"] == "would_send" and res["day"] == 10 and "post_errors" not in res
    assert state.cadence["stopped_reason"] == "exhausted"
    assert [r for r in read_shadow_log() if r["action"] == "update_opportunity_stage"]
    rec = nurture.get(LEAD, store)
    assert rec["status"] == "active" and rec["reason"] == "no_reply_after_sequence"
    assert rec["campaign_id"] == CAMPAIGN


def test_a_not_now_answer_enrolls_the_lead_in_nurture(store, tmp_env):
    state = at_day(1, ct(2026, 9, 22, 10, 0), status="negative_notnow", ghl_opportunity_id="opp-1")
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[], notify_fn=quiet)
    assert res["action"] == "follow_up_later" and "post_errors" not in res
    rec = nurture.get(LEAD, store)
    assert rec["status"] == "active" and rec["reason"] == "not_now_reply"


def test_a_not_now_reply_mid_ladder_enrolls_the_lead_in_nurture_once(env, monkeypatch):
    """The real order: the reply's pipeline stops the running ladder as
    inbound_reply before the router sets the not-now status, so the tick
    meets an already-stopped ladder. It still enrolls, once, and not in dry
    run."""
    lead = "sopiosvanishvili@taxfoaccounting.com"
    state, token = T._positive(env)
    assert env["client"].post("/approve/%s" % token).status_code == 200
    key = T.state_key(state)
    assert env["store"].get(key)["cadence"]["armed_at"]
    event = ReplyEvent.from_webhook(T.webhook_payload("rob@cjsglobal.com", "2026-09-15T22:58",
                                                      timestamp="2026-09-21T20:58:00.000Z",
                                                      reply_text="Not right now, maybe next quarter."))
    event.campaign_id, event.lead_email, event.email_id = T.CAMPAIGN, lead, "fresh-notnow"
    real = app_mod.classify

    def classify(ev, *a, **k):
        if ev.email_id == "fresh-notnow":
            return Classification(label="negative_notnow", confidence=0.95, reason="not now")
        return real(ev, *a, **k)
    monkeypatch.setattr(app_mod, "classify", classify)
    app_mod.process_event(event, deps=env["deps"], now=ct(2026, 9, 21, 16, 0))
    raw = env["store"].get(key)
    assert raw["status"] == "follow_up_later" and raw["cadence"]["stopped_reason"] == "inbound_reply"

    def tick(when, dry_run=False):
        st = LeadState(**env["store"].get(key))
        out = cadence.tick_lead(st, when, store=env["store"], free_slots=[], notify_fn=quiet, dry_run=dry_run)
        if not dry_run:
            env["store"].set(key, cadence.state_to_dict(st))
        return out

    assert tick(ct(2026, 9, 22, 9, 0), dry_run=True)["action"] == "awaiting_fresh_draft"
    assert nurture.get(lead, env["store"]) is None
    first = tick(ct(2026, 9, 22, 10, 0))
    assert first["action"] == "awaiting_fresh_draft" and "post_errors" not in first
    rec = nurture.get(lead, env["store"])
    assert rec["status"] == "active" and rec["reason"] == "not_now_reply" and rec["campaign_id"] == T.CAMPAIGN
    later = [tick(ct(2026, 9, 22, 11, 0)), tick(ct(2026, 9, 23, 10, 0))]
    assert [(r["action"], r["reason"]) for r in later] == [("already_stopped", "inbound_reply")] * 2
    assert nurture.get(lead, env["store"]) == rec and len(rec["events"]) == 1


def test_an_enroll_error_neither_crashes_the_tick_nor_stops_the_ghl_move(store, tmp_env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("store down")
    monkeypatch.setattr(nurture, "enroll", boom)
    state = at_day(1, ct(2026, 9, 22, 10, 0), status="negative_notnow", ghl_opportunity_id="opp-1")
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[], notify_fn=quiet)
    assert res["action"] == "follow_up_later" and state.cadence["stopped_reason"] == "follow_up_later"
    assert res["post_errors"] == ["nurture: store down"]
    moves = [r for r in read_shadow_log() if r["action"] == "update_opportunity_stage"]
    assert moves and moves[-1]["payload"]["opportunity_id"] == "opp-1"


# ================================================================ dry run
def test_a_dry_run_releases_counts_and_enrolls_nothing(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(6, now)
    seed_earlier(store, state)
    before = store.get(cadence.OFFERED_REGISTRY_KEY)
    assert cadence.tick_lead(state, now, store=store, free_slots=FREE, dry_run=True)["action"] == "would_send"
    assert cadence.tick_lead(state, now, store=store, free_slots=[], dry_run=True)["action"] == "skipped_no_slots"
    assert store.get(cadence.OFFERED_REGISTRY_KEY) == before and "slot_misses" not in state.cadence
    notnow = at_day(1, now, status="negative_notnow")
    assert cadence.tick_lead(notnow, now, store=store, free_slots=[], dry_run=True)["action"] == "follow_up_later"
    assert nurture.get(LEAD, store) is None


# ================================================================ 4. nurture.leave
def test_leave_marks_an_active_record_left_once(store):
    now = ct(2026, 9, 23, 10, 0)
    nurture.enroll(LEAD, "not_now_reply", now, store, campaign_id=CAMPAIGN)
    rec = nurture.leave(LEAD.upper(), "booked", ct(2026, 9, 24, 11, 0), store)
    assert rec["status"] == "left" and rec["left_reason"] == "booked"
    assert rec["left_at"] == "2026-09-24T11:00:00-05:00"
    assert [e["reason"] for e in rec["events"]] == ["not_now_reply", "booked"]
    assert not nurture.is_enrolled(LEAD, store)
    again = nurture.leave(LEAD, "re_engaged", ct(2026, 9, 25, 11, 0), store)
    assert again == rec == nurture.get(LEAD, store)  # already left: unchanged


def test_leave_without_an_enrollment_returns_none_and_writes_nothing(store):
    assert nurture.leave(LEAD, "re_engaged", ct(2026, 9, 23, 10, 0), store) is None
    assert store.get(nurture.nurture_key(LEAD)) is None
    with pytest.raises(ValueError):
        nurture.leave(LEAD, "bored", ct(2026, 9, 23, 10, 0), store)


def replies():
    return [r for r in read_shadow_log() if r["action"] == "reply_to_email"]
