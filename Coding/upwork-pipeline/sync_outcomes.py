#!/usr/bin/env python3
"""Sync Upwork proposal outcomes into proposals.csv.

The Upwork MCP can only be called by the agent, so the main session saves the
raw MCP responses as JSON and this script does the deterministic part:

  python3 sync_outcomes.py --proposals proposals.json \
      [--rooms rooms.json] [--contracts contracts.json] [--insights insights.json] \
      [--fill-boosted] [--csv proposals.csv] [--dry-run] [--report]
  python3 sync_outcomes.py --report            # rates only, no sync

Inputs (all raw MCP output, see OUTCOMES.md):
  --proposals  list_freelancer_proposals action=list responses. One response,
               a JSON list of responses (one per status/page), or {"pages": [...]}.
               action=get responses (data.vendorProposal) are accepted too.
  --rooms      {"<proposal_id>": <list_freelancer_proposals action=get_room response>}.
               A NOT_FOUND error response means no client message yet.
  --contracts  list_contracts action=search response(s). Contracts carry no
               job id, so a contract is applied only when exactly one fetched
               proposal has its title, the contract starts on/after the
               proposal date, and that proposal is not Declined/Withdrawn/
               Archived. Every other contract is listed as unmatched.

What Upwork can tell us (observed 2026-09-22):
  viewed       NOT exposed per proposal. Inferred: a client reply,
               interview, hire or "Declined by client" implies they opened it.
               With --insights (action=get responses), an open proposal
               (Accepted / Activated / Offered) whose job shows proposals_opened,
               messaged and shortlisted all 0 gets "no" (upgraded to yes by a
               later reply, interview or hire). The counts never give "yes":
               they are job-level and may not include our proposal. Closed
               proposals get nothing from insights.
  boosted      with --fill-boosted, a blank cell gets the proposal's boosted flag.
  replied      a room exists for the proposal (freelancers cannot message
               first), or status Activated / Offered / Hired.
  interviewed  status Activated ("Invitation accepted" label; the proposal is
               in an active interview) / Offered / Hired.
  hired        status Hired, or a contract matched as above.
  "no"         hired: proposal is Declined / Archived / Withdrawn and not hired.
               replied / interviewed: proposal is Declined / Archived /
               Withdrawn AND the rooms file holds an explicit NOT_FOUND for
               its proposal id. Without that, they stay blank.

Matching: first every row with an Upwork job id in job_url
(https://www.upwork.com/jobs/~02<id>) claims that job's proposal. Then rows
with no job id fall back to a normalized-title match (exact, or a unique
prefix of 15+ chars for truncated log titles) against proposals whose job id
is in no row's job_url and in no skipped row. A row whose exact title is the
title of any fetched proposal is never prefix-matched: if that proposal is
already claimed, the row stays unmatched and is reported. A proposal is
claimed by at most one row; if its title matches several URL-less rows, none
of them is updated and the summary lists them as ambiguous.

Reading: records are split the way the csv module reads them (a quote opens a
quoted field only at the start of a field) and end on "\n" only, except that
a quoted field is never allowed to run on into a line that starts with a date
(the next row): the record is cut after that line break. A leading byte-order
mark is ignored for parsing and kept on write. Malformed records are skipped
with a warning, never matched or rewritten, left out of --report, and copied
byte-for-byte: a record that does not parse, a cut record, any record that
spans more than one line (the log has one row per line), a row with fewer
fields than the header, and a row with more fields unless folding the overflow
into notes leaves every earlier column valid (see FOLD_RULES) and notes is the
only column the extra commas can be in (see fold_alternative).

Writing: only changed rows are rewritten (same line ending as before); every
other record is copied byte-for-byte. The temp file is re-read and verified,
and the CSV's size, mtime and hash are re-checked immediately before the temp
file replaces it (abort if another process wrote it). A live run keeps the
file mode and leaves proposals.csv.bak next to it.

Values are only ever upgraded: empty -> yes/no, no -> yes. A non-empty value is
never cleared and "yes" is never downgraded.
"""
import argparse
import csv
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(HERE, "proposals.csv")
OUTCOME_FIELDS = ["viewed", "replied", "interviewed", "hired"]

# Upwork status -> outcomes that status proves.
STATUS_YES = {
    "Hired": {"viewed", "replied", "interviewed", "hired"},
    "Offered": {"viewed", "replied", "interviewed"},
    "Activated": {"viewed", "replied", "interviewed"},
    "Declined": {"viewed"},
}
CLOSED_STATUSES = {"Archived", "Declined", "Withdrawn"}
OPEN_STATUSES = {"Accepted", "Activated", "Offered"}  # still open; a later sync can upgrade them
OUTCOME_VALUES = {"", "yes", "no"}
UPWORK_JOB_URL = re.compile(r"^https?://(?:www\.)?upwork\.com/(?:jobs|freelance-jobs)/\S*~\d{10,}\S*$")
JOB_URL_IN_TEXT = re.compile(r"upwork\.com/[^\s,\"]*?(~[0-9]{10,})")
BOM = "\ufeff"  # byte-order mark some editors put at the start of a CSV
# Every log row starts with its applied_at date. A line break inside a quoted
# field followed by this is a quote left open that would swallow the next row.
ROW_START = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# Column rules a row with the wrong field count must pass (after folding its
# overflow into notes) before the sync will touch it. Columns not listed here
# (job_title, build_slug, opener_variant, notes) take any text.
_ISO = r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"
_PLATFORM = r"(?:n8n|make|gohighlevel|chart|diagram|zapier)"
FOLD_RULES = {
    "applied_at": re.compile(r"^%s$" % _ISO),  # required
    "job_created_utc": re.compile(r"^(?:%s)?$" % _ISO),
    "job_url": UPWORK_JOB_URL,
    "age_hours_at_apply": re.compile(r"^(?:\d+(?:\.\d+)?)?$"),
    "platform": re.compile(r"^(?:%s(?:\|%s)*)?$" % (_PLATFORM, _PLATFORM)),
    "node_count": re.compile(r"^\d*$"),
    "loom_url": re.compile(r"^https?://(?:www\.)?loom\.com/\S+$"),
    "opener_visible_chars": re.compile(r"^\d*$"),
    "connects": re.compile(r"^\d*$"),
    "boosted": re.compile(r"^(?:yes|no|true|false)?$", re.I),
    "viewed": re.compile(r"^(?:yes|no)?$", re.I),
    "replied": re.compile(r"^(?:yes|no)?$", re.I),
    "interviewed": re.compile(r"^(?:yes|no)?$", re.I),
    "hired": re.compile(r"^(?:yes|no)?$", re.I),
}
BLANK_OK = set(FOLD_RULES) - {"applied_at"}


# ---------------------------------------------------------------- parsing

def job_id_from_url(url):
    # type: (str) -> Optional[str]
    if not url:
        return None
    m = re.search(r"~02(\d{10,})", url)
    if m:
        return m.group(1)
    m = re.search(r"~(\d{10,})", url)
    return m.group(1) if m else None


def norm_title(title):
    # type: (str) -> str
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def _display(dt_obj):
    if isinstance(dt_obj, dict):
        return dt_obj.get("displayValue") or ""
    return dt_obj or ""


def _proposal_from_node(node):
    # type: (Dict[str, Any]) -> Optional[Dict[str, Any]]
    job = node.get("marketplaceJobPosting") or {}
    status = node.get("status") or {}
    if isinstance(status, str):
        status = {"status": status}
    job_id = job.get("id") or job_id_from_url(job.get("url", ""))
    if not job_id:
        return None
    audit = node.get("auditDetails") or {}
    reason = status.get("reason") or {}
    return {
        "proposal_id": str(node.get("id", "")),
        "job_id": str(job_id),
        "title": (job.get("content") or {}).get("title", ""),
        "status": status.get("status", ""),
        "status_label": status.get("status_label", status.get("status", "")),
        "reason": reason.get("reason", "") if isinstance(reason, dict) else str(reason),
        "created": _display(audit.get("createdDateTime")),
        "modified": _display(audit.get("modifiedDateTime")),
        "boosted": node.get("boosted") if isinstance(node.get("boosted"), bool) else None,
    }


def extract_proposals(obj):
    # type: (Any) -> List[Dict[str, Any]]
    """Walk any saved MCP output shape and return flat proposal dicts."""
    out = []  # type: List[Dict[str, Any]]

    def walk(o):
        if isinstance(o, list):
            for x in o:
                walk(x)
            return
        if not isinstance(o, dict):
            return
        if "marketplaceJobPosting" in o:
            p = _proposal_from_node(o)
            if p:
                out.append(p)
            return
        for key in ("pages", "data", "vendorProposals", "edges", "node", "vendorProposal"):
            if key in o:
                walk(o[key])

    walk(obj)
    # Dedupe by proposal id, keeping the most recently modified record.
    best = {}  # type: Dict[str, Dict[str, Any]]
    for p in out:
        key = p["proposal_id"] or p["job_id"]
        if key not in best or p["modified"] > best[key]["modified"]:
            best[key] = p
    return list(best.values())


def extract_rooms(obj):
    # type: (Any) -> Tuple[Dict[str, Dict[str, Any]], set]
    """Return ({proposal_id: room} for proposals with a room,
    {proposal ids whose get_room answered an explicit NOT_FOUND})."""
    rooms = {}  # type: Dict[str, Dict[str, Any]]
    not_found = set()
    items = []  # type: List[Tuple[str, Any]]
    if isinstance(obj, dict):
        items = [(str(k), v) for k, v in obj.items()]
    elif isinstance(obj, list):
        for x in obj:
            if isinstance(x, dict) and "proposal_id" in x:
                items.append((str(x["proposal_id"]), x.get("room", x.get("response"))))
    for pid, resp in items:
        if not isinstance(resp, dict):
            continue
        if resp.get("error_code") == "NOT_FOUND":
            not_found.add(pid)
            continue
        if resp.get("status") == "error" or resp.get("error_code"):
            continue  # any other error proves nothing either way
        room = (resp.get("data") or {}).get("proposalRoom") if "data" in resp else resp
        if isinstance(room, dict) and room.get("id"):
            rooms[pid] = room
    return rooms, not_found


def extract_insights(obj):
    # type: (Any) -> Dict[str, Dict[str, Any]]
    """{proposal_id: insights} from saved list_freelancer_proposals action=get
    responses: {"<proposal_id>": <response>} or a list of responses (the id is
    then read from data.vendorProposal.id). Responses without insights are left out."""
    items = []  # type: List[Tuple[str, Any]]
    if isinstance(obj, dict):
        items = [(str(k), v) for k, v in obj.items()]
    elif isinstance(obj, list):
        for x in obj:
            if isinstance(x, dict):
                pid = ((x.get("data") or {}).get("vendorProposal") or {}).get("id", "")
                items.append((str(pid), x))
    out = {}  # type: Dict[str, Dict[str, Any]]
    for pid, resp in items:
        if pid and isinstance(resp, dict) and isinstance(resp.get("insights"), dict):
            out[pid] = resp["insights"]
    return out


def viewed_from_insights(p, ins):
    # type: (Dict[str, Any], Optional[Dict[str, Any]]) -> str
    """"no" / "" for `viewed` from the job's proposal counts (get action).

    The counts are per job and may not include our proposal (Upwork: "Averages
    describe the other applicants for this job"), so they never prove a view:
    "yes" is never returned. None opened, none messaged and none shortlisted
    means ours was not opened yet, and that "no" is written only while the
    proposal is open (OPEN_STATUSES), so a later sync that sees a reply,
    interview or hire can still upgrade it. Closed proposals and counts
    computed before our proposal existed give "". """
    if not ins or p.get("status") not in OPEN_STATUSES:
        return ""
    try:
        opened = int(ins.get("proposals_opened"))
        messaged = int(ins.get("messaged") or 0)
        shortlisted = int(ins.get("shortlisted") or 0)
    except (TypeError, ValueError):
        return ""
    computed = str(ins.get("computed_at") or "")[:19]
    if not computed or not p.get("created") or computed <= p["created"][:19]:
        return ""
    if opened == 0 and messaged == 0 and shortlisted == 0:
        return "no"
    return ""


def extract_contracts(obj):
    # type: (Any) -> List[Dict[str, str]]
    """Return one {id, title, start} dict per contract (duplicates by title kept)."""
    out = []  # type: List[Dict[str, str]]
    seen = set()

    def walk(o):
        if isinstance(o, list):
            for x in o:
                walk(x)
            return
        if not isinstance(o, dict):
            return
        if "title" in o and ("offerId" in o or "deliveryModel" in o or "startDate" in o or "createDate" in o):
            cid = str(o.get("id", ""))
            if cid and cid in seen:
                return
            seen.add(cid)
            out.append({"id": cid, "title": o.get("title") or "",
                        "start": _display(o.get("startDate")) or _display(o.get("createDate"))})
            return
        for key in ("pages", "data", "vendorContracts", "contracts", "edges", "node", "contract"):
            if key in o:
                walk(o[key])

    walk(obj)
    return out


def match_contracts(contracts, proposals):
    # type: (List[Dict[str, str]], List[Dict[str, Any]]) -> Tuple[Dict[str, List[str]], List[Tuple[Dict[str, str], str]]]
    """Return ({proposal_id: [contract ids]}, [(contract, reason)] for skipped contracts).

    A contract is applied only when exactly one fetched proposal has its title,
    the contract starts on/after the proposal date, and the proposal is not
    Declined / Withdrawn / Archived.
    """
    by_title = {}  # type: Dict[str, List[Dict[str, Any]]]
    for p in proposals:
        by_title.setdefault(norm_title(p["title"]), []).append(p)
    hires = {}  # type: Dict[str, List[str]]
    unmatched = []  # type: List[Tuple[Dict[str, str], str]]
    for c in contracts:
        nt = norm_title(c["title"])
        cands = by_title.get(nt, []) if nt else []
        if len(cands) != 1:
            reason = ("%d fetched proposals share this title" % len(cands)) if cands \
                else "no fetched proposal has this title"
        else:
            p = cands[0]
            if p["status"] in CLOSED_STATUSES:
                reason = "its proposal is %s" % p["status"]
            elif not c["start"] or not p["created"]:
                reason = "missing contract or proposal date"
            elif c["start"][:10] < p["created"][:10]:
                reason = "contract starts %s, before the proposal (%s)" % (c["start"][:10], p["created"][:10])
            else:
                hires.setdefault(p["proposal_id"], []).append(c["id"])
                continue
        unmatched.append((c, reason))
    return hires, unmatched


def load_json(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------- outcomes

def outcomes_for(p, rooms, no_rooms, hires, insights=None):
    # type: (Dict[str, Any], Dict[str, Any], set, Dict[str, List[str]], Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, str]
    pid = p["proposal_id"]
    yes = set(STATUS_YES.get(p["status"], set()))
    if pid in rooms:
        yes |= {"viewed", "replied"}
    if pid in hires:
        yes |= {"viewed", "replied", "interviewed", "hired"}
    result = {f: "yes" for f in yes}
    seen = viewed_from_insights(p, (insights or {}).get(pid))
    if seen:
        result.setdefault("viewed", seen)
    if p["status"] in CLOSED_STATUSES:
        result.setdefault("hired", "no")
        if pid in no_rooms:  # explicit NOT_FOUND from get_room: the client never messaged
            result.setdefault("replied", "no")
            result.setdefault("interviewed", "no")
    return result


def status_note(p, rooms, hires):
    # type: (Dict[str, Any], Dict[str, Any], Dict[str, List[str]]) -> str
    note = "upwork: %s" % (p["status_label"] or p["status"])
    if p["reason"]:
        note += " (%s)" % p["reason"]
    if p["proposal_id"] in rooms:
        note += ", client messaged"
    cids = hires.get(p["proposal_id"]) or []
    if cids:
        note += ", contract%s %s" % ("s" if len(cids) > 1 else "", ", ".join(cids))
    return note


def match_rows(rows, proposals, skip=(), reserved=(), blocked=None):
    # type: (List[Dict[str, str]], List[Dict[str, Any]], Any, Any, Optional[List[Tuple[int, List[str]]]]) -> Tuple[Dict[int, Tuple[Dict[str, Any], str]], List[Dict[str, Any]], List[Tuple[Dict[str, Any], List[int]]]]
    """Pass 1: job-id matches for every row. Pass 2: title fallback for rows with
    no job id, over proposals whose job id is in no row's job_url and not in
    `reserved` (job ids that belong to skipped rows or unparseable records). A
    proposal is claimed by at most one row. Rows in `skip` never match.

    A row whose normalized title equals the title of any fetched proposal,
    claimed or not, is never prefix-matched: when every proposal with that
    title is already claimed, the row stays unmatched and, if `blocked` is a
    list, (row index, [job ids with that title]) is appended to it.

    Returns (matches, unmatched proposals, ambiguous) where ambiguous lists
    (proposal, [row indexes]) for proposals whose title matches more than one
    URL-less row; none of those rows is matched."""
    by_job = {}  # type: Dict[str, Dict[str, Any]]
    for p in proposals:
        cur = by_job.get(p["job_id"])
        if cur is None or p["modified"] > cur["modified"]:
            by_job[p["job_id"]] = p
    row_jids = [job_id_from_url(r.get("job_url", "")) for r in rows]
    url_jobs = {j for j in row_jids if j} | set(reserved)

    matches = {}  # type: Dict[int, Tuple[Dict[str, Any], str]]
    used = set()
    for i, jid in enumerate(row_jids):
        if i in skip or not jid or jid not in by_job or jid in used:
            continue
        matches[i] = (by_job[jid], "job_id")
        used.add(jid)

    by_title = {}  # type: Dict[str, List[Dict[str, Any]]]
    for p in by_job.values():
        if p["job_id"] not in url_jobs:
            by_title.setdefault(norm_title(p["title"]), []).append(p)
    exact = {}  # type: Dict[str, set]  # title of every fetched proposal -> its job ids
    for p in proposals:
        exact.setdefault(norm_title(p["title"]), set()).add(p["job_id"])
    by_prop = {}  # type: Dict[str, List[int]]  # job id -> URL-less rows whose title picks it
    for i, row in enumerate(rows):
        if i in skip or row_jids[i]:
            continue
        nt = norm_title(row.get("job_title", ""))
        if not nt:
            continue
        cands = by_title.get(nt, [])
        if not cands and nt in exact:
            # Its exact title is a proposal another row already claims; a prefix
            # match could only pick a different job.
            if blocked is not None:
                blocked.append((i, sorted(exact[nt])))
            continue
        if not cands and len(nt) >= 15:
            # Log titles are sometimes truncated: allow a unique prefix match.
            cands = [q for t, ps in by_title.items() if t.startswith(nt) or (nt.startswith(t) and len(t) >= 15)
                     for q in ps]
        if len(cands) == 1 and cands[0]["job_id"] not in used:
            by_prop.setdefault(cands[0]["job_id"], []).append(i)
    ambiguous = []  # type: List[Tuple[Dict[str, Any], List[int]]]
    for jid, idxs in by_prop.items():
        if len(idxs) == 1:
            matches[idxs[0]] = (by_job[jid], "title")
            used.add(jid)
        else:  # several URL-less rows share this title: cannot tell which one applied
            ambiguous.append((by_job[jid], idxs))
    amb_jobs = {p["job_id"] for p, _ in ambiguous}
    unmatched = [p for jid, p in by_job.items() if jid not in used and jid not in amb_jobs]
    return matches, unmatched, ambiguous


def apply_outcomes(rows, matches, rooms, no_rooms, hires, insights=None, fill_boosted=False):
    # type: (List[Dict[str, str]], Dict[int, Tuple[Dict[str, Any], str]], Dict[str, Any], set, Dict[str, List[str]], Optional[Dict[str, Dict[str, Any]]], bool) -> List[Dict[str, Any]]
    """Mutate rows in place; return one change record per changed row.
    fill_boosted: a blank boosted cell gets the proposal's boosted flag (yes/no);
    a filled one is never changed, and a boosted-only change adds no note."""
    changes = []
    for i, (p, how) in sorted(matches.items()):
        row = rows[i]
        new = outcomes_for(p, rooms, no_rooms, hires, insights)
        changed = {}
        for f in OUTCOME_FIELDS:
            v = new.get(f, "")
            cur = (row.get(f) or "").strip()
            if not v or cur == v or cur.lower() == "yes":
                continue
            if cur and not (cur.lower() == "no" and v == "yes"):
                continue  # keep any other hand-entered value
            row[f] = v
            changed[f] = (cur, v)
        note = status_note(p, rooms, hires)
        notes = row.get("notes") or ""
        if row.get(None):
            notes = ",".join([notes] + list(row[None]))
        note_added = False
        if changed and note not in notes:
            row.pop(None, None)
            row["notes"] = (notes + "; " + note) if notes else note
            note_added = True
        if fill_boosted and "boosted" in row and not (row.get("boosted") or "").strip() \
                and p.get("boosted") is not None:
            row["boosted"] = "yes" if p["boosted"] else "no"
            changed["boosted"] = ("", row["boosted"])
        if changed or note_added:
            changes.append({"row": i, "title": row.get("job_title", ""), "how": how,
                            "status": p["status"], "changed": changed})
    return changes


# ---------------------------------------------------------------- io

def _scan(text):
    # type: (str) -> Tuple[List[str], set, bool]
    """Split CSV text into raw records the way the csv module reads them.

    A double quote opens a quoted field only as the first character of a
    field; inside an unquoted field (or after a closing quote) it is literal.
    Inside a quoted field "" is an escaped quote and "\\n" does not end the
    record, with one exception: a quoted field may not run on into a line that
    starts with a date (ROW_START, the next log row). The record is cut right
    after that "\\n" and its index goes in `cut`, so the rows below it are read
    on their own. Records end on "\\n" only (str.splitlines would also break on
    \\f, \\x1c-\\x1e, \\x85, U+2028/U+2029 inside a field). A leading BOM stays
    in the first record but does not count as field text.
    "".join(records) == text always.

    Returns (records, cut, True when the text ends inside a quoted field).
    """
    START, UNQUOTED, QUOTED, QUOTE_IN_QUOTED = 0, 1, 2, 3
    records = []  # type: List[str]
    cut = set()
    state, begin = START, 0
    for k in range(1 if text.startswith(BOM) else 0, len(text)):
        c = text[k]
        if state == QUOTED:
            if c == '"':
                state = QUOTE_IN_QUOTED
            elif c == "\n" and ROW_START.match(text, k + 1):
                cut.add(len(records))  # a quote left open: never swallow the next row
                records.append(text[begin:k + 1])
                begin, state = k + 1, START
            continue
        if state == QUOTE_IN_QUOTED and c == '"':
            state = QUOTED  # "" inside a quoted field
            continue
        if c == "\n":
            records.append(text[begin:k + 1])
            begin, state = k + 1, START
        elif c == ",":
            state = START
        elif state == START and c == '"':
            state = QUOTED
        else:
            state = UNQUOTED
    if begin < len(text):
        records.append(text[begin:])
    return records, cut, state == QUOTED


def _scan_records(text):
    # type: (str) -> Tuple[List[str], bool]
    """(records, True when the text ends inside a quoted field); see _scan."""
    records, _, open_quote = _scan(text)
    return records, open_quote


def split_records(text):
    # type: (str) -> List[str]
    """Raw records of `text`; see _scan."""
    return _scan(text)[0]


def _eol(rec):
    # type: (str) -> str
    if rec.endswith("\r\n"):
        return "\r\n"
    return "\n" if rec.endswith("\n") else ""


def read_text(path):
    # type: (str) -> str
    with open(path, newline="", encoding="utf-8") as f:
        return f.read()


def fingerprint(path):
    # type: (str) -> Tuple[int, int, str]
    """(size, mtime_ns, sha256) of `path`, stat taken from the same open file."""
    with open(path, "rb") as f:
        data = f.read()
        st = os.fstat(f.fileno())
    return st.st_size, st.st_mtime_ns, hashlib.sha256(data).hexdigest()


def _fits(col, v):
    # type: (str, str) -> bool
    """True when value `v` is acceptable in column `col` (see FOLD_RULES)."""
    rule = FOLD_RULES.get(col)
    return rule is None or (v == "" and col in BLANK_OK) or bool(rule.match(v))


def fold_problems(row, header):
    # type: (Dict[Any, Any], List[str]) -> List[str]
    """Why a row with extra fields cannot be synced; [] means the fold fits.

    The overflow is folded into notes (the last column) and every column before
    notes must then pass FOLD_RULES. Any failure means the extra comma sits
    somewhere else and the columns are shifted. A fit is still only safe when
    fold_alternative() finds no other place for the commas.
    """
    if not header or header[-1] != "notes":
        return ["last column is not notes"]
    missing = [c for c in FOLD_RULES if c not in header]
    if missing:
        return ["no column %s to check" % ", ".join(missing)]
    return ["%s=%r" % (col, (row.get(col) or "")[:40]) for col in header[:-1]
            if not _fits(col, row.get(col) or "")]


def fold_alternative(vals, header):
    # type: (List[str], List[str]) -> Optional[str]
    """For a row with more fields than columns whose fold into notes passes
    fold_problems(): a text column other than notes that could hold the extra
    commas just as well, or None when notes is the only place they fit.

    Extra commas in any unchecked text column (job_title, build_slug or
    opener_variant) push the checked columns after the last of those
    (opener_visible_chars .. hired) right by the same count, and the earlier
    checked columns are the ones fold_problems() already passed. So trying that
    last block at every shift 1..extra settles it: if a shifted reading also
    passes FOLD_RULES (e.g. opener "variant,2" with blank connects), which
    columns hold which values is a guess and the row must be skipped.
    """
    extra = len(vals) - len(header)
    j = len(header) - 1  # notes
    while j > 0 and header[j - 1] in FOLD_RULES:
        j -= 1
    if j == 0:
        return None  # every column before notes is checked: the commas can only be in notes
    for s in range(1, extra + 1):
        if all(_fits(header[c], vals[c + s]) for c in range(j, len(header) - 1)):
            return header[j - 1]
    return None


def _job_ids(raw, job_url=""):
    # type: (str, str) -> List[str]
    """Job ids of every Upwork job URL in a raw record, plus its job_url column's
    (a skipped row's columns may be shifted, so the raw text is searched)."""
    ids = [job_id_from_url(m.group(1)) for m in JOB_URL_IN_TEXT.finditer(raw)]
    ids.append(job_id_from_url(job_url))
    return [j for j in ids if j]


def _line_span(first, rec):
    # type: (int, str) -> str
    last = first + rec.rstrip("\n").count("\n")
    return "line %d" % first if last == first else "lines %d-%d" % (first, last)


def read_csv(path):
    # type: (str) -> Tuple[List[str], List[Dict[str, str]], Dict[str, Any]]
    """Return header, rows, and doc = {records, row_rec, skip, bad, skipped_jobs}.

    records: every raw record of the file (header, blank lines included);
    row_rec[i]: index into records of row i; skip: {row index: reason} for
    malformed rows the sync must not match, rewrite or count; bad: [(record
    index, reason)] for records that do not parse at all (they are not rows);
    skipped_jobs: {job id: "row N" / "record at line N"} for every Upwork job URL in a
    skipped row or bad record, so its proposal is never title-matched to
    another row and is listed as belonging to that row.

    Skipped: a record _scan() cut (a quote left open before the next row), any
    other record spanning more than one line, a row with fewer fields than the
    header (never padded), and a row with more fields unless fold_problems()
    and fold_alternative() both find nothing; such a row keeps the overflow
    under row[None] and fold_overflow puts it back into notes if the row is
    rewritten. Skipped rows and bad records are copied byte-for-byte.
    """
    records, cut, open_quote = _scan(read_text(path))
    head = records[0] if records else ""
    if head.startswith(BOM):
        head = head[len(BOM):]  # parse without it; records[0] keeps it for the write
    try:
        header = next(csv.reader([head])) if records else []
    except (csv.Error, StopIteration) as e:
        raise SystemExit("proposals.csv header does not parse (%s)" % e)
    missing = [c for c in ["job_url", "job_title"] + OUTCOME_FIELDS + ["notes"] if c not in header]
    if missing:
        raise SystemExit("proposals.csv is missing columns: %s" % ", ".join(missing))
    rows, row_rec, skip, bad = [], [], {}, []  # type: List[Dict[Any, Any]], List[int], Dict[int, str], List[Tuple[int, str]]
    line = 1 + (records[0].count("\n") if records else 0)
    for ri in range(1, len(records)):
        rec = records[ri]
        first, line = line, line + rec.count("\n")
        if not rec.strip():
            continue
        where = _line_span(first, rec)
        if open_quote and ri == len(records) - 1:
            bad.append((ri, "%s: a quoted field is never closed and runs to the end of the file" % where))
            continue
        try:
            parsed = list(csv.reader([rec]))
        except csv.Error as e:
            bad.append((ri, "%s: does not parse as CSV (%s)" % (where, e)))
            continue
        if len(parsed) != 1:
            bad.append((ri, "%s: parses as %d records" % (where, len(parsed))))
            continue
        vals = parsed[0]
        row = dict(zip(header, vals))  # type: Dict[Any, Any]
        for k in header[len(vals):]:
            row[k] = ""  # for the warning text only; a skipped row is never matched, counted or written
        reason = ""
        if ri in cut:
            reason = ("%s: a quoted field is not closed before line %d, which starts the next row"
                      % (where, line))
        elif "\n" in rec[:-1]:
            reason = ("%s: a quoted field runs over more than one line (a quote left open, or a line "
                      "break inside a field)" % where)
        elif len(vals) < len(header):
            reason = "%s: %d fields for %d columns (short row)" % (where, len(vals), len(header))
        elif len(vals) > len(header):
            row[None] = vals[len(header):]
            folded = dict(row)
            folded["notes"] = ",".join([row.get("notes", "")] + list(row[None]))
            problems = fold_problems(folded, header)
            alt = None if problems else fold_alternative(vals, header)
            if problems:
                reason = ("%s: %d fields for %d columns; with the extra folded into notes these "
                          "columns do not fit: %s" % (where, len(vals), len(header), ", ".join(problems)))
            elif alt:
                reason = ("%s: %d fields for %d columns; the extra comma could be in %s (or an earlier "
                          "text column) as well as in notes, so which columns shifted is unclear"
                          % (where, len(vals), len(header), alt))
        if reason:
            skip[len(rows)] = reason
        rows.append(row)
        row_rec.append(ri)
    skipped_jobs = {}  # type: Dict[str, str]
    for i in sorted(skip):
        for jid in _job_ids(records[row_rec[i]], rows[i].get("job_url") or ""):
            skipped_jobs.setdefault(jid, "row %d" % (i + 1))
    for ri, reason in bad:
        for jid in _job_ids(records[ri]):
            skipped_jobs.setdefault(jid, "record at " + reason.split(":", 1)[0])
    return header, rows, {"records": records, "row_rec": row_rec, "skip": skip, "bad": bad,
                          "skipped_jobs": skipped_jobs}


def fold_overflow(row, header):
    extra = row.pop(None, None)
    if extra and header and header[-1] == "notes":
        row["notes"] = ",".join([row.get("notes", "")] + list(extra))


def render_row(row, header, eol):
    # type: (Dict[Any, Any], List[str], str) -> str
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow([row.get(k, "") for k in header])
    return buf.getvalue()[:-1] + eol


def write_csv(path, header, rows, doc, changed_idx, backup=False):
    """Rewrite only changed rows; every other record is copied byte-for-byte.

    The temp file is re-read and verified (record count, every unchanged
    record identical, every changed record parses to the intended values)
    before it replaces `path`; on any mismatch it is deleted and `path` is
    left alone. Immediately before the replace, `path` is re-checked (size,
    mtime, sha256 as of the start of this call) and the write aborts if another
    process changed it. backup=True leaves the replaced file as `path`.bak.
    """
    orig = doc["records"]
    fp = fingerprint(path)
    if fp[2] != hashlib.sha256("".join(orig).encode("utf-8")).hexdigest():
        raise SystemExit("ABORT: %s changed since it was read; nothing written." % path)
    new = list(orig)
    changed_rec = {}  # type: Dict[int, List[str]]
    for i in changed_idx:
        if i in doc["skip"]:
            raise SystemExit("ABORT: refusing to rewrite malformed row %d; nothing written." % (i + 1))
        r = rows[i]
        fold_overflow(r, header)
        ri = doc["row_rec"][i]
        new[ri] = render_row(r, header, _eol(orig[ri]))
        changed_rec[ri] = [r.get(k, "") for k in header]

    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".proposals.", suffix=".csv")
    tmp_bak = tmp + ".bak"
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            f.write("".join(new))
        got = split_records(read_text(tmp))
        problems = []
        if len(got) != len(orig):
            problems.append("record count %d != %d" % (len(got), len(orig)))
        else:
            for ri, rec in enumerate(got):
                if ri in changed_rec:
                    if rec != new[ri] or next(csv.reader([rec])) != changed_rec[ri]:
                        problems.append("changed record %d does not read back" % ri)
                elif rec != orig[ri]:
                    problems.append("unchanged record %d differs" % ri)
        if problems:
            raise SystemExit("ABORT: verification failed (%s); %s not replaced."
                             % ("; ".join(problems[:5]), path))
        shutil.copymode(path, tmp)
        if backup:  # staged under a temp name; becomes .bak only if the check below passes
            shutil.copy2(path, tmp_bak)
        # Last check, immediately before the replace: another process may have
        # written the CSV while we worked (and the backup must be what we read).
        if fingerprint(path) != fp or (backup and fingerprint(tmp_bak)[2] != fp[2]):
            raise SystemExit("ABORT: %s changed since it was read (size, mtime or content differ); "
                             "not replaced. Re-run the sync." % path)
        if backup:
            os.replace(tmp_bak, path + ".bak")
        os.replace(tmp, path)
    finally:
        for t in (tmp, tmp_bak):
            if os.path.exists(t):
                os.unlink(t)


# ---------------------------------------------------------------- report

def _pct(k, n):
    return "%d/%d %3.0f%%" % (k, n, 100.0 * k / n) if n else "0/0    -"


def report(rows, out=sys.stdout, label="", skip=None, bad=()):
    """Rates by platform and opener_variant over well-formed rows only.

    Rows in `skip` hold shifted or missing columns and records in `bad` do not
    parse, so none of them is in any group or the ALL line; they are named on
    a separate "not counted" line under each table instead.
    """
    skip = skip or {}
    counted = [r for i, r in enumerate(rows) if i not in skip]
    left_out = (["row %d" % (i + 1) for i in sorted(skip)]
                + ["record at %s" % reason.split(":", 1)[0] for _, reason in bad])
    for dim in ("platform", "opener_variant"):
        groups = {}  # type: Dict[str, List[Dict[str, str]]]
        for r in counted:
            groups.setdefault((r.get(dim) or "(blank)").strip() or "(blank)", []).append(r)
        width = max([len(dim)] + [len(g) for g in groups])
        out.write("\nRates by %s (yes / all rows in group)%s\n" % (dim, (" " + label) if label else ""))
        out.write("%-*s  %4s  %-12s  %-12s  %-12s  %-12s\n"
                  % (width, dim, "n", "viewed", "replied", "interviewed", "hired"))
        for g in sorted(groups, key=lambda k: (-len(groups[k]), k)):
            rs = groups[g]
            n = len(rs)
            cells = [_pct(sum(1 for r in rs if (r.get(f) or "").strip().lower() == "yes"), n)
                     for f in OUTCOME_FIELDS]
            out.write("%-*s  %4d  %-12s  %-12s  %-12s  %-12s\n" % ((width, g, n) + tuple(cells)))
        n = len(counted)
        cells = [_pct(sum(1 for r in counted if (r.get(f) or "").strip().lower() == "yes"), n)
                 for f in OUTCOME_FIELDS]
        out.write("%-*s  %4d  %-12s  %-12s  %-12s  %-12s\n" % ((width, "ALL", n) + tuple(cells)))
        if left_out:
            out.write("not counted (malformed, fix by hand): %s\n" % ", ".join(left_out))


# ---------------------------------------------------------------- main

def summarize(rows, matches, changes, unmatched, unmatched_contracts=(), skip=None, out=sys.stdout,
              bad=(), ambiguous=(), blocked=(), skipped_jobs=None):
    by_how = {"job_id": 0, "title": 0}
    for _, how in matches.values():
        by_how[how] += 1
    out.write("Rows in log: %d | matched: %d (job_id %d, title %d) | unmatched rows: %d\n"
              % (len(rows), len(matches), by_how["job_id"], by_how["title"], len(rows) - len(matches)))
    for i, reason in sorted((skip or {}).items()):
        out.write("WARNING: skipped malformed row %d (%s): %s; left byte-for-byte, fix it by hand\n"
                  % (i + 1, (rows[i].get("job_title") or "")[:50], reason))
    for _, reason in bad:
        out.write("WARNING: skipped malformed record, %s; left byte-for-byte, fix it by hand\n" % reason)
    for p, idxs in ambiguous:
        out.write("AMBIGUOUS: %d URL-less rows (%s) share the title of proposal %r (job %s, %s); "
                  "none updated, add the job_url to the right row\n"
                  % (len(idxs), ", ".join("row %d" % (i + 1) for i in idxs), p["title"][:60], p["job_id"],
                     p["status"]))
    for i, jids in blocked:
        out.write("UNMATCHED: row %d (%s) has no job_url and its exact title is that of job %s, already "
                  "claimed by another row; not prefix-matched to a different job. Add this row's job_url\n"
                  % (i + 1, (rows[i].get("job_title") or "")[:50], ", ".join(jids)))
    fields = list(OUTCOME_FIELDS)
    if any("boosted" in c["changed"] for c in changes):
        fields.append("boosted")
    newly = {f: {"yes": 0, "no": 0} for f in fields}
    for c in changes:
        for f, (_, v) in c["changed"].items():
            newly[f][v] += 1
    out.write("Newly marked: " + ", ".join("%s +%d yes / +%d no" % (f, newly[f]["yes"], newly[f]["no"])
                                           for f in fields) + "\n")
    if changes:
        out.write("\nChanged rows:\n")
        for c in changes:
            fields = ", ".join("%s=%s" % (f, v) for f, (_, v) in c["changed"].items()) or "note only"
            out.write("  [%s via %s] %s: %s\n" % (c["status"], c["how"], c["title"][:60], fields))
    skipped_jobs = skipped_jobs or {}
    owned = [p for p in unmatched if p["job_id"] in skipped_jobs]
    free = [p for p in unmatched if p["job_id"] not in skipped_jobs]
    first = min((r.get("applied_at") or "" for r in rows if r.get("applied_at")), default="")
    recent = [p for p in free if not first or p["created"][:10] >= first[:10]]
    older = len(free) - len(recent)
    out.write("\nUnmatched proposals since log start (%s): %d (plus %d older)\n"
              % (first[:10] or "n/a", len(recent), older))
    for p in sorted(recent, key=lambda x: x["created"], reverse=True):
        out.write("  %s  %-10s %s  (job %s)\n" % (p["created"][:10], p["status"], p["title"][:70], p["job_id"]))
    if owned:
        out.write("\nProposals that belong to a skipped row (not updated until the row is fixed): %d\n"
                  % len(owned))
        for p in sorted(owned, key=lambda x: x["created"], reverse=True):
            out.write("  %s  %-10s %s  (job %s, belongs to skipped %s)\n"
                      % (p["created"][:10], p["status"], p["title"][:70], p["job_id"], skipped_jobs[p["job_id"]]))
    if unmatched_contracts:
        out.write("\nUnmatched contracts (not applied): %d\n" % len(unmatched_contracts))
        for c, reason in unmatched_contracts:
            out.write("  contract %s  %s  (%s)\n" % (c["id"], c["title"][:60], reason))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--proposals", help="saved list_freelancer_proposals JSON ('-' for stdin)")
    ap.add_argument("--rooms", help="saved {proposal_id: get_room response} JSON")
    ap.add_argument("--contracts", help="saved list_contracts search JSON")
    ap.add_argument("--insights", help="saved {proposal_id: list_freelancer_proposals action=get response} JSON "
                                       "(its insights can set viewed \"no\" on an open proposal, never \"yes\")")
    ap.add_argument("--fill-boosted", action="store_true",
                    help="also fill blank boosted cells (yes/no) from each matched proposal")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--dry-run", action="store_true", help="write to a temp copy and print a diff")
    ap.add_argument("--report", action="store_true", help="print rates by platform and opener_variant")
    args = ap.parse_args(argv)
    if not args.proposals and not args.report:
        ap.error("pass --proposals and/or --report")

    header, rows, doc = read_csv(args.csv)
    if not args.proposals:  # report only: say what the rates leave out
        for i, reason in sorted(doc["skip"].items()):
            print("WARNING: skipped malformed row %d (%s): %s; not counted in the report"
                  % (i + 1, (rows[i].get("job_title") or "")[:50], reason))
        for _, reason in doc["bad"]:
            print("WARNING: skipped malformed record, %s; not counted in the report" % reason)

    if args.proposals:
        proposals = extract_proposals(load_json(args.proposals))
        rooms, no_rooms = extract_rooms(load_json(args.rooms)) if args.rooms else ({}, set())
        contracts = extract_contracts(load_json(args.contracts)) if args.contracts else []
        insights = extract_insights(load_json(args.insights)) if args.insights else {}
        hires, unmatched_contracts = match_contracts(contracts, proposals)
        print("Loaded %d proposals, %d rooms (+%d NOT_FOUND), %d contracts (%d applied)%s"
              % (len(proposals), len(rooms), len(no_rooms), len(contracts),
                 len(contracts) - len(unmatched_contracts),
                 (", %d insights" % len(insights)) if args.insights else ""))
        blocked = []  # type: List[Tuple[int, List[str]]]
        matches, unmatched, ambiguous = match_rows(rows, proposals, skip=doc["skip"],
                                                   reserved=doc["skipped_jobs"], blocked=blocked)
        changes = apply_outcomes(rows, matches, rooms, no_rooms, hires, insights, args.fill_boosted)
        summarize(rows, matches, changes, unmatched, unmatched_contracts, doc["skip"],
                  bad=doc["bad"], ambiguous=ambiguous, blocked=blocked, skipped_jobs=doc["skipped_jobs"])

        changed = {c["row"] for c in changes}
        if not changes:
            print("\nNo new outcome info; nothing written.")
        elif args.dry_run:
            tmpdir = tempfile.mkdtemp(prefix="sync_outcomes_")
            try:
                target = os.path.join(tmpdir, os.path.basename(args.csv))
                shutil.copyfile(args.csv, target)
                before = split_records(read_text(target))
                write_csv(target, header, rows, doc, changed, backup=False)
                after = split_records(read_text(target))
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
            print("\nDry run: wrote the synced file to a temp copy, diffed it and removed it (%s untouched)"
                  % args.csv)
            sys.stdout.writelines(difflib.unified_diff(before, after, "proposals.csv", "proposals.csv (synced)"))
        else:
            write_csv(args.csv, header, rows, doc, changed, backup=True)
            print("\nWrote %d changed rows to %s (backup: %s.bak)" % (len(changes), args.csv, args.csv))

    if args.report:
        report(rows, label="(dry run, not written)" if args.dry_run else "", skip=doc["skip"], bad=doc["bad"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
