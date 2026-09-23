#!/usr/bin/env python3
"""Generate the schedule change-set from modal_app.SCHEDULES, and check it.

The schedule is DATA, derived from the one place that defines it
(services/reply_engine/modal_app.py SCHEDULES). This script writes:

* changesets/schedules/schedules.json  - every schedule, its tier, its runtime
  (modal or laptop), its cron and what it runs;
* changesets/schedules/laptop/          - the STAGED launchd plists and crontab
  lines that would run the laptop schedules through laptop_runner.py. Staged
  only: nothing here installs them.

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/schedules/build_schedules.py                 # rewrite both
    python3 changesets/schedules/build_schedules.py --check         # exit 1 if stale or the split is wrong
    python3 changesets/schedules/build_schedules.py --check-image   # import every deployed module from
                                                                     # a copy of exactly the Modal mounts

``--check`` also validates the Modal-vs-laptop split (owner decision R4): every
job that hands off through files is on the laptop and is not a Modal function,
every ordering pair shares one runtime, exactly one schedule drives the 07:30
O3 sweep, and the Modal app registers exactly the deployed schedules plus the
web endpoint. ``changesets/tests/test_schedules.py`` runs it.

This script writes files under changesets/schedules/ and nothing else. It
installs nothing, deploys nothing and contacts nothing. Python 3.9.
"""
import argparse
import json
import os
import re
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(HERE))          # .../Agentic Worklfows
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

OUT_PATH = os.path.join(HERE, "schedules.json")
LAPTOP_DIR = os.path.join(HERE, "laptop")
RUNNER_REL = os.path.join("changesets", "schedules", "laptop_runner.py")
LAPTOP_PYTHON = "/usr/bin/python3"      # the interpreter that carries this repo's packages on Lorenzo's Mac
LABEL_PREFIX = "com.advero."
CRONTAB_NAME = "crontab.txt"
# launchd opens StandardOutPath itself, before python starts. ~/Library/Logs
# is outside the folders macOS privacy protection (TCC) guards, unlike
# ~/Desktop where the repo lives, so a blocked run still leaves its error here.
# The home is taken from BASE_DIR, not $HOME, so the generated files do not
# change with the shell that builds them.
_HOME = os.path.join(*Path(BASE_DIR).parts[:3]) if BASE_DIR.startswith("/Users/") else os.path.expanduser("~")
LAUNCHD_LOG_DIR = os.path.join(_HOME, "Library", "Logs", "advero")

# America/Chicago is UTC-5 in daylight time and UTC-6 in standard time. CDT ends
# 2026-11-01 and CST ends 2027-03-14.
CDT_OFFSET_HOURS = 5
CST_OFFSET_HOURS = 6
DST_ENDS = "2026-11-01"
DST_RESUMES = "2027-03-14"

# Owner decision R4: these hand work to another job (or read it back) through
# files. Each Modal function runs in its own container with nothing shared on
# disk, so on Modal the hand-off silently breaks. --check refuses any of them
# on Modal. The reason is carried into schedules.json.
MUST_RUN_ON_LAPTOP = {
    "inbox_placement": "writes the level-2 sidecar and the dated change-set the 07:00 monitor reads",
    "autoresponder_canary": "writes the level-4 sidecar and the dated change-set the 07:00 monitor reads",
    "deliverability_monitor": "reads the placement and canary sidecars and writes proposals into "
                              "changesets/inbox_actions/, which Lorenzo reviews on disk",
    "inbox_inventory": "writes config/inbox_inventory.json, which Lorenzo reads on disk; a Modal container "
                       "would throw it away",
    "list_factory": "stages a CSV, keeps its resumable run state and cost ledger on disk, and needs the "
                    "real source and suppression files",
    "client_scorecard": "needs the client roster and templates on disk",
    "retro_packet": "reads the Job_Log from disk and writes .tmp/retro/",
    "daily_metrics": "reads the list-factory ledger and the Job_Log from disk for the KPI dashboard",
}

# The O3 sweep must have exactly one scheduled entry (GOL-13).
O3_MODULES = ("jobs.pipeline_sweep", "jobs.positive_sweep")

# Everything modal_app does not know: what the job does, what it may write, and
# whether leaving it running in shadow is safe. "command" is how to run a Modal
# schedule by hand from Agentic Worklfows/; a laptop schedule's command is
# derived from its argv in modal_app.SCHEDULES, so the two cannot disagree.
#
# ``shadow_safe`` is the important column. True means: in MODE=shadow this job
# performs no outbound write at all. list_factory is not, and says why.
META = {
    "poller": {
        "command": "python3 -m services.reply_engine.poller --now",
        "purpose": "Read new Instantly replies and route them (S1). No webhooks exist yet, so this polls.",
        "writes": "drafts + approval cards; every send is behind an approval token",
        "shadow_safe": True,
        "needs": [],
    },
    "approval_escalation": {
        "command": ("python3 -c \"import sys;sys.path.insert(0,'.');"
                    "from services.reply_engine import approval;print(approval.escalate_pending())\""),
        "purpose": ("The 5-minute reply SLA chase (S1): a rising ntfy push for every approval card "
                    "Lorenzo has not actioned, counted in sending minutes. The poller runs the same "
                    "chase; this tick exists so an Instantly failure in the poller cannot silence it."),
        "writes": "nothing but ntfy pushes; it takes no Instantly client and no rung of it can send",
        "shadow_safe": True,
        "needs": ["BASE_URL, or every Approve/Veto button on the chase card points at localhost",
                  "NTFY_TOPIC (and NTFY_TOKEN if the card should carry names)"],
    },
    "cadence_tick": {
        "command": "python3 -m jobs.cadence_tick --now",
        "purpose": "Send the due follow-up touch for every armed lead (S2), 07:00-19:00 CT.",
        "writes": "Instantly replies (guarded), ntfy digest",
        "shadow_safe": True,
        "needs": [],
    },
    "cadence_veto_ping": {
        "command": "python3 -m jobs.cadence_tick --now",
        "purpose": ("The 09:30 CT half-hour run the D1 veto window needs. The D1 touch auto-sends "
                    "after a 30-minute veto window opened by a push; an hourly tick never serves it."),
        "writes": "the D1 veto push, then the send after the window closes (guarded)",
        "shadow_safe": True,
        "needs": [],
    },
    "appointments_tick": {
        "command": "python3 -m jobs.appointments_tick --now",
        "purpose": "Show-rate confirmations and no-show detection for booked calls (S4/S5).",
        "writes": "GHL appointment status, SMS and email legs (guarded)",
        "shadow_safe": True,
        "needs": ["GHL_PRIVATE_INTEGRATION_TOKEN", "A2P_10DLC_REGISTERED for the SMS legs",
                  "ZOOM_WEBHOOK_SECRET for real join telemetry"],
    },
    "precall_tick": {
        "command": "python3 -m jobs.precall_tick",
        "purpose": "Pre-call brief before a booked call, and the proposal draft after it (S6/S7).",
        "writes": "GHL notes and proposal drafts (guarded); takes .tmp/precall_tick.lock",
        "shadow_safe": True,
        "needs": ["GHL_PRIVATE_INTEGRATION_TOKEN", "PAYMENT_LINK_URL for the SOP-009 draft"],
    },
    "pipeline_sync": {
        "command": "python3 -m services.reply_engine.pipeline_sync --now",
        "purpose": "Mirror the GHL Sales pipeline onto Instantly interest status (S8).",
        "writes": "Instantly interest status, GHL upserts and notes (guarded)",
        "shadow_safe": True,
        "needs": ["GHL_PRIVATE_INTEGRATION_TOKEN"],
    },
    "pipeline_sweep": {
        "command": "python3 -m jobs.pipeline_sweep --now",
        "purpose": "What is waiting on Lorenzo, ordered by money (O3).",
        "writes": "nothing; one ntfy digest and a Job_Log row. The ONLY scheduled 07:30 sweep: "
                  "jobs/positive_sweep.py delegates to it and is not scheduled (GOL-13)",
        "shadow_safe": True,
        "needs": [],
    },
    "inbox_placement": {
        "purpose": "Score the seed/placement tests and stage the next one (M1 level 2 / O5).",
        "writes": "changesets/inbox_actions/<date>.json + last_placement.json; NEVER fires the create",
        "shadow_safe": True,
        "needs": ["seed addresses (no read-only endpoint lists them; copy them from one UI test)"],
    },
    "autoresponder_canary": {
        "purpose": "Measure auto-responder rate per inbox (M1 level 4 / O7).",
        "writes": "changesets/inbox_actions/<date>.json + last_canary.json",
        "shadow_safe": True,
        "needs": ["a decision on canary-mailing real prospects (DECISIONS Q-J10)",
                  "a usable address pool: 17 today. Each address is mailed once a round, so 12 inboxes need 60 "
                  "for the 5-per-inbox verdict minimum (CANARY_MIN_ADDRESSES_FOR_VERDICT) and 120 for "
                  "the full 10 per inbox (CANARY_ADDRESSES_PER_INBOX)"],
    },
    "deliverability_monitor": {
        "purpose": "The five-level deliverability monitor (M1 / O1). Reads live, proposes, never applies.",
        "writes": "proposals into changesets/inbox_actions/<date>.json, one ntfy card",
        "shadow_safe": True,
        "needs": [],
    },
    "inbox_inventory": {
        "purpose": "Inbox and domain health alerts (M2): roles, flags and sending alerts. No reserve count "
                   "and no buying advice; promotion change-sets come only from a hand-run --promote.",
        "writes": "config/inbox_inventory.json, one ntfy digest and a Job_Log row; nothing live",
        "shadow_safe": True,
        "needs": [],
    },
    "retro_packet": {
        "purpose": "The Friday retro packet (O6): the week's numbers, lessons and three bets.",
        "writes": "markdown in .tmp/retro/ and a skool would_do; posts nothing",
        "shadow_safe": True,
        "needs": ["RIZE_EXPORT_PATH for the hours section", "FIREFLIES_API_KEY for call content"],
    },
    "client_scorecard": {
        "purpose": "Weekly client cards and the F4 retention touches (F3/F4).",
        "writes": "cards and drafts under .tmp/scorecards/, one ntfy digest and a Job_Log row; never sends "
                  "to a client (delivery is manual, by Lorenzo)",
        "shadow_safe": True,
        "needs": ["campaign ids on each roster row; Mike has none, so his card reads 'no source'"],
    },
    "daily_metrics": {
        "purpose": "The daily scorecard row, the DAILY UPDATE block and the Section 6 KPI dashboard (O4).",
        "writes": "a Google Sheets row (guarded) and a STAGED Skool post that is never auto-published",
        "shadow_safe": True,
        "needs": ["DAILY_METRICS_SHEET_ID", "a fresh Skool auth token before the first real post"],
    },
    "list_factory": {
        "purpose": "Source, score, verify, personalise and stage next week's list (O8).",
        "writes": "a staged CSV and create_lead would_do records",
        "shadow_safe": False,
        "shadow_note": ("This is the ONE scheduled job that spends through ALLOW_PAID_CALLS. Shadow stops "
                        "the Instantly writes, but Apify, Perplexity, MillionVerifier and this job's own "
                        "model calls are gated by ALLOW_PAID_CALLS=1 ALONE (owner decision R7): a shadow "
                        "run with the flag set spends. The laptop runner passes ALLOW_PAID_CALLS=0 unless "
                        "LAPTOP_PAID_JOBS names list_factory; keep it that way until Lorenzo approves a "
                        "figure (DECISIONS R14: the preflight prices about $10.20 a niche, and the "
                        "cost-per-contact cap halts every real run before Apify until then). The flag does "
                        "not stop Anthropic spend anywhere else."),
        "needs": ["ALLOW_PAID_CALLS=1 (the runner sets it only when LAPTOP_PAID_JOBS names this job)",
                  "APIFY_API_TOKEN", "MILLIONVERIFIER_API_KEY",
                  "the client-domain suppression list, which is empty today"],
    },
}


def utc_cron(expr: str, offset_hours: int) -> str:
    """Shift a 5-field CT crontab into UTC.

    Only the hour field moves, and only when it is a plain number or a simple
    ``a-b`` range. Anything else (``*``, ``*/5``, a list) is returned unchanged
    because it means the same thing in every zone. A day-of-week field is NOT
    adjusted, so a shift that crosses midnight is flagged rather than guessed:
    ``17:00 CT Fri`` is ``23:00 UTC Fri``, but ``19:15 CT Fri`` in CST is
    ``01:15 UTC SATURDAY`` and a naive shift would silently run it a day early.
    """
    minute, hour, dom, month, dow = expr.split()
    if hour == "*" or hour.startswith("*/") or "," in hour:
        return expr
    if "-" in hour:
        lo, hi = hour.split("-", 1)
        if lo.isdigit() and hi.isdigit():
            new_lo, new_hi = (int(lo) + offset_hours), (int(hi) + offset_hours)
            if new_hi > 23:
                return "%s %s %s %s %s  # CROSSES MIDNIGHT UTC: split this range by hand" % (
                    minute, hour, dom, month, dow)
            return "%s %d-%d %s %s %s" % (minute, new_lo, new_hi, dom, month, dow)
        return expr
    if not hour.isdigit():
        return expr
    shifted = int(hour) + offset_hours
    if shifted > 23:
        return "%s %d %s %s %s  # NOTE: this is the NEXT UTC day; shift the day-of-week too" % (
            minute, shifted - 24, dom, month, dow)
    return "%s %d %s %s %s" % (minute, shifted, dom, month, dow)


def laptop_command(module: str, argv) -> str:
    return " ".join(["python3", "-m", module] + list(argv or ()))


def expand_dow(field: str) -> List[int]:
    """Crontab day-of-week field -> sorted launchd Weekday values (0 = Sunday).
    Only ``*``, a digit, ``a-b`` and comma lists are accepted; anything else
    raises rather than being guessed."""
    if field == "*":
        return []
    days = set()  # type: set
    for part in field.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            if not (lo.isdigit() and hi.isdigit()) or int(lo) > int(hi):
                raise ValueError("unsupported day-of-week range %r" % field)
            days.update(range(int(lo), int(hi) + 1))
        elif part.isdigit():
            days.add(int(part))
        else:
            raise ValueError("unsupported day-of-week field %r" % field)
    return sorted(0 if d == 7 else d for d in days)


def launchd_intervals(expr: str) -> List[Dict[str, int]]:
    """StartCalendarInterval dicts for a fixed-time crontab (minute and hour
    plain numbers, day-of-month and month ``*``). Refuses anything else: the
    laptop schedules are all fixed-time, and a guess here moves a job."""
    minute, hour, dom, month, dow = expr.split()
    if not (minute.isdigit() and hour.isdigit()) or dom != "*" or month != "*":
        raise ValueError("launchd staging only supports 'M H * * DOW' crons, not %r" % expr)
    base = {"Minute": int(minute), "Hour": int(hour)}
    days = expand_dow(dow)
    if not days:
        return [dict(base)]
    return [dict(base, Weekday=d) for d in days]


def turned_off_jobs() -> Dict[str, Dict[str, Any]]:
    """config/turned_off_jobs.json: the jobs Lorenzo turned off (he runs them by hand)."""
    from shared import turned_off

    return turned_off.load()


def validate_turned_off(modal_app, turned_off: Dict[str, Dict[str, Any]]) -> List[str]:
    """A turned-off job is scheduled nowhere, is ordered against nothing, and
    its code is still in the repo."""
    problems = []  # type: List[str]
    for name in sorted(turned_off):
        rec = turned_off[name]
        if name in modal_app.SCHEDULES or name in modal_app.SCHEDULE_JOB_MODULE or name in META:
            problems.append("%s is turned off (config/turned_off_jobs.json) but still scheduled" % name)
        for producer, (consumer, _why) in modal_app.SCHEDULE_ORDERING.items():
            if name in (producer, consumer):
                problems.append("%s is turned off but SCHEDULE_ORDERING still pairs %s -> %s"
                                % (name, producer, consumer))
        module = str(rec.get("module") or "")
        path = os.path.join(BASE_DIR, *module.split(".")) + ".py"
        if not module or not os.path.isfile(path):
            problems.append("%s is turned off but its module %r is not in the repo (keep the code)" % (name, module))
        for field in ("tier", "was_scheduled", "turned_off_on", "by_hand", "why"):
            if not rec.get(field):
                problems.append("%s in config/turned_off_jobs.json has no %s" % (name, field))
    return problems


def validate(modal_app) -> List[str]:
    """Problems with the Modal-vs-laptop split, as sentences. Empty is good."""
    problems = validate_turned_off(modal_app, turned_off_jobs())
    try:
        import modal
        function_type = modal.Function  # type: Any
    except Exception:  # pragma: no cover - modal is installed wherever this runs
        function_type = None

    names = set(modal_app.SCHEDULES)
    for name in sorted(names ^ set(modal_app.SCHEDULE_JOB_MODULE)):
        problems.append("%s is in only one of SCHEDULES and SCHEDULE_JOB_MODULE" % name)
    for name in sorted(names ^ set(META)):
        problems.append("%s is in only one of modal_app.SCHEDULES and build_schedules.META" % name)
    for name in sorted(names):
        sched = modal_app.SCHEDULES[name]
        if sched.tier not in modal_app.TIERS:
            problems.append("%s has unknown tier %r" % (name, sched.tier))
        if sched.runtime not in modal_app.RUNTIMES:
            problems.append("%s has unknown runtime %r" % (name, sched.runtime))
        if len(sched.cron.split()) != 5:
            problems.append("%s cron %r is not five fields" % (name, sched.cron))
        attr = getattr(modal_app, name, None)
        if sched.runtime == modal_app.RUNTIME_LAPTOP:
            if sched.argv is None:
                problems.append("%s runs on the laptop but has no argv" % name)
            if attr is not None:
                problems.append("%s runs on the laptop but modal_app still defines a function for it" % name)
            try:
                launchd_intervals(sched.cron)
            except ValueError as exc:
                problems.append("%s: %s" % (name, exc))
        else:
            if name not in modal_app.MODAL_TIMEOUTS:
                problems.append("%s runs on Modal but has no MODAL_TIMEOUTS entry" % name)
            if not callable(attr) and not (function_type is not None and isinstance(attr, function_type)):
                problems.append("%s runs on Modal but modal_app defines no function for it" % name)
            if name in MUST_RUN_ON_LAPTOP:
                problems.append("%s hands off through files and must run on the laptop (%s)"
                                % (name, MUST_RUN_ON_LAPTOP[name]))
    for name in sorted(set(MUST_RUN_ON_LAPTOP) - names):
        problems.append("%s is in MUST_RUN_ON_LAPTOP but is not scheduled at all" % name)

    for producer, (consumer, _why) in modal_app.SCHEDULE_ORDERING.items():
        if producer not in names or consumer not in names:
            problems.append("ordering pair %s -> %s names an unscheduled job" % (producer, consumer))
            continue
        if modal_app.SCHEDULES[producer].runtime != modal_app.SCHEDULES[consumer].runtime:
            problems.append("ordering pair %s -> %s is split across runtimes; the hand-off needs one disk"
                            % (producer, consumer))

    o3 = sorted(n for n in names if modal_app.SCHEDULE_JOB_MODULE.get(n) in O3_MODULES)
    if len(o3) != 1:
        problems.append("the 07:30 O3 sweep must have exactly one scheduled entry, found %s" % o3)

    deployed = set(modal_app.DEPLOYED_SCHEDULES)
    for name in sorted(deployed):
        if modal_app.SCHEDULES[name].runtime != modal_app.RUNTIME_MODAL:
            problems.append("%s is deployed to Modal but its runtime is %s" % (name, modal_app.SCHEDULES[name].runtime))
        if modal_app.SCHEDULES[name].tier not in modal_app.DEPLOY_TIERS:
            problems.append("%s is deployed but its tier is not in DEPLOY_TIERS" % name)
        if function_type is not None and not isinstance(getattr(modal_app, name, None), function_type):
            problems.append("%s is in DEPLOYED_SCHEDULES but is not a registered modal.Function" % name)
    for name in modal_app.MODAL_SCHEDULES:
        if name not in deployed and function_type is not None \
                and isinstance(getattr(modal_app, name, None), function_type):
            problems.append("%s is registered with Modal although its tier is not deployed" % name)
    try:
        registered = set(modal_app.app.registered_functions)
    except Exception as exc:  # noqa: BLE001
        problems.append("could not read the app's registered functions: %s" % exc)
    else:
        if registered != deployed | {"web"}:
            problems.append("the Modal app registers %s, expected the deployed schedules plus web: %s"
                            % (sorted(registered), sorted(deployed | {"web"})))
    return problems


def build() -> Dict[str, Any]:
    from services.reply_engine import modal_app

    problems = validate(modal_app)
    if problems:
        raise SystemExit("REFUSING, the schedule split is wrong:\n  - " + "\n  - ".join(problems))

    entries = []  # type: List[Dict[str, Any]]
    for name in sorted(modal_app.SCHEDULES):
        sched = modal_app.SCHEDULES[name]
        meta = META[name]
        module = modal_app.SCHEDULE_JOB_MODULE[name]
        on_laptop = sched.runtime == modal_app.RUNTIME_LAPTOP
        entry = {
            "name": name,
            "module": module,
            "tier": sched.tier,
            "runtime": sched.runtime,
            "purpose": meta["purpose"],
            "command": laptop_command(module, sched.argv) if on_laptop else meta["command"],
            # What is scheduled. modal.Cron reads it in SCHEDULE_TZ, so the CT
            # time is literal and nothing drifts on 2026-11-01. The laptop
            # files use the Mac's local clock, which must be Central Time.
            "cron_ct": sched.cron,
            "timezone": modal_app.SCHEDULE_TZ,
            "when_ct": sched.when,
            # Only for a scheduler that cannot take a timezone (a plain crontab,
            # GitHub Actions). Both are given because ONE of them is wrong for
            # half the year.
            "cron_utc_cdt": utc_cron(sched.cron, CDT_OFFSET_HOURS),
            "cron_utc_cst": utc_cron(sched.cron, CST_OFFSET_HOURS),
            "mode": "shadow",
            "shadow_safe": bool(meta["shadow_safe"]),
            "writes": meta["writes"],
            "needs": list(meta.get("needs") or []),
        }
        if on_laptop:
            entry["argv"] = list(sched.argv)
            entry["why_laptop"] = MUST_RUN_ON_LAPTOP.get(name, "")
            entry["launchd_label"] = LABEL_PREFIX + name
        if meta.get("shadow_note"):
            entry["shadow_note"] = meta["shadow_note"]
        if name in modal_app.SCHEDULE_ORDERING:
            consumer, why = modal_app.SCHEDULE_ORDERING[name]
            entry["must_run_before"] = {"schedule": consumer, "why": why}
        entries.append(entry)

    tiers = {}  # type: Dict[str, Any]
    for tier in modal_app.TIERS:
        tiers[tier] = {
            "modal": modal_app.schedules_for(modal_app.RUNTIME_MODAL, (tier,)),
            "laptop": modal_app.schedules_for(modal_app.RUNTIME_LAPTOP, (tier,)),
        }

    return {
        "_about": ("Every schedule in the system as data, generated from "
                   "services/reply_engine/modal_app.py by changesets/schedules/build_schedules.py. "
                   "Do not edit by hand: regenerate."),
        "_generated_from": "services/reply_engine/modal_app.py SCHEDULES + SCHEDULE_JOB_MODULE",
        "_mode": ("Every entry is mode=shadow. MODE=live plus ALLOW_LIVE_WRITES=1 is the only "
                  "combination that writes anything. On Modal that pair lives in the secret; on the "
                  "laptop the runner sets it per job, live only for a tier named in LAPTOP_LIVE_TIERS. "
                  "Flipping either is a Lorenzo-approved step (runbooks/deployment.md)."),
        "_split": ("runtime=modal schedules are registered by `modal deploy` when their tier is in "
                   "DEPLOY_TIERS (default: sales only). runtime=laptop schedules hand off through files "
                   "and never run on Modal; changesets/schedules/laptop/ holds their STAGED launchd "
                   "plists and crontab lines, which run changesets/schedules/laptop_runner.py."),
        "_timezone": ("cron_ct is what is scheduled: modal.Cron reads it in America/Chicago, so the CT "
                      "times are literal. cron_utc_cdt and cron_utc_cst exist only for a scheduler that "
                      "cannot take a timezone; CDT ends %s and CST ends %s, and a job left on a fixed "
                      "UTC cron moves by an hour on each of those dates." % (DST_ENDS, DST_RESUMES)),
        "_install": ("Nothing here is installed. install_schedules.sh --deploy (Lorenzo's terminal) "
                     "deploys the Modal half; the laptop half is copied into place by hand "
                     "(runbooks/deployment.md)."),
        "_turned_off": ("Jobs Lorenzo turned off (he runs them by hand). Not scheduled anywhere; listed so "
                        "a reader can say 'turned off' rather than 'missing'. Source: "
                        "config/turned_off_jobs.json."),
        "deploy_default_tiers": list(modal_app.DEFAULT_DEPLOY_TIERS),
        "tiers": tiers,
        "dst": {"cdt_utc_offset_hours": -CDT_OFFSET_HOURS, "cst_utc_offset_hours": -CST_OFFSET_HOURS,
                "cdt_ends": DST_ENDS, "cst_ends": DST_RESUMES},
        "schedules": entries,
        "turned_off": [dict({"name": name}, **dict((k, v) for k, v in sorted(rec.items())))
                       for name, rec in sorted(turned_off_jobs().items())],
    }


# ------------------------------------------------------------ laptop staging
def render_plist(entry: Dict[str, Any]) -> str:
    """One launchd agent for one laptop schedule. No KeepAlive and no
    RunAtLoad: launchd never restarts a calendar job that exited non-zero, so a
    partial run is recorded once by the runner and not retried."""
    log_path = os.path.join(LAUNCHD_LOG_DIR, "launchd_%s.log" % entry["name"])
    doc = {
        "Label": entry["launchd_label"],
        "ProgramArguments": [LAPTOP_PYTHON, os.path.join(BASE_DIR, RUNNER_REL), entry["name"]],
        "WorkingDirectory": BASE_DIR,
        "StartCalendarInterval": launchd_intervals(entry["cron_ct"]),
        # Only the push opt-in. MODE, ALLOW_LIVE_WRITES and ALLOW_PAID_CALLS
        # are set per job by the runner from LAPTOP_LIVE_TIERS and
        # LAPTOP_PAID_JOBS (both read from .env), never here.
        "EnvironmentVariables": {"NOTIFY_SHADOW_SEND": "1", "PATH": "/usr/local/bin:/usr/bin:/bin"},
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
        "RunAtLoad": False,
        "ProcessType": "Background",
    }
    return plistlib.dumps(doc, sort_keys=True).decode("utf-8")


SELF_TEST_LABEL = LABEL_PREFIX + "self_test"
# Mirrors laptop_runner.SELF_TEST_MARKER_ENV / _VALUE (a test keeps them equal).
SELF_TEST_MARKER_ENV = "ADVERO_STARTED_BY"
SELF_TEST_MARKER_VALUE = "launchd"


def render_self_test_plist() -> str:
    """An agent with NO schedule: `launchctl kickstart` runs it by hand to
    prove launchd can start the runner on the repo (macOS folder access)
    without running a job. It records a self_test row and does nothing else."""
    log_path = os.path.join(LAUNCHD_LOG_DIR, "launchd_self_test.log")
    doc = {
        "Label": SELF_TEST_LABEL,
        "ProgramArguments": [LAPTOP_PYTHON, os.path.join(BASE_DIR, RUNNER_REL), "--self-test"],
        "WorkingDirectory": BASE_DIR,
        # The marker the runner records: only this agent sets it, so a
        # self-test typed in Terminal cannot pass for a launchd start.
        "EnvironmentVariables": {"PATH": "/usr/local/bin:/usr/bin:/bin",
                                 SELF_TEST_MARKER_ENV: SELF_TEST_MARKER_VALUE},
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
        "RunAtLoad": False,
        "ProcessType": "Background",
    }
    return plistlib.dumps(doc, sort_keys=True).decode("utf-8")


def render_crontab(entries: List[Dict[str, Any]]) -> str:
    lines = [
        "# STAGED, NOT INSTALLED. Laptop schedules for the Advero revenue engine, generated by",
        "# changesets/schedules/build_schedules.py. The launchd plists beside this file are the",
        "# recommended form (launchd runs a job missed while the Mac slept once it wakes; cron skips it).",
        "# Use ONE of the two, never both, or every job runs twice.",
        "# Times are the Mac's local clock, which must be Central Time (the runner alerts if it is not).",
        "# MODE / ALLOW_LIVE_WRITES / ALLOW_PAID_CALLS are set per job by laptop_runner.py; do not add them here.",
        "SHELL=/bin/bash",
        "NOTIFY_SHADOW_SEND=1",
    ]
    log = os.path.join(LAUNCHD_LOG_DIR, "cron.log")
    for entry in entries:
        lines.append("%s cd \"%s\" && %s %s %s >> \"%s\" 2>&1" % (
            entry["cron_ct"], BASE_DIR, LAPTOP_PYTHON, RUNNER_REL, entry["name"], log))
    return "\n".join(lines) + "\n"


def staged_laptop_files(data: Dict[str, Any]) -> Dict[str, str]:
    """{file name under laptop/: content} for every staged laptop file."""
    laptop = [e for e in data["schedules"] if e["runtime"] == "laptop"]
    out = {}  # type: Dict[str, str]
    for entry in laptop:
        out["%s.plist" % entry["launchd_label"]] = render_plist(entry)
    out["%s.plist" % SELF_TEST_LABEL] = render_self_test_plist()
    out[CRONTAB_NAME] = render_crontab(laptop)
    return out


# --------------------------------------------------------- image-side check
# Distribution names whose import name differs (python-dotenv -> dotenv).
IMPORT_NAMES = {"python-dotenv": ["dotenv"], "google-auth": ["google"], "pyyaml": ["yaml"]}
INJECTED_BY_MODAL = ("modal",)


def requirements_path() -> str:
    from services.reply_engine import modal_app

    return str(modal_app.REQUIREMENTS)


def allowed_imports(path: Optional[str] = None) -> List[str]:
    """Top-level import names the image provides, from requirements.txt."""
    names = set(INJECTED_BY_MODAL)
    with open(path or requirements_path(), "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            dist = re.split(r"[\[=<>!~; ]", line, 1)[0].strip().lower()
            if dist:
                names.update(IMPORT_NAMES.get(dist, [dist.replace("-", "_")]))
    return sorted(names)


# Runs in the child: imports each module with a meta-path guard that refuses a
# third-party top-level package the image does not install, when the import
# comes from this repo's code (ADVERO_IMAGE_ROOT) rather than from a package.
IMAGE_CHECK_CHILD = """
import importlib, importlib.machinery, os, sys, sysconfig
allowed = set(n for n in os.environ.get('ADVERO_IMAGE_ALLOWED', '').split(',') if n)
root = os.path.realpath(os.environ['ADVERO_IMAGE_ROOT'])
stdlib = os.path.realpath(sysconfig.get_paths()['stdlib'])
refused = []

class Guard(object):
    def find_spec(self, name, path=None, target=None):
        if path is not None or '.' in name or name in allowed or name in sys.builtin_module_names:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name)
        if spec is None or not spec.origin or spec.origin in ('built-in', 'frozen'):
            return None
        origin = os.path.realpath(spec.origin)
        if origin.startswith(root) or (origin.startswith(stdlib) and 'site-packages' not in origin):
            return None
        frame = sys._getframe(1)
        while frame is not None:
            fname = frame.f_code.co_filename
            if not fname.startswith('<frozen') and 'importlib' not in fname:
                break
            frame = frame.f_back
        fname = frame.f_code.co_filename if frame is not None else '<string>'
        caller = os.path.realpath(fname)
        if fname == '<string>' or caller.startswith(root):
            refused.append(name)
            raise ImportError('%s is not in the image requirements (imported from %s)' % (name, caller))
        return None

sys.meta_path.insert(0, Guard())
bad = []
for m in sys.argv[1:]:
    try:
        importlib.import_module(m)
    except Exception as exc:
        bad.append('%s: %s: %s' % (m, type(exc).__name__, exc))
for name in sorted(set(refused)):
    bad.append('third-party import outside requirements.txt: %s' % name)
print('\\n'.join(bad))
sys.exit(1 if bad else 0)
"""


def check_image(modules: Optional[List[str]] = None, timeout: int = 180) -> List[str]:
    """Import every deployed module from a copy of EXACTLY the Modal mounts.

    The laptop has the whole repo on sys.path, so a local import proves
    nothing about the container: changesets/ is not mounted, and a job that
    imports it (or a service nobody mounted) only fails on Modal, unattended.
    This copies each LOCAL_DIRS entry to its remote path under a temp root,
    with the same ignore patterns, and imports from there in a fresh process.
    The child also refuses any third-party import that is not in the image's
    requirements (services/reply_engine/requirements.txt, plus ``modal``,
    which Modal injects): a package that happens to be installed on the
    laptop proves nothing about the image. Imports made BY an allowed package
    (its own dependencies) are let through; only imports made by this repo's
    code are checked. Versions are not compared (the laptop cannot build the
    3.11 image offline); allowed_imports() is what is enforced.
    Returns problems; empty is good. Reads and copies files only.
    """
    from services.reply_engine import modal_app

    if modules is None:
        modules = sorted(set(modal_app.SCHEDULE_JOB_MODULE[n] for n in modal_app.DEPLOYED_SCHEDULES)
                         | {"services.reply_engine.app"})
    root = tempfile.mkdtemp(prefix="advero_image_check_")
    try:
        for local, remote in modal_app.LOCAL_DIRS.items():
            if not os.path.isdir(local):
                continue
            rel = remote[len(modal_app.REMOTE_ROOT):].lstrip("/")
            shutil.copytree(local, os.path.join(root, rel),
                            ignore=shutil.ignore_patterns(*modal_app.IGNORE))
        for pkg in ("services",):
            init = os.path.join(root, pkg, "__init__.py")
            if not os.path.exists(init) and os.path.exists(os.path.join(BASE_DIR, pkg, "__init__.py")):
                shutil.copy(os.path.join(BASE_DIR, pkg, "__init__.py"), init)
        env = dict(os.environ)
        keep = [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
                if p and os.path.abspath(p) != os.path.abspath(BASE_DIR)]
        env["PYTHONPATH"] = os.pathsep.join([root] + keep)
        env["ADVERO_TMP_DIR"] = os.path.join(root, ".tmp")
        env["ADVERO_IMAGE_ALLOWED"] = ",".join(sorted(allowed_imports()))
        env["ADVERO_IMAGE_ROOT"] = root
        proc = subprocess.run([sys.executable, "-c", IMAGE_CHECK_CHILD] + list(modules), cwd=root, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                              universal_newlines=True)
        if proc.returncode == 0:
            return []
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        return lines or ["image import check failed: %s" % proc.stderr.strip()[-500:]]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------- main
def _render_all() -> Dict[str, str]:
    """{absolute path: content} for every generated file."""
    data = build()
    files = {OUT_PATH: json.dumps(data, indent=2, sort_keys=False) + "\n"}
    for name, content in staged_laptop_files(data).items():
        files[os.path.join(LAPTOP_DIR, name)] = content
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if schedules.json or the staged laptop files are stale, or the split is wrong")
    parser.add_argument("--check-image", action="store_true",
                        help="import every deployed module from a copy of exactly the Modal mounts")
    args = parser.parse_args(argv)

    if args.check_image:
        problems = check_image()
        if problems:
            print("REFUSING: these modules do not import from the Modal mounts alone:")
            for line in problems:
                print("  - " + line)
            return 1
        print("every deployed module imports from the Modal mounts alone")
        if not args.check:
            return 0

    rendered = _render_all()
    if args.check:
        stale = []
        for path, content in sorted(rendered.items()):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    if fh.read() != content:
                        stale.append(path)
            except OSError:
                stale.append(path)
        extra = []
        if os.path.isdir(LAPTOP_DIR):
            for name in sorted(os.listdir(LAPTOP_DIR)):
                path = os.path.join(LAPTOP_DIR, name)
                if path not in rendered and (name.endswith(".plist") or name == CRONTAB_NAME):
                    extra.append(path)
        if stale or extra:
            for path in stale:
                print("stale: %s" % os.path.relpath(path, BASE_DIR))
            for path in extra:
                print("not generated (delete it): %s" % os.path.relpath(path, BASE_DIR))
            print("run: python3 changesets/schedules/build_schedules.py")
            return 1
        data = json.loads(rendered[OUT_PATH])
        on_modal = [e["name"] for e in data["schedules"] if e["runtime"] == "modal"]
        on_laptop = [e["name"] for e in data["schedules"] if e["runtime"] == "laptop"]
        print("schedules.json and the staged laptop files match modal_app (%d schedules: %d on Modal, "
              "%d on the laptop; %d turned off: %s); the Modal-vs-laptop split is valid"
              % (len(data["schedules"]), len(on_modal), len(on_laptop), len(data.get("turned_off") or []),
                 ", ".join(e["name"] for e in data.get("turned_off") or []) or "none"))
        return 0

    if not os.path.isdir(LAPTOP_DIR):
        os.makedirs(LAPTOP_DIR)
    for name in os.listdir(LAPTOP_DIR):
        path = os.path.join(LAPTOP_DIR, name)
        if path not in rendered and (name.endswith(".plist") or name == CRONTAB_NAME):
            os.remove(path)
    for path, content in sorted(rendered.items()):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    print("wrote %s and %d staged laptop files" % (os.path.relpath(OUT_PATH, BASE_DIR), len(rendered) - 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
