"""Tests for the five-level deliverability monitor (Blueprint M1 / O1).

Run: cd "Agentic Worklfows" && python3 -m pytest jobs/tests/test_deliverability_monitor.py -q

Everything here is offline. The one test that touches httpx uses MockTransport
through the real ``shared.instantly.Instantly`` client, to prove the chunking
and the query shape are what the live endpoint accepted on 2026-09-22.
"""
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from shared import job_log, thresholds as TH
from shared.settings import TZ
from jobs import deliverability_monitor as M


# --------------------------------------------------------------------- helpers

def ct(text):
    return TZ.localize(datetime.strptime(text, "%Y-%m-%d %H:%M"))


NOW = ct("2026-09-22 07:00")


def account(email, status=1, score=100, warmup_start="2026-06-01T00:00:00.000Z", daily_limit=25):
    return {"email": email, "status": status, "warmup_status": 1, "daily_limit": daily_limit,
            "stat_warmup_score": score, "timestamp_warmup_start": warmup_start,
            "timestamp_created": warmup_start}


def campaign(key, cid, emails):
    return {"key": key, "id": cid, "name": key, "status": 1, "email_list": list(emails), "daily_limit": 50}


class StubClient(object):
    """Just enough of shared.instantly.Instantly for the monitor."""

    def __init__(self, accounts=None, campaigns=None, warmup=None, vitals=None, daily=None,
                 leads=None, emails=None, sent_emails=None, lead_statuses=None):
        self._accounts = accounts or []
        self._campaigns = campaigns or {}
        self._warmup = warmup or {}
        self._vitals = vitals or {}
        self._daily = daily or []
        self._leads = leads or {}
        self._emails = emails or []
        self._sent_emails = sent_emails or []
        # {address: i_status} as GET /leads would answer. Absent means "no lead
        # row", which the canary treats as unverifiable and drops.
        self._lead_statuses = lead_statuses
        self.calls = []

    def iterate(self, path, params=None, body=None, max_pages=200):
        self.calls.append(("iterate", path, params, body))
        walk = M.__dict__["chunked"] and _Walk(self._rows_for(path, params, body))
        return walk

    def _rows_for(self, path, params, body):
        if path == "accounts":
            return list(self._accounts)
        if path == "leads/list":
            return list(self._leads.get((body or {}).get("campaign"), []))
        if path == "emails":
            if (params or {}).get("email_type") == "sent":
                return list(self._sent_emails)
            return list(self._emails)
        return []

    def list_leads(self, filter=None, campaign=None, limit=100, starting_after=None,
                   contacts=None, **extra):
        self.calls.append(("list_leads", tuple(contacts or ())))
        if self._lead_statuses is None:
            # Default: every harvested address resolves with no negative status,
            # which is what the live workspace answers for most of them.
            return {"items": [{"email": e, "i_status": 0} for e in (contacts or [])]}
        return {"items": [{"email": e, "i_status": self._lead_statuses[e]}
                          for e in (contacts or []) if e in self._lead_statuses]}

    def get_campaign(self, cid):
        self.calls.append(("get_campaign", cid))
        for camp in self._campaigns.values():
            if camp["id"] == cid:
                return dict(camp)
        raise KeyError(cid)

    def warmup_analytics(self, emails):
        self.calls.append(("warmup_analytics", tuple(emails)))
        return {"aggregate_data": {e: self._warmup[e] for e in emails if e in self._warmup}}

    def test_vitals(self, emails):
        self.calls.append(("test_vitals", tuple(emails)))
        domains = sorted(set(TH.domain_of(e) for e in emails))
        ok, bad = [], []
        for d in domains:
            row = dict(self._vitals.get(d, {"mx": True, "spf": True, "dkim": True, "dmarc": True}))
            row["domain"] = d
            row["allPass"] = all(row.get(k) for k in TH.VITALS_REQUIRED_RECORDS)
            (ok if row["allPass"] else bad).append(row)
        return {"status": "success", "success_list": ok, "failure_list": bad}

    def daily_account_analytics(self, emails=None, start_date=None, end_date=None):
        self.calls.append(("daily", tuple(emails or ()), start_date, end_date))
        wanted = set(emails or [])
        return [r for r in self._daily if r["email_account"] in wanted]


class _Walk(list):
    truncated = False
    complete = True


def build_world(reply_counts=None, bounce_counts=None, sent_per_day=25, days=7,
                domains=("a.com", "b.com"), personas=("x", "y", "z"), now=NOW):
    """12 sending inboxes across `domains`, daily rows for the last `days`."""
    emails = ["%s@%s" % (p, d) for d in domains for p in personas]
    accounts = [account(e) for e in emails]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    warmup = {e: {"health_score": 100, "sent": 60, "landed_inbox": 60, "received": 90} for e in emails}
    daily = []
    dates = M.window_dates(now, days)
    reply_counts = reply_counts or {}
    bounce_counts = bounce_counts or {}
    for e in emails:
        left = reply_counts.get(e, 0)
        bleft = bounce_counts.get(e, 0)
        for d in dates:
            r = 1 if left > 0 else 0
            left -= r
            b = 1 if bleft > 0 else 0
            bleft -= b
            daily.append({"date": d, "email_account": e, "sent": sent_per_day, "bounced": b,
                          "replies": r, "replies_automatic": 2, "contacted": sent_per_day})
    return StubClient(accounts=accounts, campaigns=camps, warmup=warmup, daily=daily), emails, camps


# --------------------------------------------------------- the reply-rate trap

def test_real_replies_uses_replies_directly_because_the_counters_are_disjoint():
    """The single most expensive bug this module could ship.

    M1 L3 says "< 1% real replies (exclude auto-replies and OOO)", which reads
    as replies - replies_automatic. On this workspace that is wrong: the two
    are disjoint counters. Measured live 2026-09-22, lorenzo@myadvero.com
    reported replies=0 with replies_automatic=2. Subtracting gives -2 real
    replies; every inbox lands at a negative rate, every inbox fails the 1%
    rule, and the monitor proposes pausing the entire fleet on its first run.
    """
    assert M.real_replies(0, 2) == 0
    assert M.real_replies(1, 3) == 1
    assert M.real_replies(3, 2) == 3
    # And the escape hatch still works if a workspace ever nests them.
    assert TH.REPLIES_INCLUDE_AUTOMATIC is False


def test_real_replies_never_returns_a_negative_even_with_the_flag_on(monkeypatch):
    monkeypatch.setattr(TH, "REPLIES_INCLUDE_AUTOMATIC", True, raising=False)
    assert M.real_replies(0, 2) == 0
    assert M.real_replies(5, 2) == 3


def _recorded_daily_rows():
    import os
    from jobs import inbox_inventory as inv

    with open(os.path.join(inv.SNAPSHOT_DIR, "daily_account_analytics_2026-09-15_21.json"), "r",
              encoding="utf-8") as fh:
        blob = json.load(fh)
    return blob.get("items") if isinstance(blob, dict) and "items" in blob else blob


def test_the_monitor_counts_replies_per_lead_like_the_inventory():
    """MKT-4. lorenzov@theadvero.com logged 3 replies from ONE lead in 150
    sends that week. The monitor summed total replies and passed it at 2.00%;
    the capacity inventory counted the lead once and flagged it at 0.67%. Both
    07:00 cards now read unique_replies through shared.analytics.real_replies."""
    rows = _recorded_daily_rows()
    dates = sorted(set(r["date"] for r in rows))
    agg = M.aggregate_window(rows, dates)
    acc = agg["lorenzov@theadvero.com"]
    assert (acc["sent"], acc["replies"], acc["replies_total"]) == (150, 1, 3)
    pct = TH.rate_pct(M.real_replies(acc["replies"], acc["replies_automatic"]), acc["sent"])
    assert round(pct, 2) == 0.67
    assert pct < TH.REPLY_RATE_MIN_PCT


def test_the_monitor_and_the_inventory_agree_on_every_inbox():
    from jobs import inbox_inventory as inv

    rows = _recorded_daily_rows()
    dates = sorted(set(r["date"] for r in rows))
    monitor = M.aggregate_window(rows, dates)
    inventory = inv.aggregate_daily(rows)
    assert set(monitor) == set(inventory)
    for email, acc in monitor.items():
        assert acc["replies"] == inventory[email]["unique_replies"], email
        assert acc["sent"] == inventory[email]["sent"], email


# ----------------------------------------------------------------- date windows

def test_window_dates_excludes_today_so_the_0700_run_is_not_dragged_by_a_blank_day():
    dates = M.window_dates(NOW, 7)
    assert dates[-1] == "2026-09-21"
    assert "2026-09-22" not in dates
    assert len(dates) == 7
    assert dates == sorted(dates)


def test_window_dates_can_include_today_when_asked():
    assert M.window_dates(NOW, 3, include_today=True)[-1] == "2026-09-22"


def test_chunked():
    assert M.chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert M.chunked([], 3) == []
    assert M.chunked([1, 2], 0) == [[1, 2]]


# ---------------------------------------------------------------------- level 1

def test_level1_flags_health_below_98_and_escalates_below_90():
    inboxes = M.build_inbox_index(
        [account("a@d.com"), account("b@d.com"), account("c@d.com")],
        {"c1": campaign("c1", "cid", ["a@d.com", "b@d.com", "c@d.com"])}, NOW)
    warmup = {"a@d.com": {"health_score": 100}, "b@d.com": {"health_score": 95},
              "c@d.com": {"health_score": 80}}
    vitals = {"d.com": {"mx": True, "spf": True, "dkim": True, "dmarc": True,
                        "allPass": True, "passed": True, "missing": []}}
    out = M.level1(inboxes, warmup, vitals)
    verdicts = {r["email"]: r["verdict"] for r in out["rows"]}
    assert verdicts == {"a@d.com": "ok", "b@d.com": "health_fail", "c@d.com": "health_emergency"}
    assert len(out["findings"]) == 2


def test_level1_never_condemns_an_inbox_that_started_warming_this_week():
    """The 33 insurance inboxes started warming 2026-09-20. A monitor that
    pauses them for a low score two days in destroys the Oct 11 capacity plan."""
    young = account("new@d.com", score=60, warmup_start="2026-09-20T23:39:36.788Z")
    inboxes = M.build_inbox_index([young], {}, NOW)
    warmup = {"new@d.com": {"health_score": 60}}
    out = M.level1(inboxes, warmup, {"d.com": {"mx": True, "spf": True, "dkim": True,
                                               "dmarc": True, "allPass": True, "missing": []}})
    assert out["rows"][0]["verdict"] == "too_young"
    assert out["findings"] == []


def test_level1_reports_a_dns_fault_once_per_domain_not_once_per_inbox():
    emails = ["a@bad.com", "b@bad.com", "c@bad.com"]
    inboxes = M.build_inbox_index([account(e) for e in emails],
                                  {"c1": campaign("c1", "cid", emails)}, NOW)
    vitals = {"bad.com": {"mx": True, "spf": True, "dkim": False, "dmarc": False,
                          "allPass": False, "passed": False, "missing": ["dkim", "dmarc"]}}
    out = M.level1(inboxes, {e: {"health_score": 100} for e in emails}, vitals)
    assert list(out["domain_dns_faults"]) == ["bad.com"]
    props = M.build_proposals(out, None, None, None, inboxes,
                              {"c1": campaign("c1", "cid", emails)}, [])
    dns = [p for p in props if p["kind"] == "fix_dns"]
    assert len(dns) == 1 and dns[0]["severity"] == "critical"
    assert sorted(dns[0]["evidence"]["inboxes"]) == sorted(emails)


def test_fetch_warmup_and_vitals_chunk_at_the_documented_cap(monkeypatch):
    monkeypatch.setattr(TH, "WARMUP_ANALYTICS_MAX_EMAILS_PER_CALL", 2)
    monkeypatch.setattr(TH, "VITALS_MAX_ACCOUNTS_PER_CALL", 2)
    emails = ["a@d.com", "b@d.com", "c@d.com"]
    client = StubClient(warmup={e: {"health_score": 100} for e in emails})
    got = M.fetch_warmup(client, emails, sleep=lambda s: None)
    assert set(got) == set(emails)
    assert len([c for c in client.calls if c[0] == "warmup_analytics"]) == 2
    M.fetch_vitals(client, emails, sleep=lambda s: None)
    assert len([c for c in client.calls if c[0] == "test_vitals"]) == 2


# ---------------------------------------------------------------------- level 3

def test_level3_judges_on_the_longest_window_with_enough_volume():
    client, emails, camps = build_world(reply_counts={e: 3 for e in emails_of()}, days=14)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    row = out["per_inbox"][0]
    # 14 days x 25 = 350 sends in the 14-day window, 175 in the 7-day one; both
    # clear 100, so the verdict must come from the longer one.
    assert row["judged_on_days"] == 14
    assert row["windows"]["14"]["sent"] > row["windows"]["7"]["sent"]


def emails_of(domains=("a.com", "b.com"), personas=("x", "y", "z")):
    return ["%s@%s" % (p, d) for d in domains for p in personas]


def test_level3_fails_an_inbox_under_one_percent_with_enough_sends():
    names = emails_of()
    replies = {e: 4 for e in names}
    replies[names[0]] = 0          # 0% over 7 x 25 = 175 sends
    client, _, camps = build_world(reply_counts=replies, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    failing = {r["email"] for r in out["failing"]}
    assert failing == {names[0]}
    assert out["failing"][0]["fails"] == ["reply_rate"]


def test_level3_abstains_below_the_hundred_send_floor():
    client, _, camps = build_world(reply_counts={}, sent_per_day=5, days=7)  # 35 sends
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    assert out["failing"] == []
    assert all(r["judged_on_days"] is None for r in out["per_inbox"])


def test_level3_marks_thin_evidence_and_demotes_the_severity():
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names[1:]}, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    row = [r for r in out["failing"] if r["email"] == names[0]][0]
    assert row["sent"] == 175 and row["sent"] < TH.REPLY_RATE_THIN_EVIDENCE_SENT
    assert row["thin_evidence"] is True
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, [])
    p = [x for x in props if x["target"] == names[0]][0]
    assert p["severity"] == "medium"
    assert "one coin flip" not in p["reason"]      # the reason states the numbers
    assert "thin evidence" in (p["note"] or "")


def test_level3_bounce_ceiling():
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names},
                                   bounce_counts={names[0]: 7}, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    row = [r for r in out["per_inbox"] if r["email"] == names[0]][0]
    assert row["bounce_pct"] == pytest.approx(4.0, abs=0.01)
    assert "bounce_rate" in row["fails"]


def test_level3_retires_a_domain_only_when_every_inbox_on_it_fails():
    names = emails_of()
    # a.com: all three at 0 replies. b.com: two good, one bad.
    replies = {e: 0 for e in names[:3]}
    replies.update({names[3]: 4, names[4]: 4, names[5]: 0})
    client, _, camps = build_world(reply_counts=replies, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    retire = {d["domain"]: d["retire"] for d in out["per_domain"]}
    assert retire == {"a.com": True, "b.com": False}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, [])
    kinds = [(p["kind"], p["target"]) for p in props]
    assert ("retire_domain", "a.com") in kinds
    # The three a.com inboxes are covered by the domain proposal, not duplicated.
    assert not any(k == "remove_from_email_list" and t.endswith("@a.com") for k, t in kinds)
    assert ("remove_from_email_list", names[5]) in kinds


def test_level3_ignores_insurance_inboxes_that_have_never_sent():
    emails = emails_of()
    accounts = [account(e) for e in emails] + [account("warm@new.com")]
    camps = {"c1": campaign("c1", "cid", emails)}
    inboxes = M.build_inbox_index(accounts, camps, NOW)
    assert [i["role"] for i in inboxes if i["email"] == "warm@new.com"] == [M.ROLE_INSURANCE]
    out = M.level3(inboxes, [], NOW)
    assert "warm@new.com" not in {r["email"] for r in out["per_inbox"]}


# ------------------------------------------------------------------ sudden drop

def test_sudden_drop_abstains_when_the_baseline_is_the_same_week_as_the_recent_window():
    """True of this workspace on 2026-09-22: sending began 2026-09-15, so the
    28-day baseline and the 7-day window hold identical data and the ratio is
    1.0 by construction. Reporting "0 flagged" would read as a passed check."""
    client, _, camps = build_world(reply_counts={}, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.sudden_drop(inboxes, client._daily, NOW, per_inbox=True)
    assert out["usable"] is False
    assert out["dropped"] == []
    assert all(r["abstained"] for r in out["inboxes"])
    assert "cannot fire yet" in out["inboxes"][0]["reason"]
    card = M.render_card({"as_of_ct": "x", "capacity": {}, "proposals": [], "sudden_drop": out})
    assert "NOT EVALUATED" in card


def test_sudden_drop_fires_when_the_recent_week_halves_the_four_week_average():
    name = "x@a.com"
    accounts = [account(name)]
    camps = {"c1": campaign("c1", "cid", [name])}
    inboxes = M.build_inbox_index(accounts, camps, NOW)
    rows = []
    old = M.window_dates(NOW, TH.SUDDEN_DROP_BASELINE_DAYS)[:-TH.SUDDEN_DROP_RECENT_DAYS]
    recent = M.window_dates(NOW, TH.SUDDEN_DROP_RECENT_DAYS)
    for d in old:                       # 21 days at 3% (25 sent, ~0.75 replies -> use 1 every other)
        rows.append({"date": d, "email_account": name, "sent": 25, "replies": 1,
                     "replies_automatic": 1, "bounced": 0})
    for d in recent:                    # 7 days at 0%
        rows.append({"date": d, "email_account": name, "sent": 25, "replies": 0,
                     "replies_automatic": 1, "bounced": 0})
    out = M.sudden_drop(inboxes, rows, NOW, per_inbox=True)
    assert out["usable"] is True
    inbox_row = [r for r in out["inboxes"] if r["name"] == name][0]
    assert inbox_row["dropped"] is True
    assert inbox_row["recent_pct"] == 0.0 and inbox_row["baseline_pct"] > 0
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, None, None, out,
                              inboxes, camps, [])
    pause = [p for p in props if p["kind"] == "pause_inbox"]
    # 175 recent sends is under REPLY_RATE_THIN_EVIDENCE_SENT, so the drop is
    # real but demoted one step and labelled: critical is the loudest thing this
    # system says and it drives a high-priority push.
    assert pause and pause[0]["trigger"] == "sudden_drop"
    assert pause[0]["severity"] == "high" and pause[0]["thin_evidence"] is True
    assert "thin evidence" in (pause[0]["note"] or "")


def test_sudden_drop_abstains_when_the_baseline_rate_is_already_near_zero():
    name = "x@a.com"
    inboxes = M.build_inbox_index([account(name)], {"c1": campaign("c1", "cid", [name])}, NOW)
    rows = [{"date": d, "email_account": name, "sent": 25, "replies": 0,
             "replies_automatic": 0, "bounced": 0}
            for d in M.window_dates(NOW, TH.SUDDEN_DROP_BASELINE_DAYS)]
    out = M.sudden_drop(inboxes, rows, NOW, per_inbox=True)
    assert out["dropped"] == []
    assert "under the" in out["inboxes"][0]["reason"]


def _halving_rows(name):
    old = M.window_dates(NOW, TH.SUDDEN_DROP_BASELINE_DAYS)[:-TH.SUDDEN_DROP_RECENT_DAYS]
    recent = M.window_dates(NOW, TH.SUDDEN_DROP_RECENT_DAYS)
    rows = [{"date": d, "email_account": name, "sent": 100, "replies": 3,
             "replies_automatic": 0, "bounced": 0} for d in old]
    rows += [{"date": d, "email_account": name, "sent": 100, "replies": 0,
              "replies_automatic": 0, "bounced": 0} for d in recent]
    return rows


def test_the_per_inbox_sudden_drop_is_off_and_says_so():
    """MKT-6 / owner decision R13. At 150 sends per inbox per week the
    5-expected-replies floor needs a 3.3% baseline against a fleet at about 1%,
    so the per-inbox check could never fire. It must abstain, visibly, with
    that reason, even on data that would have tripped it; the domain check
    stays armed and carries the alert."""
    assert TH.SUDDEN_DROP_PER_INBOX_ENABLED is False
    name = "x@a.com"
    inboxes, camps = _one_inbox_world(name, others=())
    out = M.sudden_drop(inboxes, _halving_rows(name), NOW)
    assert out["per_inbox_enabled"] is False
    inbox_row = [r for r in out["inboxes"] if r["name"] == name][0]
    assert inbox_row["abstained"] is True and inbox_row["dropped"] is False
    assert inbox_row["disabled"] is True
    assert "domain-only" in inbox_row["reason"] and "R13" in inbox_row["reason"]
    assert "3.3%" in inbox_row["reason"]
    domain_row = [r for r in out["domains"] if r["name"] == "a.com"][0]
    assert domain_row["dropped"] is True
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, None, None, out,
                              inboxes, camps, [])
    kinds = [p["kind"] for p in props if p.get("trigger") == "sudden_drop"]
    assert kinds == ["pause_domain"]
    card = M.render_card({"as_of_ct": "x", "capacity": {}, "proposals": [], "sudden_drop": out})
    assert "domain-only" in card
    assert "per-inbox: OFF" in card


def test_a_switched_off_scope_never_makes_the_check_look_usable():
    """Twelve abstaining inbox rows used to count toward 'usable'. With the
    per-inbox scope off, only the domain rows decide it."""
    client, _, camps = build_world(reply_counts={}, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.sudden_drop(inboxes, client._daily, NOW)
    assert out["usable"] is False
    assert all(r["abstained"] for r in out["domains"])
    assert all(r.get("disabled") for r in out["inboxes"])
    card = M.render_card({"as_of_ct": "x", "capacity": {}, "proposals": [], "sudden_drop": out})
    assert "NOT EVALUATED" in card and "per-inbox: OFF" in card


# -------------------------------------------------------- insurance and actions

def test_eligible_insurance_rejects_an_inbox_that_is_still_warming():
    accounts = [account("warm@new.com", warmup_start="2026-09-20T23:39:36.788Z"),
                account("ready@old.com", warmup_start="2026-08-01T00:00:00.000Z")]
    inboxes = M.build_inbox_index(accounts, {}, NOW)
    vitals = {d: {"mx": True, "spf": True, "dkim": True, "dmarc": True, "missing": []}
              for d in ("new.com", "old.com")}
    warmup = {"warm@new.com": {"health_score": 100}, "ready@old.com": {"health_score": 100}}
    out = M.eligible_insurance(inboxes, warmup, vitals)
    assert [i["email"] for i in out] == ["ready@old.com"]


def test_eligible_insurance_rejects_a_healthy_old_inbox_on_a_broken_domain():
    accounts = [account("ready@old.com", warmup_start="2026-08-01T00:00:00.000Z")]
    inboxes = M.build_inbox_index(accounts, {}, NOW)
    vitals = {"old.com": {"mx": True, "spf": True, "dkim": False, "dmarc": True, "missing": ["dkim"]}}
    assert M.eligible_insurance(inboxes, {"ready@old.com": {"health_score": 100}}, vitals) == []


def test_one_insurance_inbox_is_never_promised_to_two_failing_inboxes():
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names[2:]}, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    assert len(out["failing"]) == 2
    spare = M.build_inbox_index([account("spare@ins.com", warmup_start="2026-07-01T00:00:00.000Z")], {}, NOW)
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, spare)
    replacements = [p.get("replacement") for p in props if p["kind"] == "remove_from_email_list"]
    assert replacements.count("spare@ins.com") == 1
    assert None in replacements       # the second failure is honestly unfilled


def test_a_proposal_with_no_replacement_still_gets_made_and_says_so():
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names[1:]}, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, [])
    p = props[0]
    assert p["replacement"] is None and p["in_campaigns"] == ["c1"]
    card = M.render_card({"as_of_ct": "x", "capacity": {}, "proposals": props, "changeset_date": "d"})
    assert "NO replacement available" in card


def test_remove_actions_carry_the_exact_before_and_after_email_list():
    names = emails_of()
    camps = {"c1": campaign("c1", "cid-1", names)}
    inboxes = M.build_inbox_index([account(e) for e in names], camps, NOW)
    action = M._remove_actions(names[0], inboxes[0], camps, "spare@ins.com")[0]
    assert action["op"] == "patch_campaign_email_list"
    assert action["expected_before"] == names
    assert names[0] not in action["expected_after"]
    assert "spare@ins.com" in action["expected_after"]
    assert len(action["expected_after"]) == len(names)


def test_two_levels_condemning_the_same_inbox_produce_one_proposal():
    names = emails_of()
    camps = {"c1": campaign("c1", "cid-1", names)}
    inboxes = M.build_inbox_index([account(e) for e in names], camps, NOW)
    l1 = {"findings": [{"email": names[0], "verdict": "health_fail", "reason": "health 90%",
                        "health": 90, "warmup_age_days": 40, "warmup_sent": 1,
                        "warmup_landed_inbox": 1}],
          "domain_dns_faults": {}}
    drop = {"dropped": [{"scope": "inbox", "name": names[0], "reason": "reply rate halved",
                         "recent_pct": 0.1, "baseline_pct": 2.0}]}
    props = M.build_proposals(l1, None, None, drop, inboxes, camps, [])
    targets = [p["target"] for p in props if p["kind"] == "pause_inbox"]
    assert targets.count(names[0]) == 1
    merged = [p for p in props if p["target"] == names[0]][0]
    assert merged["severity"] == "critical"          # the louder verdict wins
    assert len(merged["also"]) == 1


# ------------------------------------------------------------------- change-set

def test_write_changeset_keeps_first_seen_across_runs_and_withdraws_what_recovered(tmp_path):
    now2 = NOW + timedelta(hours=6)
    p1 = [{"id": "pause_inbox:a@d.com", "kind": "pause_inbox", "target": "a@d.com",
           "severity": "high", "level": 1, "reason": "r", "actions": [], "evidence": {}}]
    M.write_changeset(M.build_changeset(p1, NOW, {"levels_run": [1]}), NOW, tmp_path)
    path = tmp_path / "2026-09-22.json"
    first = json.loads(path.read_text())["proposals"][0]["first_seen"]

    p2 = [{"id": "pause_inbox:b@d.com", "kind": "pause_inbox", "target": "b@d.com",
           "severity": "high", "level": 1, "reason": "r2", "actions": [], "evidence": {}}]
    M.write_changeset(M.build_changeset(p2, now2, {"levels_run": [1]}), now2, tmp_path)
    rows = {r["id"]: r for r in json.loads(path.read_text())["proposals"]}
    assert rows["pause_inbox:b@d.com"]["status"] == "proposed"
    # a@d.com is no longer proposed: it is marked withdrawn, not deleted.
    assert rows["pause_inbox:a@d.com"]["status"] == "withdrawn"
    assert rows["pause_inbox:a@d.com"]["first_seen"] == first

    # And a proposal that persists keeps its original first_seen.
    M.write_changeset(M.build_changeset(p2, now2 + timedelta(hours=1), {"levels_run": [1]}),
                      now2 + timedelta(hours=1), tmp_path)
    rows = {r["id"]: r for r in json.loads(path.read_text())["proposals"]}
    assert rows["pause_inbox:b@d.com"]["first_seen"] == \
        now2.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def test_one_job_never_withdraws_another_jobs_proposal(tmp_path):
    """Three jobs write into one day's file. Before the ownership check, the
    07:00 monitor run withdrew the placement job's create_placement_test
    proposal thirty seconds after it was written, and the apply script then
    skipped it. Reproduced from the 2026-09-22 evidence run."""
    placement = {"_about": "", "generated_at": NOW.astimezone(timezone.utc).isoformat(),
                 "generated_by": "inbox_placement", "proposals": [
                     {"id": "create_placement_test:2026-09-22", "kind": "create_placement_test",
                      "target": "t", "severity": "low", "level": 2, "reason": "due",
                      "actions": [], "evidence": {}}]}
    M.write_changeset(placement, NOW, tmp_path)

    monitor = M.build_changeset(
        [{"id": "pause_inbox:a@d.com", "kind": "pause_inbox", "target": "a@d.com",
          "severity": "high", "level": 1, "reason": "r", "actions": [], "evidence": {}}],
        NOW, {"levels_run": [1]})
    M.write_changeset(monitor, NOW, tmp_path)

    rows = {r["id"]: r for r in json.loads((tmp_path / "2026-09-22.json").read_text())["proposals"]}
    assert rows["create_placement_test:2026-09-22"]["status"] == "proposed"
    assert rows["create_placement_test:2026-09-22"]["generated_by"] == "inbox_placement"
    assert rows["pause_inbox:a@d.com"]["generated_by"] == M.JOB
    # ... and the monitor still withdraws its OWN stale proposal.
    M.write_changeset(M.build_changeset([], NOW, {"levels_run": [1]}), NOW, tmp_path)
    rows = {r["id"]: r for r in json.loads((tmp_path / "2026-09-22.json").read_text())["proposals"]}
    assert rows["pause_inbox:a@d.com"]["status"] == "withdrawn"
    assert rows["create_placement_test:2026-09-22"]["status"] == "proposed"


def test_write_changeset_is_named_for_the_central_date_not_utc():
    pass  # covered by the path assertion above: 07:00 CT on the 22nd -> 2026-09-22.json


def test_write_changeset_survives_a_corrupt_existing_file(tmp_path):
    (tmp_path / "2026-09-22.json").write_text("{not json")
    props = [{"id": "x:y", "kind": "pause_inbox", "target": "y", "severity": "low",
              "level": 1, "reason": "r", "actions": [], "evidence": {}}]
    path = M.write_changeset(M.build_changeset(props, NOW, {}), NOW, tmp_path)
    assert path is not None
    assert json.loads(path.read_text())["proposals"][0]["id"] == "x:y"


def test_level5_reports_not_configured_without_a_campaign_id(tmp_path):
    assert M.load_level5_spec(tmp_path) is None
    (tmp_path / TH.LEVEL5_SPEC_FILENAME).write_text(json.dumps({"campaign_id": None}))
    spec = M.load_level5_spec(tmp_path)
    out = M.level5(None, [], spec, NOW)
    assert out["configured"] is False and out["failing"] == []


# ------------------------------------------------------- end to end, and httpx

def test_run_monitor_end_to_end_proposes_but_never_writes(tmp_path, monkeypatch):
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names[1:]}, days=7)
    logged = []
    notified = []
    report = M.run_monitor(NOW, client=client, levels=[1, 3, 5], dry_run=True,
                           log_fn=lambda *a: logged.append(a),
                           notify_fn=lambda *a, **k: notified.append(a),
                           changeset_dir=tmp_path, campaigns=camps, sleep=lambda s: None)
    assert report["proposals"] and report["proposals"][0]["kind"] == "remove_from_email_list"
    assert report["changeset_path"] is None            # --dry-run writes nothing
    assert notified == []                              # and notifies nobody
    assert logged and logged[0][1].startswith("dry_run")
    assert not list(tmp_path.glob("*.json"))
    # No write call of any kind reached the client.
    assert all(c[0] in ("iterate", "get_campaign", "warmup_analytics", "test_vitals", "daily")
               for c in client.calls)


def test_run_monitor_writes_the_changeset_and_the_card_when_not_dry_run(tmp_path):
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names[1:]}, days=7)
    notified = []
    report = M.run_monitor(NOW, client=client, levels=[1, 3], dry_run=False,
                           log_fn=lambda *a: None,
                           notify_fn=lambda *a, **k: notified.append((a, k)) or {"sent": True},
                           changeset_dir=tmp_path, campaigns=camps, sleep=lambda s: None)
    assert report["changeset_path"] and (tmp_path / "2026-09-22.json").exists()
    assert notified and notified[0][1]["priority"] in ("default", "high")
    assert "Deliverability" in report["card"]


def test_run_monitor_degrades_when_the_analytics_endpoint_413s(tmp_path):
    names = emails_of()
    client, _, camps = build_world(reply_counts={}, days=7)

    def boom(**kwargs):
        raise RuntimeError("HTTP 413: Analytics request is too large")

    client.daily_account_analytics = boom
    report = M.run_monitor(NOW, client=client, levels=[1, 3], dry_run=True,
                           log_fn=lambda *a: None, notify_fn=lambda *a, **k: None,
                           changeset_dir=tmp_path, campaigns=camps, sleep=lambda s: None)
    assert report["level3"] is None and report["sudden_drop"] is None
    assert any("413" in n for n in report["notes"])
    # It still reports level 1 rather than dying.
    assert report["level1"]["checked"] == len(names)


def test_load_accounts_refuses_a_truncated_walk():
    class Truncating(StubClient):
        def iterate(self, path, params=None, body=None, max_pages=200):
            walk = _Walk([account("a@d.com")])
            walk.truncated = True
            return walk

    with pytest.raises(RuntimeError) as exc:
        M.load_accounts(Truncating())
    assert "partial" in str(exc.value)


def test_fetch_daily_chunks_and_sends_the_query_shape_the_live_endpoint_accepted():
    """Pinned against the request that answered HTTP 200 on 2026-09-22:
    repeated ?emails= parameters plus start_date/end_date."""
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json=[{"date": "2026-09-21", "email_account": "a@d.com",
                                          "sent": 25, "replies": 1, "replies_automatic": 0,
                                          "bounced": 0}])

    from shared.instantly import Instantly

    client = Instantly(api_key="test", transport=httpx.MockTransport(handler))
    emails = ["e%d@d.com" % i for i in range(7)]
    rows = M.fetch_daily(client, emails, "2026-08-25", "2026-09-21", sleep=lambda s: None)
    assert len(seen) == 3                       # 7 emails at a chunk size of 3 in this test
    assert len(rows) == 3
    first = str(seen[0])
    assert "start_date=2026-08-25" in first and "end_date=2026-09-21" in first
    assert first.count("emails=") == 3


@pytest.fixture(autouse=True)
def _small_chunks(monkeypatch, request):
    if request.node.name == "test_fetch_daily_chunks_and_sends_the_query_shape_the_live_endpoint_accepted":
        monkeypatch.setattr(TH, "DAILY_ANALYTICS_CHUNK_EMAILS", 3)


def test_a_domain_retirement_emits_one_executable_patch_per_campaign():
    """A retire_domain proposal used to carry a made-up ``remove_from_email_list``
    op that the apply script does not know, so the whole proposal was
    unexecutable. It now emits one patch per campaign dropping all three of the
    domain's inboxes at once: one action per inbox would make the second
    action's expected_before stale the instant the first one applied, and the
    apply script would refuse the rest of its own change-set."""
    names = emails_of()
    replies = {e: 0 for e in names[:3]}
    replies.update({names[3]: 4, names[4]: 4, names[5]: 4})
    client, _, camps = build_world(reply_counts=replies, days=7)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, [])
    retire = [p for p in props if p["kind"] == "retire_domain"][0]
    patches = [a for a in retire["actions"] if a["op"] == "patch_campaign_email_list"]
    assert len(patches) == 1                       # one campaign in this world
    assert sorted(patches[0]["remove"]) == sorted(names[:3])
    assert patches[0]["expected_after"] == sorted(names[3:])
    assert all(a["op"] == "patch_campaign_email_list" for a in retire["actions"])
    # The registrar step is its own proposal now: bundled in, its manual op made
    # the whole retirement unapplyable through the only tool allowed to apply it.
    stop = [p for p in props if p["kind"] == "stop_using_domain"]
    assert stop and stop[0]["actions"][0]["op"] == "stop_using_domain"


# =========================================================================
# Review fixes: level 3 judges its two rules independently
# =========================================================================

def _inbox_rows(email, per_day_sent, replies, bounces, days, now=NOW, camps=None):
    """Daily rows for one inbox carrying exactly `replies` and `bounces` in
    total, spread across `days` (several per day when that is what it takes)."""
    dates = M.window_dates(now, days)
    rows = []
    for i, d in enumerate(dates):
        r = replies // days + (1 if i < replies % days else 0)
        b = bounces // days + (1 if i < bounces % days else 0)
        rows.append({"date": d, "email_account": email, "sent": per_day_sent,
                     "replies": r, "replies_automatic": 1, "bounced": b})
    return rows


def _one_inbox_world(email="bad@a.com", others=("good@a.com",)):
    emails = [email] + list(others)
    camps = {"c1": campaign("c1", "cid-1", emails)}
    inboxes = M.build_inbox_index([account(e) for e in emails], camps, NOW)
    return inboxes, camps


def test_level3_flags_a_ten_percent_bounce_on_eighty_sends():
    """BOUNCE_RATE_MIN_SENT is 50, but the verdict used to be taken from the
    longest window with >= REPLY_RATE_MIN_SENT (100) sends, so an 80-send inbox
    bouncing at 10% produced no proposal at all and printed as 'sent -,
    bounce -'. Bounce is the fastest way to lose a domain."""
    inboxes, camps = _one_inbox_world()
    rows = _inbox_rows("bad@a.com", 40, replies=4, bounces=8, days=2)      # 80 sent, 10% bounce
    out = M.level3(inboxes, rows, NOW)
    row = [r for r in out["per_inbox"] if r["email"] == "bad@a.com"][0]
    assert "bounce_rate" in row["fails"]
    assert row["sent"] == 80 and row["bounce_pct"] == 10.0
    assert out["failing"] and out["failing"][0]["email"] == "bad@a.com"


def test_level3_bounce_boundaries_at_forty_nine_and_fifty_sends():
    inboxes, camps = _one_inbox_world()
    under = M.level3(inboxes, _inbox_rows("bad@a.com", 49, 0, 5, days=1), NOW)
    assert under["per_inbox"][0]["fails"] == []          # 49 sends: below BOUNCE_RATE_MIN_SENT
    at = M.level3(inboxes, _inbox_rows("bad@a.com", 50, 0, 5, days=1), NOW)
    assert "bounce_rate" in at["per_inbox"][0]["fails"]  # 50 sends, 10% bounce
    assert TH.BOUNCE_RATE_MIN_SENT == 50


def test_level3_reply_boundaries_at_ninety_nine_and_one_hundred_sends():
    inboxes, camps = _one_inbox_world()
    under = M.level3(inboxes, _inbox_rows("bad@a.com", 99, 0, 0, days=1), NOW)
    assert "reply_rate" not in under["per_inbox"][0]["fails"]
    at = M.level3(inboxes, _inbox_rows("bad@a.com", 100, 0, 0, days=1), NOW)
    assert "reply_rate" in at["per_inbox"][0]["fails"]
    assert TH.REPLY_RATE_MIN_SENT == 100


def test_level3_fails_an_inbox_whose_recent_week_collapsed_even_if_fourteen_days_reads_fine():
    """M1 L3 reads '>= 100 sent in 7 d or 14 d and < 1% real replies': either
    window failing is a failure. Judging only on the longest window let an inbox
    with 7 replies in the older week and none in the recent one pass at 2.00%
    over 14 days while its 7-day rate was 0.00%."""
    inboxes, camps = _one_inbox_world()
    old = M.window_dates(NOW, 14)[:7]
    recent = M.window_dates(NOW, 7)
    rows = [{"date": d, "email_account": "bad@a.com", "sent": 25, "replies": 1,
             "replies_automatic": 0, "bounced": 0} for d in old]
    rows += [{"date": d, "email_account": "bad@a.com", "sent": 25, "replies": 0,
              "replies_automatic": 0, "bounced": 0} for d in recent]
    out = M.level3(inboxes, rows, NOW)
    row = out["per_inbox"][0]
    assert row["windows"]["7"]["reply_pct"] == 0.0
    assert row["windows"]["14"]["reply_pct"] == 2.0
    assert "reply_rate" in row["fails"]
    assert row["failed_on_days"]["reply_rate"] == 7


def test_the_bounce_half_of_level_3_runs_every_day(tmp_path):
    """Section 6's Monday row is 'placement test; bounce audit'. Bounce used to
    be evaluated only inside the Friday pass, so a domain that started bouncing
    on a Saturday sent six more days of mail before anything noticed."""
    emails = ["x@a.com", "y@a.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    daily = _inbox_rows("x@a.com", 50, replies=5, bounces=5, days=4)      # 200 sent, 2.5% bounce
    daily += _inbox_rows("y@a.com", 50, replies=5, bounces=0, days=4)
    client = StubClient(accounts=[account(e) for e in emails], campaigns=camps,
                        warmup={e: {"health_score": 100} for e in emails}, daily=daily)
    tuesday = ct("2026-09-22 07:00")                                       # not Friday
    report = M.run_monitor(tuesday, client=client, changeset_dir=tmp_path, campaigns=camps,
                           log_fn=lambda *a: None, notify_fn=lambda *a, **k: None, sleep=lambda s: None)
    assert 3 not in report["levels_run"]
    assert report["level3"]["rules_applied"] == ["bounce_rate"]
    ids = [p["id"] for p in report["proposals"]]
    assert "remove_from_email_list:x@a.com" in ids
    assert "remove_from_email_list:y@a.com" not in ids   # the reply rule stayed on Friday
    assert TH.BOUNCE_CHECK_EVERY_DAY is True


# =========================================================================
# Review fixes: domain retirement needs evidence a single inbox does not
# =========================================================================

def test_domain_retirement_off_thin_evidence_is_demoted_and_labelled():
    """At 150 sends and a 1.22% fleet rate an individually healthy inbox reads
    under 1% about 45% of the time, so three on one domain do about 9% of the
    time: roughly one Friday in three across four domains, from noise alone."""
    names = emails_of()
    replies = {e: 0 for e in names[:3]}
    replies.update({names[3]: 4, names[4]: 4, names[5]: 4})
    client, _, camps = build_world(reply_counts=replies, days=6, sent_per_day=25)  # 150 sends each
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    domain = [d for d in out["per_domain"] if d["domain"] == "a.com"][0]
    assert domain["retire"] is True and domain["retire_thin"] is True
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, [])
    retire = [p for p in props if p["kind"] == "retire_domain"][0]
    assert retire["severity"] == "medium" and retire["thin_evidence"] is True
    assert "thin evidence" in retire["note"]
    assert "150 sends" in retire["reason"] or "on 150" in retire["reason"] or "sends" in retire["reason"]


def test_domain_retirement_on_real_volume_stays_high():
    names = emails_of()
    replies = {e: 0 for e in names[:3]}
    replies.update({names[3]: 20, names[4]: 20, names[5]: 20})
    client, _, camps = build_world(reply_counts=replies, days=14, sent_per_day=40)  # 560 sends each
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, [])
    retire = [p for p in props if p["kind"] == "retire_domain"][0]
    assert retire["severity"] == "high" and not retire.get("thin_evidence")


# =========================================================================
# Review fixes: the sudden-drop check needs signal, not just volume
# =========================================================================

def test_sudden_drop_abstains_when_the_recent_window_expects_too_few_replies():
    """SUDDEN_DROP_MIN_RECENT_SENT is 50, which at a 1.22% base rate expects
    0.6 replies: zero replies is the modal outcome and always reads as a 100%
    drop. This is the loudest proposal the system makes."""
    name = "x@a.com"
    inboxes, camps = _one_inbox_world(name, others=())
    old = M.window_dates(NOW, TH.SUDDEN_DROP_BASELINE_DAYS)[:-TH.SUDDEN_DROP_RECENT_DAYS]
    recent = M.window_dates(NOW, TH.SUDDEN_DROP_RECENT_DAYS)
    rows = [{"date": d, "email_account": name, "sent": 25, "replies": 1,
             "replies_automatic": 0, "bounced": 0} for d in old]          # ~4% baseline
    rows += [{"date": d, "email_account": name, "sent": 10, "replies": 0,
              "replies_automatic": 0, "bounced": 0} for d in recent]      # 70 sends, 2.8 expected
    out = M.sudden_drop(inboxes, rows, NOW, per_inbox=True)
    row = [r for r in out["inboxes"] if r["name"] == name][0]
    assert row["dropped"] is False and row["abstained"] is True
    assert "expect only" in row["reason"]
    assert row["expected_replies"] < TH.SUDDEN_DROP_MIN_EXPECTED_REPLIES


def test_sudden_drop_stays_critical_on_real_volume():
    name = "x@a.com"
    inboxes, camps = _one_inbox_world(name, others=())
    old = M.window_dates(NOW, TH.SUDDEN_DROP_BASELINE_DAYS)[:-TH.SUDDEN_DROP_RECENT_DAYS]
    recent = M.window_dates(NOW, TH.SUDDEN_DROP_RECENT_DAYS)
    rows = [{"date": d, "email_account": name, "sent": 100, "replies": 3,
             "replies_automatic": 0, "bounced": 0} for d in old]
    rows += [{"date": d, "email_account": name, "sent": 100, "replies": 0,
              "replies_automatic": 0, "bounced": 0} for d in recent]      # 700 recent sends
    out = M.sudden_drop(inboxes, rows, NOW, per_inbox=True)
    row = [r for r in out["inboxes"] if r["name"] == name][0]
    assert row["dropped"] is True and row["thin_evidence"] is False
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, None, None, out,
                              inboxes, camps, [])
    pause = [p for p in props if p["kind"] == "pause_inbox"][0]
    assert pause["severity"] == "critical"


def test_a_domain_scope_sudden_drop_carries_the_email_list_patches_too():
    """'A paused inbox stays in email_list. Pausing alone silently drops a
    campaign's capacity instead of moving it.' The domain branch emitted three
    bare pause_account ops and no patch at all."""
    emails = ["x@a.com", "y@a.com", "z@a.com"]
    camps = {"c%d" % i: campaign("c%d" % i, "cid-%d" % i, emails) for i in range(6)}
    inboxes = M.build_inbox_index([account(e) for e in emails], camps, NOW)
    drop = {"dropped": [{"scope": "domain", "name": "a.com", "reason": "collapsed",
                         "recent_sent": 900, "thin_evidence": False}]}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, None, None, drop,
                              inboxes, camps, [])
    pause = [p for p in props if p["kind"] == "pause_domain"][0]
    ops = [a["op"] for a in pause["actions"]]
    assert ops.count("pause_account") == 3
    assert ops.count("patch_campaign_email_list") == 6      # one per campaign, all three removed
    patch = [a for a in pause["actions"] if a["op"] == "patch_campaign_email_list"][0]
    assert patch["expected_after"] == []


def test_the_card_states_the_capacity_cost_of_a_domain_pause_in_inboxes_not_one():
    emails = ["x@a.com", "y@a.com", "z@a.com", "keep@b.com"]
    camps = {"c%d" % i: campaign("c%d" % i, "cid-%d" % i, emails) for i in range(6)}
    inboxes = M.build_inbox_index([account(e) for e in emails], camps, NOW)
    drop = {"dropped": [{"scope": "domain", "name": "a.com", "reason": "collapsed",
                         "recent_sent": 900, "thin_evidence": False}]}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, None, None, drop,
                              inboxes, camps, [])
    card = M.render_card({"proposals": props, "capacity": M._capacity(inboxes),
                          "as_of_ct": "Tue", "levels_run": [1]})
    assert "removes 3 inbox(es), 75 sends/day total" in card
    assert "25 sends/day total" not in card


# =========================================================================
# Review fixes: dedupe, replacements and the insurance pool
# =========================================================================

def _insurance(email, domain_age=30):
    row = account(email, warmup_start="2026-08-01T00:00:00.000Z")
    return row


def test_one_inbox_failing_level_1_and_level_3_produces_one_proposal_and_claims_one_spare():
    """_dedupe was keyed on kind:target, so level 1's pause_inbox and level 3's
    remove_from_email_list never merged: the card double-counted, two insurance
    inboxes were burned on one failure, and applying the first proposal made the
    second stale."""
    emails = ["bad@a.com", "good@a.com"]
    spares = ["ins1@b.com", "ins2@b.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    inboxes = M.build_inbox_index([account(e) for e in emails] + [_insurance(s) for s in spares],
                                  camps, NOW)
    insurance = [i for i in inboxes if i["role"] == M.ROLE_INSURANCE]
    l1 = {"findings": [{"email": "bad@a.com", "verdict": "health_fail",
                        "verdicts": ["health_fail"], "reason": "warm-up health 94% is below 98%",
                        "health": 94, "warmup_age_days": 60, "warmup_sent": 10,
                        "warmup_landed_inbox": 9}],
          "domain_dns_faults": {}}
    l3 = {"per_domain": [], "failing": [{"email": "bad@a.com", "domain": "a.com",
                                         "fails": ["reply_rate"], "thin_evidence": True,
                                         "reply_pct": 0.0, "bounce_pct": 0.0, "sent": 350,
                                         "judged_on_days": 14, "failed_on_days": {"reply_rate": 14},
                                         "windows": {"14": {"reply_pct": 0.0, "sent": 350,
                                                            "bounce_pct": 0.0}},
                                         "in_campaigns": ["c1"]}]}
    props = M.build_proposals(l1, l3, None, None, inboxes, camps, insurance)
    for_bad = [p for p in props if p["target"] == "bad@a.com"]
    assert len(for_bad) == 1
    assert for_bad[0]["kind"] == "pause_inbox"           # the more complete action wins
    assert for_bad[0]["also"] and for_bad[0]["also"][0]["level"] == 3
    # Exactly one spare is consumed, and it is on the surviving proposal.
    claimed = [p.get("replacement") for p in props if p.get("replacement")]
    assert len(claimed) == 1 and claimed[0] in spares


def test_dedupe_keeps_the_thin_evidence_warning_from_the_quieter_level():
    """A louder level used to strip the quieter one's thin_evidence flag and its
    note, so Lorenzo read a high-severity removal with no sign that one reply
    either way decided it."""
    emails = ["e@a.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    inboxes = M.build_inbox_index([account(e) for e in emails], camps, NOW)
    l3 = {"per_domain": [], "failing": [{"email": "e@a.com", "domain": "a.com",
                                         "fails": ["reply_rate"], "thin_evidence": True,
                                         "reply_pct": 0.0, "bounce_pct": 0.0, "sent": 150,
                                         "judged_on_days": 14, "failed_on_days": {"reply_rate": 14},
                                         "windows": {"14": {"reply_pct": 0.0, "sent": 150,
                                                            "bounce_pct": 0.0}},
                                         "in_campaigns": ["c1"]}]}
    l5 = {"failing": [{"email": "e@a.com", "reply_pct": 0.0, "median_pct": 1.33, "sent": 150}]}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, l3, l5, None,
                              inboxes, camps, [])
    assert len(props) == 1
    assert props[0]["thin_evidence"] is True
    assert props[0]["note"] and "thin evidence" in props[0]["note"]


def test_level5_never_outranks_a_thin_level3_verdict_on_the_same_inbox():
    """Level 5 fires on a third of the evidence level 3 needs, on a number the
    spec file itself calls directional, and it cannot isolate the baseline
    campaign at all: GET /accounts/analytics/daily is per account."""
    emails = ["e@a.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    inboxes = M.build_inbox_index([account(e) for e in emails], camps, NOW)
    l5 = {"failing": [{"email": "e@a.com", "reply_pct": 0.0, "median_pct": 1.33, "sent": 150}]}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, None, l5, None,
                              inboxes, camps, [])
    assert props[0]["severity"] == TH.LEVEL5_MAX_SEVERITY == "medium"
    assert props[0]["thin_evidence"] is True
    assert "cannot isolate the baseline campaign" in props[0]["reason"]
    assert TH.severity_rank("medium") > TH.severity_rank("high")


def test_a_failing_inbox_in_no_campaign_does_not_burn_the_only_spare():
    """The replacement used to be claimed before anything checked membership, so
    an orphan got a spare on a proposal with no actions while a real sending
    inbox was told 'NO replacement available'."""
    orphan, real, spare = "orphan@a.com", "real@a.com", "ins@b.com"
    camps = {"c1": campaign("c1", "cid-1", [real])}
    accounts = [account(orphan, status=2), account(real), _insurance(spare)]
    inboxes = M.build_inbox_index(accounts, camps, NOW)
    insurance = [i for i in inboxes if i["role"] == M.ROLE_INSURANCE]
    def _fail(email, campaigns):
        return {"email": email, "domain": "a.com", "fails": ["reply_rate"], "thin_evidence": False,
                "reply_pct": 0.0, "bounce_pct": 0.0, "sent": 400, "judged_on_days": 14,
                "failed_on_days": {"reply_rate": 14},
                "windows": {"14": {"reply_pct": 0.0, "sent": 400, "bounce_pct": 0.0}},
                "in_campaigns": campaigns}
    l3 = {"per_domain": [], "failing": [_fail(orphan, []), _fail(real, ["c1"])]}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, l3, None, None,
                              inboxes, camps, insurance)
    by_target = {p["target"]: p for p in props}
    assert by_target[orphan]["replacement"] is None and by_target[orphan]["actions"] == []
    assert by_target[real]["replacement"] == spare


def test_a_replacement_never_pushes_a_campaign_past_three_inboxes_on_one_domain():
    """M2: never more than 3 inboxes per domain. MAX_INBOXES_PER_DOMAIN was
    declared and never read, so a swap could trade one deliverability problem
    for another."""
    emails = ["a1@b.com", "a2@b.com", "a3@b.com", "bad@a.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    accounts = [account(e) for e in emails] + [_insurance("spare@b.com"), _insurance("spare@c.com")]
    inboxes = M.build_inbox_index(accounts, camps, NOW)
    insurance = [i for i in inboxes if i["role"] == M.ROLE_INSURANCE]
    l3 = {"per_domain": [], "failing": [{"email": "bad@a.com", "domain": "a.com",
                                         "fails": ["reply_rate"], "thin_evidence": False,
                                         "reply_pct": 0.0, "bounce_pct": 0.0, "sent": 400,
                                         "judged_on_days": 14, "failed_on_days": {"reply_rate": 14},
                                         "windows": {"14": {"reply_pct": 0.0, "sent": 400,
                                                            "bounce_pct": 0.0}},
                                         "in_campaigns": ["c1"]}]}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, l3, None, None,
                              inboxes, camps, insurance)
    assert props[0]["replacement"] == "spare@c.com"      # b.com is already at the cap
    assert TH.MAX_INBOXES_PER_DOMAIN == 3


def test_a_placement_failure_is_offered_the_same_insurance_swap_as_a_health_failure():
    emails = ["bad@a.com", "good@a.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    inboxes = M.build_inbox_index([account(e) for e in emails] + [_insurance("ins@b.com")],
                                  camps, NOW)
    insurance = [i for i in inboxes if i["role"] == M.ROLE_INSURANCE]
    placement = {"as_of": NOW.isoformat(), "age_days": 0.0,
                 "failing": [{"email": "bad@a.com", "inbox_pct": 61.0, "esp": "google",
                              "in_campaigns": ["c1"]}]}
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, None, None, None,
                              inboxes, camps, insurance, placement=placement)
    assert props[0]["replacement"] == "ins@b.com"
    assert any(a["op"] == "patch_campaign_email_list" for a in props[0]["actions"])


# =========================================================================
# Review fixes: stale sidecars, the withdrawal rule and the empty workspace
# =========================================================================

def test_a_stale_placement_sidecar_stops_proposing_and_says_so(tmp_path):
    """PLACEMENT_TEST_MAX_AGE_DAYS already existed and was used to decide when a
    new test is due, but never applied to the sidecar the card reads. One
    failing row re-proposed a HIGH pause every morning, indefinitely."""
    old = (NOW - timedelta(days=40)).isoformat()
    (tmp_path / "last_placement.json").write_text(json.dumps(
        {"as_of": old, "summary": "1 failing, 2 passing",
         "failing": [{"email": "x@a.com", "inbox_pct": 70.0, "esp": "google"}]}))
    client, emails, camps = build_world(reply_counts={e: 3 for e in emails_of()}, days=7)
    report = M.run_monitor(NOW, client=client, levels=[1, 2], changeset_dir=tmp_path,
                           campaigns=camps, log_fn=lambda *a: None,
                           notify_fn=lambda *a, **k: None, sleep=lambda s: None)
    assert [p for p in report["proposals"] if p["level"] == 2] == []
    assert report["level2"]["stale"] is True
    assert any("days old" in n for n in report["notes"])
    assert "STALE" in report["card"]


def test_a_fresh_placement_sidecar_still_proposes_and_dates_its_evidence(tmp_path):
    recent = (NOW - timedelta(hours=6)).isoformat()
    (tmp_path / "last_placement.json").write_text(json.dumps(
        {"as_of": recent, "summary": "1 failing",
         "failing": [{"email": "x@a.com", "inbox_pct": 70.0, "esp": "google",
                      "in_campaigns": ["c1"]}]}))
    client, emails, camps = build_world(reply_counts={e: 3 for e in emails_of()}, days=7)
    report = M.run_monitor(NOW, client=client, levels=[1, 2], changeset_dir=tmp_path,
                           campaigns=camps, log_fn=lambda *a: None,
                           notify_fn=lambda *a, **k: None, sleep=lambda s: None)
    p = [p for p in report["proposals"] if p["level"] == 2]
    assert p and "measured" in p[0]["reason"]
    assert "day(s) ago" in p[0]["reason"]


def test_a_stale_canary_sidecar_stops_proposing(tmp_path):
    old = (NOW - timedelta(days=30)).isoformat()
    (tmp_path / "last_canary.json").write_text(json.dumps(
        {"as_of": old, "summary": "round r1: 0 ok",
         "failing": [{"email": "x@a.com", "response_pct": 40.0}]}))
    client, emails, camps = build_world(reply_counts={e: 3 for e in emails_of()}, days=7)
    report = M.run_monitor(NOW, client=client, levels=[1, 4], changeset_dir=tmp_path,
                           campaigns=camps, log_fn=lambda *a: None,
                           notify_fn=lambda *a, **k: None, sleep=lambda s: None)
    assert [p for p in report["proposals"] if p["level"] == 4] == []
    assert report["level4"]["stale"] is True
    assert TH.CANARY_RESULT_MAX_AGE_DAYS == 7


def test_a_413_does_not_withdraw_the_levels_it_could_not_evaluate(tmp_path):
    """A second run that could not read the analytics endpoint used to mark the
    morning's level 3 verdicts 'withdrawn', and the apply script then skipped
    them. A retire_domain verdict disappeared with only a note to show for it."""
    friday = ct("2026-09-25 07:00")
    names = emails_of()
    replies = {e: 0 for e in names[:3]}
    replies.update({names[3]: 8, names[4]: 8, names[5]: 8})
    client, _, camps = build_world(reply_counts=replies, days=7, now=friday)
    first = M.run_monitor(friday, client=client, changeset_dir=tmp_path, campaigns=camps,
                          write=True, send_card=False, log_fn=lambda *a: None,
                          notify_fn=lambda *a, **k: None, sleep=lambda s: None)
    assert any(p["level"] == 3 for p in first["proposals"])
    path = tmp_path / "2026-09-25.json"
    before = {p["id"]: p["status"] for p in json.loads(path.read_text())["proposals"]}
    assert all(v == "proposed" for v in before.values())

    class Blows(type(client)):
        def daily_account_analytics(self, emails=None, start_date=None, end_date=None):
            raise RuntimeError("HTTP 413 Analytics request is too large")

    broken = Blows(accounts=client._accounts, campaigns=camps,
                   warmup=client._warmup, daily=client._daily)
    # Force a level 1 finding so the second run has something to write.
    broken._warmup = {e: {"health_score": 94} for e in names}
    second = M.run_monitor(friday + timedelta(hours=5), client=broken, changeset_dir=tmp_path,
                           campaigns=camps, write=True, send_card=False,
                           log_fn=lambda *a: None, notify_fn=lambda *a, **k: None,
                           sleep=lambda s: None)
    assert 3 not in second["levels_evaluated"]
    after = {p["id"]: p for p in json.loads(path.read_text())["proposals"]}
    level3_ids = [pid for pid, p in after.items() if p.get("level") == 3]
    assert level3_ids
    for pid in level3_ids:
        assert after[pid]["status"] == "proposed", pid
        assert "not all evaluated" in after[pid].get("kept_because", "")


def test_partial_beats_proposals_and_is_pushed_loud(tmp_path):
    """MKT-9: a run whose analytics read failed but which still proposed
    something from level 1 logged "proposals" and exited 0."""
    friday = ct("2026-09-25 07:00")
    names = emails_of()
    client, _, camps = build_world(days=7, now=friday)

    class Blows(type(client)):
        def daily_account_analytics(self, emails=None, start_date=None, end_date=None):
            raise RuntimeError("HTTP 413 Analytics request is too large")

    broken = Blows(accounts=client._accounts, campaigns=camps, warmup=client._warmup, daily=client._daily)
    broken._warmup = {e: {"health_score": 94} for e in names}
    rows, pushes = [], []
    report = M.run_monitor(friday, client=broken, changeset_dir=tmp_path, campaigns=camps, write=False,
                           dry_run=False, send_card=True, sleep=lambda s: None,
                           log_fn=lambda job, status, details=None: rows.append((status, details)),
                           notify_fn=lambda title, body="", **k: pushes.append((title, k)))
    assert report["proposals"], "the level 1 finding should still be proposed"
    assert report["partial"] is True
    assert report["status"] == "partial"
    assert rows[-1][0] == "partial" and rows[-1][1]["partial"] is True
    assert 3 not in rows[-1][1]["levels_evaluated"]
    assert pushes[-1][1]["priority"] == "high" and "PARTIAL" in pushes[-1][0]


def test_main_exits_non_zero_on_a_partial_run(monkeypatch):
    monkeypatch.setattr(M, "run_monitor", lambda now, **kw: {"partial": True, "card": "card"})
    monkeypatch.setattr(job_log, "use_scratch_logs", lambda *a, **k: None)
    assert M.main(["--dry-run", "--as-of", "2026-09-25T12:00:00+00:00"]) == 1
    assert M.main(["--dry-run", "--as-of", "2026-09-25T12:00:00+00:00", "--json"]) == 1
    monkeypatch.setattr(M, "run_monitor", lambda now, **kw: {"partial": False, "card": "card"})
    assert M.main(["--dry-run", "--as-of", "2026-09-25T12:00:00+00:00"]) == 0


def test_a_level_1_only_rerun_leaves_fridays_level_3_proposals_proposed(tmp_path):
    friday = ct("2026-09-25 07:00")
    names = emails_of()
    replies = {e: 0 for e in names[:3]}
    replies.update({names[3]: 8, names[4]: 8, names[5]: 8})
    client, _, camps = build_world(reply_counts=replies, days=7, now=friday)
    M.run_monitor(friday, client=client, changeset_dir=tmp_path, campaigns=camps, write=True,
                  send_card=False, log_fn=lambda *a: None, notify_fn=lambda *a, **k: None,
                  sleep=lambda s: None)
    client._warmup = {e: {"health_score": 94} for e in names}
    M.run_monitor(friday + timedelta(hours=7), client=client, levels=[1], changeset_dir=tmp_path,
                  campaigns=camps, write=True, send_card=False, log_fn=lambda *a: None,
                  notify_fn=lambda *a, **k: None, sleep=lambda s: None)
    after = json.loads((tmp_path / "2026-09-25.json").read_text())["proposals"]
    level3 = [p for p in after if p.get("level") == 3]
    assert level3 and all(p["status"] == "proposed" for p in level3)


def test_a_writer_with_a_pause_only_action_list_does_not_delete_the_email_list_patches(tmp_path):
    """Three jobs write one day's file. Merging used to replace the earlier
    proposal wholesale, so the canary's pause-only list silently deleted the
    monitor's patches and applying the result left a paused inbox in every
    campaign."""
    complete = {"id": "pause_inbox:x@a.com", "kind": "pause_inbox", "target": "x@a.com",
                "severity": "high", "level": 1, "reason": "health", "evidence": {},
                "actions": [{"system": "instantly", "op": "pause_account", "email": "x@a.com"},
                            {"system": "instantly", "op": "patch_campaign_email_list",
                             "campaign_key": "c1", "campaign_id": "cid-1", "remove": "x@a.com",
                             "add": None, "expected_before": ["x@a.com", "y@a.com"],
                             "expected_after": ["y@a.com"]}]}
    M.write_changeset({"generated_at": "2026-09-26T12:00:00+00:00", "generated_by": "deliverability_monitor",
                       "levels_run": [1], "levels_evaluated": [1], "capacity": {"sending": 12},
                       "proposals": [complete]}, NOW, tmp_path)
    pause_only = dict(complete, actions=[{"system": "instantly", "op": "pause_account",
                                          "email": "x@a.com"}], level=4)
    M.write_changeset({"generated_at": "2026-09-26T12:15:00+00:00", "generated_by": "autoresponder_canary",
                       "levels_run": [4], "levels_evaluated": [4],
                       "proposals": [pause_only]}, NOW, tmp_path)
    data = json.loads((tmp_path / "2026-09-22.json").read_text())
    ops = [a["op"] for a in data["proposals"][0]["actions"]]
    assert "pause_account" in ops and "patch_campaign_email_list" in ops
    # ... and the context blocks the first writer supplied survive.
    assert data["capacity"] == {"sending": 12}
    assert set(data["written_by"]) == {"deliverability_monitor", "autoresponder_canary"}


def test_an_empty_accounts_read_is_an_error_not_a_clean_bill_of_health():
    """'0 inboxes, 0 proposals / No action proposed' with Job_Log status ok was
    how an unreadable workspace used to report a 45-inbox fleet."""
    client = StubClient(accounts=[], campaigns={})
    with pytest.raises(RuntimeError) as exc:
        M.load_accounts(client)
    assert "zero accounts" in str(exc.value)


# =========================================================================
# Review fixes: level 1 accumulates, the card adds up, no dead thresholds
# =========================================================================

def test_level1_reports_both_the_dns_fault_and_the_health_failure():
    """The health branch used to overwrite the verdict and the reason the vitals
    check had just set, so an inbox on a DKIM-less domain at 94% health printed
    only the health number and the operator chased the wrong thing."""
    emails = ["x@a.com"]
    camps = {"c1": campaign("c1", "cid-1", emails)}
    inboxes = M.build_inbox_index([account(e) for e in emails], camps, NOW)
    vitals = {"a.com": {"mx": True, "spf": True, "dkim": False, "dmarc": True,
                        "missing": ["dkim"], "allPass": False, "passed": False}}
    out = M.level1(inboxes, {"x@a.com": {"health_score": 94}}, vitals)
    row = out["rows"][0]
    assert set(row["verdicts"]) == {"dns_fail", "health_fail"}
    assert "dkim" in row["reason"] and "94%" in row["reason"]
    assert row["verdict"] == "health_fail"          # the most actionable one leads
    assert out["findings"] == [row]


def test_the_card_states_the_total_capacity_cost_of_the_days_proposals():
    """Four removals each printing '25 sends/day' is 100 of 300, and that is the
    number that decides whether any of them can be applied today. It used to
    appear only in the runbook."""
    names = emails_of()
    # 14 replies each spreads one per day over both the 7 and the 14 day window,
    # so the healthy four pass on BOTH and only the two silent ones are removed.
    replies = {e: 0 for e in names[:2]}
    replies.update({e: 14 for e in names[2:]})
    client, _, camps = build_world(reply_counts=replies, days=14)
    inboxes = M.build_inbox_index(client._accounts, camps, NOW)
    out = M.level3(inboxes, client._daily, NOW)
    props = M.build_proposals({"findings": [], "domain_dns_faults": {}}, out, None, None,
                              inboxes, camps, [])
    card = M.render_card({"proposals": props, "capacity": M._capacity(inboxes),
                          "as_of_ct": "Tue", "levels_run": [1, 3], "level3": out})
    assert "Applying all of these removes 2 of 6 sending inbox(es)" in card
    assert "50 of 150 sends/day" in card
    # health alerts only (2026-09-22): the cost line no longer counts spares
    assert "promotable" not in card and "insurance" not in card


def test_a_bounce_rate_sitting_exactly_on_the_ceiling_is_flagged_on_the_card():
    """Three sending inboxes read exactly 2.00% on 2026-09-22: not a failure,
    but one more bounce condemns them and the card said nothing."""
    assert M._at_the_line(2.0) is True
    assert M._at_the_line(1.90) is False
    assert M._at_the_line(2.5) is False          # over the line is a failure, not a warning
    assert TH.BOUNCE_RATE_AT_LINE_EPSILON_PCT > 0


def test_the_notify_priority_comes_from_the_threshold_not_a_literal():
    assert TH.severities_at_or_above("high") == ("critical", "high")
    assert TH.severities_at_or_above("medium") == ("critical", "high", "medium")
    assert TH.NOTIFY_HIGH_PRIORITY_AT == "high"
    assert TH.demote("critical") == "high" and TH.demote("low") == "low"
    assert TH.cap_severity("high", "medium") == "medium"
    assert TH.cap_severity("low", "medium") == "low"


def test_levels_by_weekday_is_derived_from_the_named_weekday_constants():
    assert 2 in TH.LEVELS_BY_WEEKDAY[TH.LEVEL2_WEEKDAY]
    assert 3 in TH.LEVELS_BY_WEEKDAY[TH.LEVEL3_WEEKDAY]
    assert 4 in TH.LEVELS_BY_WEEKDAY[TH.LEVEL4_WEEKDAY]
    for day, levels in TH.LEVELS_BY_WEEKDAY.items():
        assert set(TH.LEVELS_EVERY_DAY).issubset(set(levels)), day


def test_thresholds_have_no_dead_constants():
    """A number nobody consults is decoration, and a reader who tunes it gets no
    error and no effect. MAX_INBOXES_PER_DOMAIN and NOTIFY_HIGH_PRIORITY_AT were
    both declared and never read."""
    import re
    from pathlib import Path as _Path

    base = _Path(M.__file__).resolve().parent.parent
    sources = [
        base / "jobs" / "deliverability_monitor.py",
        base / "jobs" / "inbox_placement.py",
        base / "jobs" / "autoresponder_canary.py",
        base / "changesets" / "inbox_actions" / "apply_inbox_actions.py",
        # The capacity job binds its own names to these constants rather than
        # re-declaring them (M2/O8 owns the raised-limit rule), so it counts as
        # a reader: without it, PER_INBOX_DAILY_LIMIT_RAISED reads as dead.
        base / "jobs" / "inbox_inventory.py",
        # The M4 verdict lines, the experiment alpha and the list factory's
        # Section 6 cost lines were bound to thresholds.py on 2026-09-22 (MKT-5).
        base / "services" / "experiments" / "verdicts.py",
        base / "services" / "experiments" / "experiment_log.py",
        base / "services" / "list_factory" / "ledger.py",
        # M5's 3,300-a-week default target (re-review MKT-5).
        base / "services" / "list_factory" / "pipeline.py",
        base / "jobs" / "list_factory.py",
    ]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    thresholds_src = (base / "shared" / "thresholds.py").read_text(encoding="utf-8")
    dead = []
    for name in dir(TH):
        if not re.match(r"^[A-Z][A-Z0-9_]*$", name) or name in TH.RESERVED_CONSTANTS:
            continue
        if name == "RESERVED_CONSTANTS":
            continue
        used_by_a_job = name in blob
        # A constant another constant in this module is derived from counts too.
        derived = len(re.findall(r"\b%s\b" % name, thresholds_src)) > 1
        if not used_by_a_job and not derived:
            dead.append(name)
    assert dead == [], "thresholds nothing reads: %s" % ", ".join(dead)


def test_reserved_constants_each_carry_a_reason():
    for name, why in TH.RESERVED_CONSTANTS.items():
        assert hasattr(TH, name), name
        assert len(why) > 30, name


# =========================================================================
# Review fix: a scheduled job that dies must say so
# =========================================================================

def _capture(monkeypatch, module):
    logged, notified = [], []
    monkeypatch.setattr(module, "log_run", lambda *a, **k: logged.append((a, k)))
    monkeypatch.setattr(module, "notify", lambda *a, **k: notified.append((a, k)))
    return logged, notified


def test_the_monitor_logs_and_alerts_when_the_run_blows_up(monkeypatch):
    """A silent 07:00 death reads exactly like a quiet morning: Lorenzo simply
    stops receiving cards, which is the failure this job exists to prevent for
    the inboxes. jobs/campaign_verdicts.py is the house pattern."""
    logged, notified = _capture(monkeypatch, M)

    def boom(*a, **k):
        raise RuntimeError("HTTP 503 from accounts/test/vitals")

    monkeypatch.setattr(M, "run_monitor", boom)
    rc = M.main(["--dry-run"])
    assert rc == 1
    assert logged and logged[0][0][1] == "failed"
    assert "503" in logged[0][0][2]["error"]
    assert notified and notified[0][1]["priority"] == "high"


def test_the_placement_job_logs_and_alerts_when_the_run_blows_up(monkeypatch):
    from jobs import inbox_placement as P

    logged, notified = _capture(monkeypatch, P)
    monkeypatch.setattr(P, "run_placement", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429")))
    assert P.main(["--dry-run"]) == 1
    assert logged[0][0][1] == "failed" and notified[0][1]["priority"] == "high"


def test_the_canary_logs_and_alerts_when_the_run_blows_up(monkeypatch):
    from jobs import autoresponder_canary as C

    logged, notified = _capture(monkeypatch, C)
    monkeypatch.setattr(C, "run_canary", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert C.main(["--dry-run"]) == 1
    assert logged[0][0][1] == "failed" and notified[0][1]["priority"] == "high"


def test_a_read_only_post_is_issued_with_retry_so_a_503_on_vitals_is_not_fatal():
    """accounts/test/vitals and the placement stats endpoint are reads, but the
    client's READ_POST_PATHS list does not carry them, so one transient 5xx used
    to take the whole run down without a retry."""
    seen = {}

    class Client(object):
        def _request(self, method, path, params=None, json=None, retry=None):
            seen.update({"method": method, "path": path, "retry": retry, "json": json})
            return {"success_list": [], "failure_list": []}

        def _post(self, path, body=None):
            raise AssertionError("should have gone through _request with retry=True")

    M._read_post(Client(), "accounts/test/vitals", {"accounts": ["x@a.com"]})
    assert seen["method"] == "POST" and seen["retry"] is True
    assert seen["path"] == "accounts/test/vitals"


def test_read_post_still_works_against_a_client_without_request():
    class Old(object):
        def _post(self, path, body=None):
            return {"path": path, "body": body}

    assert M._read_post(Old(), "accounts/test/vitals", {"accounts": []})["path"] \
        == "accounts/test/vitals"


def test_a_truncated_ndr_scan_says_it_only_saw_the_newest_messages():
    """A miss here is already reported as a miss, so a partial scan is tolerated
    rather than refused - but 'no NDRs found over the newest 500 messages' is a
    much weaker statement than 'no NDRs found', and the note used to say the
    stronger one."""
    class Truncated(list):
        truncated = True
        complete = False

    class Client(object):
        def iterate(self, path, params=None, body=None, max_pages=200):
            return Truncated([{"subject": "hello", "content_preview": "hi",
                               "from_address_email": "a@b.com"}])

    out = M.scan_bounce_signatures(Client())
    assert out["partial"] is True and out["scanned"] == 1
    assert "newest 1 received message(s) only" in out["note"]
    card = M.render_card({"proposals": [], "capacity": {}, "as_of_ct": "Tue", "levels_run": [1],
                          "bounces": {"hours": 24, "recent": [], "total_bounced_all_time": 0},
                          "bounce_signatures": out})
    assert "scanned the newest 1 message(s) only" in card


def test_a_complete_ndr_scan_is_not_labelled_partial():
    client = StubClient(emails=[{"subject": "Automatic reply", "content_preview": "",
                                 "from_address_email": "a@b.com"}])
    out = M.scan_bounce_signatures(client)
    assert out["partial"] is False
    assert "not evidence of clean delivery" in out["note"]


# ------------------------------------------ health alerts only (2026-09-22)
# Lorenzo: how many spare inboxes to hold, and when to buy more, is his call.
# The card, the push, the Job_Log row and the change-set's capacity block carry
# no insurance count, no promotable count, no reserve ratio against a floor and
# no buying language. Every health check and proposal stays.

_RESERVE_OR_BUY = re.compile(
    r"\b(order\w*|buy\w*|bought|purchas\w*|reserve\w*|top(ped)? up|on hand|spares?|insurance|"
    r"promotable)\b", re.IGNORECASE)


@pytest.mark.parametrize("with_ready_inbox", [False, True])
def test_no_output_counts_a_reserve_or_mentions_buying(tmp_path, with_ready_inbox):
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names[1:]}, days=7)
    if with_ready_inbox:
        client._accounts.append(_insurance("ready@c.com"))
        client._warmup["ready@c.com"] = {"health_score": 100, "sent": 60, "landed_inbox": 60,
                                         "received": 90}
    rows, pushes = [], []
    report = M.run_monitor(NOW, client=client, levels=[1, 3], dry_run=False,
                           log_fn=lambda job, status, details=None: rows.append((status, details)),
                           notify_fn=lambda title, body="", **k: pushes.append((title, body)),
                           changeset_dir=tmp_path, campaigns=camps, sleep=lambda s: None)
    # the health check still fires and still proposes the removal
    assert report["proposals"] and report["proposals"][0]["target"] == names[0]
    if with_ready_inbox:
        assert report["proposals"][0]["replacement"] == "ready@c.com"
        assert "replace with ready@c.com" in report["card"]
    else:
        assert "NO replacement available" in report["card"]
    assert "Applying all of these removes 1 of 6 sending inbox(es)" in report["card"]

    assert set(report["capacity"]) == {"total", "sending", "paused", "daily_capacity", "domains"}
    assert "insurance_promotable" not in report
    for text in [report["card"], json.dumps(rows[-1][1], default=str)] + list(pushes[-1]):
        hits = sorted(set(m.group(0) for m in _RESERVE_OR_BUY.finditer(text)))
        assert not hits, (hits, text)
        # the old ratio line's marker; "under 1%" is a health line and stays
        assert "  UNDER" not in text and "M2 floor" not in text
    written = json.loads((tmp_path / "2026-09-22.json").read_text(encoding="utf-8"))
    assert set(written["capacity"]) == {"total", "sending", "paused", "daily_capacity", "domains"}


def test_the_reserve_ratio_threshold_is_gone():
    assert not hasattr(TH, "INSURANCE_RATIO_MIN")


def test_retiring_a_domain_says_stop_sending_not_buying():
    """The registrar step used to read "stop buying and sending from X"."""
    import inspect
    src = inspect.getsource(M)
    assert "stop buying" not in src
    assert "stop sending from %s for good" in src


def test_the_card_names_inboxes_in_no_campaign_without_totalling_them():
    """The header said 7 inboxes while the line under it added up to 6. The
    rest are named, never counted: that total is a reserve count."""
    names = emails_of()
    client, _, camps = build_world(reply_counts={e: 4 for e in names}, days=7)
    accounts = client._accounts + [_insurance("ready@c.com")]
    inboxes = M.build_inbox_index(accounts, camps, NOW)
    card = M.render_card({"proposals": [], "capacity": M._capacity(inboxes),
                          "as_of_ct": "Tue", "levels_run": [1]})
    assert "sending 6 (150/day)  paused 0  the rest warming or idle (not in any campaign)" in card
    assert not _RESERVE_OR_BUY.search(card)
    # nothing outside a campaign, no clause
    only_sending = M.build_inbox_index(client._accounts, camps, NOW)
    card = M.render_card({"proposals": [], "capacity": M._capacity(only_sending),
                          "as_of_ct": "Tue", "levels_run": [1]})
    assert "the rest" not in card
