"""Build the one Google-Docs-ready HTML file with every email the system sends,
plus manifest.json (one record per editable block).

Local only: reads the template export and the Instantly snapshot. No network.
Python 3.9.

    python3 build.py [--export PATH] [--snapshot PATH] [--out-dir DIR]

Every build carries a fingerprint (doc_areas.fingerprint: every block's tag,
text and hash plus every line outside block bodies). It is printed in the doc
as the "(tag: X-BUILD)" line and stored in the manifest. Without --out-dir the
build goes to builds/<fingerprint>/ (html + manifest); the top-level
advero_all_emails.html and manifest.json are the build of the doc currently in
Drive and change only when a new doc is uploaded and promoted (README.txt).

Every part of every template's hashed review text is shown in the doc, so a
code change to any of it changes the doc: the main text, each variant (as its
changes, or a note listing the lines it drops, or skipped only when it is the
main text with example times the formatters write, or the documented missing-
data fallbacks), the fallback subjects (a note), and the full value_formats
block (one tagged block per distinct text, formats.N).

Parser contract (parse_doc.py implements it; the manifest mirrors it):
- A line with "(tag: X)" starts block X. For a tag ending in "/subject" the
  block is that one line: the text outside the tag, minus a leading
  "Subject:". It does not end the block that was open.
- Any other tag line is a label (a heading or "If there are no free times:");
  its block is the lines after it, up to the next tag line or "(section)" line.
- A line ending in "(section)" ends the open block and is skipped.
- A line ending in "(note)" is skipped and does not end the open block.
- Text before the first tag is the doc's top section and is ignored.
"""
import difflib
import hashlib
import html
import json
import os
import re
import subprocess
from collections import OrderedDict

import doc_areas
from doc_rules import HELD_NOTE, SPLICED, is_held
from export_parse import parse_export, variant, source_of

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # tools/template_doc -> Agentic Worklfows
EXPORT = os.path.join(HERE, "templates_export_final.md")
SNAPSHOT_REL = "config/snapshots/instantly_campaigns_2026-09-21.json"
SNAPSHOT = os.path.join(REPO, SNAPSHOT_REL)
BUILDS_DIR = os.path.join(HERE, "builds")
OUT_DIR = None  # builds/<fingerprint>/ unless --out-dir is given

if __name__ == "__main__":
    # Optional paths (record_doc_approvals.py builds a fresh doc into a temp
    # folder this way).
    import argparse
    _ap = argparse.ArgumentParser(description="Build advero_all_emails.html and manifest.json.")
    _ap.add_argument("--export", default=EXPORT, help="jobs/approve_templates.py --export markdown to read")
    _ap.add_argument("--out-dir", default=None,
                     help="folder for advero_all_emails.html and manifest.json (default builds/<fingerprint>/)")
    _ap.add_argument("--snapshot", default=SNAPSHOT, help="Instantly campaigns snapshot JSON")
    _args = _ap.parse_args()
    EXPORT = os.path.abspath(_args.export)
    OUT_DIR = os.path.abspath(_args.out_dir) if _args.out_dir else None
    if os.path.abspath(_args.snapshot) != os.path.abspath(SNAPSHOT):
        SNAPSHOT = os.path.abspath(_args.snapshot)
        _rel = os.path.relpath(SNAPSHOT, REPO)
        SNAPSHOT_REL = SNAPSHOT if _rel.startswith("..") else _rel.replace(os.sep, "/")

HTML_NAME = "advero_all_emails.html"
MANIFEST_NAME = "manifest.json"

PH_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")

# ------------------------------------------------------------------ styles
S_TAG = "color:#999;font-size:8pt"
# inside a heading the span also resets the heading's bold, so the tag stays small and plain
S_TAG_H = "color:#999;font-size:8pt;font-weight:normal"
S_NOTE = "color:#666;font-style:italic"
S_LABEL = "color:#666;font-style:italic"

AUTHORED = []  # every string I wrote, checked for dashes and "!"


def esc(s):
    return html.escape(s, quote=False)


def tag_span(tag, heading=False):
    return '<span style="%s">(tag: %s)</span>' % (S_TAG_H if heading else S_TAG, esc(tag))


def marker_span(word, heading=False):
    return '<span style="%s">(%s)</span>' % (S_TAG_H if heading else S_TAG, word)


class Doc(object):
    def __init__(self):
        self.parts = []
        self.manifest = []
        self.tags = set()

    def raw(self, s):
        self.parts.append(s)

    def title(self, text):
        AUTHORED.append(text)
        self.raw("<h1>%s</h1>" % esc(text))

    def top_h2(self, text):
        AUTHORED.append(text)
        self.raw("<h2>%s</h2>" % esc(text))

    def top_p(self, text):
        AUTHORED.append(text)
        self.raw('<p>%s</p>' % esc(text))

    def section(self, level, text):
        AUTHORED.append(text)
        self.raw("<h%d>%s %s</h%d>" % (level, esc(text), marker_span("section", heading=True), level))

    def note(self, text):
        AUTHORED.append(text)
        self.raw('<p><span style="%s">%s</span> %s</p>' % (S_NOTE, esc(text), marker_span("note")))

    def note_quoting(self, text, quoted):
        """A note that quotes template lines (not authored text, so not
        checked for dashes and "!")."""
        AUTHORED.append(text)
        body = text + " " + " / ".join('"%s"' % q for q in quoted)
        self.raw('<p><span style="%s">%s</span> %s</p>' % (S_NOTE, esc(body), marker_span("note")))

    def build_line(self, text, tag):
        AUTHORED.append(text)
        self.raw('<p><span style="%s">%s %s</span> %s</p>' % (S_NOTE, esc(text), doc_areas.FP_PLACEHOLDER, tag_span(tag)))

    def lines(self, lines):
        for ln in lines:
            if ln.strip():
                self.raw('<p>%s</p>' % esc(ln))
            else:
                self.raw('<p><br></p>')

    def _record(self, rec):
        if rec["tag"] in self.tags:
            raise SystemExit("duplicate tag %s" % rec["tag"])
        self.tags.add(rec["tag"])
        self.manifest.append(rec)

    def email_heading(self, text, tag, rec, level=3):
        AUTHORED.append(text)
        self.raw("<h%d>%s %s</h%d>" % (level, esc(text), tag_span(tag, heading=True), level))
        rec["tag"] = tag
        rec["heading"] = text
        self._record(rec)

    def subject(self, tag, text, rec):
        self.raw('<p><b>Subject:</b> %s %s</p>' % (esc(text), tag_span(tag)))
        rec["tag"] = tag
        rec["text"] = text
        self._record(rec)

    def variant_label(self, label, tag, rec):
        AUTHORED.append(label)
        self.raw('<p><span style="%s">%s</span> %s</p>' % (S_LABEL, esc(label), tag_span(tag)))
        rec["tag"] = tag
        rec["label"] = label
        self._record(rec)

    def box(self, label, tag, rec):
        AUTHORED.append(label)
        self.raw('<p><span style="%s">%s</span> %s</p>' % (S_LABEL, esc(label), tag_span(tag)))
        self.raw('<table style="border-collapse:collapse;width:100%"><tr><td style="border:1px solid #999;padding:6pt">'
                 '<p><br></p></td></tr></table>')
        rec["tag"] = tag
        rec["label"] = label
        self._record(rec)


def strip_blank(ls):
    ls = list(ls)
    while ls and not ls[-1].strip():
        ls.pop()
    while ls and not ls[0].strip():
        ls.pop(0)
    return ls


def doc_text(lines):
    """What parse_doc returns for these body lines."""
    return "\n".join(l.rstrip() for l in strip_blank(lines))


def norm_key(text):
    t = text.replace(" ", " ")
    t = re.sub(r"[‘’]", "'", t)
    t = re.sub(r"[“”]", '"', t)
    ls = [re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n")]
    return "\n".join(l for l in ls if l)


def text_group(text):
    return hashlib.sha256(norm_key(text).encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------ export
data = parse_export(EXPORT)
entries = data["entries"]
by_id = OrderedDict((e["id"], e) for e in entries)
approvable_ids = [e["id"] for e in entries if e["approvable"]]
assert len(approvable_ids) == data["counts"]["approvable"] == 108, (len(approvable_ids), data["counts"])
export_sha = hashlib.sha256(open(EXPORT, "rb").read()).hexdigest()

# value_formats: one tagged block per distinct text (formats.1, formats.2, ...),
# shown in full; every template that carries it depends on its block.
VF_TAGS = OrderedDict()  # text -> tag
VF_OF = {}  # template id -> tag
for e in entries:
    v = variant(e, "value_formats")
    if v and e["approvable"]:
        t = "\n".join(v["lines"])
        if t not in VF_TAGS:
            VF_TAGS[t] = "formats.%d" % (len(VF_TAGS) + 1)
        VF_OF[e["id"]] = VF_TAGS[t]
assert VF_TAGS, "no value_formats block"
VF_NEEDLES = ("Two times, {slots} and {alt_slots}: Tue 12:05pm or Thu 4:30pm CT",
               "One time, {slots}, {alt_slots}, {slot1} and {slot2}: Tue 12:05pm CT",
               "A time without its zone, {slot}: Tue 12:05pm",
               "{alt_slots}: Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT",
               "America/New_York = Mon 10:45am ET",
               "America/New_York = (1:05pm ET your time)",
               "The call time, {when_ct}: Tue, Jan 8 at 12:05pm CT",
               "America/New_York = Tue, Jan 8 at 12:05pm CT (1:05pm ET)",
               "The clock time only, {time_ct}: 12:05pm CT",
               "America/Phoenix = MST")
for _vf in VF_TAGS:
    for needle in VF_NEEDLES:  # the top section's "How times are written" claims
        assert needle in _vf, needle

DAYS_RE = re.compile(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b")
MONTHS_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b")


def value_shape(s):
    """A value with its day names, month names, numbers and am/pm abstracted:
    Tue Jan 15 2:43pm CT and Mon Jan 7 9:45am CT have the same shape."""
    s = DAYS_RE.sub("<day>", s)
    s = MONTHS_RE.sub("<mon>", s)
    s = re.sub(r"\d+", "<n>", s)
    return re.sub(r"(?<=<n>)(?:am|pm)\b", "<ap>", s)


def vf_examples(vf_text):
    """placeholder -> shapes of the example values the formatters wrote for
    it in a value_formats block ("{slots} and {alt_slots}: X", "{p}: A = X | B = Y")."""
    ex = {}
    for ln in vf_text.split("\n"):
        phs = PH_RE.findall(ln)
        if not phs:
            continue
        rest = ln[ln.rfind(phs[-1]) + len(phs[-1]):]
        if not rest.startswith(": "):
            continue
        for seg in rest[2:].split(" | "):
            val = seg.split(" = ", 1)[1] if " = " in seg else seg
            for p in phs:
                ex.setdefault(p, set()).add(value_shape(val))
    return ex

# spliced fragments, for normalising variant text back to the placeholder
FRAGMENTS = {
    "{case_study}": [by_id[i]["main"][0] for i in approvable_ids if i.startswith("cadence.d4.case_study.")],
    "{free_work}": [by_id[i]["main"][0] for i in approvable_ids if i.startswith("cadence.d5.free_work.")],
    "{research_line}": [by_id[i]["main"][0] for i in approvable_ids if i.startswith("cadence.d2.research_fallback.")],
}
COMPANY_FALLBACKS = ("your business", "your team")


def unsplice(main, lines):
    """Put {case_study}/{free_work}/{research_line} back where a variant shows
    one of the spliced lines in place (d2, d4, d5)."""
    out = []
    for ln in lines:
        for ph, frs in FRAGMENTS.items():
            if not any(ph in m for m in main):
                continue
            for fr in frs:
                for cand in [fr] + [fr.replace("{company}", fb) for fb in COMPANY_FALLBACKS]:
                    if cand in ln:
                        ln = ln.replace(cand, ph)
        out.append(ln)
    return out


def hunks(main, lines):
    sm = difflib.SequenceMatcher(a=main, b=lines, autojunk=False)
    res = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        res.append({"old": main[i1:i2], "new": lines[j1:j2], "at": [i1, i2]})
    return res


def missing_data_explained(main, vlines):
    """True when the missing_lead_data variant is only the global fallbacks
    described once at the top of the doc."""
    for fb in COMPANY_FALLBACKS:
        subs = [("Hey {first_name},", "Hey there,"), ("{company}", fb),
                ("{referral_name}", "the right person"), ("{referral_first_name}", "them"),
                ("{first_name}", None)]
        out = []
        for ln in main:
            for a, b in subs:
                if b is None:
                    continue
                ln = ln.replace(a, b)
            out.append(ln)
        if out == vlines:
            return fb
    return None


def fill_only(h, examples):
    """A hunk that only fills placeholders with example times (dated forms,
    another zone). Every filled value must be the placeholder itself or have
    exactly the shape of one of the formatter's example values for that
    placeholder in the template's own value_formats block (shown in the doc):
    any other word in a value (", or wire the deposit today") shows the
    variant instead."""
    if len(h["old"]) != len(h["new"]):
        return False
    for o, n in zip(h["old"], h["new"]):
        if o == n:
            continue
        if not PH_RE.search(o):
            return False
        parts = re.split(r"(\{[A-Za-z_][A-Za-z0-9_]*\})", o)
        phs = [p for p in parts if PH_RE.fullmatch(p)]
        pat = "^" + "".join("(.+?)" if PH_RE.fullmatch(p) else re.escape(p) for p in parts) + "$"
        m = re.match(pat, n)
        if not m:
            return False
        for ph, val in zip(phs, m.groups()):
            if val != ph and value_shape(val) not in examples.get(ph, ()):
                return False
    return True


VARIANT_LABELS = {
    "no_slots": "If there are no free times:",
    "one_slot": "If only one time is free:",
    "confirmed_time": "If they asked for a time that works:",
    "proposed_time_refused": "If they asked for a time that doesn't work:",
    "lead_in_other_timezone": "If they are in another timezone:",
    "no_alternatives": "If there are no other free times:",
    "no_proposed_time": "If we couldn't read the time they asked for:",
    "no_booking_link": "If no booking link is set up:",
    "no_call_link": "If there is no call link yet:",
    "missing_lead_data": "If we don't have their details:",
    "dated": "If the other times fall in another week:",
    "no_loom_url": "If no Loom link is set up:",
}
DELETION_NOTES = {
    "no_loom_url": "If no Loom link is set up, these lines are left out:",
}
VARIANT_NOTES = {
    "confirmed_time": "This version always comes to you as a card first.",
}

stats = {"variants_shown": 0, "variants_skipped": {}, "deletion_notes": 0, "missing_explained": 0,
         "company_fallback_team": set()}
placed = []


def skip(name, why):
    stats["variants_skipped"].setdefault(name + ": " + why, 0)
    stats["variants_skipped"][name + ": " + why] += 1


def subject_parts(e):
    """(subject text, fallback note or None, inline) for an entry."""
    main = e["main"]
    if main and main[0].startswith("Subject: "):
        return main[0][len("Subject: "):], None, True
    v = variant(e, "subject")
    if not v:
        return None, None, False
    ls = v["lines"]
    assert ls[0].startswith("Subject: "), ls
    notes = []
    for ln in ls[1:]:
        if ln.startswith("Subject when the thread has none: "):
            notes.append("If their email had no subject: " + ln.split(": ", 1)[1] + ".")
        elif ln.startswith("Subject when there is no first name either: "):
            notes.append("If we also don't have their first name: " + ln.split(": ", 1)[1] + ".")
        else:
            raise SystemExit("unknown subject line %r in %s" % (ln, e["id"]))
    return ls[0][len("Subject: "):], (" ".join(notes) if notes else None), False


def base_rec(e):
    return OrderedDict([
        ("tag", None), ("kind", None), ("template_id", e["id"]), ("variant", None),
        ("source", source_of(e)), ("approvable", e["approvable"]), ("sha256", e["sha256"]),
    ])


def place_formats(doc):
    """The full value_formats blocks, right after 'How times are written'."""
    for text, tag in VF_TAGS.items():
        lines = text.split("\n")
        dependents = [tid for tid, t in VF_OF.items() if t == tag]
        rec = OrderedDict([("tag", None), ("kind", "value_formats"), ("template_id", None), ("variant", None),
                           ("source", "services/reply_engine/template_approvals.py:value_formats_text"),
                           ("dependents", dependents), ("sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())])
        rec["text"] = doc_text(lines)
        rec["text_group"] = text_group(rec["text"])
        label = ("Exactly how the engine writes times, from its own code "
                 "(part of every email with a time in it):") if len(VF_TAGS) == 1 else (
                 "Exactly how the engine writes times, version %s, from its own code:" % tag.split(".")[1])
        doc.variant_label(label, tag, rec)
        doc.lines(lines)


def place_template(doc, tid, heading, notes=(), spliced_into=None, level=3):
    e = by_id[tid]
    assert e["approvable"], tid
    placed.append(tid)
    subj, subj_note, inline = subject_parts(e)
    body = list(e["main"])
    if inline:
        body = strip_blank(body[1:])
    rec = base_rec(e)
    rec["kind"] = "template_main"
    rec["text"] = doc_text(body)
    rec["template_text"] = "\n".join(e["main"])
    rec["subject_inline"] = inline
    if spliced_into:
        rec["spliced_into"] = spliced_into
    rec["text_group"] = text_group(rec["text"])
    rec["held"] = is_held(tid)
    rec["depends_on"] = [VF_OF[tid]] if tid in VF_OF else []
    doc.email_heading(heading, tid, rec, level=level)
    for n in notes:
        doc.note(n)
    if subj is not None:
        srec = base_rec(e)
        srec["kind"] = "template_subject"
        srec["variant"] = None if inline else "subject"
        srec["subject_inline"] = inline
        if not inline:
            srec["variant_full_text"] = "\n".join(variant(e, "subject")["lines"])
            srec["fixed_fallbacks"] = variant(e, "subject")["lines"][1:]
        doc.subject(tid + "/subject", subj, srec)
        srec["text_group"] = text_group(srec["text"])
        if subj_note:
            doc.note(subj_note)
    doc.lines(body)

    # variants
    shown = {}
    deletion = []
    for v in e["variants"]:
        name = v["name"]
        if name in ("value_formats", "subject"):
            # shown elsewhere: the formats.N block, or the Subject line plus its fallback note
            if name == "subject" and inline:
                raise SystemExit("%s has an inline subject and a subject variant; the variant would not be shown" % tid)
            if name == "value_formats":
                assert VF_OF.get(tid) and VF_TAGS.get("\n".join(v["lines"])) == VF_OF[tid], tid
            skip(name, "covered at the top / Subject block")
            continue
        vl = unsplice(e["main"], v["lines"])
        if name == "missing_lead_data":
            fb = missing_data_explained(e["main"], vl)
            if fb:
                stats["missing_explained"] += 1
                if any("your team" in l for l in v["lines"]):
                    stats["company_fallback_team"].add(tid)
                skip(name, "explained at the top")
                continue
        hs = hunks(e["main"], vl)
        if not hs:
            skip(name, "same as main")
            continue
        examples = vf_examples("\n".join(variant(e, "value_formats")["lines"])) if variant(e, "value_formats") else {}
        if name in ("dated", "lead_in_other_timezone") and all(fill_only(h, examples) for h in hs):
            skip(name, "example values only")
            continue
        if inline and any(h["at"][0] == 0 for h in hs):
            raise SystemExit("variant %s of %s touches the inline subject" % (name, tid))
        new_parts = [strip_blank(h["new"]) for h in hs]
        if not any(new_parts):
            if name in DELETION_NOTES:
                deletion.append((name, hs))
                continue
            raise SystemExit("deletion-only variant %s of %s has no note text" % (name, tid))
        shown[name] = (v, hs, new_parts)
    for v in e["variants"]:
        name = v["name"]
        if name not in shown:
            continue
        v, hs, new_parts = shown[name]
        if name == "no_call_link_or_loom":
            continue
        if name not in VARIANT_LABELS:
            raise SystemExit("no label for variant %s of %s" % (name, tid))
        lines = []
        for i, p in enumerate(new_parts):
            if not p:
                continue
            if lines:
                lines.append("")
            lines.extend(p)
        vrec = base_rec(e)
        vrec["kind"] = "template_variant"
        vrec["variant"] = name
        vrec["variant_desc"] = v["desc"]
        vrec["text"] = doc_text(lines)
        vrec["variant_full_text"] = "\n".join(v["lines"])
        vrec["replaces"] = [{"old": h["old"], "new": h["new"], "main_line_range": h["at"]} for h in hs]
        vrec["text_group"] = text_group(vrec["text"])
        doc.variant_label(VARIANT_LABELS[name], "%s/%s" % (tid, name), vrec)
        doc.lines(lines)
        if name in VARIANT_NOTES:
            doc.note(VARIANT_NOTES[name])
        stats["variants_shown"] += 1
    if "no_call_link_or_loom" in shown:
        # must be exactly no_call_link + no_loom_url
        combo = shown["no_call_link_or_loom"][1]
        parts = []
        if "no_call_link" in shown:
            parts += shown["no_call_link"][1]
        parts += [h for n, hh in deletion if n == "no_loom_url" for h in hh]
        key = lambda h: (tuple(h["old"]), tuple(h["new"]))
        assert sorted(map(key, combo)) == sorted(map(key, parts)), tid
        skip("no_call_link_or_loom", "the two cases above together")
    for name, hs in deletion:
        dropped = [l for h in hs for l in h["old"] if l.strip()]
        assert dropped, (tid, name)
        doc.note_quoting(DELETION_NOTES[name], dropped)
        stats["deletion_notes"] += 1


# ------------------------------------------------------------------ labels
NICHE_OFFER = OrderedDict([
    ("cleaning_reactivation", "cleaning (reactivation)"),
    ("cleaning_trigger", "cleaning (outbound)"),
    ("bookkeeping_reactivation", "bookkeeping (reactivation)"),
    ("bookkeeping_trigger", "bookkeeping (outbound)"),
    ("recruiting_reactivation", "recruiting (reactivation)"),
    ("recruiting_outbound", "recruiting (outbound)"),
])
OFFER_H2 = {
    "cleaning_reactivation": "Cleaning, reactivation offer",
    "cleaning_trigger": "Cleaning, outbound offer",
    "bookkeeping_reactivation": "Bookkeeping, reactivation offer",
    "bookkeeping_trigger": "Bookkeeping, outbound offer",
    "recruiting_reactivation": "Recruiting, reactivation offer",
    "recruiting_outbound": "Recruiting, outbound offer",
}
QT = OrderedDict([
    ("default", "they said yes"),
    ("pricing", "they asked about price"),
    ("send_info", "they asked you to send info"),
    ("mechanism", "they asked how it works"),
    ("other", "they asked something else"),
    ("referral", "they pointed you to someone else"),
])
SR_KEYS = OrderedDict([
    ("cleaning_reactivation", "cleaning (reactivation)"),
    ("cleaning_outbound", "cleaning (outbound)"),
    ("bookkeeping_reactivation", "bookkeeping (reactivation)"),
    ("bookkeeping_outbound", "bookkeeping (outbound)"),
    ("recruiting_reactivation", "recruiting (reactivation)"),
    ("recruiting_outbound", "recruiting (outbound)"),
    ("generic_reactivation", "any other niche (reactivation)"),
    ("generic_outbound", "any other niche (outbound)"),
])
CAMPAIGN_KEYS = {
    "2026 Cleaning - Client Reactivation": "cleaning_reactivation",
    "2026 Cleaning - Trigger Outbound": "cleaning_trigger",
    "2026 Bookkeeping - Client Reactivation": "bookkeeping_reactivation",
    "2026 Bookkeeping - Trigger Outbound": "bookkeeping_trigger",
    "2026 Recruiting - Client Reactivation": "recruiting_reactivation",
    "2026 Recruiting - Outbound (specialty roles)": "recruiting_outbound",
}
TZ_NAMES = {"America/Detroit": "Eastern", "America/Chicago": "Central", "America/New_York": "Eastern"}

# ------------------------------------------------------------------ html -> text for Instantly bodies
from html.parser import HTMLParser


class _Div2Text(HTMLParser):
    """Instantly stores each line as a <div>. <div><br /></div> is an empty
    line, a <br /> inside a div breaks the line, and a trailing <br /> adds
    nothing (as a browser renders it)."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.lines = []
        self.segs = None
        self.cur = None

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            self._flush()
            self.segs, self.cur = [], ""
        elif tag == "br":
            if self.segs is None:
                self.segs, self.cur = [], ""
            self.segs.append(self.cur)
            self.cur = ""

    def handle_endtag(self, tag):
        if tag == "div":
            self._flush()

    def handle_data(self, d):
        if self.segs is None:
            self.segs, self.cur = [], ""
        self.cur += d

    def _flush(self):
        if self.segs is None:
            return
        segs = self.segs + [self.cur]
        if len(segs) > 1 and segs[-1] == "":
            segs.pop()
        self.lines.extend(segs)
        self.segs, self.cur = None, None

    def result(self):
        self._flush()
        return self.lines


def ampm(hhmm):
    h, m = [int(x) for x in hhmm.split(":")]
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return ("%d%s" % (h12, suffix)) if m == 0 else ("%d:%02d%s" % (h12, m, suffix))


def instantly_body_lines(raw):
    p = _Div2Text()
    p.feed(raw)
    lines = p.result()
    # display text: non-breaking spaces become spaces, trailing space dropped
    return [l.replace(" ", " ").rstrip() for l in lines]


# ------------------------------------------------------------------ build
doc = Doc()
doc.raw('<html><head><meta charset="utf-8"><title>Every email the system sends</title></head>'
        '<body style="font-family:Arial,sans-serif;font-size:11pt">')

# ---- top
doc.title("Every email the system sends")
doc.top_p("Every email and text the system sends, in the order a lead meets them.")
doc.top_p("How to use it: Change any words you like. Keep the words in {curly brackets}: they are filled in for "
          "each lead. When you are done, tell Claude 'done'. Nothing goes live until you say so.")
doc.top_p("When you say 'done', everything in this doc counts as approved. Emails still only go out after you "
          "tell Claude 'go live'.")
doc.top_p("If a sentence appears in many emails (like the time-offer line in first replies), changing it once is "
          "enough; it changes everywhere. If you change two copies differently, Claude will ask.")
doc.top_p("Leave the small grey tags at the end of each heading as they are: they tell Claude which email is which. "
          "Grey lines marked note or section are only there to help you read.")
doc.top_p("Words in brackets: {first_name} their first name, {company} their company, {slots} two open times, "
          "{slot} one time, {booking_url} your booking link, {zoom_link} the call link, {loom_url} your Loom video, "
          "{original_subject} the subject of their email. The cold emails use Instantly's double brackets, like "
          "{{firstName}}.")
doc.top_p("If we don't have their first name, 'Hey {first_name},' becomes 'Hey there,'. If we don't have their "
          "company name, {company} becomes 'your business' ('your team' in the Day 2, 4, 5 and 30 follow-ups). In a "
          "referral reply with no name, {referral_name} becomes 'the right person' and {referral_first_name} "
          "becomes 'them'.")
doc.top_h2("How times are written")
doc.top_p("Every time is Central (CT). The engine writes them like this:")
for ln in (
        "{slots}: Tue 12:05pm or Thu 4:30pm CT (just Tue 12:05pm CT when only one time is free)",
        "{slot}: Tue 12:05pm (the email adds CT after it)",
        "{slot1} and {slot2}: Tue 12:05pm CT",
        "{when_ct}: Tue, Jan 8 at 12:05pm CT, and in another timezone Tue, Jan 8 at 12:05pm CT (1:05pm ET)",
        "{time_ct}: 12:05pm CT",
        "{asked_time}: the time they asked for, in their own zone, like Mon 10:45am ET",
        "{lead_local_time}: their own time, like 1:05pm ET (only added when they are not on Central)",
        "{alt_slots}: like {slots}; when the times are in another week the dates are added, like Tue Jan 15 12:05pm or Thu Jan 17 4:30pm CT",
        "Zones are written CT, ET, MT, PT, and MST for Arizona."):
    doc.top_p(ln)
place_formats(doc)
doc.build_line("Doc build:", doc_areas.BUILD_TAG)
_brec = OrderedDict([("tag", None), ("kind", "build"), ("template_id", None), ("variant", None),
                     ("source", "build.py"), ("text", "")])
_brec["tag"] = doc_areas.BUILD_TAG
doc._record(_brec)

# ---- 1. Instantly
snap = json.load(open(SNAPSHOT, encoding="utf-8"))
camps = {CAMPAIGN_KEYS[c["name"]]: c for c in snap["items"]}
assert len(camps) == 6
doc.section(1, "Cold emails in Instantly (live copy, checked 2026-09-23)")
doc.note("Instantly sends these. Step 2 goes out 3 days after step 1, in the same email thread, and only if they "
         "haven't replied. {{personalization}} is the opening line written for each lead.")
instantly_steps = 0
for key in NICHE_OFFER:
    c = camps[key]
    sched = c["campaign_schedule"]["schedules"][0]
    doc.section(2, OFFER_H2[key])
    frm, to = sched["timing"]["from"], sched["timing"]["to"]
    doc.note("Campaign: %s. Sends between %s and %s %s time." % (c["name"], ampm(frm), ampm(to),
                                                                 TZ_NAMES[sched["timezone"]]))
    steps = c["sequences"][0]["steps"]
    assert len(steps) == 2 and all(len(s["variants"]) == 1 for s in steps)
    for i, st in enumerate(steps, 1):
        v = st["variants"][0]
        base = "instantly.%s.step%d" % (key, i)
        common = OrderedDict([("campaign_id", c["id"]), ("campaign_name", c["name"]), ("step", i),
                              ("variant_index", 0), ("source", SNAPSHOT_REL)])
        lines = instantly_body_lines(v["body"])
        rec = OrderedDict([("tag", None), ("kind", "instantly_step"), ("field", "body")])
        rec.update(common)
        rec["delay"] = st.get("delay")
        rec["delay_unit"] = st.get("delay_unit")
        rec["text"] = doc_text(lines)
        rec["raw_html"] = v["body"]
        rec["text_group"] = text_group(rec["text"])
        if i == 1:
            heading = "Step 1: first email"
        else:
            prev = steps[i - 2]
            heading = "Step 2: %d %s later, if they haven't replied" % (prev["delay"], prev["delay_unit"])
        doc.email_heading(heading, base, rec)
        srec = OrderedDict([("tag", None), ("kind", "instantly_step"), ("field", "subject")])
        srec.update(common)
        srec["raw_subject"] = v["subject"]
        doc.subject(base + "/subject", v["subject"], srec)
        srec["text_group"] = text_group(srec["text"])
        if not v["subject"]:
            doc.note("No subject of its own: it goes as a reply in the same thread.")
        doc.lines(lines)
        instantly_steps += 1

# ---- 2. First replies
doc.section(1, "First reply when a lead replies interested")
doc.note("Goes out when a lead answers a cold email and sounds interested or asks a question. The version depends "
         "on their offer and what they asked. Replies only go out between 7am and 7pm Central.")
for key, label in NICHE_OFFER.items():
    doc.section(2, OFFER_H2[key])
    for qt, qlabel in QT.items():
        tid = "first_reply.%s.%s.full" % (key, qt)
        notes = []
        if is_held(tid):
            notes.append(HELD_NOTE)
        place_template(doc, tid, "First reply: %s, %s" % (label, qlabel), notes)

# ---- 3. Cadence
doc.section(1, "Daily follow-up sequence (day 1 to day 30)")
doc.note("Starts the business day after your first reply goes out. Each one goes at 10am Central on a business day "
         "and offers fresh times. It stops as soon as the lead books, replies or asks to stop.")
CAD = [
    ("cadence.d1", "Day 1 follow-up",
     ["Day 1: the business day after your first reply, if they haven't booked or replied. You get a 9:30am heads-up with a Veto button first."]),
    ("cadence.d2", "Day 2 follow-up",
     ["Day 2: 2 business days after your first reply, if they haven't booked or replied.",
      "{research_line} is one of the two lines right below this email, picked by offer."]),
    ("cadence.d3", "Day 3 follow-up",
     ["Day 3: 3 business days after your first reply, if they haven't booked or replied."]),
    ("cadence.d4", "Day 4 follow-up",
     ["Day 4: 4 business days after your first reply, if they haven't booked or replied.",
      "{case_study} is one of the two lines right below this email, picked by offer."]),
    ("cadence.d5", "Day 5 follow-up",
     ["Day 5: 5 business days after your first reply, if they haven't booked or replied.",
      "{free_work} is one of the lines right below this email, picked by niche and offer."]),
    ("cadence.d6_noinvite", "Day 6 follow-up",
     ["Day 6: 6 business days after your first reply, if they haven't booked or replied. This is the Day 6 that goes out today."]),
    ("cadence.d6", "Day 6 follow-up, calendar hold version (off for now)",
     ["Only used if the Day 6 calendar hold is turned on, and then each one needs your OK first."]),
    ("cadence.d7", "Day 7 follow-up",
     ["Day 7: 7 business days after your first reply, if they haven't booked or replied. No times offered."]),
    ("cadence.d14", "Day 14 follow-up",
     ["Day 14: one week after Day 7, if they still haven't booked or replied."]),
    ("cadence.d30", "Day 30 follow-up",
     ["Day 30: 16 days after Day 14. After this the lead stays in Follow Up Later."]),
]
SPLICE_NOTES = {
    "cadence.d2": "The engine uses this fixed line by default. A line written per lead by AI is never sent on its own; that day would be held.",
}
spliced_count = 0
for tid, heading, notes in CAD:
    place_template(doc, tid, heading, notes)
    for fid, fh in SPLICED.get(tid, []):
        n = [SPLICE_NOTES[tid]] if tid in SPLICE_NOTES and fid.endswith("reactivation") else []
        place_template(doc, fid, fh, n, spliced_into=tid, level=4)
        spliced_count += 1

# ---- 4. Booking
doc.section(1, "Booking emails")
doc.note("These go out when a lead replies about a time for the call.")
BOOK = [
    ("booking.confirmation.zoom_link", "Booking confirmation, with Zoom link",
     ["When they pick a time that works, the call is booked and this goes out. Used when the call has a Zoom link."]),
    ("booking.confirmation.no_zoom_link", "Booking confirmation, no Zoom link",
     ["Same moment, when the call has no Zoom link yet (the calendar invite carries the video link)."]),
    ("booking.counter.window_no_fit", "Other times: nothing free in their window",
     ["When they give a window, like Tuesday afternoon, and nothing in it is free."]),
    ("booking.counter.outside_window_early", "Other times: too early",
     ["When the time they ask for is before your first slot of the day (noon Central)."]),
    ("booking.counter.outside_window_late", "Other times: too late",
     ["When the time they ask for is after your last slot of the day."]),
    ("booking.counter.weekend", "Other times: weekend",
     ["When the time they ask for is on a weekend."]),
    ("booking.counter.too_soon", "Other times: too soon",
     ["When the time they ask for is less than 4 hours away."]),
    ("booking.counter.beyond_horizon", "Other times: too far out",
     ["When the time they ask for is more than 5 business days out."]),
    ("booking.counter.slot_taken", "Other times: already taken",
     ["When the time they ask for is already taken on your calendar."]),
    ("booking.slot_already_taken", "Their time filled up before the booking went through",
     ["When the time they picked got taken between your offer and the booking. Always comes to you as a card first."]),
    ("booking.already_booked.awaiting_approval", "Already booked, confirmation not sent yet",
     ["When a lead with a call booked writes again before your confirmation to them has gone out."]),
    ("booking.already_booked.invite_withheld", "Already booked, invite not sent",
     ["When a lead with a call booked writes again and the calendar invite did not go out."]),
    ("booking.already_booked.invite_on_calendar", "Already booked, invite on their calendar",
     ["When a lead with a call booked writes again and the invite is on their calendar."]),
]
for tid, heading, notes in BOOK:
    n = list(notes)
    if tid in ("booking.counter.outside_window_early",):
        n.append("For a time your rules don't allow (too early, too late, weekend, too soon, too far out), the reply "
                 "comes to you as a card first, so you can book it anyway or send this.")
    place_template(doc, tid, heading, n)

# ---- 5. Show-rate
doc.section(1, "Show-rate messages (confirmation, pre-read, reminders)")
doc.note("These go to every lead with a call on your calendar, however they booked. Texts only go out once your "
         "texting number is registered (A2P); until then they are skipped.")
for k, lab in SR_KEYS.items():
    n = ["Right after the call is booked. Skipped when the lead booked by replying and your Locked in email "
         "already went out unchanged."]
    place_template(doc, "show_rate.confirm_email.%s" % k, "Call confirmation email: %s" % lab, n)
place_template(doc, "show_rate.confirm_sms", "Call confirmation text",
               ["Right after the call is booked, with the confirmation email."])
for k, lab in SR_KEYS.items():
    n = ["15 minutes after the call is booked."]
    place_template(doc, "show_rate.preread_email.%s" % k, "Pre-read email: %s" % lab, n)
place_template(doc, "show_rate.reminder_24h_sms", "Reminder text, 24 hours before", ["24 hours before the call."])
place_template(doc, "show_rate.reminder_24h_email", "Reminder email, 24 hours before",
               ["24 hours before the call.",
                "If they haven't replied C by 4 hours before the call, you get a task to text them yourself."])
place_template(doc, "show_rate.reminder_1h_sms", "Reminder text, 1 hour before", ["1 hour before the call."])
place_template(doc, "show_rate.reminder_15m_sms", "Reminder text, 15 minutes before", ["15 minutes before the call."])

# ---- 6. No-show
doc.section(1, "No-show recovery")
doc.note("These start when a lead misses the call. The engine can only tell from Zoom join data; until Zoom is "
         "connected you get a task to mark it by hand. A second no-show gets only the first three messages. A "
         "third gets only the two Still on messages, and the lead moves to Lost.")
place_template(doc, "no_show.ns_still_on_sms", "Still on? text",
               ["About 15 minutes after the start time, if they haven't joined."])
place_template(doc, "no_show.ns_still_on_email", "Still on? email",
               ["Same time as the text. 10 minutes later you get a task to call them, with a voicemail script."])
place_template(doc, "no_show.ns_reschedule_email", "Missed you email",
               ["1 hour after the no-show."])
place_template(doc, "no_show.ns_reschedule_email.repeat", "Missed you email, second no-show",
               ["Used instead of the one above the second time the same lead misses a call."])
place_template(doc, "no_show.ns_d1_other_channel", "Day 1 text after a no-show",
               ["1 day after the no-show. If texting isn't set up yet, you get a task to text or LinkedIn them yourself instead."])
for k, lab in SR_KEYS.items():
    n = ["3 days after the no-show."]
    place_template(doc, "no_show.ns_d3_value_email.%s" % k, "Day 3 email after a no-show: %s" % lab, n)
place_template(doc, "no_show.ns_d7_yes_no_email", "Day 7 email after a no-show", ["7 days after the no-show."])
place_template(doc, "no_show.ns_d14_breakup_email", "Day 14 email after a no-show",
               ["14 days after the no-show. After this the lead moves to Follow Up Later."])

# ---- 7. Upwork pricing
doc.section(1, "Upwork pricing lines")
doc.note("Your Upwork follow-up drafts can only quote a price that is written here. Right now there is none, so "
         "drafts never state a price. Write one price per box, the way you would say it to a client. Leave a box "
         "empty if you don't need it.")
UPWORK_BOXES = 3
for i in range(1, UPWORK_BOXES + 1):
    rec = OrderedDict([("tag", None), ("kind", "upwork_pricing"), ("template_id", None), ("variant", None),
                       ("source", "config/upwork_offers.md (## Pricing)"), ("text", ""), ("box", i)])
    doc.box("Pricing line %d" % i, "U-PRICE-%d" % i, rec)
    rec["text_group"] = text_group("")

# ---- 8. After you finish
AFTER = [
    "1. Tell Claude \"done\". Claude reads this doc, puts your wording into the system and tests it. It then shows "
    "you any line a send check would stop, for example an exclamation mark or a price that is not on your offer sheet.",
    "2. Nothing goes live until you tell Claude \"go live\".",
    "3. Only you can do these, whenever you have a minute: change the passwords and keys that were saved in the code, "
    "register your texting number (A2P), and connect Zoom in GoHighLevel (optional; Google Meet works today).",
    "4. Say \"yes\" to Claude for any of these and Claude does them: create the Upwork pipeline in GoHighLevel, start "
    "the 8:30 Upwork morning drafts, and send test alerts to your phone during the test week.",
]
rec = OrderedDict([("tag", None), ("kind", "after"), ("template_id", None), ("variant", None),
                   ("source", "coordinator text, 2026-09-23"), ("text", "\n".join(AFTER))])
doc.email_heading("After you finish", "X-AFTER", rec, level=1)
rec["text_group"] = text_group(rec["text"])
for p in AFTER:
    doc.raw('<p>%s</p>' % esc(p))

doc.raw("</body></html>")

# ------------------------------------------------------------------ checks
missing = [i for i in approvable_ids if i not in placed]
extra = [i for i in placed if placed.count(i) > 1]
assert not missing, missing
assert not extra, extra
bad = [s for s in AUTHORED if re.search(u"[–—!]", s)]
assert not bad, bad
# 'your team' claim at the top must match the templates
team_days = sorted(stats["company_fallback_team"])
assert team_days == ["cadence.d2", "cadence.d30", "cadence.d4", "cadence.d5"], team_days

html_out = re.sub(r"(</(?:p|h[1-4]|li|tr|table)>)", r"\1\n", "".join(doc.parts))

# the doc as Drive's text export gives it: its block bodies must read back as
# the manifest texts exactly, and its other lines are the build's area lines
from diff_doc import diff as _diff, is_clean as _is_clean  # noqa: E402
from parse_doc import parse_with_info as _parse  # noqa: E402

plain = doc_areas.html_string_to_text(html_out)
_info = _parse(plain)
_rt = _diff(_info, {"blocks": doc.manifest})
assert _is_clean(_rt), dict((k, _rt[k]) for k in ("changed", "missing", "unknown", "duplicates"))
assert all(_info["blocks"].get(r["tag"]) == r["text"] for r in doc.manifest), "round trip is not exact"
visible = doc_areas.area_pairs(plain)
FINGERPRINT = doc_areas.fingerprint(doc.manifest, visible)
assert html_out.count(doc_areas.FP_PLACEHOLDER) == 1
html_out = html_out.replace(doc_areas.FP_PLACEHOLDER, FINGERPRINT)
assert doc_areas.read_fingerprint(doc_areas.html_string_to_text(html_out)) == (FINGERPRINT, None)

if OUT_DIR is None:
    OUT_DIR = os.path.join(BUILDS_DIR, FINGERPRINT)
OUT_HTML = os.path.join(OUT_DIR, HTML_NAME)
OUT_MANIFEST = os.path.join(OUT_DIR, MANIFEST_NAME)
if not os.path.isdir(OUT_DIR):
    os.makedirs(OUT_DIR)
open(OUT_HTML, "w", encoding="utf-8").write(html_out)

try:
    head = subprocess.check_output(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                                   stderr=subprocess.DEVNULL).decode().strip()
except Exception:  # noqa: BLE001
    head = None
manifest = OrderedDict([
    ("doc", os.path.basename(OUT_HTML)),
    ("fingerprint", FINGERPRINT),
    ("repo_head", head),
    ("export", os.path.basename(EXPORT)),
    ("export_sha256", export_sha),
    ("export_counts", data["counts"]),
    ("snapshot", SNAPSHOT_REL),
    ("parser_rules", __doc__.split("Parser contract")[1].strip()),
    ("text_note", "text is the block as parse_doc returns it from the plain-text export (blank edges stripped, "
                  "lines right-stripped). Compare with diff_doc.norm, which also ignores blank lines, runs of "
                  "spaces, curly quotes and non-breaking spaces. visible is every line outside block bodies "
                  "as [area, doc_areas.canon(line)] (see doc_areas.py); the fingerprint covers blocks and visible."),
    ("blocks", doc.manifest),
    ("visible", visible),
])
json.dump(manifest, open(OUT_MANIFEST, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

kinds = {}
for r in doc.manifest:
    kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
emails = sum(1 for r in doc.manifest if r["kind"] in ("template_main", "instantly_step") and r.get("field", "body") == "body"
             and not r.get("spliced_into"))
print("wrote", OUT_HTML, os.path.getsize(OUT_HTML), "bytes")
print("wrote", OUT_MANIFEST)
print("fingerprint:", FINGERPRINT)
print("blocks by kind:", kinds)
print("emails (bodies, not counting spliced lines):", emails)
print("spliced lines (approvable, kind template_main):", spliced_count)
print("variant blocks:", stats["variants_shown"], "deletion notes:", stats["deletion_notes"])
print("missing_lead_data explained at top:", stats["missing_explained"])
print("variants skipped:")
for k, v in sorted(stats["variants_skipped"].items()):
    print("  %4d  %s" % (v, k))
print("instantly steps:", instantly_steps)
print("not placed (not approvable):", [e["id"] for e in entries if not e["approvable"] and not e["id"].startswith("first_reply.")],
      "+", sum(1 for e in entries if not e["approvable"] and e["id"].startswith("first_reply.")), "first_reply reference pieces")
