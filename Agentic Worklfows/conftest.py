"""Root pytest configuration for Agentic Worklfows.

What this file ENFORCES for the whole session, before any test module imports
``shared`` (each lock is pinned by shared/tests/test_isolation.py):

1. **No outbound network.** Two layers. The Python-level patches refuse a
   non-loopback ``socket.socket.connect`` / ``connect_ex`` and a
   ``socket.getaddrinfo`` / ``gethostbyname`` of any hostname but localhost.
   Behind them an audit hook (which cannot be removed, and survives
   ``importlib.reload(socket)`` and direct ``_socket`` calls) refuses the C
   socket module's ``socket.connect``, ``sendto``, ``sendmsg`` (so UDP too),
   ``getaddrinfo``, ``gethostbyname`` (also raised by ``gethostbyname_ex``),
   ``gethostbyaddr`` and ``getnameinfo`` events for any non-loopback target;
   AF_UNIX is exempt. Each refusal is recorded in ``egress_attempts``; the
   test that caused it errors at teardown and the SESSION FAILS at the end
   with the list, even when the code that tried swallowed the error (notify
   never raises, the job log degrades).
2. **No real credentials.**
   a. ``shared.settings.load_env()`` reads no dotenv file in a test session:
      pytest is loaded, or ADVERO_TEST_SESSION=1 (set below and inherited by
      every child process a test starts, e.g. ``python3 jobs/x.py --help``).
      python-dotenv's own ``load_dotenv`` and ``dotenv_values`` are replaced
      with no-ops too, for the execution/ modules that call them directly.
   b. The process environment is cut down to an allowlist of OS and tooling
      variables (``_ENV_ALLOW``) before anything else runs. Whatever a shell
      exported or ``source .env`` put there is removed, including keys nobody
      has invented yet; ``scrubbed_env_keys`` records the NAMES removed.
   c. An audit hook refuses to open every ``.env`` / ``.env.*`` file under
      AdveroSolutions/ (``.env.example`` excepted), credentials.json and
      token.json beside the repo, the gcloud application-default credentials,
      ``~/.modal.toml``, and any file GOOGLE_APPLICATION_CREDENTIALS /
      GOOGLE_CREDENTIALS_JSON named at session start. The Google loaders in
      shared/job_log.py and services/metrics/sheet.py read credentials.json by
      hard-coded path; they catch the PermissionError and find no service
      account. MODAL_CONFIG_PATH points modal at a file that does not exist,
      so ``import modal`` reads no token (blocking the file alone makes modal
      raise at import).
   d. The few keys tests rely on are then set to fixed fake values
      (overwritten, never setdefault, so a real value cannot win).
3. **Child processes keep the test-session flag.** What a child gets is
   narrow, and the boundary matters: it inherits ONLY the cleaned environment
   (2b, 2d), including ADVERO_TEST_SESSION=1 and MODAL_CONFIG_PATH. It does
   NOT get the socket guard, the credential-file audit hook or the dotenv
   no-ops; those live in this process. The flag is what keeps
   ``shared.settings.load_env()`` from reading the real .env files in the
   child. A process started from THIS process without ADVERO_TEST_SESSION=1
   in its environment is refused with ``ChildWithoutTestFlag``, before any
   fork, on exactly these routes:
     - ``subprocess.Popen`` and so ``run`` / ``call`` / ``check_output``
       (the ``subprocess.Popen`` audit event, and ``_posixsubprocess.fork_exec``
       underneath it);
     - multiprocessing's ``spawn`` and ``forkserver`` start methods, and so
       ``ProcessPoolExecutor`` (they call ``_posixsubprocess.fork_exec``
       directly and raise no subprocess event);
     - ``os.exec*``, ``os.posix_spawn`` / ``posix_spawnp``, ``os.system``
       and ``pty.spawn`` (audit events; pty.spawn's fires before its fork).
   ``os.spawn*`` forks first and execs second, so there the refusal happens
   in the forked child, which exits 127 instead of running the program.
   Plain ``os.fork`` / multiprocessing ``fork`` children are copies of this
   process and keep every guard. A child that inherits the environment
   passes; an explicit ``env=`` without the flag is refused. NOT covered: a
   grandchild whose parent drops the flag itself, e.g. ``env -u
   ADVERO_TEST_SESSION ...`` or ``unset`` in a shell a test starts. Anything
   a child does beyond load_env() (a network call, ``python-dotenv`` on its
   own) is unguarded, so a test that starts one must keep it to things like
   ``--help``.
4. **Shadow defaults.** MODE=shadow, faked LLM, notifications off, and every
   file the library writes (store, job log, shadow log, ntfy topic, llm
   ledger) redirected to a per-session temp directory, removed when the
   process that created it exits.
5. **No SMTP.** On 2026-09-22 a full run sent real email from Lorenzo's Gmail:
   tests that turned NOTIFY on reached the email leg with the app password
   load_env() had loaded. See the "no SMTP" block below.

Why all of it: the 2026-09-22 max-effort review simulated the go-live .env
(GHL token and Job_Log sheet id added) and 137 tests made 1,352 outbound
attempts, mostly Google sign-ins with the real service-account key, while the
old version of this docstring said sockets were blocked. None of these locks is
advisory; each one is a test away from being noticed if it is removed.
"""
import atexit
import ipaddress
import os
import shutil
import socket
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ------------------------------------------------------------ no network
# Installed first, so nothing imported below can open a connection either.
egress_attempts = []  # (kind, target) per refused attempt; read by tests


class EgressBlocked(ConnectionRefusedError):
    """A test tried to reach a non-loopback address."""


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo
_real_gethostbyname = socket.gethostbyname


def _is_loopback_host(host) -> bool:
    if host is None:
        return True  # getaddrinfo(None, port) resolves the local host only
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    h = host.strip().strip("[]").lower().split("%", 1)[0]
    if h in ("", "localhost") or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False  # any other hostname is a DNS lookup, which is egress
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_loopback or ip.is_unspecified


def _is_loopback_address(sock, address) -> bool:
    if getattr(sock, "family", None) == getattr(socket, "AF_UNIX", object()):
        return True
    if isinstance(address, tuple) and address:
        return _is_loopback_host(address[0])
    return False


def _refuse(kind: str, target) -> None:
    egress_attempts.append((kind, repr(target)))
    raise EgressBlocked(
        "conftest blocked %s to %r: tests never leave loopback. Mock the transport "
        "(httpx.MockTransport, a fake client, a monkeypatched seam) instead." % (kind, target))


def _guarded_connect(sock, address):
    if not _is_loopback_address(sock, address):
        _refuse("connect", address)
    return _real_connect(sock, address)


def _guarded_connect_ex(sock, address):
    if not _is_loopback_address(sock, address):
        _refuse("connect_ex", address)
    return _real_connect_ex(sock, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_loopback_host(host):
        _refuse("getaddrinfo", host)
    return _real_getaddrinfo(host, *args, **kwargs)


def _guarded_gethostbyname(host):
    if not _is_loopback_host(host):
        _refuse("gethostbyname", host)
    return _real_gethostbyname(host)


def install_socket_patches(module=None):
    """Layer 1: the Python-level patches. Cheap and they name the call that
    tried, but ``importlib.reload(socket)`` or a direct ``_socket`` call gets
    past them, which is what layer 2 below is for."""
    module = socket if module is None else module
    module.socket.connect = _guarded_connect
    module.socket.connect_ex = _guarded_connect_ex
    module.getaddrinfo = _guarded_getaddrinfo
    module.gethostbyname = _guarded_gethostbyname


install_socket_patches()

# Layer 2: CPython raises an audit event inside the C socket module before
# every connect, sendto, sendmsg and name lookup, whichever Python path led
# there (connect_ex raises socket.connect; gethostbyname_ex raises
# socket.gethostbyname). An audit hook cannot be removed or reloaded away.
_SOCKET_ADDRESS_EVENTS = frozenset(("socket.connect", "socket.sendto", "socket.sendmsg"))
_SOCKET_HOST_EVENTS = frozenset(("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"))
socket_events_seen = []  # every guarded event, allowed or not; tests read it


def _socket_audit_hook(event, args):
    if not event.startswith("socket."):
        return  # the fast path for every other audit event in the session
    if event in _SOCKET_ADDRESS_EVENTS:
        sock = args[0] if args else None
        address = args[1] if len(args) > 1 else None
        socket_events_seen.append(event)
        if event == "socket.sendmsg" and address is None:
            return  # a connected socket; its connect was vetted
        if not _is_loopback_address(sock, address):
            _refuse(event, address)
    elif event in _SOCKET_HOST_EVENTS:
        socket_events_seen.append(event)
        if not _is_loopback_host(args[0] if args else None):
            _refuse(event, args[0] if args else None)
    elif event == "socket.getnameinfo":
        socket_events_seen.append(event)
        sockaddr = args[0] if args else None
        host = sockaddr[0] if isinstance(sockaddr, tuple) and sockaddr else sockaddr
        if not _is_loopback_host(host):
            _refuse(event, sockaddr)


sys.addaudithook(_socket_audit_hook)


def egress_report(attempts=None, scope="test session"):
    """The failure text for a list of attempts, or None when there were none."""
    attempts = egress_attempts if attempts is None else attempts
    if not attempts:
        return None
    lines = ["%d outbound network attempt(s) were blocked during this %s:" % (len(attempts), scope)]
    lines.extend("  %s -> %s" % (kind, target) for kind, target in attempts[:50])
    if len(attempts) > 50:
        lines.append("  ... and %d more" % (len(attempts) - 50))
    lines.append("A test reached for a live system. The session is marked failed even if every test passed.")
    return "\n".join(lines)


def fail_session_on_egress(session, attempts=None):
    """pytest_sessionfinish body: mark the session failed when anything tried
    to leave loopback. Returns the report text, or None."""
    report = egress_report(attempts)
    if report is None:
        return None
    session.exitstatus = 1  # pytest.ExitCode.TESTS_FAILED
    reporter = None
    config = getattr(session, "config", None)
    if config is not None:
        reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "EGRESS BLOCKED", red=True)
        reporter.write_line(report)
    else:
        sys.stderr.write(report + "\n")
    return report


# ------------------------------------------------------ no credential files
def _file_path_or_none(value):
    if value and not value.lstrip().startswith("{") and os.path.isfile(value):
        return value
    return None


_CREDENTIAL_FILES = set()
for _dir in (HERE, os.path.dirname(HERE)):
    for _name in ("credentials.json", "token.json", ".env"):
        _CREDENTIAL_FILES.add(os.path.join(_dir, _name))
_CREDENTIAL_FILES.add(os.path.join(os.path.expanduser("~"), ".config", "gcloud",
                                   "application_default_credentials.json"))
# `import modal` reads the real Modal token from here at import time; the
# MODAL_CONFIG_PATH redirect in FORCED_ENV below keeps modal from trying.
_CREDENTIAL_FILES.add(os.path.join(os.path.expanduser("~"), ".modal.toml"))
for _key in ("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CREDENTIALS_JSON"):
    _path = _file_path_or_none(os.environ.get(_key, ""))
    if _path:
        _CREDENTIAL_FILES.add(_path)
_CREDENTIAL_FILES = frozenset(os.path.realpath(p) for p in _CREDENTIAL_FILES)
_CREDENTIAL_BASENAMES = frozenset(os.path.basename(p) for p in _CREDENTIAL_FILES)
credential_file_opens = []  # paths a test tried to open; read by tests

# Every dotenv file anywhere under AdveroSolutions/, not just the two
# shared.settings reads: execution/.env holds a second Google key, and 39
# execution/ modules load their own .env at import. .env.example carries no
# values and stays readable.
_DOTENV_ROOT = os.path.realpath(os.path.dirname(HERE))


def _is_dotenv_name(name: str) -> bool:
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


# ~/.advero holds the write-capable keys (live.env, runbooks/read_only_keys.md).
# The home comes from the password database, so a test that points HOME at a
# temp dir does not move this. Checked unresolved AND resolved: a symlinked
# ~/.advero, or a temp symlink pointing into it, is refused either way.
def _real_home():
    import pwd

    return pwd.getpwuid(os.getuid()).pw_dir


_ADVERO_DIRS = tuple(sorted(set((os.path.join(os.path.abspath(_real_home()), ".advero"),
                                 os.path.realpath(os.path.join(_real_home(), ".advero"))))))


def _under_advero_dir(text: str) -> bool:
    for candidate in (os.path.abspath(text), os.path.realpath(text)):
        for root in _ADVERO_DIRS:
            if candidate == root or candidate.startswith(root + os.sep):
                return True
    return False


def is_credential_file(path) -> bool:
    try:
        text = os.fsdecode(os.fspath(path))
    except TypeError:
        return False  # a file descriptor, not a path
    if _under_advero_dir(text):
        return True
    name = os.path.basename(text)
    if _is_dotenv_name(name):
        real = os.path.realpath(text)
        return real == _DOTENV_ROOT or real.startswith(_DOTENV_ROOT + os.sep)
    if name not in _CREDENTIAL_BASENAMES:
        return False  # the fast path for every other open in the session
    return os.path.realpath(text) in _CREDENTIAL_FILES


def _credential_audit_hook(event, args):
    if event != "open" or not args:
        return
    if is_credential_file(args[0]):
        credential_file_opens.append(os.fsdecode(os.fspath(args[0])))
        raise PermissionError("conftest hides %s from tests; use a fake credential instead" % (args[0],))


# Audit hooks cannot be removed, which is the point: no test can undo this one.
sys.addaudithook(_credential_audit_hook)

# ------------------------------------------------------ no credentials in env
# An ALLOWLIST, not a list of credentials to strip: a key added to .env next
# month is removed without anyone remembering to update this file.
_ENV_ALLOW = frozenset((
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TEMP", "TMP", "LANG", "LANGUAGE",
    "TERM", "TZ", "PWD", "OLDPWD", "SHLVL", "COLUMNS", "LINES", "NO_COLOR", "FORCE_COLOR",
    "CLICOLOR", "VIRTUAL_ENV", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "WINDIR",
    "USERPROFILE", "__CF_USER_TEXT_ENCODING", "__PYVENV_LAUNCHER__", "_",
))
_ENV_ALLOW_PREFIXES = ("LC_", "PYTHON", "PYTEST_", "COV_CORE_", "COVERAGE_")


def env_key_allowed(name: str) -> bool:
    return name in _ENV_ALLOW or name.startswith(_ENV_ALLOW_PREFIXES)


def scrub_environment(environ=None):
    """Remove every variable outside the allowlist; return the removed NAMES."""
    environ = os.environ if environ is None else environ
    removed = sorted(k for k in list(environ) if not env_key_allowed(k))
    for key in removed:
        environ.pop(key, None)
    return removed


scrubbed_env_keys = scrub_environment()  # names only, never values

SESSION_TMP_PREFIX = "advero-tests-"
_SESSION_TMP = tempfile.mkdtemp(prefix=SESSION_TMP_PREFIX)


def is_session_tmp(path) -> bool:
    """A directory this conftest could have made: ``advero-tests-*`` directly
    inside the system temp directory. Anything else is never deleted."""
    try:
        real = os.path.realpath(os.fspath(path))
    except TypeError:
        return False
    return (os.path.basename(real).startswith(SESSION_TMP_PREFIX)
            and os.path.dirname(real) == os.path.realpath(tempfile.gettempdir()))


def _remove_session_tmp(path, owner_pid) -> bool:
    """Delete ``path`` at exit. Every run used to leave one behind (1,801 of
    them in $TMPDIR by 2026-09-22).

    The path and the owner are bound when this is registered, never read
    from the module global at exit: a test that reassigned
    ``conftest._SESSION_TMP`` once got THAT directory deleted. Only the
    process that made the directory deletes it (a forked child exiting must
    not pull it from under its parent), and only a directory that passes
    is_session_tmp()."""
    if os.getpid() != owner_pid or not is_session_tmp(path):
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


atexit.register(_remove_session_tmp, _SESSION_TMP, os.getpid())

# Fixed values, overwritten: the shell cannot supply a real one.
FORCED_ENV = {
    "MODE": "shadow",
    "LLM_FAKE": "1",
    "NOTIFY": "off",
    "RUNTIME": "local",
    "ADVERO_TMP_DIR": _SESSION_TMP,
    "STORE_PATH": os.path.join(_SESSION_TMP, "store.json"),
    "INSTANTLY_API_KEY": "test-key-not-real",
    # Inherited by every child process a test starts; shared.settings.load_env()
    # reads no dotenv file while it is set (listed test-only in modal_app).
    "ADVERO_TEST_SESSION": "1",
    # modal reads its token file at import; point it at a file that never exists.
    "MODAL_CONFIG_PATH": os.path.join(_SESSION_TMP, "no-such-modal.toml"),
}
os.environ.update(FORCED_ENV)
# Absent on purpose (the allowlist already removed them; named here so the
# intent survives an allowlist edit): ALLOW_LIVE_WRITES, JOB_LOG_SHEET_ID,
# GHL_PRIVATE_INTEGRATION_TOKEN, and the log-path overrides.
for _key in ("ALLOW_LIVE_WRITES", "JOB_LOG_SHEET_ID", "JOB_LOG_PATH", "SHADOW_LOG_PATH",
             "LLM_LEDGER_PATH", "GHL_PRIVATE_INTEGRATION_TOKEN"):
    os.environ.pop(_key, None)

# ------------------------------------------ children keep the session flag
TEST_SESSION_FLAG = "ADVERO_TEST_SESSION"
refused_spawns = []  # (event, program) per refused child; read by tests


class ChildWithoutTestFlag(PermissionError):
    """A test tried to start a process without ADVERO_TEST_SESSION=1."""


def env_has_test_flag(env) -> bool:
    """``env`` as a spawn receives it; None means "inherit os.environ"."""
    if env is None:
        env = os.environ
    try:
        value = None
        for key in (TEST_SESSION_FLAG, TEST_SESSION_FLAG.encode("ascii")):
            try:
                value = env.get(key)
            except TypeError:
                continue  # os.environ takes str keys only, os.environb bytes
            if value is not None:
                break
    except AttributeError:
        return False  # not a mapping: refuse rather than guess
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    return value == "1"


# event -> index of the env argument (None: the event has none, the child
# inherits os.environ)
_SPAWN_EVENTS = {
    "subprocess.Popen": 3,    # (executable, args, cwd, env)
    "os.exec": 2,             # (path, args, env)
    "os.posix_spawn": 2,      # (path, argv, env)
    "os.spawn": 3,            # (mode, path, args, env)
    "os.system": None,        # (command,)
    "pty.spawn": None,        # (argv,): raised BEFORE pty.spawn forks
}


def _spawn_audit_hook(event, args):
    index = _SPAWN_EVENTS.get(event, -1)
    if index == -1:
        return
    env = args[index] if index is not None and len(args) > index else None
    if env_has_test_flag(env):
        return
    program = args[0] if args else None
    refused_spawns.append((event, repr(program)))
    raise ChildWithoutTestFlag(
        "conftest refused %s(%r): the child's environment has no %s=1, so its "
        "shared.settings.load_env() would read the real .env files, and a child has "
        "none of this session's socket or file guards. Build env from os.environ "
        "(env = dict(os.environ); env.update(...)) instead of from scratch."
        % (event, program, TEST_SESSION_FLAG))


sys.addaudithook(_spawn_audit_hook)


def fork_exec_env_has_test_flag(env) -> bool:
    """``env`` as _posixsubprocess.fork_exec receives it: None to inherit
    os.environ, otherwise a sequence of b"KEY=value" entries."""
    if env is None:
        return env_has_test_flag(None)
    want = ("%s=1" % TEST_SESSION_FLAG).encode("ascii")
    try:
        entries = list(env)
    except TypeError:
        return False
    for entry in entries:
        if isinstance(entry, str):
            entry = entry.encode("utf-8", "replace")
        if entry == want:
            return True
    return False


# multiprocessing's spawn and forkserver start methods (and so
# ProcessPoolExecutor, spawn by default on macOS) start the interpreter
# through _posixsubprocess.fork_exec directly and raise no subprocess.Popen
# event, so the audit hook above never sees them. subprocess itself calls the
# same function by module attribute, which makes this a second lock for it.
import _posixsubprocess  # noqa: E402

_real_fork_exec = _posixsubprocess.fork_exec
_FORK_EXEC_ENV_INDEX = 5  # fork_exec(args, executable_list, close_fds, pass_fds, cwd, env, ...)


def _guarded_fork_exec(*args, **kwargs):
    env = args[_FORK_EXEC_ENV_INDEX] if len(args) > _FORK_EXEC_ENV_INDEX else kwargs.get("env")
    if not fork_exec_env_has_test_flag(env):
        program = args[0] if args else None
        refused_spawns.append(("_posixsubprocess.fork_exec", repr(program)))
        raise ChildWithoutTestFlag(
            "conftest refused to start %r: the child's environment has no %s=1 (this "
            "route is multiprocessing / ProcessPoolExecutor or subprocess). Keep the "
            "session's environment when starting a child." % (program, TEST_SESSION_FLAG))
    return _real_fork_exec(*args, **kwargs)


_posixsubprocess.fork_exec = _guarded_fork_exec

import pytest  # noqa: E402

# ------------------------------------------------ python-dotenv is inert
# shared.settings is not the only loader: execution/ modules call
# load_dotenv() at import, and services/metrics/sheet.py puts execution/ on
# sys.path. Patched on both dotenv and dotenv.main before anything imports
# them by name. The originals stay reachable for the one test that proves a
# fake dotenv file is well formed.
import dotenv  # noqa: E402
import dotenv.main  # noqa: E402

_real_load_dotenv = dotenv.main.load_dotenv
_real_dotenv_values = dotenv.main.dotenv_values
dotenv_calls = []  # (function name, repr of the path argument); read by tests


def _inert_load_dotenv(dotenv_path=None, *args, **kwargs):
    dotenv_calls.append(("load_dotenv", repr(dotenv_path)))
    return False


def _inert_dotenv_values(dotenv_path=None, *args, **kwargs):
    dotenv_calls.append(("dotenv_values", repr(dotenv_path)))
    return {}


for _mod in (dotenv, dotenv.main):
    _mod.load_dotenv = _inert_load_dotenv
    _mod.dotenv_values = _inert_dotenv_values

# --------------------------------------------------------------- no SMTP
# Importing shared.notify imports shared.settings, which calls load_env(). That
# used to load the parent AdveroSolutions/.env, whose NOTIFICATION_EMAIL,
# GMAIL_SENDER_EMAIL and GMAIL_APP_PASSWORD made _email_config() return
# Lorenzo's real Gmail login inside the test process; any test that set
# NOTIFY=on and got past the shadow guard then opened smtp.gmail.com:465 and
# sent a real message.
#
# Three locks now, because any one alone can be undone by a test:
#   1. load_env() reads nothing under pytest, and the scrub above leaves no
#      credential in the environment for it to fall back on;
#   2. the environment is scrubbed AGAIN after the import, and anything that
#      reappeared is recorded in leaked_after_import (a test pins it empty);
#   3. the _smtp_factory seam is replaced, so even a test that sets its own
#      credentials (shared/tests/test_notify.py does) cannot open a socket
#      unless it also installs its own fake factory.
import shared.notify as _notify_mod  # noqa: E402  (must follow the env setup)

leaked_after_import = [k for k in scrub_environment() if k not in FORCED_ENV]
os.environ.update(FORCED_ENV)

smtp_attempts = []  # inspected by shared/tests/test_notify.py


def _refuse_smtp(*args, **kwargs):
    smtp_attempts.append((args, kwargs))
    raise AssertionError(
        "A test tried to open a real SMTP connection to %r. Tests never talk to "
        "a mail server: monkeypatch shared.notify._smtp_factory with a fake in "
        "the test that needs the email leg." % (args[:2],))


_notify_mod._smtp_factory = _refuse_smtp


@pytest.fixture(autouse=True, scope="session")
def _no_smtp_sockets():
    """Re-assert the SMTP block for the whole session and fail loudly if any
    test opened a socket through the unpatched seam."""
    _notify_mod._smtp_factory = _refuse_smtp
    yield
    assert not smtp_attempts, "tests opened %d real SMTP connection(s)" % len(smtp_attempts)


@pytest.fixture(autouse=True)
def _no_egress_from_this_test():
    """Attribute a blocked connection to the test that made it. The session
    still fails at the end (pytest_sessionfinish) if this is bypassed."""
    before = len(egress_attempts)
    yield
    new = egress_attempts[before:]
    if new:
        pytest.fail(egress_report(new, scope="test"), pytrace=False)


def pytest_sessionfinish(session, exitstatus):
    fail_session_on_egress(session)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.write_line(
        "conftest egress guard: %d non-loopback connection attempt(s); credential-file opens refused: %d"
        % (len(egress_attempts), len(credential_file_opens)))


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """Per-test isolated file tree for the shared library."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.delenv("JOB_LOG_PATH", raising=False)
    monkeypatch.delenv("SHADOW_LOG_PATH", raising=False)
    monkeypatch.delenv("LLM_LEDGER_PATH", raising=False)
    return tmp_path


@pytest.fixture
def shadow_mode(monkeypatch):
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)


@pytest.fixture
def live_mode(monkeypatch):
    """Live mode for unit tests ONLY: every HTTP call is still mocked."""
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
