"""The legacy Instantly -> CRM stage mapping, kept only to find what it got wrong.

``determine_crm_stage`` below is the function ``execution/instantly_lead_sync.py``
ran on Modal (``advero-lead-sync``) from 2026-03-04, copied verbatim. Do not
fix it: the correction change-set needs to know exactly what stage the old
sync wrote for a lead, bugs included.

``legacy_stage_and_branch`` returns the same stage plus the name of the branch
that produced it. Four branches are bugs (BUG_BRANCHES):

- ``bounced_esp_code``: ``esp_code`` 3 read as "bounced". esp_code is the
  recipient's email provider (3 = Zoho), so every Zoho-hosted lead went to
  "Closed - Lost".
- ``delivered_esp_code``: ``esp_code`` 2 read as "delivered". 2 = Microsoft, so
  active Microsoft-hosted leads went to "Contacted" before any email.
- ``completed_as_replied``: lead ``status`` 3 read as "replied". 3 = Completed
  (the sequence finished), so no-reply leads went to "Replied - Neutral".
- ``ooo_as_replied``: a reply with ``lt_interest_status`` 0 counted as a neutral
  reply. 0 = Out of Office, an auto-reply.
"""
from typing import Dict, Optional, Tuple

BUG_BRANCHES = frozenset(("bounced_esp_code", "delivered_esp_code", "completed_as_replied", "ooo_as_replied"))

BRANCHES = (
    "replied_positive", "replied_not_interested", "replied_wrong_person", "ooo_as_replied",
    "completed_as_replied", "replied_neutral", "interest_positive", "interest_not_interested",
    "interest_wrong_person", "bounced_status", "bounced_esp_code", "delivered_esp_code", "none",
)


# ---- verbatim copy of the legacy function (do not edit) --------------------
def determine_crm_stage(lead: Dict) -> Optional[str]:
    status = lead.get("status", 0)
    esp_code = lead.get("esp_code", 0)
    reply_count = lead.get("email_reply_count", 0)
    interest = lead.get("lt_interest_status")

    # Replied — check sentiment via lt_interest_status
    if status == 3 or reply_count > 0:
        if interest == 1:
            return "Replied - Positive"
        elif interest == -1:
            return "Closed - Lost"  # Replied saying not interested
        elif interest == -2:
            return "Closed - Lost"  # Wrong person
        else:
            return "Replied - Neutral"  # Replied but no clear sentiment (0 or None)

    # Interest set without a reply (manually tagged in Instantly)
    if interest == 1:
        return "Replied - Positive"
    if interest == -1:
        return "Closed - Lost"
    if interest == -2:
        return "Closed - Lost"

    # Bounced
    if status == -1 or esp_code == 3:
        return "Closed - Lost"

    # Successfully delivered email — only then mark as Contacted
    if esp_code == 2 and status == 1:
        return "Contacted"

    return None
# ---- end of verbatim copy --------------------------------------------------


legacy_determine_crm_stage = determine_crm_stage


def legacy_stage_and_branch(lead: Dict) -> Tuple[Optional[str], str]:
    """(stage the legacy sync wrote, branch that fired). Same stage as
    ``determine_crm_stage`` for every lead it accepts; an ``email_reply_count``
    of None (which made the legacy function raise) is read as 0 here."""
    status = lead.get("status", 0)
    esp_code = lead.get("esp_code", 0)
    reply_count = lead.get("email_reply_count", 0) or 0
    interest = lead.get("lt_interest_status")

    if status == 3 or reply_count > 0:
        if interest == 1:
            return "Replied - Positive", "replied_positive"
        if interest == -1:
            return "Closed - Lost", "replied_not_interested"
        if interest == -2:
            return "Closed - Lost", "replied_wrong_person"
        if reply_count > 0 and interest == 0:
            return "Replied - Neutral", "ooo_as_replied"
        if status == 3 and reply_count == 0:
            return "Replied - Neutral", "completed_as_replied"
        return "Replied - Neutral", "replied_neutral"

    if interest == 1:
        return "Replied - Positive", "interest_positive"
    if interest == -1:
        return "Closed - Lost", "interest_not_interested"
    if interest == -2:
        return "Closed - Lost", "interest_wrong_person"

    if status == -1:
        return "Closed - Lost", "bounced_status"
    if esp_code == 3:
        return "Closed - Lost", "bounced_esp_code"

    if esp_code == 2 and status == 1:
        return "Contacted", "delivered_esp_code"

    return None, "none"


def is_bug_branch(branch: str) -> bool:
    return branch in BUG_BRANCHES
