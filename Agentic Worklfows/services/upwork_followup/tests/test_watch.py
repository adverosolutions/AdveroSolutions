"""The watch trigger (services/upwork_followup/watch.py and the CLI's
--watch-plan / --ingest-light). Invented rooms, clients and ids only. The store
and the snapshot live under tmp_path; GHL is a fake object that records its
reads; every model call is a fake (shared.llm.complete is replaced with a
function that fails the test). Nothing here touches the network."""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shared import settings
from shared.store import JsonFileStore, get_store

from jobs import upwork_followup as cli
from services.upwork_followup import classify as classify_mod
from services.upwork_followup import collect, draft, ghl_sync, sequence, tick, watch

FULL_AT = datetime(2026, 9, 22, 13, 5, tzinfo=timezone.utc)     # 08:05 CT, the day's full collect
NOW = datetime(2026, 9, 22, 17, 0, tzinfo=timezone.utc)         # 12:00 CT, a watch run
WALL = datetime(2026, 9, 22, 17, 1, tzinfo=timezone.utc)
STAGE_KEYS = ("new_reply", "proposal_sent", "call_booked", "follow_up_later", "won", "lost")
UPWORK_PIPELINE = {"id": "pl_upwork_watch", "stages": dict((k, "st_watch_" + k) for k in STAGE_KEYS)}
PROMPT = Path(__file__).resolve().parent.parent / "watch_task_prompt.md"


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def at(day, hour):
    return datetime(2026, 9, day, hour, tzinfo=timezone.utc)


def wrap(text):
    return "<untrusted_participant_content>\n%s\n</untrusted_participant_content>" % text


# ------------------------------------------------------------------ builders
def smsg(mid, side, when, text):
    """A normalized snapshot message."""
    return {"id": mid, "side": side, "at": when.isoformat(), "text": text, "event": False}


def sroom(rid, client, msgs):
    return {"room_id": rid, "client": client, "client_first_name": None, "room_type": "INTERVIEW",
            "job_title": "Invented job for " + client, "job_id": None, "proposal_id": "prop_" + rid,
            "origin": "proposal", "contract": None, "offer_state": None, "messages": list(msgs),
            "last_side": msgs[-1]["side"], "last_message_at": msgs[-1]["at"], "blocked": False,
            "blocked_at": None, "job_folder": None, "job": None}


def rooms_wa1():
    return sroom("room_wa1", "Willow Acre Farms", [
        smsg("st_w1", "client", at(18, 15), "Hi, saw your proposal."),
        smsg("st_w2", "freelancer", at(19, 15), "Thanks, here is the plan.")])


def rooms_qb2():
    return sroom("room_qb2", "Quartz Bay Kayaks", [
        smsg("st_q1", "client", at(17, 15), "Interested."),
        smsg("st_q2", "freelancer", at(17, 18), "Great, the Loom is inside.")])


def snapshot(generated=FULL_AT):
    return {"generated_at": generated.isoformat(), "source": "fixture",
            "sections": {"rooms": True, "messages": True, "proposals": True, "invitations": None,
                         "contracts": True, "offers": True},
            "truncated": False, "truncated_sections": [], "live_threads": [],
            "omitted_unlinked": 1, "omitted_contracted": 1,
            "contracted_rooms": [{"room_id": "room_ct5", "contract_id": "9001", "status": "ACTIVE",
                                  "proposal_id": None}],
            "missing_messages": [], "blocked_rooms": [], "link_errors": [],
            "listed_rooms": ["room_ct5", "room_ou9", "room_qb2", "room_wa1"],
            "rooms": [rooms_wa1(), rooms_qb2()]}


def card(rid, name, story_id, when, side, room_type="INTERVIEW", contract=None, text="A message."):
    c = {"id": rid, "roomName": wrap(name), "roomType": room_type,
         "lastActivity": str(int(when.timestamp() * 1000)),
         "latestStory": {"id": story_id, "createdDateTime": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                         "message": wrap(text)},
         "last_message_side": side, "last_message_from_self": side == "freelancer",
         "awaiting_reply_from": "them" if side == "freelancer" else "you", "numUnread": 0, "numUsers": 2}
    if contract:
        c["contractId"] = contract
        c["contractStatus"] = "ACTIVE"
    return c


def page(cards, has_more=False):
    return {"data": {"rooms": list(cards)}, "hasMore": has_more, "next_cursor": "cur2" if has_more else None,
            "status": "ok"}


def quiet_cards():
    """Every card shows exactly what the snapshot already holds."""
    return [card("room_wa1", "Willow Acre Farms", "st_w2", at(19, 15), "freelancer"),
            card("room_qb2", "Quartz Bay Kayaks", "st_q2", at(17, 18), "freelancer"),
            card("room_ou9", "Onyx Utility Co", "st_o1", at(22, 14), "client"),
            card("room_ct5", "Cobalt Tile", "st_c9", at(22, 16), "client", contract="9001")]


def replace_card(cards, new):
    return [new if c["id"] == new["id"] else c for c in cards]


def node(mid, side, when, text):
    n = {"id": mid, "createdDateTime": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "message": wrap(text),
         "from": wrap("Someone"), "from_my_organization": side == "freelancer", "from_side": side}
    if side == "freelancer":
        n["from_self"] = True
    return {"node": n}


def list_messages(nodes_newest_first):
    return {"data": {"roomStories": {"edges": list(nodes_newest_first),
                                     "pageInfo": {"endCursor": "s", "hasNextPage": False}}},
            "hasMore": False, "next_cursor": None, "status": "ok"}


def wa1_pull():
    """list_messages for room_wa1 after the client wrote again (newest first)."""
    return list_messages([node("st_w3", "client", at(22, 16), "Can we start Monday?"),
                          node("st_w2", "freelancer", at(19, 15), "Thanks, here is the plan."),
                          node("st_w1", "client", at(18, 15), "Hi, saw your proposal.")])


def wa1_new_cards():
    return replace_card(quiet_cards(), card("room_wa1", "Willow Acre Farms", "st_w3", at(22, 16), "client"))


class FakeGHL(object):
    """Only reads exist here; a write would fail the test."""

    def __init__(self, stage_key=None):
        self.calls = []
        self.stage_key = stage_key

    def get_opportunity(self, opp_id):
        self.calls.append(("get_opportunity", opp_id))
        return {"opportunity": {"pipelineId": UPWORK_PIPELINE["id"],
                                "pipelineStageId": UPWORK_PIPELINE["stages"][self.stage_key]}}

    def __getattr__(self, name):
        raise AssertionError("the watch must only read GHL, it called %s" % name)


class FakeLLM(object):
    def __init__(self):
        self.calls = []

    def __call__(self, role, system, user, max_tokens=800, json_mode=False):
        self.calls.append(role)
        if role in ("classify", "escalate"):
            return {"label": "positive", "confidence": 0.95}
        return "Monday works. I would start with the intake form, then the follow-up flow.\nPROPOSES_CALL: no"


class FakeNotify(object):
    def __init__(self):
        self.calls = []

    def __call__(self, title, message, **kw):
        self.calls.append(title)
        return {"sent": False, "test": False, "shadow": True}


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))

    def boom(*a, **k):
        raise AssertionError("shared.llm.complete must never be called in these tests")

    monkeypatch.setattr(draft.shared_llm, "complete", boom)
    monkeypatch.setattr(classify_mod.shared_llm, "complete", boom)
    monkeypatch.setattr(tick, "topic_is_protected", lambda: False)
    monkeypatch.setattr(tick, "log_run", lambda *a, **k: None)
    logs = []
    monkeypatch.setattr(cli, "log_run", lambda job, status, details=None: logs.append((job, status, details)))

    def no_ghl():
        raise AssertionError("no GHL client may be built while the Upwork pipeline is not configured")

    monkeypatch.setattr(cli, "_ghl_client", no_ghl)
    return {"tmp": tmp_path, "logs": logs}


def mark_processed(store, snap):
    """What a finished --run leaves behind (tick._remember_processed)."""
    store.set(tick.TICK_KEY, {tick.PROCESSED: {"revision": collect.snapshot_revision(snap),
                                               "as_of": iso(NOW)}})


@pytest.fixture
def store(tmp_path):
    s = get_store(force_new=True)
    mark_processed(s, snapshot())       # today's full ingest went through a --run
    return s


@pytest.fixture
def upwork_pipeline(monkeypatch):
    ids = json.loads(json.dumps(settings.IDS or {}))
    ids.setdefault("ghl", {}).setdefault("pipelines", {})["upwork"] = UPWORK_PIPELINE
    monkeypatch.setattr(settings, "IDS", ids)
    assert ghl_sync.mirror_status() is None
    return UPWORK_PIPELINE


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(path)


def plan(cards, snap=None, store=None, now=NOW, ghl=None, ghl_factory=None, has_more=False):
    return watch.plan(page(cards, has_more), snapshot() if snap is None else snap, store, now,
                      ghl=ghl, ghl_factory=ghl_factory)


def seed_thread(store, rid, **fields):
    thread = {"room_id": rid, "client": "Invented", "status": "active", "stage": "new_reply",
              "stage_set_by": "engine", "ghl": {"contact_id": None, "opportunity_id": None, "stage": None},
              "marks": {"last_seen_at": None}, "history": []}
    thread.update(fields)
    store.set(sequence.thread_key(rid), thread)
    return thread


# ------------------------------------------------------------------ none
def test_no_change_plans_none(store):
    result = plan(quiet_cards(), store=store)
    assert result == {"mode": "none", "rooms": [], "reasons": {"_run": "no new activity"}, "checked": 4}


def test_the_plan_is_read_only(store, tmp_path):
    seed_thread(store, "room_wa1")
    before = (tmp_path / "store.json").read_text(encoding="utf-8")
    plan(wa1_new_cards(), store=store)
    plan(quiet_cards(), store=store)
    assert (tmp_path / "store.json").read_text(encoding="utf-8") == before


# ------------------------------------------------------------------ light
def test_tracked_room_with_newer_client_activity_plans_light(store):
    result = plan(wa1_new_cards(), store=store)
    assert result["mode"] == "light"
    assert result["rooms"] == ["room_wa1"]
    assert result["reasons"] == {"room_wa1": "new client activity"}


def test_lorenzos_own_newer_message_is_not_flagged(store):
    cards = replace_card(quiet_cards(), card("room_wa1", "Willow Acre Farms", "st_w9", at(22, 16), "freelancer"))
    assert plan(cards, store=store)["mode"] == "none"


def test_an_already_ingested_message_is_not_flagged(store):
    # the card's latest story is a message the snapshot already holds
    cards = replace_card(quiet_cards(), card("room_qb2", "Quartz Bay Kayaks", "st_q1", at(17, 15), "client"))
    assert plan(cards, store=store)["mode"] == "none"
    # an id the snapshot does not know, but no newer than what it holds (another id format)
    cards = replace_card(quiet_cards(), card("room_wa1", "Willow Acre Farms", "other-id-7", at(19, 15), "client"))
    assert plan(cards, store=store)["mode"] == "none"


def test_the_threads_last_seen_mark_counts_as_seen(store):
    seed_thread(store, "room_wa1", marks={"last_seen_at": at(22, 16).isoformat()})
    assert plan(wa1_new_cards(), store=store)["mode"] == "none"


def test_a_card_with_nothing_to_compare_is_never_flagged(store):
    bare = {"id": "room_wa1", "roomName": wrap("Willow Acre Farms"), "roomType": "INTERVIEW",
            "last_message_side": "client"}
    assert plan(replace_card(quiet_cards(), bare), store=store)["mode"] == "none"


# ------------------------------------------------------------------ full
def test_untracked_room_with_new_activity_plans_full(store):
    cards = quiet_cards() + [card("room_nw3", "Nimbus Weld Shop", "st_n1", at(22, 15), "client")]
    result = plan(cards, store=store)
    assert result["mode"] == "full" and result["rooms"] == []
    assert result["reasons"]["room_nw3"] == "room not in the last full collect"
    assert "_run" in result["reasons"]


def test_rooms_the_full_collect_already_judged_do_not_force_a_full_run(store):
    # room_ou9 was listed (and left out) by the full collect; room_ct5 has a
    # contract; a GROUP room and a contract room never count either
    cards = quiet_cards() + [card("room_gr4", "Garnet Group Chat", "st_g1", at(22, 15), "client",
                                  room_type="GROUP"),
                             card("room_cx6", "Cinder Axe Co", "st_x1", at(22, 15), "client", contract="9009")]
    assert plan(cards, store=store)["mode"] == "none"


def test_an_old_untracked_room_is_not_a_trigger(store):
    cards = quiet_cards() + [card("room_ol7", "Olive Lane Cafe", "st_l1", at(10, 15), "client")]
    assert plan(cards, store=store)["mode"] == "none"


def test_first_run_of_a_ct_day_plans_full(store):
    yesterday = snapshot(generated=datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc))   # 17:00 CT on the 21st
    result = plan(quiet_cards(), snap=yesterday, store=store)
    assert result["mode"] == "full"
    assert result["reasons"] == {"_run": "first run of the CT day (last full collect 2026-09-21)"}
    # 04:30Z on the 23rd is still 23:30 CT on the 22nd: same CT day as the full collect
    late = plan(quiet_cards(), store=store, now=datetime(2026, 9, 23, 4, 30, tzinfo=timezone.utc))
    assert late["mode"] == "none"


def test_missing_snapshot_plans_full(store):
    result = watch.plan(page(quiet_cards()), None, store, NOW, snapshot_error="missing")
    assert result["mode"] == "full" and result["reasons"] == {"_run": "no snapshot (missing)"}


@pytest.mark.parametrize("raw", [
    "this is not json {",
    json.dumps({"status": "error", "message": "Rate limit exceeded"}),
    json.dumps({"data": {"nothing": []}, "status": "ok"}),
    json.dumps([]),
])
def test_unparsable_rooms_file_plans_full(raw, tmp_path, capsys, store):
    snap_path = tmp_path / "snapshot.json"
    collect.write_snapshot(snapshot(), snap_path)
    rooms = write(tmp_path, "watch_rooms.json", raw)
    code = cli.main(["--watch-plan", rooms, "--snapshot", str(snap_path), "--as-of", iso(NOW)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["mode"] == "full" and out["rooms"] == [] and "_run" in out["reasons"]


def test_a_contract_on_a_tracked_room_plans_full(store):
    cards = replace_card(quiet_cards(), card("room_qb2", "Quartz Bay Kayaks", "st_q9", at(22, 16), "client",
                                             contract="9100"))
    assert plan(cards, store=store)["mode"] == "full"


def test_a_full_page_of_newer_rooms_plans_full(store):
    cards = [card("room_p%02d" % i, "Invented %d" % i, "st_p%d" % i, at(22, 15), "freelancer")
             for i in range(3)]
    snap = snapshot()
    snap["listed_rooms"] += [c["id"] for c in cards]
    assert plan(cards, snap=snap, store=store, has_more=True)["mode"] == "full"
    assert plan(cards, snap=snap, store=store, has_more=False)["mode"] == "none"


# ------------------------------------------------------------------ GHL
def test_ghl_move_into_a_drafting_stage_plans_light(store, upwork_pipeline):
    seed_thread(store, "room_qb2", stage="follow_up_later", stage_set_by="lorenzo",
                ghl={"contact_id": "ct_1", "opportunity_id": "opp_qb2", "stage": "follow_up_later"})
    ghl = FakeGHL(stage_key="new_reply")
    result = plan(quiet_cards(), store=store, ghl=ghl)
    assert result["mode"] == "light" and result["rooms"] == ["room_qb2"]
    assert result["reasons"] == {"room_qb2": "GHL stage new_reply"}
    assert ghl.calls == [("get_opportunity", "opp_qb2")]


def test_ghl_holding_the_threads_own_stage_plans_none(store, upwork_pipeline):
    seed_thread(store, "room_qb2", stage="new_reply",
                ghl={"contact_id": "ct_1", "opportunity_id": "opp_qb2", "stage": "new_reply"})
    assert plan(quiet_cards(), store=store, ghl=FakeGHL(stage_key="new_reply"))["mode"] == "none"


def test_ghl_is_not_read_for_a_thread_won_by_contract(store, upwork_pipeline):
    seed_thread(store, "room_qb2", stage="won", stage_set_by="engine", status="won",
                ghl={"contact_id": "ct_1", "opportunity_id": "opp_qb2", "stage": None})
    ghl = FakeGHL(stage_key="new_reply")
    assert plan(quiet_cards(), store=store, ghl=ghl)["mode"] == "none"
    assert ghl.calls == []


def test_ghl_not_configured_makes_no_ghl_call(store):
    assert ghl_sync.mirror_status() is not None           # ids.json ships the Upwork pipeline empty
    seed_thread(store, "room_qb2", stage="follow_up_later",
                ghl={"contact_id": "ct_1", "opportunity_id": "opp_qb2", "stage": "follow_up_later"})
    ghl = FakeGHL(stage_key="new_reply")
    built = []
    result = plan(quiet_cards(), store=store, ghl_factory=lambda: built.append(1) or ghl)
    assert result["mode"] == "none"
    assert built == [] and ghl.calls == []


def test_cli_watch_plan_prints_one_json_line_and_builds_no_ghl_client(tmp_path, capsys, store):
    snap_path = tmp_path / "snapshot.json"
    collect.write_snapshot(snapshot(), snap_path)
    rooms = write(tmp_path, "watch_rooms.json", page(wa1_new_cards()))
    code = cli.main(["--watch-plan", rooms, "--snapshot", str(snap_path), "--as-of", iso(NOW)])
    out = capsys.readouterr().out
    assert code == 0 and len(out.strip().splitlines()) == 1
    assert json.loads(out) == {"mode": "light", "rooms": ["room_wa1"],
                               "reasons": {"room_wa1": "new client activity"}, "checked": 4}


# ------------------------------------------------------------------ light ingest
def test_ingest_light_changes_only_the_listed_rooms_and_is_idempotent():
    before = snapshot()
    raw = {"collected_at": iso(NOW), "messages": {"room_wa1": wa1_pull()}}
    once, report = watch.ingest_light(before, raw, NOW, page(wa1_new_cards()))
    assert report == {"merged": ["room_wa1"], "behind": [], "gave_up": [], "failed": [], "not_in_snapshot": []}
    assert before == snapshot()                                   # the input is not changed
    wa1 = [r for r in once["rooms"] if r["room_id"] == "room_wa1"][0]
    assert [m["id"] for m in wa1["messages"]] == ["st_w1", "st_w2", "st_w3"]
    assert wa1["last_side"] == "client" and wa1["last_message_at"] == at(22, 16).isoformat()
    # every other room and section is untouched
    assert [r for r in once["rooms"] if r["room_id"] == "room_qb2"] == [rooms_qb2()]
    for key in ("generated_at", "contracted_rooms", "listed_rooms", "sections", "truncated",
                "omitted_unlinked", "live_threads", "link_errors"):
        assert once[key] == before[key], key
    assert once["watch_seen"] == {"room_wa1": at(22, 16).isoformat()}
    twice, _ = watch.ingest_light(once, raw, NOW, page(wa1_new_cards()))
    assert twice == once


def test_ingest_light_keeps_older_history_and_skips_failed_and_unknown_rooms():
    snap = snapshot()
    snap["rooms"][0]["messages"].insert(0, smsg("st_w0", "client", at(10, 15), "An older message."))
    raw = {"collected_at": iso(NOW),
           "messages": {"room_wa1": wa1_pull(),
                        "room_qb2": {"status": "error", "message": "Rate limit exceeded"},
                        "room_zz0": wa1_pull()}}
    out, report = watch.ingest_light(snap, raw, NOW)
    assert report == {"merged": ["room_wa1"], "behind": [], "gave_up": [], "failed": ["room_qb2"],
                      "not_in_snapshot": ["room_zz0"]}
    wa1 = [r for r in out["rooms"] if r["room_id"] == "room_wa1"][0]
    assert [m["id"] for m in wa1["messages"]] == ["st_w0", "st_w1", "st_w2", "st_w3"]
    assert [r for r in out["rooms"] if r["room_id"] == "room_qb2"][0] == snap["rooms"][1]
    assert all(r["room_id"] != "room_zz0" for r in out["rooms"])
    # the failed room is planned again next time (a retry), the merged one is not
    cards = replace_card(wa1_new_cards(), card("room_qb2", "Quartz Bay Kayaks", "st_q3", at(22, 16), "client"))
    assert watch.plan(page(cards), out, None, NOW)["rooms"] == ["room_qb2"]


def test_ingest_light_clears_a_room_from_missing_messages():
    snap = snapshot()
    snap["rooms"][0]["messages"] = None
    snap["missing_messages"] = ["room_wa1"]
    snap["sections"]["messages"] = False
    out, _ = watch.ingest_light(snap, {"collected_at": iso(NOW), "messages": {"room_wa1": wa1_pull()}}, NOW)
    assert out["missing_messages"] == [] and out["sections"]["messages"] is True
    assert len([r for r in out["rooms"] if r["room_id"] == "room_wa1"][0]["messages"]) == 3


@pytest.mark.parametrize("raw, why", [
    ([], "not a JSON object"),
    ({"status": "error", "message": "Rate limit exceeded"}, "error response"),
    ({"messages": {"room_wa1": None}}, "collected_at"),
    ({"collected_at": iso(NOW + timedelta(hours=2)), "messages": {"room_wa1": None}}, "future"),
    ({"collected_at": iso(NOW), "messages": {}}, "messages must be a map"),
    ({"collected_at": iso(NOW), "messages": {"room_wa1": []}}, "no room could be merged"),
])
def test_ingest_light_refuses_a_bad_pull(raw, why):
    with pytest.raises(collect.IngestError) as err:
        watch.ingest_light(snapshot(), raw, NOW)
    assert why in str(err.value)


def test_ingest_light_needs_a_snapshot():
    with pytest.raises(collect.IngestError):
        watch.ingest_light(None, {"collected_at": iso(NOW), "messages": {"room_wa1": wa1_pull()}}, NOW)


def test_cli_ingest_light_refusal_keeps_the_snapshot(tmp_path, capsys, world):
    snap_path = tmp_path / "snapshot.json"
    collect.write_snapshot(snapshot(), snap_path)
    before = snap_path.read_text(encoding="utf-8")
    raw = write(tmp_path, "raw_light.json", {"collected_at": iso(NOW), "messages": {"room_wa1": []}})
    code = cli.main(["--ingest-light", raw, "--snapshot", str(snap_path), "--as-of", iso(NOW)])
    assert code == 1
    assert "refusing to merge" in capsys.readouterr().err
    assert snap_path.read_text(encoding="utf-8") == before
    assert world["logs"][-1][1] == "ingest_light_refused"


# ------------------------------------------------------------------ end to end
def test_light_ingest_then_run_then_the_same_rooms_file_plans_none(tmp_path, capsys, store, world):
    snap_path = tmp_path / "snapshot.json"
    collect.write_snapshot(snapshot(), snap_path)
    common = ["--snapshot", str(snap_path), "--as-of", iso(NOW)]
    rooms = write(tmp_path, "watch_rooms.json", page(wa1_new_cards()))

    assert cli.main(["--watch-plan", rooms] + common) == 0
    assert json.loads(capsys.readouterr().out)["rooms"] == ["room_wa1"]

    raw = write(tmp_path, "raw_light.json", {"collected_at": iso(NOW), "messages": {"room_wa1": wa1_pull()}})
    assert cli.main(["--ingest-light", raw, "--rooms", rooms] + common) == 0
    assert "merged 1 room(s)" in capsys.readouterr().out
    assert world["logs"][-1][1] == "ingest_light"
    # merged but not yet through a --run: the plan asks for one, not "none"
    assert cli.main(["--watch-plan", rooms] + common) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "run"

    llm = FakeLLM()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=snap_path, llm=llm, notify_fn=FakeNotify(),
                           clock=lambda: WALL)
    assert result["status"] != "locked"
    assert result["counts"]["drafted"] >= 1
    wa1 = store.get(sequence.thread_key("room_wa1"))
    assert wa1["last_seen_message_id"] == "st_w3"

    assert cli.main(["--watch-plan", rooms] + common) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "none"
    # and the second plan made no model call
    calls = len(llm.calls)
    watch.plan(page(wa1_new_cards()), collect.load_snapshot(snap_path)[0], store, NOW)
    assert len(llm.calls) == calls


def test_the_full_ingest_lists_every_room_it_saw(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "envelope_synthetic.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    snap = collect.ingest(raw, datetime(2026, 9, 22, 13, 30, tzinfo=timezone.utc), pipeline_dir=tmp_path)
    listed = []
    for p in raw["list_rooms"]:
        listed.extend(c["id"] for c in p["data"]["rooms"])
    assert snap["listed_rooms"] == sorted(listed)


# ------------------------------------------------------------------ the prompt
def test_the_watch_prompt_only_names_read_tools():
    text = PROMPT.read_text(encoding="utf-8")
    body = text.split("\n---\n")[1]
    assert "list_rooms" in body and "list_messages" in body
    assert "--watch-plan" in body and "--ingest-light" in body and "--run" in body
    assert "scheduled_task_prompt.md" in body
    assert "Desktop/AdveroSolutions/Agentic Worklfows" in body and ".worktrees" not in body
    assert "MODE" in body and ".env" in body
    tools = set(re.findall(r"upwork__[a-z_]+", text))
    assert tools == {"upwork__get_messages"}


# ------------------------------------------------ review round 1: defect 1
def light_raw(nodes, when=NOW):
    return {"collected_at": iso(when), "messages": {"room_wa1": list_messages(nodes)}}


def lagging_nodes():
    return [node("st_w2", "freelancer", at(19, 15), "Thanks, here is the plan."),
            node("st_w1", "client", at(18, 15), "Hi, saw your proposal.")]


@pytest.mark.parametrize("nodes", [[], lagging_nodes()], ids=["empty_pull", "lagging_pull"])
def test_a_pull_without_the_cards_story_marks_nothing_seen(nodes):
    snap, report = watch.ingest_light(snapshot(), light_raw(nodes), NOW, page(wa1_new_cards()))
    assert report["merged"] == ["room_wa1"] and report["behind"] == ["room_wa1"] and report["gave_up"] == []
    wa1 = [r for r in snap["rooms"] if r["room_id"] == "room_wa1"][0]
    assert wa1["last_side"] == "freelancer" and wa1["last_message_at"] == at(19, 15).isoformat()
    assert snap["watch_seen"]["room_wa1"] == at(19, 15).isoformat()     # not the card's 16:00 on the 22nd
    # the next watch asks for the room again
    again = watch.plan(page(wa1_new_cards()), snap, None, NOW)
    assert again["mode"] == "light" and again["rooms"] == ["room_wa1"]


def test_a_pull_that_holds_the_story_marks_it_seen():
    snap, report = watch.ingest_light(snapshot(), light_raw([node("st_w3", "client", at(22, 16), "Monday?")]
                                                            + lagging_nodes()), NOW, page(wa1_new_cards()))
    assert report["behind"] == []
    assert watch.plan(page(wa1_new_cards()), snap, None, NOW)["mode"] == "none"


def test_lagging_pulls_stop_being_retried_after_the_cap():
    snap = snapshot()
    for n in range(watch.LIGHT_MISS_CAP):
        raw = light_raw(lagging_nodes(), when=NOW + timedelta(minutes=30 * n))
        snap, report = watch.ingest_light(snap, raw, NOW + timedelta(hours=2), page(wa1_new_cards()))
        # the same pull ingested twice does not count as a second miss
        again, _ = watch.ingest_light(snap, raw, NOW + timedelta(hours=2), page(wa1_new_cards()))
        if n < watch.LIGHT_MISS_CAP - 1:
            assert again == snap and report["gave_up"] == []
            assert watch.plan(page(wa1_new_cards()), snap, None, NOW)["mode"] == "light"
    assert report["gave_up"] == ["room_wa1"]
    assert snap["watch_gave_up"] == {"room_wa1": "id:st_w3"}
    assert watch.plan(page(wa1_new_cards()), snap, None, NOW)["mode"] == "none"
    # a newer story on the same room is asked for again
    newer = replace_card(quiet_cards(), card("room_wa1", "Willow Acre Farms", "st_w4", at(22, 16) + timedelta(
        minutes=5), "client"))
    assert watch.plan(page(newer), snap, None, NOW)["rooms"] == ["room_wa1"]


# ------------------------------------------------ review round 1: defect 2
EVENT = "System event: meeting_scheduled. View this conversation on upwork.com for full context."


@pytest.mark.parametrize("text", [EVENT, "You: " + EVENT, "**Freelancer F.** sent an offer"])
def test_a_room_event_on_lorenzos_side_is_flagged(store, text):
    cards = replace_card(quiet_cards(), card("room_wa1", "Willow Acre Farms", "st_w5", at(22, 16), "freelancer",
                                             text=text))
    result = plan(cards, store=store)
    assert result["mode"] == "light" and result["reasons"] == {"room_wa1": "new room event"}


def test_a_client_message_under_a_room_event_is_read_and_not_flagged_twice():
    cards = replace_card(quiet_cards(), card("room_wa1", "Willow Acre Farms", "st_w5", at(22, 16), "freelancer",
                                             text=EVENT))
    pull = light_raw([node("st_w5", "freelancer", at(22, 16), EVENT),
                      node("st_w3", "client", at(22, 15), "Can we start Monday?")] + lagging_nodes())
    snap, report = watch.ingest_light(snapshot(), pull, NOW, page(cards))
    assert report["behind"] == []
    wa1 = [r for r in snap["rooms"] if r["room_id"] == "room_wa1"][0]
    assert wa1["last_side"] == "client"                       # the event never hides the client's message
    assert watch.plan(page(cards), snap, None, NOW)["mode"] == "none"


# ------------------------------------------------ review round 1: defect 3
def test_the_watch_reads_the_ticks_processed_mark():
    assert watch.TICK_KEY == tick.TICK_KEY and watch.PROCESSED == tick.PROCESSED


def test_a_full_ingest_without_a_finished_run_plans_run(store):
    store.delete(tick.TICK_KEY)
    result = plan(quiet_cards(), store=store)
    assert result["mode"] == "run" and result["rooms"] == []
    assert result["reasons"] == {"_run": "the last ingest has not been through a finished --run"}
    mark_processed(store, snapshot())
    assert plan(quiet_cards(), store=store)["mode"] == "none"


def test_a_locked_out_run_leaves_the_plan_on_run_and_a_finished_run_clears_it(tmp_path, store):
    snap_path = tmp_path / "snapshot.json"
    snap, _ = watch.ingest_light(snapshot(), light_raw([node("st_w3", "client", at(22, 16), "Monday?")]
                                                       + lagging_nodes()), NOW, page(wa1_new_cards()))
    collect.write_snapshot(snap, snap_path)
    assert watch.plan(page(wa1_new_cards()), snap, store, NOW)["mode"] == "run"

    held = tick.acquire_lock(store, WALL, "another-run")
    assert held["lease"] is not None
    locked = tick.run_tick(NOW, "run", store=store, snapshot_path=snap_path, llm=FakeLLM(),
                           notify_fn=FakeNotify(), clock=lambda: WALL)
    assert locked["status"] == "locked"
    assert watch.plan(page(wa1_new_cards()), snap, store, NOW)["mode"] == "run"

    tick.release_lock(store, "another-run", WALL)
    done = tick.run_tick(NOW, "run", store=store, snapshot_path=snap_path, llm=FakeLLM(),
                         notify_fn=FakeNotify(), clock=lambda: WALL)
    assert done["status"] != "locked"
    assert store.get(tick.TICK_KEY)[tick.PROCESSED]["revision"] == collect.snapshot_revision(snap)
    assert watch.plan(page(wa1_new_cards()), snap, store, NOW)["mode"] == "none"


def test_a_dry_run_does_not_count_as_processed(tmp_path, store):
    store.delete(tick.TICK_KEY)
    snap_path = tmp_path / "snapshot.json"
    collect.write_snapshot(snapshot(), snap_path)
    tick.run_tick(NOW, "dry-run", store=store, snapshot_path=snap_path, llm=FakeLLM(), notify_fn=FakeNotify())
    assert plan(quiet_cards(), store=store)["mode"] == "run"


# ------------------------------------------------ review round 1: defect 4
YESTERDAY = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)


def marker(minutes_ago, before=None):
    return {"started_at": iso(NOW - timedelta(minutes=minutes_ago)),
            "snapshot_before": snapshot(generated=YESTERDAY)["generated_at"] if before is None else before}


def test_a_full_run_in_progress_is_not_started_again(store):
    result = watch.plan(page(quiet_cards()), snapshot(generated=YESTERDAY), store, NOW, marker=marker(20))
    assert result["mode"] == "none"
    assert result["reasons"]["_run"].startswith("a full run started at 11:40 CT is still in progress")


def test_a_failed_full_run_waits_two_hours_then_retries(store):
    waiting = watch.plan(page(quiet_cards()), snapshot(generated=YESTERDAY), store, NOW, marker=marker(60))
    assert waiting["mode"] == "none"
    assert "the full run started at 11:00 CT did not finish; next try after 13:00 CT" in waiting["reasons"]["_run"]
    retry = watch.plan(page(quiet_cards()), snapshot(generated=YESTERDAY), store, NOW, marker=marker(125))
    assert retry["mode"] == "full"
    assert "retry: the full run started at 09:55 CT did not finish" in retry["reasons"]["_run"]


def test_a_full_run_that_succeeded_does_not_hold_back_the_next_one(store):
    # the marker's snapshot is not the current one: that full ingest succeeded
    new_room = quiet_cards() + [card("room_nw3", "Nimbus Weld Shop", "st_n1", at(22, 15), "client")]
    result = watch.plan(page(new_room), snapshot(), store, NOW, marker=marker(10))
    assert result["mode"] == "full"


def test_a_waiting_full_run_still_lets_a_light_pull_through(store):
    cards = wa1_new_cards() + [card("room_nw3", "Nimbus Weld Shop", "st_n1", at(22, 15), "client")]
    m = marker(20, before=snapshot()["generated_at"])
    result = watch.plan(page(cards), snapshot(), store, NOW, marker=m)
    assert result["mode"] == "light" and result["rooms"] == ["room_wa1"]
    assert "still in progress" in result["reasons"]["_run"]


def test_no_snapshot_and_a_full_run_in_progress_plans_none(store):
    started = {"started_at": iso(NOW - timedelta(minutes=10)), "snapshot_before": None}
    result = watch.plan(page(quiet_cards()), None, store, NOW, marker=started)
    assert result["mode"] == "none" and "still in progress" in result["reasons"]["_run"]


def test_cli_mark_full_start_is_read_by_the_next_plan(tmp_path, capsys, store):
    snap_path = tmp_path / "snapshot.json"
    collect.write_snapshot(snapshot(generated=YESTERDAY), snap_path)
    rooms = write(tmp_path, "watch_rooms.json", page(quiet_cards()))
    common = ["--snapshot", str(snap_path), "--as-of", iso(NOW)]
    assert cli.main(["--watch-plan", rooms] + common) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "full"
    assert cli.main(["--mark-full-start"] + common) == 0
    capsys.readouterr()
    saved = json.loads(watch.full_marker_path().read_text(encoding="utf-8"))
    assert saved["snapshot_before"] == snapshot(generated=YESTERDAY)["generated_at"]
    assert cli.main(["--watch-plan", rooms] + common) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "none" and "still in progress" in out["reasons"]["_run"]
    # the full ingest lands: the marker no longer holds anything back
    collect.write_snapshot(snapshot(), snap_path)
    assert cli.main(["--watch-plan", rooms] + common) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "none"
