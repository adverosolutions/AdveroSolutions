"""Test doubles for the deploy scripts: a stand-in for a deployed Modal Dict.

Not a test module (no ``test_`` prefix). The deploy tests import it.
"""
from typing import Any, Dict, List, Optional

from shared.store import ABSENT


class NotFoundError(Exception):
    """Same class name modal.exception uses for a Dict that does not exist."""


class FakeDict(dict):
    """What ModalDictStore keeps in ``_dict``: iterable keys() and items().
    ``missing`` makes both raise NotFoundError, like a Dict never created."""

    missing = False

    def keys(self):
        if self.missing:
            raise NotFoundError("Dict not found")
        return super(FakeDict, self).keys()

    def items(self):
        if self.missing:
            raise NotFoundError("Dict not found")
        return super(FakeDict, self).items()


class FakeModalStore(object):
    """ModalDictStore's surface over a plain dict. ``read_only=True`` makes any
    write raise, which is how the read-only scripts are proven read-only.
    ``missing=True`` behaves like a Dict that was never created."""

    def __init__(self, data: Optional[Dict[str, Any]] = None, read_only: bool = False, missing: bool = False):
        self._dict = FakeDict(data or {})
        self._dict.missing = missing
        self.read_only = read_only
        self.missing = missing
        self.writes = []  # type: List[Any]

    def _check_exists(self):
        if self.missing:
            raise NotFoundError("Dict not found")

    def _check_write(self, what):
        if self.read_only:
            raise AssertionError("read-only store written: %s" % (what,))
        self.writes.append(what)

    # reads
    def get(self, key: str, default: Any = None) -> Any:
        self._check_exists()
        return self._dict.get(key, default)

    def keys(self, prefix: str = "") -> List[str]:
        self._check_exists()
        return sorted(k for k in dict.keys(self._dict) if k.startswith(prefix) and not k.startswith("__lock__:"))

    def items(self, prefix: str = ""):
        for key in self.keys(prefix):
            yield key, self._dict[key]

    # writes
    def set(self, key: str, value: Any) -> None:
        self._check_write(("set", key))
        self._dict[key] = value

    def delete(self, key: str) -> None:
        self._check_write(("delete", key))
        self._dict.pop(key, None)

    def set_if_absent(self, key: str, value: Any) -> bool:
        self._check_write(("set_if_absent", key))
        if key in self._dict:
            return False
        self._dict[key] = value
        return True

    def append(self, key, item):
        self._check_write(("append", key))
        self._dict.setdefault(key, []).append(item)
        return self._dict[key]

    def add_once(self, key, item):
        self._check_write(("add_once", key))
        current = self._dict.setdefault(key, [])
        if item in current:
            return False
        current.append(item)
        return True

    def mutate(self, key, fn, default=None):
        self._check_write(("mutate", key))
        self._dict[key] = fn(self._dict.get(key, default))
        return self._dict[key]

    def compare_and_set(self, key, expected, value):
        self._check_write(("compare_and_set", key))
        present = key in self._dict
        if expected is ABSENT:
            if present:
                return False
        elif not present or self._dict[key] != expected:
            return False
        self._dict[key] = value
        return True
