"""Decision R2(a): reads use the read-only key, writes the write-capable one.

shared/keys.py picks the key; shared/instantly.py and shared/ghl.py send it per
method (not per HTTP verb); changesets/deploy/modal_secret.py takes the write
keys from ~/.advero/live.env. Every key here is a fake string, every transport
is an httpx.MockTransport, and every HOME is a temp dir.
"""
import json
import logging
import os
import subprocess

import httpx
import pytest

import conftest
from changesets.deploy import modal_secret
from shared import job_log, keys, settings
from shared.ghl import GHL, GHLError, GHLScopeError
from shared.instantly import Instantly, InstantlyError, InstantlyScopeError, endpoint_info

I_READ = "inst-READ-fake-7f3a9c11"
I_WRITE = "inst-WRITE-fake-2b8d4155"
G_READ = "ghl-READ-fake-90ae33c2"
G_WRITE = "ghl-WRITE-fake-51d0e7f4"
ALL_FAKE_KEYS = (I_READ, I_WRITE, G_READ, G_WRITE)


class Recorder(object):
    def __init__(self, responses=None):
        self.requests = []
        self.responses = list(responses or [])

    def __call__(self, request):
        self.requests.append(request)
        if self.responses:
            status, body = self.responses.pop(0)
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"items": [], "next_starting_after": None})

    def bearers(self):
        return [r.headers.get("Authorization", "").replace("Bearer ", "") for r in self.requests]


@pytest.fixture
def both_keys(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", I_WRITE)
    monkeypatch.setenv("INSTANTLY_API_KEY_READ", I_READ)
    monkeypatch.setenv("GHL_PRIVATE_INTEGRATION_TOKEN", G_WRITE)
    monkeypatch.setenv("GHL_PRIVATE_INTEGRATION_TOKEN_READ", G_READ)
    keys._reset_warnings()
    yield
    keys._reset_warnings()


@pytest.fixture
def read_only_keys(monkeypatch):
    """An agent session after the move: only the _READ keys exist."""
    monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
    monkeypatch.delenv("GHL_PRIVATE_INTEGRATION_TOKEN", raising=False)
    monkeypatch.setenv("INSTANTLY_API_KEY_READ", I_READ)
    monkeypatch.setenv("GHL_PRIVATE_INTEGRATION_TOKEN_READ", G_READ)
    keys._reset_warnings()
    yield
    keys._reset_warnings()


@pytest.fixture
def main_keys_only(monkeypatch):
    """Today: no read keys yet, the main keys serve everything."""
    monkeypatch.setenv("INSTANTLY_API_KEY", I_WRITE)
    monkeypatch.delenv("INSTANTLY_API_KEY_READ", raising=False)
    monkeypatch.setenv("GHL_PRIVATE_INTEGRATION_TOKEN", G_WRITE)
    monkeypatch.delenv("GHL_PRIVATE_INTEGRATION_TOKEN_READ", raising=False)
    keys._reset_warnings()
    yield
    keys._reset_warnings()


def instantly(responses=None):
    rec = Recorder(responses)
    return Instantly(transport=httpx.MockTransport(rec), sleep=lambda s: None), rec


def ghl(responses=None):
    rec = Recorder(responses)
    return GHL(transport=httpx.MockTransport(rec)), rec


# ------------------------------------------------------------ shared.keys
def test_the_table_names_both_systems():
    assert keys.main_name("instantly") == "INSTANTLY_API_KEY"
    assert keys.read_name("instantly") == "INSTANTLY_API_KEY_READ"
    assert keys.main_name("ghl") == "GHL_PRIVATE_INTEGRATION_TOKEN"
    assert keys.read_name("ghl") == "GHL_PRIVATE_INTEGRATION_TOKEN_READ"
    assert set(keys.write_key_names()) == {"INSTANTLY_API_KEY", "GHL_PRIVATE_INTEGRATION_TOKEN"}
    with pytest.raises(KeyError):
        keys.read_key("zoom")


def test_read_key_falls_back_to_the_main_key_when_read_is_unset(main_keys_only, shadow_mode):
    assert keys.read_key("instantly") == I_WRITE
    assert keys.read_key_and_name("ghl") == (G_WRITE, "GHL_PRIVATE_INTEGRATION_TOKEN")
    assert keys.write_key("instantly") == I_WRITE


def test_read_key_prefers_the_read_key_and_write_key_never_uses_it(read_only_keys):
    assert keys.read_key_and_name("instantly") == (I_READ, "INSTANTLY_API_KEY_READ")
    assert keys.write_key("instantly") is None
    assert keys.write_key("ghl") is None


def test_a_blank_read_key_counts_as_unset(main_keys_only, monkeypatch, shadow_mode):
    monkeypatch.setenv("INSTANTLY_API_KEY_READ", "   ")
    assert keys.read_key("instantly") == I_WRITE


def test_neither_key_set_is_none(monkeypatch):
    monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
    monkeypatch.delenv("INSTANTLY_API_KEY_READ", raising=False)
    assert keys.read_key("instantly") is None and keys.write_key("instantly") is None


def test_the_fallback_warns_once_per_process_in_shadow_naming_variables_only(main_keys_only, shadow_mode, caplog):
    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            keys.read_key("instantly")
        keys.read_key("ghl")
    warnings = [r for r in caplog.records if r.name == "shared.keys"]
    assert len(warnings) == 2                                   # one per system, not per call
    assert "INSTANTLY_API_KEY_READ is not set" in warnings[0].getMessage()
    assert I_WRITE not in caplog.text and G_WRITE not in caplog.text


def test_the_fallback_does_not_warn_in_live(main_keys_only, live_mode, caplog):
    with caplog.at_level(logging.DEBUG):
        keys.read_key("instantly")
    assert [r for r in caplog.records if r.name == "shared.keys"] == []


def test_the_live_env_path_is_one_overridable_constant(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert keys.live_env_path() == os.path.join(str(tmp_path), ".advero", "live.env")
    monkeypatch.setattr(keys, "LIVE_ENV_PATH", str(tmp_path / "elsewhere.env"))
    assert keys.live_env_path() == str(tmp_path / "elsewhere.env")


# ------------------------------------------------------------ Instantly
def test_instantly_reads_send_the_read_key(both_keys, tmp_env, shadow_mode):
    client, rec = instantly()
    client.list_campaigns()
    client.list_emails()
    client.get_lead("l1")
    assert rec.bearers() == [I_READ, I_READ, I_READ]


def test_instantly_leads_list_is_a_read_although_it_is_a_post(both_keys, tmp_env, live_mode):
    client, rec = instantly()
    client.list_leads(campaign="c1")
    list(client.iterate("leads/list", body={"limit": 100}))
    assert [r.method for r in rec.requests] == ["POST", "POST"]
    assert rec.bearers() == [I_READ, I_READ]
    assert endpoint_info("POST", "/leads/list")["access"] == "read"
    assert endpoint_info("POST", "leads")["access"] == "write"


def test_instantly_live_writes_send_the_write_key(both_keys, tmp_env, live_mode):
    client, rec = instantly([(200, {"id": "sent"}), (200, {}), (200, {})])
    client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "body", to="lead@x.com")
    client.pause_account("a@b.co")                                # the no-body path
    client.get_campaign("c1")                                     # a read after writes: read key again
    assert rec.bearers() == [I_WRITE, I_WRITE, I_READ]


def test_every_instantly_method_matches_its_endpoint_table_row(both_keys, tmp_env, live_mode):
    """Read vs write is per method: each read method's request is a 'read' row
    sent with the read key, each write method's a 'write' row sent with the
    write key. A method added without a table row fails here."""
    client, rec = instantly()
    reads = [
        lambda: client.list_campaigns(), lambda: client.get_campaign("c"), lambda: client.list_accounts(),
        lambda: client.list_emails(), lambda: client.get_email("e"), lambda: client.list_leads(),
        lambda: client.get_lead("l"), lambda: client.campaign_analytics(ids=["c"]),
        lambda: client.daily_campaign_analytics("c", "2026-09-01", "2026-09-02"),
        lambda: client.warmup_analytics(["a@b.co"]),
        lambda: client.daily_account_analytics(["a@b.co"], "2026-09-01", "2026-09-02"),
        lambda: client.campaign_step_analytics("c"), lambda: client.test_vitals(["a@b.co"]),
        lambda: client.inbox_placement_list(), lambda: client.inbox_placement_stats_by_test(["t"]),
        lambda: client.blocklist_list(), lambda: client.audit_logs_list(), lambda: client.lead_labels_list(),
        lambda: client.webhooks_list(), lambda: client.subsequences_list("c"),
        lambda: client._get("accounts/a%40b.co"),
    ]
    for call in reads:
        call()
    for req in rec.requests:
        info = endpoint_info(req.method, req.url.path[len("/api/v2"):])
        assert info is not None and info["access"] == "read", (req.method, req.url.path)
    assert set(rec.bearers()) == {I_READ}

    rec.requests[:] = []
    writes = [
        lambda: client.reply_to_email("u", "a@b.co", "s", "b", to="l@x.co"),
        lambda: client.update_interest_status("l@x.co", "c", 1), lambda: client.update_lead("l", {"x": 1}),
        lambda: client.update_campaign("c", {"daily_limit": 1}), lambda: client.pause_account("a@b.co"),
        lambda: client.resume_account("a@b.co"), lambda: client.lead_labels_create("L", "positive"),
        lambda: client.webhooks_create({"target_hook_url": "https://x.modal.run/h", "event_type": "reply_received"}),
        lambda: client.webhooks_delete("w1"), lambda: client.subsequences_create({"parent_campaign": "c"}),
        lambda: client.blocklist_create("a@b.co"), lambda: client.create_lead("c", "a@b.co"),
        lambda: client.inbox_placement_create({"name": "t"}), lambda: client.move_to_subsequence("l", "s"),
    ]
    for call in writes:
        call()
    for req in rec.requests:
        info = endpoint_info(req.method, req.url.path[len("/api/v2"):])
        assert info is not None and info["access"] == "write", (req.method, req.url.path)
    assert len(rec.requests) == len(writes) and set(rec.bearers()) == {I_WRITE}


def test_instantly_with_only_the_read_key_reads_and_shadow_writes_fine(read_only_keys, tmp_env, shadow_mode):
    client, rec = instantly()
    client.list_campaigns()
    res = client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "body", to="lead@x.com")
    assert res["shadow"] is True
    assert rec.bearers() == [I_READ]                          # the shadow write sent nothing


def test_instantly_live_write_with_only_the_read_key_raises_and_sends_nothing(read_only_keys, tmp_env, live_mode):
    import csv

    client, rec = instantly()
    with pytest.raises(InstantlyError) as exc:
        client.update_interest_status("lead@x.com", "c1", 1)
    assert "INSTANTLY_API_KEY is not set" in str(exc.value) and "live.env" in str(exc.value)
    assert rec.requests == []
    with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
        statuses = [r["status"] for r in csv.DictReader(fh) if r["job"] == "instantly.update_interest_status"]
    assert statuses == ["live_write_intent", "live_write_failed"]


def test_instantly_with_no_key_at_all_refuses_to_build(monkeypatch):
    monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
    monkeypatch.delenv("INSTANTLY_API_KEY_READ", raising=False)
    with pytest.raises(InstantlyError) as exc:
        Instantly(transport=httpx.MockTransport(Recorder()))
    assert "INSTANTLY_API_KEY_READ" in str(exc.value)


def test_an_explicit_api_key_still_serves_reads_and_writes(tmp_env, live_mode):
    rec = Recorder()
    client = Instantly(api_key="k-explicit", transport=httpx.MockTransport(rec), sleep=lambda s: None)
    client.list_campaigns()
    client.update_lead("l1", {"x": 1})
    assert rec.bearers() == ["k-explicit", "k-explicit"]


# ------------------------------------------------------------ 403 messages
def test_a_403_on_a_verified_read_names_the_scope(read_only_keys, tmp_env, shadow_mode):
    client, rec = instantly([(403, {"message": "Forbidden"})])
    with pytest.raises(InstantlyScopeError) as exc:
        client.list_emails()
    text = str(exc.value)
    assert "INSTANTLY_API_KEY_READ" in text and "emails:read" in text and "all:read" in text
    assert "read_only_keys.md" in text
    assert len(rec.requests) == 1                             # a 403 is not retried


def test_a_403_on_leads_list_names_leads_read(read_only_keys, tmp_env, shadow_mode):
    client, _ = instantly([(403, {"message": "Forbidden"})])
    with pytest.raises(InstantlyScopeError) as exc:
        client.list_leads(campaign="c1")
    assert "leads:read" in str(exc.value)


def test_a_403_on_an_unverified_read_says_unverified(read_only_keys, tmp_env, shadow_mode):
    client, _ = instantly([(403, {"message": "Forbidden"})])
    with pytest.raises(InstantlyScopeError) as exc:
        client.campaign_analytics(ids=["c1"])
    assert "UNVERIFIED" in str(exc.value) and "all:read" in str(exc.value)


def test_a_401_that_mentions_scope_is_treated_the_same(read_only_keys, tmp_env, shadow_mode):
    client, _ = instantly([(401, {"message": "The API key does not have the required scope"})])
    with pytest.raises(InstantlyScopeError):
        client.list_emails()


def test_a_403_with_the_fallback_main_key_is_a_plain_error(main_keys_only, tmp_env, shadow_mode):
    client, _ = instantly([(403, {"message": "Forbidden"})])
    with pytest.raises(InstantlyError) as exc:
        client.list_emails()
    assert not isinstance(exc.value, InstantlyScopeError) and "403" in str(exc.value)


# ------------------------------------------------------------ GHL
def test_ghl_reads_send_the_read_token_and_contacts_search_is_a_read(both_keys, tmp_env, live_mode):
    client, rec = ghl()
    client.get_contact("c1")
    client.search_contacts("a@b.co")                          # a POST, and a read
    client.search_opportunities(contact_id="c1")
    client.get_free_slots(None, 1, 2)
    client.search_conversations("c1")
    assert rec.requests[1].method == "POST"
    assert set(rec.bearers()) == {G_READ}


def test_ghl_live_writes_send_the_write_token(both_keys, tmp_env, live_mode):
    client, rec = ghl()
    client.add_tags("c1", ["hot"])
    client.update_opportunity_stage("o1", "s1")
    client.get_contact("c1")
    assert rec.bearers() == [G_WRITE, G_WRITE, G_READ]


def test_ghl_live_write_with_only_the_read_token_raises_and_sends_nothing(read_only_keys, tmp_env, live_mode):
    client, rec = ghl()
    assert client.has_token                                   # reads still work
    with pytest.raises(GHLError) as exc:
        client.upsert_contact("a@b.co")
    assert "ghl_token_missing" in str(exc.value) and "live.env" in str(exc.value)
    assert rec.requests == []


def test_ghl_falls_back_to_the_main_token_for_reads(main_keys_only, tmp_env, shadow_mode):
    client, rec = ghl()
    client.get_contact("c1")
    assert rec.bearers() == [G_WRITE]


def test_ghl_403_on_a_read_names_the_readonly_scope(read_only_keys, tmp_env, shadow_mode):
    client, _ = ghl([(403, {"message": "Forbidden"})])
    with pytest.raises(GHLScopeError) as exc:
        client.search_contacts("a@b.co")
    text = str(exc.value)
    assert "contacts.readonly" in text and "GHL_PRIVATE_INTEGRATION_TOKEN_READ" in text
    client, _ = ghl([(403, {"message": "Forbidden"})])
    with pytest.raises(GHLScopeError) as exc:
        client.get_calendar_events(None, 1, 2)
    assert "calendars/events.readonly" in str(exc.value)
    client, _ = ghl([(403, {"message": "Forbidden"})])
    with pytest.raises(GHLScopeError) as exc:
        client.search_conversations("c1")
    assert "conversations.readonly" in str(exc.value) and "UNVERIFIED" in str(exc.value)


def test_ghl_403_with_the_fallback_main_token_is_a_plain_error(main_keys_only, tmp_env, shadow_mode):
    client, _ = ghl([(403, {"message": "Forbidden"})])
    with pytest.raises(GHLError) as exc:
        client.get_contact("c1")
    assert not isinstance(exc.value, GHLScopeError)


# ------------------------------------------------------------ record_live_write_result
def test_both_clients_record_the_live_write_result_through_settings(both_keys, tmp_env, live_mode, monkeypatch):
    calls = []
    real = settings.record_live_write_result

    def spy(system, action, ok, details=None):
        calls.append((system, action, ok))
        return real(system, action, ok, details)

    monkeypatch.setattr(settings, "record_live_write_result", spy)
    client, _ = instantly([(200, {"id": "x"}), (500, {"message": "boom"})])
    client.update_lead("l1", {"x": 1})
    with pytest.raises(InstantlyError):
        client.update_lead("l2", {"x": 1})
    gclient, _ = ghl([(200, {"ok": True})])
    gclient.add_tags("c1", ["hot"])
    assert calls == [("instantly", "update_lead", True), ("instantly", "update_lead", False),
                     ("ghl", "add_tags", True)]


# ------------------------------------------------------------ the Modal secret
SECRET = "f" * 48
DOTENV = {
    "INSTANTLY_API_KEY": "inst-dotenv-fake-000111",
    "ANTHROPIC_API_KEY": "sk-ant-fake-0123456789",
    "NTFY_TOPIC": "lz-fake-topic-8812",
    "GHL_PRIVATE_INTEGRATION_TOKEN": "pit-dotenv-fake-000222",
    "NTFY_ALLOW_SENSITIVE": "1",
    "REPLY_ENGINE_SECRET": SECRET,
}


class FakeRun(object):
    def __init__(self):
        self.payloads = []

    def __call__(self, cmd, **kwargs):
        with open(cmd[cmd.index("--from-json") + 1], "r", encoding="utf-8") as fh:
            self.payloads.append(json.load(fh))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _write(path, values, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join("%s=%s\n" % (k, v) for k, v in values.items()), encoding="utf-8")
    os.chmod(str(path), mode)
    return str(path)


def _run_secret(tmp_path, environ=None, dotenv=None):
    env_file = _write(tmp_path / "repo" / ".env", DOTENV if dotenv is None else dotenv)
    run = FakeRun()
    code = modal_secret.main(["--mode", "shadow", "--create", "--env-file", env_file], runner=run,
                             confirm=lambda word, prompt: True, env_loader=conftest._real_dotenv_values,
                             environ=environ if environ is not None else {})
    return code, run


def test_the_secret_takes_the_write_keys_from_live_env_in_a_temp_home(tmp_path, tmp_env, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": I_WRITE, "GHL_PRIVATE_INTEGRATION_TOKEN": G_WRITE,
                                           "SOMETHING_ELSE": "not-for-the-secret-123"})
    code, run = _run_secret(tmp_path)
    assert code == 0
    sent = run.payloads[0]
    assert sent["INSTANTLY_API_KEY"] == I_WRITE and sent["GHL_PRIVATE_INTEGRATION_TOKEN"] == G_WRITE
    assert "SOMETHING_ELSE" not in sent
    assert sent["ANTHROPIC_API_KEY"] == DOTENV["ANTHROPIC_API_KEY"]          # everything else still from .env
    out = capsys.readouterr().out
    assert "~/.advero/live.env (required)" in out and "SOMETHING_ELSE" in out
    for value in ALL_FAKE_KEYS + tuple(DOTENV.values()) + ("not-for-the-secret-123",):
        if len(value) >= 4:
            assert value not in out


def test_the_live_env_file_overrides_the_process_env_which_overrides_dotenv(tmp_path, tmp_env, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": I_WRITE})
    code, run = _run_secret(tmp_path, environ={"INSTANTLY_API_KEY": "inst-proc-fake-333",
                                               "GHL_PRIVATE_INTEGRATION_TOKEN": G_WRITE})
    assert code == 0
    sent = run.payloads[0]
    assert sent["INSTANTLY_API_KEY"] == I_WRITE                              # file beats process env
    assert sent["GHL_PRIVATE_INTEGRATION_TOKEN"] == G_WRITE                  # process env beats .env
    out = capsys.readouterr().out
    assert "process env (required)" in out and "differs from ~/.advero/live.env" in out
    assert "inst-proc-fake-333" not in out


def test_without_live_env_the_dotenv_keys_still_work_with_a_move_note(tmp_path, tmp_env, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    code, run = _run_secret(tmp_path)
    assert code == 0
    assert run.payloads[0]["INSTANTLY_API_KEY"] == DOTENV["INSTANTLY_API_KEY"]
    assert "still in the repo .env" in capsys.readouterr().out


def test_a_write_key_missing_everywhere_still_refuses(tmp_path, tmp_env, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    dotenv = dict(DOTENV)
    dotenv.pop("GHL_PRIVATE_INTEGRATION_TOKEN")
    code, run = _run_secret(tmp_path, dotenv=dotenv)
    assert code == 1 and run.payloads == []
    out = capsys.readouterr().out
    assert "GHL_PRIVATE_INTEGRATION_TOKEN" in out and "~/.advero/live.env" in out


def test_a_placeholder_in_live_env_still_refuses(tmp_path, tmp_env, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": "<paste your key>"})
    code, run = _run_secret(tmp_path)
    assert code == 1 and run.payloads == []


def test_a_group_readable_live_env_gets_a_chmod_note(tmp_path, tmp_env, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": I_WRITE}, mode=0o644)
    code, _ = _run_secret(tmp_path)
    assert code == 0 and "chmod 600" in capsys.readouterr().out


def test_a_test_session_never_reads_live_env_in_the_real_home(monkeypatch):
    """Existing deploy tests run with the real HOME; they must not open
    Lorenzo's real write keys. Nothing is created or opened here."""
    real = os.path.join(modal_secret._real_home(), ".advero", "live.env")
    opened = []
    values, notes = modal_secret.read_live_env(real, loader=lambda p: opened.append(p) or {})
    assert values == {} and opened == [] and "not read" in notes[0]


def test_the_process_env_is_not_consulted_by_default_under_tests(tmp_path, tmp_env, monkeypatch):
    """conftest forces INSTANTLY_API_KEY=test-key-not-real into os.environ;
    it must not replace the .env value in a test that did not ask for it."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    env_file = _write(tmp_path / "repo" / ".env", DOTENV)
    run = FakeRun()
    assert modal_secret.main(["--mode", "shadow", "--create", "--env-file", env_file], runner=run,
                             confirm=lambda w, p: True, env_loader=conftest._real_dotenv_values) == 0
    assert run.payloads[0]["INSTANTLY_API_KEY"] == DOTENV["INSTANTLY_API_KEY"]


def test_load_env_reads_only_the_two_repo_env_files():
    from shared.paths import ENV_PATHS

    assert all(os.path.basename(str(p)) == ".env" for p in ENV_PATHS)
    assert not any(".advero" in str(p) for p in ENV_PATHS)


# ------------------------------------------------------------ no key value is ever logged
def test_no_key_value_reaches_any_log_message_or_error(tmp_path, tmp_env, monkeypatch, caplog, capsys):
    monkeypatch.setenv("INSTANTLY_API_KEY", I_WRITE)
    monkeypatch.setenv("GHL_PRIVATE_INTEGRATION_TOKEN", G_WRITE)
    monkeypatch.delenv("INSTANTLY_API_KEY_READ", raising=False)
    monkeypatch.delenv("GHL_PRIVATE_INTEGRATION_TOKEN_READ", raising=False)
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    keys._reset_warnings()
    errors = []
    with caplog.at_level(logging.DEBUG):
        # fallback warnings, shadow writes, reads
        client, _ = instantly([(200, {"items": []}), (403, {"message": "no"})])
        client.list_campaigns()
        try:
            client.list_emails()
        except InstantlyError as exc:
            errors.append(str(exc))
        client.reply_to_email("u", "a@b.co", "s", "b", to="l@x.co")
        gclient, _ = ghl()
        gclient.get_contact("c1")
        gclient.add_tags("c1", ["x"])
        # read-only keys: scope errors
        monkeypatch.setenv("INSTANTLY_API_KEY_READ", I_READ)
        monkeypatch.setenv("GHL_PRIVATE_INTEGRATION_TOKEN_READ", G_READ)
        client, _ = instantly([(403, {"message": "Forbidden"})])
        try:
            client.list_leads()
        except InstantlyError as exc:
            errors.append(str(exc))
        gclient, _ = ghl([(403, {"message": "Forbidden"})])
        try:
            gclient.search_contacts("a@b.co")
        except GHLError as exc:
            errors.append(str(exc))
        # live writes: ok, failed, and missing write key
        monkeypatch.setenv("MODE", "live")
        monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
        client, _ = instantly([(200, {"id": "x"}), (500, {"message": "boom"})])
        client.update_lead("l1", {"x": 1})
        try:
            client.update_lead("l2", {"x": 1})
        except InstantlyError as exc:
            errors.append(str(exc))
        monkeypatch.delenv("INSTANTLY_API_KEY")
        monkeypatch.delenv("GHL_PRIVATE_INTEGRATION_TOKEN")
        client, _ = instantly()
        try:
            client.update_lead("l3", {"x": 1})
        except InstantlyError as exc:
            errors.append(str(exc))
        gclient, _ = ghl()
        try:
            gclient.add_tags("c1", ["x"])
        except GHLError as exc:
            errors.append(str(exc))
        # the Modal secret plan
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": I_WRITE, "GHL_PRIVATE_INTEGRATION_TOKEN": G_WRITE})
        env_file = _write(tmp_path / "repo" / ".env", DOTENV)
        modal_secret.main(["--mode", "shadow", "--env-file", env_file], env_loader=conftest._real_dotenv_values,
                          environ={"INSTANTLY_API_KEY": I_READ})
    assert len(errors) == 6
    assert "scope" in errors[1] and "scope" in errors[2]
    printed = capsys.readouterr()
    written = ""
    for path in (job_log.job_log_path(), os.path.join(str(tmp_env), "shadow_log.jsonl")):
        if os.path.exists(str(path)):
            with open(str(path), "r", encoding="utf-8") as fh:
                written += fh.read()
    haystack = caplog.text + "\n".join(errors) + printed.out + printed.err + written
    assert "reads are using the write-capable" in caplog.text     # the logs did run
    for value in ALL_FAKE_KEYS:
        assert value not in haystack, "a key value leaked"


# ------------------------------------------------------------ round 2: source labels in real runs
def _as_load_env_leaves_it(dotenv, **shell):
    """os.environ after shared.settings.load_env(): every .env value copied in
    (override=False, so a value the shell exported first wins)."""
    environ = dict(dotenv)
    environ.update(shell)
    return environ


def test_keys_only_in_dotenv_are_labelled_dotenv_with_the_move_note(tmp_path, tmp_env, monkeypatch, capsys):
    """The reviewer's first case: load_env had already copied .env into the
    process env, so the old code called these 'process env' and never said
    to move them."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    code, run = _run_secret(tmp_path, environ=_as_load_env_leaves_it(DOTENV))
    assert code == 0
    assert run.payloads[0]["INSTANTLY_API_KEY"] == DOTENV["INSTANTLY_API_KEY"]
    out = capsys.readouterr().out
    assert "process env (required)" not in out
    assert out.count(".env (required)") >= 2
    assert "INSTANTLY_API_KEY is still in the repo .env" in out
    assert "GHL_PRIVATE_INTEGRATION_TOKEN is still in the repo .env" in out


def test_a_copy_left_in_dotenv_is_not_a_clean_migration(tmp_path, tmp_env, monkeypatch, capsys):
    """Second case: copied to live.env, never deleted from .env."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": DOTENV["INSTANTLY_API_KEY"],
                                           "GHL_PRIVATE_INTEGRATION_TOKEN": DOTENV["GHL_PRIVATE_INTEGRATION_TOKEN"]})
    code, _ = _run_secret(tmp_path, environ=_as_load_env_leaves_it(DOTENV))
    assert code == 0
    out = capsys.readouterr().out
    assert "~/.advero/live.env (required)" in out
    assert "INSTANTLY_API_KEY is still in the repo .env" in out
    assert "differs" not in out


def test_a_stale_dotenv_value_is_reported_as_dotenv_not_as_the_process(tmp_path, tmp_env, monkeypatch, capsys):
    """Third case: live.env holds the new key, .env the old one, and load_env
    copied the old one into the process env."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": I_WRITE, "GHL_PRIVATE_INTEGRATION_TOKEN": G_WRITE})
    code, run = _run_secret(tmp_path, environ=_as_load_env_leaves_it(DOTENV))
    assert code == 0 and run.payloads[0]["INSTANTLY_API_KEY"] == I_WRITE
    out = capsys.readouterr().out
    assert "INSTANTLY_API_KEY in the repo .env differs from ~/.advero/live.env" in out
    assert "process environment" not in out
    assert "INSTANTLY_API_KEY is still in the repo .env" in out


def test_a_value_the_shell_exported_is_labelled_process_env(tmp_path, tmp_env, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    environ = _as_load_env_leaves_it(DOTENV, INSTANTLY_API_KEY=I_WRITE)   # sourced live.env, file not there
    code, run = _run_secret(tmp_path, environ=environ)
    assert code == 0 and run.payloads[0]["INSTANTLY_API_KEY"] == I_WRITE
    out = capsys.readouterr().out
    assert "process env (required)" in out
    assert "INSTANTLY_API_KEY is still in the repo .env" in out        # .env still holds one
    assert I_WRITE not in out


def test_a_refusal_still_prints_the_live_env_notes_and_names_all_three_sources(tmp_path, tmp_env, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write(home / ".advero" / "live.env", {"INSTANTLY_API_KEY": I_WRITE, "GHL_PRIVATE_INTEGRATON_TOKEN": G_WRITE},
           mode=0o644)                                                 # misspelled name, loose mode
    dotenv = dict(DOTENV)
    dotenv.pop("GHL_PRIVATE_INTEGRATION_TOKEN")
    code, run = _run_secret(tmp_path, dotenv=dotenv)
    assert code == 1 and run.payloads == []
    out = capsys.readouterr().out
    assert "GHL_PRIVATE_INTEGRATON_TOKEN" in out and "ignored" in out
    assert "chmod 600" in out
    assert "missing or blank in all three sources" in out and "the process environment" in out
    assert G_WRITE not in out and I_WRITE not in out


# ------------------------------------------------------------ round 2: the real ~/.advero stays shut
def _stand_in_home(tmp_path):
    """A fake 'real home' with an .advero dir in it. Every symlink test points
    here, never at the real ~/.advero: a link left in pytest's temp root would
    be a predictable alias to the real live.env."""
    home = tmp_path / "stand-in-home"
    (home / ".advero").mkdir(parents=True)
    return home


def test_a_temp_symlink_into_the_advero_dir_is_not_read(tmp_path, monkeypatch):
    home = _stand_in_home(tmp_path)
    monkeypatch.setattr(modal_secret, "_real_home", lambda: str(home))
    link = tmp_path / "elsewhere" / ".advero"
    link.parent.mkdir()
    os.symlink(str(home / ".advero"), str(link))
    try:
        opened = []
        values, notes = modal_secret.read_live_env(str(link / "live.env"), loader=lambda p: opened.append(p) or {})
        assert values == {} and opened == [] and "not read" in notes[0]
    finally:
        os.unlink(str(link))


def test_the_real_advero_path_is_refused_by_the_pure_predicate():
    """The real path is only ever checked, never opened or linked to."""
    real_path = os.path.join(modal_secret._real_home(), ".advero", "live.env")
    assert modal_secret._in_real_home(real_path)
    assert conftest.is_credential_file(real_path)


def test_a_symlinked_advero_dir_is_refused_as_written(monkeypatch):
    """If ~/.advero is a symlink to somewhere outside the home, the resolved
    path escapes; the path as written must still be refused. Pure: realpath is
    faked, nothing is opened."""
    real_path = os.path.join(modal_secret._real_home(), ".advero", "live.env")
    original = os.path.realpath

    def fake_realpath(p, *a, **k):
        if ".advero" in str(p):
            return "/Volumes/elsewhere/live.env"
        return original(p, *a, **k)

    monkeypatch.setattr(os.path, "realpath", fake_realpath)
    opened = []
    values, notes = modal_secret.read_live_env(real_path, loader=lambda p: opened.append(p) or {})
    assert values == {} and opened == [] and "not read" in notes[0]


def test_conftest_refuses_the_advero_dir_as_written_and_through_a_link(tmp_path, monkeypatch):
    """conftest's ~/.advero check, run against a stand-in dir so no link or
    open ever touches the real one. Predicate only: the hook that turns this
    predicate into a PermissionError (and a count) is exercised by
    shared/tests/test_isolation.py, and this test adds nothing to the count."""
    home = _stand_in_home(tmp_path)
    advero = str(home / ".advero")
    monkeypatch.setattr(conftest, "_ADVERO_DIRS", conftest._ADVERO_DIRS + (advero, os.path.realpath(advero)))
    link = tmp_path / "link-advero"
    os.symlink(advero, str(link))
    try:
        assert conftest.is_credential_file(os.path.join(advero, "live.env"))
        assert conftest.is_credential_file(str(link / "live.env"))
        assert not conftest.is_credential_file(str(tmp_path / "other" / "live.env"))
    finally:
        os.unlink(str(link))


def test_conftest_leaves_a_temp_home_advero_dir_readable(tmp_path):
    own = tmp_path / ".advero" / "live.env"
    own.parent.mkdir()
    own.write_text("INSTANTLY_API_KEY=fake\n", encoding="utf-8")
    assert not conftest.is_credential_file(str(own))
    assert own.read_text(encoding="utf-8") == "INSTANTLY_API_KEY=fake\n"


def test_the_read_key_names_are_classified_for_modal():
    from services.reply_engine import modal_app

    for name in keys.read_key_names():
        assert name in modal_app.ENV_NOT_IN_SECRET and name not in modal_app.SECRET_KEYS
