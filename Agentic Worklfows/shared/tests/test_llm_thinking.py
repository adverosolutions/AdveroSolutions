"""Thinking control in shared/llm.py (EFFORT_POLICY, THINKING_HEADROOM_TOKENS).

Every role runs on claude-opus-5-5 since 2026-09-25. On that model thinking
cannot be disabled: ``thinking={"type": "disabled"}`` and the ``budget_tokens``
form are both a 400 (claude-api skill, "Migrating to Claude Opus 5.5"). So no
real call sends ``thinking``; each sends ``output_config={"effort": "low"}``
(the model's default is ``medium``) and asks for ``max_tokens`` plus a fixed
thinking headroom, because thinking counts toward ``max_tokens`` and the
2026-09-23 bug (a 400-token draft cut off by ~480 thinking tokens) would
otherwise come back.
"""
import pytest

from shared import llm, notify


class _Usage(object):
    input_tokens = 100
    output_tokens = 20


class _Text(object):
    type = "text"
    text = "ok"


class _Resp(object):
    content = [_Text()]
    usage = _Usage()
    stop_reason = "end_turn"


class _FakeMessages(object):
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Resp()


class _FakeClient(object):
    def __init__(self):
        self.messages = _FakeMessages()


@pytest.fixture(autouse=True)
def _billed(tmp_env, monkeypatch):
    """Billed mode behind a fake transport, spend counters zeroed per test."""
    monkeypatch.setattr(llm, "BUDGET_PATH", tmp_env / "llm_budget.json")
    llm._SPEND.update({"process": 0.0, "alerted": False, "warned": False})
    notify.reset_for_tests()
    monkeypatch.setenv("LLM_FAKE", "0")
    client = _FakeClient()
    monkeypatch.setitem(llm._CLIENT, "client", client)
    monkeypatch.setitem(llm._CLIENT, "warned", True)
    yield client
    llm._SPEND.update({"process": 0.0, "alerted": False, "warned": False})
    llm._CLIENT["client"] = None


def test_policy_covers_every_role_and_defaults_to_low():
    assert set(llm.EFFORT_POLICY) == set(llm.MODEL_POLICY)
    for role, effort in llm.EFFORT_POLICY.items():
        assert effort == "low", role


@pytest.mark.parametrize("role", sorted(llm.MODEL_POLICY))
def test_create_call_sends_low_effort_no_thinking_and_headroom_for_every_role(_billed, role):
    assert llm.complete(role, "s", "u", max_tokens=400) == "ok"
    (kwargs,) = _billed.messages.calls
    assert "thinking" not in kwargs, "claude-opus-5-5 answers 400 to any thinking shape but adaptive"
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["model"] == llm.MODEL_POLICY[role] == "claude-opus-5-5"
    assert kwargs["max_tokens"] == 400 + llm.THINKING_HEADROOM_TOKENS


def test_unknown_role_also_gets_low_effort(_billed):
    llm.complete("no_such_role", "s", "u", max_tokens=100)
    assert _billed.messages.calls[0]["output_config"] == {"effort": "low"}
    assert "thinking" not in _billed.messages.calls[0]


def test_the_budget_reserves_against_the_padded_max_tokens(_billed, monkeypatch):
    seen = []
    real = llm.enforce_budget

    def spy(role, model, system, user, max_tokens):
        seen.append(max_tokens)
        return real(role, model, system, user, max_tokens)

    monkeypatch.setattr(llm, "enforce_budget", spy)
    llm.complete("classify", "s", "u", max_tokens=120)
    assert seen == [120 + llm.THINKING_HEADROOM_TOKENS]


def test_cut_off_error_names_the_reply_cap_and_the_headroom(_billed, monkeypatch):
    class Resp(_Resp):
        stop_reason = "max_tokens"

    monkeypatch.setattr(_billed.messages, "create", lambda **kw: Resp())
    with pytest.raises(llm.LLMError) as exc:
        llm.complete("draft", "s", "u", max_tokens=400)
    assert "reply cap 400" in str(exc.value)


class _ThinkingWithText(object):
    """A thinking block that also carries ``text``.

    Real SDK thinking blocks have no ``text`` attribute, so with them alone the
    type filter in complete() is invisible: getattr(block, "text", "") already
    yields "". This fake gives the thinking block text so that dropping the
    filter leaks it into the result and these tests fail.
    """
    type = "thinking"
    thinking = "private reasoning"
    text = "SECRET THINKING"


class _RedactedWithText(object):
    type = "redacted_thinking"
    data = "opaque"
    text = "SECRET REDACTED"


def _respond_with(_billed, monkeypatch, blocks):
    class Resp(_Resp):
        content = blocks

    monkeypatch.setattr(_billed.messages, "create", lambda **kw: Resp())


def test_thinking_block_before_text_is_dropped_from_the_returned_text(_billed, monkeypatch):
    """If a role ever enables thinking, only text blocks become the draft."""
    _respond_with(_billed, monkeypatch, [_ThinkingWithText(), _RedactedWithText(), _Text()])
    out = llm.complete("draft", "s", "u", max_tokens=400)
    assert out == "ok"
    assert "SECRET" not in out


def test_json_mode_parses_only_the_text_block_after_a_thinking_block(_billed, monkeypatch):
    class Thinking(_ThinkingWithText):
        text = '{"label": "from_thinking", "confidence": 0.1}'

    class JsonText(object):
        type = "text"
        text = '{"label": "positive_interested", "confidence": 0.95}'

    _respond_with(_billed, monkeypatch, [Thinking(), JsonText()])
    assert llm.complete("classify", "s", "u", max_tokens=400, json_mode=True) == {
        "label": "positive_interested", "confidence": 0.95,
    }


def test_real_sdk_thinking_blocks_are_dropped(_billed, monkeypatch):
    """Same shapes the installed anthropic SDK returns when thinking is on."""
    types = pytest.importorskip("anthropic.types")
    blocks = [
        types.ThinkingBlock(type="thinking", thinking="private reasoning", signature="sig"),
        types.RedactedThinkingBlock(type="redacted_thinking", data="opaque"),
        types.TextBlock(type="text", text='{"label": "positive_interested"}'),
    ]
    _respond_with(_billed, monkeypatch, blocks)
    assert llm.complete("draft", "s", "u", max_tokens=400) == '{"label": "positive_interested"}'
    assert llm.complete("classify", "s", "u", max_tokens=400, json_mode=True) == {
        "label": "positive_interested",
    }


@pytest.mark.parametrize("effort", ["medium", "high", "xhigh", "max"])
def test_a_valid_higher_effort_is_passed_through(_billed, monkeypatch, effort):
    monkeypatch.setitem(llm.EFFORT_POLICY, "retro", effort)
    llm.complete("retro", "s", "u", max_tokens=4000)
    assert _billed.messages.calls[0]["output_config"] == {"effort": effort}


@pytest.mark.parametrize("cfg", [
    {"type": "disabled"},                        # the old shape: a 400 on Opus 5.5
    {"type": "enabled", "budget_tokens": 2000},  # also a 400 on Opus 5.5
    "LOW",
    "none",
    "",
    None,
    3,
])
def test_an_invalid_effort_is_refused_before_anything_bills(_billed, monkeypatch, cfg):
    monkeypatch.setitem(llm.EFFORT_POLICY, "draft", cfg)
    with pytest.raises(llm.LLMError) as exc:
        llm.complete("draft", "s", "u", max_tokens=400)
    assert "EFFORT_POLICY" in str(exc.value)
    assert _billed.messages.calls == []
    assert llm.spend_usd() == 0.0
