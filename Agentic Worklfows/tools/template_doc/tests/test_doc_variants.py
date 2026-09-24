"""The one doc determines every template's hashed text.

build.py shows each version (variant) as the changes it makes to the main
text: grey notes quoting the main-text lines it replaces or leaves out, then
the lines it puts in. doc_areas.DocReader reads every part of every template
back out of the doc's plain text alone. These tests check that it gets the
catalogue's own text for every part of every approvable template, and that a
change to any part of any template (a line deleted, two lines swapped, an
hour or a zone label changed) either changes the rebuilt doc's text for that
template or makes the build refuse (then the recorder refuses everything).
No network, no model calls, no approvals file.
"""
import ast
import io
import os
import re
import shutil
import subprocess
import sys
from collections import OrderedDict

import pytest

import doc_areas
import doc_rules
import fresh_manifest

from services.reply_engine import template_approvals as ta

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(TOOL_DIR, "build.py")
VARIANT_RE = re.compile(r"^=== variant: (\S+) \((.*)\) ===$")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d\d)([ap]m)\b")
ZONE_RE = re.compile(r"\b(CT|ET|MT|PT|MST)\b")
ZONE_SWAP = {"CT": "ET", "ET": "MT", "MT": "PT", "PT": "CT", "MST": "MT"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    b = fresh_manifest.build_fresh(str(tmp_path_factory.mktemp("variants") / "build"))
    b["plain"] = doc_areas.html_to_text(b["html_path"])
    b["md"] = io.open(b["export_path"], encoding="utf-8").read()
    return b


def _catalogue():
    return [e for e in ta.catalogue() if e.get("approvable")]


def _norm(text):
    return ta.normalise(text).split("\n") if ta.normalise(text) else []


# ------------------------------------------------------------ read back
def test_every_part_of_every_template_reads_back_from_the_doc_text(built):
    """Recoverability: from the doc's rendered text alone, every approvable
    template's main text and every one of its versions, its subject and its
    time formats equal the catalogue's (as the hash normalises them)."""
    reader = doc_areas.DocReader(built["plain"])
    entries = _catalogue()
    assert len(entries) == 108
    shown = 0
    for e in entries:
        tid = e["id"]
        assert doc_rules.norm_lines(reader.main(tid)) == _norm(e["text"]), tid
        for v in e["variants"]:
            assert reader.part(tid, v["name"]) == _norm(v["text"]), (tid, v["name"])
            if "%s/%s" % (tid, v["name"]) in reader.items:
                shown += 1
    assert shown == 195  # 154 changed versions, 25 dated and other-timezone, 8 without a Loom link, 8 combinations
    # and the hash each id carries is the hash of exactly those parts
    for e in entries:
        parts = [dict(v, text="\n".join(reader.part(e["id"], v["name"]))) for v in e["variants"]]
        assert ta.text_hash(ta.compose_review_text("\n".join(reader.main(e["id"])), parts)) == e["sha256"], e["id"]


def test_reading_back_survives_drives_extra_blank_lines(built):
    """Drive's text export writes an empty paragraph as two blank lines."""
    doubled = "\n".join(l if l.strip() else "\n" for l in built["plain"].split("\n"))
    a, b = doc_areas.DocReader(built["plain"]), doc_areas.DocReader(doubled)
    for e in _catalogue():
        for v in e["variants"]:
            assert a.part(e["id"], v["name"]) == b.part(e["id"], v["name"])


def test_every_dated_and_other_timezone_version_is_shown(built):
    reader = doc_areas.DocReader(built["plain"])
    names = ("dated", "lead_in_other_timezone")
    found = [(e["id"], v["name"]) for e in _catalogue() for v in e["variants"] if v["name"] in names]
    assert len(found) == 27
    for tid, name in found:
        tag = "%s/%s" % (tid, name)
        assert tag in reader.items, tag
        body = reader.body(tag)
        if any(doc_rules.TIME_VALUE_RE.search(l) for l in body):
            assert doc_rules.EXAMPLE_TIMES_NOTE in reader.notes(tag), tag


def test_a_version_block_quotes_what_it_replaces(built):
    reader = doc_areas.DocReader(built["plain"])
    tag = "first_reply.cleaning_reactivation.pricing.full/no_slots"
    assert reader.notes(tag) == [
        'Instead of "Would {slots} work for a 15-minute call? Or if it\'s easier, grab a time here: {booking_url}":']
    assert reader.body(tag) == ["Do you have 15 minutes this week or next? Or if it's easier, grab a time here: "
                                "{booking_url}"]
    tag = "cadence.d3/no_slots"
    assert reader.notes(tag) == ['Instead of "A couple more options if those did not work: {slots}." and '
                                 '"Or pick whatever suits you here: {booking_url}":']
    loom = "show_rate.confirm_email.cleaning_reactivation/no_loom_url"
    assert reader.notes(loom)[0].startswith('Leaves out "Here is a 60-second walkthrough') and not reader.body(loom)
    combo = "show_rate.confirm_email.cleaning_reactivation/no_call_link_or_loom"
    assert reader.notes(combo) == [doc_rules.COMBOS["no_call_link_or_loom"][1]]
    # the day 5 versions write the cleaning line out; the doc says so
    assert any(doc_rules.PIN_RE.match(n) for n in reader.notes("cadence.d5"))
    assert any(doc_rules.PIN_RE.match(n) for n in reader.notes("cadence.d4"))
    assert not any(doc_rules.PIN_RE.match(n) for n in reader.notes("cadence.d2"))


def test_the_normalise_copy_is_the_engines():
    samples = [e["review_text"] for e in ta.catalogue() if e.get("review_text")]
    samples += ["", "\n\n  a  \r\n\r\n\r\nb\t \n\n\n", "  x\n\n\n\ny  ", "a\rb\r\r\rc"]
    for s in samples:
        assert doc_rules.normalise(s) == ta.normalise(s)


def test_subject_notes_and_change_notes_read_back():
    lines = ["Subject when the thread has none: Re: {first_name}, question",
             "Subject when there is no first name either: Re: your reply."]
    note = doc_rules.subject_note(lines)
    assert doc_rules.read_subject_note(note) == lines
    assert doc_rules.read_subject_note(doc_rules.subject_note(lines[::-1])) == lines[::-1]
    assert doc_rules.read_subject_note("If their email had no subject: x") is None
    for kind in doc_rules.CHANGE_FORMS:
        quoted = ['He said "hi" and "bye"', "B."] if kind in doc_rules.QUOTING else ['x "y"']
        assert doc_rules.change_kind(doc_rules.change_note(kind, quoted)) == kind
    assert doc_rules.change_kind(doc_rules.EXAMPLE_TIMES_NOTE) is None
    assert doc_rules.change_kind(doc_rules.SAME_AS_MAIN) is None


# ------------------------------------------------------------ the export, mutated
def _parts(md):
    """(lines, [(id, OrderedDict(part -> [line indices, blank ones too]))])
    for the approvable entries of an export."""
    lines = md.split("\n")
    out, cur, approvable, i = [], None, False, 0
    while i < len(lines):
        m = re.match(r"^### `(.+)`$", lines[i])
        if m:
            cur, approvable = m.group(1), False
        if lines[i].startswith("<!-- approve-template"):
            approvable = True
        if lines[i].startswith("```text") and cur and approvable:
            j, part, items = i + 1, "main", OrderedDict()
            while lines[j] != "```":
                vm = VARIANT_RE.match(lines[j])
                if vm:
                    part = vm.group(1)
                else:
                    items.setdefault(part, []).append(j)
                j += 1
            out.append((cur, items))
            i = j
        i += 1
    return lines, out


def _needles():
    """build.py's VF_NEEDLES: lines of the time formats the top section quotes
    (removing one makes the build refuse, which is fine but slow to bisect)."""
    for node in ast.parse(io.open(BUILD, encoding="utf-8").read()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "VF_NEEDLES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("VF_NEEDLES not found in build.py")


def _mutation(lines, idx, main_lines, part, mode, needles):
    """{line index: new text or None (delete)} for one mutation of one part,
    or None when the mode does not apply to it."""
    nb = [j for j in idx if lines[j].strip()]
    free = [j for j in nb if not any(n in lines[j] for n in needles)]
    if part == "subject":
        nb = nb[1:] if len(nb) >= 3 else []  # the fallback lines (a Subject line needs one)
    if mode == "delete_shared":
        c = [j for j in (free if part == "value_formats" else nb) if part == "main" or lines[j] in main_lines]
        return {c[len(c) // 2]: None} if c else None
    if mode == "delete_own":
        c = [j for j in (free if part == "value_formats" else nb) if part == "main" or lines[j] not in main_lines]
        return {c[0]: None} if c else None
    if mode in ("swap_first", "swap_middle"):
        pairs = [(a, b) for a, b in zip(nb, nb[1:]) if lines[a] != lines[b]]
        if not pairs:
            return None
        a, b = pairs[0] if mode == "swap_first" else pairs[len(pairs) // 2]
        return {a: lines[b], b: lines[a]}
    rx = TIME_RE if mode == "digit" else ZONE_RE
    c = [j for j in (free if part == "value_formats" else nb) if rx.search(lines[j])]
    if not c:
        return None
    j = c[0]
    if mode == "digit":
        new = TIME_RE.sub(lambda m: "%d:%s%s" % (int(m.group(1)) % 12 + 1, m.group(2), m.group(3)), lines[j], count=1)
    else:
        new = ZONE_RE.sub(lambda m: ZONE_SWAP[m.group(1)], lines[j], count=1)
    return {j: new}


def _apply(lines, edits):
    out = []
    for i, l in enumerate(lines):
        if i in edits:
            if edits[i] is not None:
                out.append(edits[i])
        else:
            out.append(l)
    return "\n".join(out)


def _region(reader, tid, with_formats):
    """Everything the doc shows for one template: its blocks (labels, notes,
    body lines, in order), its Subject line and, when it has times, the time
    formats block it names."""
    out = [(tag, reader.labels[tag], tuple(items)) for tag, items in reader.items.items()
           if tag == tid or tag.startswith(tid + "/")]
    out.append(("subject", reader.subjects.get(tid)))
    if with_formats:
        out.append(("formats", tuple(reader.body(reader._formats_tag(tid)))))
    return tuple(out)


# build.py's own refusals: the recorder then refuses the whole doc
KNOWN_REFUSALS = [
    re.compile(r"^the top section says cadence\.d\d+ writes 'your team' when the company is missing, and it does not$"),
    re.compile(r"^the subject variant of \S+ has no fallback line"),
    re.compile(r"^the doc does not show every part exactly \(\d+\): "),
    re.compile(r"^AssertionError: \S+$"),
]
MODES = ("delete_shared", "delete_own", "swap_first", "swap_middle", "digit", "zone")


def test_no_part_of_any_template_can_change_unseen(built, tmp_path):
    """Mutation test with teeth: for every part of every approvable template
    (main text with its Subject line, subject fallbacks, every version, the
    time formats), delete a line (one it shares with the main text and one of
    its own), swap two adjacent lines (the first pair and a middle pair),
    change an hour and swap a zone label. Each mutation must change what the
    rebuilt doc shows for that template, or make the build refuse. Batches
    (one part, one mode, every id) whose build refuses are split down to
    single ids, so one refusing template cannot hide the others."""
    lines, entries = _parts(built["md"])
    needles = _needles()
    base = doc_areas.DocReader(built["plain"])
    has_formats = set(tid for tid, items in entries if "value_formats" in items)
    by_part = OrderedDict()
    for tid, items in entries:
        for part in items:
            by_part.setdefault(part, []).append(tid)
    main_of = dict((tid, set(lines[j] for j in items["main"] if lines[j].strip())) for tid, items in entries)
    items_of = dict(entries)
    src, out = str(tmp_path / "m.md"), str(tmp_path / "out")
    results = OrderedDict()
    hidden, refused_unknown = [], []

    def run(part, mode, ids):
        edits = {}
        for tid in ids:
            e = _mutation(lines, items_of[tid][part], main_of[tid], part, mode, needles)
            if e:
                edits[tid] = e
        if not edits:
            return
        merged = {}
        for e in edits.values():
            merged.update(e)
        io.open(src, "w", encoding="utf-8").write(_apply(lines, merged))
        shutil.rmtree(out, ignore_errors=True)
        r = subprocess.run([sys.executable, BUILD, "--export", src, "--out-dir", out], cwd=TOOL_DIR,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        key = (part, mode)
        if r.returncode == 0:
            reader = doc_areas.DocReader(doc_areas.html_to_text(os.path.join(out, "advero_all_emails.html")))
            for tid in edits:
                if _region(reader, tid, tid in has_formats) == _region(base, tid, tid in has_formats):
                    hidden.append((part, mode, tid))
                else:
                    results.setdefault(key, {"shown": 0, "refused": 0})["shown"] += 1
        elif len(edits) == 1:
            last = (r.stdout.strip().splitlines() or [""])[-1]
            results.setdefault(key, {"shown": 0, "refused": 0})["refused"] += 1
            if not any(k.match(last) for k in KNOWN_REFUSALS):
                refused_unknown.append((part, mode, list(edits)[0], last[:200]))
        else:
            ids = sorted(edits)
            run(part, mode, ids[:len(ids) // 2])
            run(part, mode, ids[len(ids) // 2:])

    for part, ids in by_part.items():
        for mode in MODES:
            run(part, mode, ids)
            if part == "value_formats":
                run(part, mode, ids[:1])  # one template's formats differing from the others'
    summary = dict(("%s/%s" % k, v) for k, v in results.items())
    assert not hidden, hidden[:10]
    assert not refused_unknown, refused_unknown[:5]
    shown = sum(v["shown"] for v in results.values())
    refused = sum(v["refused"] for v in results.values())
    by_mode = dict((m, sum(v["shown"] for k, v in results.items() if k[1] == m)) for m in MODES)
    print("mutations shown %d, refused by the build %d; shown by mode %s" % (shown, refused, by_mode))
    assert shown > 2000 and refused < 20, summary
    for m in MODES:
        assert by_mode[m] > 100, (m, by_mode)
    parts_seen = set(k[0] for k, v in results.items() if v["shown"])
    assert {"main", "subject", "value_formats", "missing_lead_data", "no_slots", "dated",
            "lead_in_other_timezone", "no_loom_url", "no_call_link_or_loom"} <= parts_seen, parts_seen


def test_a_version_the_change_notes_cannot_say_is_shown_in_full(built, tmp_path):
    """A line moved into another paragraph: shown in full, read back exactly."""
    lines, entries = _parts(built["md"])
    items = dict(entries)["booking.confirmation.zoom_link"]
    nb = [j for j in items["lead_in_other_timezone"] if lines[j].strip()]
    src, out = str(tmp_path / "m.md"), str(tmp_path / "out")
    io.open(src, "w", encoding="utf-8").write(_apply(lines, {nb[0]: lines[nb[1]], nb[1]: lines[nb[0]]}))
    r = subprocess.run([sys.executable, BUILD, "--export", src, "--out-dir", out], cwd=TOOL_DIR,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert r.returncode == 0, r.stdout[-2000:]
    reader = doc_areas.DocReader(doc_areas.html_to_text(os.path.join(out, "advero_all_emails.html")))
    tag = "booking.confirmation.zoom_link/lead_in_other_timezone"
    assert reader.notes(tag) == [doc_rules.WHOLE_NOTE]
    assert reader.body(tag)[:3] == [lines[nb[1]], "", lines[nb[0]]]


def test_the_reviewers_hidden_cases_now_show(built, tmp_path):
    """Round-two findings: the pricing answer dropped from a no-free-slots
    version, and Day 3's no-free-slots version dropping its greeting, each
    change the rebuilt doc."""
    lines, entries = _parts(built["md"])
    by = dict(entries)
    pricing = "first_reply.cleaning_reactivation.pricing.full"
    answer = next(j for j in by[pricing]["no_slots"] if lines[j].startswith("Nothing up front."))
    greeting = next(j for j in by["cadence.d3"]["no_slots"] if lines[j] == "Hey {first_name},")
    base = doc_areas.DocReader(built["plain"])
    for tid, j, note in ((pricing, answer, 'Instead of "Nothing up front.'),
                         ("cadence.d3", greeting, 'Instead of "Hey {first_name},", "A couple more options')):
        src, out = str(tmp_path / "m.md"), str(tmp_path / ("out_" + tid))
        io.open(src, "w", encoding="utf-8").write(_apply(lines, {j: None}))
        r = subprocess.run([sys.executable, BUILD, "--export", src, "--out-dir", out], cwd=TOOL_DIR,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        assert r.returncode == 0, r.stdout[-2000:]
        reader = doc_areas.DocReader(doc_areas.html_to_text(os.path.join(out, "advero_all_emails.html")))
        tag = tid + "/no_slots"
        assert reader.notes(tag) != base.notes(tag)
        assert any(n.startswith(note) for n in reader.notes(tag)), reader.notes(tag)
        assert lines[j] not in reader.body(tag)  # quoted as replaced, and not put back
