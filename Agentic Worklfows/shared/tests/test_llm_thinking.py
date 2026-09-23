"""THINKING_POLICY in shared/llm.py.

The bug this pins (shadow test, 2026-09-23): claude-sonnet-5 thinks
adaptively when a request carries no ``thinking`` parameter. On a real Upwork
drafting prompt it spent ~480 output tokens thinking, the max_tokens=400 cap
stopped the call, and complete() raised "cut off at max_tokens". Every real
call now sends ``thinking`` explicitly, disabled unless a role opts in.
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


def test_policy_covers_every_role_and_defaults_to_disabled():
    assert set(llm.THINKING_POLICY) == set(llm.MODEL_POLICY)
    for role, cfg in llm.THINKING_POLICY.items():
        assert cfg == {"type": "disabled"}, role


@pytest.mark.parametrize("role", sorted(llm.MODEL_POLICY))
def test_create_call_carries_thinking_disabled_for_every_role(_billed, role):
    assert llm.complete(role, "s", "u", max_tokens=400) == "ok"
    (kwargs,) = _billed.messages.calls
    assert kwargs["thinking"] == {"type": "disabled"}
    assert kwargs["model"] == llm.MODEL_POLICY[role]
    assert kwargs["max_tokens"] == 400


def test_unknown_role_also_gets_thinking_disabled(_billed):
    llm.complete("no_such_role", "s", "u", max_tokens=100)
    assert _billed.messages.calls[0]["thinking"] == {"type": "disabled"}


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


def test_a_valid_enabled_config_is_passed_through(_billed, monkeypatch):
    monkeypatch.setitem(llm.THINKING_POLICY, "retro", {"type": "enabled", "budget_tokens": 2000})
    llm.complete("retro", "s", "u", max_tokens=4000)
    assert _billed.messages.calls[0]["thinking"] == {"type": "enabled", "budget_tokens": 2000}


@pytest.mark.parametrize("cfg,max_tokens", [
    ({"type": "enabled", "budget_tokens": 2000}, 2000),      # budget must be below max_tokens
    ({"type": "enabled", "budget_tokens": 2000}, 400),
    ({"type": "enabled", "budget_tokens": 500}, 4000),       # under the API minimum
    ({"type": "enabled"}, 4000),                             # no budget
    ({"type": "enabled", "budget_tokens": "2000"}, 4000),    # not an int
    ({"type": "enabled", "budget_tokens": True}, 4000),
    ({"type": "adaptive"}, 4000),
    ({"type": "disabled", "budget_tokens": 2000}, 4000),     # extra key
    ({}, 4000),
    ("disabled", 4000),
    (None, 4000),
])
def test_an_invalid_thinking_config_is_refused_before_anything_bills(_billed, monkeypatch, cfg, max_tokens):
    monkeypatch.setitem(llm.THINKING_POLICY, "draft", cfg)
    with pytest.raises(llm.LLMError) as exc:
        llm.complete("draft", "s", "u", max_tokens=max_tokens)
    assert "THINKING_POLICY" in str(exc.value)
    assert _billed.messages.calls == []
    assert llm.spend_usd() == 0.0
