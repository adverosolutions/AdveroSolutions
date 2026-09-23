"""The non-API inputs: git log, Rize hours, audit logs, staged Gmail pulls.

Every function here returns a ``Source``: a value plus whether it was really
read and, when it was not, the reason in words Lorenzo can act on. Nothing
raises, nothing invents, and nothing that is missing turns into a zero.

Two of these inputs can only be fetched inside a Claude session, not from a
cron job: the Instantly and GHL audit logs (MCP-only reads today, since
``shared.instantly`` has no audit-log method) and the Fireflies recap emails
(the Gmail connector is session-scoped and there is no Gmail API credential in
.env). Both follow the pattern ``jobs/pipeline_sweep.py`` already uses for the
Upwork MCP: a session writes a JSON file, the job reads it if it is there.
"""
import csv
import json
import logging
import os
import re
import subprocess
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from shared.paths import ROOT_DIR, tmp_dir

logger = logging.getLogger("services.retro.sources")

STAGED_DIR_ENV = "RETRO_STAGE_DIR"
RECAPS_ENV = "RETRO_RECAPS_PATH"
AUDIT_ENV = "RETRO_AUDIT_PATH"
RIZE_ENV = "RIZE_EXPORT_PATH"

GIT_MAX_COMMITS = 400


class Source(object):
    """A retro input and the truth about where it came from."""

    def __init__(self, name, value=None, ok=False, reason="", origin=""):
        # type: (str, Any, bool, str, str) -> None
        self.name = name
        self.value = value
        self.ok = ok
        self.reason = reason
        self.origin = origin

    def as_dict(self):
        return {"name": self.name, "ok": self.ok, "reason": self.reason,
                "origin": self.origin, "value": self.value}

    def __repr__(self):
        return "Source(%s, ok=%s, %r)" % (self.name, self.ok, self.reason)


def stage_dir():
    override = os.environ.get(STAGED_DIR_ENV)
    if override:
        return override
    return str(tmp_dir() / "retro")


def recaps_path():
    # type: () -> str
    """Read the literal constant, not a parameter: shared/tests/test_settings.py
    walks the AST for ``os.environ.get(<literal or module constant>)`` so every
    key a deployed job reads can be registered in modal_app. A key hidden behind
    a function parameter passes that check without being deployable."""
    return os.environ.get(RECAPS_ENV) or os.path.join(stage_dir(), "call_recaps.json")


def audit_path():
    # type: () -> str
    return os.environ.get(AUDIT_ENV) or os.path.join(stage_dir(), "audit_logs.json")


def read_json_file(path):
    # type: (str) -> Any
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------------- git log
COMMIT_FIELDS = ("hash", "date", "author", "subject")
# Commits written by the vault/compiler loop, hundreds a week, none of which is
# a "system change" anybody wants listed one by one.
NOISE_PREFIXES = ("Vault:", "vault:", "wip", "WIP", "Merge branch", "Merge pull request")


def git_log(since, until, repo=None):
    # type: (str, str, Optional[str]) -> Source
    """Commits in [since, until) as {hash, date, author, subject}.

    ``since``/``until`` are ``YYYY-MM-DD``; ``until`` is exclusive, so pass the
    day after the last day you want.
    """
    repo = repo or str(ROOT_DIR)
    cmd = [
        "git", "-C", repo, "log",
        "--since=%s 00:00:00" % since, "--until=%s 00:00:00" % until,
        "--pretty=format:%H\t%aI\t%an\t%s", "--no-merges", "-n", str(GIT_MAX_COMMITS),
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Source("git", [], False, "git log failed: %s" % exc, repo)
    if proc.returncode != 0:
        return Source("git", [], False,
                      "git log exited %d: %s" % (proc.returncode,
                                                 proc.stderr.decode("utf-8", "replace")[:200]), repo)
    commits = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        commits.append(dict(zip(COMMIT_FIELDS, parts[:4])))
    return Source("git", commits, True, "", repo)


def group_commits(commits):
    # type: (List[Dict[str, str]]) -> Dict[str, Any]
    """Split commits into the ones worth reading and the machine-written bulk.

    The repo takes hundreds of "Vault: <name> via compiler engine" commits a
    week. Printed one per line they bury the three commits that actually
    changed the system, which is the whole point of the section.
    """
    notable = []
    noise = OrderedDict()  # type: Dict[str, int]
    for commit in commits or []:
        subject = commit.get("subject", "")
        prefix = None
        for candidate in NOISE_PREFIXES:
            if subject.startswith(candidate):
                prefix = candidate.rstrip(":")
                break
        if prefix:
            noise[prefix] = noise.get(prefix, 0) + 1
        else:
            notable.append(commit)
    return {"notable": notable, "rolled_up": noise, "total": len(commits or [])}


# --------------------------------------------------------------- audit logs
def audit_logs(path=None, window=None):
    # type: (Optional[str], Optional[Any]) -> Source
    """Instantly / GHL audit-log entries staged by a Claude session.

    Expected shape: {"instantly": [{ts, actor, action, target}], "ghl": [...]}.
    ``shared.instantly`` has no audit-log read method (see the cross-cutting
    request in the A10 report), so a cron run can never fetch these itself.

    **Entries outside ``window`` are dropped.** The file is staged by hand, so
    a session that stages it once and forgets it leaves a handoff on disk
    forever; without this filter a July pause showed up under "System changes
    ... in the window" of every retro from then on. When the file exists but
    nothing in it falls inside the window, the source stays ok and the reason
    says how old the newest entry is, so "no audit entries" is distinguishable
    from "the file is stale".
    """
    path = path or audit_path()
    empty = {"instantly": [], "ghl": []}
    if not os.path.exists(path):
        return Source(
            "audit_logs", dict(empty), False,
            "no staged audit log at %s (Instantly audit logs are MCP-only today, and there is no "
            "GHL Private Integration token)" % path, path)
    try:
        data = read_json_file(path)
    except (OSError, ValueError) as exc:
        return Source("audit_logs", dict(empty), False,
                      "staged audit log unreadable: %s" % exc, path)
    if not isinstance(data, dict):
        return Source("audit_logs", dict(empty), False,
                      "staged audit log is not an object", path)
    data.setdefault("instantly", [])
    data.setdefault("ghl", [])
    if window is None:
        return Source("audit_logs", data, True, "", path)
    kept = {}
    dropped = 0
    newest = ""
    for system in ("instantly", "ghl"):
        rows = []
        for entry in data.get(system) or []:
            stamp = str((entry or {}).get("ts") or "")
            newest = max(newest, stamp)
            if window.contains_date(stamp):
                rows.append(entry)
            else:
                dropped += 1
        kept[system] = rows
    reason = ""
    if dropped and not (kept["instantly"] or kept["ghl"]):
        reason = ("the staged audit log at %s has %d entr%s in it but none inside %s to %s; the "
                  "newest is %s, so the file is stale"
                  % (path, dropped, "y" if dropped == 1 else "ies",
                     window.start_date, window.end_date, newest[:10] or "undated"))
    elif dropped:
        reason = "%d staged audit entr%s fell outside the window and were dropped" % (
            dropped, "y" if dropped == 1 else "ies")
    return Source("audit_logs", kept, True, reason, path)


# ------------------------------------------------------------ call recaps
def staged_recaps(path=None):
    # type: (Optional[str]) -> Source
    """Raw Fireflies messages staged by a session with the Gmail connector."""
    path = path or recaps_path()
    if not os.path.exists(path):
        return Source(
            "recaps", [], False,
            "no staged Fireflies pull at %s (the Gmail connector only exists inside a Claude "
            "session; runbooks/retro.md has the query and the file shape)" % path, path)
    try:
        data = read_json_file(path)
    except (OSError, ValueError) as exc:
        return Source("recaps", [], False, "staged Fireflies pull unreadable: %s" % exc, path)
    if isinstance(data, dict):
        data = data.get("messages") or []
    if not isinstance(data, list):
        return Source("recaps", [], False, "staged Fireflies pull is not a list of messages", path)
    return Source("recaps", data, True, "", path)


# ------------------------------------------------------------------- Rize
DURATION_COLUMNS = ("duration", "duration (hours)", "hours", "time", "duration_seconds",
                    "duration (minutes)", "minutes", "total time", "tracked")
CATEGORY_COLUMNS = ("category", "type", "project", "label", "bucket", "tag")
HMS = re.compile(r"^(\d+):([0-5]\d)(?::([0-5]\d))?$")


def _hours_from(value, column_name):
    # type: (str, str) -> Optional[float]
    """Rize exports a duration as h:mm:ss, as decimal hours, or as seconds in a
    column that says so. Guessing wrong turns 45 minutes into 45 hours, so the
    unit comes from the column name and the format, never from the magnitude."""
    text = (value or "").strip()
    if not text:
        return None
    match = HMS.match(text)
    if match:
        hours = int(match.group(1)) + int(match.group(2)) / 60.0
        if match.group(3):
            hours += int(match.group(3)) / 3600.0
        return hours
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None
    lowered = column_name.lower()
    if "second" in lowered:
        return number / 3600.0
    if "minute" in lowered:
        return number / 60.0
    return number


DATE_COLUMNS = ("date", "day", "start", "start time", "start date", "started at",
                "start_time", "timestamp", "week")


def rize_hours(path=None, window=None):
    # type: (Optional[str], Optional[Any]) -> Source
    """Hours by category from a Rize CSV export at RIZE_EXPORT_PATH.

    **Only rows inside ``window`` are summed.** Rize exports whatever range you
    ask it for, and the obvious mistake is to export a month, or to leave last
    month's file at the path: without the filter the packet printed "Sales 46.0
    h, Build 35.5 h, Total 81.5 h" as this week's hours for a week in which the
    file held nothing at all. If the export carries no recognisable date column
    the hours are still summed, because that is better than nothing, and the
    reason says the range could not be checked.
    """
    path = path or os.environ.get(RIZE_ENV)
    if not path:
        return Source("rize", {}, False,
                      "RIZE_EXPORT_PATH is not set (export a week from Rize and point the variable "
                      "at the CSV; see runbooks/retro.md)", "")
    if not os.path.exists(path):
        return Source("rize", {}, False, "no Rize export at %s" % path, path)
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, ValueError, csv.Error) as exc:
        return Source("rize", {}, False, "Rize export unreadable: %s" % exc, path)
    if not rows:
        return Source("rize", {}, False, "Rize export is empty", path)
    headers = list(rows[0].keys())
    lowered = dict((h.lower().strip(), h) for h in headers if h)
    duration_col = None
    for candidate in DURATION_COLUMNS:
        if candidate in lowered:
            duration_col = lowered[candidate]
            break
    category_col = None
    for candidate in CATEGORY_COLUMNS:
        if candidate in lowered:
            category_col = lowered[candidate]
            break
    if not duration_col or not category_col:
        return Source("rize", {}, False,
                      "Rize export has no recognisable duration/category columns (saw %s)"
                      % ", ".join(headers[:8]), path)
    date_col = None
    for candidate in DATE_COLUMNS:
        if candidate in lowered:
            date_col = lowered[candidate]
            break
    totals = {}  # type: Dict[str, float]
    skipped = 0
    outside = 0
    for row in rows:
        if window is not None and date_col is not None:
            if not window.contains_date((row.get(date_col) or "").strip()):
                outside += 1
                continue
        hours = _hours_from(row.get(duration_col) or "", duration_col)
        if hours is None:
            skipped += 1
            continue
        category = (row.get(category_col) or "Uncategorised").strip() or "Uncategorised"
        totals[category] = totals.get(category, 0.0) + hours
    notes = []
    if skipped:
        notes.append("%d rows had no readable duration" % skipped)
    if outside:
        notes.append("%d rows fell outside %s to %s and were not counted"
                     % (outside, window.start_date, window.end_date))
    if window is not None and date_col is None:
        notes.append("the export has no date column (saw %s), so the whole file was summed and "
                     "the range could not be checked" % ", ".join(headers[:8]))
    if window is not None and date_col is not None and not totals:
        notes.append("no row in the export falls inside %s to %s"
                     % (window.start_date, window.end_date))
    return Source("rize", totals, True, "; ".join(notes), path)


# ------------------------------------------------------------------ job log
def job_log_rows(path=None, window=None):
    # type: (Optional[str], Optional[Any]) -> Source
    """Job_Log rows for the window, so the retro can say what the machine did.

    ``ts_utc`` is UTC, as the name says, and ``Window.contains_date`` converts
    to CT before comparing, so a job that ran at 20:00 CT on Friday is counted
    on Friday rather than on Saturday.
    """
    path = path or os.environ.get("JOB_LOG_PATH") or str(tmp_dir() / "job_log.csv")
    if not os.path.exists(path):
        return Source("job_log", [], False, "no Job_Log at %s" % path, path)
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, ValueError, csv.Error) as exc:
        return Source("job_log", [], False, "Job_Log unreadable: %s" % exc, path)
    if window is not None:
        rows = [r for r in rows if window.contains_date(r.get("ts_utc"))]
    return Source("job_log", rows, True, "", path)


def summarise_job_log(rows):
    # type: (List[Dict[str, str]]) -> List[List[Any]]
    """[job, runs, statuses] ordered by runs desc."""
    by_job = OrderedDict()  # type: Dict[str, Dict[str, int]]
    for row in rows or []:
        job = row.get("job") or "?"
        status = row.get("status") or "?"
        bucket = by_job.setdefault(job, {})
        bucket[status] = bucket.get(status, 0) + 1
    out = []
    for job, statuses in by_job.items():
        total = sum(statuses.values())
        detail = ", ".join("%s %d" % (k, v) for k, v in sorted(statuses.items()))
        out.append([job, total, detail])
    out.sort(key=lambda r: -r[1])
    return out
