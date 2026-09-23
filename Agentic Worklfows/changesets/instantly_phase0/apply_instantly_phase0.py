#!/usr/bin/env python3
"""Phase 0 Instantly change-set: dry-run (default) or guarded apply.

Dry-run (the default, zero writes):
    cd "Agentic Worklfows"
    python3 changesets/instantly_phase0/apply_instantly_phase0.py                 # all six, live GET
    python3 changesets/instantly_phase0/apply_instantly_phase0.py --campaign cleaning_reactivation
    python3 changesets/instantly_phase0/apply_instantly_phase0.py --from-snapshot # offline, uses config/snapshots
    python3 changesets/instantly_phase0/apply_instantly_phase0.py --labels        # lead-label taxonomy dry-run

For each campaign the dry-run: GETs the live campaign (read-only), validates the
staged sequence (spintax balance, merge variables, em dashes, proof point vs
offers.md), prints a unified diff of the plain-text bodies and the settings
delta, and saves a copy of the live campaign as
.tmp/changeset_dryruns/phase0/phase0_<id>_<ts>.dryrun.json. A dry-run never
writes to changesets/backups/ and its Job_Log rows go to
.tmp/scratch/phase0_dryrun/, not the production .tmp/job_log.csv.

Apply (refused unless MODE=live AND ALLOW_LIVE_WRITES=1, one campaign at a time):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_phase0/apply_instantly_phase0.py \
        --apply --campaign cleaning_reactivation

The apply PATCHes only the fields where live differs from the staged copy, and
skips the PATCH entirely when live already matches, so a re-apply never
replaces the rollback point with a copy of the new state. The before-image is
written as changesets/backups/phase0_<id>_<ts>.preapply.json and settled by
changesets/rollback.py (see there for every file kind): it becomes the
unsuffixed rollback point phase0_<id>_<ts>.json once the PATCH was
acknowledged, and after ANY PATCH error too (a 504 can land later, so the only
before-image must stay restorable; restoring an unchanged campaign is a no-op).

Rollback (live, one campaign, typed confirmation):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_phase0/apply_instantly_phase0.py \
        --apply --restore changesets/backups/phase0_<campaign_id>_<ts>.json --campaign cleaning_reactivation

--restore refuses any file that is not an unsuffixed phase0 rollback point for
that campaign. It reads live first and prints what it would change, refuses
when a field changed after the apply (add --override-later-changes to undo
those changes too), then asks for the typed confirmation, and PATCHes only the
fields that apply changed.

Labels (R9, owner decision 2026-09-22): created with use_with_ai false. After
the create the script reads the labels back and writes the value each one got
to changesets/instantly_phase0/lead_label_values.json, where the detectors can
pick them up before AI labelling is ever switched on.

Exit codes: 0 ok, 1 validation/data error, 2 live write refused, 3 API error.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import job_log, settings  # noqa: E402
from shared.instantly import Instantly, default_client, InstantlyError, interest_status_codes  # noqa: E402
from services.experiments.copy_validator import validate_copy  # noqa: E402
from changesets.instantly_phase0 import phase0_lib as L  # noqa: E402
from changesets import rollback as R  # noqa: E402

SCRIPT = "phase0"
BACKUP_DIR = os.path.join(ROOT, "changesets", "backups")
# R9 / GOL-11: where the created labels' values are recorded for the detectors.
# A change-set output, deliberately not config/ids.json.
LABEL_VALUES_PATH = os.path.join(HERE, "lead_label_values.json")
# The read-back does not know the field name Instantly uses for a custom
# label's value (the contract only says "their own value in -30000..30000").
# These are tried in order; a label with none of them is reported, not guessed.
LABEL_VALUE_KEYS = ("interest_status", "interest_value", "lt_interest_status", "value")
SNAPSHOT_PATH = os.path.join(ROOT, "config", "snapshots", "instantly_campaigns_2026-09-21.json")
EXPECTED_LABELS = [
    "positive_interested", "positive_question", "positive_referral", "neutral_question",
    "negative_notnow", "negative_notfit", "negative_hostile", "unsubscribe", "ooo",
    "wrong_person", "auto_reply_unmonitored",
]

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2
EXIT_API = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdMismatch(ValueError):
    """campaign_settings.json and config/ids.json disagree about a campaign id."""


def assert_ids_match_ids_json(cfg_all: Dict[str, Any], keys: Optional[List[str]] = None) -> None:
    """config/ids.json is the single source for ids; campaign_settings.json is a
    second copy of them and is what this script actually PATCHes.

    A transposed uuid in that second copy silently retargets every write at a
    different live campaign: two campaigns on the same offer type pass the proof,
    variable and money checks with the other one's copy, and only the campaign
    name in the header would betray it. The sibling script
    changesets/instantly_subsequences/apply_subsequences.py::build_payloads
    already refuses this; so does this one now, before anything is read or
    written.
    """
    live_ids = settings.CAMPAIGNS or {}
    bad = []  # type: List[str]
    for key in sorted(keys if keys is not None else cfg_all.get("campaigns", {})):
        staged = (cfg_all["campaigns"].get(key) or {}).get("id")
        canonical = (live_ids.get(key) or {}).get("id")
        if canonical is None:
            bad.append("%s: not in config/ids.json instantly.campaigns" % key)
        elif staged != canonical:
            bad.append("%s: campaign_settings.json says %s, config/ids.json says %s" % (key, staged, canonical))
    if bad:
        raise IdMismatch(
            "campaign id mismatch between changesets/instantly_phase0/campaign_settings.json and "
            "config/ids.json; refusing to touch any campaign:\n  " + "\n  ".join(bad))


# ------------------------------------------------------------------ helpers
def fetch_campaign(client: Optional[Instantly], campaign_id: str, from_snapshot: bool) -> Dict[str, Any]:
    if from_snapshot:
        snap = L.load_json(SNAPSHOT_PATH)
        for item in snap.get("items", []):
            if item.get("id") == campaign_id:
                return item
        raise InstantlyError("campaign %s not in snapshot %s" % (campaign_id, SNAPSHOT_PATH))
    if client is None:
        raise InstantlyError("no Instantly client (INSTANTLY_API_KEY missing?) and --from-snapshot not set")
    return client.get_campaign(campaign_id)


def describe_backup(backup: Dict[str, Any]) -> str:
    steps = (backup.get("sequences") or [{}])[0].get("steps") or []
    variants = sum(len(st.get("variants") or []) for st in steps)
    return "name=%r timestamp_updated=%s steps=%d variants=%d pl_value=%r" % (
        backup.get("name"), backup.get("timestamp_updated"), len(steps), variants, backup.get("pl_value"))


def brief(value: Any) -> str:
    """Readable one-liner for a settings value; a campaign_schedule printed raw
    buries the rest of the delta."""
    if isinstance(value, dict) and "schedules" in value:
        sc = (value.get("schedules") or [{}])[0]
        days = (sc.get("days") or {})
        on = "".join(d for d in sorted(days) if days[d])
        timing = sc.get("timing") or {}
        return "%s-%s %s days[%s]" % (timing.get("from"), timing.get("to"), sc.get("timezone"), on)
    return repr(value)


def format_delta(delta: Dict[str, Dict[str, Any]]) -> str:
    lines = []
    for k in sorted(delta):
        d = delta[k]
        mark = "CHANGE" if d["changed"] else "same  "
        lines.append("  %s %-20s live=%s -> desired=%s" % (mark, k, brief(d["live"]), brief(d["desired"])))
    return "\n".join(lines)


def live_allowed() -> bool:
    return settings.is_live()


def refuse_live(action: str, out: Callable[[str], None]) -> int:
    out(
        "REFUSED: %s needs MODE=live and ALLOW_LIVE_WRITES=1 (have MODE=%s ALLOW_LIVE_WRITES=%s). "
        "Nothing was written." % (action, settings.get_mode(), os.environ.get("ALLOW_LIVE_WRITES", ""))
    )
    job_log.log_run("phase0.apply", "refused", {"action": action, "mode": settings.get_mode()})
    return EXIT_REFUSED


# ------------------------------------------------------------- campaign run
def _stem(campaign_id: str, now: datetime) -> str:
    return "%s_%s_%s" % (SCRIPT, campaign_id, R.stamp(now))


def process_campaign(
    key: str,
    cfg_all: Dict[str, Any],
    client: Optional[Instantly],
    args: argparse.Namespace,
    out: Callable[[str], None],
    now: datetime,
    backup_dir: str,
    dryrun_dir: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = cfg_all["campaigns"][key]
    assert_ids_match_ids_json(cfg_all, [key])
    campaign_id = cfg["id"]
    result = {"campaign": key, "id": campaign_id, "ok": False, "writes": 0, "shadow_records": 0}  # type: Dict[str, Any]
    out("=" * 78)
    out("%s  (%s)" % (key, campaign_id))
    out("=" * 78)

    live = fetch_campaign(client, campaign_id, args.from_snapshot)
    source = "snapshot" if args.from_snapshot else "live GET /campaigns/%s" % campaign_id
    out("source: %s  name=%r  status=%s  updated=%s" % (source, live.get("name"), live.get("status"), live.get("timestamp_updated")))

    doc = L.load_sequence(key)
    # The EXTENDED validator, not phase0_lib.validate_sequence. Same call
    # signature, same Report object, same .ok/.errors/.warnings/.summary(), plus
    # the three A7 rules: a merge variable inside a spin block, one proof family
    # per campaign, and a readability flag over 30 words. The first of those is
    # the trap that mattered: {{RANDOM | thanks {{firstName}} | cheers
    # {{firstName}}}} passes the base validator and ships the literal
    # {{firstName}} to a prospect. This is the ONLY path that can PATCH a live
    # campaign, so the gate has to be the strict one here.
    rep = validate_copy(key, doc, live, cfg_all, settings.OFFERS_MD)
    out(rep.summary())
    result["errors"] = list(rep.errors)
    result["warnings"] = list(rep.warnings)

    desired = L.desired_settings(cfg_all, key)
    delta = L.settings_delta(live, desired)
    result["settings_delta"] = {k: v for k, v in delta.items() if v["changed"]}
    out("settings delta:")
    out(format_delta(delta))
    out("note: AI Smart Pause for OOO is a UI toggle (Campaign > Settings); not in this patch.")

    lost = L.dropped_step_keys(live, doc)
    result["dropped_step_keys"] = lost
    if lost:
        out("step keys the PATCH would DELETE from the live steps: %s "
            "(PATCH replaces `sequences` wholesale; Instantly re-defaults whatever is missing)" % lost)
    else:
        out("step keys: the staged steps carry every key the live steps carry.")

    if not args.no_diff:
        out("plain-text diff (live -> staged):")
        out(L.sequence_diff(live, doc, key))

    full_patch = L.build_patch(doc, desired)
    differ = R.mismatches(live, full_patch)
    result["differ"] = differ
    out("fields that differ from live (what an apply would PATCH): %s" % (differ or "none"))

    if not args.apply and not args.no_backup:
        # A dry-run copy is never a rollback point: a dry-run of an
        # already-applied campaign captures the NEW copy. It goes under .tmp
        # with the .dryrun suffix, never into changesets/backups/ (SAF-10).
        point = R.build_point(SCRIPT, R.KIND_DRYRUN, live, differ, now, campaign_id, key,
                              after=dict((k, full_patch[k]) for k in differ))
        path = R.write_point(dryrun_dir or R.dryrun_dir(SCRIPT), _stem(campaign_id, now), point)
        result["dryrun_copy"] = path
        out("dry-run copy (not a rollback point): %s" % path)

    new_vars = set(cfg.get("new_variables") or [])
    uses_new = bool(new_vars) and any(
        new_vars & L.merge_variables(v.get("subject", "") + "\n" + L.html_to_text(v.get("body", "")))
        for _s, _v, _st, v in L.iter_variants(doc)
    )
    result["uses_new_variables"] = uses_new

    if not rep.ok:
        out("RESULT: validation FAILED, this campaign cannot be applied.")
        job_log.log_run("phase0.apply" if args.apply else "phase0.dry_run", "invalid",
                        {"campaign": key, "errors": rep.errors})
        return result
    result["ok"] = True

    if not args.apply:
        out("RESULT: dry-run OK. writes=0")
        job_log.log_run(
            "phase0.dry_run", "ok",
            {"campaign": key, "source": source, "changed": sorted(result["settings_delta"]),
             "differ": differ, "warnings": len(rep.warnings)},
        )
        return result

    # ---- apply path (already gated by main(); re-checked here for safety).
    # Every refusal happens BEFORE the before-image is written, so a refused
    # run leaves no file behind at all.
    if uses_new and not args.allow_new_variables:
        out("RESULT: refused, staged copy uses new merge variables %s; pass --allow-new-variables once the leads carry them." % sorted(new_vars))
        result["ok"] = False
        result["errors"].append("new variables without --allow-new-variables")
        return result
    if not live_allowed():
        result["ok"] = False
        result["exit"] = refuse_live("apply %s" % key, out)
        return result
    if not differ:
        # GOL-9: a re-apply must never overwrite the rollback point with a copy
        # of the already-changed campaign, so nothing is written at all.
        out("RESULT: live already matches the staged change-set; PATCH skipped, no backup written. writes=0")
        result["noop"] = True
        job_log.log_run("phase0.apply", "noop", {"campaign": key, "campaign_id": campaign_id})
        return result

    patch = dict((k, full_patch[k]) for k in differ)
    before = dict((k, live.get(k)) for k in differ)
    try:
        point = R.build_point(SCRIPT, R.KIND_PREAPPLY, live, differ, now, campaign_id, key, after=patch)
        preapply = R.write_point(backup_dir, _stem(campaign_id, now), point)
    except OSError as exc:
        out("RESULT: refused, the before-image could not be written (%s); nothing was sent." % exc)
        result["ok"] = False
        result["exit"] = EXIT_REFUSED
        job_log.log_run("phase0.apply", "refused", {"campaign": key, "error": "backup failed: %s" % exc})
        return result
    out("before-image: %s (becomes the rollback point once the PATCH outcome is settled)"
        % os.path.relpath(preapply, ROOT) if preapply.startswith(ROOT) else "before-image: %s" % preapply)
    settled = R.patch_and_settle(client, campaign_id, patch, preapply, before)
    result["backup"] = settled["path"]
    result["outcome"] = settled["outcome"]
    if settled["outcome"] == "shadow":
        result["shadow_records"] += 1
        result["ok"] = False
        out("RESULT: shadow record only (no HTTP).")
        return result
    result["writes"] += 1
    out(R.describe_outcome(settled))
    job_log.log_run("phase0.apply", "applied" if settled["ok"] else "apply_unverified",
                    {"campaign": key, "campaign_id": campaign_id, "keys": sorted(patch),
                     "outcome": settled["outcome"], "rollback_point": settled["path"],
                     "error": settled["error"]})
    if settled["ok"]:
        out("RESULT: PATCH /campaigns/%s applied and verified. writes=1" % campaign_id)
    else:
        result["ok"] = False
        result["exit"] = EXIT_API
        out("RESULT: PATCH /campaigns/%s NOT verified (%s)." % (campaign_id, settled["outcome"]))
    return result


def restore_campaign(
    path: str,
    client: Optional[Instantly],
    out: Callable[[str], None],
    cfg_all: Dict[str, Any],
    campaign_key: str,
    backup_dir: str,
    now: datetime,
    accept_interrupted: bool = False,
    confirm: Optional[Callable[[], bool]] = None,
    override_later_changes: bool = False,
) -> int:
    """PATCH a phase0 rollback point back onto ITS campaign.

    changesets/rollback.py refuses anything that is not an unsuffixed phase0
    rollback point for this campaign (dry-run copies, .prerestore and
    .not_applied files, promotion or inbox-action backups, hand-made files),
    reads live and prints the per-field change BEFORE asking ``confirm``,
    refuses a field that changed after the apply unless
    ``override_later_changes``, and PATCHes only the fields that apply changed.
    """
    expected = (cfg_all["campaigns"].get(campaign_key) or {}).get("id")
    kinds = (R.KIND_APPLY, R.KIND_PREAPPLY) if accept_interrupted else (R.KIND_APPLY,)
    code, info = R.restore(client, SCRIPT, path, expected, campaign_key, backup_dir,
                           _stem(expected, now), now, out, accept_kinds=kinds, confirm=confirm,
                           override_later_changes=override_later_changes)
    status = {R.EXIT_OK: "applied", R.EXIT_INVALID: "refused", R.EXIT_REFUSED: "refused"}.get(code, "restore_failed")
    if info.get("outcome") == "already_restored":
        status = "noop"
    job_log.log_run("phase0.restore", status, info)
    return code


# ------------------------------------------------------------------ labels
def _label_value(row: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """(value, the key it came from). The field name is not in the contract
    yet, so the key is recorded per label for whoever wires the detectors."""
    for key in LABEL_VALUE_KEYS:
        value = row.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and -30000 <= value <= 30000:
            return value, key
    return None, None


def _live_labels(client: Instantly) -> List[Dict[str, Any]]:
    return [r for r in client.iterate("lead-labels", {"limit": 100}) if isinstance(r, dict)]


def process_labels(client: Optional[Instantly], args: argparse.Namespace, out: Callable[[str], None],
                   now: Optional[datetime] = None, backup_dir: str = BACKUP_DIR,
                   label_values_path: Optional[str] = None) -> int:
    now = now or _utcnow()
    doc = L.load_json(L.LABELS_PATH)
    labels = doc["labels"]
    errors = L.validate_labels(labels, EXPECTED_LABELS)
    if errors:
        for e in errors:
            out("ERROR %s" % e)
        return EXIT_INVALID
    existing = []  # type: List[str]
    live_rows = []  # type: List[Dict[str, Any]]
    if client is not None and not args.from_snapshot:
        live_rows = _live_labels(client) if args.apply else (client.lead_labels_list().get("items", []))
        existing = [it.get("label") for it in live_rows]
    to_create = [lab for lab in labels if lab["label"] not in existing]
    out("lead labels: %d staged, %d already exist, %d would be created" % (len(labels), len(labels) - len(to_create), len(to_create)))
    for lab in to_create:
        out("  would create %-24s %-8s use_with_ai=%s %s" % (
            lab["label"], lab["interest_status_label"], lab["use_with_ai"], lab["description"][:50]))
    if not args.apply:
        out("RESULT: dry-run OK. writes=0")
        job_log.log_run("phase0.labels_dry_run", "ok", {"would_create": [l["label"] for l in to_create]})
        return EXIT_OK
    if not live_allowed():
        return refuse_live("create lead labels", out)

    # GOL-20 item 7: the live label list is backed up before anything is
    # created. Labels are deleted in the UI only, so this is evidence of what
    # existed, not something --restore replays.
    try:
        point = R.build_point(SCRIPT, R.KIND_EVIDENCE, {"items": live_rows}, [], now,
                              object_type="lead_labels")
        before_path = R.write_point(backup_dir, "%s_lead_labels_%s" % (SCRIPT, R.stamp(now)), point)
    except OSError as exc:
        out("REFUSED: the lead-label backup could not be written (%s); nothing was created." % exc)
        job_log.log_run("phase0.labels_apply", "refused", {"error": "backup failed: %s" % exc})
        return EXIT_REFUSED
    out("live label list saved to %s" % before_path)

    writes = 0
    create_errors = []  # type: List[str]
    for lab in to_create:
        try:
            resp = client.lead_labels_create(lab["label"], lab["interest_status_label"], lab["description"], lab["use_with_ai"])
        except InstantlyError as exc:
            create_errors.append("%s: %s" % (lab["label"], str(exc)[:200]))
            break                      # stop at the first failure; the read-back says what exists
        if not (isinstance(resp, dict) and resp.get("shadow")):
            writes += 1

    # Read back every staged label and record the value Instantly gave it.
    readback_error = None
    try:
        after_rows = _live_labels(client)
    except InstantlyError as exc:
        after_rows = []
        readback_error = str(exc)[:200]
    by_name = dict((r.get("label"), r) for r in after_rows)
    mapping = {}  # type: Dict[str, Any]
    problems = list(create_errors)
    if readback_error:
        problems.append("read-back failed: %s" % readback_error)
    for lab in labels:
        row = by_name.get(lab["label"])
        if row is None:
            problems.append("%s: not found in the read-back" % lab["label"])
            continue
        value, source_key = _label_value(row)
        if value is None:
            problems.append("%s: no integer value in any of %s; read the row by hand (keys: %s)"
                            % (lab["label"], list(LABEL_VALUE_KEYS), sorted(row)))
        if row.get("use_with_ai") is True:
            problems.append("%s: live has use_with_ai=true; R9 says false until every detector "
                            "reads the new values. Turn it off in the UI." % lab["label"])
        mapping[lab["label"]] = {
            "id": row.get("id"),
            "value": value,
            "value_key": source_key,
            "interest_status_label": row.get("interest_status_label", lab["interest_status_label"]),
            "use_with_ai": row.get("use_with_ai"),
            "raw": row,
        }
    # A value is only trustworthy if every label got its own one and none of
    # them is a built-in interest code: a candidate key that happens to hold,
    # say, the positive/negative flag would otherwise be recorded as complete.
    values = [m["value"] for m in mapping.values() if m["value"] is not None]
    builtin = set(interest_status_codes()) or set(range(-4, 5))
    if len(set(values)) != len(values):
        problems.append("label values are not distinct (%s): the value key %s is probably not the "
                        "custom interest value" % (sorted(values), sorted(set(str(m["value_key"]) for m in mapping.values()))))
    clash = sorted(n for n, m in mapping.items() if m["value"] in builtin)
    if clash:
        problems.append("%s carry a built-in interest code (%s), so the value key is not the custom "
                        "label value" % (clash, sorted(builtin)))
    record = {
        "_about": ("Written by apply_instantly_phase0.py --labels --apply from GET /lead-labels "
                   "after the create. The value per label is the custom interest value Instantly "
                   "assigned; every detector (pipeline sweep, experiments analytics, retro "
                   "metrics, pipeline sync) must read these before AI labelling is switched on "
                   "(R9). Not config/ids.json on purpose."),
        "read_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "complete": not problems,
        "problems": problems,
        "labels": mapping,
    }
    values_path = label_values_path or LABEL_VALUES_PATH
    try:
        R._write_json(values_path, record)
    except OSError as exc:
        problems.append("could not write %s: %s" % (values_path, exc))
    out("label values recorded in %s" % values_path)
    for p in problems:
        out("PROBLEM %s" % p)
    job_log.log_run("phase0.labels_apply", "applied" if not problems else "errors",
                    {"created": writes, "backup": before_path, "values_path": values_path,
                     "problems": problems})
    out("RESULT: labels %s. writes=%d" % ("applied and read back" if not problems else "INCOMPLETE", writes))
    return EXIT_OK if not problems else EXIT_API


# -------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campaign", help="campaign key from config/ids.json (required with --apply)")
    p.add_argument("--dry-run", action="store_true",
                   help="the default; validate + diff, zero writes. Refused together with --apply or --restore")
    p.add_argument("--apply", action="store_true", help="PATCH the campaign (MODE=live + ALLOW_LIVE_WRITES=1 + --campaign)")
    p.add_argument("--from-snapshot", action="store_true", help="read campaigns from config/snapshots instead of the API")
    p.add_argument("--labels", action="store_true", help="operate on the lead-label taxonomy instead of campaigns")
    p.add_argument("--restore", metavar="ROLLBACK_POINT", help="PATCH a phase0 rollback point back onto its campaign; needs --apply and --campaign <key> (live only)")
    p.add_argument("--accept-interrupted", action="store_true",
                   help="with --restore: also accept a .preapply file left by a run that died mid-PATCH")
    p.add_argument("--override-later-changes", action="store_true",
                   help="with --restore: restore even though a field changed after the apply (undoes that change too); never with --yes")
    p.add_argument("--allow-new-variables", action="store_true", help="allow copy that uses merge variables the campaign does not have yet")
    p.add_argument("--no-backup", action="store_true", help="dry-run only: skip the .dryrun copy")
    p.add_argument("--no-diff", action="store_true")
    p.add_argument("--yes", action="store_true",
                   help="skip the typed confirmation on --apply (including --apply --restore); the live "
                        "flags are still required, and it is refused together with --override-later-changes")
    return p


def main(
    argv: Optional[List[str]] = None,
    client: Optional[Instantly] = None,
    now: Optional[datetime] = None,
    out: Callable[[str], None] = print,
    backup_dir: str = BACKUP_DIR,
    confirm: Optional[Callable[[str], str]] = None,
    dryrun_dir: Optional[str] = None,
    label_values_path: Optional[str] = None,
) -> int:
    args = build_parser().parse_args(argv)
    # GOL-20 item 6: --dry-run used to default to True and be ignored, so
    # `--dry-run --apply` applied. The combination is now refused outright.
    if args.dry_run and (args.apply or args.restore):
        out("REFUSED: --dry-run cannot be combined with --apply or --restore; say which one you mean.")
        return EXIT_REFUSED
    if R.override_with_yes(args):
        out(R.OVERRIDE_WITH_YES)
        return EXIT_REFUSED
    if args.apply or args.restore:
        return _main(args, client, now, out, backup_dir, confirm, dryrun_dir, label_values_path)
    # GOL-20 item 5: a dry-run never writes the production Job_Log.
    with R.scratch_logs("phase0_dryrun"):
        return _main(args, client, now, out, backup_dir, confirm, dryrun_dir, label_values_path)


def _main(args: argparse.Namespace, client: Optional[Instantly], now: Optional[datetime],
          out: Callable[[str], None], backup_dir: str, confirm: Optional[Callable[[str], str]],
          dryrun_dir: Optional[str], label_values_path: Optional[str]) -> int:
    now = now or _utcnow()
    cfg_all = L.load_settings()
    keys = list(cfg_all["campaigns"].keys())

    # ---- contradictory flag combinations are refused BEFORE anything is read,
    # written or backed up. Each of these used to reach the write path and die
    # with a traceback (or, for --restore, PATCH live with no confirmation).
    if args.apply and args.from_snapshot:
        out("REFUSED: --apply cannot run against --from-snapshot; a snapshot is not live state.")
        return EXIT_REFUSED
    if args.apply and args.no_backup:
        out("REFUSED: --apply with --no-backup would leave no rollback point. Drop --no-backup.")
        return EXIT_REFUSED
    if args.restore and not args.apply:
        out("REFUSED: --restore is a live write, so it needs --apply (and --campaign <key>).")
        return EXIT_REFUSED
    if args.restore and args.labels:
        out("REFUSED: --restore and --labels are separate operations.")
        return EXIT_REFUSED
    if args.restore and not args.campaign:
        out("REFUSED: --restore needs --campaign <key>; the key is checked against the id in the file.")
        return EXIT_REFUSED
    if args.campaign and args.campaign not in cfg_all["campaigns"]:
        out("unknown campaign key %r; known: %s" % (args.campaign, keys))
        return EXIT_INVALID
    try:
        assert_ids_match_ids_json(cfg_all)
    except IdMismatch as exc:
        out("REFUSED: %s" % exc)
        job_log.log_run("phase0.apply", "refused", {"error": "campaign id mismatch"})
        return EXIT_INVALID

    if client is None and not args.from_snapshot:
        try:
            client = default_client()
        except InstantlyError as exc:
            out("no Instantly client: %s (use --from-snapshot for an offline dry-run)" % exc)
            return EXIT_INVALID

    if args.apply:
        if args.labels:
            pass
        elif not args.campaign:
            out("REFUSED: --apply needs --campaign <key>; live application is one campaign at a time.")
            return EXIT_REFUSED
        if not live_allowed():
            return refuse_live("--restore" if args.restore else "--apply", out)

    target = args.campaign or "labels"

    def typed() -> bool:
        if args.yes:
            return True
        answer = (confirm or input)("Type the target (%s) to confirm the LIVE write: " % target)
        return answer.strip() == target

    # A restore asks only AFTER it has read live and printed what it would
    # change (re-review defect 3); every other live write asks here.
    if args.apply and not args.restore and not typed():
        out("aborted: confirmation did not match")
        return EXIT_REFUSED

    try:
        if args.restore:
            return restore_campaign(args.restore, client, out, cfg_all, args.campaign, backup_dir, now,
                                    accept_interrupted=args.accept_interrupted, confirm=typed,
                                    override_later_changes=args.override_later_changes)
        if args.labels:
            return process_labels(client, args, out, now=now, backup_dir=backup_dir,
                                  label_values_path=label_values_path)
    except InstantlyError as exc:
        out("API error: %s" % exc)
        job_log.log_run("phase0.apply", "api_error", {"error": str(exc)[:200]})
        return EXIT_API

    if args.campaign:
        keys = [args.campaign]

    results = []
    for key in keys:
        try:
            results.append(process_campaign(key, cfg_all, client, args, out, now, backup_dir, dryrun_dir))
        except InstantlyError as exc:
            out("API error on %s: %s" % (key, exc))
            job_log.log_run("phase0.apply" if args.apply else "phase0.dry_run", "api_error",
                            {"campaign": key, "error": str(exc)[:200]})
            return EXIT_API

    out("")
    out("SUMMARY (%s, MODE=%s, ALLOW_LIVE_WRITES=%s)" % (
        "APPLY" if args.apply else "DRY-RUN", settings.get_mode(), os.environ.get("ALLOW_LIVE_WRITES", "")))
    total_writes = 0
    all_ok = True
    for r in results:
        total_writes += r["writes"]
        all_ok = all_ok and r["ok"]
        changed = ",".join("%s:%s->%s" % (k, brief(v["live"]), brief(v["desired"])) for k, v in sorted(r.get("settings_delta", {}).items()))
        out("  %-26s %-7s errors=%d warnings=%d settings[%s] backup=%s writes=%d" % (
            r["campaign"], "OK" if r["ok"] else "FAIL", len(r.get("errors", [])), len(r.get("warnings", [])),
            changed or "none", r.get("backup") or ("dry-run copy" if r.get("dryrun_copy") else "no"), r["writes"]))
    out("  WRITES PERFORMED: %d" % total_writes)
    if not all_ok:
        return results[0].get("exit", EXIT_INVALID) if len(results) == 1 else EXIT_INVALID
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
