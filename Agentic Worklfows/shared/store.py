"""Small key/value store used by the services for state (cadence timers,
offered slots, processed reply ids).

Values are JSON-serialisable dicts/lists. Two backends:

* JsonFileStore(path)  - one JSON file, atomic writes (tmp + rename), fcntl lock
* ModalDictStore(name) - modal.Dict, imported lazily (RUNTIME=modal only)

get_store() picks by environment.
"""
import fcntl
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from shared.paths import tmp_file

logger = logging.getLogger("shared.store")


class _Absent(object):
    """Sentinel for compare_and_set: "this key must not exist yet"."""

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<ABSENT>"


ABSENT = _Absent()


class StoreError(Exception):
    """Raised when the store cannot guarantee what a caller asked for (today:
    failing to take the lock that makes a claim atomic)."""


class Store(object):
    """Abstract interface."""

    def get(self, key: str, default: Any = None) -> Any:
        raise NotImplementedError

    def set(self, key: str, value: Any) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def keys(self, prefix: str = "") -> List[str]:
        raise NotImplementedError

    def append(self, key: str, item: Any) -> List[Any]:
        """Append item to the list stored at key (creating it) and return the list."""
        raise NotImplementedError

    # -- atomic primitives ---------------------------------------------------
    # The get-then-set idiom ("if store.get(k) is None: process(); store.set(k)")
    # is two operations: two workers both read None and both act. Every
    # once-only decision (a processed reply id, a slot reservation) must go
    # through one of these instead.
    def set_if_absent(self, key: str, value: Any) -> bool:
        """Claim ``key``. True when this caller wrote it, False when it already
        existed. Atomic against other processes and containers."""
        raise NotImplementedError

    def add_once(self, key: str, item: Any) -> bool:
        """Append ``item`` to the list at ``key`` unless it is already there.
        True when this caller added it. Atomic: no append is ever lost."""
        raise NotImplementedError

    def mutate(self, key: str, fn, default: Any = None) -> Any:
        """Read-modify-write ``key`` under one lock and return the new value.

        ``fn(current)`` returns the value to store. ``get`` then ``set`` takes
        the lock twice, so two workers interleaving ``get(A); get(B); set(A);
        set(B)`` lose the first write. Every read-modify-write on a record two
        processes can touch (a touch schedule, a recovery record) belongs here.
        """
        raise NotImplementedError

    def compare_and_set(self, key: str, expected: Any, value: Any) -> bool:
        """Write ``value`` only if the stored value still equals ``expected``
        (use the module sentinel ``ABSENT`` for "must not exist"). True when
        this caller wrote it. The optimistic half of ``mutate``, for callers
        that compute the new value outside the lock.
        """
        raise NotImplementedError

    # convenience
    def items(self, prefix: str = "") -> Iterator:
        for k in self.keys(prefix):
            yield k, self.get(k)


class JsonFileStore(Store):
    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = Path(str(self.path) + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- locking -------------------------------------------------------------
    class _Lock(object):
        def __init__(self, lock_path: Path):
            self.lock_path = lock_path
            self.fh = None

        def __enter__(self):
            self.fh = open(self.lock_path, "a+")
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
            return self

        def __exit__(self, *exc):
            try:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
            finally:
                self.fh.close()
            return False

    def _lock(self):
        return JsonFileStore._Lock(self.lock_path)

    # -- io ------------------------------------------------------------------
    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            # Never read a truncated store as an empty one. Silently starting
            # empty erases every appointment schedule and recovery record, and
            # the next tick re-sends every touch in the window. Move the bad
            # file aside so it can be inspected, then fail loudly.
            quarantine = "%s.corrupt-%s" % (self.path, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
            try:
                os.replace(str(self.path), quarantine)
            except OSError as move_exc:  # noqa: BLE001
                logger.error("store file %s is corrupt and could not be moved aside: %s", self.path, move_exc)
                quarantine = None
            raise StoreError(
                "store file %s is corrupt (%s)%s. Nothing was read; fix or delete the file before "
                "running again, or the next tick re-sends every touch in the window."
                % (self.path, exc, "; moved to %s" % quarantine if quarantine else "")
            )

    def _write(self, data: Dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1, sort_keys=True, default=str)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    # -- api -----------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock():
            return self._read().get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock():
            data = self._read()
            data[key] = value
            self._write(data)

    def delete(self, key: str) -> None:
        with self._lock():
            data = self._read()
            if key in data:
                del data[key]
                self._write(data)

    def keys(self, prefix: str = "") -> List[str]:
        with self._lock():
            return sorted(k for k in self._read().keys() if k.startswith(prefix))

    def append(self, key: str, item: Any) -> List[Any]:
        with self._lock():
            data = self._read()
            current = data.get(key)
            if current is None:
                current = []
            elif not isinstance(current, list):
                current = [current]
            current.append(item)
            data[key] = current
            self._write(data)
            return current

    def set_if_absent(self, key: str, value: Any) -> bool:
        # The whole read-decide-write span happens inside one flock, which is
        # what makes it a claim rather than two racing operations.
        with self._lock():
            data = self._read()
            if key in data:
                return False
            data[key] = value
            self._write(data)
            return True

    def add_once(self, key: str, item: Any) -> bool:
        with self._lock():
            data = self._read()
            current = data.get(key)
            if current is None:
                current = []
            elif not isinstance(current, list):
                current = [current]
            if item in current:
                return False
            current.append(item)
            data[key] = current
            self._write(data)
            return True

    def mutate(self, key: str, fn, default: Any = None) -> Any:
        with self._lock():
            data = self._read()
            current = data.get(key, default)
            value = fn(current)
            data[key] = value
            self._write(data)
            return value

    def compare_and_set(self, key: str, expected: Any, value: Any) -> bool:
        with self._lock():
            data = self._read()
            present = key in data
            if expected is ABSENT:
                if present:
                    return False
            elif not present or data[key] != expected:
                return False
            data[key] = value
            self._write(data)
            return True

    def clear(self) -> None:
        with self._lock():
            self._write({})


class ModalDictStore(Store):
    """Backed by modal.Dict. Only imported when RUNTIME=modal.

    Modal runs the poller (*/5), the hourly cadence tick and the webhook app in
    separate concurrent containers, so a plain get-then-set loses writes. Every
    read-modify-write here is serialised with a lock key held through
    ``modal.Dict.put(..., skip_if_exists=True)``, which is the only atomic
    primitive the Dict offers.
    """

    LOCK_PREFIX = "__lock__:"
    LOCK_TIMEOUT_SECONDS = 10.0
    LOCK_STALE_SECONDS = 60.0

    def __init__(self, name: str, create_if_missing: bool = True):
        import modal  # lazy: modal is only present in the cloud image

        self.name = name
        self._dict = modal.Dict.from_name(name, create_if_missing=create_if_missing)

    # -- atomic put ----------------------------------------------------------
    _MISSING = object()

    def _put_if_absent(self, key: str, value: Any) -> bool:
        try:
            return bool(self._dict.put(key, value, skip_if_exists=True))
        except (AttributeError, TypeError):
            # modal without skip_if_exists: degrade to a checked write and say so
            logger.warning("modal.Dict.put(skip_if_exists) unavailable; claim on %r is not atomic", key)
            if self.get(key, ModalDictStore._MISSING) is not ModalDictStore._MISSING:
                return False
            self.set(key, value)
            return True

    class _KeyLock(object):
        def __init__(self, store, key):
            self.store = store
            self.lock_key = ModalDictStore.LOCK_PREFIX + key
            self.key = key

        def __enter__(self):
            deadline = time.time() + ModalDictStore.LOCK_TIMEOUT_SECONDS
            while True:
                if self.store._put_if_absent(self.lock_key, {"at": time.time(), "pid": os.getpid()}):
                    return self
                holder = self.store.get(self.lock_key) or {}
                held_since = 0.0
                if isinstance(holder, dict):
                    try:
                        held_since = float(holder.get("at") or 0)
                    except (TypeError, ValueError):
                        held_since = 0.0
                if time.time() - held_since > ModalDictStore.LOCK_STALE_SECONDS:
                    logger.warning("breaking a stale store lock on %r", self.key)
                    self.store.delete(self.lock_key)
                    continue
                if time.time() >= deadline:
                    raise StoreError(
                        "could not acquire the store lock for %r within %.0fs"
                        % (self.key, ModalDictStore.LOCK_TIMEOUT_SECONDS)
                    )
                time.sleep(0.05)

        def __exit__(self, *exc):
            try:
                self.store.delete(self.lock_key)
            except Exception:  # noqa: BLE001 - never mask the body's exception
                logger.warning("could not release the store lock for %r", self.key)
            return False

    def _lock(self, key: str):
        return ModalDictStore._KeyLock(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self._dict[key]
        except KeyError:
            return default

    def set(self, key: str, value: Any) -> None:
        self._dict[key] = value

    def delete(self, key: str) -> None:
        try:
            self._dict.pop(key)
        except KeyError:
            pass

    def keys(self, prefix: str = "") -> List[str]:
        return sorted(
            k for k in self._dict.keys()
            if str(k).startswith(prefix) and not str(k).startswith(self.LOCK_PREFIX)
        )

    def _as_list(self, key: str) -> List[Any]:
        current = self.get(key)
        if current is None:
            return []
        return list(current) if isinstance(current, list) else [current]

    def append(self, key: str, item: Any) -> List[Any]:
        with self._lock(key):
            current = self._as_list(key)
            current.append(item)
            self.set(key, current)
            return current

    def set_if_absent(self, key: str, value: Any) -> bool:
        return self._put_if_absent(key, value)

    def add_once(self, key: str, item: Any) -> bool:
        with self._lock(key):
            current = self._as_list(key)
            if item in current:
                return False
            current.append(item)
            self.set(key, current)
            return True

    def mutate(self, key: str, fn, default: Any = None) -> Any:
        with self._lock(key):
            value = fn(self.get(key, default))
            self.set(key, value)
            return value

    def compare_and_set(self, key: str, expected: Any, value: Any) -> bool:
        with self._lock(key):
            current = self.get(key, ModalDictStore._MISSING)
            present = current is not ModalDictStore._MISSING
            if expected is ABSENT:
                if present:
                    return False
            elif not present or current != expected:
                return False
            self.set(key, value)
            return True


_STORE = None  # type: Optional[Store]
_STORE_KEY = None  # type: Optional[Tuple[str, str]]

# ---------------------------------------------------------------- Modal Dicts
# The shadow watch and the live run must never share a Dict (owner decision
# R5, GOL-4). In shadow the cadence marks every would-be touch as a used day,
# reserves the slots it offered, and the poller moves its cursor past every
# reply it saw; carried into live, leads resume at day 3, positives from the
# watch are never drafted and shadow reservations block real slots. So the
# name is derived from the EFFECTIVE mode of the process: only MODE=live with
# ALLOW_LIVE_WRITES=1 reads and writes the live Dict. A misconfigured
# MODE=live without the flag writes nothing live and so stays on the shadow
# Dict. MODAL_DICT_NAME, when set, still wins (tests and one-off tools).
MODAL_DICT_BASE = "advero-reply-engine-store"
STORE_MODES = ("shadow", "live")

# Written last by changesets/deploy/cutover.py into the live Dict. Every
# scheduled Modal function refuses to run live until it exists, so a live
# deploy that skipped the cutover cannot start polling from an empty cursor
# (which would re-process up to 2,000 replies from the watch).
CUTOVER_KEY = "cutover:record"
# Written by the first live tick that accepts cutover:record. Before it exists
# a live tick also refuses a cutover record older than CUTOVER_MAX_AGE_MINUTES:
# the hand-off list and the shadow cards describe the moment of the cutover,
# and a live flip days later would start from a stale point (review item 7c).
CUTOVER_ACCEPTED_KEY = "cutover:accepted"
CUTOVER_MAX_AGE_MINUTES = 120

# Deployed evidence (Job_Log rows and shadow records mirrored out of Modal
# containers by shared.job_log) lives in its OWN Dict per mode, never in the
# engine's Dict: tens of thousands of evidence keys would otherwise be
# re-scanned on every prefix scan the engine makes, and a live deploy made
# before the cutover would leave rows in the live engine Dict that make it
# look used (review items 3 and 8). Modal expires a Dict entry after 7 days
# with no read or write, so this evidence lasts 7 days.
OBS_DICT_BASE = "advero-reply-engine-obs"


def modal_dict_name(mode: str) -> str:
    """The Modal Dict for ``mode`` ('shadow' or 'live'). Anything else raises."""
    if mode not in STORE_MODES:
        raise ValueError("store mode must be one of %s, not %r" % (list(STORE_MODES), mode))
    return "%s-%s" % (MODAL_DICT_BASE, mode)


def obs_dict_name(mode: str) -> str:
    """The evidence Dict for ``mode`` ('shadow' or 'live'). Anything else raises."""
    if mode not in STORE_MODES:
        raise ValueError("store mode must be one of %s, not %r" % (list(STORE_MODES), mode))
    return "%s-%s" % (OBS_DICT_BASE, mode)


def effective_mode() -> str:
    """'live' only for MODE=live AND ALLOW_LIVE_WRITES=1, else 'shadow'.

    Read from the environment directly, like shared.job_log, so this module
    stays importable without shared.settings (which loads .env at import)."""
    live = os.environ.get("MODE", "shadow") == "live" and os.environ.get("ALLOW_LIVE_WRITES") == "1"
    return "live" if live else "shadow"


def _store_target() -> Tuple[str, str]:
    if os.environ.get("RUNTIME") == "modal":
        return ("modal", os.environ.get("MODAL_DICT_NAME") or modal_dict_name(effective_mode()))
    return ("json", os.environ.get("STORE_PATH") or str(tmp_file("store.json")))


def open_modal_store(mode: str, create_if_missing: bool = False) -> "ModalDictStore":
    """The deployed Dict for ``mode``, opened from the laptop by the deploy
    tools (watch_report, cutover, budget). Read-only callers pass
    ``create_if_missing=False`` so a typo never creates an empty Dict that then
    reads as "nothing happened"."""
    return ModalDictStore(modal_dict_name(mode), create_if_missing=create_if_missing)


def open_obs_store(mode: str, create_if_missing: bool = False) -> "ModalDictStore":
    """The deployed evidence Dict for ``mode``, opened from the laptop by the
    deploy tools. Same create_if_missing rule as open_modal_store."""
    return ModalDictStore(obs_dict_name(mode), create_if_missing=create_if_missing)


_OBS_STORE = None  # type: Optional[Store]
_OBS_STORE_KEY = None  # type: Optional[Tuple[str, str]]


def get_obs_store(force_new: bool = False) -> Store:
    """Where shared.job_log mirrors deployed evidence.

    RUNTIME=modal -> the evidence Dict of the effective mode; anywhere else a
    local JSON file (.tmp/obs_store.json), which only tests touch: off Modal
    nothing is mirrored."""
    global _OBS_STORE, _OBS_STORE_KEY
    if os.environ.get("RUNTIME") == "modal":
        target = ("modal", obs_dict_name(effective_mode()))
    else:
        target = ("json", str(tmp_file("obs_store.json")))
    if _OBS_STORE is not None and _OBS_STORE_KEY == target and not force_new:
        return _OBS_STORE
    _OBS_STORE = ModalDictStore(target[1]) if target[0] == "modal" else JsonFileStore(target[1])
    _OBS_STORE_KEY = target
    return _OBS_STORE


def get_store(force_new: bool = False) -> Store:
    """RUNTIME=modal -> ModalDictStore(MODAL_DICT_NAME, or the shadow/live
    Dict named by modal_dict_name(effective_mode()));
    otherwise JsonFileStore(STORE_PATH or .tmp/store.json).

    The cache is keyed on (runtime, path/name): a job that sets STORE_PATH after
    importing shared, or a test that points tmp_env at a per-test file, gets the
    store it asked for instead of the one built on the first call.
    """
    global _STORE, _STORE_KEY
    target = _store_target()
    if _STORE is not None and _STORE_KEY == target and not force_new:
        return _STORE
    if target[0] == "modal":
        _STORE = ModalDictStore(target[1])
    else:
        _STORE = JsonFileStore(target[1])
    _STORE_KEY = target
    return _STORE
