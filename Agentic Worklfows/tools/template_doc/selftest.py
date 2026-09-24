"""Round-trip self-test for the one-doc build. Local only, Python 3.9.

1. Render advero_all_emails.html to plain text the way Drive's text export
   would (headings and paragraphs become lines, spans stay inline, an empty
   paragraph is an empty line, a table cell is a line).
2. Parse it and diff it against manifest.json: the diff must be empty.
3. Every approvable template id in the export is a main block; all 12
   Instantly steps are there.
4. Google-style noise (BOM, CRLF, curly quotes, non-breaking spaces, extra
   blank lines, trailing spaces, tag spacing) still diffs empty.
5. Real edits are caught: a changed line, a deleted block, an unknown tag, a
   duplicated tag and a changed subject.
Prints the counts. Exit 1 on any failure.
"""
import json
import os
import re
import sys
from html.parser import HTMLParser

from export_parse import parse_export
from parse_doc import parse_with_info
from diff_doc import diff, is_clean, norm

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(HERE, "advero_all_emails.html")
MANIFEST = os.path.join(HERE, "manifest.json")
EXPORT = os.path.join(HERE, "templates_export_final.md")

BLOCK = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "tr", "td", "th", "table", "title"}
SKIP = {"head", "title", "style", "script"}


class GoogleText(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.paras = []
        self.cur = None
        self.skip = 0

    def flush(self):
        if self.cur is not None:
            self.paras.append(self.cur)
        self.cur = None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if tag in BLOCK:
            self.flush()
        elif tag == "br":
            self.cur = "" if self.cur is None else self.cur + "\n"

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip -= 1
            return
        if tag in BLOCK:
            self.flush()

    def handle_data(self, d):
        if self.skip:
            return
        d = re.sub(r"[ \t\r\n]+", " ", d)
        if self.cur is None:
            if not d.strip():
                return
            self.cur = d
        else:
            self.cur += d

    def text(self):
        self.flush()
        return "\n".join(p.strip(" ") if p.strip() else "" for p in self.paras)


def html_to_text(path):
    g = GoogleText()
    g.feed(open(path, encoding="utf-8").read())
    return g.text()


def googleify(text):
    """Noise Google or a copy-paste can add without anyone typing."""
    t = text.replace("'", u"’").replace('"', u"”")
    t = t.replace("Hey ", u"Hey ")
    t = re.sub(r"\(tag: ", "( tag:", t)
    lines = []
    for i, l in enumerate(t.split("\n")):
        lines.append(l + ("  " if i % 3 == 0 else ""))
        if i % 7 == 0:
            lines.append("")
    return u"﻿" + "\r\n".join(lines)


failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


manifest = json.load(open(MANIFEST, encoding="utf-8"))
blocks = manifest["blocks"]
text = html_to_text(HTML_PATH)
open(os.path.join(HERE, "roundtrip_export.txt"), "w", encoding="utf-8").write(text)

# 1-2 round trip
info = parse_with_info(text)
rep = diff(info, manifest)
check(is_clean(rep), "round trip: changed=%d missing=%d unknown=%d duplicates=%d"
      % (len(rep["changed"]), len(rep["missing"]), len(rep["unknown"]), len(rep["duplicates"])))
exact = sum(1 for b in blocks if info["blocks"].get(b["tag"]) == b["text"])
check(exact == len(blocks), "round trip is exact (not just normalised) for %d of %d blocks" % (exact, len(blocks)))

# 3 coverage
exp = parse_export(EXPORT)
appr = [e["id"] for e in exp["entries"] if e["approvable"]]
mains = set(b["tag"] for b in blocks if b["kind"] == "template_main")
check(len(appr) == 108 and all(i in mains and i in info["blocks"] for i in appr),
      "all %d approvable ids are main blocks in the doc" % len(appr))
steps = set((b["campaign_id"], b["step"]) for b in blocks if b["kind"] == "instantly_step" and b["field"] == "body")
check(len(steps) == 12 and all(b["tag"] in info["blocks"] for b in blocks if b["kind"] == "instantly_step"),
      "all 12 Instantly steps (body and subject) are in the doc")
snap = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), manifest["snapshot"]), encoding="utf-8"))
snap_steps = set((c["id"], i + 1) for c in snap["items"] for i, _ in enumerate(c["sequences"][0]["steps"]))
check(steps == snap_steps, "Instantly steps match the snapshot's 6 campaigns x 2 steps")
subj_ok = all(b["text"] == next(v for v in [s["variants"][0] for c in snap["items"] if c["id"] == b["campaign_id"]
                                              for s in [c["sequences"][0]["steps"][b["step"] - 1]]])["subject"]
              for b in blocks if b["kind"] == "instantly_step" and b["field"] == "subject")
check(subj_ok, "Instantly subjects are exactly as stored")
vars_ok = True
for b in blocks:
    if b["kind"] == "instantly_step" and b["field"] == "body":
        raw_vars = sorted(set(re.findall(r"\{\{[^}]+\}\}", b["raw_html"])))
        if sorted(set(re.findall(r"\{\{[^}]+\}\}", b["text"]))) != raw_vars:
            vars_ok = False
check(vars_ok, "Instantly {{variables}} kept exactly")
for tag in ("X-AFTER", "U-PRICE-1", "U-PRICE-2", "U-PRICE-3"):
    check(tag in info["blocks"], "%s present" % tag)

# 4 Google noise
noisy = googleify(text)
rep2 = diff(parse_with_info(noisy), manifest)
check(is_clean(rep2) and len(rep2["cosmetic_only"]) > 50,
      "Google-style noise diffs empty (%d blocks differ only cosmetically)" % len(rep2["cosmetic_only"]))

# 5 real edits are caught
lines = text.split("\n")
i_d3 = next(i for i, l in enumerate(lines) if l.endswith("(tag: cadence.d3)"))
j = next(k for k in range(i_d3 + 1, len(lines)) if lines[k].startswith("A couple more options"))
edited = list(lines)
edited[j] = u"A couple more times that might suit: {slots}. Don’t worry if not!"
# delete Day 14 (heading + body + variants) up to the Day 30 heading
a = next(i for i, l in enumerate(edited) if l.endswith("(tag: cadence.d14)"))
b = next(i for i, l in enumerate(edited) if l.endswith("(tag: cadence.d30)"))
del edited[a:b]
# unknown tag and duplicate tag
edited.insert(5 + next(i for i, l in enumerate(edited) if "(tag: X-AFTER)" in l), "New thing (tag: first_reply.x.y)")
k = next(i for i, l in enumerate(edited) if l.endswith("(tag: cadence.d7)"))
edited.insert(k, "Day 1 follow-up (tag: cadence.d1)")
edited.insert(k + 1, "stray")
# subject edit
s = next(i for i, l in enumerate(edited) if "(tag: no_show.ns_d14_breakup_email/subject)" in l)
edited[s] = "Subject: Closing the loop (tag: no_show.ns_d14_breakup_email/subject)"
# fill in an Upwork box
u = next(i for i, l in enumerate(edited) if "(tag: U-PRICE-1)" in l)
edited.insert(u + 1, "Simple automations start at $500 fixed.")
rep3 = diff(parse_with_info("\n".join(edited)), manifest)
chg = dict((c["tag"], c) for c in rep3["changed"])
check("cadence.d3" in chg and "exclamation_mark" in chg["cadence.d3"]["typed"]
      and "curly_quotes" in chg["cadence.d3"]["typed"], "an edited line is reported, with the typed '!' and curly quote")
check("no_show.ns_d14_breakup_email/subject" in chg and chg["no_show.ns_d14_breakup_email/subject"]["new"] == "Closing the loop",
      "an edited subject is reported without the 'Subject:' prefix")
check("U-PRICE-1" in chg and chg["U-PRICE-1"]["new"] == "Simple automations start at $500 fixed.",
      "a filled Upwork box is reported")
d14 = [b["tag"] for b in blocks if b["tag"] == "cadence.d14" or b["tag"].startswith("cadence.d14/")]
check(sorted(rep3["missing"]) == sorted(d14), "a deleted email is reported missing: %s" % ", ".join(d14))
check(rep3["unknown"] == ["first_reply.x.y"], "an unknown tag is reported")
check(rep3["duplicates"] == ["cadence.d1"], "a duplicated tag is reported")
check(len(rep3["changed"]) == 3, "nothing else is reported as changed (%d)" % len(rep3["changed"]))

# counts
kinds = {}
for b in blocks:
    kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
sections = sum(1 for l in lines if l.endswith("(section)")) + (1 if "X-AFTER" in info["blocks"] else 0)
top_sections = len(re.findall(r"<h1>[^<]*<span[^>]*>\(section\)</span></h1>", open(HTML_PATH, encoding="utf-8").read())) + 1
print("\ncounts")
print("  html bytes:", os.path.getsize(HTML_PATH))
print("  top-level sections (h1):", top_sections, " all section lines incl. sub-groups:", sections)
print("  blocks by kind:", json.dumps(kinds, sort_keys=True))
print("  emails and texts (main bodies, incl. 12 Instantly steps, excl. spliced lines):",
      sum(1 for b in blocks if (b["kind"] == "template_main" and not b.get("spliced_into"))
          or (b["kind"] == "instantly_step" and b["field"] == "body")))
print("  spliced lines (days 2, 4, 5):", sum(1 for b in blocks if b.get("spliced_into")))
print("  variant blocks:", kinds.get("template_variant", 0))
print("  subject blocks:", kinds.get("template_subject", 0) + sum(1 for b in blocks if b.get("field") == "subject"))
print("  plain-text export lines:", len(lines))
if failures:
    print("\n%d FAILED" % len(failures))
    sys.exit(1)
print("\nall checks passed")
