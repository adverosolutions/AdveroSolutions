"""The test suite cannot reach live systems (SAF-2, 2026-09-22 review).

The review simulated the planned go-live step (GHL_PRIVATE_INTEGRATION_TOKEN
and JOB_LOG_SHEET_ID added to .env) with fake values: 137 tests then made
1,352 outbound attempts, mostly Google sign-ins with the real service-account
key, because importing shared ran load_env() and put everything back that
conftest had popped. These tests pin every lock conftest.py now applies.

None of them opens a socket to anything but loopback, and none reads a real
.env: the dotenv files here are temp files with fake values.
"""
import os
import socket
import threading
import types

import pytest

import conftest
from shared import job_log, settings
from shared.paths import BASE_DIR, ENV_PATHS, ROOT_DIR

FAKE_ENV = {
    "GHL_PRIVATE_INTEGRATION_TOKEN": "fake-ghl-token-not-real",
    "JOB_LOG_SHEET_ID": "fake-sheet-id-not-real",
    "ANTHROPIC_API_KEY": "sk-ant-fake-not-real",
    "NTFY_TOKEN": "tk_fake_not_real",
}


def _write_fake_dotenv(tmp_path):
    creds = tmp_path / "fake_service_account.json"
    creds.write_text('{"type": "service_account", "client_email": "x@fake.iam", '
                     '"private_key": "-----BEGIN FAKE-----"}', encoding="utf-8")
    values = dict(FAKE_ENV)
    values["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds)
    values["GOOGLE_CREDENTIALS_JSON"] = str(creds)
    # Not named ".env": the conftest audit hook refuses the real ones by path,
    # and this file must be readable for the control half of the test.
    path = tmp_path / "golive.env"
    path.write_text("".join("%s=%s\n" % kv for kv in values.items()), encoding="utf-8")
    return path, values


# ------------------------------------------------------------- load_env()
def test_load_env_imports_nothing_under_pytest(tmp_path, monkeypatch):
    path, values = _write_fake_dotenv(tmp_path)
    for key in values:
        monkeypatch.delenv(key, raising=False)

    assert settings.running_under_pytest() is True
    assert settings.load_env([path]) == []
    for key in values:
        assert key not in os.environ, "%s leaked out of a dotenv file inside pytest" % key

    # Control: the same file, with the test-session check switched off and the
    # real python-dotenv restored (conftest makes it a no-op), DOES load.
    # Without this half the assertion above could pass on a broken file.
    monkeypatch.setattr(settings, "running_under_pytest", lambda: False)
    monkeypatch.setattr(settings, "load_dotenv", conftest._real_load_dotenv)
    try:
        assert settings.load_env([path]) == [str(path)]
        for key, value in values.items():
            assert os.environ.get(key) == value, key
    finally:
        for key in values:
            os.environ.pop(key, None)


def test_load_env_with_the_real_files_is_inert_and_never_opens_them():
    before = dict(os.environ)
    opens = len(conftest.credential_file_opens)
    assert settings.load_env() == []
    assert dict(os.environ) == before
    assert len(conftest.credential_file_opens) == opens, "load_env() tried to open a real .env"


def test_importing_shared_put_nothing_back():
    """conftest scrubs the environment, imports shared (which calls
    load_env() against the REAL .env files) and scrubs again, recording what
    reappeared. With the real files on disk that list has to be empty."""
    assert conftest.leaked_after_import == []


# ------------------------------------------------------ the process environment
def test_the_environment_is_an_allowlist_so_new_keys_are_removed_too():
    env = {
        "PATH": "/usr/bin", "HOME": "/Users/x", "LC_ALL": "C", "PYTHONPATH": "/x",
        "GHL_PRIVATE_INTEGRATION_TOKEN": "fake", "JOB_LOG_SHEET_ID": "fake",
        "SOME_SERVICE_ADDED_NEXT_YEAR": "fake", "GMAIL_APP_PASS": "fake",
    }
    removed = conftest.scrub_environment(env)
    assert sorted(env) == ["HOME", "LC_ALL", "PATH", "PYTHONPATH"]
    assert "SOME_SERVICE_ADDED_NEXT_YEAR" in removed and "GMAIL_APP_PASS" in removed


@pytest.mark.parametrize("key", [
    "GHL_PRIVATE_INTEGRATION_TOKEN", "JOB_LOG_SHEET_ID", "ANTHROPIC_API_KEY", "NTFY_TOKEN",
    "NTFY_TOPIC", "GMAIL_APP_PASSWORD", "GMAIL_SENDER_EMAIL", "NOTIFICATION_EMAIL",
    "PERPLEXITY_API_KEY", "MILLIONVERIFIER_API_KEY", "APIFY_API_TOKEN", "OPENAI_API_KEY",
    "GOOGLE_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS", "SUPABASE_SERVICE_KEY",
    "GITHUB_TOKEN", "ALLOW_LIVE_WRITES",
])
def test_no_credential_is_in_the_test_process(key):
    assert not conftest.env_key_allowed(key)
    assert key not in os.environ


def test_the_keys_tests_need_are_forced_fakes():
    """Overwritten, not setdefault: a real INSTANTLY_API_KEY in the shell
    used to win."""
    assert conftest.FORCED_ENV["INSTANTLY_API_KEY"] == "test-key-not-real"
    assert conftest.FORCED_ENV["MODE"] == "shadow" and conftest.FORCED_ENV["LLM_FAKE"] == "1"
    assert os.environ["INSTANTLY_API_KEY"] == "test-key-not-real"


# ------------------------------------------------------- credential files
@pytest.mark.parametrize("path", [
    BASE_DIR / "credentials.json", ROOT_DIR / "credentials.json",
    BASE_DIR / "token.json", ROOT_DIR / "token.json",
] + list(ENV_PATHS))
def test_credential_files_are_hidden(path):
    assert conftest.is_credential_file(path)
    assert conftest.is_credential_file(str(path))
    before = len(conftest.credential_file_opens)
    try:
        # The audit hook fires before the OS is asked, so the refusal is the
        # same whether or not the file exists on this machine.
        with pytest.raises(PermissionError):
            open(str(path), "r").close()
        with pytest.raises(PermissionError):
            os.open(str(path), os.O_RDONLY)
        assert len(conftest.credential_file_opens) == before + 2
    finally:
        del conftest.credential_file_opens[before:]


def test_the_block_is_by_path_not_by_name(tmp_path):
    """A test's own fixture called credentials.json stays readable."""
    own = tmp_path / "credentials.json"
    own.write_text("{}", encoding="utf-8")
    assert not conftest.is_credential_file(own)
    assert own.read_text(encoding="utf-8") == "{}"


def test_the_job_log_finds_no_service_account(monkeypatch):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    before = len(conftest.credential_file_opens)
    try:
        assert job_log._service_account_info() is None
    finally:
        del conftest.credential_file_opens[before:]


# ------------------------------------------------------------ the socket guard
def test_the_guard_is_installed():
    assert socket.socket.connect is conftest._guarded_connect
    assert socket.socket.connect_ex is conftest._guarded_connect_ex
    assert socket.getaddrinfo is conftest._guarded_getaddrinfo
    assert socket.gethostbyname is conftest._guarded_gethostbyname


@pytest.mark.parametrize("address,local", [
    (("127.0.0.1", 80), True), (("127.8.9.10", 80), True), (("::1", 80, 0, 0), True),
    (("localhost", 80), True), (("::ffff:127.0.0.1", 80), True), (("0.0.0.0", 80), True),
    (("93.184.216.34", 443), False), (("10.0.0.5", 443), False), (("api.instantly.ai", 443), False),
    (("oauth2.googleapis.com", 443), False), (("2606:4700::1111", 443), False),
])
def test_loopback_classification(address, local):
    assert conftest._is_loopback_address(None, address) is local


class _NeverConnects(object):
    """Stands in for a socket: if the guard ever let a call through to the
    real connect, calling it on this object would raise TypeError, not dial."""
    family = socket.AF_INET


def test_a_non_loopback_connect_is_refused_recorded_and_fails_the_session():
    before = len(conftest.egress_attempts)
    try:
        with pytest.raises(conftest.EgressBlocked):
            conftest._guarded_connect(_NeverConnects(), ("93.184.216.34", 443))
        with pytest.raises(conftest.EgressBlocked):
            conftest._guarded_connect_ex(_NeverConnects(), ("203.0.113.9", 465))
        with pytest.raises(conftest.EgressBlocked):
            conftest._guarded_getaddrinfo("oauth2.googleapis.com", 443)
        with pytest.raises(OSError):  # EgressBlocked is an OSError: httpx sees a ConnectError
            conftest._guarded_gethostbyname("smtp.gmail.com")
        attempts = conftest.egress_attempts[before:]
        assert [kind for kind, _ in attempts] == ["connect", "connect_ex", "getaddrinfo", "gethostbyname"]
        assert "93.184.216.34" in attempts[0][1]

        # The session verdict for exactly these attempts.
        session = types.SimpleNamespace(exitstatus=0, config=None)
        report = conftest.fail_session_on_egress(session, attempts)
        assert session.exitstatus == 1
        assert "4 outbound network attempt(s)" in report
        for target in ("93.184.216.34", "203.0.113.9", "oauth2.googleapis.com", "smtp.gmail.com"):
            assert target in report
    finally:
        # These were deliberate; leaving them would (correctly) fail this run.
        del conftest.egress_attempts[before:]


def test_a_clean_session_is_left_alone():
    session = types.SimpleNamespace(exitstatus=0, config=None)
    assert conftest.fail_session_on_egress(session, []) is None
    assert session.exitstatus == 0


def test_loopback_still_works():
    """The guard must not break local servers (a FastAPI test client, a local
    fake). A real listening socket on 127.0.0.1, and nothing else."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = []
    t = threading.Thread(target=lambda: accepted.append(server.accept()[0]))
    t.start()
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(("127.0.0.1", port))
        t.join(5)
        assert accepted
    finally:
        client.close()
        for s in accepted:
            s.close()
        server.close()


# ------------------------------------------------- child processes (defect 1)
import json
import subprocess
import sys

# The child imports shared WITH the inherited flag, so the module-level
# load_env() in shared.settings reads nothing. Only then, and only for an
# explicit fake file, may it clear the flag: no child this suite starts ever
# runs load_env() against the real files. An audit hook in the child records
# every dotenv-named file it opens, and the child reports which environment
# variable NAMES the import added. Values are never printed.
_CHILD_LOAD_ENV = (
    "import json, os, sys\n"
    "opened = []\n"
    "def _hook(event, args):\n"
    "    if event != 'open' or not args:\n"
    "        return\n"
    "    try:\n"
    "        path = os.fsdecode(os.fspath(args[0]))\n"
    "    except TypeError:\n"
    "        return\n"
    "    name = os.path.basename(path)\n"
    "    if name == '.env' or name.startswith('.env.'):\n"
    "        opened.append(path)\n"
    "sys.addaudithook(_hook)\n"
    "fake, flag_after = sys.argv[1], sys.argv[2]\n"
    "flag_at_import = os.environ.get('ADVERO_TEST_SESSION')\n"
    "before = set(os.environ)\n"
    "from shared import settings\n"
    "added = sorted(set(os.environ) - before)\n"
    "if flag_after != '1':\n"
    "    if not fake:\n"
    "        sys.exit('refusing to clear the flag for the real ENV_PATHS')\n"
    "    os.environ['ADVERO_TEST_SESSION'] = flag_after\n"
    "loaded = settings.load_env([fake] if fake else None)\n"
    "print('@@' + json.dumps({'loaded': loaded, 'pytest': 'pytest' in sys.modules,\n"
    "                         'flag_at_import': flag_at_import, 'added_by_import': added,\n"
    "                         'dotenv_opened': opened}))\n"
)


def _child_env(**extra):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)   # like the documented `python3 jobs/x.py` command
    env.update(extra)
    return env


CHILD_TIMEOUT_SECONDS = 60  # a child that hangs fails its test; it cannot hang the suite


def _run_child(code, *args, **env_extra):
    # Output goes to files, not pipes: a grandchild that inherited a pipe (a
    # multiprocessing worker a broken guard let through) would hold it open and
    # make run() wait for the timeout even after the child itself had exited.
    import tempfile

    with tempfile.TemporaryFile() as out_fh, tempfile.TemporaryFile() as err_fh:
        proc = subprocess.run([sys.executable, "-c", code] + list(args), cwd=str(BASE_DIR),
                              env=_child_env(**env_extra), stdout=out_fh, stderr=err_fh,
                              timeout=CHILD_TIMEOUT_SECONDS)
        out_fh.seek(0)
        err_fh.seek(0)
        stdout, stderr = out_fh.read(), err_fh.read()
    assert proc.returncode == 0, stderr.decode("utf-8", "replace")[-500:]
    lines = [l for l in stdout.decode("utf-8").splitlines() if l.startswith("@@")]
    assert len(lines) == 1, "expected one report line, got %d (a forked copy kept running?)" % len(lines)
    return json.loads(lines[0][2:])


def test_the_session_flag_is_set_and_listed_as_test_only():
    from services.reply_engine import modal_app

    assert os.environ[settings.TEST_SESSION_ENV] == "1"
    assert settings.TEST_SESSION_ENV in modal_app.ENV_NOT_IN_SECRET
    assert settings.TEST_SESSION_ENV not in modal_app.SECRET_KEYS


def _clean_child(out):
    """Every child: flag inherited at import, nothing added, no dotenv opened."""
    assert out["pytest"] is False
    assert out["flag_at_import"] == "1"
    assert out["added_by_import"] == [], out["added_by_import"]
    assert out["dotenv_opened"] == [], out["dotenv_opened"]


def test_a_child_process_of_the_suite_loads_no_dotenv(tmp_path):
    """A child is not a pytest process; before the flag, `python3 jobs/x.py
    --help` from the suite loaded every key in the real .env files."""
    path, values = _write_fake_dotenv(tmp_path)
    out = _run_child(_CHILD_LOAD_ENV, "", "1")               # the real ENV_PATHS
    _clean_child(out)
    assert out["loaded"] == []
    out = _run_child(_CHILD_LOAD_ENV, str(path), "1")        # a fake file, flag inherited
    _clean_child(out)
    assert out["loaded"] == []
    # Control: the flag cleared INSIDE the child, after `from shared import
    # settings` has run its module-level load_env() with the flag still set,
    # and only for the fake file. It loads, so the flag, not a broken file, is
    # what stopped the two calls above; and the import still opened nothing.
    out = _run_child(_CHILD_LOAD_ENV, str(path), "0")
    _clean_child(out)
    assert out["loaded"] == [str(path)]


# ------------------------------------------------ the spawn check (round 3)
def _without_flag():
    env = dict(os.environ)
    env.pop(conftest.TEST_SESSION_FLAG, None)
    return env


@pytest.mark.parametrize("make_env", [
    _without_flag,
    lambda: dict(os.environ, ADVERO_TEST_SESSION="0"),
    lambda: {"PATH": os.environ.get("PATH", "")},        # built from scratch
], ids=["flag-removed", "flag-zero", "fresh-env"])
def test_a_child_without_the_flag_is_refused(make_env):
    before = len(conftest.refused_spawns)
    try:
        with pytest.raises(conftest.ChildWithoutTestFlag):
            subprocess.run([sys.executable, "-c", "pass"], env=make_env())
        assert conftest.refused_spawns[before:] and conftest.refused_spawns[-1][0] == "subprocess.Popen"
    finally:
        del conftest.refused_spawns[before:]


def test_a_child_is_refused_when_the_session_itself_lost_the_flag(monkeypatch):
    monkeypatch.delenv(conftest.TEST_SESSION_FLAG)
    before = len(conftest.refused_spawns)
    try:
        with pytest.raises(conftest.ChildWithoutTestFlag):
            subprocess.run([sys.executable, "-c", "pass"])         # inherits the flagless env
        with pytest.raises(conftest.ChildWithoutTestFlag):
            os.system("true")
    finally:
        del conftest.refused_spawns[before:]


def test_exec_and_posix_spawn_are_checked_too():
    """Through sys.audit, the same event the C functions raise first: a broken
    check must not get to replace this pytest process with os.execve."""
    before = len(conftest.refused_spawns)
    try:
        flagless = _without_flag()
        for event, args in [("os.exec", ("/bin/true", ["true"], flagless)),
                            ("os.posix_spawn", ("/bin/true", ["true"], flagless)),
                            ("os.spawn", (0, "/bin/true", ["true"], flagless))]:
            with pytest.raises(conftest.ChildWithoutTestFlag):
                sys.audit(event, *args)
        # inheriting, or passing the flag explicitly, is allowed
        sys.audit("os.exec", "/bin/true", ["true"], None)
        sys.audit("os.posix_spawn", "/bin/true", ["true"], dict(os.environ))
        sys.audit("os.posix_spawn", "/bin/true", ["true"], {b"ADVERO_TEST_SESSION": b"1"})
        assert [e for e, _ in conftest.refused_spawns[before:]] == ["os.exec", "os.posix_spawn", "os.spawn"]
    finally:
        del conftest.refused_spawns[before:]


def test_a_child_that_inherits_the_environment_runs():
    proc = subprocess.run([sys.executable, "-c", "import os; print(os.environ['ADVERO_TEST_SESSION'])"],
                          stdout=subprocess.PIPE)
    assert proc.returncode == 0 and proc.stdout.strip() == b"1"


# ------------------------------------------------ the session temp dir
_CHILD_SESSION_TMP = (
    "import json, os, conftest\n"
    "print('@@' + json.dumps({'tmp': conftest._SESSION_TMP, 'exists': os.path.isdir(conftest._SESSION_TMP)}))\n"
)


def test_the_session_temp_dir_is_removed_when_its_process_exits():
    """Every run used to leave an advero-tests-* folder in $TMPDIR."""
    out = _run_child(_CHILD_SESSION_TMP, PYTHONPATH=str(BASE_DIR))
    assert out["exists"] is True
    assert os.path.basename(out["tmp"]).startswith("advero-tests-")
    assert not os.path.exists(out["tmp"]), "the child's session temp dir outlived it"
    assert os.path.isdir(conftest._SESSION_TMP), "this session's own dir is still in use"


# --------------------------------------------------- modal's token (defect 2)
def test_modal_reads_no_user_config():
    assert os.environ["MODAL_CONFIG_PATH"].startswith(conftest._SESSION_TMP)
    assert not os.path.exists(os.environ["MODAL_CONFIG_PATH"])
    assert conftest.is_credential_file(os.path.join(os.path.expanduser("~"), ".modal.toml"))
    before = len(conftest.credential_file_opens)
    import modal.config

    assert modal.config.user_config_path == os.environ["MODAL_CONFIG_PATH"]
    assert modal.config._user_config == {}
    assert len(conftest.credential_file_opens) == before


# ------------------------------------------- every dotenv file (defect 3)
@pytest.mark.parametrize("relpath,hidden", [
    ("Agentic Worklfows/execution/.env", True),
    ("Agentic Worklfows/.env", True),
    (".env", True),
    ("Coding/lead-scrape-2026/.env", True),
    ("Agentic Worklfows/execution/.env.local", True),
    ("Agentic Worklfows/.env.production", True),
    (".env.example", False),
    ("Agentic Worklfows/execution/notenv.txt", False),
])
def test_every_dotenv_under_the_business_folder_is_hidden(relpath, hidden):
    path = os.path.join(str(ROOT_DIR), relpath)
    assert conftest.is_credential_file(path) is hidden
    if not hidden:
        return
    before = len(conftest.credential_file_opens)
    try:
        with pytest.raises(PermissionError):
            open(path, "r").close()
    finally:
        del conftest.credential_file_opens[before:]


def test_a_dotenv_outside_the_business_folder_is_not_blocked(tmp_path):
    own = tmp_path / ".env"
    own.write_text("A=1\n", encoding="utf-8")
    assert not conftest.is_credential_file(own)
    assert own.read_text(encoding="utf-8") == "A=1\n"


def test_python_dotenv_itself_is_inert(tmp_path, monkeypatch):
    """execution/ modules call load_dotenv() at import, bypassing
    shared.settings; the reviewer loaded execution/.env via `import
    ntfy_notifier`. Both entry points, and the name as a fresh import sees it."""
    import dotenv
    import dotenv.main

    path, values = _write_fake_dotenv(tmp_path)
    for key in values:
        monkeypatch.delenv(key, raising=False)
    calls = len(conftest.dotenv_calls)

    assert dotenv.load_dotenv(str(path)) is False
    assert dotenv.main.load_dotenv(dotenv_path=str(path), override=True) is False
    assert dotenv.dotenv_values(str(path)) == {}
    assert dotenv.main.dotenv_values(str(path)) == {}
    namespace = {}
    exec("from dotenv import load_dotenv\nload_dotenv(%r, override=True)" % str(path), namespace)
    for key in values:
        assert key not in os.environ, key
    assert len(conftest.dotenv_calls) == calls + 5
    assert settings.load_dotenv is conftest._inert_load_dotenv

    # the real parser still works on the same file, so the no-ops are the reason
    assert conftest._real_dotenv_values(str(path))["JOB_LOG_SHEET_ID"] == values["JOB_LOG_SHEET_ID"]


# ----------------------------------------- the socket audit layer (defect 4)
def test_the_socket_audit_hook_refuses_every_egress_event():
    """sys.audit raises the same event the C socket module raises before the
    syscall, so this exercises the hook without sending a packet."""
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    before = len(conftest.egress_attempts)
    try:
        cases = [
            ("socket.connect", (udp, ("203.0.113.9", 443))),
            ("socket.sendto", (udp, ("203.0.113.9", 53))),
            ("socket.sendmsg", (udp, ("2001:db8::1", 53, 0, 0))),
            ("socket.getaddrinfo", ("oauth2.googleapis.com", 443, 0, 0, 0)),
            ("socket.gethostbyname", ("smtp.gmail.com",)),
            ("socket.gethostbyaddr", ("8.8.8.8",)),
            ("socket.getnameinfo", (("93.184.216.34", 443),)),
        ]
        for event, args in cases:
            with pytest.raises(conftest.EgressBlocked):
                sys.audit(event, *args)
        assert [kind for kind, _ in conftest.egress_attempts[before:]] == [e for e, _ in cases]
    finally:
        del conftest.egress_attempts[before:]
        udp.close()


def test_the_socket_audit_hook_allows_loopback_and_unix_sockets():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    unix = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    before = len(conftest.egress_attempts)
    try:
        sys.audit("socket.sendto", udp, ("127.0.0.1", 9))
        sys.audit("socket.sendmsg", udp, None)            # connected socket
        sys.audit("socket.connect", unix, "/tmp/some.sock")
        sys.audit("socket.getaddrinfo", "localhost", 80, 0, 0, 0)
        sys.audit("socket.gethostbyaddr", "127.0.0.1")
        sys.audit("socket.getnameinfo", ("::1", 80))
        assert conftest.egress_attempts[before:] == []
    finally:
        udp.close()
        unix.close()


def test_a_real_c_level_udp_send_goes_through_the_audit_hook():
    """Proves the hook sees calls that skip the Python layer: a real UDP
    datagram through _socket.socket.sendto, to a loopback listener."""
    import _socket

    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.bind(("127.0.0.1", 0))
        rx.settimeout(5)
        seen = len(conftest.socket_events_seen)
        _socket.socket.sendto(tx, b"ping", rx.getsockname())
        assert rx.recv(16) == b"ping"
        assert "socket.sendto" in conftest.socket_events_seen[seen:]
    finally:
        rx.close()
        tx.close()


_CHILD_RELOAD = (
    "import importlib, json, socket, sys\n"
    "import conftest\n"
    "importlib.reload(socket)\n"
    "out = {'layer1_gone': socket.socket.connect is not conftest._guarded_connect}\n"
    "for event, args in [('socket.connect', (socket.socket(), ('203.0.113.9', 443))),\n"
    "                    ('socket.sendto', (socket.socket(socket.AF_INET, socket.SOCK_DGRAM), ('203.0.113.9', 53))),\n"
    "                    ('socket.getaddrinfo', ('example.com', 443, 0, 0, 0))]:\n"
    "    try:\n"
    "        sys.audit(event, *args)\n"
    "        out[event] = 'allowed'\n"
    "    except conftest.EgressBlocked:\n"
    "        out[event] = 'blocked'\n"
    "out['recorded'] = len(conftest.egress_attempts)\n"
    "print('@@' + json.dumps(out))\n"
)


def test_reloading_socket_does_not_remove_the_guard():
    """importlib.reload(socket) wipes the Python-level patches. Run in a child
    so this session's socket module is left alone; the child imports conftest,
    which installs both layers exactly as a session does."""
    out = _run_child(_CHILD_RELOAD, PYTHONPATH=str(BASE_DIR))
    assert out == {"layer1_gone": True, "socket.connect": "blocked", "socket.sendto": "blocked",
                   "socket.getaddrinfo": "blocked", "recorded": 3}


# -------------------------------------- the session verdict, end to end (defect 7)
_INNER_TESTS = {
    "clean": (
        "import os, conftest\n"
        "def test_ok():\n"
        "    assert os.path.isdir(conftest._SESSION_TMP)\n"
        "    with open('session_tmp.txt', 'w') as fh:\n"
        "        fh.write(conftest._SESSION_TMP)\n"),
    # a lookup at import time: no per-test fixture sees it, only the session hook
    "module_level": (
        "import socket\n"
        "try:\n"
        "    socket.getaddrinfo('oauth2.googleapis.com', 443)\n"
        "except OSError:\n"
        "    pass\n"
        "def test_ok():\n"
        "    assert True\n"),
    # a connection the code under test swallows, like notify() does
    "swallowed": (
        "import socket\n"
        "def test_swallows():\n"
        "    try:\n"
        "        socket.create_connection(('203.0.113.9', 9), timeout=0.1)\n"
        "    except OSError:\n"
        "        pass\n"),
}


def _inner_session(tmp_path, name):
    """A real pytest session in a child, with this conftest loaded as a plugin.
    Every egress attempt in it is a numeric or DNS lookup that the child's
    guard refuses before any packet is sent."""
    root = tmp_path / name
    root.mkdir()
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "test_inner.py").write_text(_INNER_TESTS[name], encoding="utf-8")
    env = _child_env(PYTHONPATH=str(BASE_DIR))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "conftest", "-p", "no:cacheprovider",
         "-c", str(root / "pytest.ini"), "--rootdir", str(root), str(root / "test_inner.py")],
        cwd=str(root), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def test_an_inner_session_with_no_egress_passes(tmp_path):
    code, out = _inner_session(tmp_path, "clean")
    assert code == 0, out
    assert "0 non-loopback connection attempt(s)" in out
    inner_tmp = (tmp_path / "clean" / "session_tmp.txt").read_text(encoding="utf-8")
    assert not os.path.exists(inner_tmp), "a pytest session left its advero-tests-* dir behind"


def test_an_inner_session_fails_on_egress_nobody_saw(tmp_path):
    """Fails if pytest_sessionfinish is removed: the only test passes and no
    fixture ran while the lookup happened."""
    code, out = _inner_session(tmp_path, "module_level")
    assert code == 1, out
    assert "1 passed" in out and "EGRESS BLOCKED" in out and "oauth2.googleapis.com" in out


def test_an_inner_session_errors_the_test_that_swallowed_egress(tmp_path):
    """Fails if the per-test fixture is removed: the attempt is pinned on the
    test that made it, not only on the session."""
    code, out = _inner_session(tmp_path, "swallowed")
    assert code == 1, out
    assert "ERROR at teardown of test_swallows" in out and "203.0.113.9" in out


def test_the_sessionfinish_hook_marks_a_recorded_attempt():
    before = len(conftest.egress_attempts)
    conftest.egress_attempts.append(("connect", "('93.184.216.34', 443)"))
    try:
        session = types.SimpleNamespace(exitstatus=0, config=None)
        conftest.pytest_sessionfinish(session, 0)
        assert session.exitstatus == 1
    finally:
        del conftest.egress_attempts[before:]


# ------------------------------ round 4: cleanup is bound to the real path
def test_the_exit_cleanup_is_bound_to_the_path_it_was_registered_with(tmp_path):
    """A test that reassigned conftest._SESSION_TMP used to get THAT directory
    deleted at exit, and the real one left behind."""
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    code = (
        "import json, sys, conftest\n"
        "real = conftest._SESSION_TMP\n"
        "conftest._SESSION_TMP = sys.argv[1]\n"
        "print('@@' + json.dumps({'real': real}))\n"
    )
    out = _run_child(code, str(victim), PYTHONPATH=str(BASE_DIR))
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "keep", "the reassigned path was deleted"
    assert not os.path.exists(out["real"]), "the real session dir was left behind"


def test_the_exit_cleanup_refuses_anything_but_its_own_kind_of_dir(tmp_path):
    import tempfile

    assert conftest.is_session_tmp(conftest._SESSION_TMP)

    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    lookalike = tmp_path / "advero-tests-lookalike"          # right name, wrong parent
    lookalike.mkdir()
    for path in (ordinary, lookalike, str(tmp_path)):
        assert conftest.is_session_tmp(path) is False
        assert conftest._remove_session_tmp(str(path), os.getpid()) is False
        assert os.path.isdir(str(path))

    own = tempfile.mkdtemp(prefix=conftest.SESSION_TMP_PREFIX)
    try:
        assert conftest.is_session_tmp(own)
        assert conftest._remove_session_tmp(own, os.getpid() + 1) is False, "not the owner"
        assert os.path.isdir(own)
        assert conftest._remove_session_tmp(own, os.getpid()) is True
        assert not os.path.exists(own)
    finally:
        if os.path.isdir(own):
            os.rmdir(own)


# ------------------ round 4: multiprocessing, ProcessPoolExecutor, pty.spawn
# Each probe runs in a child that imports conftest (so it has the same
# guards as a session), clears the flag in ITS OWN environment, and tries to
# start a process. The child has a timeout, and any forked copy of it exits
# at once, so a broken check fails the test instead of hanging the suite.
_CHILD_SPAWN_PROBE = (
    "import json, os, sys\n"
    "import conftest\n"
    "PARENT = os.getpid()\n"
    "def _report(out):\n"
    "    if os.getpid() != PARENT:\n"
    "        os._exit(0)   # a forked copy must never carry on running this script\n"
    "    out['refused_spawns'] = [event for event, _ in conftest.refused_spawns]\n"
    "    print('@@' + json.dumps(out))\n"
    "    sys.stdout.flush()\n"
    "    # os._exit skips atexit (a half-started pool must not hang shutdown), so\n"
    "    # remove this child's session temp dir by hand first.\n"
    "    conftest._remove_session_tmp(conftest._SESSION_TMP, PARENT)\n"
    "    os._exit(0)\n"
    "route = sys.argv[1]\n"
    "out = {'route': route}\n"
    "os.environ.pop('ADVERO_TEST_SESSION')\n"
    "try:\n"
    "    if route == 'pool-spawn':\n"
    "        import concurrent.futures, multiprocessing\n"
    "        ex = concurrent.futures.ProcessPoolExecutor(\n"
    "            max_workers=1, mp_context=multiprocessing.get_context('spawn'))\n"
    "        try:\n"
    "            out['result'] = ex.submit(abs, -1).result(timeout=20)\n"
    "        finally:\n"
    "            ex.shutdown(wait=False)\n"
    "    elif route == 'process-forkserver':\n"
    "        import multiprocessing\n"
    "        p = multiprocessing.get_context('forkserver').Process(target=abs, args=(-1,))\n"
    "        p.start()\n"
    "        p.join(20)\n"
    "        out['result'] = p.exitcode\n"
    "    elif route == 'pty':\n"
    "        import pty\n"
    "        out['result'] = pty.spawn(['/usr/bin/true'])\n"
    "    elif route == 'pool-spawn-with-flag':\n"
    "        os.environ['ADVERO_TEST_SESSION'] = '1'\n"
    "        import concurrent.futures, multiprocessing\n"
    "        with concurrent.futures.ProcessPoolExecutor(\n"
    "                max_workers=1, mp_context=multiprocessing.get_context('spawn')) as ex:\n"
    "            out['result'] = ex.submit(abs, -1).result(timeout=20)\n"
    "except conftest.ChildWithoutTestFlag as exc:\n"
    "    out['refused'] = True\n"
    "except Exception as exc:\n"
    "    out['other'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])\n"
    "_report(out)\n"
)


@pytest.mark.parametrize("route,event", [
    ("pool-spawn", "_posixsubprocess.fork_exec"),
    ("process-forkserver", "_posixsubprocess.fork_exec"),
    ("pty", "pty.spawn"),
])
def test_a_flagless_child_is_refused_on_every_route(route, event):
    out = _run_child(_CHILD_SPAWN_PROBE, route, PYTHONPATH=str(BASE_DIR))
    assert out.get("refused") is True, out
    assert "result" not in out, "a process was started: %r" % out
    assert out["refused_spawns"] and out["refused_spawns"][0] == event, out


def test_the_same_pool_runs_when_the_flag_is_kept():
    """Control: the refusal above is the flag, not a broken pool."""
    out = _run_child(_CHILD_SPAWN_PROBE, "pool-spawn-with-flag", PYTHONPATH=str(BASE_DIR))
    assert out.get("result") == 1 and out["refused_spawns"] == [], out


def test_fork_exec_env_check():
    flag = b"ADVERO_TEST_SESSION=1"
    assert conftest.fork_exec_env_has_test_flag([b"PATH=/bin", flag])
    assert conftest.fork_exec_env_has_test_flag(["PATH=/bin", "ADVERO_TEST_SESSION=1"])
    assert not conftest.fork_exec_env_has_test_flag([b"PATH=/bin"])
    assert not conftest.fork_exec_env_has_test_flag([b"ADVERO_TEST_SESSION=0"])
    assert not conftest.fork_exec_env_has_test_flag([b"XADVERO_TEST_SESSION=1"])
    assert conftest.fork_exec_env_has_test_flag(None)      # inherits this session's env
    import _posixsubprocess

    assert _posixsubprocess.fork_exec is conftest._guarded_fork_exec
