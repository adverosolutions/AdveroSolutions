"""Which API key a call uses: read-only for reads, write-capable for writes.

Decision R2(a) (runbooks/REREVIEW_2026-09-22.md, SAF-3): agent sessions only
ever see read-only keys. The write-capable keys live in the Modal secret and in
``~/.advero/live.env``, a file Lorenzo keeps outside the repo, chmod 600, and
sources by hand. ``shared.settings.load_env`` reads only the two repo ``.env``
files (``shared.paths.ENV_PATHS``) and never this one.

One table, one row per system:

    system       write-capable (main) name          read-only name
    instantly    INSTANTLY_API_KEY                  INSTANTLY_API_KEY_READ
    ghl          GHL_PRIVATE_INTEGRATION_TOKEN      GHL_PRIVATE_INTEGRATION_TOKEN_READ

* ``read_key(system)`` returns the ``_READ`` value when it is set and falls back
  to the main key when it is not, so nothing breaks before the read keys exist.
  While that fallback is in use in shadow mode it logs ONE warning per system
  per process, naming the variables and never a value.
* ``write_key(system)`` returns the main key only. There is no fallback to the
  read key: a write attempted with a read-only key would 403 at best.

``settings.guard_write`` stays the real protection. This module only narrows
what a leaked or misused key can do. See runbooks/read_only_keys.md.
"""
import logging
import os
from typing import Dict, Mapping, Optional, Tuple

logger = logging.getLogger("shared.keys")

READ_SUFFIX = "_READ"

# The one table of key names. The read name is always MAIN + READ_SUFFIX.
MAIN_KEY_NAMES = {
    "instantly": "INSTANTLY_API_KEY",
    "ghl": "GHL_PRIVATE_INTEGRATION_TOKEN",
}  # type: Dict[str, str]

# Where the write-capable keys live once they leave the repo .env. The ONE
# place this path is written down; changesets/deploy/modal_secret.py reads it
# from here. Expanded at call time, so a test that points HOME at a temp dir
# (or replaces this constant) never reaches the real file.
LIVE_ENV_PATH = os.path.join("~", ".advero", "live.env")

# (pid, system) pairs already warned about, so a forked child warns once too.
_warned = set()  # type: set


def _table(system: str) -> str:
    try:
        return MAIN_KEY_NAMES[system]
    except KeyError:
        raise KeyError("unknown system %r; known: %s" % (system, ", ".join(sorted(MAIN_KEY_NAMES))))


def main_name(system: str) -> str:
    """The write-capable variable name, e.g. INSTANTLY_API_KEY."""
    return _table(system)


def read_name(system: str) -> str:
    """The read-only variable name, e.g. INSTANTLY_API_KEY_READ."""
    return _table(system) + READ_SUFFIX


def write_key_names() -> Tuple[str, ...]:
    """Every write-capable variable name, in table order."""
    return tuple(MAIN_KEY_NAMES[s] for s in sorted(MAIN_KEY_NAMES))


def read_key_names() -> Tuple[str, ...]:
    return tuple(read_name(s) for s in sorted(MAIN_KEY_NAMES))


def live_env_path() -> str:
    """LIVE_ENV_PATH with ``~`` expanded against the current HOME."""
    return os.path.expanduser(LIVE_ENV_PATH)


def _value(name: str, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    env = os.environ if environ is None else environ
    value = (env.get(name) or "").strip()
    return value or None


def _shadow() -> bool:
    from shared import settings  # local import: settings loads .env on import

    return not settings.is_live()


def read_key_and_name(system: str, environ: Optional[Mapping[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """(value, variable name it came from) for reads; (None, None) when neither
    variable is set. The name is what error messages may show; the value never
    is."""
    rname = read_name(system)
    value = _value(rname, environ)
    if value:
        return value, rname
    mname = main_name(system)
    value = _value(mname, environ)
    if not value:
        return None, None
    marker = (os.getpid(), system)
    if marker not in _warned and _shadow():
        _warned.add(marker)
        logger.warning(
            "%s: %s is not set, so reads are using the write-capable %s. Create a read-only key and "
            "set %s (runbooks/read_only_keys.md).", system, rname, mname, rname)
    return value, mname


def read_key(system: str, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The ``_READ`` key when set, else the main key, else None."""
    return read_key_and_name(system, environ)[0]


def write_key(system: str, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The main (write-capable) key, or None. Never the read key."""
    return _value(main_name(system), environ)


def is_read_only_name(name: Optional[str]) -> bool:
    return bool(name) and str(name).endswith(READ_SUFFIX)


def _reset_warnings() -> None:
    """Test seam: forget which systems already warned in this process."""
    _warned.clear()
