"""The poller's start date (Lorenzo, 2026-09-25: only the replies since the
current campaigns started matter, not the whole inbox).

Replies received before shared.settings.poller_start_at() are never passed to
process_event, so they are never classified, drafted or carded and cost no
model call; they are marked seen with the reason "before_start_date", and
paging stops at the first of them. With the setting off the poller is exactly
what it was. Every transport is a MockTransport over the recorded September
fixture; every clock is fixed.
"""
from datetime import datetime

import httpx
import pytest
import pytz

from shared import llm, settings, slots
from shared.instantly import Instantly
from shared.store import JsonFileStore

from services.reply_engine import classify
from services.reply_engine import poller as P
from services.reply_engine.models import ReplyEvent
from services.reply_engine.tests.test_core_poller import REPLIES, NOW, EmailsServer, fake_process

CT = pytz.timezone("America/Chicago")
START = "2026-09-18"                                   # midnight CT = 2026-09-18T05:00Z
START_AT = CT.localize(datetime(2026, 9, 18))


def _at(row):
    return slots.parse_iso(row["timestamp_created"])


NEWER = [r for r in REPLIES if _at(r) >= START_AT]
OLDER = [r for r in REPLIES if _at(r) < START_AT]


def make(items, page_size=10):
    server = EmailsServer(items, page_size)
    return Instantly(api_key="x", transport=httpx.MockTransport(server)), server


CURRENT = {"id": None}   # the reply being classified, so each model call is attributed to one


def classifying_process():
    """A process that classifies the way process_event does (classify.classify:
    rules, then the model)."""
    seen = []

    def process(event, now=None):
        seen.append(event)
        CURRENT["id"] = event.email_id
        try:
            label = classify.classify(event).label
        finally:
            CURRENT["id"] = None
        return {"label": label, "status": "s", "actions": [], "draft": None, "approval_token": None}

    process.seen = seen
    return process


@pytest.fixture
def model_calls(monkeypatch):
    """Every shared.llm.complete call (faked in tests), with the reply it was for."""
    calls = []
    real = llm.complete

    def counting(*args, **kwargs):
        calls.append(CURRENT["id"])
        return real(*args, **kwargs)

    monkeypatch.setattr(llm, "complete", counting)
    return calls


def test_the_fixture_is_newest_first_and_straddles_the_start_date():
    """The ordering assumption paging relies on: GET /emails?email_type=received
    answers newest first. The recorded live page is in strictly descending
    timestamp_created."""
    stamps = [r["timestamp_created"] for r in REPLIES]
    assert stamps == sorted(stamps, reverse=True) and len(set(stamps)) == len(stamps)
    assert NEWER and OLDER and len(NEWER) + len(OLDER) == 44


def test_replies_before_the_start_date_are_never_processed_and_cost_no_model_call(tmp_env, model_calls):
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = classifying_process()
    summary = P.run_once(instantly, store, now=NOW, process=process, start_at=START)

    # only the replies since the start date reached the classifier
    assert sorted(e.email_id for e in process.seen) == sorted(r["id"] for r in NEWER)
    assert all(e.received_at >= START_AT for e in process.seen)
    assert summary["processed"] == len(NEWER) and summary["new"] == len(NEWER)
    # no model call was made for any older reply
    older_ids = set(r["id"] for r in OLDER)
    assert model_calls and not older_ids.intersection(model_calls)
    # ... and that is the start date's doing: the same classifier asks the
    # model about older replies when they are handed to it
    del model_calls[:]
    for row in OLDER:
        CURRENT["id"] = row["id"]
        classify.classify(ReplyEvent.from_poller_item(row, source="poller"))
    CURRENT["id"] = None
    assert older_ids.intersection(model_calls)
    # the older ones on the page that reached the start date are recorded as
    # skipped with the reason, and seen, so a later poll never takes them up
    skipped = [r for r in summary["results"] if r.get("skipped") == P.BEFORE_START]
    assert skipped and summary["before_start"] == len(skipped)
    assert all(slots.parse_iso(r["received_at"]) < START_AT for r in skipped)
    seen = store.get(P.SEEN_KEY)
    assert all(r["email_id"] in seen for r in skipped)
    assert summary["start_at"] == START_AT.isoformat() and summary["reached_start"] is True
    # not failures: nothing holds the cursor, which moves to the newest row
    assert summary["truncated"] is False and store.get(P.FAILED_KEY) == {}
    assert store.get(P.CURSOR_KEY)["last_email_id"] == REPLIES[0]["id"]


def test_paging_stops_at_the_first_row_older_than_the_start_date(tmp_env):
    page_size = 10
    instantly, server = make(REPLIES, page_size=page_size)
    store = JsonFileStore(tmp_env / "s.json")
    summary = P.run_once(instantly, store, now=NOW, process=fake_process(), start_at=START)
    # the first older row sits at index len(NEWER); its page is the last one read
    expected_pages = len(NEWER) // page_size + 1
    assert summary["pages"] == expected_pages == len(server.requests) < 5
    # every older row on that page is taken as skipped (already fetched, no
    # cost); the rows on later pages were never requested
    on_last_page = REPLIES[(expected_pages - 1) * page_size: expected_pages * page_size]
    assert summary["before_start"] == len([r for r in on_last_page if _at(r) < START_AT])
    assert summary["fetched"] == expected_pages * page_size

    # the next poll stops at the cursor after one page, whatever the start date
    del server.requests[:]
    again = P.run_once(instantly, store, now=NOW, process=fake_process(), start_at=START)
    assert again["pages"] == 1 and again["new"] == 0 and again["before_start"] == 0


def test_a_truncated_first_poll_keeps_the_cursor_and_never_reaches_older_replies(tmp_env):
    """--limit / the time budget still hold the cursor; the start date still
    bounds the rescan, so the older replies are never processed on any run."""
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    first = P.run_once(instantly, store, now=NOW, process=process, start_at=START, max_items=3)
    assert first["truncated"] is True and first["processed"] == 3 and store.get(P.CURSOR_KEY) == {}
    second = P.run_once(instantly, store, now=NOW, process=process, start_at=START)
    assert second["truncated"] is False
    assert sorted(e.email_id for e in process.seen) == sorted(r["id"] for r in NEWER)
    assert store.get(P.CURSOR_KEY)["last_email_id"] == REPLIES[0]["id"]


def test_with_the_start_date_off_the_poller_is_unchanged(tmp_env, monkeypatch):
    """test_core_poller.test_run_once_paginates_filters_and_processes_oldest_first,
    with the setting off in the environment: all 44 processed, 5 pages, same cursor."""
    monkeypatch.setenv(settings.POLLER_START_AT_ENV, "off")
    assert settings.poller_start_at() is None
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    process = fake_process()
    summary = P.run_once(instantly, store, now=NOW, process=process)
    assert summary["pages"] == 5 and summary["fetched"] == 44 and summary["processed"] == 44
    assert summary["before_start"] == 0 and summary["start_at"] is None and summary["reached_start"] is False
    assert not any(r.get("skipped") == P.BEFORE_START for r in summary["results"])
    assert store.get(P.CURSOR_KEY) == {"last_email_id": REPLIES[0]["id"],
                                       "last_timestamp": REPLIES[0]["timestamp_created"]}
    # and the keyword argument turns it off the same way
    instantly2, _ = make(REPLIES, page_size=10)
    other = P.run_once(instantly2, JsonFileStore(tmp_env / "s2.json"), now=NOW, process=fake_process(),
                       start_at="off")
    assert other["processed"] == 44 and other["pages"] == 5


def test_fetch_new_replies_without_a_start_date_returns_what_it_did(tmp_env):
    instantly, server = make(REPLIES, page_size=10)
    out = P.fetch_new_replies(instantly, None, [], {}, max_pages=20)
    assert len(out["items"]) == 44 and out["before_start"] == [] and out["reached_start"] is False
    assert out["truncated"] is False and out["pages"] == 5


def test_the_default_is_the_day_the_2026_campaigns_started_sending(monkeypatch):
    monkeypatch.delenv(settings.POLLER_START_AT_ENV, raising=False)
    assert settings.POLLER_START_AT_DEFAULT == "2026-09-15"
    assert settings.poller_start_at() == CT.localize(datetime(2026, 9, 15))
    # the earliest recorded reply is after it, so the default skips none of them
    assert min(_at(r) for r in REPLIES) >= settings.poller_start_at()


@pytest.mark.parametrize("value,expected", [
    ("2026-09-15", CT.localize(datetime(2026, 9, 15))),                                  # a date: midnight CT
    ("2026-09-15T08:30:00", CT.localize(datetime(2026, 9, 15, 8, 30))),                  # naive: CT
    ("2026-09-15T13:30:00Z", pytz.utc.localize(datetime(2026, 9, 15, 13, 30))),          # Z: UTC
    ("2026-09-15T08:30:00-05:00", CT.localize(datetime(2026, 9, 15, 8, 30))),            # offset: as written
    ("", CT.localize(datetime(2026, 9, 15))),                                            # empty: the default
    ("off", None), ("NONE", None), ("0", None),
])
def test_start_date_values(value, expected):
    assert settings.parse_start_at(value) == expected


def test_an_unreadable_start_date_stops_the_poll_before_any_read(tmp_env, monkeypatch):
    monkeypatch.setenv(settings.POLLER_START_AT_ENV, "15/09/2026")
    instantly, server = make(REPLIES, page_size=10)
    with pytest.raises(ValueError):
        P.run_once(instantly, JsonFileStore(tmp_env / "s.json"), now=NOW, process=fake_process())
    assert server.requests == []


def test_a_reply_that_failed_before_the_start_date_moved_past_it_stops_holding_the_cursor(tmp_env):
    """A reply that raised on an earlier run sits in poller:failed and holds
    the cursor until MAX_FAILED_ATTEMPTS. Once the start date is past it, it
    is never retried, so it leaves poller:failed and the cursor moves."""
    old = OLDER[0]
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    store.set(P.FAILED_KEY, {old["id"]: {"attempts": 1, "error": "timeout", "timestamp_created": old["timestamp_created"]}})
    process = fake_process()
    summary = P.run_once(instantly, store, now=NOW, process=process, start_at=START)
    assert old["id"] not in [e.email_id for e in process.seen]
    assert store.get(P.FAILED_KEY) == {} and summary["truncated"] is False
    assert old["id"] in store.get(P.SEEN_KEY)
    assert store.get(P.CURSOR_KEY)["last_email_id"] == REPLIES[0]["id"]


def test_a_failed_reply_far_older_than_the_start_date_is_retired_without_being_fetched(tmp_env):
    """Its page is never read (paging stops at the start date), so it is
    retired from its failed record's own timestamp."""
    instantly, server = make(REPLIES, page_size=10)
    store = JsonFileStore(tmp_env / "s.json")
    store.set(P.FAILED_KEY, {"ancient-1": {"attempts": 1, "error": "timeout",
                                           "timestamp_created": "2026-09-01T12:00:00.000Z"}})
    summary = P.run_once(instantly, store, now=NOW, process=fake_process(), start_at=START)
    assert store.get(P.FAILED_KEY) == {} and summary["truncated"] is False
    assert store.get(P.CURSOR_KEY)["last_email_id"] == REPLIES[0]["id"]
