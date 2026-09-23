"""load_env() never takes the live gate flags from a dotenv file (SAF-3, Slice 4a).

A write to .env must not be enough to go live: MODE and ALLOW_LIVE_WRITES
are read from the process environment only. The dotenv files here are temp
files with fake values, never the real .env.
"""
import logging
import os

import conftest
from shared import settings

SENTINEL_ALLOW = "allow-value-sentinel-8731"
SENTINEL_MODE = "live"


def _dotenv(tmp_path, name="gate.env", extra=""):
    path = tmp_path / name
    path.write_text("MODE=%s\nALLOW_LIVE_WRITES=%s\nGATE_TEST_OTHER_KEY=kept\n%s"
                    % (SENTINEL_MODE, SENTINEL_ALLOW, extra), encoding="utf-8")
    return path


def _real_loader(monkeypatch):
    """Switch off the test-session skip and restore the real python-dotenv
    (conftest makes it a no-op), as test_isolation.py does for its control."""
    monkeypatch.setattr(settings, "running_under_pytest", lambda: False)
    monkeypatch.setattr(settings, "load_dotenv", conftest._real_load_dotenv)


def _clear(monkeypatch):
    for key in ("MODE", "ALLOW_LIVE_WRITES", "GATE_TEST_OTHER_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_the_gate_flags_are_one_constant():
    assert settings.GATE_FLAGS == ("MODE", "ALLOW_LIVE_WRITES")


def test_a_file_cannot_set_the_gate_flags(tmp_path, monkeypatch, caplog):
    path = _dotenv(tmp_path)
    _clear(monkeypatch)
    _real_loader(monkeypatch)
    try:
        with caplog.at_level(logging.WARNING, logger="shared.settings"):
            assert settings.load_env([path]) == [str(path)]
        assert os.environ.get("GATE_TEST_OTHER_KEY") == "kept", "ordinary keys still load"
        assert "MODE" not in os.environ
        assert "ALLOW_LIVE_WRITES" not in os.environ
        assert settings.get_mode() == "shadow"
        assert settings.is_live() is False
    finally:
        os.environ.pop("GATE_TEST_OTHER_KEY", None)
        os.environ.pop("MODE", None)
        os.environ.pop("ALLOW_LIVE_WRITES", None)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "ignored MODE" in text and "ignored ALLOW_LIVE_WRITES" in text
    assert SENTINEL_ALLOW not in text, "the warning must name the key, never its value"
    assert "MODE=live" not in text and "=%s" % SENTINEL_ALLOW not in text


def test_a_second_file_cannot_set_them_either(tmp_path, monkeypatch):
    first = tmp_path / "first.env"
    first.write_text("GATE_TEST_OTHER_KEY=kept\n", encoding="utf-8")
    second = _dotenv(tmp_path, "second.env")
    _clear(monkeypatch)
    _real_loader(monkeypatch)
    try:
        assert settings.load_env([first, second]) == [str(first), str(second)]
        assert "MODE" not in os.environ and "ALLOW_LIVE_WRITES" not in os.environ
    finally:
        for key in ("GATE_TEST_OTHER_KEY", "MODE", "ALLOW_LIVE_WRITES"):
            os.environ.pop(key, None)


def test_process_environment_values_still_work(tmp_path, monkeypatch):
    """A value already in the process (the Modal secret, Lorenzo's terminal)
    is kept, and the file cannot change it."""
    path = _dotenv(tmp_path)
    _clear(monkeypatch)
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "0")
    _real_loader(monkeypatch)
    try:
        settings.load_env([path])
        assert os.environ["MODE"] == "shadow"
        assert os.environ["ALLOW_LIVE_WRITES"] == "0"
    finally:
        os.environ.pop("GATE_TEST_OTHER_KEY", None)


def test_process_live_flags_are_not_removed(tmp_path, monkeypatch):
    path = tmp_path / "plain.env"
    path.write_text("GATE_TEST_OTHER_KEY=kept\nMODE=shadow\n", encoding="utf-8")
    _clear(monkeypatch)
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    _real_loader(monkeypatch)
    try:
        settings.load_env([path])
        assert os.environ["MODE"] == "live" and os.environ["ALLOW_LIVE_WRITES"] == "1"
        assert settings.is_live() is True
    finally:
        os.environ.pop("GATE_TEST_OTHER_KEY", None)


def test_no_warning_when_the_file_has_no_gate_flag(tmp_path, monkeypatch, caplog):
    path = tmp_path / "clean.env"
    path.write_text("GATE_TEST_OTHER_KEY=kept\n", encoding="utf-8")
    _clear(monkeypatch)
    _real_loader(monkeypatch)
    try:
        with caplog.at_level(logging.WARNING, logger="shared.settings"):
            settings.load_env([path])
    finally:
        os.environ.pop("GATE_TEST_OTHER_KEY", None)
    assert not [r for r in caplog.records if "ignored" in r.getMessage()]


def test_under_pytest_nothing_is_read_at_all(tmp_path, monkeypatch):
    path = _dotenv(tmp_path)
    _clear(monkeypatch)
    assert settings.load_env([path]) == []
    assert "GATE_TEST_OTHER_KEY" not in os.environ and "MODE" not in os.environ
