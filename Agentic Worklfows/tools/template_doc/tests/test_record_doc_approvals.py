"""record_doc_approvals.py: approvals from the one Google Doc after "done".

Every test writes a tmp approvals file only; the real
config/approved_templates.json is checked unchanged after each test and no
Job_Log row reaches .tmp/. No network, no model calls.
"""
import ast
import copy
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import fresh_manifest
import record_doc_approvals as rda

from services.reply_engine import template_approvals as ta
from shared.paths import BASE_DIR

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_FILE = BASE_DIR / "config" / "approved_templates.json"
COMMITTED_MANIFEST = os.path.join(TOOL_DIR, "manifest.json")
COMMITTED_HTML = os.path.join(TOOL_DIR, "advero_all_emails.html")
FIRST_EDITS = os.path.join(TOOL_DIR, "exports", "2026-09-23T1815Z.txt")
QUOTE = "done"


# ------------------------------------------------ selftest's Drive rendering
def _selftest_renderer():
    """html_to_text and googleify exactly as selftest.py defines them (selftest
    runs its checks at import, so only those definitions are taken)."""
    src = io.open(os.path.join(TOOL_DIR, "selftest.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module not in ("html.parser",):
                continue
            keep.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "GoogleText":
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in ("html_to_text", "googleify"):
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(getattr(t, "id", None) in ("BLOCK", "SKIP") for t in node.targets):
            keep.append(node)
    mod = ast.Module(body=keep, type_ignores=[])
    ns = {}
    exec(compile(mod, "selftest_renderer", "exec"), ns)
    return ns["html_to_text"], ns["googleify"]


HTML_TO_TEXT, GOOGLEIFY = _selftest_renderer()


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def fresh(tmp_path_factory):
    return fresh_manifest.build_fresh(str(tmp_path_factory.mktemp("fresh") / "build"))


@pytest.fixture(scope="module")
def plain(fresh):
    """The fresh doc as Drive's text export gives it."""
    return HTML_TO_TEXT(fresh["html_path"])


@pytest.fixture(autouse=True)
def approvals_file(tmp_path, monkeypatch):
    before = REAL_FILE.read_bytes() if REAL_FILE.exists() else None
    path = tmp_path / "approved_templates.json"
    monkeypatch.setattr(ta, "APPROVALS_PATH", path)
    monkeypatch.delenv(ta.KILL_SWITCH_ENV, raising=False)
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.delenv("JOB_LOG_SHEET_ID", raising=False)
    yield path
    after = REAL_FILE.read_bytes() if REAL_FILE.exists() else None
    assert before == after, "a test wrote the real config/approved_templates.json"


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
    argv = [export, "--approvals-file", str(approvals), "--doc-manifest", fresh["manifest_path"]] + list(extra)
    return rda.main(argv, log_fn=log, build=lambda out_dir: fresh)


def _approvable(fresh):
    return sorted(fresh["hashes"])


# ------------------------------------------------------- editing the text
TAG_LINE_RE = re.compile(r"\(\s*tag\s*:\s*([^()\s]+)\s*\)")


def _tag_index(lines, tag):
    hits = [i for i, l in enumerate(lines) if [m.group(1) for m in TAG_LINE_RE.finditer(l)][-1:] == [tag]]
    assert len(hits) == 1, (tag, hits)
    return hits[0]


def _block_end(lines, start):
    k = start + 1
    while k < len(lines):
        l = lines[k]
        m = TAG_LINE_RE.findall(l)
        if m and not m[-1].endswith("/subject"):
            return k
        if l.rstrip().endswith("(section)"):
            return k
        k += 1
    return k


def _first_content_line(lines, tag):
    i = _tag_index(lines, tag)
    for k in range(i + 1, _block_end(lines, i)):
        l = lines[k]
        if l.strip() and not TAG_LINE_RE.search(l) and not l.rstrip().endswith("(note)"):
            return k
    raise AssertionError("no text line in block %s" % tag)


def edit_line(text, tag, new_line):
    lines = text.split("\n")
    lines[_first_content_line(lines, tag)] = new_line
    return "\n".join(lines)


def edit_subject(text, tag, new_subject):
    lines = text.split("\n")
    i = _tag_index(lines, tag)
    lines[i] = "Subject: %s (tag: %s)" % (new_subject, tag)
    return "\n".join(lines)


def delete_block(text, tag):
    lines = text.split("\n")
    i = _tag_index(lines, tag)
    del lines[i:_block_end(lines, i)]
    return "\n".join(lines)


def _tags(fresh, kind, template_id=None):
    return [b["tag"] for b in fresh["manifest"]["blocks"]
            if b["kind"] == kind and (template_id is None or b["template_id"] == template_id)]


def _refused(plan):
    return dict((r["id"], r["reasons"]) for r in plan["refused"])


# ---------------------------------------------------------- the happy path
def test_the_fresh_doc_approves_all_108_at_the_catalogue_hashes(fresh, plain, tmp_path, approvals_file, log, capsys):
    export = _write(tmp_path, GOOGLEIFY(plain))
    rc = _run(fresh, export, approvals_file, log, "--write", "--done-quote", QUOTE)
    out = capsys.readouterr().out
    assert rc == 0, out
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    index = ta.catalogue_index()
    approvable = [tid for tid, e in index.items() if e.get("approvable")]
    assert len(approvable) == 108
    assert sorted(data["approvals"]) == sorted(approvable)
    assert set(data) == {"version", "approvals"}  # no auto_send key invented
    for tid in approvable:
        rec = data["approvals"][tid]
        assert rec["sha256"] == index[tid]["sha256"] == fresh["hashes"][tid]
        assert rec["approved_by"] == 'Lorenzo (Google Doc "done")'
        assert set(rec) == {"sha256", "approved_at", "approved_by", "text_preview"}
        assert ta.status(tid, path=approvals_file) == ta.STATUS_APPROVED
        assert ta.is_approved(tid, path=approvals_file)
    # one Job_Log row, ids and hashes only
    assert len(log.rows) == 1
    job, status, details = log.rows[0]
    assert (job, status) == ("approve_templates", "ok")
    assert details["action"] == "approve_from_doc"
    assert details["doc_id"] == "1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U"
    assert details["done_quote"] == QUOTE
    assert details["export_sha256"] == hashlib.sha256(open(export, "rb").read()).hexdigest()
    assert details["fresh_export_sha256"] == fresh["export_sha256"]
    assert details["approved"] == dict((tid, index[tid]["sha256"]) for tid in approvable)
    assert details["refused"] == {}
    assert out.rstrip().splitlines()[-1].strip() in ("git diff -- config/approved_templates.json",
                                                     "(this run wrote %s)" % approvals_file)
    assert "git diff -- config/approved_templates.json" in out
    # the Google noise really was there, and counted as cosmetic
    assert "cosmetic only" in out


def test_a_second_run_changes_nothing(fresh, plain, tmp_path, approvals_file, log, capsys):
    export = _write(tmp_path, plain)
    assert _run(fresh, export, approvals_file, log, "--write", "--done-quote", QUOTE) == 0
    first = approvals_file.read_bytes()
    assert _run(fresh, export, approvals_file, log, "--write", "--done-quote", QUOTE) == 0
    assert approvals_file.read_bytes() == first
    assert log.rows[-1][2]["approved"] == {} and len(log.rows[-1][2]["unchanged"]) == 108
    assert "Nothing to change" in capsys.readouterr().out


# ------------------------------------------------------------- the edits
def test_edited_main_variant_subject_and_deleted_variant_refuse_exactly_those(fresh, plain):
    main_id = "cadence.d3"
    var_tag = "first_reply.cleaning_reactivation.pricing.full/no_slots"
    subj_tag = "no_show.ns_d14_breakup_email/subject"
    del_tag = next(t for t in _tags(fresh, "template_variant") if t.startswith("booking.counter.weekend/"))
    text = edit_line(plain, main_id, "A couple more times that might suit: {slots}.")
    text = edit_line(text, var_tag, "Any chance you have 15 minutes soon? {booking_url}")
    text = edit_subject(text, subj_tag, "Closing the loop")
    text = delete_block(text, del_tag)
    plan = rda.evaluate(text, fresh, fresh["manifest"], ta.empty_approvals())
    refused = _refused(plan)
    var_id, subj_id, del_id = var_tag.split("/")[0], subj_tag.split("/")[0], del_tag.split("/")[0]
    assert sorted(refused) == sorted([main_id, var_id, subj_id, del_id])
    assert refused[main_id] == [rda.R_EDITED % main_id]
    assert refused[var_id] == [rda.R_EDITED % var_tag]
    assert refused[subj_id] == [rda.R_EDITED % subj_tag]
    assert refused[del_id] == [rda.R_DELETED % del_tag]
    approved = [p["id"] for p in plan["approve"]]
    assert sorted(approved) == sorted(set(_approvable(fresh)) - set(refused))
    assert len(approved) == 104
    for p in plan["approve"]:
        assert p["sha256"] == fresh["hashes"][p["id"]]


def test_edits_through_the_cli_write_only_the_unedited_ids(fresh, plain, tmp_path, approvals_file, log):
    text = edit_line(plain, "cadence.d3", "A couple more times that might suit: {slots}.")
    rc = _run(fresh, _write(tmp_path, text), approvals_file, log, "--write", "--done-quote", QUOTE)
    assert rc == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert "cadence.d3" not in data["approvals"]
    assert len(data["approvals"]) == 107
    assert log.rows[-1][2]["refused"] == {"cadence.d3": [rda.R_EDITED % "cadence.d3"]}


def test_a_new_block_tagged_for_an_email_refuses_that_email(fresh, plain):
    lines = plain.split("\n")
    end = _block_end(lines, _tag_index(lines, "cadence.d7"))  # after d7's own blocks
    while any(TAG_LINE_RE.search(l) and "cadence.d7/" in l for l in lines[end:end + 1]):
        end = _block_end(lines, end)
    lines[end:end] = ["If they are busy: (tag: cadence.d7/busy)", "No rush at all."]
    plan = rda.evaluate("\n".join(lines), fresh, fresh["manifest"], ta.empty_approvals())
    assert _refused(plan) == {"cadence.d7": [rda.R_ADDED % "cadence.d7/busy"]}
    assert plan["unknown_tags"] == ["cadence.d7/busy"]


def test_lorenzos_first_export_refuses_cadence_d1_and_d2(fresh, approvals_file, log, capsys):
    """The 18:15Z export: cadence.d1 and cadence.d2 edited, both no_slots
    variants deleted. The fresh build is the reference: any id whose code
    changed since the committed doc was built is refused too, and nothing
    else is."""
    with io.open(FIRST_EDITS, encoding="utf-8") as fh:
        text = fh.read()
    with io.open(COMMITTED_MANIFEST, encoding="utf-8") as fh:
        committed = json.load(fh)
    plan = rda.evaluate(text, fresh, committed, ta.empty_approvals())
    refused = _refused(plan)
    assert rda.R_EDITED % "cadence.d1" in refused["cadence.d1"]
    assert rda.R_DELETED % "cadence.d1/no_slots" in refused["cadence.d1"]
    assert rda.R_EDITED % "cadence.d2" in refused["cadence.d2"]
    assert rda.R_DELETED % "cadence.d2/no_slots" in refused["cadence.d2"]
    # ids whose code moved away from the committed doc since it was built
    committed_blocks = dict((b["tag"], b) for b in committed["blocks"])
    moved = set()
    for b in fresh["manifest"]["blocks"]:
        tid = b.get("template_id")
        if not tid:
            continue
        old = committed_blocks.get(b["tag"])
        if old is None or old.get("sha256") != b["sha256"] or old["text"] != b["text"]:
            moved.add(tid)
    for tid in moved:
        assert tid in refused, tid
    assert set(refused) == {"cadence.d1", "cadence.d2"} | moved
    assert sorted(p["id"] for p in plan["approve"]) == sorted(set(_approvable(fresh)) - set(refused))
    assert plan["instantly"]["changed"] == [] and plan["instantly"]["deleted"] == []
    assert plan["instantly"]["unchanged"] == 24

    # the same through the CLI with a real fresh build, as a dry run
    rc = rda.main([FIRST_EDITS, "--approvals-file", str(approvals_file)], log_fn=log)
    out = capsys.readouterr().out
    assert rc == 0, out
    assert not approvals_file.exists()
    assert log.rows == []
    assert "refused, not approved (%d):" % len(refused) in out
    assert "Dry run: nothing was written" in out


# ------------------------------------------------------ refusals and safety
def test_write_without_a_done_quote_writes_nothing(fresh, plain, tmp_path, approvals_file, log, capsys):
    export = _write(tmp_path, plain)
    assert _run(fresh, export, approvals_file, log, "--write") == 1
    assert _run(fresh, export, approvals_file, log, "--write", "--done-quote", "   ") == 1
    assert not approvals_file.exists()
    assert log.rows == []
    assert "needs --done-quote" in capsys.readouterr().out


def test_dry_run_writes_nothing(fresh, plain, tmp_path, approvals_file, log, capsys):
    export = _write(tmp_path, plain)
    assert _run(fresh, export, approvals_file, log) == 0
    assert not approvals_file.exists()
    approvals_file.write_text('{"version": 1, "approvals": {}}\n', encoding="utf-8")
    before = approvals_file.read_bytes()
    assert _run(fresh, export, approvals_file, log, "--done-quote", QUOTE) == 0
    assert approvals_file.read_bytes() == before
    assert log.rows == []
    out = capsys.readouterr().out
    assert "will approve (108):" in out and "Dry run: nothing was written" in out


def test_duplicate_tags_refuse_the_whole_doc(fresh, plain, tmp_path, approvals_file, log, capsys):
    lines = plain.split("\n")
    k = _tag_index(lines, "cadence.d7")
    lines[k:k] = ["Day 1 follow-up (tag: cadence.d1)", "stray"]
    export = _write(tmp_path, "\n".join(lines))
    assert _run(fresh, export, approvals_file, log, "--write", "--done-quote", QUOTE) == 1
    assert not approvals_file.exists()
    assert [r[1] for r in log.rows] == ["refused"]
    assert "duplicate tags" in log.rows[0][2]["reason"]
    assert _run(fresh, export, approvals_file, log) == 1  # the dry run refuses too
    assert "REFUSED" in capsys.readouterr().out


def test_copies_of_one_sentence_changed_differently_refuse_the_whole_doc(fresh, plain, tmp_path, approvals_file,
                                                                         log):
    groups = {}
    for b in fresh["manifest"]["blocks"]:
        if b["kind"] == "template_variant" and b["text"].strip():
            groups.setdefault(b["text_group"], []).append(b["tag"])
    tags = next(ts for ts in groups.values() if len(ts) >= 2)
    text = edit_line(plain, tags[0], "One version of the new line {booking_url}")
    text = edit_line(text, tags[1], "Another version of the new line {booking_url}")
    with pytest.raises(rda.Refused):
        rda.evaluate(text, fresh, fresh["manifest"], ta.empty_approvals())
    assert _run(fresh, _write(tmp_path, text), approvals_file, log, "--write", "--done-quote", QUOTE) == 1
    assert not approvals_file.exists()
    assert "changed differently" in log.rows[-1][2]["reason"]


def test_a_failed_fresh_build_refuses_everything(plain, tmp_path, approvals_file, log):
    def broken(out_dir):
        raise fresh_manifest.FreshBuildError("build.py failed")
    rc = rda.main([_write(tmp_path, plain), "--approvals-file", str(approvals_file), "--write",
                   "--done-quote", QUOTE], log_fn=log, build=broken)
    assert rc == 1
    assert not approvals_file.exists()
    assert log.rows[-1][1] == "refused"


def test_a_doc_with_no_tags_is_refused(fresh, tmp_path, approvals_file, log):
    assert _run(fresh, _write(tmp_path, "just some text\n"), approvals_file, log, "--write",
                "--done-quote", QUOTE) == 1
    assert not approvals_file.exists()


def test_existing_approvals_and_auto_send_are_kept(fresh, plain, tmp_path, approvals_file, log):
    index = ta.catalogue_index()
    kept_current = {"sha256": index["cadence.d7"]["sha256"], "approved_at": "2026-09-01T00:00:00+00:00",
                    "approved_by": "Lorenzo", "text_preview": "kept as is"}
    refused_old = {"sha256": "0" * 64, "approved_at": "2026-09-01T00:00:00+00:00",
                   "approved_by": "Lorenzo", "text_preview": "old text"}
    other = {"sha256": "1" * 64, "approved_at": "2026-09-01T00:00:00+00:00",
             "approved_by": "Lorenzo", "text_preview": "not in the catalogue"}
    stale = {"sha256": "2" * 64, "approved_at": "2026-09-01T00:00:00+00:00",
             "approved_by": "Lorenzo", "text_preview": "will be refreshed"}
    start = {"version": 1, "auto_send": False, "note": "left alone",
             "approvals": {"cadence.d7": kept_current, "cadence.d3": refused_old, "retired.template": other,
                           "cadence.d14": stale}}
    approvals_file.write_text(json.dumps(start), encoding="utf-8")
    text = edit_line(plain, "cadence.d3", "A couple more times that might suit: {slots}.")
    assert _run(fresh, _write(tmp_path, text), approvals_file, log, "--write", "--done-quote", QUOTE) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert data["auto_send"] is False and data["note"] == "left alone" and data["version"] == 1
    assert data["approvals"]["cadence.d7"] == kept_current       # already approved: untouched
    assert data["approvals"]["cadence.d3"] == refused_old        # refused: never revoked
    assert data["approvals"]["retired.template"] == other        # not ours: untouched
    assert data["approvals"]["cadence.d14"]["sha256"] == index["cadence.d14"]["sha256"]  # refreshed
    assert data["approvals"]["cadence.d14"]["approved_by"] == 'Lorenzo (Google Doc "done")'
    assert ta.kill_switch_on(approvals_file)
    details = log.rows[-1][2]
    assert "cadence.d7" in details["unchanged"] and "cadence.d7" not in details["approved"]
    assert "cadence.d14" in details["approved"] and "cadence.d3" not in details["approved"]


def test_a_code_change_since_the_doc_was_built_is_refused(fresh, plain):
    doc = copy.deepcopy(fresh["manifest"])
    for b in doc["blocks"]:
        if b.get("template_id") == "show_rate.confirm_sms":
            b["sha256"] = "3" * 64
    plan = rda.evaluate(plain, fresh, doc, ta.empty_approvals())
    refused = _refused(plan)
    assert list(refused) == ["show_rate.confirm_sms"]
    assert refused["show_rate.confirm_sms"][0].startswith("the code changed since the doc was built")


def test_a_doc_built_from_older_code_names_the_code_not_lorenzo(fresh, plain):
    """The doc shows words the code no longer sends, and lacks a block the code
    now has: refused, and the reason says the code moved."""
    tid = "first_reply.cleaning_reactivation.pricing.full"
    var_tag = tid + "/no_slots"
    text = delete_block(edit_line(plain, tid, "Older words the code used to send."), var_tag)
    old_doc = copy.deepcopy(fresh["manifest"])
    old_doc["blocks"] = [b for b in old_doc["blocks"] if b["tag"] != var_tag]
    for b in old_doc["blocks"]:
        if b.get("template_id") == tid:
            b["sha256"] = "6" * 64
            if b["tag"] == tid:
                b["text"] = rda.parse_with_info(text)["blocks"][tid]
    refused = _refused(rda.evaluate(text, fresh, old_doc, ta.empty_approvals()))
    assert list(refused) == [tid]
    assert refused[tid][:2] == [rda.R_CODE_MOVED % tid, rda.R_CODE_NEW % var_tag]
    assert refused[tid][2].startswith("the code changed since the doc was built")


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


def test_hash_race_before_the_plan_is_refused(fresh, plain, tmp_path, approvals_file, log, monkeypatch):
    monkeypatch.setattr(ta, "catalogue_index", _patched_index("cadence.d5"))
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, "--write", "--done-quote", QUOTE) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert "cadence.d5" not in data["approvals"] and len(data["approvals"]) == 107
    assert log.rows[-1][2]["refused"]["cadence.d5"][0].startswith("the code changed after the fresh build")


def test_hash_race_between_the_plan_and_the_write_is_not_written(fresh, plain, tmp_path, approvals_file, log,
                                                                  monkeypatch, capsys):
    # the first catalogue read (the plan) is the real one; the one just before
    # writing sees cadence.d5 changed
    monkeypatch.setattr(ta, "catalogue_index", _patched_index("cadence.d5", calls_before_change=1))
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, "--write", "--done-quote", QUOTE) == 0
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    assert "cadence.d5" not in data["approvals"] and len(data["approvals"]) == 107
    details = log.rows[-1][2]
    assert "cadence.d5" not in details["approved"]
    assert details["refused"]["cadence.d5"][0].startswith("the code changed after the fresh build")
    assert "refused at write time: cadence.d5" in capsys.readouterr().out


def test_the_registry_refusing_the_plan_writes_nothing(fresh, plain, tmp_path, approvals_file, log, monkeypatch):
    def boom(*a, **k):
        raise ta.ApprovalError("these templates changed since the review file was exported")
    monkeypatch.setattr(ta, "plan_approve", boom)
    assert _run(fresh, _write(tmp_path, plain), approvals_file, log, "--write", "--done-quote", QUOTE) == 1
    assert not approvals_file.exists()
    assert log.rows[-1][1] == "refused"


# ------------------------------------------------------------ build.py
def test_build_defaults_are_byte_identical_to_the_committed_doc(tmp_path):
    """A default build (no arguments) in a copy of the folder writes the
    committed HTML byte for byte, and the committed manifest except
    repo_head (git HEAD at build time; the copy is not a git checkout)."""
    code_root = os.path.dirname(os.path.dirname(TOOL_DIR))
    tool = tmp_path / "tools" / "template_doc"
    tool.mkdir(parents=True)
    for name in ("build.py", "export_parse.py", "templates_export_final.md"):
        shutil.copy(os.path.join(TOOL_DIR, name), str(tool / name))
    snap_rel = "config/snapshots/instantly_campaigns_2026-09-21.json"
    (tmp_path / "config" / "snapshots").mkdir(parents=True)
    shutil.copy(os.path.join(code_root, snap_rel), str(tmp_path / snap_rel))
    proc = subprocess.run([sys.executable, "build.py"], cwd=str(tool), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True)
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert (tool / "advero_all_emails.html").read_bytes() == open(COMMITTED_HTML, "rb").read()
    head = re.compile(rb'\n "repo_head": [^\n]*,\n')
    built = head.sub(b"\n", (tool / "manifest.json").read_bytes())
    committed = head.sub(b"\n", open(COMMITTED_MANIFEST, "rb").read())
    assert built == committed


def test_build_writes_to_the_out_dir_only(fresh):
    assert os.path.dirname(fresh["manifest_path"]) != TOOL_DIR
    assert fresh["manifest"]["export"] == fresh_manifest.EXPORT_NAME
    assert len(fresh["hashes"]) == 108
