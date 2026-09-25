"""Environment, mode and the live-write guard.

The shadow contract
-------------------
MODE defaults to "shadow". A write against a live system happens only when
BOTH ``MODE=live`` and ``ALLOW_LIVE_WRITES=1`` are set for the process.
Every write path in shared.instantly / shared.ghl calls ``guard_write()``
first; in shadow it returns a ``{"shadow": True, ...}`` record (also appended
to .tmp/shadow_log.jsonl) and the caller performs no HTTP request.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import pytz
from dotenv import load_dotenv

from shared.paths import BASE_DIR, ENV_PATHS, IDS_PATH, OFFERS_PATH, ROOT_DIR, tmp_dir  # noqa: F401

logger = logging.getLogger("shared.settings")


# Set by the root conftest.py for the whole test session and inherited by
# every child process a test starts (``python3 jobs/x.py --help`` is not a
# pytest process, so running_under_pytest() alone did not cover it). Listed in
# modal_app.ENV_NOT_IN_SECRET as test-only; a deployed container never has it.
TEST_SESSION_ENV = "ADVERO_TEST_SESSION"

# The two live gate flags. load_env() never takes them from a dotenv file,
# whatever the file says (SAF-3, re-review 2026-09-22): a write to .env must
# not be enough to go live. Set them in the process environment (the deployed
# Modal secret, or Lorenzo's own terminal) or not at all.
GATE_FLAGS = ("MODE", "ALLOW_LIVE_WRITES")


def running_under_pytest() -> bool:
    """True inside a pytest process, or inside a child a test session started.

    The pytest check reads the imported modules: nothing in services/, jobs/
    or shared/ imports pytest, so outside a test run it is False. The flag
    covers the children, which inherit the session's scrubbed environment.
    """
    if "pytest" in sys.modules or "_pytest" in sys.modules:
        return True
    return os.environ.get(TEST_SESSION_ENV, "").strip() == "1"


def load_env(paths: Optional[Iterable[Any]] = None) -> List[str]:
    """Load Agentic Worklfows/.env then AdveroSolutions/.env without overriding
    variables that are already set in the process environment. Returns the
    files it read.

    ``paths`` replaces ENV_PATHS (a test seam; production never passes it).

    Under a test session this reads nothing, whatever the files hold. On
    2026-09-22 a test run sent real mail with the Gmail app password this
    function had loaded, and a rehearsal of the go-live .env (GHL token and
    Job_Log sheet id added) made 1,352 outbound attempts, mostly Google
    sign-ins with the real service-account key. Stripping known credential
    names afterwards is a list that goes stale the day a new key is added; not
    reading the files at all does not. Tests that need a value set a fake one.

    The skip is logged at WARNING on purpose: if it ever fires in production
    (pytest imported by accident, the flag exported in a shell) the run has no
    credentials, and that has to be visible rather than a mystery.
    """
    if running_under_pytest():
        logger.warning("load_env: test session detected (pytest loaded or %s=1); no dotenv file is read",
                       TEST_SESSION_ENV)
        return []
    loaded = []  # type: List[str]
    # The gate flags come from the process environment only (SAF-3): a value
    # a file puts there is taken out again. One already set is left alone.
    preset = set(k for k in GATE_FLAGS if k in os.environ)
    for path in (ENV_PATHS if paths is None else paths):
        if os.path.exists(str(path)):
            load_dotenv(dotenv_path=str(path), override=False)
            loaded.append(str(path))
            for key in GATE_FLAGS:
                if key not in preset and key in os.environ:
                    os.environ.pop(key, None)
                    logger.warning("load_env: ignored %s from %s; the live gate flags are read from the "
                                   "process environment only", key, path)
    return loaded


load_env()

# Snapshot at import time (kept for callers that just want the string); the
# functions below read the environment live so tests can flip modes.
MODE = os.environ.get("MODE", "shadow")

# Calendar / cadence constants (America/Chicago)
TZ = pytz.timezone("America/Chicago")
SEND_WINDOW = (7, 19)        # replies go out 07:00-19:00 CT only
SLOT_WINDOW = (12, 18)       # offered call slots 12:00-18:00 CT
MIN_LEAD_HOURS = 4           # a slot must be >= 4 h in the future
MAX_BUSINESS_DAYS = 5        # ... and within the next 5 business days
CADENCE_HOUR = 10            # daily follow-up touches send at 10:00 CT

# The reply poller's start date (Lorenzo, 2026-09-25: only the replies to the
# current campaigns matter, not the whole inbox). A received email older than
# this is never classified, drafted or carded and costs no model call: the
# poller marks it seen with the reason "before_start_date" and stops paging
# there (services/reply_engine/poller.py). jobs/seed_reply_examples.py reads
# Lorenzo's own replies back to the same date.
#
# Value: an ISO date or datetime. A date alone ("2026-09-15") is midnight
# America/Chicago; a datetime with no offset is read as America/Chicago; one
# with an offset or a trailing Z is taken as written (so "...Z" is UTC).
# Unset or empty: POLLER_START_AT_DEFAULT. "off" (or none/0/false/no) turns the
# start date off: the poller then walks back as far as its cursor and page
# budget reach, as it did before the setting existed.
#
# The default is the first day the six 2026 Instantly campaigns sent:
# runbooks/deliverability.md ("Sending began 2026-09-15") and
# runbooks/metrics.md (a read-only GET /accounts/analytics/daily over
# 2026-09-01..14 for the twelve active inboxes returned zero rows; the
# workspace has no per-inbox history before 2026-09-15). The earliest recorded
# reply (fixtures/instantly_replies_2026-09.json) is 2026-09-15T16:17Z.
POLLER_START_AT_ENV = "POLLER_START_AT"
POLLER_START_AT_DEFAULT = "2026-09-15"
POLLER_START_AT_OFF = ("off", "none", "0", "false", "no")


def parse_start_at(value: Any) -> Optional[datetime]:
    """A start-date value as an aware datetime, or None when it says "off".
    Rules as for POLLER_START_AT above. Raises ValueError on anything else:
    a typo must stop the poller, not silently classify the whole inbox."""
    if isinstance(value, datetime):
        return value if value.tzinfo else TZ.localize(value)
    text = str(value if value is not None else "").strip()
    if text.lower() in POLLER_START_AT_OFF:
        return None
    if not text:
        text = POLLER_START_AT_DEFAULT
    iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        if len(iso) == 10:
            parsed = datetime.strptime(iso, "%Y-%m-%d")
        else:
            parsed = datetime.fromisoformat(iso)
    except ValueError:
        raise ValueError("%s=%r is not an ISO date or datetime (e.g. 2026-09-15 or 2026-09-15T00:00:00-05:00), "
                         "and not 'off'" % (POLLER_START_AT_ENV, text))
    return parsed if parsed.tzinfo else TZ.localize(parsed)


def poller_start_at() -> Optional[datetime]:
    """POLLER_START_AT from the process environment (read live, so tests can
    set it), else POLLER_START_AT_DEFAULT. None when it is "off"."""
    return parse_start_at(os.environ.get(POLLER_START_AT_ENV, ""))


# Job_Log statuses for live writes. The deployed gate counts every status that
# starts with "live_write"; during the shadow watch that count must be zero.
LIVE_WRITE_INTENT = "live_write_intent"
LIVE_WRITE_OK = "live_write_ok"
LIVE_WRITE_FAILED = "live_write_failed"


class LiveWriteBlocked(Exception):
    """Raised by require_live() when a caller demands a live write in shadow."""


def get_mode() -> str:
    return os.environ.get("MODE", "shadow")


def is_live() -> bool:
    return get_mode() == "live" and os.environ.get("ALLOW_LIVE_WRITES") == "1"


def guard_write(system: str, action: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Gate every outbound write.

    Shadow (default): returns {'shadow': True, 'system', 'action', 'payload', 'ts'}
    and appends the record to the shadow log. The caller must NOT perform the
    write.
    Live (MODE=live and ALLOW_LIVE_WRITES=1): returns {'shadow': False, ...}
    and the caller proceeds.
    """
    payload = payload if payload is not None else {}
    record = {
        "system": system,
        "action": action,
        "payload": payload,
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if is_live():
        record["shadow"] = False
        # Shadow runs leave a shadow_log row per intended write; live runs must
        # leave a comparable one BEFORE the call, so a write that dies at the
        # transport or gateway can still be reconciled afterwards. On Modal the
        # row is also mirrored into the deployed store (shared.job_log), which
        # is where changesets/deploy/watch_report.py counts live_write_* rows.
        from shared import job_log  # local import avoids a cycle at module load

        # Redacted: a push payload carries the signed Approve/Veto links, and
        # this row reaches the Job_Log sheet and the deployed evidence.
        job_log.log_run("%s.%s" % (system, action), LIVE_WRITE_INTENT, {"payload": job_log.redact(payload)})
        return record
    if get_mode() == "live":
        logger.warning(
            "MODE=live but ALLOW_LIVE_WRITES!=1; treating %s.%s as shadow", system, action
        )
    record["shadow"] = True
    from shared import job_log  # local import avoids a cycle at module load

    job_log.shadow(system, action, payload)
    return record


def record_live_write_result(system: str, action: str, ok: bool,
                             details: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Record what a live write actually did, AFTER the call.

    guard_write() returns before the caller performs the write, so it can only
    record the intent. A caller that wants the outcome counted by the gate
    calls this with the result: one ``live_write_ok`` or ``live_write_failed``
    row. Does nothing (returns None) outside live, and never raises.
    """
    if not is_live():
        return None
    try:
        from shared import job_log  # local import avoids a cycle at module load

        status = LIVE_WRITE_OK if ok else LIVE_WRITE_FAILED
        return job_log.log_run("%s.%s" % (system, action), status, job_log.redact(dict(details or {})))
    except Exception as exc:  # noqa: BLE001 - recording must never break a write path
        logger.warning("could not record the live write result for %s.%s: %s", system, action, exc)
        return None


def require_live(system: str, action: str) -> None:
    """Raise LiveWriteBlocked unless the process is allowed to write live."""
    if not is_live():
        raise LiveWriteBlocked(
            "%s.%s blocked: MODE=%s ALLOW_LIVE_WRITES=%s (need MODE=live and ALLOW_LIVE_WRITES=1)"
            % (system, action, get_mode(), os.environ.get("ALLOW_LIVE_WRITES", ""))
        )


def load_ids(path=IDS_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.warning("ids.json not found at %s", path)
        return {}


OFFERS_LOADED = False


def load_offers(path=OFFERS_PATH) -> str:
    """config/offers.md is the only source of pricing and proof. An empty
    OFFERS_MD makes draft.py derive an empty allowed-figures set, so every
    draft carrying a number is rejected with a confusing reason instead of a
    clear config error: fail at ERROR level and flag it."""
    global OFFERS_LOADED
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, IOError) as exc:
        OFFERS_LOADED = False
        logger.error(
            "offers.md could not be read at %s (%s): pricing and proof are unavailable, so every "
            "draft with a number will be rejected. Restore the file before any run.", path, exc,
        )
        return ""
    OFFERS_LOADED = bool(text.strip())
    if not OFFERS_LOADED:
        logger.error("offers.md at %s is empty", path)
    return text


def require_offers() -> str:
    """OFFERS_MD, or a clear error. Anything that quotes a price uses this."""
    if not OFFERS_LOADED or not OFFERS_MD.strip():
        raise RuntimeError(
            "config/offers.md is missing or empty (%s): pricing and proof come from it and "
            "nowhere else." % OFFERS_PATH
        )
    return OFFERS_MD


IDS = load_ids()
OFFERS_MD = load_offers()

# Convenience accessors used across services (all read from IDS, never hard-coded)
_GHL = IDS.get("ghl", {})
_CAL = _GHL.get("calendars", {}).get("discovery_call", {})
GHL_LOCATION_ID = _GHL.get("location_id")
GHL_USER_ID = _GHL.get("user_id")
GHL_SALES_PIPELINE_ID = _GHL.get("pipelines", {}).get("sales", {}).get("id")
GHL_STAGES = {
    k: v.get("id") for k, v in _GHL.get("pipelines", {}).get("sales", {}).get("stages", {}).items()
}
GHL_CALENDAR_ID = _CAL.get("id")
BOOKING_URL = _CAL.get("booking_url")
CAMPAIGNS = IDS.get("instantly", {}).get("campaigns", {})
CAMPAIGN_BY_ID = {v.get("id"): dict(v, key=k) for k, v in CAMPAIGNS.items()}
