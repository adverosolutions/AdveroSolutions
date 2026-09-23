import csv
import json
import re
from pathlib import Path

import pytest

from shared import llm


@pytest.fixture(autouse=True)
def _fake(tmp_env, monkeypatch):
    monkeypatch.setenv("LLM_FAKE", "1")
    llm.clear_fakes()
    yield
    llm.clear_fakes()


def test_model_policy_exact():
    assert llm.MODEL_POLICY == {
        "classify": "claude-haiku-4-5-20251001",
        "draft": "claude-sonnet-5",
        "research": "claude-sonnet-5",
        "retro": "claude-opus-5",
        "proposal": "claude-opus-5",
        "escalate": "claude-sonnet-5",
    }
    assert llm.model_for("classify") == "claude-haiku-4-5-20251001"
    assert llm.model_for("unknown-role") == "claude-sonnet-5"


def test_fake_classify_returns_dict():
    out = llm.complete("classify", "You label replies.", "What is your percentage?", json_mode=True)
    assert out == {"label": "positive_interested", "confidence": 0.95, "reason": "fake"}


def test_fake_draft_is_deterministic_and_signed():
    a = llm.complete("draft", "You write replies.", "Lead asked: what is the upfront cost?")
    b = llm.complete("draft", "You write replies.", "Lead asked: what is the upfront cost?")
    assert a == b
    assert isinstance(a, str)
    assert a.rstrip().endswith("Lorenzo")
    assert "what is the upfront cost" in a
    assert "—" not in a  # no em dashes in customer-facing copy


def test_fake_draft_obeys_the_customer_copy_rules():
    """shared/llm.py's _fake_draft is the body every shadow dry run and every
    approval card renders, so it has to obey the same rules as a real draft:
    offers.md rule 8/9 plus 'pricing and proof only from offers.md'."""
    body = llm.complete("draft", "You write replies.", "Lead asked: what is the upfront cost?")
    assert "—" not in body and "–" not in body, "no em/en dashes in customer-facing copy"
    assert "!" not in body, "no exclamation marks"
    assert not re.search(r"\bA\.?I\.?\b", body), "never mention AI"
    assert not re.search(r"automat", body, re.I), "never mention automation"
    assert not re.search(r"\b(bot|robot|GPT|LLM|Claude)\b", body, re.I)
    assert "$" not in body, "no dollar figure that is not checked against offers.md"
    assert body.rstrip().endswith("Lorenzo")


def test_is_fake_accepts_every_spelling_of_true(monkeypatch):
    """LLM_FAKE=true is the spelling most people reach for; treating only "1"
    as fake silently billed every call in a review run."""
    for value in ("1", "true", "TRUE", "True", "yes", "on", " y "):
        monkeypatch.setenv("LLM_FAKE", value)
        assert llm.is_fake() is True, value
    for value in ("0", "", "false", "no", "off"):
        monkeypatch.setenv("LLM_FAKE", value)
        assert llm.is_fake() is False, value
    monkeypatch.delenv("LLM_FAKE", raising=False)
    assert llm.is_fake() is False


def test_truncated_output_raises_instead_of_being_returned(monkeypatch):
    """stop_reason=max_tokens means the draft is cut mid-sentence; the cadence
    auto-sends after a 30-minute veto window, so it must never be returned."""
    monkeypatch.setenv("LLM_FAKE", "0")

    class Block(object):
        type = "text"
        text = "Hey there,\n\nThanks for getting back to me. Quick answer to your"

    class Resp(object):
        content = [Block()]
        usage = None
        stop_reason = "max_tokens"

    class FakeMessages(object):
        def create(self, **kw):
            return Resp()

    class FakeClient(object):
        messages = FakeMessages()

    monkeypatch.setitem(llm._CLIENT, "client", FakeClient())
    with pytest.raises(llm.LLMError) as exc:
        llm.complete("draft", "s", "u", max_tokens=32)
    assert "max_tokens" in str(exc.value)
    monkeypatch.setitem(llm._CLIENT, "client", None)


def test_fake_generic_roles():
    assert llm.complete("research", "s", "acme.com").startswith("FAKE[research]")
    out = llm.complete("retro", "s", "week 38", json_mode=True)
    assert out["role"] == "retro" and out["fake"] is True


def test_register_fake_overrides_default():
    llm.register_fake("classify", lambda system, user, json_mode: {"label": "negative_hostile", "confidence": 0.99, "reason": "x"})
    assert llm.complete("classify", "s", "For the love of god leave me alone", json_mode=True)["label"] == "negative_hostile"
    llm.register_fake("draft", lambda system, user, json_mode: '{"body": "hi"}')
    assert llm.complete("draft", "s", "u", json_mode=True) == {"body": "hi"}  # str fakes are parsed in json_mode


def test_json_mode_parsing_helpers():
    assert llm._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm._parse_json('Sure: {"a": 2} done') == {"a": 2}
    with pytest.raises(llm.LLMError):
        llm._parse_json("not json at all")


def test_ledger_rows_and_cost(tmp_env):
    llm.complete("classify", "s" * 400, "u" * 400, json_mode=True)
    llm.complete("draft", "system prompt", "user prompt")
    path = llm.ledger_path()
    assert path == tmp_env / "llm_ledger.csv"
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["role"] for r in rows] == ["classify", "draft"]
    assert rows[0]["model"] == "claude-haiku-4-5-20251001"
    assert rows[1]["model"] == "claude-sonnet-5"
    assert int(rows[0]["input_tokens"]) >= 200
    assert float(rows[0]["est_cost_usd"]) > 0
    assert set(rows[0].keys()) == {"ts", "role", "model", "input_tokens", "output_tokens",
                                   "est_cost_usd", "faked"}
    # Both rows came from LLM_FAKE, so they cost nothing; the est_cost_usd
    # column still carries the projection a rehearsal exists to produce, and
    # the flag is what a cost audit filters on.
    assert [r["faked"] for r in rows] == ["1", "1"]


def test_estimate_cost_uses_price_table():
    assert llm.estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0
    assert llm.estimate_cost("claude-sonnet-5", 1_000_000, 1_000_000) == 12.0
    assert llm.estimate_cost("claude-opus-5", 0, 100_000) == 2.5  # $25/MTok out (list price 2026-06)
    assert llm.estimate_cost("mystery-model", 1_000_000, 0) == llm.DEFAULT_PRICE[0]


def test_fake_mode_never_touches_anthropic_client(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "anthropic", None)  # import would raise if attempted
    assert llm.complete("draft", "s", "u")


def test_model_policy_carries_no_fable_id_and_is_deliberate():
    """Lorenzo's Fable weekly allowance ran out on 2026-09-21, so every role
    that used to be Fable is Opus 5. classify/draft/research stay on the cheap
    models ON PURPOSE (CLAUDE.md "Runtime models"): classification runs on every
    reply and the drafts are template-shaped, so moving them to Opus 5 is a
    standing cost decision for Lorenzo, not a silent change."""
    policy = llm.MODEL_POLICY
    assert "fable" not in json.dumps(policy).lower()
    assert policy["retro"] == "claude-opus-5" and policy["proposal"] == "claude-opus-5"
    assert policy["classify"].startswith("claude-haiku")
    for role in ("draft", "research", "escalate"):
        assert policy[role].startswith("claude-sonnet"), role
    # every id in the policy has a price, or the ledger silently bills the
    # conservative fallback and every cost report is wrong
    for role, model in policy.items():
        assert model in llm.PRICES_USD_PER_MTOK, "%s -> %s has no price" % (role, model)


def test_every_priced_model_has_a_policy_role_and_the_reverse():
    """The price table and MODEL_POLICY have to name the same set of models.

    `claude-fable-5` was priced here until 2026-09-22 with no role pointing at
    it, eleven months after Fable was retired: a row that reads like a model
    the system still calls, in the one table a cost review trusts. The only
    exception is an undated alias of a model that IS in the policy, which has
    to carry its target's price rather than a second, drifting one."""
    policy = set(llm.MODEL_POLICY.values())
    priced = set(llm.PRICES_USD_PER_MTOK)
    aliases = dict(llm.MODEL_ALIASES)

    unpriced = sorted(policy - priced)
    assert not unpriced, (
        "these models are in MODEL_POLICY with no price, so every ledger row for them bills the "
        "DEFAULT_PRICE fallback and every cost report is wrong: %s" % unpriced)

    orphans = sorted(priced - policy - set(aliases))
    assert not orphans, (
        "these models are priced but no role in MODEL_POLICY and no entry in MODEL_ALIASES names "
        "them, so they read like models the system still calls: %s" % orphans)

    for alias, target in aliases.items():
        assert target in policy, "MODEL_ALIASES[%r] points at %r, which is in no role" % (alias, target)
        assert llm.PRICES_USD_PER_MTOK[alias] == llm.PRICES_USD_PER_MTOK[target], (
            "%s and %s are the same model at two different prices" % (alias, target))

    retired = sorted(m for m in priced | policy if "fable" in m.lower())
    assert not retired, "retired Fable ids are back in the tables: %s" % retired


def test_prices_have_no_duplicated_key():
    """A duplicated dict literal key silently wins, and every Opus cost already
    reported from .tmp/llm_ledger.csv was 2x the list price."""
    source = Path(llm.__file__).read_text(encoding="utf-8")
    block = source.split("PRICES_USD_PER_MTOK = {", 1)[1].split("}", 1)[0]
    keys = re.findall(r'"([^"]+)"\s*:', block)
    assert len(keys) == len(set(keys)), "duplicated price key: %s" % keys


# ------------------------------------------------- ledger header migration
def test_a_narrow_ledger_heals_itself_instead_of_inventing_spend(tmp_path, monkeypatch):
    """`faked` was appended to LEDGER_HEADER, but _record only wrote a header
    for a brand-new file, so the ledger on disk kept its 6-column header over
    1,020 six-field rows. csv.DictReader returns no `faked` key for those, and
    ledger_spend_usd treats a missing flag as billed - it reported $1.47957 of
    spend that never happened, and the documented "filter on the flag" audit
    could not be run on the file that existed."""
    import csv as _csv

    path = tmp_path / "llm_ledger.csv"
    with open(str(path), "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["ts", "role", "model", "input_tokens", "output_tokens", "est_cost_usd"])
        for _ in range(3):
            w.writerow(["2026-09-22T02:00:00+00:00", "draft", "claude-sonnet-5", 100, 50, "0.500000"])

    # the bug: every faked row counted as real money
    assert llm.ledger_spend_usd(path) == 1.5

    assert llm.migrate_ledger_header(path) is True
    assert llm.ledger_spend_usd(path) == 0.0

    rows = list(_csv.reader(open(str(path))))
    assert rows[0] == llm.LEDGER_HEADER
    assert all(len(r) == len(llm.LEDGER_HEADER) for r in rows)
    assert all(r[-1] == "1" for r in rows[1:]), "pre-flag rows backfill to faked=1"

    # idempotent, and a correct ledger is left alone
    assert llm.migrate_ledger_header(path) is False

    # and _record heals a narrow file on the next append
    with open(str(path), "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["ts", "role", "model", "input_tokens", "output_tokens", "est_cost_usd"])
        w.writerow(["2026-09-22T02:00:00+00:00", "draft", "claude-sonnet-5", 100, 50, "0.500000"])
    monkeypatch.setenv("LLM_LEDGER_PATH", str(path))
    monkeypatch.setenv("LLM_FAKE", "1")
    llm._record("draft", "claude-sonnet-5", 10, 5)
    after = list(_csv.DictReader(open(str(path))))
    assert [r["faked"] for r in after] == ["1", "1"]
    assert llm.ledger_spend_usd(path) == 0.0
