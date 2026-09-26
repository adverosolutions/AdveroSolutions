"""Change-set: correct CRM Stage values the legacy Instantly -> CRM sync mislabelled.

    cd "Agentic Worklfows"
    python3 changesets/crm_stage_correction/apply_crm_stage_correction.py --dry-run
    python3 changesets/crm_stage_correction/apply_crm_stage_correction.py --dry-run --mx
    python3 changesets/crm_stage_correction/apply_crm_stage_correction.py --dry-run \
        --crm-snapshot crm.json --leads-snapshot leads.json
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/crm_stage_correction/apply_crm_stage_correction.py \
        --apply --plan-file .tmp/crm_stage_correction/plan_<stamp>.json
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/crm_stage_correction/apply_crm_stage_correction.py \
        --restore changesets/backups/crm_stage_correction_before_<stamp>.json

Runbook: runbooks/lead_sync_esp_code_fix.md.

``--dry-run`` (the default) reads the CRM tabs ("HVAC Leads", "Roofing Leads"
unless ``--tab`` is given) with the read-only Sheets scope and every Instantly
lead in the workspace, works out which rows the legacy sync set through one of
its four bugs (see legacy_mapping.py), prints the plan and saves it as
``.tmp/crm_stage_correction/plan_<stamp>.json``. The plan records the
spreadsheet id it was read from (null for an offline snapshot, which can never
be applied live). It never writes to the sheet, and its Job_Log row goes to a
scratch file.

``--apply --plan-file`` writes the plan (live only), in this order:

1. refuse a plan whose spreadsheet id is null or is not the live sheet's;
2. read every tab and work out the writes; a row whose email or Stage no
   longer matches the plan, and every row of a tab whose header lacks
   "Stage", "Email" or "Last Updated", is skipped;
3. print the writes and ask for the row count (unless ``--yes``);
4. read every tab AGAIN and work the writes out again; if any (tab, row,
   email, stage before, stage after, columns) differs from what was
   confirmed, write nothing (no backup, no batch_update) and exit 2;
5. guard_write, then write the before-values from that fresh read to
   ``changesets/backups/`` (no backup, no write);
6. one batch_update per tab, stopping at the first error. Once any
   batch_update has been sent the backup is the unsuffixed, restorable
   rollback point, recording which tabs were sent, confirmed or not sent and,
   for a tab whose batch_update raised, what a re-read of it shows.

``--restore`` follows the same order (sheet id check, read, confirm, re-read
and compare, a ``.prerestore`` copy, write) and puts the before-values back
where the row still holds the corrected stage.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent.parent
EXECUTION_DIR = BASE_DIR / "execution"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pytz  # noqa: E402

from shared import settings  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.paths import tmp_dir  # noqa: E402
from changesets import rollback as R  # noqa: E402
from changesets.crm_stage_correction.legacy_mapping import (  # noqa: E402
    BUG_BRANCHES, legacy_stage_and_branch)

logger = logging.getLogger("changesets.crm_stage_correction")

JOB = "crm_stage_correction"
SCRIPT = "crm_stage_correction"
SYSTEM = "google_sheets"
ACTION = "crm_stage_correction"
RESTORE_ACTION = "crm_stage_correction_restore"
BACKUP_DIR = BASE_DIR / "changesets" / "backups"
PLAN_SUBDIR = "crm_stage_correction"
PLAN_SCHEMA = 1
CENTRAL = pytz.timezone("US/Central")
SHEET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
READONLY_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2
EXIT_API = 3

UNCONTACTED = "New/Uncontacted"
CLOSED_LOST = "Closed - Lost"
REASON_DUPLICATE = "duplicate_email_in_tab"
REASON_ZOHO_MX = "zoho_mx_no_instantly_record"
REASON_OPTED_OUT = "lead_unsubscribed_or_skipped"

# Header name -> 0-based fallback column, as the legacy sync does (A, E, P, Q).
FALLBACK_COLS = OrderedDict((("Stage", 0), ("Email", 4), ("Last Updated", 15), ("Notes", 16)))
# apply/restore write only tabs whose header names all three (never by fixed column).
REQUIRED_COLS = ("Stage", "Email", "Last Updated")

# The legacy sync went live on Modal on this date and always wrote Last Updated
# together with Stage, so a row last updated before it was not set by that sync.
LEGACY_SYNC_DEPLOYED = date(2026, 3, 4)
SHEET_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d")
# Lead status that makes "New/Uncontacted" a bad guess: -2 unsubscribed, -3 skipped (may be blocklisted).
OPTED_OUT_STATUS = {-2: "lead_status_-2_unsubscribed", -3: "lead_status_-3_skipped"}


class SourceError(Exception):
    """A live input (sheet or Instantly) could not be read."""


# =========================================================================
# The fixed sync (execution/instantly_lead_sync.py)
# =========================================================================

_SYNC = {}  # type: Dict[str, Any]


def sync_module() -> Any:
    """Import execution/instantly_lead_sync.py the way it imports itself.

    That module calls python-dotenv's load_dotenv() at import, which (unlike
    shared.settings.load_env) would take MODE / ALLOW_LIVE_WRITES from a .env
    file. The gate flags are put back to what they were before the import.
    """
    if "mod" not in _SYNC:
        if str(EXECUTION_DIR) not in sys.path:
            sys.path.insert(0, str(EXECUTION_DIR))
        preset = dict((k, os.environ.get(k)) for k in settings.GATE_FLAGS)
        try:
            import instantly_lead_sync as mod  # noqa: E402
        finally:
            for key, value in preset.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        _SYNC["mod"] = mod
    return _SYNC["mod"]


def stage_order() -> List[str]:
    return list(sync_module().STAGE_ORDER)


def default_tabs() -> List[str]:
    return list(OrderedDict.fromkeys(sync_module().CAMPAIGN_TO_SHEET.values()))


def new_stage(lead: Dict[str, Any]) -> Optional[str]:
    return sync_module().determine_crm_stage(lead)


def stage_index(stage: Optional[str]) -> int:
    order = stage_order()
    return order.index(stage) if stage in order else -1


def sync_should_update(current: str, proposed: str) -> bool:
    fn = getattr(sync_module(), "should_update", None)
    if fn is not None:
        return bool(fn(current, proposed))
    terminal = getattr(sync_module(), "TERMINAL_STAGES", set())
    return current not in terminal and stage_index(proposed) > stage_index(current)


# =========================================================================
# Sheet helpers
# =========================================================================

def norm_email(value: Any) -> str:
    return str(value or "").strip().lower()


def cell(row: List[Any], idx: int) -> str:
    return str(row[idx]) if 0 <= idx < len(row) and row[idx] is not None else ""


def columns(header: List[Any]) -> Dict[str, int]:
    return header_check(header)[0]


def header_check(header: List[Any]) -> Tuple[Dict[str, int], List[str], List[str]]:
    """(columns, missing, ambiguous) for a header row.

    A column named in the header is used where it is. A missing one falls back
    to the legacy sync's fixed column (A, E, P, Q) for READING only, and only
    when that column has no other header name; otherwise it is "ambiguous" and
    its index is -1 (reads as empty). apply/restore never write a tab with a
    missing required column (see header_problem)."""
    names = [str(h).strip() for h in (header or [])]
    cols, missing, ambiguous = {}, [], []  # type: Dict[str, int], List[str], List[str]
    for name, fb in FALLBACK_COLS.items():
        if name in names:
            cols[name] = names.index(name)
            continue
        missing.append(name)
        if fb < len(names) and names[fb] != "":
            ambiguous.append(name)
            cols[name] = -1
        else:
            cols[name] = fb
    return cols, missing, ambiguous


def header_problem(header: List[Any]) -> Optional[str]:
    """Why apply/restore refuse to write this tab, or None."""
    missing = [n for n in header_check(header)[1] if n in REQUIRED_COLS]
    if not missing:
        return None
    return ("header has no %s column, and this script never writes by fixed column"
            % " / ".join(repr(m) for m in missing))


def col_letter(idx: int) -> str:
    """0-based column index -> A1 letters (0 -> A, 25 -> Z, 26 -> AA)."""
    n, letters = idx + 1, ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def col_index(letters: str) -> int:
    """A1 letters -> 0-based column index (A -> 0, AA -> 26)."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def today_central(now: datetime) -> str:
    """Last Updated in the sync's format: today in US/Central, %Y-%m-%d."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(CENTRAL).strftime("%Y-%m-%d")


def parse_sheet_date(value: Any) -> Optional[date]:
    """A Last Updated cell as a date (the sync writes %Y-%m-%d; Sheets may show
    it as m/d/yyyy), or None."""
    text = str(value or "").strip()
    if not text:
        return None
    head = text.split()[0]
    for fmt in SHEET_DATE_FORMATS:
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            pass
    return None


def same_sheet_date(a: Any, b: Any) -> bool:
    if str(a or "").strip() == str(b or "").strip():
        return True
    da, db = parse_sheet_date(a), parse_sheet_date(b)
    return da is not None and da == db


def created_date(ts: Any) -> Optional[date]:
    """An Instantly ISO timestamp (UTC) as a US/Central date, the zone the sync
    writes Last Updated in; None when missing or unreadable."""
    text = str(ts or "").strip()
    if not text:
        return None
    try:
        dt = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.astimezone(CENTRAL).date()


def sheet_id_of(spreadsheet: Any) -> Optional[str]:
    """The spreadsheet's id (gspread's Spreadsheet.id is the key it was opened by)."""
    sid = getattr(spreadsheet, "id", None)
    return str(sid) if sid else None


def open_spreadsheet(scopes: Optional[List[str]] = None) -> Any:
    """The CRM spreadsheet via gspread, authenticated like the sync
    (GOOGLE_CREDENTIALS_JSON, or credentials.json beside the repo or in cwd).
    ``scopes`` defaults to read/write; the dry-run passes READONLY_SCOPES."""
    scopes = list(scopes or SHEET_SCOPES)
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SourceError("GOOGLE_SHEET_ID is not set")
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        from shared.job_log import _service_account_info

        info = _service_account_info()
        if info:
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        elif os.path.isfile("credentials.json"):
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        else:
            raise SourceError("no service account (GOOGLE_CREDENTIALS_JSON or credentials.json)")
        return gspread.authorize(creds).open_by_key(sheet_id)
    except SourceError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SourceError("could not open the CRM sheet: %s" % str(exc)[:300])


def read_tabs(spreadsheet: Any, tabs: List[str], out: Callable[[str], None]) -> Tuple[Dict[str, Any], Dict[str, List[List[str]]]]:
    """(worksheet by tab, values by tab). A tab that cannot be read is reported and left out."""
    sheets, values = OrderedDict(), OrderedDict()  # type: Dict[str, Any], Dict[str, List[List[str]]]
    for tab in tabs:
        try:
            ws = spreadsheet.worksheet(tab)
            values[tab] = [list(r) for r in (ws.get_all_values() or [])]
            sheets[tab] = ws
        except Exception as exc:  # noqa: BLE001
            out("WARNING: tab %r could not be read (%s); it is left out" % (tab, str(exc)[:160]))
    return sheets, values


def load_crm_snapshot(path: str, tabs: List[str], out: Callable[[str], None]) -> Dict[str, List[List[str]]]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("a CRM snapshot is {\"<tab>\": [[header...], [row...]]}")
    result = OrderedDict()  # type: Dict[str, List[List[str]]]
    for tab in tabs:
        if tab not in data:
            out("WARNING: tab %r is not in %s; it is left out" % (tab, path))
            continue
        result[tab] = [[str(c) if c is not None else "" for c in row] for row in data[tab]]
    return result


def load_leads_snapshot(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("a leads snapshot is {\"items\": [...]} or a list of lead objects")
    return [i for i in items if isinstance(i, dict)]


def live_leads() -> List[Dict[str, Any]]:
    """Every lead in the workspace (no campaign filter)."""
    sync_module()  # puts execution/ on sys.path
    try:
        from instantly_api import InstantlyAPI

        return list(InstantlyAPI().list_leads())
    except Exception as exc:  # noqa: BLE001
        raise SourceError("could not list Instantly leads: %s" % str(exc)[:300])


def dig_mx(domain: str) -> List[str]:
    """MX hosts for a domain via ``dig +short MX``; [] when dig fails."""
    try:
        proc = subprocess.run(["dig", "+short", "MX", domain], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("dig MX %s failed: %s", domain, exc)
        return []
    hosts = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        if parts:
            hosts.append(parts[-1].rstrip(".").lower())
    return hosts


# =========================================================================
# Planning
# =========================================================================

def lead_evidence(lead: Dict[str, Any]) -> Dict[str, Any]:
    old, branch = legacy_stage_and_branch(lead)
    summary = lead.get("status_summary")
    last = (summary.get("lastStep") or {}) if isinstance(summary, dict) else {}
    return {
        "id": lead.get("id"),
        "campaign": lead.get("campaign"),
        "status": lead.get("status"),
        "esp_code": lead.get("esp_code"),
        "email_reply_count": lead.get("email_reply_count"),
        "lt_interest_status": lead.get("lt_interest_status"),
        "timestamp_created": lead.get("timestamp_created"),
        "timestamp_last_contact": lead.get("timestamp_last_contact"),
        "last_step_timestamp_executed": last.get("timestamp_executed") if isinstance(last, dict) else None,
        "legacy_stage": old,
        "legacy_branch": branch,
        "new_stage": new_stage(lead),
    }


def candidate(current: str, evidence: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The correction for a row at ``current``, or None.

    A row qualifies when one of its leads went through a bug branch that
    produces exactly ``current`` and no lead explains ``current`` through a
    real signal (a status -1 bounce, a tagged "not interested", ...).
    """
    hits = [e for e in evidence if e["legacy_branch"] in BUG_BRANCHES and e["legacy_stage"] == current]
    if not hits:
        return None
    if any(e["legacy_branch"] not in BUG_BRANCHES and e["legacy_stage"] == current for e in evidence):
        return None
    news = [e["new_stage"] for e in evidence if e["new_stage"]]
    if news:
        best, unknown = max(news, key=stage_index), False
    else:
        best, unknown = UNCONTACTED, True
    if best == current:
        return None
    return {"reason": hits[0]["legacy_branch"], "proposed_stage": best, "prior_stage_unknown": unknown,
            "created": [e.get("timestamp_created") for e in hits]}


def _entry(tab: str, rownum: int, row: List[str], cols: Dict[str, int], email: str) -> Dict[str, Any]:
    notes = cell(row, cols["Notes"]).strip()
    return OrderedDict((
        ("tab", tab), ("row", rownum), ("email", email),
        ("current_stage", cell(row, cols["Stage"])),
        ("last_updated", cell(row, cols["Last Updated"])),
        ("notes", notes),
        ("proposed_stage", None), ("reason", None),
        ("confidence", "high" if not notes else "review"),
        ("review_reasons", []),
        ("prior_stage_unknown", False),
        ("evidence", []),
    ))


def review_reasons(entry: Dict[str, Any], created: List[Any], notes_column_missing: bool = False) -> List[str]:
    """Why a person should look at this row before it is written ([] = none).

    ``created`` holds the timestamp_created of the leads that explain the row's
    current Stage (the legacy sync could only have set it after one existed)."""
    reasons = []  # type: List[str]
    if entry.get("notes"):
        reasons.append("notes")
    if notes_column_missing:
        reasons.append("no_notes_column")
    raw = str(entry.get("last_updated") or "").strip()
    updated = parse_sheet_date(raw)
    if not raw:
        reasons.append("last_updated_empty")
    elif updated is None:
        reasons.append("last_updated_unreadable")
    else:
        if updated < LEGACY_SYNC_DEPLOYED:
            reasons.append("last_updated_before_legacy_sync_deploy")
        dates = [d for d in (created_date(c) for c in created) if d is not None]
        if dates and updated < min(dates):
            reasons.append("last_updated_before_lead_created")
    if entry.get("prior_stage_unknown"):
        reasons.append("prior_stage_unknown")
    return reasons


def _finish(entry: Dict[str, Any], created: List[Any], notes_column_missing: bool,
            extra: Optional[List[str]] = None) -> Dict[str, Any]:
    reasons = review_reasons(entry, created, notes_column_missing) + list(extra or [])
    entry["review_reasons"] = reasons
    entry["confidence"] = "review" if reasons else "high"
    return entry


def build_plan(crm: Dict[str, List[List[str]]], leads: List[Dict[str, Any]], now: datetime,
               mx: bool = False, resolver: Optional[Callable[[str], List[str]]] = None,
               sources: Optional[Dict[str, Any]] = None, spreadsheet_id: Optional[str] = None) -> Dict[str, Any]:
    leads_by_email = OrderedDict()  # type: Dict[str, List[Dict[str, Any]]]
    for lead in leads:
        email = norm_email(lead.get("email"))
        if email:
            leads_by_email.setdefault(email, []).append(lead)
    resolver = resolver or dig_mx
    mx_cache = {}  # type: Dict[str, List[str]]

    entries, review = [], []  # type: List[Dict[str, Any]], List[Dict[str, Any]]
    would_move = OrderedDict()  # type: Dict[str, int]
    header_warnings = OrderedDict()  # type: Dict[str, Dict[str, Any]]
    rows_with_email, emails_matched = 0, set()
    for tab, values in crm.items():
        header = values[0] if values else []
        cols, missing, ambiguous = header_check(header)
        would_move[tab] = 0
        if missing:
            left_out = [m for m in ambiguous if m in REQUIRED_COLS]
            header_warnings[tab] = OrderedDict((
                ("missing", missing),
                ("fallback_used", dict((m, col_letter(FALLBACK_COLS[m])) for m in missing if m not in ambiguous)),
                ("ambiguous", ambiguous),
                ("left_out", bool(left_out)),
                ("apply_refuses_tab", any(m in REQUIRED_COLS for m in missing)),
            ))
            if left_out:
                continue
        notes_missing = "Notes" in missing
        by_email = OrderedDict()  # type: Dict[str, List[Tuple[int, List[str]]]]
        for rownum, row in enumerate(values[1:], start=2):
            email = norm_email(cell(row, cols["Email"]))
            if email:
                by_email.setdefault(email, []).append((rownum, row))
                rows_with_email += 1
        for email, rows in by_email.items():
            lead_list = leads_by_email.get(email) or []
            if not lead_list:
                if mx:
                    for rownum, row in rows:
                        if cell(row, cols["Stage"]) != CLOSED_LOST or "@" not in email:
                            continue
                        domain = email.split("@", 1)[1]
                        if domain not in mx_cache:
                            mx_cache[domain] = [h.lower() for h in (resolver(domain) or [])]
                        if any("zoho" in h for h in mx_cache[domain]):
                            e = _entry(tab, rownum, row, cols, email)
                            e["reason"] = REASON_ZOHO_MX
                            e["evidence"] = [{"domain": domain, "mx_hosts": mx_cache[domain]}]
                            review.append(_finish(e, [], notes_missing))
                continue
            emails_matched.add(email)
            evidence = [lead_evidence(lead) for lead in lead_list]
            found = [(rownum, row, candidate(cell(row, cols["Stage"]), evidence)) for rownum, row in rows]
            duplicate = len(rows) > 1
            opted_out = [OPTED_OUT_STATUS[ev["status"]] for ev in evidence
                         if isinstance(ev["status"], int) and ev["status"] in OPTED_OUT_STATUS]
            opted_out = list(OrderedDict.fromkeys(opted_out))
            for rownum, row, cand in found:
                stage_after = cell(row, cols["Stage"])
                created = cand["created"] if cand else [ev["timestamp_created"] for ev in evidence]
                if duplicate and any(c for _, _, c in found):
                    e = _entry(tab, rownum, row, cols, email)
                    e["reason"] = REASON_DUPLICATE
                    e["bug_reason"] = cand["reason"] if cand else None
                    e["suggested_stage"] = cand["proposed_stage"] if cand else None
                    e["prior_stage_unknown"] = bool(cand and cand["prior_stage_unknown"])
                    e["evidence"] = evidence
                    review.append(_finish(e, created, notes_missing))
                elif cand and cand["proposed_stage"] == UNCONTACTED and opted_out:
                    # "New/Uncontacted" would put an unsubscribed or skipped
                    # (possibly blocklisted) lead back in line for outreach.
                    e = _entry(tab, rownum, row, cols, email)
                    e["reason"] = REASON_OPTED_OUT
                    e["bug_reason"] = cand["reason"]
                    e["suggested_stage"] = cand["proposed_stage"]
                    e["prior_stage_unknown"] = cand["prior_stage_unknown"]
                    e["evidence"] = evidence
                    review.append(_finish(e, created, notes_missing, opted_out))
                elif cand:
                    e = _entry(tab, rownum, row, cols, email)
                    e["proposed_stage"] = cand["proposed_stage"]
                    e["reason"] = cand["reason"]
                    e["prior_stage_unknown"] = cand["prior_stage_unknown"]
                    e["evidence"] = evidence
                    entries.append(_finish(e, created, notes_missing))
                    stage_after = cand["proposed_stage"]
                if any(ev["new_stage"] and sync_should_update(stage_after, ev["new_stage"]) for ev in evidence):
                    would_move[tab] += 1

    by_tab = OrderedDict()  # type: Dict[str, Dict[str, Dict[str, int]]]
    for tab in crm:
        by_tab[tab] = {"entries": {}, "needs_review": {}}
    for key, items in (("entries", entries), ("needs_review", review)):
        for e in items:
            counts = by_tab[e["tab"]][key]
            counts[e["reason"]] = counts.get(e["reason"], 0) + 1
    return OrderedDict((
        ("_meta", OrderedDict((
            ("schema", PLAN_SCHEMA),
            ("script", SCRIPT),
            ("generated_at", now.astimezone(timezone.utc).replace(microsecond=0).isoformat()),
            ("sources", sources or {}),
            ("spreadsheet_id", spreadsheet_id),
            ("tabs", list(crm.keys())),
            ("header_warnings", header_warnings),
            ("mx", bool(mx)),
            ("how_to_edit", "Delete an entry to skip it. Set proposed_stage on a needs_review entry "
                            "to include it. --apply writes every entry whose proposed_stage is set."),
            ("applicable", "only to spreadsheet_id; a plan with spreadsheet_id null (offline snapshot) "
                           "cannot be applied live"),
        ))),
        ("entries", entries),
        ("needs_review", review),
        ("summary", OrderedDict((
            ("crm_rows_with_email", rows_with_email),
            ("instantly_leads", len(leads)),
            ("crm_emails_with_instantly_lead", len(emails_matched)),
            ("entries", len(entries)),
            ("needs_review", len(review)),
            ("by_tab", by_tab),
            ("information_only", OrderedDict((
                ("fixed_sync_would_move_forward", dict(would_move, total=sum(would_move.values()))),
                ("note", "Rows the fixed sync moves forward itself on its next run (after this "
                         "correction). Not part of this plan."),
            ))),
        ))),
    ))


def print_plan(plan: Dict[str, Any], out: Callable[[str], None] = print) -> None:
    meta, summary = plan.get("_meta") or {}, plan.get("summary") or {}
    src = meta.get("sources") or {}
    out("CRM stage correction plan (%s)" % meta.get("generated_at"))
    out("  CRM:       %s (tabs: %s)" % (src.get("crm"), ", ".join(meta.get("tabs") or [])))
    out("  Instantly: %s (%s leads, whole workspace; %s CRM emails matched)"
        % (src.get("leads"), summary.get("instantly_leads"), summary.get("crm_emails_with_instantly_lead")))
    sid = meta.get("spreadsheet_id")
    out("  Sheet id:  %s" % (sid or "none (offline snapshot): this plan cannot be applied live"))
    for tab, w in (meta.get("header_warnings") or {}).items():
        fb = w.get("fallback_used") or {}
        if w.get("left_out"):
            out("  WARNING: tab %r header has no %s column and the fixed fallback column holds another "
                "header, so the tab was LEFT OUT of this plan"
                % (tab, " / ".join(repr(m) for m in w.get("ambiguous") or [])))
        else:
            out("  WARNING: tab %r header has no %s column; read from fixed column(s) %s"
                % (tab, " / ".join(repr(m) for m in w.get("missing") or []),
                   ", ".join("%s=%s" % (k, v) for k, v in fb.items()) or "-"))
        if w.get("apply_refuses_tab") and not w.get("left_out"):
            out("           --apply and --restore will NOT write this tab until the header names "
                "Stage, Email and Last Updated")
    fmt = "  %-14s %4s  %-34s %-19s -> %-19s %-21s %s"
    out("")
    out("To correct:")
    if not plan.get("entries"):
        out("  (none)")
    else:
        out(fmt % ("TAB", "ROW", "EMAIL", "CURRENT", "PROPOSED", "REASON", "CONFIDENCE"))
        for e in plan["entries"]:
            proposed = e["proposed_stage"] + (" *" if e.get("prior_stage_unknown") else "")
            conf = e["confidence"]
            if e.get("review_reasons"):
                conf += " (%s)" % ", ".join(e["review_reasons"])
            out(fmt % (e["tab"], e["row"], e["email"], e["current_stage"], proposed, e["reason"], conf))
        if any(e.get("prior_stage_unknown") for e in plan["entries"]):
            out("  * no Instantly signal: what the row said before the legacy sync overwrote it is unknown "
                "(Sheets version history has it)")
    out("")
    out("Needs review (proposed_stage is null; set it in the plan file to include the row):")
    if not plan.get("needs_review"):
        out("  (none)")
    for e in plan.get("needs_review") or []:
        extra = ""
        if e["reason"] == REASON_DUPLICATE:
            extra = "email on more than one row; suggested %s" % (e.get("suggested_stage") or "no change")
        elif e["reason"] == REASON_ZOHO_MX:
            extra = "no Instantly lead; MX %s" % ", ".join((e["evidence"][0] or {}).get("mx_hosts") or [])
        elif e["reason"] == REASON_OPTED_OUT:
            extra = "%s; would have been %s" % (
                ", ".join(r for r in e.get("review_reasons") or [] if r.startswith("lead_status_")),
                e.get("suggested_stage"))
        out("  %-14s %4s  %-34s %-19s  %s (%s)" % (e["tab"], e["row"], e["email"], e["current_stage"],
                                                  e["reason"], extra))
    out("")
    out("Summary:")
    for tab, counts in (summary.get("by_tab") or {}).items():
        def fmt_counts(d: Dict[str, int]) -> str:
            return ", ".join("%s %d" % (k, v) for k, v in sorted(d.items())) or "-"
        out("  %s: %d to correct (%s); %d to review (%s)"
            % (tab, sum(counts["entries"].values()), fmt_counts(counts["entries"]),
               sum(counts["needs_review"].values()), fmt_counts(counts["needs_review"])))
    out("  Total: %d to correct, %d to review" % (summary.get("entries", 0), summary.get("needs_review", 0)))
    info = ((summary.get("information_only") or {}).get("fixed_sync_would_move_forward") or {})
    out("  Information only, not in this plan: the fixed sync would move %d row(s) forward on its next run (%s)"
        % (info.get("total", 0), ", ".join("%s %d" % (k, v) for k, v in info.items() if k != "total") or "-"))
    if not summary.get("crm_emails_with_instantly_lead"):
        out("  No CRM email has an Instantly lead. If the HVAC/Roofing leads are gone from this workspace, "
            "only --mx can find the Zoho rows.")


def save_plan(plan: Dict[str, Any], now: datetime, directory: Optional[Path] = None) -> Path:
    directory = Path(directory) if directory else tmp_dir() / PLAN_SUBDIR
    directory.mkdir(parents=True, exist_ok=True)
    stem = "plan_%s" % R.stamp(now)
    path, n = directory / ("%s.json" % stem), 2
    while path.exists():
        path, n = directory / ("%s_%d.json" % (stem, n)), n + 1
    with open(str(path), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False, default=str)
        fh.write("\n")
    return path


# =========================================================================
# Applying
# =========================================================================

def load_plan(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        plan = json.load(fh)
    meta = plan.get("_meta") if isinstance(plan, dict) else None
    if not isinstance(meta, dict) or meta.get("script") != SCRIPT:
        raise ValueError("%s is not a plan written by %s --dry-run" % (path, SCRIPT))
    return plan


def actionable_entries(plan: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
    """(entries to write, (entry, why) for entries that cannot be used)."""
    order = stage_order()
    ok, bad = [], []  # type: List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]
    for e in list(plan.get("entries") or []) + list(plan.get("needs_review") or []):
        if not isinstance(e, dict) or e.get("proposed_stage") in (None, ""):
            continue
        if e["proposed_stage"] not in order:
            bad.append((e, "proposed_stage %r is not a CRM stage" % e["proposed_stage"]))
        elif not isinstance(e.get("row"), int) or not e.get("tab") or not norm_email(e.get("email")):
            bad.append((e, "entry needs tab, row (a number) and email"))
        elif "current_stage" not in e:
            bad.append((e, "entry has no current_stage"))
        else:
            ok.append(e)
    return ok, bad


def locate(values: List[List[str]], cols: Dict[str, int], row: int, email: str) -> Tuple[Optional[int], Optional[str]]:
    """(row number now holding ``email``, None) or (None, why not). The planned
    row wins; if it moved, the one row in the tab with that email."""
    email = norm_email(email)
    if 2 <= row <= len(values) and norm_email(cell(values[row - 1], cols["Email"])) == email:
        return row, None
    matches = [i for i, r in enumerate(values[1:], start=2) if norm_email(cell(r, cols["Email"])) == email]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, "email is no longer in the tab"
    return None, "row %d no longer holds the email and it is on %d rows; cannot tell which" % (row, len(matches))


def plan_writes(values_by_tab: Dict[str, List[List[str]]], items: List[Dict[str, Any]], today: str,
                expected_key: str, target_key: str, target_updated: Optional[str] = None
                ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check each item against live. ``expected_key`` is the stage the row must
    hold now, ``target_key`` the stage to write. A tab whose header does not
    name Stage, Email and Last Updated is refused (never written by fixed
    column)."""
    writes, skips = [], []  # type: List[Dict[str, Any]], List[Dict[str, Any]]
    used = set()
    for item in items:
        tab, email = item["tab"], norm_email(item["email"])
        base = {"tab": tab, "planned_row": item["row"], "email": email}
        if tab not in values_by_tab:
            skips.append(dict(base, why="tab could not be read"))
            continue
        values = values_by_tab[tab]
        header = values[0] if values else []
        problem = header_problem(header)
        if problem:
            skips.append(dict(base, why="tab refused: %s" % problem, tab_refused=True))
            continue
        cols = columns(header)
        rownum, why = locate(values, cols, item["row"], email)
        if rownum is None:
            skips.append(dict(base, why=why))
            continue
        live = values[rownum - 1]
        live_stage = cell(live, cols["Stage"])
        if live_stage == item[target_key]:
            skips.append(dict(base, row=rownum, why="already at %s" % item[target_key], satisfied=True))
            continue
        if live_stage != item[expected_key]:
            skips.append(dict(base, row=rownum, why="Stage changed since (expected %r, now %r)"
                                                   % (item[expected_key], live_stage)))
            continue
        if (tab, rownum) in used:
            skips.append(dict(base, row=rownum, why="row %d is already in this run" % rownum))
            continue
        used.add((tab, rownum))
        writes.append(OrderedDict((
            ("tab", tab), ("row", rownum), ("planned_row", item["row"]), ("email", email),
            ("stage_col", col_letter(cols["Stage"])), ("last_updated_col", col_letter(cols["Last Updated"])),
            ("stage_before", live_stage), ("last_updated_before", cell(live, cols["Last Updated"])),
            ("stage_after", item[target_key]),
            ("last_updated_after", item.get(target_updated) if target_updated else today),
            ("reason", item.get("reason")),
        )))
    return writes, skips


# ---------------------------------------------------------- the second read
def _write_key(w: Dict[str, Any]) -> Tuple[Any, ...]:
    return (w["tab"], w["row"], w["email"], w["stage_before"], w["stage_after"],
            w["stage_col"], w["last_updated_col"])


def _show(w: Dict[str, Any]) -> str:
    return "row %d %s -> %s (cells %s%d/%s%d)" % (w["row"], w["stage_before"], w["stage_after"],
                                                  w["stage_col"], w["row"], w["last_updated_col"], w["row"])


def differences(confirmed: List[Dict[str, Any]], writes: List[Dict[str, Any]],
                skips: List[Dict[str, Any]]) -> List[str]:
    """How a fresh plan differs from the one the person confirmed ([] = same)."""
    if [_write_key(w) for w in confirmed] == [_write_key(w) for w in writes]:
        return []
    fresh_keys = set(_write_key(w) for w in writes)
    confirmed_keys = set(_write_key(w) for w in confirmed)
    lines = []  # type: List[str]
    for w in confirmed:
        if _write_key(w) in fresh_keys:
            continue
        now = [f for f in writes if (f["tab"], f["email"]) == (w["tab"], w["email"])]
        if now:
            lines.append("%s %s: confirmed %s; now %s" % (w["tab"], w["email"], _show(w), _show(now[0])))
        else:
            why = [s["why"] for s in skips if (s["tab"], s["email"]) == (w["tab"], w["email"])]
            lines.append("%s %s: confirmed %s; now not written (%s)" % (
                w["tab"], w["email"], _show(w), why[0] if why else "not in the fresh read"))
    for f in writes:
        if _write_key(f) in confirmed_keys:
            continue
        if not any((w["tab"], w["email"]) == (f["tab"], f["email"]) for w in confirmed):
            lines.append("%s %s: was not in the confirmed list; now %s" % (f["tab"], f["email"], _show(f)))
    if not lines:
        lines.append("the same rows came back in a different order")
    return lines


def _reread(spreadsheet: Any, tabs: List[str], items: List[Dict[str, Any]], today: str, expected_key: str,
            target_key: str, target_updated: Optional[str], confirmed: List[Dict[str, Any]],
            out: Callable[[str], None]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """After the typed confirmation: read every tab again and plan again.
    (sheets, writes, skips, differences from what was confirmed)."""
    sheets, values = read_tabs(spreadsheet, tabs, out)
    writes, skips = plan_writes(values, items, today, expected_key, target_key, target_updated)
    return sheets, writes, skips, differences(confirmed, writes, skips)


# ------------------------------------------------------------ the writes
def _write_backup(kind: str, rows: List[Dict[str, Any]], now: datetime, directory: Optional[Path],
                  extra: Dict[str, Any], spreadsheet_id: Optional[str], stem_word: str = "before") -> Optional[str]:
    directory = Path(directory) if directory else BACKUP_DIR
    stem = "%s_%s_%s" % (SCRIPT, stem_word, R.stamp(now))
    try:
        obj = dict(extra, spreadsheet_id=spreadsheet_id, rows=rows)
        point = R.build_point(SCRIPT, kind, obj, ["Stage", "Last Updated"], now, object_type="crm_rows",
                              extra={"spreadsheet_id": spreadsheet_id})
        return R.write_point(str(directory), stem, point)
    except (OSError, ValueError) as exc:
        logger.warning("backup write failed (%s/%s): %s", directory, stem, exc)
        return None


def _settle(ws: Any, tab: str, tab_writes: List[Dict[str, Any]], error: str) -> Dict[str, Any]:
    """A batch_update raised: re-read the tab and say what landed. A client-side
    error (timeout, reset) does not prove the request was dropped."""
    info = OrderedDict((("tab", tab), ("error", error), ("outcome", None), ("rows", len(tab_writes)),
                        ("landed_rows", []), ("unchanged_rows", []), ("other_rows", [])))  # type: Dict[str, Any]
    try:
        values = [list(r) for r in (ws.get_all_values() or [])]
    except Exception as exc:  # noqa: BLE001
        info["outcome"] = "unknown_after_error"
        info["error"] = "%s (the re-read failed too: %s)" % (error, str(exc)[:200])
        return info
    email_col = columns(values[0] if values else [])["Email"]
    for w in tab_writes:
        row = values[w["row"] - 1] if 2 <= w["row"] <= len(values) else []
        stage = cell(row, col_index(w["stage_col"]))
        updated = cell(row, col_index(w["last_updated_col"]))
        if norm_email(cell(row, email_col)) != w["email"]:
            info["other_rows"].append(w["row"])
        elif stage == w["stage_after"] and same_sheet_date(updated, w["last_updated_after"]):
            info["landed_rows"].append(w["row"])
        elif stage == w["stage_before"] and same_sheet_date(updated, w["last_updated_before"]):
            info["unchanged_rows"].append(w["row"])
        else:
            info["other_rows"].append(w["row"])
    if info["landed_rows"] and not info["unchanged_rows"] and not info["other_rows"]:
        info["outcome"] = "landed_after_error"
    elif info["unchanged_rows"] and not info["landed_rows"] and not info["other_rows"]:
        info["outcome"] = "unchanged_at_reread"
    else:
        info["outcome"] = "mixed_at_reread"
    return info


def send_by_tab(sheets: Dict[str, Any], writes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One batch_update per tab, in order; stops at the first error and settles
    that tab by re-reading it. {sent, confirmed, not_sent, failed}: ``sent``
    lists every tab whose batch_update was called (acknowledged or not)."""
    tabs = list(OrderedDict.fromkeys(w["tab"] for w in writes))
    result = OrderedDict((("sent", []), ("confirmed", []), ("not_sent", []), ("failed", None)))  # type: Dict[str, Any]
    for i, tab in enumerate(tabs):
        tab_writes = [w for w in writes if w["tab"] == tab]
        data = []
        for w in tab_writes:
            data.append({"range": "%s%d" % (w["stage_col"], w["row"]), "values": [[w["stage_after"]]]})
            data.append({"range": "%s%d" % (w["last_updated_col"], w["row"]), "values": [[w["last_updated_after"]]]})
        result["sent"].append(tab)
        try:
            sheets[tab].batch_update(data, value_input_option="USER_ENTERED")
        except Exception as exc:  # noqa: BLE001 - settled, then reported
            result["failed"] = _settle(sheets[tab], tab, tab_writes, "%s: %s" % (type(exc).__name__, str(exc)[:300]))
            result["not_sent"] = tabs[i + 1:]
            return result
        result["confirmed"].append(tab)
    return result


def rows_known_written(writes: List[Dict[str, Any]], result: Dict[str, Any]) -> int:
    n = len([w for w in writes if w["tab"] in result["confirmed"]])
    failed = result.get("failed") or {}
    return n + len(failed.get("landed_rows") or [])


def stop_lines(result: Dict[str, Any]) -> List[str]:
    """What happened, for a run whose batch_update raised. Never claims a tab
    was not written unless a re-read shows it."""
    f = result["failed"]
    lines = ["STOPPED: batch_update on %r raised (%s). A client-side error does not prove the write "
             "was dropped." % (f["tab"], f["error"])]
    o = f["outcome"]
    if o == "landed_after_error":
        lines.append("  A re-read of %r shows all %d row(s) hold the new values: that write LANDED."
                     % (f["tab"], f["rows"]))
    elif o == "unchanged_at_reread":
        lines.append("  A re-read of %r shows all %d row(s) still hold the old values. A late write can "
                     "still land, so re-read the tab before re-running." % (f["tab"], f["rows"]))
    elif o == "mixed_at_reread":
        lines.append("  A re-read of %r is mixed: new values on row(s) %s; old values on row(s) %s; "
                     "something else (or another email) on row(s) %s. Check them in the sheet."
                     % (f["tab"], f["landed_rows"] or "none", f["unchanged_rows"] or "none",
                        f["other_rows"] or "none"))
    else:
        lines.append("  The re-read of %r failed too, so what that tab holds is UNKNOWN. Check it in the "
                     "sheet." % f["tab"])
    lines.append("  Tabs acknowledged before it: %s. Tabs not sent: %s."
                 % (", ".join(result["confirmed"]) or "none", ", ".join(result["not_sent"]) or "none"))
    return lines


def _print_skips(skips: List[Dict[str, Any]], out: Callable[[str], None]) -> None:
    for s in skips:
        out("  SKIP %s row %s %s: %s" % (s["tab"], s.get("row", s["planned_row"]), s["email"], s["why"]))


def _confirm(args: Any, confirm: Optional[Callable[[str], str]], n: int, what: str) -> bool:
    if args.yes:
        return True
    answer = (confirm or input)("Type the number of rows (%d) to confirm the LIVE %s: " % (n, what))
    return answer.strip() == str(n)


def _open(sheet: Any, scopes: Optional[List[str]] = None) -> Any:
    return sheet if sheet is not None else open_spreadsheet(scopes)


def _check_sheet(spreadsheet: Any, expected: str, what: str, out: Callable[[str], None]) -> bool:
    live_id = sheet_id_of(spreadsheet)
    if live_id != expected:
        out("REFUSED: %s was read from spreadsheet %s, but GOOGLE_SHEET_ID opens %s. Nothing was read or "
            "written." % (what, expected, live_id or "a sheet with no id"))
        return False
    return True


MOVED_HINT = ("Nothing was backed up or written. Do not edit or sort the CRM tabs while this runs; "
              "re-run to see the new list.")


def _apply(args: Any, sheet: Any, out: Callable[[str], None], confirm: Optional[Callable[[str], str]],
           now: datetime, backup_dir: Optional[Path]) -> int:
    try:
        plan = load_plan(args.plan_file)
    except (OSError, ValueError) as exc:
        out("REFUSED: could not read the plan: %s" % exc)
        return EXIT_INVALID
    plan_sheet = (plan.get("_meta") or {}).get("spreadsheet_id")
    items, bad = actionable_entries(plan)
    for e, why in bad:
        out("  SKIP %s row %s %s: %s" % (e.get("tab"), e.get("row"), e.get("email"), why))
    if not items:
        out("Nothing to apply: no entry in %s has a proposed_stage." % args.plan_file)
        log_run(JOB, "apply_nothing", {"plan_file": args.plan_file, "invalid": len(bad)})
        return EXIT_OK
    by_tab = OrderedDict()  # type: Dict[str, int]
    for e in items:
        by_tab[e["tab"]] = by_tab.get(e["tab"], 0) + 1
    payload = {"plan_file": str(args.plan_file), "rows": len(items), "by_tab": by_tab,
               "spreadsheet_id": plan_sheet}
    today = today_central(now)

    if not settings.is_live():
        settings.guard_write(SYSTEM, ACTION, payload)
        out("SHADOW (MODE=%s, ALLOW_LIVE_WRITES=%s): nothing was read or written. A live run would set:"
            % (settings.get_mode(), os.environ.get("ALLOW_LIVE_WRITES", "")))
        for e in items:
            out("  %s row %s %s: %s -> %s (Last Updated -> %s)" % (
                e["tab"], e["row"], e["email"], e["current_stage"], e["proposed_stage"], today))
        out("A live run re-reads each row first and skips any whose email or Stage changed.")
        if not plan_sheet:
            out("NOTE: this plan was built from an offline snapshot (spreadsheet_id null); a live --apply "
                "refuses it.")
        log_run(JOB, "apply_shadow", payload)
        return EXIT_OK

    if not plan_sheet:
        out("REFUSED: %s was built from an offline snapshot (spreadsheet_id is null), so it cannot be "
            "applied live. Run --dry-run against the live sheet and apply that plan." % args.plan_file)
        log_run(JOB, "apply_refused_offline_plan", payload)
        return EXIT_REFUSED
    try:
        spreadsheet = _open(sheet, SHEET_SCOPES)
    except SourceError as exc:
        out("REFUSED: %s" % exc)
        return EXIT_REFUSED
    if not _check_sheet(spreadsheet, plan_sheet, "the plan", out):
        log_run(JOB, "apply_refused_other_sheet", payload)
        return EXIT_REFUSED
    tabs = list(by_tab.keys())
    _, values = read_tabs(spreadsheet, tabs, out)
    writes, skips = plan_writes(values, items, today, "current_stage", "proposed_stage")
    _print_skips(skips, out)
    if not writes:
        real = [s for s in skips if not s.get("satisfied")]
        out("Nothing written: %d row(s) skipped, %d already corrected." % (len(real), len(skips) - len(real)))
        log_run(JOB, "apply_nothing_left", {"plan_file": args.plan_file, "skips": skips})
        return EXIT_REFUSED if real else EXIT_OK
    out("LIVE: %d row(s) to write:" % len(writes))
    for w in writes:
        out("  %s row %d %s: %s -> %s (Last Updated %s -> %s)%s" % (
            w["tab"], w["row"], w["email"], w["stage_before"], w["stage_after"], w["last_updated_before"] or "-",
            w["last_updated_after"], " [moved from row %d]" % w["planned_row"] if w["row"] != w["planned_row"] else ""))
    if not _confirm(args, confirm, len(writes), "write"):
        out("aborted: confirmation did not match; nothing written")
        return EXIT_REFUSED

    # The prompt can stay open for minutes. Read every tab again and act only
    # if the writes come out exactly as confirmed; the backup is built from
    # THIS read, so it holds the values actually overwritten.
    sheets, fresh, fresh_skips, diffs = _reread(spreadsheet, tabs, items, today, "current_stage",
                                                "proposed_stage", None, writes, out)
    if diffs:
        out("REFUSED: the CRM changed while the confirmation was open:")
        for line in diffs:
            out("  " + line)
        out(MOVED_HINT)
        log_run(JOB, "apply_refused_moved_during_prompt", dict(payload, differences=diffs))
        return EXIT_REFUSED
    writes, skips = fresh, fresh_skips

    record = settings.guard_write(SYSTEM, ACTION, dict(payload, rows=len(writes), skipped=len(skips)))
    if record.get("shadow"):
        out("REFUSED: guard_write answered shadow; nothing written")
        return EXIT_REFUSED
    backup = _write_backup(R.KIND_PREAPPLY, writes, now, backup_dir,
                           {"plan_file": str(args.plan_file), "today": today}, plan_sheet)
    if backup is None:
        out("REFUSED: the backup could not be written, so nothing was written to the sheet. "
            "Check changesets/backups/ is writable and re-run.")
        settings.record_live_write_result(SYSTEM, ACTION, False, {"error": "backup failed; nothing written"})
        log_run(JOB, "apply_refused_no_backup", payload)
        return EXIT_REFUSED
    result = send_by_tab(sheets, writes)
    failed = result["failed"]
    # Once any batch_update was sent the backup is THE rollback point, whatever
    # happened next; only a run that sent nothing is "not_applied".
    kind = R.KIND_APPLY if result["sent"] else R.KIND_NOT_APPLIED
    outcome = "not_applied" if not result["sent"] else ("stopped" if failed else "applied")
    try:
        backup = R.relabel(backup, kind, outcome=outcome, tabs_sent=result["sent"],
                           tabs_confirmed=result["confirmed"], tabs_not_sent=result["not_sent"],
                           failed=failed, error=failed["error"] if failed else None)
    except (OSError, ValueError) as exc:
        out("WARNING: could not relabel the backup %s (it stays restorable as a .preapply file): %s" % (backup, exc))
    details = {"plan_file": str(args.plan_file), "rows_known_written": rows_known_written(writes, result),
               "tabs_sent": result["sent"], "tabs_confirmed": result["confirmed"],
               "tabs_not_sent": result["not_sent"], "failed": failed, "skipped": len(skips),
               "backup": str(backup), "spreadsheet_id": plan_sheet}
    settings.record_live_write_result(SYSTEM, ACTION, failed is None, details)
    out("backup: %s" % backup)
    if failed:
        for line in stop_lines(result):
            out(line)
        out("  The backup above is a restorable rollback point: --restore puts back every row that holds "
            "the corrected stage.")
        log_run(JOB, "apply_stopped", details)
        return EXIT_API
    out("done: %d row(s) written in %d tab(s); %d skipped" % (len(writes), len(result["confirmed"]), len(skips)))
    log_run(JOB, "applied", details)
    return EXIT_OK


def _restore(args: Any, sheet: Any, out: Callable[[str], None], confirm: Optional[Callable[[str], str]],
             now: datetime, backup_dir: Optional[Path]) -> int:
    try:
        with open(args.restore, "r", encoding="utf-8") as fh:
            point = json.load(fh)
    except (OSError, ValueError) as exc:
        out("REFUSED: cannot read %s: %s" % (args.restore, exc))
        return EXIT_INVALID
    meta = point.get(R.META_KEY) if isinstance(point, dict) else None
    if (not isinstance(meta, dict) or meta.get("script") != SCRIPT or meta.get("object") != "crm_rows"
            or meta.get("kind") not in (R.KIND_APPLY, R.KIND_PREAPPLY)):
        out("REFUSED: %s is not a backup an --apply of this script wrote (kind apply or preapply)" % args.restore)
        return EXIT_INVALID
    point_sheet = meta.get("spreadsheet_id") or point.get("spreadsheet_id")
    rows = [r for r in (point.get("rows") or []) if isinstance(r, dict)]
    by_tab = OrderedDict()  # type: Dict[str, int]
    for r in rows:
        by_tab[r["tab"]] = by_tab.get(r["tab"], 0) + 1
    payload = {"backup": str(args.restore), "rows": len(rows), "by_tab": by_tab, "spreadsheet_id": point_sheet}

    if not settings.is_live():
        settings.guard_write(SYSTEM, RESTORE_ACTION, payload)
        out("SHADOW (MODE=%s): nothing was read or written. A live restore would set, where the row still "
            "holds the corrected stage:" % settings.get_mode())
        for r in rows:
            out("  %s row %s %s: %s -> %s (Last Updated -> %s)" % (
                r["tab"], r["row"], r["email"], r["stage_after"], r["stage_before"], r["last_updated_before"] or "-"))
        log_run(JOB, "restore_shadow", payload)
        return EXIT_OK

    if not point_sheet:
        out("REFUSED: %s records no spreadsheet id, so it cannot be matched to the live sheet." % args.restore)
        return EXIT_REFUSED
    try:
        spreadsheet = _open(sheet, SHEET_SCOPES)
    except SourceError as exc:
        out("REFUSED: %s" % exc)
        return EXIT_REFUSED
    if not _check_sheet(spreadsheet, point_sheet, "the backup", out):
        log_run(JOB, "restore_refused_other_sheet", payload)
        return EXIT_REFUSED
    tabs = list(by_tab.keys())
    today = today_central(now)
    _, values = read_tabs(spreadsheet, tabs, out)
    writes, skips = plan_writes(values, rows, today, "stage_after", "stage_before",
                                target_updated="last_updated_before")
    _print_skips(skips, out)
    if not writes:
        out("Nothing to restore.")
        log_run(JOB, "restore_nothing", {"backup": str(args.restore), "skips": skips})
        return EXIT_OK if all(s.get("satisfied") for s in skips) else EXIT_REFUSED
    out("LIVE restore: %d row(s):" % len(writes))
    for w in writes:
        out("  %s row %d %s: %s -> %s (Last Updated -> %s)" % (
            w["tab"], w["row"], w["email"], w["stage_before"], w["stage_after"], w["last_updated_after"] or "-"))
    if not _confirm(args, confirm, len(writes), "restore"):
        out("aborted: confirmation did not match; nothing written")
        return EXIT_REFUSED

    sheets, fresh, fresh_skips, diffs = _reread(spreadsheet, tabs, rows, today, "stage_after", "stage_before",
                                                "last_updated_before", writes, out)
    if diffs:
        out("REFUSED: the CRM changed while the confirmation was open:")
        for line in diffs:
            out("  " + line)
        out(MOVED_HINT)
        log_run(JOB, "restore_refused_moved_during_prompt", dict(payload, differences=diffs))
        return EXIT_REFUSED
    writes, skips = fresh, fresh_skips

    record = settings.guard_write(SYSTEM, RESTORE_ACTION, dict(payload, rows=len(writes)))
    if record.get("shadow"):
        out("REFUSED: guard_write answered shadow; nothing written")
        return EXIT_REFUSED
    pre = _write_backup(R.KIND_PRERESTORE, writes, now, backup_dir, {"restoring": str(args.restore)},
                        point_sheet, stem_word="prerestore")
    if pre is None:
        out("REFUSED: the pre-restore copy could not be written, so nothing was written.")
        settings.record_live_write_result(SYSTEM, RESTORE_ACTION, False, {"error": "backup failed; nothing written"})
        return EXIT_REFUSED
    result = send_by_tab(sheets, writes)
    failed = result["failed"]
    details = {"backup": str(args.restore), "prerestore": pre,
               "rows_known_written": rows_known_written(writes, result), "tabs_sent": result["sent"],
               "tabs_confirmed": result["confirmed"], "tabs_not_sent": result["not_sent"], "failed": failed,
               "skipped": len(skips), "spreadsheet_id": point_sheet}
    settings.record_live_write_result(SYSTEM, RESTORE_ACTION, failed is None, details)
    log_run(JOB, "restored" if not failed else "restore_stopped", details)
    if failed:
        for line in stop_lines(result):
            out(line)
        out("  Re-running the same --restore puts back the rows still at the corrected stage.")
        return EXIT_API
    out("restored %d row(s); pre-restore copy: %s" % (len(writes), pre))
    return EXIT_OK


# =========================================================================
# Dry-run and entry point
# =========================================================================

def _dry_run(args: Any, sheet: Any, leads: Optional[List[Dict[str, Any]]],
             resolver: Optional[Callable[[str], List[str]]], out: Callable[[str], None], now: datetime) -> int:
    tabs = args.tab or default_tabs()
    try:
        sheet_id = None  # type: Optional[str]
        if args.crm_snapshot:
            crm = load_crm_snapshot(args.crm_snapshot, tabs, out)
            crm_source = "snapshot %s" % args.crm_snapshot
        else:
            spreadsheet = _open(sheet, READONLY_SCOPES)
            sheet_id = sheet_id_of(spreadsheet)
            _, crm = read_tabs(spreadsheet, tabs, out)
            crm_source = "google sheet (GOOGLE_SHEET_ID)" if sheet is None else "sheet client"
        if args.leads_snapshot:
            lead_list = load_leads_snapshot(args.leads_snapshot)
            leads_source = "snapshot %s" % args.leads_snapshot
        elif leads is not None:
            lead_list, leads_source = list(leads), "injected"
        else:
            lead_list, leads_source = live_leads(), "instantly leads/list (no campaign filter)"
    except (OSError, ValueError) as exc:
        out("REFUSED: could not read an input: %s" % exc)
        return EXIT_INVALID
    except SourceError as exc:
        out("REFUSED: %s" % exc)
        return EXIT_REFUSED
    if not crm:
        out("REFUSED: no CRM tab could be read (%s)" % ", ".join(tabs))
        return EXIT_INVALID
    plan = build_plan(crm, lead_list, now, mx=args.mx, resolver=resolver,
                      sources={"crm": crm_source, "leads": leads_source}, spreadsheet_id=sheet_id)
    print_plan(plan, out)
    path = save_plan(plan, now, Path(args.plan_out) if args.plan_out else None)
    out("")
    out("plan saved: %s" % path)
    out("dry-run only; nothing was written. mode=%s" % settings.get_mode())
    summary = plan["summary"]
    log_run(JOB, "dry_run", {"plan_file": str(path), "tabs": list(crm.keys()), "entries": summary["entries"],
                             "needs_review": summary["needs_review"], "mx": bool(args.mx),
                             "instantly_leads": summary["instantly_leads"]})
    return EXIT_OK


def main(argv: Optional[List[str]] = None, sheet: Any = None, leads: Optional[List[Dict[str, Any]]] = None,
         resolver: Optional[Callable[[str], List[str]]] = None, out: Callable[[str], None] = print,
         confirm: Optional[Callable[[str], str]] = None, now: Optional[datetime] = None,
         backup_dir: Optional[Path] = None) -> int:
    p = argparse.ArgumentParser(prog="apply_crm_stage_correction",
                                description="Correct CRM stages the legacy Instantly sync mislabelled")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="build and save the plan; no writes (default)")
    g.add_argument("--apply", action="store_true",
                   help="write a saved plan (MODE=live + ALLOW_LIVE_WRITES=1 only); needs --plan-file")
    g.add_argument("--restore", metavar="BACKUP", help="put back the values a live --apply backed up")
    p.add_argument("--plan-file", help="plan JSON from --dry-run (with --apply)")
    p.add_argument("--tab", action="append", help="CRM tab to read (repeatable; default: HVAC Leads, Roofing Leads)")
    p.add_argument("--crm-snapshot", help="offline CRM: {\"<tab>\": get_all_values()}")
    p.add_argument("--leads-snapshot", help="offline Instantly leads: {\"items\": [...]} or a list")
    p.add_argument("--mx", action="store_true",
                   help="also flag Closed - Lost rows with no Instantly lead whose domain's MX is Zoho")
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation (live flags still required)")
    p.add_argument("--backup-dir", help=argparse.SUPPRESS)
    p.add_argument("--plan-out", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    now = now or datetime.now(timezone.utc)
    backup_dir = backup_dir or (Path(args.backup_dir) if args.backup_dir else None)

    offline_flags = [f for f, v in (("--crm-snapshot", args.crm_snapshot), ("--leads-snapshot", args.leads_snapshot),
                                    ("--mx", args.mx), ("--tab", args.tab)) if v]
    if (args.apply or args.restore) and offline_flags:
        out("REFUSED: %s only go with --dry-run" % ", ".join(offline_flags))
        return EXIT_INVALID
    if args.apply:
        if not args.plan_file:
            out("REFUSED: --apply needs --plan-file <plan from --dry-run>")
            return EXIT_INVALID
        return _apply(args, sheet, out, confirm, now, backup_dir)
    if args.restore:
        return _restore(args, sheet, out, confirm, now, backup_dir)
    if args.plan_file:
        out("REFUSED: --plan-file goes with --apply")
        return EXIT_INVALID
    with R.scratch_logs("crm_stage_correction_dryrun"):
        return _dry_run(args, sheet, leads, resolver, out, now)


if __name__ == "__main__":
    sys.exit(main())
