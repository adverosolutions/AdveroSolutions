"""Route every block Lorenzo changed in the one Google Doc to its owner.

For each changed, deleted (missing) and new (unknown) block it says which
section owns it and which file holds its text, plus what needs a look before
anything is applied: typed characters, placeholders added or lost, brace
tokens that are not real placeholders, the wrong placeholder style for the
block, and lines that are notes for Claude rather than email copy.

It only reads: the export and manifest.json. The diff itself is diff_doc.diff.

    python3 route_doc.py EXPORT.txt [--manifest manifest.json] [--json OUT.json] [--md OUT.md]

Exit 0 when a report was produced, 2 when the export (or manifest) cannot be
read or parsed.
"""
import hashlib
import io
import json
import os
import re
import sys
from collections import OrderedDict

import diff_doc
from parse_doc import parse_with_info

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW_BY_HAND = "review by hand"
INSTANTLY_CHANGESET = "changesets/instantly_copy/"

BRACE_TOKEN_RE = re.compile(r"\{\{[^{}]*\}\}|\{[^{}]*\}")
ENGINE_PLACEHOLDER_RE = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")
INSTANTLY_TAG_RE = re.compile(r"^\{\{[^{}]*\}\}$")
NOTE_MARK_RE = re.compile(r"\(\s*note\s*\)", re.IGNORECASE)
NOTE_START_RE = re.compile(r"^\s*NOTE\b", re.IGNORECASE)
ENGINE_PREFIXES = ("first_reply.", "cadence.", "booking.", "show_rate.", "no_show.")


def _source_file(block):
    src = (block or {}).get("source")
    if not src or src == "None":
        return None
    return src.split(":", 1)[0].split(" (", 1)[0].strip()


CADENCE_PY = "services/reply_engine/cadence.py"
OFFERS_MD = "config/offers.md"
PROMPTS = "services/reply_engine/prompts/"
NO_SLOTS_RE = re.compile(r"^cadence\.(d[0-9]+(?:_noinvite)?)/no_slots$")
PREREAD_RE = re.compile(r"^show_rate\.preread_email\.([a-z]+)_(reactivation|outbound)$")


def _override(tag):
    """(file, note) where the manifest source does not name the file that
    holds the text, else None. Each one was checked against the repo."""
    m = NO_SLOTS_RE.match(tag)
    if m:
        return CADENCE_PY, (
            'the text is NO_SLOTS_BODIES["%s"] in cadence.py, not the day\'s prompt file' % m.group(1))
    if tag.startswith("cadence.d4.case_study."):
        return OFFERS_MD, (
            "the line is the proof table row in config/offers.md (cadence.py:case_study_line reads it); "
            "config/offers.md is section 4's file: section 4 applies the edit on section 1's word")
    if tag == "cadence.d6/one_slot":
        return PROMPTS + "cadence_d6.md", (
            'the sentence is in cadence_d6.md with {slot2}; the words "another time" are '
            "build_touch's slot2 fallback in cadence.py")
    m = PREREAD_RE.match(tag)
    if m:
        niche, offer = m.groups()
        name = "show_rate_preread_%s.md" % niche if offer == "reactivation" else (
            "show_rate_preread_%s_outbound.md" % niche)
        return PROMPTS + name, "show_rate.py loads this body from the prompt file (preread_path)"
    return None


def route(tag, block):
    """(section, file, note) for a tag; block is its manifest entry or None."""
    if block is None:
        return 4, REVIEW_BY_HAND, "tag is not in the manifest"
    over = _override(tag)
    if tag.startswith("first_reply."):
        return 1, "services/reply_engine/draft.py", None
    if tag.startswith("cadence."):
        if over:
            return 1, over[0], over[1]
        return 1, _source_file(block) or REVIEW_BY_HAND, None
    if tag.startswith("booking.already_booked"):
        return 2, "services/reply_engine/app.py", (
            "app.py is section 4's file: section 4 applies the edit on section 2's word")
    if tag.startswith(("booking.", "show_rate.", "no_show.")):
        if over:
            return 2, over[0], over[1]
        return 2, _source_file(block) or REVIEW_BY_HAND, None
    if tag.startswith("U-PRICE-"):
        return 3, "config/upwork_offers.md", None
    if tag.startswith("instantly."):
        return 4, INSTANTLY_CHANGESET, "the Instantly copy change-set"
    return 4, REVIEW_BY_HAND, None


def placeholder_style(tag, block):
    """'instantly', 'engine' or None (no placeholder rule for this block)."""
    if tag.startswith("instantly."):
        return "instantly"
    kind = (block or {}).get("kind") or ""
    if kind.startswith("template_") or tag.startswith(ENGINE_PREFIXES):
        return "engine"
    return None


def invalid_placeholders(text):
    out = []
    for m in BRACE_TOKEN_RE.finditer(text or ""):
        tok = m.group(0)
        if ENGINE_PLACEHOLDER_RE.match(tok) or INSTANTLY_TAG_RE.match(tok):
            continue
        if tok not in out:
            out.append(tok)
    return out


def wrong_placeholder_style(text, style):
    out = []
    for m in BRACE_TOKEN_RE.finditer(text or ""):
        tok = m.group(0)
        bad = ((style == "instantly" and ENGINE_PLACEHOLDER_RE.match(tok)) or
               (style == "engine" and INSTANTLY_TAG_RE.match(tok)))
        if bad and tok not in out:
            out.append(tok)
    return out


def stray_braces(text):
    """Braces left over once every brace token is taken out: the valid
    placeholders for either style, and the tokens invalid_placeholders and
    wrong_placeholder_style already report. Each is shown as the run of
    non-space text around it, e.g. "{{first_name}," or "{slots}}"."""
    text = text or ""
    covered = [False] * len(text)
    for m in BRACE_TOKEN_RE.finditer(text):
        for i in range(m.start(), m.end()):
            covered[i] = True
    out = []
    for i, ch in enumerate(text):
        if ch not in "{}" or covered[i]:
            continue
        a = i
        while a > 0 and not text[a - 1].isspace():
            a -= 1
        b = i + 1
        while b < len(text) and not text[b].isspace():
            b += 1
        run = text[a:b]
        if run not in out:
            out.append(run)
    return out


def split_notes(text):
    """(notes, text_without_notes): note lines hold (note) or start with NOTE."""
    notes, keep = [], []
    for line in (text or "").split("\n"):
        if NOTE_MARK_RE.search(line) or NOTE_START_RE.match(line):
            notes.append(line.strip())
        else:
            keep.append(line)
    while keep and not keep[0].strip():
        keep.pop(0)
    while keep and not keep[-1].strip():
        keep.pop()
    return notes, "\n".join(keep)


def _entry(tag, what, block, old, new, change=None):
    section, path, note = route(tag, block)
    e = OrderedDict([("tag", tag), ("section", section), ("file", path), ("what", what)])
    if note:
        e["route_note"] = note
    if block is not None:
        e["kind"] = block.get("kind")
        e["source"] = block.get("source")
    e["old"] = old
    e["new"] = new
    if new is not None:
        notes, clean = split_notes(new)
        style = placeholder_style(tag, block)
        e["notes_for_claude"] = notes
        e["new_text_without_notes"] = clean
        # The copy is what gets sent: a brace inside a note does not flag it.
        e["invalid_placeholders"] = invalid_placeholders(clean)
        e["wrong_placeholder_style"] = wrong_placeholder_style(clean, style)
        e["stray_braces"] = stray_braces(clean)
        if change is not None:
            e["typed"] = list(change["typed"])
            e["placeholders_added"] = list(change["placeholders_added"])
            e["placeholders_removed"] = list(change["placeholders_removed"])
        else:
            e["typed"] = diff_doc.flags(u"", new)
            e["placeholders_added"] = diff_doc.placeholders(new)
            e["placeholders_removed"] = []
    return e


def build_report(text, manifest, export_name=None, raw=None):
    """raw: the export file's bytes, hashed as they are (default: text as UTF-8)."""
    info = parse_with_info(text)
    if not info["order"]:
        # An empty file or the base64 JSON from the Drive read-back would
        # otherwise report every manifest block as deleted.
        raise ValueError("no tagged blocks found; is this the text/plain export?")
    d = diff_doc.diff(info, manifest)
    by_tag = OrderedDict((b["tag"], b) for b in manifest["blocks"])
    entries = []
    for c in d["changed"]:
        entries.append(_entry(c["tag"], "changed", by_tag.get(c["tag"]), c["old"], c["new"], c))
    for tag in d["missing"]:
        entries.append(_entry(tag, "deleted", by_tag.get(tag), by_tag[tag]["text"], None))
    for tag in d["unknown"]:
        entries.append(_entry(tag, "new", None, None, info["blocks"][tag]))
    sections = OrderedDict((str(s), []) for s in (1, 2, 3, 4))
    for e in entries:
        sections[str(e["section"])].append(e)
    conflicts = []
    for g in d["conflicting_text_groups"]:
        conflicts.append(OrderedDict([
            ("text_group", g),
            ("tags", [c["tag"] for c in d["changed"] if c["text_group"] == g])]))
    counts = OrderedDict(d["counts"])
    counts["routed"] = len(entries)
    return OrderedDict([
        ("export", export_name),
        ("export_sha256", hashlib.sha256(raw if raw is not None else text.encode("utf-8")).hexdigest()),
        ("counts", counts),
        ("duplicates", list(d["duplicates"])),
        ("conflicting_text_groups", conflicts),
        ("cosmetic_only", len(d["cosmetic_only"])),
        ("sections", sections),
    ])


SECTION_NAMES = OrderedDict([
    ("1", "Section 1: email follow-up and nurture"),
    ("2", "Section 2: booked calls"),
    ("3", "Section 3: Upwork"),
    ("4", "Section 4: core engine, Instantly, go-live"),
])
FLAG_KEYS = ("typed", "placeholders_added", "placeholders_removed",
             "invalid_placeholders", "wrong_placeholder_style", "stray_braces")


def render_text(r):
    out = []
    c = r["counts"]
    out.append("export: %s" % (r["export"] or "-"))
    out.append("export sha256: %s" % r["export_sha256"])
    out.append("blocks in manifest: %d, found in doc: %d" % (c["manifest_blocks"], c["parsed_blocks"]))
    out.append("changed: %d, deleted: %d, new: %d, cosmetic only: %d"
               % (c["changed"], c["missing"], c["unknown"], r["cosmetic_only"]))
    out.append("duplicate tags (decide first): %s" % (", ".join(r["duplicates"]) or "none"))
    if r["conflicting_text_groups"]:
        out.append("conflicting edits of one sentence (decide first):")
        for g in r["conflicting_text_groups"]:
            out.append("  %s: %s" % (g["text_group"], ", ".join(g["tags"])))
    else:
        out.append("conflicting edits of one sentence (decide first): none")
    if not c["routed"]:
        out.append("\nNothing to route: the doc matches the manifest.")
    for key, entries in r["sections"].items():
        if not entries:
            continue
        out.append("\n########## %s (%d)" % (SECTION_NAMES[key], len(entries)))
        for e in entries:
            out.append("\n== %s: %s" % (e["what"], e["tag"]))
            out.append("   file: %s" % e["file"])
            out.append("   source: %s" % (e.get("source") or "-"))
            if e.get("route_note"):
                out.append("   note: %s" % e["route_note"])
            if e["old"] is not None:
                out.append("-- old:\n" + e["old"])
            if e["new"] is not None:
                out.append("-- new:\n" + e["new"])
                if e["notes_for_claude"]:
                    out.append("-- notes for Claude (not email copy):")
                    for n in e["notes_for_claude"]:
                        out.append("   " + n)
                    out.append("-- new text without notes:\n" + e["new_text_without_notes"])
                for k in FLAG_KEYS:
                    if e[k]:
                        out.append("   %s: %s" % (k, ", ".join(e[k])))
    return "\n".join(out) + "\n"


def render_md(r):
    out = ["# Doc routing report", ""]
    c = r["counts"]
    out.append("- export: `%s`" % (r["export"] or "-"))
    out.append("- sha256: `%s`" % r["export_sha256"])
    out.append("- changed %d, deleted %d, new %d, cosmetic only %d"
               % (c["changed"], c["missing"], c["unknown"], r["cosmetic_only"]))
    out.append("- duplicate tags (decide first): %s" % (", ".join(r["duplicates"]) or "none"))
    out.append("- conflicting edits (decide first): %s" % (
        "; ".join("%s: %s" % (g["text_group"], ", ".join(g["tags"]))
                  for g in r["conflicting_text_groups"]) or "none"))
    if not c["routed"]:
        out += ["", "Nothing to route: the doc matches the manifest."]
    for key, entries in r["sections"].items():
        if not entries:
            continue
        out += ["", "## %s" % SECTION_NAMES[key]]
        for e in entries:
            out += ["", "### %s `%s`" % (e["what"], e["tag"]), "", "- file: `%s`" % e["file"],
                    "- source: `%s`" % (e.get("source") or "-")]
            if e.get("route_note"):
                out.append("- note: %s" % e["route_note"])
            if e["new"] is not None:
                for k in FLAG_KEYS:
                    if e[k]:
                        out.append("- %s: %s" % (k, ", ".join("`%s`" % x for x in e[k])))
                for n in e["notes_for_claude"]:
                    out.append("- note for Claude: %s" % n)
            if e["old"] is not None:
                out += ["", "Old:", "", "```", e["old"], "```"]
            if e["new"] is not None:
                label = "New (without notes):" if e["notes_for_claude"] else "New:"
                out += ["", label, "", "```", e["new_text_without_notes"], "```"]
    return "\n".join(out) + "\n"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    usage = "usage: route_doc.py EXPORT.txt [--manifest manifest.json] [--json OUT.json] [--md OUT.md]"
    opts = {"--manifest": os.path.join(HERE, "manifest.json"), "--json": None, "--md": None}
    for key in list(opts):
        if key in args:
            i = args.index(key)
            if i + 1 >= len(args):
                sys.stderr.write(usage + "\n")
                return 2
            opts[key] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 1:
        sys.stderr.write(usage + "\n")
        return 2
    try:
        with open(args[0], "rb") as fh:
            raw = fh.read()
        text = raw.decode("utf-8-sig")
        manifest = diff_doc.load_manifest(opts["--manifest"])
        report = build_report(text, manifest, export_name=os.path.basename(args[0]), raw=raw)
    except (IOError, OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write("route_doc: cannot read or parse the export: %s\n" % exc)
        return 2
    sys.stdout.write(render_text(report))
    if opts["--json"]:
        with io.open(opts["--json"], "w", encoding="utf-8") as fh:
            fh.write(json.dumps(report, indent=1, ensure_ascii=False))
    if opts["--md"]:
        with io.open(opts["--md"], "w", encoding="utf-8") as fh:
            fh.write(render_md(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
