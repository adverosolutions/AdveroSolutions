"""precall_tick: the scheduled job behind S6 (pre-call brief) and S7 (proposal).

    python3 -m jobs.precall_tick --dry-run
    python3 -m jobs.precall_tick --dry-run --now 2026-09-23T10:30:00-05:00
    python3 -m jobs.precall_tick --dry-run --appointments jobs/tests/fixtures/appointments_2026-09-21.json
    python3 -m jobs.precall_tick --dry-run --proposal-for eqlug7qn67rnjdppja91ffuto0 --transcript call.txt

Every run:
  1. reads the Discovery Call window from GHL (``jobs.appointments_tick.fetch_appointments``,
     the same read the S4/S5 tick uses) AND the hand-made calls on Lorenzo's own
     Google Calendar (``precall.manual_calls``). The second source is included
     here and excluded there on purpose: a brief is internal, so briefing
     Lorenzo about a call he booked himself is safe, while emailing that
     prospect from the show-rate ladder is not;
  2. builds and delivers a pre-call brief for every call starting inside the
     next 60 minutes that has not been briefed yet (ntfy card, guarded GHL
     note, full text filed under .tmp/precall/);
  3. for every call that has already ended today, drafts the proposal and the
     SOP-009 verbal-commit emails and files them under .tmp/proposals/;
  4. writes one Job_Log row and sends one digest.

Nothing in this job can reach a prospect. The only outbound calls are
``ghl.create_note`` and ``notify``, both guarded by shared.settings.guard_write,
and the proposal is a file.

``--dry-run`` forces MODE=shadow, NOTIFY=off, LLM_FAKE=1, a scratch store and
scratch logs: no write of any kind and no billed model call. It still issues the
read-only Instantly GETs that build the thread, unless you also pass --no-read.
``--llm`` opts a dry run back into the billed Opus polish, deliberately and
explicitly.

Runs every 5 minutes in production. On Modal, one container at a time
(modal_app.MODAL_MAX_CONTAINERS: the file lock ``_run_lock`` is on the
container's own disk and only serialises runs on one machine).
"""
import argparse
import fcntl
import json
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jobs.precall_tick")

JOB = "precall_tick"
# How long after the start a call counts as "over" and the proposal pass picks
# it up. The Discovery Call is 15 minutes with a 15-minute buffer.
PROPOSAL_AFTER = timedelta(minutes=20)
# "Same day as the call" (Blueprint S7) means the end of the call's own day in
# Central, not a rolling window: a recap that lands two days later is worse
# than none, and one written the morning after is not what S7 promises.
# A late-evening call still gets a floor so it is not born expired.
MIN_PROPOSAL_WINDOW = timedelta(hours=3)


def _force_shadow(llm_ok: bool = False) -> None:
    """Everything a dry run promises, including the billed model call.

    LLM_FAKE was the one gate this did not close: ``shared.settings.load_env()``
    puts the real ANTHROPIC_API_KEY into the process at import, so a dry run
    without the runbook's ``LLM_FAKE=1`` prefix reached the real-client branch
    of ``shared.llm.complete`` once per due proposal, on claude-opus-5-5, while
    the docstring promised no HTTP request at all. services/reply_engine/replay.py
    sets the same variable for the same reason; this is the house pattern.
    """
    os.environ["MODE"] = "shadow"
    os.environ.pop("ALLOW_LIVE_WRITES", None)
    os.environ["NOTIFY"] = "off"
    if not llm_ok:
        os.environ.setdefault("LLM_FAKE", "1")
    from shared.job_log import use_scratch_logs

    use_scratch_logs("precall_tick_dryrun")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="precall_tick", description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="force MODE=shadow; propose and log, never write")
    p.add_argument("--now", help="ISO 8601 clock to run at (default: real time, America/Chicago)")
    p.add_argument("--appointments", help="JSON file with {'appointments': [...]} used when GHL returns nothing")
    p.add_argument("--store", help="path of the JSON store (default STORE_PATH or .tmp/store.json)")
    p.add_argument("--lead-minutes", type=int, default=None, help="how early the brief goes out (default 60)")
    p.add_argument("--no-proposals", action="store_true", help="briefs only, skip the proposal pass")
    p.add_argument("--proposal-for", help="force a proposal draft for this appointment id, whatever the clock says")
    p.add_argument("--transcript", help="Fireflies transcript file for --proposal-for")
    p.add_argument("--notes", help="file with Lorenzo's own call notes for --proposal-for")
    p.add_argument("--facts", help="lead facts CSV (default: the list factory export, or LEAD_FACTS_CSV)")
    p.add_argument("--no-read", action="store_true", help="skip the Instantly reads (offline)")
    p.add_argument("--llm", action="store_true",
                   help="let a --dry-run make the billed claude-opus-5-5 polish call (off by default)")
    p.add_argument("--no-notify", action="store_true", help="skip the digest notification")
    p.add_argument("--scheduled", action="store_true",
                   help="the unattended 5-minute run: push only when this run produced a brief, a proposal "
                        "or an error (a quiet run pushes nothing; 288 idle digests a day otherwise)")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


@contextmanager
def _run_lock():
    """One tick at a time: two overlapping runs would claim the same brief."""
    from shared.paths import tmp_dir

    try:
        lock_path = Path(tmp_dir()) / "precall_tick.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(str(lock_path), "a+")
    except OSError as exc:  # noqa: BLE001
        logger.warning("could not open the tick lock (%s); running unlocked", exc)
        yield False
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield True
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# ------------------------------------------------------------ inputs
def _same_call(appointment: Dict[str, Any]) -> Optional[str]:
    """(lead email, start rounded to the minute): the identity of a real call.

    The two appointment sources use different id spaces - the manual row's id is
    the Google Calendar event id, the GHL row's is GHL's own appointment id - so
    de-duplicating on id alone can never match them, and one call present in
    both was briefed twice, noted twice on one contact and proposed on twice.
    """
    from services.reply_engine import precall

    email = str(appointment.get("email") or appointment.get("lead_email") or "").strip().lower()
    start = precall._normalise_start(appointment.get("start_iso"))  # noqa: SLF001 - one start normaliser
    if not email or not start:
        return None
    return "%s|%s" % (email, start[:16])


def load_appointments(ghl, now: datetime, fixture: Optional[str]) -> Dict[str, Any]:
    """GHL Discovery Call bookings plus the hand-made Google Calendar calls.

    The GHL row always wins: it is the live record, the manual seed in
    config/ids.json is a hand-maintained snapshot.
    """
    from jobs import appointments_tick as s4
    from services.reply_engine import precall

    fetched = s4.fetch_appointments(ghl, now, fixture)
    appts = list(fetched["appointments"])
    seen_ids = set(str(a.get("id")) for a in appts)
    seen_calls = set(c for c in (_same_call(a) for a in appts) if c)
    manual = []  # type: List[Dict[str, Any]]
    duplicates = []  # type: List[Dict[str, Any]]
    for row in precall.manual_calls(now):
        same = _same_call(row)
        if str(row.get("id")) in seen_ids or (same is not None and same in seen_calls):
            duplicates.append({"id": str(row.get("id")), "email": row.get("email"), "start": row.get("start_iso")})
            continue
        manual.append(row)
        seen_ids.add(str(row.get("id")))
        if same is not None:
            seen_calls.add(same)
    stale = precall.stale_manual_calls(now)
    return {
        "source": fetched["source"],
        "error": fetched.get("error"),
        "appointments": appts + manual,
        "ghl_count": len(appts),
        "manual_count": len(manual),
        "manual_duplicates": duplicates,
        "manual_stale": [str(r.get("id")) for r in stale],
        "cancelled": fetched.get("cancelled") or [],
    }


def held_evidence(store, appointment: Dict[str, Any]) -> str:
    """What the no-show state machine knows about this call.

    'zoom' when a join was seen, 'no_show' when it was flagged, 'unknown'
    otherwise - which is today's normal case, because Zoom is not connected to
    GHL and there is no telemetry at all.

    ``done`` is the recovery sequence's terminal state and is only ever reached
    FROM ``no_show`` (no_show.cancel_recovery rewrites it when the lead replies,
    cancel_recovery_for_rebooking when they rebook, _apply_after when the ladder
    finishes). Reading it as 'unknown' meant a lead who missed the call and then
    emailed back got a full proposal, with a "What you told me" recap, for a
    call that never happened.
    """
    if store is None:
        return "unknown"
    try:
        from services.reply_engine import no_show

        state = store.get(no_show.state_key(str(appointment.get("id")))) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the no-show state: %s", exc)
        return "unknown"
    value = str(state.get("state") or "")
    if value in ("showed", "late_show"):
        return "zoom"
    if value == "no_show":
        return "no_show"
    if value == "done":
        if str(state.get("previous_state") or "") in ("showed", "late_show"):
            return "zoom"
        return "no_show"
    return "unknown"


def proposal_due(appointment: Dict[str, Any], now: datetime) -> bool:
    from shared import slots
    from shared.settings import TZ

    try:
        start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    except (ValueError, TypeError, KeyError):
        return False
    if appointment.get("cancelled") or str(appointment.get("ghl_status") or "").lower() in ("cancelled", "canceled"):
        return False
    from services.reply_engine import precall

    if str(appointment.get("response_status") or "").strip().lower() in precall.REFUSED_STATUSES:
        return False
    opens = start + PROPOSAL_AFTER
    closes = max(_end_of_day(start), opens + MIN_PROPOSAL_WINDOW)
    return opens <= now <= closes


def _end_of_day(when: datetime) -> datetime:
    from shared.settings import TZ

    naive = datetime(when.year, when.month, when.day, 23, 59, 59)
    try:
        return TZ.localize(naive)
    except Exception:  # noqa: BLE001 - DST edge
        return TZ.localize(naive, is_dst=False)


# ------------------------------------------------------------------ run
def tick(
    now: datetime,
    store,
    ghl,
    appointments: List[Dict[str, Any]],
    instantly=None,
    lead_minutes: Optional[int] = None,
    do_proposals: bool = True,
    proposal_for: Optional[str] = None,
    transcript_path: Optional[str] = None,
    notes_path: Optional[str] = None,
    facts_path: Optional[str] = None,
    notify_fn=None,
    instantly_error: Optional[str] = None,
) -> Dict[str, Any]:
    """Pure-ish core: everything the CLI does after loading inputs."""
    from services.reply_engine import precall, proposal as proposal_mod
    from shared import slots
    from shared.settings import TZ

    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    lead_minutes = precall.DEFAULT_LEAD_MINUTES if lead_minutes is None else lead_minutes
    offline_reason = instantly_error or "offline mode, --no-read"
    out = {
        "now": now.isoformat(),
        "mode": os.environ.get("MODE", "shadow"),
        "appointments": len(appointments),
        "briefs": [], "briefs_skipped": [], "proposals": [], "proposals_skipped": [], "errors": [],
    }  # type: Dict[str, Any]

    for appt in appointments:
        try:
            if not precall.due(appt, now, lead_minutes):
                continue
            if precall.already_briefed(store, appt.get("id"), appt.get("start_iso")):
                out["briefs_skipped"].append({"id": str(appt.get("id")), "reason": "already_briefed"})
                continue
            brief = precall.build_brief(appt, now, instantly=instantly, ghl=ghl, facts_path=facts_path,
                                        read_thread=instantly is not None, offline_reason=offline_reason)
            res = precall.deliver(brief, store, ghl=ghl, now=now, notify_fn=notify_fn)
            out["briefs"].append({
                "id": brief.appointment_id, "company": brief.company, "start": brief.start_iso,
                "minutes_out": brief.meta.get("minutes_out"), "offer": brief.campaign_key,
                "thread_messages": brief.meta.get("thread_messages"), "problems": brief.problems,
                "objections": [o["id"] for o in brief.objections if o["id"] != "framework"][:3],
                "delivered": {k: v for k, v in res.items()
                              if k in ("claimed", "file", "skipped", "delivered", "claim_released")},
                "note": _shape(res.get("note")), "notified": _shape(res.get("notified")),
                "source": brief.source,
            })
        except Exception as exc:  # noqa: BLE001 - one bad booking must not take the tick
            logger.exception("brief failed for %s", appt.get("id"))
            out["errors"].append({"where": "brief", "id": str(appt.get("id")), "error": str(exc)[:400]})

    if do_proposals:
        notes = _read_file(notes_path)
        for appt in appointments:
            try:
                forced = proposal_for is not None and str(appt.get("id")) == str(proposal_for)
                if not forced and not proposal_due(appt, now):
                    continue
                # The claim is checked HERE, before gather_inputs (two Instantly
                # GETs) and build_proposal (a billed claude-opus-5-5 turn), exactly
                # as the brief pass checks already_briefed. Taking it inside
                # deliver() meant the 5-minute tick paid for a proposal on every
                # pass of the whole proposal window - 146 model calls for one
                # 11:30 call - and discarded all but the first.
                call_date = proposal_mod.call_date_for(appt, now)
                if not forced and proposal_mod.already_drafted(store, appt.get("id"), call_date):
                    out["proposals_skipped"].append({"id": str(appt.get("id")), "reason": "already_drafted"})
                    continue
                evidence = held_evidence(store, appt)
                if evidence == "no_show" and not forced:
                    out["proposals"].append({"id": str(appt.get("id")), "skipped": "no_show"})
                    continue
                inputs = proposal_mod.gather_inputs(
                    (appt.get("email") or "").strip().lower() or None,
                    instantly=instantly,
                    transcript_path=transcript_path if forced else None,
                    notes=notes if forced else None,
                )
                # The brief for this same call resolved the campaign from the
                # Instantly lead record; reuse that answer so the two documents
                # can never quote two different offers for one call.
                campaign_key = _briefed_offer(out, appt)
                draft = proposal_mod.build_proposal(appt, now, inputs=inputs, held_evidence=evidence,
                                                    instantly=instantly, campaign_key=campaign_key,
                                                    call_date=call_date)
                verbal = proposal_mod.verbal_commit_drafts(draft, now)
                res = proposal_mod.deliver(draft, store=store, ghl=ghl, now=now, notify_fn=notify_fn, verbal=verbal,
                                           replace=forced)
                out["proposals"].append({
                    "id": draft.appointment_id, "company": draft.company, "offer": draft.campaign_key,
                    "source": draft.source, "held_evidence": draft.held_evidence, "model": draft.model,
                    "problems": draft.problems, "notes": draft.meta.get("notes_for_lorenzo"),
                    "verbal_blocked": [v.key for v in verbal if not v.sendable],
                    "skipped": res.get("skipped"),
                    "delivered": {k: v for k, v in res.items()
                                  if k in ("claimed", "file", "skipped", "replaced")},
                })
            except Exception as exc:  # noqa: BLE001
                logger.exception("proposal failed for %s", appt.get("id"))
                out["errors"].append({"where": "proposal", "id": str(appt.get("id")), "error": str(exc)[:400]})
    return out


def _briefed_offer(result: Dict[str, Any], appointment: Dict[str, Any]) -> Optional[str]:
    """The campaign key the brief pass resolved for this call in this run."""
    for brief in result.get("briefs") or []:
        if str(brief.get("id")) == str(appointment.get("id")):
            return brief.get("offer")
    return None


def _shape(value: Any) -> Any:
    """Keep the digest readable: a guard record, not the whole payload."""
    if isinstance(value, dict):
        for key in ("shadow", "skipped", "error", "sent", "test"):
            if key in value:
                return {key: value[key]}
        return {"keys": sorted(value)[:4]}
    return value


def _read_file(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:  # noqa: BLE001
        logger.warning("could not read %s: %s", path, exc)
        return None


def digest_text(result: Dict[str, Any]) -> str:
    lines = ["precall_tick %s (MODE=%s)" % (result["now"], result["mode"]),
             "%d call(s) in the window" % result["appointments"]]
    for brief in result["briefs"]:
        lines.append("BRIEF %s at %s (%s min out, %s): %d thread messages, expect %s"
                     % (brief["company"], brief["start"], brief["minutes_out"], brief["offer"],
                        brief.get("thread_messages") or 0, ", ".join(brief["objections"]) or "nothing specific"))
        for problem in brief["problems"]:
            lines.append("  check: %s" % problem)
        if brief["delivered"].get("claim_released"):
            lines.append("  NOT DELIVERED: every push and note leg failed. The claim was released; the next tick "
                         "retries.")
        if brief["delivered"].get("file"):
            lines.append("  filed: %s" % brief["delivered"]["file"])
    for row in result["briefs_skipped"]:
        lines.append("brief skipped %s: %s" % (row["id"], row["reason"]))
    for row in result.get("proposals_skipped") or []:
        lines.append("proposal skipped %s: %s" % (row["id"], row["reason"]))
    for prop in result["proposals"]:
        if prop.get("skipped"):
            lines.append("PROPOSAL skipped %s: %s" % (prop["id"], prop["skipped"]))
            continue
        lines.append("PROPOSAL %s (%s) from %s, evidence %s%s"
                     % (prop["company"], prop["offer"], prop["source"], prop["held_evidence"],
                        ", BLOCKED: %s" % "; ".join(prop["problems"]) if prop["problems"] else ""))
        for note in prop.get("notes") or []:
            lines.append("  check: %s" % note)
        if prop.get("verbal_blocked"):
            lines.append("  verbal commit drafts needing you: %s" % ", ".join(prop["verbal_blocked"]))
        if prop["delivered"].get("replaced"):
            lines.append("  replaced the proposal already drafted for this call today")
        if prop["delivered"].get("file"):
            lines.append("  filed: %s" % prop["delivered"]["file"])
        elif prop["delivered"].get("skipped"):
            # Without this the digest printed a full PROPOSAL line with no
            # "filed:" and no reason, so a dropped draft read as a delivered one.
            lines.append("  NOT FILED: %s" % prop["delivered"]["skipped"])
    for err in result.get("errors") or []:
        lines.append("ERROR %s on %s: %s" % (err["where"], err["id"], err["error"]))
    if not result["briefs"] and not result["proposals"]:
        skipped = len(result.get("briefs_skipped") or []) + len(result.get("proposals_skipped") or [])
        if skipped:
            # "nothing due" under a line saying a brief was skipped is the
            # common steady state (eleven of the twelve ticks inside a 60-minute
            # window), and on a phone it reads as the opposite of what happened.
            lines.append("nothing new due (%d call(s) already handled)" % skipped)
        else:
            lines.append("nothing due")
    return "\n".join(lines)


SCHEDULED_WARNING_KEY = "precall:scheduled_warning:"
# A skipped proposal row (a call marked no-show sits in the proposal window
# from start+20 min to the end of its day: ~140 runs) pushes once per call and
# reason, and a repeated identical error once per clock hour. Both claimed in
# the store, so a fresh Modal container does not push again.
SCHEDULED_SKIP_KEY = "precall:skip_pushed:"
SCHEDULED_ERROR_KEY = "precall:error_pushed:"


def _claim(store, key: str, value: Dict[str, Any]) -> bool:
    try:
        return bool(store.set_if_absent(key, value))
    except Exception:  # noqa: BLE001 - cannot claim: report rather than go quiet
        return True


def _error_signature(err: Dict[str, Any]) -> str:
    import hashlib

    raw = json.dumps([err.get("where"), str(err.get("id")), str(err.get("error"))[:200]], sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def scheduled_push_due(result: Dict[str, Any], degraded: bool, store=None, now: Optional[datetime] = None) -> bool:
    """A --scheduled run pushes only when there is something to act on.

    A brief or a drafted proposal always pushes. A SKIPPED proposal row (a
    no-show call, a lost delivery claim) pushes once per call and reason, not
    on every run of the proposal window. An error pushes when it is new; the
    same error again pushes about once an hour. A run whose only news is a
    failed GHL read or a failed Instantly client pushes once per clock hour.
    All of it is claimed in the store, so an outage or a stuck call is
    reported without a push every 5 minutes. An idle run pushes nothing."""
    if result.get("briefs"):
        return True
    proposals = result.get("proposals") or []
    if any(not p.get("skipped") for p in proposals):
        return True
    skipped = [p for p in proposals if p.get("skipped")]
    errors = result.get("errors") or []
    if store is None:
        return bool(skipped or errors or degraded or result.get("instantly_error"))
    hour = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H")
    news = False
    for row in skipped:
        if _claim(store, "%s%s:%s" % (SCHEDULED_SKIP_KEY, row.get("id"), row.get("skipped")),
                  {"at": hour, "reason": str(row.get("skipped"))}):
            news = True
    for err in errors:
        if _claim(store, "%s%s:%s" % (SCHEDULED_ERROR_KEY, hour, _error_signature(err)),
                  {"at": hour, "where": err.get("where"), "id": str(err.get("id"))}):
            news = True
    if news:
        return True
    if not (degraded or result.get("instantly_error")):
        return False
    return _claim(store, SCHEDULED_WARNING_KEY + hour, {"at": hour})


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        _force_shadow(llm_ok=args.llm)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    here = Path(__file__).resolve().parent.parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from shared import job_log, notify, slots
    from shared.ghl import GHL
    from shared.settings import TZ, is_live
    from shared.store import JsonFileStore, get_store

    now = slots.to_tz(slots.parse_iso(args.now), TZ) if args.now else datetime.now(timezone.utc).astimezone(TZ)
    if args.store:
        store = JsonFileStore(args.store)
    elif args.dry_run:
        # a dry run advertises "nothing can be written", and the claim keys a
        # brief writes are a write like any other: a dry run against the real
        # store would silently consume the claim and the live tick would then
        # skip the brief as already delivered.
        from shared.paths import tmp_file

        scratch = tmp_file("precall_dryrun_store.json")
        logger.info("dry run: using the scratch store %s (pass --store to choose another)", scratch)
        store = JsonFileStore(scratch)
    else:
        store = get_store()
    ghl = GHL()
    instantly = None
    instantly_error = None
    if not args.no_read:
        try:
            from shared.instantly import default_client
            instantly = default_client()
        except Exception as exc:  # noqa: BLE001 - a brief without the thread is still a brief
            logger.warning("could not build the Instantly client: %s", exc)
            instantly_error = "the Instantly client could not be built: %s" % str(exc)[:120]
    try:
        loaded = load_appointments(ghl, now, args.appointments)
        with _run_lock():
            result = tick(now, store, ghl, loaded["appointments"], instantly=instantly,
                          lead_minutes=args.lead_minutes, do_proposals=not args.no_proposals,
                          proposal_for=args.proposal_for, transcript_path=args.transcript,
                          notes_path=args.notes, facts_path=args.facts, instantly_error=instantly_error)
        result["source"] = loaded["source"]
        result["ghl_token"] = "present" if ghl.has_token else "missing"
        result["read_error"] = loaded.get("error")
        result["instantly_error"] = instantly_error
        result["manual_calls"] = loaded["manual_count"]
        result["manual_duplicates"] = loaded.get("manual_duplicates") or []
        result["manual_stale"] = loaded.get("manual_stale") or []
        degraded = bool(loaded.get("error")) and not str(loaded["source"]).startswith("fixture:")
        status = "partial" if (degraded or result.get("errors")) else "ok"
    except Exception as exc:  # noqa: BLE001
        logger.exception("tick failed")
        job_log.log_run(JOB, "error", {"error": str(exc), "dry_run": args.dry_run})
        if not args.no_notify:
            notify.notify("precall_tick failed", str(exc), priority="high")
        return 1
    finally:
        ghl.close()
        if instantly is not None:
            try:
                instantly.close()
            except Exception:  # noqa: BLE001
                pass

    job_log.log_run(JOB, status, {
        "dry_run": args.dry_run, "live": is_live(), "source": result["source"],
        "ghl_token": result["ghl_token"], "read_error": result.get("read_error"),
        "instantly_error": result.get("instantly_error"),
        "appointments": result["appointments"], "manual_calls": result["manual_calls"],
        "manual_duplicates": len(result.get("manual_duplicates") or []),
        "briefs": [b["id"] for b in result["briefs"]],
        "briefs_skipped": len(result["briefs_skipped"]),
        "proposals": [p["id"] for p in result["proposals"]],
        "proposals_skipped": len(result.get("proposals_skipped") or []),
        "errors": result.get("errors") or [],
    })
    text = digest_text(result)
    text += "\nsource: %s; GHL token: %s; manual calendar calls: %d" % (
        result["source"], result["ghl_token"], result["manual_calls"])
    if result.get("manual_duplicates"):
        text += ("\n%d hand-made calendar row(s) matched a GHL booking on email and start time; the GHL row won."
                 % len(result["manual_duplicates"]))
    if result.get("manual_stale"):
        text += ("\nNOTE: %d entry in config/ids.json google_calendar.booked_this_week is already in the past. That "
                 "file is hand maintained: update it on every reschedule or this job briefs a time that no longer "
                 "exists." % len(result["manual_stale"]))
    if degraded:
        text += ("\nWARNING: the GHL calendar read failed (%s). Only the hand-made Google Calendar calls were "
                 "covered this run." % result["read_error"])
    if result.get("instantly_error"):
        text += "\nWARNING: %s. Briefs this run have no thread and the objections are the defaults." % \
                result["instantly_error"]
    if not args.no_notify and (not args.scheduled or scheduled_push_due(result, degraded, store, now)):
        notify.notify("Pre-call tick", text, priority="high" if (degraded or result["briefs"]) else "default")
    print(text)
    if not args.quiet:
        print(json.dumps({"briefs": result["briefs"], "proposals": result["proposals"]}, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
