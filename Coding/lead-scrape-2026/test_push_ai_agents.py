"""instantly_push --offer ai_agents, and the old single-file push left as it was. No network."""
import csv
import json
import runpy
import sys
from datetime import date, datetime, timezone

import pytest

import instantly_push as ip
import slots_daily as sd

HERE = ip.ROOT / "instantly_push.py"
IDS = {k: "cid-%s" % k for k in sd.AI_CAMPAIGN_KEYS}
DAY_FIELDS = ["lead_id", "campaign", "send_order", "first_name", "company_name", "personalization", "specialty", "tier"]


def write_csv(path, fields, rows):
    with open(str(path), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def day_row(lead_id, campaign, tier="1", personalization="Hey Pat, saw that you do X."):
    return {"lead_id": lead_id, "campaign": campaign, "send_order": "", "first_name": "Pat",
            "company_name": "Acme Pest Control LLC", "personalization": personalization, "specialty": "", "tier": tier}


@pytest.fixture
def files(tmp_path):
    master = write_csv(tmp_path / "master.csv", ["campaign", "lead_id", "first_name", "last_name", "email", "mv_result", "company_name"], [
        {"campaign": "x", "lead_id": lid, "first_name": "Pat", "last_name": "Lee", "email": em, "mv_result": "ok", "company_name": "Acme"}
        for lid, em in [("PC-1", "a@google.test"), ("MS-1", "b@google.test"), ("LA-1", "c@ms.test"),
                        ("IB-1", "d@google.test"), ("IB-2", "A@google.test"), ("BO-1", "e@other.test"),
                        ("MA-1", "f@google.test"), ("RE-1", "g@google.test"), ("PC-2", "h@google.test")]])
    f1 = write_csv(tmp_path / "day1.csv", DAY_FIELDS, [
        day_row("PC-1", "pest_control"), day_row("MS-1", "msp"), day_row("LA-1", "landscaping"),
        day_row("IB-1", "insurance_broker", tier="skip"), day_row("RE-1", "recruiting"),
        day_row("MA-1", "marketing_agency", personalization="  "), day_row("NO-1", "bookkeeping")])
    f2 = write_csv(tmp_path / "day2.csv", DAY_FIELDS, [
        day_row("PC-1", "pest_control"),          # duplicate lead_id
        day_row("IB-2", "insurance_broker"),      # same email as PC-1, other case
        day_row("BO-1", "bookkeeping"), day_row("PC-2", "pest_control"), day_row("CL-1", "cleaning")])
    ids = tmp_path / "ai_ids.json"
    ids.write_text(json.dumps(IDS))
    return master, [f1, f2], ids


def esp(email):
    return {"google.test": "google", "ms.test": "microsoft", "other.test": "other"}[email.split("@")[1].lower()]


NOW = sd._local(date(2026, 10, 7), 21, 0)   # Wed evening -> send day Thu -> Fri + Mon slots


class Recorder(object):
    """leads/add answers with counts; leads/list and GET leads/{id} serve what was added.
    existing: {campaign_id: [lead, ...]} already in Instantly (copied, never mutated);
    an added email that already sits anywhere in the workspace is skipped, like
    skip_if_in_workspace. statuses: {campaign_id: status} for GET campaigns/{id} (default 0 draft).
    on_add(recorder, body) runs before each leads/add."""

    def __init__(self, existing=None, statuses=None, on_add=None):
        self.calls = []
        self.added = {cid: [dict(l) for l in ls] for cid, ls in (existing or {}).items()}
        self.statuses, self.on_add, self.n = dict(statuses or {}), on_add, 0

    def __call__(self, method, path, body=None, tok=None):
        self.calls.append((method, path, body))
        if method == "POST" and path == "leads/add":
            if self.on_add:
                self.on_add(self, body)
            in_ws = {l["email"].lower() for ls in self.added.values() for l in ls}
            up = 0
            for l in body["leads"]:
                if l["email"].lower() in in_ws:
                    continue
                self.n += 1
                lid = "I-%s-%d" % (body["campaign_id"], len(self.added.get(body["campaign_id"], [])))
                self.added.setdefault(body["campaign_id"], []).append(
                    {"id": lid, "email": l["email"], "campaign": body["campaign_id"],
                     "timestamp_created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                     "payload": dict(l["custom_variables"], firstName=l["first_name"])})
                up += 1
            return {"status": "success", "total_sent": len(body["leads"]), "leads_uploaded": up,
                    "skipped_count": len(body["leads"]) - up, "invalid_email_count": 0}
        if method == "POST" and path == "leads/list":
            return {"items": [dict(l) for l in self.added.get(body.get("campaign"), [])], "next_starting_after": None}
        if method == "GET" and path.startswith("campaigns/"):
            cid = path.split("/", 1)[1]
            return {"id": cid, "status": self.statuses.get(cid, 0)}
        if method == "GET" and path.startswith("leads/"):
            lid = path.split("/", 1)[1]
            return dict(next(l for ls in self.added.values() for l in ls if l["id"] == lid))
        raise AssertionError("unexpected %s %s" % (method, path))

    def writes(self):
        return [c for c in self.calls if not (c[1] == "leads/list" or c[0] == "GET")]


def reads_only(method, path, body=None, tok=None):
    """A dry-run may GET the campaigns (status check) and nothing else."""
    if method == "GET" and path.startswith("campaigns/"):
        return {"id": path.split("/", 1)[1], "status": 0}
    raise AssertionError("dry-run must only GET campaigns, got %s %s" % (method, path))


def no_calls(*a, **k):
    raise AssertionError("dry-run must not call Instantly")


def test_dry_run_mapping_dedupe_filters_and_slot_vars(files, capsys):
    master, days, ids = files
    s = ip.push_ai_agents("tok", [str(p) for p in days], dry_run=True, ids_file=str(ids), call_fn=reads_only, now=NOW,
                          free_fn=lambda now: None, master_path=master, esp=esp)
    assert s["per_file"] == {str(days[0]): 7, str(days[1]): 5}
    assert s["per_campaign"] == {"pest_control_ai": 2, "msp_ai": 1, "bookkeeping_ai": 1}
    assert s["skipped"] == {"other niche (recruiting)": 1, "other niche (cleaning)": 1, "skip tier": 1,
                            "empty personalization": 1, "no email in master": 1, "duplicate": 2, "esp microsoft": 1}
    assert s["source"] == "fallback" and s["send_day"] == "2026-10-08"
    pest = s["leads"]["pest_control_ai"]
    assert [l["email"] for l in pest] == ["a@google.test", "h@google.test"]   # first occurrence kept, file order
    for ls in s["leads"].values():
        for l in ls:
            cv = l["custom_variables"]
            assert set(cv) == {"personalization", "specialty", "lead_id", "mv_result", "slot1", "slot2", "slot_date"}
            assert cv["slot1"].startswith("Friday at ") and cv["slot2"].startswith("Monday at ") and cv["slot2"].endswith(" CT")
            assert cv["slot_date"] == "2026-10-08"
    assert pest[0]["company_name"] == "Acme Pest Control"
    out = capsys.readouterr().out
    assert "dry-run: nothing written" in out and out.count("sample body") == 2


def test_live_push_uses_bulk_add_records_and_reads_back(files, tmp_path, capsys):
    master, days, ids = files
    rec = Recorder()
    s = ip.push_ai_agents("tok", [str(p) for p in days], dry_run=False, ids_file=str(ids), call_fn=rec, now=NOW,
                          free_fn=lambda now: None, master_path=master, esp=esp, sleep=lambda x: None,
                          record_dir=tmp_path / "logs")
    writes = rec.writes()
    assert writes and all(c[0] == "POST" and c[1] == "leads/add" for c in writes)
    assert not any("activate" in c[1] for c in rec.calls)
    bodies = {c[2]["campaign_id"]: c[2] for c in writes}
    assert set(bodies) == {IDS["pest_control_ai"], IDS["msp_ai"], IDS["bookkeeping_ai"]}
    for b in bodies.values():
        assert b["skip_if_in_workspace"] is True and 1 <= len(b["leads"]) <= ip.BULK_ADD_MAX
        assert all(l["custom_variables"]["slot1"] and l["custom_variables"]["slot2"] for l in b["leads"])
    assert sum(r["leads_uploaded"] for r in s["results"]) == 4
    # the push record: every email/lead_id per campaign, the API counts, then the Instantly ids found
    record = json.loads(open(s["record"]).read())
    assert s["record"].startswith(str(tmp_path / "logs" / "push_ai_"))
    pest = record["campaigns"]["pest_control_ai"]
    assert pest["campaign_id"] == IDS["pest_control_ai"]
    assert pest["sent"] == [{"email": "a@google.test", "lead_id": "PC-1"}, {"email": "h@google.test", "lead_id": "PC-2"}]
    assert pest["results"][0]["leads_uploaded"] == 2 and pest["results"][0]["total_sent"] == 2
    assert pest["instantly_ids"] == {"a@google.test": "I-cid-pest_control_ai-0", "h@google.test": "I-cid-pest_control_ai-1"}
    assert pest["verified_lead"]["variables"]["slot1"].startswith("Friday at ")
    assert set(record["campaigns"]) == {"pest_control_ai", "msp_ai", "bookkeeping_ai"}
    # one GET leads/{id} per campaign with pushed leads, and the six campaign status GETs
    assert len([c for c in rec.calls if c[0] == "GET" and c[1].startswith("leads/")]) == 3
    assert len([c for c in rec.calls if c[0] == "GET" and c[1].startswith("campaigns/")]) == 6
    assert record["push_started_at"].endswith("Z") and pest["pre_existing"] == []
    assert pest["not_created_by_this_push"] == {}
    out = capsys.readouterr().out
    assert "push record:" in out and "MISSING" not in out and "NOT activated" in out


def test_limit_per_campaign_keeps_the_first_n(files, tmp_path):
    master, days, ids = files
    rec = Recorder()
    s = ip.push_ai_agents("tok", [str(p) for p in days], dry_run=False, ids_file=str(ids), call_fn=rec, now=NOW,
                          free_fn=lambda now: None, master_path=master, esp=esp, sleep=lambda x: None,
                          limit_per_campaign=1, record_dir=tmp_path)
    assert s["per_campaign"] == {"pest_control_ai": 1, "msp_ai": 1, "bookkeeping_ai": 1}
    pest = [c[2] for c in rec.writes() if c[2]["campaign_id"] == IDS["pest_control_ai"]]
    assert [l["email"] for l in pest[0]["leads"]] == ["a@google.test"]
    assert s["skipped"]["over --limit-per-campaign 1"] == 1


def test_dry_run_with_limit_writes_no_record(files, tmp_path):
    master, days, ids = files
    s = ip.push_ai_agents("tok", [str(p) for p in days], dry_run=True, ids_file=str(ids), call_fn=reads_only, now=NOW,
                          free_fn=lambda now: None, master_path=master, esp=esp, limit_per_campaign=1, record_dir=tmp_path)
    assert s["per_campaign"]["pest_control_ai"] == 1 and "record" not in s
    assert not list(tmp_path.glob("push_ai_*.json"))


def test_live_push_needs_ids_file(files, tmp_path):
    master, days, _ = files
    with pytest.raises(SystemExit):
        ip.push_ai_agents("tok", [str(p) for p in days], dry_run=False, ids_file=str(tmp_path / "missing.json"),
                          call_fn=no_calls, now=NOW, free_fn=lambda now: None, master_path=master, esp=esp)


def test_dry_run_tolerates_missing_ids_file(files, tmp_path):
    master, days, _ = files
    s = ip.push_ai_agents("tok", [str(p) for p in days], dry_run=True, ids_file=str(tmp_path / "missing.json"),
                          call_fn=reads_only, now=NOW, free_fn=lambda now: None, master_path=master, esp=esp)
    assert s["ids"]["msp_ai"] == "<missing:msp_ai>"


def test_slot_error_stops_the_push(files):
    master, days, ids = files
    only_friday = [g.isoformat() for g in sd.grid_for([date(2026, 10, 9)])]   # Mon missing -> no slot2 day
    with pytest.raises(SystemExit):
        ip.push_ai_agents("tok", [str(p) for p in days], dry_run=False, ids_file=str(ids), call_fn=no_calls, now=NOW,
                          free_fn=lambda now: only_friday, master_path=master, esp=esp)


def test_empty_ghl_answer_uses_the_grid_with_a_banner(files, capsys):
    master, days, ids = files
    s = ip.push_ai_agents("tok", [str(p) for p in days], dry_run=True, ids_file=str(ids), call_fn=reads_only, now=NOW,
                          free_fn=lambda now: [], master_path=master, esp=esp)
    assert s["source"] == "fallback_empty"
    assert "GHL CALENDAR NOT READ (GHL answered with no free slot" in capsys.readouterr().out


# ---------------------------------------------------------------- old offer
def test_old_single_file_push_unchanged(tmp_path, monkeypatch):
    (tmp_path / "output" / "FINAL").mkdir(parents=True)
    write_csv(tmp_path / "output" / "FINAL" / "MASTER_for_sheets.csv", ["lead_id", "email", "first_name", "last_name", "company_name", "mv_result"], [
        {"lead_id": "RE-1", "email": "r1@google.test", "first_name": "Ann", "last_name": "B", "company_name": "Rec Inc", "mv_result": "ok"},
        {"lead_id": "RE-2", "email": "r2@ms.test", "first_name": "Bo", "last_name": "C", "company_name": "R2", "mv_result": "ok"},
        {"lead_id": "PC-1", "email": "p@google.test", "first_name": "Cy", "last_name": "D", "company_name": "P", "mv_result": "ok"}])
    old_ids = {k: "old-%s" % k for k in ip.CAMPAIGNS}
    (tmp_path / "instantly_campaigns.json").write_text(json.dumps(old_ids))
    day = write_csv(tmp_path / "day.csv", DAY_FIELDS, [
        dict(day_row("RE-1", "recruiting"), specialty="IT"), day_row("RE-2", "recruiting"), day_row("PC-1", "pest_control")])
    monkeypatch.setattr(ip, "ROOT", tmp_path)
    import personalize.esp as pe
    monkeypatch.setattr(pe, "prime", lambda emails: 0)
    monkeypatch.setattr(pe, "esp_of", esp)
    monkeypatch.setattr(pe, "save", lambda: None)
    calls = []
    monkeypatch.setattr(ip, "call", lambda m, p, b=None, tok=None: calls.append((m, p, b)) or {})
    ip.push("tok", str(day))
    assert calls == [("POST", "leads", {
        "campaign": "old-recruiting_reactivation", "email": "r1@google.test", "first_name": "Pat", "last_name": "B",
        "company_name": "Acme Pest Control", "personalization": "Hey Pat, saw that you do X.", "skip_if_in_workspace": True,
        "custom_variables": {"personalization": "Hey Pat, saw that you do X.", "specialty": "IT", "lead_id": "RE-1", "mv_result": "ok"}})]


@pytest.fixture
def guarded(monkeypatch):
    """Every live entry point raises: a refused CLI combination must exit before any of them."""
    def boom(*a, **k):
        raise AssertionError("must not be reached")
    for name in ("key", "call", "setup", "activate", "check", "push", "push_ai_agents"):
        monkeypatch.setattr(ip, name, boom)


@pytest.mark.parametrize("argv", [
    ["--push", "a.csv", "b.csv"],                       # old offer takes one file
    ["--push", "a.csv", "--dry-run"],                   # no dry-run on the old path (it would push live)
    ["--push", "a.csv", "--offer", "ai_agents", "--activate"],
    ["--offer", "ai_agents"],
    ["--push", "f.csv", "--offer", "ai_agents", "--dry-run", "--setup"],
    ["--push", "f.csv", "--offer", "ai_agents", "--setup"],
    ["--offer", "ai_agents", "--setup"],
    ["--setup", "--dry-run"],
    ["--setup", "--push", "f.csv", "--dry-run"],
    ["--activate", "--dry-run"],
    ["--push", "f.csv", "--offer", "ai_agents", "--dry-run", "--activate"],
    ["--push", "f.csv", "--limit-per-campaign", "1"],   # limit only exists on the ai_agents path
    ["--push", "f.csv", "--offer", "ai_agents", "--limit-per-campaign", "0"],
    ["--push", "f.csv", "--allow-active"],              # --allow-active only exists on the ai_agents path
])
def test_cli_rejects_unsafe_combinations_before_key_or_call(argv, guarded):
    with pytest.raises(SystemExit) as e:
        ip.main(argv)
    assert e.value.code == 2


def test_cli_script_entry_point_still_refuses(monkeypatch):
    import urllib.request

    def no_network(*a, **k):
        raise AssertionError("network reached")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)   # the fresh runpy namespace shares this module
    monkeypatch.setattr(sys, "argv", ["instantly_push.py", "--push", "x.csv", "--offer", "ai_agents", "--dry-run", "--setup"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(HERE), run_name="__main__")
    assert e.value.code == 2


def test_cli_passes_limit_to_the_ai_push(monkeypatch):
    got = {}
    monkeypatch.setattr(ip, "key", lambda: "tok")
    monkeypatch.setattr(ip, "push_ai_agents", lambda tok, files, **kw: got.update(kw, files=files))
    ip.main(["--push", "f.csv", "--offer", "ai_agents", "--dry-run", "--limit-per-campaign", "1"])
    assert got == {"files": ["f.csv"], "dry_run": True, "ids_file": None, "limit_per_campaign": 1,
                   "allow_active": False}


# ---------------------------------------------------------------- rollback list, record timing, status check
def _live(files, tmp_path, rec, **kw):
    master, days, ids = files
    return ip.push_ai_agents("tok", [str(p) for p in days], dry_run=False, ids_file=str(ids), call_fn=rec, now=NOW,
                             free_fn=lambda now: None, master_path=master, esp=esp, sleep=lambda x: None,
                             record_dir=tmp_path / "logs", **kw)


OLD_A = {"id": "OLD-A", "email": "a@google.test", "campaign": IDS["pest_control_ai"],
         "timestamp_created": "2026-09-01T10:00:00.000Z", "payload": {"personalization": "older lead"}}


def test_rollback_list_holds_only_leads_this_push_created(files, tmp_path):
    # pest_control_ai already holds OLD-A (a@); the push re-sends a@ (skipped, in workspace) and h@ (new)
    stale_b = {"id": "STALE-B", "email": "b@google.test", "campaign": IDS["msp_ai"],
               "timestamp_created": "2020-01-01T00:00:00Z", "payload": {}}

    def on_add(r, body):   # a lead the pre-push listing missed: new id, but created long before the push
        if body["campaign_id"] == IDS["msp_ai"] and not any(l["id"] == "STALE-B" for l in r.added.get(IDS["msp_ai"], [])):
            r.added.setdefault(IDS["msp_ai"], []).append(dict(stale_b))
    existing = {IDS["pest_control_ai"]: [OLD_A]}
    rec = Recorder(existing=existing, on_add=on_add)
    s = _live(files, tmp_path, rec)
    assert existing == {IDS["pest_control_ai"]: [OLD_A]}   # the fake copies, never mutates
    record = json.loads(open(s["record"]).read())
    pest = record["campaigns"]["pest_control_ai"]
    assert pest["pre_existing"] == [{"id": "OLD-A", "email": "a@google.test"}]
    assert pest["instantly_ids"] == {"h@google.test": "I-cid-pest_control_ai-1"}
    assert pest["not_created_by_this_push"] == {"a@google.test": {"id": "OLD-A", "reason": "in the campaign before this push"}}
    msp = record["campaigns"]["msp_ai"]
    assert msp["instantly_ids"] == {}
    assert msp["not_created_by_this_push"]["b@google.test"]["id"] == "STALE-B"
    assert "before the push start" in msp["not_created_by_this_push"]["b@google.test"]["reason"]
    assert record["campaigns"]["bookkeeping_ai"]["instantly_ids"] == {"e@other.test": "I-cid-bookkeeping_ai-0"}


def test_record_with_pre_existing_is_written_and_printed_before_the_first_add(files, tmp_path, capsys):
    seen = []

    def on_add(r, body):
        if not seen:
            out = capsys.readouterr().out
            assert "push record (written before the first add): " in out
            found = list((tmp_path / "logs").glob("push_ai_*.json"))
            assert len(found) == 1
            seen.append(json.loads(found[0].read_text()))
        if len(seen) == 1 and body["campaign_id"] == IDS["msp_ai"]:
            seen.append("crash")
            raise RuntimeError("network died mid-push")
    old_z = {"id": "OLD-Z", "email": "z@other.test", "campaign": IDS["bookkeeping_ai"],
             "timestamp_created": "2026-09-01T10:00:00Z", "payload": {}}
    rec = Recorder(existing={IDS["pest_control_ai"]: [OLD_A], IDS["bookkeeping_ai"]: [old_z]}, on_add=on_add)
    with pytest.raises(RuntimeError):
        _live(files, tmp_path, rec)   # bookkeeping_ai is added first, then msp_ai crashes
    first = seen[0]
    assert first["push_started_at"] and set(first["campaigns"]) == {"pest_control_ai", "msp_ai", "bookkeeping_ai"}
    assert first["campaigns"]["pest_control_ai"]["pre_existing"] == [{"id": "OLD-A", "email": "a@google.test"}]
    # crashed push: rollback = ids in the campaign now minus pre_existing, emails from `sent`
    crashed = json.loads(next((tmp_path / "logs").glob("push_ai_*.json")).read_text())
    bo = crashed["campaigns"]["bookkeeping_ai"]
    assert bo["pre_existing"] == [{"id": "OLD-Z", "email": "z@other.test"}]
    now_in = rec("POST", "leads/list", {"campaign": IDS["bookkeeping_ai"]})["items"]
    assert {l["id"] for l in now_in} == {"OLD-Z", "I-cid-bookkeeping_ai-1"}
    created, not_created = ip.created_by_this_push(now_in, {l["email"] for l in bo["sent"]},
                                                   {p["id"] for p in bo["pre_existing"]}, crashed["push_started_at"])
    assert created == {"e@other.test": "I-cid-bookkeeping_ai-1"} and not_created == {}
    assert crashed["campaigns"]["msp_ai"]["sent"] and "instantly_ids" not in crashed["campaigns"]["msp_ai"]


@pytest.mark.parametrize("status", [1, None])
def test_live_push_refuses_an_active_or_unreadable_target_campaign(files, tmp_path, capsys, status):
    rec = Recorder(statuses={IDS["msp_ai"]: status})
    with pytest.raises(SystemExit) as e:
        _live(files, tmp_path, rec)
    assert e.value.code == 2 and not rec.writes()
    assert not list(tmp_path.glob("**/push_ai_*.json"))
    out = capsys.readouterr().out
    assert "refused:" in out and "--allow-active" in out
    assert all(ck in out for ck in sd.AI_CAMPAIGN_KEYS)   # all six statuses printed


def test_allow_active_and_non_target_active_campaigns_go_ahead(files, tmp_path, capsys):
    rec = Recorder(statuses={IDS["msp_ai"]: 1})
    s = _live(files, tmp_path, rec, allow_active=True)
    assert rec.writes() and "going ahead because --allow-active" in capsys.readouterr().out
    rec2 = Recorder(statuses={IDS["landscaping_ai"]: 1})   # active, but this push sends it nothing
    _live(files, tmp_path, rec2)
    assert rec2.writes()
    assert json.loads(open(s["record"]).read())["allow_active"] is True


def test_dry_run_prints_the_six_statuses_and_warns_on_active(files, capsys):
    master, days, ids = files

    def active_msp(method, path, body=None, tok=None):
        r = reads_only(method, path, body, tok)
        return dict(r, status=1) if path == "campaigns/" + IDS["msp_ai"] else r
    s = ip.push_ai_agents("tok", [str(p) for p in days], dry_run=True, ids_file=str(ids), call_fn=active_msp, now=NOW,
                          free_fn=lambda now: None, master_path=master, esp=esp)
    out = capsys.readouterr().out
    assert s["campaign_status"]["msp_ai"] == 1 and s["campaign_status"]["pest_control_ai"] == 0
    assert "A live push would be refused (exit 2)" in out and "dry-run: nothing written" in out
    assert "1 ACTIVE" in out and out.count("0 draft") == 5
