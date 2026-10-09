"""Record Lorenzo's template approvals from the one Google Doc after he says "done".

Lorenzo's rule (2026-09-23): when he types "done" in chat about the doc,
everything in the doc counts as approved. This tool turns that into approvals
in config/approved_templates.json, the same registry and record format as the
terminal path (jobs/approve_templates.py), which stays as it is.

The principle: an id is approved only if Lorenzo could see every part of its
hashed review text in the doc he said "done" on, he changed and commented on
none of it (anywhere in the doc, not only in block bodies), and the code
still renders exactly that.

How:
* The export names its build: the "(tag: X-BUILD)" line carries the build
  fingerprint, and builds/<fingerprint>/manifest.json is that build (its
  fingerprint is recomputed and must match). build.py shows every part of
  every template's hashed text in the doc: the main text, the subject line
  and its fallbacks, the time formats (tagged formats.N blocks), and every
  version as grey notes quoting the main-text lines it replaces or leaves out
  followed by the lines it puts in (the dated and other-timezone versions
  that write out example times are shown in full). A build is only written when
  doc_areas.DocReader reads every part back out of the doc's own text
  exactly, so the doc a build came from determines each id's hashed text.
* The export is diffed against that build: block bodies (diff_doc) and every
  other line (doc_areas: top section, headings, labels, notes with their
  place in their block, section lines, text typed between them).
* Per id, the build must match a fresh build of the current code: same hash,
  same blocks, labels and notes. The catalogue hash is checked again just
  before writing.

Refused, per id: an edited, deleted or added block of it (or of its time
formats block); a changed, moved or deleted heading, label or note of it
(the quoted lines of its versions included); a changed line in its section
outside any email; a block that carries a sentence an edit changed or removed
anywhere else (the doc says "changing it once is enough; it changes
everywhere"): exactly the blocks route_doc.py lists as "also appears in" for
that edit (the same text, or the same sentence found by route_doc's own
sentence matching, which leaves out greetings, sign-offs and sentences in more
than half of all blocks), mapped to their template ids; a cadence day and the
lines spliced into it together; the first replies the doc says start as
approval cards (doc_rules.HELD_QT); code changed since the build.
Refused, whole doc (for --write): duplicate tags, copies of one sentence
changed differently, a change in the top section or outside the engine
sections, a tag that matches no email, no build fingerprint (a doc from before
fingerprints), a --doc-id that uploads.json does not map to the fingerprint.

Default is a dry run: it prints the plan and writes nothing (exit 1 when
--write would be refused as a whole). --write needs --doc-id, --done-quote
(Lorenzo's exact words, containing "done") and --checked-comments (the
operator read the doc's open comments and suggestions and none is open;
suggestions are not in a text export), writes through the registry's own
plan_approve (fresh hashes as ``expected``) and apply_approve, only adds or
refreshes approvals, never revokes, never touches auto_send, logs one Job_Log
row (JOB_LOG_PATH, with checked_comments) and prints the git diff command to
run for Lorenzo.

Instantly blocks are not approvals: changed ones go through
changesets/instantly_copy/.

    python3 tools/template_doc/record_doc_approvals.py EXPORT.txt
    python3 tools/template_doc/record_doc_approvals.py EXPORT.txt --write --doc-id DOC_ID --done-quote "done" --checked-comments

Exit 0: plan printed or approvals written. Exit 1: refused (nothing written).
Exit 2: the export cannot be read.
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, CODE_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import diff_doc  # noqa: E402
import doc_areas  # noqa: E402
import route_doc  # noqa: E402
from doc_rules import is_held, section_of, splice_pairs  # noqa: E402
from fresh_manifest import FreshBuildError, build_fresh  # noqa: E402
from parse_doc import parse_with_info  # noqa: E402

from services.reply_engine import template_approvals as ta  # noqa: E402
from shared.job_log import log_run  # noqa: E402

JOB = "approve_templates"  # the same Job_Log job as the terminal path
ACTION = "approve_from_doc"
DEFAULT_BY = "Lorenzo (Google Doc)"
BUILDS_DIR = os.path.join(HERE, "builds")
UPLOADS_PATH = os.path.join(HERE, "uploads.json")
LEGACY_MANIFEST = os.path.join(HERE, "manifest.json")
LEGACY_HTML = os.path.join(HERE, "advero_all_emails.html")
INSTANTLY_CHANGESET = "changesets/instantly_copy/"
GIT_DIFF_CMD = "git diff -- config/approved_templates.json"
DONE_RE = re.compile(r"\bdone\b", re.IGNORECASE)
QUOTE_MAX = 80

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNREADABLE = 2

R_HELD = "held: the doc says these start as approval cards"
R_EDITED = "edited in the doc (%s): the owning section changes the code first, then the doc is rebuilt"
R_DELETED = "deleted in the doc (%s): the code still sends it; the owning section changes the code first"
R_ADDED = "new block tagged for this email in the doc (%s): the code does not send it"
R_REPEAT = ("it carries words that were edited in %s, and the doc says changing it once changes it everywhere: "
            "the owning section changes the code first")
R_AREA = "a heading, label or note of it changed, moved or was deleted in the doc (%s)"
R_SECTION = "a line outside any email changed in its section (%s) of the doc"
R_SPLICE_HOST = "its line is spliced into %s, which is refused"
R_SPLICE_FRAG = "%s is spliced into it and is refused"
R_NOT_IN_DOC = "not in this doc's build"
R_DOC_STALE = "code changed since this doc was built (doc %s, code %s): rebuild and re-upload the doc"
R_RENDER = ("the doc shows it differently from a build of the current code (%s): rebuild and re-upload "
            "the doc")
R_FRESH_MISMATCH = "the fresh build shows more than one hash for it"
R_RACE = "the code changed after the fresh build (build %s, now %s): run again"
R_GONE = "no longer an approvable template in the catalogue"

W_NO_TAGS = "the export has no tagged blocks: is it the right doc?"
W_LEGACY = "this doc predates build fingerprints; rebuild and re-upload"

KEEPS_SENDING = "keeps sending its previously approved text"
OLD_APPROVAL = "its earlier approval is for older text, so it stays a card or is held"


class Refused(Exception):
    """Nothing may be written."""


def _short(h: Optional[str]) -> str:
    return (h or "")[:12]


def _hashes_by_id(manifest: Dict[str, Any]) -> Dict[str, set]:
    out = {}  # type: Dict[str, set]
    for b in manifest.get("blocks", []):
        tid = b.get("template_id")
        if tid:
            out.setdefault(tid, set()).add(b.get("sha256"))
    return out


def _owners(blocks: Dict[str, Dict[str, Any]], tag: str) -> List[str]:
    """The template ids a block belongs to (a formats block: its dependents)."""
    b = blocks.get(tag)
    if not b:
        return []
    if b.get("template_id"):
        return [b["template_id"]]
    return list(b.get("dependents") or [])


def _tags_of(manifest: Dict[str, Any], tid: str) -> List[str]:
    tags = []  # type: List[str]
    for b in manifest.get("blocks", []):
        if b.get("template_id") == tid:
            tags.append(b["tag"])
            tags.extend(b.get("depends_on") or [])
    return sorted(set(tags))


def _sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ------------------------------------------------------------ doc builds
def load_doc_build(fp: Optional[str]) -> Dict[str, Any]:
    """The build a doc export came from. fp None: the legacy top-level build
    (no fingerprint; read-only). Raises Refused when it cannot be trusted."""
    if fp is None:
        try:
            with io.open(LEGACY_MANIFEST, encoding="utf-8") as fh:
                manifest = json.load(fh)
            visible = doc_areas.area_pairs(doc_areas.html_to_text(LEGACY_HTML))
        except (OSError, ValueError) as exc:
            raise Refused("cannot read the legacy doc build: %s" % exc)
        return {"manifest": manifest, "visible": visible, "fingerprint": None, "legacy": True,
                "manifest_path": LEGACY_MANIFEST, "manifest_sha256": _sha_file(LEGACY_MANIFEST)}
    path = os.path.join(BUILDS_DIR, fp, "manifest.json")
    try:
        with io.open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Refused("no readable build for fingerprint %s (%s): was this doc built here?" % (fp, exc))
    visible = manifest.get("visible") or []
    if manifest.get("fingerprint") != fp or doc_areas.fingerprint(manifest.get("blocks", []), visible) != fp:
        raise Refused("builds/%s/manifest.json does not hash to its fingerprint" % fp)
    return {"manifest": manifest, "visible": visible, "fingerprint": fp, "legacy": False,
            "manifest_path": path, "manifest_sha256": _sha_file(path)}


def uploaded_fingerprint(doc_id: str) -> Any:
    """The fingerprint uploads.json records for a doc id ('missing' if none)."""
    try:
        with io.open(UPLOADS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Refused("cannot read %s: %s" % (UPLOADS_PATH, exc))
    found = "missing"
    for u in data.get("uploads", []):
        if u.get("doc_id") == doc_id:
            found = u.get("fingerprint")
    return found


# ------------------------------------------------------------------ plan
def evaluate(export_text: str, doc: Dict[str, Any], fresh: Dict[str, Any], approvals: Dict[str, Any],
             entries_now: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The plan for one doc export against the build it came from. Writes
    nothing. plan["whole"] lists what refuses the whole doc for --write."""
    dm, fm = doc["manifest"], fresh["manifest"]
    info = parse_with_info(export_text)
    report = diff_doc.diff(info, dm)
    whole = []  # type: List[str]
    refusals = OrderedDict()  # type: Dict[str, List[str]]
    ids = sorted(fresh["hashes"])

    def refuse(tid: str, reason: str) -> None:
        rs = refusals.setdefault(tid, [])
        if reason not in rs:
            rs.append(reason)

    def whole_doc(reason: str) -> None:
        if reason not in whole:
            whole.append(reason)

    dblocks = OrderedDict((b["tag"], b) for b in dm.get("blocks", []))
    fblocks = OrderedDict((b["tag"], b) for b in fm.get("blocks", []))
    if not info["blocks"]:
        whole_doc(W_NO_TAGS)
    if report["duplicates"]:
        whole_doc("duplicate tags in the doc: %s" % ", ".join(sorted(set(report["duplicates"]))))
    if report["conflicting_text_groups"]:
        groups = OrderedDict()  # type: Dict[str, List[str]]
        for c in report["changed"]:
            if c["text_group"] in report["conflicting_text_groups"]:
                groups.setdefault(c["text_group"], []).append(c["tag"])
        whole_doc("copies of one sentence were changed differently: %s"
                  % "; ".join(", ".join(tags) for tags in groups.values()))

    # 1. the first replies the doc says start as approval cards
    held = set(b.get("template_id") for m in (dm, fm) for b in m.get("blocks", []) if b.get("held"))
    for tid in ids:
        if is_held(tid) or tid in held:
            refuse(tid, R_HELD)

    # 2. edited, deleted and added blocks, and the repeat rule
    changed = OrderedDict((c["tag"], c) for c in report["changed"])
    missing = list(report["missing"])
    passive = ("instantly.", "U-PRICE-")  # edits there are not approvals and refuse nothing
    for tag in list(changed) + missing:
        owners = _owners(dblocks, tag)
        for tid in owners:
            refuse(tid, (R_EDITED if tag in changed else R_DELETED) % tag)
        if not owners and not tag.startswith(passive):
            whole_doc("%s was %s in the doc" % (tag, "changed" if tag in changed else "deleted"))
    # The repeat rule: every block route_doc lists as "also appears in" for
    # an edit (same text group, or a sentence the edit changed or removed,
    # by route_doc's own sentence matching) refuses its template ids.
    dm_blocks = dm.get("blocks", [])
    normed = dict((b["tag"], diff_doc.norm(b.get("text") or "")) for b in dm_blocks)
    edited = set(changed) | set(missing)
    sentence_cache = {}  # type: Dict[str, Any]
    for tag in list(changed) + missing:
        old = dblocks[tag].get("text") or ""
        new = changed[tag]["new"] if tag in changed else None
        also = route_doc._also_in(tag, old, new, dm_blocks, normed, edited, sentence_cache)
        for carriers in also.values():
            for t in carriers:
                for tid in _owners(dblocks, t):
                    refuse(tid, R_REPEAT % tag)
    for t in report["unknown"]:
        hit = [tid for tid in ids if t.startswith(tid + "/") or t.startswith(tid + ".")]
        for tid in hit:
            refuse(tid, R_ADDED % t)
        if not hit:
            whole_doc("a tag in the doc matches no email: %s" % t)

    # 3. every line outside block bodies
    exp_areas = doc_areas.areas(doc_areas.area_pairs(export_text))
    ref_areas = doc_areas.areas(doc["visible"])
    skip = set(missing) | set(report["unknown"])
    area_changes = []  # type: List[str]
    for key in list(ref_areas) + [k for k in exp_areas if k not in ref_areas]:
        if exp_areas.get(key) == ref_areas.get(key):
            continue
        area_changes.append(key)
        if key == "top":
            whole_doc("the doc's top section changed")
        elif key.startswith("gap:"):
            sec = section_of(key[4:])
            if sec:
                for tid in ids:
                    if section_of(tid) == sec:
                        refuse(tid, R_SECTION % sec)
            else:
                whole_doc("a line outside the emails changed before %s" % key[4:])
        elif key not in skip:
            owners = _owners(dblocks, key)
            for tid in owners:
                refuse(tid, R_AREA % key)
            if not owners:
                whole_doc("a heading, label or note outside the engine emails changed (%s)" % key)

    # 4. the doc's build against the code now
    entries_now = entries_now if entries_now is not None else ta.catalogue_index()
    d_by, f_by = _hashes_by_id(dm), _hashes_by_id(fm)
    fresh_areas = doc_areas.areas(fm.get("visible") or [])
    for tid in ids:
        h = fresh["hashes"][tid]
        if not d_by.get(tid):
            refuse(tid, R_NOT_IN_DOC)
        elif d_by[tid] != {h}:
            refuse(tid, R_DOC_STALE % (",".join(sorted(_short(x) for x in d_by[tid] if x)), _short(h)))
        else:
            dt, ft = _tags_of(dm, tid), _tags_of(fm, tid)
            diffs = sorted(set(dt) ^ set(ft))
            for t in ft:
                if t in dblocks and (diff_doc.norm(dblocks[t].get("text") or "") != diff_doc.norm(
                        fblocks[t].get("text") or "") or ref_areas.get(t) != fresh_areas.get(t)):
                    diffs.append(t)
            if diffs:
                refuse(tid, R_RENDER % ", ".join(sorted(set(diffs))))
        if f_by.get(tid) != {h}:
            refuse(tid, R_FRESH_MISMATCH)
        entry = entries_now.get(tid)
        if entry is None or not entry.get("approvable") or not entry.get("extractable"):
            refuse(tid, R_GONE)
        elif entry.get("sha256") != h:
            refuse(tid, R_RACE % (_short(h), _short(entry.get("sha256"))))

    # 5. a cadence day and the lines spliced into it stand or fall together
    pairs = set(splice_pairs())
    for m in (dm, fm):
        for b in m.get("blocks", []):
            if b.get("spliced_into") and b.get("template_id"):
                pairs.add((b["spliced_into"], b["template_id"]))
    grew = True
    while grew:
        grew = False
        for host, frag in sorted(pairs):
            if host in refusals and frag not in refusals and frag in fresh["hashes"]:
                refuse(frag, R_SPLICE_HOST % host)
                grew = True
            if frag in refusals and host not in refusals and host in fresh["hashes"]:
                refuse(host, R_SPLICE_FRAG % frag)
                grew = True

    approve, already, refused = [], [], []
    for tid in ids:
        before = ta.status(tid, entries=entries_now, approvals=approvals)
        if tid in refusals:
            item = OrderedDict([("id", tid), ("reasons", refusals[tid]), ("before", before)])
            if before == ta.STATUS_APPROVED:
                item["note"] = KEEPS_SENDING
            elif before == ta.STATUS_CHANGED:
                item["note"] = OLD_APPROVAL
            refused.append(item)
            continue
        item = OrderedDict([("id", tid), ("sha256", fresh["hashes"][tid]), ("before", before)])
        (already if before == ta.STATUS_APPROVED else approve).append(item)

    inst = [t for t in dblocks if t.startswith("instantly.")]
    other = [t for t in dblocks if t.startswith("U-PRICE-")]
    return OrderedDict([
        ("fingerprint", doc.get("fingerprint")), ("legacy", doc.get("legacy")),
        ("fresh_fingerprint", fresh.get("fingerprint")),
        ("whole", whole), ("approve", approve), ("already", already), ("refused", refused),
        ("unknown_tags", list(report["unknown"])), ("area_changes", area_changes),
        ("cosmetic_only", len(report["cosmetic_only"])),
        ("instantly", OrderedDict([
            ("unchanged", sum(1 for t in inst if t not in changed and t not in missing)),
            ("changed", [t for t in inst if t in changed]),
            ("deleted", [t for t in inst if t in missing]),
        ])),
        ("other_changed", [t for t in other if t in changed or t in missing]),
        ("counts", report["counts"]),
    ])


def print_plan(plan: Dict[str, Any]) -> None:
    c = plan["counts"]
    print("doc build: %s" % (plan["fingerprint"] or "none (a doc from before build fingerprints)"))
    print("fresh build of the current code: %s" % plan["fresh_fingerprint"])
    print("doc blocks: %d found, %d in the doc's build; %d changed, %d deleted, %d new tags, %d cosmetic only; "
          "%d areas outside block bodies changed"
          % (c["parsed_blocks"], c["manifest_blocks"], c["changed"], c["missing"], c["unknown"],
             plan["cosmetic_only"], len(plan["area_changes"])))
    print("")
    print("will approve (%d):" % len(plan["approve"]))
    for p in plan["approve"]:
        print("  %s  sha256 %s  (was %s)" % (p["id"], p["sha256"], p["before"]))
    print("already approved at that hash, unchanged (%d):" % len(plan["already"]))
    for p in plan["already"]:
        print("  %s  sha256 %s" % (p["id"], p["sha256"]))
    print("refused, not approved (%d):" % len(plan["refused"]))
    for r in plan["refused"]:
        print("  %s%s" % (r["id"], ("  (%s)" % r["note"]) if r.get("note") else ""))
        for reason in r["reasons"]:
            print("      - %s" % reason)
    if plan["unknown_tags"]:
        print("new tags in the doc, not approved (%d): %s" % (len(plan["unknown_tags"]), ", ".join(plan["unknown_tags"])))
    inst = plan["instantly"]
    print("")
    print("Instantly blocks (not approvals): %d unchanged, %d changed, %d deleted"
          % (inst["unchanged"], len(inst["changed"]), len(inst["deleted"])))
    for t in inst["changed"] + inst["deleted"]:
        print("  %s" % t)
    if inst["changed"] or inst["deleted"]:
        print("  changed Instantly copy goes through %s (dry-run first, Lorenzo approves the push)" % INSTANTLY_CHANGESET)
    if plan["other_changed"]:
        print("other changed blocks (not approvals; see route_doc.py): %s" % ", ".join(plan["other_changed"]))
    if plan["whole"]:
        print("")
        print("--write refuses the whole doc:")
        for w in plan["whole"]:
            print("  - %s" % w)


# ----------------------------------------------------------------- write
def _read_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def write_approvals(plan: Dict[str, Any], fresh_hashes: Dict[str, str], approvals_path: Optional[str],
                    approved_by: str, before_bytes: Optional[bytes]) -> Dict[str, Any]:
    """Write the plan's approvals through the registry's own functions.
    Returns {"written": [...], "unchanged": [...], "race": {id: reason}}.
    Raises Refused (nothing written) on any doubt."""
    path = approvals_path
    approvals = ta.load_approvals(path)
    entries_now = ta.catalogue_index()
    ids, race = [], OrderedDict()
    for p in plan["approve"] + plan["already"]:
        tid = p["id"]
        now_h = (entries_now.get(tid) or {}).get("sha256")
        if now_h != fresh_hashes.get(tid) or p["sha256"] != fresh_hashes.get(tid):
            race[tid] = R_RACE % (_short(fresh_hashes.get(tid)), _short(now_h))
            continue
        ids.append(tid)
    expected = dict((tid, fresh_hashes[tid]) for tid in ids)
    try:
        todo_plan = ta.plan_approve(ids, entries_now, approvals, expected=expected)
    except ta.ApprovalError as exc:
        raise Refused("the approval registry refused the plan: %s" % exc)
    todo = [p for p in todo_plan if p["before"] != ta.STATUS_APPROVED]
    unchanged = [p["id"] for p in todo_plan if p["before"] == ta.STATUS_APPROVED]
    if not todo:
        return {"written": [], "unchanged": unchanged, "race": race}
    new = ta.apply_approve(todo_plan, approvals, approved_by)

    # Defence in depth: only the planned ids change, each to its fresh hash;
    # every other approval and every top-level key (auto_send) is as it was.
    todo_ids = set(p["id"] for p in todo)
    for key in set(approvals) | set(new):
        if key != "approvals" and approvals.get(key) != new.get(key):
            raise Refused("internal check: top-level key %r would change" % key)
    old_recs, new_recs = approvals.get("approvals") or {}, new.get("approvals") or {}
    for tid in set(old_recs) | set(new_recs):
        if tid in todo_ids:
            if (new_recs.get(tid) or {}).get("sha256") != fresh_hashes[tid]:
                raise Refused("internal check: %s would not be recorded at its fresh hash" % tid)
        elif old_recs.get(tid) != new_recs.get(tid):
            raise Refused("internal check: the approval of %s would change" % tid)

    if _read_bytes(str(ta._path(path))) != before_bytes:
        raise Refused("the approvals file changed while this ran; run again")
    ta.save_approvals(new, path)
    reread = ta.load_approvals(path)
    bad = [tid for tid in todo_ids
           if ta.status(tid, entries=entries_now, approvals=reread) != ta.STATUS_APPROVED]
    if bad:
        raise RuntimeError("written, but these do not read back as approved: %s" % ", ".join(sorted(bad)))
    return {"written": [p["id"] for p in todo], "unchanged": unchanged, "race": race}


def _head() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "-C", CODE_ROOT, "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return None


def _approved_by(by: str, quote: str, fp: str) -> str:
    q = " ".join(quote.split())
    if len(q) > QUOTE_MAX:
        q = q[:QUOTE_MAX - 3].rstrip() + "..."
    return '%s: "%s", build %s' % (by.strip(), q, _short(fp))


def main(argv: Optional[List[str]] = None, log_fn: Callable[..., Any] = log_run,
         build: Callable[[str], Dict[str, Any]] = build_fresh) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    ap.add_argument("export", help="plain-text export of the Google Doc")
    ap.add_argument("--write", action="store_true", help="write the approvals (default: dry run)")
    ap.add_argument("--doc-id", default=None, help="the Google Doc's id (required with --write; checked in uploads.json)")
    ap.add_argument("--done-quote", default=None, help="Lorenzo's exact words, containing 'done' (required with --write)")
    ap.add_argument("--checked-comments", action="store_true",
                    help="required with --write: you read the doc's open comments and suggestions (Drive "
                         "read_file_content with includeComments) and none is open")
    ap.add_argument("--approvals-file", default=None, help="approvals registry (default config/approved_templates.json)")
    ap.add_argument("--by", default=DEFAULT_BY, help="who approved (default: %s); the quote and build are added" % DEFAULT_BY)
    args = ap.parse_args(argv)
    quote = (args.done_quote or "").strip()
    if args.write:
        problems = []
        if not quote:
            problems.append("--write needs --done-quote with Lorenzo's exact words")
        elif not DONE_RE.search(quote):
            problems.append("--done-quote must contain the word 'done' (Lorenzo's words when he said it)")
        if not (args.doc_id or "").strip():
            problems.append("--write needs --doc-id (the Google Doc he said 'done' on)")
        if not args.checked_comments:
            problems.append("--write needs --checked-comments: read the doc's open comments and suggestions first "
                            "(they are not in the text export); if any is open, stop and ask Lorenzo")
        if not (args.by or "").strip():
            problems.append("--by must not be empty")
        if problems:
            for p in problems:
                print("REFUSED: %s." % p)
            print("Nothing was written.")
            return EXIT_REFUSED

    raw = _read_bytes(args.export)
    if raw is None:
        print("cannot read %s" % args.export)
        return EXIT_UNREADABLE
    try:
        export_text = raw.decode("utf-8-sig")
    except ValueError as exc:
        print("cannot read %s: %s" % (args.export, exc))
        return EXIT_UNREADABLE
    export_sha = hashlib.sha256(raw).hexdigest()
    path = args.approvals_file or None
    base = OrderedDict([("action", ACTION), ("doc_id", args.doc_id), ("export_file", os.path.basename(args.export)),
                        ("export_sha256", export_sha), ("done_quote", quote),
                        ("checked_comments", bool(args.checked_comments)),
                        ("approvals_path", str(ta._path(path))), ("head", _head())])

    def refuse(msg: str, **extra: Any) -> int:
        print("REFUSED: %s" % msg)
        print("Nothing was written.")
        if args.write:
            log_fn(JOB, "refused", dict(base, reason=msg, **extra))
        return EXIT_REFUSED

    print("doc export: %s (sha256 %s)" % (args.export, export_sha))
    if args.doc_id:
        print("Google Doc: %s" % args.doc_id)
    fp, fp_problem = doc_areas.read_fingerprint(export_text)
    if fp_problem:
        return refuse("the doc's build line is damaged: %s" % fp_problem)
    base["fingerprint"] = fp
    try:
        doc = load_doc_build(fp)
    except Refused as exc:
        return refuse(str(exc))
    base["doc_manifest"] = os.path.relpath(doc["manifest_path"], CODE_ROOT)
    base["doc_manifest_sha256"] = doc["manifest_sha256"]
    upfront = []  # type: List[str]
    if fp is None:
        upfront.append(W_LEGACY)
    if args.doc_id:
        try:
            recorded = uploaded_fingerprint(args.doc_id)
        except Refused as exc:
            return refuse(str(exc))
        if recorded == "missing":
            upfront.append("uploads.json has no doc %s" % args.doc_id)
        elif fp is not None and recorded != fp:
            upfront.append("uploads.json records build %s for doc %s, not this export's build %s"
                           % (recorded, args.doc_id, fp))
    if args.write and upfront:
        return refuse("; ".join(upfront))

    with tempfile.TemporaryDirectory(prefix="fresh_doc_") as tmp:
        try:
            fresh = build(os.path.join(tmp, "build"))
        except FreshBuildError as exc:
            return refuse("the doc could not be rebuilt from the current code: %s" % exc)
        base["fresh_export_sha256"] = fresh["export_sha256"]
        base["fresh_fingerprint"] = fresh.get("fingerprint")
        try:
            before_bytes = _read_bytes(str(ta._path(path)))
            approvals = ta.load_approvals(path)
            plan = evaluate(export_text, doc, fresh, approvals)
        except ValueError as exc:  # unreadable approvals file
            return refuse("approvals file unreadable: %s" % exc)
        plan["whole"] = upfront + plan["whole"]
        print("")
        print_plan(plan)
        refused = OrderedDict((r["id"], r["reasons"]) for r in plan["refused"])
        if not args.write:
            print("")
            print("Dry run: nothing was written.")
            if plan["whole"]:
                return EXIT_REFUSED
            print("To record: --write --doc-id <doc id> --done-quote \"<Lorenzo's words>\" --checked-comments "
                  "(after reading the doc's open comments and suggestions)")
            return EXIT_OK
        if plan["whole"]:
            return refuse("the whole doc is refused: %s" % " / ".join(plan["whole"]), refused=refused)
        approved_by = _approved_by(args.by, quote, fp)
        base["approved_by"] = approved_by
        try:
            result = write_approvals(plan, fresh["hashes"], path, approved_by, before_bytes)
        except Refused as exc:
            return refuse(str(exc), refused=refused)
        except ValueError as exc:
            return refuse("approvals file unreadable: %s" % exc)
    for tid, why in result["race"].items():
        refused[tid] = [why]
        print("refused at write time: %s: %s" % (tid, why))
    approved = OrderedDict((tid, fresh["hashes"][tid]) for tid in result["written"])
    print("")
    if approved:
        print("approved %d template(s) as %s; wrote %s" % (len(approved), approved_by, ta._path(path)))
        print(ta.WIRED_NOTE)
    else:
        print("Nothing to change: nothing was written.")
    log_fn(JOB, "ok", dict(base, approved=approved, unchanged=result["unchanged"], refused=refused))
    print("")
    print("Run this and show Lorenzo the output before committing:")
    print("    %s" % GIT_DIFF_CMD)
    if path is not None:
        print("    (this run wrote %s)" % path)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
