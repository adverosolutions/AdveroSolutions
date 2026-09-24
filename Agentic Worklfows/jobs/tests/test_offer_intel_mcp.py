"""Offer Intel `collect --via mcp`: the skool-mcp transport, faked. Made-up
posts only (jobs/tests/fixtures/offer_intel/mcp/, real key shapes); no node,
no Skool, no network.
"""
import copy
import json
import subprocess
from datetime import datetime, timezone

import pytest

from shared.paths import BASE_DIR
from services.offer_intel import analyze, files, skool_read
from jobs import offer_intel as job

FIX = BASE_DIR / "jobs" / "tests" / "fixtures" / "offer_intel" / "mcp"
AS_OF = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
SINCE = datetime(2026, 9, 10, tzinfo=timezone.utc)
WINS_URL = "https://www.skool.com/makerschool?c=lab-wins-0001&s=newest"
EMPTY = {"self": True, "total": 6, "postTrees": []}


def _load(name):
    with open(FIX / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OFFER_INTEL_DIR", str(tmp_path / "offer_intel"))
    yield tmp_path / "offer_intel"


class FakeMcp(object):
    """Stands in for McpTransport: serves the fixtures and records each call."""

    def __init__(self, pages=None, fail_feed=(), fail_comments=()):
        self.pages = pages if pages is not None else {
            1: _load("feed_page_1.json"), 2: _load("feed_page_2.json"), 3: _load("feed_page_3.json")}
        self.fail_feed, self.fail_comments, self.calls = set(fail_feed), set(fail_comments), []

    def feed(self, group, label, page):
        self.calls.append(("feed", group, label, page))
        if page in self.fail_feed:
            raise skool_read.McpError("feed exit 1: boom")
        return copy.deepcopy(self.pages.get(page, EMPTY))

    def comments(self, post_id, group_id):
        self.calls.append(("comments", post_id, group_id))
        if post_id in self.fail_comments:
            raise skool_read.McpError("comments exit 1: boom")
        return _load("comments_%s.json" % post_id)


def _run(fake, **kw):
    kw.setdefault("max_pages", 5)
    return skool_read.collect_mcp(WINS_URL, now=AS_OF, transport=fake, sleep=lambda s: None, **kw)


def test_collect_mcp_saves_posts_with_only_the_authors_replies_in_order(data_dir):
    fake = FakeMcp()
    out = _run(fake)
    assert (out["status"], out["via"], out["group"]) == ("ok", "mcp", "makerschool")
    counts = out["counts"]
    assert (counts["pages"], counts["new"], counts["threads_read"], counts["threads_partial"]) == (5, 6, 3, 1)
    saved = dict((r["post_id"], r) for r in files.all_raw())
    one = saved["mp-001"]
    assert [r["id"] for r in one["author_replies"]] == ["c-13", "c-11"]  # sorted, nested one first
    assert [r["depth"] for r in one["author_replies"]] == [2, 1]
    assert "Congrats" not in json.dumps(one) and one["author_name"] == "Ann Example"
    assert one["thread_fetched"] and not one.get("thread_partial")
    two = saved["mp-002"]
    assert [r["id"] for r in two["author_replies"]] == ["c-23", "c-21"]  # pinned kept once
    assert two["thread_partial"] is True and two["author_name"] == "Cat"
    assert saved["mp-003"]["author_name"] == "eve-handle" and not saved["mp-003"]["thread_fetched"]
    comment_calls = [c for c in fake.calls if c[0] == "comments"]
    assert comment_calls == [("comments", "mp-001", "grp-0001"), ("comments", "mp-002", "grp-0001"),
                             ("comments", "mp-004", "grp-0001")]
    assert fake.calls[0] == ("feed", "makerschool", "lab-wins-0001", 1)


def test_collect_mcp_since_skips_old_posts_and_stops_paging_and_max_posts_stops(data_dir):
    fake = FakeMcp()
    out = _run(fake, since=SINCE, max_pages=10)
    assert sorted(r["post_id"] for r in files.all_raw()) == ["mp-001", "mp-002", "mp-003"]
    assert out["counts"]["skipped_old"] == 3
    assert [c[3] for c in fake.calls if c[0] == "feed"] == [1, 2, 3]  # two old pages end the walk
    assert ("comments", "mp-004", "grp-0001") not in fake.calls

    out = skool_read.collect_mcp(WINS_URL, max_posts=2, now=AS_OF, transport=FakeMcp(), sleep=lambda s: None,
                                 refresh_days=0)
    assert out["counts"]["updated"] + out["counts"]["new"] == 2 and out["counts"]["pages"] == 1


def test_collect_mcp_statuses(data_dir, monkeypatch):
    logged_out = FakeMcp(pages={1: dict(_load("feed_page_1.json"), self=False)})
    assert _run(logged_out)["status"] == "logged_out"
    assert files.all_raw() == []

    out = _run(FakeMcp(fail_feed=[1]))
    assert out["status"] == "fetch_failed" and out["detail"] == "McpError: feed exit 1: boom"
    out = _run(FakeMcp(fail_feed=[2]))
    assert out["status"] == "fetch_failed" and out["counts"]["new"] == 4  # page 1 stays saved

    for path in files.raw_dir().glob("*.json"):
        path.unlink()
    out = _run(FakeMcp(fail_comments=["mp-001"]))
    assert out["status"] == "ok" and out["counts"]["thread_errors"] == 1
    kept = files.load_raw("mp-001")
    assert not kept["thread_fetched"] and kept["author_replies"] == []

    out = skool_read.collect_mcp("https://www.skool.com/makerschool?s=newest", transport=FakeMcp())
    assert out["status"] == "bad_url"
    assert skool_read.collect_mcp("https://example.com/x?c=1", transport=FakeMcp())["status"] == "bad_url"

    monkeypatch.setenv("SKOOL_MCP_CLIENT", str(data_dir / "missing" / "client.js"))
    out = skool_read.collect_mcp(WINS_URL)
    assert out["status"] == "mcp_unavailable" and "SKOOL_MCP_CLIENT" in out["detail"]


def test_a_second_run_leaves_every_source_hash_unchanged(data_dir):
    _run(FakeMcp())
    first = dict((r["post_id"], analyze.source_hash(r)) for r in files.all_raw())
    again = _run(FakeMcp())
    assert again["counts"]["updated"] == 6
    assert dict((r["post_id"], analyze.source_hash(r)) for r in files.all_raw()) == first

    thread = skool_read.thread_from_api2(_load("feed_page_1.json")["postTrees"][0], _load("comments_mp-001.json"))
    record = skool_read.record_from_tree(thread, "makerschool", "t", thread_fetched=True)
    assert [r["created_at"] for r in record["author_replies"]] == sorted(r["created_at"]
                                                                          for r in record["author_replies"])
    assert record["author_name"] == "Ann Example"


def test_the_transport_runs_the_script_and_parses_stdout(monkeypatch, tmp_path):
    client = tmp_path / "client.js"
    client.write_text("// fake", encoding="utf-8")
    seen = []

    def fake_run(argv, **kw):
        seen.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"self": True, "postTrees": []}), stderr="")

    monkeypatch.setattr(skool_read.subprocess, "run", fake_run)
    transport = skool_read.McpTransport(client=client, node="/opt/node")
    assert transport.feed("makerschool", "lab-1", 2) == {"self": True, "postTrees": []}
    transport.comments("mp-001", "grp-0001")
    assert seen[0][0] == ["/opt/node", str(skool_read.MCP_SCRIPT), str(client), "feed", "makerschool", "lab-1", "2"]
    assert seen[1][0][3:] == ["comments", "mp-001", "grp-0001"]
    assert seen[0][1]["timeout"] == 90 and "shell" not in seen[0][1]

    monkeypatch.setattr(skool_read.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 1, stdout="", stderr="HTTP 401 Unauthorized\n"))
    with pytest.raises(skool_read.McpError) as err:
        transport.feed("makerschool", "lab-1", 1)
    assert "HTTP 401" in str(err.value)
    monkeypatch.setattr(skool_read.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, stdout="not json", stderr=""))
    with pytest.raises(skool_read.McpError):
        transport.feed("makerschool", "lab-1", 1)


def test_the_fetch_script_only_reads():
    source = skool_read.MCP_SCRIPT.read_text(encoding="utf-8")
    for write in ("POST", "PUT", "PATCH", "DELETE", "posts_create", "posts_comment"):
        assert write not in source
    assert 'method: "GET"' in source and 'LIMIT = "25"' in source and "limit: LIMIT" in source


def test_the_cli_dispatches_collect_via_mcp(data_dir, monkeypatch):
    seen = {}

    def fake_collect_mcp(url, **kw):
        seen.update(kw, url=url)
        return {"status": "ok", "group": "makerschool", "category_url": url, "via": "mcp", "counts": {}}

    monkeypatch.setattr(skool_read, "collect_mcp", fake_collect_mcp)
    monkeypatch.setattr(skool_read, "collect", lambda *a, **k: pytest.fail("Playwright path used"))
    assert job.main(["collect", "--via", "mcp", "--url", WINS_URL, "--since", "2026-09-10",
                     "--max-pages", "12", "--max-posts", "400", "--no-threads"]) == 0
    assert seen == {"url": WINS_URL, "max_pages": 12, "max_posts": 400, "since": SINCE, "threads": False}
