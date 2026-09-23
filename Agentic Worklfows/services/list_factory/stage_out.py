"""Staging: the CSV, and the ``POST /leads`` record the run would have sent.

Nothing is uploaded. The last stage writes a CSV in Instantly's own column
names and records the intent through ``shared.settings.guard_write``, which in
shadow appends to ``.tmp/shadow_log.jsonl`` and performs no HTTP request.

Why ``guard_write`` is called here rather than a ``shared.instantly`` method:
the library has no ``create_lead`` yet (it was built for the reply engine,
which only ever updates leads). Calling the guard directly keeps this run
inside the same shadow contract; adding ``Instantly.create_lead`` is a
cross-cutting request, not something this brief edits.

The live request this stands for, per Instantly v2 ``POST /leads``:

    {"campaign": "<uuid>", "email": "...", "first_name": "...",
     "last_name": "...", "company_name": "...", "website": "...",
     "personalization": "...", "custom_variables": {...},
     "skip_if_in_workspace": true, "verify_leads_on_import": true}

one call per lead. The batch record carries the count, the CSV path and three
complete per-lead bodies so the shape is reviewable without 3,300 log lines;
``--would-do per-lead`` emits one record per lead when that is what is wanted.
"""
import csv
import logging
import os
from typing import Any, Dict, List, Optional

from shared import settings

from services.list_factory import models

logger = logging.getLogger("list_factory.stage_out")

# Instantly's own field names, plus the custom variables. firstName/companyName
# are what the live campaign copy interpolates (verified read-only 2026-09-21:
# every campaign uses firstName, companyName and personalization; only
# recruiting_outbound also uses specialty).
CSV_COLUMNS = [
    "email", "first_name", "last_name", "company_name", "website", "phone",
    "personalization", "specialty", "buildingType", "metro",
    "advero_source", "advero_icp_confidence", "advero_verify_status",
    "advero_b_variant", "advero_lead_key", "advero_verified_by",
]

SKIP_IF_IN_WORKSPACE = True
VERIFY_LEADS_ON_IMPORT = True


def custom_variables(lead: Dict[str, Any]) -> Dict[str, Any]:
    """The custom variables the campaign copy can interpolate.

    Only non-empty values go in. An empty ``specialty`` in the payload renders
    as an empty string in the email body, which is worse than the variable
    being absent and the send failing the campaign's own variable check.
    """
    out = {}  # type: Dict[str, Any]
    if lead.get("specialty"):
        out["specialty"] = lead["specialty"]
    if lead.get("building_type"):
        out["buildingType"] = lead["building_type"]
    if lead.get("metro"):
        out["metro"] = lead["metro"]
    out["advero_source"] = lead.get("source") or ""
    out["advero_lead_key"] = lead.get("lead_key") or ""
    out["advero_b_variant"] = "yes" if lead.get("b_variant_eligible") else "no"
    if lead.get("verify_status"):
        # The suffix only adds information when the status is not already
        # "catch_all"; without this a catch-all row read "catch_all+catch_all".
        status = lead["verify_status"]
        if lead.get("verify_catch_all") and status != "catch_all":
            status = "%s+catch_all" % status
        out["advero_verify_status"] = status
    if lead.get("verify_source"):
        # Which verifier said so. A replayed row must never be mistaken for a
        # paid one once the CSV has left this machine.
        out["advero_verified_by"] = lead["verify_source"]
    return out


def lead_payload(lead: Dict[str, Any], campaign_id: str) -> Dict[str, Any]:
    """Exactly the body one live ``POST /leads`` call would carry."""
    return {
        "campaign": campaign_id,
        "email": lead.get("email") or "",
        "first_name": lead.get("first_name") or "",
        "last_name": lead.get("last_name") or "",
        "company_name": lead.get("company_name") or "",
        "website": lead.get("website") or "",
        "personalization": lead.get("personalization") or "",
        "custom_variables": custom_variables(lead),
        "skip_if_in_workspace": SKIP_IF_IN_WORKSPACE,
        "verify_leads_on_import": VERIFY_LEADS_ON_IMPORT,
    }


def csv_row(lead: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "email": lead.get("email") or "",
        "first_name": lead.get("first_name") or "",
        "last_name": lead.get("last_name") or "",
        "company_name": lead.get("company_name") or "",
        "website": lead.get("website") or "",
        "phone": lead.get("phone") or "",
        "personalization": lead.get("personalization") or "",
        "specialty": lead.get("specialty") or "",
        "buildingType": lead.get("building_type") or "",
        "metro": lead.get("metro") or "",
        "advero_source": lead.get("source") or "",
        "advero_icp_confidence": lead.get("icp_confidence"),
        "advero_verify_status": lead.get("verify_status") or "",
        "advero_b_variant": "yes" if lead.get("b_variant_eligible") else "no",
        "advero_lead_key": lead.get("lead_key") or "",
        "advero_verified_by": lead.get("verify_source") or "",
    }


def csv_data_rows(path: str) -> int:
    """How many data rows the CSV at ``path`` already holds. -1 when absent."""
    if not os.path.exists(path):
        return -1
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return max(0, sum(1 for _ in csv.reader(fh)) - 1)
    except (OSError, IOError, csv.Error):
        return -1


class StagedCsvWouldBeEmptied(Exception):
    """Refusing to replace a staged list with a header-only file."""


def write_csv(leads: List[Dict[str, Any]], path: str, allow_empty: bool = False) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    if not leads and not allow_empty:
        existing = csv_data_rows(path)
        if existing > 0:
            # os.replace on a header-only temp file silently deleted the week's
            # list. A resume of a finished run had nothing pending, so `ready`
            # was empty, and the run still reported ok.
            raise StagedCsvWouldBeEmptied(
                "refusing to overwrite %s (%d staged rows) with an empty list" % (path, existing)
            )
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow(csv_row(lead))
    os.replace(tmp, path)
    return path


def stage(
    leads: List[Dict[str, Any]],
    campaign_key: str,
    csv_path: str,
    mode: str = "batch",
    campaigns: Optional[Dict[str, Any]] = None,
    include_catch_all: bool = True,
) -> Dict[str, Any]:
    """Write the CSV and record the upload intent. Uploads nothing.

    A lead without a verified address never reaches here: ``staged`` is defined
    as "has an email, passed suppression, has a personalization line".

    ``include_catch_all=False`` stages only CONFIRMED mailboxes. A catch-all
    domain accepts every local part at SMTP time, so for an address the factory
    guessed there is no evidence the mailbox exists; about a quarter of real
    checks come back that way.
    """
    campaigns = campaigns if campaigns is not None else settings.CAMPAIGNS
    campaign = campaigns.get(campaign_key) or {}
    campaign_id = campaign.get("id")
    if not campaign_id:
        raise ValueError(
            "unknown campaign key %r; config/ids.json knows %s"
            % (campaign_key, ", ".join(sorted(campaigns)))
        )

    ready = []
    dropped = 0
    held_catch_all = 0
    for lead in leads:
        if models.is_rejected(lead):
            dropped += 1
            continue
        if not lead.get("email") or not lead.get("personalization"):
            dropped += 1
            continue
        if not include_catch_all and lead.get("verify_catch_all"):
            held_catch_all += 1
            dropped += 1
            continue
        ready.append(lead)

    write_csv(ready, csv_path)
    payloads = [lead_payload(lead, campaign_id) for lead in ready]

    records = []
    if mode == "per-lead":
        for payload in payloads:
            records.append(settings.guard_write("instantly", "create_lead", payload))
    else:
        records.append(settings.guard_write("instantly", "create_lead_batch", {
            "endpoint": "POST /leads",
            "calls": len(payloads),
            "campaign": campaign_id,
            "campaign_key": campaign_key,
            "skip_if_in_workspace": SKIP_IF_IN_WORKSPACE,
            "verify_leads_on_import": VERIFY_LEADS_ON_IMPORT,
            "csv": csv_path,
            "sample": payloads[:3],
        }))

    for lead in ready:
        models.advance(lead, models.STAGED)

    catch_all = sum(1 for lead in ready if lead.get("verify_catch_all"))
    return {
        "campaign_key": campaign_key,
        "campaign_id": campaign_id,
        "staged": len(ready),
        "dropped": dropped,
        "catch_all_staged": catch_all,
        "catch_all_share": round(float(catch_all) / len(ready), 4) if ready else None,
        "catch_all_excluded": held_catch_all,
        "csv": csv_path,
        "b_variant_eligible": sum(1 for lead in ready if lead.get("b_variant_eligible")),
        "would_do_records": len(records),
        "shadow": all(record.get("shadow") for record in records) if records else True,
    }
