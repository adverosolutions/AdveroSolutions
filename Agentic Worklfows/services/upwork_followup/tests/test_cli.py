"""U4b CLI (jobs/upwork_followup.py). Invented clients only; the store and the
snapshot live under tmp_path; the tick itself is replaced where a test only
checks the CLI's routing, so nothing here can reach a model."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shared.store import JsonFileStore, get_store

from jobs import upwork_followup as cli
from services.upwork_followup import collect, sequence

NOW = datetime(2026, 9, 22, 13, 30, tzinfo=timezone.utc)
AS_OF = ["--as-of", "2026-09-22T13:30:00Z"]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "envelope_synthetic.json"


def room(rid, client, title):
    msgs = [{"id": rid + "_c", "side": "client", "at": "2026-09-18T15:00:00Z", "text": "positive: sounds good"},
            {"id": rid + "_f", "side": "freelancer", "at": "2026-09-21T15:00:00Z", "text": "Here is my plan."}]
    return {"room_id": rid, "client": client, "client_first_name": None, "room_type": "ONE_ON_ONE",
            "job_title": title, "job_id": None, "proposal_id": "prop_" + rid, "origin": "proposal",
            "contract": None, "offer_state": None, "messages": msgs, "last_side": "freelancer",
            "last_message_at": msgs[-1]["at"], "job_folder": None, "job": None}


ROOMS = [room("room_jb1", "Juniper Bakery Co", "Pipedrive invoice sync"),
         room("room_jf2", "Juniper Florist", "Shopify order sync"),
         room("room_ol3", "Orchard Lane Dental", "Appointment reminder texts")]


def snap(rooms):
    return {"generated_at": "2026-09-22T13:20:00Z", "source": "fixture",
            "sections": {"rooms": True, "messages": True, "proposals": True, "invitations": None,
                         "contracts": True, "offers": True},
            "truncated": False, "rooms": list(rooms), "contracted_rooms": []}


def classify(text, room_):
    return {"label": "positive", "confidence": 0.95, "follow_up_at": None}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("UPWORK_PIPELINE_DIR", str(tmp_path / "no_pipeline"))
    logs = []
    monkeypatch.setattr(cli, "log_run", lambda job, status, details=None: logs.append((job, status, details)))
    store = get_store(force_new=True)
    assert isinstance(store, JsonFileStore)
    path = tmp_path / "snapshot.json"
    collect.write_snapshot(snap(ROOMS), path)
    return {"store": store, "snapshot": str(path), "logs": logs, "tmp": tmp_path}


@pytest.fixture
def enrolled(env):
    sequence.run(env["store"], snap(ROOMS), NOW, classify)
    return env


def stage_of(store, rid):
    return store.get(sequence.thread_key(rid))["stage"]


# ------------------------------------------------------------------ --stage
def test_stage_unique_fragment_moves_the_job(enrolled, capsys):
    code = cli.main(["--stage", "orchard", "call_booked", "--snapshot", enrolled["snapshot"]] + AS_OF)
    out = capsys.readouterr().out
    assert code == 0
    assert stage_of(enrolled["store"], "room_ol3") == "call_booked"
    t = enrolled["store"].get(sequence.thread_key("room_ol3"))
    assert t["stage_set_by"] == "lorenzo"
    assert "Moved Orchard Lane Dental | Appointment reminder texts | room room_ol3" in out
    assert enrolled["logs"][-1][:2] == ("upwork_followup", "stage")


def test_stage_matches_the_job_title_case_insensitively(enrolled):
    assert cli.main(["--stage", "SHOPIFY", "lost", "--snapshot", enrolled["snapshot"]] + AS_OF) == 0
    assert stage_of(enrolled["store"], "room_jf2") == "lost"


def test_stage_by_exact_room_id(enrolled):
    assert cli.main(["--stage", "room_jb1", "proposal_sent", "--snapshot", enrolled["snapshot"]] + AS_OF) == 0
    assert stage_of(enrolled["store"], "room_jb1") == "proposal_sent"


def test_stage_several_matches_changes_nothing_and_lists_them(enrolled, capsys):
    code = cli.main(["--stage", "juniper", "lost", "--snapshot", enrolled["snapshot"]] + AS_OF)
    out = capsys.readouterr().out
    assert code == 1
    assert "matches 2 jobs. Nothing changed." in out
    assert "room room_jb1" in out and "room room_jf2" in out and "room_ol3" not in out
    assert stage_of(enrolled["store"], "room_jb1") == "new_reply"
    assert stage_of(enrolled["store"], "room_jf2") == "new_reply"


def test_stage_no_match_changes_nothing_and_lists_candidates(enrolled, capsys):
    code = cli.main(["--stage", "zeppelin", "lost", "--snapshot", enrolled["snapshot"]] + AS_OF)
    out = capsys.readouterr().out
    assert code == 1
    assert "No job matches 'zeppelin'. Nothing changed. Candidates:" in out
    for rid in ("room_jb1", "room_jf2", "room_ol3"):
        assert rid in out
        assert stage_of(enrolled["store"], rid) == "new_reply"


def test_stage_unknown_stage_is_refused(enrolled, capsys):
    assert cli.main(["--stage", "orchard", "maybe", "--snapshot", enrolled["snapshot"]] + AS_OF) == 2
    assert stage_of(enrolled["store"], "room_ol3") == "new_reply"


def test_stage_uses_the_saved_title_when_the_room_left_the_snapshot(enrolled, tmp_path):
    def fn(cur):
        cur = dict(cur)
        cur["job_title"] = "Appointment reminder texts"
        return cur
    enrolled["store"].mutate(sequence.thread_key("room_ol3"), fn)
    empty = tmp_path / "empty.json"
    collect.write_snapshot(snap([]), empty)
    assert cli.main(["--stage", "reminder", "won", "--snapshot", str(empty)] + AS_OF) == 0
    assert stage_of(enrolled["store"], "room_ol3") == "won"


# ------------------------------------------------------------------ stop / resume / enroll
def test_stop_and_resume_by_fragment(enrolled):
    assert cli.main(["--stop", "orchard", "--snapshot", enrolled["snapshot"]] + AS_OF) == 0
    assert enrolled["store"].get(sequence.thread_key("room_ol3"))["status"] == "stopped"
    assert cli.main(["--resume", "orchard", "--snapshot", enrolled["snapshot"]] + AS_OF) == 0
    assert enrolled["store"].get(sequence.thread_key("room_ol3"))["status"] == "active"


def test_enroll_needs_the_room_in_the_snapshot(env, capsys):
    assert cli.main(["--enroll", "florist", "--snapshot", env["snapshot"]] + AS_OF) == 0
    assert env["store"].get(sequence.thread_key("room_jf2"))["enrolled_by"] == "manual"
    assert cli.main(["--enroll", "nobody", "--snapshot", env["snapshot"]] + AS_OF) == 1
    assert cli.main(["--enroll", "florist", "--snapshot", str(env["tmp"] / "missing.json")] + AS_OF) == 1


# ------------------------------------------------------------------ --status
def test_status_prints_the_table(enrolled, capsys):
    cli.main(["--stage", "orchard", "call_booked", "--snapshot", enrolled["snapshot"]] + AS_OF)
    capsys.readouterr()
    assert cli.main(["--status", "--snapshot", enrolled["snapshot"]] + AS_OF) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    for col in ("client", "job title", "stage (set by)", "status", "pending", "next due", "room"):
        assert col in lines[0]
    body = "\n".join(lines[2:])
    assert "Juniper Bakery Co" in body and "Pipedrive invoice sync" in body
    assert "new_reply (engine)" in body
    assert "call_booked (lorenzo)" in body
    assert "T1 due 2026-09-23" in body
    assert "upwork:meta" not in out and "upwork_meta" not in out
    assert len(lines) == 2 + 3


def test_status_with_no_threads(env, capsys):
    assert cli.main(["--status", "--snapshot", env["snapshot"]] + AS_OF) == 0
    assert "No Upwork threads yet" in capsys.readouterr().out


# ------------------------------------------------------------------ --ingest / --print-collect
def test_ingest_writes_the_snapshot(env, capsys, tmp_path):
    target = tmp_path / "out" / "snapshot.json"
    code = cli.main(["--ingest", str(FIXTURE), "--snapshot", str(target)] + AS_OF)
    out = capsys.readouterr().out
    assert code == 0
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "rooms in scope" in out and "omitted:" in out and "sections:" in out
    assert "%d rooms in scope" % len(data["rooms"]) in out
    assert env["logs"][-1][:2] == ("upwork_followup", "ingest")


def test_ingest_refusal_exits_1_and_writes_nothing(env, capsys, tmp_path):
    raw = tmp_path / "empty.json"
    raw.write_text("{}", encoding="utf-8")
    target = tmp_path / "out" / "snapshot.json"
    assert cli.main(["--ingest", str(raw), "--snapshot", str(target)] + AS_OF) == 1
    assert not target.exists()
    assert "refusing to write the snapshot" in capsys.readouterr().err
    assert env["logs"][-1][:2] == ("upwork_followup", "ingest_refused")


def test_ingest_unreadable_file_exits_1(env, tmp_path):
    raw = tmp_path / "broken.json"
    raw.write_text("{not json", encoding="utf-8")
    assert cli.main(["--ingest", str(raw), "--snapshot", str(tmp_path / "s.json")] + AS_OF) == 1


def test_print_collect(capsys):
    assert cli.main(["--print-collect"]) == 0
    out = capsys.readouterr().out
    assert "org_uid for this run" in out
    assert out.startswith(collect.collect_instructions()[:40])


# ------------------------------------------------------------------ tick routing
class FakeTick(object):
    def __init__(self):
        self.calls = []

    def __call__(self, now, mode, snapshot_path=None, **kw):
        self.calls.append({"mode": mode, "snapshot_path": snapshot_path, "now": now})
        counts = dict((k, 0) for k in ("rooms", "enrolled", "drafted", "needs_edit", "pending", "sent_detected",
                                       "replies", "won", "lost", "skipped", "resurfaced", "deferred",
                                       "needs_review", "revivable", "ghl_errors", "errors"))
        counts.update(snapshot_age_h=0.2, mode=mode)
        return {"status": "ok", "mode": mode, "counts": counts, "warnings": [], "errors": [], "check": [],
                "ghl_notes": [], "cards": [], "cards_state": "none", "batch_path": "/tmp/x/drafts.md",
                "snapshot_error": None}


def test_default_is_dry_run(env, monkeypatch, capsys):
    fake = FakeTick()
    monkeypatch.setattr(cli.tick, "run_tick", fake)
    assert cli.main(["--snapshot", env["snapshot"]] + AS_OF) == 0
    assert [c["mode"] for c in fake.calls] == ["dry-run"]
    out = capsys.readouterr().out
    assert "spends Anthropic tokens" not in out
    assert "upwork_followup dry-run: ok" in out
    assert cli.main(["--dry-run"] + AS_OF) == 0
    assert fake.calls[-1]["mode"] == "dry-run"


@pytest.mark.parametrize("flag", ["--run", "--now"])
def test_run_prints_the_token_note_first(env, monkeypatch, capsys, flag):
    fake = FakeTick()
    monkeypatch.setattr(cli.tick, "run_tick", fake)
    assert cli.main([flag, "--snapshot", env["snapshot"]] + AS_OF) == 0
    assert [c["mode"] for c in fake.calls] == ["run"]
    out = capsys.readouterr().out
    assert out.startswith("Note: this run spends Anthropic tokens (Sonnet drafts, Haiku classification).")


def test_run_exits_1_when_the_snapshot_is_missing(env, monkeypatch):
    fake = FakeTick()

    def missing(now, mode, snapshot_path=None, **kw):
        out = fake(now, mode, snapshot_path=snapshot_path)
        out.update(status="error", snapshot_error="missing")
        return out

    monkeypatch.setattr(cli.tick, "run_tick", missing)
    assert cli.main(["--dry-run"] + AS_OF) == 1


def test_dry_run_end_to_end_makes_no_model_call(enrolled, monkeypatch):
    """The real tick through the CLI: dry-run needs no LLM and leaves the store as it was."""
    from services.upwork_followup import classify as classify_mod
    from services.upwork_followup import draft

    def boom(*a, **k):
        raise AssertionError("dry-run reached a model")

    monkeypatch.setattr(draft.shared_llm, "complete", boom)
    monkeypatch.setattr(classify_mod.shared_llm, "complete", boom)
    before = json.dumps({k: enrolled["store"].get(k) for k in enrolled["store"].keys("")}, sort_keys=True)
    assert cli.main(["--dry-run", "--snapshot", enrolled["snapshot"], "--as-of", "2026-09-24T13:30:00Z"]) == 0
    after = json.dumps({k: enrolled["store"].get(k) for k in enrolled["store"].keys("")}, sort_keys=True)
    assert after == before


def test_mutually_exclusive_actions():
    with pytest.raises(SystemExit):
        cli.main(["--run", "--dry-run"])


def test_status_shows_a_pending_draft_as_not_sent_yet(enrolled, capsys):
    def reserve_and_fill(cur):
        cur = dict(cur)
        cur["pending"] = {"kind": "touch", "touch": 1, "issued_at": "2026-09-22T13:30:00Z", "text": "draft text",
                          "card_id": "uwf-x", "resurfaced_at": None}
        return cur
    enrolled["store"].mutate(sequence.thread_key("room_ol3"), reserve_and_fill)
    assert cli.main(["--status", "--snapshot", enrolled["snapshot"]] + AS_OF) == 0
    out = capsys.readouterr().out
    row = next(l for l in out.splitlines() if "room_ol3" in l)
    assert "Follow-up T1 drafted, not sent yet" in row
    assert "unknown" not in row


def test_run_prints_a_clear_message_when_another_run_holds_the_lock(env, monkeypatch, capsys):
    fake = FakeTick()

    def locked(now, mode, snapshot_path=None, **kw):
        out = fake(now, mode, snapshot_path=snapshot_path)
        out.update(status="locked", locked={"acquired_at": "2026-09-22T13:30:00+00:00",
                                            "expires_at": "2026-09-22T14:00:00+00:00"})
        return out

    monkeypatch.setattr(cli.tick, "run_tick", locked)
    assert cli.main(["--run"] + AS_OF) == 0
    out = capsys.readouterr().out
    assert "Another --run is still in progress" in out and "did nothing" in out


# ------------------------------------------------------------------ round 3: --json when locked, --status lines
WALL = datetime(2026, 9, 23, 6, 0, tzinfo=timezone.utc)   # the real clock the run lease reads


def test_run_json_prints_json_when_another_run_holds_the_lock(env, monkeypatch, capsys):
    fake = FakeTick()

    def locked(now, mode, snapshot_path=None, **kw):
        out = fake(now, mode, snapshot_path=snapshot_path)
        out.update(status="locked", locked={"acquired_at": "2026-09-23T05:55:00+00:00",
                                            "free_by": "2026-09-23T06:25:00+00:00"})
        return out

    monkeypatch.setattr(cli.tick, "run_tick", locked)
    assert cli.main(["--run", "--json"] + AS_OF) == 0
    captured = capsys.readouterr()
    doc = json.loads(captured.out)                        # stdout is the JSON document and nothing else
    assert doc["status"] == "locked" and doc["locked"]["free_by"] == "2026-09-23T06:25:00+00:00"
    assert "spends Anthropic tokens" in captured.err and "Another --run" not in captured.out


def test_run_json_with_a_real_live_lease(env, monkeypatch, capsys):
    """The real tick: a lease another run renewed 5 minutes ago on the real
    clock blocks this --run, whatever its --as-of."""
    held = {"owner": "scheduled-run", "acquired_at": "2026-09-23T05:50:00+00:00",
            "heartbeat_at": "2026-09-23T05:55:00+00:00", "expires_at": "2026-09-23T06:25:00+00:00", "pid": 4242}
    env["store"].set(cli.tick.LOCK_KEY, held)
    monkeypatch.setattr(cli.tick, "wall_clock", lambda: WALL)
    monkeypatch.setattr(cli.tick, "log_run", lambda job, status, details=None: env["logs"].append((job, status)))

    def boom(*a, **k):
        raise AssertionError("a locked run reached a model")

    from services.upwork_followup import classify as classify_mod
    from services.upwork_followup import draft
    monkeypatch.setattr(draft.shared_llm, "complete", boom)
    monkeypatch.setattr(classify_mod.shared_llm, "complete", boom)
    assert cli.main(["--run", "--json", "--snapshot", env["snapshot"], "--as-of", "2026-09-21T13:30:00Z"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["status"] == "locked" and doc["locked"]["free_by"] == "2026-09-23T06:25:00+00:00"
    assert env["store"].get(cli.tick.LOCK_KEY) == held
    assert env["store"].keys("upwork:") == []


def blocked(r, at="2026-09-21T16:00:00Z"):
    r = json.loads(json.dumps(r))
    r["messages"].append({"id": r["room_id"] + "_b", "side": "unknown", "at": at, "event": True,
                          "event_name": "blocked",
                          "text": "System event: blocked. View this conversation on upwork.com for full context."})
    r.update(blocked=True, blocked_at=at)
    return r


def status_row(env, snapshot, rid, capsys):
    path = env["tmp"] / "status_snapshot.json"
    collect.write_snapshot(snapshot, path)
    assert cli.main(["--status", "--snapshot", str(path)] + AS_OF) == 0
    return next(line for line in capsys.readouterr().out.splitlines() if rid in line)


def test_status_shows_a_blocked_room(enrolled, capsys):
    s = snap([ROOMS[0], blocked(ROOMS[1]), ROOMS[2]])
    s["blocked_rooms"] = ["room_jf2"]
    assert "blocked on Upwork since 2026-09-21" in status_row(enrolled, s, "room_jf2", capsys)
    assert "T1 due 2026-09-23" in status_row(enrolled, s, "room_jb1", capsys)


def test_status_lists_a_blocked_room_that_was_never_enrolled(env, capsys):
    s = snap([blocked(ROOMS[1])])
    s["blocked_rooms"] = ["room_jf2"]
    row = status_row(env, s, "room_jf2", capsys)
    assert "Juniper Florist" in row and "not enrolled" in row and "blocked on Upwork since 2026-09-21" in row


def test_status_for_a_closed_thread(enrolled, capsys):
    s = snap([ROOMS[0], blocked(ROOMS[1], at="2026-09-20T12:00:00Z"), ROOMS[2]])
    s["blocked_rooms"] = ["room_jf2"]
    sequence.run(enrolled["store"], s, NOW, classify)     # the block closes the thread
    t = enrolled["store"].get(sequence.thread_key("room_jf2"))
    assert (t["status"], t["stop_reason"]) == ("closed", "room_blocked")
    # the room has left the pull: the thread's own block time, not the run time
    assert "blocked on Upwork since 2026-09-20" in status_row(enrolled, snap([ROOMS[0], ROOMS[2]]), "room_jf2",
                                                              capsys)
    # the room is open again, the thread still closed
    row = status_row(enrolled, snap(ROOMS), "room_jf2", capsys)
    assert "closed (blocked on Upwork); --resume or a drafting --stage reopens it" in row


def test_status_shows_a_skipped_reply(env, capsys):
    r = json.loads(json.dumps(ROOMS[2]))
    r["messages"].append({"id": "room_ol3_q", "side": "client", "at": "2026-09-21T16:00:00Z",
                          "text": "question: does it work with Open Dental?"})
    r.update(last_side="client", last_message_at="2026-09-21T16:00:00Z")
    sequence.run(env["store"], snap([r]), NOW, classify)
    env["store"].mutate(sequence.thread_key("room_ol3"),
                        lambda cur: sequence.clear_pending(cur, NOW, reason="cleared", retry=False))
    row = status_row(env, snap([r]), "room_ol3", capsys)
    assert "reply skipped on 2026-09-22; client waiting since 2026-09-21" in row


# ------------------------------------------------------------------ round 4: --run --json stdout
def test_run_json_stdout_is_only_the_json_document_on_a_drafting_run(env, capfd):
    """The real tick through the CLI, classifying one reply and drafting (the
    session's LLM_FAKE canned answers: nothing billed, no network). stdout,
    read at the file-descriptor level, parses as the one JSON document; the
    token note goes to stderr."""
    r = json.loads(json.dumps(ROOMS[2]))
    r["messages"].append({"id": "room_ol3_q", "side": "client", "at": "2026-09-21T16:00:00Z",
                          "text": "question: does it work with Open Dental?"})
    r.update(last_side="client", last_message_at="2026-09-21T16:00:00Z")
    path = env["tmp"] / "drafting_snapshot.json"
    collect.write_snapshot(snap([ROOMS[0], ROOMS[1], r]), path)
    assert cli.main(["--run", "--json", "--snapshot", str(path), "--as-of", "2026-09-24T13:30:00Z"]) == 0
    out, err = capfd.readouterr()
    doc = json.loads(out)
    assert doc["mode"] == "run" and doc["status"] != "error" and doc["lock_lost"] is None
    assert doc["counts"]["replies"] == 1 and doc["counts"]["drafted"] == 3
    assert "spends Anthropic tokens" in err and "spends Anthropic tokens" not in out
