#!/usr/bin/env python3
"""Daily calendar slots for the six AI-agents cold campaigns.

Every email in those campaigns ends "how does {{slot1}} or {{slot2}} sound?"
(step 1) or "Would {{slot1}} or {{slot2}} work for a quick 15 minute call?"
(step 2). Instantly fills both from each lead's custom variables at send time
and has no calendar-aware variable, so this job refreshes them every morning
from Lorenzo's GHL Discovery Call calendar.

  python3 slots_daily.py                       # dry-run (default): reads only, writes nothing
  python3 slots_daily.py --apply               # PATCHes leads; needs MODE=live AND ALLOW_LIVE_WRITES=1
  python3 slots_daily.py --lead-id <id> [--apply]          # the whole flow on exactly one lead (rehearsal)
  python3 slots_daily.py --restore <backup.json> [--apply] # put a backup's saved variables back
  python3 slots_daily.py --date 2026-10-01     # pretend the send day is that date
  python3 slots_daily.py --ids-file other.json # campaign ids (default instantly_campaigns_ai_agents.json)

Rules for a send day D (today in CT when run as the job):
  slot1 = a free time on the 1st business day after D, slot2 = one on the 2nd
  (rolling forward past fully busy days, within 5 business days). Times come
  from a 30-minute grid, 12:00-17:30 CT starts, and pass shared.slots.candidate_slots
  (>= 4 h out, <= 5 business days). GHL unreachable -> full grid, source "fallback";
  GHL answers with no free slot at all -> full grid, source "fallback_empty".

An --apply run backs up every lead it will touch, reads the first patched lead
back and aborts unless it is intact, and stops after 5 PATCH failures in a row.
Exit codes: 0 ok; 1 slot, ids, lead or campaign-field error, or some PATCHes
failed; 2 refused (live flags missing, or campaign copy lacks the slot
variables) or a usage error; 3 aborted mid-run (read-back, failure brake,
unexpected exception); 130 Ctrl-C, 143 SIGTERM, 129 SIGHUP (status
"interrupted", logged with the counts so far and the --restore command).

The pure functions compute_slots() and slot_vars_for() are also used by
instantly_push.py --offer ai_agents. See SLOTS_RUNBOOK.md.
"""
import argparse
import hashlib
import importlib.util
import json
import logging
import os
import signal
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

ROOT = Path(__file__).resolve().parent
AW = ROOT.parent.parent / "Agentic Worklfows"
IDS_FILE = ROOT / "instantly_campaigns_ai_agents.json"
OLD_IDS_NAME = "instantly_campaigns.json"  # never written here (--activate starts every id in it); read only to reject its ids
OLD_IDS_FILE = ROOT / OLD_IDS_NAME
LOG_FILE = ROOT / "logs" / "slots_daily.jsonl"

AI_CAMPAIGN_KEYS = ("bookkeeping_ai", "insurance_broker_ai", "landscaping_ai",
                    "marketing_agency_ai", "msp_ai", "pest_control_ai")
# Live AI-agents campaigns whose copy has no {{slot1}}/{{slot2}}: never a slot target.
KNOWN_NON_AI_IDS = {"d81f1d53-23d6-48a6-aea3-80c21192e17e": "Service - AI Agents",
                    "59b20790-12bb-446d-bcd6-e3b6f9a61953": "Recruiting - AI Agents"}
SLOT_TOKENS = ("{{slot1}}", "{{slot2}}")

GRID_START = (12, 0)      # first start 12:00 CT
GRID_LAST = (17, 30)      # last start 17:30 CT (17:30 + 15 min <= 18:00)
GRID_STEP_MIN = 30
ZONE_LABEL = "CT"

# Instantly v2 lead.status: 1 active, 2 paused, 3 completed, -1 bounced,
# -2 unsubscribed, -3 skipped. Only 1 and 2 can still receive a step.
SENDABLE_STATUSES = (1, 2)
# Keys Instantly keeps in a lead's `payload` that are standard lead fields, not
# custom variables. `personalization` is both, and stays (the emails use it).
STANDARD_PAYLOAD_KEYS = frozenset(("firstName", "lastName", "companyName", "email", "website",
                                   "phone", "jobTitle"))
# Keys Instantly itself keeps in `payload` (2026-09-21 replied-leads snapshot:
# `campaign` on all 39 leads, `pause_until` on 15). Never written back.
SYSTEM_PAYLOAD_KEYS = frozenset(("campaign", "pause_until"))
EXCLUDED_KEYS = STANDARD_PAYLOAD_KEYS | SYSTEM_PAYLOAD_KEYS
# Read-back after the first PATCH: these payload keys must equal the backup...
READBACK_PAYLOAD_KEYS = ("personalization", "lead_id", "firstName", "companyName") + tuple(sorted(SYSTEM_PAYLOAD_KEYS))
# ...these top-level fields must be unchanged...
READBACK_TOP_KEYS = ("first_name", "company_name", "personalization")
# ...these must stay non-empty when the backup had them non-empty...
READBACK_NONEMPTY_KEYS = ("personalization", "lead_id")
# ...and these must hold the new values.
SLOT_KEYS = ("slot1", "slot2", "slot_date")
MAX_CONSECUTIVE_FAILURES = 5

BATCH_CALLS = 100         # contract: batch about 100 calls then wait ~2 seconds
BATCH_PAUSE_S = 2.0

log = logging.getLogger("slots_daily")


def _load_shared_slots():
    """shared/slots.py loaded by file path: it is pure (stdlib + pytz) and this
    avoids shared/__init__.py, which imports every engine module."""
    path = AW / "shared" / "slots.py"
    spec = importlib.util.spec_from_file_location("advero_shared_slots", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = _load_shared_slots()
TZ = S.TZ


class SlotError(Exception):
    """Fewer than one offerable time for slot1 or slot2. Nothing may be written."""


class NoCampaignFieldError(Exception):
    """Eligible leads were listed but none could be tied to a campaign (no `campaign` field)."""


class LeadIdError(Exception):
    """--lead-id names a lead that is missing or outside the six AI-agents campaigns."""


class Abort(Exception):
    """Stops an --apply/--restore run mid-way (exit 3)."""

    def __init__(self, status: str, message: str, details: Optional[Dict[str, Any]] = None,
                 private: Optional[Dict[str, Any]] = None):
        Exception.__init__(self, message)
        # details go into the log line; private (lead values) only into the backup file
        self.status, self.details, self.private = status, details or {}, private or {}


class Interrupted(KeyboardInterrupt):
    """SIGTERM / SIGHUP turned into the same path as Ctrl-C."""

    def __init__(self, signum: int):
        KeyboardInterrupt.__init__(self, "signal %d" % signum)
        self.signum = signum


# ------------------------------------------------------------------ dates
def _as_date(d: Union[str, date, datetime]) -> date:
    if isinstance(d, datetime):
        return S.to_tz(S.ensure_aware(d, TZ), TZ).date()
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d), "%Y-%m-%d").date()


def _local(d: date, hour: int, minute: int) -> datetime:
    naive = datetime(d.year, d.month, d.day, hour, minute)
    try:
        return TZ.localize(naive, is_dst=None)
    except Exception:  # noqa: BLE001 - DST edge, never inside 12:00-18:00
        return TZ.localize(naive, is_dst=False)


def business_days_after(d: date, n: int) -> List[date]:
    out, cur = [], d
    while len(out) < n:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:
            out.append(cur)
    return out


def next_send_day(now: datetime) -> date:
    """Campaigns send 06:00-18:00 CT Mon-Sat. Today if it is Mon-Sat and before
    06:00 CT, else the next Mon-Sat date."""
    now_ct = S.to_tz(S.ensure_aware(now, TZ), TZ)
    today = now_ct.date()
    if today.weekday() <= 5 and now_ct.hour < 6:
        return today
    d = today + timedelta(days=1)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d


def grid_for(days: Iterable[date]) -> List[datetime]:
    out = []
    for d in days:
        m = GRID_START[0] * 60 + GRID_START[1]
        last = GRID_LAST[0] * 60 + GRID_LAST[1]
        while m <= last:
            out.append(_local(d, m // 60, m % 60))
            m += GRID_STEP_MIN
    return out


def _minute_key(dt: datetime) -> str:
    return S.to_tz(dt, TZ).strftime("%Y-%m-%dT%H:%M")


# ------------------------------------------------------------------ slots
def slot_source(free_slots_or_None: Optional[Iterable[Any]]) -> str:
    if free_slots_or_None is None:
        return "fallback"
    if not list(free_slots_or_None):
        return "fallback_empty"
    return "ghl"


def compute_slots(send_day: Union[str, date], free_slots_or_None: Optional[Iterable[Any]],
                  now: datetime) -> Tuple[List[datetime], List[datetime], str]:
    """(day1_slots, day2_slots, source) for send day D.

    free_slots_or_None: GHL free-slot ISO strings/datetimes; None when GHL could
    not be read (source "fallback"); an empty answer is treated as a GHL problem
    too (source "fallback_empty"). Both fallbacks use the full grid.
    Raises SlotError when either day has no offerable time.
    """
    d = _as_date(send_day)
    window_days = business_days_after(d, S.MAX_BUSINESS_DAYS + 1)
    grid = grid_for(window_days)
    raw = None if free_slots_or_None is None else list(free_slots_or_None)
    source = slot_source(raw)
    if source != "ghl":
        free = grid
    else:
        free_keys = set()
        for item in raw:
            try:
                free_keys.add(_minute_key(S.parse_iso(item, TZ)))
            except (ValueError, TypeError):
                log.warning("unreadable GHL free slot skipped: %r", item)
        free = [g for g in grid if _minute_key(g) in free_keys]
    cands = [c for c in S.candidate_slots(free, now) if c.date() > d]
    by_day = {}  # type: Dict[date, List[datetime]]
    for c in cands:
        by_day.setdefault(c.date(), []).append(c)
    days = sorted(by_day)
    if len(days) < 2:
        raise SlotError(
            "not enough free calendar time for send day %s (source=%s): %d day(s) with a free 12:00-17:30 CT "
            "start within %d business days (need 2: one for slot1, a later one for slot2). Nothing written."
            % (d.isoformat(), source, len(days), S.MAX_BUSINESS_DAYS))
    return by_day[days[0]], by_day[days[1]], source


def fmt_slot(dt: datetime, zone: bool = False) -> str:
    """'Thursday at 1pm', 'Thursday at 1:30pm'; zone=True adds ' CT'."""
    dt = S.to_tz(dt, TZ)
    hour = dt.hour % 12 or 12
    t = str(hour) if dt.minute == 0 else "%d:%02d" % (hour, dt.minute)
    out = "%s at %s%s" % (dt.strftime("%A"), t, "am" if dt.hour < 12 else "pm")
    return out + (" " + ZONE_LABEL if zone else "")


def _spread_index(email: str, send_day: date) -> Tuple[int, int]:
    h = hashlib.sha256(("%s|%s" % ((email or "").strip().lower(), send_day.isoformat())).encode()).digest()
    return int.from_bytes(h[:8], "big"), int.from_bytes(h[8:16], "big")


def slot_vars_for(email: str, send_day: Union[str, date], day1_slots: List[datetime],
                  day2_slots: List[datetime]) -> Dict[str, str]:
    """{'slot1', 'slot2', 'slot_date'} for one lead: a stable hash of email + D
    picks (day1_slots[i % n1], day2_slots[j % n2])."""
    if not day1_slots or not day2_slots:
        raise SlotError("slot_vars_for needs at least one slot per day")
    d = _as_date(send_day)
    i, j = _spread_index(email, d)
    return {"slot1": fmt_slot(day1_slots[i % len(day1_slots)]),
            "slot2": fmt_slot(day2_slots[j % len(day2_slots)], zone=True),
            "slot_date": d.isoformat()}


def print_fallback_banner(source: str) -> None:
    why = ("GHL answered with no free slot at all (treated as a GHL problem)" if source == "fallback_empty"
           else "GHL could not be read")
    print("!" * 72)
    print("!! GHL CALENDAR NOT READ (%s): using the full 12:00-17:30 CT grid. Calendar conflicts were NOT checked."
          % why)
    print("!" * 72)


# ------------------------------------------------------------------ GHL (read only)
def ghl_free_slots(now: datetime) -> Optional[List[str]]:
    """Free slots from the GHL Discovery Call calendar, or None (=> fallback).
    Read-only: GET calendars/{id}/free-slots with GHL_PRIVATE_INTEGRATION_TOKEN_READ."""
    try:
        if str(AW) not in sys.path:
            sys.path.insert(0, str(AW))
        from shared import ghl as ghl_mod  # noqa: WPS433 - lazy: pulls in settings/.env
        from services.reply_engine.draft import parse_ghl_free_slots
        client = ghl_mod.GHL()
    except Exception as exc:  # noqa: BLE001
        log.error("GHL client unavailable (%s): %s", type(exc).__name__, exc)
        return None
    if not client.has_token:
        log.error("GHL read token missing (set %s): calendar NOT checked", ghl_mod.READ_TOKEN_ENV)
        return None
    start = S.ensure_aware(now, TZ)
    end = S.business_days_ahead(start, S.MAX_BUSINESS_DAYS + 2)
    try:
        payload = client.get_free_slots(client.calendar_id, int(start.timestamp() * 1000),
                                        int(end.timestamp() * 1000), timezone="America/Chicago",
                                        user_id=client.user_id)
    except Exception as exc:  # noqa: BLE001
        log.error("GHL free-slots read failed (%s): %s", type(exc).__name__, str(exc)[:200])
        return None
    if payload is None:
        log.error("GHL free-slots returned nothing")
        return None
    return parse_ghl_free_slots(payload)


# ------------------------------------------------------------------ campaign ids
def _old_campaign_ids(path: Optional[Union[str, Path]]) -> set:
    p = Path(path) if path else OLD_IDS_FILE
    if not p.exists():
        return set()
    try:
        old = json.loads(p.read_text())
    except ValueError as exc:
        raise SystemExit("cannot read %s to rule out its ids (%s); refusing" % (p, exc))
    vals = old.values() if isinstance(old, dict) else old
    return {str(v).strip().lower() for v in vals if v}


def load_ai_ids(path: Optional[Union[str, Path]] = None,
                old_ids_path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """The six AI-agents campaign ids. Raises SystemExit unless the file holds
    exactly the six keys, six distinct non-empty ids, none of them from
    instantly_campaigns.json or the known non-AI campaigns."""
    p = Path(path) if path else IDS_FILE
    if p.name == OLD_IDS_NAME:
        raise SystemExit("refusing %s: the AI-agents ids live in %s" % (p, IDS_FILE.name))
    if not p.exists():
        raise SystemExit("AI-agents campaign ids file missing: %s (created by the AI-agents campaign change-set; "
                         "or pass --ids-file)" % p)
    try:
        ids = json.loads(p.read_text())
    except ValueError as exc:
        raise SystemExit("AI-agents ids file %s is not valid JSON: %s" % (p, exc))
    if not isinstance(ids, dict):
        raise SystemExit("AI-agents ids file %s must be a JSON object of the six campaign keys" % p)
    missing = [k for k in AI_CAMPAIGN_KEYS if k not in ids]
    extra = sorted(k for k in ids if k not in AI_CAMPAIGN_KEYS)
    if missing or extra:
        raise SystemExit("AI-agents ids file %s must hold exactly %s (missing %s, unexpected %s)"
                         % (p, list(AI_CAMPAIGN_KEYS), missing, extra))
    empty = [k for k in AI_CAMPAIGN_KEYS if not isinstance(ids[k], str) or not ids[k].strip()]
    if empty:
        raise SystemExit("AI-agents ids file %s has empty or non-string ids for %s" % (p, empty))
    out = {k: ids[k].strip() for k in AI_CAMPAIGN_KEYS}
    norm = [v.lower() for v in out.values()]
    dups = sorted({v for v in norm if norm.count(v) > 1})
    if dups:
        raise SystemExit("AI-agents ids file %s repeats campaign id(s) %s" % (p, dups))
    known = {k.lower(): n for k, n in KNOWN_NON_AI_IDS.items()}
    bad_known = ["%s=%s (%s)" % (k, v, known[v.lower()]) for k, v in out.items() if v.lower() in known]
    if bad_known:
        raise SystemExit("AI-agents ids file %s points at campaign(s) whose copy has no slots: %s" % (p, bad_known))
    old = _old_campaign_ids(old_ids_path)
    bad_old = ["%s=%s" % (k, v) for k, v in out.items() if v.lower() in old]
    if bad_old:
        raise SystemExit("AI-agents ids file %s reuses id(s) from %s: %s" % (p, OLD_IDS_NAME, bad_old))
    return out


# ------------------------------------------------------------------ Instantly
class Paced(object):
    """Wraps instantly_push.call: pauses 2 s every 100 calls, retries 429."""

    def __init__(self, call_fn: Callable, tok: str, sleep: Callable = time.sleep):
        self.call_fn, self.tok, self.sleep, self.n = call_fn, tok, sleep, 0

    def __call__(self, method: str, path: str, body: Any = None) -> Any:
        for attempt in range(4):
            self.n += 1
            if self.n % BATCH_CALLS == 0:
                self.sleep(BATCH_PAUSE_S)
            try:
                return self.call_fn(method, path, body, self.tok)
            except SystemExit as exc:
                if "HTTP 429" in str(exc) and attempt < 3:
                    self.sleep(5.0 * (attempt + 1))
                    continue
                raise


def campaign_copy_problems(api: Callable, ids: Dict[str, str]) -> List[str]:
    """[] when every step-1 variant body and every step-2 body of all six
    campaigns contains both {{slot1}} and {{slot2}}; else one line per problem."""
    problems = []
    for ck in AI_CAMPAIGN_KEYS:
        cid = ids[ck]
        try:
            camp = api("GET", "campaigns/%s" % cid) or {}
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - a failed read is a refusal, not a crash
            problems.append("%s: GET campaigns/%s failed: %s" % (ck, cid, str(exc)[:200]))
            continue
        seqs = camp.get("sequences") or []
        steps = (seqs[0].get("steps") if seqs and isinstance(seqs[0], dict) else None) or []
        if len(steps) < 2:
            problems.append("%s: %d step(s) returned, need step 1 and step 2" % (ck, len(steps)))
            continue
        for si in (0, 1):
            variants = (steps[si] or {}).get("variants") or []
            if not variants:
                problems.append("%s: step %d has no variants" % (ck, si + 1))
            for vi, v in enumerate(variants):
                body = (v or {}).get("body") or ""
                lacking = [t for t in SLOT_TOKENS if t not in body]
                if lacking:
                    problems.append("%s: step %d variant %d body lacks %s" % (ck, si + 1, vi + 1, lacking))
    return problems


def list_campaign_leads(api: Callable, campaign_ids: Iterable[str],
                        stats: Optional[Dict[str, int]] = None) -> Dict[str, List[dict]]:
    """Leads per campaign via POST leads/list (a read). Uses the documented
    `campaign` filter (verified 2026-09-30; `campaign_id` is ignored). If a page
    ever comes back with leads of another campaign, or leads without a
    `campaign` field, the filter is treated as ignored: page the whole workspace
    once and group by each lead's `campaign`. `stats` counts listed leads that
    carry no `campaign` field (and how many of those could still get a step)."""
    wanted = list(campaign_ids)
    out = {c: [] for c in wanted}  # type: Dict[str, List[dict]]
    for cid in wanted:
        after, ignored = None, False
        while True:
            body = {"limit": 100, "campaign": cid}
            if after:
                body["starting_after"] = after
            d = api("POST", "leads/list", body) or {}
            items = d.get("items", [])
            if any(it.get("campaign") != cid for it in items):
                ignored = True
                break
            out[cid].extend(items)
            after = d.get("next_starting_after")
            if not after or not items:
                break
        if ignored:
            log.warning("leads/list ignored the campaign filter; paging the whole workspace and grouping")
            return _list_all_grouped(api, wanted, stats)
    return out


def _list_all_grouped(api: Callable, wanted: List[str],
                      stats: Optional[Dict[str, int]] = None) -> Dict[str, List[dict]]:
    stats = {} if stats is None else stats
    stats.setdefault("no_campaign_field", 0)
    stats.setdefault("no_campaign_field_eligible", 0)
    out = {c: [] for c in wanted}  # type: Dict[str, List[dict]]
    after = None
    while True:
        body = {"limit": 100}
        if after:
            body["starting_after"] = after
        d = api("POST", "leads/list", body) or {}
        for it in d.get("items", []):
            c = it.get("campaign")
            if c in out:
                out[c].append(it)
            elif not c:
                stats["no_campaign_field"] += 1
                if can_receive_step(it):
                    stats["no_campaign_field_eligible"] += 1
        after = d.get("next_starting_after")
        if not after or not d.get("items"):
            return out


def can_receive_step(lead: dict) -> bool:
    """Not completed, bounced, unsubscribed or skipped (status in 1, 2) and never replied."""
    if lead.get("status") not in SENDABLE_STATUSES:
        return False
    if (lead.get("email_reply_count") or 0) > 0 or lead.get("timestamp_last_reply"):
        return False
    return True


def _vars_view(lead: dict) -> Dict[str, Any]:
    """payload (with `custom_variables` laid over it if a response carries one)."""
    out = {}  # type: Dict[str, Any]
    if isinstance(lead.get("payload"), dict):
        out.update(lead["payload"])
    if isinstance(lead.get("custom_variables"), dict):
        out.update(lead["custom_variables"])
    return out


def existing_custom_variables(lead: dict) -> Optional[Dict[str, Any]]:
    """The lead's full custom variables, or None when they cannot be trusted.
    Instantly returns them inside `payload` (with the standard fields and its
    own `campaign` / `pause_until` mixed in); `custom_variables` is used if a
    response ever carries it. Readable only when the result is a dict with a
    non-empty `personalization`: anything less (null, {}, only standard keys)
    would turn the PATCH into a partial dict."""
    if isinstance(lead.get("custom_variables"), dict):
        src = lead["custom_variables"]
    elif isinstance(lead.get("payload"), dict):
        src = lead["payload"]
    else:
        return None
    out = {k: v for k, v in src.items() if k not in EXCLUDED_KEYS}
    if not str(out.get("personalization") or "").strip():
        return None
    return out


def merged_variables(existing: Dict[str, Any], new: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Full existing dict + new slot values, or None when nothing changes."""
    if all(existing.get(k) == v for k, v in new.items()):
        return None
    out = dict(existing)
    out.update(new)
    return out


def _new_counts(n: int) -> Dict[str, int]:
    return {"leads": n, "eligible": 0, "change": 0, "unchanged": 0, "unreadable": 0}


def _plan_lead(api: Callable, lead: dict, ck: str, c: Dict[str, int], send_day: date, day1: List[datetime],
               day2: List[datetime], plan: List[dict], refetch: bool = True) -> None:
    if not can_receive_step(lead):
        return
    c["eligible"] += 1
    raw, before = lead, existing_custom_variables(lead)
    if before is None and refetch:
        try:
            full = api("GET", "leads/%s" % lead["id"]) or {}
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - an unreadable lead is skipped, never guessed
            log.warning("GET leads/%s failed: %s", lead.get("id"), str(exc)[:200])
            full = {}
        if full and (full.get("id") != lead.get("id") or full.get("campaign") != lead.get("campaign")):
            # only the same lead in the same campaign may stand in for the listed one
            log.warning("GET leads/%s returned id %r in campaign %r (listed in %r); ignored",
                        lead.get("id"), full.get("id"), full.get("campaign"), lead.get("campaign"))
            full = {}
        before = existing_custom_variables(full)
        if before is not None:
            raw = full
    if before is None:
        c["unreadable"] += 1
        log.warning("lead %s: custom variables unreadable, skipped (never send a partial dict)", lead.get("id"))
        return
    after = merged_variables(before, slot_vars_for(lead.get("email", ""), send_day, day1, day2))
    if after is None:
        c["unchanged"] += 1
        return
    c["change"] += 1
    plan.append({"id": lead["id"], "email": lead.get("email"), "campaign_key": ck,
                 "before": before, "after": after, "raw": raw})


def plan_updates(api: Callable, ids: Dict[str, str], send_day: date, day1: List[datetime],
                 day2: List[datetime], stats: Optional[Dict[str, int]] = None
                 ) -> Tuple[List[dict], Dict[str, Dict[str, int]]]:
    """[{id, email, campaign_key, before, after, raw}] for leads whose slot values change.
    Raises NoCampaignFieldError when no listed lead matched a campaign but
    eligible leads without a `campaign` field were listed."""
    stats = {} if stats is None else stats
    by_cid = list_campaign_leads(api, ids.values(), stats)
    key_of = {v: k for k, v in ids.items()}
    plan, counts = [], {}  # type: List[dict], Dict[str, Dict[str, int]]
    for cid, leads in by_cid.items():
        ck = key_of[cid]
        c = counts.setdefault(ck, _new_counts(len(leads)))
        for lead in leads:
            _plan_lead(api, lead, ck, c, send_day, day1, day2, plan)
    matched = sum(len(v) for v in by_cid.values())
    if matched == 0 and stats.get("no_campaign_field_eligible"):
        raise NoCampaignFieldError(
            "%d lead(s) that can still get a step were listed WITHOUT a `campaign` field, and no lead matched any of "
            "the six AI-agents campaigns. The job cannot tell which campaign they belong to, so it wrote nothing. "
            "Check the leads/list response shape before trusting any run." % stats["no_campaign_field_eligible"])
    return plan, counts


def plan_one(api: Callable, ids: Dict[str, str], lead_id: str, send_day: date, day1: List[datetime],
             day2: List[datetime]) -> Tuple[List[dict], Dict[str, Dict[str, int]]]:
    """The plan for exactly one lead (--lead-id), read with GET leads/{id}."""
    try:
        lead = api("GET", "leads/%s" % lead_id) or {}
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - e.g. HTTP 404 for a wrong id
        raise LeadIdError("GET leads/%s failed: %s" % (lead_id, str(exc)[:200]))
    if lead.get("id") != lead_id:
        raise LeadIdError("GET leads/%s did not return that lead (got id %r)" % (lead_id, lead.get("id")))
    key_of = {v: k for k, v in ids.items()}
    ck = key_of.get(lead.get("campaign"))
    if ck is None:
        raise LeadIdError("lead %s is in campaign %r, not one of the six AI-agents campaigns"
                          % (lead_id, lead.get("campaign")))
    c = _new_counts(1)
    plan = []  # type: List[dict]
    _plan_lead(api, lead, ck, c, send_day, day1, day2, plan, refetch=False)
    return plan, {ck: c}


def backup_entry(item: dict) -> Dict[str, Any]:
    raw = item["raw"]
    return {"id": item["id"], "email": item.get("email") or raw.get("email"), "campaign": raw.get("campaign"),
            "campaign_key": item.get("campaign_key"), "payload": raw.get("payload"),
            "first_name": raw.get("first_name"), "company_name": raw.get("company_name"),
            "custom_variables": item["before"], "raw": raw}


def write_backup(plan: List[dict], send_day: date, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%dT%H%M%S")
    path = directory / ("slots_backup_%s_%s.json" % (send_day.isoformat(), stamp))
    n = 1
    while path.exists():
        n += 1
        path = directory / ("slots_backup_%s_%s_%d.json" % (send_day.isoformat(), stamp, n))
    doc = {"kind": "slots_backup", "ts": datetime.now(TZ).isoformat(), "send_day": send_day.isoformat(),
           "leads": [backup_entry(it) for it in plan]}
    path.write_text(json.dumps(doc, indent=1, default=str))
    return path


def readback_problems(backup: Dict[str, Any], got: dict, expected_slots: Dict[str, Any]
                      ) -> List[Tuple[str, str]]:
    """[] when the lead read back after its PATCH is intact and carries the new slots.
    Each problem is (summary, detail): the summary names the field only and may be
    logged; the detail carries the values and goes only into the backup file."""
    if not got or got.get("id") != backup["id"]:
        return [("read-back returned another lead",
                 "GET leads/%s did not return that lead (got id %r)" % (backup["id"], (got or {}).get("id")))]
    before, after = _vars_view(backup["raw"]), _vars_view(got)
    problems = []  # type: List[Tuple[str, str]]
    for k in READBACK_PAYLOAD_KEYS:
        if after.get(k) != before.get(k):
            problems.append(("payload.%s changed" % k,
                             "payload.%s changed: %r -> %r" % (k, before.get(k), after.get(k))))
    for k in READBACK_NONEMPTY_KEYS:
        # required only when the backup had it: a lead added by hand may never have had a lead_id
        if str(before.get(k) or "").strip() and not str(after.get(k) or "").strip():
            problems.append(("payload.%s empty" % k, "payload.%s is empty after the PATCH" % k))
    for k in READBACK_TOP_KEYS:
        if got.get(k) != backup["raw"].get(k):
            problems.append(("%s changed" % k, "%s changed: %r -> %r" % (k, backup["raw"].get(k), got.get(k))))
    for k in SLOT_KEYS:
        if after.get(k) != expected_slots.get(k):
            problems.append(("%s not set" % k,
                             "%s not set: want %r, got %r" % (k, expected_slots.get(k), after.get(k))))
    return problems


def _field_of(summary: str) -> str:
    """Every summary starts with the field name ('payload.firstName changed' -> 'payload.firstName')."""
    return summary.split(" ", 1)[0]


def record_readback_failure(backup_path: Path, private: Dict[str, Any]) -> bool:
    """Adds the read-back details (lead values) to the run's backup file, under
    `readback_failure`. --restore reads only `leads`, so the file stays usable."""
    try:
        doc = json.loads(Path(backup_path).read_text())
        doc["readback_failure"] = private
        Path(backup_path).write_text(json.dumps(doc, indent=1, default=str))
        return True
    except (OSError, ValueError, TypeError) as exc:
        log.error("could not add the read-back details to %s: %s", backup_path, exc)
        return False


def apply_updates(api: Callable, plan: List[dict], state: Dict[str, Any],
                  backups: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """PATCH each item's full `after` dict. With `backups` (id -> backup entry),
    the first successful PATCH is read back and checked; a failed check raises
    Abort("readback_failed"). MAX_CONSECUTIVE_FAILURES failures in a row raise
    Abort("failure_brake"). state["patched"] always holds the count so far."""
    ok, failed, streak, checked = 0, [], 0, backups is None
    state["patched"], state["failed"] = 0, 0
    for item in plan:
        try:
            api("PATCH", "leads/%s" % item["id"], {"custom_variables": item["after"]})
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - counted, then the brake decides
            failed.append({"id": item["id"], "error": str(exc)[:200]})
            state["failed"] = len(failed)
            log.error("PATCH leads/%s failed: %s", item["id"], str(exc)[:200])
            streak += 1
            if streak >= MAX_CONSECUTIVE_FAILURES:
                raise Abort("failure_brake", "%d PATCH failures in a row; stopped" % streak,
                            {"failures": failed[-MAX_CONSECUTIVE_FAILURES:]})
            continue
        ok, streak = ok + 1, 0
        state["patched"] = ok
        if not checked:
            checked = True
            try:
                got = api("GET", "leads/%s" % item["id"]) or {}
            except (Exception, SystemExit) as exc:  # noqa: BLE001
                got, problems = {}, [("read-back GET failed",
                                      "read-back GET leads/%s failed: %s" % (item["id"], str(exc)[:200]))]
            else:
                problems = readback_problems(backups[item["id"]], got, item["after"])
            summaries = [s for s, _ in problems]
            # no lead values here: state["readback"] and the Abort details go into the log line
            state["readback"] = {"id": item["id"], "ok": not problems, "problems": summaries}
            if problems:
                raise Abort("readback_failed", "first patched lead %s failed the read-back" % item["id"],
                            {"readback_lead_id": item["id"], "problems": summaries,
                             "failed_fields": sorted({_field_of(s) for s in summaries})},
                            private={"id": item["id"], "problems": [d for _, d in problems],
                                     "read_back": got})
    return {"patched": ok, "failed": len(failed), "failures": failed[:20]}


# ------------------------------------------------------------------ job
def live_allowed(environ: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get("MODE") == "live" and env.get("ALLOW_LIVE_WRITES") == "1"


def append_log(record: Dict[str, Any], path: Path = None) -> None:
    path = path or LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _make_api(call_fn: Optional[Callable], tok_fn: Optional[Callable], sleep: Callable) -> Paced:
    if call_fn is None or tok_fn is None:
        import instantly_push as ip
        call_fn = call_fn or ip.call
        tok_fn = tok_fn or ip.key
    return Paced(call_fn, tok_fn(), sleep=sleep)


def _done(rec: Dict[str, Any], log_path: Optional[Path], status: str, code: int, **extra: Any) -> int:
    rec.update(extra)
    rec["status"] = status
    append_log(rec, log_path)
    return code


def _run_slots(a: argparse.Namespace, rec: Dict[str, Any], state: Dict[str, Any], now: Optional[datetime],
               call_fn: Optional[Callable], tok_fn: Optional[Callable], free_fn: Optional[Callable],
               log_path: Optional[Path], sleep: Callable, old_ids_path: Optional[Path]) -> int:
    real_now = now or datetime.now(TZ)
    if a.date:
        send_day = _as_date(a.date)
        # simulate the scheduled 05:00 CT run on that day, unless that is in the past
        now_ = max(real_now, _local(send_day, 5, 0)) if now is None else real_now
    else:
        send_day = S.to_tz(S.ensure_aware(real_now, TZ), TZ).date()
        now_ = real_now
    rec["send_day"] = send_day.isoformat()

    free = (free_fn or ghl_free_slots)(now_)
    free = None if free is None else list(free)
    try:
        day1, day2, source = compute_slots(send_day, free, now_)
    except SlotError as exc:
        print("ERROR: %s" % exc)
        return _done(rec, log_path, "slot_error", 1, error=str(exc), source=slot_source(free))
    if source != "ghl":
        print_fallback_banner(source)
    print("send day D: %s (%s)   source: %s" % (send_day.isoformat(), send_day.strftime("%A"), source))
    print("slot1 day %s: %s" % (day1[0].date(), [fmt_slot(x) for x in day1]))
    print("slot2 day %s: %s" % (day2[0].date(), [fmt_slot(x, zone=True) for x in day2]))
    rec.update({"source": source, "slot1_options": [fmt_slot(x) for x in day1],
                "slot2_options": [fmt_slot(x, zone=True) for x in day2]})

    try:
        ids = load_ai_ids(a.ids_file, old_ids_path)
    except SystemExit as exc:
        print("ERROR: %s" % exc)
        return _done(rec, log_path, "ids_error", 1, error=str(exc))

    api = _make_api(call_fn, tok_fn, sleep)
    problems = campaign_copy_problems(api, ids)
    if problems:
        print("campaign copy check FAILED (every step-1 variant and the step-2 body need {{slot1}} and {{slot2}}):")
        for pr in problems:
            print("  - %s" % pr)
        rec["copy_problems"] = problems
        if a.apply:
            print("refused: --apply needs all six campaigns to pass the copy check. Nothing written.")
            return _done(rec, log_path, "copy_check_failed", 2)
        print("(dry-run: reported only; an --apply run would be refused)")
    else:
        print("campaign copy check: all six campaigns carry {{slot1}} and {{slot2}} in step 1 and step 2")

    stats = {}  # type: Dict[str, int]
    try:
        if a.lead_id:
            plan, counts = plan_one(api, ids, a.lead_id, send_day, day1, day2)
        else:
            plan, counts = plan_updates(api, ids, send_day, day1, day2, stats)
    except LeadIdError as exc:
        print("ERROR: %s" % exc)
        return _done(rec, log_path, "lead_id_refused", 1, error=str(exc))
    except NoCampaignFieldError as exc:
        print("!" * 72)
        print("!! NO LEAD MATCHED A CAMPAIGN: %s" % exc)
        print("!" * 72)
        return _done(rec, log_path, "no_campaign_field", 1, error=str(exc), list_stats=stats)
    if stats.get("no_campaign_field"):
        print("WARNING: %d listed lead(s) had no `campaign` field and were not counted"
              % stats["no_campaign_field"])
        rec["list_stats"] = stats
    for ck in AI_CAMPAIGN_KEYS:
        c = counts.get(ck, {})
        if a.lead_id and ck not in counts:
            continue
        print("  %-20s leads=%-5s eligible=%-5s would_change=%-5s unchanged=%-5s unreadable=%s"
              % (ck, c.get("leads", 0), c.get("eligible", 0), c.get("change", 0), c.get("unchanged", 0),
                 c.get("unreadable", 0)))
    for item in plan[:3]:
        print("sample %s (%s)\n  before: %s\n  after:  %s" % (item["email"], item["campaign_key"],
                                                          json.dumps(item["before"]), json.dumps(item["after"])))
    rec.update({"counts": counts, "to_change": len(plan)})
    if not a.apply:
        print("dry-run: %d lead(s) would be PATCHed; nothing written" % len(plan))
        return _done(rec, log_path, "dry_run_ok", 0)
    if not plan:
        print("nothing to PATCH")
        return _done(rec, log_path, "applied", 0, patched=0, failed=0)

    backup = write_backup(plan, send_day, (log_path or LOG_FILE).parent)
    rec["backup"] = str(backup)
    print("backup of %d lead(s): %s" % (len(plan), backup))
    backups = {e["id"]: e for e in json.loads(backup.read_text())["leads"]}
    res = apply_updates(api, plan, state, backups)
    if state.get("readback"):
        print("read-back of the first patched lead (%s): ok" % state["readback"]["id"])
    print("patched %d, failed %d" % (res["patched"], res["failed"]))
    rec["readback"] = state.get("readback")
    return _done(rec, log_path, "applied" if not res["failed"] else "applied_with_failures",
                 0 if not res["failed"] else 1, **res)


def _run_restore(a: argparse.Namespace, rec: Dict[str, Any], state: Dict[str, Any],
                 call_fn: Optional[Callable], tok_fn: Optional[Callable], log_path: Optional[Path],
                 sleep: Callable, old_ids_path: Optional[Path]) -> int:
    path = Path(a.restore)
    rec["backup"] = str(path)
    try:
        doc = json.loads(path.read_text())
        leads = doc["leads"]
        if not isinstance(leads, list):
            raise ValueError("`leads` is not a list")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ERROR: cannot read backup %s: %s" % (path, exc))
        return _done(rec, log_path, "restore_error", 1, error="%s: %s" % (type(exc).__name__, exc))
    if a.lead_id:
        leads = [l for l in leads if l.get("id") == a.lead_id]
        if not leads:
            print("ERROR: lead %s is not in %s" % (a.lead_id, path))
            return _done(rec, log_path, "restore_error", 1, error="lead not in backup")
    try:
        ids = load_ai_ids(a.ids_file, old_ids_path)
    except SystemExit as exc:
        print("ERROR: %s" % exc)
        return _done(rec, log_path, "ids_error", 1, error=str(exc))
    allowed = set(ids.values())
    bad = [l.get("id") for l in leads
           if l.get("campaign") not in allowed or existing_custom_variables({"custom_variables": l.get("custom_variables")}) is None]
    if bad:
        msg = "%d backup lead(s) are outside the six campaigns or have no usable saved variables: %s" % (len(bad), bad[:10])
        print("ERROR: %s" % msg)
        return _done(rec, log_path, "restore_error", 1, error=msg)
    plan = [{"id": l["id"], "email": l.get("email"), "campaign_key": l.get("campaign_key"),
             "after": l["custom_variables"]} for l in leads]
    print("restore from %s: %d lead(s)" % (path, len(plan)))
    for item in plan[:3]:
        print("  %s (%s) -> custom_variables %s" % (item["email"], item["id"], json.dumps(item["after"])))
    rec["to_restore"] = len(plan)
    if not a.apply:
        print("dry-run: %d lead(s) would be PATCHed back to their saved variables; nothing written" % len(plan))
        return _done(rec, log_path, "restore_dry_run_ok", 0)
    api = _make_api(call_fn, tok_fn, sleep)
    res = apply_updates(api, plan, state)
    print("restored %d, failed %d" % (res["patched"], res["failed"]))
    return _done(rec, log_path, "restored" if not res["failed"] else "restored_with_failures",
                 0 if not res["failed"] else 1, **res)


def run(argv: Optional[List[str]] = None, now: Optional[datetime] = None, call_fn: Callable = None,
        tok_fn: Callable = None, free_fn: Callable = None, environ: Optional[Dict[str, str]] = None,
        log_path: Optional[Path] = None, sleep: Callable = time.sleep, old_ids_path: Optional[Path] = None) -> int:
    p = argparse.ArgumentParser(description="Refresh {{slot1}}/{{slot2}} on AI-agents campaign leads")
    p.add_argument("--apply", action="store_true", help="write (needs MODE=live and ALLOW_LIVE_WRITES=1)")
    p.add_argument("--date", help="send day D as YYYY-MM-DD (default: today in CT)")
    p.add_argument("--ids-file", help="AI-agents campaign ids JSON (default %s)" % IDS_FILE.name)
    p.add_argument("--lead-id", help="run the whole flow on exactly this one lead (rehearsal)")
    p.add_argument("--restore", metavar="BACKUP_FILE",
                   help="PATCH each lead in a slots_backup_*.json back to its saved variables (dry-run unless --apply)")
    usage_msgs = []  # type: List[str]
    argparse_error = p.error

    def _error(message: str) -> None:
        usage_msgs.append(message)
        argparse_error(message)
    p.error = _error  # type: ignore[assignment]
    try:
        a = p.parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):  # --help exits 0 and is not an error
            append_log({"ts": datetime.now(TZ).isoformat(), "kind": "usage", "status": "usage_error",
                        "argv": list(sys.argv[1:] if argv is None else argv),
                        "error": usage_msgs[-1] if usage_msgs else "exit %s" % exc.code}, log_path)
        raise

    rec = {"ts": datetime.now(TZ).isoformat(), "mode": "apply" if a.apply else "dry-run",
           "kind": "restore" if a.restore else "slots"}  # type: Dict[str, Any]
    if a.lead_id:
        rec["lead_id"] = a.lead_id
    if a.apply and not live_allowed(environ):
        print("refused: --apply needs MODE=live and ALLOW_LIVE_WRITES=1 in the environment (Lorenzo sets them). "
              "Nothing read or written.")
        return _done(rec, log_path, "refused", 2, error="live flags missing")

    state = {"patched": 0, "failed": 0}  # type: Dict[str, Any]
    prev_handlers = _install_signal_handlers()
    try:
        if a.restore:
            return _run_restore(a, rec, state, call_fn, tok_fn, log_path, sleep, old_ids_path)
        return _run_slots(a, rec, state, now, call_fn, tok_fn, free_fn, log_path, sleep, old_ids_path)
    except Abort as exc:
        print("!" * 72)
        print("!! ABORTED (%s) after %d lead(s) updated: %s" % (exc.status, state["patched"], exc))
        for pr in exc.details.get("problems", []):
            print("!!   - %s" % pr)
        if exc.private and rec.get("backup") and record_readback_failure(Path(rec["backup"]), exc.private):
            rec["details_in"] = rec["backup"]
            print("!! read-back values: `readback_failure` in %s" % rec["backup"])
        if rec.get("backup") and not a.restore:
            print("!! undo with: python3 slots_daily.py --restore %s   (then the same with --apply)" % rec["backup"])
        print("!" * 72)
        if state.get("readback"):
            rec["readback"] = state["readback"]
        return _done(rec, log_path, exc.status, 3, error=str(exc), patched=state["patched"],
                     failed=state["failed"], **exc.details)
    except KeyboardInterrupt as exc:  # Ctrl-C, or SIGTERM / SIGHUP via Interrupted
        _ignore_signals()  # a second Ctrl-C must not cut the log line short
        signum = exc.signum if isinstance(exc, Interrupted) else signal.SIGINT
        name = signal.Signals(signum).name
        print("!" * 72)
        print("!! INTERRUPTED (%s) after %d lead(s) updated, %d failed" % (name, state["patched"], state["failed"]))
        if rec.get("backup") and not a.restore:
            print("!! undo with: python3 slots_daily.py --restore %s   (then the same with --apply)" % rec["backup"])
        elif a.restore:
            print("!! the restore is partial; finish it with: python3 slots_daily.py --restore %s --apply" % a.restore)
        print("!" * 72)
        if state.get("readback"):
            rec["readback"] = state["readback"]
        return _done(rec, log_path, "interrupted", 128 + int(signum), signal=name, patched=state["patched"],
                     failed=state["failed"])
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - every run leaves a log line
        print("ERROR: %s mid-run after %d lead(s) updated: %s" % (type(exc).__name__, state["patched"], exc))
        if rec.get("backup") and not a.restore:
            print("undo with: python3 slots_daily.py --restore %s   (then the same with --apply)" % rec["backup"])
        return _done(rec, log_path, "exception", 3, error="%s: %s" % (type(exc).__name__, str(exc)[:300]),
                     patched=state["patched"], failed=state["failed"])
    finally:
        _restore_signal_handlers(prev_handlers)


# ------------------------------------------------------------------ signals
_STOP_SIGNALS = tuple(s for s in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGHUP", None)) if s)


def _raise_interrupted(signum: int, frame: Any) -> None:
    raise Interrupted(signum)


def _install_signal_handlers() -> Dict[int, Any]:
    """SIGTERM and SIGHUP raise Interrupted for the rest of the run (SIGINT
    already raises KeyboardInterrupt). A signal someone set to SIG_IGN (nohup)
    stays ignored. Returns the previous handlers of SIGINT, SIGTERM and SIGHUP."""
    prev = {}  # type: Dict[int, Any]
    for sig in (signal.SIGINT,) + _STOP_SIGNALS:
        try:
            prev[sig] = signal.getsignal(sig)
            if sig != signal.SIGINT and prev[sig] is not signal.SIG_IGN:
                signal.signal(sig, _raise_interrupted)
        except (ValueError, OSError):  # not the main thread: leave the handlers alone
            prev.pop(sig, None)
    return prev


def _ignore_signals() -> None:
    for sig in (signal.SIGINT,) + _STOP_SIGNALS:
        try:
            signal.signal(sig, signal.SIG_IGN)
        except (ValueError, OSError):
            pass


def _restore_signal_handlers(prev: Dict[int, Any]) -> None:
    for sig, handler in prev.items():
        try:
            signal.signal(sig, handler if handler is not None else signal.SIG_DFL)
        except (ValueError, OSError, TypeError):
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run())
