import json
import os

import pytest

from shared import store as store_mod
from shared.store import ABSENT, JsonFileStore, StoreError, get_store


def test_get_set_delete_keys(tmp_path):
    s = JsonFileStore(tmp_path / "state" / "store.json")
    assert s.get("missing") is None
    assert s.get("missing", {"d": 1}) == {"d": 1}
    s.set("lead:a", {"status": "new"})
    s.set("lead:b", {"status": "booked"})
    s.set("other", 5)
    assert s.get("lead:a") == {"status": "new"}
    assert s.keys("lead:") == ["lead:a", "lead:b"]
    assert s.keys() == ["lead:a", "lead:b", "other"]
    s.delete("lead:a")
    s.delete("never-there")  # no error
    assert s.keys("lead:") == ["lead:b"]


def test_append_creates_and_extends(tmp_path):
    s = JsonFileStore(tmp_path / "store.json")
    assert s.append("offered:2026-09-22", "2026-09-22T14:00:00-05:00") == ["2026-09-22T14:00:00-05:00"]
    s.append("offered:2026-09-22", "2026-09-22T15:30:00-05:00")
    assert s.get("offered:2026-09-22") == ["2026-09-22T14:00:00-05:00", "2026-09-22T15:30:00-05:00"]
    s.set("scalar", "x")
    assert s.append("scalar", "y") == ["x", "y"]


def test_persists_across_instances_and_is_valid_json(tmp_path):
    path = tmp_path / "store.json"
    JsonFileStore(path).set("k", {"n": 1})
    assert JsonFileStore(path).get("k") == {"n": 1}
    with open(path) as fh:
        assert json.load(fh) == {"k": {"n": 1}}


def test_atomic_write_leaves_no_temp_files(tmp_path):
    s = JsonFileStore(tmp_path / "store.json")
    for i in range(20):
        s.set("k%d" % i, i)
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []
    assert set(os.listdir(tmp_path)) == {"store.json", "store.json.lock"}


def test_corrupt_file_raises_and_is_quarantined_instead_of_reading_as_empty(tmp_path):
    """A truncated store read as {} erases every appointment schedule and
    recovery record, and the next tick re-sends every touch in the window. The
    read must fail loudly and leave the bad bytes on disk for inspection."""
    path = tmp_path / "store.json"
    path.write_text("{not json")
    s = JsonFileStore(path)
    with pytest.raises(StoreError) as exc:
        s.get("k")
    assert "corrupt" in str(exc.value)
    corrupt = list(tmp_path.glob("store.json.corrupt-*"))
    assert len(corrupt) == 1 and corrupt[0].read_text() == "{not json"
    # the bad file was moved aside, so the next run starts clean rather than silently
    assert s.get("k") is None
    s.set("k", 1)
    assert s.get("k") == 1


def test_mutate_holds_one_lock_across_read_and_write(tmp_path):
    s = JsonFileStore(tmp_path / "store.json")
    s.set("rec", {"touches": [1]})

    def add_two(current):
        current = dict(current or {})
        current["touches"] = list(current.get("touches") or []) + [2]
        return current

    assert s.mutate("rec", add_two) == {"touches": [1, 2]}
    assert s.get("rec") == {"touches": [1, 2]}
    assert s.mutate("fresh", lambda cur: (cur or 0) + 1, default=10) == 11


def test_compare_and_set_refuses_a_value_that_moved_under_it(tmp_path):
    s = JsonFileStore(tmp_path / "store.json")
    assert s.compare_and_set("k", ABSENT, {"v": 1}) is True
    assert s.compare_and_set("k", ABSENT, {"v": 2}) is False
    assert s.compare_and_set("k", {"v": 9}, {"v": 3}) is False
    assert s.compare_and_set("k", {"v": 1}, {"v": 3}) is True
    assert s.get("k") == {"v": 3}


def test_get_store_picks_json_file_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME", "local")
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "s.json"))
    s = get_store(force_new=True)
    assert isinstance(s, JsonFileStore)
    assert s.path == tmp_path / "s.json"
    assert get_store() is s  # cached while the target is unchanged
    store_mod._STORE = None
    store_mod._STORE_KEY = None


def test_get_store_cache_follows_a_changed_store_path(tmp_path, monkeypatch):
    """A job that sets STORE_PATH after importing shared, or a test using the
    tmp_env fixture, must not read and write the store built on the first call."""
    monkeypatch.setenv("RUNTIME", "local")
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "first.json"))
    first = get_store(force_new=True)
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "second.json"))
    second = get_store()
    assert second is not first
    assert second.path == tmp_path / "second.json"
    store_mod._STORE = None
    store_mod._STORE_KEY = None


# ------------------------------------------------------------- atomic claim
def test_set_if_absent_claims_once(tmp_path):
    s = JsonFileStore(tmp_path / "store.json")
    assert s.set_if_absent("processed:reply-1", {"by": "poller"}) is True
    assert s.set_if_absent("processed:reply-1", {"by": "webhook"}) is False
    assert s.get("processed:reply-1") == {"by": "poller"}


def test_add_once_never_double_offers_a_slot(tmp_path):
    s = JsonFileStore(tmp_path / "store.json")
    assert s.add_once("offered:2026-09-22", "2026-09-22T14:00:00-05:00") is True
    assert s.add_once("offered:2026-09-22", "2026-09-22T14:00:00-05:00") is False
    assert s.add_once("offered:2026-09-22", "2026-09-22T15:30:00-05:00") is True
    assert s.get("offered:2026-09-22") == ["2026-09-22T14:00:00-05:00", "2026-09-22T15:30:00-05:00"]


def _claim_child(path, key, out_path):
    """Run in a forked child: claim the key and report whether we won."""
    store = JsonFileStore(path)
    won = store.set_if_absent(key, {"pid": os.getpid()})
    with open(out_path, "w") as fh:
        fh.write("1" if won else "0")


def test_claim_once_is_atomic_under_concurrent_writers(tmp_path):
    """Two Modal containers (or the webhook and the poller) can see the same
    reply id at the same time. get-then-set lets both claim it and both send;
    exactly one may win."""
    import multiprocessing as mp

    path = str(tmp_path / "store.json")
    JsonFileStore(path).set("warm", 1)  # create the file before the race
    ctx = mp.get_context("fork")
    results = [str(tmp_path / "a.txt"), str(tmp_path / "b.txt")]
    procs = [ctx.Process(target=_claim_child, args=(path, "processed:reply-1", out)) for out in results]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    won = [open(p).read() for p in results]
    assert sorted(won) == ["0", "1"], "exactly one writer may claim the key, got %r" % won


def _append_child(path, key, item):
    JsonFileStore(path).add_once(key, item)


def test_concurrent_appends_never_lose_a_reservation(tmp_path):
    import multiprocessing as mp

    path = str(tmp_path / "store.json")
    JsonFileStore(path).set("warm", 1)
    ctx = mp.get_context("fork")
    items = ["2026-09-22T14:00:00-05:00", "2026-09-22T15:00:00-05:00", "2026-09-22T16:00:00-05:00"]
    procs = [ctx.Process(target=_append_child, args=(path, "offered:2026-09-22", i)) for i in items]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    assert sorted(JsonFileStore(path).get("offered:2026-09-22")) == sorted(items)


def test_get_store_modal_uses_lazy_import(monkeypatch):
    """RUNTIME=modal constructs ModalDictStore; we stub the modal module."""
    import sys
    import types

    calls = {}

    fake_modal = types.ModuleType("modal")
    fake_modal.Dict = _make_fake_dict(calls)
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    monkeypatch.setenv("RUNTIME", "modal")
    monkeypatch.setenv("MODAL_DICT_NAME", "advero-test")
    s = get_store(force_new=True)
    assert calls["name"] == "advero-test"
    s.set("a", {"x": 1})
    s.append("l", 1)
    s.append("l", 2)
    assert s.get("a") == {"x": 1}
    assert s.get("l") == [1, 2]
    assert s.keys() == ["a", "l"]
    s.delete("a")
    assert s.get("a") is None
    store_mod._STORE = None
    store_mod._STORE_KEY = None


def _make_fake_dict(calls=None):
    """Stand-in for modal.Dict, including the atomic put(skip_if_exists=True)
    that ModalDictStore builds its lock on."""

    class FakeDict(dict):
        @classmethod
        def from_name(cls, name, create_if_missing=True):
            if calls is not None:
                calls["name"] = name
            return cls()

        def put(self, key, value, skip_if_exists=False):
            if skip_if_exists and key in self:
                return False
            self[key] = value
            return True

    return FakeDict


def _modal_store(monkeypatch, calls=None):
    import sys
    import types

    fake_modal = types.ModuleType("modal")
    fake_modal.Dict = _make_fake_dict(calls)
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    from shared.store import ModalDictStore

    return ModalDictStore("advero-test")


def test_modal_store_claim_is_atomic_and_releases_its_lock(monkeypatch):
    s = _modal_store(monkeypatch)
    assert s.set_if_absent("processed:reply-1", {"by": "poller"}) is True
    assert s.set_if_absent("processed:reply-1", {"by": "webhook"}) is False
    assert s.add_once("offered:2026-09-22", "14:00") is True
    assert s.add_once("offered:2026-09-22", "14:00") is False
    assert s.add_once("offered:2026-09-22", "15:30") is True
    assert s.get("offered:2026-09-22") == ["14:00", "15:30"]
    # the lock keys are released and never leak into keys()
    assert s.keys() == ["offered:2026-09-22", "processed:reply-1"]
    assert not [k for k in s._dict.keys() if str(k).startswith(s.LOCK_PREFIX)]


def test_modal_store_breaks_a_stale_lock(monkeypatch):
    s = _modal_store(monkeypatch)
    s._dict[s.LOCK_PREFIX + "offered:x"] = {"at": 0, "pid": 1}  # held since the epoch
    assert s.add_once("offered:x", "14:00") is True


def test_modal_store_raises_rather_than_racing_when_the_lock_is_held(monkeypatch):
    s = _modal_store(monkeypatch)
    monkeypatch.setattr(type(s), "LOCK_TIMEOUT_SECONDS", 0.1)
    import time as _time

    s._dict[s.LOCK_PREFIX + "offered:x"] = {"at": _time.time(), "pid": 999}
    with pytest.raises(StoreError):
        s.add_once("offered:x", "14:00")
