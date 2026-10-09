"""Offer Intel (MAKER_SCHOOL_WINS_PLAN.md): parsing, the quote check, the
taxonomy, the ranking and the offline rehearsal. Made-up posts only
(jobs/tests/fixtures/offer_intel/); no Skool, no network, no billed call.
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shared import job_log, llm
from shared.paths import BASE_DIR
from services.offer_intel import analyze, extract, files, gate, rehearsal, rollup, skool_read, taxonomy
from jobs import offer_intel as job

FIX = BASE_DIR / "jobs" / "tests" / "fixtures" / "offer_intel"
AS_OF = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def _load(name):
    with open(FIX / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OFFER_INTEL_DIR", str(tmp_path / "offer_intel"))
    yield tmp_path / "offer_intel"
    llm.clear_fakes()


# ------------------------------------------------------------------ parsing
def test_a_record_keeps_the_root_post_and_only_the_authors_own_replies():
    props = _load("post_signed-a-dental-practice.json")
    record = skool_read.record_from_tree(skool_read.trees_from_props(props)[0], "makerschool", "t",
                                         thread_fetched=True)
    assert record["post_id"] == "p-001"
    assert record["author_id"] == "u-alpha"
    assert record["url"] == "https://www.skool.com/makerschool/signed-a-dental-practice"
    replies = [r["content"] for r in record["author_replies"]]
    assert replies == ["Leads came from Apollo, I targeted the practice owners directly."]
    assert "Congrats" not in json.dumps(record)


def test_a_merge_keeps_replies_the_feed_payload_did_not_carry():
    old = {"post_id": "p", "content": "old", "thread_fetched": True,
           "author_replies": [{"id": "r1", "content": "first answer", "created_at": "2026-09-01T00:00:00Z"}]}
    new = {"post_id": "p", "content": "edited", "thread_fetched": False, "author_replies": []}
    merged = skool_read.merge_records(old, new)
    assert merged["content"] == "edited"
    assert [r["id"] for r in merged["author_replies"]] == ["r1"]
    assert merged["thread_fetched"] is True


def test_skool_timestamps_with_nanoseconds_and_z_parse_on_python_39():
    stamp = skool_read.parse_time("2026-09-20T15:04:05.123456789Z")
    assert stamp == datetime(2026, 9, 20, 15, 4, 5, 123456, tzinfo=timezone.utc)
    assert skool_read.parse_time("2026-09-20T15:04:05Z").tzinfo is not None
    assert skool_read.parse_time("not a date") is None


def test_the_wins_category_is_found_in_the_payload():
    labels = skool_read.find_labels(_load("feed_page_1.json"))
    assert [lab["name"] for lab in labels] == ["General", "Help", "Wins"]
    assert [lab["id"] for lab in skool_read.wins_labels(labels)] == ["lab-wins"]


def test_page_urls_keep_the_category_and_set_the_page():
    url = "https://www.skool.com/makerschool?c=lab-wins"
    assert skool_read.page_url(url, 1) == url
    assert skool_read.page_url(url, 2) == "https://www.skool.com/makerschool?c=lab-wins&p=2"
    assert skool_read.page_url(url + "&p=5", 3) == "https://www.skool.com/makerschool?c=lab-wins&p=3"
    assert skool_read.group_from_url(url) == "makerschool"
    with pytest.raises(ValueError):
        skool_read.group_from_url("https://example.com/makerschool")


def test_a_thread_is_reread_only_while_young_or_never_read():
    now = AS_OF
    assert skool_read.needs_thread(None, now)
    young = {"thread_fetched": True, "created_at": (now - timedelta(days=3)).isoformat()}
    old = {"thread_fetched": True, "created_at": (now - timedelta(days=30)).isoformat()}
    assert skool_read.needs_thread(young, now)
    assert not skool_read.needs_thread(old, now)
    assert skool_read.needs_thread(dict(old, thread_fetched=False), now)


def test_a_screenshot_post_is_flagged_as_media():
    feed = _load("feed_page_1.json")
    by_id = dict((t["post"]["id"], t["post"]) for t in feed["postTrees"])
    assert skool_read.has_media(by_id["p-008"])
    assert not skool_read.has_media(by_id["p-001"])


def test_importing_the_reader_does_not_import_the_old_scraper():
    # execution/skool_scraper.py calls sys.exit(1) at import without Playwright.
    assert "skool_scraper" not in sys.modules


# ------------------------------------------------- the live walk, faked
class _FakePage(object):
    def __init__(self, pages, fail=()):
        self.pages, self.fail, self.url, self.visited = pages, set(fail), "", []

    async def goto(self, url, timeout=None):
        self.visited.append(url)
        if url in self.fail:
            raise TimeoutError(url)
        self.url = url


class _FakeContext(object):
    closed = False

    async def close(self):
        self.closed = True


class _FakeScraper(object):
    """Stands in for execution/skool_scraper.py: same three names collect uses."""
    TIMING = {"nav_timeout": 1, "page_load_wait": 0, "between_pages": (0, 0)}

    def __init__(self, page):
        self.page, self.context = page, _FakeContext()

    async def setup_auth(self, p, group, headless):
        return self.page, self.context

    async def _page_props(self, page):
        return page.pages.get(page.url, {})


class _FakePlaywright(object):
    async def __aenter__(self):
        return "pw"

    async def __aexit__(self, *exc):
        return False


WINS_URL = "https://www.skool.com/makerschool?c=lab-wins"


def _fake_site(monkeypatch, pages, fail=()):
    page = _FakePage(pages, fail)
    scraper = _FakeScraper(page)
    monkeypatch.setattr(skool_read, "_scraper", lambda: scraper)
    monkeypatch.setattr(skool_read, "_async_playwright", lambda: _FakePlaywright)
    return page, scraper


def _site():
    empty = {"self": {"name": "v"}, "postTrees": []}
    return {
        WINS_URL: _load("feed_page_1.json"),
        WINS_URL + "&p=2": empty, WINS_URL + "&p=3": empty,
        "https://www.skool.com/makerschool/signed-a-dental-practice": _load("post_signed-a-dental-practice.json"),
        "https://www.skool.com/makerschool/first-client": _load("post_first-client.json"),
    }


def test_collect_saves_every_post_and_reads_the_authors_replies(data_dir, monkeypatch):
    import asyncio
    page, scraper = _fake_site(monkeypatch, _site())
    out = asyncio.run(skool_read.collect(WINS_URL, max_pages=3, max_posts=40, now=AS_OF))
    assert out["status"] == "ok"
    assert out["counts"]["new"] == 12 and out["counts"]["threads_read"] == 2
    saved = dict((r["post_id"], r) for r in files.all_raw())
    assert len(saved) == 12
    assert saved["p-001"]["thread_fetched"] and "Apollo" in saved["p-001"]["author_replies"][0]["content"]
    assert saved["p-002"]["author_replies"][0]["content"].startswith("Cold email")
    assert not saved["p-007"]["thread_fetched"]  # no post page for it: kept from the feed
    assert scraper.context.closed
    # Two empty pages in a row end the walk.
    assert page.visited[-2:] == [WINS_URL + "&p=2", WINS_URL + "&p=3"]


def test_collect_stops_at_max_posts_and_counts_updates_on_a_rerun(data_dir, monkeypatch):
    import asyncio
    _fake_site(monkeypatch, _site())
    first = asyncio.run(skool_read.collect(WINS_URL, max_posts=5, now=AS_OF))
    assert first["counts"]["new"] == 5
    again = asyncio.run(skool_read.collect(WINS_URL, max_posts=40, now=AS_OF))
    assert (again["counts"]["new"], again["counts"]["updated"]) == (7, 5)


def test_collect_since_skips_old_posts(data_dir, monkeypatch):
    import asyncio
    _fake_site(monkeypatch, _site())
    out = asyncio.run(skool_read.collect(WINS_URL, since=datetime(2026, 9, 15, tzinfo=timezone.utc), now=AS_OF))
    kept = sorted(r["post_id"] for r in files.all_raw())
    assert kept == ["p-001", "p-002", "p-006", "p-007", "p-008", "p-012"]
    assert out["counts"]["skipped_old"] == 6


def test_collect_stops_cleanly_when_logged_out_or_a_page_times_out(data_dir, monkeypatch):
    import asyncio
    pages = _site()
    pages[WINS_URL] = dict(pages[WINS_URL], self=None)
    _fake_site(monkeypatch, pages)
    assert asyncio.run(skool_read.collect(WINS_URL, now=AS_OF))["status"] == "logged_out"
    assert files.all_raw() == []

    _fake_site(monkeypatch, _site(), fail=["https://www.skool.com/makerschool/first-client"])
    out = asyncio.run(skool_read.collect(WINS_URL, now=AS_OF))
    assert out["status"] == "ok" and out["counts"]["thread_errors"] == 1
    assert not files.load_raw("p-002")["thread_fetched"]

    _fake_site(monkeypatch, _site(), fail=[WINS_URL])
    assert asyncio.run(skool_read.collect(WINS_URL, now=AS_OF))["status"] == "fetch_failed"


# ------------------------------------------------------------- quote check
SOURCE = "Signed a dental office in Ohio. $3k setup and $1,500/mo. Sent 1,200 emails with Instantly."


def test_the_quote_check_drops_invented_facts_and_keeps_stated_ones():
    raw = {
        "industry": {"value": "dental office", "quote": "Signed a dental office in Ohio"},
        "setup_usd": {"value": 3000, "quote": "$3k setup"},
        "monthly_usd": {"value": 2000, "quote": "$1,500/mo"},
        "guarantee": {"value": "money back", "quote": "or your money back"},
        "tools": {"value": ["Instantly", "Smartlead"], "quote": "with Instantly"},
        "pricing_model": {"value": "subscription", "quote": "$1,500/mo"},
        "geo": None,
    }
    result = extract.verify(raw, SOURCE)
    assert extract.value(result, "industry") == "dental office"
    assert extract.value(result, "setup_usd") == 3000.0
    assert extract.value(result, "tools") == ["Instantly"]
    assert result["dropped"] == {"monthly_usd": "number_not_in_quote", "guarantee": "quote_not_in_post",
                                 "pricing_model": "not_allowed"}
    assert result["evidence_strength"] == "numbers"


def test_a_counted_value_must_rest_on_its_own_quote():
    source = "Signed a new client! Dentists in Ohio, we run reactivation for them."
    raw = {"industry": {"value": "dental", "quote": "Signed a new client!"},
           "mechanism": {"value": "database reactivation", "quote": "we run reactivation for them"},
           "geo": {"value": "Ohio", "quote": "Dentists in Ohio"}}
    result = extract.verify(raw, source)
    assert result["dropped"] == {"industry": "value_not_in_quote"}
    assert extract.value(result, "mechanism") == "database reactivation"
    assert extract.value(result, "geo") == "Ohio"
    assert extract.value_in_quote("dentists", "dental practices")
    assert extract.value_in_quote("IT", "anything")


def test_quotes_match_across_case_curly_quotes_and_an_ellipsis():
    source = "We" + chr(0x2019) + "re running a Database Reactivation campaign on their 6,000 old patients."
    assert extract.quote_in_source("we're running a database reactivation campaign", source)
    assert extract.quote_in_source("We're running ... 6,000 old patients", source)
    assert not extract.quote_in_source("running a review campaign", source)
    assert not extract.quote_in_source("a", source)


@pytest.mark.parametrize("text,expected", [
    ("$3k/mo", [3000.0]), ("$1,500 setup", [1500.0]), ("$1.5M pipeline", [1500000.0]),
    ("1.8% reply rate", [1.8]), ("3 months", [3.0]), ("5 grand", [5000.0]),
])
def test_numbers_are_read_with_their_scale(text, expected):
    assert extract.numbers_in(text) == expected


def test_a_post_with_no_numbers_but_a_screenshot_is_screenshot_only():
    assert extract.verify({}, "Best month yet.", has_media=True)["evidence_strength"] == "screenshot_only"
    assert extract.verify({}, "Best month yet.", has_media=False)["evidence_strength"] == "vague"



# Skool's markdown escapes "\(" in the post; the model copies them into a quote.
BAD_JSON = ('```json\n{"offer_one_line": {"value": "AI voice agent \\"Ava\\"", '
            '"quote": "built an AI voice agent \\(inbound\\) for a med spa"},\n'
            '"copy_angle": {"value": "line one\\nline two", "quote": "the client' + chr(0x2019) + 's go-to"},\n'
            '"list_source": {"value": "C:\\\\leads", "quote": "x"}}\n```')


def test_invalid_markdown_escapes_are_repaired_and_valid_escapes_decode():
    parsed = extract.parse_json(BAD_JSON)
    assert parsed["offer_one_line"]["quote"] == "built an AI voice agent \\(inbound\\) for a med spa"
    assert parsed["offer_one_line"]["value"] == 'AI voice agent "Ava"'
    assert parsed["copy_angle"]["value"] == "line one\nline two"
    assert parsed["copy_angle"]["quote"] == "the client" + chr(0x2019) + "s go-to"
    assert parsed["list_source"]["value"] == "C:\\leads"


def test_extract_keeps_a_field_whose_quote_carries_a_markdown_escape(data_dir):
    llm.register_fake("research", lambda s, u, j: BAD_JSON)
    record = {"post_id": "p1", "title": "Win", "content": "Just built an AI voice agent \\(inbound\\) for a med spa."}
    result = extract.extract(record)
    assert extract.value(result, "offer_one_line") == 'AI voice agent "Ava"'
    assert "offer_one_line" not in result["dropped"]


def test_garbage_from_the_model_is_an_llm_error():
    with pytest.raises(llm.LLMError):
        extract.parse_json("Sorry, I can't help with that.")
    with pytest.raises(llm.LLMError):
        extract.parse_json("[1, 2]")


def test_the_extract_prompt_pins_prices_to_one_client_and_defines_each_pricing_model():
    for rule in ("ONE client", "Contracted Revenue = $34,348", "$10k+ scope", "$5 flat job is one_off_build",
                 "setup_plus_retainer needs a stated setup fee", "takes the per-result model"):
        assert rule in extract.SYSTEM
    for model in extract.PRICING_MODELS:
        assert "  %s = " % model in extract.SYSTEM

# -------------------------------------------------------------------- gate
def test_the_gate_escalates_below_point_eight(data_dir):
    llm.register_fake("classify", lambda s, u, j: {"is_win": True, "win_type": "new_client",
                                                   "channel": "cold_email", "confidence": 0.5})
    llm.register_fake("escalate", lambda s, u, j: {"is_win": True, "win_type": "new_client",
                                                   "channel": "referral", "confidence": 0.9})
    verdict = gate.gate({"post_id": "x", "title": "t", "content": "c"})
    assert verdict["escalated"] and verdict["model_role"] == "escalate"
    assert verdict["channel"] == "referral"
    assert verdict["first_pass"]["confidence"] == 0.5


def test_the_gate_cleans_unknown_values(data_dir):
    llm.register_fake("classify", lambda s, u, j: {"is_win": "false", "win_type": "new_client",
                                                   "channel": "email", "confidence": "high"})
    llm.register_fake("escalate", lambda s, u, j: {"is_win": "false", "channel": "email", "confidence": 0.95})
    verdict = gate.gate({"post_id": "x", "title": "t", "content": "c"})
    assert verdict["is_win"] is False
    assert verdict["win_type"] == "other_win"
    assert verdict["channel"] == "unknown"


def test_the_prompts_forbid_guessing_the_channel_and_inventing_fields():
    assert "Never assume cold_email" in gate.SYSTEM
    assert "WORD FOR WORD" in extract.SYSTEM and "Never infer" in extract.SYSTEM


# ---------------------------------------------------------------- taxonomy
@pytest.mark.parametrize("text,kind,expected", [
    ("dental practices", "industries", "dental"),
    ("Orthodontist office", "industries", "dental"),
    ("med spa", "industries", "med_spa"),
    ("spanish language school", "industries", "education"),
    ("roofing contractor", "industries", "roofing"),
    ("staffing agency", "industries", "recruiting"),
    ("lawn care company", "industries", "landscaping"),
    ("personal injury law firm", "industries", "legal"),
    ("underwater basket weaving", "industries", "other"),
    ("", "industries", "unknown"),
    ("database reactivation campaign", "mechanisms", "lead_reactivation"),
    ("AI receptionist that answers missed calls", "mechanisms", "ai_voice"),
    ("missed call text back and speed to lead", "mechanisms", "speed_to_lead"),
    ("trigger-based outbound", "mechanisms", "trigger_outbound"),
    ("n8n workflow for invoicing", "mechanisms", "custom_automation"),
])
def test_taxonomy_examples(text, kind, expected):
    assert taxonomy.classify(text, kind) == expected


def test_a_missing_industry_falls_back_to_the_offer_line_but_never_overrides():
    fields = {"offer_one_line": {"value": "reactivation for HVAC companies", "quote": "q"}}
    assert taxonomy.normalize(fields)["industry"] == "hvac"
    fields["industry"] = {"value": "dental", "quote": "q"}
    assert taxonomy.normalize(fields)["industry"] == "dental"


# ------------------------------------------------------------------ rollup
def _row(pid, author, industry, mechanism, days_ago, channel="cold_email"):
    return {"post_id": pid, "author_id": author, "author_name": author, "url": "u/%s" % pid,
            "posted_at": (AS_OF - timedelta(days=days_ago)).isoformat(), "industry": industry,
            "mechanism": mechanism, "industry_label": industry, "mechanism_label": mechanism,
            "channel": channel, "evidence_strength": "vague", "setup_usd": None, "monthly_usd": None,
            "deal_usd": None}


def test_rank_counts_different_winners_not_posts():
    rows = [_row("a%d" % i, "prolific", "dental", "ai_voice", i) for i in range(1, 6)]
    rows += [_row("b1", "m1", "hvac", "lead_reactivation", 2), _row("b2", "m2", "hvac", "lead_reactivation", 3)]
    ranked = rollup.patterns(rows, AS_OF)
    assert [(p["industry"], p["winners"], p["wins"]) for p in ranked] == [("hvac", 2, 2), ("dental", 1, 5)]


def test_trend_compares_the_last_30_days_with_the_30_before():
    rows = [_row("a", "m1", "dental", "ai_voice", 5), _row("b", "m2", "dental", "ai_voice", 40),
            _row("c", "m3", "dental", "ai_voice", 45)]
    item = rollup.patterns(rows, AS_OF)[0]
    assert (item["wins_30d"], item["wins_prev_30d"], item["trend"]) == (1, 2, "fading")


def test_crowded_patterns_are_flagged_and_never_picked():
    rows = [_row("c%d" % i, "m%d" % i, "dental", "ai_voice", i) for i in range(1, 7)]
    rows += [_row("q1", "x1", "hvac", "lead_reactivation", 3), _row("q2", "x2", "hvac", "lead_reactivation", 4)]
    ranked = rollup.patterns(rows, AS_OF)
    assert ranked[0]["crowded"] and ranked[0]["industry"] == "dental"
    assert [p["industry"] for p in rollup.candidates(ranked)] == ["hvac"]


def test_single_winner_picks_are_marked_weak():
    rows = [_row("a", "m1", "dental", "ai_voice", 2)]
    picks = rollup.candidates(rollup.patterns(rows, AS_OF))
    assert picks and picks[0]["weak"] is True


def test_a_win_with_nothing_stated_is_counted_but_not_ranked():
    rows = [_row("a", "m1", "unknown", "unknown", 2), _row("b", "m2", "dental", "unknown", 2)]
    ranked = rollup.patterns(rows, AS_OF)
    assert [p["industry"] for p in ranked] == ["dental"]
    assert rollup.unstated(rows) == 1


def test_the_fit_flag_marks_what_we_already_have_proof_for():
    rows = [_row("a", "m1", "roofing", "lead_reactivation", 2), _row("b", "m2", "dental", "ai_voice", 2)]
    fits = dict((p["industry"], p["fit"]) for p in rollup.patterns(rows, AS_OF))
    assert fits == {"roofing": "mechanism+industry", "dental": ""}



def test_price_medians_read_only_one_client_wins():
    total = dict(_row("a", "m1", "dental", "ai_voice", 2), win_type="revenue_milestone", deal_usd=34348)
    signed = dict(_row("b", "m2", "dental", "ai_voice", 3), win_type="new_client", deal_usd=1500)
    item = rollup.patterns([total, signed], AS_OF)[0]
    assert (item["median_deal_usd"], item["wins"]) == (1500.0, 2)

# ---------------------------------------------------------- paid-call gate
def test_analyze_refuses_billed_calls_without_the_switch(data_dir, monkeypatch):
    monkeypatch.delenv("LLM_FAKE", raising=False)
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    files.save_raw(rehearsal.fixture_records()[0])
    with pytest.raises(analyze.PaidCallsOff):
        analyze.run(files.all_raw())
    assert job.main(["analyze", "--sample", "1"]) == 2
    assert files.all_analyzed() == []


def test_preflight_prices_the_run_and_spends_nothing(data_dir, monkeypatch):
    monkeypatch.delenv("LLM_FAKE", raising=False)
    for record in rehearsal.fixture_records():
        files.save_raw(record)
    ledger = llm.ledger_path()
    before = ledger.read_text() if ledger.exists() else ""
    out = job.do_analyze(sample=5, force=False, preflight=True, now=AS_OF)
    assert out["status"] == "preflight"
    assert out["estimate"]["posts"] == 5
    assert 0 < out["estimate"]["typical_usd"] < out["estimate"]["worst_usd"] < 1
    assert (ledger.read_text() if ledger.exists() else "") == before
    assert files.all_analyzed() == []


def test_only_new_or_changed_posts_are_analyzed_again(data_dir, monkeypatch):
    monkeypatch.setenv("LLM_FAKE", "1")
    rehearsal.install_fakes()
    records = rehearsal.fixture_records()
    for record in records:
        files.save_raw(record)
    analyze.run(analyze.pending(files.all_raw()), now=AS_OF)
    assert analyze.pending(files.all_raw()) == []
    changed = dict(records[0], author_replies=records[0]["author_replies"] + [
        {"id": "new", "content": "It was a pay per meeting deal.", "created_at": "2026-09-23T00:00:00Z"}])
    files.save_raw(changed)
    assert [r["post_id"] for r in analyze.pending(files.all_raw())] == [changed["post_id"]]


# --------------------------------------------------------------- rehearsal
def _job_log_rows():
    path = job_log.job_log_path()
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("job") == "offer_intel"]


def test_the_rehearsal_runs_the_whole_pipeline_offline(monkeypatch):
    monkeypatch.setenv("LLM_FAKE", "1")
    monkeypatch.setenv("OFFER_INTEL_DIR", "restored-after-test")
    try:
        out = job.do_rehearse()
    finally:
        llm.clear_fakes()
    assert out["posts"] == 12
    counts = out["analyze"]["counts"]
    assert (counts["wins"], counts["not_wins"], counts["escalated"], counts["fields_dropped"]) == (11, 1, 1, 2)
    report = out["report"]
    assert report["picks"][0] == "Dental x Lead / database reactivation"
    assert "(not stated)" not in report["push_line"]
    digest = Path(report["files"]["digest"]).read_text(encoding="utf-8")
    assert "Market research only" in digest
    assert "2 different winners" in digest
    assert "Member" not in report["push_line"]  # no member names in the push
    hand_check = Path(report["files"]["hand_check"]).read_text(encoding="utf-8")
    assert "Dropped by the quote check: guarantee (quote_not_in_post), monthly_usd (number_not_in_quote)" \
        in hand_check
    with open(report["files"]["wins_csv"], encoding="utf-8") as fh:
        wins = list(csv.DictReader(fh))
    medspa = [w for w in wins if w["post_id"] == "p-010"][0]
    assert medspa["monthly_usd"] == "" and medspa["guarantee"] == ""
    assert medspa["industry"] == "med_spa" and medspa["mechanism"] == "review_generation"
    statuses = [r["status"] for r in _job_log_rows()]
    assert {"analyze_ok", "report_ok", "rehearse_ok"} <= set(statuses)


# ------------------------------------------------------------- guardrails
def test_no_copy_path_reads_offer_intel():
    """Their proof is not our proof: nothing that writes emails or proof lines
    may import this research."""
    for folder in ("services/reply_engine", "services/experiments", "services/upwork_followup",
                   "services/list_factory", "services/metrics", "services/retro"):
        for path in (BASE_DIR / folder).rglob("*.py"):
            assert "offer_intel" not in path.read_text(encoding="utf-8"), path


def test_offer_intel_never_writes_to_skool():
    source = (BASE_DIR / "services" / "offer_intel" / "skool_read.py").read_text(encoding="utf-8")
    for write in ("posts_create", "posts_comment", ".click(", ".fill(", ".type(", "method=\"POST\""):
        assert write not in source
