"""Level 4 - Saturday auto-responder canary (Blueprint M1 L4, job O7).

    cd "Agentic Worklfows"
    python3 jobs/autoresponder_canary.py --dry-run            # harvest, plan, score the last round
    python3 jobs/autoresponder_canary.py --dry-run --harvest-only
    python3 jobs/autoresponder_canary.py --now                # same + change-set + sidecar + push

The idea (Eric's practice, from the video transcript, not a published spec):
mailboxes that answer everything automatically are a free delivery probe. Send
one plain email from each inbox to a handful of them and count the automatic
answers. At least CANARY_RESPONSE_TARGET_PCT is healthy; under
CANARY_RESPONSE_KILL_PCT the inbox is not reaching mailboxes at all and is
proposed for the kill, whatever its warm-up score says.

Two things make this the most dangerous job in the set, and both are handled
here rather than in a comment on the runbook:

**1. The canary send is a real email to a real person's mailbox.** Every
harvested address belongs to a prospect who once received a cold email from
Lorenzo. So the plan is filtered: anyone who is on the blocklist, who ever
answered with a negative interest status, or whose auto-reply says the address
is dead is dropped before the plan is built. What is left is an address that
answers automatically and has shown no sign of objecting.

**2. Instantly v2 has no endpoint that sends an arbitrary email.**
``POST /emails/reply`` replies inside an existing thread and is the wrong tool:
replying into a cold-email thread to probe deliverability puts a second unwanted
message in a prospect's inbox, and ``shared.instantly.reply_to_email`` would
happily do it. This job therefore does NOT send. It records the would_do as a
``canary_send_staged`` shadow-log row whose status is ``manual_send_required``
and never calls ``settings.guard_write``, because a guarded write opens a
``live_write_intent`` Job_Log row that no code path here could ever close. The
live procedure in runbooks/deliverability.md creates a one-off Instantly
campaign whose lead list is the harvested addresses and whose email_list is the
inboxes being tested. That is the only documented mechanism, and it keeps the
send inside the same rate limits, schedule and stop_on_reply rules as everything
else. Whether Instantly's "send a test email" endpoint (rate-limited at 10/min
in the API contract's rate-limit table) can do this in one call is an open
question for Lorenzo; guessing a send endpoint is not something this job does.

Scoring a round needs no send at all: the round's inbox/address plan is kept in
the sidecar, and the next run counts which of those addresses answered after the
send timestamp by reading GET /emails?email_type=received.
"""
import argparse
import json
import logging
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from shared import job_log  # noqa: E402
from shared import settings  # noqa: E402
from shared import thresholds as TH  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.settings import TZ  # noqa: E402

from jobs.deliverability_monitor import (  # noqa: E402
    CHANGESET_DIR,
    ROLE_SENDING,
    _pause_actions,
    _parse_ts,
    _read_sidecar,
    build_inbox_index,
    load_accounts,
    load_campaign_email_lists,
    write_changeset,
    write_sidecar,
)

logger = logging.getLogger("jobs.autoresponder_canary")

JOB = "autoresponder_canary"
SIDECAR = "last_canary.json"

# There is no send path in this process (module docstring, point 2), so the
# staged round is recorded under its own action name and its own status.
# Neither may ever read as an intent to write: see _stage_manual_sends().
CANARY_SEND_ACTION = "canary_send_staged"
MANUAL_SEND_STATUS = "manual_send_required"

# Copy rules from config/offers.md apply: no em dashes, no exclamation marks,
# never mention AI or automation, sign "Lorenzo". A canary that looks like a
# test harness gets filtered like a test harness, which would make every
# reading of this level wrong.
CANARY_SUBJECT = "quick question"
CANARY_BODY = (
    "Hi there,\n\n"
    "Reaching out to see whether this is still the right address for you.\n"
    "If it is not, no need to reply.\n\n"
    "Lorenzo\n"
)

# An auto-reply saying the address is dead is not a canary target: it is a
# mailbox that will never be read and, in several cases, one that bounces later.
DEAD_ADDRESS_PATTERNS = ("no longer monitored", "no longer in use")


# =========================================================================
# Harvest
# =========================================================================

def is_autoresponder_subject(subject: Optional[str]) -> bool:
    text = (subject or "").lower()
    return any(p in text for p in TH.AUTORESPONDER_SUBJECT_PATTERNS)


def harvest_addresses(client: Any, max_pages: Optional[int] = None,
                      received: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Read-only harvest from GET /emails?email_type=received (M1 L4).

    ``received`` lets a test or a replay pass recorded rows instead of calling
    the API. GET /emails is capped at 20 requests per minute workspace-wide,
    which is why the page budget is a named constant rather than "walk it all".
    """
    max_pages = TH.CANARY_HARVEST_MAX_PAGES if max_pages is None else max_pages
    if received is None:
        walk = client.iterate("emails", params={"email_type": "received", "limit": 100},
                              max_pages=max_pages)
        received = list(walk)
        if getattr(walk, "truncated", False):
            # A partial harvest decides WHO GETS MAILED. load_accounts already
            # refuses on a truncated walk for exactly this reason; this walk is
            # the one that picks real people's mailboxes, so it refuses too.
            raise RuntimeError(
                "the received-mail walk stopped at max_pages=%d with the cursor still open, so the "
                "harvest is partial and the pool would change week to week for reasons nobody can "
                "see. Raise CANARY_HARVEST_MAX_PAGES or pass recorded rows." % max_pages)
    found = {}  # type: Dict[str, Dict[str, Any]]
    dead = {}  # type: Dict[str, str]
    for row in received:
        subject = row.get("subject") or ""
        if not is_autoresponder_subject(subject):
            continue
        addr = (row.get("from_address_email") or "").strip().lower()
        if not addr:
            continue
        lowered = subject.lower()
        if any(p in lowered for p in DEAD_ADDRESS_PATTERNS):
            dead[addr] = subject
            continue
        found.setdefault(addr, {
            "email": addr, "subject": subject, "seen_on_inbox": row.get("eaccount"),
            "last_seen": row.get("timestamp_created") or row.get("timestamp_email"),
            "interest_status": row.get("i_status"),
        })
    return {"addresses": sorted(found.values(), key=lambda r: r["email"]),
            "dead": dead, "scanned": len(received)}


def load_blocklist(client: Any) -> List[str]:
    """Anyone on the blocklist is never mailed again, canary included.

    This read may not fail open, in either of its two ways. An exception
    refuses, and so does a **truncated** walk: the cap used to be a bare
    ``max_pages=10`` and nothing read ``CursorWalk.truncated``, so a blocklisted
    prospect past entry 1,000 was simply absent from the list and kept as a
    canary target. The module docstring and the runbook both promise the
    opposite, so the operator had no reason to check.
    """
    try:
        walk = client.iterate("block-lists-entries", params={"limit": 100},
                              max_pages=TH.BLOCKLIST_MAX_PAGES)
        rows = list(walk)
    except Exception as exc:  # noqa: BLE001 - an unreadable blocklist must not silently open the gate
        raise RuntimeError("could not read the blocklist (%s); refusing to plan a canary without it"
                           % str(exc)[:160])
    if getattr(walk, "truncated", False):
        raise RuntimeError(
            "the blocklist walk was truncated at %d pages with the cursor still open; refusing to "
            "plan a canary on a partial blocklist. Anyone past that point asked to be left alone "
            "and would be mailed again." % TH.BLOCKLIST_MAX_PAGES)
    out = []
    for row in rows:
        value = (row.get("bl_value") or row.get("value") or "").strip().lower()
        if value:
            out.append(value)
    return out


def resolve_interest_statuses(client: Any, addresses: Sequence[Dict[str, Any]],
                              batch: int = 50) -> Dict[str, Any]:
    """The authoritative interest status per address, read from the LEAD.

    ``i_status`` on a received message is null for 8 of the 29 addresses
    harvested live on 2026-09-22, and ``harvest_addresses`` pins whichever row
    it saw first. A prospect who answered "not interested" (status -1 on the
    lead) but whose auto-reply row carries no status was therefore kept as a
    canary target, while the runbook promises without qualification that anyone
    with a negative status is dropped.

    Returns ``{'statuses': {address: status_or_None}, 'unresolved': [address],
    'error': str_or_None}``. An address that could not be read is *unresolved*,
    and ``suppress`` fails closed on it.
    """
    emails = [a["email"] for a in addresses]
    statuses = {}  # type: Dict[str, Any]
    unresolved = []  # type: List[str]
    error = None
    for i in range(0, len(emails), max(1, batch)):
        chunk = emails[i:i + max(1, batch)]
        try:
            data = client.list_leads(contacts=list(chunk), limit=100)
        except Exception as exc:  # noqa: BLE001 - a failed read means "unverified", never "fine"
            error = str(exc)[:200]
            unresolved.extend(chunk)
            continue
        items = data.get("items") if isinstance(data, dict) else data
        seen = set()
        for row in items or []:
            addr = (row.get("email") or "").strip().lower()
            if not addr:
                continue
            seen.add(addr)
            value = row.get("i_status")
            if value is None:
                value = row.get("interest_status")
            # Several leads can share an address across campaigns. The most
            # negative status wins: one "not interested" anywhere is a no.
            prior = statuses.get(addr)
            if addr in statuses and prior is not None and value is not None:
                statuses[addr] = min(_as_int(prior), _as_int(value))
            elif addr not in statuses or statuses[addr] is None:
                statuses[addr] = value
        unresolved.extend([e for e in chunk if e not in seen])
    return {"statuses": statuses, "unresolved": sorted(set(unresolved)), "error": error}


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def negative_status_codes() -> Dict[int, str]:
    """{-1: 'not_interested', ...} from config/ids.json."""
    codes = settings.IDS.get("instantly", {}).get("interest_status_codes") or {}
    out = {}  # type: Dict[int, str]
    for raw, name in codes.items():
        value = _as_int(raw)
        if value is not None and value < 0:
            out[value] = name
    return out


def suppress(addresses: List[Dict[str, Any]], blocklist: Sequence[str],
             statuses: Optional[Dict[str, Any]] = None,
             unresolved: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Drop anyone blocklisted (by address or domain) or marked negative.

    Negative interest statuses come from config/ids.json:
    -1 not interested, -2 wrong person, -3 lost, -4 no show. A canary to someone
    who told Lorenzo to stop is the single worst thing this system could do.

    ``statuses`` is the authoritative per-address status from
    ``resolve_interest_statuses``; when it is given it overrides whatever the
    harvested message carried. **Any address whose status could not be verified
    is dropped**, because "no status on the auto-reply row" and "no negative
    status on the lead" are not the same statement and this side of the check is
    the half that protects someone who asked to be left alone.
    """
    codes = negative_status_codes()
    label = settings.IDS.get("instantly", {}).get("interest_status_codes") or {}
    blocked_exact = set(b for b in blocklist if "@" in b)
    blocked_domains = set(b for b in blocklist if "@" not in b and b)
    unresolved = set(unresolved or [])
    kept, dropped = [], []
    for row in addresses:
        addr = row["email"]
        domain = addr.rsplit("@", 1)[-1]
        reason = None
        if addr in blocked_exact:
            reason = "blocklisted"
        elif domain in blocked_domains:
            reason = "domain blocklisted"
        elif statuses is not None and addr in unresolved:
            reason = "interest status could not be verified on the lead"
        else:
            if statuses is not None:
                status = _as_int(statuses.get(addr))
                verified = addr in statuses
            else:
                status = _as_int(row.get("interest_status"))
                verified = status is not None
            if status is not None and status in codes:
                reason = "interest status %s (%s)" % (status, label.get(str(status), "negative"))
            elif not verified:
                reason = "interest status could not be verified on the lead"
        if reason:
            dropped.append(dict(row, dropped_because=reason))
        else:
            kept.append(row)
    return {"kept": kept, "dropped": dropped}


# =========================================================================
# Plan and score
# =========================================================================

def build_plan(inboxes: List[Dict[str, Any]], addresses: List[Dict[str, Any]],
               now: datetime, per_inbox: Optional[int] = None) -> Dict[str, Any]:
    """Partition the harvested pool across the sending inboxes.

    **The pool is partitioned, never wrapped.** The round-robin modulo this
    replaces over-subscribed the pool: 12 inboxes x 10 addresses drawn from 29
    harvested mailboxes meant every one of those 29 real prospects received 4 or
    5 near-identical notes on the same day, each from a different Advero domain.
    At the Oct 11 target of 45 sending inboxes it would have been 18 or 19 each.
    That is the burst-from-many-domains pattern that gets a domain group
    filtered, aimed squarely at the mailboxes this monitor exists to protect the
    domains from, and it was produced by the job whose job is to detect exactly
    that damage.

    So the round is clamped to what the pool can cover
    (``CANARY_MAX_SENDS_PER_ADDRESS``), and when the clamp falls below
    ``CANARY_MIN_ADDRESSES_FOR_VERDICT`` nothing is planned at all: a pool that
    cannot give every inbox that many distinct addresses cannot produce a
    verdict, and sending anyway would be damage with no reading to show for it.

    Rotating the start by day means consecutive rounds do not hand the same
    mailbox to the same inbox.
    """
    requested = TH.CANARY_ADDRESSES_PER_INBOX if per_inbox is None else per_inbox
    targets = [i for i in inboxes if i["role"] == ROLE_SENDING]
    seen = set()
    pool = []
    for a in addresses:
        addr = (a.get("email") or "").strip().lower()
        if addr and addr not in seen:
            seen.add(addr)
            pool.append(addr)
    base = {"round_id": None, "per_inbox": 0, "requested_per_inbox": requested,
            "assignments": [], "pool_size": len(pool), "inboxes": len(targets),
            "sends_per_address": TH.CANARY_MAX_SENDS_PER_ADDRESS, "refused": True}
    if not pool:
        base["note"] = "no harvested addresses survived suppression; nothing to send"
        return base
    if not targets:
        base["note"] = "no sending inbox to canary; nothing to send"
        return base

    capacity = (len(pool) * TH.CANARY_MAX_SENDS_PER_ADDRESS) // len(targets)
    allowed = min(requested, capacity, len(pool))
    if allowed < min(TH.CANARY_MIN_ADDRESSES_FOR_VERDICT, requested):
        base["per_inbox"] = allowed
        base["note"] = (
            "pool too small, harvest more addresses: %d usable address(es) cannot give %d sending "
            "inbox(es) %d distinct target(s) each at %d send(s) per mailbox (that is %d each, and a "
            "verdict needs %d). Nothing is planned; mailing the same prospects several times from "
            "several domains to measure deliverability is the damage this level looks for."
            % (len(pool), len(targets), requested, TH.CANARY_MAX_SENDS_PER_ADDRESS, allowed,
               TH.CANARY_MIN_ADDRESSES_FOR_VERDICT))
        return base

    offset = now.astimezone(TZ).toordinal() % len(pool)
    rotated = pool[offset:] + pool[:offset]
    # Repeating the pool CANARY_MAX_SENDS_PER_ADDRESS times and then cutting
    # consecutive, non-overlapping slices is what bounds a mailbox's exposure:
    # at the default of 1 the slices are a true partition.
    expanded = rotated * TH.CANARY_MAX_SENDS_PER_ADDRESS
    plan = []
    for n, inbox in enumerate(targets):
        take = expanded[n * allowed:(n + 1) * allowed]
        plan.append({"email": inbox["email"], "domain": inbox["domain"],
                     "in_campaigns": inbox["in_campaigns"], "targets": list(take)})
    counts = Counter(t for a in plan for t in a["targets"])
    return {"round_id": "canary-%s" % now.astimezone(TZ).strftime("%Y%m%dT%H%M"),
            "per_inbox": allowed, "requested_per_inbox": requested, "assignments": plan,
            "pool_size": len(pool), "inboxes": len(targets),
            "sends_per_address": max(counts.values()) if counts else 0,
            "distinct_addresses": len(counts),
            "total_sends": sum(counts.values()), "refused": False,
            "note": ("" if allowed == requested else
                     "clamped from %d to %d address(es) per inbox so no mailbox is mailed more than "
                     "%d time(s) in this round" % (requested, allowed, TH.CANARY_MAX_SENDS_PER_ADDRESS))}


def realised_assignments(sent_rows: Sequence[Dict[str, Any]], sent_at: datetime,
                         window_end: datetime) -> Dict[str, List[str]]:
    """{inbox: [addresses it actually mailed]} from GET /emails?email_type=sent.

    This is the denominator the score needs. The plan says who *should* have
    mailed whom; Instantly decides who actually did, and the two only agree when
    every canary campaign has an ``email_list`` of exactly one account.
    """
    out = {}  # type: Dict[str, List[str]]
    for row in sent_rows or []:
        ts = _parse_ts(row.get("timestamp_created") or row.get("timestamp_email"))
        if ts is None or ts < sent_at or ts > window_end:
            continue
        inbox = (row.get("eaccount") or row.get("from_address_email") or "").strip().lower()
        raw_to = row.get("to_address_email_list") or row.get("lead") or row.get("to_address_email") or ""
        for addr in str(raw_to).split(","):
            addr = addr.strip().lower()
            if inbox and addr:
                bucket = out.setdefault(inbox, [])
                if addr not in bucket:
                    bucket.append(addr)
    return out


def score_round(previous: Optional[Dict[str, Any]], received: List[Dict[str, Any]],
                now: datetime, inbox_index: Optional[Dict[str, Dict[str, Any]]] = None,
                sent: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Count auto-responses to the previous round.

    A round is only scorable once it has actually been sent, which in shadow it
    never is. ``sent_at`` is written into the sidecar by whoever performs the
    live send (the runbook's step 6); without it this reports ``not_sent`` and
    proposes nothing, rather than scoring an unsent round as 0% and killing
    every inbox in the fleet.

    **Attribution.** The numerator was always measured: an auto-reply arrives at
    the inbox that sent, so the received row's ``eaccount`` is the truth. The
    denominator was not. Scoring "how many of the ten addresses I *planned* for
    this inbox answered it" is only correct if that inbox really mailed those
    ten, and under the old runbook procedure (one campaign, ``email_list`` of
    all twelve inboxes, 29 leads) Instantly mailed each lead once from an inbox
    of its own choosing. Replaying the committed 120-pair plan with every one of
    the 29 mailboxes answering scored all twelve inboxes at 0-20% and proposed
    killing the entire sending fleet.

    So: pass ``sent`` (GET /emails?email_type=sent inside the round window) and
    the denominator is what each inbox really mailed. Without it the plan is
    used as a fallback and an attribution sanity check applies - if the round as
    a whole answered at or above the kill line while individual inboxes are
    being condemned, that is an attribution failure and the round is reported
    unscorable rather than turned into pause proposals.
    """
    inbox_index = inbox_index or {}
    if not previous or not previous.get("plan", {}).get("assignments"):
        return {"scored": False, "reason": "no previous canary round recorded", "rows": [], "failing": []}
    sent_at = _parse_ts(previous.get("sent_at"))
    if sent_at is None:
        return {"scored": False, "rows": [], "failing": [],
                "reason": ("previous round %s was planned but never marked sent (no sent_at in the "
                           "sidecar), so there is nothing to score"
                           % previous.get("plan", {}).get("round_id"))}
    window_end = sent_at + timedelta(hours=TH.CANARY_RESPONSE_WINDOW_HOURS)
    if now < window_end:
        return {"scored": False, "rows": [], "failing": [], "window_open": True,
                "reason": "the %dh response window for %s closes at %s"
                          % (TH.CANARY_RESPONSE_WINDOW_HOURS, previous["plan"]["round_id"],
                             window_end.astimezone(TZ).isoformat())}
    # {(inbox, from_address)} that answered automatically inside the window.
    answered = set()
    for row in received:
        ts = _parse_ts(row.get("timestamp_created") or row.get("timestamp_email"))
        if ts is None or ts < sent_at or ts > window_end:
            continue
        if not is_autoresponder_subject(row.get("subject")):
            continue
        answered.add(((row.get("eaccount") or "").strip().lower(),
                      (row.get("from_address_email") or "").strip().lower()))

    planned = OrderedDict()
    for assignment in previous["plan"]["assignments"]:
        planned[assignment["email"]] = list(assignment["targets"])

    attribution = "planned"
    per_inbox = planned
    if sent is not None:
        measured = realised_assignments(sent, sent_at, window_end)
        planned_addresses = set(a for targets in planned.values() for a in targets)
        measured = {k: [a for a in v if a in planned_addresses] for k, v in measured.items()}
        measured = {k: v for k, v in measured.items() if v}
        if not measured:
            return {"scored": False, "rows": [], "failing": [], "attribution": "none",
                    "reason": ("round %s is marked sent at %s but GET /emails?email_type=sent shows no "
                               "canary message to any of its %d planned addresses inside the %dh "
                               "window, so there is nothing to attribute and nothing to score"
                               % (previous["plan"]["round_id"], previous.get("sent_at"),
                                  len(planned_addresses), TH.CANARY_RESPONSE_WINDOW_HOURS))}
        attribution = "measured"
        per_inbox = OrderedDict()
        for email in list(planned) + [k for k in sorted(measured) if k not in planned]:
            per_inbox[email] = measured.get(email, [])

    rows, failing = [], []
    for inbox, targets in per_inbox.items():
        got = sum(1 for t in targets if (inbox, t) in answered)
        pct = TH.rate_pct(got, len(targets))
        meta = inbox_index.get(inbox) or {}
        row = {"email": inbox, "sent": len(targets), "responses": got,
               "response_pct": round(pct, 2), "attribution": attribution,
               "in_campaigns": meta.get("in_campaigns")
               or planned and next((a.get("in_campaigns") for a in previous["plan"]["assignments"]
                                    if a["email"] == inbox), []) or []}
        if len(targets) < TH.CANARY_MIN_ADDRESSES_FOR_VERDICT:
            row["verdict"] = "insufficient"
            row["reason"] = ("only %d canary addresses (need %d) so the rate is not a verdict"
                             % (len(targets), TH.CANARY_MIN_ADDRESSES_FOR_VERDICT))
        elif pct < TH.CANARY_RESPONSE_KILL_PCT:
            row["verdict"] = "kill"
            row["reason"] = ("%.0f%% auto-responses is below the %.0f%% kill line"
                             % (pct, TH.CANARY_RESPONSE_KILL_PCT))
            failing.append(row)
        elif pct < TH.CANARY_RESPONSE_TARGET_PCT:
            row["verdict"] = "warn"
            row["reason"] = ("%.0f%% auto-responses is below the %.0f%% target but above the kill line"
                             % (pct, TH.CANARY_RESPONSE_TARGET_PCT))
        else:
            row["verdict"] = "ok"
            row["reason"] = "%.0f%% auto-responses" % pct
        rows.append(row)

    guard = _attribution_guard(attribution, per_inbox, answered, failing, rows)
    if guard:
        return guard
    return {"scored": True, "round_id": previous["plan"]["round_id"], "sent_at": previous.get("sent_at"),
            "attribution": attribution, "rows": rows, "failing": failing, "reason": ""}


def _attribution_guard(attribution: str, per_inbox: Dict[str, List[str]], answered: set,
                       failing: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Refuse to turn an attribution failure into twelve dead inboxes.

    If the round as a whole answered at or above the kill line while individual
    inboxes are being condemned, the sends did not go out the way the plan says
    they did. That is the signature of one shared canary campaign: Instantly
    rotated the leads across the ``email_list`` and every planned (inbox,
    address) pair missed. Killing the fleet on that reading is the worst
    possible outcome, so the round is reported unscorable and Lorenzo is told
    which procedure produces a scorable one.
    """
    if attribution != "planned" or not failing:
        return None
    distinct = set(a for targets in per_inbox.values() for a in targets)
    replied = set(addr for _, addr in answered if addr in distinct)
    overall = TH.rate_pct(len(replied), len(distinct))
    if overall < TH.CANARY_RESPONSE_KILL_PCT:
        return None
    return {"scored": False, "rows": rows, "failing": [], "attribution": "unattributable",
            "reason": ("%d of %d canary mailboxes (%.0f%%) auto-replied, yet %d inbox(es) score under "
                       "the %.0f%% kill line against the PLANNED assignment. That is an attribution "
                       "failure, not a dead fleet: the round was sent through a campaign whose "
                       "email_list held more than one inbox, so Instantly chose which inbox mailed "
                       "which address. Re-run the round as one campaign per inbox (runbooks/"
                       "deliverability.md level 4), or re-score with GET /emails?email_type=sent."
                       % (len(replied), len(distinct), overall, len(failing),
                          TH.CANARY_RESPONSE_KILL_PCT))}


# =========================================================================
# The run
# =========================================================================

def _walk_emails(client: Any, email_type: str) -> List[Dict[str, Any]]:
    """One GET /emails walk, refusing a partial read.

    ``scan_bounce_signatures`` in the monitor tolerates a partial scan and says
    so on the card; these two walks decide who gets mailed and how a round is
    scored, so they do not.
    """
    walk = client.iterate("emails", params={"email_type": email_type, "limit": 100},
                          max_pages=TH.CANARY_HARVEST_MAX_PAGES)
    rows = list(walk)
    if getattr(walk, "truncated", False):
        raise RuntimeError(
            "the %s-mail walk stopped at max_pages=%d with the cursor still open; a partial read "
            "here silently changes who is mailed and how a round scores"
            % (email_type, TH.CANARY_HARVEST_MAX_PAGES))
    return rows


def _pace_emails_endpoint(sleep: Callable[[float], None] = time.sleep) -> None:
    """GET /emails is capped at EMAILS_ENDPOINT_REQUESTS_PER_MINUTE workspace
    wide, and this job is the only caller that makes two multi-page walks back
    to back. One interval between them keeps it inside the envelope."""
    try:
        sleep(60.0 / float(TH.EMAILS_ENDPOINT_REQUESTS_PER_MINUTE))
    except (TypeError, ValueError, ZeroDivisionError):
        sleep(1.0)


def _pending_round(previous: Optional[Dict[str, Any]], now: datetime) -> Optional[str]:
    """The reason this run must not plan over the sidecar, or None.

    A round is pending when it has been marked sent and its response window has
    not closed. Replacing it destroys the only record of which inbox mailed
    which prospect.
    """
    if not previous:
        return None
    sent_at = _parse_ts(previous.get("sent_at"))
    if sent_at is None:
        return None
    window_end = sent_at + timedelta(hours=TH.CANARY_RESPONSE_WINDOW_HOURS)
    if now >= window_end:
        return None
    plan = previous.get("plan") or {}
    return ("round %s was sent at %s and its %dh response window closes at %s, so this run kept the "
            "existing plan and planned nothing new. Overwriting it would lose the record of which "
            "inbox mailed which mailbox, and those emails have already been delivered."
            % (plan.get("round_id"), previous.get("sent_at"), TH.CANARY_RESPONSE_WINDOW_HOURS,
               window_end.astimezone(TZ).isoformat()))


def _stage_manual_sends(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Record the planned round as the manual step it is. Nothing is sent.

    This deliberately does NOT go through ``settings.guard_write``. There is no
    live branch anywhere in this job (module docstring, point 2): Instantly v2
    has no endpoint that sends an arbitrary email, so a round is mailed by hand
    from the UI, one campaign per inbox, per runbooks/deliverability.md level 4.

    ``guard_write`` in MODE=live writes a ``live_write_intent`` Job_Log row
    BEFORE the call it is meant to precede, and that row is meant to be closed
    by a ``live_write_ok`` / ``live_write_failed`` from the same code path. No
    code path here can send, so the row could never be closed: the Job_Log
    Lorenzo is told to read as his safety gate claimed an intent to email a
    real prospect's mailbox that nothing in this process could carry out, and
    an incident reconciliation would have to chase every one of them.

    The round lands in the shadow log instead, where every other would_do is
    read from, under its own action (``canary_send_staged``) and carrying its
    own status (``manual_send_required``) plus ``sent_by_this_job: false``, in
    every mode. It is a no-op record and it says so.
    """
    staged = []  # type: List[Dict[str, Any]]
    for assignment in plan.get("assignments") or []:
        payload = {
            "eaccount": assignment["email"],
            "to": assignment["targets"],
            "subject": CANARY_SUBJECT,
            "body": {"text": CANARY_BODY},
            "_status": MANUAL_SEND_STATUS,
            "_sent_by_this_job": False,
            "_mechanism": ("one campaign per inbox, see runbooks/deliverability.md level 4; "
                           "there is no v2 endpoint for an arbitrary outbound email"),
        }
        job_log.shadow("instantly", CANARY_SEND_ACTION, payload)
        staged.append({"system": "instantly", "action": CANARY_SEND_ACTION,
                       "status": MANUAL_SEND_STATUS, "sent_by_this_job": False,
                       "mode": settings.get_mode(), "payload": payload})
    return staged


def run_canary(now: datetime, client: Any = None, dry_run: bool = True,
               notify_fn: Callable = notify, log_fn: Callable = log_run,
               changeset_dir: Path = CHANGESET_DIR, received: Optional[List[Dict[str, Any]]] = None,
               write: Optional[bool] = None, send_card: Optional[bool] = None,
               harvest_only: bool = False, per_inbox: Optional[int] = None,
               campaigns: Optional[Dict[str, Any]] = None,
               blocklist: Optional[List[str]] = None,
               sent: Optional[List[Dict[str, Any]]] = None,
               resolve_statuses: bool = True) -> Dict[str, Any]:
    if client is None:
        from shared.instantly import default_client
        client = default_client()
    notes = []  # type: List[str]
    # Reads that failed. Any one makes the run "partial": logged as such, a
    # high-priority push, and a non-zero exit (MKT-9). An unreadable blocklist
    # used to log "ok_unscored" with a default-priority push, which reads as a
    # quiet Saturday rather than a canary that could not plan.
    read_failures = []  # type: List[str]

    if received is None:
        received = _walk_emails(client, "received")
    harvest = harvest_addresses(client, received=received)

    if blocklist is None:
        try:
            blocklist = load_blocklist(client)
        except RuntimeError as exc:
            notes.append(str(exc))
            read_failures.append("blocklist unreadable: %s" % str(exc)[:160])
            blocklist = None
    if blocklist is None:
        # No plan without a blocklist. Scoring the previous round is still safe.
        suppressed = {"kept": [], "dropped": []}
    else:
        # The authoritative interest status lives on the LEAD, not on the
        # auto-reply row, which carries none for 8 of the 29 addresses harvested
        # live. Unverifiable means dropped.
        resolved = {"statuses": None, "unresolved": [], "error": None}
        if resolve_statuses and harvest["addresses"]:
            resolved = resolve_interest_statuses(client, harvest["addresses"])
            if resolved["error"]:
                notes.append("lead interest-status lookup partly failed (%s); every address it could "
                             "not verify was dropped" % resolved["error"])
                read_failures.append("interest-status lookup: %s" % str(resolved["error"])[:160])
        suppressed = suppress(harvest["addresses"], blocklist,
                              statuses=resolved["statuses"], unresolved=resolved["unresolved"])
    if suppressed["dropped"]:
        notes.append("%d harvested address(es) suppressed: %s" % (
            len(suppressed["dropped"]),
            ", ".join(sorted(set(d["dropped_because"] for d in suppressed["dropped"])))))
    if harvest["dead"]:
        notes.append("%d address(es) skipped as dead (%s)" % (
            len(harvest["dead"]), ", ".join(DEAD_ADDRESS_PATTERNS)))

    accounts = load_accounts(client)
    campaign_lists = load_campaign_email_lists(client, campaigns)
    inboxes = build_inbox_index(accounts, campaign_lists, now)
    index = {i["email"]: i for i in inboxes}

    previous = _read_sidecar(changeset_dir, SIDECAR)
    if sent is None and previous and previous.get("sent_at"):
        # Attribution for a round that really went out: which inbox mailed which
        # address. Only fetched when there is a sent round to attribute, so an
        # ordinary shadow run still makes exactly one GET /emails walk.
        if hasattr(client, "_request"):   # a real transport, not a test stub
            _pace_emails_endpoint()
        sent = _walk_emails(client, "sent")
    scored = score_round(previous, received, now, index, sent=sent)
    if not scored["scored"] and scored.get("reason"):
        notes.append(scored["reason"])

    # **A sent round that has not been scored yet is not replaced.** The sidecar
    # is the only record of which inbox mailed which mailbox, and the live
    # procedure has Lorenzo write ``sent_at`` into it by hand. A scheduler retry
    # or a second ``--now`` inside the response window used to overwrite both,
    # so a round whose 120 emails had already reached real prospects could never
    # be scored and the next round mailed them again.
    pending = _pending_round(previous, now)
    if pending and not harvest_only:
        plan = dict(previous.get("plan") or {})
        plan["note"] = pending
        notes.append(pending)
    else:
        plan = {"round_id": None, "assignments": [], "note": "harvest only"} if harvest_only else \
            build_plan(inboxes, suppressed["kept"], now, per_inbox=per_inbox)
    if plan.get("refused") and plan.get("note"):
        notes.append(plan["note"])
    manual_sends = [] if pending else _stage_manual_sends(plan)

    proposals = []
    for row in scored.get("failing") or []:
        meta = index.get(row["email"]) or {}
        proposals.append({
            "id": "pause_inbox:%s" % row["email"], "kind": "pause_inbox", "target": row["email"],
            "severity": "high", "level": 4, "reason": row["reason"],
            "in_campaigns": meta.get("in_campaigns") or [],
            # The COMPLETE pause action list, not a bare pause_account. Three
            # jobs write one change-set file: a pause-only list used to replace
            # the monitor's version of the same proposal id, and applying the
            # merged row paused the inbox while leaving it in every campaign's
            # email_list, which is the silent capacity drop the monitor exists
            # to prevent.
            "actions": _pause_actions(row["email"], meta, campaign_lists, None),
            "evidence": row,
        })

    if scored["scored"]:
        summary = "round %s: %d ok, %d warn, %d kill of %d inboxes" % (
            scored["round_id"],
            sum(1 for r in scored["rows"] if r["verdict"] == "ok"),
            sum(1 for r in scored["rows"] if r["verdict"] == "warn"),
            len(scored["failing"]), len(scored["rows"]))
    else:
        summary = "not scored (%s); %d address(es) harvested, %d planned" % (
            scored.get("reason", "no reason"), len(harvest["addresses"]),
            len(plan.get("assignments") or []))

    report = {"job": JOB, "as_of": now.isoformat(), "mode": settings.get_mode(), "dry_run": bool(dry_run),
              "harvest": harvest, "suppressed": suppressed, "plan": plan, "manual_sends": manual_sends,
              "scored": scored, "proposals": proposals, "notes": notes, "summary": summary,
              "pending": bool(pending),
              "failing": scored.get("failing") or []}
    report["card"] = render_card(report, now)

    if write is None:
        write = not dry_run
    report["changeset_path"] = None
    report["sidecar_path"] = None
    if write:
        if proposals:
            path = write_changeset(
                {"_about": "Level 4 canary proposals (M1 L4 / O7). Nothing applied.",
                 "generated_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
                 "generated_by": JOB, "mode": settings.get_mode(), "levels_run": [4],
                 "levels_evaluated": [4] if scored.get("scored") else [],
                 "proposals": proposals}, now, changeset_dir)
            report["changeset_path"] = str(path) if path else None
        if pending:
            # Leave the sent round exactly where it is. Nothing in this run
            # learned anything the sidecar does not already hold.
            report["sidecar_path"] = str(Path(changeset_dir) / SIDECAR)
            report["sidecar_preserved"] = True
        else:
            sidecar = {"job": JOB, "as_of": now.isoformat(), "summary": summary,
                       "plan": plan, "sent_at": None,
                       "sent_at_note": ("set this to the ISO timestamp of the live canary send "
                                        "(runbooks/deliverability.md level 4, step 6). Until it is set "
                                        "the next run reports the round as unsent and proposes "
                                        "nothing."),
                       "failing": scored.get("failing") or [], "rows": scored.get("rows") or [],
                       "harvested": len(harvest["addresses"]), "notes": notes}
            sc = write_sidecar(changeset_dir, SIDECAR, sidecar)
            report["sidecar_path"] = str(sc) if sc else None
            # Every round is also archived under its own name, so a round that
            # is rolled forward is still recoverable.
            if previous and previous.get("sent_at") and (previous.get("plan") or {}).get("round_id"):
                write_sidecar(changeset_dir,
                              "last_canary_%s.json" % previous["plan"]["round_id"], previous)

    status = "dry_run" if dry_run else "ok"
    if read_failures:
        status += "_partial"
    elif scored.get("failing"):
        status += "_failing"
    elif not scored["scored"]:
        status += "_unscored"
    report["status"] = status
    report["read_failures"] = read_failures
    log_fn(JOB, status, {"as_of": now.isoformat(), "harvested": len(harvest["addresses"]),
                         "read_failures": read_failures,
                         "suppressed": len(suppressed["dropped"]), "planned": len(plan.get("assignments") or []),
                         # Planned sends are staged for a human, never attempted here.
                         "manual_sends": len(manual_sends), "sent": 0,
                         "scored": scored["scored"], "failing": len(scored.get("failing") or []),
                         "notes": notes, "changeset": report["changeset_path"]})

    if send_card is None:
        send_card = not dry_run
    report["notified"] = None
    if send_card:
        report["notified"] = notify_fn(
            "Auto-responder canary: %s%s" % ("PARTIAL, " if read_failures else "", summary), report["card"],
            priority="high" if (scored.get("failing") or read_failures) else "default",
            tags=["bird"])
    return report


def render_card(report: Dict[str, Any], now: datetime) -> str:
    h = report["harvest"]
    plan = report["plan"]
    lines = ["Auto-responder canary %s" % now.astimezone(TZ).strftime("%a %Y-%m-%d %H:%M CT"),
             "=" * 42,
             "harvested %d auto-responder address(es) from %d received messages; %d usable after suppression"
             % (len(h["addresses"]), h["scanned"], len(report["suppressed"]["kept"])),
             report["summary"], ""]
    scored = report["scored"]
    if scored["scored"]:
        for row in scored["rows"]:
            lines.append("  %-38s %3d/%-3d %6.0f%%  %s" % (
                row["email"], row["responses"], row["sent"], row["response_pct"], row["verdict"]))
    if plan.get("assignments"):
        total = sum(len(a["targets"]) for a in plan["assignments"])
        distinct = len(set(t for a in plan["assignments"] for t in a["targets"]))
        lines.append("")
        lines.append("%s round %s: %d inbox(es) x %d address(es) = %d sends to %d distinct "
                     "mailbox(es), at most %d email(s) each" % (
                         "Pending" if report.get("pending") else "Planned",
                         plan.get("round_id"), len(plan["assignments"]), plan.get("per_inbox", 0),
                         total, distinct,
                         max(Counter(t for a in plan["assignments"] for t in a["targets"]).values())
                         if total else 0))
        if plan.get("note"):
            lines.append("  %s" % plan["note"])
        if not report.get("pending"):
            lines.append("  Staged as %s. No email was sent, and this job has no code path "
                         "that can send one. Live procedure: runbooks/deliverability.md "
                         "level 4, one campaign per inbox." % MANUAL_SEND_STATUS)
    elif plan.get("refused"):
        lines.append("")
        lines.append("No round planned: %s" % plan.get("note", "refused"))
    for note in report.get("notes") or []:
        lines.append("note: %s" % note)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="autoresponder_canary",
                                description="Saturday auto-responder canary (M1 L4 / O7)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="read-only: harvest, plan, score, print")
    g.add_argument("--now", action="store_true", help="same + change-set, sidecar and the ntfy card")
    p.add_argument("--as-of", help="ISO timestamp used as 'now'")
    p.add_argument("--harvest-only", action="store_true", help="harvest and score, never plan a round")
    p.add_argument("--per-inbox", type=int, help="addresses per inbox (default %d)" % TH.CANARY_ADDRESSES_PER_INBOX)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        from shared.job_log import use_scratch_logs

        use_scratch_logs("autoresponder_canary_dryrun")

    now = _parse_ts(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if now is None:
        raise SystemExit("--as-of must be an ISO timestamp")
    # A Saturday cron that dies must leave a Job_Log row and a push. Without
    # this the run propagated, wrote nothing and notified nobody, and a canary
    # that stopped running looked exactly like a canary with nothing to report.
    try:
        report = run_canary(now, dry_run=bool(args.dry_run), harvest_only=args.harvest_only,
                            per_inbox=args.per_inbox)
    except Exception as exc:  # noqa: BLE001
        logger.exception("auto-responder canary failed")
        log_run(JOB, "failed", {"as_of": now.isoformat(), "dry_run": bool(args.dry_run),
                                "error": str(exc)[:400]})
        notify("Auto-responder canary FAILED",
               "%s\n\nLevel 4 did not run, so no canary round was planned or scored.\n"
               "Re-run:\n  python3 jobs/autoresponder_canary.py --dry-run" % str(exc)[:400],
               priority="high", tags=["rotating_light"])
        return 1
    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        print(report["card"])
    # Partial (a read failed) exits non-zero, the same contract as the monitor
    # and the capacity inventory.
    return 1 if report.get("read_failures") else 0


if __name__ == "__main__":
    sys.exit(main())
