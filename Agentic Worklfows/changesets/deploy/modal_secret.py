#!/usr/bin/env python3
"""Build the Modal secret ``advero-reply-engine`` from .env. The ONE way to create
or re-create it (GOL-5, GOL-7).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/modal_secret.py --mode shadow                      # plan only
    python3 changesets/deploy/modal_secret.py --mode shadow --create             # first pass
    python3 changesets/deploy/modal_secret.py --mode shadow --base-url "$(cat .tmp/deploy/web_url.txt)" --create
    python3 changesets/deploy/modal_secret.py --mode live --create               # the live flip

What it guarantees
------------------
* The write-capable keys (INSTANTLY_API_KEY, GHL_PRIVATE_INTEGRATION_TOKEN;
  the table is shared/keys.py) come from ~/.advero/live.env first
  (shared.keys.LIVE_ENV_PATH, outside the repo, chmod 600), then the process
  environment (a shell that sourced that file), then .env. That file overrides
  .env for the secret only: shared.settings.load_env never reads it, so agent
  sessions only ever see the _READ keys (decision R2(a),
  runbooks/read_only_keys.md). Only the write-key names are taken from it;
  any other name in it is ignored and listed. Whenever the repo .env still
  holds a write key (the only source, or a copy left behind) a note says to
  delete it; a process value equal to the .env value is labelled .env, since
  load_env put it there.
* Every other value comes from .env (Agentic Worklfows/.env, then AdveroSolutions/.env,
  first one wins) or is set here on purpose (MODE, ALLOW_LIVE_WRITES,
  NOTIFY_SHADOW_SEND, WEBHOOK_SECRET, DEBUG_SECRET, ALLOW_PAID_CALLS=0). No
  placeholder, no blank: an optional key that is empty in .env is left OUT of
  the secret, and a value that looks like a placeholder refuses the run. One
  exception: an empty AUTO_SEND_TEMPLATES= is the template auto-send kill
  switch on the laptop, so it is sent as "off" rather than left out (left out,
  Modal would read it as not set and keep auto-send on).
* It refuses when a required key is missing: INSTANTLY_API_KEY,
  ANTHROPIC_API_KEY, NTFY_TOPIC, GHL_PRIVATE_INTEGRATION_TOKEN,
  NTFY_ALLOW_SENSITIVE (0 or 1, DECISIONS C7) and REPLY_ENGINE_SECRET. It also
  refuses when no channel can carry an approval card's buttons (a protected
  ntfy topic, or the full email leg).
* REPLY_ENGINE_SECRET is read from .env, its one saved source, and is NEVER
  generated here. The six Instantly webhooks and every outstanding approval
  link carry it, so a new value breaks them all. If .env has none, add one
  once (``python3 -c "import secrets;print(secrets.token_hex(24))"``) and never
  change it. A stale .tmp/reply_engine_secret.txt that disagrees refuses.
* It prints key NAMES and value LENGTHS only, never a value.
* It runs ``python3 -m modal secret create advero-reply-engine --from-json <tmp>
  --force`` only with ``--create`` AND the word CREATE typed on the terminal
  (not stdin, so it cannot be piped). The JSON file is 0600 and deleted after.
* ``--mode live --create`` also refuses, before it asks, unless
  ``install_schedules.sh --preflight`` passed on THIS code within the last
  hour (changesets/deploy/preflight_stamp.py). The live flip starts at this
  secret, so the preflight has to pass before it, never after. The runbook's
  live flip is ``install_schedules.sh --deploy live``, which calls this and
  deploys right after it.

Without --create it contacts nothing and writes nothing. Python 3.9.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from changesets.deploy import common
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common

SECRET_NAME = "advero-reply-engine"

REQUIRED_FROM_ENV = (
    "INSTANTLY_API_KEY", "ANTHROPIC_API_KEY", "NTFY_TOPIC", "GHL_PRIVATE_INTEGRATION_TOKEN",
    "NTFY_ALLOW_SENSITIVE", "REPLY_ENGINE_SECRET",
)
# Capability switches: the .env value when present, else "0" (a real value,
# not a blank): A2P registration and the D6 calendar hold stay off until set.
DEFAULT_OFF_FROM_ENV = ("A2P_10DLC_REGISTERED", "CADENCE_D6_HOLD")
# Included only when .env has a non-empty value; otherwise left out entirely.
OPTIONAL_FROM_ENV = (
    "GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NOTIFY_EMAIL",
    "JOB_LOG_SHEET_ID", "GOOGLE_CREDENTIALS_JSON",
    "ZOOM_WEBHOOK_SECRET", "ZOOM_URL_VALIDATION", "NTFY_TOKEN",
    "SHOW_RATE_SENDER", "AUTO_SEND_AFTER_MINUTES", "LOOM_URL_GENERIC", "LOG_LEVEL",
    "AUTO_SEND_TEMPLATES",
    "FIREFLIES_API_KEY", "PAYMENT_LINK_URL",
    "DAILY_METRICS_SHEET_ID", "SKOOL_GROUP", "SKOOL_GROUP_ID",
)
# Optional keys whose EMPTY value is a decision, not a gap: an empty
# AUTO_SEND_TEMPLATES= is the kill switch on the laptop
# (template_approvals.kill_switch_on: any set value but 1/on/true/yes), so it
# is sent as this value instead of being left out, and Modal agrees.
EMPTY_IS_OFF = {"AUTO_SEND_TEMPLATES": "off"}
# Set by this script, never read from .env.
SET_HERE = ("MODE", "ALLOW_LIVE_WRITES", "NOTIFY_SHADOW_SEND", "WEBHOOK_SECRET", "DEBUG_SECRET",
            "ALLOW_PAID_CALLS", "BASE_URL", "REPLY_ENGINE_BASE_URL")
# In SECRET_KEYS but deliberately not sent: no Modal schedule reads them (the
# list factory runs on the laptop), so a copy on Modal is exposure for nothing.
NOT_SENT = {
    "APIFY_API_TOKEN": "only the list factory uses it, and it runs on the laptop",
    "APIFY_TOKEN": "only the list factory uses it, and it runs on the laptop",
}

LEGACY_SECRET_NAME = "reply_engine_secret.txt"    # the old runbook's copy, under .tmp/
MIN_SECRET_CHARS = 32
PLACEHOLDER_RE = re.compile(
    r"(<[^>]*>|paste[_ ]?your|your[_ ]|changeme|change[_ ]me|placeholder|replace[_ ]?me|\bxxx+\b|\btodo\b|"
    r"example\.(com|org)|\.\.\.$)", re.IGNORECASE)


class SecretRefused(Exception):
    """The secret cannot be built safely; the message names keys, never values."""


def env_paths() -> List[str]:
    from shared.paths import ENV_PATHS

    return [str(p) for p in ENV_PATHS]


def read_env_files(paths: Sequence[str], loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> Dict[str, str]:
    """Merged .env values, the first file winning per key. os.environ is not
    touched and is not consulted: the secret is built from the saved files.
    ``loader`` is a test seam (the test session makes python-dotenv inert)."""
    if loader is None:
        from dotenv import dotenv_values as loader

    merged = {}  # type: Dict[str, str]
    for path in paths:
        if not os.path.isfile(path):
            continue
        for key, value in loader(path).items():
            if key not in merged and value is not None:
                merged[key] = value
    return merged


LIVE_ENV_LABEL = "~/.advero/live.env"


def write_key_names() -> Tuple[str, ...]:
    from shared import keys

    return keys.write_key_names()


def live_env_file() -> str:
    """shared.keys.LIVE_ENV_PATH expanded against the current HOME."""
    from shared import keys

    return keys.live_env_path()


def _real_home() -> str:
    """The account's home from the password database, whatever HOME says
    (unresolved: _protected_roots resolves it separately)."""
    import pwd

    return os.path.abspath(pwd.getpwuid(os.getuid()).pw_dir)


def _under(path: str, root: str) -> bool:
    root = root.rstrip(os.sep)
    return path == root or path.startswith(root + os.sep)


def _protected_roots() -> Tuple[str, ...]:
    """The real home and the real ~/.advero, each as written and resolved."""
    home = _real_home()
    advero = os.path.join(home, ".advero")
    return tuple(sorted(set((home, os.path.realpath(home), advero, os.path.realpath(advero)))))


def _in_real_home(path: str) -> bool:
    """True when ``path``, as written OR resolved, lies under the real home or
    under the real ~/.advero. Resolved alone is not enough: a symlinked
    ~/.advero resolves outside the home; as written alone is not enough: a temp
    symlink can point into ~/.advero."""
    candidates = (os.path.abspath(path), os.path.realpath(path))
    return any(_under(c, root) for c in candidates for root in _protected_roots())


def read_live_env(path: Optional[str] = None,
                  loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> Tuple[Dict[str, str], List[str]]:
    """(write-capable key values from ~/.advero/live.env, notes). Names only in
    the notes, never a value. A missing file is not an error (.env still works).

    Under a test session a file inside the account's real home directory is
    never opened, so a test run cannot read the real write keys; tests point
    HOME (or shared.keys.LIVE_ENV_PATH) at a temp dir."""
    from shared import settings

    path = path or live_env_file()
    notes = []  # type: List[str]
    if settings.running_under_pytest() and _in_real_home(path):
        return {}, ["test session: %s is inside the real home directory and is not read" % LIVE_ENV_LABEL]
    if not os.path.isfile(path):
        return {}, notes
    if os.stat(path).st_mode & 0o077:
        notes.append("%s is readable by group or others; run chmod 600 on it" % LIVE_ENV_LABEL)
    if loader is None:
        from dotenv import dotenv_values as loader
    loaded = loader(path)
    wanted = write_key_names()
    values = {}  # type: Dict[str, str]
    for key in wanted:
        value = (loaded.get(key) or "").strip()
        if value:
            values[key] = value
    ignored = sorted(k for k in loaded if k not in wanted)
    if ignored:
        notes.append("%s: ignored (only the write-capable keys are read from it): %s"
                     % (LIVE_ENV_LABEL, ", ".join(ignored)))
    return values, notes


def overlay_write_keys(env: Dict[str, str], live: Dict[str, str],
                       environ: Mapping[str, str]) -> Tuple[Dict[str, str], Dict[str, str], List[str]]:
    """(env with the write keys resolved, source per write key, notes).

    Per write key: ~/.advero/live.env, then the process environment, then
    .env. Only the write-key names are touched; every other key stays exactly
    what .env said (D1: the secret is built from the saved files).

    ``environ`` in a real run is os.environ AFTER shared.settings.load_env()
    has copied every .env value into it (importing anything under shared/
    runs it), so a process value equal to the .env value is labelled .env: it
    came from there, not from a shell. The move-it note is raised whenever the
    saved .env files still hold a write key, whichever source wins."""
    merged = dict(env)
    source = {}  # type: Dict[str, str]
    notes = []  # type: List[str]
    for key in write_key_names():
        from_dotenv = (env.get(key) or "").strip()
        from_env = (environ.get(key) or "").strip()
        shell_value = from_env if from_env and from_env != from_dotenv else ""
        if live.get(key):
            merged[key], source[key] = live[key], LIVE_ENV_LABEL + " (required)"
            if shell_value and shell_value != live[key]:
                notes.append("%s in the process environment (not from .env) differs from %s; the file wins"
                             % (key, LIVE_ENV_LABEL))
            if from_dotenv and from_dotenv != live[key]:
                notes.append("%s in the repo .env differs from %s; the file wins" % (key, LIVE_ENV_LABEL))
        elif shell_value:
            merged[key], source[key] = shell_value, "process env (required)"
        elif from_dotenv:
            merged[key], source[key] = from_dotenv, ".env (required)"
        if from_dotenv:
            notes.append("%s is still in the repo .env, where agent sessions can read it; delete it from "
                         "both repo .env files and keep it only in %s (runbooks/read_only_keys.md)"
                         % (key, LIVE_ENV_LABEL))
    return merged, source, notes


def looks_like_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_RE.search(value or ""))


def _usable_base_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip().rstrip("/")
    if not value:
        return None
    lowered = value.lower()
    if not lowered.startswith("https://") or "localhost" in lowered or "127.0.0.1" in lowered \
            or "0.0.0.0" in lowered:
        return None
    return value


def _google_credentials(raw: str) -> str:
    """The service-account JSON itself (a laptop file path is useless in a
    container), validated for client_email and private_key."""
    info = None
    try:
        info = json.loads(raw)
    except ValueError:
        if os.path.isfile(raw):
            try:
                with open(raw, "r", encoding="utf-8") as fh:
                    info = json.load(fh)
            except (OSError, ValueError):
                info = None
    if not (isinstance(info, dict) and info.get("client_email") and info.get("private_key")):
        raise SecretRefused("GOOGLE_CREDENTIALS_JSON is set in .env but is not a service-account JSON "
                            "(or a path to one) with client_email and private_key; fix it or remove it")
    return json.dumps(info, separators=(",", ":"), sort_keys=True)


def legacy_secret_file() -> str:
    from shared.paths import tmp_dir

    return os.path.join(str(tmp_dir()), LEGACY_SECRET_NAME)


def build_secret(env: Dict[str, str], mode: str, base_url: Optional[str] = None,
                 legacy_path: Optional[str] = None) -> Tuple[Dict[str, str], Dict[str, str], List[str]]:
    """(values, source per key, notes). Raises SecretRefused naming the keys."""
    from services.reply_engine import modal_app

    legacy_path = legacy_path or legacy_secret_file()

    if mode not in ("shadow", "live"):
        raise SecretRefused("mode must be shadow or live")
    problems = []  # type: List[str]
    notes = []  # type: List[str]
    values = {}  # type: Dict[str, str]
    source = {}  # type: Dict[str, str]

    def get(key: str) -> str:
        return (env.get(key) or "").strip()

    missing = [k for k in REQUIRED_FROM_ENV if not get(k)]
    write_names = set(write_key_names())
    missing_write = [k for k in missing if k in write_names]
    missing_other = [k for k in missing if k not in write_names]
    if missing_other:
        problems.append("required key(s) missing or blank in .env: %s" % ", ".join(missing_other))
    if missing_write:
        problems.append("write-capable key(s) missing or blank in all three sources (%s, the process "
                        "environment, .env): %s" % (LIVE_ENV_LABEL, ", ".join(missing_write)))
    for key in REQUIRED_FROM_ENV:
        if get(key):
            values[key], source[key] = get(key), ".env (required)"

    if get("NTFY_ALLOW_SENSITIVE") and get("NTFY_ALLOW_SENSITIVE") not in ("0", "1"):
        problems.append("NTFY_ALLOW_SENSITIVE must be 0 or 1")

    secret = get("REPLY_ENGINE_SECRET")
    if secret:
        if len(secret) < MIN_SECRET_CHARS:
            problems.append("REPLY_ENGINE_SECRET is shorter than %d characters" % MIN_SECRET_CHARS)
        if os.path.isfile(legacy_path):
            with open(legacy_path, "r", encoding="utf-8") as fh:
                legacy = fh.read().strip()
            if legacy and legacy != secret:
                problems.append(".tmp/%s holds a DIFFERENT REPLY_ENGINE_SECRET from .env; .env is the one saved "
                                "source. Decide which one the webhooks carry, keep it in .env, delete the file"
                                % LEGACY_SECRET_NAME)
        for alias in ("WEBHOOK_SECRET", "DEBUG_SECRET"):
            if get(alias) and get(alias) != secret:
                problems.append("%s in .env differs from REPLY_ENGINE_SECRET; the secret sets both to "
                                "REPLY_ENGINE_SECRET, so remove it from .env or make it equal" % alias)
            values[alias], source[alias] = secret, "= REPLY_ENGINE_SECRET"

    for key in DEFAULT_OFF_FROM_ENV:
        if get(key):
            values[key], source[key] = get(key), ".env"
        else:
            values[key], source[key] = "0", "default off"

    for key in OPTIONAL_FROM_ENV:
        if not get(key):
            if key in EMPTY_IS_OFF and env.get(key) is not None:
                values[key], source[key] = EMPTY_IS_OFF[key], ".env (empty: sent as off, the kill switch)"
                notes.append("%s is empty in .env, which is the kill switch on the laptop; sent to Modal as %s "
                             "so both agree" % (key, EMPTY_IS_OFF[key]))
            continue
        if key == "GOOGLE_CREDENTIALS_JSON":
            try:
                values[key], source[key] = _google_credentials(get(key)), ".env (validated service account)"
            except SecretRefused as exc:
                problems.append(str(exc))
            continue
        values[key], source[key] = get(key), ".env"

    values["MODE"], source["MODE"] = mode, "--mode"
    values["ALLOW_LIVE_WRITES"], source["ALLOW_LIVE_WRITES"] = ("1" if mode == "live" else "0"), "--mode"
    values["NOTIFY_SHADOW_SEND"], source["NOTIFY_SHADOW_SEND"] = "1", "fixed: pushes to Lorenzo only"
    values["ALLOW_PAID_CALLS"], source["ALLOW_PAID_CALLS"] = "0", "fixed: no Modal schedule spends"

    url = _usable_base_url(base_url)
    if base_url is not None and not url:
        # An empty value is what "$(cat .tmp/deploy/web_url.txt)" gives when the
        # file is missing: never fall back to .env or to a first pass then.
        problems.append("--base-url must be an https:// URL that is not localhost (got %s)"
                        % ("an empty value: is .tmp/deploy/web_url.txt there?" if not str(base_url).strip()
                           else "%d characters" % len(str(base_url))))
    if url is None and base_url is None:
        url = _usable_base_url(get("BASE_URL"))
        if get("BASE_URL") and url is None:
            notes.append("BASE_URL in .env is not a public https URL; ignored")
        if url:
            source["BASE_URL"] = ".env"
    if url:
        values["BASE_URL"] = url
        values["REPLY_ENGINE_BASE_URL"] = url
        source.setdefault("BASE_URL", "--base-url")
        source["REPLY_ENGINE_BASE_URL"] = "= BASE_URL"
    elif mode == "live":
        problems.append("live needs the deployment's https URL: pass --base-url or set BASE_URL in .env")
    else:
        notes.append("BASE_URL is left OUT (first pass): approval buttons are dead until the second pass "
                     "re-creates the secret with --base-url and redeploys")

    ntfy_buttons = bool(get("NTFY_TOKEN")) or get("NTFY_ALLOW_SENSITIVE") == "1"
    email_leg = all(get(k) for k in ("GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NOTIFY_EMAIL"))
    if not (ntfy_buttons or email_leg):
        problems.append("no channel can carry an approval card's buttons: set NTFY_TOKEN or "
                        "NTFY_ALLOW_SENSITIVE=1, or all of GMAIL_SENDER_EMAIL, GMAIL_APP_PASSWORD, NOTIFY_EMAIL")

    for key, value in values.items():
        if key == "GOOGLE_CREDENTIALS_JSON":
            continue
        if not value.strip():
            problems.append("%s would be blank" % key)
        elif looks_like_placeholder(value):
            problems.append("%s looks like a placeholder; put the real value in .env or remove it" % key)

    unknown = sorted(set(values) - set(modal_app.SECRET_KEYS))
    if unknown:
        problems.append("keys not in modal_app.SECRET_KEYS: %s" % ", ".join(unknown))
    if problems:
        raise SecretRefused("; ".join(problems))
    for key, why in NOT_SENT.items():
        notes.append("%s not sent: %s" % (key, why))
    return values, source, notes


def describe(values: Dict[str, str], source: Dict[str, str]) -> List[str]:
    """One line per key: name, length, source. Never a value."""
    width = max(len(k) for k in values) if values else 10
    return ["  %-*s  %5d chars  %s" % (width, k, len(values[k]), source.get(k, "")) for k in sorted(values)]


def _scrub(text: str, values: Dict[str, str]) -> str:
    for value in sorted(values.values(), key=len, reverse=True):
        if len(value) >= 4:
            text = text.replace(value, "<redacted>")
    return text


def create(values: Dict[str, str], runner: Callable = subprocess.run) -> int:
    """Write a 0600 JSON file, run `modal secret create --from-json --force`,
    delete the file. Output is scrubbed of every value before it is shown."""
    directory = common.deploy_tmp()
    fd, path = tempfile.mkstemp(prefix="modal_secret_", suffix=".json", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(values, fh)
        cmd = [sys.executable, "-m", "modal", "secret", "create", SECRET_NAME, "--from-json", path, "--force"]
        proc = runner(cmd, cwd=common.BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      universal_newlines=True)
        code = proc.returncode
        if code != 0:
            print("modal secret create FAILED (exit %s):" % code)
            print(_scrub((proc.stderr or "") + (proc.stdout or ""), values)[-2000:])
        else:
            print("modal secret create: secret %s re-created with %d keys" % (SECRET_NAME, len(values)))
        return code
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def history_path() -> str:
    return os.path.join(common.deploy_tmp(), "secret_history.jsonl")


def base_url_host(values: Dict[str, str]) -> Optional[str]:
    from urllib.parse import urlparse

    url = values.get("BASE_URL") or ""
    return (urlparse(url).hostname or "").lower() or None


def _history(values: Dict[str, str], mode: str, status: str) -> None:
    # The host is recorded (not a secret: it is the public web URL's host) so
    # verify_health.py can prove the deployed BASE_URL is THIS deployment.
    record = {"ts_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "mode": mode,
              "status": status, "keys": dict((k, len(v)) for k, v in sorted(values.items())),
              "base_url_host": base_url_host(values)}
    try:
        with open(history_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        from shared.job_log import log_run

        log_run("deploy.modal_secret", status, {"mode": mode, "keys": sorted(values)})
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("could not record the secret history: %s\n" % exc)


def live_preflight_problems() -> List[str]:
    from changesets.deploy import preflight_stamp

    return preflight_stamp.problems()


def main(argv: Optional[List[str]] = None, runner: Callable = subprocess.run,
         confirm: Callable[[str, str], bool] = common.confirm_from_tty,
         env_loader: Optional[Callable[[str], Dict[str, Any]]] = None,
         preflight_check: Optional[Callable[[], List[str]]] = None,
         environ: Optional[Mapping[str, str]] = None) -> int:
    """``environ`` is where the write keys are looked up after
    ~/.advero/live.env. It defaults to os.environ, except under a test session,
    where it defaults to empty: the test conftest forces a fake
    INSTANTLY_API_KEY into os.environ, which would silently replace .env."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", required=True, choices=("shadow", "live"))
    parser.add_argument("--base-url", help="the deployment's https web URL (install_schedules.sh saves it "
                                           "to .tmp/deploy/web_url.txt)")
    parser.add_argument("--create", action="store_true",
                        help="actually run `modal secret create --force` (asks for CREATE on the terminal)")
    parser.add_argument("--env-file", action="append", dest="env_files",
                        help="read this .env instead of the default two (repeatable; tests)")
    args = parser.parse_args(argv)

    env = read_env_files(args.env_files or env_paths(), loader=env_loader)
    if environ is None:
        from shared import settings

        environ = {} if settings.running_under_pytest() else os.environ
    live, live_notes = read_live_env(loader=env_loader)
    env, write_source, write_notes = overlay_write_keys(env, live, environ)
    try:
        values, source, notes = build_secret(env, args.mode, args.base_url)
    except SecretRefused as exc:
        print("REFUSED: %s" % exc)
        print("The write-capable keys (%s) are looked for in %s, then the process environment, then .env."
              % (", ".join(write_key_names()), LIVE_ENV_LABEL))
        for note in live_notes + write_notes:
            print("note: %s" % note)
        print("Nothing was created.")
        return 1
    source.update(dict((k, v) for k, v in write_source.items() if k in values))
    notes = live_notes + write_notes + notes

    print("Modal secret %s, MODE=%s, %d keys (names and lengths only):" % (SECRET_NAME, args.mode, len(values)))
    for line in describe(values, source):
        print(line)
    for note in notes:
        print("note: %s" % note)
    if not args.create:
        print("\nPlan only. Nothing was created. Add --create to write it.")
        return 0
    if args.mode == "live":
        problems = (preflight_check or live_preflight_problems)()
        if problems:
            print("REFUSED: the live secret is created only after the preflight passed on this code:")
            for line in problems:
                print("  - %s" % line)
            print("Nothing was created. Run: bash changesets/schedules/install_schedules.sh --preflight")
            return 1
    if not confirm("CREATE", "Re-create Modal secret %s with these %d keys, MODE=%s?"
                   % (SECRET_NAME, len(values), args.mode)):
        print("Not confirmed. Nothing was created.")
        return 1
    code = create(values, runner=runner)
    _history(values, args.mode, "created" if code == 0 else "create_failed")
    if code == 0 and args.mode != "live":
        print("Next: redeploy so every container reads it (install_schedules.sh --deploy %s)." % args.mode)
    return code


if __name__ == "__main__":
    sys.exit(main())
