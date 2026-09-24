#!/usr/bin/env python3
"""Instantly copy change-set (edits made in the one Google Doc): dry-run or guarded apply.

Dry-run (the default, zero writes to Instantly):
    cd "Agentic Worklfows"
    python3 changesets/instantly_copy/apply_instantly_copy.py --staged changesets/instantly_copy/staged/<stem>
    python3 changesets/instantly_copy/apply_instantly_copy.py --staged DIR --campaign cleaning_reactivation
    python3 changesets/instantly_copy/apply_instantly_copy.py --staged DIR --from-snapshot   # offline

Before anything is read from Instantly, the staged folder is verified: the
export, manifest and snapshot recorded in staged.json must exist and match
their sha256, and re-running build_from_doc.plan() on them must reproduce every
staged file byte for byte. Otherwise: exit 1, no GET.

For every staged campaign the dry-run GETs the live campaign (or reads the
manifest's snapshot with --from-snapshot) and first checks that live still
equals the baseline the doc was built from: the same step count, each step's
type, delay and delay_unit, the same variant count, and every variant's subject
and body equal to the manifest's raw_subject / raw_html (an edited variant may
also already hold the staged value). If live drifted, that campaign is REFUSED
and the drift is printed: someone changed it in Instantly after the doc was
made, and applying would silently overwrite that change. Otherwise it prints
the plain-text diff live -> target and the exact PATCH body, and writes a
dry-run copy (never a rollback point) under
.tmp/changeset_dryruns/instantly_copy/instantly_copy_<id>_<ts>.dryrun.json.
Dry-run Job_Log rows go to .tmp/scratch/instantly_copy_dryrun/.

Apply (refused unless MODE=live AND ALLOW_LIVE_WRITES=1; one campaign at a time;
only after Lorenzo said "done" on the doc AND, separately, "go live"):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_copy/apply_instantly_copy.py \
        --staged DIR --apply --campaign cleaning_reactivation

The apply reads live, runs the drift check, prints the diff and the PATCH,
and sends nothing (and writes no backup) when live already equals the target.
Otherwise it asks for the campaign key typed back (unless --yes), reads live
AGAIN and refuses if the sequences moved while the prompt was open, writes the
before-image changesets/backups/instantly_copy_<id>_<ts>.preapply.json, then
sends ONE ``PATCH /campaigns/{id}`` with only ``{"sequences": [...]}``, built
from the LIVE sequences with only the edited variants' subject/body swapped,
so live-only keys (v_disabled, pre_delay_unit, ...) survive. The PATCH goes
through changesets/rollback.py patch_and_settle (Instantly.update_campaign, so
shared.settings.guard_write runs inside it), which settles the before-image
into the rollback point instantly_copy_<id>_<ts>.json.

Rollback (live, one campaign, typed confirmation):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_copy/apply_instantly_copy.py \
        --apply --restore changesets/backups/instantly_copy_<id>_<ts>.json --campaign cleaning_reactivation

Exit codes: 0 ok; 1 staged folder not verifiable against its export/manifest,
or live drifted from the doc baseline; 2 live write refused (not live,
--dry-run with --apply, no --campaign, --from-snapshot with --apply, typed
confirmation mismatch, live moved during the prompt, backup not writable,
shadow record); 3 API error (a multi-campaign dry-run reports it and goes on
with the others) or a PATCH that was not verified (the before-image is then
kept as the rollback point).
"""
import argparse
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import job_log, settings  # noqa: E402
from shared.instantly import Instantly, InstantlyError, default_client  # noqa: E402
from changesets import rollback as R  # noqa: E402
from changesets.instantly_copy import build_from_doc as B  # noqa: E402
from changesets.instantly_copy import copy_lib as C  # noqa: E402

SCRIPT = "instantly_copy"
BACKUP_DIR = os.path.join(ROOT, "changesets", "backups")

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2
EXIT_API = 3


class StagedInvalid(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stem(campaign_id: str, now: datetime) -> str:
    return "%s_%s_%s" % (SCRIPT, campaign_id, R.stamp(now))


# ------------------------------------------------------------------ staged
def load_staged(staged_dir: str) -> Dict[str, Any]:
    """staged.json and every campaign file, VERIFIED against their sources.

    Offline and before any GET: the recorded export, manifest and snapshot must
    exist and match their recorded sha256, and re-running the build's plan()
    on them must reproduce every staged file byte for byte (with the recorded
    built_at). So a staged folder can only ever carry what the doc export
    holds; a hand edit, however consistent, is refused. The drift baseline is
    the manifest's raw_html/raw_subject (types from the snapshot), rebuilt
    here, never read from the staged files."""
    meta_path = os.path.join(staged_dir, "staged.json")
    try:
        meta = C.load_json(meta_path)
    except (OSError, ValueError) as exc:
        raise StagedInvalid("cannot read %s: %s" % (meta_path, exc))
    if not isinstance(meta, dict) or meta.get("tool") != C.TOOL:
        raise StagedInvalid("%s was not written by %s" % (meta_path, C.TOOL))
    problems = []  # type: List[str]
    for field in ("export", "manifest", "snapshot"):
        rec = meta.get(field)
        if not isinstance(rec, str) or not rec:
            problems.append("staged.json records no %s" % field)
            continue
        path = C.resolve(rec)
        if not os.path.isfile(path):
            problems.append("the recorded %s %s is gone (moved or deleted); re-export and re-build" % (field, rec))
        elif C.sha256_file(path) != meta.get("%s_sha256" % field):
            problems.append("the recorded %s %s changed since the build (sha256 differs); re-build" % (field, rec))
    if problems:
        raise StagedInvalid("the staged change-set in %s cannot be verified:\n  %s" % (staged_dir, "\n  ".join(problems)))
    try:
        p = B.plan(C.resolve(meta["export"]), C.resolve(meta["manifest"]))
    except (OSError, ValueError, KeyError) as exc:
        raise StagedInvalid("re-building from the recorded export failed: %s" % exc)
    if p["errors"]:
        raise StagedInvalid("the recorded export no longer builds:\n  %s" % "\n  ".join(p["errors"]))
    if p["snapshot_rel"] != meta["snapshot"]:
        raise StagedInvalid("the manifest now names snapshot %s, the staged folder %s" % (p["snapshot_rel"], meta["snapshot"]))
    expected = B.render(p, meta["export"], meta["manifest"], meta.get("built_at") or "")
    listed_map = meta.get("campaigns")
    if not isinstance(listed_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and C.CAMPAIGN_FILE_RE.match(v) for k, v in listed_map.items()):
        raise StagedInvalid("%s: 'campaigns' must map campaign keys to <key>.json file names" % meta_path)
    listed = ["staged.json"] + list(listed_map.values())
    if sorted(listed) != sorted(expected):
        raise StagedInvalid("%s lists %s, a re-build from the export gives %s"
                            % (meta_path, sorted(listed), sorted(expected)))
    for name, data in expected.items():
        try:
            with open(os.path.join(staged_dir, name), "r", encoding="utf-8") as fh:
                have = fh.read()
        except OSError as exc:
            raise StagedInvalid("cannot read %s: %s" % (name, exc))
        if have != C.dumps(data):
            raise StagedInvalid("%s differs from what the recorded export builds (edited by hand?); re-run "
                                "build_from_doc.py" % os.path.join(staged_dir, name))
    campaigns = OrderedDict()  # type: Dict[str, Dict[str, Any]]
    for key, c in p["campaigns"].items():
        campaigns[key] = {"key": key, "campaign_id": c["campaign_id"], "baseline": c["doc_baseline"],
                          "target": c["sequences"], "changes": c["changes"]}
    if not campaigns:
        raise StagedInvalid("%s stages no campaign" % staged_dir)
    return {"meta": meta, "campaigns": campaigns, "snapshot_path": p["snapshot_path"]}


def fetch_campaign(client: Optional[Instantly], campaign_id: str, snapshot_path: Optional[str]) -> Dict[str, Any]:
    if snapshot_path:
        for item in C.load_json(snapshot_path).get("items", []):
            if item.get("id") == campaign_id:
                return item
        raise InstantlyError("campaign %s not in snapshot %s" % (campaign_id, snapshot_path))
    if client is None:
        raise InstantlyError("no Instantly client and --from-snapshot not set")
    return client.get_campaign(campaign_id)


def refuse_live(action: str, out: Callable[[str], None]) -> int:
    out("REFUSED: %s needs MODE=live and ALLOW_LIVE_WRITES=1 (have MODE=%s ALLOW_LIVE_WRITES=%s). "
        "Nothing was written." % (action, settings.get_mode(), os.environ.get("ALLOW_LIVE_WRITES", "")))
    job_log.log_run("instantly_copy.apply", "refused", {"action": action, "mode": settings.get_mode()})
    return EXIT_REFUSED


# ------------------------------------------------------------- one campaign
def _show_drift(drifted: List[str], out: Callable[[str], None]) -> None:
    out("REFUSED: live no longer matches the copy the doc was built from, so applying would silently "
        "overwrite a change made in Instantly after the doc was made. Re-export the campaign into a "
        "new doc (or undo the Instantly edit) first. Drift:")
    for d in drifted:
        out("  " + d)


def process_campaign(
    camp: Dict[str, Any],
    client: Optional[Instantly],
    args: argparse.Namespace,
    out: Callable[[str], None],
    now: datetime,
    backup_dir: str,
    snapshot_path: Optional[str] = None,
    dryrun_dir: Optional[str] = None,
    confirm: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Dry-run or apply one staged campaign.

    Order on --apply (as rollback.restore does it): read live, drift check,
    print the diff and the PATCH, ask the typed confirmation, READ LIVE AGAIN
    and refuse if anything moved while the prompt was open, write the
    before-image, send the one PATCH."""
    key, cid = camp["key"], camp["campaign_id"]
    job = "instantly_copy.apply" if args.apply else "instantly_copy.dry_run"
    result = {"campaign": key, "id": cid, "ok": False, "writes": 0}  # type: Dict[str, Any]
    out("=" * 78)
    out("%s  (%s)" % (key, cid))
    out("=" * 78)
    live = fetch_campaign(client, cid, snapshot_path)
    source = "snapshot %s" % C.rel(snapshot_path) if snapshot_path else "live GET /campaigns/%s" % cid
    out("source: %s  name=%r  status=%s  updated=%s" % (source, live.get("name"), live.get("status"),
                                                        live.get("timestamp_updated")))
    for c in camp["changes"]:
        out("edit: step%d variant %d %s  (%s)" % (c["step"], c["variant_index"], c["field"], c["tag"]))
        for n in c.get("format_notes") or []:
            out("  " + n)
        for w in c.get("warnings") or []:
            out("  WARNING (from the build): %s" % w)
        src = c.get("propagated_from")
        if src:
            src_key = (C.parse_tag(src) or ("?",))[0]
            out("  NOTE: NOT EDITED IN THIS CAMPAIGN'S BLOCK. This text comes from the edit to %s (campaign %s), "
                "because the doc shares this sentence across campaigns. %s's leads will get: %r"
                % (src, src_key, key, c.get("new_text")))

    drifted = C.drift(live.get("sequences"), camp["baseline"], camp["changes"])
    if drifted:
        _show_drift(drifted, out)
        result["drift"] = drifted
        result["exit"] = EXIT_INVALID
        job_log.log_run(job, "drift", {"campaign": key, "campaign_id": cid, "drift": drifted})
        return result

    live_steps = C.steps_of(live.get("sequences"))
    for c in camp["changes"]:
        var = live_steps[c["step"] - 1]["variants"][c["variant_index"]]
        if var.get("v_disabled"):
            out("WARNING: step%d variant %d is switched off in Instantly (v_disabled); the edit lands but that "
                "variant does not send until it is switched on." % (c["step"], c["variant_index"]))

    patch_sequences = C.apply_changes(live["sequences"], camp["changes"])
    patch = {"sequences": patch_sequences}
    noop = patch_sequences == live["sequences"]
    result["noop"] = noop
    if args.apply or not args.no_diff:
        out("plain-text diff (live -> target):")
        out(C.text_diff(live["sequences"], patch_sequences, key))
    if not args.no_diff:
        out("PATCH /campaigns/%s body%s:" % (cid, " (not sent: live already equals the target)" if noop else ""))
        out(json.dumps(patch, indent=1, ensure_ascii=False))

    if not args.apply:
        point = R.build_point(SCRIPT, R.KIND_DRYRUN, live, ["sequences"], now, cid, key, after=patch,
                              extra={"staged": args.staged, "noop": noop})
        path = R.write_point(dryrun_dir or R.dryrun_dir(SCRIPT), _stem(cid, now), point)
        result["dryrun_copy"] = path
        out("dry-run copy (not a rollback point): %s" % path)
        out("RESULT: dry-run OK%s. writes=0" % (" (live already equals the target)" if noop else ""))
        result["ok"] = True
        job_log.log_run(job, "ok", {"campaign": key, "campaign_id": cid, "source": source, "noop": noop,
                                    "edits": [c["tag"] for c in camp["changes"]]})
        return result

    # ---- apply (already gated in main(); re-checked here). Every refusal
    # happens BEFORE the before-image is written.
    if not settings.is_live():
        result["exit"] = refuse_live("apply %s" % key, out)
        return result
    if noop:
        out("RESULT: live already equals the target; PATCH skipped, no backup written. writes=0")
        result["ok"] = True
        job_log.log_run(job, "noop", {"campaign": key, "campaign_id": cid})
        return result
    if confirm is not None and not confirm():
        out("aborted: confirmation did not match; nothing was written")
        result["exit"] = EXIT_REFUSED
        return result
    # The prompt can stay open for minutes: read again and act only if live
    # did not move meanwhile; the before-image and the PATCH come from THIS read.
    fresh = fetch_campaign(client, cid, None)
    if fresh.get("sequences") != live.get("sequences"):
        where = R.diff_paths(live.get("sequences"), fresh.get("sequences"), "sequences")
        out("REFUSED: the campaign's sequences changed while the confirmation was open (%s); nothing was sent "
            "or written. Re-run and read the new diff." % "; ".join(where))
        result["exit"] = EXIT_REFUSED
        job_log.log_run(job, "refused", {"campaign": key, "error": "moved during the prompt", "at": where})
        return result
    live = fresh
    patch = {"sequences": C.apply_changes(live["sequences"], camp["changes"])}
    try:
        point = R.build_point(SCRIPT, R.KIND_PREAPPLY, live, ["sequences"], now, cid, key, after=patch,
                              extra={"staged": args.staged})
        preapply = R.write_point(backup_dir, _stem(cid, now), point)
    except OSError as exc:
        out("RESULT: refused, the before-image could not be written (%s); nothing was sent." % exc)
        result["exit"] = EXIT_REFUSED
        job_log.log_run(job, "refused", {"campaign": key, "error": "backup failed: %s" % exc})
        return result
    out("before-image: %s" % preapply)
    settled = R.patch_and_settle(client, cid, patch, preapply, {"sequences": live["sequences"]})
    result["backup"] = settled["path"]
    result["outcome"] = settled["outcome"]
    if settled["outcome"] == "shadow":
        out("RESULT: shadow record only (no HTTP).")
        result["exit"] = EXIT_REFUSED
        return result
    result["writes"] = 1
    out(R.describe_outcome(settled))
    job_log.log_run(job, "applied" if settled["ok"] else "apply_unverified",
                    {"campaign": key, "campaign_id": cid, "edits": [c["tag"] for c in camp["changes"]],
                     "outcome": settled["outcome"], "rollback_point": settled["path"], "error": settled["error"]})
    if settled["ok"]:
        result["ok"] = True
        out("RESULT: PATCH /campaigns/%s applied and verified. writes=1" % cid)
    else:
        result["exit"] = EXIT_API
        out("RESULT: PATCH /campaigns/%s NOT verified (%s). The before-image is kept as the rollback point "
            "%s; see runbooks/instantly_copy_from_doc.md (exit 3)." % (cid, settled["outcome"], settled["path"]))
    return result


# -------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--staged", help="folder written by build_from_doc.py (not needed with --restore)")
    p.add_argument("--campaign", help="campaign key (required with --apply)")
    p.add_argument("--dry-run", action="store_true", help="the default; refused together with --apply or --restore")
    p.add_argument("--apply", action="store_true", help="PATCH one campaign (MODE=live + ALLOW_LIVE_WRITES=1 + --campaign)")
    p.add_argument("--from-snapshot", action="store_true", help="dry-run against the manifest's snapshot, offline")
    p.add_argument("--restore", metavar="ROLLBACK_POINT", help="PATCH an instantly_copy rollback point back (live, needs --apply and --campaign)")
    p.add_argument("--accept-interrupted", action="store_true", help="with --restore: also accept a .preapply file left by a run that died mid-PATCH")
    p.add_argument("--override-later-changes", action="store_true", help="with --restore: undo changes made after the apply too; never with --yes")
    p.add_argument("--no-diff", action="store_true", help="dry-run: do not print the text diff and the PATCH body (an apply always shows the diff before the prompt)")
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation (the live flags are still required)")
    return p


def main(argv: Optional[List[str]] = None, client: Optional[Instantly] = None, now: Optional[datetime] = None,
         out: Callable[[str], None] = print, backup_dir: str = BACKUP_DIR,
         confirm: Optional[Callable[[str], str]] = None, dryrun_dir: Optional[str] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run and (args.apply or args.restore):
        out("REFUSED: --dry-run cannot be combined with --apply or --restore; say which one you mean.")
        return EXIT_REFUSED
    if R.override_with_yes(args):
        out(R.OVERRIDE_WITH_YES)
        return EXIT_REFUSED
    if args.apply or args.restore:
        return _main(args, client, now, out, backup_dir, confirm, dryrun_dir)
    with R.scratch_logs("instantly_copy_dryrun"):
        return _main(args, client, now, out, backup_dir, confirm, dryrun_dir)


def _main(args: argparse.Namespace, client: Optional[Instantly], now: Optional[datetime],
          out: Callable[[str], None], backup_dir: str, confirm: Optional[Callable[[str], str]],
          dryrun_dir: Optional[str]) -> int:
    now = now or _utcnow()
    if args.apply and args.from_snapshot:
        out("REFUSED: --apply cannot run against --from-snapshot; a snapshot is not live state.")
        return EXIT_REFUSED
    if args.restore and not args.apply:
        out("REFUSED: --restore is a live write, so it needs --apply (and --campaign <key>).")
        return EXIT_REFUSED
    if args.apply and not args.campaign:
        out("REFUSED: --apply needs --campaign <key>; live application is one campaign at a time.")
        return EXIT_REFUSED

    staged = None  # type: Optional[Dict[str, Any]]
    if not args.restore:
        if not args.staged:
            out("--staged DIR is required (the folder build_from_doc.py wrote).")
            return EXIT_INVALID
        try:
            staged = load_staged(args.staged)
        except StagedInvalid as exc:
            out("REFUSED: %s" % exc)
            job_log.log_run("instantly_copy.apply" if args.apply else "instantly_copy.dry_run", "invalid",
                            {"staged": args.staged, "error": str(exc)[:400]})
            return EXIT_INVALID
        if args.campaign and args.campaign not in staged["campaigns"]:
            out("campaign %r has no staged change in %s; staged: %s"
                % (args.campaign, args.staged, sorted(staged["campaigns"])))
            return EXIT_INVALID
    elif R.campaign_id_for(args.campaign) is None:
        out("unknown campaign key %r; known: %s" % (args.campaign, sorted(settings.CAMPAIGNS or {})))
        return EXIT_INVALID

    if args.apply and not settings.is_live():
        return refuse_live("--restore" if args.restore else "--apply", out)

    snapshot_path = None  # type: Optional[str]
    if args.from_snapshot:
        snapshot_path = staged.get("snapshot_path")
        if not snapshot_path or not os.path.isfile(snapshot_path):
            out("--from-snapshot: the staged folder records no readable snapshot (%r)" % snapshot_path)
            return EXIT_INVALID
    elif client is None:
        try:
            client = default_client()
        except InstantlyError as exc:
            out("no Instantly client: %s (use --from-snapshot for an offline dry-run)" % exc)
            return EXIT_INVALID

    target = args.campaign or ""

    def typed() -> bool:
        if args.yes:
            return True
        answer = (confirm or input)("Type the campaign key (%s) to confirm the LIVE write: " % target)
        return answer.strip() == target

    if args.restore:
        kinds = (R.KIND_APPLY, R.KIND_PREAPPLY) if args.accept_interrupted else (R.KIND_APPLY,)
        cid = R.campaign_id_for(args.campaign)
        try:
            code, info = R.restore(client, SCRIPT, args.restore, cid, args.campaign, backup_dir, _stem(cid, now),
                                   now, out, accept_kinds=kinds, confirm=typed,
                                   override_later_changes=args.override_later_changes)
        except InstantlyError as exc:
            out("API error: %s" % exc)
            job_log.log_run("instantly_copy.restore", "api_error", {"error": str(exc)[:200]})
            return EXIT_API
        status = {EXIT_OK: "applied", EXIT_INVALID: "refused", EXIT_REFUSED: "refused"}.get(code, "restore_failed")
        if info.get("outcome") == "already_restored":
            status = "noop"
        job_log.log_run("instantly_copy.restore", status, info)
        return code

    keys = [args.campaign] if args.campaign else list(staged["campaigns"])
    results = []
    for key in keys:
        try:
            results.append(process_campaign(staged["campaigns"][key], client, args, out, now, backup_dir,
                                            snapshot_path, dryrun_dir, confirm=typed))
        except InstantlyError as exc:
            # report it, carry on with the other campaigns, exit 3 at the end
            out("API error on %s: %s" % (key, exc))
            job_log.log_run("instantly_copy.apply" if args.apply else "instantly_copy.dry_run", "api_error",
                            {"campaign": key, "error": str(exc)[:200]})
            results.append({"campaign": key, "ok": False, "writes": 0, "exit": EXIT_API, "api_error": str(exc)[:200]})

    out("")
    out("SUMMARY (%s, MODE=%s, ALLOW_LIVE_WRITES=%s)" % ("APPLY" if args.apply else "DRY-RUN", settings.get_mode(),
                                                        os.environ.get("ALLOW_LIVE_WRITES", "")))
    total = 0
    for r in results:
        total += r["writes"]
        state = "OK" if r["ok"] else ("DRIFT" if r.get("drift") else ("API" if r.get("api_error") else "FAIL"))
        out("  %-26s %-5s %s writes=%d" % (r["campaign"], state,
                                          "noop" if r.get("noop") else (r.get("backup") or ("dry-run copy" if r.get("dryrun_copy") else "-")),
                                          r["writes"]))
    out("  WRITES PERFORMED: %d" % total)
    bad = [r for r in results if not r["ok"]]
    if not bad:
        return EXIT_OK
    return max(r.get("exit", EXIT_INVALID) for r in bad)


if __name__ == "__main__":
    sys.exit(main())
