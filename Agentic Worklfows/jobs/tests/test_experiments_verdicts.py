"""Verdict rules, analytics parsing and projection math (brief A7).

Runs entirely on the fixtures recorded read-only from the live workspace on
2026-09-22 (``services/experiments/fixtures/``). No network, no writes.
"""
import datetime

import pytest

from services.experiments import analytics, verdicts as V
from services.experiments.fakes import FakeInstantly, load_fixture

AS_OF = datetime.date(2026, 9, 22)
CAMPAIGNS = {
    "cleaning_reactivation": {"id": "8086b41e-b546-4b36-9fa0-2d01f5cc119a", "niche": "cleaning", "offer": "reactivation"},
    "cleaning_trigger": {"id": "f347604e-48c7-4813-831c-dc7b9d4b50ae", "niche": "cleaning", "offer": "outbound"},
    "bookkeeping_reactivation": {"id": "f00c5e28-fdc4-4d84-a7e6-dfba9695f35d", "niche": "bookkeeping", "offer": "reactivation"},
    "bookkeeping_trigger": {"id": "87ebb167-9b64-4b6f-b658-88f3d1af9980", "niche": "bookkeeping", "offer": "outbound"},
    "recruiting_reactivation": {"id": "1d4d5bb3-40a7-4333-bf34-b269d2cc9955", "niche": "recruiting", "offer": "reactivation"},
    "recruiting_outbound": {"id": "cd2e251c-3b5a-40d2-a3dc-d07c4004a48c", "niche": "recruiting", "offer": "outbound"},
}


@pytest.fixture
def client():
    return FakeInstantly()


@pytest.fixture
def stats(client):
    return analytics.collect(
        client, daily_start="2026-09-08", daily_end="2026-09-22", campaigns=CAMPAIGNS
    )


def _stub(key="cleaning_reactivation", **kw):
    """A CampaignStats with only the fields a rule reads."""
    s = analytics.CampaignStats(key, "id-%s" % key, niche=kw.pop("niche", "cleaning"), offer="reactivation")
    s.sent = kw.pop("sent", 0)
    s.positives = kw.pop("positives", 0)
    s.negatives = kw.pop("negatives", 0)
    s.real_replies = kw.pop("real_replies", 0)
    s.bounced = kw.pop("bounced", 0)
    s.inboxes = kw.pop("inboxes", 12)
    s.daily_limit = kw.pop("daily_limit", 50)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ----------------------------------------------------- the live-shape traps
def test_real_replies_never_subtracts_automatic_replies():
    """reply_count_unique already excludes automatic replies.

    The plausible reading of M1 level 3 is unique minus automatic. On the
    2026-09-22 live data that is -3 for bookkeeping_reactivation (1 unique, 4
    automatic) and -5 for bookkeeping_trigger. Two disjoint buckets, and the
    subtraction would report a negative reply rate and trip every threshold.
    """
    overview = {r["campaign_id"]: r for r in load_fixture("campaign_overview_2026-09-22.json")}
    book = overview["f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"]
    assert book["reply_count_unique"] == 1
    assert book["reply_count_automatic_unique"] == 4
    assert analytics.real_replies(book) == 1
    assert analytics.auto_replies(book) == 4


def test_real_plus_auto_replies_equals_the_replied_lead_count_on_every_campaign():
    """The proof the two buckets are disjoint: they sum to the replied list."""
    overview = {r["campaign_id"]: r for r in load_fixture("campaign_overview_2026-09-22.json")}
    leads = load_fixture("replied_leads_2026-09-22.json")
    for key, meta in CAMPAIGNS.items():
        row = overview[meta["id"]]
        total = analytics.real_replies(row) + analytics.auto_replies(row)
        assert total == len(leads[key]), key


def test_unknown_lead_filter_is_refused_not_sent(client):
    """POST /leads/list ignores a filter it does not know and answers with the
    unfiltered list, so a typo would count every contacted lead as a positive."""
    with pytest.raises(analytics.AnalyticsError) as exc:
        analytics.replied_leads(client, CAMPAIGNS["cleaning_reactivation"]["id"],
                                lead_filter="FILTER_VAL_LEAD_INTERESTED")
    assert "returns everything" in str(exc.value)


def test_steps_totals_row_is_dropped(client):
    rows = analytics.step_rows(client, CAMPAIGNS["cleaning_reactivation"]["id"])
    assert rows, "fixture should carry step rows"
    assert all(r.get("step") is not None for r in rows)
    parsed = analytics.parse_variants(rows)
    # The API answers strings, zero-based; the objects expose 1-based steps.
    assert sorted([(v.step_number, v.variant_letter) for v in parsed]) == [(1, "A"), (2, "A")]


def test_collect_reads_the_live_numbers(stats):
    clean = stats["cleaning_reactivation"]
    assert clean.sent == 300
    assert clean.real_replies == 4
    assert clean.auto_replies == 3
    # ilmi@shiningarmorcleaningnj.com is status 1 and rob@cjsglobal.com is -3
    # (lost). Rob replied positively and held his call on Sept 18: the
    # blueprint audit counts both, and a positive that later closes out is
    # still a positive the copy produced.
    assert clean.positives == 2
    assert clean.open_positives == 1
    assert clean.closed_out == 1
    assert clean.negatives == 2                  # the two -1s only
    assert clean.daily_limit == 50
    assert clean.inboxes == 12
    assert clean.status == 1 and clean.is_active
    assert clean.observed_sends_per_day == 50    # median of the sending days
    assert clean.sends_per_day == 50


def test_positives_are_attributed_to_the_variant_that_earned_them(stats):
    clean = stats["cleaning_reactivation"]
    step1 = clean.variants_for_step(1)[0]
    step2 = clean.variants_for_step(2)[0]
    assert step1.sent == 197 and step2.sent == 103
    # Ilmi replied to step 1 variant 0, Rob to step 2 variant 0.
    assert step1.positives + step2.positives == clean.positives == 2
    assert step1.positives == 1 and step2.positives == 1


def test_a_positive_with_no_readable_reply_step_is_not_attributed_to_step_one():
    """Mis-attributing a positive is how an A/B test gets decided wrongly."""
    variants = [analytics.VariantStats(0, 0, 100, 2, 0), analytics.VariantStats(0, 1, 100, 1, 0)]
    analytics.attach_positives(variants, [{"email": "x@y.com", "lt_interest_status": 1,
                                           "email_replied_step": None, "email_replied_variant": None}])
    assert [v.positives for v in variants] == [0, 0]


def test_observed_rate_uses_the_median_of_sending_days_not_the_mean():
    rows = [{"sent": 0}, {"sent": 0}, {"sent": 50}, {"sent": 50}, {"sent": 50}]
    assert analytics.observed_rate(rows) == 50
    assert analytics.observed_rate([{"sent": 0}]) == 0


# ------------------------------------------------------------- the M4 rules
def test_no_verdict_before_one_thousand_sends(stats):
    for key, s in stats.items():
        assert s.sent == 300
        v = V.decide(s)
        assert v.recommendation == "keep_running", key
        assert v.next_line == V.VERDICT_LINE


def test_one_positive_at_the_line_buys_a_run_to_three_thousand():
    v = V.decide(_stub(sent=1000, positives=1))
    assert v.recommendation == "run_to_3000"
    assert v.next_line == V.CONFIRM_LINE


def test_recruiting_with_zero_positives_at_one_thousand_is_proposed_for_retirement():
    v = V.decide(_stub(key="recruiting_outbound", niche="recruiting", sent=1000, positives=0, inboxes=12))
    assert v.recommendation == "retire"
    assert v.next_line is None
    # Without the other campaigns in hand the text must not claim it releases
    # 12 inboxes; it reports the headroom it can actually vouch for.
    assert "release its 12 inboxes" not in v.reason
    assert "daily_limit headroom" in v.reason
    assert "shared across campaigns" in v.reason


def test_a_non_recruiting_campaign_with_zero_positives_is_reworked_not_retired():
    v = V.decide(_stub(sent=1000, positives=0, niche="bookkeeping"))
    assert v.recommendation == "rework_copy"
    assert v.next_line == V.REWORK_RETEST_LINE


def test_recruiting_below_the_line_is_warned_but_not_retired():
    v = V.decide(_stub(key="recruiting_reactivation", niche="recruiting", sent=900, positives=0))
    assert v.recommendation == "keep_running"
    assert "proposed for retirement" in v.reason


def test_three_thousand_send_outcomes():
    assert V.decide(_stub(sent=3000, positives=25)).recommendation == "scale"     # 0.83%
    assert V.decide(_stub(sent=3000, positives=18)).recommendation == "hold"      # 0.60%
    assert V.decide(_stub(sent=3000, positives=6)).recommendation == "rework_copy"  # 0.20%


def test_section_six_flags_ride_along_without_changing_the_verdict():
    # 1,500 sends over 12 inboxes clears the 100-per-inbox precondition.
    s = _stub(sent=1500, positives=5, bounced=40, real_replies=5)
    v = V.decide(s)
    assert v.recommendation == "run_to_3000"
    assert any("bounce" in f for f in v.flags)
    assert any("real reply" in f for f in v.flags)


def test_a_truncated_lead_walk_is_flagged_because_positives_become_a_floor():
    client = FakeInstantly(truncate_leads=True)
    stats = analytics.collect(client, campaigns=CAMPAIGNS)
    v = V.decide(stats["cleaning_reactivation"])
    assert any("truncated" in f for f in v.flags)


# ------------------------------------------------------------- projections
def test_capacity_from_ids_matches_the_blueprint():
    ids = {"instantly": {
        "active_inboxes": ["a"] * 12,
        "warming_domains": ["d"] * 11,
        "per_inbox_daily_limit": 25,
    }}
    cap = V.capacity_from_ids(ids)
    assert cap.now_per_day == 300
    assert cap.after_step_per_day == 1125
    assert round(cap.multiplier, 2) == 3.75


def test_projection_skips_the_days_the_campaign_does_not_send():
    mon_sat = {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": True}
    # 2026-09-22 is a Tuesday; 700 more sends at 50/day is 14 sending days,
    # and two Sundays (Sept 27, Oct 4) fall inside that span.
    assert AS_OF.weekday() == 1
    got = V.project_date(300, 1000, AS_OF, mon_sat, 50)
    assert got == datetime.date(2026, 10, 7)
    # Same campaign sending seven days a week lands two days earlier.
    every_day = dict(mon_sat, **{"0": True})
    assert V.project_date(300, 1000, AS_OF, every_day, 50) == datetime.date(2026, 10, 5)


def test_projection_at_the_oct_eleven_rate_is_the_floor_and_the_blend_is_the_plan():
    mon_sat = {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": True}
    now_rate, after_rate = 50, 188
    floor = V.project_date(300, 3000, AS_OF, mon_sat, after_rate)
    current = V.project_date(300, 3000, AS_OF, mon_sat, now_rate)
    blended = V.project_date(300, 3000, AS_OF, mon_sat, now_rate, per_day_after=after_rate)
    assert floor < blended < current


def test_a_paused_campaign_projects_to_none_not_to_a_date_years_out():
    mon_sat = {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": True}
    assert V.project_date(300, 1000, AS_OF, mon_sat, 0) is None
    assert V.project_date(300, 1000, AS_OF, mon_sat, 1, max_days=30) is None


def test_projection_returns_today_when_the_line_is_already_passed():
    mon_sat = {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": True}
    assert V.project_date(1200, 1000, AS_OF, mon_sat, 50) == AS_OF


def test_run_fills_all_three_dates_on_live_stats(stats):
    cap = V.capacity_from_ids({"instantly": {"active_inboxes": ["a"] * 12,
                                             "warming_domains": ["d"] * 11,
                                             "per_inbox_daily_limit": 25}})
    out = V.run(stats, cap, AS_OF)
    for key, v in out.items():
        assert v.eta_current and v.eta_oct11 and v.eta_blended, key
        assert v.eta_blended <= v.eta_current, key
        # The Oct 11 column is a date that has to be reachable, so it is never
        # earlier than the capacity step it is named after.
        assert v.eta_oct11 >= V.CAPACITY_STEP_DATE, key


# ---------------------------------------------------------- variant judging
def test_a_variant_is_never_judged_below_five_hundred_sends():
    s = _stub(sent=1000)
    s.variants = [analytics.VariantStats(0, 0, 499, 20, 0), analytics.VariantStats(0, 1, 499, 2, 0)]
    for v, p in zip(s.variants, (10, 1)):
        v.positives = p
    vv = V.judge_step(s, 1)
    assert vv.status == "insufficient_sample"
    assert "needs 1 more sends" in vv.reason
    assert vv.winner is None


def test_a_clear_winner_at_sample_is_called():
    s = _stub(sent=2000)
    a = analytics.VariantStats(0, 0, 1000, 40, 0)
    b = analytics.VariantStats(0, 1, 1000, 8, 0)
    a.positives, b.positives = 30, 5
    s.variants = [a, b]
    vv = V.judge_step(s, 1)
    assert vv.status == "winner"
    assert vv.winner == "step1/A" and vv.loser == "step1/B"
    assert vv.p_value < 0.05


def test_a_narrow_lead_at_sample_is_not_called():
    s = _stub(sent=1000)
    a = analytics.VariantStats(0, 0, 500, 6, 0)
    b = analytics.VariantStats(0, 1, 500, 5, 0)
    a.positives, b.positives = 3, 2
    s.variants = [a, b]
    vv = V.judge_step(s, 1)
    assert vv.status == "no_difference"
    assert vv.winner is None


def test_two_variants_with_no_positives_are_reported_as_no_difference_not_a_tie_winner():
    s = _stub(sent=1200)
    s.variants = [analytics.VariantStats(0, 0, 600, 4, 0), analytics.VariantStats(0, 1, 600, 3, 0)]
    vv = V.judge_step(s, 1)
    assert vv.status == "no_difference"
    assert vv.p_value is None


def test_single_variant_steps_report_that_and_nothing_else(stats):
    for key, s in stats.items():
        for vv in V.judge_all_steps(s):
            assert vv.status == "single_variant", (key, vv.step)


def test_two_proportion_p_is_symmetric_and_bounded():
    assert V.two_proportion_p(10, 100, 2, 100) == pytest.approx(V.two_proportion_p(2, 100, 10, 100))
    assert 0.0 <= V.two_proportion_p(10, 100, 2, 100) <= 1.0
    assert V.two_proportion_p(0, 100, 0, 100) is None
    assert V.two_proportion_p(1, 0, 1, 10) is None


# ------------------------------------------------- live shapes, second pass
@pytest.mark.parametrize("key", sorted(CAMPAIGNS.keys()))
def test_steps_totals_row_is_dropped(client, key):
    """The totals row is `step: null` on four campaigns and the STRING "null"
    on recruiting_reactivation. Both are totals; neither is a step."""
    rows = analytics.step_rows(client, CAMPAIGNS[key]["id"])
    assert rows, key
    assert all(not analytics.is_totals_row(r) for r in rows), key
    assert len(rows) == 2, key
    parsed = analytics.parse_variants(rows)
    assert sorted([(v.step_number, v.variant_letter) for v in parsed]) == [(1, "A"), (2, "A")], key


def test_a_clean_pull_logs_no_unreadable_step_warning(client, caplog):
    caplog.set_level("WARNING", logger="services.experiments.analytics")
    analytics.collect(client, campaigns=CAMPAIGNS)
    unreadable = [r for r in caplog.records if "unreadable step/variant" in r.getMessage()]
    assert not unreadable, [r.getMessage() for r in unreadable]


def test_a_string_typed_interest_status_still_counts_as_a_positive():
    """The same endpoint family already answers `step` and `variant` as
    strings, so an untyped `in (1, 2, 3, 4)` test would zero every positive."""
    leads = load_fixture("replied_leads_2026-09-22.json")
    stringified = [dict(l, lt_interest_status=str(l["lt_interest_status"])
                        if l.get("lt_interest_status") is not None else None)
                   for l in leads["cleaning_reactivation"]]
    assert analytics.positives_from_leads(stringified) == 2
    assert analytics.negatives_from_leads(stringified) == 2
    assert analytics.open_positives_from_leads(stringified) == 1


def test_an_unreadable_interest_status_is_counted_and_noted():
    leads = [{"email": "a@b.com", "lt_interest_status": "interested"}]
    assert analytics.count_statuses(leads) == {"unreadable": 1}
    assert analytics.positives_from_leads(leads) == 0


def test_a_lead_returned_twice_by_the_cursor_is_counted_once():
    """An overlapping `starting_after` page hands the same lead back twice.
    One duplicated positive on 300 sends is the difference between hold and
    scale at the 3,000-send decision."""
    leads = load_fixture("replied_leads_2026-09-22.json")
    doubled = dict(leads)
    positive = [l for l in leads["cleaning_reactivation"] if l["lt_interest_status"] == 1][0]
    doubled["cleaning_reactivation"] = list(leads["cleaning_reactivation"]) + [dict(positive)]
    client = FakeInstantly(leads=doubled)
    stats = analytics.collect(client, campaigns=CAMPAIGNS)["cleaning_reactivation"]
    assert stats.positives == 2                   # not 3
    assert stats.duplicate_leads == 1
    assert any("duplicate" in n for n in stats.notes)
    assert any("duplicate" in f for f in V.decide(stats).flags)


def test_real_replies_falls_back_to_human_replies_not_the_total():
    """reply_count is human + automatic. Falling back to it would print a
    2.33% real reply rate where the truth is 1.33%."""
    row = {"reply_count": 7, "reply_count_automatic_unique": 3}
    assert analytics.real_replies(row) == 4
    assert not analytics.has_unique_reply_count(row)
    assert analytics.real_replies({"reply_count_unique": 4, "reply_count": 7}) == 4


def _paused_client():
    campaigns = load_fixture("campaigns_2026-09-22.json")
    campaigns["cleaning_reactivation"]["status"] = 2
    daily = load_fixture("campaign_daily_2026-09-22.json")
    daily["cleaning_reactivation"] = [dict(r, sent=0) for r in daily["cleaning_reactivation"]]
    return FakeInstantly(campaigns=campaigns, daily=daily)


def test_a_paused_campaign_is_flagged_and_does_not_project_a_date():
    """Instantly does not zero daily_limit on a paused campaign, so the old
    fallback handed a campaign sending nothing a confident decision date."""
    stats = analytics.collect(_paused_client(), campaigns=CAMPAIGNS,
                              daily_start="2026-09-08", daily_end="2026-09-22")
    paused = stats["cleaning_reactivation"]
    assert paused.status == 2 and not paused.is_active
    assert paused.daily_limit == 50 and paused.sends_per_day == 0
    cap = V.capacity_from_ids({"instantly": {"active_inboxes": ["a"] * 12,
                                             "warming_domains": ["d"] * 11,
                                             "per_inbox_daily_limit": 25}})
    verdict = V.run(stats, cap, AS_OF)["cleaning_reactivation"]
    assert verdict.eta_current is None and verdict.eta_blended is None
    assert any("paused" in f for f in verdict.flags)


def test_a_campaign_that_has_stopped_sending_gets_no_eta_either():
    daily = load_fixture("campaign_daily_2026-09-22.json")
    daily["cleaning_trigger"] = [dict(r, sent=0) for r in daily["cleaning_trigger"]]
    stats = analytics.collect(FakeInstantly(daily=daily), campaigns=CAMPAIGNS,
                              daily_start="2026-09-08", daily_end="2026-09-22")
    stopped = stats["cleaning_trigger"]
    assert stopped.is_active and stopped.sends_nothing and stopped.sends_per_day == 0
    assert any("no sends in the pulled window" in f for f in V.decide(stopped).flags)


# --------------------------------------------------- what retirement frees
def test_retiring_a_campaign_releases_daily_limit_not_shared_inboxes(stats):
    """All six live campaigns carry the identical 12-inbox email_list, so
    retiring one releases none of them."""
    recruiting = stats["recruiting_outbound"]
    recruiting.sent = 1000
    peers = list(stats.values())
    v = V.decide(recruiting, peers=peers)
    assert v.recommendation == "retire"
    assert "no inboxes" in v.reason
    assert "50 sends/day of daily_limit headroom" in v.reason
    info = V.released_capacity(recruiting, peers)
    assert info["exclusive_inboxes"] == 0 and info["shared_with"] == 5


def test_an_exclusive_inbox_is_reported_as_released(stats):
    recruiting = stats["recruiting_outbound"]
    recruiting.sent = 1000
    recruiting.inbox_emails = list(recruiting.inbox_emails) + ["solo@theadvero.com"]
    recruiting.inboxes = len(recruiting.inbox_emails)
    v = V.decide(recruiting, peers=list(stats.values()))
    assert "1 inbox(es) no other campaign uses" in v.reason


# ------------------------------------------ past the re-test line and stuck
def test_a_campaign_past_the_retest_line_with_no_positives_escalates_to_retire():
    """Without this branch rework_copy points for ever at a line it passed."""
    v = V.decide(_stub(sent=2500, positives=0, niche="bookkeeping"))
    assert v.recommendation == "retire"
    assert v.next_line is None
    assert "2500 sends" in v.reason and "past the 2000-send re-test line" in v.reason


def test_zero_positives_with_open_opportunities_is_flagged_not_retired():
    """Counted positives and Instantly's own opportunity counter disagreeing
    is a data fault; retiring on it would release inboxes over a parse bug."""
    s = _stub(key="recruiting_outbound", niche="recruiting", sent=1000, positives=0)
    s.opportunities = 2
    v = V.decide(s)
    assert v.recommendation == "hold"
    assert v.next_line is None
    assert any("disagree" in f for f in v.flags)


# ------------------------------------------------------ Section 6 labelling
def test_the_real_reply_flag_waits_for_100_sends_per_inbox():
    """300 sends over 12 inboxes is 25 per inbox: a quarter of the threshold's
    own precondition, on one reply."""
    s = _stub(sent=300, real_replies=1, inboxes=12)
    assert V.reply_check_minimum(s) == 1200
    assert not any("real reply" in f for f in V.decide(s).flags)
    s.sent = 1200
    flags = V.decide(s).flags
    assert any("campaign real reply" in f for f in flags)
    assert any("not the Section 6 inbox rule" in f for f in flags)


# ------------------------------------------------------------- projections
def test_the_oct11_column_never_reports_a_date_before_the_capacity_step(stats):
    cap = V.capacity_from_ids({"instantly": {"active_inboxes": ["a"] * 12,
                                             "warming_domains": ["d"] * 11,
                                             "per_inbox_daily_limit": 25}})
    for key, v in V.run(stats, cap, AS_OF).items():
        assert v.eta_oct11 >= V.CAPACITY_STEP_DATE, (key, v.eta_oct11)


def test_the_capacity_multiplier_is_not_applied_twice_after_the_step():
    """After 2026-10-11 the observed rate already contains the step; a second
    multiply projects 3.75x the workspace ceiling."""
    cap = V.capacity_from_ids({"instantly": {"active_inboxes": ["a"] * 12,
                                             "warming_domains": ["d"] * 11,
                                             "per_inbox_daily_limit": 25}})
    assert V.post_step_rate(188, cap, datetime.date(2026, 10, 20)) == 188
    assert V.post_step_rate(50, cap, datetime.date(2026, 9, 22)) == 188
    after = datetime.date(2026, 10, 20)
    s = _stub(sent=2000, positives=3, observed_sends_per_day=188)
    s.sending_days = {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": True}
    v = V.project(V.decide(s), cap, after)
    assert v.eta_current == v.eta_blended == v.eta_oct11


def test_warming_inboxes_still_listed_after_the_step_are_called_out(stats):
    cap = V.capacity_from_ids({"instantly": {"active_inboxes": ["a"] * 12,
                                             "warming_domains": ["d"] * 11,
                                             "per_inbox_daily_limit": 25}})
    V.run(stats, cap, datetime.date(2026, 10, 20))
    assert any("still lists 33 warming inboxes" in n for n in cap.notes)


def test_an_ids_file_with_no_inboxes_is_surfaced_in_the_report_not_just_logged():
    """A renamed key (or settings.load_ids() answering {}) gives 0/day, a 1.00x
    step and three identical ETAs. A logger.warning on a cron run reaches
    nobody, so it has to be in the document."""
    from services.experiments import experiment_log as EL
    from services.experiments import report as report_mod

    cap = V.capacity_from_ids({})
    assert cap.now_per_day == 0 and cap.multiplier == 1.0
    assert any("no active inboxes" in n for n in cap.notes)
    md = report_mod.render([], [], EL.seed_document(), cap, AS_OF, "shadow")
    assert "WARNING" in md and "no active inboxes" in md
