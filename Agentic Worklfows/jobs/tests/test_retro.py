"""Tests for O6, the Friday retro packet (brief A10).

Everything runs offline against ``services/retro/fixtures/week_2026-09.json``,
which is a real read-only pull from the live Instantly workspace on
2026-09-22, and ``fireflies_emails_2026-09.json``, which is a real read-only
pull from Lorenzo's Gmail on the same night. No test touches the network, and
the safety tests assert the job stays read-only even with the live flags set.
"""
import json
import os
from datetime import datetime

import pytest
import pytz

from shared import job_log as job_log_mod
from shared import llm
from shared.store import JsonFileStore

from jobs import retro_packet
from services.retro import collect as collect_mod
from services.retro import fakes, lessons, metrics, packet, recaps, render, scorecard, sources, weeks

TZ = pytz.timezone("America/Chicago")
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "services", "retro", "fixtures")

# Friday 16:00 CT of the week the recorded data covers.
FRIDAY = TZ.localize(datetime(2026, 9, 18, 16, 0))


@pytest.fixture
def week_fixture():
    with open(os.path.join(FIXTURES, "week_2026-09.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def fireflies():
    with open(os.path.join(FIXTURES, "fireflies_emails_2026-09.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)["messages"]


@pytest.fixture
def week(week_fixture):
    return collect_mod.collect_week(FRIDAY, fixtures=week_fixture)


@pytest.fixture(autouse=True)
def _clear_fakes():
    llm.clear_fakes()
    yield
    llm.clear_fakes()


# ----------------------------------------------------------------- windows
def test_both_windows_stop_on_the_same_weekday_so_friday_is_not_a_collapse():
    this_week, last_week = weeks.windows(FRIDAY)
    assert this_week.dates() == ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
    assert last_week.dates() == ["2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"]
    # Same number of days, or the week-over-week delta is meaningless.
    assert len(this_week.dates()) == len(last_week.dates())
    assert this_week.partial_last_day is True
    assert "last day partial" in this_week.describe()


def test_a_run_after_the_send_window_closes_is_not_marked_partial():
    late = TZ.localize(datetime(2026, 9, 18, 19, 30))
    this_week, _ = weeks.windows(late)
    assert this_week.partial_last_day is False
    assert "partial" not in this_week.describe()


def test_weeks_back_shifts_both_windows():
    this_week, last_week = weeks.windows(FRIDAY, weeks_back=1)
    assert this_week.start_date == "2026-09-07"
    assert last_week.start_date == "2026-08-31"
    assert weeks.week_key(this_week) == "2026-09-07"


# ----------------------------------------------------------------- metrics
def test_replies_automatic_is_not_a_subset_so_it_is_never_subtracted(week_fixture):
    """The bug this pins: `replies` already excludes auto-responders.

    17 recorded account-daily rows carry replies=0 with replies_automatic>=1,
    which is impossible if automatic were a subset. Subtracting reported 2 real
    replies for a week that really had 17.
    """
    rows = week_fixture["account_rows"]
    contradictions = [r for r in rows if r.get("replies_automatic", 0) > r.get("replies", 0)]
    assert contradictions, "fixture no longer proves the point; re-pull it"

    window = weeks.Window(TZ.localize(datetime(2026, 9, 14)), TZ.localize(datetime(2026, 9, 18)),
                          "test")
    totals = metrics.sum_daily(rows, window)
    assert metrics.real_replies(totals) == totals["unique_replies"]
    assert metrics.real_replies(totals) == 17
    assert metrics.auto_replies(totals) == 15
    # The old, wrong formula.
    assert totals["unique_replies"] - totals["unique_replies_automatic"] == 2


def test_real_reply_rate_matches_the_hand_measured_week(week_fixture):
    """Sept 15-21: 1,800 sent, 22 replies, 19 of them from distinct leads.

    The docstring, the runbook and this test used to justify the formula with
    "22/1800 is 1.22%, exactly the rate measured by hand" while
    ``metrics.real_replies`` returned ``unique_replies`` and the packet printed
    1.06%. Nothing asserted on the number the packet actually renders, so the
    two drifted. Section 6's 1% line is a per-lead rule, so unique is the right
    numerator; the three leads who replied twice are the whole difference.
    """
    window = weeks.Window(TZ.localize(datetime(2026, 9, 15)), TZ.localize(datetime(2026, 9, 21)),
                          "test")
    totals = metrics.sum_daily(week_fixture["account_rows"], window)
    assert totals["sent"] == 1800
    assert totals["replies"] == 22            # raw: 1.22%, the hand-measured figure
    assert totals["unique_replies"] == 19     # per lead: what the rule is about

    # This is the number the funnel row prints, so this is the number pinned.
    assert metrics.real_replies(totals) == 19
    assert abs(metrics.real_replies(totals) / totals["sent"] - 0.0106) < 0.0002


def test_statuses_are_cumulative_so_booked_is_a_subset_of_positives():
    window = weeks.Window(TZ.localize(datetime(2026, 9, 14)), TZ.localize(datetime(2026, 9, 18)),
                          "test")
    leads = [
        {"lt_interest_status": 1, "timestamp_last_interest_change": "2026-09-16T10:00:00Z"},
        {"lt_interest_status": 2, "timestamp_last_interest_change": "2026-09-17T10:00:00Z"},
        {"lt_interest_status": 4, "timestamp_last_interest_change": "2026-09-18T10:00:00Z"},
        {"lt_interest_status": -4, "timestamp_last_interest_change": "2026-09-18T11:00:00Z"},
        {"lt_interest_status": -1, "timestamp_last_interest_change": "2026-09-18T11:00:00Z"},
        # Outside the window: must not count at all.
        {"lt_interest_status": 4, "timestamp_last_interest_change": "2026-09-01T10:00:00Z"},
    ]
    counts = metrics.count_statuses(leads, window)
    assert counts == {"positives": 3, "booked": 2, "held": 1, "closes": 1,
                      "no_shows": 1, "negative": 1}


def test_an_unreadable_ghl_leaves_revenue_none_and_never_zero():
    window = weeks.Window(TZ.localize(datetime(2026, 9, 14)), TZ.localize(datetime(2026, 9, 18)),
                          "test")
    assert metrics.count_opportunities(None, window, {}) is None
    # An empty list, on the other hand, is a real zero.
    assert metrics.count_opportunities([], window, {}) == {
        "proposals": 0.0, "closes": 0.0, "revenue": 0.0,
        "undated": {"proposals": 0, "closes": 0}}

    funnel = metrics.build_funnel(
        {"accounts": {"sent": 10}, "statuses": {}, "opps": None},
        {"accounts": {"sent": 10}, "statuses": {}, "opps": None})
    revenue = metrics.by_key(funnel)["revenue"]
    assert revenue.this_week is None
    assert revenue.available is False
    assert "token" in revenue.note


def test_only_metrics_that_actually_moved_are_offered_to_the_model():
    funnel = [
        metrics.Metric("a", "A", 5, 5),
        metrics.Metric("b", "B", 6, 5),
        metrics.Metric("c", "C", None, 5),
    ]
    assert [m.key for m in metrics.moved(funnel)] == ["b"]


# ----------------------------------------------------------------- recaps
def test_the_daily_brief_is_parsed_into_sections_and_cited_items(fireflies):
    window = weeks.windows(FRIDAY)[0]
    parsed = recaps.parse_messages(fireflies, window=window)
    assert len(parsed["briefs"]) == 1
    assert sorted(parsed["briefs"][0]["sections"]) == ["ACTION ITEMS", "POPULAR TOPICS"]
    texts = [i["text"] for i in parsed["items"]]
    assert any("$2,000 retainer" in t for t in texts)
    # Sub-headings are captured, not glued into the bullet text.
    assert {i["subsection"] for i in parsed["items"]} >= {"Commercial Terms", "Expansion Plans"}
    assert not any("#####" in t for t in texts)
    assert not any("View In App" in t for t in texts)
    # Every item is indexed so the model can only cite one that exists.
    assert [i["index"] for i in parsed["items"]] == list(range(len(parsed["items"])))


def test_open_items_are_tagged_and_the_prefix_is_stripped(fireflies):
    parsed = recaps.parse_messages(fireflies, window=weeks.windows(FRIDAY)[0])
    opens = recaps.tagged(parsed["items"], "open")
    assert opens
    assert all(not t["text"].lower().startswith("open:") for t in opens)
    assert any("payment timing" in t["text"] for t in opens)


def test_a_meeting_recap_email_carries_no_notes_only_a_link(fireflies):
    parsed = recaps.parse_messages(fireflies, window=weeks.windows(FRIDAY)[0])
    assert len(parsed["calls"]) == 2
    assert all(c["url"].startswith("https://app.fireflies.ai/view/") for c in parsed["calls"])
    assert all(r["link_only"] for r in parsed["recaps"])
    assert all(r["items"] == [] for r in parsed["recaps"])


def test_non_fireflies_mail_and_marketing_blasts_are_skipped(fireflies):
    parsed = recaps.parse_messages(fireflies, window=weeks.windows(FRIDAY)[0])
    assert parsed["skipped"] >= 2  # the Stripe receipt and the Fireflies marketing email


def test_an_empty_daily_brief_says_so_instead_of_inventing_items(fireflies):
    empty = [m for m in fireflies if m["id"] == "1a0bf0386c955ab7"]  # the 09-20 brief
    window = weeks.windows(TZ.localize(datetime(2026, 9, 20, 20, 0)))[0]
    assert window.contains_date("2026-09-20")
    parsed = recaps.parse_messages(empty, window=window)
    assert parsed["items"] == []
    assert "empty" in parsed["note"]


# ------------------------------------------------------------------ rubric
def _context(week):
    from services.retro.render import fmt_delta, fmt_number

    return lessons.build_context(
        funnel=week.funnel,
        moved_keys=[m.key for m in metrics.moved(week.funnel)],
        changes=week.changes.get("notable") or [],
        recap_items=week.recaps.get("items") or [],
        campaign_rows=week.campaign_rows,
        thresholds=collect_mod.SECTION6_THRESHOLDS,
        fmt_number=fmt_number, fmt_delta=fmt_delta, owners=packet.OWNERS,
    )


NEXT_WEEK = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24",
             "2026-09-25", "2026-09-26", "2026-09-27"]


def test_the_rubric_rejects_every_item_of_a_generic_answer(week):
    context = _context(week)
    result = lessons.propose(context, NEXT_WEEK, week.recaps["items"],
                             complete=lambda *a, **k: fakes.generic("", "", True))
    assert result["lessons"] == []
    assert result["bets"] == []
    assert result["wins"] == []
    assert result["objections"] == []
    assert result["short"] is True
    reasons = " | ".join(r["reason"] for r in result["rejections"])
    assert "is not in the funnel table" in reasons        # metric "vibes"
    assert "is not a value the table prints" in reasons   # number 999999
    assert "generic advice" in reasons                    # keep doing what is working
    assert "owner" in reasons
    assert "is not inside next week" in reasons           # bet dated 2099
    assert "outside the week's call items" in reasons     # cite 9999


def test_the_rubric_accepts_a_grounded_answer(week):
    context = _context(week)
    result = lessons.propose(
        context, NEXT_WEEK, week.recaps["items"],
        complete=lambda *a, **k: fakes.compliant(context, NEXT_WEEK, week.recaps["items"])("", "", True))
    assert len(result["lessons"]) == 3
    assert len(result["bets"]) == 3
    assert result["rejections"] == []
    assert result["short"] is False
    for lesson in result["lessons"]:
        assert lesson["metric"] in context["moved"]
        assert lesson["owner"] == "Lorenzo"


@pytest.mark.parametrize("mutation,expected", [
    ({"metric": "nope"}, "is not in the funnel table"),
    ({"number": "12345"}, "is not a value the table prints"),
    ({"cite": ""}, "cause cites nothing"),
    ({"cite": "deadbeef"}, "is not a commit, campaign or call item"),
    ({"action": "Keep doing what is working"}, "generic advice"),
    ({"action": "Send more emails"}, "no target number and no date"),
    ({"action": "We should send 200 more emails"}, "does not start with a verb"),
    ({"owner": "the intern"}, "owner"),
    ({"cause": "x"}, "no cause given"),
])
def test_each_rubric_rule_fires_on_its_own(week, mutation, expected):
    context = _context(week)
    good = fakes.compliant(context, NEXT_WEEK, week.recaps["items"])("", "", True)["lessons"][0]
    broken = dict(good)
    broken.update(mutation)
    reasons = " | ".join(lessons.validate_lesson(broken, context))
    assert expected in reasons


def test_a_lesson_about_a_metric_that_did_not_move_is_rejected(week):
    context = _context(week)
    still = [k for k in context["metrics"] if k not in context["moved"]]
    assert still, "the fixture week has no flat metric to test with"
    good = fakes.compliant(context, NEXT_WEEK, week.recaps["items"])("", "", True)["lessons"][0]
    broken = dict(good, metric=still[0])
    assert any("did not move" in r for r in lessons.validate_lesson(broken, context))


def test_the_expensive_model_is_called_at_most_twice(week):
    context = _context(week)
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        return fakes.generic("", "", True)

    result = lessons.propose(context, NEXT_WEEK, week.recaps["items"], complete=counting)
    assert len(calls) == lessons.MAX_CALLS == 2
    assert result["calls"] == 2


def test_a_model_that_raises_does_not_kill_the_packet(week):
    context = _context(week)

    def boom(*args, **kwargs):
        raise RuntimeError("overloaded")

    result = lessons.propose(context, NEXT_WEEK, week.recaps["items"], complete=boom)
    assert result["lessons"] == []
    assert "overloaded" in result["error"]
    section = packet.lessons_section(result)
    assert "model call failed" in section.note


# ------------------------------------------------------------------ render
def test_rates_are_always_rendered_as_fractions():
    assert render.fmt_number(0.0122, "%") == "1.22%"
    assert render.fmt_number(1.0, "%") == "100.00%"          # not 1.00%
    assert render.fmt_number(None, "%") == "not available"
    assert render.fmt_delta(0.02, 0.01, "%") == "+1.00pp"
    assert render.fmt_delta(5, None) == "not available"      # never guesses a direction
    assert render.fmt_delta(5, 0) == "new"
    assert render.fmt_delta(0, 0) == "flat"
    assert render.fmt_delta(300, 300) == "flat"              # not "+0"
    assert render.fmt_delta(0.0033, 0.0, "%") == "+0.33pp"   # a rate never reads "new"
    assert render.fmt_delta(1200, 1000, "$") == "+$200"


def test_client_copy_rules_catch_what_the_offer_sheet_bans():
    bad = "We used automation to double your pipeline! A real win — congratulations."
    problems = render.check_client_copy(bad)
    assert "contains an em dash" in problems
    assert "contains an exclamation mark" in problems
    assert any("automation" in p for p in problems)
    assert "is not signed Lorenzo" in problems
    # Word boundaries: "domain" must not trip the "ai" rule.
    assert render.check_client_copy("Your domain warmed up nicely. Lorenzo") == []


def test_the_scorecard_refuses_to_render_copy_that_breaks_the_rules(week):
    card = scorecard.build_client_scorecard(week, "Test Client", campaign_keys=["cleaning_reactivation"],
                                            wins=["We ran the automation for you"])
    with pytest.raises(render.ClientCopyError):
        scorecard.render_client_scorecard(card)


def test_the_scorecard_and_the_packet_share_one_renderer(week):
    """A12 gets the same numbers, filtered, through the same code."""
    card = scorecard.build_client_scorecard(week, "Shining Armor Cleaning",
                                            campaign_keys=["cleaning_reactivation"])
    markdown = scorecard.render_client_scorecard(card)
    assert markdown.startswith("# Shining Armor Cleaning, week of 2026-09-14")
    numbers = scorecard.scorecard_numbers(week, ["cleaning_reactivation"])
    assert numbers["sent"]["value"] == week.per_campaign["this"]["cleaning_reactivation"]["sent"]
    # The client card never shows the internal "Source" column.
    assert "accounts/analytics/daily" not in markdown
    # Nothing unmeasured is shown as a zero.
    assert "Revenue attributed" not in markdown.split("Not reported")[0]


# ----------------------------------------------------------------- sources
def test_git_commits_are_split_into_notable_and_machine_noise():
    grouped = sources.group_commits([
        {"hash": "a" * 40, "subject": "Vault: your_thing via compiler engine"},
        {"hash": "b" * 40, "subject": "Vault: other via compiler engine"},
        {"hash": "c" * 40, "subject": "Phase 1 sales engine, reviewed"},
    ])
    assert [c["subject"] for c in grouped["notable"]] == ["Phase 1 sales engine, reviewed"]
    assert grouped["rolled_up"] == {"Vault": 2}
    assert grouped["total"] == 3


def test_a_missing_rize_export_degrades_with_a_reason(monkeypatch):
    monkeypatch.delenv(sources.RIZE_ENV, raising=False)
    source = sources.rize_hours()
    assert source.ok is False
    assert "RIZE_EXPORT_PATH" in source.reason
    assert source.value == {}


def test_rize_durations_use_the_column_unit_not_the_magnitude(tmp_path):
    csv_path = tmp_path / "rize.csv"
    csv_path.write_text("Category,Duration\nSales,1:30:00\nFulfillment,2.5\n", encoding="utf-8")
    source = sources.rize_hours(str(csv_path))
    assert source.ok is True
    assert abs(source.value["Sales"] - 1.5) < 1e-6
    assert abs(source.value["Fulfillment"] - 2.5) < 1e-6

    minutes = tmp_path / "rize_minutes.csv"
    minutes.write_text("Category,Duration (minutes)\nSales,45\n", encoding="utf-8")
    assert abs(sources.rize_hours(str(minutes)).value["Sales"] - 0.75) < 1e-6


def test_a_missing_staged_recap_pull_degrades_and_names_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv(sources.RECAPS_ENV, str(tmp_path / "nothing.json"))
    source = sources.staged_recaps()
    assert source.ok is False
    assert "Gmail connector" in source.reason


# ------------------------------------------------------------------- packet
def test_the_packet_names_its_caveats_instead_of_hiding_them(week):
    proposal = {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": [],
                "calls": 0, "short": True}
    pkt = packet.build_internal_packet(week, proposal, NEXT_WEEK)
    markdown = render.render_markdown(pkt)
    assert "Read this before you trust a number" in markdown
    assert "no GHL Private Integration token" in markdown
    assert "counted whole in both weeks" in markdown
    assert "No lesson passed the rubric this week." in markdown


def test_rejected_proposals_are_printed_not_deleted(week):
    context = _context(week)
    proposal = lessons.propose(context, NEXT_WEEK, week.recaps["items"],
                               complete=lambda *a, **k: fakes.generic("", "", True))
    markdown = render.render_markdown(packet.build_internal_packet(week, proposal, NEXT_WEEK))
    assert "Appendix: rejected by the rubric" in markdown
    assert "Keep doing what is working" in markdown


def test_inbox_verdicts_follow_the_section_6_rule():
    """The rule fires, but only when the volume behind it can carry it.

    At 100 sends the 1% reply line IS one reply, so a genuinely healthy 1.2%
    inbox shows zero about a third of the time. A verdict is "remove" only when
    the 95% range clears the line; the point estimate crossing it is "watch".
    """
    verdicts = packet.inbox_verdicts([
        ["badbounce@x.com", 400.0, 20.0, 0.05, 8.0, 0.02],   # 5% bounce on 400: real
        ["dead@x.com", 400.0, 2.0, 0.005, 0.0, 0.0],         # 0 replies in 400: real
        ["unlucky@x.com", 100.0, 0.0, 0.0, 0.0, 0.0],        # 0 replies in 100: noise
        ["threebounces@x.com", 100.0, 3.0, 0.03, 2.0, 0.02],  # 3 bounces in 100: noise
        ["fine@x.com", 400.0, 2.0, 0.005, 8.0, 0.02],
        ["new@x.com", 20.0, 0.0, 0.0, 0.0, 0.0],             # not enough data
    ])
    by_email = dict((v["email"], v) for v in verdicts)
    assert by_email["badbounce@x.com"]["verdict"] == "remove"
    assert "bounce" in by_email["badbounce@x.com"]["why"]
    assert by_email["dead@x.com"]["verdict"] == "remove"
    assert "1%" in by_email["dead@x.com"]["why"]
    assert by_email["unlucky@x.com"]["verdict"] == "watch"
    assert by_email["threebounces@x.com"]["verdict"] == "watch"
    assert by_email["fine@x.com"]["verdict"] == "ok"
    assert by_email["new@x.com"]["verdict"] == "not enough data"


def test_the_inbox_audit_does_not_flag_a_healthy_recorded_week(week):
    """The measured state of the recorded week is 1.2% bounce and 1.2% real
    replies with no inbox failing a Section 6 threshold. The audit used to name
    5 of the 12 inboxes as removals, 42% of the sending capacity."""
    verdicts = packet.inbox_verdicts(week.inbox_rows)
    assert verdicts, "the recorded week has no per-inbox rows"
    removes = [v["email"] for v in verdicts if v["verdict"] == "remove"]
    assert removes == []
    markdown = render.render_markdown(packet.build_internal_packet(
        week, {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}, []))
    assert "cross a Section 6 line" not in markdown


def test_the_inbox_audit_runs_over_the_trailing_pull_not_the_partial_week(week):
    """One partial week is ~100 sends an inbox; the audit uses what was pulled."""
    assert week.audit_window.start_date == week.last_window.start_date
    # The run day is partial at 16:00 CT and is dropped.
    assert week.audit_window.end_date < week.this_window.end_date
    sends = [row[1] for row in week.inbox_rows]
    assert min(sends) > 125, "the audit window is no wider than one week"


def test_campaign_verdicts_wait_for_the_1000_send_line(week):
    verdicts = packet.campaign_verdicts(week.campaign_totals)
    assert verdicts
    assert all(v["verdict"] == "no verdict yet" for v in verdicts)
    assert all("the first verdict line is 1000" in v["why"] for v in verdicts)


def test_the_skool_draft_obeys_the_punctuation_and_signature_rules(week):
    proposal = {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}
    draft = packet.skool_draft(week, proposal)
    assert render.check_copy(draft["body"], ban_words=False) == []
    assert draft["body"].rstrip().endswith("Lorenzo")
    assert "invent one" in draft["body"]  # it says nothing passed rather than padding


# ---------------------------------------------------------------------- job
def _run_job(argv, week_fixture, tmp_path, store=None, now=FRIDAY):
    return retro_packet.main(argv, now=now, store=store or JsonFileStore(str(tmp_path / "s.json")))


def test_dry_run_writes_no_file_stages_no_post_and_leaves_the_store_alone(week_fixture, tmp_path):
    store = JsonFileStore(str(tmp_path / "s.json"))
    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=True)
    assert summary["path"] is None
    assert summary["skool"] is None
    assert store.get(retro_packet._claim_key("2026-09-14")) is None


def test_a_real_run_writes_one_file_and_stages_exactly_one_skool_would_do(
        week_fixture, tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    store = JsonFileStore(str(tmp_path / "s.json"))
    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                               out_dir=str(tmp_path / "out"))
    assert os.path.exists(summary["path"])
    assert summary["path"].endswith("retro_2026-09-14.md")

    shadow = job_log_mod.read_shadow_log(tmp_path / "shadow.jsonl")
    skool = [r for r in shadow if r["system"] == "skool"]
    assert len(skool) == 1
    assert skool[0]["action"] == "post_create"
    assert skool[0]["payload"]["posting"] == "manual, by Lorenzo, after editing"
    # And nothing else was even proposed to a live system.
    assert [r["system"] for r in shadow] == ["skool"]


def test_the_job_never_posts_to_skool_even_with_the_live_flags_set(
        week_fixture, tmp_path, monkeypatch, live_mode):
    """The safety test. MODE=live plus ALLOW_LIVE_WRITES=1 still stages only.

    It must not open a ``live_write_intent`` Job_Log row either: this job never
    closes one, so an open intent would sit in the reconciliation forever.
    """
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    store = JsonFileStore(str(tmp_path / "s.json"))
    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                               out_dir=str(tmp_path / "out"))
    assert summary["skool"]["system"] == "skool"
    shadow = job_log_mod.read_shadow_log(tmp_path / "shadow.jsonl")
    assert [r["system"] for r in shadow] == ["skool"]
    if os.path.exists(str(tmp_path / "job_log.csv")):
        with open(str(tmp_path / "job_log.csv"), "r", encoding="utf-8") as handle:
            assert "live_write_intent" not in handle.read()


def test_the_expensive_model_runs_once_a_week_however_often_the_job_runs(week_fixture, tmp_path):
    store = JsonFileStore(str(tmp_path / "s.json"))
    calls = []

    def counting_complete(role, system, user, **kwargs):
        calls.append(role)
        context = _context(collect_mod.collect_week(FRIDAY, fixtures=week_fixture))
        return fakes.compliant(context, NEXT_WEEK)("", "", True)

    first = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                             complete=counting_complete, out_dir=str(tmp_path / "out"))
    second = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                              complete=counting_complete, out_dir=str(tmp_path / "out"))
    assert len(calls) == 1
    assert first["cached_proposal"] is False
    assert second["cached_proposal"] is True
    assert second["lessons"] == first["lessons"]

    third = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                             complete=counting_complete, refresh=True,
                             out_dir=str(tmp_path / "out"))
    assert len(calls) == 2
    assert third["cached_proposal"] is False


def test_no_llm_renders_the_numbers_and_says_the_lessons_are_missing(week_fixture, tmp_path):
    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=None, dry_run=True,
                               skip_llm=True)
    assert summary["model_calls"] == 0
    assert summary["lessons"] == 0
    assert "Emails sent" in summary["markdown"]


def test_the_cli_dry_run_writes_one_job_log_row_and_no_file(week_fixture, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    fixture_path = os.path.join(FIXTURES, "week_2026-09.json")
    code = retro_packet.main(
        ["--dry-run", "--fixtures", "--fixtures-path", fixture_path,
         "--as-of", "2026-09-18T16:00:00-05:00"],
        store=JsonFileStore(str(tmp_path / "s.json")))
    assert code == 0
    out = capsys.readouterr().out
    assert "dry run: nothing written" in out
    # --dry-run redirects the logs to a scratch dir, so the real Job_Log is untouched.
    assert not os.path.exists(str(tmp_path / "job_log.csv"))


def test_the_cli_renders_the_client_scorecard_from_the_same_week(week_fixture, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=None, dry_run=False,
                               out_dir=str(tmp_path / "out"), client="Shining Armor Cleaning",
                               campaign_keys=["cleaning_reactivation"])
    assert summary["path"].endswith("scorecard_shining_armor_cleaning_2026-09-14.md")
    # A client scorecard never stages a Skool post.
    assert summary.get("skool") is None


def test_a_week_with_no_staged_recaps_degrades_and_says_why(week_fixture, tmp_path, monkeypatch):
    monkeypatch.setenv(sources.RECAPS_ENV, str(tmp_path / "missing.json"))
    fixtures = dict(week_fixture)
    fixtures["recap_messages"] = None
    week = collect_mod.collect_week(FRIDAY, fixtures=fixtures)
    assert week.recaps["items"] == []
    markdown = render.render_markdown(packet.build_internal_packet(
        week, {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []},
        NEXT_WEEK))
    assert "Wins and objections are empty" in markdown
    assert "Nothing the call notes support." in markdown


class Broken(object):
    """An Instantly client whose every read fails, the documented failure modes."""

    def daily_account_analytics(self, **kwargs):
        raise RuntimeError("HTTP 413: Analytics request is too large")

    def daily_campaign_analytics(self, *args, **kwargs):
        raise RuntimeError("HTTP 500")

    def campaign_analytics(self, *args, **kwargs):
        raise RuntimeError("HTTP 500")

    def iterate(self, *args, **kwargs):
        raise RuntimeError("HTTP 401 Unauthorized")


def test_a_dead_accounts_endpoint_renders_not_available_and_a_caveat(week_fixture):
    """A failed read is never a zero, and the failure reaches the markdown.

    This used to assert `week.metric("sent").this_week in (0, 0.0)`, pinning
    the bug: sum_daily over nothing returns a fully-zeroed dict, so the packet
    printed "Emails sent 0 | 0 | flat | Instantly accounts/analytics/daily" for
    a week in which every read answered 413 or 401, and the string "413"
    appeared nowhere in the document.
    """
    week = collect_mod.collect_week(FRIDAY, instantly=Broken(), ghl=None)
    assert any("HTTP 413" in e for e in week.errors)
    assert week.sources["accounts_daily"].ok is False
    assert week.sources["leads"].ok is False
    assert week.sources["campaigns_daily"].ok is False

    for key in ("sent", "bounced", "bounce_rate", "real_replies", "real_reply_rate",
                "positives", "booked", "held", "closes"):
        metric = week.metric(key)
        assert metric.this_week is None, "%s printed a number nobody measured" % key
        assert metric.last_week is None, key

    markdown = render.render_markdown(packet.build_internal_packet(
        week, {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}, []))
    assert "| Emails sent | not available |" in markdown
    assert "413" in markdown and "too large" in markdown
    assert "401" in markdown
    assert "413" in markdown.split("Read this before you trust a number")[1]

    # And the public draft refuses to state a number it does not have.
    draft = packet.skool_draft(week, {"lessons": [], "bets": []})
    assert "Holding this week's numbers back" in draft["body"]
    assert "Sent 0" not in draft["body"]


def test_a_partial_lead_failure_is_named_in_the_caveats(week_fixture):
    """One 429 on one filter turned 3 booked calls into a confident 0."""

    class OneFilterDown(Broken):
        def daily_account_analytics(self, **kwargs):
            return week_fixture["account_rows"]

        def iterate(self, *args, **kwargs):
            body = (kwargs.get("body") or {})
            if body.get("filter") == "FILTER_LEAD_MEETING_BOOKED":
                raise RuntimeError("HTTP 429 Too Many Requests")

            class Walk(list):
                truncated = False

            return Walk(week_fixture["leads"])

    week = collect_mod.collect_week(FRIDAY, instantly=OneFilterDown(), ghl=None)
    assert week.sources["leads"].ok is True          # three filters did answer
    assert "FILTER_LEAD_MEETING_BOOKED" in week.sources["leads"].reason
    markdown = render.render_markdown(packet.build_internal_packet(
        week, {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}, []))
    caveats = markdown.split("Read this before you trust a number")[1]
    assert "429" in caveats
    assert "floors, not totals" in caveats


def test_a_faked_proposal_is_never_served_to_a_real_run(week_fixture, tmp_path, monkeypatch):
    """An LLM_FAKE evidence run must not poison the real Friday run.

    The claim in the store is what keeps the weekly Opus call to one. A demo
    run writes a claim too, so without this the next real run would print
    invented lessons under Lorenzo's name and report model_calls=0.
    """
    store = JsonFileStore(str(tmp_path / "s.json"))
    monkeypatch.setenv("LLM_FAKE", "1")
    faked = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                             out_dir=str(tmp_path / "out"))
    assert faked["lessons"] == 3
    stored = store.get(retro_packet._claim_key("2026-09-14"))
    assert stored["faked"] is True

    calls = []

    def real_complete(role, system, user, **kwargs):
        calls.append(role)
        context = _context(collect_mod.collect_week(FRIDAY, fixtures=week_fixture))
        return fakes.compliant(context, NEXT_WEEK)("", "", True)

    monkeypatch.delenv("LLM_FAKE", raising=False)
    real = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                            complete=real_complete, out_dir=str(tmp_path / "out"))
    assert calls == ["retro"], "the real run reused the faked proposal"
    assert real["cached_proposal"] is False
    assert store.get(retro_packet._claim_key("2026-09-14"))["faked"] is False


# ------------------------------------------------- windows, dates, timezones
def test_last_weeks_window_keeps_its_offset_across_the_dst_change():
    """timedelta arithmetic on a pytz datetime keeps the OLD offset.

    windows(2026-11-06 16:00 CT) used to return last_window.start as
    2026-10-26T00:00-06:00, but 2026-10-26 was still CDT (-05:00), so the
    instant was an hour late and contains() said an event at 00:30 CT that
    Monday was outside last week.
    """
    this_week, last_week = weeks.windows(TZ.localize(datetime(2026, 11, 6, 16, 0)))
    assert this_week.start.strftime("%Y-%m-%d %z") == "2026-11-02 -0600"
    assert last_week.start.strftime("%Y-%m-%d %z") == "2026-10-26 -0500"
    assert last_week.contains(TZ.localize(datetime(2026, 10, 26, 0, 30))) is True
    assert last_week.cutoff.strftime("%H:%M %z") == "16:00 -0500"


def test_a_status_change_after_19_00_CT_lands_in_the_CT_week():
    """Instantly stamps interest changes in UTC. Slicing the first ten
    characters put a Friday 20:30 CT positive on Saturday, which with three
    positives a week is a 33% error on the headline row, and the one below
    fell out of both windows entirely."""
    this_week, last_week = weeks.windows(FRIDAY)
    friday_evening = {"lt_interest_status": 1,
                      "timestamp_last_interest_change": "2026-09-19T01:30:00Z"}  # Fri 20:30 CT
    sunday_evening = {"lt_interest_status": 2,
                      "timestamp_last_interest_change": "2026-09-14T01:30:00Z"}  # Sun 20:30 CT
    assert metrics.count_statuses([friday_evening], this_week)["positives"] == 1
    assert metrics.count_statuses([friday_evening], last_week)["positives"] == 0
    # Sunday 2026-09-13 20:30 CT belongs to the week before, not to this one.
    assert metrics.count_statuses([sunday_evening], this_week)["positives"] == 0
    assert weeks.ct_date("2026-09-19T01:30:00Z") == "2026-09-18"
    assert weeks.ct_date("2026-09-15") == "2026-09-15"          # a plain date is left alone


def test_a_week_over_week_delta_renders_from_two_populated_weeks(week):
    """The comparison the whole deliverable is about, end to end.

    The fixture used to hold only 2026-09-15 onwards, so at the tests' Friday
    the last-week window was empty and every Change cell read "new", "flat" or
    "not available". The signed and percentage-point branches of fmt_delta and
    the Change column on real movement were never exercised through a packet.
    """
    assert week.metric("sent").last_week == 1250
    assert week.metric("sent").this_week == 1200
    markdown = render.render_markdown(packet.build_internal_packet(
        week, {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}, []))
    assert "| Emails sent | 1200 | 1250 | -50 |" in markdown
    assert "| Bounce rate | 1.42% | 0.80% | +0.62pp |" in markdown
    assert "| Real reply rate | 1.42% | 1.84% | -0.42pp |" in markdown
    assert "not available" not in markdown.split("| Emails sent")[1].split("\n")[0]
    moved = [m.key for m in metrics.moved(week.funnel)]
    assert "real_reply_rate" in moved and "sent" in moved


def test_a_metric_note_is_visible_even_when_the_number_is_present(week):
    """metric_table used to print Metric.note only in place of a missing value,
    so every note written to qualify a number that exists was invisible."""
    markdown = render.render_markdown(packet.build_internal_packet(
        week, {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}, []))
    assert "GHL appointment status is the better source" in markdown
    assert "replies_automatic is a separate counter" in markdown


# --------------------------------------------------- campaigns and verdicts
def test_campaign_verdicts_use_unique_replies_and_never_subtract_automatic(week):
    """One document, two rates for the same campaign, one of them wrong.

    campaign_verdicts computed reply_count_unique minus
    reply_count_automatic_unique, the exact double subtraction
    metrics.real_replies and the runbook forbid. The Campaigns table printed
    2.50% for Cleaning - Trigger Outbound and this table printed 0.67%.
    """
    verdicts = packet.campaign_verdicts(week.campaign_totals)
    by_row = dict((r.get("campaign_name"), r) for r in week.campaign_totals)
    for verdict in verdicts:
        row = by_row[verdict["name"]]
        assert verdict["real_replies"] == float(row["reply_count_unique"])
        assert verdict["auto_replies"] == float(row["reply_count_automatic_unique"])
        assert abs(verdict["real_reply_rate"]
                   - float(row["reply_count_unique"]) / float(row["emails_sent_count"])) < 1e-9

    cleaning = [v for v in verdicts if v["name"] == "2026 Cleaning - Client Reactivation"][0]
    assert abs(cleaning["real_reply_rate"] - 0.0133) < 0.0001   # not 0.33%

    # A true 1.20% real reply rate at the verdict line is a Section 6 keep.
    at_the_line = packet.campaign_verdicts([{
        "campaign_name": "X", "emails_sent_count": 1000, "reply_count_unique": 12,
        "reply_count_automatic_unique": 8, "total_opportunities": 0}])[0]
    assert at_the_line["verdict"] == "keep"
    assert "1.20%" in at_the_line["why"]


def test_a_campaign_with_a_positive_at_1000_runs_to_3000(week):
    """Blueprint M4: no verdict before 1,000, and with >=1 positive at 1,000,
    run to 3,000 before deciding. total_opportunities was collected, displayed
    and never read, so a campaign with positives was killed at 1,000."""
    rows = []
    for row in week.campaign_totals:
        rows.append(dict(row, emails_sent_count=1000))
    verdicts = dict((v["name"], v) for v in packet.campaign_verdicts(rows))
    trigger = verdicts["2026 Cleaning - Trigger Outbound"]
    assert trigger["opportunities"] == 2
    assert trigger["verdict"] == "run to 3,000"
    # No positives at 1,000 and under 1% is still a kill.
    barren = packet.campaign_verdicts([{
        "campaign_name": "Y", "emails_sent_count": 1000, "reply_count_unique": 4,
        "reply_count_automatic_unique": 9, "total_opportunities": 0}])[0]
    assert barren["verdict"] == "kill or rewrite"
    assert "no positives" in barren["why"]


# --------------------------------------------------------- the rubric, again
def test_a_cause_that_only_restates_the_metric_is_rejected(week):
    """A citation proves nothing on its own. "Emails sent moved to 1200 this
    week", citing an unrelated campaign, passed every other rule."""
    context = _context(week)
    key = context["moved"][0]
    cite = context["refs"][0]
    lesson = {
        "metric": key,
        "number": context["metrics"][key]["this_week"],
        "cause": "%s moved to %s this week" % (context["metrics"][key]["label"],
                                               context["metrics"][key]["this_week"]),
        "cite": cite,
        "action": "Ship the next copy change by 2026-09-25",
        "owner": "Lorenzo",
    }
    reasons = " | ".join(lessons.validate_lesson(lesson, context))
    assert "does not mention what it cites" in reasons

    # The same lesson, with a cause that names the cited thing, passes that rule.
    grounded = dict(lesson, cause="The change behind %s landed this week" % cite)
    assert "does not mention what it cites" not in " | ".join(
        lessons.validate_lesson(grounded, context))


def test_a_lesson_that_asks_to_raise_bounces_is_rejected(week):
    """The rubric had no notion of direction, so "Hold bounced above 17 next
    Friday" was an accepted lesson and "Push bounces to 40 next week" an
    accepted bet."""
    context = _context(week)
    assert "bounced" in context["moved"], "the fixture week has no bounce movement"
    cite = context["refs"][0]
    lesson = {
        "metric": "bounced",
        "number": context["metrics"]["bounced"]["this_week"],
        "cause": "The change behind %s landed this week" % cite,
        "cite": cite,
        "action": "Hold bounced above 17 by 2026-09-25",
        "owner": "Lorenzo",
    }
    assert any("up is bad" in r for r in lessons.validate_lesson(lesson, context))
    good = dict(lesson, action="Cut bounced below 17 by 2026-09-25")
    assert lessons.validate_lesson(good, context) == []

    bet = {"bet": "Push bounces to 40 next week", "owner": "Lorenzo", "target": "40 bounces",
           "metric": "bounced", "by": NEXT_WEEK[4]}
    assert any("up is bad" in r for r in lessons.validate_bet(bet, context, NEXT_WEEK))


def test_hold_it_above_n_is_generic_advice():
    """Restatement with a number stapled on. The NUMBER check waved it through
    and the package's own compliant fixture was made of it."""
    assert lessons.is_generic("Review sent again next Friday and hold it above 1200")
    assert lessons.is_generic("Hold it above 1200")
    assert lessons.is_generic("Hold real_reply_rate at or above this week's level")
    assert lessons.is_generic("Cut bounced below 17 by 2026-09-25") is None
    assert lessons.is_generic("Take sent past 1200 by 2026-09-25") is None


def test_the_compliant_fixture_is_not_made_of_the_advice_the_rubric_rejects(week):
    context = _context(week)
    payload = fakes.compliant(context, NEXT_WEEK, week.recaps["items"])("", "", True)
    for lesson in payload["lessons"]:
        assert lessons.validate_lesson(lesson, context) == [], lesson
        assert lessons.is_generic(lesson["action"]) is None, lesson
    for bet in payload["bets"]:
        assert lessons.validate_bet(bet, context, NEXT_WEEK) == [], bet


# ----------------------------------------------------------- staged sources
def test_a_stale_staged_audit_log_is_not_printed_as_this_weeks_changes(tmp_path, monkeypatch):
    """A handoff file staged once and forgotten made every later retro list a
    July campaign pause under "System changes in the window"."""
    staged = tmp_path / "audit_logs.json"
    staged.write_text(json.dumps({"instantly": [
        {"ts": "2026-07-04T10:00:00Z", "action": "campaign.pause",
         "target": "2026 Cleaning - Client Reactivation"},
        {"ts": "2026-09-16T10:05:00Z", "action": "account.delete",
         "target": "lorenzo@oldadvero.com"},
    ], "ghl": []}), encoding="utf-8")
    monkeypatch.setenv(sources.AUDIT_ENV, str(staged))

    window = weeks.windows(FRIDAY)[0]
    source = sources.audit_logs(window=window)
    assert [e["action"] for e in source.value["instantly"]] == ["account.delete"]
    assert "outside the window" in source.reason

    old_only = sources.audit_logs(window=weeks.windows(
        TZ.localize(datetime(2026, 9, 25, 16, 0)))[0])
    assert old_only.value["instantly"] == []
    assert "stale" in old_only.reason


def test_rize_hours_only_count_rows_inside_the_window(tmp_path):
    """A month-wide or stale export was printed as this week's hours."""
    csv_path = tmp_path / "rize.csv"
    csv_path.write_text(
        "Date,Category,Duration\n"
        "2026-08-03,Sales,40\n"
        "2026-08-10,Build,35.5\n"
        "2026-09-16,Sales,6\n",
        encoding="utf-8")
    window = weeks.windows(FRIDAY)[0]
    source = sources.rize_hours(str(csv_path), window=window)
    assert source.value == {"Sales": 6.0}
    assert "2 rows fell outside" in source.reason

    empty_week = sources.rize_hours(str(csv_path), window=weeks.windows(
        TZ.localize(datetime(2026, 9, 25, 16, 0)))[0])
    assert empty_week.value == {}
    assert "no row in the export falls inside" in empty_week.reason


def test_the_ghl_opportunities_walk_follows_the_cursor():
    """One page is not the pipeline; revenue is the invoice basis for A12."""
    pages = []

    class PagedGHL(object):
        def __init__(self):
            self.rows = [{"id": "o%03d" % i, "updatedAt": "2026-09-16T10:00:00Z",
                          "pipelineStageId": "stage-won", "monetaryValue": 10} for i in range(250)]

        def search_opportunities(self, pipeline_id=None, limit=100, start_after_id=None,
                                 start_after=None, **kwargs):
            pages.append(start_after_id)
            start = 0
            if start_after_id:
                start = [r["id"] for r in self.rows].index(start_after_id) + 1
            return {"opportunities": self.rows[start:start + limit]}

    week = collect_mod.Week(FRIDAY, *weeks.windows(FRIDAY))
    rows = collect_mod.pull_opportunities(week, PagedGHL())
    assert len(rows) == 250
    assert pages == [None, "o099", "o199"]


# ------------------------------------------------------------- cost control
def _must_not_be_called(*args, **kwargs):
    raise AssertionError("the expensive model was called on a run that must not pay")


def test_a_dry_run_does_not_call_the_paid_model_unless_the_week_is_already_claimed(
        week_fixture, tmp_path, monkeypatch):
    """--dry-run is advertised as the safe look-first command and it billed
    Opus 5 every single invocation, with persist=False, so the answer was
    thrown away and the next dry run paid again. The runbook's own Friday flow
    (--dry-run then --now) cost two calls where the design says one.
    """
    monkeypatch.delenv("LLM_FAKE", raising=False)
    store = JsonFileStore(str(tmp_path / "s.json"))
    summary = retro_packet.run(FRIDAY, store=store, dry_run=True, complete=_must_not_be_called)
    assert summary["model_calls"] == 0
    assert summary["lessons"] == 0
    assert "does not pay" in summary["skipped"]
    assert store.get(retro_packet._claim_key("2026-09-14")) is None
    # and it still renders the numbers it came for
    assert "Emails sent" in summary["markdown"]


def test_a_dry_run_reuses_a_claim_that_was_already_paid_for(week_fixture, tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_FAKE", raising=False)
    store = JsonFileStore(str(tmp_path / "s.json"))
    calls = []

    def paying(role, system, user, **kwargs):
        calls.append(role)
        context = _context(collect_mod.collect_week(FRIDAY, fixtures=week_fixture))
        return fakes.compliant(context, retro_packet.next_week_dates_for(
            collect_mod.collect_week(FRIDAY, fixtures=week_fixture)))("", "", True)

    paid = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                            complete=paying, out_dir=str(tmp_path / "out"))
    assert paid["lessons"] == 3 and len(calls) == 1
    dry = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=True,
                           complete=_must_not_be_called)
    assert dry["cached_proposal"] is True
    assert dry["lessons"] == 3
    assert len(calls) == 1


def test_the_scorecard_path_never_calls_the_paid_model(week_fixture, tmp_path, monkeypatch):
    """build_client_scorecard takes no proposal, so the lessons-and-bets call
    the CLI made before branching was bought and discarded, once per client per
    week; with --dry-run --scorecard nothing was even cached."""
    monkeypatch.delenv("LLM_FAKE", raising=False)
    store = JsonFileStore(str(tmp_path / "s.json"))
    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                               out_dir=str(tmp_path / "out"), complete=_must_not_be_called,
                               client="Shining Armor Cleaning",
                               campaign_keys=["cleaning_reactivation"])
    assert summary["model_calls"] == 0
    assert store.get(retro_packet._claim_key("2026-09-14")) is None
    assert "lesson" not in summary["markdown"].lower()
    assert "bet" not in summary["markdown"].lower()


def test_fixtures_replay_never_calls_the_paid_model(week_fixture, tmp_path, monkeypatch):
    """--fixtures is documented as an offline replay that touches no API, and
    it reached Anthropic on every run, including from --help's "offline replay"
    and the runbook's flag table."""
    monkeypatch.delenv("LLM_FAKE", raising=False)
    import anthropic

    def explode(*args, **kwargs):
        raise AssertionError("--fixtures reached the Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", explode)
    monkeypatch.setattr(llm, "_CLIENT", {"client": None, "warned": True})
    store = JsonFileStore(str(tmp_path / "s.json"))
    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                               out_dir=str(tmp_path / "out"))
    assert summary["lessons"] == 3
    assert store.get(retro_packet._claim_key("2026-09-14"))["faked"] is True


def test_a_faked_claim_is_written_when_llm_fake_is_set_even_with_an_injected_complete(
        week_fixture, tmp_path, monkeypatch):
    """`faked = is_fake() and complete is None` keyed the provenance tag on who
    supplied the callable. Any caller that injected its own stand-in under
    LLM_FAKE=1 (an evidence run, a replay harness, a demo, a scheduled task)
    stored a fabricated proposal tagged faked=false, and the next real run
    served those invented lessons and reported model_calls=0.
    """
    monkeypatch.setenv("LLM_FAKE", "1")
    store = JsonFileStore(str(tmp_path / "s.json"))

    def injected(role, system, user, **kwargs):
        context = _context(collect_mod.collect_week(FRIDAY, fixtures=week_fixture))
        return fakes.compliant(context, NEXT_WEEK, week_fixture.get("recap_messages") and [])(
            "", "", True)

    retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                     complete=injected, out_dir=str(tmp_path / "out"))
    stored = store.get(retro_packet._claim_key("2026-09-14"))
    assert stored["faked"] is True, "a fake-mode run stored its answer as a real one"

    monkeypatch.delenv("LLM_FAKE", raising=False)
    calls = []

    def real_complete(role, system, user, **kwargs):
        calls.append(role)
        week = collect_mod.collect_week(FRIDAY, fixtures=week_fixture)
        return fakes.compliant(_context(week), retro_packet.next_week_dates_for(week))(
            "", "", True)

    real = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                            complete=real_complete, out_dir=str(tmp_path / "out"))
    assert calls == ["retro"], "the real run reused the faked proposal"
    assert real["cached_proposal"] is False


def test_a_failed_model_call_is_not_claimed_for_the_week(week_fixture, tmp_path, monkeypatch):
    """A 529 is a routine Anthropic response. Writing it into the store as the
    week's answer meant one blip permanently emptied the one section the whole
    brief is about, and only --refresh could get it back."""
    monkeypatch.delenv("LLM_FAKE", raising=False)
    store = JsonFileStore(str(tmp_path / "s.json"))

    def overloaded(*args, **kwargs):
        raise RuntimeError("anthropic 529 overloaded")

    first = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                             complete=overloaded, out_dir=str(tmp_path / "out"))
    assert first["lessons"] == 0
    assert store.get(retro_packet._claim_key("2026-09-14")) is None
    assert "529" in first["not_claimed"]

    calls = []

    def working(role, system, user, **kwargs):
        calls.append(role)
        week = collect_mod.collect_week(FRIDAY, fixtures=week_fixture)
        return fakes.compliant(_context(week), retro_packet.next_week_dates_for(week))(
            "", "", True)

    second = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                              complete=working, out_dir=str(tmp_path / "out"))
    assert calls == ["retro"]
    assert second["lessons"] == 3


def test_a_store_that_cannot_hold_the_claim_stops_the_run_before_it_pays(
        week_fixture, tmp_path, monkeypatch):
    """The claim IS the cost cap. Catching the write failure and logging a
    warning left every run that Friday paying again, silently."""
    monkeypatch.delenv("LLM_FAKE", raising=False)

    class DeadStore(object):
        def get(self, key, default=None):
            return None

        def set(self, key, value):
            raise IOError("read-only file system")

        def delete(self, key):
            pass

        def set_if_absent(self, key, value):
            raise IOError("read-only file system")

    # No fixtures and no LLM_FAKE, so this is the path that would really pay.
    with pytest.raises(retro_packet.ClaimNotWritable) as excinfo:
        retro_packet.run(FRIDAY, store=DeadStore(), dry_run=False, complete=None,
                         out_dir=str(tmp_path / "out"))
    # The pre-flight probe fired, not the post-call write: nothing was spent.
    assert "nothing to stop the expensive model being billed again" in str(excinfo.value)
    assert "already been paid for" not in str(excinfo.value)


# ------------------------------------------------------------ rerun safety
def test_a_second_run_does_not_overwrite_the_edited_packet(week_fixture, tmp_path, monkeypatch):
    """The packet whose stated purpose is ten minutes of hand editing is the
    thing a retry used to destroy: a fixed filename opened with "w"."""
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    store = JsonFileStore(str(tmp_path / "s.json"))
    out = tmp_path / "out"
    first = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                             out_dir=str(out))
    assert first["path"].endswith("retro_2026-09-14.md")
    with open(first["path"], "a", encoding="utf-8") as handle:
        handle.write("\nLORENZO EDIT: this is the line I spent ten minutes on.\n")

    second = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                              out_dir=str(out))
    assert second["path"] != first["path"]
    assert second["kept_existing"] is True
    with open(first["path"], "r", encoding="utf-8") as handle:
        assert "LORENZO EDIT" in handle.read()

    # --force is how you overwrite on purpose.
    third = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                             out_dir=str(out), force=True)
    assert third["path"] == first["path"]
    with open(first["path"], "r", encoding="utf-8") as handle:
        assert "LORENZO EDIT" not in handle.read()


def test_a_retry_stages_at_most_one_skool_would_do(week_fixture, tmp_path, monkeypatch):
    """Whoever posts from the shadow log used to see the same week twice."""
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    store = JsonFileStore(str(tmp_path / "s.json"))
    out = tmp_path / "out"
    retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False, out_dir=str(out))
    second = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                              out_dir=str(out))
    shadow = job_log_mod.read_shadow_log(tmp_path / "shadow.jsonl")
    skool = [r for r in shadow if r["system"] == "skool"]
    assert len(skool) == 1
    assert second["skool"] is None
    assert second["skool_already_staged"] is True


# ------------------------------------------------- the cache and the numbers
def test_a_cached_proposal_is_rejudged_against_this_weeks_numbers(week_fixture, tmp_path,
                                                                  monkeypatch):
    """The claim is keyed by the Monday, so a proposal written by a mid-week
    run was handed back verbatim on Friday: the funnel said "Emails sent 1200"
    while the lessons underneath quoted "sent 300"."""
    monkeypatch.delenv("LLM_FAKE", raising=False)
    store = JsonFileStore(str(tmp_path / "s.json"))
    tuesday = TZ.localize(datetime(2026, 9, 15, 9, 0))

    def tuesdays_answer(role, system, user, **kwargs):
        week = collect_mod.collect_week(tuesday, fixtures=week_fixture)
        return fakes.compliant(_context(week), retro_packet.next_week_dates_for(week))(
            "", "", True)

    early = retro_packet.run(tuesday, fixtures=week_fixture, store=store, dry_run=False,
                             complete=tuesdays_answer, out_dir=str(tmp_path / "out"))
    assert early["lessons"] >= 1
    early_numbers = [l["number"] for l in store.get(
        retro_packet._claim_key("2026-09-14"))["lessons"]]

    friday = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=False,
                              complete=_must_not_be_called, out_dir=str(tmp_path / "out"))
    assert friday["cached_proposal"] is True
    assert friday["numbers_changed"] is True
    markdown = friday["markdown"]
    printed = markdown.split("| Emails sent |")[1].split("|")[0].strip()
    assert printed == "1200"
    # Nothing quoting Tuesday's numbers survives into the lessons section.
    lessons_block = markdown.split("## Three lessons from the data")[1].split("## Hours")[0]
    stale = [n for n in early_numbers if n not in ("1200",) and n in lessons_block]
    assert not stale, "a lesson quotes a number this week's funnel does not print: %s" % stale
    assert friday["stale_dropped"] >= 1
    assert "Appendix: rejected by the rubric" in markdown
    assert "no longer true of these numbers" in markdown


def test_weeks_back_moves_next_weeks_dates_too(week_fixture):
    """--weeks-back is the runbook's answer to a missed Friday, and it was
    exactly when this fired: next_week_dates came from windows(week.now), so a
    packet for the week of 2026-09-07 told the model next week ran 2026-09-21
    to 2026-09-27 and validate_bet threw out every correctly dated bet."""
    week = collect_mod.collect_week(FRIDAY, fixtures=week_fixture, weeks_back=1)
    dates = retro_packet.next_week_dates_for(week)
    assert week.this_window.start_date == "2026-09-07"
    assert dates[0] == "2026-09-14"
    assert dates[-1] == "2026-09-20"

    summary = retro_packet.run(FRIDAY, fixtures=week_fixture, store=None, dry_run=True,
                               weeks_back=1)
    assert "# Retro packet, week of 2026-09-07" in summary["markdown"]
    assert "Next week runs 2026-09-14 to 2026-09-20" in summary["markdown"]


def test_the_dry_run_still_reads_the_real_job_log(week_fixture, tmp_path, monkeypatch, capsys):
    """main() repointed JOB_LOG_PATH at an empty scratch file before collecting,
    so "What the machine did" was always empty in the run the runbook tells
    Lorenzo to inspect first."""
    real_log = tmp_path / "job_log.csv"
    real_log.write_text(
        "ts_utc,job,status,mode,details\n"
        "2026-09-16T12:00:00+00:00,cadence_tick,ok,shadow,{}\n",
        encoding="utf-8")
    monkeypatch.setenv("JOB_LOG_PATH", str(real_log))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    fixture_path = os.path.join(FIXTURES, "week_2026-09.json")
    seen = {}
    real_run = retro_packet.run

    def capture(*args, **kwargs):
        summary = real_run(*args, **kwargs)
        seen["markdown"] = summary["markdown"]
        seen["job_log_path"] = kwargs.get("job_log_path")
        return summary

    monkeypatch.setattr(retro_packet, "run", capture)
    code = retro_packet.main(
        ["--dry-run", "--fixtures", "--fixtures-path", fixture_path,
         "--as-of", "2026-09-18T16:00:00-05:00"],
        store=JsonFileStore(str(tmp_path / "s.json")))
    assert code == 0
    # main() captured the REAL path before use_scratch_logs moved JOB_LOG_PATH.
    assert seen["job_log_path"] == str(real_log)
    assert os.environ["JOB_LOG_PATH"] != str(real_log)   # the dry run's own log is scratch
    machine = seen["markdown"].split("## What the machine did")[1]
    assert "cadence_tick" in machine
    assert "No Job_Log rows in the window" not in machine


# --------------------------------------------------------- client scorecard
def test_the_client_scorecard_names_what_it_cannot_yet_confirm(week):
    """The card is the invoice basis for a performance deal and it carried no
    caveats at all, so a client whose call Lorenzo held read "Calls booked 0,
    Calls held 0, Signed 0" as hard fact."""
    card = scorecard.build_client_scorecard(week, "Shining Armor Cleaning",
                                            campaign_keys=["cleaning_reactivation"])
    markdown = scorecard.render_client_scorecard(card)
    assert "How to read these numbers" in markdown
    assert "check them against your own calendar" in markdown
    assert "floor" in markdown
    # Client copy rules still hold over the whole thing, caveats included.
    assert render.check_client_copy(markdown) == []
    for banned in ("mirror", "shadow", "S8", "lt_interest_status"):
        assert banned not in markdown


def test_an_unknown_campaign_key_raises_instead_of_rendering_zeros(week):
    """`--campaigns cleaning` (the key is cleaning_reactivation) rendered a
    perfectly valid client report of a total failure week."""
    with pytest.raises(scorecard.UnknownCampaign) as excinfo:
        scorecard.build_client_scorecard(week, "Shining Armor Cleaning",
                                         campaign_keys=["cleaning"])
    assert "cleaning_reactivation" in str(excinfo.value)

    with pytest.raises(SystemExit):
        retro_packet.main(["--dry-run", "--fixtures", "--scorecard", "Shining Armor Cleaning",
                           "--campaigns", "cleaning"], now=FRIDAY)


def test_the_skool_draft_reports_an_em_dash_it_had_to_repair(week):
    """The copy check ran AFTER skool_draft had already substituted em dashes
    and exclamation marks away, so the guard could never fire."""
    proposal = {"lessons": [{"metric": "sent", "number": "1200",
                             "cause": "the copy change landed\u2014and it worked!",
                             "cite": "x", "action": "Ship it", "owner": "Lorenzo"}],
                "bets": []}
    draft = packet.skool_draft(week, proposal)
    assert "contains an em dash" in draft["copy_repairs"]
    assert "contains an exclamation mark" in draft["copy_repairs"]
    # ... and the body that would be posted is clean.
    assert render.check_copy(draft["body"], ban_words=False) == []


def test_dry_run_plus_refresh_is_an_error_not_a_silent_no_op(week_fixture):
    """--refresh asks to pay again and --dry-run does not pay. Ignoring one of
    them quietly is worse than saying so."""
    with pytest.raises(SystemExit):
        retro_packet.main(["--dry-run", "--fixtures", "--refresh"], now=FRIDAY)


def test_dry_run_with_pay_claims_the_week_so_it_still_costs_one_call(
        week_fixture, tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_FAKE", raising=False)
    store = JsonFileStore(str(tmp_path / "s.json"))
    calls = []

    def paying(role, system, user, **kwargs):
        calls.append(role)
        week = collect_mod.collect_week(FRIDAY, fixtures=week_fixture)
        return fakes.compliant(_context(week), retro_packet.next_week_dates_for(week))(
            "", "", True)

    first = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=True, pay=True,
                             complete=paying)
    assert first["lessons"] == 3
    assert store.get(retro_packet._claim_key("2026-09-14")) is not None
    second = retro_packet.run(FRIDAY, fixtures=week_fixture, store=store, dry_run=True, pay=True,
                              complete=_must_not_be_called)
    assert second["cached_proposal"] is True
    assert len(calls) == 1


# ------------------------------------ re-review 2026-09-22 (OPS-3, 4, 6, 11, 12)
class CampaignsDown(Broken):
    """Accounts and leads answer; every per-campaign daily pull answers 500."""

    def __init__(self, week_fixture):
        self.fx = week_fixture

    def daily_account_analytics(self, **kwargs):
        return self.fx["account_rows"]

    def campaign_analytics(self, *args, **kwargs):
        return self.fx.get("campaign_totals") or []

    def iterate(self, path, body=None, max_pages=None):
        status = {"FILTER_LEAD_INTERESTED": 1, "FILTER_LEAD_MEETING_BOOKED": 2,
                  "FILTER_LEAD_MEETING_COMPLETED": 3, "FILTER_LEAD_CLOSED": 4}.get(
                      (body or {}).get("filter"))

        class Walk(list):
            truncated = False

        return Walk([l for l in self.fx["leads"] if l.get("lt_interest_status") == status])


def test_ops3_failed_campaign_reads_render_not_available_on_the_card_and_in_the_retro(week_fixture):
    week = collect_mod.collect_week(FRIDAY, instantly=CampaignsDown(week_fixture), ghl=None)
    assert week.sources["campaigns_daily"].ok is False
    assert all(v is None for v in week.per_campaign["this"].values())
    for row in week.campaign_rows:
        assert row[1:] == [None] * 6, row

    card = scorecard.render_client_scorecard(scorecard.build_client_scorecard(
        week, "Example Cleaning", campaign_keys=["cleaning_reactivation"]))
    assert "| Emails sent |" not in card
    assert "Emails sent (could not be read" in card
    assert "left out below rather than shown as a zero" in card

    markdown = render.render_markdown(packet.build_internal_packet(
        week, {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}, []))
    campaigns = markdown.split("## Campaigns")[1].split("##")[0]
    assert "not available" in campaigns
    assert "| 0 |" not in campaigns


def test_ops3_one_failed_campaign_makes_a_two_campaign_client_not_available(week_fixture):
    class OneDown(CampaignsDown):
        def daily_campaign_analytics(self, campaign_id, *args, **kwargs):
            if campaign_id == collect_mod.settings.CAMPAIGNS["cleaning_trigger"]["id"]:
                raise RuntimeError("HTTP 500")
            key = [k for k, v in collect_mod.settings.CAMPAIGNS.items() if v["id"] == campaign_id][0]
            return self.fx["campaign_rows"].get(key) or []

    week = collect_mod.collect_week(FRIDAY, instantly=OneDown(week_fixture), ghl=None)
    metrics_ = scorecard.client_funnel(week, ["cleaning_reactivation", "cleaning_trigger"])
    assert metrics.by_key(metrics_)["sent"].this_week is None
    assert metrics.by_key(scorecard.client_funnel(week, ["cleaning_reactivation"]))["sent"].available


def test_ops4_an_edit_only_updated_at_is_not_a_close_or_a_proposal():
    """Two August Won deals and an August proposal, edited this week: the
    retro read updatedAt first and showed closes 2 and $10,000."""
    stages = {"won": "W", "proposal_sent": "P"}
    window = weeks.windows(TZ.localize(datetime(2026, 9, 25, 16, 0)))[0]
    edited = [{"pipelineStageId": "W", "monetaryValue": 6000, "updatedAt": "2026-09-22T03:00:00Z",
               "lastStageChangeAt": "2026-08-10T15:00:00Z"},
              {"pipelineStageId": "W", "monetaryValue": 4000, "updatedAt": "2026-09-22T03:00:05Z",
               "lastStatusChangeAt": "2026-08-11T15:00:00Z"},
              {"pipelineStageId": "P", "updatedAt": "2026-09-22T03:00:09Z",
               "lastStageChangeAt": "2026-08-12T15:00:00Z"}]
    out = metrics.count_opportunities(edited, window, stages)
    assert (out["proposals"], out["closes"], out["revenue"]) == (0.0, 0.0, 0.0)

    # a real move this week counts
    moved = edited + [{"pipelineStageId": "W", "monetaryValue": 2500,
                       "lastStageChangeAt": "2026-09-23T15:00:00Z"}]
    assert metrics.count_opportunities(moved, window, stages)["revenue"] == 2500.0

    # an opportunity with only an edit time cannot be placed: not available
    undated = [{"pipelineStageId": "W", "monetaryValue": 6000, "updatedAt": "2026-09-22T03:00:00Z"}]
    out = metrics.count_opportunities(undated, window, stages)
    assert out["closes"] is None and out["revenue"] is None
    funnel = metrics.build_funnel({"accounts": {"sent": 1}, "statuses": {}, "opps": out},
                                  {"accounts": {"sent": 1}, "statuses": {}, "opps": out})
    assert metrics.by_key(funnel)["revenue"].this_week is None
    assert "no stage-change date" in metrics.by_key(funnel)["revenue"].note


def test_ops6_retro_statuses_are_bounded_and_deduped_by_email():
    window = weeks.Window(TZ.localize(datetime(2026, 9, 14)), TZ.localize(datetime(2026, 9, 18)),
                          "test")
    stamp = "2026-09-16T15:00:00Z"
    leads = [{"id": "1", "email": "a@x.com", "lt_interest_status": 1,
              "timestamp_last_interest_change": stamp},
             {"id": "2", "email": "A@x.com", "lt_interest_status": 2,
              "timestamp_last_interest_change": stamp},
             {"id": "3", "email": "c@x.com", "lt_interest_status": 1000,
              "timestamp_last_interest_change": stamp}]
    counts = metrics.count_statuses(leads, window)
    assert counts["closes"] == 0 and counts["positives"] == 2        # custom label ignored
    people, collapsed = metrics.dedupe_by_email(leads)
    assert collapsed == 1
    counts = metrics.count_statuses(people, window)
    assert counts["positives"] == 1 and counts["booked"] == 1        # the copy furthest up wins


def test_ops11_no_shows_are_not_available_rather_than_zero(week):
    no_shows = week.metric("no_shows")
    assert no_shows.this_week is None
    assert "no-show (-4)" in no_shows.note
    assert "floor" in week.metric("booked").note


def test_ops12_fixtures_now_writes_only_a_stamped_replay(week_fixture, tmp_path, monkeypatch):
    """--fixtures --now used to write this week's canonical retro_<monday>.md,
    record a Skool would_do in the real shadow log and claim the week's Skool
    slot, all unstamped."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path / "tmp"))
    real_job_log = tmp_path / "real_job_log.csv"
    real_shadow = tmp_path / "real_shadow.jsonl"
    monkeypatch.setenv("JOB_LOG_PATH", str(real_job_log))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(real_shadow))
    store = JsonFileStore(str(tmp_path / "s.json"))
    out = tmp_path / "retro_out"
    real = out / "retro_2026-09-14.md"
    out.mkdir()
    real.write_text("Lorenzo's edited packet\n", encoding="utf-8")

    assert _run_job(["--now", "--fixtures", "--force", "--out-dir", str(out)], week_fixture,
                    tmp_path, store=store) == 0
    assert real.read_text(encoding="utf-8") == "Lorenzo's edited packet\n"
    written = list((out / "replay").glob("*.replay.md"))
    assert len(written) == 1
    text = written[0].read_text(encoding="utf-8")
    assert text.startswith("# REPLAY:")
    assert retro_packet.REPLAY_STAMP in text
    assert store.get(retro_packet._skool_key("2026-09-14")) is None
    assert store.get(retro_packet._claim_key("2026-09-14")) is None
    assert not real_shadow.exists() or "post_create" not in real_shadow.read_text(encoding="utf-8")
    assert not real_job_log.exists()


def test_ops12_the_fake_never_bets_on_cutting_a_zero():
    context = {"moved": ["bounced", "sent"], "refs": ["abc1234"], "owners": ["Lorenzo"],
               "metrics": {"bounced": {"this_week": "0", "label": "Bounces"},
                           "sent": {"this_week": "300", "label": "Emails sent"}}}
    payload = fakes.compliant(context, ["2026-09-28"] * 5)("", "", True)
    assert all("below 0" not in b["bet"] for b in payload["bets"])
