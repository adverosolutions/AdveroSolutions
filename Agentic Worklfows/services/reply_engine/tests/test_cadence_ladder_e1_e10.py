"""The ten-email follow-up ladder agreed with Lorenzo on 2026-09-23
(sections/1_email_followup/sequence_final.md): E1..E7 on consecutive business
days, E8 two weeks after E7, E9 and E10 a week apart, then the ladder is
exhausted. Every email's text per campaign, E2 slotless, the holds for missing
lead data, the E4 proof per offer type, and the catalogue ids.

Lead data is made up. MODE=shadow unless a test asks for live_mode, and every
client is a mock.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from shared import slots as slot_rules
from shared.job_log import read_shadow_log
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import cadence
from services.reply_engine import template_approvals as ta
from services.reply_engine import template_gate as gate
from services.reply_engine.cadence import LeadState

SEQUENCE_FINAL = Path(__file__).resolve().parents[3] / "sections" / "1_email_followup" / "sequence_final.md"

CAMPAIGNS = {
    ("cleaning", "reactivation"): "8086b41e-b546-4b36-9fa0-2d01f5cc119a",
    ("cleaning", "outbound"): "f347604e-48c7-4813-831c-dc7b9d4b50ae",
    ("bookkeeping", "reactivation"): "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d",
    ("bookkeeping", "outbound"): "87ebb167-9b64-4b6f-b658-88f3d1af9980",
    ("recruiting", "reactivation"): "1d4d5bb3-40a7-4333-bf34-b269d2cc9955",
    ("recruiting", "outbound"): "cd2e251c-3b5a-40d2-a3dc-d07c4004a48c",
}
LEAD = "dana@examplecleaning.test"
COMPANY = "Brightside Janitorial"
SLOTS = ["2026-09-23T14:00:00-05:00", "2026-09-24T15:30:00-05:00"]
FREE = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]

# ---------------------------------------------------------------- the agreed text, written out
BODIES = {
    1: "Hey {first_name},\n\nThe time slots I sent got filled. Here are 2 more, let me know if they work: {slots}.\n\n"
       "Lorenzo\n",
    2: "Hey {first_name},\n\n{research_line}\n\nFifteen minutes is enough for me to show you how this would run for "
       "{company}. Let me know when a good time is to get a call on the books.\n\nLorenzo\n",
    3: "Hey {first_name},\n\nI really want to get this call on the books with you. Those last two times got taken "
       "too.\n\nWould {slots} work instead?\n\nLorenzo\n",
    4: "Hey {first_name},\n\nI really think there's a lot of room for growth at {company}. I've built these systems "
       "across numerous industries. A few of my favorites:\n\n- {offer_proof}\n- an outbound system that raised a "
       "software consultancy's qualified lead volume 35%\n- $5M in loan applications in 30 days on $1,500 of ad "
       "spend for a lender\n\nThe first one is the same kind of system I'd build for {company}. Those last two times "
       "got booked. Would {slots} work to go over it?\n\nLorenzo\n",
    5: "Hey {first_name},\n\nHaven't heard back yet, no worries. It's a busy time of year and the slots keep getting "
       "filled.\n\nI'd still like to show you how we'd {offer_line}. Would {slots} work?\n\nLorenzo\n",
    6: "Hey {first_name},\n\nHere's a preview of what I'd show you on the call.\n\n{preview}\n\nThe rest takes about 15 "
       "minutes. Those last two times are gone, but I've got {slots} open.\n\nLorenzo\n",
    7: "Hey {first_name},\n\nLast one from me this week. Should I keep trying to find a time, or is now just not the "
       "right moment?\n\nThose last two times went too. If it's still on your list, I can do {slots}.\n\nLorenzo\n",
    8: "Hey {first_name},\n\nBeen a couple of weeks. Was hoping now was a good time to get a call on the books.\n\n"
       "The times I sent before are long gone. How about {slots}?\n\nLet me know if right now is a bad time, or if "
       "this just isn't a priority.\n\nLorenzo\n",
    9: "Hey {first_name},\n\nQuick thought for you. {observation}\n\nThat's where I'd start with you. The last times "
       "I sent are gone, but I'm free {slots}.\n\nLorenzo\n",
    10: "Hey {first_name},\n\nYou wrote back that you were interested, so I didn't want to just go quiet on you.\n\n"
        "I'll give you some room and check back in a few months. If you'd rather talk sooner, those last two times "
        "are gone, but {slots} would work.\n\nLorenzo\n",
}
RESEARCH_FALLBACK = {
    "reactivation": "The quickest place to start is usually the accounts that already know you and went quiet.",
    "outbound": "The quickest place to start is usually the prospects who are in market right now.",
}
OFFER_PROOF = {
    "reactivation": "a win-back system for a commercial roofer doing $150M a year that recovered about $6M worth of "
                    "contracts within 6 months",
    "outbound": "an outbound system for a commercial roofer doing $150M a year that brought in about $180,000 in new "
                "contracts in 90 days",
}
OFFER_LINE = {
    ("cleaning", "reactivation"): "win back {company}'s past accounts",
    ("recruiting", "reactivation"): "win back {company}'s past accounts",
    ("bookkeeping", "reactivation"): "win back {company}'s past clients",
    ("cleaning", "outbound"): "get {company} in front of new clients right when they need you",
    ("bookkeeping", "outbound"): "get {company} in front of new clients right when they need you",
    ("recruiting", "outbound"): "get {company} in front of new clients right when they need you",
}
PREVIEW = {
    ("cleaning", "reactivation"): 'The first two messages I\'d send accounts that cancelled or never signed: "Quick '
                                  'question, who\'s handling your cleaning these days?" and "Happy to take another '
                                  'look at the space and send a fresh quote. Want me to set that up?"',
    ("bookkeeping", "reactivation"): 'The first two messages I\'d send former clients and old inquiries: "Checking '
                                     'in, who\'s keeping your books these days?" and "Want us to get everything '
                                     'caught up before your next quarterly estimate is due?"',
    ("recruiting", "reactivation"): 'The first two messages I\'d send clients who\'ve gone quiet: "Anything you\'re '
                                    'hiring for this quarter that we could help with?" and "If a role\'s been open '
                                    'longer than you\'d like, send it over and we\'ll take a first pass."',
    ("cleaning", "outbound"): "The three things I'd watch for in your area: new office leases, companies moving into "
                              "bigger space, and buildings that just changed property managers. The outreach goes "
                              "out under your name.",
    ("bookkeeping", "outbound"): "The three things I'd watch for in your area: newly registered businesses, companies "
                                 "posting for a part-time bookkeeper, and businesses opening a second location. The "
                                 "outreach goes out under your name.",
    ("recruiting", "outbound"): "What I'd watch for in your market: specialty roles hitting the job boards, especially "
                                "ones that sit open for weeks or get reposted. The outreach goes out under your name.",
}
OBSERVATION = {
    ("cleaning", "reactivation"): "An account that cancelled or never signed already knows your name, so it's "
                                  "usually an easier conversation than a brand-new lead.",
    ("bookkeeping", "reactivation"): "Quarterly estimates, year-end and tax season each give you a natural reason to "
                                     "check back in with former clients and old inquiries.",
    ("recruiting", "reactivation"): "Clients who hired through you before, or almost did, already know how you work, "
                                    "so they're an easier conversation than any cold account.",
    ("cleaning", "outbound"): "A company moving into new space has to sort out cleaning around move-in.",
    ("bookkeeping", "outbound"): "A company posting a part-time bookkeeper job has already said out loud it needs "
                                 "help with its books.",
    ("recruiting", "outbound"): "An open specialty role on a job board is a hiring manager saying in public they need "
                                "someone.",
}


def ct(*args):
    return TZ.localize(datetime(*args))


# Campaign ids config/ids.json does not have (fake_campaigns): a niche or an offer the ladder has no line for.
ODD_CAMPAIGNS = {
    ("landscaping", "reactivation"): "odd-landscaping-reactivation",
    ("landscaping", "outbound"): "odd-landscaping-outbound",
    ("cleaning", None): "odd-cleaning-no-offer",
}


def make_state(niche="cleaning", offer="reactivation", **kw):
    """A lead on the campaign for (niche, offer)."""
    campaign = CAMPAIGNS.get((niche, offer)) or ODD_CAMPAIGNS.get((niche, offer)) or "not-a-campaign"
    base = dict(lead_email=LEAD, campaign_id=campaign, status="positive_interested",
                first_name="Dana", company=COMPANY, eaccount="lorenzo@adveromedia.com", thread_id="thr-e",
                last_email_id="01a0c5aa-0000-7000-8000-0000000000e1", last_subject="Re: Dana, question")
    base.update(kw)
    return LeadState(**base)


def expected_body(day, niche, offer, first="Dana", company=COMPANY):
    slots = slot_rules.format_slots([slot_rules.parse_iso(s) for s in SLOTS])
    values = {
        "first_name": first, "company": company, "slots": slots,
        "research_line": RESEARCH_FALLBACK[offer],
        "offer_proof": OFFER_PROOF[offer],
        "offer_line": OFFER_LINE[(niche, offer)].replace("{company}", company),
        "preview": PREVIEW[(niche, offer)],
        "observation": OBSERVATION[(niche, offer)],
    }
    out = BODIES[day]
    for key, value in values.items():
        out = out.replace("{%s}" % key, value)
    return out


@pytest.fixture
def fake_campaigns(monkeypatch):
    from shared import settings

    for (niche, offer), cid in ODD_CAMPAIGNS.items():
        monkeypatch.setitem(settings.CAMPAIGN_BY_ID, cid, {"id": cid, "niche": niche, "offer": offer or "",
                                                            "key": cid})


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


@pytest.fixture(autouse=True)
def public_base_url(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.test")
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)


def replies():
    return [r for r in read_shadow_log() if r["action"] == "reply_to_email"]


def at_day(done, when, **kw):
    state = cadence.arm(make_state(**kw), ct(2026, 9, 18, 16, 0))
    state.cadence["day"] = done
    state.cadence["next_send_at"] = when.isoformat()
    return state


# ================================================================ the ladder
def test_the_ladder_is_ten_emails_with_the_agreed_intents():
    assert cadence.DAY_SEQUENCE == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    assert cadence.INTENTS == {1: "times_filled", 2: "research", 3: "want_booked", 4: "proof", 5: "busy_offer",
                               6: "preview", 7: "week_close", 8: "restart", 9: "observation", 10: "pause"}
    assert cadence.SLOTLESS_DAYS == (2,)


def test_the_prompt_files_are_exactly_the_agreed_text():
    """Every prompts/cadence_e<n>.md body is the AGREED text in sequence_final.md, character for character."""
    seq = SEQUENCE_FINAL.read_text(encoding="utf-8")
    for n in range(1, 11):
        m = re.search(r"^## E%d .*?\n(Hey \{first_name\},\n.*?\nLorenzo)\n" % n, seq, re.S | re.M)
        assert m, "E%d not found in sequence_final.md" % n
        assert cadence._load_template("e%d" % n) == m.group(1) + "\n" == BODIES[n]


def test_the_old_prompt_files_are_gone():
    names = sorted(p.name for p in cadence.PROMPTS_DIR.glob("cadence_*.md"))
    assert names == sorted(["cadence_e%d.md" % n for n in range(1, 11)] + ["cadence_research.md"])


# ================================================================ schedule
def test_e1_to_e7_go_out_on_consecutive_business_days_across_a_weekend():
    state = cadence.arm(make_state(), ct(2026, 9, 23, 15, 0))  # Wednesday afternoon reply
    assert cadence._parse(state.cadence["next_send_at"]) == ct(2026, 9, 24, 10, 0)  # E1 Thursday
    sent = ct(2026, 9, 24, 10, 0)
    got = [sent]
    for day in range(1, 7):
        sent = cadence.schedule_after(day, sent)
        got.append(sent)
    assert got == [ct(2026, 9, 24, 10, 0), ct(2026, 9, 25, 10, 0), ct(2026, 9, 28, 10, 0), ct(2026, 9, 29, 10, 0),
                   ct(2026, 9, 30, 10, 0), ct(2026, 10, 1, 10, 0), ct(2026, 10, 2, 10, 0)]
    assert [d.weekday() for d in got] == [3, 4, 0, 1, 2, 3, 4]


def test_e8_is_fourteen_days_after_e7_and_e9_e10_a_week_apart():
    e7 = ct(2026, 10, 2, 10, 0)
    e8 = cadence.schedule_after(7, e7)
    assert e8 == ct(2026, 10, 16, 10, 0)
    e9 = cadence.schedule_after(8, e8)
    assert e9 == ct(2026, 10, 23, 10, 0)
    e10 = cadence.schedule_after(9, e9)
    assert e10 == ct(2026, 10, 30, 10, 0)
    assert cadence.schedule_after(10, e10) is None


def test_the_long_gaps_roll_to_a_business_day():
    # a touch recorded on a Saturday (a repaired marker, a late tick) never schedules a weekend send
    sat = ct(2026, 10, 3, 11, 0)
    assert cadence.schedule_after(7, sat) == ct(2026, 10, 19, 10, 0)  # +14 = Sat 17th -> Mon 19th
    assert cadence.schedule_after(8, sat) == ct(2026, 10, 12, 10, 0)  # +7 = Sat 10th -> Mon 12th
    assert cadence.schedule_after(9, sat) == ct(2026, 10, 12, 10, 0)
    assert cadence.schedule_after(6, ct(2026, 10, 2, 10, 0)) == ct(2026, 10, 5, 10, 0)  # Fri -> Mon


def test_after_e10_the_ladder_is_exhausted_and_moves_to_follow_up_later(store, tmp_env):
    now = ct(2026, 10, 30, 10, 0)
    state = at_day(9, now)
    free = ["2026-11-02T13:00:00-06:00", "2026-11-03T14:00:00-06:00"]
    res = cadence.tick_lead(state, now, store=store, free_slots=free, notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send" and res["day"] == 10
    assert state.cadence["stopped_reason"] == "exhausted" and state.cadence["next_send_at"] is None
    assert len(replies()) == 1
    ghl = [r for r in read_shadow_log() if r["action"] == "update_opportunity_stage"]
    assert len(ghl) == 1
    again = cadence.tick_lead(state, ct(2026, 11, 6, 10, 0), store=store, free_slots=FREE,
                              notify_fn=lambda *a, **k: None)
    assert again["action"] == "already_stopped" and len(replies()) == 1


@pytest.mark.parametrize("legacy_day", [14, 30])
def test_a_legacy_row_at_day_14_or_30_stops_as_exhausted_without_sending(legacy_day, store, tmp_env):
    now = ct(2026, 10, 30, 10, 0)
    state = at_day(legacy_day, now)
    assert cadence.pending_day(state) is None
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "stopped" and res["reason"] == "exhausted"
    assert state.cadence["stopped_reason"] == "exhausted"
    assert replies() == []
    assert cadence.tick_lead(state, now + timedelta(days=1), store=store, free_slots=FREE,
                             notify_fn=lambda *a, **k: None)["action"] == "already_stopped"
    assert replies() == []


def test_a_legacy_row_carrying_the_old_d6_keys_loads_and_ticks(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(5, now)
    state.cadence["d6_notified_at"] = ct(2026, 9, 21, 10, 0).isoformat()
    loaded = cadence.state_from_dict(cadence.state_to_dict(state))
    res = cadence.tick_lead(loaded, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send" and res["day"] == 6
    assert "requires_approval" not in res["touch"] and "channel_note" not in res["touch"]
    rearmed = cadence.arm(loaded, now + timedelta(days=1))
    assert "d6_notified_at" not in rearmed.cadence


# ================================================================ the text per campaign
@pytest.mark.parametrize("combo", sorted(CAMPAIGNS))
def test_every_email_renders_exactly_the_agreed_text_for_every_campaign(combo):
    niche, offer = combo
    state = make_state(niche, offer)
    for day in cadence.DAY_SEQUENCE:
        touch = cadence.build_touch(state, day, SLOTS)
        assert touch.body_text == expected_body(day, niche, offer), day
        assert touch.subject == "Re: Dana, question"
        body = touch.body_text
        assert "{" not in body and "}" not in body
        assert cadence.DEFAULT_BOOKING_URL not in body and "leadconnectorhq" not in body and "http" not in body
        assert "—" not in body and "–" not in body and "!" not in body
        assert touch.problems == [], (day, touch.problems)


@pytest.mark.parametrize("combo", sorted(CAMPAIGNS))
def test_the_template_ids_follow_the_campaign(combo):
    niche, offer = combo
    state = make_state(niche, offer)
    line = "reactivation_bookkeeping" if combo == ("bookkeeping", "reactivation") else offer
    assert cadence.touch_template_ids(1, state) == ("cadence.e1", [])
    assert cadence.touch_template_ids(2, state) == ("cadence.e2", ["cadence.e2.research_fallback.%s" % offer])
    assert cadence.touch_template_ids(2, state, research_source="researched") == ("cadence.e2", [cadence.E2_RESEARCH_RULES_ID])
    assert cadence.touch_template_ids(4, state) == ("cadence.e4", ["cadence.e4.offer_proof.%s" % offer])
    assert cadence.touch_template_ids(5, state) == ("cadence.e5", ["cadence.e5.offer_line.%s" % line])
    assert cadence.touch_template_ids(6, state) == ("cadence.e6", ["cadence.e6.preview.%s_%s" % (niche, offer)])
    assert cadence.touch_template_ids(9, state) == ("cadence.e9",
                                                    ["cadence.e9.observation.%s_%s" % (niche, offer)])
    for day in (3, 7, 8, 10):
        assert cadence.touch_template_ids(day, state) == ("cadence.e%d" % day, [])
    touch = cadence.build_touch(state, 6, SLOTS)
    assert touch.template_id == "cadence.e6"
    assert list(touch.template_parts) == ["cadence.e6.preview.%s_%s" % (niche, offer)]


@pytest.mark.parametrize("combo", sorted(CAMPAIGNS))
def test_the_varying_emails_pass_the_template_gate_for_every_campaign(combo, tmp_path, tmp_env):
    """Approved ladder ids (conftest): E2 / E4 / E5 / E6 / E9 of each campaign conform and go out."""
    niche, offer = combo
    when = ct(2026, 9, 22, 10, 0)
    for day in (2, 4, 5, 6, 9):
        state = at_day(day - 1, when, niche=niche, offer=offer)
        res = cadence.tick_lead(state, when, store=JsonFileStore(tmp_path / ("s%d.json" % day)), free_slots=FREE,
                                notify_fn=lambda *a, **k: None)
        assert res["action"] == "would_send", (day, res.get("reason"), res.get("ids"))
        assert res["touch"]["template_id"] == "cadence.e%d" % day


def test_the_first_name_fallback_is_there():
    touch = cadence.build_touch(make_state(first_name=None), 3, SLOTS)
    assert touch.body_text.startswith("Hey there,\n\n")


# ================================================================ E2 is slotless
def test_e2_offers_no_times_and_claims_or_reserves_none(store, tmp_env, monkeypatch):
    from services.reply_engine import approval as approval_mod

    def refuse(*a, **k):
        raise AssertionError("E2 must not claim slots")
    monkeypatch.setattr(approval_mod, "claim_slots", refuse)
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(1, now)
    before = list(state.offered_slots)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send" and res["day"] == 2
    assert res["touch"]["slots"] == []
    assert state.offered_slots == before
    assert store.get(cadence.OFFERED_REGISTRY_KEY, []) in ([], None)
    assert store.get(cadence.offered_key(now), []) in ([], None)
    marker = store.get(cadence.touch_marker_key(state, 2))
    assert marker["sent"] and marker["slots"] == []
    assert state.cadence["touches"][-1]["slots"] == []
    body = replies()[0]["payload"]["body"]["text"]
    assert "CT" not in body and "Fifteen minutes" in body


def test_e2_goes_out_even_when_no_free_times_exist(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(at_day(1, now), now, store=store, free_slots=[], notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send" and res["day"] == 2


def test_e7_now_offers_two_times(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(6, now)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send" and res["day"] == 7 and len(res["touch"]["slots"]) == 2
    assert len(state.offered_slots) == 2


def test_a_touch_that_needs_times_without_two_free_is_skipped(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    res = cadence.tick_lead(at_day(6, now), now, store=store, free_slots=[], notify_fn=lambda *a, **k: None)
    assert res["action"] == "skipped_no_slots" and res["day"] == 7
    assert replies() == []


# ================================================================ missing lead data holds
@pytest.mark.parametrize("day", [2, 4, 5])
def test_an_unknown_company_holds_the_emails_that_name_it(day, store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(day - 1, now, company=None)
    assert cadence.missing_lead_data(state, day) == ["company"]
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "held_template" and res["reason"] == "missing_lead_data"
    assert res["cause"] == "lead_data" and res["missing"] == ["company"]
    assert replies() == [] and state.cadence["day"] == day - 1
    assert "your team" not in cadence.build_touch(state, day, SLOTS).body_text


def test_an_unknown_company_does_not_hold_an_email_that_does_not_name_it(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    for day in (1, 3, 6, 7, 8, 9, 10):
        assert cadence.missing_lead_data(make_state(company=None), day) == [], day
    state = at_day(2, now, company=None)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "would_send" and res["day"] == 3


def test_an_unknown_niche_holds_the_emails_written_per_niche(store, tmp_env, fake_campaigns):
    now = ct(2026, 9, 22, 10, 0)
    for day in (5, 6, 9):
        assert cadence.missing_lead_data(make_state("landscaping", "reactivation"), day) == ["niche"], day
    state = at_day(5, now, niche="landscaping", offer="reactivation")
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "held_template" and res["reason"] == "missing_lead_data"
    assert replies() == []


def test_an_unknown_offer_holds_the_emails_written_per_offer(store, tmp_env, fake_campaigns):
    now = ct(2026, 9, 22, 10, 0)
    for day in (2, 4, 5, 6, 9):
        assert "offer" in cadence.missing_lead_data(make_state("cleaning", None), day), day
    state = at_day(3, now, niche="cleaning", offer=None)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, notify_fn=lambda *a, **k: None)
    assert res["action"] == "held_template" and res["reason"] == "missing_lead_data"
    assert replies() == []


def test_an_outbound_e5_needs_no_niche(fake_campaigns):
    state = make_state(niche="landscaping", offer="outbound")
    assert cadence.missing_lead_data(state, 5) == []
    assert cadence.missing_lead_data(state, 6) == ["niche"]


def test_a_lead_on_no_known_campaign_is_held_for_every_email_that_needs_it():
    state = make_state(niche=None, offer=None)
    assert state.campaign_id == "not-a-campaign"
    for day in (2, 4, 5, 6, 9):
        assert "offer" in cadence.missing_lead_data(state, day), day
    assert cadence.missing_lead_data(state, 1) == [] and cadence.missing_lead_data(state, 3) == []


def test_a_missing_data_hold_is_previewed_by_a_dry_run_and_advises_fixing_the_record(store, tmp_env):
    now = ct(2026, 9, 22, 10, 0)
    state = at_day(3, now, company=None)
    res = cadence.tick_lead(state, now, store=store, free_slots=FREE, dry_run=True)
    assert res["action"] == "held_template" and res["dry_run"] and res["reason"] == "missing_lead_data"
    assert "template_hold" not in state.cadence
    advice = cadence.hold_advice("missing_lead_data")
    assert "Approving changes nothing" in advice and "company" in advice


def test_a_missing_data_hold_stalls_into_a_resumable_stop(store, tmp_env):
    state = at_day(3, ct(2026, 9, 22, 10, 0), company=None)
    notes = []
    days = [ct(2026, 9, 22, 10, 0), ct(2026, 9, 23, 10, 0), ct(2026, 9, 24, 10, 0), ct(2026, 9, 25, 10, 0)]
    results = [cadence.tick_lead(state, d, store=store, free_slots=FREE,
                                 notify_fn=lambda *a, **k: notes.append(a)) for d in days]
    assert [r["action"] for r in results] == ["held_template", "held_template", "held_template", "stopped"]
    assert state.cadence["stopped_reason"] == "template_unapproved"
    assert replies() == []


# ================================================================ E4 proof, never mixed
@pytest.mark.parametrize("combo", [("cleaning", "reactivation"), ("recruiting", "outbound")])
def test_e4_carries_only_its_own_offers_proof(combo):
    niche, offer = combo
    body = cadence.build_touch(make_state(niche, offer), 4, SLOTS).body_text
    other = "outbound" if offer == "reactivation" else "reactivation"
    assert OFFER_PROOF[offer] in body and OFFER_PROOF[other] not in body
    if offer == "reactivation":
        assert "$6M" in body and "$180,000" not in body
    else:
        assert "$180,000" in body and "$6M" not in body


@pytest.mark.parametrize("combo", [("cleaning", "reactivation"), ("recruiting", "outbound")])
def test_the_copy_gate_refuses_the_other_offers_proof_in_e4(combo):
    niche, offer = combo
    state = make_state(niche, offer)
    touch = cadence.build_touch(state, 4, SLOTS)
    other = "outbound" if offer == "reactivation" else "reactivation"
    mixed = touch.body_text.replace(OFFER_PROOF[offer], OFFER_PROOF[other])
    problems = cadence.copy_problems(mixed, allow=touch.allow_terms, campaign_key=touch.campaign_key)
    assert "proof_from_another_offer" in problems


def test_the_e4_lender_figure_is_allowed_only_on_its_agreed_line():
    """$1,500 is offers.md's "$1.5k" written out; the verbatim money check allows it on E4's fixed line only."""
    body = cadence.build_touch(make_state(), 4, SLOTS).body_text
    assert cadence.E4_LENDER_LINE in body
    assert "- %s\n" % cadence.E4_LENDER_LINE in cadence._load_template("e4")
    assert cadence.copy_problems(body, allow=[COMPANY, "Dana"], campaign_key="cleaning_reactivation") == []
    stray = "Hey Dana,\n\nIt costs $1,500 to start.\n\nLorenzo\n"
    assert "money_not_in_offer_sheet" in cadence.copy_problems(stray, campaign_key="cleaning_reactivation")
    edited = body.replace("$1,500 of ad spend", "$1,500 of ad spend and $2,000 of setup")
    assert "money_not_in_offer_sheet" in cadence.copy_problems(edited, allow=[COMPANY, "Dana"],
                                                                 campaign_key="cleaning_reactivation")


# ================================================================ catalogue
NEW_CADENCE_IDS = sorted(
    ["cadence.e%d" % n for n in range(1, 11)]
    + ["cadence.e2.research_fallback.reactivation", "cadence.e2.research_fallback.outbound",
       "cadence.e2.research_line",
       "cadence.e4.offer_proof.reactivation", "cadence.e4.offer_proof.outbound",
       "cadence.e5.offer_line.reactivation", "cadence.e5.offer_line.reactivation_bookkeeping",
       "cadence.e5.offer_line.outbound"]
    + ["cadence.e6.preview.%s_%s" % c for c in CAMPAIGNS]
    + ["cadence.e9.observation.%s_%s" % c for c in CAMPAIGNS]
    # the AI agents offer (2026-10-06): one line per email for every AI agents campaign
    + ["cadence.e2.research_fallback.ai_agents", "cadence.e4.offer_proof.ai_agents",
       "cadence.e5.offer_line.ai_agents", "cadence.e6.preview.ai_agents", "cadence.e9.observation.ai_agents"])


def test_the_catalogue_has_exactly_the_new_cadence_ids():
    index = ta.catalogue_index()
    got = sorted(tid for tid in index if tid.startswith("cadence."))
    assert got == NEW_CADENCE_IDS
    assert len(got) == 35
    for tid in got:
        e = index[tid]
        if tid == "cadence.e2.research_line":
            assert not e["approvable"] and not e["extractable"]
            continue
        assert e["approvable"] and e["extractable"], tid
        assert e["kind"] == ("cadence" if re.match(r"cadence\.e\d+$", tid) else "cadence_fragment")
        assert "booking_url" not in e["variables"], tid
        assert "{booking_url}" not in e["review_text"] and "leadconnectorhq" not in e["review_text"]
        names = [v["name"] for v in e["variants"]]
        assert "no_slots" not in names and "one_slot" not in names


def test_the_catalogue_fragments_are_the_agreed_lines():
    index = ta.catalogue_index()
    for offer, text in RESEARCH_FALLBACK.items():
        assert index["cadence.e2.research_fallback.%s" % offer]["text"] == text
    for offer, text in OFFER_PROOF.items():
        assert index["cadence.e4.offer_proof.%s" % offer]["text"] == text
    assert index["cadence.e5.offer_line.reactivation"]["text"] == OFFER_LINE[("cleaning", "reactivation")]
    assert index["cadence.e5.offer_line.reactivation_bookkeeping"]["text"] == OFFER_LINE[("bookkeeping",
                                                                                         "reactivation")]
    assert index["cadence.e5.offer_line.outbound"]["text"] == OFFER_LINE[("cleaning", "outbound")]
    for (niche, offer), text in PREVIEW.items():
        assert index["cadence.e6.preview.%s_%s" % (niche, offer)]["text"] == text
    for (niche, offer), text in OBSERVATION.items():
        assert index["cadence.e9.observation.%s_%s" % (niche, offer)]["text"] == text
    for n in range(1, 11):
        assert index["cadence.e%d" % n]["text"] == BODIES[n]


def test_the_gate_maps_each_part_to_its_placeholder():
    assert gate._part_placeholder("cadence.e2.research_fallback.outbound") == "research_line"
    assert gate._part_placeholder("cadence.e2.research_line") == "research_line"
    assert gate._part_placeholder("cadence.e4.offer_proof.reactivation") == "offer_proof"
    assert gate._part_placeholder("cadence.e5.offer_line.reactivation_bookkeeping") == "offer_line"
    assert gate._part_placeholder("cadence.e6.preview.cleaning_outbound") == "preview"
    assert gate._part_placeholder("cadence.e9.observation.recruiting_reactivation") == "observation"
    assert gate._part_placeholder("cadence.d4.case_study.reactivation") is None
    assert gate.UNEXTRACTABLE_BY_DESIGN == ("cadence.e2.research_line",)


@pytest.mark.parametrize("record, spoken", [
    ("Brightline Cleaning LLC", "Brightline Cleaning"),
    ("Acme, Inc.", "Acme"),
    ("Tallgrass Bookkeeping | Omaha's small-business bookkeeper", "Tallgrass Bookkeeping"),
    ("Northside Staffing - Tulsa", "Northside Staffing"),
    ("Keystone Tax: bookkeeping and payroll", "Keystone Tax"),
    ("Re:Source Staffing LLC", "Re:Source Staffing"),
    ("Smith & Co.", "Smith & Co"),
    ("Acme:", "Acme"),
])
def test_company_is_said_the_way_a_person_says_it(record, spoken):
    assert cadence.spoken_company(record) == spoken
