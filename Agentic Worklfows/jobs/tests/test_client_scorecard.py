"""Client scorecard and the F4 retention drafts (brief A12, Blueprint F3/F4).

Clock injected everywhere: 2026-09-22T00:45:00-05:00, which is the hour the
brief was run. Instantly is served through httpx.MockTransport; nothing here
touches a live system and the shadow-mode assertions prove it.
"""
import json
from datetime import date, datetime

import httpx
import pytest
import pytz

from shared import settings
from shared.ghl import GHL
from shared.instantly import Instantly
from shared.store import JsonFileStore
from jobs import client_scorecard as cs

CT = pytz.timezone("America/Chicago")
NOW = CT.localize(datetime(2026, 9, 22, 0, 45))

CLEANING = settings.CAMPAIGNS["cleaning_reactivation"]["id"]
BOOKKEEPING = settings.CAMPAIGNS["bookkeeping_trigger"]["id"]


def daily_row(day, campaign_id, sent=50, replies=0, auto=0, unique=None):
    return {"date": day, "campaign_id": campaign_id, "sent": sent, "contacted": sent,
            "replies": replies, "unique_replies": replies if unique is None else unique,
            "replies_automatic": auto, "unique_replies_automatic": auto, "opportunities": 0}


def lead(email, status, replied=None, contacted=None, company="Acme", **extra):
    row = {"email": email, "company_name": company, "first_name": "Sam", "last_name": "Lee",
           "lt_interest_status": status, "campaign": CLEANING}
    if replied:
        row["timestamp_last_reply"] = replied
    if contacted:
        row["timestamp_last_contact"] = contacted
    row.update(extra)
    return row


# ------------------------------------------------------------------- dates
def test_week_is_the_seven_days_ending_yesterday():
    start, end = cs.week_bounds(NOW)
    assert (start, end) == (date(2026, 9, 15), date(2026, 9, 21))
    assert (end - start).days == 6


def test_week_ending_pins_the_window():
    assert cs.week_bounds(NOW, date(2026, 9, 12)) == (date(2026, 9, 6), date(2026, 9, 12))


def test_a_date_only_string_is_not_shifted_by_the_timezone():
    """The regression that made the week report six of its own days plus one of
    last week's. GET /campaigns/analytics/daily answers {"date": "2026-09-16"};
    read as a timestamp that is midnight UTC, which is 19:00 on the 15th in
    Central."""
    assert cs.parse_day("2026-09-16") == date(2026, 9, 16)
    # A real timestamp still converts, because it carries a time.
    assert cs.parse_day("2026-09-16T02:30:00Z") == date(2026, 9, 15)


def test_the_bug_in_full_a_week_of_daily_rows_all_land_in_that_week():
    rows = [daily_row("2026-09-%02d" % d, CLEANING) for d in range(15, 22)]
    week = cs.sum_daily(rows, date(2026, 9, 15), date(2026, 9, 21))
    prior = cs.sum_daily(rows, date(2026, 9, 8), date(2026, 9, 14))
    assert week["sent"] == 350
    assert prior["sent"] == 0


# ------------------------------------------------------------------ totals
def test_automatic_replies_are_never_subtracted_from_replies():
    """``replies`` already excludes auto-responders in this API, and
    ``replies_automatic`` is a parallel counter, not a subset: bookkeeping is
    1 reply with 6 automatic, which a subset cannot be. Subtracting reported
    0.33% against a hand-measured 1.22% for the same week and then told the
    client to rewrite a sequence that was holding."""
    rows = [
        daily_row("2026-09-16", CLEANING, replies=7, auto=3),
        daily_row("2026-09-16", BOOKKEEPING, replies=1, auto=6),
    ]
    week = cs.sum_daily(rows, date(2026, 9, 15), date(2026, 9, 21))
    assert week["replies"] == 8
    assert week["replies_automatic"] == 9
    assert week["real_replies"] == 8          # not 4, and not 0
    assert "automatic_exceeds_replies" not in week


def test_the_recorded_week_reports_the_reply_rate_that_was_measured_by_hand():
    """The whole recorded week: 1,800 sent, 22 replies. 22/1800 is 1.22%, which
    is the figure the brief measured live. The old formula printed 0.3%, and
    Section 6's removal rule reads the same number."""
    fixtures = cs.load_fixtures()
    week = cs.sum_daily(fixtures["daily"], date(2026, 9, 15), date(2026, 9, 21))
    assert week["sent"] == 1800
    assert week["real_replies"] == 22
    assert round(100.0 * week["real_replies"] / week["sent"], 1) == 1.2


def test_unique_replies_win_over_the_raw_reply_count():
    """A lead who hits reply three times is one reply, which is what Section 6
    counts."""
    rows = [daily_row("2026-09-16", CLEANING, replies=6, unique=2)]
    assert cs.sum_daily(rows, date(2026, 9, 15), date(2026, 9, 21))["real_replies"] == 2


# ---------------------------------------------------------------- statuses
def test_statuses_are_counted_cumulatively_up_the_funnel():
    leads = [
        lead("a@x.co", 1, replied="2026-09-16T10:00:00Z"),
        lead("b@x.co", 2, replied="2026-09-17T10:00:00Z"),
        lead("c@x.co", 4, replied="2026-09-18T10:00:00Z"),
        lead("d@x.co", -1, replied="2026-09-18T10:00:00Z"),
    ]
    out = cs.count_statuses(leads, date(2026, 9, 15), date(2026, 9, 21))
    assert (out["positives"], out["booked"], out["held"], out["closed"]) == (3, 2, 1, 1)


def test_a_positive_with_no_reply_timestamp_is_counted_as_undated_not_dropped():
    out = cs.count_statuses([lead("a@x.co", 1)], date(2026, 9, 15), date(2026, 9, 21))
    assert out["positives"] == 0
    assert out["undated"] == 1
    assert out["positives_all_time"] == 1


def test_a_reply_outside_the_week_is_not_counted_into_it():
    leads = [lead("a@x.co", 1, replied="2026-09-01T10:00:00Z")]
    assert cs.count_statuses(leads, date(2026, 9, 15), date(2026, 9, 21))["positives"] == 0


def test_a_custom_lead_label_is_not_promoted_to_a_signed_deal():
    """config/instantly_api_contract.md: custom lead labels use their own value
    in -30000..30000. A >= ladder read the first one anyone creates as
    interested, booked, held AND closed."""
    out = cs.count_statuses([lead("x@x.co", 1000, replied="2026-09-16T10:00:00Z")],
                            date(2026, 9, 15), date(2026, 9, 21))
    assert (out["positives"], out["booked"], out["held"], out["closed"]) == (0, 0, 0, 0)
    assert out["unknown_status"] == 1


def test_a_custom_lead_label_never_reaches_the_revenue_table():
    client = dict(PERF, value_per_close_usd=50000)
    rows = cs.attribution_rows([lead("x@x.co", 1000, replied="2026-09-16T10:00:00Z",
                                     first_touch_date="2026-05-01")], client, NOW,
                               period=(date(2026, 9, 15), date(2026, 9, 21)))
    assert rows == []


def test_the_same_contact_on_two_campaigns_is_counted_once():
    """A lead moved between campaigns, or the same list uploaded twice, which
    is normal in this workspace."""
    both = [lead("dup@x.co", 1, replied="2026-09-16T10:00:00Z"),
            lead("dup@x.co", 2, replied="2026-09-17T10:00:00Z", company="Acme")]
    deduped, collapsed = cs.dedupe_leads(both)
    assert collapsed == 1
    assert len(deduped) == 1
    # The surviving copy is the one furthest up the funnel.
    assert deduped[0]["lt_interest_status"] == 2
    out = cs.count_statuses(deduped, date(2026, 9, 15), date(2026, 9, 21))
    assert (out["positives"], out["booked"]) == (1, 1)


def test_a_duplicate_lead_does_not_double_the_invoice_line():
    one = [lead("won@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z", first_touch_date="2026-05-01")]
    twice = one + [dict(one[0])]
    period = (date(2026, 9, 15), date(2026, 9, 21))
    values = {"won@x.co": 12000.0}
    single = cs.revenue_attributed(
        cs.attribution_rows(one, PERF, NOW, won_values=values, period=period), PERF)
    doubled = cs.revenue_attributed(
        cs.attribution_rows(cs.dedupe_leads(twice)[0], PERF, NOW, won_values=values,
                            period=period), PERF)
    assert single["contract_value_usd"] == 12000.0
    assert doubled["contract_value_usd"] == 12000.0
    assert len(doubled["counted"]) == 1


# ------------------------------------------------------------- attribution
PERF = {"slug": "perf", "company": "Perf", "deal_type": "performance",
        "attribution_window_days": 180, "commission_rate": 0.25, "active": True}
PERIOD = (date(2026, 9, 15), date(2026, 9, 21))


def test_a_close_inside_the_window_with_a_recorded_value_is_invoiceable():
    leads = [lead("won@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z",
                  first_touch_date="2026-05-01")]
    rows = cs.attribution_rows(leads, PERF, NOW, won_values={"won@x.co": 12000.0})
    assert rows[0]["in_window"] is True
    assert rows[0]["value_source"] == "ghl_opportunity"
    out = cs.revenue_attributed(rows, PERF)
    assert out["invoiceable"] is True
    assert out["contract_value_usd"] == 12000.0
    assert out["commission_usd"] == 3000.0


def test_a_close_outside_the_window_is_excluded_with_the_reason():
    leads = [lead("late@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z",
                  first_touch_date="2025-01-01")]
    out = cs.revenue_attributed(
        cs.attribution_rows(leads, PERF, NOW, won_values={"late@x.co": 9000.0}), PERF)
    assert out["invoiceable"] is False
    assert "outside the window" in out["excluded"][0]["reason"]


def test_a_close_with_no_first_touch_date_is_never_counted():
    """The lead record only carries the LAST contact. Judging a six-month
    window from it would invoice on an invented start date."""
    leads = [lead("nodate@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z",
                  contacted="2026-09-10T10:00:00Z")]
    rows = cs.attribution_rows(leads, PERF, NOW, won_values={"nodate@x.co": 5000.0})
    assert rows[0]["first_touch_source"] == "last_contact_fallback"
    out = cs.revenue_attributed(rows, PERF)
    assert out["invoiceable"] is False
    assert "not recorded" in out["excluded"][0]["reason"]


def test_a_roster_estimate_is_reported_but_never_invoiced():
    client = dict(PERF, value_per_close_usd=7000)
    leads = [lead("est@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z", first_touch_date="2026-08-01")]
    out = cs.revenue_attributed(cs.attribution_rows(leads, client, NOW), client)
    assert out["invoiceable"] is False
    assert out["contract_value_usd"] is None
    assert out["estimated_usd"] == 7000.0
    assert "not invoiceable" in out["excluded"][0]["reason"]


def test_the_attribution_section_names_the_window_and_the_contacts():
    leads = [lead("won@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z",
                  first_touch_date="2026-05-01", company="Northwind")]
    out = cs.revenue_attributed(
        cs.attribution_rows(leads, PERF, NOW, won_values={"won@x.co": 12000.0},
                            period=PERIOD), PERF)
    text = "\n".join(cs._attribution_lines(out))
    assert "180 days" in text
    assert "Northwind" in text
    assert "2026-05-01" in text
    assert "$12,000" in text            # not "12000.0" on the one bold line
    assert "Commission at 25%: **$3,000**" in text


def test_a_close_from_an_earlier_period_is_not_on_this_weeks_invoice_line():
    """offers.md invoices performance deals monthly against this card. A total
    with no period filter re-invoiced an August close every single week until
    the attribution window expired. Nor is it labelled as billed or unbilled:
    invoicing is tracked by hand (OPS-5)."""
    leads = [lead("aug@x.co", 4, replied="2026-08-10T10:00:00Z", timestamp_last_interest_change="2026-08-10T10:00:00Z", first_touch_date="2026-05-01",
                  company="Northwind")]
    rows = cs.attribution_rows(leads, PERF, NOW, won_values={"aug@x.co": 12500.0},
                               period=PERIOD)
    assert rows[0]["in_window"] is True
    assert rows[0]["this_period"] is False
    out = cs.revenue_attributed(rows, PERF)
    assert out["invoiceable"] is False
    assert out["contract_value_usd"] is None
    assert out["commission_usd"] is None
    assert len(out["earlier_periods"]) == 1
    text = "\n".join(cs._attribution_lines(out))
    assert "invoiced" not in text.lower()
    assert "Closed in an earlier period, not part of this week's figure" in text
    assert "nothing new to invoice" in text


def test_a_performance_deal_with_no_window_prints_the_reason_not_a_number():
    """Defaulting the window silently invoices against a period nobody agreed
    to. The card used to state 180 days to the client as coming from
    config/offers.md."""
    client = {"slug": "perf", "company": "Perf", "deal_type": "performance",
              "commission_rate": 0.25, "active": True}
    leads = [lead("won@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z", first_touch_date="2026-05-01")]
    rows = cs.attribution_rows(leads, client, NOW, won_values={"won@x.co": 12000.0},
                               period=PERIOD)
    assert rows[0]["in_window"] is None
    out = cs.revenue_attributed(rows, client)
    assert out["invoiceable"] is False
    assert out["window_days"] is None
    text = "\n".join(cs._attribution_lines(out))
    assert "180" not in text
    assert "not set for this deal" in text


def test_a_performance_client_with_no_commission_rate_is_a_validation_error():
    problems = cs._validate_client({"slug": "x", "deal_type": "performance",
                                    "attribution_window_days": 180})
    assert any("commission_rate" in p for p in problems)


def test_a_performance_card_with_no_commission_rate_says_so_instead_of_printing_one_number():
    client = dict(PERF)
    client.pop("commission_rate")
    leads = [lead("won@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z", first_touch_date="2026-05-01")]
    out = cs.revenue_attributed(
        cs.attribution_rows(leads, client, NOW, won_values={"won@x.co": 12500.50},
                            period=PERIOD), client)
    text = "\n".join(cs._attribution_lines(out))
    assert "$12,500.50" in text
    assert "12500.5" not in text
    assert "No commission rate is recorded" in text


def test_a_performance_client_with_no_source_does_not_claim_there_is_nothing_to_invoice():
    """Nothing was read, so nothing could have closed. "There is nothing to
    invoice" is the unmeasured zero the module's own rule 1 refuses."""
    out = cs.revenue_attributed([], PERF, measured=False)
    assert out["invoiceable"] is None
    text = "\n".join(cs._attribution_lines(out))
    assert "nothing to invoice" not in text
    assert "No source" in text


def test_a_first_touch_recorded_in_the_store_makes_a_close_invoiceable(tmp_path):
    """The lead record never carries first_touch_date and nothing in the repo
    writes it, so without this lookup a reactivation deal can never produce an
    invoice line at all."""
    store = JsonFileStore(tmp_path / "s.json")
    store.set("first_touch:won@x.co", "2026-05-01")
    leads = [lead("won@x.co", 4, replied="2026-09-18T10:00:00Z", timestamp_last_interest_change="2026-09-18T10:00:00Z")]
    touches = cs.first_touch_index(store, leads, [])
    assert touches == {"won@x.co": date(2026, 5, 1)}
    rows = cs.attribution_rows(leads, PERF, NOW, won_values={"won@x.co": 12000.0},
                               first_touches=touches, period=PERIOD)
    assert rows[0]["first_touch_source"] == "recorded"
    assert cs.revenue_attributed(rows, PERF)["invoiceable"] is True


def test_the_won_opportunity_read_follows_the_cursor_past_the_first_page():
    """Past 100 lifetime wins a contact that closed this week sits on page 2,
    loses its monetaryValue and drops off the invoice with nothing saying the
    read was partial."""
    pages = []

    class FakeGHL(object):
        token = "t"

        def search_opportunities(self, pipeline_id=None, stage_id=None, limit=100,
                                 start_after_id=None, start_after=None):
            pages.append(start_after_id)
            if start_after_id is None:
                items = [{"id": "opp%d" % i, "contact": {"email": "a%d@x.co" % i},
                          "monetaryValue": 100, "updatedAt": "2026-09-01"} for i in range(100)]
            else:
                items = [{"id": "last", "contact": {"email": "page2@x.co"},
                          "monetaryValue": 9000}]
            return {"opportunities": items}

    notes = []
    values, touches = cs.pull_won_values(FakeGHL(), PERF, notes)
    assert pages == [None, "opp99"]
    assert values["page2@x.co"] == 9000.0
    assert notes == []


# ---------------------------------------------------------------- "no source"
def test_a_client_with_no_campaigns_reports_no_source_not_zero(tmp_env, shadow_mode):
    client = {"slug": "quiet", "company": "Quiet Co", "deal_type": "flat", "active": True}
    result = cs.run_client(client, NOW, None, [])
    assert result["metrics"]["sent"] is None
    assert cs.NO_SOURCE in result["scorecard"]
    assert "| Sent | no source |" in result["scorecard"]
    assert "| Sent | 0 |" not in result["scorecard"]


def test_the_plan_says_so_rather_than_judging_a_week_it_could_not_measure():
    bets = cs.fallback_plan({"slug": "quiet"}, {"sent": None}, {"sent": None})
    assert len(bets) == 1
    assert "Nothing here was measured" in bets[0]


def test_a_previous_week_of_zero_is_not_called_steady():
    bets = cs.fallback_plan({}, {"sent": 300, "real_replies": 4, "positives": 1, "booked": 1},
                            {"sent": 0})
    assert any("nothing to compare against" in b for b in bets)


# ------------------------------------------------------------------ roster
def test_the_store_overrides_the_seed_file_field_by_field(tmp_path):
    store = JsonFileStore(tmp_path / "s.json")
    store.set("client:man-transformed", {"contact_email": "mike@example.com"})
    clients, notes = cs.load_roster(store=store)
    mike = [c for c in clients if c["slug"] == "man-transformed"][0]
    assert mike["contact_email"] == "mike@example.com"
    assert mike["company"] == "Man Transformed"      # seed fields survive
    assert notes == []


def test_a_performance_deal_with_no_attribution_window_is_a_validation_error():
    problems = cs._validate_client({"slug": "x", "deal_type": "performance"})
    assert any("attribution_window_days" in p for p in problems)


def test_a_term_end_that_does_not_match_the_start_plus_term_is_caught():
    problems = cs._validate_client({"slug": "x", "start_date": "2026-09-17",
                                    "term_days": 30, "term_end": "2026-10-20"})
    assert any("term_end" in p for p in problems)


def test_the_seed_roster_itself_validates():
    clients, notes = cs.load_roster(include_inactive=True)
    assert notes == [], notes
    assert any(c["slug"] == "man-transformed" for c in clients)


# -------------------------------------------------------------- templates
def test_every_shipped_retention_template_parses():
    templates, notes = cs.load_templates()
    assert notes == [], notes
    assert [t.day for t in templates] == [7, 21, 25, 30]


def test_an_unknown_placeholder_is_left_in_the_text_and_reported():
    """A draft that silently contains nothing where a number should be is the
    one that goes out wrong."""
    text, missing = cs.fill("We sent {sent} and booked {booked}.", {"sent": 300})
    assert text == "We sent 300 and booked {booked}."
    assert missing == ["booked"]


def test_a_price_not_in_the_offer_sheet_is_refused():
    assert cs.price_in_offers(2000, "commission is 20 to 30 percent") is False
    assert cs.price_in_offers(24000, "Guarantee $24,000/yr in new contracts") is True


def test_a_price_that_is_only_a_substring_of_an_offer_sheet_price_is_refused():
    """The substring test passed 500 (inside "$2,500"), 15 (inside "15,000"),
    200, 24, 20, 5 and 1 against the real sheet, and refused 750 and 1500. It
    was the only guard on money in client-facing copy."""
    sheet = "Guarantee **$24,000/yr** or money back plus a $200 gift card."
    assert cs.price_in_offers(24000, sheet) is True
    assert cs.price_in_offers(200, sheet) is True
    for refused in (24, 2400, 4000, 20, 2, 0, 1):
        assert cs.price_in_offers(refused, sheet) is False, refused


def test_the_real_offer_sheet_does_not_approve_a_price_it_never_states():
    figures = cs.offer_figures()
    assert 24000.0 in figures                     # "$24,000/yr", a stated guarantee
    for refused in (500, 750, 1500, 2000, 528.64):
        assert cs.price_in_offers(refused) is False, refused


def test_a_figure_the_offer_sheet_marks_to_confirm_is_not_quotable():
    """offers.md carries "$2,500-5,000/mo (TO CONFIRM with Lorenzo before
    quoting in writing)". The old test passed it anyway."""
    assert cs.price_in_offers(2500) is False
    assert cs.price_in_offers(5000) is False


def test_a_proof_point_figure_is_not_a_price():
    """The $150M roofer and the $1.5k build are somebody else's numbers."""
    assert cs.price_in_offers(1500) is False
    assert cs.price_in_offers(150000000) is False


def test_a_dollar_figure_in_renewal_terms_is_checked_against_the_offer_sheet():
    """day25_renewal.md has no price placeholder at all: the money in the email
    lives in {renewal_terms}, operator free text that reaches the reader."""
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day25_renewal"][0]
    client = dict(MIKE, renewal_price_usd=24000,
                  renewal_terms="Same again at $500 a month.",
                  expansion_line="We add the second location.")
    sheet = "Guarantee **$24,000/yr** in new contracts."
    draft = cs.render_retention(template, client, date(2026, 10, 12), 20, TERM_WEEK, NOW,
                                term=TERM_TO_DATE, offers_md=sheet)
    assert draft["ready"] is False
    assert any("$500" in b and "config/offers.md" in b for b in draft["blockers"])


def test_a_price_written_in_words_is_checked_and_a_count_is_not():
    """"2,000 dollars" is the same promise as "$2,000". "1,800 sent" is a
    count, and flagging it would block a true draft."""
    sheet = "Guarantee **$24,000/yr**."
    assert cs.unapproved_prices("Same again at 2,000 dollars a month.", sheet) == ["$2,000"]
    assert cs.unapproved_prices("1,800 sent and 22 replies.", sheet) == []
    assert cs.unapproved_prices("The guarantee is $24,000 a year.", sheet) == []


def test_a_roster_value_with_an_em_dash_blocks_the_draft():
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day25_renewal"][0]
    client = dict(MIKE, renewal_price_usd=24000,
                  renewal_terms="Same again — month to month.",
                  expansion_line="We add the second location.")
    draft = cs.render_retention(template, client, date(2026, 10, 12), 20, TERM_WEEK, NOW,
                                term=TERM_TO_DATE, offers_md="Guarantee **$24,000/yr**.")
    assert draft["ready"] is False
    assert any("em dash" in b for b in draft["blockers"])


def test_a_roster_value_with_an_exclamation_mark_blocks_the_draft():
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day25_renewal"][0]
    client = dict(MIKE, renewal_price_usd=24000,
                  renewal_terms="Same again, and it is working!",
                  expansion_line="We add the second location.")
    draft = cs.render_retention(template, client, date(2026, 10, 12), 20, TERM_WEEK, NOW,
                                term=TERM_TO_DATE, offers_md="Guarantee **$24,000/yr**.")
    assert draft["ready"] is False
    assert any("exclamation" in b for b in draft["blockers"])


# ------------------------------------------------------------ F4 retention
MIKE = {"slug": "man-transformed", "name": "Mike", "company": "Man Transformed",
        "product_name": "Content and lead system (30 day)", "deal_type": "flat",
        "price_usd": 2000, "start_date": "2026-09-17", "term_days": 30,
        "term_end": "2026-10-17", "active": True}


def test_mikes_day_25_renewal_falls_on_2026_10_12():
    """The blueprint's date, and the one the brief names."""
    templates, _ = cs.load_templates()
    due = dict((t.id, d) for t, d, _ in cs.due_retention(MIKE, NOW, templates, lookahead_days=40))
    assert due["day25_renewal"] == date(2026, 10, 12)


def test_a_touch_that_lands_on_a_weekend_rolls_to_the_next_business_day():
    """Day 30 from 2026-09-17 is 2026-10-17, a Saturday. The rest of the
    cadence holds Mon-Fri and a due date that quietly breaks it puts a weekend
    date on Lorenzo's list and in a filename."""
    templates, _ = cs.load_templates()
    due = dict((t.id, d) for t, d, _ in cs.due_retention(MIKE, NOW, templates, lookahead_days=40))
    assert date(2026, 10, 17).weekday() == 5
    assert due["day30_referral_review"] == date(2026, 10, 19)
    assert due["day30_referral_review"].weekday() == 0


def test_mikes_day_25_renewal_is_blocked_until_it_has_real_numbers_and_a_price():
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day25_renewal"][0]
    empty_week = {k: None for k in ("sent", "positives", "booked", "held", "closed")}
    draft = cs.render_retention(template, MIKE, date(2026, 10, 12), 20, empty_week, NOW)
    assert draft["ready"] is False
    assert draft["auto_ok"] is False
    assert any("missing metric: sent" == b for b in draft["blockers"])
    assert any("config/offers.md" in b for b in draft["blockers"])
    # The body is still produced, with the gaps visible rather than blank.
    assert "{sent}" in draft["body"]
    assert draft["body"].rstrip().endswith("Lorenzo")


TERM_WEEK = {"sent": 1800, "replies": 22, "real_replies": 22, "positives": 4,
             "booked": 1, "held": 1, "closed": 0, "through": "2026-09-21", "days_measured": 7}
TERM_TO_DATE = {"sent": 6200, "replies": 74, "real_replies": 74, "positives": 11,
                "booked": 3, "held": 2, "closed": 1, "through": "2026-10-11",
                "days_measured": 25, "start": "2026-09-17"}


def test_a_day_25_draft_quotes_the_term_to_date_totals_not_one_weeks():
    """The copy says "where it stands after N days". Filling it from the
    reporting week rendered a seven-day 1,800 as the whole term, and on the
    live path the window can be a single morning."""
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day25_renewal"][0]
    assert template.metrics_scope == cs.TERM_SCOPE
    draft = cs.render_retention(template, MIKE, date(2026, 10, 12), 20, TERM_WEEK, NOW,
                                term=TERM_TO_DATE)
    assert "after 25 days" in draft["body"]
    assert "6200 sent" in draft["body"]
    assert "1800" not in draft["body"]
    # ... and it says what the numbers actually cover.
    assert "2026-10-11" in draft["body"]


def test_a_day_21_draft_and_its_case_study_quote_the_term_not_the_week():
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day21_results"][0]
    draft = cs.render_retention(template, dict(MIKE, headline="Two calls came out of it.",
                                               starting_point="No follow-up at all.",
                                               what_we_built="A weekly sequence.",
                                               client_quote="It worked."),
                                date(2026, 10, 8), 16, TERM_WEEK, NOW, term=TERM_TO_DATE)
    assert "6200 sent" in draft["body"]
    assert "What happened in the first 25 days: 6200 sent" in draft["body"]
    assert "1800" not in draft["body"]


def test_a_term_draft_with_no_term_numbers_is_blocked_rather_than_filled_from_the_week():
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day25_renewal"][0]
    draft = cs.render_retention(template, MIKE, date(2026, 10, 12), 20, TERM_WEEK, NOW, term=None)
    assert draft["ready"] is False
    assert any("missing metric: sent" == b for b in draft["blockers"])
    assert "1800" not in draft["body"]


def test_the_day_7_check_in_is_ready_because_it_carries_no_numbers():
    templates, _ = cs.load_templates()
    template = [t for t in templates if t.id == "day07_checkin"][0]
    draft = cs.render_retention(template, MIKE, date(2026, 9, 24), 2, {}, NOW)
    assert draft["ready"] is True
    assert draft["auto_ok"] is True
    assert "Mike," in draft["body"]


def test_a_retention_draft_never_breaks_the_client_copy_rules():
    render_mod = cs.retro_modules()[2]
    if render_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    templates, _ = cs.load_templates()
    week = {"sent": 300, "replies": 4, "real_replies": 4, "positives": 2,
            "booked": 1, "held": 1, "closed": 0}
    client = dict(MIKE, headline="Two calls came out of the first month.",
                  review_link="https://example.com/review",
                  renewal_terms="Same again, month to month.",
                  expansion_line="We add the second location.",
                  starting_point="No follow-up at all.", what_we_built="A weekly sequence.",
                  client_quote="It worked.")
    for template in templates:
        draft = cs.render_retention(template, client, date(2026, 10, 12), 1, week, NOW,
                                    term=TERM_TO_DATE, render_mod=render_mod)
        assert cs.copy_problems(draft["body"], render_mod) == [], (template.id, draft["body"])
        # Every placeholder filled, so the only blocker left is the price gate.
        assert [b for b in draft["blockers"] if "config/offers.md" not in b] == [], template.id


def test_a_recently_overdue_touch_is_included_whatever_the_lookahead():
    templates, _ = cs.load_templates()
    late = dict(MIKE, start_date="2026-09-08")      # day 7 was 2026-09-15, six days ago
    due = [t.id for t, _, days in cs.due_retention(late, NOW, templates, lookahead_days=0)
           if days < 0]
    assert "day07_checkin" in due


def test_a_touch_far_past_due_stops_being_listed_instead_of_being_urgent_forever():
    """Without the floor Mike's four touches came back on every run at -26,
    then -68, then -250 days, and run_scorecards sets the digest to high
    priority whenever anything is overdue."""
    templates, _ = cs.load_templates()
    notes = []
    ancient = dict(MIKE, start_date="2025-01-01")
    due = cs.due_retention(ancient, NOW, templates, lookahead_days=7, notes=notes)
    assert due == []
    assert len(notes) == 4
    assert all("no longer listed" in note for note in notes)


def test_a_retention_touch_already_marked_sent_is_not_re_rendered(tmp_path):
    templates, _ = cs.load_templates()
    store = JsonFileStore(tmp_path / "s.json")
    before = [t.id for t, _, _ in cs.due_retention(MIKE, NOW, templates, lookahead_days=40,
                                                   store=store)]
    assert "day07_checkin" in before
    cs.mark_retention_handled(store, MIKE["slug"], "day07_checkin", NOW)
    notes = []
    after = [t.id for t, _, _ in cs.due_retention(MIKE, NOW, templates, lookahead_days=40,
                                                  store=store, notes=notes)]
    assert "day07_checkin" not in after
    assert any("marked handled" in note for note in notes)
    assert store.get(cs.retention_key(MIKE["slug"], "day07_checkin"))["handled_at"]


def test_a_client_whose_term_ended_stops_producing_overdue_touches():
    """Mike's 30-day term ends 2026-10-17. Five weeks later nothing is due."""
    templates, _ = cs.load_templates()
    later = CT.localize(datetime(2026, 11, 20, 9, 0))
    assert cs.due_retention(MIKE, later, templates, lookahead_days=7) == []


def test_rendering_a_draft_does_not_retire_it_so_the_runbook_can_regenerate(tmp_path):
    """The runbook regenerates Mike's drafts on purpose. A render-retires rule
    would make the second run produce nothing at all."""
    templates, _ = cs.load_templates()
    store = JsonFileStore(tmp_path / "s.json")
    first = cs.due_retention(MIKE, NOW, templates, lookahead_days=40, store=store)
    second = cs.due_retention(MIKE, NOW, templates, lookahead_days=40, store=store)
    assert [t.id for t, _, _ in first] == [t.id for t, _, _ in second]


# ------------------------------------------------------- end to end, mocked
def transport(recorder=None):
    daily = [daily_row("2026-09-%02d" % d, CLEANING, sent=50, replies=1, auto=0)
             for d in range(15, 22)]
    leads = [lead("a@x.co", 1, replied="2026-09-16T10:00:00Z"),
             lead("b@x.co", 2, replied="2026-09-17T10:00:00Z")]

    def handler(request):
        if recorder is not None:
            recorder.append(request)
        path = request.url.path
        if request.method == "GET" and path == "/api/v2/campaigns/analytics/daily":
            return httpx.Response(200, json=daily)
        if request.method == "POST" and path == "/api/v2/leads/list":
            return httpx.Response(200, json={"items": leads})
        return httpx.Response(404, json={"message": "unmocked %s %s" % (request.method, path)})

    return httpx.MockTransport(handler)


def client_with_campaign():
    return {"slug": "acme", "name": "Dana", "company": "Acme Cleaning",
            "product_name": "Reactivation system", "deal_type": "flat",
            "start_date": "2026-09-17", "term_days": 30, "term_end": "2026-10-17",
            "instantly_campaign_ids": [CLEANING], "active": True}


def test_end_to_end_renders_a_card_and_logs_one_row(tmp_env, shadow_mode, monkeypatch):
    from shared import job_log
    rows = []
    monkeypatch.setattr(job_log, "log_run", lambda *a, **k: rows.append(a))
    monkeypatch.setattr(cs, "log_run", lambda *a, **k: rows.append(a))
    out = cs.run_scorecards(
        NOW, clients=[client_with_campaign()],
        instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    assert out["status"].startswith("dry_run")
    assert len(rows) == 1
    card = out["results"][0]
    assert card["metrics"]["sent"] == 350
    assert card["metrics"]["positives"] == 2
    assert "Acme Cleaning" in card["scorecard"]
    assert any(str(p).endswith("scorecard_2026-09-21.md") for p in out["written"])


def test_delivering_a_scorecard_is_listed_for_a_manual_send_and_sends_nothing(tmp_env, shadow_mode):
    client = dict(client_with_campaign(), contact_email="dana@acme.example")
    out = cs.run_scorecards(
        NOW, clients=[client],
        instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    assert len(out["deliveries"]) == 1
    delivery = out["deliveries"][0]
    assert delivery["sent"] is False
    assert delivery["system"] == "gmail"
    assert delivery["payload"]["to"] == "dana@acme.example"


def test_ops15_no_orphan_live_write_intent_for_a_send_that_never_happens(tmp_env, monkeypatch):
    """guard_write in live mode opens a live_write_intent row that the send is
    expected to close. There is no send, so the row hung open every run."""
    from shared import job_log
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    monkeypatch.setattr(settings, "guard_write", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("guard_write called for a write that never happens")))
    client = dict(client_with_campaign(), contact_email="dana@acme.example")
    cs.run_scorecards(
        NOW, clients=[client],
        instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    path = job_log.job_log_path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    assert "live_write_intent" not in text


def test_an_internal_pseudo_client_is_never_queued_for_delivery(tmp_env, shadow_mode):
    out = cs.run_scorecards(
        NOW, clients=[cs.self_client()],
        instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    assert out["deliveries"] == []


def test_the_run_makes_no_write_request_of_any_kind(tmp_env, shadow_mode):
    seen = []
    cs.run_scorecards(
        NOW, clients=[client_with_campaign()],
        instantly=Instantly(api_key="t", transport=transport(seen)),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    assert seen, "the mock transport was never called"
    for request in seen:
        assert request.method in ("GET", "POST")
        # leads/list is a POST-shaped READ (shared/README.md). Nothing else may
        # be a POST, and no PATCH, PUT or DELETE may appear at all.
        if request.method == "POST":
            assert request.url.path.endswith("/leads/list"), request.url.path


def test_a_client_with_no_campaigns_does_not_inherit_every_campaign(tmp_env, shadow_mode):
    """scorecard.client_funnel reads campaign_keys=None as EVERY campaign, so a
    client with none of their own must not be rendered with the A10 card."""
    out = cs.run_scorecards(
        NOW, clients=[MIKE],
        instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
    )
    card = out["results"][0]
    assert card["card_source"] == "built-in"
    assert card["metrics"]["sent"] is None


def test_the_scorecard_passes_the_client_copy_rules(tmp_env, shadow_mode):
    render_mod = cs.retro_modules()[2]
    if render_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    out = cs.run_scorecards(
        NOW, clients=[client_with_campaign()],
        instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    assert out["results"][0]["copy_problems"] == []


def test_a_missing_retro_generator_is_noted_and_the_job_still_runs(tmp_env, shadow_mode, monkeypatch):
    monkeypatch.setattr(cs, "retro_modules", lambda: (None, None, None))
    out = cs.run_scorecards(
        NOW, clients=[client_with_campaign()],
        instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    assert out["results"][0]["card_source"] == "built-in"
    assert any("not importable" in n for n in out["notes"])


def test_fixtures_replay_stamps_every_card_as_a_replay(tmp_env, shadow_mode):
    out = cs.run_scorecards(
        NOW, clients=[cs.self_client()], instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
        fixtures=cs.load_fixtures(),
    )
    assert "FIXTURES REPLAY" in out["results"][0]["scorecard"]
    assert out["results"][0]["replay"] is True
    # The digest is what --now pushes, and it used to carry no marker at all.
    assert "REPLAY Advero (internal)" in out["digest"]
    assert any(str(p).endswith(".replay.md") for p in out["written"])
    assert not any(str(p).endswith("scorecard_2026-09-21.md") for p in out["written"])


def test_a_fixtures_replay_never_hands_a_real_client_advero_numbers(tmp_env, shadow_mode):
    """The fixtures are Advero's own recorded leads and daily rows. Injected
    for every client, they rendered Mike (no campaigns at all, must read "no
    source") as 1800 sent, 22 replies, 4 interested."""
    out = cs.run_scorecards(
        NOW, clients=[MIKE], instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
        fixtures=cs.load_fixtures(),
    )
    card = out["results"][0]
    assert card["replay"] is False
    assert card["metrics"]["sent"] is None
    assert "1800" not in card["scorecard"]
    assert "| Sent | no source |" in card["scorecard"]
    assert any("NOT injected" in n for n in card["notes"])


def test_a_fixtures_replay_never_writes_a_client_facing_draft_carrying_the_recorded_numbers(
        tmp_env, shadow_mode):
    out = cs.run_scorecards(
        NOW, clients=[MIKE], instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards", lookahead_days=40,
        fixtures=cs.load_fixtures(),
    )
    drafts = [d for d in out["results"][0]["drafts"]]
    assert drafts, "the lookahead should reach Mike's touches"
    for draft in drafts:
        assert "1800" not in draft["body"]
        assert "22" not in draft["body"].replace("2026", "")
    for path in out["written"]:
        with open(str(path), encoding="utf-8") as fh:
            assert "1800" not in fh.read()


def test_a_replay_run_queues_no_delivery_for_anyone(tmp_env, shadow_mode):
    clients = [cs.self_client(), dict(MIKE, contact_email="mike@example.com")]
    out = cs.run_scorecards(
        NOW, clients=clients, instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
        fixtures=cs.load_fixtures(),
    )
    assert out["deliveries"] == []
    assert any("replay run" in n for n in out["notes"])


# ------------------------------------------------ what the client never reads
def test_the_client_card_carries_no_retention_schedule_and_no_run_notes(tmp_env, shadow_mode):
    """A client reading their own card used to learn that a renewal note was
    scheduled for day 25, that their price was not in Lorenzo's offer sheet,
    and that their account had no campaigns wired up."""
    out = cs.run_scorecards(
        NOW, clients=[MIKE], instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards", lookahead_days=40,
    )
    card = out["results"][0]
    body = card["scorecard"]
    for leak in ("Retention touches due", "day 25", "config/offers.md", "Notes from this run",
                 "instantly_campaign_ids", "NOT READY"):
        assert leak not in body, leak
    appendix = card["operator_appendix"]
    assert "Retention touches due" in appendix
    assert "instantly_campaign_ids" in appendix
    assert "Internal." in appendix


def test_the_delivery_guard_carries_the_client_body_not_the_appendix(tmp_env, shadow_mode):
    client = dict(client_with_campaign(), contact_email="dana@acme.example")
    out = cs.run_scorecards(
        NOW, clients=[client], instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    result = out["results"][0]
    assert out["deliveries"][0]["payload"]["body_markdown_chars"] == len(result["scorecard"])
    assert len(result["scorecard"]) < len(result["scorecard"] + result["operator_appendix"])


# ------------------------------------------------------- the A10 card path
SUNDAY = CT.localize(datetime(2026, 9, 27, 19, 0))


def a10_week(now=SUNDAY):
    """A real A10 Week off its recorded fixture, so the card path is exercised
    rather than mocked. A10's window is Monday 00:00 CT to now, so only a
    Sunday run gives it seven days."""
    collect_mod = cs.retro_modules()[0]
    if collect_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    with open(str(settings.BASE_DIR / "services" / "retro" / "fixtures" / "week_2026-09.json"),
              encoding="utf-8") as fh:
        return collect_mod.collect_week(now, fixtures=json.load(fh))


def test_the_a10_card_carries_the_run_notes_and_the_how_to_read_footer(tmp_env, shadow_mode):
    """A truncated pull, a failed campaign read and the "no source is not
    zero" line used to vanish whenever the A10 renderer produced the card, on
    a document used as an invoice basis."""
    _collect, scorecard_mod, render_mod = cs.retro_modules()
    if scorecard_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    result = cs.run_client(client_with_campaign(), SUNDAY,
                           Instantly(api_key="t", transport=transport()), [],
                           ghl=GHL(token=None), week_obj=a10_week(),
                           scorecard_mod=scorecard_mod, render_mod=render_mod)
    assert result["card_source"] == "retro_scorecard (A10)"
    assert "## How to read this" in result["scorecard"]
    assert "no source" in result["scorecard"]
    assert result["copy_problems"] == []


def test_a_one_day_retro_window_is_refused_rather_than_called_a_week(tmp_env, shadow_mode):
    """Run live on 2026-09-22 the A10 window was Mon 21 to Tue 22 and the card
    came back titled "week ending 2026-09-22, 300 sent" against a real week of
    1,800. For a performance deal that document is the invoice."""
    _collect, scorecard_mod, render_mod = cs.retro_modules()
    if scorecard_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    result = cs.run_client(client_with_campaign(), NOW,
                           Instantly(api_key="t", transport=transport()), [],
                           ghl=GHL(token=None), week_obj=a10_week(NOW),
                           scorecard_mod=scorecard_mod, render_mod=render_mod)
    assert result["card_source"] == "built-in"
    assert result["week"] == {"start": "2026-09-15", "end": "2026-09-21"}
    assert result["metrics"]["sent"] == 350           # the whole seven days
    assert any("is 2 day(s), so it was not used" in n for n in result["notes"])


# ------------------------------------------- unmeasured is not zero
def failing_daily_transport():
    leads = [lead("a@x.co", 1, replied="2026-09-16T10:00:00Z")]

    def handler(request):
        if request.url.path == "/api/v2/campaigns/analytics/daily":
            return httpx.Response(500, json={"message": "boom"})
        if request.method == "POST" and request.url.path == "/api/v2/leads/list":
            return httpx.Response(200, json={"items": leads})
        return httpx.Response(404, json={"message": "unmocked"})

    return httpx.MockTransport(handler)


def test_a_failed_daily_pull_is_not_reported_as_a_week_of_zeros(tmp_env, shadow_mode):
    """Instantly was up and sending 300 that week. A 500, a rotated key or an
    exhausted rate limit used to print "Sent 0, Replies 0" as a measurement
    and tell the client nothing was sent."""
    out = cs.run_scorecards(
        NOW, clients=[client_with_campaign()],
        instantly=Instantly(api_key="t", transport=failing_daily_transport(), sleep=lambda s: None),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    card = out["results"][0]
    assert card["metrics"]["sent"] is None
    assert "| Sent | no source |" in card["scorecard"]
    assert "Nothing sent this week" not in card["scorecard"]
    assert "sent 0" not in out["digest"]


def test_a_failed_daily_pull_is_visible_on_the_card_not_only_in_the_job_log(tmp_env, shadow_mode):
    out = cs.run_scorecards(
        NOW, clients=[client_with_campaign()],
        instantly=Instantly(api_key="t", transport=failing_daily_transport(), sleep=lambda s: None),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=True, send_digest=False,
        out_dir=tmp_env / "cards",
    )
    card = out["results"][0]
    assert "could not be read" in card["scorecard"]
    assert any("could not be read" in n for n in out["digest"].splitlines())


def test_injected_send_rows_with_no_lead_source_leave_the_status_columns_blank():
    result = cs.run_client(client_with_campaign(), NOW, None, [], week_ending=date(2026, 9, 21),
                           daily=[daily_row("2026-09-%02d" % d, CLEANING) for d in range(15, 22)])
    assert result["metrics"]["sent"] == 350
    assert result["metrics"]["positives"] is None
    assert "| Interested | no source |" in result["scorecard"]


def test_a_performance_client_with_no_source_says_so_in_the_digest(tmp_env, shadow_mode):
    client = {"slug": "perf", "company": "Perf Co", "deal_type": "performance",
              "attribution_window_days": 180, "commission_rate": 0.25, "active": True,
              "instantly_campaign_ids": []}
    out = cs.run_scorecards(
        NOW, clients=[client], instantly=None, ghl=None,
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
    )
    assert "invoiceable: no source, nothing measured" in out["digest"]
    assert "nothing to invoice" not in out["results"][0]["scorecard"]


def test_a_truncated_lead_pull_says_so_on_the_card(tmp_env, shadow_mode):
    notes = cs.Notes()
    leads, truncated = cs.pull_leads(_capped_instantly(), [CLEANING], notes)
    assert truncated is True
    assert any("floor" in n for n in notes.client_facing())
    footer = "\n".join(cs._footer_lines(notes))
    assert "floor" in footer


def _capped_instantly():
    class Walk(object):
        truncated = True

        def __iter__(self):
            return iter([])

    class Capped(object):
        def iterate(self, *a, **k):
            return Walk()

    return Capped()


# ----------------------------------------------------- the reply-rate verdict
def test_the_reply_rate_verdict_needs_a_sample_before_it_judges():
    """Section 6's line is "< 1% after 100 sent per inbox". On 25 sends zero
    replies is the expected outcome, and a client in week one must not be told
    to rewrite their sequence on it."""
    for sent in (25, 40, 99, 299):
        bets = cs.fallback_plan({}, {"sent": sent, "real_replies": 0}, {})
        assert "too few to judge" in bets[0], sent
        assert "under the 1% line" not in bets[0]


def test_the_bets_hook_is_refused_unless_it_declares_itself_free(monkeypatch):
    """The old version imported jobs.retro_packet (the module whose whole job
    is the paid Opus call) and called the first attribute it found named
    client_bets, once per client per run, with none of retro_packet's week
    claim. The except branch catches a hook that raises, not one that bills."""
    import types
    module = types.ModuleType("fake_bets")
    module.client_bets = lambda client, week, prior: ["bet"]
    monkeypatch.setitem(__import__("sys").modules, "fake_bets", module)
    monkeypatch.setattr(cs, "CLIENT_BETS_MODULE", "fake_bets")
    assert cs._retro_renderer() is None              # no CLIENT_BETS_IS_FREE
    module.CLIENT_BETS_IS_FREE = True
    assert cs._retro_renderer() is module.client_bets


def test_the_bets_hook_is_never_discovered_in_the_billing_module():
    assert cs.CLIENT_BETS_MODULE == "services.retro.lessons"
    assert "retro_packet" not in cs.CLIENT_BETS_MODULE


def test_the_verdict_still_fires_once_there_is_a_sample():
    bets = cs.fallback_plan({}, {"sent": 1800, "real_replies": 3}, {})
    assert "under the 1% line" in bets[0]


# ------------------------------------------------------------ offline safety
def test_passing_instantly_none_means_offline_and_makes_no_request(tmp_env, shadow_mode,
                                                                   monkeypatch):
    """A caller that passes None meaning "no client" used to get live traffic
    to api.instantly.ai, up to 20 lead pages per campaign."""
    def explode(*a, **k):
        raise AssertionError("run_scorecards built a live Instantly client")

    monkeypatch.setattr(cs, "Instantly", explode)
    out = cs.run_scorecards(
        NOW, clients=[client_with_campaign()], instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
    )
    card = out["results"][0]
    assert card["metrics"]["sent"] is None
    assert "| Sent | no source |" in card["scorecard"]


# ------------------------------------------------- notes that must not vanish
def test_a_client_whose_campaigns_are_not_in_ids_json_is_not_told_no_campaigns_are_assigned(
        tmp_env, shadow_mode):
    """The guard read config/ids.json, which only holds Advero's own six
    campaigns, so every real client card said "no campaigns are assigned to
    you" directly under a table of their own real sends."""
    client = dict(client_with_campaign(), instantly_campaign_ids=["11111111-2222-3333-4444-555555555555"])

    class Week(object):
        pass

    out = cs.run_client(client, NOW, Instantly(api_key="t", transport=transport()), [],
                        ghl=GHL(token=None), week_obj=Week(), scorecard_mod=object())
    notes = " ".join(out["notes"])
    assert "no campaigns are assigned" not in notes
    assert "not registered in config/ids.json" in notes
    assert out["metrics"]["sent"] == 350


def test_an_unreadable_template_directory_reaches_the_digest(tmp_env, shadow_mode):
    """Mike's day-25 renewal has a hard 2026-10-12 deadline. A moved directory
    used to make the job exit 0 every week with the touch simply never
    drafted."""
    from pathlib import Path as _Path
    out = cs.run_scorecards(
        NOW, clients=[MIKE], instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
        templates_dir=_Path("/nonexistent/retention"),
    )
    assert out["counts"]["drafts_ready"] == 0
    assert "NO RETENTION TEMPLATES" in out["digest"]
    assert any("NO RETENTION TEMPLATES" in n for n in out["notes"])


def test_roster_validation_problems_reach_the_run_not_just_stderr(tmp_env, shadow_mode):
    out = cs.run_scorecards(
        NOW, clients=[MIKE], instantly=None, ghl=GHL(token=None),
        store=JsonFileStore(tmp_env / "s.json"), week_ending=date(2026, 9, 21),
        dry_run=True, send_digest=False, out_dir=tmp_env / "cards",
        roster_notes=["perf: deal_type=performance with no attribution_window_days"],
    )
    assert any("attribution_window_days" in n for n in out["notes"])
    assert "attribution_window_days" in out["digest"]


# --------------------------------------------------------- the change-set
def test_the_onboarding_changeset_plans_but_never_applies(tmp_env, shadow_mode):
    from changesets.onboarding import apply as onboarding
    result = onboarding.run()
    assert result["applicable"] == []
    for item in result["planned"]:
        assert item["capability"] in ("manual_only", "no_credential")
        assert item["guard"]["shadow"] is True
    assert onboarding.main(["--apply"]) == 2


def test_a_dry_run_records_no_live_write_intent_when_live_writes_are_enabled(
        tmp_env, live_mode, monkeypatch):
    """shared/README.md: a live_write_intent with no matching live_write_ok or
    live_write_failed is the signature of a write that died in flight. This
    change-set never makes a call at all, so a plan run used to leave six rows
    reading as "a Stripe invoice and a GHL workflow may have been created"."""
    from changesets.onboarding import apply as onboarding
    rows = []
    monkeypatch.setattr(onboarding.job_log, "log_run",
                        lambda job, status, details=None: rows.append((job, status)))
    result = onboarding.run()
    assert result["planned"], "the plan should still be produced"
    assert [r for r in rows if r[1] == "live_write_intent"] == []
    for item in result["planned"]:
        assert item["guard"]["shadow"] is True
        assert item["guard"]["recorded"] == "plan_only"


def test_every_file_the_onboarding_spec_names_exists():
    """Step 4 and step 8a are the only two client-facing messages in the whole
    F1 flow and they carry the form link and the booking link. Both were named
    by the spec and neither file was written, so the build order stopped dead
    at step 4 with nothing to paste."""
    import re
    spec = _read("changesets/onboarding/onboarding_spec.md")
    named = sorted(set(re.findall(r"`([A-Za-z0-9_./-]+\.md)`", spec)))
    assert "kickoff_email.md" in named and "kickoff_nudge_email.md" in named
    for name in named:
        candidates = [settings.BASE_DIR / "changesets" / "onboarding" / name,
                      settings.BASE_DIR / name]
        assert any(p.exists() for p in candidates), name


def test_the_changeset_manifest_and_the_scorecard_roster_agree_on_the_products():
    from changesets.onboarding import apply as onboarding
    manifest = onboarding.load_manifest()
    keys = set(p["key"] for p in manifest["products"])
    clients, _ = cs.load_roster(include_inactive=True)
    for client in clients:
        assert client["product"] in keys, client["slug"]


# --------------------------------------------------- the shipped copy itself
CLIENT_FACING = (
    "changesets/onboarding/retention/day07_checkin.md",
    "changesets/onboarding/retention/day21_results.md",
    "changesets/onboarding/retention/day25_renewal.md",
    "changesets/onboarding/retention/day30_referral_review.md",
    "changesets/onboarding/kickoff_form.md",
    "changesets/onboarding/kickoff_email.md",
    "changesets/onboarding/kickoff_nudge_email.md",
    "products/reactivation_system/campaign_templates.md",
    "products/demo_library_011_reply_engine/011-reply-and-booking-engine.md",
)

LOOM_SCRIPTS = (
    "products/reactivation_system/loom_script.md",
    "products/bid_follow_up_system/loom_script.md",
    "products/cold_email_infrastructure/loom_script.md",
    "products/demo_library_011_reply_engine/loom_script.md",
)


def _read(relative):
    with open(str(settings.BASE_DIR / relative), "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("relative", CLIENT_FACING)
def test_shipped_client_facing_copy_obeys_the_offer_sheet_rules(relative):
    render_mod = cs.retro_modules()[2]
    if render_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    assert render_mod.check_client_copy(_read(relative)) == []


@pytest.mark.parametrize("relative", LOOM_SCRIPTS)
def test_the_spoken_half_of_every_loom_script_obeys_the_same_rules(relative):
    """The spoken section only. The heading and the recording notes are
    Lorenzo's, not the prospect's, and they say the word "script"."""
    render_mod = cs.retro_modules()[2]
    if render_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    parts = _read(relative).split("---")
    assert len(parts) > 2, "the script has no spoken section between two rules"
    assert render_mod.check_client_copy(parts[1]) == []


@pytest.mark.parametrize("relative", CLIENT_FACING + LOOM_SCRIPTS + (
    "products/README.md", "products/reactivation_system/SOP.md",
    "products/bid_follow_up_system/SOP.md", "products/cold_email_infrastructure/SOP.md",
    "changesets/onboarding/onboarding_spec.md", "changesets/onboarding/clickup_templates.md",
))
def test_no_em_dash_anywhere_in_the_kits(relative):
    assert "—" not in _read(relative)


COMMITTED_DRAFTS = settings.BASE_DIR / "changesets" / "onboarding" / "retention" / "drafts"


def test_the_committed_man_transformed_artifacts_match_a_fresh_render(tmp_env, shadow_mode):
    """The committed copy went stale against the code and still printed
    strings the module no longer emits. It is Mike's file: the runbook tells
    Lorenzo to regenerate rather than hand-edit, so it has to match."""
    clients, _ = cs.load_roster(include_inactive=True)
    mike = [c for c in clients if c["slug"] == "man-transformed"]
    out = cs.run_scorecards(
        NOW, clients=mike, instantly=None, ghl=None,
        store=JsonFileStore(tmp_env / "s.json"), dry_run=True, send_digest=False,
        lookahead_days=30, out_dir=tmp_env / "drafts",
    )
    fresh = {}
    for path in out["written"]:
        with open(str(path), encoding="utf-8") as fh:
            fresh[str(path).rsplit("/", 1)[-1]] = fh.read()
    committed = COMMITTED_DRAFTS / "man-transformed"
    on_disk = sorted(p.name for p in committed.glob("*.md"))
    assert on_disk == sorted(fresh), (
        "regenerate with: python3 jobs/client_scorecard.py --dry-run --client man-transformed "
        "--lookahead 30 --offline --as-of 2026-09-22T00:45:00-05:00 "
        "--out-dir changesets/onboarding/retention/drafts")
    for name, text in fresh.items():
        with open(str(committed / name), encoding="utf-8") as fh:
            assert fh.read() == text, name


def test_mikes_committed_day_25_draft_still_names_its_three_blockers():
    """The brief's named deliverable. It cannot go out until his numbers have a
    source, the two free-text offers are written, and the price is in the
    offer sheet."""
    with open(str(COMMITTED_DRAFTS / "man-transformed" / "draft_2026-10-12_day25_renewal.md"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "NOT READY, do not send" in text
    assert "missing metric: sent" in text
    assert "unfilled placeholder: {renewal_terms}" in text
    assert "price $2,000 is not in config/offers.md" in text


def test_every_sms_row_in_templates_csv_ships_disabled():
    """The SOP's own prevention step: enabled FALSE on every SMS row until the
    client's 10DLC registration is confirmed. A2P 10DLC is not registered, and
    a client who loaded the shipped file started texting from an unregistered
    number, which the SOP says ends in a suspended number."""
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(_read("products/bid_follow_up_system/templates.csv"))))
    sms = [r for r in rows if r["channel"] == "sms"]
    assert len(sms) == 4
    for row in sms:
        assert row["enabled"] == "FALSE", row["step"]
        assert "Reply STOP to opt out" in row["body"], row["step"]


def test_templates_csv_obeys_the_client_copy_rules():
    render_mod = cs.retro_modules()[2]
    if render_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    text = _read("products/bid_follow_up_system/templates.csv")
    assert "—" not in text
    assert "!" not in text
    # The signature rule does not apply: every body signs with the CLIENT's
    # merge fields, not Lorenzo's name.
    assert render_mod.check_copy(text, ban_words=True, require_signature=False) == []


def test_no_shipped_kit_carries_the_previous_clients_details():
    """The delivered bid system had the client's business name, owner first
    name and team address in its Config node. A template that ships the last
    client's details is the worst thing in products/."""
    raw = _read("products/bid_follow_up_system/bid-follow-up-system.n8n.json")
    lowered = raw.lower()
    for token in ("lawson", "jennifer"):
        assert token not in lowered
    config = [n for n in json.loads(raw)["nodes"] if n.get("name") == "Config"][0]
    values = dict((a["name"], a["value"])
                  for a in config["parameters"]["assignments"]["assignments"])
    assert values["business_name"].startswith("PASTE_")
    assert values["owner_name"].startswith("PASTE_")


# ------------------------------------------- re-review 2026-09-22 (OPS-2, 5, 6)
def test_ops5_a_thank_you_reply_weeks_later_does_not_re_invoice_the_close():
    """The period used to key on timestamp_last_reply, so a thank-you three
    weeks after signing moved the $10,000 close into the later period."""
    signed = lead("won@x.co", 4, replied="2026-09-23T15:00:00Z", first_touch_date="2026-08-01",
                  timestamp_last_interest_change="2026-09-02T15:00:00Z", contract_value=10000)
    later = (date(2026, 9, 21), date(2026, 9, 27))
    out = cs.revenue_attributed(cs.attribution_rows([signed], PERF, NOW, period=later), PERF)
    assert out["counted"] == [] and out["contract_value_usd"] is None
    assert len(out["earlier_periods"]) == 1             # listed, never billed, no billing state

    first = (date(2026, 8, 31), date(2026, 9, 6))
    out = cs.revenue_attributed(cs.attribution_rows([signed], PERF, NOW, period=first), PERF)
    assert out["contract_value_usd"] == 10000.0


def test_ops5_a_close_signed_on_a_call_with_no_new_email_is_billed_in_its_week():
    on_call = lead("call@x.co", 4, replied="2026-09-10T15:00:00Z", first_touch_date="2026-08-01",
                   timestamp_last_interest_change="2026-09-25T17:00:00Z", contract_value=8000)
    period = (date(2026, 9, 21), date(2026, 9, 27))
    out = cs.revenue_attributed(cs.attribution_rows([on_call], PERF, NOW, period=period), PERF)
    assert out["contract_value_usd"] == 8000.0
    assert out["earlier_periods"] == []
    assert "invoiced" not in "\n".join(cs._attribution_lines(out)).lower()


def test_ops5_a_close_with_no_close_timestamp_is_excluded_not_placed_on_its_last_reply():
    undated = lead("nodate@x.co", 4, replied="2026-09-23T15:00:00Z",
                   first_touch_date="2026-08-01", contract_value=5000)
    out = cs.revenue_attributed(cs.attribution_rows(
        [undated], PERF, NOW, period=(date(2026, 9, 21), date(2026, 9, 27))), PERF)
    assert out["counted"] == []
    assert "no close date" in out["excluded"][0]["reason"]


def test_ops5_the_ghl_won_move_dates_the_close_and_edits_do_not(tmp_path):
    class FakeGHL(object):
        token = "t"

        def search_opportunities(self, **kwargs):
            return {"opportunities": [{"id": "o1", "contact": {"email": "won@x.co"},
                                       "monetaryValue": 12000,
                                       "updatedAt": "2026-09-24T03:00:00Z",
                                       "lastStageChangeAt": "2026-09-03T16:00:00Z"}]}

    closes = {}
    values, _t = cs.pull_won_values(FakeGHL(), PERF, [], close_dates=closes)
    assert closes == {"won@x.co": date(2026, 9, 3)}
    rows = cs.attribution_rows([lead("won@x.co", 4, replied="2026-09-24T15:00:00Z",
                                     first_touch_date="2026-08-01")], PERF, NOW,
                               won_values=values, close_dates=closes,
                               period=(date(2026, 9, 21), date(2026, 9, 27)))
    assert rows[0]["closed"] == "2026-09-03" and rows[0]["close_source"] == "ghl_won_stage"


def test_ops2_the_digest_push_on_a_public_topic_carries_counts_only(tmp_env, shadow_mode,
                                                                   monkeypatch):
    from shared import notify as notify_mod
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    notify_mod.reset_for_tests()
    client = dict(client_with_campaign(), company="Pat Example Co")
    out = cs.run_scorecards(
        NOW, clients=[client], instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=False, send_digest=True,
        out_dir=tmp_env / "cards")
    sent = notify_mod.sent_in_test[-1]
    assert "Pat Example" not in sent["message"] and "Pat Example" not in sent["title"]
    assert "$" not in sent["message"]
    assert "1 client card(s)" in sent["message"]
    assert sent["email_message"] == out["digest"] and "Pat Example" in sent["email_message"]


def _sunday_card(extra_leads=()):
    _collect, scorecard_mod, render_mod = cs.retro_modules()
    if scorecard_mod is None:
        pytest.skip("services/retro (brief A10) is not present in this tree")
    with open(str(settings.BASE_DIR / "services" / "retro" / "fixtures" / "week_2026-09.json"),
              encoding="utf-8") as fh:
        fx = json.load(fh)
    reactivation = settings.CAMPAIGNS["cleaning_reactivation"]["id"]
    trigger = settings.CAMPAIGNS["cleaning_trigger"]["id"]
    leads = list(fx["leads"]) + list(extra_leads)
    now = CT.localize(datetime(2026, 9, 20, 20, 0))
    week_obj = _collect.collect_week(now, fixtures=dict(fx, leads=leads))
    daily = []
    for key, cid in (("cleaning_reactivation", reactivation), ("cleaning_trigger", trigger)):
        for row in fx["campaign_rows"][key]:
            daily.append(dict(row, campaign_id=cid))
    client = {"slug": "test-co", "name": "Pat", "company": "Test Co",
              "product_name": "Reactivation system", "deal_type": "flat", "price_usd": 2000,
              "start_date": "2026-08-27", "term_days": 30, "term_end": "2026-09-26",
              "instantly_campaign_ids": [reactivation, trigger], "active": True}
    templates, _ = cs.load_templates()
    return cs.run_client(client, now, None, templates, leads=leads, daily=daily,
                         week_obj=week_obj, scorecard_mod=scorecard_mod, render_mod=render_mod,
                         lookahead_days=7)


def test_ops6_the_sunday_card_carries_no_retention_text():
    result = _sunday_card()
    assert result["card_source"] == "retro_scorecard (A10)"
    assert result["drafts"], "the fixture client has a retention touch due"
    card = result["scorecard"]
    assert "note (due" not in card and "day 25" not in card.lower()
    assert "cannot go out yet" not in card
    for draft in result["drafts"]:
        for blocker in draft["blockers"]:
            assert blocker not in card


def test_ops6_a_contact_on_two_campaigns_is_one_interested_on_the_card():
    base = _sunday_card()
    with open(str(settings.BASE_DIR / "services" / "retro" / "fixtures" / "week_2026-09.json"),
              encoding="utf-8") as fh:
        fx = json.load(fh)
    reactivation = settings.CAMPAIGNS["cleaning_reactivation"]["id"]
    trigger = settings.CAMPAIGNS["cleaning_trigger"]["id"]
    source = [l for l in fx["leads"] if l.get("campaign") == trigger
              and l.get("lt_interest_status") == 1][0]
    dup = dict(source, id="dup-1", campaign=reactivation)
    result = _sunday_card([dup])
    assert result["metrics"]["positives"] == base["metrics"]["positives"]
    assert "| Interested | %d |" % base["metrics"]["positives"] in result["scorecard"]
    assert "counted once" in result["scorecard"]
    assert "by the date the contact's status last changed" in result["scorecard"]
    assert "by the date of the contact's last reply" not in result["scorecard"]



# ------------------------- OPS-5 round 3: no ledger, hand invoicing, failed cards
def _render_perf(perf, store, leads, out_dir):
    daily = [daily_row("2026-09-%02d" % d, CLEANING) for d in range(15, 22)]
    result = cs.run_client(perf, NOW, None, [], week_ending=date(2026, 9, 21), leads=leads,
                           daily=daily, ghl=GHL(token=None), store=store)
    written = cs.write_outputs(result, root=out_dir)
    return result, written


BILLING_STATE = ("already invoiced", "invoiced", "not yet on an invoice", "uninvoiced",
                 "invoice ledger", "mark-invoiced", "was billed", "not billed")


def test_ops5_the_invoice_ledger_is_gone():
    for name in ("invoiced_ledger", "mark_invoiced", "invoiced_key", "STORE_INVOICED_PREFIX",
                 "invoice_basis", "load_invoice_basis", "MarkInvoicedRefused"):
        assert not hasattr(cs, name), name
    import inspect
    assert "invoiced" not in inspect.signature(cs.revenue_attributed).parameters


def test_ops5_mark_invoiced_is_an_unknown_argument(tmp_env, shadow_mode, capsys):
    with pytest.raises(SystemExit) as exited:
        cs.main(["--dry-run", "--mark-invoiced", "perf"])
    assert exited.value.code == 2
    assert "unrecognized arguments: --mark-invoiced" in capsys.readouterr().err


def test_ops5_no_invoice_basis_file_is_written(tmp_env, shadow_mode):
    stamp = "2026-09-18T15:00:00Z"
    result, written = _render_perf(dict(PERF), JsonFileStore(tmp_env / "s.json"),
                                   [lead("a@x.co", 4, replied=stamp,
                                         timestamp_last_interest_change=stamp,
                                         first_touch_date="2026-08-01", contract_value=10000)],
                                   tmp_env / "cards")
    assert result["attribution"]["contract_value_usd"] == 10000.0
    import os
    assert not [p for p in written if os.path.basename(p).startswith("invoice_")]
    assert not list((tmp_env / "cards").rglob("invoice_*.json"))


def test_ops5_no_card_says_anything_about_billing_state(tmp_env, shadow_mode):
    """Invoicing is tracked by hand. Neither the client body nor the operator
    notes may claim a close was or was not invoiced."""
    aug, sep = "2026-08-10T15:00:00Z", "2026-09-18T15:00:00Z"
    result, _w = _render_perf(dict(PERF), JsonFileStore(tmp_env / "s.json"), [
        lead("aug@x.co", 4, replied=aug, timestamp_last_interest_change=aug,
             first_touch_date="2026-05-01", contract_value=12500, company="Northwind"),
        lead("sep@x.co", 4, replied=sep, timestamp_last_interest_change=sep,
             first_touch_date="2026-08-01", contract_value=9000, company="Southwind")],
        tmp_env / "cards")
    assert result["attribution"]["earlier_periods"]
    body = result["scorecard"].lower()
    appendix = result["operator_appendix"].lower()
    for claim in BILLING_STATE:
        assert claim not in body, claim
        assert claim not in appendix, claim
    assert "closed in an earlier period, not part of this week's figure" in body
    assert cs.INVOICING_BY_HAND in result["operator_appendix"]
    assert ("check every close on this week's invoice line against your own records"
            in result["operator_appendix"])
    assert cs.INVOICING_BY_HAND not in result["scorecard"]


def _two_clients():
    perf = dict(PERF, slug="perf", company="Pat Example Co", instantly_campaign_ids=[CLEANING],
                start_date="2026-09-01", term_days=30, term_end="2026-10-01")
    return perf, client_with_campaign()


def _perf_blows_up(monkeypatch, slugs):
    real = cs.run_client

    def boom(client, *a, **k):
        if client.get("slug") in slugs:
            raise RuntimeError("card exploded for %s" % client.get("company"))
        return real(client, *a, **k)

    monkeypatch.setattr(cs, "run_client", boom)


def test_round2_a_failed_card_is_counted_on_the_public_push_at_high_priority(
        tmp_env, shadow_mode, monkeypatch):
    from shared import notify as notify_mod
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    notify_mod.reset_for_tests()
    perf, flat = _two_clients()
    _perf_blows_up(monkeypatch, {"perf"})
    out = cs.run_scorecards(
        NOW, clients=[perf, flat], instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=False, send_digest=True,
        out_dir=tmp_env / "cards")
    assert [r["slug"] for r in out["results"]] == ["acme"]
    assert out["status"] == "partial" and out["counts"]["cards_failed"] == 1
    sent = notify_mod.sent_in_test[-1]
    assert sent["priority"] == "high"
    assert "1 card failed" in sent["message"] and "1 card failed" in sent["title"]
    for private in ("Pat Example", "perf", "exploded"):
        assert private not in sent["message"], private
        assert private not in sent["title"], private
    assert "card for perf failed" in sent["email_message"]


def test_round2_every_card_failing_exits_non_zero(tmp_env, shadow_mode, monkeypatch):
    from shared import job_log, notify as notify_mod
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    notify_mod.reset_for_tests()
    perf, flat = _two_clients()
    monkeypatch.setattr(cs, "load_roster", lambda **k: ([perf, flat], []))
    monkeypatch.setattr(cs, "get_store", lambda: JsonFileStore(tmp_env / "s.json"))
    _perf_blows_up(monkeypatch, {"perf", "acme"})
    code = cs.main(["--now", "--offline", "--as-of", NOW.isoformat(),
                    "--out-dir", str(tmp_env / "cards")])
    assert code == 1
    sent = notify_mod.sent_in_test[-1]
    assert sent["priority"] == "high" and "2 cards failed" in sent["message"]
    log = job_log.job_log_path().read_text(encoding="utf-8")
    assert "client_scorecard,failed" in log


def test_round2_some_cards_failing_is_partial_not_a_failure(tmp_env, shadow_mode, monkeypatch):
    perf, flat = _two_clients()
    monkeypatch.setattr(cs, "load_roster", lambda **k: ([perf, flat], []))
    monkeypatch.setattr(cs, "get_store", lambda: JsonFileStore(tmp_env / "s.json"))
    _perf_blows_up(monkeypatch, {"perf"})
    assert cs.main(["--now", "--offline", "--as-of", NOW.isoformat(),
                    "--out-dir", str(tmp_env / "cards")]) == 0


# ------------------------- OPS-5 round 4: double-billing disclosure, later closes, digest
class _WonGHL(object):
    """GHL readable from week 2 on: the Won move re-dates the close."""
    token = "t"

    def search_opportunities(self, **kw):
        return {"opportunities": [{"id": "o1", "contact": {"email": "won@x.co"},
                                   "monetaryValue": 10000,
                                   "lastStageChangeAt": "2026-09-22T16:00:00Z"}]}


def _signed_card(now, ghl, store, signed):
    daily = [daily_row("2026-09-%02d" % d, CLEANING) for d in range(10, 26)]
    return cs.run_client(dict(PERF), now, None, [], leads=[signed], daily=daily, ghl=ghl,
                         store=store)


def test_round4_a_close_re_dated_by_ghl_is_on_two_cards_and_the_operator_is_warned(
        tmp_env, shadow_mode):
    """Probe A: card 1 counts the close on its Instantly status date; once GHL
    is readable the Won move re-dates it into the next week, so card 2 counts it
    again. With no ledger that cannot be prevented, so card 2's operator notes
    must say to check every counted close and show where each date came from."""
    store = JsonFileStore(tmp_env / "s.json")
    signed = lead("won@x.co", 4, replied="2026-09-16T15:00:00Z", first_touch_date="2026-08-01",
                  timestamp_last_interest_change="2026-09-16T15:00:00Z", contract_value=10000)
    card1 = _signed_card(CT.localize(datetime(2026, 9, 18, 19, 15)), GHL(token=None), store, signed)
    card2 = _signed_card(CT.localize(datetime(2026, 9, 25, 19, 15)), _WonGHL(), store, signed)
    assert [r["close_source"] for r in card1["attribution"]["counted"]] == ["interest_status_change"]
    assert [r["close_source"] for r in card2["attribution"]["counted"]] == ["ghl_won_stage"]
    for card, source in ((card1, "Instantly status change"), (card2, "GHL Won")):
        appendix = card["operator_appendix"]
        assert cs.INVOICING_BY_HAND in appendix
        assert "the same close can be counted on two cards" in appendix
        assert "check every close on this week's invoice line" in appendix
        assert "its source changes" in appendix and "off the Friday schedule" in appendix
        assert "won@x.co closed" in appendix and "(%s)" % source in appendix
        for claim in BILLING_STATE:
            assert claim not in appendix.lower(), claim
            assert claim not in card["scorecard"].lower(), claim
        assert cs.INVOICING_BY_HAND not in card["scorecard"]
        assert "won@x.co" not in card["scorecard"]


def test_round4_the_date_source_labels_cover_every_close_source():
    for source, label in (("ghl_won_stage", "GHL Won"), ("lead_record", "lead close date"),
                          ("interest_status_change", "Instantly status change")):
        assert cs.close_list([{"email": "a@x.co", "closed": "2026-09-16",
                               "close_source": source}]) == "a@x.co closed 2026-09-16 (%s)" % label


def test_round4_a_close_after_the_week_is_not_printed_as_an_earlier_period(tmp_env, shadow_mode):
    """Probe r3b: signed Friday afternoon, the Friday 19:15 run covers
    Fri 09-11 to Thu 09-17. The 09-18 close is after the week, not before it."""
    signed = lead("fri@x.co", 4, replied="2026-09-18T20:00:00Z", first_touch_date="2026-08-01",
                  timestamp_last_interest_change="2026-09-18T20:00:00Z", contract_value=8000,
                  company="Fri Co")
    daily = [daily_row("2026-09-%02d" % d, CLEANING) for d in range(10, 19)]
    r = cs.run_client(dict(PERF), CT.localize(datetime(2026, 9, 18, 19, 15)), None, [],
                      leads=[signed], daily=daily, ghl=GHL(token=None),
                      store=JsonFileStore(tmp_env / "s.json"))
    assert (r["week"]["start"], r["week"]["end"]) == ("2026-09-11", "2026-09-17")
    attribution = r["attribution"]
    assert attribution["counted"] == [] and attribution["earlier_periods"] == []
    assert [row["email"] for row in attribution["later_periods"]] == ["fri@x.co"]
    assert attribution["contract_value_usd"] is None
    body = r["scorecard"]
    assert "Closed in an earlier period" not in body
    assert "Fri Co" not in body and "fri@x.co" not in body
    assert ("1 close(s) dated after this week's end are left off this card and are not part "
            "of its figure." in r["operator_appendix"])
    assert "fri@x.co closed 2026-09-18 (Instantly status change)" in r["operator_appendix"]
    assert "a later card is not guaranteed to count it" in r["operator_appendix"]


def test_round4_an_earlier_close_still_prints_under_the_earlier_heading():
    rows = cs.attribution_rows(
        [lead("aug@x.co", 4, timestamp_last_interest_change="2026-08-10T10:00:00Z",
              first_touch_date="2026-05-01", contract_value=12500)],
        PERF, NOW, period=PERIOD)
    assert rows[0]["period_position"] == "earlier"
    out = cs.revenue_attributed(rows, PERF)
    assert len(out["earlier_periods"]) == 1 and out["later_periods"] == []
    assert "Closed in an earlier period" in "\n".join(cs._attribution_lines(out))


def test_round4_the_digest_does_not_say_no_active_clients_when_every_card_failed(
        tmp_env, shadow_mode, monkeypatch):
    from shared import notify as notify_mod
    notify_mod.reset_for_tests()
    perf, flat = _two_clients()
    _perf_blows_up(monkeypatch, {"perf", "acme"})
    out = cs.run_scorecards(
        NOW, clients=[perf, flat], instantly=Instantly(api_key="t", transport=transport()),
        ghl=GHL(token=None), store=JsonFileStore(tmp_env / "s.json"),
        week_ending=date(2026, 9, 21), dry_run=False, send_digest=True,
        out_dir=tmp_env / "cards")
    assert out["results"] == []
    digest = out["digest"]
    assert "No active clients in the roster." not in digest
    assert "No card was produced this run: all 2 cards failed, see above." in digest
    assert "card for perf failed" in digest and "card for acme failed" in digest
    assert "No active clients in the roster." in cs.render_digest([], NOW, notes=[])


# ------------------------- OPS-5 round 5: a close that lands on no invoice line
class _ThursdayWonGHL(object):
    """GHL readable from card N+1 on: the Won move dates the close a day EARLIER."""
    token = "t"

    def search_opportunities(self, **kw):
        return {"opportunities": [{"id": "o1", "contact": {"email": "late@x.co"},
                                   "monetaryValue": 9000,
                                   "lastStageChangeAt": "2026-09-17T16:00:00Z"}]}


def test_round5_a_close_moved_back_across_the_boundary_is_flagged_for_a_hand_check(
        tmp_env, shadow_mode):
    """Probe r4 A: card N (09-11..09-17) sees an Instantly close dated 09-18, after
    its week. On card N+1 (09-18..09-24) GHL Won dates it 09-17, before its week.
    It is on no invoice line, so card N+1's operator notes must ask for the
    earlier-period closes to be checked, not only this week's invoice line."""
    store = JsonFileStore(tmp_env / "s.json")
    signed = lead("late@x.co", 4, replied="2026-09-18T20:00:00Z", first_touch_date="2026-08-01",
                  timestamp_last_interest_change="2026-09-18T20:00:00Z", contract_value=9000)
    daily = [daily_row("2026-09-%02d" % d, CLEANING) for d in range(10, 26)]

    def card(now, ghl):
        return cs.run_client(dict(PERF), now, None, [], leads=[signed], daily=daily, ghl=ghl,
                             store=store)

    card_n = card(CT.localize(datetime(2026, 9, 18, 19, 15)), GHL(token=None))
    card_n1 = card(CT.localize(datetime(2026, 9, 25, 19, 15)), _ThursdayWonGHL())
    assert [r["email"] for r in card_n["attribution"]["later_periods"]] == ["late@x.co"]
    assert card_n["attribution"]["counted"] == []
    assert [r["email"] for r in card_n1["attribution"]["earlier_periods"]] == ["late@x.co"]
    assert card_n1["attribution"]["counted"] == []
    appendix = card_n1["operator_appendix"]
    assert cs.INVOICING_BY_HAND in appendix
    assert "or on none" in appendix
    assert ("Also check every close these notes list from an earlier period or dated after "
            "this week's end: it may never have been on any invoice line") in appendix
    assert "earlier or later, when its source changes" in appendix
    assert "a week whose card failed or did not run had no invoice line at all" in appendix
    assert ("not part of this week's figure. Check each against your own records: it may "
            "never have been on any invoice line: late@x.co closed 2026-09-17 (GHL Won)"
            in appendix)
    # Neutral about which source dates a close later.
    assert "later GHL Won" not in appendix and "later GHL Won" not in cs.INVOICING_BY_HAND
    for claim in BILLING_STATE:
        assert claim not in appendix.lower(), claim
        assert claim not in card_n1["scorecard"].lower(), claim
    assert cs.INVOICING_BY_HAND not in card_n1["scorecard"]
    assert "Check each against your own records" not in card_n1["scorecard"]
