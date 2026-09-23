"""Job_Log and shadow log writers.

log_run(job, status, details)  -> CSV row in .tmp/job_log.csv (+ Google Sheet
                                  tab "Job_Log" when JOB_LOG_SHEET_ID is set
                                  AND the process is live; in shadow the sheet
                                  append is recorded as an intent instead)
shadow(system, action, payload) -> JSONL row in .tmp/shadow_log.jsonl

Both create their directories and never raise: any failure is logged as a
warning so a logging problem can never break a job or a shadow run.

On Modal (RUNTIME=modal) both files live on the container's temporary disk
and vanish with it, so every row and every shadow record is ALSO:

* printed to stdout as one ``ADVERO_RECORD {json}`` line (it shows in
  ``modal app logs``) carrying only kind, time, job/system, status/action
  and mode; and
* written to the deployed EVIDENCE Dict (shared.store.get_obs_store: its own
  Dict per mode, never the engine's) under ``obs:job:<ts>:<id>`` or
  ``obs:shadow:<ts>:<id>``, one key per record (no read-modify-write, so two
  containers can never lose each other's rows).

That is what makes the 48-hour shadow gate readable (GOL-2):
``changesets/deploy/watch_report.py`` reads those keys back.

What is mirrored is only what the gate reads, and redacted (review item 4):
a Job_Log row keeps ts/job/status/mode plus ``exit_code``, ``error``,
``reason`` and ``result_type`` from its details; a shadow record keeps its
payload for the would_do review. Every mirrored value goes through redact():
URLs on the deployment's host (any ``*.modal.run`` host, and the host of
BASE_URL / REPLY_ENGINE_BASE_URL) become ``<redacted-url host>`` and the
``actions`` and ``click`` fields (the signed Approve/Veto links of an
approval card) become ``<redacted>``. settings.guard_write applies the same
redact() to the live_write_intent row it logs, which also reaches the Job_Log
sheet. The laptop CSV and shadow log are unchanged.
"""
import csv
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

from shared.paths import BASE_DIR, ROOT_DIR, tmp_dir, tmp_file

logger = logging.getLogger("shared.job_log")

JOB_LOG_HEADER = ["ts_utc", "job", "status", "mode", "details"]
SHEET_TAB = "Job_Log"

# Deployed-evidence mirror (see the module docstring).
OBS_PREFIX = "obs:"
OBS_JOB_PREFIX = OBS_PREFIX + "job:"
OBS_SHADOW_PREFIX = OBS_PREFIX + "shadow:"
RECORD_TAG = "ADVERO_RECORD"
# A modal.Dict value and a log line both have practical limits, and a shadow
# payload can carry a whole drafted email. Anything bigger is kept as a
# preview and marked, never silently dropped.
OBS_MAX_CHARS = 16000
OBS_PREVIEW_CHARS = 2000
# The Job_Log details the gate reads; everything else stays on the laptop CSV.
MIRROR_JOB_DETAIL_KEYS = ("exit_code", "error", "reason", "result_type", "started_at")
MIRROR_TEXT_CHARS = 500
# Fields that carry signed approval links (shared.notify: the card's buttons
# and its tap target). Dropped wherever they appear in a mirrored value.
REDACTED_FIELDS = ("actions", "click")
REDACTED = "<redacted>"
DEPLOYMENT_HOST_SUFFIX = ".modal.run"
BASE_URL_KEYS = ("REPLY_ENGINE_BASE_URL", "BASE_URL")
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


def job_log_path() -> Path:
    override = os.environ.get("JOB_LOG_PATH")
    return Path(override) if override else tmp_file("job_log.csv")


def shadow_log_path() -> Path:
    override = os.environ.get("SHADOW_LOG_PATH")
    return Path(override) if override else tmp_file("shadow_log.jsonl")


def job_log_read_path() -> Path:
    """The Job_Log a READER wants, even inside a scratch redirect.

    ``use_scratch_logs()`` repoints ``JOB_LOG_PATH`` process-wide, so a job
    that reads the Job_Log during its own ``--dry-run`` (the KPI dashboard, the
    retro packet, the Upwork response-time metric) was reading the empty
    scratch file it had just created and reporting "no runs". Three jobs worked
    around it by capturing the path before the redirect. This is that, once:
    the pre-redirect path is remembered in ``JOB_LOG_READ_PATH`` and readers
    resolve through here.
    """
    real = os.environ.get("JOB_LOG_READ_PATH")
    return Path(real) if real else job_log_path()


def use_scratch_logs(name: str, extra_env: Optional[Dict[str, str]] = None) -> Path:
    """Point JOB_LOG_PATH and SHADOW_LOG_PATH at a per-run scratch directory.

    ``extra_env`` redirects the caller's OWN evidence artifacts into the same
    directory: ``{"LIST_FACTORY_LEDGER_PATH": "cost_ledger.csv"}`` puts the
    list factory's cost ledger beside the scratch job log instead of appending
    a rehearsal's imaginary spend to the real one. A bare filename lands in the
    scratch directory; an absolute path is used as given. Each key is set with
    ``setdefault`` semantics, so an operator who exported the variable
    deliberately still wins.

    Every ``--dry-run`` and every evidence/demo run calls this. The 48-hour
    shadow watch is gated on reading ``.tmp/job_log.csv``, and before this the
    file held 1,642 rows of which 48 were ``mode=live``, written by ad-hoc
    evidence scripts that set MODE=live inside their own process (the
    transports were mocked, so nothing reached a live API, but the rows name
    real production ids and are interleaved with the shadow ones). After 48
    hours nobody could tell a test row from a real one. The polluted file is
    quarantined under ``.tmp/quarantine/``.

    ``.claude/hooks/guard_live_writes.sh`` greps the command string and cannot
    see a process that sets those variables internally, which is why this is a
    convention enforced at the entry points rather than by the hook.
    """
    scratch = tmp_dir() / "scratch" / name
    try:
        scratch.mkdir(parents=True, exist_ok=True)
    except OSError:
        return scratch
    # Remembered before the redirect so job_log_read_path() can still find the
    # operational log. Only the first redirect in a process records it, or a
    # second dry-run would point readers at the first one's scratch file.
    os.environ.setdefault("JOB_LOG_READ_PATH", str(job_log_path()))
    os.environ["JOB_LOG_PATH"] = str(scratch / "job_log.csv")
    os.environ["SHADOW_LOG_PATH"] = str(scratch / "shadow_log.jsonl")
    for key, value in (extra_env or {}).items():
        target = Path(value)
        if not target.is_absolute():
            target = scratch / value
        os.environ.setdefault(key, str(target))
    return scratch


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mode() -> str:
    # Read directly from the environment (not shared.settings) to avoid an
    # import cycle: settings.guard_write() calls shadow().
    return os.environ.get("MODE", "shadow")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=_json_default, ensure_ascii=False, sort_keys=True)


def log_run(job: str, status: str, details: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Append one row to the Job_Log CSV (and the sheet tab when configured).

    Returns the row that was written (as a dict) or None if nothing could be
    written. Never raises.
    """
    row = {
        "ts_utc": _now_utc_iso(),
        "job": str(job),
        "status": str(status),
        "mode": _mode(),
        "details": _dumps(details or {}),
    }
    ok = _append_csv(row)
    _append_sheet(row)
    if _deployed():
        _observe("job", {"ts_utc": row["ts_utc"], "job": row["job"], "status": row["status"],
                         "mode": row["mode"], "details": _gate_details(details)})
    return row if ok else None


def shadow(system: str, action: str, payload: Optional[Dict[str, Any]] = None,
           mirror: bool = True) -> Optional[Dict[str, Any]]:
    """Record a write that WOULD have happened (MODE=shadow). Never raises.

    ``mirror=False`` keeps a record out of the deployed store: the Job_Log
    sheet-append intent below duplicates the row it describes, and mirroring
    it would double every store write and bury the real would_do records."""
    record = {
        "ts_utc": _now_utc_iso(),
        "mode": _mode(),
        "system": str(system),
        "action": str(action),
        "payload": payload if payload is not None else {},
    }
    if mirror:
        _observe("shadow", record)
    path = shadow_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(_dumps(record) + "\n")
        return record
    except Exception as exc:  # noqa: BLE001 - logging must never raise
        logger.warning("shadow log write failed (%s): %s", path, exc)
        return None


def read_shadow_log(path: Optional[Path] = None) -> list:
    """Helper for tests and reports: parse the JSONL shadow log."""
    path = path or shadow_log_path()
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError:
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("shadow log read failed (%s): %s", path, exc)
    return out


# ----------------------------------------------------------------- internals

def _deployed() -> bool:
    # RUNTIME is set only in the Modal image (modal_app.build_image); the
    # laptop and the test session never mirror.
    return os.environ.get("RUNTIME") == "modal"


def _obs_key(prefix: str, ts_utc: str) -> str:
    compact = "".join(ch for ch in str(ts_utc) if ch.isdigit())[:14]
    return "%s%s:%s" % (prefix, compact, uuid.uuid4().hex[:12])


def _bounded(record: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-safe copy of ``record``; an oversized body becomes a preview."""
    text = _dumps(record)
    if len(text) <= OBS_MAX_CHARS:
        return json.loads(text)
    slim = dict((k, v) for k, v in record.items() if k not in ("payload", "details"))
    slim["truncated"] = True
    slim["original_chars"] = len(text)
    slim["preview"] = text[:OBS_PREVIEW_CHARS]
    return json.loads(_dumps(slim))


def _deployment_hosts() -> Set[str]:
    hosts = set()
    for key in BASE_URL_KEYS:
        try:
            host = urlparse((os.environ.get(key) or "").strip()).hostname
        except ValueError:
            host = None
        if host:
            hosts.add(host.lower())
    return hosts


def _redact_text(text: str, hosts: Set[str]) -> str:
    def sub(match):
        url = match.group(0)
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return "<redacted-url>"
        if host.endswith(DEPLOYMENT_HOST_SUFFIX) or host in hosts:
            return "<redacted-url %s>" % host
        return url

    return _URL_RE.sub(sub, text)


def redact(value: Any, _hosts: Optional[Set[str]] = None) -> Any:
    """A copy of ``value`` safe to print or store outside the laptop.

    URLs on the deployment's host (``*.modal.run``, or the host of BASE_URL /
    REPLY_ENGINE_BASE_URL) become ``<redacted-url host>``: an approval link is
    a signed capability to send an email. Any ``actions`` or ``click`` field
    becomes ``<redacted>`` whatever it holds. Never raises on odd input."""
    hosts = _deployment_hosts() if _hosts is None else _hosts
    if isinstance(value, dict):
        return dict((k, REDACTED if str(k).lower() in REDACTED_FIELDS else redact(v, hosts))
                    for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return [redact(v, hosts) for v in value]
    if isinstance(value, str):
        return _redact_text(value, hosts)
    return value


def _gate_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Only the Job_Log details the gate reads, text capped."""
    out = {}  # type: Dict[str, Any]
    if not isinstance(details, dict):
        return out
    for key in MIRROR_JOB_DETAIL_KEYS:
        if key in details:
            value = details[key]
            if not isinstance(value, (int, float, bool)) and value is not None:
                value = str(value)[:MIRROR_TEXT_CHARS]
            out[key] = value
    return out


STDOUT_KEYS = ("kind", "ts_utc", "job", "status", "system", "action", "mode", "truncated")


def _observe(kind: str, record: Dict[str, Any]) -> None:
    """Mirror one record out of a Modal container, redacted. Never raises."""
    if not _deployed():
        return
    try:
        body = _bounded(redact(record))
    except Exception as exc:  # noqa: BLE001
        logger.warning("record could not be serialised for the deployed mirror: %s", exc)
        return
    try:
        line = _dumps(dict((k, v) for k, v in dict(body, kind=kind).items() if k in STDOUT_KEYS))
        sys.stdout.write("%s %s\n" % (RECORD_TAG, line))
        sys.stdout.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("record could not be printed: %s", exc)
    try:
        from shared import store as store_mod  # local import: store must not be a load-time dep

        prefix = OBS_JOB_PREFIX if kind == "job" else OBS_SHADOW_PREFIX
        store_mod.get_obs_store().set(_obs_key(prefix, body.get("ts_utc", "")), body)
    except Exception as exc:  # noqa: BLE001 - evidence must never break a tick
        logger.warning("record could not be written to the deployed evidence store: %s", exc)


def _append_csv(row: Dict[str, str]) -> bool:
    path = job_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists() or path.stat().st_size == 0
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=JOB_LOG_HEADER)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("job log CSV write failed (%s): %s", path, exc)
        return False


def _service_account_info() -> Optional[Dict[str, Any]]:
    """A service account that can actually authenticate, or None.

    Every candidate is validated for ``client_email`` + ``private_key`` before
    it is accepted, and an invalid one falls through to the next. Checking only
    "did json.loads work" is not enough: GOOGLE_CREDENTIALS_JSON in this repo's
    .env is the placeholder ``{"type": "service_account",
    "paste_your_json_here": "..."}``, which parses, so the placeholder won and
    the real credentials.json sitting beside it was never tried. The Job_Log
    sheet mirror then failed deep inside google.auth with MalformedError
    instead of working. ``services/metrics/sheet.py::service_account_info``
    carries the same rule; keep the two in step.
    """
    candidates = []  # type: list
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if raw:
        try:
            candidates.append(json.loads(raw))
        except ValueError:
            if os.path.isfile(raw):
                try:
                    with open(raw, "r", encoding="utf-8") as fh:
                        candidates.append(json.load(fh))
                except (OSError, ValueError):
                    logger.warning("GOOGLE_CREDENTIALS_JSON points at a file that is not JSON")
            else:
                logger.warning("GOOGLE_CREDENTIALS_JSON is neither JSON nor a file path")
    for candidate in (BASE_DIR / "credentials.json", ROOT_DIR / "credentials.json"):
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    candidates.append(json.load(fh))
            except (OSError, ValueError):
                continue
    for info in candidates:
        if isinstance(info, dict) and info.get("client_email") and info.get("private_key"):
            return info
    if candidates:
        logger.warning(
            "found %d service-account candidate(s) but none carried both client_email and "
            "private_key (the .env placeholder parses as JSON but cannot authenticate)",
            len(candidates))
    return None


_SHEET_CLIENT_CACHE = {}  # type: Dict[str, Any]


def _is_live() -> bool:
    # Read the environment directly, exactly like _mode(): importing
    # shared.settings here would re-enter guard_write -> log_run -> here.
    return os.environ.get("MODE", "shadow") == "live" and os.environ.get("ALLOW_LIVE_WRITES") == "1"


def _append_sheet(row: Dict[str, str]) -> bool:
    sheet_id = os.environ.get("JOB_LOG_SHEET_ID")
    if not sheet_id:
        return False
    if not _is_live():
        # The sheet mirror is a real network write (it can even create the
        # worksheet), so it obeys the same shadow contract as every other
        # write. It cannot call settings.guard_write() without recursing back
        # into log_run(), so it records the intent here instead.
        shadow("google_sheets", "job_log_append", {"sheet_id": sheet_id, "tab": SHEET_TAB, "row": dict(row)},
               mirror=False)
        return False
    try:
        import gspread  # local import: only needed when the sheet is configured
        from google.oauth2.service_account import Credentials

        client = _SHEET_CLIENT_CACHE.get("client")
        if client is None:
            info = _service_account_info()
            if not info:
                logger.warning("JOB_LOG_SHEET_ID set but no service-account credentials found")
                return False
            creds = Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            client = gspread.authorize(creds)
            _SHEET_CLIENT_CACHE["client"] = client
        spreadsheet = client.open_by_key(sheet_id)
        try:
            ws = spreadsheet.worksheet(SHEET_TAB)
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=SHEET_TAB, rows=1000, cols=len(JOB_LOG_HEADER))
            ws.append_row(JOB_LOG_HEADER)
        ws.append_row([row[k] for k in JOB_LOG_HEADER], value_input_option="RAW")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("job log sheet append failed: %s", exc)
        return False
