"""The unattended copy gate (GAP 2).

``cadence.copy_problems`` is the ONLY thing standing between a D1-D7 follow-up
and a prospect's inbox: nobody reads those touches before they are sent. It
used to be weaker than ``draft.validate_draft``, which gates the first reply
Lorenzo approves by hand, and the two cases below are the proof. Both of them
returned ``[]`` from the cadence and a refusal from the draft validator.

Every test here asserts the SAME body against both gates, so the day one of
them grows a rule the other does not, this file fails instead of a prospect
receiving the difference.
"""
from datetime import datetime

import pytest

from shared import llm, slots as slot_rules
from shared.job_log import read_shadow_log
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import cadence, draft as draft_mod
from services.reply_engine.cadence import LeadState

NOW = slot_rules.parse_iso("2026-09-21T21:10:00-05:00")  # Monday night
CLEANING_REACT = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
BOOKKEEPING_TRIG = "87ebb167-9b64-4b6f-b658-88f3d1af9980"

# The critic's two bodies, verbatim in shape: a TO CONFIRM retainer, and one
# vertical's guarantee figure inside another vertical's thread.
TO_CONFIRM_RETAINER = ("Hey Dana,\n\nIt is setup plus a $2,500 a month retainer, sized to your "
                       "service area.\n\nLorenzo")
CLEANING_GUARANTEE = ("Hey Dana,\n\nWe land $24,000 a year in new contracts within 90 days or your "
                      "money back.\n\nLorenzo")


def ct(*args):
    return TZ.localize(datetime(*args))


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


def make_state(campaign_id=CLEANING_REACT, **kw):
    base = dict(
        lead_email="tiffany@flowerhillfs.com",
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


# ------------------------------------------------- the critic's two cases
def test_the_to_confirm_retainer_is_refused_on_the_unattended_path():
    """offers.md marks the $2,500-5,000/mo retainer "TO CONFIRM with Lorenzo
    before quoting in writing". draft.validate_draft has always refused it; the
    cadence passed it, and the cadence is the path with nobody reading."""
    human_gate = draft_mod.validate_draft(TO_CONFIRM_RETAINER, campaign_key="cleaning_trigger")
    assert any("TO CONFIRM" in p for p in human_gate)

    # The old code returned [] here, with or without a campaign key.
    assert cadence.copy_problems(TO_CONFIRM_RETAINER) == ["money_marked_to_confirm"]
    assert cadence.copy_problems(TO_CONFIRM_RETAINER, campaign_key="cleaning_trigger") == [
        "money_marked_to_confirm"]


def test_another_verticals_guarantee_is_refused_inside_this_leads_thread():
    """$24,000/yr is cleaning_trigger's guarantee. It exists in offers.md, so
    the cadence's substring check waved it through in a bookkeeping thread,
    where the real promise is $15,000 in new annual client fees."""
    human_gate = draft_mod.validate_draft(CLEANING_GUARANTEE, campaign_key="bookkeeping_trigger")
    assert any("cleaning_trigger" in p for p in human_gate)

    # The old code returned [] here.
    assert cadence.copy_problems(CLEANING_GUARANTEE, campaign_key="bookkeeping_trigger") == [
        "guarantee_from_another_offer"]
    # ... and it is still the right number for the offer it belongs to.
    assert cadence.copy_problems(CLEANING_GUARANTEE, campaign_key="cleaning_trigger") == []


def test_without_a_campaign_key_the_cross_offer_half_is_blind():
    """Why Touch carries campaign_key: both draft.validate_draft and the cadence
    answer [] for a foreign guarantee when nothing says whose offer this is."""
    assert draft_mod.validate_draft(CLEANING_GUARANTEE, campaign_key=None) == []
    assert cadence.copy_problems(CLEANING_GUARANTEE) == []


# -------------------------------------------------- the two gates in step
PARITY_BODIES = [
    (TO_CONFIRM_RETAINER, "cleaning_trigger"),
    (TO_CONFIRM_RETAINER, "bookkeeping_trigger"),
    (CLEANING_GUARANTEE, "bookkeeping_trigger"),
    (CLEANING_GUARANTEE, "recruiting_outbound"),
    ("Hey Dana,\n\nWe promise $15,000 in new annual client fees.\n\nLorenzo", "cleaning_trigger"),
    ("Hey Dana,\n\nWe promise $40,000 in new placement fees.\n\nLorenzo", "bookkeeping_trigger"),
    ("Hey Dana,\n\nI recovered about $6M worth of contracts within 6 months.\n\nLorenzo",
     "recruiting_outbound"),
    ("Hey Dana,\n\nI can get you $50,000 back.\n\nLorenzo", "cleaning_reactivation"),
    ("Hey Dana,\n\nThe automation handles it — no work for you!\n\nLorenzo", "cleaning_reactivation"),
    ("Hey Dana,\n\nWorth a look.\n", "cleaning_reactivation"),
]


@pytest.mark.parametrize("body,key", PARITY_BODIES)
def test_the_unattended_gate_is_never_weaker_than_the_human_approved_one(body, key):
    """The one property that matters. A body the human-approved path refuses
    must not be sendable on the path with no human in it."""
    human = [p for p in draft_mod.validate_draft(body, campaign_key=key)
             if not p.startswith("too long")]
    unattended = cadence.copy_problems(body, campaign_key=key)
    if human:
        assert unattended, "draft.validate_draft refused %r (%s) and the cadence did not" % (body, human)


@pytest.mark.parametrize("body,key", PARITY_BODIES)
def test_every_draft_problem_arrives_as_a_cadence_code(body, key):
    """No draft rule is silently dropped in translation: anything the shared
    validator raises comes back as a mapped code, never as the raw sentence."""
    for code in cadence.shared_problems(body, campaign_key=key):
        assert not code.startswith("copy_rule:"), code


def test_a_body_the_offer_sheet_allows_still_passes_both_gates():
    """The guard has to refuse the two cases WITHOUT refusing real copy."""
    good = ("Hey Dana,\n\nI recently implemented the same system for a commercial roofer doing $150M/yr "
            "and generated about $180,000 in new contracts in 90 days.\n\nLorenzo")
    assert draft_mod.validate_draft(good, campaign_key="cleaning_trigger") == []
    assert cadence.copy_problems(good, campaign_key="cleaning_trigger") == []


def test_every_shipped_touch_for_every_campaign_still_clears_the_gate():
    """A stricter gate that blocks the templates themselves is an outage, not a
    fix: every lead would stall at blocked_copy from D1."""
    from shared import settings

    now = ct(2026, 9, 22, 10, 0)
    two = [ct(2026, 9, 23, 13, 0), ct(2026, 9, 24, 15, 0)]
    blocked = []
    for key, meta in settings.CAMPAIGNS.items():
        state = make_state(campaign_id=meta["id"], campaign_key=key)
        assert cadence.campaign_key_of(state) == key
        for day in cadence.INTENTS:
            touch = cadence.build_touch(state, day, two)
            assert touch.campaign_key == key, (key, day)
            if touch.problems:
                blocked.append((key, day, touch.problems))
    assert blocked == []
    assert now  # the grid above is fixed; `now` only documents the week


# ----------------------------------------------- the old vocabulary stands
def test_the_existing_cadence_codes_are_unchanged():
    assert "mentions_ai_or_automation" in cadence.copy_problems("The Automation runs itself\n\nLorenzo")
    assert "money_not_in_offer_sheet" in cadence.copy_problems("I can guarantee $50,000 back\n\nLorenzo")
    assert "unverified_guarantee" in cadence.copy_problems("I guarantee it\n\nLorenzo")
    assert "percentage_not_in_offer_sheet" in cadence.copy_problems("I take 45% of fees\n\nLorenzo")
    assert "unsigned" in cadence.copy_problems("No sign off")
    assert "dash" in cadence.copy_problems("A — b\n\nLorenzo")
    assert "exclamation" in cadence.copy_problems("Great news!\n\nLorenzo")
    assert "unfilled_placeholder" in cadence.copy_problems("Hey {first_name}\n\nLorenzo")


# --------------------------------------------------------- failing closed
def test_a_validator_that_cannot_be_imported_blocks_instead_of_opening_the_gate(monkeypatch):
    """The gate missing is not "no problems". Returning [] there would auto-send
    completely unchecked copy, which is worse than the bug being fixed."""
    monkeypatch.setattr(cadence, "draft_mod", None)
    problems = cadence.copy_problems("Hey Dana,\n\nPerfectly ordinary copy.\n\nLorenzo")
    assert cadence.VALIDATOR_UNAVAILABLE in problems


def test_a_validator_that_raises_blocks_too(monkeypatch):
    class Boom(object):
        @staticmethod
        def validate_draft(*a, **kw):
            raise RuntimeError("offers.md unreadable")

    monkeypatch.setattr(cadence, "draft_mod", Boom)
    assert cadence.VALIDATOR_UNAVAILABLE in cadence.copy_problems("Hey Dana,\n\nFine.\n\nLorenzo")


# ------------------------------------------------------ on the send path
def test_a_touch_quoting_the_to_confirm_retainer_is_never_sent(store, tmp_env, monkeypatch):
    """End to end through tick_lead: the gate is on the send path, not just a
    function somebody could forget to call. P4: E2 in "llm" mode ends in the
    fallback line in tests (nothing is researched), so the bad line rides in
    as that line."""
    monkeypatch.setattr(cadence, "fallback_research_line", lambda company, offer: (
        "I saw the new builds going up on your side of town, and setup plus a $2,500 a month "
        "retainer covers that whole area"))
    try:
        state = cadence.arm(make_state(), NOW)
        state.cadence["day"] = 1
        now = ct(2026, 9, 22, 10, 0)
        state.cadence["next_send_at"] = now.isoformat()
        pings = []
        res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                notify_fn=lambda *a, **k: pings.append((a, k)), research_mode="llm")
        assert res["action"] == "blocked_copy" and res["day"] == 2
        assert "money_marked_to_confirm" in res["problems"]
        assert [r for r in read_shadow_log() if r["action"] == "reply_to_email"] == []
        assert state.cadence["day"] == 1 and state.cadence["touches"] == []
        assert pings and pings[0][1]["priority"] == "high"
    finally:
        llm.clear_fakes()


def test_a_touch_quoting_another_verticals_guarantee_is_never_sent(store, tmp_env, monkeypatch):
    """The bookkeeping lead, told cleaning's number, with nobody reading."""
    monkeypatch.setattr(cadence, "fallback_research_line", lambda company, offer: (
        "I noticed the two new locations, and $24,000 a year in new contracts inside 90 days is "
        "the usual shape for that"))
    try:
        state = cadence.arm(make_state(campaign_id=BOOKKEEPING_TRIG,
                                       campaign_key="bookkeeping_trigger"), NOW)
        state.cadence["day"] = 1
        now = ct(2026, 9, 22, 10, 0)
        state.cadence["next_send_at"] = now.isoformat()
        res = cadence.tick_lead(state, now, store=store, free_slots=cadence.default_slot_grid(now),
                                notify_fn=lambda *a, **k: None, research_mode="llm")
        assert res["action"] == "blocked_copy" and res["day"] == 2
        assert "guarantee_from_another_offer" in res["problems"]
        assert [r for r in read_shadow_log() if r["action"] == "reply_to_email"] == []
    finally:
        llm.clear_fakes()
