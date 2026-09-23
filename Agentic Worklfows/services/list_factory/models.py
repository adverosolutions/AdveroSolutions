"""Lead record, stage vocabulary and the normalisers every stage shares.

A lead is a plain dict, not a dataclass, because the whole run state is
persisted as JSON between stages and round-trips through
``shared.store.JsonFileStore``. The key names here are the schema.
"""
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# ------------------------------------------------------------------ stages
# The pipeline advances a lead through these in order. STAGE_ORDER is what
# makes the run resumable: a lead is re-processed by a stage only when its own
# stage index is below that stage's index, so a crash in VERIFY never re-runs
# (and never re-pays for) OWNER.
SOURCED = "sourced"
ICP = "icp"
OWNER = "owner"
PATTERNS = "patterns"
VERIFIED = "verified"
FINDER = "finder"
SUPPRESSED_CHECK = "suppression"
PERSONALIZED = "personalized"
STAGED = "staged"

STAGE_ORDER = [
    SOURCED,
    ICP,
    OWNER,
    PATTERNS,
    VERIFIED,
    FINDER,
    SUPPRESSED_CHECK,
    PERSONALIZED,
    STAGED,
]
STAGE_INDEX = dict((name, i) for i, name in enumerate(STAGE_ORDER))

# A lead that reaches one of these is finished and costs nothing further. It
# stays in the state file so a resumed run does not re-source and re-pay for it.
REJECTED = "rejected"

REJECT_ICP = "icp_miss"
REJECT_NO_DOMAIN = "no_domain"
REJECT_NO_OWNER = "no_owner"
REJECT_NO_CANDIDATES = "no_email_candidates"
REJECT_UNVERIFIABLE = "unverifiable"
REJECT_SUPPRESSED = "suppressed"
REJECT_COPY = "copy_rules"
REJECT_BUDGET = "halted_over_budget"

# Not a rejection. A lead the run was not ALLOWED to pay for (the paid gate was
# closed) or could not get an answer about (the verifier errored) is held where
# it stands, with a note, so the next pass picks it up from exactly here.
# ``reject()`` cannot express that: it is terminal, ``stage_at_least`` returns
# True for a rejected lead, and ``RunState.pending`` filters it out for good.
HOLD_GATE = "paid_gate_closed"
HOLD_VERIFY_ERROR = "verifier_error"


def hold(lead: Dict[str, Any], reason: str, detail: str = "") -> Dict[str, Any]:
    """Park a lead without rejecting it. Reversible: ``release`` clears it."""
    lead["blocked_by_gate"] = reason
    if detail:
        lead["blocked_detail"] = detail
    lead.setdefault("stage_history", []).append("held:%s" % reason)
    return lead


def is_held(lead: Dict[str, Any]) -> bool:
    return bool(lead.get("blocked_by_gate"))


def release(lead: Dict[str, Any]) -> bool:
    """Clear a hold so the next pass re-attempts the lead. True when it did."""
    if not lead.get("blocked_by_gate"):
        return False
    lead.pop("blocked_by_gate", None)
    lead.pop("blocked_detail", None)
    return True


def stage_at_least(lead: Dict[str, Any], stage: str) -> bool:
    """True when ``lead`` has already been through ``stage``."""
    if lead.get("stage") == REJECTED:
        return True
    return STAGE_INDEX.get(lead.get("stage") or SOURCED, 0) >= STAGE_INDEX[stage]


def advance(lead: Dict[str, Any], stage: str, note: Optional[str] = None) -> Dict[str, Any]:
    lead["stage"] = stage
    history = lead.setdefault("stage_history", [])
    history.append(stage if not note else "%s:%s" % (stage, note))
    return lead


def reject(lead: Dict[str, Any], reason: str, detail: str = "") -> Dict[str, Any]:
    """Terminal. ``reason`` is one of the REJECT_* constants; it is what the
    ledger and the run summary count by."""
    lead["stage"] = REJECTED
    lead["reject_reason"] = reason
    if detail:
        lead["reject_detail"] = detail
    lead.setdefault("stage_history", []).append("rejected:%s" % reason)
    return lead


def is_rejected(lead: Dict[str, Any]) -> bool:
    return lead.get("stage") == REJECTED


def is_live_candidate(lead: Dict[str, Any]) -> bool:
    """Still moving through the pipeline (not rejected, not finished)."""
    return not is_rejected(lead) and lead.get("stage") != STAGED


# ------------------------------------------------------------- normalisers
_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

FREE_MAIL_HINT = (
    "gmail.com", "yahoo.com", "hotmail.com", "aol.com", "outlook.com",
    "icloud.com", "me.com", "msn.com", "comcast.net", "live.com",
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return _WS.sub(" ", str(value)).strip()


def domain_of(website_or_email: Any) -> str:
    """Bare registrable-ish domain from a URL or an email. '' when there is none.

    Deliberately shares the www-stripping rule with
    ``execution/generate_email_patterns.extract_domain`` so a domain derived
    here and a domain derived there are the same string.
    """
    raw = clean_text(website_or_email).lower()
    if not raw:
        return ""
    if "@" in raw and "://" not in raw:
        raw = raw.rsplit("@", 1)[-1]
    if "://" not in raw:
        raw = "http://" + raw
    try:
        netloc = urlparse(raw).netloc
    except ValueError:
        return ""
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if not netloc or "." not in netloc:
        return ""
    return netloc


def slug(value: Any) -> str:
    return _NON_ALNUM.sub("-", clean_text(value).lower()).strip("-")


def lead_key(record: Dict[str, Any]) -> str:
    """Stable identity for dedupe and for resume.

    Domain first (one company, one outreach), then company+city, so two
    listings of the same business under slightly different names in the same
    city collapse, while two franchisees in different cities do not.
    """
    dom = record.get("domain") or domain_of(record.get("website"))
    if dom:
        return "d:%s" % dom
    return "c:%s|%s" % (slug(record.get("company_name")), slug(record.get("city")))


def searchable_text(lead: Dict[str, Any]) -> str:
    """Everything a keyword rule or the model should look at, lowercased."""
    parts = [
        lead.get("company_name"),
        lead.get("industry"),
        lead.get("keywords"),
        lead.get("description"),
        lead.get("headline"),
        lead.get("title"),
        lead.get("categories"),
        lead.get("website"),
    ]
    return " ".join(clean_text(p).lower() for p in parts if p)


def new_lead(record: Dict[str, Any], source: str, shard: str = "") -> Dict[str, Any]:
    """Normalise one raw source row into the factory's schema."""
    website = clean_text(record.get("website") or record.get("company_website") or record.get("url"))
    dom = domain_of(website) or domain_of(record.get("company_domain")) or domain_of(record.get("email"))
    lead = {
        "source": source,
        "source_shard": shard,
        "company_name": clean_text(record.get("company_name") or record.get("name") or record.get("title")),
        "website": website,
        "domain": dom,
        "phone": clean_text(record.get("phone") or record.get("company_phone")),
        "city": clean_text(record.get("city") or record.get("company_city")),
        "state": clean_text(record.get("state") or record.get("company_state")),
        "country": clean_text(record.get("country") or record.get("company_country") or "United States"),
        "industry": clean_text(record.get("industry")),
        "keywords": clean_text(record.get("keywords") or record.get("categories")),
        "description": clean_text(record.get("description") or record.get("company_description")),
        "headline": clean_text(record.get("headline")),
        "company_size": record.get("company_size"),
        "rating": record.get("rating"),
        "reviews": record.get("reviews") or record.get("review_count"),
        # owner
        "first_name": clean_text(record.get("first_name")),
        "last_name": clean_text(record.get("last_name")),
        "title": clean_text(record.get("job_title") or record.get("title_role") or record.get("seniority_level")),
        "owner_confidence": clean_text(record.get("owner_confidence")) or ("HIGH" if record.get("first_name") else ""),
        "owner_source": "source_row" if record.get("first_name") else "",
        "research": clean_text(record.get("research")),
        # contact
        "email_candidates": [],
        "email": "",
        "verify_status": "",
        "verify_catch_all": False,
        "verify_source": "",
        # scoring / copy / triggers
        "icp_verdict": "",
        "icp_confidence": None,
        "icp_reason": "",
        "icp_decided_by": "",
        "personalization": "",
        "personalization_model": "",
        "building_type": "",
        "metro": "",
        "specialty": "",
        "b_variant_eligible": False,
        "b_variant_reason": "",
        # bookkeeping
        "stage": SOURCED,
        "stage_history": [SOURCED],
        "reject_reason": "",
    }
    lead["lead_key"] = lead_key(lead)
    return lead


def dedupe(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """First occurrence wins, on ``lead_key``."""
    seen = set()
    out = []
    for lead in leads:
        key = lead.get("lead_key") or lead_key(lead)
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out
