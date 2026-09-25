"""Lorenzo's own replies kept as examples (reply_examples, 2026-09-25).

* The day-0 thread check (cadence.detect_manual_first_reply) keeps his first
  reply to a lead as an example, in the engine store, once per email id.
* A reply the engine sent is never one: the check does not run for a lead
  with an engine reply recorded, and the seed skips a row the engine sent.
* jobs/seed_reply_examples.py finds his replies since the start date with
  GET /emails reads, prints them by default and writes only with --write.
* Nothing in the send path reads the examples.

Shadow only, every client a fake, every clock fixed, every lead fictional
apart from the recorded September manual list.
"""
import ast
import json
import os
import re
from datetime import timedelta
from pathlib import Path

import pytest

from shared import settings
from shared.store import JsonFileStore

from jobs import seed_reply_examples as seed
from services.reply_engine import cadence
from services.reply_engine import reply_examples as RX
from services.reply_engine.tests.test_day0_detection import (  # noqa: F401 - env is a fixture
    CAMPAIGN, EACCOUNT, LEAD, SENT_AT, THREAD, TICK, ThreadInstantly, _row, _seed, env)

FIXTURES = Path(__file__).parent / "fixtures"
MANUAL = json.loads((FIXTURES / "instantly_manual_sent_2026-09.json").read_text(encoding="utf-8"))
BASE = Path(__file__).resolve().parents[3]

HIS_TEXT = ("Hey Jordan, happy to walk you through it. Does Monday at 1pm or Tuesday at 2pm work?\n\n"
            "Lorenzo\n\nOn Fri, Jan 11, 2030 at 2:00 PM Jordan wrote:\n> Sounds good, tell me more.")


def _his_row(email_id="out-1", when=SENT_AT, text=HIS_TEXT):
    return dict(_row(email_id, when), body={"text": text})


# ============================================== capture on the day-0 thread check
def test_his_first_reply_found_in_the_thread_is_kept_as_an_example(env):
    store = env["store"]
    state, card = _seed(store)
    inst = ThreadInstantly([_his_row()])
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)
    assert res["action"] == "ladder_started" and res["example"] == "recorded"

    ex = store.get(RX.key_for("out-1"))
    assert ex["email_id"] == "out-1" and ex["date"] == SENT_AT.isoformat()
    assert ex["lead_email"] == LEAD and ex["thread_id"] == THREAD and ex["campaign_id"] == CAMPAIGN
    assert ex["campaign_key"] == "cleaning_reactivation" and ex["offer"] == "reactivation"
    assert ex["niche"] == "cleaning" and ex["eaccount"] == EACCOUNT
    assert ex["category"] == "positive_interested"            # how the engine classified the lead's message
    assert ex["lead_message"] == "Sounds good, tell me more." and ex["lead_message_id"] == "in-1"
    # his words, the quoted thread under them cut
    assert ex["reply"].startswith("Hey Jordan, happy to walk you through it.") and "> Sounds good" not in ex["reply"]
    assert ex["sent_by"] == "lorenzo" and ex["source"] == "thread"
    assert RX.recent(store=store) == [ex]
    # one read of the thread, no extra read for the text (the row carried it)
    assert len(inst.reads) == 1 and inst.sent == []


def test_a_row_without_its_text_is_read_once_by_id(env):
    """The recorded manual list has an empty text on every row we sent; the
    capture then reads GET /emails/{id} (read-only) for his words."""
    store = env["store"]
    state, card = _seed(store)
    inst = ThreadInstantly([_row("out-1", SENT_AT)])
    got = []

    def get_email(email_id):
        got.append(email_id)
        return {"id": email_id, "body": {"text": "Hey Jordan, Monday at 1pm works on my side."}}

    inst.get_email = get_email
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)
    assert res["example"] == "recorded" and got == ["out-1"]
    assert store.get(RX.key_for("out-1"))["reply"] == "Hey Jordan, Monday at 1pm works on my side."


def test_no_example_when_the_engine_sent_the_reply(env):
    """An engine reply is recorded on the lead (reply_sent): the thread check
    does not run, so an outbound row in the thread (the engine's own send)
    is never kept as his."""
    store = env["store"]
    state, card = _seed(store)
    row = cadence.state_from_dict(store.get(state.key))
    row.history.append({"at": SENT_AT.isoformat(), "event": "reply_sent", "approval": card.token.split(".", 1)[0],
                        "sent_at": SENT_AT.isoformat()})
    store.set(state.key, cadence.state_to_dict(row))
    inst = ThreadInstantly([_his_row()])
    res = cadence.detect_manual_first_reply(row, TICK, inst, store)
    assert res["action"] == "not_candidate" and res["reason"] == "reply_recorded"
    assert store.keys(RX.PREFIX) == [] and inst.reads == []


def test_no_example_on_a_dry_run_or_a_campaign_step(env):
    store = env["store"]
    state, card = _seed(store)
    res = cadence.detect_manual_first_reply(state, TICK, ThreadInstantly([_his_row()]), store, dry_run=True)
    assert res["action"] == "ladder_would_start" and store.keys(RX.PREFIX) == []
    # a campaign step from the inbox (ue_type 1) is not his reply
    step = dict(_his_row("step-2"), ue_type=1)
    res = cadence.detect_manual_first_reply(state, TICK, ThreadInstantly([step]), store)
    assert res["action"] == "no_reply_found" and store.keys(RX.PREFIX) == []


def test_a_failing_capture_never_costs_the_tick_its_work(env, monkeypatch):
    store = env["store"]
    state, card = _seed(store)

    def boom(*a, **k):
        raise RuntimeError("store down")

    monkeypatch.setattr(RX, "record", boom)
    res = cadence.detect_manual_first_reply(state, TICK, ThreadInstantly([_his_row()]), store)
    assert res["action"] == "ladder_started" and res["example"] == "failed"
    assert cadence.is_armed(cadence.state_from_dict(store.get(state.key)))


# ============================================================= dedupe and read
def test_the_same_email_is_kept_once(env):
    store = env["store"]
    ex = RX.build(email_id="e-1", sent_at=SENT_AT, reply_text="Monday works.", lead_email=LEAD,
                  campaign_id=CAMPAIGN, lead_message="Tell me more", category="positive_interested", now=TICK)
    assert RX.record(store, ex) is True
    assert RX.record(store, dict(ex, reply="something else")) is False
    assert store.get(RX.key_for("e-1"))["reply"] == "Monday works." and len(store.keys(RX.PREFIX)) == 1
    # the tick's capture of an email already kept is a duplicate, and reads nothing
    state, card = _seed(store)
    inst = ThreadInstantly([_his_row("e-1")])
    res = cadence.detect_manual_first_reply(state, TICK, inst, store)
    assert res["example"] == "duplicate" and len(store.keys(RX.PREFIX)) == 1


def test_recent_is_newest_first_filtered_by_category_and_capped(env):
    store = env["store"]
    for i, cat in enumerate(["positive_interested", "neutral_question", "positive_interested",
                             "positive_interested"]):
        RX.record(store, RX.build(email_id="e-%d" % i, sent_at=SENT_AT + timedelta(days=i), reply_text="r%d" % i,
                                  lead_email=LEAD, category=cat, now=TICK))
    assert [e["email_id"] for e in RX.recent(store=store)] == ["e-3", "e-2", "e-1", "e-0"]
    assert [e["email_id"] for e in RX.recent("positive_interested", n=2, store=store)] == ["e-3", "e-2"]
    assert [e["email_id"] for e in RX.recent("neutral_question", store=store)] == ["e-1"]
    assert RX.recent("not_a_label", store=store) == []


def test_an_example_needs_his_email_id_and_his_words():
    with pytest.raises(ValueError):
        RX.build(email_id=None, sent_at=SENT_AT, reply_text="x", lead_email=LEAD)
    with pytest.raises(ValueError):
        RX.build(email_id="e", sent_at=SENT_AT, reply_text="  ", lead_email=LEAD)


# Rule: examples may shape a draft (a future decide() prompt); auto-send
# still needs an exact approved-template match. So no module of the send or
# auto-send path may reference the examples, by module name or by key.
DENY = ["services/reply_engine/template_gate.py", "services/reply_engine/template_approvals.py",
        "services/reply_engine/approval.py", "services/reply_engine/thread_reply.py", "shared/instantly.py"]
ALLOW = {
    "services/reply_engine/cadence.py",      # capture (detect_manual_first_reply) and keep_alive (tick)
    "jobs/seed_reply_examples.py",           # the seed and the cutover copy
    "changesets/deploy/cutover.py",          # copied examples are not live activity
    # reserved: the planned decide() module (Opus 5.5) that reads recent()
    # into its prompt goes here when it is built; it drafts, it never sends.
}


def _references(path):
    return re.search(r"reply_examples|reply_example:", path.read_text(encoding="utf-8")) is not None


def test_no_send_or_auto_send_module_references_the_examples():
    for rel in DENY:
        assert not _references(BASE / rel), "%s must never read the reply examples" % rel


def test_only_the_allowed_modules_import_the_examples():
    importers = set()
    for root in ("services", "jobs", "shared", "changesets"):
        for path in sorted((BASE / root).rglob("*.py")):
            if "tests" in path.parts or path.name == "reply_examples.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + ["%s.%s" % (node.module, a.name) for a in node.names]
                elif isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                if any(n.endswith("reply_examples") for n in names):
                    importers.add(str(path.relative_to(BASE)))
                    break
    assert importers <= ALLOW, "not on the allow-list: %s" % sorted(importers - ALLOW)
    assert not importers & set(DENY)


# ================================================================== the seed job
class ManualList(object):
    """GET /emails?email_type=manual over the recorded September list (newest
    first, one page) and GET /emails/{id}; anything else fails the test."""

    def __init__(self, rows, texts=None):
        self.rows = list(rows)
        self.texts = dict(texts or {})
        self.reads = []

    def list_emails(self, **params):
        assert params.get("email_type") == "manual"
        self.reads.append(("list", params))
        return {"items": list(self.rows), "next_starting_after": None}

    def get_email(self, email_id):
        self.reads.append(("get", email_id))
        return {"id": email_id, "body": {"text": self.texts.get(email_id, "Sure, does Thursday at 2pm work?")}}

    def __getattr__(self, name):
        raise AssertionError("the seed job called Instantly.%s" % name)


START = settings.parse_start_at("2026-09-15")
NOW = TICK


def _pairs(tmp_env):
    """His replies in the recorded list that answer a lead message, by hand:
    the rows sent to a lead's address (the fixture has no ue_type) with an
    earlier message of the lead's in the thread since our last email."""
    return seed.find_examples(MANUAL, START, seed.store_index(JsonFileStore(tmp_env / "empty.json")))


def test_the_seed_dry_run_prints_and_writes_nothing(tmp_env, monkeypatch, capsys):
    store = JsonFileStore(tmp_env / "seed.json")
    for key in ("JOB_LOG_PATH", "SHADOW_LOG_PATH", "JOB_LOG_READ_PATH"):
        monkeypatch.setenv(key, str(tmp_env / ("before_" + key.lower())))
    inst = ManualList(MANUAL)
    assert seed.main(["--as-of", NOW.isoformat()], store=store, instantly=inst) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "would_record" in out
    assert store.keys("") == []                                  # nothing written to the store
    assert os.environ["JOB_LOG_PATH"].endswith(os.path.join("scratch", "seed_reply_examples_dryrun", "job_log.csv"))
    # reads only: the list, then his texts by id (the recorded rows carry none)
    assert inst.reads[0][0] == "list" and all(kind in ("list", "get") for kind, _ in inst.reads)


def test_the_seed_finds_his_replies_since_the_start_date_and_writes_only_with_write(tmp_env):
    store = JsonFileStore(tmp_env / "seed.json")
    found = _pairs(tmp_env)
    assert found["examples"], "the recorded list holds replies of his"
    ids = [e["email_id"] for e in found["examples"]]
    # each is a row we sent to the lead, after the start date, answering a message of the lead's
    by_id = dict((r["id"], r) for r in MANUAL)
    for e in found["examples"]:
        row = by_id[e["email_id"]]
        assert row["to_address_email_list"] != row["eaccount"] and e["sent_at"] >= START
        assert e["lead_message"]["to_address_email_list"] == row["eaccount"]
        assert e["lead_message"]["thread_id"] == row["thread_id"]
    # a bump with no lead message before it is not an example
    assert any(s["reason"] == "no_lead_message" for s in found["skipped"])

    dry = seed.run(ManualList(MANUAL), store, NOW, START, write=False)
    assert dry["counts"] == {"would_record": len(ids)} and store.keys(RX.PREFIX) == []
    wrote = seed.run(ManualList(MANUAL), store, NOW, START, write=True)
    assert wrote["counts"] == {"recorded": len(ids)} and sorted(store.keys(RX.PREFIX)) == sorted(
        RX.key_for(i) for i in ids)
    sopio = [e for e in RX.recent(n=50, store=store) if e["lead_email"] == "sopiosvanishvili@taxfoaccounting.com"]
    assert sopio and all(e["campaign_key"] == "bookkeeping_reactivation" and e["source"] == "seed" for e in sopio)
    assert any("What is your percentage?" in (e["lead_message"] or "") for e in sopio)
    # a second run keeps nothing twice
    again = seed.run(ManualList(MANUAL), store, NOW, START, write=True)
    assert again["counts"] == {"exists": len(ids)} and len(store.keys(RX.PREFIX)) == len(ids)


def test_the_seed_skips_a_reply_the_engine_sent_and_takes_the_engines_label(tmp_env):
    store = JsonFileStore(tmp_env / "seed.json")
    found = _pairs(tmp_env)["examples"]
    engine, labelled = found[0], found[1]
    # the engine's own reply is on its lead row at the row's time; another lead's
    # message was classified by the engine
    store.set("lead:%s:%s" % (engine["campaign_id"], engine["lead_email"]),
              {"lead_email": engine["lead_email"], "thread_id": engine["thread_id"],
               "history": [{"event": "reply_sent", "at": engine["sent_at"].isoformat(),
                            "sent_at": (engine["sent_at"] + timedelta(minutes=1)).isoformat()}]})
    store.set("lead:%s:%s" % (labelled["campaign_id"], "someone@example.com"),
              {"lead_email": "someone@example.com", "thread_id": labelled["thread_id"],
               "history": [{"event": "inbound", "email_id": labelled["lead_message_id"],
                            "label": "neutral_question"}]})
    # the pairing itself skips the engine's row (a belt: with a live send on
    # file the job refuses to run at all, see the refusal tests below)
    found_now = seed.find_examples(MANUAL, START, seed.store_index(store))
    assert {"email_id": engine["email_id"], "reason": "engine_sent"} in [
        {"email_id": s["email_id"], "reason": s["reason"]} for s in found_now["skipped"]]
    with pytest.raises(seed.SeedRefused):
        seed.run(ManualList(MANUAL), store, NOW, START, write=True)
    # without the engine's send on file, the example takes the engine's label
    store.delete("lead:%s:%s" % (engine["campaign_id"], engine["lead_email"]))
    seed.run(ManualList(MANUAL), store, NOW, START, write=True)
    kept = store.get(RX.key_for(labelled["email_id"]))
    assert kept["category"] == "neutral_question"


def test_the_seed_stops_paging_before_the_start_date(tmp_env):
    """Newest first: the first row older than the start date (less the lead
    message lookback) ends the read."""
    pages = [{"items": [dict(MANUAL[0], id="p1")], "next_starting_after": "p1"},
             {"items": [dict(MANUAL[0], id="old", timestamp_created="2026-09-01T12:00:00.000Z")],
              "next_starting_after": "old"},
             {"items": [dict(MANUAL[0], id="never")], "next_starting_after": None}]
    calls = []

    class Paged(object):
        def list_emails(self, **params):
            calls.append(params)
            return pages[len(calls) - 1]

    got = seed.fetch_manual_rows(Paged(), START)
    assert [r["id"] for r in got["rows"]] == ["p1"] and len(calls) == 2 and got["truncated"] is False


def test_the_seed_refuses_a_start_date_later_than_now(tmp_env):
    store = JsonFileStore(tmp_env / "seed.json")
    inst = ManualList(MANUAL)
    with pytest.raises(seed.SeedRefused, match="later than now"):
        seed.run(inst, store, NOW, settings.parse_start_at("2031-01-01"), write=True)
    assert inst.reads == [] and store.keys("") == []


@pytest.mark.parametrize("key,value", [
    ("cutover:record", {"cutover_at": "2026-10-01T10:00:00-05:00"}),
    ("lead:c1:a@example.com", {"lead_email": "a@example.com",
                               "history": [{"event": "reply_sent", "sent_at": "2026-10-01T10:00:00-05:00"}]}),
    ("lead:c1:b@example.com", {"lead_email": "b@example.com",
                               "cadence": {"touches": [{"kind": "done", "shadow": False, "sent_at": "2026-10-01"}]}}),
])
def test_the_seed_refuses_once_the_engine_has_sent_live(tmp_env, key, value, monkeypatch, capsys):
    store = JsonFileStore(tmp_env / "seed.json")
    store.set(key, value)
    inst = ManualList(MANUAL)
    for k in ("JOB_LOG_PATH", "SHADOW_LOG_PATH", "JOB_LOG_READ_PATH"):
        monkeypatch.setenv(k, str(tmp_env / ("before_" + k.lower())))
    assert seed.main(["--write", "--as-of", NOW.isoformat()], store=store, instantly=inst) == 2
    assert "REFUSED" in capsys.readouterr().out and inst.reads == [] and store.keys(RX.PREFIX) == []


def test_the_seed_refuses_the_live_dict_without_the_flag(tmp_env, monkeypatch, capsys):
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    for k in ("JOB_LOG_PATH", "SHADOW_LOG_PATH", "JOB_LOG_READ_PATH"):
        monkeypatch.setenv(k, str(tmp_env / ("before_" + k.lower())))
    inst = ManualList(MANUAL)
    assert seed.main(["--modal", "--write"], instantly=inst) == 2     # refused before any Dict is opened
    assert "--i-am-lorenzo-live" in capsys.readouterr().out and inst.reads == []


def test_the_cutover_copy_moves_the_shadow_examples_into_live(tmp_env, monkeypatch):
    from changesets.deploy import cutover

    for k in ("JOB_LOG_PATH", "SHADOW_LOG_PATH", "JOB_LOG_READ_PATH"):
        monkeypatch.setenv(k, str(tmp_env / ("before_" + k.lower())))
    shadow = JsonFileStore(tmp_env / "shadow.json")
    live = JsonFileStore(tmp_env / "live.json")
    for i in range(2):
        RX.record(shadow, RX.build(email_id="e-%d" % i, sent_at=SENT_AT, reply_text="r%d" % i, lead_email=LEAD,
                                   now=TICK))
    copy = ["--copy-shadow-to-live"]
    # before the cutover wrote its record: refused (the cutover needs an empty live store)
    assert seed.main(copy, store=shadow, live_store=live) == 2 and live.keys("") == []
    live.set("cutover:record", {"cutover_at": TICK.isoformat()})
    live.set("poller:cursor", {"last_email_id": "x", "last_timestamp": "y"})
    assert seed.main(copy, store=shadow, live_store=live) == 0 and live.keys(RX.PREFIX) == []      # dry run
    assert seed.main(copy + ["--write"], store=shadow, live_store=live) == 2                       # no flag
    assert seed.main(copy + ["--write", "--i-am-lorenzo-live"], store=shadow, live_store=live) == 0
    assert sorted(live.keys(RX.PREFIX)) == sorted(shadow.keys(RX.PREFIX))
    # copied examples are not live activity, so --redo / --resume-live read the store as before
    assert cutover.live_activity(live) == []


def test_the_hourly_cadence_tick_reads_every_example(env):
    """Modal deletes a Dict entry after 7 days with no read or write; the tick
    reads every reply_example:* key, as it reads every lead record."""
    store = env["store"]
    for i in range(3):
        RX.record(store, RX.build(email_id="e-%d" % i, sent_at=SENT_AT, reply_text="r", lead_email=LEAD, now=TICK))
    reads = []
    real_get = store.get

    def spying_get(key, default=None):
        reads.append(key)
        return real_get(key, default)

    store.get = spying_get
    summary = cadence.tick(now=TICK, store=store, dry_run=True)
    assert summary["reply_examples_read"] == 3
    assert set(RX.key_for("e-%d" % i) for i in range(3)) <= set(reads)
