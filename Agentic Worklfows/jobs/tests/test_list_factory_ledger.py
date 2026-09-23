"""Cost ledger, the 2-cent hard stop, and source attribution."""
import csv
import os

import pytest

from services.list_factory import ledger as ledger_mod


def make(max_cost=0.02):
    return ledger_mod.Ledger("run-1", "cleaning", max_cost_per_contact=max_cost)


def test_priced_units_charge_the_documented_rate():
    led = make()
    led.spend_units("verify", "millionverifier_per_check", 1000)
    assert led.costs["verify"] == pytest.approx(0.6)
    led.spend_units("owner", "perplexity_per_owner_lookup", 100)
    assert led.costs["owner"] == pytest.approx(0.5)
    assert led.total() == pytest.approx(1.1)


def test_cost_per_verified_is_none_until_something_verifies():
    led = make()
    led.spend("source", 5.0)
    assert led.cost_per_verified() is None
    assert led.verdict() == "no_verified_contacts"


def test_a_run_inside_the_cap_is_green():
    led = make()
    led.count("verify", 1000)
    led.spend("verify", 10.0)
    assert led.cost_per_verified() == pytest.approx(0.01)
    assert led.verdict() == "green"


def test_verdict_grades_over_cap_and_alert_separately():
    led = make()
    led.count("verify", 100)
    led.spend("verify", 3.0)          # $0.03 -> over the $0.02 cap
    assert led.verdict() == "over_cap"
    led.spend("verify", 3.0)          # $0.06 -> past the $0.04 alert line
    assert led.verdict() == "alert"


def test_hard_stop_fires_on_the_projection_not_after_the_money_is_gone():
    """The whole point: a run heading for 3 cents is stopped while the
    remaining verifications are still unspent."""
    led = make()
    led.count("verify", 100)
    led.note("verify_attempted", 400)   # 25% verify rate
    led.spend("source", 8.00)
    led.spend("verify", 0.24)
    # 900 candidates left at 25% -> 325 expected verified. $8.24 spent plus
    # $0.54 of verification still to come is $8.78, or $0.027 each: over.
    with pytest.raises(ledger_mod.BudgetExceeded) as exc:
        led.check_budget(remaining_candidates=900, where="verify")
    assert led.halted
    assert "exceeds the $0.0200 cap" in str(exc.value)
    assert exc.value.snapshot["verdict"] == "halted_over_budget"


def test_hard_stop_does_not_fire_on_a_run_that_is_on_track():
    led = make()
    led.count("verify", 100)
    led.note("verify_attempted", 200)
    led.spend("source", 0.50)
    led.spend("verify", 0.12)
    led.check_budget(remaining_candidates=1000, where="verify")  # must not raise
    assert not led.halted


def test_nothing_verified_and_nothing_left_cannot_stop_a_run_at_stage_one():
    """With no rate to project from there is no projection, and stopping on an
    imaginary one would kill every run before it sourced anything."""
    led = make()
    led.spend("source", 5.0)
    led.check_budget(remaining_candidates=0, where="source")
    assert not led.halted


def test_an_explicit_verify_rate_overrides_the_observed_one():
    led = make()
    led.count("verify", 1)
    led.note("verify_attempted", 100)   # observed 1%
    led.spend("source", 0.10)
    projected_observed = led.project_cost_per_verified(1000)
    projected_given = led.project_cost_per_verified(1000, verify_rate=0.5)
    assert projected_given < projected_observed


def test_ledger_row_and_csv_carry_the_stage_breakdown(tmp_path):
    led = make()
    led.count("source", 500)
    led.count("icp", 300)
    led.count("verify", 150)
    led.count("stage", 140)
    led.note("icp_rejected", 200)
    led.note("suppressed", 10)
    led.spend("source", 1.20)
    led.spend("verify", 0.39)
    path = str(tmp_path / "ledger.csv")
    led.append_csv("shadow", path)
    with open(path, "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    row = rows[0]
    assert row["sourced"] == "500"
    assert row["icp_pass"] == "300"
    assert row["icp_reject"] == "200"
    assert row["verified"] == "150"
    assert row["staged"] == "140"
    assert row["suppressed"] == "10"
    assert row["mode"] == "shadow"
    assert float(row["cost_total"]) == pytest.approx(1.59)
    assert row["verdict"] == "green"


def test_csv_appends_rather_than_overwrites(tmp_path):
    path = str(tmp_path / "ledger.csv")
    for _ in range(3):
        led = make()
        led.count("verify", 10)
        led.spend("verify", 0.01)
        led.append_csv("shadow", path)
    with open(path, "r", encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 3


def test_table_renders_without_a_verified_contact():
    led = make()
    led.spend("source", 1.0)
    assert "cost per verified contact: n/a" in led.table()


# ------------------------------------------------------------- attribution
WORKSPACE = [
    {"payload": {"advero_source": "apify:leads-finder"}, "timestamp_last_contact": "x", "email_reply_count": 1, "status": 1},
    {"payload": {"advero_source": "apify:leads-finder"}, "timestamp_last_contact": "x", "email_reply_count": 0, "status": 1},
    {"payload": {"advero_source": "gmaps"}, "timestamp_last_contact": "x", "email_reply_count": 0, "status": -1},
    {"payload": {"advero_source": "gmaps"}, "timestamp_last_contact": None, "email_reply_count": 0, "status": 1},
    {"payload": {}, "timestamp_last_contact": "x", "email_reply_count": 2, "status": 1},
]


def test_attribution_reports_replies_per_1k_sends_by_source():
    report = ledger_mod.source_attribution(lambda: WORKSPACE)
    by_source = dict((row["source"], row) for row in report["by_source"])
    assert by_source["apify:leads-finder"]["sends"] == 2
    assert by_source["apify:leads-finder"]["replies_per_1k_sends"] == pytest.approx(500.0)
    assert by_source["gmaps"]["sends"] == 1
    assert by_source["gmaps"]["bounce_rate_pct"] == pytest.approx(100.0)


def test_leads_with_no_source_are_reported_not_dropped():
    """Dropping the unattributed leads would make every attributed source look
    better than it is."""
    report = ledger_mod.source_attribution(lambda: WORKSPACE)
    sources = [row["source"] for row in report["by_source"]]
    assert "unattributed" in sources
    assert report["total_leads"] == len(WORKSPACE)


def test_a_source_with_no_sends_reports_no_rate_rather_than_zero():
    report = ledger_mod.source_attribution(lambda: [
        {"payload": {"advero_source": "brand-new"}, "timestamp_last_contact": None, "email_reply_count": 0},
    ])
    assert report["by_source"][0]["replies_per_1k_sends"] is None


# =====================================================================
# Regressions from the 2026-09-22 review.
# =====================================================================
from services.list_factory import pipeline as pipeline_mod


def test_a_replay_row_is_labelled_so_it_cannot_pass_as_a_paid_run(tmp_path):
    """A free --verify replay rehearsal landed in the same cost_ledger.csv as a
    real paid run with nothing to tell them apart, so runbook step 4 ("correct
    DEFAULT_RATES from the ledger's observed rates") could not be done at all:
    you cannot tell which rows were paid."""
    path = str(tmp_path / "ledger.csv")
    rehearsal = ledger_mod.Ledger("r1", "cleaning", source="fixture", verifier="replay",
                                  dry_run=True, target=3300)
    rehearsal.count("verify", 37)
    rehearsal.spend("verify", 0.0264)
    rehearsal.append_csv("shadow", path)

    real = ledger_mod.Ledger("r2", "cleaning", source="apify", verifier="millionverifier",
                             dry_run=False, target=3300)
    real.count("verify", 3300)
    real.spend("verify", 10.30)
    real.append_csv("shadow", path)

    with open(path, "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["verifier"] for r in rows] == ["replay", "millionverifier"]
    assert [r["source"] for r in rows] == ["fixture", "apify"]
    assert [r["dry_run"] for r in rows] == ["yes", "no"]
    assert [r["target"] for r in rows] == ["3300", "3300"]


def test_catch_alls_are_reported_apart_from_confirmed_mailboxes(tmp_path):
    led = make()
    led.count("verify", 70)
    led.count("catch_all", 30)
    led.spend("verify", 2.00)
    assert led.deliverable_count() == 100
    assert led.catch_all_share() == pytest.approx(0.30)
    assert led.cost_per_verified() == pytest.approx(0.028571, rel=1e-3)
    assert led.cost_per_deliverable() == pytest.approx(0.02)
    # The KPI is computed on CONFIRMED mailboxes, so this run is over the cap.
    assert led.verdict() == "over_cap"
    path = str(tmp_path / "l.csv")
    led.append_csv("shadow", path)
    with open(path, "r", encoding="utf-8") as fh:
        row = list(csv.DictReader(fh))[0]
    assert row["verified"] == "70"
    assert row["catch_all"] == "30"


def test_the_projection_falls_back_to_the_planned_rate_before_anything_verifies():
    """It returned None until verification had already happened, so the hard
    stop could not speak at any boundary before `verify` - on a Google Maps run
    that is 81 percent of the money already committed."""
    # A realistic Sunday run at the owner boundary: nothing verified yet.
    led = ledger_mod.Ledger("p", "cleaning", 0.02, rates=pipeline_mod.DEFAULT_RATES)
    led.spend("source", 25.62)      # Apify
    led.spend("icp", 3.36)          # Haiku
    led.spend("owner", 41.25)       # Perplexity
    projected = led.project_cost_per_verified(8250)
    assert projected is not None, "the old version returned None here and the run carried on"
    with pytest.raises(ledger_mod.BudgetExceeded):
        led.check_budget(8250, where="owner", rates=pipeline_mod.DEFAULT_RATES)
    assert led.halted


def test_the_future_leg_prices_every_pattern_and_the_work_still_to_come():
    led = ledger_mod.Ledger("p", "cleaning", 0.02, rates=pipeline_mod.DEFAULT_RATES)
    led.count("verify", 100)
    led.note("verify_attempted", 200)
    lean = led.project_cost_per_verified(1000, verify_rate=0.5)
    fat = led.project_cost_per_verified(1000, verify_rate=0.5, extra_future_usd=5.0)
    assert fat > lean
    # 2.6 checks a lead, not 1.
    assert lean == pytest.approx(
        (led.total() + ledger_mod.PRICES["millionverifier_per_check"] * 1000 * 2.6) / 600.0, rel=1e-6)


def test_verify_errors_are_reported_in_the_row(tmp_path):
    led = make()
    led.count("verify", 5)
    led.note("verify_errors", 12)
    path = str(tmp_path / "l.csv")
    led.append_csv("shadow", path)
    with open(path, "r", encoding="utf-8") as fh:
        assert list(csv.DictReader(fh))[0]["verify_errors"] == "12"


def test_an_old_schema_ledger_is_moved_aside_rather_than_corrupted(tmp_path):
    """DictWriter would write the new field order under the old header and
    every column after the first new one would be silently wrong."""
    path = str(tmp_path / "cost_ledger.csv")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("ts_utc,run_id,niche,mode,sourced,verified,cost_total,verdict\n")
        fh.write("2026-09-22T07:44:23+00:00,old_run,cleaning,shadow,58,37,0.0749,green\n")
    led = make()
    led.count("verify", 1)
    led.append_csv("shadow", path)

    with open(path, "r", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ledger_mod.LEDGER_HEADER
    assert len(rows) == 2
    archived = str(tmp_path / "cost_ledger.v1.csv")
    assert os.path.exists(archived)
    with open(archived, "r", encoding="utf-8") as fh:
        assert "old_run" in fh.read()


def test_the_planned_fallback_counts_confirmed_mailboxes_only():
    """MKT-1: the fallback rate was the deliverable rate, catch-alls included,
    while cost_per_verified divides by confirmed mailboxes only."""
    led = ledger_mod.Ledger("p", "cleaning", 0.02,
                            rates={"verify_rate": 0.5, "catch_all_share": 0.25, "checks_per_lead": 2.6})
    led.spend("source", 10.0)
    projected = led.project_cost_per_verified(1000)
    future = ledger_mod.PRICES["millionverifier_per_check"] * 1000 * 2.6
    assert projected == pytest.approx((10.0 + future) / 375.0, rel=1e-4)


def test_the_observed_fallback_counts_confirmed_mailboxes_only():
    led = make()
    led.count("verify", 60)
    led.count("catch_all", 40)
    led.note("verify_attempted", 200)
    assert led.observed_verify_rate() == pytest.approx(0.5)
    assert led.observed_confirmed_rate() == pytest.approx(0.3)
    projected = led.project_cost_per_verified(1000)
    future = ledger_mod.PRICES["millionverifier_per_check"] * 1000 * 2.6
    assert projected == pytest.approx((led.total() + future) / (60 + 300), rel=1e-4)


def test_the_cost_lines_are_bound_to_shared_thresholds():
    from shared import thresholds as TH

    assert ledger_mod.DEFAULT_MAX_COST_PER_CONTACT == TH.LIST_FACTORY_MAX_COST_PER_CONTACT_USD == 0.02
    assert ledger_mod.ALERT_COST_PER_CONTACT == TH.LIST_FACTORY_ALERT_COST_PER_CONTACT_USD == 0.04
