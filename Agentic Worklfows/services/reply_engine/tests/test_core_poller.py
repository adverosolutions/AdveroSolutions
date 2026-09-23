"""Poller: GET-only pagination over /emails, campaign filter, dedupe and cursor."""
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytz

from shared.instantly import Instantly
from shared.store import JsonFileStore

from services.reply_engine import poller as P

FIXTURES = Path(__file__).parent / "fixtures"
REPLIES = json.loads((FIXTURES / "instantly_replies_2026-09.json").read_text(encoding="utf-8"))
CT = pytz.timezone("America/Chicago")
NOW = CT.localize(datetime(2026, 9, 21, 21, 10))


class EmailsServer(object):
    """Serves items newest-first in pages with next_starting_after; refuses anything but GET /emails."""

    def __init__(self, items, page_size=10):
        self.items = sorted(items, key=lambda it: it["timestamp_created"], reverse=True)
        self.page_size = page_size
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if request.method != "GET" or request.url.path != "/api/v2/emails":
            raise AssertionError("unexpected request %s %s" % (request.method, request.url))
        params = dict(request.url.params)
        assert params.get("email_type") == "received"
        start = 0
        cursor = params.get("starting_after")
        if cursor:
            ids = [it["id"] for it in self.items]
            start = ids.index(cursor) + 1
        page = self.items[start: start + self.page_size]
        nxt = page[-1]["id"] if page and start + self.page_size < len(self.items) else None
        return httpx.Response(200, json={"items": page, "next_starting_after": nxt})


def make(items, page_size=10):
    server = EmailsServer(items, page_size)
    return Instantly(api_key="x", transport=httpx.MockTransport(server)), server


def fake_process():
    seen = []

    def process(event, now=None):
        seen.append(event)
        return {"label": "x", "status": "s", "actions": [], "draft": None, "approval_token": None}

    process.seen = seen
    return process


def test_run_once_paginates_filters_and_processes_oldest_first(tmp_env):
    foreign = dict(REPLIES[0], id="foreign-1", campaign_id="not-ours", timestamp_created="2026-09-22T01:00:00.000Z")
    own = dict(REPLIES[0], id="own-1", from_address_email="lorenzo@myadvero.com", timestamp_created="2026-09-22T02:00:00.000Z")
    instantly, server = make(REPLIES + [foreign, own], page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    summary = P.run_once(instantly, store, now=NOW, process=process)
    assert summary["fetched"] == 46 and summary["pages"] == 5
    assert summary["new"] == 44 and summary["processed"] == 44 and summary["errors"] == 0
    assert all(r.method == "GET" for r in server.requests)
    ids = [e.email_id for e in process.seen]
    assert "foreign-1" not in ids and "own-1" not in ids and len(ids) == 44
    times = [e.received_at for e in process.seen]
    assert times == sorted(times)
    assert all(e.source == "poller" for e in process.seen)
    cursor = store.get(P.CURSOR_KEY)
    # the high-water mark is the newest row the scan SAW, including the ones it
    # filtered out (foreign campaign, Lorenzo's own inbox): those will never be
    # processed, so leaving the cursor behind them only costs a re-scan
    assert cursor == {"last_email_id": "own-1", "last_timestamp": "2026-09-22T02:00:00.000Z"}
    assert len(store.get(P.SEEN_KEY)) == 44


def test_second_run_stops_at_cursor_and_processes_only_new(tmp_env):
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    P.run_once(instantly, store, now=NOW, process=process)
    assert len(process.seen) == 44
    # nothing new: one page fetched, stops at the cursor id
    server.requests[:] = []
    summary = P.run_once(instantly, store, now=NOW, process=process)
    assert summary["new"] == 0 and summary["pages"] == 1 and len(process.seen) == 44
    # a newer reply arrives
    newer = dict(REPLIES[0], id="new-1", timestamp_created="2026-09-22T03:00:00.000Z")
    server.items.insert(0, newer)
    summary = P.run_once(instantly, store, now=NOW, process=process)
    assert summary["new"] == 1 and process.seen[-1].email_id == "new-1"
    assert store.get(P.CURSOR_KEY)["last_email_id"] == "new-1"


def test_duplicate_ids_across_pages_are_processed_once(tmp_env):
    dup = list(REPLIES) + [dict(REPLIES[5])]  # same id twice
    instantly, server = make(dup, page_size=7)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    summary = P.run_once(instantly, store, now=NOW, process=process)
    assert summary["fetched"] == 45 and summary["new"] == 44 and len(process.seen) == 44


def test_explicit_since_cursor_by_timestamp(tmp_env):
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    summary = P.run_once(instantly, store, since_cursor={"last_timestamp": "2026-09-21T00:00:00.000Z"}, now=NOW, process=process)
    assert summary["new"] == 4 and all(e.received_at.isoformat() >= "2026-09-21" for e in process.seen)


def test_max_items_and_persist_cursor_false_for_dry_run(tmp_env):
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    summary = P.run_once(instantly, store, now=NOW, process=process, max_items=3, persist_cursor=False)
    assert summary["new"] == 3 and store.get(P.CURSOR_KEY) is None and store.get(P.SEEN_KEY) is None


def test_one_bad_reply_does_not_stop_the_poll(tmp_env):
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")

    def process(event, now=None):
        if event.lead_email == "buck@cgavery.com":
            raise RuntimeError("boom")
        return {"label": "x", "status": "s", "actions": [], "draft": None, "approval_token": None}

    summary = P.run_once(instantly, store, now=NOW, process=process)
    assert summary["errors"] == 1 and summary["processed"] == 43
    assert any(r.get("error") == "boom" for r in summary["results"])


def test_full_pipeline_through_poller_is_shadow_only(tmp_env, monkeypatch):
    """Real process_event, GET-only transport: any write would raise inside the transport."""
    from shared import job_log, notify
    from shared.ghl import GHL
    from services.reply_engine import app as app_mod

    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit")
    notify.reset_for_tests()
    instantly, server = make(REPLIES, page_size=25)
    store = JsonFileStore(tmp_env / "s.json")
    app_mod.configure(store=store, ghl=GHL(token=None, transport=httpx.MockTransport(server)), instantly=instantly, clock=lambda: NOW)
    try:
        summary = P.run_once(instantly, store, now=NOW)
    finally:
        app_mod.configure()
    assert summary["processed"] == 44 and summary["errors"] == 0
    labels = [r["label"] for r in summary["results"]]
    assert labels.count("ooo") == 17 and labels.count("positive_interested") == 6
    assert sum(1 for r in summary["results"] if r["draft"]) == 9
    assert all(r.method == "GET" for r in server.requests)
    log = job_log.read_shadow_log()
    assert log and all(x["mode"] == "shadow" for x in log)
    assert sum(1 for x in log if x["action"] == "blocklist_create") == 6
    assert len(notify.sent_in_test) == 9
    # 44 replies from 39 distinct leads: Sopio x3, Ilmi x3 and Rob x2 collapse into one lead:<campaign>:<email> each
    assert len(store.keys("lead:")) == 39


def test_run_once_is_the_modal_entrypoint(monkeypatch, tmp_env):
    """modal_app calls poller.run_once() with no arguments (_call_entrypoint)."""
    import inspect

    sig = inspect.signature(P.run_once)
    required = [n for n, p in sig.parameters.items() if p.default is inspect.Parameter.empty]
    assert required == [], "run_once() must be callable with no arguments: %s" % required

    built = {}
    instantly, server = make(REPLIES, page_size=25)
    store = JsonFileStore(tmp_env / "s.json")

    def fake_build():
        built["called"] = True
        return instantly, store

    monkeypatch.setattr(P, "build_deps", fake_build)
    summary = P.run_once(now=NOW, process=fake_process())
    assert built.get("called") is True
    assert summary["new"] == 44 and summary["mode"] == "shadow"
    assert all(r.method == "GET" for r in server.requests)


def test_lead_state_keys_are_lead_campaign_email(tmp_env, monkeypatch):
    """jobs/cadence_tick.py and jobs/pipeline_sweep.py read 'lead:<campaign_id>:<email>'."""
    from shared.ghl import GHL
    from services.reply_engine import app as app_mod

    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit")
    instantly, server = make(REPLIES, page_size=25)
    store = JsonFileStore(tmp_env / "s.json")
    app_mod.configure(store=store, ghl=GHL(token=None, transport=httpx.MockTransport(server)), instantly=instantly, clock=lambda: NOW)
    try:
        P.run_once(instantly, store, now=NOW)
    finally:
        app_mod.configure()
    keys = store.keys("lead:")
    assert keys and all(k.count(":") == 2 for k in keys)
    campaigns = {k.split(":")[1] for k in keys}
    assert campaigns <= {c["id"] for c in __import__("shared").settings.CAMPAIGNS.values()}
    positive = [k for k in keys if (store.get(k) or {}).get("status") in ("draft_pending_approval", "positive_awaiting_draft")]
    assert len(positive) == 4  # Rob, Tiffany, Ilmi and Sopio: the leads the sweep must surface


# ------------------------------------------- the cursor must not outrun the work
def test_max_items_does_not_advance_the_cursor_past_unprocessed_replies(tmp_env):
    """run_once persisted the cursor at the newest fetched item even when the
    fetch was truncated, so everything older was skipped forever: with --limit 3
    over this 44-reply backlog, 41 replies - every positive one among them - were
    never classified, drafted or shown to Lorenzo."""
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    first = P.run_once(instantly, store, now=NOW, process=process, max_items=3)
    assert first["new"] == 3 and first["truncated"] is True
    assert store.get(P.CURSOR_KEY) == {}  # unchanged: the backlog is still outstanding

    second = P.run_once(instantly, store, now=NOW, process=process, max_items=3)
    assert second["new"] == 3 and len(process.seen) == 6  # three more, not zero

    rest = P.run_once(instantly, store, now=NOW, process=process)
    assert rest["truncated"] is False
    assert len({e.email_id for e in process.seen}) == 44
    newest = max(REPLIES, key=lambda it: it["timestamp_created"])
    assert store.get(P.CURSOR_KEY)["last_email_id"] == newest["id"]


def test_max_pages_exhaustion_leaves_the_cursor_alone(tmp_env):
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    first = P.run_once(instantly, store, now=NOW, process=process, max_pages=2)
    assert first["truncated"] is True and first["new"] == 20
    assert store.get(P.CURSOR_KEY) == {}

    rest = P.run_once(instantly, store, now=NOW, process=process, max_pages=20)
    assert rest["truncated"] is False
    assert len({e.email_id for e in process.seen}) == 44


def test_a_complete_fetch_still_advances_the_cursor(tmp_env):
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    summary = P.run_once(instantly, store, now=NOW, process=fake_process())
    assert summary["truncated"] is False
    newest = max(REPLIES, key=lambda it: it["timestamp_created"])
    assert store.get(P.CURSOR_KEY)["last_email_id"] == newest["id"]


# ------------------------------------------------ the live GET /emails shape
API_SHAPE = json.loads((FIXTURES / "instantly_emails_api_shape_2026-09-21.json").read_text(encoding="utf-8"))


def test_poller_item_reads_body_text_not_content_preview():
    """Live GET /emails nests the reply under body.text and carries
    content_preview, a ~60 character truncation. from_poller_item read
    text/body_text/content_preview, so on the only live ingestion path the
    engine saw 60 characters cut mid-word: every time, phone number, question
    and opt-out past that point was invisible to classify and extract."""
    from services.reply_engine.models import ReplyEvent as RE

    ilmi = [r for r in API_SHAPE if r["lead"] == "ilmi@shiningarmorcleaningnj.com"][0]
    assert "text" not in ilmi and "body_text" not in ilmi  # the shape the API really returns
    event = RE.from_poller_item(ilmi)
    assert event.text == ilmi["body"]["text"]
    assert len(event.text) > len(ilmi["content_preview"])
    assert "11:30" in event.text and "11:30" not in ilmi["content_preview"]
    # html is the fallback when body.text is absent
    html_only = dict(ilmi, body={"html": ilmi["body"]["html"]})
    assert "11:30" in RE.from_poller_item(html_only).text
    # content_preview is the last resort, not the first choice
    preview_only = dict(ilmi)
    preview_only.pop("body")
    assert RE.from_poller_item(preview_only).text == ilmi["content_preview"]


def test_poller_item_carries_the_thread_counterparty_and_message_id():
    """item['lead'] is the CRM address; item['from_address_email'] is who wrote
    the thread. Instantly validates the reply `to` against the thread, so the
    two must not be confused."""
    from services.reply_engine.models import ReplyEvent as RE

    ilmi = [r for r in API_SHAPE if r["lead"] == "ilmi@shiningarmorcleaningnj.com"][0]
    event = RE.from_poller_item(ilmi)
    assert event.lead_email == "ilmi@shiningarmorcleaningnj.com"
    assert event.reply_from == "info@shiningarmorcleaningnj.com"
    assert event.reply_to_address == "info@shiningarmorcleaningnj.com"
    assert event.message_id == ilmi["message_id"]
    assert ("mid:%s" % ilmi["message_id"]) in event.dedupe_keys


def test_the_api_shape_runs_through_the_real_classifier():
    """The flattened fixture is a hand-made shape; this is the wire format."""
    from services.reply_engine import classify as C
    from services.reply_engine.models import ReplyEvent as RE

    ilmi = [r for r in API_SHAPE if r["lead"] == "ilmi@shiningarmorcleaningnj.com"][0]
    res = C.classify(RE.from_poller_item(ilmi))
    assert res.label == "positive_interested"
    assert res.extracted.proposed_time == "2026-09-23T11:30:00-05:00"
    sopio = [r for r in API_SHAPE if r["lead"] == "sopiosvanishvili@taxfoaccounting.com"][0]
    res2 = C.classify(RE.from_poller_item(sopio))
    assert res2.extracted.availability_window == {"start_hour": 15, "end_hour": 18, "tz": "America/New_York"}


def test_pending_approval_digest_surfaces_unactioned_cards(tmp_env):
    """notify() swallows its own failures and returns sent=False, so a card that
    never reached Lorenzo used to sit in the store with nothing surfacing it."""
    store = JsonFileStore(tmp_env / "s.json")
    store.set("approval:old1", {"status": "pending", "lead_email": "a@b.co", "created_at": "2026-09-21T20:00:00-05:00",
                                "notify_result": {"sent": False, "errors": ["ntfy: boom"]}})
    store.set("approval:new1", {"status": "pending", "lead_email": "c@d.co", "created_at": "2026-09-21T21:05:00-05:00",
                                "notify_result": {"sent": True}})
    store.set("approval:done", {"status": "sent", "lead_email": "e@f.co", "created_at": "2026-09-20T09:00:00-05:00"})
    waiting = P.pending_approvals(store, NOW)
    assert [w["lead"] for w in waiting] == ["a@b.co"]
    assert waiting[0]["pushed"] is False


def test_failed_reply_is_retried_on_the_next_poll(tmp_env):
    """A classifier timeout on one reply used to retire it: the id went into
    poller:seen and the cursor moved past it, so the reply was never fetched
    again and never classified, drafted or shown to Lorenzo."""
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    calls = {"n": 0}
    victim = "buck@cgavery.com"

    def flaky(event, now=None):
        if event.lead_email == victim:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("classifier timeout")
        return {"label": "x", "status": "s", "actions": [], "draft": None, "approval_token": None}

    first = P.run_once(instantly, store, now=NOW, process=flaky)
    assert first["errors"] == 1
    assert victim not in [r.get("lead") for r in first["results"] if not r.get("error")]
    assert store.get(P.CURSOR_KEY) == {}                 # cursor held: the failure is still unread
    assert list((store.get(P.FAILED_KEY) or {}).keys())  # and it is recorded as pending

    instantly2, _ = make(REPLIES, page_size=10)
    second = P.run_once(instantly2, store, now=NOW, process=flaky)
    assert second["errors"] == 0
    assert [r["lead"] for r in second["results"]] == [victim]   # only the failure came back
    assert second["processed"] == 1
    assert store.get(P.FAILED_KEY) == {}
    assert store.get(P.CURSOR_KEY)                        # now the cursor may advance


# ------------------------------- the retry path has to do real work
def test_a_reply_that_failed_mid_pipeline_is_actually_reprocessed_by_the_real_process_event(tmp_env, monkeypatch):
    """test_failed_reply_is_retried_on_the_next_poll substitutes a fake
    `process` that keeps no state, so the interaction between process_event's
    claim and the poller's retry was never exercised. With the real pipeline the
    claim was written as 'processed' BEFORE classification, so run 2 answered
    {'skipped': 'duplicate'} - which the poller counts as a success, clearing
    the retry record and advancing the cursor - and the positive reply was
    retired without ever being classified, drafted or shown."""
    from shared import notify
    from shared.ghl import GHL
    from services.reply_engine import app as app_mod

    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit")
    notify.reset_for_tests()
    victim = "tiffany@flowerhillfs.com"
    rows = [r for r in REPLIES if r["from_address_email"] == victim]
    assert rows and rows[0]["id"] == "01a0af6e-3cca-7f67-8660-349b15dfb36f"
    instantly, server = make(rows, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    app_mod.configure(store=store, ghl=GHL(token=None, transport=httpx.MockTransport(server)), instantly=instantly,
                      clock=lambda: NOW)
    real_classify = app_mod.classify
    calls = {"n": 0}

    def flaky(event):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("anthropic 529")
        return real_classify(event)

    try:
        monkeypatch.setattr(app_mod, "classify", flaky)
        first = P.run_once(instantly, store, now=NOW)
        assert first["errors"] == 1 and first["processed"] == 0
        assert list((store.get(P.FAILED_KEY) or {}).keys()) == [rows[0]["id"]]
        assert store.get(P.CURSOR_KEY) == {}
        assert store.keys("approval:") == []

        instantly2, _ = make(rows, page_size=10)
        second = P.run_once(instantly2, store, now=NOW)
        assert second["errors"] == 0 and second["processed"] == 1
        result = second["results"][0]
        assert result["label"] == "positive_question", result
        assert result["draft"] is True and result["approval"] is True
        assert store.keys("approval:")
        assert store.get(P.FAILED_KEY) == {}
        assert store.get(P.CURSOR_KEY)
        # and a third poll really is a no-op
        instantly3, _ = make(rows, page_size=10)
        third = P.run_once(instantly3, store, now=NOW)
        assert third["processed"] == 0 and third["errors"] == 0
        assert len(store.keys("approval:")) == 1
    finally:
        app_mod.configure()


def test_a_permanently_failing_reply_stops_holding_the_cursor(tmp_env):
    """`truncated = ... or errors > 0` pinned poller:cursor forever on a row
    that always raises, so every tick rescanned up to max_pages x 100 rows
    against a GET /emails endpoint limited to 20 requests a minute, and once the
    backlog grew past that budget older replies were never fetched at all."""
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    victim = "buck@cgavery.com"

    def always_bad(event, now=None):
        if event.lead_email == victim:
            raise RuntimeError("no timestamp_created")
        return {"label": "x", "status": "s", "actions": [], "draft": None, "approval_token": None}

    for attempt in range(1, P.MAX_FAILED_ATTEMPTS + 1):
        inst, _ = make(REPLIES, page_size=10)
        summary = P.run_once(inst, store, now=NOW, process=always_bad)
        assert summary["errors"] == 1, attempt
        failed = store.get(P.FAILED_KEY)
        assert failed[list(failed)[0]]["attempts"] == attempt
        if attempt < P.MAX_FAILED_ATTEMPTS:
            assert store.get(P.CURSOR_KEY) == {}, attempt          # still held
    # after MAX_FAILED_ATTEMPTS the cursor is released, and the id is still recorded
    assert store.get(P.CURSOR_KEY), store.get(P.CURSOR_KEY)
    assert victim in str(store.get(P.FAILED_KEY)) or list(store.get(P.FAILED_KEY))
    assert list(store.get(P.FAILED_KEY))


# ------------------------------------------- nothing auto-sends on the tick
def test_the_scheduled_tick_never_auto_sends(tmp_env, monkeypatch):
    """auto_send_due was wired into the every-5-minute poller, so one
    environment variable would have made the engine send the first reply to a
    positive lead with no human in the loop. It is no longer called from
    run_once. CT3's only auto-send (an approved template, exactly) runs in
    the reply pipeline, not on the tick."""
    import inspect

    code = [ln for ln in inspect.getsource(P.run_once).splitlines() if not ln.strip().startswith("#")]
    assert "auto_send_due" not in "\n".join(code)
    assert "flush_queued" in "\n".join(code)
    # CT3: the tick pushes cards whose template auto-send never ran and sends
    # the counts-only FYI; neither sends a reply (the template auto-send runs
    # in the reply pipeline, approval.auto_send_approved).
    assert "push_orphaned_deferred" in "\n".join(code)
    assert "flush_auto_send_fyi" in "\n".join(code)
    assert "auto_send_approved" not in "\n".join(code)

    from services.reply_engine import approval as approval_mod

    calls = []
    monkeypatch.setattr(approval_mod, "auto_send_due", lambda *a, **kw: calls.append(1) or [])
    monkeypatch.setenv("AUTO_SEND_AFTER_MINUTES", "1")
    instantly, server = make(REPLIES[:2], page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    P.run_once(instantly, store, now=NOW, process=fake_process())
    assert calls == []


def test_auto_send_refuses_a_card_that_never_reached_lorenzo(tmp_env, monkeypatch, live_mode):
    """If it is ever turned on again: a card Lorenzo never saw is not a card he
    declined to answer."""
    from services.reply_engine import approval as approval_mod

    monkeypatch.setenv("AUTO_SEND_AFTER_MINUTES", "30")
    store = JsonFileStore(tmp_env / "s.json")
    base = {"status": "pending", "label": "positive_interested", "lead_email": "a@b.co",
            "state_key": "lead:c:a@b.co", "email_id": "e1", "campaign_id": "c",
            "created_at": "2026-09-21T20:00:00-05:00", "expires_at": "2026-09-23T20:00:00-05:00",
            "token": "tok.sig", "draft": {"subject": "s", "body_text": "b\n\nLorenzo", "problems": []}}
    store.set("approval:unpushed", dict(base, notify_result={"sent": False, "errors": ["ntfy: boom"]}))
    store.set("approval:stripped", dict(base, notify_result={"sent": True, "actionable": False}))
    assert approval_mod.auto_send_due(None, store=store, now=CT.localize(datetime(2026, 9, 21, 21, 0))) == []


# -------------------------------------------- cards with nobody chasing them
def test_the_digest_surfaces_sends_that_stuck_and_cards_with_no_successor(tmp_env):
    """pending_approvals filtered on status == 'pending', so an approved send
    that failed or was interrupted (send_failed / sending) never appeared in
    'approvals still waiting on you' and nothing retried it; and a card
    superseded with nothing in its place was invisible the same way."""
    store = JsonFileStore(tmp_env / "s.json")
    store.set("approval:stuck", {"status": "sending", "lead_email": "stuck@x.co",
                                 "created_at": "2026-09-21T20:00:00-05:00",
                                 "decided_at": "2026-09-21T20:01:00-05:00", "notify_result": {"sent": True}})
    store.set("approval:failed", {"status": "send_failed", "lead_email": "failed@x.co",
                                  "created_at": "2026-09-21T20:00:00-05:00",
                                  "decided_at": "2026-09-21T20:02:00-05:00", "notify_result": {"sent": True}})
    store.set("approval:orphan", {"status": "superseded", "lead_email": "orphan@x.co",
                                  "created_at": "2026-09-21T20:00:00-05:00", "notify_result": {"sent": True}})
    store.set("approval:ok", {"status": "superseded", "lead_email": "fine@x.co",
                              "created_at": "2026-09-21T20:00:00-05:00", "notify_result": {"sent": True}})
    store.set("approval:ok2", {"status": "pending", "lead_email": "fine@x.co",
                               "created_at": "2026-09-21T21:09:00-05:00", "notify_result": {"sent": True}})
    waiting = {w["lead"]: w for w in P.pending_approvals(store, NOW)}
    assert set(waiting) == {"stuck@x.co", "failed@x.co", "orphan@x.co"}
    assert waiting["stuck@x.co"]["status"] == "sending"
    assert "stuck at send_failed" in waiting["failed@x.co"]["why"]
    assert "no card in its place" in waiting["orphan@x.co"]["why"]
    # fine@x.co was superseded BY a live card, which is what supersede is for
    assert "fine@x.co" not in waiting


def test_stuck_cards_are_pushed_once_not_every_five_minutes(tmp_env):
    from shared import notify

    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "s.json")
    store.set("approval:failed", {"status": "send_failed", "lead_email": "failed@x.co",
                                  "created_at": "2026-09-21T20:00:00-05:00",
                                  "decided_at": "2026-09-21T20:02:00-05:00", "notify_result": {"sent": True}})
    waiting = P.pending_approvals(store, NOW)
    assert P._push_stuck(store, waiting) == ["failed"]
    assert len(notify.sent_in_test) == 1
    assert "failed@x.co" in notify.sent_in_test[0]["message"]
    assert P._push_stuck(store, waiting) == []
    assert len(notify.sent_in_test) == 1
