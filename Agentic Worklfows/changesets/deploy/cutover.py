#!/usr/bin/env python3
"""Shadow -> live cutover for the Modal reply engine (owner decision R5, GOL-4).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    W="$(cat .tmp/deploy/handoff_start.txt)"
    python3 changesets/deploy/cutover.py --watch-start "$W"             # dry-run (the default)
    python3 changesets/deploy/cutover.py --watch-start "$W" --apply     # asks for CUTOVER, seeds the live store
    python3 changesets/deploy/cutover.py --reset                        # dry-run: what a reset would delete
    python3 changesets/deploy/cutover.py --reset --apply                # asks for RESET
    python3 changesets/deploy/cutover.py --redo --watch-start "$W"      # dry-run: reset + a fresh cutover
    python3 changesets/deploy/cutover.py --redo --watch-start "$W" --apply   # asks for REDO
    python3 changesets/deploy/cutover.py --seed-shadow-from-live        # rollback: dry-run
    python3 changesets/deploy/cutover.py --seed-shadow-from-live --apply     # asks for SEED
    python3 changesets/deploy/cutover.py --status                       # read-only: the live store's cutover state
    python3 changesets/deploy/cutover.py --resume-live                  # back to live after a rollback: dry-run
    python3 changesets/deploy/cutover.py --resume-live --apply          # asks for RESUME

W is the HAND-OFF start (.tmp/deploy/handoff_start.txt, written before the
first shadow deploy by changesets/deploy/watch_clock.py), never the report
start the watch report reads.

Run the cutover AFTER the shadow watch is signed off and BEFORE the live
secret and deploy, while the shadow deployment is still running.

The cutover (default action)
----------------------------
1. Reads the SHADOW engine Dict and the SHADOW evidence Dict (read-only).
   Refuses unless the shadow poller is healthy: its newest Job_Log row is a
   ``tick`` no older than --max-poller-age-minutes (default 15).
2. Takes the shadow poller's cursor (its high-water mark: the newest reply it
   has consumed) as the cutover point. Every reply at or before that point is
   on the hand-off list; every reply after it is processed by the live poller.
3. Writes the HAND-OFF LIST: every reply the watch saw since --watch-start,
   the replies that failed in shadow, and the ids the poller saw but wrote no
   lead record for, to .tmp/cutover/handoff_<time>.md and .json. Lorenzo
   handles these by hand. Nothing here acts on them.
4. Checks the LIVE engine Dict is clean (no keys but stale lock keys).
   Deployed evidence lives in its own Dict (shared.store.get_obs_store), so a
   live deploy made before the cutover (every tick refused) leaves nothing
   here that blocks it.
5. --apply only: writes the seeded ``poller:cursor`` into the live Dict, then
   ``cutover:record`` last. Every live Modal tick refuses to run until
   ``cutover:record`` exists, and refuses one older than
   shared.store.CUTOVER_MAX_AGE_MINUTES until a live tick has accepted it.

--reset: deletes every key in the LIVE engine Dict. Refused when the LIVE
evidence Dict holds any instantly.* or ghl.* ``live_write_*`` row (a real
write to a prospect-facing system happened: the live store is then the record
of it and is not thrown away), or when that Dict cannot be read. Refused too
when the live ENGINE store itself shows live activity (a live tick accepted
the cutover, or anything beyond the cursor and the cutover record is there):
evidence rows expire after 7 idle days and are written best-effort, the store
is what the live engine actually did. ``--override-live-activity "<reason>"``
lets a reset or redo go ahead anyway; the reason is logged (Job_Log and
.tmp/cutover/overrides.jsonl).
--redo: --reset, then a fresh cutover, under one typed word. For a cutover
that went stale before the live flip (no live tick ever ran).
--seed-shadow-from-live: the rollback aid. Copies the live poller cursor into
the SHADOW engine Dict, so a shadow redeploy after a live period does not
re-read (and re-classify, and push a card for) every reply since the cutover,
and a shadow Dict whose cursor expired (7 idle days) does not walk back 20
pages. The live cursor it copied is kept in .tmp/cutover/rollback_seed.json.
--resume-live: back to live after a rollback, keeping the live store (it is
the record of the live period). With the shadow deployment running, it
re-seeds the live ``poller:cursor`` from the shadow poller's high-water mark,
writes a hand-off of the replies the shadow engine saw during the rollback
(after the live cursor, up to that mark), lists and clears the live
``poller:failed`` entries (older than the new cursor, the live poller could
never retry them and they would pin its cursor), and re-arms the age limit:
``cutover:accepted`` is deleted and a fresh ``cutover:record`` written LAST,
so the live deploy has to follow within CUTOVER_MAX_AGE_MINUTES. It REFUSES,
writing nothing ("STOP and ask"), when any reply arrived during the rollback
(identified or not) while anything live could send: an armed ladder, a ladder
paused by an auto-reply (cadence.is_auto_reply_pause: the engine restarts it
by itself), or a pending, approved_queued or sending card (resume_blockers).
--status: read-only. The live store's cutover record, whether a live tick
accepted it, its age against the limit, the live cursor and any live activity.

Everything is a dry run unless --apply is given, and --apply always asks for
its typed word on the terminal. Writes to no system other than these Modal
Dicts. Python 3.9.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from changesets.deploy import common
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common

LOCK_PREFIX = "__lock__:"
DEFAULT_MAX_POLLER_AGE_MIN = 15
# A real write to a prospect-facing system. Its row in the live evidence Dict
# makes --reset and --redo refuse.
PROSPECT_SYSTEMS = ("instantly.", "ghl.")
LIVE_WRITE_PREFIX = "live_write"
# What the cutover itself writes into the live engine store. Anything else
# there (and a cutover:accepted with a value) is live activity.
OPEN_CARD_STATUSES = ("pending", "approved_queued", "sending")
ROLLBACK_SEED_NAME = "rollback_seed.json"
OVERRIDES_NAME = "overrides.jsonl"


class CutoverRefused(Exception):
    """The step cannot be done safely; nothing was written."""


def _poller_keys() -> Tuple[str, str, str]:
    from services.reply_engine import poller

    return poller.CURSOR_KEY, poller.SEEN_KEY, poller.FAILED_KEY


def _parse(value: Any) -> Optional[datetime]:
    from changesets.deploy.watch_report import parse_ts

    return parse_ts(value)


def _is_not_found(exc: BaseException) -> bool:
    return type(exc).__name__ == "NotFoundError"


def _complete(cursor: Any) -> bool:
    return isinstance(cursor, dict) and bool(cursor.get("last_timestamp")) and bool(cursor.get("last_email_id"))


def live_keys(live_store) -> Optional[List[str]]:
    """Every key in the live Dict (lock keys included), or None when the Dict
    does not exist yet. Any other read error propagates: refuse, do not guess."""
    raw = getattr(live_store, "_dict", None)
    try:
        if raw is not None and hasattr(raw, "keys"):
            return sorted(str(k) for k in raw.keys())
        return sorted(live_store.keys(""))
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None
        raise


def newest_poller_row(obs_store) -> Optional[Dict[str, Any]]:
    from changesets.deploy.watch_report import iter_prefix
    from shared.job_log import OBS_JOB_PREFIX

    newest = None
    for _key, rec in iter_prefix(obs_store, OBS_JOB_PREFIX):
        if not isinstance(rec, dict) or rec.get("job") != "modal.poller":
            continue
        if newest is None or str(rec.get("ts_utc")) > str(newest.get("ts_utc")):
            newest = rec
    return newest


def prospect_writes(live_obs) -> List[Dict[str, Any]]:
    """instantly.* / ghl.* live_write_* rows in the live evidence Dict. A Dict
    that was never created holds none; any other read error propagates."""
    from changesets.deploy.watch_report import iter_prefix
    from shared.job_log import OBS_JOB_PREFIX

    out = []  # type: List[Dict[str, Any]]
    try:
        for key, rec in iter_prefix(live_obs, OBS_JOB_PREFIX):
            if not isinstance(rec, dict):
                continue
            if str(rec.get("job", "")).startswith(PROSPECT_SYSTEMS) and \
                    str(rec.get("status", "")).startswith(LIVE_WRITE_PREFIX):
                out.append(dict(rec, _key=key))
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return []
        raise
    return out


def live_activity(live_store, keys: Optional[List[str]] = None) -> List[str]:
    """What in the LIVE engine store shows the live engine ran, as short lines.

    Empty for a store holding only what a cutover writes (the seeded cursor
    and cutover:record, plus lock keys, plus reply_example:* copied from
    shadow after it) and for a store that does not exist.
    A ``cutover:accepted`` with a value means a live tick accepted the cutover;
    any other key (lead records, cards, poller:seen, llm.spend_usd, claims)
    was written by the live engine. Read errors propagate: refuse, never guess."""
    from services.reply_engine import poller
    from shared import store as store_mod

    if keys is None:
        keys = live_keys(live_store)
    if keys is None:
        return []
    out = []  # type: List[str]
    accepted = live_store.get(store_mod.CUTOVER_ACCEPTED_KEY) if store_mod.CUTOVER_ACCEPTED_KEY in keys else None
    if accepted is not None:
        out.append("a live tick accepted the cutover (%s at %s)" % (
            (accepted or {}).get("job") if isinstance(accepted, dict) else "?",
            (accepted or {}).get("accepted_at") if isinstance(accepted, dict) else accepted))
    from services.reply_engine import reply_examples

    exempt = (store_mod.CUTOVER_KEY, store_mod.CUTOVER_ACCEPTED_KEY, poller.CURSOR_KEY)
    # Reply examples copied from shadow after the cutover (seed_reply_examples
    # --copy-shadow-to-live) are context for prompts, not live activity.
    other = [k for k in keys if k not in exempt and not k.startswith(LOCK_PREFIX)
             and not k.startswith(reply_examples.PREFIX)]
    if other:
        out.append("%d key(s) written by the live engine, e.g. %s" % (len(other), ", ".join(other[:5])))
    return out


def _log_override(reason: str, activity: List[str], action: str, directory: Optional[str] = None) -> None:
    record = {"ts_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "action": action,
              "reason": reason, "live_activity": activity}
    try:
        path = os.path.join(directory or common.tmp_subdir("cutover"), OVERRIDES_NAME)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        sys.stderr.write("could not record the override locally: %s\n" % exc)
    _log("override_live_activity", record)


def build_handoff(shadow_store, seed: Dict[str, Any], watch_start: Optional[datetime],
                  exclude_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """The replies the watch saw at or before the cutover point, for Lorenzo.

    ``exclude_ids``: replies already handled elsewhere (the resume passes the
    live cursor's own reply, which the live engine processed)."""
    from changesets.deploy.watch_report import iter_prefix

    _cursor_key, seen_key, failed_key = _poller_keys()
    seen = shadow_store.get(seen_key) or {}
    seen = seen if isinstance(seen, dict) else {}
    failed = shadow_store.get(failed_key) or {}
    failed = failed if isinstance(failed, dict) else {}
    seed_id = str(seed.get("last_email_id") or "")
    seed_ts = str(seed.get("last_timestamp") or "")

    excluded = set(str(e) for e in (exclude_ids or []) if e)

    def before_cutover(email_id: str, received: str) -> bool:
        if email_id and email_id in excluded:
            return False
        if email_id and email_id == seed_id:
            return True
        return bool(received) and received < seed_ts

    def after_start(received: str) -> bool:
        ts = _parse(received)
        return watch_start is None or ts is None or ts >= watch_start

    rows = []  # type: List[Dict[str, Any]]
    listed = set()
    for key, state in iter_prefix(shadow_store, "lead:"):
        if not isinstance(state, dict):
            continue
        for event in state.get("history") or []:
            if not isinstance(event, dict) or event.get("event") != "inbound":
                continue
            email_id = str(event.get("email_id") or "")
            received = str(seen.get(email_id) or event.get("at") or "")
            if not before_cutover(email_id, received) or not after_start(received):
                continue
            listed.add(email_id)
            rows.append({
                "received_at": received,
                "lead_email": state.get("lead_email"),
                "first_name": state.get("first_name"),
                "company": state.get("company"),
                "campaign_key": state.get("campaign_key"),
                "label": event.get("label"),
                "lead_status_in_shadow": state.get("status"),
                "drafted_in_shadow": bool(state.get("drafts")),
                "approval_cards": len(state.get("approvals") or []),
                "subject": state.get("last_subject"),
                "email_id": email_id,
                "store_key": key,
            })
    failed_rows = []  # type: List[Dict[str, Any]]
    for email_id, info in sorted(failed.items()):
        info = info if isinstance(info, dict) else {}
        received = str(info.get("timestamp_created") or "")
        if email_id in listed or not before_cutover(str(email_id), received) or not after_start(received):
            continue
        failed_rows.append({"email_id": email_id, "received_at": received, "attempts": info.get("attempts"),
                            "error": info.get("error")})
    rows.sort(key=lambda r: (str(r["received_at"]), str(r["email_id"])))
    failed_ids = set(str(r["email_id"]) for r in failed_rows)
    no_record = sorted(
        ({"email_id": str(eid), "received_at": str(ts)} for eid, ts in seen.items()
         if str(eid) not in listed and str(eid) not in failed_ids
         and before_cutover(str(eid), str(ts)) and after_start(str(ts))),
        key=lambda r: (r["received_at"], r["email_id"]))
    return {"replies": rows, "failed_in_shadow": failed_rows, "seen_without_lead_record": no_record}


def healthy_shadow_poller(shadow_obs, at: datetime, max_poller_age_min: int) -> Dict[str, Any]:
    """The shadow poller's newest Job_Log row, if it is a tick from the last
    ``max_poller_age_min`` minutes. Raises CutoverRefused otherwise."""
    try:
        row = newest_poller_row(shadow_obs)
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the shadow evidence store could not be read (%s: %s)" % (type(exc).__name__, exc))
    if row is None:
        raise CutoverRefused("no modal.poller Job_Log row in the shadow evidence: no evidence the shadow poller ran")
    row_ts = _parse(row.get("ts_utc"))
    if row.get("status") != "tick" or row_ts is None:
        raise CutoverRefused("the shadow poller's newest row is %r at %s, not a healthy tick; fix the poller "
                             "first" % (row.get("status"), row.get("ts_utc")))
    age = at - row_ts
    if age > timedelta(minutes=max_poller_age_min) or age < timedelta(minutes=-5):
        raise CutoverRefused("the shadow poller last ticked at %s, %d minutes before the cutover time; it must "
                             "be under %d. Is the shadow deployment still running? (A live deploy replaces "
                             "it: redeploy shadow, wait for a poller tick, then cut over.)"
                             % (row.get("ts_utc"), int(age.total_seconds() // 60), max_poller_age_min))
    return row


def plan_cutover(shadow_store, shadow_obs, live_store, cutover_at: datetime,
                 watch_start: Optional[datetime] = None,
                 max_poller_age_min: int = DEFAULT_MAX_POLLER_AGE_MIN,
                 live_reset_first: bool = False) -> Dict[str, Any]:
    """Everything the cutover would do. Raises CutoverRefused; writes nothing.

    ``live_reset_first`` (the --redo path) skips the clean-live-store check,
    because the reset that precedes it deletes every key."""
    from shared import store as store_mod

    cursor_key, _seen_key, _failed_key = _poller_keys()
    try:
        cursor = shadow_store.get(cursor_key)
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the shadow store could not be read (%s: %s)" % (type(exc).__name__, exc))
    if not _complete(cursor):
        raise CutoverRefused("the shadow store has no complete %s (last_email_id and last_timestamp); the "
                             "shadow poller never completed a scan, so there is no cutover point" % cursor_key)

    row = healthy_shadow_poller(shadow_obs, cutover_at, max_poller_age_min)

    try:
        keys = live_keys(live_store)
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the live store could not be read (%s: %s)" % (type(exc).__name__, exc))
    engine_keys = [k for k in (keys or []) if not k.startswith(LOCK_PREFIX)]
    if engine_keys and not live_reset_first:
        existing = None
        try:
            existing = live_store.get(store_mod.CUTOVER_KEY)
        except Exception:  # noqa: BLE001
            existing = None
        if existing:
            raise CutoverRefused("the live store was already cut over at %s; a second cutover is refused. "
                                 "STOP. Read --status: if no live tick ever ran, use --redo; after a live "
                                 "period and a rollback, use --resume-live (runbook step 5)"
                                 % existing.get("cutover_at"))
        raise CutoverRefused("the live store is not clean: %d key(s), e.g. %s. STOP: find out what wrote them "
                             "(runbook step 5, 'If the cutover refuses')" % (len(engine_keys), engine_keys[:5]))

    seed = {"last_email_id": str(cursor["last_email_id"]), "last_timestamp": str(cursor["last_timestamp"]),
            "seeded_by": "changesets/deploy/cutover.py", "seeded_at": cutover_at.isoformat()}
    handoff = build_handoff(shadow_store, seed, watch_start)
    return {
        "cutover_at": cutover_at.isoformat(),
        "watch_start": watch_start.isoformat() if watch_start else None,
        "shadow_store": store_mod.modal_dict_name("shadow"),
        "live_store": store_mod.modal_dict_name("live"),
        "live_store_exists": keys is not None,
        "seed_cursor": seed,
        "shadow_poller_last_tick": row.get("ts_utc"),
        "max_age_minutes": store_mod.CUTOVER_MAX_AGE_MINUTES,
        "handoff": handoff,
    }


def plan_reset(live_store, live_obs, override_reason: str = "") -> Dict[str, Any]:
    """What --reset would delete. Raises CutoverRefused; writes nothing.

    Refuses on a prospect-facing live write in the evidence (always), and on
    live activity in the live engine store itself unless ``override_reason``
    is given (the caller logs it)."""
    try:
        writes = prospect_writes(live_obs)
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the live evidence store could not be read (%s: %s), so there is no proof that "
                             "nothing was sent; refusing" % (type(exc).__name__, exc))
    if writes:
        jobs = sorted(set(str(w.get("job")) for w in writes))
        raise CutoverRefused("the live evidence holds %d Instantly/GHL live_write_* row(s) (%s, first at %s). A "
                             "prospect-facing write happened; the live store is its record and is not reset"
                             % (len(writes), ", ".join(jobs), min(str(w.get("ts_utc")) for w in writes)))
    try:
        keys = live_keys(live_store)
        activity = live_activity(live_store, keys)
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the live store could not be read (%s: %s)" % (type(exc).__name__, exc))
    if activity and not (override_reason or "").strip():
        raise CutoverRefused("the live store shows live activity: %s. The live engine ran, and this store is its "
                             "record (evidence rows expire after 7 idle days, so their absence proves nothing). To "
                             "go live again after a rollback use --resume-live, which keeps it. To delete it "
                             "anyway, add --override-live-activity \"<reason>\" (logged)" % "; ".join(activity))
    return {"live_store_exists": keys is not None, "delete": list(keys or []), "live_activity": activity,
            "override_reason": (override_reason or "").strip() or None}


def read_rollback_seed(directory: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(directory or common.tmp_subdir("cutover"), ROLLBACK_SEED_NAME), "r",
                  encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def plan_resume(shadow_store, shadow_obs, live_store, now: datetime,
                max_poller_age_min: int = DEFAULT_MAX_POLLER_AGE_MIN,
                rollback_seed: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Back to live after a rollback, keeping the live store. Raises
    CutoverRefused; writes nothing."""
    from changesets.deploy.watch_report import iter_prefix
    from services.reply_engine import approval as approval_mod
    from shared import store as store_mod

    cursor_key, _seen_key, failed_key = _poller_keys()
    try:
        shadow_cursor = shadow_store.get(cursor_key)
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the shadow store could not be read (%s: %s)" % (type(exc).__name__, exc))
    if not _complete(shadow_cursor):
        raise CutoverRefused("the shadow store has no complete %s: the shadow poller has not completed a scan "
                             "since the rollback, so there is no point to resume from" % cursor_key)
    row = healthy_shadow_poller(shadow_obs, now, max_poller_age_min)
    try:
        keys = live_keys(live_store)
        activity = live_activity(live_store, keys)
        record = live_store.get(store_mod.CUTOVER_KEY) if keys else None
        live_cursor = live_store.get(cursor_key) if keys else None
        failed = (live_store.get(failed_key) or {}) if keys else {}
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the live store could not be read (%s: %s)" % (type(exc).__name__, exc))
    if not record and not activity:
        raise CutoverRefused("the live store was never cut over (no cutover:record, no live activity): this is "
                             "a first cutover, not a resume. Use the plain cutover (runbook step 5)")
    lower = live_cursor if _complete(live_cursor) else None
    lower_source = "the live store's poller:cursor"
    if lower is None:
        seed = (rollback_seed or {}).get("live_cursor")
        if _complete(seed):
            lower, lower_source = seed, ".tmp/cutover/%s (the live cursor copied at the rollback)" % ROLLBACK_SEED_NAME
    if lower is None:
        raise CutoverRefused("the live store has no complete poller:cursor (expired after 7 idle days?) and "
                             ".tmp/cutover/%s holds none, so the rollback period cannot be bounded. STOP and "
                             "ask: nothing here can tell which replies the live engine already handled"
                             % ROLLBACK_SEED_NAME)
    if str(shadow_cursor["last_timestamp"]) < str(lower["last_timestamp"]):
        raise CutoverRefused("the shadow cursor (%s at %s) is older than the live one (%s at %s): the shadow "
                             "engine has not caught up with the live period (was its cursor seeded from live at "
                             "the rollback?). STOP and ask" % (shadow_cursor["last_email_id"],
                                                               shadow_cursor["last_timestamp"],
                                                               lower["last_email_id"], lower["last_timestamp"]))
    seed = {"last_email_id": str(shadow_cursor["last_email_id"]),
            "last_timestamp": str(shadow_cursor["last_timestamp"]),
            "seeded_by": "changesets/deploy/cutover.py --resume-live", "seeded_at": now.isoformat()}
    handoff = build_handoff(shadow_store, seed, _parse(lower["last_timestamp"]),
                            exclude_ids=[str(lower["last_email_id"])])
    failed = failed if isinstance(failed, dict) else {}
    handoff["failed_in_live_cleared"] = [
        {"email_id": str(eid), "received_at": str((info or {}).get("timestamp_created") or ""),
         "attempts": (info or {}).get("attempts"), "error": (info or {}).get("error")}
        for eid, info in sorted(failed.items()) if isinstance(info, dict) or info is None]
    open_cards = []  # type: List[Dict[str, Any]]
    ladders = []  # type: List[Dict[str, Any]]
    try:
        for key, card in iter_prefix(live_store, approval_mod.APPROVAL_PREFIX):
            if isinstance(card, dict) and card.get("status") in OPEN_CARD_STATUSES:
                open_cards.append({"approval": key.split(":", 1)[-1], "lead": card.get("lead_email"),
                                   "status": card.get("status"), "created_at": card.get("created_at")})
        for key, state in iter_prefix(live_store, "lead:"):
            why = live_ladder_state(state)
            if why:
                ladders.append({"lead": (state or {}).get("lead_email") if isinstance(state, dict) else None,
                                "store_key": key, "why": why})
    except Exception as exc:  # noqa: BLE001
        raise CutoverRefused("the live store could not be read (%s: %s)" % (type(exc).__name__, exc))
    handoff["open_live_cards"] = sorted(open_cards, key=lambda c: str(c.get("created_at")))
    handoff["live_ladders_that_could_send"] = sorted(ladders, key=lambda r: str(r["store_key"]))
    blocked = resume_blockers(handoff)
    if blocked:
        raise CutoverRefused(
            "STOP and ask. %s, and the live store holds %d thing(s) that could send once live runs again, with "
            "nothing able to veto or stop them while shadow is deployed: %s. Nothing was written"
            % (rollback_replies_summary(handoff), len(blocked), "; ".join(blocked)))
    return {
        "cutover_at": now.isoformat(),
        "resume": True,
        "watch_start": lower["last_timestamp"],
        "rollback_lower_bound": {"cursor": dict(lower), "source": lower_source},
        "shadow_store": store_mod.modal_dict_name("shadow"),
        "live_store": store_mod.modal_dict_name("live"),
        "live_store_exists": keys is not None,
        "seed_cursor": seed,
        "previous_record": record,
        "live_activity": activity,
        "shadow_poller_last_tick": row.get("ts_utc"),
        "max_age_minutes": store_mod.CUTOVER_MAX_AGE_MINUTES,
        "handoff": handoff,
    }


def live_ladder_state(raw: Any) -> Optional[str]:
    """Why a live lead record's ladder could send once live runs again, or
    None. Decided by the engine's own functions on the loaded record:
    ``cadence.is_armed`` (an armed ladder) and ``cadence.is_auto_reply_pause``
    (stopped by an out-of-office or other machine reply: the next live tick
    restarts it by itself). A record the engine cannot load counts too."""
    if not isinstance(raw, dict):
        return None
    from services.reply_engine import cadence as cadence_mod
    from services.reply_engine.models import LeadState

    try:
        state = LeadState.from_store(raw)
    except Exception as exc:  # noqa: BLE001 - cannot tell: count it, never guess
        return "a lead record the engine cannot load (%s)" % type(exc).__name__
    if cadence_mod.is_armed(state):
        return "an armed live ladder"
    if cadence_mod.is_auto_reply_pause(state):
        return "a ladder paused by an auto-reply, which the next live tick restarts by itself"
    return None


def rollback_replies(handoff: Dict[str, Any]) -> Dict[str, List[str]]:
    """Every reply of the rollback period on the hand-off, identified or not."""
    return {"leads": sorted(set(str(r.get("lead_email") or r.get("email_id")) for r in handoff.get("replies") or [])),
            "failed_in_shadow": [str(r.get("email_id")) for r in handoff.get("failed_in_shadow") or []],
            "seen_without_lead_record": [str(r.get("email_id"))
                                         for r in handoff.get("seen_without_lead_record") or []]}


def rollback_replies_summary(handoff: Dict[str, Any]) -> str:
    got = rollback_replies(handoff)
    parts = []
    if got["leads"]:
        parts.append("from %s" % ", ".join(got["leads"]))
    if got["failed_in_shadow"]:
        parts.append("failed in shadow, lead unknown: %s" % ", ".join(got["failed_in_shadow"]))
    if got["seen_without_lead_record"]:
        parts.append("seen with no lead record, lead unknown: %s" % ", ".join(got["seen_without_lead_record"]))
    count = len(handoff.get("replies") or []) + len(got["failed_in_shadow"]) + len(got["seen_without_lead_record"])
    return "%d repl(ies) arrived during the rollback (%s)" % (count, "; ".join(parts))


def resume_blockers(handoff: Dict[str, Any]) -> List[str]:
    """Why a resume must not go ahead (empty: it may). Lorenzo's broad rule.

    When ANY reply arrived during the rollback (identified, failed in shadow
    or seen with no lead record, whose lead nobody knows), EVERY live thing
    that could send blocks the resume, whoever's it is: an armed ladder, a
    ladder paused by an auto-reply (the engine restarts it by itself), and a
    ``pending``, ``approved_queued`` or ``sending`` card. Any of them could go
    out to a lead whose new reply is Lorenzo's to answer by hand. With no
    reply during the rollback, nothing blocks."""
    got = rollback_replies(handoff)
    if not (handoff.get("replies") or got["failed_in_shadow"] or got["seen_without_lead_record"]):
        return []
    out = []  # type: List[str]
    for ladder in handoff.get("live_ladders_that_could_send") or []:
        out.append("%s (%s): %s" % (ladder.get("lead") or "?", ladder.get("store_key"), ladder.get("why")))
    for card in handoff.get("open_live_cards") or []:
        what = {"pending": "an open card, one tap sends it", "approved_queued": "a queued approved card",
                "sending": "a card being sent"}.get(str(card.get("status")), "an open card")
        out.append("card %s for %s: %s (%s)" % (card.get("approval"), card.get("lead") or "?", what,
                                                card.get("status")))
    return out


def apply_resume(live_store, plan: Dict[str, Any], handoff_path: str) -> None:
    """Re-arm the age limit, re-seed the cursor, clear the failed ids the new
    cursor makes unreachable, then write the fresh cutover:record LAST."""
    from shared import store as store_mod

    cursor_key, _seen_key, failed_key = _poller_keys()
    live_store.delete(store_mod.CUTOVER_ACCEPTED_KEY)
    live_store.set(cursor_key, plan["seed_cursor"])
    live_store.delete(failed_key)
    record = {
        "cutover_at": plan["cutover_at"],
        "resumed": True,
        "seed_cursor": plan["seed_cursor"],
        "rollback_lower_bound": plan["rollback_lower_bound"],
        "shadow_store": plan["shadow_store"],
        "handoff_file": handoff_path,
        "handoff_replies": len(plan["handoff"]["replies"]),
        "failed_in_live_cleared": [r["email_id"] for r in plan["handoff"].get("failed_in_live_cleared") or []],
        "previous": plan.get("previous_record"),
    }
    live_store.set(store_mod.CUTOVER_KEY, record)


def status(live_store, shadow_store, now: datetime) -> Dict[str, Any]:
    """Read-only: where the live store stands."""
    from shared import store as store_mod

    cursor_key, _s, _f = _poller_keys()
    keys = live_keys(live_store)
    record = live_store.get(store_mod.CUTOVER_KEY) if keys else None
    accepted = live_store.get(store_mod.CUTOVER_ACCEPTED_KEY) if keys else None
    age_min = None
    if isinstance(record, dict) and _parse(record.get("cutover_at")) is not None:
        age_min = int((now - _parse(record.get("cutover_at"))).total_seconds() // 60)
    try:
        shadow_cursor = shadow_store.get(cursor_key)
    except Exception as exc:  # noqa: BLE001
        shadow_cursor = "unreadable: %s" % exc
    stands = bool(record) and accepted is None and age_min is not None \
        and age_min <= store_mod.CUTOVER_MAX_AGE_MINUTES
    return {
        "live_store": store_mod.modal_dict_name("live"),
        "live_store_exists": keys is not None,
        "cutover_record": record,
        "accepted_by_a_live_tick": accepted,
        "cutover_age_minutes": age_min,
        "max_age_minutes": store_mod.CUTOVER_MAX_AGE_MINUTES,
        "live_cursor": live_store.get(cursor_key) if keys else None,
        "shadow_cursor": shadow_cursor,
        "live_activity": live_activity(live_store, keys),
        "next": ("no cutover yet: run the cutover" if not record else
                 "the cutover stands: deploy live within %d minutes of it" % store_mod.CUTOVER_MAX_AGE_MINUTES
                 if stands else
                 "a live tick ran on this cutover: to go live again after a rollback use --resume-live"
                 if accepted is not None else
                 "the resume is stale and no live tick ran since it: run --resume-live again (never --redo, "
                 "which would delete the record of the live period)"
                 if isinstance(record, dict) and record.get("resumed") else
                 "the cutover is stale and no live tick ran: --redo"),
    }


def render_handoff_md(plan: Dict[str, Any]) -> str:
    handoff = plan["handoff"]
    if plan.get("resume"):
        head = [
            "# Hand-off: replies from the rollback period (resume to live)",
            "",
            "Resumed at %s. The live engine starts again after reply `%s` (%s) and never sees the replies below."
            % (plan["cutover_at"], plan["seed_cursor"]["last_email_id"], plan["seed_cursor"]["last_timestamp"]),
            "Rollback period starts after reply `%s` (%s), from %s." % (
                plan["rollback_lower_bound"]["cursor"]["last_email_id"],
                plan["rollback_lower_bound"]["cursor"]["last_timestamp"], plan["rollback_lower_bound"]["source"]),
        ]
    else:
        head = [
            "# Hand-off: replies from the shadow watch",
            "",
            "Cutover at %s. The live engine starts after reply `%s` (%s) and never sees the replies below."
            % (plan["cutover_at"], plan["seed_cursor"]["last_email_id"], plan["seed_cursor"]["last_timestamp"]),
            "Watch start: %s (older replies are not listed)." % (plan.get("watch_start") or "not given: every reply"),
        ]
    lines = head + [
        "Handle each one by hand in Instantly. Nothing was sent, drafted for sending or moved for any of them.",
        "",
        "| Received (UTC) | Lead | Name | Company | Campaign | Label | Drafted in shadow | Subject |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in handoff["replies"]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["received_at"], r["lead_email"] or "", r["first_name"] or "", r["company"] or "",
            r["campaign_key"] or "", r["label"] or "", "yes" if r["drafted_in_shadow"] else "no",
            (r["subject"] or "").replace("|", "/")))
    lines.append("")
    lines.append("## Failed in shadow (never classified): %d" % len(handoff["failed_in_shadow"]))
    for r in handoff["failed_in_shadow"]:
        lines.append("- email `%s`, received %s, %s attempt(s): %s" % (
            r["email_id"], r["received_at"], r.get("attempts"), r.get("error")))
    lines.append("")
    lines.append("## Seen by the shadow poller with no lead record: %d" % len(handoff["seen_without_lead_record"]))
    lines.append("The poller marked these ids seen but wrote no lead record for them. Usually an auto-reply, a "
                 "bounce, one of the team's own inboxes or a campaign outside scope, but this list cannot tell "
                 "which: open each id in Instantly (Unibox) and confirm it needs nothing.")
    for r in handoff["seen_without_lead_record"]:
        lines.append("- email `%s`, received %s" % (r["email_id"], r["received_at"]))
    if plan.get("resume"):
        lines.append("")
        lines.append("## Failed in live before the rollback, cleared from the live store: %d"
                     % len(handoff.get("failed_in_live_cleared") or []))
        lines.append("The new cursor is past these, so the live poller could never retry them. Check each by hand.")
        for r in handoff.get("failed_in_live_cleared") or []:
            lines.append("- email `%s`, received %s, %s attempt(s): %s" % (
                r["email_id"], r["received_at"], r.get("attempts"), r.get("error")))
        lines.append("")
        lines.append("## Live cards still open: %d" % len(handoff.get("open_live_cards") or []))
        lines.append("A resume goes ahead with these only when nobody replied during the rollback; they carry on "
                     "as they were.")
        for c in handoff.get("open_live_cards") or []:
            lines.append("- %s: `%s`, %s since %s" % (c.get("lead"), c.get("approval"), c.get("status"),
                                                   c.get("created_at")))
        lines.append("")
        lines.append("## Live ladders that could send: %d" % len(handoff.get("live_ladders_that_could_send") or []))
        lines.append("Armed, or paused by an auto-reply (the engine restarts those by itself). Same rule as the "
                     "cards.")
        for ladder in handoff.get("live_ladders_that_could_send") or []:
            lines.append("- %s (`%s`): %s" % (ladder.get("lead"), ladder.get("store_key"), ladder.get("why")))
    return "\n".join(lines) + "\n"


def write_handoff(plan: Dict[str, Any], dry_run: bool, directory: Optional[str] = None) -> Tuple[str, str]:
    directory = directory or common.tmp_subdir("cutover")
    if not os.path.isdir(directory):
        os.makedirs(directory)
    stamp = _parse(plan["cutover_at"]).strftime("%Y%m%dT%H%M%SZ")
    suffix = ".dryrun" if dry_run else ""
    json_path = os.path.join(directory, "handoff_%s%s.json" % (stamp, suffix))
    md_path = os.path.join(directory, "handoff_%s%s.md" % (stamp, suffix))
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, sort_keys=True)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_handoff_md(plan))
    return json_path, md_path


def apply_reset(writer, plan: Dict[str, Any]) -> int:
    n = 0
    for key in plan["delete"]:
        writer.delete(key)
        n += 1
    return n


def apply_cutover(live_store, plan: Dict[str, Any], handoff_path: str) -> None:
    """Seed the cursor, then write cutover:record LAST (it is what unlocks live)."""
    from shared import store as store_mod

    cursor_key, _seen_key, _failed_key = _poller_keys()
    if not live_store.set_if_absent(cursor_key, plan["seed_cursor"]):
        raise CutoverRefused("%s appeared in the live store while this ran; stopping before cutover:record"
                             % cursor_key)
    record = {
        "cutover_at": plan["cutover_at"],
        "seed_cursor": plan["seed_cursor"],
        "shadow_store": plan["shadow_store"],
        "handoff_file": handoff_path,
        "handoff_replies": len(plan["handoff"]["replies"]),
        "handoff_failed": len(plan["handoff"]["failed_in_shadow"]),
        "watch_start": plan.get("watch_start"),
    }
    if not live_store.set_if_absent(store_mod.CUTOVER_KEY, record):
        raise CutoverRefused("%s appeared in the live store while this ran" % store_mod.CUTOVER_KEY)


def _log(status: str, details: Dict[str, Any]) -> None:
    try:
        from shared.job_log import log_run

        log_run("deploy.cutover", status, details)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("could not write the Job_Log row: %s\n" % exc)


def _refused(exc: Exception, what: str = "") -> int:
    print("REFUSED%s: %s" % (what, exc))
    print("Nothing was written. STOP here and read runbooks/deployment.md %s." % (
        "Rollback, 'Going live again after a rollback'" if "resume" in what else "step 5, 'If the cutover refuses'"))
    _log("refused", {"reason": str(exc)})
    return 1


def _print_plan(plan: Dict[str, Any], md_path: str) -> None:
    handoff = plan["handoff"]
    print("Cutover point: reply %s at %s (the shadow poller's high-water mark; last tick %s)"
          % (plan["seed_cursor"]["last_email_id"], plan["seed_cursor"]["last_timestamp"],
             plan["shadow_poller_last_tick"]))
    print("Watch start: %s" % (plan.get("watch_start") or "not given (every reply the shadow store holds)"))
    print("Hand-off: %d repl(ies), %d failed in shadow, %d seen with no lead record (ids listed) -> %s"
          % (len(handoff["replies"]), len(handoff["failed_in_shadow"]),
             len(handoff["seen_without_lead_record"]), md_path))
    print("Deploy live within %d minutes of the apply: the first live tick refuses an older cutover."
          % plan["max_age_minutes"])


def _seed_shadow(shadow_store, live_store, args, confirm, open_shadow_for_write, cutover_at,
                 handoff_dir: Optional[str] = None) -> int:
    cursor_key, _s, _f = _poller_keys()
    try:
        cursor = live_store.get(cursor_key)
        current = shadow_store.get(cursor_key)
    except Exception as exc:  # noqa: BLE001
        return _refused(CutoverRefused("a store could not be read (%s: %s)" % (type(exc).__name__, exc)))
    if not _complete(cursor):
        return _refused(CutoverRefused("the live store has no complete %s to copy" % cursor_key))
    seed = {"last_email_id": str(cursor["last_email_id"]), "last_timestamp": str(cursor["last_timestamp"]),
            "seeded_by": "changesets/deploy/cutover.py --seed-shadow-from-live", "seeded_at": cutover_at.isoformat()}
    print("Shadow %s now: %s" % (cursor_key, json.dumps(current, sort_keys=True) if current else "absent"))
    print("Would become:  %s (the live poller's high-water mark)" % json.dumps(seed, sort_keys=True))
    if not args.apply:
        print("\nDry run. Nothing was written. Re-run with --apply (asks for SEED).")
        return 0
    if not confirm("SEED", "Overwrite the SHADOW poller cursor with the live one?"):
        print("Not confirmed. Nothing was written.")
        return 1
    writer = open_shadow_for_write() if open_shadow_for_write else shadow_store
    writer.set(cursor_key, seed)
    _log("shadow_seeded_from_live", {"seed_cursor": seed})
    try:
        path = os.path.join(handoff_dir or common.tmp_subdir("cutover"), ROLLBACK_SEED_NAME)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"seeded_at": cutover_at.isoformat(), "live_cursor": dict(cursor)}, fh, indent=2,
                      sort_keys=True)
        print("The live cursor at the rollback is kept in %s (--resume-live reads it if the live one expires)."
              % path)
    except OSError as exc:
        sys.stderr.write("could not keep the rollback seed locally: %s\n" % exc)
    print("Seeded. The shadow poller starts after reply %s." % seed["last_email_id"])
    return 0


def _resume(shadow_store, shadow_obs, live_store, args, confirm, open_live_for_write, now,
            handoff_dir: Optional[str]) -> int:
    try:
        plan = plan_resume(shadow_store, shadow_obs, live_store, now, args.max_poller_age_minutes,
                           rollback_seed=read_rollback_seed(handoff_dir))
    except CutoverRefused as exc:
        return _refused(exc, " (resume)")
    dry_run = not args.apply
    _json_path, md_path = write_handoff(plan, dry_run, handoff_dir)
    handoff = plan["handoff"]
    print("Resume point: reply %s at %s (the shadow poller's high-water mark; last tick %s)"
          % (plan["seed_cursor"]["last_email_id"], plan["seed_cursor"]["last_timestamp"],
             plan["shadow_poller_last_tick"]))
    print("Rollback period after: reply %s at %s (%s)" % (
        plan["rollback_lower_bound"]["cursor"]["last_email_id"],
        plan["rollback_lower_bound"]["cursor"]["last_timestamp"], plan["rollback_lower_bound"]["source"]))
    print("Hand-off: %d repl(ies), %d failed in shadow, %d seen with no lead record, %d failed in live (cleared), "
          "%d live card(s) still open, %d live ladder(s) that could send -> %s"
          % (len(handoff["replies"]), len(handoff["failed_in_shadow"]), len(handoff["seen_without_lead_record"]),
             len(handoff["failed_in_live_cleared"]), len(handoff["open_live_cards"]),
             len(handoff["live_ladders_that_could_send"]), md_path))
    print("The live store is kept (%s). Deploy live within %d minutes of the apply: the age limit is re-armed."
          % ("; ".join(plan["live_activity"]) or "no live activity found", plan["max_age_minutes"]))
    if dry_run:
        print("\nDry run. Nothing was written to either store. Re-run with --resume-live --apply (asks for RESUME).")
        _log("resume_dry_run", {"handoff_replies": len(handoff["replies"]), "handoff_file": md_path})
        return 0
    if not confirm("RESUME", "Re-seed the live cursor, clear %d live failed id(s) and re-arm the cutover? The %d "
                   "hand-off repl(ies) become yours to handle." % (len(handoff["failed_in_live_cleared"]),
                                                                   len(handoff["replies"]))):
        print("Not confirmed. Nothing was written.")
        return 1
    from shared import store as store_mod

    writer = open_live_for_write() if open_live_for_write else live_store
    apply_resume(writer, plan, md_path)
    _log("resumed", {"handoff_replies": len(handoff["replies"]), "handoff_file": md_path,
                     "seed_cursor": plan["seed_cursor"], "live_activity": plan["live_activity"]})
    print("\nResumed. Next, within %d minutes: install_schedules.sh --deploy live (runbooks/deployment.md, "
          "Rollback, 'Going live again')." % store_mod.CUTOVER_MAX_AGE_MINUTES)
    return 0


def main(argv: Optional[List[str]] = None, shadow_store=None, live_store=None,
         open_live_for_write: Optional[Callable[[], Any]] = None,
         confirm: Callable[[str, str], bool] = common.confirm_from_tty,
         now: Optional[datetime] = None, handoff_dir: Optional[str] = None,
         shadow_obs=None, live_obs=None, open_shadow_for_write: Optional[Callable[[], Any]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--reset", action="store_true", help="delete every key in the live engine store")
    action.add_argument("--redo", action="store_true", help="--reset, then a fresh cutover (asks for REDO)")
    action.add_argument("--seed-shadow-from-live", action="store_true",
                        help="rollback aid: copy the live poller cursor into the shadow store (asks for SEED)")
    action.add_argument("--resume-live", action="store_true",
                        help="back to live after a rollback, keeping the live store (asks for RESUME)")
    action.add_argument("--status", action="store_true", help="read-only: the live store's cutover state")
    parser.add_argument("--apply", action="store_true", help="write (asks for the typed word)")
    parser.add_argument("--dry-run", action="store_true", help="the default; kept for explicitness")
    parser.add_argument("--watch-start", "--handoff-start", dest="watch_start",
                        help="the HAND-OFF start: ISO time recorded before the first shadow deploy (older replies "
                             "are left out); watch_clock.py saves it to .tmp/deploy/handoff_start.txt")
    parser.add_argument("--override-live-activity", default="", metavar="REASON",
                        help="let --reset/--redo delete a live store that shows live activity; the reason is logged")
    parser.add_argument("--max-poller-age-minutes", type=int, default=DEFAULT_MAX_POLLER_AGE_MIN)
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        print("--apply and --dry-run together: refusing (pick one)")
        return 2
    watch_start = None
    if args.watch_start is not None:
        watch_start = _parse(args.watch_start.strip())
        if watch_start is None:
            print("--watch-start is empty or not an ISO time (%r). Is .tmp/deploy/handoff_start.txt there? "
                  "Refusing." % args.watch_start)
            return 2

    from shared import store as store_mod

    cutover_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    if shadow_store is None:
        shadow_store = store_mod.open_modal_store("shadow", create_if_missing=False)
    if live_store is None:
        live_store = store_mod.open_modal_store("live", create_if_missing=False)
    if shadow_obs is None:
        shadow_obs = store_mod.open_obs_store("shadow", create_if_missing=False)
    if live_obs is None:
        live_obs = store_mod.open_obs_store("live", create_if_missing=False)

    if args.override_live_activity and not (args.reset or args.redo):
        print("--override-live-activity only goes with --reset or --redo. Refusing.")
        return 2
    if args.status:
        try:
            print(json.dumps(status(live_store, shadow_store, cutover_at), indent=2, sort_keys=True, default=str))
        except Exception as exc:  # noqa: BLE001 - read-only: report and stop
            print("could not read the live store (%s: %s)" % (type(exc).__name__, exc))
            return 2
        return 0
    if args.seed_shadow_from_live:
        return _seed_shadow(shadow_store, live_store, args, confirm, open_shadow_for_write, cutover_at,
                            handoff_dir=handoff_dir)
    if args.resume_live:
        return _resume(shadow_store, shadow_obs, live_store, args, confirm, open_live_for_write, cutover_at,
                       handoff_dir)

    reset = None
    if args.reset or args.redo:
        try:
            reset = plan_reset(live_store, live_obs, override_reason=args.override_live_activity)
        except CutoverRefused as exc:
            return _refused(exc)
        print("Reset: %d key(s) in %s would be deleted%s" % (
            len(reset["delete"]), store_mod.modal_dict_name("live"),
            (": %s%s" % (", ".join(reset["delete"][:10]), " ..." if len(reset["delete"]) > 10 else ""))
            if reset["delete"] else ""))
        print("No Instantly or GHL live write is recorded in %s." % store_mod.obs_dict_name("live"))
        if reset.get("live_activity"):
            print("OVERRIDE: the live store shows live activity (%s); deleting it anyway because: %s"
                  % ("; ".join(reset["live_activity"]), reset["override_reason"]))
        if args.reset:
            if not args.apply:
                print("\nDry run. Nothing was written. Re-run with --reset --apply (asks for RESET).")
                return 0
            if not confirm("RESET", "Delete all %d key(s) in the live engine store?" % len(reset["delete"])):
                print("Not confirmed. Nothing was written.")
                return 1
            if reset.get("live_activity"):
                _log_override(reset["override_reason"], reset["live_activity"], "reset",
                              directory=handoff_dir)
            writer = open_live_for_write() if open_live_for_write else live_store
            n = apply_reset(writer, reset)
            _log("reset", {"deleted": n, "override_reason": reset.get("override_reason")})
            print("Reset: %d key(s) deleted. Next: the cutover (runbook step 5)." % n)
            return 0

    try:
        plan = plan_cutover(shadow_store, shadow_obs, live_store, cutover_at, watch_start,
                            args.max_poller_age_minutes, live_reset_first=bool(args.redo))
    except CutoverRefused as exc:
        return _refused(exc)

    dry_run = not args.apply
    json_path, md_path = write_handoff(plan, dry_run, handoff_dir)
    _print_plan(plan, md_path)
    if dry_run:
        print("\nDry run. Nothing was written to either store. Re-run with --apply to %s."
              % ("reset and seed the live store (asks for REDO)" if args.redo else "seed the live store (asks for CUTOVER)"))
        _log("dry_run", {"handoff_replies": len(plan["handoff"]["replies"]), "handoff_file": md_path,
                         "redo": bool(args.redo)})
        return 0
    word = "REDO" if args.redo else "CUTOVER"
    if not confirm(word, "%sSeed %s and mark it cut over? The %d hand-off repl(ies) become yours to handle."
                   % ("Delete %d live key(s), then: " % len(reset["delete"]) if args.redo else "",
                      plan["live_store"], len(plan["handoff"]["replies"]))):
        print("Not confirmed. Nothing was written.")
        return 1
    writer = open_live_for_write() if open_live_for_write else (
        live_store if plan["live_store_exists"] else store_mod.open_modal_store("live", create_if_missing=True))
    try:
        if args.redo:
            if reset.get("live_activity"):
                _log_override(reset["override_reason"], reset["live_activity"], "redo", directory=handoff_dir)
            apply_reset(writer, reset)
        apply_cutover(writer, plan, md_path)
    except CutoverRefused as exc:
        return _refused(exc, " during apply")
    _log("redone" if args.redo else "applied", {"handoff_replies": len(plan["handoff"]["replies"]),
                                                "handoff_file": md_path, "seed_cursor": plan["seed_cursor"]})
    print("\nCut over. Next, within %d minutes: the live secret and the live deploy (runbooks/deployment.md "
          "step 5)." % plan["max_age_minutes"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
