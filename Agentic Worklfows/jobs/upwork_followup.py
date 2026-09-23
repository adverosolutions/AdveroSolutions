"""Upwork follow-up pipeline CLI (U4). Drafts Lorenzo's Upwork replies and
follow-ups; he sends every one himself. Nothing here writes to Upwork.

Laptop only. It is not a Modal schedule: the Upwork MCP exists only inside a
Claude session, so the morning run is a Claude desktop scheduled task (08:30 CT
weekdays, prompt in services/upwork_followup/scheduled_task_prompt.md) that
runs the read-only collect, then --ingest, then the tick.

CLI (from "Agentic Worklfows/"):
    python3 -m jobs.upwork_followup --print-collect          # the read-only MCP calls to make
    python3 -m jobs.upwork_followup --ingest .tmp/upwork_followup/raw.json
    python3 -m jobs.upwork_followup                          # same as --dry-run (the default)
    python3 -m jobs.upwork_followup --dry-run                # no model call, nothing saved, no card
    python3 -m jobs.upwork_followup --run                    # (alias --now) drafts, cards; spends tokens
    python3 -m jobs.upwork_followup --status
    python3 -m jobs.upwork_followup --stage <room_id | client/title fragment> <stage>
    python3 -m jobs.upwork_followup --stop <room_id | fragment>
    python3 -m jobs.upwork_followup --resume <room_id | fragment>
    python3 -m jobs.upwork_followup --enroll <room_id | fragment>

A fragment is matched case-insensitively against the client name and the job
title. No match, or more than one, changes nothing and lists the candidates.

``--json`` prints the tick result as one JSON document on stdout, a run skipped
for the lock included (the token note then goes to stderr).

Python 3.9. ``now`` is injected (``--as-of``); the only real-clock read is the
tick's run lease, which never uses ``--as-of``.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # run as a script: make "shared" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import slots  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.store import get_store  # noqa: E402

from services.upwork_followup import collect, sequence, tick  # noqa: E402

logger = logging.getLogger("jobs.upwork_followup")

JOB_NAME = "upwork_followup"
TOKEN_NOTE = ("Note: this run spends Anthropic tokens (Sonnet drafts, Haiku classification). "
              "--dry-run makes no model call.")


# ------------------------------------------------------------------ matching
def _candidate(room_id: str, client: Any, job_title: Any) -> Dict[str, str]:
    return {"room_id": str(room_id), "client": str(client or ""), "job_title": str(job_title or "")}


def thread_candidates(store, snapshot: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Every enrolled thread, with its job title from the snapshot when the
    room is in it, else the title the tick saved on the thread."""
    rooms = dict((r.get("room_id"), r) for r in ((snapshot or {}).get("rooms") or []) if isinstance(r, dict))
    out = []
    for key in sorted(store.keys(sequence.PREFIX)):
        if key in tick.META_KEYS:
            continue
        thread = store.get(key)
        if not isinstance(thread, dict):
            continue
        rid = thread.get("room_id") or key[len(sequence.PREFIX):]
        room = rooms.get(rid) or {}
        out.append(_candidate(rid, thread.get("client") or room.get("client"),
                              room.get("job_title") or thread.get("job_title")))
    return out


def room_candidates(snapshot: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [_candidate(r.get("room_id"), r.get("client"), r.get("job_title"))
            for r in ((snapshot or {}).get("rooms") or []) if isinstance(r, dict) and r.get("room_id")]


def match(target: str, candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """An exact room id wins; otherwise a case-insensitive fragment of the
    client name or the job title."""
    target = (target or "").strip()
    exact = [c for c in candidates if c["room_id"] == target]
    if exact:
        return exact
    frag = target.lower()
    if not frag:
        return []
    return [c for c in candidates if frag in c["client"].lower() or frag in c["job_title"].lower()]


def _describe(c: Dict[str, str]) -> str:
    return "%s | %s | room %s" % (c["client"] or "unknown client", c["job_title"] or "job title unknown",
                                  c["room_id"])


def pick(target: str, candidates: List[Dict[str, str]], out=None) -> Optional[Dict[str, str]]:
    """The one matching candidate, or None after printing why nothing changed."""
    out = out or sys.stdout
    found = match(target, candidates)
    if len(found) == 1:
        return found[0]
    if not found:
        print("No job matches %r. Nothing changed. Candidates:" % target, file=out)
        shown = candidates
    else:
        print("%r matches %d jobs. Nothing changed. Use the room id of one of these:" % (target, len(found)),
              file=out)
        shown = found
    for c in shown:
        print("  %s" % _describe(c), file=out)
    if not shown:
        print("  (none)", file=out)
    return None


# ------------------------------------------------------------------ commands
def _load_snapshot(path: Optional[str]) -> Optional[Dict[str, Any]]:
    snapshot, _err = collect.load_snapshot(path)
    return snapshot


def cmd_print_collect() -> int:
    print(collect.collect_instructions())
    return 0


def cmd_ingest(source: str, now: datetime, snapshot_path: Optional[str]) -> int:
    try:
        with open(source, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        print("could not read %s: %s. Nothing was written." % (source, exc), file=sys.stderr)
        log_run(JOB_NAME, "ingest_refused", {"input": source, "reason": str(exc)[:300]})
        return 1
    try:
        snap = collect.ingest(raw, now)
        target = collect.write_snapshot(snap, snapshot_path)
    except collect.IngestError as exc:
        print("refusing to write the snapshot: %s" % exc, file=sys.stderr)
        log_run(JOB_NAME, "ingest_refused", {"input": source, "reason": str(exc)[:300]})
        return 1
    sections = snap.get("sections") or {}

    def word(value):
        return "yes" if value is True else ("not collected" if value is None else "NO")

    print("wrote %s: %d rooms in scope (generated_at %s)" % (target, len(snap.get("rooms") or []),
                                                             snap.get("generated_at")))
    print("  omitted: %d with no linked proposal, %d with a contract" % (
        int(snap.get("omitted_unlinked") or 0), int(snap.get("omitted_contracted") or 0)))
    print("  sections: %s" % ", ".join("%s %s" % (k, word(sections.get(k))) for k in collect.SECTION_KEYS))
    if snap.get("truncated"):
        print("  truncated: %s" % ", ".join(snap.get("truncated_sections") or []))
    if snap.get("missing_messages"):
        print("  messages missing for: %s" % ", ".join(snap["missing_messages"]))
    if snap.get("link_errors"):
        print("  proposals not linked (get_room failed): %s" % ", ".join(snap["link_errors"]))
    log_run(JOB_NAME, "ingest", {
        "rooms": len(snap.get("rooms") or []),
        "omitted_unlinked": snap.get("omitted_unlinked"),
        "omitted_contracted": snap.get("omitted_contracted"),
        "sections": sections,
        "truncated": bool(snap.get("truncated")),
        "path": str(target),
    })
    return 0


def status_rows(store, snapshot: Optional[Dict[str, Any]], now: datetime) -> List[List[str]]:
    """One row per thread, plus one per room the snapshot shows blocked that
    has no thread (sequence.py never enrols a blocked room). "next due" says
    "blocked on Upwork since <date>" for a room the snapshot shows blocked (or,
    once it has left the snapshot, a thread sequence.py closed as
    ``room_blocked``), the closed line for a closed thread whose room is open
    again, and "reply skipped on <date>; client waiting since <date>" for a
    client still waiting after the reply drafted for them was dropped."""
    rows = []
    titles = dict((c["room_id"], c) for c in thread_candidates(store, snapshot))
    blocked_ids = set(b["room_id"] for b in tick.blocked_rooms(snapshot or {}))
    rooms = dict((r.get("room_id"), dict(r, blocked=True) if r.get("room_id") in blocked_ids else r)
                 for r in ((snapshot or {}).get("rooms") or []) if isinstance(r, dict))
    seen = set()
    for key in sorted(store.keys(sequence.PREFIX)):
        if key in tick.META_KEYS:
            continue
        thread = store.get(key)
        if not isinstance(thread, dict):
            continue
        rid = thread.get("room_id") or key[len(sequence.PREFIX):]
        cand = titles.get(rid) or _candidate(rid, thread.get("client"), thread.get("job_title"))
        due = sequence.due_summary(thread, now)
        pending = thread.get("pending") or None
        if pending:
            what = "T%s" % pending.get("touch") if pending.get("kind") == "touch" else pending.get("kind")
            pend = "%s since %s" % (what, str(pending.get("issued_at") or "")[:10])
        else:
            pend = "-"
        blocked = tick.blocked_since(thread, rooms.get(rid))
        seen.add(rid)
        rows.append([cand["client"] or "unknown", cand["job_title"] or "-",
                     "%s (%s)" % (thread.get("stage"), thread.get("stage_set_by")),
                     str(thread.get("status")), pend, tick.due_text(due, thread, blocked), rid])
    for rid in sorted(blocked_ids - seen):
        room = rooms[rid]
        rows.append([str(room.get("client") or "unknown"), str(room.get("job_title") or "-"), "-", "not enrolled",
                     "-", tick.due_text({}, None, tick.blocked_since(None, room)), rid])
    rows.sort(key=lambda r: (r[0].lower(), r[6]))
    return rows


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def format_table(rows: List[List[str]]) -> str:
    header = ["client", "job title", "stage (set by)", "status", "pending", "next due", "room"]
    limits = [28, 40, 30, 18, 20, 72, 40]
    table = [header] + [[_clip(c, limits[i]) for i, c in enumerate(r)] for r in rows]
    widths = [max(len(r[i]) for r in table) for i in range(len(header))]
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip() for r in table]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def cmd_status(store, snapshot_path: Optional[str], now: datetime) -> int:
    rows = status_rows(store, _load_snapshot(snapshot_path), now)
    if not rows:
        print("No Upwork threads yet. Run the collect, --ingest and the tick first.")
        return 0
    print(format_table(rows))
    return 0


def cmd_stage(store, target: str, stage: str, snapshot_path: Optional[str], now: datetime) -> int:
    if stage not in sequence.STAGES:
        print("unknown stage %r. Use one of: %s" % (stage, ", ".join(sequence.STAGES)), file=sys.stderr)
        return 2
    chosen = pick(target, thread_candidates(store, _load_snapshot(snapshot_path)))
    if chosen is None:
        return 1
    try:
        thread, acts = sequence.set_stage(store, chosen["room_id"], stage, now, by="lorenzo")
    except (ValueError, LookupError) as exc:
        print("Nothing changed: %s" % exc, file=sys.stderr)
        return 1
    moved = [a for a in acts if a.get("type") == "stage_change"]
    if moved:
        print("Moved %s from %s to %s (set by lorenzo; the engine will not override it)." % (
            _describe(chosen), moved[0].get("from"), stage))
    else:
        print("%s was already in %s; it is now pinned as your choice." % (_describe(chosen), stage))
    if any(a.get("type") == "withdraw_pending" for a in acts):
        print("The pending draft was withdrawn.")
    log_run(JOB_NAME, "stage", {"room_id": chosen["room_id"], "stage": stage, "moved": bool(moved)})
    return 0


def cmd_stop_resume(store, which: str, target: str, snapshot_path: Optional[str], now: datetime) -> int:
    chosen = pick(target, thread_candidates(store, _load_snapshot(snapshot_path)))
    if chosen is None:
        return 1
    fn = sequence.stop if which == "stop" else sequence.resume
    try:
        thread, acts = fn(store, chosen["room_id"], now)
    except (ValueError, LookupError) as exc:
        print("Nothing changed: %s" % exc, file=sys.stderr)
        return 1
    print("%s %s: status %s, stage %s." % ("Stopped" if which == "stop" else "Resumed", _describe(chosen),
                                          thread.get("status"), thread.get("stage")))
    log_run(JOB_NAME, which, {"room_id": chosen["room_id"], "status": thread.get("status")})
    return 0


def cmd_enroll(store, target: str, snapshot_path: Optional[str], now: datetime) -> int:
    snapshot, err = collect.load_snapshot(snapshot_path)
    if err:
        print("No snapshot (%s): --enroll needs the room in the current snapshot. Run --ingest first." % err,
              file=sys.stderr)
        return 1
    chosen = pick(target, room_candidates(snapshot))
    if chosen is None:
        return 1
    room = next(r for r in snapshot["rooms"] if r.get("room_id") == chosen["room_id"])
    try:
        sequence.enroll(store, room, now)
    except (ValueError, LookupError) as exc:
        print("Nothing changed: %s" % exc, file=sys.stderr)
        return 1
    print("Enrolled %s. The next tick reads its history and drafts what is due." % _describe(chosen))
    log_run(JOB_NAME, "enroll", {"room_id": chosen["room_id"]})
    return 0


def cmd_tick(mode: str, now: datetime, snapshot_path: Optional[str], as_json: bool) -> int:
    if mode == "run":
        # under --json stdout carries only the JSON document
        out = sys.stderr if as_json else sys.stdout
        print(TOKEN_NOTE, file=out)
        out.flush()
    result = tick.run_tick(now, mode, snapshot_path=snapshot_path)
    if as_json:
        print(tick.to_json(result))
        return 1 if result.get("snapshot_error") else 0
    if result.get("status") == "locked":
        held = result.get("locked") or {}
        print("Another --run is still in progress (lock taken %s, free by %s at the latest%s). This run did "
              "nothing; wait for it to finish." % (
                  held.get("acquired_at"), held.get("free_by") or held.get("expires_at"),
                  "; its time stamps are ahead of this machine's clock" if held.get("clock_problem") else ""))
        return 0
    print("upwork_followup %s: %s" % (mode, result["status"]))
    print(tick.summary_text(result))
    if mode == "run":
        print("Cards: %s." % tick.cards_note(result))
    for item in result["check"]:
        print("Check: %s in room %s" % (item["reason"], item["room_id"]))
    for err in result["errors"]:
        print("Error: %s" % err)
    return 1 if result.get("snapshot_error") else 0


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="upwork_followup", description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--print-collect", action="store_true", help="print the read-only MCP calls to make")
    g.add_argument("--ingest", metavar="RAW", help="turn the raw MCP JSON file into the snapshot")
    g.add_argument("--dry-run", action="store_true",
                   help="the default: run the tick on a copy of the store, no model call, no card")
    g.add_argument("--run", "--now", dest="run", action="store_true",
                   help="run the tick for real: drafts (spends Anthropic tokens), store, cards")
    g.add_argument("--status", action="store_true", help="list every thread with its stage and next due date")
    g.add_argument("--stage", nargs=2, metavar=("TARGET", "STAGE"),
                   help="move a job to a stage (%s)" % ", ".join(sequence.STAGES))
    g.add_argument("--stop", metavar="TARGET", help="stop a thread and withdraw its pending draft")
    g.add_argument("--resume", metavar="TARGET", help="restart a stopped or closed thread")
    g.add_argument("--enroll", metavar="TARGET", help="enrol a room from the current snapshot")
    p.add_argument("--as-of", help="ISO timestamp to evaluate at (default: now); the --run lease always uses "
                                   "the real clock")
    p.add_argument("--snapshot", help="snapshot path (default: .tmp/%s)" % collect.SNAPSHOT_NAME)
    p.add_argument("--json", action="store_true",
                   help="print the tick result as JSON on stdout (a run skipped for the lock too)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    now = slots.parse_iso(args.as_of) if args.as_of else datetime.now(timezone.utc)

    if args.print_collect:
        return cmd_print_collect()
    if args.ingest:
        return cmd_ingest(args.ingest, now, args.snapshot)
    if args.status:
        return cmd_status(get_store(), args.snapshot, now)
    if args.stage:
        return cmd_stage(get_store(), args.stage[0], args.stage[1], args.snapshot, now)
    if args.stop:
        return cmd_stop_resume(get_store(), "stop", args.stop, args.snapshot, now)
    if args.resume:
        return cmd_stop_resume(get_store(), "resume", args.resume, args.snapshot, now)
    if args.enroll:
        return cmd_enroll(get_store(), args.enroll, args.snapshot, now)
    return cmd_tick("run" if args.run else "dry-run", now, args.snapshot, args.json)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
