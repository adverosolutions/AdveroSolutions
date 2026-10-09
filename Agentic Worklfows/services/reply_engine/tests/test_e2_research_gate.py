"""E2: the template gate's side of the researched day 2 line.

Lorenzo approves the cadence.d2 frame and the research rules
(cadence.d2.research_rules) once; a day 2 touch with a per-lead line then
auto-sends only when the gate itself runs research_rules.validate on the line
in the body and every check passes.

section 1 owns services/reply_engine/research_rules.py and has not written it
yet, so every test here injects a STUB module into sys.modules (monkeypatch,
undone after each test) and clears both catalogue caches. The last test
checks nothing leaked: the real catalogue still has 108 approvable ids.
No network, no LLM, no live flags; tmp approvals and parity files only.
"""
import copy
import dataclasses
import sys
import types

import pytest

from shared import notify, settings
from shared.paths import BASE_DIR

from services.reply_engine import cadence
from services.reply_engine import template_approvals as ta
from services.reply_engine import template_gate as gate
from services.reply_engine.tests import template_fixtures as tf

REAL_APPROVALS = BASE_DIR / "config" / "approved_templates.json"
REAL_REFERENCE = BASE_DIR / "config" / "template_catalogue_hashes.json"
MODULE = ta.RESEARCH_RULES_MODULE
RULES_ID = ta.RESEARCH_RULES_ID
FALLBACK_R = "cadence.d2.research_fallback.reactivation"
FALLBACK_O = "cadence.d2.research_fallback.outbound"
FIRST = "Jordan"
COMPANY = "Brightline Test Co"
LINK = "https://example.invalid/book"
TWO = [ta._ct(2030, 1, 8, 13, 0), ta._ct(2030, 1, 10, 15, 30)]
LINE = "Your site says your crews clean dental offices across Tulsa at night."
EVIDENCE = {
    "facts": [{"fact": "crews clean dental offices across Tulsa at night",
               "source_url": "https://brightline.example/services",
               "excerpt": "Our night crews clean dental offices across Tulsa."}],
    "identity_pages": ["https://brightline.example/about"],
}
CONTEXT = {"website_domain": "brightline.example", "offer_branch": "reactivation", "niche": "cleaning"}
RULES = ("A researched line states one fact the lead's own website says, in plain words.\n"
         "It names no figure, price, percentage, person or competitor, and makes no claim about results.\n"
         "Every fact has a source page on the lead's own domain with an excerpt that says it.")
APPROVABLE_TODAY = 108
UNIT = "Your crews clean offices in Tulsa. "


@dataclasses.dataclass(frozen=True)
class ResearchVerdict(object):
    ok: bool
    line: str
    reasons: tuple
    rules_sha: str


def make_stub(text=RULES, version=1):
    """A stand-in for section 1's research_rules module. ``behaviour`` steers
    what validate returns; ``calls`` records every call."""
    mod = types.ModuleType(MODULE)
    mod.RULES_TEXT = text
    mod.RULES_VERSION = version
    mod.ResearchVerdict = ResearchVerdict
    mod.calls = []
    mod.behaviour = {"ok": True, "reasons": (), "line": None, "sha": None, "raise": None, "result": None}

    def validate(line, evidence, context):
        mod.calls.append({"line": line, "evidence": evidence, "context": context})
        b = mod.behaviour
        if b["raise"] is not None:
            raise b["raise"]
        if b["result"] is not None:
            return b["result"]
        sha = b["sha"] if b["sha"] is not None else ta.research_rules_sha(mod.RULES_TEXT, mod.RULES_VERSION)
        return ResearchVerdict(ok=b["ok"], line=b["line"] if b["line"] is not None else line,
                               reasons=tuple(b["reasons"]), rules_sha=sha)
    mod.validate = validate
    return mod


def _bytes(p):
    return p.read_bytes() if p.exists() else None


def _clear():
    ta.clear_cache()
    gate.clear_cache()


def _base_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setattr(notify, "notify", lambda *a, **k: {"sent": False, "test": True})
    monkeypatch.setattr(settings, "BOOKING_URL", LINK)


@pytest.fixture
def stub(monkeypatch, tmp_path):
    """The stub module installed, a tmp approvals file approving cadence.d2,
    both fallback lines and the research rules, and a parity reference that
    matches the catalogue with the stub in it."""
    before = (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE))
    _base_env(monkeypatch, tmp_path)
    mod = make_stub()
    monkeypatch.setitem(sys.modules, MODULE, mod)
    _clear()
    env = tf.make_template_env(monkeypatch, tmp_path)
    env.approve_ids("cadence.d2", FALLBACK_R, FALLBACK_O, RULES_ID)
    mod.env = env
    yield mod
    monkeypatch.delitem(sys.modules, MODULE, raising=False)
    _clear()
    assert (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE)) == before, "a test wrote a real config file"


@pytest.fixture
def no_stub(monkeypatch, tmp_path):
    """No rules module at all (today's state)."""
    before = (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE))
    _base_env(monkeypatch, tmp_path)
    monkeypatch.delitem(sys.modules, MODULE, raising=False)
    _clear()
    env = tf.make_template_env(monkeypatch, tmp_path)
    env.approve_ids("cadence.d2", FALLBACK_R, FALLBACK_O)
    yield env
    _clear()
    assert (_bytes(REAL_APPROVALS), _bytes(REAL_REFERENCE)) == before, "a test wrote a real config file"


# ------------------------------------------------------------- builders
def _state(offer="reactivation", niche="cleaning"):
    return types.SimpleNamespace(first_name=FIRST, company=COMPANY, niche=niche, offer=offer,
                                 campaign_key="%s_%s" % (niche, offer), campaign_id=None, phone=None, specialty=None,
                                 website="https://brightline.example", last_subject="Quick question", subject=None,
                                 thread_subject=None, lead_email="lead@example.invalid", ghl_contact_id=None,
                                 cadence={})


def researched(line=LINE, offer="reactivation", evidence=None, parts=(RULES_ID,), main="cadence.d2"):
    """(touch, bindings): day 2 rendered with ``line`` the way section 1 will
    hand it over (meta research_line / research_evidence / research_source,
    the rules part), stamped, with the research context in the bindings."""
    st = _state(offer)
    t = cadence.build_touch(st, 2, [s.isoformat() for s in TWO], research_line=line)
    t.meta["research_source"] = "researched"
    t.meta["research_evidence"] = copy.deepcopy(EVIDENCE if evidence is None else evidence)
    gate.stamp(t, main, list(parts))
    b = cadence.touch_bindings(st, t)
    b.update(CONTEXT)
    b["offer_branch"] = offer if offer in ("reactivation", "outbound") else "outbound"
    return t, b


def with_body_line(t, new_line, meta_line=None):
    """Put ``new_line`` in the body where the research line was (build_touch
    would sanitize it), and in meta unless ``meta_line`` says otherwise."""
    old = t.meta["research_line"]
    assert old in t.body_text
    t.body_text = t.body_text.replace(old, new_line)
    t.meta["research_line"] = new_line if meta_line is None else meta_line
    return t


def fallback_touch(offer="reactivation", part_offer=None):
    st = _state(offer)
    t = cadence.build_touch(st, 2, [s.isoformat() for s in TWO],
                            research_line=cadence.fallback_research_line(COMPANY, offer))
    gate.stamp(t, "cadence.d2", ["cadence.d2.research_fallback.%s" % (part_offer or offer)])
    return t, cadence.touch_bindings(st, t)


def verdict(t, b):
    return gate.touch_verdict(t, b)


# ------------------------------------------------------------ the entry
def test_the_rules_entry_is_approvable_with_the_module(stub):
    e = ta.catalogue_index()[RULES_ID]
    assert e["kind"] == ta.RESEARCH_RULES_KIND and e["approvable"] and e["extractable"]
    assert e["review_text"] == RULES + "\n\nRULES_VERSION: 1"
    assert e["sha256"] == ta.text_hash(e["review_text"]) == ta.research_rules_sha(RULES, 1)
    assert e["variables"] == []
    assert gate.research_rules_sha(stub) == e["sha256"]
    approvable = [tid for tid, x in ta.catalogue_index().items() if x["approvable"]]
    assert len(approvable) == APPROVABLE_TODAY + 1
    assert RULES_ID in gate.ladder_ids()
    assert ta.status(RULES_ID) == ta.STATUS_APPROVED
    assert gate.ids_verdict("cadence.d2", [RULES_ID]).allowed


def test_module_missing_rules_not_approvable_and_e2_refused(no_stub):
    idx = ta.catalogue_index()
    e = idx[RULES_ID]
    assert not e["approvable"] and not e["extractable"] and e["sha256"] is None
    assert e["explanation"] == "the research rules module is not there yet"
    assert sum(1 for x in idx.values() if x["approvable"]) == APPROVABLE_TODAY
    assert RULES_ID not in gate.unextractable_ladder_ids(idx)       # not there yet is by design
    with pytest.raises(ta.ApprovalError):
        tf.approve_ids(RULES_ID, path=no_stub.approvals_path)
    t, b = researched()
    v = verdict(t, b)
    assert not v.allowed and v.reason == "not_approvable", v
    assert gate.ids_verdict("cadence.d2", [RULES_ID]).reason == "not_approvable"


@pytest.mark.parametrize("breakage", ["empty_text", "bad_version", "bool_version", "no_validate", "raises"])
def test_a_broken_rules_module_is_not_approvable(monkeypatch, tmp_path, breakage):
    _base_env(monkeypatch, tmp_path)
    mod = make_stub()
    if breakage == "empty_text":
        mod.RULES_TEXT = "  \n"
    elif breakage == "bad_version":
        mod.RULES_VERSION = "1"
    elif breakage == "bool_version":
        mod.RULES_VERSION = True
    elif breakage == "no_validate":
        del mod.validate
    if breakage == "raises":
        # a module file that raises on import: import_module sees the error
        def boom(name, *a, **k):
            if name == MODULE:
                raise RuntimeError("rules module broke")
            return real(name, *a, **k)
        real = ta.importlib.import_module
        monkeypatch.setattr(ta.importlib, "import_module", boom)
    else:
        monkeypatch.setitem(sys.modules, MODULE, mod)
    _clear()
    try:
        idx = ta.catalogue_index()
        e = idx[RULES_ID]
        assert not e["approvable"] and not e["extractable"] and e["explanation"]
        assert not e.get("unextractable_by_design")
        assert RULES_ID in gate.unextractable_ladder_ids(idx)      # broken IS reported
        assert sum(1 for x in idx.values() if x["approvable"]) == APPROVABLE_TODAY
    finally:
        monkeypatch.undo()
        _clear()


# ---------------------------------------------------------- the good path
def test_a_validated_line_with_evidence_and_context_is_allowed(stub):
    t, b = researched()
    v = verdict(t, b)
    assert v.allowed and v.reason == "ok", v
    assert v.ids == ["cadence.d2", RULES_ID]
    assert v.statuses == {"cadence.d2": "approved", RULES_ID: "approved"}
    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["line"] == LINE
    assert call["evidence"] == EVIDENCE and call["evidence"] is not t.meta["research_evidence"]
    assert call["context"] == {"company": COMPANY, "website_domain": "brightline.example",
                               "offer_branch": "reactivation", "niche": "cleaning"}


def test_an_outbound_lead_is_allowed_too(stub):
    t, b = researched(offer="outbound")
    assert verdict(t, b).allowed
    assert stub.calls[-1]["context"]["offer_branch"] == "outbound"


def test_a_line_of_exactly_300_characters_is_allowed(stub):
    line = (UNIT * 20)[:299] + "."
    assert len(line) == 300 and line == line.strip()
    t, b = researched()
    with_body_line(t, line)
    v = verdict(t, b)
    assert v.allowed, v


def test_the_no_slots_variant_takes_a_researched_line(stub):
    st = _state()
    t = cadence.build_touch(st, 2, [], research_line=LINE)
    t.meta["research_evidence"] = copy.deepcopy(EVIDENCE)
    gate.stamp(t, "cadence.d2", [RULES_ID])
    b = cadence.touch_bindings(st, t)
    b.update(CONTEXT)
    assert verdict(t, b).allowed


# ---------------------------------------------------- the old paths stay
def test_the_fallback_path_is_unchanged(stub):
    t, b = fallback_touch("reactivation")
    assert verdict(t, b).allowed
    t, b = fallback_touch("outbound")
    assert verdict(t, b).allowed
    t, b = fallback_touch("reactivation", part_offer="outbound")
    v = verdict(t, b)
    assert not v.allowed and v.reason == "nonconforming"
    assert stub.calls == []                     # the fallback path never asks the rules


def test_the_fallback_path_is_unchanged_without_the_module(no_stub):
    t, b = fallback_touch("reactivation")
    assert verdict(t, b).allowed
    t, b = fallback_touch("reactivation", part_offer="outbound")
    assert verdict(t, b).reason == "nonconforming"


def test_the_llm_research_line_part_is_still_refused(stub):
    t, b = researched(parts=("cadence.d2.research_line",))
    v = verdict(t, b)
    assert not v.allowed and v.reason == "not_approvable"
    assert not ta.catalogue_index()["cadence.d2.research_line"]["approvable"]


def test_a_fallback_line_cannot_pass_as_research_without_its_own_part(stub):
    # the fallback text in the body under the rules part is a researched line
    # like any other: it must be what meta says and pass validate
    t, b = fallback_touch("reactivation")
    t.meta["research_evidence"] = copy.deepcopy(EVIDENCE)
    gate.stamp(t, "cadence.d2", [RULES_ID])
    b.update(CONTEXT)
    stub.behaviour["ok"] = False
    stub.behaviour["reasons"] = ("no fact from the site",)
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_rules_failed"


def test_the_rules_part_with_the_fallback_part_is_refused(stub):
    t, b = researched(parts=(RULES_ID, FALLBACK_R))
    v = verdict(t, b)
    assert not v.allowed and v.reason == "nonconforming"


def test_the_rules_part_on_another_day_is_refused(stub):
    stub.env.approve_ids("cadence.d4", "cadence.d4.case_study.reactivation")
    st = _state()
    t = cadence.build_touch(st, 4, [s.isoformat() for s in TWO])
    t.meta["research_line"] = LINE
    t.meta["research_evidence"] = copy.deepcopy(EVIDENCE)
    gate.stamp(t, "cadence.d4", [RULES_ID])
    b = cadence.touch_bindings(st, t)
    b.update(CONTEXT)
    v = verdict(t, b)
    assert not v.allowed and v.reason == "unknown_id"
    assert stub.calls == []


def test_the_rules_part_never_conforms_outside_the_touch_verdict(stub):
    t, b = researched()
    assert gate.conforms("cadence.d2", t.body_text, t.subject, [RULES_ID], b) is False
    assert gate.conforms(RULES_ID, RULES) is False


def test_the_rules_part_is_not_a_main_template(stub):
    t, b = researched(main=RULES_ID, parts=())
    assert verdict(t, b).reason == "unknown_id"


# ------------------------------------------------- the rules change
@pytest.mark.parametrize("change", ["text", "version"])
def test_changed_rules_are_changed_since_approval(stub, change):
    t, b = researched()
    assert verdict(t, b).allowed
    if change == "text":
        stub.RULES_TEXT = RULES + "\nIt never names a competitor."
    else:
        stub.RULES_VERSION = 2
    gate.clear_cache()
    # the deployed parity reference no longer matches: refused before anything else
    assert verdict(t, b).reason == "parity_failed"
    # after the deploy preflight rewrote the reference, the approval no longer holds
    stub.env.write_reference()
    v = verdict(t, b)
    assert not v.allowed and v.reason == "changed_since_approval"
    assert v.statuses[RULES_ID] == "changed_since_approval"
    # a touch stamped under the new rules is still refused until approved again
    t2, b2 = researched()
    assert verdict(t2, b2).reason == "changed_since_approval"
    stub.env.approve_ids(RULES_ID)
    assert verdict(t2, b2).allowed
    # and the old stamp is stale
    assert verdict(t, b).reason == "stale_render"


def test_rules_changed_after_the_catalogue_was_read_are_refused(stub, monkeypatch):
    t, b = researched()
    real = gate._index

    def index_then_change(key=None):
        idx = real(key)
        stub.RULES_VERSION = 7          # changes between the catalogue read and the validate call
        return idx
    monkeypatch.setattr(gate, "_index", index_then_change)
    v = verdict(t, b)
    assert not v.allowed and v.reason == "changed_since_approval"
    assert stub.calls == []


def test_the_module_going_away_after_the_catalogue_was_read_is_unavailable(stub, monkeypatch):
    t, b = researched()
    real = gate._index

    def index_then_drop(key=None):
        idx = real(key)
        sys.modules.pop(MODULE, None)
        return idx
    monkeypatch.setattr(gate, "_index", index_then_drop)
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_rules_unavailable"


# ---------------------------------------------------- the validator's say
def test_a_failing_validator_refuses_with_its_reasons(stub):
    stub.behaviour["ok"] = False
    stub.behaviour["reasons"] = ("fact_not_in_excerpt", "names_a_figure")
    t, b = researched()
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_rules_failed"
    assert "fact_not_in_excerpt" in v.detail and "names_a_figure" in v.detail
    assert "detail" not in v.to_record()


@pytest.mark.parametrize("ok", [1, "true", None, "yes"])
def test_only_ok_true_passes(stub, ok):
    stub.behaviour["ok"] = ok
    t, b = researched()
    assert verdict(t, b).reason == "research_rules_failed"


def test_a_raising_validator_refuses_and_says_so(stub, caplog):
    stub.behaviour["raise"] = ValueError("evidence page unreadable")
    t, b = researched()
    with caplog.at_level("WARNING", logger="reply_engine.template_gate"):
        v = verdict(t, b)
    assert not v.allowed and v.reason == "research_rules_error"
    assert "ValueError" in v.detail
    assert any("research_rules.validate raised" in r.getMessage() for r in caplog.records)


def test_a_validator_that_returns_no_verdict_refuses(stub):
    stub.behaviour["result"] = {"ok": True, "line": LINE, "reasons": (), "rules_sha": gate.research_rules_sha(stub)}
    t, b = researched()
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_rules_error"


def test_a_rules_sha_mismatch_refuses(stub):
    stub.behaviour["sha"] = "0" * 64
    t, b = researched()
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_rules_sha_mismatch"


def test_a_module_rules_sha_is_the_expected_sha(stub):
    stub.rules_sha = lambda: "c" * 64
    t, b = researched()
    assert verdict(t, b).reason == "research_rules_sha_mismatch"   # the stub still reports the default
    stub.behaviour["sha"] = "c" * 64
    assert verdict(t, b).allowed


def test_a_rules_sha_that_raises_is_unavailable(stub):
    def broken():
        raise RuntimeError("no sha")
    stub.rules_sha = broken
    t, b = researched()
    v = verdict(t, b)
    assert v.reason == "research_rules_unavailable"
    assert stub.calls == []


def test_the_verdict_must_be_about_the_captured_line(stub):
    stub.behaviour["line"] = "Some other line the validator liked."
    t, b = researched()
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_line_mismatch"


def test_the_gate_calls_validate_itself_and_ignores_a_stored_verdict(stub):
    t, b = researched()
    t.meta["research_verdict"] = ResearchVerdict(True, LINE, (), gate.research_rules_sha(stub))
    t.meta["research_ok"] = True
    stub.behaviour["ok"] = False
    stub.behaviour["reasons"] = ("stale",)
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_rules_failed"
    assert len(stub.calls) == 1
    stub.behaviour["ok"] = True
    assert verdict(t, b).allowed
    assert len(stub.calls) == 2                 # every verdict asks again


def test_the_validator_cannot_change_the_touch_evidence(stub):
    def mutate(line, evidence, context):
        evidence["facts"] = []
        context["company"] = "Other"
        return ResearchVerdict(True, line, (), ta.research_rules_sha(stub.RULES_TEXT, stub.RULES_VERSION))
    stub.validate = mutate
    t, b = researched()
    assert verdict(t, b).allowed
    assert t.meta["research_evidence"] == EVIDENCE and b["company"] == COMPANY


# ----------------------------------------------- what the touch must carry
def test_the_captured_line_must_be_meta_research_line(stub):
    t, b = researched()
    t.meta["research_line"] = "Your site says your crews clean dental offices across Dallas at night."
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_line_mismatch"
    assert stub.calls == []


def test_meta_line_is_compared_after_normalisation(stub):
    t, b = researched()
    t.meta["research_line"] = "  " + LINE + "  \n"
    assert verdict(t, b).allowed


@pytest.mark.parametrize("meta", ["no_line", "empty_line", "blank_line", "not_text", "no_meta"])
def test_a_missing_research_line_is_refused(stub, meta):
    t, b = researched()
    if meta == "no_line":
        del t.meta["research_line"]
    elif meta == "empty_line":
        t.meta["research_line"] = ""
    elif meta == "blank_line":
        t.meta["research_line"] = "  \n "
    elif meta == "not_text":
        t.meta["research_line"] = ["a", "list"]
    else:
        t.meta = None
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_line_missing"
    assert stub.calls == []


@pytest.mark.parametrize("evidence", ["missing", None, [], "text"])
def test_missing_evidence_is_refused(stub, evidence):
    t, b = researched()
    if evidence == "missing":
        del t.meta["research_evidence"]
    else:
        t.meta["research_evidence"] = evidence
    v = verdict(t, b)
    assert not v.allowed and v.reason == "research_evidence_missing"
    assert stub.calls == []


@pytest.mark.parametrize("key", list(gate.RESEARCH_CONTEXT_KEYS))
@pytest.mark.parametrize("how", ["missing", "empty", "blank"])
def test_any_missing_context_key_is_refused(stub, key, how):
    t, b = researched()
    if how == "missing":
        b.pop(key, None)
    else:
        b[key] = "" if how == "empty" else "   "
    v = verdict(t, b)
    assert not v.allowed
    # the company is also a placeholder: without its binding the body may still
    # conform, but the research context refuses
    assert v.reason == "research_context_missing", v
    assert key in v.detail
    assert stub.calls == []


def test_no_bindings_at_all_is_refused(stub):
    t, _ = researched()
    assert verdict(t, None).reason == "research_context_missing"


def test_an_unknown_offer_branch_is_refused(stub):
    t, b = researched()
    b["offer_branch"] = "trigger"
    assert verdict(t, b).reason == "research_context_missing"


def test_the_company_in_the_body_must_still_be_the_bound_one(stub):
    t, b = researched()
    t.body_text = t.body_text.replace("run for %s." % COMPANY, "run for Other Co.")
    v = verdict(t, b)
    assert not v.allowed and v.reason == "nonconforming"


# --------------------------------------------------- the capture's shape
@pytest.mark.parametrize("bad", [
    "Your site says your crews clean offices.\n\nAnd they do it at night.",   # a blank line inside
    "Your site says your crews clean offices\nacross Tulsa at night.",        # any line break
    "Saw the {Promo page} on your site about night crews.",                   # braces
    "Saw the } on your site.",
    " Your site says your crews clean offices across Tulsa at night.",        # leading space
])
def test_a_line_of_the_wrong_shape_does_not_conform(stub, bad):
    t, b = researched()
    with_body_line(t, bad)
    v = verdict(t, b)
    assert not v.allowed and v.reason in ("nonconforming", "research_line_mismatch"), v
    assert stub.calls == []


def test_a_line_over_300_characters_does_not_conform(stub):
    line = (UNIT * 20)[:300] + "."
    assert len(line) == 301 and line == line.strip()
    t, b = researched()
    with_body_line(t, line)
    v = verdict(t, b)
    assert not v.allowed and v.reason == "nonconforming"
    assert stub.calls == []


def test_a_line_with_a_zero_width_character_does_not_conform(stub):
    t, b = researched()
    with_body_line(t, LINE.replace("crews", "cr​ews"))
    v = verdict(t, b)
    assert not v.allowed and v.reason == "nonconforming"


# ------------------------------------------------------- the copy gate
@pytest.mark.parametrize("bad", [
    "Your site says your crews clean dental offices — across Tulsa at night.",
    "Your site says your crews clean dental offices across Tulsa at night!",
    "Your site says your crews use AI to clean dental offices across Tulsa.",
    "Your site says your crews cut costs by 40% for dental offices across Tulsa.",
])
def test_the_copy_gate_applies_to_the_research_line_even_when_the_rules_pass(stub, bad):
    t, b = researched()
    with_body_line(t, bad)
    v = verdict(t, b)
    assert not v.allowed and v.reason == "copy_gate", v
    assert stub.calls == []


def test_the_copy_gate_is_run_on_the_body_not_taken_from_touch_problems(stub):
    t, b = researched()
    with_body_line(t, LINE[:-1] + "!")
    fake = types.SimpleNamespace(template_id=t.template_id, template_hash=t.template_hash,
                                 template_parts=dict(t.template_parts), body_text=t.body_text, subject=t.subject,
                                 meta=dict(t.meta), allow_terms=list(t.allow_terms), campaign_key=t.campaign_key,
                                 problems=[])
    v = verdict(fake, b)
    assert not v.allowed and v.reason == "copy_gate"
    assert stub.calls == []


# ------------------------------------------------- the usual gate steps
def test_the_kill_switch_and_approvals_still_come_first(stub):
    t, b = researched()
    stub.env.kill_switch(True)
    assert verdict(t, b).reason == "kill_switch"
    stub.env.kill_switch(False)
    stub.env.revoke_ids(RULES_ID)
    assert verdict(t, b).reason == "unapproved"
    stub.env.approve_ids(RULES_ID)
    stub.env.revoke_ids("cadence.d2")
    assert verdict(t, b).reason == "unapproved"
    assert stub.calls == []


def test_an_unstamped_rules_part_is_stale(stub):
    t, b = researched()
    t.template_parts = {RULES_ID: None}
    assert verdict(t, b).reason == "stale_render"


def test_every_new_reason_is_listed():
    for reason in ("research_line_missing", "research_evidence_missing", "research_context_missing",
                   "research_line_mismatch", "research_rules_unavailable", "research_rules_error",
                   "research_rules_failed", "research_rules_sha_mismatch"):
        assert reason in gate.REASONS


# ----------------------------------------------------------- no leaks
def test_zz_no_stub_leaks_into_the_catalogue():
    """Runs last in this file: the stub is gone and the real catalogue is
    today's, 108 approvable ids, the rules entry not approvable."""
    assert MODULE not in sys.modules or not hasattr(sys.modules[MODULE], "calls")
    _clear()
    idx = ta.catalogue_index()
    assert sum(1 for e in idx.values() if e["approvable"]) == APPROVABLE_TODAY
    assert not idx[RULES_ID]["approvable"]
    assert idx[RULES_ID]["explanation"] == ta.RESEARCH_RULES_ABSENT
    _clear()
