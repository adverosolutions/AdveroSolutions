"""D1 round 3, defect 2: a poll killed by Modal's 240 s timeout must never drop
the reply it was working on.

A killed container leaves that reply claimed "in flight" (app.CLAIM_STALE_MINUTES,
15). The next */5 run used to get {'skipped': 'in_flight'} back, mark the reply
seen and move the cursor past it, so it was never classified, drafted or
carded. The fix: an in_flight skip is never seen and holds the cursor, and the
scheduled run stops taking new replies well before its timeout.
"""
from datetime import timedelta
from pathlib import Path

import httpx

from shared.store import JsonFileStore

from services.reply_engine import poller as P
from services.reply_engine.tests.test_core_poller import NOW, REPLIES, make


CAMPAIGN = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"


def _one_campaign(n):
    rows = sorted((r for r in REPLIES if r["campaign_id"] == CAMPAIGN), key=lambda it: it["timestamp_created"])
    assert len(rows) >= n
    return rows[:n]


class ContainerKilled(BaseException):
    """What a Modal timeout looks like from inside: nothing below it runs, no
    ``except Exception`` catches it, nothing is saved on the way out."""


def test_a_run_killed_mid_reply_still_gets_that_reply_processed(tmp_env, monkeypatch):
    from shared import notify
    from shared.ghl import GHL
    from services.reply_engine import app as app_mod

    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit")
    notify.reset_for_tests()
    victim = "tiffany@flowerhillfs.com"
    rows = [r for r in REPLIES if r["from_address_email"] == victim]
    email_id = rows[0]["id"]
    store = JsonFileStore(tmp_env / "s.json")
    instantly, server = make(rows, page_size=10)
    app_mod.configure(store=store, ghl=GHL(token=None, transport=httpx.MockTransport(server)), instantly=instantly,
                      clock=lambda: NOW)
    real_classify = app_mod.classify
    try:
        # Run 1: the container dies inside process_event, after the claim.
        def killed(event):
            raise ContainerKilled("modal timeout at 240 s")

        monkeypatch.setattr(app_mod, "classify", killed)
        try:
            P.run_once(instantly, store, now=NOW)
        except ContainerKilled:
            pass
        else:  # pragma: no cover - the kill must escape
            raise AssertionError("the simulated kill was swallowed")
        assert store.get(P.CURSOR_KEY) is None, "a killed run saved nothing"
        assert any(k.startswith(app_mod.CLAIM_PREFIX) for k in store.keys(app_mod.CLAIM_PREFIX))
        monkeypatch.setattr(app_mod, "classify", real_classify)

        # Run 2, the next */5 tick, inside the claim's 15 minutes.
        instantly2, _ = make(rows, page_size=10)
        second = P.run_once(instantly2, store, now=NOW + timedelta(minutes=5))
        assert second["processed"] == 0 and second["in_flight"] == [email_id]
        assert email_id not in (store.get(P.SEEN_KEY) or {}), "an in_flight skip must never be marked seen"
        assert store.get(P.CURSOR_KEY) in ({}, None), "the cursor must not move past an in_flight reply"
        assert second["truncated"] is True
        assert store.keys("approval:") == []

        # Run 3, once the dead run's claim is stale: the reply is processed.
        instantly3, _ = make(rows, page_size=10)
        third = P.run_once(instantly3, store, now=NOW + timedelta(minutes=20))
        assert third["processed"] == 1 and third["in_flight"] == []
        result = third["results"][0]
        assert result["email_id"] == email_id and result["draft"] is True and result["approval"] is True
        assert store.keys("approval:"), "the positive reply reached a card"
        assert email_id in (store.get(P.SEEN_KEY) or {})
        assert (store.get(P.CURSOR_KEY) or {}).get("last_email_id") == email_id
    finally:
        app_mod.configure()


def test_the_time_budget_stops_taking_new_replies_and_keeps_the_cursor(tmp_env):
    """The scheduled run stops starting replies at the budget; the rest are not
    seen, the cursor does not move, and later runs drain the backlog."""
    items = _one_campaign(6)
    store = JsonFileStore(tmp_env / "s.json")
    ticks = {"t": 0.0}

    def clock():
        return ticks["t"]

    done = []

    def process(event, now=None):
        done.append(event.email_id)
        ticks["t"] += 50.0          # each reply takes 50 s of a 120 s budget
        return {"label": "x", "status": "s", "actions": [], "draft": None, "approval_token": None}

    drained = []
    cursors = []
    for run in range(4):
        ticks["t"] = 0.0
        instantly, _ = make(items, page_size=10)
        summary = P.run_once(instantly, store, now=NOW + timedelta(minutes=5 * run), process=process,
                             campaign_filter=[CAMPAIGN], time_budget_s=120, clock=clock)
        drained.append((summary["processed"], summary["deferred"], summary["truncated"]))
        cursors.append(store.get(P.CURSOR_KEY))
        if not summary["truncated"]:
            break
    # 50 + 50 + (a third starts at 100 s < 120 s) = 3 per run; a 4th would start at 150 s
    assert drained[0] == (3, 3, True), drained
    assert cursors[0] == {}, "a budget-cut run must not move the cursor"
    assert drained[1][0] == 3 and drained[1][2] is False, drained
    assert sorted(done) == sorted(it["id"] for it in items), "every reply processed exactly once"
    assert len(done) == len(set(done))
    newest = max(items, key=lambda it: it["timestamp_created"])
    assert store.get(P.CURSOR_KEY)["last_email_id"] == newest["id"]


def test_a_budget_cut_run_does_not_advance_the_cursor(tmp_env):
    items = _one_campaign(4)
    store = JsonFileStore(tmp_env / "s.json")
    ticks = {"t": 0.0}

    def process(event, now=None):
        ticks["t"] += 200.0
        return {"label": "x", "status": "s", "actions": [], "draft": None, "approval_token": None}

    instantly, _ = make(items, page_size=10)
    summary = P.run_once(instantly, store, now=NOW, process=process, campaign_filter=[CAMPAIGN],
                         time_budget_s=120, clock=lambda: ticks["t"])
    assert summary["processed"] == 1 and summary["deferred"] == 3 and summary["truncated"] is True
    assert store.get(P.CURSOR_KEY) == {}
    assert len(store.get(P.SEEN_KEY) or {}) == 1


def test_the_modal_poller_passes_a_budget_well_inside_its_timeout(monkeypatch):
    from services.reply_engine import modal_app

    assert modal_app.POLLER_TIME_BUDGET_S <= modal_app.MODAL_TIMEOUTS["poller"] // 2
    seen = {}

    def run_once(time_budget_s=None):
        seen["budget"] = time_budget_s
        return {"ok": True}

    import services.reply_engine.poller as poller_mod

    monkeypatch.setattr(poller_mod, "run_once", run_once)
    monkeypatch.setattr(modal_app, "_log_row", lambda *a, **k: None)
    modal_app._call_entrypoint("services.reply_engine.poller", ("run_once",),
                               time_budget_s=modal_app.POLLER_TIME_BUDGET_S)
    assert seen["budget"] == modal_app.POLLER_TIME_BUDGET_S
    source = Path(modal_app.__file__).read_text(encoding="utf-8")
    assert "time_budget_s=POLLER_TIME_BUDGET_S" in source
