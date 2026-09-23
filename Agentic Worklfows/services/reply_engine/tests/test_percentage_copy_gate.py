"""Defect 8 (SAL-11 follow-up): the flat percentage check.

validate_draft refused any dollar figure offers.md does not state, but for
percentages it only caught one that belonged to ANOTHER offer. The reviewer's
probe:

* "I take 25% of first-year contract value" in a cleaning_trigger draft passed,
  while "$25" was refused;
* "twenty to thirty percent" was not read at all;
* "20 and 30 percent" flagged only 30.

And in the cadence the new percentage problems fell into the generic
``copy_rule:<sentence>`` code. Every percentage a draft states must now appear
in offers.md for some offer (today 20, 30 and the +35% P.S. proof); the one
exception is the certainty idiom "100% sure", which states no term.
"""
import json
from pathlib import Path

import pytest

from services.reply_engine import cadence, draft as draft_mod

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def body(line):
    return "Hey Jo,\n\n%s\n\nLorenzo" % line


def flat(problems):
    return [p for p in problems if p.endswith("% not in offers.md")]


# ------------------------------------------------------ the reviewer's probe
def test_an_off_sheet_percentage_is_refused_like_an_off_sheet_dollar_figure():
    pct = draft_mod.validate_draft(body("I take 25% of first-year contract value."), campaign_key="cleaning_trigger")
    assert "percentage 25% not in offers.md" in pct
    dollars = draft_mod.validate_draft(body("I take $25 of first-year contract value."), campaign_key="cleaning_trigger")
    assert "dollar figure $25 not in offers.md" in dollars
    # with no campaign key too: the flat check does not need to know the offer
    assert "percentage 25% not in offers.md" in draft_mod.validate_draft(body("I take 25% of fees."))


def test_spelled_out_percentages_are_read():
    problems = draft_mod.validate_draft(body("I take twenty to thirty percent of fees."), campaign_key="cleaning_trigger")
    assert any("percentage 20%" in p and "cleaning_reactivation" in p for p in problems)
    assert any("percentage 30%" in p and "cleaning_reactivation" in p for p in problems)
    assert flat(draft_mod.validate_draft(body("I take twenty-five percent of fees."))) == \
        ["percentage 25% not in offers.md"]


def test_both_numbers_of_a_list_are_read():
    problems = draft_mod.validate_draft(body("It is 20 and 30 percent of fees."), campaign_key="cleaning_trigger")
    assert any("percentage 20%" in p for p in problems)
    assert any("percentage 30%" in p for p in problems)
    assert flat(draft_mod.validate_draft(body("It is 40 and 45 percent of fees."))) == \
        ["percentage 40% not in offers.md", "percentage 45% not in offers.md"]


# --------------------------------------------------------------- normaliser
@pytest.mark.parametrize("text,expected", [
    ("25%", ["25"]),
    ("25 %", ["25"]),
    ("25 percent", ["25"]),
    ("25 per cent", ["25"]),
    ("25-percent", ["25"]),
    ("25.5%", ["25.5"]),
    ("10 pct", ["10"]),
    ("20-30%", ["20", "30"]),
    ("20–30%", ["20", "30"]),
    ("20 to 30 percent", ["20", "30"]),
    ("20% to 30%", ["20", "30"]),
    ("between 20% and 30%", ["20", "30"]),
    ("20 and 30 percent", ["20", "30"]),
    ("20, 25 or 30 percent", ["20", "25", "30"]),
    ("twenty to thirty percent", ["20", "30"]),
    ("twenty-five percent", ["25"]),
    ("between fifteen and forty per cent", ["15", "40"]),
    ("a hundred percent", ["100"]),
    ("one hundred percent", ["100"]),
    ("one hundred and twenty percent", ["120"]),
    ("1,000%", ["1000"]),
    # a number after the last percent word is not a percentage
    ("20% to 30 accounts", ["20"]),
    # a list of 60 accounts is not part of the range that follows it
    ("60 or more accounts, 20 to 30 percent", ["20", "30"]),
    # "$20" is a dollar figure and "12:30" a clock time
    ("$20 to 30 percent", ["30"]),
    ("12:30 to 40%", ["40"]),
    # no number at all
    ("a percentage of placement fees", []),
    ("often tenants", []),
])
def test_the_normaliser(text, expected):
    assert draft_mod._norm_percents(text) == expected  # noqa: SLF001


def test_the_offer_sheet_states_the_reactivation_range_and_the_ps_proof():
    allowed = set(draft_mod.allowed_percent_figures())
    assert {"20", "30", "35"} <= allowed


# ------------------------------------------------------------ false positives
@pytest.mark.parametrize("key", ["cleaning_reactivation", "bookkeeping_reactivation", "recruiting_reactivation"])
def test_every_reactivation_pricing_line_still_passes(key):
    assert draft_mod.validate_draft(body(draft_mod.PRICING[key]), campaign_key=key) == []


@pytest.mark.parametrize("key", sorted(draft_mod.PRICING))
def test_no_shipped_pricing_line_states_an_off_sheet_percentage(key):
    assert draft_mod.unlisted_percent_figures(draft_mod.PRICING[key]) == []


def test_the_ps_proof_and_the_spelled_out_range_pass_the_flat_check():
    ps = body("Happy to walk you through it.\n\nP.S. A consultancy saw +35% reply rate.")
    assert flat(draft_mod.validate_draft(ps, campaign_key="cleaning_trigger")) == []
    assert draft_mod.validate_draft(body("I take twenty to thirty percent of fees."),
                                    campaign_key="bookkeeping_reactivation") == []


@pytest.mark.parametrize("line", ["I am 100% sure it fits.", "I am a hundred percent sure it fits.",
                                  "100 percent agree with you."])
def test_the_certainty_idiom_is_allowed(line):
    assert flat(draft_mod.validate_draft(body(line))) == []


@pytest.mark.parametrize("line", ["We show up to 100% of the calls.", "You get 100% of your money back.",
                                  "A hundred percent money-back guarantee.", "I keep 50 percent of the setup fee."])
def test_a_figure_that_reads_as_a_claim_or_a_term_is_refused(line):
    assert flat(draft_mod.validate_draft(body(line)))


def test_the_prospects_own_name_is_not_our_percentage():
    text = body("Happy to talk with the team at 110 Percent Cleaning.")
    assert flat(draft_mod.validate_draft(text)) == ["percentage 110% not in offers.md"]
    assert flat(draft_mod.validate_draft(text, allow_terms=["110 Percent Cleaning"])) == []
    # blanking the name does not blank a figure we wrote next to it
    text2 = body("110 Percent Cleaning would pay 25% of fees.")
    assert flat(draft_mod.validate_draft(text2, allow_terms=["110 Percent Cleaning"])) == \
        ["percentage 25% not in offers.md"]


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_no_recorded_fixture_states_an_off_sheet_percentage():
    """Lorenzo's own sent mail ("between 20% and 30% of first-year fees") is
    the only percentage in the fixtures, and it is on the sheet."""
    seen = 0
    for path in sorted(FIXTURES.glob("*.json")):
        for text in _strings(json.loads(path.read_text(encoding="utf-8"))):
            if draft_mod._norm_percents(text):  # noqa: SLF001
                seen += 1
                assert draft_mod.unlisted_percent_figures(text) == [], (path.name, text[:200])
    assert seen >= 1


# ------------------------------------------------------------ cadence codes
def test_the_flat_problem_has_its_own_cadence_code():
    codes = cadence.shared_problems(body("I take 25% of first-year contract value."), campaign_key="cleaning_trigger")
    assert codes == ["percentage_not_in_offer_sheet"]
    # a dollar figure keeps its own code; the two needles do not collide
    assert cadence.shared_problems(body("I take $25 a month.")) == ["money_not_in_offer_sheet"]


def test_the_cross_offer_problem_has_its_own_cadence_code():
    codes = cadence.shared_problems(body("I take twenty to thirty percent of fees."), campaign_key="cleaning_trigger")
    assert codes == ["percentage_from_another_offer"]


@pytest.mark.parametrize("line,key", [
    ("I take 25% of first-year contract value.", "cleaning_trigger"),
    ("I take twenty-five percent of fees.", "cleaning_reactivation"),
    ("It is 20 and 30 percent of fees.", "bookkeeping_trigger"),
    ("It is 40 and 45 percent of fees.", None),
    ("We added about 12% more.", "recruiting_outbound"),
])
def test_no_percentage_problem_arrives_as_a_generic_copy_rule(line, key):
    codes = cadence.shared_problems(body(line), campaign_key=key)
    assert codes
    assert not [c for c in codes if c.startswith("copy_rule:")], codes


def test_the_blocked_copy_alert_reads_cleanly():
    touch_problems = cadence.copy_problems(body("I take twenty to thirty percent of fees."),
                                           campaign_key="cleaning_trigger")
    line = cadence.summarize_touch({"action": "blocked_copy", "day": 3, "lead_email": "jo@x.com",
                                    "problems": touch_problems})
    assert line == "D3 -> jo@x.com: BLOCKED, copy check failed (percentage_from_another_offer)"
