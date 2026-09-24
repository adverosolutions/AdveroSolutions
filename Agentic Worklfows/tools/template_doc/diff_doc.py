"""Compare the parsed Google Doc with manifest.json.

Lists the blocks that changed (tag, old, new), the tags that are missing
(deleted from the doc) and any unknown tags. Comparison ignores what Google
or a copy-paste changes on its own: extra blank lines (a run of them counts as
one paragraph break; a break added or removed is a change), runs of spaces,
spaces at the ends of lines, curly quotes and non-breaking spaces. Those are normalised for
comparison only; the reported "new" text is exactly what the doc holds, and a
changed block lists what Lorenzo typed that the send checks care about
(curly quotes, non-breaking spaces, dashes, "!", placeholders added or lost).

    python3 diff_doc.py export.txt [--manifest manifest.json] [--json]
"""
import json
import os
import re
import sys
from collections import OrderedDict

from parse_doc import parse_with_info

HERE = os.path.dirname(os.path.abspath(__file__))
PLACEHOLDER_RE = re.compile(r"\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}|\{[A-Za-z_][A-Za-z0-9_]*\}")
SINGLE_QUOTES = u"‘’‚‛′"
DOUBLE_QUOTES = u"“”„‟″"
SPACES = u"     　"


def norm(text):
    t = text
    for ch in SINGLE_QUOTES:
        t = t.replace(ch, u"'")
    for ch in DOUBLE_QUOTES:
        t = t.replace(ch, u'"')
    for ch in SPACES:
        t = t.replace(ch, u" ")
    t = t.replace(u"\t", u" ")
    lines = [re.sub(u" +", u" ", l).strip() for l in t.split(u"\n")]
    # A run of blank lines is one paragraph break (Drive's export doubles
    # them); a break added or removed is a change (the hash keeps them).
    out = []
    for l in lines:
        if l or (out and out[-1]):
            out.append(l)
    while out and not out[-1]:
        out.pop()
    return u"\n".join(out)


def placeholders(text):
    return sorted(set(m.group(0).replace(" ", "") for m in PLACEHOLDER_RE.finditer(norm(text))))


def flags(old, new):
    out = []
    if any(ch in new for ch in SINGLE_QUOTES + DOUBLE_QUOTES):
        out.append("curly_quotes")
    if any(ch in new for ch in SPACES):
        out.append("non_breaking_space")
    if u"—" in new and u"—" not in old:
        out.append("em_dash")
    if u"–" in new and u"–" not in old:
        out.append("en_dash")
    if new.count("!") > old.count("!"):
        out.append("exclamation_mark")
    if u"…" in new and u"…" not in old:
        out.append("ellipsis_character")
    return out


def load_manifest(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def diff(parsed_info, manifest):
    blocks = manifest["blocks"]
    by_tag = OrderedDict((b["tag"], b) for b in blocks)
    parsed = parsed_info["blocks"]
    changed, cosmetic = [], []
    for tag, b in by_tag.items():
        if tag not in parsed:
            continue
        old, new = b["text"], parsed[tag]
        if norm(old) == norm(new):
            if old != new:
                cosmetic.append(tag)
            continue
        po, pn = placeholders(old), placeholders(new)
        changed.append(OrderedDict([
            ("tag", tag), ("kind", b["kind"]),
            ("template_id", b.get("template_id")), ("variant", b.get("variant")),
            ("campaign_id", b.get("campaign_id")), ("step", b.get("step")), ("field", b.get("field")),
            ("old", old), ("new", new), ("new_normalized", norm(new)),
            ("placeholders_removed", [p for p in po if p not in pn]),
            ("placeholders_added", [p for p in pn if p not in po]),
            ("typed", flags(old, new)),
            ("text_group", b.get("text_group")),
        ]))
    missing = [t for t in by_tag if t not in parsed]
    unknown = [t for t in parsed if t not in by_tag]
    # the repeat rule: copies of one sentence that were changed differently
    groups = OrderedDict()
    for c in changed:
        groups.setdefault(c["text_group"], set()).add(c["new_normalized"])
    conflicting = [g for g, news in groups.items() if len(news) > 1]
    return OrderedDict([
        ("changed", changed), ("missing", missing), ("unknown", unknown),
        ("duplicates", parsed_info.get("duplicates", [])),
        ("cosmetic_only", cosmetic),
        ("conflicting_text_groups", conflicting),
        ("counts", OrderedDict([("manifest_blocks", len(by_tag)), ("parsed_blocks", len(parsed)),
                                ("changed", len(changed)), ("missing", len(missing)),
                                ("unknown", len(unknown)), ("cosmetic_only", len(cosmetic))])),
    ])


def is_clean(report):
    return not (report["changed"] or report["missing"] or report["unknown"] or report["duplicates"])


def print_report(r):
    c = r["counts"]
    print("blocks in manifest: %d, found in doc: %d" % (c["manifest_blocks"], c["parsed_blocks"]))
    print("changed: %d, missing: %d, unknown: %d, duplicate tags: %d, cosmetic only: %d"
          % (c["changed"], c["missing"], c["unknown"], len(r["duplicates"]), c["cosmetic_only"]))
    for ch in r["changed"]:
        print("\n== changed: %s" % ch["tag"])
        print("-- old:\n" + ch["old"])
        print("-- new:\n" + ch["new"])
        for k in ("placeholders_removed", "placeholders_added", "typed"):
            if ch[k]:
                print("   %s: %s" % (k, ", ".join(ch[k])))
    for k in ("missing", "unknown", "duplicates", "conflicting_text_groups"):
        if r[k]:
            print("\n%s: %s" % (k, ", ".join(r[k])))


if __name__ == "__main__":
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    mpath = os.path.join(HERE, "manifest.json")
    if "--manifest" in args:
        i = args.index("--manifest")
        mpath = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit("usage: diff_doc.py <plain-text export> [--manifest manifest.json] [--json]")
    with open(args[0], "rb") as fh:
        text = fh.read().decode("utf-8-sig")
    report = diff(parse_with_info(text), load_manifest(mpath))
    if as_json:
        print(json.dumps(report, indent=1, ensure_ascii=False))
    else:
        print_report(report)
