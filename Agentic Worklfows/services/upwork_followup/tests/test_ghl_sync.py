"""U4a: the GHL mirror (ghl_sync.sync_thread) and the stage read-back, against
the separate Upwork pipeline (DESIGN.md "GHL pipeline for Upwork (revised
2026-09-22 after the U4a review)").

Invented names and ids only. Every request goes to an httpx MockTransport;
live is simulated by patching ``settings.is_live`` (the real MODE /
ALLOW_LIVE_WRITES flags are never set). The Upwork pipeline ids are patched
into a COPY of ``settings.IDS``; config/ids.json ships them null.

The loop tests (S1-S12) and the C-series are the U4a reviewer's probes,
adapted to the Upwork pipeline. Round 3 adds: a blocked thread reports
``ghl_blocked`` on every run and makes no request; a live stage write reads
the opportunity first and writes only while GHL still shows the last mirrored
stage (S17-S20); any other pipeline's id keeps the mirror off; the same id on
two stages; an ``abandoned`` status reads as ``lost`` (S15, S16); and the
hand fix from the runbook resumes a blocked thread (S21).
"""
import copy
import csv
import json
from datetime import datetime, timezone

import httpx
import pytest

from services.upwork_followup import ghl_sync
from shared import ghl as ghl_mod
from shared import job_log, settings
from shared.ghl import GHL

LOCATION = "ebyNANPagaK7ycf1pfge"
UP_PIPELINE = "upw-pipeline-0001"
S = {k: "upw-stage-%s" % k for k in ghl_sync.STAGE_KEYS}   # invented Upwork stage ids
SALES_PIPELINE = settings.GHL_SALES_PIPELINE_ID
SALES_IDS = set(v for v in settings.GHL_STAGES.values() if v) | {SALES_PIPELINE}
SALES_REQUESTS = settings.IDS["ghl"]["pipelines"]["sales_requests"]   # the demo pipeline shipped in ids.json
# An invented extra pipeline block, to prove the gate covers ANY other pipeline.
OTHER = {"id": "pl-other-0001", "name": "Other", "stages": {"alpha": "st-other-alpha", "beta": {"id": "st-other-beta"}}}
NOW = datetime(2026, 9, 23, 13, 30, tzinfo=timezone.utc)
ROOM_ID = "room_0000feedc0de"
CLIENT = "Northwind Kiln Studio"
MANUAL = ("lorenzo", "ghl")


def other_pipeline_ids():
    """Every pipeline and stage id ids.json holds outside the Upwork block."""
    out = set(SALES_IDS)
    for name, block in settings.IDS["ghl"]["pipelines"].items():
        if name == "upwork":
            continue
        out.add(block.get("id"))
        for value in (block.get("stages") or {}).values():
            out.add(value.get("id") if isinstance(value, dict) else value)
    return set(i for i in out if i)


def upwork_ids(pipeline_id=UP_PIPELINE, stages=None):
    ids = copy.deepcopy(settings.IDS)
    ids["ghl"]["pipelines"]["upwork"] = {
        "id": pipeline_id,
        "stages": dict(S) if stages is None else stages,
        "note": "test",
    }
    return ids


@pytest.fixture
def upwork(monkeypatch):
    """The Upwork pipeline configured (invented ids)."""
    monkeypatch.setattr(settings, "IDS", upwork_ids())


@pytest.fixture
def fake_live(monkeypatch):
    monkeypatch.setattr(settings, "is_live", lambda: True)


@pytest.fixture
def verified(monkeypatch):
    monkeypatch.setattr(ghl_mod, "CONTACT_WITHOUT_EMAIL_VERIFIED", True)


class Recorder(object):
    def __init__(self, responses=None):
        self.requests = []
        self.responses = list(responses or [])

    def __call__(self, request):
        self.requests.append(request)
        if self.responses:
            status, body = self.responses.pop(0)
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"ok": True})


def make(responses=None, **kw):
    rec = Recorder(responses)
    if not kw:
        kw = {"token": "tok"}
    return GHL(transport=httpx.MockTransport(rec), **kw), rec


def body_of(request):
    return json.loads(request.content.decode("utf-8"))


def thread(stage="new_reply", ghl=None, set_by="engine"):
    return {
        "room_id": ROOM_ID, "client": CLIENT, "status": "active", "stage": stage, "stage_set_by": set_by,
        "stage_changed_at": "2026-09-22T14:00:00+00:00",
        "ghl": ghl if ghl is not None else {"contact_id": None, "opportunity_id": None, "stage": None},
    }


def synced(stage="new_reply", mirrored="new_reply", set_by="engine"):
    return thread(stage=stage, set_by=set_by,
                  ghl={"contact_id": "c-41", "opportunity_id": "o-41", "stage": mirrored})


def opp_response(stage_id, pipeline=UP_PIPELINE, status="open"):
    """What GET /opportunities/o-41 answers."""
    return {"opportunity": {"id": "o-41", "pipelineStageId": stage_id, "pipelineId": pipeline, "status": status}}


ROOM = {"room_id": ROOM_ID, "client": CLIENT, "room_type": "ONE_ON_ONE", "proposal_id": "prop_invented_01"}


def job_rows():
    try:
        with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except (IOError, OSError):
        return []


# ================================================================ not configured
def test_shipped_ids_json_has_the_upwork_block_unconfigured():
    conf = settings.load_ids()["ghl"]["pipelines"]["upwork"]
    assert conf["id"] is None
    assert conf["stages"] == {k: None for k in ghl_sync.STAGE_KEYS}
    assert ghl_sync.upwork_pipeline()[0] is None
    assert ghl_sync.mirror_status()["code"] == "ghl_not_configured"


@pytest.mark.parametrize("conf", [
    None,                                                          # no block
    {"id": None, "stages": dict(S)},                               # no pipeline id
    {"id": UP_PIPELINE, "stages": dict(S, won=None)},              # one stage id missing
    {"id": UP_PIPELINE, "stages": {k: S[k] for k in ("new_reply", "lost")}},
    {"id": SALES_PIPELINE, "stages": dict(S)},                     # the Sales pipeline itself
    {"id": UP_PIPELINE, "stages": dict(S, lost=settings.GHL_STAGES["lost"])},  # a Sales stage id
    {"id": SALES_REQUESTS["id"], "stages": dict(S)},               # another pipeline in ids.json (note 3)
    {"id": UP_PIPELINE, "stages": dict(S, lost=S["won"])},         # the same id on two stages (note 4)
])
def test_mirror_is_off_until_the_upwork_pipeline_is_fully_configured(tmp_env, monkeypatch, fake_live, verified, conf):
    ids = copy.deepcopy(settings.IDS)
    if conf is None:
        ids["ghl"]["pipelines"].pop("upwork", None)
    else:
        ids["ghl"]["pipelines"]["upwork"] = conf
    monkeypatch.setattr(settings, "IDS", ids)
    client, rec = make(responses=[(200, {"opportunity": {"pipelineStageId": S["lost"], "pipelineId": UP_PIPELINE}})])
    t = synced(stage="lost")
    before = copy.deepcopy(t)
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert actions == []
    assert [e["code"] for e in errors] == ["ghl_not_configured"] and errors[0]["room_id"] is None
    assert ghl_sync.read_back_stage(t, client) is None
    assert rec.requests == [] and job_rows() == [] and job_log.read_shadow_log() == []
    assert t == before and state == before["ghl"]
    assert ghl_sync.mirror_status()["code"] == "ghl_not_configured"


@pytest.mark.parametrize("pipeline_id,stages,where", [
    (SALES_REQUESTS["id"], dict(S), "pipelines.sales_requests.id"),            # the reviewer's case
    (" %s " % SALES_REQUESTS["id"], dict(S), "pipelines.sales_requests.id"),   # padded, still the same id
    (UP_PIPELINE, dict(S, won=SALES_REQUESTS["stages"]["replied"]), "pipelines.sales_requests.stages.replied"),
    (settings.GHL_STAGES["won"], dict(S), "pipelines.sales.stages.won"),       # a Sales STAGE id as the pipeline id
    (UP_PIPELINE, dict(S, lost=SALES_PIPELINE), "pipelines.sales.id"),         # the Sales pipeline id as a stage id
    (UP_PIPELINE, dict(S, won={"id": settings.GHL_STAGES["won"]}), "pipelines.sales.stages.won"),
    (OTHER["id"], dict(S), "pipelines.other_demo.id"),                          # any pipeline, not only Sales
    (UP_PIPELINE, dict(S, call_booked=OTHER["stages"]["alpha"]), "pipelines.other_demo.stages.alpha"),
    (UP_PIPELINE, dict(S, call_booked=OTHER["stages"]["beta"]["id"]), "pipelines.other_demo.stages.beta"),
])
def test_an_id_any_other_pipeline_uses_keeps_the_mirror_off(tmp_env, monkeypatch, fake_live, verified,
                                                           pipeline_id, stages, where):
    ids = upwork_ids(pipeline_id=pipeline_id, stages=stages)
    ids["ghl"]["pipelines"]["other_demo"] = copy.deepcopy(OTHER)
    monkeypatch.setattr(settings, "IDS", ids)
    conf, reason = ghl_sync.upwork_pipeline()
    assert conf is None and where in reason
    assert ghl_sync.mirror_status()["code"] == "ghl_not_configured"
    client, rec = make()
    _, actions, errors = ghl_sync.sync_thread(thread(), ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_not_configured"]
    assert rec.requests == [] and job_rows() == []


def test_other_pipelines_do_not_block_distinct_upwork_ids(monkeypatch):
    ids = upwork_ids()
    ids["ghl"]["pipelines"]["other_demo"] = copy.deepcopy(OTHER)
    monkeypatch.setattr(settings, "IDS", ids)
    assert ghl_sync.upwork_pipeline() == ({"id": UP_PIPELINE, "stages": S}, None)


def test_the_same_id_on_two_upwork_stages_keeps_the_mirror_off(tmp_env, monkeypatch, fake_live, verified):
    """Note 4: two stage keys sharing one id could not be read back apart."""
    monkeypatch.setattr(settings, "IDS", upwork_ids(stages=dict(S, lost=S["won"])))
    conf, reason = ghl_sync.upwork_pipeline()
    assert conf is None and reason == "ghl.pipelines.upwork has the same id on two stages (won, lost)"
    monkeypatch.setattr(settings, "IDS", upwork_ids(stages={k: {"id": "one-id"} for k in S}))
    assert "same id on two stages (%s)" % ", ".join(ghl_sync.STAGE_KEYS) in ghl_sync.upwork_pipeline()[1]
    client, rec = make()
    _, actions, errors = ghl_sync.sync_thread(synced(stage="lost"), ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_not_configured"] and rec.requests == []


def test_unconfigured_mirror_with_the_real_ids_json_does_nothing(tmp_env, shadow_mode):
    client, rec = make()
    state, actions, errors = ghl_sync.sync_thread(thread(), ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_not_configured"]
    assert rec.requests == [] and job_log.read_shadow_log() == []


def test_mirror_status_is_none_once_configured(upwork):
    assert ghl_sync.mirror_status() is None
    conf, reason = ghl_sync.upwork_pipeline()
    assert reason is None and conf == {"id": UP_PIPELINE, "stages": S}


def test_stage_entries_may_be_id_objects(monkeypatch):
    monkeypatch.setattr(settings, "IDS", upwork_ids(stages={k: {"id": v, "name": k} for k, v in S.items()}))
    assert ghl_sync.upwork_pipeline()[0]["stages"] == S


# ============================================================ Sales tripwire
def test_contact_without_email_is_not_verified_while_upwork_could_land_in_sales():
    """Tripwire: CONTACT_WITHOUT_EMAIL_VERIFIED may only be True once the
    separate Upwork pipeline is configured in config/ids.json."""
    if ghl_mod.CONTACT_WITHOUT_EMAIL_VERIFIED:
        conf, reason = ghl_sync.upwork_pipeline()
        assert conf is not None, "CONTACT_WITHOUT_EMAIL_VERIFIED flipped before the Upwork pipeline exists: %s" % reason
    else:
        assert ghl_mod.CONTACT_WITHOUT_EMAIL_VERIFIED is False


def test_ghl_sync_never_sends_a_sales_pipeline_or_stage_id(tmp_env, upwork, monkeypatch, verified):
    """No request, body or shadow row carries an id of any other pipeline in
    ids.json (Sales, Sales Requests); every live stage move reads first."""
    live = {"on": True}
    monkeypatch.setattr(settings, "is_live", lambda: live["on"])
    fake = FakeGHL()
    client = GHL(token="tok", transport=httpx.MockTransport(fake))
    t = thread()
    ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    for stage in ("proposal_sent", "call_booked", "won", "lost", "follow_up_later"):
        t["stage"] = stage
        _, _, errs = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
        assert errs == [] and t["ghl"]["stage"] == stage == fake.stage()
    live["on"] = False
    t2 = thread()
    t2["room_id"] = "room_0000feedc0df"
    ghl_sync.sync_thread(t2, ROOM, client, NOW, dry_run=False)
    t2["stage"] = "won"
    ghl_sync.sync_thread(t2, ROOM, client, NOW, dry_run=False)
    blob = json.dumps([r.content.decode("utf-8") for r in fake.requests] + [str(r.url) for r in fake.requests]
                      + [job_log.read_shadow_log()])
    assert len(fake.requests) == 12 and fake.puts() == 5
    assert [m for m, _ in fake.log[2:]] == ["GET", "PUT"] * 5
    assert [i for i in other_pipeline_ids() if i in blob] == []
    assert UP_PIPELINE in blob and S["won"] in blob
    for r in fake.requests:
        if r.url.path == "/opportunities/upsert":
            assert body_of(r)["pipelineId"] == UP_PIPELINE


# ==================================================================== create
def test_create_in_shadow_records_the_would_do_rows(tmp_env, upwork, shadow_mode):
    client, rec = make()
    t = thread()
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)

    assert errors == []
    assert rec.requests == []
    assert [(a["action"], a["kind"]) for a in actions] == [("upsert_contact", "would_do"),
                                                            ("upsert_opportunity", "would_do")]
    assert actions[0]["at"] == "2026-09-23T13:30:00+00:00"

    rows = job_log.read_shadow_log()
    assert [r["action"] for r in rows] == ["upsert_contact", "upsert_opportunity"]
    contact, opp = rows[0]["payload"], rows[1]["payload"]
    assert contact == {"locationId": LOCATION, "name": CLIENT, "tags": ["upwork"], "source": "Upwork"}
    assert "email" not in contact
    assert opp == {
        "locationId": LOCATION, "contactId": "shadow:contact:%s" % ROOM_ID, "pipelineId": UP_PIPELINE,
        "pipelineStageId": S["new_reply"], "name": "Northwind Kiln Studio (Upwork)", "status": "open",
    }
    assert state == {"contact_id": "shadow:contact:%s" % ROOM_ID,
                     "opportunity_id": "shadow:opportunity:%s" % ROOM_ID, "stage": "new_reply"}
    assert t["ghl"] == state


def test_create_at_the_threads_stage(tmp_env, upwork, shadow_mode):
    client, _ = make()
    ghl_sync.sync_thread(thread(stage="follow_up_later"), ROOM, client, NOW, dry_run=False)
    opp = job_log.read_shadow_log()[-1]["payload"]
    assert opp["pipelineStageId"] == S["follow_up_later"] and opp["status"] == "open"


def test_second_run_is_idempotent(tmp_env, upwork, shadow_mode):
    client, rec = make()
    t = thread()
    ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    before = copy.deepcopy(t)
    n = len(job_log.read_shadow_log())
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert (actions, errors) == ([], [])
    assert t == before and state == before["ghl"]
    assert len(job_log.read_shadow_log()) == n
    assert rec.requests == []


def test_existing_ids_do_no_create(tmp_env, upwork, fake_live):
    client, rec = make()
    state, actions, errors = ghl_sync.sync_thread(synced(), ROOM, client, NOW, dry_run=False)
    assert (actions, errors) == ([], [])
    assert rec.requests == []
    assert state == {"contact_id": "c-41", "opportunity_id": "o-41", "stage": "new_reply"}


def test_live_create_once_verified_stores_the_real_ids(tmp_env, upwork, fake_live, verified):
    client, rec = make(responses=[(200, {"contact": {"id": "c-77"}}), (200, {"opportunity": {"id": "o-77"}})])
    # shadow placeholders from before go-live count as "no id" in live
    t = thread(ghl={"contact_id": "shadow:contact:%s" % ROOM_ID,
                    "opportunity_id": "shadow:opportunity:%s" % ROOM_ID, "stage": "new_reply"})
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert errors == []
    assert [(a["action"], a["kind"]) for a in actions] == [("upsert_contact", "done"), ("upsert_opportunity", "done")]
    r0, r1 = rec.requests
    assert "email" not in body_of(r0)
    assert body_of(r1)["contactId"] == "c-77" and body_of(r1)["pipelineStageId"] == S["new_reply"]
    assert body_of(r1)["pipelineId"] == UP_PIPELINE
    assert state == {"contact_id": "c-77", "opportunity_id": "o-77", "stage": "new_reply"}


def test_live_contact_without_email_is_refused_while_unverified(tmp_env, upwork, fake_live):
    assert ghl_mod.CONTACT_WITHOUT_EMAIL_VERIFIED is False
    client, rec = make()
    t = thread()
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert [e["code"] for e in errors] == ["ghl_contact_needs_identity"]
    assert [(a["action"], a["kind"]) for a in actions] == [("upsert_contact", "failed")]
    assert rec.requests == []
    assert [(r["job"], r["status"]) for r in job_rows()] == [("ghl.upsert_contact", "ghl_contact_needs_identity")]
    assert state == {"contact_id": None, "opportunity_id": None, "stage": None}
    assert t["ghl"] == state


def test_C4_unverified_live_with_placeholders_two_runs_change_nothing(tmp_env, upwork, fake_live):
    client, rec = make()
    t = {"room_id": "r4", "client": CLIENT, "stage": "proposal_sent", "stage_set_by": "engine",
         "ghl": {"contact_id": "shadow:contact:r4", "opportunity_id": "shadow:opportunity:r4", "stage": "new_reply"}}
    before = json.dumps(t, sort_keys=True)
    for _ in range(2):
        _, _, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
        assert [e["code"] for e in errs] == ["ghl_contact_needs_identity"]
    assert ghl_sync.read_back_stage(t, client) is None
    assert rec.requests == [] and json.dumps(t, sort_keys=True) == before
    assert [r["status"] for r in job_rows()] == ["ghl_contact_needs_identity"] * 2


# ============================================================ blocked threads
@pytest.mark.parametrize("contact_reply,opp_reply,posts", [
    ({"new": True}, None, 1),                                  # contact upsert answers without an id
    ({"contact": {"id": "c-5"}}, {"opportunity": {}}, 2),      # opportunity upsert answers without an id
])
def test_C5_live_create_without_an_id_blocks_and_every_later_run_reports_it(tmp_env, upwork, fake_live, verified,
                                                                            contact_reply, opp_reply, posts):
    replies = [(200, contact_reply)] + ([(200, opp_reply)] if opp_reply is not None else [])
    client, rec = make(responses=replies)
    t = thread()
    _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
    assert [e["code"] for e in errs] == ["ghl_no_id_returned"]
    assert "ghl_blocked" in errs[0]["detail"]
    assert t["ghl"]["blocked"] == "ghl_no_id_returned"
    for _ in range(3):
        state, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
        assert acts == [] and [e["code"] for e in errs] == ["ghl_blocked"]
        err = errs[0]
        assert (err["room_id"], err["blocked"], err["stage"], err["ghl_stage"]) == (
            ROOM_ID, "ghl_no_id_returned", "new_reply", None)
        assert "ghl_no_id_returned (a live create answered without an id)" in err["detail"]
        assert "Stage new_reply waits to be mirrored" in err["detail"]
        assert "delete ghl.blocked (runbooks/upwork_followup.md, GHL mirror recovery)." in err["detail"]
        assert len(err["detail"]) < 400                      # never cut off
        assert state["blocked"] == "ghl_no_id_returned"
    assert len(rec.requests) == posts
    assert sum(1 for r in rec.requests if r.url.path == "/contacts/upsert") == 1
    assert ghl_sync.read_back_stage(t, client) is None
    assert len(rec.requests) == posts


@pytest.mark.parametrize("hand_filled", [False, True])
def test_a_cli_move_on_a_blocked_thread_is_reported_and_sends_nothing(tmp_env, upwork, fake_live, verified,
                                                                      hand_filled):
    """Reviewer round 2: a --stage move on a blocked thread was never mirrored
    and never reported, even after the ids were filled in by hand."""
    client, rec = make(responses=[(200, {"contact": {"id": "c-5"}}), (200, {"opportunity": {}})])
    t = thread()
    ghl_sync.sync_thread(t, None, client, NOW, False)          # the opportunity create answers without an id
    assert t["ghl"]["blocked"] == "ghl_no_id_returned"
    if hand_filled:
        t["ghl"]["opportunity_id"] = "o-5"                      # ids filled in by hand, blocked left in place
    n = len(rec.requests)
    t["stage"], t["stage_set_by"] = "won", "lorenzo"            # --stage: the client hired him
    for _ in range(2):
        _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False,
                                             engine_actions=[{"type": "ghl_stage", "stage": "won", "by": "lorenzo"}])
        assert acts == [] and [e["code"] for e in errs] == ["ghl_blocked"]
        assert errs[0]["stage"] == "won" and "Stage won waits to be mirrored" in errs[0]["detail"]
    assert len(rec.requests) == n
    assert t["ghl"]["blocked"] == "ghl_no_id_returned"


@pytest.mark.parametrize("mode", ["live", "shadow", "dry_run"])
def test_a_blocked_thread_is_reported_in_every_mode_without_a_request(tmp_env, upwork, monkeypatch, verified, mode):
    monkeypatch.setattr(settings, "is_live", lambda: mode == "live")
    client, rec = make()
    t = thread(stage="call_booked", set_by="lorenzo",
               ghl={"contact_id": "c-5", "opportunity_id": "o-5", "stage": "call_booked",
                    "blocked": "ghl_no_id_returned"})
    before = copy.deepcopy(t)
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=(mode == "dry_run"))
    assert actions == [] and [e["code"] for e in errors] == ["ghl_blocked"]
    assert "Nothing waits: GHL is known to hold stage call_booked" in errors[0]["detail"]
    assert rec.requests == [] and job_rows() == [] and job_log.read_shadow_log() == []
    assert t == before and state == before["ghl"]


def test_a_blocked_thread_reaches_the_batch_and_the_status_through_the_tick(tmp_env, upwork, fake_live):
    """tick._ghl_sync forwards only sync_thread's errors: the ghl_blocked entry
    is what makes a blocked thread visible in the batch on every run."""
    from services.upwork_followup import tick as tick_module
    from shared.store import JsonFileStore

    store = JsonFileStore(tmp_env / "store.json")
    t = thread(stage="won", set_by="lorenzo",
               ghl={"contact_id": "c-5", "opportunity_id": None, "stage": None, "blocked": "ghl_no_id_returned"})
    store.set("upwork:%s" % ROOM_ID, t)
    client, rec = make()
    for _ in range(2):
        result = tick_module._new_result(NOW, "run")
        tick_module._ghl_sync(store, {ROOM_ID: {"room": ROOM, "acts": []}}, [ROOM_ID], NOW, client, result)
        assert [e["code"] for e in result["ghl_errors"]] == ["ghl_blocked"]
        assert tick_module._status(result) == "attention"
        text = tick_module.render_batch(result, [], [], NOW)
        assert "## GHL mirror errors" in text
        assert "- ghl_blocked | room %s | GHL mirror blocked: ghl_no_id_returned" % ROOM_ID in text
        assert "Stage won waits to be mirrored" in text
    assert rec.requests == [] and store.get("upwork:%s" % ROOM_ID) == t


def test_C3_no_private_or_message_text_reaches_ghl(tmp_env, upwork, fake_live, verified):
    secret = ["SECRET_MSG_TEXT", "SECRET_PRIVATE_NOTES", "SECRET_ASK", "SECRET_JOB_POST", "SECRET_PENDING",
              "SECRET_HISTORY", "SECRET_TITLE", "SECRET_PROPOSAL"]
    room = {"room_id": "r3", "client": CLIENT, "job_title": "SECRET_TITLE",
            "messages": [{"id": "m1", "side": "client", "at": "2026-09-20T00:00:00Z", "text": "SECRET_MSG_TEXT"}],
            "job": {"post": "SECRET_JOB_POST", "proposal": "SECRET_PROPOSAL", "ask_before_quoting": ["SECRET_ASK"],
                    "private_notes": "SECRET_PRIVATE_NOTES"}}
    t = {"room_id": "r3", "client": CLIENT, "stage": "new_reply", "stage_set_by": "engine",
         "pending": {"kind": "touch", "text": "SECRET_PENDING"}, "history": [{"event": "SECRET_HISTORY"}],
         "ghl": {"contact_id": None, "opportunity_id": None, "stage": None}}
    client, rec = make(responses=[(200, {"contact": {"id": "c-3"}}), (200, {"opportunity": {"id": "o-3"}})])
    _, acts, errs = ghl_sync.sync_thread(t, room, client, NOW, False)
    blob = json.dumps([r.content.decode() for r in rec.requests] + [acts, errs, job_rows(), job_log.read_shadow_log()])
    assert [s for s in secret if s in blob] == []


def test_C2_reads_use_the_read_key_and_writes_the_write_key(tmp_env, upwork, fake_live, verified):
    at_call_booked = {"opportunity": {"id": "o-9", "pipelineStageId": S["call_booked"], "pipelineId": UP_PIPELINE}}
    client, rec = make(responses=[
        (200, {"contact": {"id": "c-9"}}), (200, {"opportunity": {"id": "o-9"}}),
        (200, at_call_booked),                   # the read-back
        (200, at_call_booked),                   # the read before the stage write
        (200, {"opportunity": {"id": "o-9"}})], read_token="rtok", write_token="wtok")
    t = thread()
    ghl_sync.sync_thread(t, None, client, NOW, False)
    assert ghl_sync.read_back_stage(t, client) == "call_booked"
    t["stage"], t["stage_set_by"] = "call_booked", "ghl"          # the tick applies the read-back
    ghl_sync.sync_thread(t, None, client, NOW, False)             # recorded, no request
    t["stage"], t["stage_set_by"] = "lost", "lorenzo"             # then a CLI move
    _, _, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
    assert errs == [] and t["ghl"]["stage"] == "lost"
    auth = [(r.method, r.headers.get("Authorization")) for r in rec.requests]
    assert [m for m, _ in auth] == ["POST", "POST", "GET", "GET", "PUT"]
    assert all(a == "Bearer wtok" for m, a in auth if m != "GET")
    assert all(a == "Bearer rtok" for m, a in auth if m == "GET")


# ============================================================== stage moves
def test_engine_stage_change_on_a_placeholder_updates_once(tmp_env, upwork, shadow_mode):
    client, rec = make()
    t = thread()
    ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    t["stage"] = "proposal_sent"
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert errors == []
    assert [(a["action"], a["kind"]) for a in actions] == [("update_opportunity_stage", "would_do")]
    row = job_log.read_shadow_log()[-1]
    assert row["payload"] == {"pipelineStageId": S["proposal_sent"], "status": "open",
                              "opportunity_id": "shadow:opportunity:%s" % ROOM_ID}
    assert state["stage"] == "proposal_sent" and t["ghl"]["stage"] == "proposal_sent"
    _, again, _ = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert again == [] and rec.requests == []


@pytest.mark.parametrize("stage,status", [("won", "won"), ("lost", "lost"), ("call_booked", "open")])
def test_stage_update_live_reads_first_then_sends_the_stage_id_and_status(tmp_env, upwork, fake_live, stage, status):
    client, rec = make(responses=[(200, opp_response(S["new_reply"])), (200, {"opportunity": {"id": "o-41"}})],
                       read_token="rtok", write_token="wtok")
    state, actions, errors = ghl_sync.sync_thread(synced(stage=stage), ROOM, client, NOW, dry_run=False)
    assert errors == []
    assert [(a["action"], a["kind"]) for a in actions] == [("update_opportunity_stage", "done")]
    get, put = rec.requests
    assert (get.method, get.url.path, get.headers["Authorization"]) == ("GET", "/opportunities/o-41", "Bearer rtok")
    assert (put.method, put.url.path, put.headers["Authorization"]) == ("PUT", "/opportunities/o-41", "Bearer wtok")
    assert body_of(put) == {"pipelineStageId": S[stage], "status": status}
    assert state["stage"] == stage


def test_shadow_would_do_on_a_real_opportunity_does_not_advance_the_known_stage(tmp_env, upwork, shadow_mode):
    client, rec = make()
    t = synced(stage="lost")
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert [(a["action"], a["kind"]) for a in actions] == [("update_opportunity_stage", "would_do")]
    assert errors == [] and rec.requests == []
    assert state["stage"] == "new_reply" and t["ghl"]["stage"] == "new_reply"


@pytest.mark.parametrize("reply", [{"succeded": False}, {"succeeded": False}, {"success": False}])
def test_live_rejection_body_is_an_error_and_does_not_advance(tmp_env, upwork, fake_live, reply):
    client, _ = make(responses=[(200, opp_response(S["new_reply"])), (200, reply)])
    t = synced(stage="lost")
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert [e["code"] for e in errors] == ["ghl_write_rejected"]
    assert actions[0]["kind"] == "failed"
    assert state["stage"] == "new_reply"


def test_live_rejected_create_is_retried_not_blocked(tmp_env, upwork, fake_live, verified):
    client, rec = make(responses=[(200, {"succeded": False}), (200, {"contact": {"id": "c-1"}}),
                                  (200, {"opportunity": {"id": "o-1"}})])
    t = thread()
    _, _, errs = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert [e["code"] for e in errs] == ["ghl_write_rejected"] and "blocked" not in t["ghl"]
    state, _, errs = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert errs == [] and state == {"contact_id": "c-1", "opportunity_id": "o-1", "stage": "new_reply"}


def test_live_stage_write_failure_is_an_error_and_keeps_the_old_stage(tmp_env, upwork, fake_live):
    client, _ = make(responses=[(200, opp_response(S["new_reply"])), (500, {"message": "boom"})])
    state, actions, errors = ghl_sync.sync_thread(synced(stage="won"), ROOM, client, NOW, dry_run=False)
    assert [e["code"] for e in errors] == ["ghl_write_failed"]
    assert actions[0]["kind"] == "failed"
    assert state["stage"] == "new_reply"


def test_a_stage_that_came_from_ghl_is_not_echoed(tmp_env, upwork, fake_live):
    client, rec = make()
    t = synced(stage="call_booked", set_by="ghl")
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert (actions, errors) == ([], [])
    assert rec.requests == [] and job_rows() == []
    assert state["stage"] == "call_booked" and t["ghl"]["stage"] == "call_booked"
    client2, _ = make(responses=[(200, {"opportunity": {"pipelineStageId": S["call_booked"],
                                                        "pipelineId": UP_PIPELINE}})])
    assert ghl_sync.read_back_stage(t, client2) is None


def test_a_cli_move_by_lorenzo_is_pushed(tmp_env, upwork, shadow_mode):
    client, _ = make()
    _, actions, _ = ghl_sync.sync_thread(synced(stage="call_booked", set_by="lorenzo"), ROOM, client, NOW,
                                         dry_run=False)
    assert [a["action"] for a in actions] == ["update_opportunity_stage"]
    assert actions[0]["payload"]["stage_id"] == S["call_booked"]


def test_matching_engine_action_is_fine(tmp_env, upwork, fake_live):
    client, rec = make(responses=[(200, opp_response(S["new_reply"])), (200, {"opportunity": {"id": "o-41"}})])
    acts = [{"type": "ghl_stage", "stage": "new_reply", "by": "engine"}, {"type": "ghl_stage", "stage": "lost"}]
    _, actions, errors = ghl_sync.sync_thread(synced(stage="lost"), ROOM, client, NOW, False, engine_actions=acts)
    assert errors == [] and [a["kind"] for a in actions] == ["done"]


@pytest.mark.parametrize("set_by", ["engine", "lorenzo", "ghl"])
def test_C1_engine_action_that_disagrees_with_the_thread_is_an_error_and_no_write(tmp_env, upwork, fake_live,
                                                                                    set_by):
    client, rec = make()
    t = synced(stage="call_booked", mirrored="call_booked", set_by=set_by)
    before = copy.deepcopy(t)
    state, actions, errors = ghl_sync.sync_thread(t, None, client, NOW, False,
                                                  engine_actions=[{"type": "ghl_stage", "stage": "lost"}])
    assert actions == [] and [e["code"] for e in errors] == ["ghl_stage_action_mismatch"]
    ghl_sync.sync_thread(t, None, client, NOW, False)
    assert rec.requests == [] and job_rows() == []
    assert t == before and state == before["ghl"]


# ================================== read before a live stage write (note 2)
@pytest.mark.parametrize("answer,kind,seen", [
    (opp_response(S["call_booked"]), "stage", "call_booked"),                        # he moved the card in GHL
    (opp_response(S["new_reply"], status="lost"), "stage", "lost"),                  # he closed it with the status
    (opp_response(S["new_reply"], status="abandoned"), "stage", "lost"),             # he abandoned it
    (opp_response("stage-id-nobody-knows"), "unknown_stage", "stage-id-nobody-knows"),   # a column added in GHL
    (opp_response(S["new_reply"], pipeline=SALES_PIPELINE), "other_pipeline", SALES_PIPELINE),
    (opp_response(S["new_reply"], pipeline="another-pipeline"), "other_pipeline", "another-pipeline"),
])
def test_live_write_is_refused_when_ghl_no_longer_shows_the_last_mirrored_stage(tmp_env, upwork, fake_live,
                                                                                 answer, kind, seen):
    client, rec = make(responses=[(200, answer)])
    t = synced(stage="proposal_sent", mirrored="new_reply")      # an engine move waiting to be pushed
    before = copy.deepcopy(t)
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_stage_conflict"]
    err = errors[0]
    assert (err["room_id"], err["stage"], err["ghl_stage"], err["seen"]["kind"]) == (
        ROOM_ID, "proposal_sent", "new_reply", kind)
    assert seen in err["detail"] and "not written" in err["detail"] and len(err["detail"]) < 400
    assert [r.method for r in rec.requests] == ["GET"]
    assert t == before and state == before["ghl"]


@pytest.mark.parametrize("responses", [
    [(503, {"message": "down"})],                 # GHL down
    [(404, {"message": "not found"})],            # deleted in GHL
    [(200, {"ok": True})],                        # no stage in the answer
    [(200, {})],                                  # an empty answer
])
def test_live_write_is_refused_when_the_opportunity_cannot_be_read(tmp_env, upwork, fake_live, responses):
    client, rec = make(responses=responses)
    t = synced(stage="lost")
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_read_failed"]
    assert errors[0]["stage"] == "lost" and "The next run tries again" in errors[0]["detail"]
    assert [r.method for r in rec.requests] == ["GET"]
    assert state["stage"] == "new_reply"


@pytest.mark.parametrize("answer", ["raises", "none", "garbage"])
def test_live_write_is_refused_when_the_read_raises_or_returns_nothing(tmp_env, upwork, fake_live, answer):
    class Reader(object):
        def __init__(self):
            self.writes = []

        def get_opportunity(self, opportunity_id):
            if answer == "raises":
                raise RuntimeError("socket closed")
            return None if answer == "none" else ["not", "a", "dict"]

        def update_opportunity_stage(self, *a, **k):
            self.writes.append(a)
            return {"opportunity": {"id": "o-41"}}

    reader = Reader()
    _, actions, errors = ghl_sync.sync_thread(synced(stage="lost"), ROOM, reader, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_read_failed"] and reader.writes == []


def test_live_write_is_skipped_when_ghl_already_shows_the_threads_stage(tmp_env, upwork, fake_live):
    client, rec = make(responses=[(200, opp_response(S["call_booked"]))])
    t = synced(stage="call_booked", set_by="lorenzo")
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert (actions, errors) == ([], [])
    assert [r.method for r in rec.requests] == ["GET"]
    assert state["stage"] == "call_booked" and t["ghl"]["stage"] == "call_booked"


def test_live_write_goes_through_over_an_abandoned_status_already_read_as_lost(tmp_env, upwork, fake_live):
    """GHL holds lost (by an abandoned status) and the mirror last wrote lost:
    no GHL move since, so Lorenzo's CLI reopen is pushed."""
    client, rec = make(responses=[(200, opp_response(S["lost"], status="abandoned")),
                                  (200, {"opportunity": {"id": "o-41"}})])
    _, _, errors = ghl_sync.sync_thread(synced(stage="new_reply", mirrored="lost", set_by="lorenzo"), ROOM, client,
                                        NOW, dry_run=False)
    assert errors == [] and [r.method for r in rec.requests] == ["GET", "PUT"]
    assert body_of(rec.requests[1]) == {"pipelineStageId": S["new_reply"], "status": "open"}


def test_shadow_and_dry_run_never_read_before_a_stage_write(tmp_env, upwork, monkeypatch):
    for live, dry in ((True, True), (False, True), (False, False)):
        monkeypatch.setattr(settings, "is_live", lambda live=live: live)
        client, rec = make()
        _, actions, errors = ghl_sync.sync_thread(synced(stage="lost"), ROOM, client, NOW, dry_run=dry)
        assert errors == [] and rec.requests == []
        assert [a["kind"] for a in actions] == ["planned" if dry else "would_do"]


# ================================================================ errors, dry run
@pytest.mark.parametrize("stage", ["negotiating", None, ""])
def test_unknown_stage_is_an_error_and_no_write(tmp_env, upwork, shadow_mode, stage):
    client, rec = make()
    t = thread(stage=stage)
    before = copy.deepcopy(t)
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert actions == []
    assert [e["code"] for e in errors] == ["ghl_unknown_stage"] and errors[0]["room_id"] == ROOM_ID
    assert rec.requests == [] and job_log.read_shadow_log() == []
    assert t == before


def test_unknown_stage_on_an_existing_opportunity_writes_nothing(tmp_env, upwork, fake_live):
    client, rec = make()
    _, actions, errors = ghl_sync.sync_thread(synced(stage="negotiating"), ROOM, client, NOW, dry_run=False)
    assert actions == [] and errors[0]["code"] == "ghl_unknown_stage"
    assert rec.requests == [] and job_rows() == []


def test_dry_run_plans_and_calls_nothing(tmp_env, upwork, shadow_mode):
    client, rec = make()
    t = thread()
    before = copy.deepcopy(t)
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=True)
    assert errors == []
    assert [(a["action"], a["kind"]) for a in actions] == [("upsert_contact", "planned"),
                                                            ("upsert_opportunity", "planned")]
    assert actions[1]["payload"]["name"] == "Northwind Kiln Studio (Upwork)"
    assert actions[1]["payload"]["pipeline_id"] == UP_PIPELINE
    assert rec.requests == [] and job_log.read_shadow_log() == []
    assert t == before and state == before["ghl"]


# ================================================================== read-back
def test_read_back_returns_a_stage_lorenzo_set_in_ghl(tmp_env, upwork):
    client, rec = make(responses=[(200, opp_response(S["call_booked"]))], read_token="rtok", write_token="wtok")
    assert ghl_sync.read_back_stage(synced(), client) == "call_booked"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("GET", "/opportunities/o-41")
    assert req.headers["Authorization"] == "Bearer rtok"


@pytest.mark.parametrize("key", ghl_sync.STAGE_KEYS)
def test_read_back_maps_every_upwork_stage_id(tmp_env, upwork, key):
    other = "lost" if key != "lost" else "won"
    status = key if key in ("won", "lost") else "open"
    client, _ = make(responses=[(200, opp_response(S[key], status=status))])
    assert ghl_sync.read_back_stage(synced(stage=other, mirrored=other), client) == key


def test_read_back_a_sales_stage_id_is_unknown(tmp_env, upwork):
    client, _ = make(responses=[(200, opp_response(settings.GHL_STAGES["call_booked"]))])
    assert ghl_sync.read_back_stage(synced(), client) is None


def test_read_back_accepts_a_bare_opportunity_body(tmp_env, upwork):
    client, _ = make(responses=[(200, {"id": "o-41", "pipelineStageId": S["proposal_sent"]})])
    assert ghl_sync.read_back_stage(synced(), client) == "proposal_sent"


def test_read_back_none_when_ghl_matches_the_thread(tmp_env, upwork):
    client, _ = make(responses=[(200, opp_response(S["new_reply"]))])
    assert ghl_sync.read_back_stage(synced(), client) is None


def test_read_back_none_when_the_thread_moved_since_the_known_stage(tmp_env, upwork):
    client, _ = make(responses=[(200, opp_response(S["new_reply"]))])
    assert ghl_sync.read_back_stage(synced(stage="proposal_sent", mirrored="new_reply"), client) is None


@pytest.mark.parametrize("status,stage", [("won", "won"), ("lost", "lost"), ("abandoned", "lost"),
                                          ("Abandoned", "lost")])
def test_note3_a_won_lost_or_abandoned_status_reads_back_as_that_stage(tmp_env, upwork, status, stage):
    """Note 6 (round 2): abandoned is Lorenzo dropping the deal; it reads as lost."""
    client, _ = make(responses=[(200, opp_response(S["new_reply"], status=status))])
    assert ghl_sync.read_back_stage(synced(), client) == stage


def test_read_back_of_abandoned_is_none_once_lost_is_known(tmp_env, upwork):
    client, _ = make(responses=[(200, opp_response(S["lost"], status="abandoned"))])
    assert ghl_sync.read_back_stage(synced(stage="lost", mirrored="lost"), client) is None


def test_C6_status_only_lost_in_ghl_is_adopted_and_not_reopened(tmp_env, upwork, fake_live):
    """Lorenzo marks the opportunity Lost with GHL's status control (stage
    column unchanged): read back as lost, recorded, never pushed as open."""
    client, rec = make(responses=[(200, opp_response(S["new_reply"], status="lost")),
                                  (200, opp_response(S["new_reply"], status="lost"))])
    t = synced()
    assert ghl_sync.read_back_stage(t, client) == "lost"
    t["stage"], t["stage_set_by"] = "lost", "ghl"   # sequence.apply_external_stage(..., by="ghl")
    state, actions, errors = ghl_sync.sync_thread(t, None, client, NOW, False)
    assert (actions, errors) == ([], []) and state["stage"] == "lost"
    assert ghl_sync.read_back_stage(t, client) is None
    assert [r.method for r in rec.requests] == ["GET", "GET"]


def test_read_back_unknown_stage_id_is_none(tmp_env, upwork, caplog):
    client, _ = make(responses=[(200, opp_response("stage-id-nobody-knows"))])
    with caplog.at_level("WARNING"):
        assert ghl_sync.read_back_stage(synced(), client) is None
    assert "unknown stage id" in caplog.text


@pytest.mark.parametrize("pipeline", [SALES_PIPELINE, "another-pipeline"])
def test_read_back_other_pipeline_is_none(tmp_env, upwork, pipeline):
    client, _ = make(responses=[(200, opp_response(S["won"], pipeline=pipeline, status="won"))])
    assert ghl_sync.read_back_stage(synced(), client) is None


@pytest.mark.parametrize("ghl_state", [
    {"contact_id": None, "opportunity_id": None, "stage": None},
    {"contact_id": "shadow:contact:x", "opportunity_id": "shadow:opportunity:x", "stage": "new_reply"},
    None,
])
def test_read_back_none_without_a_real_opportunity(tmp_env, upwork, ghl_state):
    client, rec = make()
    t = thread()
    if ghl_state is None:
        t.pop("ghl")
    else:
        t["ghl"] = ghl_state
    assert ghl_sync.read_back_stage(t, client) is None
    assert rec.requests == []


def test_read_back_reads_a_blocked_thread_once_its_id_is_filled_in(tmp_env, upwork):
    """The docstring as corrected: blocked stops the sync only. A blocked
    thread usually has no opportunity id; a hand-filled one is read back."""
    client, rec = make(responses=[(200, opp_response(S["call_booked"]))])
    t = synced()
    t["ghl"]["blocked"] = "ghl_no_id_returned"
    assert ghl_sync.read_back_stage(t, client) == "call_booked"
    assert [r.method for r in rec.requests] == ["GET"]


def test_read_back_none_without_a_client_or_token(tmp_env, upwork):
    assert ghl_sync.read_back_stage(synced(), None) is None
    client, rec = make(token=None)
    assert ghl_sync.read_back_stage(synced(), client) is None
    assert rec.requests == []


def test_read_back_http_error_returns_none(tmp_env, upwork):
    client, _ = make(responses=[(500, {"message": "down"})])
    assert ghl_sync.read_back_stage(synced(), client) is None


class Exploding(object):
    def get_opportunity(self, opportunity_id):
        raise RuntimeError("socket closed")


class Garbage(object):
    def get_opportunity(self, opportunity_id):
        return ["not", "a", "dict"]


def test_read_back_never_raises(tmp_env, upwork):
    assert ghl_sync.read_back_stage(synced(), Exploding()) is None
    assert ghl_sync.read_back_stage(synced(), Garbage()) is None
    assert ghl_sync.read_back_stage({"ghl": "broken"}, Exploding()) is None
    assert ghl_sync.read_back_stage(None, Exploding()) is None


# ======================================== loop safety (reviewer probes S1-S12)
class FakeGHL(object):
    """A stateful GHL holding the opportunities."""

    def __init__(self):
        self.opps = {}
        self.contacts = 0
        self.log = []
        self.requests = []
        self.put_reply = None        # e.g. {"succeded": False}: 200 but not applied
        self.put_status = 200
        self.get_status = 200        # e.g. 503: every GET fails
        self.get_failures = 0        # the next N GETs fail with a 503
        self.opp_without_id = False  # the opportunity upsert creates it but answers without its id

    def __call__(self, request):
        path, method = request.url.path, request.method
        self.log.append((method, path))
        self.requests.append(request)
        if method == "POST" and path == "/contacts/upsert":
            self.contacts += 1
            return httpx.Response(200, json={"contact": {"id": "c-%d" % self.contacts}})
        if method == "POST" and path == "/opportunities/upsert":
            body = json.loads(request.content.decode("utf-8"))
            oid = "o-%d" % (len(self.opps) + 1)
            self.opps[oid] = {"id": oid, "pipelineStageId": body["pipelineStageId"], "pipelineId": body["pipelineId"],
                              "status": body["status"]}
            if self.opp_without_id:
                return httpx.Response(200, json={"opportunity": {}})
            return httpx.Response(200, json={"opportunity": dict(self.opps[oid])})
        if path.startswith("/opportunities/"):
            oid = path.rsplit("/", 1)[-1]
            if oid not in self.opps:
                return httpx.Response(404, json={"message": "not found"})
            if method == "GET":
                if self.get_failures > 0 or self.get_status != 200:
                    self.get_failures = max(0, self.get_failures - 1)
                    return httpx.Response(503 if self.get_status == 200 else self.get_status,
                                          json={"message": "down"})
                return httpx.Response(200, json={"opportunity": dict(self.opps[oid])})
            if method == "PUT":
                if self.put_status != 200:
                    return httpx.Response(self.put_status, json={"message": "boom"})
                if self.put_reply is not None:
                    return httpx.Response(200, json=self.put_reply)
                body = json.loads(request.content.decode("utf-8"))
                self.opps[oid]["pipelineStageId"] = body["pipelineStageId"]
                if body.get("status"):
                    self.opps[oid]["status"] = body["status"]
                return httpx.Response(200, json={"opportunity": dict(self.opps[oid])})
        return httpx.Response(404, json={"message": "no route"})

    def stage(self, oid="o-1"):
        return ghl_sync.stage_key_for_id(self.opps[oid]["pipelineStageId"])

    def puts(self):
        return sum(1 for m, _ in self.log if m == "PUT")


def tick(t, client, engine_move=None, force=False, order="readback_first"):
    """A mini tick: read-back (applied as by="ghl"), the engine (never over a
    lorenzo/ghl stage unless forced; emits a ghl_stage action), then sync."""
    acts = []

    def engine():
        if engine_move and engine_move != t["stage"] and (force or t["stage_set_by"] not in MANUAL):
            t["stage"], t["stage_set_by"] = engine_move, "engine"
            acts.append({"type": "ghl_stage", "stage": engine_move, "by": "engine"})

    def readback():
        k = ghl_sync.read_back_stage(t, client)
        if k is not None and k != t["stage"]:
            t["stage"], t["stage_set_by"] = k, "ghl"

    if order == "readback_first":
        readback()
        engine()
    else:
        engine()
        readback()
    return ghl_sync.sync_thread(t, None, client, NOW, False, engine_actions=acts)


def snap(t, fake):
    return (t["stage"], t["stage_set_by"], t["ghl"]["stage"], fake.stage())


@pytest.fixture
def world(tmp_env, upwork, monkeypatch, verified):
    """A thread already mirrored live: contact c-1, opportunity o-1 at new_reply."""
    live = {"on": True}
    monkeypatch.setattr(settings, "is_live", lambda: live["on"])
    fake = FakeGHL()
    client = GHL(token="tok", transport=httpx.MockTransport(fake))
    t = {"room_id": "room_probe", "client": CLIENT, "stage": "new_reply",
         "stage_set_by": "engine", "ghl": {"contact_id": None, "opportunity_id": None, "stage": None}}
    _, _, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
    assert errs == [] and t["ghl"] == {"contact_id": "c-1", "opportunity_id": "o-1", "stage": "new_reply"}
    assert fake.opps["o-1"]["pipelineId"] == UP_PIPELINE
    return t, fake, client, live


def run(t, fake, client, steps):
    out = []
    for step in steps:
        tick(t, client, **step)
        out.append(snap(t, fake))
    return out


def test_S1_steady_state_no_writes(world):
    t, fake, client, _ = world
    assert run(t, fake, client, [{}, {}, {}]) == [("new_reply", "engine", "new_reply", "new_reply")] * 3
    assert fake.puts() == 0


def test_S2_lorenzo_moves_in_ghl_is_adopted_not_echoed(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    hist = run(t, fake, client, [{}, {}, {}, {"engine_move": "lost"}])
    assert hist[-1] == ("call_booked", "ghl", "call_booked", "call_booked") and fake.puts() == 0


def test_S3_engine_move_pushed_once(world):
    t, fake, client, _ = world
    assert run(t, fake, client, [{"engine_move": "lost"}, {}, {}]) == [("lost", "engine", "lost", "lost")] * 3
    assert fake.puts() == 1


def test_S4_cli_move_pushed_and_engine_cannot_override(world):
    t, fake, client, _ = world
    t["stage"], t["stage_set_by"] = "call_booked", "lorenzo"
    hist = run(t, fake, client, [{}, {"engine_move": "lost"}, {}])
    assert hist[-1] == ("call_booked", "lorenzo", "call_booked", "call_booked") and fake.puts() == 1


def test_S5_ghl_move_and_engine_move_same_interval_readback_first(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    hist = run(t, fake, client, [{"engine_move": "lost"}, {}, {}])
    assert hist[-1] == ("call_booked", "ghl", "call_booked", "call_booked") and fake.puts() == 0


def test_S6_stale_engine_action_never_overrides_lorenzos_ghl_move(world):
    """The engine ran before the read-back: its ghl_stage action disagrees
    with the thread (now Lorenzo's GHL stage), so it is an error, not a write."""
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    _, _, errs = tick(t, client, engine_move="lost", order="engine_first")
    assert [e["code"] for e in errs] == ["ghl_stage_action_mismatch"]
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("call_booked", "ghl", "call_booked", "call_booked")
    assert fake.puts() == 0


def test_S7_live_then_shadow_with_real_ids_keeps_an_engine_move(world):
    """Live -> shadow (rollback, or a read-only-key agent session): the
    would-do does not advance the known stage, so the next read-back does not
    report GHL's untouched stage as Lorenzo's move. The declined client stays
    lost, and the push goes through once live again."""
    t, fake, client, live = world
    live["on"] = False
    hist = run(t, fake, client, [{"engine_move": "lost"}, {}, {}])
    assert hist == [("lost", "engine", "new_reply", "new_reply")] * 3
    assert fake.puts() == 0
    live["on"] = True
    hist = run(t, fake, client, [{}, {}])
    assert hist == [("lost", "engine", "lost", "lost")] * 2 and fake.puts() == 1


def test_S8_live_200_not_applied_keeps_an_engine_move(world):
    t, fake, client, _ = world
    fake.put_reply = {"succeded": False}
    _, _, errs = tick(t, client, engine_move="lost")
    assert [e["code"] for e in errs] == ["ghl_write_rejected"]
    assert snap(t, fake) == ("lost", "engine", "new_reply", "new_reply")
    hist = run(t, fake, client, [{}])                       # still rejected: retried, no bounce
    assert hist == [("lost", "engine", "new_reply", "new_reply")]
    fake.put_reply = None
    hist = run(t, fake, client, [{}, {}])
    assert hist == [("lost", "engine", "lost", "lost")] * 2 and fake.puts() == 3


def test_S9_live_500_is_retried_without_bounce(world):
    t, fake, client, _ = world
    fake.put_status = 500
    hist = run(t, fake, client, [{"engine_move": "lost"}])
    fake.put_status = 200
    hist += run(t, fake, client, [{}, {}])
    assert hist == [("lost", "engine", "new_reply", "new_reply"), ("lost", "engine", "lost", "lost"),
                    ("lost", "engine", "lost", "lost")]


def test_S10_ghl_move_while_a_push_is_pending_wins(world):
    t, fake, client, _ = world
    fake.put_status = 500
    run(t, fake, client, [{"engine_move": "lost"}])
    fake.put_status = 200
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("call_booked", "ghl", "call_booked", "call_booked")


def test_S11_forced_won_over_ghl_stage_is_pushed(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    run(t, fake, client, [{}])
    hist = run(t, fake, client, [{"engine_move": "won", "force": True}, {}, {}])
    assert hist[-1] == ("won", "engine", "won", "won") and fake.opps["o-1"]["status"] == "won"


def test_S12_lorenzo_moves_back_to_last_mirrored_stage(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    run(t, fake, client, [{}])
    fake.opps["o-1"]["pipelineStageId"] = S["new_reply"]
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("new_reply", "ghl", "new_reply", "new_reply") and fake.puts() == 0


def test_S13_status_lost_set_in_ghl_is_adopted_and_stays(world):
    """Note 3: Lorenzo closes the deal as Lost with the status control only."""
    t, fake, client, _ = world
    fake.opps["o-1"]["status"] = "lost"
    hist = run(t, fake, client, [{}, {"engine_move": "proposal_sent"}, {}])
    assert [h[:3] for h in hist] == [("lost", "ghl", "lost")] * 3
    assert fake.puts() == 0 and fake.opps["o-1"]["status"] == "lost"


def test_S14_lorenzo_reopens_a_lost_deal_from_the_cli(world):
    t, fake, client, _ = world
    run(t, fake, client, [{"engine_move": "lost"}])
    assert fake.opps["o-1"]["status"] == "lost"
    t["stage"], t["stage_set_by"] = "new_reply", "lorenzo"
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("new_reply", "lorenzo", "new_reply", "new_reply")
    assert fake.opps["o-1"]["status"] == "open"


def test_S15_abandoned_in_ghl_is_adopted_as_lost_and_never_reopened(world):
    """Note 6: before, abandoned was not read back and the next push reopened
    the opportunity as open."""
    t, fake, client, _ = world
    fake.opps["o-1"]["status"] = "abandoned"
    hist = run(t, fake, client, [{}, {"engine_move": "proposal_sent"}, {}])
    assert [h[:3] for h in hist] == [("lost", "ghl", "lost")] * 3
    assert fake.puts() == 0 and fake.opps["o-1"]["status"] == "abandoned"


def test_S16_lorenzo_reopens_an_abandoned_deal_from_the_cli(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["status"] = "abandoned"
    run(t, fake, client, [{}])
    t["stage"], t["stage_set_by"] = "new_reply", "lorenzo"
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("new_reply", "lorenzo", "new_reply", "new_reply")
    assert fake.opps["o-1"]["status"] == "open" and fake.puts() == 1


def test_S17_failed_reads_never_let_an_engine_move_overwrite_a_ghl_move(world):
    """Note 2 (probe E1): Lorenzo moves the card in GHL while the engine moves
    the thread, and GHL cannot be read. Nothing is written; when GHL answers
    again his move is adopted."""
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    fake.get_status = 503
    _, _, errs = tick(t, client, engine_move="lost")
    assert [e["code"] for e in errs] == ["ghl_read_failed"]
    assert snap(t, fake) == ("lost", "engine", "new_reply", "call_booked") and fake.puts() == 0
    fake.get_status = 200
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("call_booked", "ghl", "call_booked", "call_booked") and fake.puts() == 0


def test_S18_the_check_before_the_write_catches_a_move_the_read_back_missed(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    fake.get_failures = 1                                   # only the read-back's GET fails
    _, _, errs = tick(t, client, engine_move="lost")
    assert [e["code"] for e in errs] == ["ghl_stage_conflict"]
    assert errs[0]["seen"]["kind"] == "stage" and "GHL shows stage call_booked" in errs[0]["detail"]
    assert fake.puts() == 0
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("call_booked", "ghl", "call_booked", "call_booked") and fake.puts() == 0


def test_S19_a_column_outside_the_six_is_never_written_over(world):
    """Note 2 (probe E2): a custom column is reported on every run that has a
    stage to push, and never overwritten."""
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = "upw-stage-negotiating"
    codes = [[e["code"] for e in tick(t, client, **step)[2]] for step in ({}, {"engine_move": "lost"}, {})]
    assert codes == [[], ["ghl_stage_conflict"], ["ghl_stage_conflict"]]
    assert fake.puts() == 0 and snap(t, fake)[:3] == ("lost", "engine", "new_reply")
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]   # he moves it to one of the six
    hist = run(t, fake, client, [{}, {}])
    assert hist[-1] == ("call_booked", "ghl", "call_booked", "call_booked") and fake.puts() == 0


def test_S20_an_opportunity_moved_to_another_pipeline_is_never_moved_back(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineId"] = SALES_PIPELINE
    codes = [[e["code"] for e in tick(t, client, **step)[2]] for step in ({"engine_move": "lost"}, {})]
    assert codes == [["ghl_stage_conflict"]] * 2
    assert fake.puts() == 0 and fake.opps["o-1"]["pipelineId"] == SALES_PIPELINE


def test_S21_blocked_thread_is_reported_every_run_then_the_runbook_fix_resumes_it(tmp_env, upwork, fake_live,
                                                                                   verified):
    fake = FakeGHL()
    fake.opp_without_id = True               # GHL creates the opportunity but answers without its id
    client = GHL(token="tok", transport=httpx.MockTransport(fake))
    t = {"room_id": "room_probe", "client": CLIENT, "stage": "new_reply", "stage_set_by": "engine",
         "ghl": {"contact_id": None, "opportunity_id": None, "stage": None}}
    _, _, errs = tick(t, client)
    assert [e["code"] for e in errs] == ["ghl_no_id_returned"] and t["ghl"]["blocked"] == "ghl_no_id_returned"
    n = len(fake.log)
    t["stage"], t["stage_set_by"] = "won", "lorenzo"               # --stage while blocked
    for _ in range(3):
        _, acts, errs = tick(t, client)
        assert acts == [] and [e["code"] for e in errs] == ["ghl_blocked"]
        assert (errs[0]["stage"], errs[0]["blocked"]) == ("won", "ghl_no_id_returned")
    assert len(fake.log) == n                                      # no request at all, read-back included
    # runbooks/upwork_followup.md "GHL mirror recovery": the id and the stage
    # GHL shows, and blocked removed, in one edit
    t["ghl"].update({"opportunity_id": "o-1", "stage": "new_reply"})
    del t["ghl"]["blocked"]
    fake.opp_without_id = False
    hist = run(t, fake, client, [{}, {}])
    assert hist == [("won", "lorenzo", "won", "won")] * 2
    assert fake.opps["o-1"]["status"] == "won" and fake.puts() == 1 and fake.contacts == 1


def contract_won(t):
    """sequence's contract rule (the engine sets won only from a real
    contract); tick._won_by_contract then skips the read-back for the room."""
    t["stage"], t["stage_set_by"] = "won", "engine"
    return [{"type": "ghl_stage", "stage": "won", "by": "engine"}]


@pytest.mark.parametrize("column,status", [(S["call_booked"], "open"), (S["new_reply"], "lost"),
                                           ("upw-stage-negotiating", "open")])
def test_S22_won_from_a_real_contract_is_pushed_over_whatever_stage_ghl_shows(world, column, status):
    """DESIGN "Stages": won from a real contract beats every stage, a GHL move
    the mirror never saw included, so the same run pushes it."""
    t, fake, client, _ = world
    fake.opps["o-1"].update({"pipelineStageId": column, "status": status})   # Lorenzo's GHL move
    _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False, engine_actions=contract_won(t))
    assert errs == [] and [a["kind"] for a in acts] == ["done"]
    assert [m for m, _ in fake.log[-2:]] == ["GET", "PUT"]
    assert snap(t, fake) == ("won", "engine", "won", "won") and fake.opps["o-1"]["status"] == "won"
    _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
    assert (acts, errs) == ([], []) and fake.puts() == 1


def test_S23_won_from_a_contract_never_moves_a_card_out_of_another_pipeline(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineId"] = "pl-clients-invented"      # he moved the card to another pipeline
    for _ in range(2):
        _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False, engine_actions=contract_won(t))
        assert acts == [] and [e["code"] for e in errs] == ["ghl_stage_conflict"]
        assert errs[0]["seen"]["kind"] == "other_pipeline"
    assert fake.puts() == 0 and fake.opps["o-1"]["pipelineId"] == "pl-clients-invented"


def test_S24_won_from_a_contract_is_not_written_blind(world):
    t, fake, client, _ = world
    fake.get_status = 503
    _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False, engine_actions=contract_won(t))
    assert acts == [] and [e["code"] for e in errs] == ["ghl_read_failed"] and fake.puts() == 0
    fake.get_status = 200
    _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
    assert errs == [] and snap(t, fake) == ("won", "engine", "won", "won")


def test_a_cli_won_is_not_the_contract_exception(world):
    """Only the engine's won (a real contract) passes over a GHL move; a CLI
    won against a card Lorenzo moved in GHL is a conflict like any CLI move."""
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    t["stage"], t["stage_set_by"] = "won", "lorenzo"
    _, acts, errs = ghl_sync.sync_thread(t, None, client, NOW, False)
    assert acts == [] and [e["code"] for e in errs] == ["ghl_stage_conflict"] and fake.puts() == 0


def test_pipeline_sync_reads_only_the_sales_pipeline(monkeypatch):
    """The nightly reverse check pulls opportunities by the Sales pipeline id,
    so the separate Upwork pipeline never reaches it."""
    from services.reply_engine import pipeline_sync

    calls = []

    class Reader(object):
        has_token = True

        def search_opportunities(self, contact_id=None, pipeline_id=None, stage_id=None, limit=20,
                                 start_after_id=None, start_after=None):
            calls.append(pipeline_id)
            return {"opportunities": [], "meta": {}}

    rows, _ = pipeline_sync.fetch_ghl_opportunities(Reader())
    assert rows == [] and calls and set(calls) == {SALES_PIPELINE}


# ============================== polish: a write GHL answers with another stage
@pytest.mark.parametrize("answer,why", [
    ({"opportunity": {"id": "o-41", "pipelineStageId": S["new_reply"], "status": "lost"}}, "stage id"),
    ({"opportunity": {"id": "o-41", "pipelineStageId": S["lost"], "status": "open"}}, "status open"),
    ({"opportunity": {"id": "o-41", "pipelineStageId": S["lost"], "status": "lost",
                      "pipelineId": SALES_REQUESTS["id"]}}, "pipeline"),
    ({"opportunity": {"id": "o-41", "pipelineStageId": SALES_REQUESTS["stages"]["replied"], "status": "lost"}},
     "stage id"),
    ({"id": "o-41", "pipelineStageId": S["call_booked"], "status": "lost"}, "stage id"),     # a bare body
])
def test_a_put_answered_with_another_stage_status_or_pipeline_is_rejected(tmp_env, upwork, fake_live, answer,
                                                                          why):
    client, rec = make(responses=[(200, opp_response(S["new_reply"])), (200, answer)])
    t = synced(stage="lost")
    state, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert [e["code"] for e in errors] == ["ghl_write_rejected"]
    assert why in errors[0]["detail"] and "not applied as sent" in errors[0]["detail"]
    assert [(a["action"], a["kind"]) for a in actions] == [("update_opportunity_stage", "failed")]
    assert [r.method for r in rec.requests] == ["GET", "PUT"]
    assert state["stage"] == "new_reply" and t["ghl"]["stage"] == "new_reply"   # retried next run


def test_a_put_answered_with_exactly_what_was_sent_is_done(tmp_env, upwork, fake_live):
    answer = {"opportunity": {"id": "o-41", "pipelineStageId": S["lost"], "status": "LOST",
                              "pipelineId": UP_PIPELINE}}
    client, _ = make(responses=[(200, opp_response(S["new_reply"])), (200, answer)])
    state, actions, errors = ghl_sync.sync_thread(synced(stage="lost"), ROOM, client, NOW, dry_run=False)
    assert errors == [] and [a["kind"] for a in actions] == ["done"] and state["stage"] == "lost"


def test_S8b_a_put_that_does_not_apply_the_status_keeps_an_engine_move(world):
    """GHL moves the column but ignores status on PUT: rejected, never recorded as lost."""
    t, fake, client, _ = world
    real_call = fake.__call__

    class StatusIgnored(object):
        def __call__(self, request):
            if request.method == "PUT":
                body = json.loads(request.content.decode("utf-8"))
                body.pop("status", None)
                request = httpx.Request("PUT", request.url, json=body, headers=request.headers)
            return real_call(request)

    client = GHL(token="tok", transport=httpx.MockTransport(StatusIgnored()))
    _, _, errs = tick(t, client, engine_move="lost")
    assert [e["code"] for e in errs] == ["ghl_write_rejected"] and "status open (sent lost)" in errs[0]["detail"]
    assert t["ghl"]["stage"] == "new_reply"


# ======================================== polish: ids of another pipeline
@pytest.mark.parametrize("stages,dup", [
    (dict(S, lost=" %s " % S["won"]), "won, lost"),                      # padded, still the same id
    (dict(S, lost={"id": S["won"]}), "won, lost"),                        # an id object and a bare id
    (dict(S, new_reply=S["follow_up_later"], call_booked=S["follow_up_later"]),
     "new_reply, call_booked, follow_up_later"),
])
def test_duplicate_upwork_stage_ids_keep_the_mirror_off(tmp_env, monkeypatch, fake_live, verified, stages, dup):
    monkeypatch.setattr(settings, "IDS", upwork_ids(stages=stages))
    conf, reason = ghl_sync.upwork_pipeline()
    assert conf is None and reason == "ghl.pipelines.upwork has the same id on two stages (%s)" % dup
    client, rec = make()
    _, actions, errors = ghl_sync.sync_thread(synced(stage="lost"), ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_not_configured"] and rec.requests == []
    assert ghl_sync.read_back_stage(synced(), client) is None and rec.requests == []


def test_an_upwork_stage_with_the_pipelines_own_id_keeps_the_mirror_off(monkeypatch):
    monkeypatch.setattr(settings, "IDS", upwork_ids(stages=dict(S, won=UP_PIPELINE)))
    conf, reason = ghl_sync.upwork_pipeline()
    assert conf is None and reason == "ghl.pipelines.upwork stage won has the pipeline's own id"


@pytest.mark.parametrize("stage_id,where", [
    (SALES_REQUESTS["stages"]["replied"], "pipelines.sales_requests.stages.replied"),
    (settings.GHL_STAGES["won"], "pipelines.sales.stages.won"),
])
def test_a_stage_id_of_another_pipeline_without_a_pipeline_id_reads_as_that_pipeline(tmp_env, upwork, fake_live,
                                                                                      stage_id, where):
    body = {"opportunity": {"id": "o-41", "pipelineStageId": stage_id, "status": "open"}}
    reader, _ = make(responses=[(200, body)])
    assert ghl_sync.read_back_stage(synced(), reader) is None
    client, rec = make(responses=[(200, body)])
    _, actions, errors = ghl_sync.sync_thread(synced(stage="lost"), ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_stage_conflict"]
    assert errors[0]["seen"]["kind"] == "other_pipeline" and where in errors[0]["detail"]
    assert [r.method for r in rec.requests] == ["GET"]


# ============ round 2: a CLI move and a GHL move before the same run: GHL wins
# (U4a rule restored: a GHL move is never overwritten, except won from a real
# contract; no GHL timestamp decides it). The tick-level override line is in
# test_tick.py.
def cli_move(t, stage, at):
    """sequence's own --stage (by lorenzo), as jobs.upwork_followup runs it."""
    from services.upwork_followup import sequence
    t.setdefault("marks", {})
    new, _acts = sequence._apply_manual_stage(t, stage, at, "lorenzo")
    t.clear()
    t.update(new)


@pytest.mark.parametrize("ghl_at", [None, "2026-09-23T11:00:00.000Z", "2026-09-23T13:00:00.000Z", 1758630000,
                                    "not a date"])
def test_S25_a_ghl_drag_wins_over_a_cli_move_whatever_the_times(world, ghl_at):
    t, fake, client, _ = world
    cli_move(t, "won", "2026-09-23T12:00:00Z")
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    if ghl_at is not None:
        fake.opps["o-1"]["lastStageChangeAt"] = ghl_at
    hist = run(t, fake, client, [{}, {}])
    assert hist == [("call_booked", "ghl", "call_booked", "call_booked")] * 2 and fake.puts() == 0


def test_S26_a_cli_move_back_to_the_mirrored_stage_does_not_hide_a_ghl_drag(world):
    """--stage call_booked, a GHL drag to proposal_sent, --stage new_reply: the
    thread and the known stage agree, so the GHL drag is read back, not lost."""
    t, fake, client, _ = world
    cli_move(t, "call_booked", "2026-09-23T09:00:00Z")
    fake.opps["o-1"].update({"pipelineStageId": S["proposal_sent"], "lastStageChangeAt": "2026-09-23T10:00:00Z"})
    cli_move(t, "new_reply", "2026-09-23T11:00:00Z")
    hist = run(t, fake, client, [{}, {}])
    assert hist == [("proposal_sent", "ghl", "proposal_sent", "proposal_sent")] * 2 and fake.puts() == 0


def test_S27_a_future_as_of_stamp_on_a_cli_move_never_beats_a_ghl_move(world):
    t, fake, client, _ = world
    cli_move(t, "call_booked", "2026-12-01T00:00:00Z")
    fake.opps["o-1"].update({"pipelineStageId": S["proposal_sent"], "lastStageChangeAt": "2026-09-23T12:00:00Z"})
    assert run(t, fake, client, [{}]) == [("proposal_sent", "ghl", "proposal_sent", "proposal_sent")]
    fake.opps["o-1"].update({"pipelineStageId": S["lost"], "status": "lost"})
    assert run(t, fake, client, [{}]) == [("lost", "ghl", "lost", "lost")] and fake.puts() == 0


def test_S28_a_status_reopen_in_ghl_wins_over_a_cli_move(world):
    """Lost by the status control (column proposal_sent), then --stage
    follow_up_later and a reopen in GHL (status open): the reopen is read back."""
    t, fake, client, _ = world
    fake.opps["o-1"].update({"pipelineStageId": S["proposal_sent"], "status": "lost"})
    assert run(t, fake, client, [{}]) == [("lost", "ghl", "lost", "proposal_sent")]
    cli_move(t, "follow_up_later", "2026-09-23T12:00:00Z")
    fake.opps["o-1"].update({"status": "open", "lastStatusChangeAt": "2026-09-23T11:00:00Z"})
    assert run(t, fake, client, [{}, {}]) == [("proposal_sent", "ghl", "proposal_sent", "proposal_sent")] * 2
    assert fake.puts() == 0


def test_S29_a_cli_pin_of_the_same_stage_does_not_beat_a_ghl_drag(world):
    t, fake, client, _ = world
    fake.opps["o-1"]["pipelineStageId"] = S["call_booked"]
    cli_move(t, "new_reply", "2026-09-23T12:00:00Z")          # a pin: set_by lorenzo, stage unchanged
    assert t["stage_set_by"] == "lorenzo"
    assert run(t, fake, client, [{}]) == [("call_booked", "ghl", "call_booked", "call_booked")]
    assert fake.puts() == 0


def test_S30_a_cli_move_never_writes_over_a_card_without_pipeline_evidence(tmp_env, upwork, fake_live):
    """No pipelineId, a column none of the configured pipelines has, status
    lost: nothing is written, whatever the CLI move's time."""
    body = {"opportunity": {"id": "o-41", "pipelineStageId": "st-some-unconfigured-col", "status": "lost",
                            "lastStageChangeAt": "2026-09-20T10:00:00.000Z"}}
    client, rec = make(responses=[(200, body)])
    t = synced(stage="proposal_sent", mirrored="new_reply", set_by="lorenzo")
    t["stage_changed_at"] = "2026-12-01T00:00:00Z"
    _, actions, errors = ghl_sync.sync_thread(t, ROOM, client, NOW, dry_run=False)
    assert actions == [] and [e["code"] for e in errors] == ["ghl_stage_conflict"]
    assert [r.method for r in rec.requests] == ["GET"]


def test_no_ghl_timestamp_is_read_to_decide_a_stage():
    src = open(ghl_sync.__file__, encoding="utf-8").read()
    assert "lastStageChangeAt" not in src and "lastStatusChangeAt" not in src
