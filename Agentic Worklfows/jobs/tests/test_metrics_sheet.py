"""services/metrics/sheet.py: the Daily Log read, the streak, the guarded write."""
import json
from datetime import date

import pytest

from shared import settings
from shared.job_log import read_shadow_log
from services.metrics import sheet

FIXTURES = sheet.BASE_DIR / "services" / "metrics" / "fixtures"
DAY = date(2026, 9, 22)


class FakeSheet(object):
    """The recorded Daily Log, plus a record of every update attempt."""

    def __init__(self, values=None):
        if values is None:
            with open(FIXTURES / "daily_log_2026-09-22.json", "r", encoding="utf-8") as fh:
                values = json.load(fh)
        self.values = values
        self.updates = []

    def get_all_values(self):
        return self.values

    def update(self, range_name, values):
        self.updates.append((range_name, values))
        return {"updatedRange": range_name}


@pytest.fixture
def log():
    return sheet.read_daily_log(FakeSheet())


# ------------------------------------------------------------------ schema
def test_the_local_schema_copy_matches_the_tracker_builder():
    """execution/build_daily_metrics_tracker.py owns the column order. If it
    changes and FALLBACK_METRICS does not, a degraded run writes every number
    into the wrong column.

    The builder is imported **here**, not through ``metric_schema()``: that
    helper falls back to FALLBACK_METRICS when the import fails, so the
    assertion compared the fallback to itself and stayed green exactly when the
    builder had drifted and the guard was needed."""
    import importlib
    import sys

    exec_dir = str(sheet.BASE_DIR / "execution")
    if exec_dir not in sys.path:
        sys.path.insert(0, exec_dir)
    module = importlib.import_module("build_daily_metrics_tracker")
    assert [(m[0], m[2]) for m in module.METRICS] == sheet.FALLBACK_METRICS
    assert sheet.metric_schema() == sheet.FALLBACK_METRICS


def test_row_range_stops_at_the_notes_column():
    # B..X are the 23 metrics, Y is Notes. Z ("Logged") holds a formula and must
    # never be in the range: writing a value there breaks the streak.
    assert sheet.row_range(52) == "B52:Y52"
    assert sheet.col_letter(26) == "Z"


# -------------------------------------------------------------- reading it
def test_reads_the_date_column_as_serials_not_display_text(log):
    # The displayed value is "Tue, Sep 22" with no year, so only the serial can
    # identify the row.
    assert log.row_for(DAY) == 52
    assert log.row_for(date(2026, 8, 3)) == 2


def test_logged_days_are_the_four_real_ones(log):
    assert log.logged_days() == [date(2026, 8, 3), date(2026, 8, 10),
                                 date(2026, 8, 11), date(2026, 8, 12)]
    assert log.is_logged(DAY) is False


# ------------------------------------------------------------- streak rules
def test_a_forty_day_gap_restarts_the_streak_and_backfills_nothing(log):
    out = sheet.streak_and_day(log.logged_days(), DAY)
    assert out["streak"] == 1
    assert out["day_number"] == 5           # four logged days plus today
    assert out["last_logged"] == date(2026, 8, 12)
    assert out["gap_days"] == 40 and out["restarted"] is True


def test_consecutive_days_accumulate():
    days = [date(2026, 9, 19), date(2026, 9, 20), date(2026, 9, 21)]
    out = sheet.streak_and_day(days, date(2026, 9, 22))
    assert out["streak"] == 4 and out["gap_days"] == 0 and out["restarted"] is False


def test_future_days_never_count():
    out = sheet.streak_and_day([date(2026, 9, 25)], date(2026, 9, 22))
    assert out["day_number"] == 1 and out["streak"] == 1 and out["last_logged"] is None


# ------------------------------------------------------------------ merging
def test_measured_values_win_and_manual_cells_survive(log):
    merged = sheet.merge_row(log, date(2026, 8, 3), {"Cold Emails Sent": 300})
    assert merged["write"] == {"Cold Emails Sent": 300}
    assert merged["render"]["Cold Emails Sent"] == 300
    assert merged["render"]["Upwork Proposals"] == 7     # what Lorenzo typed that day
    assert "Upwork Proposals" not in merged["write"]     # and we do not rewrite it


def test_a_measured_metric_we_could_not_read_renders_na(log):
    merged = sheet.merge_row(log, DAY, {})
    assert merged["render"]["Cold Emails Sent"] is None   # n/a, not 0
    assert merged["render"]["Calls Booked"] is None
    assert merged["write"] == {}


def test_a_measured_zero_never_overwrites_a_number_lorenzo_typed(log):
    """The engine books nothing in shadow, so its "calls booked today" is 0
    every evening. On a day he had typed 2 booked calls and 3 positives, the run
    wrote 0 over both and the post read "0 booked - 2 held - 0 booked all-time"."""
    values = json.loads(json.dumps(FakeSheet().values))
    header = values[0]
    row = values[1]                                   # 2026-08-03, a logged day
    row[header.index("Calls Booked")] = 2
    row[header.index("Positive Replies")] = 3
    log2 = sheet.read_daily_log(FakeSheet(values))
    merged = sheet.merge_row(log2, date(2026, 8, 3),
                             {"Calls Booked": 0, "Positive Replies": 0, "Cold Emails Sent": 300})
    assert "Calls Booked" not in merged["write"]
    assert "Positive Replies" not in merged["write"]
    assert merged["render"]["Calls Booked"] == 2 and merged["render"]["Positive Replies"] == 3
    assert sorted(merged["kept"]) == ["Calls Booked", "Positive Replies"]
    assert merged["write"]["Cold Emails Sent"] == 300      # a real measurement still wins


def test_a_measured_zero_still_fills_an_empty_cell(log):
    merged = sheet.merge_row(log, DAY, {"Calls Booked": 0})
    assert merged["write"]["Calls Booked"] == 0
    assert merged["kept"] == []


def test_a_nonzero_measurement_overwrites_whatever_is_in_the_cell(log):
    merged = sheet.merge_row(log, date(2026, 8, 3), {"Upwork Proposals": 9})
    assert merged["write"]["Upwork Proposals"] == 9       # the cell held 7


# ------------------------------------------------------- an unreadable log
def test_a_text_date_column_is_reported_not_read_as_an_empty_log():
    """If column A ever comes back as display text ("Tue, Sep 22" carries no
    year), every row parses to None and the log looks identical to a first run:
    the job would publish "Day 1, 1 day streak" on day five with n/a all-time
    totals and nothing in the notes saying the sheet was unreadable."""
    values = json.loads(json.dumps(FakeSheet().values))
    for row in values[1:]:
        row[0] = "Tue, Sep 22"
    with pytest.raises(RuntimeError) as excinfo:
        sheet.read_daily_log(FakeSheet(values))
    assert "no readable date in column A" in str(excinfo.value)


def test_a_header_only_daily_log_is_still_a_valid_empty_log():
    """A genuinely empty log must keep working: it is the first-run case."""
    with open(FIXTURES / "daily_log_2026-09-22.json", "r", encoding="utf-8") as fh:
        header = json.load(fh)[0]
    log = sheet.read_daily_log(FakeSheet([header]))
    assert log.logged_days() == [] and log.unparsed_dates == 0


def test_a_manual_flow_with_an_empty_cell_renders_zero_but_is_not_written(log):
    merged = sheet.merge_row(log, DAY, {})
    assert merged["render"]["DMs Sent"] == 0.0
    assert merged["render"]["Community Posts"] == 0.0
    assert "DMs Sent" not in merged["write"]


def test_a_stock_metric_carries_the_last_restated_value_forward(log):
    values = json.loads(json.dumps(FakeSheet().values))
    header = values[0]
    col = header.index("Total MRR")
    values[11][col] = 4000           # row 12 == 2026-08-13, after the last logged day
    log2 = sheet.read_daily_log(FakeSheet(values))
    merged = sheet.merge_row(log2, DAY, {})
    assert merged["render"]["Total MRR"] == 4000


def test_all_time_totals_sum_flows_and_take_the_latest_stock(log):
    totals = sheet.all_time_totals(log, DAY, today={"Cold Emails Sent": 300})
    assert totals["Upwork Proposals"] == 7 + 3 + 8 + 2
    assert totals["Cold Emails Sent"] == 300           # today's measured value included
    assert totals["Active Clients"] == 0


# ------------------------------------------------------------------- write
def test_write_is_shadowed_and_the_sheet_is_never_touched(log, tmp_env, shadow_mode):
    io = FakeSheet()
    out = sheet.write_day(DAY, {"Cold Emails Sent": 300}, log.existing(DAY), log.row_for(DAY), io=io)
    assert out["ok"] and out["shadow"] is True
    assert io.updates == []
    records = [r for r in read_shadow_log() if r["action"] == "daily_metrics_row"]
    assert records and records[-1]["system"] == "google_sheets"
    assert records[-1]["payload"]["row"] == 52
    assert records[-1]["payload"]["range"] == "B52:Y52"


def test_live_write_lands_in_the_dated_row_with_blanks_for_what_we_did_not_measure(log, tmp_env, live_mode):
    io = FakeSheet()
    out = sheet.write_day(DAY, {"Cold Emails Sent": 300, "Replies": 2}, log.existing(DAY),
                          log.row_for(DAY), io=io)
    assert out["ok"] and out["shadow"] is False
    (rng, values), = io.updates
    assert rng == "B52:Y52"
    row = values[0]
    names = [n for n, _k in sheet.metric_schema()]
    assert row[names.index("Cold Emails Sent")] == 300
    assert row[names.index("Replies")] == 2
    assert row[names.index("DMs Sent")] == ""     # untouched, so the day is not faked
    assert len(row) == len(names) + 1             # metrics plus Notes, never "Logged"


def test_a_date_outside_the_prefilled_rows_is_refused(log, tmp_env, shadow_mode):
    out = sheet.write_day(date(2030, 1, 1), {"Cold Emails Sent": 1}, {}, None, io=FakeSheet())
    assert out["ok"] is False and out["reason"] == "no_row_for_date"


def test_a_failed_live_write_is_reported_not_raised(log, tmp_env, live_mode):
    class Boom(FakeSheet):
        def update(self, range_name, values):
            raise RuntimeError("quota")

    out = sheet.write_day(DAY, {"Cold Emails Sent": 300}, log.existing(DAY), log.row_for(DAY), io=Boom())
    assert out["ok"] is False and out["reason"] == "write_failed" and "quota" in out["error"]


# ------------------------------------------------------------- credentials
def test_the_placeholder_service_account_is_rejected(monkeypatch, tmp_path):
    """GOOGLE_CREDENTIALS_JSON in .env is
    {"type": "service_account", "paste_your_json_here": "..."} - valid JSON and
    useless. Accepting it fails later inside google.auth with MalformedError.

    The credentials.json fallback is pointed at empty temp dirs, so the test
    never reaches the repo's real credentials file."""
    base = tmp_path / "base"
    root = tmp_path / "root"
    base.mkdir()
    root.mkdir()
    monkeypatch.setattr(sheet, "BASE_DIR", base)
    monkeypatch.setattr(sheet, "ROOT_DIR", root)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON",
                       '{"type": "service_account", "paste_your_json_here": "..."}')
    info = sheet.service_account_info()
    assert info is None
