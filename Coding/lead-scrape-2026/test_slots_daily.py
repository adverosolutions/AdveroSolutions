"""slots_daily: slots, fallback, merge, ids and copy checks, --apply gate, backup, read-back, brake, restore, --lead-id. No network."""
import copy
import json
from collections import Counter
from datetime import date, timedelta

import pytest

import slots_daily as sd

MON = date(2026, 10, 5)  # a Monday


def at5(d):
    return sd._local(d, 5, 0)


def ghl_iso(days, times=None):
    """GHL-style free slot ISO strings for the given days (default: the whole grid)."""
    out = []
    for g in sd.grid_for(days):
        if times is None or (g.hour, g.minute) in times:
            out.append(g.isoformat())
    return out


IDS = {k: "cid-%s" % k for k in sd.AI_CAMPAIGN_KEYS}


@pytest.fixture
def ids_file(tmp_path):
    p = tmp_path / "ai_ids.json"
    p.write_text(json.dumps(IDS))
    return p


@pytest.mark.parametrize("offset,want", [
    (0, ("Tue", "Wed")), (1, ("Wed", "Thu")), (2, ("Thu", "Fri")),
    (3, ("Fri", "Mon")), (4, ("Mon", "Tue")), (5, ("Mon", "Tue")),
])
def test_slot_days_for_each_send_weekday(offset, want):
    d = MON + timedelta(days=offset)
    day1, day2, source = sd.compute_slots(d, None, at5(d))
    assert (day1[0].strftime("%a"), day2[0].strftime("%a")) == want
    assert all(x.date() == day1[0].date() for x in day1) and all(x.date() == day2[0].date() for x in day2)
    assert [(x.hour, x.minute) for x in day1][0] == (12, 0) and [(x.hour, x.minute) for x in day1][-1] == (17, 30)
    assert len(day1) == 12 and source == "fallback"


def test_ghl_source_uses_only_free_grid_times():
    d = MON + timedelta(days=2)  # Wed -> Thu, Fri
    free = ghl_iso([d + timedelta(days=1), d + timedelta(days=2)], times={(13, 0), (14, 30)})
    free.append(sd._local(d + timedelta(days=1), 13, 15).isoformat())  # off-grid: ignored
    day1, day2, source = sd.compute_slots(d, free, at5(d))
    assert source == "ghl"
    assert [sd.fmt_slot(x) for x in day1] == ["Thursday at 1pm", "Thursday at 2:30pm"]
    assert [sd.fmt_slot(x, zone=True) for x in day2] == ["Friday at 1pm CT", "Friday at 2:30pm CT"]


def test_text_format():
    assert sd.fmt_slot(sd._local(date(2026, 10, 8), 13, 0)) == "Thursday at 1pm"
    assert sd.fmt_slot(sd._local(date(2026, 10, 8), 13, 30)) == "Thursday at 1:30pm"
    assert sd.fmt_slot(sd._local(date(2026, 10, 8), 12, 0)) == "Thursday at 12pm"
    assert sd.fmt_slot(sd._local(date(2026, 10, 9), 14, 30), zone=True) == "Friday at 2:30pm CT"
    d = MON + timedelta(days=2)
    day1, day2, _ = sd.compute_slots(d, None, at5(d))
    v = sd.slot_vars_for("a@b.com", d, day1, day2)
    assert set(v) == {"slot1", "slot2", "slot_date"} and v["slot_date"] == "2026-10-07"
    assert not v["slot1"].endswith("CT") and v["slot2"].endswith(" CT")
    assert ":00" not in v["slot1"] + v["slot2"]
    sentence = "how does %s or %s sound?" % (v["slot1"], v["slot2"])
    assert sentence.startswith("how does Thursday at ") and " or Friday at " in sentence and sentence.endswith("pm CT sound?")


def test_rollover_when_a_day_is_fully_busy():
    d = MON + timedelta(days=2)  # Wed: Thu fully busy -> Fri + Mon
    free = ghl_iso([d + timedelta(days=2), d + timedelta(days=5)])
    day1, day2, _ = sd.compute_slots(d, free, at5(d))
    assert day1[0].date() == date(2026, 10, 9) and day2[0].date() == date(2026, 10, 12)


def test_too_few_slots_errors_and_job_writes_nothing(tmp_path, ids_file):
    d = MON + timedelta(days=2)
    only_one_day = ghl_iso([d + timedelta(days=1)])
    with pytest.raises(sd.SlotError):
        sd.compute_slots(d, only_one_day, at5(d))

    def boom(*a, **k):
        raise AssertionError("Instantly must not be called")
    log = tmp_path / "log.jsonl"
    rc = sd.run(["--date", d.isoformat(), "--ids-file", str(ids_file)], now=at5(d), call_fn=boom,
                tok_fn=lambda: "t", free_fn=lambda now: only_one_day, log_path=log)
    assert rc == 1
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["status"] == "slot_error" and rec["source"] == "ghl"


def test_empty_ghl_answer_falls_back_to_grid_loudly(tmp_path, ids_file, capsys):
    d = MON + timedelta(days=2)
    day1, day2, source = sd.compute_slots(d, [], at5(d))
    assert source == "fallback_empty" and len(day1) == 12 and len(day2) == 12
    fake = FakeInstantly({})
    log = tmp_path / "log.jsonl"
    rc = sd.run(["--date", d.isoformat(), "--ids-file", str(ids_file)], now=at5(d), call_fn=fake,
                tok_fn=lambda: "t", free_fn=lambda now: [], log_path=log)
    assert rc == 0
    assert json.loads(log.read_text().splitlines()[-1])["source"] == "fallback_empty"
    out = capsys.readouterr().out
    assert "GHL CALENDAR NOT READ (GHL answered with no free slot" in out


def test_beyond_five_business_days_is_refused():
    d = MON + timedelta(days=2)
    # Thu free, then nothing until 6+ business days out
    free = ghl_iso([d + timedelta(days=1), d + timedelta(days=9)])
    with pytest.raises(sd.SlotError):
        sd.compute_slots(d, free, at5(d))


def test_spread_is_deterministic_and_even():
    d = MON
    day1, day2, _ = sd.compute_slots(d, None, at5(d))
    emails = ["lead%05d@example%d.com" % (i, i % 7) for i in range(6000)]
    a = [sd.slot_vars_for(e, d, day1, day2) for e in emails]
    b = [sd.slot_vars_for(e.upper(), d, day1, day2) for e in emails]
    assert a == b  # stable, case-insensitive
    c1 = Counter(v["slot1"] for v in a)
    c2 = Counter(v["slot2"] for v in a)
    assert len(c1) == 12 and len(c2) == 12
    for c in (c1, c2):
        assert max(c.values()) < 500 * 1.2 and min(c.values()) > 500 * 0.8
    other_day = [sd.slot_vars_for(e, d + timedelta(days=1), *sd.compute_slots(d + timedelta(days=1), None,
                                                                              at5(d + timedelta(days=1)))[:2])
                 for e in emails[:50]]
    assert other_day != a[:50]



LIVE = {"MODE": "live", "ALLOW_LIVE_WRITES": "1"}
GOOD_STEP1 = "Hey\n\nhow does {{slot1}} or {{slot2}} sound?"
GOOD_STEP2 = "Would {{slot1}} or {{slot2}} work for a quick 15 minute call?"


def campaign(step1=(GOOD_STEP1, GOOD_STEP1), step2=(GOOD_STEP2,)):
    steps = [{"type": "email", "variants": [{"subject": "s", "body": b} for b in step1]}]
    if step2 is not None:
        steps.append({"type": "email", "variants": [{"subject": "", "body": b} for b in step2]})
    return {"id": "c", "sequences": [{"steps": steps}]}


class FakeInstantly(object):
    """leads/list, GET campaigns/{id}, GET leads/{id} and PATCH leads/{id}.
    patch_mode: merge (documented behaviour), replace (custom_variables replace
    the payload), drop_pause (merge, but Instantly loses pause_until), noop."""

    def __init__(self, leads_by_cid, ignore_filter=False, campaigns=None, patch_mode="merge", fail_ids=(),
                 get_leads=None, on_patch=None, list_error=None):
        self.leads, self.ignore, self.calls = leads_by_cid, ignore_filter, []
        self.by_id = {l["id"]: l for ls in leads_by_cid.values() for l in ls}
        self.campaigns = campaigns or {}
        self.patch_mode, self.fail_ids, self.get_leads = patch_mode, set(fail_ids), get_leads or {}
        self.on_patch, self.list_error = on_patch, list_error

    def __call__(self, method, path, body=None, tok=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if method == "POST" and path == "leads/list":
            if self.list_error:
                raise self.list_error
            if self.ignore or "campaign" not in body:
                items = [l for ls in self.leads.values() for l in ls]
            else:
                items = list(self.leads.get(body["campaign"], []))
            return {"items": copy.deepcopy(items), "next_starting_after": None}
        if method == "GET" and path.startswith("campaigns/"):
            return copy.deepcopy(self.campaigns.get(path.split("/", 1)[1], campaign()))
        if method == "GET" and path.startswith("leads/"):
            lid = path.split("/", 1)[1]
            if lid in self.get_leads:
                return copy.deepcopy(self.get_leads[lid])
            return copy.deepcopy(self.by_id.get(lid, {}))
        if method == "PATCH" and path.startswith("leads/"):
            lid = path.split("/", 1)[1]
            if self.on_patch:
                self.on_patch(lid, body)
            if lid in self.fail_ids:
                raise SystemExit("PATCH %s -> HTTP 500: boom" % path)
            lead = self.by_id[lid]
            cv = body["custom_variables"]
            if self.patch_mode in ("merge", "drop_pause"):
                lead["payload"].update(cv)
                if self.patch_mode == "drop_pause":
                    lead["payload"].pop("pause_until", None)
            elif self.patch_mode == "replace":
                lead["payload"] = dict(cv)
            return {}
        raise AssertionError("unexpected %s %s" % (method, path))

    def patches(self):
        return [c for c in self.calls if c[0] == "PATCH"]


def _lead(i, cid, status=1, replies=0, payload=True, pause_until=None):
    l = {"id": "L%d" % i, "email": "p%d@x.com" % i, "campaign": cid, "status": status, "email_reply_count": replies,
         "first_name": "Pat", "company_name": "Acme"}
    if payload is True:
        l["payload"] = {"firstName": "Pat", "companyName": "Acme", "email": l["email"],
                        "personalization": "Hey Pat, saw that you do X.", "lead_id": "BO-%d" % i,
                        "specialty": "", "mv_result": "ok", "campaign": "e12bb686-old-niche-tag"}
        if pause_until:
            l["payload"]["pause_until"] = pause_until
    elif payload is not False:
        l["payload"] = payload
    return l


def _apply(fake, ids_file, tmp_path, extra=(), d=MON, env=None, **kw):
    log = tmp_path / "l.jsonl"
    rc = sd.run(["--apply", "--date", d.isoformat(), "--ids-file", str(ids_file)] + list(extra), now=at5(d),
                call_fn=fake, tok_fn=lambda: "t", free_fn=lambda now: ghl_iso(sd.business_days_after(d, 3)),
                environ=LIVE if env is None else env, log_path=log, sleep=lambda s: None, **kw)
    lines = log.read_text().splitlines() if log.exists() else []
    return rc, (json.loads(lines[-1]) if lines else None)


def test_merge_keeps_existing_variables_and_skips_identical():
    existing = {"personalization": "Hey", "lead_id": "BO-1", "specialty": "x", "mv_result": "ok"}
    new = {"slot1": "Monday at 1pm", "slot2": "Tuesday at 2pm CT", "slot_date": "2026-10-03"}
    out = sd.merged_variables(existing, new)
    assert out == dict(existing, **new)
    assert sd.merged_variables(out, new) is None
    lead = _lead(1, "c", pause_until="2026-10-09T00:00:00Z")
    got = sd.existing_custom_variables(lead)
    # standard fields AND Instantly's own campaign / pause_until are never written back
    assert got == {"personalization": "Hey Pat, saw that you do X.", "lead_id": "BO-1", "specialty": "", "mv_result": "ok"}
    assert sd.existing_custom_variables({"id": "x"}) is None


@pytest.mark.parametrize("lead", [
    {"id": "x", "payload": None},
    {"id": "x", "payload": {}},
    {"id": "x", "payload": {"firstName": "Pat", "companyName": "Acme", "email": "p@x.com", "campaign": "c"}},
    {"id": "x", "payload": {"personalization": "   ", "lead_id": "BO-1"}},
    {"id": "x", "payload": "not a dict"},
    {"id": "x", "custom_variables": {}},
    {"id": "x", "custom_variables": {"lead_id": "BO-1"}},
])
def test_unreadable_variables_are_none(lead):
    assert sd.existing_custom_variables(lead) is None


def test_unreadable_list_payload_is_refetched_then_skipped(tmp_path, ids_file):
    cid = IDS["msp_ai"]
    bad_null, bad_empty, bad_std = _lead(1, cid, payload=None), _lead(2, cid, payload={}), _lead(
        3, cid, payload={"firstName": "Pat", "companyName": "Acme", "email": "p3@x.com"})
    full = _lead(1, cid)  # GET returns the real payload for L1 only
    fake = FakeInstantly({cid: [bad_null, bad_empty, bad_std]}, get_leads={"L1": full})
    fake.by_id["L1"] = full
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 0
    gets = [c[1] for c in fake.calls if c[0] == "GET" and c[1].startswith("leads/")]
    assert {"leads/L1", "leads/L2", "leads/L3"} <= set(gets)
    patches = fake.patches()
    assert [p[1] for p in patches] == ["leads/L1"]
    cv = patches[0][2]["custom_variables"]
    assert cv["personalization"] == "Hey Pat, saw that you do X." and cv["lead_id"] == "BO-1" and cv["slot1"]
    assert "campaign" not in cv and "firstName" not in cv
    assert rec["counts"]["msp_ai"]["unreadable"] == 2 and rec["counts"]["msp_ai"]["change"] == 1


def test_dry_run_plans_full_dicts_and_filters_ineligible(tmp_path, ids_file, capsys):
    cid = IDS["msp_ai"]
    leads = [_lead(1, cid), _lead(2, cid, status=3), _lead(3, cid, status=-1), _lead(4, cid, status=-2),
             _lead(5, cid, replies=1), _lead(6, cid, status=2), _lead(7, cid, payload=False)]
    fake = FakeInstantly({cid: leads})
    d = MON + timedelta(days=3)
    log = tmp_path / "log.jsonl"
    rc = sd.run(["--date", d.isoformat(), "--ids-file", str(ids_file)], now=at5(d), call_fn=fake,
                tok_fn=lambda: "t", free_fn=lambda now: None, log_path=log)
    assert rc == 0
    assert not fake.patches()
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["source"] == "fallback" and rec["status"] == "dry_run_ok"
    assert rec["counts"]["msp_ai"] == {"leads": 7, "eligible": 3, "change": 2, "unchanged": 0, "unreadable": 1}
    out = capsys.readouterr().out
    assert "CALENDAR NOT READ" in out and "would_change=2" in out and "copy check: all six" in out


def test_apply_refuses_without_both_env_vars_and_logs_it(tmp_path, ids_file):
    def boom(*a, **k):
        raise AssertionError("nothing may be read or written")
    log = tmp_path / "l.jsonl"
    envs = ({}, {"MODE": "live"}, {"ALLOW_LIVE_WRITES": "1"}, {"MODE": "shadow", "ALLOW_LIVE_WRITES": "1"})
    for env in envs:
        for extra in ([], ["--restore", str(tmp_path / "b.json")], ["--lead-id", "L1"]):
            rc = sd.run(["--apply", "--ids-file", str(ids_file)] + extra, call_fn=boom, tok_fn=boom, free_fn=boom,
                        environ=env, log_path=log)
            assert rc == 2
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(lines) == len(envs) * 3 and all(x["status"] == "refused" for x in lines)


def test_apply_backs_up_then_patches_full_merged_dict_and_reads_back(tmp_path, ids_file):
    cid = IDS["pest_control_ai"]
    seen_backup = []

    def on_patch(lid, body):
        if not seen_backup:
            files = list(tmp_path.glob("slots_backup_2026-10-05_*.json"))
            assert len(files) == 1, "backup must exist before the first PATCH"
            seen_backup.append(json.loads(files[0].read_text()))
    fake = FakeInstantly({cid: [_lead(1, cid, pause_until="2026-10-20T00:00:00Z"), _lead(2, cid)]}, on_patch=on_patch)
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 0 and rec["status"] == "applied" and rec["patched"] == 2
    patches = fake.patches()
    assert [p[1] for p in patches] == ["leads/L1", "leads/L2"]
    cv = patches[0][2]["custom_variables"]
    assert set(patches[0][2]) == {"custom_variables"}
    assert cv["personalization"] == "Hey Pat, saw that you do X." and cv["lead_id"] == "BO-1" and cv["mv_result"] == "ok"
    assert "campaign" not in cv and "pause_until" not in cv
    assert cv["slot1"].startswith("Tuesday at ") and cv["slot2"].startswith("Wednesday at ") and cv["slot_date"] == "2026-10-05"
    # read-back GET right after the first PATCH
    i_patch = fake.calls.index(next(c for c in fake.calls if c[0] == "PATCH"))
    assert fake.calls[i_patch + 1][:2] == ("GET", "leads/L1")
    backup = seen_backup[0]
    assert [e["id"] for e in backup["leads"]] == ["L1", "L2"]
    e = backup["leads"][0]
    assert e["email"] == "p1@x.com" and e["campaign"] == cid and e["payload"]["pause_until"] == "2026-10-20T00:00:00Z"
    assert e["payload"]["firstName"] == "Pat" and "slot1" not in e["custom_variables"]
    assert rec["backup"].endswith(".json") and rec["readback"]["ok"] is True


@pytest.mark.parametrize("mode,want", [
    ("replace", "payload.firstName changed"),
    ("drop_pause", "payload.pause_until changed"),
    ("noop", "slot1 not set"),
])
def test_first_write_check_aborts(tmp_path, ids_file, capsys, mode, want):
    cid = IDS["msp_ai"]
    fake = FakeInstantly({cid: [_lead(i, cid, pause_until="2026-10-20T00:00:00Z") for i in range(1, 4)]},
                         patch_mode=mode)
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 3
    assert len(fake.patches()) == 1
    assert rec["status"] == "readback_failed" and rec["patched"] == 1
    assert any(p.startswith(want) for p in rec["problems"]), rec["problems"]
    assert "--restore" in capsys.readouterr().out


def test_first_write_check_sees_top_level_name_change(tmp_path, ids_file):
    cid = IDS["msp_ai"]
    fake = FakeInstantly({cid: [_lead(1, cid), _lead(2, cid)]})
    orig = fake.__call__

    def call(method, path, body=None, tok=None):
        out = orig(method, path, body, tok)
        if method == "PATCH":
            fake.by_id[path.split("/")[1]]["company_name"] = ""
        return out
    rc, rec = _apply(call, ids_file, tmp_path)
    assert rc == 3 and any(p.startswith("company_name changed") for p in rec["problems"])


def test_failure_brake_stops_after_five_in_a_row(tmp_path, ids_file):
    cid = IDS["msp_ai"]
    leads = [_lead(i, cid) for i in range(1, 9)]
    fake = FakeInstantly({cid: leads}, fail_ids={l["id"] for l in leads})
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 3 and len(fake.patches()) == 5
    assert rec["status"] == "failure_brake" and rec["patched"] == 0 and rec["failed"] == 5


def test_a_few_failures_do_not_trip_the_brake(tmp_path, ids_file):
    cid = IDS["msp_ai"]
    fake = FakeInstantly({cid: [_lead(i, cid) for i in range(1, 5)]}, fail_ids={"L1", "L2"})
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 1 and rec["status"] == "applied_with_failures"
    assert rec["patched"] == 2 and rec["failed"] == 2 and rec["readback"]["id"] == "L3"


def test_unexpected_exception_is_logged_with_progress(tmp_path, ids_file, monkeypatch):
    cid = IDS["msp_ai"]
    fake = FakeInstantly({cid: [_lead(1, cid), _lead(2, cid)]})

    def broken(*a, **k):
        raise RuntimeError("bug after the first write")
    monkeypatch.setattr(sd, "readback_problems", broken)
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 3 and rec["status"] == "exception" and rec["patched"] == 1
    assert "RuntimeError" in rec["error"]

    fake2 = FakeInstantly({cid: [_lead(1, cid)]}, list_error=ValueError("bad page"))
    rc, rec = _apply(fake2, ids_file, tmp_path)
    assert rc == 3 and rec["status"] == "exception" and rec["patched"] == 0


def test_restore_is_gated_and_writes_saved_variables(tmp_path, ids_file, capsys):
    cid = IDS["landscaping_ai"]
    fake = FakeInstantly({cid: [_lead(1, cid, pause_until="2026-10-20T00:00:00Z"), _lead(2, cid)]})
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 0
    backup = rec["backup"]
    saved = {e["id"]: e["custom_variables"] for e in json.loads(open(backup).read())["leads"]}

    def boom(*a, **k):
        raise AssertionError("dry-run restore must not call Instantly")
    log = tmp_path / "r.jsonl"
    rc = sd.run(["--restore", backup, "--ids-file", str(ids_file)], call_fn=boom, tok_fn=boom, log_path=log)
    assert rc == 0 and json.loads(log.read_text().splitlines()[-1])["status"] == "restore_dry_run_ok"
    assert "would be PATCHed back" in capsys.readouterr().out
    rc = sd.run(["--restore", backup, "--apply", "--ids-file", str(ids_file)], call_fn=boom, tok_fn=boom,
                environ={}, log_path=log)
    assert rc == 2

    fake2 = FakeInstantly({cid: [_lead(1, cid), _lead(2, cid)]})
    rc = sd.run(["--restore", backup, "--apply", "--ids-file", str(ids_file)], call_fn=fake2, tok_fn=lambda: "t",
                environ=LIVE, log_path=log, sleep=lambda s: None)
    assert rc == 0 and json.loads(log.read_text().splitlines()[-1])["status"] == "restored"
    got = {p[1].split("/")[1]: p[2] for p in fake2.patches()}
    assert got == {lid: {"custom_variables": cv} for lid, cv in saved.items()}
    assert all("pause_until" not in b["custom_variables"] and "campaign" not in b["custom_variables"]
               for b in got.values())

    fake3 = FakeInstantly({cid: [_lead(1, cid), _lead(2, cid)]})
    rc = sd.run(["--restore", backup, "--apply", "--lead-id", "L2", "--ids-file", str(ids_file)], call_fn=fake3,
                tok_fn=lambda: "t", environ=LIVE, log_path=log, sleep=lambda s: None)
    assert rc == 0 and [p[1] for p in fake3.patches()] == ["leads/L2"]


def test_lead_id_rehearsal_touches_exactly_one_lead(tmp_path, ids_file):
    cid = IDS["bookkeeping_ai"]
    fake = FakeInstantly({cid: [_lead(1, cid), _lead(2, cid), _lead(3, cid)]})
    rc, rec = _apply(fake, ids_file, tmp_path, extra=["--lead-id", "L2"])
    assert rc == 0 and rec["status"] == "applied" and rec["patched"] == 1 and rec["lead_id"] == "L2"
    assert [p[1] for p in fake.patches()] == ["leads/L2"]
    assert not [c for c in fake.calls if c[1] == "leads/list"]
    assert ("GET", "leads/L2") in [c[:2] for c in fake.calls[fake.calls.index(fake.patches()[0]):]]
    assert [e["id"] for e in json.loads(open(rec["backup"]).read())["leads"]] == ["L2"]

    other = FakeInstantly({"some-old-campaign": [_lead(9, "some-old-campaign")]})
    rc, rec = _apply(other, ids_file, tmp_path, extra=["--lead-id", "L9"])
    assert rc == 1 and rec["status"] == "lead_id_refused" and not other.patches()


GOOD_IDS = dict(IDS)


@pytest.mark.parametrize("content,needle", [
    (json.dumps(dict(GOOD_IDS, extra_ai="cid-x")), "unexpected"),
    (json.dumps({k: v for k, v in GOOD_IDS.items() if k != "msp_ai"}), "missing"),
    (json.dumps(dict(GOOD_IDS, msp_ai=GOOD_IDS["landscaping_ai"])), "repeats"),
    (json.dumps(dict(GOOD_IDS, msp_ai="d81f1d53-23d6-48a6-aea3-80c21192e17e")), "Service - AI Agents"),
    (json.dumps(dict(GOOD_IDS, msp_ai="59B20790-12bb-446d-bcd6-e3b6f9a61953")), "Recruiting - AI Agents"),
    (json.dumps(dict(GOOD_IDS, msp_ai="old-1")), "reuses"),
    (json.dumps(dict(GOOD_IDS, msp_ai="  ")), "empty"),
    (json.dumps(list(GOOD_IDS.values())), "JSON object"),
    ("{not json", "not valid JSON"),
])
def test_ids_file_validation(tmp_path, content, needle):
    old = tmp_path / "instantly_campaigns.json"
    old.write_text(json.dumps({"cleaning_trigger": "old-1"}))
    p = tmp_path / "ai_ids.json"
    p.write_text(content)
    with pytest.raises(SystemExit) as e:
        sd.load_ai_ids(p, old_ids_path=old)
    assert needle in str(e.value)
    assert sd.load_ai_ids(_write(tmp_path / "ok.json", GOOD_IDS), old_ids_path=old) == GOOD_IDS


def _write(p, obj):
    p.write_text(json.dumps(obj))
    return p


def test_malformed_ids_file_still_logs_a_line(tmp_path):
    bad = tmp_path / "ai_ids.json"
    bad.write_text("{oops")
    log = tmp_path / "l.jsonl"
    rc = sd.run(["--date", MON.isoformat(), "--ids-file", str(bad)], now=at5(MON), call_fn=None,
                tok_fn=None, free_fn=lambda now: None, log_path=log)
    assert rc == 1
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["status"] == "ids_error" and "not valid JSON" in rec["error"]


@pytest.mark.parametrize("camp,needle", [
    (campaign(step1=(GOOD_STEP1, "how does {{slot1}} sound?")), "step 1 variant 2 body lacks ['{{slot2}}']"),
    (campaign(step2=("Would tomorrow work?",)), "step 2 variant 1 body lacks"),
    (campaign(step2=None), "1 step(s) returned"),
])
def test_copy_check_refuses_apply_but_only_warns_on_dry_run(tmp_path, ids_file, capsys, camp, needle):
    cid = IDS["msp_ai"]
    fake = FakeInstantly({cid: [_lead(1, cid)]}, campaigns={IDS["insurance_broker_ai"]: camp})
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 2 and rec["status"] == "copy_check_failed" and not fake.patches()
    assert any(needle in p and p.startswith("insurance_broker_ai") for p in rec["copy_problems"])
    rc = sd.run(["--date", MON.isoformat(), "--ids-file", str(ids_file)], now=at5(MON), call_fn=fake,
                tok_fn=lambda: "t", free_fn=lambda now: None, log_path=tmp_path / "d.jsonl")
    assert rc == 0 and "copy check FAILED" in capsys.readouterr().out


def test_leads_without_campaign_field_fail_loudly(tmp_path, ids_file, capsys):
    cid = IDS["msp_ai"]
    leads = [_lead(1, cid), _lead(2, cid)]
    for l in leads:
        del l["campaign"]
    fake = FakeInstantly({cid: leads})
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 1 and rec["status"] == "no_campaign_field" and not fake.patches()
    assert rec["list_stats"]["no_campaign_field_eligible"] == 2
    assert "NO LEAD MATCHED A CAMPAIGN" in capsys.readouterr().out


def test_ignored_campaign_filter_falls_back_to_grouping():
    a, b = IDS["msp_ai"], "some-old-campaign"
    fake = FakeInstantly({a: [_lead(1, a)], b: [_lead(2, b)]}, ignore_filter=True)
    got = sd.list_campaign_leads(fake, [a])
    assert [l["id"] for l in got[a]] == ["L1"]


def test_old_ids_file_is_refused(tmp_path):
    p = tmp_path / "instantly_campaigns.json"
    p.write_text(json.dumps(IDS))
    with pytest.raises(SystemExit):
        sd.load_ai_ids(p)
    with pytest.raises(SystemExit):
        sd.load_ai_ids(tmp_path / "nope.json")


@pytest.mark.parametrize("hour,day_offset,want_offset", [
    (5, 0, 0), (6, 0, 1), (5, 5, 5), (7, 5, 7), (3, 6, 7), (20, 4, 5),
])
def test_next_send_day(hour, day_offset, want_offset):
    d = MON + timedelta(days=day_offset)
    assert sd.next_send_day(sd._local(d, hour, 0)) == MON + timedelta(days=want_offset)


# ---------------------------------------------------------------- interrupts, usage errors, refetch, read-back privacy
def test_ctrl_c_mid_apply_logs_interrupted_with_progress_and_undo(tmp_path, ids_file, capsys):
    import signal
    cid = IDS["msp_ai"]
    n = []

    def on_patch(lid, body):
        n.append(lid)
        if len(n) == 3:
            raise KeyboardInterrupt()
    before = signal.getsignal(signal.SIGTERM)
    fake = FakeInstantly({cid: [_lead(i, cid) for i in range(1, 6)]}, on_patch=on_patch, fail_ids={"L2"})
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 130
    assert rec["status"] == "interrupted" and rec["signal"] == "SIGINT"
    assert rec["patched"] == 1 and rec["failed"] == 1 and rec["backup"].endswith(".json")
    assert len(fake.patches()) == 3
    out = capsys.readouterr().out
    assert "INTERRUPTED (SIGINT)" in out and "--restore %s" % rec["backup"] in out
    assert signal.getsignal(signal.SIGTERM) == before and signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_sigterm_mid_apply_takes_the_same_path(tmp_path, ids_file, capsys):
    import os
    import signal
    cid = IDS["msp_ai"]
    n = []

    def on_patch(lid, body):
        n.append(lid)
        if len(n) == 2:
            # never send a real SIGTERM unless the job's own handler is installed
            assert signal.getsignal(signal.SIGTERM) is sd._raise_interrupted
            os.kill(os.getpid(), signal.SIGTERM)
    fake = FakeInstantly({cid: [_lead(i, cid) for i in range(1, 5)]}, on_patch=on_patch)
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 128 + signal.SIGTERM and rec["status"] == "interrupted" and rec["signal"] == "SIGTERM"
    assert rec["patched"] == 1 and rec["backup"]
    assert "--restore" in capsys.readouterr().out
    assert signal.getsignal(signal.SIGTERM) is not sd._raise_interrupted


def test_usage_error_leaves_a_log_line(tmp_path):
    log = tmp_path / "l.jsonl"
    with pytest.raises(SystemExit) as e:
        sd.run(["--bogus"], log_path=log)
    assert e.value.code == 2
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["status"] == "usage_error" and rec["argv"] == ["--bogus"] and "--bogus" in rec["error"]
    with pytest.raises(SystemExit) as e:
        sd.run(["--help"], log_path=tmp_path / "h.jsonl")
    assert e.value.code == 0 and not (tmp_path / "h.jsonl").exists()


@pytest.mark.parametrize("swap", ["other_id", "other_campaign"])
def test_refetch_of_another_lead_or_campaign_is_unreadable(tmp_path, ids_file, swap):
    cid = IDS["msp_ai"]
    listed = _lead(1, cid, payload=None)
    wrong = _lead(99, cid) if swap == "other_id" else _lead(1, IDS["pest_control_ai"])
    fake = FakeInstantly({cid: [listed]}, get_leads={"L1": wrong})
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 0 and not fake.patches()
    assert rec["counts"]["msp_ai"]["unreadable"] == 1 and rec["counts"]["msp_ai"]["change"] == 0


def test_readback_requires_lead_id_only_when_the_backup_had_one():
    lead = _lead(1, "c")
    del lead["payload"]["lead_id"]           # a lead added by hand: no lead_id
    slots = {"slot1": "a", "slot2": "b", "slot_date": "2026-10-05"}
    got = copy.deepcopy(lead)
    got["payload"].update(slots)
    entry = {"id": "L1", "raw": lead}
    assert sd.readback_problems(entry, got, slots) == []
    with_id = _lead(1, "c")
    lost = copy.deepcopy(with_id)
    lost["payload"].update(slots, lead_id="")
    summaries = [s for s, _ in sd.readback_problems({"id": "L1", "raw": with_id}, lost, slots)]
    assert "payload.lead_id empty" in summaries and "payload.lead_id changed" in summaries
    top = copy.deepcopy(with_id)
    top["personalization"] = "Hey Pat"
    moved = copy.deepcopy(top)
    moved["payload"].update(slots)
    moved["personalization"] = ""
    assert [s for s, _ in sd.readback_problems({"id": "L1", "raw": top}, moved, slots)] == ["personalization changed"]


def test_readback_failed_log_line_holds_no_lead_values(tmp_path, ids_file):
    cid = IDS["msp_ai"]
    fake = FakeInstantly({cid: [_lead(1, cid), _lead(2, cid)]}, patch_mode="replace")
    rc, rec = _apply(fake, ids_file, tmp_path)
    assert rc == 3 and rec["status"] == "readback_failed"
    line = (tmp_path / "l.jsonl").read_text().splitlines()[-1]
    for secret in ("p1@x.com", "Pat", "Acme", "saw that you do", "BO-1"):
        assert secret not in line, secret
    assert rec["readback_lead_id"] == "L1" and "payload.firstName" in rec["failed_fields"]
    assert rec["details_in"] == rec["backup"]
    doc = json.loads(open(rec["backup"]).read())
    assert doc["readback_failure"]["id"] == "L1" and any("Pat" in p for p in doc["readback_failure"]["problems"])
    assert [e["id"] for e in doc["leads"]] == ["L1", "L2"]   # --restore still reads the same list
