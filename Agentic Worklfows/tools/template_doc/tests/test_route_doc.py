"""route_doc sends every block Lorenzo changed in the one doc to the section
that owns it and the file that holds its text, and flags what needs a look
before anything is applied."""
import base64
import hashlib
import io
import json
import os
import re

import route_doc

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(TOOL_DIR, "manifest.json")
UPLOAD_EXPORT = os.path.join(TOOL_DIR, "drive_export.txt")
FIRST_EDITS = os.path.join(TOOL_DIR, "exports", "2026-09-23T1815Z.txt")


def _read(path):
    with io.open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _report(text):
    return route_doc.build_report(text, route_doc.diff_doc.load_manifest(MANIFEST), "x.txt")


def _entries(report):
    out = {}
    for entries in report["sections"].values():
        for e in entries:
            out[e["tag"]] = e
    return out


def _edit_first_body_line(lines, tag, fn):
    """Apply fn to the first copy line after the line tagged `tag`."""
    start = next(i for i, l in enumerate(lines) if "(tag: %s)" % tag in l)
    for i in range(start + 1, len(lines)):
        l = lines[i]
        if not l.strip() or re.search(r"\(note\)\s*$", l) or re.search(r"/subject\)\s*$", l):
            continue
        assert "(tag:" not in l, "no copy line under %s" % tag
        lines[i] = fn(l)
        return
    raise AssertionError(tag)


def test_first_real_edits_route_to_section_1():
    r = _report(_read(FIRST_EDITS))
    assert [e["tag"] for e in r["sections"]["1"]] == [
        "cadence.d1", "cadence.d2", "cadence.d1/no_slots", "cadence.d2/no_slots"]
    for k in ("2", "3", "4"):
        assert r["sections"][k] == []
    e = _entries(r)
    assert e["cadence.d1"]["file"] == "services/reply_engine/prompts/cadence_d1.md"
    assert e["cadence.d2"]["file"] == "services/reply_engine/prompts/cadence_d2.md"
    assert e["cadence.d1/no_slots"]["what"] == "deleted"
    # The no_slots text is NO_SLOTS_BODIES in cadence.py, whatever the
    # manifest source says.
    for tag, day in (("cadence.d1/no_slots", "d1"), ("cadence.d2/no_slots", "d2")):
        assert e[tag]["file"] == "services/reply_engine/cadence.py"
        assert 'NO_SLOTS_BODIES["%s"]' % day in e[tag]["route_note"]
    d2 = e["cadence.d2"]
    assert d2["what"] == "changed"
    assert d2["invalid_placeholders"] == ["{company name}"]
    assert "{booking_url}" in d2["placeholders_removed"]
    assert any("NOTE FOR CLAUDE" in n for n in d2["notes_for_claude"])
    assert "NOTE FOR CLAUDE" not in d2["new_text_without_notes"]
    assert "(note)" not in d2["new_text_without_notes"]
    assert d2["new_text_without_notes"].startswith("Hey {first_name},")
    assert e["cadence.d1"]["notes_for_claude"] == []
    assert e["cadence.d1"]["invalid_placeholders"] == []
    assert r["counts"]["routed"] == 4
    assert len(r["export_sha256"]) == 64


def test_synthetic_edits_land_in_the_right_section_and_file(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n")
    _edit_first_body_line(lines, "instantly.cleaning_reactivation.step1",
                          lambda l: l + " Hi {first_name}.")
    idx = next(i for i, l in enumerate(lines)
               if "(tag: instantly.cleaning_reactivation.step1/subject)" in l)
    lines[idx] = lines[idx].replace("question", "quick question")
    _edit_first_body_line(lines, "show_rate.confirm_email.cleaning_reactivation",
                          lambda l: l + " See you {{firstName}}.")
    _edit_first_body_line(lines, "booking.already_booked.awaiting_approval",
                          lambda l: l + " Talk soon { first_name}.")
    idx = next(i for i, l in enumerate(lines) if "(tag: U-PRICE-1)" in l)
    lines.insert(idx + 1, "Setup: $500 flat")
    lines += ["Brand new email (tag: something.new)", "Hello there {first_name}", ""]
    path = tmp_path / "edited.txt"
    path.write_text(u"\n".join(lines), encoding="utf-8")

    r = _report(_read(str(path)))
    e = _entries(r)
    assert set(e) == {
        "instantly.cleaning_reactivation.step1", "instantly.cleaning_reactivation.step1/subject",
        "show_rate.confirm_email.cleaning_reactivation",
        "booking.already_booked.awaiting_approval", "U-PRICE-1", "something.new"}

    body = e["instantly.cleaning_reactivation.step1"]
    assert (body["section"], body["file"], body["what"]) == (4, "changesets/instantly_copy/", "changed")
    assert body["wrong_placeholder_style"] == ["{first_name}"]
    subj = e["instantly.cleaning_reactivation.step1/subject"]
    assert (subj["section"], subj["file"]) == (4, "changesets/instantly_copy/")
    assert subj["wrong_placeholder_style"] == []

    sr = e["show_rate.confirm_email.cleaning_reactivation"]
    assert (sr["section"], sr["file"]) == (2, "services/reply_engine/show_rate.py")
    assert sr["wrong_placeholder_style"] == ["{{firstName}}"]

    ab = e["booking.already_booked.awaiting_approval"]
    assert (ab["section"], ab["file"]) == (2, "services/reply_engine/app.py")
    assert "section 4" in ab["route_note"]
    assert ab["invalid_placeholders"] == ["{ first_name}"]

    up = e["U-PRICE-1"]
    assert (up["section"], up["file"], up["new"]) == (3, "config/upwork_offers.md", "Setup: $500 flat")

    new = e["something.new"]
    assert (new["section"], new["file"], new["what"]) == (4, "review by hand", "new")
    assert new["old"] is None and new["new"] == "Hello there {first_name}"

    assert [x["tag"] for x in r["sections"]["3"]] == ["U-PRICE-1"]
    assert r["counts"]["routed"] == 6


def test_clean_upload_export_routes_nothing():
    r = _report(_read(UPLOAD_EXPORT))
    assert all(v == [] for v in r["sections"].values())
    assert r["counts"]["routed"] == 0
    assert r["duplicates"] == [] and r["conflicting_text_groups"] == []
    assert "Nothing to route" in route_doc.render_text(r)


def test_cli_json_round_trips(tmp_path, capsys):
    out_json = tmp_path / "r.json"
    out_md = tmp_path / "r.md"
    rc = route_doc.main([FIRST_EDITS, "--manifest", MANIFEST,
                         "--json", str(out_json), "--md", str(out_md)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "cadence.d2" in printed and "{company name}" in printed
    loaded = json.loads(out_json.read_text(encoding="utf-8"))
    with open(FIRST_EDITS, "rb") as fh:
        raw = fh.read()
    expected = route_doc.build_report(raw.decode("utf-8-sig"),
                                      route_doc.diff_doc.load_manifest(MANIFEST),
                                      os.path.basename(FIRST_EDITS), raw=raw)
    assert loaded["export_sha256"] == hashlib.sha256(raw).hexdigest()
    assert loaded == json.loads(json.dumps(expected))
    assert "cadence.d2" in out_md.read_text(encoding="utf-8")


def test_cli_unreadable_export_exits_2(tmp_path):
    assert route_doc.main([str(tmp_path / "missing.txt")]) == 2
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\xfa not utf-8")
    assert route_doc.main([str(bad)]) == 2


def test_empty_export_exits_2_not_379_deletions(tmp_path, capsys):
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    assert route_doc.main([str(empty), "--manifest", MANIFEST]) == 2
    captured = capsys.readouterr()
    assert "no tagged blocks found; is this the text/plain export?" in captured.err
    assert captured.out == ""


def test_base64_json_read_back_exits_2(tmp_path, capsys):
    with open(UPLOAD_EXPORT, "rb") as fh:
        raw = fh.read()
    wrapped = tmp_path / "download.json"
    wrapped.write_text(json.dumps({"content": base64.b64encode(raw).decode("ascii"),
                                   "mimeType": "text/plain"}), encoding="utf-8")
    assert route_doc.main([str(wrapped), "--manifest", MANIFEST]) == 2
    captured = capsys.readouterr()
    assert "no tagged blocks found; is this the text/plain export?" in captured.err
    assert captured.out == ""


def test_case_study_routes_to_offers_md_and_source_is_shown(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n")
    _edit_first_body_line(lines, "cadence.d4.case_study.reactivation",
                          lambda l: l.replace("$6M", "$7M"))
    path = tmp_path / "edited.txt"
    path.write_text(u"\n".join(lines), encoding="utf-8")
    r = _report(_read(str(path)))
    e = _entries(r)
    cs = e["cadence.d4.case_study.reactivation"]
    assert (cs["section"], cs["file"], cs["what"]) == (1, "config/offers.md", "changed")
    assert "config/offers.md is section 4's file" in cs["route_note"]
    assert "section 4 applies the edit on section 1's word" in cs["route_note"]
    full = "services/reply_engine/cadence.py:case_study_line (config/offers.md proof table)"
    assert cs["source"] == full
    assert "   source: " + full in route_doc.render_text(r)
    assert "- source: `%s`" % full in route_doc.render_md(r)


def test_every_entry_shows_its_source_in_text_and_md():
    r = _report(_read(FIRST_EDITS))
    text, md = route_doc.render_text(r), route_doc.render_md(r)
    for e in _entries(r).values():
        assert "   source: %s" % e["source"] in text
        assert "- source: `%s`" % e["source"] in md


REPO = os.path.dirname(os.path.dirname(TOOL_DIR))


def test_every_routed_file_exists_and_overrides_hold_the_text():
    manifest = route_doc.diff_doc.load_manifest(MANIFEST)
    for b in manifest["blocks"]:
        _, path, _ = route_doc.route(b["tag"], b)
        if path in (route_doc.REVIEW_BY_HAND, route_doc.INSTANTLY_CHANGESET):
            continue
        assert os.path.isfile(os.path.join(REPO, path)), (b["tag"], path)
        if route_doc._override(b["tag"]) and b["tag"] != "cadence.d6/one_slot":
            held = _read(os.path.join(REPO, path))
            # every placeholder-free piece of each line of the block is in the
            # file (a prompt file's markdown only adds heading marks)
            pieces = [p.strip() for p in re.split(r"\{[^{}]*\}|\n", b["text"])]
            pieces = [p for p in pieces if len(p) >= 10]
            assert pieces, b["tag"]
            for p in pieces:
                assert p in held, (b["tag"], path, p)


def test_stray_braces_in_engine_and_instantly_blocks(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n")
    _edit_first_body_line(lines, "cadence.d1", lambda l: l.replace("{first_name}", "{{first_name}"))
    idx = next(i for i, l in enumerate(lines) if "did not suit: {slots}." in l)
    lines[idx] = lines[idx].replace("{slots}", "{slots}}")
    _edit_first_body_line(lines, "instantly.cleaning_reactivation.step1",
                          lambda l: l.replace("{{personalization}}", "{{personalization}}}"))
    path = tmp_path / "edited.txt"
    path.write_text(u"\n".join(lines), encoding="utf-8")
    r = _report(_read(str(path)))
    e = _entries(r)
    d1 = e["cadence.d1"]
    assert d1["stray_braces"] == ["{{first_name},", "{slots}}."]
    assert d1["invalid_placeholders"] == [] and d1["wrong_placeholder_style"] == []
    body = e["instantly.cleaning_reactivation.step1"]
    assert body["stray_braces"] == ["{{personalization}}}"]
    assert body["wrong_placeholder_style"] == []
    text, md = route_doc.render_text(r), route_doc.render_md(r)
    assert "stray_braces: {{first_name},, {slots}}." in text
    assert "- stray_braces: `{{personalization}}}`" in md


def test_stray_braces_rules():
    assert route_doc.stray_braces("Hey {{first_name},") == ["{{first_name},"]
    assert route_doc.stray_braces("I have {slots}} open") == ["{slots}}"]
    assert route_doc.stray_braces("{{personalization}}}") == ["{{personalization}}}"]
    assert route_doc.stray_braces("{{RANDOM | Hi | Hello}} {{firstName}}, {first_name}") == []
    # engine-style {{x}} in an engine block is a style problem, not a stray brace
    assert route_doc.stray_braces("Hi {{firstName}}") == []
    assert route_doc.wrong_placeholder_style("Hi {{firstName}}", "engine") == ["{{firstName}}"]


def test_clean_manifest_has_no_stray_braces():
    manifest = route_doc.diff_doc.load_manifest(MANIFEST)
    assert len(manifest["blocks"]) == 379
    for b in manifest["blocks"]:
        assert route_doc.stray_braces(b["text"]) == [], b["tag"]


def test_brace_in_a_note_does_not_flag_the_copy(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n")
    idx = next(i for i, l in enumerate(lines) if "did not suit: {slots}." in l)
    lines.insert(idx + 1, "NOTE for Claude: say {x y} here if it reads better {")
    path = tmp_path / "edited.txt"
    path.write_text(u"\n".join(lines), encoding="utf-8")
    e = _entries(_report(_read(str(path))))["cadence.d1"]
    assert any("{x y}" in n for n in e["notes_for_claude"])
    assert e["invalid_placeholders"] == []
    assert e["wrong_placeholder_style"] == []
    assert e["stray_braces"] == []
