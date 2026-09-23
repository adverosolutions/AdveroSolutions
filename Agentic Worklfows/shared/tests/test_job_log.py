import csv
import json

from shared import job_log


def test_log_run_writes_header_and_rows(tmp_env):
    row = job_log.log_run("reply_engine.poll", "ok", {"replies": 3, "when": "2026-09-21"})
    assert row["job"] == "reply_engine.poll" and row["status"] == "ok" and row["mode"] == "shadow"
    job_log.log_run("reply_engine.poll", "error", {"err": "boom"})
    path = job_log.job_log_path()
    assert path == tmp_env / "job_log.csv"
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["job"] for r in rows] == ["reply_engine.poll", "reply_engine.poll"]
    assert rows[0]["status"] == "ok"
    assert json.loads(rows[0]["details"]) == {"replies": 3, "when": "2026-09-21"}
    assert rows[1]["mode"] == "shadow"
    assert rows[0]["ts_utc"].endswith("+00:00")


def test_log_run_creates_missing_directories(tmp_env, monkeypatch):
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_env / "deep" / "er" / "job_log.csv"))
    assert job_log.log_run("x", "ok", {}) is not None
    assert (tmp_env / "deep" / "er" / "job_log.csv").exists()


def test_shadow_appends_jsonl(tmp_env):
    job_log.shadow("instantly", "reply_to_email", {"reply_to_uuid": "u1"})
    job_log.shadow("ghl", "upsert_contact", {"email": "a@b.co"})
    path = job_log.shadow_log_path()
    assert path == tmp_env / "shadow_log.jsonl"
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["system"] == "instantly" and first["action"] == "reply_to_email"
    assert first["payload"] == {"reply_to_uuid": "u1"} and first["mode"] == "shadow"
    assert job_log.read_shadow_log()[1]["system"] == "ghl"


def test_never_raises_on_unwritable_paths(tmp_env, monkeypatch, caplog):
    # a directory where the file should be -> open() fails -> warning, not exception
    (tmp_env / "job_log.csv").mkdir()
    (tmp_env / "shadow_log.jsonl").mkdir()
    with caplog.at_level("WARNING"):
        assert job_log.log_run("x", "ok", {}) is None
        assert job_log.shadow("s", "a", {}) is None
    assert "write failed" in caplog.text


def test_details_with_non_json_values(tmp_env):
    from datetime import datetime

    row = job_log.log_run("x", "ok", {"at": datetime(2026, 9, 21, 10, 0), "obj": object()})
    parsed = json.loads(row["details"])
    assert parsed["at"] == "2026-09-21T10:00:00"


def test_sheet_append_skipped_without_sheet_id(tmp_env, monkeypatch):
    monkeypatch.delenv("JOB_LOG_SHEET_ID", raising=False)
    assert job_log._append_sheet({"ts_utc": "", "job": "", "status": "", "mode": "", "details": ""}) is False


def test_sheet_append_never_raises_without_credentials(tmp_env, monkeypatch, caplog, live_mode):
    monkeypatch.setenv("JOB_LOG_SHEET_ID", "sheet-123")
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    monkeypatch.setattr(job_log, "_service_account_info", lambda: None)
    with caplog.at_level("WARNING"):
        row = job_log.log_run("x", "ok", {})
    assert row is not None  # CSV still written
    assert "no service-account credentials" in caplog.text


def test_sheet_append_is_recorded_not_performed_in_shadow(tmp_env, monkeypatch, shadow_mode):
    """The sheet mirror is the one network write in shared that used to ignore
    MODE, so a shadow dry run appended rows to a real spreadsheet."""
    monkeypatch.setenv("JOB_LOG_SHEET_ID", "sheet-123")

    def boom():
        raise AssertionError("shadow mode must not authorise a Google client")

    monkeypatch.setattr(job_log, "_service_account_info", boom)
    row = job_log.log_run("reply_engine.poll", "ok", {"replies": 1})
    assert row is not None  # local CSV still written
    intents = [r for r in job_log.read_shadow_log() if r["system"] == "google_sheets"]
    assert len(intents) == 1
    assert intents[0]["action"] == "job_log_append"
    assert intents[0]["payload"]["sheet_id"] == "sheet-123"
    assert intents[0]["payload"]["row"]["job"] == "reply_engine.poll"


def test_use_scratch_logs_redirects_both_logs(tmp_env, monkeypatch):
    """Every --dry-run and every evidence run calls this. Before it, ad-hoc
    evidence scripts wrote 48 mode=live rows into the same .tmp/job_log.csv
    that runbooks/deployment.md names as the shadow-watch gate, so after 48
    hours nobody could tell a test row from a real one."""
    monkeypatch.delenv("JOB_LOG_PATH", raising=False)
    monkeypatch.delenv("SHADOW_LOG_PATH", raising=False)
    real_log = job_log.job_log_path()
    scratch = job_log.use_scratch_logs("unit-demo")

    assert job_log.job_log_path() != real_log
    assert str(job_log.job_log_path()).startswith(str(scratch))
    assert str(job_log.shadow_log_path()).startswith(str(scratch))

    job_log.log_run("demo", "ok", {"n": 1})
    job_log.shadow("ghl", "send_message", {"contact_id": "x"})
    assert job_log.job_log_path().exists() and job_log.shadow_log_path().exists()
    assert not real_log.exists(), "a scratch run wrote into the real job log"
