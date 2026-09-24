"""appointments_tick: the scheduled job behind S4 (show-rate) and S5 (no-show).

    python3 -m jobs.appointments_tick --dry-run --appointments jobs/tests/fixtures/appointments_2026-09-21.json
    python3 -m jobs.appointments_tick --dry-run --now 2026-09-23T11:41:00-05:00 --appointments ... --joins joins.json

Every run:
  1. loads upcoming appointments from GHL ``get_calendar_events`` for the
     Discovery Call calendar (window: now-1 day .. now+30 days, matching the
     calendar's allow_booking_for_days). Without a GHL token that returns
     None, so ``--appointments <json>`` is the fallback (also useful for
     replaying fixtures). A failed read is reported, never read as "zero
     appointments";
  2. ensures every appointment has its show-rate schedule and sends the due
     touches (show_rate.run, guarded GHL writes);
  3. for every appointment past its start, runs the no-show state machine
     with the joins the Zoom webhook stored (or ``--joins`` fixture);
  4. sends the due recovery touches for older no-shows;
  5. writes a Job_Log row and a digest notification.

``--no-show-watch`` is the light mode for every minute in call hours: only
N1 ("I'm on" at S+3) and no-show detection, for calls that started in the
last 30 minutes (no show-rate run, no ladder sweep, no rebooking scan). It
reads GHL only when the store knows of a call in that window, and it logs and
notifies only when something happened.

``--dry-run`` forces MODE=shadow and NOTIFY=off for the process: no write can
happen even if the environment says live, and no outbound HTTP request is made
at all (the digest is recorded, not posted to ntfy). Runs every 5 minutes in
production, one run at a time (``_run_lock``).
"""
import argparse
import fcntl
import json
import logging
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jobs.appointments_tick")

JOB = "appointments_tick"
LOOKBACK = timedelta(days=1)
# the Discovery Call calendar accepts bookings 30 days out (config/ids.json
# allow_booking_for_days), so a 7-day window meant a lead booking three weeks
# ahead got no confirmation until two weeks after they booked.
LOOKAHEAD = timedelta(days=30)


def _force_shadow() -> None:
    os.environ["MODE"] = "shadow"
    os.environ.pop("ALLOW_LIVE_WRITES", None)
    # a run advertised as "no write can happen" must also make no outbound
    # request: shared.notify posts the digest to ntfy.sh over real HTTP.
    os.environ["NOTIFY"] = "off"
    # ...and it must not write into the log the 48-hour shadow watch is read
    # from. A dry run already gets a throwaway store; the job log and the
    # shadow log are the same class of file. See job_log.use_scratch_logs.
    from shared.job_log import use_scratch_logs

    use_scratch_logs("appointments_tick_dryrun")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="appointments_tick", description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="force MODE=shadow; propose and log, never send")
    p.add_argument("--now", help="ISO 8601 clock to run at (default: real time, America/Chicago)")
    p.add_argument("--appointments", help="JSON file with {'appointments': [...]} used when GHL returns nothing")
    p.add_argument("--joins", help="JSON file {'<appointment_id>': [join, ...]} to replay Zoom joins")
    p.add_argument("--store", help="path of the JSON store (default STORE_PATH or .tmp/store.json)")
    p.add_argument("--no-notify", action="store_true", help="skip the digest notification")
    p.add_argument("--no-show-watch", action="store_true",
                   help="light mode: N1 and no-show detection only, for calls started in the last 30 minutes")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


# ------------------------------------------------------------ inputs
def load_appointments_file(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("appointments", [])
    return [a for a in data if isinstance(a, dict) and a.get("start_iso")]


# services/reply_engine/cadence.py writes a day-6 calendar hold with this title
# prefix and appointmentStatus "new". It is an internal block, not a call the
# lead agreed to: treated as a booking, show_rate emails them "Locked in for
# ..." and the no-show ladder then chases them for missing it.
HOLD_TITLE_PREFIX = "HOLD: "
HOLD_STATUSES = ("new",)


def is_cadence_hold(ev: Dict[str, Any]) -> bool:
    """A cadence hold, not a booking.

    cadence.py writes holds with BOTH the title prefix and appointmentStatus
    "new" (cadence.py:1354, 1363), so the title is the discriminating half.
    Treating any "new" appointment as a hold silently dropped a real Discovery
    Call booking from the show-rate sequence AND from no-show detection, which
    is what happens whenever the calendar's auto_confirm is off or Lorenzo
    creates the appointment by hand.
    """
    return str(ev.get("title") or "").startswith(HOLD_TITLE_PREFIX)


def normalise_ghl_event(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """GHL calendar event -> the appointment dict the sequences expect.

    Returns None for a cadence hold, so nothing downstream can mistake it for
    a booked call."""
    start = ev.get("startTime") or ev.get("start_iso")
    if not start or not ev.get("id"):
        return None
    if is_cadence_hold(ev):
        logger.warning("skipping cadence hold %s (%r): no show-rate sequence and no no-show detection",
                       ev.get("id"), ev.get("title"))
        return None
    contact = ev.get("contact") or {}
    title = ev.get("title") or ""
    name = contact.get("name") or (title.split(" - ", 1)[1] if " - " in title else "")
    status = (ev.get("appointmentStatus") or "").lower()
    tags = contact.get("tags") or ev.get("tags") or []
    return {
        "id": str(ev["id"]),
        "contact_id": ev.get("contactId") or contact.get("id"),
        "opportunity_id": ev.get("opportunityId"),
        "start_iso": start,
        "end_iso": ev.get("endTime") or ev.get("end_iso"),
        "zoom_link": call_link(ev),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "first_name": contact.get("firstName") or (name.split(" ")[0] if name else None),
        "contact_name": name or None,
        "company": contact.get("companyName") or ev.get("company"),
        "tags": tags,
        # the GHL contact's timezone. Without it lead_tz_of() answered None for
        # every real booking, so the lead-local SMS window never applied (07:00
        # CT is 05:00 for a Pacific lead) and the "(12:30 ET)" clarifier in the
        # confirmation never appeared.
        "lead_tz": contact.get("timezone") or ev.get("timezone"),
        # offer and niche come from the contact tags the published GHL
        # workflows branch on. Without them every calendar booking fell back to
        # "reactivation" and an outbound/trigger prospect was quoted commission
        # pricing and the reactivation proof point.
        "niche": ev.get("niche") or _tag_value(tags, "niche-"),
        "offer": ev.get("offer") or _tag_value(tags, "offer-"),
        "title": title,
        "ghl_status": status,
        "booked_at": ev.get("dateAdded") or ev.get("createdAt") or ev.get("booked_at"),
        "cancelled": status in ("cancelled", "canceled"),
    }


_CALL_LINK_RE = re.compile(r"https://[^\s<>\"']+")


def call_link(ev: Dict[str, Any]) -> Optional[str]:
    """The call's join link from a GHL calendar event: a bare https Zoom link
    in ``address`` or ``meetingLocation`` first, else the first of the two
    that is a bare https link (a Google Meet link on a widget booking). Free text such as "Google Meet" or a phone number is not
    a link: it used to be quoted to the lead as one, and the template gate then
    held the message until it expired. None means "no link on file" and the
    messages use their no-link wording. The gate still checks the host."""
    fields = [str(ev.get(k) or "").strip() for k in ("address", "meetingLocation")]
    for value in fields:
        if "zoom.us" in value and _CALL_LINK_RE.fullmatch(value):
            return value
    for value in fields:
        if _CALL_LINK_RE.fullmatch(value):
            return value
    return None


def _tag_value(tags: Any, prefix: str) -> Optional[str]:
    """`niche-cleaning` -> "cleaning". show_rate validates the value."""
    if isinstance(tags, str):
        tags = tags.split(",")
    for tag in tags or []:
        text = str(tag).strip().lower()
        if text.startswith(prefix) and text[len(prefix):]:
            return text[len(prefix):]
    return None


def manual_calendar_calls(now: datetime) -> List[Dict[str, Any]]:
    """Calls this job does NOT cover: hand-made events on Lorenzo's own Google
    Calendar (``config/ids.json`` google_calendar.booked_this_week).

    The only appointment source below is the GHL Discovery Call calendar, and
    both calls actually on the books this week are Zoom meetings Lorenzo made
    by hand in Google Calendar - which is how he books today. They are
    deliberately NOT fed into show_rate: the S4 ladder would mail a
    confirmation, a pre-read and a "we are on for tomorrow, reply C" to a
    prospect who already agreed the time with him directly, out of a GHL
    contact record that may not exist. They are reported on every tick instead,
    so the gap is visible in the digest rather than silent.

    jobs/pipeline_sweep.py reads the same seed for its booked-call check, which
    is why the two jobs disagree about what a booked call is. This is that
    disagreement, written down.
    """
    from shared import settings, slots

    out = []  # type: List[Dict[str, Any]]
    for row in (settings.IDS.get("google_calendar") or {}).get("booked_this_week") or []:
        try:
            start = slots.to_tz(slots.parse_iso(row.get("start")), settings.TZ)
        except (ValueError, TypeError):
            continue
        if start < now - timedelta(minutes=15):
            continue
        out.append({"who": row.get("who"), "start_iso": start.isoformat(), "email": row.get("email"),
                    "source": "ids.json google_calendar"})
    return out


def fetch_appointments(ghl, now: datetime, fixture_path: Optional[str], lookback: timedelta = LOOKBACK,
                       lookahead: timedelta = LOOKAHEAD) -> Dict[str, Any]:
    """Read the Discovery Call window.

    This is the ONLY appointment source, by design: engine-made and widget-made
    GHL bookings. Calls Lorenzo makes by hand on his own Google Calendar are
    not covered - see ``manual_calendar_calls``.

    Returns ``{source, appointments, cancelled, active_ids, window, error,
    authoritative}``. ``error`` is True when the GHL call itself failed or
    there is no token: an outage must never be read as "zero appointments",
    which would look like every call was cancelled.
    """
    from shared.settings import GHL_CALENDAR_ID

    source = "ghl"
    appts = []  # type: List[Dict[str, Any]]
    cancelled = []  # type: List[Dict[str, Any]]
    raw = None
    error = None  # type: Optional[str]
    if not getattr(ghl, "has_token", False):
        error = "ghl_token_missing"
        logger.warning("ghl_token_missing: calendar read skipped, no appointment source from GHL")
    else:
        try:
            start_ms = int((now - lookback).timestamp() * 1000)
            end_ms = int((now + lookahead).timestamp() * 1000)
            raw = ghl.get_calendar_events(GHL_CALENDAR_ID, start_ms, end_ms)
            if raw is None:
                error = "ghl_read_returned_none"
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_calendar_events failed: %s", exc)
            error = "ghl_read_failed: %s" % exc
            raw = None
    if raw:
        events = raw.get("events", raw) if isinstance(raw, dict) else raw
        for ev in events or []:
            a = normalise_ghl_event(ev)
            if not a:
                continue
            (cancelled if a.get("cancelled") else appts).append(a)
    replay = False
    if not appts and not cancelled and fixture_path:
        source = "fixture:%s" % fixture_path
        appts = load_appointments_file(fixture_path)
        # `error` is deliberately NOT cleared. Clearing it made `authoritative`
        # True, so active_ids became the two ids in the fixture and show_rate
        # cancelled every other schedule in the 31-day window - permanently,
        # because a cancelled record is never re-armed. A fixture is a source
        # of appointments, never proof that nothing else exists.
        replay = True
    elif not appts and not cancelled:
        source = "none"
    authoritative = error is None
    return {
        "source": source,
        "appointments": appts,
        "cancelled": cancelled,
        "active_ids": set(str(a["id"]) for a in appts if a.get("id")) if authoritative else None,
        "window": (now - lookback, now + lookahead),
        "error": error,
        "replay": replay,
        "authoritative": authoritative,
    }


@contextmanager
def _run_lock():
    """One tick at a time. Two overlapping 5-minute runs read-modify-write the
    same store records and can dispatch the same touch twice."""
    from shared.paths import tmp_dir

    try:
        lock_path = Path(tmp_dir()) / "appointments_tick.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(str(lock_path), "a+")
    except OSError as exc:  # noqa: BLE001 - never block the run on the lock file
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


def load_joins_file(path: Optional[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------ run
def tick(
    now: datetime,
    store,
    ghl,
    appointments: List[Dict[str, Any]],
    joins_override: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    a2p: Optional[bool] = None,
    active_ids: Optional[Any] = None,
    window: Optional[Any] = None,
    cancelled: Optional[List[Dict[str, Any]]] = None,
    instantly=None,
) -> Dict[str, Any]:
    """Pure-ish core: everything the CLI does after loading inputs.

    ``a2p`` is accepted for old callers and ignored: nothing sends SMS any
    more (section 2, 2026-09-23). ``instantly`` is the Instantly client the
    in-thread reminder and no-show emails go out through.

    ``active_ids`` (the ids GHL just reported alive) and ``window`` let the
    show-rate sequence stop for a cancelled or deleted appointment. Both are
    None when the GHL read failed, and nothing is then treated as cancelled.
    """
    from services.reply_engine import no_show, show_rate, zoom_webhook
    from shared import slots
    from shared.settings import TZ

    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    upcoming = [a for a in appointments if slots.parse_iso(a["start_iso"]) > now]
    started = [a for a in appointments if slots.parse_iso(a["start_iso"]) <= now]

    # a lead who rebooked after a no-show: drop the old recovery before it
    # sends "Should I close your file?" with a new call on the books.
    rebooked = _cancel_recovery_for_rebookings(now, store, upcoming, no_show, slots)

    for appt in cancelled or []:
        for key in store.keys("showrate:%s:" % appt.get("id")):
            show_rate.cancel_schedule(store, key, "cancelled")

    # The lead replies "C" to the 24 h reminder, which went out through GHL, so
    # the Instantly poller never sees it. Read the GHL side BEFORE the 4 h
    # "has not confirmed" task can be dispatched below, or the task fires on
    # every booking. Its own try/except: nothing here is worth losing the tick.
    try:
        confirmations = show_rate.scan_ghl_confirmations(now, store, ghl)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scan_ghl_confirmations failed")
        confirmations = {"checked": 0, "confirmed": [], "skipped": [], "errors": [{"error": str(exc)[:400]}]}

    show = show_rate.run(now, store, ghl, appointments=upcoming, active_ids=active_ids, window=window,
                         **_instantly_kwarg(show_rate.run, instantly))
    no_show_results = []
    errors = []  # type: List[Dict[str, Any]]
    recovery = no_show._new_summary()  # type: Dict[str, List[Any]]
    for appt in started:
        # One appointment must never take the tick with it. A single HTTP 500
        # on PUT /calendars/events/appointments/{id} used to propagate out of
        # tick(), so every other started appointment was skipped, the recovery
        # sweep below never ran, and a deterministic failure (a deleted
        # contact, a permanently 404 id) stopped the whole S5 ladder for every
        # lead, on every 10-minute tick, for good.
        try:
            joins = (joins_override or {}).get(str(appt.get("id")))
            if joins is None:
                joins = zoom_webhook.joins_for_appointment(store, appt)
            res = no_show.process(now, appt, joins, store, ghl,
                                  meeting_signals=zoom_webhook.meeting_signals(store, appt),
                                  instantly=instantly)
        except Exception as exc:  # noqa: BLE001
            logger.exception("no_show.process failed for %s", appt.get("id"))
            failure = {"appointment_id": str(appt.get("id")), "state": "error", "events": ["error"],
                       "actions": [], "error": str(exc)[:400]}
            no_show_results.append(failure)
            errors.append({"appointment_id": failure["appointment_id"], "where": "no_show.process",
                           "error": failure["error"]})
            continue
        # process() dispatches this appointment's due recovery touches itself; fold them into the totals
        for k, v in (res.get("run") or {}).items():
            recovery.setdefault(k, []).extend(v)
        no_show_results.append({k: v for k, v in res.items() if k != "run"})
    # older no-shows whose appointments are no longer in the fetched window.
    # Its own try/except: an appointment-level failure above must not take the
    # recovery sweep for every other lead with it, and vice versa.
    try:
        for k, v in no_show.run_recovery(now, store, ghl, upcoming_appointments=upcoming,
                                         instantly=instantly).items():
            recovery.setdefault(k, []).extend(v)
    except Exception as exc:  # noqa: BLE001
        logger.exception("no_show.run_recovery failed")
        errors.append({"appointment_id": None, "where": "no_show.run_recovery", "error": str(exc)[:400]})

    pending = show_rate.pending_touches(store)
    held_ids = {}  # type: Dict[str, int]
    for entry in (show.get("held_template") or []) + (recovery.get("held_template") or []):
        tid = entry.get("template_id") or "(no template)"
        held_ids[tid] = held_ids.get(tid, 0) + 1
    return {
        "errors": errors,
        "now": now.isoformat(),
        "mode": os.environ.get("MODE", "shadow"),
        "appointments": {"upcoming": len(upcoming), "started": len(started), "cancelled": len(cancelled or [])},
        "manual_calendar_calls": manual_calendar_calls(now),
        "confirmations": confirmations,
        "rebooked_cancelled": rebooked,
        "show_rate": {k: (len(v) if isinstance(v, list) else v) for k, v in show.items()},
        "show_rate_detail": show,
        "no_show": no_show_results,
        "recovery": {k: len(v) for k, v in recovery.items()},
        "recovery_detail": recovery,
        "pending_touches": len(pending),
        "next_touch": pending[0] if pending else None,
        # CT3: touches the template gate held this tick, per template id
        # (ids and counts only). They stay pending until approved or expired.
        "held_template": held_ids,
    }


def _instantly_kwarg(fn, instantly) -> Dict[str, Any]:
    """{"instantly": client} when ``fn`` takes that keyword (show_rate.run
    does since section 2's reminder rebuild), else {}. Decided from the
    signature, never by catching a TypeError from the call itself: a
    TypeError raised inside a run that already sent something must not run it
    a second time."""
    import inspect

    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    return {"instantly": instantly} if "instantly" in params else {}


# --no-show-watch: calls that started this long ago or less. N1 is due at S+3
# and expires at S+10; the flag is due at S+10. The margin covers a slow run.
WATCH_WINDOW = timedelta(minutes=30)


def watch_candidates(store, now: datetime) -> List[str]:
    """Appointment ids the store knows of (a show-rate schedule,
    ``showrate:<id>:<start_iso>``) whose call started in the watch window.
    Reading keys only: a minute-by-minute run with no call on makes no
    request at all."""
    from shared import slots

    out = []  # type: List[str]
    for key in store.keys("showrate:"):
        rest = key[len("showrate:"):]
        if ":" not in rest:
            continue
        appt_id, start_iso = rest.split(":", 1)
        try:
            start = slots.parse_iso(start_iso)
        except (ValueError, TypeError):
            continue
        if now - WATCH_WINDOW <= start <= now and appt_id not in out:
            out.append(appt_id)
    return out


def watch(now: datetime, store, ghl, appointments: List[Dict[str, Any]],
          joins_override: Optional[Dict[str, List[Dict[str, Any]]]] = None, instantly=None) -> Dict[str, Any]:
    """The --no-show-watch core: for every call that started in the last 30
    minutes, no_show.process with the ladder off (N1 at S+3 and detection;
    the flag still marks GHL, writes the note and records the ladder, which
    the regular tick then sends). Nothing else runs."""
    from services.reply_engine import no_show, zoom_webhook
    from shared import slots
    from shared.settings import TZ

    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    started = [a for a in appointments
               if now - WATCH_WINDOW <= slots.parse_iso(a["start_iso"]) <= now and not a.get("cancelled")]
    results = []  # type: List[Dict[str, Any]]
    errors = []  # type: List[Dict[str, Any]]
    run = no_show._new_summary()  # type: Dict[str, List[Any]]
    for appt in started:
        try:
            joins = (joins_override or {}).get(str(appt.get("id")))
            if joins is None:
                joins = zoom_webhook.joins_for_appointment(store, appt)
            res = no_show.process(now, appt, joins, store, ghl,
                                  meeting_signals=zoom_webhook.meeting_signals(store, appt),
                                  instantly=instantly, run_ladder=False)
        except Exception as exc:  # noqa: BLE001 - one call must not take the others with it
            logger.exception("no_show.process (watch) failed for %s", appt.get("id"))
            errors.append({"appointment_id": str(appt.get("id")), "where": "no_show.process",
                           "error": str(exc)[:400]})
            continue
        for k, v in (res.get("run") or {}).items():
            run.setdefault(k, []).extend(v)
        results.append({k: v for k, v in res.items() if k != "run"})
    return {"now": now.isoformat(), "mode": os.environ.get("MODE", "shadow"), "checked": len(started),
            "no_show": results, "recovery": {k: len(v) for k, v in run.items()}, "recovery_detail": run,
            "errors": errors}


def watch_digest(result: Dict[str, Any]) -> str:
    lines = ["no-show watch %s (MODE=%s): %d call(s) checked" % (result["now"], result["mode"], result["checked"])]
    for r in result["no_show"]:
        if r.get("events"):
            lines.append("  %s: state=%s events=%s" % (r.get("appointment_id"), r.get("state"),
                                                       ",".join(r.get("events") or [])))
    for err in result.get("errors") or []:
        lines.append("ERROR %s on %s: %s" % (err.get("where"), err.get("appointment_id"), err.get("error")))
    return "\n".join(lines)


def _run_watch(args, now, store, ghl, instantly) -> int:
    """main() for --no-show-watch."""
    from shared import job_log, notify

    fixture = args.appointments
    if not fixture and not watch_candidates(store, now):
        return 0  # no call in the window: no request, no log row
    fetched = fetch_appointments(ghl, now, fixture, lookback=WATCH_WINDOW + timedelta(minutes=15),
                                 lookahead=timedelta(minutes=1))
    with _run_lock():
        result = watch(now, store, ghl, fetched["appointments"], joins_override=load_joins_file(args.joins),
                       instantly=instantly)
    happened = [r for r in result["no_show"] if r.get("events")]
    if result["checked"] or result["errors"]:
        job_log.log_run(JOB + ":no_show_watch", "partial" if result["errors"] or fetched.get("error") else "ok",
                        {"dry_run": args.dry_run, "source": fetched["source"], "read_error": fetched.get("error"),
                         "checked": result["checked"], "recovery": result["recovery"],
                         "no_show": [{"id": r.get("appointment_id"), "state": r.get("state"),
                                      "events": r.get("events")} for r in result["no_show"]],
                         "errors": result["errors"]})
    text = watch_digest(result)
    if (happened or result["errors"]) and not args.no_notify:
        notify.notify("No-show watch", text, priority="high" if result["errors"] else "default")
    if not args.quiet:
        print(text)
    return 0


def _cancel_recovery_for_rebookings(now, store, upcoming: List[Dict[str, Any]], no_show, slots) -> List[Dict[str, Any]]:
    """booking.py (brief A2) is meant to call cancel_recovery_for_rebooking;
    it does not yet, and a widget rebooking produces no inbound reply, so the
    tick does it from the calendar itself."""
    out = []  # type: List[Dict[str, Any]]
    by_contact = {}  # type: Dict[str, List[Dict[str, Any]]]
    for appt in upcoming:
        cid = str(appt.get("contact_id") or "")
        if cid:
            by_contact.setdefault(cid, []).append(appt)
    if not by_contact:
        return out
    for key in store.keys("noshow_state:"):
        st = store.get(key) or {}
        if st.get("state") != "no_show":
            continue
        old_id = key[len("noshow_state:"):]
        rec_keys = store.keys("recovery:%s:" % old_id)
        contact_id = None
        for rk in rec_keys:
            contact_id = ((store.get(rk) or {}).get("appointment") or {}).get("contact_id")
            if contact_id:
                break
        if not contact_id:
            continue
        for appt in by_contact.get(str(contact_id), []):
            if str(appt.get("id")) == old_id and str(appt.get("start_iso")) == str(st.get("start_iso")):
                continue  # same call, not a rebooking
            n = no_show.cancel_recovery_for_rebooking(store, old_id)
            out.append({"appointment_id": old_id, "new_appointment_id": str(appt.get("id")), "cancelled": n})
            break
    return out


def digest_text(result: Dict[str, Any]) -> str:
    sr = result["show_rate"]
    lines = [
        "appointments_tick %s (MODE=%s)" % (result["now"], result["mode"]),
        "appointments: %d upcoming, %d started, %d cancelled"
        % (result["appointments"]["upcoming"], result["appointments"]["started"], result["appointments"].get("cancelled", 0)),
        "show-rate: %d scheduled, %d sent, %d would_do (shadow), %d skipped, %d errors, %d held (template)"
        % (sr.get("scheduled", 0), sr.get("sent", 0), sr.get("would_do", 0), sr.get("skipped", 0), sr.get("errors", 0),
           sr.get("held_template", 0)),
    ]
    conf = result.get("confirmations") or {}
    if conf.get("confirmed") or conf.get("checked"):
        lines.append("GHL confirmations: %d checked, %d newly confirmed" % (conf.get("checked", 0), len(conf.get("confirmed") or [])))
    for row in conf.get("skipped") or []:
        if row.get("reason") == "ghl_token_missing":
            lines.append("WARNING: %d call(s) are waiting on a 'reply C' nobody can read: the GHL "
                         "conversations read needs the Private Integration token, so the 4 h "
                         "'has not confirmed' task will fire on each of them." % row.get("waiting", 0))
    for r in result["no_show"]:
        lines.append("no-show check %s: state=%s events=%s" % (r.get("appointment_id"), r.get("state"), ",".join(r.get("events") or []) or "-"))
    rec = result["recovery"]
    lines.append("recovery: %d sent, %d would_do, %d skipped, %d stage moves, %d cancelled, %d held (template)"
                 % (rec.get("sent", 0), rec.get("would_do", 0), rec.get("skipped", 0), rec.get("stage_moves", 0),
                    rec.get("cancelled", 0), rec.get("held_template", 0)))
    if rec.get("nurture"):
        lines.append("recovery: %d lead(s) handed to the 90-day nurture" % rec["nurture"])
    detail = result.get("recovery_detail") or {}
    for row in detail.get("maybe_sent") or []:
        lines.append("CHECK BY HAND: no-show email %s may have been delivered (%s); it will not be retried"
                     % (row.get("template"), row.get("key")))
    for row in detail.get("needs_attention") or []:
        lines.append("NEEDS A LOOK: no-show email %s is held, the lead's thread: %s" % (row.get("template"),
                                                                                         row.get("reason")))
    held = result.get("held_template") or {}
    if held:
        lines.append("HELD, not sent (template not approved for auto-send, retried every tick until it expires): %s"
                     % ", ".join("%s x%d" % (tid, n) for tid, n in sorted(held.items())))
    for err in result.get("errors") or []:
        lines.append("ERROR %s on %s: %s" % (err.get("where"), err.get("appointment_id") or "-", err.get("error")))
    for rb in result.get("rebooked_cancelled") or []:
        lines.append("rebooked: recovery for %s dropped, new call %s (%d touches)"
                     % (rb["appointment_id"], rb["new_appointment_id"], rb["cancelled"]))
    for row in result.get("manual_calendar_calls") or []:
        lines.append("NOT COVERED: %s at %s is on your own Google Calendar, so no confirmation, "
                     "pre-read, reminder or no-show check runs for it" % (row.get("who"), row.get("start_iso")))
    nxt = result.get("next_touch")
    if nxt:
        lines.append("next touch: %s %s at %s" % (nxt["template_key"], nxt["channel"], nxt["when_iso"]))
    lines.append("pending touches: %d" % result["pending_touches"])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        _force_shadow()
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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
        # --dry-run advertises "no write can happen". It used to gate HTTP only,
        # so the documented fixture replay ran against the production store and
        # cancelled every schedule the fixture did not mention. A dry run gets
        # its own scratch store unless --store says otherwise.
        from shared.paths import tmp_file

        scratch = tmp_file("dryrun_store.json")
        logger.info("dry run: using the scratch store %s (pass --store to choose another)", scratch)
        store = JsonFileStore(scratch)
    else:
        store = get_store()
    ghl = GHL()
    # The Instantly client (shared.instantly.default_client, as every job
    # builds it): the reminder and no-show emails go out as replies in the
    # lead's thread through it, and a held call moves the lead to interest 3
    # (S3 item 4). Its writes are guarded (a shadow record in MODE=shadow, no
    # request) and in shadow nothing reads through it either. Built here so
    # the tick owns its lifetime.
    instantly = None
    try:
        from shared.instantly import default_client
        instantly = default_client()
    except Exception as exc:  # noqa: BLE001 - live emails then hold (no_instantly_client); shadow records them
        logger.warning("could not build the Instantly client: %s", exc)
    if args.no_show_watch:
        try:
            return _run_watch(args, now, store, ghl, instantly)
        except Exception as exc:  # noqa: BLE001
            logger.exception("no-show watch failed")
            job_log.log_run(JOB + ":no_show_watch", "error", {"error": str(exc), "dry_run": args.dry_run})
            if not args.no_notify:
                notify.notify("no-show watch failed", str(exc), priority="high")
            return 1
        finally:
            ghl.close()
            if instantly is not None:
                try:
                    instantly.close()
                except Exception:  # noqa: BLE001
                    pass
    try:
        fetched = fetch_appointments(ghl, now, args.appointments)
        joins_override = load_joins_file(args.joins)
        with _run_lock():
            result = tick(now, store, ghl, fetched["appointments"], joins_override=joins_override,
                          active_ids=fetched.get("active_ids"), window=fetched.get("window"),
                          cancelled=fetched.get("cancelled"), instantly=instantly)
        result["source"] = fetched["source"]
        result["ghl_token"] = "present" if ghl.has_token else "missing"
        result["read_error"] = fetched.get("error")
        degraded = bool(fetched.get("error")) and not fetched["source"].startswith("fixture:")
        status = "ok" if not result["show_rate"].get("errors") and not result["recovery"].get("errors") else "partial"
        if degraded or result.get("errors"):
            status = "partial"
    except Exception as exc:  # noqa: BLE001
        logger.exception("tick failed")
        job_log.log_run(JOB, "error", {"error": str(exc), "dry_run": args.dry_run})
        if not args.no_notify:
            notify.notify("appointments_tick failed", str(exc), priority="high")
        return 1
    finally:
        ghl.close()
        if instantly is not None:
            try:
                instantly.close()
            except Exception:  # noqa: BLE001
                pass

    summary = {
        "dry_run": args.dry_run, "live": is_live(), "source": result["source"], "ghl_token": result["ghl_token"],
        "read_error": result.get("read_error"),
        "appointments": result["appointments"], "show_rate": result["show_rate"], "recovery": result["recovery"],
        "manual_calendar_calls": [r.get("who") for r in result.get("manual_calendar_calls") or []],
        "confirmations": {"checked": (result.get("confirmations") or {}).get("checked", 0),
                          "confirmed": len((result.get("confirmations") or {}).get("confirmed") or [])},
        "no_show": [{"id": r.get("appointment_id"), "state": r.get("state"), "events": r.get("events")} for r in result["no_show"]],
        "pending_touches": result["pending_touches"],
        "held_template": result.get("held_template") or {},
        "errors": result.get("errors") or [],
    }
    job_log.log_run(JOB, status, summary)
    text = digest_text(result)
    text += "\nsource: %s; GHL token: %s" % (result["source"], result["ghl_token"])
    if degraded:
        text += "\nWARNING: the calendar read failed (%s). No appointment was treated as cancelled and nothing new was scheduled." % result["read_error"]
    if not args.no_notify:
        notify.notify("Appointments tick", text, priority="high" if degraded else "default")
    print(text)
    if not args.quiet:
        for entry in result["show_rate_detail"].get("would_do", []) + result["show_rate_detail"].get("sent", []):
            print("  touch %s -> %s %s (%s)" % (entry["when"], entry["channel"], entry["template"], "shadow" if entry.get("shadow") else "LIVE"))
        for entry in result["show_rate_detail"].get("skipped", []):
            print("  skipped %s: %s" % (entry.get("key"), entry.get("reason")))
        for r in result["no_show"]:
            for a in r.get("actions", []):
                print("  no-show action %s %s -> %s" % (r.get("appointment_id"), a.get("action"), a.get("status")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
