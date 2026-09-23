"""Pipeline hygiene (Blueprint S8): nightly mirror GHL "Sales" -> Instantly.

GHL "Sales" is the single source of truth. Once a night this module

1. reads every opportunity in the Sales pipeline (GHL, read-only),
2. reads the matching Instantly leads (POST /leads/list, read-only),
3. computes the interest-status diff (``compute_diff``),
4. computes the reverse check: Instantly leads marked interested that have no
   GHL opportunity (``compute_reverse``) and GHL opportunities with no
   monetary value (``compute_value_fixes``),
5. applies everything through the shared clients (``apply``). Every write goes
   through ``shared.settings.guard_write`` inside the clients, so in
   MODE=shadow nothing reaches Instantly or GHL: each write comes back as a
   ``would_do`` record and lands in .tmp/shadow_log.jsonl.

Stage -> Instantly interest value
---------------------------------
    new_reply        -> 1  interested
    call_booked      -> 2  meeting booked
    proposal_sent    -> 3  meeting completed
    won              -> 4  closed
    lost             -> -1 not interested, -2 when the lost reason names the
                           wrong person, -4 no_show when it mentions
                           "no show" / "ghosted"
    follow_up_later  -> -1 not interested (this is the router's "not now": it
                           agrees with models.INTEREST_FOR_LABEL[
                           "negative_notnow"]), plus a GHL note

A negative Instantly value is sticky: the mirror never turns a lead the engine
marked negative back into a positive unless GHL shows real progress (Call
Booked, Proposal Sent, Won), and never shuffles one negative code into another
unless GHL named the reason (wrong person, no show). See ``mirror_allowed``.

CLI (from "Agentic Worklfows/"):
    python3 -m services.reply_engine.pipeline_sync --dry-run          # compute + print, no apply
    python3 -m services.reply_engine.pipeline_sync --now              # apply (shadow -> would_do)
    python3 -m services.reply_engine.pipeline_sync --dry-run --fixtures  # offline replay on recorded leads
    python3 -m services.reply_engine.pipeline_sync --dry-run --as-of 2026-09-21T21:10:00-05:00

``--fixtures`` is a replay of a recorded snapshot and can never apply: it is
rejected together with ``--now`` and forces ``apply_blocked=fixture_replay``.

No GHL token yet: every GHL read returns None (logged ``ghl_token_missing``)
and the forward diff is empty; the reverse check still runs because it only
needs Instantly. Python 3.9 compatible.
"""
import argparse
import inspect
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from shared import settings
from shared.ghl import GHL
from shared.instantly import Instantly, default_client, InstantlyError
from shared.job_log import log_run
from shared.notify import notify

logger = logging.getLogger("reply_engine.pipeline_sync")

JOB_NAME = "pipeline_sync"

# --------------------------------------------------------------------- config
# GHL Sales stage key (config/ids.json ghl.pipelines.sales.stages) -> Instantly
# interest value (config/ids.json instantly.interest_status_codes).
STAGE_TO_INTEREST = {
    "new_reply": 1,
    "call_booked": 2,
    "proposal_sent": 3,
    "won": 4,
    "lost": -1,
    # "not now". models.STAGE_FOR_LABEL["negative_notnow"] parks the lead here
    # and models.INTEREST_FOR_LABEL["negative_notnow"] sets Instantly -1; the
    # mirror must agree or it flips every dated not-now lead back to Interested
    # the night after the router classified it.
    "follow_up_later": -1,
}  # type: Dict[str, int]

INTEREST_NO_SHOW = -4          # config/ids.json instantly.interest_status_codes: -4 no_show
INTEREST_LOST = -3             # -3 lost (kept for completeness; the mirror writes -1/-2/-4)
INTEREST_WRONG_PERSON = -2
INTEREST_NOT_INTERESTED = -1
LOST_NO_SHOW_MARKERS = ("no show", "no-show", "noshow", "ghost")
LOST_WRONG_PERSON_MARKERS = ("wrong person", "wrong contact", "not the right person",
                             "no longer with", "no longer here", "left the company")

# Negative Instantly values the mirror may write on top of another negative,
# because GHL stated the reason explicitly.
SPECIFIC_NEGATIVES = (INTEREST_WRONG_PERSON, INTEREST_NO_SHOW)
# GHL stages that prove the lead really did re-open, so a negative Instantly
# value may be replaced by a positive one.
REOPEN_STAGES = ("call_booked", "proposal_sent", "won")

# Instantly interest values that mean "this lead should have a GHL opportunity".
POSITIVE_INTEREST_VALUES = (1, 2, 3, 4)

# Which Sales stage a positive Instantly lead lands in when the reverse check
# has to create the opportunity (the lead exists in Instantly, not in GHL).
INTEREST_TO_STAGE = {1: "new_reply", 2: "call_booked", 3: "proposal_sent", 4: "won"}  # type: Dict[int, str]

# How far along the Sales funnel a stage is, for picking between two
# opportunities on the same contact. This is deliberately NOT the ids.json
# stage position (which puts Lost 4 and Follow Up Later 5 above Won 3).
STAGE_PROGRESS = {
    "lost": 0,
    "follow_up_later": 1,
    "new_reply": 2,
    "call_booked": 3,
    "proposal_sent": 4,
    "won": 5,
}  # type: Dict[str, int]

# Opportunity value defaults, in USD, applied on upsert when GHL has no value.
# Reactivation offers bill 20-30% of first-year fees on a 60-100 contact list
# (config/offers.md). A 60-contact list reactivating 5-8% of contacts at
# $3k-5k first-year fees each is $9k-$40k recovered; 25% of the low-middle of
# that range is about $6,000, so that is the pipeline value until the deal is
# priced on the call.
# Outbound / trigger offers are a $2,500-5,000/mo retainer (offers.md, TO
# CONFIRM); two months at the $3,750 midpoint is $7,500, the value a first
# contract is worth before churn risk.
OPPORTUNITY_VALUE_DEFAULTS = {
    "reactivation": 6000.0,
    "outbound": 7500.0,
}  # type: Dict[str, float]
DEFAULT_OFFER_KEY = "reactivation"  # lower of the two when the campaign is unknown

# Instantly POST /leads/list filter values that select positive leads. Used by
# the reverse check so a nightly run does not page through every lead in every
# campaign. If the API rejects a value the code falls back to a full pull.
POSITIVE_LEAD_FILTERS = (
    "FILTER_LEAD_INTERESTED",
    "FILTER_LEAD_MEETING_BOOKED",
    "FILTER_LEAD_MEETING_COMPLETED",
    "FILTER_LEAD_CLOSED",
)
FULL_PULL_MAX_PAGES = 60  # 60 x 100 leads per campaign is the safety cap on a fallback full pull

# GHL opportunities/search paging. The Sales pipeline holds open AND closed
# opportunities, so it crosses one page within weeks of go-live; a truncated
# read makes every opportunity past the cap look "missing from GHL" to the
# reverse check, which would create duplicates. A truncated pull therefore
# blocks apply exactly the way an unreadable GHL does.
GHL_PAGE_SIZE = 100
GHL_MAX_PAGES = 20  # 2,000 opportunities
# GHL's /opportunities/search cursor is a PAIR: the id of the last row plus the
# matching timestamp. Sending only the id lets GHL re-serve the same page, which
# used to burn all 20 calls and leave the mirror permanently blocked.
# ``nextPage`` is deliberately absent: it is a page NUMBER, not an id, and
# sending 2 as startAfterId asks GHL for the rows after an opportunity called
# "2", which is page 1 again.
GHL_CURSOR_ID_PARAMS = ("start_after_id", "startAfterId")
GHL_CURSOR_TS_PARAMS = ("start_after", "startAfter")
GHL_CURSOR_PARAMS = GHL_CURSOR_ID_PARAMS + GHL_CURSOR_TS_PARAMS  # kept for callers that introspect

FIXTURES_DIR = Path(__file__).resolve().parent / "tests" / "fixtures"
LEADS_FIXTURE = FIXTURES_DIR / "instantly_replied_leads_2026-09.json"


# ------------------------------------------------------------------ helpers
def _lower(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def parse_ts(value: Any) -> Optional[datetime]:
    """ISO string (Z or offset), epoch seconds/ms, or datetime -> aware UTC."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / (1000.0 if value > 1e11 else 1.0)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# Timestamps that say when GHL last moved an opportunity, newest wins.
GHL_CHANGE_FIELDS = ("lastStageChangeAt", "last_stage_change_at", "lastStatusChangeAt",
                     "updatedAt", "updated_at", "dateUpdated")
# Timestamps that bound when Instantly last recorded anything about a lead,
# which is the best available upper bound on when its interest status was set.
LEAD_ACTIVITY_FIELDS = ("timestamp_updated", "timestamp_last_interest_change",
                        "timestamp_last_reply", "timestamp_last_contact")


def opportunity_changed_at(opp: Dict[str, Any]) -> Optional[datetime]:
    stamps = [parse_ts(opp.get(f)) for f in GHL_CHANGE_FIELDS]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


def lead_activity_at(lead: Dict[str, Any]) -> Optional[datetime]:
    stamps = [parse_ts(lead.get(f)) for f in LEAD_ACTIVITY_FIELDS]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


def stage_id_to_key() -> Dict[str, str]:
    """Reverse of settings.GHL_STAGES: stage id -> stage key."""
    return {v: k for k, v in (settings.GHL_STAGES or {}).items() if v}


def opp_email(opp: Dict[str, Any]) -> str:
    contact = opp.get("contact") or {}
    return _lower(contact.get("email") or opp.get("email") or opp.get("contact_email"))


def opp_contact_id(opp: Dict[str, Any]) -> Optional[str]:
    contact = opp.get("contact") or {}
    return opp.get("contactId") or opp.get("contact_id") or contact.get("id")


def opp_value(opp: Dict[str, Any]) -> Optional[float]:
    raw = opp.get("monetaryValue", opp.get("monetary_value"))
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def stage_key_for(opp: Dict[str, Any], id_to_key: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Stage key for a GHL opportunity: by pipelineStageId, then by an explicit
    ``stage`` key (fixtures / ids.json), then by status won/lost."""
    id_to_key = id_to_key if id_to_key is not None else stage_id_to_key()
    sid = opp.get("pipelineStageId") or opp.get("pipeline_stage_id") or opp.get("stage_id")
    if sid and sid in id_to_key:
        return id_to_key[sid]
    explicit = opp.get("stage")
    if explicit in STAGE_TO_INTEREST:
        return explicit
    status = _lower(opp.get("status"))
    if status in ("won", "lost"):
        return status
    return None


def lost_reason_text(opp: Dict[str, Any]) -> str:
    parts = []  # type: List[str]
    for key in ("lostReason", "lost_reason", "lostReasonName", "lost_reason_name", "notes", "note"):
        val = opp.get(key)
        if isinstance(val, str):
            parts.append(val)
    for field in opp.get("customFields") or []:
        if isinstance(field, dict):
            val = field.get("fieldValue", field.get("value"))
            if isinstance(val, str):
                parts.append(val)
    return " ".join(parts).lower()


def desired_interest(opp: Dict[str, Any], id_to_key: Optional[Dict[str, str]] = None) -> Tuple[Optional[int], str, Optional[str]]:
    """(interest_value, reason, note) for an opportunity; (None, reason, None)
    when the stage is unknown."""
    key = stage_key_for(opp, id_to_key)
    if key is None:
        return None, "unknown_stage", None
    if key == "lost":
        reason_text = lost_reason_text(opp)
        if any(marker in reason_text for marker in LOST_NO_SHOW_MARKERS):
            return INTEREST_NO_SHOW, "ghl_stage:lost (no show / ghosted)", None
        if any(marker in reason_text for marker in LOST_WRONG_PERSON_MARKERS):
            return INTEREST_WRONG_PERSON, "ghl_stage:lost (wrong person)", None
        return INTEREST_NOT_INTERESTED, "ghl_stage:lost", None
    value = STAGE_TO_INTEREST[key]
    note = None
    if key == "follow_up_later":
        note = (
            "Pipeline sync: stage Follow Up Later mirrored to Instantly as Not Interested (-1), "
            "the same value the reply router sets for a not-now lead, so the cold sequence stays "
            "stopped; revisit on the follow-up date."
        )
    return value, "ghl_stage:%s" % key, note


def status_for_stage(stage_key: Optional[str]) -> str:
    """GHL opportunity status for a Sales stage. Never rely on the client
    default: a Won deal written as ``open`` shows as open pipeline forever."""
    if stage_key == "won":
        return "won"
    if stage_key == "lost":
        return "lost"
    return "open"


def mirror_allowed(
    current: Optional[int],
    target: int,
    stage_key: Optional[str],
    ghl_changed_at: Optional[datetime] = None,
    negative_set_at: Optional[datetime] = None,
) -> Tuple[bool, Optional[str]]:
    """Should the GHL stage overwrite the Instantly value the engine already
    holds? (allowed, skip_reason).

    A negative Instantly value was set deliberately (the router classified the
    reply, or Lorenzo clicked it). The nightly mirror may not undo it:
    * negative -> positive only when GHL shows real progress (REOPEN_STAGES)
      AND GHL is demonstrably NEWER than the negative;
    * negative -> another negative only when GHL named the reason (wrong
      person, no show), otherwise the distinct code is kept.

    The staleness test is the half that was missing. Nothing moves an
    opportunity out of Call Booked after the call (no_show.py says so
    explicitly), so a lead Lorenzo marks No Show (-4) or Not Interested (-1)
    tonight sat against a Call Booked stage that last moved weeks ago: the
    mirror read that old positive stage as a re-open, wrote 2 back over the -4,
    and the next night agreed with itself, so the negative was gone for good
    with no alert. When both sides carry a timestamp and GHL's is not newer,
    the row is skipped and reported as a conflict instead. When either side has
    no timestamp there is nothing to compare, so the old behaviour stands.
    """
    if current is None or current >= 0:
        return True, None
    if target >= 0:
        if stage_key not in REOPEN_STAGES:
            return False, "negative_sticky: Instantly %s kept; ghl_stage:%s is not a re-open" % (current, stage_key)
        if ghl_changed_at is not None and negative_set_at is not None and ghl_changed_at <= negative_set_at:
            return False, (
                "stale_reopen: Instantly %s kept; ghl_stage:%s last moved %s, which is not after the Instantly "
                "value set around %s" % (current, stage_key, ghl_changed_at.isoformat(), negative_set_at.isoformat()))
        return True, None
    if target in SPECIFIC_NEGATIVES:
        return True, None
    return False, "negative_sticky: Instantly %s kept; ghl_stage:%s adds no detail" % (current, stage_key)


def pick_opportunity(opps: List[Dict[str, Any]], id_to_key: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The opportunity that decides a contact's mirrored status when the
    contact has more than one in the Sales pipeline. Deterministic: furthest
    along STAGE_PROGRESS, then most recently updated, then id."""
    id_to_key = id_to_key if id_to_key is not None else stage_id_to_key()

    def rank(opp: Dict[str, Any]):
        key = stage_key_for(opp, id_to_key)
        progress = STAGE_PROGRESS.get(key, -1)
        updated = str(opp.get("updatedAt") or opp.get("lastStageChangeAt") or opp.get("createdAt") or "")
        return (progress, updated, str(opp.get("id") or ""))

    return sorted(opps, key=rank)[-1]


def group_opportunities_by_email(
    ghl_opportunities: Iterable[Dict[str, Any]],
    id_to_key: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """One opportunity per contact email, chosen by ``pick_opportunity``.
    GHL's /opportunities/search does not guarantee an order, so without this a
    contact with an old Lost opportunity and a new Call Booked one mirrors a
    different value every night."""
    id_to_key = id_to_key if id_to_key is not None else stage_id_to_key()
    by_email = {}  # type: Dict[str, List[Dict[str, Any]]]
    for opp in ghl_opportunities:
        email = opp_email(opp)
        if email:
            by_email.setdefault(email, []).append(opp)
    out = []  # type: List[Dict[str, Any]]
    for email in sorted(by_email):
        group = by_email[email]
        chosen = pick_opportunity(group, id_to_key)
        if len(group) > 1:
            logger.info(
                "pipeline_sync: %s has %d Sales opportunities; mirroring %s (%s) and ignoring %s",
                email, len(group), chosen.get("id"), stage_key_for(chosen, id_to_key),
                [o.get("id") for o in group if o is not chosen],
            )
        out.append(chosen)
    return out


def offer_key_for_campaign(campaign_id: Optional[str]) -> str:
    camp = settings.CAMPAIGN_BY_ID.get(campaign_id or "", {})
    return camp.get("offer") or DEFAULT_OFFER_KEY


def default_value_for_campaign(campaign_id: Optional[str]) -> float:
    return OPPORTUNITY_VALUE_DEFAULTS.get(offer_key_for_campaign(campaign_id), OPPORTUNITY_VALUE_DEFAULTS[DEFAULT_OFFER_KEY])


def lead_email(lead: Dict[str, Any]) -> str:
    return _lower(lead.get("email") or lead.get("lead_email"))


def lead_campaign(lead: Dict[str, Any]) -> Optional[str]:
    return lead.get("campaign") or lead.get("campaign_id")


def lead_interest(lead: Dict[str, Any]) -> Optional[int]:
    raw = lead.get("lt_interest_status", lead.get("interest_status"))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def index_leads(instantly_leads: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out = {}  # type: Dict[str, List[Dict[str, Any]]]
    for lead in instantly_leads:
        email = lead_email(lead)
        if email:
            out.setdefault(email, []).append(lead)
    return out


def opportunity_name(lead: Dict[str, Any]) -> str:
    company = (lead.get("company_name") or "").strip()
    person = ("%s %s" % (lead.get("first_name") or "", lead.get("last_name") or "")).strip()
    base = " - ".join(p for p in (company, person) if p) or lead_email(lead)
    return "%s (Cold Email)" % base


# ------------------------------------------------------------ computations
def compute_diff(
    ghl_opportunities: Iterable[Dict[str, Any]],
    instantly_leads: Iterable[Dict[str, Any]],
    conflicts: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """GHL stage -> Instantly interest status changes.

    Returns one row per Instantly lead whose current ``lt_interest_status``
    differs from the value its GHL stage requires:
    {lead_email, campaign_id, from, to, reason, stage, opportunity_id, contact_id, note}

    ``conflicts`` (optional, appended to) collects the rows where a stale GHL
    stage would have overwritten a fresher Instantly negative. Those are the
    ones Lorenzo has to settle by hand: the mirror refuses to guess.
    """
    id_to_key = stage_id_to_key()
    by_email = index_leads(instantly_leads)
    rows = []  # type: List[Dict[str, Any]]
    seen = set()
    for opp in group_opportunities_by_email(ghl_opportunities, id_to_key):
        email = opp_email(opp)
        if not email:
            continue
        target, reason, note = desired_interest(opp, id_to_key)
        if target is None:
            logger.info("pipeline_sync: %s has unknown stage; skipped", email)
            continue
        stage = stage_key_for(opp, id_to_key)
        for lead in by_email.get(email, []):
            campaign_id = lead_campaign(lead)
            key = (email, campaign_id)
            if key in seen:
                continue
            seen.add(key)
            current = lead_interest(lead)
            if current == target:
                continue
            allowed, skip_reason = mirror_allowed(
                current, target, stage,
                ghl_changed_at=opportunity_changed_at(opp),
                negative_set_at=lead_activity_at(lead),
            )
            if not allowed:
                logger.info("pipeline_sync: %s %s -> %s skipped (%s)", email, current, target, skip_reason)
                if conflicts is not None and skip_reason and skip_reason.startswith("stale_reopen"):
                    conflicts.append({
                        "lead_email": email, "campaign_id": campaign_id, "from": current, "to": target,
                        "stage": stage, "opportunity_id": opp.get("id"), "reason": skip_reason,
                    })
                continue
            rows.append({
                "lead_email": email,
                "campaign_id": campaign_id,
                "from": current,
                "to": target,
                "reason": reason,
                "stage": stage,
                "opportunity_id": opp.get("id"),
                "contact_id": opp_contact_id(opp),
                "note": note,
            })
    rows.sort(key=lambda r: (r["lead_email"], r["campaign_id"] or ""))
    return rows


def opportunities_without_email(ghl_opportunities: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sales opportunities whose contact email could not be read.

    ``compute_reverse`` keys "already in GHL" on that email, so an opportunity
    that came back as ``{"contact": {"id": "cIlmi", "name": "Ilmi Curovic"}}``
    -- a contact created from a booking, or a search response that omits the
    address -- is invisible to the check and the lead gets a SECOND contact and
    a second Call Booked opportunity in the single source of truth. This is the
    same failure the ``ghl_truncated`` guard exists to prevent, so ``run_sync``
    blocks the reverse check the same way when this list is not empty.
    """
    return [o for o in ghl_opportunities if not opp_email(o)]


def compute_reverse(ghl_opportunities: Iterable[Dict[str, Any]], instantly_leads: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Instantly leads marked positive (1-4) with no GHL opportunity -> create."""
    ghl_opportunities = list(ghl_opportunities)
    have = set(opp_email(o) for o in ghl_opportunities if opp_email(o))
    rows = []  # type: List[Dict[str, Any]]
    seen = set()
    for lead in instantly_leads:
        email = lead_email(lead)
        interest = lead_interest(lead)
        if not email or interest not in POSITIVE_INTEREST_VALUES or email in have or email in seen:
            continue
        seen.add(email)
        campaign_id = lead_campaign(lead)
        stage = INTEREST_TO_STAGE.get(interest, "new_reply")
        status = status_for_stage(stage)
        rows.append({
            "action": "create_opportunity",
            "lead_email": email,
            "campaign_id": campaign_id,
            "interest": interest,
            "stage": stage,
            "status": status,
            "name": opportunity_name(lead),
            "first_name": lead.get("first_name"),
            "last_name": lead.get("last_name"),
            "company": lead.get("company_name"),
            # A won (or lost) deal must not carry a guessed pipeline value: it
            # would be reported as revenue that was never quoted. Leave it
            # blank so the real contract value is obviously missing.
            "monetary_value": None if status != "open" else default_value_for_campaign(campaign_id),
            "offer": offer_key_for_campaign(campaign_id),
            "reason": "instantly_interest:%s with no GHL opportunity" % interest,
        })
    rows.sort(key=lambda r: r["lead_email"])
    return rows


def compute_value_fixes(ghl_opportunities: Iterable[Dict[str, Any]], instantly_leads: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Open GHL opportunities with no monetary value -> set the offer default.

    A value fix must never move a deal. Opportunities whose stage id is not in
    config/ids.json are skipped exactly the way ``compute_diff`` skips them:
    the old code let them through with ``stage: None``, and ``apply`` then
    defaulted the stage to New Reply, dragging a live deal back up the funnel
    as a side effect of filling in a dollar value.
    """
    ghl_opportunities = list(ghl_opportunities)
    by_email = index_leads(instantly_leads)
    id_to_key = stage_id_to_key()
    per_contact = {}  # type: Dict[str, int]
    for opp in ghl_opportunities:
        cid = opp_contact_id(opp)
        if cid:
            per_contact[cid] = per_contact.get(cid, 0) + 1
    rows = []  # type: List[Dict[str, Any]]
    for opp in ghl_opportunities:
        value = opp_value(opp)
        if value:
            continue
        key = stage_key_for(opp, id_to_key)
        if key is None:
            logger.info("pipeline_sync: value fix for %s skipped, unknown stage", opp.get("id"))
            continue
        if key in ("won", "lost"):
            continue
        email = opp_email(opp)
        leads = by_email.get(email, [])
        campaign_id = lead_campaign(leads[0]) if leads else None
        contact_id = opp_contact_id(opp)
        rows.append({
            "action": "set_value",
            "opportunity_id": opp.get("id"),
            "contact_id": contact_id,
            "lead_email": email,
            "campaign_id": campaign_id,
            "stage": key,
            "stage_id": (settings.GHL_STAGES or {}).get(key),
            "status": status_for_stage(key),
            # Upserting by contact is ambiguous when the contact has more than
            # one Sales opportunity; apply() refuses those unless the client
            # can update the opportunity by id.
            "ambiguous_contact": bool(contact_id and per_contact.get(contact_id, 0) > 1),
            "name": opp.get("name") or email,
            "monetary_value": default_value_for_campaign(campaign_id),
            "offer": offer_key_for_campaign(campaign_id),
            "reason": "ghl_opportunity has no monetary value",
        })
    return rows


# ------------------------------------------------------------------- apply
# Only used in shadow, where upsert_contact returns a guard record and there is
# no real id yet. In live an unreadable contact id is an error, never a string.
SHADOW_CONTACT_PLACEHOLDER = "<contact from upsert (shadow)>"


class GHLContactIdUnreadable(Exception):
    """contacts/upsert answered in a shape with no id in it."""


def _shape(value: Any) -> Any:
    """Keys only: an error message must not carry the contact payload."""
    if isinstance(value, dict):
        return sorted(value.keys())
    return type(value).__name__


def _outcome(result: Any) -> str:
    if isinstance(result, dict) and result.get("shadow"):
        return "would_do"
    if result is None:
        return "skipped"
    if isinstance(result, dict):
        # GHL answers 200 with {"succeded": false} on a rejected write.
        for flag in ("succeded", "succeeded", "success"):
            if result.get(flag) is False:
                return "error"
    return "done"


def contact_id_from_upsert(contact: Any) -> Optional[str]:
    """The contact id in any of the envelopes GHL answers with. None means the
    id could not be read: the caller must NOT invent one."""
    if not isinstance(contact, dict):
        return None
    nested = contact.get("contact")
    nested = nested if isinstance(nested, dict) else {}
    for candidate in (nested.get("id"), nested.get("_id"), contact.get("id"), contact.get("_id")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _value_updater(ghl: GHL):
    """``GHL.update_opportunity_value(opportunity_id, monetary_value)`` if the
    shared client offers it (PUT /opportunities/{id} with only monetaryValue).
    None while it does not exist: see the cross-cutting request in the S8
    report. Never guessed by calling and catching TypeError."""
    fn = getattr(ghl, "update_opportunity_value", None)
    return fn if callable(fn) else None


def apply(
    diff: List[Dict[str, Any]],
    instantly: Optional[Instantly],
    ghl: Optional[GHL] = None,
    reverse: Optional[List[Dict[str, Any]]] = None,
    value_fixes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Apply the computed changes through the guarded clients.

    In shadow every client write returns its guard record, which is reported
    here as a ``would_do`` entry; nothing is sent. Returns
    {"results": [...], "would_do": n, "done": n, "skipped": n, "errors": [...]}.
    """
    results = []  # type: List[Dict[str, Any]]
    errors = []  # type: List[str]
    ghl = ghl if ghl is not None else GHL()

    for row in diff:
        entry = dict(row, action="update_interest_status")
        try:
            if instantly is None:
                raise InstantlyError("no Instantly client")
            res = instantly.update_interest_status(row["lead_email"], row["campaign_id"], row["to"])
            entry["outcome"] = _outcome(res)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the run
            entry["outcome"] = "error"
            entry["error"] = str(exc)
            errors.append("%s: %s" % (row["lead_email"], exc))
        # The GHL note is a separate write with its own outcome. It used to
        # share the try block, so a 429 on the note rewrote entry["outcome"] to
        # "error" for an interest update Instantly had already accepted, and
        # whoever reconciled from the digest re-applied a write that landed.
        if entry.get("outcome") not in (None, "error") and row.get("note") and row.get("contact_id"):
            try:
                note_res = ghl.create_note(row["contact_id"], row["note"])
                entry["note_outcome"] = _outcome(note_res)
            except Exception as exc:  # noqa: BLE001
                entry["note_outcome"] = "error"
                entry["note_error"] = str(exc)
                errors.append("%s: interest status applied, GHL note NOT written (%s)" % (row["lead_email"], exc))
        results.append(entry)

    for row in reverse or []:
        entry = dict(row)
        try:
            contact = ghl.upsert_contact(
                row["lead_email"],
                first_name=row.get("first_name"),
                last_name=row.get("last_name"),
                company=row.get("company"),
                tags=["cold-email", "instantly-positive-reply"],
            )
            entry["contact_outcome"] = _outcome(contact)
            shadow_contact = isinstance(contact, dict) and bool(contact.get("shadow"))
            contact_id = contact_id_from_upsert(contact) if not shadow_contact else None
            if contact_id is None:
                if not shadow_contact:
                    raise GHLContactIdUnreadable(
                        "contacts/upsert returned no contact id for %s (%r); opportunity not written"
                        % (row["lead_email"], _shape(contact))
                    )
                contact_id = SHADOW_CONTACT_PLACEHOLDER
            stage_key = row.get("stage")
            stage_id = (settings.GHL_STAGES or {}).get(stage_key or "")
            if not stage_id:
                raise ValueError("no GHL stage id for %r; opportunity not written" % (stage_key,))
            opp = ghl.upsert_opportunity(
                contact_id,
                settings.GHL_SALES_PIPELINE_ID,
                stage_id,
                row["name"],
                monetary_value=row.get("monetary_value"),
                status=row.get("status") or status_for_stage(stage_key),
            )
            entry["outcome"] = _outcome(opp)
        except Exception as exc:  # noqa: BLE001
            entry["outcome"] = "error"
            entry["error"] = str(exc)
            errors.append("%s: %s" % (row["lead_email"], exc))
        results.append(entry)

    updater = _value_updater(ghl)
    for row in value_fixes or []:
        entry = dict(row)
        try:
            opportunity_id = row.get("opportunity_id")
            if updater is not None and opportunity_id:
                # Preferred path: PUT /opportunities/{id} with monetaryValue
                # only. A value fix must not carry a stage or a status.
                res = updater(opportunity_id, row["monetary_value"])
            else:
                stage_id = row.get("stage_id") or (settings.GHL_STAGES or {}).get(row.get("stage") or "")
                if not stage_id:
                    raise ValueError(
                        "value fix for %s has no resolvable stage; refusing to upsert (it would move the deal)"
                        % (opportunity_id,))
                if not row.get("contact_id"):
                    raise ValueError("value fix for %s has no contact id; refusing to upsert" % (opportunity_id,))
                if row.get("ambiguous_contact"):
                    raise ValueError(
                        "contact %s has more than one Sales opportunity; a contact-keyed upsert would hit the "
                        "wrong one. Needs GHL.update_opportunity_value" % (row.get("contact_id"),))
                res = ghl.upsert_opportunity(
                    row["contact_id"],
                    settings.GHL_SALES_PIPELINE_ID,
                    stage_id,
                    row["name"],
                    monetary_value=row["monetary_value"],
                    status=row.get("status") or status_for_stage(row.get("stage")),
                )
            entry["outcome"] = _outcome(res)
        except Exception as exc:  # noqa: BLE001
            entry["outcome"] = "error"
            entry["error"] = str(exc)
            errors.append("%s: %s" % (row.get("opportunity_id"), exc))
        results.append(entry)

    counts = {"would_do": 0, "done": 0, "skipped": 0, "error": 0}
    for entry in results:
        outcome = entry.get("outcome", "error")
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome == "error" and not entry.get("error"):
            # a 200 whose body said the write did not happen (see _outcome)
            entry["error"] = "the API answered 200 but reported the write as not succeeded"
            errors.append("%s: %s" % (entry.get("lead_email") or entry.get("opportunity_id"), entry["error"]))
    return {
        "results": results,
        "would_do": counts["would_do"],
        "done": counts["done"],
        "skipped": counts["skipped"],
        "error": counts["error"],
        "errors": errors,
    }


# ------------------------------------------------------------------ fetching
def _page_rows(page: Any) -> List[Dict[str, Any]]:
    if isinstance(page, dict):
        return list(page.get("opportunities") or page.get("items") or [])
    if isinstance(page, list):
        return list(page)
    return []


def _page_meta(page: Any) -> Dict[str, Any]:
    meta = page.get("meta") if isinstance(page, dict) else None
    return meta if isinstance(meta, dict) else {}


def _cursor_params(ghl: GHL) -> Tuple[Optional[str], Optional[str]]:
    """(id keyword, timestamp keyword) ``GHL.search_opportunities`` accepts.

    Checked by signature, never by calling and catching TypeError. Both halves
    are resolved separately because GHL's cursor is the pair: the code used to
    pick the FIRST name in one flat list, which always resolved to
    ``start_after_id`` and silently dropped the timestamp the page meta had
    just handed us.
    """
    fn = getattr(ghl, "search_opportunities", None)
    if fn is None:
        return None, None
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return None, None
    id_param = next((n for n in GHL_CURSOR_ID_PARAMS if n in params), None)
    ts_param = next((n for n in GHL_CURSOR_TS_PARAMS if n in params), None)
    return id_param, ts_param


def _cursor_param(ghl: GHL) -> Optional[str]:
    """The id half of the cursor keyword, for callers that only need that."""
    return _cursor_params(ghl)[0]


def fetch_ghl_opportunities(ghl: GHL, limit: int = GHL_PAGE_SIZE, max_pages: int = GHL_MAX_PAGES) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Every opportunity in the Sales pipeline. (rows, note).

    note is ``ghl_token_missing`` when GHL could not be read at all, and
    ``ghl_truncated: ...`` when the pull could not be completed: a cursor the
    shared client cannot follow, a cursor that stops advancing, or the page
    cap. A truncated read is treated like an unreadable one by ``run_sync``,
    because every opportunity it did not see looks "missing from GHL" to the
    reverse check and would be created a second time.

    Paging sends BOTH halves of GHL's cursor (``startAfterId`` and the matching
    ``startAfter`` timestamp) whenever the client's signature offers them. When
    the page meta carries no cursor at all but the page is full, the last row's
    own id is used as ``startAfterId`` -- that is exactly what the parameter
    means -- so "exactly one full page" is settled by asking GHL rather than by
    guessing. A page that adds no new ids is a hard stop: the cursor is not
    advancing, and re-asking 19 more times only burns the rate limit.
    """
    if not ghl.has_token:
        return [], "ghl_token_missing"
    id_param, ts_param = _cursor_params(ghl)
    rows = []  # type: List[Dict[str, Any]]
    seen_ids = set()
    cursor_id = None  # type: Optional[Any]
    cursor_ts = None  # type: Optional[Any]
    pages = 0
    while pages < max_pages:
        kwargs = {"pipeline_id": settings.GHL_SALES_PIPELINE_ID, "limit": limit}  # type: Dict[str, Any]
        if cursor_id is not None and id_param:
            kwargs[id_param] = cursor_id
        if cursor_ts is not None and ts_param:
            kwargs[ts_param] = cursor_ts
        try:
            page = ghl.search_opportunities(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pipeline_sync: GHL opportunities read failed: %s", exc)
            return rows, "ghl_read_failed: %s" % exc
        if page is None:
            return rows, "ghl_token_missing"
        pages += 1
        page_rows = _page_rows(page)
        added = 0
        for row in page_rows:
            rid = row.get("id")
            if rid and rid in seen_ids:
                continue
            if rid:
                seen_ids.add(rid)
            rows.append(row)
            added += 1
        meta = _page_meta(page)
        next_id = meta.get("startAfterId") or meta.get("start_after_id")
        next_ts = meta.get("startAfter") or meta.get("start_after")
        total = meta.get("total")
        if isinstance(total, int):
            more = len(rows) < total
        else:
            # nextPage is a page number, not a cursor, so it is not evidence here.
            more = bool(meta.get("nextPageUrl") or next_id) or len(page_rows) >= limit
        if not page_rows or not more:
            return rows, None
        if pages > 1 and added == 0:
            return rows, (
                "ghl_truncated: GHL re-served a page already read after %d opportunities, so the cursor is "
                "not advancing" % len(rows))
        if not id_param:
            return rows, (
                "ghl_truncated: read %d opportunities and GHL has more, but shared.ghl.GHL."
                "search_opportunities exposes no startAfterId argument" % len(rows))
        if next_id in (None, ""):
            # The meta carried no cursor. startAfterId means "the id to
            # continue after", so ask for the page after the last row rather
            # than reporting a complete pull as truncated (or the reverse).
            # No timestamp is invented to go with it.
            next_id, next_ts = page_rows[-1].get("id"), None
        if next_id in (None, ""):
            return rows, (
                "ghl_truncated: read %d opportunities and GHL has more, but neither the page meta nor the "
                "last row carried an id to continue from" % len(rows))
        cursor_id, cursor_ts = next_id, next_ts
    return rows, "ghl_truncated: stopped at the %d page cap (%d opportunities)" % (max_pages, len(rows))


def fetch_instantly_leads(
    instantly: Instantly,
    emails: Iterable[str],
    campaign_ids: Optional[Iterable[str]] = None,
    positive_filters: Iterable[str] = POSITIVE_LEAD_FILTERS,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Leads for the GHL emails (exact lookup) plus every positive lead per
    campaign (filtered pull, falling back to a full pull if a filter is
    rejected). Read-only (POST /leads/list).

    Returns (leads, note), the same contract ``fetch_ghl_opportunities`` has.
    A read that failed is NEVER reported as "no positive leads": this used to
    log a warning and return ``[]``, so a 503 on POST /leads/list produced an
    empty lead list with no error channel at all. ``run_sync`` then computed a
    clean, empty interest diff AND value fixes whose ``campaign_id`` was None,
    which fall back to the reactivation default -- a wrong dollar value written
    into GHL, the source of truth, on a run reported as "ok". A GHL read
    failure blocked apply; an Instantly one did not.
    """
    campaign_ids = list(campaign_ids) if campaign_ids is not None else [c["id"] for c in settings.CAMPAIGNS.values() if c.get("id")]
    out = {}  # type: Dict[Tuple[str, Optional[str]], Dict[str, Any]]
    failures = []  # type: List[str]
    # A pull that stopped at max_pages is PARTIAL, not empty. Applying a partial
    # lead list as if it were the whole set writes interest statuses and values
    # from a sample - so a cap blocks apply exactly the way a failed read does.
    truncated = []  # type: List[str]

    def _take(lead: Dict[str, Any]) -> None:
        key = (lead_email(lead), lead_campaign(lead))
        if key[0]:
            out[key] = lead

    emails = sorted(set(e for e in (_lower(x) for x in emails) if e))
    for i in range(0, len(emails), 50):
        chunk = emails[i:i + 50]
        try:
            walk = instantly.iterate("leads/list", body={"contacts": chunk, "limit": 100}, max_pages=5)
            for lead in walk:
                _take(lead)
            if getattr(walk, "truncated", False):
                truncated.append("contacts chunk %d" % (i // 50 + 1))
        except InstantlyError as exc:
            logger.warning("pipeline_sync: contacts lookup failed: %s", exc)
            failures.append("contacts chunk %d: %s" % (i // 50 + 1, exc))

    for cid in campaign_ids:
        filtered_ok = True
        for flt in positive_filters:
            try:
                walk = instantly.iterate("leads/list", body={"campaign": cid, "filter": flt, "limit": 100}, max_pages=10)
                for lead in walk:
                    _take(lead)
                if getattr(walk, "truncated", False):
                    truncated.append("campaign %s filter %s" % (cid[:8], flt))
            except InstantlyError as exc:
                logger.warning("pipeline_sync: filter %s rejected for %s (%s); full pull", flt, cid, exc)
                filtered_ok = False
                break
        if not filtered_ok:
            # The filter being rejected is an expected fallback, not a failure;
            # the full pull failing on top of it is.
            try:
                walk = instantly.iterate("leads/list", body={"campaign": cid, "limit": 100}, max_pages=FULL_PULL_MAX_PAGES)
                for lead in walk:
                    _take(lead)
                if getattr(walk, "truncated", False):
                    truncated.append("campaign %s full pull" % cid[:8])
            except InstantlyError as exc:
                logger.warning("pipeline_sync: full pull failed for %s: %s", cid, exc)
                failures.append("campaign %s: %s" % (cid[:8], exc))
    note = None
    if failures:
        note = "instantly_unreadable: %d POST /leads/list read(s) failed (%s); the lead list is incomplete" % (
            len(failures), "; ".join(failures[:3]))
    elif truncated:
        note = "instantly_truncated: %d POST /leads/list pull(s) hit max_pages with the cursor still open (%s); " \
               "the lead list is incomplete" % (len(truncated), "; ".join(truncated[:3]))
    return list(out.values()), note


def snapshot_opportunities_from_ids() -> List[Dict[str, Any]]:
    """config/ids.json ghl.opportunities_observed_<date>: the read-only snapshot
    Lorenzo pulled by hand. Used for REPORTING ONLY while there is no GHL
    token; run_sync never applies changes computed from a snapshot."""
    ghl_ids = settings.IDS.get("ghl") or {}
    rows = []  # type: List[Dict[str, Any]]
    for key, val in ghl_ids.items():
        if key.startswith("opportunities_observed") and isinstance(val, list):
            for row in val:
                rows.append(dict(row, source="ids.json:%s" % key))
    return rows


def load_fixture_leads(path: Path = LEADS_FIXTURE) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else list(data.get("items", []))


# --------------------------------------------------------------------- run
def run_sync(
    dry_run: bool = True,
    now: Optional[datetime] = None,
    instantly: Optional[Instantly] = None,
    ghl: Optional[GHL] = None,
    ghl_opportunities: Optional[List[Dict[str, Any]]] = None,
    instantly_leads: Optional[List[Dict[str, Any]]] = None,
    notify_digest: bool = True,
    replay: bool = False,
) -> Dict[str, Any]:
    """One nightly run. Injected data (``ghl_opportunities`` / ``instantly_leads``)
    skips the network entirely (fixtures, tests).

    ``replay=True`` marks the inputs as a recorded snapshot: nothing is applied,
    not even in shadow, because a September file must never drive a write."""
    now = now or datetime.now(timezone.utc)
    notes = []  # type: List[str]
    ghl = ghl if ghl is not None else GHL()

    sources_readable = True
    block_reason = None  # type: Optional[str]
    if replay:
        sources_readable = False
        block_reason = "fixture_replay"
        notes.append("fixture replay: inputs come from a recorded snapshot, so nothing is applied")
    if ghl_opportunities is None:
        ghl_opportunities, note = fetch_ghl_opportunities(ghl)
        if note:
            notes.append(note)
            sources_readable = False
            block_reason = block_reason or ("ghl_truncated" if note.startswith("ghl_truncated") else "ghl_unreadable")
            if not ghl_opportunities:
                ghl_opportunities = snapshot_opportunities_from_ids()
                if ghl_opportunities:
                    notes.append("GHL opportunities seeded from the config/ids.json snapshot for reporting only; nothing is applied until GHL is readable")
    if instantly_leads is None:
        if instantly is None:
            instantly = default_client()
        instantly_leads, lead_note = fetch_instantly_leads(instantly, [opp_email(o) for o in ghl_opportunities])
        if lead_note:
            # Symmetry with GHL: a source of truth that could not be read in
            # full must not drive writes derived from what came back.
            notes.append(lead_note)
            sources_readable = False
            block_reason = block_reason or (
                "instantly_truncated" if lead_note.startswith("instantly_truncated") else "instantly_unreadable")

    conflicts = []  # type: List[Dict[str, Any]]
    diff = compute_diff(ghl_opportunities, instantly_leads, conflicts=conflicts)
    reverse = compute_reverse(ghl_opportunities, instantly_leads)
    value_fixes = compute_value_fixes(ghl_opportunities, instantly_leads)
    for row in conflicts:
        notes.append("conflict: %s %s stayed at %s; %s" % (row["lead_email"], (row.get("campaign_id") or "")[:8],
                                                           row["from"], row["reason"]))

    no_email = opportunities_without_email(ghl_opportunities)
    reverse_blocked = None  # type: Optional[str]
    if no_email:
        reverse_blocked = (
            "ghl_rows_without_email: %d Sales opportunit%s came back with no contact email, so a lead that already "
            "has one would look missing from GHL and be created a second time; the reverse check is not applied"
            % (len(no_email), "y" if len(no_email) == 1 else "ies"))
        notes.append(reverse_blocked)

    report = {
        "job": JOB_NAME,
        "as_of": now.isoformat(),
        "mode": settings.get_mode(),
        "dry_run": dry_run,
        "ghl_opportunities": len(ghl_opportunities),
        "instantly_leads": len(instantly_leads),
        "diff": diff,
        "reverse": reverse,
        "value_fixes": value_fixes,
        "conflicts": conflicts,
        "reverse_blocked": reverse_blocked,
        "notes": notes,
    }  # type: Dict[str, Any]

    report["apply_blocked"] = None if sources_readable else (block_reason or "ghl_unreadable")
    if dry_run:
        report["applied"] = None
        status = "dry_run"
    elif not sources_readable:
        # GHL is the source of truth; if it (or the Instantly side it is
        # compared against) could not be read in full, nothing computed here is
        # trustworthy enough to push, not even in shadow.
        report["applied"] = {"results": [], "would_do": 0, "done": 0, "error": 0,
                             "skipped": len(diff) + len(reverse) + len(value_fixes), "errors": []}
        status = "skipped_%s" % (block_reason or "ghl_unreadable")
    else:
        applied = apply(diff, instantly, ghl=ghl,
                        reverse=[] if reverse_blocked else reverse,
                        value_fixes=value_fixes)
        if reverse_blocked:
            applied["skipped"] += len(reverse)
        report["applied"] = applied
        if not applied["errors"]:
            status = "ok"
        elif applied["done"] == 0 and applied["would_do"] == 0:
            # Every row that was attempted failed. "partial" reads as healthy
            # enough to pass the deployment runbook's shadow gate; this does not.
            status = "error"
        else:
            status = "partial"

    log_run(JOB_NAME, status, {
        "diff": len(diff), "reverse": len(reverse), "value_fixes": len(value_fixes),
        "conflicts": len(conflicts), "notes": notes, "dry_run": dry_run,
        "would_do": (report["applied"] or {}).get("would_do") if report["applied"] else None,
        "errors": (report["applied"] or {}).get("errors") if report["applied"] else None,
    })
    if notify_digest and not dry_run and (diff or reverse or value_fixes):
        notify("Pipeline sync (%s)" % settings.get_mode(), render_summary(report), priority="default", tags=["arrows_counterclockwise"])
    return report


def _money(value: Optional[float]) -> str:
    """A won or lost opportunity carries no guessed value; say so."""
    if value in (None, ""):
        return "value to be set by Lorenzo"
    return "$%.0f" % float(value)


def render_summary(report: Dict[str, Any]) -> str:
    lines = []  # type: List[str]
    lines.append("Pipeline sync %s | mode=%s | %d GHL opps, %d Instantly leads" % (
        "DRY RUN" if report.get("dry_run") else "run", report.get("mode"),
        report.get("ghl_opportunities", 0), report.get("instantly_leads", 0)))
    for note in report.get("notes") or []:
        lines.append("note: %s" % note)
    lines.append("Interest-status changes (%d):" % len(report.get("diff") or []))
    for row in report.get("diff") or []:
        lines.append("  %s [%s] %s -> %s (%s)" % (row["lead_email"], (row.get("campaign_id") or "")[:8], row["from"], row["to"], row["reason"]))
    for row in report.get("conflicts") or []:
        lines.append("  conflict: %s stayed at %s (%s)" % (row["lead_email"], row["from"], row["reason"]))
    lines.append("Missing GHL opportunities (%d)%s:" % (
        len(report.get("reverse") or []), " NOT APPLIED" if report.get("reverse_blocked") else ""))
    for row in report.get("reverse") or []:
        lines.append("  %s -> %s, %s (%s)" % (row["lead_email"], row["stage"], _money(row.get("monetary_value")), row["offer"]))
    lines.append("Opportunities without a value (%d):" % len(report.get("value_fixes") or []))
    for row in report.get("value_fixes") or []:
        lines.append("  %s -> %s (%s)" % (row["name"], _money(row.get("monetary_value")), row["offer"]))
    applied = report.get("applied")
    if report.get("apply_blocked"):
        why = {
            "ghl_unreadable": "report only; mint the GHL token to let the sync act",
            "ghl_truncated": "the opportunity pull did not reach the end of the Sales pipeline, so the reverse check "
                             "would create duplicates; see runbooks/pipeline_hygiene.md Known gaps",
            "instantly_unreadable": "POST /leads/list failed, so the lead list is incomplete and a value fix could "
                                    "carry the wrong campaign default",
            "instantly_truncated": "a POST /leads/list pull stopped at its page cap with the cursor still open, so "
                                   "the lead list is a sample; raise max_pages or narrow the filter",
            "fixture_replay": "recorded snapshot; a replay never writes",
        }.get(report["apply_blocked"], "report only")
        lines.append("Apply blocked: %s (%s)" % (report["apply_blocked"], why))
    if applied:
        lines.append("Applied: %d done, %d would_do (shadow), %d skipped, %d errors" % (
            applied["done"], applied["would_do"], applied["skipped"], len(applied["errors"])))
    return "\n".join(lines)


def _parse_as_of(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Nightly GHL Sales -> Instantly interest-status mirror (S8)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="compute and print; apply nothing")
    group.add_argument("--now", action="store_true", help="apply through the guarded clients (shadow -> would_do)")
    parser.add_argument("--as-of", help="ISO timestamp to use as 'now' (tests / replay)")
    parser.add_argument("--fixtures", action="store_true", help="use recorded leads instead of the Instantly API")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    kwargs = {}  # type: Dict[str, Any]
    if args.fixtures:
        if args.now:
            # --fixtures is a replay of a recorded September snapshot. Applying
            # from it would write months-old state into whatever GHL/Instantly
            # the environment points at the moment MODE flips to live.
            parser.error("--fixtures is a replay and cannot be applied; use --dry-run --fixtures")
        kwargs["instantly_leads"] = load_fixture_leads()
        kwargs["ghl_opportunities"] = []
        kwargs["ghl"] = GHL(token=None)
        kwargs["replay"] = True
    report = run_sync(dry_run=bool(args.dry_run), now=_parse_as_of(args.as_of), notify_digest=not args.no_notify, **kwargs)
    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        print(render_summary(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
