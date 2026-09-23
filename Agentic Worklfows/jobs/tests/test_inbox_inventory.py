"""Tests for jobs/inbox_inventory.py (Blueprint M2, brief A5).

Fixtures are the recorded read-only pulls in changesets/capacity/snapshots/
(45 accounts, 6 campaigns, 72 daily-analytics rows for 2026-09-15..21, taken
2026-09-22). Nothing here touches a live system: the only client used is an
httpx.MockTransport that refuses anything that is not a read.

Several tests run the job at clocks other than the recorded one. That is
deliberate: this job is scheduled daily and forever, and every constant in it
that was frozen to a single date (the go-live date, the ramp horizon) used to
produce nonsense on the first run past it.
"""
import copy
import json
import os
import re
from datetime import date, datetime, timedelta

import httpx
import pytest
import pytz

from jobs import inbox_inventory as inv

CT = pytz.timezone("America/Chicago")
NOW = CT.localize(datetime(2026, 9, 22, 0, 45, 0))
SNAPSHOTS = inv.SNAPSHOT_DIR


def _load(name):
    with open(os.path.join(SNAPSHOTS, name), "r", encoding="utf-8") as fh:
        blob = json.load(fh)
    return blob.get("items") if isinstance(blob, dict) and "items" in blob else blob


def at(text):
    return CT.localize(datetime.fromisoformat(text))


def account(email, warm_start="2026-07-01", **kw):
    row = {
        "email": email, "status": 1, "daily_limit": 25, "stat_warmup_score": 100,
        "warmup_status": 1,
        "timestamp_created": warm_start + "T00:00:00.000Z",
        "timestamp_warmup_start": warm_start + "T00:00:00.000Z",
    }
    row.update(kw)
    return row


@pytest.fixture(scope="module")
def recorded():
    return {
        "accounts": _load("accounts_2026-09-22.json"),
        "campaigns": _load("campaigns_2026-09-22.json"),
        "daily": _load("daily_account_analytics_2026-09-15_21.json"),
    }


@pytest.fixture(scope="module")
def inventory(recorded):
    return inv.build_inventory(recorded["accounts"], recorded["campaigns"], recorded["daily"],
                               NOW, source="fixtures", window=("2026-09-15", "2026-09-21"))


# --------------------------------------------------------------- primitives
def test_parse_ts_handles_instantly_millisecond_z_timestamps():
    parsed = inv.parse_ts("2026-09-20T19:08:52.230Z")
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day, parsed.hour) == (2026, 9, 20, 19)
    assert parsed.utcoffset().total_seconds() == 0
    assert inv.parse_ts(None) is None
    assert inv.parse_ts("not a date") is None


def test_replies_automatic_is_never_subtracted_from_replies():
    """The load-bearing arithmetic bug this job exists to avoid.

    ``replies_automatic`` is an independent counter in
    ``GET /accounts/analytics/daily``, not a subset of ``replies``. The live
    numbers for 2026-09-19 are replies=0 with replies_automatic=7. Reading
    "exclude auto-replies" (Blueprint M1 level 3) as a subtraction gives that
    day a reply count of -7, drives every active inbox under the 1% line and
    retires the whole estate on the first Friday audit.
    """
    rows = [
        {"email_account": "a@x.com", "date": "2026-09-19", "sent": 25, "bounced": 0,
         "replies": 0, "unique_replies": 0, "replies_automatic": 7, "unique_replies_automatic": 7},
        {"email_account": "a@x.com", "date": "2026-09-20", "sent": 25, "bounced": 1,
         "replies": 1, "unique_replies": 1, "replies_automatic": 0, "unique_replies_automatic": 0},
    ]
    agg = inv.aggregate_daily(rows)["a@x.com"]
    assert agg["unique_replies"] == 1
    assert agg["replies_automatic"] == 7
    row = inv.build_inbox_row(account("a@x.com", "2026-07-27"), {}, {"a@x.com": agg}, NOW)
    assert row["reply_rate_7d"] == pytest.approx(1.0 / 50)
    assert row["reply_rate_7d"] > 0
    assert row["replies_automatic_7d"] == 7


def test_real_snapshot_has_a_day_where_automatic_exceeds_replies(recorded):
    """Guards the claim above against the actual recorded pull."""
    day = [r for r in recorded["daily"] if r["date"] == "2026-09-19"]
    assert day, "the 2026-09-19 rows are the evidence; the fixture changed"
    assert sum(r["replies"] for r in day) == 0
    assert sum(r["replies_automatic"] for r in day) == 7


def test_classify_role_precedence():
    old = 60
    young = 2
    assert inv.classify_role({"status": 1}, True, old) == inv.ROLE_ACTIVE
    assert inv.classify_role({"status": 1}, False, old) == inv.ROLE_INSURANCE
    assert inv.classify_role({"status": 1}, False, young) == inv.ROLE_WARMING
    # A paused or half-built account is retired even when a campaign still
    # lists it: promoting one of those is how a dead inbox ends up sending.
    assert inv.classify_role({"status": 2}, True, old) == inv.ROLE_RETIRED
    assert inv.classify_role({"status": 1, "setup_pending": True}, True, old) == inv.ROLE_RETIRED


def test_daily_limit_of_honours_an_explicit_zero():
    """`row.get("daily_limit") or 25` reads a deliberate 0 as 25 and overstates
    the target-date plan by 25/day per held-back inbox."""
    assert inv.daily_limit_of({"daily_limit": 0}, inv.PER_INBOX_DAILY_LIMIT) == 0
    assert inv.daily_limit_of({"daily_limit": 30}, inv.PER_INBOX_DAILY_LIMIT) == 30
    assert inv.daily_limit_of({}, inv.PER_INBOX_DAILY_LIMIT) == 25
    assert inv.daily_limit_of({"daily_limit": None}, 0) == 0


# ---------------------------------------------------------------- inventory
def test_inventory_matches_the_measured_estate(inventory):
    counts = inventory["counts"]
    assert counts["inboxes"] == 45
    assert counts["domains"] == 15
    # No "insurance" total: that is a reserve count, and the reserve is
    # Lorenzo's call, not this job's (2026-09-22).
    assert counts["by_role"] == {"active": 12, "warming": 33, "retired": 0}
    actives = [r for r in inventory["inboxes"] if r["role"] == "active"]
    assert sorted(set(r["domain"] for r in actives)) == [
        "adveromedia.com", "myadvero.com", "proadvero.com", "theadvero.com"]
    assert all(r["daily_limit"] == 25 for r in actives)
    assert all(r["warmup_enabled"] for r in inventory["inboxes"])
    assert all(r["warmup_health"] == 100 for r in inventory["inboxes"])
    assert all(len(r["campaign_keys"]) == 6 for r in actives)


def test_every_active_inbox_is_in_every_campaign(inventory):
    """The fact promote_insurance's capacity arithmetic turns on.

    All twelve live inboxes sit in all six campaign email_lists, so pulling one
    out of ONE campaign does not stop it sending and costs 0/day, not 25/day.
    """
    actives = [r for r in inventory["inboxes"] if r["role"] == "active"]
    assert len(actives) == 12
    assert set(len(r["campaign_ids"]) for r in actives) == {6}


def test_inventory_reply_and_bounce_rates_match_the_stated_live_facts(inventory):
    actives = [r for r in inventory["inboxes"] if r["role"] == "active"]
    sent = sum(r["sent_7d"] for r in actives)
    bounced = sum(r["bounced_7d"] for r in actives)
    replies = sum(r["unique_replies_7d"] for r in actives)
    assert sent == 1800
    assert bounced == 20
    assert replies == 19
    assert 0.010 <= float(bounced) / sent <= 0.013     # the brief's "about 1.2 percent"
    assert 0.010 <= float(replies) / sent <= 0.013
    assert all(r["sent_7d"] == 0 for r in inventory["inboxes"] if r["role"] == "warming")


def test_section6_flags_fire_on_the_right_inboxes(inventory):
    below = [r["email"] for r in inventory["inboxes"] if "reply_rate_below_1pct" in r["flags"]]
    # 150 sends each in the window (>= the 100-send minimum) and 0 or 1 reply.
    assert len(below) == 5
    for email in below:
        row = [r for r in inventory["inboxes"] if r["email"] == email][0]
        assert row["sent_7d"] >= inv.REPLY_RATE_MIN_SENT
        assert row["reply_rate_7d"] < inv.REPLY_RATE_ALERT
    # No inbox is flagged for reply rate on zero sends.
    assert not [r for r in inventory["inboxes"]
                if r["sent_7d"] == 0 and "reply_rate_below_1pct" in r["flags"]]
    # The two-day-old warming inboxes are marked immature rather than healthy.
    warming = [r for r in inventory["inboxes"] if r["role"] == "warming"]
    assert all("warmup_score_immature" in r["flags"] for r in warming)


@pytest.mark.parametrize("sent,replies,bounced,health,expected_flags", [
    # Exactly the Section 6 boundaries. Flipping any `<` to `<=` (or `>` to
    # `>=`) in _flags removes healthy inboxes from live campaigns on the next
    # Friday audit, and nothing else in the suite would notice.
    (100, 1, 0, 100, []),                            # exactly 1.00% reply: not flagged
    (100, 0, 0, 100, ["reply_rate_below_1pct"]),     # 0% on exactly the minimum sends
    (99, 0, 0, 100, []),                             # one send short of the minimum
    (100, 5, 2, 100, []),                            # exactly 2.00% bounce: not flagged
    (100, 5, 3, 100, ["bounce_above_2pct"]),         # 3% bounce
    (100, 5, 0, 98, []),                             # warm-up exactly 98: not flagged
    (100, 5, 0, 97, ["warmup_below_98"]),            # 97
])
def test_flags_at_exactly_the_section6_thresholds(sent, replies, bounced, health, expected_flags):
    daily = [{"email_account": "a@x.com", "date": "2026-09-20", "sent": sent,
              "bounced": bounced, "replies": replies, "unique_replies": replies,
              "replies_automatic": 0, "unique_replies_automatic": 0}]
    built = inv.build_inventory(
        [account("a@x.com", "2026-07-01", stat_warmup_score=health)],
        [{"id": "c1", "status": 1, "daily_limit": 50, "email_list": ["a@x.com"]}],
        daily, NOW)
    row = built["inboxes"][0]
    assert row["role"] == "active"
    assert inv.actionable_flags(row) == expected_flags


@pytest.mark.parametrize("reply_rate,expected", [
    (0.0199, 25),
    (0.02, 30),      # exactly 2.00% earns the ramp
    (0.0201, 30),
])
def test_thirty_a_day_is_earned_at_exactly_two_percent(reply_rate, expected):
    base = {"role": "active", "warmup_ready_date": "2026-08-17", "age_days": 57,
            "status": 1, "setup_pending": False}
    segments = inv.ramp_segments(dict(base, reply_rate_7d=reply_rate), NOW)
    assert segments[-1]["daily_limit"] == expected


def test_no_domain_is_over_the_three_inbox_cap(inventory):
    for domain in inventory["domains"]:
        assert domain["inboxes"] <= inv.MAX_INBOXES_PER_DOMAIN
        assert domain["over_inbox_cap"] is False


def test_inboxes_only_in_a_paused_campaign_are_not_counted_as_active_capacity():
    """Staging a scale-up is a draft campaign with the new inboxes pre-assigned.

    campaign_limits has always skipped a campaign with status != 1; membership
    did not, so the same report claimed 875/day of active capacity under a
    300/day campaign ceiling, and the staged inboxes silently stopped being
    promotion candidates.
    """
    accounts = [account("spare%d@d%d.com" % (i % 3, i // 3)) for i in range(3)]
    draft = {"id": "draft1", "name": "staged", "status": 0, "daily_limit": 500,
             "email_list": [a["email"] for a in accounts]}
    built = inv.build_inventory(accounts, [draft], [], NOW)
    assert built["counts"]["by_role"] == {"active": 0, "warming": 0, "retired": 0}
    assert all(r["role"] == inv.ROLE_INSURANCE for r in built["inboxes"])
    cap = built["capacity"]
    assert cap["today"]["active_capacity_per_day"] == 0
    assert "no_active_capacity" in cap["alerts"]
    assert cap["campaign_limits"]["active_campaigns"] == 0
    # The membership is not lost, it is reported as context rather than capacity.
    row = built["inboxes"][0]
    assert row["inactive_campaign_ids"] == ["draft1"]
    assert "in_paused_campaign" in row["flags"]
    assert inv.actionable_flags(row) == []


def test_a_correctly_ramped_30_a_day_inbox_is_not_flagged_off_plan():
    """From 2026-11-01 an inbox clearing 2% real replies is SUPPOSED to be at
    30/day. Flagging that as off-plan puts every ramped inbox in the table that
    carries Section 6 alerts."""
    when = at("2026-11-05T07:00:00")
    daily = [{"email_account": "a@x.com", "date": "2026-11-03", "sent": 100, "bounced": 0,
              "replies": 3, "unique_replies": 3, "replies_automatic": 0,
              "unique_replies_automatic": 0}]
    campaigns = [{"id": "c1", "status": 1, "daily_limit": 50, "email_list": ["a@x.com"]}]
    ramped = inv.build_inventory([account("a@x.com", "2026-07-01", daily_limit=30)],
                                 campaigns, daily, when)["inboxes"][0]
    assert ramped["reply_rate_7d"] == 0.03
    assert ramped["planned_daily_limit"] == 30
    assert "daily_limit_off_plan" not in ramped["flags"]
    # ... and an inbox that did NOT earn the ramp is still flagged at 30/day.
    unearned = inv.build_inventory([account("b@x.com", "2026-07-01", daily_limit=30)],
                                   [{"id": "c1", "status": 1, "daily_limit": 50,
                                     "email_list": ["b@x.com"]}], [], when)["inboxes"][0]
    assert unearned["planned_daily_limit"] == 25
    assert "daily_limit_off_plan" in unearned["flags"]


def test_an_inbox_held_at_zero_a_day_is_flagged_and_counted_as_zero():
    accounts = [account("a@x.com", daily_limit=0), account("b@x.com")]
    campaigns = [{"id": "c1", "status": 1, "daily_limit": 50,
                  "email_list": ["a@x.com", "b@x.com"]}]
    built = inv.build_inventory(accounts, campaigns, [], NOW)
    zeroed = [r for r in built["inboxes"] if r["email"] == "a@x.com"][0]
    assert "daily_limit_zero" in zeroed["flags"]
    assert built["capacity"]["today"]["active_capacity_per_day"] == 25


# ------------------------------------------------ capacity today, health only
# Lorenzo, 2026-09-22: "Health alerts only". How many inboxes to hold and when
# to buy more is his decision, so the job carries no reserve count, no reserve
# target, no go-live forecast and no order size. What is left is what the
# estate sends TODAY and the alerts that say nothing is sending at all.
REMOVED_CAPACITY_KEYS = (
    "order_to_meet_rule", "cap_active_instead", "on_target_date", "target_date",
    "target_date_passed", "readiness_judged_at", "planned_active_inboxes_rule",
    "order_by_date_for_target", "order_by_date_missed", "days_late",
    "earliest_ready_if_ordered_today", "earliest_ready_slips_target_by_days", "target_note",
    "warmup_days", "setup_days",
)


def test_capacity_today_reports_what_is_sending_and_nothing_else(inventory):
    cap = inventory["capacity"]
    assert cap["today"] == {"active_inboxes": 12, "active_capacity_per_day": 300,
                            "warming_inboxes": 33, "retired_inboxes": 0}
    assert cap["alerts"] == []
    for key in REMOVED_CAPACITY_KEYS:
        assert key not in cap, key


def test_the_reserve_and_order_helpers_are_gone():
    for name in ("capacity_plan", "insurance_requirement", "ready_by", "INSURANCE_RATIO",
                 "PLANNED_ACTIVE_INBOXES", "GO_LIVE_DATE", "SETUP_DAYS"):
        assert not hasattr(inv, name), name


def test_empty_account_list_is_not_reported_as_ok():
    """An API-key scope change or a workspace switch empties the accounts pull.
    That is the sending estate failing, so it is still an alert."""
    built = inv.build_inventory([], [], [], NOW)
    assert built["capacity"]["alerts"] == ["no_inboxes"]


def test_an_estate_with_nothing_sending_raises_an_alert():
    accounts = [account("a@x.com"), account("b@y.com")]
    built = inv.build_inventory(accounts, [], [], NOW)
    assert built["capacity"]["alerts"] == ["no_active_capacity"]
    title, body = inv._digest(built)
    assert "ALERT: no_active_capacity" in body


def test_the_cli_no_longer_takes_the_planning_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    for flag in (["--target", "2026-12-01"], ["--planned-active", "30"]):
        with pytest.raises(SystemExit):
            inv.main(["--dry-run", "--fixtures"] + flag)


# ---------------------------------------------------------------- ramp plan
def test_ramp_plan_keeps_warmup_on_in_every_segment(inventory):
    plan = inventory["ramp_plan"]["per_inbox"]
    assert len(plan) == 45
    for email, segments in plan.items():
        assert segments, email
        for segment in segments:
            assert segment["warmup"] == "on", email


def test_ramp_plan_holds_warming_inboxes_at_zero_until_they_are_ready(inventory):
    plan = inventory["ramp_plan"]["per_inbox"]
    warming = [r for r in inventory["inboxes"] if r["role"] == "warming"][0]
    segments = plan[warming["email"]]
    assert segments[0]["daily_limit"] == 0
    assert segments[0]["from"] == "2026-09-22"
    assert segments[0]["to"] == "2026-10-10"
    assert segments[1]["from"] == "2026-10-11"
    assert segments[1]["daily_limit"] == 25
    assert segments[-1]["from"] == "2026-11-01"
    # No reply history, so no inbox earns 30/day by default.
    assert segments[-1]["daily_limit"] == 25


def test_thirty_a_day_is_earned_only_above_two_percent():
    base = {"role": "active", "warmup_ready_date": "2026-08-17", "age_days": 57,
            "status": 1, "setup_pending": False}
    under = inv.ramp_segments(dict(base, reply_rate_7d=0.0133), NOW)
    assert under[-1]["daily_limit"] == 25
    assert "under" in under[-1]["reason"]
    over = inv.ramp_segments(dict(base, reply_rate_7d=0.0201), NOW)
    assert over[-1]["daily_limit"] == 30
    assert over[-1]["from"] == "2026-11-01"
    none_yet = inv.ramp_segments(dict(base, reply_rate_7d=None), NOW)
    assert none_yet[-1]["daily_limit"] == 25


def test_active_inboxes_run_at_25_a_day_until_the_ramp_date(inventory):
    plan = inventory["ramp_plan"]["per_inbox"]
    active = [r for r in inventory["inboxes"] if r["role"] == "active"][0]
    segments = plan[active["email"]]
    assert segments[0]["from"] == "2026-09-22"
    assert segments[0]["to"] == "2026-10-31"
    assert segments[0]["daily_limit"] == 25


@pytest.mark.parametrize("when", ["2026-09-22T00:45:00", "2026-11-02T07:00:00",
                                  "2026-12-15T07:00:00", "2027-03-01T07:00:00"])
def test_ramp_segments_never_invert(recorded, when):
    """ramp_plan.per_inbox is a data contract. A fixed 2026-11-01 horizon makes
    every segment run backwards on any run after it, and anything selecting the
    segment where from <= today <= to finds none."""
    built = inv.build_inventory(recorded["accounts"], recorded["campaigns"],
                                recorded["daily"], at(when))
    for email, segments in built["ramp_plan"]["per_inbox"].items():
        for segment in segments:
            assert segment["from"] <= segment["to"], (email, segment)


def test_an_inbox_whose_warmup_ends_after_the_plan_horizon_has_a_forward_window():
    row = {"role": "warming", "warmup_ready_date": "2026-11-12", "age_days": 3,
           "status": 1, "setup_pending": False, "reply_rate_7d": None}
    segments = inv.ramp_segments(row, at("2026-10-25T09:00:00"))
    assert [s["from"] <= s["to"] for s in segments] == [True, True]
    assert segments[-1]["from"] == "2026-11-12"
    assert segments[-1]["open_ended"] is True


# ---------------------------------------------------------------- promotion
def _synthetic_inventory(active_by_domain, insurance, sent_for=None, now=NOW):
    """active_by_domain: {domain: n}; insurance: [(email, health, bounce, age)].

    ``sent_for`` is {email: (sent, bounced, replies)} for insurance inboxes that
    have a measured window.
    """
    accounts = []
    email_list = []
    personas = ["lorenzo", "lorenzov", "lorenzovillarreal"]
    for domain, count in active_by_domain.items():
        for i in range(count):
            email = "%s@%s" % (personas[i], domain)
            email_list.append(email)
            accounts.append(account(email))
    for email, health, _bounce, age_days in insurance:
        start = (now.date() - timedelta(days=age_days)).isoformat()
        accounts.append(account(email, start, stat_warmup_score=health))
    campaign_id = __import__("shared.settings", fromlist=["x"]).CAMPAIGNS["cleaning_reactivation"]["id"]
    campaigns = [{"id": campaign_id, "name": "2026 Cleaning - Client Reactivation",
                  "status": 1, "daily_limit": 50, "email_list": email_list}]
    daily = []
    for email, _h, bounce, _a in insurance:
        if bounce:
            daily.append({"email_account": email, "date": "2026-09-20", "sent": 100,
                          "bounced": int(bounce * 100), "replies": 3, "unique_replies": 3,
                          "replies_automatic": 0, "unique_replies_automatic": 0})
    for email, numbers in (sent_for or {}).items():
        sent, bounced, replies = numbers
        daily.append({"email_account": email, "date": "2026-09-20", "sent": sent,
                      "bounced": bounced, "replies": replies, "unique_replies": replies,
                      "replies_automatic": 0, "unique_replies_automatic": 0})
    return inv.build_inventory(accounts, campaigns, daily, now), campaigns


def test_promote_insurance_picks_the_healthiest_candidate():
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3, "b.com": 3},
        [("lorenzo@spare1.com", 92, 0, 30), ("lorenzo@spare2.com", 100, 0, 25),
         ("lorenzo@spare3.com", 100, 0, 40)])
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["status"] == "proposed"
    # health 100 beats 92; among the two at 100 the older inbox wins.
    assert record["promote"] == "lorenzo@spare3.com"
    assert record["remove"] == "lorenzo@a.com"
    assert "lorenzo@a.com" not in record["proposed_email_list"]
    assert "lorenzo@spare3.com" in record["proposed_email_list"]
    assert len(record["proposed_email_list"]) == len(record["current_email_list"])
    assert record["promote_health"]["warmup_health"] == 100


def test_a_measured_clean_candidate_outranks_one_with_no_data():
    """A missing bounce rate used to score 0.0, the best value there is, so an
    inbox with no analytics outranked one measured clean."""
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3}, [("lorenzo@spare1.com", 100, 0, 40), ("lorenzo@spare2.com", 100, 0, 30)],
        sent_for={"lorenzo@spare2.com": (200, 0, 6)})
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["promote"] == "lorenzo@spare2.com"
    assert record["promote_health"]["bounce_rate_7d"] == 0.0
    assert record["promote_health"]["sent_7d"] == 200


def test_promote_insurance_refuses_a_candidate_with_no_analytics():
    """The fail-open gate: _flags produces nothing when the analytics window is
    missing, so an inbox at 8% bounce read as "the healthiest insurance inbox"
    and went into the change-set's PATCH payload."""
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3}, [("lorenzo@hot.com", 100, 0, 83)],
        sent_for={"lorenzo@hot.com": (200, 16, 0)})
    # with the analytics row present, the 8% bounce is caught by the flags
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["status"] == "removed_without_replacement"
    assert "bounce_above_2pct" in record["candidates_considered"][0]["rejected_because"]

    # ... and with the chunk that carried it lost, it must NOT read as clean
    accounts = [account("lorenzo@%s" % d) for d in ("a.com",) for _ in range(1)]
    accounts = [account(e) for e in ("lorenzo@a.com", "lorenzov@a.com", "lorenzovillarreal@a.com")]
    accounts.append(account("lorenzo@hot.com", "2026-07-01"))
    blind = inv.build_inventory(
        accounts, campaigns, [], NOW, missing_analytics=["lorenzo@hot.com"])
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", blind,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["status"] == "removed_without_replacement"
    assert record["promote"] is None
    assert "no 7-day analytics" in record["candidates_considered"][0]["rejected_because"]


def test_promote_insurance_refuses_an_inbox_previously_removed_for_health():
    """Nothing else remembers why an inbox left a campaign. A week after it was
    pulled for a 6% bounce its window is empty, it files as insurance with no
    flags, and the age tiebreak makes the burnt one beat the clean spare."""
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3},
        [("lorenzo@burnt.com", 100, 0, 121), ("lorenzo@clean.com", 100, 0, 40)])
    quarantined = {"lorenzo@burnt.com": {"since": "2026-09-22T00:45:00-05:00",
                                         "reason": "removed for bounce_above_2pct"}}
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined=quarantined)
    assert record["promote"] == "lorenzo@clean.com"
    burnt = [c for c in record["candidates_considered"] if c["email"] == "lorenzo@burnt.com"][0]
    assert "quarantined" in burnt["rejected_because"]
    # without the ledger the oldest inbox wins, which is the bug
    without = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                    campaigns=campaigns, now=NOW, quarantined={})
    assert without["promote"] == "lorenzo@burnt.com"


def test_quarantine_ledger_round_trips(tmp_env):
    from shared.store import get_store
    store = get_store(force_new=True)
    assert inv.load_quarantine(store) == {}
    inv.quarantine_inbox("a@x.com", reason="removed for bounce", flags=["bounce_above_2pct"],
                         campaign_key="cleaning_reactivation", now=NOW, store=store)
    ledger = inv.load_quarantine(store)
    assert "a@x.com" in ledger
    assert ledger["a@x.com"]["flags"] == ["bounce_above_2pct"]
    assert inv.clear_quarantine("a@x.com", store=store) is True
    assert inv.load_quarantine(store) == {}
    assert inv.clear_quarantine("a@x.com", store=store) is False


def test_promote_insurance_never_puts_a_fourth_inbox_from_one_domain_in_a_campaign():
    # b.com already has all 3 of its inboxes in the campaign, and it is the
    # only domain with spare inboxes: the swap must not top it up.
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3, "b.com": 3},
        [("lorenzovillarreal2@b.com", 100, 0, 40)])
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["status"] == "removed_without_replacement"
    assert record["promote"] is None
    assert record["capacity_delta_per_day"] == -25
    rejected = [c for c in record["candidates_considered"]
                if c["email"] == "lorenzovillarreal2@b.com"][0]
    assert "cap 3" in rejected["rejected_because"]
    counts = record["domain_counts_after"]
    assert max(counts.values()) <= inv.MAX_INBOXES_PER_DOMAIN


def test_promote_insurance_removes_the_failing_inbox_even_with_no_replacement():
    inventory, campaigns = _synthetic_inventory({"a.com": 3}, [])
    record = inv.promote_insurance("cleaning_reactivation", "lorenzov@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["status"] == "removed_without_replacement"
    assert "lorenzov@a.com" not in record["proposed_email_list"]
    assert len(record["proposed_email_list"]) == 2


def test_promotion_capacity_delta_counts_the_estate_not_one_email_list(recorded):
    """All twelve live inboxes are in all six campaigns, so removing one from
    ONE campaign does not stop it sending and costs 0/day, not -25/day. The
    -25 was both the wrong number and the wrong conclusion."""
    inventory = inv.build_inventory(recorded["accounts"], recorded["campaigns"],
                                    recorded["daily"], NOW)
    record = inv.promote_insurance("cleaning_reactivation", "lorenzov@theadvero.com",
                                   inventory, campaigns=recorded["campaigns"], now=NOW,
                                   quarantined={})
    assert record["status"] == "removed_without_replacement"
    assert len(record["remaining_campaigns"]) == 5
    assert record["failing_inbox_still_sends"] is True
    assert record["capacity_delta_per_day"] == 0
    assert "one change-set per campaign" in record["reason"]
    assert "300" in record["capacity_note"]          # the binding campaign ceiling


def test_a_swap_adds_the_promoted_inboxs_capacity_when_the_failing_one_keeps_sending():
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3}, [("lorenzo@spare.com", 100, 0, 40)])
    second = dict(campaigns[0], id="other-campaign-id", name="second")
    inventory["inboxes"] = [
        dict(r, campaign_ids=r["campaign_ids"] + ["other-campaign-id"],
             campaign_keys=r["campaign_keys"] + ["cleaning_trigger"])
        if r["role"] == "active" else r
        for r in inventory["inboxes"]]
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns + [second], now=NOW, quarantined={})
    assert record["promote"] == "lorenzo@spare.com"
    assert record["remaining_campaigns"] == ["cleaning_trigger"]
    assert record["capacity_delta_per_day"] == 25


def test_promote_insurance_rejects_a_candidate_carrying_a_section6_flag():
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3}, [("lorenzo@hot.com", 100, 0.05, 40)])   # 5% bounce
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["status"] == "removed_without_replacement"
    rejected = record["candidates_considered"][0]
    assert "bounce_above_2pct" in rejected["rejected_because"]


def test_promote_insurance_rejects_unknown_campaign_and_unlisted_inbox():
    inventory, campaigns = _synthetic_inventory({"a.com": 3}, [])
    bad_campaign = inv.promote_insurance("no_such_campaign", "lorenzo@a.com", inventory,
                                         campaigns=campaigns, now=NOW, quarantined={})
    assert bad_campaign["status"] == "unknown_campaign"
    assert bad_campaign["patch"] is None
    not_listed = inv.promote_insurance("cleaning_reactivation", "nobody@nowhere.com", inventory,
                                       campaigns=campaigns, now=NOW, quarantined={})
    assert not_listed["status"] == "inbox_not_in_campaign"
    assert not_listed["patch"] is None


def test_promote_insurance_uses_the_recorded_live_email_list(recorded):
    """An address in a live email_list that is no longer an account is invisible
    to a list rebuilt from the account rows, and apply_promotion then refuses
    the change-set for a mismatch that regenerating reproduces exactly."""
    campaigns = copy.deepcopy(recorded["campaigns"])
    key = __import__("shared.settings", fromlist=["x"]).CAMPAIGNS["cleaning_reactivation"]["id"]
    for campaign in campaigns:
        if campaign["id"] == key:
            campaign["email_list"] = list(campaign["email_list"]) + ["lorenzo@deleted-domain.com"]
    inventory = inv.build_inventory(recorded["accounts"], campaigns, recorded["daily"], NOW)
    # campaigns=None: the inventory's own recorded lists are used, not a rebuild
    record = inv.promote_insurance("cleaning_reactivation", "lorenzov@theadvero.com",
                                   inventory, now=NOW, quarantined={})
    assert len(record["current_email_list"]) == 13
    assert record["current_email_list_source"] == "inventory.campaigns"
    assert record["unknown_addresses_in_email_list"] == ["lorenzo@deleted-domain.com"]


def test_promote_insurance_is_a_changeset_and_never_a_live_patch():
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3}, [("lorenzo@spare.com", 100, 0, 40)])
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["live_patch_performed"] is False
    assert record["patch"]["method"] == "PATCH"
    assert set(record["patch"]["payload"]) == {"email_list"}
    # The function takes no client and cannot reach the network: promote_insurance's
    # signature has no transport argument at all.
    import inspect
    assert "client" not in inspect.signature(inv.promote_insurance).parameters


def test_write_changeset_round_trips(tmp_path):
    inventory, campaigns = _synthetic_inventory(
        {"a.com": 3}, [("lorenzo@spare.com", 100, 0, 40)])
    record = inv.promote_insurance("cleaning_reactivation", "lorenzo@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    path = inv.write_changeset(record, str(tmp_path))
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as fh:
        again = json.load(fh)
    assert again["proposed_email_list"] == record["proposed_email_list"]
    assert again["action"] == "promote_insurance"


# ------------------------------------------------------------- the apply gate
def _apply_record(**kw):
    base = {
        "action": "promote_insurance", "campaign_id": "c1", "remove": "a@d.com",
        "current_email_list": ["a@d.com"], "proposed_email_list": ["b@e.com"],
        "promote": "b@e.com",
        "promote_health": {"warmup_health": 100, "bounce_rate_7d": None, "reply_rate_7d": None,
                           "sent_7d": 0, "analytics_days": 0, "analytics_missing": False,
                           "age_days": 40, "flags": []},
    }
    base.update(kw)
    return base


def test_apply_promotion_refuses_a_stale_or_illegal_changeset():
    from changesets.capacity import apply_promotion as ap
    record = _apply_record(remove="gone@a.com",
                           current_email_list=["lorenzo@a.com", "gone@a.com"],
                           proposed_email_list=["lorenzo@a.com", "new@b.com"],
                           promote="new@b.com")
    live = {"id": "c1", "email_list": ["lorenzo@a.com", "other@a.com"]}
    problems = ap.check(record, live, accounts=[], all_campaigns=[])
    assert any("stale" in p for p in problems)
    assert any("has changed" in p for p in problems)
    assert any("not an Instantly account" in p for p in problems)

    over = _apply_record(remove="a1@d.com",
                         current_email_list=["a1@d.com", "a2@d.com", "a3@d.com"],
                         proposed_email_list=["a2@d.com", "a3@d.com", "a4@d.com", "a5@d.com"],
                         promote="a4@d.com")
    live_over = {"id": "c1", "email_list": ["a1@d.com", "a2@d.com", "a3@d.com"]}
    problems = ap.check(over, live_over, accounts=None, all_campaigns=None)
    assert any("cap 3" in p for p in problems)

    empty = dict(over, proposed_email_list=[], promote=None)
    assert any("empty" in p for p in ap.check(empty, live_over))


def test_apply_promotion_refuses_a_hand_edited_email_list():
    """check() used to validate only the `promote` field, so a change-set whose
    proposed list held someone else's inbox and a deleted address returned zero
    problems and would have been PATCHed verbatim."""
    from changesets.capacity import apply_promotion as ap
    record = _apply_record(
        proposed_email_list=["b@e.com", "someone-elses@othercampaign.com", "deleted@gone.com"])
    live = {"id": "c1", "email_list": ["a@d.com"]}
    accounts = [{"email": "b@e.com", "status": 1}]
    others = [{"id": "c2", "name": "other", "status": 1,
               "email_list": ["someone-elses@othercampaign.com"]}]
    problems = ap.check(record, live, accounts=accounts, all_campaigns=others)
    assert problems
    assert any("is not 'live minus" in p for p in problems)
    assert any("someone-elses@othercampaign.com is in the proposed email_list but is not an "
               "Instantly account" in p for p in problems)
    assert any("deleted@gone.com" in p for p in problems)


def test_apply_promotion_refuses_to_leave_the_failing_inbox_in_the_list():
    from changesets.capacity import apply_promotion as ap
    record = _apply_record(proposed_email_list=["a@d.com", "b@e.com"])
    live = {"id": "c1", "email_list": ["a@d.com"]}
    problems = ap.check(record, live)
    assert any("the removal would not happen" in p for p in problems)


def test_apply_promotion_rejects_a_candidate_that_is_already_sending():
    from changesets.capacity import apply_promotion as ap
    record = _apply_record()
    live = {"id": "c1", "email_list": ["a@d.com"]}
    accounts = [{"email": "b@e.com", "status": 1}]
    others = [{"id": "c2", "name": "2026 Cleaning - Trigger Outbound", "email_list": ["b@e.com"]}]
    problems = ap.check(record, live, accounts=accounts, all_campaigns=others)
    assert any("not insurance" in p for p in problems)


def test_apply_promotion_warns_but_does_not_block_on_a_paused_campaign():
    from changesets.capacity import apply_promotion as ap
    record = _apply_record()
    live = {"id": "c1", "email_list": ["a@d.com"]}
    accounts = [{"email": "b@e.com", "status": 1}]
    paused = [{"id": "c2", "name": "paused recruiting", "status": 2, "email_list": ["b@e.com"]}]
    warnings = []
    problems = ap.check(record, live, accounts=accounts, all_campaigns=paused, warnings=warnings)
    assert problems == []
    assert warnings and "not sending today" in warnings[0]


def test_apply_promotion_refuses_a_candidate_whose_health_was_never_measured():
    from changesets.capacity import apply_promotion as ap
    live = {"id": "c1", "email_list": ["a@d.com"]}
    accounts = [{"email": "b@e.com", "status": 1}]
    blind = _apply_record(promote_health={"warmup_health": 100, "analytics_missing": True,
                                          "flags": []})
    assert any("no 7-day analytics" in p
               for p in ap.check(blind, live, accounts=accounts, all_campaigns=[]))
    scoreless = _apply_record(promote_health={"warmup_health": None, "analytics_missing": False,
                                              "flags": []})
    assert any("no warm-up score" in p
               for p in ap.check(scoreless, live, accounts=accounts, all_campaigns=[]))
    legacy = _apply_record()
    legacy.pop("promote_health")
    assert any("predates the health gate" in p
               for p in ap.check(legacy, live, accounts=accounts, all_campaigns=[]))


def test_apply_promotion_refuses_to_apply_in_shadow(tmp_path, capsys, monkeypatch):
    from changesets.capacity import apply_promotion as ap
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    record = _apply_record(campaign_name="x", reason="test", capacity_delta_per_day=0)
    path = tmp_path / "cs.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    class Stub(object):
        patched = []

        def get_campaign(self, cid):
            return {"id": "c1", "email_list": ["a@d.com"]}

        def iterate(self, path_, params=None, body=None, max_pages=200):
            if path_ == "accounts":
                return [{"email": "b@e.com", "status": 1}]
            return [{"id": "c1", "email_list": ["a@d.com"]}]

        def update_campaign(self, cid, payload):
            Stub.patched.append((cid, payload))
            return {}

    monkeypatch.setattr(ap, "BACKUP_DIR", str(tmp_path / "backups"))
    code = ap.main(["--changeset", str(path), "--apply", "--yes"], client=Stub())
    assert code == ap.EXIT_REFUSED
    assert Stub.patched == []
    assert "refused" in capsys.readouterr().err.lower()


# ------------------------------------------------------------------- the CLI
class _ReadOnlyTransport(httpx.BaseTransport):
    """Answers the job's reads from the recorded snapshots and fails loudly on
    anything that is not a read, which is how the test proves the job cannot
    write to Instantly."""

    def __init__(self, recorded):
        self.recorded = recorded
        self.calls = []

    def handle_request(self, request):
        self.calls.append((request.method, request.url.path))
        if request.method not in ("GET", "POST"):
            raise AssertionError("inbox_inventory attempted a %s to %s"
                                 % (request.method, request.url.path))
        path = request.url.path
        if path.endswith("/accounts"):
            body = {"items": self.recorded["accounts"]}
        elif path.endswith("/campaigns"):
            body = {"items": self.recorded["campaigns"]}
        elif "analytics/daily" in path:
            wanted = set(request.url.params.get_list("emails"))
            body = [r for r in self.recorded["daily"] if r["email_account"] in wanted]
        else:
            raise AssertionError("unexpected path %s" % path)
        return httpx.Response(200, json=body,
                              headers={"content-type": "application/json"})


def test_run_against_a_mocked_api_only_reads(recorded, monkeypatch):
    from shared.instantly import Instantly
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    transport = _ReadOnlyTransport(recorded)
    client = Instantly(api_key="test-key", transport=transport)
    inventory = inv.run(NOW, client=client)
    assert inventory["counts"]["by_role"]["active"] == 12
    assert inventory["capacity"]["today"]["active_capacity_per_day"] == 300
    assert inventory["analytics_errors"] == []
    assert inventory["source_errors"] == []
    assert all(method in ("GET", "POST") for method, _ in transport.calls)
    assert not [p for _, p in transport.calls if "pause" in p or "resume" in p]


def test_one_analytics_chunk_failing_is_retried_at_half_size(recorded, monkeypatch):
    """A 413 on a chunk is the documented behaviour of this workspace. Halving
    the chunk recovers the data instead of losing 15 inboxes' week."""
    from shared.instantly import Instantly, InstantlyError

    class Flaky(_ReadOnlyTransport):
        def handle_request(self, request):
            if "analytics/daily" in request.url.path and not self.failed:
                self.failed = True
                return httpx.Response(413, json={"error": "Analytics request is too large"})
            return _ReadOnlyTransport.handle_request(self, request)

    transport = Flaky(recorded)
    transport.failed = False
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    client = Instantly(api_key="test-key", transport=transport, sleep=lambda s: None)
    inventory = inv.run(NOW, client=client)
    assert inventory["counts"]["inboxes"] == 45
    assert inventory["analytics_errors"] == []
    assert len(inventory["analytics_retries"]) == 1
    assert "413" in inventory["analytics_retries"][0]
    # nothing was lost: the twelve active inboxes still carry their 1,800 sends
    actives = [r for r in inventory["inboxes"] if r["role"] == "active"]
    assert sum(r["sent_7d"] for r in actives) == 1800
    assert inventory["counts"]["analytics_missing"] == 0
    assert isinstance(InstantlyError, type)


def test_a_persistent_analytics_outage_marks_the_rows_instead_of_zeroing_them(recorded, monkeypatch):
    """The silent-data-loss case: with every chunk answering 413 the twelve
    active inboxes' sent_7d went 1,800 -> 0, their reply rates became None, the
    flag table went from 5 to 0 and the run still reported success."""
    from shared.instantly import Instantly

    class Dead(_ReadOnlyTransport):
        def handle_request(self, request):
            if "analytics/daily" in request.url.path:
                return httpx.Response(413, json={"error": "Analytics request is too large"})
            return _ReadOnlyTransport.handle_request(self, request)

    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    client = Instantly(api_key="test-key", transport=Dead(recorded), sleep=lambda s: None)
    inventory = inv.run(NOW, client=client)
    assert inventory["counts"]["inboxes"] == 45
    assert inventory["counts"]["analytics_missing"] == 45
    assert inventory["counts"]["analytics_missing_active"] == 12
    assert inventory["analytics_errors"]
    actives = [r for r in inventory["inboxes"] if r["role"] == "active"]
    assert all(r["analytics_missing"] for r in actives)
    assert all("analytics_missing" in r["flags"] for r in actives)
    printed = inv.render(inventory)
    assert "have NO 7-day analytics" in printed
    title, message = inv._digest(inventory)
    assert "NO analytics" in title
    assert "no 7-day analytics" in message


def test_a_truncated_accounts_walk_downgrades_the_run_to_partial(recorded, monkeypatch):
    """shared/instantly.py added CursorWalk.truncated precisely so a partial
    pull cannot pass as a complete one; discarding it makes an understated
    estate look like a healthy one."""
    from shared.instantly import Instantly

    class Endless(_ReadOnlyTransport):
        def handle_request(self, request):
            if request.url.path.endswith("/accounts"):
                return httpx.Response(200, json={"items": self.recorded["accounts"][:2],
                                                 "next_starting_after": "cursor"},
                                      headers={"content-type": "application/json"})
            return _ReadOnlyTransport.handle_request(self, request)

    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    client = Instantly(api_key="test-key", transport=Endless(recorded), sleep=lambda s: None)
    inventory = inv.run(NOW, client=client)
    assert inventory["source_errors"]
    assert "truncated" in inventory["source_errors"][0]
    assert "PARTIAL account list" in inv.render(inventory)


def test_cli_dry_run_writes_a_job_log_row_and_no_config_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.delenv("JOB_LOG_PATH", raising=False)
    monkeypatch.delenv("SHADOW_LOG_PATH", raising=False)
    out = tmp_path / "inbox_inventory.json"
    code = inv.main(["--dry-run", "--fixtures", "--as-of", "2026-09-22T00:45:00-05:00",
                     "--out", str(out)])
    assert code == 0
    assert not out.exists()
    printed = capsys.readouterr().out
    assert "300/day from 12 active inbox(es)" in printed
    assert "2 inbox(es) unhealthy on theadvero.com: reply_rate_below_1pct" in printed
    assert_no_reserve_or_buy_text(printed)
    log = tmp_path / "scratch" / inv.JOB / "job_log.csv"
    assert log.exists()
    rows = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2                      # header + exactly one row per run
    assert inv.JOB in rows[1]


def test_cli_now_writes_the_inventory_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    out = tmp_path / "inbox_inventory.json"
    code = inv.main(["--now", "--fixtures", "--as-of", "2026-09-22T00:45:00-05:00",
                     "--out", str(out)])
    assert code == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["counts"]["inboxes"] == 45
    assert_no_reserve_or_order_keys(written)
    assert written["mode"] == "shadow"
    assert len(written["ramp_plan"]["per_inbox"]) == 45


def test_cli_refuses_to_overwrite_the_deliverable_with_replayed_fixtures(tmp_path, monkeypatch,
                                                                        capsys):
    """--out defaults to the shipped config/inbox_inventory.json, so `--now
    --fixtures` silently rewrote a live-looking deliverable from snapshots."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    code = inv.main(["--now", "--fixtures", "--as-of", "2026-09-22T00:45:00-05:00"])
    assert code == 1
    assert "refusing --now --fixtures" in capsys.readouterr().err


def test_cli_promote_writes_the_changeset(tmp_path, monkeypatch, capsys):
    """The one command this component exists for. argparse used to force
    --dry-run when neither flag was given, so the documented invocation printed
    a proposal and wrote nothing at the moment an inbox was burning."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setattr(inv, "CHANGESET_DIR", str(tmp_path / "capacity"))
    code = inv.main(["--promote", "cleaning_reactivation:lorenzov@theadvero.com",
                     "--fixtures", "--as-of", "2026-09-22T00:45:00-05:00"])
    assert code == 0
    written = sorted(os.listdir(str(tmp_path / "capacity")))
    assert len(written) == 1
    assert written[0].startswith("promote_cleaning_reactivation_lorenzov_at_theadvero.com")
    record = json.loads((tmp_path / "capacity" / written[0]).read_text(encoding="utf-8"))
    assert record["action"] == "promote_insurance"
    assert record["remove"] == "lorenzov@theadvero.com"
    assert record["live_patch_performed"] is False
    printed = capsys.readouterr().out
    assert "change-set: " in printed
    assert "not written" not in printed
    # the removed inbox is quarantined so it cannot come back as "healthiest"
    from shared.store import get_store
    assert "lorenzov@theadvero.com" in inv.load_quarantine(get_store(force_new=True))
    # ... and --no-changeset is the preview
    code = inv.main(["--promote", "cleaning_reactivation:lorenzo@theadvero.com",
                     "--fixtures", "--no-changeset", "--as-of", "2026-09-22T00:45:00-05:00"])
    assert code == 0
    assert sorted(os.listdir(str(tmp_path / "capacity"))) == written


def test_cli_does_not_refresh_the_inventory_just_to_write_a_changeset(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setattr(inv, "CHANGESET_DIR", str(tmp_path / "capacity"))
    out = tmp_path / "inbox_inventory.json"
    inv.main(["--promote", "cleaning_reactivation:lorenzov@theadvero.com", "--fixtures",
              "--out", str(out), "--as-of", "2026-09-22T00:45:00-05:00"])
    assert not out.exists()


def test_cli_reports_a_failure_and_alerts(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    sent = []

    def boom(*a, **k):
        raise RuntimeError("instantly is down")

    monkeypatch.setattr(inv, "run", boom)
    monkeypatch.setattr(inv, "notify", lambda *a, **k: sent.append((a, k)))
    code = inv.main(["--dry-run"])
    assert code == 1
    assert sent and "failed" in sent[0][0][0].lower()
    # shared.notify takes a LIST of tags; a bare string becomes seven letters
    assert sent[0][1]["tags"] == ["warning"]
    assert "instantly is down" in capsys.readouterr().err


def test_a_failure_after_the_reads_still_writes_a_job_log_row(monkeypatch, tmp_path, capsys):
    """write_inventory, render, log_run and the digest used to sit outside
    main()'s try/except, so a racing --now died with a traceback that left no
    Job_Log row and no alert."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    sent = []
    rows = []
    monkeypatch.setattr(inv, "notify", lambda *a, **k: sent.append((a, k)))
    monkeypatch.setattr(inv, "log_run", lambda job, status, details=None: rows.append(
        (job, status, details)))

    def boom(*a, **k):
        raise FileNotFoundError("the shared .tmp file vanished under us")

    monkeypatch.setattr(inv, "write_inventory", boom)
    out = tmp_path / "inbox_inventory.json"
    code = inv.main(["--now", "--fixtures", "--out", str(out),
                     "--as-of", "2026-09-22T00:45:00-05:00"])
    assert code == 1
    assert rows and rows[-1][1] == "error"
    assert rows[-1][2]["stage"] == "post_read"
    assert sent and sent[0][1]["tags"] == ["warning"]
    assert "failed after the reads" in capsys.readouterr().err


def test_write_inventory_survives_concurrent_writers(tmp_path):
    """A fixed "<path>.tmp" is shared state: with four writers the loser died
    on os.replace in 37 of 40 trials."""
    import threading
    path = str(tmp_path / "inventory.json")
    errors = []

    def writer(n):
        try:
            for _ in range(20):
                inv.write_inventory({"n": n}, path)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert json.loads(open(path, "r", encoding="utf-8").read())["n"] in (0, 1, 2, 3)
    # and no stray temp files survive
    assert [p for p in os.listdir(str(tmp_path)) if p.endswith(".tmp")] == []


def test_digest_flag_count_matches_the_printed_flag_table(inventory, monkeypatch):
    """The push said "38 inbox(es) flagged" while the table under it said 5.
    The 33-inbox gap was warmup_score_immature, which the runbook itself calls
    informational."""
    printed = inv.render(inventory)
    assert "FLAGGED INBOXES (5)" in printed
    title, message = inv._digest(inventory)
    assert "5 inbox(es) flagged (33 informational)" in message
    assert inventory["counts"]["flagged"] == 5
    assert inventory["counts"]["flagged_informational"] == 33


def test_digest_tags_are_a_list(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    sent = []
    monkeypatch.setattr(inv, "notify", lambda *a, **k: sent.append((a, k)))
    out = tmp_path / "inbox_inventory.json"
    inv.main(["--now", "--fixtures", "--out", str(out),
              "--as-of", "2026-09-22T00:45:00-05:00"])
    assert sent
    assert sent[0][1]["tags"] == ["chart_with_upwards_trend"]


def test_a_partial_run_refuses_to_overwrite_the_deliverable_and_exits_non_zero(
        recorded, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    out = tmp_path / "inbox_inventory.json"
    out.write_text(json.dumps({"keep": "me"}), encoding="utf-8")

    def blind(now, client=None, fixtures=None):
        return inv.build_inventory(
            recorded["accounts"], recorded["campaigns"], [], now, source="test",
            analytics_errors=["analytics for 15 inbox(es): HTTP 413"],
            missing_analytics=[(a["email"] or "").lower() for a in recorded["accounts"]])

    monkeypatch.setattr(inv, "run", blind)
    monkeypatch.setattr(inv, "notify", lambda *a, **k: None)
    code = inv.main(["--now", "--out", str(out), "--as-of", "2026-09-22T00:45:00-05:00"])
    assert code == 1
    assert json.loads(out.read_text(encoding="utf-8")) == {"keep": "me"}
    assert "refused to overwrite" in capsys.readouterr().out


def test_shipped_inventory_file_is_current_and_parseable():
    """config/inbox_inventory.json is a deliverable, not a scratch file."""
    with open(inv.INVENTORY_PATH, "r", encoding="utf-8") as fh:
        shipped = json.load(fh)
    assert shipped["counts"]["inboxes"] == 45
    assert shipped["counts"]["flagged"] == 5
    assert shipped["counts"]["flagged_informational"] == 33
    # health alerts only: the deliverable carries no reserve count or order
    assert_no_reserve_or_order_keys(shipped)
    assert shipped["capacity"]["today"]["active_capacity_per_day"] == 300
    assert shipped["rules"]["warmup_stays_on"] is True
    assert len(shipped["inboxes"]) == 45
    assert len(shipped["campaigns"]) == 6
    # the live email_lists are recorded so a change-set can be built from the file
    assert all(len(c["email_list"]) == 12 for c in shipped["campaigns"])


# --------------------------------------------------- the second capacity cap
def test_campaign_daily_limits_are_reported_as_the_other_constraint(inventory):
    """Inboxes are only half of what goes out today: six campaigns at
    daily_limit 50 add up to 300/day, exactly the 12 inboxes' 300/day. This is
    a measurement of today, with no target and no increase to make."""
    limits = inventory["capacity"]["campaign_limits"]
    assert limits["active_campaigns"] == 6
    assert limits["total_campaign_daily_limit"] == 300
    assert limits["inbox_capacity_per_day"] == 300
    assert limits["binding_constraint"] == "balanced"
    assert "required_total_campaign_limit_on_target" not in limits
    assert "campaign_limit_increase_needed" not in limits
    assert all(row["key"] for row in limits["campaigns"])


def test_campaign_limits_names_whichever_side_binds():
    assert inv.campaign_limits([{"id": "c", "status": 1, "daily_limit": 100}],
                               300)["binding_constraint"] == "campaign_daily_limit"
    assert inv.campaign_limits([{"id": "c", "status": 1, "daily_limit": 900}],
                               300)["binding_constraint"] == "inbox_capacity"
    # A paused campaign consumes no capacity and is left out of the sum.
    paused = inv.campaign_limits([{"id": "c", "status": 0, "daily_limit": 900}], 300)
    assert paused["active_campaigns"] == 0
    assert paused["total_campaign_daily_limit"] == 0


def test_the_last_ramp_segment_is_the_standing_limit_not_a_one_day_window(inventory):
    """The plan horizon is 2026-11-01, which is also the ramp date. Without the
    flag the final segment reads as a single day rather than the limit that
    stands from that date onward."""
    for segments in inventory["ramp_plan"]["per_inbox"].values():
        assert segments[-1]["open_ended"] is True
        assert segments[-1]["from"] == "2026-11-01"
        for segment in segments[:-1]:
            assert segment["open_ended"] is False




# ------------------------------------------ health alerts only (2026-09-22)
# Lorenzo cut this job to health alerts: "tracking how many sending inboxes
# there are and when to buy more is kind of my decision and not really a
# system decision". Nothing the job produces (the printed report, the ntfy
# push, the Job_Log row, config/inbox_inventory.json) may count a reserve or
# tell him to buy, order or top up. It may still say plainly that health has
# dropped, e.g. "2 inbox(es) unhealthy on theadvero.com".

BUY_OR_RESERVE_TEXT = re.compile(
    r"\b(order\w*|buy\w*|bought|purchas\w*|reserve\w*|top(ped)? up|on hand|spares?|insurance)\b",
    re.IGNORECASE)
RESERVE_OR_ORDER_KEY = re.compile(
    r"insurance|order|reserve|buy|purchase|on_hand|planned_active|target|go_live|setup_days",
    re.IGNORECASE)


def assert_no_reserve_or_buy_text(text):
    hits = sorted(set(m.group(0) for m in BUY_OR_RESERVE_TEXT.finditer(text or "")))
    assert not hits, "reserve or buying language in the output: %s\n%s" % (hits, text)


def assert_no_reserve_or_order_keys(blob, path="$"):
    """Walk the inventory. No key may name a reserve, a target or an order, and
    no string may carry buying language. Two exceptions, both documentation of
    a kept feature: the per-inbox ``role`` label (promote_insurance picks from
    it) and the ``_about`` note that explains the roles."""
    if isinstance(blob, dict):
        for key, value in blob.items():
            assert not RESERVE_OR_ORDER_KEY.search(str(key)), "%s.%s" % (path, key)
            if key in ("_about", "role"):
                continue
            assert_no_reserve_or_order_keys(value, "%s.%s" % (path, key))
    elif isinstance(blob, list):
        for i, value in enumerate(blob):
            assert_no_reserve_or_order_keys(value, "%s[%d]" % (path, i))
    elif isinstance(blob, str):
        assert not BUY_OR_RESERVE_TEXT.search(blob), "%s = %r" % (path, blob)


def _spares(n, warm_start, prefix):
    return [account("p%d@%s%d.com" % (i % 3, prefix, i // 3), warm_start=warm_start)
            for i in range(n)]


def _scenario(name):
    accounts = _load("accounts_2026-09-22.json")
    campaigns = _load("campaigns_2026-09-22.json")
    daily = _load("daily_account_analytics_2026-09-15_21.json")
    if name == "recorded_today":
        return inv.build_inventory(accounts, campaigns, daily, NOW)
    if name == "after_the_old_go_live_date":
        return inv.build_inventory(accounts, campaigns, daily, at("2026-11-15T07:00:00"))
    if name == "spares_bought_and_still_warming":
        return inv.build_inventory(accounts + _spares(24, "2026-09-23", "new"), campaigns, daily,
                                   at("2026-09-24T07:00:00"))
    if name == "warm_spares_on_hand":
        active = _spares(45, "2026-07-01", "d")
        campaign = {"id": "c1", "status": 1, "daily_limit": 1125,
                    "email_list": [a["email"] for a in active]}
        return inv.build_inventory(active + _spares(24, "2026-07-01", "s"), [campaign], [], NOW)
    if name == "empty_estate":
        return inv.build_inventory([], [], [], NOW)
    raise AssertionError(name)


@pytest.mark.parametrize("name", ["recorded_today", "after_the_old_go_live_date",
                                  "spares_bought_and_still_warming", "warm_spares_on_hand",
                                  "empty_estate"])
def test_no_output_counts_a_reserve_or_recommends_buying(name):
    built = _scenario(name)
    assert "insurance" not in built["counts"]["by_role"]
    for dom in built["domains"]:
        assert "insurance" not in dom["roles"], dom["domain"]
    assert_no_reserve_or_order_keys(built)
    assert_no_reserve_or_buy_text(inv.render(built))
    title, body = inv._digest(built)
    assert_no_reserve_or_buy_text(title)
    assert_no_reserve_or_buy_text(body)


def test_the_scheduled_run_pushes_health_and_no_buying_advice(tmp_path, monkeypatch):
    """The 07:00 `--now` run end to end: the ntfy push, the Job_Log row and the
    written deliverable."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    sent = []
    rows = []
    monkeypatch.setattr(inv, "notify", lambda *a, **k: sent.append((a, k)))
    monkeypatch.setattr(inv, "log_run", lambda job, status, details=None: rows.append(
        (job, status, details)))
    out = tmp_path / "inbox_inventory.json"
    code = inv.main(["--now", "--fixtures", "--out", str(out),
                     "--as-of", "2026-09-22T00:45:00-05:00"])
    assert code == 0
    (title, body), _kw = sent[0]
    assert title == "Inbox health: 5 inbox(es) flagged"
    assert "2 inbox(es) unhealthy on theadvero.com (reply_rate_below_1pct)." in body
    assert "12 active, 33 warming, 0 retired" in body
    assert_no_reserve_or_buy_text(title)
    assert_no_reserve_or_buy_text(body)
    job, status, details = rows[-1]
    assert (job, status) == (inv.JOB, "attention")
    assert details["flagged"] == 5 and details["unhealthy_domains"] == 4
    assert_no_reserve_or_order_keys(details)
    assert_no_reserve_or_order_keys(json.loads(out.read_text(encoding="utf-8")))


def _sick_estate():
    accounts = [
        account("off@a.com", warmup_status=0),                     # warm-up switched off
        account("sick@a.com", stat_warmup_score=95),               # health dropped under 98
        account("bouncy@b.com"),                                   # 5% bounce
        account("dead@c.com", status=-1),                          # disconnected / erroring
        account("fine@d.com"),
    ]
    campaigns = [{"id": "c1", "status": 1, "daily_limit": 250,
                  "email_list": [a["email"] for a in accounts]}]
    daily = [{"email_account": "bouncy@b.com", "date": "2026-09-20", "sent": 100, "bounced": 5,
              "replies": 3, "unique_replies": 3, "replies_automatic": 0,
              "unique_replies_automatic": 0}]
    return accounts, campaigns, daily


def test_the_health_alerts_still_fire():
    accounts, campaigns, daily = _sick_estate()
    built = inv.build_inventory(accounts, campaigns, daily, NOW)
    by_email = {r["email"]: r for r in built["inboxes"]}
    assert "warmup_off" in by_email["off@a.com"]["flags"]
    assert "warmup_below_98" in by_email["sick@a.com"]["flags"]
    assert "bounce_above_2pct" in by_email["bouncy@b.com"]["flags"]
    assert by_email["dead@c.com"]["role"] == inv.ROLE_RETIRED
    assert inv.actionable_flags(by_email["dead@c.com"]) == [
        "account_status_error", "retired_in_sending_campaign"]
    assert inv.actionable_flags(by_email["fine@d.com"]) == []
    assert built["counts"]["flagged"] == 4
    assert built["counts"]["unhealthy_domains"] == 3
    assert built["counts"]["by_role"]["retired"] == 1

    printed = inv.render(built)
    assert "2 inbox(es) unhealthy on a.com: " in printed
    assert "1 inbox(es) unhealthy on b.com: bounce_above_2pct" in printed
    assert ("1 inbox(es) unhealthy on c.com: account_status_error, retired_in_sending_campaign"
            in printed)
    assert "1 retired (not status 1: paused, disconnected or erroring)" in printed
    title, body = inv._digest(built)
    assert title == "Inbox health: 4 inbox(es) flagged"
    assert "2 inbox(es) unhealthy on a.com (" in body
    assert "warmup_off" in body and "warmup_below_98" in body
    assert "1 inbox(es) unhealthy on b.com (bounce_above_2pct)." in body
    assert "1 retired" in body
    for text in (printed, title, body):
        assert_no_reserve_or_buy_text(text)

    # an analytics outage on one inbox is a health alert of its own
    blind = inv.build_inventory(accounts, campaigns, daily, NOW, missing_analytics=["fine@d.com"])
    assert "analytics_missing" in {r["email"]: r for r in blind["inboxes"]}["fine@d.com"]["flags"]
    assert "NO analytics" in inv._digest(blind)[0]


def test_a_flagged_estate_logs_attention_and_keeps_exit_zero(tmp_path, monkeypatch):
    """Status follows health now that the reserve rule is gone. The exit code
    is unchanged: only a partial read exits 1."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    accounts, campaigns, daily = _sick_estate()
    rows = []
    monkeypatch.setattr(inv, "run", lambda now, client=None, fixtures=None: inv.build_inventory(
        accounts, campaigns, daily, now))
    monkeypatch.setattr(inv, "log_run", lambda job, status, details=None: rows.append(
        (job, status, details)))
    assert inv.main(["--dry-run", "--as-of", "2026-09-22T00:45:00-05:00"]) == 0
    assert rows[-1][1] == "attention"

    healthy = [account("fine@d.com")]
    monkeypatch.setattr(inv, "run", lambda now, client=None, fixtures=None: inv.build_inventory(
        healthy, [{"id": "c1", "status": 1, "daily_limit": 25, "email_list": ["fine@d.com"]}],
        [], now))
    assert inv.main(["--dry-run", "--as-of", "2026-09-22T00:45:00-05:00"]) == 0
    assert rows[-1][1] == "ok"


def test_a_promotion_with_no_candidate_does_not_count_the_pool():
    """The promotion change-set is kept (apply_promotion consumes it), but its
    reason no longer states the size of the spare pool."""
    inventory, campaigns = _synthetic_inventory({"a.com": 3}, [])
    record = inv.promote_insurance("cleaning_reactivation", "lorenzov@a.com", inventory,
                                   campaigns=campaigns, now=NOW, quarantined={})
    assert record["status"] == "removed_without_replacement"
    assert "pool of" not in record["reason"]
    assert not BUY_OR_RESERVE_TEXT.search(record["reason"].replace("insurance inbox", ""))


# --------------------------- review fixes: no false all-clear, idle is named
def test_a_disconnected_inbox_in_a_sending_campaign_is_never_an_all_clear(tmp_path, monkeypatch):
    """The reviewer's probe: one inbox at Instantly status -1 (connection
    error) still in a sending campaign's email_list used to push "Inbox
    health: no alerts", print "no domain has an unhealthy inbox" and log ok."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    accounts = [account("a@x.com"), account("b@x.com"), account("c@z.com"),
                account("dead@y.com", status=-1)]
    campaigns = [{"id": "c1", "status": 1, "daily_limit": 75,
                  "email_list": ["a@x.com", "b@x.com", "dead@y.com"]}]
    built = inv.build_inventory(accounts, campaigns, [], NOW)
    dead = [r for r in built["inboxes"] if r["email"] == "dead@y.com"][0]
    assert dead["role"] == inv.ROLE_RETIRED
    assert "account_status_error" in dead["flags"]
    assert "retired_in_sending_campaign" in dead["flags"]
    assert built["counts"]["flagged"] == 1 and built["counts"]["unhealthy_domains"] == 1
    printed = inv.render(built)
    assert "no domain has an unhealthy inbox" not in printed
    assert "1 inbox(es) unhealthy on y.com: account_status_error" in printed
    title, body = inv._digest(built)
    assert title == "Inbox health: 1 inbox(es) flagged"
    assert "1 inbox(es) unhealthy on y.com (account_status_error" in body

    rows, pushes = [], []
    monkeypatch.setattr(inv, "run", lambda now, client=None, fixtures=None:
                        inv.build_inventory(accounts, campaigns, [], now))
    monkeypatch.setattr(inv, "log_run", lambda job, status, details=None: rows.append(status))
    monkeypatch.setattr(inv, "notify", lambda t, m, **k: pushes.append(t))
    code = inv.main(["--now", "--out", str(tmp_path / "x.json"),
                     "--as-of", "2026-09-22T07:00:00-05:00"])
    assert code == 0
    assert rows[-1] == "attention"
    assert pushes[-1] == "Inbox health: 1 inbox(es) flagged"


@pytest.mark.parametrize("status,in_campaign,expected", [
    (-1, False, ["account_status_error"]),        # erroring, even outside every campaign
    (-2, True, ["account_status_error", "retired_in_sending_campaign"]),
    (2, True, ["retired_in_sending_campaign"]),   # paused but still listed to send
    (2, False, []),                               # paused on purpose and unlisted: not an alert
])
def test_retired_inboxes_are_flagged_only_when_they_are_an_alert(status, in_campaign, expected):
    campaigns = [{"id": "c1", "status": 1, "daily_limit": 50,
                  "email_list": ["ok@x.com"] + (["r@y.com"] if in_campaign else [])}]
    built = inv.build_inventory([account("ok@x.com"), account("r@y.com", status=status)],
                                campaigns, [], NOW)
    row = [r for r in built["inboxes"] if r["email"] == "r@y.com"][0]
    assert row["role"] == inv.ROLE_RETIRED
    assert inv.actionable_flags(row) == expected


@pytest.mark.parametrize("accounts", [[], [account("a@x.com")]])
def test_a_sending_alert_leads_the_title_even_with_nothing_flagged(accounts):
    """no_inboxes / no_active_capacity with zero flags used to title the push
    "Inbox health: 0 inbox(es) flagged"."""
    built = inv.build_inventory(accounts, [], [], NOW)
    assert built["counts"]["flagged"] == 0
    alert = built["capacity"]["alerts"][0]
    title, body = inv._digest(built)
    assert title == "Inbox health: ALERT %s" % alert
    assert "no alerts" not in title and "0 inbox(es) flagged" not in title
    assert "ALERT: %s" % alert in body


def test_a_sending_alert_and_flags_share_the_title():
    built = inv.build_inventory([account("a@x.com", stat_warmup_score=90)], [], [], NOW)
    title, _ = inv._digest(built)
    assert title == "Inbox health: ALERT no_active_capacity, 1 inbox(es) flagged"


def test_warm_inboxes_outside_every_campaign_are_labelled_idle_but_never_totalled(recorded):
    """At 2026-11-15 the 33 new inboxes are warm and in no campaign. Their
    domain rows used to print blank roles and the headline stopped adding up
    ("12 active, 0 warming, 0 retired" of 45)."""
    built = inv.build_inventory(recorded["accounts"], recorded["campaigns"], recorded["daily"],
                                at("2026-11-15T07:00:00"))
    idle = [r for r in built["inboxes"] if r["role"] == "idle"]
    assert len(idle) == 33
    assert inv.ROLE_INSURANCE == inv.ROLE_IDLE == "idle"
    assert "idle" not in built["counts"]["by_role"]
    printed = inv.render(built)
    assert ("45 inboxes on 15 domains: 12 active, 0 warming, 0 retired (not status 1: paused, "
            "disconnected or erroring), the rest idle (not in any sending campaign)") in printed
    domain_rows = printed.split("\nDOMAINS\n")[1].split("\n\n")[0].splitlines()
    assert len(domain_rows) == 15
    for line in domain_rows:
        label = line.split("inbox(es)")[1].split()[0]
        assert not label.startswith("sent7d="), "blank roles: %s" % line
    assert sum(1 for line in domain_rows if " idle " in line) == 11
    assert not re.search(r"idle\s*=\s*\d", printed)
    title, body = inv._digest(built)
    assert "the rest idle (not in any sending campaign)" in body
    assert_no_reserve_or_buy_text(printed)
    assert_no_reserve_or_buy_text(body)
    # no idle inbox, no "the rest idle" clause
    today = inv.build_inventory(recorded["accounts"], recorded["campaigns"], recorded["daily"], NOW)
    assert "the rest idle" not in inv.render(today)
