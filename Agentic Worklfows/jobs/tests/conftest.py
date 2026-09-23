"""CT3 template gate for the jobs tests: the same autouse ``approvals_file``
fixture and ``legacy_ungated`` marker as services/reply_engine/tests/conftest.py
(see its docstring). Every test gets a per-test STORE_PATH and a tmp approvals
file with every cadence, show_rate and no_show id approved at its current
hash; first-reply and booking ids stay unapproved.
"""
import pytest

from services.reply_engine import template_gate as gate
from services.reply_engine.tests.conftest import (LEGACY_MARKER, install_template_env, restore_root_conftest,
                                                  ungate)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "%s: the CT3 template gate allows everything in this test (tests that swap templates on "
                   "purpose; there is no engine switch for this)" % LEGACY_MARKER)
    restore_root_conftest(config)  # changesets/tests import the root conftest by name


@pytest.fixture(autouse=True)
def approvals_file(monkeypatch, tmp_path_factory, request):
    # A directory of its own, not the test's tmp_path: some tests assert
    # their tmp_path holds only what they wrote.
    own = tmp_path_factory.mktemp("ct3")
    monkeypatch.setenv("STORE_PATH", str(own / "store.json"))
    env = install_template_env(monkeypatch, own)
    if request.node.get_closest_marker(LEGACY_MARKER) is not None:
        ungate(monkeypatch)
    yield env
    gate.clear_cache()
