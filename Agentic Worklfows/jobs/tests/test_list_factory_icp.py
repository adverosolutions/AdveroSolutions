"""ICP scoring: the rules that stop the snow-removal company."""
import json

import pytest

from shared import llm

from services.list_factory import icp, models


def lead(**kw):
    base = {
        "company_name": "Acme", "city": "Chicago", "state": "Illinois",
        "industry": "", "keywords": "", "description": "", "headline": "", "website": "",
    }
    base.update(kw)
    return models.new_lead(base, source="test")


@pytest.fixture(autouse=True)
def keep_other_briefs_fakes():
    """Snapshot and restore shared.llm's fake registry around every test here.

    These tests used ``llm.clear_fakes()`` in a finally block, which is a
    GLOBAL reset: it also dropped the fakes other services register at import
    time (services/retro/fakes.py registers "retro"), and a retro test that ran
    afterwards in the same session failed on a real-looking cached proposal.
    A shared registry needs save-and-restore, not clear.
    """
    saved = dict(llm._FAKES)
    try:
        yield
    finally:
        llm._FAKES.clear()
        llm._FAKES.update(saved)


@pytest.fixture
def cleaning():
    return icp.load_rubric("cleaning")


def test_every_shipped_rubric_loads_and_names_its_campaigns():
    niches = icp.available_niches()
    assert set(niches) >= {"cleaning", "bookkeeping", "recruiting"}
    for niche in niches:
        rubric = icp.load_rubric(niche)
        assert rubric["question"]
        assert rubric["campaigns"]["trigger"]


def test_snow_removal_is_hard_rejected_before_any_model_call(cleaning):
    """The September miss. A snow-removal company that also says 'commercial'
    must never reach the model, because a model that sees 'commercial' and
    'property managers' has a real chance of saying yes."""
    snow = lead(
        company_name="Northland Snow Removal and Lawn",
        keywords="snow removal, snow plowing, salting, lawn care",
        description="Commercial snow removal for property managers.",
    )
    verdict = icp.rule_verdict(snow, cleaning)
    assert verdict["verdict"] == icp.VERDICT_REJECT
    assert "snow removal" in verdict["reason"]


def test_hard_reject_beats_hard_accept(cleaning):
    """A restoration franchise that also advertises janitorial is still a
    restoration franchise. Reject wins, whatever order the keywords appear in."""
    both = lead(
        company_name="ServiceMaster Restore",
        keywords="janitorial services, water damage, mold remediation",
    )
    assert icp.rule_verdict(both, cleaning)["verdict"] == icp.VERDICT_REJECT


def test_obvious_match_is_accepted_for_free(cleaning):
    """A hard accept has to come from the business's OWN words. ``keywords`` is
    where the Apify actor echoes the search terms we sent it, so evidence that
    lives only there is not decisive (see the test below)."""
    good = lead(company_name="Bright Path Building Services",
                description="Nightly commercial cleaning and day porter service for office buildings.",
                keywords="commercial cleaning, janitorial services, day porter")
    verdict = icp.rule_verdict(good, cleaning)
    assert verdict["verdict"] == icp.VERDICT_ACCEPT
    # ... and the company name alone is enough when it says what it does.
    named = lead(company_name="Established Janitorial", keywords="")
    assert icp.rule_verdict(named, cleaning)["verdict"] == icp.VERDICT_ACCEPT


def test_a_scraper_injected_search_term_does_not_hard_accept(cleaning):
    """The Apify actor appends its own query to every row's ``keywords``:
    "janitorial services, facilities services" appears on 27 of the 58 recorded
    businesses for no reason other than the search we ran. A bin-cleaning
    company was therefore accepted at confidence 1.0 before the model ever saw
    it, which is exactly the 'snow-removal company mailed as a cleaner' failure
    the rubric exists to stop."""
    bins = lead(
        company_name="Cleanse Your Bins",
        description="Trash can cleaning, house washing, window washing, solar panel cleaning.",
        keywords="trash can cleaning, house washing, window washing, trash bin cleaning, "
                 "solar panel cleaning, pressure washing, janitorial services, facilities services",
    )
    assert icp.rule_verdict(bins, cleaning)["verdict"] != icp.VERDICT_ACCEPT
    windows = lead(
        company_name="Gillette Window And Solar Cleaning",
        keywords="window cleaning, solar panel cleaning, gutter cleaning, janitorial services",
    )
    assert icp.rule_verdict(windows, cleaning)["verdict"] != icp.VERDICT_ACCEPT


def test_a_hard_reject_still_reads_every_field(cleaning):
    """Over-rejecting on an echoed term costs a fraction of a cent, and no
    query we send contains a reject phrase, so hard REJECT keeps reading
    keywords even though hard accept does not."""
    snow = lead(company_name="Northland Facilities", keywords="snow removal, salting")
    assert icp.rule_verdict(snow, cleaning)["verdict"] == icp.VERDICT_REJECT


def test_ambiguous_lead_goes_to_the_model_and_an_unsure_answer_is_rejected(cleaning, monkeypatch):
    """Unsure means no. A maybe that gets mailed is a hostile reply; a maybe
    that gets dropped is a fraction of a cent."""
    vague = lead(company_name="Vanta Clean Cooperative", keywords="cleaning")
    assert icp.rule_verdict(vague, cleaning)["verdict"] == icp.VERDICT_UNSURE

    llm.register_fake("icp_score", lambda s, u, j: {"results": [{"n": 1, "verdict": "unsure", "confidence": 0.3, "reason": "no evidence"}]})
    llm.register_fake("icp_escalate", lambda s, u, j: {"results": [{"n": 1, "verdict": "unsure", "confidence": 0.4, "reason": "still unclear"}]})
    summary = icp.score([vague], cleaning)
    assert vague["icp_verdict"] == icp.VERDICT_REJECT
    assert summary["unsure_rejected"] == 1
    assert summary["escalations"] == 1


def test_low_confidence_accept_escalates_to_sonnet_and_can_be_saved(cleaning):
    vague = lead(company_name="Vanta Clean Cooperative", keywords="cleaning")
    llm.register_fake("icp_score", lambda s, u, j: {"results": [{"n": 1, "verdict": "accept", "confidence": 0.55, "reason": "maybe"}]})
    llm.register_fake("icp_escalate", lambda s, u, j: {"results": [{"n": 1, "verdict": "accept", "confidence": 0.93, "reason": "site lists office cleaning"}]})
    summary = icp.score([vague], cleaning)
    assert vague["icp_verdict"] == icp.VERDICT_ACCEPT
    assert vague["icp_decided_by"] == llm.model_for("escalate")
    assert summary["escalations"] == 1


def test_accept_below_min_confidence_is_downgraded_to_reject(cleaning):
    vague = lead(company_name="Vanta Clean Cooperative", keywords="cleaning")
    # Escalation is off, so the 0.5 accept stands and must be treated as a miss.
    llm.register_fake("icp_score", lambda s, u, j: {"results": [{"n": 1, "verdict": "accept", "confidence": 0.5, "reason": "maybe"}]})
    icp.score([vague], cleaning, max_escalations=0)
    assert vague["icp_verdict"] == icp.VERDICT_REJECT
    assert "min_confidence" in vague["icp_reason"]


def test_escalation_cap_is_respected(cleaning):
    leads = [lead(company_name="Vague %d" % i, keywords="cleaning") for i in range(5)]
    llm.register_fake("icp_score", lambda s, u, j: {"results": [
        {"n": i + 1, "verdict": "unsure", "confidence": 0.1, "reason": "x"} for i in range(5)
    ]})
    llm.register_fake("icp_escalate", lambda s, u, j: {"results": [{"n": 1, "verdict": "accept", "confidence": 0.99, "reason": "ok"}]})
    summary = icp.score(leads, cleaning, max_escalations=2)
    assert summary["escalations"] == 2
    assert sum(1 for l in leads if l["icp_verdict"] == icp.VERDICT_ACCEPT) == 2


def test_a_model_answer_that_skips_businesses_does_not_smear_across_them(cleaning):
    """A short answer used to be zipped against the batch, so business 3's
    verdict landed on business 1. Missing numbers must come back unsure."""
    leads = [lead(company_name="Vague %d" % i, keywords="cleaning") for i in range(3)]
    llm.register_fake("icp_score", lambda s, u, j: {"results": [
        {"n": 3, "verdict": "accept", "confidence": 0.99, "reason": "definitely"},
    ]})
    icp.score(leads, cleaning, max_escalations=0)
    assert leads[0]["icp_verdict"] == icp.VERDICT_REJECT
    assert leads[1]["icp_verdict"] == icp.VERDICT_REJECT
    assert leads[2]["icp_verdict"] == icp.VERDICT_ACCEPT


def test_unusable_model_response_rejects_the_whole_batch(cleaning):
    leads = [lead(company_name="Vague %d" % i, keywords="cleaning") for i in range(3)]
    llm.register_fake("icp_score", lambda s, u, j: {"nonsense": True})
    llm.register_fake("icp_escalate", lambda s, u, j: {"nonsense": True})
    icp.score(leads, cleaning, max_escalations=0)
    assert all(l["icp_verdict"] == icp.VERDICT_REJECT for l in leads)


def test_prompt_carries_every_business_and_the_niche_question(cleaning):
    leads = [lead(company_name="A"), lead(company_name="B")]
    prompt = icp.build_prompt(leads, cleaning)
    assert cleaning["question"] in prompt
    assert "1. name: A" in prompt
    assert "2. name: B" in prompt


def test_missing_rubric_raises_rather_than_scoring_with_nothing():
    with pytest.raises(icp.RubricError):
        icp.load_rubric("not-a-niche")


# ------------------------------------------------- word boundaries (regressed)
def test_warehouse_cleaning_is_not_house_cleaning(cleaning):
    """Found in the first fixture rehearsal: a bare substring match rejected
    'Industrial and warehouse cleaning crews' as a residential maid service.
    A rule that silently removes good leads is the worst kind, because nothing
    downstream reports it."""
    industrial = lead(
        company_name="Harborline Facility Group",
        keywords="facility services, warehouse cleaning, industrial cleaning, distribution centers",
        description="Industrial and warehouse cleaning crews for distribution and logistics sites.",
    )
    assert icp.rule_verdict(industrial, cleaning)["verdict"] != icp.VERDICT_REJECT


def test_the_real_house_cleaning_phrase_still_rejects(cleaning):
    residential = lead(company_name="Tidy Nest", keywords="house cleaning, move out cleaning")
    assert icp.rule_verdict(residential, cleaning)["verdict"] == icp.VERDICT_REJECT


def test_keyword_hit_is_whole_phrase_only():
    assert icp.keyword_hit("industrial and warehouse cleaning crews", "house cleaning") is False
    assert icp.keyword_hit("we do house cleaning weekly", "house cleaning") is True
    assert icp.keyword_hit("greenhouse cleaning specialists", "house cleaning") is False
    assert icp.keyword_hit("powerhouse cleaning co", "house cleaning") is False
    assert icp.keyword_hit("snow removal and salting", "snow removal") is True
    assert icp.keyword_hit("", "snow removal") is False
    assert icp.keyword_hit("anything", "") is False


def test_serving_property_managers_is_not_a_hard_reject(cleaning):
    """Property managers are a commercial cleaner's biggest customer, so a page
    that names them is more often a good sign than a bad one. It stays in
    reject_signals for the model to weigh, not in hard_reject_keywords."""
    good = lead(
        company_name="Pristine Services",
        description="Commercial cleaning for property management companies.",
        keywords="commercial cleaning for property management companies",
    )
    assert icp.rule_verdict(good, cleaning)["verdict"] == icp.VERDICT_ACCEPT
    assert "property management" not in (cleaning.get("hard_reject_keywords") or [])


def test_the_offline_stand_in_uses_word_boundaries_too(cleaning):
    """The same substring bug lived in two places. A rehearsal that rejects
    'warehouse cleaning' as 'house cleaning' reports a pass rate the real model
    would never produce, which makes the whole cost model fiction."""
    industrial = lead(
        company_name="Harborline Facility Group",
        keywords="facility services, warehouse cleaning, industrial cleaning, distribution centers",
        description="Industrial and warehouse cleaning crews for distribution and logistics sites.",
    )
    prompt = icp.build_prompt([industrial], cleaning)
    answer = icp.offline_score(icp.SYSTEM, prompt, True)
    assert answer["results"][0]["verdict"] == icp.VERDICT_ACCEPT
