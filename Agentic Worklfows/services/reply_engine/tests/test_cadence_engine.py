"""Cadence tests (Blueprint S2). Clock injected everywhere; MODE=shadow from conftest."""
import json
from datetime import datetime, timedelta

import httpx
import pytest

from shared import slots as slot_rules
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.job_log import read_shadow_log
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import cadence
from services.reply_engine.cadence import LeadState

NOW = slot_rules.parse_iso("2026-09-21T21:10:00-05:00")  # Monday night
CLEANING_REACT = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
CLEANING_TRIG = "f347604e-48c7-4813-831c-dc7b9d4b50ae"
BOOKKEEPING_REACT = "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"
BOOKKEEPING_TRIG = "87ebb167-9b64-4b6f-b658-88f3d1af9980"
RECRUITING_REACT = "1d4d5bb3-40a7-4333-bf34-b269d2cc9955"
RECRUITING_OUT = "cd2e251c-3b5a-40d2-a3dc-d07c4004a48c"


def ct(*args):
    return TZ.localize(datetime(*args))


def raising_transport():
    def handler(request):
        raise AssertionError("HTTP request attempted in shadow: %s %s" % (request.method, request.url))

    return httpx.MockTransport(handler)


def make_state(email="tiffany@flowerhillfs.com", campaign_id=CLEANING_REACT, **kw):
    base = dict(
        lead_email=email,
        campaign_id=campaign_id,
        status="positive_interested",
        first_name="Tiffany",
        company="Flowerhill Facility Services",
        eaccount="lorenzo@adveromedia.com",
        thread_id="thr-1",
        last_email_id="01a0c5aa-0000-7000-8000-000000000001",
        last_subject="Re: Tiffany, question",
    )
    base.update(kw)
    return LeadState(**base)


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


@pytest.fixture(autouse=True)
def public_base_url(monkeypatch):
    """A deployed engine has a BASE_URL. In live, D1 now refuses to open its
    veto window (or send) without one, so every live test here runs with it
    set; the tests of that hold remove it themselves."""
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)


# ------------------------------------------------------------ day math
def test_arm_friday_afternoon_schedules_d1_monday_10():
    state = make_state()
    friday = ct(2026, 9, 25, 16, 0)
    cadence.arm(state, friday)
    assert state.cadence["day"] == 0
    assert state.cadence["armed_at"] == friday.isoformat()
    nxt = slot_rules.parse_iso(state.cadence["next_send_at"])
    assert nxt.isoformat() == "2026-09-28T10:00:00-05:00"
    assert nxt.strftime("%a") == "Mon"


def test_arm_monday_night_schedules_tuesday():
    state = cadence.arm(make_state(), NOW)
    assert state.cadence["next_send_at"] == "2026-09-22T10:00:00-05:00"


def test_schedule_after_walks_the_week_and_skips_weekends():
    # E5 sent Friday -> E6 Monday; E7 -> E8 two weeks later (rolled to a business day); E8 -> E9 -> E10 weekly
    assert cadence.schedule_after(5, ct(2026, 9, 25, 10, 0)).isoformat() == "2026-09-28T10:00:00-05:00"
    e8 = cadence.schedule_after(7, ct(2026, 9, 26, 10, 0))  # a Saturday send date (should not happen, but roll forward)
    assert e8.weekday() < 5 and e8.isoformat() == "2026-10-12T10:00:00-05:00"
    e9 = cadence.schedule_after(8, e8)
    assert e9.weekday() < 5 and e9 > e8
    e10 = cadence.schedule_after(9, e9)
    assert e10.weekday() < 5 and e10 > e9
    assert cadence.schedule_after(10, e10) is None
    assert cadence.next_day_number(7) == 8 and cadence.next_day_number(9) == 10 and cadence.next_day_number(10) is None
    # the old ladder's days are not in the sequence: nothing follows them
    assert cadence.next_day_number(14) is None and cadence.next_day_number(30) is None


def test_due_only_on_business_days_at_or_after_10_within_send_window():
    state = cadence.arm(make_state(), ct(2026, 9, 25, 16, 0))  # D1 = Mon 28 10:00
    assert not cadence.due(state, ct(2026, 9, 26, 12, 0))  # Saturday
    assert not cadence.due(state, ct(2026, 9, 28, 9, 59))
    assert cadence.due(state, ct(2026, 9, 28, 10, 0))
    assert cadence.due(state, ct(2026, 9, 28, 14, 30))
    assert not cadence.due(state, ct(2026, 9, 28, 19, 0))  # send window closed
    # missed the whole day: next morning it is due again only from 10:00
    assert not cadence.due(state, ct(2026, 9, 29, 7, 30))
    assert cadence.due(state, ct(2026, 9, 29, 10, 0))


def test_send_window_enforced_in_tick(store):
    state = cadence.arm(make_state(), ct(2026, 9, 25, 16, 0))
    late = cadence.tick_lead(state, ct(2026, 9, 28, 19, 5), store=store, free_slots=cadence.default_slot_grid(ct(2026, 9, 28, 19, 5)))
    assert late["action"] == "not_due"
    early = cadence.tick_lead(state, ct(2026, 9, 28, 6, 30), store=store)
    assert early["action"] == "not_due"
    assert state.cadence["touches"] == []


def test_max_one_touch_per_lead_per_day(store):
    state = cadence.arm(make_state(), NOW)
    t1 = ct(2026, 9, 22, 10, 0)
    r1 = cadence.tick_lead(state, t1, store=store, free_slots=cadence.default_slot_grid(t1))
    assert r1["action"] == "would_send" and r1["day"] == 1
    # even though next_send_at is now Wednesday, force the check: a second tick the same day does nothing
    state.cadence["next_send_at"] = t1.isoformat()
    r2 = cadence.tick_lead(state, ct(2026, 9, 22, 15, 0), store=store, free_slots=cadence.default_slot_grid(t1))
    assert r2["action"] == "not_due"
    assert len(state.cadence["touches"]) == 1


# ------------------------------------------------------------ stops
def test_stop_on_inbound_reply_flags_fresh_draft(store):
    state = cadence.arm(make_state(), NOW)
    state.last_inbound_at = "2026-09-22T08:00:00-05:00"  # they replied before D1
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[])
    assert res["action"] == "stopped" and res["reason"] == "inbound_reply"
    assert res["needs_fresh_draft"] is True
    assert state.cadence["stopped_reason"] == "inbound_reply"
    assert state.cadence["needs_fresh_draft"] is True
    assert state.cadence["next_send_at"] is None
    assert not cadence.due(state, ct(2026, 9, 22, 10, 0))


def test_inbound_before_arm_does_not_stop():
    state = make_state(last_inbound_at="2026-09-21T17:37:32-05:00")
    cadence.arm(state, NOW)
    assert cadence.stop_reason(state, ct(2026, 9, 22, 10, 0)) is None


@pytest.mark.parametrize("status,reason", [
    ("call_booked", "booked"),
    ("unsubscribe", "unsubscribe"),
    ("negative_hostile", "hostile"),
])
def test_stop_on_status(status, reason, store):
    state = cadence.arm(make_state(), NOW)
    state.status = status
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=[])
    assert res["action"] == "stopped" and res["reason"] == reason


def test_not_now_moves_to_follow_up_later(store, tmp_env):
    state = cadence.arm(make_state(ghl_opportunity_id="opp-1"), NOW)
    state.status = "negative_notnow"
    ghl = GHL(token="fake-token", transport=raising_transport())
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, ghl=ghl, free_slots=[])
    assert res["action"] == "follow_up_later"
    assert state.cadence["stopped_reason"] == "follow_up_later"
    log = read_shadow_log()
    stage_moves = [r for r in log if r["action"] == "update_opportunity_stage"]
    assert stage_moves and stage_moves[-1]["payload"]["pipelineStageId"] == "ce219fc8-3caa-45e5-bc81-622a1625a23b"
    assert stage_moves[-1]["payload"]["opportunity_id"] == "opp-1"


# ------------------------------------------------------------ slots
def test_no_double_offer_across_two_leads_same_day(store):
    now = ct(2026, 9, 22, 10, 0)
    grid = cadence.default_slot_grid(now)
    a = cadence.arm(make_state(), NOW)
    b = cadence.arm(make_state(email="ilmi@shiningarmorcleaningnj.com", first_name="Ilmi", company="Shining Armor Cleaning NJ"), NOW)
    ra = cadence.tick_lead(a, now, store=store, free_slots=grid)
    rb = cadence.tick_lead(b, now, store=store, free_slots=grid)
    sa, sb = set(ra["touch"]["slots"]), set(rb["touch"]["slots"])
    assert len(sa) == 2 and len(sb) == 2
    assert not (sa & sb), "second lead was offered a slot already offered today"
    assert set(store.get("offered:2026-09-22")) == sa | sb
    assert a.offered_slots == sorted(sa) or set(a.offered_slots) == sa


def test_fresh_slots_exclude_leads_own_previous_offers(store):
    now = ct(2026, 9, 22, 10, 0)
    grid = cadence.default_slot_grid(now)
    state = cadence.arm(make_state(offered_slots=["2026-09-23T12:00:00-05:00", "2026-09-24T12:00:00-05:00"]), NOW)
    two = cadence.fresh_slots(state, now, grid, store)
    isos = {s.isoformat() for s in two}
    assert "2026-09-23T12:00:00-05:00" not in isos and "2026-09-24T12:00:00-05:00" not in isos
    for s in two:
        assert 12 <= s.hour < 18 and s.weekday() < 5 and s >= now + timedelta(hours=4)


def test_default_grid_respects_window_and_horizon():
    grid = [slot_rules.parse_iso(s) for s in cadence.default_slot_grid(NOW)]
    assert grid, "grid empty"
    assert all(s.weekday() < 5 for s in grid)
    assert all(12 <= s.hour < 18 for s in grid)
    # the grid starts today: candidate_slots applies the 4-hour rule, so today's
    # still-compliant afternoon is offerable instead of being skipped to tomorrow
    assert min(grid).date() == datetime(2026, 9, 21).date()
    morning = ct(2026, 9, 22, 10, 0)
    today_cands = [s for s in slot_rules.candidate_slots(cadence.default_slot_grid(morning), morning)
                   if s.date() == morning.date()]
    assert today_cands and min(today_cands) >= morning + timedelta(hours=4)


def test_parse_free_slots_ghl_shape():
    resp = {"2026-09-22": {"slots": ["2026-09-22T12:00:00-05:00", "2026-09-22T12:30:00-05:00"]}, "traceId": "x"}
    assert cadence.parse_free_slots(resp) == ["2026-09-22T12:00:00-05:00", "2026-09-22T12:30:00-05:00"]
    assert cadence.parse_free_slots({"_dates_": resp}) == ["2026-09-22T12:00:00-05:00", "2026-09-22T12:30:00-05:00"]
    assert cadence.parse_free_slots(None) == []


def test_resolve_free_slots_uses_ghl_when_token_present():
    def handler(request):
        assert request.method == "GET" and "/free-slots" in str(request.url)
        return httpx.Response(200, json={"2026-09-23": {"slots": ["2026-09-23T13:00:00-05:00"]}})

    ghl = GHL(token="fake-token", transport=httpx.MockTransport(handler))
    free, source = cadence.resolve_free_slots(ghl, NOW)
    assert source == "ghl" and free == ["2026-09-23T13:00:00-05:00"]
    free2, source2 = cadence.resolve_free_slots(GHL(token=None, transport=raising_transport()), NOW)
    assert source2 == "default_grid" and free2


# ------------------------------------------------------------ copy
SLOTS = ["2026-09-23T14:00:00-05:00", "2026-09-24T15:30:00-05:00"]


@pytest.mark.parametrize("day", list(range(1, 11)))
def test_build_touch_every_day_is_clean(day):
    touch = cadence.build_touch(make_state(), day, SLOTS)
    assert touch.subject == "Re: Tiffany, question"
    assert touch.body_text.startswith("Hey Tiffany,")
    assert touch.problems == [], (day, touch.problems, touch.body_text)
    assert touch.intent == cadence.INTENTS[day]
    if day == 2:
        assert touch.slots == [] and "Wed 2:00pm" not in touch.body_text
    else:
        assert touch.slots == SLOTS
        assert "Wed 2:00pm or Thu 3:30pm CT" in touch.body_text
    # no booking link in any follow-up (Lorenzo, 2026-09-23)
    assert cadence.DEFAULT_BOOKING_URL not in touch.body_text and "http" not in touch.body_text


def test_day_intents_exact_wording():
    assert "The time slots I sent got filled. Here are 2 more, let me know if they work: Wed 2:00pm or Thu 3:30pm CT." \
        in cadence.build_touch(make_state(), 1, SLOTS).body_text
    assert "Those last two times got taken too.\n\nWould Wed 2:00pm or Thu 3:30pm CT work instead?" in \
        cadence.build_touch(make_state(), 3, SLOTS).body_text
    assert "Should I keep trying to find a time, or is now just not the right moment?" in \
        cadence.build_touch(make_state(), 7, SLOTS).body_text


def test_d2_research_line_from_llm_fake_and_override():
    t = cadence.build_touch(make_state(), 2, SLOTS, research_mode="llm")
    assert t.meta["research_line"] and t.meta["research_line"] in t.body_text
    t2 = cadence.build_touch(make_state(), 2, SLOTS, research_line="Saw the 4.9 stars across 300 reviews, that list is worth a second pass!")
    assert "!" not in t2.body_text and "4.9 stars" in t2.body_text


def test_e4_proof_matches_offer_type():
    react = cadence.build_touch(make_state(campaign_id=CLEANING_REACT), 4, SLOTS)
    assert "$6M" in react.body_text and "6 months" in react.body_text
    assert "$180,000" not in react.body_text
    out = cadence.build_touch(make_state(campaign_id=CLEANING_TRIG), 4, SLOTS)
    assert "$180,000" in out.body_text and "90 days" in out.body_text
    assert "$6M" not in out.body_text


def test_e6_preview_matches_the_offers_md_mechanism():
    """Every campaign's E6 preview names the mechanism config/offers.md defines
    for that offer, and none of the other offer's ("never mixed")."""
    # offers.md: cleaning_trigger watches "new leases, office expansions, PM changes"
    clean_trigger = cadence.build_touch(make_state(campaign_id=CLEANING_TRIG), 6, SLOTS).body_text
    assert "office leases" in clean_trigger and "property managers" in clean_trigger
    assert "cancelled or never signed" not in clean_trigger
    # offers.md: bookkeeping_trigger watches "new business formations, part-time bookkeeper posts"
    assert "part-time bookkeeper" in cadence.build_touch(make_state(campaign_id=BOOKKEEPING_TRIG, company="Taxfo"),
                                                         6, SLOTS).body_text
    # offers.md: recruiting_outbound watches roles opening on job boards
    assert "job boards" in cadence.build_touch(make_state(campaign_id=RECRUITING_OUT), 6, SLOTS).body_text


def test_e6_preview_matches_offer_type_not_just_niche():
    # reactivation prospects are working their own dormant list: no trigger watching
    book = cadence.build_touch(make_state(campaign_id=BOOKKEEPING_REACT, company="Taxfo"), 6, SLOTS).body_text
    assert "newly registered" not in book and "part-time bookkeeper" not in book
    assert "former clients and old inquiries" in book
    rec = cadence.build_touch(make_state(campaign_id=RECRUITING_REACT, company="Hire Co"), 6, SLOTS).body_text
    assert "job boards" not in rec and "clients who've gone quiet" in rec
    clean = cadence.build_touch(make_state(campaign_id=CLEANING_REACT), 6, SLOTS).body_text
    assert "office leases" not in clean and "cancelled or never signed" in clean


def test_e6_is_a_plain_email_with_no_calendar_hold(store, tmp_env):
    """The D6 calendar hold is gone: E6 is a plain email like the rest. No
    hold, no calendar write, no approval flag, and the day goes out."""
    state = cadence.arm(make_state(ghl_contact_id="tE3tyj5iIAXfBpD52rFM"), NOW)
    state.cadence["day"] = 5
    now = ct(2026, 9, 28, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "would_send" and res["day"] == 6
    assert "hold" not in res["touch"]["body_text"].lower()
    assert "requires_approval" not in res["touch"] and "channel_note" not in res["touch"]
    assert not any(r.get("action") == "create_appointment" for r in res["records"])
    assert [r for r in read_shadow_log() if r["action"] == "create_appointment"] == []


@pytest.mark.usefixtures("e1_veto_on")  # the E1 Veto window, off since 2026-10-06
def test_d1_live_opens_veto_window_then_sends_via_mock(store, live_mode, tmp_env):
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url), json.loads(request.content or b"{}")))
        if request.method == "GET":  # the recipient re-read must CONFIRM the lead (decision R6)
            return httpx.Response(200, json={"id": "e-1", "from_address_email": "tiffany@flowerhillfs.com"})
        return httpx.Response(200, json={"id": "sent-1"})

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    pings = []
    at_930 = ct(2026, 9, 22, 9, 30)
    res = cadence.tick_lead(state, at_930, store=store, instantly=inst, free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "veto_window_opened" and pings and "Veto" in pings[0][1]["actions"][0][0]
    assert calls == []
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, instantly=inst,
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"], notify_fn=lambda *a, **k: None)
    assert res["action"] == "sent"
    # one read (does this thread still belong to the lead?) then the reply
    assert [m for m, _, _ in calls] == ["GET", "POST"]
    calls = [c for c in calls if c[0] == "POST"]
    method, url, body = calls[0]
    assert method == "POST" and url.endswith("/emails/reply")
    assert body["reply_to_uuid"] == "01a0c5aa-0000-7000-8000-000000000001" and body["eaccount"] == "lorenzo@adveromedia.com"
    assert body["to"] == "tiffany@flowerhillfs.com"
    assert "The time slots I sent got filled. Here are 2 more" in body["body"]["text"]
    assert state.cadence["touches"][-1]["kind"] == "done"


def test_d1_vetoed_stops(store, live_mode, tmp_env):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    cadence.record_veto(store, state, ct(2026, 9, 22, 9, 40))
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=["2026-09-23T13:00:00-05:00"], notify_fn=lambda *a, **k: None)
    assert res["action"] == "vetoed" and state.cadence["stopped_reason"] == "vetoed"


# ------------------------------------------------------------ shadow: zero HTTP
def test_zero_http_in_shadow_full_week(store, tmp_env):
    inst = Instantly(api_key="x", transport=raising_transport())
    ghl = GHL(token="fake-token", transport=raising_transport())
    state = cadence.arm(make_state(), ct(2026, 9, 18, 16, 0))  # Friday -> D1 Monday 21st
    day = ct(2026, 9, 21, 10, 0)
    seen_days = []
    for _ in range(10):
        free = cadence.default_slot_grid(day)
        res = cadence.tick_lead(state, day, store=store, instantly=inst, ghl=ghl, free_slots=free)
        if res["action"] == "would_send":
            seen_days.append(res["day"])
            assert res["touch"]["problems"] == [] if "problems" in res["touch"] else True
        day = slot_rules.parse_iso(state.cadence["next_send_at"]) if state.cadence.get("next_send_at") else day + timedelta(days=1)
        if state.cadence.get("stopped_reason"):
            break
    assert seen_days == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert state.cadence["stopped_reason"] == "exhausted"
    log = read_shadow_log()
    replies = [r for r in log if r["system"] == "instantly" and r["action"] == "reply_to_email"]
    assert len(replies) == 10
    assert all(r["payload"]["eaccount"] == "lorenzo@adveromedia.com" for r in replies)
    # each touch that offered times used two never-before-offered slots
    offered = [tuple(t["slots"]) for t in state.cadence["touches"] if t["slots"]]
    flat = [s for pair in offered for s in pair]
    assert len(flat) == len(set(flat)) == 18  # nine emails with two times each; E2 has none


def test_state_roundtrip_through_store(store):
    state = cadence.arm(make_state(), NOW)
    store.set(state.key, cadence.state_to_dict(state))
    back = cadence.state_from_dict(store.get(state.key))
    assert back.cadence["next_send_at"] == state.cadence["next_send_at"]
    assert back.lead_email == state.lead_email


# --------------------------------------------------- recipient safety (to=)
@pytest.mark.parametrize("day", list(range(1, 11)))
def test_cadence_send_passes_to_for_recipient_validation(day, store, live_mode, tmp_env, monkeypatch):
    """Instantly validates `to` against the thread before sending. Ten emails
    go out with no human in the loop, so every one of them carries it."""
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content or b"{}"))
        if request.method == "GET":  # the recipient re-read must CONFIRM the lead (decision R6)
            return httpx.Response(200, json={"id": "e-1", "from_address_email": "tiffany@flowerhillfs.com"})
        return httpx.Response(200, json={"id": "sent-%d" % day})

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    state = cadence.arm(make_state(ghl_contact_id="tE3tyj5iIAXfBpD52rFM"), ct(2026, 9, 21, 16, 0))
    state.cadence["day"] = [d for d in (0,) + cadence.DAY_SEQUENCE if d < day][-1]
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    res = cadence.tick_lead(state, now, store=store, instantly=inst,
                            ghl=GHL(token="fake-token", transport=httpx.MockTransport(
                                lambda r: httpx.Response(200, json={"id": "appt-1"}))),
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "sent" and res["day"] == day
    sent = [b for b in bodies if "reply_to_uuid" in b]
    assert len(sent) == 1
    assert sent[0]["to"] == "tiffany@flowerhillfs.com"
    assert "skip_validation" not in sent[0]


def test_cadence_send_records_the_recipient_in_the_shadow_payload(store, tmp_env):
    state = cadence.arm(make_state(), NOW)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "would_send"
    replies = [r for r in read_shadow_log() if r["action"] == "reply_to_email"]
    assert replies and replies[-1]["payload"]["to"] == "tiffany@flowerhillfs.com"


# ------------------------------------------------------- copy gate / failures
def test_touch_with_copy_problems_is_not_sent(store, tmp_env, monkeypatch):
    """An E2 research line that breaks the copy rules must never reach a lead:
    approval.send_approved blocks on draft.problems and the unattended path
    applies the same bar. (P4: "llm" mode ends in the fallback line in tests,
    so the bad line rides in as that line.)"""
    from shared import llm

    monkeypatch.setattr(cadence, "fallback_research_line", lambda company, offer: (
        "I saw your team still books jobs by hand, so the bot I built for a similar shop "
        "should recover $50,000 in contracts"))
    try:
        state = cadence.arm(make_state(), NOW)
        state.cadence["day"] = 1
        now = ct(2026, 9, 22, 10, 0)
        state.cadence["next_send_at"] = now.isoformat()
        pings = []
        res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                notify_fn=lambda *a, **k: pings.append((a, k)), research_mode="llm")
        assert res["action"] == "blocked_copy" and res["day"] == 2
        assert "mentions_ai_or_automation" in res["problems"]
        assert "money_not_in_offer_sheet" in res["problems"]
        assert [r for r in read_shadow_log() if r["action"] == "reply_to_email"] == []
        assert state.cadence["day"] == 1 and state.cadence["touches"] == []
        assert pings and pings[0][1]["priority"] == "high"
    finally:
        llm.clear_fakes()


def test_copy_problems_catches_capitalised_automation_and_invented_money():
    # "automation" is allowed since the AI agents offer (2026-10-06); a capitalised bot is not
    assert "mentions_ai_or_automation" in cadence.copy_problems("The Bot runs itself\n\nLorenzo")
    assert "money_not_in_offer_sheet" in cadence.copy_problems("I can guarantee $50,000 back\n\nLorenzo")
    # the offer sheet's own proof numbers are fine
    assert cadence.copy_problems("I recovered about $6M worth of contracts\n\nLorenzo") == []


def test_render_flags_a_missing_placeholder_instead_of_emptying_the_sentence():
    body = cadence.render("e1", first_name="Ann")
    assert "{slots}" in body
    assert "unfilled_placeholder" in cadence.copy_problems(body)


def test_live_send_without_thread_ids_does_not_advance_the_day(store, live_mode, tmp_env):
    """A state that lost its eaccount used to burn the whole ladder in silence."""
    state = cadence.arm(make_state(eaccount=None), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    res = cadence.tick_lead(state, now, store=store, instantly=Instantly(api_key="x", transport=raising_transport()),
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "send_failed" and res["reason"] == "missing_thread_ids"
    assert state.cadence["day"] == 0 and state.cadence["touches"] == []
    assert state.offered_slots == []
    assert "D1 -> tiffany@flowerhillfs.com: NOT SENT" in cadence.summarize_touch(res)


def test_a_crash_after_the_send_does_not_send_the_day_twice(store, tmp_env):
    """The marker is written before the send: a tick that dies before the store
    write is repaired, never replayed."""
    state = cadence.arm(make_state(), NOW)
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "would_send"
    marker = store.get(cadence.touch_marker_key(state, 1))
    assert marker and marker["sent"] is True
    # replay the tick against the pre-tick snapshot (what a dead process leaves behind)
    stale = cadence.arm(make_state(), NOW)
    again = cadence.tick_lead(stale, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert again["action"] == "already_sent"
    assert stale.cadence["day"] == 1 and stale.cadence["next_send_at"] == "2026-09-23T10:00:00-05:00"
    assert len([r for r in read_shadow_log() if r["action"] == "reply_to_email"]) == 1


# ------------------------------------------------------------ state lifecycle
def test_rearm_after_inbound_reply_resumes_at_the_next_day(store):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    day = ct(2026, 9, 22, 10, 0)
    for _ in range(4):
        cadence.tick_lead(state, day, store=store, free_slots=cadence.default_slot_grid(day))
        day = slot_rules.parse_iso(state.cadence["next_send_at"])
    assert state.cadence["day"] == 4
    cadence.stop(state, "inbound_reply", day)
    cadence.arm(state, day, store=store)  # what approval._arm_cadence does after the fresh answer
    assert state.cadence["day"] == 4 and cadence.pending_day(state) == 5
    res = cadence.tick_lead(state, slot_rules.parse_iso(state.cadence["next_send_at"]), store=store,
                            free_slots=cadence.default_slot_grid(day))
    assert res["day"] == 5
    intents = [t["intent"] for t in state.cadence["touches"]]
    assert len(intents) == len(set(intents)), intents
    assert "The time slots I sent got filled" not in res["touch"]["body_text"]


def test_arm_with_restart_starts_the_ladder_again():
    state = cadence.arm(make_state(), NOW)
    state.cadence["day"] = 4
    cadence.arm(state, ct(2026, 9, 22, 10, 0), restart=True)
    assert state.cadence["day"] == 0 and cadence.pending_day(state) == 1


def test_veto_does_not_survive_a_rearm(store, live_mode, tmp_env):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    cadence.record_veto(store, state, ct(2026, 9, 22, 9, 40))
    assert cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, free_slots=["2026-09-23T13:00:00-05:00"],
                             notify_fn=lambda *a, **k: None)["action"] == "vetoed"
    # the lead re-engages a fortnight later and Lorenzo approves a fresh reply
    later = ct(2026, 10, 5, 9, 0)
    cadence.arm(state, later, store=store)
    assert store.get(cadence.veto_key(state)) is None
    state.cadence["veto_notified_at"] = "2026-10-06T09:30:00-05:00"
    res = cadence.tick_lead(state, ct(2026, 10, 6, 10, 0), store=store,
                            instantly=None,
                            free_slots=["2026-10-07T13:00:00-05:00", "2026-10-08T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: None)
    assert res["action"] != "vetoed"


def test_decision_urls_carry_a_signed_token(monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "s3cret")
    state = cadence.arm(make_state(), NOW)
    url = cadence._decision_url("veto", state, NOW)
    assert "?t=" in url
    token = url.split("?t=")[1]
    from urllib.parse import unquote

    token = unquote(token)
    assert cadence.verify_decision_token("veto", state, token, NOW) is True
    # another lead's card cannot be replayed against this one
    other = cadence.arm(make_state(email="ilmi@shiningarmorcleaningnj.com"), NOW)
    assert cadence.verify_decision_token("veto", other, token, NOW) is False
    assert cadence.verify_decision_token("approve", state, token, NOW) is False
    assert cadence.verify_decision_token("veto", state, token, NOW + timedelta(hours=49)) is False
    assert cadence.verify_decision_token("veto", state, "garbage", NOW) is False


def test_a_forged_decision_is_ignored_by_the_tick(store, live_mode, tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "s3cret")
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    cadence.record_veto(store, state, ct(2026, 9, 22, 9, 40), token="2026-09-24T09:40:00-05:00.deadbeef")
    assert store.get(cadence.veto_key(state))["token_ok"] is False
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store,
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: None)
    assert res["action"] != "vetoed"
    # Lorenzo's own tap, with the token the card carried, still holds the touch
    state2 = cadence.arm(make_state(email="rob@example.com"), ct(2026, 9, 21, 16, 0))
    state2.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    good = cadence.make_decision_token("veto", state2, ct(2026, 9, 22, 9, 35))
    cadence.record_veto(store, state2, ct(2026, 9, 22, 9, 40), token=good)
    assert cadence.tick_lead(state2, ct(2026, 9, 22, 10, 0), store=store, free_slots=["2026-09-23T13:00:00-05:00"],
                             notify_fn=lambda *a, **k: None)["action"] == "vetoed"


def test_an_auto_responder_pauses_the_cadence_instead_of_killing_it(store):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    # what app.py + router.py leave behind for an out-of-office reply: its
    # history entry (the label the pause is decided from), the stop, the
    # router's pause fields and status
    state.last_inbound_at = "2026-09-22T08:00:00-05:00"
    state.history.append({"at": "2026-09-22T08:00:30-05:00", "event": "inbound", "email_id": "ooo-1",
                          "label": "ooo", "source": "webhook"})
    state.processed_email_ids.append("ooo-1")
    cadence.stop(state, "inbound_reply", ct(2026, 9, 22, 8, 0))
    state.cadence = dict(state.cadence, paused=True, resume_at="2026-10-05", reason="ooo")
    state.status = "ooo"
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store)
    assert res["action"] == "resumed_after_auto_reply"
    assert state.cadence["stopped_reason"] is None
    assert state.cadence["next_send_at"] == "2026-10-05T10:00:00-05:00"
    assert state.cadence["day"] == 0 and cadence.pending_day(state) == 1
    # the baseline is the auto-reply's own received time, not the tick's clock,
    # and the auto-reply's reason goes with the pause
    assert state.cadence["resumed_after_auto_reply_at"] == "2026-09-22T08:00:00-05:00"
    assert "reason" not in state.cadence
    # and the same auto-reply does not stop it again on the next tick
    assert cadence.tick_lead(state, ct(2026, 9, 23, 10, 0), store=store)["action"] == "not_due"
    # a real human reply after the resume still stops it
    state.last_inbound_at = "2026-09-24T09:00:00-05:00"
    assert cadence.tick_lead(state, ct(2026, 9, 24, 10, 0), store=store)["action"] == "stopped"


def test_a_human_reply_is_reported_once_then_stays_quiet(store):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.last_inbound_at = "2026-09-22T08:00:00-05:00"
    cadence.stop(state, "inbound_reply", ct(2026, 9, 22, 8, 0))
    first = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store)
    assert first["action"] == "awaiting_fresh_draft"
    assert cadence.tick_lead(state, ct(2026, 9, 22, 11, 0), store=store)["action"] == "already_stopped"


def test_no_double_offer_across_two_leads_on_different_days(store):
    """The reservation is keyed on the slot, not on the day the offer was made."""
    mon = ct(2026, 9, 22, 10, 0)
    tue = ct(2026, 9, 23, 10, 0)
    a = cadence.arm(make_state(), NOW)
    b = cadence.arm(make_state(email="ilmi@shiningarmorcleaningnj.com", first_name="Ilmi"), NOW)
    ra = cadence.tick_lead(a, mon, store=store, free_slots=cadence.default_slot_grid(mon))
    rb = cadence.tick_lead(b, tue, store=store, free_slots=cadence.default_slot_grid(tue))
    sa, sb = set(ra["touch"]["slots"]), set(rb["touch"]["slots"])
    assert len(sa) == 2 and len(sb) == 2
    assert not (sa & sb), "the same slot was offered to two leads on two days"
    # every offer still ahead of us is held; Monday's own 14:00 has expired by Tuesday
    outstanding = set(cadence.outstanding_offers(store, tue))
    assert {s for s in sa | sb if slot_rules.parse_iso(s) >= tue} <= outstanding
    assert sb <= outstanding


def test_live_send_refuses_when_the_thread_belongs_to_somebody_else(store, live_mode, tmp_env):
    """config/instantly_api_contract.md asks for this compensating control: the
    last inbound on the thread is re-read and must be from the lead we mean to
    answer. Ilmi's reply came from info@shiningarmorcleaningnj.com while the
    lead record is ilmi@ (fixture #1/#12)."""
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        if request.method == "GET":
            return httpx.Response(200, json={"id": "e-1", "from_address_email": "info@shiningarmorcleaningnj.com"})
        raise AssertionError("sent to the wrong recipient: %s" % request.url)

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    state = cadence.arm(make_state(email="ilmi@shiningarmorcleaningnj.com", first_name="Ilmi"), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    res = cadence.tick_lead(state, now, store=store, instantly=inst,
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "send_failed" and res["reason"] == "recipient_mismatch"
    assert state.cadence["day"] == 0 and state.cadence["touches"] == []
    assert all(m == "GET" for m, _ in calls)


def test_an_unconfirmed_attempt_holds_the_day_instead_of_sending_twice(store, tmp_env):
    """The process died with the POST in flight: the marker says "started, not
    confirmed". Retrying inside the same day could put two identical emails in
    the thread, so the day is held and reported."""
    state = cadence.arm(make_state(), NOW)
    now = ct(2026, 9, 22, 10, 0)
    store.set(cadence.touch_marker_key(state, 1), {"ts": now.isoformat(), "day": 1, "sent": False})
    res = cadence.tick_lead(state, ct(2026, 9, 22, 11, 0), store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "send_failed" and res["reason"] == "previous_attempt_unconfirmed"
    assert state.cadence["day"] == 0 and read_shadow_log() == []
    # the next business day it is retried
    later = ct(2026, 9, 23, 10, 0)
    state.cadence["next_send_at"] = later.isoformat()
    assert cadence.tick_lead(state, later, store=store, free_slots=cadence.default_slot_grid(later))["action"] == "would_send"


# ----------------------------------------- regressions found by the A2 review
def test_arm_on_a_weekend_schedules_monday_ten():
    """next_business_day_send's roll_to_business_day loop was only covered for
    Friday afternoon; arming happens whenever Lorenzo approves a reply."""
    for when in (ct(2026, 9, 26, 11, 0), ct(2026, 9, 27, 11, 0)):  # Sat, Sun
        state = cadence.arm(make_state(), when)
        assert state.cadence["next_send_at"] == "2026-09-28T10:00:00-05:00", when
    # and a Saturday night arm does not roll into the following week
    assert cadence.arm(make_state(), ct(2026, 9, 26, 23, 30)).cadence["next_send_at"] == "2026-09-28T10:00:00-05:00"


@pytest.mark.parametrize("subject", [
    "Automatic reply: Tiffany, question",
    "Out of Office Re: Ashley, question",
    "Thank you for your e-mail Re: Amanda, question",
    "This email is no longer monitored Re: Eva, question",
    "Thank you for contacting SD Clean Co. Re: Conner, question",
    "I'm currently out of the office.",
])
def test_subject_never_repeats_an_auto_reply_prefix_back_to_the_prospect(subject):
    """app.py stores last_subject on EVERY inbound, including auto-responders,
    and resume_after_auto_reply exists precisely to keep the ladder alive on
    that path. Without stripping, the normal outcome for an out-of-office lead
    was a touch titled "Re: Automatic reply: Tiffany, question", which tells the
    prospect in the subject line that a machine is answering their machine."""
    out = cadence.subject_for(make_state(last_subject=subject))
    lowered = out.lower()
    for banned in ("automatic reply", "out of office", "no longer monitored", "thank you for your e-mail",
                   "thank you for contacting", "auto reply"):
        assert banned not in lowered, (subject, out)
    assert out.startswith("Re: ") and out.count("Re: ") == 1


def test_cadence_and_first_reply_use_the_same_subject():
    """The approved first reply and every cadence touch must stay on one thread
    subject; subject_for used to keep an "EXT:" prefix draft.reply_subject strips."""
    from services.reply_engine.draft import reply_subject

    for raw in ("Re: Tiffany, question", "Re: EXT: Chris, question", "[EXTERNAL] Re: Sopio, question",
                "Fwd: Re: Dana, question", "Ilmi, question"):
        assert cadence.subject_for(make_state(last_subject=raw)) == reply_subject(raw), raw


def test_copy_gate_catches_percentages_guarantees_and_dotted_ai():
    """copy_problems only guarded dollar figures, so percentage pricing, bare
    guarantee claims, "A.I." and "bots" all passed the gate nine unattended
    touches ride on. offers.md prices reactivation at 20-30%."""
    def flagged(text):
        return cadence.copy_problems(text + "\n\nLorenzo")

    assert "percentage_not_in_offer_sheet" in flagged("I take 45% of first-year fees on anyone I bring back")
    assert "unverified_guarantee" in flagged("I guarantee you 50 new cleaning contracts in 90 days")
    assert "unverified_guarantee" in flagged("Guaranteed $24,000/yr in new cleaning contracts within 90 days")
    assert "money_not_in_offer_sheet" in flagged("We can do this for $3,750 a month")
    assert "mentions_ai_or_automation" not in flagged("I'll have the A.I. draft it")  # allowed since 2026-10-06
    assert "mentions_ai_or_automation" in flagged("Our bots handle the outreach")
    assert "mentions_ai_or_automation" in flagged("A chatbot could do the first pass")
    # the offer sheet's own numbers still pass
    assert cadence.copy_problems("I recovered about $6M worth of contracts\n\nLorenzo") == []
    assert "percentage_not_in_offer_sheet" not in flagged("Commission is 20-30% of first-year contract value")


def test_a_leads_own_name_does_not_trip_the_copy_gate():
    """A prospect called "Automation Depot" is not a copy failure. Blocking on
    it lost that lead D2 onwards and re-pinged Lorenzo every hour."""
    # ("automation" is allowed since 2026-10-06; a bot is still banned, so the case is a "Bot" name)
    touch = cadence.build_touch(make_state(company="Bot Depot", first_name="Dana"), 4, SLOTS)
    assert "Bot Depot" in touch.body_text
    assert touch.problems == []
    # but the same word in the prose is still caught
    assert "mentions_ai_or_automation" in cadence.copy_problems(
        touch.body_text.replace("Lorenzo", "The bot runs itself\n\nLorenzo"), allow=touch.allow_terms)


def test_blocked_copy_is_reported_once_per_day(store, tmp_env, monkeypatch):
    """The blocked day never advances, so it was retried on every hourly tick:
    one high-priority push and one fresh paid research line each time.
    (P4: the bad line rides in as E2's fallback line; a repeat tick must not
    rebuild the touch at all.)"""
    from shared import llm

    calls = {"research": 0}
    try:
        state = cadence.arm(make_state(), NOW)
        pings = []

        def counting(*a, **k):
            calls["research"] += 1
            return "Our bots recovered $50,000 for a similar shop"

        monkeypatch.setattr(cadence, "fallback_research_line", counting)
        built = []
        state.cadence["day"] = 1
        for hour in (10, 11, 12, 13):
            now = ct(2026, 9, 22, hour, 0)
            state.cadence["next_send_at"] = ct(2026, 9, 22, 10, 0).isoformat()
            res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                    notify_fn=lambda *a, **k: pings.append((a, k)), research_mode="llm")
            assert res["action"] == "blocked_copy", (hour, res["action"])
            built.append(calls["research"])
        assert len(pings) == 1, pings
        assert built[0] >= 1 and built == [built[0]] * 4, "the E2 touch was rebuilt on a repeat tick"
        assert state.cadence["day"] == 1 and state.cadence["touches"] == []
        assert [r for r in read_shadow_log() if r["action"] == "reply_to_email"] == []
    finally:
        llm.clear_fakes()


def test_blocked_copy_three_days_running_stops_instead_of_stalling(store, tmp_env, monkeypatch):
    from shared import llm

    monkeypatch.setattr(cadence, "fallback_research_line",
                        lambda company, offer: "Our bots recovered $50,000 for a similar shop")
    try:
        state = cadence.arm(make_state(), NOW)
        state.cadence["day"] = 1
        pings = []
        actions = []
        for day in (22, 23, 24):
            now = ct(2026, 9, day, 10, 0)
            state.cadence["next_send_at"] = now.isoformat()
            actions.append(cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                             notify_fn=lambda *a, **k: pings.append((a, k)),
                                             research_mode="llm")["action"])
        assert actions == ["blocked_copy", "blocked_copy", "blocked_copy_stalled"]
        assert state.cadence["stopped_reason"] == "blocked_copy"
        assert len(pings) == 3
    finally:
        llm.clear_fakes()


def test_two_auto_replies_in_a_row_do_not_kill_the_cadence(store):
    """An auto-responder answers every message in a thread, so the SECOND robot
    reply is as much a pause as the first. Treating resumed_after_auto_reply_at
    as a permanent one-shot parked the lead in needs_fresh_draft for ever,
    waiting on a human draft a robot can never produce."""
    from datetime import date as _date

    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    resumes = 0
    d = _date(2026, 9, 22)
    while d < _date(2026, 10, 31):
        if d.weekday() < 5:
            now = ct(d.year, d.month, d.day, 10, 0)
            res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                    notify_fn=lambda *a, **k: None)
            if res["action"] == "would_send":
                # the same auto-responder answers this touch too, and the
                # pipeline records it (label ooo) and stops the ladder
                state.last_inbound_at = ct(d.year, d.month, d.day, 10, 5).isoformat()
                state.history.append({"at": ct(d.year, d.month, d.day, 10, 5).isoformat(), "event": "inbound",
                                      "email_id": "ooo-%s" % d.isoformat(), "label": "ooo"})
                cadence.stop(state, "inbound_reply", ct(d.year, d.month, d.day, 10, 5))
            elif res["action"] == "resumed_after_auto_reply":
                resumes += 1
            assert res["action"] != "awaiting_fresh_draft", (d, "parked waiting on a draft a robot cannot produce")
        d = d + timedelta(days=1)
    touches = [t["day"] for t in state.cadence["touches"]]
    assert touches[:7] == [1, 2, 3, 4, 5, 6, 7], touches
    assert resumes >= 7, "the second auto-reply was not treated as a pause"


def test_an_unsigned_veto_is_refused_once_a_secret_is_configured(store, live_mode, tmp_env, monkeypatch):
    """The /cadence/{kind}/{campaign}/{email} path is entirely in the URL and
    these URLs are broadcast on a public ntfy topic, so a bare GET used to stop
    a positive lead's whole ladder."""
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "s3cret")
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    rec = cadence.record_veto(store, state, ct(2026, 9, 22, 9, 40))  # no token at all
    assert rec["token_ok"] is False
    assert cadence.decision_is_current(rec, state) is False
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store,
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: None)
    assert res["action"] != "vetoed"
    assert state.cadence.get("stopped_reason") != "vetoed"
    # with no secret configured at all, an unsigned tap is still honoured
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    assert cadence.verify_decision_token("veto", state, None, NOW) is None
    assert cadence.decision_is_current(cadence.record_veto(store, state, ct(2026, 9, 22, 9, 41)), state) is True


@pytest.mark.usefixtures("e1_veto_on")  # the E1 Veto window, off since 2026-10-06
def test_d1_veto_window_does_not_open_when_the_veto_link_was_withheld(store, live_mode, tmp_env):
    """shared.notify strips action buttons from an unauthenticated topic and the
    email fallback never rendered them, so the only human hold on the live D1
    auto-send was undeliverable and the send proceeded anyway."""
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    withheld = {"sent": True, "ntfy": {"ok": True, "headers": {"Title": "x"}}, "email": False}
    res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                            notify_fn=lambda *a, **k: withheld)
    assert res["action"] == "veto_undeliverable"
    assert state.cadence["veto_notified_at"] is None
    assert [r for r in read_shadow_log() if r["action"] == "reply_to_email"] == []
    # and it is said once, not on every tick
    again = cadence.tick_lead(state, ct(2026, 9, 22, 11, 0), store=store,
                              free_slots=cadence.default_slot_grid(now),
                              notify_fn=lambda *a, **k: pytest.fail("re-notified"))
    assert again["action"] == "veto_undeliverable" and again["quiet"] is True
    # a push that did carry the buttons opens the window as before
    ok = cadence.arm(make_state(email="ilmi@shiningarmorcleaningnj.com"), ct(2026, 9, 21, 16, 0))
    ok.cadence["next_send_at"] = now.isoformat()
    delivered = {"sent": True, "ntfy": {"ok": True, "headers": {"Actions": "view, Veto, https://x"}}, "email": False}
    assert cadence.tick_lead(ok, now, store=store, free_slots=cadence.default_slot_grid(now),
                             notify_fn=lambda *a, **k: delivered)["action"] == "veto_window_opened"


@pytest.mark.usefixtures("e1_veto_on")  # the E1 Veto window, off since 2026-10-06
def test_the_veto_card_passes_the_link_as_click_so_the_email_leg_carries_it(store, live_mode, tmp_env):
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    seen = {}
    cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                      notify_fn=lambda *a, **k: seen.update(k) or None)
    assert seen.get("click") and "/cadence/veto/" in seen["click"]
    assert seen["actions"][0][1] == seen["click"]


def test_an_unverifiable_slot_source_is_reported_once_and_then_escalates(store, live_mode, tmp_env):
    """With no GHL Private Integration token every slot-bearing touch returned
    skipped_unverified_slots for ever: the ladder never advanced, never stopped,
    and put a line in every hourly digest."""
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    state.cadence["day"] = 2  # E3 carries slots and needs no veto window (E2 has none)
    pings = []
    actions = []
    for hour in range(10, 19):
        now = ct(2026, 9, 22, hour, 5)
        state.cadence["next_send_at"] = ct(2026, 9, 22, 10, 0).isoformat()
        res = cadence.tick_lead(state, now, store=store, ghl=GHL(token=None),
                                notify_fn=lambda *a, **k: pings.append((a, k)))
        actions.append((res["action"], res.get("quiet")))
    assert actions[0] == ("skipped_unverified_slots", False)
    assert actions[1:] == [("skipped_unverified_slots", True)] * 8, actions
    assert pings == []
    # the next day it is still unverifiable: stop rather than stall in silence
    nxt = ct(2026, 9, 23, 10, 5)
    state.cadence["next_send_at"] = nxt.isoformat()
    res = cadence.tick_lead(state, nxt, store=store, ghl=GHL(token=None),
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "stopped" and res["reason"] == "slots_unavailable"
    assert state.cadence["stopped_reason"] == "slots_unavailable"
    assert len(pings) == 1 and pings[0][1]["priority"] == "high"


def test_a_send_that_was_issued_and_failed_holds_the_day_instead_of_resending(store, live_mode, tmp_env):
    """shared/instantly.py deliberately does not retry a write that never got an
    answer, because it may already have been accepted. Deleting the marker made
    the next hourly tick POST the identical body into the same thread."""
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    posts = []

    def handler(request):
        posts.append(str(request.url))
        if str(request.url).endswith("/emails/reply"):
            raise httpx.ReadTimeout("no answer", request=request)
        return httpx.Response(200, json={"from_address_email": "tiffany@flowerhillfs.com"})

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    free = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]
    first = cadence.tick_lead(state, now, store=store, instantly=inst, free_slots=free,
                              notify_fn=lambda *a, **k: None)
    assert first["action"] == "send_failed" and first["needs_manual_check"] is True
    marker = store.get(cadence.touch_marker_key(state, 1))
    assert marker is not None and marker["sent"] is False, "the marker was deleted, so the day will re-send"
    sends_after_first = len([u for u in posts if u.endswith("/emails/reply")])
    # the next hourly tick must not put the same body in the thread again
    again = cadence.tick_lead(state, ct(2026, 9, 22, 11, 0), store=store, instantly=inst, free_slots=free,
                              notify_fn=lambda *a, **k: None)
    assert again["action"] == "send_failed" and again["reason"] == "previous_attempt_unconfirmed"
    assert len([u for u in posts if u.endswith("/emails/reply")]) == sends_after_first == 1
    assert "confirm by hand" in cadence.summarize_touch(again).lower()


def test_a_refusal_decided_before_the_post_still_clears_the_marker(store, live_mode, tmp_env):
    """The other half: a state that cannot address a reply never issued a
    request, so the day stays retryable."""
    state = cadence.arm(make_state(eaccount=None), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    res = cadence.tick_lead(state, now, store=store, instantly=Instantly(api_key="x", transport=raising_transport()),
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: None)
    assert res["action"] == "send_failed" and res["reason"] == "missing_thread_ids"
    assert res.get("needs_manual_check") is None
    assert store.get(cadence.touch_marker_key(state, 1)) is None
    assert cadence.nothing_left_the_process("missing_thread_ids") is True
    assert cadence.nothing_left_the_process("send_failed: ReadTimeout") is False


def test_a_repaired_touch_reserves_the_slots_it_already_offered(store, tmp_env, monkeypatch):
    """The crash window the marker exists for: the confirmed marker was written
    and reserve_slots never ran. The repair rebuilt the touch but left the two
    emailed times free, so the next lead was offered one of them."""
    state = cadence.arm(make_state(), NOW)
    now = ct(2026, 9, 22, 10, 0)
    real = cadence._record_touch
    monkeypatch.setattr(cadence, "_record_touch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("killed")))
    with pytest.raises(RuntimeError):
        cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    monkeypatch.setattr(cadence, "_record_touch", real)
    marker = store.get(cadence.touch_marker_key(state, 1))
    assert marker and marker["sent"] is True and len(marker["slots"]) == 2
    stale = cadence.arm(make_state(), NOW)
    res = cadence.tick_lead(stale, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert res["action"] == "already_sent"
    assert sorted(stale.offered_slots) == sorted(marker["slots"])
    assert set(marker["slots"]) <= set(cadence.outstanding_offers(store, now))
    # a second lead is no longer offered one of those times
    other = cadence.arm(make_state(email="ilmi@shiningarmorcleaningnj.com", first_name="Ilmi"), NOW)
    rb = cadence.tick_lead(other, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert not (set(rb["touch"]["slots"]) & set(marker["slots"]))
    # and the repair is idempotent: replaying it does not double the registry
    before = len(store.get(cadence.OFFERED_REGISTRY_KEY, []))
    cadence._repair_from_marker(cadence.arm(make_state(), NOW), 1, marker, now, store)
    assert len(store.get(cadence.OFFERED_REGISTRY_KEY, [])) == before


def test_two_workers_cannot_claim_the_same_cadence_day(store, tmp_env):
    """The touch marker used the get-then-set idiom shared/store.py documents as
    unsafe, so the second worker did not see the first one's claim."""
    state_a = cadence.arm(make_state(), NOW)
    state_b = cadence.arm(make_state(), NOW)
    now = ct(2026, 9, 22, 10, 0)
    first = cadence.tick_lead(state_a, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert first["action"] == "would_send"
    # worker B holds the pre-tick snapshot; the marker is its own claim
    store.set(cadence.touch_marker_key(state_b, 1), {"ts": now.isoformat(), "day": 1, "sent": False})
    second = cadence.tick_lead(state_b, now, store=store, free_slots=cadence.default_slot_grid(now))
    assert second["action"] in ("locked", "send_failed")
    assert len([r for r in read_shadow_log() if r["action"] == "reply_to_email"]) == 1


def test_e2_fallback_line_matches_the_offer_type():
    """The fallback fires on every LLM error and in every LLM_FAKE dry run, so
    it is the line Lorenzo reviews. It used to open "I had a look at {company}"
    (research nobody did) and use reactivation wording for outbound prospects."""
    react = cadence.fallback_research_line("Flowerhill Facility Services", "reactivation")
    out = cadence.fallback_research_line("Flowerhill Facility Services", "outbound")
    assert react != out
    assert "had a look" not in react.lower() and "had a look" not in out.lower()
    for banned in ("went quiet", "dormant", "already know you", "quiet accounts"):
        assert banned not in out.lower(), out
    assert cadence.copy_problems(react + "\n\nLorenzo") == []
    assert cadence.copy_problems(out + "\n\nLorenzo") == []
    # and the rendered E2 body for an outbound campaign carries the outbound one
    body = cadence.build_touch(make_state(campaign_id=CLEANING_TRIG), 2, SLOTS).body_text
    assert "went quiet" not in body.lower()


def test_follow_up_later_stops_the_cadence_even_when_ghl_fails(store, live_mode, tmp_env):
    """No Private Integration token has been minted, so the GHL write raises.
    stop() sat after it, so the lead was never stopped and the same GHLError was
    reported on every daily tick for ever."""
    def handler(request):
        return httpx.Response(401, json={"message": "unauthorized"})

    ghl = GHL(token="fake-token", transport=httpx.MockTransport(handler))
    state = cadence.arm(make_state(status="negative_notnow", ghl_opportunity_id="hStqQMLQ5eSRVnqxnSMq"),
                        ct(2026, 9, 21, 16, 0))
    actions = []
    for day in (22, 23, 24):
        res = cadence.tick_lead(state, ct(2026, 9, day, 10, 0), store=store, ghl=ghl,
                                notify_fn=lambda *a, **k: None)
        actions.append(res["action"])
    assert actions[0] == "follow_up_later"
    assert state.cadence["stopped_reason"] == "follow_up_later"
    assert actions[1:] == ["already_stopped", "already_stopped"]


def test_a_cadence_touch_answers_the_address_that_actually_replied(store, tmp_env):
    """item['from_address_email'] "is NOT always the CRM address in
    item['lead']". approval.py sends the first reply to it; the cadence
    addressed every touch to lead_email, so a lead who answered from a shared
    mailbox got the first reply and none of the nine touches."""
    state = make_state(email="ilmi@shiningarmorcleaningnj.com")
    state.cadence = {"reply_from": "office@shiningarmorcleaningnj.com"}
    state = cadence.arm(state, NOW)
    assert cadence.recipient_for(state) == "office@shiningarmorcleaningnj.com"
    now = ct(2026, 9, 22, 10, 0)
    cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now))
    sent = [r for r in read_shadow_log() if r["action"] == "reply_to_email"]
    assert sent and sent[-1]["payload"]["to"] == "office@shiningarmorcleaningnj.com"
    assert sent[-1]["payload"]["lead_email"] == "ilmi@shiningarmorcleaningnj.com"  # still the store key


def test_a_thread_that_belongs_to_somebody_else_stops_once_instead_of_looping(store, live_mode, tmp_env):
    """Every tick used to log "refusing D2 to ...", return recipient_mismatch and
    leave the day unchanged, so nothing ever re-armed the lead and nothing sent."""
    def handler(request):
        return httpx.Response(200, json={"from_address_email": "someone-else@example.com"})

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    state = cadence.arm(make_state(), ct(2026, 9, 21, 16, 0))
    state.cadence["veto_notified_at"] = "2026-09-22T09:30:00-05:00"
    now = ct(2026, 9, 22, 10, 0)
    state.cadence["next_send_at"] = now.isoformat()
    pings = []
    res = cadence.tick_lead(state, now, store=store, instantly=inst,
                            free_slots=["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"],
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "send_failed" and res["reason"] == "recipient_mismatch"
    assert state.cadence["stopped_reason"] == "recipient_mismatch"
    assert len(pings) == 1 and pings[0][1]["priority"] == "high"
    assert cadence.tick_lead(state, ct(2026, 9, 22, 11, 0), store=store, instantly=inst,
                             notify_fn=lambda *a, **k: pings.append((a, k)))["action"] == "already_stopped"
    assert len(pings) == 1
