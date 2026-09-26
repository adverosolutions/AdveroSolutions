"""CRM stage correction change-set (changesets/crm_stage_correction/).

Fixtures: fixtures/crm_stage_correction/crm_snapshot.json (two tabs in the
legacy sync's layout) and leads_snapshot.json (scrubbed real items from
config/snapshots/instantly_replied_leads_2026-09-21.json; its _meta lists
every edit). The sheet is a fake that records calls; nothing leaves the process.
"""
import copy
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shared import job_log
from changesets.crm_stage_correction import apply_crm_stage_correction as A
from changesets.crm_stage_correction import legacy_mapping as L

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "crm_stage_correction"
CRM_PATH = FIX / "crm_snapshot.json"
LEADS_PATH = FIX / "leads_snapshot.json"
RECORDED = HERE.parent.parent / "config" / "snapshots" / "instantly_replied_leads_2026-09-21.json"
NOW = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)   # 10:00 CDT
TODAY = "2026-09-25"


def crm():
    data = json.loads(CRM_PATH.read_text())
    return dict((k, v) for k, v in data.items() if not k.startswith("_"))


def leads():
    return json.loads(LEADS_PATH.read_text())["items"]


class FakeWorksheet(object):
    def __init__(self, book, title, values):
        self.book, self.title, self.values = book, title, values

    def get_all_values(self):
        self.book.calls.append(("get_all_values", self.title))
        if self.book.unreadable.get(self.title):
            raise ConnectionResetError("connection reset by peer")
        return copy.deepcopy(self.values)

    def batch_update(self, data, value_input_option=None):
        backups = sorted(os.listdir(str(self.book.backup_dir))) if self.book.backup_dir else []
        self.book.calls.append(("batch_update", self.title, copy.deepcopy(data), value_input_option, backups))
        mode = self.book.fail.get(self.title)
        if mode == "before":
            raise TimeoutError("The read operation timed out")
        for item in data:
            m = re.match(r"^([A-Z]+)(\d+)$", item["range"])
            col = 0
            for ch in m.group(1):
                col = col * 26 + (ord(ch) - 64)
            row = self.values[int(m.group(2)) - 1]
            while len(row) < col:
                row.append("")
            row[col - 1] = item["values"][0][0]
        if mode in ("after", "after_unreadable"):
            if mode == "after_unreadable":
                self.book.unreadable[self.title] = True
            raise TimeoutError("The read operation timed out")


class FakeBook(object):
    def __init__(self, tabs, backup_dir=None, id="sheet-crm-test"):
        self.id = id
        self.calls = []
        self.backup_dir = backup_dir
        self.fail = {}          # tab -> "before" | "after" | "after_unreadable"
        self.unreadable = {}    # tab -> True: get_all_values raises
        self.sheets = dict((t, FakeWorksheet(self, t, copy.deepcopy(v))) for t, v in tabs.items())

    def worksheet(self, title):
        self.calls.append(("worksheet", title))
        if title not in self.sheets:
            raise KeyError(title)
        return self.sheets[title]

    def writes(self):
        return [c for c in self.calls if c[0] == "batch_update"]

    def values(self):
        return dict((t, copy.deepcopy(ws.values)) for t, ws in self.sheets.items())


def by_email(items):
    out = {}
    for e in items:
        out.setdefault(e["email"], []).append(e)
    return out


def dry_run(tmp_path, extra=None, **kw):
    lines = []
    argv = ["--dry-run", "--plan-out", str(tmp_path / "plans")] + (extra or [])
    code = A.main(argv, out=lines.append, now=NOW, **kw)
    plans = sorted((tmp_path / "plans").glob("plan_*.json"))
    return code, lines, (json.loads(plans[-1].read_text()) if plans else None), (plans[-1] if plans else None)


def live_plan(tmp_path, tabs=None, id="sheet-crm-test"):
    """A plan read from a (fake) live sheet, so it carries a spreadsheet id."""
    code, lines, plan, path = dry_run(tmp_path, sheet=FakeBook(tabs or crm(), id=id), leads=leads())
    assert code == 0, "\n".join(lines)
    return plan, path


def apply(book, path, backups, confirm=None, yes=True):
    lines = []
    argv = ["--apply", "--plan-file", str(path)] + (["--yes"] if yes else [])
    code = A.main(argv, sheet=book, out=lines.append, now=NOW, confirm=confirm, backup_dir=backups)
    return code, lines


def restore(book, point, backups, confirm=None, yes=True):
    lines = []
    argv = ["--restore", str(point)] + (["--yes"] if yes else [])
    code = A.main(argv, sheet=book, out=lines.append, now=NOW, confirm=confirm, backup_dir=backups)
    return code, lines


def entry(plan, email, key="entries"):
    return [e for e in plan[key] if e["email"] == email][0]


# ------------------------------------------------------------------ mappings

def test_branch_function_matches_the_verbatim_legacy_function():
    items = leads() + json.loads(RECORDED.read_text())["items"]
    for lead in items:
        assert L.legacy_stage_and_branch(lead)[0] == L.determine_crm_stage(lead)
    assert L.legacy_stage_and_branch({"status": 1, "esp_code": 3})[1] == "bounced_esp_code"
    assert L.legacy_stage_and_branch({"status": -1, "esp_code": 3})[1] == "bounced_status"
    assert L.legacy_stage_and_branch({"status": 1, "esp_code": 2}) == ("Contacted", "delivered_esp_code")
    assert L.legacy_stage_and_branch({"status": 3, "email_reply_count": 0})[1] == "completed_as_replied"
    assert L.legacy_stage_and_branch({"status": 1, "email_reply_count": 1, "lt_interest_status": 0})[1] \
        == "ooo_as_replied"
    assert L.legacy_stage_and_branch({"status": 3, "email_reply_count": 2})[1] == "replied_neutral"


def test_fixed_sync_mapping_follows_the_spec():
    d = A.sync_module().determine_crm_stage
    contacted = {"timestamp_last_contact": "2026-09-18T17:32:40Z"}
    assert d(dict(contacted, status=1, esp_code=3)) == "Contacted"
    assert d({"status": 1, "esp_code": 3}) is None
    assert d(dict(contacted, status=1, email_reply_count=1, lt_interest_status=0)) == "Contacted"
    assert d({"status": -2}) == "Closed - Lost"
    assert d({"status": 3, "lt_interest_status": 4}) == "Closed - Won"
    assert d({"status": 3, "lt_interest_status": -4}) == "No-Show"
    assert d({"status": 1, "email_reply_count": 1}) == "Replied - Neutral"
    assert d({"status": 1, "status_summary": {"lastStep": {"timestamp_executed": "x"}}}) == "Contacted"


# ------------------------------------------------------------------ the plan

def test_plan_flags_the_bug_rows_and_nothing_else():
    plan = A.build_plan(crm(), leads(), NOW)
    e = by_email(plan["entries"])
    assert plan["_meta"]["spreadsheet_id"] is None

    z1 = e["owner@z1-hvac.example"][0]
    assert (z1["tab"], z1["row"], z1["current_stage"]) == ("HVAC Leads", 2, "Closed - Lost")
    assert (z1["reason"], z1["proposed_stage"], z1["confidence"]) == ("bounced_esp_code", "Contacted", "high")
    assert z1["review_reasons"] == [] and z1["prior_stage_unknown"] is False
    assert z1["evidence"][0]["esp_code"] == 3 and z1["evidence"][0]["last_step_timestamp_executed"]
    assert z1["evidence"][0]["timestamp_created"] == "2026-09-15T14:59:39.126Z"

    z2 = e["owner@z2-hvac.example"][0]     # the sheet holds "Owner@Z2-HVAC.example "
    assert (z2["reason"], z2["proposed_stage"], z2["prior_stage_unknown"]) == \
        ("bounced_esp_code", "New/Uncontacted", True)
    assert (z2["confidence"], z2["review_reasons"]) == ("review", ["prior_stage_unknown"])

    z3 = e["owner@z3-hvac.example"][0]
    assert z3["confidence"] == "review" and z3["notes"] and z3["review_reasons"] == ["notes"]

    m1 = e["owner@m1-roof.example"][0]
    assert (m1["current_stage"], m1["reason"], m1["proposed_stage"], m1["prior_stage_unknown"]) == \
        ("Contacted", "delivered_esp_code", "New/Uncontacted", True)
    assert m1["confidence"] == "review"

    c1 = e["owner@c1-roof.example"][0]
    assert (c1["current_stage"], c1["reason"], c1["proposed_stage"], c1["confidence"]) == \
        ("Replied - Neutral", "completed_as_replied", "Contacted", "high")

    o1 = e["owner@o1-roof.example"][0]
    assert (o1["reason"], o1["proposed_stage"], o1["confidence"]) == ("ooo_as_replied", "Contacted", "high")

    # A real bounce, a real positive reply and a row the old sync never moved stay out.
    flagged = set(e) | set(r["email"] for r in plan["needs_review"])
    for email in ("owner@b1-hvac.example", "owner@p1-roof.example", "owner@g1-hvac.example"):
        assert email not in flagged

    dup = [r for r in plan["needs_review"] if r["email"] == "owner@z4-hvac.example"]
    assert sorted(r["row"] for r in dup) == [5, 8]
    assert all(r["proposed_stage"] is None and r["reason"] == "duplicate_email_in_tab"
               and r["suggested_stage"] == "Contacted" for r in dup)
    assert "owner@z4-hvac.example" not in e

    s = plan["summary"]
    assert s["entries"] == 6 and s["needs_review"] == 2
    assert s["by_tab"]["HVAC Leads"]["entries"] == {"bounced_esp_code": 3}
    assert s["by_tab"]["Roofing Leads"]["entries"] == {
        "delivered_esp_code": 1, "completed_as_replied": 1, "ooo_as_replied": 1}
    # g1 (Google-hosted, emailed, still New/Uncontacted) is the fixed sync's job.
    assert s["information_only"]["fixed_sync_would_move_forward"] == {
        "HVAC Leads": 1, "Roofing Leads": 0, "total": 1}


@pytest.mark.parametrize("last_updated,reasons", [
    ("2026-02-20", ["last_updated_before_legacy_sync_deploy", "last_updated_before_lead_created"]),
    ("2026-09-01", ["last_updated_before_lead_created"]),
    ("9/1/2026", ["last_updated_before_lead_created"]),
    ("", ["last_updated_empty"]),
    ("soon", ["last_updated_unreadable"]),
    ("2026-09-15", []),       # created 2026-09-15 09:59 CDT: same day is not before
])
def test_confidence_is_review_when_the_legacy_sync_cannot_have_set_the_stage(last_updated, reasons):
    tabs = crm()
    tabs["HVAC Leads"][1][15] = last_updated          # z1
    z1 = entry(A.build_plan(tabs, leads(), NOW), "owner@z1-hvac.example")
    assert z1["review_reasons"] == reasons
    assert z1["confidence"] == ("review" if reasons else "high")


def test_skipped_lead_that_would_go_back_to_new_uncontacted_needs_review(tmp_path):
    items = leads()
    for lead in items:
        if lead["email"] == "owner@z2-hvac.example":
            lead["status"] = -3                       # skipped (may be blocklisted)
    plan = A.build_plan(crm(), items, NOW)
    assert "owner@z2-hvac.example" not in by_email(plan["entries"])
    z2 = entry(plan, "owner@z2-hvac.example", "needs_review")
    assert (z2["reason"], z2["proposed_stage"], z2["suggested_stage"], z2["bug_reason"]) == \
        ("lead_unsubscribed_or_skipped", None, "New/Uncontacted", "bounced_esp_code")
    assert z2["confidence"] == "review" and "lead_status_-3_skipped" in z2["review_reasons"]
    lines = []
    A.print_plan(plan, lines.append)
    assert any("owner@z2-hvac.example" in l and "lead_status_-3_skipped" in l for l in lines)


def test_mx_flags_zoho_hosted_closed_lost_rows_with_no_instantly_lead(tmp_path):
    asked = []

    def resolver(domain):
        asked.append(domain)
        return {"zoho-mx-only.example": ["mx.zoho.com", "mx2.zoho.com"]}.get(domain, ["aspmx.l.google.com"])

    code, lines, plan, _ = dry_run(tmp_path, ["--crm-snapshot", str(CRM_PATH), "--leads-snapshot",
                                              str(LEADS_PATH), "--mx"], resolver=resolver)
    assert code == 0
    assert sorted(asked) == ["google-mx-only.example", "zoho-mx-only.example"]
    mx = [r for r in plan["needs_review"] if r["reason"] == "zoho_mx_no_instantly_record"]
    assert [(r["tab"], r["row"], r["email"], r["proposed_stage"]) for r in mx] == \
        [("HVAC Leads", 9, "info@zoho-mx-only.example", None)]
    assert mx[0]["evidence"][0]["mx_hosts"] == ["mx.zoho.com", "mx2.zoho.com"]


# ------------------------------------------------------------------ no writes

def test_dry_run_offline_and_against_a_sheet_writes_nothing(tmp_path, tmp_env):
    code, lines, plan, path = dry_run(tmp_path, ["--crm-snapshot", str(CRM_PATH),
                                                 "--leads-snapshot", str(LEADS_PATH)])
    assert code == 0 and plan["summary"]["entries"] == 6
    assert plan["_meta"]["spreadsheet_id"] is None
    assert any("dry-run only; nothing was written" in l for l in lines)
    assert any("cannot be applied live" in l for l in lines)

    book = FakeBook(crm(), id="sheet-A")
    code, _, plan2, _ = dry_run(tmp_path, sheet=book, leads=leads())
    assert code == 0 and plan2["summary"]["entries"] == 6
    assert plan2["_meta"]["spreadsheet_id"] == "sheet-A"
    assert book.writes() == []
    assert set(c[0] for c in book.calls) == {"worksheet", "get_all_values"}
    # The default plan location is the repo tmp dir.
    assert A.save_plan(plan2, NOW).parent == Path(os.environ["ADVERO_TMP_DIR"]) / "crm_stage_correction"


def test_dry_run_opens_the_sheet_read_only_and_apply_read_write(tmp_path, monkeypatch, live_mode):
    scopes = []
    book = FakeBook(crm())

    def fake_open(requested=None):
        scopes.append(list(requested))
        return book

    monkeypatch.setattr(A, "open_spreadsheet", fake_open)
    code, lines, plan, path = dry_run(tmp_path, leads=leads())
    assert code == 0 and plan["_meta"]["spreadsheet_id"] == "sheet-crm-test"
    assert scopes == [["https://www.googleapis.com/auth/spreadsheets.readonly"]]
    code, lines = apply(None, path, tmp_path / "backups")
    assert code == 0, "\n".join(lines)
    assert scopes[1] == ["https://www.googleapis.com/auth/spreadsheets"]


def test_shadow_apply_reads_and_writes_nothing(tmp_path, shadow_mode):
    _, _, _, path = dry_run(tmp_path, ["--crm-snapshot", str(CRM_PATH), "--leads-snapshot", str(LEADS_PATH)])
    book = FakeBook(crm())
    lines = []
    code = A.main(["--apply", "--plan-file", str(path), "--yes"], sheet=book, out=lines.append, now=NOW,
                  backup_dir=tmp_path / "backups")
    assert code == 0
    assert book.calls == []
    assert not (tmp_path / "backups").exists()
    assert any(l.startswith("SHADOW") for l in lines)
    assert any("offline snapshot" in l for l in lines)
    rows = [r for r in job_log.read_shadow_log() if r.get("action") == "crm_stage_correction"]
    assert rows and rows[-1]["payload"]["rows"] == 6


# ------------------------------------------------------------------ live (mocked)

def test_live_apply_backs_up_first_writes_only_planned_cells_and_restore_puts_them_back(tmp_path, live_mode):
    plan, path = live_plan(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    tabs = crm()
    # Since the plan: a row was inserted at the top of HVAC (every HVAC row moved
    # down one) and someone moved the completed lead on by hand.
    tabs["HVAC Leads"].insert(1, ["New/Uncontacted", "Inserted Co", "", "", "new@row.example"] + [""] * 12)
    tabs["Roofing Leads"][2][0] = "Meeting Scheduled"
    book = FakeBook(tabs, backup_dir=backups)
    before = copy.deepcopy(book.sheets)

    prompts = []
    code, lines = apply(book, path, backups, confirm=lambda q: (prompts.append(q), "5")[1], yes=False)
    assert code == 0, "\n".join(lines)
    assert "(5)" in prompts[0]
    # Read, confirm, read again, then write.
    reads = [i for i, c in enumerate(book.calls) if c[0] == "get_all_values"]
    assert len(reads) == 4 and reads[-1] < book.calls.index(book.writes()[0])

    writes = book.writes()
    assert [w[1] for w in writes] == ["HVAC Leads", "Roofing Leads"]
    assert all(w[3] == "USER_ENTERED" for w in writes)
    assert all(any(n.endswith(".preapply.json") for n in w[4]) for w in writes)   # backup existed first
    assert [d["range"] for d in writes[0][2]] == ["A3", "P3", "A4", "P4", "A5", "P5"]
    assert [d["range"] for d in writes[1][2]] == ["A2", "P2", "A4", "P4"]
    hv, rf = book.sheets["HVAC Leads"].values, book.sheets["Roofing Leads"].values
    assert (hv[2][0], hv[2][15]) == ("Contacted", TODAY)             # z1, moved from row 2
    assert (hv[3][0], hv[3][15]) == ("New/Uncontacted", TODAY)       # z2
    assert hv[4][0] == "Contacted" and hv[4][16]                     # z3, Notes untouched
    assert rf[2][0] == "Meeting Scheduled" and rf[2][15] == "2026-09-22"   # changed since plan: skipped
    assert rf[1][0] == "New/Uncontacted" and rf[3][0] == "Contacted"
    # Every other cell is as it was.
    touched = {("HVAC Leads", 2), ("HVAC Leads", 3), ("HVAC Leads", 4), ("Roofing Leads", 1), ("Roofing Leads", 3)}
    for tab, ws in book.sheets.items():
        for i, row in enumerate(ws.values):
            if (tab, i) not in touched:
                assert row == before[tab].values[i]
    assert any("Stage changed since" in l and "owner@c1-roof.example" in l for l in lines)

    point_files = sorted(backups.glob("crm_stage_correction_before_*.json"))
    assert len(point_files) == 1 and not point_files[0].name.endswith(".preapply.json")
    point = json.loads(point_files[0].read_text())
    meta = point["_rollback_point"]
    assert (meta["kind"], meta["outcome"], meta["spreadsheet_id"]) == ("apply", "applied", "sheet-crm-test")
    assert point["spreadsheet_id"] == "sheet-crm-test"
    assert meta["tabs_sent"] == meta["tabs_confirmed"] == ["HVAC Leads", "Roofing Leads"]
    z1 = [r for r in point["rows"] if r["email"] == "owner@z1-hvac.example"][0]
    assert (z1["row"], z1["stage_before"], z1["last_updated_before"]) == (3, "Closed - Lost", "2026-09-16")

    # Restore: m1 was changed again by hand after the apply, so it stays.
    book.sheets["Roofing Leads"].values[1][0] = "Replied - Positive"
    book.calls[:] = []
    code, lines = restore(book, point_files[0], backups)
    assert code == 0, "\n".join(lines)
    hv, rf = book.sheets["HVAC Leads"].values, book.sheets["Roofing Leads"].values
    assert (hv[2][0], hv[2][15]) == ("Closed - Lost", "2026-09-16")
    assert (hv[3][0], hv[4][0]) == ("Closed - Lost", "Closed - Lost")
    assert (rf[3][0], rf[3][15]) == ("Replied - Neutral", "2026-09-17")
    assert rf[1][0] == "Replied - Positive"
    assert any("owner@m1-roof.example" in l and "SKIP" in l for l in lines)
    pre = list(backups.glob("*.prerestore.json"))
    assert pre and json.loads(pre[0].read_text())["_rollback_point"]["spreadsheet_id"] == "sheet-crm-test"


def test_live_apply_writes_nothing_when_the_backup_fails(tmp_path, live_mode):
    _, path = live_plan(tmp_path)
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    book = FakeBook(crm())
    code, lines = apply(book, path, blocker)
    assert code == A.EXIT_REFUSED
    assert book.writes() == []
    assert any("backup could not be written" in l for l in lines)


# ------------------------------------------ the sheet moves during the prompt

def _delete_z1_row(book):
    del book.sheets["HVAC Leads"].values[1]              # HVAC row 2; every row below moves up


def _insert_row(book):
    book.sheets["HVAC Leads"].values.insert(1, ["New/Uncontacted", "Inserted Co", "", "", "new@row.example"]
                                            + [""] * 12)


def _change_m1_stage(book):
    book.sheets["Roofing Leads"].values[1][0] = "Replied - Positive"


MUTATIONS = [_delete_z1_row, _insert_row, _change_m1_stage]


@pytest.mark.parametrize("mutate", MUTATIONS)
def test_apply_writes_nothing_when_the_sheet_changes_during_the_prompt(tmp_path, live_mode, mutate):
    _, path = live_plan(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    book = FakeBook(crm(), backup_dir=backups)

    def confirm(question):
        mutate(book)
        return "6"

    code, lines = apply(book, path, backups, confirm=confirm, yes=False)
    assert code == A.EXIT_REFUSED, "\n".join(lines)
    assert book.writes() == []
    assert list(backups.iterdir()) == []
    assert any("changed while the confirmation was open" in l for l in lines)
    assert any("Nothing was backed up or written" in l for l in lines)
    assert any("confirmed row" in l for l in lines)


@pytest.mark.parametrize("mutate", MUTATIONS)
def test_restore_writes_nothing_when_the_sheet_changes_during_the_prompt(tmp_path, live_mode, mutate):
    _, path = live_plan(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    book = FakeBook(crm(), backup_dir=backups)
    code, lines = apply(book, path, backups)
    assert code == 0, "\n".join(lines)
    point = sorted(backups.glob("crm_stage_correction_before_*.json"))[0]
    applied = book.values()
    book.calls[:] = []

    def confirm(question):
        mutate(book)
        return "6"

    code, lines = restore(book, point, backups, confirm=confirm, yes=False)
    assert code == A.EXIT_REFUSED, "\n".join(lines)
    assert book.writes() == []
    assert list(backups.glob("*.prerestore.json")) == []
    assert any("changed while the confirmation was open" in l for l in lines)
    # Nothing but the mutation itself changed.
    expected = FakeBook(applied)
    mutate(expected)
    assert book.values() == expected.values()


# ------------------------------------------ a batch_update that raises

def test_timeout_after_the_write_landed_leaves_a_restorable_backup(tmp_path, live_mode):
    _, path = live_plan(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    book = FakeBook(crm(), backup_dir=backups)
    original = book.values()
    book.fail["HVAC Leads"] = "after"
    code, lines = apply(book, path, backups)
    assert code == A.EXIT_API
    assert [w[1] for w in book.writes()] == ["HVAC Leads"]              # Roofing never sent
    assert book.sheets["HVAC Leads"].values[1][0] == "Contacted"        # it landed
    assert book.values()["Roofing Leads"] == original["Roofing Leads"]
    text = "\n".join(lines)
    assert "LANDED" in text and "Tabs not sent: Roofing Leads" in text

    points = sorted(backups.glob("crm_stage_correction_before_*.json"))
    assert len(points) == 1 and not points[0].name.endswith((".preapply.json", ".not_applied.json"))
    meta = json.loads(points[0].read_text())["_rollback_point"]
    assert (meta["kind"], meta["outcome"]) == ("apply", "stopped")
    assert meta["tabs_sent"] == ["HVAC Leads"] and meta["tabs_confirmed"] == []
    assert meta["tabs_not_sent"] == ["Roofing Leads"]
    assert meta["failed"]["outcome"] == "landed_after_error" and "TimeoutError" in meta["error"]

    book.fail.clear()
    code, lines = restore(book, points[0], backups)
    assert code == 0, "\n".join(lines)
    assert book.values() == original


def test_timeout_before_the_write_landed_reports_it_and_restore_is_a_no_op(tmp_path, live_mode):
    _, path = live_plan(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    book = FakeBook(crm(), backup_dir=backups)
    original = book.values()
    book.fail["HVAC Leads"] = "before"
    code, lines = apply(book, path, backups)
    assert code == A.EXIT_API
    assert book.values() == original
    text = "\n".join(lines)
    assert "still hold the old values" in text and "does not prove the write was dropped" in text
    assert "Nothing after it was sent" not in text

    points = sorted(backups.glob("crm_stage_correction_before_*.json"))
    meta = json.loads(points[0].read_text())["_rollback_point"]
    assert (meta["kind"], meta["failed"]["outcome"]) == ("apply", "unchanged_at_reread")

    book.fail.clear()
    book.calls[:] = []
    code, lines = restore(book, points[0], backups)
    assert code == 0 and book.writes() == []
    assert any("Nothing to restore" in l for l in lines)


def test_timeout_with_an_unreadable_tab_says_the_outcome_is_unknown(tmp_path, live_mode):
    _, path = live_plan(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    book = FakeBook(crm(), backup_dir=backups)
    book.fail["HVAC Leads"] = "after_unreadable"
    code, lines = apply(book, path, backups)
    assert code == A.EXIT_API
    assert any("UNKNOWN" in l for l in lines)
    meta = json.loads(sorted(backups.glob("crm_stage_correction_before_*.json"))[0].read_text())["_rollback_point"]
    assert (meta["kind"], meta["failed"]["outcome"]) == ("apply", "unknown_after_error")


# ------------------------------------------ headers

def test_a_tab_without_a_last_updated_header_is_read_but_never_written(tmp_path, live_mode):
    tabs = crm()
    tabs["Roofing Leads"][0][15] = ""
    plan, path = live_plan(tmp_path, tabs)
    assert plan["_meta"]["header_warnings"]["Roofing Leads"]["apply_refuses_tab"] is True
    assert plan["summary"]["by_tab"]["Roofing Leads"]["entries"]         # still planned (read by column P)
    lines = []
    A.print_plan(plan, lines.append)
    assert any("WARNING" in l and "Roofing Leads" in l and "Last Updated" in l for l in lines)
    assert any("will NOT write this tab" in l for l in lines)

    backups = tmp_path / "backups"
    book = FakeBook(tabs, backup_dir=None)
    code, lines = apply(book, path, backups)
    assert code == 0, "\n".join(lines)
    assert [w[1] for w in book.writes()] == ["HVAC Leads"]
    assert book.values()["Roofing Leads"] == tabs["Roofing Leads"]
    assert any("tab refused" in l and "Roofing Leads" in l for l in lines)


def test_restore_refuses_a_tab_whose_header_lost_a_column(tmp_path, live_mode):
    _, path = live_plan(tmp_path)
    backups = tmp_path / "backups"
    book = FakeBook(crm())
    assert apply(book, path, backups)[0] == 0
    point = sorted(backups.glob("crm_stage_correction_before_*.json"))[0]
    book.sheets["HVAC Leads"].values[0][0] = ""          # no "Stage" header any more
    hvac = copy.deepcopy(book.sheets["HVAC Leads"].values)
    book.calls[:] = []
    code, lines = restore(book, point, backups)
    assert [w[1] for w in book.writes()] == ["Roofing Leads"]
    assert book.sheets["HVAC Leads"].values == hvac
    assert any("tab refused" in l and "'Stage'" in l for l in lines)


def test_an_ambiguous_missing_header_leaves_the_tab_out_of_the_plan(tmp_path):
    tabs = crm()
    tabs["Roofing Leads"][0][4] = "Contact"              # column E has another name
    plan, _ = live_plan(tmp_path, tabs)
    w = plan["_meta"]["header_warnings"]["Roofing Leads"]
    assert w["left_out"] is True and w["ambiguous"] == ["Email"]
    assert not any(e["tab"] == "Roofing Leads" for e in plan["entries"])
    lines = []
    A.print_plan(plan, lines.append)
    assert any("LEFT OUT" in l for l in lines)


# ------------------------------------------ spreadsheet id

def test_a_snapshot_plan_is_never_applied_live(tmp_path, live_mode):
    _, _, _, path = dry_run(tmp_path, ["--crm-snapshot", str(CRM_PATH), "--leads-snapshot", str(LEADS_PATH)])
    book = FakeBook(crm())
    code, lines = apply(book, path, tmp_path / "backups")
    assert code == A.EXIT_REFUSED
    assert book.calls == []
    assert any("offline snapshot" in l and "cannot be" in l for l in lines)


def test_apply_and_restore_refuse_another_spreadsheet(tmp_path, live_mode):
    _, path = live_plan(tmp_path, id="sheet-A")
    backups = tmp_path / "backups"
    other = FakeBook(crm(), id="sheet-B")
    code, lines = apply(other, path, backups)
    assert code == A.EXIT_REFUSED and other.calls == []
    assert any("sheet-A" in l and "sheet-B" in l for l in lines)

    book = FakeBook(crm(), id="sheet-A")
    assert apply(book, path, backups)[0] == 0
    point = sorted(backups.glob("crm_stage_correction_before_*.json"))[0]
    code, lines = restore(other, point, backups)
    assert code == A.EXIT_REFUSED and other.calls == []
