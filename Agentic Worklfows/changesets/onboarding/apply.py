#!/usr/bin/env python3
"""F1 onboarding change-set: plan only (Blueprint F1, brief A12).

Reads ``manifest.json`` (the single source of truth, shared with
``onboarding_spec.md``), diffs what can be read from live, records every
intended object as a ``would_do`` through ``shared.settings.guard_write`` and
writes one Job_Log row.

    cd "Agentic Worklfows"
    MODE=shadow LLM_FAKE=1 NOTIFY=off python3 changesets/onboarding/apply.py --dry-run
    MODE=shadow LLM_FAKE=1 NOTIFY=off python3 changesets/onboarding/apply.py --dry-run --json

``--apply`` always refuses, and not only because of the controlled-environment
rule. Every target in this change-set is one of:

* ``manual_only``  - GHL has no public create API for workflows, forms or
  calendars, so there is no request to send however live the process is;
* ``no_credential`` - Google Drive (the service account has zero storage quota
  and cannot create a folder), ClickUp and Stripe have no key in any .env.

So ``--apply`` exits 2 with the per-target reason rather than pretending a live
run is one environment variable away. When a credential appears, the target's
``capability`` in the manifest changes and the applier for that one system gets
written then, with a backup-first apply like
``changesets/instantly_webhooks.py``.

Exit codes: 0 plan produced, 1 manifest/data error, 2 apply refused.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import job_log  # noqa: E402
from shared import settings  # noqa: E402
from shared.ghl import GHL  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402

JOB = "changeset_onboarding"
MANIFEST_PATH = os.path.join(HERE, "manifest.json")

# guard_write action names, one per target kind. Keeping them here (rather than
# building a string from the manifest) means the shadow log has a fixed, greppable
# vocabulary that a later applier can replay against.
ACTIONS = {
    "ghl_workflow_kickoff": ("ghl", "create_workflow"),
    "drive_client_folder": ("google_drive", "create_folder_tree"),
    "kickoff_form": ("ghl", "create_form"),
    "kickoff_calendar": ("ghl", "create_calendar"),
    "stripe_invoice": ("stripe", "create_invoice"),
    "clickup_task_template": ("clickup", "create_task_template"),
}


def load_manifest(path: str = MANIFEST_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("manifest has no targets")
    unknown = [t.get("key") for t in targets if t.get("key") not in ACTIONS]
    if unknown:
        # A target added to the manifest with no action mapping would be planned
        # under a made-up guard_write action and silently drift from the spec.
        raise ValueError("manifest targets with no ACTIONS entry: %s" % unknown)
    bad = [t.get("key") for t in targets
           if t.get("capability") not in ("manual_only", "no_credential", "api")]
    if bad:
        raise ValueError("manifest targets with an unknown capability: %s" % bad)
    return data


def preflight(manifest: Dict[str, Any], ghl: Optional[GHL] = None) -> Dict[str, Any]:
    """Read-only look at live state. Never writes, never raises: an unreadable
    source becomes a note so the plan still prints."""
    notes = []  # type: List[str]
    live = {}  # type: Dict[str, Any]

    ghl = ghl if ghl is not None else GHL()
    if not getattr(ghl, "token", None):
        notes.append("ghl_token_missing: no live workflow/calendar/form diff; "
                     "using the state recorded in config/ids.json")
        recorded = (settings.IDS.get("ghl") or {}).get("workflows") or {}
        live["ghl_workflows_recorded"] = {
            k: v for k, v in recorded.items() if isinstance(v, dict)
        }
    else:
        # shared.ghl has no list_workflows today (see the cross-cutting request
        # in the A12 report). Use it if another brief adds one; never assume it.
        lister = getattr(ghl, "list_workflows", None)
        if callable(lister):
            try:
                live["ghl_workflows"] = lister()
            except Exception as exc:  # noqa: BLE001 - a read failure is a note, not a crash
                notes.append("ghl_workflows_read_failed: %s" % exc)
        else:
            notes.append("shared.ghl has no list_workflows(); cannot diff workflows against live")

    for env_key, system in (("STRIPE_SECRET_KEY", "stripe"),
                            ("CLICKUP_API_TOKEN", "clickup"),
                            ("GOOGLE_CREDENTIALS_JSON", "google_drive")):
        if os.environ.get(env_key):
            live["%s_credential" % system] = "present (%s)" % env_key
        else:
            notes.append("%s: no %s in the environment" % (system, env_key))
    if live.get("google_drive_credential"):
        notes.append("google_drive: a service-account credential is present but it has ZERO Drive "
                     "storage quota, so it still cannot create the client folder (see the spec)")

    extends = manifest.get("extends") or {}
    if extends.get("id"):
        recorded = ((settings.IDS.get("ghl") or {}).get("workflows") or {}).get("deal_won_clickup") or {}
        if recorded.get("id") != extends.get("id"):
            notes.append("manifest.extends.id %s does not match ids.json deal_won_clickup %s"
                         % (extends.get("id"), recorded.get("id")))
        else:
            live["extends_workflow"] = recorded
    return {"live": live, "notes": notes}


def plan(manifest: Dict[str, Any], pre: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One planned object per target, each recorded as a reviewable would_do.

    A target that is ``manual_only`` or ``no_credential`` cannot be applied by
    anything, so it is recorded straight to the shadow log rather than through
    ``guard_write``. Under ``MODE=live`` plus ``ALLOW_LIVE_WRITES=1``,
    ``guard_write`` writes a ``live_write_intent`` Job_Log row BEFORE the call
    it is guarding, and shared/README.md says an intent with no matching
    ``live_write_ok`` or ``live_write_failed`` is the signature of a write that
    died in flight. This script never makes a call at all, so a harmless plan
    run left six rows reading as "a Stripe invoice and a GHL workflow may have
    been created". Only a target the manifest marks ``api`` is guarded.
    """
    out = []  # type: List[Dict[str, Any]]
    for target in sorted(manifest["targets"], key=lambda t: t.get("order", 0)):
        system, action = ACTIONS[target["key"]]
        payload = {k: v for k, v in target.items()
                   if k not in ("order", "capability", "preflight_read", "spec_section")}
        if target["capability"] == "api":
            record = settings.guard_write(system, action, payload)
        else:
            job_log.shadow(system, action, payload)
            record = {"shadow": True, "recorded": "plan_only",
                      "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
        out.append({
            "key": target["key"],
            "system": system,
            "action": action,
            "capability": target["capability"],
            "reason": manifest.get("capability_reasons", {}).get(target["capability"], ""),
            "blocker": target.get("blocker"),
            "spec_section": target.get("spec_section"),
            "guard": {"shadow": record.get("shadow"), "ts": record.get("ts"),
                      "recorded": record.get("recorded", "guard_write")},
        })
    return out


def render(manifest: Dict[str, Any], pre: Dict[str, Any], planned: List[Dict[str, Any]]) -> str:
    lines = ["F1 onboarding change-set: PLAN ONLY (nothing created)",
             "mode=%s  live_writes=%s" % (settings.get_mode(), settings.is_live()),
             "extends: %s (%s)" % ((manifest.get("extends") or {}).get("name"),
                                   (manifest.get("extends") or {}).get("id")),
             ""]
    for item in planned:
        lines.append("  [%s] %s.%s  (%s)" % (item["capability"], item["system"], item["action"], item["key"]))
        if item.get("blocker"):
            lines.append("      blocker: %s" % item["blocker"])
        elif item.get("reason"):
            lines.append("      %s" % item["reason"])
    lines.append("")
    if pre["notes"]:
        lines.append("notes:")
        for note in pre["notes"]:
            lines.append("  - %s" % note)
    counts = {}  # type: Dict[str, int]
    for item in planned:
        counts[item["capability"]] = counts.get(item["capability"], 0) + 1
    lines.append("")
    lines.append("totals: " + ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))
    lines.append("apply: refused. Every target is manual_only or no_credential; see onboarding_spec.md.")
    return "\n".join(lines)


def run(manifest_path: str = MANIFEST_PATH, ghl: Optional[GHL] = None) -> Dict[str, Any]:
    manifest = load_manifest(manifest_path)
    pre = preflight(manifest, ghl=ghl)
    planned = plan(manifest, pre)
    result = {
        "job": JOB,
        "mode": settings.get_mode(),
        "planned": planned,
        "live": pre["live"],
        "notes": pre["notes"],
        "applicable": [p["key"] for p in planned if p["capability"] == "api"],
    }
    result["text"] = render(manifest, pre, planned)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="F1 onboarding change-set (plan only)")
    parser.add_argument("--dry-run", action="store_true", help="produce the plan (the default)")
    parser.add_argument("--apply", action="store_true", help="refused: see the module docstring")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    args = parser.parse_args(argv)

    from shared.job_log import use_scratch_logs
    use_scratch_logs("changeset_onboarding")  # plan runs are evidence, not operations

    try:
        result = run(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log_run(JOB, "error", {"error": str(exc)})
        notify("Onboarding change-set failed", "plan could not be built: %s" % exc, priority="high")
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if args.apply:
        log_run(JOB, "apply_refused", {"reasons": [
            {"key": p["key"], "capability": p["capability"]} for p in result["planned"]]})
        print(result["text"])
        print("\n--apply refused: nothing in this change-set has an applier, by design.", file=sys.stderr)
        for item in result["planned"]:
            print("  %-24s %s" % (item["key"], item.get("blocker") or item["reason"]), file=sys.stderr)
        return 2

    log_run(JOB, "dry_run", {
        "targets": len(result["planned"]),
        "manual_only": sum(1 for p in result["planned"] if p["capability"] == "manual_only"),
        "no_credential": sum(1 for p in result["planned"] if p["capability"] == "no_credential"),
        "notes": result["notes"],
    })
    if args.json:
        print(json.dumps(result, indent=1, default=str))
    else:
        print(result["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
