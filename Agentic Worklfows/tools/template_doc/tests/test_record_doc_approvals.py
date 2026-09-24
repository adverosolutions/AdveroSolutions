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
import html
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


def html_of(text):
    """A plain HTML file whose text is exactly these lines (no styles): what
    Drive's text/html export of an unformatted doc reads back as."""
    body = "".join("<p>%s</p>\n" % html.escape(l, quote=False) if l.strip() else "<p><br></p>\n"
                   for l in text.replace("\r\n", "\n").lstrip(u"﻿").split("\n"))
    return '<html><head><meta charset="utf-8"></head><body>%s</body></html>' % body


def _run(fresh, export, approvals, log, *extra):
    """--write runs get --html: a plain HTML export of the same text, unless the test passes its own."""
    extra = list(extra)
    if "--write" in extra and "--html" not in extra:
        path = export + ".html"
        io.open(path, "w", encoding="utf-8").write(html_of(io.open(export, encoding="utf-8-sig").read()))
        extra += ["--html", path]
    return rda.main([export, "--approvals-file", str(approvals)] + extra, log_fn=log,
                    build=lambda out_dir: fresh)


def _write_args():
    return ("--write", "--doc-id", DOC_ID, "--done-quote", QUOTE, "--checked-comments")


def _doc_build(doc):
    return rda.load_doc_build(doc["fingerprint"])


def _plan(text, doc, fresh, approvals=None):
    return rda.evaluate(text, _doc_build(doc), fresh, approvals or ta.empty_approvals())


def _refused(plan):
    return dict((r["id"], r["reasons"]) for r in plan["refused"])


INDEX = ta.catalogue_index()
ORDER = [e["id"] for e in ta.catalogue() if e.get("approvable")]  # the approvable ids, catalogue order
APPROVABLE = set(ORDER)
HELD = sorted(i for i in INDEX if doc_rules.is_held(i))
# The catalogue's own structure, read from its ids: spliced line -> its cadence email
SPLICED = dict((t, doc_rules.splice_host(t, APPROVABLE)) for t in ORDER if doc_rules.splice_host(t, APPROVABLE))
HOSTS = [t for t in ORDER if t in set(SPLICED.values())]
# cadence emails with no spliced lines: nothing else stands or falls with them
PLAIN_CADENCE = [t for t in ORDER if doc_rules.section_of(t) == "cadence" and t not in SPLICED and t not in HOSTS]
READ_ONLY = sorted(t for t, e in INDEX.items() if not e.get("approvable") and doc_rules.splice_host(t, APPROVABLE))
CAD_A, CAD_B, CAD_C = PLAIN_CADENCE[:3]


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
    line no sentence of which a block of any other email carries (every line,
    with all_unique), of an id that is not held, not spliced, and not in
    exclude. (A version shares sentences with its own main text.)"""
    groups = {}
    for b in _template_blocks(doc):
        groups[b["text_group"]] = groups.get(b["text_group"], 0) + 1
    spliced = set(SPLICED) | set(HOSTS)
    tid_of = dict((b["tag"], b["template_id"]) for b in _template_blocks(doc))
    for b in _template_blocks(doc):
        tid = b["template_id"]
        if (b["kind"] == kind and groups[b["text_group"]] == 1 and tid not in exclude and tid not in spliced
                and not doc_rules.is_held(tid) and b["text"].strip()):
            lines = [l for l in b["text"].split("\n") if l.strip()]
            own = [l for l in lines if b["tag"] in _carriers(doc, l)
                   and set(tid_of[t] for t in _carriers(doc, l)) == {tid}]
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
    assert HELD and set(HELD) < set(approvable)
    # the one count check: the doc holds exactly the catalogue's approvable ids
    assert set(b["template_id"] for b in _template_blocks(doc)) == set(approvable) == set(fresh["hashes"])
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
    assert rda.SENDING_NOTE in out and ta.WIRED_NOTE not in out


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
    assert log.rows[-1][2]["approved"] == {}
    assert len(log.rows[-1][2]["unchanged"]) == len(fresh["hashes"]) - len(HELD)
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
    end = _block_end(lines, _tag_index(lines, CAD_A))
    lines[end:end] = ["If they are busy: (tag: %s/busy)" % CAD_A, "No rush at all.",
                      "Or this: (tag: %s.extra)" % CAD_A, "Maybe later."]
    plan = _plan("\n".join(lines), doc, fresh)
    assert _refused(plan)[CAD_A] == [rda.R_ADDED % (CAD_A + "/busy"), rda.R_ADDED % (CAD_A + ".extra")]
    assert plan["whole"] == []
    lines[end:end] = ["Something new: (tag: brand.new.email)", "Hello."]
    plan = _plan("\n".join(lines), doc, fresh)
    assert plan["whole"] == ["a tag in the doc matches no email: brand.new.email"]
    export = _write(tmp_path, "\n".join(lines))
    assert _run(fresh, export, approvals_file, log) == 1  # dry run reports, exits 1
    assert _run(fresh, export, approvals_file, log, *_write_args()) == 1
    assert not approvals_file.exists()


# ------------------------------------------------------ the repeat rule
def _time_offer(doc):
    """The line most first replies share: the one with {slots} that the
    most main texts carry as a line of their own."""
    counts = {}
    for b in _template_blocks(doc):
        if b["kind"] == "template_main" and b["template_id"].startswith("first_reply."):
            for l in set(b["text"].split("\n")):
                if "{slots}" in l:
                    counts[l] = counts.get(l, 0) + 1
    return max(sorted(counts), key=lambda l: counts[l])


def test_the_time_offer_line_edited_once_refuses_every_email_with_it(doc, fresh, plain):
    offer = _time_offer(doc)
    holders = sorted(b["template_id"] for b in _template_blocks(doc) if offer in b["text"].split("\n"))
    assert len(holders) >= 2
    tag = holders[0]
    text = replace_line(plain, tag, offer, "Would {slots} work for a quick 10-minute call?")
    refused = _refused(_plan(text, doc, fresh))
    for tid in holders[1:]:
        assert rda.R_REPEAT % tag in refused[tid], tid


def test_a_sentence_edited_inside_a_longer_line_refuses_every_email_carrying_it(doc, fresh, plain):
    """The doc promises sentences: editing the time-offer sentence once, inside
    a longer line of one version (a first reply's "the time they asked for is
    tough" line), refuses every email that carries that sentence anywhere,
    also where it is a line of its own (the first replies' main texts), and
    exactly the emails route_doc lists as "also appears in"."""
    offer = _time_offer(doc)
    longer = [b for b in _template_blocks(doc) if b["kind"] == "template_variant" and not doc_rules.is_held(
        b["template_id"]) and any(offer in l and l != offer for l in b["text"].split("\n"))]
    assert longer
    block = longer[0]
    tag, tid0 = block["tag"], block["template_id"]
    line = next(l for l in block["text"].split("\n") if offer in l and l != offer)
    text = replace_line(plain, tag, line, line.replace(offer, "Would {slots} work for a quick chat?"))
    refused = _refused(_plan(text, doc, fresh))
    carrying = [b for b in _template_blocks(doc) if offer in b["text"]]
    whole_line = [b["tag"] for b in carrying if offer in b["text"].split("\n")]
    inside = [b["tag"] for b in carrying if b["tag"] not in whole_line and b["tag"] != tag]
    assert whole_line and inside  # a line of its own in some blocks, inside a longer line in others
    carriers = sorted(set(b["template_id"] for b in carrying))
    for tid in carriers:
        assert tid in refused, tid
        if tid != tid0:
            assert rda.R_REPEAT % tag in refused[tid], tid
    report = route_doc.build_report(text, doc["manifest"])
    (entry,) = [e for es in report["sections"].values() for e in es if e["tag"] == tag]
    by_tag = dict((b["tag"], b) for b in doc["manifest"]["blocks"])
    listed = set(by_tag[t]["template_id"] for ts in entry["also_in"].values() for t in ts
                 if by_tag[t].get("template_id"))
    repeat = set(tid for tid, rs in refused.items() if rda.R_REPEAT % tag in rs)
    assert listed <= repeat  # route_doc's list, and the recorder's stricter rule on top


@pytest.mark.parametrize("kind", ["template_variant", "template_subject"])
def test_a_shared_block_edited_once_refuses_every_copy(doc, fresh, plain, kind):
    groups = {}
    for b in _template_blocks(doc):
        if b["kind"] == kind and b["text"].strip():
            groups.setdefault(b["text_group"], []).append(b)
    group = max(groups.values(), key=len)
    assert len(group) >= 2
    first = group[0]
    if kind == "template_subject":
        text = edit_subject(plain, first["tag"], "Quick follow-up")
    else:
        text = replace_line(plain, first["tag"], first["text"].split("\n")[0], "Grab any time here: {booking_url}")
    refused = _refused(_plan(text, doc, fresh))
    for b in group[1:]:
        assert rda.R_REPEAT % first["tag"] in refused[b["template_id"]], b["tag"]


def test_a_cadence_email_and_its_spliced_lines_stand_or_fall_together(doc, fresh, plain):
    recorded = dict((b["template_id"], b["spliced_into"]) for b in doc["manifest"]["blocks"] if b.get("spliced_into"))
    assert recorded == SPLICED and HOSTS
    counts = _line_count(doc)
    tested = []
    for host in HOSTS:
        frags = [f for f, h in SPLICED.items() if h == host]
        hb = next(b for b in doc["manifest"]["blocks"] if b["tag"] == host)
        line = next(l for l in hb["text"].split("\n") if l.strip() and counts[l.strip()] == 1)
        refused = _refused(_plan(replace_line(plain, host, line, "A new line."), doc, fresh))
        for frag in frags:
            assert rda.R_SPLICE_HOST % host in refused[frag], frag
        # a line whose words no other block carries, so only the host spreads the refusal
        fb = next((b for b in doc["manifest"]["blocks"] if b["tag"] in frags
                   and counts[b["text"].split("\n")[0].strip()] == 1), None)
        if fb is None:
            continue
        frag = fb["tag"]
        refused = _refused(_plan(replace_line(plain, frag, fb["text"].split("\n")[0], "New words."), doc, fresh))
        # the host is refused for its line (and, when its note writes the line out, for carrying its words)
        assert set(refused[host]) <= {rda.R_SPLICE_FRAG % frag, rda.R_REPEAT % frag} and refused[host]
        for other in frags:
            assert other in refused
        tested.append(host)
    assert tested


def test_a_line_that_is_not_approvable_is_read_only_and_never_recorded(doc, fresh, plain, tmp_path, approvals_file,
                                                                       log):
    """cadence.e2.research_line (written for each lead, no fixed text) shows
    as a note on its email, has no tag, and "done" never approves it; nor any
    other catalogue entry that is not approvable."""
    assert "cadence.e2.research_line" in READ_ONLY
    reader = doc_areas.DocReader(plain)
    tags = set(b["tag"] for b in doc["manifest"]["blocks"])
    for rid in READ_ONLY:
        host = doc_rules.splice_host(rid, APPROVABLE)
        assert rid not in tags and rid not in fresh["hashes"] and rid not in reader.items
        assert [n for n in reader.notes(host) if rid in n and "does not approve" in n], host
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *_write_args()) == 0
    written = set(json.loads(approvals_file.read_text(encoding="utf-8"))["approvals"])
    assert written <= APPROVABLE and not (written & set(READ_ONLY))
    # a block typed for it in the doc refuses its email and records nothing for it
    rid = READ_ONLY[0]
    host = doc_rules.splice_host(rid, APPROVABLE)
    lines = plain.split("\n")
    end = _block_end(lines, _tag_index(lines, host))
    lines[end:end] = ["The AI line (tag: %s)" % rid, "Some words."]
    plan = _plan("\n".join(lines), doc, fresh)
    assert rda.R_ADDED % rid in _refused(plan)[host] and plan["whole"] == []
    assert rid not in [p["id"] for p in plan["approve"] + plan["already"] + plan["refused"]]
    # and its note is part of its email: an edit to it refuses the email
    lines = plain.split("\n")
    k = _note_index(lines, host, "Read only:")
    lines[k] = "Read only: send the AI line too. (note)"
    assert rda.R_AREA % host in _refused(_plan("\n".join(lines), doc, fresh))[host]


def test_the_doc_says_how_approved_emails_are_sent(doc, plain):
    """First replies are drafts Lorenzo sends himself; other replies go out on
    their own only once a reply of his reached the lead, the Locked in
    confirmation excepted. No line says approved emails simply send."""
    low = plain.lower()
    assert "send automatically" not in low and "sends automatically" not in low
    assert "you send them yourself from the email thread" in plain
    assert "only after a reply of yours has reached" in plain and "Locked in booking confirmation" in plain


# ---------------------------------------------- lines outside block bodies
def _fallbacks(doc, tid):
    b = next((x for x in doc["manifest"]["blocks"] if x["tag"] == tid + "/subject"), {})
    return [l.split(": ", 1)[1] for l in b.get("fixed_fallbacks") or []]


def test_an_edited_fallback_subject_note_refuses_that_email(doc, fresh, plain):
    """The fallback subject is template words the doc shows in a note: an edit
    refuses that email and, as the doc says a change changes everywhere,
    every email with the same fallback subject."""
    lines = plain.split("\n")
    i = _tag_index(lines, CAD_A + "/subject")
    assert lines[i + 1].startswith("If their email had no subject:") and lines[i + 1].endswith("(note)")
    old = lines[i + 1]
    lines[i + 1] = "If their email had no subject: URGENT: pay the invoice today. (note)"
    refused = _refused(_plan("\n".join(lines), doc, fresh))
    assert rda.R_AREA % CAD_A in refused[CAD_A]
    gone = [f for f in _fallbacks(doc, CAD_A) if f not in lines[i + 1] and f in old]
    same = set(t for t in fresh["hashes"] if set(gone) & set(_fallbacks(doc, t)))
    assert gone and len(same) > 1
    assert same | {CAD_A} <= set(refused)
    # nothing else, but the lines spliced into a refused follow-up email
    assert set(refused) - set(HELD) - same - {CAD_A} <= set(f for f, h in SPLICED.items() if h in same)
    for t in same - {CAD_A}:
        assert rda.R_REPEAT % CAD_A in refused[t], t
    # a note changed with every fallback still in it word for word refuses only its own email
    lines[i + 1] = old.replace(gone[0], gone[0] + " ")
    refused = _refused(_plan("\n".join(lines), doc, fresh))
    assert sorted(refused) == sorted(set(HELD) | {CAD_A}) and refused[CAD_A] == [rda.R_AREA % CAD_A]


def _note_index(lines, tag, startswith):
    i = _tag_index(lines, tag)
    for k in range(i + 1, _block_end(lines, i)):
        if lines[k].startswith(startswith) and lines[k].rstrip().endswith("(note)"):
            return k
    raise AssertionError("no note %r in %s" % (startswith, tag))


def _quoting_version(doc):
    """A version block shown as one "Instead of" change, of an email that is
    not held and has no spliced lines."""
    for b in _template_blocks(doc):
        ch = b.get("changes") or []
        if (b["kind"] == "template_variant" and len(ch) == 1 and ch[0]["kind"] == "instead"
                and not doc_rules.is_held(b["template_id"]) and b["template_id"] not in SPLICED
                and b["template_id"] not in HOSTS):
            return b
    raise AssertionError("no version shown as one change")


def test_the_lines_a_version_quotes_are_compared(doc, fresh, plain):
    """The quoted main-text lines of a version are part of what "done" is
    checked against: an edited, deleted or moved quote refuses that email,
    and a quote edited or deleted refuses every email that shows that line
    (the doc says a change changes everywhere)."""
    b = _quoting_version(doc)
    tag, tid = b["tag"], b["template_id"]
    quoted = b["changes"][0]["quoted"][0]
    lines = plain.split("\n")
    k = _note_index(lines, tag, 'Instead of "')
    edited = list(lines)
    edited[k] = 'Instead of "%s.": (note)' % quoted[:-1]
    moved = list(lines)
    moved[k], moved[k + 1] = lines[k + 1], lines[k]
    deleted = lines[:k] + lines[k + 1:]
    carriers = set(x["template_id"] for x in _template_blocks(doc) if quoted in x["text"])
    assert len(carriers) > 1
    refused = _refused(_plan("\n".join(moved), doc, fresh))
    assert sorted(refused) == sorted(set(HELD) | {tid}) and refused[tid] == [rda.R_AREA % tag]
    for variant_text in (edited, deleted):
        refused = _refused(_plan("\n".join(variant_text), doc, fresh))
        assert rda.R_AREA % tag in refused[tid]
        assert carriers <= set(refused)
        for t in carriers - {tid}:
            assert rda.R_REPEAT % tag in refused[t], t


def test_edits_to_headings_and_labels_refuse_those_emails(doc, fresh, plain):
    v = _quoting_version(doc)
    text = edit_tag_line(plain, CAD_A, "Follow-up: DO NOT SEND THIS ONE (tag: %s)" % CAD_A)
    text = edit_tag_line(text, v["tag"], "In this case send nothing at all: (tag: %s)" % v["tag"])
    refused = _refused(_plan(text, doc, fresh))
    assert refused[CAD_A] == [rda.R_AREA % CAD_A]
    assert refused[v["template_id"]] == [rda.R_AREA % v["tag"]]


def test_an_instruction_after_a_section_line_refuses_that_section(doc, fresh, plain):
    lines = plain.split("\n")
    s = next(k for k, l in enumerate(lines) if l.startswith("No-show recovery") and l.endswith("(section)"))
    lines[s + 1:s + 1] = ["Do not send any of the no-show emails below, I will handle no-shows by phone."]
    plan = _plan("\n".join(lines), doc, fresh)
    refused = _refused(plan)
    no_show = sorted(i for i in fresh["hashes"] if doc_rules.section_of(i) == "no_show")
    assert no_show
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
    """The 18:15Z export of the doc in Drive (built before fingerprints and
    before the follow-ups became cadence.e1..e10): cadence.d1 and cadence.d2
    edited, both no_slots variants deleted, and a note to Claude typed after
    cadence.d2's fallback-subject note. The d emails are no longer in the
    catalogue; every follow-up email now is refused as not in that doc."""
    text = io.open(FIRST_EDITS, encoding="utf-8-sig").read()
    assert doc_areas.read_fingerprint(text) == (None, None)
    plan = rda.evaluate(text, rda.load_doc_build(None), fresh, ta.empty_approvals())
    refused = _refused(plan)
    assert not [t for t in refused if t.startswith("cadence.d")]  # only catalogue ids are ever planned
    for tid in ORDER:
        if doc_rules.section_of(tid) == "cadence":
            assert rda.R_NOT_IN_DOC in refused[tid], tid
    for tid in HELD:
        assert rda.R_HELD in refused[tid]
    # the removed line "Or if it's easier, grab a time here: {booking_url}" was in other emails too
    assert rda.R_REPEAT % "cadence.d1" in refused["booking.counter.weekend"]
    # the doc in Drive does not show the time formats block: nothing with a time can be approved from it
    for tid in fresh["manifest"]["blocks"][0]["dependents"]:
        assert tid in refused
    approved = set(p["id"] for p in plan["approve"])
    assert not (approved & set(refused)) and approved <= APPROVABLE

    rc = rda.main([FIRST_EDITS, "--approvals-file", str(approvals_file)], log_fn=log)  # real fresh build
    out = capsys.readouterr().out
    assert rc == 1 and rda.W_LEGACY in out and "Dry run: nothing was written" in out
    assert not approvals_file.exists() and log.rows == []
    html_path = _write(tmp_path, html_of(text), "first_edits.html")
    rc = rda.main([FIRST_EDITS, "--approvals-file", str(approvals_file), "--write", "--doc-id",
                   "1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U", "--done-quote", "done", "--checked-comments",
                   "--html", html_path], log_fn=log)
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
    assert len(changed) * 2 >= len([x for x in b["manifest"]["blocks"] if x.get("depends_on")]) > 0
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
    """Round two's X1, for the e ladder: follow-up email 3 drops its greeting
    when the first name is missing (the version the top section would
    otherwise explain)."""
    def build_touch(state, day, slots, *a, **k):
        t = orig(state, day, slots, *a, **k)
        if not getattr(state, "first_name", None) and day == 3:
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
        assert changed == ["cadence.e3"]
        assert new_reader.notes("cadence.e3/missing_lead_data")[0] == 'Leaves out "Hey {first_name},".'
        assert new_reader.part("cadence.e3", "missing_lead_data")[0] != "Hey there,"
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
             re.compile(r"^the top section would say a follow-up email that names the company is held"),
             re.compile(r"^AssertionError: [\w.]+$")]  # no_call_link + no_loom_url == no_call_link_or_loom
    unexpected = [f for f in failures if not any(k.match(f[3]) for k in known)]
    assert not unexpected, unexpected[:5]
    assert stats["shown"] > 10 * len(fresh["hashes"]), stats  # the sweep really ran


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
    rec = json.loads(approvals_file.read_text(encoding="utf-8"))["approvals"][CAD_A]
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
    assert "will approve (%d):" % (len(fresh["hashes"]) - len(HELD)) in out
    assert "Dry run: nothing was written" in out


def test_duplicate_tags_refuse_the_whole_doc(doc, fresh, plain, tmp_path, approvals_file, log):
    lines = plain.split("\n")
    k = _tag_index(lines, CAD_B)
    lines[k:k] = ["Follow-up (tag: %s)" % CAD_A, "stray"]
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
    rc = rda.main([_write(tmp_path, plain), "--approvals-file", str(approvals_file)] + list(_write_args())
                  + ["--html", _write(tmp_path, html_of(plain), "export.html")], log_fn=log, build=broken)
    assert rc == 1 and not approvals_file.exists() and log.rows[-1][1] == "refused"


def test_a_doc_with_no_tags_is_refused(fresh, tmp_path, approvals_file, log):
    assert _run(fresh, _write(tmp_path, "just some text\n"), approvals_file, log) == 1
    assert not approvals_file.exists()


def test_existing_approvals_and_auto_send_are_kept(doc, fresh, plain, tmp_path, approvals_file, log):
    index = ta.catalogue_index()
    m, m_line = _unique_block(doc, "template_main", exclude=(CAD_A, CAD_B))
    edited = m["template_id"]
    rec = lambda sha, note: {"sha256": sha, "approved_at": "2026-09-01T00:00:00+00:00",
                             "approved_by": "Lorenzo", "text_preview": note}
    kept_current = rec(index[CAD_A]["sha256"], "kept as is")
    refused_current = rec(index[edited]["sha256"], "refused but approved")
    other = rec("1" * 64, "not in the catalogue")
    stale = rec("2" * 64, "will be refreshed")
    held_old = rec("3" * 64, "held, stays")
    start = {"version": 1, "auto_send": False, "note": "left alone",
             "approvals": {CAD_A: kept_current, edited: refused_current, "retired.template": other,
                           CAD_B: stale, HELD[0]: held_old}}
    approvals_file.write_text(json.dumps(start), encoding="utf-8")
    text = replace_line(plain, m["tag"], m_line, "Some brand new words for this email.")
    plan = _plan(text, doc, fresh, ta.load_approvals(approvals_file))
    notes = dict((r["id"], r.get("note")) for r in plan["refused"])
    assert notes[edited] == rda.KEEPS_SENDING and notes[HELD[0]] == rda.OLD_APPROVAL
    assert _run(fresh, _write(tmp_path, text), approvals_file, log, *_write_args()) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert data["auto_send"] is False and data["note"] == "left alone" and data["version"] == 1
    assert data["approvals"][CAD_A] == kept_current
    assert data["approvals"][edited] == refused_current
    assert data["approvals"]["retired.template"] == other
    assert data["approvals"][HELD[0]] == held_old
    assert data["approvals"][CAD_B]["sha256"] == index[CAD_B]["sha256"]
    assert ta.kill_switch_on(approvals_file)
    d = log.rows[-1][2]
    assert CAD_A in d["unchanged"] and CAD_B in d["approved"] and edited not in d["approved"]


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
    monkeypatch.setattr(ta, "catalogue_index", _patched_index(CAD_A))
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *_write_args()) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert CAD_A not in data["approvals"] and len(data["approvals"]) == len(fresh["hashes"]) - len(HELD) - 1
    assert log.rows[-1][2]["refused"][CAD_A][0].startswith("the code changed after the fresh build")


def test_hash_race_between_the_plan_and_the_write_is_not_written(doc, fresh, plain, tmp_path, approvals_file, log,
                                                                  monkeypatch, capsys):
    monkeypatch.setattr(ta, "catalogue_index", _patched_index(CAD_A, calls_before_change=1))
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *_write_args()) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert CAD_A not in data["approvals"] and len(data["approvals"]) == len(fresh["hashes"]) - len(HELD) - 1
    assert log.rows[-1][2]["refused"][CAD_A][0].startswith("the code changed after the fresh build")
    assert "refused at write time: %s" % CAD_A in capsys.readouterr().out


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


# ------------------------------------------- round two: the reviewer's cases
def _carrying(doc, text):
    """Template ids whose blocks show this text anywhere."""
    return set(b["template_id"] for b in _template_blocks(doc) if text in b["text"])


def _block_span(lines, tag):
    """(start, end) of a version block: its label line up to the next tag or section line."""
    i = _tag_index(lines, tag)
    return i, _block_end(lines, i)


def test_no_exemptions_in_the_recorders_repeat_rule():
    """Unit level (today's catalogue shares no placeholder-only line): a gone
    placeholder-only line, greeting or sign-off finds every carrier."""
    shown = {"a": ["Hey {first_name},\n\n{zoom_link}\n\nLorenzo"], "b": ["x {zoom_link} y"], "c": ["nothing here"]}
    gone = rda._gone("Hey {first_name},\n{zoom_link}\nLorenzo", "Hi {first_name},\nthe link\nLorenzo V.")
    assert ("line", "{zoom_link}") in gone and ("sentence", "Hey {first_name},") in gone
    assert rda._carriers(gone, shown) == ["a", "b"]
    assert rda._gone("Would {slots} work?", "Would {slots} work? Happy to help.") == [("line", "Would {slots} work?")]


@pytest.mark.parametrize("case", ["greeting", "sign_off", "common_line_appended"])
def test_an_edit_to_shared_words_refuses_every_email_showing_them(doc, fresh, plain, case):
    """The doc says a change "changes everywhere". Greetings, sign-offs,
    placeholder-only sentences and very common lines have no exemption: an
    edit to them in one email refuses every email that shows the old words."""
    lines = plain.split("\n")
    if case == "greeting":
        tag, old, new = CAD_B, "Hey {first_name},", "Hi {first_name},"
    elif case == "sign_off":
        tag, old, new = CAD_A, "Lorenzo", "Lorenzo V."
    else:
        old = _time_offer(doc)
        tag = next(b["tag"] for b in _template_blocks(doc) if old in b["text"].split("\n")
                   and b["kind"] == "template_main" and not doc_rules.is_held(b["template_id"]))
        new = old + " Happy to work around you."
    carriers = _carrying(doc, old)
    assert len(carriers) > 1
    refused = _refused(_plan(replace_line(plain, tag, old, new), doc, fresh))
    tid = next(b["template_id"] for b in _template_blocks(doc) if b["tag"] == tag)
    for t in carriers - {tid}:
        assert rda.R_REPEAT % tag in refused[t], t


def test_a_deleted_blank_line_or_an_added_one_is_an_edit(doc, fresh, plain):
    """Paragraph breaks are part of the hash: joining or splitting paragraphs
    refuses the email; Drive doubling an empty paragraph does not."""
    lines = plain.split("\n")
    i = _tag_index(lines, CAD_B)
    j = next(k for k in range(i + 1, _block_end(lines, i)) if not lines[k].strip())
    joined = lines[:j] + lines[j + 1:]
    assert rda.R_EDITED % CAD_B in _refused(_plan("\n".join(joined), doc, fresh))[CAD_B]
    two = next(b for b in _template_blocks(doc) if b["kind"] == "template_main" and not doc_rules.is_held(
        b["template_id"]) and b["template_id"] not in SPLICED and any(
        x.strip() and y.strip() for x, y in zip(b["text"].split("\n"), b["text"].split("\n")[1:])))
    first = next(x for x, y in zip(two["text"].split("\n"), two["text"].split("\n")[1:]) if x.strip() and y.strip())
    k = _line_in_block(lines, two["tag"], first)
    split = lines[:k + 1] + [""] + lines[k + 1:]
    assert rda.R_EDITED % two["tag"] in _refused(_plan("\n".join(split), doc, fresh))[two["template_id"]]
    doubled = lines[:j] + [""] + lines[j:]
    assert sorted(_refused(_plan("\n".join(doubled), doc, fresh))) == HELD


def _movable_version(doc):
    """(version block, another email after it): neither held nor spliced."""
    blocks = _template_blocks(doc)
    for n, b in enumerate(blocks):
        tid = b["template_id"]
        if b["kind"] != "template_variant" or doc_rules.is_held(tid) or tid in SPLICED or tid in HOSTS:
            continue
        for later in blocks[n + 1:]:
            t2 = later["template_id"]
            if (later["kind"] == "template_variant" and t2 != tid and not doc_rules.is_held(t2)
                    and t2 not in SPLICED and t2 not in HOSTS):
                return b, later
    raise AssertionError("no movable version")


def test_a_moved_version_or_subject_line_refuses_both_emails(doc, fresh, plain):
    """A version moved under another email, or a Subject line moved into
    another email, reads as that email's in the doc: both are refused."""
    v, target = _movable_version(doc)
    lines = plain.split("\n")
    a, b = _block_span(lines, v["tag"])
    blk, rest = lines[a:b], lines[:a] + lines[b:]
    k = _tag_index(rest, target["tag"])
    refused = _refused(_plan("\n".join(rest[:k] + blk + rest[k:]), doc, fresh))
    assert rda.R_MOVED % v["tag"] in refused[v["template_id"]]
    assert rda.R_MOVED_INTO % v["tag"] in refused[target["template_id"]]
    # the e1-into-e3 case: a follow-up email's Subject line moved into another
    i = _tag_index(lines, CAD_A + "/subject")
    s, rest = lines[i], lines[:i] + lines[i + 1:]
    k = _tag_index(rest, CAD_C + "/subject")
    refused = _refused(_plan("\n".join(rest[:k + 1] + [s] + rest[k + 1:]), doc, fresh))
    assert rda.R_MOVED % (CAD_A + "/subject") in refused[CAD_A]
    assert rda.R_MOVED_INTO % (CAD_A + "/subject") in refused[CAD_C]
    # nothing moved, nothing refused for it
    assert not [r for rs in _refused(_plan(plain, doc, fresh)).values() for r in rs if "moved" in r]


def _html_with(plain, style_css="", span_attrs=None, line_hint=None):
    """html_of(plain) with <style> css, and one line's text wrapped in a span
    with span_attrs."""
    h = html_of(plain)
    if style_css:
        h = h.replace("<head>", "<head><style>%s</style>" % style_css, 1)
    if span_attrs is not None:
        esc = html.escape(line_hint, quote=False)
        assert esc in h
        h = h.replace(esc, "<span %s>%s</span>" % (span_attrs, esc), 1)
    return h


@pytest.mark.parametrize("case,css,attrs,expect", [
    ("strike_class", ".c7{text-decoration:line-through}", 'class="c7"', "struck through"),
    ("strike_inline", "", 'style="text-decoration: line-through"', "struck through"),
    ("strike_tag", "", None, "<s> markup"),
    ("highlight", ".c3{background-color:#ffff00}", 'class="c3"', "highlighted"),
    ("colour", "", 'style="color:#ff0000"', "coloured"),
    ("suggestion", "", 'id="suggest-insert-1"', "suggestion markup"),
    ("comment", "", 'id="cmnt_ref1"', "a comment"),
])
def test_the_html_export_refuses_formatting_and_suggestions(doc, fresh, plain, tmp_path, approvals_file, log,
                                                            case, css, attrs, expect):
    line = "Hey {first_name},"
    h = _html_with(plain, css, attrs, line) if attrs is not None or css else html_of(plain)
    if case == "strike_tag":
        h = h.replace(html.escape(line, quote=False), "<s>%s</s>" % html.escape(line, quote=False), 1)
    problems = rda.html_problems(h, plain)
    assert any(expect in p for p in problems), problems
    export = _write(tmp_path, plain)
    hp = _write(tmp_path, h, "export.html")
    assert _run(fresh, export, approvals_file, log, *(_write_args() + ("--html", hp))) == 1
    assert not approvals_file.exists() and "HTML export" in log.rows[-1][2]["reason"]


def _build_html(doc):
    return io.open(doc["html_path"], encoding="utf-8").read()


def test_the_builds_own_html_and_a_plain_export_pass_the_html_check(doc, plain):
    assert rda.html_problems(_build_html(doc), plain, _build_html(doc)) == []
    assert rda.html_problems(html_of(GOOGLEIFY(plain)), plain, _build_html(doc)) == []


def _coloured(plain, paint):
    """html_of(plain) with some lines painted: paint maps a line index to
    [(part of the line, css colour)]; the part is wrapped in a span of that
    colour (through a class, as Google's export often does)."""
    lines = plain.split("\n")
    css, out = [], []
    for i, l in enumerate(lines):
        if not l.strip():
            out.append("<p><br></p>")
            continue
        text = html.escape(l, quote=False)
        for n, (part, colour) in enumerate(paint.get(i, [])):
            cls = "k%d_%d" % (i, n)
            css.append(".%s{color:%s}" % (cls, colour))
            esc = html.escape(part, quote=False)
            assert esc in text, (part, l)
            text = text.replace(esc, '<span class="%s">%s</span>' % (cls, esc), 1)
        out.append("<p>%s</p>" % text)
    return ('<html><head><meta charset="utf-8"><style>%s</style></head><body>%s</body></html>'
            % ("".join(css), "\n".join(out)))


@pytest.mark.parametrize("grey", ["#999999", "#666666", "#999"])
def test_a_body_line_greyed_is_refused_and_the_builds_greys_pass(doc, plain, grey):
    """Both greys are stock colours in Google's text-colour menu: grey is
    allowed only on the characters the build made grey (tag markers, notes,
    labels, section markers), never on an email's words."""
    lines = plain.split("\n")
    h = _tag_index(lines, CAD_A)
    body = _line_in_block(lines, CAD_A, "Hey {first_name},")
    note = next(k for k, l in enumerate(lines) if l.endswith("(note)") and k > h)
    label = next(k for k, l in enumerate(lines) if TAG_LINE_RE.findall(l)[-1:] and "/" in TAG_LINE_RE.findall(l)[-1]
                 and not TAG_LINE_RE.findall(l)[-1].endswith("/subject"))
    section = next(k for k, l in enumerate(lines) if l.endswith("(section)"))
    tag = "(tag: %s)" % CAD_A
    ok = {h: [(tag, grey)], note: [(lines[note][:-len("(note)")].strip(), "#666666"), ("(note)", grey)],
          label: [(lines[label].split(" (tag:")[0], "#666666"), (lines[label][lines[label].index("(tag:"):], grey)],
          section: [("(section)", grey)]}
    assert rda.html_problems(_coloured(plain, ok), plain, _build_html(doc)) == []
    bad = dict(ok)
    bad[body] = [("Hey {first_name},", grey)]
    problems = rda.html_problems(_coloured(plain, bad), plain, _build_html(doc))
    assert problems == ["grey text where the build has none: 'Hey {first_name},'"], problems
    # a heading's own words greyed are not the build's grey either
    heading = {h: [(lines[h].split(" (tag:")[0], grey), (tag, grey)]}
    assert rda.html_problems(_coloured(plain, heading), plain, _build_html(doc))
    # without the build's HTML to compare with, any grey refuses
    assert rda.html_problems(_coloured(plain, ok), plain)


REAL_HTML = os.path.join(TOOL_DIR, "tests", "fixtures", "drive_export_2026-09-23T1815Z.html")


def test_a_real_drive_html_export_passes_and_a_greyed_line_in_it_does_not(fresh, tmp_path, approvals_file, log,
                                                                          capsys):
    """Drive's own text/html export of the doc in Drive (legacy build) at the
    revision of exports/2026-09-23T1815Z.txt: inline styles, #000000, #666666,
    #999999 and a #ffffff background. Lorenzo's typed note took the grey of
    the "(note)" marker; that line is an edit, refused by the text checks."""
    real = io.open(REAL_HTML, encoding="utf-8-sig").read()
    text = io.open(FIRST_EDITS, encoding="utf-8-sig").read()
    legacy = io.open(rda.LEGACY_HTML, encoding="utf-8").read()
    assert rda.html_problems(real, text, legacy) == []
    line = "A couple more options if those did not work: {slots}."
    k = real.index(html.escape(line, quote=False))
    start = real.rindex("<span", 0, k)
    span = real[start:k]
    assert "color:#000000" in span
    for grey in ("#999999", "#666666"):
        greyed = real[:start] + span.replace("color:#000000", "color:" + grey) + real[k:]
        assert rda.html_problems(greyed, text, legacy) == ["grey text where the build has none: %r" % line[:50]]
    rc = rda.main([FIRST_EDITS, "--approvals-file", str(approvals_file), "--html", REAL_HTML], log_fn=log,
                  build=lambda out_dir: fresh)
    out = capsys.readouterr().out
    assert rc == 1
    whole = out.split("--write refuses the whole doc:")[1].split("Dry run")[0]
    assert [l.strip() for l in whole.strip().split("\n")] == ["- " + rda.W_LEGACY]


def test_the_html_export_must_be_the_same_doc(doc, plain):
    other = replace_line(plain, CAD_A, "Hey {first_name},", "Hi {first_name},")
    assert any("not the same doc" in p for p in rda.html_problems(html_of(other), plain))


def test_blank_lines_the_html_export_drops_are_not_a_different_doc(doc, plain):
    # A real Drive export (2026-09-23): the HTML leaves out empty paragraphs
    # inside some blocks that the text export keeps as blank lines.
    squeezed = "\n".join(ln for ln in plain.split("\n") if ln.strip())
    assert rda.html_problems(html_of(squeezed), plain) == []


def test_write_needs_the_html_export(doc, fresh, plain, tmp_path, approvals_file, log, capsys):
    args = ["--write", "--doc-id", DOC_ID, "--done-quote", QUOTE, "--checked-comments"]
    assert rda.main([_write(tmp_path, plain), "--approvals-file", str(approvals_file)] + args, log_fn=log,
                    build=lambda out_dir: fresh) == 1
    assert "--html" in capsys.readouterr().out and not approvals_file.exists() and log.rows == []


def test_one_build_mapped_to_two_docs_is_refused(doc, fresh, plain, tmp_path, approvals_file, log):
    json.dump({"uploads": [{"doc_id": DOC_ID, "fingerprint": doc["fingerprint"]},
                           {"doc_id": "another-doc", "fingerprint": doc["fingerprint"]}]}, open(rda.UPLOADS_PATH, "w"))
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, *_write_args()) == 1
    assert "more than one doc" in log.rows[-1][2]["reason"] and not approvals_file.exists()


def test_what_the_doc_reads_back_as_must_hash_to_the_template(doc, fresh, plain, builds_dir):
    """Re-hash at run time: every approvable id's text, read back out of the
    fresh build and out of the doc's build, hashes to its template hash; an
    id that does not is refused."""
    assert fresh["readback_mismatch"] == {} and _doc_build(doc)["readback_mismatch"] == {}
    broken = dict(fresh, readback_mismatch={CAD_A: "reads back as 000000000000, not 111111111111"})
    refused = _refused(_plan(plain, doc, broken))
    assert refused[CAD_A] == [rda.R_READBACK % ("fresh build", "reads back as 000000000000, not 111111111111")]
    # a build folder whose HTML is not its manifest's doc is refused
    fake = copy.deepcopy(doc["manifest"])
    tid = next(b["template_id"] for b in fake["blocks"] if b.get("kind") == "template_main")
    reader = doc_areas.DocReader(plain)
    assert fresh_manifest.readback_mismatches(plain, doc["manifest"]) == {}
    main = next(b for b in fake["blocks"] if b.get("template_id") == tid and b["kind"] == "template_main")
    main["variants"] = list(main["variants"])[:-1] if main["variants"] else ["missing_lead_data"]
    assert tid in fresh_manifest.readback_mismatches(plain, fake)
    assert reader.main(tid)


def test_a_variant_header_without_a_title_and_a_fence_line(tmp_path):
    import export_parse
    md = ("## Counts\n\n- approvable: 1\n\n## Section\n\n### `x.y`\n\n<!-- approve-template id=x.y sha256=ab -->\n\n"
          "```text\nHello\n\n=== variant: plain ===\nHi\n```\n\n## Not in the catalogue\n")
    p = tmp_path / "e.md"
    p.write_text(md, encoding="utf-8")
    (e,) = export_parse.parse_export(str(p))["entries"]
    assert e["main"] == ["Hello"] and e["variants"] == [{"name": "plain", "desc": "", "lines": ["Hi"]}]
    p.write_text(md.replace("Hello\n", "Hello\n```\nmore template text\n"), encoding="utf-8")
    with pytest.raises(export_parse.ExportError):
        export_parse.parse_export(str(p))


def test_the_pin_note_says_which_version_writes_the_line_out(doc, plain):
    reader = doc_areas.DocReader(plain)
    pinned = [b for b in doc["manifest"]["blocks"] if b.get("pinned_line")]
    assert pinned
    for b in pinned:
        (note,) = [n for n in reader.notes(b["tag"]) if doc_rules.PIN_RE.match(n)]
        scope = doc_rules.PIN_RE.match(note).group(1)
        shown = [t for t in reader.items if t.startswith(b["tag"] + "/")]
        assert (doc_rules.PIN_SCOPE_SHOWN in scope) == bool(shown), (b["tag"], note)
        assert doc_rules.PIN_SCOPE_MISSING in scope or shown
