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
    # JSON keeps the full also_in list; only text and md cap it at 15.
    d1 = next(e for e in loaded["sections"]["1"] if e["tag"] == "cadence.d1")
    assert sum(len(v) for v in d1["also_in"].values()) == 110
    assert len(d1["also_in"]["1"]) > route_doc.ALSO_IN_SHOW


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


# --- also_in: the other blocks that carry the text Lorenzo edited ---------

TIME_OFFER = "Would {slots} work for a 15-minute call? Or if it's easier, grab a time here: {booking_url}"
EASIER = "Or if it's easier, grab a time here: {booking_url}"


def _all_also_in(e):
    return [t for tags in e["also_in"].values() for t in tags]


def _write(tmp_path, lines):
    path = tmp_path / "edited.txt"
    path.write_text(u"\n".join(lines), encoding="utf-8")
    return _read(str(path))


def test_also_in_for_the_first_real_edits():
    manifest = route_doc.diff_doc.load_manifest(MANIFEST)
    by_tag = dict((b["tag"], b) for b in manifest["blocks"])
    e = _entries(_report(_read(FIRST_EDITS)))
    # cadence.d1 dropped "Or if it's easier, grab a time here: {booking_url}",
    # a line the first replies and the booking counter-proposals also carry.
    d1 = e["cadence.d1"]
    want = [b["tag"] for b in manifest["blocks"]
            if EASIER in b["text"] and b["tag"] not in (
                "cadence.d1", "cadence.d2", "cadence.d1/no_slots", "cadence.d2/no_slots")]
    assert _all_also_in(d1) == sorted(want, key=lambda t: (route_doc.route(t, by_tag[t])[0],
                                                             want.index(t)))
    assert len(want) == 110
    assert set(d1["also_in"]) == {"1", "2"}
    assert "first_reply.cleaning_reactivation.default.full" in d1["also_in"]["1"]
    assert "booking.counter.window_no_fit" in d1["also_in"]["2"]
    # No other cadence block holds d1's lines.
    assert not [t for t in _all_also_in(d1) if t.startswith("cadence.")]
    # d2 dropped "I have {slots} open, or grab a time here: {booking_url}",
    # a sentence cadence.d14 also has.
    assert e["cadence.d2"]["also_in"] == {"1": ["cadence.d14"]}
    # Deleting d2/no_slots removes "Grab any open time here: {booking_url}",
    # which the d4, d5 and d14 no_slots bodies share; d1/no_slots shares
    # nothing. Every no_slots body still has a text_group of its own.
    assert e["cadence.d2/no_slots"]["also_in"] == {
        "1": ["cadence.d4/no_slots", "cadence.d5/no_slots", "cadence.d14/no_slots"]}
    assert e["cadence.d1/no_slots"]["also_in"] == {}
    groups = [b["text_group"] for b in manifest["blocks"] if route_doc.NO_SLOTS_RE.match(b["tag"])]
    assert len(groups) == len(set(groups)) == 8  # one per NO_SLOTS_BODIES key
    text = route_doc.render_text(_report(_read(FIRST_EDITS)))
    assert "also appears in 110 other blocks (section 1: first_reply." in text
    assert " and %d more" % (len(d1["also_in"]["1"]) - 15) in text
    assert "section 2: booking.counter.window_no_fit" in text


def test_time_offer_edit_lists_the_other_first_replies(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n")
    tag = "first_reply.cleaning_reactivation.default.full"
    _edit_first_body_line(lines, tag, lambda l: l)  # sanity: the block exists
    start = next(i for i, l in enumerate(lines) if "(tag: %s)" % tag in l)
    idx = next(i for i in range(start, len(lines)) if lines[i].strip() == TIME_OFFER)
    lines[idx] = lines[idx].replace("15-minute call", "quick call")
    r = _report(_write(tmp_path, lines))
    e = _entries(r)
    assert list(e) == [tag]
    manifest = route_doc.diff_doc.load_manifest(MANIFEST)
    carriers = [b["tag"] for b in manifest["blocks"] if TIME_OFFER in b["text"] and b["tag"] != tag]
    assert len(carriers) == 59
    got = _all_also_in(e[tag])
    assert set(carriers) == set(got)
    assert all(t.startswith("first_reply.") for t in carriers)
    assert "first_reply.bookkeeping_trigger.pricing.full" in e[tag]["also_in"]["1"]
    md = route_doc.render_md(r)
    assert "- also appears in %d other blocks (section 1: " % len(got) in md


def test_booking_link_sentence_edit_inside_a_time_offer_line(tmp_path):
    # The booking-link sentence shares a doc line with the time offer; the
    # edit is matched per sentence, so every block with that sentence counts.
    lines = _read(UPLOAD_EXPORT).split("\n")
    tag = "first_reply.cleaning_reactivation.default.full"
    start = next(i for i, l in enumerate(lines) if "(tag: %s)" % tag in l)
    idx = next(i for i in range(start, len(lines)) if lines[i].strip() == TIME_OFFER)
    lines[idx] = lines[idx].replace("Or if it's easier, grab a time here", "Or just grab a time here")
    e = _entries(_report(_write(tmp_path, lines)))
    assert list(e) == [tag]
    manifest = route_doc.diff_doc.load_manifest(MANIFEST)
    carriers = [b["tag"] for b in manifest["blocks"] if EASIER in b["text"] and b["tag"] != tag]
    assert len(carriers) == 110
    assert sorted(_all_also_in(e[tag])) == sorted(carriers)
    assert set(e[tag]["also_in"]) == {"1", "2"}


def test_short_heading_edit_lists_the_other_prereads(tmp_path):
    # "Proof" is one word but not a greeting or sign-off, so it counts.
    lines = _read(UPLOAD_EXPORT).split("\n")
    tag = "show_rate.preread_email.cleaning_reactivation"
    start = next(i for i, l in enumerate(lines) if "(tag: %s)" % tag in l)
    idx = next(i for i in range(start, len(lines)) if lines[i].strip() == "Proof")
    lines[idx] = lines[idx].replace("Proof", "Proof points")
    e = _entries(_report(_write(tmp_path, lines)))
    assert list(e) == [tag]
    others = ["show_rate.preread_email.%s" % k for k in (
        "cleaning_outbound", "bookkeeping_reactivation", "bookkeeping_outbound",
        "recruiting_reactivation", "recruiting_outbound", "generic_reactivation",
        "generic_outbound")]
    assert e[tag]["also_in"] == {"2": others}


def _edit_in_block(tmp_path, tag, old, new):
    """Replace old with new in the first line under `tag` that holds it."""
    lines = _read(UPLOAD_EXPORT).split("\n")
    start = next(i for i, l in enumerate(lines) if "(tag: %s)" % tag in l)
    idx = next(i for i in range(start + 1, len(lines)) if old in lines[i])
    assert not [l for l in lines[start + 1:idx]
                if "(tag:" in l and not re.search(r"/subject\)\s*$", l)], "%s not under %s" % (old, tag)
    lines[idx] = lines[idx].replace(old, new, 1)
    e = _entries(_report(_write(tmp_path, lines)))
    assert list(e) == [tag]
    return e[tag]


def test_words_added_in_front_of_a_shared_sentence_count(tmp_path):
    # The old sentence is still inside the new one, but no longer starts a
    # sentence, so it counts as edited.
    tag = "no_show.ns_d3_value_email.cleaning_reactivation"
    e = _edit_in_block(tmp_path, tag, "I built a similar system", "Last year I built a similar system")
    manifest = route_doc.diff_doc.load_manifest(MANIFEST)
    built = "I built a similar system for a commercial roofer doing $150M/year."
    carriers = [b["tag"] for b in manifest["blocks"] if built in b["text"] and b["tag"] != tag]
    assert len(carriers) == 11
    assert sorted(_all_also_in(e)) == sorted(carriers)
    assert "cadence.d4.case_study.reactivation" in e["also_in"]["1"]
    assert "instantly.cleaning_reactivation.step1" in e["also_in"]["4"]
    e = _edit_in_block(tmp_path, "cadence.d2", "I have {slots} open", "Right now I have {slots} open")
    assert e["also_in"] == {"1": ["cadence.d14"]}


def test_sentence_rules():
    assert route_doc._edited_sentences(
        "Plan for {company}. Think about it. Proof",
        "Plan for {company}.Think about it. Proof points") == ["Proof"]
    assert route_doc._edited_sentences(
        "Hi. I have {slots} open.", "Hi. Honestly, I have {slots} open.") == ["I have {slots} open."]
    assert route_doc._edited_sentences("Hi. I have {slots} open.", "Hi.I have {slots} open.") == []
    for s in ("Hey {first_name},", "Hi {first_name},", "Hey there,", "Lorenzo",
              "Thanks,", "Talk soon,", "{booking_url}", "{first_name},",
              "Hey {{firstName}},", "Hi {{firstName}},"):
        assert route_doc._boilerplate(s), s
    for s in ("Proof", "What it costs", "Hey {first_name}, Lorenzo again."):
        assert not route_doc._boilerplate(s), s


def test_shared_subject_edit_lists_every_copy(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n")
    idx = next(i for i, l in enumerate(lines) if "(tag: cadence.d1/subject)" in l)
    lines[idx] = lines[idx].replace("Re: {original_subject}", "Re: {original_subject} (times)")
    e = _entries(_report(_write(tmp_path, lines)))
    assert list(e) == ["cadence.d1/subject"]
    manifest = route_doc.diff_doc.load_manifest(MANIFEST)
    group = [b["tag"] for b in manifest["blocks"]
             if b.get("text_group") == "6379c4faef3d" and b["tag"] != "cadence.d1/subject"]
    assert len(group) == 58
    assert sorted(_all_also_in(e["cadence.d1/subject"])) == sorted(group)
    assert "booking.already_booked.awaiting_approval/subject" in e["cadence.d1/subject"]["also_in"]["2"]


def test_greeting_and_sign_off_edits_do_not_list_everything(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n")
    start = next(i for i, l in enumerate(lines) if "(tag: cadence.d14)" in l)
    g = next(i for i in range(start, len(lines)) if lines[i].strip() == "Hey {first_name},")
    lines[g] = "Hi {first_name},"
    s = next(i for i in range(g, len(lines)) if lines[i].strip() == "Lorenzo")
    lines[s] = "Lorenzo V"
    e = _entries(_report(_write(tmp_path, lines)))
    assert list(e) == ["cadence.d14"]
    assert e["cadence.d14"]["also_in"] == {}
    assert route_doc.also_in_summary(e["cadence.d14"]) is None


def test_lines_in_more_than_half_the_blocks_do_not_count():
    common = "This line is everywhere in the doc"
    blocks = [{"tag": "first_reply.x%d" % i, "text": "Hey {first_name},\n\n%s\n\nLorenzo" % common,
               "text_group": "g%d" % i} for i in range(5)]
    blocks.append({"tag": "cadence.d9", "text": "Something rare but long enough", "text_group": "r"})
    blocks.append({"tag": "cadence.d10", "text": "Something rare but long enough\n" + common,
                   "text_group": "s"})
    normed = dict((b["tag"], route_doc.diff_doc.norm(b["text"])) for b in blocks)
    got = route_doc._also_in("first_reply.x0", blocks[0]["text"], "Hey,", blocks, normed, set(), {})
    assert got == {}  # common line in 6 of 7 blocks; greeting and sign-off ignored
    got = route_doc._also_in("cadence.d9", blocks[5]["text"], None, blocks, normed, set(), {})
    assert got == {"1": ["cadence.d10"]}
    got = route_doc._also_in("cadence.d9", blocks[5]["text"], None, blocks, normed, {"cadence.d10"}, {})
    assert got == {}


def test_new_entries_have_no_also_in_and_clean_export_stays_empty(tmp_path):
    lines = _read(UPLOAD_EXPORT).split("\n") + [
        "Brand new email (tag: something.new)", EASIER, ""]
    e = _entries(_report(_write(tmp_path, lines)))
    assert "also_in" not in e["something.new"]
    r = _report(_read(UPLOAD_EXPORT))
    assert r["counts"]["routed"] == 0 and all(v == [] for v in r["sections"].values())
