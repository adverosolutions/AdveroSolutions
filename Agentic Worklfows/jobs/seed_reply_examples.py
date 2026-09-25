"""Seed the reply examples with Lorenzo's own replies since the start date.

    python3 jobs/seed_reply_examples.py                      # dry run: prints what it would record
    python3 jobs/seed_reply_examples.py --write              # records them in the engine store
    python3 jobs/seed_reply_examples.py --write --modal      # ... in the deployed Modal Dict of this mode
    python3 jobs/seed_reply_examples.py --copy-shadow-to-live [--write --i-am-lorenzo-live]   # cutover step
    python3 jobs/seed_reply_examples.py --start-at 2026-09-15 --pages 5 --json

Reads GET /emails?email_type=manual (read-only; both directions of every
thread answered by hand, newest first) back to the poller's start date
(shared.settings.poller_start_at, default 2026-09-15, the first day the 2026
campaigns sent) and pairs each reply Lorenzo sent himself (ue_type 3, else the
sender, else the recipients: cadence._sent_by_hand) with the lead's message it
answered: the newest message of the lead's in the same thread since our last
email in it, auto-replies excluded. Only a lead's row counts as the lead's
message (ue_type 2, else a row that is not outbound: _from_lead); any other
row of ours (a campaign step or scheduled send, ue_type 1 or 4) clears it, so
our own email is never paired as the message he answered. A reply of ours with
no lead message before it (a bump) is not an example.

Never a reply the engine sent: a row whose id is an engine touch's Instantly
id, or whose time is within ENGINE_MATCH_MINUTES of an engine send recorded
on the lead row (history ``reply_sent``; cadence touches of kind ``done``),
is skipped as ``engine_sent``.

The category is the label the engine gave the lead's message (the lead row's
``inbound`` history entry for that email id); a message the engine never
classified is recorded with no category. No model is called.

Default is a dry run: nothing is written to the store, and its Job_Log row
goes to a scratch log (.tmp/scratch/seed_reply_examples_dryrun/). ``--write``
records each new example with reply_examples.record (set_if_absent on
``reply_example:<email id>``, so a rerun or the cadence tick's own capture
never duplicates one). Store writes are not live-system writes: the engine
store is separate per mode (shared.store), which is the pattern every job
follows, so guard_write is not involved. Nothing is sent, tagged or moved.

Refusals (exit 2, a Job_Log row "refused", nothing read or written): a start
date later than now; a store showing the engine has sent live (a cutover
record, an engine reply_sent, a live cadence touch), because the engine's
thread_reply, show-rate and no-show sends would then read as Lorenzo's; the
live Dict (``--modal`` in live mode, ``--copy-shadow-to-live --write``, or
MODE=live) without ``--i-am-lorenzo-live``. Every run of this job is
Lorenzo's to start (runbooks/reply_examples.md).
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if __package__ in (None, ""):  # run as a script: make "shared"/"services" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings
from shared import slots as slot_rules
from shared.job_log import log_run

logger = logging.getLogger("jobs.seed_reply_examples")

JOB = "seed_reply_examples"
PAGE_SIZE = 100
MAX_PAGES = 10
# The lead's message a reply answers can be older than the reply itself, so
# paging reads this much further back than the start date.
LEAD_MESSAGE_LOOKBACK_DAYS = 7
# An engine send recorded on the lead row this close to a row's time is taken
# to be that row: the engine's own reply, never an example of his.
ENGINE_MATCH_MINUTES = 10


def _time(row: Dict[str, Any]) -> Optional[datetime]:
    from jobs.pipeline_sweep import parse_ts

    return parse_ts(row.get("timestamp_created") or row.get("timestamp_email"))


def fetch_manual_rows(instantly: Any, start_at: Optional[datetime], max_pages: int = MAX_PAGES,
                      page_size: int = PAGE_SIZE) -> Dict[str, Any]:
    """Pages of GET /emails?email_type=manual, newest first, until a row older
    than ``start_at`` minus LEAD_MESSAGE_LOOKBACK_DAYS (the rest are older
    still), the last page, or ``max_pages``. Returns {"rows", "pages",
    "truncated"}; truncated: the page budget ran out first."""
    floor = start_at - timedelta(days=LEAD_MESSAGE_LOOKBACK_DAYS) if start_at is not None else None
    rows = []  # type: List[Dict[str, Any]]
    seen = set()  # type: Set[str]
    cursor = None  # type: Optional[str]
    pages = 0
    done = False
    while pages < max_pages and not done:
        page = instantly.list_emails(email_type="manual", limit=page_size, starting_after=cursor)
        pages += 1
        if isinstance(page, dict):
            items = page.get("items") or []
            cursor = page.get("next_starting_after")
        elif isinstance(page, list):
            items, cursor = list(page), None
        else:
            items, cursor = [], None
        for row in items:
            if not isinstance(row, dict):
                continue
            eid = str(row.get("id") or "")
            if eid and eid in seen:
                continue   # the cursor row echoed back by the API
            seen.add(eid)
            at = _time(row)
            if floor is not None and at is not None and at < floor:
                done = True
                break
            rows.append(row)
        if not cursor or not items:
            done = True
    return {"rows": rows, "pages": pages, "truncated": not done}


def store_index(store: Any) -> Dict[str, Any]:
    """What the engine store says about the threads, read once from every
    ``lead:*`` row:

    * ``labels``: email id -> the label the engine gave that inbound
      (the row's ``inbound`` history entries);
    * ``engine_ids``: the Instantly ids of the engine's own touches;
    * ``engine_times``: the times the engine itself sent, keyed
      ``lead:<email>`` and ``thread:<thread id>`` (a ``reply_sent`` history
      entry; a cadence touch of kind ``done`` that was not a shadow record).
      ``reply_sent_manually`` is Lorenzo's own and is not here;
    * ``thread_leads``: thread id -> the lead's email on the lead row (the
      lead can answer from another address than the one the campaign mailed)."""
    labels = {}  # type: Dict[str, str]
    ids = set()  # type: Set[str]
    times = {}  # type: Dict[str, List[datetime]]
    thread_leads = {}  # type: Dict[str, str]
    for key in store.keys("lead:"):
        raw = store.get(key)
        if not isinstance(raw, dict):
            continue
        lead = str(raw.get("lead_email") or "").strip().lower()
        thread = str(raw.get("thread_id") or "")
        if thread and lead:
            thread_leads.setdefault(thread, lead)
        sends = []  # type: List[datetime]
        for entry in raw.get("history") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("event") == "inbound" and entry.get("email_id") and entry.get("label"):
                labels.setdefault(str(entry["email_id"]), str(entry["label"]))
            elif entry.get("event") == "reply_sent":
                at = _time({"timestamp_created": entry.get("sent_at") or entry.get("at")})
                if at is not None:
                    sends.append(at)
        for touch in (raw.get("cadence") or {}).get("touches") or []:
            if not isinstance(touch, dict) or touch.get("kind") != "done" or touch.get("shadow"):
                continue
            if touch.get("result_id"):
                ids.add(str(touch["result_id"]))
            at = _time({"timestamp_created": touch.get("sent_at")})
            if at is not None:
                sends.append(at)
        for k in (("lead:" + lead) if lead else None, ("thread:" + thread) if thread else None):
            if k and sends:
                times.setdefault(k, []).extend(sends)
    return {"labels": labels, "engine_ids": ids, "engine_times": times, "thread_leads": thread_leads}


def _engine_sent(index: Dict[str, Any], eid: str, at: Optional[datetime], lead: str, thread_id: str) -> bool:
    if eid and eid in index["engine_ids"]:
        return True
    if at is None:
        return False
    window = timedelta(minutes=ENGINE_MATCH_MINUTES).total_seconds()
    near = index["engine_times"].get("lead:" + lead, []) + index["engine_times"].get("thread:" + thread_id, [])
    return any(abs((at - t).total_seconds()) <= window for t in near)


def _first_recipient(row: Dict[str, Any]) -> str:
    to_field = str(row.get("to_address_email_list") or "")
    for part in to_field.replace(";", ",").split(","):
        if part.strip():
            return part.strip().lower()
    return ""


def _from_lead(row: Dict[str, Any]) -> bool:
    """True for a row the lead sent: ``ue_type`` 2 (pipeline_sweep's
    UE_TYPE_INBOUND); a row without ``ue_type`` when is_outbound's sender,
    then recipients, say it did not come from our inbox. Any other ue_type
    (1 a campaign step, 3 his hand send, 4 a scheduled send, or an unreadable
    value) is ours."""
    from jobs.pipeline_sweep import UE_TYPE_INBOUND, is_outbound

    ue_type = row.get("ue_type")
    if ue_type not in (None, ""):
        try:
            return int(ue_type) == UE_TYPE_INBOUND
        except (TypeError, ValueError):
            return False
    return not is_outbound(row)


def find_examples(rows: List[Dict[str, Any]], start_at: Optional[datetime],
                  index: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Pair each of Lorenzo's replies since ``start_at`` with the lead message
    it answered: the lead's newest row (_from_lead, not an auto-reply)
    since any other email of ours in the thread. Returns {"examples": [...],
    "skipped": [{"email_id", "reason", ...}]}; each example holds build()'s fields, with his row as
    ``reply_row`` and the lead's row as ``lead_message`` (run() reads their
    texts). ``index`` is store_index(). Pure: no store, no network."""
    from jobs.pipeline_sweep import is_auto_reply
    from services.reply_engine.cadence import _sent_by_hand

    threads = {}  # type: Dict[str, List[Dict[str, Any]]]
    for row in rows:
        if row.get("thread_id"):
            threads.setdefault(str(row["thread_id"]), []).append(row)
    examples = []  # type: List[Dict[str, Any]]
    skipped = []  # type: List[Dict[str, Any]]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for thread_id, thread in threads.items():
        thread.sort(key=lambda r: (_time(r) or epoch, str(r.get("id") or "")))
        pending = None  # type: Optional[Dict[str, Any]]   # the lead's newest message since our last email
        for row in thread:
            eaccount = str(row.get("eaccount") or "").strip().lower()
            mine = _sent_by_hand(dict(row, eaccount=eaccount))
            if not mine:
                if _from_lead(dict(row, eaccount=eaccount)):
                    if not is_auto_reply(row):
                        pending = row
                else:
                    pending = None   # a campaign step or scheduled send of ours: never the lead's message
                continue
            answered, pending = pending, None
            at = _time(row)
            eid = str(row.get("id") or "")
            if start_at is not None and (at is None or at < start_at):
                continue   # before the start date: not reported, not recorded
            lead = (str((answered or {}).get("lead") or index["thread_leads"].get(thread_id)
                        or (answered or {}).get("from_address_email") or "").strip().lower()
                    or _first_recipient(row))
            if _engine_sent(index, eid, at, lead, thread_id):
                skipped.append({"email_id": eid, "lead_email": lead, "thread_id": thread_id, "reason": "engine_sent"})
                continue
            if answered is None:
                skipped.append({"email_id": eid, "lead_email": lead, "thread_id": thread_id,
                                "reason": "no_lead_message"})
                continue
            answered_id = str(answered.get("id") or "")
            examples.append({
                "email_id": eid, "sent_at": at, "reply_row": row, "lead_email": lead,
                "thread_id": thread_id, "campaign_id": row.get("campaign_id") or answered.get("campaign_id"),
                "lead_message": answered, "lead_message_id": answered_id or None,
                "lead_message_at": _time(answered), "category": index["labels"].get(answered_id),
                "subject": row.get("subject"), "eaccount": eaccount or None,
            })
    examples.sort(key=lambda e: e["sent_at"])
    return {"examples": examples, "skipped": skipped}


class SeedRefused(Exception):
    """The seed must not run as asked; nothing was read or written."""


def live_send_evidence(store: Any) -> List[str]:
    """Why ``store`` shows the engine has sent for real, as short lines
    (empty: it has not). A cutover to live (``cutover:record`` or
    ``cutover:accepted``), a lead row with an engine ``reply_sent`` (shadow
    writes ``reply_would_send``) or a cadence touch of kind ``done`` that was
    not a shadow record. Read errors propagate: refuse, never guess."""
    from shared import store as store_mod

    out = []  # type: List[str]
    for key in (store_mod.CUTOVER_KEY, store_mod.CUTOVER_ACCEPTED_KEY):
        if store.get(key) is not None:
            out.append("%s is set" % key)
    for key in store.keys("lead:"):
        raw = store.get(key)
        if not isinstance(raw, dict):
            continue
        if any(isinstance(e, dict) and e.get("event") == "reply_sent" for e in raw.get("history") or []):
            out.append("an engine reply_sent on %s" % key)
        elif any(isinstance(t, dict) and t.get("kind") == "done" and not t.get("shadow")
                 for t in (raw.get("cadence") or {}).get("touches") or []):
            out.append("a live cadence touch on %s" % key)
    return out


def run(instantly: Any, store: Any, now: datetime, start_at: Optional[datetime], write: bool = False,
        max_pages: int = MAX_PAGES, log_fn: Any = log_run) -> Dict[str, Any]:
    """Find the examples and, with ``write``, record the new ones. Returns the
    summary (also the Job_Log row, texts left out).

    Raises SeedRefused before any read when the start date is later than
    ``now`` or ``store`` shows the engine has sent for real
    (live_send_evidence): its sends through the thread_reply, show-rate and
    no-show paths are not told apart from Lorenzo's own, so once the engine
    sends live the seed would take them for his."""
    from services.reply_engine import reply_examples

    try:
        settings.require_start_not_future(start_at, now)
    except ValueError as exc:
        raise SeedRefused(str(exc))
    evidence = live_send_evidence(store)
    if evidence:
        raise SeedRefused("the engine has sent live (%s); its replies cannot be told from Lorenzo's, so the "
                          "seed is for before go-live only" % "; ".join(evidence[:3]))
    fetched = fetch_manual_rows(instantly, start_at, max_pages=max_pages)
    found = find_examples(fetched["rows"], start_at, store_index(store))
    out = []  # type: List[Dict[str, Any]]
    skipped = list(found["skipped"])
    for pair in found["examples"]:
        kwargs = dict(pair)
        if reply_examples.exists(store, kwargs["email_id"]):
            out.append({"email_id": kwargs["email_id"], "date": kwargs["sent_at"].isoformat() if kwargs["sent_at"] else None,
                        "lead_email": kwargs["lead_email"], "status": "exists"})
            continue
        # His text, and the lead's: from the list row, else one GET /emails/{id}
        # each (a list page can carry a row without its body).
        kwargs["reply_text"] = reply_examples.fetch_text(instantly, kwargs.pop("reply_row"))
        kwargs["lead_message"] = reply_examples.fetch_text(instantly, kwargs["lead_message"])
        if not str(kwargs["reply_text"] or "").strip():
            skipped.append({"email_id": kwargs["email_id"], "lead_email": kwargs["lead_email"],
                            "thread_id": kwargs["thread_id"], "reason": "no_reply_text"})
            continue
        example = reply_examples.build(source="seed", now=now, **kwargs)
        if reply_examples.exists(store, example["email_id"]):
            status = "exists"
        elif write:
            status = "recorded" if reply_examples.record(store, example) else "exists"
        else:
            status = "would_record"
        out.append(dict(example, status=status))
    counts = {}  # type: Dict[str, int]
    for ex in out:
        counts[ex["status"]] = counts.get(ex["status"], 0) + 1
    summary = {
        "dry_run": not write, "start_at": start_at.isoformat() if start_at is not None else None,
        "rows_read": len(fetched["rows"]), "pages": fetched["pages"], "truncated": fetched["truncated"],
        "examples": out, "skipped": skipped, "counts": counts,
    }
    log_fn("jobs.%s" % JOB, "ok" if not fetched["truncated"] else "truncated", {
        "dry_run": not write, "start_at": summary["start_at"], "rows_read": summary["rows_read"],
        "pages": summary["pages"], "truncated": summary["truncated"], "counts": counts,
        "skipped": [{"email_id": s["email_id"], "reason": s["reason"]} for s in skipped][:50],
        "email_ids": [ex["email_id"] for ex in out][:50]})
    return summary


def _clip(text: Any, n: int = 90) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= n else flat[:n - 3] + "..."


def _print(summary: Dict[str, Any]) -> None:
    print("%s start=%s rows_read=%d pages=%d%s" % (
        "DRY RUN (nothing written; --write records)" if summary["dry_run"] else "WRITE",
        summary["start_at"], summary["rows_read"], summary["pages"],
        " TRUNCATED (raise --pages)" if summary["truncated"] else ""))
    for ex in summary["examples"]:
        print("-" * 100)
        print("%s  %s  %s  %s  category=%s  [%s]" % ((ex.get("date") or "")[:16], ex.get("lead_email"),
                                                     ex.get("campaign_key") or ex.get("campaign_id"),
                                                     ex.get("offer"), ex.get("category") or "-", ex["status"]))
        if ex["status"] != "exists":
            print("  lead: %s" % _clip(ex.get("lead_message")))
            print("  you:  %s" % _clip(ex.get("reply")))
    if summary["skipped"]:
        print("-" * 100)
        for s in summary["skipped"]:
            print("skipped %s (%s): %s" % (s["email_id"], s.get("lead_email"), s["reason"]))
    print("counts: %s" % (summary["counts"] or "{}"))


LIVE_FLAG = "--i-am-lorenzo-live"


def _refuse(why: str, log_fn: Any = log_run) -> int:
    print("REFUSED: %s" % why)
    log_fn("jobs.%s" % JOB, "refused", {"why": why})
    return 2


def _copy_shadow_to_live(write: bool, live_ok: bool, shadow_store: Any = None, live_store: Any = None) -> int:
    """Runbook deployment.md step 5: after cutover.py --apply, copy every
    reply example from the shadow Dict into the live one (set_if_absent).
    Refuses the live Dict without --i-am-lorenzo-live on a write, and before
    the live store has a cutover:record (the cutover needs it empty)."""
    from services.reply_engine import reply_examples
    from shared import store as store_mod

    if write and not live_ok:
        return _refuse("writing to the live Dict needs %s (Lorenzo only)" % LIVE_FLAG)
    if shadow_store is None:
        shadow_store = store_mod.open_modal_store("shadow", create_if_missing=False)
    if live_store is None:
        live_store = store_mod.open_modal_store("live", create_if_missing=False)
    if not live_store.get(store_mod.CUTOVER_KEY):
        return _refuse("the live store has no %s: run cutover.py --apply first (it needs an empty live store)"
                       % store_mod.CUTOVER_KEY)
    res = reply_examples.copy_all(shadow_store, live_store, write=write)
    print("%s: %d example(s) %s, %d already in live" % (
        "WRITE" if write else "DRY RUN (nothing written; --write %s copies)" % LIVE_FLAG, len(res["copied"]),
        "copied" if write else "would be copied", len(res["present"])))
    log_run("jobs.%s" % JOB, "copied" if write else "copy_dry_run",
            {"copied": len(res["copied"]), "present": len(res["present"])})
    return 0


def main(argv: Optional[List[str]] = None, store: Any = None, instantly: Any = None,
         live_store: Any = None) -> int:
    """``store`` / ``instantly`` / ``live_store`` are test seams; the CLI builds them."""
    p = argparse.ArgumentParser(prog=JOB, description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="the default: print what would be recorded, write nothing")
    p.add_argument("--write", action="store_true", help="record the new examples in the engine store")
    p.add_argument("--start-at", default=None,
                   help="ISO date/datetime (a date is midnight CT). Default: POLLER_START_AT, else %s"
                        % settings.POLLER_START_AT_DEFAULT)
    p.add_argument("--pages", type=int, default=MAX_PAGES, help="max pages of %d manual rows to read" % PAGE_SIZE)
    p.add_argument("--store", help="path to a JSON store (default: STORE_PATH or .tmp/store.json)")
    p.add_argument("--modal", action="store_true",
                   help="use the deployed Modal Dict of the current mode (shadow unless MODE=live and "
                        "ALLOW_LIVE_WRITES=1) instead of the local store; the live Dict needs %s" % LIVE_FLAG)
    p.add_argument("--copy-shadow-to-live", action="store_true",
                   help="cutover step: copy the examples from the shadow Dict to the live Dict (after "
                        "cutover.py --apply); dry run unless --write %s" % LIVE_FLAG)
    p.add_argument(LIVE_FLAG, dest="live_ok", action="store_true",
                   help="Lorenzo only: allow the live Dict (--modal in live mode, --copy-shadow-to-live --write)")
    p.add_argument("--as-of", help="ISO timestamp for recorded_at (default: now, CT)")
    p.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = p.parse_args(argv)

    write = bool(args.write) and not args.dry_run
    if not write:
        from shared.job_log import use_scratch_logs

        use_scratch_logs("%s_dryrun" % JOB)
    if args.copy_shadow_to_live:
        try:
            return _copy_shadow_to_live(write, args.live_ok, shadow_store=store, live_store=live_store)
        except Exception as exc:  # noqa: BLE001 - a read error is a refusal, never a guess
            return _refuse("could not read the Dicts: %s: %s" % (type(exc).__name__, exc))
    try:
        start_at = settings.poller_start_at() if args.start_at is None else settings.parse_start_at(args.start_at)
    except ValueError as exc:
        return _refuse(str(exc))
    now = slot_rules.parse_iso(args.as_of) if args.as_of else datetime.now(settings.TZ)
    if store is None:
        from shared.store import JsonFileStore, effective_mode, get_store, open_modal_store

        if args.modal:
            mode = effective_mode()
            if mode == "live" and not args.live_ok:
                return _refuse("the live Dict needs %s (Lorenzo only)" % LIVE_FLAG)
            store = open_modal_store(mode, create_if_missing=False)
        else:
            store = JsonFileStore(args.store) if args.store else get_store()
    if settings.is_live() and not args.live_ok:
        return _refuse("MODE=live and ALLOW_LIVE_WRITES=1 are set; a live run needs %s (Lorenzo only)" % LIVE_FLAG)
    close = None
    if instantly is None:
        from shared.instantly import default_client

        instantly = default_client()
        close = getattr(instantly, "close", None)
    try:
        summary = run(instantly, store, now, start_at, write=write, max_pages=args.pages)
    except SeedRefused as exc:
        return _refuse(str(exc))
    finally:
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - closing a client must not fail the run
                logger.warning("could not close the Instantly client")
    if args.json:
        print(json.dumps(summary, indent=1, default=str))
    else:
        _print(summary)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
