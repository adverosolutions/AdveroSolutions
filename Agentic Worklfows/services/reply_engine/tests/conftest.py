"""CT3 template gate for the reply-engine tests (jobs/tests/conftest.py reuses it).

Every test runs with:

- a per-test STORE_PATH (store.json in a per-test directory of its own);
- ``ta.APPROVALS_PATH`` pointing at a tmp approvals file that approves every
  approvable cadence, show_rate and no_show id at its current hash, so the
  ladders send as they did before CT3. First-reply and booking ids stay
  unapproved, so every card test keeps today's behaviour (a card, never an
  auto-send);
- ``template_gate.PARITY_REFERENCE_PATH`` pointing at a tmp parity reference
  that matches the catalogue;
- ``AUTO_SEND_TEMPLATES`` removed from the environment (kill switch off).

It is ``template_fixtures.make_template_env(monkeypatch, tmp_path,
approve_ladders=True)``, except that the catalogue work (the reference record
and the ladder approvals) is done once per session and only the two files are
written per test. The fixture yields the ``template_fixtures.TemplateEnv``, so
a test can ask for ``approvals_file`` and call ``approve_ids`` /
``revoke_ids`` / ``kill_switch`` on it.

It is named ``approvals_file`` on purpose: test_template_approvals.py defines
its own autouse ``approvals_file`` (an empty registry), and pytest's name
shadowing makes that one replace this one in that module.

``@pytest.mark.legacy_ungated``: for tests that swap templates on purpose
(a patched prompt, offer sheet or copy function), the gate's verdict
functions are replaced by ones that allow everything. Test-only: there is no
environment switch that does this in the engine.

Nothing here touches config/approved_templates.json or
config/template_catalogue_hashes.json.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

from services.reply_engine import template_approvals as ta
from services.reply_engine import template_gate as gate
from services.reply_engine.tests import template_fixtures as tf

LEGACY_MARKER = "legacy_ungated"
ROOT_CONFTEST = Path(__file__).resolve().parents[3] / "conftest.py"

# One catalogue computation per session, keyed on the catalogue's source key:
# a test that edits a source file gets its own (and then usually needs
# legacy_ungated, since the engine's text no longer matches the reference).
_SESSION_FILES = {}  # type: Dict[Any, Dict[str, str]]


def ladder_template_files() -> Dict[str, str]:
    """{"approvals": json, "reference": json}: every approvable ladder id
    approved at its current hash, and the parity reference for the current
    catalogue. Computed once per catalogue source key."""
    key = ta._source_key()
    got = _SESSION_FILES.get(key)
    if got is not None:
        return got
    gate.clear_cache()
    index = ta.catalogue_index()
    reference = gate.reference_record(index)
    empty = ta.empty_approvals()
    plan = ta.plan_approve(gate.ladder_ids(index), index, empty)
    approvals = ta.apply_approve(plan, ta.empty_approvals(), tf.TEST_APPROVER)
    got = {"approvals": json.dumps(approvals, indent=2, sort_keys=True) + "\n",
           "reference": json.dumps(reference, indent=2, sort_keys=True) + "\n"}
    _SESSION_FILES.clear()
    _SESSION_FILES[key] = got
    return got


def install_template_env(monkeypatch: Any, tmp_path: Any) -> "tf.TemplateEnv":
    """make_template_env(approve_ladders=True) with the session's catalogue work."""
    files = ladder_template_files()
    base = Path(tmp_path) / "template_gate"
    base.mkdir(parents=True, exist_ok=True)
    approvals_path = tf._refuse_real(base / "approved_templates.json")
    reference_path = tf._refuse_real(base / "template_catalogue_hashes.json")
    approvals_path.write_text(files["approvals"], encoding="utf-8")
    reference_path.write_text(files["reference"], encoding="utf-8")
    monkeypatch.setattr(ta, "APPROVALS_PATH", approvals_path)
    monkeypatch.setattr(gate, "PARITY_REFERENCE_PATH", reference_path)
    monkeypatch.delenv(ta.KILL_SWITCH_ENV, raising=False)
    gate.clear_cache()
    return tf.TemplateEnv(monkeypatch, approvals_path, reference_path)


def ungate(monkeypatch: Any) -> None:
    """legacy_ungated: every verdict allowed (test-only)."""
    def allowed(obj: Any = None) -> Any:
        template_id = obj if isinstance(obj, str) or obj is None else getattr(obj, "template_id", None)
        return gate.Verdict(True, "ok", template_id, [template_id] if template_id else [], {})

    monkeypatch.setattr(gate, "ids_verdict", lambda template_id, parts=(): allowed(template_id))
    monkeypatch.setattr(gate, "draft_verdict", lambda draft, **kw: allowed(draft))
    monkeypatch.setattr(gate, "touch_verdict", lambda touch, bindings=None: allowed(touch))
    monkeypatch.setattr(gate, "appointment_touch_verdict", lambda touch, **kw: allowed(touch))


def restore_root_conftest(config: Any) -> None:
    """Put the root Agentic Worklfows/conftest.py back as ``sys.modules["conftest"]``.

    The tests directories are not packages, so pytest imports every
    conftest.py there under the plain module name "conftest", dropping the
    root one from sys.modules first. changesets/tests (and shared/tests) then
    ``import conftest`` and got this file instead of the root one
    (``module 'conftest' has no attribute '_real_dotenv_values'``). pytest
    already holds this module as a plugin by the time pytest_configure runs
    for it, so the name can go back to the root conftest here."""
    root = Path(ROOT_CONFTEST).resolve()
    for plugin in config.pluginmanager.get_plugins():
        f = getattr(plugin, "__file__", None)
        if f and Path(f).resolve() == root:
            sys.modules["conftest"] = plugin
            return


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "%s: the CT3 template gate allows everything in this test (tests that swap templates on "
                   "purpose; there is no engine switch for this)" % LEGACY_MARKER)
    restore_root_conftest(config)


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
