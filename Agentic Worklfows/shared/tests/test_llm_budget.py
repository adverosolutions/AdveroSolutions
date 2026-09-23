"""The cumulative USD ceiling on billed model calls (shared/llm.py).

The case this exists for: runbooks/GO_LIVE_CHECKLIST.md Stage 3 deploys to
Modal and watches for 48 hours (3.1 checks the spend) with LLM_FAKE unset, so every tick bills. Shadow mode
bounds what a WRITE can do; until this ceiling existed nothing bounded what a
loop could do to the bill.
"""
import json

import pytest

from shared import llm, notify


class _Usage(object):
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Block(object):
    type = "text"
    text = "ok"


class _Resp(object):
    def __init__(self, usage):
        self.content = [_Block()]
        self.usage = usage
        self.stop_reason = "end_turn"


class _FakeMessages(object):
    def __init__(self, input_tokens, output_tokens):
        self.calls = []
        self._usage = (input_tokens, output_tokens)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Resp(_Usage(*self._usage))


class _FakeClient(object):
    """A stand-in for anthropic.Anthropic that bills a known amount per call."""

    def __init__(self, input_tokens=1_000_000, output_tokens=0):
        self.messages = _FakeMessages(input_tokens, output_tokens)

    @property
    def calls(self):
        return self.messages.calls


@pytest.fixture(autouse=True)
def _budget_env(tmp_env, monkeypatch):
    """Per-test store, per-test ledger, per-test budget file, counters zeroed.

    tmp_env repoints STORE_PATH, so the durable spend counter starts empty for
    each test and never leaks into another one.
    """
    monkeypatch.setattr(llm, "BUDGET_PATH", tmp_env / "llm_budget.json")
    llm._SPEND.update({"process": 0.0, "alerted": False, "warned": False})
    notify.reset_for_tests()
    yield
    llm._SPEND.update({"process": 0.0, "alerted": False, "warned": False})
    llm._CLIENT["client"] = None


def _billed(monkeypatch, client):
    """Put the process in billed mode behind a fake transport."""
    monkeypatch.setenv("LLM_FAKE", "0")
    monkeypatch.setitem(llm._CLIENT, "client", client)


def _write_budget(path, **values):
    path.write_text(json.dumps(values), encoding="utf-8")


# --------------------------------------------------------------- the config
def test_the_default_applies_when_there_is_no_config_file():
    assert not llm.BUDGET_PATH.exists()
    assert llm.budget_usd() == llm.DEFAULT_BUDGET_USD
    assert llm.budget_config()["warn_at_fraction"] == llm.DEFAULT_WARN_FRACTION


def test_the_config_file_sets_the_cap(tmp_env):
    _write_budget(llm.BUDGET_PATH, budget_usd=3.5, warn_at_fraction=0.5)
    assert llm.budget_usd() == 3.5
    assert llm.budget_config()["warn_at_fraction"] == 0.5


def test_a_malformed_config_falls_back_to_the_default_instead_of_raising(tmp_env):
    llm.BUDGET_PATH.write_text("{not json at all", encoding="utf-8")
    assert llm.budget_usd() == llm.DEFAULT_BUDGET_USD
    llm.BUDGET_PATH.write_text('["a list"]', encoding="utf-8")
    assert llm.budget_usd() == llm.DEFAULT_BUDGET_USD
    _write_budget(llm.BUDGET_PATH, budget_usd="lots")
    assert llm.budget_usd() == llm.DEFAULT_BUDGET_USD


def test_zero_or_negative_is_not_read_as_unlimited(tmp_env):
    """A ceiling that a typo can remove is not a ceiling. 0 and -1 fall back to
    the conservative default rather than disabling the check (or, worse,
    refusing every call and making the system look broken for a config typo)."""
    for value in (0, 0.0, -1, -0.01):
        _write_budget(llm.BUDGET_PATH, budget_usd=value)
        assert llm.budget_usd() == llm.DEFAULT_BUDGET_USD, value


def test_an_out_of_range_warn_fraction_falls_back(tmp_env):
    for value in (0, 1.5, -0.2, "soon"):
        _write_budget(llm.BUDGET_PATH, budget_usd=5.0, warn_at_fraction=value)
        assert llm.budget_config()["warn_at_fraction"] == llm.DEFAULT_WARN_FRACTION, value


# ------------------------------------------------------------- what it does
def test_billed_calls_accumulate_and_then_the_cap_refuses(tmp_env, monkeypatch):
    """Two $1.00 calls fit under a $1.50 cap only because the ledger is
    cumulative; the third is refused before the client is touched."""
    _write_budget(llm.BUDGET_PATH, budget_usd=1.5)
    client = _FakeClient(input_tokens=1_000_000, output_tokens=0)  # $1.00 on haiku-4-5
    _billed(monkeypatch, client)

    llm.complete("classify", "s", "u")
    assert llm.spend_usd() == pytest.approx(1.0)
    llm.complete("classify", "s", "u")
    assert llm.spend_usd() == pytest.approx(2.0)

    with pytest.raises(llm.LLMBudgetExceeded) as exc:
        llm.complete("classify", "s", "u")
    assert len(client.calls) == 2, "the refused call must not reach the model"
    assert "2.0" in str(exc.value) and "1.50" in str(exc.value)
    assert str(llm.BUDGET_PATH) in str(exc.value), "the message has to say where to raise the cap"


def test_one_oversized_call_cannot_jump_the_cap(tmp_env, monkeypatch):
    """The check runs before the call, so it prices the call at max_tokens.
    Without that, a single 2,000-token Opus call walks straight past a cap it
    could not have afforded."""
    _write_budget(llm.BUDGET_PATH, budget_usd=0.01)
    client = _FakeClient(input_tokens=10, output_tokens=10)
    _billed(monkeypatch, client)

    with pytest.raises(llm.LLMBudgetExceeded):
        llm.complete("proposal", "s", "u", max_tokens=2000)   # 2000 x $25/MTok = $0.05
    assert client.calls == []
    assert llm.spend_usd() == 0.0


def test_the_refusal_is_an_llm_error_so_a_tick_degrades_instead_of_crashing():
    """classify falls back to unsure and draft refuses on LLMError. The cap
    reusing that path is deliberate: a scheduled tick must not die on it, and
    the push plus the Job_Log row are what make it loud."""
    assert issubclass(llm.LLMBudgetExceeded, llm.LLMError)


def test_fake_calls_never_consume_or_trip_the_budget(tmp_env, monkeypatch):
    """LLM_FAKE costs nothing, so it is neither counted nor refused. This is
    what keeps the suite (and every --dry-run) free of the ceiling."""
    _write_budget(llm.BUDGET_PATH, budget_usd=0.000001)
    monkeypatch.setenv("LLM_FAKE", "1")
    for _ in range(5):
        assert llm.complete("draft", "s", "u")
    assert llm.spend_usd() == 0.0
    assert llm.ledger_spend_usd() == 0.0, "faked ledger rows are a projection, not money"


def test_the_stop_pushes_once(tmp_env, monkeypatch):
    _write_budget(llm.BUDGET_PATH, budget_usd=0.01)
    _billed(monkeypatch, _FakeClient(input_tokens=1_000_000))
    llm.complete("classify", "s", "u")   # a cheap-looking call that bills $1.00
    for _ in range(3):
        with pytest.raises(llm.LLMBudgetExceeded):
            llm.complete("classify", "s", "u")
    stops = [n for n in notify.sent_in_test if "budget stop" in n["title"].lower()]
    assert len(stops) == 1, "one push per process, not one per refused call"
    assert "reset_spend" in stops[0]["message"]


def test_the_warning_fires_once_on_the_way_up(tmp_env, monkeypatch):
    _write_budget(llm.BUDGET_PATH, budget_usd=2.5, warn_at_fraction=0.8)
    client = _FakeClient(input_tokens=1_000_000)   # $1.00 a call
    _billed(monkeypatch, client)

    llm.complete("classify", "s", "u")             # $1.00, under 80% of $2.50
    assert [n for n in notify.sent_in_test if "spend at" in n["title"].lower()] == []
    llm.complete("classify", "s", "u")             # $2.00, over the $2.00 line
    llm.complete("classify", "s", "u")
    warnings = [n for n in notify.sent_in_test if "spend at" in n["title"].lower()]
    assert len(warnings) == 1


# ------------------------------------------------------ across the containers
def test_the_total_survives_a_fresh_process(tmp_env, monkeypatch):
    """On Modal every tick is a new container with a new .tmp, so a file-local
    total would reset every five minutes and bound nothing. The running total
    lives in the shared store, which is the modal.Dict there."""
    _write_budget(llm.BUDGET_PATH, budget_usd=5.0)
    _billed(monkeypatch, _FakeClient(input_tokens=1_000_000))
    llm.complete("classify", "s", "u")

    llm._SPEND["process"] = 0.0          # the next container knows nothing
    assert llm.spend_usd() == pytest.approx(1.0)


def test_a_store_outage_degrades_to_the_process_and_the_ledger(tmp_env, monkeypatch):
    _write_budget(llm.BUDGET_PATH, budget_usd=5.0)
    _billed(monkeypatch, _FakeClient(input_tokens=1_000_000))
    llm.complete("classify", "s", "u")

    def _broken():
        raise RuntimeError("modal.Dict unreachable")

    monkeypatch.setattr(llm, "_store", _broken)
    assert llm.spend_usd() == pytest.approx(1.0)   # from this process
    llm._SPEND["process"] = 0.0
    assert llm.spend_usd() == pytest.approx(1.0)   # then from the ledger CSV


def test_ledger_spend_counts_billed_rows_only(tmp_env, monkeypatch):
    monkeypatch.setenv("LLM_FAKE", "1")
    llm.complete("draft", "s" * 4000, "u" * 4000)
    assert llm.ledger_spend_usd() == 0.0
    _billed(monkeypatch, _FakeClient(input_tokens=1_000_000))
    llm.complete("classify", "s", "u")
    assert llm.ledger_spend_usd() == pytest.approx(1.0)


def test_reset_spend_zeroes_the_counter_and_rearms_the_alerts(tmp_env, monkeypatch):
    _write_budget(llm.BUDGET_PATH, budget_usd=0.01)
    _billed(monkeypatch, _FakeClient(input_tokens=1_000_000))
    llm.complete("classify", "s", "u")           # bills $1.00 against a $0.01 cap
    with pytest.raises(llm.LLMBudgetExceeded):
        llm.complete("classify", "s", "u")
    assert llm.spend_usd() == pytest.approx(1.0)
    assert llm._SPEND["alerted"]
    period = llm._store().get(llm.SPEND_PERIOD_KEY)
    assert llm.reset_spend() == 0.0
    assert llm.spend_usd() == 0.0
    assert llm._SPEND["alerted"] is False
    assert llm._store().get(llm.SPEND_PERIOD_KEY) not in (None, period), "a reset opens a new alert period"


# ------------------------- D1 round 3, defect 7: one alert per threshold per period
def _fresh_container():
    """What a new Modal container knows: nothing in-process."""
    llm._SPEND.update({"process": 0.0, "alerted": False, "warned": False})


def _capture(monkeypatch):
    pushes, rows = [], []
    monkeypatch.setattr(llm, "_notify_budget", lambda title, message: pushes.append((title, message)))
    monkeypatch.setattr(llm, "_log_budget", lambda status, details: rows.append(status))
    return pushes, rows


def test_the_warning_pushes_once_across_six_fresh_containers(tmp_env, monkeypatch):
    pushes, rows = _capture(monkeypatch)
    llm._store().set(llm.SPEND_KEY, 8.5)          # past warn_at (0.8 x $10), under the cap
    for _run in range(6):
        _fresh_container()
        llm.enforce_budget("classify", "claude-haiku-4-5", "s", "u", 50)
    assert len(pushes) == 1 and rows == ["warned"]


def test_the_stop_pushes_once_across_six_fresh_containers_and_a_reset_rearms_it(tmp_env, monkeypatch):
    pushes, rows = _capture(monkeypatch)
    llm._store().set(llm.SPEND_KEY, 9.999)
    for _run in range(6):
        _fresh_container()
        with pytest.raises(llm.LLMBudgetExceeded):
            llm.enforce_budget("draft", "claude-sonnet-4-5", "s" * 4000, "u" * 4000, 800)
    assert [p[0].split(":")[0] for p in pushes] == ["LLM budget stop"] and rows == ["refused"]
    # a reset in the deployed Dict (changesets/deploy/budget.py) opens a new period
    llm.start_period(llm._store())
    llm._store().set(llm.SPEND_KEY, 9.999)
    _fresh_container()
    with pytest.raises(llm.LLMBudgetExceeded):
        llm.enforce_budget("draft", "claude-sonnet-4-5", "s" * 4000, "u" * 4000, 800)
    assert len(pushes) == 2 and rows == ["refused", "refused"]


def test_on_modal_the_stop_names_the_deployed_reset_and_the_redeploy(tmp_env, monkeypatch):
    pushes, _rows = _capture(monkeypatch)
    local = llm._store()                      # RUNTIME=modal would select the Modal Dict
    monkeypatch.setattr(llm, "_store", lambda: local)
    monkeypatch.setenv("RUNTIME", "modal")
    local.set(llm.SPEND_KEY, 9.999)
    with pytest.raises(llm.LLMBudgetExceeded) as err:
        llm.enforce_budget("draft", "claude-sonnet-4-5", "s" * 4000, "u" * 4000, 800)
    text = pushes[0][1]
    for message in (text, str(err.value)):
        assert "changesets/deploy/budget.py reset --store-mode shadow" in message
        assert "redeploy" in message
        assert "reset_spend" not in message


def test_on_the_laptop_the_stop_still_names_reset_spend(tmp_env, monkeypatch):
    pushes, _rows = _capture(monkeypatch)
    monkeypatch.delenv("RUNTIME", raising=False)
    llm._store().set(llm.SPEND_KEY, 9.999)
    with pytest.raises(llm.LLMBudgetExceeded):
        llm.enforce_budget("draft", "claude-sonnet-4-5", "s" * 4000, "u" * 4000, 800)
    assert "llm.reset_spend()" in pushes[0][1]


def test_budget_status_is_readable_for_the_morning_check(tmp_env):
    _write_budget(llm.BUDGET_PATH, budget_usd=4.0)
    status = llm.budget_status()
    assert status["budget_usd"] == 4.0
    assert status["spent_usd"] == 0.0
    assert status["remaining_usd"] == 4.0
    assert status["over_budget"] is False
    assert status["config_path"].endswith("llm_budget.json")


# --------------------------------------------------- the number is defensible
def test_the_default_sits_between_a_healthy_watch_and_a_runaway():
    """The cap is sized from modal_app's real tick frequencies, so a change to
    those has to come back through this number.

    A healthy 48 hours is about $0.65 (the arithmetic is in shared/llm.py).
    precall_tick and poller both run on */5, which is 576 runs in 48 hours; one
    Opus proposal per run is $40 of drafts nobody asked for.
    """
    from services.reply_engine import modal_app

    minute_field = modal_app.SCHEDULES["precall_tick"][0].split()[0]
    assert minute_field.startswith("*/"), minute_field
    runs_in_48h = int(48 * 60 / int(minute_field[2:]))
    assert runs_in_48h == 576

    proposal_call = llm.estimate_cost("claude-opus-5", 6000, 1600)      # $0.07
    runaway_48h = runs_in_48h * proposal_call                            # about $40
    healthy_48h = 1.00                                                   # generous rounding of $0.65

    assert llm.DEFAULT_BUDGET_USD >= 5 * healthy_48h, (
        "the cap would trip during a healthy watch and the watch would prove nothing")
    assert llm.DEFAULT_BUDGET_USD < runaway_48h / 2, (
        "a runaway on the 5-minute schedule would finish its two days before the cap bit")
    assert 0 < llm.DEFAULT_WARN_FRACTION < 1


def test_the_shipped_config_is_readable_and_conservative():
    """The file Lorenzo actually deploys, not a test fixture."""
    from shared.paths import CONFIG_DIR

    path = CONFIG_DIR / "llm_budget.json"
    assert path.exists(), "config/llm_budget.json is what the container reads; it has to be committed"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert 0 < float(data["budget_usd"]) <= 50, "a rehearsal cap, raised deliberately and not by drift"
    assert 0 < float(data["warn_at_fraction"]) <= 1


# ------------------------------------------- reserve first, count every attempt
# SAF-8 (2026-09-22 review): spend was counted only after a call SUCCEEDED, the
# SDK's own retries were invisible to it, and concurrent calls all passed the
# same check (the reviewer took a $10.00 cap to $10.48).
import threading
import time


def _projected(role="classify", system="s", user="u", max_tokens=800):
    return llm.projected_cost_usd(llm.model_for(role), system, user, max_tokens)


class _ScriptedMessages(object):
    """create() plays a script: an exception instance is raised, a tuple is
    returned as (input_tokens, output_tokens) usage. Records the spend the
    ceiling showed at the moment each request left the process."""

    def __init__(self, script, delay=0.0):
        self.script = list(script)
        self.delay = delay
        self.calls = []
        self.spend_at_call = []
        self._lock = threading.Lock()

    def create(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
            self.spend_at_call.append(llm.spend_usd())
            step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if self.delay:
            time.sleep(self.delay)
        if isinstance(step, BaseException):
            raise step
        return _Resp(_Usage(*step))


class _ScriptedClient(object):
    def __init__(self, script, delay=0.0):
        self.messages = _ScriptedMessages(script, delay)


class RateLimitError(Exception):
    """Named like anthropic's, which is how llm._is_retryable recognises it."""


class _Status529(Exception):
    status_code = 529


def test_the_reservation_is_charged_before_the_request_leaves(tmp_env, monkeypatch):
    client = _ScriptedClient([(10, 10)])
    _billed(monkeypatch, client)
    llm.complete("classify", "s", "u")
    assert client.messages.spend_at_call == [pytest.approx(_projected())], (
        "the worst case must already be on the counter while the request is in flight")
    # ...and reconciled to the real cost once the response says what it was
    assert llm.spend_usd() == pytest.approx(llm.estimate_cost(llm.model_for("classify"), 10, 10))


def test_a_failed_call_still_counts(tmp_env, monkeypatch):
    client = _ScriptedClient([ValueError("bad request")])
    _billed(monkeypatch, client)
    with pytest.raises(ValueError):
        llm.complete("classify", "s", "u")
    assert len(client.messages.calls) == 1, "a non-transient error is not retried"
    assert llm.spend_usd() == pytest.approx(_projected()), "the reservation stays charged"


def test_racing_threads_cannot_exceed_the_cap(tmp_env, monkeypatch):
    """40 threads, a cap that fits about 9 worst-case calls, and a slow model so
    every thread is in flight at once. Each call bills exactly its worst case,
    so the old check-then-charge shape would have let all 40 through."""
    per_call = _projected(max_tokens=1000)
    cap = round(per_call * 9.5, 6)
    _write_budget(llm.BUDGET_PATH, budget_usd=cap)
    input_tokens = llm._approx_tokens("s") + llm._approx_tokens("u")
    client = _ScriptedClient([(input_tokens, 1000)], delay=0.02)
    _billed(monkeypatch, client)

    start = threading.Barrier(40)
    outcomes = []

    def worker():
        start.wait()
        try:
            llm.complete("classify", "s", "u", max_tokens=1000)
            outcomes.append("ok")
        except llm.LLMBudgetExceeded:
            outcomes.append("refused")

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert len(outcomes) == 40
    assert outcomes.count("ok") == 9 and outcomes.count("refused") == 31
    assert len(client.messages.calls) == 9
    assert llm.spend_usd() <= cap
    assert llm.spend_usd() == pytest.approx(9 * per_call)


def test_every_retry_is_counted(tmp_env, monkeypatch):
    """The SDK retried invisibly; now every attempt reserves its own worst case."""
    monkeypatch.setattr(llm, "_sleep", lambda seconds: None)
    client = _ScriptedClient([RateLimitError("429"), _Status529("overloaded"), (10, 10)])
    _billed(monkeypatch, client)
    llm.complete("classify", "s", "u")
    assert len(client.messages.calls) == 3
    actual = llm.estimate_cost(llm.model_for("classify"), 10, 10)
    assert llm.spend_usd() == pytest.approx(2 * _projected() + actual)


def test_retries_stop_at_max_attempts_and_all_count(tmp_env, monkeypatch):
    monkeypatch.setattr(llm, "_sleep", lambda seconds: None)
    client = _ScriptedClient([RateLimitError("429")])
    _billed(monkeypatch, client)
    with pytest.raises(RateLimitError):
        llm.complete("classify", "s", "u")
    assert len(client.messages.calls) == llm.MAX_ATTEMPTS
    assert llm.spend_usd() == pytest.approx(llm.MAX_ATTEMPTS * _projected())


def test_a_retry_the_budget_cannot_afford_is_refused_not_sent(tmp_env, monkeypatch):
    monkeypatch.setattr(llm, "_sleep", lambda seconds: None)
    _write_budget(llm.BUDGET_PATH, budget_usd=round(_projected() * 1.5, 6))
    client = _ScriptedClient([RateLimitError("429"), (10, 10)])
    _billed(monkeypatch, client)
    with pytest.raises(llm.LLMBudgetExceeded):
        llm.complete("classify", "s", "u")
    assert len(client.messages.calls) == 1


def test_the_real_client_has_sdk_retries_disabled(monkeypatch):
    """max_retries=0: the SDK's two silent retries per call were uncounted."""
    import sys
    import types

    made = []
    fake_anthropic = types.ModuleType("anthropic")
    fake_anthropic.Anthropic = lambda **kwargs: made.append(kwargs) or object()
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    monkeypatch.setitem(llm._CLIENT, "client", None)
    llm._client()
    assert made == [{"max_retries": 0}]


def test_only_transient_errors_are_retryable():
    assert llm._is_retryable(RateLimitError("x"))
    assert llm._is_retryable(_Status529("x"))
    assert not llm._is_retryable(ValueError("x"))
    assert not llm._is_retryable(llm.LLMError("x"))
    assert not llm._is_retryable(llm.LLMBudgetExceeded("x"))


def test_a_store_outage_during_the_reservation_is_refunded_to_the_process_only(tmp_env, monkeypatch):
    """Re-review repro: the reservation fell back to the process counter
    because the store was down, the store came back, and the reconcile then
    refunded the unused reservation FROM THE STORE, which never got the
    charge: a $5.00 total ended at $4.960116 after a $0.00012 call."""
    real_store = llm._store()
    real_store.set(llm.SPEND_KEY, 5.0)
    calls = {"n": 0}

    class _DownOnce(object):
        """The store is unreachable for the reservation, fine afterwards."""

        def __getattr__(self, name):
            return getattr(real_store, name)

        def mutate(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("modal.Dict unreachable")
            return real_store.mutate(*args, **kwargs)

    monkeypatch.setattr(llm, "_store", lambda: _DownOnce())
    monkeypatch.setattr(llm, "ledger_spend_usd", lambda path=None: 0.0)
    client = _ScriptedClient([(10, 10)])
    _billed(monkeypatch, client)

    llm.complete("classify", "s", "u")
    actual = llm.estimate_cost(llm.model_for("classify"), 10, 10)
    assert real_store.get(llm.SPEND_KEY) == pytest.approx(5.0), "the store never got the charge"
    assert llm._SPEND["process"] == pytest.approx(actual), "the process counter reconciles to the real cost"
    assert llm.spend_usd() == pytest.approx(5.0)


def test_a_reservation_in_the_store_is_reconciled_in_the_store(tmp_env, monkeypatch):
    llm._store().set(llm.SPEND_KEY, 5.0)
    _billed(monkeypatch, _ScriptedClient([(10, 10)]))
    llm.complete("classify", "s", "u")
    actual = llm.estimate_cost(llm.model_for("classify"), 10, 10)
    assert llm._store().get(llm.SPEND_KEY) == pytest.approx(5.0 + actual)
