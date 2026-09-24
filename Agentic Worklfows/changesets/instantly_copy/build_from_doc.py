#!/usr/bin/env python3
"""Stage Lorenzo's doc edits to the 6 live Instantly cold campaigns. Offline.

    cd "Agentic Worklfows"
    python3 changesets/instantly_copy/build_from_doc.py EXPORT.txt \
        [--manifest tools/template_doc/manifest.json] [--out DIR] [--overwrite]

EXPORT.txt is Drive's text/plain export of the one Google Doc
(1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U). It is diffed against the
manifest with tools/template_doc/parse_doc.py + diff_doc.py; only the
``instantly.*`` blocks are used here (the engine templates go through the doc
router, not this script; unknown tags that do not start with ``instantly.``,
such as a build fingerprint line, are ignored).

Refused, with nothing written (exit 1), when:
  * an ``instantly.*`` tag is missing from the doc (a deleted step cannot be
    applied from the doc), the doc has an unknown ``instantly.`` tag, or any
    duplicate tag;
  * a changed text breaks a copy rule (see copy_lib.check_copy): a note for
    Claude or a doc layout line inside the email, dashes and "--", "!" in any
    form, AI/automation, single-brace placeholders like {first_name},
    unbalanced {{ }}, a merge variable inside a spin, a bad spin, a variable
    the campaign does not have, a subject added to step 2 or removed from
    step 1, an empty body, a new dollar figure / promised time window /
    reactivation guarantee not in config/offers.md;
  * copies of one shared sentence (the six step-1 subjects) were edited to
    different texts;
  * config/offers.md cannot be read, a campaign has no offer type in
    config/ids.json, the manifest disagrees with its snapshot, or a campaign
    id disagrees with config/ids.json.
Nothing is "fixed"; every problem is printed.

An edit to one copy of a shared sentence is staged for every Instantly block
that shares it (the doc says "changing it once is enough").

Otherwise it writes, for each campaign with at least one changed subject or
body, ``<campaign_key>.json`` (the snapshot's full ``sequences`` with only the
changed variants' body, text_to_html(doc text), and/or subject, doc text
trimmed, replaced) and ``staged.json`` (export, manifest and snapshot paths and
sha256, doc id, built_at, every change with old and new text). The apply
script rebuilds all of it from the recorded export and manifest and refuses a
folder that does not match byte for byte, so keep the export file.

--out must be inside changesets/instantly_copy/staged/ (default
staged/<export file stem>/) or the system temp dir. --overwrite replaces only a
folder this tool wrote, and deletes only the files its staged.json lists.

A clean export stages nothing, writes nothing, and exits 0.

Exit codes: 0 staged (or nothing to stage), 1 refused (data or copy error).
Next step: apply_instantly_copy.py --staged DIR (a dry-run by default).
"""
import argparse
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from changesets import rollback as R  # noqa: E402
from changesets.instantly_copy import copy_lib as C  # noqa: E402
from changesets.instantly_phase0 import phase0_lib as L  # noqa: E402
from shared import job_log, settings  # noqa: E402

EXIT_OK = 0
EXIT_INVALID = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def plan(export_path: str, manifest_path: str) -> Dict[str, Any]:
    """Everything a build writes, computed without writing. Deterministic in
    (export, manifest, snapshot, config/ids.json, config/offers.md): the apply
    script re-runs it to verify a staged folder."""
    manifest = C.diff_doc.load_manifest(manifest_path)
    info = C.parse_doc.parse_with_info(C.read_export(export_path))
    report = C.diff_doc.diff(info, manifest)
    parsed = info["blocks"]
    errors = []  # type: List[str]
    warnings = []  # type: List[str]
    try:
        offers_md = settings.require_offers()
    except RuntimeError as exc:
        errors.append(str(exc))
        offers_md = ""

    blocks = OrderedDict((b["tag"], b) for b in manifest["blocks"] if b["tag"].startswith(C.TAG_PREFIX))
    if report["duplicates"]:
        errors.append("the doc has duplicate tags (a block was copied): %s" % ", ".join(sorted(set(report["duplicates"]))))
    for tag in report["missing"]:
        if tag.startswith(C.TAG_PREFIX):
            errors.append("%s is missing from the doc. Deleting an Instantly step from the doc is not "
                          "supported; put the block back (or change the step in Instantly by hand)." % tag)
    for tag in report["unknown"]:
        if tag.startswith(C.TAG_PREFIX):
            errors.append("unknown tag %s in the doc: new Instantly steps or variants cannot be added from "
                          "the doc" % tag)

    # The snapshot the manifest was built from supplies step types and the full
    # objects the staged target is built on; the manifest supplies the copy.
    snap_rel = manifest.get("snapshot") or next((b.get("source") for b in blocks.values()), None)
    snapshot_path = C.resolve(snap_rel) if snap_rel else None
    snap = {}  # type: Dict[str, Any]
    if not snapshot_path or not os.path.exists(snapshot_path):
        errors.append("the manifest's snapshot %r cannot be read" % snap_rel)
    else:
        snap = dict((c["id"], c) for c in C.load_json(snapshot_path).get("items", []))

    ids = settings.CAMPAIGNS or {}
    key_of = {}  # type: Dict[str, str]
    by_campaign = OrderedDict()  # type: Dict[str, List[Dict[str, Any]]]
    for tag, b in blocks.items():
        parsed_tag = C.parse_tag(tag)
        if parsed_tag is None or parsed_tag[1] != b.get("step") or parsed_tag[2] != b.get("field"):
            errors.append("manifest block %s: tag does not match its step/field" % tag)
            continue
        key = parsed_tag[0]
        canonical = (ids.get(key) or {}).get("id")
        if canonical != b.get("campaign_id"):
            errors.append("%s: manifest campaign id %s, config/ids.json says %s for %s"
                          % (tag, b.get("campaign_id"), canonical, key))
            continue
        key_of[tag] = key
        by_campaign.setdefault(key, []).append(b)

    baselines = {}  # type: Dict[str, List[Dict[str, Any]]]
    for key, cblocks in by_campaign.items():
        camp = snap.get(cblocks[0]["campaign_id"])
        if camp is None:
            if snap:
                errors.append("campaign %s (%s) is not in the snapshot" % (key, cblocks[0]["campaign_id"]))
            continue
        try:
            baselines[key] = C.manifest_baseline(cblocks, camp)
        except C.BuildError as exc:
            errors.append("%s: %s" % (key, exc))
            continue
        for d in C.drift(camp.get("sequences"), baselines[key], []):
            errors.append("%s: the manifest disagrees with its snapshot (%s); rebuild the manifest" % (key, d))

    # Edits as the doc holds them, plus the ones a shared sentence carries.
    edited = OrderedDict((c["tag"], c["new"]) for c in report["changed"] if c["tag"] in blocks)
    cosmetic = [t for t, b in blocks.items() if t in parsed and t not in edited
                and C.doc_text(b["field"], parsed[t]) != b["text"]]
    propagated = {}  # type: Dict[str, str]
    groups = OrderedDict()  # type: Dict[Any, List[str]]
    for tag, b in blocks.items():
        if b.get("text_group") and b["text"].strip():   # a blank is not a shared sentence
            groups.setdefault((b["text_group"], b["field"]), []).append(tag)
    for (_g, _f), members in groups.items():
        if len(members) < 2:
            continue
        hit = [t for t in members if t in edited]
        if not hit:
            continue
        news = OrderedDict((C.diff_doc.norm(edited[t]), t) for t in hit)
        if len(news) > 1:
            errors.append("the shared sentence in %s was edited to different texts (%s); make them the same, "
                          "or edit only one copy" % (", ".join(members), " / ".join(repr(edited[t]) for t in hit)))
            continue
        for t in members:
            if t not in edited:
                edited[t] = edited[hit[0]]
                propagated[t] = hit[0]
    edited = OrderedDict((t, edited[t]) for t in blocks if t in edited)   # manifest order

    structure = C.structure_lines(manifest)
    changes = []  # type: List[Dict[str, Any]]
    for tag, new in edited.items():
        b = blocks[tag]
        key = key_of.get(tag)
        if key is None:
            continue
        camp = snap.get(b["campaign_id"]) or {}
        known = L.campaign_variables(camp) if camp else None
        offer = (ids.get(key) or {}).get("offer")
        errs, warns = C.check_copy(b["field"], b["text"], new, known, key, offer, offers_md, structure)
        errors.extend("%s: %s" % (tag, e) for e in errs)
        warnings.extend("%s: %s" % (tag, w) for w in warns)
        for flag in C.diff_doc.flags(b["text"], new):
            if flag in ("curly_quotes", "non_breaking_space", "ellipsis_character"):
                warnings.append("%s: %s typed in the new text (sent as typed)" % (tag, flag.replace("_", " ")))
        old_value = b.get("raw_html") if b["field"] == "body" else b.get("raw_subject")
        changes.append(OrderedDict([
            ("tag", tag), ("campaign_key", key), ("campaign_id", b["campaign_id"]),
            ("campaign_name", b.get("campaign_name")), ("step", b["step"]),
            ("variant_index", b.get("variant_index", 0)), ("field", b["field"]),
            ("old", b["text"]), ("new", new), ("new_text", C.doc_text(b["field"], new)),
            ("propagated_from", propagated.get(tag)),
            ("format_notes", C.format_notes(old_value, b["text"]) if b["field"] == "body" else []),
            ("old_value", old_value), ("value", C.doc_value(b["field"], new)),
        ]))

    campaigns = OrderedDict()  # type: Dict[str, Dict[str, Any]]
    if not errors:
        for ch in changes:
            key = ch["campaign_key"]
            if key not in campaigns:
                camp = snap[ch["campaign_id"]]
                campaigns[key] = {"campaign_id": ch["campaign_id"], "campaign_name": camp.get("name"),
                                  "snapshot": camp["sequences"], "doc_baseline": baselines[key], "changes": []}
            campaigns[key]["changes"].append(ch)
        for key, c in campaigns.items():
            c["sequences"] = C.apply_changes(c["snapshot"], c["changes"])
    return {"errors": errors, "warnings": warnings, "changes": changes, "campaigns": campaigns,
            "ignored": len([c for c in report["changed"] if not c["tag"].startswith(C.TAG_PREFIX)]),
            "cosmetic": cosmetic, "snapshot_rel": snap_rel, "snapshot_path": snapshot_path}


def render(p: Dict[str, Any], export_rec: str, manifest_rec: str, built_at: str) -> "OrderedDict[str, Any]":
    """{file name: content} for a staged folder. The recorded paths are passed
    in verbatim so the apply side renders byte-identical files."""
    files = OrderedDict()  # type: OrderedDict
    files["staged.json"] = OrderedDict([
        ("tool", C.TOOL),
        ("_about", "Staged by changesets/instantly_copy/build_from_doc.py. Apply with "
                   "apply_instantly_copy.py --staged <this folder> (dry-run by default). The apply "
                   "rebuilds this folder from the export and manifest below and refuses any difference."),
        ("doc_id", C.DOC_ID),
        ("export", export_rec),
        ("export_sha256", C.sha256_file(C.resolve(export_rec))),
        ("manifest", manifest_rec),
        ("manifest_sha256", C.sha256_file(C.resolve(manifest_rec))),
        ("snapshot", p["snapshot_rel"]),
        ("snapshot_sha256", C.sha256_file(p["snapshot_path"])),
        ("built_at", built_at),
        ("campaigns", OrderedDict((k, "%s.json" % k) for k in p["campaigns"])),
        ("changes", p["changes"]),
    ])
    for key, c in p["campaigns"].items():
        files["%s.json" % key] = OrderedDict([
            ("campaign_key", key), ("campaign_id", c["campaign_id"]), ("campaign_name", c["campaign_name"]),
            ("changes", [OrderedDict((k, ch[k]) for k in ("tag", "step", "variant_index", "field", "old_value", "value"))
                         for ch in c["changes"]]),
            ("doc_baseline", c["doc_baseline"]),
            ("baseline_sequences", c["snapshot"]),
            ("sequences", c["sequences"]),
        ])
    return files


def prepare_out_dir(out_dir: str, overwrite: bool) -> Optional[str]:
    """None when out_dir may be written, else why not. Deletes only the files
    a previous build of THIS tool listed, and only with overwrite."""
    if not C.out_dir_allowed(out_dir):
        return ("%s is outside changesets/instantly_copy/staged/ (and the system temp dir); a staged folder "
                "goes there only" % out_dir)
    if os.path.exists(out_dir) and not os.path.isdir(out_dir):
        return "%s is a file" % out_dir
    if not os.path.isdir(out_dir) or not os.listdir(out_dir):
        return None
    meta_path = os.path.join(out_dir, "staged.json")
    try:
        meta = C.load_json(meta_path)
    except (OSError, ValueError):
        meta = None
    if not isinstance(meta, dict) or meta.get("tool") != C.TOOL:
        return ("%s is not empty and holds no staged.json written by %s; it is not replaced. Use another "
                "--out folder." % (out_dir, C.TOOL))
    if not overwrite:
        return ("%s already holds a staged change-set; pass --overwrite to replace it, or --out another "
                "folder" % out_dir)
    names = list((meta.get("campaigns") or {}).values())
    bad = [n for n in names if not isinstance(n, str) or not C.CAMPAIGN_FILE_RE.match(n) or n == "staged.json"]
    if bad:
        return "%s/staged.json lists unexpected files %s; not replacing it" % (out_dir, bad)
    for name in names + ["staged.json"]:
        path = os.path.join(out_dir, name)
        if os.path.isfile(path):
            os.remove(path)
    return None


def build(export_path: str, manifest_path: str = C.DEFAULT_MANIFEST, out_dir: Optional[str] = None,
          now: Optional[datetime] = None, out: Callable[[str], None] = print,
          overwrite: bool = False) -> int:
    # Staging is offline and writes no live state: its Job_Log rows go to a
    # scratch log, like every dry-run, never the production .tmp/job_log.csv.
    with R.scratch_logs("instantly_copy_build"):
        return _build(export_path, manifest_path, out_dir, now, out, overwrite)


def _build(export_path: str, manifest_path: str, out_dir: Optional[str], now: Optional[datetime],
           out: Callable[[str], None], overwrite: bool) -> int:
    now = now or _utcnow()
    out_dir = out_dir or os.path.join(C.STAGED_ROOT, os.path.splitext(os.path.basename(export_path))[0])
    try:
        p = plan(export_path, manifest_path)
    except (OSError, ValueError, KeyError) as exc:
        out("REFUSED: could not read the export or the manifest: %s. Nothing was written." % exc)
        job_log.log_run("instantly_copy.build", "refused", {"export": export_path, "error": str(exc)[:200]})
        return EXIT_INVALID

    out("export:   %s" % C.rel(export_path))
    out("manifest: %s" % C.rel(manifest_path))
    if p["ignored"]:
        out("%d changed block(s) outside Instantly ignored here (the doc router handles those)." % p["ignored"])
    if p["cosmetic"]:
        out("whitespace/quote-only edits, not staged (Instantly keeps the old text): %s" % ", ".join(p["cosmetic"]))
    for w in p["warnings"]:
        out("warn  %s" % w)
    if p["errors"]:
        out("REFUSED: %d problem(s); nothing was staged or written:" % len(p["errors"]))
        for e in p["errors"]:
            out("  ERROR %s" % e)
        job_log.log_run("instantly_copy.build", "refused", {"export": C.rel(export_path), "errors": p["errors"]})
        return EXIT_INVALID
    if not p["changes"]:
        out("No Instantly changes in this export; nothing staged, nothing written.")
        job_log.log_run("instantly_copy.build", "noop", {"export": C.rel(export_path), "cosmetic": p["cosmetic"]})
        return EXIT_OK

    why = prepare_out_dir(out_dir, overwrite)
    if why:
        out("REFUSED: %s. Nothing was written." % why)
        return EXIT_INVALID
    files = render(p, C.rel(export_path), C.rel(manifest_path),
                   now.astimezone(timezone.utc).replace(microsecond=0).isoformat())
    for name, data in files.items():
        if name != "staged.json":
            C.write_json(os.path.join(out_dir, name), data)
    C.write_json(os.path.join(out_dir, "staged.json"), files["staged.json"])   # last: marks the folder complete

    for key, c in p["campaigns"].items():
        out("staged %-26s %d change(s):" % (key, len(c["changes"])))
        for ch in c["changes"]:
            out("  %s%s" % (ch["tag"], " (same shared sentence as %s)" % ch["propagated_from"]
                            if ch["propagated_from"] else ""))
            for n in ch["format_notes"]:
                out("    %s" % n)
    out("written: %s" % C.rel(out_dir))
    out("keep the export file: the apply verifies the staged folder against it (sha256).")
    out("next: python3 changesets/instantly_copy/apply_instantly_copy.py --staged %s" % C.rel(out_dir))
    job_log.log_run("instantly_copy.build", "staged", {
        "export": C.rel(export_path), "export_sha256": files["staged.json"]["export_sha256"],
        "out": C.rel(out_dir), "campaigns": list(p["campaigns"]), "changes": [ch["tag"] for ch in p["changes"]]})
    return EXIT_OK


def main(argv: Optional[List[str]] = None, now: Optional[datetime] = None,
         out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="Drive text/plain export of the doc")
    ap.add_argument("--manifest", default=C.DEFAULT_MANIFEST)
    ap.add_argument("--out", help="output folder (default changesets/instantly_copy/staged/<export stem>/)")
    ap.add_argument("--overwrite", action="store_true", help="replace a staged folder this tool wrote")
    args = ap.parse_args(argv)
    return build(args.export, args.manifest, args.out, now=now, out=out, overwrite=args.overwrite)


if __name__ == "__main__":
    sys.exit(main())
