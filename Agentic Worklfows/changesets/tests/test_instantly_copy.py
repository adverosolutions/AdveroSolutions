"""Instantly copy change-set (doc edits -> staged sequences -> PATCH).

Offline: the input is tools/template_doc/drive_export.txt (Drive's export right
after upload, which diffs clean against the manifest) with edits applied in a
tmp copy; the baseline is config/snapshots/instantly_campaigns_2026-09-21.json;
every HTTP call is an httpx.MockTransport; the clock is injected. Nothing here
can reach Instantly.
"""
import copy
import hashlib
import json
import os
from datetime import datetime, timezone

import httpx
import pytest

from shared import job_log, settings
from shared.instantly import Instantly
from changesets import rollback as R
from changesets.instantly_copy import apply_instantly_copy as app
from changesets.instantly_copy import build_from_doc as bfd
from changesets.instantly_copy import copy_lib as C
from changesets.instantly_phase0 import phase0_lib as L

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXPORT = os.path.join(ROOT, "tools", "template_doc", "drive_export.txt")
MANIFEST = os.path.join(ROOT, "tools", "template_doc", "manifest.json")
SNAPSHOT = os.path.join(ROOT, "config", "snapshots", "instantly_campaigns_2026-09-21.json")
NOW = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)
STAMP = "20260923T200000Z"

CR = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"   # cleaning_reactivation
CT = "f347604e-48c7-4813-831c-dc7b9d4b50ae"   # cleaning_trigger
KEYS = ["cleaning_reactivation", "cleaning_trigger", "bookkeeping_reactivation",
        "bookkeeping_trigger", "recruiting_reactivation", "recruiting_outbound"]

BODY_EDIT = ("Let me know.\r\n", "Let me know if that works.\r\n")                       # cleaning_reactivation step 1
TRIGGER_BODY_EDIT = ("I do this by watching for triggers (new leases",                   # cleaning_trigger step 1
                     "I do this by tracking triggers (new leases")
SUBJECT_EDIT = ("Subject: {{firstName}}, question (tag: instantly.cleaning_trigger.step1/subject)",
                "Subject: {{firstName}}, quick question (tag: instantly.cleaning_trigger.step1/subject)")


@pytest.fixture(scope="module")
def snapshot():
    with open(SNAPSHOT, "r", encoding="utf-8") as fh:
        return {c["id"]: c for c in json.load(fh)["items"]}


@pytest.fixture(scope="module")
def manifest():
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        return json.load(fh)


def export_text():
    with open(EXPORT, "rb") as fh:
        return fh.read().decode("utf-8-sig")


def edited_export(tmp_path, *edits, name="export.txt", text=None):
    text = export_text() if text is None else text
    for old, new in edits:
        assert old in text, old
        text = text.replace(old, new, 1)
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return str(path)


def collector():
    lines = []
    return lines, lines.append


def build(export, out_dir, **kw):
    lines, out = collector()
    code = bfd.build(export, MANIFEST, str(out_dir), now=NOW, out=out, **kw)
    return code, "\n".join(lines)


def staged_dir(tmp_path, *edits):
    out_dir = tmp_path / "staged"
    code, text = build(edited_export(tmp_path, *edits), out_dir)
    assert code == 0, text
    return out_dir


class Recorder(object):
    """Serves campaigns on GET, applies a PATCH to its own copy and answers
    with the updated campaign (what the real API returns). ``on_patch`` runs
    before the PATCH is applied; ``patch_status`` makes the PATCH fail;
    ``missing`` answers 404 for those campaign ids."""

    def __init__(self, campaigns, on_patch=None, patch_status=None, missing=()):
        self.campaigns = copy.deepcopy(campaigns)
        self.requests = []
        self.on_patch = on_patch
        self.patch_status = patch_status
        self.missing = set(missing)

    def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        if path.startswith("/api/v2/campaigns/"):
            cid = path.rsplit("/", 1)[1]
            if cid in self.missing:
                return httpx.Response(404, json={"error": "not found"})
            if request.method == "GET":
                return httpx.Response(200, json=self.campaigns[cid])
            if request.method == "PATCH":
                if self.on_patch:
                    self.on_patch(request)
                if self.patch_status:
                    return httpx.Response(self.patch_status, json={"error": "boom"})
                self.campaigns[cid].update(json.loads(request.content))
                return httpx.Response(200, json=self.campaigns[cid])
        return httpx.Response(404, json={"error": "not mocked"})

    @property
    def methods(self):
        return [r.method for r in self.requests]


def make_client(campaigns, **kw):
    rec = Recorder(campaigns, **kw)
    return Instantly(api_key="test-key", transport=httpx.MockTransport(rec), sleep=lambda s: None), rec


def run_app(argv, client=None, backup_dir=None, dryrun_dir=None, confirm=None):
    lines, out = collector()
    code = app.main(argv, client=client, now=NOW, out=out, backup_dir=str(backup_dir) if backup_dir else app.BACKUP_DIR,
                    confirm=confirm, dryrun_dir=str(dryrun_dir) if dryrun_dir else None)
    return code, "\n".join(lines)


def apply_argv(out_dir, key="cleaning_reactivation", yes=True):
    return ["--staged", str(out_dir), "--apply", "--campaign", key] + (["--yes"] if yes else [])


def steps(campaign_or_seqs):
    seqs = campaign_or_seqs.get("sequences") if isinstance(campaign_or_seqs, dict) else campaign_or_seqs
    return C.steps_of(seqs)


# ------------------------------------------------------ text_to_html finding
ROUNDTRIP_FAILS = {
    # three bodies carry a trailing &nbsp; the plain text drops ...
    "instantly.cleaning_trigger.step1",
    "instantly.bookkeeping_trigger.step1",
    "instantly.recruiting_reactivation.step1",
    # ... and one has "<div><br />Would you ...</div>" (a break inside a line)
    "instantly.bookkeeping_reactivation.step1",
}


def test_text_to_html_roundtrip_finding(manifest):
    """text_to_html(manifest text) == manifest raw_html for 8 of the 12 live
    bodies; the 4 in ROUNDTRIP_FAILS do not reproduce byte for byte. So only an
    EDITED variant is regenerated from the doc; every other body is copied
    from the baseline untouched (next tests)."""
    fails = set()
    bodies = [b for b in manifest["blocks"] if b["tag"].startswith("instantly.") and b["field"] == "body"]
    assert len(bodies) == 12
    for b in bodies:
        if L.text_to_html(b["text"]) != b["raw_html"]:
            fails.add(b["tag"])
            assert C.format_notes(b["raw_html"], b["text"])
        else:
            assert C.format_notes(b["raw_html"], b["text"]) == []
    assert fails == ROUNDTRIP_FAILS


def test_drive_export_body_text_equals_the_manifest_text(manifest):
    """Drive writes each paragraph gap as two blank lines; body_text_from_doc
    collapses them, and gives exactly the manifest text for all 12 bodies."""
    parsed = C.parse_doc.parse_with_info(export_text())["blocks"]
    for b in manifest["blocks"]:
        if b["tag"].startswith("instantly.") and b["field"] == "body":
            assert parsed[b["tag"]] != b["text"]              # the export really does double the gaps
            assert C.body_text_from_doc(parsed[b["tag"]]) == b["text"], b["tag"]


def test_unchanged_non_roundtrip_bodies_stay_byte_identical(tmp_env, tmp_path, snapshot):
    edit = ("Worth a quick 15 minute call? Just reply yes and I'll send a calendar invite.\r\n\r\n\r\n"
            "Thanks for the time,\r\nLorenzo\r\nBookkeeping, outbound offer",
            "Worth a short 15 minute call? Just reply yes and I'll send a calendar invite.\r\n\r\n\r\n"
            "Thanks for the time,\r\nLorenzo\r\nBookkeeping, outbound offer")
    out_dir = staged_dir(tmp_path, edit)          # bookkeeping_reactivation step 2
    doc = json.loads((out_dir / "bookkeeping_reactivation.json").read_text())
    live_step1 = steps(snapshot["f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"])[0]
    assert "<div><br />Would you be open" in live_step1["variants"][0]["body"]
    assert json.dumps(steps(doc)[0]) == json.dumps(live_step1)
    assert "Worth a short 15 minute call?" in steps(doc)[1]["variants"][0]["body"]


def test_note_regexes_match_the_doc_router():
    import route_doc
    assert C.NOTE_MARK_RE.pattern == route_doc.NOTE_MARK_RE.pattern
    assert C.NOTE_START_RE.pattern == route_doc.NOTE_START_RE.pattern
    assert C.NOTE_MARK_RE.flags == route_doc.NOTE_MARK_RE.flags


# ------------------------------------------------------------------ build
def test_clean_export_stages_nothing(tmp_env, tmp_path):
    out_dir = tmp_path / "staged"
    code, text = build(EXPORT, out_dir)
    assert code == 0
    assert "No Instantly changes in this export; nothing staged" in text
    assert "whitespace/quote-only" not in text
    assert not out_dir.exists()


def test_a_build_fingerprint_tag_does_not_break_the_build(tmp_env, tmp_path):
    text = export_text().replace("Every email the system sends\r\n",
                                 "Every email the system sends\r\nBuild 3f2a9c (tag: X-BUILD)\r\n", 1)
    out_dir = tmp_path / "staged"
    code, out = build(edited_export(tmp_path, BODY_EDIT, text=text), out_dir)
    assert code == 0, out
    assert sorted(os.listdir(str(out_dir))) == ["cleaning_reactivation.json", "staged.json"]


def test_two_bodies_in_two_campaigns_stage_two_files(tmp_env, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT, TRIGGER_BODY_EDIT)
    assert sorted(os.listdir(str(out_dir))) == ["cleaning_reactivation.json", "cleaning_trigger.json", "staged.json"]
    cr = json.loads((out_dir / "cleaning_reactivation.json").read_text())
    live = snapshot[CR]
    assert cr["baseline_sequences"] == live["sequences"]
    assert json.dumps(steps(cr)[1]) == json.dumps(steps(live)[1])       # unchanged step: byte-identical
    new_text = L.html_to_text(steps(live)[0]["variants"][0]["body"]).replace("Let me know.", "Let me know if that works.")
    assert steps(cr)[0]["variants"][0]["body"] == L.text_to_html(new_text)
    assert steps(cr)[0]["variants"][0]["subject"] == steps(live)[0]["variants"][0]["subject"]
    for k in ("type", "delay", "delay_unit", "pre_delay_unit"):
        assert steps(cr)[0][k] == steps(live)[0][k]
    ct = json.loads((out_dir / "cleaning_trigger.json").read_text())
    assert "I do this by tracking triggers" in steps(ct)[0]["variants"][0]["body"]
    assert json.dumps(steps(ct)[1]) == json.dumps(steps(snapshot[CT])[1])


def test_one_subject_edit_is_staged_for_every_campaign_sharing_it(tmp_env, tmp_path, snapshot):
    """The six step-1 subjects are one shared sentence: the doc says changing
    one copy changes them all."""
    export = edited_export(tmp_path, BODY_EDIT, SUBJECT_EDIT)
    out_dir = tmp_path / "staged"
    code, text = build(export, out_dir)
    assert code == 0, text
    assert sorted(os.listdir(str(out_dir))) == sorted(["%s.json" % k for k in KEYS] + ["staged.json"])
    for key in KEYS:
        doc = json.loads((out_dir / ("%s.json" % key)).read_text())
        assert steps(doc)[0]["variants"][0]["subject"] == "{{firstName}}, quick question"
        assert "same shared sentence as instantly.cleaning_trigger.step1/subject" in text or key == "cleaning_trigger"
    cr = json.loads((out_dir / "cleaning_reactivation.json").read_text())
    assert "Let me know if that works." in steps(cr)[0]["variants"][0]["body"]
    bt = json.loads((out_dir / "bookkeeping_trigger.json").read_text())
    base = snapshot["87ebb167-9b64-4b6f-b658-88f3d1af9980"]
    assert steps(bt)[0]["variants"][0]["body"] == steps(base)[0]["variants"][0]["body"]
    meta = json.loads((out_dir / "staged.json").read_text())
    prop = dict((c["tag"], c["propagated_from"]) for c in meta["changes"])
    assert prop["instantly.cleaning_trigger.step1/subject"] is None
    assert prop["instantly.recruiting_outbound.step1/subject"] == "instantly.cleaning_trigger.step1/subject"


def test_two_copies_of_a_shared_subject_edited_differently_are_refused(tmp_env, tmp_path):
    other = ("Subject: {{firstName}}, question (tag: instantly.recruiting_outbound.step1/subject)",
             "Subject: {{firstName}}, a thought (tag: instantly.recruiting_outbound.step1/subject)")
    out_dir = tmp_path / "staged"
    code, text = build(edited_export(tmp_path, SUBJECT_EDIT, other), out_dir)
    assert code == bfd.EXIT_INVALID and "edited to different texts" in text and not out_dir.exists()


def test_staged_json_records_the_export_hash_and_every_change(tmp_env, tmp_path):
    export = edited_export(tmp_path, BODY_EDIT, TRIGGER_BODY_EDIT)
    out_dir = tmp_path / "staged"
    assert build(export, out_dir)[0] == 0
    meta = json.loads((out_dir / "staged.json").read_text())
    with open(export, "rb") as fh:
        assert meta["export_sha256"] == hashlib.sha256(fh.read()).hexdigest()
    with open(MANIFEST, "rb") as fh:
        assert meta["manifest_sha256"] == hashlib.sha256(fh.read()).hexdigest()
    with open(SNAPSHOT, "rb") as fh:
        assert meta["snapshot_sha256"] == hashlib.sha256(fh.read()).hexdigest()
    assert meta["tool"] == "instantly_copy/build_from_doc"
    assert meta["doc_id"] == "1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U"
    assert meta["built_at"] == "2026-09-23T20:00:00+00:00"
    assert meta["export"] == export and meta["manifest"] == "tools/template_doc/manifest.json"
    got = dict((c["tag"], c) for c in meta["changes"])
    assert sorted(got) == ["instantly.cleaning_reactivation.step1", "instantly.cleaning_trigger.step1"]
    body = got["instantly.cleaning_reactivation.step1"]
    assert (body["campaign_key"], body["campaign_id"], body["step"], body["variant_index"], body["field"]) == \
        ("cleaning_reactivation", CR, 1, 0, "body")
    assert "Let me know.\n" in body["old"] and "Let me know if that works." in body["new"]
    assert body["format_notes"] == []
    assert got["instantly.cleaning_trigger.step1"]["format_notes"] == [
        "formatting-only change: trailing non-breaking spaces removed"]


def test_non_instantly_edits_are_ignored(tmp_env, tmp_path):
    parsed = C.parse_doc.parse_with_info(export_text())["blocks"]
    tag = next(t for t in parsed if not t.startswith("instantly.") and not t.endswith("/subject") and parsed[t])
    first_line = parsed[tag].split("\n")[0]
    out_dir = tmp_path / "staged"
    code, text = build(edited_export(tmp_path, (first_line + "\r\n", first_line + " Edited.\r\n")), out_dir)
    assert code == 0 and "outside Instantly ignored" in text and not out_dir.exists()


def test_quote_only_edits_are_listed_not_staged(tmp_env, tmp_path):
    out_dir = tmp_path / "staged"
    code, text = build(edited_export(tmp_path, ("Just reply yes and I'll send", "Just reply yes and I’ll send")),
                       out_dir)
    assert code == 0
    assert "whitespace/quote-only edits, not staged (Instantly keeps the old text): " \
           "instantly.cleaning_reactivation.step2" in text
    assert "No Instantly changes" in text and not out_dir.exists()


def _delete_step2():
    text = export_text()
    start = text.index("Step 2: 3 days later, if they haven't replied (tag: instantly.cleaning_reactivation.step2)")
    end = text.index("Cleaning, outbound offer (section)")
    return text[:start] + text[end:]


GUARANTEE = "signed within 90 days, or I give your money back"      # cleaning_trigger step 1 (first in the doc)
NOTE_ANCHOR = ("Subject: (tag: instantly.cleaning_trigger.step2/subject)\r\n"
               "No subject of its own: it goes as a reply in the same thread. (note)\r\n")

REFUSALS = [
    ("em dash", [("Let me know.\r\n", "Let me know — either way.\r\n")], "em dash"),
    ("en dash", [("Let me know.\r\n", "Let me know – either way.\r\n")], "en dash"),
    ("double hyphen", [("Let me know.\r\n", "Let me know -- either way.\r\n")], "'--' used as a dash"),
    ("figure dash", [("Let me know.\r\n", "Let me know ‒ either way.\r\n")], "figure dash"),
    ("horizontal bar", [("Let me know.\r\n", "Let me know ― either way.\r\n")], "horizontal bar"),
    ("minus sign", [("Let me know.\r\n", "Let me know − either way.\r\n")], "minus sign"),
    ("small em dash", [("Let me know.\r\n", "Let me know ﹘ either way.\r\n")], "small em dash"),
    ("exclamation", [("Let me know.\r\n", "Let me know!\r\n")], "exclamation mark"),
    ("full-width exclamation", [("Let me know.\r\n", "Let me know！\r\n")], "full-width exclamation"),
    ("emoji exclamation", [("Let me know.\r\n", "Let me know ❗\r\n")], "exclamation mark emoji"),
    ("single brace", [("Let me know.\r\n", "Let me know, {first_name}.\r\n")], "single-brace placeholder {first_name}"),
    ("unbalanced", [("Let me know.\r\n", "Let me know, {{firstName}.\r\n")], "unbalanced"),
    ("unknown variable", [("Let me know.\r\n", "Let me know, {{first_name}}.\r\n")], "{{first_name}} is not a variable"),
    ("variable inside a spin", [("Let me know.\r\n", "{{RANDOM | Hey {{firstName}} | Hi {{firstName}}}}\r\n")],
     "merge variable inside a spin option"),
    ("spin with one option", [("Let me know.\r\n", "{{RANDOM | Let me know}}.\r\n")], "at least two options"),
    ("spin with an empty option", [("Let me know.\r\n", "{{RANDOM | Let me know | }}.\r\n")], "empty option"),
    ("spin with a repeated option", [("Let me know.\r\n", "{{RANDOM | Let me know | Let me know}}.\r\n")],
     "repeats an option"),
    ("variable inside a spin in a subject", [SUBJECT_EDIT[:1] + (
        "Subject: {{RANDOM | {{firstName}}, question | a question}} (tag: instantly.cleaning_trigger.step1/subject)",)],
     "merge variable inside a spin option"),
    ("new dollar figure", [("Let me know.\r\n", "Worth $9,999 to you.\r\n")], "new dollar figure $9,999"),
    ("new promised window", [("Let me know.\r\n", "Results within 14 days.\r\n")], "new time window '14 days'"),
    ("next 2 weeks", [("Let me know.\r\n", "Free in the next 2 weeks?\r\n")], "new time window '2 weeks'"),
    ("window in words", [("Let me know.\r\n", "Results in sixty days.\r\n")], "new time window '60 days'"),
    ("changed guarantee window", [(GUARANTEE, GUARANTEE.replace("signed within 90 days", "signed in the first 60 days"))],
     "new time window '60 days'"),
    ("changed case-study window", [("$180K in new contracts in 90 days", "$180K in new contracts in just 60 days")],
     "new time window '60 days'"),
    ("60 day guarantee", [(GUARANTEE, GUARANTEE.replace("90 days,", "90 days (a 60 day guarantee),"))],
     "new time window '60 days'"),
    ("over the next 60 days", [(GUARANTEE, GUARANTEE.replace("90 days,", "90 days, over the next 60 days,"))],
     "new time window '60 days'"),
    ("60 days from kickoff", [(GUARANTEE, GUARANTEE.replace("90 days,", "90 days (60 days from kickoff),"))],
     "new time window '60 days'"),
    ("ai mention", [("Let me know.\r\n", "My AI does the work.\r\n")], "mentions AI"),
    ("step 2 subject", [("Subject: (tag: instantly.cleaning_reactivation.step2/subject)",
                         "Subject: following up (tag: instantly.cleaning_reactivation.step2/subject)")], "new thread"),
    ("step 1 subject removed", [("Subject: {{firstName}}, question (tag: instantly.cleaning_reactivation.step1/subject)",
                                 "Subject: (tag: instantly.cleaning_reactivation.step1/subject)")], "the subject is empty"),
    ("note for Claude", [("Let me know.\r\n", "Let me know.\r\nNOTE: Claude, can we try a shorter sign-off here?\r\n")],
     "holds a note, not email copy"),
    ("note marker", [("Let me know.\r\n", "Let me know.\r\n(note) also check the subject\r\n")],
     "holds a note, not email copy"),
    ("section marker deleted", [("Cleaning, outbound offer (section)", "Cleaning, outbound offer")],
     "holds a line of the doc's own layout"),
    ("note marker deleted", [(NOTE_ANCHOR, NOTE_ANCHOR.replace(" (note)", ""))], "holds a line of the doc's own layout"),
    ("tag fragment", [("Let me know.\r\n", "Let me know. (tag: something\r\n")], "holds a doc marker"),
    ("unknown instantly tag", [("Thanks,\r\nLorenzo\r\nStep 2:",
                                "Thanks,\r\nLorenzo\r\nStep 3 (tag: instantly.cleaning_reactivation.step3)\r\nHi\r\nStep 2:")],
     "unknown tag instantly.cleaning_reactivation.step3"),
    ("duplicate tag", [("Subject: {{firstName}}, question (tag: instantly.cleaning_trigger.step1/subject)",
                        "Subject: {{firstName}}, question (tag: instantly.cleaning_reactivation.step1/subject)")],
     "duplicate tags"),
]


@pytest.mark.parametrize("name,edits,expect", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_refused_with_nothing_written(tmp_env, tmp_path, name, edits, expect):
    out_dir = tmp_path / "staged"
    code, text = build(edited_export(tmp_path, *edits), out_dir)
    assert code == bfd.EXIT_INVALID, text
    assert "REFUSED" in text and expect in text, text
    assert not out_dir.exists()


def test_an_empty_body_is_refused(tmp_env, tmp_path):
    text = export_text()
    start = text.index("Subject: {{firstName}}, question (tag: instantly.cleaning_reactivation.step1/subject)\r\n")
    start = text.index("\n", start) + 1
    end = text.index("Step 2: 3 days later, if they haven't replied (tag: instantly.cleaning_reactivation.step2)")
    out_dir = tmp_path / "staged"
    code, out = build(edited_export(tmp_path, text=text[:start] + text[end:]), out_dir)
    assert code == bfd.EXIT_INVALID and "instantly.cleaning_reactivation.step1: the body is empty" in out
    assert not out_dir.exists()


def test_a_deleted_instantly_step_is_refused(tmp_env, tmp_path):
    out_dir = tmp_path / "staged"
    code, text = build(edited_export(tmp_path, text=_delete_step2()), out_dir)
    assert code == bfd.EXIT_INVALID
    assert "instantly.cleaning_reactivation.step2 is missing from the doc" in text
    assert not out_dir.exists()


EXEMPT_SHAPES = [
    "We talked 3 days ago.",                        # "N <unit> ago"
    "We met two weeks ago.",
    "Clients for 1 year now.",                      # "for N years" (tenure)
    "We have done this for over 10 years.",
    "Our team has 12 years in business.",           # "N years in business"
    "I have 15 years of experience.",               # "N years of experience"
]


@pytest.mark.parametrize("line", EXEMPT_SHAPES)
def test_non_promise_time_shapes_pass(tmp_env, tmp_path, line):
    code, text = build(edited_export(tmp_path, ("Let me know.\r\n", line + "\r\n")), tmp_path / "staged")
    assert code == 0, text


def test_time_windows_parse_words_digits_and_hyphens():
    got = [(k, e) for _p, k, e in C.time_windows("a 60-day plan, sixty days, twenty-one days, 3 weeks ago, "
                                                  "for 5 years, 2 months")]
    assert got == [("60 day", False), ("60 day", False), ("21 day", False), ("3 week", True),
                   ("5 year", True), ("2 month", False)]


def test_allowed_promise_window_passes(tmp_env, tmp_path):
    # "within 6 months" is in the reactivation proof line of config/offers.md
    code, text = build(edited_export(tmp_path, ("Let me know.\r\n", "Most come back within 6 months.\r\n")),
                       tmp_path / "staged")
    assert code == 0, text


def test_warnings_spaces_in_braces_square_brackets_removed_variables(tmp_env, tmp_path):
    edits = [("Let me know.\r\n", "Let me know, {{ firstName }}, or [first_name].\r\n"),
             ("- I want to build a reactivation system for {{companyName}}. Goal is to bring back the accounts",
              "- I want to build a reactivation system for you. Goal is to bring back the accounts")]
    code, text = build(edited_export(tmp_path, *edits), tmp_path / "staged")
    assert code == 0, text
    assert "has spaces inside the braces; write {{firstName}}" in text
    assert "square-bracket text [first_name]" in text
    assert "instantly.cleaning_reactivation.step2: {{companyName}} was in the old text and is not in the new one" in text


def test_curly_quotes_are_staged_as_typed_with_a_warning(tmp_env, tmp_path):
    out_dir = tmp_path / "staged"
    code, text = build(edited_export(tmp_path, ("Let me know.\r\n", "Let me know, it’s fine.\r\n")), out_dir)
    assert code == 0, text
    assert "warn  instantly.cleaning_reactivation.step1: curly quotes typed in the new text" in text
    cr = json.loads((out_dir / "cleaning_reactivation.json").read_text())
    assert "it’s fine." in steps(cr)[0]["variants"][0]["body"]


def test_offer_checks_fail_closed(tmp_env, tmp_path, monkeypatch):
    export = edited_export(tmp_path, BODY_EDIT)
    monkeypatch.setattr(settings, "OFFERS_LOADED", False)
    code, text = build(export, tmp_path / "staged")
    assert code == bfd.EXIT_INVALID and "config/offers.md is missing or empty" in text
    monkeypatch.setattr(settings, "OFFERS_LOADED", True)
    campaigns = copy.deepcopy(settings.CAMPAIGNS)
    campaigns["cleaning_reactivation"].pop("offer")
    monkeypatch.setattr(settings, "CAMPAIGNS", campaigns)
    code, text = build(export, tmp_path / "staged")
    assert code == bfd.EXIT_INVALID and "no offer type" in text
    assert not (tmp_path / "staged").exists()


# ------------------------------------------------------------- out folder
def test_out_outside_the_staged_folder_is_refused(tmp_env, tmp_path, monkeypatch):
    """Runs against FAKE config/ and changesets/backups/ folders: the allowed
    roots are pointed at a fake repo tree, so a regression can never delete a
    real rollback point or config file."""
    repo = tmp_path / "repo"
    staged_root = repo / "changesets" / "instantly_copy" / "staged"
    staged_root.mkdir(parents=True)
    monkeypatch.setattr(C, "allowed_out_roots", lambda: (str(staged_root),))
    fake_config = repo / "config"
    fake_config.mkdir()
    (fake_config / "ids.json").write_text("{}")
    (fake_config / "staged.json").write_text('{"tool": "instantly_copy/build_from_doc", "campaigns": {"ids": "ids.json"}}')
    fake_backups = repo / "changesets" / "backups"
    fake_backups.mkdir()
    (fake_backups / ("instantly_copy_%s_%s.json" % (CR, STAMP))).write_text("{}")
    export = edited_export(tmp_path, BODY_EDIT)
    for target in (fake_config, fake_backups, staged_root, tmp_path / "elsewhere"):
        before = sorted(os.listdir(str(target))) if target.exists() else None
        code, text = build(export, target, overwrite=True)
        assert code == bfd.EXIT_INVALID and "outside changesets/instantly_copy/staged/" in text
        assert (sorted(os.listdir(str(target))) if target.exists() else None) == before
    assert (fake_config / "ids.json").read_text() == "{}"
    code, text = build(export, staged_root / "ok", overwrite=True)
    assert code == 0, text


def test_the_real_config_and_backups_folders_are_not_allowed_out_dirs():
    for target in (os.path.join(ROOT, "config"), os.path.join(ROOT, "changesets", "backups"), C.STAGED_ROOT):
        assert not C.out_dir_allowed(target)
    assert C.out_dir_allowed(os.path.join(C.STAGED_ROOT, "2026-09-23T1815Z"))


def test_overwrite_never_touches_a_folder_it_did_not_write(tmp_env, tmp_path):
    out_dir = tmp_path / "backups"
    out_dir.mkdir()
    point = out_dir / ("instantly_copy_%s_%s.json" % (CR, STAMP))
    point.write_text('{"id": "x"}')
    (out_dir / "staged.json").write_text('{"campaigns": {"x": "instantly_copy_x.json"}}')
    code, text = build(edited_export(tmp_path, BODY_EDIT), out_dir, overwrite=True)
    assert code == bfd.EXIT_INVALID and "not replaced" in text
    assert sorted(os.listdir(str(out_dir))) == sorted([point.name, "staged.json"])


def test_overwrite_deletes_only_the_files_its_staged_json_lists(tmp_env, tmp_path):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    keep = out_dir / ("instantly_copy_%s_%s.json" % (CR, STAMP))
    keep.write_text('{"rollback": true}')
    before = (out_dir / "staged.json").read_text()
    code, text = build(edited_export(tmp_path, TRIGGER_BODY_EDIT, name="e2.txt"), out_dir)
    assert code == bfd.EXIT_INVALID and "--overwrite" in text
    assert (out_dir / "staged.json").read_text() == before
    code, text = build(edited_export(tmp_path, TRIGGER_BODY_EDIT, name="e3.txt"), out_dir, overwrite=True)
    assert code == 0, text
    assert sorted(os.listdir(str(out_dir))) == sorted(["cleaning_trigger.json", "staged.json", keep.name])
    assert keep.read_text() == '{"rollback": true}'


# ---------------------------------------------------------------- dry-run
def test_dry_run_from_snapshot_shows_the_diff_and_writes_only_under_tmp(tmp_env, shadow_mode, tmp_path):
    out_dir = staged_dir(tmp_path, BODY_EDIT, TRIGGER_BODY_EDIT)
    staged_before = sorted(os.listdir(str(out_dir)))
    client, rec = make_client({})
    code, text = run_app(["--staged", str(out_dir), "--from-snapshot"], client=client, backup_dir=tmp_path / "b")
    assert code == 0, text
    assert rec.requests == []
    assert "-Let me know." in text and "+Let me know if that works." in text
    assert "+I do this by tracking triggers" in text
    assert "formatting-only change: trailing non-breaking spaces removed" in text
    assert "PATCH /campaigns/%s body:" % CR in text and '"sequences": [' in text
    assert "WRITES PERFORMED: 0" in text
    assert not (tmp_path / "b").exists()
    dry = tmp_env / "changeset_dryruns" / "instantly_copy"
    assert sorted(p.name for p in dry.iterdir()) == [
        "instantly_copy_%s_%s.dryrun.json" % (CR, STAMP), "instantly_copy_%s_%s.dryrun.json" % (CT, STAMP)]
    point = json.loads((dry / ("instantly_copy_%s_%s.dryrun.json" % (CR, STAMP))).read_text())
    assert point["_rollback_point"]["kind"] == "dryrun"
    assert "Let me know if that works." in json.dumps(point["_rollback_point"]["after"])
    assert sorted(os.listdir(str(out_dir))) == staged_before
    assert not job_log.job_log_path().exists()
    scratch = tmp_env / "scratch" / "instantly_copy_dryrun" / "job_log.csv"
    assert scratch.read_text().count("instantly_copy.dry_run,ok") == 2
    assert job_log.read_shadow_log() == []


def test_dry_run_against_live_is_get_only(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)
    code, text = run_app(["--staged", str(out_dir), "--no-diff"], client=client, backup_dir=tmp_path / "b",
                         dryrun_dir=tmp_path / "dry")
    assert code == 0, text
    assert rec.methods == ["GET"] and rec.requests[0].url.path == "/api/v2/campaigns/" + CR


def test_dry_run_warns_when_the_edited_variant_is_disabled_in_live(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    live = copy.deepcopy(snapshot)
    steps(live[CR])[0]["variants"][0]["v_disabled"] = True
    client, _rec = make_client(live)
    code, text = run_app(["--staged", str(out_dir), "--no-diff"], client=client, dryrun_dir=tmp_path / "dry")
    assert code == 0 and "WARNING: step1 variant 0 is switched off in Instantly (v_disabled)" in text


def test_an_api_error_on_one_campaign_does_not_stop_the_others(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT, TRIGGER_BODY_EDIT)
    client, rec = make_client(snapshot, missing=[CR])
    code, text = run_app(["--staged", str(out_dir), "--no-diff"], client=client, dryrun_dir=tmp_path / "dry")
    assert code == app.EXIT_API
    assert "API error on cleaning_reactivation" in text
    assert "cleaning_trigger" in text and "RESULT: dry-run OK" in text
    assert "cleaning_reactivation      API" in text and "cleaning_trigger           OK" in text


def test_drift_is_refused_and_shown(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    live = copy.deepcopy(snapshot)
    v = steps(live[CR])[1]["variants"][0]
    v["body"] = v["body"].replace("Worth a quick 15 minute call?", "Worth a quick 10 minute call?")
    client, rec = make_client(live)
    code, text = run_app(["--staged", str(out_dir)], client=client, backup_dir=tmp_path / "b",
                         dryrun_dir=tmp_path / "dry")
    assert code == app.EXIT_INVALID
    assert "REFUSED: live no longer matches the copy the doc was built from" in text
    assert "step2 variant 0 body: live differs from the doc baseline" in text
    assert "+Worth a quick 10 minute call?" in text
    assert rec.methods == ["GET"]
    assert not (tmp_path / "dry").exists() and not (tmp_path / "b").exists()
    scratch = tmp_env / "scratch" / "instantly_copy_dryrun" / "job_log.csv"
    assert "instantly_copy.dry_run,drift" in scratch.read_text()


def test_an_edited_field_holding_a_third_value_is_drift(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    live = copy.deepcopy(snapshot)
    steps(live[CR])[0]["variants"][0]["body"] = "<div>written in the Instantly UI</div>"
    client, _rec = make_client(live)
    code, text = run_app(["--staged", str(out_dir)], client=client, dryrun_dir=tmp_path / "dry")
    assert code == app.EXIT_INVALID and "step1 variant 0 body: live differs from the doc baseline" in text


def test_drift_in_step_count_or_delay_is_refused(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    live = copy.deepcopy(snapshot)
    steps(live[CR])[0]["delay"] = 4
    client, _rec = make_client(live)
    code, text = run_app(["--staged", str(out_dir)], client=client, dryrun_dir=tmp_path / "dry")
    assert code == app.EXIT_INVALID and "step1 delay: live 4, doc baseline 3" in text
    live = copy.deepcopy(snapshot)
    steps(live[CR]).append(copy.deepcopy(steps(live[CR])[1]))
    client, _rec = make_client(live)
    code, text = run_app(["--staged", str(out_dir)], client=client, dryrun_dir=tmp_path / "dry")
    assert code == app.EXIT_INVALID and "live has 3 steps, the doc was built from 2" in text


def test_drift_baseline_is_the_manifest_not_the_staged_file(tmp_env, shadow_mode, tmp_path, snapshot, manifest):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    staged = app.load_staged(str(out_dir))
    base = steps(staged["campaigns"]["cleaning_reactivation"]["baseline"])
    raw = dict((b["tag"], b) for b in manifest["blocks"])
    assert base[1]["variants"][0]["body"] == raw["instantly.cleaning_reactivation.step2"]["raw_html"]
    assert base[0]["variants"][0]["subject"] == raw["instantly.cleaning_reactivation.step1/subject"]["raw_subject"]
    assert set(base[0]) == {"type", "delay", "delay_unit", "variants"}


# ------------------------------------------------- staged folder verification
def _tamper_consistently(out_dir, new_line):
    """Rewrite a change's new text and value in staged.json AND the campaign
    file's sequences, so the folder is internally consistent."""
    meta_path = out_dir / "staged.json"
    meta = json.loads(meta_path.read_text())
    ch = meta["changes"][0]
    ch["new"] = ch["new"].replace("Let me know if that works.", new_line)
    ch["new_text"] = C.body_text_from_doc(ch["new"])
    ch["value"] = C.body_html_from_doc(ch["new"])
    meta_path.write_text(C.dumps(meta))
    cpath = out_dir / "cleaning_reactivation.json"
    doc = json.loads(cpath.read_text())
    doc["changes"][0]["value"] = ch["value"]
    steps(doc)[0]["variants"][0]["body"] = ch["value"]
    cpath.write_text(C.dumps(doc))


def test_a_consistently_hand_edited_staged_folder_is_refused_before_any_get(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    _tamper_consistently(out_dir, "Wire the deposit today.")
    client, rec = make_client(snapshot)
    for argv in (["--staged", str(out_dir)], apply_argv(out_dir)):
        code, text = run_app(argv, client=client, backup_dir=tmp_path / "b", dryrun_dir=tmp_path / "dry")
        assert code == app.EXIT_INVALID, text
        assert "differs from what the recorded export builds" in text
        assert "Wire the deposit" not in text
    assert rec.requests == [] and not (tmp_path / "b").exists() and not (tmp_path / "dry").exists()


def test_a_negative_index_in_a_staged_file_is_refused(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    meta = json.loads((out_dir / "staged.json").read_text())
    meta["changes"][0]["variant_index"] = -1
    (out_dir / "staged.json").write_text(C.dumps(meta))
    client, rec = make_client(snapshot)
    code, text = run_app(["--staged", str(out_dir)], client=client)
    assert code == app.EXIT_INVALID and rec.requests == []
    with pytest.raises(C.BuildError):
        C.apply_changes(snapshot[CR]["sequences"], [dict(meta["changes"][0], variant_index=-1)])
    with pytest.raises(C.BuildError):
        C.apply_changes(snapshot[CR]["sequences"], [dict(meta["changes"][0], step=0)])
    with pytest.raises(C.BuildError):
        C.apply_changes(snapshot[CR]["sequences"], [dict(meta["changes"][0], field="name")])


def test_a_moved_or_changed_export_is_refused(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    export = tmp_path / "export.txt"
    client, rec = make_client(snapshot)
    export.rename(tmp_path / "moved.txt")
    code, text = run_app(["--staged", str(out_dir)], client=client)
    assert code == app.EXIT_INVALID and "is gone (moved or deleted)" in text
    (tmp_path / "moved.txt").rename(export)
    with open(str(export), "ab") as fh:
        fh.write(b"\r\n")
    code, text = run_app(["--staged", str(out_dir)], client=client)
    assert code == app.EXIT_INVALID and "changed since the build (sha256 differs)" in text
    assert rec.requests == []


def test_a_staged_json_without_a_snapshot_is_a_clear_error(tmp_env, shadow_mode, tmp_path):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    meta = json.loads((out_dir / "staged.json").read_text())
    meta.pop("snapshot")
    (out_dir / "staged.json").write_text(C.dumps(meta))
    code, text = run_app(["--staged", str(out_dir), "--from-snapshot"])
    assert code == app.EXIT_INVALID and "staged.json records no snapshot" in text


# ------------------------------------------------------------------ apply
def test_dry_run_with_apply_and_apply_without_campaign_are_refused(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)
    for argv, why in (
            (["--staged", str(out_dir), "--dry-run", "--apply", "--campaign", "cleaning_reactivation", "--yes"], "cannot be combined"),
            (["--staged", str(out_dir), "--apply", "--yes"], "one campaign at a time"),
            (["--staged", str(out_dir), "--apply", "--campaign", "cleaning_reactivation", "--from-snapshot", "--yes"], "not live state")):
        code, text = run_app(argv, client=client, backup_dir=tmp_path / "b")
        assert code == app.EXIT_REFUSED and why in text
    assert rec.requests == [] and not (tmp_path / "b").exists()


def test_apply_without_live_mode_exits_2_and_sends_nothing(tmp_env, shadow_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)
    code, text = run_app(apply_argv(out_dir), client=client, backup_dir=tmp_path / "b")
    assert code == app.EXIT_REFUSED
    assert "REFUSED" in text and rec.requests == [] and not (tmp_path / "b").exists()
    assert "instantly_copy.apply,refused" in job_log.job_log_path().read_text()


def test_apply_with_mode_live_but_no_allow_flag_exits_2(tmp_env, monkeypatch, tmp_path, snapshot):
    monkeypatch.setenv("MODE", "live")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)
    code, _text = run_app(apply_argv(out_dir), client=client, backup_dir=tmp_path / "b")
    assert code == app.EXIT_REFUSED and rec.requests == []


def test_in_shadow_the_client_update_returns_the_shadow_record(tmp_env, shadow_mode, tmp_path, snapshot):
    """Even with main()'s gate bypassed, process_campaign refuses before any
    backup, and Instantly.update_campaign only records a would-do."""
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    staged = app.load_staged(str(out_dir))
    client, rec = make_client(snapshot)
    args = app.build_parser().parse_args(apply_argv(out_dir, yes=False) + ["--no-diff"])
    lines, out = collector()
    result = app.process_campaign(staged["campaigns"]["cleaning_reactivation"], client, args, out, NOW,
                                  str(tmp_path / "b"))
    assert result["writes"] == 0 and result["exit"] == app.EXIT_REFUSED
    assert rec.methods == ["GET"] and not (tmp_path / "b").exists()
    shadow = client.update_campaign(CR, {"sequences": staged["campaigns"]["cleaning_reactivation"]["target"]})
    assert shadow["shadow"] is True and shadow["action"] == "update_campaign"
    assert rec.methods == ["GET"]
    assert job_log.read_shadow_log()[0]["action"] == "update_campaign"


def test_live_apply_backs_up_first_patches_once_and_keeps_live_only_keys(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    live = copy.deepcopy(snapshot)
    for st in steps(live[CR]):
        st["some_live_only_step_key"] = 7
        for v in st["variants"]:
            v["v_disabled"] = False
    original = copy.deepcopy(live[CR])
    bdir = tmp_path / "b"
    seen_at_patch = []

    def on_patch(request):
        seen_at_patch.append(sorted(os.listdir(str(bdir))) if bdir.exists() else [])

    client, rec = make_client(live, on_patch=on_patch)
    code, text = run_app(apply_argv(out_dir), client=client, backup_dir=bdir)
    assert code == 0, text
    assert rec.methods == ["GET", "GET", "PATCH"]
    assert seen_at_patch == [["instantly_copy_%s_%s.preapply.json" % (CR, STAMP)]]
    body = json.loads(rec.requests[2].content)
    assert rec.requests[2].url.path == "/api/v2/campaigns/" + CR
    assert list(body) == ["sequences"]
    sent = steps(body["sequences"])
    assert all(st["some_live_only_step_key"] == 7 and st["variants"][0]["v_disabled"] is False for st in sent)
    assert sent[1] == steps(original)[1]
    changed0 = copy.deepcopy(sent[0])
    assert "Let me know if that works." in changed0["variants"][0]["body"]
    changed0["variants"][0]["body"] = steps(original)[0]["variants"][0]["body"]
    assert changed0 == steps(original)[0]
    assert sorted(os.listdir(str(bdir))) == ["instantly_copy_%s_%s.json" % (CR, STAMP)]
    point = json.loads((bdir / ("instantly_copy_%s_%s.json" % (CR, STAMP))).read_text())
    meta = point["_rollback_point"]
    assert (meta["kind"], meta["script"], meta["fields"], meta["outcome"]) == \
        ("apply", "instantly_copy", ["sequences"], "landed_verified")
    assert point["sequences"] == original["sequences"]
    assert "instantly_copy.apply,applied" in job_log.job_log_path().read_text()

    code, text = run_app(apply_argv(out_dir), client=client, backup_dir=bdir)
    assert code == 0, text
    assert rec.methods == ["GET", "GET", "PATCH", "GET"]
    assert "PATCH skipped, no backup written" in text
    assert sorted(os.listdir(str(bdir))) == ["instantly_copy_%s_%s.json" % (CR, STAMP)]


def test_apply_shows_the_diff_before_the_prompt_and_rereads_after_it(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)
    lines, out = collector()
    at_prompt = {}

    def confirm(prompt):
        at_prompt["methods"] = list(rec.methods)
        at_prompt["diff_shown"] = any("+Let me know if that works." in l for l in lines)
        return "cleaning_reactivation"

    code = app.main(apply_argv(out_dir, yes=False), client=client, now=NOW, out=out,
                    backup_dir=str(tmp_path / "b"), confirm=confirm)
    assert code == 0, "\n".join(lines)
    assert at_prompt == {"methods": ["GET"], "diff_shown": True}
    assert rec.methods == ["GET", "GET", "PATCH"]


def test_live_moving_while_the_prompt_is_open_is_refused(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)

    def confirm(prompt):
        steps(rec.campaigns[CR])[1]["variants"][0]["body"] += "<div>P.S.</div>"
        return "cleaning_reactivation"

    code, text = run_app(apply_argv(out_dir, yes=False), client=client, backup_dir=tmp_path / "b", confirm=confirm)
    assert code == app.EXIT_REFUSED and "changed while the confirmation was open" in text
    assert rec.methods == ["GET", "GET"] and not (tmp_path / "b").exists()


def test_typed_confirmation_mismatch_aborts(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)
    code, _ = run_app(apply_argv(out_dir, yes=False), client=client, backup_dir=tmp_path / "b",
                      confirm=lambda prompt: "nope")
    assert code == app.EXIT_REFUSED and rec.methods == ["GET"] and not (tmp_path / "b").exists()


def test_live_apply_refuses_drift_on_the_fresh_get(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    live = copy.deepcopy(snapshot)
    steps(live[CR])[0]["variants"][0]["subject"] = "{{firstName}}, edited in Instantly"
    client, rec = make_client(live)
    code, text = run_app(apply_argv(out_dir), client=client, backup_dir=tmp_path / "b")
    assert code == app.EXIT_INVALID and "step1 variant 0 subject" in text
    assert rec.methods == ["GET"] and not (tmp_path / "b").exists()


def test_a_failed_backup_write_sends_no_patch(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    not_a_dir = tmp_path / "file"
    not_a_dir.write_text("x")
    client, rec = make_client(snapshot)
    code, text = run_app(apply_argv(out_dir), client=client, backup_dir=not_a_dir / "b")
    assert code == app.EXIT_REFUSED and "before-image could not be written" in text
    assert "PATCH" not in rec.methods


def test_a_patch_error_exits_3_and_leaves_a_restorable_point(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot, patch_status=500)
    bdir = tmp_path / "b"
    code, text = run_app(apply_argv(out_dir), client=client, backup_dir=bdir)
    assert code == app.EXIT_API, text
    assert rec.methods.count("PATCH") == 1
    name = "instantly_copy_%s_%s.json" % (CR, STAMP)
    assert sorted(os.listdir(str(bdir))) == [name]
    point, meta, restore_patch = R.load_point(str(bdir / name), "instantly_copy", CR)
    assert meta["outcome"] == "unchanged_at_reread" and restore_patch == {"sequences": snapshot[CR]["sequences"]}


def test_restore_puts_the_old_copy_back(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    client, rec = make_client(snapshot)
    bdir = tmp_path / "b"
    assert run_app(apply_argv(out_dir), client=client, backup_dir=bdir)[0] == 0
    point = bdir / ("instantly_copy_%s_%s.json" % (CR, STAMP))
    code, text = run_app(["--apply", "--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                         client=client, backup_dir=bdir)
    assert code == 0, text
    assert rec.campaigns[CR]["sequences"] == snapshot[CR]["sequences"]
    assert json.loads(rec.requests[-1].content) == {"sequences": snapshot[CR]["sequences"]}


def test_restore_refuses_a_phase0_point_and_another_campaigns_point(tmp_env, live_mode, tmp_path, snapshot):
    bdir = tmp_path / "b"
    phase0 = R.write_point(str(bdir), "phase0_%s_%s" % (CR, STAMP), R.build_point(
        "phase0", R.KIND_APPLY, snapshot[CR], ["sequences"], NOW, CR, "cleaning_reactivation",
        after={"sequences": snapshot[CR]["sequences"]}))
    other = R.write_point(str(bdir), "instantly_copy_%s_%s" % (CT, STAMP), R.build_point(
        "instantly_copy", R.KIND_APPLY, snapshot[CT], ["sequences"], NOW, CT, "cleaning_trigger",
        after={"sequences": snapshot[CT]["sequences"]}))
    client, rec = make_client(snapshot)
    code, text = run_app(["--apply", "--restore", phase0, "--campaign", "cleaning_reactivation", "--yes"],
                         client=client, backup_dir=bdir)
    assert code == app.EXIT_INVALID and "was written by 'phase0'" in text
    code, text = run_app(["--apply", "--restore", other, "--campaign", "cleaning_reactivation", "--yes"],
                         client=client, backup_dir=bdir)
    assert code == app.EXIT_INVALID and "would overwrite a different campaign" in text
    assert rec.requests == []


# ------------------------------------------------------------ round 3 extras
def test_build_warnings_reach_the_dry_run_and_the_apply_prompt(tmp_env, live_mode, tmp_path, snapshot):
    out_dir = staged_dir(tmp_path, ("Let me know.\r\n", "Let me know, it\u2019s fine, {{ firstName }}.\r\n"))
    client, rec = make_client(snapshot)
    code, text = run_app(["--staged", str(out_dir), "--from-snapshot", "--no-diff"], dryrun_dir=tmp_path / "dry")
    assert code == 0, text
    assert "WARNING (from the build): curly quotes typed in the new text" in text
    assert "WARNING (from the build): {{ firstName }} has spaces inside the braces" in text
    lines, out = collector()
    seen = {}

    def confirm(prompt):
        seen["warned"] = any("WARNING (from the build): curly quotes" in l for l in lines)
        return "nope"

    app.main(apply_argv(out_dir, yes=False), client=client, now=NOW, out=out, backup_dir=str(tmp_path / "b"),
             confirm=confirm)
    assert seen == {"warned": True}


def test_a_propagated_edit_is_announced_in_the_dry_run(tmp_env, shadow_mode, tmp_path):
    out_dir = staged_dir(tmp_path, SUBJECT_EDIT)
    code, text = run_app(["--staged", str(out_dir), "--from-snapshot", "--no-diff"], dryrun_dir=tmp_path / "dry")
    assert code == 0, text
    assert text.count("NOT EDITED IN THIS CAMPAIGN'S BLOCK") == 5
    assert ("comes from the edit to instantly.cleaning_trigger.step1/subject (campaign cleaning_trigger)" in text)
    assert "recruiting_outbound's leads will get: '{{firstName}}, quick question'" in text


def test_a_block_receiving_a_propagated_edit_is_not_listed_as_dropped(tmp_env, tmp_path):
    spaces = ("Subject: {{firstName}}, question (tag: instantly.bookkeeping_trigger.step1/subject)",
              "Subject: {{firstName}},  question (tag: instantly.bookkeeping_trigger.step1/subject)")
    code, text = build(edited_export(tmp_path, SUBJECT_EDIT, spaces), tmp_path / "staged")
    assert code == 0, text
    assert "whitespace/quote-only" not in text
    doc = json.loads((tmp_path / "staged" / "bookkeeping_trigger.json").read_text())
    assert steps(doc)[0]["variants"][0]["subject"] == "{{firstName}}, quick question"


def test_one_variable_in_two_spin_options_is_reported_once(tmp_env, tmp_path):
    code, text = build(edited_export(tmp_path, ("Let me know.\r\n", "{{RANDOM | Hey {{firstName}} | Hi {{firstName}}}}\r\n")),
                       tmp_path / "staged")
    assert code == bfd.EXIT_INVALID
    assert text.count("merge variable inside a spin option") == 1


def test_format_notes_tell_a_plain_trailing_space_from_a_non_breaking_one():
    assert C.format_notes("<div>a </div>", "a") == ["formatting-only change: trailing spaces removed"]
    assert C.format_notes(u"<div>a\u00a0</div>", "a") == ["formatting-only change: trailing non-breaking spaces removed"]


def test_non_string_file_names_in_staged_json_are_a_clean_refusal(tmp_env, shadow_mode, tmp_path):
    out_dir = staged_dir(tmp_path, BODY_EDIT)
    meta = json.loads((out_dir / "staged.json").read_text())
    meta["campaigns"]["cleaning_reactivation"] = 5
    (out_dir / "staged.json").write_text(C.dumps(meta))
    code, text = run_app(["--staged", str(out_dir), "--from-snapshot"])
    assert code == app.EXIT_INVALID and "must map campaign keys to <key>.json file names" in text
