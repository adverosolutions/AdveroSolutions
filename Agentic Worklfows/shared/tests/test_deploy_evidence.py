"""GOL-2 and R5: what a deployed container leaves behind, and where.

* shared.store derives the Modal Dict from the effective mode, so the shadow
  watch and the live run never share state;
* shared.job_log mirrors every Job_Log row and shadow record into that store
  and onto stdout when RUNTIME=modal (and only then);
* shared.settings records live-write intents and results as live_write_* rows
  the deployed gate can count.
"""
import csv
import json

import pytest

from shared import job_log, settings, store as store_mod


@pytest.fixture
def modal_runtime(tmp_env, monkeypatch):
    """RUNTIME=modal with the deployed EVIDENCE store swapped for a local file.
    The engine store is a second file the mirror must never touch."""
    monkeypatch.setenv("RUNTIME", "modal")
    local = store_mod.JsonFileStore(tmp_env / "deployed_obs.json")
    engine = store_mod.JsonFileStore(tmp_env / "deployed_engine.json")
    monkeypatch.setattr(store_mod, "get_obs_store", lambda force_new=False: local)
    monkeypatch.setattr(store_mod, "get_store", lambda force_new=False: engine)
    local.engine = engine
    return local


# ------------------------------------------------------------ R5: store names
def test_the_dict_name_follows_the_effective_mode(monkeypatch):
    monkeypatch.setenv("RUNTIME", "modal")
    monkeypatch.delenv("MODAL_DICT_NAME", raising=False)
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    assert store_mod._store_target() == ("modal", "advero-reply-engine-store-shadow")
    # MODE=live without the flag writes nothing live, so it stays on the shadow Dict
    monkeypatch.setenv("MODE", "live")
    assert store_mod._store_target() == ("modal", "advero-reply-engine-store-shadow")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert store_mod._store_target() == ("modal", "advero-reply-engine-store-live")
    # an explicit name still wins (tests and one-off tools)
    monkeypatch.setenv("MODAL_DICT_NAME", "advero-test")
    assert store_mod._store_target() == ("modal", "advero-test")


def test_modal_dict_name_refuses_anything_but_shadow_or_live():
    assert store_mod.modal_dict_name("shadow") != store_mod.modal_dict_name("live")
    with pytest.raises(ValueError):
        store_mod.modal_dict_name("prod")


def test_evidence_has_its_own_dict_per_mode(monkeypatch):
    """Review item 8: four Dicts, never shared between engine and evidence."""
    names = set([store_mod.modal_dict_name("shadow"), store_mod.modal_dict_name("live"),
                 store_mod.obs_dict_name("shadow"), store_mod.obs_dict_name("live")])
    assert len(names) == 4
    with pytest.raises(ValueError):
        store_mod.obs_dict_name("prod")


def test_the_local_store_is_unchanged(tmp_env, monkeypatch):
    monkeypatch.setenv("RUNTIME", "local")
    kind, path = store_mod._store_target()
    assert kind == "json" and path.endswith("store.json")


# ------------------------------------------- GOL-2: the deployed mirror
def _obs(local, prefix):
    return [local.get(k) for k in local.keys(prefix)]


def test_a_job_log_row_is_mirrored_to_the_store_and_stdout_on_modal(modal_runtime, capsys):
    job_log.log_run("modal.poller", "tick", {"result_type": "dict"})
    rows = _obs(modal_runtime, job_log.OBS_JOB_PREFIX)
    assert len(rows) == 1
    assert rows[0]["job"] == "modal.poller" and rows[0]["status"] == "tick" and rows[0]["mode"] == "shadow"
    assert rows[0]["details"] == {"result_type": "dict"}
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if l.startswith(job_log.RECORD_TAG + " ")]
    assert len(line) == 1
    record = json.loads(line[0][len(job_log.RECORD_TAG) + 1:])
    assert record["kind"] == "job" and record["status"] == "tick"
    # the laptop CSV is still written too
    with open(str(job_log.job_log_path()), "r", encoding="utf-8") as fh:
        assert [r["job"] for r in csv.DictReader(fh)] == ["modal.poller"]


def test_a_shadow_record_is_mirrored_to_the_store(modal_runtime):
    job_log.shadow("instantly", "reply", {"to": "lead@x.test"})
    rows = _obs(modal_runtime, job_log.OBS_SHADOW_PREFIX)
    assert len(rows) == 1
    assert rows[0]["system"] == "instantly" and rows[0]["action"] == "reply"
    assert rows[0]["payload"] == {"to": "lead@x.test"}


def test_the_mirror_never_writes_the_engine_store(modal_runtime):
    job_log.log_run("modal.poller", "tick", {})
    job_log.shadow("instantly", "reply", {"to": "lead@x.test"})
    assert modal_runtime.engine.keys("") == []
    assert len(modal_runtime.keys("obs:")) == 2


def test_every_record_gets_its_own_key(modal_runtime):
    for _ in range(5):
        job_log.log_run("modal.poller", "tick", {})
    assert len(modal_runtime.keys(job_log.OBS_JOB_PREFIX)) == 5


def test_an_oversized_payload_is_kept_as_a_marked_preview(modal_runtime):
    job_log.shadow("instantly", "reply", {"body": "x" * (job_log.OBS_MAX_CHARS * 2)})
    row = _obs(modal_runtime, job_log.OBS_SHADOW_PREFIX)[0]
    assert row["truncated"] is True and "payload" not in row
    assert len(row["preview"]) == job_log.OBS_PREVIEW_CHARS
    assert row["system"] == "instantly"


def test_nothing_is_mirrored_off_modal(tmp_env, monkeypatch, capsys):
    monkeypatch.setenv("RUNTIME", "local")
    touched = []
    monkeypatch.setattr(store_mod, "get_store", lambda force_new=False: touched.append(1))
    job_log.log_run("x", "tick", {})
    job_log.shadow("instantly", "reply", {})
    assert touched == []
    assert job_log.RECORD_TAG not in capsys.readouterr().out


def test_a_store_outage_never_breaks_a_tick(tmp_env, monkeypatch):
    monkeypatch.setenv("RUNTIME", "modal")

    def boom(force_new=False):
        raise RuntimeError("modal down")

    monkeypatch.setattr(store_mod, "get_store", boom)
    assert job_log.log_run("modal.poller", "tick", {}) is not None
    assert job_log.shadow("instantly", "reply", {}) is not None


# ------------------------------------------- live-write rows the gate counts
def test_a_live_write_intent_reaches_the_deployed_store(modal_runtime, live_mode):
    record = settings.guard_write("instantly", "reply", {"to": "lead@x.test"})
    assert record["shadow"] is False
    rows = _obs(modal_runtime, job_log.OBS_JOB_PREFIX)
    assert [(r["job"], r["status"], r["mode"]) for r in rows] == [
        ("instantly.reply", settings.LIVE_WRITE_INTENT, "live")]


def test_live_write_results_are_recorded_in_live_only(modal_runtime, monkeypatch):
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    assert settings.record_live_write_result("instantly", "reply", True) is None
    assert _obs(modal_runtime, job_log.OBS_JOB_PREFIX) == []

    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    settings.record_live_write_result("instantly", "reply", True, {"status_code": 200})
    settings.record_live_write_result("ghl", "upsert", False, {"error": "500"})
    statuses = sorted((r["job"], r["status"]) for r in _obs(modal_runtime, job_log.OBS_JOB_PREFIX))
    assert statuses == [("ghl.upsert", "live_write_failed"), ("instantly.reply", "live_write_ok")]


def test_the_shadow_path_of_guard_write_is_unchanged(modal_runtime, shadow_mode):
    record = settings.guard_write("instantly", "reply", {"to": "lead@x.test"})
    assert record["shadow"] is True
    assert _obs(modal_runtime, job_log.OBS_JOB_PREFIX) == []
    assert len(_obs(modal_runtime, job_log.OBS_SHADOW_PREFIX)) == 1


def test_the_sheet_append_intent_is_not_mirrored(modal_runtime, monkeypatch):
    """With JOB_LOG_SHEET_ID set, every shadow Job_Log row also records a
    sheet-append intent. It duplicates the row, so it stays off the store."""
    monkeypatch.setenv("JOB_LOG_SHEET_ID", "sheet-fake")
    monkeypatch.setenv("MODE", "shadow")
    job_log.log_run("modal.poller", "tick", {})
    assert len(_obs(modal_runtime, job_log.OBS_JOB_PREFIX)) == 1
    assert _obs(modal_runtime, job_log.OBS_SHADOW_PREFIX) == []
    assert [r["action"] for r in job_log.read_shadow_log()] == ["job_log_append"]


# ---------------------------------------------- review item 4: redaction
URL = "https://ws--advero-reply-engine-web.modal.run/approve/APPROVALID.SIGNATUREPART"


def _push_card(monkeypatch):
    from shared import notify as notify_mod

    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "test-topic-not-real")
    monkeypatch.setenv("NOTIFY_SHADOW_SEND", "1")
    for key in ("GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NOTIFY_EMAIL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(notify_mod, "_send_ntfy", lambda *a, **k: {"ok": True, "status": 200, "headers": {},
                                                                   "authenticated": True})
    notify_mod.notify("Positive reply: Ann", "Draft: Hi Ann. Approve here: %s" % URL, priority="high",
                      actions=[("Approve", URL), ("Veto", URL.replace("approve", "veto"))], click=URL)


@pytest.mark.parametrize("mode_fixture", ["shadow_mode", "live_mode"])
def test_an_approval_card_leaves_no_signed_link_in_logs_or_the_store(modal_runtime, monkeypatch, capsys,
                                                                     request, mode_fixture):
    request.getfixturevalue(mode_fixture)
    _push_card(monkeypatch)
    out = capsys.readouterr().out
    records = [l for l in out.splitlines() if l.startswith(job_log.RECORD_TAG + " ")]
    assert records, "the card left no evidence at all"
    assert "APPROVALID" not in out and "SIGNATURE" not in out
    stored = json.dumps([modal_runtime.get(k) for k in modal_runtime.keys("obs:")])
    assert "APPROVALID" not in stored and "SIGNATURE" not in stored
    assert "modal.run/" not in stored
    # stdout carries only who/what/when, never a payload
    for line in records:
        body = json.loads(line[len(job_log.RECORD_TAG) + 1:])
        assert set(body) <= set(job_log.STDOUT_KEYS)


def test_the_live_intent_row_is_redacted_on_the_laptop_csv_and_the_sheet_path(tmp_env, live_mode, monkeypatch):
    record = settings.guard_write("notify", "push_email", {"message": "tap %s" % URL, "actions": [URL],
                                                           "click": URL, "title": "t"})
    assert record["shadow"] is False and record["payload"]["click"] == URL     # the caller still gets it
    with open(str(job_log.job_log_path()), "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "APPROVALID" not in text
    assert "<redacted>" in text and "<redacted-url ws--advero-reply-engine-web.modal.run>" in text


def test_redact_keeps_other_urls_and_catches_the_base_url_host(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://engine.example.test")
    value = {"a": "see https://engine.example.test/approve/X.Y and https://instantly.ai/app",
             "nested": [{"Click": "anything"}, "https://other--x.modal.run/veto/Q"]}
    out = job_log.redact(value)
    assert out["a"] == "see <redacted-url engine.example.test> and https://instantly.ai/app"
    assert out["nested"][0] == {"Click": "<redacted>"}
    assert out["nested"][1] == "<redacted-url other--x.modal.run>"


def test_the_job_mirror_keeps_only_what_the_gate_reads(modal_runtime):
    job_log.log_run("reply_engine.approval", "push_failed",
                    {"lead": "ann@x.test", "error": "x" * 900, "reason": "no topic", "body": "Hi Ann"})
    row = [modal_runtime.get(k) for k in modal_runtime.keys(job_log.OBS_JOB_PREFIX)][0]
    assert set(row["details"]) == {"error", "reason"}
    assert len(row["details"]["error"]) == job_log.MIRROR_TEXT_CHARS
    assert "ann@x.test" not in json.dumps(row)
