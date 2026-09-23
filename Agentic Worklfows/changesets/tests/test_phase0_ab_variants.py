"""M3.3: two variants on EVERY step of every staged Phase 0 sequence.

Blueprint M3.3 asks for an A/B pair on each of the three steps. The staged
sequences carried a B variant on step 1 only, so steps 2 and 3 ran one body for
1,000 sends and the verdict job had nothing to compare. These tests pin the
pair on every step and hold the new copy to the rules the repo already proves
elsewhere, plus two that nothing pinned before:

* no variant may quote a figure that config/offers.md marks **TO CONFIRM**
  (``phase0_lib.validate_sequence`` reads the whole offers.md row, so the
  unconfirmed $2,500-5,000/mo retainer passes its money check today);
* the B body must be a different angle, not a reworded A.

Run: cd "Agentic Worklfows" && python3 -m pytest changesets/tests/test_phase0_ab_variants.py -q
"""
import difflib
import json
import os
import re

import pytest

from changesets.instantly_phase0 import phase0_lib as L
from services.experiments import copy_validator as CV
from services.experiments.fakes import load_fixture
from shared import settings

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAPSHOT = os.path.join(ROOT, "config", "snapshots", "instantly_campaigns_2026-09-21.json")
KEYS = [
    "cleaning_reactivation", "cleaning_trigger", "bookkeeping_reactivation",
    "bookkeeping_trigger", "recruiting_reactivation", "recruiting_outbound",
]

# Two bodies that share more than this much of their text are the same email
# twice: the M3.3 verdict at 500 sends each would be measuring noise. The six
# staged pairs sit at 0.39 or below today.
MAX_AB_SIMILARITY = 0.6


@pytest.fixture(scope="module")
def snapshot():
    with open(SNAPSHOT, "r", encoding="utf-8") as fh:
        return {c["id"]: c for c in json.load(fh)["items"]}


@pytest.fixture(scope="module")
def cfg():
    return L.load_settings()


@pytest.fixture(scope="module")
def offers_md():
    with open(os.path.join(ROOT, "config", "offers.md"), "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def live_campaigns():
    return load_fixture("campaigns_2026-09-22.json")


def _blob(var):
    return (var.get("subject") or "") + "\n" + L.html_to_text(var.get("body") or "")


def _figures(text):
    """Every money figure in ``text``, the way phase0_lib reads offers.md rows:
    $-prefixed amounts plus bare four-figure-or-larger numbers, so the second
    half of a range written "$2,500-5,000/mo" is picked up too."""
    vals = L.money_values(text)
    for m in L.BARE_AMOUNT_RE.finditer(text):
        raw = m.group(1)
        num = float(raw.replace(",", ""))
        if "," in raw or num >= 1000:
            vals.add(round(num, 2))
    return vals


def to_confirm_figures(offers_md):
    """Figures inside a sentence of config/offers.md marked TO CONFIRM.

    Only the sentence, never the whole row: the cleaning_trigger row carries
    the agreed $24,000 guarantee and the unconfirmed $2,500-5,000/mo retainer
    in the same cell.
    """
    out = set()
    for line in offers_md.splitlines():
        if "TO CONFIRM" not in line:
            continue
        for cell in line.split("|"):
            for sentence in re.split(r"(?<=\.)\s+", cell):
                if "TO CONFIRM" in sentence:
                    out |= _figures(sentence)
    return out


# ------------------------------------------------------------- the A/B pairs
@pytest.mark.parametrize("key", KEYS)
def test_every_step_has_exactly_two_variants(key):
    """phase0_lib only ever required the pair on step 1."""
    steps = L.load_sequence(key)["sequences"][0]["steps"]
    assert len(steps) == 3
    assert [len(st["variants"]) for st in steps] == [2, 2, 2]


@pytest.mark.parametrize("key", KEYS)
def test_the_thread_rules_hold_for_the_b_variants_too(key, cfg):
    """Step 2 stays in the step 1 thread, so BOTH its variants keep an empty
    subject. Step 3 opens a new thread and both variants use the same fresh
    subject, so the verdict compares bodies and nothing else."""
    steps = L.load_sequence(key)["sequences"][0]["steps"]
    assert [v["subject"] for v in steps[1]["variants"]] == ["", ""]
    want = cfg["campaigns"][key]["step3_subject"]
    assert [v["subject"] for v in steps[2]["variants"]] == [want, want]
    assert steps[0]["variants"][0]["subject"] == steps[0]["variants"][1]["subject"] != ""


@pytest.mark.parametrize("key", KEYS)
def test_every_variant_passes_both_validators(key, snapshot, cfg, offers_md, live_campaigns):
    doc = L.load_sequence(key)
    base = L.validate_sequence(key, doc, snapshot[cfg["campaigns"][key]["id"]], cfg, offers_md)
    assert base.ok, base.summary()
    extended = CV.validate_copy(key, doc, live_campaigns[key], cfg, settings.OFFERS_MD)
    assert extended.ok, extended.summary()


@pytest.mark.parametrize("key", KEYS)
def test_the_b_variant_is_a_different_angle_not_a_reworded_a(key):
    doc = L.load_sequence(key)
    for si, step in enumerate(doc["sequences"][0]["steps"]):
        a = L.html_to_text(step["variants"][0]["body"])
        b = L.html_to_text(step["variants"][1]["body"])
        assert a != b
        ratio = difflib.SequenceMatcher(None, a, b).ratio()
        assert ratio < MAX_AB_SIMILARITY, "%s step%d: A and B are %.0f%% the same text" % (
            key, si + 1, ratio * 100)
        # The greeting line is shared on purpose (it is the same spun opener);
        # the paragraph under it is the angle, and that has to differ.
        assert a.split("\n\n")[1] != b.split("\n\n")[1], (key, si + 1)


@pytest.mark.parametrize("key", KEYS)
def test_the_new_b_variants_carry_their_own_frame(key):
    """Step 2 B asks one question and offers a "not now" out instead of
    repeating A's three bullets; step 3 B closes the file instead of pitching a
    fourth time. If a future edit makes B a copy of A's frame, this fails."""
    steps = L.load_sequence(key)["sequences"][0]["steps"]
    step2_a, step2_b = [L.html_to_text(v["body"]) for v in steps[1]["variants"]]
    step3_a, step3_b = [L.html_to_text(v["body"]) for v in steps[2]["variants"]]
    assert "not now" in step2_b.lower() and "not now" not in step2_a.lower()
    assert "one question" in step2_b.lower() and "one question" not in step2_a.lower()
    assert "close the file" in step3_b.lower() or "closing the file" in step3_b.lower()
    assert "close the file" not in step3_a.lower() and "closing the file" not in step3_a.lower()


# ------------------------------------------------------------ the copy rules
@pytest.mark.parametrize("key", KEYS)
def test_every_variant_has_three_to_five_spin_points_and_none_on_a_merge_variable(key):
    doc = L.load_sequence(key)
    for si, vi, _step, var in L.iter_variants(doc):
        blob = _blob(var)
        spins = list(L.iter_spins(blob))
        assert L.MIN_SPINS <= len(spins) <= L.MAX_SPINS, (key, si, vi, len(spins))
        for raw, options in spins:
            assert len(set(options)) == len(options) == len([o for o in options if o.strip()]), raw
        # never on the merge variables (M3.2): not as an option, not nested in one
        assert CV.variables_inside_spins(blob) == [], (key, si, vi)


@pytest.mark.parametrize("key", KEYS)
def test_no_prospect_facing_string_carries_a_dash_or_an_exclamation_mark(key):
    for si, vi, _step, var in L.iter_variants(L.load_sequence(key)):
        blob = _blob(var)
        assert L.EM_DASH not in blob and L.EN_DASH not in blob, (key, si, vi)
        assert "!" not in blob, (key, si, vi)
        assert not L.AI_RE.search(blob), (key, si, vi)


@pytest.mark.parametrize("key", KEYS)
def test_one_proof_point_per_campaign_identical_across_steps_and_variants(key, cfg):
    """Every step 1 and step 2 variant carries the campaign's own proof
    numbers, verbatim from config/offers.md, and no variant anywhere in the
    campaign carries the other offer type's."""
    offer = cfg["campaigns"][key]["offer"]
    markers = L.OFFER_MARKERS[offer]
    families = set()
    for si, vi, _step, var in L.iter_variants(L.load_sequence(key)):
        text = L.html_to_text(var["body"])
        if si in (0, 1):
            assert all(m in text for m in markers["must"]), (key, si, vi)
        for bad in markers["forbid"]:
            assert bad not in text, (key, si, vi, bad)
        families |= CV.proof_families(text)
    assert families == set([offer]), (key, families)


def test_no_variant_quotes_a_figure_marked_to_confirm(offers_md):
    """offers.md marks the $2,500-5,000/mo retainer TO CONFIRM with Lorenzo.

    ``validate_sequence`` cannot catch this: it allows every figure in the
    campaign's offers.md row and the retainer is in that row, so a price
    Lorenzo has not agreed to would ship as a contractual promise in a cold
    email. Nothing else in the suite pins it.
    """
    pending = to_confirm_figures(offers_md)
    assert pending, "offers.md no longer marks any figure TO CONFIRM; drop or rewrite this test"
    for key in KEYS:
        for si, vi, _step, var in L.iter_variants(L.load_sequence(key)):
            quoted = _figures(_blob(var)) & pending
            assert not quoted, "%s step%d/variant%d quotes the unconfirmed figure(s) %s" % (
                key, si + 1, vi, sorted(quoted))


def test_the_new_b_copy_keeps_every_sentence_readable():
    """The staged A copy carries 15 sentences over 30 words in their longest
    rendering, and jobs/tests/test_experiments_copy_validator.py pins that
    number. New copy is held to the line instead of moving it: every B body on
    steps 2 and 3 reads under 30 words a sentence, worst case."""
    for key in KEYS:
        for si, vi, _step, var in L.iter_variants(L.load_sequence(key)):
            if si >= 1 and vi == 1:
                assert CV.long_sentences(_blob(var)) == [], (key, si, vi)


@pytest.mark.parametrize("key", KEYS)
def test_every_variant_is_signed_and_ends_the_way_the_snapshot_does(key):
    for si, vi, _step, var in L.iter_variants(L.load_sequence(key)):
        text = L.html_to_text(var["body"])
        assert "Lorenzo" in text, (key, si, vi)
        assert text.rstrip().endswith("Lorenzo") or "P.S." in text, (key, si, vi)
