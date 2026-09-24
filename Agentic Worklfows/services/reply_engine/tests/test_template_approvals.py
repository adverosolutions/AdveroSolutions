"""CT1: template approval registry, catalogue and CLI. No network, no LLM, no live flags.

Every test points the registry at a tmp_path file; the real
config/approved_templates.json is checked unchanged after each test.
"""
import importlib
import json
import os
import shutil
from datetime import datetime

import pytest

from shared import slots
from shared.paths import BASE_DIR

from services.reply_engine import cadence, draft, models, show_rate
from services.reply_engine import template_approvals as ta
from jobs import approve_templates as cli

REAL_FILE = BASE_DIR / "config" / "approved_templates.json"


@pytest.fixture(autouse=True)
def approvals_file(tmp_path, monkeypatch):
    before = REAL_FILE.read_bytes() if REAL_FILE.exists() else None
    path = tmp_path / "approved_templates.json"
    monkeypatch.setattr(ta, "APPROVALS_PATH", path)
    monkeypatch.delenv(ta.KILL_SWITCH_ENV, raising=False)
    # Any Job_Log row a CLI test forgets to capture lands in tmp, never in .tmp/.
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.delenv("JOB_LOG_SHEET_ID", raising=False)
    ta.clear_cache()
    yield path
    ta.clear_cache()
    after = REAL_FILE.read_bytes() if REAL_FILE.exists() else None
    assert before == after, "a test wrote the real config/approved_templates.json"


def _tty_yes():
    return True


def _tty_no():
    return False


def _confirm_ok(word, prompt):
    return word == "APPROVE"


def _confirm_never(word, prompt):
    raise AssertionError("confirm must not be asked")


def _index():
    return ta.catalogue_index()


class _Log(object):
    def __init__(self):
        self.rows = []

    def __call__(self, job, status, details=None):
        self.rows.append((job, status, details or {}))
        return {"job": job, "status": status}


@pytest.fixture
def log():
    return _Log()


# ------------------------------------------------------------ catalogue
def test_every_cadence_prompt_file_has_an_entry():
    files = sorted(p.stem[len("cadence_"):] for p in cadence.PROMPTS_DIR.glob("cadence_e*.md"))
    assert files, "no cadence prompt files found"
    idx = _index()
    for name in files:
        e = idx.get("cadence.%s" % name)
        assert e is not None, "cadence_%s.md has no catalogue entry" % name
        assert e["kind"] == "cadence" and e["approvable"] and e["extractable"]
        assert e["source"].endswith("prompts/cadence_%s.md" % name)
        assert e["text"] == cadence._load_template(name)
    for n in range(1, 11):
        assert "cadence.e%d" % n in idx
    # the old ladder's ids are gone
    for gone in ("d1", "d2", "d3", "d4", "d5", "d6", "d6_noinvite", "d7", "d14", "d30"):
        assert "cadence.%s" % gone not in idx


def test_cadence_variables_are_marked():
    idx = _index()
    # the subject variant adds {original_subject} to every cadence id
    assert idx["cadence.e1"]["variables"] == ["first_name", "slots", "original_subject"]
    # E2 offers no times
    assert set(idx["cadence.e2"]["variables"]) == {"first_name", "research_line", "company", "original_subject"}
    assert set(idx["cadence.e4"]["variables"]) == {"first_name", "company", "offer_proof", "slots", "original_subject"}
    assert set(idx["cadence.e5"]["variables"]) == {"first_name", "offer_line", "slots", "original_subject", "company"}
    assert set(idx["cadence.e6"]["variables"]) == {"first_name", "preview", "slots", "original_subject"}
    assert idx["cadence.e7"]["variables"] == ["first_name", "slots", "original_subject"]
    assert set(idx["cadence.e9"]["variables"]) == {"first_name", "observation", "slots", "original_subject"}
    for n in range(1, 11):
        assert "booking_url" not in idx["cadence.e%d" % n]["variables"]


def test_every_question_type_branch_has_an_entry_per_offer():
    idx = _index()
    branches = list(models.QUESTION_TYPES) + ["referral", "default"]
    assert set(branches) == set(ta.FIRST_REPLY_BRANCHES)
    assert len(draft.PRICING) == 6
    for offer in draft.PRICING:
        assert idx["first_reply.%s.greeting" % offer]["kind"] == "first_reply_piece"
        assert idx["first_reply.%s.slots" % offer]["kind"] == "first_reply_piece"
        for branch in branches:
            full = idx["first_reply.%s.%s.full" % (offer, branch)]
            assert full["kind"] == "first_reply" and full["approvable"] and full["extractable"]
            piece = idx["first_reply.%s.answer.%s" % (offer, branch)]
            assert not piece["approvable"]


def test_full_first_reply_is_greeting_answer_slots_signature():
    idx = _index()
    for offer in draft.PRICING:
        for branch in ("pricing", "send_info", "mechanism", "other", "default"):
            full = idx["first_reply.%s.%s.full" % (offer, branch)]["text"]
            parts = [idx["first_reply.%s.greeting" % offer]["text"],
                     idx["first_reply.%s.answer.%s" % (offer, branch)]["text"],
                     idx["first_reply.%s.slots" % offer]["text"], "Lorenzo"]
            assert full == "\n\n".join(parts)


def test_first_reply_template_matches_a_real_render():
    """Filling the placeholders gives exactly what build_draft produces for a real lead."""
    tz = slots.TZ
    now = tz.localize(datetime(2030, 1, 7, 9, 0))
    ev = models.ReplyEvent(email_id="e1", lead_email="marisol@brightwater-janitorial.test",
                           campaign_key="bookkeeping_reactivation", first_name="Marisol",
                           company="Brightwater Ledger Co", received_at=now)
    cls = models.Classification(label="positive_question", extracted=models.Extracted(question_type="send_info"))
    d = draft.build_draft(ev, cls, now=now, booking_link="https://book.example.test/x", use_llm=False,
                          already_offered=[], busy_blocks=[])
    two = [slots.parse_iso(s) for s in d.offered_slots]
    tpl = _index()["first_reply.bookkeeping_reactivation.send_info.full"]["text"]
    filled = ta.fill(tpl, first_name="Marisol", company="Brightwater Ledger Co", slots=slots.format_slots(two),
                     booking_url="https://book.example.test/x")
    assert filled == d.body_text


def test_cadence_and_show_rate_templates_match_real_renders():
    tpl = _index()["cadence.e3"]["text"]
    real = cadence.render("e3", first_name="Oswin", slots="Tue 2:00pm or Wed 3:00pm CT")
    assert ta.fill(tpl, first_name="Oswin", slots="Tue 2:00pm or Wed 3:00pm CT") == real

    start = slots.TZ.localize(datetime(2030, 2, 5, 15, 0))
    appt = {"first_name": "Tamsin", "company": "Kettleby Staffing", "niche": "recruiting", "offer": "outbound",
            "zoom_link": "https://zoom.example.test/j/1", "booking_url": "https://book.example.test/z"}
    copy = show_rate.render("reminder_24h_email", appt, start, start)
    tpl = _index()["show_rate.reminder_24h_email"]["text"]
    filled = ta.fill(tpl, first_name="Tamsin", company="Kettleby Staffing", when_ct=show_rate.fmt_when(start),
                     time_ct=show_rate.fmt_time_only(start), zoom_link="https://zoom.example.test/j/1")
    assert filled == "Subject: %s\n\n%s" % (copy["subject"], copy["body"])


def test_catalogue_covers_booking_show_rate_and_no_show():
    idx = _index()
    kinds = set(e["kind"] for e in idx.values())
    assert {"first_reply", "cadence", "booking", "show_rate", "no_show"} <= kinds
    assert "booking.confirmation.zoom_link" in idx and "booking.confirmation.no_zoom_link" in idx
    for key in ta.SHOW_RATE_LEAD_FACING:
        assert any(i == "show_rate.%s" % key or i.startswith("show_rate.%s." % key) for i in idx), key
    for key in ta.NO_SHOW_LEAD_FACING:
        assert any(i == "no_show.%s" % key or i.startswith("no_show.%s." % key) for i in idx), key
    # Lorenzo-facing tasks are not prospect templates.
    assert not any("unconfirmed_task" in i or "ns_call_task" in i for i in idx)


def test_no_sentinel_or_unexpected_unextractable_entry():
    for e in ta.catalogue():
        assert "zqx" not in e["review_text"].lower(), e["id"]
        assert "leadconnectorhq" not in e["review_text"], e["id"]
        if not e["extractable"]:
            assert e["id"] == "cadence.e2.research_line", e["id"]
            assert e["explanation"]
            assert not e["approvable"]
        else:
            assert e["text"].strip(), e["id"]
            assert e["sha256"] == ta.text_hash(e["review_text"])
            assert e["review_text"].startswith(e["text"].rstrip("\n"))


def test_catalogue_does_not_change_when_imported_twice():
    env_before = dict(os.environ)
    first = ta.catalogue()
    importlib.reload(ta)
    second = ta.catalogue()
    third = ta.catalogue()
    assert first == second == third
    assert dict(os.environ) == env_before


# --------------------------------------------------------------- hashes
def test_hash_is_stable_and_whitespace_normalised():
    a = "Hey {first_name},\n\nLine one.\n\nLorenzo\n"
    assert ta.text_hash(a) == ta.text_hash(a)
    assert ta.text_hash(a) == ta.text_hash("Hey {first_name},  \r\n\r\n\r\nLine one.\n\nLorenzo")
    assert ta.text_hash(a) != ta.text_hash(a.replace("one", "two"))
    assert len(ta.text_hash(a)) == 64


def test_edited_first_reply_text_shows_changed(monkeypatch, approvals_file):
    tid = "first_reply.cleaning_reactivation.pricing.full"
    assert ta.status(tid) == ta.STATUS_UNAPPROVED
    ta.approve([tid], approved_by="Wendeline Okafor")
    assert ta.status(tid) == ta.STATUS_APPROVED
    assert ta.is_approved(tid)
    monkeypatch.setitem(draft.PRICING, "cleaning_reactivation", draft.PRICING["cleaning_reactivation"] + " Plus more.")
    ta.clear_cache()  # an in-memory edit does not touch any file mtime
    assert ta.status(tid) == ta.STATUS_CHANGED
    assert not ta.is_approved(tid)
    # A different offer's template is untouched by the edit.
    other = "first_reply.bookkeeping_reactivation.pricing.full"
    ta.approve([other], approved_by="Wendeline Okafor")
    assert ta.status(other) == ta.STATUS_APPROVED


def test_edited_cadence_prompt_shows_changed(monkeypatch, tmp_path, approvals_file):
    ta.approve(["cadence.e1"], approved_by="Wendeline Okafor")
    assert ta.status("cadence.e1") == ta.STATUS_APPROVED
    copy_dir = tmp_path / "prompts"
    shutil.copytree(str(cadence.PROMPTS_DIR), str(copy_dir))
    p = copy_dir / "cadence_e1.md"
    p.write_text(p.read_text(encoding="utf-8").replace("2 more", "two more"), encoding="utf-8")
    monkeypatch.setattr(cadence, "PROMPTS_DIR", copy_dir)
    assert ta.status("cadence.e1") == ta.STATUS_CHANGED
    assert ta.status("cadence.e3") == ta.STATUS_UNAPPROVED


def test_status_unknown_and_unapproved():
    assert ta.status("no.such.template") == ta.STATUS_UNKNOWN
    assert not ta.is_approved("no.such.template")
    assert ta.status("cadence.e7") == ta.STATUS_UNAPPROVED


def test_reference_pieces_and_unextractable_cannot_be_approved():
    with pytest.raises(ta.ApprovalError):
        ta.approve(["first_reply.cleaning_reactivation.greeting"], approved_by="Wendeline Okafor")
    with pytest.raises(ta.ApprovalError):
        ta.approve(["cadence.e2.research_line"], approved_by="Wendeline Okafor")
    with pytest.raises(ta.ApprovalError):
        ta.approve(["no.such.template"], approved_by="Wendeline Okafor")


def test_corrupt_file_fails_closed(approvals_file):
    approvals_file.write_text("{not json", encoding="utf-8")
    assert not ta.is_approved("cadence.e1")
    assert ta.kill_switch_on()
    with pytest.raises(ValueError):
        ta.load_approvals()


# ------------------------------------------------------ approve / revoke
def test_approve_and_revoke_round_trip(approvals_file):
    assert ta.load_approvals() == {"version": 1, "approvals": {}}
    ta.approve(["cadence.e1", "booking.confirmation.zoom_link"], approved_by="Wendeline Okafor",
               now=datetime(2030, 1, 7, 15, 0))
    data = json.loads(approvals_file.read_text(encoding="utf-8"))
    rec = data["approvals"]["cadence.e1"]
    assert set(rec) == {"sha256", "approved_at", "approved_by", "text_preview"}
    assert rec["approved_by"] == "Wendeline Okafor"
    assert rec["sha256"] == _index()["cadence.e1"]["sha256"]
    assert rec["approved_at"].startswith("2030-01-07T15:00")
    assert rec["text_preview"].startswith("Hey {first_name},")
    assert ta.is_approved("cadence.e1") and ta.is_approved("booking.confirmation.zoom_link")
    ta.revoke(["cadence.e1"])
    assert ta.status("cadence.e1") == ta.STATUS_UNAPPROVED
    assert ta.is_approved("booking.confirmation.zoom_link")
    with pytest.raises(ta.ApprovalError):
        ta.revoke(["cadence.e1"])
    leftovers = [p.name for p in approvals_file.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_cli_approve_and_revoke_round_trip(approvals_file, capsys, log):
    rc = cli.main(["--approve", "cadence.e3", "--by", "Wendeline Okafor"], confirm=_confirm_ok, isatty=_tty_yes,
                  log_fn=log)
    assert rc == 0
    out = capsys.readouterr().out
    assert "approved: cadence.e3" in out and ta.WIRED_NOTE in out
    assert ta.WIRED_NOTE == ("Approved templates send automatically (CT3). Revoke or set the kill switch to "
                             "stop them.")
    assert ta.NOT_YET_WIRED_NOTE == ta.WIRED_NOTE  # the CT1 name still imports
    assert cli.AUTO_SEND_WARNING in out  # the interactive approve path warns
    assert "once CT3 phase 2 is deployed" in cli.AUTO_SEND_WARNING  # it does not claim auto-send is live today
    assert ta.status("cadence.e3") == ta.STATUS_APPROVED
    rc = cli.main(["--revoke", "cadence.e3", "--yes"], confirm=_confirm_never, isatty=_tty_yes, log_fn=log)
    assert rc == 0
    assert "revoked: cadence.e3" in capsys.readouterr().out
    assert ta.status("cadence.e3") == ta.STATUS_UNAPPROVED
    h = _index()["cadence.e3"]["sha256"]
    assert [(j, st) for j, st, _ in log.rows] == [("approve_templates", "ok"), ("approve_templates", "ok")]
    assert log.rows[0][2]["approved"] == {"cadence.e3": h}
    assert log.rows[0][2]["approved_by"] == "Wendeline Okafor"
    assert log.rows[1][2]["revoked"] == {"cadence.e3": h}
    # ids and hashes only, never the template text
    flat = json.dumps([d for _, _, d in log.rows])
    assert "A couple more options" not in flat and "Hey " not in flat


def test_cli_list_show_export(approvals_file, tmp_path, capsys):
    assert cli.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "cadence.e1" in out and "unapproved" in out
    assert cli.main(["--show", "cadence.e7"]) == 0
    assert "Should I keep trying to find a time" in capsys.readouterr().out
    assert cli.main(["--show", "no.such.template"]) == 1
    out_md = tmp_path / "review.md"
    assert cli.main(["--export", str(out_md)]) == 0
    assert out_md.exists()


# ------------------------------------------------------------- TTY gate
def test_yes_is_refused_without_a_tty(approvals_file, capsys, log):
    rc = cli.main(["--approve", "cadence.e1", "--yes"], confirm=_confirm_never, isatty=_tty_no, log_fn=log)
    assert rc == 1
    assert "--yes is only accepted from an interactive terminal" in capsys.readouterr().out
    assert not approvals_file.exists()
    assert [st for _, st, _ in log.rows] == ["refused"]


def test_no_tty_without_yes_is_refused(approvals_file, capsys, log):
    rc = cli.main(["--approve", "cadence.e1"], confirm=_confirm_never, isatty=_tty_no, log_fn=log)
    assert rc == 1
    assert not approvals_file.exists()
    assert cli.AUTO_SEND_WARNING not in capsys.readouterr().out  # the warning is for the TTY path only
    ta.approve(["cadence.e1"], approved_by="Wendeline Okafor")
    before = approvals_file.read_bytes()
    assert cli.main(["--revoke", "cadence.e1", "--yes"], confirm=_confirm_never, isatty=_tty_no, log_fn=log) == 1
    assert approvals_file.read_bytes() == before


def test_wrong_confirm_word_writes_nothing(approvals_file, log):
    rc = cli.main(["--approve", "cadence.e1"], confirm=lambda w, p: False, isatty=_tty_yes, log_fn=log)
    assert rc == 1
    assert not approvals_file.exists()


# --------------------------------------------------- approve-all-shown
def test_approve_all_shown_approves_exactly_the_export(approvals_file, tmp_path, log):
    md_path = tmp_path / "review.md"
    md_path.write_text(ta.render_catalogue_markdown(), encoding="utf-8")
    shown = ta.parse_exported(md_path.read_text(encoding="utf-8"))
    approvable = [e["id"] for e in ta.catalogue() if e["approvable"]]
    assert sorted(shown) == sorted(approvable)
    rc = cli.main(["--approve-all-shown", str(md_path), "--yes"], confirm=_confirm_never, isatty=_tty_yes,
                  log_fn=log)
    assert rc == 0
    data = ta.load_approvals()
    assert sorted(data["approvals"]) == sorted(shown)
    for tid, h in shown.items():
        assert data["approvals"][tid]["sha256"] == h
        assert ta.is_approved(tid)
    assert not ta.is_approved("first_reply.cleaning_reactivation.greeting")
    assert log.rows[-1][1] == "ok" and log.rows[-1][2]["approved"] == shown


def test_approve_all_shown_refuses_when_a_template_changed(approvals_file, tmp_path, monkeypatch, capsys, log):
    md_path = tmp_path / "review.md"
    md_path.write_text(ta.render_catalogue_markdown(), encoding="utf-8")
    monkeypatch.setitem(draft.MECHANISM, "recruiting_outbound", draft.MECHANISM["recruiting_outbound"] + " Also more.")
    ta.clear_cache()
    rc = cli.main(["--approve-all-shown", str(md_path), "--yes"], confirm=_confirm_never, isatty=_tty_yes,
                  log_fn=log)
    assert rc == 1
    out = capsys.readouterr().out
    assert "changed since the review file was exported" in out
    assert "first_reply.recruiting_outbound.mechanism.full" in out
    assert "first_reply.recruiting_outbound.send_info.full" in out
    assert "- first_reply.cleaning_reactivation.pricing.full" not in out
    assert not approvals_file.exists()
    assert [st for _, st, _ in log.rows] == ["refused"]


def test_approve_all_shown_refuses_a_hand_edited_hash(approvals_file, tmp_path, capsys, log):
    md = ta.render_catalogue_markdown()
    h = ta.catalogue_index()["cadence.e1"]["sha256"]
    md_path = tmp_path / "review.md"
    md_path.write_text(md.replace(h, "0" * 64), encoding="utf-8")
    assert cli.main(["--approve-all-shown", str(md_path), "--yes"], isatty=_tty_yes, log_fn=log) == 1
    out = capsys.readouterr().out
    assert "cadence.e1: the text shown does not match its marker hash" in out
    assert not approvals_file.exists()
    assert [st for _, st, _ in log.rows] == ["refused"]


# ------------------------------------------------------------ kill switch
def test_kill_switch(approvals_file, monkeypatch):
    assert not ta.kill_switch_on()
    # any value that is set and is not an explicit enable is the kill switch
    for value in ("0", "off", "OFF", " off ", "false", "no", "", "disable", "maybe", "2", "enabled"):
        monkeypatch.setenv(ta.KILL_SWITCH_ENV, value)
        assert ta.kill_switch_on(), repr(value)
    for value in ("1", "on", "ON", "true", "True", "yes", " yes "):
        monkeypatch.setenv(ta.KILL_SWITCH_ENV, value)
        assert not ta.kill_switch_on(), repr(value)
    monkeypatch.delenv(ta.KILL_SWITCH_ENV)
    # "auto_send" is kill unless absent or the JSON literal true
    for value in (False, "false", "true", 0, 1, None, "yes", [], {}):
        ta.save_approvals({"version": 1, "approvals": {}, "auto_send": value})
        assert ta.kill_switch_on(), repr(value)
    ta.save_approvals({"version": 1, "approvals": {}, "auto_send": True})
    assert not ta.kill_switch_on()
    ta.save_approvals({"version": 1, "approvals": {}})
    assert not ta.kill_switch_on()
    # the env enable value does not override a file kill
    monkeypatch.setenv(ta.KILL_SWITCH_ENV, "1")
    ta.save_approvals({"version": 1, "approvals": {}, "auto_send": False})
    assert ta.kill_switch_on()


def test_auto_send_allowed_honours_kill_switch(approvals_file, monkeypatch):
    ta.approve(["cadence.e1"], approved_by="Wendeline Okafor")
    assert ta.auto_send_allowed("cadence.e1")
    monkeypatch.setenv(ta.KILL_SWITCH_ENV, "off")
    assert ta.is_approved("cadence.e1")
    assert not ta.auto_send_allowed("cadence.e1")


# --------------------------------------------------------------- markdown
def test_markdown_contains_every_id_and_the_header():
    entries = ta.catalogue()
    md = ta.render_catalogue_markdown(entries)
    for e in entries:
        assert "`%s`" % e["id"] in md, e["id"]
    assert "sends automatically" in md
    assert "safety checks stay on" in md
    for kind in set(e["kind"] for e in entries):
        assert "- %s: " % kind in md
    assert "—" not in md and "–" not in md


def test_real_config_file_is_the_empty_registry():
    data = json.loads(REAL_FILE.read_text(encoding="utf-8"))
    assert data["version"] == 1 and isinstance(data["approvals"], dict)
    assert ta.APPROVALS_PATH != REAL_FILE  # the fixture redirected it


# ================================================================ round 2
# Defect 1: every literal a body can carry under an approved id feeds its hash.
# Each case edits ONE literal in a copy of the source module (as the review
# probes did), swaps the copy's functions in, and expects the id to flip.
import importlib.util  # noqa: E402
import inspect  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402

from services.reply_engine import booking  # noqa: E402


def _edited_copy(module, old, new, tmp_path, monkeypatch):
    """What a file edit does, in-process: load an edited copy of the module and
    put its functions in place of the originals, including where another module
    imported them by name (no_show does "from show_rate import fmt_when")."""
    src = open(module.__file__, encoding="utf-8").read()
    assert old in src, "literal %r not found in %s" % (old, module.__file__)
    path = tmp_path / ("edited_%s.py" % module.__name__.rsplit(".", 1)[-1])
    path.write_text(src.replace(old, new), encoding="utf-8")
    name = "ct1_edited_%s_%d" % (module.__name__.rsplit(".", 1)[-1], abs(hash((old, new))))
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(module, "PROMPTS_DIR"):
        mod.PROMPTS_DIR = module.PROMPTS_DIR
    swapped = {}
    for attr, val in list(vars(module).items()):
        if inspect.isfunction(val) and val.__module__ == module.__name__ and inspect.isfunction(getattr(mod, attr, None)):
            swapped[id(val)] = getattr(mod, attr)
            monkeypatch.setattr(module, attr, getattr(mod, attr))
    for other_name, other in list(sys.modules.items()):
        if other is None or other is module or not other_name.startswith(("services.", "shared.")):
            continue
        for attr, val in list(vars(other).items()):
            if inspect.isfunction(val) and id(val) in swapped:
                monkeypatch.setattr(other, attr, swapped[id(val)])
    ta.clear_cache()


# The time and slot formatters (round 3). The value_formats block is the same
# on every id that carries a time or slot placeholder, so an edit to any
# formatter must flip ALL of them. That is a superset of the ids carrying the
# placeholder each formatter fills (67, 72 and 5 ids in the round 2 probes,
# which flipped 0, 9 and 1 of them).
FORMATTER_EDITS = [
    ("slots", '"%s or %s %s"', '"%s and %s %s"', "cadence.e1", ta.TIME_PLACEHOLDERS),
    ("slots", 'return "CT"', 'return "Central"', "booking.already_booked.invite_on_calendar", ta.TIME_PLACEHOLDERS),
    ("show_rate", '"%s CT" % _clock(ct)', '"%s Central" % _clock(ct)', "show_rate.reminder_1h_email",
     ta.TIME_PLACEHOLDERS),
    # ZA item 5: the lead's proposed time in their own zone (slots.format_asked_time)
    ("slots", 'return "%s %s" % (text, _tz_label(local, tz))', 'return "%s (%s)" % (text, _tz_label(local, tz))',
     "booking.counter.weekend", ta.TIME_PLACEHOLDERS),
    # ZC item 8: am/pm on every show-rate and no-show time is part of every hash
    ("show_rate", '"am" if dt.hour < 12 else "pm"', '"" if dt.hour < 12 else ""', "no_show.ns_reschedule_email",
     ta.TIME_PLACEHOLDERS),
]

# (module, literal in the source, replacement, an id whose hash must flip,
#  placeholders: every approvable id carrying any of them must flip as well)
FALLBACK_EDITS = [
    ("show_rate", "60-second walkthrough", "90-second walkthrough", "show_rate.confirm_email.cleaning_reactivation",
     ()),
    ("show_rate", "The call link is on the calendar invite from when we booked.",
     "The call link is on the invite from when we booked.", "show_rate.reminder_1h_email", ()),
    ("show_rate", '"The link is on your calendar invite."', '"The link is in your calendar invite."',
     "show_rate.reminder_24h_email", ()),
    ("show_rate", '"The link\'s on your calendar invite."', '"The link is on your invite."',
     "show_rate.reminder_morning_email", ()),
    ("show_rate", '"there"', '"friend"', "show_rate.reminder_1h_email", ()),
    ("show_rate", '"The calendar invite is on its way with the call link."', '"The calendar invite is on its way."',
     "show_rate.confirm_email.cleaning_reactivation", ()),
    ("no_show", "I'm on the call now, no rush. The link is on your calendar invite.",
     "I'm on the call now. The link is in the invite.", "no_show.ns_still_on_email", ()),
    ("no_show", "Today didn't line up, and no problem if now is a bad time.",
     "Today didn't work out, and no problem if now is a bad time.", "no_show.ns_reschedule_email.repeat", ()),
    ("booking", "your time)", "your local time)", "booking.confirmation.zoom_link", ()),
    ("booking", "Could you send me a couple of times that work for you next week?",
     "Could you send me a few times that work for you next week?", "booking.counter.weekend", ()),
    ("booking", '"That time does not work on my side"', '"That day does not work on my side"',
     "booking.counter.weekend", ()),
    ("booking", '"%s %s %d %s" % (local.strftime("%a")', '"%s, %s %d %s" % (local.strftime("%a")',
     "booking.counter.too_soon", ()),
    ("booking", "Could you send me a couple of times that work for you next week?",
     "Could you send me some times that work for you next week?", "booking.slot_already_taken", ()),
    ("draft", '"Hey there,"', '"Hi there,"', "first_reply.cleaning_reactivation.default.full", ()),
    ("draft", '"your business"', '"your company"', "first_reply.cleaning_trigger.send_info.full", ()),
    ("draft", '"the right person"', '"the best contact"', "first_reply.bookkeeping_trigger.referral.full", ()),
    ("draft", 'or "them"', 'or "that person"', "first_reply.bookkeeping_trigger.referral.full", ()),
    ("cadence", 'default="there"', 'default="friend"', "cadence.e1", ()),
    ("cadence", "usually the prospects who are in market right now", "usually the prospects in market right now",
     "cadence.e2.research_fallback.outbound", ()),
    ("cadence", "recovered about $6M worth of", "recovered roughly $6M worth of", "cadence.e4.offer_proof.reactivation",
     ()),
    ("cadence", "win back {company}'s past clients", "win back {company}'s former clients",
     "cadence.e5.offer_line.reactivation_bookkeeping", ()),
    ("cadence", "buildings that just changed property managers", "buildings that changed property managers",
     "cadence.e6.preview.cleaning_outbound", ()),
    ("cadence", "has to sort out cleaning around move-in", "has to sort out cleaning at move-in",
     "cadence.e9.observation.cleaning_outbound", ()),
    ("cadence", '"Re: your reply"', '"Re: our chat"', "cadence.e1", ()),
    ("cadence", '"Re: %s, question"', '"Re: %s, quick question"', "cadence.e1", ()),
] + FORMATTER_EDITS


def _edit_id(edit):
    return "%s:%s" % (edit[0], re.sub(r"\W+", "_", edit[2]).strip("_")[:28])


@pytest.mark.parametrize("modname,old,new,tid,carrying", FALLBACK_EDITS, ids=[_edit_id(e) for e in FALLBACK_EDITS])
def test_edit_to_any_fallback_literal_flips_the_id(modname, old, new, tid, carrying, approvals_file, tmp_path,
                                                   monkeypatch):
    from services.reply_engine import cadence as cad_mod, draft as draft_mod, no_show as ns_mod, show_rate as sr_mod

    module = {"show_rate": sr_mod, "booking": booking, "draft": draft_mod, "cadence": cad_mod, "slots": slots,
              "no_show": ns_mod}[modname]
    before = _index()
    ids = sorted(set([tid]) | set(i for i, e in before.items()
                                  if e["approvable"] and set(e["variables"]) & set(carrying)))
    if carrying:
        assert len(ids) > 60, "only %d ids carry %s" % (len(ids), carrying)
    ta.approve(ids, approved_by="Wendeline Okafor")
    assert [i for i in ids if ta.status(i) != ta.STATUS_APPROVED] == []
    _edited_copy(module, old, new, tmp_path, monkeypatch)
    after = _index()
    kept = [i for i in ids if ta.status(i, entries=after) != ta.STATUS_CHANGED]
    assert kept == [], "%s: editing %r left %d of %d ids approved: %s" % (modname, old, len(kept), len(ids), kept[:8])
    assert not ta.is_approved(tid)


def test_loom_sentence_is_inside_confirm_email_text():
    idx = _index()
    sentence = ta.loom_sentence()
    assert sentence and "{loom_url}" in sentence and "walkthrough" in sentence
    for tid, e in idx.items():
        if tid.startswith("show_rate.confirm_email"):
            assert sentence in e["text"], tid
            assert "loom_url" in e["variables"]
            assert "no_loom_url" in [v["name"] for v in e["variants"]]
            no_loom = [v for v in e["variants"] if v["name"] == "no_loom_url"][0]["text"]
            assert sentence not in no_loom


def test_variants_are_in_the_hash_and_in_the_review_document():
    idx = _index()
    e = idx["booking.counter.weekend"]
    names = [v["name"] for v in e["variants"]]
    assert {"missing_lead_data", "no_alternatives", "no_proposed_time", "dated", "subject"} <= set(names)
    texts = dict((v["name"], v["text"]) for v in e["variants"])
    assert "Hey there," in texts["missing_lead_data"]
    assert "Could you send me a couple of times that work for you next week?" in texts["no_alternatives"]
    assert "{booking_url}" not in texts["no_alternatives"] and "grab a time" not in texts["no_alternatives"]
    assert "That time does not work on my side" in texts["no_proposed_time"]
    assert "Re: your reply" in texts["subject"] and "Re: there, question" not in texts["subject"]
    assert "{booking_url}" not in texts["dated"] and "grab a time" not in texts["dated"]
    md = ta.render_catalogue_markdown()
    for v in e["variants"]:
        assert v["text"].rstrip("\n") in md
    conf = idx["booking.confirmation.zoom_link"]
    assert "your time" in [v for v in conf["variants"] if v["name"] == "lead_in_other_timezone"][0]["text"]
    ref = idx["first_reply.cleaning_reactivation.referral.full"]
    missing = [v for v in ref["variants"] if v["name"] == "missing_lead_data"][0]["text"]
    assert "the right person" in missing and "for them?" in missing and "Hey there," in missing


def test_catalogue_hashes_do_not_depend_on_the_environment(monkeypatch):
    from services.reply_engine import cadence as cad_mod, no_show as ns_mod, show_rate as sr_mod
    from shared import settings

    base = dict((e["id"], e["sha256"]) for e in ta.catalogue())
    monkeypatch.setenv("LOOM_URL_GENERIC", "https://loom.example.test/share/abc")
    monkeypatch.setenv("LOOM_URL_CLEANING", "https://loom.example.test/share/cln")
    for mod in (cad_mod,):
        monkeypatch.setattr(mod, "DEFAULT_BOOKING_URL", "https://other.example.test/booking")
    monkeypatch.setattr(settings, "BOOKING_URL", "https://other.example.test/booking")
    monkeypatch.setattr(sr_mod, "BOOKING_URL", "https://other.example.test/booking")
    ta.clear_cache()
    other = dict((e["id"], e["sha256"]) for e in ta.catalogue())
    assert [k for k in base if base[k] != other.get(k)] == []


# Defect 2: --approve-all-shown hashes the text it shows, not just the markers.
def test_approve_all_shown_refuses_text_swapped_under_intact_markers(approvals_file, tmp_path, capsys, log):
    md = ta.render_catalogue_markdown()
    real = _index()["cadence.e7"]["review_text"].rstrip("\n")
    assert real in md
    edited = md.replace(real, "Hey {first_name},\n\nTotally different words the reviewer read.\n\nLorenzo")
    p = tmp_path / "review.md"
    p.write_text(edited, encoding="utf-8")
    rc = cli.main(["--approve-all-shown", str(p), "--yes"], confirm=_confirm_never, isatty=_tty_yes, log_fn=log)
    assert rc == 1
    out = capsys.readouterr().out
    assert "cadence.e7: the text shown does not match its marker hash" in out
    assert ta.status("cadence.e7") == ta.STATUS_UNAPPROVED
    assert not approvals_file.exists()
    assert log.rows[-1][1] == "refused"


def test_approve_all_shown_refuses_a_markers_only_file(approvals_file, tmp_path, capsys, log):
    md = ta.render_catalogue_markdown()
    only = "\n".join(line for line in md.splitlines() if line.startswith("<!-- approve-template"))
    p = tmp_path / "markers_only.md"
    p.write_text(only, encoding="utf-8")
    rc = cli.main(["--approve-all-shown", str(p), "--yes"], confirm=_confirm_never, isatty=_tty_yes, log_fn=log)
    assert rc == 1
    assert "marker has no text block" in capsys.readouterr().out
    assert not approvals_file.exists()


def test_approve_all_shown_refuses_the_whole_file_for_one_bad_block(approvals_file, tmp_path, capsys, log):
    md = ta.render_catalogue_markdown()
    marker = [line for line in md.splitlines() if "id=cadence.e3 " in line][0]
    # drop the text block after one marker only
    head, tail = md.split(marker, 1)
    tail = tail.split("```", 2)[2]  # removes "```text ... ```"
    p = tmp_path / "one_bad.md"
    p.write_text(head + marker + tail, encoding="utf-8")
    assert cli.main(["--approve-all-shown", str(p), "--yes"], isatty=_tty_yes, log_fn=log) == 1
    assert "cadence.e3: marker has no text block" in capsys.readouterr().out
    assert not approvals_file.exists()


def test_parse_exported_blocks_reads_text_after_each_marker():
    md = ta.render_catalogue_markdown()
    blocks = ta.parse_exported_blocks(md)
    idx = _index()
    assert len(blocks) == sum(1 for e in idx.values() if e["approvable"])
    for b in blocks:
        assert b["text"] is not None
        assert ta.text_hash(b["text"]) == b["marker_sha256"] == idx[b["id"]]["sha256"]


# Unreadable approvals file: the refusal is logged.
def test_approve_against_an_unreadable_file_writes_a_job_log_row(approvals_file, capsys, log):
    approvals_file.write_text("{broken", encoding="utf-8")
    rc = cli.main(["--approve", "cadence.e1", "--yes"], confirm=_confirm_never, isatty=_tty_yes, log_fn=log)
    assert rc == 1
    assert "REFUSED" in capsys.readouterr().out
    assert log.rows and log.rows[-1][1] == "refused"
    assert "unreadable" in log.rows[-1][2]["reason"]
    assert approvals_file.read_text(encoding="utf-8") == "{broken"


# Excluded list.
def test_excluded_lists_the_invite_title_and_edited_bodies():
    sources = " ".join(x["source"] for x in ta.EXCLUDED)
    assert "booking.py:book" in sources
    assert "approval.py:edit" in sources
    edited = [x for x in ta.EXCLUDED if "approval.py:edit" in x["source"]][0]
    assert "never auto-sent" in edited["why"]


# Log noise and cache.
def test_catalogue_build_does_not_log_the_dummy_booking_refusal(caplog):
    ta.clear_cache()
    with caplog.at_level(logging.WARNING, logger="reply_engine.booking"):
        ta.catalogue()
    assert not [r for r in caplog.records if ta.DUMMY_LEAD_EMAIL in r.getMessage()]
    assert not [f for f in logging.getLogger("reply_engine.booking").filters
                if isinstance(f, ta._DummyLeadLogFilter)]


def test_log_filter_matches_only_the_dummy_address():
    flt = ta._DummyLeadLogFilter()

    def rec(msg):
        return logging.LogRecord("reply_engine.booking", logging.WARNING, __file__, 1, msg, (), None)
    assert not flt.filter(rec("booking refused for %s at x: slot_already_taken" % ta.DUMMY_LEAD_EMAIL))
    assert flt.filter(rec("booking refused for marisol@brightwater.test at x: slot_already_taken"))


def test_catalogue_is_cached_and_an_edit_invalidates_it(monkeypatch, tmp_path):
    from services.reply_engine import cadence as cad_mod

    calls = []
    real_build = ta._build_catalogue

    def counting():
        calls.append(1)
        return real_build()
    monkeypatch.setattr(ta, "_build_catalogue", counting)
    ta.clear_cache()
    first = ta.catalogue()
    ta.catalogue()
    assert len(calls) == 1
    copy_dir = tmp_path / "prompts"
    shutil.copytree(str(cad_mod.PROMPTS_DIR), str(copy_dir))
    monkeypatch.setattr(cad_mod, "PROMPTS_DIR", copy_dir)
    ta.catalogue()
    assert len(calls) == 2
    ta.catalogue()
    assert len(calls) == 2
    p = copy_dir / "cadence_e7.md"
    p.write_text(p.read_text(encoding="utf-8").replace("Last one from me this week", "Last one from me for this week"), encoding="utf-8")
    st = os.stat(str(p))
    os.utime(str(p), ns=(st.st_atime_ns, st.st_mtime_ns + 5 * 10 ** 9))
    again = dict((e["id"], e["sha256"]) for e in ta.catalogue())
    assert len(calls) == 3
    assert again["cadence.e7"] != dict((e["id"], e["sha256"]) for e in first)["cadence.e7"]
    # callers get copies: mutating one does not change the cache
    got = ta.catalogue()
    got[0]["text"] = "mutated"
    assert ta.catalogue()[0]["text"] != "mutated"


# ================================================================ round 3
# Defect 1: how times and slots are written feeds the hash of every id that
# carries a time or slot placeholder (the value_formats variant).
NON_TIME_PLACEHOLDERS = ("first_name", "company", "booking_url", "zoom_link", "referral_name", "referral_first_name",
                         "specialty", "research_line", "offer_proof", "offer_line", "preview", "observation",
                         "loom_url", "original_subject")
# {slot1} / {slot2} were the old cadence D6's placeholders. No template carries
# them since the E1..E10 ladder (2026-09-23), but they stay in
# ta.TIME_PLACEHOLDERS and in the value_formats block: dropping them would
# change that block, and so the hash of every approved id with a time in it.
# Section 4 decides when to retire them.
RETIRED_TIME_PLACEHOLDERS = ("slot1", "slot2")


def test_every_catalogue_placeholder_is_classified():
    """A new placeholder must be sorted into time/slot (and so get the
    value_formats block) or not; it cannot slip in unclassified."""
    assert not set(ta.TIME_PLACEHOLDERS) & set(NON_TIME_PLACEHOLDERS)
    seen = set(v for e in ta.catalogue() for v in e["variables"])
    assert seen - set(ta.TIME_PLACEHOLDERS) - set(NON_TIME_PLACEHOLDERS) == set()
    block = ta.value_formats_text()
    assert not seen & set(RETIRED_TIME_PLACEHOLDERS)
    for name in ta.TIME_PLACEHOLDERS:
        if name in RETIRED_TIME_PLACEHOLDERS:
            assert "{%s}" % name in block
            continue
        assert name in seen, "%s is listed as a time placeholder but no template carries it" % name
        assert "{%s}" % name in block, "the value_formats block does not say how {%s} is written" % name


def test_every_id_with_a_time_or_slot_placeholder_carries_the_value_formats_block():
    block = ta.value_formats_text()
    header = ta.VARIANT_HEADER % "value_formats (how times and slots are written)"
    md = ta.render_catalogue_markdown()
    shown = dict((b["id"], b["text"]) for b in ta.parse_exported_blocks(md))
    with_block = 0
    for e in ta.catalogue():
        names = [v["name"] for v in e["variants"]]
        if e["extractable"] and set(e["variables"]) & set(ta.TIME_PLACEHOLDERS):
            with_block += 1
            assert names.count("value_formats") == 1 and names[-1] == "value_formats", e["id"]
            assert e["variants"][-1]["text"] == block, e["id"]
            assert e["review_text"].endswith(header + "\n" + block), e["id"]
            assert e["sha256"] == ta.text_hash(e["review_text"]), e["id"]
            if e["approvable"]:
                assert header in shown[e["id"]] and block in shown[e["id"]], e["id"]
        else:
            assert "value_formats" not in names, e["id"]
            assert header not in e["review_text"], e["id"]
        # the block's own {placeholders} do not leak into the template's variables
        own = ta.compose_review_text(e["text"], [v for v in e["variants"] if v["name"] != "value_formats"])
        assert e["variables"] == ta._placeholders(own), e["id"]
    assert with_block > 80
    assert "cadence.e2" in shown and header not in shown["cadence.e2"]  # E2 offers no times


def test_value_formats_block_is_the_engine_formatters_output():
    import pytz

    block = ta.value_formats_text()
    tz = slots.TZ
    mon, tue, thu = [tz.localize(datetime(*t)) for t in ta.VALUE_FORMAT_TIMES]
    nxt = [tz.localize(datetime(*t)) for t in ta.VALUE_FORMAT_NEXT_WEEK]
    expected = [
        slots.format_slots([tue, thu]), slots.format_slots([tue]),
        slots.format_slot(tue), slots.format_slot(thu), slots.format_slot(mon),
        booking._dated_slots(nxt),
        show_rate.fmt_when(tue), show_rate.fmt_time_only(tue), show_rate.fmt_time_only(thu),
    ]
    for name in ta.ASKED_TIME_ZONES:
        expected.append("%s = %s" % (name, slots.format_asked_time(mon, pytz.timezone(name))))
        expected.append("%s = %s" % (name, slots.format_asked_time(mon, pytz.timezone(name), dated=True)))
    for name in ta.VALUE_FORMAT_ZONES:
        zone = pytz.timezone(name)
        expected.append("%s = %s" % (name, slots._tz_label(slots.to_tz(tue, zone), zone)))
        expected.append(show_rate.fmt_when(tue, zone))
        if booking._their_time(tue, name):
            expected.append(booking._their_time(tue, name).strip())
    for text in expected:
        assert text in block, text
    # every _tz_label branch and both clock halves are exercised
    for fragment in (" CT", " ET)", " MT)", " PT)", " MST)", "am", "pm", "12:05pm", " or "):
        assert fragment in block, fragment
    assert "zqx" not in block.lower()


def test_value_formats_and_hashes_do_not_depend_on_the_machine_timezone():
    import time

    base_block = ta.value_formats_text()
    base = dict((e["id"], e["sha256"]) for e in ta.catalogue())
    old = os.environ.get("TZ")
    offsets = set()
    try:
        # UTC+14 with no DST, and a half-hour zone that observes DST
        for zone in ("Pacific/Kiritimati", "America/St_Johns"):
            os.environ["TZ"] = zone
            time.tzset()
            offsets.add(time.localtime().tm_gmtoff)
            ta.clear_cache()
            assert ta.value_formats_text() == base_block, zone
            got = dict((e["id"], e["sha256"]) for e in ta.catalogue())
            assert [k for k in base if base[k] != got.get(k)] == [], zone
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()
        ta.clear_cache()
    assert len(offsets) == 2, "the two runs did not have different local timezones"


def test_a_value_formats_failure_fails_closed(monkeypatch):
    def broken():
        raise RuntimeError("formatter exploded")
    monkeypatch.setattr(ta, "value_formats_text", broken)
    ta.clear_cache()
    idx = _index()
    assert not idx["cadence.e1"]["extractable"] and not idx["cadence.e1"]["approvable"]
    assert "formatter exploded" in idx["cadence.e1"]["explanation"]
    assert not ta.is_approved("cadence.e1")
    # a template with no time in it is unaffected (E2 offers no times)
    assert idx["cadence.e2"]["approvable"] and idx["cadence.e2"]["extractable"]


# Cache: keyed on file content, and a build that raced an edit is not cached.
def _counting_build(monkeypatch, during=None):
    calls = []
    real_build = ta._build_catalogue

    def counting():
        out = real_build()
        calls.append(1)
        if during is not None and len(calls) == 1:
            during()
        return out
    monkeypatch.setattr(ta, "_build_catalogue", counting)
    ta.clear_cache()
    return calls


def test_a_same_size_edit_with_its_mtime_put_back_invalidates_the_cache(monkeypatch, tmp_path):
    from services.reply_engine import cadence as cad_mod

    copy_dir = tmp_path / "prompts"
    shutil.copytree(str(cad_mod.PROMPTS_DIR), str(copy_dir))
    monkeypatch.setattr(cad_mod, "PROMPTS_DIR", copy_dir)
    calls = _counting_build(monkeypatch)
    first = _index()["cadence.e7"]
    assert len(calls) == 1
    p = copy_dir / "cadence_e7.md"
    st = os.stat(str(p))
    text = p.read_text(encoding="utf-8")
    edited = text.replace("not the right moment", "not the right minute")
    assert edited != text and len(edited.encode("utf-8")) == len(text.encode("utf-8"))
    p.write_text(edited, encoding="utf-8")
    os.utime(str(p), ns=(st.st_atime_ns, st.st_mtime_ns))
    assert (os.stat(str(p)).st_mtime_ns, os.stat(str(p)).st_size) == (st.st_mtime_ns, st.st_size)
    again = _index()["cadence.e7"]
    assert len(calls) == 2
    assert "not the right minute" in again["text"] and again["sha256"] != first["sha256"]


def test_a_source_edited_during_the_build_is_built_again_not_cached_stale(monkeypatch, tmp_path):
    from services.reply_engine import cadence as cad_mod

    copy_dir = tmp_path / "prompts"
    shutil.copytree(str(cad_mod.PROMPTS_DIR), str(copy_dir))
    monkeypatch.setattr(cad_mod, "PROMPTS_DIR", copy_dir)
    p = copy_dir / "cadence_e7.md"

    def edit_mid_build():
        p.write_text(p.read_text(encoding="utf-8").replace("Last one from me this week", "Last one from me for this week"), encoding="utf-8")
    calls = _counting_build(monkeypatch, during=edit_mid_build)
    got = _index()["cadence.e7"]
    assert len(calls) == 2, "the build that raced the edit was kept"
    assert "Last one from me for this week" in got["text"]
    assert "Last one from me for this week" in _index()["cadence.e7"]["text"]
    assert len(calls) == 2  # the second, consistent build is the cached one


def test_sources_that_never_hold_still_fail_closed(monkeypatch, tmp_path, approvals_file):
    from services.reply_engine import cadence as cad_mod

    ta.approve(["cadence.e7"], approved_by="Wendeline Okafor")
    copy_dir = tmp_path / "prompts"
    shutil.copytree(str(cad_mod.PROMPTS_DIR), str(copy_dir))
    monkeypatch.setattr(cad_mod, "PROMPTS_DIR", copy_dir)
    p = copy_dir / "cadence_e7.md"
    real_build = ta._build_catalogue

    def always_racing():
        out = real_build()
        p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return out
    monkeypatch.setattr(ta, "_build_catalogue", always_racing)
    ta.clear_cache()
    with pytest.raises(RuntimeError):
        ta.catalogue()
    assert not ta.is_approved("cadence.e7")
