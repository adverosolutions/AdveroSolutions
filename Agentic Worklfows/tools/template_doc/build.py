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
code change to any of it changes the doc: the main text; each version
(variant) as the changes it makes to the main text, every change a grey note
quoting the main-text lines it replaces or leaves out (or the line it adds
after or before), followed by the lines it puts in (doc_rules, "variants");
the dated and other-timezone versions that write out example times in full,
example times and all (Lorenzo's choice, 2026-09-23); a version is left out
only when it is exactly the missing-data fallbacks the top section states, a
version that is exactly two others together is one note, and one the change
forms cannot say exactly is shown in full too; the subject line and its
fallbacks (a note); and the full value_formats block (one tagged block per
distinct text, formats.N, and a note on each email when there is more than
one). A cadence day whose versions write a spliced line out in full says
which line (a note).

Before writing anything, the build reads every template back out of the
doc's own text with doc_areas.DocReader (main text, subject, every version,
time formats) and stops (exit 1, nothing written) unless each part equals
the export's text as the hash normalises it. So two different hashed texts
can never produce the same doc.

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
import doc_rules
from doc_rules import (COMBOS, COMPANY_FALLBACK, EXAMPLE_TIMES_NOTE, GREETING, HELD_NOTE, PIN_NOTE,
                       REFERRAL_FALLBACKS, SAME_AS_MAIN, TIME_VALUE_RE, VF_VERSION_NOTE, WHOLE_NOTE, fill_missing,
                       is_held, norm_lines, section_of)
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

    def note_quoting(self, text, wording):
        """A note that quotes template text. Only its fixed wording is
        authored (checked for dashes and "!"); the quoted lines are the
        templates' own."""
        AUTHORED.append(wording)
        self.raw('<p><span style="%s">%s</span> %s</p>' % (S_NOTE, esc(text), marker_span("note")))

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
APPROVABLE = set(approvable_ids)
# The layout below follows whatever the catalogue holds; the one count check
# is that the doc places every approvable id of the export (see "checks").
assert len(approvable_ids) == data["counts"]["approvable"], (len(approvable_ids), data["counts"])
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

# Spliced lines, from the catalogue: an approvable cadence email
# "cadence.<name>" and the lines "cadence.<name>.<family>.<key>" the engine
# puts in for one of its placeholders (doc_rules.splice_host). A line that is
# not approvable (written per lead by AI) is shown for reading only.
SPLICE_NOTE_RE = r"(\{[A-Za-z_][A-Za-z0-9_]*\}) is %s\."


def fragment_texts(ids):
    """The one-line texts of spliced lines (an empty or longer one matches
    nothing: a version then shows the text it writes out as an ordinary change)."""
    return [by_id[i]["main"][0] for i in ids if len(by_id[i]["main"]) == 1 and by_id[i]["main"][0].strip()]


def host_placeholder(host, family, ids):
    """The placeholder of the host the family's lines fill: as the catalogue's
    note on the host names it ("{offer_proof} is cadence.e4.offer_proof.<offer>"),
    else the one placeholder that, replaced by one of the lines, gives a line of
    one of the host's versions; None when neither says."""
    e = by_id[host]
    m = re.search(SPLICE_NOTE_RE % re.escape(host + "." + family), e["meta"].get("notes", ""))
    if m and any(m.group(1) in l for l in e["main"]):
        return m.group(1)
    found = set()
    for l in e["main"]:
        for ph in PH_RE.findall(l):
            for t in fragment_texts(ids):
                if any(l.replace(ph, t) in vl for v in e["variants"] for vl in v["lines"]):
                    found.add(ph)
    return found.pop() if len(found) == 1 else None


SPLICE = OrderedDict()  # host -> OrderedDict(family -> {"placeholder": str or None, "ids": [approvable ids]})
READ_ONLY = OrderedDict()  # host -> [entries spliced into it that are not approvable]
for _e in entries:
    _host = doc_rules.splice_host(_e["id"], APPROVABLE)
    if not _host:
        continue
    if _e["approvable"]:
        _fam = SPLICE.setdefault(_host, OrderedDict()).setdefault(_e["id"].split(".")[2],
                                                                  {"placeholder": None, "ids": []})
        _fam["ids"].append(_e["id"])
    else:
        READ_ONLY.setdefault(_host, []).append(_e)
for _host, _fams in SPLICE.items():
    for _family, _f in _fams.items():
        _f["placeholder"] = host_placeholder(_host, _family, _f["ids"])
NOT_VERSIONS = ("value_formats", "subject")  # shown as the formats.N block and the Subject line


def pinned_fragment(e):
    """(placeholder, line) when the versions of a cadence email write one of
    its spliced lines out in full (the catalogue renders them for one niche
    and offer), else None. It must be one line for every version: the doc
    names it, and DocReader puts it back where the placeholder is. When the
    versions write out more than one, none is pinned and they show as changes."""
    found = []
    for fam in SPLICE.get(e["id"], {}).values():
        ph = fam["placeholder"]
        if not ph or not any(ph in m for m in e["main"]):
            continue
        for v in e["variants"]:
            if v["name"] in NOT_VERSIONS:
                continue
            for fr in fragment_texts(fam["ids"]):
                forms = [fr, fr.replace("{company}", COMPANY_FALLBACK)]
                if any(f in l for l in v["lines"] for f in forms) and (ph, fr) not in found:
                    found.append((ph, fr))
    found = [p for p in found if not any(p != q and p[1] in q[1] for q in found)]
    return found[0] if len(found) == 1 else None


def unsplice(lines, pin):
    """The pinned spliced line back to its placeholder (as the main text has it)."""
    return [l.replace(pin[1], pin[0]) for l in lines] if pin else list(lines)


def resplice(lines, pin):
    return [l.replace(pin[0], pin[1]) for l in lines] if pin else list(lines)


def names_company(e, pin):
    return any("{company}" in l for l in resplice(e["main"], pin))


def keeps_company(e, pin):
    """None when the email has no {company} or no missing_lead_data version;
    else False when that version writes the company fallback in its place,
    and True when it does not (the email is held without a company)."""
    v = variant(e, "missing_lead_data")
    if not v or not names_company(e, pin):
        return None
    return sum(l.count(COMPANY_FALLBACK) for l in v["lines"]) <= sum(l.count(COMPANY_FALLBACK)
                                                                   for l in resplice(e["main"], pin))


# The top section says a follow-up email that names the company is held until
# we have it (doc_rules.COMPANY_KEPT_CLAUSE) when the catalogue's follow-ups
# keep {company}; it must then be true of every one of them.
_kept = [(t, keeps_company(by_id[t], pinned_fragment(by_id[t]))) for t in approvable_ids
         if section_of(t) == doc_rules.COMPANY_KEPT_SECTION]
COMPANY_KEPT = any(k for _, k in _kept)
if COMPANY_KEPT and any(k is False for _, k in _kept):
    raise SystemExit("the top section would say a follow-up email that names the company is held until we have "
                     "it, and %s writes a fallback instead" % ", ".join(t for t, k in _kept if k is False))


def missing_explained(tid, main, vlines, pin):
    """True when the missing_lead_data version is exactly the main text with
    the fallbacks the top section states."""
    company = doc_rules.company_for(tid, COMPANY_FALLBACK, COMPANY_KEPT)
    return norm_lines(fill_missing(resplice(main, pin), GREETING, company, REFERRAL_FALLBACKS)) == vlines


def variant_changes(M, V):
    """A version as changes to the main text: [(kind, quoted lines, new
    lines)] in doc_rules' forms. M and V are normalised line lists (blank lines
    kept, single). The diff runs over the non-blank lines; the lines a change
    puts in are the version's own, blank lines between them included. Whether
    DocReader reads V back exactly is checked on the whole doc at the end
    (quoted lines may hold double quotes: DocReader finds them by writing
    candidate lines of the text the same way, not by splitting the note)."""
    pm = [i for i, l in enumerate(M) if l]
    pv = [j for j, l in enumerate(V) if l]
    a, b = [M[i] for i in pm], [V[j] for j in pv]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        new = V[pv[j1]:pv[j2 - 1] + 1] if j2 > j1 else []
        if i2 > i1:
            out.append(("instead" if new else "leaves", a[i1:i2], new))
            continue
        first, last = pv[j1], pv[j2 - 1]
        blank_before = first > 0 and V[first - 1] == ""
        blank_after = last + 1 < len(V) and V[last + 1] == ""
        if i1 == 0:
            out.append(("start_para" if blank_after else "start", [], new))
        elif not blank_before:
            out.append(("after", [a[i1 - 1]], new))
        elif i1 < len(a) and not blank_after:
            out.append(("before", [a[i1]], new))
        else:
            out.append(("after_para", [a[i1 - 1]], new))
    return out


def as_read(changes):
    """The changes as DocReader reads them back: [(kind, note, new lines)]."""
    return [(kind, doc_rules.change_note(kind, quoted), new) for kind, quoted, new in changes]


def reads_back(M, changes, V, pin):
    """True when DocReader, applying these changes to the main text, gets V."""
    try:
        return norm_lines(resplice(doc_areas.apply_changes(M, as_read(changes)), pin)) == V
    except doc_areas.DocError:
        return False


def combo_matches(name, M, V, pin, rendered):
    """True when a COMBOS version is exactly its two parts' changes together."""
    parts, _ = COMBOS[name]
    lines = list(M)
    try:
        for p in parts:
            if p not in rendered:
                return False
            lines = doc_areas.apply_changes(lines, rendered[p])
    except doc_areas.DocError:
        return False
    return norm_lines(resplice(lines, pin)) == V


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
    "no_call_link_or_loom": "If there is no call link and no Loom link:",
}
def variant_label(v):
    """The label of a version: VARIANT_LABELS, else one made from the
    catalogue's own description of it."""
    if v["name"] in VARIANT_LABELS:
        return VARIANT_LABELS[v["name"]]
    desc = (v.get("desc") or "").strip()
    if desc and not re.search(u"[\u2013\u2014!]", desc):
        return "If %s:" % desc
    return "Version %s:" % v["name"].replace("_", " ")


def time_version(M, V):
    """A version that writes out example times its main text does not have
    (the dated and other-timezone versions). These are shown in full
    (Lorenzo, 2026-09-23: "the 25 time/timezone versions shown in full"), so
    every hour, date and zone label is read in its email."""
    return any(TIME_VALUE_RE.search(l) for l in V) and not any(TIME_VALUE_RE.search(l) for l in M)


stats = {"variants_shown": 0, "variants_skipped": {}, "changes": {}, "missing_explained": 0,
         "combos_as_note": 0, "same_as_main": 0, "in_full": 0, "times_in_full": 0, "pinned": 0}
placed = []


def skip(name, why):
    stats["variants_skipped"].setdefault(name + ": " + why, 0)
    stats["variants_skipped"][name + ": " + why] += 1


def subject_parts(e):
    """(subject text, fallback note or None, inline) for an entry."""
    main = e["main"]
    if main and main[0].startswith(doc_rules.SUBJECT_PREFIX):
        return main[0][len(doc_rules.SUBJECT_PREFIX):], None, True
    v = variant(e, "subject")
    if not v:
        return None, None, False
    ls = v["lines"]
    if not ls or not ls[0].startswith(doc_rules.SUBJECT_PREFIX):
        raise SystemExit("the subject variant of %s does not start with a Subject line" % e["id"])
    if len(ls) < 2:
        raise SystemExit("the subject variant of %s has no fallback line; the doc would show it as part of "
                         "the main text" % e["id"])
    try:
        note = doc_rules.subject_note(ls[1:])
    except ValueError as exc:
        raise SystemExit("%s in %s" % (exc, e["id"]))
    return ls[0][len(doc_rules.SUBJECT_PREFIX):], note, False


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
    if inline and variant(e, "subject"):
        raise SystemExit("%s has an inline subject and a subject variant; the variant would not be shown" % tid)
    body = list(e["main"])
    if inline:
        body = strip_blank(body[1:])
    pin = pinned_fragment(e)
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
    if pin:
        rec["pinned_line"] = OrderedDict([("placeholder", pin[0]), ("line", pin[1])])
    doc.email_heading(heading, tid, rec, level=level)
    for n in notes:
        doc.note(n)
    if pin:
        doc.note_quoting(PIN_NOTE % pin, PIN_NOTE % ("", ""))
        stats["pinned"] += 1
    if tid in VF_OF and len(VF_TAGS) > 1:
        doc.note(VF_VERSION_NOTE % int(VF_OF[tid].split(".")[1]))
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
            doc.note_quoting(subj_note, " ".join(d for _, d in doc_rules.SUBJECT_FALLBACKS))
    doc.lines(body)

    # versions, in the catalogue's order
    M = norm_lines(e["main"])
    rendered = {}  # name -> its changes as DocReader reads them
    for v in e["variants"]:
        name = v["name"]
        if name in NOT_VERSIONS:
            if name == "value_formats":
                assert VF_OF.get(tid) and VF_TAGS.get("\n".join(v["lines"])) == VF_OF[tid], tid
            skip(name, "the formats.N block / the Subject line and its note")
            continue
        V = norm_lines(v["lines"])
        if name == "missing_lead_data" and missing_explained(tid, e["main"], V, pin):
            stats["missing_explained"] += 1
            skip(name, "the fallbacks the top section states")
            continue
        special = None
        changes = []
        whole = []
        if name in COMBOS and combo_matches(name, M, V, pin, rendered):
            special = COMBOS[name][1]
            stats["combos_as_note"] += 1
        elif time_version(M, V):
            special, whole = WHOLE_NOTE, unsplice(V, pin)
            stats["times_in_full"] += 1
        else:
            changes = variant_changes(M, unsplice(V, pin))
            if not changes:
                special = SAME_AS_MAIN
                stats["same_as_main"] += 1
            elif not reads_back(M, changes, V, pin):
                # the change forms cannot say this one exactly: show it in full
                special, changes, whole = WHOLE_NOTE, [], unsplice(V, pin)
                stats["in_full"] += 1
        if special in (None, SAME_AS_MAIN):
            rendered[name] = as_read(changes)
        new_lines = whole + [l for _, _, new in changes for l in new]
        vrec = base_rec(e)
        vrec["kind"] = "template_variant"
        vrec["variant"] = name
        vrec["variant_desc"] = v["desc"]
        vrec["text"] = doc_text(new_lines)
        vrec["variant_full_text"] = "\n".join(v["lines"])
        vrec["changes"] = [OrderedDict([("kind", kind), ("quoted", quoted), ("new", new)])
                           for kind, quoted, new in changes]
        if special:
            vrec["note"] = special
        # an empty body is not "the same text" as other empty bodies
        vrec["text_group"] = text_group(vrec["text"]) if vrec["text"].strip() else text_group("empty:" + tid + "/" + name)
        doc.variant_label(variant_label(v), "%s/%s" % (tid, name), vrec)
        if special == WHOLE_NOTE and time_version(M, V):
            doc.note(EXAMPLE_TIMES_NOTE)
        if special:
            doc.note(special)
        doc.lines(whole)
        for kind, quoted, new in changes:
            doc.note_quoting(doc_rules.change_note(kind, quoted), doc_rules.CHANGE_FORMS[kind] % (("",) * doc_rules.CHANGE_FORMS[kind].count("%s")))
            doc.lines(new)
            stats["changes"][kind] = stats["changes"].get(kind, 0) + 1
        stats["variants_shown"] += 1


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
doc.top_p("Other versions of an email, like 'If there are no free times:', show what they change: a grey line quotes "
          "the lines of the email above that they replace or leave out, and the lines under it are the new ones. "
          "The versions with example dates and times are written out in full.")
doc.top_p("Words in brackets: {first_name} their first name, {company} their company, {slots} two open times, "
          "{slot} one time, {booking_url} your booking link, {zoom_link} the call link, {loom_url} your Loom video, "
          "{original_subject} the subject of their email. The cold emails use Instantly's double brackets, like "
          "{{firstName}}.")
doc.top_p(doc_rules.missing_data_sentence())
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
# the top section's 'your team' claim must hold for the days it names
for _tid in TEAM_IDS:
    _v = variant(by_id[_tid], "missing_lead_data")
    if not _v or not any(COMPANY_FALLBACK_TEAM in l for l in _v["lines"]):
        raise SystemExit("the top section says %s writes '%s' when the company is missing, and it does not"
                         % (_tid, COMPANY_FALLBACK_TEAM))

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

# Every part of every template, read back from the doc's text alone, must be
# the export's text as the hash normalises it; otherwise the doc does not
# show what "done" would approve, and nothing is written.
_reader = doc_areas.DocReader(plain)
_unread = []
for _tid in approvable_ids:
    _e = by_id[_tid]
    for _name, _want in [("main", _e["main"])] + [(v["name"], v["lines"]) for v in _e["variants"]]:
        try:
            _got = norm_lines(_reader.main(_tid)) if _name == "main" else _reader.part(_tid, _name)
        except doc_areas.DocError as exc:
            _got = exc
        if _got != norm_lines(_want):
            _unread.append("%s %s" % (_tid, _name))
if _unread:
    raise SystemExit("the doc does not show every part exactly (%d): %s" % (len(_unread), ", ".join(_unread[:8])))
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
print("variant blocks:", stats["variants_shown"], "changes by kind:", dict(sorted(stats["changes"].items())),
      "combinations as one note:", stats["combos_as_note"], "same as main:", stats["same_as_main"],
      "time versions in full:", stats["times_in_full"], "other versions in full:", stats["in_full"],
      "days naming a spliced line:", stats["pinned"])
print("missing_lead_data explained at top:", stats["missing_explained"])
print("every part of all %d approvable templates reads back from the doc's text" % len(approvable_ids))
print("variants skipped:")
for k, v in sorted(stats["variants_skipped"].items()):
    print("  %4d  %s" % (v, k))
print("instantly steps:", instantly_steps)
print("not placed (not approvable):", [e["id"] for e in entries if not e["approvable"] and not e["id"].startswith("first_reply.")],
      "+", sum(1 for e in entries if not e["approvable"] and e["id"].startswith("first_reply.")), "first_reply reference pieces")
