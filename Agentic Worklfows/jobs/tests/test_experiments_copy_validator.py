"""The extended copy validator (brief A7).

Everything runs against the copy the Phase 0 change-set already stages and the
live campaign objects recorded on 2026-09-22, so a rule that would break a
real apply fails here first.
"""
import copy

import pytest

from changesets.instantly_phase0 import phase0_lib as p0
from services.experiments import copy_validator as CV
from services.experiments.fakes import load_fixture
from shared import settings

CAMPAIGN_KEYS = [
    "cleaning_reactivation", "cleaning_trigger",
    "bookkeeping_reactivation", "bookkeeping_trigger",
    "recruiting_reactivation", "recruiting_outbound",
]


@pytest.fixture(scope="module")
def live_campaigns():
    return load_fixture("campaigns_2026-09-22.json")


@pytest.fixture(scope="module")
def settings_doc():
    return p0.load_settings()


def _sequence(key):
    return p0.load_sequence(key)


def _validate(key, live_campaigns, settings_doc, doc=None, **kw):
    return CV.validate_copy(
        key, doc if doc is not None else _sequence(key),
        live_campaigns[key], settings_doc, settings.OFFERS_MD, **kw
    )


# ------------------------------------------------- the staged copy still passes
def test_every_staged_phase0_sequence_passes_the_extended_validator(live_campaigns, settings_doc):
    """The extension must not turn a Phase 0 apply red. If this fails, either
    the staged copy broke or a new rule needs a warning instead of an error."""
    for key in CAMPAIGN_KEYS:
        rep = _validate(key, live_campaigns, settings_doc)
        assert rep.ok, rep.summary()


def test_the_readability_rule_is_a_warning_by_default_and_finds_the_long_sentences(
    live_campaigns, settings_doc
):
    """15 sentences in the staged copy run over 30 words in their longest
    rendering. They are warnings so the gate stays usable; strict mode is how
    new copy is held to the line. If this number moves, the staged copy moved:
    look at the list before changing it."""
    warned = 0
    for key in CAMPAIGN_KEYS:
        rep = _validate(key, live_campaigns, settings_doc)
        warned += len([w for w in rep.warnings if "longest rendering" in w])
    assert warned == 15


def test_strict_readability_turns_those_warnings_into_errors(live_campaigns, settings_doc):
    rep = _validate("cleaning_trigger", live_campaigns, settings_doc, strict_readability=True)
    assert not rep.ok
    assert any("longest rendering" in e for e in rep.errors)


# ---------------------------------------------------------------- new rules
def test_a_merge_variable_inside_a_spin_option_is_an_error(live_campaigns, settings_doc):
    """phase0_lib only catches an option that IS a variable. This is the shape
    that passes it and still breaks: a variable nested inside the option."""
    doc = _sequence("cleaning_reactivation")
    body = doc["sequences"][0]["steps"][0]["variants"][0]["body"]
    doc["sequences"][0]["steps"][0]["variants"][0]["body"] = body.replace(
        "{{RANDOM | Let me know. | Worth a look? | Open to it?}}",
        "{{RANDOM | Let me know {{firstName}}. | Worth a look? | Open to it?}}",
    )
    base = p0.validate_sequence("cleaning_reactivation", doc, live_campaigns["cleaning_reactivation"],
                                settings_doc, settings.OFFERS_MD)
    assert base.ok, "phase0_lib lets this through, which is why the extension exists"
    rep = _validate("cleaning_reactivation", live_campaigns, settings_doc, doc=doc)
    assert not rep.ok
    assert any("merge variable inside a spin option" in e for e in rep.errors)


def test_variables_inside_spins_finds_nesting_at_any_depth():
    text = "{{RANDOM | a | b {{RANDOM | c {{companyName}} | d}}}}"
    found = CV.variables_inside_spins(text)
    assert any("{{companyName}}" in f for f in found)


def test_a_spin_that_only_contains_other_spins_is_not_reported_as_a_variable():
    text = "{{RANDOM | {{RANDOM | a | b}} | c}}"
    assert CV.variables_inside_spins(text) == []


def test_two_proof_families_in_one_campaign_is_an_error(live_campaigns, settings_doc):
    doc = _sequence("cleaning_reactivation")
    step3 = doc["sequences"][0]["steps"][2]["variants"][0]
    step3["body"] = step3["body"] + "<div>I also generated about $180,000 in 90 days.</div>"
    rep = _validate("cleaning_reactivation", live_campaigns, settings_doc, doc=doc)
    assert not rep.ok
    assert any("two proof families" in e for e in rep.errors)


def test_proof_family_must_match_the_campaign_offer():
    assert CV.proof_families("recovered about $6M worth of contracts") == set(["reactivation"])
    assert CV.proof_families("generated about $180,000 in new contracts") == set(["outbound"])
    assert CV.proof_families("no numbers at all") == set()


def test_require_known_vars_promotes_the_new_variable_warning(live_campaigns, settings_doc):
    """cleaning_trigger's staged copy uses {{buildingType}} and {{metro}},
    which no live lead carries yet. Phase 0 ships that as a warning; the list
    factory should run the same gate with require_known_vars=True."""
    soft = _validate("cleaning_trigger", live_campaigns, settings_doc)
    assert soft.ok
    assert any("is NEW for this campaign" in w for w in soft.warnings)
    hard = _validate("cleaning_trigger", live_campaigns, settings_doc, require_known_vars=True)
    assert not hard.ok
    assert any("is NOT on the live campaign" in e for e in hard.errors)


# ------------------------------------------------- inherited rules still bite
@pytest.mark.parametrize("mutation,needle", [
    ("em_dash", "em dash"),
    ("bang", "exclamation mark"),
    ("money", "not in this campaign's offers.md"),
    ("unbalanced", "spintax/tag error"),
    ("unknown_var", "not in campaign variables"),
])
def test_inherited_rules_are_still_enforced(live_campaigns, settings_doc, mutation, needle):
    doc = _sequence("cleaning_reactivation")
    variant = doc["sequences"][0]["steps"][0]["variants"][0]
    if mutation == "em_dash":
        variant["body"] = variant["body"].replace("About me:", "About me —")
    elif mutation == "bang":
        variant["body"] = variant["body"].replace("Lorenzo", "Lorenzo!")
    elif mutation == "money":
        variant["body"] = variant["body"].replace("$6M worth", "$9,400,000 worth")
    elif mutation == "unbalanced":
        variant["body"] = variant["body"].replace("{{RANDOM | Let me know.", "{{RANDOM | Let me know.")
        variant["body"] = variant["body"] + "<div>{{RANDOM | a | b</div>"
    elif mutation == "unknown_var":
        variant["body"] = variant["body"].replace("Lorenzo", "{{notAVariable}}\nLorenzo")
    rep = _validate("cleaning_reactivation", live_campaigns, settings_doc, doc=doc)
    assert not rep.ok
    assert any(needle in e for e in rep.errors), rep.summary()


def test_spin_count_stays_between_three_and_five(live_campaigns, settings_doc):
    doc = _sequence("cleaning_reactivation")
    variant = doc["sequences"][0]["steps"][0]["variants"][0]
    variant["body"] = variant["body"].replace(
        "{{RANDOM | Let me know. | Worth a look? | Open to it?}}", "Let me know.")
    variant["body"] = variant["body"].replace(
        "{{RANDOM | Thanks, | Appreciate it, | Cheers,}}", "Thanks,")
    rep = _validate("cleaning_reactivation", live_campaigns, settings_doc, doc=doc)
    assert not rep.ok
    assert any("spin points" in e for e in rep.errors)


# ------------------------------------------------------------- the renderer
def test_render_picks_first_shortest_and_longest_options():
    text = "{{RANDOM | one | two words here}} tail"
    assert CV.render(text, "first") == "one tail"
    assert CV.render(text, "shortest") == "one tail"
    assert CV.render(text, "longest") == "two words here tail"


def test_render_counts_a_merge_variable_as_one_word():
    assert CV.render("Hey {{firstName}}, hi") == "Hey X, hi"


def test_sentences_do_not_split_on_a_decimal_or_a_price():
    got = CV.sentences("A $1.5k build. Another one")
    assert got == ["A $1.5k build", "Another one"]


def test_long_sentences_measures_the_worst_rendering():
    text = "{{RANDOM | Short. | " + " ".join(["word"] * 40) + ".}}"
    assert CV.long_sentences(text, 30, mode="shortest") == []
    assert len(CV.long_sentences(text, 30, mode="longest")) == 1


# -------------------------------------------------------------- single email
def test_validate_email_checks_one_body_without_a_campaign():
    body = ("{{RANDOM | Hey | Hi}} {{firstName}},\n\n"
            "{{RANDOM | Quick one. | Short one.}} I build reactivation systems.\n\n"
            "{{RANDOM | Thanks, | Cheers,}}\nLorenzo")
    rep = CV.validate_email("subject", body, known_variables=["firstName"])
    assert rep.ok, rep.summary()
    bad = CV.validate_email("subject!", body, known_variables=["firstName"])
    assert not bad.ok
    assert any("exclamation mark" in e for e in bad.errors)


def test_validate_email_rejects_an_unsigned_body():
    body = ("{{RANDOM | Hey | Hi}} there,\n\n{{RANDOM | One. | Two.}}\n\n{{RANDOM | Thanks, | Cheers,}}")
    rep = CV.validate_email("s", body)
    assert any("not signed Lorenzo" in e for e in rep.errors)


def test_report_object_is_the_one_the_changesets_already_consume():
    rep = CV.Report("x")
    assert rep.ok
    rep.error("where", "boom")
    assert not rep.ok and "boom" in rep.summary()
    assert isinstance(rep, p0.Report)


# ------------------------------------------- the proof markers are derived
def test_proof_markers_are_derived_from_offer_markers_not_hardcoded():
    """A change to offers.md / OFFER_MARKERS has to move these rules, not turn
    them into no-ops that always pass."""
    for family, markers in CV.PROOF_MARKERS.items():
        must = set(p0.OFFER_MARKERS[family]["must"])
        assert markers, family
        # every derived marker is either one of that family's must-markers or a
        # declared alternative spelling of one
        for marker in markers:
            aliases = set()
            for base in must:
                aliases |= set(CV.MARKER_ALIASES.get(base, ()))
            assert marker in must or marker in aliases, (family, marker)
    # "$150M" is on both families, so it can never decide which one this is.
    assert "$150M" not in CV.PROOF_MARKERS["reactivation"]
    assert "$150M" not in CV.PROOF_MARKERS["outbound"]
    assert CV.proof_families("The roofer does $150M a year") == set()


def test_alternative_spellings_of_the_proof_number_are_caught():
    assert CV.proof_families("$6M in 6 months") == {"reactivation"}
    assert CV.proof_families("$6,000,000 recovered") == {"reactivation"}
    assert CV.proof_families("$180K in 90 days") == {"outbound"}
    assert CV.proof_families("180,000 in new contracts") == {"outbound"}


def test_a_family_with_no_distinguishing_marker_fails_loudly(monkeypatch):
    """If both families ever carry the same must-markers the campaign-level
    proof rules would silently stop firing; that has to raise instead."""
    monkeypatch.setattr(p0, "OFFER_MARKERS", {
        "reactivation": {"must": ["$150M"], "forbid": []},
        "outbound": {"must": ["$150M"], "forbid": []},
    })
    with pytest.raises(RuntimeError) as exc:
        CV.assert_distinguishable(CV._distinguishing_markers())
    assert "no marker that distinguishes it" in str(exc.value)
