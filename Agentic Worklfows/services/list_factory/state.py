"""Resumable run state.

One run = one directory under ``.tmp/list_factory/runs/<run_id>/`` holding
``state.json`` (through ``shared.store.JsonFileStore``, so the write is atomic
tmp+rename under an fcntl lock) and the staged CSVs.

Why a single key rather than one key per lead: ``JsonFileStore`` rewrites the
whole file on every ``set``, so 3,300 per-lead writes would rewrite a 3 MB file
3,300 times. The run holds its leads in memory and checkpoints the whole list
as one atomic write at stage boundaries and every ``checkpoint_every`` leads
inside the paid stages, which is where a crash actually costs money.
"""
import binascii
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from shared.paths import tmp_dir
from shared.store import JsonFileStore

from services.list_factory import models

logger = logging.getLogger("list_factory.state")

STATE_KEY = "state"
DEFAULT_CHECKPOINT_EVERY = 25


_RUNS_DIR_OVERRIDE = None  # type: Optional[str]


def use_runs_dir(path: Optional[str]) -> Optional[str]:
    """Point run state at ``path`` (None restores the default). Returns the
    previous override so the caller can put it back.

    ``jobs/list_factory.py --dry-run`` keeps its run state in its scratch
    directory with this: a dry run used to adopt an open REAL run from the
    shared runs directory, verify its paid leads with the replay verifier,
    write a staged CSV into it and close it as ok (re-review 2).
    """
    global _RUNS_DIR_OVERRIDE
    previous = _RUNS_DIR_OVERRIDE
    _RUNS_DIR_OVERRIDE = path
    return previous


def runs_dir() -> str:
    path = _RUNS_DIR_OVERRIDE or os.path.join(str(tmp_dir()), "list_factory", "runs")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def new_run_id(niche: str, now: Optional[datetime] = None) -> str:
    """A run id that cannot collide with another run started the same second.

    The bare timestamp was second-granular, so an at-least-once scheduler that
    fired the job twice inside the same minute produced the SAME id twice, and
    ``RunState.create`` then reset ``leads`` to [] on the existing directory:
    the first run's state and its resumability were gone with no error. The
    four-character suffix makes the id unique; ``create`` refusing to overwrite
    makes the loss impossible even if it somehow were not.
    """
    now = now or datetime.now(timezone.utc)
    suffix = binascii.hexlify(os.urandom(2)).decode("ascii")
    return "%s_%s_%s" % (models.slug(niche) or "run", now.strftime("%Y%m%d_%H%M%S"), suffix)


def run_dir(run_id: str) -> str:
    path = os.path.join(runs_dir(), run_id)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def list_runs() -> List[str]:
    try:
        return sorted(
            name for name in os.listdir(runs_dir())
            if os.path.isfile(os.path.join(runs_dir(), name, "state.json"))
        )
    except OSError:
        return []


def run_meta(run_id: str) -> Dict[str, Any]:
    """The run's meta block without loading its leads. {} when unreadable."""
    path = os.path.join(runs_dir(), run_id, "state.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh) or {}
    except (OSError, IOError, ValueError):
        return {}
    payload = blob.get(STATE_KEY)
    payload = payload if isinstance(payload, dict) else blob
    meta = payload.get("meta")
    return meta if isinstance(meta, dict) else {}


def find_open_run(niche: str) -> Optional[str]:
    """The newest unfinished run for ``niche``, or None.

    An unattended Sunday job that dies mid-verify and is re-fired by an
    at-least-once scheduler used to start from ``source`` and pay for the whole
    pipeline a second time. Resuming the open run instead is the difference
    between a retry and a second $46 bill.
    """
    candidates = []
    for run_id in list_runs():
        meta = run_meta(run_id)
        if (meta.get("status") or "open") != "open":
            continue
        if models.slug(meta.get("niche") or "") != models.slug(niche):
            continue
        candidates.append((meta.get("updated_utc") or meta.get("created_utc") or "", run_id))
    if not candidates:
        return None
    return sorted(candidates)[-1][1]


class RunState(object):
    """The run's leads, its stage cursor and its ledger, persisted together.

    ``meta`` carries the run parameters and ``stages_done``; ``leads`` is the
    list. Everything a resumed run needs is in the one file, so a resume never
    has to re-read a source (and never re-pays a source fee).
    """

    def __init__(self, run_id: str, path: Optional[str] = None, checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY):
        self.run_id = run_id
        self.dir = run_dir(run_id) if path is None else os.path.dirname(os.path.abspath(path))
        self.path = path or os.path.join(self.dir, "state.json")
        self.store = JsonFileStore(self.path)
        self.checkpoint_every = max(1, int(checkpoint_every))
        self.meta = {}  # type: Dict[str, Any]
        self.leads = []  # type: List[Dict[str, Any]]
        self._since_checkpoint = 0
        self._ledger_snapshot = None  # type: Optional[Callable[[], Dict[str, Any]]]

    # ------------------------------------------------------------- lifecycle
    def bind_ledger(self, ledger: Any) -> None:
        """Persist the ledger with every checkpoint.

        Writing ``meta['ledger']`` only after the stage loop meant a run that
        was actually killed (kill -9, OOM, power) left a state file with no
        ledger at all, and ``--resume`` seeded a fresh Ledger with $0: the
        cost cap restarted on every resume, which is the one failure the cap
        exists to prevent. The snapshot now rides along with the leads, under
        the same atomic write.
        """
        self._ledger_snapshot = getattr(ledger, "snapshot", None)

    @classmethod
    def create(cls, run_id: str, meta: Dict[str, Any], checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY,
               overwrite: bool = False) -> "RunState":
        state = cls(run_id, checkpoint_every=checkpoint_every)
        if not overwrite and os.path.exists(state.path) and os.path.getsize(state.path) > 0:
            raise RunStateError(
                "run %s already exists at %s; creating it again would reset its leads to [] and "
                "throw away everything the first pass paid for. Resume it instead." % (run_id, state.path)
            )
        state.meta = dict(meta)
        state.meta.setdefault("run_id", run_id)
        state.meta.setdefault("created_utc", datetime.now(timezone.utc).replace(microsecond=0).isoformat())
        state.meta.setdefault("stages_done", [])
        state.meta.setdefault("status", "open")
        state.leads = []
        state.checkpoint(force=True)
        return state

    @classmethod
    def load(cls, run_id: str, checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY) -> "RunState":
        state = cls(run_id, checkpoint_every=checkpoint_every)
        blob = state.store.get(STATE_KEY)
        if not isinstance(blob, dict):
            raise RunStateError("no resumable state at %s" % state.path)
        state.meta = blob.get("meta") or {}
        state.leads = blob.get("leads") or []
        state.meta.setdefault("stages_done", [])
        return state

    @classmethod
    def load_or_create(cls, run_id: str, meta: Dict[str, Any], checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY) -> "RunState":
        try:
            return cls.load(run_id, checkpoint_every=checkpoint_every)
        except RunStateError:
            return cls.create(run_id, meta, checkpoint_every=checkpoint_every)

    # --------------------------------------------------------------- writing
    def checkpoint(self, force: bool = False) -> bool:
        """Persist. Returns True when it actually wrote."""
        self._since_checkpoint += 0 if force else 1
        if not force and self._since_checkpoint < self.checkpoint_every:
            return False
        self._since_checkpoint = 0
        self.meta["updated_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        if self._ledger_snapshot is not None:
            try:
                self.meta["ledger"] = self._ledger_snapshot()
            except Exception as exc:  # noqa: BLE001 - a ledger problem must not lose the leads
                logger.warning("could not snapshot the ledger into run %s: %s", self.run_id, exc)
        try:
            self.store.set(STATE_KEY, {"meta": self.meta, "leads": self.leads})
            return True
        except Exception as exc:  # noqa: BLE001 - a checkpoint failure must be loud but not fatal
            logger.error("checkpoint failed for run %s (%s): a crash now loses this stage", self.run_id, exc)
            return False

    def tick(self, n: int = 1) -> None:
        """Count n leads of paid work; checkpoint when the budget of
        unsaved work is used up."""
        self._since_checkpoint += n
        if self._since_checkpoint >= self.checkpoint_every:
            self.checkpoint(force=True)

    def mark_stage_done(self, stage: str) -> None:
        done = self.meta.setdefault("stages_done", [])
        if stage not in done:
            done.append(stage)
        self.checkpoint(force=True)

    def stage_done(self, stage: str) -> bool:
        return stage in (self.meta.get("stages_done") or [])

    def close(self, status: str) -> None:
        self.meta["status"] = status
        self.meta["closed_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self.checkpoint(force=True)

    # --------------------------------------------------------------- reading
    def add_leads(self, leads: List[Dict[str, Any]]) -> int:
        """Merge new source rows in, skipping keys the run already holds."""
        known = set(lead.get("lead_key") for lead in self.leads)
        added = 0
        for lead in leads:
            key = lead.get("lead_key") or models.lead_key(lead)
            if key in known:
                continue
            known.add(key)
            self.leads.append(lead)
            added += 1
        return added

    def pending(self, stage: str) -> List[Dict[str, Any]]:
        """Leads this stage still has to do (resume is exactly this call).

        A held lead (paid gate closed, verifier erroring) is skipped for the
        rest of THIS pass but stays pending for the next one: ``release_holds``
        clears the flag at the start of every pass, so "rehearse, then open the
        gate and resume" picks the lead up from exactly where it stopped.
        """
        return [
            lead for lead in self.leads
            if not models.is_rejected(lead)
            and not models.is_held(lead)
            and not models.stage_at_least(lead, stage)
        ]

    def held(self) -> List[Dict[str, Any]]:
        return [lead for lead in self.leads if models.is_held(lead)]

    def release_holds(self) -> int:
        """Clear every hold so this pass re-attempts them. Returns how many."""
        return sum(1 for lead in self.leads if models.release(lead))

    def at_least(self, stage: str) -> List[Dict[str, Any]]:
        return [lead for lead in self.leads if not models.is_rejected(lead) and models.stage_at_least(lead, stage)]

    def rejected(self) -> List[Dict[str, Any]]:
        return [lead for lead in self.leads if models.is_rejected(lead)]

    def counts(self) -> Dict[str, int]:
        out = {}  # type: Dict[str, int]
        for lead in self.leads:
            key = lead.get("stage") or models.SOURCED
            if key == models.REJECTED:
                key = "rejected:%s" % (lead.get("reject_reason") or "unknown")
            elif models.is_held(lead):
                # A held lead is not finished and not pending; reporting it as
                # its stage would hide a run that produced nothing because the
                # gate was shut.
                key = "held:%s" % lead.get("blocked_by_gate")
            out[key] = out.get(key, 0) + 1
        return out

    def artifact(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<RunState %s leads=%d stages_done=%s>" % (
            self.run_id, len(self.leads), self.meta.get("stages_done"),
        )


class RunStateError(Exception):
    pass


def write_json(path: str, payload: Any) -> str:
    """Atomic JSON artifact beside the state file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str, ensure_ascii=False)
    os.replace(tmp, path)
    return path
