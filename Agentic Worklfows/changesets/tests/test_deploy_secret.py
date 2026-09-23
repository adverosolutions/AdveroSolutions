"""GOL-5 / GOL-7: the Modal secret is built from .env by one script that never
prints a value, never uses a placeholder or a blank, never generates
REPLY_ENGINE_SECRET, and only runs `modal secret create --force` when told to.

Every .env here is a temp file with fake values; the subprocess is mocked.
"""
import json
import os
import subprocess

import pytest

import conftest
from changesets.deploy import modal_secret

SECRET = "f" * 48
FAKE_ENV = {
    "INSTANTLY_API_KEY": "inst-key-0123456789",
    "ANTHROPIC_API_KEY": "sk-ant-fake-0123456789",
    "NTFY_TOPIC": "lz-fake-topic-8812",
    "GHL_PRIVATE_INTEGRATION_TOKEN": "pit-fake-0123456789",
    "NTFY_ALLOW_SENSITIVE": "1",
    "REPLY_ENGINE_SECRET": SECRET,
    "GMAIL_SENDER_EMAIL": "",
    "NOTIFY_EMAIL": "",
    "MODE": "live",                 # the .env's own MODE must never reach the secret
    "ALLOW_LIVE_WRITES": "1",
    "ALLOW_PAID_CALLS": "1",
    "APIFY_API_TOKEN": "apify-fake-0123456789",
}


def _write_env(tmp_path, values, name=".env"):
    path = tmp_path / name
    path.write_text("".join("%s=%s\n" % (k, v) for k, v in values.items()), encoding="utf-8")
    return str(path)


class FakeRun(object):
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []
        self.payloads = []
        self.modes = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        path = cmd[cmd.index("--from-json") + 1]
        self.modes.append(oct(os.stat(path).st_mode & 0o777))
        with open(path, "r", encoding="utf-8") as fh:
            self.payloads.append(json.load(fh))
        return subprocess.CompletedProcess(cmd, self.returncode, stdout="", stderr=self.stderr)


def _main(tmp_path, argv, env=None, runner=None, confirm=lambda word, prompt: True):
    path = _write_env(tmp_path, FAKE_ENV if env is None else env)
    return modal_secret.main(argv + ["--env-file", path], runner=runner or FakeRun(), confirm=confirm,
                             env_loader=conftest._real_dotenv_values)


# ------------------------------------------------------------------ building
def test_a_shadow_secret_from_env_has_every_value_from_env_and_no_blank(tmp_env):
    values, source, notes = modal_secret.build_secret(dict(FAKE_ENV), "shadow")
    for key in ("INSTANTLY_API_KEY", "ANTHROPIC_API_KEY", "NTFY_TOPIC", "GHL_PRIVATE_INTEGRATION_TOKEN",
                "NTFY_ALLOW_SENSITIVE", "REPLY_ENGINE_SECRET"):
        assert values[key] == FAKE_ENV[key]
    assert values["MODE"] == "shadow" and values["ALLOW_LIVE_WRITES"] == "0"
    assert values["NOTIFY_SHADOW_SEND"] == "1"
    assert values["ALLOW_PAID_CALLS"] == "0"
    assert values["WEBHOOK_SECRET"] == values["DEBUG_SECRET"] == SECRET
    assert values["A2P_10DLC_REGISTERED"] == "0" and values["CADENCE_D6_HOLD"] == "0"
    assert all(v.strip() for v in values.values())
    # blank optional keys are left out, never sent empty
    assert "GMAIL_SENDER_EMAIL" not in values and "NOTIFY_EMAIL" not in values
    # the list factory's token is not sent to Modal
    assert "APIFY_API_TOKEN" not in values
    # first pass: no BASE_URL at all, and a note that the buttons are dead until the second pass
    assert "BASE_URL" not in values
    assert any("BASE_URL is left OUT" in n for n in notes)


def test_every_key_it_writes_is_a_key_the_app_reads():
    from services.reply_engine import modal_app

    classified = (set(modal_secret.REQUIRED_FROM_ENV) | set(modal_secret.DEFAULT_OFF_FROM_ENV)
                  | set(modal_secret.OPTIONAL_FROM_ENV) | set(modal_secret.SET_HERE) | set(modal_secret.NOT_SENT))
    assert classified == set(modal_app.SECRET_KEYS), classified ^ set(modal_app.SECRET_KEYS)
    assert "NTFY_ALLOW_SENSITIVE" in modal_secret.REQUIRED_FROM_ENV


def test_a_missing_required_key_refuses_and_names_it(tmp_env):
    env = dict(FAKE_ENV)
    env.pop("GHL_PRIVATE_INTEGRATION_TOKEN")
    env["NTFY_ALLOW_SENSITIVE"] = ""
    with pytest.raises(modal_secret.SecretRefused) as exc:
        modal_secret.build_secret(env, "shadow")
    assert "GHL_PRIVATE_INTEGRATION_TOKEN" in str(exc.value)
    assert "NTFY_ALLOW_SENSITIVE" in str(exc.value)


@pytest.mark.parametrize("value", ["<Job_Log sheet id, optional>", "paste_your_json_here", "changeme",
                                   "your_token_here"])
def test_a_placeholder_refuses(tmp_env, value):
    env = dict(FAKE_ENV, JOB_LOG_SHEET_ID=value)
    with pytest.raises(modal_secret.SecretRefused) as exc:
        modal_secret.build_secret(env, "shadow")
    assert "JOB_LOG_SHEET_ID looks like a placeholder" in str(exc.value)
    assert value not in str(exc.value)


def test_the_env_placeholder_service_account_refuses(tmp_env):
    env = dict(FAKE_ENV, GOOGLE_CREDENTIALS_JSON='{"type": "service_account", "paste_your_json_here": "..."}')
    with pytest.raises(modal_secret.SecretRefused) as exc:
        modal_secret.build_secret(env, "shadow")
    assert "GOOGLE_CREDENTIALS_JSON" in str(exc.value)


def test_a_real_looking_service_account_is_sent_as_json(tmp_env):
    info = {"type": "service_account", "client_email": "svc@proj.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIfake\n-----END PRIVATE KEY-----\n"}
    values, _s, _n = modal_secret.build_secret(dict(FAKE_ENV, GOOGLE_CREDENTIALS_JSON=json.dumps(info)), "shadow")
    assert json.loads(values["GOOGLE_CREDENTIALS_JSON"]) == info


def test_no_button_channel_refuses(tmp_env):
    env = dict(FAKE_ENV, NTFY_ALLOW_SENSITIVE="0")
    with pytest.raises(modal_secret.SecretRefused) as exc:
        modal_secret.build_secret(env, "shadow")
    assert "buttons" in str(exc.value)
    # the full email leg is enough on its own
    env.update(GMAIL_SENDER_EMAIL="lz@advero.test", GMAIL_APP_PASSWORD="abcd efgh ijkl mnop",
               NOTIFY_EMAIL="lz@advero.test")
    values, _s, _n = modal_secret.build_secret(env, "shadow")
    assert values["NOTIFY_EMAIL"] == "lz@advero.test"


def test_live_needs_a_public_base_url_and_sets_the_live_pair(tmp_env):
    with pytest.raises(modal_secret.SecretRefused):
        modal_secret.build_secret(dict(FAKE_ENV), "live")
    with pytest.raises(modal_secret.SecretRefused):
        modal_secret.build_secret(dict(FAKE_ENV), "live", base_url="http://localhost:8000")
    url = "https://advero--advero-reply-engine-web.modal.run"
    values, _s, _n = modal_secret.build_secret(dict(FAKE_ENV), "live", base_url=url)
    assert (values["MODE"], values["ALLOW_LIVE_WRITES"]) == ("live", "1")
    assert values["BASE_URL"] == values["REPLY_ENGINE_BASE_URL"] == url
    assert values["ALLOW_PAID_CALLS"] == "0"


def test_a_localhost_base_url_in_env_counts_as_unset(tmp_env):
    values, _s, notes = modal_secret.build_secret(dict(FAKE_ENV, BASE_URL="http://localhost:8000"), "shadow")
    assert "BASE_URL" not in values
    assert any("not a public https URL" in n for n in notes)


# ----------------------------------------------------- REPLY_ENGINE_SECRET
def test_the_reply_engine_secret_is_never_generated(tmp_env):
    env = dict(FAKE_ENV)
    env.pop("REPLY_ENGINE_SECRET")
    with pytest.raises(modal_secret.SecretRefused) as exc:
        modal_secret.build_secret(env, "shadow")
    assert "REPLY_ENGINE_SECRET" in str(exc.value)
    # and when it exists, the value sent is exactly the saved one, every time
    first, _s, _n = modal_secret.build_secret(dict(FAKE_ENV), "shadow")
    second, _s, _n = modal_secret.build_secret(dict(FAKE_ENV), "live",
                                               base_url="https://a--advero-reply-engine-web.modal.run")
    assert first["REPLY_ENGINE_SECRET"] == second["REPLY_ENGINE_SECRET"] == SECRET
    source = open(modal_secret.__file__, "r", encoding="utf-8").read()
    for generator in ("token_hex(", "token_urlsafe(", "urandom(", "openssl rand", "uuid4("):
        assert generator not in source.split('"""', 2)[2], generator


def test_a_second_saved_copy_that_disagrees_refuses(tmp_env):
    (tmp_env / modal_secret.LEGACY_SECRET_NAME).write_text("0" * 48, encoding="utf-8")
    with pytest.raises(modal_secret.SecretRefused) as exc:
        modal_secret.build_secret(dict(FAKE_ENV), "shadow")
    assert "DIFFERENT" in str(exc.value)
    assert "0" * 48 not in str(exc.value)


def test_a_webhook_secret_alias_that_disagrees_refuses(tmp_env):
    with pytest.raises(modal_secret.SecretRefused):
        modal_secret.build_secret(dict(FAKE_ENV, WEBHOOK_SECRET="e" * 48), "shadow")


# -------------------------------------------------------------- the CLI
def test_the_plan_prints_names_and_lengths_never_values(tmp_path, tmp_env, capsys):
    fake = FakeRun()
    assert _main(tmp_path, ["--mode", "shadow"], runner=fake) == 0
    out = capsys.readouterr().out
    assert fake.calls == []                                    # plan only: nothing run
    for key, value in FAKE_ENV.items():
        if len(value) >= 4 and key not in ("MODE",):
            assert value not in out, key
    assert "REPLY_ENGINE_SECRET" in out and "   48 chars" in out
    assert "Nothing was created" in out


def test_create_runs_modal_once_with_force_from_a_private_file_then_deletes_it(tmp_path, tmp_env, capsys):
    fake = FakeRun()
    assert _main(tmp_path, ["--mode", "shadow", "--create"], runner=fake) == 0
    assert len(fake.calls) == 1
    cmd = fake.calls[0]
    assert cmd[1:6] == ["-m", "modal", "secret", "create", "advero-reply-engine"]
    assert "--force" in cmd and "--from-json" in cmd
    assert fake.modes == ["0o600"]
    path = cmd[cmd.index("--from-json") + 1]
    assert not os.path.exists(path)                            # deleted after
    sent = fake.payloads[0]
    assert sent["REPLY_ENGINE_SECRET"] == SECRET and sent["MODE"] == "shadow"
    assert all(isinstance(v, str) and v.strip() for v in sent.values())
    assert SECRET not in capsys.readouterr().out
    # values never reach argv, only the file
    assert not any(SECRET in part for part in cmd)
    # a history line with names and lengths, no values
    with open(str(tmp_env / "deploy" / "secret_history.jsonl"), "r", encoding="utf-8") as fh:
        history = [json.loads(line) for line in fh]
    assert history[-1]["status"] == "created" and history[-1]["keys"]["REPLY_ENGINE_SECRET"] == 48
    assert SECRET not in json.dumps(history)


def test_create_without_the_typed_word_runs_nothing(tmp_path, tmp_env):
    fake = FakeRun()
    assert _main(tmp_path, ["--mode", "shadow", "--create"], runner=fake,
                 confirm=lambda word, prompt: False) == 1
    assert fake.calls == []


def test_a_refused_build_runs_nothing(tmp_path, tmp_env):
    env = dict(FAKE_ENV)
    env.pop("INSTANTLY_API_KEY")
    fake = FakeRun()
    assert _main(tmp_path, ["--mode", "shadow", "--create"], env=env, runner=fake) == 1
    assert fake.calls == []


def test_a_modal_error_is_shown_without_values(tmp_path, tmp_env, capsys):
    fake = FakeRun(returncode=1, stderr="boom near %s" % SECRET)
    assert _main(tmp_path, ["--mode", "shadow", "--create"], runner=fake) == 1
    out = capsys.readouterr().out
    assert "FAILED" in out and SECRET not in out and "<redacted>" in out


def test_the_confirmation_reads_the_terminal_not_stdin():
    from changesets.deploy import common

    def no_tty(path, mode="r"):
        raise OSError("no tty")

    assert common.confirm_from_tty("CREATE", "ok?", opener=no_tty) is False

    class Tty(object):
        def __init__(self, answer):
            self.answer = answer

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def write(self, text):
            pass

        def flush(self):
            pass

        def readline(self):
            return self.answer

    assert common.confirm_from_tty("CREATE", "ok?", opener=lambda p, m="r": Tty("CREATE\n")) is True
    assert common.confirm_from_tty("CREATE", "ok?", opener=lambda p, m="r": Tty("create\n")) is False


# --------------------------------------------- review item 10c: the base URL
@pytest.mark.parametrize("mode", ["shadow", "live"])
@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_base_url_refuses_and_never_falls_back(tmp_path, tmp_env, mode, value, capsys):
    """What --base-url "$(cat .tmp/deploy/web_url.txt)" passes when the file is
    missing. It must not quietly become a first pass or the .env BASE_URL."""
    env = dict(FAKE_ENV, BASE_URL="https://stale--advero-reply-engine-web.modal.run")
    run = FakeRun()
    assert _main(tmp_path, ["--mode", mode, "--base-url", value, "--create"], env=env, runner=run) == 1
    assert run.calls == []
    assert "empty value" in capsys.readouterr().out


def test_create_records_the_base_url_host_for_the_health_check(tmp_path, tmp_env):
    url = "https://x--advero-reply-engine-web.modal.run"
    assert _main(tmp_path, ["--mode", "shadow", "--base-url", url, "--create"]) == 0
    from changesets.deploy import verify_health

    assert verify_health.last_secret_host("shadow") == "x--advero-reply-engine-web.modal.run"
    with open(modal_secret.history_path(), "r", encoding="utf-8") as fh:
        text = fh.read()
    assert SECRET not in text and "inst-key" not in text


# ------------------------- CT1 round 3: an empty AUTO_SEND_TEMPLATES= is the kill switch on both sides
@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_auto_send_templates_is_sent_as_off_as_the_laptop_reads_it(tmp_path, tmp_env, monkeypatch, value):
    from services.reply_engine import template_approvals

    values, source, notes = modal_secret.build_secret(dict(FAKE_ENV, AUTO_SEND_TEMPLATES=value), "shadow")
    assert values["AUTO_SEND_TEMPLATES"] == "off"
    assert "kill switch" in source["AUTO_SEND_TEMPLATES"]
    assert any(n.startswith("AUTO_SEND_TEMPLATES is empty in .env") for n in notes)
    # the laptop (dotenv puts the empty value in its environment) and Modal (the secret's value) both read "off"
    no_file = str(tmp_path / "no_approvals_file.json")
    for seen in (value, values["AUTO_SEND_TEMPLATES"]):
        monkeypatch.setenv(template_approvals.KILL_SWITCH_ENV, seen)
        assert template_approvals.kill_switch_on(no_file), repr(seen)


def test_an_empty_auto_send_templates_line_reaches_modal_as_off(tmp_path, tmp_env):
    run = FakeRun()
    assert _main(tmp_path, ["--mode", "shadow", "--create"], env=dict(FAKE_ENV, AUTO_SEND_TEMPLATES=""),
                 runner=run) == 0
    assert run.payloads[0]["AUTO_SEND_TEMPLATES"] == "off"


def test_only_auto_send_templates_turns_an_empty_value_into_off(tmp_path, tmp_env):
    # absent from .env: left out, so Modal reads it as not set, as the laptop does
    values, _s, _n = modal_secret.build_secret(dict(FAKE_ENV), "shadow")
    assert "AUTO_SEND_TEMPLATES" not in values
    path = _write_env(tmp_path, FAKE_ENV)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("AUTO_SEND_TEMPLATES\n")   # a bare name: dotenv gives no value, so it is not set either
    env = modal_secret.read_env_files([path], loader=conftest._real_dotenv_values)
    assert "AUTO_SEND_TEMPLATES" not in modal_secret.build_secret(env, "shadow")[0]
    # a real value passes through unchanged
    values, _s, _n = modal_secret.build_secret(dict(FAKE_ENV, AUTO_SEND_TEMPLATES="1"), "shadow")
    assert values["AUTO_SEND_TEMPLATES"] == "1"
    # every other optional key that is empty is still left out
    empty = dict((k, "") for k in modal_secret.OPTIONAL_FROM_ENV)
    values, _s, _n = modal_secret.build_secret(dict(FAKE_ENV, **empty), "shadow")
    assert [k for k in modal_secret.OPTIONAL_FROM_ENV if k in values] == ["AUTO_SEND_TEMPLATES"]
    assert set(modal_secret.EMPTY_IS_OFF) == {"AUTO_SEND_TEMPLATES"}
