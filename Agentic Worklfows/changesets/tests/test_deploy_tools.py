"""GOL-14, GOL-15 and GOL-6: the budget commands act on the deployed store,
the post-deploy check reads mode and live from /health, and log reads are
bounded. Every remote is faked."""
import json
import os
import pty
import select
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

from changesets.deploy import bounded_logs, budget, verify_health
from changesets.tests.deploy_fakes import FakeModalStore
from shared import llm


# ------------------------------------------------------------ GOL-14: budget
def test_budget_status_reads_the_deployed_counter_and_writes_nothing(tmp_env, capsys):
    store = FakeModalStore({llm.SPEND_KEY: 3.25}, read_only=True)
    assert budget.main(["status", "--store-mode", "shadow"], store=store) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["store"] == "advero-reply-engine-store-shadow"
    assert out["spent_usd"] == 3.25
    assert "redeploy" in out["note"]


def test_budget_reset_zeroes_the_deployed_counter_after_the_typed_word(tmp_env, capsys):
    store = FakeModalStore({llm.SPEND_KEY: 9.99})
    assert budget.main(["reset", "--store-mode", "live"], store=store, confirm=lambda w, p: True) == 0
    assert store.get(llm.SPEND_KEY) == 0.0
    # the counter is zeroed AND a new alert period opens, so the $8 and $10
    # alerts can each push once more (D1 round 3, defect 7)
    assert store.writes == [("set", llm.SPEND_KEY), ("set", llm.SPEND_PERIOD_KEY)]
    assert store.get(llm.SPEND_PERIOD_KEY)
    assert "advero-reply-engine-store-live" in capsys.readouterr().out


def test_budget_reset_without_the_typed_word_changes_nothing(tmp_env):
    store = FakeModalStore({llm.SPEND_KEY: 9.99})
    assert budget.main(["reset"], store=store, confirm=lambda w, p: False) == 1
    assert store.get(llm.SPEND_KEY) == 9.99 and store.writes == []


def test_budget_never_falls_back_to_a_laptop_number(tmp_env, capsys):
    store = FakeModalStore(missing=True, read_only=True)
    assert budget.main(["status"], store=store) == 2
    assert "Nothing was changed" in capsys.readouterr().out


def test_the_budget_tool_does_not_touch_the_laptop_store(tmp_env):
    from shared import store as store_mod

    local = store_mod.get_store(force_new=True)
    local.set(llm.SPEND_KEY, 7.0)
    deployed = FakeModalStore({llm.SPEND_KEY: 1.0})
    budget.main(["reset"], store=deployed, confirm=lambda w, p: True)
    assert local.get(llm.SPEND_KEY) == 7.0
    assert deployed.get(llm.SPEND_KEY) == 0.0


# ------------------------------------------------- GOL-15: post-deploy /health
HEALTHY_SHADOW = {"ok": True, "mode": "shadow", "live": False, "auto_send_after_minutes": 0,
                  "ghl_token": True, "webhook_secret": True, "base_url_set": True,
                  "approval_channels": {"ntfy_actions": True, "email": False, "any": True},
                  "templates": {"parity": "ok", "kill_switch": False, "approved_count": 3}}


WEB = "https://x--advero-reply-engine-web.modal.run"


def _secret_created(mode="shadow", host="x--advero-reply-engine-web.modal.run", status="created"):
    """What modal_secret.py --create records (names, lengths and the URL host)."""
    from changesets.deploy import modal_secret

    with open(modal_secret.history_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"mode": mode, "status": status, "base_url_host": host, "keys": {}}) + "\n")


@pytest.fixture
def created(tmp_env):
    _secret_created("shadow")
    _secret_created("live")
    return tmp_env


def _verify(health, argv):
    return verify_health.main(argv + ["--url", WEB], fetch=lambda url: dict(health), sleep=lambda s: None)


def test_health_passes_when_the_deployment_reports_the_expected_mode(created, capsys):
    assert _verify(HEALTHY_SHADOW, ["--expect-mode", "shadow"]) == 0
    assert "FAIL" not in capsys.readouterr().out


def test_health_fails_when_the_secret_carries_another_deployments_url(tmp_env, capsys):
    """Review item 10c: base_url_set is only yes or no; the host is compared."""
    _secret_created("shadow", host="old-workspace--advero-reply-engine-web.modal.run")
    assert _verify(HEALTHY_SHADOW, ["--expect-mode", "shadow"]) == 1
    assert "FAIL  BASE_URL host is this deployment's" in capsys.readouterr().out
    _secret_created("shadow", status="create_failed")          # a failed create proves nothing
    assert _verify(HEALTHY_SHADOW, ["--expect-mode", "shadow"]) == 1
    _secret_created("shadow")
    assert _verify(HEALTHY_SHADOW, ["--expect-mode", "shadow"]) == 0
    # and a later app that reports its host is compared as well
    assert _verify(dict(HEALTHY_SHADOW, base_url_host="elsewhere.modal.run"), ["--expect-mode", "shadow"]) == 1


def test_health_fails_with_no_record_of_the_secret(tmp_env, capsys):
    assert _verify(HEALTHY_SHADOW, ["--expect-mode", "shadow"]) == 1


def test_health_fails_when_the_deployment_is_live_but_shadow_was_expected(created, capsys):
    live = dict(HEALTHY_SHADOW, mode="live", live=True)
    assert _verify(live, ["--expect-mode", "shadow"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  mode is shadow" in out and "FAIL  live is false" in out


def test_health_fails_on_the_fallback_app_and_on_a_missing_base_url(created, capsys):
    assert _verify({"ok": False, "app": "missing", "detail": "ImportError"}, ["--expect-mode", "shadow"]) == 1
    assert _verify(dict(HEALTHY_SHADOW, base_url_set=False), ["--expect-mode", "shadow"]) == 1
    # the first pass knows the URL is not set yet
    assert _verify(dict(HEALTHY_SHADOW, base_url_set=False), ["--expect-mode", "shadow", "--first-pass"]) == 0


def test_health_fails_when_no_channel_can_carry_buttons(created, capsys):
    none = dict(HEALTHY_SHADOW, approval_channels={"ntfy_actions": False, "email": False, "any": False})
    assert _verify(none, ["--expect-mode", "shadow"]) == 1


@pytest.mark.parametrize("parity", ["mismatch", "reference_missing", "error"])
def test_health_fails_when_template_parity_is_not_ok(created, capsys, parity):
    """CT3-E1: a catalogue that does not match the reference fails the deploy.
    The message names the status only."""
    bad = dict(HEALTHY_SHADOW, templates={"parity": parity, "kill_switch": False, "approved_count": 3})
    assert _verify(bad, ["--expect-mode", "shadow"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  template parity is ok  (parity=%r)" % parity in out
    assert out.count("FAIL") == 2          # the parity check, and the "N check(s) FAILED" line


def test_health_fails_when_the_templates_block_is_missing(created, capsys):
    old_app = dict(HEALTHY_SHADOW)
    del old_app["templates"]
    assert _verify(old_app, ["--expect-mode", "shadow"]) == 1
    assert "FAIL  template parity is ok  (templates block missing)" in capsys.readouterr().out
    assert _verify(dict(HEALTHY_SHADOW, templates=None), ["--expect-mode", "shadow"]) == 1
    assert _verify(dict(HEALTHY_SHADOW, templates={}), ["--expect-mode", "shadow"]) == 1


def test_template_parity_detail_carries_no_template_text():
    health = dict(HEALTHY_SHADOW, templates={"parity": "mismatch", "kill_switch": True, "approved_count": 0,
                                             "ids": ["cadence.d1"], "text": "Hey {name}"})
    name, passed, detail = verify_health.template_parity_check(health)
    assert passed is False and detail == "parity='mismatch'"


def _sequence(bodies):
    """A fetch that answers each body in turn (an Exception instance is raised),
    and the list of calls and sleeps it saw."""
    calls, sleeps = [], []
    queue = list(bodies)

    def fetch(url):
        calls.append(url)
        body = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(body, Exception):
            raise body
        return dict(body)
    return fetch, calls, sleeps


NOT_READY = dict(HEALTHY_SHADOW, templates={"parity": "not_ready", "kill_switch": False, "approved_count": 3})


def test_health_polls_again_while_parity_is_not_ready(created, capsys):
    """Flag 15: not_ready means the app is still importing; a later poll
    answers ok, so it is re-polled rather than failed at once."""
    fetch, calls, sleeps = _sequence([NOT_READY, NOT_READY, HEALTHY_SHADOW])
    code = verify_health.main(["--expect-mode", "shadow", "--url", WEB], fetch=fetch, sleep=sleeps.append)
    out = capsys.readouterr().out
    assert code == 0, out
    assert len(calls) == 3 and sleeps == [verify_health.RETRY_SECONDS] * 2
    assert "PASS  template parity is ok  (parity='ok')" in out and "FAIL" not in out


def test_health_fails_when_parity_stays_not_ready(created, capsys):
    fetch, calls, sleeps = _sequence([NOT_READY])
    code = verify_health.main(["--expect-mode", "shadow", "--url", WEB, "--attempts", "3"], fetch=fetch,
                              sleep=sleeps.append)
    out = capsys.readouterr().out
    assert code == 1
    assert len(calls) == 3 and len(sleeps) == 2          # bounded by --attempts, no sleep after the last
    assert "FAIL  template parity is ok  (parity='not_ready')" in out


def test_health_shares_one_budget_between_a_cold_start_and_not_ready(created, capsys):
    fetch, calls, sleeps = _sequence([OSError("refused"), NOT_READY, HEALTHY_SHADOW])
    assert verify_health.main(["--expect-mode", "shadow", "--url", WEB], fetch=fetch, sleep=sleeps.append) == 0
    assert len(calls) == 3
    fetch, calls, sleeps = _sequence([OSError("refused"), NOT_READY, HEALTHY_SHADOW])
    assert verify_health.main(["--expect-mode", "shadow", "--url", WEB, "--attempts", "2"], fetch=fetch,
                              sleep=sleeps.append) == 1
    assert len(calls) == 2
    assert "parity='not_ready'" in capsys.readouterr().out


@pytest.mark.parametrize("templates", [{"parity": "mismatch"}, {"parity": "reference_missing"}, {"parity": "error"},
                                       None, {}, "missing"])
def test_health_does_not_re_poll_a_final_parity_status(created, capsys, templates):
    body = dict(HEALTHY_SHADOW)
    if templates == "missing":
        del body["templates"]
    else:
        body["templates"] = templates
    fetch, calls, sleeps = _sequence([body, HEALTHY_SHADOW])
    assert verify_health.main(["--expect-mode", "shadow", "--url", WEB], fetch=fetch, sleep=sleeps.append) == 1
    assert len(calls) == 1 and sleeps == []
    assert "FAIL  template parity is ok" in capsys.readouterr().out


def test_health_retries_a_cold_start_then_fails_honestly(tmp_env, capsys):
    calls = []

    def fetch(url):
        calls.append(url)
        raise OSError("connection refused")

    code = verify_health.main(["--expect-mode", "shadow", "--url", "https://x.modal.run", "--attempts", "3"],
                              fetch=fetch, sleep=lambda s: None)
    assert code == 1 and len(calls) == 3
    assert "did not answer" in capsys.readouterr().out


def test_health_reads_the_url_the_deploy_saved(tmp_env, capsys):
    from changesets.deploy import common

    with open(common.web_url_file(), "w", encoding="utf-8") as fh:
        fh.write("https://saved--advero-reply-engine-web.modal.run\n")
    seen = []
    verify_health.main(["--expect-mode", "shadow"], fetch=lambda url: seen.append(url) or dict(HEALTHY_SHADOW),
                       sleep=lambda s: None)
    assert seen == ["https://saved--advero-reply-engine-web.modal.run"]


def test_health_refuses_without_an_https_url(tmp_env, capsys):
    assert verify_health.main(["--expect-mode", "shadow"], fetch=lambda url: {}, sleep=lambda s: None) == 1


# ------------------------------------------------------ GOL-6: bounded logs
class FakePopen(object):
    """A `modal app logs` that prints three lines and then streams forever."""

    instances = []

    def __init__(self, cmd, **kwargs):
        import threading

        self.cmd = cmd
        self.terminated = False
        self._done = threading.Event()
        lines = ["2026-09-24 poller tick\n", "BASE_URL is unset\n", "2026-09-24 sweep tick\n"]
        self.stdout = self._stream(lines)
        FakePopen.instances.append(self)

    def _stream(self, lines):
        for line in lines:
            yield line
        self._done.wait(30)          # "streams while the app runs" until terminated

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True
        self._done.set()

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminate()


def test_bounded_logs_stop_the_stream_and_count(capsys):
    FakePopen.instances = []
    assert bounded_logs.main(["--seconds", "1", "--grep", "BASE_URL is unset", "--count"], popen=FakePopen) == 0
    assert capsys.readouterr().out.strip() == "1"
    proc = FakePopen.instances[0]
    assert proc.terminated is True
    assert proc.cmd[1:] == ["-m", "modal", "app", "logs", "advero-reply-engine", "--timestamps"]


# ------------------------------------ CT3-E1: install_schedules.sh steps 7 and 8
INSTALL_SH = Path(__file__).resolve().parents[2] / "changesets" / "schedules" / "install_schedules.sh"

PREFLIGHT_FAKE_PYTHON = r"""#!/bin/bash
# Stands in for python3 inside a copy of install_schedules.sh --preflight.
echo "$*" >> "$FAKE_LOG"
case "$1" in
  changesets/deploy/template_parity.py)
    case "$2" in
      --write) exit "${WRITE_RC:-0}" ;;
      --check) exit "${CHECK_RC:-0}" ;;
      --report-unapproved) printf '%b' "${REPORT:-UNAPPROVED LADDER IDS: 0\nUNEXTRACTABLE LADDER IDS: 0\nKILL SWITCH: off\n}"; exit "${REPORT_RC:-0}" ;;
    esac ;;
  -) body="$(cat)"
     case "$body" in *_write_after_preflight*) echo "STAMP" >> "$FAKE_LOG"; echo "preflight stamp written: x" ;; esac
     exit 0 ;;
esac
exit 0
"""


def _preflight_copy(tmp_path, env):
    root = tmp_path / "repo"
    (root / "changesets" / "schedules").mkdir(parents=True)
    shutil.copy(str(INSTALL_SH), str(root / "changesets" / "schedules" / "install_schedules.sh"))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "python3"
    fake.write_text(PREFLIGHT_FAKE_PYTHON)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.log"
    # built from os.environ, so the session's test flag reaches the child
    child_env = dict(os.environ)
    for key in ("WRITE_RC", "CHECK_RC", "REPORT", "REPORT_RC"):
        child_env.pop(key, None)
    child_env.update({"PATH": "%s:/usr/bin:/bin" % bindir, "FAKE_LOG": str(log), "TERM": "dumb"})
    child_env.update(dict((k, str(v)) for k, v in env.items()))
    return root / "changesets" / "schedules" / "install_schedules.sh", child_env, log


def _calls(log):
    return log.read_text().splitlines() if log.exists() else []


def _run_preflight_no_tty(tmp_path, **env):
    """A COPY of install_schedules.sh --preflight with a fake python3, stdin
    from /dev/null and no controlling terminal. Nothing real runs."""
    script, child_env, log = _preflight_copy(tmp_path, env)
    proc = subprocess.run(["/bin/bash", str(script), "--preflight"], env=child_env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, timeout=60)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), _calls(log)


def _run_preflight_on_pty(tmp_path, answer, **env):
    """The same copy on a pseudo-terminal, typing ``answer`` at the HOLD prompt."""
    script, child_env, log = _preflight_copy(tmp_path, env)
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execve("/bin/bash", ["bash", str(script), "--preflight"], child_env)
        finally:
            os._exit(127)
    out = b""
    sent = False
    deadline = time.time() + 30
    while time.time() < deadline:
        ready, _w, _x = select.select([fd], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        if not sent and b"[type HOLD]" in out:
            os.write(fd, answer.encode("utf-8") + b"\n")
            sent = True
    _pid, status = os.waitpid(pid, 0)
    os.close(fd)
    return os.WEXITSTATUS(status), out.decode("utf-8", "replace"), _calls(log)


HEAD = r"UNAPPROVED LADDER IDS: %s\nUNEXTRACTABLE LADDER IDS: %s\nKILL SWITCH: %s\n"
TWO_UNAPPROVED = HEAD % (2, 0, "off") + r"Not approved at their current text:\n  cadence.d3\n  no_show.n1\n"


def test_the_preflight_text_has_steps_7_and_8_before_the_stamp():
    text = INSTALL_SH.read_text(encoding="utf-8")
    pre = text[text.index("preflight() {"):text.index("abort_text() {")]
    write = pre.index("template_parity.py --write")
    check = pre.index("template_parity.py --check")
    report = pre.index("template_parity.py --report-unapproved")
    stamp = pre.index("preflight_stamp._write_after_preflight()")
    assert pre.index("== 6.") < pre.index("== 7.") < write < check < pre.index("== 8.") < report < stamp
    assert "[type HOLD]" in pre and '"$hold" != "HOLD"' in pre
    assert "[ ! -t 0 ]" in pre and "< /dev/tty" in pre[report:stamp]


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
def test_the_preflight_passes_with_every_ladder_approved(tmp_path):
    code, out, calls = _run_preflight_no_tty(tmp_path)
    assert code == 0, out
    parity = [c for c in calls if c.startswith("changesets/deploy/template_parity.py")]
    assert parity == ["changesets/deploy/template_parity.py --write", "changesets/deploy/template_parity.py --check",
                      "changesets/deploy/template_parity.py --report-unapproved"]
    assert calls.index(parity[-1]) < calls.index("STAMP")
    assert "UNAPPROVED LADDER IDS: 0" in out and "[type HOLD]" not in out


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
@pytest.mark.parametrize("env,stops_after", [({"WRITE_RC": 1}, "--write"), ({"CHECK_RC": 1}, "--check"),
                                             ({"REPORT_RC": 1}, "--report-unapproved"),
                                             ({"REPORT": r"something else\n"}, "--report-unapproved"),
                                             ({"REPORT": r"UNAPPROVED LADDER IDS: two\n"}, "--report-unapproved"),
                                             ({"REPORT": r"UNAPPROVED LADDER IDS: 0\n"}, "--report-unapproved"),
                                             ({"REPORT": HEAD % (0, "x", "off")}, "--report-unapproved"),
                                             ({"REPORT": HEAD % (0, 0, "maybe")}, "--report-unapproved"),
                                             ({"REPORT": HEAD % ("-1", 0, "off")}, "--report-unapproved")])
def test_a_parity_failure_stops_the_preflight_before_the_stamp(tmp_path, env, stops_after):
    code, out, calls = _run_preflight_no_tty(tmp_path, **env)
    assert code != 0, out
    assert "STAMP" not in calls
    assert "REFUSING" in out and "Not deployed" in out
    assert calls[-1] == "changesets/deploy/template_parity.py " + stops_after


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
def test_unapproved_ladders_abort_without_an_interactive_terminal(tmp_path):
    code, out, calls = _run_preflight_no_tty(tmp_path, REPORT=TWO_UNAPPROVED)
    assert code != 0, out
    assert "cadence.d3" in out and "no_show.n1" in out
    assert "No interactive terminal to read the HOLD answer from. Not deployed." in out
    assert "STAMP" not in calls


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
@pytest.mark.parametrize("answer", ["hold", "HOLD ", "yes", ""])
def test_anything_but_hold_aborts(tmp_path, answer):
    code, out, calls = _run_preflight_on_pty(tmp_path, answer, REPORT=TWO_UNAPPROVED)
    assert "[type HOLD]" in out
    assert code != 0, out
    assert "STAMP" not in calls


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
def test_typing_hold_continues_to_the_stamp(tmp_path):
    code, out, calls = _run_preflight_on_pty(tmp_path, "HOLD", REPORT=TWO_UNAPPROVED)
    assert code == 0, out
    assert "HOLD accepted: 2 unapproved and 0 unrendered ladder template(s) stay held." in out
    assert calls[-1] == "STAMP"


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
@pytest.mark.parametrize("report", [HEAD % (0, 1, "off") + r"Could not be rendered:\n  show_rate.confirm_email\n",
                                    HEAD % ("00", 0, "off"), HEAD % (0, "00", "off")])
def test_unrendered_ladders_or_an_odd_zero_also_ask_for_hold(tmp_path, report):
    """Anything but a clean 0 and 0 asks for HOLD (the comparison fails closed)."""
    code, out, calls = _run_preflight_no_tty(tmp_path, REPORT=report)
    assert code != 0, out
    assert "No interactive terminal to read the HOLD answer from. Not deployed." in out
    assert "STAMP" not in calls


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
def test_the_kill_switch_state_is_shown_and_warned(tmp_path):
    code, out, calls = _run_preflight_no_tty(tmp_path, REPORT=HEAD % (0, 0, "on"))
    assert code == 0, out
    assert "KILL SWITCH: on" in out
    assert "WARNING: the template kill switch is ON" in out and "is held, approved or not" in out
    assert calls[-1] == "STAMP"
    code, out, calls = _run_preflight_no_tty(tmp_path / "off", REPORT=HEAD % (0, 0, "off"))
    assert code == 0 and "WARNING: the template kill switch" not in out
