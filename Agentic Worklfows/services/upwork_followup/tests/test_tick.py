"""U4b tick orchestration (services/upwork_followup/tick.py).

Invented clients only. Every model call is an injected fake (shared.llm.complete
is replaced with a function that fails the test), notify and GHL are fakes, the
store is a JsonFileStore under tmp_path. The round-4 store-lock tests are the
exception: they run the REAL shared.llm.complete (billed mode) behind an
in-process fake Anthropic client, so nothing leaves the process and nothing is
billed. Two fixed clocks: NOW is the run's
--as-of, and the real clock the run lease uses (tick.wall_clock) is a FakeClock
at WALL, a different day, so every test also shows the lease ignores --as-of."""
import copy
import faulthandler
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from shared import llm as shared_llm_mod
from shared import settings
from shared import store as store_mod
from shared.store import ABSENT, JsonFileStore, Store, get_store

from services.upwork_followup import classify as classify_mod
from services.upwork_followup import collect, draft, sequence, tick

# The real shared.llm.complete, taken before any test replaces it (the world
# fixture swaps in a function that fails the test).
REAL_COMPLETE = shared_llm_mod.complete

NOW = datetime(2026, 9, 22, 13, 30, tzinfo=timezone.utc)  # Tuesday 08:30 CT
WALL = datetime(2026, 9, 23, 6, 0, tzinfo=timezone.utc)   # the real clock in these tests
PRIVATE = "Standard pricing: $1,800 fixed for the Pipedrive build."
STAGE_KEYS = ("new_reply", "proposal_sent", "call_booked", "follow_up_later", "won", "lost")
UPWORK_PIPELINE = {"id": "pl_upwork_invented", "stages": dict((k, "st_up_" + k) for k in STAGE_KEYS)}


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def msg(mid, side, when, text):
    return {"id": mid, "side": side, "at": iso(when), "text": text}


def room(rid, client, title, post, msgs, first_name=None, private=None, applied="2026-09-15", job=True):
    r = {"room_id": rid, "client": client, "client_first_name": first_name, "room_type": "ONE_ON_ONE",
         "job_title": title, "job_id": None, "proposal_id": "prop_" + rid, "origin": "proposal",
         "contract": None, "offer_state": None, "messages": list(msgs), "job_folder": rid if job else None,
         "job": {"post": post, "proposal": "I built a flow for this, Loom inside.", "beats": [],
                 "ask_before_quoting": [], "private_notes": private or "", "loom_url": None,
                 "applied_at": applied} if job else None}
    r["last_side"] = msgs[-1]["side"]
    r["last_message_at"] = msgs[-1]["at"]
    return r


def rep_room():
    return room("room_rep1", "Juniper Bakery Co", "Pipedrive invoice sync for bakery orders",
                "Juniper Bakery needs Pipedrive deals to sync invoice tags into QuickBooks when an order is "
                "confirmed.",
                [msg("r1", "client", datetime(2026, 9, 18, 14, tzinfo=timezone.utc), "Hi, saw your proposal."),
                 msg("r2", "freelancer", datetime(2026, 9, 18, 15, tzinfo=timezone.utc),
                     "Thanks, the Loom shows the Pipedrive flow."),
                 msg("r3", "client", datetime(2026, 9, 21, 20, tzinfo=timezone.utc),
                     "question: can the invoice tags also carry the delivery date?")],
                first_name="Mara", private="Time: 12-15 hours.\n" + PRIVATE)


def tch_room():
    return room("room_tch1", "Orchard Lane Dental", "Appointment reminder texts for a dental office",
                "Orchard Lane Dental wants appointment reminder texts sent from Open Dental two days before each "
                "visit.",
                [msg("t1", "client", datetime(2026, 9, 15, 15, tzinfo=timezone.utc),
                     "positive: Looks good, what would you need from us?"),
                 msg("t2", "freelancer", datetime(2026, 9, 19, 15, tzinfo=timezone.utc),
                     "I would need read access to the Open Dental schedule.")])


def wai_room():
    return room("room_wai1", "Cobalt Freight LLC", "Load board scraper for freight quotes",
                "Cobalt Freight wants a load board scraper that turns freight quotes into a sheet.",
                [msg("w1", "client", datetime(2026, 9, 20, 15, tzinfo=timezone.utc), "positive: sounds useful"),
                 msg("w2", "freelancer", datetime(2026, 9, 21, 18, tzinfo=timezone.utc), "Here is the plan.")])


def chk_room():
    return room("room_chk1", "Harbor Yoga Studio", "Class booking sync for a yoga studio",
                "Harbor Yoga Studio wants Mindbody class bookings synced to each instructor calendar.",
                [msg("k1", "client", datetime(2026, 9, 8, 15, tzinfo=timezone.utc), "positive: interested"),
                 msg("k2", "freelancer", datetime(2026, 9, 9, 15, tzinfo=timezone.utc), "Great, here is how."),
                 msg("k3", "client", datetime(2026, 9, 10, 15, tzinfo=timezone.utc),
                     "not_now: busy this month, check back after the 20th")])


def bkd_room():
    return room("room_bkd1", "Pine Ridge Roofing", "Roofing estimate follow-up automation",
                "Pine Ridge Roofing wants estimate follow-ups sent after each roof inspection.",
                [msg("b1", "client", datetime(2026, 9, 5, 15, tzinfo=timezone.utc), "positive: let us talk"),
                 msg("b2", "freelancer", datetime(2026, 9, 6, 15, tzinfo=timezone.utc), "Happy to.")])


DRAFTS = {
    "Pipedrive invoice sync": (
        "Yes, the invoice tags can carry the delivery date. I would read it from the Pipedrive order field and "
        "write it onto the QuickBooks invoice line, so the bakery sees it without opening the deal. Is the "
        "delivery date always filled in on the order?\nNEEDS_YOU: confirm the QuickBooks plan has custom "
        "fields\nPROPOSES_CALL: yes"),
    "Appointment reminder texts": (
        "One idea for the Open Dental reminders: I would skip reminder texts for visits booked less than two "
        "days out, so nobody gets a reminder for a visit they booked that morning. Should same-week bookings "
        "get a single reminder instead?\nPROPOSES_CALL: no"),
    "Class booking sync": (
        "Back on the class booking sync for Harbor Yoga: I would start with the Mindbody class list feeding "
        "each instructor calendar, since that is the piece the post leads with. Is the studio still planning "
        "the switch this fall?\nPROPOSES_CALL: no"),
}


class FakeLLM(object):
    """classify/escalate: the label is the client text before the first colon.
    draft: the text keyed by a fragment of the JOB_TITLE block."""

    def __init__(self, drafts=None, follow_up=None):
        self.drafts = dict(DRAFTS if drafts is None else drafts)
        self.follow_up = follow_up
        self.calls = []

    def __call__(self, role, system, user, max_tokens=800, json_mode=False):
        self.calls.append(role)
        if role in ("classify", "escalate"):
            client = re.search(r"=== BEGIN CLIENT_MESSAGE ===\n(.*?)\n=== END", user, re.S).group(1)
            label = client.split(":", 1)[0].strip().lower()
            if label not in classify_mod.LABELS:
                label = "positive"
            return {"label": label, "confidence": 0.95}
        title = re.search(r"=== BEGIN JOB_TITLE ===\n(.*?)\n=== END", user, re.S).group(1)
        for key, out in self.drafts.items():
            if key in title:
                if isinstance(out, Exception):
                    raise out
                return out
        raise AssertionError("no fake draft for %r" % title)

    def drafts_called(self):
        return [c for c in self.calls if c == "draft"]


class FakeNotify(object):
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"sent": False, "test": False, "shadow": True}

    def __call__(self, title, message, **kw):
        self.calls.append({"title": title, "message": message, "kw": kw})
        return dict(self.result)


class FakeGHL(object):
    def __init__(self, stage_id=None, fail_writes=False):
        self.calls = []
        self.stage_id = stage_id
        self.fail_writes = fail_writes

    def get_opportunity(self, opp_id):
        self.calls.append(("get_opportunity", opp_id))
        return {"opportunity": {"pipelineStageId": self.stage_id, "pipelineId": UPWORK_PIPELINE["id"]}}

    def _write(self, _action, *args, **kw):
        self.calls.append((_action, args, kw))
        if self.fail_writes:
            raise RuntimeError("GHL is down (invented)")
        return {"shadow": True}

    def upsert_contact(self, *a, **k):
        return self._write("upsert_contact", *a, **k)

    def upsert_opportunity(self, *a, **k):
        return self._write("upsert_opportunity", *a, **k)

    def update_opportunity_stage(self, *a, **k):
        return self._write("update_opportunity_stage", *a, **k)

    def names(self):
        return [c[0] for c in self.calls]


class FakeClock(object):
    """The injected real clock (tick.wall_clock)."""

    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, **kw):
        self.at = self.at + timedelta(**kw)


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path / "tmpdir"))
    monkeypatch.delenv(tick.BUDGET_ENV, raising=False)
    monkeypatch.delenv(tick.CLASSIFY_CAP_ENV, raising=False)

    def boom(*a, **k):
        raise AssertionError("shared.llm.complete must never be called in these tests")

    monkeypatch.setattr(draft.shared_llm, "complete", boom)
    monkeypatch.setattr(classify_mod.shared_llm, "complete", boom)
    monkeypatch.setattr(tick, "topic_is_protected", lambda: False)
    logs = []
    monkeypatch.setattr(tick, "log_run", lambda job, status, details=None: logs.append((job, status, details)))
    clock = FakeClock(WALL)
    monkeypatch.setattr(tick, "wall_clock", clock)
    return {"tmp": tmp_path, "logs": logs, "clock": clock}


@pytest.fixture
def upwork_pipeline(monkeypatch):
    """An invented, fully configured ghl.pipelines.upwork, so the mirror is on."""
    ids = json.loads(json.dumps(settings.IDS or {}))
    ids.setdefault("ghl", {}).setdefault("pipelines", {})["upwork"] = UPWORK_PIPELINE
    monkeypatch.setattr(settings, "IDS", ids)
    return UPWORK_PIPELINE


@pytest.fixture
def store(tmp_path):
    return JsonFileStore(tmp_path / "store.json")


def snapshot(rooms, generated=NOW - timedelta(minutes=10), contracted=None):
    return {"generated_at": iso(generated), "source": "fixture",
            "sections": {"rooms": True, "messages": True, "proposals": True, "invitations": None,
                         "contracts": True, "offers": True},
            "truncated": False, "rooms": list(rooms), "contracted_rooms": list(contracted or []),
            "omitted_contracted": len(contracted or [])}


def write_snap(tmp_path, snap):
    path = tmp_path / "snapshot.json"
    collect.write_snapshot(snap, path)
    return path


def seed_classify(text, room_):
    label = (text or "").split(":", 1)[0].strip().lower()
    return {"label": label if label in classify_mod.LABELS else "positive", "confidence": 0.95,
            "follow_up_at": "2026-09-20" if label == "not_now" else None}


def seed(store):
    """Harbor Yoga paused until 2026-09-20; Pine Ridge moved to call_booked by Lorenzo."""
    at = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    sequence.run(store, snapshot([chk_room(), bkd_room()], generated=at), at, seed_classify)
    sequence.set_stage(store, "room_bkd1", "call_booked", at, by="lorenzo")


def full_run(store, tmp_path, llm=None, notify=None, ghl=None, mode="run"):
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room(), wai_room(), chk_room(), bkd_room()]))
    llm = llm or FakeLLM()
    notify = notify or FakeNotify()
    ghl = ghl or FakeGHL()
    result = tick.run_tick(NOW, mode, store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=ghl)
    return result, llm, notify, ghl


def thread(store, rid):
    return store.get(sequence.thread_key(rid))


def batch_text(result):
    with open(result["batch_path"], encoding="utf-8") as fh:
        return fh.read()


def fenced_blocks(text):
    return re.findall(r"```text\n(.*?)\n```", text, re.S)


# ------------------------------------------------------------------ full run
def test_full_run_drafts_each_kind_and_records_pending(store, tmp_path):
    seed(store)
    result, llm, notify, _ghl = full_run(store, tmp_path)

    kinds = sorted((d["room_id"], d["kind"], d["touch"]) for d in result["drafts"])
    assert kinds == [("room_chk1", "checkin", None), ("room_rep1", "reply", None), ("room_tch1", "touch", 1)]
    for rid, kind in (("room_rep1", "reply"), ("room_tch1", "touch"), ("room_chk1", "checkin")):
        p = thread(store, rid)["pending"]
        assert p["kind"] == kind and p["text"] and p["card_id"].startswith("uwf-%s-" % rid)
        assert thread(store, rid)["draft_meta"]["card_id"] == p["card_id"]
    assert thread(store, "room_rep1")["draft_meta"]["needs_you"] == ["confirm the QuickBooks plan has custom fields"]
    assert thread(store, "room_rep1")["draft_meta"]["proposes_call"] is True
    assert thread(store, "room_wai1")["pending"] is None
    assert thread(store, "room_rep1")["job_title"] == "Pipedrive invoice sync for bakery orders"
    assert llm.drafts_called() == ["draft", "draft", "draft"]
    titles = [c["title"] for c in notify.calls]
    # public topic: the push titles carry no client-derived text ...
    assert sorted(titles[:3]) == ["Upwork: 1 new draft (T1)", "Upwork: 1 new draft (check-in)",
                                  "Upwork: 1 new draft (reply)"]
    assert titles[-1].startswith("Upwork drafts: 3 new, 3 pending")
    # ... and the client-named title opens the email leg
    firsts = sorted(c["kw"]["email_message"].split("\n", 1)[0] for c in notify.calls[:3])
    assert firsts == ["Upwork T1 for Orchard Lane Dental", "Upwork check-in for Harbor Yoga Studio",
                      "Upwork reply for Juniper Bakery Co"]
    assert len(notify.calls) == 4
    for call in notify.calls:
        assert call["kw"].get("actions") is None
    assert result["cards_state"] == "shadow"


def test_full_run_status_is_ok_without_problems(store, tmp_path, upwork_pipeline):
    seed(store)
    result, _llm, _n, ghl = full_run(store, tmp_path)
    assert "upsert_contact" in ghl.names()      # the mirror ran (shadow placeholders)
    assert result["ghl_notes"] == []
    assert result["counts"]["needs_edit"] == 0 and result["counts"]["needs_review"] == 0
    assert result["ghl_errors"] == []
    assert result["status"] == "ok"


# ------------------------------------------------------------------ dry run
def test_dry_run_leaves_the_real_store_alone_and_calls_no_model(store, tmp_path):
    seed(store)
    before = json.dumps({k: store.get(k) for k in store.keys("")}, sort_keys=True)
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room(), wai_room(), chk_room(), bkd_room()]))

    def no_llm(*a, **k):
        raise AssertionError("dry-run called a model")

    notify, ghl = FakeNotify(), FakeGHL()
    result = tick.run_tick(NOW, "dry-run", store=store, snapshot_path=path, llm=no_llm, notify_fn=notify, ghl=ghl)

    after = json.dumps({k: store.get(k) for k in store.keys("")}, sort_keys=True)
    assert after == before
    assert notify.calls == [] and ghl.calls == []
    assert result["counts"]["drafted"] == 3
    assert result["counts"]["enrolled"] == 3
    text = batch_text(result)
    assert "Would draft Reply now" in text
    assert "Would draft Follow-up T1 now" in text
    assert "Would draft Check-in now" in text
    assert "Mode: dry-run" in text


def test_dry_run_classifier_is_deterministic():
    assert tick.classify_dry_run("Can you start Monday?", {})["via"] == "dry_run"
    assert tick.classify_dry_run("Can you start Monday?", {})["label"] == "neutral"
    assert tick.classify_dry_run("", {})["label"] == "machine"


# ------------------------------------------------------------------ snapshot
def test_stale_snapshot_warns_loudly_and_still_processes(store, tmp_path, world):
    path = write_snap(tmp_path, snapshot([tch_room()], generated=NOW - timedelta(hours=30)))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert result["counts"]["snapshot_age_h"] == 30.0
    assert any("STALE SNAPSHOT" in w for w in result["warnings"])
    assert result["counts"]["drafted"] == 1
    assert result["status"] == "attention"
    assert "**WARNING: STALE SNAPSHOT: it is 30.0 hours old" in batch_text(result)
    job, status, details = world["logs"][-1]
    assert status == "attention" and any("STALE" in w for w in details["warnings"])


def test_missing_snapshot_is_an_error_and_drafts_nothing(store, tmp_path, world):
    llm, notify = FakeLLM(), FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=tmp_path / "nope.json", llm=llm,
                           notify_fn=notify, ghl=FakeGHL())
    assert result["status"] == "error"
    assert result["snapshot_error"] == "missing"
    assert llm.calls == []
    assert store.keys("upwork:") == []
    assert "ERROR: no batch this run" in batch_text(result)
    assert [c["title"] for c in notify.calls] == ["Upwork drafts: no snapshot"]
    job, status, details = world["logs"][-1]
    assert (job, status) == ("upwork_followup", "error")
    assert details["snapshot_error"] == "missing"


def test_unreadable_snapshot_is_an_error(store, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = tick.run_tick(NOW, "dry-run", store=store, snapshot_path=bad)
    assert result["status"] == "error" and result["snapshot_error"].startswith("unreadable")


def test_bad_mode_is_refused(store):
    with pytest.raises(ValueError):
        tick.run_tick(NOW, "live", store=store)


# ------------------------------------------------------------------ failures and needs edit
def test_llm_error_clears_the_reservation_for_a_retry(store, tmp_path):
    path = write_snap(tmp_path, snapshot([tch_room()]))
    llm = FakeLLM(drafts={"Appointment reminder texts": RuntimeError("model unreachable (invented)")})
    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())

    assert thread(store, "room_tch1")["pending"] is None
    assert result["counts"]["drafted"] == 0 and result["counts"]["errors"] == 1
    assert result["status"] == "error"
    assert not any("(T1)" in c["title"] or c["title"].startswith("Upwork T1") for c in notify.calls)
    assert "draft failed" in batch_text(result)

    # the next run drafts it again
    ok = tick.run_tick(NOW + timedelta(minutes=5), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                       notify_fn=notify, ghl=FakeGHL())
    assert ok["counts"]["drafted"] == 1
    assert thread(store, "room_tch1")["pending"]["text"]


def test_needs_edit_draft_is_recorded_and_flagged(store, tmp_path):
    path = write_snap(tmp_path, snapshot([tch_room()]))
    bad = "Great news on the Open Dental reminders! I would skip reminder texts for visits booked today."
    llm = FakeLLM(drafts={"Appointment reminder texts": bad})
    notify = FakeNotify(result={"sent": True})
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())

    assert thread(store, "room_tch1")["pending"]["text"] == bad
    assert result["counts"]["needs_edit"] == 1
    assert result["status"] == "attention"
    card = next(c for c in notify.calls if c["title"] == "Upwork: 1 new draft (T1)")
    assert "Needs edit: exclamation" in card["kw"]["email_message"]
    assert "Needs edit: exclamation" in batch_text(result)
    assert result["cards_state"] == "delivered"


# ------------------------------------------------------------------ GHL
def _with_real_ghl_ids(store, rid):
    def fn(cur):
        cur = dict(cur)
        cur["ghl"] = {"contact_id": "ct_invented", "opportunity_id": "opp_invented", "stage": "new_reply"}
        return cur
    store.mutate(sequence.thread_key(rid), fn)


def test_ghl_read_back_is_applied_before_drafting_and_sync(store, tmp_path, upwork_pipeline):
    at = datetime(2026, 9, 19, 16, tzinfo=timezone.utc)
    sequence.run(store, snapshot([tch_room()], generated=at), at, seed_classify)
    _with_real_ghl_ids(store, "room_tch1")
    path = write_snap(tmp_path, snapshot([tch_room()]))
    ghl = FakeGHL(stage_id=upwork_pipeline["stages"]["call_booked"])
    llm, notify = FakeLLM(), FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=ghl)

    t = thread(store, "room_tch1")
    assert (t["stage"], t["stage_set_by"]) == ("call_booked", "ghl")
    assert t["pending"] is None                  # the T1 reservation was withdrawn by the GHL move
    assert llm.drafts_called() == []             # so no draft was made
    assert ghl.names()[0] == "get_opportunity"   # read-back first
    assert "update_opportunity_stage" not in ghl.names()   # a GHL move is never written back
    assert result["drafts"] == []
    assert "Call booked (1)" in batch_text(result)


# ------------------------------------------- round 2: a --stage replaced by a GHL move
def _cli_then_ghl(store, tmp_path, upwork_pipeline, ghl_stage, moves):
    at = datetime(2026, 9, 19, 16, tzinfo=timezone.utc)
    sequence.run(store, snapshot([tch_room()], generated=at), at, seed_classify)
    _with_real_ghl_ids(store, "room_tch1")
    for i, stage in enumerate(moves):
        sequence.set_stage(store, "room_tch1", stage, datetime(2026, 9, 22, 9 + i, tzinfo=timezone.utc))
    path = write_snap(tmp_path, snapshot([tch_room()]))
    ghl = FakeGHL(stage_id=upwork_pipeline["stages"][ghl_stage])
    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=notify, ghl=ghl)
    return result, ghl, notify


@pytest.mark.parametrize("moves", [["call_booked"], ["call_booked", "new_reply"]])
def test_a_cli_stage_replaced_by_a_ghl_move_is_said_in_one_line(store, tmp_path, upwork_pipeline, world, moves):
    """GHL wins (a GHL move is never overwritten), and the batch, the summary
    and Job_Log say his --stage was replaced. The second case is --stage back
    to the stage the mirror last wrote: still read back and still reported."""
    result, ghl, notify = _cli_then_ghl(store, tmp_path, upwork_pipeline, "proposal_sent", moves)
    t = thread(store, "room_tch1")
    assert (t["stage"], t["stage_set_by"]) == ("proposal_sent", "ghl")
    assert "update_opportunity_stage" not in ghl.names()
    want = {"room_id": "room_tch1", "cli_stage": moves[-1], "ghl_stage": "proposal_sent"}
    assert result["stage_overrides"] == [want] and result["status"] == "attention"
    line = ("The stage you set (%s) for Orchard Lane Dental (room room_tch1) was overridden by the GHL card move "
            "to proposal_sent; run --stage %s again if you meant it." % (moves[-1], moves[-1]))
    assert "Stage override: " + line in batch_text(result)
    assert world["logs"][-1][2]["stage_overrides"] == [want]
    summary = [c for c in notify.calls if c["title"].startswith("Upwork drafts")][-1]
    assert ("The stage you set (%s) for room room_tch1 was overridden" % moves[-1]) in summary["kw"]["email_message"]
    assert "1 stage you set was overridden by a GHL card move this run; the batch names it." in summary["message"]
    assert "Orchard" not in summary["message"] and "room_tch1" not in summary["message"]


def test_no_override_line_when_ghl_agrees_or_the_stage_was_the_engines(store, tmp_path, upwork_pipeline):
    result, _g, _n = _cli_then_ghl(store, tmp_path, upwork_pipeline, "call_booked", ["call_booked"])
    assert result["stage_overrides"] == [] and "Stage override" not in batch_text(result)
    store2 = JsonFileStore(tmp_path / "store2.json")
    (tmp_path / "b").mkdir()
    result, _g, _n = _cli_then_ghl(store2, tmp_path / "b", upwork_pipeline, "call_booked", [])
    assert thread(store2, "room_tch1")["stage"] == "call_booked" and result["stage_overrides"] == []


def test_the_line_names_no_stage_command_when_the_stage_came_from_resume(store, tmp_path, upwork_pipeline):
    """--resume of a thread the engine moved to lost sets new_reply as his move
    (stage_set_by lorenzo). The line names the stage he set, not a --stage he
    never ran."""
    at = datetime(2026, 9, 19, 16, tzinfo=timezone.utc)
    sequence.run(store, snapshot([tch_room()], generated=at), at, seed_classify)
    _with_real_ghl_ids(store, "room_tch1")

    def lost_by_engine(cur):
        cur = copy.deepcopy(cur)
        cur.update(status="lost", stage="lost", stage_set_by="engine")
        return cur

    store.mutate(sequence.thread_key("room_tch1"), lost_by_engine)
    sequence.resume(store, "room_tch1", datetime(2026, 9, 22, 9, tzinfo=timezone.utc))
    assert (thread(store, "room_tch1")["stage"], thread(store, "room_tch1")["stage_set_by"]) == ("new_reply", "lorenzo")
    path = write_snap(tmp_path, snapshot([tch_room()]))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                           ghl=FakeGHL(stage_id=upwork_pipeline["stages"]["proposal_sent"]))
    assert result["stage_overrides"] == [{"room_id": "room_tch1", "cli_stage": "new_reply",
                                          "ghl_stage": "proposal_sent"}]
    text = batch_text(result)
    assert ("Stage override: The stage you set (new_reply) for Orchard Lane Dental (room room_tch1) was overridden "
            "by the GHL card move to proposal_sent; run --stage new_reply again if you meant it.") in text
    assert "Your --stage" not in text


def test_an_override_on_a_same_day_rerun_still_sends_the_summary_card(store, tmp_path, upwork_pipeline):
    """The summary card goes once per snapshot and Central day unless a run
    forces it. A rerun on the same snapshot that records a stage override
    forces it; the override is recorded once, so the next rerun sends nothing.
    The public push only counts it."""
    at = datetime(2026, 9, 19, 16, tzinfo=timezone.utc)
    sequence.run(store, snapshot([tch_room()], generated=at), at, seed_classify)
    _with_real_ghl_ids(store, "room_tch1")
    path = write_snap(tmp_path, snapshot([tch_room()]))

    def rerun(minutes, ghl_stage):
        notify = FakeNotify()
        result = tick.run_tick(NOW + timedelta(minutes=minutes), "run", store=store, snapshot_path=path,
                               llm=FakeLLM(), notify_fn=notify,
                               ghl=FakeGHL(stage_id=upwork_pipeline["stages"][ghl_stage]))
        return result, notify

    _first, notify = rerun(0, "new_reply")
    assert [c["title"] for c in notify.calls] == ["Upwork: 1 new draft (T1)", "Upwork drafts: 1 new, 1 pending"]
    _quiet, notify = rerun(10, "new_reply")
    assert notify.calls == []                        # same snapshot, same Central day: no second summary

    sequence.set_stage(store, "room_tch1", "call_booked", NOW + timedelta(minutes=15))
    result, notify = rerun(20, "proposal_sent")
    assert result["stage_overrides"] == [{"room_id": "room_tch1", "cli_stage": "call_booked",
                                          "ghl_stage": "proposal_sent"}]
    assert result["counts"]["drafted"] == 0 and result["status"] == "attention"
    assert [c["title"] for c in notify.calls] == ["Upwork drafts: 0 new, 0 pending"]
    push = notify.calls[0]["message"]
    assert "1 stage you set was overridden by a GHL card move this run; the batch names it." in push
    for word in ("Orchard", "room_tch1", "call_booked", "proposal_sent"):
        assert word not in push, word
    assert ("The stage you set (call_booked) for room room_tch1 was overridden by the GHL card move to "
            "proposal_sent") in notify.calls[0]["kw"]["email_message"]

    again, notify = rerun(30, "proposal_sent")
    assert again["stage_overrides"] == [] and notify.calls == []


def test_ghl_errors_are_collected_and_the_tick_carries_on(store, tmp_path, upwork_pipeline):
    seed(store)
    result, llm, notify, ghl = full_run(store, tmp_path, ghl=FakeGHL(fail_writes=True))
    assert result["counts"]["drafted"] == 3
    assert result["counts"]["ghl_errors"] == len(result["ghl_errors"]) >= 1
    assert all(e["code"] == "ghl_write_failed" for e in result["ghl_errors"])
    assert result["status"] == "attention"
    assert "## GHL mirror errors" in batch_text(result)


def test_ghl_not_configured_is_one_note_not_an_error(store, tmp_path, monkeypatch, world):
    ids = json.loads(json.dumps(settings.IDS or {}))
    ids.setdefault("ghl", {}).setdefault("pipelines", {}).pop("upwork", None)
    monkeypatch.setattr(settings, "IDS", ids)
    seed(store)
    result, _l, _n, ghl = full_run(store, tmp_path)
    assert ghl.calls == []                      # the mirror is off: no read, no write
    assert result["ghl_errors"] == [] and result["ghl_notes"] == ["ghl_not_configured"]
    assert result["status"] == "ok"
    assert batch_text(result).count("GHL mirror: off (ghl_not_configured") == 1
    assert world["logs"][-1][2]["ghl"] == ["ghl_not_configured"]


def test_sync_gets_only_actions_that_match_the_final_stage(store, tmp_path, monkeypatch, upwork_pipeline):
    seen = []
    real = tick.ghl_sync.sync_thread

    def spy(thread_, room_, ghl_, now_, dry_run, engine_actions=None):
        seen.append((thread_["room_id"], thread_["stage"], list(engine_actions or [])))
        return real(thread_, room_, ghl_, now_, dry_run, engine_actions=engine_actions)

    monkeypatch.setattr(tick.ghl_sync, "sync_thread", spy)
    seed(store)
    full_run(store, tmp_path)
    assert seen
    for rid, stage, acts in seen:
        assert all(a["stage"] == stage for a in acts), (rid, stage, acts)
    # the check-in moved follow_up_later -> new_reply this run; only new_reply is passed
    chk = [s for s in seen if s[0] == "room_chk1"][0]
    assert chk[1] == "new_reply"


# ------------------------------------------------------------------ contracted rooms
def test_contracted_room_marks_the_thread_won_and_mirrors_it(store, tmp_path, upwork_pipeline):
    first = write_snap(tmp_path, snapshot([tch_room()], generated=NOW - timedelta(hours=2, minutes=10)))
    tick.run_tick(NOW - timedelta(hours=2), "run", store=store, snapshot_path=first, llm=FakeLLM(),
                  notify_fn=FakeNotify(), ghl=FakeGHL())
    assert thread(store, "room_tch1")["pending"]["text"]

    contracted = [{"room_id": "room_tch1", "contract_id": "ct_77", "status": "ACTIVE", "proposal_id": "prop_x"}]
    path = write_snap(tmp_path, snapshot([], contracted=contracted))
    ghl = FakeGHL()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                           ghl=ghl)

    t = thread(store, "room_tch1")
    assert (t["status"], t["stage"]) == ("won", "won")
    assert t["pending"] is None
    assert result["counts"]["won"] == 1
    won_id = upwork_pipeline["stages"]["won"]
    writes = [c for c in ghl.calls if c[0] in ("upsert_opportunity", "update_opportunity_stage")]
    assert writes and won_id in writes[-1][1]
    text = batch_text(result)
    assert "## Won (1)" in text and "(not in today's snapshot)" in text


# ------------------------------------------------------------------ batch
def test_batch_groups_by_stage_with_one_liners(store, tmp_path):
    seed(store)
    result, _l, _n, _g = full_run(store, tmp_path)
    text = batch_text(result)
    heads = ["## New reply", "## Proposal sent", "## Follow-up later", "## Call booked", "## Won", "## Lost"]
    positions = [text.index(h) for h in heads]
    assert positions == sorted(positions)
    new_reply = text[positions[0]:positions[1]]
    assert "### Reply | Juniper Bakery Co | Pipedrive invoice sync for bakery orders" in new_reply
    assert "### Follow-up T1 | Orchard Lane Dental" in new_reply
    assert "### Check-in | Harbor Yoga Studio" in new_reply
    assert "- Cobalt Freight LLC | Load board scraper for freight quotes | T1 due 2026-09-23" in new_reply
    assert "Open room: https://www.upwork.com/ab/messages/rooms/room_rep1" in new_reply
    assert "Suggests a call" in new_reply
    assert "Needs you:\n- confirm the QuickBooks plan has custom fields" in new_reply
    booked = text[positions[3]:positions[4]]
    assert "- Pine Ridge Roofing | Roofing estimate follow-up automation | status active, stage set by lorenzo" \
        in booked
    assert "room room_bkd1" in booked
    assert "Counts: 5 rooms | 3 enrolled | 3 drafted (0 needs edit) | 3 pending" in text
    assert "Snapshot: generated" in text and "0.2 h old" in text
    assert "--stage <room_id or client/title fragment> <stage>" in text


def test_private_notes_only_in_the_for_you_block(store, tmp_path):
    seed(store)
    result, _l, notify, _g = full_run(store, tmp_path)
    text = batch_text(result)
    blocks = fenced_blocks(text)
    assert len(blocks) == 3
    assert all(PRIVATE not in b and "12-15 hours" not in b for b in blocks)
    section = text[text.index("### Reply | Juniper Bakery Co"):]
    assert section.index("For you, not the client:") < section.index(PRIVATE)
    assert section.index("```text") < section.index("For you, not the client:")
    assert "- Applied: 2026-09-15" in section
    assert "- Touches sent so far: none (0 in the current silence)" in section
    card = next(c for c in notify.calls if c["kw"]["email_message"].startswith("Upwork reply for Juniper"))
    body = card["kw"]["email_message"]
    assert body.index("For you, not the client:") < body.index(PRIVATE)
    draft_text = thread(store, "room_rep1")["pending"]["text"]
    assert body.index(draft_text) < body.index("For you, not the client:")
    # the public push carries neither the draft nor the private notes
    assert PRIVATE not in card["message"] and draft_text not in card["message"]


# An invented private assessment block in the shape the proposal skill writes:
# empty "Label:" lines, their text on the next lines, and "- " bullets of its own.
ASSESSMENT = ("Time:\n"
              "6 to 10 hours of real work, most of it the invoice mapping.\n"
              "Likelihood:\n"
              "Home turf: a Pipedrive to QuickBooks sync, built twice before.\n"
              "- The list is old. The post is 9 days old with 30 proposals.\n"
              "- Payment verified, 4.9 rating.\n"
              "Standard pricing: $1,400 fixed.\n"
              "- Quote after the call, not before.")
ASSESSMENT_BULLETS = [
    "- Time: 6 to 10 hours of real work, most of it the invoice mapping.",
    "- Likelihood: Home turf: a Pipedrive to QuickBooks sync, built twice before.",
    "  - The list is old. The post is 9 days old with 30 proposals.",
    "  - Payment verified, 4.9 rating.",
    "- Standard pricing: $1,400 fixed.",
    "  - Quote after the call, not before.",
]


def test_private_note_bullets_nest_a_multi_line_field_without_doubled_dashes():
    notes = draft.private_note_lines({"job": {"private_notes": ASSESSMENT}})
    assert tick.private_note_bullets(notes) == ASSESSMENT_BULLETS
    # a line before any field is a top-level bullet, its own "- " not doubled
    assert tick.private_note_bullets(["- loose note", "plain note", "Time: 2 hours", "- detail"]) == [
        "- loose note", "- plain note", "- Time: 2 hours", "  - detail"]
    # an empty field never swallows the next known field
    assert tick.private_note_bullets(["Time:", "Likelihood: high"]) == ["- Time:", "- Likelihood: high"]


@pytest.mark.parametrize("notes,want", [
    (["Time:", "- Standard pricing: $500 fixed", "Likelihood: high"],
     ["- Time:", "- Standard pricing: $500 fixed", "- Likelihood: high"]),
    (["Time:", "Standard pricing: $500 fixed", "- quote after the call"],
     ["- Time:", "- Standard pricing: $500 fixed", "  - quote after the call"]),
    (["Time:", "- 6 hours", "Likelihood: high"], ["- Time: 6 hours", "- Likelihood: high"]),
    (["Likelihood: medium", "- Note: an unknown label stays nested"],
     ["- Likelihood: medium", "  - Note: an unknown label stays nested"]),
])
def test_a_line_starting_with_a_known_label_starts_a_new_field(notes, want):
    assert tick.private_note_bullets(notes) == want


def test_a_multi_line_assessment_renders_nested_in_the_batch_and_the_card(store, tmp_path):
    rep = rep_room()
    rep["job"]["private_notes"] = ASSESSMENT
    path = write_snap(tmp_path, snapshot([rep]))
    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=notify,
                           ghl=FakeGHL())
    section = batch_text(result)
    section = section[section.index("For you, not the client:"):]
    block = "\n".join(["For you, not the client:",
                       "- Job: Pipedrive invoice sync for bakery orders",
                       "- Applied: 2026-09-15",
                       "- Touches sent so far: none (0 in the current silence)"] + ASSESSMENT_BULLETS)
    assert section.startswith(block + "\n")
    assert "- - " not in section and "\n- Likelihood:\n" not in section
    card = next(c for c in notify.calls if c["kw"]["email_message"].startswith("Upwork reply for Juniper"))
    assert card["kw"]["email_message"].endswith("\n".join(ASSESSMENT_BULLETS))
    assert "Home turf" not in card["message"]            # the public push still carries no private notes


# ------------------------------------------------------------------ cards
def test_card_titles():
    assert tick.card_title("touch", 3, "Acme  Test Co") == "Upwork T3 for Acme Test Co"
    assert tick.card_title("reply", None, "Acme Test Co") == "Upwork reply for Acme Test Co"
    assert tick.card_title("checkin", None, "Acme Test Co") == "Upwork check-in for Acme Test Co"


def test_card_body_is_truncated_on_a_protected_topic(store, tmp_path, monkeypatch):
    monkeypatch.setattr(tick, "topic_is_protected", lambda: True)
    long_notes = "\n".join("Time: note line %d about the build, kept private for Lorenzo only." % i
                           for i in range(120))
    r = tch_room()
    r["job"]["private_notes"] = long_notes
    path = write_snap(tmp_path, snapshot([r]))
    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=notify,
                           ghl=FakeGHL())
    card = next(c for c in notify.calls if c["title"] == "Upwork T1 for Orchard Lane Dental")  # protected
    assert len(card["message"].encode("utf-8")) <= tick.CARD_MAX_BYTES
    assert card["message"].endswith("(truncated; the full text is in %s)" % result["batch_path"])
    assert thread(store, "room_tch1")["pending"]["text"] in card["message"]
    assert len(card["kw"]["email_message"]) > len(card["message"])


def test_truncate_bytes_keeps_short_text():
    assert tick.truncate_bytes("short", 100, "(cut)") == "short"
    out = tick.truncate_bytes("x" * 500, 100, "(cut)")
    assert len(out.encode("utf-8")) <= 100 and out.endswith("(cut)")


# ------------------------------------------------------------------ Job_Log
def test_job_log_row_has_the_counts(store, tmp_path, world):
    seed(store)
    result, _l, _n, _g = full_run(store, tmp_path)
    job, status, details = world["logs"][-1]
    assert job == "upwork_followup"
    assert status == result["status"]
    for key in ("rooms", "enrolled", "drafted", "needs_edit", "sent_detected", "replies", "won", "lost",
                "deferred", "needs_review", "ghl_errors", "errors", "snapshot_age_h", "mode"):
        assert key in details, key
    assert details["rooms"] == 5
    assert details["enrolled"] == 3
    assert details["drafted"] == 3
    assert details["replies"] == 1
    assert details["mode"] == "run"
    assert details["batch"] == result["batch_path"]


def test_sent_detection_counts_on_the_next_run(store, tmp_path, world):
    path = write_snap(tmp_path, snapshot([tch_room()]))
    tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                  ghl=FakeGHL())
    later = NOW + timedelta(days=1)
    r = tch_room()
    r["messages"].append(msg("t3", "freelancer", later - timedelta(hours=2), "sent my own version"))
    r["last_side"], r["last_message_at"] = "freelancer", r["messages"][-1]["at"]
    path = write_snap(tmp_path, snapshot([r], generated=later - timedelta(minutes=5)))
    result = tick.run_tick(later, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert result["counts"]["sent_detected"] == 1
    assert world["logs"][-1][2]["sent_detected"] == 1
    assert thread(store, "room_tch1")["touch_index"] == 1


# ------------------------------------------------------------------ idempotency
def test_second_run_makes_no_new_drafts_or_cards(store, tmp_path):
    seed(store)
    first, llm, notify, ghl = full_run(store, tmp_path)
    assert len(notify.calls) == 4
    first_text = batch_text(first)

    llm2, notify2 = FakeLLM(), FakeNotify()
    second = tick.run_tick(NOW + timedelta(minutes=3), "run", store=store,
                           snapshot_path=tmp_path / "snapshot.json", llm=llm2, notify_fn=notify2, ghl=ghl)
    assert llm2.calls == []
    assert notify2.calls == []
    assert second["counts"]["drafted"] == 0
    assert second["counts"]["pending"] == 3
    second_text = batch_text(second)
    assert second["batch_path"] == first["batch_path"]
    assert fenced_blocks(second_text) == fenced_blocks(first_text)
    assert second_text.count("Pending since 2026-09-22.") == 3


def test_record_pending_refusal_drops_the_draft_without_a_card(store, tmp_path, monkeypatch):
    real = tick.sequence.record_pending

    def refuse(thread_, kind, touch, text, now_, card_id_):
        if text is None:          # a reservation, if sequence reserves through this function
            return real(thread_, kind, touch, text, now_, card_id_)
        raise sequence.PendingRefused("stage_not_drafting", "call_booked")

    monkeypatch.setattr(tick.sequence, "record_pending", refuse)
    path = write_snap(tmp_path, snapshot([tch_room()]))
    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=notify,
                           ghl=FakeGHL())
    assert result["drafts"] == [] and result["counts"]["drafted"] == 0
    assert result["dropped"] == [{"room_id": "room_tch1", "kind": "touch", "touch": 1,
                                  "reason": "stage_not_drafting"}]
    assert not any("(T1)" in c["title"] or c["title"].startswith("Upwork T1") for c in notify.calls)
    assert "Follow-up T1 draft dropped, no card: stage_not_drafting" in batch_text(result)


# ------------------------------------------------------------------ round 2: public topic
def test_public_topic_push_carries_no_client_text_and_no_path(store, tmp_path, monkeypatch):
    """The real shared.notify, NOTIFY_SHADOW_SEND=1 in-process, ntfy on a
    MockTransport: what would reach the public topic has no client, company or
    job words and no local path."""
    import httpx
    from shared import notify as notify_mod

    sent = []

    def handler(request):
        sent.append({"title": request.headers.get("Title"), "body": request.content.decode("utf-8")})
        return httpx.Response(200, json={"id": "x"})

    real_client = httpx.Client

    class Mocked(real_client):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super(Mocked, self).__init__(*a, **k)

    monkeypatch.setattr(notify_mod.httpx, "Client", Mocked)
    monkeypatch.setattr(tick, "topic_is_protected", notify_mod.topic_is_protected)
    for k in ("NTFY_TOKEN", "NTFY_ALLOW_SENSITIVE", "NOTIFY_EMAIL", "NOTIFICATION_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NOTIFY_SHADOW_SEND", "1")
    monkeypatch.setenv("NTFY_TOPIC", "advero-0123456789ab")
    notify_mod.reset_for_tests()

    r = rep_room()
    r["client"] = "Maria Lopez, Lopez Family Dental"
    path = write_snap(tmp_path, snapshot([r]))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM())   # real notify
    assert len(sent) == 2, sent
    words = ("Maria", "Lopez", "Dental", "Juniper", "Pipedrive", "invoice", "bakery", "delivery", "1,800",
             "Open room", str(tmp_path), "/private", "/Users", ".md")
    for push in sent:
        text = (push["title"] or "") + "\n" + push["body"]
        for w in words:
            assert w not in text, (w, push)
        assert "draft ready" not in push["title"].lower()
        assert "email" not in push["body"].lower()          # no email leg is configured
    assert sent[0]["title"] == "Upwork: 1 new draft (reply)"
    assert "drafts file on the laptop" in sent[0]["body"]
    assert result["cards_state"] == "delivered"


def test_email_wording_only_when_email_is_configured(store, tmp_path, monkeypatch):
    monkeypatch.setattr(tick, "email_configured", lambda: True)
    path = write_snap(tmp_path, snapshot([tch_room()]))
    notify = FakeNotify()
    tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=notify, ghl=FakeGHL())
    assert all("The full card went by email." in c["message"] for c in notify.calls)


def test_summary_and_error_cards_never_say_draft_ready(store, tmp_path):
    notify = FakeNotify()
    tick.run_tick(NOW, "run", store=store, snapshot_path=tmp_path / "missing.json", notify_fn=notify)
    path = write_snap(tmp_path, snapshot([wai_room()]))
    tick.run_tick(NOW + timedelta(days=1), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                  notify_fn=notify, ghl=FakeGHL())
    assert [c["title"].split(":")[0] for c in notify.calls] == ["Upwork drafts", "Upwork drafts"]
    for c in notify.calls:
        assert "draft ready" not in (c["title"] + c["message"]).lower()
        assert str(tmp_path) not in c["message"]


# ------------------------------------------------------------------ round 2: contract beats a GHL move
@pytest.mark.parametrize("ghl_stage", ["call_booked", "proposal_sent"])
def test_contract_and_ghl_move_in_the_same_run_end_won(store, tmp_path, upwork_pipeline, ghl_stage):
    at = datetime(2026, 9, 19, 16, tzinfo=timezone.utc)
    sequence.run(store, snapshot([tch_room()], generated=at), at, seed_classify)
    _with_real_ghl_ids(store, "room_tch1")
    contracted = [{"room_id": "room_tch1", "contract_id": "ct_9", "status": "ACTIVE", "proposal_id": "p"}]
    path = write_snap(tmp_path, snapshot([], contracted=contracted))
    ghl = FakeGHL(stage_id=upwork_pipeline["stages"][ghl_stage])
    llm = FakeLLM()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=FakeNotify(), ghl=ghl)

    t = thread(store, "room_tch1")
    assert (t["stage"], t["stage_set_by"], t["status"]) == ("won", "engine", "won")
    assert "get_opportunity" not in ghl.names()       # the read-back is skipped for a contracted room
    updates = [c for c in ghl.calls if c[0] == "update_opportunity_stage"]
    assert updates and upwork_pipeline["stages"]["won"] in updates[-1][1]
    assert llm.drafts_called() == [] and result["drafts"] == []


# ------------------------------------------------------------------ round 2: snapshot alerts
def test_missing_snapshot_alerts_once_per_central_day(store, tmp_path):
    notify = FakeNotify()
    per_day = []
    for day in (22, 23, 24):
        at = datetime(2026, 9, day, 13, 30, tzinfo=timezone.utc)
        before = len(notify.calls)
        tick.run_tick(at, "run", store=store, snapshot_path=tmp_path / "nope.json", notify_fn=notify)
        tick.run_tick(at + timedelta(minutes=20), "run", store=store, snapshot_path=tmp_path / "nope.json",
                      notify_fn=notify)
        per_day.append([c["title"] for c in notify.calls[before:]])
    assert per_day == [["Upwork drafts: no snapshot"]] * 3
    assert all(c["kw"]["priority"] == "high" for c in notify.calls)


def test_future_snapshot_is_an_error_run_with_an_alert(store, tmp_path, world):
    path = write_snap(tmp_path, snapshot([tch_room()], generated=NOW + timedelta(hours=3)))
    llm, notify = FakeLLM(), FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())
    assert result["status"] == "error" and result["snapshot_error"].startswith("future")
    assert llm.calls == [] and store.keys("upwork:") == []
    assert [c["title"] for c in notify.calls] == ["Upwork drafts: snapshot from the future"]
    assert world["logs"][-1][1] == "error"


@pytest.mark.parametrize("minutes,refused", [(9, False), (11, True)])
def test_future_rule_is_the_ingests(store, tmp_path, minutes, refused):
    """collect.is_future_stamp (10-minute drift) decides, as at ingest: 9 minutes
    ahead passes both, 11 minutes ahead is refused by both."""
    stamp = NOW + timedelta(minutes=minutes)
    assert collect.is_future_stamp(iso(stamp), NOW) is refused
    path = write_snap(tmp_path, snapshot([tch_room()], generated=stamp))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    if refused:
        assert result["status"] == "error" and result["snapshot_error"].startswith("future")
        assert result["counts"]["drafted"] == 0
    else:
        assert result["snapshot_error"] is None and result["counts"]["drafted"] == 1


def test_incomplete_pull_is_warned_in_batch_and_summary(store, tmp_path):
    snap = snapshot([tch_room()])
    snap["link_errors"] = ["prop_lost1", "prop_lost2"]
    snap["sections"]["offers"] = False
    snap["sections"]["contracts"] = False
    path = write_snap(tmp_path, snap)
    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=notify,
                           ghl=FakeGHL())
    line = "Upwork data incomplete: 2 room links failed; sections missing: contracts, offers."
    assert result["status"] == "attention"
    assert line in batch_text(result)
    summary = notify.calls[-1]
    assert summary["title"].startswith("Upwork drafts:")
    assert line in summary["message"] and line in summary["kw"]["email_message"]
    assert result["counts"]["drafted"] == 1        # the rest of the batch still runs


def test_a_complete_pull_has_no_incomplete_warning():
    assert tick.incomplete_warning(snapshot([tch_room()])) is None


# ------------------------------------------------------------------ round 2: run lock
def test_a_live_lock_makes_a_second_run_do_nothing(store, tmp_path, world):
    path = write_snap(tmp_path, snapshot([tch_room()]))
    notify, drafts = FakeNotify(), []
    inner = {}

    class NestedLLM(FakeLLM):
        def __call__(self, role, system, user, **kw):
            if role == "draft" and not inner:
                inner["result"] = tick.run_tick(NOW + timedelta(minutes=1), "run", store=store, snapshot_path=path,
                                                llm=FakeLLM(), notify_fn=notify, ghl=FakeGHL())
            if role == "draft":
                drafts.append(role)
            return FakeLLM.__call__(self, role, system, user, **kw)

    outer = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=NestedLLM(), notify_fn=notify,
                          ghl=FakeGHL())
    assert inner["result"]["status"] == "locked"
    assert inner["result"]["drafts"] == [] and inner["result"]["cards"] == []
    assert outer["counts"]["drafted"] == 1 and drafts == ["draft"]
    assert [c["title"] for c in notify.calls] == ["Upwork: 1 new draft (T1)", "Upwork drafts: 1 new, 1 pending"]
    assert [row[1] for row in world["logs"]] == ["locked", "ok"]
    assert store.get(tick.LOCK_KEY)["owner"] is None        # released at the end


def test_dry_run_ignores_the_lock(store, tmp_path):
    store.set(tick.LOCK_KEY, a_lease("live-run", WALL))
    path = write_snap(tmp_path, snapshot([tch_room()]))
    result = tick.run_tick(NOW, "dry-run", store=store, snapshot_path=path)
    assert result["status"] == "ok" and result["counts"]["drafted"] == 1


# ------------------------------------------------------------------ round 3: the lease on the real clock
def a_lease(owner, stamped, minutes=30):
    """A lease record as another run would have left it."""
    return {"owner": owner, "acquired_at": stamped.isoformat(), "heartbeat_at": stamped.isoformat(),
            "expires_at": (stamped + timedelta(minutes=minutes)).isoformat(), "pid": 4242}


def tch_run(store, tmp_path, as_of=NOW, llm=None, notify=None):
    """One --run on the Orchard Lane room (T1 due), with a snapshot 10 minutes older than ``as_of``."""
    path = write_snap(tmp_path, snapshot([tch_room()], generated=as_of - timedelta(minutes=10)))
    return tick.run_tick(as_of, "run", store=store, snapshot_path=path, llm=llm or FakeLLM(),
                         notify_fn=notify or FakeNotify(), ghl=FakeGHL())


def test_a_live_lease_blocks_and_is_left_as_it_was(store, tmp_path, world):
    """Reviewer case 1: a run that died 5 minutes ago still blocks."""
    held = a_lease("scheduled-run", WALL - timedelta(minutes=5))
    store.set(tick.LOCK_KEY, held)
    llm, notify = FakeLLM(), FakeNotify()
    result = tch_run(store, tmp_path, llm=llm, notify=notify)
    assert result["status"] == "locked"
    assert llm.calls == [] and notify.calls == [] and store.keys("upwork:") == []
    assert store.get(tick.LOCK_KEY) == held
    assert result["locked"]["free_by"] == (WALL + timedelta(minutes=25)).isoformat()
    assert result["locked"]["clock_problem"] is False
    assert world["logs"][-1][1] == "locked"


def test_a_stale_lock_is_taken_over_noted_and_released(store, tmp_path, world):
    """Reviewer case 2: no heartbeat for 31 minutes."""
    store.set(tick.LOCK_KEY, a_lease("dead-run", WALL - timedelta(minutes=31)))
    result = tch_run(store, tmp_path)
    assert result["status"] == "ok" and result["counts"]["drafted"] == 1
    details = world["logs"][-1][2]
    assert details["lock_taken_over"]["acquired_at"] == (WALL - timedelta(minutes=31)).isoformat()
    text = batch_text(result)
    assert "took over a stale run lock" in text and "no heartbeat since" in text
    assert store.get(tick.LOCK_KEY)["owner"] is None


@pytest.mark.parametrize("shift", [timedelta(days=-1), timedelta(days=1)], ids=["past_as_of", "future_as_of"])
def test_an_as_of_run_cannot_take_a_live_lease(store, tmp_path, world, shift):
    """Reviewer case 5: --as-of a day off is irrelevant to the lease. On the
    real clock the scheduled run's lease is 5 minutes old."""
    held = a_lease("scheduled-run", WALL)
    store.set(tick.LOCK_KEY, held)
    world["clock"].advance(minutes=5)
    llm = FakeLLM()
    result = tch_run(store, tmp_path, as_of=NOW + shift, llm=llm)
    assert result["status"] == "locked" and llm.calls == []
    assert store.get(tick.LOCK_KEY) == held            # neither taken over nor released


def test_the_lease_is_stamped_on_the_real_clock_not_the_as_of(store, tmp_path, world):
    seen = []

    class Peek(FakeLLM):
        def __call__(self, role, system, user, **kw):
            if role == "draft":
                seen.append(store.get(tick.LOCK_KEY))
            return FakeLLM.__call__(self, role, system, user, **kw)

    result = tch_run(store, tmp_path, as_of=NOW - timedelta(days=1), llm=Peek())
    assert result["counts"]["drafted"] == 1
    lease = seen[0]
    assert lease["acquired_at"] == WALL.isoformat() and lease["heartbeat_at"] == WALL.isoformat()
    assert lease["expires_at"] == (WALL + timedelta(minutes=30)).isoformat()
    assert lease["as_of"] == (NOW - timedelta(days=1)).isoformat()
    assert store.get(tick.LOCK_KEY) == {"owner": None, "released_at": WALL.isoformat(),
                                        "released_by": lease["owner"]}


@pytest.mark.parametrize("ahead", [timedelta(minutes=29), timedelta(hours=2), timedelta(days=1)],
                         ids=["29min", "2h", "1day"])
def test_a_lease_stamped_in_the_future_blocks_one_ttl_at_most(store, tmp_path, world, ahead):
    """Reviewer cases 3 and 4. Stamped ahead of the real clock (a holder whose
    clock runs fast, or an older run stamped with a future --as-of): the first
    run it blocks marks it, and one TTL later it is free, however far ahead it
    is stamped."""
    store.set(tick.LOCK_KEY, a_lease("fast-clock-run", WALL + ahead))
    first = tch_run(store, tmp_path)
    assert first["status"] == "locked"
    assert first["locked"]["clock_problem"] is True
    assert first["locked"]["free_by"] == (WALL + timedelta(minutes=30)).isoformat()
    assert store.get(tick.LOCK_KEY)["clock_suspect_at"] == WALL.isoformat()
    world["clock"].advance(minutes=29, seconds=59)
    assert tch_run(store, tmp_path)["status"] == "locked"
    world["clock"].advance(seconds=1)                   # one TTL after it first blocked a run
    later = tch_run(store, tmp_path)
    assert later["status"] == "ok" and later["counts"]["drafted"] == 1
    assert "ahead of this machine's clock" in later["lock_taken_over"]["why"]


def test_a_holders_heartbeat_clears_the_clock_mark(store):
    """A live holder whose clock runs 10 minutes fast keeps its lease: every
    renewal drops the mark a blocked run left, and a later check re-marks it
    from that moment."""
    token = "fast-holder"
    store.set(tick.LOCK_KEY, a_lease(token, WALL + timedelta(minutes=10)))
    got = tick.acquire_lock(store, WALL, "second-run")
    assert got["held"]["owner"] == token and got["lease"] is None
    assert store.get(tick.LOCK_KEY)["clock_suspect_at"] == WALL.isoformat()
    lease, found = tick.renew_lock(store, WALL + timedelta(minutes=10), token)   # its own, fast, clock
    assert found is None and "clock_suspect_at" not in lease and lease["beats"] == 1
    assert store.get(tick.LOCK_KEY) == lease
    tick.renew_lock(store, WALL + timedelta(minutes=41), token)                 # still renewing 31 min on
    got = tick.acquire_lock(store, WALL + timedelta(minutes=31), "second-run")
    assert got["held"]["owner"] == token
    assert tick.lock_state(store.get(tick.LOCK_KEY), WALL + timedelta(minutes=31)) == "live"


def test_lease_writes_compare_and_set_on_the_owner_token(store):
    store.set(tick.LOCK_KEY, a_lease("run-a", WALL))
    before = store.get(tick.LOCK_KEY)
    lease, found = tick.renew_lock(store, WALL + timedelta(minutes=1), "run-b")
    assert lease is None and found == before and store.get(tick.LOCK_KEY) == before
    assert tick.release_lock(store, "run-b", WALL) is True
    assert store.get(tick.LOCK_KEY) == before           # not run-b's to give back
    tick.release_lock(store, "run-a", WALL + timedelta(minutes=2))
    released = store.get(tick.LOCK_KEY)
    assert released["owner"] is None and released["released_by"] == "run-a"
    lease, found = tick.renew_lock(store, WALL + timedelta(minutes=3), "run-a")
    assert lease is None and found == released           # a released lease is not renewed back


class DictOnlyStore(Store):
    """A store with get and set only: no atomic mutate."""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def set(self, key, value):
        self.data[key] = copy.deepcopy(value)


def test_a_store_without_mutate_writes_then_rereads_the_lease():
    s = DictOnlyStore()
    got = tick.acquire_lock(s, WALL, "run-a")
    assert got["lease"]["owner"] == "run-a" and s.get(tick.LOCK_KEY)["owner"] == "run-a"
    assert tick.acquire_lock(s, WALL + timedelta(minutes=1), "run-b")["held"]["owner"] == "run-a"
    lease, _ = tick.renew_lock(s, WALL + timedelta(minutes=2), "run-a")
    assert lease["heartbeat_at"] == (WALL + timedelta(minutes=2)).isoformat()

    class Racing(DictOnlyStore):
        """Another writer lands between this run's set and its re-read."""

        def set(self, key, value):
            DictOnlyStore.set(self, key, value)
            if key == tick.LOCK_KEY and isinstance(value, dict) and value.get("owner") == "run-a":
                self.data[key] = dict(value, owner="run-c")

    r = Racing()
    got = tick.acquire_lock(r, WALL, "run-a")
    assert got["lease"] is None and got["held"]["owner"] == "run-c"


class FlakyLockStore(JsonFileStore):
    """Lease writes fail once armed (the store is down at release time)."""
    armed = False

    def mutate(self, key, fn, default=None):
        if key == tick.LOCK_KEY and self.armed:
            raise RuntimeError("store down (invented)")
        return JsonFileStore.mutate(self, key, fn, default)


def test_a_failed_release_leaves_the_lease_to_its_ttl(tmp_path, world):
    """Reviewer case 7."""
    flaky = FlakyLockStore(tmp_path / "flaky.json")

    class ArmOnSummary(FakeNotify):
        def __call__(self, title, message, **kw):
            if title.startswith("Upwork drafts"):
                flaky.armed = True
            return FakeNotify.__call__(self, title, message, **kw)

    first = tch_run(flaky, tmp_path, notify=ArmOnSummary())
    assert first["status"] == "ok" and first["counts"]["drafted"] == 1
    flaky.armed = False
    assert flaky.get(tick.LOCK_KEY)["owner"]             # the release failed: still held
    world["clock"].advance(minutes=10)
    assert tch_run(flaky, tmp_path)["status"] == "locked"
    world["clock"].advance(minutes=21)                    # 31 minutes after its last heartbeat
    later = tch_run(flaky, tmp_path)
    assert later["status"] == "ok" and later["lock_taken_over"]


@pytest.mark.parametrize("b_as_of", [NOW + timedelta(minutes=31), NOW], ids=["later_as_of", "same_as_of"])
def test_a_run_that_outlives_the_ttl_never_double_drafts(store, tmp_path, world, b_as_of):
    """Reviewer case 6. Run A's first draft call hangs 31 minutes; run B starts
    then, takes the stale lease over and drafts both rooms. A records nothing
    and sends no card: one draft and one card per room."""
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room()]))
    notify, inner = FakeNotify(), {}

    class Hangs(FakeLLM):
        def __call__(self, role, system, user, **kw):
            if role == "draft" and not inner:
                world["clock"].advance(minutes=31)
                inner["b"] = tick.run_tick(b_as_of, "run", store=store, snapshot_path=path, llm=FakeLLM(),
                                           notify_fn=notify, ghl=FakeGHL())
            return FakeLLM.__call__(self, role, system, user, **kw)

    a = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=Hangs(), notify_fn=notify, ghl=FakeGHL())
    b = inner["b"]
    assert b["lock_taken_over"] and b["status"] == "ok" and b["counts"]["drafted"] == 2
    assert a["status"] == "lock_lost" and a["counts"]["drafted"] == 0 and a["cards"] == []
    assert a["lock_lost"]["reason"] == "released" and a["lock_lost"]["released"] == []
    for rid in ("room_rep1", "room_tch1"):
        t = thread(store, rid)
        assert [h["event"] for h in t["history"]].count("drafted") == 1, t["history"]
        assert t["pending"]["text"] and tick.CLAIM_KEY not in t
    titles = [c["title"] for c in notify.calls]
    assert sorted(titles[:2]) == ["Upwork: 1 new draft (T1)", "Upwork: 1 new draft (reply)"]
    assert len(titles) == 3                               # B's two cards and B's summary; none from A
    assert store.get(tick.LOCK_KEY)["owner"] is None
    assert [row[1] for row in world["logs"]] == ["ok", "lock_lost"]
    assert "LOCK LOST" in world["logs"][-1][2]["warnings"][0]


def test_heartbeats_keep_a_slow_run_ahead_of_a_second_run(store, tmp_path, world):
    """Each draft call takes 20 minutes. 40 minutes in, past one TTL, the lease
    is live because every call renewed it: a second run is locked out and the
    first finishes normally."""
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room()]))
    inner = []

    class Slow(FakeLLM):
        def __call__(self, role, system, user, **kw):
            if role == "draft":
                earlier = len(self.drafts_called())
                world["clock"].advance(minutes=20)
                if earlier == 1:                          # the second draft call, 40 minutes in
                    inner.append(tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(),
                                               notify_fn=FakeNotify(), ghl=FakeGHL()))
            return FakeLLM.__call__(self, role, system, user, **kw)

    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=Slow(), notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert inner[0]["status"] == "locked"
    assert inner[0]["locked"]["heartbeat_at"] == (WALL + timedelta(minutes=20)).isoformat()
    assert result["status"] == "ok" and result["counts"]["drafted"] == 2 and result["lock_lost"] is None


def test_the_lease_is_renewed_before_every_model_call_record_and_card(store, tmp_path, monkeypatch):
    seed(store)
    events = []
    real_renew, real_record = tick.renew_lock, tick.sequence.record_pending

    def renew(store_, wall, token):
        out = real_renew(store_, wall, token)
        events.append("renew")
        return out

    def record(thread_, kind, touch, text, now_, cid):
        events.append("record")
        return real_record(thread_, kind, touch, text, now_, cid)

    class Logged(FakeLLM):
        def __call__(self, role, system, user, **kw):
            events.append("model " + role)
            return FakeLLM.__call__(self, role, system, user, **kw)

    class LoggedNotify(FakeNotify):
        def __call__(self, title, message, **kw):
            events.append("card")
            return FakeNotify.__call__(self, title, message, **kw)

    monkeypatch.setattr(tick, "renew_lock", renew)
    monkeypatch.setattr(tick.sequence, "record_pending", record)
    full_run(store, tmp_path, llm=Logged(), notify=LoggedNotify())
    critical = [i for i, e in enumerate(events) if e != "renew"]
    kinds = [events[i] for i in critical]
    assert kinds.count("model draft") == 3 and kinds.count("model classify") == 1
    assert kinds.count("record") == 3 and kinds.count("card") == 4
    for i in critical:
        assert i > 0 and events[i - 1] == "renew", events[max(0, i - 3):i + 1]


def test_a_lease_lost_mid_run_stops_drafts_records_and_cards(store, tmp_path, world):
    """Another run takes the lease while this run's second draft call is out:
    that draft is not recorded, the third is never started, no card goes out,
    and only this run's own unfilled reservations are given back."""
    seed(store)
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room(), wai_room(), chk_room(), bkd_room()]))

    class StolenDuringSecondDraft(FakeLLM):
        def __call__(self, role, system, user, **kw):
            out = FakeLLM.__call__(self, role, system, user, **kw)
            if role == "draft" and len(self.drafts_called()) == 2:
                store.set(tick.LOCK_KEY, a_lease("intruder", WALL))
            return out

    llm, notify = StolenDuringSecondDraft(), FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())

    assert result["status"] == "lock_lost" and result["lock_lost"]["reason"] == "taken_over"
    assert llm.drafts_called() == ["draft", "draft"]
    assert notify.calls == [] and result["cards"] == []
    assert result["counts"]["drafted"] == 1
    kept = [rid for rid in ("room_rep1", "room_tch1", "room_chk1")
            if (thread(store, rid)["pending"] or {}).get("text")]
    assert kept == ["room_rep1"]                          # the reply went first: its client is waiting
    for rid in ("room_tch1", "room_chk1"):
        t = thread(store, rid)
        assert t["pending"] is None and tick.CLAIM_KEY not in t
        assert (t["history"][-1]["event"], t["history"][-1]["reason"]) == ("withdrawn", "lock_lost")
    assert sorted(result["lock_lost"]["released"]) == ["room_chk1", "room_tch1"]
    assert store.get(tick.LOCK_KEY)["owner"] == "intruder"    # another run's lease is left alone
    assert "LOCK LOST" in batch_text(result)
    job, status, details = world["logs"][-1]
    assert status == "lock_lost" and details["lock_lost"]["reason"] == "taken_over"
    assert details["lock_lost"]["holder"]["pid"] == 4242

    # once the intruder's lease is stale, the next run drafts the two that went
    # back and sends the recorded reply's card late
    world["clock"].advance(minutes=31)
    again = FakeNotify()
    later = tick.run_tick(NOW + timedelta(minutes=40), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                          notify_fn=again, ghl=FakeGHL())
    assert later["counts"]["drafted"] == 2 and later["lock_taken_over"]
    firsts = sorted(c["kw"]["email_message"].split("\n", 1)[0] for c in again.calls[:3])
    assert firsts == ["Upwork T1 for Orchard Lane Dental", "Upwork check-in for Harbor Yoga Studio",
                      "Upwork reply for Juniper Bakery Co"]


def test_a_lease_lost_between_cards_sends_no_more_cards(store, tmp_path, world):
    seed(store)

    class GoneAfterFirstCard(FakeNotify):
        def __call__(self, title, message, **kw):
            out = FakeNotify.__call__(self, title, message, **kw)
            if len(self.calls) == 1:
                store.delete(tick.LOCK_KEY)
            return out

    result, _llm, notify, _g = full_run(store, tmp_path, notify=GoneAfterFirstCard())
    assert len(notify.calls) == 1                         # no second card and no summary card
    assert result["status"] == "lock_lost" and result["lock_lost"]["reason"] == "gone"
    assert result["counts"]["drafted"] == 3 and result["lock_lost"]["released"] == []
    marked = [rid for rid in ("room_rep1", "room_tch1", "room_chk1")
              if thread(store, rid)["draft_meta"].get("card_sent_at")]
    assert len(marked) == 1                               # the card that went out is marked sent
    again = FakeNotify()
    tick.run_tick(NOW + timedelta(minutes=5), "run", store=store, snapshot_path=tmp_path / "snapshot.json",
                  llm=FakeLLM(), notify_fn=again, ghl=FakeGHL())
    late = [c for c in again.calls if c["title"].startswith("Upwork: 1 new draft")]
    assert len(late) == 2                                 # the other two; the first is not sent twice


def test_a_lease_lost_during_sequence_run_advances_nothing_more(store, tmp_path, world, monkeypatch):
    """The lease is gone by the second room's write: sequence.run writes
    nothing more (those rooms count as not advanced, not as errors), no model
    call follows, and the reservation already made is given back."""
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room(), wai_room()]))
    real_renew = tick.renew_lock
    calls = []

    def renew(store_, wall, token):
        calls.append(wall)
        # 1: the meta record, 2: the first room's classifier call (outside any
        # lock), 3: the first room's write, 4: the second room's write
        if len(calls) >= 4:
            return None, a_lease("intruder", wall)
        return real_renew(store_, wall, token)

    monkeypatch.setattr(tick, "renew_lock", renew)
    llm, notify = FakeLLM(), FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())
    assert result["status"] == "lock_lost" and result["lock_lost"]["reason"] == "taken_over"
    assert llm.calls == ["classify"]                      # the first room's classification, then nothing
    assert thread(store, "room_tch1") is None and thread(store, "room_wai1") is None
    assert result["counts"]["lock_skipped"] == 2 and result["errors"] == []
    rep = thread(store, "room_rep1")
    assert rep["pending"] is None and rep["history"][-1]["reason"] == "lock_lost"
    assert result["lock_lost"]["released"] == ["room_rep1"]
    assert notify.calls == []


# ------------------------------------------------------------------ round 2: run budget
def test_run_budget_stops_drafting_and_leaves_the_rest_for_next_run(store, tmp_path, monkeypatch, world):
    seed(store)
    monkeypatch.setattr(tick, "call_cost", lambda role, system, user, max_tokens, **kw: 0.5)
    monkeypatch.setenv(tick.BUDGET_ENV, "1.2")
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room(), wai_room(), chk_room(), bkd_room()]))
    llm, notify = FakeLLM(), FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())

    # 1 classify (0.5) + 1 draft (0.5) = 1.0; the next draft (1.5) is refused
    assert llm.calls.count("draft") == 1
    assert result["counts"]["drafted"] == 1
    assert result["counts"]["budget_deferred"] == 2
    assert result["budget"] == "budget" and result["status"] == "attention"
    assert result["errors"] == []
    pend = [thread(store, r)["pending"] for r in ("room_rep1", "room_tch1", "room_chk1")]
    assert sum(1 for p in pend if p and p.get("text")) == 1
    assert sum(1 for p in pend if p and p.get("text") is None) == 0   # released, not left as placeholders
    assert "RUN BUDGET" in batch_text(result)
    assert world["logs"][-1][2]["budget_hit"] == "budget"
    assert world["logs"][-1][2]["llm"]["projected_usd"] == 1.0

    monkeypatch.setenv(tick.BUDGET_ENV, "5")
    later = tick.run_tick(NOW + timedelta(minutes=30), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                          notify_fn=notify, ghl=FakeGHL())
    assert later["counts"]["drafted"] == 2 and later["budget"] is None


def test_classify_cap_leaves_the_reply_for_next_run(store, tmp_path, monkeypatch):
    monkeypatch.setenv(tick.CLASSIFY_CAP_ENV, "0")
    path = write_snap(tmp_path, snapshot([rep_room(), tch_room()]))
    llm = FakeLLM()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert "classify" not in llm.calls
    assert thread(store, "room_rep1") is None             # not advanced: enrolled on the next run
    assert result["budget"] == "classify_cap" and result["errors"] == []
    assert result["counts"]["budget_deferred"] >= 1
    monkeypatch.delenv(tick.CLASSIFY_CAP_ENV)
    again = tick.run_tick(NOW + timedelta(minutes=5), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                          notify_fn=FakeNotify(), ghl=FakeGHL())
    assert thread(store, "room_rep1")["pending"]["kind"] == "reply" and again["budget"] is None


def test_meter_counts_projected_cost_from_shared_llm(monkeypatch):
    m = tick.Meter(lambda role, system, user, **kw: "ok", budget=10, max_classify=5)
    assert m("draft", "system text", "user text", max_tokens=400) == "ok"
    assert m.calls == {"draft": 1} and m.spent > 0


def test_meter_counts_exactly_what_shared_llm_reserves(monkeypatch, tmp_path):
    """call_cost priced the caller's bare max_tokens while complete() reserves
    max_tokens + THINKING_HEADROOM_TOKENS, so every call counted about half
    its cost against the $1.50 run cap. The Meter's count must equal what
    complete() hands enforce_budget, for a JSON classification and a draft."""
    monkeypatch.setenv("LLM_FAKE", "0")
    monkeypatch.setenv("LLM_LEDGER_PATH", str(tmp_path / "ledger.csv"))
    reserved = []

    def spy(role, model, system, user, max_tokens):
        cost = shared_llm_mod.projected_cost_usd(model, system, user, max_tokens)
        reserved.append((role, max_tokens, cost))
        return {"reserved_usd": cost, "reserved_in_store": False}

    class _Messages(object):
        def create(self, **kwargs):
            if "JSON" in (kwargs.get("system") or ""):
                text = '{"label": "positive", "confidence": 0.9}'
            else:
                text = "a draft"
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=None,
                                   stop_reason="end_turn")

    monkeypatch.setattr(shared_llm_mod, "enforce_budget", spy)
    monkeypatch.setattr(shared_llm_mod, "_client", lambda: SimpleNamespace(messages=_Messages()))
    monkeypatch.setattr(shared_llm_mod, "complete", REAL_COMPLETE)
    m = tick.Meter(None, budget=10, max_classify=5)
    m("classify", "classify system " * 40, "client text " * 60, max_tokens=200, json_mode=True)
    after_classify = m.spent
    m("draft", "draft system " * 300, "thread " * 400, max_tokens=400)

    assert [r[:2] for r in reserved] == [
        ("classify", 200 + shared_llm_mod.THINKING_HEADROOM_TOKENS),
        ("draft", 400 + shared_llm_mod.THINKING_HEADROOM_TOKENS)]
    assert after_classify == pytest.approx(reserved[0][2], abs=1e-9)
    assert m.spent - after_classify == pytest.approx(reserved[1][2], abs=1e-9)
    assert tick.call_cost("draft", "s", "u", 400) == shared_llm_mod.reserved_cost_usd("draft", "s", "u", 400)


# ------------------------------------------------------------------ polish: shared LLM ceiling
class CeilingLLM(FakeLLM):
    """shared.llm at its cumulative ceiling: every call in ``refuse`` raises
    LLMBudgetExceeded, as complete() does before billing."""

    def __init__(self, refuse=("classify", "escalate", "draft"), **kw):
        FakeLLM.__init__(self, **kw)
        self.refuse = tuple(refuse)

    def __call__(self, role, system, user, max_tokens=800, json_mode=False):
        if role in self.refuse:
            self.calls.append(role)
            raise shared_llm_mod.LLMBudgetExceeded("LLM spend ceiling reached (invented)")
        return FakeLLM.__call__(self, role, system, user, max_tokens=max_tokens, json_mode=json_mode)


def test_meter_records_the_shared_ceiling_and_stops_calling_the_model():
    inner = CeilingLLM()
    m = tick.Meter(inner, budget=10, max_classify=5)
    with pytest.raises(shared_llm_mod.LLMBudgetExceeded):
        m("classify", "system", "user text")
    assert m.hit == tick.CEILING_HIT and m.ceiling_refusals == 1 and m.refusals == 1
    with pytest.raises(shared_llm_mod.LLMBudgetExceeded):
        m("escalate", "system", "user text")
    assert inner.calls == ["classify"]            # the second one never reached shared.llm
    assert m.can_classify() is False and m.can_draft() is False


def test_a_reply_at_the_shared_ceiling_stays_unread_not_neutral(store, tmp_path, world):
    path = write_snap(tmp_path, snapshot([chk_room()]))
    llm = CeilingLLM()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert llm.calls == ["classify"]              # no escalate after the refusal
    assert thread(store, "room_chk1") is None     # not enrolled on a fallback label
    assert result["budget"] == tick.CEILING_HIT and result["errors"] == []
    assert result["counts"]["budget_deferred"] == 1 and result["counts"]["needs_review"] == 0
    assert result["status"] == "attention"
    warning = [w for w in result["warnings"] if "LLM SPEND CEILING" in w]
    assert len(warning) == 1
    assert "laptop's llm.spend_usd counter" in warning[0] and "budget_status()" in warning[0]
    assert "Modal reply engine's counter is separate" in warning[0]
    assert "/" not in warning[0].split("Check it with")[0]      # no path on a public push
    assert "not this run's own budget" in warning[0]
    assert not [w for w in result["warnings"] if w.startswith("RUN BUDGET")]
    assert "LLM SPEND CEILING" in batch_text(result)
    assert world["logs"][-1][2]["budget_hit"] == tick.CEILING_HIT

    later = tick.run_tick(NOW + timedelta(minutes=30), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                          notify_fn=FakeNotify(), ghl=FakeGHL())
    t = thread(store, "room_chk1")
    assert later["budget"] is None
    assert t["stage"] == "follow_up_later" and t["last_seen_message_id"] == "k3"   # the real label


def test_a_new_message_on_an_enrolled_thread_at_the_ceiling_is_left_for_the_next_run(store, tmp_path):
    seed(store)
    before = thread(store, "room_chk1")
    chk = chk_room()
    chk["messages"].append(msg("k4", "client", datetime(2026, 9, 21, 15, tzinfo=timezone.utc),
                               "hired_other: we went with another freelancer, thanks"))
    chk["last_side"], chk["last_message_at"] = "client", chk["messages"][-1]["at"]
    path = write_snap(tmp_path, snapshot([chk, bkd_room()]))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=CeilingLLM(),
                           notify_fn=FakeNotify(), ghl=FakeGHL())
    after = thread(store, "room_chk1")
    assert result["budget"] == tick.CEILING_HIT and result["counts"]["budget_deferred"] == 1
    assert [c for c in result["check"] if c["room_id"] == "room_chk1"] == []
    assert after["last_seen_message_id"] == "k3"  # still unread
    assert (after["stage"], after["status"]) == (before["stage"], before["status"])

    tick.run_tick(NOW + timedelta(minutes=30), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                  notify_fn=FakeNotify(), ghl=FakeGHL())
    again = thread(store, "room_chk1")
    assert again["last_seen_message_id"] == "k4" and again["status"] != before["status"]


def test_a_draft_refused_at_the_shared_ceiling_is_released_for_the_next_run(store, tmp_path):
    path = write_snap(tmp_path, snapshot([tch_room(), rep_room()]))
    llm = CeilingLLM(refuse=("draft",))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert llm.calls.count("draft") == 1          # the second draft is not attempted
    assert result["counts"]["drafted"] == 0 and result["counts"]["budget_deferred"] == 2
    assert result["budget"] == tick.CEILING_HIT and result["errors"] == []
    for rid in ("room_tch1", "room_rep1"):
        assert (thread(store, rid)["pending"] or {}).get("text") is None
    later = tick.run_tick(NOW + timedelta(minutes=30), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                          notify_fn=FakeNotify(), ghl=FakeGHL())
    assert later["counts"]["drafted"] == 2


def test_the_run_budget_warning_points_at_the_shared_ceiling_check(store, tmp_path, monkeypatch):
    monkeypatch.setenv(tick.CLASSIFY_CAP_ENV, "0")
    path = write_snap(tmp_path, snapshot([rep_room()]))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    warning = [w for w in result["warnings"] if w.startswith("RUN BUDGET")]
    assert len(warning) == 1 and "shared LLM spend ceiling is separate" in warning[0]
    assert "budget_status()" in warning[0]


# ------------------------------------------------------------------ round 2: card after a killed run
def test_a_draft_recorded_without_a_card_gets_it_on_the_next_run(store, tmp_path):
    path = write_snap(tmp_path, snapshot([tch_room()]))
    tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                  ghl=FakeGHL())

    def unsent(cur):     # what a run killed between record_pending and the card leaves behind
        cur = json.loads(json.dumps(cur))
        cur["draft_meta"].pop("card_sent_at")
        return cur
    store.mutate(sequence.thread_key("room_tch1"), unsent)

    notify = FakeNotify()
    result = tick.run_tick(NOW + timedelta(minutes=30), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                           notify_fn=notify, ghl=FakeGHL())
    assert result["counts"]["drafted"] == 0
    assert [c["title"] for c in notify.calls][0] == "Upwork: 1 new draft (T1)"
    assert result["cards"][0]["late"] is True
    assert thread(store, "room_tch1")["draft_meta"]["card_sent_at"]
    again = FakeNotify()
    tick.run_tick(NOW + timedelta(minutes=40), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                  notify_fn=again, ghl=FakeGHL())
    assert again.calls == []


# ------------------------------------------------------------------ round 2: wording
def test_due_text_for_a_pending_draft():
    assert tick.due_text({"pending": True, "kind": "touch", "touch": 2}) == "Follow-up T2 drafted, not sent yet"
    assert tick.due_text({"pending": True, "kind": "checkin"}) == "Check-in drafted, not sent yet"


def test_dry_run_summary_says_would_draft_and_prints_skipped(store, tmp_path):
    path = write_snap(tmp_path, snapshot([tch_room(), rep_room()]))
    result = tick.run_tick(NOW, "dry-run", store=store, snapshot_path=path)
    text = tick.summary_text(result)
    assert "2 would draft (dry run: no model call, nothing saved)" in text
    assert "new draft" not in text
    assert "skipped 0" in text


# ------------------------------------------------------------------ round 3: lease writes and claims
class CasOnlyStore(DictOnlyStore):
    """get, set, keys and compare_and_set; no mutate."""

    def keys(self, prefix=""):
        return sorted(k for k in self.data if k.startswith(prefix))

    def compare_and_set(self, key, expected, value):
        ok = (key not in self.data) if expected is ABSENT else (key in self.data and self.data[key] == expected)
        if ok:
            self.data[key] = copy.deepcopy(value)
        return ok


def test_a_store_with_compare_and_set_but_no_mutate_uses_it():
    s = CasOnlyStore()
    assert tick.acquire_lock(s, WALL, "run-a")["lease"]["owner"] == "run-a"
    lease, _ = tick.renew_lock(s, WALL + timedelta(minutes=1), "run-a")
    assert lease["beats"] == 1 and s.data[tick.LOCK_KEY] == lease

    class Sneaky(CasOnlyStore):
        """Another run takes the lease between this run's read and its compare_and_set."""
        sneaked = False

        def compare_and_set(self, key, expected, value):
            if key == tick.LOCK_KEY and not self.sneaked:
                self.sneaked = True
                self.data[key] = a_lease("run-c", WALL)
            return CasOnlyStore.compare_and_set(self, key, expected, value)

    r = Sneaky()
    got = tick.acquire_lock(r, WALL, "run-a")
    assert got["lease"] is None and got["held"]["owner"] == "run-c" and r.data[tick.LOCK_KEY]["owner"] == "run-c"


@pytest.mark.parametrize("theirs, reason", [("claimed", "claim_lost"), ("filled", "already_drafted"),
                                            ("withdrawn", "no_reservation")])
def test_a_reservation_this_run_no_longer_holds_is_never_recorded_over(store, tmp_path, theirs, reason):
    """The claim is checked before sequence.record_pending, which checks only
    kind, touch, stage and status: it would fill another run's reservation,
    or overwrite a draft another run already recorded."""
    path = write_snap(tmp_path, snapshot([tch_room()]))
    key = sequence.thread_key("room_tch1")

    def other_run(cur):
        cur = copy.deepcopy(cur)
        if theirs == "claimed":
            cur[tick.CLAIM_KEY] = dict(cur[tick.CLAIM_KEY], token="other-run")
        elif theirs == "filled":
            cur = sequence.record_pending(cur, "touch", 1, "The other run's draft.", NOW, "card-other")
            cur.pop(tick.CLAIM_KEY, None)
        else:
            cur = sequence.clear_pending(cur, NOW, reason="stage_call_booked", retry=True)
        return cur

    class Meddles(FakeLLM):
        def __call__(self, role, system, user, **kw):
            if role == "draft":
                store.mutate(key, other_run)          # the raw store: this run's lease is untouched
            return FakeLLM.__call__(self, role, system, user, **kw)

    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=Meddles(), notify_fn=notify,
                           ghl=FakeGHL())
    assert result["counts"]["drafted"] == 0 and result["lock_lost"] is None
    assert result["dropped"] == [{"room_id": "room_tch1", "kind": "touch", "touch": 1, "reason": reason}]
    t = thread(store, "room_tch1")
    if theirs == "filled":
        assert (t["pending"]["text"], t["pending"]["card_id"]) == ("The other run's draft.", "card-other")
    elif theirs == "claimed":
        assert t["pending"]["text"] is None and t[tick.CLAIM_KEY]["token"] == "other-run"
    else:
        assert t["pending"] is None
    assert not [c for c in notify.calls if c["title"].startswith("Upwork: 1 new draft")]


# ------------------------------------------------------------------ round 3: spend caps from the environment
@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "-1", "1.5", "1e3", "abc", "40.0"])
def test_a_classifier_cap_that_is_not_a_whole_number_falls_back(monkeypatch, raw):
    monkeypatch.setenv(tick.CLASSIFY_CAP_ENV, raw)
    assert tick.run_max_classify() == tick.DEFAULT_MAX_CLASSIFY


@pytest.mark.parametrize("raw, want", [("0", 0), ("12", 12), (" 7 ", 7)])
def test_a_whole_classifier_cap_is_used(monkeypatch, raw, want):
    monkeypatch.setenv(tick.CLASSIFY_CAP_ENV, raw)
    assert tick.run_max_classify() == want


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "-0.5", "abc", "1e400"])
def test_a_run_budget_that_is_not_finite_and_non_negative_falls_back(monkeypatch, raw):
    monkeypatch.setenv(tick.BUDGET_ENV, raw)
    assert tick.run_budget_usd() == tick.DEFAULT_RUN_BUDGET_USD


@pytest.mark.parametrize("raw, want", [("1.00", 1.0), ("0.25", 0.25), ("0", 0.0)])
def test_a_lower_one_off_budget_is_used(monkeypatch, raw, want):
    monkeypatch.setenv(tick.BUDGET_ENV, raw)
    assert tick.run_budget_usd() == want


def test_bad_caps_do_not_crash_a_run(store, tmp_path, monkeypatch):
    monkeypatch.setenv(tick.CLASSIFY_CAP_ENV, "inf")
    monkeypatch.setenv(tick.BUDGET_ENV, "nan")
    result = tch_run(store, tmp_path)
    assert result["status"] == "ok" and result["counts"]["drafted"] == 1
    assert (result["llm"]["budget_usd"], result["llm"]["max_classify"]) == (1.5, 40)


# ------------------------------------------------------------------ round 3: no OS error text in a public push
def test_an_os_error_on_the_snapshot_stays_out_of_the_public_push(store, tmp_path, world):
    snapdir = tmp_path / "snapshot_dir"
    snapdir.mkdir()                                       # opening a directory is an OSError
    notify = FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=snapdir, llm=FakeLLM(), notify_fn=notify,
                           ghl=FakeGHL())
    assert result["status"] == "error" and result["snapshot_error"].startswith("unreadable: [Errno")
    (card,) = notify.calls
    assert "the snapshot is unreadable (OSError)" in card["message"]
    for public in (card["title"], card["message"]):
        assert "Errno" not in public and str(tmp_path) not in public
    assert "[Errno" in card["kw"]["email_message"] and str(snapdir) in card["kw"]["email_message"]
    details = world["logs"][-1][2]
    assert "[Errno" in details["snapshot_error"] and str(snapdir) in details["error"]


def test_public_snapshot_error_keeps_only_the_kind():
    assert tick.public_snapshot_error("unreadable: [Errno 13] Permission denied: '/private/invented/s.json'") \
        == "unreadable (OSError)"
    assert tick.public_snapshot_error("unreadable: Expecting value: line 1 column 1 (char 0)") \
        == "unreadable (ValueError)"
    assert tick.public_snapshot_error("future: generated_at 2026-09-23T00:00:00Z is 5.0 h after this run") \
        == "stamped in the future"
    assert tick.public_snapshot_error("missing") == "missing"


# ------------------------------------------------------------------ round 3: a client left waiting
BWH_DRAFT = ("Yes, a quote can go out the same day: the text fires when the visit is marked done in the field "
             "app, so the homeowner has it before dinner. Does every visit end with a price on the spot?\n"
             "PROPOSES_CALL: no")
LATER = datetime(2026, 9, 29, 13, 30, tzinfo=timezone.utc)   # Tuesday 08:30 CT, a week after NOW


def bwh_room():
    """Birchwood Heating Co (invented): the client asked a question on
    2026-09-15 and was never answered."""
    return room("room_bwh1", "Birchwood Heating Co", "Heat pump quote follow-ups",
                "Birchwood Heating Co wants heat pump quotes followed up by text two days after each site visit.",
                [msg("h1", "freelancer", datetime(2026, 9, 12, 15, tzinfo=timezone.utc),
                     "The Loom shows the quote flow."),
                 msg("h2", "client", datetime(2026, 9, 15, 15, tzinfo=timezone.utc),
                     "question: can the quotes go out the same day as the visit?")])


def fill(store, rid, at, text="A reply the test wrote."):
    def fn(cur):
        p = cur["pending"]
        return sequence.record_pending(cur, p["kind"], p.get("touch"), text, at, "card-%s" % rid)
    store.mutate(sequence.thread_key(rid), fn)


def skipped_once(store):
    """The reply drafted on 2026-09-15 expired unsent on 2026-09-22 and was
    drafted again (sequence.REPLY_REDRAFTS); that one is still unsent."""
    t0 = datetime(2026, 9, 15, 20, tzinfo=timezone.utc)
    sequence.run(store, snapshot([bwh_room()], generated=t0), t0, seed_classify)
    fill(store, "room_bwh1", t0)
    sequence.run(store, snapshot([bwh_room()], generated=NOW), NOW, seed_classify)
    fill(store, "room_bwh1", NOW)


def test_a_client_left_waiting_is_listed_under_needs_you_on_every_run(store, tmp_path, world):
    skipped_once(store)
    path = write_snap(tmp_path, snapshot([bwh_room()], generated=LATER - timedelta(minutes=10)))
    llm, notify = FakeLLM(drafts={"Heat pump quote": BWH_DRAFT}), FakeNotify()
    result = tick.run_tick(LATER, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())

    assert llm.calls == []                                # the second expiry: no third draft
    due = sequence.due_summary(thread(store, "room_bwh1"), LATER)
    assert due["kind"] == "reply_skipped"
    assert result["counts"]["waiting_on_you"] == 1 and result["status"] == "attention"
    # sequence.py's needs_review reply_skipped is this same news: shown once, under Needs you
    assert result["check"] == [] and result["counts"]["needs_review"] == 0
    text = batch_text(result)
    assert "## Check these" not in text
    needs = text.split("## Needs you", 1)[1].split("\n## ", 1)[0]
    assert ("- Birchwood Heating Co | Heat pump quote follow-ups | reply skipped on 2026-09-29; client waiting "
            "since 2026-09-15 | room room_bwh1 | %s" % tick.room_url("room_bwh1")) in needs
    assert "--resume <room_id>" in needs
    assert "reply skipped on 2026-09-29; client waiting since 2026-09-15; status awaiting_lorenzo" in text
    summary = [c for c in notify.calls if c["title"].startswith("Upwork drafts")][0]
    assert "Needs you: 1 client still waiting on a reply that was skipped." in summary["message"]
    assert "Birchwood" not in summary["message"]
    assert world["logs"][-1][2]["waiting_on_you"] == 1

    nxt = LATER + timedelta(days=1)
    path = write_snap(tmp_path, snapshot([bwh_room()], generated=nxt - timedelta(minutes=10)))
    again = tick.run_tick(nxt, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                          ghl=FakeGHL())
    assert again["counts"]["waiting_on_you"] == 1 and "## Needs you" in batch_text(again)

    sequence.resume(store, "room_bwh1", nxt)              # Lorenzo asks for the reply again
    resumed = thread(store, "room_bwh1")
    assert tick.due_text(sequence.due_summary(resumed, nxt), resumed) == "reply due now"


def test_a_reply_cleared_without_retry_leaves_the_client_waiting(store):
    t0 = datetime(2026, 9, 15, 20, tzinfo=timezone.utc)
    sequence.run(store, snapshot([bwh_room()], generated=t0), t0, seed_classify)
    store.mutate(sequence.thread_key("room_bwh1"),
                 lambda cur: sequence.clear_pending(cur, t0 + timedelta(days=1), reason="cleared", retry=False))
    t = thread(store, "room_bwh1")
    due = sequence.due_summary(t, t0 + timedelta(days=2))
    assert tick.reply_skipped(due, t)
    assert tick.due_text(due, t) == "reply skipped on 2026-09-16; client waiting since 2026-09-15"


def test_skip_dates_come_from_the_due_summary_else_the_thread():
    due = {"kind": "reply_skipped", "status": "awaiting_lorenzo", "pending": False, "hold": False,
           "skipped_at": "2026-09-29T13:30:00+00:00", "waiting_since": "2026-09-15T15:00:00Z"}
    assert tick.due_text(due) == "reply skipped on 2026-09-29; client waiting since 2026-09-15"
    assert tick.due_text(dict(due, skipped_at=None, waiting_since=None)) == \
        "reply skipped; the client is still waiting"
    older = {"status": "awaiting_lorenzo", "stage": "new_reply", "pending": None,
             "marks": {"reply_target": "h2", "reply_for": "h2", "last_client_at": "2026-09-15T15:00:00Z"},
             "history": [{"at": "2026-09-21T14:00:00Z", "event": "withdrawn", "reason": "skipped",
                          "kind": "reply"}]}
    no_kind = {"kind": None, "status": "awaiting_lorenzo", "pending": False, "hold": False}
    assert tick.reply_skipped(no_kind, older)
    assert tick.due_text(no_kind, older) == "reply skipped on 2026-09-21; client waiting since 2026-09-15"
    older["marks"]["reply_skipped"] = {"message_id": "h2", "count": 2, "at": "2026-09-22T14:00:00Z"}
    assert tick.reply_skip_dates(older) == ("2026-09-22T14:00:00Z", "2026-09-15T15:00:00Z")
    older["marks"]["reply_skipped"]["message_id"] = "an older message"     # not this reply's skip
    assert tick.reply_skip_dates(older) == ("2026-09-21T14:00:00Z", "2026-09-15T15:00:00Z")


def test_a_reply_that_is_due_is_not_a_skipped_one():
    t = {"status": "awaiting_lorenzo", "stage": "new_reply", "pending": None,
         "marks": {"reply_target": "h2", "reply_for": None, "last_client_at": "2026-09-15T15:00:00Z"}}
    due = {"kind": "reply", "draft_now": True, "status": "awaiting_lorenzo", "pending": False, "hold": False}
    assert not tick.reply_skipped(due, t) and tick.due_text(due, t) == "reply due now"
    held = dict(due, kind="reply_skipped", hold=True)
    assert tick.due_text(held, t).startswith("on hold")


# ------------------------------------------------------------------ round 3: rooms blocked on Upwork
BLOCKED_AT = datetime(2026, 9, 21, 16, tzinfo=timezone.utc)


def blocked_room(blocked=True, blocked_at=BLOCKED_AT):
    """Maple Street Bistro (invented) blocked the room after Lorenzo's last
    message: collect.py's shape (an event message, ``blocked``, ``blocked_at``)."""
    r = room("room_blk1", "Maple Street Bistro", "Reservation reminder texts",
             "Maple Street Bistro wants reservation reminder texts sent the morning of each booking.",
             [msg("m1", "client", datetime(2026, 9, 14, 15, tzinfo=timezone.utc), "positive: send me the details"),
              msg("m2", "freelancer", datetime(2026, 9, 15, 15, tzinfo=timezone.utc), "Here is the plan.")])
    if blocked:
        r["messages"].append({"id": "m3", "side": "unknown", "at": iso(blocked_at), "event": True,
                              "event_name": "blocked", "text": "System event: blocked. View this conversation "
                                                               "on upwork.com for full context."})
    r["blocked"], r["blocked_at"] = bool(blocked), iso(blocked_at) if blocked else None
    return r


def blocked_snap(rooms, at=NOW):
    s = snapshot(rooms, generated=at - timedelta(minutes=10))
    s["blocked_rooms"] = sorted(r["room_id"] for r in rooms if r.get("blocked"))
    return s


def test_a_blocked_room_is_listed_once_and_never_drafted(store, tmp_path, world):
    path = write_snap(tmp_path, blocked_snap([blocked_room(), tch_room()]))
    llm, notify = FakeLLM(), FakeNotify()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=notify, ghl=FakeGHL())

    assert llm.drafts_called() == ["draft"]               # Orchard Lane only
    assert thread(store, "room_blk1") is None             # sequence.py never enrols a blocked room
    assert (result["counts"]["blocked"], result["counts"]["blocked_new"]) == (1, 1)
    assert result["status"] == "attention"
    text = batch_text(result)
    section = text.split("## Blocked on Upwork (no drafts)", 1)[1].split("\n## ", 1)[0]
    assert "- Maple Street Bistro | Reservation reminder texts | blocked 2026-09-21 | room room_blk1" in section
    summary = [c for c in notify.calls if c["title"].startswith("Upwork drafts")][0]
    assert "1 room blocked on Upwork (no drafts)." in summary["message"]
    assert "Maple" not in summary["message"] and "Reservation" not in summary["message"]
    assert ("Blocked on Upwork (no drafts): Maple Street Bistro | Reservation reminder texts | room room_blk1, "
            "blocked 2026-09-21.") in summary["kw"]["email_message"]
    assert world["logs"][-1][2]["blocked_new"] == 1
    assert store.get(tick.TICK_KEY)[tick.BLOCKED_LISTED]["room_blk1"]["blocked_at"] == iso(BLOCKED_AT)

    # the next morning it is still blocked: not listed again (--status keeps showing it)
    nxt = NOW + timedelta(days=1)
    path = write_snap(tmp_path, blocked_snap([blocked_room(), tch_room()], at=nxt))
    again = tick.run_tick(nxt, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                          ghl=FakeGHL())
    assert (again["counts"]["blocked"], again["counts"]["blocked_new"]) == (1, 0)
    assert "Blocked on Upwork" not in batch_text(again)
    assert "blocked on Upwork" not in tick.summary_text(again)
    assert "blocked on Upwork" not in tick.summary_text(again, public=True)


def test_a_thread_whose_room_gets_blocked_is_closed_and_listed_once(store, tmp_path, world):
    at = datetime(2026, 9, 16, 13, 30, tzinfo=timezone.utc)
    sequence.run(store, snapshot([blocked_room(blocked=False)], generated=at), at, seed_classify)
    assert thread(store, "room_blk1")["status"] == "active"      # enrolled; T1 would be due by NOW
    path = write_snap(tmp_path, blocked_snap([blocked_room()]))
    llm = FakeLLM()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert llm.calls == []
    t = thread(store, "room_blk1")
    assert (t["status"], t["stop_reason"], t["stage"], t["pending"]) == ("closed", "room_blocked", "lost", None)
    # sequence.py's needs_review room_blocked is this same news: listed once, not under Check these
    assert result["check"] == [] and result["counts"]["needs_review"] == 0
    text = batch_text(result)
    assert "## Check these" not in text
    assert "- Maple Street Bistro | Reservation reminder texts | blocked 2026-09-21 | room room_blk1" in text
    assert tick.blocked_since(t) == t["marks"]["blocked_at"]
    assert tick.due_text(sequence.due_summary(t, NOW), t, tick.blocked_since(t)) == \
        "blocked on Upwork since 2026-09-21"


def test_blocked_since_is_the_rooms_block_time_and_closed_says_how_to_reopen():
    t = {"status": "closed", "stop_reason": "room_blocked", "stage": "lost", "stage_set_by": "engine",
         "marks": {"blocked_at": "2026-09-21T16:00:00+00:00"},
         "history": [{"at": "2026-09-22T13:30:00+00:00", "event": "room_blocked",
                      "blocked_at": "2026-09-21T16:00:00+00:00"}]}
    assert tick.blocked_since(t) == "2026-09-21T16:00:00+00:00"           # not the run time it was seen
    assert tick.blocked_since(t, {"room_id": "room_blk1", "not_in_snapshot": True}) == "2026-09-21T16:00:00+00:00"
    assert tick.blocked_since(t, dict(blocked_room(), blocked_at=None)) == "2026-09-21T16:00:00+00:00"
    assert tick.blocked_since(t, blocked_room(blocked_at=datetime(2026, 9, 20, 9, tzinfo=timezone.utc))) \
        == "2026-09-20T09:00:00Z"                                          # the pull's own time wins
    t_old = dict(t, marks={}, history=[{"at": "2026-09-22T13:30:00+00:00", "event": "room_blocked",
                                        "blocked_at": "2026-09-20T10:00:00Z"}])
    assert tick.blocked_since(t_old) == "2026-09-20T10:00:00Z"
    closed_due = {"status": "closed", "kind": None, "pending": False, "hold": False}
    assert tick.due_text(closed_due, t, tick.blocked_since(t)) == "blocked on Upwork since 2026-09-21"
    open_again = blocked_room(blocked=False)
    assert tick.blocked_since(t, open_again) is None
    assert tick.due_text(closed_due, t, None) == tick.CLOSED_TEXT == \
        "closed (blocked on Upwork); --resume or a drafting --stage reopens it"
    assert tick.blocked_since({"status": "active", "marks": {}}) is None


def test_a_room_without_the_blocked_flag_is_not_blocked():
    r = tch_room()                                        # built without the key, like an older snapshot
    assert "blocked" not in r
    assert tick.blocked_rooms(snapshot([r])) == [] and tick.blocked_since(None, r) is None
    closed = dict(r, blocked=False, blocked_at=None)
    assert tick.blocked_rooms(snapshot([closed])) == [] and tick.blocked_since(None, closed) is None
    listed = dict(snapshot([r]), blocked_rooms=["room_tch1"])
    assert [b["room_id"] for b in tick.blocked_rooms(listed)] == ["room_tch1"]


def test_an_unblocked_room_is_forgotten_and_a_new_block_is_listed_again(store, tmp_path):
    def run_at(at, blk):
        path = write_snap(tmp_path, blocked_snap([blk], at=at))
        return tick.run_tick(at, "run", store=store, snapshot_path=path, llm=FakeLLM(), notify_fn=FakeNotify(),
                             ghl=FakeGHL())

    assert run_at(NOW, blocked_room())["counts"]["blocked_new"] == 1
    assert run_at(NOW + timedelta(days=1), blocked_room(blocked=False))["counts"]["blocked"] == 0
    assert "room_blk1" not in store.get(tick.TICK_KEY)[tick.BLOCKED_LISTED]
    reblocked = blocked_room(blocked_at=datetime(2026, 9, 23, 18, tzinfo=timezone.utc))
    again = run_at(NOW + timedelta(days=2), reblocked)
    assert again["counts"]["blocked_new"] == 1
    assert "blocked 2026-09-23 | room room_blk1" in batch_text(again)


def test_fold_reviews_keeps_a_line_whose_room_is_not_listed_this_run():
    result = tick._new_result(NOW, "run")
    result["check"] = [{"room_id": "a", "reason": "room_blocked", "detail": {}},
                       {"room_id": "b", "reason": "room_blocked", "detail": {}},
                       {"room_id": "c", "reason": "reply_skipped", "detail": {}},
                       {"room_id": "d", "reason": "low_confidence", "detail": {}}]
    result["counts"]["needs_review"] = 4
    tick._fold_reviews(result, waiting={"c"}, blocked_new={"a"})
    assert [(i["room_id"], i["reason"]) for i in result["check"]] == [("b", "room_blocked"),
                                                                      ("d", "low_confidence")]
    assert result["counts"]["needs_review"] == 2


# ------------------------------------------------------------------ round 4: no store lock around a model call
class FakeAnthropic(object):
    """Stands in for anthropic.Anthropic under the REAL shared.llm.complete
    (billed mode). Nothing leaves the process: ``messages.create`` answers a
    classify call (json_mode) with the label FakeLLM reads from the client
    text, and a draft call with the DRAFTS text."""

    DRAFTS = dict(DRAFTS, **{"Load board scraper": (
        "On the Cobalt Freight quote sheet: I would read each load board posting into one row per lane, so "
        "the quotes compare side by side. Which load boards does the team check first?\nPROPOSES_CALL: no")})

    def __init__(self):
        self.roles = []
        self.messages = self

    def create(self, model, max_tokens, system, messages, thinking=None, output_config=None):
        role = "classify" if "Respond with a single JSON object" in system else "draft"
        self.roles.append(role)
        out = FakeLLM(drafts=FakeAnthropic.DRAFTS)(role, system, messages[0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=out if isinstance(out, str)
                                                        else json.dumps(out))],
                               usage=SimpleNamespace(input_tokens=400, output_tokens=60), stop_reason="end_turn")


@pytest.fixture
def billed(tmp_path, monkeypatch):
    """The REAL shared.llm.complete in billed mode behind FakeAnthropic. It
    keeps its spend counter in get_store(), the JsonFileStore at STORE_PATH,
    which is also the tick's store when run_tick gets none: one file, one
    flock, as on the laptop."""
    assert (REAL_COMPLETE.__module__, REAL_COMPLETE.__name__) == ("shared.llm", "complete")
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("LLM_LEDGER_PATH", str(tmp_path / "llm_ledger.csv"))
    monkeypatch.setenv("LLM_FAKE", "0")
    monkeypatch.setattr(shared_llm_mod, "BUDGET_PATH", tmp_path / "no_budget_file.json")   # the $10 default
    monkeypatch.setattr(shared_llm_mod, "complete", REAL_COMPLETE)
    for key, value in (("process", 0.0), ("alerted", False), ("warned", False)):
        monkeypatch.setitem(shared_llm_mod._SPEND, key, value)
    # a lock of its own: a thread a regression leaves hanging holds this one,
    # not the one every later test in the session takes
    monkeypatch.setattr(shared_llm_mod, "_SPEND_LOCK", threading.RLock())
    client = FakeAnthropic()
    monkeypatch.setitem(shared_llm_mod._CLIENT, "client", client)
    monkeypatch.setitem(shared_llm_mod._CLIENT, "warned", True)
    return client


TICK_TIMEOUT_S = 30


def _within(seconds, fn):
    """fn() on a daemon thread, with a hard timeout. A hang (this process
    taking the store file's flock a second time) dumps every thread's stack
    and fails the test instead of hanging the session; faulthandler's own
    timer is the backstop should the join itself not return."""
    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the test's thread
            box["error"] = exc

    worker = threading.Thread(target=target, name="run_tick under test", daemon=True)
    faulthandler.dump_traceback_later(seconds + 30, exit=True)
    try:
        worker.start()
        worker.join(seconds)
        if worker.is_alive():
            faulthandler.dump_traceback(all_threads=True)
            pytest.fail("run_tick did not finish within %d s: the store's lock was taken again while a "
                        "store.mutate held it (every thread's stack is above)" % seconds)
    finally:
        faulthandler.cancel_dump_traceback_later()
    if "error" in box:
        raise box["error"]
    return box["value"]


def test_a_real_model_run_on_the_json_file_store_does_not_deadlock(tmp_path, billed):
    """Regression (U2 round 4). The classifier ran inside the thread's
    store.mutate, and shared.llm.complete reserves its spend in the same
    JsonFileStore file, so the process took the file's flock a second time
    and waited forever. Real pieces here: a --run on get_store(), the real
    complete() (only the Anthropic client is fake), a room whose client wrote
    last, and a hard timeout."""
    path = write_snap(tmp_path, snapshot([rep_room()]))
    result = _within(TICK_TIMEOUT_S, lambda: tick.run_tick(NOW, "run", snapshot_path=path, notify_fn=FakeNotify(),
                                                          ghl=FakeGHL()))
    assert billed.roles == ["classify", "draft"]
    assert result["errors"] == [] and result["lock_lost"] is None and result["status"] in ("ok", "attention")
    assert (result["counts"]["replies"], result["counts"]["drafted"]) == (1, 1)
    real = get_store()
    assert isinstance(real, JsonFileStore) and real.path == tmp_path / "store.json"
    assert real.get(shared_llm_mod.SPEND_KEY) > 0              # complete() charged the tick's own store file
    t = thread(real, "room_rep1")
    assert t["status"] == sequence.AWAITING and t["pending"]["kind"] == "reply" and t["pending"]["text"]


class MutateGuard(Store):
    """Wraps a JsonFileStore. ANY store call (any method, any key) made while
    one of its mutates is open is recorded and refused before it reaches the
    file, where it would wait on the file's own flock forever."""

    def __init__(self, inner):
        self.inner = inner
        self.open = []      # keys of the mutates open now
        self.nested = []    # (call, key, the open mutate's key) for every refused call
        self.mutated = []   # every key mutated, in order

    def _outside(self, call, key):
        if self.open:
            self.nested.append((call, key, self.open[-1]))
            raise AssertionError("store.%s(%r) while store.mutate(%r) is open" % (call, key, self.open[-1]))

    def get(self, key, default=None):
        self._outside("get", key)
        return self.inner.get(key, default)

    def keys(self, prefix=""):
        self._outside("keys", prefix)
        return self.inner.keys(prefix)

    def set(self, key, value):
        self._outside("set", key)
        self.inner.set(key, value)

    def delete(self, key):
        self._outside("delete", key)
        self.inner.delete(key)

    def append(self, key, item):
        self._outside("append", key)
        return self.inner.append(key, item)

    def set_if_absent(self, key, value):
        self._outside("set_if_absent", key)
        return self.inner.set_if_absent(key, value)

    def add_once(self, key, item):
        self._outside("add_once", key)
        return self.inner.add_once(key, item)

    def compare_and_set(self, key, expected, value):
        self._outside("compare_and_set", key)
        return self.inner.compare_and_set(key, expected, value)

    def mutate(self, key, fn, default=None):
        self._outside("mutate", key)
        self.mutated.append(key)

        def wrapped(cur):
            self.open.append(key)
            try:
                return fn(cur)
            finally:
                self.open.pop()
        return self.inner.mutate(key, wrapped, default)


def _guarded(monkeypatch, tmp_path):
    """One MutateGuard over the store file, returned by every get_store() (the
    tick's and shared.llm's spend counter), and shared.llm.complete refused
    (and recorded) while one of its mutates is open."""
    guard = MutateGuard(JsonFileStore(tmp_path / "store.json"))
    monkeypatch.setattr(store_mod, "get_store", lambda force_new=False: guard)
    monkeypatch.setattr(tick, "get_store", lambda force_new=False: guard)
    inside = []

    def complete(role, system, user, **kw):
        if guard.open:
            inside.append((role, guard.open[-1]))
            raise AssertionError("shared.llm.complete(%s) while store.mutate(%r) is open" % (role, guard.open[-1]))
        return REAL_COMPLETE(role, system, user, **kw)

    monkeypatch.setattr(shared_llm_mod, "complete", complete)
    return guard, inside


def moved_room(rid, client, title):
    return room(rid, client, title, "%s wants %s." % (client, title.lower()),
                [msg(rid + "_c", "client", datetime(2026, 9, 8, 15, tzinfo=timezone.utc), "positive: yes"),
                 msg(rid + "_f", "freelancer", datetime(2026, 9, 9, 15, tzinfo=timezone.utc), "Great, here it is.")])


def test_no_store_call_and_no_model_call_while_a_store_mutate_is_open(tmp_path, monkeypatch, billed, world,
                                                                    upwork_pipeline):
    """The generic guard. Every store the run reaches is one MutateGuard, and
    shared.llm.complete is watched too. Two runs over rooms that reach every
    store.mutate the tick and sequence.py make: the meta record, a revivable
    listing, enrolment, a classified reply, the draft claims and records, a
    draft released over the run budget, a check-in, a contract won, a thread
    missing from the pull, a thread whose room is now blocked, the GHL
    read-back and mirror, the titles, the cards, the summary, the blocked
    list, the lease and shared.llm's spend counter. Not one store call and not
    one model call happens while a mutate is open."""
    guard, inside = _guarded(monkeypatch, tmp_path)
    monkeypatch.setattr(tick, "call_cost", lambda role, system, user, max_tokens, **kw: 0.5)
    monkeypatch.setenv(tick.BUDGET_ENV, "1.7")        # classify + 2 drafts fit; the third is released
    at = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    gone = moved_room("room_gone1", "Fern Gully Florist", "Wedding order intake")
    sequence.run(guard, snapshot([chk_room(), bkd_room(), blocked_room(blocked=False),
                                  moved_room("room_con1", "Quarry Hill Movers", "Moving quote follow-ups"), gone],
                                 generated=at), at, seed_classify)
    sequence.set_stage(guard, "room_bkd1", "call_booked", at, by="lorenzo")
    at2 = datetime(2026, 9, 19, 16, tzinfo=timezone.utc)
    sequence.run(guard, snapshot([tch_room(), gone], generated=at2), at2, seed_classify)
    _with_real_ghl_ids(guard, "room_tch1")
    old = room("room_old1", "Juniper Kiln Studio", "Kiln firing schedule reminders",
               "Juniper Kiln Studio wants kiln firing reminders.",
               [msg("o1", "client", datetime(2026, 7, 1, 15, tzinfo=timezone.utc), "positive: maybe later")])
    snap = snapshot([rep_room(), tch_room(), wai_room(), chk_room(), bkd_room(), blocked_room(), old],
                    contracted=[{"room_id": "room_con1", "contract_id": "ct_invented", "status": "ACTIVE"}])
    snap["blocked_rooms"] = ["room_blk1"]
    path = write_snap(tmp_path, snap)
    ghl = FakeGHL(stage_id=upwork_pipeline["stages"]["proposal_sent"])
    guard.mutated[:] = []

    first = tick.run_tick(NOW, "run", snapshot_path=path, notify_fn=FakeNotify(), ghl=ghl)
    second = tick.run_tick(NOW + timedelta(days=1), "run", snapshot_path=path, notify_fn=FakeNotify(), ghl=ghl)

    assert guard.nested == [] and inside == []
    assert first["errors"] == [] and second["errors"] == []
    assert billed.roles.count("classify") == 1 and billed.roles.count("draft") >= 2
    assert first["counts"]["budget_deferred"] >= 1 and first["counts"]["won"] == 1
    assert first["counts"]["revivable"] == 1 and first["counts"]["blocked_new"] == 1
    assert thread(guard, "room_tch1")["stage_set_by"] == "ghl"             # the read-back was applied
    assert any(c["reason"] == "not_in_pull" for c in first["check"])
    mutated = set(guard.mutated)
    assert {sequence.META_KEY, tick.LOCK_KEY, tick.TICK_KEY, shared_llm_mod.SPEND_KEY} <= mutated
    assert {sequence.thread_key(r) for r in ("room_rep1", "room_tch1", "room_chk1", "room_con1", "room_gone1",
                                             "room_blk1")} <= mutated
    assert guard.get(shared_llm_mod.SPEND_KEY) > 0


def test_the_guard_catches_a_model_call_inside_a_thread_mutate(tmp_path, monkeypatch, billed):
    """The guard is not vacuous. A model call made inside a thread mutate, the
    round-3 shape, is caught at shared.llm's own spend-counter write, even
    though complete() swallows that store error and carries on; and a call to
    shared.llm.complete there is refused outright."""
    guard, inside = _guarded(monkeypatch, tmp_path)
    user = "=== BEGIN CLIENT_MESSAGE ===\nquestion: what does it cost?\n=== END CLIENT_MESSAGE ==="

    def classify_inside(cur):
        REAL_COMPLETE("classify", "Label the message.", user, max_tokens=60, json_mode=True)
        return cur

    guard.mutate(sequence.thread_key("room_x"), classify_inside)
    assert ("mutate", shared_llm_mod.SPEND_KEY, sequence.thread_key("room_x")) in guard.nested
    with pytest.raises(AssertionError):
        guard.mutate(sequence.thread_key("room_y"), lambda cur: shared_llm_mod.complete("draft", "s", "u") and cur)
    assert inside == [("draft", sequence.thread_key("room_y"))]


def test_inside_an_open_run_mutate_a_store_or_model_call_raises(store, world):
    """The runtime guard behind the audit. On a --run, a store read or write, a
    renewal, a classifier call or a model call made while one of the run's
    store.mutate calls is open raises NestedStoreCall. The file's flock is
    really held there, so each of them would otherwise hang."""
    lease = tick.RunLease(store, world["clock"])
    assert lease.acquire()["lease"]
    leased = tick.LeasedStore(store, lease)
    llm = FakeLLM()
    meter = tick.Meter(llm, budget=5, max_classify=5, lease=lease)
    classify = tick._classify_live(meter)
    attempts = [lambda: leased.get(tick.TICK_KEY), lambda: leased.keys(sequence.PREFIX),
                lambda: leased.set(tick.TICK_KEY, {}), lambda: leased.delete(tick.TICK_KEY),
                lambda: leased.mutate(tick.TICK_KEY, lambda cur: cur), lambda: lease.renew("a test"),
                lambda: classify("question: does it sync?", rep_room()), lambda: meter("draft", "system", "user")]
    for attempt in attempts:
        def fn(cur, attempt=attempt):
            attempt()
            return cur
        with pytest.raises(tick.NestedStoreCall):
            leased.mutate(sequence.thread_key("room_x"), fn)
    assert llm.calls == [] and meter.calls == {} and lease.depth == 0 and lease.lost is None
    assert leased.get(sequence.thread_key("room_x")) is None               # nothing was written
    assert classify("question: does it sync?", rep_room())["label"] == "question"    # outside, it all works
    assert llm.calls == ["classify"]


def test_each_classifier_call_renews_the_lease_first(store, tmp_path, monkeypatch):
    """A low-confidence read escalates: two model calls for one message, each
    right after its own renewal (round 3 renewed once, before the mutate the
    whole classification ran in)."""
    events = []
    real_renew = tick.renew_lock

    def renew(store_, wall, token):
        events.append("renew")
        return real_renew(store_, wall, token)

    class Unsure(FakeLLM):
        def __call__(self, role, system, user, **kw):
            events.append("model " + role)
            out = FakeLLM.__call__(self, role, system, user, **kw)
            return dict(out, confidence=0.5) if role == "classify" else out

    monkeypatch.setattr(tick, "renew_lock", renew)
    path = write_snap(tmp_path, snapshot([rep_room()]))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=Unsure(), notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    i = events.index("model classify")
    assert events[i - 1:i + 3] == ["renew", "model classify", "renew", "model escalate"]
    assert result["errors"] == [] and result["counts"]["replies"] == 1
    assert thread(store, "room_rep1")["status"] == sequence.AWAITING


def test_a_lease_lost_at_the_classifier_renewal_advances_nothing(store, tmp_path, monkeypatch, world):
    """The renewal before the classify call finds the lease taken over.
    classify.py turns that error into a fallback neutral label; the tick reads
    the loss back right after, so the label is never used: no model call, no
    thread written, and the run ends lock_lost."""
    real_renew = tick.renew_lock
    calls = []

    def renew(store_, wall, token):
        calls.append(wall)
        if len(calls) >= 2:           # 1: the meta record, 2: the renewal before the classify call
            return None, a_lease("intruder", wall)
        return real_renew(store_, wall, token)

    monkeypatch.setattr(tick, "renew_lock", renew)
    llm = FakeLLM()
    path = write_snap(tmp_path, snapshot([rep_room()]))
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert llm.calls == [] and thread(store, "room_rep1") is None
    assert result["status"] == "lock_lost" and result["lock_lost"]["reason"] == "taken_over"
    assert result["lock_lost"]["during"] == "a model call (classify)"
    assert (result["counts"]["lock_skipped"], result["counts"]["replies"]) == (1, 0)


class MeddlingStore(JsonFileStore):
    """Another writer takes the thread's lock between sequence.run's unlocked
    read and its write, once: ``meddle`` runs just before that mutate."""

    def __init__(self, path, key):
        JsonFileStore.__init__(self, path)
        self.key, self.meddle = key, None

    def mutate(self, key, fn, default=None):
        if key == self.key and self.meddle is not None:
            meddle, self.meddle = self.meddle, None
            JsonFileStore.mutate(self, key, meddle, default)
        return JsonFileStore.mutate(self, key, fn, default)


def test_a_room_deferred_by_the_sequence_is_noted_and_not_drafted(tmp_path, world):
    """Juniper Bakery's thread holds a T1 reservation a crashed run never
    filled, and the client's question is new. Another writer marks the
    question read between this run's classification and its write: the room
    is deferred, counted, noted without its id (Job_Log has it), and not even
    the old reservation is drafted. The next run drafts it."""
    store = MeddlingStore(tmp_path / "store.json", sequence.thread_key("room_rep1"))
    early = datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
    before = rep_room()
    before["messages"] = before["messages"][:2]
    before["last_side"], before["last_message_at"] = "freelancer", before["messages"][-1]["at"]
    sequence.run(store, snapshot([before], generated=early), early, seed_classify)
    assert thread(store, "room_rep1")["pending"] == {"kind": "touch", "touch": 1, "issued_at": iso(early),
                                                      "text": None, "card_id": None, "resurfaced_at": None}

    def mark_read(cur):
        cur = copy.deepcopy(cur)
        cur["last_seen_message_id"] = "r3"
        cur["marks"]["last_seen_at"] = "2026-09-21T20:00:00Z"
        return cur

    store.meddle = mark_read
    path = write_snap(tmp_path, snapshot([rep_room()]))
    llm = FakeLLM()
    result = tick.run_tick(NOW, "run", store=store, snapshot_path=path, llm=llm, notify_fn=FakeNotify(),
                           ghl=FakeGHL())
    assert llm.calls == ["classify"]                            # the unlocked pass; no draft for this room
    assert thread(store, "room_rep1")["pending"]["text"] is None            # the old reservation, untouched
    assert result["counts"]["room_deferred"] == 1 and result["errors"] == []
    note = "1 room changed while this run classified it, so it is left for the next run"
    assert note in result["notes"] and "room_rep1" not in tick.summary_text(result, public=True)
    assert "Note: %s." % note in batch_text(result)
    details = world["logs"][-1][2]
    assert details["room_deferred"] == 1
    assert [(d["room_id"], d["reason"]) for d in details["deferred_rooms"]] == [("room_rep1", "message_ids_changed")]

    later = tick.run_tick(NOW + timedelta(minutes=5), "run", store=store, snapshot_path=path, llm=FakeLLM(),
                          notify_fn=FakeNotify(), ghl=FakeGHL())
    assert later["counts"]["room_deferred"] == 0 and later["counts"]["drafted"] == 1


@pytest.mark.parametrize("raw, want", [("10", 10.0), ("10.01", 10.0), ("25", 10.0), ("1e3", 10.0), ("9.99", 9.99)])
def test_a_run_budget_above_ten_dollars_is_clamped_to_ten(monkeypatch, raw, want):
    monkeypatch.setenv(tick.BUDGET_ENV, raw)
    assert tick.MAX_RUN_BUDGET_USD == 10.0
    assert tick.run_budget_usd() == want
