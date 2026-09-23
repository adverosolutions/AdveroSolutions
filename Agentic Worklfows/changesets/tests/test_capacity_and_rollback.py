"""GOL-8, GOL-9, GOL-17, SAF-10 and GOL-20 items 8 and 9.

Every Instantly call goes through one httpx.MockTransport (FakeInstantly) that
keeps campaign and account state the way the API does, so the tests assert the
exact method, path and body that would be sent live. MODE stays shadow unless
a test takes the live_mode fixture, and even then nothing leaves the process.
"""
import copy
import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from shared import job_log
from shared.instantly import Instantly
from changesets import rollback as R
from changesets.capacity import apply_capacity as cap
from changesets.capacity import apply_promotion as ap
from changesets.inbox_actions import apply_inbox_actions as A

NOW = datetime(2026, 10, 11, 14, 0, tzinfo=timezone.utc)
STAMP = "20261011T140000Z"
CR = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"      # cleaning_reactivation
CT = "f347604e-48c7-4813-831c-dc7b9d4b50ae"      # cleaning_trigger
LIVE = ["a1@d1.com", "a2@d1.com", "b1@d2.com"]
NEW = ["n1@d3.com", "n2@d3.com"]


def account(email, status=1, warm_days=25, score=100, warmup_status=1, setup_pending=False):
    started = (NOW - timedelta(days=warm_days)).isoformat().replace("+00:00", "Z")
    return {"email": email, "status": status, "warmup_status": warmup_status,
            "stat_warmup_score": score, "setup_pending": setup_pending,
            "timestamp_warmup_start": started, "daily_limit": 25}


class FakeInstantly(object):
    def __init__(self, campaigns=None, accounts=None, fail_patch=None):
        self.campaigns = copy.deepcopy(campaigns or {
            CR: {"id": CR, "name": "2026 Cleaning - Client Reactivation", "status": 1,
                 "email_list": list(LIVE), "daily_limit": 50, "pl_value": 6000},
            CT: {"id": CT, "name": "2026 Cleaning - Trigger Outbound", "status": 1,
                 "email_list": list(LIVE), "daily_limit": 50, "pl_value": 7500},
        })
        self.accounts = dict((a["email"], a) for a in (accounts or
                             [account(e) for e in LIVE + NEW]))
        self.requests = []
        self.fail_patch = dict(fail_patch or {})     # cid -> (status, landed)

    def __call__(self, request):
        self.requests.append(request)
        method, path = request.method, request.url.path
        if method == "GET" and path == "/api/v2/campaigns":
            return httpx.Response(200, json={"items": list(self.campaigns.values())})
        if method == "GET" and path == "/api/v2/accounts":
            return httpx.Response(200, json={"items": list(self.accounts.values())})
        if path.startswith("/api/v2/campaigns/"):
            cid = path.rsplit("/", 1)[1]
            if method == "GET":
                return httpx.Response(200, json=self.campaigns[cid])
            if method == "PATCH":
                body = json.loads(request.content)
                if cid in self.fail_patch:
                    status, landed = self.fail_patch.pop(cid)
                    if landed:
                        self.campaigns[cid].update(body)
                    return httpx.Response(status, text="upstream timeout")
                self.campaigns[cid].update(body)
                return httpx.Response(200, json=self.campaigns[cid])
        if path.startswith("/api/v2/accounts/"):
            rest = path[len("/api/v2/accounts/"):]
            if method == "GET":
                return httpx.Response(200, json=self.accounts[rest])
            if method == "POST" and rest.endswith("/pause"):
                email = rest[: -len("/pause")]
                self.accounts[email]["status"] = 2
                return httpx.Response(200, json=self.accounts[email])
        return httpx.Response(404, text="unexpected %s %s" % (method, path))

    @property
    def writes(self):
        return [r for r in self.requests if r.method != "GET"]

    def client(self):
        return Instantly(api_key="test-key", transport=httpx.MockTransport(self), sleep=lambda s: None)


def lines():
    out = []
    return out, out.append


# ============================================================ GOL-20 item 8
def test_pause_account_sends_no_body_and_url_encodes_the_email(tmp_env, live_mode):
    """config/instantly_api_contract.md: path parameter only, URL-encoded, no
    request body at all. It used to send `{}` and a raw `@`."""
    fake = FakeInstantly(accounts=[account("lorenzo+x@myadvero.com")])
    fake.client().pause_account("lorenzo+x@myadvero.com")
    req = fake.requests[0]
    assert req.method == "POST"
    assert req.url.raw_path == b"/api/v2/accounts/lorenzo%2Bx%40myadvero.com/pause"
    assert req.content == b""
    assert "content-type" not in req.headers
    assert fake.accounts["lorenzo+x@myadvero.com"]["status"] == 2


def test_pause_account_is_still_guarded_in_shadow(tmp_env, shadow_mode):
    fake = FakeInstantly()
    res = fake.client().pause_account("a1@d1.com")
    assert res["shadow"] is True and fake.requests == []


# ================================================================ rollback
def test_a_rollback_point_can_only_name_patchable_fields():
    with pytest.raises(ValueError):
        R.build_point("capacity", "apply", {"id": CR}, ["status"], NOW, CR)
    assert set(["email_list", "daily_limit", "sequences"]) <= set(R.PATCHABLE_CAMPAIGN_FIELDS)
    assert "status" not in R.PATCHABLE_CAMPAIGN_FIELDS


# ========================================================= GOL-8 capacity
def plan_file(tmp_path, example=False, adds=None, limits=None, total=None, option="B"):
    limits = limits or {"cleaning_reactivation": 100, "cleaning_trigger": 80}
    doc = {"example": example, "option": option,
           "expected_total_daily_limit": total if total is not None else sum(limits.values()),
           "campaigns": {}}
    ids = {"cleaning_reactivation": CR, "cleaning_trigger": CT}
    for key, limit in limits.items():
        doc["campaigns"][key] = {"campaign_id": ids[key], "add_inboxes": list(adds if adds is not None else NEW),
                                 "daily_limit": limit}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    return str(path)


def run_cap(fake, argv, tmp_path, now=NOW):
    out, say = lines()
    code = cap.main(argv, client=fake.client(), now=now, out=say,
                    backup_dir=str(tmp_path / "backups"), dryrun_dir=str(tmp_path / "dry"))
    return code, out


def test_the_example_file_is_marked_and_never_applied(tmp_env, live_mode, tmp_path):
    with open(cap.EXAMPLE_PATH) as fh:
        doc = json.load(fh)
    assert doc["example"] is True and "EXAMPLE ONLY" in doc["_about"]
    assert "NOT Option A or Option B" in doc["_about"]
    doc_problems = cap.load_input(cap.EXAMPLE_PATH)[1]
    assert doc_problems == []                     # well-formed, so it shows the shape truthfully
    fake = FakeInstantly()
    code, out = run_cap(fake, ["--input", cap.EXAMPLE_PATH, "--campaign", "cleaning_reactivation",
                               "--apply", "--yes"], tmp_path)
    assert code == cap.EXIT_REFUSED
    assert fake.requests == [] and not (tmp_path / "backups").exists()
    assert any("example file is never applied" in l for l in out)


def test_capacity_input_is_validated_before_anything_is_read(tmp_env, shadow_mode, tmp_path):
    fake = FakeInstantly()
    path = plan_file(tmp_path, total=999)
    code, out = run_cap(fake, ["--input", path], tmp_path)
    assert code == cap.EXIT_INVALID and fake.requests == []
    assert any("add up to 180" in l for l in out)
    doc = json.loads(open(path).read())
    doc["expected_total_daily_limit"] = 180
    doc["campaigns"]["cleaning_reactivation"]["campaign_id"] = CT
    open(path, "w").write(json.dumps(doc))
    code, out = run_cap(fake, ["--input", path], tmp_path)
    assert code == cap.EXIT_INVALID and any("does not match config/ids.json" in l for l in out)


def test_capacity_dry_run_reads_only_and_writes_nothing_real(tmp_env, shadow_mode, tmp_path):
    fake = FakeInstantly()
    code, out = run_cap(fake, ["--input", plan_file(tmp_path)], tmp_path)
    assert code == 0, out
    assert fake.writes == []
    assert not (tmp_path / "backups").exists()
    assert sorted(os.listdir(str(tmp_path / "dry"))) == [
        "capacity_%s_%s.dryrun.json" % (CR, STAMP), "capacity_%s_%s.dryrun.json" % (CT, STAMP)]
    text = "\n".join(out)
    assert "+ n1@d3.com" in text and "daily_limit: 50 -> 100" in text
    assert not job_log.job_log_path().exists()                  # scratch log only


def test_capacity_refuses_an_inbox_that_is_missing_or_not_warmed(tmp_env, live_mode, tmp_path):
    accounts = [account(e) for e in LIVE] + [
        account("cold@d3.com", warm_days=9), account("sick@d4.com", score=91),
        account("paused@d5.com", status=2), account("nowarm@d6.com", warmup_status=0)]
    fake = FakeInstantly(accounts=accounts)
    adds = ["cold@d3.com", "sick@d4.com", "paused@d5.com", "nowarm@d6.com", "ghost@d7.com"]
    code, out = run_cap(fake, ["--input", plan_file(tmp_path, adds=adds), "--campaign",
                               "cleaning_reactivation", "--apply", "--yes"], tmp_path)
    assert code == cap.EXIT_INVALID
    assert fake.writes == [] and not (tmp_path / "backups").exists()
    text = "\n".join(out)
    assert "cold@d3.com has warmed 9.0 days, under the 21-day minimum" in text
    assert "sick@d4.com warm-up score 91 is under 98.0" in text
    assert "paused@d5.com is not enabled" in text
    assert "nowarm@d6.com has no running warm-up" in text
    assert "ghost@d7.com is not an Instantly account" in text


def test_capacity_refuses_a_fourth_inbox_on_one_domain(tmp_env, live_mode, tmp_path):
    accounts = [account(e) for e in LIVE + ["a3@d1.com", "a4@d1.com"]]
    fake = FakeInstantly(accounts=accounts)
    code, out = run_cap(fake, ["--input", plan_file(tmp_path, adds=["a3@d1.com", "a4@d1.com"]),
                               "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)
    assert code == cap.EXIT_INVALID and fake.writes == []
    assert any("d1.com would have 4 inboxes" in l for l in out)


def test_capacity_apply_reapply_restore_end_to_end(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    path = plan_file(tmp_path)
    argv = ["--input", path, "--campaign", "cleaning_reactivation", "--apply", "--yes"]
    code, out = run_cap(fake, argv, tmp_path)
    assert code == 0, out
    patches = [r for r in fake.writes]
    assert len(patches) == 1
    assert patches[0].method == "PATCH" and patches[0].url.path == "/api/v2/campaigns/%s" % CR
    assert json.loads(patches[0].content) == {"email_list": LIVE + NEW, "daily_limit": 100}
    assert fake.campaigns[CT]["email_list"] == LIVE                 # one campaign at a time
    point = tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))
    assert os.listdir(str(tmp_path / "backups")) == [point.name]
    saved = json.loads(point.read_text())
    assert saved["_rollback_point"]["fields"] == ["daily_limit", "email_list"]
    assert saved["email_list"] == LIVE and saved["daily_limit"] == 50
    with open(job_log.job_log_path()) as fh:
        assert "capacity_oct11_apply,applied" in fh.read()

    # safe re-run: live already matches, nothing sent, nothing written
    n = len(fake.requests)
    code, out = run_cap(fake, argv, tmp_path, now=NOW + timedelta(hours=1))
    assert code == 0 and "live already matches" in "\n".join(out)
    assert [r.method for r in fake.requests[n:]] == ["GET", "GET"]   # accounts, campaign
    assert os.listdir(str(tmp_path / "backups")) == [point.name]

    # restore puts BOTH fields back, and only those fields
    n = len(fake.requests)
    code, out = run_cap(fake, ["--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                        tmp_path, now=NOW + timedelta(hours=2))
    assert code == 0, out
    restore_writes = [r for r in fake.requests[n:] if r.method != "GET"]
    assert len(restore_writes) == 1
    assert json.loads(restore_writes[0].content) == {"daily_limit": 50, "email_list": LIVE}
    assert fake.campaigns[CR]["email_list"] == LIVE and fake.campaigns[CR]["daily_limit"] == 50
    assert any(n_.endswith(".prerestore.json") for n_ in os.listdir(str(tmp_path / "backups")))
    # restoring twice is a no-op
    n = len(fake.requests)
    code, out = run_cap(fake, ["--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                        tmp_path, now=NOW + timedelta(hours=3))
    assert code == 0 and [r.method for r in fake.requests[n:]] == ["GET"]


def test_capacity_patches_only_daily_limit_when_the_inboxes_are_already_in(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    fake.campaigns[CR]["email_list"] = LIVE + NEW
    code, out = run_cap(fake, ["--input", plan_file(tmp_path), "--campaign", "cleaning_reactivation",
                               "--apply", "--yes"], tmp_path)
    assert code == 0
    assert [json.loads(r.content) for r in fake.writes] == [{"daily_limit": 100}]
    saved = json.loads((tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))).read_text())
    assert saved["_rollback_point"]["fields"] == ["daily_limit"]


def test_capacity_restore_in_shadow_and_of_the_wrong_file_writes_nothing(tmp_env, shadow_mode, tmp_path):
    fake = FakeInstantly()
    good = R.write_point(str(tmp_path), "capacity_%s_x" % CR,
                         R.build_point("capacity", "apply", fake.campaigns[CR], ["daily_limit"], NOW, CR,
                                       after={"daily_limit": 100}))
    code, out = run_cap(fake, ["--restore", good, "--campaign", "cleaning_reactivation", "--yes"], tmp_path)
    assert code == cap.EXIT_REFUSED and fake.requests == []
    assert not (tmp_path / "backups").exists()
    # the right script's point for another campaign
    code, out = run_cap(fake, ["--restore", good, "--campaign", "cleaning_trigger", "--yes"], tmp_path)
    assert code == cap.EXIT_INVALID and "different campaign" in "\n".join(out)
    assert fake.requests == []


def test_capacity_timeout_that_landed_keeps_the_rollback_point(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly(fail_patch={CR: (504, True)})
    code, out = run_cap(fake, ["--input", plan_file(tmp_path), "--campaign", "cleaning_reactivation",
                               "--apply", "--yes"], tmp_path)
    assert code == cap.EXIT_API
    assert [r.method for r in fake.writes] == ["PATCH"]             # never retried
    assert os.listdir(str(tmp_path / "backups")) == ["capacity_%s_%s.json" % (CR, STAMP)]
    assert any("LANDED" in l for l in out)


# ======================================================= promotion (GOL-9)
def promo_record(tmp_path, campaign_id=CR, remaining=None, name="promo.json"):
    record = {
        "action": "promote_insurance", "campaign_id": campaign_id,
        "campaign_key": R.campaign_key_for(campaign_id), "campaign_name": "x", "reason": "test",
        "remove": "a1@d1.com", "promote": "n1@d3.com",
        "current_email_list": list(LIVE),
        "proposed_email_list": sorted(["a2@d1.com", "b1@d2.com", "n1@d3.com"]),
        "remaining_campaigns": remaining or [],
        "promote_health": {"warmup_health": 100, "analytics_missing": False, "flags": []},
    }
    path = tmp_path / name
    path.write_text(json.dumps(record))
    return str(path)


def run_promo(fake, argv, tmp_path, now=NOW):
    return ap.main(argv, client=fake.client(), now=now, backup_dir=str(tmp_path / "backups"),
                   dryrun_dir=str(tmp_path / "dry"))


def test_promotion_dry_run_writes_no_backup_and_no_real_log(tmp_env, shadow_mode, tmp_path, capsys):
    """SAF-10: every dry-run wrote an unsuffixed campaign_<id>_<ts>.json into
    changesets/backups/, next to the real rollback points."""
    fake = FakeInstantly()
    assert run_promo(fake, ["--changeset", promo_record(tmp_path)], tmp_path) == 0
    assert fake.writes == []
    assert not (tmp_path / "backups").exists()
    assert os.listdir(str(tmp_path / "dry")) == ["promotion_%s_%s.dryrun.json" % (CR, STAMP)]
    assert not job_log.job_log_path().exists()


def test_promotion_dry_run_and_apply_together_is_refused(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    assert run_promo(fake, ["--changeset", promo_record(tmp_path), "--dry-run", "--apply", "--yes"],
                     tmp_path) == ap.EXIT_REFUSED
    assert fake.requests == []


def test_promotion_apply_reapply_restore(tmp_env, live_mode, tmp_path, capsys):
    fake = FakeInstantly()
    cs = promo_record(tmp_path)
    assert run_promo(fake, ["--changeset", cs, "--apply", "--yes"], tmp_path) == 0
    assert [(r.method, r.url.path, json.loads(r.content)) for r in fake.writes] == [
        ("PATCH", "/api/v2/campaigns/%s" % CR, {"email_list": sorted(["a2@d1.com", "b1@d2.com", "n1@d3.com"])})]
    point = tmp_path / "backups" / ("promotion_%s_%s.json" % (CR, STAMP))
    assert os.listdir(str(tmp_path / "backups")) == [point.name]
    assert json.loads(point.read_text())["email_list"] == LIVE
    # re-apply: live already holds the proposed list
    n = len(fake.requests)
    assert run_promo(fake, ["--changeset", cs, "--apply", "--yes"], tmp_path, now=NOW + timedelta(hours=1)) == 0
    assert all(r.method == "GET" for r in fake.requests[n:])
    assert os.listdir(str(tmp_path / "backups")) == [point.name]
    # restore: email_list only
    n = len(fake.requests)
    assert run_promo(fake, ["--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                     tmp_path, now=NOW + timedelta(hours=2)) == 0
    writes = [r for r in fake.requests[n:] if r.method != "GET"]
    assert [json.loads(r.content) for r in writes] == [{"email_list": LIVE}]
    assert fake.campaigns[CR]["email_list"] == LIVE


def test_promotion_restore_refuses_its_own_dry_run_copy_and_a_phase0_point(tmp_env, live_mode, tmp_path, capsys):
    fake = FakeInstantly()
    assert run_promo(fake, ["--changeset", promo_record(tmp_path)], tmp_path) == 0
    dry = os.path.join(str(tmp_path / "dry"), os.listdir(str(tmp_path / "dry"))[0])
    phase0 = R.write_point(str(tmp_path), "phase0_%s_x" % CR,
                           R.build_point("phase0", "apply", fake.campaigns[CR], ["pl_value"], NOW, CR))
    n = len(fake.requests)
    for path in (dry, phase0):
        assert run_promo(fake, ["--restore", path, "--campaign", "cleaning_reactivation", "--yes"],
                         tmp_path) == ap.EXIT_INVALID
    assert fake.requests[n:] == [] and not (tmp_path / "backups").exists()


def test_the_same_insurance_inbox_can_replace_one_failing_inbox_in_several_campaigns(tmp_env, live_mode, tmp_path):
    """GOL-20 item 9: an inbox that sits in all six campaigns could only be
    replaced in one, because the second change-set saw the insurance inbox
    already sending."""
    fake = FakeInstantly()
    first = promo_record(tmp_path, CR, remaining=["cleaning_trigger"], name="p1.json")
    second = promo_record(tmp_path, CT, remaining=["cleaning_reactivation"], name="p2.json")
    assert run_promo(fake, ["--changeset", first, "--apply", "--yes"], tmp_path) == 0
    assert run_promo(fake, ["--changeset", second, "--apply", "--yes"], tmp_path,
                     now=NOW + timedelta(minutes=5)) == 0
    assert "n1@d3.com" in fake.campaigns[CR]["email_list"] and "n1@d3.com" in fake.campaigns[CT]["email_list"]
    assert "a1@d1.com" not in fake.campaigns[CT]["email_list"]


def test_an_insurance_inbox_sending_for_an_unrelated_campaign_is_still_refused(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    fake.campaigns[CR]["email_list"] = LIVE
    fake.campaigns[CT]["email_list"] = ["n1@d3.com", "b1@d2.com"]    # not a sibling: a1 never there
    other = promo_record(tmp_path, CR, remaining=[], name="p.json")
    assert run_promo(fake, ["--changeset", other, "--apply", "--yes"], tmp_path) == ap.EXIT_INVALID
    assert fake.writes == []
    # listed as a sibling, but the failing inbox is still in it: not a completed swap either
    fake.campaigns[CT]["email_list"] = ["n1@d3.com", "a1@d1.com"]
    sib = promo_record(tmp_path, CR, remaining=["cleaning_trigger"], name="q.json")
    assert run_promo(fake, ["--changeset", sib, "--apply", "--yes"], tmp_path) == ap.EXIT_INVALID
    assert fake.writes == []


# =================================================== inbox actions (GOL-17)
def action(cid, key, before=None, remove="a1@d1.com"):
    before = list(before if before is not None else LIVE)
    return {"system": "instantly", "op": "patch_campaign_email_list", "campaign_key": key,
            "campaign_id": cid, "remove": remove, "add": None, "expected_before": before,
            "expected_after": [e for e in before if e != remove]}


def write_cs(tmp_path, actions, pid="pause_inbox:a1@d1.com", status=None, extra=None):
    p = {"id": pid, "kind": "pause_inbox", "target": "a1@d1.com", "severity": "high", "level": 3,
         "reason": "test", "actions": actions}
    if status:
        p["status"] = status
    p.update(extra or {})
    path = tmp_path / "cs" / "2026-10-11.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"generated_at": NOW.isoformat(), "proposals": [p]}))
    return path


def run_ia(fake, argv, tmp_path, now=NOW):
    out, say = lines()
    code = A.main(argv + ["--backup-dir", str(tmp_path / "backups")], client=fake.client(), out=say,
                  now=now, directory=tmp_path / "cs")
    return code, out


def test_inbox_actions_stop_at_the_first_failed_patch_and_a_rerun_finishes(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly(fail_patch={CR: (502, False)})
    acts = [{"system": "instantly", "op": "pause_account", "email": "a1@d1.com"},
            action(CR, "cleaning_reactivation"), action(CT, "cleaning_trigger")]
    path = write_cs(tmp_path, acts)
    code, out = run_ia(fake, ["--apply", "--id", "pause_inbox:a1@d1.com", "--yes"], tmp_path)
    assert code == A.EXIT_INVALID
    methods = [(r.method, r.url.path) for r in fake.writes]
    # the pause went out (no body, encoded), the first PATCH failed, the second was NEVER sent
    assert methods == [("POST", "/api/v2/accounts/a1@d1.com/pause"), ("PATCH", "/api/v2/campaigns/%s" % CR)]
    assert fake.writes[0].content == b""
    assert fake.campaigns[CT]["email_list"] == LIVE
    text = "\n".join(out)
    assert "STOPPED at the first failed write" in text and "Re-planned from live" in text
    assert "ALREADY DONE" in text                       # the pause, re-planned from live
    assert json.loads(path.read_text())["proposals"][0]["status"] == "apply_failed"
    names = os.listdir(str(tmp_path / "backups"))
    # re-review defect 2: an error never leaves the before-image unrestorable
    assert "inbox_actions_campaign_%s_before_%s.json" % (CR, STAMP) in names
    assert not any(n.endswith((".preapply.json", ".not_applied.json")) for n in names)

    # GOL-17: apply_failed is re-planned, not inherited as a dead end
    code, out = run_ia(fake, ["--apply", "--id", "pause_inbox:a1@d1.com", "--yes"], tmp_path,
                       now=NOW + timedelta(minutes=10))
    assert code == A.EXIT_OK, out
    assert "a1@d1.com" not in fake.campaigns[CR]["email_list"]
    assert "a1@d1.com" not in fake.campaigns[CT]["email_list"]
    assert json.loads(path.read_text())["proposals"][0]["status"] == "applied"


def test_a_patch_that_landed_on_an_earlier_run_is_satisfied_not_blocked(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    fake.campaigns[CR]["email_list"] = [e for e in LIVE if e != "a1@d1.com"]   # landed last time
    write_cs(tmp_path, [action(CR, "cleaning_reactivation"), action(CT, "cleaning_trigger")],
             status="apply_failed")
    code, out = run_ia(fake, ["--apply", "--id", "pause_inbox:a1@d1.com", "--yes"], tmp_path)
    assert code == A.EXIT_OK, out
    assert [(r.method, r.url.path) for r in fake.writes] == [("PATCH", "/api/v2/campaigns/%s" % CT)]
    assert "already applied" in "\n".join(out)


def test_inbox_actions_restore_puts_email_list_back(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    write_cs(tmp_path, [action(CR, "cleaning_reactivation")])
    code, out = run_ia(fake, ["--apply", "--id", "pause_inbox:a1@d1.com", "--yes"], tmp_path)
    assert code == 0, out
    point = tmp_path / "backups" / ("inbox_actions_campaign_%s_before_%s.json" % (CR, STAMP))
    assert point.exists()
    n = len(fake.requests)
    code, out = run_ia(fake, ["--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                       tmp_path, now=NOW + timedelta(hours=1))
    assert code == 0, out
    writes = [r for r in fake.requests[n:] if r.method != "GET"]
    assert [(r.method, r.url.path, json.loads(r.content)) for r in writes] == [
        ("PATCH", "/api/v2/campaigns/%s" % CR, {"email_list": LIVE})]
    assert fake.campaigns[CR]["email_list"] == LIVE


def test_inbox_actions_restore_refuses_in_shadow_and_for_another_campaign(tmp_env, shadow_mode, tmp_path):
    fake = FakeInstantly()
    point = R.write_point(str(tmp_path), "inbox_actions_campaign_%s_before_x" % CR,
                          R.build_point("inbox_actions", "apply", fake.campaigns[CR], ["email_list"], NOW, CR,
                                        after={"email_list": LIVE[1:]}))
    code, out = run_ia(fake, ["--restore", point, "--campaign", "cleaning_reactivation", "--yes"], tmp_path)
    assert code == A.EXIT_REFUSED and fake.requests == []
    code, out = run_ia(fake, ["--restore", point, "--campaign", "cleaning_trigger", "--yes"], tmp_path)
    assert code == A.EXIT_INVALID and fake.requests == []
    assert not (tmp_path / "backups").exists()


def test_the_placement_retest_is_not_run_before_its_not_before(tmp_env, live_mode, tmp_path):
    """jobs/inbox_placement.py stages the re-test with not_before 48 h after
    the pause (M1 L2)."""
    not_before = (NOW + timedelta(hours=47)).isoformat()
    retest = {"system": "instantly", "op": "create_placement_test", "payload": {"name": "x"}}
    write_cs(tmp_path, [retest], pid="retest_placement:2026-10-11", extra={"not_before": not_before})
    fake = FakeInstantly()
    code, out = run_ia(fake, ["--dry-run"], tmp_path)
    assert code == 0 and "not due until %s" % not_before in "\n".join(out)
    code, out = run_ia(fake, ["--apply", "--id", "retest_placement:2026-10-11", "--yes"], tmp_path)
    assert code == A.EXIT_REFUSED and "not due until" in "\n".join(out)
    # after not_before it is planned (and, being manual, only printed)
    code, out = run_ia(fake, ["--apply", "--id", "retest_placement:2026-10-11", "--yes"], tmp_path,
                       now=NOW + timedelta(hours=49))
    assert code == A.EXIT_OK and "manual follow-up" in "\n".join(out)
    assert fake.writes == []
    # an unreadable not_before is refused, not guessed
    write_cs(tmp_path, [retest], pid="retest_placement:2026-10-11", extra={"not_before": "Tuesday"})
    code, out = run_ia(fake, ["--apply", "--id", "retest_placement:2026-10-11", "--yes"], tmp_path,
                       now=NOW + timedelta(days=9))
    assert code == A.EXIT_REFUSED and "refusing to guess" in "\n".join(out)


def test_inbox_actions_dry_run_writes_nothing(tmp_env, shadow_mode, tmp_path):
    fake = FakeInstantly()
    write_cs(tmp_path, [action(CR, "cleaning_reactivation")])
    code, out = run_ia(fake, ["--dry-run"], tmp_path)
    assert code == 0 and fake.writes == []
    assert not (tmp_path / "backups").exists()
    assert not job_log.job_log_path().exists()


def test_a_rollback_point_is_never_overwritten_by_a_write_in_the_same_second(tmp_path):
    first = R.write_point(str(tmp_path), "phase0_%s_%s" % (CR, STAMP),
                          R.build_point("phase0", "apply", {"id": CR, "pl_value": 1}, ["pl_value"], NOW, CR))
    pre = R.write_point(str(tmp_path), "phase0_%s_%s" % (CR, STAMP),
                        R.build_point("phase0", "preapply", {"id": CR, "pl_value": 2}, ["pl_value"], NOW, CR))
    promoted = R.relabel(pre, "apply", outcome="landed_verified")
    assert promoted != first and promoted.endswith("_2.json")
    assert json.load(open(first))["pl_value"] == 1
    assert json.load(open(promoted))["pl_value"] == 2


def test_reapplying_an_applied_inbox_action_is_a_clean_no_op(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    write_cs(tmp_path, [action(CR, "cleaning_reactivation")], status="applied")
    code, out = run_ia(fake, ["--apply", "--id", "pause_inbox:a1@d1.com", "--yes"], tmp_path)
    assert code == A.EXIT_OK and fake.writes == []
    assert "already applied" in "\n".join(out)
