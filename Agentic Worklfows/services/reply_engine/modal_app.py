"""Modal deployment scaffold for the reply engine: app ``advero-reply-engine``.

Importing this module never deploys, builds or contacts Modal; every Modal
object below is a lazy handle. Deploying is a separate, Lorenzo-approved
step run from his own terminal (runbooks/deployment.md). Do not rely on the
PreToolUse hook to stop a deploy: it only matches command text and does not
run from every folder. The code-level protection is shared.settings.guard_write.

What the app carries
--------------------
* image: debian_slim python 3.11 + services/reply_engine/requirements.txt,
  with shared/, services/*, config/ and jobs/ mounted at /root. The mounts are
  a snapshot taken at deploy time: a file edited on the laptop afterwards
  (config/llm_budget.json, config/offers.md) reaches the containers only
  through another deploy.
* secret ``advero-reply-engine`` (modal.Secret.from_name), built from .env by
  changesets/deploy/modal_secret.py and by nothing else. SECRET_KEYS below is
  the complete list of keys the deployed code reads.
* two engine modal.Dicts behind shared.store.ModalDictStore:
  ``advero-reply-engine-store-shadow`` and ``advero-reply-engine-store-live``.
  The container picks one from its effective mode (MODE=live AND
  ALLOW_LIVE_WRITES=1 -> live, anything else -> shadow), so the 48-hour
  shadow watch and the live run never share state (owner decision R5).
  Deployed evidence (Job_Log rows, shadow records) goes to two more,
  ``advero-reply-engine-obs-shadow`` / ``-live``, never to the engine's.
  Modal expires a Dict entry after 7 days with no read or write.
* web: @modal.asgi_app() serving services.reply_engine.app:app. Always
  deployed; GET /health reports mode and live.
* schedules: SCHEDULES below is the one source of truth for every schedule in
  the system, Modal and laptop alike. Each entry carries its cron (five
  fields, read in America/Chicago, so nothing drifts on Nov 1, 2026), its
  tier and its runtime.

Which schedules this deploy registers (owner decisions R3 and R4)
-----------------------------------------------------------------
* runtime ``laptop``: jobs that hand work to another job through files
  (sidecars, change-sets, config/*.json, the run state and ledgers on disk).
  Each Modal function runs in its own throwaway
  container with nothing shared on disk, so on Modal those hand-offs silently
  break. They are NOT Modal functions at all; changesets/schedules/laptop/
  holds the staged launchd plists and crontab lines that run them through
  changesets/schedules/laptop_runner.py. On the laptop two more switches act
  as live flags beside MODE and ALLOW_LIVE_WRITES: LAPTOP_LIVE_TIERS and
  LAPTOP_PAID_JOBS, which the runner reads only from the saved .env.
* runtime ``modal``: registered only when their tier is in DEPLOY_TIERS, read
  at import (deploy) time and baked into the image env so the container
  registers exactly the same functions. Unset or blank means ``sales`` only,
  the first live scope. Tiers are added one redeploy at a time, always through
  the runbook's wrapper (preflight, typed confirmation, /health check), never
  a raw ``modal deploy``:
      DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow
  An unknown tier name raises here, at import, rather than deploying a guess.

Every scheduled tick writes one Job_Log row (mirrored into the store and to
stdout on Modal, see shared.job_log), fails the Modal run on an exception, a
non-zero exit or a missing entrypoint, and is never retried: the bodies send
replies and update statuses. In live, every tick also refuses to run until
changesets/deploy/cutover.py has seeded the live store, refuses a cutover
older than shared.store.CUTOVER_MAX_AGE_MINUTES until the first live tick has
accepted it, and the live poller refuses to run without a complete cursor.

    python3 -c "import services.reply_engine.modal_app"     # offline import check
"""
import logging
import os
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import modal

logger = logging.getLogger("reply_engine.modal_app")

APP_NAME = "advero-reply-engine"
SECRET_NAME = "advero-reply-engine"
# The base of the two Dict names. shared.store.MODAL_DICT_BASE is the same
# string (pinned by a test); it is not imported here because importing
# ``shared`` loads .env and every client, and this module must stay light.
DICT_NAME = "advero-reply-engine-store"
PYTHON_VERSION = "3.11"

HERE = Path(__file__).resolve().parent            # .../services/reply_engine
BASE_DIR = HERE.parent.parent                     # .../Agentic Worklfows
REQUIREMENTS = HERE / "requirements.txt"
REMOTE_ROOT = "/root"

# Schedules are CT-native: modal.Cron reads them in SCHEDULE_TZ, so there is no
# UTC arithmetic to redo when daylight saving ends.
SCHEDULE_TZ = "America/Chicago"

TIERS = ("sales", "marketing", "ops", "fulfillment")
RUNTIME_MODAL = "modal"
RUNTIME_LAPTOP = "laptop"
RUNTIMES = (RUNTIME_MODAL, RUNTIME_LAPTOP)

DEPLOY_TIERS_ENV = "DEPLOY_TIERS"
DEFAULT_DEPLOY_TIERS = ("sales",)

# cron: 5-field crontab read in SCHEDULE_TZ. when: plain-English CT time.
# tier: the tier that flips live with it. runtime: where it runs.
# argv: what `python3 -m <module>` gets on the laptop (and what _run_job
# passes on Modal); None for the reply-engine entrypoints called directly.
Schedule = namedtuple("Schedule", ["cron", "when", "tier", "runtime", "argv"])

SCHEDULES = {
    # ---- sales tier (S1-S8): Modal ------------------------------------------
    "poller": Schedule("*/5 * * * *", "every 5 minutes", "sales", RUNTIME_MODAL, None),
    # The 5-minute reply SLA chase, on its own tick rather than only inside the
    # poller. poller.run_once calls fetch_new_replies BEFORE it reaches the
    # chase, unguarded, so any Instantly failure - a rotated key above all -
    # raises the whole tick and silently takes the chase with it.
    # escalate_pending touches no Instantly client and claims each rung with
    # set_if_absent, so running from both places cannot double-push.
    "approval_escalation": Schedule(
        "*/5 * * * *", "every 5 minutes, beside poller; it chases only, it cannot send",
        "sales", RUNTIME_MODAL, None),
    "cadence_tick": Schedule(
        "0 7-19 * * *", "hourly 07:00-19:00 CT; the function re-checks the CT send window itself",
        "sales", RUNTIME_MODAL, None),
    # The D1 touch is auto-sent after a 30-minute veto window that opens with a
    # push at 09:30 CT (runbooks/cadence_and_booking.md). The hourly tick fires
    # on the hour, so without this half-hour run the veto window is never
    # actually served and a vetoed D1 goes out anyway at 10:00.
    "cadence_veto_ping": Schedule(
        "30 9 * * 1-5", "09:30 CT weekdays: the half-hour run the D1 veto window needs",
        "sales", RUNTIME_MODAL, None),
    "appointments_tick": Schedule("*/10 * * * *", "every 10 minutes", "sales", RUNTIME_MODAL, None),
    # --scheduled: push only when this run produced a brief, a proposal or an
    # error. Without it every 5-minute run pushed a digest (288 a day).
    # Its file lock (jobs/precall_tick._run_lock) is on the container's own
    # disk and cannot stop two containers; max_containers=1 (MODAL_MAX_CONTAINERS)
    # is what keeps a run that passes 5 minutes from overlapping the next.
    "precall_tick": Schedule(
        "*/5 * * * *", "every 5 minutes, beside appointments_tick; one container at a time (max_containers=1)",
        "sales", RUNTIME_MODAL, ("--scheduled",)),
    # The "I'm on" nudge 3 minutes after a call starts (N1). Every minute in
    # call hours; a run with no call on does nothing. Its file lock
    # (jobs/appointments_tick._run_lock) covers one container's disk only, so
    # max_containers=1 (MODAL_MAX_CONTAINERS) keeps one run at a time.
    "no_show_watch": Schedule(
        "* 12-18 * * 1-5", "every minute 12:00-18:59 CT weekdays; one container at a time (max_containers=1)",
        "sales", RUNTIME_MODAL, ("--no-show-watch",)),
    "pipeline_sync": Schedule("0 6 * * *", "06:00 CT", "sales", RUNTIME_MODAL, None),
    # O3, the ONE scheduled 07:30 sweep (GOL-13). jobs/positive_sweep.py only
    # delegates to this same sweep, so scheduling both pushed two identical
    # digests and hit GET /emails (20 requests/minute) twice beside the poller.
    # positive_sweep stays a CLI (its --kpi view) and is not scheduled.
    "pipeline_sweep": Schedule("30 7 * * *", "07:30 CT (O3, the single scheduled sweep)",
                               "sales", RUNTIME_MODAL, None),
    # ---- marketing tier: laptop (file hand-offs, R4) --------------------------
    # ORDER MATTERS on Monday and Saturday. inbox_placement and
    # autoresponder_canary write their proposals into the SAME dated
    # change-set file the 07:00 monitor writes, and the monitor reads their
    # sidecars to build its card, so both run at 06:45, before it. On one
    # disk (the laptop) that ordering is real; on Modal it was not.
    "inbox_placement": Schedule("45 6 * * 1", "Mon 06:45 CT, before the 07:00 monitor (O5)",
                                "marketing", RUNTIME_LAPTOP, ("--now",)),
    "autoresponder_canary": Schedule("45 6 * * 6", "Sat 06:45 CT, before the 07:00 monitor (O7)",
                                     "marketing", RUNTIME_LAPTOP, ("--now",)),
    "deliverability_monitor": Schedule("0 7 * * *", "07:00 CT daily (O1)",
                                       "marketing", RUNTIME_LAPTOP, ("--now",)),
    "inbox_inventory": Schedule("0 7 * * *", "07:00 CT daily, alongside O1 (M2/A5)",
                                "marketing", RUNTIME_LAPTOP, ("--now",)),
    # campaign_verdicts (Fri 15:00) is TURNED OFF (Lorenzo, 2026-09-22): he runs
    # it by hand. Its code stays; config/turned_off_jobs.json lists it.
    # PAID whenever ALLOW_PAID_CALLS=1, in shadow as well as live (owner
    # decision R7): that flag alone gates Apify, Perplexity, MillionVerifier and
    # this job's own Anthropic calls. It does NOT stop Anthropic spend anywhere
    # else; the reply engine, precall_tick and retro_packet are capped only by
    # config/llm_budget.json. The laptop runner passes ALLOW_PAID_CALLS=0 unless
    # the job is named in LAPTOP_PAID_JOBS.
    "list_factory": Schedule("0 9 * * 0", "Sun 09:00 CT (O8); PAID whenever ALLOW_PAID_CALLS=1, live or not",
                             "marketing", RUNTIME_LAPTOP,
                             ("--now", "--all-campaigns", "--refresh-suppression")),
    # ---- ops tier: laptop ------------------------------------------------------
    # upwork_rooms_am / upwork_rooms_pm (09:00 and 15:00 weekdays) are TURNED
    # OFF (Lorenzo, 2026-09-22): he checks the Upwork rooms by hand. Their code
    # stays; config/turned_off_jobs.json lists them.
    # Reads the Job_Log from disk and writes .tmp/retro/.
    "retro_packet": Schedule("0 16 * * 5", "Fri 16:00 CT (O6)", "ops", RUNTIME_LAPTOP, ("--now",)),
    # Reads the list-factory ledger and the Job_Log from disk for the KPI view.
    "daily_metrics": Schedule("0 18 * * *", "18:00 CT daily (O4)", "ops", RUNTIME_LAPTOP, ("--now",)),
    # ---- fulfillment tier: laptop ---------------------------------------------
    # Needs the client roster and templates on disk (Mike's Oct 12 renewal).
    "client_scorecard": Schedule("15 19 * * 5", "Fri 19:15 CT, after the sending day closes (F3/F4)",
                                 "fulfillment", RUNTIME_LAPTOP, ("--now",)),
}  # type: Dict[str, Schedule]

# Schedules that must run BEFORE another one on the same day, and why. Both
# pairs hand off through files, so both halves of each run on the laptop;
# build_schedules.py --check refuses a pair split across runtimes. The Friday
# retro no longer waits for campaign_verdicts: that job is turned off
# (config/turned_off_jobs.json), so a pair naming it would log
# ordering_not_met every Friday.
SCHEDULE_ORDERING = {
    "inbox_placement": ("deliverability_monitor",
                        "level 2's sidecar and its change-set rows have to exist before the card is built"),
    "autoresponder_canary": ("deliverability_monitor",
                             "level 4's sidecar and its change-set rows have to exist before the card is built"),
}  # type: Dict[str, Any]

# Which module each schedule drives. changesets/schedules/schedules.json is
# generated from this plus SCHEDULES, and jobs/README.md is checked against it.
SCHEDULE_JOB_MODULE = {
    "poller": "services.reply_engine.poller",
    "approval_escalation": "services.reply_engine.approval",
    "cadence_tick": "services.reply_engine.cadence",
    "cadence_veto_ping": "services.reply_engine.cadence",
    "appointments_tick": "services.reply_engine.show_rate",
    "precall_tick": "jobs.precall_tick",
    "no_show_watch": "jobs.appointments_tick",
    "pipeline_sync": "services.reply_engine.pipeline_sync",
    "pipeline_sweep": "jobs.pipeline_sweep",
    "inbox_placement": "jobs.inbox_placement",
    "autoresponder_canary": "jobs.autoresponder_canary",
    "deliverability_monitor": "jobs.deliverability_monitor",
    "inbox_inventory": "jobs.inbox_inventory",
    "retro_packet": "jobs.retro_packet",
    "client_scorecard": "jobs.client_scorecard",
    "daily_metrics": "jobs.daily_metrics",
    "list_factory": "jobs.list_factory",
}  # type: Dict[str, str]

# Jobs Lorenzo turned off (he runs them by hand) are listed, with their old
# schedule, in config/turned_off_jobs.json and nowhere above. build_schedules.py
# --check refuses a name that is in both.

# Per-function timeouts for the Modal schedules (seconds).
MODAL_TIMEOUTS = {
    "poller": 240,
    "approval_escalation": 120,
    "cadence_tick": 240,
    "cadence_veto_ping": 240,
    "appointments_tick": 240,
    "precall_tick": 600,
    "no_show_watch": 120,
    "pipeline_sync": 600,
    "pipeline_sweep": 600,
}  # type: Dict[str, int]

# At most this many containers of a schedule at once. A */5 run that passes
# five minutes would otherwise overlap the next; Modal queues the next input
# until the running container is done. precall_tick's own lock is a file on
# its container's disk, which a second container never sees.
MODAL_MAX_CONTAINERS = {
    "precall_tick": 1,
    "no_show_watch": 1,
}  # type: Dict[str, int]

# The scheduled poller stops TAKING NEW replies once this many seconds of its
# run have passed, well inside its MODAL_TIMEOUTS entry (240 s): a reply is
# never started that its run cannot finish. What is left is not marked seen
# and the cursor does not move, so the next */5 run picks it up; a first-poll
# backlog drains over several polls (runbooks/deployment.md step 2b).
POLLER_TIME_BUDGET_S = 120


def parse_deploy_tiers(raw: Optional[str]) -> Tuple[str, ...]:
    """DEPLOY_TIERS as a tuple in TIERS order. Unset or blank -> sales only.

    Refuses (ValueError) an unknown name rather than guessing: a typo such as
    ``DEPLOY_TIERS=marketting`` must stop the deploy, not deploy sales alone
    while the operator believes marketing went out too."""
    if raw is None or not raw.strip():
        return DEFAULT_DEPLOY_TIERS
    wanted = [part.strip().lower() for part in raw.replace(" ", ",").split(",") if part.strip()]
    unknown = sorted(set(wanted) - set(TIERS))
    if unknown:
        raise ValueError("%s=%r names unknown tier(s) %s; the tiers are %s"
                         % (DEPLOY_TIERS_ENV, raw, unknown, list(TIERS)))
    # Tiers are added to sales, never swapped for it. `modal deploy` replaces
    # the whole app, so DEPLOY_TIERS=marketing would silently remove the
    # poller, the SLA chase and the cadence from Modal.
    for required in DEFAULT_DEPLOY_TIERS:
        if required not in wanted:
            raise ValueError("%s=%r leaves out %r; list every tier to keep, e.g. %s=sales,marketing "
                             "(a deploy replaces the whole app)"
                             % (DEPLOY_TIERS_ENV, raw, required, DEPLOY_TIERS_ENV))
    return tuple(t for t in TIERS if t in wanted)


def schedules_for(runtime: str, tiers: Optional[Sequence[str]] = None) -> List[str]:
    """Schedule names on ``runtime``, optionally limited to ``tiers``, sorted."""
    return sorted(name for name, sched in SCHEDULES.items()
                  if sched.runtime == runtime and (tiers is None or sched.tier in tiers))


DEPLOY_TIERS = parse_deploy_tiers(os.environ.get(DEPLOY_TIERS_ENV))
MODAL_SCHEDULES = schedules_for(RUNTIME_MODAL)            # every schedule that runs on Modal
LAPTOP_SCHEDULES = schedules_for(RUNTIME_LAPTOP)          # every schedule that runs on the laptop
DEPLOYED_SCHEDULES = schedules_for(RUNTIME_MODAL, DEPLOY_TIERS)   # what THIS deploy registers
# The Modal functions this deploy registers, i.e. the schedules the watch and
# the preflight check. Kept under its historical name for its readers.
SCHEDULED_FUNCTIONS = list(DEPLOYED_SCHEDULES)  # type: List[str]


def deploy_summary() -> Dict[str, Any]:
    """What `modal deploy` of this module registers, for the preflight and the
    Modal plan quota check (crons and web endpoints are plan-limited)."""
    return {
        "app": APP_NAME,
        "deploy_tiers": list(DEPLOY_TIERS),
        "crons": len(DEPLOYED_SCHEDULES),
        "web_endpoints": 1,
        "modal_functions": len(DEPLOYED_SCHEDULES) + 1,
        "schedules": list(DEPLOYED_SCHEDULES),
        "held_back_modal_schedules": [n for n in MODAL_SCHEDULES if n not in DEPLOYED_SCHEDULES],
        "laptop_schedules": list(LAPTOP_SCHEDULES),
        # A selected tier with nothing on Modal: its jobs run on the laptop, so
        # selecting it here changes nothing and the operator should know that.
        "tiers_with_no_modal_schedule": [t for t in DEPLOY_TIERS if not schedules_for(RUNTIME_MODAL, (t,))],
    }


def cron(name: str) -> modal.Cron:
    """modal.Cron for a schedule, always in CT. Fails loudly here rather than
    server-side at deploy if a string is not a 5-field crontab expression."""
    expr = SCHEDULES[name][0]
    if len(expr.split()) != 5:
        raise ValueError(
            "SCHEDULES[%r] = %r is not a 5-field Unix crontab expression; modal.Cron would be "
            "rejected at deploy and take every other schedule down with it." % (name, expr))
    return modal.Cron(expr, timezone=SCHEDULE_TZ)


SECRET_KEYS = [
    "INSTANTLY_API_KEY", "GHL_PRIVATE_INTEGRATION_TOKEN", "ANTHROPIC_API_KEY", "NTFY_TOPIC",
    "REPLY_ENGINE_SECRET", "MODE", "ALLOW_LIVE_WRITES",
    # A push is a guarded write, so MODE=shadow records it as an intent into
    # the container's .tmp/ and delivers nothing. That intent dies with the
    # container, so without this key the 48-hour shadow watch produces no
    # 07:30 digest on Lorenzo's phone and no approval request at all: the gate
    # in runbooks/deployment.md becomes unobservable. Pushes only ever go to
    # Lorenzo's own topic and address, so opting them back in is safe.
    "NOTIFY_SHADOW_SEND",
    "GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NOTIFY_EMAIL",
    "JOB_LOG_SHEET_ID", "GOOGLE_CREDENTIALS_JSON",
    # approval.base_url() RAISES in live rather than quietly using
    # http://localhost:8000, so a deploy without BASE_URL fails at the first
    # positive reply. REPLY_ENGINE_BASE_URL is the alias it also accepts.
    # WEBHOOK_SECRET and DEBUG_SECRET gate the inbound webhook and the
    # /state debug read; modal_secret.py sets both to REPLY_ENGINE_SECRET.
    "BASE_URL", "REPLY_ENGINE_BASE_URL", "WEBHOOK_SECRET", "DEBUG_SECRET",
    # Four capabilities the runbooks tell Lorenzo to turn on, which could not be
    # turned on in the deployed container without editing this file:
    #   ZOOM_WEBHOOK_SECRET  - zoom_webhook.py answers 503 zoom_secret_missing to
    #     every event without it, so no joins:<id> row is ever written, no_show
    #     detection returns "unknown" for every call and S5 degrades to a manual
    #     "mark it by hand" task. That is the exact state connecting Zoom was
    #     meant to fix (runbooks/show_rate_and_no_show.md step 5).
    #   ZOOM_URL_VALIDATION  - the endpoint validation handshake Zoom performs
    #     when the webhook is first saved.
    #   A2P_10DLC_REGISTERED - until it is "1", every SMS leg in S4 and S5
    #     returns skipped/a2p_not_registered.
    #   NTFY_TOKEN / NTFY_ALLOW_SENSITIVE - DECISIONS C2 option A (an access
    #     token on the ntfy topic) cannot be applied on Modal without them, so
    #     approval buttons stay email-only.
    #   CADENCE_D6_HOLD      - the D6 calendar hold can never be enabled.
    # shared/tests/test_settings.py::test_every_env_key_is_deployable pins this
    # list against the environment the code actually reads.
    "ZOOM_WEBHOOK_SECRET", "ZOOM_URL_VALIDATION", "A2P_10DLC_REGISTERED",
    "NTFY_TOKEN", "NTFY_ALLOW_SENSITIVE", "CADENCE_D6_HOLD",
    # Optional behaviour switches the runbooks name; harmless to omit.
    "SHOW_RATE_SENDER", "AUTO_SEND_AFTER_MINUTES", "LOOM_URL_GENERIC", "LOG_LEVEL",
    # Template auto-send kill switch (template_approvals.kill_switch_on): any
    # value but 1/on/true/yes stops every approved-template auto-send. It can
    # only switch sends off, never on, so leaving it out is the normal state.
    "AUTO_SEND_TEMPLATES",
    # ---- Phases 2-4. Not all of these are secrets; every one of them has to
    # reach the container the way JOB_LOG_SHEET_ID does, or the component
    # silently falls back to a hard-coded id or refuses to run at all.
    #   ALLOW_PAID_CALLS   - the ONLY gate in front of Apify, Perplexity,
    #     MillionVerifier and the list factory's own Anthropic calls (owner
    #     decision R7): live mode is not required, a shadow run with it set
    #     spends. It does NOT stop Anthropic spend anywhere else; the reply
    #     engine, precall_tick and retro_packet are capped only by
    #     config/llm_budget.json. No Modal schedule spends through it today
    #     (the list factory runs on the laptop), so modal_secret.py always
    #     writes ALLOW_PAID_CALLS=0 into the secret.
    #   APIFY_API_TOKEN / APIFY_TOKEN - the same token under two names: the
    #     root .env uses APIFY_API_TOKEN, Coding/lead-scrape-2026/runner.py
    #     reads APIFY_TOKEN. Both are registered so either path works.
    #   FIREFLIES_API_KEY  - call recaps for the pre-call brief and the retro.
    #   PAYMENT_LINK_URL   - **this one matters**: unset, every SOP-009
    #     "here is the link to get started" draft ships a visible
    #     {payment_link} placeholder and is permanently unsendable, so the
    #     verbal-commit path cannot be completed from a container at all.
    #   DAILY_METRICS_SHEET_ID, SKOOL_GROUP, SKOOL_GROUP_ID - not secrets, but
    #     the override exists precisely so the container does not use the
    #     hard-coded ids.
    "ALLOW_PAID_CALLS", "APIFY_API_TOKEN", "APIFY_TOKEN",
    "FIREFLIES_API_KEY", "PAYMENT_LINK_URL",
    "DAILY_METRICS_SHEET_ID", "SKOOL_GROUP", "SKOOL_GROUP_ID",
]

# Environment keys that are deliberately NOT in the Modal secret, with the
# reason. Everything the code reads must be in one list or the other; the test
# named above fails when a new os.environ read appears in neither, which is how
# ZOOM_WEBHOOK_SECRET and A2P_10DLC_REGISTERED went missing in the first place.
ENV_NOT_IN_SECRET = {
    "MODAL_DICT_NAME": "explicit store override for tests and one-off tools; never set on Modal, where "
                       "shared.store derives the shadow or live Dict from the mode (owner decision R5)",
    "DEPLOY_TIERS": "deploy-time tier selection (owner decision R3), read by this module at import and "
                    "baked into the image env by build_image so the container registers the same functions",
    "RUNTIME": "set by modal_app itself when it runs in a container",
    "INSTANTLY_API_KEY_READ": "laptop/agent sessions only (R2(a), shared/keys.py); the container holds "
                              "INSTANTLY_API_KEY and reads fall back to it",
    "GHL_PRIVATE_INTEGRATION_TOKEN_READ": "laptop/agent sessions only (R2(a), shared/keys.py); the container "
                                          "holds GHL_PRIVATE_INTEGRATION_TOKEN and reads fall back to it",
    "ADVERO_TMP_DIR": "container-local scratch path",
    "STORE_PATH": "container-local; the Modal Dict store is selected by RUNTIME",
    "JOB_LOG_PATH": "container-local CSV mirror of the Job_Log sheet",
    "SHADOW_LOG_PATH": "container-local shadow log",
    "LLM_LEDGER_PATH": "container-local LLM cost ledger",
    "LLM_FAKE": "test/replay only: a deployed container must never fake the model",
    "REPLY_ENGINE_OFFLINE_FAKES": "test/replay only",
    "NOTIFY": "tests set NOTIFY=off; the container always notifies",
    "NOTIFICATION_EMAIL": "legacy alias read as a fallback for NOTIFY_EMAIL",
    "JOB_LOG_READ_PATH": "container-local; remembers the pre-redirect Job_Log so a --dry-run reader "
                         "does not read the scratch file it just created",
    "ANALYTICS_CACHE_TTL_SECONDS": "in-process cache lifetime for the Instantly analytics reader; "
                                   "the 300s default is right in a container and 0 disables it",
    # Phases 2-4. All local paths or test switches: a container either has a
    # working default or must not have the file at all.
    "LIST_FACTORY_LEDGER_PATH": "container-local cost ledger CSV",
    "LIST_FACTORY_ICP_DIR": "test override for config/icp/",
    "LIST_FACTORY_OFFLINE_FAKES": "test/replay only: a deployed container must never fake the model",
    "LEAD_FACTS_CSV": "path to the list factory export; has a default, container-local",
    "RETRO_STAGE_DIR": "container-local staging dir for the retro's session-fetched inputs",
    "RETRO_RECAPS_PATH": "container-local staged Fireflies pull",
    "RETRO_AUDIT_PATH": "container-local staged Instantly/GHL audit log",
    "RIZE_EXPORT_PATH": "local path to a Rize CSV export; unset in a container",
    "UPWORK_PIPELINE_DIR": "laptop-only override for Coding/upwork-pipeline (the Upwork follow-up "
                           "collector reads job folders there); unset in a container",
    "ADVERO_TEST_SESSION": "test-only: set by conftest.py so shared.settings.load_env() reads no "
                           "dotenv file in a test or its child processes; never set in a container",
}

LOCAL_DIRS = {
    # local path -> remote path. shared/paths.py derives BASE_DIR from the
    # shared/ location, so /root/shared makes /root/config the config dir.
    str(BASE_DIR / "shared"): REMOTE_ROOT + "/shared",
    str(HERE): REMOTE_ROOT + "/services/reply_engine",
    str(BASE_DIR / "config"): REMOTE_ROOT + "/config",
    str(BASE_DIR / "jobs"): REMOTE_ROOT + "/jobs",
    # jobs/pipeline_sweep and jobs/precall_tick import across services, so the
    # sibling services are mounted too. changesets/schedules/build_schedules.py
    # --check-image imports every deployed module from a copy of exactly these
    # mounts, which is how a missing one is caught before deploy.
    str(BASE_DIR / "services" / "metrics"): REMOTE_ROOT + "/services/metrics",
    str(BASE_DIR / "services" / "retro"): REMOTE_ROOT + "/services/retro",
    str(BASE_DIR / "services" / "experiments"): REMOTE_ROOT + "/services/experiments",
    str(BASE_DIR / "services" / "list_factory"): REMOTE_ROOT + "/services/list_factory",
}

IGNORE = ["tests", "__pycache__", "*.pyc", ".pytest_cache", ".tmp", "snapshots"]


def image_env() -> Dict[str, str]:
    """The environment baked into the image (not secrets)."""
    return {
        "RUNTIME": "modal",
        "PYTHONPATH": REMOTE_ROOT,
        "ADVERO_TMP_DIR": "/tmp/advero",   # container scratch; evidence goes to the store and stdout
        # The container re-imports this module to find its function; it must
        # see the same tier selection the deploy saw, or it would look for a
        # function the deploy never registered (or register one it did not).
        DEPLOY_TIERS_ENV: ",".join(DEPLOY_TIERS),
    }


def build_image() -> modal.Image:
    image = modal.Image.debian_slim(python_version=PYTHON_VERSION)
    if REQUIREMENTS.exists():
        image = image.pip_install_from_requirements(str(REQUIREMENTS))
    image = image.env(image_env())
    # add_local_dir must come after every build step (mounted at runtime, not copied).
    for local, remote in LOCAL_DIRS.items():
        if Path(local).exists():
            image = image.add_local_dir(local, remote_path=remote, ignore=IGNORE)
    return image


app = modal.App(APP_NAME)
image = build_image()
secrets = [modal.Secret.from_name(SECRET_NAME)]


def dict_name(mode: str) -> str:
    """The Modal Dict for 'shadow' or 'live' (same rule as shared.store.modal_dict_name)."""
    if mode not in ("shadow", "live"):
        raise ValueError("mode must be 'shadow' or 'live', not %r" % (mode,))
    return "%s-%s" % (DICT_NAME, mode)


class _Missing(object):
    """Sentinel: the module or entrypoint was not there at all. Distinct from
    an entrypoint that ran and returned None, so a deploy whose image dropped
    poller.py cannot pass the 48-hour shadow gate as a healthy tick."""

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<entrypoint missing>"


MISSING = _Missing()


class TickFailed(RuntimeError):
    """Raised (after its Job_Log row is written) so Modal marks the run failed."""


class JobFailed(TickFailed):
    """A job's main() returned a non-zero exit code: a partial or failed run."""

    def __init__(self, job: str, exit_code: Any):
        self.job = job
        self.exit_code = exit_code
        super(JobFailed, self).__init__("%s exited %r" % (job, exit_code))


class EntrypointMissing(TickFailed):
    """The module or its entrypoint was not in the deployed image."""


class CutoverMissing(TickFailed):
    """Live mode on a live store that changesets/deploy/cutover.py never seeded."""


def _call_entrypoint(module_name: str, candidates: Sequence[str], **kwargs) -> Any:
    """Import ``module_name`` and call the first attribute in ``candidates``.

    Returns ``MISSING`` (and logs) when the module cannot be imported or has
    none of the entrypoints; the scheduled wrapper then writes an
    ``entrypoint_missing`` row and fails the run. An exception raised INSIDE
    the entrypoint is never retried: the entrypoints send replies, update
    interest statuses and create appointments, so a second run inside the same
    tick would repeat every side effect the first one already performed.
    """
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        logger.warning("entrypoint_missing: %s not importable (%s)", module_name, exc)
        return MISSING
    except Exception as exc:  # noqa: BLE001 - a sibling that raises at import must not look healthy
        logger.warning("entrypoint_missing: %s failed at import (%s)", module_name, exc, exc_info=True)
        return MISSING
    for name in candidates:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn(**_bindable(fn, kwargs))
    logger.warning("entrypoint_missing: %s has none of %s", module_name, list(candidates))
    return MISSING


def _bindable(fn: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """The subset of ``kwargs`` the entrypoint actually accepts, decided by its
    signature. The old code called ``fn(**kwargs)`` and fell back to ``fn()``
    on TypeError, which could not tell a signature mismatch from a TypeError
    raised inside the function body and re-ran the whole tick."""
    if not kwargs:
        return {}
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return {}
    if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
        return dict(kwargs)
    accepted = set(
        name for name, p in sig.parameters.items()
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    )
    dropped = [k for k in kwargs if k not in accepted]
    if dropped:
        logger.warning("entrypoint %s does not accept %s; calling without them", getattr(fn, "__name__", fn), dropped)
    return dict((k, v) for k, v in kwargs.items() if k in accepted)


def _log_row(job: str, status: str, details: Dict[str, Any]) -> None:
    try:
        from shared.job_log import log_run

        log_run("modal.%s" % job, status, details)
    except Exception as exc:  # noqa: BLE001
        logger.warning("job_log unavailable while reporting %s %s: %s", job, status, exc)


def _started(started_at: Optional[str]) -> Dict[str, Any]:
    return {"started_at": started_at} if started_at else {}


def _log_tick(job: str, result: Any, started_at: Optional[str] = None) -> None:
    if isinstance(result, _Missing):
        _log_row(job, "entrypoint_missing", dict({"result_type": "missing"}, **_started(started_at)))
        return
    details = dict({"result_type": type(result).__name__}, **_started(started_at))  # type: Dict[str, Any]
    if isinstance(result, dict) and "exit_code" in result:
        details["exit_code"] = result["exit_code"]
    _log_row(job, "tick", details)


def _log_error(job: str, exc: BaseException, started_at: Optional[str] = None) -> None:
    _log_row(job, "error", dict({"error": "%s: %s" % (type(exc).__name__, exc)}, **_started(started_at)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _tick(job: str, started_at: Optional[str] = None):
    """Run a schedule body and guarantee exactly one Job_Log row either way.

    * the body raised            -> ``error`` row, re-raised;
    * a job exited non-zero      -> ``failed`` row with the exit code, JobFailed;
    * the entrypoint was missing -> ``entrypoint_missing`` row, EntrypointMissing;
    * otherwise                  -> ``tick`` row.

    Every failure re-raises so Modal marks the run failed, and nothing is
    retried: these bodies send replies and write interest statuses. Before
    this, a job that exited 1 on a partial run was logged as a healthy tick
    with no exit code, and the 48-hour gate could not see it (GOL-2).

    Each row carries ``started_at``, when the run STARTED (the row itself is
    stamped when it ends). The watch report matches runs to their due times
    on the start: with max_containers=1 a slow precall_tick and the run
    queued behind it would otherwise both end inside the next slot.
    """
    started_at = started_at or _now_iso()
    tick = {"result": None}  # type: Dict[str, Any]
    try:
        yield tick
    except JobFailed as exc:
        _log_row(job, "failed", dict({"exit_code": exc.exit_code}, **_started(started_at)))
        raise
    except BaseException as exc:  # noqa: BLE001 - report, then let Modal see it
        _log_error(job, exc, started_at)
        raise
    _log_tick(job, tick["result"], started_at)
    if isinstance(tick["result"], _Missing):
        raise EntrypointMissing("%s: the module or its entrypoint is not in the deployed image" % job)


CUTOVER_ALERT_PREFIX = "cutover_alert:"
REFUSAL_TEXT = {
    "cutover_missing": "MODE=live but the live store was never seeded. Every scheduled tick is refusing. "
                       "Run changesets/deploy/cutover.py (runbooks/deployment.md step 5).",
    "cutover_stale": "The live store's cutover is older than the limit and no live tick ever accepted it. "
                     "Every scheduled tick is refusing. Check changesets/deploy/cutover.py --status, then "
                     "--redo if no live tick ever ran, or --resume-live after a rollback (runbooks/deployment.md "
                     "step 5, 'If the cutover refuses').",
    "cursor_missing": "The live poller has no complete poller:cursor, so it would re-read up to 20 pages of "
                      "replies. The poller is refusing. Roll back to shadow, then re-seed the live cursor with "
                      "changesets/deploy/cutover.py --resume-live (runbooks/deployment.md, Rollback, "
                      "'Going live again after a rollback').",
}


def _live_refusal(job: str, now=None) -> Optional[str]:
    """Why a live tick must not run, or None. Always None in shadow.

    * ``cutover_missing``: changesets/deploy/cutover.py never seeded the live
      store. An empty live store has no poller cursor, so the first live poll
      would walk back up to 20 pages (2,000 replies) and act on every reply
      from the shadow watch.
    * ``cutover_stale``: the cutover is older than
      store.CUTOVER_MAX_AGE_MINUTES and no live tick has accepted it yet. The
      first tick that accepts a fresh one writes ``cutover:accepted``; from
      then on the age no longer matters.
    * ``cursor_missing`` (poller only): the live cursor is gone or
      incomplete (for example a Dict entry expired after 7 idle days).
    Raises when the store cannot be read: the caller refuses, it never guesses.
    """
    from datetime import datetime, timedelta, timezone

    from shared import settings, store as store_mod

    if not settings.is_live():
        return None
    st = store_mod.get_store()
    record = st.get(store_mod.CUTOVER_KEY)
    if not isinstance(record, dict):
        return "cutover_missing"
    if st.get(store_mod.CUTOVER_ACCEPTED_KEY) is None:
        text = str(record.get("cutover_at") or "").replace("Z", "+00:00")
        try:
            at = datetime.fromisoformat(text)
            at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        except ValueError:
            return "cutover_stale"
        now = now or datetime.now(timezone.utc)
        if now - at > timedelta(minutes=store_mod.CUTOVER_MAX_AGE_MINUTES):
            return "cutover_stale"
        st.set_if_absent(store_mod.CUTOVER_ACCEPTED_KEY, {"accepted_at": now.isoformat(), "job": job,
                                                           "cutover_at": record.get("cutover_at")})
    if job == "poller":
        from services.reply_engine.poller import CURSOR_KEY

        cursor = st.get(CURSOR_KEY)
        if not (isinstance(cursor, dict) and cursor.get("last_email_id") and cursor.get("last_timestamp")):
            return "cursor_missing"
    return None


def _refuse_without_cutover(job: str) -> None:
    """In live, refuse a scheduled tick for any reason _live_refusal gives.

    One ``refused`` row per tick (in the evidence Dict) and one push per reason
    per day make it loud. The daily alert claim is kept in the EVIDENCE Dict,
    not the engine's: a live deploy made before the cutover must leave nothing
    in the live engine store (review item 3).
    """
    try:
        reason = _live_refusal(job)
    except Exception as exc:  # noqa: BLE001 - cannot read the store: refuse, do not guess
        _log_row(job, "refused", {"reason": "store_unreadable", "error": "%s: %s" % (type(exc).__name__, exc)})
        raise CutoverMissing("%s refused: the store could not be read to confirm the cutover" % job)
    if reason is None:
        return
    _log_row(job, "refused", {"reason": reason})
    try:
        from datetime import datetime, timezone

        from shared import store as store_mod
        from shared.notify import notify

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if store_mod.get_obs_store().set_if_absent("%s%s:%s" % (CUTOVER_ALERT_PREFIX, reason, day), {"job": job}):
            notify("Live tick refused: %s" % reason, REFUSAL_TEXT.get(reason, reason), priority="urgent")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not push the refusal alert: %s", exc)
    raise CutoverMissing("%s refused in live: %s (runbooks/deployment.md step 5)" % (job, reason))


def _scheduled(job: str, body) -> None:
    """The one wrapper every Modal schedule goes through."""
    started_at = _now_iso()   # before anything else: the watch report matches runs on their start
    _refuse_without_cutover(job)
    with _tick(job, started_at) as tick:
        tick["result"] = body()


def _run_job(module_name: str, argv: Sequence[str], tick_name: str) -> None:
    """Import jobs.<module> and call main(argv); a non-zero exit fails the tick."""
    import importlib

    def body():
        module = importlib.import_module(module_name)
        code = module.main(list(argv))
        if code not in (0, None):
            raise JobFailed(tick_name, code)
        return {"exit_code": 0 if code is None else code}

    _scheduled(tick_name, body)


# --------------------------------------------------------------------- web
@app.function(image=image, secrets=secrets, timeout=120)
@modal.asgi_app()
def web():
    """FastAPI app (services.reply_engine.app:app). Falls back to a health-only
    app that reports the failure so a shadow deploy is observable. Catches any
    import-time exception, not just ImportError: a module that exists and
    raises a config KeyError must still answer /health."""
    try:
        from services.reply_engine.app import app as fastapi_app  # owned by the A1 brief

        return fastapi_app
    except Exception as exc:  # noqa: BLE001
        logger.warning("services.reply_engine.app unavailable (%s); serving the health-only fallback", exc, exc_info=True)
        from fastapi import FastAPI

        fallback = FastAPI(title="advero-reply-engine (fallback)")
        message = str(exc)

        @fallback.get("/health")
        def health():
            return {"ok": False, "app": "missing", "detail": message}

        return fallback


# --------------------------------------------------------------- schedules
# Plain functions first; the loop at the bottom registers only the ones in
# DEPLOYED_SCHEDULES with Modal. A schedule of a tier that is not deployed
# stays an ordinary function here and does not exist on Modal at all.
def poller():
    """Shadow poller: reads new replies with GET calls (no webhooks yet).

    It also carries the approval SLA chase (approval.escalate_pending), and the
    ``approval_escalation`` schedule runs the same chase on its own */5 tick.
    Both, on purpose: the chase is cheap and idempotent (each rung is claimed
    with set_if_absent), while this function reaches it only if the Instantly
    fetch above it succeeded. A rotated key would otherwise silence the SLA.
    """
    _scheduled("poller", lambda: _call_entrypoint(
        "services.reply_engine.poller", ("run_once", "tick", "poll", "main"),
        time_budget_s=POLLER_TIME_BUDGET_S))


def approval_escalation():
    """The 5-minute reply SLA chase, independent of the poller.

    ``poller.run_once`` calls ``fetch_new_replies`` long before it reaches the
    chase and does not guard it, so a rotated INSTANTLY_API_KEY or an Instantly
    outage raises the whole tick and takes the chase down with it. Running from
    both places is safe: ``escalate_pending`` claims each rung with
    ``store.set_if_absent`` before it pushes, and it takes no Instantly client,
    so no rung of it can send.
    """
    _scheduled("approval_escalation", lambda: _call_entrypoint(
        "services.reply_engine.approval", ("escalate_pending",)))


def cadence_tick():
    """Daily follow-up cadence (S2); the function itself enforces 07:00-19:00 CT."""
    _scheduled("cadence_tick", lambda: _call_entrypoint(
        "services.reply_engine.cadence", ("tick", "run_once", "main")))


def cadence_veto_ping():
    """The 09:30 CT half-hour run the D1 veto window needs. Same entrypoint as
    cadence_tick; the tick is idempotent per lead per day."""
    _scheduled("cadence_veto_ping", lambda: _call_entrypoint(
        "services.reply_engine.cadence", ("tick", "run_once", "main")))


def appointments_tick():
    """Show-rate and no-show detection (S4/S5)."""
    _scheduled("appointments_tick", lambda: _call_entrypoint(
        "services.reply_engine.show_rate", ("appointments_tick", "tick", "run_once", "main")))


def precall_tick():
    """Pre-call brief + proposal draft for a booked call (S6/S7). argv is
    ``--scheduled`` only (push only when there is something to say); this
    job's --now takes an ISO clock, it is not the action flag."""
    _run_job("jobs.precall_tick", SCHEDULES["precall_tick"].argv, "precall_tick")


def no_show_watch():
    """The "I'm on" nudge 3 minutes after a booked call starts (N1). argv is
    ``--no-show-watch``; a run with no call on does nothing."""
    _run_job("jobs.appointments_tick", SCHEDULES["no_show_watch"].argv, "no_show_watch")


def pipeline_sync():
    """Nightly GHL Sales -> Instantly interest mirror (S8). Shadow -> would_do."""
    def body():
        from services.reply_engine.pipeline_sync import run_sync

        return run_sync(dry_run=False)

    _scheduled("pipeline_sync", body)


def pipeline_sweep():
    """07:30 CT sweep: what is waiting on Lorenzo, ordered by money (O3). The
    only scheduled O3 entry (GOL-13)."""
    def body():
        from datetime import datetime, timezone

        from jobs.pipeline_sweep import run_sweep

        return run_sweep(datetime.now(timezone.utc), dry_run=False)

    _scheduled("pipeline_sweep", body)


def _register(name: str) -> Any:
    """Register the module-level function ``name`` as a scheduled Modal
    function. It must stay a module global: the container finds it with
    getattr(module, name). No retries: every body has side effects."""
    fn = globals()[name]
    options = {}  # type: Dict[str, Any]
    if name in MODAL_MAX_CONTAINERS:
        options["max_containers"] = MODAL_MAX_CONTAINERS[name]
    return app.function(image=image, secrets=secrets, schedule=cron(name),
                        timeout=MODAL_TIMEOUTS[name], **options)(fn)


for _name in DEPLOYED_SCHEDULES:
    globals()[_name] = _register(_name)
del _name
