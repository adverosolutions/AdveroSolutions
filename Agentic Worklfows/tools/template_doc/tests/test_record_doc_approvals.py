"""record_doc_approvals.py: approvals from the one Google Doc after "done".

The doc under test is a real build (build.py via fresh_manifest) registered in
a tmp builds/ folder and a tmp uploads.json; the recorder's fresh build is a
second, separate build. Every approvals file is a tmp file; the real
config/approved_templates.json is checked (and restored) after each test and
no Job_Log row reaches .tmp/. No network, no model calls.
"""
import ast
import copy
import dataclasses
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import timedelta

import pytest

import diff_doc
import doc_areas
import doc_rules
import fresh_manifest
import record_doc_approvals as rda
import route_doc
from parse_doc import parse_with_info

from services.reply_engine import template_approvals as ta
from shared.paths import BASE_DIR

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_FILE = BASE_DIR / "config" / "approved_templates.json"
FIRST_EDITS = os.path.join(TOOL_DIR, "exports", "2026-09-23T1815Z.txt")
DRIVE_EXPORT = os.path.join(TOOL_DIR, "drive_export.txt")
DOC_ID = "test-doc-0001"
QUOTE = "done"
TAG_LINE_RE = re.compile(r"\(\s*tag\s*:\s*([^()\s]+)\s*\)")


# ------------------------------------------------ selftest's Drive rendering
def _selftest_renderer():
    """html_to_text and googleify exactly as selftest.py defines them."""
    src = io.open(os.path.join(TOOL_DIR, "selftest.py"), encoding="utf-8").read()
    keep = []
    for node in ast.parse(src).body:
        if isinstance(node, ast.Import) or (isinstance(node, ast.ImportFrom) and node.module == "html.parser"):
            keep.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "GoogleText":
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in ("html_to_text", "googleify"):
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(getattr(t, "id", None) in ("BLOCK", "SKIP") for t in node.targets):
            keep.append(node)
    ns = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "selftest_renderer", "exec"), ns)
    return ns["html_to_text"], ns["googleify"]


SELFTEST_HTML_TO_TEXT, GOOGLEIFY = _selftest_renderer()


# ------------------------------------------------------------------ fixtures
def _register(build, builds_dir):
    """Put a build into builds/<fingerprint>/ as build.py's default does."""
    fp = build["fingerprint"]
    dest = os.path.join(builds_dir, fp)
    if not os.path.isdir(dest):
        shutil.copytree(os.path.dirname(build["manifest_path"]), dest)
    return fp


@pytest.fixture(scope="module")
def builds_dir(tmp_path_factory):
    return str(tmp_path_factory.mktemp("builds"))


@pytest.fixture(scope="module")
def doc(tmp_path_factory, builds_dir):
    """The doc Lorenzo reads: a build of the current code, registered."""
    b = fresh_manifest.build_fresh(str(tmp_path_factory.mktemp("doc") / "build"))
    _register(b, builds_dir)
    b["plain"] = doc_areas.html_to_text(b["html_path"])
    return b


@pytest.fixture(scope="module")
def fresh(tmp_path_factory):
    """The recorder's own fresh build (separate files from the doc's)."""
    return fresh_manifest.build_fresh(str(tmp_path_factory.mktemp("fresh") / "build"))


@pytest.fixture
def plain(doc):
    return doc["plain"]


@pytest.fixture(autouse=True)
def approvals_file(tmp_path, monkeypatch, builds_dir, doc):
    before = REAL_FILE.read_bytes() if REAL_FILE.exists() else None
    path = tmp_path / "approved_templates.json"
    monkeypatch.setattr(ta, "APPROVALS_PATH", path)
    monkeypatch.delenv(ta.KILL_SWITCH_ENV, raising=False)
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.delenv("JOB_LOG_SHEET_ID", raising=False)
    uploads = tmp_path / "uploads.json"
    uploads.write_text(json.dumps({"uploads": [{"doc_id": DOC_ID, "fingerprint": doc["fingerprint"]}]}),
                       encoding="utf-8")
    monkeypatch.setattr(rda, "BUILDS_DIR", builds_dir)
    monkeypatch.setattr(rda, "UPLOADS_PATH", str(uploads))
    yield path
    after = REAL_FILE.read_bytes() if REAL_FILE.exists() else None
    if before != after:
        if before is None:
            REAL_FILE.unlink()
        else:
            REAL_FILE.write_bytes(before)
        pytest.fail("a test wrote the real config/approved_templates.json (restored)")


class _Log(object):
    def __init__(self):
        self.rows = []

    def __call__(self, job, status, details=None):
        self.rows.append((job, status, details or {}))
        return {"job": job, "status": status}


@pytest.fixture
def log():
    return _Log()


def _write(tmp_path, text, name="export.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _run(fresh, export, approvals, log, *extra):
    return rda.main([export, "--approvals-file", str(approvals)] + list(extra), log_fn=log,
                    build=lambda out_dir: fresh)


def _write_args():
    return ("--write", "--doc-id", DOC_ID, "--done-quote", QUOTE, "--checked-comments")


def _doc_build(doc):
    return rda.load_doc_build(doc["fingerprint"])


def _plan(text, doc, fresh, approvals=None):
    return rda.evaluate(text, _doc_build(doc), fresh, approvals or ta.empty_approvals())


def _refused(plan):
    return dict((r["id"], r["reasons"]) for r in plan["refused"])


HELD = sorted(i for i in ta.catalogue_index() if doc_rules.is_held(i))


# ------------------------------------------------------- editing the text
def _tag_index(lines, tag):
    hits = [i for i, l in enumerate(lines) if TAG_LINE_RE.findall(l)[-1:] == [tag]]
    assert len(hits) == 1, (tag, hits)
    return hits[0]


def _block_end(lines, start):
    k = start + 1
    while k < len(lines):
        m = TAG_LINE_RE.findall(lines[k])
        if (m and not m[-1].endswith("/subject")) or lines[k].rstrip().endswith("(section)"):
            return k
        k += 1
    return k


def _line_in_block(lines, tag, text):
    i = _tag_index(lines, tag)
    for k in range(i + 1, _block_end(lines, i)):
        if lines[k].strip() == text.strip():
            return k
    raise AssertionError("%r not in block %s" % (text, tag))


def replace_line(text, tag, old, new):
    lines = text.split("\n")
    lines[_line_in_block(lines, tag, old)] = new
    return "\n".join(lines)


def edit_subject(text, tag, new_subject):
    lines = text.split("\n")
    lines[_tag_index(lines, tag)] = "Subject: %s (tag: %s)" % (new_subject, tag)
    return "\n".join(lines)


def delete_block(text, tag):
    lines = text.split("\n")
    i = _tag_index(lines, tag)
    del lines[i:_block_end(lines, i)]
    return "\n".join(lines)


def edit_tag_line(text, tag, new_line):
    lines = text.split("\n")
    lines[_tag_index(lines, tag)] = new_line
    return "\n".join(lines)


def _template_blocks(doc):
    return [b for b in doc["manifest"]["blocks"] if b.get("template_id")]


def _line_count(doc):
    """normalised line -> number of template blocks that carry it"""
    counts = {}
    for b in _template_blocks(doc):
        for l in set(l.strip() for l in b["text"].split("\n") if l.strip()):
            counts[l] = counts.get(l, 0) + 1
    return counts


def _carriers(doc, line):
    """The template blocks that carry any sentence of the line (route_doc's
    own sentence matching, the repeat rule's)."""
    normed = doc.setdefault("_normed", dict((b["tag"], diff_doc.norm(b["text"] or "")) for b in _template_blocks(doc)))
    out = set()
    for sentence in route_doc._sentences(line):
        rx = route_doc._sentence_re(sentence)
        out |= set(t for t, text in normed.items() if rx.search(text))
    return out


def _unique_block(doc, kind, exclude=(), all_unique=False):
    """(block, line): a block of this kind whose text group is its own, with a
    line no sentence of which any other block carries (every line, with
    all_unique), of an id that is not held, not spliced, and not in exclude."""
    groups = {}
    for b in _template_blocks(doc):
        groups[b["text_group"]] = groups.get(b["text_group"], 0) + 1
    spliced = set(i for pair in doc_rules.splice_pairs() for i in pair)
    for b in _template_blocks(doc):
        tid = b["template_id"]
        if (b["kind"] == kind and groups[b["text_group"]] == 1 and tid not in exclude and tid not in spliced
                and not doc_rules.is_held(tid) and b["text"].strip()):
            lines = [l for l in b["text"].split("\n") if l.strip()]
            own = [l for l in lines if _carriers(doc, l) == {b["tag"]}]
            if own and (not all_unique or len(own) == len(lines)):
                return b, own[0]
    raise AssertionError("no unique %s block" % kind)


# ---------------------------------------------------------- renderer drift
def test_the_renderer_is_selftests(doc):
    for path in (os.path.join(TOOL_DIR, "advero_all_emails.html"), doc["html_path"]):
        assert doc_areas.html_to_text(path) == SELFTEST_HTML_TO_TEXT(path)


def test_the_real_drive_export_has_the_same_lines_as_the_local_rendering():
    legacy = rda.load_doc_build(None)
    text = io.open(DRIVE_EXPORT, encoding="utf-8-sig").read()
    assert doc_areas.areas(doc_areas.area_pairs(text)) == doc_areas.areas(legacy["visible"])


# ---------------------------------------------------------- the happy path
def test_the_doc_approves_every_id_but_the_held_first_replies(doc, fresh, plain, tmp_path, approvals_file, log,
                                                               capsys):
    export = _write(tmp_path, GOOGLEIFY(plain))
    rc = _run(fresh, export, approvals_file, log, *_write_args())
    out = capsys.readouterr().out
    assert rc == 0, out
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    index = ta.catalogue_index()
    approvable = sorted(tid for tid, e in index.items() if e.get("approvable"))
    assert len(approvable) == 108 and len(HELD) == 12
    assert sorted(data["approvals"]) == sorted(set(approvable) - set(HELD))
    assert set(data) == {"version", "approvals"}
    by = 'Lorenzo (Google Doc): "done", build %s' % doc["fingerprint"][:12]
    for tid in data["approvals"]:
        rec = data["approvals"][tid]
        assert rec["sha256"] == index[tid]["sha256"] == fresh["hashes"][tid] == doc["hashes"][tid]
        assert rec["approved_by"] == by
        assert set(rec) == {"sha256", "approved_at", "approved_by", "text_preview"}
        assert ta.status(tid, path=approvals_file) == ta.STATUS_APPROVED
    assert len(log.rows) == 1
    job, status, d = log.rows[0]
    assert (job, status, d["action"]) == ("approve_templates", "ok", "approve_from_doc")
    assert d["doc_id"] == DOC_ID and d["fingerprint"] == doc["fingerprint"] and d["done_quote"] == QUOTE
    assert d["checked_comments"] is True
    assert d["export_sha256"] == hashlib.sha256(open(export, "rb").read()).hexdigest()
    assert d["doc_manifest_sha256"] == hashlib.sha256(
        open(os.path.join(rda.BUILDS_DIR, doc["fingerprint"], "manifest.json"), "rb").read()).hexdigest()
    assert d["approvals_path"] == str(approvals_file)
    assert d["head"] is None or re.match(r"^[0-9a-f]{40}$", d["head"])
    assert d["approved"] == dict((tid, index[tid]["sha256"]) for tid in data["approvals"])
    assert sorted(d["refused"]) == HELD
    assert "git diff -- config/approved_templates.json" in out


def test_held_first_replies_are_single_sourced(doc):
    held_in_doc = sorted(b["template_id"] for b in doc["manifest"]["blocks"] if b.get("held"))
    assert held_in_doc == HELD
    areas = doc_areas.areas(doc["manifest"]["visible"])
    for tid in HELD:
        assert any(doc_rules.HELD_NOTE in l for l in areas[tid]), tid
    src = io.open(os.path.join(TOOL_DIR, "build.py"), encoding="utf-8").read()
    assert "HELD_QT =" not in src and "from doc_rules import" in src


def test_a_second_run_changes_nothing(doc, fresh, plain, tmp_path, approvals_file, log, capsys):
    export = _write(tmp_path, plain)
    assert _run(fresh, export, approvals_file, log, *_write_args()) == 0
    first = approvals_file.read_bytes()
    assert _run(fresh, export, approvals_file, log, *_write_args()) == 0
    assert approvals_file.read_bytes() == first
    assert log.rows[-1][2]["approved"] == {} and len(log.rows[-1][2]["unchanged"]) == 96
    assert "Nothing to change" in capsys.readouterr().out


def test_another_approvals_file_is_honoured(doc, fresh, plain, tmp_path, approvals_file, log):
    other = tmp_path / "elsewhere" / "registry.json"
    assert _run(fresh, _write(tmp_path, plain), other, log, *_write_args()) == 0
    assert other.exists() and not approvals_file.exists()
    assert log.rows[-1][2]["approvals_path"] == str(other)


# ------------------------------------------------------------- the edits
def test_edited_main_variant_subject_and_deleted_variant_refuse_exactly_those(doc, fresh, plain):
    m, m_line = _unique_block(doc, "template_main")
    v, v_line = _unique_block(doc, "template_variant", exclude=(m["template_id"],))
    s, _ = _unique_block(doc, "template_subject", exclude=(m["template_id"], v["template_id"]))
    d, _ = _unique_block(doc, "template_variant", exclude=(m["template_id"], v["template_id"], s["template_id"]),
                         all_unique=True)
    text = replace_line(plain, m["tag"], m_line, "Some brand new words for this email.")
    text = replace_line(text, v["tag"], v_line, "Any chance you have 15 minutes soon? {booking_url}")
    text = edit_subject(text, s["tag"], "Closing the loop")
    text = delete_block(text, d["tag"])
    refused = _refused(_plan(text, doc, fresh))
    ids = [m["template_id"], v["template_id"], s["template_id"], d["template_id"]]
    assert sorted(refused) == sorted(set(ids) | set(HELD))
    assert rda.R_EDITED % m["tag"] in refused[m["template_id"]]
    assert rda.R_EDITED % v["tag"] in refused[v["template_id"]]
    assert rda.R_EDITED % s["tag"] in refused[s["template_id"]]
    assert rda.R_DELETED % d["tag"] in refused[d["template_id"]]


def test_a_new_block_tagged_for_an_email_refuses_it_and_an_orphan_tag_refuses_the_doc(doc, fresh, plain, tmp_path,
                                                                                     approvals_file, log):
    lines = plain.split("\n")
    end = _block_end(lines, _tag_index(lines, "cadence.d7"))
    lines[end:end] = ["If they are busy: (tag: cadence.d7/busy)", "No rush at all.",
                      "Or this: (tag: cadence.d7.extra)", "Maybe later."]
    plan = _plan("\n".join(lines), doc, fresh)
    assert _refused(plan)["cadence.d7"] == [rda.R_ADDED % "cadence.d7/busy", rda.R_ADDED % "cadence.d7.extra"]
    assert plan["whole"] == []
    lines[end:end] = ["Something new: (tag: brand.new.email)", "Hello."]
    plan = _plan("\n".join(lines), doc, fresh)
    assert plan["whole"] == ["a tag in the doc matches no email: brand.new.email"]
    export = _write(tmp_path, "\n".join(lines))
    assert _run(fresh, export, approvals_file, log) == 1  # dry run reports, exits 1
    assert _run(fresh, export, approvals_file, log, *_write_args()) == 1
    assert not approvals_file.exists()


# ------------------------------------------------------ the repeat rule
TIME_OFFER = "Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}"


def test_the_time_offer_line_edited_once_refuses_every_email_with_it(doc, fresh, plain):
    holders = sorted(b["template_id"] for b in _template_blocks(doc) if TIME_OFFER in b["text"].split("\n"))
    assert len(holders) >= 30
    tag = holders[0]
    text = replace_line(plain, tag, TIME_OFFER, "Would {slots} work for a quick 10-minute call? {booking_url}")
    refused = _refused(_plan(text, doc, fresh))
    for tid in holders[1:]:
        assert rda.R_REPEAT % tag in refused[tid], tid


EASIER = "Or if it's easier, grab a time here: {booking_url}"


def test_a_sentence_edited_inside_a_longer_line_refuses_every_email_carrying_it(doc, fresh, plain):
    """The doc promises sentences: editing "Or if it's easier, grab a time
    here: {booking_url}" once, inside the time-offer line of one first reply,
    refuses every email that carries that sentence anywhere, also where it is
    a line of its own (the booking counter-proposals), and exactly the emails
    route_doc lists as "also appears in"."""
    tag = "first_reply.cleaning_reactivation.default.full"
    text = replace_line(plain, tag, TIME_OFFER, TIME_OFFER.replace(EASIER, "Or pick any open time here: {booking_url}"))
    refused = _refused(_plan(text, doc, fresh))
    carriers = sorted(set(b["template_id"] for b in _template_blocks(doc) if EASIER in b["text"]))
    whole_line = sorted(set(b["template_id"] for b in _template_blocks(doc) if TIME_OFFER in b["text"].split("\n")))
    elsewhere = [t for t in carriers if t not in whole_line]
    assert len(carriers) == 45 and len(elsewhere) == 15
    assert [t for t in elsewhere if t.startswith("booking.counter.")]
    for tid in carriers:
        assert tid in refused, tid
        if tid != tag:
            assert rda.R_REPEAT % tag in refused[tid], tid
    report = route_doc.build_report(text, doc["manifest"])
    (entry,) = [e for es in report["sections"].values() for e in es if e["tag"] == tag]
    by_tag = dict((b["tag"], b) for b in doc["manifest"]["blocks"])
    listed = set(by_tag[t]["template_id"] for ts in entry["also_in"].values() for t in ts
                 if by_tag[t].get("template_id"))
    repeat = set(tid for tid, rs in refused.items() if rda.R_REPEAT % tag in rs)
    assert repeat == listed


@pytest.mark.parametrize("kind", ["template_variant", "template_subject"])
def test_a_shared_block_edited_once_refuses_every_copy(doc, fresh, plain, kind):
    groups = {}
    for b in _template_blocks(doc):
        if b["kind"] == kind and b["text"].strip():
            groups.setdefault(b["text_group"], []).append(b)
    group = max(groups.values(), key=len)
    assert len(group) >= 29
    first = group[0]
    if kind == "template_subject":
        text = edit_subject(plain, first["tag"], "Quick follow-up")
    else:
        text = replace_line(plain, first["tag"], first["text"].split("\n")[0], "Grab any time here: {booking_url}")
    refused = _refused(_plan(text, doc, fresh))
    for b in group[1:]:
        assert rda.R_REPEAT % first["tag"] in refused[b["template_id"]], b["tag"]


def test_a_cadence_day_and_its_spliced_lines_stand_or_fall_together(doc, fresh, plain):
    d4 = next(b for b in doc["manifest"]["blocks"] if b["tag"] == "cadence.d4")
    counts = _line_count(doc)
    line = next(l for l in d4["text"].split("\n") if l.strip() and counts[l.strip()] == 1)
    refused = _refused(_plan(replace_line(plain, "cadence.d4", line, "A new line."), doc, fresh))
    for host, frag in doc_rules.splice_pairs():
        if host == "cadence.d4":
            assert rda.R_SPLICE_HOST % "cadence.d4" in refused[frag]
    frag = "cadence.d5.free_work.generic_outbound"
    fb = next(b for b in doc["manifest"]["blocks"] if b["tag"] == frag)
    refused = _refused(_plan(replace_line(plain, frag, fb["text"].split("\n")[0], "New words."), doc, fresh))
    assert rda.R_SPLICE_FRAG % frag in refused["cadence.d5"]
    for host, other in doc_rules.splice_pairs():
        if host == "cadence.d5":
            assert other in refused


# ---------------------------------------------- lines outside block bodies
def test_an_edited_fallback_subject_note_refuses_that_email(doc, fresh, plain):
    lines = plain.split("\n")
    i = _tag_index(lines, "cadence.d3/subject")
    assert lines[i + 1].startswith("If their email had no subject:") and lines[i + 1].endswith("(note)")
    lines[i + 1] = "If their email had no subject: URGENT: pay the invoice today. (note)"
    refused = _refused(_plan("\n".join(lines), doc, fresh))
    assert refused["cadence.d3"] == [rda.R_AREA % "cadence.d3"]
    assert sorted(refused) == sorted(set(HELD) | {"cadence.d3"})


def _note_index(lines, tag, startswith):
    i = _tag_index(lines, tag)
    for k in range(i + 1, _block_end(lines, i)):
        if lines[k].startswith(startswith) and lines[k].rstrip().endswith("(note)"):
            return k
    raise AssertionError("no note %r in %s" % (startswith, tag))


def test_the_lines_a_version_quotes_are_compared(doc, fresh, plain):
    """The quoted main-text lines of a version are part of what "done" is
    checked against: an edited, deleted or moved quote refuses that email."""
    tag = "cadence.d3/no_slots"
    lines = plain.split("\n")
    k = _note_index(lines, tag, 'Instead of "A couple more options')
    edited = list(lines)
    edited[k] = 'Instead of "A couple more options if those did not work: {slots}.": (note)'
    moved = list(lines)
    moved[k], moved[k + 1] = lines[k + 1], lines[k]
    deleted = lines[:k] + lines[k + 1:]
    for variant_text in (edited, moved, deleted):
        refused = _refused(_plan("\n".join(variant_text), doc, fresh))
        assert sorted(refused) == sorted(set(HELD) | {"cadence.d3"}), sorted(set(refused) - set(HELD))
        assert refused["cadence.d3"] == [rda.R_AREA % tag]


def test_edits_to_headings_and_labels_refuse_those_emails(doc, fresh, plain):
    text = edit_tag_line(plain, "cadence.d7", "Day 7 follow-up: DO NOT SEND THIS ONE (tag: cadence.d7)")
    text = edit_tag_line(text, "cadence.d14/no_slots", "If there are no free times, send nothing at all: "
                                                       "(tag: cadence.d14/no_slots)")
    refused = _refused(_plan(text, doc, fresh))
    assert refused["cadence.d7"] == [rda.R_AREA % "cadence.d7"]
    assert refused["cadence.d14"] == [rda.R_AREA % "cadence.d14/no_slots"]


def test_an_instruction_after_a_section_line_refuses_that_section(doc, fresh, plain):
    lines = plain.split("\n")
    s = next(k for k, l in enumerate(lines) if l.startswith("No-show recovery") and l.endswith("(section)"))
    lines[s + 1:s + 1] = ["Do not send any of the no-show emails below, I will handle no-shows by phone."]
    plan = _plan("\n".join(lines), doc, fresh)
    refused = _refused(plan)
    no_show = sorted(i for i in fresh["hashes"] if i.startswith("no_show."))
    assert len(no_show) == 15
    assert sorted(refused) == sorted(set(HELD) | set(no_show))
    for tid in no_show:
        assert refused[tid] == [rda.R_SECTION % "no_show"]
    assert plan["whole"] == []


@pytest.mark.parametrize("old,new", [
    ("{slots}: Tue 12:05pm or Thu 4:30pm CT (just Tue 12:05pm CT when only one time is free)",
     "{slots}: Tuesday at 12:05 or Thursday at 4:30 Central"),
    ("If we don't have their first name, 'Hey {first_name},' becomes 'Hey there,'.",
     "If we don't have their first name, 'Hey {first_name},' becomes 'Hi friend,'."),
])
def test_a_top_section_edit_refuses_the_whole_doc(doc, fresh, plain, tmp_path, approvals_file, log, old, new):
    assert old in plain
    text = plain.replace(old, new, 1)
    assert _plan(text, doc, fresh)["whole"] == ["the doc's top section changed"]
    assert _run(fresh, _write(tmp_path, text), approvals_file, log, *_write_args()) == 1
    assert not approvals_file.exists()
    assert log.rows[-1][1] == "refused" and "top section" in log.rows[-1][2]["reason"]


def test_an_instantly_heading_edit_refuses_the_whole_doc(doc, fresh, plain):
    tag = "instantly.cleaning_reactivation.step1"
    plan = _plan(edit_tag_line(plain, tag, "Step 1: do not send (tag: %s)" % tag), doc, fresh)
    assert plan["whole"] and tag in plan["whole"][0]


def test_lorenzos_first_export(doc, fresh, tmp_path, approvals_file, log, capsys):
    """The 18:15Z export of the doc in Drive (built before fingerprints):
    cadence.d1 and cadence.d2 edited, both no_slots variants deleted, and a
    note to Claude typed after cadence.d2's fallback-subject note."""
    text = io.open(FIRST_EDITS, encoding="utf-8-sig").read()
    assert doc_areas.read_fingerprint(text) == (None, None)
    plan = rda.evaluate(text, rda.load_doc_build(None), fresh, ta.empty_approvals())
    refused = _refused(plan)
    assert rda.R_EDITED % "cadence.d1" in refused["cadence.d1"]
    assert rda.R_DELETED % "cadence.d1/no_slots" in refused["cadence.d1"]
    assert rda.R_EDITED % "cadence.d2" in refused["cadence.d2"]
    assert rda.R_DELETED % "cadence.d2/no_slots" in refused["cadence.d2"]
    assert rda.R_AREA % "cadence.d2" in refused["cadence.d2"]  # the note line is no longer a note
    for frag in ("cadence.d2.research_fallback.reactivation", "cadence.d2.research_fallback.outbound"):
        assert rda.R_SPLICE_HOST % "cadence.d2" in refused[frag]
    for tid in HELD:
        assert rda.R_HELD in refused[tid]
    # the removed line "Or if it's easier, grab a time here: {booking_url}" is in other emails too
    assert rda.R_REPEAT % "cadence.d1" in refused["booking.counter.weekend"]
    # the doc in Drive does not show the time formats block: nothing with a time can be approved from it
    for tid in fresh["manifest"]["blocks"][0]["dependents"]:
        assert tid in refused
    approved = set(p["id"] for p in plan["approve"])
    assert approved and not (approved & set(refused))

    rc = rda.main([FIRST_EDITS, "--approvals-file", str(approvals_file)], log_fn=log)  # real fresh build
    out = capsys.readouterr().out
    assert rc == 1 and rda.W_LEGACY in out and "Dry run: nothing was written" in out
    assert not approvals_file.exists() and log.rows == []
    rc = rda.main([FIRST_EDITS, "--approvals-file", str(approvals_file), "--write", "--doc-id",
                   "1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U", "--done-quote", "done", "--checked-comments"],
                  log_fn=log)
    assert rc == 1 and not approvals_file.exists()
    assert log.rows[-1][1] == "refused" and rda.W_LEGACY in log.rows[-1][2]["reason"]


# ------------------------------------------------ hashed text the doc shows
def _patched_build(monkeypatch, tmp_path, target, name, wrap):
    orig = getattr(target, name)
    monkeypatch.setattr(target, name, wrap(orig))
    ta.clear_cache()
    try:
        return fresh_manifest.build_fresh(str(tmp_path / ("build_" + name)))
    finally:
        monkeypatch.setattr(target, name, orig)
        ta.clear_cache()


def _pst(orig):
    def lab(dt, tz):
        return "PST" if getattr(tz, "zone", "") == "America/Los_Angeles" else orig(dt, tz)
    return lab


def _wire(orig):
    def ds(s):
        r = orig(s)
        return (r + ", or wire the $500 deposit today to hold one") if r else r
    return ds


@pytest.mark.parametrize("which", ["pst", "dated"])
def test_a_formatter_change_is_refused_and_shows_in_a_rebuilt_doc(doc, fresh, plain, tmp_path, monkeypatch,
                                                                  builds_dir, which):
    from services.reply_engine import booking
    from shared import slots
    if which == "pst":
        b = _patched_build(monkeypatch, tmp_path, slots, "_tz_label", _pst)
        words = "PST"
    else:
        b = _patched_build(monkeypatch, tmp_path, booking, "_dated_slots", _wire)
        words = "or wire the $500 deposit today"
    changed = sorted(t for t in b["hashes"] if b["hashes"][t] != doc["hashes"][t])
    assert len(changed) >= 80
    new_plain = doc_areas.html_to_text(b["html_path"])
    assert new_plain != plain and words in new_plain and words not in plain
    # Lorenzo said done on the old doc: every changed id is refused, even with the new build registered
    _register(b, builds_dir)
    refused = _refused(rda.evaluate(plain, _doc_build(doc), b, ta.empty_approvals(), entries_now=_index_from(b)))
    for tid in changed:
        assert any(r.startswith("code changed since this doc was built") for r in refused[tid]), tid
    # the rebuilt doc shows the new words, so "done" on it approves them
    plan = rda.evaluate(new_plain, rda.load_doc_build(b["fingerprint"]), b, ta.empty_approvals(),
                        entries_now=_index_from(b))
    assert set(changed) - set(HELD) <= set(p["id"] for p in plan["approve"])


def _no_greeting_on_day_3_without_slots(orig):
    """Round two's X1: Day 3 without free times also drops its greeting."""
    def build_touch(state, day, slots, *a, **k):
        t = orig(state, day, slots, *a, **k)
        if not slots and day == 3:
            lines = t.body_text.split("\n")
            if lines and lines[0].startswith("Hey "):
                lines = lines[1:]
                while lines and not lines[0].strip():
                    lines = lines[1:]
            t = dataclasses.replace(t, body_text="\n".join(lines))
        return t
    return build_touch


def _mountain_for_eastern(orig):
    """Round two's X2a: a New York lead's times written in Mountain time."""
    def render(key, appt, start, now):
        if appt.get("lead_tz") == "America/New_York":
            appt = dict(appt, lead_tz="America/Denver")
        return orig(key, appt, start, now)
    return render


def _hour_off_in_lead_zone(orig):
    """Round two's X2b: the other-timezone version an hour off."""
    def render(key, appt, start, now):
        if appt.get("lead_tz"):
            start = start + timedelta(hours=1)
        return orig(key, appt, start, now)
    return render


ROUND_TWO = {
    "x1_day3_no_greeting": ("cadence", "build_touch", _no_greeting_on_day_3_without_slots),
    "x2a_mountain_for_eastern": ("show_rate", "render", _mountain_for_eastern),
    "x2b_hour_off_in_lead_zone": ("show_rate", "render", _hour_off_in_lead_zone),
}


def _shown(reader, tid):
    """Everything the doc shows for one template: its blocks' labels, notes and
    lines, and its Subject line."""
    return ([(tag, reader.labels[tag], reader.items[tag]) for tag in reader.items
             if tag == tid or tag.startswith(tid + "/")], reader.subjects.get(tid))


@pytest.mark.parametrize("case", sorted(ROUND_TWO))
def test_round_two_code_changes_show_in_a_rebuilt_doc(doc, fresh, plain, tmp_path, monkeypatch, builds_dir, case):
    """The three code changes round two found hidden: each changes what the
    rebuilt doc shows for every template it changes, "done" on the old doc
    refuses them, and "done" on the rebuilt doc approves what it now shows."""
    from services.reply_engine import cadence, show_rate
    module, name, wrap = ROUND_TWO[case]
    b = _patched_build(monkeypatch, tmp_path, {"cadence": cadence, "show_rate": show_rate}[module], name, wrap)
    changed = sorted(t for t in b["hashes"] if b["hashes"][t] != doc["hashes"][t])
    assert changed
    new_plain = doc_areas.html_to_text(b["html_path"])
    old_reader, new_reader = doc_areas.DocReader(plain), doc_areas.DocReader(new_plain)
    for tid in changed:
        assert _shown(old_reader, tid) != _shown(new_reader, tid), tid
    if case.startswith("x1"):
        assert changed == ["cadence.d3"]
        assert new_reader.notes("cadence.d3/no_slots")[0].startswith('Instead of "Hey {first_name},", "A couple')
        assert new_reader.part("cadence.d3", "no_slots")[0] != "Hey {first_name},"
    elif case.startswith("x2a"):
        assert "(12:47pm MT)" in new_plain and "(12:47pm MT)" not in plain
    else:
        assert "2:47pm CT (3:47pm ET)" in new_plain and "2:47pm CT (3:47pm ET)" not in plain
    _register(b, builds_dir)
    refused = _refused(rda.evaluate(plain, _doc_build(doc), b, ta.empty_approvals(), entries_now=_index_from(b)))
    for tid in changed:
        assert any(r.startswith("code changed since this doc was built") for r in refused[tid]), tid
    plan = rda.evaluate(new_plain, rda.load_doc_build(b["fingerprint"]), b, ta.empty_approvals(),
                        entries_now=_index_from(b))
    assert set(changed) - set(HELD) <= set(p["id"] for p in plan["approve"])


def _index_from(build):
    return dict((tid, {"sha256": h, "approvable": True, "extractable": True}) for tid, h in build["hashes"].items())


def test_dropped_lines_are_shown(doc):
    areas = doc_areas.areas(doc["manifest"]["visible"])
    loom = [tid for tid, e in ta.catalogue_index().items()
            if e.get("approvable") and any(v["name"] == "no_loom_url" for v in e["variants"])]
    assert len(loom) == 8
    for tid in loom:
        notes = areas[tid + "/no_loom_url"]
        assert notes[0] == "If no Loom link is set up: (tag: %s/no_loom_url)" % tid
        assert notes[1].startswith('Leaves out "') and "{loom_url}" in notes[1] and notes[1].endswith('". (note) @0')


VARIANT_RE = re.compile(r"^=== variant: (\S+) \((.*)\) ===$")


def _export_parts(md):
    """[(id, [(line index, part)], main line set)] for approvable entries."""
    lines = md.split("\n")
    out, cur, approvable, i = [], None, False, 0
    while i < len(lines):
        m = re.match(r"^### `(.+)`$", lines[i])
        if m:
            cur, approvable = m.group(1), False
        if lines[i].startswith("<!-- approve-template"):
            approvable = True
        if lines[i].startswith("```text") and cur and approvable:
            j, part, items, main = i + 1, "main", [], set()
            while lines[j] != "```":
                vm = VARIANT_RE.match(lines[j])
                if vm:
                    part = vm.group(1)
                elif lines[j].strip():
                    items.append((j, part))
                    if part == "main":
                        main.add(lines[j])
                j += 1
            out.append((cur, items, main))
            i = j
        i += 1
    return out


def _mutate(md, part, mode, ids):
    """Append a unique token to lines of one part of the given ids. mode:
    all lines, only the lines that differ from the main text, only the ones
    shared with it. Returns (markdown, {id: [tokens]})."""
    lines = md.split("\n")
    toks, n = {}, [0]

    def tok():
        n[0] += 1
        return "zq%dq" % n[0]
    for tid, items, main in _export_parts(md):
        if tid not in ids:
            continue
        first_of = {}
        for j, p in items:
            first_of.setdefault(p, j)
        inline = lines[first_of["main"]].startswith("Subject: ")
        if part == "inline_subject":
            if inline:
                t = tok()
                for j in first_of.values():  # the subject line of the main text and of every variant
                    lines[j] += " " + t
                toks[tid] = [t]
            continue
        for j, p in items:
            if p != part or (inline and j == first_of[p]):
                continue
            shared = lines[j] in main
            if (mode == "diff" and shared) or (mode == "ctx" and not shared):
                continue
            t = tok()
            lines[j] += " " + t
            toks.setdefault(tid, []).append(t)
    return "\n".join(lines), toks


def test_every_hashed_part_of_every_template_shows_in_the_doc(fresh, tmp_path):
    """Coverage over the whole catalogue: a change to any line of any part of
    any template's review text (main, subject, every variant, value_formats)
    either shows in the rebuilt doc's text or makes the build fail (which
    refuses everything). Batches whose build fails are split down to single
    ids, so one fail-closed template cannot hide the others."""
    md = io.open(fresh["export_path"], encoding="utf-8").read()
    parts = {}
    for tid, items, _ in _export_parts(md):
        for _, p in items:
            parts.setdefault(p, set()).add(tid)
    parts["inline_subject"] = set(fresh["hashes"])
    out = str(tmp_path / "out")
    src = str(tmp_path / "m.md")
    stats = {"shown": 0, "failed_closed": 0}
    failures = []

    def check(part, mode, ids):
        text, toks = _mutate(md, part, mode, ids)
        if not toks:
            return
        io.open(src, "w", encoding="utf-8").write(text)
        shutil.rmtree(out, ignore_errors=True)
        r = subprocess.run([sys.executable, os.path.join(TOOL_DIR, "build.py"), "--export", src, "--out-dir", out],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if r.returncode == 0:
            shown = doc_areas.html_to_text(os.path.join(out, "advero_all_emails.html"))
            hidden = [(tid, t) for tid, ts in toks.items() for t in ts if t not in shown]
            assert not hidden, (part, mode, hidden[:5])
            stats["shown"] += len(toks)
        elif len(toks) == 1:
            stats["failed_closed"] += 1
            last = (r.stdout.strip().splitlines() or [""])[-1]
            failures.append((part, mode, sorted(toks)[0], re.sub(r"zq\d+q", "#", last)[:160]))
        else:
            ids = sorted(toks)
            check(part, mode, set(ids[:len(ids) // 2]))
            check(part, mode, set(ids[len(ids) // 2:]))
    for part, ids in sorted(parts.items()):
        for mode in (("all",) if part in ("main", "inline_subject") else ("all", "diff", "ctx")):
            check(part, mode, ids)
    # A single template whose change the build cannot place fails one of the
    # build's own consistency checks; the recorder then refuses everything.
    known = [re.compile(r"^variant \S+ of \S+ touches the inline subject$"),  # a time in an inline subject
             re.compile(r"^AssertionError: \[.*\]$"),  # the top section's 'your team' claim
             re.compile(r"^AssertionError: [\w.]+$")]  # no_call_link + no_loom_url == no_call_link_or_loom
    unexpected = [f for f in failures if not any(k.match(f[3]) for k in known)]
    assert not unexpected, unexpected[:5]
    assert stats["shown"] > 1000, stats


# ------------------------------------------------ binding to the build
def test_write_needs_a_doc_id_known_to_uploads(doc, fresh, plain, tmp_path, approvals_file, log, capsys):
    export = _write(tmp_path, plain)
    assert _run(fresh, export, approvals_file, log, "--write", "--done-quote", QUOTE) == 1
    assert "--doc-id" in capsys.readouterr().out
    assert _run(fresh, export, approvals_file, log, "--write", "--doc-id", "some-other-doc", "--done-quote", QUOTE,
                "--checked-comments") == 1
    assert "uploads.json has no doc some-other-doc" in log.rows[-1][2]["reason"]
    json.dump({"uploads": [{"doc_id": DOC_ID, "fingerprint": "0" * 16}]}, open(rda.UPLOADS_PATH, "w"))
    assert _run(fresh, export, approvals_file, log, *_write_args()) == 1
    assert "not this export's build" in log.rows[-1][2]["reason"]
    assert not approvals_file.exists()


def test_a_tampered_or_unknown_build_is_refused(doc, fresh, plain, tmp_path, approvals_file, log, builds_dir):
    fake = "0123456789abcdef"
    text = plain.replace(doc["fingerprint"], fake)
    assert _run(fresh, _write(tmp_path, text), approvals_file, log, *_write_args()) == 1
    assert "no readable build" in log.rows[-1][2]["reason"]
    tampered = copy.deepcopy(doc["manifest"])
    tampered["fingerprint"] = fake
    os.makedirs(os.path.join(builds_dir, fake), exist_ok=True)
    json.dump(tampered, open(os.path.join(builds_dir, fake, "manifest.json"), "w"))
    assert _run(fresh, _write(tmp_path, text), approvals_file, log) == 1
    try:
        rda.load_doc_build(fake)
        raise AssertionError("tampered build accepted")
    except rda.Refused as exc:
        assert "does not hash to its fingerprint" in str(exc)
    finally:
        shutil.rmtree(os.path.join(builds_dir, fake))
    lines = plain.split("\n")
    k = next(i for i, l in enumerate(lines) if "(tag: X-BUILD)" in l)
    lines.insert(k, lines[k])
    assert _run(fresh, _write(tmp_path, "\n".join(lines)), approvals_file, log, *_write_args()) == 1
    assert not approvals_file.exists()


@pytest.mark.parametrize("quote", [None, "   ", "ok go ahead", "undone"])
def test_write_needs_a_done_quote(doc, fresh, plain, tmp_path, approvals_file, log, quote):
    args = ["--write", "--doc-id", DOC_ID, "--checked-comments"] + (["--done-quote", quote] if quote is not None else [])
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *args) == 1
    assert not approvals_file.exists() and log.rows == []


def test_write_needs_the_comments_check(doc, fresh, plain, tmp_path, approvals_file, log, capsys):
    args = ["--write", "--doc-id", DOC_ID, "--done-quote", QUOTE]
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *args) == 1
    assert "--checked-comments" in capsys.readouterr().out
    assert not approvals_file.exists() and log.rows == []
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *(args + ["--checked-comments"])) == 0
    assert log.rows[-1][1] == "ok" and log.rows[-1][2]["checked_comments"] is True


def test_the_quote_goes_into_approved_by(doc, fresh, plain, tmp_path, approvals_file, log):
    quote = "Done.  Looks good,   ship the emails"
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, "--write", "--doc-id", DOC_ID,
                "--done-quote", quote, "--checked-comments") == 0
    rec = json.loads(approvals_file.read_text(encoding="utf-8"))["approvals"]["cadence.d7"]
    assert rec["approved_by"] == 'Lorenzo (Google Doc): "Done. Looks good, ship the emails", build %s' % (
        doc["fingerprint"][:12])


# ------------------------------------------------------ refusals and safety
def test_dry_run_writes_nothing(doc, fresh, plain, tmp_path, approvals_file, log, capsys):
    export = _write(tmp_path, plain)
    assert _run(fresh, export, approvals_file, log) == 0
    assert not approvals_file.exists()
    approvals_file.write_text('{"version": 1, "approvals": {}}\n', encoding="utf-8")
    before = approvals_file.read_bytes()
    assert _run(fresh, export, approvals_file, log, "--done-quote", QUOTE, "--doc-id", DOC_ID) == 0
    assert approvals_file.read_bytes() == before and log.rows == []
    out = capsys.readouterr().out
    assert "will approve (96):" in out and "Dry run: nothing was written" in out


def test_duplicate_tags_refuse_the_whole_doc(doc, fresh, plain, tmp_path, approvals_file, log):
    lines = plain.split("\n")
    k = _tag_index(lines, "cadence.d7")
    lines[k:k] = ["Day 1 follow-up (tag: cadence.d1)", "stray"]
    export = _write(tmp_path, "\n".join(lines))
    assert _run(fresh, export, approvals_file, log, *_write_args()) == 1
    assert not approvals_file.exists()
    assert [r[1] for r in log.rows] == ["refused"] and "duplicate tags" in log.rows[0][2]["reason"]
    assert _run(fresh, export, approvals_file, log) == 1


def test_copies_of_one_sentence_changed_differently_refuse_the_whole_doc(doc, fresh, plain, tmp_path,
                                                                         approvals_file, log):
    groups = {}
    for b in _template_blocks(doc):
        if b["kind"] == "template_variant" and b["text"].strip():
            groups.setdefault(b["text_group"], []).append(b)
    g = next(bs for bs in groups.values() if len(bs) >= 2)
    first = g[0]["text"].split("\n")[0]
    text = replace_line(plain, g[0]["tag"], first, "One version of the new line {booking_url}")
    text = replace_line(text, g[1]["tag"], first, "Another version of the new line {booking_url}")
    assert any("changed differently" in w for w in _plan(text, doc, fresh)["whole"])
    assert _run(fresh, _write(tmp_path, text), approvals_file, log, *_write_args()) == 1
    assert not approvals_file.exists()


def test_a_failed_fresh_build_refuses_everything(plain, tmp_path, approvals_file, log):
    def broken(out_dir):
        raise fresh_manifest.FreshBuildError("build.py failed")
    rc = rda.main([_write(tmp_path, plain), "--approvals-file", str(approvals_file)] + list(_write_args()),
                  log_fn=log, build=broken)
    assert rc == 1 and not approvals_file.exists() and log.rows[-1][1] == "refused"


def test_a_doc_with_no_tags_is_refused(fresh, tmp_path, approvals_file, log):
    assert _run(fresh, _write(tmp_path, "just some text\n"), approvals_file, log) == 1
    assert not approvals_file.exists()


def test_existing_approvals_and_auto_send_are_kept(doc, fresh, plain, tmp_path, approvals_file, log):
    index = ta.catalogue_index()
    m, m_line = _unique_block(doc, "template_main", exclude=("cadence.d7", "cadence.d14"))
    edited = m["template_id"]
    rec = lambda sha, note: {"sha256": sha, "approved_at": "2026-09-01T00:00:00+00:00",
                             "approved_by": "Lorenzo", "text_preview": note}
    kept_current = rec(index["cadence.d7"]["sha256"], "kept as is")
    refused_current = rec(index[edited]["sha256"], "refused but approved")
    other = rec("1" * 64, "not in the catalogue")
    stale = rec("2" * 64, "will be refreshed")
    held_old = rec("3" * 64, "held, stays")
    start = {"version": 1, "auto_send": False, "note": "left alone",
             "approvals": {"cadence.d7": kept_current, edited: refused_current, "retired.template": other,
                           "cadence.d14": stale, HELD[0]: held_old}}
    approvals_file.write_text(json.dumps(start), encoding="utf-8")
    text = replace_line(plain, m["tag"], m_line, "Some brand new words for this email.")
    plan = _plan(text, doc, fresh, ta.load_approvals(approvals_file))
    notes = dict((r["id"], r.get("note")) for r in plan["refused"])
    assert notes[edited] == rda.KEEPS_SENDING and notes[HELD[0]] == rda.OLD_APPROVAL
    assert _run(fresh, _write(tmp_path, text), approvals_file, log, *_write_args()) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert data["auto_send"] is False and data["note"] == "left alone" and data["version"] == 1
    assert data["approvals"]["cadence.d7"] == kept_current
    assert data["approvals"][edited] == refused_current
    assert data["approvals"]["retired.template"] == other
    assert data["approvals"][HELD[0]] == held_old
    assert data["approvals"]["cadence.d14"]["sha256"] == index["cadence.d14"]["sha256"]
    assert ta.kill_switch_on(approvals_file)
    d = log.rows[-1][2]
    assert "cadence.d7" in d["unchanged"] and "cadence.d14" in d["approved"] and edited not in d["approved"]


def _patched_index(tid, calls_before_change=0):
    real = ta.catalogue_index
    state = {"calls": 0}

    def fake(entries=None):
        idx = real(entries)
        state["calls"] += 1
        if state["calls"] > calls_before_change:
            idx = dict(idx)
            idx[tid] = dict(idx[tid], sha256="4" * 64)
        return idx
    return fake


def test_hash_race_before_the_plan_is_refused(doc, fresh, plain, tmp_path, approvals_file, log, monkeypatch):
    monkeypatch.setattr(ta, "catalogue_index", _patched_index("cadence.d7"))
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *_write_args()) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert "cadence.d7" not in data["approvals"] and len(data["approvals"]) == 95
    assert log.rows[-1][2]["refused"]["cadence.d7"][0].startswith("the code changed after the fresh build")


def test_hash_race_between_the_plan_and_the_write_is_not_written(doc, fresh, plain, tmp_path, approvals_file, log,
                                                                  monkeypatch, capsys):
    monkeypatch.setattr(ta, "catalogue_index", _patched_index("cadence.d7", calls_before_change=1))
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *_write_args()) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert "cadence.d7" not in data["approvals"] and len(data["approvals"]) == 95
    assert log.rows[-1][2]["refused"]["cadence.d7"][0].startswith("the code changed after the fresh build")
    assert "refused at write time: cadence.d7" in capsys.readouterr().out


def test_the_registry_refusing_the_plan_writes_nothing(doc, fresh, plain, tmp_path, approvals_file, log,
                                                       monkeypatch):
    def boom(*a, **k):
        raise ta.ApprovalError("these templates changed since the review file was exported")
    monkeypatch.setattr(ta, "plan_approve", boom)
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *_write_args()) == 1
    assert not approvals_file.exists() and log.rows[-1][1] == "refused"


# ------------------------------------------------------------ build.py
def test_build_defaults_to_a_fingerprint_folder_and_leaves_the_top_level_alone(tmp_path):
    code_root = os.path.dirname(os.path.dirname(TOOL_DIR))
    tool = tmp_path / "tools" / "template_doc"
    tool.mkdir(parents=True)
    for name in ("build.py", "export_parse.py", "doc_areas.py", "doc_rules.py", "parse_doc.py", "diff_doc.py",
                 "templates_export_final.md", "manifest.json", "advero_all_emails.html"):
        shutil.copy(os.path.join(TOOL_DIR, name), str(tool / name))
    snap_rel = "config/snapshots/instantly_campaigns_2026-09-21.json"
    (tmp_path / "config" / "snapshots").mkdir(parents=True)
    shutil.copy(os.path.join(code_root, snap_rel), str(tmp_path / snap_rel))
    before = dict((n, (tool / n).read_bytes()) for n in ("manifest.json", "advero_all_emails.html"))
    proc = subprocess.run([sys.executable, "build.py"], cwd=str(tool), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True)
    assert proc.returncode == 0, proc.stdout[-2000:]
    fp = re.search(r"fingerprint: ([0-9a-f]{16})", proc.stdout).group(1)
    built = json.loads((tool / "builds" / fp / "manifest.json").read_text(encoding="utf-8"))
    assert built["fingerprint"] == fp == doc_areas.fingerprint(built["blocks"], built["visible"])
    plain = doc_areas.html_to_text(str(tool / "builds" / fp / "advero_all_emails.html"))
    assert doc_areas.read_fingerprint(plain) == (fp, None)
    for n, data in before.items():
        assert (tool / n).read_bytes() == data


def test_uploads_records_the_legacy_doc():
    data = json.load(io.open(os.path.join(TOOL_DIR, "uploads.json"), encoding="utf-8"))
    (u,) = [u for u in data["uploads"] if u["doc_id"] == "1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U"]
    assert u["fingerprint"] is None and u["uploaded_at"] == "2026-09-23T17:59Z"
