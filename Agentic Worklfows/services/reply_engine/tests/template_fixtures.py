"""Test helpers for the CT3 template gate. A helper module, NOT a conftest:
nothing here runs unless a test asks for it.

    from services.reply_engine.tests.template_fixtures import template_env, template_env_ladders  # noqa: F401

    def test_x(template_env):
        template_env.approve_ids("cadence.d1")
        template_env.kill_switch(True)             # "auto_send": false in the tmp file
        template_env.kill_switch(True, via="env")  # AUTO_SEND_TEMPLATES=0

``make_template_env`` is the factory both fixtures use:

- ``ta.APPROVALS_PATH`` points at a tmp approvals file (empty, or with every
  approvable cadence, show_rate and no_show id approved at its current hash
  when ``approve_ladders=True``);
- a parity reference matching the current catalogue is written to tmp and
  ``template_gate.PARITY_REFERENCE_PATH`` points at it;
- ``AUTO_SEND_TEMPLATES`` is removed from the environment;
- both catalogue caches are cleared.

It never touches config/approved_templates.json or
config/template_catalogue_hashes.json: every write goes to the tmp paths, and
the helpers refuse a path under the real config/ directory.

The module-level ``approve_ids`` / ``revoke_ids`` / ``kill_switch`` act on
whatever ``ta.APPROVALS_PATH`` points at now, and refuse the real file.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from shared.paths import BASE_DIR

from services.reply_engine import template_approvals as ta
from services.reply_engine import template_gate as gate

REAL_CONFIG = (BASE_DIR / "config").resolve()
TEST_APPROVER = "test-fixture"


def _refuse_real(path: Any) -> Path:
    p = Path(path)
    if p.resolve().parent == REAL_CONFIG:
        raise AssertionError("template_fixtures refuses to write under the real config/ directory: %s" % p)
    return p


def _load(path: Path) -> Dict[str, Any]:
    return ta.load_approvals(path)


def approve_ids(*ids: str, path: Optional[Any] = None) -> None:
    """Approve ``ids`` at their current hash in the (tmp) approvals file."""
    p = _refuse_real(path if path is not None else ta.APPROVALS_PATH)
    approvals = _load(p)
    plan = ta.plan_approve(list(ids), ta.catalogue_index(), approvals)
    ta.save_approvals(ta.apply_approve(plan, approvals, TEST_APPROVER), p)


def revoke_ids(*ids: str, path: Optional[Any] = None) -> None:
    """Remove ``ids`` from the (tmp) approvals file; unknown ids are ignored."""
    p = _refuse_real(path if path is not None else ta.APPROVALS_PATH)
    approvals = _load(p)
    ta.save_approvals(ta.apply_revoke([i for i in ids if i in (approvals.get("approvals") or {})], approvals), p)


def kill_switch(on: bool = True, path: Optional[Any] = None) -> None:
    """File kill switch: ``"auto_send": false`` in the (tmp) approvals file
    (on), or the key removed (off)."""
    p = _refuse_real(path if path is not None else ta.APPROVALS_PATH)
    approvals = _load(p)
    if on:
        approvals["auto_send"] = False
    else:
        approvals.pop("auto_send", None)
    ta.save_approvals(approvals, p)


def write_reference(path: Any) -> Dict[str, Any]:
    """A parity reference matching the current catalogue, at a tmp path."""
    p = _refuse_real(path)
    rec = gate.reference_record()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec


class TemplateEnv(object):
    def __init__(self, monkeypatch: Any, approvals_path: Path, reference_path: Path) -> None:
        self.monkeypatch = monkeypatch
        self.approvals_path = approvals_path
        self.reference_path = reference_path

    def approve_ids(self, *ids: str) -> None:
        approve_ids(*ids, path=self.approvals_path)

    def revoke_ids(self, *ids: str) -> None:
        revoke_ids(*ids, path=self.approvals_path)

    def approve_ladders(self) -> None:
        self.approve_ids(*gate.ladder_ids())

    def kill_switch(self, on: bool = True, via: str = "file") -> None:
        if via == "env":
            if on:
                self.monkeypatch.setenv(ta.KILL_SWITCH_ENV, "0")
            else:
                self.monkeypatch.delenv(ta.KILL_SWITCH_ENV, raising=False)
            return
        kill_switch(on, path=self.approvals_path)

    def write_reference(self) -> Dict[str, Any]:
        rec = write_reference(self.reference_path)
        gate.clear_cache()
        return rec


def make_template_env(monkeypatch: Any, tmp_path: Any, approve_ladders: bool = False) -> TemplateEnv:
    base = Path(tmp_path) / "template_gate"
    base.mkdir(parents=True, exist_ok=True)
    approvals_path = _refuse_real(base / "approved_templates.json")
    reference_path = _refuse_real(base / "template_catalogue_hashes.json")
    monkeypatch.setattr(ta, "APPROVALS_PATH", approvals_path)
    monkeypatch.setattr(gate, "PARITY_REFERENCE_PATH", reference_path)
    monkeypatch.delenv(ta.KILL_SWITCH_ENV, raising=False)
    gate.clear_cache()
    ta.save_approvals(ta.empty_approvals(), approvals_path)
    env = TemplateEnv(monkeypatch, approvals_path, reference_path)
    env.write_reference()
    if approve_ladders:
        env.approve_ladders()
    return env


@pytest.fixture
def template_env(monkeypatch, tmp_path):
    env = make_template_env(monkeypatch, tmp_path)
    yield env
    gate.clear_cache()


@pytest.fixture
def template_env_ladders(monkeypatch, tmp_path):
    env = make_template_env(monkeypatch, tmp_path, approve_ladders=True)
    yield env
    gate.clear_cache()
