#!/usr/bin/env python3
"""Inbox inventory, health alerts and insurance promotion (Blueprint M2 / brief A5).

    cd "Agentic Worklfows"
    python3 jobs/inbox_inventory.py --dry-run                  # live GETs, prints, writes nothing
    python3 jobs/inbox_inventory.py --now                      # + refreshes config/inbox_inventory.json
    python3 jobs/inbox_inventory.py --dry-run --fixtures       # offline, recorded snapshots
    python3 jobs/inbox_inventory.py --dry-run --as-of 2026-10-11T07:00:00-05:00
    python3 jobs/inbox_inventory.py --promote cleaning_reactivation:lorenzo@theadvero.com

Reads only. Every Instantly call this job makes is a GET or a POST-shaped read
(``accounts``, ``campaigns``, ``accounts/analytics/daily``): it never pauses an
inbox, never PATCHes a campaign and never orders a domain. The one thing it
produces that could change a live system is a *change-set* under
``changesets/capacity/``, applied later by hand with
``changesets/capacity/apply_promotion.py`` after Lorenzo approves the diff.

Health alerts only (Lorenzo, 2026-09-22)
----------------------------------------
How many sending inboxes to hold, and when to buy more, is Lorenzo's decision,
not this job's. It reports inbox and domain HEALTH: warm-up score, warm-up off,
bounce and reply lines, missing analytics, inboxes that are not status 1
(paused, disconnected or erroring), and whether anything is sending at all. It
does not count a reserve, size a reserve target, forecast capacity for a
go-live date or recommend buying or ordering anything.

What it derives
---------------
* one row per Instantly account: domain, persona, age in days, warm-up health,
  daily limit, 7-day real reply rate, 7-day bounce rate, the Section 6 flags,
  and a role of ``active`` / ``warming`` / ``idle`` / ``retired``. The
  role is kept per inbox because ``promote_insurance`` picks from it; it is
  never totalled into a reserve count;
* what the estate sends today (active inboxes and the campaign daily limits),
  with an alert when nothing is sending at all;
* the ramp plan as data: a daily-limit schedule per inbox from today to the
  plan horizon, with warm-up on at every step, forever;
* ``promote_insurance()``: the healthiest insurance inbox to swap in for a
  failing one, never more than 3 inboxes from one domain in one campaign, and
  never an inbox whose health is unmeasured or that was quarantined earlier.

Reply-rate arithmetic (verified against live data 2026-09-22)
-------------------------------------------------------------
``replies_automatic`` from ``GET /accounts/analytics/daily`` is a SEPARATE
counter, not a subset of ``replies``. On 2026-09-19 the twelve active inboxes
recorded ``replies=0`` and ``replies_automatic=7``. Subtracting one from the
other (the obvious reading of "exclude auto-replies", Blueprint M1 level 3)
gives every inbox a negative reply count and would retire the whole estate on
the first Friday audit. The real reply rate is ``unique_replies / sent`` as it
stands; ``replies_automatic`` is the auto-responder canary (M1 level 4).

Two facts this module refuses to forget
---------------------------------------
1. **An inbox belongs to many campaigns.** All twelve live inboxes sit in all
   six campaign ``email_list``s (measured 2026-09-22). Pulling one out of a
   single campaign therefore does NOT stop it sending, and the capacity delta
   of that PATCH is 0/day, not -25/day. ``promote_insurance`` reports the
   campaigns the failing inbox is still in.
2. **Missing data is not good data.** A dropped analytics chunk makes an inbox
   look flawless (no bounce rate, no reply rate, no flags). Rows whose window
   could not be read are marked ``analytics_missing``, are never eligible for
   promotion, block the overwrite of the deliverable and downgrade the run to
   ``partial`` with a non-zero exit code.
"""
import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import analytics  # noqa: E402
from shared import settings  # noqa: E402
from shared import thresholds as TH  # noqa: E402
from shared.job_log import log_run, use_scratch_logs  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.settings import TZ, get_mode  # noqa: E402

logger = logging.getLogger("jobs.inbox_inventory")

JOB = "inbox_inventory"

INVENTORY_PATH = os.path.join(ROOT, "config", "inbox_inventory.json")
CHANGESET_DIR = os.path.join(ROOT, "changesets", "capacity")
SNAPSHOT_DIR = os.path.join(CHANGESET_DIR, "snapshots")
REPLAY_INVENTORY_PATH = os.path.join(SNAPSHOT_DIR, "replay_inventory.json")

# --------------------------------------------------------------- the rules
# Blueprint M2 + Section 6. Every number a plan depends on lives here.
# Six of these are BOUND to shared/thresholds.py rather than written again.
# They were literals here and literals there, and the units had already drifted:
# this module carried RAMP_MIN_REPLY_RATE = 0.02 (a fraction) while thresholds
# carried REPLY_RATE_FOR_RAISED_LIMIT_PCT = 2.0 (a percentage), so the same rule
# was two numbers in two units in two files. The names stay because the rest of
# this module and its tests read them; only the source of truth moved.
#
# The reserve rule (insurance >= 50% of active), the go-live target, the
# planned active count and the order-to-live setup day are NOT here any more:
# on 2026-09-22 Lorenzo cut this job to health alerts only, and buying inboxes
# stays his decision. Nothing in this module sizes a reserve or an order.
WARMUP_DAYS = TH.WARMUP_DAYS_BEFORE_PROMOTION      # 21: no cold sends before this
MAX_INBOXES_PER_DOMAIN = TH.MAX_INBOXES_PER_DOMAIN  # "never more than 3 inboxes per domain"
PER_INBOX_DAILY_LIMIT = TH.PER_INBOX_DAILY_LIMIT    # today's per-inbox cold limit
RAMPED_DAILY_LIMIT = TH.PER_INBOX_DAILY_LIMIT_RAISED  # only for inboxes clearing the rate below
RAMP_MIN_REPLY_RATE = TH.REPLY_RATE_FOR_RAISED_LIMIT_PCT / 100.0  # >= 2% real replies earns 30/day
RAMP_PLAN_END = date(2026, 11, 1)
RAMP_DATE = date(2026, 11, 1)
ANALYTICS_WINDOW_DAYS = TH.REPLY_RATE_WINDOWS_DAYS[0]  # 7: Section 6 "100 sent in 7 d" reply-rate window
ANALYTICS_CHUNK = 15          # this workspace answers HTTP 413 on large analytics pulls
ANALYTICS_RETRY_DEPTH = 2     # a failed chunk is retried at half size, twice, before it is lost

# Section 6 thresholds (alert values, not green values), BOUND to
# shared/thresholds.py like the M2 numbers above. They were literals here (98,
# 0.02, 0.01, 100, 7) and they drive the flags and whether an insurance inbox
# may be promoted, so a change in thresholds.py used to leave this card on the
# old line (MKT-5). The local names stay because this module and its tests
# read them; fractions here, percentages there.
WARMUP_HEALTH_FLOOR = TH.WARMUP_HEALTH_MIN_PCT                  # < 98 -> pause
BOUNCE_ALERT = TH.BOUNCE_RATE_MAX_PCT / 100.0                   # > 2% -> remove from the campaign
REPLY_RATE_ALERT = TH.REPLY_RATE_MIN_PCT / 100.0                # < 1% real replies -> remove ...
REPLY_RATE_MIN_SENT = TH.REPLY_RATE_MIN_SENT                    # ... once the inbox has sent 100
WARMUP_SCORE_MATURE_DAYS = TH.WARMUP_MIN_AGE_DAYS_BEFORE_VERDICT  # a 2-day-old score means nothing yet

ROLE_ACTIVE = "active"
ROLE_WARMING = "warming"
ROLE_RETIRED = "retired"
# Warm-up finished and not in any SENDING campaign. The label reads "idle" so a
# row never looks like missing data; the constant keeps its old name because
# promote_insurance picks its candidates from exactly these inboxes.
ROLE_IDLE = "idle"
ROLE_INSURANCE = ROLE_IDLE

# The roles that are totalled in counts, per domain, in the report and the
# push. ``idle`` is left out on purpose: its total is a reserve count, and the
# reserve is Lorenzo's call (2026-09-22). The report says "the rest idle"
# instead, and a domain row says "idle" without a number.
COUNTED_ROLES = (ROLE_ACTIVE, ROLE_WARMING, ROLE_RETIRED)

# Instantly account status: 1 is active, 2 is paused, and a NEGATIVE status is
# an error (connection error, soft bounce error, sending error). A negative
# status is a health alert wherever the inbox sits.
ACCOUNT_STATUS_ACTIVE = 1

# Flags that are context, not an alert. render(), the digest and the Job_Log
# all count actionable flags only, and they all count the same ones.
INFORMATIONAL_FLAGS = ("warmup_score_immature", "in_paused_campaign")

# Inboxes a change-set pulled out of a campaign for health reasons. They stop
# being promotion candidates until Lorenzo clears them by hand, because an
# inbox that has not sent for a week has an empty analytics window and would
# otherwise come back looking like the healthiest spare in the estate.
QUARANTINE_KEY = "capacity.quarantine"


# ------------------------------------------------------------------ helpers
def parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Instantly timestamps: '2026-09-20T19:08:52.230Z'. Returns aware UTC."""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Python 3.9's fromisoformat wants exactly 3 or 6 fractional digits.
    if "." in text:
        head, _, tail = text.partition(".")
        digits = ""
        rest = ""
        for i, ch in enumerate(tail):
            if ch.isdigit():
                digits += ch
            else:
                rest = tail[i:]
                break
        if digits:
            digits = (digits + "000000")[:6] if len(digits) > 3 else (digits + "000")[:3]
            text = "%s.%s%s" % (head, digits, rest)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        logger.warning("unparseable timestamp %r", value)
        return None


def to_date(value: Optional[datetime]) -> Optional[date]:
    return value.date() if value is not None else None


def domain_of(email: str) -> str:
    return email.split("@", 1)[1].lower() if "@" in email else ""


def persona_of(email: str) -> str:
    return email.split("@", 1)[0].lower() if "@" in email else email.lower()


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.2f%%" % (100.0 * value)


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def daily_limit_of(row: Dict[str, Any], when_unset: int) -> int:
    """The inbox's daily limit, honouring an explicit 0.

    ``row.get("daily_limit") or 25`` reads a deliberate 0 (Lorenzo's way of
    holding an inbox back without pausing it) as 25 and overstates the plan by
    25/day per held-back inbox. Only a missing field falls back.
    """
    value = row.get("daily_limit")
    if value is None:
        return int(when_unset)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(when_unset)


def actionable_flags(row: Dict[str, Any]) -> List[str]:
    return [f for f in (row.get("flags") or []) if f not in INFORMATIONAL_FLAGS]


# -------------------------------------------------------------- aggregation
def aggregate_daily(rows: Optional[List[Dict[str, Any]]]) -> Dict[str, Dict[str, int]]:
    """Sum ``GET /accounts/analytics/daily`` rows per inbox.

    ``replies_automatic`` is kept as its own counter and never subtracted from
    ``replies``: the two are independent in this API (see the module docstring).
    """
    out = {}  # type: Dict[str, Dict[str, int]]
    for row in rows or []:
        email = (row.get("email_account") or "").lower()
        if not email:
            continue
        bucket = out.setdefault(email, {
            "sent": 0, "bounced": 0, "contacted": 0,
            "replies": 0, "unique_replies": 0,
            "replies_automatic": 0, "unique_replies_automatic": 0,
            "days": 0,
        })
        for key in ("sent", "bounced", "contacted", "replies", "unique_replies",
                    "replies_automatic", "unique_replies_automatic"):
            bucket[key] += int(row.get(key) or 0)
        bucket["days"] += 1
    return out


def campaign_is_active(campaign: Dict[str, Any]) -> bool:
    """Instantly campaign status: 1 sending, 0 draft, 2 paused.

    A missing status is treated as active on purpose: the conservative reading
    of an unknown campaign is that it sends. Only an explicit non-1 counts as
    inactive, and the same helper decides membership AND the campaign daily
    limit sum, so a staged draft campaign can never inflate active capacity in
    one place while being skipped in the other.
    """
    status = campaign.get("status")
    if status is None:
        return True
    try:
        return int(status) == 1
    except (TypeError, ValueError):
        return True


def campaign_membership(campaigns: Optional[List[Dict[str, Any]]]) -> Dict[str, Dict[str, List[str]]]:
    """{inbox email: {"active": [campaign id, ...], "inactive": [...]}}.

    Split by campaign status. Pre-assigning the new insurance inboxes to a
    draft campaign is the natural way to stage a scale-up; counting that as
    active capacity moves several hundred sends a day of imaginary capacity
    into the report and empties the insurance pool at the same time.
    """
    out = {}  # type: Dict[str, Dict[str, List[str]]]
    for campaign in campaigns or []:
        cid = campaign.get("id")
        bucket_key = "active" if campaign_is_active(campaign) else "inactive"
        for email in campaign.get("email_list") or []:
            entry = out.setdefault((email or "").lower(), {"active": [], "inactive": []})
            entry[bucket_key].append(cid)
    return out


def classify_role(account: Dict[str, Any], in_campaign: bool, age_days: Optional[int]) -> str:
    """active | warming | idle | retired.

    ``in_campaign`` means "in the email_list of a campaign that is SENDING".
    Order matters: a paused or half-built account is retired whatever else is
    true of it, because promoting one into a campaign is how a dead inbox ends
    up sending.
    """
    if int(account.get("status") or 0) != ACCOUNT_STATUS_ACTIVE or account.get("setup_pending"):
        return ROLE_RETIRED
    if in_campaign:
        return ROLE_ACTIVE
    if age_days is not None and age_days >= WARMUP_DAYS:
        return ROLE_INSURANCE
    return ROLE_WARMING


def planned_daily_limit(row: Dict[str, Any], today: date,
                        ramp_date: date = RAMP_DATE) -> int:
    """The limit the ramp plan prescribes for this inbox on ``today``.

    The flag table compares against this rather than the bare constant 25: from
    the ramp date onward an inbox clearing 2% real replies is SUPPOSED to be at
    30/day, and flagging that as ``daily_limit_off_plan`` trains Lorenzo to
    ignore the one table that carries Section 6 alerts.
    """
    if row.get("role") == ROLE_RETIRED:
        return 0
    ready_raw = row.get("warmup_ready_date")
    if ready_raw:
        try:
            if date.fromisoformat(ready_raw) > today:
                return 0
        except ValueError:
            pass
    if today < ramp_date:
        return PER_INBOX_DAILY_LIMIT
    rate = row.get("reply_rate_7d")
    if rate is not None and rate >= RAMP_MIN_REPLY_RATE:
        return RAMPED_DAILY_LIMIT
    return PER_INBOX_DAILY_LIMIT


def _flags(row: Dict[str, Any]) -> List[str]:
    flags = []  # type: List[str]
    # Disconnected or erroring. Both are actionable, so they reach the flag
    # table, the per-domain health lines, the push title and the attention
    # status. A retired inbox that no campaign lists is left alone: pausing an
    # inbox on purpose is not an alert.
    if int(row.get("status") or 0) < 0:
        flags.append("account_status_error")
    if row.get("role") == ROLE_RETIRED and row.get("campaign_ids"):
        flags.append("retired_in_sending_campaign")
    health = row.get("warmup_health")
    if health is not None and health < WARMUP_HEALTH_FLOOR:
        flags.append("warmup_below_%d" % WARMUP_HEALTH_FLOOR)
    if not row.get("warmup_enabled"):
        flags.append("warmup_off")
    if row.get("analytics_missing"):
        flags.append("analytics_missing")
    bounce = row.get("bounce_rate_7d")
    if bounce is not None and bounce > BOUNCE_ALERT:
        flags.append("bounce_above_2pct")
    reply = row.get("reply_rate_7d")
    if (reply is not None and reply < REPLY_RATE_ALERT
            and (row.get("sent_7d") or 0) >= REPLY_RATE_MIN_SENT):
        flags.append("reply_rate_below_1pct")
    if row.get("role") == ROLE_ACTIVE:
        planned = row.get("planned_daily_limit")
        if planned is not None and daily_limit_of(row, planned) != planned:
            flags.append("daily_limit_off_plan")
    if row.get("role") != ROLE_RETIRED and row.get("daily_limit") == 0:
        flags.append("daily_limit_zero")
    if row.get("inactive_campaign_ids"):
        flags.append("in_paused_campaign")
    age = row.get("age_days")
    if age is not None and age < WARMUP_SCORE_MATURE_DAYS:
        flags.append("warmup_score_immature")
    return flags


def _campaign_keys(ids: List[str]) -> List[str]:
    return sorted(settings.CAMPAIGN_BY_ID[c]["key"] for c in ids if c in settings.CAMPAIGN_BY_ID)


def build_inbox_row(account: Dict[str, Any], membership: Dict[str, Dict[str, List[str]]],
                    analytics: Dict[str, Dict[str, int]], now: datetime,
                    missing_analytics: Optional[Any] = None) -> Dict[str, Any]:
    email = (account.get("email") or "").lower()
    created = parse_ts(account.get("timestamp_created"))
    warm_start = parse_ts(account.get("timestamp_warmup_start")) or created
    age_days = None
    ready_date = None
    if warm_start is not None:
        age_days = (now.date() - warm_start.date()).days
        ready_date = warm_start.date() + timedelta(days=WARMUP_DAYS)
    entry = membership.get(email) or {}
    campaigns = list(entry.get("active") or [])
    inactive = list(entry.get("inactive") or [])
    stats = analytics.get(email, {})
    sent = int(stats.get("sent") or 0)
    row = {
        "email": email,
        "domain": domain_of(email),
        "persona": persona_of(email),
        "role": classify_role(account, bool(campaigns), age_days),
        "age_days": age_days,
        "created": _iso(to_date(created)),
        "warmup_started": _iso(to_date(warm_start)),
        "warmup_ready_date": _iso(ready_date),
        "warmup_health": account.get("stat_warmup_score"),
        "warmup_enabled": int(account.get("warmup_status") or 0) == 1,
        "warmup_limit": (account.get("warmup") or {}).get("limit"),
        "daily_limit": account.get("daily_limit"),
        "sending_gap_minutes": account.get("sending_gap"),
        "provider_code": account.get("provider_code"),
        "tracking_domain": account.get("tracking_domain_name"),
        "tracking_domain_status": account.get("tracking_domain_status"),
        "status": int(account.get("status") or 0),
        "setup_pending": bool(account.get("setup_pending")),
        "campaign_ids": campaigns,
        "campaign_keys": _campaign_keys(campaigns),
        "inactive_campaign_ids": inactive,
        "inactive_campaign_keys": _campaign_keys(inactive),
        "sent_7d": sent,
        "bounced_7d": int(stats.get("bounced") or 0),
        "replies_7d": int(stats.get("replies") or 0),
        "unique_replies_7d": int(stats.get("unique_replies") or 0),
        "replies_automatic_7d": int(stats.get("replies_automatic") or 0),
        "analytics_days": int(stats.get("days") or 0),
        "analytics_missing": bool(missing_analytics and email in missing_analytics),
    }
    row["reply_rate_7d"] = _rate(row["unique_replies_7d"], sent)
    row["bounce_rate_7d"] = _rate(row["bounced_7d"], sent)
    row["planned_daily_limit"] = planned_daily_limit(row, now.date())
    row["flags"] = _flags(row)
    return row


def summarise_domains(inboxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_domain = {}  # type: Dict[str, Dict[str, Any]]
    for row in inboxes:
        bucket = by_domain.setdefault(row["domain"], {
            "domain": row["domain"], "inboxes": 0, "roles": {}, "capacity_per_day": 0,
            "sent_7d": 0, "bounced_7d": 0, "unique_replies_7d": 0,
            "warmup_health_min": None, "oldest_warmup_start": None, "flags": [],
            "unhealthy_inboxes": 0, "has_idle_inboxes": False,
        })
        bucket["inboxes"] += 1
        if row["role"] in COUNTED_ROLES:
            bucket["roles"][row["role"]] = bucket["roles"].get(row["role"], 0) + 1
        elif row["role"] == ROLE_IDLE:
            bucket["has_idle_inboxes"] = True
        if actionable_flags(row):
            bucket["unhealthy_inboxes"] += 1
        if row["role"] == ROLE_ACTIVE:
            bucket["capacity_per_day"] += daily_limit_of(row, 0)
        bucket["sent_7d"] += row["sent_7d"]
        bucket["bounced_7d"] += row["bounced_7d"]
        bucket["unique_replies_7d"] += row["unique_replies_7d"]
        health = row.get("warmup_health")
        if health is not None:
            current = bucket["warmup_health_min"]
            bucket["warmup_health_min"] = health if current is None else min(current, health)
        start = row.get("warmup_started")
        if start and (bucket["oldest_warmup_start"] is None or start < bucket["oldest_warmup_start"]):
            bucket["oldest_warmup_start"] = start
        for flag in row["flags"]:
            if flag not in bucket["flags"]:
                bucket["flags"].append(flag)
    out = []
    for domain in sorted(by_domain):
        bucket = by_domain[domain]
        bucket["reply_rate_7d"] = _rate(bucket["unique_replies_7d"], bucket["sent_7d"])
        bucket["bounce_rate_7d"] = _rate(bucket["bounced_7d"], bucket["sent_7d"])
        bucket["over_inbox_cap"] = bucket["inboxes"] > MAX_INBOXES_PER_DOMAIN
        out.append(bucket)
    return out


# ------------------------------------------------------------------ capacity
def campaign_limits(campaigns: Optional[List[Dict[str, Any]]], active_capacity: int) -> Dict[str, Any]:
    """What the estate can send TODAY, from the campaign side.

    Inbox capacity is ``inboxes x daily_limit``; what actually goes out is
    capped a second time by the sum of the campaigns' own ``daily_limit``
    fields. This is a measurement of today, not a plan: there is no target
    and no increase to make. ``promote_insurance`` quotes the total in its
    capacity note so a swap is read against the real ceiling.
    """
    rows = []
    total = 0
    for campaign in campaigns or []:
        if not campaign_is_active(campaign):
            continue
        limit = int(campaign.get("daily_limit") or 0)
        total += limit
        cid = campaign.get("id")
        rows.append({
            "key": (settings.CAMPAIGN_BY_ID.get(cid) or {}).get("key"),
            "id": cid,
            "name": campaign.get("name"),
            "daily_limit": limit,
            "inboxes_in_email_list": len(campaign.get("email_list") or []),
        })
    rows.sort(key=lambda r: (r.get("name") or ""))
    if not rows:
        binding = "unknown"
    elif total < active_capacity:
        binding = "campaign_daily_limit"
    elif total > active_capacity:
        binding = "inbox_capacity"
    else:
        binding = "balanced"
    return {
        "active_campaigns": len(rows),
        "total_campaign_daily_limit": total,
        "inbox_capacity_per_day": active_capacity,
        "binding_constraint": binding,
        "campaigns": rows,
    }


def capacity_today(inboxes: List[Dict[str, Any]], now: datetime,
                   campaigns: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """What is sending today, and the two alerts that say nothing is.

    Health alerts only (Lorenzo, 2026-09-22): no reserve count, no reserve
    target, no target-date forecast and no order size. An estate whose
    accounts pull came back empty, or where no inbox sits in a sending
    campaign, is still an alert, because that is the sending estate failing,
    not a buying decision.
    """
    active = [r for r in inboxes if r["role"] == ROLE_ACTIVE]
    active_capacity = sum(daily_limit_of(r, 0) for r in active)
    alerts = []  # type: List[str]
    if not inboxes:
        alerts.append("no_inboxes")
    elif active_capacity <= 0:
        alerts.append("no_active_capacity")
    return {
        "as_of": now.date().isoformat(),
        "alerts": alerts,
        "today": {
            "active_inboxes": len(active),
            "active_capacity_per_day": active_capacity,
            "warming_inboxes": len([r for r in inboxes if r["role"] == ROLE_WARMING]),
            "retired_inboxes": len([r for r in inboxes if r["role"] == ROLE_RETIRED]),
        },
        "campaign_limits": campaign_limits(campaigns, active_capacity),
    }


# ----------------------------------------------------------------- ramp plan
def ramp_segments(row: Dict[str, Any], now: datetime,
                  end: date = RAMP_PLAN_END, ramp_date: date = RAMP_DATE) -> List[Dict[str, Any]]:
    """The daily-limit schedule for one inbox, today -> the plan horizon.

    Warm-up is ``on`` in every segment of every inbox, forever (Blueprint M2).

    The horizon is ``max(end, today, the day this inbox starts sending)``, not
    the bare constant: ``ramp_plan.per_inbox`` is a data contract, and a
    segment whose ``from`` is after its ``to`` is a negative-length window for
    anything that reads it (a chart, a diff against live daily limits, the
    deliverability job). A fixed end date inverts every segment on any run
    after it, and inverts the closing segment of any inbox whose warm-up
    finishes after it.
    """
    today = now.date()
    ready_raw = row.get("warmup_ready_date")
    ready = date.fromisoformat(ready_raw) if ready_raw else None
    segments = []  # type: List[Dict[str, Any]]

    if row["role"] == ROLE_RETIRED:
        horizon = max(end, today)
        return [{
            "from": today.isoformat(), "to": horizon.isoformat(), "open_ended": True,
            "daily_limit": 0, "warmup": "on",
            "reason": "retired (status=%s, setup_pending=%s): no cold sends, warm-up stays on"
                      % (row.get("status"), row.get("setup_pending")),
        }]

    sending_from = today
    if ready is not None and ready > today:
        segments.append({
            "from": today.isoformat(),
            "to": (ready - timedelta(days=1)).isoformat(),
            "open_ended": False,
            "daily_limit": 0,
            "warmup": "on",
            "reason": "warming: %d of %d days done, cold sends start %s"
                      % (row.get("age_days") or 0, WARMUP_DAYS, ready.isoformat()),
        })
        sending_from = ready

    reply_rate = row.get("reply_rate_7d")
    eligible = reply_rate is not None and reply_rate >= RAMP_MIN_REPLY_RATE
    if sending_from < ramp_date:
        segments.append({
            "from": sending_from.isoformat(),
            "to": (ramp_date - timedelta(days=1)).isoformat(),
            "open_ended": False,
            "daily_limit": PER_INBOX_DAILY_LIMIT,
            "warmup": "on",
            "reason": "standard cold limit",
        })
    limit_after = RAMPED_DAILY_LIMIT if eligible else PER_INBOX_DAILY_LIMIT
    if eligible:
        reason = ("7-day real reply rate %s >= %s on %s, so %d/day"
                  % (_pct(reply_rate), _pct(RAMP_MIN_REPLY_RATE), today.isoformat(), RAMPED_DAILY_LIMIT))
    elif reply_rate is None:
        reason = ("no reply history yet, so it stays at %d/day; re-check on %s"
                  % (PER_INBOX_DAILY_LIMIT, ramp_date.isoformat()))
    else:
        reason = ("7-day real reply rate %s is under %s, so it stays at %d/day; re-check on %s"
                  % (_pct(reply_rate), _pct(RAMP_MIN_REPLY_RATE), PER_INBOX_DAILY_LIMIT,
                     ramp_date.isoformat()))
    # The last segment has no end date: it is the standing limit from the ramp
    # date onward, not a one-day window because the plan horizon happens to sit
    # on the ramp date.
    closing_from = max(sending_from, ramp_date)
    horizon = max(end, today, closing_from)
    segments.append({
        "from": closing_from.isoformat(),
        "to": horizon.isoformat(),
        "open_ended": True,
        "daily_limit": limit_after,
        "warmup": "on",
        "reason": reason,
    })
    return segments


def ramp_plan(inboxes: List[Dict[str, Any]], now: datetime,
              end: date = RAMP_PLAN_END) -> Dict[str, Any]:
    plan = {}  # type: Dict[str, Any]
    eligible = []  # type: List[str]
    horizon = end
    for row in inboxes:
        segments = ramp_segments(row, now, end=end)
        plan[row["email"]] = segments
        last = date.fromisoformat(segments[-1]["to"])
        if last > horizon:
            horizon = last
        rate = row.get("reply_rate_7d")
        if rate is not None and rate >= RAMP_MIN_REPLY_RATE:
            eligible.append(row["email"])
    return {
        "_rule": ("25/day now. 30/day from %s only for an inbox whose 7-day real reply rate is "
                  "at least %s, recomputed from that week's data on the day. Warm-up stays on "
                  "forever, on every inbox, including retired ones."
                  % (RAMP_DATE.isoformat(), _pct(RAMP_MIN_REPLY_RATE))),
        "decision_date": RAMP_DATE.isoformat(),
        "plan_end": end.isoformat(),
        "plan_horizon": horizon.isoformat(),
        "eligible_for_30_on_todays_data": sorted(eligible),
        "per_inbox": plan,
    }


# ---------------------------------------------------------------- quarantine
def _store():
    from shared.store import get_store
    return get_store()


def load_quarantine(store=None) -> Dict[str, Any]:
    """{email: {since, campaign_key, flags, reason}} for inboxes a change-set
    pulled out of a campaign. Never raises; an unreadable store means an empty
    ledger and a logged warning, not a crash."""
    try:
        store = store or _store()
        value = store.get(QUARANTINE_KEY, {}) or {}
        return dict(value) if isinstance(value, dict) else {}
    except Exception as exc:  # noqa: BLE001 - the ledger must never break a read-only run
        logger.warning("quarantine ledger unreadable: %s", exc)
        return {}


def quarantine_inbox(email: str, reason: str, flags: Optional[List[str]] = None,
                     campaign_key: Optional[str] = None, now: Optional[datetime] = None,
                     store=None) -> Dict[str, Any]:
    """Record that ``email`` was pulled out of a campaign, so it cannot come
    back as "the healthiest insurance inbox" a week later on an empty window."""
    email = (email or "").lower()
    now = now or datetime.now(TZ)
    entry = {
        "since": now.isoformat(),
        "campaign_key": campaign_key,
        "flags": list(flags or []),
        "reason": reason,
    }
    try:
        store = store or _store()
        ledger = load_quarantine(store)
        ledger[email] = entry
        store.set(QUARANTINE_KEY, ledger)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not record quarantine for %s: %s", email, exc)
    return entry


def clear_quarantine(email: str, store=None) -> bool:
    email = (email or "").lower()
    try:
        store = store or _store()
        ledger = load_quarantine(store)
        if email not in ledger:
            return False
        del ledger[email]
        store.set(QUARANTINE_KEY, ledger)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not clear quarantine for %s: %s", email, exc)
        return False


# ---------------------------------------------------------------- promotion
def _candidate_sort_key(row: Dict[str, Any]) -> Tuple[float, int, float, int, str]:
    """Healthiest first: warm-up score desc, MEASURED bounce before unmeasured,
    bounce asc, age desc, email asc.

    A missing bounce rate used to score 0.0, the best value there is, so an
    inbox with no data outranked one measured clean. Unmeasured now sorts after
    every measured candidate.
    """
    health = row.get("warmup_health")
    bounce = row.get("bounce_rate_7d")
    measured = 0 if bounce is not None else 1
    return (
        -(float(health) if health is not None else -1.0),
        measured,
        float(bounce) if bounce is not None else 0.0,
        -(int(row.get("age_days") or 0)),
        row["email"],
    )


def _campaign_rows(inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(inventory.get("campaigns") or [])


def promote_insurance(campaign_key: str, failing_inbox: str, inventory: Dict[str, Any],
                      campaigns: Optional[List[Dict[str, Any]]] = None,
                      now: Optional[datetime] = None,
                      max_per_domain: int = MAX_INBOXES_PER_DOMAIN,
                      quarantined: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Propose swapping the healthiest insurance inbox in for ``failing_inbox``.

    Returns a change-set record. It performs no HTTP call of any kind: the
    proposed ``email_list`` is handed to
    ``changesets/capacity/apply_promotion.py``, which diffs it against live and
    refuses to PATCH without Lorenzo's approval and the live flags.

    Three gates, all of which fail CLOSED:

    * never more than ``max_per_domain`` inboxes from one domain in one
      campaign, counted on the PROPOSED list;
    * never a candidate carrying a Section 6 flag, and never one whose health
      is unmeasured (no warm-up score, or an analytics window that could not be
      read). "No data" is not "clean";
    * never an inbox a previous change-set pulled out for health, until Lorenzo
      clears it with ``--clear-quarantine``.

    ``campaigns`` should be the live campaign list. When it is omitted the
    inventory's own recorded ``campaigns`` block is used, which is the same
    data; only as a last resort is the list rebuilt from the account rows,
    which cannot see an address that is in a live ``email_list`` but is no
    longer an account.
    """
    now = now or datetime.now(TZ)
    failing_inbox = (failing_inbox or "").lower()
    inboxes = inventory.get("inboxes") or []
    by_email = {r["email"]: r for r in inboxes}
    if quarantined is None:
        quarantined = load_quarantine()

    campaign_meta = settings.CAMPAIGNS.get(campaign_key) or {}
    campaign_id = campaign_meta.get("id")
    record = {
        "changeset": "capacity/promote_insurance",
        "action": "promote_insurance",
        "generated_at": now.isoformat(),
        "mode": get_mode(),
        "campaign_key": campaign_key,
        "campaign_id": campaign_id,
        "campaign_name": campaign_meta.get("name"),
        "remove": failing_inbox,
        "promote": None,
        "status": "proposed",
        "reason": "",
        "max_per_domain": max_per_domain,
        "current_email_list": [],
        "current_email_list_source": None,
        "proposed_email_list": [],
        "candidates_considered": [],
        "unknown_addresses_in_email_list": [],
        "remaining_campaigns": [],
        "failing_inbox_still_sends": False,
        "patch": None,
        "live_patch_performed": False,
        "apply_with": ("python3 changesets/capacity/apply_promotion.py --dry-run "
                       "--changeset <this file>"),
    }
    if not campaign_id:
        record["status"] = "unknown_campaign"
        record["reason"] = ("%r is not a campaign key in config/ids.json (known: %s)"
                            % (campaign_key, ", ".join(sorted(settings.CAMPAIGNS))))
        return record

    source_campaigns = campaigns if campaigns is not None else _campaign_rows(inventory)
    live = None
    for candidate in source_campaigns or []:
        if candidate.get("id") == campaign_id:
            live = candidate
            break
    if live is not None and live.get("email_list") is not None:
        current = [e.lower() for e in live.get("email_list") or []]
        record["current_email_list_source"] = (
            "live campaign email_list" if campaigns is not None else "inventory.campaigns")
    else:
        # Last resort. This cannot see an address that is in the live list but
        # is no longer an account, and apply_promotion would then refuse the
        # change-set for a list mismatch that regenerating cannot fix.
        current = sorted(r["email"] for r in inboxes
                         if campaign_id in (r.get("campaign_ids") or [])
                         or campaign_id in (r.get("inactive_campaign_ids") or []))
        record["current_email_list_source"] = "rebuilt from account rows (no campaign supplied)"
    record["current_email_list"] = current
    record["unknown_addresses_in_email_list"] = sorted(e for e in current if e not in by_email)

    if failing_inbox not in current:
        record["status"] = "inbox_not_in_campaign"
        record["reason"] = "%s is not in the email_list of %s" % (failing_inbox, campaign_key)
        record["proposed_email_list"] = current
        return record

    failing_row = by_email.get(failing_inbox) or {}
    remaining_campaigns = [k for k in (failing_row.get("campaign_keys") or [])
                           if k != campaign_key]
    record["remaining_campaigns"] = remaining_campaigns
    record["failing_inbox_still_sends"] = bool(remaining_campaigns)

    remaining = [e for e in current if e != failing_inbox]
    domain_counts = {}  # type: Dict[str, int]
    for email in remaining:
        domain_counts[domain_of(email)] = domain_counts.get(domain_of(email), 0) + 1

    pool = [r for r in inboxes
            if r["role"] == ROLE_INSURANCE and r["email"] not in current]
    chosen = None
    for row in sorted(pool, key=_candidate_sort_key):
        considered = {
            "email": row["email"],
            "domain": row["domain"],
            "warmup_health": row.get("warmup_health"),
            "bounce_rate_7d": row.get("bounce_rate_7d"),
            "reply_rate_7d": row.get("reply_rate_7d"),
            "analytics_days": row.get("analytics_days"),
            "analytics_missing": bool(row.get("analytics_missing")),
            "age_days": row.get("age_days"),
            "rejected_because": None,
        }
        if domain_counts.get(row["domain"], 0) >= max_per_domain:
            considered["rejected_because"] = (
                "%s already has %d inboxes in this campaign (cap %d)"
                % (row["domain"], domain_counts.get(row["domain"], 0), max_per_domain))
        elif row["email"] in quarantined:
            entry = quarantined.get(row["email"]) or {}
            considered["rejected_because"] = (
                "quarantined since %s (%s). Clear it with --clear-quarantine %s once you have "
                "checked it by hand."
                % (str(entry.get("since"))[:10], entry.get("reason") or "removed from a campaign",
                   row["email"]))
        elif row.get("analytics_missing"):
            considered["rejected_because"] = (
                "no 7-day analytics: cannot be called healthy (the analytics pull for this inbox "
                "failed this run)")
        elif row.get("warmup_health") is None:
            considered["rejected_because"] = (
                "no warm-up score: cannot be called healthy")
        elif row.get("flags"):
            considered["rejected_because"] = "carries flags: %s" % ", ".join(row["flags"])
        elif chosen is not None:
            considered["rejected_because"] = "a healthier candidate was picked"
        else:
            chosen = row
        record["candidates_considered"].append(considered)

    failing_limit = daily_limit_of(failing_row, PER_INBOX_DAILY_LIMIT)
    if chosen is None:
        record["status"] = "removed_without_replacement"
        record["proposed_email_list"] = remaining
        if remaining_campaigns:
            consequence = (
                "%s stays in %d other campaign(s) (%s), so this PATCH does not stop it sending and "
                "costs 0/day of capacity. To take it out of the estate, write one change-set per "
                "campaign."
                % (failing_inbox, len(remaining_campaigns), ", ".join(remaining_campaigns)))
        else:
            consequence = (
                "%s is in no other campaign, so it stops sending: capacity drops by %d/day, which "
                "is the cheaper of the two mistakes."
                % (failing_inbox, failing_limit))
        # No pool size here: the size of the spare pool is a reserve count,
        # and candidates_considered already names every inbox that was tried.
        record["reason"] = ("no eligible insurance inbox. %s still comes OUT of %s. %s"
                            % (failing_inbox, campaign_key, consequence))
    else:
        record["promote"] = chosen["email"]
        record["proposed_email_list"] = sorted(remaining + [chosen["email"]])
        record["status"] = "proposed"
        # The health figures the pick was made on, carried into the change-set
        # so apply_promotion can refuse a candidate whose health was never
        # measured instead of trusting the word "healthiest".
        record["promote_health"] = {
            "warmup_health": chosen.get("warmup_health"),
            "bounce_rate_7d": chosen.get("bounce_rate_7d"),
            "reply_rate_7d": chosen.get("reply_rate_7d"),
            "sent_7d": chosen.get("sent_7d"),
            "analytics_days": chosen.get("analytics_days"),
            "analytics_missing": bool(chosen.get("analytics_missing")),
            "age_days": chosen.get("age_days"),
            "flags": list(chosen.get("flags") or []),
        }
        record["reason"] = (
            "%s is the healthiest insurance inbox (warm-up %s, bounce %s over %s day(s) of "
            "analytics, %s days old) on a domain with %d of %d slots used in this campaign"
            % (chosen["email"], chosen.get("warmup_health"), _pct(chosen.get("bounce_rate_7d")),
               chosen.get("analytics_days"), chosen.get("age_days"),
               domain_counts.get(chosen["domain"], 0), max_per_domain))

    after = {}  # type: Dict[str, int]
    for email in record["proposed_email_list"]:
        after[domain_of(email)] = after.get(domain_of(email), 0) + 1
    record["domain_counts_after"] = after
    over = sorted(d for d, n in after.items() if n > max_per_domain)
    if over:
        # Pre-existing over-cap domains are reported, never created by this function.
        record["pre_existing_over_cap_domains"] = over
    record["patch"] = {
        "method": "PATCH",
        "path": "/api/v2/campaigns/%s" % campaign_id,
        "id": campaign_id,
        "payload": {"email_list": record["proposed_email_list"]},
    }

    # Capacity is an ESTATE number, not an email_list number. An inbox only
    # stops sending when it leaves every campaign it is in, and the promoted
    # inbox adds its full daily limit because insurance sends nothing today.
    removed_delta = 0 if remaining_campaigns else -failing_limit
    promoted_delta = daily_limit_of(chosen, PER_INBOX_DAILY_LIMIT) if chosen else 0
    limits = ((inventory.get("capacity") or {}).get("campaign_limits") or {})
    record["capacity_delta_per_day"] = removed_delta + promoted_delta
    record["email_list_size_delta"] = len(record["proposed_email_list"]) - len(current)
    record["capacity_note"] = (
        "estate delta %+d/day: %s from removing %s, %+d/day from promoting %s. The estate's real "
        "ceiling is also capped by the campaign daily_limits, which add up to %s/day today and "
        "this change-set does not touch."
        % (record["capacity_delta_per_day"],
           ("0/day (it still sends for %s)" % ", ".join(remaining_campaigns))
           if remaining_campaigns else "%+d/day" % removed_delta,
           failing_inbox, promoted_delta, chosen["email"] if chosen else "nothing",
           limits.get("total_campaign_daily_limit")))
    return record


def write_changeset(record: Dict[str, Any], directory: Optional[str] = None) -> str:
    """Persist a promotion proposal as a reviewable change-set file."""
    directory = directory or CHANGESET_DIR
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        pass
    stamp = (record.get("generated_at") or "").replace(":", "").replace("-", "")[:15]
    name = "promote_%s_%s_%s.json" % (
        record.get("campaign_key") or "unknown",
        (record.get("remove") or "unknown").replace("@", "_at_"),
        stamp or "now",
    )
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return path


# ------------------------------------------------------------------ the run
def _campaign_block(campaigns: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """The campaign email_lists, recorded verbatim in the deliverable.

    ``promote_insurance`` needs the live list, not a list rebuilt from the
    account rows: an address that is in a live ``email_list`` but is no longer
    an Instantly account is invisible to the rebuild, and apply_promotion then
    refuses the change-set for a list-length mismatch that regenerating the
    change-set reproduces exactly. Keeping the lists here means the shipped
    inventory is enough to build a correct change-set from.
    """
    rows = []
    for campaign in campaigns or []:
        cid = campaign.get("id")
        rows.append({
            "id": cid,
            "key": (settings.CAMPAIGN_BY_ID.get(cid) or {}).get("key"),
            "name": campaign.get("name"),
            "status": campaign.get("status"),
            "is_active": campaign_is_active(campaign),
            "daily_limit": campaign.get("daily_limit"),
            "email_list": [e.lower() for e in campaign.get("email_list") or []],
        })
    rows.sort(key=lambda r: (r.get("name") or ""))
    return rows


def build_inventory(accounts: List[Dict[str, Any]], campaigns: List[Dict[str, Any]],
                    daily_rows: List[Dict[str, Any]], now: datetime,
                    source: str = "live", window: Optional[Tuple[str, str]] = None,
                    analytics_errors: Optional[List[str]] = None,
                    missing_analytics: Optional[List[str]] = None,
                    source_errors: Optional[List[str]] = None) -> Dict[str, Any]:
    membership = campaign_membership(campaigns)
    analytics = aggregate_daily(daily_rows)
    missing = set((e or "").lower() for e in (missing_analytics or []))
    inboxes = [build_inbox_row(a, membership, analytics, now, missing) for a in accounts]
    inboxes.sort(key=lambda r: (r["role"], r["domain"], r["persona"]))
    capacity = capacity_today(inboxes, now, campaigns=campaigns)
    missing_rows = [r for r in inboxes if r["analytics_missing"]]
    missing_active = [r["email"] for r in missing_rows if r["role"] == ROLE_ACTIVE]
    return {
        "_about": (
            "Inbox inventory and health alerts for Blueprint M2. Generated by "
            "jobs/inbox_inventory.py from live Instantly reads; never edited by hand. role: active "
            "(in the email_list of a SENDING campaign), warming (< %d days), idle (warm-up done "
            "and in no sending campaign, the pool promote_insurance picks from), retired (not "
            "status 1: paused, disconnected, erroring or half-built). Health alerts only: this "
            "file carries no reserve count and no buying advice." % WARMUP_DAYS),
        "_reply_rate_note": (
            "reply_rate_7d = unique_replies / sent. replies_automatic is a SEPARATE counter in "
            "GET /accounts/analytics/daily, not a subset of replies (2026-09-19: replies=0, "
            "replies_automatic=7 across the twelve active inboxes), so it is never subtracted."),
        "generated_at": now.isoformat(),
        "generated_by": "jobs/inbox_inventory.py",
        "source": source,
        "mode": get_mode(),
        "analytics_window": {"start": window[0], "end": window[1]} if window else None,
        "analytics_errors": analytics_errors or [],
        "source_errors": source_errors or [],
        "analytics_missing_inboxes": sorted(r["email"] for r in missing_rows),
        "analytics_missing_active_inboxes": sorted(missing_active),
        "rules": {
            "warmup_days": WARMUP_DAYS,
            "max_inboxes_per_domain": MAX_INBOXES_PER_DOMAIN,
            "per_inbox_daily_limit": PER_INBOX_DAILY_LIMIT,
            "ramped_daily_limit": RAMPED_DAILY_LIMIT,
            "ramp_date": RAMP_DATE.isoformat(),
            "ramp_min_reply_rate": RAMP_MIN_REPLY_RATE,
            "warmup_health_floor": WARMUP_HEALTH_FLOOR,
            "bounce_alert": BOUNCE_ALERT,
            "reply_rate_alert": REPLY_RATE_ALERT,
            "warmup_stays_on": True,
            "informational_flags": list(INFORMATIONAL_FLAGS),
        },
        "counts": {
            "inboxes": len(inboxes),
            "domains": len(set(r["domain"] for r in inboxes)),
            # No "idle" total: that is a reserve count (see COUNTED_ROLES).
            "by_role": {
                role: len([r for r in inboxes if r["role"] == role])
                for role in COUNTED_ROLES
            },
            "unhealthy_domains": len(set(r["domain"] for r in inboxes if actionable_flags(r))),
            # "flagged" is the ACTIONABLE count. render(), the digest and the
            # Job_Log all read this one field, so the push on Lorenzo's phone
            # can no longer say 38 while the table under it says 5.
            "flagged": len([r for r in inboxes if actionable_flags(r)]),
            "flagged_informational": len([r for r in inboxes
                                          if r["flags"] and not actionable_flags(r)]),
            "analytics_missing": len(missing_rows),
            "analytics_missing_active": len(missing_active),
        },
        "capacity": capacity,
        "ramp_plan": ramp_plan(inboxes, now),
        "campaigns": _campaign_block(campaigns),
        "domains": summarise_domains(inboxes),
        "inboxes": inboxes,
    }


def _pull_analytics(client, emails: List[str], start: str, end: str, chunk: int,
                    rows: List[Dict[str, Any]], errors: List[str], missing: List[str],
                    retries: List[str], depth: int = 0) -> None:
    """Fetch the 7-day window in chunks, halving a chunk that fails.

    This workspace answers HTTP 413 on a large analytics pull, so a chunk that
    fails is retried at half the size before it is given up. Whatever is still
    unreadable at the end goes into ``missing``: those inboxes are marked, not
    silently reported as having sent nothing, because an inbox reported as
    having sent nothing reads as a 0% reply rate and that is a removal.

    The loop itself is ``shared.analytics.account_daily(on_error="halve")``;
    this keeps the out-parameter signature its two callers pass.
    """
    got = analytics.account_daily(
        client, emails, start, end, chunk=chunk,
        on_error=analytics.HALVE, retry_depth=ANALYTICS_RETRY_DEPTH - depth,
        sleep_seconds=0.0)
    rows.extend(got.rows)
    errors.extend(got.errors)
    missing.extend(got.missing)
    retries.extend(got.retries)


def _fetch_live(client, now: datetime) -> Dict[str, Any]:
    source_errors = []  # type: List[str]
    # Bind the walks: shared.instantly.CursorWalk exists so a caller can tell a
    # complete pull from one that stopped at max_pages. A short accounts pull
    # understates capacity and hides inboxes from the flag table with no sign
    # that anything was missed.
    accounts_walk = client.iterate("accounts", {"limit": 100})
    accounts = list(accounts_walk)
    if getattr(accounts_walk, "truncated", False):
        source_errors.append("the accounts walk was truncated at %d page(s): the inventory is a "
                             "PARTIAL account list" % getattr(accounts_walk, "pages", 0))
    campaigns_walk = client.iterate("campaigns", {"limit": 100})
    campaigns = list(campaigns_walk)
    if getattr(campaigns_walk, "truncated", False):
        source_errors.append("the campaigns walk was truncated at %d page(s): roles and campaign "
                             "limits are computed from a PARTIAL campaign list"
                             % getattr(campaigns_walk, "pages", 0))
    end = now.date() - timedelta(days=1)
    start = end - timedelta(days=ANALYTICS_WINDOW_DAYS - 1)
    emails = [(a.get("email") or "").lower() for a in accounts if a.get("email")]
    rows = []  # type: List[Dict[str, Any]]
    errors = []  # type: List[str]
    missing = []  # type: List[str]
    retries = []  # type: List[str]
    _pull_analytics(client, emails, start.isoformat(), end.isoformat(), ANALYTICS_CHUNK,
                    rows, errors, missing, retries)
    return {
        "accounts": accounts, "campaigns": campaigns, "daily": rows,
        "errors": errors, "missing": missing, "retries": retries,
        "source_errors": source_errors,
        "window": (start.isoformat(), end.isoformat()),
    }


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _items(blob: Any) -> List[Dict[str, Any]]:
    if isinstance(blob, list):
        return blob
    if isinstance(blob, dict):
        return blob.get("items") or []
    return []


def _fetch_fixtures(directory: str) -> Dict[str, Any]:
    return {
        "accounts": _items(_load_json(os.path.join(directory, "accounts_2026-09-22.json"))),
        "campaigns": _items(_load_json(os.path.join(directory, "campaigns_2026-09-22.json"))),
        "daily": _items(_load_json(
            os.path.join(directory, "daily_account_analytics_2026-09-15_21.json"))),
        "errors": [], "missing": [], "retries": [], "source_errors": [],
        "window": ("2026-09-15", "2026-09-21"),
    }


def run(now: datetime, client=None, fixtures: Optional[str] = None) -> Dict[str, Any]:
    if fixtures:
        pulled = _fetch_fixtures(fixtures)
        source = "fixtures:%s" % os.path.basename(fixtures.rstrip("/"))
    else:
        if client is None:
            from shared.instantly import default_client
            client = default_client()
        pulled = _fetch_live(client, now)
        source = "live"
    inventory = build_inventory(
        pulled["accounts"], pulled["campaigns"], pulled["daily"], now, source=source,
        window=pulled["window"], analytics_errors=pulled["errors"],
        missing_analytics=pulled["missing"], source_errors=pulled["source_errors"])
    inventory["analytics_retries"] = pulled["retries"]
    return inventory


def write_inventory(inventory: Dict[str, Any], path: str = INVENTORY_PATH) -> str:
    """Atomic write through a UNIQUE temp file.

    A fixed ``<path>.tmp`` is shared state: two overlapping runs (the 07:00
    scheduled one plus a manual ``--now``, or a retry after a hung run) race on
    it and the loser dies with FileNotFoundError inside os.replace.
    """
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp",
                               dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(inventory, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


# ------------------------------------------------------------------- output
def _unhealthy_by_domain(inventory: Dict[str, Any]) -> List[Tuple[str, int, List[str]]]:
    """[(domain, inboxes with an actionable flag, the actionable flags)], worst first."""
    out = {}  # type: Dict[str, Tuple[int, List[str]]]
    for row in inventory.get("inboxes") or []:
        flags = actionable_flags(row)
        if not flags:
            continue
        n, seen = out.get(row["domain"], (0, []))
        for flag in flags:
            if flag not in seen:
                seen.append(flag)
        out[row["domain"]] = (n + 1, seen)
    return sorted(((d, n, f) for d, (n, f) in out.items()), key=lambda t: (-t[1], t[0]))


def _role_line(inventory: Dict[str, Any]) -> str:
    """The headline roles. Idle inboxes are named but never totalled: their
    total is a reserve count, and the reserve is Lorenzo's call."""
    counts = inventory["counts"]["by_role"]
    line = ("%d active, %d warming, %d retired (not status 1: paused, disconnected or erroring)"
            % (counts[ROLE_ACTIVE], counts[ROLE_WARMING], counts[ROLE_RETIRED]))
    if any(r.get("role") == ROLE_IDLE for r in inventory.get("inboxes") or []):
        line += ", the rest idle (not in any sending campaign)"
    return line


def render(inventory: Dict[str, Any]) -> str:
    cap = inventory["capacity"]
    today = cap["today"]
    lines = []
    lines.append("INBOX HEALTH  %s  (source: %s, mode: %s)"
                 % (inventory["generated_at"][:19], inventory["source"], inventory["mode"]))
    window = inventory.get("analytics_window") or {}
    if window:
        lines.append("7-day analytics window: %s to %s" % (window.get("start"), window.get("end")))
    lines.append("%d inboxes on %d domains: %s"
                 % (inventory["counts"]["inboxes"], inventory["counts"]["domains"],
                    _role_line(inventory)))
    missing = inventory["counts"].get("analytics_missing") or 0
    if missing:
        lines.append("!! %d inbox(es) have NO 7-day analytics this run (%d of them active). "
                     "Reply and bounce rates below are incomplete."
                     % (missing, inventory["counts"].get("analytics_missing_active") or 0))
    for problem in inventory.get("source_errors") or []:
        lines.append("!! %s" % problem)
    lines.append("")
    lines.append("SENDING TODAY")
    lines.append("  %d/day from %d active inbox(es)"
                 % (today["active_capacity_per_day"], today["active_inboxes"]))
    limits = cap.get("campaign_limits") or {}
    if limits.get("active_campaigns"):
        lines.append("  %d/day is the sum of the %d active campaign daily_limits (binding: %s)"
                     % (limits["total_campaign_daily_limit"], limits["active_campaigns"],
                        limits["binding_constraint"]))
    for alert in cap.get("alerts") or []:
        lines.append("  ALERT  %s" % alert)
    lines.append("")
    lines.append("HEALTH BY DOMAIN")
    unhealthy = _unhealthy_by_domain(inventory)
    for domain, n, flags in unhealthy:
        lines.append("  %d inbox(es) unhealthy on %s: %s" % (n, domain, ", ".join(flags)))
    if not unhealthy:
        lines.append("  no domain has an unhealthy inbox")
    lines.append("")
    lines.append("DOMAINS")
    for dom in inventory["domains"]:
        roles = ",".join("%s=%d" % (k, v) for k, v in sorted(dom["roles"].items()))
        if dom.get("has_idle_inboxes"):
            # named, not counted: see COUNTED_ROLES
            roles = ",".join(p for p in (roles, ROLE_IDLE) if p)
        lines.append("  %-22s %d inbox(es) %-28s sent7d=%-5d reply=%-7s bounce=%-7s health>=%s%s"
                     % (dom["domain"], dom["inboxes"], roles, dom["sent_7d"],
                        _pct(dom["reply_rate_7d"]), _pct(dom["bounce_rate_7d"]),
                        dom["warmup_health_min"],
                        "  FLAGS: " + ",".join(dom["flags"]) if dom["flags"] else ""))
    flagged = [r for r in inventory["inboxes"] if actionable_flags(r)]
    lines.append("")
    lines.append("FLAGGED INBOXES (%d)" % len(flagged))
    for row in flagged:
        lines.append("  %-38s %-10s %s" % (row["email"], row["role"], ",".join(row["flags"])))
    if not flagged:
        lines.append("  none")
    ramp = inventory["ramp_plan"]
    lines.append("")
    lines.append("RAMP: %s" % ramp["_rule"])
    lines.append("  eligible for %d/day on today's data: %s"
                 % (RAMPED_DAILY_LIMIT,
                    ", ".join(ramp["eligible_for_30_on_todays_data"]) or "none"))
    if inventory.get("analytics_retries"):
        lines.append("")
        lines.append("ANALYTICS RETRIES: %s" % "; ".join(inventory["analytics_retries"]))
    if inventory.get("analytics_errors"):
        lines.append("")
        lines.append("ANALYTICS ERRORS: %s" % "; ".join(inventory["analytics_errors"]))
    return "\n".join(lines)


def _digest(inventory: Dict[str, Any]) -> Tuple[str, str]:
    """The one-line push. It must not disagree with the printed report.

    Health only: it leads with an analytics outage, then says plainly where
    health has dropped ("N inboxes unhealthy on domain X"), and counts the same
    actionable flags the report prints. It never counts a reserve and never
    suggests buying or ordering anything.
    """
    cap = inventory["capacity"]
    counts = inventory["counts"]
    missing = counts.get("analytics_missing") or 0
    flagged = counts["flagged"]
    alerts = cap.get("alerts") or []
    if missing:
        title = "Inbox health: %d inbox(es) with NO analytics" % missing
    elif alerts:
        # A sending alert leads. The title never says "no alerts" or opens on
        # "0 flagged" while nothing is sending.
        title = "Inbox health: ALERT %s" % ", ".join(alerts)
        if flagged:
            title += ", %d inbox(es) flagged" % flagged
    elif flagged:
        title = "Inbox health: %d inbox(es) flagged" % flagged
    else:
        title = "Inbox health: no alerts"
    parts = []
    if missing:
        parts.append("%d inbox(es) have no 7-day analytics this run (%d active). Reply and bounce "
                     "figures are incomplete and config/inbox_inventory.json was not overwritten."
                     % (missing, counts.get("analytics_missing_active") or 0))
    for problem in inventory.get("source_errors") or []:
        parts.append(problem)
    for alert in cap.get("alerts") or []:
        parts.append("ALERT: %s" % alert)
    for domain, n, flags in _unhealthy_by_domain(inventory):
        parts.append("%d inbox(es) unhealthy on %s (%s)." % (n, domain, ", ".join(flags)))
    parts.append("%s." % _role_line(inventory))
    parts.append("Sending %d/day from %d active inbox(es)."
                 % (cap["today"]["active_capacity_per_day"], cap["today"]["active_inboxes"]))
    parts.append("%d inbox(es) flagged (%d informational)."
                 % (flagged, counts.get("flagged_informational") or 0))
    return title, "\n".join(p for p in parts if p)


# --------------------------------------------------------------------- main
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="inbox_inventory", description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="read, compute and print; writes no config file and sends no digest")
    p.add_argument("--now", action="store_true",
                   help="refresh config/inbox_inventory.json and send Lorenzo the digest")
    p.add_argument("--as-of", help="ISO timestamp to evaluate at (default: now, America/Chicago)")
    p.add_argument("--fixtures", nargs="?", const=SNAPSHOT_DIR, default=None,
                   help="offline: read recorded snapshots instead of the Instantly API")
    p.add_argument("--out", default=None,
                   help="inventory path (default config/inbox_inventory.json)")
    p.add_argument("--json", action="store_true", help="print the inventory as JSON")
    p.add_argument("--promote", metavar="CAMPAIGN_KEY:INBOX",
                   help="propose an insurance swap and write the change-set")
    p.add_argument("--no-changeset", action="store_true",
                   help="with --promote: print the proposal without writing the change-set file")
    p.add_argument("--changeset-dir", default=None,
                   help="where --promote writes the change-set (default changesets/capacity/)")
    p.add_argument("--clear-quarantine", metavar="INBOX",
                   help="make a previously removed inbox eligible for promotion again")
    args = p.parse_args(argv)

    if not args.dry_run and not args.now:
        args.dry_run = True
    if args.dry_run:
        use_scratch_logs(JOB)

    explicit_out = args.out is not None
    out_path = args.out or INVENTORY_PATH
    if args.now and args.fixtures and not explicit_out:
        # --fixtures replays recorded snapshots. Letting that overwrite the
        # shipped deliverable puts replayed data behind a live-looking file.
        print("refusing --now --fixtures without an explicit --out: that would overwrite %s with "
              "replayed snapshot data. Use --out %s (or any path) to write the replay."
              % (INVENTORY_PATH, REPLAY_INVENTORY_PATH), file=sys.stderr)
        return 1

    if args.clear_quarantine:
        cleared = clear_quarantine(args.clear_quarantine)
        print("quarantine: %s %s" % (args.clear_quarantine,
                                     "cleared" if cleared else "was not quarantined"))

    if args.as_of:
        from shared.slots import parse_iso
        now = parse_iso(args.as_of)
        if now is None:
            print("could not parse --as-of %r" % args.as_of, file=sys.stderr)
            return 1
        now = now.astimezone(TZ)
    else:
        now = datetime.now(TZ)

    try:
        inventory = run(now, fixtures=args.fixtures)
    except Exception as exc:  # noqa: BLE001 - one row per run, then alert
        log_run(JOB, "error", {"error": str(exc)[:400], "dry_run": bool(args.dry_run)})
        notify("Inbox inventory failed", "%s: %s" % (type(exc).__name__, str(exc)[:300]),
               priority="high", tags=["warning"])
        print("inbox_inventory failed: %s" % exc, file=sys.stderr)
        return 1

    # Everything after the reads is inside the same guard: a crash in the
    # write, the render or the digest used to escape main() entirely, leaving
    # no Job_Log row and no alert, which breaks the one-row-per-run contract.
    try:
        return _finish(args, inventory, now, out_path)
    except Exception as exc:  # noqa: BLE001
        log_run(JOB, "error", {"error": str(exc)[:400], "stage": "post_read",
                               "dry_run": bool(args.dry_run)})
        notify("Inbox inventory failed after the reads",
               "%s: %s" % (type(exc).__name__, str(exc)[:300]),
               priority="high", tags=["warning"])
        print("inbox_inventory failed after the reads: %s" % exc, file=sys.stderr)
        return 1


def _finish(args, inventory: Dict[str, Any], now: datetime, out_path: str) -> int:
    cap = inventory["capacity"]
    missing_active = inventory["counts"].get("analytics_missing_active") or 0

    promotion = None
    changeset_path = None
    if args.promote:
        if ":" not in args.promote:
            print("--promote wants CAMPAIGN_KEY:INBOX, got %r" % args.promote, file=sys.stderr)
            return 1
        key, _, inbox = args.promote.partition(":")
        promotion = promote_insurance(key.strip(), inbox.strip(), inventory, now=now)
        if not args.no_changeset and promotion["status"] in ("proposed",
                                                             "removed_without_replacement"):
            # Writing a local change-set file is not a live write. It is the
            # entire point of --promote, so it happens by default; the PATCH
            # still needs apply_promotion.py, MODE=live and Lorenzo.
            changeset_path = write_changeset(promotion, getattr(args, "changeset_dir", None))
            removed = (inventory_row(inventory, promotion["remove"]) or {})
            quarantine_inbox(promotion["remove"],
                             reason="removed from %s by change-set %s"
                                    % (promotion["campaign_key"],
                                       os.path.basename(changeset_path)),
                             flags=removed.get("flags"),
                             campaign_key=promotion["campaign_key"], now=now)

    written = None
    refused_write = None
    if args.now:
        if missing_active:
            refused_write = (
                "refused to overwrite %s: %d active inbox(es) have no 7-day analytics this run "
                "(%s). The file still holds the last complete picture."
                % (out_path, missing_active,
                   ", ".join(inventory["analytics_missing_active_inboxes"][:5])))
        else:
            written = write_inventory(inventory, out_path)

    if args.json:
        print(json.dumps(
            {"inventory": inventory, "promotion": promotion, "written": written,
             "changeset": changeset_path, "refused_write": refused_write}, indent=2))
    else:
        print(render(inventory))
        if promotion is not None:
            print("")
            print("PROMOTION (%s)" % promotion["status"])
            print("  campaign : %s (%s)" % (promotion["campaign_key"], promotion["campaign_id"]))
            print("  remove   : %s" % promotion["remove"])
            print("  promote  : %s" % (promotion["promote"] or "nothing available"))
            print("  why      : %s" % promotion["reason"])
            if promotion.get("remaining_campaigns"):
                print("  still in : %s  (this PATCH does not stop it sending)"
                      % ", ".join(promotion["remaining_campaigns"]))
            print("  list     : %d -> %d inboxes"
                  % (len(promotion["current_email_list"]), len(promotion["proposed_email_list"])))
            print("  capacity : %s" % promotion.get("capacity_note"))
            print("  change-set: %s" % (changeset_path or "not written (--no-changeset)"))
        if refused_write:
            print("")
            print(refused_write)
        if written:
            print("")
            print("wrote %s" % written)

    # Health only: "attention" means an inbox carries an actionable flag or
    # nothing is sending at all. The old reserve rule no longer drives it.
    status = "ok"
    if inventory["counts"]["flagged"] or cap.get("alerts"):
        status = "attention"
    if (inventory.get("analytics_errors") or inventory.get("source_errors")
            or inventory["counts"].get("analytics_missing")):
        status = "partial"
    log_run(JOB, status, {
        "dry_run": bool(args.dry_run),
        "source": inventory["source"],
        "inboxes": inventory["counts"]["inboxes"],
        "by_role": inventory["counts"]["by_role"],
        "active_capacity_per_day": cap["today"]["active_capacity_per_day"],
        "alerts": cap.get("alerts"),
        "flagged": inventory["counts"]["flagged"],
        "unhealthy_domains": inventory["counts"].get("unhealthy_domains"),
        "flagged_informational": inventory["counts"].get("flagged_informational"),
        "analytics_missing": inventory["counts"].get("analytics_missing"),
        "promotion": promotion["status"] if promotion else None,
        "changeset": changeset_path,
        "written": written,
        "refused_write": refused_write,
    })

    if args.now:
        title, message = _digest(inventory)
        priority = "high" if status == "partial" else "default"
        notify(title, message, priority=priority, tags=["chart_with_upwards_trend"])
    return 1 if status == "partial" else 0


def inventory_row(inventory: Dict[str, Any], email: str) -> Optional[Dict[str, Any]]:
    for row in inventory.get("inboxes") or []:
        if row["email"] == (email or "").lower():
            return row
    return None


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
