"""GHL mirror for Upwork follow-up threads (U4; DESIGN.md "GHL mirror", "Stages"
and "GHL pipeline for Upwork (revised 2026-09-22 after the U4a review)").

Upwork has its OWN GHL pipeline, ``config/ids.json`` ``ghl.pipelines.upwork``
``{id, stages{key: id}}``, never the cold-email Sales pipeline (an email-less
Sales opportunity blocks pipeline_sync's nightly reverse check). Until Lorenzo
creates it and every id is filled in, the mirror is OFF: no write, no read,
and :func:`mirror_status` gives the single ``ghl_not_configured`` marker the
tick reports once per run (``sync_thread`` also returns it as its only error).
An Upwork id that another pipeline in ids.json already uses (its pipeline id
or any of its stage ids, Sales or not) also leaves the mirror off.

Two entry points, both called by the tick once per thread:

* :func:`read_back_stage` reads the thread's opportunity and returns the stage
  key Lorenzo set in GHL (by stage, or by a won / lost / abandoned status), or
  None. The caller applies it with ``sequence.apply_external_stage``. Call it
  BEFORE :func:`sync_thread`.
* :func:`sync_thread` creates the contact and opportunity once, then keeps the
  opportunity's stage equal to ``thread["stage"]``, and only that. A live stage
  write is made only while GHL still shows the stage the mirror last wrote
  (the opportunity is read first), so a move Lorenzo made in GHL is never
  overwritten, even when the read-back could not see it. The one exception,
  as in DESIGN "Stages", is ``won`` from a real contract: it is written over
  any stage in the Upwork pipeline, never into another pipeline.

``thread["ghl"]["stage"]`` means "the stage GHL is known to hold". It advances
only on a confirmed live write (a 2xx answer that is neither a ``{"succeded":
false}`` rejection nor an answer showing another stage, status or pipeline)
or when the opportunity id is a shadow placeholder, and
when a stage read from GHL is recorded. A shadow would-do against a real
opportunity, a failed or rejected write and a dry run leave it alone, so the
read-back can never mistake the mirror's own unconfirmed intent for a GHL move.

GHL's status decides the stage whatever the column: ``won`` and ``lost`` are
stages of their own, and ``abandoned`` (Lorenzo dropped the deal) reads as
``lost``, so a later push never reopens it as open.

A live stage write (PUT ``/opportunities/{id}``) whose answer shows a stage,
status or pipeline other than the one sent is ``ghl_write_rejected``, not a
success: the known stage does not advance and the next run tries again.

A GHL move is never overwritten, except by ``won`` from a real contract. When
Lorenzo moves a card in GHL and also runs ``--stage`` (or ``--resume``) before
the next run, the read-back applies GHL's stage and his CLI stage is replaced;
the tick says so in the batch so he can run ``--stage`` again. No GHL
timestamp is read to decide between the two.

Every write goes through ``shared.ghl`` (``guard_write``). In shadow the ids
GHL would return do not exist, so the thread stores placeholders
(``shadow:contact:<room_id>``, ``shadow:opportunity:<room_id>``): a shadow run
is idempotent, a placeholder is never read back, and a live run treats a
placeholder as "no id" and creates the real object. Shadow and dry runs make
no request at all.

A live create that answers without an id is reported as ``ghl_no_id_returned``
and marks the thread ``thread["ghl"]["blocked"]``: no further create (which
would duplicate the contact every run). From then on every sync of that
thread makes no request and returns one ``ghl_blocked`` error naming the room,
the reason, the stage waiting to be mirrored and the recovery step, until
Lorenzo fills the ids in and removes ``blocked`` by hand
(runbooks/upwork_followup.md, "GHL mirror recovery").

``sync_thread`` never raises for a GHL failure: each one is an ``errors`` entry.
"""
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared import ghl as ghl_client
from shared import settings

logger = logging.getLogger("services.upwork_followup.ghl_sync")

PIPELINE_KEY = "upwork"
STAGE_KEYS = ("new_reply", "proposal_sent", "call_booked", "follow_up_later", "won", "lost")
UPWORK_TAG = "upwork"
UPWORK_SOURCE = "Upwork"
SHADOW_PREFIX = "shadow:"
NAME_MAX = 100
RECOVERY_DOC = "runbooks/upwork_followup.md, GHL mirror recovery"

STAGE_ACTION = "ghl_stage"
STATUS_FOR_STAGE = {"won": "won", "lost": "lost"}  # every other stage is "open"
# A GHL status that decides the stage whatever the column. abandoned is
# Lorenzo dropping the deal: it reads as lost, never as open.
STAGE_FOR_STATUS = {"won": "won", "lost": "lost", "abandoned": "lost"}

# errors[] codes
NOT_CONFIGURED = "ghl_not_configured"
ERR_UNKNOWN_STAGE = "ghl_unknown_stage"
ERR_STAGE_MISMATCH = "ghl_stage_action_mismatch"
ERR_NO_CLIENT = "ghl_no_client_name"
ERR_NO_GHL = "ghl_client_missing"
ERR_NEEDS_IDENTITY = ghl_client.CONTACT_NEEDS_IDENTITY
ERR_WRITE_FAILED = "ghl_write_failed"
ERR_REJECTED = "ghl_write_rejected"
ERR_NO_ID = "ghl_no_id_returned"
ERR_BLOCKED = "ghl_blocked"
ERR_STAGE_CONFLICT = "ghl_stage_conflict"
ERR_READ_FAILED = "ghl_read_failed"


# ------------------------------------------------------------- pipeline config
def _id_value(value: Any) -> Optional[str]:
    """A stage entry is either the id string or ``{"id": ...}``."""
    if isinstance(value, dict):
        value = value.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _pipelines() -> Dict[str, Any]:
    ghl_ids = (settings.IDS or {}).get("ghl")
    pipelines = ghl_ids.get("pipelines") if isinstance(ghl_ids, dict) else None
    return pipelines if isinstance(pipelines, dict) else {}


def _taken_ids(pipelines: Dict[str, Any]) -> Dict[str, str]:
    """Every id another pipeline uses, as ``{id: where}``: the pipeline id and
    each stage id of every ``ghl.pipelines`` block other than Upwork, plus the
    Sales ids settings read at import (still there when a test patches IDS)."""
    taken = {}  # type: Dict[str, str]

    def add(value: Any, where: str) -> None:
        found = _id_value(value)
        if found:
            taken.setdefault(found, where)

    for name in sorted(pipelines):
        block = pipelines[name]
        if name == PIPELINE_KEY or not isinstance(block, dict):
            continue
        add(block.get("id"), "pipelines.%s.id" % name)
        stages = block.get("stages")
        if isinstance(stages, dict):
            for key in sorted(stages):
                add(stages[key], "pipelines.%s.stages.%s" % (name, key))
        elif isinstance(stages, list):
            for i, value in enumerate(stages):
                add(value, "pipelines.%s.stages[%d]" % (name, i))
    add(settings.GHL_SALES_PIPELINE_ID, "pipelines.sales.id")
    for key, value in sorted((settings.GHL_STAGES or {}).items()):
        add(value, "pipelines.sales.stages.%s" % key)
    return taken


def upwork_pipeline() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``({"id", "stages"}, None)`` when ``ghl.pipelines.upwork`` is fully
    configured, else ``(None, reason)``. Read from ``settings.IDS`` on every
    call. Refuses (as not configured) a pipeline or stage id that any other
    pipeline in ids.json already uses (its pipeline id or one of its stage
    ids: Sales, Sales Requests or any other), and the same id on two Upwork
    stages. Upwork opportunities must never land in another pipeline."""
    pipelines = _pipelines()
    conf = pipelines.get(PIPELINE_KEY)
    if not isinstance(conf, dict):
        return None, "config/ids.json has no ghl.pipelines.upwork block"
    pipeline_id = _id_value(conf.get("id"))
    if not pipeline_id:
        return None, "ghl.pipelines.upwork.id is not set (Lorenzo creates the Upwork pipeline in GHL first)"
    raw = conf.get("stages") if isinstance(conf.get("stages"), dict) else {}
    stages = {}  # type: Dict[str, str]
    missing = []
    for key in STAGE_KEYS:
        sid = _id_value(raw.get(key))
        if sid:
            stages[key] = sid
        else:
            missing.append(key)
    if missing:
        return None, "ghl.pipelines.upwork.stages has no id for: %s" % ", ".join(missing)
    taken = _taken_ids(pipelines)
    if pipeline_id in taken:
        return None, "ghl.pipelines.upwork.id equals %s; Upwork needs its own pipeline" % taken[pipeline_id]
    clash = ["%s (= %s)" % (key, taken[stages[key]]) for key in STAGE_KEYS if stages[key] in taken]
    if clash:
        return None, "ghl.pipelines.upwork stage ids belong to another pipeline: %s" % ", ".join(clash)
    ids = list(stages.values())
    dup = [key for key in STAGE_KEYS if ids.count(stages[key]) > 1]
    if dup:
        return None, "ghl.pipelines.upwork has the same id on two stages (%s)" % ", ".join(dup)
    own = [key for key in STAGE_KEYS if stages[key] == pipeline_id]
    if own:
        return None, "ghl.pipelines.upwork stage %s has the pipeline's own id" % ", ".join(own)
    return {"id": pipeline_id, "stages": stages}, None


def mirror_status() -> Optional[Dict[str, Any]]:
    """None when the Upwork pipeline is configured, else the one
    ``ghl_not_configured`` marker the tick reports once per run."""
    conf, reason = upwork_pipeline()
    if conf is not None:
        return None
    return {"code": NOT_CONFIGURED, "room_id": None, "detail": reason}


def opportunity_name(client: str) -> str:
    return "%s (Upwork)" % client


def stage_key_for_id(stage_id: Any, conf: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The Upwork stage key for a GHL pipelineStageId, or None when unknown
    (or when the Upwork pipeline is not configured)."""
    if conf is None:
        conf, _ = upwork_pipeline()
    if not stage_id or conf is None:
        return None
    for key, value in conf["stages"].items():
        if str(value) == str(stage_id):
            return key
    return None


def is_real_id(value: Any) -> bool:
    return bool(value) and not str(value).startswith(SHADOW_PREFIX)


def _iso(now: Any) -> Optional[str]:
    if isinstance(now, datetime):
        return now.replace(microsecond=0).isoformat()
    return str(now) if now is not None else None


def _state(thread: Dict[str, Any]) -> Dict[str, Any]:
    ghl = thread.get("ghl") if isinstance(thread.get("ghl"), dict) else {}
    out = {
        "contact_id": ghl.get("contact_id"),
        "opportunity_id": ghl.get("opportunity_id"),
        "stage": ghl.get("stage"),
    }
    if ghl.get("blocked"):
        out["blocked"] = ghl.get("blocked")
    return out


def _client_name(thread: Dict[str, Any], room: Optional[Dict[str, Any]]) -> str:
    name = thread.get("client") or (room or {}).get("client") or ""
    return " ".join(str(name).split())[:NAME_MAX]


def _id_from(result: Any, *paths: Tuple[str, ...]) -> Optional[str]:
    """An id out of a live GHL response; None for a shadow record."""
    if not isinstance(result, dict) or result.get("shadow"):
        return None
    for path in paths:
        cur = result  # type: Any
        for part in path:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, str) and cur.strip():
            return cur.strip()
    return None


def _rejected(result: Any) -> bool:
    """GHL answers 200 with ``{"succeded": false}`` on a rejected write (the
    same rule as pipeline_sync._outcome)."""
    if not isinstance(result, dict):
        return False
    return any(result.get(flag) is False for flag in ("succeded", "succeeded", "success"))


def _write_mismatch(result: Any, pipeline_id: str, stage_id: str, status: str) -> Optional[str]:
    """Why a 2xx stage-write answer shows GHL did not apply what was sent, or
    None. Only fields the answer carries are compared: a pipeline, a stage or
    a status other than the one sent is a mismatch (a stage or pipeline id
    another configured pipeline uses is never the one sent, so it is one too).
    An answer without those fields cannot be checked here; the first live
    rehearsal (runbook, Going live) confirms GHL applies ``status`` on PUT."""
    opp = _opportunity_of(result)
    if opp is None:
        return None
    got_pipeline = opp.get("pipelineId") or opp.get("pipeline_id")
    got_stage = opp.get("pipelineStageId") or opp.get("pipeline_stage_id")
    got_status = opp.get("status")
    bad = []
    if got_pipeline and str(got_pipeline).strip() != pipeline_id:
        bad.append("pipeline %s (sent %s)" % (_short(got_pipeline), _short(pipeline_id)))
    if got_stage and str(got_stage).strip() != stage_id:
        bad.append("stage id %s (sent %s)" % (_short(got_stage), _short(stage_id)))
    if got_status is not None and str(got_status).strip().lower() != status:
        bad.append("status %s (sent %s)" % (_short(got_status, 20), status))
    return "; ".join(bad) or None


def _error(code: str, room_id: Any, detail: str, action: Optional[str] = None) -> Dict[str, Any]:
    out = {"code": code, "room_id": room_id, "detail": detail[:400]}
    if action:
        out["action"] = action
    return out


def _short(value: Any, limit: int = 60) -> str:
    return str(value)[:limit]


def _won_by_contract(thread: Dict[str, Any]) -> bool:
    """``won`` set by the engine. sequence sets won only from a real contract
    (or a contract_started offer), and that beats every stage, a GHL move
    included (DESIGN "Stages"; the tick skips the read-back for such a room)."""
    return thread.get("stage") == "won" and thread.get("stage_set_by") == "engine"


def _last_engine_stage(engine_actions: Any) -> Optional[Any]:
    """The stage of the LAST ``ghl_stage`` engine action, or None. Earlier ones
    in the same tick (enrolment at new_reply, then a reply moving the thread)
    are superseded history."""
    last = None
    for act in engine_actions or []:
        if isinstance(act, dict) and (act.get("type") or act.get("kind") or act.get("action")) == STAGE_ACTION:
            last = act.get("stage")
    return last


# ------------------------------------------------------- reading an opportunity
def _opportunity_of(resp: Any) -> Optional[Dict[str, Any]]:
    opp = resp
    if isinstance(opp, dict) and isinstance(opp.get("opportunity"), dict):
        opp = opp["opportunity"]
    return opp if isinstance(opp, dict) else None


def _ghl_view(resp: Any, conf: Dict[str, Any]) -> Tuple[str, Any, Dict[str, str]]:
    """What a ``get_opportunity`` answer shows, read the same way by the
    read-back and by the check before a stage write. ``(kind, value, seen)``:

    * ``("stage", key, seen)``: GHL holds this Upwork stage. A won, lost or
      abandoned status decides it whatever the column (``STAGE_FOR_STATUS``),
      otherwise the column (``pipelineStageId``) does.
    * ``("other_pipeline", pipeline_id, seen)``: the opportunity sits in
      another pipeline.
    * ``("unknown_stage", stage_id, seen)``: a column that is none of the six
      Upwork stages.
    * ``("unreadable", why, seen)``: no opportunity in the answer (None means
      no read token), or no stage in it.

    ``seen`` is the raw pipeline id, stage id and status (ids only). A stage
    id another configured pipeline uses, on an answer with no pipeline id,
    reads as that pipeline.
    """
    opp = _opportunity_of(resp)
    if opp is None:
        why = "GHL returned nothing (no read token?)" if resp is None else "the answer is not an opportunity"
        return "unreadable", why, {}
    pipeline_id = opp.get("pipelineId") or opp.get("pipeline_id")
    stage_id = opp.get("pipelineStageId") or opp.get("pipeline_stage_id")
    status = str(opp.get("status") or "").strip().lower()
    seen = dict((k, _short(v, 80)) for k, v in (("pipeline_id", pipeline_id), ("stage_id", stage_id),
                                                 ("status", status)) if v)
    if pipeline_id and str(pipeline_id) != conf["id"]:
        return "other_pipeline", str(pipeline_id), seen
    if not pipeline_id and stage_id and str(stage_id) not in conf["stages"].values():
        where = _taken_ids(_pipelines()).get(str(stage_id).strip())
        if where:
            return "other_pipeline", where, seen
    if status in STAGE_FOR_STATUS:
        return "stage", STAGE_FOR_STATUS[status], seen
    if not stage_id:
        return "unreadable", "the answer has no pipelineStageId", seen
    key = stage_key_for_id(stage_id, conf)
    if key is None:
        return "unknown_stage", str(stage_id), seen
    return "stage", key, seen


def _read_opportunity(ghl: Any, opp_id: Any, conf: Dict[str, Any]) -> Tuple[str, Any, Dict[str, str]]:
    """:func:`_ghl_view` of a fresh read; a read that raises is unreadable."""
    try:
        resp = ghl.get_opportunity(opp_id)
    except Exception as exc:  # noqa: BLE001 - a read failure is an errors entry, never a raise
        return "unreadable", "%s: %s" % (type(exc).__name__, str(exc)[:200]), {}
    return _ghl_view(resp, conf)


# ------------------------------------------------------------- error entries
def _blocked_error(room_id: Any, thread: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    reason = state.get("blocked")
    target = thread.get("stage")
    known = state.get("stage")
    why = " (a live create answered without an id)" if reason == ERR_NO_ID else ""
    if target == known:
        waiting = "Nothing waits: GHL is known to hold stage %s" % _short(target)
    else:
        waiting = "Stage %s waits to be mirrored (GHL is known to hold %s)" % (
            _short(target), _short(known) if known else "nothing yet")
    detail = ("GHL mirror blocked: %s%s. No request is made for this thread until the block is cleared. %s. "
              "Recovery: fill the missing ghl ids from GHL, set ghl.stage, delete ghl.blocked (%s)."
              % (_short(reason, 80), why, waiting, RECOVERY_DOC))
    out = _error(ERR_BLOCKED, room_id, detail)
    out.update({"blocked": reason, "stage": target, "ghl_stage": known})
    return out


def _conflict_error(room_id: Any, opp_id: Any, kind: str, value: Any, seen: Dict[str, str], target: Any,
                    known: Any, set_by: Any) -> Dict[str, Any]:
    if kind == "stage":
        detail = ("GHL shows stage %s, but the mirror last wrote %s: the card was moved in GHL, so stage %s (set by "
                  "%s) was not written over it. The next run reads GHL's stage back and applies it to the thread "
                  "(your GHL move wins). To keep %s, move the card to it in GHL."
                  % (value, _short(known, 30) if known else "nothing", target, _short(set_by or "engine", 20), target))
    elif kind == "other_pipeline":
        detail = ("opportunity %s is in pipeline %s, not the Upwork pipeline: stage %s was not written, and the "
                  "mirror never moves a card between pipelines. Move it back to the Upwork pipeline in GHL (%s)."
                  % (_short(opp_id), _short(value), target, RECOVERY_DOC))
    else:
        detail = ("GHL shows stage id %s, which is none of the six Upwork stages (a column added in GHL?): stage %s "
                  "was not written. Move the card to one of the six Upwork columns in GHL; the next run reads that "
                  "move back and applies it (%s)." % (_short(value), target, RECOVERY_DOC))
    out = _error(ERR_STAGE_CONFLICT, room_id, detail, "update_opportunity_stage")
    out.update({"stage": target, "ghl_stage": known, "seen": dict(seen, kind=kind)})
    return out


def _read_failed_error(room_id: Any, opp_id: Any, why: Any, target: Any, known: Any) -> Dict[str, Any]:
    detail = ("could not read opportunity %s before moving it to %s, so nothing was written (a move made in GHL is "
              "never overwritten blind). The next run tries again. Read error: %s"
              % (_short(opp_id), target, _short(why, 150)))
    out = _error(ERR_READ_FAILED, room_id, detail, "get_opportunity")
    out.update({"stage": target, "ghl_stage": known})
    return out


# ----------------------------------------------------------------------- sync
def sync_thread(
    thread: Dict[str, Any],
    room: Optional[Dict[str, Any]],
    ghl: Any,
    now: Any,
    dry_run: bool,
    engine_actions: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Mirror one thread into the Upwork GHL pipeline. Returns
    ``(ghl_state, actions_done, errors)``; the caller stores ``ghl_state`` as
    ``thread["ghl"]``.

    * Upwork pipeline not configured: nothing at all; ``errors`` is the single
      ``ghl_not_configured`` marker.
    * ``thread["ghl"]["blocked"]`` set (a live create answered without an id):
      no request at all, on every run, and ``errors`` is one ``ghl_blocked``
      entry naming the room, the reason, the stage waiting to be mirrored and
      the recovery step, until the block is removed by hand.
    * No ids yet: upsert the contact (name = client, tags ``["upwork"]``,
      source "Upwork", no email), then the opportunity ``"<client> (Upwork)"``
      in the Upwork pipeline at ``thread["stage"]``.
    * Ids stored: no create; one ``update_opportunity_stage`` only when
      ``thread["stage"]`` differs from the stage GHL is known to hold. A stage
      that came FROM GHL (``stage_set_by == "ghl"``) is recorded, never
      written back.
    * Live, before that stage write, the opportunity is read (GET, read key)
      and the write is made only while GHL still shows the stage it is known
      to hold, in the Upwork pipeline. GHL already at ``thread["stage"]``:
      recorded, no write. Another stage, a column that is none of the six, or
      another pipeline: a ``ghl_stage_conflict`` error and no write (Lorenzo's
      GHL move wins; the next read-back applies a known stage). The one
      exception is ``won`` from a real contract (``won`` set by the engine),
      which is written over any stage in the Upwork pipeline, never into
      another pipeline. The read fails: ``ghl_read_failed`` and no write; the
      next run tries again. Shadow and dry run make no request, so they never
      read first.
    * The mirror follows ``thread["stage"]`` only. ``engine_actions`` is a
      cross-check: when the last ``ghl_stage`` action names another stage, the
      result is a ``ghl_stage_action_mismatch`` error and no write this run.
    * Unknown or missing stage: an error entry and no write.
    * ``dry_run``: nothing is called on ``ghl``; actions come back as
      ``planned`` and the state is unchanged.

    ``thread["ghl"]`` is also updated in place (not in dry run). Never raises
    for a GHL failure: each one is an ``errors`` entry.
    """
    state = _state(thread)
    actions = []  # type: List[Dict[str, Any]]
    errors = []  # type: List[Dict[str, Any]]
    at = _iso(now)
    room_id = thread.get("room_id") or (room or {}).get("room_id")

    conf, reason = upwork_pipeline()
    if conf is None:
        errors.append(_error(NOT_CONFIGURED, None, reason or "not configured"))
        return dict(state), actions, errors
    if state.get("blocked"):
        errors.append(_blocked_error(room_id, thread, state))
        return dict(state), actions, errors

    target = thread.get("stage")
    stage_id = conf["stages"].get(target) if isinstance(target, str) else None
    if not stage_id:
        errors.append(_error(ERR_UNKNOWN_STAGE, room_id, "stage %r is not an Upwork pipeline stage key (%s)"
                             % (target, ", ".join(STAGE_KEYS))))
        return dict(state), actions, errors
    engine_stage = _last_engine_stage(engine_actions)
    if engine_stage is not None and engine_stage != target:
        errors.append(_error(ERR_STAGE_MISMATCH, room_id, "engine ghl_stage action says %r but the thread's stage "
                             "is %r (set by %s); nothing written, the mirror follows the thread"
                             % (engine_stage, target, thread.get("stage_set_by"))))
        return dict(state), actions, errors
    client = _client_name(thread, room)
    if not client:
        errors.append(_error(ERR_NO_CLIENT, room_id, "thread has no client name; contact not created"))
        return dict(state), actions, errors
    if ghl is None and not dry_run:
        errors.append(_error(ERR_NO_GHL, room_id, "no GHL client passed"))
        return dict(state), actions, errors

    pipeline_id = conf["id"]
    status = STATUS_FOR_STAGE.get(target, "open")
    live = settings.is_live()

    def have(value: Any) -> bool:
        # In live a shadow placeholder is not an id: the real object is created.
        return bool(value) and (not live or is_real_id(value))

    def record(action: str, payload: Dict[str, Any], kind: str, result: Any = None) -> None:
        row = {"system": "ghl", "action": action, "payload": payload, "kind": kind, "at": at}
        if result is not None:
            row["result"] = result if isinstance(result, dict) else {"raw": result}
        actions.append(row)

    def call(action: str, payload: Dict[str, Any], fn: Callable[[], Any],
             check: Optional[Callable[[Any], Optional[str]]] = None) -> Tuple[str, Any]:
        """``(kind, result)``; kind is planned / would_do / done, or failed.
        ``check`` reads a live 2xx answer: a reason back means GHL did not
        apply the write (``ghl_write_rejected``)."""
        if dry_run:
            record(action, payload, "planned")
            return "planned", None
        try:
            result = fn()
        except ghl_client.GHLContactNeedsIdentity as exc:
            record(action, payload, "failed", {"error": str(exc)[:400]})
            errors.append(_error(ERR_NEEDS_IDENTITY, room_id, str(exc), action))
            return "failed", None
        except Exception as exc:  # noqa: BLE001 - one CRM failure must not stop the tick
            logger.error("ghl %s failed for %s: %s", action, room_id, exc)
            record(action, payload, "failed", {"error": str(exc)[:400]})
            errors.append(_error(ERR_WRITE_FAILED, room_id, str(exc), action))
            return "failed", None
        if isinstance(result, dict) and result.get("shadow") is True:
            record(action, payload, "would_do", result)
            return "would_do", result
        if result is None or _rejected(result):
            # None: nothing was written. A rejection body: GHL said no.
            record(action, payload, "failed", result if result is not None else {"error": "no response"})
            errors.append(_error(ERR_REJECTED, room_id, "GHL did not apply %s: %r" % (action, result), action))
            return "failed", result
        mismatch = check(result) if check is not None else None
        if mismatch:
            record(action, payload, "failed", result)
            errors.append(_error(ERR_REJECTED, room_id, "GHL answered %s with %s: not applied as sent; the "
                                 "known stage stays and the next run tries again" % (action, mismatch), action))
            return "failed", result
        record(action, payload, "done", result)
        return "done", result

    new = dict(state)

    def block(action: str) -> None:
        errors.append(_error(ERR_NO_ID, room_id, "%s answered without an id; not created again, and every later "
                             "run reports ghl_blocked until the ids are filled in by hand and ghl.blocked is "
                             "removed (%s)." % (action, RECOVERY_DOC), action))
        new["blocked"] = ERR_NO_ID

    # ---- contact
    if not have(new["contact_id"]):
        payload = {"email": None, "name": client, "tags": [UPWORK_TAG], "source": UPWORK_SOURCE}
        kind, res = call("upsert_contact", payload,
                         lambda: ghl.upsert_contact(None, name=client, tags=[UPWORK_TAG], source=UPWORK_SOURCE))
        if kind == "failed":
            return _finish(thread, state, new, dry_run), actions, errors
        contact_id = _id_from(res, ("contact", "id"), ("contact", "_id"), ("id",), ("_id",))
        if kind == "done" and contact_id is None:
            block("upsert_contact")
            return _finish(thread, state, new, dry_run), actions, errors
        new["contact_id"] = contact_id or "%scontact:%s" % (SHADOW_PREFIX, room_id)

    # ---- opportunity
    if not have(new["opportunity_id"]):
        name = opportunity_name(client)
        contact_id = new["contact_id"]
        payload = {"contact_id": contact_id, "pipeline_id": pipeline_id, "stage": target,
                   "stage_id": stage_id, "name": name, "status": status}
        kind, res = call("upsert_opportunity", payload,
                         lambda: ghl.upsert_opportunity(contact_id, pipeline_id, stage_id, name, status=status))
        if kind == "failed":
            return _finish(thread, state, new, dry_run), actions, errors
        opp_id = _id_from(res, ("opportunity", "id"), ("opportunity", "_id"), ("id",), ("_id",))
        if kind == "done" and opp_id is None:
            block("upsert_opportunity")
            return _finish(thread, state, new, dry_run), actions, errors
        new["opportunity_id"] = opp_id or "%sopportunity:%s" % (SHADOW_PREFIX, room_id)
        # Confirmed live create, or a shadow placeholder: GHL holds (or, for a
        # placeholder, would hold) the target stage.
        new["stage"] = target
        return _finish(thread, state, new, dry_run), actions, errors

    # ---- stage
    if target != new["stage"]:
        if thread.get("stage_set_by") == "ghl":
            # The stage came from GHL itself (read_back_stage): GHL is known to
            # hold it. Record it, never write it back.
            new["stage"] = target
            return _finish(thread, state, new, dry_run), actions, errors
        opp_id = new["opportunity_id"]
        known = new["stage"]
        if live and not dry_run:
            # Read before writing: only while GHL still shows the stage the
            # mirror last wrote. Any other stage is Lorenzo's GHL move and
            # wins over this push, except against won from a real contract,
            # which beats every stage (DESIGN "Stages"). Never another
            # pipeline, and never blind.
            seen_kind, seen_value, seen = _read_opportunity(ghl, opp_id, conf)
            if seen_kind == "unreadable":
                errors.append(_read_failed_error(room_id, opp_id, seen_value, target, known))
                return _finish(thread, state, new, dry_run), actions, errors
            if seen_kind == "stage" and seen_value == target:
                new["stage"] = target  # GHL already holds the thread's stage: nothing to write
                return _finish(thread, state, new, dry_run), actions, errors
            moved = seen_kind != "stage" or seen_value != known
            if seen_kind == "other_pipeline" or (moved and not _won_by_contract(thread)):
                errors.append(_conflict_error(room_id, opp_id, seen_kind, seen_value, seen, target, known,
                                              thread.get("stage_set_by")))
                return _finish(thread, state, new, dry_run), actions, errors
        payload = {"opportunity_id": opp_id, "stage": target, "stage_id": stage_id, "status": status,
                   "from_stage": known}
        kind, _ = call("update_opportunity_stage", payload,
                       lambda: ghl.update_opportunity_stage(opp_id, stage_id, status=status),
                       check=lambda res: _write_mismatch(res, pipeline_id, stage_id, status))
        if kind == "done" or (kind == "would_do" and not is_real_id(opp_id)):
            new["stage"] = target
    return _finish(thread, state, new, dry_run), actions, errors


def _finish(thread: Dict[str, Any], old: Dict[str, Any], new: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    if dry_run:
        return dict(old)
    ghl = thread.get("ghl") if isinstance(thread.get("ghl"), dict) else {}
    ghl.update(new)
    thread["ghl"] = ghl
    return dict(new)


# ------------------------------------------------------------------ read-back
def read_back_stage(thread: Dict[str, Any], ghl: Any) -> Optional[str]:
    """The stage key Lorenzo set on the GHL opportunity, or None.

    GHL's stage is read by :func:`_ghl_view`: its ``status`` when that is
    ``won`` or ``lost`` (Lorenzo can close a deal with the status control and
    leave the stage column alone), ``abandoned`` read as ``lost``, else the
    Upwork stage its ``pipelineStageId`` maps to.

    None when: the Upwork pipeline is not configured (no read at all; the
    marker is :func:`mirror_status`); there is no real opportunity id (none
    yet, or a shadow placeholder); no GHL client; the read fails or returns
    nothing (no token); the opportunity sits in another pipeline; the stage id
    is unknown; GHL matches ``thread["stage"]``; or GHL holds the stage it is
    known to hold (``thread["ghl"]["stage"]``), which means the thread moved
    since and the next sync pushes it.

    Any other GHL stage is Lorenzo's GHL move and is returned, also when the
    thread's stage is his own ``--stage`` or ``--resume`` not yet mirrored: a
    GHL move is never overwritten (except by ``won`` from a real contract).

    A blocked thread (``thread["ghl"]["blocked"]``) is read like any other. The
    create that blocked it usually left no opportunity id, so there is nothing
    to read; once Lorenzo fills a real id in by hand it is read back, blocked
    or not. Only :func:`sync_thread` stays off until he removes ``blocked``.
    Never raises.
    """
    try:
        conf, _ = upwork_pipeline()
        if conf is None:
            return None
        state = _state(thread)
        opp_id = state.get("opportunity_id")
        if ghl is None or not is_real_id(opp_id):
            return None
        try:
            resp = ghl.get_opportunity(opp_id)
        except Exception as exc:  # noqa: BLE001 - a read failure must not break the tick
            logger.warning("ghl read-back of opportunity %s failed: %s", opp_id, exc)
            return None
        kind, value, _seen = _ghl_view(resp, conf)
        if kind == "other_pipeline":
            logger.warning("opportunity %s is in pipeline %s, not Upwork; stage not read back", opp_id, value)
            return None
        if kind == "unknown_stage":
            logger.warning("opportunity %s has unknown stage id %s; stage not read back", opp_id, value)
            return None
        if kind != "stage":
            return None
        if value == thread.get("stage") or value == state.get("stage"):
            return None
        return value
    except Exception as exc:  # noqa: BLE001 - belt and braces: never raise into the tick
        logger.warning("ghl read-back failed for %s: %s", (thread or {}).get("room_id")
                       if isinstance(thread, dict) else None, exc)
        return None
