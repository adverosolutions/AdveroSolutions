"""R5 / GOL-4: the shadow watch and the live run never share a store, and the
cutover step hands the watch's replies to Lorenzo, seeds the live poller's
cursor and refuses anything it cannot do cleanly. Stores are fakes."""
from datetime import datetime, timezone

import pytest

from changesets.deploy import cutover
from changesets.tests.deploy_fakes import FakeModalStore
from shared import store as store_mod

NOW = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
CURSOR = {"last_email_id": "e-105", "last_timestamp": "2026-09-25T14:40:00.000Z"}


def _lead(email, campaign, name, label, email_id, at):
    return {
        "lead_email": email, "campaign_id": campaign, "campaign_key": "cleaning_reactivation",
        "first_name": name, "company": name + " Co", "status": "replied",
        "drafts": [{"subject": "Re: hi"}] if label == "interested" else [],
        "approvals": ["tok-1"] if label == "interested" else [],
        "last_subject": "Re: quick question",
        "history": [{"at": at, "event": "inbound", "email_id": email_id, "label": label, "source": "poller"}],
    }


def _shadow_obs(poller_row_ts="2026-09-25T14:55:00+00:00", poller_status="tick"):
    """The shadow EVIDENCE Dict: Job_Log rows live here, not in the engine's."""
    return FakeModalStore({
        "obs:job:20260925145500:aaa": {"ts_utc": poller_row_ts, "job": "modal.poller",
                                       "status": poller_status, "mode": "shadow"},
        "obs:job:20260925140000:bbb": {"ts_utc": "2026-09-25T14:00:00+00:00", "job": "modal.poller",
                                       "status": "tick", "mode": "shadow"},
    }, read_only=True)


def _shadow(cursor=CURSOR):
    data = {
        "poller:seen": {
            "e-100": "2026-09-24T15:00:00.000Z",
            "e-101": "2026-09-24T16:00:00.000Z",
            "e-102": "2026-09-24T17:00:00.000Z",    # an auto-reply: seen, never a lead record
            "e-105": "2026-09-25T14:40:00.000Z",    # the cursor row itself
        },
        "poller:failed": {"e-103": {"timestamp_created": "2026-09-25T09:00:00.000Z", "attempts": 3,
                                    "error": "classifier timeout"},
                          "e-200": {"timestamp_created": "2026-09-25T14:50:00.000Z", "attempts": 1,
                                    "error": "late"}},
        "lead:c1:ann@x.test": _lead("ann@x.test", "c1", "Ann", "interested", "e-100", "2026-09-24T15:05:00+00:00"),
        "lead:c1:bob@x.test": _lead("bob@x.test", "c1", "Bob", "not_interested", "e-101", "2026-09-24T16:05:00+00:00"),
        "lead:c1:cy@x.test": _lead("cy@x.test", "c1", "Cy", "question", "e-105", "2026-09-25T14:45:00+00:00"),
    }
    if cursor is not None:
        data["poller:cursor"] = dict(cursor)
    return FakeModalStore(data, read_only=True)


def _missing():
    return FakeModalStore(missing=True, read_only=True)


def _run(tmp_path, argv, shadow=None, live=None, confirm=lambda w, p: True, shadow_obs=None, live_obs=None,
         writer=None, words=None):
    shadow = shadow if shadow is not None else _shadow()
    live = live if live is not None else _missing()
    writer = writer if writer is not None else FakeModalStore()
    words = words if words is not None else []

    def _confirm(word, prompt):
        words.append(word)
        return confirm(word, prompt)

    code = cutover.main(argv, shadow_store=shadow, live_store=live, open_live_for_write=lambda: writer,
                        confirm=_confirm, now=NOW, handoff_dir=str(tmp_path / "cutover"),
                        shadow_obs=shadow_obs if shadow_obs is not None else _shadow_obs(),
                        live_obs=live_obs if live_obs is not None else _missing())
    return code, writer


def _plan(**kw):
    return cutover.plan_cutover(_shadow(), _shadow_obs(), _missing(), NOW, **kw)


# ------------------------------------------------------------------ dry-run
def test_the_dry_run_writes_no_store_and_lists_the_watch_replies(tmp_path, tmp_env, capsys):
    code, writer = _run(tmp_path, [])
    assert code == 0
    assert writer.writes == []                               # nothing written to the live Dict
    out = capsys.readouterr().out
    assert "Dry run. Nothing was written" in out
    files = sorted(p.name for p in (tmp_path / "cutover").iterdir())
    assert files == ["handoff_20260925T150000Z.dryrun.json", "handoff_20260925T150000Z.dryrun.md"]
    md = (tmp_path / "cutover" / "handoff_20260925T150000Z.dryrun.md").read_text(encoding="utf-8")
    for email in ("ann@x.test", "bob@x.test", "cy@x.test"):
        assert email in md
    assert "e-103" in md                                      # failed in shadow, before the cutover point
    assert "e-200" not in md                                  # after the point: the live poller takes it


def test_the_handoff_partitions_replies_at_the_shadow_high_water_mark():
    plan = _plan()
    ids = [r["email_id"] for r in plan["handoff"]["replies"]]
    assert ids == ["e-100", "e-101", "e-105"]
    assert [r["email_id"] for r in plan["handoff"]["failed_in_shadow"]] == ["e-103"]
    # e-102 was seen but no lead record was written: listed by id, not just counted
    assert plan["handoff"]["seen_without_lead_record"] == [{"email_id": "e-102",
                                                            "received_at": "2026-09-24T17:00:00.000Z"}]
    # the seed is the shadow cursor, so the live poller starts exactly after e-105
    seed = plan["seed_cursor"]
    assert (seed["last_email_id"], seed["last_timestamp"]) == ("e-105", "2026-09-25T14:40:00.000Z")
    ann = [r for r in plan["handoff"]["replies"] if r["email_id"] == "e-100"][0]
    assert ann["label"] == "interested" and ann["drafted_in_shadow"] is True
    assert ann["received_at"] == "2026-09-24T15:00:00.000Z"   # the reply's own time, not processing time


def test_watch_start_leaves_older_replies_out():
    start = datetime(2026, 9, 24, 15, 30, tzinfo=timezone.utc)
    plan = _plan(watch_start=start)
    assert [r["email_id"] for r in plan["handoff"]["replies"]] == ["e-101", "e-105"]


# ------------------------------------------------------------------ apply
def test_apply_seeds_the_cursor_then_writes_the_cutover_record_last(tmp_path, tmp_env):
    code, writer = _run(tmp_path, ["--apply"])
    assert code == 0
    assert [w for w in writer.writes] == [("set_if_absent", "poller:cursor"),
                                          ("set_if_absent", store_mod.CUTOVER_KEY)]
    cursor = writer.get("poller:cursor")
    assert cursor["last_email_id"] == "e-105" and cursor["last_timestamp"] == "2026-09-25T14:40:00.000Z"
    record = writer.get(store_mod.CUTOVER_KEY)
    assert record["handoff_replies"] == 3 and record["handoff_failed"] == 1
    assert record["shadow_store"] == "advero-reply-engine-store-shadow"
    assert (tmp_path / "cutover" / "handoff_20260925T150000Z.md").exists()


def test_apply_without_the_typed_word_writes_nothing(tmp_path, tmp_env):
    code, writer = _run(tmp_path, ["--apply"], confirm=lambda w, p: False)
    assert code == 1
    assert writer.writes == []


def test_apply_and_dry_run_together_are_refused(tmp_path, tmp_env):
    code, writer = _run(tmp_path, ["--apply", "--dry-run"])
    assert code == 2 and writer.writes == []


def test_the_seeded_cursor_stops_the_live_poller_at_the_cutover_point():
    """The live poller reads the seed with its own fetch loop: it must process
    only what came after the shadow high-water mark."""
    from services.reply_engine import poller

    class Instantly(object):
        def list_emails(self, **kwargs):
            return {"items": [
                {"id": "e-201", "timestamp_created": "2026-09-25T14:58:00.000Z", "campaign_id": "c1"},
                {"id": "e-200", "timestamp_created": "2026-09-25T14:50:00.000Z", "campaign_id": "c1"},
                {"id": "e-105", "timestamp_created": "2026-09-25T14:40:00.000Z", "campaign_id": "c1"},
                {"id": "e-101", "timestamp_created": "2026-09-24T16:00:00.000Z", "campaign_id": "c1"},
            ]}

    seed = _plan()["seed_cursor"]
    fetched = poller.fetch_new_replies(Instantly(), seed, ["c1"], {})
    assert [i["id"] for i in fetched["items"]] == ["e-201", "e-200"]


# ---------------------------------------------------------------- refusals
def test_a_live_store_that_is_not_clean_is_refused(tmp_path, tmp_env, capsys):
    live = FakeModalStore({"lead:c1:x@y.test": {}}, read_only=True)
    code, writer = _run(tmp_path, ["--apply"], live=live)
    assert code == 1 and writer.writes == []
    assert "not clean" in capsys.readouterr().out


def test_a_second_cutover_is_refused(tmp_path, tmp_env, capsys):
    live = FakeModalStore({store_mod.CUTOVER_KEY: {"cutover_at": "2026-09-25T15:00:00+00:00"},
                           "poller:cursor": dict(CURSOR)}, read_only=True)
    code, writer = _run(tmp_path, ["--apply"], live=live)
    assert code == 1 and writer.writes == []
    assert "already cut over" in capsys.readouterr().out


@pytest.mark.parametrize("shadow,obs,reason", [
    (lambda: _shadow(cursor=None), _shadow_obs, "no complete poller:cursor"),
    (_shadow, lambda: _shadow_obs(poller_status="error"), "not a healthy tick"),
    (_shadow, lambda: _shadow_obs(poller_row_ts="2026-09-25T13:00:00+00:00"), "must be under"),
])
def test_an_unhealthy_shadow_poller_is_refused(tmp_path, tmp_env, capsys, shadow, obs, reason):
    code, writer = _run(tmp_path, ["--apply"], shadow=shadow(), shadow_obs=obs())
    assert code == 1 and writer.writes == []
    assert reason in capsys.readouterr().out


def test_an_unreadable_live_store_is_refused_not_guessed(tmp_path, tmp_env):
    class Broken(object):
        class _D(object):
            def keys(self):
                raise RuntimeError("network down")

        _dict = _D()

    code, writer = _run(tmp_path, ["--apply"], live=Broken())
    assert code == 1 and writer.writes == []


def test_the_handoff_lists_the_ids_seen_without_a_lead_record(tmp_path, tmp_env):
    code, _writer = _run(tmp_path, [])
    assert code == 0
    md = (tmp_path / "cutover" / "handoff_20260925T150000Z.dryrun.md").read_text(encoding="utf-8")
    assert "Seen by the shadow poller with no lead record: 1" in md
    assert "`e-102`" in md


def test_an_empty_watch_start_is_refused(tmp_path, tmp_env, capsys):
    """What "$(cat .tmp/deploy/handoff_start.txt)" gives when the file is missing."""
    code, writer = _run(tmp_path, ["--watch-start", "", "--apply"])
    assert code == 2 and writer.writes == []


# ------------------------------------------- review item 3: a live deploy made first
def test_a_live_deploy_made_before_the_cutover_does_not_block_it(tmp_path, tmp_env, live_mode, monkeypatch):
    """Drives the REAL refusal and notify path, then cuts over against exactly
    what it left behind in the live engine store and the live evidence store."""
    from services.reply_engine import modal_app
    from shared import notify as notify_mod
    from shared import store as store_mod

    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "test-topic-not-real")
    for key in ("GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NOTIFY_EMAIL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(notify_mod, "_send_ntfy", lambda *a, **k: {"ok": True, "status": 200, "headers": {},
                                                                   "authenticated": False})
    monkeypatch.setenv("RUNTIME", "modal")                          # the evidence mirror is on
    engine = store_mod.JsonFileStore(tmp_env / "live_engine.json")
    obs = store_mod.JsonFileStore(tmp_env / "live_obs.json")
    monkeypatch.setattr(store_mod, "get_store", lambda force_new=False: engine)
    monkeypatch.setattr(store_mod, "get_obs_store", lambda force_new=False: obs)
    for _ in range(2):
        with pytest.raises(modal_app.CutoverMissing):
            modal_app._refuse_without_cutover("poller")
    monkeypatch.setenv("RUNTIME", "local")
    obs_rows = [obs.get(k) for k in obs.keys("obs:job:")]
    assert sorted((r["job"], r["status"]) for r in obs_rows) == [
        ("modal.poller", "refused"), ("modal.poller", "refused"), ("notify.push_email", "live_write_intent")]
    live = FakeModalStore(dict((k, engine.get(k)) for k in engine.keys("")), read_only=True)
    live_obs = FakeModalStore(dict((k, obs.get(k)) for k in obs.keys("")), read_only=True)
    code, writer = _run(tmp_path, ["--apply"], live=live, live_obs=live_obs)
    assert code == 0
    assert writer.writes == [("set_if_absent", "poller:cursor"), ("set_if_absent", store_mod.CUTOVER_KEY)]


# ----------------------------------------------------- reset, redo, rollback seed
def _cut_over_live():
    return FakeModalStore({store_mod.CUTOVER_KEY: {"cutover_at": "2026-09-25T10:00:00+00:00"},
                           store_mod.CUTOVER_ACCEPTED_KEY: None,
                           "poller:cursor": {"last_email_id": "e-050", "last_timestamp": "2026-09-25T09:00:00.000Z"}},
                          read_only=True)


def _live_obs(*rows):
    return FakeModalStore(dict(("obs:job:2026092510%04d:x" % i, r) for i, r in enumerate(rows)), read_only=True)


NOTIFY_INTENT = {"ts_utc": "2026-09-25T10:05:00+00:00", "job": "notify.push_email",
                 "status": "live_write_intent", "mode": "live"}


def test_reset_dry_run_lists_the_keys_and_writes_nothing(tmp_path, tmp_env, capsys):
    code, writer = _run(tmp_path, ["--reset"], live=_cut_over_live(), live_obs=_live_obs(NOTIFY_INTENT))
    assert code == 0 and writer.writes == []
    out = capsys.readouterr().out
    assert "3 key(s)" in out and "Dry run" in out


def test_reset_apply_needs_the_typed_word_and_deletes_every_live_key(tmp_path, tmp_env):
    words = []
    code, writer = _run(tmp_path, ["--reset", "--apply"], live=_cut_over_live(),
                        live_obs=_live_obs(NOTIFY_INTENT), words=words)
    assert code == 0 and words == ["RESET"]
    assert sorted(w for w in writer.writes) == sorted(
        [("delete", store_mod.CUTOVER_KEY), ("delete", store_mod.CUTOVER_ACCEPTED_KEY), ("delete", "poller:cursor")])
    code, writer = _run(tmp_path, ["--reset", "--apply"], live=_cut_over_live(), confirm=lambda w, p: False)
    assert code == 1 and writer.writes == []


@pytest.mark.parametrize("job,status", [("instantly.reply", "live_write_intent"),
                                        ("ghl.upsert_opportunity", "live_write_ok"),
                                        ("instantly.update_interest_status", "live_write_failed")])
def test_reset_and_redo_refuse_after_a_prospect_facing_write(tmp_path, tmp_env, capsys, job, status):
    row = {"ts_utc": "2026-09-25T10:06:00+00:00", "job": job, "status": status, "mode": "live"}
    for argv in (["--reset", "--apply"], ["--redo", "--apply"]):
        code, writer = _run(tmp_path, argv, live=_cut_over_live(), live_obs=_live_obs(NOTIFY_INTENT, row))
        assert code == 1 and writer.writes == []
        assert "prospect-facing write happened" in capsys.readouterr().out


def test_reset_refuses_when_the_live_evidence_cannot_be_read(tmp_path, tmp_env):
    class Broken(object):
        class _D(object):
            def items(self):
                raise RuntimeError("network down")

        _dict = _D()

    code, writer = _run(tmp_path, ["--reset", "--apply"], live=_cut_over_live(), live_obs=Broken())
    assert code == 1 and writer.writes == []


def test_redo_resets_then_cuts_over_under_one_typed_word(tmp_path, tmp_env):
    words = []
    code, writer = _run(tmp_path, ["--redo"], live=_cut_over_live())
    assert code == 0 and writer.writes == []                         # the dry run
    code, writer = _run(tmp_path, ["--redo", "--apply"], live=_cut_over_live(), words=words)
    assert code == 0 and words == ["REDO"]
    deletes = [w for w in writer.writes if w[0] == "delete"]
    assert len(deletes) == 3 and writer.writes[len(deletes):] == [
        ("set_if_absent", "poller:cursor"), ("set_if_absent", store_mod.CUTOVER_KEY)]
    assert writer.get("poller:cursor")["last_email_id"] == "e-105"   # the fresh shadow high-water mark


def test_seed_shadow_from_live_is_a_dry_run_then_a_typed_overwrite(tmp_path, tmp_env):
    shadow_writer = FakeModalStore()
    base = dict(shadow=_shadow(), live=_cut_over_live())
    code = cutover.main(["--seed-shadow-from-live"], shadow_store=base["shadow"], live_store=base["live"],
                        shadow_obs=_shadow_obs(), live_obs=_missing(), now=NOW,
                        open_shadow_for_write=lambda: shadow_writer, confirm=lambda w, p: True)
    assert code == 0 and shadow_writer.writes == []
    words = []
    code = cutover.main(["--seed-shadow-from-live", "--apply"], shadow_store=base["shadow"],
                        live_store=base["live"], shadow_obs=_shadow_obs(), live_obs=_missing(), now=NOW,
                        open_shadow_for_write=lambda: shadow_writer,
                        confirm=lambda w, p: words.append(w) or True)
    assert code == 0 and words == ["SEED"]
    assert shadow_writer.writes == [("set", "poller:cursor")]
    assert shadow_writer.get("poller:cursor")["last_email_id"] == "e-050"
